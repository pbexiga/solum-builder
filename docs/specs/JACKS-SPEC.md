# Jacks and their cables — spec

## Goal
The user (2026-11-16), after drawing a stereo input jack switching the battery:
1. **Visually**, a jack should connect to the middle of the IN (guitar) symbol and to the end of the OUT (amp) symbol, so the drawing reads "the guitar plugs in here" and "the amp's cable plugs in here".
2. **With the input cable out the pedal is off**: no battery and no signal (a real pedal has no guitar in it), and no sound from a render.

## Before
A `jack` (J1…) was drawing only (D-174): out of the netlist, its pins just points that wires join. A stereo jack had a cable in/out switch whose out only opened the ring through 1 TΩ (D-185). The signal still flowed from IN, so a render with the cable out was about 43 dB quieter, not silent, and the op-amp rules named a phantom supply.

## What was built

### A plug point on IN and OUT, for jacks only (D-353)
- IN has a **plug point** in the middle of its circle and OUT one at the tip of its triangle. Each is the same node as the part's pin (`parts.py` `PLUGS`, `symbols.js` follows); nothing changes electrically. No separate mark: the wire tool's target ring snaps to the point and a wire ending there gets a pin's dot; a plain click there still selects the part.
- Only a jack's T may join it, by its pin on the point or by a plain run of wire. Anything else (a label, another pin, a branch, a wire passing over) is refused with the reason over the canvas: *"Only a jack's T plugs into the middle of IN. Wire other parts to IN's pin."* (`connectivity.plug_problem`).

### What a jack switches (D-354, D-355; `solum/circuit/cables.py`)
- **Input**: its T on the guitar's net. **Output**: its T on the amp's net. **Ring**: a stereo jack with its R and S both wired: a switch, closed only by a mono plug. **Battery**: a ring that carries the battery's − (not on ground).
- A jack with none of these roles switches nothing.
- What's in the jack is three-way for a stereo jack (`plug`: `mono`, `stereo`, `none`; schema v31, migrated from `plugged`), two-way for a mono jack (`mono`, `none`). A stereo cable's ring is its own, so it leaves the jack's ring open.
- Each switching jack gets a switch in Knobs & switches, named by its label (*Input cable*) or ref (*J1 cable*): *Mono cable / Stereo cable / Cable out*, or *Cable in / Cable out*.

### What a cable out does
- **Battery**: a battery on a ring with no mono plug is cut off for real: 0 V in the netlist, DC about 0 V, and the chip beside the Power menu reads *Battery · cut off*. When nothing else supplies the circuit (no part on a rail the Power menu holds, no DC source; the battery's + on V+ or on a net of its own), Problems warns **Battery cut off: no mono cable in** (`battery-cable-out`) and checks only the drawing (no op-point rules about a pedal that's simply off) (D-357).
- **Input or output with no cable**: no curves, scope or live curves; each pane says which jack and what it cuts (*"J1 has no cable in: no guitar reaches the pedal and its battery is cut off."*). A render or render sweep is **refused** with that reason and *"Put its cable in (Knobs) to render."* (the user: "just don't render at all").
- **A cut-off battery alone** (a stereo cable in the input, or a ring jack that isn't the input) isn't refused: the guitar still reaches the circuit, simulated unpowered, so a true bypass still passes it (the user asked).
- **No rule for mono jacks** (the user: they don't need one). A loose jack, on neither IN nor OUT, never blocks a render.
- A DC plug in (the DC jack's Power switch) powers the pedal whatever the input jack's ring does.

### Blocks (D-356)
*9 V power · battery, switched by the input jack* and *9 V power · DC jack and battery, switched by the input jack*: the two battery blocks with the battery's − on J1's ring and J1's T as the `in` port, to wire to IN's middle. The no-jack blocks stay, as the simplest way to hear a circuit.

## Out of scope
- Plug insertion clicks, or a mono plug in a stereo jack shorting anything but ring to sleeve.
- The rest of a jack as an electrical part. Only its ring-to-sleeve contact is simulated (a switch a mono plug closes, `netlist._jack`); its T and S are junctions like a wire, and a cable out of the input or output is decided from the jack's role, not opened in the netlist (a missing guitar or amp stops the render anyway). Not modelled: switched lugs (a contact the plug pushes away, such as one grounding an unused input), contact resistance.

## Decisions
D-353 (plug points), D-354 (a cable out simulated, renders refused), D-355 (mono, stereo or none; a ring is a switch; schema v31), D-356 (the blocks), D-357 (off with nothing else supplying it; the chip). They narrow D-174 and D-185.
