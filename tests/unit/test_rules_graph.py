"""Connectivity graphs for the topology rules (solum/rules/graph.py), by hand."""

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.rules import graph


def test_groups_join_through_edges() -> None:
    joined = graph.groups(["a", "b", "c", "d"], [("a", "b"), ("b", "c")])
    assert joined["a"] == joined["c"] == {"a", "b", "c"}
    assert joined["d"] == {"d"}


def test_reachable_stops_at_blocked_nets() -> None:
    edges = [("in", "x"), ("x", "V+"), ("V+", "y"), ("x", "out")]
    assert graph.reachable("in", edges, blocked={"V+"}) == {"in", "x", "V+", "out"}
    assert "y" not in graph.reachable("in", edges, blocked={"V+"})


def test_reachable_can_follow_edges_one_way() -> None:
    edges = [("a", "b"), ("c", "b")]
    assert graph.reachable("a", edges, directed=True) == {"a", "b"}
    assert graph.reachable("a", edges) == {"a", "b", "c"}


def test_another_op_amps_output_can_be_left_but_not_crossed() -> None:
    """D-247: U1 drives o1 itself, so a path from o2 through R6 can't enter o1, while
    U1's own way in (p to o1) and out (R5) still pass."""
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("U1", "opamp", "p", "o1", "o1", model="TL072")
        .part("R5", "resistor", "o1", "m", value="100k")
        .part("R6", "resistor", "o2", "o1", value="10k")
        .part("U2", "opamp", "p", "m", "o2", model="TL072")
        .build()
    )
    nets = connect(c)
    edges = graph.signal_edges(c, nets, skip="U2", dc=True)
    arcs = graph.one_way_outputs(c, nets, edges, "U2")
    assert graph.reachable("o2", arcs, directed=True) == {"o2"}
    assert "m" in graph.reachable("p", arcs, directed=True)


def test_a_capacitor_is_no_dc_path_but_carries_signal() -> None:
    c = CircuitBuilder().part("C1", "capacitor", "a", "b", value="100n").build()
    n = connect(c)
    assert graph.spice_edges(c, n) == []
    assert graph.signal_edges(c, n) == [("a", "b")]


def test_a_jack_is_no_path() -> None:
    """D-174: drawing only: its tip and sleeve aren't joined in the simulation."""
    c = CircuitBuilder().part("J1", "jack", "t", "0").build()
    assert graph.spice_edges(c, connect(c)) == []


def test_every_pin_pair_is_an_edge() -> None:
    """An emitter follower's base reaches its emitter even with the collector on V+."""
    c = CircuitBuilder().rail("V+", 9).part("Q1", "bjt", "V+", "b", "e", model="2N5089").build()
    n = connect(c)
    assert graph.reachable("b", graph.signal_edges(c, n), blocked={"V+"}) >= {"e"}


def test_rails_and_dc_sources_are_tied_to_ground() -> None:
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "a", value="1k")
        .part("V1", "vsource", "b", "GND", value=16)
        .build()
    )
    edges = graph.spice_edges(c, connect(c))
    assert ("V+", "GND") in edges and ("b", "GND") in edges


def test_a_switchs_poles_are_apart_as_ngspice_sees_them() -> None:
    """Each contact is its own resistor (open ones 1 TΩ), so a common reaches its own
    throws but never the other pole's (the Tone Bender's Mode switch, D-135)."""
    a = {"A2": "a", "A1": "b", "A3": "c"}
    b = {"B2": "d", "B1": "e", "B3": "f"}
    c = (
        CircuitBuilder()
        .part("SW1A", "switch", kind="dpdt", pole="a", pins=a)
        .part("SW1B", "switch", kind="dpdt", pole="b", pins=b)
        .build()
    )
    joined = graph.groups([*a.values(), *b.values()], graph.spice_edges(c, connect(c)))
    assert joined["a"] == {"a", "b", "c"}
    assert joined["d"] == {"d", "e", "f"}


def test_bias_ignores_semiconductors_and_open_contacts() -> None:
    c = (
        CircuitBuilder()
        .part("D1", "diode", "a", "GND", model="1N4148")
        .part("SW1", "switch", position=0, pins={"2": "b", "1": "GND", "3": "c"})
        .build()
    )
    edges = graph.bias_edges(c, connect(c))
    assert ("b", "GND") in edges and ("b", "c") not in edges
    assert not any("a" in e for e in edges)


def test_bias_anchors_are_driven_nets() -> None:
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("Q1", "bjt", "c", "b", "e", model="2N5089")
        .part("U1", "opamp", "p", "m", "o", model="TL072")
        .build()
    )
    anchors = graph.bias_anchors(c, connect(c))
    assert {"GND", "V+", "c", "e", "o"} <= anchors
    assert not {"b", "p", "m"} & anchors


def test_a_single_otas_output_is_a_current_and_it_has_no_buffer() -> None:
    """A CA3080 has no buffer pin to drive a net (D-180): its output is a current, so the
    load sets the voltage. It used to crash looking for `bufout`."""
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("U1", "ota", "p", "m", "o", "ib", model="CA3080")
        .part("IC1A", "ota", "p", "m", "o2", "b2", "d", "o2", "buf", model="LM13700", half="a")
        .part("IC1B", "ota", model="LM13700", half="b")
        .build()
    )
    anchors = graph.bias_anchors(c, connect(c))
    assert "buf" in anchors
    assert not {"o", "o2", "p", "m", "ib"} & anchors


def test_block_ports_count_as_driven() -> None:
    cap = {"ref": "C1", "type": "capacitor", "nets": ["in", "x"], "value": "1u"}
    res = {"ref": "R1", "type": "resistor", "nets": ["x", "GND"], "value": "1M"}
    spec = {"template": True, "ports": {"in": "in"}, "parts": [cap, res]}
    c = CircuitBuilder.from_spec(spec).build()
    assert ("in", "GND") in graph.spice_edges(c, connect(c))


def test_big_caps_to_a_supply_make_ac_grounds() -> None:
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("C1", "capacitor", "VREF", "GND", value="10u")
        .part("C2", "capacitor", "a", "GND", value="100n")
        .build()
    )
    n = connect(c)
    assert graph.ac_grounds(c, n, {"GND", "V+"}) == {"VREF"}
