from collections import defaultdict
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import (
    ConnectivityError,
    connect,
    loose_parts,
    on_segment,
    spare_poles,
)
from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.circuit.parts import pin_positions, rotate
from solum.circuit.schema import Circuit, Resistor, Switch

FIXTURE = Path(__file__).parents[1] / "fixtures" / "circuits" / "jfet-drive.json"


def test_hand_drawn_fixture_nets() -> None:
    nets = connect(load_circuit(FIXTURE))
    assert nets.members["GND"] == (("R1", "2"), ("R2", "2"), ("VR1", "3"))
    assert nets.members["OUT"] == (("OUT", "in"), ("VR1", "2"))
    # unlabelled nets take a transistor's or op-amp's pin name when they have one (D-082)
    assert nets.members["Q1.G"] == (("C1", "2"), ("Q1", "G"), ("R1", "1"))  # T-junction
    assert nets.members["Q1.D"] == (("C2", "1"), ("Q1", "D"), ("TR1", "2"))
    assert nets.members["V+"] == (("TR1", "1"),)
    assert nets.members["TR1.3"] == (("TR1", "3"),)  # unconnected pin: a net of its own
    assert nets.resolve("Q1.D") == "Q1.D"
    assert nets.resolve("C2.1") == "Q1.D"  # any pin on it still finds it
    assert nets.resolve("IN.out") == "C1.1"  # passive parts only: the first pin, as before
    assert nets.resolve("OUT") == "OUT"


def test_a_change_of_value_reuses_the_nets_and_a_move_does_not() -> None:
    """Phase 10 (D-273): the nets depend on the drawing alone, so a search's thousands of
    value swaps and knob turns work them out once."""
    c = load_circuit(FIXTURE)
    nets = connect(c)
    assert connect(c.with_part("R1", value=4700.0)) is nets
    assert connect(c.with_part("TR1", rotation=0.2)) is nets
    x, y = c.part("R1").pos
    moved = connect(c.with_part("R1", pos=(x + 500, y + 500)))
    assert moved is not nets
    assert moved.members["Q1.G"] == (("C1", "2"), ("Q1", "G"))  # R1 has left the net
    assert connect(c) is nets


def test_loose_parts_are_worked_out_once_per_drawing() -> None:
    """Phase 10 (D-280): which parts are loose depends on the wiring and each part's
    kind, so a value swap reuses the answer; the set handed back is the caller's own."""
    from solum.circuit.connectivity import _loose

    c = load_circuit(FIXTURE)
    x, y = c.part("R1").pos
    adrift = c.with_part("R1", pos=(x + 500, y + 500))  # R1 moved off its wires
    first = loose_parts(adrift, connect(adrift))
    assert first == {"R1"}
    before = _loose.cache_info().hits
    first.add("spoiled")
    again = loose_parts(adrift.with_part("R2", value=4700.0), connect(adrift))
    assert again == {"R1"} and _loose.cache_info().hits == before + 1
    assert loose_parts(c, connect(c)) == set()  # wired in: another drawing, another answer


def test_resolve_unknown_name() -> None:
    nets = connect(load_circuit(FIXTURE))
    with pytest.raises(ConnectivityError, match=r"no net or pin called 'Q9\.D'"):
        nets.resolve("Q9.D")


def _two_resistors(wires: list[dict[str, list[int]]]) -> dict[str, object]:
    return {
        "schema": 1,
        "id": "t",
        "name": "t",
        "parts": [
            {"ref": "R1", "type": "resistor", "value": "1k", "pos": [0, 0]},  # pins (-20,0) (20,0)
            {"ref": "R2", "type": "resistor", "value": "1k", "pos": [100, 0], "rot": 90},
        ],  # R2 pins (100,-20) (100,20)
        "wires": wires,
    }


def test_crossing_wires_do_not_connect() -> None:
    c = parse_circuit(_two_resistors([
        {"from": [20, 0], "to": [20, 50]},
        {"from": [0, 30], "to": [100, 30]},
        {"from": [100, 20], "to": [100, 30]},
    ]))  # fmt: skip
    nets = connect(c)
    assert nets.net_of("R1", "2") != nets.net_of("R2", "2")


def test_wire_end_on_another_wire_is_a_junction() -> None:
    c = parse_circuit(_two_resistors([
        {"from": [20, 0], "to": [20, 50]},
        {"from": [20, 30], "to": [100, 30]},
        {"from": [100, 20], "to": [100, 30]},
    ]))  # fmt: skip
    nets = connect(c)
    assert nets.net_of("R1", "2") == nets.net_of("R2", "2")


def test_two_names_on_one_net_is_an_error() -> None:
    data = _two_resistors([{"from": [20, 0], "to": [100, -20]}])
    data["labels"] = [{"net": "A", "pos": [20, 0]}, {"net": "B", "pos": [100, -20]}]
    with pytest.raises(ConnectivityError, match="Net labels A and B are wired together"):
        connect(parse_circuit(data))


def test_same_label_joins_distant_points(circuit: Callable[..., CircuitBuilder]) -> None:
    c = (
        circuit()
        .part("R1", "resistor", "x", "0", value="1k")
        .part("R2", "resistor", "x", "V+", value="1k")
        .rail("V+", 9.0)
        .build()
    )
    nets = connect(c)
    assert nets.members["x"] == (("R1", "1"), ("R2", "1"))
    assert nets.members["GND"] == (("R1", "2"),)


def test_rail_without_pins_still_resolves() -> None:
    data = _two_resistors([])
    data["labels"] = [{"net": "VREF", "pos": [500, 500]}]
    assert connect(parse_circuit(data)).members["VREF"] == ()


def test_empty_circuit() -> None:
    nets = connect(parse_circuit({"schema": 1, "id": "e", "name": "e", "parts": []}))
    assert nets.members == {}


@pytest.mark.parametrize(
    ("rot", "expected"), [(0, (20, 0)), (90, (0, 20)), (180, (-20, 0)), (270, (0, -20))]
)
def test_rotation_is_clockwise_on_screen(rot: int, expected: tuple[int, int]) -> None:
    assert rotate((20, 0), rot) == expected


def test_pin_positions_follow_pos_and_rot() -> None:
    r = Resistor(ref="R1", type="resistor", value="1k", pos=(100, 40), rot=90)
    assert pin_positions(r) == {"1": (100, 20), "2": (100, 60)}


def test_switch_pins() -> None:
    """D-143 (v15, as KiCad): a pole's common on the left, its throws on the right,
    centred on it."""
    sw = Switch(ref="SW1B", type="switch", kind="rotary-2p3t", pole="b", pos=(0, 60))
    assert pin_positions(sw) == {"BC": (-20, 60), "B1": (20, 40), "B2": (20, 60),
                                 "B3": (20, 80)}  # fmt: skip
    toggle = Switch(ref="SW1", type="switch", kind="spdt-on-off-on")
    assert pin_positions(toggle) == {"2": (-20, 0), "1": (20, -20), "3": (20, 20)}


@pytest.mark.parametrize(
    ("p", "inside"),
    [((5, 0), True), ((0, 0), True), ((10, 0), True), ((11, 0), False), ((5, 1), False)],
)
def test_on_segment(p: tuple[int, int], inside: bool) -> None:
    assert on_segment(p, (0, 0), (10, 0)) is inside


def _wired_instead_of_labelled(c: Circuit) -> Circuit:
    """The builder labels every net; join each net's pins with wires instead (ground
    keeps its labels), so the nets are unlabelled."""
    data = circuit_to_dict(c)
    points: dict[str, list[list[int]]] = defaultdict(list)
    for label in data["labels"]:
        points[label["net"]].append(label["pos"])
    data["labels"] = [lb for lb in data["labels"] if lb["net"] == "GND"]
    data["wires"] = [
        {"from": a, "to": b}
        for net, pos in points.items()
        if net != "GND"
        for a, b in pairwise(pos)
    ]
    return parse_circuit(data)


def test_active_pins_name_unlabelled_nets_first_in_order(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """Label first; else the first transistor or op-amp pin; else the first pin."""
    c = (
        circuit("names")
        .part("R1", "resistor", "a", "b", value="1k")
        .part("C1", "capacitor", "b", "x", value="1n")  # sorts first: the old rule's pick
        .part("Q2", "bjt", pins={"C": "b", "B": "x", "E": "0"}, model="2N5089")
        .part("Q1", "bjt", pins={"C": "b", "B": "y", "E": "0"}, model="2N5089")
        .part("U1", "opamp", pins={"+": "x", "-": "y", "out": "z"}, model="TL072")
        .build()
    )
    nets = connect(_wired_instead_of_labelled(c))
    assert nets.net_of("C1", "1") == "Q1.C"  # Q1 before Q2; both before C1 and R1
    assert nets.net_of("C1", "2") == "Q2.B"  # a BJT before an op-amp: alphabetical (Q < U)
    assert nets.net_of("R1", "1") == "R1.1"


def _loose(b: CircuitBuilder) -> set[str]:
    c = b.build()
    return loose_parts(c, connect(c))


def test_loose_parts_carry_no_current() -> None:
    """The user (2026-11-02): a cap dropped on the Big Muff stopped every live curve. A
    part no current can reach is left out of the simulation instead (D-165)."""

    def base() -> CircuitBuilder:
        return (
            CircuitBuilder()
            .part("IN", "guitar", "in")
            .part("R1", "resistor", "in", "0", value="1M")
            .part("C1", "capacitor", "in", "out", value="100n")
            .part("R2", "resistor", "out", "0", value="100k")
        )

    assert _loose(base()) == set()
    assert _loose(base().part("C9", "capacitor", None, None, value="1n")) == {"C9"}
    # wired at one end, and a chain hanging off by one pin
    assert _loose(base().part("C9", "capacitor", "out", None, value="1n")) == {"C9"}
    hanging = base().part("C9", "capacitor", "out", "x", value="1n")
    assert _loose(hanging.part("R9", "resistor", "x", None, value="1k")) == {"C9", "R9"}
    # a group joined to itself only, transistor included
    island = base().part("R9", "resistor", "x", "y", value="1k")
    island = island.part("Q9", "bjt", "x", "y", "z", model="2N3904")
    assert _loose(island) == {"R9", "Q9"}
    # ...until one pin reaches ground; a transistor with an open pin stays (it isn't passive)
    assert _loose(island.part("R8", "resistor", "z", "0", value="1k")) == set()
    # a pot as a variable resistor, one end open, still carries current
    assert _loose(base().part("VR1", "pot", None, "out", "0", value="100k")) == set()


def test_a_switch_pole_with_nothing_wired_is_spare() -> None:
    """A 4PDT slide used as a 3PDT (the Klon's): pole B wired, pole A not. A is loose (not
    simulated) and spare (no rule names it); a lone unwired switch isn't spare."""
    base = (
        CircuitBuilder()
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "out", "0", value="100k")
        .part("SW1B", "switch", "in", "out", None, kind="dpdt", pole="b")
        .part("SW1A", "switch", None, None, None, kind="dpdt", pole="a")
    )
    c = base.build()
    nets = connect(c)
    assert spare_poles(c, nets) == {"SW1A"} and "SW1A" in loose_parts(c, nets)
    lone = CircuitBuilder().part("IN", "guitar", "in").part("SW2", "switch", None, None, None)
    c = lone.build()
    assert spare_poles(c, connect(c)) == set()
    # one lug wired: not spare (part-not-simulated says what to do)
    half = (
        CircuitBuilder()
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "out", "0", value="100k")
        .part("SW1B", "switch", "in", "out", None, kind="dpdt", pole="b")
        .part("SW1A", "switch", "out", None, None, kind="dpdt", pole="a")
    ).build()
    assert spare_poles(half, connect(half)) == set()


def test_a_jack_is_never_loose_and_carries_nothing() -> None:
    """D-174: a jack is drawing only. A stage wired to ground only through a jack's sleeve
    has no path in the simulation, so it's loose; the jack itself never is."""
    base = CircuitBuilder().part("IN", "guitar", "in").part("R1", "resistor", "in", "0", value="1M")
    assert _loose(base.part("J1", "jack", None, None)) == set()
    stage = base.part("J2", "jack", "x", "0", stereo=True, pins={"R": None})
    stage = stage.part("R9", "resistor", "x", "y", value="1k").part(
        "C9", "capacitor", "y", "x", value="1n"
    )
    assert _loose(stage) == {"R9", "C9"}
