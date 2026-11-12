"""`solum bench`: time the Big Muff bench netlist through the active engine.

Prints a JSON report the user can paste back from another machine (the NAS).
"""

import os
import platform
import resource
import statistics
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from solum import __version__
from solum.cache import SimCache, content_hash
from solum.circuit.schema import Circuit
from solum.sim.engine import Plot, SimEngine, SimResult

AUDIO_RATE = 96_000


@dataclass(frozen=True)
class Case:
    name: str
    lines: tuple[str, ...]  # appended after the circuit: source, .save, analysis


CASES: tuple[Case, ...] = (
    Case("op", ("VIN in 0 DC 0", ".op")),
    Case("ac", ("VIN in 0 DC 0 AC 1", ".ac dec 100 10 100k")),
    Case("tran_50ms", ("VIN in 0 DC 0 SIN(0 0.1 196)", ".tran 10u 50m")),
    Case(
        "tran_audio_5s",
        (
            "VIN in 0 DC 0 SIN(0 0.1 196)",
            ".save v(vw)",
            f".tran {1 / AUDIO_RATE:.6e} 5 0 {1 / AUDIO_RATE:.6e}",
        ),
    ),
)


def build_netlist(circuit: str, case: Case) -> str:
    """The bench circuit with the case's input source and analysis appended."""
    return "\n".join((circuit.rstrip(), *case.lines, ".end"))


def time_case(
    engine: SimEngine, netlist: str, runs: int, clock: Callable[[], float] = time.perf_counter
) -> tuple[list[float], SimResult]:
    """Run `netlist` `runs` times; return each run's wall time and the last result."""
    times: list[float] = []
    result: SimResult | None = None
    for _ in range(runs):
        start = clock()
        result = engine.run(netlist)
        times.append(clock() - start)
    assert result is not None
    return times, result


def summarise(case: Case, times: list[float], result: SimResult) -> dict[str, Any]:
    """Timing stats plus a small sanity check that the simulation did real work."""
    plot = result.plots[0]  # each bench case runs exactly one analysis
    out: dict[str, Any] = {
        "median_s": round(statistics.median(times), 4),
        "min_s": round(min(times), 4),
        "runs": len(times),
    }
    if plot.kind == "op":
        out["check"] = {n: round(float(plot.vectors[n][0]), 3) for n in ("c1", "c2", "c3", "c4")}
    elif plot.kind == "ac":
        gain = np.abs(plot.vectors["vw"])
        out["check"] = {"points": len(gain), "peak_gain_db": round(20 * np.log10(gain.max()), 2)}
    else:
        vw = plot.vectors["vw"]
        out["check"] = {"points": len(vw), "peak_out_v": round(float(np.abs(vw).max()), 3)}
    return out


KNOB = ("ts808", "VR2")  # starter and pot for the knob-turn timing: the TS808's Tone


def time_knob_turn(
    view: Callable[[Circuit], object],
    circuit: Circuit,
    ref: str,
    runs: int,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Server time for one knob change: `view` (the viewer's run: DC, frequency response,
    scope) at a new rotation each time, so nothing comes from the cache. Phase 2's
    "Tone updates the curve in < 1 s" is this plus the browser's redraw (~tens of ms)."""
    times = []
    for i in range(runs):
        turned = circuit.with_part(ref, rotation=(i + 1) / (runs + 1))
        start = clock()
        view(turned)
        times.append(clock() - start)
    return {"median_s": round(statistics.median(times), 4), "max_s": round(max(times), 4),
            "runs": runs}  # fmt: skip


CACHE_CALLS = 200
SEARCH = ("big-muff-pi-v3", "Q4")  # Find parts on the Big Muff's last stage (D-126's search)


def time_cache(
    cache: SimCache, calls: int = CACHE_CALLS, clock: Callable[[], float] = time.perf_counter
) -> dict[str, Any]:
    """The cache where it lives: `calls` small results written, then read back, in ms a
    call; they are forgotten afterwards. On a local disk each is a fraction of a
    millisecond. An index that syncs to disk on every call (D-126) shows as ~10 ms: a
    search makes thousands of them."""
    result = SimResult([Plot("op1", {"v": np.array([1.0])})])
    keys = [content_hash("bench", str(os.getpid()), str(i)) for i in range(calls)]
    start = clock()
    for key in keys:
        cache.put(key, result)
    written = clock()
    for key in keys:
        cache.get(key)
    read = clock()
    for key in keys:
        cache.forget(key)
    return {"put_ms": round((written - start) / calls * 1e3, 3),
            "get_ms": round((read - written) / calls * 1e3, 3), "calls": calls}  # fmt: skip


def time_search(
    search: Callable[[], object], clock: Callable[[], float] = time.perf_counter
) -> dict[str, Any]:
    """A search through the cache, as the app runs it: its first run (every simulation
    real, every result written) and the same again (every result read back)."""
    start = clock()
    search()
    first = clock()
    search()
    return {"first_s": round(first - start, 3), "again_s": round(clock() - first, 3)}


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def memory_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024**2, 1)
    except OSError:
        pass
    return None


def run_bench(
    engine: SimEngine,
    circuit: str,
    runs: int,
    audio_runs: int = 1,
    more: Mapping[str, Callable[[], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Time every case and return the JSON-ready report. `audio_runs=0` skips the 5 s render;
    `more` adds a timing under each of its names (`knob_turn`, `cache`, `find_parts`)."""
    results: dict[str, Any] = {}
    total_start = time.perf_counter()
    for case in CASES:
        n = audio_runs if case.name == "tran_audio_5s" else runs
        if n < 1:
            continue
        times, result = time_case(engine, build_netlist(circuit, case), n)
        results[case.name] = summarise(case, times, result)
    for name, timed in (more or {}).items():
        results[name] = timed()
    return {
        "solum": __version__,
        "engine": engine.name,
        "ngspice": engine.version(),
        "cpu": cpu_model(),
        "cpu_count": os.cpu_count(),
        "memory_gb": memory_gb(),
        "python": platform.python_version(),
        "circuit": "library/bench/big-muff.cir",
        "results": results,
        "total_s": round(time.perf_counter() - total_start, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
