"""*Build a full layout* (D-399): the search from Start a board's base, made smaller,
wired and checked; the same board for the same seeds; the On / Off choices kept."""

import json
from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import circuit_to_dict, load_circuit
from solum.circuit.schema import Circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Hole, Layout, layout_from_data
from solum.stripboard.check import check_layout
from solum.stripboard.compact import (
    CompactError,
    Found,
    State,
    _row,
    best_of,
    finish,
    problem,
    search,
    start_pos,
)
from solum.stripboard.footprints import board_parts
from solum.stripboard.start import shapes
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
FUZZ_FACE = load_circuit(LIBRARY / "starters" / "fuzz-face.json")
TS808 = load_circuit(LIBRARY / "starters" / "ts808.json")
GOOD: dict[str, Any] = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def built(circuit: Circuit, steps: int, seeds: range,
          layout: Layout | None = None) -> tuple[Layout, Found | None]:  # fmt: skip
    pb = problem(layout, circuit, MODELS, TABLE)
    best = best_of(search(pb, steps, seed) for seed in seeds)
    return finish(pb, best, MODELS, TABLE).layout, best


@pytest.mark.parametrize(("circuit", "steps", "most"),
                         [(RANGEMASTER, 5000, 56), (FUZZ_FACE, 20_000, 77)])  # fmt: skip
def test_a_small_circuit_comes_out_small_and_checked(
    circuit: Circuit, steps: int, most: int
) -> None:
    """Rangemaster 6×8 and Fuzz Face 8×7 in the P6h1 spike (CP-SAT: 40 and 48 holes);
    Start a board's base is 10×9 and 18×9. When needed (the default), nothing stands that
    could lie flat (D-403), so the Fuzz Face takes 11×7 in these few steps."""
    board, best = built(circuit, steps, range(1, 3))
    assert best is not None and best.key[0] == 0  # no part standing
    assert board.columns * board.strips <= most
    assert (board.columns, board.strips) == (best.columns, best.strips)
    assert check_layout(board, circuit, MODELS, TABLE).ok


def test_the_same_seeds_give_the_same_board_and_other_seeds_another() -> None:
    first, _ = built(TS808, 2000, range(1, 2))
    assert first == built(TS808, 2000, range(1, 2))[0]
    other, _ = built(TS808, 2000, range(2, 3))
    assert other != first
    for board in (first, other):
        assert check_layout(board, TS808, MODELS, TABLE).ok


def test_the_on_off_choices_and_the_notes_are_kept_and_the_board_replaced() -> None:
    data = {**GOOD, "parts": {k: v for k, v in GOOD["parts"].items() if k != "R2"},
            "where": {"R2": "off-board"}, "notes": [{"text": "Mind the bias"}]}  # fmt: skip
    plain = json.loads(json.dumps(data))  # the YAML's leg names are numbers
    circuit = Circuit.model_validate({**circuit_to_dict(RANGEMASTER), "stripboard": plain})
    old = layout_from_data(data)
    board, _ = built(circuit, 3000, range(1, 2), old)
    assert board.where == old.where and board.notes == old.notes
    assert "R2" not in {p.ref for p in board.parts} and "R2" in dict(board.spots)
    assert check_layout(board, circuit, MODELS, TABLE).ok


def test_nothing_better_than_the_base_gives_the_base_back() -> None:
    pb = problem(None, RANGEMASTER, MODELS, TABLE)
    done = finish(pb, None, MODELS, TABLE)
    assert done.fell_back and done.layout == pb.base


def test_stopping_early_keeps_the_best_so_far() -> None:
    """None while every board seen had a problem."""
    pb = problem(None, TS808, MODELS, TABLE)
    asked: list[int] = []

    def going(step: int, best: Found | None) -> bool:
        asked.append(step)
        return step < 512

    best = search(pb, 100_000, 1, going)
    assert asked == [0, 256, 512, 512]  # told the steps done at the end
    assert best is None or best.columns * best.strips < pb.base.columns * pb.base.strips


def test_a_strip_s_pieces_cuts_and_shorts() -> None:
    """Nets 1, 1, 2 at columns 0, 2, 5: one cut in the gap's middle (3 or 4: the middle of
    two is the second); a no-connect (-1) shares any strip; 2 and 3 side by side: a short."""
    row = _row({0: 1, 2: 1, 5: 2, 7: -1, 9: 2})
    assert row.cuts == (4,) and row.shorts == 0
    assert [(n, lo, hi) for n, lo, hi in row.pieces][1] == (2, 5, 10**6)
    assert _row({0: 2, 1: 3}).shorts == 1


def test_parts_can_t_be_moved_onto_each_other() -> None:
    pb = problem(None, RANGEMASTER, MODELS, TABLE)
    st = State(pb, start_pos(pb))
    taken: dict[Hole, str] = dict(st.occ)
    a, b = pb.refs[:2]
    _, x, y = st.pos[b]
    assert st.move({a: (st.pos[a][0], x, y)}) is None or a == b
    assert st.occ == taken  # refused: nothing changed


def test_a_board_whose_parts_share_a_hole_is_refused() -> None:
    pb = problem(None, RANGEMASTER, MODELS, TABLE)
    pos = start_pos(pb)
    a, b = pb.refs[:2]
    with pytest.raises(CompactError, match="share a hole"):
        State(pb, {**pos, a: (pos[a][0], pos[b][1], pos[b][2])})


def test_every_shape_adds_lying_along_a_strip_standing_and_a_trimmer_turned() -> None:
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    r1 = board["R1"]
    across, every = shapes(r1), shapes(r1, every=True, stand="last")
    assert len(every) == 2 * len(across) + 4  # along a strip too; standing, either way round
    assert all(not s.standing for s in across) and sum(s.standing for s in every) == 4
    assert not any(s.standing for s in shapes(r1, every=True))  # D-403: Never
    first = shapes(r1, stand="first")
    assert [s.standing for s in first] == [True, True] + [False] * len(across)  # Prefer
    assert [s.standing for s in shapes(r1, stand="last")][-2:] == [True, True]
    assert any({y for _, y in s.legs.values()} == {0} for s in every)
    assert all({x for x, _ in s.legs.values()} == {0} for s in across)
    mode = load_circuit(LIBRARY / "starters" / "tone-bender-mk2-mode.json")
    trimmer = board_parts(mode, MODELS, TABLE)[0]["TR1"]
    assert (len(shapes(trimmer)), len(shapes(trimmer, every=True))) == (4, 8)  # D-393
