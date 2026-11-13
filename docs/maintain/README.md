# Maintaining Solum Builder

For people working on the code. Installing and using the app are in the [top README](../../README.md); the users' guide is in [`docs/guide/`](../guide/README.md).

## Setting up

Everything runs in a dev container (Python 3.12, ngspice, the test tools and a browser for the UI tests), so nothing is installed on your machine. You need Podman or Docker and `make`.

    make dev-image   # once, and again after pyproject.toml or the Dockerfile changes
    make hooks       # once per clone: the pre-commit hook
    make test        # the unit tests: a quick check that it all works

The Makefile finds Podman or Docker by itself (`make CONTAINER=docker …` to choose) and mounts the repo into the container, so the tests run on your working copy.

Keep throwaway work (exploration scripts, dumps, screenshots) in `scratch/`, which git ignores. Never install anything system-wide for the project: a container, or a virtual environment under `scratch/`.

## The make commands

`make help` lists them. `make` is the single entry point for building, testing and checking.

| Command | What it does | When |
|---|---|---|
| `make dev-image` | Builds the dev image `solum-builder:dev`. | First, and after changing dependencies. |
| `make image` | Builds the runtime image `solum-builder:latest`, the one `docker compose` runs. | Before `make bench` or a release. |
| `make test` | Unit tests: pure functions, no ngspice, all cores. Under 20 s. | Constantly while coding. |
| `make ruff` | Ruff's lint and format check on `solum/`, `tests/`, `scripts/` and `.claude/skills/` (not the fits' `worked/` scripts, D-307). | Part of `lint`. |
| `make jslint` | The browser code's static check: names never declared or imported, unused imports, imports that don't exist. | Part of `lint`. |
| `make lint` | `ruff`, `jslint` and `mypy --strict`. | Part of `check`. |
| `make check` | `lint`, then the unit, simulation, rules and parity tests with a coverage report (85 % floor on the core). A few minutes. | Before every commit. |
| `make accept` | The acceptance tests (each starter against its published figures) and the browser tests (Playwright), then the timing tests on their own. | Before ending a session or merging. |
| `make bench` | `solum bench` in the runtime image: times a bench circuit through the simulator and prints a JSON report. See [Benchmarks and profiling](#benchmarks-and-profiling). | After performance work, or on a new machine. |
| `make image-tar` | Builds the runtime image and saves it as `dist/solum-builder-image.tar.gz`, for a machine that won't build it. | Deploying to the NAS. |
| `make schema` | Regenerates `docs/circuit.schema.json` from the circuit models. A test fails when it's stale. | After changing the circuit format. |
| `make hooks` | Installs the pre-commit hook: ruff, `jslint` and the unit tests before each commit (skipped for commits that only change Markdown notes). | Once per clone. |
| `make run CMD="…"` | Any command in the dev image, from the repo's top folder. | Scripts, one-off checks. |

Settings you can pass to any of them:

- `LOCAL=1` runs the command directly on your machine instead of in the container (you provide Python, ngspice and the tools).
- `JOBS=0 ACCEPT_JOBS=0` runs the tests one at a time instead of on every core (`JOBS=auto`, `ACCEPT_JOBS=4` by default): slower, easier to read when a test fails.
- `BENCH_CACHE=/path` puts `make bench`'s cache somewhere other than `./cache`.

## The `solum` command

The app's own command line, available in both images:

- `solum serve` runs the web app (what the runtime image does).
- `solum run <circuit.json>` simulates a circuit file and prints its results: DC voltages by default; `--ac NET` the frequency response at a net, `--tran NET` waveform figures at a net, with `--level soft|med|hard` for the input; `--json` for machine-readable output. For example:

      make run CMD="solum run library/starters/ts808.json --ac out"

- `solum bench` times the simulator; see below.

## Benchmarks and profiling

- **`make bench`** (`solum bench` in the runtime image, so `make image` first) times the Big Muff bench circuit (`library/bench/big-muff.cir`): DC, AC, a short transient and a 5 s audio render, then the cache, a TS808 knob turn and a Find parts search. It prints a JSON report, with the machine's CPU, memory and ngspice version, so a run on another machine (the NAS) can be pasted back and compared. The cache timings need the disk the app's cache lives on (a RAM disk hides the real cost, D-126), hence `BENCH_CACHE`. `solum bench --help` lists its options: how many repeats of each (`--runs`, `--audio-runs`, `--knob-runs`; 0 skips the knob turn).
- **`scripts/prof.py`** times the heavy requests (run, stages, clipper, a knob turn) through the API for one or more starters, with a cold and a warm cache: `make run CMD="python scripts/prof.py ts808"`. `--profile NAME` writes a cProfile of one request. Its data and cache go under `scratch/perf/`.

## Other scripts

[`scripts/README.md`](../../scripts/README.md) lists them all and where each runs. The ones you're likeliest to need:

| Script | What it does |
|---|---|
| `scripts/guide_shots.py` | Makes the users' guide's screenshots by driving the real app: `make run CMD="python scripts/guide_shots.py [names]"`. |
| `scripts/models_index.py` | Rewrites the shipped-models table in `data/spec-sheets/README.md` from the model records (plain Python, on your machine). |
| `scripts/fetch_spec_sheets.py` | Downloads the datasheets listed there that aren't on disk (they aren't in the repo). |
| `scripts/dupes.py` | For a clean-up review: functions with the same name in several files, and runs of identical lines. |

## Tests

Tests live in `tests/`, by layer:

| Folder | What | Run by |
|---|---|---|
| `tests/unit/` | Pure functions: units, netlists, measures, rules' checks, migrations. No ngspice. | `make test` |
| `tests/sim/` | Small circuits through real ngspice. | `make check` |
| `tests/rules/` | Each rule's bad and good fixtures, every shipped circuit kept clean, and the mutation tests (break a circuit, expect a rule to notice). | `make check` |
| `tests/parity/` | The browser's live solver against ngspice, within 0.1 dB. | `make check` |
| `tests/acceptance/` | Each starter against the figures its source publishes (`tests/fixtures/acceptance/*.expected.yaml`, with the source's link). | `make accept` |
| `tests/ui/` | The app in a real browser: place parts, run, probe, render audio. | `make accept` |

Bug fixes start with a failing test. `AGENTS.md`'s *Testing* section has the full practice.

## The project's documents

The project is built in sessions, mostly by an AI agent, with a person deciding what gets built. These files carry what one session knows to the next. **[The working documents](working-docs.md)** explains each one, how they're kept, and why they must stay up to date.

| File | What it is |
|---|---|
| [`AGENTS.md`](../../AGENTS.md) | The working agreement for agents and people: stack, coding standards, testing, how a session starts and ends. |
| `notes/PHASES.md` | The plan for the work in hand, phase by phase, and the note for the next session. Kept by each maintainer, git-ignored, not in the repo: start your own. |
| `notes/<NAME>-SPEC.md` | The spec for a new piece of work, written before its phases. Also local and git-ignored; copied to `docs/specs/` when the feature is finished. |
| [`docs/DECISIONS.md`](../DECISIONS.md) | Every decision, numbered (D-001 on), with why and what was turned down. |
| [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) | The data flow and the module map: where each piece of code lives. |
| [`docs/specs/`](../specs/) | The specs of what has been built: [the original](../specs/ORIGINAL-SPEC.md) and one per feature added since. For consulting (DECISIONS.md wins where they differ). |
| [`docs/DESIGN.md`](../DESIGN.md) | The look: brand, colours, type. |
| [`docs/guide/`](../guide/README.md) | The users' guide, also shown in the app. |

## Maintainers' how-tos

In this folder:

| Page | Read it when |
|---|---|
| [The working documents](working-docs.md) | starting on the project: how PHASES, DECISIONS and ARCHITECTURE work and why they're kept up to date |
| [Updating the guide](updating-the-guide.md) | something the app shows has changed |
| [Adding a model](add-a-model.md) | a part needs a SPICE model in the library |
| [Adding a starter circuit](add-a-starter.md) | adding a pedal to File → New from starter (with the wish list) |
| [Adding a core block](add-a-block.md) | adding a block to the core library |
| [Releasing a version](release.md) | cutting a version |

## Working with an AI agent

The instructions are in [`AGENTS.md`](../../AGENTS.md), the file coding agents read, Claude Code included. The skills are in Claude Code's format.

**What the agent reads.** The agent loads `AGENTS.md` at the start of every session. It tells the agent to read [`working-docs.md`](working-docs.md) (what is where and how the project's documents are kept) and `notes/PHASES.md` (the current phase and the last session's note; local and git-ignored), and to keep the first read short beyond that: it searches `docs/DECISIONS.md` by area tag rather than read all of it, and consults the specs in `docs/specs/` when it needs them. It sets the rules: reuse before writing, tests with the code, one owner per concept, no new dependency without a decision, nothing installed outside a container, and how to end a session.

**Starting from a fresh clone.** Install Podman or Docker, `make` and the agent, clone, and start the agent in the repo's top folder. With no `notes/PHASES.md`, the agent builds the dev image, installs the hook and runs `make check` itself, then asks what you want to work on and proposes a plan in phases for you to agree. You can run the same steps by hand: `make dev-image`, `make hooks`, `make check`.

**Skills.** Three jobs are long and particular enough to have agent skills, in `.claude/skills/`. Claude Code finds them by itself and uses one when a request fits:

| Skill | What it does |
|---|---|
| `fit-model` | Fits our own SPICE model to a maker's datasheet (BJT, diode, LED, JFET, op-amp) and adds it to `library/models/` with its record and measured checks. Holds the fitting tools (`tools/`) and the worked fits the model records cite (`worked/`). |
| `build-starter` | Turns a published pedal schematic into a starter circuit with its acceptance file: drawn by script, models checked, expected values from the source, no Problems. Holds a worked example (`make_klon.py`). |
| `draw-circuit` | Draws a circuit worked out with the user as a file they open in the app: parts placed and wired by script, the drawn nets checked against the netlist meant, looked at in the real app (Problems, DC voltages, a picture), then copied into their circuits folder. Holds a worked example (`example_boost.py`) and the look (`look.py`). |

The skills are in Claude Code's format; another agent can read a skill's `SKILL.md` and follow it.

The other jobs (adding a block, adding a model by hand, releasing) are how-tos above, for a person or an agent alike.

**Permissions and personal settings.** Claude Code's per-person settings (`.claude/settings.local.json`: allowed commands and the like) and its memory belong to each machine; keep them out of commits. Anything the project needs every session to know goes in the documents above, not in an agent's memory.

**Keeping the agent honest.** Expected values in acceptance files come from published sources with their links, never from memory. The person checks what tests can't judge (does it look and read right) from a test list of their own (`notes/TESTLIST-*.md`, git-ignored like PHASES.md). Review DECISIONS.md entries as they land: they say what the code is meant to do.
