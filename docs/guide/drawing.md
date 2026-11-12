# Drawing a circuit

## Placing parts

Drag a tile from the parts palette onto the sheet, or click a tile and then click where the part goes. Each tile's tooltip gives its key: press the key and click to place one (R resistor, C capacitor, P pot, T trimmer, S switch, D diode, E LED, Q transistor, J JFET, U dual op-amp, O single op-amp, I guitar in, A amp out, V DC source, H DC jack, Y battery, K charge pump, X text, W wire, G ground, L net label). Esc puts a part down without placing it.

- **Space** turns the selected part a quarter turn.
- **Drag** a part to move it; its wires follow and keep their bends.
- A part **dropped on a wire** sits on it in series: the wire is cut and joined to its two pins.
- **Del** deletes what's selected. IN and OUT can't be deleted: every circuit has one guitar input and one amp.

Every part gets a ref (designator) of its kind with the next free number: R1, C3, VR2 (pot), TR1 (trimmer), SW1, D1, LED1, Q1 (any transistor), IC1, BAT1, J1 (jack). The DC jack is always DC. A dual op-amp is placed as both halves and its power unit (IC1A, IC1B, IC1C), and a switch with several poles as one part per pole (SW1A, SW1B…), all turned by one control.

## Wires

Pick the **Wire** tool (W). Click to start, click again to add a bend, and click a pin, a label or another wire to finish. Wires make square bends, go around parts, and hop over wires they cross without joining them. A dot marks each junction, where wires join.

- **Drag a ball** on a wire's end to move that end.
- **Click a wire** to select all of it, through its bends, to its ends. Drag a selected wire to move the stretch you grabbed; what it connects stays connected.
- A press on a pin's end, a label's point or a supply's point starts a new wire from there, whatever tool is picked.

## Names for nets: labels, ground and supplies

A *net* is everything joined together. Wires join things you can see; a name joins things anywhere on the sheet.

- **Net label** (L): every label with the same name is one net. Use it for a reference voltage (`VREF`), a filtered supply (`V+F`) or to avoid a long wire. Double-click a label to rename it.
- **Ground** (G): every ground symbol is the net GND.
- **V+** and **V-**: every V+ bar is the same net, driven by the Power menu (see [Power](power.md)). Placing a V- bar adds a negative supply.

Labels, grounds and supplies drag by their symbol or their name.

## Selecting, copying and undoing

- **Shift+drag** on empty space draws a box around what to select; Ctrl+Shift+drag adds to the selection. **Ctrl+click** (or Shift+click) adds or removes one thing. **Ctrl+A** selects everything.
- Dragging any selected part moves the whole selection.
- **Ctrl+C** copies, **Ctrl+V** pastes: the copy follows the pointer until you click where it goes. Pasting works across circuits; pasted parts are renumbered so no ref is used twice.
- **Ctrl+Z** undoes, **Ctrl+Shift+Z** (or Ctrl+Y) redoes. Undo puts back the selection too, so an undone move leaves the moved things selected.
- **History** (in the header, or Edit → History…) lists every step since the circuit opened, newest first. Click one to go back, or forward, to it.
- **Ctrl+F** (Edit → Find part…) selects a part by its ref and brings it into view.

**Right-click** anything for what can be done to it (Edit, Rotate, Add note…, Delete, Copy, Paste), followed by every header menu.

## Moving around the sheet

Scroll to zoom, drag empty space to pan. The **+**, **−** and **Fit** buttons at the bottom right, and the View menu, do the same; Fit shows the whole circuit.

## Editing a part

Double-click a part, or select it and press **Enter**, to open its form. **Apply** (or Enter) keeps the changes; **Cancel** (or Esc) leaves it as it was. Every Apply is one step to undo.

- **Value**: type it the way it's written on a schematic: `4k7`, `22n`, `2M2`, `100p`, `4.7k` and `4700` all work, and `u` stands for `µ`. A value the part can't have (`4k7F` on a resistor, `10F` on a capacitor) is refused with the reason. The value is kept in its standard form: `100uf` becomes `100µ`.
- **Slide**: a slider over the standard values from a tenth to ten times the value. The Frequency curve follows as you drag; letting go applies the value and runs again. It works on a sheet that can't be simulated yet, without the live curve.
- **Model**: for diodes, LEDs, transistors, op-amps and chips, the list of models in the library. See [Models](models.md).
- **ⓘ** at the top of a form says how to measure a value, what the datasheet's range is and the background, where a part has any.
- **Try** at the bottom compares several values or models at once. See [Frequency and knobs](frequency.md#trying-several-values).

Some forms have more:

- **Capacitor**: its *Kind* (film, ceramic, C0G, electrolytic, tantalum) and *Rating* in volts. The kind doesn't change the simulation; it's for the build, the voltage check and the advice in Problems. Help → **Choosing capacitors…** says which kind goes where.
- **Pot and trimmer**: value, taper (A log, B linear, C reverse log, W centre-tap), *Rotation* (where its knob starts when the circuit opens) and a label, which names its knob ("VR1 Volume"). A pot can be *Dual*: two gangs on one shaft, drawn as VR1A and VR1B. A trimmer can hold a voltage instead of a rotation: see [Bias & headroom](bias-and-headroom.md#a-trimmer-with-a-target).
- **Transistor and JFET**: the model's typical gain, or your own unit's measured figures. See [Germanium transistors](germanium.md) for why that matters.
- **Switch**: its *Type*, from the toggles, push buttons, footswitches, DIP switches and rotary selectors that are sold, or **Custom…** for your own poles, throws and what each position joins. *Position* is where it starts; name the positions (Vintage, Thick) and the names show on its buttons in Knobs.
- **Op-amps and chips**: the model (one per chip: changing it changes every half), and the pin numbers from the model's datasheet. The power pins are wired with labels like any pin; a single op-amp's offset and NC pins are drawn only when asked.
- **IN**: the pickup that loads the input (or *Buffered*, when nothing does), the guitar's volume pot, and a mono or stereo jack. **OUT**: the amp's input impedance (1 MΩ to start).

View → **Capacitor types** writes each capacitor's kind under its value on the sheet.

## Text on the sheet

The **Text** tile (X) puts a box of text on the sheet: an optional bold title and the text. It's saved with the circuit. For notes about a part or a net, the Notes pane is usually better: see [Notes](notes.md).

## When the circuit can't run yet

A half-drawn circuit often can't be simulated: a net with no DC path to ground, a chip with no power. Run then says *Can't simulate yet:* and why, and Problems lists what to fix. A part joined by only one pin is left out of the simulation and named in Problems, and the rest still runs.
