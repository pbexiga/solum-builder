"""Guidance as the board is built (D-377): marked holes, the ratsnest, suggested cuts and
links, what to place next; on the Rangemaster's hand-made board taken apart."""

from pathlib import Path
from typing import Any

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import hole_name, layout_from_data, parse_hole
from solum.stripboard.check import check_layout, placement_faults
from solum.stripboard.footprints import board_parts
from solum.stripboard.guidance import Guidance, guidance
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def linked(g: Guidance) -> list[list[str]]:
    return [[hole_name(a), hole_name(b)] for a, b in g.links]


def run(data: dict[str, Any]) -> Guidance:
    return guidance(layout_from_data(data), RANGEMASTER, MODELS, TABLE)


def only(*refs: str, **changes: Any) -> dict[str, Any]:
    """The good board with only these parts placed (no wires unless given)."""
    parts = {k: v for k, v in GOOD["parts"].items() if k in refs}
    return {"size": GOOD["size"], "parts": parts, "standing": GOOD["standing"], **changes}


def test_a_finished_board_needs_nothing() -> None:
    g = run(GOOD)
    assert g.ratsnest == [] and g.cuts == [] and g.links == [] and g.next is None


def test_marks_are_the_free_copper_of_a_net_s_own_strips() -> None:
    """Q1 and R1 placed: Q1's base strip (4) is the base's, its free holes marked; the
    holes Q1's and R1's legs sit in are not; an empty strip is nobody's."""
    g = run(only("Q1", "R1"))
    base = g.marks["Q1.B"]
    assert base == [(3, 0, 1), (3, 3, 3), (3, 5, 11)]  # C4 (R1) and E4 (Q1) taken
    every = [run for runs in g.marks.values() for run in runs]
    marked = {(c, s) for s, a, b in every for c in range(a, b + 1)}
    assert parse_hole("C4") not in marked and parse_hole("E3") not in marked
    assert not any(s == 0 for s, _, _ in every)  # strip 1 is empty


def test_a_shorted_strip_is_marked_for_no_net() -> None:
    """Strip 8 uncut carries V- (R1) and GND (R2): no hole on it is marked."""
    g = run(only("R1", "R2"))
    assert all(s != 7 for runs in g.marks.values() for s, _, _ in runs)


def test_the_ratsnest_joins_each_net_s_pieces_by_their_nearest_holes() -> None:
    """C3 and C4 on strip 2 (ground) and R2's ground leg at J8 with G8 cut: ground is in
    two pieces, one strand between the nearest holes; V- likewise without the B link."""
    g = run(only("R1", "R2", "C3", "C4", "Q1", "R3", cuts=["G8"]))
    strands = {(s.net, hole_name(s.a), hole_name(s.b)) for s in g.ratsnest}
    assert ("GND", "I2", "J8") in strands
    assert [s.net for s in g.ratsnest].count("GND") == 1


def test_suggested_cuts_and_links_are_the_hand_made_board_s() -> None:
    """The good board without its cut and links: a cut on strip 8 between R1's V- leg at C8
    and R2's ground leg at J8 (the first free hole, D8), and the two links it had."""
    g = run({**GOOD, "cuts": [], "links": []})
    assert [hole_name(h) for h in g.cuts] == ["D8"]
    assert sorted((hole_name(a), hole_name(b)) for a, b in g.links) == [("B1", "B8"),
                                                                        ("K2", "K8")]  # fmt: skip
    done = layout_from_data({**GOOD, "cuts": ["D8"], "links": linked(g)})
    assert check_layout(done, RANGEMASTER, MODELS, TABLE).ok  # accepted, the board passes


def test_no_cut_is_suggested_where_no_hole_is_free_between_two_nets() -> None:
    """R1's legs moved next to each other on one strip (C8, D8 would be its spacing if
    allowed): nets side by side with no free hole between get no cut."""
    data = only("R1", "R2", parts={"R1": {"1": "C8", "2": "C4"}, "R2": {"1": "D4", "2": "D8"}})
    g = run(data)
    assert all(h[1] != 7 for h in g.cuts)


def test_a_suggested_link_never_passes_over_a_leg_or_under_a_standing_part() -> None:
    g = run({**GOOD, "cuts": [], "links": []})
    cuts = [hole_name(h) for h in g.cuts]
    layout = layout_from_data({**GOOD, "cuts": cuts, "links": linked(g)})
    board = board_parts(RANGEMASTER, MODELS, TABLE)[0]
    assert placement_faults(layout, board, set()) == []


def test_next_follows_the_signal_and_prefers_what_joins_the_board() -> None:
    empty = run({"size": [12, 9]}).next
    assert empty is not None and empty.ref == "C1" and "input" in empty.why
    nxt = run(only("Q1", "R1")).next
    assert nxt is not None and nxt.ref == "C1"  # joins Q1's base, nearest the input
    assert nxt.why.startswith("Next: C1. It joins ") and "(Q1.B)" in nxt.why
    rest = run(only("Q1", "R1", "C1", "C2", "C3", "C4", "R2")).next
    assert rest is not None and rest.ref == "R3"
