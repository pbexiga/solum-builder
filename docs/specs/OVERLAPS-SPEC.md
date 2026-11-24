# Overlaps: the builder decides (P6h4, D-398)

## Goal
D-394 flags two bodies touching between holes, or one hanging past the board's edge, as a warning. The user (2026-11-23): "a trimmer can still be worked around — if a cap is next to a trimmer, I can wire taller and bend it out of the way… having a list of what is in 'error' and allowing the user to decide taller, bent, or just accept and leave notes." So the builder decides each one, and the decision travels with the board to the build sheet.

## What the person gets
- **The overlaps in the board's Warnings**, each naming the two parts (or the part and the edge) and by how much in mm, with **Decide…**. The form offers:
  - **Stand taller**: which of the two, and by how much in mm if known. With typical heights known, it fills in the other part's height plus 1 mm; the builder's own figure is never replaced.
  - **Bend out of the way**: which of the two, toward left, right, up or down (as the parts side shows the board; no bent bodies are drawn).
  - **Accept**: leave it as it is.
  Each may carry the builder's note ("sleeve the leg"). A part past the edge takes only Accept with a note: it's about the enclosure, and nothing bends past the edge.
- **Hints, not rules**, at the top of the form: by kind ("TR1's adjusting screw must stay reachable from above", "If IC1 goes in a socket, it must lift straight out", "SW3's switches must stay reachable to flip"), then each part's typical height ("C1 is about 11 mm tall (typical: check yours)"). Nothing is refused.
- **Decided overlaps** leave the warnings and are listed under *Decided (n)* in words ("C1: stand 6 mm taller (clears TR1); sleeve the leg."), each with **Change…** (the form filled in, with **Forget it**). The part's card on the board (shown while it's selected) names its decisions. Each choice is one undo step.
- **The build sheet** (the package's stripboard page) lists the decisions after the parts, under *Where bodies touch: as you decided*, accepted ones too as a reminder.
- **Moving a part** drops a decision when its two parts no longer touch, **or touch by another amount** (the user, 2026-11-24: the old fix may not fit); the overlap is a fresh warning.

## How it works
- The decisions are kept in the board's own section of the circuit file, `circuit.stripboard.overlaps` (schema v40; a v39 board has none): `{parts: [a, b], fix: taller | bent | accept, part?, mm?, toward?, note?, overlap_mm}`, `b` the other part or `"edge"`. They ride on `board.Layout`, so every edit round-trips them; `board.decision_problem` is the one check of what makes sense.
- `check.outline_overlaps` gives each overlap structured (parts, mm, sentence, hints, the suggested mm per part); `check.covers` matches a decision by the pair (either order) and the amount to 0.1 mm; `progress` returns the undecided as `overlaps` and the matched decisions as `decided`, with their words from `check.decision_words` (the one owner of the words, used by the Warnings, the card and the build sheet). Every board edit, size change, Start a board and Tidy up drop the decisions that no longer match (`check.kept_decisions`).
- A `decide` board edit keeps a decision at the amount the board has now (the page doesn't send it); `undecide` forgets one.
- **Heights** are typical, from one maker's sheet per kind, named in `library/guides/footprints.yaml` with where and when they were read (D-019): electrolytics (NIC NRWS, 25 V), box film (WIMA MKS 2, 63 V), the 5 mm LED, TO-92, the two trimmers, a DIP. A flat axial part stands its diameter high. Without a sourced height the form leaves the mm to the builder.
- Start for me, Tidy up and the starters still avoid overlaps (D-391).

## Out of scope
- Rules that refuse a placement (the user: a trimmer can be worked around).
- 3D clearance checks, or the enclosure's lid height (with "does the board fit the enclosure?", later).
- Heights for the DIP switch, SIL chips, leaded MLCCs, TO-18 / TO-5 cans and 3 mm LEDs (no sheet read yet).

## Answers (the user, 2026-11-23 and 24)
1. Bend toward a side (left, right, up, down as shown), not toward a hole: no bent bodies drawn.
2. An accepted overlap still prints on the build sheet as a reminder.
3. "Taller", with an optional mm; heights from makers' sheets, typical ones ("standard heights, as I won't be buying caps from the same vendor every time").
4. The edge overhang gets only Accept with a note.
5. Decisions live in the board's section of the file.
6. A part moved so the pair touches by another amount: drop the decision.
