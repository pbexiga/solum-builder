"""The editor's progress check (D-368): a board in the making, part by part, and the
placement limits shown as warnings."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import layout_from_data, parse_hole
from solum.stripboard.check import Progress, check_layout, progress
from solum.stripboard.footprints import board_parts
from solum.stripboard.limits import (
    Limit,
    LoudInput,
    broken_limits,
    group_met,
    limit_warnings,
    placement_limits,
)
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")
BOARD_REFS = ["C1", "C2", "C3", "C4", "Q1", "R1", "R2", "R3"]


def run(data: dict[str, Any], circuit: Circuit = RANGEMASTER) -> Progress:
    return progress(layout_from_data(data), circuit, MODELS, TABLE)


def edited(**changes: Any) -> dict[str, Any]:
    data = {**GOOD, **changes}
    if "parts" in changes:
        data["parts"] = {**GOOD["parts"], **changes["parts"]}
    return data


def states(p: Progress) -> dict[str, str]:
    return {n.net: n.state for n in p.nets}


def test_an_empty_board_has_everything_to_place_and_no_faults() -> None:
    p = run({"size": [12, 9]})
    assert p.to_place == BOARD_REFS
    assert sorted(p.wires_to_go) == ["GND", "IN.S", "IN.out", "OUT.S", "OUT.in", "V-",
                                     "VR1.1", "VR1.2", "VR1.3"]  # fmt: skip
    assert p.loose == 0
    assert p.faults == [] and p.stale == [] and not p.done
    assert set(states(p).values()) == {"pieces"}
    assert all(n.placed == 0 and n.pieces == 0 for n in p.nets)
    assert p.nets[0].net == "GND"  # ground first


def test_a_part_with_no_footprint_is_unplaceable_not_a_fault() -> None:
    """D-370: the tool opens whatever the circuit's state; a part it can't size is named
    for the tray and left out of `to_place`, never a fault."""
    data = RANGEMASTER.model_dump(mode="json", exclude_none=True)
    for part in data["parts"]:
        if part["ref"] == "C1":
            del part["kind"]
    p = run({"size": [12, 9]}, Circuit.model_validate(data))
    assert "C1" not in p.to_place and p.faults == []
    assert len(p.unplaceable) == 1 and "C1" in p.unplaceable[0]


def test_the_finished_rangemaster_is_done_net_by_net() -> None:
    p = run(GOOD)
    assert p.done and p.faults == [] and p.to_place == [] and p.wires_to_go == []
    assert p.nets_done == len(p.nets) == len(connect(RANGEMASTER).members)
    assert all(n.placed == n.total and n.pieces == 1 for n in p.nets)


def test_a_part_not_yet_placed_is_to_place_not_a_fault() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "C4"}
    p = run({**GOOD, "parts": parts})
    assert p.to_place == ["C4"] and p.faults == [] and not p.done
    c4 = {n.net for n in p.nets if n.state == "pieces"}
    assert c4 == {connect(RANGEMASTER).net_of("C4", pin) for pin in ("1", "2")}
    assert p.nets_done == len(p.nets) - 2


def test_a_short_names_the_other_net_and_where() -> None:
    p = run(edited(cuts=[]))  # G8's cut missed: V- and GND on strip 8
    shorted = {n.net: n for n in p.nets if n.state == "shorted"}
    assert set(shorted) == {"V-", "GND"}
    assert shorted["V-"].shorts[0].other == "GND"
    assert "R1's leg at C8 and R2's leg at I8 are joined" in shorted["V-"].shorts[0].words
    assert not p.done


def test_a_reversed_electrolytic_is_named() -> None:
    p = run(edited(parts={"C3": {"1": "G3", "2": "G2"}}))
    assert p.faults == [
        "C3 is the wrong way round: C3's + leg at G3 and C3's − leg at G2 are each on the "
        "other's strip. Turn it."
    ]


def test_a_resistor_or_film_cap_has_no_way_round() -> None:
    """D-368: the check turns an either-way part to fit; the full check passes it too."""
    turned = edited(parts={"R1": {"1": "C4", "2": "C8"}, "C1": {"1": "F4", "2": "F6"}})
    assert check_layout(layout_from_data(turned), RANGEMASTER, MODELS, TABLE).ok
    assert run(turned).done


def test_a_part_gone_from_the_circuit_is_stale_not_a_fault() -> None:
    p = run(edited(parts={"R9": {"1": "L1", "2": "L5"}}))
    assert p.stale == ["R9"] and p.faults == [] and not p.done


def _swapped(a: str, b: str) -> Circuit:
    """The Rangemaster with parts `a` and `b` trading places in the schematic: each now on
    the other's nets (a rewiring the board doesn't know about)."""
    data = RANGEMASTER.model_dump(mode="json", exclude_none=True)
    for part in data["parts"]:
        part["ref"] = {a: b, b: a}.get(part["ref"], part["ref"])
    return Circuit.model_validate(data)


def test_a_part_rewired_in_the_schematic_names_its_leg_and_where_it_should_go() -> None:
    """D-376: R1 and R2 swapped in the schematic. R1 (C8 on strip 8's V- end, C4 the base)
    now runs base to ground: its C8 leg is on V-'s strip, its own net's terminals are
    named; R2 likewise. Nothing is stale."""
    p = run(GOOD, _swapped("R1", "R2"))
    assert p.stale == [] and not p.done
    assert p.faults == [
        "R1's leg at C8 is on the strip of V-, but the circuit puts it on GND: it should join "
        "C3's + leg at G2, C4's + leg at I2, R3's leg at H2 and 3 more.",
        "R2's leg at I8 is on the strip of GND, but the circuit puts it on V-: it should join "
        "C4's − leg at I1, the V- supply's wire at A1 and VR1 lug 1's wire at D1.",
    ]


def test_a_rewired_leg_whose_net_is_not_placed_yet_says_so() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k not in ("R3", "C3", "C4")}
    wires = [{"from": "V-", "hole": "A1"}]
    p = run({**GOOD, "parts": parts, "wires": wires}, _swapped("R1", "R2"))
    # GND's six: R3, C3 and C4's legs, the ground wire, both jacks' sleeves
    assert p.faults == [
        "R1's leg at C8 is on the strip of V-, but the circuit puts it on GND: it should join "
        "6 terminals not on the board yet."
    ]


def test_off_board_parts_and_wires_gone_from_the_circuit_are_stale() -> None:
    """D-376: an off-board part put beside the board, and a wire to its lug, once the
    schematic no longer has it: stale (one click clears), not a wiring fault."""
    data = edited(off={"VR9": [2, -8]}, wires=[*GOOD["wires"], {"from": "VR9.1", "hole": "L1"}])
    p = run(data)
    assert p.stale == ["VR9"] and p.faults == []


def test_a_placed_part_that_cant_be_placed_now_is_not_stale() -> None:
    """C1 loses its kind in the schematic: still the circuit's, named in the tray."""
    data = RANGEMASTER.model_dump(mode="json", exclude_none=True)
    for part in data["parts"]:
        if part["ref"] == "C1":
            del part["kind"]
    p = run(GOOD, Circuit.model_validate(data))
    assert p.stale == [] and any("C1" in u for u in p.unplaceable)


def test_each_leg_says_what_it_must_reach_and_whether_it_does() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "R2"}
    p = run({**GOOD, "parts": parts})
    r1 = {leg.leg: leg for leg in p.legs["R1"]}
    assert r1["2"].hole == "C4" and r1["2"].net == connect(RANGEMASTER).net_of("Q1", "B")
    assert {(x.to, x.joined) for x in r1["2"].reach} == {("Q1.B", True), ("C1.2", True),
                                                         ("R2.1", False)}  # fmt: skip
    assert [leg.hole for leg in p.legs["R2"]] == [None, None]


# --- placement limits ----------------------------------------------------------------


def _two_buffers(circuit: Callable[..., CircuitBuilder]) -> Circuit:
    return (
        circuit()
        .rail("V+", 9)
        .part("IC1A", "opamp", "in", "a", "a", model="TL072", half="a")
        .part("IC1B", "opamp", "in2", "b", "b", model="TL072", half="b")
        .part("C1", "capacitor", "V+", "0", value="100n", kind="ceramic")
        .build()
    )


def test_a_decoupling_cap_must_sit_by_its_chip_s_supply_pin(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    limits = placement_limits(c, connect(c), board)
    assert limits == [Limit("C1", "1", "IC1", "8", "decoupling")]
    chip = {"1": "E3", "2": "E4", "3": "E5", "4": "E6", "8": "H3", "7": "H4", "6": "H5",
            "5": "H6"}  # fmt: skip
    far = layout_from_data({"size": [14, 8], "parts": {"IC1": chip,
                            "C1": {"1": "L3", "2": "L2"}}})  # fmt: skip
    rule = ("C1 should sit by IC1's pin 8 at H3 (its decoupling cap): on its strip within 2 "
            "holes, nothing between. ")  # fmt: skip
    assert limit_warnings(far, limits) == [rule + "C1: it's 4 holes away."]
    up = layout_from_data({"size": [14, 8], "parts": {"IC1": chip,
                           "C1": {"1": "J2", "2": "J1"}}})  # fmt: skip
    assert limit_warnings(up, limits) == [rule + "C1: it's on another strip."]
    cut = layout_from_data({"size": [14, 8], "cuts": ["I3"], "parts": {"IC1": chip,
                            "C1": {"1": "J3", "2": "J2"}}})  # fmt: skip
    assert limit_warnings(cut, limits) == [rule + "C1: the cut at I3 is between them."]
    both = layout_from_data({"size": [14, 8], "cuts": ["I3"], "parts": {"IC1": chip,
                             "C1": {"1": "L3", "2": "L2"}}})  # fmt: skip
    assert limit_warnings(both, limits) == [
        rule + "C1: it's 4 holes away and the cut at I3 is between them."
    ]
    near = layout_from_data({"size": [14, 8], "parts": {"IC1": chip,
                             "C1": {"1": "J3", "2": "J2"}}})  # fmt: skip
    assert limit_warnings(near, limits) == []


def test_an_either_way_part_meets_its_limit_by_either_leg(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """C1 turned round (its leg 2 by pin 8, as the check lets a ceramic cap go): met when
    it's `turnable`, broken by its leg 1 otherwise."""
    c = _two_buffers(circuit)
    limits = placement_limits(c, connect(c), board_parts(c, MODELS, TABLE)[0])
    chip = {"1": "E3", "2": "E4", "3": "E5", "4": "E6", "8": "H3", "7": "H4", "6": "H5",
            "5": "H6"}  # fmt: skip
    turned = layout_from_data({"size": [14, 8], "parts": {"IC1": chip,
                               "C1": {"1": "J2", "2": "J3"}}})  # fmt: skip
    assert broken_limits(turned, limits) == [("IC1", "8")]
    assert broken_limits(turned, limits, frozenset({"C1"})) == []


def _kinds(limits: list[Limit]) -> list[tuple[str, str, str, str]]:
    return [(lim.part, lim.anchor, lim.pin, lim.why) for lim in limits]


def test_a_regulator_s_smallest_cap_on_each_side_must_sit_by_its_pin(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """D-400: the 100 nF by the input, not the 100 µF beside it; the output's own."""
    c = (
        circuit()
        .rail("V+", 18)
        .part("U1", "regulator", "V+", "o", "0", model="78L12")
        .part("C1", "capacitor", "V+", "0", value="100u", kind="electrolytic")
        .part("C2", "capacitor", "V+", "0", value="100n", kind="ceramic")
        .part("C3", "capacitor", "o", "0", value="330n", kind="film")
        .part("R1", "resistor", "o", "0", value="10k")
        .build()
    )
    board, _ = board_parts(c, MODELS, TABLE)
    found = _kinds(placement_limits(c, connect(c), board))
    assert [(p, w) for p, a, _, w in found if a == "U1"] == [("C2", "regulator"),
                                                             ("C3", "regulator")]  # fmt: skip


def test_an_emitter_bypass_cap_must_sit_by_the_emitter(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """D-400: Q1's emitter is bypassed; Q2's is grounded, so it has none."""
    c = (
        circuit()
        .rail("V+", 9)
        .part("Q1", "bjt", "c1", "b1", "e1", model="2N2222A")
        .part("R1", "resistor", "e1", "0", value="1k")
        .part("C1", "capacitor", "e1", "0", value="22u", kind="electrolytic")
        .part("R2", "resistor", "V+", "c1", value="10k")
        .part("Q2", "bjt", "c2", "c1", "0", model="2N2222A")
        .part("R3", "resistor", "V+", "c2", value="10k")
        .build()
    )
    board, _ = board_parts(c, MODELS, TABLE)
    found = _kinds(placement_limits(c, connect(c), board))
    assert found == [("C1", "Q1", "E", "bypass")]


def test_the_parts_on_a_high_gain_stage_s_input_must_sit_by_it(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """D-400: with Q1 found high gain (`probe.loud_inputs`), every two-leg part on its
    base's net in series with the signal keeps by the base: its coupling cap and its
    feedback resistor, not the bias resistors to ground or to a rail AC-quiet there."""
    c = (
        circuit()
        .rail("V+", 9)
        .part("Q1", "bjt", "c", "b", "0", model="2N2222A")
        .part("C1", "capacitor", "in", "b", value="100n", kind="film")
        .part("R1", "resistor", "c", "b", value="470k")
        .part("R2", "resistor", "V+", "c", value="10k")
        .part("R3", "resistor", "in", "0", value="1M")
        .part("R4", "resistor", "V+", "b", value="1M")
        .part("R5", "resistor", "b", "0", value="100k")
        .build()
    )
    board, _ = board_parts(c, MODELS, TABLE)
    assert placement_limits(c, connect(c), board) == []
    found = _kinds(
        placement_limits(c, connect(c), board, [LoudInput("Q1", "B", frozenset({"V+"}))])
    )
    assert found == [("C1", "Q1", "B", "input"), ("R1", "Q1", "B", "input")]


def test_two_high_gain_inputs_on_one_net_keep_its_parts_by_the_first(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """The Klon's two U2 inputs share a net: its parts are kept by the first input only, as
    one part can't sit by two pins on different strips."""
    c = (
        circuit()
        .rail("V+", 9)
        .part("Q1", "bjt", "c", "b", "0", model="2N2222A")
        .part("Q2", "bjt", "d", "b", "0", model="2N2222A")
        .part("C1", "capacitor", "in", "b", value="100n", kind="film")
        .part("R2", "resistor", "V+", "c", value="10k")
        .part("R3", "resistor", "V+", "d", value="10k")
        .build()
    )
    board, _ = board_parts(c, MODELS, TABLE)
    found = _kinds(
        placement_limits(c, connect(c), board, [LoudInput("Q1", "B"), LoudInput("Q2", "B")])
    )
    assert found == [("C1", "Q1", "B", "input")]


def test_group_met_counts_holes_from_the_pin_one_more_per_extra_leg() -> None:
    pin = parse_hole("E3")
    clear: Callable[[tuple[int, int]], bool] = lambda h: False  # noqa: E731
    assert group_met(pin, [parse_hole("G3")], clear)  # 2 holes away
    assert not group_met(pin, [parse_hole("H3")], clear)  # 3
    assert group_met(pin, [parse_hole("H3"), parse_hole("C3")], clear)  # 3 with two legs
    assert not group_met(pin, [parse_hole("G4")], clear)  # another strip
    assert not group_met(pin, [parse_hole("G3")], lambda h: h == parse_hole("F3"))


def test_the_off_board_parts_are_the_parts_list_s_and_power() -> None:
    """The Rangemaster's pot, the guitar's and amp's jacks it doesn't draw, and Power
    (D-375); each drawn at its default spot until it's put somewhere."""
    p = run({"size": [12, 9]})
    assert [(o.name, o.kind, o.value) for o in p.items] == [
        ("VR1 (Volume)", "pot", "A10k"), ("IN (Input)", "jack", '¼" jack'),
        ("OUT (Output)", "jack", '¼" jack'), ("Power", "power", ""),
    ]  # fmt: skip
    assert p.spots["VR1"] == (0, -7)
    moved = run({"size": [12, 9], "off": {"VR1": [4, -9]}})
    assert moved.spots["VR1"] == (4, -9)


def test_a_loose_wire_is_to_do_not_a_fault() -> None:
    wires = [w for w in GOOD["wires"] if w["from"] != "VR1.2"]
    p = run(edited(wires=[*wires, {"from": "VR1.2"}]))
    assert p.loose == 1 and p.wires_to_go == ["VR1.2"] and p.faults == [] and not p.done
    assert {n.net: n.wires for n in p.nets}["C2.1"] == ("VR1 lug 2",)


def test_each_net_names_its_off_board_wires_still_to_land() -> None:
    """D-371: the lugs still to wire are listed with their nets (the Nets pane), in words."""
    empty = {n.net: n.wires for n in run({"size": [12, 9]}).nets}
    assert empty["V-"] == ("the V- supply", "VR1 lug 1") and empty["C2.1"] == ("VR1 lug 2",)
    assert empty["GND"] == ("ground", "the input jack's sleeve", "the output jack's sleeve")
    assert sum(len(w) for w in empty.values()) == 9
    assert all(n.wires == () for n in run(GOOD).nets)


def test_the_rails_copper_is_given_by_net() -> None:
    """D-381: on the Rangemaster (PNP, so V- is its supply) strip 8 is V- left of the cut at
    G8 and GND right of it; links B1–B8 and K2–K8 join strips 1 (V-) and 2 (GND). Copper
    carrying two nets is a short's, not a rail's."""
    p = run(GOOD)
    assert p.rails == {"GND": [(1, 0, 11), (7, 7, 11)], "V-": [(0, 0, 11), (7, 0, 5)]}
    shorted = run(edited(cuts=[]))
    assert (7, 0, 11) not in [r for found in shorted.rails.values() for r in found]
