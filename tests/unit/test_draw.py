"""`solum.circuit.draw`: a circuit drawn in code, and its nets against the ones meant (D-314)."""

import pytest

from solum.circuit.connectivity import connect
from solum.circuit.draw import Drawing, DrawingError, net_differences
from solum.circuit.io import CircuitError
from solum.circuit.schema import SCHEMA_VERSION

RAILS = {"rails": {"V+": 9.0}}
# guitar → R1 → C1 to ground, the amp across C1
LOW_PASS = [{"IN.out", "R1.1"}, {"R1.2", "C1.1", "OUT.in"}, {"C1.2"}]


def low_pass() -> Drawing:
    d = Drawing()
    d.part("IN", "guitar", (0, 0))
    d.part("R1", "resistor", (100, 0), value="10k")
    d.part("C1", "capacitor", (160, 40), 90, value="22n")
    d.part("OUT", "amp", (260, 0))
    d.wire("IN.out", "R1.1")
    d.wire("R1.2", "OUT.in")
    d.label("GND", "C1.2")
    return d


def test_pins_follow_position_and_rotation() -> None:
    d = low_pass()
    assert d.pin("R1", "1") == (80, 0)
    assert d.pin("R1", "2") == (120, 0)
    # turned 90° clockwise, pin 1 is on top
    assert d.pins("C1") == {"1": (160, 20), "2": (160, 60)}
    assert d.at("C1.2") == (160, 60)
    assert d.at((5, 7)) == (5, 7)


def test_a_wire_has_one_piece_per_leg() -> None:
    d = low_pass()
    d.wire("C1.1", (160, 0))
    assert d.wires == [
        {"from": [20, 0], "to": [80, 0]},
        {"from": [120, 0], "to": [240, 0]},
        {"from": [160, 20], "to": [160, 0]},
    ]


def test_the_drawing_is_a_circuit_of_the_current_schema() -> None:
    d = low_pass()
    d.wire("C1.1", (160, 0))
    d.text((0, 100), title="Low pass", text="723 Hz")
    c = d.circuit("My low pass", power=RAILS, description="An RC low pass.")
    assert (c.schema_, c.id, c.name) == (SCHEMA_VERSION, "my-low-pass", "My low pass")
    assert c.power.rails == {"V+": 9.0}
    assert c.texts[0].title == "Low pass"
    nets = connect(c)
    # the wire from R1 to the amp passes C1's top pin's wire end: a T-junction joins them
    assert nets.net_of("C1", "1") == nets.net_of("R1", "2") == nets.net_of("OUT", "in")
    assert nets.net_of("C1", "2") == "GND"
    assert net_differences(c, LOW_PASS) == []


def test_a_missing_wire_is_reported_both_ways() -> None:
    c = low_pass().circuit("Low pass", power=RAILS)  # C1's top pin isn't wired
    assert net_differences(c, LOW_PASS) == [
        "Not drawn as one net: C1.1, OUT.in, R1.2.",
        "Drawn as one net, but not meant: C1.1.",
        "Drawn as one net, but not meant: OUT.in, R1.2.",
    ]


def test_a_pin_left_out_must_join_nothing() -> None:
    d = low_pass()
    d.wire("C1.1", (160, 0))
    c = d.circuit("Low pass", power=RAILS)
    without_c1 = [{"IN.out", "R1.1"}, {"R1.2", "OUT.in"}]
    assert net_differences(c, without_c1) == [
        "C1.1 is left out of the intended netlist, but the drawing joins it to OUT.in, R1.2."
    ]
    # an open pin may be left out or listed alone
    assert net_differences(c, LOW_PASS[:2]) == []


def test_a_pin_the_drawing_lacks_is_reported() -> None:
    d = low_pass()
    d.wire("C1.1", (160, 0))
    c = d.circuit("Low pass", power=RAILS)
    assert net_differences(c, [*LOW_PASS, {"R9.1"}])[0] == (
        "R9.1 is in the intended netlist, but the drawing has no such pin."
    )


def test_labels_take_a_rotation_and_a_stub_ends_in_one() -> None:
    d = low_pass()
    d.label("V+", (0, -40), rot=90)
    d.stub("C1.1", "tone", dy=-20)
    assert d.labels[1:] == [
        {"net": "V+", "pos": [0, -40], "rot": 90},
        {"net": "tone", "pos": [160, 0]},
    ]
    assert d.wires[-1] == {"from": [160, 20], "to": [160, 0]}


@pytest.mark.parametrize(
    ("step", "says"),
    [
        (lambda d: d.part("R1", "resistor", (0, 0), value="1k"), "R1 is placed twice"),
        (lambda d: d.part("X1", "resistor", (0, 0), value="1k"), "A resistor's ref is R"),
        (lambda d: d.part("R2", "resistor", (0, 0), value="10F"), "R2 (resistor) can't be placed"),
        (lambda d: d.pin("R7", "1"), "There's no part R7 yet"),
        (lambda d: d.pin("R1", "3"), "R1 has no pin '3'. Its pins are 1, 2."),
        (lambda d: d.wire("R1.1", "C1.2"), "is diagonal. Add a corner: (160, 0) or (80, 60)."),
        (lambda d: d.wire("R1.1", (80, 0)), "to itself"),
    ],
)
def test_a_step_that_cant_be_done_says_why(step, says: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(DrawingError) as err:
        step(low_pass())
    assert says in str(err.value)


def test_a_file_problem_is_the_loaders_plain_error() -> None:
    d = low_pass()
    d.part("IC1A", "opamp", (400, 0), model="TL072", half="a")  # half a chip
    with pytest.raises(CircuitError, match="IC1B isn't in the file"):
        d.circuit("Low pass", power=RAILS)
