"""*Start for me* (D-387): Start over and Fill the rest on the Rangemaster, each board
checked; what Fill the rest can't join is named; nothing to do says so."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Layout, layout_from_data
from solum.stripboard.check import check_layout
from solum.stripboard.footprints import board_parts
from solum.stripboard.start import StartError, shapes, start_for_me
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def without(*refs: str, **changes: Any) -> Layout:
    """The hand-made board with these parts back in the tray and no wires."""
    parts = {k: v for k, v in GOOD["parts"].items() if k not in refs}
    return layout_from_data({**GOOD, "parts": parts, "wires": [], **changes})


def test_start_over_lays_out_a_checked_board_the_same_every_run() -> None:
    first = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False)
    again = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False)
    assert first == again and first.left == ()
    assert check_layout(first.layout, RANGEMASTER, MODELS, TABLE).ok
    board = first.layout
    assert {p.ref for p in board.parts} == set(GOOD["parts"])
    assert board.columns * board.strips <= 12 * 10  # about as tight as by hand (11×9)
    assert {w.lug for w in board.wires} >= {"VR1.1", "VR1.2", "VR1.3", "IN.out", "OUT.in"}


def test_start_over_replaces_the_board_but_keeps_the_on_off_choices() -> None:
    """What's on the board goes (its parts, cuts, links, wires); the parts' On / Off the
    board choices stay."""
    old = layout_from_data({**GOOD, "where": {"VR1": "off-board"}})
    started = start_for_me(old, RANGEMASTER, MODELS, TABLE, fill=False).layout
    assert started.where == old.where
    assert started.parts != old.parts and not started.cuts & old.cuts - started.cuts
    assert check_layout(started, RANGEMASTER, MODELS, TABLE).ok


@pytest.mark.parametrize("tray", [("R2",), ("C3", "R3"), ("Q1",), ("C1", "C2", "C3", "C4")])
def test_fill_the_rest_keeps_what_s_placed_and_lays_out_the_tray(tray: tuple[str, ...]) -> None:
    before = without(*tray)
    filled = start_for_me(before, RANGEMASTER, MODELS, TABLE, fill=True)
    board = filled.layout
    assert filled.left == () and check_layout(board, RANGEMASTER, MODELS, TABLE).ok
    assert board.parts[: len(before.parts)] == before.parts  # nothing moved
    assert before.cuts <= board.cuts and board.links[: len(before.links)] == before.links
    assert {p.ref for p in board.parts} == set(GOOD["parts"])
    assert board.columns >= before.columns and board.strips > before.strips  # laid out below


def test_fill_the_rest_with_nothing_to_do_says_so() -> None:
    with pytest.raises(StartError, match="Nothing to fill"):
        start_for_me(layout_from_data(GOOD), RANGEMASTER, MODELS, TABLE, fill=True)


def test_fill_the_rest_names_a_piece_it_can_t_join_and_moves_nothing() -> None:
    """Q1 alone, every other hole of its strips cut: no free hole for a link to start
    from, so its emitter's and base's nets (each with legs in the tray) are named, and Q1
    stays where it is; the board doesn't pass (the progress check shows the rest)."""
    boxed = {"size": [3, 3], "parts": {"Q1": {"E": "B1", "B": "B2", "C": "B3"}},
             "cuts": ["A1", "C1", "A2", "C2", "A3", "C3"]}  # fmt: skip
    filled = start_for_me(layout_from_data(boxed), RANGEMASTER, MODELS, TABLE, fill=True)
    assert [s.split(":")[0] for s in filled.left] == ["Q1.B", "Q1.E"]
    assert all("no free column" in s for s in filled.left)
    assert filled.layout.parts[0] == layout_from_data(boxed).parts[0]
    assert not check_layout(filled.layout, RANGEMASTER, MODELS, TABLE).ok


def test_a_part_that_can_t_go_on_a_board_is_named() -> None:
    """The BD-2 (Aion)'s Q1 off its adapter (D-392): surface-mount, named."""
    bd2 = load_circuit(LIBRARY / "starters" / "boss-bd2-aion.json").with_part("Q1", adapter=False)
    with pytest.raises(StartError, match="surface-mount"):
        start_for_me(None, bd2, MODELS, TABLE, fill=False)


def test_shapes_stand_each_part_across_the_strips() -> None:
    """A chip either way up; a transistor's legs down a column either way round; a flat
    resistor from its least span to three holes more, either way round."""
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    q1 = shapes(board["Q1"])
    assert all({x for x, _ in s.legs.values()} == {0} for s in q1)
    assert q1[0].legs == {"E": (0, 0), "B": (0, 1), "C": (0, 2)}
    assert q1[1].legs == {"C": (0, 0), "B": (0, 1), "E": (0, 2)}
    r1 = shapes(board["R1"])
    flat = board["R1"].footprint.flat
    assert [s.legs["2"][1] + s.legs["1"][1] for s in r1[::2]] == [
        flat,
        flat + 1,
        flat + 2,
        flat + 3,
    ]
