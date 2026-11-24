# Quiet links: keeping links away from sensitive nodes (P6h5e–f)

The user, 2026-11-24: links running under parts may add noise. Agreed (option A): keep links
under parts where the risk is low, and keep them away from the nodes where a small pickup
gets amplified. With it, the high-gain input limit (D-400) is narrowed to the parts in series
with the signal: the Klon's six-part group was too strict.

## The goal
A board where no link runs under or right beside a sensitive node's parts, laid out that way
by Start a board, Tidy up and *Build a full layout*, warned about when a hand-made board does
it, never refused.

## What the builder gets
- In *Warnings*, a link too near a sensitive node says so, in words: "The link from J4 to J9
  runs under R2, on Q1's base (the high-gain stage's input): move it a column or two."
- Start a board, Tidy up and *Build a full layout* lay links clear of them where they can,
  as they follow the placement limits (D-400).
- Fewer, more meaningful high-gain input warnings: only the parts in series with the signal.

## How it works
- **Sensitive nets** (from what D-400 already measures, `probe.loud_inputs`): the net each
  high-gain stage's signal enters by (a base, a gate, an op-amp's + input), for each stage
  whose own gain reaches 10× with the pots as set, all down or all up. No simulator, or a
  circuit that doesn't simulate: none, as D-400.
- **The rule**: a link may not pass under, or have an end or a passing hole in the hole beside
  (on the same strip, either side), a leg or body of a part on a sensitive net; nor pass
  under a chip whose high-gain input pin is on it. A link of the sensitive net itself is let
  be (it is that node). Links under other parts stay allowed (D-401).
- **Loud nets** (a charge pump's switching pins, a high-gain stage's output) need no rule of
  their own: they can only reach a sensitive node through a link near its parts, which the
  rule above already keeps away.
- **Where it lives**: one check, beside the placement limits (`limits.py` or its own module),
  read by the board check's warnings, the guidance's suggested links, Start a board's links,
  Tidy up's guard (never break one the board met) and the search's cost (a broken one costs
  as a broken placement limit).
- **The input limit narrowed** (D-400 amended): the parts kept by a high-gain input are those
  in series with the signal: a part whose other leg isn't on a rail, ground or a DC reference
  net (the bias resistors to Vref or ground drop out).

## Out of scope
- Impedance at every node (the app works out the input's and the output's only): a
  high-impedance node with no gain after it isn't flagged.
- Discrete op-amp stages (D-224), as D-400.
- Shielded wire, ground planes, star grounding advice.

## Decisions it will need
- D-402: quiet links (the sensitive nets, the rule, warnings not refusals, which code follows
  it); D-400 amended (the input limit to the series parts).

## Answered (the user left all three to the agent, 2026-11-24)
1. **"Beside" is one hole in any direction**: no link end or passing hole in, or in any of
   the eight holes round, a leg or body hole of a part on a sensitive net. Coupling falls
   off quickly with distance, so one hole of clearance does most of the good; it covers the
   strips above and below too, which a link running down a column passes.
2. **A DC reference net is read from the simulation, not from names**: the AC run
   `loud_inputs` already makes gives every net's signal; a net whose signal at the tone is
   below 1 % (−40 dB) of the stage's input signal is AC-quiet (rails, ground, Vref behind
   its big cap all are). A part on the input net whose other leg is on an AC-quiet net is
   biasing it, not carrying the signal: it drops out of the input limit.
3. **Lighter than a placement limit, heavier than the board's size**: in the search's
   cost a broken quiet-link rule is 500 (a placement limit 2000, area ×100 a hole); in
   choosing the best board, placement limits broken first, then quiet links broken, then
   the area. Tidy up never breaks one the board met; Start a board avoids them where a
   link has another free column.

## As built (2026-11-24; D-400 amended, D-402)
- `solum/stripboard/quiet.py` owns the rule; `probe.loud_inputs` gives each input with the nets AC-quiet beside it (`LoudInput`).
- Beyond the answers above: **a link on an AC-quiet net (ground, a rail, Vref) is let be**, as nothing on it can be picked up (most links are rail links). A part counts by its legs on the sensitive net and its body; a chip by its input pin and the holes between its rows.
- Start a board takes a quiet column only where another is free (pushing links further right made boards much bigger) and ranks noisy links after size.
