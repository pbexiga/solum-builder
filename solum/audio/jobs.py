"""Render jobs: renders run in worker processes, report progress, land in the cache (D-083).

ngspice keeps global state, one run at a time per process (D-028), so parallel renders
(a render sweep) need separate processes. Workers also keep an ngspice crash away from
the server (D-040): a dead worker fails its job with a plain message and the pool is
started again.

A job is known by its render key: asking for a render that's cached answers at once,
and asking again while it runs gets the same job.

A job can be cancelled (D-240): a queued one is dropped; a running one stops at its next
progress report, where its worker finds the job's flag file; one that doesn't stop
within `KILL_AFTER` s has its pool killed (the crash path), the other jobs on it started
again. A cancelled render caches no take.
"""

import json
import logging
import multiprocessing as mp
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any, Literal

from solum.audio.render import Inputs, Rendered, render
from solum.cache import SimCache, cache_from_settings, content_hash
from solum.config import Settings

log = logging.getLogger("solum.audio")

State = Literal["queued", "running", "done", "failed", "cancelled"]
WORKERS = min(4, max(1, (os.cpu_count() or 2) - 1))
PROGRESS_EVERY = 0.2  # seconds between a worker's progress messages
KILL_AFTER = 5.0  # seconds a cancelled job may take to stop before its pool is killed
CANCELLED = "Render cancelled."
CRASHED = (
    "The simulator stopped unexpectedly while rendering. Try again; if it happens again, "
    "check the Problems panel for a part with an extreme value."
)


@dataclass
class Job:
    id: str
    key: str
    label: str  # what the job renders, for the panel ("VR1 at 30 %")
    state: State = "queued"
    progress: float = 0.0
    message: str = ""
    seconds: float = 0.0
    peak: float = 0.0
    amp_in: float = 0.0  # peak into the amp capture (1 = its 0 dBFS)
    amp_compression: float = 0.0  # dB the capture squashed it (0 = clean)

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id, "key": self.key, "label": self.label, "state": self.state,
            "progress": round(self.progress, 3), "message": self.message,
            "seconds": self.seconds, "peak": self.peak, "amp_in": self.amp_in,
            "amp_compression": self.amp_compression,
        }  # fmt: skip

    def take(self, stats: dict[str, float]) -> None:
        self.seconds = stats.get("seconds", 0.0)
        self.peak = stats.get("peak", 0.0)
        self.amp_in = stats.get("amp_in", 0.0)
        self.amp_compression = stats.get("amp_compression", 0.0)


Result = tuple[bool, str, dict[str, float]]  # ok, message, the render's stats


class Cancelled(Exception):
    """Raised in a worker at the progress report after its job was cancelled."""


def cancel_flag(cache_dir: Path, job_id: str) -> Path:
    """The file whose presence tells a worker its job was cancelled."""
    return cache_dir / "cancelled" / job_id


def stats_key(key: str) -> str:
    """Where a render's stats (`Rendered.stats`) are cached, next to its WAV."""
    return content_hash(key, "stats")


def spectra_key(key: str) -> str:
    """Where a render's spectra (`Rendered.spectra`, D-096) are cached, next to its WAV."""
    return content_hash(key, "spectra")


# --- in the worker process ---------------------------------------------------------

_worker: dict[str, Any] = {}


def _init_worker(settings: Settings, queue: "Queue[tuple[str, float]]") -> None:
    from solum.rules.run import Checker, rule_book
    from solum.sim.engine import engine_from_settings
    from solum.simulate import Simulator, model_library

    models = model_library(settings)
    _worker["sim"] = Simulator(engine_from_settings(settings), models)
    _worker["checker"] = Checker(rule_book(settings.library_dir), models)
    _worker["settings"] = settings
    _worker["cache"] = cache_from_settings(settings)
    _worker["queue"] = queue


def _message(err: Exception) -> str:
    """A failed render in plain English (never a traceback, AGENTS.md)."""
    from solum.audio.assets import AssetError
    from solum.audio.nam import NamError
    from solum.audio.render import RenderError
    from solum.audio.wav import WavError
    from solum.bias import BiasError
    from solum.circuit.connectivity import ConnectivityError
    from solum.circuit.io import CircuitError
    from solum.netlist import NetlistError
    from solum.sim.engine import SimError

    if isinstance(err, SimError):
        return str(_worker["checker"].message(err))
    plain = (AssetError, NamError, RenderError, WavError, BiasError, ConnectivityError,
             CircuitError, NetlistError)  # fmt: skip
    if isinstance(err, plain):
        return str(err)
    log.exception("Render failed", exc_info=err)
    return "The render failed inside Solum Builder. The server log has details."


def render_in_worker(
    job_id: str, key: str, circuit: dict[str, Any] | None, inputs: Inputs
) -> Result:
    """Render and cache it (the WAV and its stats). Runs in a worker process."""
    from solum.circuit.io import parse_circuit

    settings: Settings = _worker["settings"]
    queue = _worker["queue"]
    flag = cancel_flag(settings.cache_dir, job_id)
    last = [0.0]

    def progress(fraction: float) -> None:
        now = time.monotonic()
        if now - last[0] >= PROGRESS_EVERY or fraction >= 1.0:
            last[0] = now
            if flag.exists():
                raise Cancelled
            queue.put((job_id, fraction))

    if flag.exists():  # cancelled while it waited in the pool's queue
        return False, CANCELLED, {}
    cache: SimCache = _worker["cache"]
    try:
        parsed = parse_circuit(circuit) if circuit is not None else None
        out: Rendered = render(_worker["sim"], parsed, inputs, settings.cache_dir, progress, cache)
    except Cancelled:
        return False, CANCELLED, {}
    except Exception as err:
        return False, _message(err), {}
    if flag.exists():
        return False, CANCELLED, {}
    cache.put_bytes(spectra_key(key), json.dumps(out.spectra).encode())
    cache.put_bytes(stats_key(key), json.dumps(out.stats()).encode())  # before the WAV:
    cache.put_bytes(key, out.wav)  # a cached WAV always has its stats
    return True, "", out.stats()


# --- in the server -----------------------------------------------------------------

Work = Callable[[str, str, dict[str, Any] | None, Inputs], Result]


@dataclass
class _Work:
    circuit: dict[str, Any] | None
    inputs: Inputs
    future: "Future[Result]"
    pool: ProcessPoolExecutor


class RenderJobs:
    """Render jobs by id, run by a pool of `workers` processes."""

    def __init__(
        self, settings: Settings, cache: SimCache, workers: int = WORKERS,
        work: Work = render_in_worker,
    ) -> None:  # fmt: skip
        self.settings = settings
        self.cache = cache
        self.workers = workers
        self.work = work
        self._ctx = mp.get_context("spawn")  # a fresh process: no inherited ngspice state
        self._queue: Queue[tuple[str, float]] = self._ctx.Queue()
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._running: dict[str, str] = {}  # key → job id, while queued or running
        # job id → what it was started with, its future and its pool, while queued or running
        self._work: dict[str, _Work] = {}
        self._requeue: set[str] = set()  # job ids whose pool was killed under them
        self._pool: ProcessPoolExecutor | None = None
        threading.Thread(target=self._read_progress, daemon=True).start()

    def _executor(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(
                self.workers, mp_context=self._ctx, initializer=_init_worker,
                initargs=(self.settings, self._queue),
            )  # fmt: skip
        return self._pool

    def _read_progress(self) -> None:
        while True:
            job_id, fraction = self._queue.get()
            with self._lock:
                job = self._jobs.get(job_id)
                if job and job.state in ("queued", "running"):
                    job.state, job.progress = "running", max(job.progress, fraction)

    def submit(
        self,
        key: str,
        label: str,
        circuit: dict[str, Any] | None,
        inputs: Inputs,
        cached_only: bool = False,
    ) -> Job | None:
        """A job for this render: done at once if cached, the running one if asked twice.
        `cached_only`: never start one; None if it isn't cached or running."""
        with self._lock:
            if key in self._running:
                return self._jobs[self._running[key]]
            if cached_only and not self.cache.has(key):
                return None
            job = Job(uuid.uuid4().hex, key, label)
            self._jobs[job.id] = job
            if self.cache.has(key):
                job.state, job.progress = "done", 1.0
                stats = self.cache.get_bytes(stats_key(key))
                job.take(json.loads(stats) if stats else {})
                return job
            self._running[key] = job.id
            future = self._start(job, circuit, inputs)
        future.add_done_callback(lambda f: self._finished(job, f))
        return job

    def _start(self, job: Job, circuit: dict[str, Any] | None, inputs: Inputs) -> "Future[Result]":
        """Hand the job to the pool (the lock held; the caller adds `_finished`)."""
        try:
            future = self._executor().submit(self.work, job.id, job.key, circuit, inputs)
        except BrokenProcessPool:
            self._pool = None
            future = self._executor().submit(self.work, job.id, job.key, circuit, inputs)
        self._work[job.id] = _Work(circuit, inputs, future, self._executor())
        return future

    def cancel(self, job_id: str) -> Job | None:
        """Stop a job: dropped if it hasn't started, else stopped at its next progress
        report, else its pool killed after `KILL_AFTER` s. A finished job is left as it is."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state not in ("queued", "running"):
                return job
            job.state, job.message = "cancelled", CANCELLED
            if self._running.get(job.key) == job.id:
                del self._running[job.key]  # asking again starts afresh
            work = self._work.get(job.id)
        if work is None or work.future.cancel():
            return job
        flag = cancel_flag(self.settings.cache_dir, job.id)
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        timer = threading.Timer(KILL_AFTER, self._kill_if_running, (work,))
        timer.daemon = True
        timer.start()
        return job

    def _kill_if_running(self, work: _Work) -> None:
        """A cancelled job still running: kill its pool's workers (a stuck ngspice run, or
        a step with no progress reports); the other jobs on it start again on a new pool."""
        pool = work.pool
        with self._lock:
            if work.future.done():
                return
            if self._pool is pool:
                self._pool = None
            for job_id, other in self._work.items():
                if other.pool is pool and self._jobs[job_id].state != "cancelled":
                    self._requeue.add(job_id)
        for process in list(pool._processes.values()):
            process.kill()
        pool.shutdown(wait=False, cancel_futures=True)

    def _finished(self, job: Job, future: "Future[Result]") -> None:
        again: Future[Result] | None = None
        with self._lock:
            work = self._work.pop(job.id, None)
            cancel_flag(self.settings.cache_dir, job.id).unlink(missing_ok=True)
            if job.state == "cancelled":
                self._requeue.discard(job.id)
                return
            try:
                ok, message, stats = future.result()
            except (BrokenProcessPool, CancelledError):  # crashed, or its pool killed
                ok, message, stats = False, CRASHED, {}
                if work is not None and self._pool is work.pool:
                    self._pool = None  # started again on the next submit
                if job.id in self._requeue and work is not None:
                    self._requeue.discard(job.id)
                    job.state, job.progress = "queued", 0.0
                    again = self._start(job, work.circuit, work.inputs)
            except Exception as err:  # the pool itself failed; the job says so
                log.exception("Render job failed", exc_info=err)
                ok, message, stats = False, CRASHED, {}
            if again is None:
                self._done(job, ok, message, stats)
        if again is not None:
            again.add_done_callback(lambda f: self._finished(job, f))

    def _done(self, job: Job, ok: bool, message: str, stats: dict[str, float]) -> None:
        """Record a job's result (the lock held)."""
        if self._running.get(job.key) == job.id:
            del self._running[job.key]
        job.state = "done" if ok else "failed"
        job.progress = 1.0 if ok else job.progress
        job.message = message
        job.take(stats)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
