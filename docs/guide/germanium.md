# Germanium transistors

Germanium transistors vary a lot from one unit to the next: two AC128s from the same bag can differ in gain by three times, and leak very different currents. A germanium fuzz is biased around the units in it, so in Solum Builder each transistor has two things you can set:

- **Model**: the card that gives the transistor's shape: how its base voltage, its gain at different currents and its treble behave. The germanium cards are the AC128, OC71, OC44, OC75 and OC81D (the OC81D is an estimate: its form says so), plus the 2N404 and 2N1308.
- **Gain and leakage**: *the model's (typical)*, or *your unit's (measured)*: the hFE and leakage you read off your own transistor.

The figures below were simulated on the starters; every one, per card and per starter, is in the [germanium study](germanium-study.md).

## Measure first

Use a Geofex-style tester (9 V, the collector through 2.4 kΩ, 2.2 MΩ from the base to the supply):

1. **Leakage:** base open, read the collector current (the volts across the 2.4 kΩ ÷ 2.4 kΩ). Let it settle; a warm finger raises it. 100–200 µA is common, over 300 µA suspect, over 500 µA bad.
2. **Gain (hFE):** with the 2.2 MΩ connected, the collector current less the leakage, divided by the base current (about 4 µA).

The form's ⓘ next to each field says the same.

## Enter your unit's figures

1. Select the transistor and open its form.
2. Under **Gain and leakage**, pick *your unit's (measured)*.
3. Type **Measured hFE** (a plain number) and **Measured leakage** (in µA).

The starters already ship like this, with figures from the middle of their source's ranges (the Tone Bender's Q3: hFE 108, leakage 175 µA). Replace them with yours before trusting a bias reading.

## Swap the model

Pick another card in **Model**. If the part has measured figures, they stay: only the card's shape changes. To see a card's own typical unit instead, pick *the model's (typical)*.

## What a swap changes

**With your measured figures kept, the bias barely moves.** The Fuzz Face's Q2 collector reads −4.67 to −5.30 V on any of the four main cards; the Tone Bender's bias trimmer still reaches its target, only at a different turn (0.18 on the AC128 to 0.50 on the OC44). The clipping level moves under 3 dB.

**The treble is what changes**, through each card's collector capacitance (AC128 100 pF, OC71 40 pF, OC75 50 pF, OC44 10.5 pF). The Rangemaster, a treble booster built round the OC44, gains 35 dB at 5 kHz on its OC44 and 29 dB on an AC128: 6 dB less top end. The Fuzz Face at 20 kHz: 29 dB on its AC128, 41 dB on an OC44.

**With the card's own typical figures, the circuits come apart,** as builders know: the Fuzz Face's Q2 collector goes from −5.18 V (OC44) to −8.06 V (OC75, Q2 nearly off), and the Tone Bender's trimmer can't reach its target with the AC128's, OC75's or OC44's own figures. That's what measuring is for: **the measured hFE and leakage carry the bias; the card shapes the base voltage and the treble.**

## The guitar's volume

A Fuzz Face cleans up well as you roll the guitar's volume back: by volume 6 it's clean, only 6 dB quieter. The guitar's volume pot works straight into its low input impedance.

A Tone Bender MkII has a boost stage (Q1) in front of a Fuzz Face pair, which makes up for the pot's loss, so it cleans up less. How much depends on its bias:

- **As the starter is set** (TR1 holding Q2's collector at −0.16 V, a leaky Q1 at 200 µA) it stays fuzzy at every guitar volume.
- **At the low-gain end of Aion's settings** (TR1 at its 3:00 start, a Q1 leaking about 100 µA), with Fuzz down and a soft touch, turning the guitar to 4 takes the fuzz out and leaves a fat, warm tone: the 3rd and higher harmonics drop from 52 % to 13 %. It never gets as clean as a Fuzz Face: a Tone Bender's output pair adds 2nd harmonic even at low levels.

To try it: open the Tone Bender MkII and make a copy. In the guitar input's form (IN), pick the *Strat single coil* pickup. Select TR1, remove its bias target and turn it to 85 %; set Q1's measured leakage to 100 µA; turn Fuzz down in Knobs. Probe the output, set the pick level to *Soft*, and watch the Harmonics pane as you turn the guitar's volume (in Knobs too) from 10 to 4: the odd ones (3rd, 5th…) fall away and the 2nd stays.

The Rangemaster is nearly clean already: its guitar volume works as a level control.
