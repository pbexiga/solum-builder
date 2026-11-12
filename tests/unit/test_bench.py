from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from solum import bench
from solum.cache import SimCache
from solum.circuit.build import CircuitBuilder
from solum.sim.engine import Plot, SimResult


def op_result() -> SimResult:
    return SimResult([Plot("op1", {n: np.array([4.5]) for n in ("c1", "c2", "c3", "c4")})])


class FakeEngine:
    name = "fake"

    def __init__(self) -> None:
        self.netlists: list[str] = []

    def version(self) -> str:
        return "1.0"

    def run(self, netlist: str) -> SimResult:
        self.netlists.append(netlist)
        if ".ac" in netlist:
            return SimResult([Plot("ac1", {"vw": np.array([1.0, 10.0 + 0j])})])
        if ".tran" in netlist:
            return SimResult([Plot("tran1", {"vw": np.array([0.0, -0.25, 0.1])})])
        return op_result()


def test_build_netlist_appends_case_lines_and_end() -> None:
    case = bench.Case("x", ("VIN in 0 0", ".op"))
    assert (
        bench.build_netlist("title\nR1 a 0 1k\n\n", case)
        == "title\nR1 a 0 1k\nVIN in 0 0\n.op\n.end"
    )


def test_audio_case_samples_at_96k_with_max_step() -> None:
    audio = next(c for c in bench.CASES if c.name == "tran_audio_5s")
    assert audio.lines[-1] == ".tran 1.041667e-05 5 0 1.041667e-05"
    assert ".save v(vw)" in audio.lines


def test_time_case_uses_the_clock_per_run() -> None:
    ticks: Iterator[float] = iter([0.0, 0.5, 1.0, 1.25])
    times, result = bench.time_case(FakeEngine(), "t\n.op", 2, clock=lambda: next(ticks))
    assert times == [0.5, 0.25]
    assert result.plots[0].kind == "op"


def test_summarise_reports_median_min_and_checks() -> None:
    op = bench.summarise(bench.CASES[0], [0.3, 0.1, 0.2], op_result())
    assert op == {
        "median_s": 0.2,
        "min_s": 0.1,
        "runs": 3,
        "check": {"c1": 4.5, "c2": 4.5, "c3": 4.5, "c4": 4.5},
    }
    ac = bench.summarise(bench.CASES[1], [1.0], FakeEngine().run("t\n.ac"))
    assert ac["check"] == {"points": 2, "peak_gain_db": 20.0}
    tran = bench.summarise(bench.CASES[2], [1.0], FakeEngine().run("t\n.tran"))
    assert tran["check"] == {"points": 3, "peak_out_v": 0.25}


def test_run_bench_skips_audio_when_asked() -> None:
    engine = FakeEngine()
    report = bench.run_bench(engine, "title", runs=2, audio_runs=0)
    assert list(report["results"]) == ["op", "ac", "tran_50ms"]
    assert len(engine.netlists) == 6
    assert report["engine"] == "fake"
    assert report["ngspice"] == "1.0"
    assert report["peak_rss_mb"] > 0


def test_machine_description_never_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_self: object) -> str:
        raise OSError("no /proc")

    monkeypatch.setattr(bench.Path, "read_text", missing)
    assert bench.cpu_model()
    assert bench.memory_gb() is None


def test_knob_turn_uses_a_new_rotation_each_time() -> None:
    c = CircuitBuilder().part("VR1", "pot", "a", "b", "c", value="10k").build()
    seen: list[float] = []
    ticks = iter([0.0, 0.2, 1.0, 1.1, 2.0, 2.3])

    def view(turned: object) -> None:
        seen.append(turned.part("VR1").rotation)  # type: ignore[attr-defined]

    result = bench.time_knob_turn(view, c, "VR1", 3, clock=lambda: next(ticks))
    assert seen == [0.25, 0.5, 0.75]
    assert result == {"median_s": 0.2, "max_s": 0.3, "runs": 3}


def test_the_cache_is_timed_per_call_and_left_empty(tmp_path: Path) -> None:
    cache = SimCache(tmp_path, max_bytes=10**6)
    ticks = iter([0.0, 0.04, 0.05])
    timed = bench.time_cache(cache, calls=4, clock=lambda: next(ticks))
    assert timed == {"put_ms": 10.0, "get_ms": 2.5, "calls": 4}
    assert cache.size() == 0 and not list(tmp_path.rglob("*.bin"))


def test_a_search_is_timed_first_and_again() -> None:
    calls: list[int] = []
    ticks = iter([0.0, 2.0, 2.25])
    timed = bench.time_search(lambda: calls.append(1), clock=lambda: next(ticks))
    assert timed == {"first_s": 2.0, "again_s": 0.25} and len(calls) == 2


def test_more_timings_go_under_their_names() -> None:
    report = bench.run_bench(FakeEngine(), "title", 1, 0, more={"cache": lambda: {"put_ms": 1}})
    assert report["results"]["cache"] == {"put_ms": 1}
