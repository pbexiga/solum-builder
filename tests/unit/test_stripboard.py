"""The stripboard board model, footprints and check (D-367): hand-made layouts, good and
broken, each broken one refused with a sentence naming its fault."""

import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Capacitor, Circuit, Resistor, Trimmer
from solum.circuit.switches import KINDS
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import (
    BoardError,
    Layout,
    Link,
    Placed,
    hole_name,
    layout_data,
    layout_from_data,
    parse_hole,
    segments,
)
from solum.stripboard.check import (
    Checked,
    check_layout,
    joined_groups,
    outline_overlaps,
    placement_warnings,
    stripboard_nets,
)
from solum.stripboard.footprints import (
    board_parts,
    body_holes,
    dip_legs,
    drawing_data,
    leg_problem,
    one_board_part,
    triangle_legs,
)
from solum.stripboard.offboard import default_spots, lug_nets, off_board_items, switch_drawing
from solum.stripboard.start import start_for_me
from solum.stripboard.wiring import WiringError, pad_cost, wire_for_me
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def check(data: dict[str, Any], circuit: Circuit = RANGEMASTER) -> Checked:
    return check_layout(layout_from_data(data), circuit, MODELS, TABLE)


def edited(**changes: Any) -> dict[str, Any]:
    """The good Rangemaster layout with some fields replaced (parts merged)."""
    data = {**GOOD, **changes}
    if "parts" in changes:
        data["parts"] = {**GOOD["parts"], **changes["parts"]}
    return data


# --- the board ---------------------------------------------------------------------


def test_holes_are_named_by_column_letter_and_strip_number() -> None:
    assert hole_name((5, 6)) == "F7"
    assert hole_name((0, 0)) == "A1"
    assert hole_name((26, 9)) == "AA10"
    assert parse_hole("f7") == (5, 6)
    with pytest.raises(BoardError, match="like F7"):
        parse_hole("7F")


@given(st.integers(0, 700), st.integers(0, 200))
def test_hole_names_round_trip(column: int, strip: int) -> None:
    assert parse_hole(hole_name((column, strip))) == (column, strip)


def test_a_cut_splits_its_strip_and_holds_no_copper() -> None:
    seg = segments(Layout(4, 2, (), frozenset({(1, 0)})))
    assert (1, 0) not in seg
    assert seg[(0, 0)] != seg[(2, 0)]
    assert seg[(2, 0)] == seg[(3, 0)]
    assert seg[(0, 1)] == seg[(3, 1)] != seg[(0, 0)]


def test_segments_and_groups_of_chosen_holes_are_the_whole_boards() -> None:
    layout = layout_from_data(GOOD)
    chosen = [(0, 0), (6, 7), (3, 4), (99, 0), *layout.cuts]  # off the board, cut: none
    full = segments(layout)
    assert segments(layout, chosen) == {h: full[h] for h in chosen if h in full}
    holes, lugs = joined_groups(layout)
    some, same_lugs = joined_groups(layout, chosen)
    assert some == {h: holes[h] for h in chosen if h in holes}
    assert same_lugs == lugs


def test_layout_data_round_trips() -> None:
    layout = layout_from_data(GOOD)
    assert layout_from_data(layout_data(layout)) == layout
    assert Link((1, 0), (1, 7)).between == [(1, s) for s in range(1, 7)]


def test_malformed_layout_data_is_refused_in_plain_english() -> None:
    with pytest.raises(BoardError, match="incomplete or malformed"):
        layout_from_data({"parts": {}})


# --- footprints --------------------------------------------------------------------


def test_footprints_come_from_the_table_by_type_value_and_package() -> None:
    board, problems = board_parts(RANGEMASTER, MODELS, TABLE)
    assert problems == []
    assert set(board) == {"Q1", "R1", "R2", "R3", "C1", "C2", "C3", "C4"}  # not VR1
    r1, c1, c3, q1 = board["R1"].footprint, board["C1"].footprint, board["C3"], board["Q1"]
    assert (r1.shape, r1.flat, r1.stand, r1.length) == ("axial", 3, 1, 6.3)  # ¼ W (D-410)
    assert (c1.shape, c1.steps, c1.length) == ("radial", (2, 3, 4), 7.2)  # 5n film, MKS 2
    assert (c3.footprint.diameter, c3.footprint.steps) == (5, (1, 2, 3))  # 47µ: NIC NRWS
    assert q1.footprint.order == ("E", "B", "C")  # OC44: e b c in a line
    assert q1.pins["B"] == ("Q1", "B")


def test_an_axial_electrolytic_lies_flat_or_stands_as_a_resistor(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """D-411: by value at 25 V from Vishay's 021 ASM: 10µ in its 4.5 × 10 mm case, flat
    from 4 holes apart as the published Fuzz Face lays it (10.16 mm: leads bent at the
    body), standing from 2; 470µ, 10 × 18, flat from 8, standing from 3. Radial unless set."""
    c = (
        circuit()
        .part("C1", "capacitor", "a", "0", value="10µ", kind="electrolytic", axial=True)
        .part("C2", "capacitor", "a", "0", value="470µ", kind="electrolytic", axial=True)
        .part("C3", "capacitor", "a", "0", value="10µ", kind="electrolytic")
        .part("C4", "capacitor", "a", "0", value="2.2m", kind="electrolytic", axial=True)
        .build()
    )
    board, problems = board_parts(c, MODELS, TABLE)
    c1, c2 = board["C1"].footprint, board["C2"].footprint
    assert (c1.shape, c1.flat, c1.stand, c1.length, c1.width) == ("axial", 4, 2, 10, 4.5)
    assert (c2.flat, c2.stand, c2.length, c2.width) == (8, 3, 18, 10)
    assert board["C3"].footprint.shape == "radial"
    assert problems == ["There's no board size for an axial electrolytic as big as C4 yet."]
    assert leg_problem(board["C1"], {"1": (2, 7), "2": (2, 3)}, False) is None
    assert "at least 4 holes" in (leg_problem(board["C1"], {"1": (2, 6), "2": (2, 3)}, False) or "")
    assert leg_problem(board["C1"], {"1": (2, 5), "2": (2, 3)}, True) is None


def test_a_capacitor_without_a_type_or_size_gets_no_footprint(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    c = (
        circuit()
        .part("C1", "capacitor", "a", "0", value="10n")
        .part("C2", "capacitor", "a", "0", value="10µ", kind="tantalum", rating_v=16)
        .part("C3", "capacitor", "a", "0", value="2.2m", kind="electrolytic", rating_v=16)
        .build()
    )
    board, problems = board_parts(c, MODELS, TABLE)
    assert board == {}
    assert problems == [
        "C1 has no type, so its size isn't known: set its type (film, electrolytic...) in "
        "its properties.",
        "There's no board size for tantalum capacitors (C2) yet.",
        "There's no board size for a electrolytic as big as C3 yet.",
    ]


def test_legs_must_sit_as_the_footprint_allows() -> None:
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    r1, c1, q1 = board["R1"], board["C1"], board["Q1"]
    assert leg_problem(r1, {"1": (2, 6), "2": (2, 3)}, False) is None  # 3 apart, flat (D-410)
    assert leg_problem(r1, {"1": (2, 10), "2": (2, 3)}, False) is None  # long leads: no most
    assert "at least 3 holes" in (leg_problem(r1, {"1": (2, 5), "2": (2, 3)}, False) or "")
    assert leg_problem(r1, {"1": (2, 4), "2": (2, 3)}, True) is None  # stood up
    assert leg_problem(r1, {"1": (2, 5), "2": (2, 3)}, True) is None  # a lead bent further
    assert "one row or one column" in (leg_problem(r1, {"1": (3, 7), "2": (2, 3)}, False) or "")
    assert leg_problem(c1, {"1": (2, 4), "2": (2, 3)}, False) == (
        "C1's legs must be 2 to 4 holes apart."
    )
    assert "can't be stood up" in (leg_problem(c1, {"1": (2, 5), "2": (2, 3)}, True) or "")
    assert leg_problem(q1, {"E": (4, 4), "B": (4, 6), "C": (4, 8)}, False) is None  # bent out
    assert "in a line, in order" in (
        leg_problem(q1, {"B": (4, 2), "E": (4, 3), "C": (4, 4)}, False) or ""
    )


def test_a_body_covers_the_holes_under_it() -> None:
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    flat = {"1": (2, 7), "2": (2, 3)}
    assert body_holes(board["R1"], flat, False) == {(2, 4), (2, 5), (2, 6)}
    assert body_holes(board["R1"], {"1": (2, 4), "2": (2, 3)}, True) == set()
    assert body_holes(board["C3"], {"1": (7, 1), "2": (7, 2)}, False) == set()  # 5 mm


def test_a_dip_sits_across_the_strips_pin_1_top_left_or_turned_round() -> None:
    legs = dip_legs(8, (4, 2))
    assert legs["1"] == (4, 2) and legs["4"] == (4, 5)
    assert legs["8"] == (7, 2) and legs["5"] == (7, 5)
    turned = dip_legs(8, (7, 5), turned=True)
    assert turned["1"] == (7, 5) and turned["8"] == (4, 5) and turned["4"] == (7, 2)


# --- the check: the Rangemaster ----------------------------------------------------


def test_the_hand_made_rangemaster_layout_passes() -> None:
    result = check(GOOD)
    assert result.faults == []
    assert result.ok
    assert result.nets == len(connect(RANGEMASTER).members)  # every net is on the board


def test_off_board_lugs_are_each_pot_lug_the_jacks_and_the_supply() -> None:
    """D-375: the parts list's off-board parts in its order (the undrawn jacks with their
    sleeves on ground), then Power for the supplies no drawn part brings."""
    nets = connect(RANGEMASTER)
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    items = off_board_items(RANGEMASTER, nets, board, MODELS)
    assert [(i.ref, i.name, i.kind) for i in items] == [
        ("VR1", "VR1 (Volume)", "pot"), ("IN", "IN (Input)", "jack"),
        ("OUT", "OUT (Output)", "jack"), ("power", "Power", "power"),
    ]  # fmt: skip
    assert [lug.label for lug in items[1].lugs] == ["T", "S"]
    assert lug_nets(items) == {
        "VR1.1": "V-", "VR1.2": "C2.1", "VR1.3": "Q1.C", "IN.out": "in", "IN.S": "GND",
        "OUT.in": "out", "OUT.S": "GND", "V-": "V-", "GND": "GND",
    }  # fmt: skip
    assert items[0].size == (7, 3)


def test_a_dual_pot_is_one_off_board_part_with_its_gangs_lugs() -> None:
    bd2 = load_circuit(LIBRARY / "starters" / "boss-bd2.json")
    board, _ = board_parts(bd2, MODELS, TABLE)
    items = {i.ref: i for i in off_board_items(bd2, connect(bd2), board, MODELS)}
    assert [lug.end for lug in items["VR1"].lugs] == [
        "VR1A.1", "VR1A.2", "VR1A.3", "VR1B.1", "VR1B.2", "VR1B.3"]  # fmt: skip
    assert [lug.label for lug in items["VR1"].lugs][:2] == ["A1", "A2"]


def test_a_footswitch_is_drawn_as_a_square_of_lugs_and_a_toggle_as_a_slim_one() -> None:
    """D-384: poles across, each pole's lug 1 at the top, the common in the middle, 3 at
    the bottom, two holes apart; labels as the pins (A1), not the pole twice (AA1)."""
    klon = load_circuit(LIBRARY / "starters" / "klon-centaur-aion-built.json")
    board, _ = board_parts(klon, MODELS, TABLE)
    items = {i.ref: i for i in off_board_items(klon, connect(klon), board, MODELS)}
    stomp, toggle = items["SW2"], items["SW1"]
    assert (stomp.shape, stomp.size) == ("stomp", (7, 7))
    assert (toggle.shape, toggle.size) == ("toggle", (7, 7))
    places = {lug.label: at for lug, at in zip(stomp.lugs, stomp.places, strict=True)}
    assert places["A1"] == (1, 1) and places["A2"] == (1, 3) and places["A3"] == (1, 5)
    assert places["B1"] == (3, 1) and places["C3"] == (5, 5)
    assert items["VR1"].shape == "row" and items["VR1"].places[:2] == ((1, 2), (3, 2))


@pytest.mark.parametrize("kind", [k for k in KINDS.values() if k.group != "DIP"], ids=str)
def test_every_switch_type_has_its_lugs_apart_inside_its_outline(kind: Any) -> None:
    shape, (width, height), places = switch_drawing(kind)
    assert len(places) == kind.poles * len(kind.lugs)
    at = list(places.values())
    assert all(1 <= x <= width - 2 and 1 <= y <= height - 2 for x, y in at), at
    gaps = [abs(a[0] - b[0]) + abs(a[1] - b[1]) for i, a in enumerate(at) for b in at[i + 1 :]]
    assert min(gaps, default=2) >= 1.5  # room for a wire between two lugs
    assert (shape == "stomp") == (kind.group == "Footswitch")
    assert (shape == "rotary") == (kind.look == "rotary")
    if shape == "stomp":
        assert width == height


def test_footswitches_go_below_the_board_with_the_jacks_down_their_sides() -> None:
    klon = load_circuit(LIBRARY / "starters" / "klon-centaur-aion-built.json")
    board, _ = board_parts(klon, MODELS, TABLE)
    items = off_board_items(klon, connect(klon), board, MODELS)
    spots = default_spots(items, layout_from_data({**GOOD, "size": [20, 12]}))
    assert spots["SW2"] == (6, 16)  # under the middle of a 20-column board, past its margin
    assert spots["SW1"][1] < 0  # a toggle goes on top with the knobs
    assert spots["IN"] == (24, 9) and spots["OUT"][1] == 9  # beside the board's bottom strips


def test_default_spots_put_pots_on_top_input_right_output_left() -> None:
    nets = connect(RANGEMASTER)
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    items = off_board_items(RANGEMASTER, nets, board, MODELS)
    spots = default_spots(items, layout_from_data(GOOD))  # 12 × 9
    assert spots["VR1"] == (0, -7)  # above the margin, its bottom 2 strips clear of it
    assert spots["IN"] == (16, 0) and spots["OUT"][0] + items[2].size[0] - 1 == -5
    assert spots["power"][1] == 13


def test_a_missed_cut_is_refused() -> None:
    result = check(edited(cuts=[]))
    assert result.faults == [
        "R1's leg at C8 and R2's leg at I8 are joined on the board, but the circuit doesn't "
        "connect them."
    ]


def test_a_leg_one_strip_off_is_refused() -> None:
    result = check(edited(parts={"R2": {"1": "J4", "2": "J9"}}))  # on the output strip
    assert "C2's leg at F9 and R2's leg at J9 are joined on the board" in result.faults[0]
    assert any("aren't connected on the board" in f and "R2's leg at J9" in f
               for f in result.faults)  # fmt: skip


def test_a_missing_link_is_refused() -> None:
    result = check(edited(links=[["B1", "B8"]]))
    assert result.faults == [
        "C3's + leg at F2 and R2's leg at I8 aren't connected on the board, but the circuit "
        "joins them."
    ]


def test_a_transistor_turned_round_is_refused() -> None:
    result = check(edited(parts={"Q1": {"E": "E5", "B": "E4", "C": "E3"}}))
    assert "Q1's emitter at E5" in " ".join(result.faults)


def test_an_unwired_lug_a_wire_to_nothing_or_a_loose_wire_is_refused() -> None:
    wires = [w for w in GOOD["wires"] if w["from"] != "VR1.1"]
    assert check(edited(wires=wires)).faults == ["VR1 lug 1 isn't wired yet."]
    wrong = check(edited(wires=[*GOOD["wires"], {"from": "VR2.1", "hole": "L1"}]))
    assert "A wire goes to 'VR2.1', which isn't an off-board lug of this circuit." in (wrong.faults)
    loose = check(edited(wires=[*wires, {"from": "VR1.1"}]))
    assert "The wire from VR1 lug 1 is loose: solder its other end." in loose.faults


def test_lugs_wired_together_join_their_nets() -> None:
    """The output jack's sleeve reaches ground through the input's (D-375); wired to the
    input instead, it's a short."""
    assert check(GOOD).ok
    wires = [w for w in GOOD["wires"] if w["from"] != "OUT.S"]
    short = check(edited(wires=[*wires, {"from": "OUT.S", "lug": "IN.out"}]))
    assert short.faults[0].startswith("The output jack's sleeve and C1's leg at F6 are joined")


def test_a_wire_in_a_cut_hole_or_beside_a_leg_is_refused() -> None:
    wires = [{**w, "hole": "G8"} if w["from"] == "VR1.1" else w for w in GOOD["wires"]]
    cut = check(edited(wires=wires))
    assert "The wire from VR1 lug 1 is in a cut hole (G8): the cut takes its copper away." in (
        cut.faults
    )
    wires = [{**w, "hole": "E3"} if w["from"] == "VR1.1" else w for w in GOOD["wires"]]
    beside = layout_from_data(edited(wires=wires))
    assert "Q1 and the wire from VR1 lug 1 share E3: check both leads fit." in (
        placement_warnings(beside, board_parts(RANGEMASTER, MODELS, TABLE)[0])
    )  # D-410: a warning, the builder's call


def test_missing_extra_and_off_board_parts_are_named() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "C4"}
    assert "C4 isn't on the board." in check(edited(parts=parts) | {"parts": parts}).faults
    extra = check(edited(parts={"VR1": {"1": "L1", "2": "L2", "3": "L3"}}))
    assert "VR1 goes off the board: put it beside the board and wire it." in extra.faults


def test_two_legs_of_a_part_in_a_hole_or_a_body_over_a_leg_is_refused() -> None:
    """D-410: what can't be built is a fault; two things from different parts in one hole
    is a warning (`test_two_parts_in_a_hole_is_a_warning`)."""
    twice = check(edited(parts={"R1": {"1": "C4", "2": "C4"}}))
    assert "R1 has two legs in C4." in twice.faults
    over = check(edited(parts={"Q1": {"E": "C5", "B": "C6", "C": "C7"}}))  # under R1's body
    assert "R1's body covers C5, where Q1 goes." in over.faults


def test_two_parts_in_a_hole_is_a_warning() -> None:
    """R3 stood in C3's leg's hole: no "share" fault (the nets' check still has its say)."""
    data = edited(parts={"R3": {"1": "F3", "2": "F4"}})
    assert not any("share" in f for f in check(data).faults)
    board = board_parts(RANGEMASTER, MODELS, TABLE)[0]
    assert placement_warnings(layout_from_data(data), board)[:2] == [
        "R3 and C3 share F3: check both leads fit.",
        "R3 and C1 share F4: check both leads fit.",
    ]


def test_a_link_may_run_under_any_body_and_over_a_leg_with_insulated_wire() -> None:
    """D-410: a link under a flat resistor, a film cap or an electrolytic says nothing; over
    a leg it's a warning (insulated wire), not a fault."""
    board = board_parts(RANGEMASTER, MODELS, TABLE)[0]
    for link in (["C5", "C7"], ["F4", "F6"]):  # under R1's body, under C1's (film)
        data = edited(links=[*GOOD["links"], link])
        assert not any("under" in f for f in check(data).faults)
        assert not any("under" in w for w in placement_warnings(layout_from_data(data), board))
    over = layout_from_data(edited(links=[["B1", "B8"], ["K2", "K8"], ["E2", "E6"]]))
    assert "The link from E2 to E6 passes over Q1 at E3: use insulated wire for it." in (
        placement_warnings(over, board)
    )
    assert not any(
        "passes over" in f for f in check_layout(over, RANGEMASTER, MODELS, TABLE).faults
    )


def test_two_link_ends_in_one_hole_are_a_tap_with_nothing_said() -> None:
    """D-410: a link from strip 1 to 8 and one from 8 to 9 sharing B8, down one column (the
    DS-1's "P joins 2, 6, 13"): no fault, no warning about the hole."""
    tapped = layout_from_data(edited(links=[["B1", "B8"], ["B8", "B9"], ["K2", "K8"]]))
    faults = check_layout(tapped, RANGEMASTER, MODELS, TABLE).faults
    assert not any("share" in f or ("B8" in f and "link" in f) for f in faults)
    assert placement_warnings(tapped, board_parts(RANGEMASTER, MODELS, TABLE)[0]) == []


# --- the check: a chip -------------------------------------------------------------


def _two_buffers(circuit: Callable[..., CircuitBuilder]) -> Circuit:
    """A TL072's halves as followers, a bias resistor on each input, a decoupling cap."""
    return (
        circuit()
        .rail("V+", 9)
        .part("IC1A", "opamp", "in", "a", "a", model="TL072", half="a")
        .part("IC1B", "opamp", "in2", "b", "b", model="TL072", half="b")
        .part("R1", "resistor", "in", "0", value="1M")
        .part("R2", "resistor", "in2", "0", value="1M")
        .part("C1", "capacitor", "V+", "0", value="100n", kind="ceramic")
        .build()
    )


CHIP = {
    "size": [12, 10],
    "parts": {
        "IC1": {
            "1": "E3",
            "2": "E4",
            "3": "E5",
            "4": "E6",
            "8": "H3",
            "7": "H4",
            "6": "H5",
            "5": "H6",
        },
        "R1": {"1": "D5", "2": "D6"},
        "R2": {"1": "L6", "2": "L10"},
        "C1": {"1": "B1", "2": "B2"},
    },
    "standing": ["R1"],
    "cuts": ["F3", "F4", "F5", "F6"],  # the chip's own, between its rows
    "links": [["C3", "C4"], ["J4", "J5"], ["K1", "K3"], ["A2", "A10"], ["B6", "B10"]],
    "wires": [{"from": "V+", "hole": "D1"}, {"from": "GND", "hole": "D2"}],
}


def test_a_chip_layout_passes(circuit: Callable[..., CircuitBuilder]) -> None:
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    assert board["IC1"].pins["8"] == ("IC1C", "V+") and board["IC1"].pins["5"] == ("IC1B", "+")
    assert check(CHIP, c).faults == []


def test_drawing_data_names_a_chip_s_units(circuit: Callable[..., CircuitBuilder]) -> None:
    """The Board view draws IC1 from it and lights its units on the schematic (D-368)."""
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    chip = drawing_data(board, c)["IC1"]
    assert chip["shape"] == "dip" and chip["legs"] == [str(n) for n in range(1, 9)]
    assert chip["row_holes"] == 3 and chip["refs"] == ["IC1A", "IC1B", "IC1C"]


def test_a_missed_cut_under_a_chip_is_named(circuit: Callable[..., CircuitBuilder]) -> None:
    result = check({**CHIP, "cuts": ["F3", "F4", "F6"]}, _two_buffers(circuit))
    assert result.faults == ["The strip under IC1 isn't cut between pins 3 and 6 (strip 5)."]


def test_a_leg_between_a_chip_s_rows_is_a_warning_and_a_link_may_pass(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """D-410 (D-401 relaxed): the holes between a chip's rows are under its body; a leg
    there is a warning (a socketed chip over a low part), not a fault; a link may pass
    under it and say nothing."""
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    legs = {leg: parse_hole(name) for leg, name in CHIP["parts"]["IC1"].items()}
    assert body_holes(board["IC1"], legs, False) == {
        parse_hole(f"{col}{strip}") for col in "FG" for strip in range(3, 7)
    }
    moved = {**CHIP, "parts": {**CHIP["parts"], "R1": {"1": "G5", "2": "G6"}}}
    assert not any("body covers" in f for f in check(moved, c).faults)
    assert placement_warnings(layout_from_data(moved), board) == [
        "R1 sits under IC1: only if the chip is in a socket and the part is low enough."
    ]
    under = {**CHIP, "links": [*CHIP["links"], ["G2", "G7"]]}
    assert check(under, c).faults == []
    assert placement_warnings(layout_from_data(under), board) == []


def test_a_chip_placed_along_a_strip_is_refused(circuit: Callable[..., CircuitBuilder]) -> None:
    legs = {str(n): f"{'CDEFGHIJ'[n - 1]}8" for n in range(1, 9)}
    result = check({**CHIP, "parts": {**CHIP["parts"], "IC1": legs}}, _two_buffers(circuit))
    assert any("IC1 sits across the strips" in f for f in result.faults)


def test_stripboard_nets_reads_the_board_back(circuit: Callable[..., CircuitBuilder]) -> None:
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    groups = stripboard_nets(layout_from_data(CHIP), board)
    assert groups[("IC1A", "out")] == groups[("IC1A", "-")]  # joined by the link C3-C4
    assert groups[("IC1C", "V-")] == groups[("R2", "2")] == groups["GND"]
    assert groups[("IC1A", "+")] != groups[("IC1B", "out")]  # the cut at F5


def test_every_starter_but_the_kit_builds_gets_its_footprints() -> None:
    """The Aion kits are PCB builds: surface-mount parts and a DIP switch, named plainly."""
    for path in sorted((LIBRARY / "starters").glob("*.json")):
        _, problems = board_parts(load_circuit(path), MODELS, TABLE)
        if "aion" not in path.stem:
            assert problems == [], path.stem
    bd2 = load_circuit(LIBRARY / "starters" / "boss-bd2-aion.json").with_part("Q1", adapter=False)
    _, smd = board_parts(bd2, MODELS, TABLE)
    assert smd == [
        "Q1's 2SK209-GR is surface-mount (SC-59 (S-MINI)): it can't go on a stripboard. "
        "Choose a through-hole model for it, or put it on a TO-92 adapter (its Mounting)."
    ]


def test_a_dip_switch_is_one_board_part_like_a_chip() -> None:
    """D-397: the Bluesbreaker (Aion)'s gain DIP (SW3A, SW3B) goes on as one 4-pin DIP,
    SW3: switch k from pin k (its lug 1) to the pin across (its lug 2), rows 3 holes apart;
    the Same Sky DS04-254 body, 6.20 mm across and 2 × 2.54 + 1.00 = 6.08 mm along."""
    path = LIBRARY / "starters" / "marshall-bluesbreaker-aion.json"
    parts, problems = board_parts(load_circuit(path), MODELS, TABLE)
    assert problems == []
    sw3 = parts["SW3"]
    assert sw3.legs == ("1", "2", "3", "4")
    assert sw3.pins == {"1": ("SW3A", "A1"), "4": ("SW3A", "A2"),
                        "2": ("SW3B", "B1"), "3": ("SW3B", "B2")}  # fmt: skip
    fp = sw3.footprint
    assert (fp.shape, fp.row_holes) == ("dip", 3)
    assert fp.width == pytest.approx(6.20)
    assert fp.length == pytest.approx(6.08)
    legs = dip_legs(4, (0, 0))
    assert leg_problem(sw3, legs, standing=False) is None
    assert body_holes(sw3, legs, standing=False) == {(1, 0), (2, 0), (1, 1), (2, 1)}
    circuit = load_circuit(path)
    laid = start_for_me(None, circuit, MODELS, TABLE, fill=False).layout
    moved = tuple(
        Placed(p.ref, tuple((leg, (x, y + 1)) for leg, (x, y) in p.legs)) if p.ref == "SW3" else p
        for p in laid.parts
    )
    faults = " ".join(check_layout(replace(laid, parts=moved), circuit, MODELS, TABLE).faults)
    assert "SW3's pin 1 (SW3A A1)" in faults  # named like a chip's pin


def test_a_trimmer_is_a_triangle_unless_set_in_line() -> None:
    """D-393: a trimmer is the Bourns 3362P, legs 1 and 3 two holes apart and the wiper a
    hole back between them, turned any way; its ends may be swapped (the part isn't
    mirrored, its outer legs just go on the other nets: it turns the other way to set,
    fine for a trimmer, the user). Its 6.60 × 6.99 mm body covers the hole between 1 and 3
    and the two beside the wiper. Set `inline` it's the 3296W, three legs in a row."""
    tr = Trimmer(ref="TR1", pos=(0, 0), type="trimmer", value=10e3)
    triangle = one_board_part(tr, MODELS, TABLE)
    assert triangle.footprint.shape == "triangle" and triangle.legs == ("1", "2", "3")
    own = triangle_legs(0, (4, 2))
    assert own == {"1": (5, 2), "2": (4, 3), "3": (5, 4)}
    assert triangle_legs(1) == {"1": (2, 1), "2": (1, 0), "3": (0, 1)}  # a quarter clockwise
    assert triangle_legs(0, (4, 2), swapped=True) == {"1": (5, 4), "2": (4, 3), "3": (5, 2)}
    assert all(
        leg_problem(triangle, triangle_legs(t, (3, 3), m), False) is None
        for t in range(4)
        for m in (False, True)
    )
    in_line = {"1": (4, 2), "2": (4, 3), "3": (4, 4)}
    assert leg_problem(triangle, in_line, False) == (
        "TR1's legs: 1 and 3 two holes apart in a line, the wiper (2) a hole back from the "
        "middle of them."
    )
    assert body_holes(triangle, own, False) == {(5, 3), (4, 2), (4, 4)}
    inline = one_board_part(tr.model_copy(update={"style": "inline"}), MODELS, TABLE)
    assert inline.footprint.shape == "inline" and inline.footprint.length == 9.53


def test_bodies_touching_between_holes_or_hanging_off_the_edge_are_warned() -> None:
    """D-394: a triangle trimmer (legs B1, A2, B3; body 6.99 mm across, to 4.77 mm) and a
    100 µF electrolytic (6.3 mm, legs D1, D2; its edge at 4.47 mm) share no hole, so the
    board passes, but their outlines touch by 0.3 mm: a warning. A body more than half a
    hole past the board's edge is warned too; one hole further apart, nothing."""
    tr = one_board_part(Trimmer(ref="TR1", pos=(0, 0), type="trimmer", value=10e3), MODELS, TABLE)
    cap = Capacitor(ref="C1", pos=(0, 0), type="capacitor", value=100e-6, kind="electrolytic")
    c1 = one_board_part(cap, MODELS, TABLE)
    board = {"TR1": tr, "C1": c1}
    trimmer = Placed("TR1", tuple(triangle_legs(0, (0, 0)).items()))

    def at(column: int, columns: int) -> list[str]:
        cap_at = Placed("C1", (("1", (column, 0)), ("2", (column, 1))))
        return [o.text for o in outline_overlaps(Layout(columns, 3, (trimmer, cap_at)), board)]

    assert at(3, 6) == ["TR1 and C1's bodies touch: move one a hole further away if you can."]
    assert at(4, 6) == []
    assert at(4, 5) == [  # C1's edge at 13.31 mm, the board's at 4.5 holes, 11.43 mm
        "C1 hangs past the board's edge: check it clears the enclosure, or move it in."
    ]


def _flat_resistor_and(other: Placed, other_part: Any) -> list[str]:
    """The touching warnings for a flat ¼ W resistor R1 (legs A2, E2: its 6.3 × 2.5 mm body
    centred on C2, 1.93–8.23 mm across and 1.29–3.79 mm down) and `other`."""
    r1 = one_board_part(Resistor(ref="R1", pos=(0, 0), type="resistor", value=10e3), MODELS,
                        TABLE)  # fmt: skip
    board = {"R1": r1, other.ref: other_part}
    flat = Placed("R1", (("1", (0, 1)), ("2", (4, 1))))
    return [o.text for o in outline_overlaps(Layout(8, 6, (flat, other)), board)]


def test_a_flat_resistor_s_body_is_its_length_along_the_legs_not_a_circle() -> None:
    """P6i5: an axial's outline is a box, its length along the legs and its diameter across
    (the table's `diameter` is the footprint's `width`), so a 6.3 mm electrolytic standing
    in D3–D4 (centre 7.62, 6.35 mm) reaches R1's body near its end (2.56 mm from the box,
    under its 3.15 mm radius). A 2.5 mm circle round R1's middle would leave it 0.18 mm
    clear, unwarned. In F3–F4 (centre 12.7 mm) it's past R1's end: nothing."""
    cap = Capacitor(ref="C1", pos=(0, 0), type="capacitor", value=100e-6, kind="electrolytic")
    c1 = one_board_part(cap, MODELS, TABLE)
    assert c1.footprint.diameter == 6.3
    at = lambda column: Placed("C1", (("1", (column, 2)), ("2", (column, 3))))  # noqa: E731
    assert _flat_resistor_and(at(3), c1) == [
        "R1 and C1's bodies touch: move one a hole further away if you can."
    ]
    assert _flat_resistor_and(at(5), c1) == []


def test_flat_resistors_on_neighbouring_strips_are_not_warned() -> None:
    """P6i5 (the user): ¼ W resistors lying flat a strip apart, their 2.5 mm bodies 2.54 mm
    apart, are how every board is built: 0.04 mm clear, never warned (`check._SLACK`)."""
    r2 = one_board_part(Resistor(ref="R2", pos=(0, 0), type="resistor", value=1e3), MODELS,
                        TABLE)  # fmt: skip
    assert _flat_resistor_and(Placed("R2", (("1", (0, 2)), ("2", (4, 2)))), r2) == []
    assert _flat_resistor_and(Placed("R2", (("1", (1, 2)), ("2", (5, 2)))), r2) == []


def test_a_surface_mount_transistor_on_an_adapter_takes_the_to92_footprint() -> None:
    """D-392: the BD-2 (Aion)'s 2SK209s on TO-92 adapters, as Aion's kit builds them: the
    table's TO-92, legs D-S-G (Aion's adapter, the J201's)."""
    bd2 = load_circuit(LIBRARY / "starters" / "boss-bd2-aion.json")
    found, problems = board_parts(bd2, MODELS, TABLE)
    q1 = found["Q1"]
    assert problems == [] and q1.footprint.package == "TO-92"
    assert q1.legs == ("D", "S", "G")
    assert q1.pins == {"D": ("Q1", "D"), "S": ("Q1", "S"), "G": ("Q1", "G")}


# --- Wire it for me (D-375) ----------------------------------------------------------


def test_wire_it_for_me_wires_every_lug_to_a_board_that_passes() -> None:
    """Every off-board part put at its default spot, each lug wired to the nearest free
    hole on a strip of its net only; the same board wires the same way; done twice, the
    second has nothing to do."""
    bare = layout_from_data({**GOOD, "wires": [], "off": {"VR1": [2, -8]}})
    wired = wire_for_me(bare, RANGEMASTER, MODELS, TABLE)
    assert check_layout(wired, RANGEMASTER, MODELS, TABLE).faults == []
    assert dict(wired.spots)["VR1"] == (2, -8)  # put there by hand: kept
    assert set(dict(wired.spots)) == {"VR1", "IN", "OUT", "power"}
    assert wire_for_me(bare, RANGEMASTER, MODELS, TABLE) == wired
    with pytest.raises(WiringError, match="Nothing to wire"):
        wire_for_me(wired, RANGEMASTER, MODELS, TABLE)


def test_a_pad_is_chosen_by_a_wire_s_way_in_not_a_straight_line() -> None:
    """The user, 2026-11-23 (J1 S's wire ran across the board to a pad inside it): from a
    lug above a 10 × 8 board at (5, -6), a hole on strip 2 straight below (7 holes away) is
    dearer than the corner hole A1 (7.8 away): a wire to it goes 5.5 to the edge, then 1.5
    in at 3 each (10), one to A1 7.4 to the edge and 0.5 in (8.9)."""
    lug = (5.0, -6.0)
    assert pad_cost((5, 1), lug, 10, 8) == pytest.approx(5.5 + 3 * 1.5)
    assert pad_cost((0, 0), lug, 10, 8) == pytest.approx(math.hypot(5, 5.5) + 3 * 0.5)
    assert pad_cost((0, 0), lug, 10, 8) < pad_cost((5, 1), lug, 10, 8)
    assert pad_cost((9, 4), (12.0, 4.0), 10, 8) == pytest.approx(2.5 + 3 * 0.5)  # in from the right


def test_wire_it_for_me_leaves_a_net_not_on_the_board() -> None:
    """With C2 not placed, VR1's wiper has no strip to go to: left to wire."""
    parts = {k: v for k, v in GOOD["parts"].items() if k != "C2"}
    bare = layout_from_data({**GOOD, "parts": parts, "wires": []})
    wired = wire_for_me(bare, RANGEMASTER, MODELS, TABLE)
    assert "VR1.2" not in {w.lug for w in wired.wires}
    assert "VR1.1" in {w.lug for w in wired.wires}


def test_drawing_data_carries_each_part_s_markings() -> None:
    """D-378: the Rangemaster's resistors' colour bands (470k yellow violet yellow, 68k blue
    grey orange, gold for 5 %), the electrolytics' − leg, the TO-92-less germanium can and
    the film caps unmarked."""
    rangemaster = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
    board, _ = board_parts(rangemaster, MODELS, TABLE)
    drawn = drawing_data(board, rangemaster)
    assert drawn["R1"]["look"] == {"bands": ["yellow", "violet", "yellow", "gold"]}
    assert drawn["R2"]["look"] == {"bands": ["blue", "grey", "orange", "gold"]}
    assert drawn["C3"]["look"] == {"minus": "2"}
    assert drawn["C1"]["look"] == {} and drawn["Q1"]["look"] == {}
