"""The pipeline end to end on small circuits: op, ac (with the invalid flag), tran, cache."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from solum.analysis.measures import corner_3db
from solum.cache import CachedEngine, SimCache
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.models import ModelLibrary, load_models
from solum.sim.engine import SimError
from solum.sim.native import NativeNgspice
from solum.simulate import Settling, Simulator

REPO = Path(__file__).parents[2]
Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


@pytest.fixture
def sim(engine: NativeNgspice, models: ModelLibrary) -> Simulator:
    return Simulator(engine, models)


def test_hand_drawn_fixture_is_biased_to_its_target(sim: Simulator) -> None:
    c = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    op = sim.op(c)
    assert op.voltages[sim.resolve(c, "Q1.D")] == pytest.approx(9.0, abs=0.01)
    assert 0 < op.bias["TR1"] < 1
    assert op.voltages["V+"] == pytest.approx(16.0)
    assert op.currents["Q1.id"] == pytest.approx(7.0 / (op.bias["TR1"] * 50e3), rel=0.01)
    # each target as the run met it: the DC overlay's ◎ (D-127)
    (held,) = op.held
    assert (held.ref, held.node, held.net) == ("TR1", "Q1.D", sim.resolve(c, "Q1.D"))
    assert held.volts == 9.0 and held.met and held.rotation == op.bias["TR1"]
    assert held.reached == pytest.approx(op.voltages[held.net], abs=1e-3)
    from solum.probe import op_data

    assert op_data(op)["held"] == [
        {"ref": "TR1", "node": "Q1.D", "net": held.net, "volts": 9.0,
         "reached": held.reached, "rotation": held.rotation, "met": True}
    ]  # fmt: skip


def test_a_targets_reach_brackets_where_it_holds(sim: Simulator, tmp_path: Path) -> None:
    """D-127: TR1 turned end to end moves Q1.D either side of its 9 V target, within the
    16 V supply; the endpoint says so in words."""
    c = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    reach = sim.target_reach(c, "TR1")
    assert 0 <= reach.low < 9.0 < reach.high <= 16.0 + 1e-6
    from fastapi.testclient import TestClient

    from solum.api.app import create_app
    from solum.circuit.io import circuit_to_dict
    from solum.config import load_settings

    settings = load_settings({"DATA_DIR": str(tmp_path / "d"), "CACHE_DIR": str(tmp_path / "c"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    client = TestClient(create_app(settings))
    body = {"circuit": circuit_to_dict(c), "ref": "TR1"}
    got = client.post("/api/trimmer/reach", json=body).json()
    assert got["low"] == pytest.approx(reach.low) and got["node"] == "Q1.D"
    assert got["text"].startswith("With TR1 (50k), Q1.D can go from ")
    assert got["holds"]
    far = circuit_to_dict(c.with_part("TR1", bias_target={"node": "Q1.D", "volts": 30.0}))
    assert not client.post("/api/trimmer/reach", json={**body, "circuit": far}).json()["holds"]
    refused = client.post("/api/trimmer/reach", json={**body, "ref": "Q1"})
    assert refused.status_code == 422
    assert "isn't a trimmer with a bias target" in refused.json()["message"]


def clipper(circuit: Builder) -> CircuitBuilder:
    return (
        circuit("diode clipper")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="1k")
        .part("D1", "diode", "out", "0", model="1N4148")
        .part("D2", "diode", "0", "out", model="1N4148")
        .part("OUT", "amp", "out")
    )


def test_diode_clipper_waveforms(sim: Simulator, circuit: Builder) -> None:
    c = clipper(circuit).build()
    soft = sim.tran(c, ["out"], "soft").stats["out"]
    hard = sim.tran(c, ["out"], "hard").stats["out"]
    assert soft.gain_db == pytest.approx(0.0, abs=0.5)  # 0.1 V barely turns the diodes on
    assert hard.peak_pos == pytest.approx(0.55, abs=0.08)  # silicon clips near 0.6 V
    assert hard.peak_neg == pytest.approx(-hard.peak_pos, abs=0.01)  # symmetric
    assert hard.clipping.label in ("moderate", "heavy")
    assert hard.harmonics_db[3] > -20 > hard.harmonics_db[2]  # odd harmonics only
    assert hard.polarity == "same"


def test_rc_lowpass_ac_matches_formula(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit()
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="1k")
        .part("C1", "capacitor", "out", "0", value="220n")
        .build()
    )
    ac = sim.ac(c)
    assert ac.valid
    fc = 1 / (2 * 3.141592653589793 * 1e3 * 220e-9)  # 723.4 Hz
    assert corner_3db(ac.freq, ac.responses["out"], "high") == pytest.approx(fc, rel=0.01)


def test_impedances_looking_in_from_each_end(sim: Simulator, circuit: Builder) -> None:
    """D-127: a 470k pulldown, then 10k in series to the 1M amp. The guitar sees 470k
    against 10k + 1M; the amp sees 10k (the ideal guitar is 0 Ω); at the output with
    everything in, 10k against the amp's 1M. A 10n capacitor in series instead shows it's
    measured at 1 kHz: 1/(2π·1k·10n) = 15.9k, at -90°."""
    c = (
        circuit()
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "0", value="470k")
        .part("R2", "resistor", "in", "out", value="10k")
        .part("OUT", "amp", "out")
        .build()
    )
    zin, sat = sim.impedance(c, "in", open="IN")
    assert abs(zin) == pytest.approx(1 / (1 / 470e3 + 1 / 1.01e6), rel=1e-3) and sat == []
    assert abs(sim.impedance(c, "out", open="OUT")[0]) == pytest.approx(10e3, rel=1e-3)
    assert abs(sim.impedance(c, "out")[0]) == pytest.approx(1 / (1 / 10e3 + 1 / 1e6), rel=1e-3)
    capped = (
        circuit()
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "out", value="10n")
        .part("OUT", "amp", "out")
        .build()
    )
    z = sim.impedance(capped, "out", open="OUT")[0]
    assert abs(z) == pytest.approx(1 / (2 * np.pi * 1e3 * 10e-9), rel=1e-3)
    assert np.angle(z, deg=True) == pytest.approx(-90, abs=0.5)


def test_an_impedance_says_a_stage_is_saturated(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("hard-on BJT")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="100n")
        .part("R6", "resistor", "V+", "b", value="10k")
        .part("R7", "resistor", "V+", "c", value="10k")
        .part("Q1", "bjt", "c", "b", "0", model="2N5089")
        .build()
    )
    _, sat = sim.impedance(c, "in", open="IN")
    assert [s.ref for s in sat] == ["Q1"]


def test_saturated_stage_marks_ac_invalid(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("hard-on BJT")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="100n")
        .part("R6", "resistor", "V+", "b", value="10k")  # far too much base current
        .part("R7", "resistor", "V+", "c", value="10k")
        .part("Q1", "bjt", "c", "b", "0", model="2N5089")
        .build()
    )
    ac = sim.ac(c)
    assert not ac.valid
    assert [(s.ref, s.state) for s in ac.saturated] == [("Q1", "saturated")]


def test_railed_opamp_marks_ac_invalid(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("open loop")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "p", value="100n")
        .part("R2", "resistor", "V+", "p", value="10k")  # + input 0.4 V above -
        .part("R3", "resistor", "p", "0", value="12k")
        .part("R4", "resistor", "V+", "n", value="10k")
        .part("R5", "resistor", "n", "0", value="10k")
        .part("U1", "opamp", "p", "n", "out", model="TL072")
        .build()
    )
    assert [(s.ref, s.state) for s in sim.ac(c).saturated] == [("U1", "railed")]


def test_second_run_is_a_cache_hit(
    engine: NativeNgspice, models: ModelLibrary, circuit: Builder, tmp_path: Path
) -> None:
    cached = CachedEngine(engine, SimCache(tmp_path, 10**8))
    sim = Simulator(cached, models)
    c = clipper(circuit).build()
    first = sim.ac(c)
    misses = cached.misses
    second = sim.ac(c)
    assert cached.misses == misses
    # the .ac from the cache; the .op for its saturation check is the simulator's own
    # (the same circuit object, D-280)
    assert cached.hits == 1
    assert second.responses["out"] == pytest.approx(first.responses["out"])


def test_a_failed_run_carries_the_net_names(sim: Simulator, circuit: Builder) -> None:
    """Parts dropped on the sheet and not wired yet (a 47µ cap and a resistor, both pins
    loose) make ngspice fail. The error keeps the raw log and the netlist's net → node map,
    so the error rules (tests/rules) can name the nets in plain English."""
    c = (
        circuit("half drawn")
        .part("C16", "capacitor", None, None, value="47u", kind="electrolytic")
        .part("R3", "resistor", None, None, value="10k")
        .build()
    )
    with pytest.raises(SimError) as err:
        sim.op(c)
    assert err.value.nodes["C16.2"] == "c16_2"
    assert any("singular matrix" in line for line in err.value.log)


def test_a_dc_source_drives_its_own_net_beside_the_rail(sim: Simulator, circuit: Builder) -> None:
    """D-091: V+ is the ideal 9 V; a 12 V source on V12 is live too, and a 10k/10k
    divider off it sits at half."""
    c = (
        circuit()
        .rail("V+", 9.0)
        .part("R3", "resistor", "V+", "0", value="10k")
        .part("V1", "vsource", "V12", "0", value=12.0)
        .part("R1", "resistor", "V12", "mid", value="10k")
        .part("R2", "resistor", "mid", "0", value="10k")
        .build()
    )
    op = sim.op(c)
    assert op.voltages["V+"] == pytest.approx(9.0)
    assert op.voltages["mid"] == pytest.approx(6.0)


def test_a_pickup_peaks_where_its_coil_and_cable_resonate(sim: Simulator, circuit: Builder) -> None:
    """D-096: a '57/'62 Strat middle pickup (2.55 H, 151 pF) on 3 m of cable (300 pF) into
    a 1 M amp peaks at 1 / (2π √(L C)) = 4.70 kHz (Lemme measured a Strat at about 4.5 kHz
    on 470 pF and 200k). Its 250k volume pot, on 10, takes most of the peak off, and a
    low-impedance input (10k, like a Fuzz Face's) pulls the pickup's level down."""
    pickup = {"r": "6k38", "l": "2.55", "c": "151p", "kind": "strat"}
    c = (
        circuit()
        .part("IN", "guitar", "in", source="pickup", pickup=pickup, cable=3)
        .part("OUT", "amp", "in")
        .build()
    )

    def peak(circ: object) -> tuple[float, float]:
        ac = sim.ac(circ)  # type: ignore[arg-type]
        db = 20 * np.log10(np.abs(ac.responses["in"]))
        i = int(np.argmax(db))
        return float(ac.freq[i]), float(db[i])

    f0, height = peak(c)
    assert f0 == pytest.approx(1 / (2 * np.pi * np.sqrt(2.55 * 451e-12)), rel=0.03)
    assert height > 10  # a sharp peak into a 1M load
    _, damped = peak(c.with_part("IN", volume="250k"))
    assert damped < height - 6
    fuzz = c.with_part("OUT", value="10k")  # a Fuzz Face-like input: the pickup sags
    lows = sim.ac(fuzz).responses["in"][0]
    assert abs(lows) == pytest.approx(10e3 / (10e3 + 6380), rel=0.02)


def clamp(circuit: Builder, series: str, cap: str) -> CircuitBuilder:
    """A coupling cap into one diode to ground: the cap charges with the signal, so the
    output's DC slides down cycle by cycle, as a fuzz's bias does, at a pace set by
    `series` x `cap`."""
    return (
        circuit("clamp")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "a", value=series)
        .part("C1", "capacitor", "a", "out", value=cap)
        .part("D1", "diode", "out", "0", model="1N4148")
        .part("R2", "resistor", "out", "0", value="100k")
        .part("OUT", "amp", "out")
    )


@pytest.mark.parametrize(
    ("series", "cap", "seconds", "settled"),
    [
        ("1k", "1u", 0.05, True),  # 1 ms: settled at the first wait
        ("10k", "2u2", 0.2, True),  # 22 ms
        ("10k", "47u", 0.4, False),  # 470 ms: still sliding at the cap
    ],
)
def test_settling_is_found_per_circuit(
    sim: Simulator, circuit: Builder, series: str, cap: str, seconds: float, settled: bool
) -> None:
    """D-122: the wait comes from the circuit, not a count of cycles."""
    c = clamp(circuit, series, cap).build()
    found = sim.settling(c)
    assert found.seconds == pytest.approx(seconds)
    assert found.settled is settled
    assert sim.tran(c, ["out"], "hard").settled is settled


def test_an_edited_circuits_search_starts_at_its_last_wait(
    sim: Simulator, circuit: Builder
) -> None:
    """An edit (a knob, a value) starts the search at the wait the circuit needed before,
    and checks the shorter waits on that same run: the answer is a fresh search's, with
    the earlier runs saved. A slower circuit still doubles on from there."""
    fresh = Simulator(sim.engine, sim.models)
    for series, cap, most in (("1k", "1u", 2), ("10k", "3u3", 3), ("10k", "47u", 3)):
        runs: list[str] = []
        counted = Simulator(sim.engine, sim.models)
        real = counted._run

        def run(
            netlist: Any, kind: str, *a: Any, real: Any = real, runs: list[str] = runs, **k: Any
        ) -> Any:
            runs.append(netlist.text)
            return real(netlist, kind, *a, **k)

        counted._run = run  # type: ignore[method-assign]
        before = counted.settling(clamp(circuit, "10k", "2u2").build())
        assert before.seconds == pytest.approx(0.2)
        edited = clamp(circuit, series, cap).build()  # the same circuit, a value changed
        runs.clear()
        assert counted.settling(edited) == fresh.settling(edited)
        assert len(runs) == most  # the stiffness probe, then one run (two when slower)


def test_a_settled_run_matches_a_long_one_at_every_tone(sim: Simulator, circuit: Builder) -> None:
    """The 22 ms clamp measured after its found wait reads what it does after 1 s, at a
    low tone and a high one (a count of cycles would wait 3 ms at 3 kHz)."""
    c = clamp(circuit, "10k", "2u2").build()
    for tone in (100.0, 3000.0):
        run = sim.tran(c, ["out"], "hard", tone)
        assert run.freq == tone
        got = run.stats["out"]
        long = Simulator(sim.engine, sim.models)
        long.settling = lambda _c: Settling(1.0, True)  # type: ignore[method-assign]
        ref = long.tran(c, ["out"], "hard", tone).stats["out"]
        assert got.peak_pos == pytest.approx(ref.peak_pos, rel=0.02)
        assert got.peak_neg == pytest.approx(ref.peak_neg, rel=0.02)


def test_a_long_wait_goes_by_at_coarse_steps_and_reads_the_same(
    sim: Simulator, circuit: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-275: all but the wait's last cycles run at coarse steps, and the measuring run
    starts where they ended (every node's volts, the pickup coil's amps). The 22 ms clamp
    behind a pickup, told to wait 0.4 s at 3 kHz: 1,190 coarse cycles, then 20 fine ones,
    reading what 1,210 fine ones do."""
    import solum.simulate as module

    c = (
        clamp(circuit, "10k", "2u2")
        .build()
        .with_part("IN", source="pickup", pickup={"r": "6k", "l": 2.5, "c": "500p"})
    )

    def measured() -> tuple[Any, list[str]]:
        runs: list[str] = []
        s = Simulator(sim.engine, sim.models)
        s.settling = lambda _c: Settling(0.4, True)  # type: ignore[method-assign]
        real = s._run

        def run(netlist: Any, kind: str, *a: Any, **k: Any) -> Any:
            runs.append(netlist.text)
            return real(netlist, kind, *a, **k)

        s._run = run  # type: ignore[method-assign]
        return s.tran(c, ["out"], "hard", 3000.0), runs

    two, runs = measured()
    wait, fine = runs
    assert ".ic " not in wait and " uic" not in wait
    assert "\n.tran 3.33333333333e-06 0.396666666667 0.396665 3.33333333333e-06\n" in wait
    assert "\n.ic v(out)=" in fine and "\nL_IN " in fine
    coil = next(ln for ln in fine.splitlines() if ln.startswith("L_IN "))
    assert coil.split()[-1].startswith("ic=")
    assert (
        fine.splitlines()[-2]
        == ".tran 8.33333333333e-07 0.00666666666667 0.003 8.33333333333e-07 uic"
    )
    monkeypatch.setattr(module, "WAIT_WORTH", 10**9)  # one fine run all the way
    one, runs = measured()
    assert len(runs) == 1 and " uic" not in runs[0]
    got, ref = two.stats["out"], one.stats["out"]
    assert got.amplitude == pytest.approx(ref.amplitude, rel=2e-3)
    assert got.peak_pos == pytest.approx(ref.peak_pos, rel=5e-3)
    assert got.peak_neg == pytest.approx(ref.peak_neg, rel=5e-3)
    assert got.dc == pytest.approx(ref.dc, abs=2e-3)
    for n in (2, 3):
        assert got.harmonics_db[n] == pytest.approx(ref.harmonics_db[n], abs=0.1)
    # each keeps the cycles measured and one before, not the wait
    for run in (two, one):
        assert run.time[-1] - run.time[0] == pytest.approx(11 / 3000.0, rel=1e-3)


def test_a_tone_is_one_run_whichever_nets_are_read(sim: Simulator, circuit: Builder) -> None:
    """D-277: the run records every node, so the scope at another net, a part's view and
    the Bias & headroom pane read the same run (the same netlist: one cache entry)."""
    s = Simulator(sim.engine, sim.models)
    texts: list[str] = []
    real = s._run

    def run(netlist: Any, kind: str, *a: Any, **k: Any) -> Any:
        if kind == "tran":
            texts.append(netlist.text)
        return real(netlist, kind, *a, **k)

    s._run = run  # type: ignore[method-assign]
    c = clamp(circuit, "1k", "1u").build()
    s.settling(c)
    texts.clear()
    out = s.tran(c, ["out"], "med")
    both = s.tran(c, ["a", "out"], "med")
    assert len(texts) == 2 and texts[0] == texts[1] and ".save" not in texts[0]
    assert list(out.waves) == ["in", "out"] and list(both.waves) == ["in", "a", "out"]
    assert both.stats["out"] == out.stats["out"]
    assert s.tran(c, ["out"], "hard").amplitude == 1.0 and texts[2] != texts[0]


def test_a_short_wait_is_one_run(sim: Simulator, circuit: Builder) -> None:
    """Under `WAIT_WORTH` coarse cycles a second run isn't worth it: 50 ms at 200 Hz."""
    s = Simulator(sim.engine, sim.models)
    runs: list[str] = []
    real = s._run
    s._run = lambda n, kind, *a, **k: (runs.append(kind), real(n, kind, *a, **k))[1]  # type: ignore[method-assign]
    c = clamp(circuit, "1k", "1u").build()
    assert s.settling(c).seconds == pytest.approx(0.05)
    runs.clear()
    s.tran(c, ["out"], "hard", 200.0)
    assert runs == ["tran"]


def test_a_circuits_operating_point_is_solved_once_however_often_it_is_asked(
    sim: Simulator, circuit: Builder
) -> None:
    """D-280: the DC, the AC run's saturation check and an impedance all want the same
    circuit's operating point; it is solved (and its netlist built) once. Another
    circuit object, even an equal one, is solved for itself, and only the last
    `OP_MEMO` are held."""
    import solum.simulate as module

    s = Simulator(sim.engine, sim.models)
    solved: list[Any] = []
    real = s._solve_op
    s._solve_op = lambda c: (solved.append(c), real(c))[1]  # type: ignore[method-assign]
    c = clamp(circuit, "1k", "1u").build()
    dc = s.op(c)
    s.ac(c)
    s.impedance(c, "out")
    assert solved == [c] and s.op(c).voltages == dc.voltages
    turned = c.with_part("R1", value=2200.0)
    s.ac(turned)
    assert len(solved) == 2 and solved[1] is turned
    for _ in range(module.OP_MEMO):
        s.op(clamp(circuit, "1k", "1u").build())
    assert len(solved) == 2 + module.OP_MEMO and len(s._ops) == module.OP_MEMO
    s.op(c)  # long gone from the memo: solved again
    assert len(solved) == 3 + module.OP_MEMO


def test_a_quad_op_amps_halves_each_run(sim: Simulator, circuit: Builder) -> None:
    """D-172: a TL074 with IC1A following 4.5 V, IC1B following 5.0 V and IC1C following
    IC1B; IC1B and IC1C run from IC1A's power pins, IC1D is unused and left out. Inside the
    TL07x's common-mode range on 9 V (4 V from either rail)."""
    c = (
        circuit("quad")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "p1", value="10k")
        .part("R2", "resistor", "p1", "0", value="10k")  # 4.5 V
        .part("R3", "resistor", "V+", "p2", value="4k")
        .part("R4", "resistor", "p2", "0", value="5k")  # 5.0 V
        .part("IC1A", "opamp", "p1", "o1", "o1", model="TL074", half="a")
        .part("IC1B", "opamp", "p2", "o2", "o2", model="TL074", half="b")
        .part("IC1C", "opamp", "o2", "o3", "o3", model="TL074", half="c")
        .part("IC1D", "opamp", model="TL074", half="d")
        .build()
    )
    v = sim.op(c).voltages
    assert v["o1"] == pytest.approx(4.5, abs=0.01)
    assert v["o2"] == pytest.approx(5.0, abs=0.01)
    assert v["o3"] == pytest.approx(5.0, abs=0.01)
