# Standing resistors and diodes: a choice (P6i1)

## Goal
Today Start a board, Fill the rest and Tidy up never stand a part up, while Build a full layout stands up as many as it can (it costs nothing), so the TS808's full layout has nine parts standing (R6, R9, R11, R14, R32, R34, R35, D1, D2). Builders differ: some never stand parts (sturdier, easier to read), some like the room it saves. The builder chooses, and the choice stays with the board. The default stands a part only when it's needed, never just to save room: a board that works matters more than a small one (the user, 2026-11-25).

## What the builder gets
- In the **Layout…** window, one line under the choices: **Standing resistors and diodes: Never / When needed / Prefer**. Default **When needed**. It applies to whichever layout choice runs (Start a board, Fill the rest, Tidy up, Build a full layout).
- The window opens on the **board's own choice** (the one that made it; the default on a board that has none). What's run is kept with the board, so **Try another** (the review bar) and a later Tidy up or Fill the rest use it unless the builder changes it in the window.
- A standing part is checked for touching like any other body (it had no outline before).

## How each layout choice uses it
| | Never | When needed (default) | Prefer |
|---|---|---|---|
| **Start a board** | none stand | a part kept by a pin (decoupling, feedback, bypass) stands when no flat shape brings its leg to the pin's strip; each band is laid out flat too, and where lying flat breaks a limit (a leg too far along the strip included) once more with that limit's parts allowed to stand. Fewest limits broken wins, then fewest standing, then size. For limits only, unlike the other choices: warnings rank after size in Start, for every choice (changing that is its own step) | standing tried first: a part stands wherever it fits |
| **Fill the rest** | none stand | as Start a board | standing tried first |
| **Tidy up** | no shape step | after tidying, a part stood up (one leg kept, the other a hole beside it) only where that leaves fewer limits broken and warnings, whatever the size, without breaking a limit the board met; then tidied again. It can't fix a leg too far along (see below) | a part stood up whenever the board's size, cuts and links get no worse |
| **Build a full layout** | no standing shapes | the best board breaks the fewest limits, then has the fewest warnings (links near a high-gain input, strips alongside one), then **the fewest standing parts**, then is the smallest; finishing lays flat again any standing part that can lie flat with no more limits nor warnings; a fifth, flat attempt runs beside the four (Never's seed-1 board), so it ranks no worse than that | as before: standing costs nothing (with the flat attempt too) |

**Why not "when it saves room"**: the first version (2026-11-24) counted each standing part as a column's worth of holes (the board's strips). On the starters it behaved as Never (a standing resistor saves two or three holes along a strip, rarely a column), and it was the wrong question: the user wants a part stood up "when absolutely necessary, not just when it saves room", where lying flat it can't be where it must (2026-11-25).

**Start doesn't reach Prefer's size, by design.** The TS808 laid flat is 54 × 18 with two limits broken (R5 and D1 too far along IC1's pins 5 and 6); When needed stands D1 and D2 and meets every limit on 68 × 20; Prefer's 51 × 17 stands eight parts, R5 and others no limit asks for: standing for room. Start only has to be roomy and correct; size is Build a full layout's.

**Why Tidy up can't do what Start does for a leg too far along.** Start lays its parts across the strips, a leg on each net's strip. A tidy step stands a part by keeping one leg and moving the other a hole over: up or down, it lands on another strip and leaves its net (the check refuses it); sideways, the part still takes its column, so no room is freed for the kept part to slide into. Fixing it would take standing and rewiring in one step (a new link or cut). A wider trigger, tidying after each stand, was tried and fired on no starter.

**The search's cost** (`compact.STAND`, 450): each standing part, under a warning's cost (500) and a broken limit's (2000), above any room it saves; in choosing the best board, the count of standing parts comes after limits and warnings, before size.

## The outline of a standing part
The body stands over its first leg (as the board draws it: a circle over the first leg, the lead bent down to the other). Its outline is a box along the legs: from the body's far side (half its diameter past the first leg) to half a lead (0.3 mm) past the other leg, as wide as the body (the bent lead over the other hole stays within it). Two standing ¼ W resistors on neighbouring strips (2.5 mm bodies, 2.54 mm apart) aren't warned, like flat ones (P6i5).

## The file
`stripboard.stand_up`: `"never"`, `"needed"` or `"prefer"`; left out when `"needed"` (defaults aren't written). `stripboard.standing` (the parts stood up) already exists, so the choice can't take that name. Schema 41; a v40 board has none, so it reads as "needed" (the default: what a new board gets), and the migration changes nothing. Old-version fixture `tests/fixtures/circuits/old/schema-v40.json`.

## Out of scope
- Laying a standing part flat again in Tidy up (Never on a board with standing parts: Tidy up leaves them; Start a board or Build a full layout with Never lays everything flat).
- Standing other parts (a film cap on its side, a transistor bent over).
- A per-part choice.

## Decisions it needs
D-403 (the choice, its default, where it's kept, how each layout choice uses it, the cost); D-388 amended (Tidy up's shape step); D-399 amended (the cost); D-394 amended (standing parts' outline).

## Open questions
None: the user answered them on 2026-11-24 (P6i1 in `notes/PHASES.md`) and on 2026-11-25 (When needed, in every layout choice, Tidy up too); *default* choices the agent made are marked in the PR: the outline's box, Start a board's "only a kept part that can't reach its pin", Tidy up's "fewer limits broken and warnings, first found", Tidy up's Prefer rule, `STAND`'s 450.
