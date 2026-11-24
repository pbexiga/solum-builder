# Overlaps: warnings, board notes and dismissals (P6h4, as built; D-398)

Replaces a first design (Decide… with Stand taller / Bend / Accept, typical heights), built on the same branch and reworked before it shipped. The user (2026-11-24): "we probably don't need the heights. We should just leave it to the builder to decide… a notes section like we did for schematics. Allowing global notes and notes per warning."

## Goal
D-394 warns when two bodies touch between holes, or one hangs past the board's edge. The builder knows their real parts, so the app doesn't guess heights or offer fixes: it warns, and the builder writes a note, dismisses the warning, or leaves it. Notes travel with the board to the build sheet.

## What the person gets
- **Warnings without numbers.** "C2 and R1's bodies touch: move one a hole further away if you can." / "C1 hangs past the board's edge." The outlines are one maker's, so no mm is shown (a small margin inside the check still keeps bodies that only just meet from counting).
- **Marks on the board**, as the schematic's problem marks (D-176, D-181): one where the two bodies touch (a part past the edge: on that part). Clicking a mark opens its row in the Warnings. **View → Problem marks** hides them, the same setting for the schematic and the board. A dismissed warning has no mark.
- **Each warning row:** **Note…** and **Dismiss…**.
  - **Note…** opens the note form with Parts already filled in ("C2, R1").
  - **Dismiss…** as the Problems pane's (optional reason); dismissed warnings under *Dismissed*, each with **Bring back**. Matched by the pair (either order). A dismissal whose warning no longer exists lapses quietly; if the overlap comes back, it's a fresh warning.
  - Notes and dismissals are independent: dismissing doesn't touch a note, writing a note doesn't dismiss.
- **A board Notes pane**, one list, as the schematic's Notes pane looks:
  - each note: optional **Parts** (refs, e.g. "C2, R1"; checked against the board's parts) and **Text**; shown as "C2, R1: solder C2 a bit higher."; a note with no parts is a general note ("Socket IC1.").
  - Add, edit (both fields; editing never drops the refs unless the builder clears them), delete. Each is one undo step.
  - **Never deleted automatically.** A note goes out of date, and is shown dimmed with why, when:
    - its parts no longer touch (it was written from a warning that has cleared): "C2 and R1 no longer touch";
    - a part it names isn't on the board: "R1 isn't on the board".
    The tag goes when the cause does.
  - A part renamed in the schematic: its refs in the board's notes follow (as schematic notes do, D-267).
- **The build sheet** (the package's stripboard page) lists every note after the parts, as written, with no out-of-date tags.

## How it works
- Schema 40: `circuit.stripboard.notes: [{parts: [refs], text, overlap?: true}]` and `circuit.stripboard.dismissed: [{parts: [a, b], reason?}]` (`b` may be `"edge"`). `overlap` marks a note started from a warning, so "no longer touch" applies to it only. Migration v39 → v40: nothing to add.
- The server owns the warnings' words and the out-of-date reasons (`check`); the browser builds the edit payloads only.
- Dismissals lapse with the next board change when their overlap is gone (`check.kept_dismissals`). Notes are never pruned.
- Start for me, Tidy up and the starters still avoid overlaps (D-391).

## Removed from the first P6h4
Heights (`footprints.yaml`, `Footprint.height`, guides sizes, the clearance and the suggestion), the fix kinds (taller / bent / accept, part, mm, toward), the hints by kind, `overlap_mm` and matching by amount, the Decide… form, the part card's decisions, the overlap depth in the warning text. Kept: the WIMA MKS 2 width fix (3.3 / 4.7 µF at 11 mm, the 63 V column) and the 2.2 µF row.

## Out of scope
- Rules that refuse a placement; 3D clearance; the enclosure's height ("does the board fit the enclosure?", later: the heights' sources were in the first design's commit 11c635b, not on main).
- Notes per part beyond refs on a note.

## Answers (the user, 2026-11-24)
1. No heights, no fix kinds: a note in the builder's words.
2. Notes are never cleared automatically; out-of-date ones are marked.
3. A warning needn't have a note; it can be left alone or dismissed.
4. Notes are editable; editing keeps the refs.
5. Warnings marked on the board like the schematic's, with the same toggle.
6. One Notes list (no separate Overlaps tab); general notes are notes with no parts.
7. Overlap amounts aren't shown: the outlines aren't accurate enough.
