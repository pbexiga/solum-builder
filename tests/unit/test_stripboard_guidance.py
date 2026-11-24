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
from solum.stripboard.guidance import Guidance, Kept, guidance
from solum.stripboard.limits import LoudInput
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
    """C3 and C4 on strip 2 (ground) and R2's ground leg at I8 with G8 cut: ground is in
    two pieces, one strand between the nearest holes; V- likewise without the B link."""
    g = run(only("R1", "R2", "C3", "C4", "Q1", "R3", cuts=["G8"]))
    strands = {(s.net, hole_name(s.a), hole_name(s.b)) for s in g.ratsnest}
    assert ("GND", "I2", "I8") in strands
    assert [s.net for s in g.ratsnest].count("GND") == 1


def test_suggested_cuts_and_links_are_the_hand_made_board_s() -> None:
    """The good board without its cut and links: a cut on strip 8 between R1's V- leg at C8
    and R2's ground leg at I8 (the first free hole, D8), and its two links: the ground one
    in the first free column, J, where the hand-made board has it one column on, at K."""
    g = run({**GOOD, "cuts": [], "links": []})
    assert [hole_name(h) for h in g.cuts] == ["D8"]
    assert sorted((hole_name(a), hole_name(b)) for a, b in g.links) == [("B1", "B8"),
                                                                        ("J2", "J8")]  # fmt: skip
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


def test_suggested_links_never_pass_over_each_other() -> None:
    """Base (D5, F1, J4) and ground (F5, H6) both in pieces: the shortest link for each in
    column G overlapped (G1 to G6 over G4 to G5's ends), which the editor then refused.
    Accepting every suggestion must add no placement fault."""
    parts = {"R1": {"1": "D1", "2": "D5"}, "R2": {"1": "F1", "2": "F5"},
             "R3": {"1": "H2", "2": "H6"}, "C1": {"1": "J6", "2": "J4"}}  # fmt: skip
    g = run({"size": [12, 12], "parts": parts})
    assert len(g.links) == 3
    cuts = [hole_name(h) for h in g.cuts]
    layout = layout_from_data({"size": [12, 12], "parts": parts, "cuts": cuts, "links": linked(g)})
    board = board_parts(RANGEMASTER, MODELS, TABLE)[0]
    faults = placement_faults(layout, board, set())
    assert [f for f in faults if not f.endswith("isn't on the board.")] == []


def test_next_follows_the_signal_and_prefers_what_joins_the_board() -> None:
    empty = run({"size": [12, 9]}).next
    assert empty is not None and empty.ref == "C1" and "input" in empty.why
    nxt = run(only("Q1", "R1")).next  # its bypass cap first, kept by its emitter (D-400)
    assert nxt is not None and nxt.why == "Next: C3, by Q1's emitter: its bypass cap."
    nxt = run(only("Q1", "R1", "C3")).next
    assert nxt is not None and nxt.ref == "C1"  # joins Q1's base, nearest the input
    assert nxt.why.startswith("Next: C1. It joins ") and "(Q1.B)" in nxt.why
    rest = run(only("Q1", "R1", "C1", "C2", "C3", "C4", "R2")).next
    assert rest is not None and rest.ref == "R3"


def test_a_net_on_one_strip_either_side_of_another_leg_is_explained() -> None:
    """The base at C4 and J4, C2's leg at F4 between them, cut either side: no link can
    join one strip to itself; the sentence says so and what to move."""
    g = run({"size": [12, 9], "cuts": ["D4", "G4", "D8"],
             "parts": {"R1": {"1": "C8", "2": "C4"}, "R2": {"1": "J4", "2": "J8"},
                       "C2": {"1": "F4", "2": "F6"}}})  # fmt: skip
    assert g.links == []
    assert g.stuck == [
        "Q1.B: R1's leg at C4 and R2's leg at J4 are both on strip 4, with C2's leg at F4 "
        "between them, and a link only joins one strip to another. Move C2 off strip 4, or "
        "join them with a wire across the top."
    ]


def test_a_piece_with_no_free_hole_is_explained() -> None:
    """R1's base leg at A4 with the cut at B4 beside it: its copper is that one hole."""
    g = run({"size": [6, 9], "cuts": ["B4"],
             "parts": {"R1": {"1": "A8", "2": "A4"}, "R2": {"1": "E2", "2": "E6"}}})  # fmt: skip
    assert len(g.stuck) == 1
    assert g.stuck[0].startswith("Q1.B: nothing can join R1's leg at A4 to the rest")


def test_a_blocked_link_names_what_is_in_the_way() -> None:
    """The base on strips 4 and 6 shares columns B to D free; C2 lies across strip 5 between
    them, its legs at B5 and D5, its body over C5."""
    g = run({"size": [5, 9],
             "parts": {"R1": {"1": "A8", "2": "A4"}, "R2": {"1": "E6", "2": "E2"},
                       "C2": {"1": "B5", "2": "D5"}}})  # fmt: skip
    assert g.stuck == [
        "Q1.B: every link that would join R1's leg at A4 and R2's leg at E6 is blocked; the "
        "shortest, B4 to B6, by C2's leg at B5. Move C2, or join them with a wire across the "
        "top."
    ]


def test_nothing_is_stuck_when_the_suggestions_join_everything() -> None:
    assert run({**GOOD, "cuts": [], "links": []}).stuck == []


# --- the guidance follows the placement limits (D-400) ---------------------------------
TS808 = load_circuit(LIBRARY / "starters" / "ts808.json")
TS808_LOUD = [
    LoudInput("IC1B", "+", frozenset({"GND", "V+"}))
]  # as `probe.loud_inputs` finds it (it needs ngspice)
IC1 = {"1": "E3", "2": "E4", "3": "E5", "4": "E6", "8": "H3", "7": "H4", "6": "H5", "5": "H6"}
UNDER = ["F3", "F4", "F5", "F6"]  # the cuts under the chip


def ts808(**data: Any) -> Guidance:
    board = {"size": [20, 12], "parts": {"IC1": IC1}, "cuts": UNDER, **data}
    return guidance(layout_from_data(board), TS808, MODELS, TABLE, TS808_LOUD)


def holes_of(kept: Kept) -> list[str]:
    return [hole_name((c, strip)) for strip, c0, c1 in kept.holes for c in range(c0, c1 + 1)]


def test_a_part_kept_by_a_placed_pin_is_marked_only_by_that_pin() -> None:
    """The TS808 with IC1 placed: C4 (on pin 6's net, with D1 and D2: reach 4) is marked
    on pin 6's own copper only, I5 to L5 (none between the chip's rows: its body, D-401);
    R11 by pin 2, the chip on its right: C4 and D4."""
    g = ts808()
    assert g.kept["C4"] == Kept("1", "IC1B.-", g.kept["C4"].holes, None)
    assert holes_of(g.kept["C4"]) == ["I5", "J5", "K5", "L5"]
    assert holes_of(g.kept["R11"]) == ["C4", "D4"]
    assert "R1" not in g.kept  # kept by no pin


def test_no_free_hole_by_the_pin_names_what_is_in_the_way() -> None:
    g = ts808(cuts=[*UNDER, "D4"])
    assert g.kept["R11"].holes == []
    assert g.kept["R11"].blocked == (
        "No free hole by IC1's pin 2: the cut at D4 and the cut at F4 are in the way. Move "
        "one, or place R11 elsewhere and it will show as a warning."
    )


def test_place_next_names_a_part_a_placed_pin_keeps_first_saying_why() -> None:
    g = ts808()
    assert g.next is not None
    assert g.next.why == "Next: C2, by IC1's pin 5: the high-gain stage's input."
    assert guidance(layout_from_data({"size": [20, 12], "parts": {}}), TS808, MODELS, TABLE,
                    TS808_LOUD).kept == {}  # fmt: skip


def test_a_suggested_link_keeps_clear_of_a_sensitive_part_when_it_can() -> None:
    """D-402: with a link taken out, the shortest link back is suggested; with the holes of
    that link kept clear of another net's sensitive part, a link down another free column
    comes first."""
    from solum.stripboard.check import read_layout
    from solum.stripboard.guidance import _linking, suggested_cuts

    data = {**GOOD, "links": [["B1", "B8"]]}
    r = read_layout(layout_from_data(data), RANGEMASTER, MODELS, TABLE)
    cuts = suggested_cuts(r)
    (first,) = _linking(r, cuts)[1]
    column = first[0][0]
    zone = {(column, y): "elsewhere" for y in range(r.layout.strips)}
    (other,) = _linking(r, cuts, zone)[1]
    assert other[0][0] != column
    assert abs(other[1][1] - other[0][1]) >= abs(first[1][1] - first[0][1])
