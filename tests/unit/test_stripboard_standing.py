"""Standing resistors and diodes, the board's choice (D-403): Never, When needed (the
default) or Prefer, for *Lay it out for me* and its starting board; kept with the board, so
Try another uses it; and a standing part's outline, checked for touching like any other
body. When needed, a part stands only where lying flat it can't do as well, never to save
room (the user)."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from solum.circuit.io import load_circuit
from solum.circuit.schema import Capacitor, Resistor
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard import compact
from solum.stripboard.board import Layout, Placed, StandUp
from solum.stripboard.check import check_layout, outline_overlaps
from solum.stripboard.compact import (
    Found,
    board_of,
    finish,
    lay_flat,
    positions,
    problem,
    search,
    standing_unneeded,
)
from solum.stripboard.footprints import one_board_part
from solum.stripboard.start import stand_order, start_for_me

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
TS808 = load_circuit(LIBRARY / "starters" / "ts808.json")
FUZZ_FACE = load_circuit(LIBRARY / "starters" / "fuzz-face.json")
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
TONE_BENDER = load_circuit(LIBRARY / "starters" / "tone-bender-mk2.json")
CHOICES: tuple[StandUp, ...] = ("never", "needed", "prefer")


def standing(layout: Layout) -> list[str]:
    return sorted(p.ref for p in layout.parts if p.standing)


def empty(stand_up: StandUp) -> Layout:
    return Layout(0, 0, (), stand_up=stand_up)


def test_start_a_board_stands_a_part_only_when_preferred() -> None:
    """With no placement limits (D-410) nothing needs a part standing in Start a board:
    When needed lies flat as Never does (the full layout stands one where lying flat
    can't fit); Prefer stands parts (the Fuzz Face's R4)."""
    assert [stand_order(s) for s in CHOICES] == ["none", "none", "first"]
    for choice in CHOICES:
        made = start_for_me(empty(choice), FUZZ_FACE, MODELS, TABLE).layout
        assert made.stand_up == choice and check_layout(made, FUZZ_FACE, MODELS, TABLE).ok
        assert (len(standing(made)) > 0) == (choice == "prefer")


def test_the_search_ranks_standing_parts_before_size() -> None:
    """When needed, a board's key counts its standing parts first, so a smaller board with a
    part standing loses to a flat one: room isn't a reason to stand a part."""

    def d(stood: int, area: int) -> SimpleNamespace:
        return SimpleNamespace(stood=stood, area=area, cuts=(), count=0, length=0)

    assert compact.key(d(0, 120)) < compact.key(d(1, 100))


def test_build_a_full_layout_follows_the_choice_the_same_board_each_time() -> None:
    """Never stands nothing (no standing shape is tried); When needed stands fewer parts
    than Prefer on the TS808; Prefer stands them freely, as before D-403. The search's
    base never stands parts. The same choice gives the same board twice."""
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
    assert len(found["needed"]) < len(found["prefer"])


def test_the_flat_attempt_is_never_s_board_for_its_seed() -> None:
    """D-403: a search that picks no standing shape on a When needed problem finds the
    board Never's search finds with the same seed (the standing shapes come after the
    flat ones, and the moves draw alike), so a run with it can't do worse than Never's
    attempt with that seed."""
    needed = problem(empty("needed"), TS808, MODELS, TABLE)
    never = problem(empty("never"), TS808, MODELS, TABLE)
    flat, own = search(needed, 3000, 1, flat=True), search(never, 3000, 1)
    assert flat is not None and own is not None
    assert not standing(board_of(needed, flat))
    assert replace(board_of(needed, flat), stand_up="never") == board_of(never, own)
    assert flat.key == own.key


def test_a_full_layout_s_standing_parts_a_limit_or_warning_doesn_t_need_lie_flat() -> None:
    """When needed, the search prefers fewer standing parts only among the boards it saw,
    so finishing lays flat again each standing part that can lie flat (a leg kept in its
    hole) with no problem (`lay_flat`): a board searched as Prefer (standing free) keeps
    none that `standing_unneeded` finds, and its key is no worse."""
    needed = problem(empty("needed"), TS808, MODELS, TABLE)
    free = problem(empty("prefer"), TS808, MODELS, TABLE)
    got = search(free, 3000, 1)
    assert got is not None
    pos = positions(needed, replace(board_of(free, got), stand_up="needed"))
    assert standing_unneeded(needed, pos)  # Prefer stands parts nothing needs
    flat = lay_flat(needed, Found(got.key, 1, 0, 0, 0, 0, tuple(pos.items())))
    assert standing_unneeded(needed, dict(flat.pos)) == []


def test_try_another_uses_the_board_s_own_choice() -> None:
    """The search reads the choice off the board it's given (`stand_up` None): a board
    made with Never is searched again with no standing shape."""
    kept = start_for_me(empty("never"), RANGEMASTER, MODELS, TABLE).layout
    pb = problem(kept, RANGEMASTER, MODELS, TABLE)
    assert pb.stand_up == "never"
    assert not any(v.standing for vs in pb.variants.values() for v in vs)


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
