"""The builder's decisions on bodies touching (P6h4): kept with the board, matched to the
overlaps by the two parts and the amount, dropped when the overlap ends or changes. On
D-394's case (`tests/fixtures/circuits/old/schema-v39.json`): a triangle trimmer TR1 (legs
B1, A2, B3) and a 6.3 mm electrolytic C1 (D1, D2) whose outlines run 0.3 mm into each
other."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.circuit.schema import Resistor
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import (
    EDGE,
    BoardError,
    Decision,
    Layout,
    decision_data,
    decision_from_data,
    decision_problem,
    layout_data,
    layout_from_data,
    parse_hole,
)
from solum.stripboard.check import (
    Overlap,
    covers,
    decided,
    decision_words,
    kept_decisions,
    outline_overlaps,
    progress,
)
from solum.stripboard.edit import BoardEdit, EditError, edit_layout
from solum.stripboard.footprints import board_parts, one_board_part, outline_overlap

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
V39 = load_circuit(REPO / "tests/fixtures/circuits/old/schema-v39.json")
BOARD = board_parts(V39, MODELS, TABLE)[0]
assert V39.stripboard is not None
LAYOUT = V39.stripboard.layout()
HINTS = (
    "TR1's adjusting screw must stay reachable from above.",
    "TR1 is about 4.88 mm tall (typical: check yours).",
    "C1 is about 11 mm tall (typical: check yours).",
)
TALLER = Decision(("C1", "TR1"), "taller", 0.3, part="C1", mm=3.0, note="sleeve the leg")


def edit(layout: Layout, change: BoardEdit) -> Layout:
    return edit_layout(layout, change, BOARD, started=True, grow=False).layout


def test_outlines_overlap_by_how_far_they_run_into_each_other() -> None:
    """Two 6 mm circles 5 mm apart: 1 mm; a 3 mm radius 2 mm from a box: 1 mm (4 mm: 1 mm
    apart); a circle's centre inside a box, 0.5 mm in: radius plus 0.5; two boxes: the
    lesser overlap; apart: 0 or less."""
    circle = (-3.0, -3.0, 3.0, 3.0, 3.0)
    assert outline_overlap(circle, (2.0, -3.0, 8.0, 3.0, 3.0)) == pytest.approx(1.0)
    assert outline_overlap(circle, (2.0, -1.0, 9.0, 1.0, 0.0)) == pytest.approx(1.0)
    assert outline_overlap((4.0, -1.0, 9.0, 1.0, 0.0), circle) == pytest.approx(-1.0)
    assert outline_overlap(circle, (-0.5, -5.0, 9.0, 5.0, 0.0)) == pytest.approx(3.5)
    assert outline_overlap((0, 0, 4, 4, 0), (3, 1, 9, 2, 0)) == pytest.approx(1.0)
    assert outline_overlap((0, 0, 4, 4, 0), (5, 0, 9, 4, 0)) <= 0


def test_a_v39_board_has_no_decisions_and_saves_none() -> None:
    """v40 added `overlaps`: a v39 board has none, so its overlap is still a warning, and an
    empty list isn't written."""
    assert V39.schema_ == 40 and LAYOUT.overlaps == ()
    assert outline_overlaps(LAYOUT, BOARD) == [Overlap(("TR1", "C1"), 0.3, (
        "TR1 and C1's bodies touch between the holes (0.3 mm): one would have to stand "
        "taller. Move one a hole further away if you can."
    ), HINTS, {"TR1": 12.0, "C1": 6.0})]  # fmt: skip
    assert "overlaps" not in circuit_to_dict(V39)["stripboard"]


def test_a_decision_is_kept_in_the_board_s_section_of_the_file() -> None:
    """Saved in `stripboard.overlaps` with only what was said, and read back the same."""
    board = {**layout_data(LAYOUT), "overlaps": [decision_data(TALLER)]}
    saved = circuit_to_dict(parse_circuit({**circuit_to_dict(V39), "stripboard": board}))
    assert saved["stripboard"]["overlaps"] == [{
        "parts": ["C1", "TR1"], "fix": "taller", "part": "C1", "mm": 3.0,
        "note": "sleeve the leg", "overlap_mm": 0.3,
    }]  # fmt: skip
    again = parse_circuit(saved).stripboard
    assert again is not None and again.layout().overlaps == (TALLER,)
    bent = {"parts": ["TR1", "C1"], "fix": "bent", "part": "TR1", "toward": "left",
            "overlap_mm": 0.31}  # fmt: skip
    assert decision_from_data(bent) == Decision(("TR1", "C1"), "bent", 0.3, "TR1", None, "left")


@pytest.mark.parametrize(
    ("data", "said"),
    [
        ({"parts": ["C1", "C1"], "fix": "accept"}, "names the two parts"),
        ({"parts": ["edge", "C1"], "fix": "accept"}, "names the two parts"),
        ({"parts": ["C1", "TR1"], "fix": "glue"}, "stand one taller, bend one"),
        ({"parts": ["C1", "edge"], "fix": "taller", "part": "C1"}, "accept it with a note"),
        ({"parts": ["C1", "edge"], "fix": "bent", "part": "C1", "toward": "up"}, "with a note"),
        ({"parts": ["C1", "TR1"], "fix": "taller", "part": "R1"}, "Say which of C1 and TR1"),
        ({"parts": ["C1", "TR1"], "fix": "taller"}, "Say which of C1 and TR1 to stand"),
        ({"parts": ["C1", "TR1"], "fix": "bent", "part": "C1"}, "Say which way C1 bends"),
        ({"parts": ["C1", "TR1"], "fix": "bent", "part": "C1", "toward": "in"}, "which way"),
        ({"parts": ["C1", "TR1"], "fix": "taller", "part": "C1", "mm": -1}, "above 0"),
        ({"parts": ["C1", "TR1"], "fix": "accept", "mm": 2}, "above 0"),
        ({"parts": ["C1", "TR1"], "fix": "accept", "part": "C1"}, "names no part or side"),
        ({"parts": ["C1", "TR1"], "fix": "taller", "part": "C1", "toward": "up"}, "no part or"),
    ],
)
def test_a_decision_that_makes_no_sense_is_refused_in_words(
    data: dict[str, Any], said: str
) -> None:
    """The edge takes only Accept (the user, 2026-11-23); a fix names one of the two; a
    bend says which way; a height is a length above 0, and only for standing taller."""
    with pytest.raises(BoardError, match=said):
        decision_from_data({**data, "overlap_mm": 0.3})
    negative = replace(TALLER, overlap_mm=-1)
    assert decision_problem(negative) == "An overlap's amount is 0 mm or more."
    with pytest.raises(BoardError):
        layout_from_data({**layout_data(LAYOUT), "overlaps": [{**data, "overlap_mm": 0.3}]})


def test_a_decision_covers_the_same_two_by_the_same_amount_either_way_round() -> None:
    """To 0.1 mm; by another amount it's a new overlap (the user, 2026-11-24)."""
    touching = Overlap(("TR1", "C1"), 0.3, "")
    assert covers(TALLER, touching)
    assert covers(replace(TALLER, overlap_mm=0.4), touching)
    assert not covers(replace(TALLER, overlap_mm=0.5), touching)
    assert not covers(replace(TALLER, parts=("C1", "C2")), touching)
    with_it = replace(LAYOUT, overlaps=(TALLER,))
    assert decided(with_it, [touching]) == ([], [TALLER])
    assert decided(with_it, []) == ([], [])


def test_deciding_keeps_the_amount_now_and_replaces_an_earlier_decision() -> None:
    """`decide` takes the board's amount, whatever was sent; deciding the same two again
    replaces it; `undecide` forgets it; two that don't touch can't be decided."""
    once = edit(LAYOUT, BoardEdit("decide", decision=replace(TALLER, overlap_mm=0)))
    assert once.overlaps == (TALLER,)
    accept = Decision(("TR1", "C1"), "accept", 0, note="fine")
    twice = edit(once, BoardEdit("decide", decision=accept))
    assert twice.overlaps == (replace(accept, overlap_mm=0.3),)
    assert edit(twice, BoardEdit("undecide", "C1", to="TR1")).overlaps == ()
    with pytest.raises(EditError, match="no decision on C1 and TR1"):
        edit(LAYOUT, BoardEdit("undecide", "C1", to="TR1"))
    apart = edit(LAYOUT, BoardEdit("place", "C1", (("1", (4, 0)), ("2", (4, 1)))))
    with pytest.raises(EditError, match="TR1 and C1 don't touch now"):
        edit(apart, BoardEdit("decide", decision=replace(accept, parts=("TR1", "C1"))))


def test_moving_a_part_drops_a_decision_its_overlap_no_longer_matches() -> None:
    """C1 a column further away: the overlap ends, the decision goes; any other edit keeps
    it; a decision at another amount than the board's now is dropped (the user,
    2026-11-24: drop it)."""
    kept = replace(LAYOUT, overlaps=(TALLER,))
    assert edit(kept, BoardEdit("cut", holes=(parse_hole("F3"),))).overlaps == (TALLER,)
    moved = edit(kept, BoardEdit("place", "C1", (("1", (4, 0)), ("2", (4, 1)))))
    assert moved.overlaps == ()
    assert kept_decisions(replace(kept, overlaps=(replace(TALLER, overlap_mm=0.6),)), BOARD) == (
        replace(kept, overlaps=())
    )
    assert kept_decisions(kept, BOARD) is kept


def test_the_edge_is_decided_by_accepting() -> None:
    """C1 at column E of a 5-column board hangs 1.9 mm past its edge: Accept with a note."""
    out = Layout(5, 3, tuple(p if p.ref != "C1" else replace(p, legs=(("1", (4, 0)), ("2", (4, 1))))
                             for p in LAYOUT.parts))  # fmt: skip
    assert [(o.parts, o.mm) for o in outline_overlaps(out, BOARD)] == [(("C1", EDGE), 1.9)]
    note = Decision(("C1", EDGE), "accept", 0, note="the box is deep")
    done = edit(out, BoardEdit("decide", decision=note))
    assert done.overlaps == (replace(note, overlap_mm=1.9),)


def test_progress_parts_the_undecided_overlaps_from_the_decided() -> None:
    """The board's check lists the overlaps still to decide apart from the decisions that
    cover the rest; neither is a fault."""
    before = progress(LAYOUT, V39, MODELS, TABLE)
    assert [o.parts for o in before.overlaps] == [("TR1", "C1")] and before.decided == []
    after = progress(replace(LAYOUT, overlaps=(TALLER,)), V39, MODELS, TABLE)
    assert after.overlaps == [] and [d.decision for d in after.decided] == [TALLER]
    assert after.decided[0].text == "C1: stand 3 mm taller (clears TR1); sleeve the leg."
    assert after.faults == before.faults


def test_a_decision_in_words_for_the_warnings_and_the_build_sheet() -> None:
    """Each kind of fix said plainly, the other part it clears named, the note after it."""
    assert decision_words(replace(TALLER, note="")) == "C1: stand 3 mm taller (clears TR1)."
    assert decision_words(replace(TALLER, mm=None, note="")) == "C1: stand taller (clears TR1)."
    bent = Decision(("C1", "TR1"), "bent", 0.3, "TR1", toward="left", note="Away from the pot.")
    assert decision_words(bent) == "TR1: bend left (clears C1); Away from the pot."
    assert decision_words(Decision(("TR1", "C1"), "accept", 0.3)) == "TR1 and C1 touch: accepted."
    edge = Decision(("C1", EDGE), "accept", 1.9, note="deep box")
    assert decision_words(edge) == "C1 past the board's edge: accepted; deep box."


def test_an_overlap_says_what_is_worth_knowing_about_its_parts() -> None:
    """Hints, not rules: by kind (a trimmer's screw), then each part's typical height from
    the footprint table (Bourns 3362P 4.88 mm, a 6.3 mm NRWS 11 mm); to stand one taller,
    the other's height and 1 mm, up to the next half mm (C1 over TR1: 5.88 → 6; TR1 over
    C1: 12)."""
    found = outline_overlaps(LAYOUT, BOARD)[0]
    assert found.hints == HINTS
    assert found.taller == {"TR1": 12.0, "C1": 6.0}


def test_every_height_in_the_footprint_table_names_where_it_was_read() -> None:
    """D-398, D-019: a typical height only from a maker's sheet, its source saying where and
    when it was read; a flat axial part stands its diameter high; a DIP switch, a SIL and a
    leaded MLCC have none yet (the builder types it)."""
    radial = [s for sizes in TABLE.radial.values() for s in sizes]
    one = [TABLE.trimmer, TABLE.trimmer_triangle, TABLE.dip, TABLE.dip_switch, TABLE.sil]
    sized = [*radial, *TABLE.inline, *one]
    with_height = [s for s in sized if s.height]
    assert len(with_height) == 19
    for size in with_height:
        assert "read 2026-11-24" in size.source, size
    assert [s.height for s in TABLE.radial["electrolytic"]] == [11, 11, 11.5, 12.5, 20]
    assert (TABLE.dip_switch.height, TABLE.sil.height) == (0, 0)
    c1 = board_parts(V39, MODELS, TABLE)[0]["C1"].footprint
    assert (c1.diameter, c1.height) == (6.3, 11)
    resistor = Resistor(ref="R1", pos=(0, 0), type="resistor", value=1e3)
    r1 = one_board_part(resistor, MODELS, TABLE)
    assert r1.footprint.height == r1.footprint.width == 2.5
