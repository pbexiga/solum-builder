"""The stripboard board model, footprints and check (D-367): hand-made layouts, good and
broken, each broken one refused with a sentence naming its fault."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import (
    BoardError,
    Layout,
    Link,
    hole_name,
    layout_data,
    layout_from_data,
    parse_hole,
    segments,
)
from solum.stripboard.check import Checked, check_layout, off_board_ends, stripboard_nets
from solum.stripboard.footprints import board_parts, body_holes, dip_legs, leg_problem
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
    assert (r1.shape, r1.flat, r1.stand, r1.length) == ("axial", 4, 1, 6.3)  # ¼ W
    assert (c1.shape, c1.steps, c1.length) == ("radial", (2,), 7.2)  # 5n film, WIMA MKS 2
    assert (c3.footprint.diameter, c3.footprint.steps) == (5, (1,))  # 47µ: 5 mm, NIC NRWS
    assert q1.footprint.order == ("E", "B", "C")  # OC44: e b c in a line
    assert q1.pins["B"] == ("Q1", "B")


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
    assert leg_problem(r1, {"1": (2, 7), "2": (2, 3)}, False) is None  # 4 apart, flat
    assert "at least 4 holes" in (leg_problem(r1, {"1": (2, 6), "2": (2, 3)}, False) or "")
    assert leg_problem(r1, {"1": (2, 4), "2": (2, 3)}, True) is None  # stood up
    assert "one row or one column" in (leg_problem(r1, {"1": (3, 7), "2": (2, 3)}, False) or "")
    assert "2 holes apart" in (leg_problem(c1, {"1": (2, 4), "2": (2, 3)}, False) or "")
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


def test_off_board_wires_are_each_pot_lug_the_input_the_output_and_the_supply() -> None:
    nets = connect(RANGEMASTER)
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    assert off_board_ends(RANGEMASTER, nets, board) == {
        "IN.out": "in", "VR1.1": "V-", "VR1.2": "C2.1", "VR1.3": "Q1.C", "OUT.in": "out",
        "GND": "GND", "V-": "V-",
    }  # fmt: skip


def test_a_missed_cut_is_refused() -> None:
    result = check(edited(cuts=[]))
    assert result.faults == [
        "R1's leg at C8 and R2's leg at J8 are joined on the board, but the circuit doesn't "
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
        "C3's + leg at H2 and R2's leg at J8 aren't connected on the board, but the circuit "
        "joins them."
    ]


def test_a_transistor_turned_round_is_refused() -> None:
    result = check(edited(parts={"Q1": {"E": "E5", "B": "E4", "C": "E3"}}))
    assert "Q1's emitter at E5" in " ".join(result.faults)


def test_a_missing_pad_or_a_pad_for_nothing_is_refused() -> None:
    pads = {k: v for k, v in GOOD["pads"].items() if k != "D1"}
    assert "There's no pad for VR1 lug 1." in check(edited(pads=pads)).faults
    wrong = check(edited(pads={**GOOD["pads"], "L1": ["VR2.1"]}))
    assert "Pad L1 goes to 'VR2.1', which isn't an off-board wire this circuit needs." in (
        wrong.faults
    )


def test_missing_extra_and_off_board_parts_are_named() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "C4"}
    assert "C4 isn't on the board." in check(edited(parts=parts) | {"parts": parts}).faults
    extra = check(edited(parts={"VR1": {"1": "L1", "2": "L2", "3": "L3"}}))
    assert "VR1 goes off the board: wire it to pads instead." in extra.faults


def test_two_legs_in_a_hole_or_a_body_over_a_leg_is_refused() -> None:
    shared = check(edited(parts={"R3": {"1": "H3", "2": "G2"}}))
    assert "R3 and C3 share hole H3." in shared.faults
    covered = check(edited(parts={"R2": {"1": "C4", "2": "C8"}, "R1": {"1": "C8", "2": "C4"}}))
    assert any("share hole" in f for f in covered.faults)
    over = check(edited(parts={"Q1": {"E": "C5", "B": "C6", "C": "C7"}}))  # under R1's body
    assert "R1's body covers C5, where Q1 goes." in over.faults


def test_a_link_may_run_under_a_flat_resistor_but_not_over_a_leg() -> None:
    under = edited(links=[*GOOD["links"], ["D3", "D9"]], cuts=["G8"])
    assert not any("runs under" in f for f in check(under).faults)
    flat_r1 = check(edited(links=[["B1", "B8"], ["K2", "K8"], ["C5", "C7"]]))
    assert not any("runs under" in f for f in flat_r1.faults)
    over = check(edited(links=[["B1", "B8"], ["K2", "K8"], ["E2", "E6"]]))
    assert "The link from E2 to E6 passes over Q1 at E3." in over.faults


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
    "pads": {"D1": ["V+"], "D2": ["GND"]},
}


def test_a_chip_layout_passes(circuit: Callable[..., CircuitBuilder]) -> None:
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    assert board["IC1"].pins["8"] == ("IC1C", "V+") and board["IC1"].pins["5"] == ("IC1B", "+")
    assert check(CHIP, c).faults == []


def test_a_missed_cut_under_a_chip_is_named(circuit: Callable[..., CircuitBuilder]) -> None:
    result = check({**CHIP, "cuts": ["F3", "F4", "F6"]}, _two_buffers(circuit))
    assert result.faults == ["The strip under IC1 isn't cut between pins 3 and 6 (strip 5)."]


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
    _, smd = board_parts(load_circuit(LIBRARY / "starters" / "boss-ds1-aion.json"), MODELS, TABLE)
    assert smd[0] == (
        "D9's APT1608SURCK is surface-mount (1.6 × 0.8 mm SMD chip (0603)): it can't go on "
        "a stripboard. Choose a through-hole model for it."
    )
    path = LIBRARY / "starters" / "marshall-bluesbreaker-aion.json"
    _, dip = board_parts(load_circuit(path), MODELS, TABLE)
    assert dip == ["There's no board size for DIP switches (SW3) yet."]  # once, not per pole
