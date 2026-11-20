"""Editing the board by hand (D-374): place, move, take back, cut, link, each refused in a
sentence when it can't be made; auto-grow fitting the board; the shorts an edit makes. On
the hand-made Rangemaster layout (`tests/fixtures/stripboard/rangemaster.yaml`): strip 8 is
V- left of the cut at G8 and GND right of it."""

from dataclasses import replace
from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import (
    Hole,
    Layout,
    Placed,
    Wire,
    layout_data,
    layout_from_data,
    parse_hole,
)
from solum.stripboard.check import check_layout, progress, runs, shorts
from solum.stripboard.edit import BoardEdit, Edited, EditError, edit_layout
from solum.stripboard.footprints import board_parts
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
BOARD = board_parts(RANGEMASTER, MODELS, TABLE)[0]
GOOD = layout_from_data(load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml"))


def place(ref: str, legs: dict[str, str | Hole], standing: bool = False) -> BoardEdit:
    at = tuple((leg, parse_hole(h) if isinstance(h, str) else h) for leg, h in legs.items())
    return BoardEdit("place", ref, at, standing)


def holes_edit(kind: str, *names: str) -> BoardEdit:
    return BoardEdit(kind, holes=tuple(parse_hole(n) for n in names))  # type: ignore[arg-type]


def made(layout: Layout, change: BoardEdit, *, grow: bool = True, started: bool = True) -> Edited:
    return edit_layout(layout, change, BOARD, started=started, grow=grow)


def edit(layout: Layout, change: BoardEdit, *, grow: bool = True) -> Layout:
    return made(layout, change, grow=grow).layout


def without(ref: str) -> Layout:
    return replace(GOOD, parts=tuple(p for p in GOOD.parts if p.ref != ref))


def legs(layout: Layout, ref: str) -> dict[str, str]:
    return layout_data(layout)["parts"][ref]


def test_a_part_from_the_tray_lands_where_it_is_put() -> None:
    board = edit(without("R2"), place("R2", {"1": "J4", "2": "J8"}))
    assert legs(board, "R2") == {"1": "J4", "2": "J8"}
    assert check_layout(board, RANGEMASTER, MODELS, TABLE).ok


def test_a_placed_part_moves_in_its_place_in_the_list() -> None:
    moved = edit(GOOD, place("C1", {"1": "F4", "2": "F6"}))  # turned round
    assert legs(moved, "C1") == {"1": "F4", "2": "F6"}
    assert [p.ref for p in moved.parts] == [p.ref for p in GOOD.parts]


def test_a_part_goes_back_to_the_tray() -> None:
    board = edit(GOOD, BoardEdit("remove", "R2"))
    assert "R2" not in layout_data(board)["parts"]
    with pytest.raises(EditError, match="R2 isn't on the board"):
        edit(board, BoardEdit("remove", "R2"))


def test_a_part_that_doesnt_go_on_the_board_is_refused() -> None:
    with pytest.raises(EditError, match="VR1 doesn't go on the board"):
        edit(GOOD, place("VR1", {"1": "L1", "2": "L2", "3": "L3"}))


def test_legs_as_the_footprint_doesnt_allow_are_refused() -> None:
    with pytest.raises(EditError, match="R2 lying flat needs its legs at least 4 holes apart"):
        edit(without("R2"), place("R2", {"1": "J4", "2": "J6"}))
    with pytest.raises(EditError, match="R3 standing has its legs 1 hole apart"):
        edit(without("R3"), place("R3", {"1": "G3", "2": "G6"}, standing=True))


def test_two_legs_in_a_hole_or_a_body_over_a_leg_are_refused() -> None:
    with pytest.raises(EditError, match="share hole J4"):
        edit(without("R1"), place("R1", {"1": "J8", "2": "J4"}))
    with pytest.raises(EditError, match="R1's body covers E3, where Q1 goes"):
        edit(without("R1"), place("R1", {"1": "E2", "2": "E6"}))


def test_a_fault_already_there_doesnt_refuse_another_edit() -> None:
    """Two legs already sharing a hole (a board from a file) don't stop R2 moving."""
    crowded = replace(GOOD, parts=tuple(
        replace(p, legs=(("1", parse_hole("J4")), ("2", parse_hole("J8"))))
        if p.ref == "R1" else p for p in GOOD.parts
    ))  # fmt: skip
    board = edit(crowded, place("R2", {"1": "L3", "2": "L7"}))
    assert legs(board, "R2") == {"1": "L3", "2": "L7"}


def test_past_the_edge_is_refused_with_auto_grow_off() -> None:
    with pytest.raises(EditError, match="past the board's right edge: turn Auto-grow on"):
        edit(without("R2"), place("R2", {"1": "M4", "2": "M8"}), grow=False)
    with pytest.raises(EditError, match="past the board's top edge"):
        edit(GOOD, BoardEdit("link", holes=((11, -2), (11, 1))), grow=False)


def test_auto_grow_takes_in_the_margin_and_says_how_far_it_moved() -> None:
    right = made(without("R2"), place("R2", {"1": "M4", "2": "M8"}))
    assert (right.layout.columns, right.layout.strips) == (13, 9) and right.shift == (0, 0)
    left = made(without("R2"), place("R2", {"1": (-1, 3), "2": (-1, 7)}))
    assert (left.layout.columns, left.layout.strips, left.shift) == (13, 9, (1, 0))
    assert legs(left.layout, "R2") == {"1": "A4", "2": "A8"}
    assert legs(left.layout, "Q1") == {"E": "F3", "B": "F4", "C": "F5"}


def test_the_first_placement_makes_the_board_what_is_on_it() -> None:
    first = made(Layout(14, 10, ()), place("R2", {"1": "C3", "2": "C7"}), started=False)
    assert (first.layout.columns, first.layout.strips, first.shift) == (1, 5, (-2, -2))
    assert legs(first.layout, "R2") == {"1": "A1", "2": "A5"}


def test_auto_grow_off_keeps_an_empty_board_its_start_size() -> None:
    first = made(Layout(14, 10, ()), place("R2", {"1": "C3", "2": "C7"}), started=False,
                 grow=False)  # fmt: skip
    assert (first.layout.columns, first.layout.strips) == (14, 10)


def test_cuts_are_made_and_mended_by_hand() -> None:
    board = edit(GOOD, holes_edit("cut", "J5"))
    assert parse_hole("J5") in board.cuts
    assert parse_hole("G8") not in edit(GOOD, holes_edit("uncut", "G8")).cuts
    with pytest.raises(EditError, match="R2 is in J4: a cut there would take its copper away"):
        edit(GOOD, holes_edit("cut", "J4"))
    with pytest.raises(EditError, match="a cut at G8 already"):
        edit(GOOD, holes_edit("cut", "G8"))
    with pytest.raises(EditError, match="no cut at J5"):
        edit(GOOD, holes_edit("uncut", "J5"))
    with pytest.raises(EditError, match="the board"):
        edit(GOOD, BoardEdit("cut", holes=((-1, 2),)))


def test_links_are_laid_and_lifted_down_a_column() -> None:
    board = edit(GOOD, holes_edit("link", "L1", "L3"))
    assert layout_data(board)["links"][-1] == ["L1", "L3"]
    assert layout_data(edit(GOOD, holes_edit("unlink", "B8", "B1")))["links"] == [["K2", "K8"]]
    with pytest.raises(EditError, match="A link runs down a column"):
        edit(GOOD, holes_edit("link", "L1", "M1"))
    with pytest.raises(EditError, match="passes over Q1 at E3"):
        edit(GOOD, holes_edit("link", "E2", "E6"))
    with pytest.raises(EditError, match="no link from L1 to L3"):
        edit(GOOD, holes_edit("unlink", "L1", "L3"))


def test_shorts_are_the_pairs_of_nets_the_board_joins() -> None:
    assert shorts(GOOD, RANGEMASTER, MODELS, TABLE) == {}
    mended = edit(GOOD, holes_edit("uncut", "G8"))
    found = shorts(mended, RANGEMASTER, MODELS, TABLE)
    assert list(found) == [frozenset({"GND", "V-"})]
    assert (
        "joined on the board, but the circuit doesn't connect them"
        in found[frozenset({"GND", "V-"})]
    )


def test_the_shorted_copper_is_drawn_red_in_runs() -> None:
    assert runs({(1, 0), (2, 0), (3, 0), (5, 0), (0, 1)}) == [(0, 1, 3), (0, 5, 5), (1, 0, 0)]
    assert progress(GOOD, RANGEMASTER, MODELS, TABLE).shorted == []
    mended = edit(GOOD, holes_edit("uncut", "G8"))
    red = progress(mended, RANGEMASTER, MODELS, TABLE).shorted
    assert (7, 0, 11) in red  # strip 8, A to L


def test_clear_takes_off_whatever_the_circuit_no_longer_has() -> None:
    """D-376: a part, an off-board part beside the board and a wire to its lug, all gone
    from the schematic, cleared in one edit; the rest kept as it was."""
    stale = replace(
        GOOD,
        parts=(*GOOD.parts, Placed("R9", (("1", parse_hole("L1")), ("2", parse_hole("L5"))))),
        spots=(("VR9", (2, -8)),),
        wires=(*GOOD.wires, Wire("VR9.1", parse_hole("L6")), Wire("VR1.3", None, "VR9.2")),
    )
    items = {"VR1": ("VR1.1", "VR1.2", "VR1.3"), "IN": ("IN.out", "IN.S"),
             "OUT": ("OUT.in", "OUT.S"), "power": ("V-", "GND")}  # fmt: skip
    cleared = edit_layout(stale, BoardEdit("clear"), BOARD, started=True, grow=False,
                          items=items)  # fmt: skip
    assert cleared.layout == GOOD
    with pytest.raises(EditError, match="Nothing on the board is gone from the circuit"):
        edit_layout(GOOD, BoardEdit("clear"), BOARD, started=True, grow=False, items=items)


def test_clear_keeps_a_part_the_circuit_has_but_cant_place_now() -> None:
    board = {ref: part for ref, part in BOARD.items() if ref != "C1"}
    r9 = Placed("R9", (("1", parse_hole("L1")), ("2", parse_hole("L5"))))
    stale = replace(GOOD, parts=(*GOOD.parts, r9), wires=())
    kept = edit_layout(stale, BoardEdit("clear"), board, started=True, grow=False,
                       known={"C1"})  # fmt: skip
    assert kept.layout == replace(GOOD, wires=())
