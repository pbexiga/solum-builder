# A stage's output kept away from its input (P6i2)

## Goal
The failure that makes fuzzes and high-gain drives squeal: a later node's copper running alongside an earlier high-gain input's (neighbouring strips couple a little through the board, enough at high gain and impedance), and the input and output jacks' wires running side by side round the board's edge. Warn about both, and have the layout help keep clear of the first.

## When a pair counts: the phase test
A later net beside a high-gain input (P6i3's: `probe.loud_inputs`) counts only when what couples back **adds** to the input: positive feedback. An inverting stage's output beside its input only trims the treble.
- Read from the AC run the high-gain check already makes (the pots as set, all down, all up), at **2, 10 and 50 kHz** (three points, not a sweep: at 10 kHz alone a stage's 6–8 kHz low-pass can make a real pair look harmless, squeal can sit higher, and phase drifts across the band; the user).
- A net is kept off the input's side when, at **any** of the three, it is **louder than the input**, **in phase with it within ±90°**, and the gain from the input to the output (P6i3's measure, to the last pot's input) clears P6i3's threshold there (25 dB, or 20 dB on a node of 470 kΩ or more).
- Only nets **after** the input on the signal path; never ground, a rail or a bias net (AC-quiet).
- **None for an input on a bias net** (the Klon's U2A and U2B, the Bluesbreaker's IC1B: inverting stages whose + only holds VR or VB): its signal is a trace, so every later node looks louder and in phase, and there's nothing for feedback to add to.
- **Feedback meant is left out**: the stage's own pin that follows the input (an op-amp's − input, an emitter, a source), and a net a two-leg part joins to the input directly (a feedback resistor's far end: the board's fraction of a picofarad is nothing beside the part).
- On the starters: the Fuzz Face's Q1 base keeps Q2's collector and the output cap off its side, not Q1's own collector (inverted) nor Q2's emitter (the feedback resistor); the TS808's inputs keep the clipping stage's output, the tone stage and the output buffer away; the Rangemaster has none (one inverting stage).

## "Alongside" on the board (*default*)
Two neighbouring strips whose copper, joined to the two nets, runs side by side for **3 columns or more, uncut** (`apart.ALONGSIDE`). Copper with no leg on it (cut off past the last leg) doesn't count. A warning, never a refusal:

> Strips 8 and 9 run side by side from A to O: IC1's pin 5 (the high-gain stage's input) beside C4's pin 2, later and in phase with it. Cut one shorter or move it a strip further, so the output can't feed back into the input and squeal.

**The layout help follows it**: Build a full layout counts each such pair of strips as it counts a noisy link (after limits broken, before size: `compact.APART`, the key's second place); Start a board and Tidy up count it with the noisy links, and Tidy never makes it worse.

## The jacks' wires (*default*)
When the output is in phase with the guitar at one of the three frequencies with high gain between (`probe.jacks_in_phase`), the IN and OUT jacks' tip wires as drawn may run side by side (in one lane or the next, half a hole apart) for **10 mm at most** (`board-logic.js`' `APART_MM`). Further, a warning: "The input and output jacks' wires run side by side for 15 mm: …". The routes are the browser's (D-375: a wire is only lug + hole to the server), so the measure is there; the server says only whether the circuit needs it (`jacks_apart`). Wire it for me puts the input jack right and the output left, so this is rare: it comes when a builder drags a jack or bends a wire's run.

## The tuning (Fuzz Face and Big Muff, the user)
Measured with 2 seeds × 3000 steps of the search, on 2026-11-24:

| Starter | Inputs (later nets kept off) | Start board | Full layout without the cost | with it |
|---|---|---|---|---|
| Fuzz Face | Q1.B (4) | 1 pair | 7×9, 1 pair | 7×9, 1 pair |
| Big Muff Pi v3 | Q4.B (14), Q3.B (8), Q2.B (4) | 1 | 30×24, 0 | 30×24, 0 |
| Rangemaster | Q1.B (none) | 0 | 9×7, 0 | – |
| TS808 | Q1.B (15), IC1B.+ (15) | 1 | 44×17, 1 | 46×17, 0 |

At 3 columns a Fuzz Face of its size can't always keep clear: a warning the builder reads, not a bigger board forced. 2 columns would flag almost every pair of neighbours with a leg each; 4 lets a whole transistor's width run beside its input. The jacks' 10 mm is four holes: a wire crossing another's lane, or bending past it, never warns; one routed along it does.

## Out of scope
- Shielded wire, or the wires' length in themselves.
- Coupling between strips two apart, or through a part's body.
- Moving the jacks: Wire it for me already puts them on opposite sides.
