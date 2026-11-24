"""Overlap warnings, the builder's board notes and dismissals (D-398): warnings with no
amount, notes kept with the board and never dropped (out of date, with why), dismissals
matched by the two parts and lapsing when they no longer touch. On D-394's case
(`tests/fixtures/circuits/old/schema-v39.json`): a triangle trimmer TR1 (legs B1, A2, B3)
and a 6.3 mm electrolytic C1 (D1, D2) whose outlines run into each other."""

from dataclasses import replace
from pathlib import Path

import pytest

from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import (
    EDGE,
    BoardError,
    Dismissed,
    Layout,
    Note,
    dismissed_from_data,
    layout_data,
    layout_from_data,
    note_data,
    note_from_data,
    parse_hole,
)
from solum.stripboard.check import (
    NoteState,
    Overlap,
    dismissed_apart,
    kept_dismissals,
    note_states,
    note_words,
    outline_overlaps,
    progress,
)
from solum.stripboard.edit import BoardEdit, EditError, edit_layout
from solum.stripboard.footprints import board_parts, outline_overlap

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
V39 = load_circuit(REPO / "tests/fixtures/circuits/old/schema-v39.json")
BOARD = board_parts(V39, MODELS, TABLE)[0]
assert V39.stripboard is not None
LAYOUT = V39.stripboard.layout()
TOUCH = "TR1 and C1's bodies touch: move one a hole further away if you can."
NOTE = Note("Solder C1 a little higher.", ("C1", "TR1"), overlap=True)
APART = (("1", (4, 0)), ("2", (4, 1)))  # C1 a column further from TR1: they no longer touch


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


def test_a_v39_board_has_no_notes_and_its_overlap_is_a_plain_warning() -> None:
    """v40 added `notes` and `dismissed`: a v39 board has neither, its overlap is warned of
    with no amount (the outlines are one maker's), and empty lists aren't written."""
    assert V39.schema_ == 40 and (LAYOUT.notes, LAYOUT.dismissed) == ((), ())
    assert outline_overlaps(LAYOUT, BOARD) == [Overlap(("TR1", "C1"), TOUCH)]
    saved = circuit_to_dict(V39)["stripboard"]
    assert "notes" not in saved and "dismissed" not in saved


def test_notes_and_dismissals_are_kept_in_the_board_s_section_of_the_file() -> None:
    """Saved with only what was said, read back the same; a general note has no parts."""
    general = Note("Socket IC1.")
    board = {**layout_data(LAYOUT), "notes": [note_data(NOTE), note_data(general)],
             "dismissed": [{"parts": ["C1", "TR1"], "reason": "Low trimmer"}]}  # fmt: skip
    saved = circuit_to_dict(parse_circuit({**circuit_to_dict(V39), "stripboard": board}))
    assert saved["stripboard"]["notes"] == [
        {"parts": ["C1", "TR1"], "text": "Solder C1 a little higher.", "overlap": True},
        {"text": "Socket IC1."},
    ]
    assert saved["stripboard"]["dismissed"] == [{"parts": ["C1", "TR1"], "reason": "Low trimmer"}]
    again = parse_circuit(saved).stripboard
    assert again is not None
    assert again.layout().notes == (NOTE, general)
    assert again.layout().dismissed == (Dismissed(("C1", "TR1"), "Low trimmer"),)


def test_a_note_or_dismissal_that_makes_no_sense_is_refused_in_words() -> None:
    """A note needs text (spaces aren't); its parts are trimmed and each named once, and a
    note with none can't be from an overlap. A dismissal names two parts, or a part and the
    edge (never the edge first, never a part twice)."""
    with pytest.raises(BoardError, match="needs some text"):
        note_from_data({"parts": ["C1"], "text": "  "})
    assert note_from_data({"parts": [" C1", "C1", ""], "text": " x ", "overlap": True}) == (
        Note("x", ("C1",), overlap=True)
    )
    assert note_from_data({"text": "x", "overlap": True}) == Note("x")
    for pair in (["C1", "C1"], ["edge", "C1"], ["", "C1"]):
        with pytest.raises(BoardError, match="names the two parts"):
            dismissed_from_data({"parts": pair})
    with pytest.raises(BoardError):
        layout_from_data({**layout_data(LAYOUT), "notes": [{"parts": ["C1"]}]})


def test_a_dismissal_matches_its_overlap_either_way_round() -> None:
    """Dismissed C1 and TR1 covers the warning on TR1 and C1, with its reason."""
    touching = outline_overlaps(LAYOUT, BOARD)
    with_it = replace(LAYOUT, dismissed=(Dismissed(("C1", "TR1"), "fine"),))
    assert dismissed_apart(with_it, touching) == ([], [Overlap(("TR1", "C1"), TOUCH, "fine")])
    other = replace(LAYOUT, dismissed=(Dismissed(("C1", "C2")),))
    assert dismissed_apart(other, touching) == (touching, [])


def test_dismissing_and_bringing_back_are_board_edits() -> None:
    """`dismiss` with a reason replaces an earlier dismissal of the same two; `restore`
    brings the warning back; two that don't touch, or a warning not dismissed, refused."""
    once = edit(LAYOUT, BoardEdit("dismiss", "C1", to="TR1", reason=" low trimmer "))
    assert once.dismissed == (Dismissed(("C1", "TR1"), "low trimmer"),)
    twice = edit(once, BoardEdit("dismiss", "TR1", to="C1"))
    assert twice.dismissed == (Dismissed(("TR1", "C1")),)
    assert edit(twice, BoardEdit("restore", "C1", to="TR1")).dismissed == ()
    with pytest.raises(EditError, match="warning on C1 and TR1 isn't dismissed"):
        edit(LAYOUT, BoardEdit("restore", "C1", to="TR1"))
    apart = edit(LAYOUT, BoardEdit("place", "C1", APART))
    with pytest.raises(EditError, match="no warning on TR1 and C1 now"):
        edit(apart, BoardEdit("dismiss", "TR1", to="C1"))


def test_a_dismissal_lapses_when_its_parts_no_longer_touch() -> None:
    """C1 moved away: the dismissal goes (moved back, the warning is fresh); any other edit
    keeps it; `kept_dismissals` leaves a layout with nothing lapsed as it is."""
    kept = replace(LAYOUT, dismissed=(Dismissed(("C1", "TR1")),))
    assert edit(kept, BoardEdit("cut", holes=(parse_hole("F3"),))).dismissed == kept.dismissed
    moved = edit(kept, BoardEdit("place", "C1", APART))
    assert moved.dismissed == ()
    back = edit(moved, BoardEdit("place", "C1", (("1", (3, 0)), ("2", (3, 1)))))
    assert [o.parts for o in dismissed_apart(back, outline_overlaps(back, BOARD))[0]] == [
        ("TR1", "C1")
    ]
    assert kept_dismissals(kept, BOARD) is kept


def test_notes_are_added_changed_and_deleted_and_never_dropped() -> None:
    """Each a board edit; a part moved, a cut made: notes stay. A note may name only the
    board's parts (and off-board parts), but a part it already named stays nameable when
    the note is changed."""
    one = edit(LAYOUT, BoardEdit("note-add", note=NOTE))
    two = edit(one, BoardEdit("note-add", note=Note("Socket IC1.")))
    assert two.notes == (NOTE, Note("Socket IC1."))
    changed = edit(two, BoardEdit("note-set", index=0, note=replace(NOTE, text="Higher.")))
    assert changed.notes[0] == replace(NOTE, text="Higher.")
    assert edit(changed, BoardEdit("note-delete", index=1)).notes == (changed.notes[0],)
    moved = edit(changed, BoardEdit("place", "C1", APART))
    assert moved.notes == changed.notes
    with pytest.raises(EditError, match="There's no R9 among the board's parts"):
        edit(LAYOUT, BoardEdit("note-add", note=Note("x", ("R9",))))
    gone = replace(LAYOUT, notes=(Note("x", ("R9",)),))
    assert edit(gone, BoardEdit("note-set", index=0, note=Note("y", ("R9",)))).notes == (
        Note("y", ("R9",)),
    )
    with pytest.raises(EditError, match="isn't on the board any more"):
        edit(LAYOUT, BoardEdit("note-delete", index=0))


def test_a_note_says_why_it_is_out_of_date_and_stops_when_the_cause_does() -> None:
    """From a warning, its parts no longer touching; any note, a part it names off the
    board; a general note never; back as it was, no tag."""
    notes = (NOTE, Note("Socket IC1.", ("IC1",)), Note("Fine."), Note("Mind it.", ("C1",)))
    layout = replace(LAYOUT, notes=notes)
    assert [n.why for n in note_states(layout, outline_overlaps(layout, BOARD))] == [
        None, "IC1 isn't on the board", None, None,
    ]  # fmt: skip
    moved = edit(layout, BoardEdit("place", "C1", APART))
    assert [n.why for n in note_states(moved, outline_overlaps(moved, BOARD))] == [
        "C1 and TR1 no longer touch", "IC1 isn't on the board", None, None,
    ]  # fmt: skip
    off = edit(layout, BoardEdit("remove", "C1"))
    both = replace(off, notes=(Note("x", ("C1", "IC1")),))
    assert note_states(both, outline_overlaps(both, BOARD)) == [
        NoteState(("C1", "IC1"), "x", False, "C1 and IC1 aren't on the board")
    ]


def test_a_note_from_the_edge_warning_goes_out_of_date_when_the_part_is_in() -> None:
    """C1 at column E of a 5-column board hangs past its edge; a note on it from that
    warning is out of date once the board is wider."""
    legs = (("1", (4, 0)), ("2", (4, 1)))
    out = Layout(5, 3, tuple(p if p.ref != "C1" else replace(p, legs=legs) for p in LAYOUT.parts),
                 notes=(Note("Deep box.", ("C1",), overlap=True),))  # fmt: skip
    edge = outline_overlaps(out, BOARD)
    assert [o.parts for o in edge] == [("C1", EDGE)]
    assert edge[0].text == (
        "C1 hangs past the board's edge: check it clears the enclosure, or move it in."
    )
    assert note_states(out, edge)[0].why is None
    wide = replace(out, columns=7)
    assert note_states(wide, outline_overlaps(wide, BOARD))[0].why == (
        "C1 no longer hangs past the edge"
    )
    done = edit(out, BoardEdit("dismiss", "C1", to=EDGE))
    assert done.dismissed == (Dismissed(("C1", EDGE)),)


def test_progress_lists_warnings_dismissed_and_notes_apart() -> None:
    """The board's check: undismissed overlaps, dismissed ones with their reason, each note
    with why it's out of date; none of them a fault."""
    before = progress(LAYOUT, V39, MODELS, TABLE)
    assert [o.parts for o in before.overlaps] == [("TR1", "C1")] and before.dismissed == []
    layout = replace(LAYOUT, dismissed=(Dismissed(("C1", "TR1"), "ok"),), notes=(NOTE,))
    after = progress(layout, V39, MODELS, TABLE)
    assert after.overlaps == [] and after.dismissed == [Overlap(("TR1", "C1"), TOUCH, "ok")]
    assert after.notes == [NoteState(NOTE.parts, NOTE.text, True, None)]
    assert after.faults == before.faults


def test_a_note_in_words_for_the_build_sheet() -> None:
    assert note_words(("C2", "R1"), "Solder C2 higher.") == "C2, R1: Solder C2 higher."
    assert note_words((), "Socket IC1.") == "Socket IC1."
