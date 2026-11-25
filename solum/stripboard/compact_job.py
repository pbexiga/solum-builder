"""*Build a full layout* as a job (D-399): the search's attempts on worker processes, their
progress and best board so far reported as they go, stopped when asked; and the time it
will take on this machine, measured.

A run is a fixed set of attempts (seeds), each a fixed number of steps by the circuit's
size (Quick, or Thorough's four times as many), so the same circuit and choice give the
same board on any machine: a slower one, or one with fewer workers (the seeds queue),
takes longer to the same board. *Try another* is the next set of seeds. When standing
parts is allowed, a fifth attempt lies everything flat (`FLAT_SEED`, the same steps:
Never's own board for that seed), so standing shapes can't leave a board breaking more
limits or with more warnings than lying flat would (D-403); it's the same for every try,
so it runs once per board and Try another reuses it. When every attempt, flat one too,
ends with a problem on its board (a short, a net not joined, a leg off the copper), the
rest of Never's seeds for the try run flat before Start a board's layout is kept: When
needed falls back only where Never would (D-403). The workers are spawned for the run
(not the render pool: a render and a layout don't queue behind each other) and end with it.
"""

import json
import math
import multiprocessing as mp
import os
import queue
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing.synchronize import Event as MpEvent
from typing import Any

from solum.cache import content_hash
from solum.circuit.io import circuit_to_dict
from solum.circuit.schema import Circuit
from solum.config import Settings
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import Layout, layout_data
from solum.stripboard.compact import Found, Problem, best_of, problem, search
from solum.stripboard.limits import LoudInput

WORKERS = min(4, max(1, (os.cpu_count() or 2) - 1))  # as renders' (D-083)
ATTEMPTS = 4  # seeds a run tries (P6h5a's measurement)
FLAT_SEED = 1  # the flat attempt's seed (D-403): Never's first board
RESCUE = 1000  # tags of the flat seeds run when no attempt found a board (+ the seed)
STEPS_PER_PART = 12_000  # Quick: each attempt's steps for each board part
MOST_PARTS = 40  # ...counted up to this many parts: a big board's run stays in minutes
THOROUGH = 4  # Thorough looks this many times as long
PROGRESS_EVERY = 0.2  # seconds between a worker's reports
SAMPLE = 0.5  # seconds of real steps the estimate times
# the opening's speed against a whole run's (it speeds up as the board shrinks: 0.5–1.0 on
# the starters, 0.77 typical) and a run lasting as long as its slowest seed (~10 %, P6h5g)
RAMP = 0.70
SPAWN = 1.5  # seconds a run spends starting its workers (measured on a Mac)
FELL_BACK = "Couldn't do better than Start a board's layout: here it is."


def steps_for(parts: int, thorough: bool) -> int:
    """Each attempt's steps: by the board parts (up to `MOST_PARTS`), four times as many
    when Thorough."""
    return STEPS_PER_PART * min(max(parts, 1), MOST_PARTS) * (THOROUGH if thorough else 1)


def seeds_for(attempt: int) -> list[int]:
    """Try `attempt`'s seeds: try 1 seeds 1–4, try 2 seeds 5–8…"""
    first = (max(attempt, 1) - 1) * ATTEMPTS + 1
    return list(range(first, first + ATTEMPTS))


# --- in a worker process ---------------------------------------------------------------

_worker: dict[str, Any] = {}


def _init_worker(settings: Settings, reports: "mp.Queue[Any]", stop: MpEvent) -> None:
    from solum.guides import footprint_table
    from solum.simulate import model_library

    _worker.update(models=model_library(settings), table=footprint_table(settings.library_dir),
                   reports=reports, stop=stop)  # fmt: skip


def _attempt(layout: Layout | None, circuit: Circuit, loud: Sequence[LoudInput],
             steps: int, seed: int, tag: int, flat: bool) -> Found | None:  # fmt: skip
    """One seed's search (`flat`: no standing shape), its progress reported every
    `PROGRESS_EVERY` seconds under `tag`."""
    pb = problem(layout, circuit, _worker["models"], _worker["table"], loud)
    reports, stop = _worker["reports"], _worker["stop"]
    last = 0.0

    count = 0

    def going(done: int, best: Found | None) -> bool:
        nonlocal last, count
        count = done
        now = time.monotonic()
        if now - last >= PROGRESS_EVERY:
            reports.put((tag, done, best, False))
            last = now
        return not stop.is_set()

    found = search(pb, steps, seed, going, flat)
    reports.put((tag, count, found, True))  # the last: the server waits for each attempt's
    return found


_flat: dict[str, Found | None] = {}  # the flat attempt's board, by what it searched (D-403)
FLAT_KEPT = 16  # boards' flat attempts kept, the oldest dropped


def _flat_key(pb: Problem, circuit: Circuit, loud: Sequence[LoudInput], steps: int) -> str:
    """What decides the flat attempt's board, hashed by content: the circuit as saved, the
    base board and its choices, the high-gain inputs the simulation found, the parts'
    shapes as the search sees them (footprints from the library), and the steps. The
    rules are the code's: the cache lives in the server's memory, so a new version of
    them (a restart) starts it empty."""
    shapes = [[ref, [[v.legs, v.standing] for v in pb.variants[ref]]] for ref in pb.refs]
    return content_hash(json.dumps(circuit_to_dict(circuit), sort_keys=True),
                        json.dumps(layout_data(pb.base), sort_keys=True),
                        json.dumps([[i.ref, i.pin, sorted(i.quiet), sorted(i.along)]
                                    for i in loud]),
                        json.dumps(shapes), str(steps))  # fmt: skip


def flat_needed(pb: Problem) -> bool:
    """Whether a run adds the flat attempt: when the board's choice stands parts (D-403)."""
    return pb.stand_up != "never"


# --- in the server -----------------------------------------------------------------

Report = Callable[[int, int, Found | None], None]  # steps done, of how many, a new best


@dataclass(frozen=True)
class Run:
    """A run's problem (its base board) and the best board over its seeds (None: none
    without a problem), and whether it was stopped before the end."""

    pb: Problem
    best: Found | None
    stopped: bool


def run(pb: Problem, layout: Layout | None, circuit: Circuit, loud: Sequence[LoudInput],
        thorough: bool, attempt: int, settings: Settings, report: Report,
        stop: threading.Event) -> Run:  # fmt: skip
    """Try `attempt`'s seeds on up to `WORKERS` processes, telling `report` the steps done
    and each new best; `stop` set ends every worker at its next check, with its best so
    far. `pb` is the server's own reading of the same circuit (the workers read it again:
    the same base)."""
    steps = steps_for(len(pb.refs), thorough)
    seeds = seeds_for(attempt)
    jobs = [(s, s, False) for s in seeds]  # (tag, seed, flat)
    flat = _flat_key(pb, circuit, loud, steps) if flat_needed(pb) else None
    known: list[Found | None] = []
    if flat is not None and flat in _flat:
        known.append(_flat[flat])  # Try another: the same flat board as before
    elif flat is not None:
        jobs.append((0, FLAT_SEED, True))  # tag 0: no seed's (they start at 1)
    ctx = mp.get_context("spawn")
    reports: mp.Queue[Any] = ctx.Queue()
    halt = ctx.Event()
    done = {tag: 0 for tag, _, _ in jobs}
    found: dict[int, Found] = {i: f for i, f in enumerate(known, -len(known)) if f}
    best: Found | None = best_of(found.values())
    ended: set[int] = set()

    def take(tag: int, steps_done: int, f: Found | None, last: bool) -> None:
        nonlocal best
        done[tag] = steps_done
        if last:
            ended.add(tag)
        if f is not None:
            found[tag] = f
        now = best_of(found.values())
        report(sum(done.values()), steps * len(done), now if now != best else None)
        best = now

    def attempts(jobs: list[tuple[int, int, bool]]) -> list[Found | None]:
        """`jobs` (tag, seed, flat) on the workers, each reported to `take` as it goes."""
        done.update({tag: 0 for tag, _, _ in jobs})
        with ProcessPoolExecutor(min(WORKERS, len(jobs)), mp_context=ctx,
                                 initializer=_init_worker,
                                 initargs=(settings, reports, halt)) as pool:  # fmt: skip
            futures = [pool.submit(_attempt, layout, circuit, loud, steps, seed, tag, fl)
                       for tag, seed, fl in jobs]  # fmt: skip
            while not {tag for tag, _, _ in jobs} <= ended:
                if stop.is_set():
                    halt.set()
                failed = next((f for f in futures if f.done() and f.exception()), None)
                if failed is not None:
                    halt.set()
                    failed.result()  # a worker's error, raised here
                try:
                    take(*reports.get(timeout=0.1))
                except queue.Empty:
                    continue
            return [f.result() for f in futures]

    results = attempts(jobs)
    if flat is not None and flat not in _flat and not stop.is_set():
        _flat[flat] = results[-1]  # a whole run's flat board only, never a stopped one's
        while len(_flat) > FLAT_KEPT:
            del _flat[next(iter(_flat))]
    results += known
    if flat is not None and best_of(results) is None and not stop.is_set():
        # no board without a problem: the rest of Never's seeds, before Start a board's
        rescue = [(RESCUE + s, s, True) for s in seeds if s != FLAT_SEED]
        results += attempts(rescue)
    return Run(pb, best_of(results), stop.is_set())


@dataclass(frozen=True)
class Estimate:
    """How long Quick and Thorough take on this circuit on this machine, in seconds."""

    quick: float
    thorough: float


def estimate(layout: Layout | None, circuit: Circuit, models: ModelLibrary,
             table: FootprintTable, loud: Sequence[LoudInput]) -> Estimate:  # fmt: skip
    """Time `SAMPLE` seconds of real steps on this circuit, here, and scale them to each
    choice's steps, attempts and workers, corrected for the run speeding up as the board
    shrinks (`RAMP`); plus what every worker does first (the base)."""
    started = time.monotonic()
    pb = problem(layout, circuit, models, table, loud)
    base = time.monotonic() - started
    timing: list[float] = []
    counted = 0

    def going(done: int, _best: Found | None) -> bool:
        nonlocal counted
        timing.append(time.monotonic())
        counted = done
        return timing[-1] - timing[0] < SAMPLE

    search(pb, 10**9, 1, going)
    speed = counted / max(timing[-1] - timing[0], 1e-3) / RAMP if counted else 1e4

    def seconds(thorough: bool) -> float:
        steps = steps_for(len(pb.refs), thorough)
        flat = flat_needed(pb) and _flat_key(pb, circuit, loud, steps) not in _flat
        # the flat attempt too (D-403): it starts as the quickest attempt ends and runs
        # mostly alone, so it costs its share, not a whole round (TS808: +26 %, 4 workers)
        rounds = max(math.ceil(ATTEMPTS / WORKERS), (ATTEMPTS + flat) / WORKERS)
        return SPAWN + base + rounds * steps / speed

    return Estimate(round(seconds(False), 1), round(seconds(True), 1))
