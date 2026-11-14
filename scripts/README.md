# scripts

Maintainers' tools. None is needed to run the app. Run them from the repo's top folder;
those marked *dev image* need the app's Python packages and ngspice, so they run in the
dev container (`make dev-image` builds it):

    make run CMD="python scripts/prof.py ts808"

The model-fitting tools are with their skill, in `.claude/skills/fit-model/` (`tools/` the
working scripts, `worked/` the per-part work the model records cite); the worked example
of a starter drawn by script is in `.claude/skills/build-starter/`.

| Script | What it does | Runs in |
|---|---|---|
| `ngspice_build.sh` | Builds ngspice (the shared library and the program) from the pinned release tarball, the one recipe for the Docker image and the Mac app: `ngspice_build.sh PREFIX WORKDIR`. The Dockerfile and `mac_app.sh` run it; nobody else needs to. | image build, Mac |
| `mac_app.sh` | `make mac-app`: the Mac app from this checkout, its tools, tests, smoke test and `.dmg` ([Building the Mac app](../docs/maintain/mac-app.md), D-326). | Mac |
| `mac_sign.sh` | Signs the app inside out with the hardened runtime, signs the `.dmg`, notarises and staples; run by `mac_app.sh` only when `MAC_SIGN_IDENTITY` is set (D-330). | Mac |
| `mac_smoke.py` | The built app's smoke test, run by `mac_app.sh`. | Mac |
| `mac_icon.py` | The app's icon set from the brand's outlined favicon, run by `mac_app.sh`. | Mac |
| `pre-commit` | The git hook: ruff, the browser code's check and the unit tests before each commit. `make hooks` installs it (once per clone). | host |
| `jscheck.sh`, `jscheck.js` | The browser code's static check (`make jslint`): names never declared or imported, unused imports, imports that don't exist. | dev image |
| `models_index.py` | Rewrites the Shipped table of `data/spec-sheets/README.md` from the model records, with each model's licence review. A unit test fails when the table is out of date. | host (plain Python) |
| `fetch_spec_sheets.py` | Downloads every datasheet listed in `data/spec-sheets/README.md` that isn't on disk (the PDFs aren't in the repo). | host (plain Python) |
| `fit_models.py` | The fitting sums for our own SPICE models (a diode's forward curve and the rest); imported by the fit scripts and tested in `tests/unit/`. | dev image |
| `outline_svg_text.py` | One-off: turns the logo's `<text>` wordmark into font outlines. Needs fonttools and uharfbuzz in a throwaway venv. | venv |
| `prof.py` | Times the heavy requests (run, stages, clipper, a knob turn) through the API for one or more starters, cold and warm cache; `--profile NAME` writes a cProfile of one. Its cache and data go under `scratch/perf/` (ignored by git). | dev image |
| `dupes.py` | Clean-up review helper: functions with the same name in several files, and runs of five or more identical lines, in `solum/` and `web/` (or the folders named). | host (plain Python) |
| `guide_shots.py` | The user guide's screenshots: drives the real app and writes `docs/guide/img/*.png`, one function per picture (`python scripts/guide_shots.py sweep` for one). Run it when the screens change and look at the pictures before committing them. | dev image |
