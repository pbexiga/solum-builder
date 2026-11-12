# Models

Every diode, LED, transistor, JFET, MOSFET, op-amp and chip is simulated from a **model**: a SPICE card that describes how that part number behaves. Pick one in the part's form (**Model**). Resistors, capacitors and pots need none: they're simulated as their values.

## Parts and datasheets

Tools → **Parts and datasheets…** lists every model the app simulates with, grouped by kind (transistors, JFETs, diodes, op-amps…), each with a one-line description and a link to its datasheet (**Datasheet ↗**, the maker's or an archive's copy). Type in **Find** to narrow the list. Open one for where it came from, what its datasheet covers, where the model is a guess, its package and pin numbers, and the checks it passed.

Each model is tagged with where its card came from:

- **Our fit**: our own model, fitted to the maker's datasheet.
- **Maker's model**: the maker's own SPICE file.
- **Library card**: the maker's card as published in a SPICE library, checked here against the datasheet.
- **Estimate**: not a fit (no datasheet curves to fit to). Measure your part and enter its figures.
- **Yours**: one you added.
- **Not included**: a card that can't be shipped with the app (its terms don't allow it). Its ⓘ says whose it is, which file to get and where, and to add it with Tools → Add a model.

**Yours**, **Stock** and **Not included** show or hide each set.

## A part is more than its model

A model is one typical part. Real ones vary: a J201's Idss runs from 0.2 to 1 mA, a 2N5089's gain from 400 to 1200, a germanium transistor's leakage by several times. The ⓘ on a transistor's or JFET's form gives the datasheet's range.

- **Transistor**: under **Gain**, pick *your unit's (measured)* and enter its hFE (and leakage, for germanium).
- **JFET**: under **Idss and Vp**, pick *your unit's (measured)* and enter what you measured. Better still, give it a **Drain target** and a bias trimmer, and let the app set the trimmer as you would on the bench (see [Bias & headroom](bias-and-headroom.md#a-trimmer-with-a-target)).

[Germanium transistors](germanium.md) shows what this changes on a Fuzz Face and a Tone Bender.

**At rest**, on a transistor's form, can be set to *off by design* for a part that's meant to sit off with no signal (a compressor's envelope rectifier): Problems then doesn't call it cut off.

## Adding a model

Tools → **Add a model…** adds a part from a maker's SPICE file (`.lib`, `.mod`): a diode, LED, transistor, JFET or MOSFET `.model` card, or an op-amp `.subckt`.

1. Choose the **File**. If it holds several models, pick one.
2. Say what it is (diode, LED, transistor, JFET, MOSFET or op-amp) and give it a **Name in Solum Builder** (*2N3904-mine*).
3. For an op-amp, say which pin is on each of its nodes, in the order its `.subckt` line gives them. They start in the usual order (+, −, V+, V−, out); the maker's comment above the line is shown, since makers often say otherwise. The check wires it as a buffer and tells you if the order looks wrong.
4. The app cleans the card for the simulator (it says what it changed) and measures it: a transistor's gain, a diode's forward voltage, and so on. A reading that looks wrong for that kind of part is flagged: check the card is the part you meant.
5. **Add to my models**. It's in the model lists at once, and in Parts and datasheets as *Yours*.

Your models are kept in the data folder with your circuits, on this machine. A model you add has no package or pin numbers, so the parts list can't say which leg is which (Problems notes it under *Before you build*).

## A circuit naming a model you don't have

A circuit made on another machine may name a model that isn't in your library. It still opens and draws; Problems says which model to add (*Model not in the library*), and it won't simulate until you add it or pick another in the part's form.
