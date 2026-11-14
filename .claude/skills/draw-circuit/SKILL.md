---
name: draw-circuit
description: Draw a circuit as a Solum Builder file the user can open in the app (parts placed, real wires, checked against the intended netlist, no Problems), and put it in their circuits folder. Use when the user wants a circuit you've worked out together drawn, a schematic turned into a file to open, or asks how to get a circuit into the app without drawing it by hand.
---

# Draw a circuit for the app

An agent can't draw in the editor, so it writes the circuit file. A circuit is one JSON
file; the app lists every file in its circuits folder, so "importing" is copying the file
there. This skill is how to make a file that opens as a readable drawing and simulates.

A published pedal meant to ship as a starter is the `build-starter` skill's job (it adds
the source's figures and an acceptance file). This one is for the user's own circuits.

## Where the truth is

The code wins over this page. Read the part you need:

- `solum/circuit/schema.py`: every part type and its fields, and the file's own fields
  (`Circuit`). `docs/circuit.schema.json` is the same as JSON Schema, generated.
- `solum/circuit/parts.py`: each part's pins and where they are (`PIN_OFFSETS`).
- `solum/circuit/refs.py`: the ref each part type takes (R1, VR1, IC1A, IN, OUT).
- `solum/circuit/switches.py`: the switch types (`KINDS`) and their lugs.
- `library/models/<type>/`: the models that exist, one `.json` each (the user's own are in
  their data folder's `models/`).
- `solum/circuit/draw.py`: `Drawing`, the helper the script uses.

## Steps

1. **Agree the circuit** with the user: what it does, each stage, the knobs and their
   names, the supply. Say where every value comes from: the user, a source you can both
   read, or arithmetic you show (a corner is 1/(2πRC), a gain 1 + Rf/Rg). Never pass off
   a remembered value of a published pedal as its real one: fetch the schematic or say it
   is from memory and unchecked.
2. **Check the models.** Every transistor, diode, LED, op-amp and chip needs a model that
   exists (`ls library/models/opamp/`). A missing one: offer the nearest and say so, or
   the `fit-model` skill when the user wants the real part.
3. **Write the netlist meant**: a set of pins per net (`{"C1.2", "R2.2", "IC1.+"}`). This
   is what the drawing is checked against, so write it from the design before drawing and
   never change it to make a drawing pass.
4. **Draw by script**, in `scratch/drawn/<id>.py` (git ignores `scratch/`). Copy
   `example_boost.py` here: it shows every step. Lay it out as schematics are read: signal
   left to right, supply at the top, ground at the bottom.
5. **Run it and look**:
   ```
   make run CMD="python scratch/drawn/<id>.py"
   make run CMD="python .claude/skills/draw-circuit/look.py scratch/drawn/<id>.json"
   ```
   The script stops with each difference from the netlist meant. `look.py` opens the file
   in the real app (temporary folders, nobody's circuits touched), prints its Problems and
   DC voltages, and saves `scratch/drawn/<id>.png`. Read the picture: fix text over
   text, wires through parts and labels on top of each other, then look again. Problems
   should be none; one that is true of the design is told to the user, not hidden.
6. **Measure what was designed**: `make run CMD="solum run scratch/drawn/<id>.json --ac
   out"` gives the gain and corners at a net (`--op` the DC voltages, `--tran out` the
   waveform's figures). Compare them with step 1's arithmetic and tell the user both.
7. **Hand it over** (next section), and say what to look at in the app.

## Getting the file into the app

The circuits folder is `circuits/` inside the app's data folder: `data/` beside
`compose.yaml` unless `DATA_DIR` says otherwise (`.env`, or the environment); File →
Settings… in the app shows it (with Docker, the host path is the one to use).

- **By the user, anywhere:** File → Import… in the app takes the file (it asks for a name
  when the file's is taken). Give them the file's full path.
- **Same machine:** copy the file into that folder under any name ending `.json`. The app
  reads the folder each time File → Open… is shown, with no restart, and renames the file
  its own way (`<id>-v1.json`).
- **Another machine** (a NAS): give the user the file to copy there, or, when they ask you
  to, send it to the running app, which saves it as a new circuit and refuses a name
  already taken:
  ```
  curl -sS -X POST http://<host>:8000/api/circuits -H 'Content-Type: application/json' \
    -d "{\"circuit\": $(cat scratch/drawn/<id>.json)}"
  ```

A copied or posted file is opened from File → Open….

**Never write over a circuit the user may have changed.** Before copying, list the folder.
A file with that id already there: if it is the same as the one you last put there (keep
that copy in `scratch/drawn/`), replace it; if it differs, the user has edited it in the
app, so ask whether to replace it or use a new name. Once the user edits in the app, their
file is the circuit: read it back (`solum.circuit.io.load_circuit`) before changing
anything, and don't redraw from the old script.

## The file

The least a file needs:

```json
{"schema": 30, "id": "my-boost", "name": "My boost", "parts": []}
```

`schema` is the version (`SCHEMA_VERSION` in `schema.py`; `Drawing.circuit()` writes the
current one, and an older file is brought up to date when opened). The rest:

- `parts`: each has `ref`, `type`, `pos` `[x, y]`, `rot` (0, 90, 180, 270) and its type's
  own fields. Values are written as on a schematic: `"4k7"`, `"22n"`, `"1M"`, `"100µ"`.
- `wires`: `{"from": [x, y], "to": [x, y]}`, each one level or upright.
- `labels`: `{"net": "VREF", "pos": [x, y]}` names the net at that point; the same name
  anywhere is the same net. `GND` is ground.
- `power`: `{"rails": {"V+": 9.0}}`. The only rails are `V+` and `V-`; any other supply
  (VREF, a filtered rail) is a net the circuit makes, with a label.
- `probes`: `{"in": "in", "out": "out"}`, the nets the app measures between (else the
  guitar's and the amp's).
- Optional: `description`, `tags`, `texts` (free text on the sheet), `notes` (general),
  `net_notes` (by net name), a part's own `note`, `enclosure` (`{"size": "125B"}`).

To simulate, a circuit needs the guitar (`IN`), the amp (`OUT`), a rail and a ground.

A file with no wires at all is valid: give every pin a label and same-named pins join.
That simulates, but nobody can read it. Draw wires; keep labels for ground, the supplies
and the few nets that would otherwise cross the whole sheet.

## Drawing

`Drawing` (`solum/circuit/draw.py`):

| Call | Does |
|---|---|
| `part("R1", "resistor", (100, 0), rot, value="10k")` | places a part; refuses a wrong ref or field in plain English |
| `wire("R1.2", (140, 0), "C1.1")` | a wire through pins and points, one straight piece between each two |
| `label("GND", "R2.2", "C1.2", rot=0)` | names the net at each place |
| `stub("VR2.1", "GND", dx=40)` | a short wire from a pin ending in a label |
| `text((0, 200), title="…", text="…")` | free text on the sheet |
| `pins("Q1")`, `pin("Q1", "B")` | where a placed part's pins are |
| `circuit("Name", power=…, …)` | the validated circuit; `save_circuit(circuit, path)` writes it |
| `net_differences(circuit, INTENDED)` | each difference from the netlist meant, in words |

How the sheet joins things (D-036):

- Positions are in sheet units; the grid is 10. Put parts on multiples of 20 so pins meet.
- y grows downwards; `rot` turns clockwise. A two-pin part is 40 long: pins at ±20.
  Turned 90, pin 1 is on top; 270, at the bottom.
- **Any point on a wire joins it.** A wire that runs through another part's pin, or ends on
  another wire, is connected there. Wires that only cross are not. So route round pins,
  and never along another wire. The net check finds every slip.
- Two different labels on one net is an error.

Parts (the common ones; `schema.py` has them all, `pins()` lists a placed part's):

| Type | Ref | Pins at rot 0 | Fields |
|---|---|---|---|
| `guitar` | `IN` | `out` right | `volume="250k"` (its volume pot), `source`, `pickup` |
| `amp` | `OUT` | `in` left | `value="1M"` |
| `resistor` | R1 | `1` left, `2` right | `value` |
| `capacitor` | C1 | `1` left (the + of a polarised one), `2` right | `value`, `kind` (film, ceramic, c0g, electrolytic, tantalum), `rating_v` |
| `pot`, `trimmer` | VR1, TR1 | `1` left (counter-clockwise end), `2` wiper on top, `3` right | `value`, `taper` (A log, B linear, C reverse log, W the S-shaped one; `pot.py`), `rotation` 0 to 1, `label` (the knob's name) |
| `diode`, `led` | D1, LED1 | `A` left, `K` right | `model` |
| `bjt`, `jfet`, `mosfet` | Q1 | `B` or `G` left; `C` or `D` top right; `E` or `S` bottom right | `model` (PNP or NPN is the model's) |
| `opamp` | IC1, or IC1A and IC1B | `-` top left, `+` bottom left, `out` right; a single's `V+` top, `V-` bottom | `model`, `half` (a, b) on a dual |
| `powerunit` | IC1C | `V+` top, `V-` bottom | `model`: a dual's supply pins |
| `switch` | SW1, or SW1A… per pole | common left, throws right | `kind`, `pole`, `position`, `label`, `names` |
| `battery`, `dcjack`, `jack`, `vsource`, `inductor`, `regulator`, `chargepump`, `inverter`, `ota` | | see `parts.py` | see `schema.py` |

Rules a file must keep (the loader says which is broken):

- A dual op-amp is three parts: IC1A, IC1B and its power unit IC1C, all of one model, with
  V+ and V- wired or labelled on IC1C. A quad is IC1A to IC1D and IC1E. An unused half
  still has to be there: wire it as a buffer on VREF.
- A multi-pole switch is a part per pole (SW1A, SW1B, SW1C), all of one kind, position and
  label; a dual pot a part per gang (VR1A, VR1B).
- One `IN`, one `OUT`. A knob's name goes in `label`, never in the ref.

Laying it out so it reads:

- The signal along one line, left to right; each stage's feedback above it; parts to
  ground hanging below; the supply and VREF divider in their own group at the top.
- A part's ref and value are drawn beside it: leave 60 or more between neighbours in a
  row, 80 between upright parts side by side.
- Put `GND` and supply labels on the pin itself where the symbol has room (ground hangs
  down, a rail stands up; `rot=180` turns one over for a pin that faces the other way),
  else at the end of a `stub`.
- Pots as on the pedal: clockwise is more. Pin 3 is the clockwise end.
