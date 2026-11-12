# Adding a model

There are two different jobs.

## A model of your own, in your data folder

Tools → Add a model, in the app. Paste or choose a `.lib`/`.mod` file; the app finds the
cards in it, checks each one simulates, and saves the ones you tick to your data folder.
They show under Yours in every model list and are never part of the repo. [the guide's Models page](../guide/models.md#adding-a-model)
covers it; nothing here applies.

## A model that ships in the library

A model is two files in `library/models/<type>/`: `<ID>.lib` (the card) and `<ID>.json`
(the record: where it came from, its licence, ratings, package, and `validation`, the
datasheet figures it is checked against with what the simulation gives).

1. **Whose card?** A maker's own published card if its terms let us ship it; else our own,
   built from the maker's datasheet (D-156, D-159). Never a card of unknown origin.
   - Our own fit: the `fit-model` skill (`.claude/skills/fit-model/SKILL.md`) is the whole
     procedure, with the tools.
   - A maker's card: `.claude/skills/fit-model/tools/add_model.py` writes the record from
     a spec (its docstring lists the fields) and measures every check.
2. **The datasheet** goes in `data/spec-sheets/` (PDFs stay out of the repo) and its link
   in the record.
3. **Checks.** Every limit of the sheet that `solum/model_checks.py` can measure is a
   `validation` row. A row the model misses is not deleted or loosened: fix the model or
   say why in the record.
4. **The index.** `python3 scripts/models_index.py` rewrites the Shipped table in
   `data/spec-sheets/README.md`, with each model's licence review. A unit test fails when
   it is stale. A model flagged *Decide* does not ship: it is listed in
   `library/models/not-included.json` with where to get it.
5. **`make check`.** The model tests run every record's checks through ngspice.
6. **Notices.** A new maker gets a line in `THIRD-PARTY-NOTICES.md`.
