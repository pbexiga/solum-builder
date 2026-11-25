# Standing resistors and diodes: a choice (P6i1)

## Goal
Today Start a board, Fill the rest and Tidy up never stand a part up, while Build a full layout stands up as many as it can (it costs nothing), so the TS808's full layout has nine parts standing (R6, R9, R11, R14, R32, R34, R35, D1, D2). Builders differ: some never stand parts (sturdier, easier to read), some like the room it saves. The builder chooses, and the choice stays with the board.

## What the builder gets
- In the **Layout…** window, one line under the choices: **Standing resistors and diodes: Never / When it saves room / Prefer**. Default **When it saves room**. It applies to whichever layout choice runs (Start a board, Fill the rest, Tidy up, Build a full layout).
- The window opens on the **board's own choice** (the one that made it; the default on a board that has none). What's run is kept with the board, so **Try another** (the review bar) and a later Tidy up or Fill the rest use it unless the builder changes it in the window.
- A standing part is checked for touching like any other body (it had no outline before).

## How each layout choice uses it
| | Never | When it saves room (default) | Prefer |
|---|---|---|---|
| **Start a board** | none stand | none stand (roomy and predictable) | standing tried first: a part stands wherever it fits |
| **Fill the rest** | none stand | standing tried after lying flat: chosen only where it's cheaper in the band | standing tried first |
| **Tidy up** | no shape step | a part stood up only when the board then shrinks by at least a column's worth of holes (the board's strips) | a part stood up whenever the board's size, cuts and links get no worse |
| **Build a full layout** | no standing shapes | each standing part costs a column's worth of holes (the board's strips): kept only where it saves more | as before: standing costs nothing |

**The cost, "a column's worth"**: the board's strips count as holes of board, per standing part, in the search's cost and in choosing the best board. A strip's worth was weighed (it barely changes anything on a wide board) and a fixed count of holes (20) too (it means a column on one board and half a column on another): the user chose "about a column's worth of holes (the board's strips count)" (2026-11-24).

## The outline of a standing part
The body stands over its first leg (as the board draws it: a circle over the first leg, the lead bent down to the other). Its outline is a box along the legs: from the body's far side (half its diameter past the first leg) to half a lead (0.3 mm) past the other leg, as wide as the body (the bent lead over the other hole stays within it). Two standing ¼ W resistors on neighbouring strips (2.5 mm bodies, 2.54 mm apart) aren't warned, like flat ones (P6i5).

## The file
`stripboard.stand_up`: `"never"`, `"room"` or `"prefer"`; left out when `"room"` (defaults aren't written). `stripboard.standing` (the parts stood up) already exists, so the choice can't take that name. Schema 41; a v40 board has none, so it reads as "room" (the default: what a new board gets), and the migration changes nothing. Old-version fixture `tests/fixtures/circuits/old/schema-v40.json`.

## Out of scope
- Laying a standing part flat again in Tidy up (Never on a board with standing parts: Tidy up leaves them; Start a board or Build a full layout with Never lays everything flat).
- Standing other parts (a film cap on its side, a transistor bent over).
- A per-part choice.

## Decisions it needs
D-403 (the choice, its default, where it's kept, how each layout choice uses it, the cost); D-388 amended (Tidy up's shape step); D-399 amended (the cost); D-394 amended (standing parts' outline).

## Open questions
None: the user answered them on 2026-11-24 (P6i1 in `notes/PHASES.md`); *default* choices the agent made are marked in the PR: the outline's box, Fill the rest's "after lying flat", Tidy up's Prefer rule.
