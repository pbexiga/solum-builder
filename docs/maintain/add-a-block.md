# Adding a core block

A block is a small circuit with named ports that Blocks → Insert or manage blocks pastes into a sheet. Core
blocks are the files in `library/blocks/`; a user's own are in their data folder (My
blocks) and need none of this.

1. **Draw it in the app** on a new sheet. Label the nets that are its ports (`in`, `out`,
   the supply rails), then Blocks → Save sheet as block: name, description, tags, ports.
2. **Copy the file** from `DATA_DIR/blocks/` to `library/blocks/<id>-v1.json`. Set the id
   to match the file name and `"template": true`, as the others have. A changed block is a
   new version of the same file, not a second block.
3. **Say where the values come from** in the description when they are a known circuit's
   (the pedal, the source), in our own words.
4. **`make check`.** Every core block must:
   - have no Problems on its own (`tests/rules/`; a warning that is true of the block goes
     in `tests/rules/corpus_warnings.yaml` with its reason);
   - survive the mutation test: each scripted breakage is noticed by a rule, or listed in
     `tests/rules/mutation_gaps.yaml` with the reason;
   - match ngspice in the live solver if it has signal ports (`tests/parity/`).
5. **Try it:** insert it into a sheet next to parts with the same refs (they renumber),
   wire it, run.
