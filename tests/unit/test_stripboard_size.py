"""The board's size (D-372): what's used, Trim, a line inserted or taken out, auto-grow's
fit, an empty board's starting size. On the hand-made Rangemaster layout, which must still
pass the check after every change that's allowed."""

from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import (
    Layout,
    Wire,
    column_name,
    hole_name,
    layout_data,
    layout_from_data,
    parse_hole,
)
from solum.stripboard.check import check_layout
from solum.stripboard.footprints import board_parts
from solum.stripboard.size import (
    SizeError,
    box,
    fit,
    insert_line,
    remove_line,
    start_size,
    trim,
    used_box,
    used_holes,
)
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
BOARD = board_parts(RANGEMASTER, MODELS, TABLE)[0]
GOOD = layout_from_data(load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml"))


def passes(layout: Layout) -> bool:
    return check_layout(layout, RANGEMASTER, MODELS, TABLE).ok


def legs(layout: Layout, ref: str) -> dict[str, str]:
    return layout_data(layout)["parts"][ref]


def test_used_holes_are_legs_bodies_cuts_links_and_wires() -> None:
    used = used_holes(GOOD, BOARD)
    assert used[parse_hole("E4")] == "Q1"
    assert used[parse_hole("G8")] == "the cut at G8"
    assert used[parse_hole("B5")] == "the link from B1 to B8"  # passed over
    assert used[parse_hole("A6")] == "the wire at A6"
    assert box(used) == (0, 0, 10, 8)  # A1 to K9: column L is empty
    assert box([]) is None
    assert used_box(GOOD, BOARD) == box(used)  # the quick box, no sentences
    assert used_box(Layout(5, 5, ()), BOARD) is None


def test_trim_takes_off_the_empty_edge_column() -> None:
    trimmed = trim(GOOD, BOARD)
    assert (trimmed.columns, trimmed.strips) == (11, 9)
    assert trimmed.parts == GOOD.parts  # nothing moves: the empty column was at the right
    assert passes(trimmed)


def test_an_empty_board_cant_be_trimmed() -> None:
    with pytest.raises(SizeError, match="nothing on the board"):
        trim(Layout(10, 6, ()), BOARD)


def test_a_column_at_the_left_moves_everything_along() -> None:
    grown = insert_line(GOOD, BOARD, "column", 0)
    assert (grown.columns, grown.strips) == (13, 9)
    assert legs(grown, "Q1") == {"E": "F3", "B": "F4", "C": "F5"}
    assert layout_data(grown)["cuts"] == ["H8"]
    assert passes(grown)


def test_a_column_between_two() -> None:
    grown = insert_line(GOOD, BOARD, "column", 5)  # before F
    assert legs(grown, "Q1") == {"E": "E3", "B": "E4", "C": "E5"}  # before it: stays
    assert legs(grown, "C1") == {"1": "G6", "2": "G4"}  # from F on: along one
    assert passes(grown)


def test_a_strip_stretches_resistors_and_links_across_it() -> None:
    grown = insert_line(GOOD, BOARD, "strip", 6)  # before strip 7
    assert legs(grown, "R1") == {"1": "C9", "2": "C4"}
    assert layout_data(grown)["links"] == [["B1", "B9"], ["K2", "K9"]]
    assert passes(grown)


def test_a_line_through_a_part_that_cant_stretch_is_refused() -> None:
    with pytest.raises(SizeError, match="before strip 5 would go through Q1"):
        insert_line(GOOD, BOARD, "strip", 4)  # between Q1's legs
    with pytest.raises(SizeError, match="through C1"):
        insert_line(GOOD, BOARD, "strip", 5)  # between a radial cap's legs


def test_an_empty_column_can_be_taken_out() -> None:
    smaller = remove_line(GOOD, BOARD, "column", 11)
    assert (smaller.columns, smaller.strips) == (11, 9)
    assert passes(smaller)


def test_a_line_that_isnt_empty_names_whats_on_it() -> None:
    with pytest.raises(SizeError, match="Column A isn't empty: the wire at A1 is on it"):
        remove_line(GOOD, BOARD, "column", 0)
    with pytest.raises(SizeError, match="Column G isn't empty: C3 is on it"):
        remove_line(GOOD, BOARD, "column", 6)
    with pytest.raises(SizeError, match="no strip 10"):
        remove_line(GOOD, BOARD, "strip", 9)
    with pytest.raises(SizeError, match="at least one column"):
        remove_line(Layout(1, 3, ()), BOARD, "column", 0)


def test_a_strip_with_only_a_link_passing_and_a_body_across_comes_out() -> None:
    grown = insert_line(GOOD, BOARD, "strip", 6)
    assert remove_line(grown, BOARD, "strip", 6) == GOOD  # R1 and the links shrink back


def test_a_cut_on_a_removed_strip_goes_with_it() -> None:
    cut = replace(insert_line(GOOD, BOARD, "strip", 9), cuts=GOOD.cuts | {parse_hole("D10")})
    assert remove_line(cut, BOARD, "strip", 9) == GOOD


@given(st.sampled_from(["column", "strip"]), st.integers(0, 12))
def test_insert_then_remove_gives_the_board_back(axis: str, at: int) -> None:
    try:
        grown = insert_line(GOOD, BOARD, axis, at)  # type: ignore[arg-type]
    except SizeError:
        return
    assert remove_line(grown, BOARD, axis, at) == GOOD  # type: ignore[arg-type]


def test_fit_grows_to_take_in_whats_in_the_margin() -> None:
    after = replace(GOOD, wires=(*GOOD.wires, Wire("VR1.9", (-2, -1))))
    grown = fit(GOOD, after, BOARD)
    assert (grown.columns, grown.strips) == (14, 10)
    assert legs(grown, "Q1") == {"E": "G4", "B": "G5", "C": "G6"}


def test_fit_shrinks_only_by_the_lines_the_edit_emptied() -> None:
    """Taking every wire off column A empties it: the board loses it. Column L was empty
    before (as if added by hand): it stays."""
    after = replace(GOOD, wires=tuple(w for w in GOOD.wires if not w.hole or w.hole[0]))
    shrunk = fit(GOOD, after, BOARD)
    assert (shrunk.columns, shrunk.strips) == (11, 9)
    assert legs(shrunk, "Q1") == {"E": "D3", "B": "D4", "C": "D5"}


def test_the_first_placement_makes_the_board_what_is_on_it() -> None:
    first = Layout(11, 8, (replace(GOOD.parts[0]),))  # Q1 at E3 to E5
    board = fit(None, first, BOARD)
    assert (board.columns, board.strips) == (1, 3)
    assert legs(board, "Q1") == {"E": "A1", "B": "A2", "C": "A3"}


def test_fit_keeps_the_size_when_nothing_is_left() -> None:
    assert fit(GOOD, Layout(12, 9, ()), BOARD) == Layout(12, 9, ())


def test_an_empty_board_starts_with_room_wider_than_tall() -> None:
    columns, strips = start_size(BOARD)
    assert (columns, strips) == (11, 8)  # 8 parts, 34 holes: 85 holes, 3 to 2
    assert start_size({}) == (10, 6)  # the least


def test_a_hole_in_the_margin_has_no_column_letters() -> None:
    assert column_name(-1) == "" and hole_name((-2, 0)) == "1"
