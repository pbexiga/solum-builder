# Stripboard rules: what published boards do, and the rules we keep

The spike asked for by the user, 2026-11-26: compare our layout rules with published boards and find what builders do that our editor should allow. What it decided was built as P8 (D-410 to D-414). The user: "don't be afraid to remove our rules - they may be too zealous. i don't mind starting from scratch."

## The boards read

Eleven stripboards, read from their drawings by the agent (2026-11-26), all strips horizontal:

| Board | Source | Size | Cuts / links |
|---|---|---|---|
| Klon Centaur ("Smaller") | Tagboard Effects | 21 × 26 | 32 / 14 |
| Boss DS-1 (by mirosol) | Tagboard Effects | 22 × 17 | 24 / 10 |
| EHX '73 Ram's Head Big Muff | Tagboard Effects | 19 × 17 | 17 / 5 |
| MXR Dyna Comp | Tagboard Effects | 18 × 15 | 17 / 8 |
| Ibanez TS808 ("layout 2") | Tagboard Effects | 20 × 15 | 17 / 7 |
| ProCo Rat ("smaller") | Tagboard Effects | 20 × 11 | 15 / 4 |
| Marshall Bluesbreaker | Tagboard Effects | 21 × 10 | 19 / 3 |
| Fuzz Face PNP | Tagboard Effects | 20 × 9 | 2 / 1 |
| Tone Bender MkII ("smallest") | Tagboard Effects | 15 × 9 | 4 / 1 |
| Dallas Rangemaster (PNP, negative ground) | Tagboard Effects | 14 × 8 | 9 / 2 |
| EHX × JHS Big Muff 2 | vero-p2p.blogspot.com (2025-12-24) | 22 × 23 | — |

The links are each starter's acceptance file (`stripboard:`); the Big Muff 2 is https://vero-p2p.blogspot.com/2025/12/electro-harmonic-x-jhs-big-muff-2.html. A third site's Triangle Big Muff (effectslayouts.blogspot.com, by storyboardist) turned out to be perfboard with wire traces: left out. Three authors: nine are IvIark's, the DS-1 is mirosol's (also on Tagboard Effects), the Big Muff 2 is vero-p2p's.

## What they do

Counted over the eleven (a board without the part type isn't counted against).

| # | Practice | Boards | Our editor today |
|---|---|---|---|
| 1 | ¼ W resistor flat, legs 3 apart (4 holes) as the norm | 11 / 11 | allowed since the WIP commit (was 4 apart) |
| 2 | Resistor on long leads, 5–7 apart, to reach a strip | 5 (BM 7, TS808 7, Rat 5, Klon, Dyna Comp) | allowed; the search tries up to 6 |
| 3 | Small-signal diode flat, legs **2** apart (DO-35; the BM's 1N5817, DO-41, too) | 5 (BM, Klon, TS808, Rat, BMP2); others 3–4 | **refused** (at least 3) |
| 4 | Film caps 2 apart; ceramics 1–2 | every board with them | allowed since the WIP commit |
| 5 | Electrolytic standing 1–2 apart, a lead bent to 3 | every board with them | allowed |
| 6 | Axial electrolytic or big box film lying across 4–5 strips | 2 (Fuzz Face, Tone Bender) | can't be said (electrolytics are radial only) |
| 7 | TO-92 legs 1 apart down a column; two transistors in one column | all with transistors; Tone Bender stacks two | allowed |
| 8 | Links under a chip, between its rows, ending there too | 7 / 7 boards with a chip | allowed (D-401) |
| 9 | A chip's cuts in either middle column, per strip (staggered) | 4 (Klon, Rat, Dyna Comp, Bluesbreaker) | allowed |
| 10 | A link running over cut holes (down a column of cuts) | 3 (BM, Rat, Bluesbreaker) | allowed |
| 11 | **Two link ends in one hole** (a tap: one strip joined to two others down one column) | 4 (Klon, TS808, Dyna Comp ×3, DS-1 drawn as a tapped link) | **refused** ("share hole") |
| 12 | **A link under a body other than a flat resistor or diode**: an electrolytic, a film cap, a TO-92 | 4 (DS-1 film and electrolytic, TS808 100 µ and Q2, Bluesbreaker and Dyna Comp at an electrolytic's edge) | **refused** |
| 13 | A part along a strip, a cut under its body between its legs | 2 (Bluesbreaker's 1K, BMP2's four 100 nF and its diode) | allowed |
| 14 | The supply strip in the middle of the board, not at an edge | 6 (BM, Klon, TS808, Rat, Bluesbreaker, Dyna Comp) | allowed; Start a board puts rails top and bottom |
| 15 | Off-board wires into the left and right edge holes | 11 / 11 | allowed (pads where cheapest) |
| 16 | Bodies over a neighbour's (a standing electrolytic over a resistor) | 2 (Dyna Comp, Klon) | a warning (D-398) |
| 17 | A TO-92's flat face at the board's edge, the body past it | 2 (TS808, Dyna Comp) | a warning (D-394) |
| 18 | Not a 1:1 build (parts left out) | 1 (DS-1 omits C2 and its 100k) | n/a: the check is the circuit |

Not readable from drawings: whether they keep our placement limits (D-367, D-400), quiet links (D-402) or outputs away from inputs (D-404); that needs each board's nets. None of the drawings shows anything done for them (no link moved aside, no strip left empty between stages); the Klon's and Big Muff's long links run past every stage.

Seen once more on the DS-1 (Next session note, 2026-11-26): the published board keeps connected nets 2–3 strips apart, so resistors are short; our search runs most 5–7 holes and needs more links. **Most of the gap is the strip order, not the rules.**

## The experiments

A Quick full layout (attempt 1, standing When needed) of seven starters under each switch alone and all together (`scratch/p7/rules_exp.py`, `rules_batch.sh`; the switches as env-guarded edits, `scratch/p7/rules-switches.patch`, never committed; log `scratch/p7/rules-exp.log`, boards in `scratch/p7/exp/`):

- **DIODE2**: DO-35, DO-34 and DO-41 flat from 2 apart (practice 3).
- **NOLIMITS**: no placement limits in the search (D-367, D-400).
- **NOQUIET**: no quiet-link or alongside cost in the search (D-402, D-404).
- **ANYLINKS**: a link may pass under any body (practice 12).
- **TAPS**: a link end may share a hole with its own net's other link (practice 11).


**The first batch ran without the simulator** (the native venv had no `NGSPICE_LIBRARY`), so the loud inputs were empty and D-400's input limit, D-402 and D-404 never acted: it measures the physical switches against our rules minus those. Log `scratch/p7/rules-exp-nosim.log`. Area in holes:

| | Big Muff | Klon | TS808 | Rat | DS-1 | Bluesbreaker | Dyna Comp | Total | vs published |
|---|---|---|---|---|---|---|---|---|---|
| Published | 323 | 546 | 300 | 220 | 374 | 210 | 270 | 2243 | 1.00× |
| Our rules (no simulator) | 391 | 1000 | 330 | 294 | 638 | 264 | 405 | 3322 | 1.48× |
| DIODE2 | 390 | 960 | 336 | 304 | 594 | 264 | 392 | 3240 | 1.44× |
| ANYLINKS | 374 | 1050 | 322 | 330 | 567 | 247 | 378 | 3268 | 1.46× |
| TAPS | 374 | 1008 | 345 | 288 | 594 | 247 | 360 | 3216 | 1.43× |
| All five | 360 | 936 | 345 | 304 | 598 | 240 | 364 | 3147 | 1.40× |

**The second, with ngspice** (`scratch/p7/rules-exp.log`; stopped after four configurations when the user chose to drop the input/output rules):

| | Big Muff | Klon | TS808 | Rat | DS-1 | Bluesbreaker | Dyna Comp | Total | vs published |
|---|---|---|---|---|---|---|---|---|---|
| Our rules | 460 | 1175 | 416 | 304 | 651 | 300 | 390 | 3696 | 1.65× |
| NOLIMITS + NOQUIET | 378 | 1450 | 392 | 308 | 672 | 312 | 406 | 3918 | 1.75× |
| DIODE2 + ANYLINKS + TAPS | 352 | 840 | 391 | 300 | 546 | 286 | 375 | 3090 | 1.38× |
| All five | 851 | 1755 | — | — | — | — | — | — | — |

What they say:
- The input/output rules cost area: our rules come to 1.48× without them, 1.65× with them.
- What builders do (diodes 2 apart, links under any body, taps) gives the smallest boards: 1.38×.
- **One attempt swings ±30 %**: taking rules away sometimes made boards bigger (the Klon 1175 → 1450; all five on the Big Muff 37 × 23). The placement limits' pull seems to steer the search usefully, so without them it wanders. These runs can't rank the rules finely.
- **Board size follows the part count**: under ~15 parts at or below the published board, ~30 about 1.35×, ~40 1.1–1.4×, ~45 1.5–1.7×, ~70 (Klon) 1.8×.

**CP-SAT under today's rules**, for comparison (the user asked; `scratch/starter_boards.py`, 60 s a height, in the dev image): the Rat 23 × 10 = 230, 17 cuts, 6 links, passes the check, in about 7 minutes on 8 cores: 1.05× the published 220. Our Quick: 294–304; Start a board + Tidy up: 50 × 23. So even a much stronger solver given minutes only matches a hand layout. Not pursued (D-368 still holds).

## What we're doing (the user, 2026-11-26)

**The builder is free to lay the board out as builders do; the app gives guardrails, not routing rules.** The aim: every sample board's practices can be drawn in the editor, and the check finds only real mistakes. A limit exists only to keep a board realistic.

### Faults: the board isn't done until they're fixed
- **Each part's least leg span**, from its real size; **no most** (long leads are the builder's call: the Big Muff's 7-apart resistor). Counted as holes, legs included:

  | Part | Flat | Standing |
  |---|---|---|
  | ¼ W resistor | 4 holes (legs 3 apart) | 2 holes (legs 1 apart) |
  | ½ W resistor | as the table has it (5 holes flat) | 3 |
  | DO-35, DO-34, DO-41 diode | 3 holes (legs 2 apart) | 2 |
  | DO-15, DO-7 diode | 5 holes, as today | 3 |
  | Box film | 3 holes (legs 2 apart) | — |
  | Ceramic, C0G | 2 holes (legs 1 apart) | — |
  | Electrolytic | — | its pitch's holes, as today, and a lead bent out a hole or two more |
  | TO-92 and cans | legs 1 apart, or bent out to 2 | — |
  | DIP | its rows (3 apart) | — |
  | Trimmer | as its footprint | — |

  What's "as today" stays as `footprints.yaml` has it; the WIP commit's spans (`642f8e8`) are the start, written up as D-410.
- **Impossible placements**: two legs of one part in a hole; a leg or link end in a cut; a leg under another part's body (a chip's body excepted, below); a link over a leg. A link runs down one column.
- **Connections**, as now: shorts, a net in pieces, a polarised part the wrong way round, an off-board wire without a pad. The ratsnest, the progress check, the suggested cuts and links, the marked holes and *Place next* stay: they're hand-layout help.

### Allowed, as builders do
- **A link under any body** (an electrolytic, a film cap, a TO-92), not only a flat resistor, diode or chip (practice 12).
- **Two link ends in one hole** (practice 11): **taps**. A link from strip 2 to 6 and one from 6 to 13 down one column is the DS-1's "P joins 2, 6, 13": no new data, the editor just lets a link end land on another's, and draws the shared hole with a dot.
- A link over cut holes, cuts under a chip in either middle column, a part along a strip with a cut under it (allowed already: kept).

### Warnings, dismissable (D-398's notes and dismissals)
- **A leg between a chip's rows** (D-401 relaxed): "R5 sits under IC1: only if the chip is in a socket and the part is low enough."
- **Two things in one hole from different parts**, or a leg and a link end: "R3 and C2 share F7: check both leads fit."
- Bodies touching and a part past the board's edge (D-394, D-398), as now.

### Removed
- **Quiet links** (D-402, `quiet.py`), **outputs away from inputs** (D-404, `apart.py`, the phase test), **every placement limit** (D-367's, D-400: `limits.py`), in the check, the guidance and the search. The loud-input probe goes if nothing else uses it.
- **A noisy-neighbour rule** was considered (the input jack's strip beside the output's) and dropped: a strip's coupling to the next is tiny beside the off-board wiring, none of the sample boards does anything for it, and on gain stages it would mostly warn about what's meant. A guide note on keeping the jacks' wires apart instead.

### The layout help, reshaped
- **One *Lay it out for me***: today's *Build a full layout* (D-399), Quick only, its cost cleaned of the removed rules (area, cuts, links, link length, pad depth, standing). *Start a board* stays only as its starting board, not a button. A draft, said so.
- **Large circuits**: past a part count measured on the starters (the spike puts it near 25–30), the window says "This circuit has 42 parts: a layout made for you will likely be larger than one laid out by hand. Use it as a draft and look it over." The dialog says what counts as large.
- **Tighten** (today's *Tidy up*, its cost cleaned the same way): small moves on the builder's own board, each kept only if the check passes and nothing gets worse, one undo step. **Kept only if it earns it**: tried on the sample boards (below); if it can't tighten a published hand layout without scrambling it, it goes.
- **The Layout dialog** goes: two actions, each with its own confirmation.

### The sample boards as the test
The TS808, Rat, Bluesbreaker and Klon drawings entered by hand as fixtures (`tests/fixtures/stripboard/`), each checked part by part against our starter, every difference written in the fixture; the check passes each with no faults (its warnings listed). The Klon's ICL7660 is our MAX1044's footprint (pin-compatible; pin 1 unused). **Not the DS-1**: it leaves out C2 (470n, Q1's emitter into the next stage) and R4 (100k to the 4.5 V reference), which our circuit needs (a builder on its page asked why; another found it "sounds like a Fuzz"). Not the Big Muff: the Ram's Head values differ from our V3.

## Decided with the user (2026-11-26)
1. *Lay it out for me* keeps D-403's three standing choices (Never / When needed / Prefer), default When needed.
2. **An axial electrolytic lying flat is added now** (the Fuzz Face and Tone Bender drawings), sized from a maker's sheet. No starter uses one yet: a capacitor needs a way to say it's axial (a field on the part, a schema bump with its migration and the parts list's words), in R1.
3. The removed warnings' saved notes and dismissals: nothing done (no saved boards in use yet).

## What was built (P8, D-410 to D-414)

- **The rules** (D-410): spans from the least a part's size allows and no most; faults, warnings and allowances as above; taps (a link end landing on another's, drawn with a dot, and *Tap here* on a link's right-click); a link under any body; placement limits, quiet links and outputs away removed from the check, guidance, search and warnings. **An axial electrolytic** (D-411, schema v42): a capacitor's `axial`, sized from Vishay's 021 ASM.
- **The sample boards** (D-412): the TS808, Rat, Bluesbreaker and Klon drawings as `tests/fixtures/stripboard/*-tagboard.yaml`, each passing the check with no faults and exactly the warnings its fixture lists.
- **The layout help** (D-413, D-414): one *Lay it out for me…* (Quick only, a draft, "large" past 25 board parts), Start a board as its starting board only; the Layout dialog, Fill the rest, Tidy up (Tighten) and Thorough removed. Find part in the Board view, and a peek over a large view (D-414).
- **The guide**: `docs/guide/stripboard.md` (*What the board checks*, *Letting the app lay it out*), `drawing.md` (a capacitor's Leads), `first-pedal.md` (peeks).

The earlier specs this changes carry a note saying so: `QUIET-LINKS-SPEC.md`, `OUTPUT-AWAY-SPEC.md`, `COMPACT-SPEC.md`, `STANDING-SPEC.md`, `STRIPBOARD-SPEC.md`.
