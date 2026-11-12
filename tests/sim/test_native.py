"""Engine-level tests on raw SPICE text (circuits go through the netlist generator
elsewhere; these exercise what the engine itself must survive)."""

import time
from pathlib import Path

import pytest

from solum.sim.engine import SimError
from solum.sim.native import NativeNgspice, native_engine


def spice(*lines: str) -> str:
    return "\n".join(("test circuit", *lines, ".end"))


def divider(top: float = 1e3) -> str:
    return spice("V1 a 0 9", f"R1 a b {top}", "R2 b 0 2000", ".op")


def test_reports_version(engine: NativeNgspice) -> None:
    assert engine.version().split(".")[0].isdigit()


def test_engine_is_one_per_process(engine: NativeNgspice) -> None:
    assert native_engine() is engine


def test_divider_dc(engine: NativeNgspice) -> None:
    op = engine.run(divider()).plot("op")
    assert op.vectors["b"][0] == pytest.approx(6.0, abs=1e-9)
    assert op.vectors["v1#branch"][0] == pytest.approx(-3e-3, rel=1e-9)


def test_runs_do_not_leak_between_circuits(engine: NativeNgspice) -> None:
    engine.run(divider())
    result = engine.run(divider(top=2e3))
    assert [p.kind for p in result.plots] == ["op"]
    assert result.plot("op").vectors["b"][0] == pytest.approx(4.5, abs=1e-9)


def test_every_analysis_comes_back_by_kind(engine: NativeNgspice) -> None:
    net = spice("V1 a 0 DC 1 AC 1", "R1 a b 1e3", "C1 b 0 1e-6",
                ".op", ".ac dec 5 10 1k", ".tran 1u 10u")  # fmt: skip
    result = engine.run(net)
    assert sorted(p.kind for p in result.plots) == ["ac", "op", "tran"]
    assert len(result.plot("ac").vectors["frequency"]) == 11
    assert result.plot("op").vectors["b"][0] == pytest.approx(1.0)


def test_bad_netlist_is_plain_error_with_log(engine: NativeNgspice) -> None:
    with pytest.raises(SimError, match="couldn't be loaded") as err:
        engine.run(spice("Q1 c b e NOSUCHMODEL", ".op"))
    assert any("nosuchmodel" in line.lower() for line in err.value.log)


def test_recovers_after_ngspice_gives_up(engine: NativeNgspice) -> None:
    """A text model parameter makes ngspice wait to be reset (D-028); we reload it."""
    fatal = spice("VD d 0 10", "J1 d 0 0 JX", ".model JX NJF(VTO=-1 MFG=PHILIPS)", ".op")
    for _ in range(2):
        with pytest.raises(SimError):
            engine.run(fatal)
        assert engine.run(divider()).plot("op").vectors["b"][0] == pytest.approx(6.0)


def test_star_hash_lines_do_not_hang(engine: NativeNgspice) -> None:
    """NXP's 1N4148 file has a bare `*#` line, which ngspice runs as a command (D-028)."""
    net = spice("*#", "I1 0 a 1e-3", "D1 a 0 DX", ".model DX D(IS=4.352E-9 N=1.906 RS=0.6458)",
                ".op")  # fmt: skip
    assert engine.run(net).plot("op").vectors["a"][0] == pytest.approx(0.609, abs=0.005)


def test_poly_sources_need_code_models(engine: NativeNgspice) -> None:
    """TI's TL072 macromodel uses POLY sources; the image ships spice2poly (D-027)."""
    net = spice("V1 a 0 2", "R1 a 0 1e3", "E1 b 0 POLY(1) (a,0) 1 3", "R2 b 0 1e3", ".op")
    assert engine.run(net).plot("op").vectors["b"][0] == pytest.approx(7.0, abs=1e-6)


def test_a_run_that_takes_too_long_is_stopped(engine: NativeNgspice) -> None:
    slow = spice("V1 a 0 SIN(0 1 1k)", "R1 a b 1k", "C1 b 0 1u", ".tran 1n 10")
    with pytest.raises(SimError, match=r"took longer than 0\.2 s"):
        engine.run(slow, timeout=0.2)
    assert engine.run(divider()).plot("op").vectors["b"][0] == pytest.approx(6.0)


def test_long_transients_report_progress(engine: NativeNgspice) -> None:
    seen: list[float] = []
    net = spice("V1 a 0 SIN(0 1 1k)", "R1 a b 1k", "C1 b 0 100n", ".tran 1u 2 0 1u")
    engine.run(net, timeout=None, progress=seen.append)
    assert seen and seen == sorted(seen) and 0 < seen[-1] <= 1
    seen.clear()
    engine.run(net, timeout=None)  # no callback: nothing called, nothing kept
    assert not seen


class Stop(Exception):
    pass


def test_a_progress_callback_that_raises_stops_the_run(engine: NativeNgspice) -> None:
    """A cancelled render: the progress callback raises, ngspice is halted at once and the
    exception comes out of `run`; the engine runs the next netlist as usual."""
    slow = spice("V1 a 0 SIN(0 1 1k)", "R1 a b 1k", "C1 b 0 1u", ".tran 1n 10")
    calls: list[float] = []  # when the callback raised

    def stop(fraction: float) -> None:
        calls.append(time.monotonic())
        raise Stop

    with pytest.raises(Stop):
        engine.run(slow, timeout=120, progress=stop)
    assert len(calls) == 1 and time.monotonic() - calls[0] < 5  # halted, not run to the end
    assert engine.run(divider()).plot("op").vectors["b"][0] == pytest.approx(6.0)


def test_a_file_source_plays_its_recording(engine: NativeNgspice, tmp_path: Path) -> None:
    """XSPICE `filesource` (audio renders): linear between points, scaled by amplscale."""
    rec = tmp_path / "rec.txt"
    rec.write_text("0 0\n1e-3 1\n2e-3 -1\n")
    net = spice(
        "A1 %vd([a 0]) rec",
        f'.model rec filesource (file="{rec}" amploffset=[0] amplscale=[0.5] timeoffset=0 '
        "timescale=1 timerelative=false amplstep=false)",
        "R1 a 0 1k",
        ".tran 1e-5 2e-3 0 1e-5",
    )
    v = engine.run(net).plot("tran").vectors
    t, a = v["time"].real, v["a"].real
    assert float(a[abs(t - 0.5e-3).argmin()]) == pytest.approx(0.25, abs=0.01)
    assert float(a[abs(t - 1.5e-3).argmin()]) == pytest.approx(0.0, abs=0.01)
