"""*Tidy up* (D-388): a board made smaller and still checked, the same every run; a board
that doesn't pass is refused; wrongly placed parts are asked about, then laid out again."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Layout, layout_from_data
from solum.stripboard.check import check_layout, misfits, read_layout
from solum.stripboard.size import insert_line
from solum.stripboard.start import start_for_me
from solum.stripboard.tidy import MendFirst, TidyError, joins, key, tidy_up
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def good(**changes: Any) -> Layout:
    return layout_from_data({**GOOD, **changes})


def board_of(layout: Layout) -> Any:
    return read_layout(layout, RANGEMASTER, MODELS, TABLE).board


def test_a_start_for_me_board_comes_out_smaller_checked_and_the_same_every_run() -> None:
    started = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False).layout
    first = tidy_up(started, RANGEMASTER, MODELS, TABLE)
    assert first == tidy_up(started, RANGEMASTER, MODELS, TABLE) and first.mended == ()
    board = first.layout
    assert check_layout(board, RANGEMASTER, MODELS, TABLE).ok
    before, after = key(started), key(board)
    assert all(a <= b for a, b in zip(after[:3], before[:3], strict=True))
    assert board.columns * board.strips < started.columns * started.strips


def test_an_empty_column_inside_the_board_is_taken_out() -> None:
    """The hand-made board (12×9) with an empty column put in at G: back to 12 or fewer."""
    wide = insert_line(good(), board_of(good()), "column", 6)
    assert wide.columns == 13 and check_layout(wide, RANGEMASTER, MODELS, TABLE).ok
    board = tidy_up(wide, RANGEMASTER, MODELS, TABLE).layout
    assert board.columns <= 12 and check_layout(board, RANGEMASTER, MODELS, TABLE).ok
    assert len(board.cuts) <= 1 and len(board.links) <= 2


def test_a_board_tidied_already_can_t_be_made_smaller() -> None:
    started = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False).layout
    tidied = tidy_up(started, RANGEMASTER, MODELS, TABLE).layout
    with pytest.raises(TidyError, match="Couldn't make this board smaller"):
        tidy_up(tidied, RANGEMASTER, MODELS, TABLE)


def test_a_board_that_doesn_t_pass_is_refused_saying_why() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "R3"}
    with pytest.raises(TidyError, match="passes the check: R3 isn't on the board"):
        tidy_up(good(parts=parts), RANGEMASTER, MODELS, TABLE)
    with pytest.raises(TidyError, match="nothing on the board"):
        tidy_up(Layout(5, 5, ()), RANGEMASTER, MODELS, TABLE)


def test_a_wrongly_placed_part_is_asked_about_then_laid_out_again() -> None:
    """R2 on the collector's and the output's strips (its nets are the base and GND): named
    first; with `mend` it goes back to the tray and comes out laid out, the board checked.
    A part placed right is never moved for it."""
    moved = good(parts={**GOOD["parts"], "R2": {"1": "J5", "2": "J9"}})
    assert misfits(moved, RANGEMASTER, MODELS, TABLE) == ["R2"]
    with pytest.raises(MendFirst, match="R2 is placed wrongly") as asked:
        tidy_up(moved, RANGEMASTER, MODELS, TABLE)
    assert asked.value.refs == ["R2"]
    mended = tidy_up(moved, RANGEMASTER, MODELS, TABLE, mend=True)
    assert mended.mended == ("R2",)
    assert check_layout(mended.layout, RANGEMASTER, MODELS, TABLE).ok


def test_a_part_the_wrong_way_round_is_a_misfit() -> None:
    turned = good(parts={**GOOD["parts"], "C3": {"1": "H3", "2": "H2"}})
    assert misfits(turned, RANGEMASTER, MODELS, TABLE) == ["C3"]
    assert misfits(good(), RANGEMASTER, MODELS, TABLE) == []


def test_joins_name_an_either_way_part_by_its_ref() -> None:
    """R1 turned (its legs swapped) joins the same when it may go either way round."""
    swapped = good(parts={**GOOD["parts"], "R1": {"1": "C4", "2": "C8"}})
    assert joins(swapped) != joins(good())
    assert joins(swapped, frozenset({"R1"})) == joins(good(), frozenset({"R1"}))
