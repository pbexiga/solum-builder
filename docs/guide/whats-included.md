# What comes with the app

The app ships with classic pedals to open and study (**starters**), ready-made stages to drop into your own circuits (**core blocks**), and the SPICE models of the parts they use. Each starter's and block's own description, in the Notes pane once it's open, says more: its source, the parts it changed from the original, and what to try.

## Starters

File → **New from starter**. Every starter is a real pedal drawn from a published schematic, and most are checked against that source's measured or worked figures. Several come twice: the original, and Aion FX's kit version of it, which usually adds a switch or two. Starters are read-only; File → Save as… makes a copy you can change.

| Starter | What it is |
|---|---|
| Big Muff Pi (V3) | Electro-Harmonix's American V3 fuzz (1976-77), from ElectroSmash's schematic: a booster, two clipping stages, the passive tone control and an output stage. |
| Big Muff Pi (Aion Halo) | Aion FX's Halo, with the Gilmour '73 Ram's Head values and a Midrange switch (scoop, flat, hump). Text beside the drawing lists the parts to change for the other versions. |
| Boss BD-2 Blues Driver | Drawn from Boss's service schematic, with Boss's parts: two discrete op-amps sharing the Drive pot, diodes clipping between them, Tone, Volume, and an op-amp stage that lifts the bass. |
| Boss BD-2 (Aion Sapphire) | Aion FX's Sapphire, the stock circuit with true bypass, plus Aion's Bass knob (drawn at 0, the stock BD-2). |
| Boss DS-1 Distortion | The post-1994 DS-1 as ElectroSmash draws it: a transistor booster, an op-amp gain stage, two diodes clipping, a Big Muff-style Tone and Level. |
| Boss DS-1 (Aion Comet) | Aion FX's Comet, with the pre-1994 values and a Mode switch for the clipping (the stock diodes, red LEDs, or two diodes each way). |
| Dallas Rangemaster (OC44) | The 1965 treble booster: one germanium PNP on a positive-ground supply, from ElectroSmash's analysis. |
| Fuzz Face (AC128) | The Arbiter Fuzz Face with two AC128 germanium PNPs, positive ground, from ElectroSmash's schematic, at the gains it measured. |
| Klon Centaur | The 1994 overdrive as ElectroSmash draws it: a dual Gain pot that turns up a clipping stage while it turns down a clean copy, a summing amp, Treble and Level, with a charge pump making the higher rails. |
| Klon Centaur (Aion Refractor) | Aion FX's Refractor: the same idea with Aion's parts (BAT41 Schottkys for the germanium diodes); the effect and its power only. |
| Klon Centaur (Aion Refractor, with footswitch) | The Refractor drawn whole, its true or buffered bypass board and footswitch included. |
| Marshall Bluesbreaker | The first, black-box Bluesbreaker, from General Guitar Gadgets' replica: two op-amp stages sharing the Gain pot, soft clipping, Tone and Volume. |
| Marshall Bluesbreaker (Aion Cerulean) | Aion FX's Cerulean, with true bypass and the King of Tone's extras: a Clipping switch (soft, none, hard), a Mode switch between the old and new values, and a Gain DIP. |
| MXR Dyna Comp | The 1972 compressor as ElectroSmash draws it: an OTA whose gain an envelope detector turns down as you play harder; Sensitivity and Output. |
| MXR Dyna Comp (Aion Aurora) | Aion FX's Aurora: the Dyna Comp and Ross with an LM13700, a Release knob and a Treble switch. |
| ProCo Rat | From ElectroSmash's schematic: an LM308 gain stage, diodes clipping to ground, the Filter control and a JFET output buffer. |
| Tone Bender MkII (germanium) | The 1966 Sola Sound fuzz as Fuzz Central traced an original: three germanium PNPs, positive ground, fixed bias, Level and Attack. |
| Tone Bender MkII (Aion Deimos, Mode switch) | Aion FX's Deimos: bias trimmers, and a Mode switch between the MkII and the earlier two-transistor "1.5", much like a Fuzz Face. |
| Ibanez TS808 Tube Screamer | The true-bypass TS808 from ElectroSmash's schematic: a buffer, the soft-clipping op-amp stage, Tone and Level. |

## Core blocks

Blocks → **Insert or manage blocks…** (or press B). A block is a small, named circuit: click it, then click on a wire to splice it in, or on empty sheet to place it. Its parts are renumbered so they don't clash, and its description arrives in the Notes pane. See [Blocks](blocks.md).

Blocks that bias from a mid-supply voltage have a **vref** port: wire it to the Vref divider. The power blocks are listed here too; [Power](power.md) explains them.

### Gain, clipping and tone

| Block | What it is |
|---|---|
| Gain stage · JFET (Fetzer Valve) | Run Off Groove's one-JFET gain stage, with a trimmer the app sets to put the drain at 4.5 V, and a Volume pot. |
| Gain stage · op-amp (TS808) | A non-inverting op-amp stage with the Tube Screamer's values: about 21.5 dB, less in the bass. Add diodes across its feedback for a clipper. |
| Gain stage · Big Muff (BJT, soft clipping) | One of the Big Muff's clipping stages: a transistor with diodes in its feedback. Delete the diodes for the input booster. |
| Treble booster · Rangemaster (germanium) | The Rangemaster's single germanium PNP on a negative supply. Put it first: it needs the guitar's pickup driving it. |
| Clipper · diodes to ground (Rat) | The Rat's clipper: a resistor and two diodes back to back to ground. Swap the diodes to change where it clips. |
| Clipper and tone · Tube Screamer (TS808) | The Tube Screamer's heart: the soft-clipping stage with Drive, then the low-pass and active Tone control. |
| Distortion stage · ProCo Rat (gain, clipper, filter) | The Rat's LM308 gain stage with Distortion, its hard clipper and the Filter knob. |
| Tone stack · Big Muff | The Big Muff's passive tone: a low-pass and a high-pass blended by one pot, scooped at noon. It needs a high-impedance load. |
| Tone stack · Fender TMB | Fender's treble-middle-bass stack with blackface values. It loses 15-20 dB and needs a low source impedance and a high load. |
| Tone stack · Baxandall (bass, treble) | The classic active bass and treble control from a Texas Instruments application note, flat with both knobs half-way. |
| Tone stack · Baxandall (bass, mid, treble) | The same with a Mid control, from a Texas Instruments data sheet. Put a buffer before it when it follows a pot or the guitar. |

### Buffers and bypass

| Block | What it is |
|---|---|
| Buffer · JFET (ProCo Rat) | The Rat's output buffer: a JFET source follower to drive a volume pot and a cable. |
| Buffer · op-amp (Klon) | The Klon's input buffer: an op-amp follower the guitar sees as about 1 MΩ. |
| Buffer · transistor (Boss DS-1) | Boss's emitter-follower buffer, used at both ends of the DS-1. |
| Bypass · true (3PDT footswitch) | A 3PDT footswitch wired as true bypass, with its LED; your circuit's input is grounded when bypassed. Flip it in Knobs & switches. |
| Bypass · buffered (JFET buffer + 3PDT) | A JFET buffer in front of the true-bypass footswitch, so the guitar always sees a high input impedance. |
| Bypass · Klon, true or buffered (3PDT switch + 3PDT footswitch) | The Klon's bypass, after Aion FX's Refractor: a switch picks true or buffered bypass, the footswitch turns the effect on. |

### Power

| Block | What it is |
|---|---|
| 9 V power · DC jack and battery | A DC jack and a battery, with the reverse-polarity diode and the supply filter. Pick which one feeds it in Knobs & switches. |
| 9 V power · battery only | A battery feeding the supply filter, for a pedal with no DC jack. It swaps with the block above. |
| 9 V power · supply filter | The reverse-polarity diode and the filter between the jack (V+) and the circuit (V+F), from the Rat. |
| Vref · half-supply divider | Two equal resistors and a capacitor: the mid-supply voltage op-amp and JFET stages bias from. |
| Charge pump · doubler, chip (TC1044S) | A charge-pump chip doubling the 9 V to about 17.5 V for stages that want more headroom. |
| Charge pump · inverter, chip (TC1044S) | The same chip making about -9 V, for a ± supply. |
| Charge pump · doubler and inverter, chip (LT1054) | One chip doubling and inverting at once, as the Klon does. |
| Charge pump · doubler, op-amp (no chip) | A doubler built from an op-amp oscillator and two diodes, to see how one works. Checked in simulation only, not a tested build. |
| Charge pump · inverter, op-amp (no chip) | The inverter built the same way. Also checked in simulation only. |
| 12 V supply · charge pump and zener | The doubler with a resistor and a 12 V zener after it: the simplest regulator, to learn how one works. |
| 12 V supply · charge pump and regulator (78L12) | The doubler with a 78L12 regulator, holding 12 V whatever the circuit draws. |

## Models

Tools → **Parts and datasheets…** lists every model the app simulates with: transistors, JFETs, MOSFETs, diodes, LEDs, op-amps, OTAs, charge pumps and regulators, each with its datasheet and where the model came from. Most are the app's own, fitted to the maker's datasheet; some are the maker's own models. A few well-known models can't be shipped because of their terms; the list names them and where to get them. See [Models](models.md).

## Help sheets

The Help menu's reference sheets (choosing capacitors, the resistor colour code, formulas) come with the app too. See [Tools and help sheets](tools.md).
