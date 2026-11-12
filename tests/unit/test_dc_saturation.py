"""saturation(): which active parts leave no room for a small signal at DC (D-041).

The operating points are given by hand, so each threshold is checked without ngspice.
J201: vto = -0.6708 V (library/models/jfet/J201.lib), so with Vgs = -0.3 V the edge of the
ohmic region is Vds = Vgs - Vto = 0.37 V.
"""

from collections.abc import Callable
from pathlib import Path

from solum.analysis.dc import Saturation, saturation
from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.models import load_models

MODELS = load_models([Path(__file__).parents[2] / "library" / "models"])


def states(
    c: CircuitBuilder, voltages: dict[str, float], currents: dict[str, float]
) -> list[Saturation]:
    circuit = c.build()
    return saturation(circuit, connect(circuit), {"GND": 0.0, **voltages}, currents, MODELS)


def bjt(circuit: Callable[..., CircuitBuilder]) -> CircuitBuilder:
    return circuit("bjt").rail("V+", 9.0).part("Q1", "bjt", "c", "b", "0", model="2N5089")


def jfet(circuit: Callable[..., CircuitBuilder], **fields: object) -> CircuitBuilder:
    return (
        circuit("jfet")
        .rail("V+", 9.0)
        .part("Q1", "jfet", pins={"D": "d", "G": "g", "S": "s"}, model="J201", **fields)
    )


def test_bjt_with_no_collector_current_is_cut_off(circuit: Callable[..., CircuitBuilder]) -> None:
    v = {"c": 9.0, "b": 0.2, "V+": 9.0}
    assert states(bjt(circuit), v, {"Q1.ic": 1e-9}) == [
        Saturation(
            "Q1",
            "cut off",
            "Q1 is switched off: no collector current flows, so it doesn't amplify.",
        )
    ]
    assert states(bjt(circuit), {**v, "c": 4.5, "b": 0.6}, {"Q1.ic": 1e-3}) == []


def test_jfet_pinched_off_and_ohmic(circuit: Callable[..., CircuitBuilder]) -> None:
    v = {"g": 0.0, "s": 0.3, "V+": 9.0}  # Vgs = -0.3 V
    assert states(jfet(circuit), {**v, "d": 4.5}, {"Q1.id": 1e-3}) == []  # Vds 4.2 V: fine
    assert states(jfet(circuit), {**v, "d": 4.5}, {"Q1.id": 1e-9}) == [
        Saturation(
            "Q1",
            "cut off",
            "Q1 is switched off (pinched off): no drain current flows, so it doesn't amplify.",
        )
    ]
    assert states(jfet(circuit), {**v, "d": 0.5}, {"Q1.id": 1e-3}) == [  # Vds 0.2 < 0.37
        Saturation(
            "Q1",
            "triode",
            "Q1 is in its ohmic region (Vds = 0.20 V): it acts as a resistor, not an amplifier.",
        )
    ]


def test_jfet_measured_pinch_off_replaces_the_models(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """Vds = 1.0 V is fine for the model's Vp (-0.67 V, edge 0.37 V) but ohmic for a
    measured Vp of -2.0 V (edge 1.7 V)."""
    v = {"g": 0.0, "s": 0.3, "d": 1.3, "V+": 9.0}
    assert states(jfet(circuit), v, {"Q1.id": 1e-3}) == []
    measured = jfet(circuit, measured={"idss": 5e-3, "vp": -2.0})
    assert [s.state for s in states(measured, v, {"Q1.id": 1e-3})] == ["triode"]


def test_mosfet_off_ohmic_and_amplifying(circuit: Callable[..., CircuitBuilder]) -> None:
    """D-175, the 2N7000 (VTO 2.3973 V): with the gate 4 V over the source the ohmic edge is
    Vds = 4 - 2.3973 = 1.60 V; just past the threshold it's the 0.2 V floor, not ~0 V."""
    c = circuit("mosfet").rail("V+", 9.0)
    c.part("Q1", "mosfet", pins={"D": "d", "G": "g", "S": "0"}, model="2N7000")
    assert states(c, {"g": 4.0, "d": 1.7, "V+": 9.0}, {"Q1.id": 0.1}) == []
    assert states(c, {"g": 4.0, "d": 1.5, "V+": 9.0}, {"Q1.id": 0.1}) == [
        Saturation(
            "Q1",
            "triode",
            "Q1 is fully on (ohmic, Vds = 1.50 V): it acts as a resistor, not an amplifier.",
        )
    ]
    near = {"g": 2.42, "V+": 9.0}  # the parity stage's first try: 3.9 mA, the drain at 48 mV
    assert [s.state for s in states(c, {**near, "d": 0.048}, {"Q1.id": 3.9e-3})] == ["triode"]
    assert states(c, {**near, "d": 0.25}, {"Q1.id": 3.9e-3}) == []
    assert states(c, {"g": 0.0, "d": 9.0, "V+": 9.0}, {"Q1.id": 1e-12}) == [
        Saturation(
            "Q1",
            "cut off",
            "Q1 is switched off: its gate is below its threshold, so no drain current flows "
            "and it doesn't amplify.",
        )
    ]


def test_no_terminal_current_means_no_verdict(circuit: Callable[..., CircuitBuilder]) -> None:
    """Without the device's current (not saved by the run) nothing is claimed."""
    assert states(jfet(circuit), {"g": 0.0, "s": 0.3, "d": 0.31, "V+": 9.0}, {}) == []


def test_a_bjt_is_saturated_only_with_its_base_collector_junction_forward(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """Under 0.3 V across it, a transistor is saturated only when its collector has come
    past its base (Vce < Vbe), and always under 0.1 V. Germanium at low current runs at
    Vbe 0.17 V: the Tone Bender MkII's Q2 sits at Vce 0.27 V, collector still 0.1 V short
    of the base, amplifying."""
    on = {"Q1.ic": 1e-4}
    germanium = {"c": 0.27, "b": 0.17, "V+": 9.0}
    assert states(bjt(circuit), germanium, on) == []
    assert [s.state for s in states(bjt(circuit), {**germanium, "c": 0.12}, on)] == ["saturated"]
    starved = {"c": 0.025, "b": 0.006, "V+": 9.0}  # under 0.1 V: bottomed out regardless
    assert [s.state for s in states(bjt(circuit), starved, on)] == ["saturated"]
    silicon = {"c": 0.25, "b": 0.65, "V+": 9.0}  # silicon's Vbe is always above 0.3 V
    assert [s.state for s in states(bjt(circuit), silicon, on)] == ["saturated"]


def test_a_part_off_by_design_isnt_cut_off(circuit: Callable[..., CircuitBuilder]) -> None:
    """D-238: a rectifier or switch that's off at rest (the Dyna Comp's Q3, Q4) is marked
    `off_by_design`, so off is no fault; fully on (saturated) still is."""
    c = circuit("bjt").rail("V+", 9.0)
    c.part("Q1", "bjt", "c", "b", "0", model="2N5089", off_by_design=True)
    assert states(c, {"c": 9.0, "b": 0.2, "V+": 9.0}, {"Q1.ic": 1e-9}) == []
    assert [s.state for s in states(c, {"c": 0.05, "b": 0.7, "V+": 9.0}, {"Q1.ic": 1e-3})] == [
        "saturated"
    ]
    j = jfet(circuit, off_by_design=True)
    assert states(j, {"g": 0.0, "s": 0.3, "d": 4.5, "V+": 9.0}, {"Q1.id": 1e-9}) == []
    m = circuit("mosfet").rail("V+", 9.0)
    m.part("Q1", "mosfet", pins={"D": "d", "G": "g", "S": "0"}, model="2N7000", off_by_design=True)
    assert states(m, {"g": 0.0, "d": 9.0, "V+": 9.0}, {"Q1.id": 1e-12}) == []
