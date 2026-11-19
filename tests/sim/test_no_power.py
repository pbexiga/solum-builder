"""No power, no numbers (P2): with every supply cut off by a plug, op-amp models still
make up a few volts of supply, so no view shows DC readings; each says why instead."""

from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.circuit.supply import no_power, render_refusal
from solum.models import load_models
from solum.probe import part_view, run_view, stages_view, sweep_view
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]
CUT = "The pedal has no power: J1 has no cable in, so its battery is cut off."


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def boost(plug: str) -> Circuit:
    """The user's clean boost (a TL061 on a battery switched by J1's ring), 1.2.0: with
    the cable out it read V+ 3.08 V, the op-amp model floating the rail up."""
    c = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "boost-battery-jack.json")
    return c.with_part("J1", plug=plug)


def dc_only(plugged: bool) -> Circuit:
    """A TL061 stage powered only through a DC jack, no battery (left by deleting it)."""
    return (
        CircuitBuilder("dc")
        .rail("V+", 9)
        .part("DC", "dcjack", "V+", "0", None, plugged=plugged)
        .part("IN", "guitar", "in")
        .part("R2", "resistor", "V+", "VREF", value="100k")
        .part("R3", "resistor", "VREF", "GND", value="100k")
        .part("R4", "resistor", "p", "VREF", value="1M")
        .part("C3", "capacitor", "in", "p", value="100n")
        .part("IC1", "opamp", "p", "o", "o", model="TL061", supply=("V+", "GND"))
        .part("OUT", "amp", "o")
        .build()
    )


def test_the_users_boost_with_the_cable_out_reads_no_voltages(sim: Simulator) -> None:
    view = run_view(sim, boost("none"), ["V+"], "med")
    assert view["no_power"] == CUT
    assert view["op"]["voltages"] == {} and view["op"]["currents"] == {}
    assert view["ac"] is None and view["tran"] is None


def test_the_users_boost_with_the_cable_in_reads_its_voltages(sim: Simulator) -> None:
    view = run_view(sim, boost("ts"), ["V+"], "med")
    assert view["no_power"] is None
    assert view["op"]["voltages"]["V+"] == pytest.approx(9.0, abs=0.01)


def test_a_part_with_no_power_has_no_readings(sim: Simulator) -> None:
    part = part_view(sim, boost("none"), "IC1", "med")
    assert part["no_power"] == CUT
    assert all(pin["dc"] is None for pin in part["pins"].values())
    assert part["detail"] == {}
    assert part_view(sim, boost("ts"), "IC1", "med")["no_power"] is None


def test_a_sweep_with_no_power_has_no_dc(sim: Simulator) -> None:
    view = sweep_view(sim, boost("none"), "R2", "value", ["100k", "47k"], ["VREF"], "med")
    assert view["no_power"] == CUT
    assert view["dc"] == {} and view["dc_all"] == {}
    assert all(p["no_power"] == CUT for p in view["parts"])


def test_the_stages_with_no_power_say_why(sim: Simulator) -> None:
    view = stages_view(sim, boost("none"))
    assert view["rows"] == [] and view["note"] == CUT


def test_an_unplugged_dc_jack_alone_is_no_power(sim: Simulator) -> None:
    """1.2.0 ran it at 9 V: the plug went unread with no battery."""
    off = dc_only(plugged=False)
    assert no_power(off) == "The pedal has no power: DC has no plug in."
    assert sim.op(off).voltages["V+"] == pytest.approx(0.0, abs=1e-6)
    view = run_view(sim, off, ["o"], "med")
    assert view["op"]["voltages"] == {} and view["ac"] is None
    assert render_refusal(off) == (
        "The pedal has no power: DC has no plug in. Plug DC in (Knobs) to render."
    )
    on = run_view(sim, dc_only(plugged=True), ["o"], "med")
    assert on["no_power"] is None and on["op"]["voltages"]["V+"] == pytest.approx(9.0)
