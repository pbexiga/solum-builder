"""`live_view` through real ngspice: the system the browser solves, where each shown net
sits in it, and sliders on circuits as drawn (D-081). Parity of the curves themselves is
in tests/parity."""

from pathlib import Path

import pytest

from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.circuit.parts import pin_positions
from solum.live import LiveError, live_view
from solum.models import load_models
from solum.probe import ac_data
from solum.rules.run import CantSimulate, Checker, rule_book
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator
from tests.jig import core_block, jig

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def test_nets_are_found_in_the_system(sim: Simulator) -> None:
    tmb = jig(core_block("fender-tmb"))
    out = tmb.probes.out
    assert out is not None
    view = live_view(sim, tmb, [out, "GND", "VR1.2"], [("C3", "value")])
    system, nets = view["system"], view["nets"]
    assert system is not None and len(system["freq"]) > 100
    assert nets["GND"] == -1
    assert system["nodes"][nets[out]]  # a real node
    # a pin name is the net it's on: the treble wiper is the output
    assert set(nets) == {out, "GND"}
    [s] = view["sliders"]
    assert (s["ref"], s["field"]) == ("C3", "value") and view["valid"]


def test_kept_steps_and_a_value_off_the_series(sim: Simulator) -> None:
    tmb = jig(core_block("fender-tmb"))
    first = live_view(sim, tmb, [], [("R1", "value")])["sliders"][0]
    shown = [step["value"] for step in first["steps"]]
    assert shown[0] == "10k" and shown[-1] == "1M"
    # each step's value as a number too, so the page never parses one (Edit mode's handles)
    assert first["steps"][0]["si"] == pytest.approx(10e3) and first["steps"][-1][
        "si"
    ] == pytest.approx(1e6)
    moved = tmb.with_part("R1", value="90k")
    again = live_view(sim, moved, [], [("R1", "value")], {"R1.value": shown})["sliders"][0]
    values = [s["value"] for s in again["steps"]]
    assert "90k" in values and [v for v in values if v != "90k"] == shown  # same range
    assert again["steps"][again["index"]]["value"] == "90k" and again["nearest"] == "82k"


def test_a_starter_with_knobs(sim: Simulator) -> None:
    ts808 = load_circuit(REPO / "library" / "starters" / "ts808.json")
    out = ts808.probes.out
    assert out is not None
    view = live_view(sim, ts808, [out], [("VR1", "rotation"), ("VR2", "rotation")])
    assert [s["ref"] for s in view["sliders"]] == ["VR1", "VR2"]
    assert view["nets"][out] >= 0


def test_no_guitar_input_still_gives_sliders(sim: Simulator) -> None:
    view = live_view(sim, core_block("fender-tmb"), ["out"], [("C1", "value")])
    assert view["system"] is None and view["nets"] == {}
    assert view["sliders"][0]["ref"] == "C1"


def test_an_unknown_part_is_explained(sim: Simulator) -> None:
    with pytest.raises(LiveError, match="no part R99"):
        live_view(sim, core_block("fender-tmb"), [], [("R99", "value")])


def test_the_live_grid_is_the_runs(sim: Simulator) -> None:
    """Exactly the run's frequencies: the live grid used to end at 100000.0000000014 Hz,
    and a log axis ending there spans a decade more, so the plot shifted while dragging."""
    muff = load_circuit(REPO / "library" / "starters" / "big-muff-pi-v3.json")
    live = live_view(sim, muff, ["out"], [])
    assert live["system"]["freq"] == ac_data(sim.ac(muff), ["out"])["freq"]  # exact on purpose


def test_nudges_raise_each_part_by_a_tenth(sim: Simulator) -> None:
    """Part influence (Phase 8b): every R, C and pot +10 %, as element values, with the
    parts carrying DC marked (the live solver holds their bias fixed)."""
    ts808 = load_circuit(REPO / "library" / "starters" / "ts808.json")
    assert ts808.probes.out is not None
    view = live_view(sim, ts808, [ts808.probes.out], [], nudge=True)
    assert view["nudge"] == pytest.approx(0.1)
    nudged = {n["ref"]: n for n in view["nudges"]}
    assert {"R4", "C3", "VR1", "VR2"} <= set(nudged)
    assert not {"Q1", "U1", "D1", "IN", "OUT"} & set(nudged)
    [(name, ohms)] = nudged["R4"]["elements"].items()
    assert ohms == pytest.approx(4700 * 1.1)
    assert next(iter(nudged["C3"]["elements"].values())) == pytest.approx(47e-9 * 1.1)
    assert len(nudged["VR1"]["elements"]) == 2  # both halves, after the taper
    # R4 sits in series with C3 (no DC through it); R14 is Q3's emitter resistor
    assert not nudged["R4"]["bias"] and nudged["R14"]["bias"] and not nudged["C3"]["bias"]
    # pots are the panel's knobs (Edit mode's handles leave them to the Knob ranges layer)
    assert nudged["VR1"]["knob"] and not nudged["C3"]["knob"] and not nudged["R4"]["knob"]
    # every nudged element is one the browser's system has
    names = {e["name"] for e in view["system"]["elements"]}
    assert name in names
    assert live_view(sim, ts808, [ts808.probes.out], [])["nudges"] == []


def test_a_circuit_that_cant_run_still_gives_sliders(sim: Simulator) -> None:
    """The user (2026-11-02): while a schematic is half drawn, it can't be run, and
    the part form's slider was locked. The slider's steps don't need a run, so they come
    back, with no live curve (D-164)."""
    data = circuit_to_dict(jig(core_block("fender-tmb")))
    # two caps in series to ground: the net between them has no DC path (parts wired to
    # nothing don't stop a run, D-165)
    for ref, pos in (("C98", [900, 900]), ("C99", [900, 1000])):
        data["parts"].append({"ref": ref, "type": "capacitor", "value": "47µ", "pos": pos})
    half_drawn = parse_circuit(data)
    pins = {ref: pin_positions(half_drawn.part(ref)) for ref in ("C98", "C99")}
    data["labels"] += [{"net": "GND", "pos": list(pins["C98"]["1"])},
                       {"net": "x", "pos": list(pins["C98"]["2"])},
                       {"net": "x", "pos": list(pins["C99"]["1"])},
                       {"net": "GND", "pos": list(pins["C99"]["2"])}]  # fmt: skip
    half_drawn = parse_circuit(data)
    checker = Checker(rule_book(REPO / "library"), sim.models)
    with pytest.raises(CantSimulate):
        checker.require_runnable(half_drawn)
    # what /api/live does then
    view = live_view(sim, half_drawn, ["out"], [("C3", "value")], simulate=False)
    assert view["system"] is None and view["nets"] == {} and not view["valid"]
    assert view["sliders"][0]["ref"] == "C3" and len(view["sliders"][0]["steps"]) > 50


def test_a_part_wired_to_nothing_leaves_the_live_curve(sim: Simulator) -> None:
    """The user (2026-11-02): on the Big Muff, a cap dropped on the sheet and not wired
    yet stopped C8's slider moving the curves. It carries no current, so the simulation
    leaves it out and the curve is the same as without it (D-165)."""
    muff = load_circuit(REPO / "library" / "starters" / "big-muff-pi-v3.json")
    data = circuit_to_dict(muff)
    data["parts"].append({"ref": "C99", "type": "capacitor", "value": "47n", "pos": [900, 900]})
    stray = parse_circuit(data)
    out = muff.probes.out
    assert out is not None
    before = live_view(sim, muff, [out], [("C8", "value")])
    after = live_view(sim, stray, [out], [("C8", "value")])
    assert after["valid"] and after["system"] is not None
    assert after["system"] == before["system"] and after["sliders"] == before["sliders"]
    # the stray cap's own slider still works
    assert live_view(sim, stray, [out], [("C99", "value")])["sliders"][0]["ref"] == "C99"
