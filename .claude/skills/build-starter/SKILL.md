---
name: build-starter
description: Turn a published pedal schematic into a Solum Builder starter circuit with its acceptance file (drawing by script, models, expected values from the source, no Problems). Use when the user asks for a new starter or a pedal from the wish list.
---

# Build a starter from a schematic

`docs/maintain/add-a-starter.md` is the full list of what a starter needs (source, models,
drawing, notes, parts list, no Problems) and the wish list. Read it first. This skill is
how an agent does it, since an agent can't draw in the app.

## Rules

- Never fill a value from memory: every part value comes from the source's schematic or
  parts list, every expected figure from its text, table or graph, with the link, the
  Wayback snapshot and the date read.
- A non-commercial source (ElectroSmash, CC BY-NC) is cited and said in our own words
  (`says`), never quoted (D-292). Aion FX's notes are reworded and credited too (D-213).
- A figure the simulation misses gets `known_gap` with the reason worked by hand. Never a
  wider tolerance after the fact.
- A value read off a graph is `from: image` and waits for the user to confirm it.

## Steps

1. **Read the source.** The schematic, the parts list, every published voltage, gain and
   corner. Note each difference from the original pedal for `substitutions`.
2. **Check the models.** Every transistor, diode, op-amp and chip needs a card in
   `library/models/`. A missing one: the nearest that exists, said in `substitutions`, or
   the `fit-model` skill when the user wants the real part.
3. **Write the netlist you intend:** a list of sets of pins (`"R1.1"`, `"Q1.B"`) per net.
   This is what the drawing is checked against.
4. **Draw by script,** with `Drawing` (`solum/circuit/draw.py`; the `draw-circuit` skill
   has its calls, the sheet's rules and how to lay a drawing out). `make_klon.py` here is
   the worked example: `part()` places a part, wires run pin to pin, and
   `check_and_write()` compares the drawn connectivity with the intended netlist
   (`net_differences`) before writing the file, saying every net that is missing or extra. Lay it out as the
   source draws it: signal left to right, supply at the top, ground at the bottom, refs as
   the source numbers them. Write to `library/starters/<id>.json` with `"starter": true`.
   Run it with `make run CMD="python <script>"`.
5. **Look at it.** A drawing that passes the net check can still be unreadable.
   `make run CMD="python .claude/skills/draw-circuit/look.py <file>"` saves a picture of it
   as the app draws it (and prints its Problems and DC voltages): fix overlaps, crossed
   labels and wires through parts.
6. **Notes, description, parts list:** as the how-to's points 4 and 5.
7. **The acceptance file,** `tests/fixtures/acceptance/<id>.expected.yaml`: copy one that
   is close; the how-to's step 3 lists its fields.
8. **Run `make check`, then `make accept`.** Problems must be empty for the starter (a true
   warning goes in `tests/rules/corpus_warnings.yaml` with its reason); the mutation test's
   unseen breakages go in `tests/rules/mutation_gaps.yaml` with theirs. Netlist snapshots
   are new files to review.
9. **Record it:** a decision in `docs/DECISIONS.md` (source, substitutions, anything
   judged), the wish list's row, `THIRD-PARTY-NOTICES.md` if the source is new.
10. **Tell the user** what to look at in the app: the drawing, the knobs' names, and any
    `from: image` value waiting for them.
