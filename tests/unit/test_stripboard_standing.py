"""Standing resistors and diodes, the board's choice (D-403): Never, When it saves room
(the default) or Prefer, for Start a board, Fill the rest, Tidy up and Build a full
layout; kept with the board, so Try another and a later Tidy up use it; and a standing
part's outline, checked for touching like any other body."""

from dataclasses import replace
from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.circuit.schema import Capacitor, Resistor
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Layout, Placed, StandUp
from solum.stripboard.check import check_layout, outline_overlaps
from solum.stripboard.compact import finish, problem, search
from solum.stripboard.footprints import one_board_part
from solum.stripboard.start import stand_order, start_for_me
from solum.stripboard.tidy import key, tidy_up

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
TS808 = load_circuit(LIBRARY / "starters" / "ts808.json")
FUZZ_FACE = load_circuit(LIBRARY / "starters" / "fuzz-face.json")
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
CHOICES: tuple[StandUp, ...] = ("never", "room", "prefer")


def standing(layout: Layout) -> list[str]:
    return sorted(p.ref for p in layout.parts if p.standing)


def empty(stand_up: StandUp) -> Layout:
    return Layout(0, 0, (), stand_up=stand_up)


def test_start_a_board_stands_parts_only_when_preferred_and_fill_when_allowed() -> None:
    """Start a board is roomy and predictable: parts stand only when the choice is Prefer
    (the Fuzz Face's three resistors, its board 126 holes for 162); Fill the rest tries
    standing after lying flat when it saves room, first when preferred."""
    assert [stand_order(s, fill=False) for s in CHOICES] == ["none", "none", "first"]
    assert [stand_order(s, fill=True) for s in CHOICES] == ["none", "last", "first"]
    for choice in CHOICES:
        made = start_for_me(empty(choice), FUZZ_FACE, MODELS, TABLE, fill=False).layout
        assert made.stand_up == choice and check_layout(made, FUZZ_FACE, MODELS, TABLE).ok
        assert (len(standing(made)) > 0) == (choice == "prefer")
    flat = start_for_me(None, FUZZ_FACE, MODELS, TABLE, fill=False).layout
    stood = start_for_me(None, FUZZ_FACE, MODELS, TABLE, fill=False, stand_up="prefer").layout
    assert flat.columns * flat.strips == 162 and stood.columns * stood.strips == 126


def test_build_a_full_layout_follows_the_choice_the_same_board_each_time() -> None:
    """Never stands nothing (no standing shape is tried); When it saves room stands fewer
    parts than Prefer on the TS808 (each costs a column's worth of holes); Prefer stands
    them freely, as before D-403. The search's base never stands parts. The same
    choice gives the same board twice."""
    found = {}
    for choice in CHOICES:
        pb = problem(empty(choice), TS808, MODELS, TABLE)
        variants = [v for vs in pb.variants.values() for v in vs]
        assert any(v.standing for v in variants) == (choice != "never")
        assert not standing(pb.base) and pb.base.stand_up == choice
        board = finish(pb, search(pb, 2000, 1), MODELS, TABLE).layout
        again = finish(pb, search(pb, 2000, 1), MODELS, TABLE).layout
        assert board == again and board.stand_up == choice
        found[choice] = standing(board)
    assert found["never"] == []
    assert len(found["room"]) < len(found["prefer"])


def test_try_another_uses_the_board_s_own_choice() -> None:
    """The search reads the choice off the board it's given (`stand_up` None): a board
    made with Never is searched again with no standing shape."""
    kept = start_for_me(empty("never"), RANGEMASTER, MODELS, TABLE, fill=False).layout
    pb = problem(kept, RANGEMASTER, MODELS, TABLE)
    assert pb.stand_up == "never"
    assert not any(v.standing for vs in pb.variants.values() for v in vs)


@pytest.mark.parametrize(("choice", "stood"), [("never", []), ("room", []), ("prefer", ["R3"])])
def test_tidy_up_stands_a_part_as_the_choice_allows(choice: StandUp, stood: list[str]) -> None:
    """On the Rangemaster's Start a board (12 × 9): Prefer stands R3 up (the board no
    bigger); When it saves room doesn't (it saves less than a column); Never doesn't try.
    The choice is kept with the board, and None means the board's own."""
    base = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False).layout
    tidied = tidy_up(base, RANGEMASTER, MODELS, TABLE, stand_up=choice).layout
    assert standing(tidied) == stood and tidied.stand_up == choice
    assert check_layout(tidied, RANGEMASTER, MODELS, TABLE).ok
    own = tidy_up(replace(base, stand_up=choice), RANGEMASTER, MODELS, TABLE)
    assert own.layout == tidied


def test_tidy_up_s_measure_counts_standing_parts_by_the_choice() -> None:
    """When it saves room, each standing part counts as a column's worth of holes (the
    board's strips); preferred, the more standing the tidier; never, they don't count."""
    part = Placed("R1", (("1", (0, 0)), ("2", (0, 1))), True)
    board = Layout(4, 9, (part,))
    assert key(board)[0] == 36 + 9 and key(board)[3] == 0  # the default: room
    assert key(Layout(4, 9, (part,), stand_up="never"))[0] == 36
    assert key(Layout(4, 9, (part,), stand_up="room"))[0] == 36 + 9
    assert key(Layout(4, 9, (part,), stand_up="prefer"))[3] == -1


def test_a_standing_part_is_checked_for_touching() -> None:
    """D-403: a standing ¼ W resistor's body over its first leg (A2), its lead bent over
    to B2: a box 2.5 mm wide from the body's far side to the lead's. A 6.3 mm electrolytic
    in B3–B4 (centre 2.54, 6.35 mm) reaches it (2.56 mm from the box, under its 3.15 mm
    radius); another standing resistor a strip down (2.5 mm bodies 2.54 mm apart) doesn't."""
    r1 = one_board_part(Resistor(ref="R1", pos=(0, 0), type="resistor", value=10e3), MODELS,
                        TABLE)  # fmt: skip
    r2 = one_board_part(Resistor(ref="R2", pos=(0, 0), type="resistor", value=1e3), MODELS,
                        TABLE)  # fmt: skip
    cap = Capacitor(ref="C1", pos=(0, 0), type="capacitor", value=100e-6, kind="electrolytic")
    board = {"R1": r1, "R2": r2, "C1": one_board_part(cap, MODELS, TABLE)}
    stood = Placed("R1", (("1", (0, 1)), ("2", (1, 1))), True)

    def touching(other: Placed) -> list[tuple[str, str]]:
        return [o.parts for o in outline_overlaps(Layout(6, 6, (stood, other)), board)]

    assert touching(Placed("C1", (("1", (1, 2)), ("2", (1, 3))))) == [("R1", "C1")]
    assert touching(Placed("R2", (("1", (0, 2)), ("2", (1, 2))), True)) == []
