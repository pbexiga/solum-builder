# AGENTS.md — working agreement for Solum Builder

At the start of every session read this file, `docs/maintain/working-docs.md` (how the plan, the decisions log and the module map work) and `notes/PHASES.md` (the maintainer's plan: local and git-ignored; on a fresh clone there is none, see "Starting on a fresh clone" below).
Don't read `docs/DECISIONS.md` whole (it's long): search it by the tags of the areas you're changing (each heading ends with tags such as `` `panes` ``; the list is at its top), and read every D-number cited in the code you touch.
`docs/SPEC.md` is the product spec: the original spec the app was built from, kept current, so it says what the app does today. When they disagree, DECISIONS.md wins (it is newer), and you fix SPEC.md in the same change.
New work is never planned in `docs/`: its spec (`notes/<NAME>-SPEC.md`) and its phases (`notes/PHASES.md`) live in `notes/`, local to each maintainer and git-ignored. If `notes/` has a spec for the current phase's work, read it too.

## What this is
A local, self-hosted circuit simulator for guitar-pedal builders. You draw a circuit, probe any node (waveform, harmonics, DC), see frequency curves update as you turn knobs, check the circuit against plain-English rules, and render audio through it into a NAM amp model.
Single user, runs in one Docker container (or from source). No accounts, no cloud.

## Look and feel
Follow `docs/DESIGN.md`. Brand assets are in `web/assets/brand/`; never redraw the logo. Colours come only from the tokens in `web/theme.css`.

## Agent skills
Two long jobs have skills in `.claude/skills/`: `fit-model` (our own SPICE model from a maker's datasheet) and `build-starter` (a published schematic as a starter with its acceptance file). Use the skill when a request fits. They're in Claude Code's format; another agent reads the skill's `SKILL.md` and follows it. The other jobs are how-tos in `docs/maintain/`.

## Stack (see DECISIONS.md for why)
- Backend: Python 3.12, FastAPI, numpy/scipy. Simulator: ngspice as a shared library (`libngspice`) via ctypes (no WASM fallback, D-087).
- Frontend: plain JavaScript ES modules served by FastAPI. **No bundler, no npm, no framework.** Charts: uPlot (vendored). Schematic canvas: SVG.
- Storage: JSON files are the source of truth. SQLite (stdlib `sqlite3`) is a rebuildable index and cache only.
- Packaging: one Docker image, `docker compose up`.

## Coding standards

### Reuse before you write (most important rule)
1. **Before writing any function, search for one that already does it.** Grep the codebase by intent, not just name (e.g. units parsing: grep `parse_value`, `si`, `"4k7"`, `1e3`). Check `docs/ARCHITECTURE.md`'s module map.
2. If something close exists, **extend or generalise it** (add a parameter, split out the shared part). Do not write a parallel version.
3. If you find two functions doing the same job, merge them in the same change and update the callers.
4. Every new public function or module gets a one-line entry in the module map in `docs/ARCHITECTURE.md`. That map is how the next session finds it.
5. One owner per concept. These must each exist in exactly one place:
   - SI value parsing and formatting (`4k7`, `22n`, `1M`, `100p`) and E-series snapping
   - Circuit JSON load / validate / save / migrate
   - Netlist generation from a circuit
   - Running ngspice (behind the `SimEngine` interface) and parsing its results
   - Pot model (rotation + taper → two resistances)
   - Content hashing for the cache
   - Frequency-response measures (corner, notch, band edges)
   The frontend may not re-implement backend logic, with one deliberate exception: the in-browser linear solver for live curves (D-012). It is tested against ngspice AC results (see Testing).

Never use sudo or install anything system-wide (no dnf, no pip outside a venv). Containers and a gitignored scratch/ venv only. When you've installed anything, say how much disk it used and the command that removes it.

### Simplicity
- Simplest thing that meets the phase's acceptance criteria. No speculative abstractions, plugin systems or config options nobody asked for.
- No new dependency without a DECISIONS.md entry saying why the standard library or an existing dependency can't do it.
- Delete dead code; don't comment it out.

### Code style
- Python: type hints everywhere. `ruff` (lint + format) must pass on `solum/`, `tests/`, `scripts/` and `.claude/skills/` (the fit skill's `worked/` excepted, D-307), and `mypy --strict` on `solum/`. Small functions; pure functions where possible; I/O at the edges.
- JS: ES modules, JSDoc types on exported functions, no globals except the app root. Keep DOM code apart from logic so logic is testable.
- `web/app.js` is the root only (state, open/show, edit/undo, select, run/render). New dialogs, menu items, tiles, panes and form behaviour go in their own modules, each given a small set of callbacks by the root: see "Where browser code goes" in `docs/ARCHITECTURE.md` before adding browser code (D-284).
- Names follow the domain: `net`, `node`, `part`, `ref` (designator), `port`, `block`, `rail`. Don't invent synonyms.
- Units: internal values are SI floats (ohms, farads, volts, hertz, seconds). Strings like `4k7` exist only at the edges (files, UI).
- Errors shown to the user are plain English and say what to do. Never surface a raw traceback or ngspice message in the UI.

### Testing
Tests are written **with** the code, not after. A function isn't done until its unit tests exist and pass.

**Layers** (folders under `tests/`, mirroring the package layout):
| Layer | Folder / marker | What | Speed |
|---|---|---|---|
| Unit | `tests/unit/` | Pure functions: units parsing, E-series, pot taper, connectivity, netlist generation, hashing, measures, harmonics, each rule's check, migrations | Whole suite < 10 s, no ngspice |
| Simulation | `tests/sim/`, `@pytest.mark.sim` | Small fixture circuits through real ngspice: RC corner, divider DC, op-amp gain, diode clip level | < 1 min |
| Acceptance | `tests/acceptance/`, `@pytest.mark.acceptance` | Classic circuits vs their `.expected.yaml` (D-019) | minutes, run before finishing a session |
| Parity | `tests/parity/` | JS linear solver vs ngspice `.ac` within 0.1 dB | with sim tests |
| Rules | `tests/rules/` | Per-rule bad/good fixtures, known-good corpus, mutation tests | with sim tests |
| UI | `tests/ui/`, `@pytest.mark.ui` | Playwright tests: page loads, place a part, run, panel shows a curve | minutes |

**Practices**
- Test first for bug fixes: write the failing test that reproduces the bug, then fix it.
- Unit tests check behaviour with concrete numbers you can verify by hand (an RC corner of 1/(2πRC), `"4k7"` → 4700.0), and edge cases (empty circuit, floating pin, zero-value part, unicode `µ`).
- Property-based tests (`hypothesis`) for round-trips and invariants: `format(parse(x)) == x`, netlist generation is deterministic, renumbering a pasted block never collides with existing refs.
- Netlist generation gets snapshot tests: the generated netlist for each fixture circuit is stored and diffed. A changed snapshot must be reviewed, not blindly updated.
- Simulation and acceptance tests load circuits from `library/` and `tests/fixtures/`, so they exercise the real pipeline. Unit tests may build small circuits in code with the fixture builder in `tests/conftest.py` (one builder, reused everywhere).
- Floats are compared with stated tolerances (`pytest.approx`), never `==`.
- Core packages (`solum/` minus `api/`) keep ≥ 85 % line coverage; the report runs with the suite. Coverage is a floor, not a goal: no tests written just to touch lines.
- JS logic lives in modules with no DOM access so it can be tested; the in-browser solver is tested by the parity suite (run through Playwright's browser).

**Commands** (in `Makefile`, the single entry point):
- `make test`: unit tests only (run constantly while coding)
- `make check`: ruff, the browser code's check (`make jslint`: undefined names, unused and wrong imports, D-286), mypy, unit + sim + rules + parity, coverage report (run before every commit)
- `make accept`: acceptance and UI tests (run before ending a session)
A pre-commit hook runs ruff, `make jslint` and `make test`, except on commits that only change Markdown notes in `docs/` or the top folder (D-194).

### Data and files
- Circuit/block files carry `"schema": N`. Any format change bumps N and adds a migration in the one migrations module, with a test that loads an old-version fixture.
- Never write inside the repo at runtime. User data goes to `DATA_DIR`, cache/index to `CACHE_DIR`.
- The SQLite index and cache must be safe to delete at any time.

### Starting on a fresh clone
When there is no `notes/PHASES.md`:
1. Get the machine ready yourself: `make dev-image`, `make hooks`, then `make check`. They need Podman (or Docker) and `make`; if either is missing, tell the person what to install, never install it yourself. If `make check` isn't green, say so before changing anything.
2. Ask what the person wants to work on. For anything larger than a small change, first write its spec in `notes/<NAME>-SPEC.md` (goal, what the person gets, how it works, out of scope, open questions) and have the person answer its questions. Then turn it into phases: related work grouped together, each phase small enough to check and accept in one sitting. Write them in `notes/PHASES.md` in the layout `docs/maintain/working-docs.md` gives (goal, checklist, *Accept when*), and have the person agree the plan before building.

### Working in sessions
- Work only on the current phase in `notes/PHASES.md` (local, git-ignored). If you discover something needed from a later phase, note it there; don't build it.
- When the person asks for something new that isn't in the plan, it gets its own spec and phases in `notes/` before it's built ("Starting something new" in `docs/maintain/working-docs.md`); a small change goes straight into the plan.
- When a body of work is finished and accepted, move its phases and notes out of `notes/PHASES.md` to `notes/PHASES-<name>.md`: the plan holds only the work in hand.
- When you make a choice that a future session would otherwise re-debate (library, format, algorithm, trade-off), add it to `docs/DECISIONS.md` in the same commit.
- End every session by: running the full test suite, updating the phase checklist in `notes/PHASES.md`, adding decisions, updating ARCHITECTURE.md's module map, and writing a 3–5 line "Next session" note at the bottom of PHASES.md.
- Small, focused commits with clear messages.
- When reviewing a change (yours or someone else's), check that every choice a later session would re-debate has a DECISIONS.md entry, and add any that are missing.
- After a major UI change (a menu, pane, dialog or workflow added, renamed or reworked), ask the user whether to update the guide (`docs/guide/`) now or leave it for a full docs pass. If it's left, note in PHASES.md which pages and screenshots it affects, so the pass finds them (D-298). How: `docs/maintain/updating-the-guide.md`.
- If an instruction here conflicts with what the user asks in the session, follow the user and record the change in DECISIONS.md.

## Domain notes worth knowing
- Users design real pedals. Acceptance tests are classic, measured circuits (TS808, Big Muff, Fuzz Face, Rat, BD-2 and the other starters): expected values come from published analyses and are stored with their source link (D-019). Never fill expected values from memory.
- JFETs vary unit to unit (J201 Idss ~0.2–1 mA, Vp ~−0.3 to −1.5 V). Bias is set with a trimmer to a drain-voltage target; the sim must support "set drain to X V" by solving the trimmer, and per-part measured Idss/Vp.
- A passive tone stack loses 15–20 dB and needs a ~1 MΩ load; source impedance changes its curve. Always let source and load impedance be set.
- An AC (small-signal) result is meaningless if the DC operating point is saturated. Flag it instead of plotting it confidently.
