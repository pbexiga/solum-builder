# Germanium study

What swapping a transistor's model changes: the full figures behind [Germanium transistors](germanium.md), per card and per starter. Simulated in Solum Builder's own pipeline (ngspice) on 2026-11-03; the cards are D-170 (AC128), D-184 (OC71, OC44, OC75) and D-186 (OC81D, estimated). The scripts and raw output are in `.claude/skills/fit-model/worked/germanium/` (local, gitignored): `compare.py`, `compare_ac.py`, `volume.py` and their `out_*.txt`.

**Two ways to swap.** *Measured kept*: the part keeps its measured hFE and leakage (the transistor form's *your unit's (measured)*, D-130), so only the card's shape changes: VBE, how gain varies with current, the leakage split and the capacitances. *Card's own*: the measured values are removed and the card's typical unit is simulated. Starters ship with measured values (the middle of the source's ranges), so the first is what a builder sees.

Card figures on the Geofex tester (gain / leakage): AC128 91.5 / 315 µA, OC71 60.1 / 200 µA, OC44 94.6 / 32.7 µA, OC75 86.2 / 370 µA, OC81D 29.7 / 143 µA. Collector capacitance: AC128 100 pF, OC71 40 pF, OC75 50 pF max, OC81D 40 pF max, OC44 10.5 pF.

## 1. Measured kept: the bias barely moves

| Starter | Node | AC128 | OC71 | OC75 | OC44 |
|---|---|---|---|---|---|
| Fuzz Face | Q2 collector | −5.30 V | −4.93 | −5.01 | −4.67 |
| Fuzz Face | Q1 collector | −0.50 V | −0.56 | −0.54 | −0.62 |
| Tone Bender MkII | Q1 collector | −7.32 V | −7.42 | −7.39 | −7.56 |
| Rangemaster | Q1 collector | −6.66 V | −6.72 | −6.69 | −6.76 |

ElectroSmash gives −4.5 V and −0.7 V for the Fuzz Face's two collectors; every germanium card sits a little closer than the AC128. In the Tone Bender, TR1 still sets Q2's collector to −0.16 V with every card; only its rotation moves (0.18 AC128, 0.27-0.30 OC75, 0.34 OC71, 0.50 OC44). With the OC81D in all three places: Q1 −7.39 V, TR1 0.30, the same as the OC75.

## 2. Measured kept: the clip level barely moves

200 Hz, the app's soft (0.1 V) and hard (1.0 V) picks, at the output:
- Fuzz Face: within 1.4 dB soft and 2.6 dB hard across the four cards; peaks within ~15 %; the OC71 clips a little softer (THD 1.32-1.36 against 1.42-1.72).
- Tone Bender: within 0.1 dB soft, 0.9 dB hard. OC81D against OC75: within 0.03 dB.
- Rangemaster: clean gain 12.7-13.0 dB, hard 10.2-10.5 dB.

## 3. Measured kept: the treble is what changes

Small-signal gain at the output (dB), where the collector capacitance shows:

| Starter | Card | 100 Hz | 1 kHz | 5 kHz | 20 kHz |
|---|---|---|---|---|---|
| Rangemaster | AC128 | 6.8 | 24.9 | 29.0 | 29.2 |
| Rangemaster | OC71 | 7.0 | 25.7 | 30.7 | 31.1 |
| Rangemaster | OC75 | 6.7 | 25.5 | 31.0 | 31.4 |
| Rangemaster | OC44 (the starter's) | 6.6 | 26.3 | 35.0 | 36.3 |
| Fuzz Face | AC128 (the starter's) | 38.1 | 42.5 | 39.0 | 29.1 |
| Fuzz Face | OC44 | 37.8 | 42.1 | 42.1 | 41.2 |
| Tone Bender | AC128 | 44.8 | 67.6 | 59.6 | 47.6 |
| Tone Bender | OC75 (the starter's) | 43.5 | 65.1 | 61.6 | 51.0 |
| Tone Bender | OC81D | 43.5 | 65.1 | 63.0 | 53.7 |
| Tone Bender | OC44 | 44.5 | 66.1 | 66.2 | 62.0 |

The Rangemaster is a treble booster built round the OC44; on the AC128 (100 pF) it loses 6-7 dB of its top end.

## 4. The card's own values: the circuits diverge, as builders know

- Fuzz Face Q2 collector: −8.00 V (AC128; Q2 nearly off), −6.15 (OC71), −8.06 (OC75), −5.18 (OC44).
- Tone Bender: TR1 can't reach −0.16 V with the AC128's, OC75's or OC44's own values (Q2's collector only moves between −0.04 and −0.10 V, or −0.21 and −0.44 V for the OC44); the OC71's own (gain 60, leakage 200 µA, near Aion's middle readings) and the OC81D's (gain 30) do.

So the measured hFE and leakage carry the bias; the card shapes VBE and the treble. Measure your transistors (Geofex tester, D-130) before trusting a germanium bias.

## 5. The guitar's volume: how much each cleans up

A real pickup (the pickup guide's Strat single coil and PAF humbucker) through the guitar's 250K audio-taper volume pot, medium pick (0.3 V at the pickup), 200 Hz, measured kept. Output level against volume full, and THD:

| Starter (card) | Volume 10 | 8 | 6 | 4 |
|---|---|---|---|---|
| Fuzz Face (AC128), Strat | 0 dB, THD 48 % | −1.0 dB, 9 % | −6.0 dB, 0.2 % | −8.2 dB, 0.1 % |
| Fuzz Face (AC128), PAF | 0 dB, 43 % | −1.3 dB, 8 % | −6.3 dB, 0.2 % | −8.5 dB, 0.1 % |
| Tone Bender (OC75), Strat | 0 dB, 58 % | −0.7 dB, 68 % | −0.5 dB, 63 % | −0.2 dB, 58 % |
| Tone Bender (OC75), PAF | 0 dB, 54 % | −0.8 dB, 68 % | −0.6 dB, 63 % | −0.3 dB, 58 % |
| Rangemaster (OC44), Strat | 0 dB, 2.6 % | −4.6 dB, 1.3 % | −11.6 dB, 0.5 % | −22.0 dB, 0.2 % |

- The Fuzz Face cleans up: by volume 6 it's clean at only 6 dB down. The pot's resistance in front of its low input impedance does it.
- The Tone Bender MkII, as the starter is set, doesn't: it keeps clipping at every volume and its output hardly drops. At the low-gain end of Aion's settings it does, as players describe it (see below).
- The Rangemaster is nearly clean already; the volume is a level control.
- The card makes no difference here: on the AC128 or the OC81D the Tone Bender's and Rangemaster's figures are within 0.1 dB and the same THD.

The pickup barely matters at these settings (Strat against PAF within 0.3 dB).

### The Tone Bender's clean-up: explained (2026-11-04, 9d2)

Owners and builders say a MkII cleans up with the guitar's volume, best at low Fuzz ([effectsdatabase, Lumpy's MkII](https://www.effectsdatabase.com/model/lumpy/tonebender/mk2); [Equipboard owners' notes](https://equipboard.com/items/sola-sound-tone-bender-professional-mkii)). These are reports, not measurements; no published figure says how much. The starter matches Aion's Deimos schematic part for part (the output is taken at R5's 470 Ω end, as drawn), so the wiring isn't the gap. What the simulation shows:

**1. The starter sits at the high-gain end of Aion's settings.** Gain at 1 kHz, `in` to `out` (`.claude/skills/fit-model/worked/tone-bender/gains.py`):

| Setting | Fuzz full | Fuzz min | Q3's collector, idle current |
|---|---|---|---|
| Starter (TR1 solved for Q2's collector at −0.16 V) | 65 dB | 45 dB | −7.86 V, 120 µA |
| TR1 at Aion's starting 3:00 (Q2's collector −0.09 V) | 44 dB | 33 dB | −8.39 V, 66 µA |
| Starter, Q1 leakage 50 µA (Aion's "high leakage" starts at 100) | 54 dB | 33 dB | as the starter |
| Starter, R1 10k (Aion: "some versions use 10k") | 56 dB | 36 dB | as the starter |

Q1 adds 20-24 dB in front of the Fuzz Face pair (Q2, Q3), and only Q1 sees the guitar's volume pot. A Fuzz Face cleans up because the pot works straight into its low input impedance; in the MkII the same attenuation happens in front of Q1, and Q1's gain makes it up. Q3's leakage and hFE change nothing here (under 0.5 dB).

**2. Small signals bend in the output pair, mostly as 2nd harmonic.** With Aion's readings Q3 idles at about 100 µA (its emitter at −0.1 V on the 1K Fuzz pot), so its own feedback is weak (gm × 1 kΩ ≈ 5) and its base-emitter junction bends the wave from about 0.3 mV at the input: at 0.1 mV in, the output is 10 mV with 11 % THD, the 2nd harmonic −22 dB and the 3rd −40 dB, rising from Q2's collector on (`.claude/skills/fit-model/worked/tone-bender/where.py`). Q2's collector, only 0.1-0.2 V from its emitter in Aion's readings, can swing little towards it. A real MkII biased to Aion's figures has the same idle currents, so it isn't a hi-fi "clean" at any setting.

**3. What turning the guitar down changes.** Strat through the 250K audio volume pot, 200 Hz, the 2nd harmonic and the rest (3rd-8th, rms) at `out` (`.claude/skills/fit-model/worked/tone-bender/orders.py`):

| Setting, pick | Volume 10 | 6 | 4 | 2 |
|---|---|---|---|---|
| Starter, Fuzz min, 0.1 V | 0 dB, h2 27 %, h3+ 51 % | −0.0 dB, 9 %, 45 % | −0.6 dB, 32 %, 29 % | −1.6 dB, 44 %, 11 % |
| Starter, Fuzz full, 0.1 V | 0 dB, 27 %, 52 % | +0.3 dB, 3 %, 53 % | +0.2 dB, 19 %, 53 % | 0 dB, 33 %, 50 % |
| TR1 3:00, Q1 100 µA, Fuzz min, 0.1 V | 0 dB, 2 %, 52 % | −0.6 dB, 34 %, 36 % | −3.7 dB, 55 %, 13 % | −7.6 dB, 55 %, 13 % |
| TR1 3:00, Q1 100 µA, Fuzz min, 0.3 V | 0 dB, 37 %, 49 % | +0.3 dB, 16 %, 51 % | +0.3 dB, 7 %, 48 % | 0 dB, 28 %, 40 % |
| TR1 3:00, Q1 50 µA (under Aion's range), Fuzz min, 0.1 V | 0 dB, 15 %, 51 % | −1.5 dB, 52 %, 20 % | −7.7 dB, 56 %, 14 % | −12.7 dB, 55 %, 15 % |
| Fuzz Face, Fuzz full, 0.1 V | 0 dB, 4 %, 37 % | −15.9 dB, 0 %, 0 % | −18.1 dB, 0 %, 0 % | −18.7 dB, 0 %, 0 % |

At the low-gain end of Aion's ranges (TR1 at 3:00, Q1 at the bottom of its 100-300 µA) and low Fuzz, played softly, the guitar's volume takes the fuzz out (the 3rd and higher harmonics fall from 52 % to 13 % by volume 4) and leaves a fat, even-harmonic tone, a little quieter: that matches "cleans up, best at low Fuzz" as players hear it. A medium pick (0.3 V) keeps it fuzzing until volume 2. The starter, at the high-gain end and with a leaky Q1, doesn't. It never gets as clean as a Fuzz Face. THD alone hid this: it counts the 2nd harmonic, which grows as the fuzz goes.

**So:** a gap of setting, not of the simulator. The starter keeps TR1's target (Q2's collector at −0.16 V, inside Aion's −0.15 to −0.25 V reading); TR1 at Aion's 3:00 or a less leaky Q1 is where the clean-up is. The acceptance file says so (`omitted`). Earlier scripts: `.claude/skills/fit-model/worked/germanium/tb_cleanup.py`, `tb_osc.py`, `tb_fuzzpot.py`.
