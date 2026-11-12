---
name: fit-model
description: Fit Solum Builder's own SPICE model to a maker's datasheet (BJT, diode, LED, JFET, op-amp) and add it to library/models with its record and measured checks. Use when a part has no model we may ship, or the user asks for a model built from a sheet.
---

# Fit a model from a datasheet

Our models are a maker's own published card where one exists and may be shipped, else our
own, built from the maker's datasheet (D-156, D-159). This skill is the second case. The
decisions that set the method: D-161 (JFETs, range middles), D-162 (op-amp macromodel),
D-163 (BJTs: Gummel-Poon from the typical curves), D-157/D-158/D-160 (LEDs and diodes),
D-180 (OTAs), and `docs/guide/germanium-study.md` (germanium).

Run everything from the repo's top folder. Anything that needs numpy or ngspice runs in the
dev image: `make run CMD="python <script> <args>"` (`make dev-image` builds it).

## Rules

- Every number comes from the datasheet and names where (figure, table row, page). Never
  from memory, never from another maker's card.
- Don't loosen a tolerance or drop a check to make it pass. If a sheet limit can't be met,
  stop and report it with the numbers.
- Say what you judged: which curve is the 25 °C one, a family curve scaled to a grade, a
  figure read by eye, anything left out.
- The fit sums live in `scripts/fit_models.py` (unit-tested in `tests/unit/`). If they need
  a change, make it there with a test, not in a spec file.
- No sudo, nothing installed system-wide. Datasheet PDFs go in `data/spec-sheets/` (not in
  the repo; `scripts/fetch_spec_sheets.py` fetches the listed ones).

## Steps

1. **Get the sheet and read it.** Text and tables: `pdftotext -layout -f P -l P sheet.pdf -`.
   Pages as pictures: `pdftocairo -png -r 110 -f P -l P sheet.pdf <scratchpad>/pg`, then
   look at the PNG. Settle which curve is which and the conditions of each figure.
2. **Digitise the curves.** `python3 tools/plots.py sheet.pdf PAGE` lists each plot (axes
   mapped from the tick labels) and its candidate curves; add `PLOT# CURVE#` to print one
   curve's points. Check the axis mapping against the picture. Thin to 10-20 points, keep
   the ends. A raster figure has no curves to read: read points off the picture and say so
   in the figure text, or leave the figure out and say why.
3. **Write the spec.** The data and its citations, as Python:
   - BJT: one file in `tools/specs/` defining `PARTS = {"ID": {...}}`. The format is
     `tools/bjt_record.py`'s docstring; `tools/fit_bjts.py` has two worked parts (2N3904, a
     whole single-part spec; 2N5088/2N5089, a family curve scaled per part).
   - Diode, LED, JFET, op-amp: an entry in `tools/fit_diodes.py`, `fit_leds.py`,
     `fit_jfets.py` or `fit_opamps.py`, shaped as its neighbours.
   - Checks: every min/max row of the sheet's table that `solum/model_checks.py` can
     measure, each citing its row.
4. **Fit.** `make run CMD="python .claude/skills/fit-model/tools/fit_bjts.py ID"` (or the
   type's fitter). It writes `library/models/<type>/ID.lib` and `.json` and prints the card
   and its worst errors. Aim for hFE within a few percent, voltages within a few mV.
   **A fitter rewrites the whole record.** For a model already in the library, read the
   `git diff` afterwards and put back fields added since (`datasheet`, the tester gain).
5. **Measure in ngspice.**
   `make run CMD="python .claude/skills/fit-model/tools/add_model.py .claude/skills/fit-model/tools/remeasure.py ID"`
   fills the record's `simulated` values; every line must end `OK`.
   `tools/try_model.py` tries a card without writing anything.
6. **Finish.** `python3 scripts/models_index.py` (the index's Shipped table),
   `make check` (the model tests run every record's checks; netlist snapshots that carry the
   card are reviewed, not blindly updated), a line in `THIRD-PARTY-NOTICES.md` if the maker
   is new, and the decision in `docs/DECISIONS.md` when a judgement was made.
7. **Report.** Per part: the card, the worst fitted errors, any check not met and why, the
   figures and pages used.

## What is here

- `tools/`: the working scripts. `plots.py` (+ `svgpaths.py`) reads curves from a PDF;
  `bjt_record.py`, `diode_record.py` build and write records; `fit_*.py` hold each type's
  parts; `opamp_pm_fit.py`, `opamp_tran.py`, `opamp_os.py` fit and check an op-amp's phase
  margin, step and overshoot; `add_model.py` writes or re-measures a record;
  `remeasure.py` is its spec list for models already in the library.
- `worked/`: the scripts and notes behind models that needed more than the general tools,
  kept because the model records cite them: germanium transistors (`germanium/NOTES.md` is
  the method), OTAs (`ota/NOTES.md`), MOSFETs, the CD4049UB, and several BJTs and JFETs
  read by pixel. They are records of how each card was made, with the data they read; they
  were written in a working folder, so expect to adjust a path before one runs again.
  Start from the nearest one when a new part is of the same kind.
