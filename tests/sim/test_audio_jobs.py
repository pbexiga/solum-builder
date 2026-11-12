"""Render jobs in real worker processes (each with its own ngspice)."""

import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import solum.audio.jobs as jobs_module
from solum.audio.jobs import CANCELLED, CRASHED, Job, RenderJobs, Result, render_in_worker
from solum.audio.render import Inputs, render_key
from solum.audio.wav import Audio, read_wav, write_wav
from solum.cache import SimCache
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import circuit_to_dict, parse_circuit
from solum.config import Settings, load_settings
from solum.models import ModelLibrary
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]


def clip() -> bytes:
    t = np.arange(4410) / 44100
    return write_wav(Audio(44100, 0.5 * np.sin(2 * np.pi * 220 * t)))


def lowpass() -> dict[str, Any]:
    c = (
        CircuitBuilder("rc")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="10k")
        .part("C1", "capacitor", "out", "0", value="15n")
        .part("OUT", "amp", "out")
        .build()
    )
    return circuit_to_dict(c)


def crash(job_id: str, key: str, circuit: object, inputs: object) -> Result:
    os._exit(1)  # what a segfault in ngspice looks like to the pool


def by_key(job_id: str, key: str, circuit: object, inputs: object) -> Result:
    """`stuck` never stops (a step with no progress reports); `slow` takes 1.5 s; the rest
    answer at once. Each leaves a file saying it started."""
    from solum.audio.jobs import _worker

    (Path(_worker["settings"].cache_dir) / f"started-{key}").touch()
    if key == "stuck":
        time.sleep(600)
    if key == "slow":
        time.sleep(1.5)
    return True, "", {"seconds": 1.0}


def long_clip(seconds: float) -> bytes:
    t = np.arange(int(44100 * seconds)) / 44100
    return write_wav(Audio(44100, 0.5 * np.sin(2 * np.pi * 220 * t)))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings({"DATA_DIR": str(tmp_path / "data"), "CACHE_DIR": str(tmp_path / "cache"),
                          "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip


def wait(jobs: RenderJobs, job: Job, timeout: float = 60) -> Job:
    deadline = time.monotonic() + timeout
    while job.state in ("queued", "running"):
        assert time.monotonic() < deadline, "render job didn't finish"
        time.sleep(0.05)
    found = jobs.get(job.id)
    assert found is not None
    return found


def test_a_render_lands_in_the_cache_and_is_instant_after(
    settings: Settings, engine: NativeNgspice
) -> None:
    cache = SimCache(settings.cache_dir, 10**9)
    jobs = RenderJobs(settings, cache, workers=2)
    try:
        key = render_key(Simulator(engine, ModelLibrary({})), parse_circuit(lowpass()),
                         Inputs(clip()), settings.cache_dir)  # fmt: skip
        job = jobs.submit(key, "rc", lowpass(), Inputs(clip()))
        assert jobs.submit(key, "rc", lowpass(), Inputs(clip())) is job  # asked twice
        done = wait(jobs, job)
        assert (done.state, done.progress, done.message) == ("done", 1.0, "")
        assert done.seconds == pytest.approx(0.1) and done.peak > 0
        wav = cache.get_bytes(key)
        assert wav is not None and read_wav(wav).rate == 48000
        again = jobs.submit(key, "rc", lowpass(), Inputs(clip()))
        assert again is not job and again.state == "done"  # from the cache, no worker
        assert again.view() | {"id": job.id} == done.view()  # with its stats
    finally:
        jobs.close()


def test_a_failed_render_says_why_in_plain_english(settings: Settings) -> None:
    jobs = RenderJobs(settings, SimCache(settings.cache_dir, 10**9), workers=1)
    try:
        no_amp = lowpass()
        no_amp["parts"] = [p for p in no_amp["parts"] if p["type"] != "amp"]
        done = wait(jobs, jobs.submit("k1", "rc", no_amp, Inputs(clip())))
        assert done.state == "failed" and "amp output" in done.message
    finally:
        jobs.close()


def test_a_crashed_worker_fails_its_job_and_the_pool_restarts(settings: Settings) -> None:
    jobs = RenderJobs(settings, SimCache(settings.cache_dir, 10**9), workers=1, work=crash)
    try:
        done = wait(jobs, jobs.submit("k2", "rc", lowpass(), Inputs(clip())))
        assert (done.state, done.message) == ("failed", CRASHED)
        jobs.work = render_in_worker
        done = wait(jobs, jobs.submit("k3", "rc", lowpass(), Inputs(clip())))
        assert done.state == "done"
    finally:
        jobs.close()


def test_a_queued_render_is_dropped_when_cancelled(settings: Settings) -> None:
    jobs = RenderJobs(settings, SimCache(settings.cache_dir, 10**9), workers=1, work=by_key)
    try:
        first = jobs.submit("slow", "a", None, Inputs(clip()))
        queued = [jobs.submit(f"q{i}", "b", None, Inputs(clip())) for i in range(3)]
        assert first is not None and all(queued)
        for job in queued:
            assert job is not None
            cancelled = jobs.cancel(job.id)
            assert cancelled is job and (job.state, job.message) == ("cancelled", CANCELLED)
        assert wait(jobs, first).state == "done"
        time.sleep(0.3)
        assert all(j is not None and j.state == "cancelled" for j in queued)
        assert jobs.cancel(first.id) is first and first.state == "done"  # finished: kept
        assert jobs.cancel("nope") is None
        again = jobs.submit("q0", "b", None, Inputs(clip()))  # asked again: a new job
        assert again is not None and again is not queued[0]
        assert wait(jobs, again).state == "done"
    finally:
        jobs.close()


def test_a_running_render_stops_at_its_next_progress_report_and_caches_nothing(
    settings: Settings, engine: NativeNgspice
) -> None:
    cache = SimCache(settings.cache_dir, 10**9)
    jobs = RenderJobs(settings, cache, workers=1)
    try:
        inputs = Inputs(long_clip(10.0))
        job = jobs.submit("long", "rc", lowpass(), inputs)
        assert job is not None
        deadline = time.monotonic() + 60
        while job.state != "running" or job.progress == 0:
            assert time.monotonic() < deadline, "the render never reported progress"
            time.sleep(0.05)
        jobs.cancel(job.id)
        start = time.monotonic()
        assert job.state == "cancelled"
        # the worker is free again within a moment: the next job runs and finishes
        after = jobs.submit("k-after", "rc", lowpass(), Inputs(clip()))
        assert after is not None and wait(jobs, after).state == "done"
        assert time.monotonic() - start < jobs_module.KILL_AFTER  # stopped, not killed
        assert not cache.has("long") and job.state == "cancelled"
        assert not list((settings.cache_dir / "cancelled").iterdir())  # flags tidied
    finally:
        jobs.close()


def test_a_render_that_wont_stop_has_its_pool_killed_and_the_others_restarted(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs_module, "KILL_AFTER", 0.5)
    jobs = RenderJobs(settings, SimCache(settings.cache_dir, 10**9), workers=2, work=by_key)
    try:
        stuck = jobs.submit("stuck", "a", None, Inputs(clip()))
        other = jobs.submit("slow", "b", None, Inputs(clip()))
        assert stuck is not None and other is not None
        deadline = time.monotonic() + 60
        while not all((settings.cache_dir / f"started-{k}").exists() for k in ("stuck", "slow")):
            assert time.monotonic() < deadline, "the jobs never started"
            time.sleep(0.05)
        jobs.cancel(stuck.id)
        done = wait(jobs, other, timeout=30)
        assert done.state == "done" and stuck.state == "cancelled"
        later = jobs.submit("k-later", "c", None, Inputs(clip()))
        assert later is not None and wait(jobs, later).state == "done"
    finally:
        jobs.close()
