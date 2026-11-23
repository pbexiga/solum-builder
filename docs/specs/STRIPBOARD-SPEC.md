# Stripboard: a guided editor

What was built in P6 (2026-11-19 to 2026-11-23), and why. The decisions are D-367 to D-394; where one disagrees with this page, the decision wins.

## Goal
A builder plans their stripboard (Veroboard) **in the app, before soldering**, guided by the circuit: every part the board needs, where each leg must connect, mistakes caught as they're made, and a board that is **checked against the circuit** before it goes in the build package. No PCB (the user, 2026-11-19).

## Why an editor (D-368)
Laying out the whole board automatically was tried first. Small circuits laid out well, but a ~40-part circuit didn't: a plain search found no fault-free TS808 or Rat, and a CP-SAT trial (OR-Tools) found a checked TS808 only in minutes on 8 cores, not the same twice. The tools builders use (VeroRoute, VeeCAD, DIY Layout Creator) don't lay out a board either: the builder places the parts and the tool shows what's unconnected, stops shorts and checks at the end. That is the shape here, with what they lack: no netlist import (the circuit is already open), the check free and in plain English, placement limits, a changed circuit named rather than a broken board, and the board in the build package. Automatic layout is help (*Start for me*, *Tidy up*); a better layout is a feature of its own, still to come (*The starters*, below).

## The parts of it
- **The board model** (`solum/stripboard/board.py`, D-367): holes 0.1" apart, strips along the rows, cuts at holes, links down a column, off-board parts beside the board joined by wires; a board's plain form (`layout_from_data`, `layout_data`) is what the circuit file holds.
- **The footprints table** (`library/guides/footprints.yaml`, `footprints.py`, sourced): each board part's leg spacing and body, from the part's attributes in the schematic (a resistor's rating, a capacitor's kind and value, a transistor's package, a trimmer's style). A trimmer is the triangle kind (Bourns 3362P: legs 1 and 3 two holes apart, the wiper a hole back between them) unless set in line (Bourns 3296W), D-393. A surface-mount transistor goes on the board only on a TO-92 adapter (its *Mounting*; a JFET's legs D-S-G), D-392.
- **The check** (`check.py`, D-367): the board read back into nets and compared with `connect(circuit)`, every fault a sentence; placement faults (two things in a hole, a body over a leg, a leg the footprint doesn't allow, a link under a standing body). The **progress check** (D-368) is the same reading for a board in the making: unplaced parts are *to place*, not faults.
- **Placement limits** (`limits.py`): a chip's decoupling cap, a charge pump's caps, an op-amp's feedback parts by their pin; warnings, not faults.

## The circuit is the only source of parts (the user, 2026-11-20)
- The editor shows **only the circuit's parts**: the on-board ones `export.built_where` names (the parts list's split, D-203) go on the board; the off-board ones (pots, switches but DIP, jacks, the DC jack, the battery, the status LED) sit **whole, beside the board**, joined to it by **wires**. **The bypass comes only from the schematic** (D-385): the builder adds the True bypass block in the schematic and wires it in; its footswitch, LED and resistor are circuit parts like any other. No stock footswitch or status LED is offered (it risks a second bypass). **On the board / Off the board, per part** (D-385): right-click a placed part, its tray row or an off-board part to move it to the other side of the board's edge (a part with no footprint greyed, with why), or back to the parts list's place; kept with the board, followed by the parts list.
- **No part is added, removed or changed in the editor**, nor its value. A part's size follows its schematic attributes.
- The edits are placement only: move, turn, flip, stand up or lay down a part; add or remove a cut or a link; place an off-board part; draw, move or delete a wire (D-374, D-375).
- When the schematic changes (D-376): a value only, the board still matches; a new part appears in the tray; a deleted one is said in Warnings ("R7 is no longer in the circuit", one click clears them all); a rewired one shows its legs on the wrong nets, with where they should go.

## The Board view
*Schematic* and *Board* are two views of the same circuit (D-369, D-370).
- **Optional, never in the way**: one fixed **Board** button in the header, just before the circuit's name, starts a board and switches to it: **quiet** when the circuit has no board ("Lay out a stripboard for this circuit"), **marked** once a board is started, **highlighted** in the Board view, where clicking it again goes back. Never greyed. *Tools → Stripboard layout* does the same.
- **Starting a board**: the Board view opens on an empty board, the tray full; nothing is saved until the first thing is placed.
- **Ready means placeable**: the view opens whatever the state, and names each part that can't be placed yet (a capacitor with no type, a model with no package, a surface-mount model off its adapter, a DIP switch); those stay in the tray.
- **Removing a board**: *Remove board* at the bottom of the board's Settings pane, one undo step.
- **The board canvas**, 2D, at real proportions, parts side by default.
- **The panes** (D-371): the result panes' column holds the board's own panes instead, through the same pane code under its own key: **Warnings**, **Schematic** (smaller, selection lit on both), **Nets** (each net *done*, *in pieces* or *shorted*; "18 of 24 nets done"), **Settings**; the **Tray** (the parts not yet placed, on-board and off-board; *Show placed (n)* lists those placed) takes the palette's place on the left. Back in the Schematic view the result panes return as they were.
- **Editor settings** (each remembered per viewer): *show values* (on), *what to place next* (on), *allow shorts while editing, shown red* (on; off refuses a move that makes a short), *auto-grow* (on), *see-through* (off), *mirror the copper side* (off, D-390), *ratsnest lines: all* (on), *highlight rails* (off).

### Board size (D-372, D-373)
- **The board is what's on it**: the box around every leg, body, link end and pad. Around it the canvas shows a **margin of free holes** (3 each side) to place into; placing in the margin grows the board, and taking things off shrinks it back (only by the edge lines that edit emptied). The header line gives size in holes and mm, cuts and links ("22 × 14 holes (56 × 36 mm), 18 cuts, 9 links").
- **Auto-grow** on by default; off, the board stays its size and a placement past the edge is refused with a sentence.
- **By hand**: on the rulers, add or insert a column or strip, or remove an empty one; a part straddling the line stretches or squeezes when its footprint allows, else the change is refused naming it. **Trim** takes off the empty edge lines.
- **An empty board** opens at a size worked out from the tray (about two and a half times the holes the parts take, wider than tall).
- **No fixed or stock size**; one board per circuit.

### Off-board parts and wires (D-375, D-379, D-380, D-384)
- **Off-board parts are dragged in whole**: a pot with its three lugs, a toggle, a jack (T, S; TRS: T, R, S), the DC jack, the battery clip, the status LED, the footswitch, each drawn by type (a stomp switch as its square of lugs, poles across the top; toggles and rotaries their own shape). The guitar's and amp's jacks the schematic doesn't draw have T and S lugs, and **Power** stands for the supplies no drawn battery or DC jack brings.
- **Wires** from a lug to a hole (its pad) or lug to lug; either end moved; a wire may be left loose (counted as still to do). Checked like the board: a wire on the wrong net is named at once.
- Wires bend round the board's edge in lanes and hop where they cross, never on top of each other nor right beside one another, never over another part's lug or along the rulers (D-389); a wire's middle runs can be moved by hand (kept), and *Route it for me* puts them back.
- **One click *Wire it for me***: every off-board part at its default spot (pots along the top in knob order, the input jack at the right, the output at the left, the footswitch below near the jacks), each lug wired to the free hole on its net's strip that a wire reaches most cheaply: round the board to the edge beside it, then in (D-389), so a wire crosses the board as little as it can.

### Drawing (D-378, D-390)
- Parts drawn as they look: resistor colour bands, an electrolytic's top with its − stripe, a diode's band, a TO-92's flat face, a chip's notch; each labelled by ref (and value while *show values* is on). Hovering a part names its legs.
- **Hide parts**: the copper side as seen from the parts side, not mirrored: strips, the holes used, cuts (the copper scraped away, D-395) and links. **Mirror** (beside See-through, off by default) turns it over as you hold the board to solder, with a short animation. Links are lavender on both sides.

### Guidance as you edit (D-377)
- **A part's needs, leg by leg**: each leg's net and the pins it must reach, joined or not.
- **Marked holes** where a picked-up part's legs would join their nets; **ratsnest lines** from each placed leg to the pins of its net it doesn't reach yet.
- **Suggested cuts and links**, faded, one click to accept; never added behind the builder's back. A join no single link can make is said in Warnings.
- **What to place next**: following the signal, preferring a part whose nets are already on the board.
- **Mistakes named as they're made**: a short, a part the wrong way round (each leg is a named pin), a broken placement limit. Values aren't checked: the parts list carries them.
- **Bodies by their real outlines** (D-394): two touching between holes, or one hanging more than half a hole past the board's edge, is a **warning** saying what to do (move one; standing one taller is possible, but the user would rather not). The board still passes. Letting the builder decide each one (taller, bent, accepted with a note) is a later feature.

### Automatic help
- **Layout…** (in the board's Settings pane, never the default; D-396) opens one dialog of choices, each with a line saying what it does, and every choice is confirmed after it, saying what will happen (Start a board over placed parts names what it replaces, by count); one undo step each, the Layout button saying what's being done and a bar moving while it works:
  - **Start a board** (D-387): a complete board that passes the check, the same every time, in well under a second. Parts left to right in signal order across the strips; a net carried along its strip; a part's two legs on one net joined by a short link beside it; every net left in pieces gets a full-width bus and each piece is linked to it, which is why it never fails. On a board with parts it's called **Start over**: it wipes the board and lays it out afresh. Then *Wire it for me*. **Make the board compact** (under it, remembered per viewer) runs Tidy up after, as the same undo step.
  - **Fill the rest** keeps what's placed and lays out the tray below it, never moving the builder's parts. Greyed with the reason when nothing is placed.
  - **Tidy up**, below. Greyed with the reason when nothing is placed.
  - The dialog opens on Start a board on an empty board; once parts are placed nothing is chosen, and Continue waits for the builder's choice. *Build a full layout* (the optimiser, P6h5) joins it, below a divider.
- **Tidy up** (D-388): small steps (slide a part, take out an empty line, shorten or drop a link or cut), each kept only if the board still passes the check and is no worse in size, cuts or links; the same board always tidies the same way; one undo step; "Couldn't make this board smaller" otherwise. Parts placed wrongly are named first and, on asking, laid out again. Small and middling boards shrink by a tenth to a fifth; the biggest little: they are a start.

### Undo, saving, staleness (D-370, D-376, D-386)
- **The board is saved in the circuit file** (`Circuit.stripboard`, schema v35; v36 off-board parts and wires, v37 wire runs, v38 On / Off the board; v39 a transistor's adapter and a trimmer's style).
- **The board has its own undo history**: board edits change only `circuit.stripboard`, schematic edits never touch it; Undo, Redo and History follow the view. The circuit is *Not saved* when either has changes; Save keeps both.
- **On every open and export the board is checked against the circuit as it now is.** A board that doesn't match is never packaged; the package index says why.

## In the build package (D-386)
The parts list's Hardware names the kept board: "Stripboard, 13 × 15 holes, cut to 33 × 38 mm, 0.1" pitch" (the board itself stays unsized, D-373; stock sheet sizes later, from makers' listings only).

`stripboard.pdf`: a line saying it's checked ("Every connection on this board matches the circuit (N nets)"); the cut list, the link list, the off-board wires numbered ("VR1 (Gain) lug 1 to F2"); the parts side with the off-board parts and wires, the copper side mirrored with its cuts and the copper side not mirrored, each labelled and filled onto its own sheet (D-390); then both sides of the board alone at real size on one A4 page, with a 25.4 mm line to check the print. Drawn by the browser's board canvas (D-205). No board kept: the package index's Ready to build notes "No stripboard layout kept"; a stale board is left out, the note saying what doesn't match. The generic wiring pages (D-209) stay.

## The starters (D-391)
**The starters ship without boards for now.** A builder lays one out with *Layout…* (Start a board, made compact on asking, and wired) or by hand. An offline CP-SAT search tried in P6g made the small and medium starters' boards smaller than the published ones but the big ones larger, and the user chose to ship without them and make a better layout its own feature (in the app, a separate tool or a pure-Python search, decided after a spike). The BD-2 (Aion)'s surface-mount JFETs go on TO-92 adapters, as Aion's kit builds them (D-392), so it can be laid out like the rest; the Bluesbreaker (Aion) can't (a DIP switch with no footprint) and *Start for me* says so.

**The benchmark** for that feature: published Tagboard Effects layouts, kept with their links in the acceptance files (`stripboard:`); the layouts are copyrighted drawings, so only the link and the counts are kept. Most drawings print their own size, cuts and links; the agent read and counted them, at the user's request (D-391; was a person, D-019).

| Starter | Published layout (Tagboard Effects) | Published: holes, cuts, links |
|---|---|---|
| TS808 | https://tagboardeffects.blogspot.com/2012/02/ibanez-ts808.html | 20 × 15, 17, 7 |
| ProCo Rat | https://tagboardeffects.blogspot.com/2012/01/proco-rat.html | 20 × 11, 15, 4 |
| Boss DS-1 | https://tagboardeffects.blogspot.com/2014/10/boss-ds-1-distortion.html | 22 × 17, 24, 10 |
| MXR Dyna Comp | https://tagboardeffects.blogspot.com/2012/07/mxr-dyna-comp.html | 18 × 15, 17, 8 |
| Marshall Bluesbreaker | https://tagboardeffects.blogspot.com/2012/02/marshall-bluesbreaker.html | 21 × 10, 19, 3 |
| Klon Centaur | https://tagboardeffects.blogspot.com/2012/02/klon-centaur.html ("Smaller") | 21 × 26, 32, 14 |
| Tone Bender MkII | https://tagboardeffects.blogspot.com/2012/02/sola-sound-tone-bender-professional.html ("smallest") | 15 × 9, 4, 1 |
| Dallas Rangemaster | https://tagboardeffects.blogspot.com/2014/02/dallas-rangemaster-pnp-negative-ground.html | 14 × 8, 9, 2 (with an ICL7660 ours doesn't need) |
| Big Muff Pi | https://tagboardeffects.blogspot.com/2012/06/ehx-73-rams-head-big-muff.html ('73 Ram's Head; ours the V3) | 19 × 17, 17, 5 |
| Fuzz Face | https://tagboardeffects.blogspot.com/2010/03/few-veros.html ("Fuzz Face PNP") | 20 × 9, 2, 1 |

## Out of scope
- A PCB, Gerbers, KiCad; perfboard and tagboard; drilling templates.
- Boards that hold the pots, or more than one board; a check against the enclosure's size.
- Changing a part's footprint per part beyond a trimmer's style and a transistor's adapter (sizes follow the schematic's attributes); DIP switches, tantalums and inductors on the board (no footprint yet).
- **Export to the dedicated tools** (VeroRoute, VeeCAD, DIY Layout Creator): ours is a simple editor, an add-on, not meant to beat them. Later list.
- **A 3D viewer** of the kept board: later, if 2D falls short in use.
- The circuit's own off-board wiring drawing in the package, replacing the generic pages (D-209): the numbered wire list and the parts-side drawing carry it for now (D-386).
