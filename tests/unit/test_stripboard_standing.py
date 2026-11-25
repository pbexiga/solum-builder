"""Standing resistors and diodes, the board's choice (D-403): Never, When needed (the
default) or Prefer, for Start a board, Fill the rest, Tidy up and Build a full layout;
kept with the board, so Try another and a later Tidy up use it; and a standing part's
outline, checked for touching like any other body. When needed, a part stands only where
lying flat it breaks a placement limit (or a warning, in the full layout), never to save
room (the user)."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Capacitor, Circuit, Resistor
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard import compact
from solum.stripboard.board import Layout, Placed, StandUp
from solum.stripboard.check import check_layout, outline_overlaps, read_layout
from solum.stripboard.compact import board_of, finish, problem, search
from solum.stripboard.footprints import one_board_part
from solum.stripboard.limits import LoudInput, broken_limits, placement_limits
from solum.stripboard.start import stand_order, start_for_me
from solum.stripboard.tidy import key as tidy_key
from solum.stripboard.tidy import stand_where_needed, tidy_up

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
TS808 = load_circuit(LIBRARY / "starters" / "ts808.json")
FUZZ_FACE = load_circuit(LIBRARY / "starters" / "fuzz-face.json")
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
# the TS808's high-gain stages' inputs as `probe.loud_inputs` finds them (it needs ngspice)
TS808_LOUD = [LoudInput("Q1", "B", frozenset({"V+", "GND"})),
              LoudInput("IC1B", "+", frozenset({"V+", "GND"}))]  # fmt: skip
CHOICES: tuple[StandUp, ...] = ("never", "needed", "prefer")


def standing(layout: Layout) -> list[str]:
    return sorted(p.ref for p in layout.parts if p.standing)


def empty(stand_up: StandUp) -> Layout:
    return Layout(0, 0, (), stand_up=stand_up)


def broken(layout: Layout, circuit: Circuit) -> int:
    """The placement limits `layout` breaks, the TS808's high-gain inputs counted."""
    r = read_layout(layout, circuit, MODELS, TABLE)
    limits = placement_limits(circuit, connect(circuit), r.board, TS808_LOUD)
    return len(broken_limits(layout, limits))


def test_start_a_board_stands_a_part_only_when_it_meets_a_limit_lying_flat_can_t() -> None:
    """The Fuzz Face lies flat when needed (standing R4 would only save room: Prefer's
    board is smaller, 60 holes for 100); the TS808 stands parts when needed, only because
    they meet a limit lying flat breaks: fewer limits broken, on a bigger board."""
    assert [stand_order(s) for s in CHOICES] == ["none", "needed", "first"]
    for choice in CHOICES:
        made = start_for_me(empty(choice), FUZZ_FACE, MODELS, TABLE, fill=False).layout
        assert made.stand_up == choice and check_layout(made, FUZZ_FACE, MODELS, TABLE).ok
        assert (len(standing(made)) > 0) == (choice == "prefer")
    flat = start_for_me(empty("never"), TS808, MODELS, TABLE, False, TS808_LOUD).layout
    needed = start_for_me(empty("needed"), TS808, MODELS, TABLE, False, TS808_LOUD).layout
    assert not standing(flat) and standing(needed)
    assert broken(needed, TS808) < broken(flat, TS808)
    assert needed.columns * needed.strips > flat.columns * flat.strips  # room isn't why


def test_the_search_ranks_standing_parts_after_limits_and_warnings_before_size() -> None:
    """When needed, a board's key counts its standing parts third (after limits broken,
    then noisy links and strips alongside), so a smaller board with a part standing loses
    to a flat one, and a part stands only where it meets a limit or clears a warning;
    a standing part costs less than a warning (`STAND` under `QUIET`, `APART`)."""

    def d(broken: int, noisy: int, stood: int, area: int) -> SimpleNamespace:
        return SimpleNamespace(broken=broken, noisy=noisy, apart=0, stood=stood, area=area,
                               far=0, cuts=(), count=0, length=0)  # fmt: skip

    assert compact.key(d(0, 0, 0, 120)) < compact.key(d(0, 0, 1, 100))  # room isn't a reason
    assert compact.key(d(0, 0, 1, 120)) < compact.key(d(1, 0, 0, 100))  # a limit met is
    assert compact.key(d(0, 0, 1, 120)) < compact.key(d(0, 1, 0, 100))  # so is a warning
    assert min(compact.QUIET, compact.APART, compact.LIMIT) > compact.STAND


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
    attempt with that seed on limits or warnings, which rank first."""
    needed = problem(empty("needed"), TS808, MODELS, TABLE)
    never = problem(empty("never"), TS808, MODELS, TABLE)
    flat, own = search(needed, 3000, 1, flat=True), search(never, 3000, 1)
    assert flat is not None and own is not None
    assert not standing(board_of(needed, flat))
    assert replace(board_of(needed, flat), stand_up="never") == board_of(never, own)
    assert flat.key == own.key


def test_try_another_uses_the_board_s_own_choice() -> None:
    """The search reads the choice off the board it's given (`stand_up` None): a board
    made with Never is searched again with no standing shape."""
    kept = start_for_me(empty("never"), RANGEMASTER, MODELS, TABLE, fill=False).layout
    pb = problem(kept, RANGEMASTER, MODELS, TABLE)
    assert pb.stand_up == "never"
    assert not any(v.standing for vs in pb.variants.values() for v in vs)


@pytest.mark.parametrize(("choice", "stood"), [("never", []), ("needed", []), ("prefer", ["R3"])])
def test_tidy_up_stands_a_part_as_the_choice_says(choice: StandUp, stood: list[str]) -> None:
    """On the Rangemaster's Start a board (12 × 9): Prefer stands R3 up (the board no
    bigger); When needed doesn't (no limit broken nor warning for it to clear: standing
    would only save room); Never doesn't try. The choice is kept with the board, and None
    means the board's own."""
    base = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False).layout
    tidied = tidy_up(base, RANGEMASTER, MODELS, TABLE, stand_up=choice).layout
    assert standing(tidied) == stood and tidied.stand_up == choice
    assert check_layout(tidied, RANGEMASTER, MODELS, TABLE).ok
    own = tidy_up(replace(base, stand_up=choice), RANGEMASTER, MODELS, TABLE)
    assert own.layout == tidied


def test_when_needed_tidy_up_stands_a_part_only_where_it_clears_a_fault() -> None:
    """`stand_where_needed`: R1 lies flat across A1–A5 (legs 1 and 2, a strip apart is
    the hole below); a fault cleared only with leg 2 brought to A2 (leg 1 kept in A1,
    the other stood beside it): that stand is kept, and nothing more. With no fault, or a
    fault no stand clears, the board is left as it was; a board that wouldn't pass the
    check isn't taken."""
    r1 = one_board_part(Resistor(ref="R1", pos=(0, 0), type="resistor", value=10e3), MODELS,
                        TABLE)  # fmt: skip
    board = {"R1": r1}
    flat = Layout(3, 6, (Placed("R1", (("1", (0, 0)), ("2", (0, 4)))),))

    def met(layout: Layout) -> bool:
        return dict(layout.parts[0].legs)["2"] == (0, 1)

    stood = stand_where_needed(flat, lambda _: True, lambda m: 0 if met(m) else 1, board)
    assert standing(stood) == ["R1"] and met(stood)
    assert stand_where_needed(flat, lambda _: True, lambda _: 0, board) == flat  # room alone
    assert stand_where_needed(flat, lambda _: True, lambda _: 1, board) == flat  # no help
    assert stand_where_needed(flat, lambda _: False, lambda m: 0 if met(m) else 1, board) == flat


def test_tidy_up_s_measure_counts_standing_parts_only_when_preferred() -> None:
    """Preferred, the more standing the tidier; otherwise they don't count."""
    part = Placed("R1", (("1", (0, 0)), ("2", (0, 1))), True)
    assert tidy_key(Layout(4, 9, (part,)))[:4] == (36, 0, 0, 0)  # the default: needed
    assert tidy_key(Layout(4, 9, (part,), stand_up="never"))[3] == 0
    assert tidy_key(Layout(4, 9, (part,), stand_up="prefer"))[3] == -1


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
