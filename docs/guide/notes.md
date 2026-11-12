# Notes

The Notes pane holds what you want to remember about a circuit: why a part has its value, what to try next, how you set the bias on the bench. Notes are saved with the circuit and go into the exported build notes.

## General notes and part notes

The pane has two tabs:

- **General**: titled notes about the whole circuit. **+ Note** adds one. Click a note's title to open it; one is open at a time.
- **Parts & nets**: a note on a part (*R6*) or on a named net (*VREF*), listed under its ref or name. Click one to select it on the drawing.

The pane's title counts all of them. Starters come with notes on their parts and suggestions to try (*Try: germanium for D1, D2*).

Edit a note in place: the change is kept when you click away, as one step to undo. **Delete**, beside an open note, removes it (Undo brings it back).

## Adding a note to a part or a net

Right-click a part or a wire and choose **Add note…** (or **Edit note…** if it has one). A note goes on a named net, so it keeps its place as the drawing changes: a net with no name asks for one in the same form, and a label with that name goes where you clicked.

A part's or net's note also shows in the Probe pane when you probe it.

## Notes from blocks

Dropping a block adds its description as a general note (*From block: Gain stage · JFET (Fetzer Valve)*), and its notes on its parts come with it, under the parts' new refs.

## When a ref changes

Renaming a part (R7 to R9), or a paste that renumbers parts, can leave notes naming the old ref. The app then shows a notice on the drawing: *R7 is mentioned in 2 notes (it’s R9 now).* **Show** lists each mention, to tick which to change; **Replace** changes them (Undo takes it back). The mention's name opens that note to edit it by hand.
