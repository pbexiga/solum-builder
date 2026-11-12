"""Node and part views through real ngspice, on small circuits with hand-checkable numbers."""

import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from solum.cache import CachedEngine, SimCache
from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect, spare_poles
from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.models import ModelLibrary, load_models
from solum.probe import (
    SCOPE_CYCLES,
    SweepError,
    impedance_view,
    part_view,
    run_view,
    sweep_view,
)
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]
Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


@pytest.fixture
def sim(engine: NativeNgspice, models: ModelLibrary) -> Simulator:
    return Simulator(engine, models)


def clipper(circuit: Builder) -> CircuitBuilder:
    return (
        circuit("diode clipper")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="1k")
        .part("D1", "diode", "out", "0", model="1N4148")
        .part("D2", "diode", "0", "out", model="1N4148")
        .part("OUT", "amp", "out")
    )


def test_run_view_probes_node_and_output(sim: Simulator, circuit: Builder) -> None:
    view = run_view(sim, clipper(circuit).build(), ["R1.1"], "hard")
    assert view["nodes"] == ["in", "out"]  # the pin resolves to its net; output added
    assert view["op"]["voltages"]["out"] == pytest.approx(0.0, abs=1e-6)
    assert set(view["ac"]["nodes"]) == {"in", "out"} and view["ac"]["valid"]
    tran = view["tran"]
    assert tran["level"] == "hard" and tran["input"] == "in"
    # SCOPE_CYCLES of 200 Hz, on an even grid
    assert tran["time_ms"][-1] == pytest.approx(SCOPE_CYCLES * 5.0, rel=0.01)
    out = tran["nodes"]["out"]
    assert len(out["wave"]) == len(out["overlay"]) == len(tran["time_ms"])
    assert max(out["wave"]) == pytest.approx(0.55, abs=0.08)  # clipped near 0.6 V
    # the overlay is the input scaled by the node's gain: same fundamental, unclipped shape
    gain = 10 ** (out["stats"]["gain_db"] / 20)
    assert max(out["overlay"]) == pytest.approx(gain * 1.0, rel=0.02)
    # the Probe pane's Impedance row (D-127): looking in, everything connected, at 1 kHz;
    # the ideal guitar holds "in" (0 Ω), "out" sees 1k against the amp and the diodes
    z = view["impedance"]
    assert z["in"]["ohms"] == pytest.approx(0, abs=1e-3)
    assert z["out"]["ohms"] == pytest.approx(1e3, rel=0.01) and z["out"]["freq"] == 1000
    assert z["out"]["text"].endswith("\u03a9") and z["out"]["saturated"] is None


def test_the_impedance_overlay(sim: Simulator, circuit: Builder) -> None:
    """D-127: the guitar sees 1k then the amp (1M) beside the diodes, which at 0 V are
    near open; the amp sees the 1k (the ideal guitar is 0 Ω). D-241: a buffered guitar
    loses nothing and has no resonance; the 1k into the amp's 1M loses 0.009 dB."""
    view = impedance_view(sim, clipper(circuit).build())
    assert view["freq"] == 1000
    zin, zout = view["zin"], view["zout"]
    assert (zin["ref"], zin["net"]) == ("IN", "in")
    assert 0.8e6 < zin["ohms"] < 1.01e6
    assert zin["source"] == "0 \u03a9" and zin["level_db"] == 0 and zin["resonance"] is None
    assert zin["level_text"] == "0.0 dB" and zin["amp"] == "1 M\u03a9"
    assert (zout["ref"], zout["net"]) == ("OUT", "out")
    assert zout["ohms"] == pytest.approx(1e3, rel=0.01)
    assert zout["level_db"] == pytest.approx(20 * math.log10(1e6 / 1.001e6), abs=0.005)
    assert zout["load"] == "1 M\u03a9" and zout["follows"] == []
    no_amp = circuit().part("IN", "guitar", "in").part("R1", "resistor", "in", "0", value="1k")
    assert impedance_view(sim, no_amp.build())["zout"] is None


def test_the_overlay_says_what_loading_a_pickup_costs(sim: Simulator, circuit: Builder) -> None:
    """D-241: a pickup (10k, 2.5 H, 150 pF) into a 10k input. At 1 kHz the coil is
    10k + j·15.7k (its 150 pF, 1.06 MΩ, across it), so the 10k input keeps
    |10k / (Zs + 10k)| of the level; straight into the amp's 1 MΩ it peaks near
    1/(2π√(LC)) = 8.2 kHz, and into the 10k it doesn't peak at all. The output's Volume
    pot, behind its cap, is what Zout follows."""
    pickup = {"r": "10k", "l": "2.5", "c": "150p"}
    c = (
        circuit("loaded pickup")
        .part("IN", "guitar", "in", source="pickup", pickup=pickup)
        .part("R1", "resistor", "in", "0", value="10k")
        .part("C1", "capacitor", "in", "top", value="1µ")
        .part("VR1", "pot", "0", "out", "top", value="100k", rotation=0.5, label="Level")
        .part("OUT", "amp", "out")
        .build()
    )
    view = impedance_view(sim, c)
    w = 2 * math.pi * 1e3
    coil = 10e3 + 1j * w * 2.5
    zs = 1 / (1 / coil + 1j * w * 150e-12)
    zin = view["zin"]
    load = 1 / (1 / 10e3 + 1 / (1 / (1j * w * 1e-6) + 50e3 + 1 / (1 / 50e3 + 1 / 1e6)))
    assert zin["ohms"] == pytest.approx(abs(load), rel=0.01)
    assert zin["level_db"] == pytest.approx(20 * math.log10(abs(load / (zs + load))), abs=0.05)
    assert zin["level_text"].startswith("\u2212") and zin["source"].endswith("k\u03a9")
    alone, loaded = zin["resonance"]["alone"], zin["resonance"]["loaded"]
    assert alone["hz"] == pytest.approx(1 / (2 * math.pi * math.sqrt(2.5 * 150e-12)), rel=0.05)
    assert alone["db"] > 6 and alone["text"].startswith("8.")
    assert loaded["hz"] is None and loaded["text"].startswith("no peak, 3 dB down at")
    assert view["zout"]["follows"] == ["VR1 (Level)"]


def test_rangemaster_input_loading_follows_the_pickup(sim: Simulator) -> None:
    """The user, 2026-11-10: switching the Rangemaster's guitar from buffered to a single
    coil to a P-90 didn't change the overlay. The pedal's own Zin doesn't move (the guitar
    is left out of it), but what the loading does to the level does, and the guitar's
    source. With a pickup, the 5 nF input cap and the coil resonate near 1.2 kHz: at 1 kHz
    the level rises a little instead of falling."""
    from solum.circuit.schema import Pickup
    from solum.guides import pickup_guide

    base = load_circuit(REPO / "library" / "starters" / "dallas-rangemaster.json")
    guide = {p.kind: p for p in pickup_guide(REPO / "library").pickups}
    views = {"buffered": impedance_view(sim, base.with_part("IN", source="ideal"))}
    for kind in ("strat", "p90"):
        p = guide[kind]
        pickup = Pickup(r=p.r, l=p.l, c=p.c, kind=kind)
        guitar = base.with_part("IN", source="pickup", pickup=pickup, volume=p.volume)
        views[kind] = impedance_view(sim, guitar)
    zins = {k: v["zin"] for k, v in views.items()}
    assert len({round(z["ohms"]) for z in zins.values()}) == 1  # the pedal's Zin
    assert zins["buffered"]["level_db"] == 0 and zins["buffered"]["resonance"] is None
    assert len({z["source"] for z in zins.values()}) == 3  # 0 Ω, 17 kΩ, 45.4 kΩ
    assert zins["strat"]["level_db"] > 0 and zins["p90"]["level_db"] > 0  # the resonance
    strat, p90 = zins["strat"]["resonance"], zins["p90"]["resonance"]
    # loaded by the input cap the peak moves down to about 1.2 kHz and 790 Hz (the P-90's
    # bigger coil): the line the overlay draws under Zin
    assert strat["loaded"]["hz"] == pytest.approx(1230, rel=0.05)
    assert p90["loaded"]["hz"] == pytest.approx(790, rel=0.05)
    assert strat["alone"]["hz"] == pytest.approx(7180, rel=0.05)


def test_run_view_inverted_overlay(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("inverter")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "a", value="10u")
        .part("R1", "resistor", "a", "n", value="10k")
        .part("R2", "resistor", "n", "o", value="20k")
        .part("R3", "resistor", "V+", "p", value="10k")
        .part("R4", "resistor", "p", "0", value="10k")
        .part("U1", "opamp", "p", "n", "o", model="TL072")
        .build()
    )
    node = run_view(sim, c, ["o"], "soft")["tran"]["nodes"]["o"]
    assert node["stats"]["polarity"] == "inverted"
    assert node["stats"]["gain_db"] == pytest.approx(20 * math.log10(2), abs=0.1)
    wave, overlay = np.array(node["wave"]), np.array(node["overlay"])
    assert np.max(np.abs(wave - overlay)) < 0.01  # a clean inverter matches its overlay


def test_run_view_without_guitar_has_dc_only(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("divider")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "m", value="10k")
        .part("R2", "resistor", "m", "0", value="10k")
        .build()
    )
    view = run_view(sim, c, ["m"], "med")
    assert view["op"]["voltages"]["m"] == pytest.approx(4.5)
    assert view["ac"] is None and view["tran"] is None


def test_resistor_view(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("divider")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "m", value="10k", rating_w=0.25)
        .part("R2", "resistor", "m", "0", value="10k")
        .build()
    )
    view = part_view(sim, c, "R1", "med")
    assert view["pins"] == {"1": {"net": "V+", "dc": 9.0}, "2": {"net": "m", "dc": 4.5}}
    d = view["detail"]
    assert d["across"] == pytest.approx(4.5)
    assert d["current"] == pytest.approx(4.5e-4)
    assert d["power"] == pytest.approx(2.025e-3)
    assert d["load"] == pytest.approx(2.025e-3 / 0.25)
    assert d["display"] == {"current": "450 µA", "power": "2.02 mW"}  # 2.025e-3 is just below


def test_capacitor_view_shows_both_sides(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("high-pass")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="100n", rating_v=16, kind="electrolytic")
        .part("R1", "resistor", "V+", "b", value="10k")
        .part("R2", "resistor", "b", "0", value="10k")
        .build()
    )
    d = part_view(sim, c, "C1", "med")["detail"]
    assert d["across"] == pytest.approx(-4.5)
    assert d["load"] == pytest.approx(4.5 / 16)
    assert d["polarised"]
    assert set(d["curves"]["nodes"]) == {"in", "b"}
    b = np.array(d["curves"]["nodes"]["b"])
    freq = np.array(d["curves"]["freq"])
    fc = 1 / (2 * math.pi * 5e3 * 100e-9)  # 318 Hz: C1 into 10k || 10k
    assert np.interp(math.log10(fc), np.log10(freq), b) == pytest.approx(-3.01, abs=0.1)


def test_pot_view_sweeps_the_wiper(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("volume")
        .part("IN", "guitar", "in")
        .part("VR1", "pot", "0", "out", "in", value="10k", taper="B", rotation=0.7)
        .part("OUT", "amp", "out")
        .build()
    )
    d = part_view(sim, c, "VR1", "med")["detail"]
    assert d["rotation"] == 0.7
    assert d["halves"] == pytest.approx([7000, 3000])
    assert d["display"]["halves"] == ["7 kΩ", "3 kΩ"]
    assert d["solved"] is False
    assert "sweep" not in d  # the Frequency panel shows the wiper and the output instead


def test_solved_trimmer_is_marked_solved(sim: Simulator) -> None:
    c = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    d = part_view(sim, c, "TR1", "med")["detail"]
    assert d["solved"] is True
    assert 0 < d["rotation"] < 1


def test_diode_view_iv_curve_and_swing(sim: Simulator, circuit: Builder) -> None:
    d = part_view(sim, clipper(circuit).build(), "D1", "hard")["detail"]
    v, i = np.array(d["curve"]["v"]), np.array(d["curve"]["i"])
    assert v[0] == pytest.approx(-1.0) and v[-1] == pytest.approx(1.0)
    assert np.all(np.diff(i) >= 0)  # current rises with voltage
    # onsemi 1N4148 card: about 0.61 V at 1 mA (D-029)
    assert float(np.interp(1e-3, i, v)) == pytest.approx(0.61, abs=0.03)
    assert d["dc"] == {"v": pytest.approx(0.0, abs=1e-6), "i": pytest.approx(0.0, abs=1e-9)}
    swing = np.array(d["swing"]["v"])
    assert swing.max() == pytest.approx(0.55, abs=0.08)
    assert swing.min() == pytest.approx(-0.55, abs=0.08)  # D2 clips the other half


def common_emitter(circuit: Builder) -> CircuitBuilder:
    return (
        circuit("common emitter")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="1u")
        .part("R1", "resistor", "V+", "b", value="1M")
        .part("R2", "resistor", "b", "0", value="100k")
        .part("R5", "resistor", "V+", "c", value="10k")
        .part("R6", "resistor", "e", "0", value="1k")
        .part("Q1", "bjt", "c", "b", "e", model="2N5089")
        .probe(out="c")
    )


def test_bjt_view_operating_point_on_its_curve(sim: Simulator, circuit: Builder) -> None:
    d = part_view(sim, common_emitter(circuit).build(), "Q1", "soft")["detail"]
    assert d["polarity"] == "n"
    assert d["beta"] == pytest.approx(d["ic"] / d["ib"])
    v, i = np.array(d["curve"]["v"]), np.array(d["curve"]["i"])
    assert v[0] < d["vbe"] < v[-1]
    # the curve is taken at the operating Vce, so it passes through the operating point
    assert float(np.interp(d["vbe"], v, i)) == pytest.approx(d["ic"], rel=0.02)
    stage = d["stage"]
    assert stage["terminal"] == "C" and not stage["follower"]
    vc = 9.0 - d["ic"] * 10e3  # hand check: collector sits R5 * Ic below V+
    assert stage["headroom"]["up"] == pytest.approx(9.0 - vc, rel=0.01)
    assert stage["headroom"]["down"] == pytest.approx(d["vce"] - 0.3, rel=0.01)
    assert 0 < stage["swing"]["up"] < stage["headroom"]["up"]


def test_follower_is_judged_at_its_emitter(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("emitter follower")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="1u")
        .part("R1", "resistor", "V+", "b", value="1M")
        .part("R2", "resistor", "b", "0", value="1M")
        .part("R6", "resistor", "e", "0", value="10k")
        .part("Q1", "bjt", "V+", "b", "e", model="2N5089")
        .build()
    )
    d = part_view(sim, c, "Q1", "soft")["detail"]
    stage = d["stage"]
    assert stage["terminal"] == "E" and stage["follower"]
    ve = 9.0 - d["vce"]
    assert stage["headroom"]["down"] == pytest.approx(ve, rel=0.01)  # down to ground
    assert stage["headroom"]["up"] == pytest.approx(d["vce"] - 0.3, rel=0.01)


def test_jfet_view_honours_measured_values(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("jfet cs")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "g", value="100n")
        .part("R7", "resistor", "g", "0", value="1M")
        .part("R8", "resistor", "V+", "d", value="10k")
        .part("R9", "resistor", "s", "0", value="1k")
        .part("Q1", "jfet", "d", "g", "s", model="J201", measured={"idss": 6e-4, "vp": -0.8})
        .build()
    )
    d = part_view(sim, c, "Q1", "soft")["detail"]
    assert d["vp"] == -0.8
    v, i = np.array(d["curve"]["v"]), np.array(d["curve"]["i"])
    assert v[0] == pytest.approx(-0.88) and v[-1] == pytest.approx(0.0)
    assert float(i[-1]) == pytest.approx(6e-4, rel=0.1)  # Idss at Vgs = 0 (plus lambda)
    assert float(np.interp(d["vgs"], v, i)) == pytest.approx(d["id"], rel=0.02)
    assert d["stage"]["terminal"] == "D"


def test_mosfet_view_operating_point_on_its_curve(sim: Simulator, circuit: Builder) -> None:
    """D-175: a 2N7000 common-source stage, the gate held at 2.6 V by a divider (the drain
    current is then a few mA: 9 V across 1 kΩ at most)."""
    c = (
        circuit("mosfet cs")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "g", value="100n")
        .part("R1", "resistor", "V+", "g", value="2.46Meg")
        .part("R2", "resistor", "g", "0", value="1M")
        .part("R3", "resistor", "V+", "d", value="1k")
        .part("Q1", "mosfet", "d", "g", "0", model="2N7000")
        .build()
    )
    d = part_view(sim, c, "Q1", "soft")["detail"]
    assert d["polarity"] == "n" and d["vto"] == pytest.approx(2.3973)
    assert d["vgs"] == pytest.approx(9 * 1 / 3.46, rel=1e-3)
    assert d["id"] == pytest.approx((9.0 - d["vds"]) / 1e3, rel=1e-3)
    v, i = np.array(d["curve"]["v"]), np.array(d["curve"]["i"])
    assert v[0] == 0.0 and v[-1] == pytest.approx(d["vgs"] + 2.0)  # past the gate, above VTO
    assert float(np.interp(d["vgs"], v, i)) == pytest.approx(d["id"], rel=0.02)
    assert d["stage"]["terminal"] == "D"


def test_opamp_view(sim: Simulator) -> None:
    c = load_circuit(REPO / "library" / "starters" / "ts808.json")
    d = part_view(sim, c, "IC1B", "med")["detail"]
    assert d["rails"] == [0.0, 9.0]
    assert d["out"] == pytest.approx(4.5, abs=0.1)
    assert d["inputs"]["+"] == pytest.approx(d["inputs"]["-"], abs=0.01)
    assert not d["input_outside"]
    assert d["to_rails"]["up"] + d["to_rails"]["down"] == pytest.approx(9.0)
    assert 0.3 < d["swing"]["up"] < 0.8  # diodes in the feedback loop hold it near 0.4-0.6 V


def test_every_part_of_every_starter_has_a_view(sim: Simulator, tmp_path: Path) -> None:
    """Through the cache, as the app runs: a starter's parts share its runs (117 s
    without it, each part's view simulating the circuit again; Phase 10)."""
    sim = Simulator(CachedEngine(sim.engine, SimCache(tmp_path, 10**9)), sim.models)
    for path in sorted((REPO / "library" / "starters").glob("*.json")):
        c = load_circuit(path)
        spare = spare_poles(c, connect(c))  # open lugs: no voltage to show
        for p in c.parts:
            if p.ref in spare:
                continue
            view = part_view(sim, c, p.ref, "med")
            assert view["ref"] == p.ref
            assert all(pin["dc"] is not None for pin in view["pins"].values()), p.ref


def test_sweep_view_moves_an_rc_corner(sim: Simulator, circuit: Builder) -> None:
    """R1 at 1k and 10k with C1 = 100n: corners at 1/(2πRC) = 1592 Hz and 159 Hz."""
    c = (
        circuit("rc")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="1k")
        .part("C1", "capacitor", "out", "0", value="100n")
        .part("OUT", "amp", "out")
        .build()
    )
    view = sweep_view(sim, c, "R1", "value", ["1k", "10k"], ["R1.1"], "soft")
    assert view["values"] == ["1k", "10k"] and view["nodes"] == ["in", "out"]
    freq = np.log10(view["ac"]["freq"])
    for curve, rc in zip(view["ac"]["nodes"]["out"], (1e3 * 100e-9, 1e4 * 100e-9), strict=True):
        corner = 1 / (2 * math.pi * rc)
        assert np.interp(math.log10(corner), freq, curve) == pytest.approx(-3.01, abs=0.05)
    assert view["ac"]["valid"] == [True, True]
    waves = view["tran"]["nodes"]["out"]
    assert len(waves) == 2 and len(waves[0]) == len(view["tran"]["time_ms"])
    # 200 Hz through a 159 Hz corner is attenuated more than through a 1.6 kHz one
    assert max(waves[1]) < 0.7 * max(waves[0])


def test_sweep_view_dc_only_without_input(sim: Simulator, circuit: Builder) -> None:
    """Divider from 9 V: the top resistor at 10k then 20k puts mid at 4.5 V then 3.0 V."""
    c = (
        circuit("divider")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "mid", value="10k")
        .part("R2", "resistor", "mid", "0", value="10k")
        .build()
    )
    view = sweep_view(sim, c, "R1", "value", ["10k", "20k"], ["mid"], "med")
    assert view["dc"]["mid"] == pytest.approx([4.5, 3.0], abs=1e-6)
    assert view["ac"] is None and view["tran"] is None


def test_sweep_view_tries_models(sim: Simulator, circuit: Builder) -> None:
    c = clipper(circuit).build()
    view = sweep_view(sim, c, "D1", "model", ["1N4148", "1N4148"], [], "hard")
    assert view["ac"]["nodes"]["out"][0] == view["ac"]["nodes"]["out"][1]


def test_sweep_view_of_a_dc_source_on_its_own_net(sim: Simulator, circuit: Builder) -> None:
    """Trying 9, 12 and 18 V on a DC source driving its own net (V16) moves a divider off
    it, beside the ideal V+ (D-091)."""
    c = (
        circuit("own net")
        .rail("V+", 9.0)
        .part("R3", "resistor", "V+", "0", value="10k")
        .part("V1", "vsource", "V16", "0", value=16.0)
        .part("R1", "resistor", "V16", "mid", value="10k")
        .part("R2", "resistor", "mid", "0", value="10k")
        .build()
    )
    view = sweep_view(sim, c, "V1", "value", ["9", "12", "18"], ["mid"], "med")
    assert view["dc"]["mid"] == pytest.approx([4.5, 6.0, 9.0], abs=1e-6)
    assert view["dc_all"]["V16"] == pytest.approx([9.0, 12.0, 18.0], abs=1e-6)
    assert view["dc_all"]["V+"] == pytest.approx([9.0, 9.0, 9.0], abs=1e-6)


def test_sweep_view_of_a_supply_rail(sim: Simulator, circuit: Builder) -> None:
    """Comparing supply voltages directly (D-068): plain numbers keep the rail's sign, so
    "9, 18" on V- is -9 and -18 V."""
    pos = (
        circuit("divider")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "mid", value="10k")
        .part("R2", "resistor", "mid", "0", value="10k")
    )
    view = sweep_view(sim, pos.build(), "V+", "rail", ["9", "12", "18"], ["mid"], "med")
    assert view["dc"]["mid"] == pytest.approx([4.5, 6.0, 9.0], abs=1e-6)
    neg = (
        circuit("negative divider")
        .rail("V-", -9.0)
        .part("R1", "resistor", "V-", "mid", value="10k")
        .part("R2", "resistor", "mid", "0", value="10k")
        .build()
    )
    view = sweep_view(sim, neg, "V-", "rail", ["9", "18"], ["mid"], "med")
    assert view["dc"]["mid"] == pytest.approx([-4.5, -9.0], abs=1e-6)
    with pytest.raises(SweepError, match="no supply rail called 'V9'"):
        sweep_view(sim, pos.build(), "V9", "rail", ["9"], ["mid"], "med")
    with pytest.raises(SweepError, match="isn't a supply"):
        sweep_view(sim, neg, "V-", "rail", ["0"], ["mid"], "med")
    with pytest.raises(SweepError) as bad:
        sweep_view(sim, neg, "V-", "rail", ["9", "nine"], ["mid"], "med")
    assert str(bad.value) == "V-: can't use 'nine'. Write a voltage like 9 or 12."


def test_more_supply_gives_the_fuzz_face_more_swing(sim: Simulator) -> None:
    """The example for the user (D-068): the Fuzz Face has no clipping diodes, so its
    transistors' swing grows with the supply. At the hard pick level the output's
    negative peak at -18 V is well beyond the one at -9 V (simulated -0.40 vs -0.80 V)."""
    c = load_circuit(REPO / "library" / "starters" / "fuzz-face.json")
    view = sweep_view(sim, c, "V-", "rail", ["9", "18"], ["out"], "hard")
    lows = [min(w) for w in view["tran"]["nodes"]["out"]]
    assert lows[1] < 1.5 * lows[0]  # at least half as much again, negative-going


def test_a_loose_part_shows_no_readings_and_the_rest_runs(sim: Simulator) -> None:
    """D-165: placing a part selects it, and the page asks for its view and a run at once.
    A part wired to nothing isn't simulated: its pins have no DC and it has no detail, its
    net has no scope or impedance, and the output still has all of them, with no error."""
    ts808 = load_circuit(REPO / "library" / "starters" / "ts808.json")
    data = circuit_to_dict(ts808)
    data["parts"].append({"ref": "C99", "type": "capacitor", "value": "47n", "pos": [2000, 2000]})
    stray = parse_circuit(data)
    view = part_view(sim, stray, "C99", "med")
    assert view["detail"] == {} and all(pin["dc"] is None for pin in view["pins"].values())
    out = ts808.probes.out
    run = run_view(sim, stray, ["C99.1"], "med")
    assert run["nodes"] == ["C99.1", out]
    assert set(run["tran"]["nodes"]) == {out} and set(run["impedance"]) == {out}
    assert out in run["ac"]["nodes"] and "C99.1" not in run["ac"]["nodes"]
