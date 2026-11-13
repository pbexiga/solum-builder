# Decisions

One entry per decision a future session would otherwise re-debate. Newest at the bottom.

- **Numbers are permanent.** Code, tests and docs cite entries by number, so an entry is never renumbered or removed. A decision that changes gets a new entry; the old one becomes a one-line stub saying what replaced it.
- **Format:** ``**D-NNN — Title** (date) `tag` …``, then what was decided (precise enough to check the code against), why, and *Alternatives:* turned down. Stubs are one line.
- This file was pruned once, before the first public commit (D-304): history, phase status and session narrative were taken out; every decision and its reasons were kept.

## Tags

Every entry's heading ends with one or more area tags. To find the decisions about an area, search for its tag with the backticks, e.g. ``grep -n '`panes`' docs/DECISIONS.md``; don't read the file whole. A new entry takes every tag that fits, from this list only (a unit test checks, `tests/unit/test_decisions.py`). A new tag is added here first.

| Tag | Covers |
|---|---|
| `project` | The stack, packaging, dependencies, licences, tests and how the work is run |
| `docs` | The user guide, Help, and the project's own documents |
| `sim` | Netlists, running ngspice, measuring, the cache, speed |
| `schema` | The circuit and block file format, schema versions, migrations |
| `power` | Supplies, rails, batteries, charge pumps, regulators |
| `editor` | Drawing and editing: parts, wires, labels, selection, blocks dropped on the sheet, notes |
| `panes` | The result panes and views: probe, DC, frequency, Bias & headroom, Edit curve, knobs |
| `audio` | Rendering audio, guitar input, NAM amps and cabs, takes |
| `rules` | The rules and the Problems pane |
| `models` | SPICE models and part types, fits to datasheets, Parts and datasheets, Add a model |
| `library` | Starter circuits, blocks, and the published sources and acceptance files behind them |
| `build` | The build package: parts list, schematic and other exports, wiring diagrams |
| `look` | The look: brand, fonts, themes, layout and wording |

---

**D-001 — Build our own, clean-room** (2026-10-19) `project`
A self-hosted simulator inspired by PedalSpice and CircuitJS features. No code, assets or layouts copied from either. PedalSpice's terms forbid reverse engineering and automated access; feature ideas came from its public site and screenshots.

**D-002 — Probing is the core feature** (2026-10-19) `panes`
Click any node or part and get a view made for it (waveform, harmonics, DC, annotation), with "at this point" and "at the output" side by side. Audio is secondary. *Why:* existing tools don't lead with this, and it matches how builders document their builds.

**D-003 — ngspice as the simulator** (2026-10-19) `project`
ngspice for all nonlinear and authoritative analyses; no SPICE engine of our own. *Alternatives:* own MNA solver (only for linear live curves, D-012), CircuitJS's engine (no SPICE model cards).

**D-004 — Native ngspice default, WASM fallback** (2026-10-19) — superseded by D-087: native ngspice only, behind the `SimEngine` interface. `project`

**D-005 — Python backend** (2026-10-19) `project`
Python 3.12 + FastAPI. *Why:* numpy/scipy for FFT, resampling and convolution; NAM's reference implementation is Python; ngspice via ctypes. *Alternative:* Node (dropped once the container answered portability).

**D-006 — Ship as one Docker image** (2026-10-19) `project`
`docker compose up` is the main way to run. The image bundles native ngspice, the Python dependencies and the frontend. Running from source stays possible (`pip install` + system ngspice). Image size: see D-026 (no PyTorch, ~220 MB).

**D-007 — No frontend build step** (2026-10-19) `project`
Plain JS ES modules served as static files; uPlot vendored; SVG for the schematic. *Why:* no npm/node in the toolchain. *Alternative:* TypeScript + Vite (better types; adds node to dev and image build).

**D-008 — Files are the source of truth; SQLite is index + cache** (2026-10-19) `project` `schema`
Circuits, blocks, models and rules are JSON/YAML files. SQLite (`index.sqlite` in `CACHE_DIR`) holds the search index and sim/render cache metadata, and is always rebuildable. *Why:* diffable, no DB server. *Alternative:* Postgres (overkill for one user).

**D-009 — Repo is read-only library; user data outside it** (2026-10-19) `project`
The core library ships in the repo/image and updates with `git pull` or a new image. User data lives in `DATA_DIR`; cache and index in `CACHE_DIR` on a local disk. *Why:* updates can never conflict with or delete user work; SQLite on network shares risks corruption.

**D-010 — Every circuit is a block; paste-flatten by default** (2026-10-19) `library`
Inserting a block copies its parts (renumbered) into the circuit. Linked `.subckt` instances are a later feature. *Why:* builders tweak blocks per circuit and want flat designators for BOMs and build docs. (Provenance tracking dropped, D-075.)

**D-011 — Layered library lookup** (2026-10-19) — refined by D-074/D-075: core and user layers both listed, core never hidden or edited in place. `library`

**D-012 — In-browser linear solver for live curves** (2026-10-19) `sim`
A small complex-valued MNA solver in JS gives instant curves while dragging values and knobs. It must match ngspice `.ac` within 0.1 dB on shared fixtures (parity test). *Why:* sub-millisecond updates while dragging; ngspice round trips are ~10–50 ms plus network.

**D-013 — Rules as YAML + Python checks, tested three ways** (2026-10-19) `rules`
One YAML file per rule (message, why, fix, highlight, fixtures) with the check in Python. Tests: per-rule fixtures, a known-good corpus (zero errors), and mutation testing of corpus circuits. *Why:* rules are content to review; mutation testing finds gaps automatically.

**D-014 — Any block can open as a calculator** (2026-10-19) — superseded by D-081: value sliders in the inspector, no calculator pane. `library`

**D-015 — Offline audio rendering, NAM after the circuit** (2026-10-19) `audio`
Audio is rendered, not real-time: oversampled ngspice transient → downsample → NAM → optional IR. Re-renders only when circuit or knobs change; cached by hash. Real-time playback is a non-goal.

**D-016 — Power modes share rail names** (2026-10-19) `power`
Circuits reference global rails only; the Power menu decides what drives them. Charge pumps are behavioural (DC + output impedance + ripple), not switch-level. (Rails and modes refined in D-069, D-071, D-091, D-093.)

**D-017 — Reference circuits are acceptance tests** (2026-10-19) — superseded by D-019. `library`

**D-018 — Editing model borrowed from CircuitJS** (2026-10-19) `editor`
Hotkey per part, drag to wire, double-click to edit, live probes. Layout after PedalSpice: palette left, canvas centre, stacked result panels right (D-057).

**D-019 — Validate against classic, measured circuits** (2026-10-19) `library`
Acceptance tests use widely built pedals with published analyses and measurements (TS808, Big Muff, Fuzz Face, Rat from ElectroSmash, and more starters since). Expected values are read from the source and stored with the link and a tolerance; never from memory. Unbuilt designs aren't used: their targets are design intentions, so validating against them would be circular.

**D-020 — Testing stack and layers** (2026-10-19) `project`
pytest with markers for layers (unit / sim / acceptance / parity / rules / ui), `hypothesis` for property tests, snapshot tests for generated netlists, `pytest-cov` with an 85 % floor on core packages, Playwright (Python) for UI tests and the JS solver's parity tests in a real browser. All dev-only: none ship in the runtime image. The unit suite stays fast with no ngspice so it can run constantly.

**D-021 — Name and brand: Solum Builder** (2026-10-20) `project` `look`
The app is "Solum Builder" (package `solum`, CLI `solum`, compose service `solum-builder`). Logo, favicon and palette come from solumfx.com (tokens ink, bone, slate, ocean, cloud, brass; logo stamp in silver `#B0B8BD`). Visual rules live in `docs/DESIGN.md`; colours are defined only in `web/theme.css`.

**D-022 — Fonts vendored, not fetched** (2026-10-20) `look`
Fahkwang (display) and Lora (prose) are vendored in `web/fonts/` with their OFL licence files. UI controls use `system-ui`, values `ui-monospace`. *Why:* the app works offline and makes no third-party requests.

**D-023 — No unbuilt user designs in the repo** (2026-10-20) `project`
The repo ships only published circuits as starters. A user's own designs are ordinary circuits in `DATA_DIR`. Large-circuit and benchmark checks use the Big Muff.

**D-024 — Timing: ngspice is fast enough; audio renders are background jobs** (2026-10-20) `project` `sim`
`solum bench` runs `library/bench/big-muff.cir` (4 × 2N5089, 4 × 1N4148, tone stack) through native ngspice 44.2. Median wall time:

| Analysis | Desktop (Ryzen 7 5800X3D) | NAS (Pentium Gold 8505) |
|---|---|---|
| `.op` | 0.5 ms | 0.8 ms |
| `.ac` 10 Hz–100 kHz, 100 pts/dec (401 pts) | 2.2 ms | 2.3 ms |
| `.tran` 50 ms, 10 µs step | 38 ms | 31 ms |
| `.tran` 5 s at 96 kHz, max step 1/96000, `.save v(out)` only | 3.4 s | 2.8 s |
| Peak RSS of the whole bench | 62 MB | 63 MB |

Results are identical across machines to the last printed digit. `.op` + `.ac` + short `.tran` per knob change is ~35 ms, far inside "< 1 s". A 5 s render is ~0.7× real time, so audio stays an offline background job (D-015). Long transients `.save` only the nodes they need: ngspice keeps every vector in memory.

**D-025 — WASM fallback in the browser** (2026-10-20) — superseded by D-087: not built. `project`

**D-026 — NAM inference in numpy, no PyTorch** (2026-10-20) `project` `audio`
The NAM WaveNet forward pass is implemented in numpy (`solum/audio/nam.py`): the classic architecture nearly all shared captures use (WaveNet, Tanh, no gating/FiLM/grouping), widened by D-084. Anything else gets a plain "this capture type isn't supported yet". Tested against output files made once by the official package (fixtures), so PyTorch is never a dependency.
Spike (8 s clip at 48 kHz, standard WaveNet): official package + PyTorch 0.50 s and +1.7 GB of image; numpy 0.54 s and nothing added; outputs agree within 2 × 10⁻⁸. *Cost:* the `.nam` format keeps growing; we track only the classic subset.

**D-027 — ngspice in the image: Debian trixie libngspice0 + code models** (2026-10-20) `project` `sim`
Base image `python:3.12-slim-trixie`; `libngspice0` 44.2 from Debian. That package ships no XSPICE code models and no `spinit`, so macromodels using `POLY` sources (TI's TL072) fail. A build stage downloads the `ngspice` .deb and copies only `usr/lib/<arch>/ngspice/*.cm` and `usr/share/ngspice/` into the runtime image. *Alternatives:* the `ngspice` CLI package (drags in X11); building from source (slower builds, own the patching).

**D-028 — Native engine: in-process, self-healing, sanitised input** (2026-10-20) `sim`
`NativeNgspice` loads libngspice once per process, serialises calls with a lock, and reads results from memory (`ngGet_Vec_Info`). Findings that shaped it:
- Some load errors (e.g. `MFG=PHILIPS`) make ngspice call ControlledExit and every later run fails. The engine then `dlclose`s and reloads the library (under 1 ms).
- A comment line starting with `*#` is run as a command and blocks forever. `prepare_netlist` (shared by every engine) drops `*#` lines and rejects `.control` blocks, which can run shell commands.
- ngspice runs analyses in its own order, and two of one kind come back in an unreliable order. So a netlist holds at most one analysis of each kind and results are looked up by kind (`SimResult.plot("ac")`).
- Timeouts and worker processes: D-040, D-083.

**D-029 — Model cards: what ngspice 44 accepts** (2026-10-20) `sim` `models`
Fixes the model importer applies (`clean_card`): strip LTspice-only `Vceo=`, `Icrating=`, `mfg=` (fatal in ngspice; kept as metadata, Vceo/Icrating feed the rating rules); strip JFET `isr`, `nr`, `alpha`, `vk` (ignored with warnings; breakdown effects pedals don't reach); drop `*#` lines (D-028). TI's TL072 needs the `spice2poly` code model (D-027). The Motorola and Fairchild 2N5457 cards differ by 4× in Idss, so cards are chosen against datasheets.

**D-030 — Dev workflow in containers; FastAPI served by uvicorn** (2026-10-20) `project`
- All Python tooling runs in the Dockerfile's `dev` stage; `make` wraps it with Podman or Docker. Nothing is installed system-wide. Throwaway files live in the gitignored `scratch/`. `make LOCAL=1 …` runs directly with Python 3.12 + libngspice.
- Runtime dependency `uvicorn` (FastAPI needs an ASGI server); dev-only `httpx` (FastAPI's `TestClient`). Starlette warns that `httpx` in TestClient is deprecated for `httpx2`; harmless, switching is a dependency change.
- The pre-commit hook lives in `scripts/pre-commit`; `make hooks` installs it.

**D-031 — Memory budget: 8 GB** (2026-10-20) `project`
Solum Builder is designed to fit in 8 GB for all its processes together, so it can share a NAS with other services. The whole bench, a 5 s render included, peaks at 63 MB (D-024); a render worker is ~140 MB (D-083).

**D-032 — Circuit schema is Pydantic models; the JSON Schema file is generated** (2026-10-20) `schema`
`solum/circuit/schema.py` defines the circuit file as Pydantic models, the single source of truth. `docs/circuit.schema.json` is generated from them (`make schema`) and a unit test fails if it's stale. Unknown fields are rejected. Part values are stored as typed (`"4k7"`) so files round-trip; files are saved without defaults and written atomically. Errors name the part (`part R1 value: Couldn't read the value '4k7k'`).
Refs are letters+digits only (generated SPICE names can't collide); net names have no `.` (`Q1.D` always means a pin); `pos` is integer schematic units; a single-throw switch is open at position 0.
*Alternatives:* the `jsonschema` package (a Rust extension), a hand-written validator (two definitions of the format).

**D-033 — YAML via one `yaml.safe_load` loader** (2026-10-20) `schema`
PyYAML is a runtime dependency. Everything reads YAML through `solum.yamlio.load_yaml`, which only calls `yaml.safe_load`.

**D-034 — Acceptance values from archived ElectroSmash pages** (2026-10-20) `library`
electrosmash.com stopped resolving (no address record); the Wayback Machine holds its analyses. Each `.expected.yaml` records the original URL, the snapshot URL and the date read.
Values come from the page text and tables (LaTeX in formula image URLs counts as text). A value only in an image that didn't archive is left out, and the fixture says so. Values read from images are marked `from: image` with the image link. Where the page contradicts itself, the fixture says which value was used and why.
Tolerances are set from what the published number is, before simulating: RC-formula corners ±10 %; values ElectroSmash measured or simulated with other parts ±2 dB (gains) or ±15 % (frequencies); bias voltages max(±10 %, ±0.15 V), wider where the page's transistor differs from ours (noted per check).

**D-035 — Pot tapers are piecewise-linear** (2026-10-20) `sim` `models`
`solum/circuit/pot.py` maps rotation to the pin-1-to-wiper fraction by straight segments: B linear; A 10 % at half rotation; C its mirror; W/G/S from ElectroSmash's TS808 tone-pot curve (28 % at 10 %, 37 % at 20 %, 50 % at 50 %, symmetric). Each half is at least 1 Ω. The A-taper midpoint is a common convention, not one maker's datasheet.

**D-036 — Connectivity rules** (2026-10-20) `rules`
Points connect when they coincide, when a wire joins them, or when one lies on a wire segment (T-junction). Crossing wires don't connect. Labels name nets and join same-named points anywhere; `GND` is node 0; two different labels on one net is an error. An unlabelled net is named after its first pin in sorted order (`R1.2`; see D-082); `Nets.resolve` accepts a net name or `REF.PIN`. Pin geometry lives only in `solum/circuit/parts.py`.

**D-037 — Model library layout** (2026-10-20) `models`
`library/models/<type>/<ID>.json` + `<ID>.lib`. The JSON holds the SPICE name, kind (`.model` or subcircuit with pin roles), source URL + licence, the importer's fixes, ratings, and a validation record. `tests/sim/test_models.py` re-measures every recorded value through the real pipeline and checks it against the datasheet range. (Which models ship and from where: D-156, D-159, D-288.)

**D-038 — Transient probe: three pick levels at 200 Hz; harmonics by coherent FFT** (2026-10-20) `sim` `panes`
Soft / med / hard are a 0.1 / 0.3 / 1.0 V-peak sine at the guitar input, from the TS808 page's figures (single coils 60–200 mV, humbuckers 200–600 mV, hard picking up to 2 V peak). 200 Hz; 10 cycles to settle plus 10 measured, 400 steps per cycle. The window is resampled to 256 points per cycle so FFT bins land on harmonics 1–8; drift from a coupling cap still charging is removed first. Gain is fundamental vs the input's; polarity is "inverted" past 90° of phase. Clipping estimate: THD over harmonics 2–8 (clean < 1 %, light < 5 %, moderate < 20 %, heavy above) plus peak asymmetry. (Settling refined in D-122.)

**D-039 — Simulation pipeline and bias targets** (2026-10-20) `sim`
`solum/simulate.py` (`Simulator`) is the one path from a circuit to results: solve bias targets, generate the netlist, run, read vectors back by net name. Every analysis first solves trimmers with a `bias_target` (bisection on rotation over `.op`, 1 mV tolerance; several trimmers repeat until all hold); an unreachable target is a plain error naming the reachable range. `.op` also saves each primitive transistor's terminal currents.

**D-040 — Engine run timeouts** (2026-10-20) `sim`
Native runs use `bg_run` and wait on ngspice's "background thread ended" callback; past the timeout (`DEFAULT_TIMEOUT`, 30 s) the engine sends `bg_halt` and raises a plain error, and the next run works. Interactive runs stay in-process (~1–40 ms, serialised by the lock); renders run in worker processes (D-083).

**D-041 — Cache and the "AC invalid" flag** (2026-10-20) `sim`
`CachedEngine` wraps any engine; the key is SHA-256 over the engine name, version and the full netlist text. Results are `.npz` blobs under `CACHE_DIR/sim/`, indexed in `index.sqlite` with size and last use; above `CACHE_MAX_GB` (default 2) the least recently used go first. A missing index or blob is a miss, so the cache is safe to delete.
AC invalid: an AC result carries the saturated stages from its `.op`: a BJT with Vce < 0.3 V or Ic < 100 nA; a JFET pinched off (Id < 100 nA) or ohmic (Vds < Vgs − Vp); an op-amp output within 2 V of a rail. Coarse on purpose; the operating-point rules (D-077) give the explained warnings.

**D-042 — Acceptance files: check kinds and known gaps** (2026-10-20) `library`
- Acceptance circuits are starters in `library/starters/`. Substitutions are the source's own listed alternatives, written in the file and its `.expected.yaml`.
- Check kinds: `dc`, `gain` (or an upper bound `max_db`), `peak_gain`, `corner`, `notch`, `clip`. A check measures a node against `ref` (default the guitar input) after `set` (knobs, or a part change such as removing the amp load when the page's formula has none). Formats live in `tests/acceptance/expected.py`; measures come from `solum/analysis`.
- Tolerance policy (adds to D-034): gains from a formula on the page ±1 dB, unless the page's own simplification is known to shift it (then the reason and the hand estimate sit next to the wider tolerance).
- When the simulation misses a published value, tolerances are **not** widened after the fact. The check gets a `known_gap` with the reason worked out by hand and runs as a strict xfail: visible in `make accept`, and it fails if it starts passing.
- A value not on the page is dropped, not invented (listed under `omitted`). A check waiting on a source has `pending` and is skipped.
- Every value read off an image carries the archived `image` link and a `confirmed` mark; a test refuses unconfirmed image values.
*Why:* a suite that's green because tolerances were stretched would hide the cases worth looking at.

**D-043 — Datasheet values in model records** (2026-10-20) `models`
Datasheets are copyrighted, so only values and citations go in the repo (the PDFs stay in the gitignored `data/spec-sheets/`). Each validation record cites document, revision and table or figure. `DatasheetRange` has `tol`: a `typ` is checked only when a tolerance is given, and values read off a curve say so. Example: the LM308 macromodel's gain-bandwidth is about 23 % above National's typical curve, which explains most of the Rat's `slew-limited-gain` gap; the maker's model is kept as published.

**D-044 — Viewer API: the browser sends the whole circuit; the server owns geometry and results** (2026-10-20) `sim`
`GET /api/starters/{id}` and `POST /api/view` return the circuit view (`solum/view.py`): parts with pin positions and nets, label sides, junction dots, each wire's net, knob controls, probes. `POST /api/run` (circuit, probed nets, pick level) returns DC everywhere plus AC and scope at the probed net and the output; `POST /api/part` returns one part's view. A knob change edits the circuit JSON in the browser and re-posts it, debounced, newest request wins. Errors are `{"message"}` in plain English, 4xx for the user's, a fixed 500 message otherwise (logged).
*Why:* the browser never re-derives geometry or connectivity, and one round trip per change keeps it simple: about 120–130 ms of server time per Tone turn on the TS808 (`solum bench`, `knob_turn`), desktop and NAS alike. *Alternative:* knob deltas only (a second update path).

**D-045 — SI display strings come from the server** (2026-10-20) `sim`
`units.format_quantity(x, unit)` (`1.2 mA`, `4.7 kΩ`) is the display form of measured values, beside `format_value` (`4k7`, part values). The browser formats only fixed-decimal volts, dB and percentages (`web/fixed.js`); log-axis tick labels come from fixed tables in `web/plots.js`. *Why:* SI formatting has one owner.

**D-046 — Brand assets: outlined wordmark, TTF fonts, uPlot 1.6.31** (2026-10-20) `look`
An SVG shown through `<img>` or as a favicon can't use the page's fonts, so the logo, its `currentColor` variant and the favicon have `*-outlined.svg` copies with the wordmark as paths, made once by `scripts/outline_svg_text.py` (fontTools + uharfbuzz; not a project dependency). Fonts are the Google Fonts repository's TTFs, unconverted (~700 KB). uPlot 1.6.31 (MIT) is vendored in `web/vendor/uplot/`. No request leaves the machine (UI test).

**D-047 — UI and browser-logic tests: Playwright in the dev image** (2026-10-20) `project`
The dev image installs `chromium-headless-shell` into `/opt/ms-playwright`; the runtime image is unchanged. `tests/ui/` starts the real app on a free port with a temporary cache. DOM-free JS modules are tested by importing them into the app page (`tests/ui/test_js_logic.py`), including a check that every symbol's lead ends match `parts.py`'s pin offsets. UI tests fail on any browser console error.

**D-048 — What the part views show** (2026-10-20) `panes`
`solum/probe.py`. Device curves come from a DC sweep of a two-source test jig around the part's own model and measured values: diode I-V; transistor current against Vbe/Vgs with the collector/drain held at its operating voltage, so the curve passes through the operating point. Headroom: room to swing before a rail or saturation, judged at the drain/collector, or at the source/emitter for a follower (`view.rail_nets`). Op-amp: output and inputs against the supply. Pot: output and wiper response at 0/25/50/75/100 %; none for a trimmer solved for a bias target. Capacitor: DC across vs rating and the response at both nets.

**D-049 — Starter rows pulled closer** (2026-10-20) — superseded by D-060: starters drawn with wires. `library`

**D-050 — Theme contrast tuning** (2026-10-20) `look`
Text roles meet WCAG AA on the panel surfaces (`--text-3` `#868E94`, `--error` `#CF7466`); `tests/unit/test_theme.py` checks every text role on `--surface-0` and `--surface-1`. Layout CSS is in `web/app.css`, tokens only.

**D-051 — Editor: pure edits in the browser, the server draws; undo is a snapshot stack** (2026-10-20) `editor`
Every edit is a pure function from circuit JSON to new circuit JSON (`web/editor/edit.js`). The browser posts the result to `POST /api/view` and draws what comes back. A circuit the server refuses is rolled back with the plain-English message. Wiring that contradicts itself (two labels joined) still gets a geometry-only view with `problem` set, so it can be seen and undone.
Undo/redo (`web/editor/history.js`) keeps the whole circuit before each edit, up to 200 steps: circuits are small and never mutated, so a snapshot is a reference and there are no inverse operations to get wrong. Knob turns aren't edits (D-103). `symbols.js` `pinPositions` reads pin positions from the symbol leads; a UI test compares them with `pin_positions` for every part and rotation.
*Alternatives:* inverse commands (more code, more bugs); a server-side edit API (a round trip per change, a second circuit model).

**D-052 — User circuits: files, index in SQLite, `tags`** (2026-10-20) `schema`
User circuits live in `DATA_DIR/circuits/` (file naming: D-075, D-076). The index is a `circuits` table in `CACHE_DIR/index.sqlite`: name, tags, part models, a `problem` for files that can't be opened, each file's size and mtime. `CircuitStore.sync()` runs at start and before every listing; it stats files and re-reads changed ones, so the index is safe to delete and hand-edited files show up. Search matches a case-insensitive substring of the name, a tag or a part model. Starters are read-only: Save on a starter is Save as.

**D-053 — Hotkeys and gestures** (2026-10-20) `editor`
One key per part type (R resistor, C capacitor, P pot, T trimmer, S switch, D diode, Q BJT, J JFET, U op-amp…), L net label, G ground, W wire, **Space rotates** (R is the resistor in CircuitJS and LTspice), Delete/Backspace, Enter opens the inspector, Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y), Ctrl+S, Esc. The full list lives in `web/keys.js` (D-302). Click probes; drag a part to move it; drag empty space to pan; double-click a part or label to edit it. Grid dots double their spacing as you zoom out so they stay at least 14 px apart. (Wiring: D-062, D-063.)

**D-054 — "No DC path" in plain English, without changing netlists** (2026-10-20) `sim` `rules`
A half-drawn circuit often has islands with no DC path to ground. The message names the nets and says what to do (now a `stops_sim` topology rule, D-077). *Alternative rejected:* `.option rshunt` would make every half-drawn circuit simulate, but changes every netlist and result and plots a confident answer for a floating node (flag, don't plot).

**D-055 — "Try several values": one run per value, overlaid; 12 sweep colours** (2026-10-20) `panes`
The inspector's sweep takes a comma list (≤ 12) of values (R, C, pot, trimmer, source, amp) or models (diode, transistors, op-amp). `POST /api/sweep` validates each (errors name the value), runs `.op` + `.ac` + the scope `.tran` per value, and returns DC, frequency response and waveform at the probed net and the output. Frequency and Scope overlay the runs until the circuit changes or Clear sweep.
Colours: `--plot-sweep-1..12` is one ramp brass → silver → cloud → bone, and n runs take n evenly spaced steps (`sweepStyle`). Each line carries its value at its right end. The output curve has its own token, `--plot-output`.

**D-056 — Inspector fields** (2026-10-20) `editor`
`web/editor/fields.js` lists the fields per part type and turns the form back into a patch (pure, tested). Values stay as typed (`4k7`); the server parses them. Display scaling only: rotation in %, measured Idss in mA, switch position from 1. A JFET's "drain target" writes the chosen trimmer's `bias_target` (`node: "Q1.D"`) and clears any other trimmer aimed at that drain. Renaming a part also renames its note key, bias targets and probes on its pins. One popup component (`web/editor/form.js`) serves the inspector, label names and the circuit dialogs.

**D-057 — PedalSpice-style layout in Solum's colours; drag-and-drop palette** (2026-10-20) `editor` `look`
A palette of tiles (symbol above the name) dragged onto the canvas or clicked then placed; a header with menus and a Power selector; parts drawn large enough to read; +/−/Fit buttons. Only the structure is borrowed: colours, fonts and every drawing are our own (D-001). Hotkeys are shortcuts shown only in tooltips and menu hints (and Help → Hot keys, D-302). A fit never zooms in past 2 px per unit. GND labels draw as a ground symbol and rail labels as a supply bar.

**D-058 — The start page is a new sheet** (2026-10-20) `editor`
Opening the app (or File → New sheet) shows an unsaved Untitled circuit with a guitar input on the left and an amp (1 MΩ) on the right, from `GET /api/blank` (`blank_circuit`, so the schema stays on the server). Until anything is wired the panels say what to do instead of plotting a −290 dB "response". Saved circuits can be deleted (`DELETE /api/circuits/{id}`) after a confirm.

**D-059 — Zigzag resistor and pot symbols; wires stay square when parts move** (2026-10-20) `editor`
Resistors, pots and trimmers draw as zigzags, as most pedal schematics do. Text on a part turned 180° stays upright with the ref above the value; a pot's label isn't repeated after its ref. (Wire behaviour on moves: D-063, D-066.)

**D-060 — Starters drawn as wired schematics** (2026-10-20) `library`
Starters are drawn with wires, ground symbols and rail bars, laid out by stage, as printed schematics are. Labels only where they mean something: `in`, `out`, rails and GND, `VREF`, nets that carry a note, and row joins; other nets take automatic names. The JSON files are the source of truth.

**D-061 — Power mode `custom`** (2026-10-20) — superseded by D-091: no custom mode; V+ and V- always come from the Power menu. `power`

**D-062 — Wire tool: click to start, click to bend, ends only on a pin; balls on wire ends** (2026-10-20) `editor`
With the Wire tool on, a click starts a wire anywhere; each click on empty grid adds a bend; a click on a pin, label, wire end or a wire's body (a T) finishes it. Legs are square: the next leg leaves the last bend the way the pointer first moves. Nothing is added until the wire finishes, so the tool never leaves a dangling wire; Esc or right-click drops it (a second Esc leaves the tool). The tool stays on after a wire. Without it, dragging from a pin draws a quick one-bend wire.
Wire ends: a filled ball where a wire meets a pin or label, an open ball where it meets nothing, none where wires bend into each other (junction dots mark 3-way joins). Every end has a handle; dragging it moves every wire end on that point together. Wire direction carries no meaning.

**D-063 — Wires lay themselves out: routing around parts, re-laying on moves, hops on crossings** (2026-10-20) `editor`
A grid router (`web/editor/router.js`, A* on the 10-unit grid) finds the tidiest square path, with a penalty per bend and per crossing. Since any point on a wire connects (D-036), a route must touch nothing it isn't meant to: it stays out of part bodies and their text, never passes over a pin, label or another wire's end, never runs along another wire, and may cross a wire at right angles but not turn on it.
- **Moving a part** (or rotating it, or dragging a wire-end ball) re-lays each run of wire from a moved point from its far end, as a fresh wire would go. Old bends aren't kept, so dragging leaves no trail. A run with both ends on the moved part moves with it. While dragging, the new wires show as a ghost.
- **Drawing with the Wire tool** keeps the leg as aimed unless it would cut through a part body.
- **Crossings** are drawn with a hop on the horizontal wire (drawing only).
Re-laying replaces hand-placed bends on runs touching what moved: the price of never leaving diagonal or trailing wires. Falls back to a plain elbow if no clear path exists within 300 units. (Kept bends: D-164.)

**D-064 — The ideal supply switches DC sources off** (2026-10-20) — superseded by D-091: DC sources are always live. `sim` `power`

**D-065 — Run button; auto-run is a switch, off by default** (2026-10-20) `panes`
Edits don't run the simulation by themselves: the Run button turns brass and the panels say the results are out of date until Run (or Ctrl+Enter). Things that are themselves a request for a result still run: opening a circuit, probing, turning a knob, the pick level. The Auto-run switch restores run-after-every-edit (debounced 250 ms), remembered per browser. *Why:* avoid simulating every half-drawn edit.

**D-066 — Moves keep connections** (2026-10-20) `editor`
In `relay`: wires are split wherever something joins them part-way (`splitAtJoins`) before re-laying, so a run stops at a T; a moved pin that touched a pin staying put gets a wire back to it; with no clear route (a part dropped on another) the router tries again through bodies and text, still touching no pin, label or wire, before the last-resort elbow. `tests/ui/test_editor_logic.py::test_moving_or_turning_any_part_keeps_its_connections` moves every starter part four ways and turns it, and checks the nets are unchanged unless a pin was dropped onto something.

**D-067 — Comparing values: numbers beside the curves; a supply is compared at the output** (2026-10-20) `panes`
A sweep comes with a small table: per value, DC, gain at 1 kHz and scope peaks at the net shown (`series.sweepSummary`); a note when the runs overlap (within 0.1 dB and 1 % of the peak); and the bias points whose DC moved most (`dc_all` in `POST /api/sweep`). When the probed net is a supply or GND, the view starts on the output (a supply carries no signal). The "try several values" row says what it compares and gives a fitting example per part type.

**D-068 — Power → Advanced, free-form rails** (2026-10-20) — superseded by D-069, D-071 and D-093. Kept from it: comparing supply voltages needs no supply drawn (`POST /api/sweep` with `field: "rail"`; plain numbers keep the rail's sign); `plots.replace` holds each plot's old height until the next frame so a redraw doesn't jump the pane's scroll (Firefox). `power`

**D-069 — Supplies by polarity: V+ and V-, a voltage each** (2026-10-20) `power`
You pick a polarity and a voltage: V+ (positive) and V- (negative), each a voltage or none; "9" on V- is −9 V. Turning a rail off moves everything that used it (labels, op-amp supplies, block ports) to the rail left or turned on in its place (`edit.setRails`); when that's ambiguous it's refused, naming what uses it. The palette always has V+ and V- Supply tiles; placing one the circuit hasn't got adds that rail (`edit.addSupply`). A label typed with the Net label tool doesn't, since a net named like a supply may be a filtered supply after a resistor. (Menu: D-093.)

**D-070 — The Rat's supply is V+ like the other starters** (2026-10-21) `power`
The Rat's rail is V+ and its filtered supply (after R10, 47 Ω, with C11 and C12) is V+F, with a net note; U1's `supply` names V+F.

**D-071 — Rails are V+ and V- only** (2026-10-21) `power`
`Power` validates its rails: only `V+` (positive) and `V-` (negative); a file with any other rail, a wrongly signed or a 0 V one is refused with a plain message saying how to fix the file. Other supply-like nets are ordinary nets (V+F, VREF); an op-amp's `supply` may name any net. No schema bump: a migration couldn't know which polarity an arbitrary name meant.

**D-072 — Blocks: paste-flatten in the editor, a library on the server** (2026-10-21) `library`
- Pasting is an edit, so it lives with the pure edit operations in `web/editor/blocks.js` (D-051): renumbering reuses `nextRef`, splicing reuses `routeWire`, copy/paste of a selection is the same function. The server owns storage: `solum/library.py` lists, loads and saves blocks. `tests/ui/test_blocks_logic.py` checks the JS paste against Python connectivity, including a hypothesis test that repeated pastes never collide and never join a host net.
- Core blocks in `library/blocks/` (read-only, ship with the app), My blocks in `DATA_DIR/blocks/` (D-074, D-075).
- **Paste-flatten rules.** Parts get the next free ref per prefix (D-141). Supplies and GND keep their names and connect by themselves; a supply the circuit hasn't got comes along at the main rail's size. Every other label is renamed to a name the circuit doesn't use (`in` → `in_2`), so ports arrive as labels to wire up and nothing joins by accident (D-189). Bias targets, op-amp supplies and notes follow the renaming. The block lands at the nearest spot where its box touches nothing (`clearSpot`).
- **Splice.** Dropped on a wire, the wire's two ends are routed to the block's `in` and `out` ports, or its first two non-supply ports; a block without two ports is refused.
- **Ports** map a port name to a *labelled* net (unlabelled net names change on renumbering). Marking a port on an unlabelled net puts a label on one of its pins. Supplies and ground need no port.
- **Selection.** Shift+drag draws a box; Shift+click (and Ctrl+click, D-092) adds or removes; Ctrl+A selects all; dragging a selected item moves the selection (D-113); Delete, Ctrl+C/Ctrl+V work on it. B opens the Blocks dialog.
*Alternatives:* paste on the server (a second renumberer and router); linked `.subckt` instances (later); ports on pin names (break on renumbering).

**D-073 — Core blocks: contents and sources** (2026-10-21) `library`
- Big Muff gain stage and tone stack come from the Big Muff starter, so their values are ElectroSmash's (D-019).
- Vref divider (100k/100k, 1 µF) and 9 V input filter (47 Ω, 100 µF, 100 nF) use the ProCo Rat's values; the filter takes V+ to V+F (D-070).
- Fender TMB: AB763 blackface values, slope 100k, treble 250 pF, bass 100 nF, mid 47 nF, treble 250kA, bass 250kA, mid 10kA (robrobinette.com "How the TMB tone stack works"; a Music Electronics Forum AB763 schematic for 47 nF and the 10k mid pot). A plain TMB: no source defined a "Thick" switch, so none was guessed. Checked against Yeh & Smith (D-080).
- Gain stages, buffers and the clipper use ordinary starting values (said in each description): templates to edit, not measured circuits.
- Charge pump: see D-093, D-094.
Each block is checked through ngspice in a jig (`tests/sim/test_blocks_sim.py`). The full list is in `docs/guide/whats-included.md` (D-297).

**D-074 — Core blocks are never hidden; a Blocks manager; a drag moves the whole selection** (2026-10-21) `library`
- Core blocks stay as shipped and are always listed beside My blocks. `delete` removes only My blocks.
- The Blocks dialog (B) lists both, with Core / My blocks toggles and A–Z / Z–A (D-075); grouping and sorting are a pure function (`blockSections`).
- Save as block with a name already in My blocks asks "Replace it?" instead of making "name-2".
- A drag moves the whole selection: `moveItems(circuit, items, dx, dy)` moves selected parts, wires and labels; every moved point ends a run of wire in `relay`, so a wire between moved points moves with them and one to something left behind is re-laid. `relay` gives a wire back as one piece when all its pieces moved alike.
- Opening is "last one wins" (`latestOnly`): an older answer never overwrites the circuit asked for last.

**D-075 — Blocks are plain copies; file names follow names; version tags and finals; the save prompt** (2026-10-21) `library`
- **A pasted block is a copy.** Nothing links a circuit back to a block (no provenance, no change notice); schema v5 drops `provenance`. Linked blocks only with real versioning (later).
- **File names follow names**: the file name is `id_from_name(name)`; Save with a new name, rename and Properties rename the file; a taken file name is refused in plain English, never suffixed. My blocks may share a core block's name (separate folders; `get(id, layer)` picks).
- **Version tags.** Every file has `version: {major, minor}` shown `v1.12`. A save that changes anything adds one to the minor; an unchanged save leaves the file alone. **New major version** (`CircuitStore.new_major`) writes a frozen copy (`final: true`) and carries on at the next major (file naming: D-076). **Final** files are read-only until unlocked (asked first). Not built: history between finals, compare, carrying fixes forward.
- **Core blocks and finals are edited as unsaved copies** badged *Never saved*; Save asks for a name and saves into My blocks.
- **Properties**: name, tags, description (an undoable edit); read-only rows for kind, path, version, last saved, status, and Mark as final / Unlock.
- **The save prompt** in the usual layout ("Do you want to save the changes to "X"?", **Don't Save** apart from **Cancel** and **Save**; Enter saves, Escape cancels) — `ask()` in `web/editor/form.js`, used for every question instead of `confirm()`. It comes before anything replaces unsaved work (`confirmLeave` / `leaveTo`), browser Back and Forward included (history entries are numbered, so Cancel steps back by the right amount). Closing the tab gets only the browser's own warning. A draft or auto-save is "Later".
- **Header**: name (renamed with the pencil, D-287), *Block*, the tag, *read-only*, *Not saved* / *Never saved*; it never wraps.
*Alternatives:* random ids with the name in metadata (files you can't tell apart); auto-save (saving is deliberate); tabs (later).

**D-076 — One file per major version, the name shared, the short link finds the newest** (2026-10-21) `library`
- **File names carry the major:** `<name>-v<major>.json`, circuits and blocks alike. All versions keep the same name; the tag tells them apart. The family is the file name without `-v<n>` (`split_id`, `file_id` in `solum/store.py`).
- **Current = newest major.** The short id resolves to it (`resolve_id`) in the API and the address bar (`#block/test-block` current, `#block/test-block-v1` older), so bookmarks follow the newest. Unlocking an old version for a fix doesn't make it current.
- **New major version** marks the current file final in place and writes `<name>-v<n+1>.json` at `v<n+1>.0`; refused on an older version.
- **Names** belong to every version of one circuit/block. A name ending in a version like "v2" is refused, so a file name can't be read two ways. Renaming renames every version.
- **Delete** removes the open version only; the next newest becomes current.
- **Old files are tidied, not migrated:** `sync()` renames any file whose name isn't the app's and drops a trailing " v<major>" from an old final's name (`_tidy`, `strip_version`); unreadable files or taken names are left alone.
- **Lists:** Open… and the Blocks dialog share `listFiles` (`web/editor/files.js`) and the controls: **Current only** (on by default) and A–Z / Z–A.
*Alternatives:* versions as folders (one flat folder per kind is easier to see and back up); the current version without a suffix (a new major would rename the working file).

**D-077 — Rules: one YAML file each with inline fixtures, a check registry, three layers, and a stop before every run** (2026-10-21) `rules`
- **Rule files.** `library/rules/<id>.yaml`: `id` (= file name), `layer`, `severity` (error / warning / info), `check` (a function in `solum/rules/checks.py` registered with `@check(layer)`; the loader refuses a missing check or one of another layer), `title`, `message`, `why`, `fix` (`{names}` filled from what the check found), and `fixtures`. Each hit carries the refs and nets to highlight.
- **Fixtures are inline**: `CircuitBuilder.from_spec` specs, `{starter: id}`, or for `sim_error` rules `{log: [...], nodes: {...}}`. `tests/rules/test_rules.py` runs every `bad` (must fire, on the refs in `expect` if given, no `{…}` left) and every `good` (must stay quiet) through real ngspice.
- **Layers.** `topology` on the drawing; `operating_point` after a `.op`; `sim_error` explains a failed run, with one rule marked `fallback` for anything else. A topology rule may say `stops_sim`: the circuit isn't simulated while it fires.
- **A stop before every run.** On a floating net ngspice often "succeeds" at 0 V after its fallbacks, so `Checker.require_runnable` runs the stopping rules before every simulation and refuses with `CantSimulate` (422, "Can't simulate yet: …"). Whatever ngspice calls singular, the no-DC-path rule catches, plus resistor islands ngspice solves at 0 V.
- **Three graphs** (`solum/rules/graph.py`): *spice* (DC paths as ngspice sees them), *bias* (paths that set a DC voltage), *signal* (where a signal can pass, never through a supply, ground or a net a ≥ 1 µF cap ties to a supply, `AC_GROUND_FARADS`).
- **Blocks get topology rules only**, with their ports counted as driven.
- **Design-choice thresholds** are named constants in `checks.py`, not datasheet values: JFET Vds below 1 V; JFET gate 0.5 V forward; 0.25 W resistors when no rating is given; a polarised cap reversed by more than 0.5 V; more than 0.1 V DC at the output; under 1 Ω between supplies is a short. Ratings from model files win where they exist.
- **Problems panel**: count by severity, one row per problem; click for message, why and fix, and to select the part or net. `POST /api/problems` → `{problems, checked_op}`.
- **Known-good corpus and mutations.** Every starter and core block gives no problems at all. `tests/rules/mutations.py` breaks the corpus (remove a part, lift a pin, reverse a diode or polarised cap, swap an op-amp's supplies; `python -m tests.rules.mutations` prints the report); every mutation must fire a rule or be listed with its reason in `tests/rules/mutation_gaps.yaml`, and a listed gap that now fires fails the test.
*Alternatives:* fixtures as separate JSON files (a rule can't be read on one screen); `.option rshunt` (D-054); checking only after a failed run (misses the silent 0 V).

**D-078 — Op-amp ratings from datasheets, minimum guaranteed figures** (2026-10-21) `models`
Model files may carry `vs_max` (total supply, absolute maximum) and `cm_neg_headroom` / `cm_pos_headroom` (how close to each rail the inputs may go), each cited in `rating_sources`. Values are guaranteed minimums, not typicals (e.g. TL072 36 V, 4 V each side, TI SLOS080W). The op-amp part view and the `opamp-input-common-mode` rule use them (`opamp_input_limits` in `solum/analysis/dc.py`); a model without them falls back to `OPAMP_RAIL_MARGIN` and says "rule of thumb".

**D-079 — Live curves: semiconductors measured by ngspice as N-port admittances; slider steps carry their element values** (2026-10-21) `sim`
- **Linearising.** The browser solves passive parts itself. Every semiconductor (op-amp subcircuits included) is a black box measured by ngspice at the real operating point: a 0 V source in series with each pin (`Ac(sense=True)`), `.ac` once as usual plus once per free port node with a 1 A AC current injected there (`Ac(inject=net)`). Per frequency, `Y = I · pinv(V)` gives each device's admittance matrix (`solum/linear.py`). `Simulator.linearise` does it (cached).
- **Why not per-device formulas:** a single-pole op-amp was 0.62 dB off on the Rat, and the hybrid-π BJT missed Gummel-Poon terms. Measuring is exact for any model ngspice has, with no device maths in JS. Parity: ≤ 1e-5 dB on every starter and core block (`tests/parity/`).
- **The cost:** a slider that moves a semiconductor's operating point is solved at the old operating point until ngspice re-runs on release (D-081).
- **Slider steps carry element values** (`part_elements`: a pot's two halves after its taper, a resistor's value), so the browser never parses `4k7` or applies a taper. Value sliders step through E12 (pots and trimmers through 1, 2, 2.5, 5 per decade), value/10 to ×10. Rotation: 101 steps; switches: their positions.
- **Measures come from ngspice** (`measures` module, one owner); greyed (`stale`) while the live curve is ahead.
- **Source and load are jig parts** (`JIGRS`, `JIGLOAD`).
*Alternatives:* per-device formulas in JS; ngspice on every slider step (too slow while dragging); a precomputed curve per step (sliders interact).

**D-080 — The Fender TMB is checked against Yeh & Smith's transfer function** (2026-10-21) `library`
Duncan's Tone Stack Calculator publishes no tables, so there's nothing to cite. `tests/sim/test_tone_stacks.py` transcribes eq. (1) of D. T. Yeh and J. O. Smith, "Discretization of the '59 Fender Bassman Tone Stack", DAFx-06 (https://ccrma.stanford.edu/~dtyeh/papers/yeh06_dafx.pdf), checked by the paper against SPICE. Our TMB block is the paper's circuit with the Middle control at m = 1 and R3 the mid pot's resistance; ours matches within 0.01 dB from 10 Hz to 100 kHz at six knob settings, ideal source, no load. The Big Muff tone block reproduces ElectroSmash's notch (1 kHz, −13.5 dB) unloaded; in the pedal the output stage's ~74K load takes 3 dB more (the starter's `tone-notch` known gap).

**D-081 — No calculator pane: value sliders in the inspector, live curves in the Frequency panel** (2026-10-21) `panes`
A calculator pane was built, tried and dropped: a tone stack is studied by putting it on a sheet with a source and a load, like everything else.
- **Inspector value slider** for a resistor, capacitor, pot, trimmer or the amp input (D-079's steps). Dragging redraws the Frequency curve in the browser at every step (`web/solver.js`). Letting go applies the value as one undo step and re-runs ngspice whatever Auto-run says. Cancel puts it back.
- **Knobs follow live too**: grabbing a pot fetches its live system; the debounced ngspice run comes after.
- **Which curves:** a capacitor's two sides and the output; else the probed net and the output.
- **A pot or trimmer also gets a rotation slider** (0–100 %); both sliders share one history.
- **The curve follows the selection**: with the inspector open, clicking another part or net shows it while the slider still moves the opened part (shows how a bias part moves the stage it biases).
- **Bias parts are approximate while dragging**: the live curve is a guess until the release's ngspice run. The user chose this over re-running ngspice during the drag.
- **A pot's view is its wiper and the output.**
- **Hover readout** on line plots (x value and each series at the cursor); frequency text comes from the server (`freq_text`).
- **"AC invalid" wording** says what is off ("Q4 is switched off: no collector current flows, so it doesn't amplify.").
- **Readings row** under the Frequency curve: gain at 1 kHz, peak, −3 dB corners, the dip, from ngspice's curve (`readings`, `CURVE_MEASURES` in `solum/analysis/measures.py`).
- **API:** `POST /api/live` {circuit, nets, controls, steps} → {system, nets, sliders, valid}.

**D-082 — Unlabelled nets are named after a transistor's or op-amp's pin first** (2026-10-22) `sim`
`connect` names an unlabelled net: a label; else the first BJT, JFET or op-amp pin on it (`ACTIVE_PARTS`, "Q4.B"); else the first pin. Saved files refer to pins ("Q1.D"), which `resolve` still finds. *Alternatives:* labels in the starters only (doesn't help what users draw); role names ("Q4 base", more words, and the pin name is what you type to probe).

**D-083 — Audio renders: a file source into ngspice, pick-level input, NAM calibrated by its metadata, worker processes, WAV only** (2026-10-22) `audio`
- **Offline only.** A render runs when Render is pressed.
- **Into ngspice.** The clip is resampled to 96 kHz and written once as a "time volts" file in `CACHE_DIR/audio/sources/<hash>.txt`; the guitar becomes XSPICE's `filesource` (`Tran.source_file`). On the TS808, 5 s: file source 6.6 s, as fast as a SIN source; an inline PWL 314 s. Output is interpolated onto the 96 kHz grid, DC removed, then taken to 48 kHz (`solum/audio/resample.py`: Kaiser-windowed sinc, ~90 dB stopband, numpy only).
- **Levels.** The clip's peak is scaled to the pick level (soft 0.1 V, medium 0.3 V, hard 1 V, D-038), so render and Scope agree (clip levels: D-096). Volts go to the capture's digital level through its `input_level_dbu` (the .nam spec: dBu of a 1 kHz sine at 0 dBFS peak); without it 12 dBu (`DEFAULT_INPUT_DBU`, a design choice). Nothing is normalised. Above full scale is kept (32-bit float WAV) and said.
- **Cab IRs** are scaled to unit energy, at most 2 s (`MAX_IR_SECONDS`).
- **NAM** reads config v0.5 and v0.7; checked against the official package's output (`tests/fixtures/nam/`). Unsupported architectures are refused in plain English. Other sample rates are resampled around.
- **A/B.** Each render also renders "dry" (the clip straight into the amp and cab at the same level).
- **Jobs.** A pool of worker processes (`spawn`, up to CPUs − 1, max 4), each with its own ngspice: renders run side by side, and a crash fails its job with a plain message and the pool restarts. Progress from ngspice's status callback. Server ~79 MB, a worker ~142 MB.
- **Cache.** Key: `content_hash` over the recording netlist, engine and version, the capture's and IR's bytes and `RENDER_VERSION`. WAVs share `SimCache` with simulation results (`put_bytes` / `get_bytes`). A running render can be joined.
- **Uploads: WAV only, as the request body** (`?name=`). MP3/FLAC would need a new dependency; our RIFF reader takes PCM 8/16/24/32 and float 32/64, mixed to mono. Clips ≤ 10 s, files ≤ 50 MB.
- **Where things live.** Built-ins in `library/audio/` with `sources.yaml` (none ship, D-272); uploads in `DATA_DIR/audio/{clips,captures,irs}/`.
*Alternatives:* inline PWL (too slow); real-time playback (non-goal); normalising (hides the pedal's level); MP3/FLAC (not worth a dependency yet).

**D-084 — NAM: SlimmableContainer captures play their largest submodel** (2026-10-22) `audio`
Such a file holds several WaveNets of different sizes (`config.submodels`, each with a `max_value`); `load_nam` takes the largest, with the container's metadata and sample rate. Also supported: per-layer kernel sizes, parameterised activations (LeakyReLU, LeakyHardtanh, Softsign, Hardtanh, besides Tanh/ReLU/Sigmoid), and a head convolution wider than 1 tap. Still refused with a plain message: gating, FiLM, grouping, bottlenecks, head 1x1, slimmable layers, a top-level output head, LSTM. Checked: `tests/fixtures/nam/slimmable-random.*` (random weights, run by the official package) within 1e-5 relative.

**D-085 — Amp input and output trims, and an "into the amp" meter** (2026-10-22) `audio`
A capture's gain, EQ and master are baked in, so only two honest trims: **Amp input** (dB into the capture, as the NAM plugin's Input; changes how hard the amp distorts) and **Amp output** (dB after amp and cab; loudness only). Both −40 to +20 dB (`TRIM_DB`), part of the render key. No fake post-amp EQ or gain. Every render records `amp_in` (peak into the capture after the trim, 1 = its full scale), shown for the take and for the guitar alone, with a warning above 0 dBFS. A render's stats are cached next to its WAV (`jobs.stats_key`). The over-full-scale message says whether the capture or the circuit sets the level.

**D-086 — How driven the amp is: compression against a quiet copy** (2026-10-22) `audio`
The capture is run a second time on the same input 60 dB quieter (`PROBE_DB`), where it is clean, and output levels are compared (RMS, DC removed). `compression_db` is how many dB quieter the real output is than a clean amp's would be; 0 = clean. One more NAM pass. Checked: the same figure with the copy 60 or 80 dB down; a unit test with a hand-built hard clipper matches the sine's computed loss. Bands are a judgement call: under 1 dB clean, under 6 breaking up, under 15 driven, else saturated. The trims are sliders (1 dB steps, double-click for 0); the meter says when its levels are after a non-zero input trim.

**D-087 — No WASM fallback; native ngspice only** (2026-10-22) `project`
Solum Builder runs from the Docker image (native ngspice always present) or from source with libngspice installed. `engine_from_settings` starts native ngspice directly; a missing libngspice gives `EngineUnavailable`'s plain message. An old `.env` setting `NGSPICE` is ignored. If a fallback is ever wanted: eecircuit-engine (ngspice built with Emscripten) in a Web Worker; no WASI build of ngspice exists.

**D-088 — An out-of-date take is marked, worked out in the page** (2026-10-22) `panes`
Each render records what it was made from (`renderSources`); the Audio panel re-checks on every edit, knob turn and change to its controls, and says what changed ("Out of date: the knobs and pick level changed since this take."), with Render ringed. Only the latest pedal take is checked. No server call: the circuit counts by what it sounds like (parts without `pos`/`rot`, each pin's net, `power`, `probes`), so moving parts or re-routing keeps a take current. Knob and switch positions are listed as "knobs".
*Alternatives:* asking the server for the render key on every change; comparing the whole circuit JSON (tidying the drawing would mark a take out of date).

**D-089 — Find part: Edit → Find part…, Ctrl+F** (2026-10-22) `editor`
Type a ref in any case or spacing ("r 12"): the part is selected and probed, the view moves only if it's off screen or near an edge (`revealPoint`), and a ring fades over 1.6 s (none with reduced motion). An unknown ref says so. Ctrl+F replaces the browser's find on the editor page, except when a form field has the focus.

**D-090 — No simulator badge in the header** (2026-10-22) `look`
The header has no "Simulator ready" badge: it only said whether libngspice loaded at start. A missing simulator is explained where it matters: every run answers with its plain message (503). `/api/health` stays for scripts.

**D-091 — No custom power mode: V+ and V- are always the Power menu's; DC sources drive their own nets; text blocks; schema v6** (2026-10-22) `power`
- **Rails are always ideal sources** and every DC source is always in the netlist; `power.mode` is gone. A weak supply is V+ → resistor → its own net; a second supply is a DC source on a net of its own.
- **A DC source on V+ or V-** is the topology rule `dc-source-on-supply` (error, stops the simulation): two ideal sources on one net only give a singular matrix.
- **Migration v5→v6** (`migrations._v5_to_v6`): `mode` dropped; in a `custom` file, a DC source driving V+ (or V-) from GND becomes the rail's voltage. Fixtures `schema-v5-own-supply.json` and `schema-v5-series.json` test it.
- **Text blocks** (Misc group, Text tile, hotkey X): `texts: [{title, text, pos}]` (title up to 100 characters, bold; text up to 2000; at least one), in the view as `texts`, never part of the circuit. Placed first, written second; double-click edits; emptying both removes it; selection, copy/paste and Save as block carry it. Routed wires don't avoid text blocks.

**D-092 — Ctrl+click adds or removes one item from the selection** (2026-10-22) `editor`
Ctrl+click (Cmd+click on a Mac) or Shift+click puts one part, wire, label or text block in the selection or takes it out, whatever made the selection. Ctrl+Shift+drag adds a box; a plain Shift+drag replaces. Set logic is pure (`blocks.toggleItems`, `blocks.addItems`); the canvas reports the item under the pointer (`Schematic.itemAt`).

**D-093 — Charge pumps, the Power menu, current draw, power rules** (2026-10-22) `power`
- **The part.** `chargepump` (schema v7): `model` (a chip), `mode` `doubler` | `inverter`, `boost`, `diode` (the doubler's two diodes, default 1N5817). Pins `in`, `out`, `gnd`; its output is a supply net (`rail_nets`). The flying capacitor is inside the part; the reservoir is drawn.
- **The chips are data.** `library/models/chargepump/<ID>.json`, kind `behavioural`: `f_pump`, `f_pump_boost`, `r_out`, `v_drop`, `i_q`, `i_q_boost`, each sourced in `param_sources`; `vs_max` in ratings. TC1044S (Microchip DS21348A), ICL7660 (Renesas FN3072), LT1054 (TI SLVS033G); MAX1044 added later (D-244). The 7660 family pumps at half the oscillator (a TC1044S whines at 5 kHz, 22.5 kHz with boost); the LT1054 at 25 kHz.
- **The model** (`netlist._chargepump`, one owner): a current into the output (through two real diodes for the doubler) of `g(t) · (target − Vout) / r_out`, target `2·Vin − v_drop` or `−Vin + v_drop`, `g(t) = 1 + tanh(8·sin(2π f_pump t))`. At t = 0, `g` is 1, so `.op`, `.ac` and the transient's start are the pump's steady state, and the live solver measures it like a transistor. The input draws the output current times the ratio plus `i_q`. Checked against a switch-level reference of the datasheet's doubler: ripple 88 vs 94 mV at 5 kHz, 22 vs 21 mV at 22.5 kHz (the ICL7660 sheet's formula gives 94 and 21).
- **Time steps.** At most 1/(20 f_pump) per step (`PUMP_STEPS`). Renders with a pump are much slower.
- **Power menu:** one dropdown, 9, 12, 18 V, ±9, ±12, ±15 V (a V−-only circuit gets −9, −12, −18 V), the circuit's own supply first when it's none of these, and Custom… (polarity and voltage per side, and compare supply voltages). A pedal's own 18 V or −9 V comes from the pump parts. A rail dropped while in use goes to the rail left only when that one isn't in use. (What the dropdown, DC jack and DC source each mean: D-143.)
- **Current draw**: `OpResult.supply` beside the menu after a run, an estimate (op-amp macromodels differ in their supply current).
- **Rules:** `pump-in-audio-band` (warning, pump below 20 kHz), `pump-no-reservoir` (error, no ≥ 1 µF from its output to ground), `supply-no-bulk` (warning, an IC's supply without such a capacitor; blocks skipped), `pump-supply-over-max` (error).
- **Acceptance** (`tests/acceptance/test_pump_whine.py`): the JFET stage on the doubler's output through the real render path; boost off, a 5 kHz tone audible; boost on, nothing but the note's harmonics above −110 dB in 100 Hz–20 kHz. Thresholds are design choices.

**D-094 — Charge pumps without a chip: op-amp oscillator blocks** (2026-10-22) `power`
- An op-amp square-wave oscillator (Schmitt trigger with an RC, about 22 kHz) drives the flying capacitor and two Schottky diodes: `charge-pump-doubler-opamp-v1` (14.6 V from 9 V at 1 mA) and `charge-pump-inverter-opamp-v1` (−5.7 V), tagged "no chip"; the chip blocks are `…-chip-v1`. Values are ordinary starting values checked in simulation, not a published circuit, and each block says so in a warning text block and its description.
- **DC doesn't see a free-running oscillator**: the operating point is the oscillator balanced and still, so DC, AC and current draw show the doubler near V+ and the inverter near 0 V; only Scope and renders show the pumping. Each description says so.
- **Transistor oscillator: tried, not shipped.** The textbook astable locks up with both transistors on; a self-starting version glitches at the usual step (trapezoidal ringing), and the fixes (`method=gear`, `trtol=1`) would change every simulation.
- 2N3904 and 2N3906 added (now our own fits, D-163).
- `tests/jig.py`'s `jig(…, supply_load=)` loads a power block for transient checks.

**D-095 — Editor layout: header, starters under File, reorderable panes, Tools and Help menus, right-click menu** (2026-10-22) `editor`
- **Header**, left to right: logo, File, Edit, Blocks, View, Tools, Help, the circuit's name and badges, then Power (with the current draw), Run and Auto-run.
- **Starters are File → New from starter ▸** (a starter replaces the sheet; a block drops into it). Menus have submenus (`menus.js`; `openMenu(x, y, items)` opens one anywhere).
- **Panes reorder** (`web/panes.js`): drag a pane's grip or focus it and press ↑/↓; the order is kept per browser (`solum.panes`). View → Reset pane order restores it.
- **Capacitor kinds explained** (`library/guides/capacitors.yaml`, `solum/guides.py`, `/api/guides/capacitors`): one entry per schema kind (a test keeps them in step); the same text feeds the Kind dropdown's hints, Help → Choosing capacitors, and rule `cap-kind-signal-path` (info: a general-purpose ceramic or a tantalum on a signal net; the fix suggests by value).
- **Help menu**: Choosing capacitors, Documentation and Formulas (D-290), Hot keys (D-302), About. Help and Tools pages open in a `sheet`.
- **Tools menu**: Unit converter (with capacitor codes both ways: `223` ↔ 22 nF) and Resistor colour code (4 or 5 bands both ways, whether the value is standard, the E24 and E96 values either side). All reading and formatting is the server's (`solum/markings.py` over `solum/units.py`): the pages lay out `/api/tools/*` answers. E96 is in `E_SERIES`. Band colours are theme tokens (`--band-*`).
- **Right-click menu** on the canvas: the clicked thing is selected first (a selection stays); its own items (Edit, Rotate, Delete, Copy), Paste (follows the pointer until a click drops it, as Ctrl+V), and the header's menus as submenus built from the same item lists (`MENUS`). Nothing while placing or drawing a wire.

- **Drag a wire**: a selected wire drags (via `moveItems` → `relay`) with its ends re-laid to what they joined; pressing on an unselected wire still starts a new wire. A drag of wires alone must keep every connection (`sameConnections` on the server's new view); otherwise nothing changes and the hint says so (refined in D-293).
- **A moved or pasted selection stays whole**: after a move or paste, wires and labels are found again by where they went (`itemsAfterMove`, `itemsAt`) and stay selected.
- **Any other click lets go of the selection**: drawing a wire, dragging a wire end or something outside the selection drops it; only dragging the selection keeps it.
- **Resistor chart in Help** (reference in Help, calculators in Tools): Help → Resistor colour code and values, one row per colour with all twelve multipliers and the IEC 60062 tolerance letters, worked examples, and the R/k/M notation. Data from the server (`tables()`).
- **Converter examples follow the quantity** (`QUANTITIES` in `solum/markings.py`; a test checks every example reads).
- **One run per netlist at a time**: a request for a netlist already running waits for its result (`CachedEngine`).
- **No ghosts while dragging**: re-laid wires are hidden at their old place; the live ghost shows where they go.
- **DC order**: supplies, then the guitar's net ("from guitar") and the amp's ("to amp"), then the rest: DC at either end causes scratchy pots and pops.
- **Long panes scroll**: Problems past about six rows; DC (shut at start) past about 200 px.
- **A bent wire is one wire**: a click selects the whole run (`wireRun`: pieces joined end to end up to a pin, label, branch or T); Delete, drag and the right-click menu act on it; Ctrl+click still adds or removes one piece.

**D-096 — Audio and input: a timed-out render says why, the guitar input's pickups and loading, the Audio panel as a signal chain** (2026-10-23) `audio`
- **A render that times out says why.** Limit: 30 s per second of clip plus 30 s (`recording_limit`). `SimTimeout` carries the limit; the message says how far it got, how long the whole clip would take at that pace, the likely cause (a charge-pump chip named by its ref, or an oscillator or extreme value) and what to do.
- **The guitar input is the guitar plugged into this circuit.** "No pickup (buffered)" (`source: ideal`) is a stiff source. A pickup comes from `library/guides/pickups.yaml`: five measured pickups (UIUC Physics 406, one measured unit each: R and L as measured, C from the measured unloaded resonance as 1/((2πf)²L), checked by a unit test), with the guitar's volume pot (250k single coils, 500k humbuckers and P-90s; cited) and the cable at 100 pF/m (cited). "Your own values" keeps R, L, C editable. Netlist: EMF → coil R → L → coil node (coil C) → volume pot (through the one pot model) → cable C → the circuit. The volume is a knob like any pot. Schema v8. The inspector's form has `fills` and `showIf` (`linkFields`). (Pickups by peak and Q: Later.)
- **Renders take the DI's pickup back out first.** A DI clip already carries its pickup's sound; with a pickup set, the render divides the clip (FFT at 96 kHz) by the same guitar into a 1M DI input (`di_reference`, `di_response`), boost held to 24 dB with a 5 ms fade-in, then plays it through the circuit's pickup. A high-Z input gives the clip as recorded (within 0.1 dB, sim-tested); a fuzz gives only what its loading changes. One pickup setting, on the circuit, serves both jobs: set it to the guitar the clip was recorded with.
- **The pedal's output is cached** (`pedal_key`): changing amp, cab or amp input re-renders in about a second.
- **The Audio panel is a signal chain**: Guitar ▸ Pedal ▸ Amp ▸ Cab chips, each with a summary, one drawer open at a time. The Pedal drawer opens the guitar input in the inspector (one place to set it). Below: Render, the takes, the player, Loop, Download. No Output trim (the player's volume does that); the amp Input trim stays.
- **Each take carries its spectrum**: 1/6-octave bands, 20 Hz–20 kHz (`band_levels`, Welch with Hann windows), of the pedal's output (dBV), the take as heard (dBFS) and the DI colour (dB), at `GET /api/render/spectrum/{key}`. Two views: **Pedal output** and **What you hear**, with ticks for Dry, Pedal and Snapshot. **Pedal (no clipping)**: the dry clip's spectrum plus the output's frequency curve, less the DI colour (the clip through a clean version of the circuit; follows the knobs). It stays the clean prediction; when the probe's last scope run isn't clean, a note says where the pedal clips (`clipText`). A **live area** shows the player's sound.
- **The live area is worked out in the browser** (`web/bands.js`): the second exception to "the frontend doesn't repeat backend logic", after D-012, because it keeps up with playback. It reads the player's samples (an analyser, 8192 samples), works out the same bands, and `tests/parity/test_bands.py` holds it to `band_levels` within 0.01 dB. It's drawn as a faint area behind the lines (`--plot-live`), ~30 redraws a second; level axes are fixed per view; bands narrower than the resolution take a level between their neighbours (`fillEmptyBands`); browsers apply the player's volume before Web Audio, so the area is lifted back by it (`atFullVolume`).
- **Compare at most 5 values at once** (try several values, supply compare, render sweep): `SWEEP_MAX` in `solum/probe.py`, copied as `COMPARE_MAX` in `web/series.js` for the page's messages.
- **Every starter's gain knob raises the gain clockwise** (`tests/sim/test_starter_knobs.py`), after the Fuzz Face's Fuzz pot was found wired end for end.
- **Takes:** Dry, Pedal and one kept Snapshot (Keep); a slot holding the same take as another says so (`sameTakeText`). A render sweep's takes are buttons under them on the one player (positions default 5, 25, 50, 75, 100; marked when the circuit changed since); a new sweep replaces the last. Takes are preloaded so A/B switches with no wait.
- **Download all (.zip)**: every take once, named `<circuit> <take>.wav`, with the circuit each came from (`.json`) and `takes.txt` saying what each was made from, recorded when Render was pressed. The server keeps no record of takes, so it zips what the page sends (`POST /api/render/zip`, stdlib `zipfile`).
- **No Audio pane keys** (tried, not useful). Enter on a focused button presses it.
- **The Audio panel remembers its settings** per browser (`solum.audio`) and asks whether the take is already cached (`cached_only` on `POST /api/render` and `/api/render/sweep`: never starts a render, answers null for what isn't cached). Nothing renders by itself.
- **The blank sheet's guitar and amp start ±300 apart.**
- **Opening another circuit stops the player**; a take found for the new circuit loads but waits for Play.
- The Fuzz Face's volume clean-up all happens in the top quarter of the guitar's volume knob (its input is a few kΩ), so a sweep should look there.

**D-097 — Frequency tools: layers on the one Frequency plot, measures on the server, nudged curves in the browser** (2026-10-23) `panes`
- **Layers, not a second graph.** A Layers menu on the Frequency panel turns on Knees, Peaks and dips, Knob ranges and Part influence (remembered per browser; the large view keeps its own set, all on).
- **Every measure has one owner, on the server** (`solum/analysis/measures.py`): knees are `corner_3db` (`knees`); peaks and dips are interior extrema at least 1 dB prominent, refined by a parabola on log frequency (`extrema`, also used by `peak`); `curve_shape` says whether the curve is a simple low-pass, high-pass or one hump (a knee is the band's corner) or "shaped" (knees labelled "−3 dB below peak"). Curve comparisons in `solum/analysis/compare.py`. numpy only.
- **Live curves are measured live**: while a slider or knob moves, the browser sends the live curve to `POST /api/curve` (one request at a time, newest next) and gets features and readings back. *Rejected:* porting the measures to JS (a localhost round trip is fast enough, and keeps one owner).
- **Knob ranges come from ngspice**: each knob at 0 and 100 % through `.ac` (`knob_ranges`, `POST /api/knobs`, cached), so a pot that also moves a bias is right. The band is where the change is at least half its largest (`act_band`); shelves read "below"/"above". The swing is given from where the knob is now. Checked against Yeh & Smith's TMB: band edges within a third of an octave.
- **Part influence uses the in-browser solver**: the server sends each R, C, pot and trimmer's element values at +10 % (`nudges`, via `part_elements`), the browser solves each nudged curve (`nudgedCurves`), and `POST /api/influence` ranks them and says what moved (a knee or peak/dip, else the gain). Small effects are hidden. A resistor with over 10 mV DC across it is marked "sets bias" (the live solver holds bias fixed, D-079). Parity: parts that carry no DC match a full ngspice run within 0.1 dB on the starters.
- **Rows** light the part on the schematic (`Schematic.highlight`) and shade its band; a click on the plot ranks at that frequency. (Changing values from here: D-102.)
- **Clip lines on the Audio spectrum** (`clipLevels`, `clipLines`), behind a Clip levels box, off by default.
*Alternatives:* a second "influence" graph; influence through ngspice (one `.ac` per part, ~1 s on the Big Muff, and includes bias shifts, which is the sweep's job).

**D-098 — The Fuzz Face's low input impedance at low Fuzz is the feedback, not a gap** (2026-10-23) `library`
ElectroSmash gives 5.2K–8.4K "in the simulation" with no setting or method (archived page, read 2026-10-23). Ours: 8.0k at full Fuzz (Zin ≈ Q1's rπ, the page's upper figure and own estimate) and 0.55k at Fuzz 0, where R4 (100k) feeds the input back: Zin ≈ R4/(1 + A), A ≈ 170 (0.58k by hand), a Miller effect (`tests/sim/test_starter_knobs.py`). The page's lower figure is left unexplained, not used as a reference.

**D-099 — Edit curve: drag a knee or peak to change the part that sets it** (2026-10-24) `panes`
Pro EQ-style handles, in the large view only (so a drag never fights the plot click that ranks influence).
- **A session: Keep or Discard.** While editing, the buttons are **Discard changes** and **Keep changes** (just **Done** until something changed), and the column lists what changed ("Changed: C5 220n → 330n"). Each drag is applied and re-run on release, so the curve is real ngspice. **Keep** makes the session one undo step; **Discard** puts back the circuit and its Not saved state, with no undo step (`editSession` in `app.js`, `History.mark/squash/rollback`). Esc discards. Collapse is disabled while values have changed. Opening another circuit ends it (`backToEditor`).
- **Handles go on the curve's shape, not on parts**: a dot per knee of a simple curve, per peak and per dip (at most 6); dots under 1/6 octave apart share one. "−3 dB below peak" points get none.
- **Which part a handle moves** (`compare.handles`, server): each part's `exponent` (d log f / d log value, from its +10 % nudge), kept when it moves the handle by at least `MOVES` of the nudge; ranked by how far, then by how little it does besides. Knobs (the Knob ranges layer's) and bias parts (the live solver can't show them) are left out. Dots get different parts where another moves them nearly as much. The user can pick another in the handle's row.
- **A drag becomes a value** by `value = known × (target / f_known)^(1/exponent)`, snapped to the part's slider steps; each live curve measured by `/api/curve` gives a new known point (at most three corrections per move). Slider steps carry `si` (the value as a number) so the page never parses `47n`.
*Alternatives:* an asymptotic view (on interacting stages corners don't belong to single parts); handing over to the next part at the end of a range (the drag stops and says so: never changes a part silently).

**D-100 — Edit curve up/down: two parts change together to move a peak's or dip's level** (2026-10-24) `panes`
- **One part alone almost never does it** (every part nudged through ngspice): on tone stacks each part moves the dip sideways as much as up or down; elsewhere the level-only parts are gains or bias resistors.
- **Two parts in the ratio that cancels their sideways pulls**: with exponents e₁, e₂ and slopes s₁, s₂ (dB / d log value), log values change by weights ∝ (e₂, −e₁), so the frequency holds to first order and the level moves. Checked through ngspice (TS808 C3 ↑ C5 ↓ ×1.5: +2.5 dB at the same frequency). Same nudged curves as influence: no new simulations.
- **Ranking** (`compare.level_moves`): least **spill** first (how much the move changes the curve an octave away; ≥ 0.9 is shown as "whole curve", it acts like gain), then fastest; none slower than `LEVEL_MIN`; 4 per handle. Knobs and bias parts left out (`avoid`), for sideways moves too. Knees stay sideways (a knee's level is 3 dB under the top by definition).
- **Shift picks the way**: plain drag sideways, Shift+drag up/down (counted at the grab); holding Shift relabels the dots, the cursor shows ↔ / ↕. A drag moves the dot by the pointer's movement since the grab (`dragTarget`). Values step from the last measured point (`seekLevel`), snapped, corrected with a measured secant slope (`measuredSlope`); the move also solves for holding the frequency (`hold`). If the level goes the wrong way the drag holds at the last good step and says so. Each row has "Drag ↔" and "Shift-drag ↕" menus; both parts' sliders move together as one edit (`slideTogether`).
- **The level axis holds still while editing** (`heldRange`).
- **The curve as it was**: the curve at Edit's start is drawn faint with rings where each handle was (`startDots`, `--plot-before`); rows say where their handle was.
- **Every handle keeps its dot**: a handle no part moves shows an unlabelled faint dot (`HandleMark.idle`), and a drag says why. Two handles sharing a dot draw a double ring labelled with both parts. A handle the curve has lost keeps its row, greyed, with the reason (`lostReason`).
- **A changed part stays in its menu** ("· changed", `rowParts`); each Changed line has ↺ to put that part back (one undo step).
- On drives and fuzzes, raising a peak before the clipping means more gain into it; the edit section says so.
*Alternatives:* one part per level (mostly a gain control); a free diagonal drag (later).

**D-101 — History: the undo steps in a header pane; Edit curve as a fenced session** (2026-10-24) `panes`
- **One history, one place.** A **History** button at the header's right opens a scrolling pane: the undo steps, newest first, the current lit, undone ones dimmed until a new change drops them. A click goes to that step. Edit → History opens it too. Steps come from the undo stack (`History.rows()`); the pane is `web/history-pane.js`.
- **Edit curve fences the stack** (`History.begin()`): undo stops at where it began and redo at its end; older steps show greyed under "Before Edit curve" until Keep (its steps become one) or Discard (forgotten).
- **Changes from anywhere join the session** and say so: each step records its `source`; outside steps are tagged "outside Edit curve", structural ones listed under Changed and named in Keep's label. While editing, the History button and the schematic wear the accent outline.
- **Changed together**: a part changed in the same step as others gets a dot; hovering names and lights them (`changeLinks`, `partnerText`). ↺ puts back one part; a whole step is Ctrl+Z or History.
*Alternatives:* a History panel in the right column; blocking structural edits during Edit curve (allowed and shown instead).

**D-102 — Frequency plot 10 Hz – 30 kHz, one level axis, one way of editing the curve** (2026-10-25) `panes`
- **Frequency plot 10 Hz – 30 kHz** (FabFilter Pro-Q's range; takes in a 6-string bass's low B at 30.9 Hz), shaded outside 20 Hz – 20 kHz (`--plot-outside`). ngspice still sweeps 10 Hz – 100 kHz (readings and acceptance files unchanged); the band is `PLOT_BAND` in `measures.py`, and `features`, `knob_range` and `influence` cut their curves to it (`plotted`).
- **The level axis fits 20 Hz – 20 kHz** with 10 dB of room on 5 dB lines (`levelAxis`, `heldRange`), the same in and out of Edit curve; a live plot only widens it.
- **Knob shading on hover** in the Knobs panel, with the layer off too.
- **One way of editing the curve**: values change from the plot only inside Edit curve. Part influence outside it is for reading; a **double-click** on a row opens Edit curve on that part. Edit curve has **By curve** (the dots) and **By part** (the influence list with a slider per part), both feeding the one session. The schematic, part form and knobs stay immediate.
- **Audio spectrum** floor −80, the same 10 Hz – 30 kHz span; bands stop at Nyquist, bands narrower than the bin spacing take their share of the bins either side (on the server and in `bands.js`), each segment's mean taken off first.
- **One large view for any pane** (`setLargeView` in `panels.js`, `.large-view`): shrunk by its title to a bar the canvas's width, ringed in the accent; bars stack at the bottom; one open at a time; Esc acts on the open one; a bar's Collapse puts it back in the panel (locked while Edit curve has changes, `lockLargeView`); the Frequency bar wears an "Editing" chip (`largeViewChip`); a view redraws once laid out full width (`onShow`). Conventions in DESIGN.md.
*Alternatives:* 20 Hz – 20 kHz with a zoom (maybe later); sliders on the small graph (two ways to change a value).

**D-103 — Knobs are played, not saved: the circuit holds their opening positions** (2026-10-25) `schema` `panes`
- **The circuit's `rotation` / `position` is where each knob opens** (50 % for a new pot). It's set in the part form or with **Use as opening positions** under the knobs (one edit).
- **Turning a knob only moves `state.controls`**: no Not saved, no undo step. Everything that simulates or renders takes `played()` (`withControls`: the same object until the circuit or a knob changes, so caches hold). Knob turns never count as curve edits.
- **Across edits a knob stays where it was turned**, unless its opening position changed (`keptControls`); opening a circuit starts every knob at its opening position.
*Alternatives:* knob turns mark Not saved (playing a starter would ask to save on leaving); saving positions silently (saved only by chance).

**D-104 — The large spectrum carries the whole player** (2026-10-25) `panes`
- **One player, moved, not copied** (`placePlayer`): while the large spectrum is open the player and the whole chain sit in its right column; shrunk or collapsed, it's back in the Audio panel. Moving an `<audio>` within the page keeps it playing. Two copies were ruled out (two Web Audio graphs, every control's state twice).
- **What you hear** is the spectrum's default view.
- **Every curve is placed by frequency** on the full bands (`onBands`), so takes rendered with other band sets line up; a band a take doesn't have is left empty.
- **Expected is named Pedal (no clipping)**: the dry clip through the small-signal curve, what the pedal would give if it never clipped; starts unticked. (Checked: the TS808's gap goes to 0.0 ±0.1 dB with D1/D2 removed, so it's the pedal's own clipping.)
- **The top band reaches past Nyquist**: a band is left off only when its centre is past Nyquist; one straddling it is read from its part below. Playback runs at 48 kHz (`AudioContext({sampleRate: 48000})`, falling back to the browser's rate). `RENDER_VERSION` bumps make old takes render again once.

**D-105 — The Pedal line reaches 30 kHz; a hatch where nothing can be recorded** (2026-10-25) `panes`
- **Pedal output's Pedal line is read from the 96 kHz simulation** before conversion, so it reaches 30 kHz like the Frequency chart. The pedal output is cached at 96 kHz and converted on each render; `band_levels` takes a segment twice as long at 96 kHz. Lines after the amp read `SILENT_DB` past 24 kHz and aren't drawn.
- **Dry is read at the clip's own rate** (each spectrum carries `pedal_top`); the dry WAV and what's heard stay 48 kHz.
- **Hatched where nothing can be** (`spectrumHatch`): after the amp above 24 kHz (the app's 48 kHz output, not the capture's limit); before the amp above what the dry clip holds.
- Clip and capture rates are shown in their drawers.
- **Large views alike**: Expand / Collapse is the last tool at the far right (`.large-toggle`); explanations beside a large view's plot use the spectrum's note style (DESIGN.md).

**D-106 — Bias & headroom: its own pane, measured against the unclipped level** (2026-10-25) `panes`
- **Its own pane, after Frequency**: headroom is level per stage, not per frequency, and a bias fix moves both. (Stage chain: D-122; fixes: D-119, D-123.)
- **What a stage is** (`solum/stages.py`): each transistor and op-amp section a guitar signal reaches (the rules' signal graph, `graph.quiet_nets`) with an AC gain at 200 Hz at least 1/1000 of the guitar's. Gain stage, buffer (a follower, read at its emitter/source) or op-amp stage. Signal order is the fewest edges from the guitar (`graph.distances`); a clipper comes right after the stage whose output it holds.
- **What a clipper is**: diodes grouped into series chains and then by their two end nets (a pair, 2+2 or 2+1 is one row). Left out: a group touching a supply or DC source's net (polarity, pump diodes) or off the signal path (an indicator). **Kind**: to ground (hard); in feedback when it spans a device's output and input (also through one series part, as the Big Muff's cap); else in series.
- **The unclipped level comes from the row before**: the peak that actually reaches the previous row times the small-signal gain between the two nets at the Scope's 200 Hz (`sim.ac`). No extra simulations: one `.op`, one `.ac` and the Scope transients.
- **Stage headroom** = 20·log10(smaller room / unclipped peak): positive spare, negative over. Room (`stages.device_room`, one owner): a transistor bottoms out 0.3 V (BJT) or Vdsat (JFET) short of its common terminal, a rail limits the other way; an op-amp's output from its datasheet swing (`out_neg_headroom`, `out_pos_headroom`, D-150), else `OPAMP_SWING_MARGIN` = 1.5 V, said as a rule of thumb. A stage whose feedback diodes hold its output is **held**: never "over".
- **Clipper drive** = 20·log10(unclipped peak / what gets through); 1 dB or more is clipping. **Clamp**: the peaks across the diodes at a hard pick, not at the node (the TS808's 1.37 V at the op-amp output is ±0.45 V across D1/D2). Harmonics: even or odd lead when one is 3 dB above the other.
- **Bias position**: room down over total room; 0.4–0.6 is centred, else high or low and which side clips first. A saturated / cut-off / railed stage shows the Frequency warning's message and "—".
- **Colours**: spare green, under 6 dB amber, over and a clipper's drive in the accent; red is kept for a bias problem (clipping isn't an error).
- The pane measures only when the circuit changes and only while open.
*Alternatives:* a diode-free re-run per clipper (an extra transient per pick per clipper; the AC curve gives the same for free); THD alone (says nothing about room left); a fixed 0.6 V clamp.

**D-107 — One large-view helper for every pane** (2026-10-25) `panes`
`largeView(el, {id, name, what, onChange, onShow, onEsc, canCollapse})` in `panels.js` is the one way a pane goes large: the Expand / Collapse button (`.large-toggle`), Esc, `body.dataset[name + "Expanded"]`, plot height (`plotHeight(reserved)`: 62 % of the window less what sits around the plot, at least 320 px) and the shrunk bar. One layout: `.large-split` (a main column and a side column of `minmax(340px, 32%)`), `.large-side`, `.large-notes`; a large view never scrolls. Collapse is held only while Edit curve has changes (`lock(reason)`).

**D-108 — Bias & headroom's large view: a level diagram, and a level in → out curve on request** (2026-10-25) `panes`
- **Level diagram**, from the rows already measured: x is the signal path, y the peak in dBV (0 dBV = 1 V peak). Per pick: what it reaches (solid) and what it would unclipped (dashed). Each row's **limit** is a dot (a stage's smaller room, a clipper to ground's clamp); none for feedback or series clippers (their clamp is across the diodes). Dots, not a line: one stage's limit has nothing to do with the next's. The server gives `limit` and `picks`; the page converts volts to dBV.
- **Level in → out, on request**: each stage's peak against the guitar's, in dBV; a flattening line is a stage clipping. 12 guitar levels from 3 mV to 3 V (`SWEEP_LEVELS`). A clipper and the stage it holds share a line.
- **One request per level** (`POST /api/stages/level`, `stage_levels`), for progress and a curve that fills as it goes; each is one `.op`/`.ac` (cached) and one transient at that amplitude (`Simulator.tran` takes a peak in volts, up to `MAX_AMPLITUDE` = 10 V); the page keeps the last 8 curves. `stage_levels` and `stages_view` find the path the same way (`_signal_path`).
*Alternatives:* one request for the whole sweep (needs a job and polling); limits and dB computed in the page (the server owns measures); a joined limit line (reads as a level the signal follows).

**D-109 — Explanations behind an ⓘ; Bias & headroom rows in two lines** (2026-10-25) `panes` `look`
- **Every pane's explanations are behind an ⓘ** (`paneInfo(el, title, content)` in `panels.js`) after the pane's name in its title bar, panel and large view alike (hidden on a shrunk bar). A click opens a pop-up, one at a time, closed by a click outside or Esc; on a scroll it follows its button. Its content is built on each opening, so it describes what's on screen. Readings, not explanations, stay in the pane (where the pedal clips, a problem's why and fix, status lines). Panes with nothing to explain have no ⓘ.
- **Bias & headroom rows in two lines**: name, role and net, then the bias bar and one word (centred, sits high, sits low; an asterisk for the op-amp rule of thumb) or a clipper's clamp (`clamp.short`); then the three picks. The sentences are the row's tooltip. Hovering a row lights its place on the chart and its parts on the schematic.

**D-110 — Expand on the title bar; the whole Audio pane is one large view** (2026-10-25) `panes`
- **Expand sits on a pane's title bar** (right, before the grip); a shut pane goes large in one click. Large, it's Collapse, last in the pane's tools.
- **The Audio pane is one large view**: spectrum on the left, the whole player on the right (`.large-side`); the shared grid places it, nothing moves.
- **Shrunk to its bar, the Audio pane keeps Render (with progress), Play / Pause and Dry / Pedal / Snapshot** (`largeView`'s `bar`, `onShrink`): the same buttons moved onto the bar. Play / Pause drives the `<audio>` element.
*Alternatives:* nothing on the bar (re-render needs the pane reopened); copies of the controls (two sets to keep in step).

**D-111 — The Audio bar stays at the bottom, its controls centred** (2026-10-25) `audio`
The Audio pane's shrunk bar is always the bottom one (`pinBar`); its controls sit in the middle with a rule between Render and Play. Back in the panel, the Spectrum fold is as it was left. The Audio ⓘ is in sections (the chain, then the spectrum view picked).

**D-112 — Small editor and Audio-bar fixes** (2026-10-26) `look`
- The Audio bar's progress sits left of Render, outside the centred group; Play is greyed until a clip is loaded.
- **A wire can end on nothing**: with the wire tool, clicking the last point again ends the wire there. Canvas hints stay one line (cut with "…", the whole text in the tooltip): a wrapping hint resized the canvas.
- A form field's `help` can be a link to a Help page ("Choosing capacitors").
- **An upright two-pin part's value sits under its ref**, on the same side (`placeText`).
- **A part dropped on a wire lands on the line and goes in series** (`dropSpot`; `inSeries`, D-113).
*Alternatives:* turning a part to lie along the wire (a guess; Space turns the ghost); ending a wire with Enter.

**D-113 — A press on anything in a selection moves the selection** (2026-10-26) `editor`
- With several items selected, a drag starting on any of them (a part or its pin, a wire or its end ball, a label, a text block) moves them all (`grabsSelection` in `render.js`). Outside a selection, a pin, label or wire starts a wire and a ball moves its end.
- **Any part placed, moved or turned onto a wire goes in series**: `inSeries` in `edit.js`, after `addPart`, `moveItems` and `rotatePart`, cuts a wire running through two of a part's pins (one of them part-way along it). A jumper drawn pin to pin stays, as does a wire touching one pin.

**D-114 — A net label's text keeps off the wires; a part's probe uses one circuit** (2026-10-26) `editor`
- A label not on a pin puts its text on the first side no wire leaves by: above, below, right, left (`label_sides` in `view.py`, `SIDES`). A label on a pin points away from its part.
- Probing a part sends the part's view request and the run with the same circuit (`refresh` in `app.js`).

**D-115 — Take buttons update wherever they are; button groups' first button stays inside its box** (2026-10-26) `audio`
`showSlots` walks the Audio pane's own button list (the bar's buttons live outside the pane body). `.segmented button` overlaps only at the joins (`margin-left: -1px`, not the first).

**D-116 — Switching between shrunk bars happens in one frame; Play keeps its width** (2026-10-26) `audio`
A click on a large view's title switches in the click itself (`setLargeView` binds it; `shrinkOthers`, `shrunkNow`), not on each `<details>`' later toggle event, so the browser never draws the steps in between. No animation. The bar's Play button holds both words stacked, so it doesn't change width.

**D-117 — Supply symbols turn; schema v9** (2026-10-26) `schema` `editor`
- A label has an optional `rot` (0, 90, 180, 270, clockwise), saved only when not 0. Schema v9 (`_v8_to_v9` changes nothing). Turning never changes the net.
- Only supply symbols turn (ground, V+, V-): Space turns the ghost or a selected one (`rotateLabel`). A plain net label finds its own side (D-114).
- The symbol turns about its point (`drawSupply` in `render.js`, one helper for sheet and ghosts); a rail's name sits beyond its bar, upright (`supplyText`).
*Alternatives:* a `dir` field (a second way to say what `rot` says).

**D-118 — Clipper diodes: 1N34A, BAT46, a red LED; no BAT41** (2026-10-26) `models`
- Models for the clipper swaps, one per kind a builder reaches for (cards and checks since replaced by our own fits, D-160, except the 1N34A). The palette has an LED tile (E).
- **No BAT41** from ST's card: it fails ST's own sheet (now our fit, D-159).
- **The forward voltage is measured at the stated current**: `diode_vf` re-sizes its resistor from the drop it found (three passes).
- On the Rat's pair to ground: 1N34A 0.31 V, BAT46 0.27 V, 1N4148 0.62 V, LED 1.74 V. Germanium and Schottky overlap at these currents, so neither is assumed lower.

**D-119 — Centre: a resistor value that centres a stage's bias, tried in an edit session** (2026-10-26) `panes`
- **The search** (`centre_bias` in `probe.py`, `POST /api/stages/centre`): every resistor with a pin on one of the stage's own nets (not a supply's or ground's) is searched from a tenth to ten times its value (10 Ω to 10 MΩ) by bisection on log value (`bisect` in `bias.py`, shared with the trimmer solver), to where the output sits halfway between its limits (`_room`), then snapped to the nearer E24 neighbour. Each option says where the stage then sits and names any other stage it pushes off centre. Ranked: centred first, then disturbing no other stage, then smallest change (`centring_rank`); at most three; only options that improve on now.
- **In the pane**: a stage that sits high or low (or is saturated) has Centre; **Try** puts one value in and the pane measures again. The first Try opens an **edit session** ("Centre Q4"), the same kind as Edit curve's: Keep makes it one undo step, Discard leaves none. Edits carry `source: "bias"`; `History.begin(name, source)` names the session.
*Alternatives:* every resistor in the circuit (slower; far ones move every stage); a continuous slider (a bias fix wants a standard value); applying the best value at once (Try in a session instead).

**D-120 — One edit session at a time asks first; a Centre option shows its gain change** (2026-10-27) `panes`
- Starting one session while another has changes asks "Keep the changes?" with Discard / Cancel / Keep (`ask`, D-075); a session with nothing changed ends quietly. Each session's owner gives `editSession` its `pending` and `end` (`SessionOwner` in `app.js`).
- Each option says how the stage's own gain changes at 200 Hz (`_tone_gain`), from ngspice AC before and after. The ranking ignores it; it's shown so the user knows the sound changes too.

**D-121 — The result panes remember which are open and how far the list is scrolled** (2026-10-27) `panes`
- Open or shut per pane in `solum.panes.open` (`panes.js`); View → Reset pane order forgets it.
- The pane list's scroll in `solum.panes.scroll` (place and each pane's height). On load each open pane holds its saved height (`--reserve`) until its content is that tall and the list stays hidden until the scroll is set, so there's no jump; the hold ends when panes fill, on user input or after 10 s.
- Panes out as large views stay out, shrunk to their bars (`solum.large`, `restoreLargeViews()`); opening another circuit puts them back.
*Alternatives:* `sessionStorage` (lost in a new tab); restoring the scroll once at load (the list jumps as panes fill).

**D-122 — The Bias & headroom pane is a stage chain, measured at four tones** (2026-10-27) `sim` `panes`
- **The chain**: one block per stage and clipper in signal order (`guitar ─▶ [ Q1 buffer ] ─▶ [ U1 op-amp +38 dB ] ─▶ [ D1 D2 to ground ] ─▶ amp`), each with its role and its kind of clipping: hard (diodes to ground), soft (in feedback), lopsided (an uneven pair, or a stage off centre), the device itself saturating. An active tone stage is named by its knobs. Clicking a block lights its parts (its device plus every part on the device's pins other than supply and ground) and opens a details card.
- **Pots are chips where they act** (`solum.stages.pot_places`): on a block when the pot touches the stage's input pins (op-amp + or −, base or gate, and emitter or source unless a follower) or sits on a passive path from its output back to its input (feedback); else on the arrow after the last row nearer the guitar than the pot's nearest net; else at the end. A chip opens the Knobs pane's own control (`panels.knobControl`). Starters have tests for where each pot lands.
- **Tone stacks and volume pots don't get blocks**: they're passive and nothing on the chain edits them. They're chips because a passive loss between stages sets how hard the next is driven, and a tone control before a clipper changes how it clips. The chain doesn't recognise designs; the numbers are always the whole circuit's from ngspice, never block gains added up.
- **Headroom and drive at four tones** (100 Hz, 200 Hz, 1 kHz, 3 kHz): only a transient is right past the first clipper, and a treble booster in front of a fuzz shows only at high tones. The chain shows each stage's worst case and its tone.
- **Settling** (`Simulator.settling`): a run starts from the no-signal DC; coupling caps charge and clipped stages move their bias, so peaks are measured only once the cycles repeat. The wait is found per circuit in seconds (a fixed count of cycles is the wrong unit), then used at every tone. Search: a hard pick at 100 Hz, windows compared after a wait, twice and four times it, at every net, 50 ms doubling to 400 ms; compared on each net's first eight harmonics with in-window drift removed (peaks jitter, harmonics don't); a second change the same way and not shrinking means still drifting, a shrinking one is summed to estimate what's left (under 1 %); changes both under 0.3 % are steady. Still drifting at 400 ms: marked "still settling". A circuit with its own oscillator (a charge pump) is too slow to search: shortest wait, marked unchecked. Against a 0.6 s settle: TS808 and Rat within 0.4 % at every tone, Big Muff 0.1 %, Fuzz Face 2.5 % at 3 kHz. Tests: clamps with known time constants (`tests/sim/test_simulate.py`) and made-up waves (`tests/unit/test_settling.py`).
- **200 Hz on every change; other tones on Measure** (ngspice is one instance per server behind a lock, so background tones would hold up other runs). Results are cached for the circuit as it stands.
- **The expanded view** shows the chain as a strip over the level diagram's columns (`placeStrip`); the editing lives there (D-123).
*Alternatives:* blocks for tone stacks and volume pots; a linear per-tone estimate from the AC sweep (wrong past the first clipper); a list under the chain.

**D-123 — Bias & headroom's large view: one card at a time; Try changes for every block, Bias to… included** (2026-10-27) `panes`
- **A tone being measured greys the chart and strip** (the last results stay, faded).
- **The card holds one thing**: a block's card is everything about that stage (bias, picks, the knobs on it, its Try changes). A chip on an arrow (a tone stack, a Level) opens a card of its own ("Level — between U1 and Q3: it sets what Q3 gets"), never given to a stage.
- **One strip for both charts**; over the level in → out curve each block carries its line's colour, so the strip is the curve's key.
- **Try changes** (`solum/fixes.py`, one shape for every option: `set`, `undo`, a History `label`, a sentence; the page applies any with `tryPatches`). Endpoints `POST /api/stages/bias` (no target centres), `/gain`, `/clipper`, `/reach`.
  - **Bias:** Centre, and **Bias to…**: drag the mark on the stage's bias bar; options are searched on release (D-119's search aimed at that position, 2–98 % of the room). Each option says where the stage then sits, its room, which side clips first and the hard pick's room before and after, and its gain change. The bar's ends are labelled in volts (`biasScale`).
  - **A trimmer**: one with a bias target already turns itself before every run (`solve_bias`), so the drag changes the target ("R6 trimmer to 62 %"); out of reach, it says what the full turn gives and offers resistors. One without a target offers a turn, then "keep it at this voltage" (saves a target), then fixed resistors; never a new fixed value for a trimmer. Targets are stored to 10 mV (`TARGET_DECIMALS`) with the solved `rotation` kept in the file (where to set the real trimmer before trimming). A targeted trimmer's Rotation is read-only and shows the last run's turn (`op.bias`); clearing the target unlocks it (`lockedWhile`).
  - **Reach**: `bias_reach` measures where the stage sits with each part Bias to… could change at its range ends (a trimmer at 0 and 100 %, resistors at ÷10 and ×10), from where it sits now. The bar hatches what one part can't reach. Under 5 % of the room (`REACH_MIN`) the bar doesn't drag and says why (an op-amp's output follows its + input, held from a reference elsewhere).
  - **Gain**: a slider per part (D-125).
  - **Clipper**: the diode type for the whole group (1N4148, 1N34A, BAT46, red LED) and a lopsided pair, each measured at a hard pick (where it clamps, louder or quieter after); arrangements that add parts: D-124.
- **A clipper's clamp is the voltage across its diodes as it is**, not about its mean (a lopsided pair reads +1.77 / −0.61 V, not ±1.19 V).
- **An arrow shows what the passive parts on it do; a block's gain starts where the signal enters it** (`signal_input`: a base or gate, an op-amp's + input, a clipper's node). The arrow carries the rest, from the row before's net (`_Path.arrow_db`); the two add up. No arrow number without a separate net or for an inverting op-amp stage; under 1 dB isn't shown.
- **Esc shrinks the open large view to its bar; it never collapses one** (every pane). Keep or Discard is asked only on Collapse.
- **Try changes is one edit session over any blocks**, "Bias & headroom" in History. Another option from the same box replaces the one tried. **Keep changes / Discard changes** and **Before** sit in the large view's top bar; Collapse is held while anything changed. Discard restores the chain measured when the session began (nothing re-measured). A **Changed** list with ↺ per part (restoring every field Try can set, `type` included; `curveChanges` with `TRY_FIELDS`). Both charts draw the chain as it was, faint (`--plot-before`).
- **Progress bars** for the searches and the level sweep: with `progress: true` the endpoints stream one JSON line per step, then `{"result"}` or `{"message"}` (`progressing` in `app.py`, `postProgress` in `api.js`); without it, plain JSON. Error handlers share `error_text`. Not a polled job: a search is seconds and belongs to the page that asked.
*Alternatives:* giving an arrow's pot to the next stage (looks like that stage's knob); bias presets or a typed voltage alone (the drag shows the target as it moves).

**D-124 — Clipper arrangements that add parts: placed in the browser, checked and measured on the server** (2026-10-27) `panes`
- **Offered**: **two in series** (each diode doubled), **2 + 1** (lopsided), and for a clipper to ground **a resistor in series** with each diode (1k, 2k2, 4k7: a softer knee). Each is measured like the swaps. In an antiparallel pair only one diode conducts at a time, so a resistor per diode is the same circuit and needs no shared node.
- **Placement is the browser's** (`insertInSeries` in `web/editor/insert.js`), since the router is: the new part goes beside the diode's pin, along its line, its near pin taking the pin's place and the wires re-laid to its far end. Else a clear spot near the pin with a wire back (the tidiest of eight, `untidiness`), else `clearSpot`.
- **Making room** (`makeRoom`): when neither pin has room, the sheet is split like a schematic editor's "insert space": everything past a line across the diode moves out one part's length; crossing wires stretch, pins split across the gap get a straight wire, so every connection is kept by construction. Always said before ("Makes room first: moves C20, C21 and 13 others down.") and after (its own History step, a warning-coloured Changed line, undone by ↺, another option or Discard).
- **The server checks before it measures** (`_arranged_row`): only the added parts are new, every pin joined as before, each added part between the diode's pin and its old net; the room step alone must change no connection. A placement that fails is left out with a note ("make some space around them and try again"), never measured wrongly.
- **In the session** an arrangement carries what placing it added and removed (`editDiff`, `applyDiff` in `web/editor/edit.js`); ↺ on an added part takes out everything that option added.

**D-125 — The gain parts get a slider each, reading what clips first anywhere in the chain** (2026-10-27) `panes`
- **No target**: a gain target means guessing a number without knowing the limits. Find parts ranks the parts on the stage's nets (+10 % each, ngspice AC). A **resistor or pot gets a slider** over its standard values from a tenth to ten times its own (E12, `SLIDER_SERIES`; pots `POT_SERIES`), placed along it by the gain each gives, so the ends read the most and least one part can do. Letting go (or Enter) Tries it in the session. One part at a time per box.
- **What each value says**: its gain change (a pot's as if turned full up), a bias change if any, and **what clips first in the whole chain** with how far at a hard pick and what it was. More gain in one stage often clips the next, so its own room alone would mislead.
- **Marks** (S, M, H) where something starts clipping at each pick: information, not stops.
- **An estimate until let go**: `estimate_chain` walks the chain with the small-signal gain (a DC and an AC run per value), each stage capped at its room, each clipper taking off what it was measured to take off at the three picks (`clipper_knees`, from the pane's transients), carried past them as a clamp. On the starters it clips the same rows at the same picks as the transients. Trying runs the real thing.
- **A slider stops** before a value that saturates a stage at DC or puts its bias within 5 % of a limit (`EDGE`), and says why.
- **A capacitor gets no slider**: at 200 Hz it mostly moves where the curve bends, not the drive. Its **Edit curve** button opens the Frequency large view on its slider (`editPart`).
- Trimmers stay out (they set bias).
*Alternatives:* a target plus reach (still guessing); the stage's own headroom as readout (wrong where the next stage clips first); three transients per value (a minute per slider); capacitors as gain parts.

**D-126 — The cache index keeps one connection open, in WAL mode** (2026-10-27) `sim`
`SimCache` opened a connection per get and put, and every get writes (`last_used`); each commit synced to disk (~10 ms on btrfs), so a search with ~4,000 cache calls took 40–60 s (5 s on tmpfs, where tests run). Now one connection per `SimCache` per process (reopened in a forked worker or if the file was deleted), `journal_mode = WAL`, `synchronous = NORMAL`: the same search takes 4 s. `_evict` reads rows only when over size. The index stays safe to delete (with its `-wal` and `-shm`). *Alternatives:* `synchronous = OFF` (a power cut could corrupt the index); batching writes (more code, same result).

**D-127 — Interface polish** (2026-10-27) `look`
- **The large view's strip is the panel's chain**, framed and centred over both charts; over the level in → out curve each block carries its line's colour as a 3 px shadow (boxes don't move between charts). A line hidden in the curve's legend fades its block (`linePlot`'s `hidden`, `onToggle`).
- **Arrows have heads** (`.arrow-glyph`). "Find diodes" names its button as "Find parts" does. A block's chip toggles its card.
- **A picked stage has its own colour, `--picked` (#D68A4A, copper)**, on its parts, block and card; kept off the error brick (19° of hue away, tested in `test_theme.py`) and the brass highlight. Picked parts are their own layer (`highlight(refs, picked)`), so hovering another block lights over it; the hover wins on the schematic.
- **A bar while a tone is measured**: `POST /api/stages` streams progress (`progress`, as D-123): the small-signal pass, then each pick's transient. `Progress` lives in `solum/probe.py`.
- **The gain sliders' S / M / H marks** are outlined tags over a tick, the bar tinted where each pick clips (`--clip-zone-soft/med/hard`).
- **Searches keep their answers** in the content-hash cache (`searched` in `app.py`), keyed on the request (circuit with its knobs, stage, aim or arrangements), engine and version, the model library (`ModelLibrary.fingerprint`) and `FIXES_VERSION` (bump it when a search's answer changes for the same request).
- **Edit curve's session is "Frequency curve" in History** and the save prompts.
- **Large views shrink rather than collapse**: opening another circuit (`shrinkLargeViews`, from `backToEditor`) or a click on the canvas shrinks them to bars; View → Reset pane order puts them back in the column (asking first if a session has changes, `endSession`).
- **A large view is 560 px tall** (`--large-h`, read by `plotHeight`), anchored above the bars; a window too short for it (under 200 px of canvas left) shrinks it to its bar.
- **A tone is measured when picked**; the tone stays where it was picked until another circuit opens (200 Hz). Measure all stays. The tone row's note says what's left to measure, or the progress.
- **A card's Waveform section** (under the tones, open at first, remembered shut until another circuit, `wavesShut`): the block's waveform at the three picks with Peak +, Peak −, Clipping and THD per pick, from the pane's own transients (`POST /api/stages/waves`, `stage_waves`); one plot element moves between cards so nothing flickers.
- **A part's slider takes a key press at a time**: a step key commits and re-runs, and further steps wait until that run is drawn (`valueSlider`, `slideFields` waits on `ranAgain`); the slider is greyed (`.running`, `aria-busy`), not disabled, so it keeps focus.
- **A trimmer's target in its form.** The node a trimmer holds is found, not picked: the drain or collector of the one transistor it's wired to, whichever pin it touches (stages are biased by their output voltage; the solver bisects on any node). No target for a balance trim between two transistors, a trimmer on no transistor, or a node another trimmer holds. Fields: Target node (read-only), Target in volts (hint: its reach, `POST /api/trimmer/reach`, `bias.target_reach`; Apply refuses a target out of reach, `movedTargets`), Remove target / Add target swapping in place (nothing saved until Apply). While targeted, Rotation is read-only at the solved turn (`showTargetRotation` follows each run); turning the slider after Remove takes the target off. A JFET's drain target is the trimmer's target, shown in both forms. Test circuit: `tests/fixtures/circuits/jfet-source-trim.json`.
- **A number field's problem is said as soon as its box is left**; out-of-range rotations are refused, not clamped.
- **A JFET's Idss and Vp: "the model's / measured"**, never a blank box meaning the model. Measured shows both boxes, starting at the model's values (Idss = BETA·VTO², `GET /api/models/jfets`); hints say how to measure (Idss: gate and source grounded, drain at 9 V through 100 Ω; Vp: gate grounded, 1 MΩ source to ground, read the source). The netlist uses a copy of the card with VTO and BETA from yours.
- **A held node is drawn in its own colour on the DC overlay** (`--sch-held`; hover: "target 9 V, held by TR1 at 61 %"); one not met would read in `--warning` (`OpResult.held`).
- **View → Impedance in and out**: Zin under the guitar and Zout under the amp at 1 kHz; the Probe pane gets an Impedance row at the probed net. ngspice `.ac` at 1 kHz with 1 A AC into the net (`Ac.inject`) and its volts read back; a part left out (`Ac.open`) becomes 1 GΩ to ground so its net keeps a DC path. With a stage saturated it says "saturated". Checked by hand (470k pulldown and 10k to the 1M amp: 320.7k in, 10k out; 10n in series: 15.9k at −90°). TS808 about 458k in and 172 Ω out; Fuzz Face 692 Ω in.
- **ⓘ split**: `infoButton(title, content)` beside `paneInfo`; Try changes has its own ⓘ.
- **A knob or switch in use lights its part** (`inUse` in panels.js, `knobInUse` in app.js); a flipped switch keeps its light and label (`redrawPart`; test circuit `tests/fixtures/circuits/switch-tone.json`).
- **Collapse sits at the far right of a large view's title bar.**

**D-128 — reserved** — not used in v1 (v2 modulation work, not in this repo). `project`

**D-129 — reserved** — not used in v1 (v2 modulation work, not in this repo). `project`

**D-130 — Measured transistors: hFE and leakage; schema v10, v11** (2026-10-28) `schema` `models`
- **"Gain: the model's / measured"** in a transistor's form; Measured starts at the model's BF (`GET /api/models/bjts`, `Model.bjt_spec`), offered for model cards only. The netlist uses a copy of the card with BF from yours (`_Emitter.measured_bjt`). Schema v10: `Bjt.measured = {hfe}`.
- **Leakage** (schema v11, `measured.leakage`, amps) is what the Geofex tester reads with the base open (Iceo); how to measure: D-153, D-193. No model parameter is leakage alone, so it's a hidden current source from collector to base, Icbo = (yours − the model's) ÷ (hFE + 1), which the transistor's gain turns back into your Iceo (`netlist._leak`). A model's own leakage is what its card reads on the simulated tester, kept in its record (`iceo`, re-measured by `tests/sim/test_models.py` with `model_checks.bjt_iceo`); silicon counts as 0. Shown only for germanium models (D-138).
- **Accepted against ElectroSmash's Fuzz Face**: with Q1 and Q2 measured at 85 and 120 (the page's own figures), the collectors match its bias diagram. Q1's hFE sets the bias through the DC loop; Q2's hardly. More leakage pushes Q2.C further negative, the direction builders report.
- No published measured analysis of leakage against a Fuzz Face's bias was found, so that acceptance check is pending. Temperature is left for later.

**D-131 — reserved** — not used in v1 (v2 delay-line work, not in this repo). `project`

**D-132 — v1 scope: real schematics; modulation is v2** (2026-10-28) `project`
v1 represents real schematics only: an LFO as an ideal source, or a delay without real BBD and clock parts, would not be, so modulation is v2 (PHASES, not in this repo). A measured part's form says what the measurement is for: "the model's (typical) / your unit's (measured)", with the datasheet's range from the model's validation records (`Model.datasheet_range`, `range` on `/api/models/jfets` and `/bjts`), or that the range isn't in yet.

**D-133 — Two germanium starters; a transistor is saturated only with its collector past its base** (2026-10-28) `models` `library`
- **Dallas Rangemaster** (`dallas-rangemaster`), from ElectroSmash's analysis: one germanium PNP, positive ground on −9 V, the stock 470k/68k divider; matches the page's bias, gain and input high-pass (image readings confirmed, D-042). (Model since: OC44, D-184.)
- **Tone Bender MkII** (`tone-bender-mk2`), from Aion FX's Deimos build document (benchmark voltages for every pin, hFE and leakage ranges per transistor); trimmers at the document's starting positions. Q1 is biased by its own leakage alone, so measured leakage matters most here (`tests/sim/test_measured_bjt.py`). (Models since: D-184, D-186.)
- **Saturation needs the collector past the base** (`analysis/dc.py`): under 0.3 V across it, a BJT is saturated only when Vce < Vbe, and always under 0.1 V (`BJT_VCE_FLOOR`). Germanium's small Vbe let a working stage read saturated before; silicon is judged as before. The headroom pane's 0.3 V floor is unchanged.

**D-134 — A buffered guitar keeps its volume; Render doesn't re-render a sweep; Keep keeps a sweep take** (2026-10-28) `audio`
- **"Buffered" keeps the guitar's volume**: the pot only scales the signal (`_scaled` scales the source; `Guitar.has_volume`; `live._step_values`).
- **An out-of-date sweep says so** (`sweepStaleText`); Render renders the pedal take only.
- **Keep keeps the take that is playing**, a sweep's too.
- **The progress bar takes the download buttons' place** (hidden, not removed), so nothing moves.

**D-135 — The Tone Bender with its Mode switch; a starter may keep a true warning; a switch's poles are apart in the DC graph** (2026-10-28) `library`
- `tone-bender-mk2-mode`: the Deimos's Mode toggle (Aion: "optionally bypasses the first transistor for a lower-gain mode … equivalent to the Tone Bender Mk. 1.5"). Only capacitors switch, so bias and benchmarks hold in both modes.
- **A starter keeps a warning that is true of the real circuit**: the board has no pull-downs on the switch, so the switched-out caps float: Missing pull-down warnings. The known-good corpus allows a warning listed in `tests/rules/corpus_warnings.yaml` with its reason (warnings only); the app shows them as for any circuit.
- **no-dc-path no longer joins a switch's poles** (`graph.spice_edges`): each contact is its own resistor in the netlist (1 TΩ open), so a common reaches its own throws only.

**D-136 — Every guitar starts with a volume pot; what plays changes only with Render or a take's button** (2026-10-28) `audio`
- A guitar input has a 250k A volume pot at full by default (every starter, a new sheet, the palette); its box can be emptied for none.
- **A cache lookup never swaps the take that's there**: it fills a pedal take only for a circuit just opened, with the player stopped. After a change the take stays, marked out of date.
- No render status text under the player; only a failure is written there.
- The pickup is part of the circuit (it loads the input), saved with it.

**D-137 — The schematic says which guitar is simulated** (2026-10-28) `audio`
Under the Guitar in symbol: its pickup's name ("Strat single coil"), "Your pickup", or "Buffered" (`view.part_text`, with the guide's names passed in).

**D-138 — A transistor's form shows the model's values; a sweep's buttons name their position** (2026-10-28) `panes`
- With the model picked, the form shows read-only Model's hFE and leakage (BJT) or Idss and Vp (JFET). Leakage shows for germanium models or a part already measured with one; germanium is read from the card itself, EG under 0.9 eV (`EG_GERMANIUM_MAX`), and every germanium model must carry its simulated `iceo` (unit test). Picking another model rebuilds the form with what's typed so far (`draftFrom`). `showIf` takes `is` as well as `not`.
- Each sweep job is labelled with its position (`renderSweep`).

**D-139 — branch order** (2026-10-28) — process note, nothing to keep. `project`

**D-140 — Op-amps are chips: a dual's two halves, power on real pins, pin numbers from the datasheets (schema v12)** (2026-10-28) `models`
- **A dual is two parts, one chip**: `Opamp.half` is `a` or `b`, refs IC1A/IC1B (D-141); the schema refuses a half without its partner or halves with different models. Placing a dual places both (half b `HALF_B_OFFSET` to the right); deleting either asks, then deletes the chip; paste and extract take the chip whole. Model or ref changes in one half change both (`renameChip`). The model list offers the same kind only. (Quads: D-172; power unit: D-179.)
- **Power is on real pins** (V+ out of the top, V− out of the bottom), wired like any pin; half b runs from half a's nets (`chips.supply_nets`). The supply rules read the pins.
- **Pin layout** in one table (`parts.py`, tested against the browser's).
- **Singles have all their pins**; the form's "all its pins" (`show_pins`) draws offset and NC pins too. The form lists every pin with its datasheet number, its net and how the simulation treats it.
- **Pin numbers come from each model's datasheet**, recorded as the model's `package` with its source; none without a checked sheet.
- **An unused half is a warning, not simulated** (`opamp-half-unused`): left out of the netlist (it would be singular), drawn faded, and the Problem says how to wire it as a buffer with pin numbers. Wiring a pin the model doesn't simulate is an info Problem (`opamp-pin-not-simulated`).
- **Migration v11 → v12** pairs old dual op-amps into chips (`V11_DUALS` fixed), turns `supply` into labels on the power pins, renames refs in notes, probes and bias targets. Netlists stayed the same but for names (`tests/fixtures/netlists/v11/`).

**D-141 — Each part type has fixed refs; IN and OUT never change (schema v13)** (2026-10-28) `schema` `editor`
- **The refs** (`solum/circuit/refs.py`, one owner; palette prefixes tested against it): R resistor, C capacitor, VR pot, TR trimmer, SW switch, D diode, LED (or D) LED, Q transistor and JFET, IC or U chip, V DC source, each with a number; a dual's halves end in A or B. The guitar input is always IN and the amp OUT; their Ref box is read-only.
- **Why**: factory schematics number the controls (Boss: VR1–VR3); DIY documents name them by function. Numbered refs keep tools and BOMs unambiguous; the name is the part's label (the "tag": "VR1 Volume"). An LED may keep a D ref so a diode swapped for an LED in Try changes keeps its ref.
- **A ref that doesn't fit is refused** with what it should look like ("A pot's ref is VR and a number, like VR1. Put its name in its label."), by the schema; no JS copy of the rule.
- **Migration v12 → v13**: a misfit ref gets its type's prefix, keeping its number if free, else the next; a pot, trimmer or switch named by its ref keeps the name as its label; AMP → OUT (`_rename_refs`, shared with v12). A file with two guitar inputs no longer loads.
- Read-only form rows wrap to their text.

**D-142 — Phase 9 groups** (2026-10-28) — process note: Phase 9 was split by area of code (parts, models, model tools, content, release) so each session worked in one area. Also settled: impedance stays the View overlay (Zin at IN, Zout at OUT), no number per net. `project`

**D-143 — Parts as real parts: switch types, poles as parts, the footswitch, DC jack and battery (schema v14, v15)** (2026-10-29) `schema` `editor`
- **Switch types instead of poles and throws**: SPST, DPST, SPDT, DPDT, 3PDT, 4PDT (on-on and on-off-on), DPDT on-on-on, rotaries 1P and 2P with 3 to 6 throws, and the 3PDT footswitch (more since, D-201, D-202). `solum/circuit/switches.py` owns them (`KINDS`: each type's lugs, positions and which lug each common joins); the browser gets them from `GET /api/switches`. Toggle lugs as the parts number them (common 2, throws 1 and 3); a rotary's C and 1…n. On-on-on follows Honeywell 2NT1-12's contact table. Each contact is a resistor in the netlist (`SWITCH_ON` / `SWITCH_OFF`).
- **Each pole is its own part**: SW1A, SW1B…, same `kind`, `position` and `label`, one knob for all; lugs A1–A3, B1–B3, as Aion draws them. `Circuit.with_part("SW1", position=1)` sets every pole. Deleting a pole deletes the switch; a paste renumbers the poles as one. Poles are stacked (`POLE_OFFSET`, `poleStep`).
- **Drawn as KiCad draws them**: each pole as KiCad's SW_SPDT (common left, throws right; SW_SP3T for three or more, SW_SPST, SW_SPDT_MSM for on-off-on); rotaries a part per pole; the DC jack as `Barrel_Jack_Switch`. A multi-pole switch's type is written once, under its last pole.
- **Migrations**: v13 → v14 turns `poles`/`throws` into a `kind` (`from_poles_throws`), pins into lugs, splits multi-pole switches into poles; v14 → v15 adds a wire where a lug moved, only where something was wired.
- **Position names**: `names` (one per position, up to 24 characters, empty keeps the type's), shown on the Knobs buttons with what each position joins as the tooltip (`contacts_text`) and in the drawing's value line ("SPDT · Thick").
- **The footswitch is simulated**: a 3PDT with On and Bypassed. Core blocks **True bypass (3PDT footswitch)** and **Buffered bypass (JFET buffer + 3PDT)**: on, the guitar goes to `send`, `return` to the jack, the LED lights; bypassed, in goes to out and the circuit's input is grounded. Wiring after Coda Effects' 3PDT guide (https://www.coda-effects.com/2015/03/3pdt-and-true-bypass-wiring.html); the grounded input and the LED's 4k7 after General Guitar Gadgets ("generally between 1k and 8k2, typically 4k7", https://generalguitargadgets.com/how-to-build-it/technical-help/bypass-sw-options/). Sim-tested.
- **The status LED is a normal LED with a label** (LED1 "Status"); LEDs have a `label`.
- **The DC jack is drawing-only**: ref DC, one per circuit, lugs + (sleeve), − (centre, centre negative) and the battery lug `sw`. It sits on V+ and GND; the Power dropdown's voltage still sets V+. `plugged` is the knob "Power: DC jack / Battery" when the circuit has a battery.
- **The battery is its own part**: BAT1, `volts`, `state` (fresh, half, low, flat, from `library/guides/batteries.yaml`, `GET /api/guides/batteries`), optional `resistance`. It powers the circuit when there's no DC jack or the jack is unplugged (`solum/circuit/supply.py`: `battery_of`, `live_rails`, `supply_volts`): the positive rails' ideal sources are left out. States from the Energizer 522 sheet's "Clock radio" curve (620 Ω): 9.0, 7.4, 6.6, 5.5 V (image readings, confirmed by the user). No internal resistance by default (the sheet gives none). (Battery wiring: D-164, D-185, D-202.)
- **Power blocks**: **9 V power: DC jack and battery** and **9 V power: battery only**, both ending in the 9 V filter to V+F (same ports, so either replaces the other).
- **What the power parts mean**: the **Power dropdown** is the wall-wart supply and always sets V+ (and V−); mains is never simulated. The **DC jack** draws the real jack and makes no voltage (for a full drawing, the parts list and export, and with a battery it's the Power switch). The **DC source** is an ideal voltage on a net other than V+/V− (a reference, a second supply, a test voltage); a voltage the pedal makes itself is the charge pump.
- **Blocks are suggestions**: no special case for dropping bypass blocks; Problems says what's left unwired.
- **Palette and hotkeys**: one Switch tile (S, SPDT; a footswitch is a type in its form), DC jack (H), Battery (Y).
- **Timing tests run on their own** (`@pytest.mark.timing`, after the rest of `make accept`).
- **A DC source's text says its volts.**

**D-144 — View → Capacitor types** (2026-10-29) `look`
A View switch, off by default, remembered (`solum.capTypes`), that writes each capacitor's type on its own line under its value (film, ceramic, C0G, electrolytic, tantalum; "not-set" dimmed italic), so the sheet doubles as a check before a BOM. Off by default because pedal schematics write the value only. `typeLine(part)` in `symbols.js`; redraws the schematic only.

**D-145 — The Power chip: who powers the pedal** (2026-10-29) `power`
With a battery or DC jack drawn, a chip left of Power says which powers the pedal now ("Battery · 7.4 V" or "DC jack"). With the battery in charge the dropdown is greyed (set the voltage on the battery, or plug the jack in); with the jack it stays live. `supply.power_chip(circuit)` is the one owner; with both parts it gives one entry per position of the Power switch, so a flip needs no request (`powerChip` in `app.js`).

**D-146 — A circuit's guitar input and amp stay; blocks never carry them** (2026-10-29) `library`
In a circuit, IN and OUT can't be deleted (Delete skips them and says why); in a block they can. Save as block leaves them and their wires out (`withoutEnds` in `blocks.js`). A box selection keeps its wires and labels across an edit that left them in place.

**D-147 — Readings move with what they belong to; each reading its own colour** (2026-10-29) `panes`
DC voltages are redrawn with the circuit after every edit and move with their label or pin while dragging; impedances with their part. Colours: DC brass (`--sch-dc`), impedance steel blue (`--sch-impedance`), capacitor types lavender (`--sch-type`), at least 30° of hue apart (`test_theme.py`).

**D-148 — Undo and redo put the selection back** (2026-10-29) `editor`
Each undo step keeps the selection that went with its circuit: undo restores the circuit before the step and what was selected then; redo the circuit after and its selection. As Figma, Illustrator and KiCad do. History jumps do the same. A snapshot's selection names wires and labels by their place in that very snapshot's lists, so it is always exact. Nothing selected then: the output is probed. `History.record(before, label, source, selection)`; `undo(current, selection)` and `redo(current, selection)` store and restore it (`restoreSelection`); a squashed session keeps its first step's.

**D-149 — Models and part types for v1; datasheets kept locally with a committed index** (2026-10-29) `models`
- **Which models**: the part lists builders meet in other pedal tools, plus requests (TL061). Op-amps, NPN and PNP (silicon and germanium), JFETs, diodes, zeners and LEDs; the shipped list is Tools → Parts and datasheets (D-191).
- **The bar**: a model ships only if it passes a datasheet check and may be redistributed (D-159).
- **New part types**: MOSFET (BS170, 2N7000, LND150), OTA (CA3080, LM13700), inductor (L plus wire resistance, with measured wah-coil presets), CMOS inverter (CD4049UBE) and power amp (LM386), each a real part with pins, a package and a datasheet.
- **Not now**: the optocoupler (its slow response over time is the point: v2); the transformer (Later: the maker's sheet gives impedances, not the winding inductances and coupling a simulation needs).
- **Datasheets stay local**: sheets are downloaded to `data/spec-sheets/`; the folder's `README.md` index (part, file, URL, date) is committed, the PDFs are gitignored (they usually can't be redistributed). `scripts/fetch_spec_sheets.py` downloads any listed sheet that's missing. Values read from a sheet go in the model's JSON record, cited (`rating_sources`, `validation`, `package.source`). Models tried and left out are listed in the index's Not shipped section, their files in the gitignored `data/spec-sheets/rejected/`.

**D-150 — Op-amp models, and every op-amp's output swing from its datasheet** (2026-10-29) `models`
- **Output swing**: each op-amp records `out_pos_headroom` and `out_neg_headroom`, the sheet's **typical** maximum peak output at ±15 V into 10 kΩ as headroom from each rail (typical, since the simulation is a typical unit). The Bias & headroom pane then reads "datasheet"; the 1.5 V rule of thumb stays only for an op-amp without a figure (a user's model); a unit test checks every library op-amp has one.
- **The cards are checked too**: `swing_pos` and `swing_neg` (`opamp_swing`: driven hard each way open loop into 10 kΩ) in every validation record, against the sheet's minimum swing. Some cards clip a volt short of their typical part (within the sheet's minimum), so the pane's limit can be about a volt wider than where the render clips with those.
- (Which op-amp models ship and how they were made: D-159, D-162, D-169.)
*Alternatives:* the minimum swing (1–2 V tighter than a bench part); the card's own clip point (not the part's).

**D-151 — BJT cards and sheets** (2026-10-29) — superseded by D-159 and D-163: BJTs are now our own fits to makers' sheets. Kept from it: Central Semiconductor's sheets (served at `my.centralsemi.com/datasheets/<NAME>.PDF`) were used where other makers refuse scripted downloads; cards from all-rights-reserved files (Intusoft's `BJTN.LIB`) are never used. `models`

**D-152 — No cards from LTspice's libraries** (2026-10-29) `models`
LTspice's library files are Analog Devices' ("All rights reserved"; the LTspice licence, section 4, forbids distributing the software in whole or in part), and collections that copy them can't relicense them. Cards there with no maker named are taken to be Analog Devices' and aren't shipped. A maker's own card carried inside such a file stays under the maker's terms (section 9). Lesson kept: a cut-off card can load with ngspice's defaults and still pass loose limits; read a card's simulated values against its own parameters, not only the sheet. (What ships now: D-159, D-288.)

**D-153 — A measured transistor is fitted on the simulated Geofex tester** (2026-10-29) `models`
- A card's gain at a real current sits away from its BF, a little or a lot, so replacing BF with a measured hFE (D-130) simulated the wrong unit.
- **A measured hFE is what the Geofex tester reads** (9 V, collector through 2.4 kΩ, 2.2 MΩ base to supply; collector current less leakage, over the base current; D-193). `solum.tester` simulates it; `fit_bjt` finds the gain scale and Icbo that make it read the measured hFE and leakage (within 0.1 %, remembered per card and values). The `Simulator` gives its library this fitter, so every run uses it; without a simulator `direct_fit` keeps BF = hFE.
- **The gain is scaled, not BF alone**: BF × k and ISE ÷ k, so the gain scales at every current, a hotter unit of the same die.
- **Where the form starts**: each BJT card records its own tester gain (`tester_hfe`, re-measured by the sim tests; a unit test checks every card has one), which `bjt_spec()` gives.
- **Published betas that are a simulation's BF are converted once** to tester readings (ElectroSmash's Fuzz Face β 85 and 120 read 79.4 and 110.4; the Rangemaster's 100 reads 91.6). Builders' meter readings (Aion's) keep their meaning.
- A gain over a thousand times or under a thousandth of the card's is refused in plain English (`FitError`).
*Alternatives:* BF alone (can't reach many cards' working gain); a fit per circuit at its own bias (a measured unit is one part, and the tester is what was measured).

**D-154 — JFET pins numbered 1 drain, 2 source, 3 gate** (2026-10-29) `models`
Makers disagree on TO-92 JFETs. onsemi's and Fairchild's numbered sheets say 1 drain, 2 source, 3 gate, the order pedal layouts assume; InterFET uses 1 source, 2 drain, 3 gate. The library takes the common order; each record's `package.source` notes where InterFET differs. The gate is pin 3 either way, so a swap only exchanges drain and source. A builder checks a unit against its own maker's sheet, or finds the gate with a meter's diode test. Central's and InterFET's cards forbid redistribution, so aren't used.

**D-155 — Diodes and zeners** (2026-10-29) `models`
- **Zeners are subcircuits**, as Diodes Incorporated publishes them (a forward diode, and a reverse diode behind a voltage source). A zener's record has no reverse-voltage rating (breaking down is its job). Gaps: a zener's current isn't read at the operating point, so the current rule and the probe skip it; the charge pump's doubler refuses a zener in plain English.
- **Validation quantity `vz`**: the zener voltage at the sheet's test current, measured as `vf` with the diode turned round on a 30 V supply.
- (Which diode and LED models ship: D-157 to D-160.)

**D-156 — The models index lists what ships and each model's licence; our own fitted models where no card may ship** (2026-10-29) `models`
- `data/spec-sheets/README.md` lists every model in `library/models/` (part, type, who made the model, source, datasheet checks, licence), written from the records by `scripts/models_index.py`; a unit test fails when it's stale. With the Not shipped list, every part's outcome is in one place.
- **Our own models**: where every published card is off limits or none exists, a model is fitted to the part's datasheet and published as ours: checked at datasheet points it wasn't fitted to, its record saying it's a fit and from which sheet. (The order of preference: D-159.)
*Alternatives:* downloading licence-blocked cards on the user's machine (needs the network, leaves the image without them); keeping the table by hand (goes stale).

**D-157 — Green, blue and white LEDs: our own fits to Kingbright's sheets** (2026-10-29) `models`
WP7113GD (green), WP7113QBC-D (blue), WP7113QWC-D (white). The sheets draw the forward curve as vectors, so points are read exactly from the PDF (`pdftocairo -svg`, mapped by the grid lines). IS, N and RS from a least-squares fit of V = N·Vt·ln(I/IS) + RS·I over every other curve point from 1 mA up (`scripts/fit_models.py`); each record's `fit` block keeps points, sheet, figure and method. Checks: VF typ (±0.1 V) and max, plus held-out curve points (±50 mV). Fitter floors: N ≥ 1, and IS ≥ 1e-26 (ngspice quietly raises a smaller IS to about 1e-28). Below 1 mA the fits follow the diode equation, not the sheet (noted).

**D-158 — 1N60 and BAT42 as our fits; a reverse-current check** (2026-10-29) `models`
- Fitted to each sheet's vector forward curve (every other point fitted, the rest held out; the top point always fitted so the top-current limit holds): 1N60 (Wuxi Xuyang; a very soft curve, N 4.3, RS 22 Ω) and BAT42 (Vishay).
- **IS is the model's reverse current, so it's held under the sheet's leakage limit** (`fit_diode(..., is_max=)`; the 1N60 at half its 100 µA limit, so it leaks more than a typical unit: a known gap in the record).
- **Validation quantity `ir`**: reverse current at the sheet's test voltage. Records round measured values to 6 significant figures.
- A fit to maxima alone would model a worst-case unit, so parts whose sheets give only maxima aren't fitted. 1N916 ships as the 1N914 (one onsemi sheet covers both; only the capacitance differs).

**D-159 — Models: a maker's own card, else our own from the sheet; diode pins 1 cathode, 2 anode** (2026-10-29) `models`
- **The order for every part**: (1) the maker's own card from the maker's own site, where its terms let it be passed on; (2) otherwise our own model built from the maker's sheet (a curve fit where it draws curves; its typical values where it gives them, as for op-amps; the middle of its ranges only for JFETs, whose per-unit Idss and Vp replace it anyway); (3) only without a sheet, ask. Cards from libraries we may not pass on are rebuilt this way.
- **Diode and LED pins: 1 cathode, 2 anode** (KiCad's convention); each record's `package.source` cites the outline and how the cathode is marked.
- **Two diodes in parallel where one can't follow the curve** (`fit_diode_pair`, a two-pin subcircuit): BAT41 (its curve's slope changes too much for one diode), BAT46. Same gap as zeners: a subcircuit's current isn't read at the operating point. BAT48 from Vishay's sheet.
*Alternatives:* keeping licence-questioned cards pending a decision; one diode fitted to the clipping range only (fails the sheet's high-current limit).

**D-160 — Every diode and LED card is our own fit to a maker's sheet, except the 1N34A** (2026-10-29) `models`
- Rebuilt, each record's `fit` block naming its sheet and figure: 1N4148 and 1N914 (Diotec's curve plus onsemi's low-current readings), 1N4001 and 1N5817 (Diotec), 1SS133 (ROHM), BAT46 (Vishay, two diodes), APT1608SURCK (Kingbright).
- Makers' own cards weren't an option: onsemi's carry a notice restricting commercial use; Nexperia names no terms; ROHM's and Analog Devices' are for internal use only.
- The doubler's pulse-current test takes N from the card.
- **1N34A** keeps a library card: every sheet found gives only VF ≤ 1.0 V at 5 mA, no curve. A kept card that misses its sheet somewhere (the 1N34A breaks down at 25 V against 65 V guaranteed: irrelevant in a clipper) records the sheet's figure in the check's note, not as `min`/`max`, so the miss is written down and still re-measured.

**D-161 — JFETs: our own level-1 models from their sheets** (2026-10-29) `models`
- Idss and Vp give VTO and BETA = Idss/Vp². Where the sheet gives a typical Idss and a typical VGS at a current, Vp follows from the square law; otherwise the geometric middle of each range (they spread over decades). LAMBDA from a typical output conductance where given; CGD = Crss, CGS = Ciss − Crss.
- Checks: each part's Idss and cut-off ranges plus the typical VGS points. One square law can't meet both a typical |Yfs| and the bias; bias matters more in a pedal.
- No noise, RD/RS or temperature terms (the sheets give no figures). A circuit's measured Idss and Vp still replace the card's.
*Alternatives:* arithmetic middles (most units sit low in a decade-wide range); fitting to transfer-curve figures (sample units, not a typical one).

**D-162 — Op-amps: our own small macromodel from the sheet's typical figures** (2026-10-29) `models`
- Makers build these cards from their own typical figures, so we do the same from the sheet (TI's 1993 TLC2262 card came with unclear terms).
- **How** (`OpAmpFit`, `opamp_card` in `scripts/fit_models.py`): an ideal input (1 TΩ) feeds a tanh transconductance stage limited to 10 µA into C1 (slew = 10 µA / C1); R1 gives the open-loop gain (gm·R1 = AVD) and gm/2πC1 the gain-bandwidth; a second pole at GBW / tan(90° − PM) gives the phase margin, gm raised by 1/cos(90° − PM) so the crossing stays at GBW; diode clamps a set headroom from each rail and an output resistance set the swing; output current drawn from the rails plus the quiescent current. Pins + − V+ V− out.
- First: TLC2262 (SLOS177D): simulates at 105.8 dB and 719 kHz; slews at 0.548 V/µs.
- **Not modelled**: input bias and offset, noise, common-mode limits, output current limit. Ratings still come from the sheet.
*Alternatives:* a Boyle macromodel (more parameters than a sheet pins down); keeping TI's card (licence unclear).

**D-163 — BJTs: our own Gummel-Poon fits to the sheets' typical curves** (2026-11-02) `models`
- **How** (`GummelPoon`, `fit_bjt_forward`, `fit_bjt_saturation`, `fit_junction_cap`, `bjt_tf`, `bjt_card` in `scripts/fit_models.py`): `GummelPoon` computes currents as ngspice's BJT does. IS, NF, BF, ISE, NE, IKF, NKF and RE by least squares on the typical hFE and VBE(on) curves together; BR, ISC, NC and RC on the VCE(sat) curve at its forced beta, **with the hFE points held** (alone, it drove ISC up and lifted low-current gain). CJE/VJE/MJE from Cibo, CJC/VJC/MJC from Cobo; TF from fT less the junction charging time; VAF = IC/hoe − VCE from a typical output admittance, else left out. RB, NR, VAR, TR and temperature terms at defaults.
- **NKF fitted** (not 0.5): with 0.5 the gain read 12 % low past 20 mA on parts whose sheet falls faster; bounded at 1.
- **NR = NF**: with NR 1, parts with NF 1.2–1.3 read VCE(sat) 0.1 V high whatever else did; fitted freely NR isn't pinned.
- **Family curves**: where one typical curve covers several parts or grades, its shape is kept and its level set to the geometric middle of the part's hFE range.
- **Where a figure contradicts the sheet's own table, the table wins**; the record says so.
- **Fit range**: up to `top_ma` where Gummel-Poon can't follow further; held-out checks inside it; the record says how the card reads above.
- **Checks** (`tests/sim/model_checks.py` `vbe`, `vce_sat`): the sheet's min/max table plus held-out points: hFE within 5 %, VBE within 10 mV, VCE(sat) within 5 mV or 7 % (Gummel-Poon has no quasi-saturation). `bjt_hfe` measures at exactly the current asked for.
- A circuit's measured hFE still applies (D-153).
*Alternatives:* NKF fixed at 0.5 with the fit stopped lower; VBIC or quasi-saturation models (more parameters than typical curves pin down).

**D-164 — Battery ground, kept bends, label drags, checked values (schema v16)** (2026-11-02) `schema` `editor`
- **The battery's − is ground** (schema v16): the migration turns each `IN_ring` label into a GND label and drops the blocks' `IN_ring` port. (Cable switching: D-185.)
- **A part dropped on a wire is cut in even where the wire is in pieces under it** (`inSeries`, `cutBetween`); a jumper pin to pin stays.
- **Wires keep their bends when what they're joined to moves** (`stretchRun`; narrows D-063), as KiCad drags: the bend next to the moved point slides so its leg stays straight. A straight wire, a run whose bends would land on something (`touchesNew`), or a run with both ends moved is routed afresh.
- **Labels, GND and V+ drag by their symbol or name**; a press right on the label's point (within 3 units) still starts a wire.
- **Text blocks copy and paste on their own**; pasted labels keep their turn.
- **A block dropped with a pin, label or wire end exactly on a point of the sheet stays there and joins it** (`joinsAt`) when nothing else is under it; otherwise it moves to a clear spot (D-072, D-189).
- **Symbol text stays upright on a turned part.**
- **A window resize keeps the zoom and the middle** (`resizeView`; scale held while resizing, a `ResizeObserver`).
- **Values: the unit must be the part's, and the value one a slip can't produce** (`parse_value(text, unit)`, schema `Ohms`/`Farads`): "4k7F" on a resistor is refused; a capacitor takes 100 fF to 1 F, a resistor, pot or trimmer 1 mΩ to 1 TΩ, so `10f` (femto) or `10F` for 10µ are caught, with what was read and an example. `10uf`/`100pf` read as farads. **A typed value is kept in its standard form** (`100uf` → `100µ`, `0.047u` → `47n`, `4.7 kΩ` → `4k7`; `format_value` to 6 figures); a number stays a number. Formatting has T.
- **A capacitor's slider runs over a fixed 10p–470µ in E12** (`CAP_RANGE`); resistors and pots keep a decade each way.
- **A slider works on a sheet that can't be simulated yet** (`live_view(..., simulate=False)`).
- **A clicked label stays selected through an edit to it** (`keepSelection`), so Space turns it again and again.
- **Multi-throw switches are named by poles and throws** ("2P3T", group Selector); ids keep `rotary-…`.
*Alternatives:* a reserved `BAT_GND` net treated as ground everywhere; range checks only in the form (the server owns parsing).

**D-165 — Parts no current can reach are left out of the simulation, and said so** (2026-11-02) `sim` `rules`
- **What's left out** (`loose_parts`, `solum/circuit/connectivity.py`): a group of parts touching no ground, supply, block port, guitar or amp; then, repeatedly, a passive part with at most one pin joined to the rest. No current flows through them, so leaving them out changes nothing. A transistor or op-amp with an open pin stays in. If nothing reaches an anchor, nothing is left out (no-dc-path says so).
- **One list for "not simulated"**: `left_out(circuit, nets)` (`chips.py`): a chip's unused halves plus loose parts; the netlist, the saturation check and `spice_edges` skip them, and rules look only at simulated parts (`Context.parts`). A stray part no longer stops runs, live curves or Bias & headroom.
- **Problems names them** (`part-not-simulated`, warning); `unconnected-pin` skips them.
- **Probing a loose part shows no readings, without an error** (`loose_net`); recording or driving a loose net is a plain `NetlistError` (`require_wired`).
- A floating net the circuit does depend on (two caps in series to ground) still stops the run.
*Alternatives:* `rshunt` (confident 0 V readings on floating nets); leaving out only parts with every pin open.

**D-166 — Tests run in parallel (pytest-xdist)** (2026-11-02) `project`
pytest-xdist (dev extra only): `make test` and `make check` run on every core (`JOBS`, default `auto`); `make accept` on 4 workers, a test file each (`ACCEPT_JOBS`, `--dist loadfile`; more browsers with their servers and renders timed out); timing tests serial in `make accept`'s second pass. `JOBS=0 ACCEPT_JOBS=0` runs one at a time. On 16 cores `make check` went from 4 min to under 1.5. *Alternatives:* fewer, bigger tests; skipping coverage in `make check`.

**D-167 — Big Muff Miller poles checked like for like: BC549C for the page's BC239** (2026-11-02) `models`
The two Miller-pole checks in `big-muff-pi-v3.expected.yaml` run with BC549Cs (`set:`) in the stages they measure, standing in for ElectroSmash's BC239s; the starter keeps its 2N5089s. `both-clippers-high` passes; `input-miller-low-pass` stays a known gap with the reason: R9 ∥ C10 alone gives 720 Hz, which the stage's loop gain lifts; the page's 1.2 kHz would need much less gain than the stage has (not beta, which barely moves it). *Alternatives:* BC549C in the starter (builders use 2N5089s); widening the tolerance (D-034 forbids it).

**D-168 — Library cards with no curve sheet** (2026-11-02) — superseded by D-288: those cards (2N4123, 2N4125, AC127, BC109C) left the library. The note-not-limit rule for a kept card that misses its sheet is in D-160. `models`

**D-169 — Five more op-amps as our own macromodels: NE5532, LM833, OPA2134, JRC4580, CA3260** (2026-11-02) `models`
- Their published cards failed (swing past the sheet, or PSpice-compatibility mode only) or didn't exist; each is now `opamp_card` from its sheet's typical figures (`.claude/skills/fit-model/tools/fit_opamps.py`).
- **Phase margin from a sheet's overshoot** (NE5532, CA3260 give 10 % as a follower): fitted so the follower at the sheet's own load overshoots 10 % (the textbook two-pole figure gives 16 % there: output resistance and load capacitance add phase).
- **JRC4580: margin assumed, 60°** (the sheet gives none, and its one phase graph contradicts its own table). The model holds the table's gain at 10 kHz; above the audio band it may ring less than a real 4580.
- **A sheet's "GB at f = 10 kHz"** is held as gain × frequency there, letting the margin set the crossing; a unity-gain bandwidth is the crossing itself.

**D-170 — One AC128, our own fit to Valvo's sheet; schema v17** (2026-11-02) `schema` `models`
- **Sheet**: Valvo, *Halbleiterdioden und Transistoren* 8.63, pages 123-129 (a scan; `data/spec-sheets/AC128_Valvo.pdf`, local). Curves read off the raster (`.claude/skills/fit-model/worked/ac128/trace.py`). Package TO-1 (E1 B2 C3).
- **One card, measured units**: the sheet's gain spread is 55-175, so circuits set each transistor's measured hFE and leakage. Schema v17 moves the old ElectroSmash AC128-B85/B120 parts to `AC128` with their measured values.
- **Fitter**: `rb` (the sheet's rbb′ 25 Ω); `is_max` (germanium IS ~1e-5 A); fit points at VCB = 0 (`vce=None`), as old sheets measure (at VCE = 1 V germanium leakage props up low-current gain); ICBO fitted with the gain and VBE through BR. Gain within 4.9 %, VBE within 3.2 mV to 10 mA. Checks gained `icbo` and a `vcb` condition.
- **Closer to reality than ElectroSmash's card**: its VBE is ~0.22 V, Valvo's 80-160 mV at pedal currents, and Aion's readings of real Tone Benders agree with Valvo. So the germanium acceptance files carry the resulting differences as known gaps with reasons.
- **Tone Bender TR1 is solved for Q2's collector at -0.16 V** (inside Aion's readings).
*Alternatives:* keeping ElectroSmash's cards (VBE disagrees with the maker and real pedals; CC BY-NC); fitting at VCE = 1 V.

**D-171 — A tester gain below the sheet's gain curve is said so in the form** (2026-11-02) `rules`
The Geofex tester runs a transistor near 0.3–0.4 mA, below some sheets' curves. `Model.bjt_spec()` adds `tester_ic` and `sheet_low_ic` when the tester's collector current is under the lowest fitted gain point (MPSA06, AC128); the form's Model's hFE hint (`belowSheet`) says the figure is the model's extrapolation.

**D-172 — Quad op-amps (TL074): a chip of four, IC1A to IC1D; schema v18** (2026-11-02) `schema` `models`
An op-amp's `half` takes a–d; a chip with a C or D unit is a quad and must have all four; one model per chip; `chip_spec().halves`. Placed as IC1A/IC1B over IC1C/IC1D (`HALF_OFFSETS`), deleted and renamed whole. TL074: 14-pin package from TI SLOS080W. A "Quad op-amp" tile, no hotkey. (Power unit: D-179.)
*Alternatives:* a separate 14-pin part with four op-amps inside (every pin rule and form would need a second path).

**D-173 — The inductor: L in series with its wire's resistance; measured wah inductors as presets** (2026-11-02) `models`
- **Part**: `inductor`, ref L1, `value` in henries (1 nH to 100 H), `resistance` (wire DCR, 0 = ideal), `kind` (preset). Netlist: `R_L1_wire` then `L1`. A plain two-terminal part everywhere else (slider, influence, compare, parity-tested on a wah-like tank).
- **Presets** (`library/guides/inductors.yaml`): Stickman393's measurements (PedalPCB forum, "Wah inductors: no hype, just measurements", 2024-11-09; Hantek 1832C LCR meter): red Fasel 666 mH / 15.65 Ω, yellow Fasel 638 mH / 13.9 Ω, Dunlop Halo 564 mH / 27.2 Ω, Whipple Halo 520 mH / 27.8 Ω, ME-6 613 mH / 28.8 Ω, 535Q 626 mH / 17.8 Ω. L at **1 kHz**, the frequency Dunlop states its ME-6 at (these cores read up to 30 % higher at 100 Hz). The thread's opening list is left out (its author marks it untrustworthy).
- No hotkey (L is the label key). **Not modelled**: core loss, frequency dependence, saturation, self-capacitance (a wah's sweep is far below self-resonance).
*Alternatives:* L at 120 Hz (below a wah's sweep); a Q factor (DCR is what a builder can measure).

**D-174 — Input and output jacks: drawing-only parts, as KiCad draws them** (2026-11-02) `editor`
`jack`, refs J1, J2…, stereo (TRS) or mono (TS), `label`. Pins and drawing are KiCad's `AudioJack2` / `AudioJack3`. Drawing only: left out of the netlist; the rules' graphs don't pass through it; never loose and no path searched through it. A stereo jack's ring may be open. (The battery and the ring: D-176, D-185.)

**D-175 — The MOSFET: ngspice's VDMOS, fitted to Fairchild's 2N7000 sheet** (2026-11-02) `models`
- **Part**: `mosfet`, ref Q, pins D, G, S, `model`. Netlist `M_Q1 d g s <card>` (VDMOS: three terminals, body diode inside; `@m_q1[id]` read at the operating point). N-channel; `Model.polarity` reads `pchan`. A transistor everywhere a JFET is (anchors, signal paths, net names, the unbiased-gate and drain-source short rules, part view, live curves).
- **Saturation**: ohmic when VDS is under VGS − VTO **or 0.2 V** (`MOSFET_VDS_SAT`, `mosfet_vds_sat`): the fitted card conducts below VTO. Cut off under 0.1 µA.
- **2N7000 card**: fitted through ngspice by Levenberg-Marquardt to Fairchild's Rev. 2.10 vector figures (output, transfer, capacitances, body diode) and table (VGS(th) 2.1 V at 1 mA weighted heavily; the table wins where Figure 5's low end disagrees, D-163). Package TO-92 S-G-D.
- **BS170** is the 2N7000's card under its own package (TO-92 D-G-S): same die and figures (checked against onsemi's MMBF170 by pixel, D-178).
- **Drawing**: enhancement symbol; body diode drawn (D-177). No hotkey.
*Alternatives:* level-1/3 MOSFETs (no body diode or subthreshold); vendor subcircuits (no licence allowing shipping).

**D-176 — Chips drawn the KiCad way; problem marks; the battery and the ring; MOSFET stages** (2026-11-02) `editor`
- **Chips are drawn the KiCad way**: signal units (IC1A, IC1B…: op-amps, a 4049's six inverters, an LM13700's two OTAs) plus a separate power unit with V+ and V− (KiCad's unit C on a TL072). Placed whole. (D-179.)
- **Problem marks** as KiCad's ERC markers, with dismissal (D-181).
- **Jacks and the battery**: as Aion's and PedalPCB's schematics, the battery's − drawn to the input jack's ring; the simulation assumes a cable is in (D-185).
- **MOSFETs** join the bias-trimmer solve and the Bias & headroom pane as a JFET does; body diode drawn (D-177, D-178).

**D-177 — MOSFETs as stages: the drain target, the Bias & headroom row, the body diode drawn** (2026-11-02) `models`
A MOSFET is a stage as a JFET is (`stages._OUT_PINS`: out D, common S, in G); its room down is to `mosfet_vds_sat`. The form has the JFET's Drain target and Bias trimmer (`drainFields`); a trimmer's Add target finds a MOSFET's drain (`OUTPUT_PIN`). The body diode is drawn beside the channel, outside the circle, no pin of its own (it shows why a MOSFET can guard a reversed supply).

**D-178 — The LND150 as our own depletion VDMOS fit; the BS170 keeps the 2N7000's card** (2026-11-02) `models`
- **LND150**: fitted through ngspice to Microchip's DS20005454A vector figures: VTO −1.27 V, KP, KSUBTHRES, MTRIODE, LAMBDA (capped at 0.01), RS to Figure 2-4 (points past the knee weighted, since pedals use it saturated), the table's RDS(on) and VGS(off) middle; capacitances to Figure 2-9. Figures at VDS 400 V left out (self-heating); Figure 2-10 is a held-out check the card runs above (its sample is weaker), noted.
- **Depletion in the app**: `Model.depletion`; a solid channel in the symbol (`draw.depletion`); the transfer curve starts below VTO (`MOSFET_VGS_BELOW`); model checks `idss` and `vp` measure it as a JFET's.
- **BS170**: onsemi's MMBF170/D figures, read by pixel, match the 2N7000 points within a few %: same die, same card.

**D-179 — A dual's or quad's power unit, as KiCad draws it** (2026-11-03) `editor`
- **The part**: `powerunit` (schema v19): V+ out of the top at (0, −40), V− out of the bottom at (0, 40), a narrow box (KiCad's unit C on a TL072, E on a TL074). Its ref is the chip's with the letter after its last half (IC1C, IC1E: `refs.ref_problem`); its `model` is the chip's; the schema refuses a chip without its unit, a unit without a chip, or a unit with another model. Halves have no power pins; `chips.power_part` returns the unit, so `supply_nets`, the supply rules (which name the unit) and the netlist read the chip's supply from it. Not simulated itself (`DRAWING_ONLY`): its nets are the halves' supply.
- **Singles keep V+ and V− on the triangle**, as KiCad draws a TL071.
- **Editor**: placing a dual or quad places its unit too, right of the halves (a quad's between its two rows); selecting, deleting, renaming or changing the model of any one changes the chip (`chipRefs`, `isChipPart`); a pasted chip gets one new number. The unit's form lists the chip's op-amps and its two pins with datasheet numbers (the package's unprefixed `V+`/`V-`).
- **Migration v18 → v19**: half a's V+/V− move to a new unit beside half a, at the first spot (60, 80, … 200 either side) where its pins touch nothing and its body crosses no wire or part. A labelled net gets the label on the unit's pin; an unlabelled one a short wire from the old pin. Failing every spot: past the drawing's right edge when the supply is labelled, else on half a with its pins where hers were. Every connection stays (tested on labelled, unlabelled and blocked cases).
- The LM386 power amp was dropped from v1's part types.
*Alternatives:* a power unit for singles too (not KiCad's standard); keeping power on half a (not what a KiCad user expects); jumpers to every migrated unit (labels read more cleanly).

**D-180 — The 4049 and the OTAs as chips on D-179's power unit; schema v20** (2026-11-03) `models`
- **One chip concept for every chip**: op-amps, inverters and OTAs are each a chip's units (`_ChipUnit`, `CHIP_UNITS`): a `model`, a `half` letter on a chip of several (the field keeps its v12 name) and a `chip`. A chip of several has a power unit after its last unit; a single carries its own V+ and V-. `chips.py` (`halves`, `power_part`, `supply_nets`, `unused`), the editor (`isChipPart`, `chipRefs`, `CHIP_UNIT_TYPES`), the schema's whole-chip check (`CHIP_SIZES`: op-amps 2 or 4, inverters 6, OTAs 2; one kind and model per chip), the netlist (`_chip_unit`), the supply rules and the form (`chipFields`) work on all three.
- **The 4049 (`inverter`)**: always six, IC1A to IC1F, power unit IC1G (VDD on V+, VSS on V-), as KiCad's units A–G. Pins in, out. Placed in two rows of three, the power unit to their right.
- **OTAs (`ota`)**: a single (CA3080: +, -, out, iabc, its own V+ and V-) or half a or b of an LM13700 (+, -, out, iabc, dbias for its linearising diodes, bufin and bufout for its Darlington buffer; power unit IC1C). The buffer is drawn inside its half, not as a unit: one part per amplifier keeps form and netlist one subcircuit each. An OTA's out is a current, so it isn't a bias anchor; its buffer's out is. Diodes and buffer may be left unconnected without a warning.
- **Unused units (`chip-unit-unused`)**: a spare inverter's input is tied to a supply (a floating CMOS input sits where both transistors conduct); a spare OTA's inputs go to V- with its bias input open. The op-amp's own rule (buffer on mid-supply) stays.
- **`/api/models/chips`** (replacing `/api/models/opamps`): each chip model's type, units, simulated pins and package.
- **Schema v20, no migration**: the bump stops an older build reading files with the new types (or D-181's dismissals).
*Alternatives:* a separate buffer unit on the LM13700 (another unit type for one chip); the 4049 as six singles each with power pins (LTspice's way, not KiCad's).

**D-181 — Problem marks on the schematic; dismissed problems kept in the circuit** (2026-11-03) `editor` `rules`
- **Marks**: as KiCad's ERC markers, a small ■ ▲ ● by severity (`--error`, `--warning`, `--text-3`, outlined in `--surface-0`) on the pin of the problem's first part that is on its first net when exactly one pin is; else just off the part's top right corner; a nets-only problem at its first net's anchor; none for a problem naming nothing on the sheet. Several on one spot sit side by side. Tooltip is the message; a click opens the problem's row in Problems. View → Problem marks (on by default, `solum.problemMarks`). Placement is `problems.js` (`markSpot`, `problemMarks`) from the circuit view's pins and nets, re-resolved on every redraw, so the server's Problem needs no pin field.
- **Dismissing**: Dismiss… asks an optional reason (≤ 200 characters). A dismissal names its problem by rule, refs and nets (`Circuit.dismissed`, `schema.Dismissal`), so it survives re-checks and reloads. Dismissed problems lose their mark and are listed under a Dismissed section with reason and Bring back; the heading's count leaves them out. Dismiss and Bring back are edits (undo, History, saved), but don't re-check or mark results stale. Renaming a part renames its dismissals' refs and pin-named nets (`Q1.D`).
- **What a save keeps**: a dismissal naming a part or net the circuit no longer has is dropped on save (`circuit.dismissals.kept_dismissals`). One whose parts are all there is kept while its problem doesn't occur, so a problem that comes back (a knob turned) comes back dismissed.
- **Schema**: `dismissed` is optional (omitted when empty), part of the v20 bump.
*Alternatives:* dropping a dismissal whenever its problem isn't in the last check (a knob position would lose operating-point dismissals); matching on the server (the browser needs the match anyway: one owner in `problems.js`); a pin field on every rule hit; a free-text key per problem (a renamed part couldn't take it along).

**D-182 — The battery-ring rule** (2026-11-03) — superseded by D-185: the rule (`battery-not-on-ring`) was dropped; a battery's − to ground is always fine. `power` `rules`

**D-183 — National's LM13700 card is not shipped; ours stays** (2026-11-03) `models`
- **National's card** (TI SNOM267, may be copied and distributed, not resold): single-pole (its header says AC bandwidth and phase margin are overstated over 2×) with a 0.6 mV input offset (its input pair differs 2.5 % in IS). It met the table's gm and peak current. Listed as *Not included* (D-197); ours is the only LM13700 in the library.
- **Figure 13 (distortion with the diodes) is met by neither** (ours 0.0003–0.002 %, National's 0.2–1 %, the sheet 0.08–10 %). Accepted: the low-level difference is inaudible, and the sheet's steep rise likely depends on Figure 13's test circuit. Rebuild that circuit before changing the card, if an LM13700 circuit ever disagrees with a published measurement.
- The OTA gm check takes the current from −1 mV to +1 mV across the inputs, so a card's input offset cancels.

**D-184 — OC71, OC44 and OC75: our own fits to Mullard's sheets; the germanium starters use the pedals' own parts** (2026-11-03) `models`
- **Sheets**: Mullard Technical Handbook Vol. 4 Part III (Nov 1968): OC71 Issue 2, OC44 (Dec 1960), OC75 (March 1959), raster scans read by pixel; Philips' OC75 table (1958-60) adds six checks. Package SO-2 glass, E B C. Scripts and notes: `.claude/skills/fit-model/worked/germanium/` (`NOTES.md`).
- **Fitted as drawn, leakage in**: Mullard's transfer line meets IB = 0 at I'co, so IC at the sheet's IB, VBE and ICBO are fitted together at the sheet's VCE (−4.5 V; OC44 −2 V) with the card's own leakage flowing, not at VCB = 0 as Valvo's AC128 (D-170). RB is rbb' (OC71 300 Ω, OC44 110 Ω, OC75 none so 0); VAF from h'22; CJC from Cc/Cb'c (the OC75's from a cross-reference book's Cob ≤ 50 pF); TF from fα as fT.
- **Judgements**: the OC71's Average line is drawn into the origin (no leakage), so used from 5 mA; its VBE (117-121 mV at 1 mA) is kept against the table's 135 typical as it's inside the limits (D-163). The OC44's input figure contradicts its IC-VBE figure and table and is left out.
- **Result**: OC71 IC within 1.5 % to 1.1 mA (7.9 % at 5 mA), VBE 4.7 mV to 6 mA; OC44 IC within 5.8 %, VBE 2.4 mV; OC75 IC within 6.6 %, VBE 1.9 mV. Every table limit met; 6 held-out misses, each above the useful range or against a figure judged off (listed in NOTES).
- **The starters use them**: the Rangemaster's Q1 is the OC44 (ElectroSmash names it), the Tone Bender MkII's Q1-Q3 the OC75 (Aion: OC75, some units OC81D). Measured hFE and leakage stay (D-130), so bias moves little; the treble changes through collector capacitance. The acceptance files' known gaps were re-read and re-explained. The AC128 stays (the Fuzz Face's part).
*Alternatives:* the AC128 everywhere (wrong treble for the OC44); fitting at VCB = 0 (Mullard gives no such curves); a free RB for the OC75 (trades against IS and VBE).

**D-185 — Battery and stereo jack: ground by default, a cable switch when wired to the ring; schema v21** (2026-11-03) `schema` `power`
- A battery's − to ground is always fine: the 9 V power block draws it that way and no rule asks for a jack. Replaces D-182.
- A stereo jack gets a **cable in / out** toggle (`Jack.plugged`, default true, as the DC jack's plug, D-143). Cable in: the ring joins the sleeve; out: the ring is open. Otherwise the jack stays drawing-only (D-174): its tip needn't be wired to the guitar input part, which stays the source (wiring it would add nothing and a second way to draw the same thing).
- A battery whose − reaches a stereo jack's ring powers the circuit only with the cable in; with it out a warning says the battery's cut off.
- **Two switches, as on a real pedal**: the DC jack's plug decides DC or battery; the input cable decides whether a battery wired to the ring reaches ground. The battery powers the circuit only with no DC plug and, when wired to the ring, a cable in.
- **The lug is simulated as wired**: the DC plug cuts the battery off only when its + goes through the DC jack's battery lug. A battery whose + is on V+ directly stays connected beside the adapter.
- **Netlist**: `R_J1_ring` from R to S, 0.01 Ω with the cable in, 1e12 Ω out, only when both pins are wired. Knobs shows a stereo jack's "Input cable" switch whenever the circuit has a battery; both it and the DC jack's Power are `plug` knobs, so the browser no longer singles out ref `DC`. The guitar input part's own ring keeps its cable always in.
- **Rules**: `battery-cable-out` (warning, on the jack); `battery-beside-adapter` (warning, on the battery: a DC jack is drawn and the battery's + is on a rail instead of the battery lug; fires plugged or not). A + reaching the lug through a part (a protection diode) isn't flagged.
- **Two supplies on one net**: `supply.on_battery` (battery alone, the positive rails' sources go) and `supply.battery_of(circuit, nets)` (battery connected now). Beside a DC plug the battery is in the netlist with its internal resistance; with none and its + on a live rail, the netlist refuses in plain English naming both fixes (wire + to the battery lug, or give the battery a resistance).
*Alternatives:* a default internal resistance (a made-up figure behind a real-looking result); the cable switch only on jacks whose ring is wired (Knobs would need the nets); the switch on the guitar input part too (one way is enough).

**D-186 — OC81D: an estimated card, the OC75's shape at the OC81D's table figures; no NKT275** (2026-11-03) `models`
- **No sheet with curves could be found** (Mullard 1968 and Philips' books skip it). The only figures are a cross-reference book's row: VCE 16 V, IC 10 mA, 150 mW, fT ≥ 200 kHz, Cob ≤ 40 pF, hFE ≥ 20 at 5 mA, lead code as the OC75.
- **The card**: our OC75 fit (D-184) scaled by the ratio of the two rows: BF × 20/55, ISE × 55/20, CJC × 40/50, TF × 1/2; VBE, leakage, VAF and RE stay the OC75's. hFE 33 at 5 mA, 30 on the tester. Script `.claude/skills/fit-model/worked/germanium/estimate_oc81d.py`.
- **Marked as an estimate**: `source.original` is `Solum Builder estimate` (`models.ESTIMATE`); the models index says *Estimated (…)*; `bjt_spec()` carries `estimated`, and the transistor form's gain hint says to measure yours.
- In the Tone Bender, with measured hFE and leakage kept, OC81D for OC75 changes nothing audible (treble +1.3 dB at 5 kHz, +2.6 dB at 20 kHz). The starter stays on the OC75.
- **No NKT275**: no figures anywhere; a card would be invented, not estimated. Left out until a sheet turns up.
*Alternatives:* leaving the OC81D out (Aion names it); aliasing it to the OC75 (hides its lower gain); estimating the NKT275 from the AC125 (nothing of its own to scale by).

**D-187 — 2SC1815: our own fit to Toshiba's sheet** (2026-11-03) `models`
- **Read by pixel** off Toshiba's 1997-04-10 sheet (`data/spec-sheets/2SC1815_Toshiba.pdf`, page 2; `.claude/skills/fit-model/worked/c1815/`): hFE – IC at 6 V, IB – VBE (turned into VBE against IC), VCE(sat) at IC/IB 10, fT – IE. Fitted as D-163.
- **Judgements**: VBE fitted from 1 mA (below it the sheet's line is steeper than a junction can be). No VAF (the sheet's hFE lines at 1 V and 6 V coincide; the output curve disagrees, likely self-heating). RB 50 Ω from rbb'. ISC capped at 0.1 nA (`fit_bjt_saturation(isc_max=)`): left free it sits on the fitter's bound, leaking 10 nA; 3.4 pA fits VCE(sat) about as well. No CJE (no Cibo); TF from fT at 1 mA; CJC from Cob 2.0 pF at 10 V.
- **Result**: VBE within 4.1 mV (1-100 mA); VCE(sat) within 2.3 mV; hFE within 3.5 % from 0.2 to 50 mA, 8.7 % low at 100 mA (the sheet's knee is sharper than Gummel-Poon's). Every table limit met; held-out points within 2.9 % and 2.8 mV.
- **One card for the four gain grades** (the sheet draws one line); a GR or BL part is measured (D-130). Pins E C B. `.claude/skills/fit-model/tools/bjt_record.py` takes an optional Cibo and RB from rbb'.
- **The TS808 uses it** for Q1 and Q3 (as published), replacing the 2N5089 stand-in. Its gain through the 510K bias resistors puts the buffers' emitters at 2.85 V (higher-gain grades sit higher), so Q1's stage reads *sits low*; no published DC figure to check against. Every published check unchanged. The 2N2222A's and 2N3906's ISC also sit near the bound, left as they are.
*Alternatives:* the KiCad library's Toshiba card (hFE 715 at 2 mA, VAF 6 V: not shipped); VBE fitted from 0.05 mA; VAF 32 V from the output line (contradicts the hFE lines).

**D-188 — 2N404 and 2N1308: our own fits to RCA's and TI's sheets; VBE(sat) as a model check** (2026-11-03) `models`
- **Sheets**: RCA 2N404/2N404A/2N581/2N582, File No. 15 (`data/spec-sheets/2N404_RCA.pdf`); TI 2N1302–2N1309, bulletin DL-S 1136 (August 1959). Both are computer-switching alloy transistors described at 10–300 mA, nothing below 10 mA, so at a pedal's 0.3–2 mA the gain is the card's extrapolation, which the form says (D-171). Read by pixel, fitted by `.claude/skills/fit-model/worked/germanium/alloy.py` (hFE, IC at an IB, VBE(sat), VCE(sat), ICBO, IEBO, and curve shapes up to one free factor). Notes and tables in `NOTES.md` there.
- **2N404 (PNP, TO-5, E B C)**: no typical curves, only a table. Level from the table, high-current shape the geometric middle of the minimum and maximum collector curves. **Fig. 2 (minimum hFE) left out**: it reads 1.2–1.75× the table's minimums and rises where the table falls. **Gain held flat below 12 mA**: left free it rose with nothing to hold it, unlike every other germanium sheet. RB 0 (no rbb'), no VAF; CJC from Cob 12 pF; TF from fhfb. Result: the table within 5.3 % (hFE), 11 mV (VCE(sat)), 17 mV (VBE(sat)), every limit met; VBE(sat) 12–16 mV under Fig. 8's minimum at IB 1–4 mA (no RB; under 1 mV at pedal currents), recorded as known misses.
- **2N1308 (NPN, TO-5, E B C, base on the case)**: fitted to its own table column and the NPN hFE curve's shape (its free level came out 1.02 × the table, so they agree). **The family's VCE and VBE lines are information only** (no one type's; fitted, they missed the table's VCE(sat) by 30 mV); they give only RC 1.28 Ω. Cob the 20 pF maximum shaped by the family curve; CJE from Cib 10 pF; TF from fαb. Result: the table within 0.1 %, 0.5 mV and 0.9 mV, the curve within 6.2 %, held-out points within 5 %.
- **In the pipeline**: a `vbe_sat` validation quantity (`bjt_saturated` returns VBE and VCE together); `GummelPoon.saturated` and `GummelPoon.iebo` in `scripts/fit_models.py`; `forward` takes the first VBE that carries the current (a germanium card's IC turns over past about 0.6 V at fixed VCE, and bisecting landed past the turn).
- **Other cards**: none exists for the 2N404; Central's 2N1304 card (no redistribution) misses its own sheet, so no reference. Central's one figure at pedal current (hfe 140 typical at 1 mA, the whole family) against our 122 (13 % under) isn't reason to refit.
*Alternatives:* fitting Fig. 2 (contradicts the table); the 2N404's gain free below 12 mA (it rises); a free RB from VBE(sat) lines (RB only from rbb', D-163); fitting TI's family VCE lines (another type's gain).

**D-189 — A dropped block never joins two named nets** (2026-11-03; refines D-164) `editor`
- **The bug** (found by Hypothesis, `test_pasting_again_and_again_never_collides`): a dropped block's V18 wire end landed on the sheet's GND label, was taken as a join, and the circuit no longer loaded. Paste went the same way.
- **The rule**: a drop that would put two differently named labels on one net isn't a join: the block goes to the nearest clear spot. Every other coinciding end still joins (D-164); wiring by hand is untouched (the server still reports a clash).
- **How**: `namesClash(wires, labels)` in `web/editor/blocks.js`, the narrow geometric part of the server's label check (`connectivity.py`), needed synchronously while placing; the server stays the owner of nets. A paste judges with the names the block will have, so a renamed non-global label (`OUT` → `OUT_2`) doesn't join the sheet's `OUT` (D-072).
*Alternatives:* asking the server per candidate drop (placement is synchronous); refusing any join through a block's wire (loses D-164's case).

**D-190 — A BJT record's fit points are (IC, DC gain); a transfer curve is kept under `curves.transfer`; the tester's current counts leakage** (2026-11-03) `models`
- **Shape**: every BJT record's `fit.points` are `[IC amps, IC/IB]`, as `Model._below_sheet` reads them (a unit test checks every record). Mullard's transfer curves `[IB, IC]` (OC44, OC71, OC75) are kept as read under `fit.curves.transfer`.
- **The gain is the DC gain with leakage in it**, as a sheet's hFE is, so the lowest-current points read high.
- **The tester's collector current counts leakage**: `tester_ic` = tester gain × VCC/RB + `iceo`, since the sheets' curves include it.
*Alternatives:* leakage-corrected points (needs the IB = 0 current, an extrapolation for the OC44); `tester_ic` without leakage (compares unlike currents).

**D-191 — Tools → Parts and datasheets: every model, its datasheet and its caveats, read from its record** (2026-11-03) `models`
- **What it shows**: every model by type, searchable. A row: id, description, origin (*Our fit*, *Estimate*, *Library card*, *Maker's model*) and a Datasheet ↗ link. Opened: the origin in a sentence, the sheet's figures it was fitted to, caveats, how many datasheet limits it meets, and figures the sheet gives no limit for, each with its note.
- **Nothing computed anew**: `Model.catalogue_entry()` reads the record. A check "meets" a limit when the datasheet record has a min, max or typical with tolerance (`tests/sim/test_models.py` holds each); a comparison with a note and no limit is shown as compared, not checked (D-168).
- **Whose card**: `solum/model_origin.py` (`card_origin`) is the one owner, used by the app and `scripts/models_index.py` (standard library only, so the script runs without the app's dependencies).
- **Records gain optional fields** (model records, no circuit schema change): `datasheet` (the URL to open) and `note` (caveats of a card we didn't fit: the no-curve-sheet cards, D-168; the RC4558/MC1458/LM741 swing; the behavioural charge pumps, D-093). A fit's caveats stay in `fit.note`.
*Alternatives:* datasheet links from `data/spec-sheets/README.md` at run time (not in the image); caveats computed from validation numbers (a kept miss has no limit to compare against).

**D-192 — Tools → Add a model: a discrete `.model` card from the user's file, cleaned, checked and saved to `DATA_DIR/models`** (2026-11-03) `models`
- **Flow**: pick a file → the server lists its top-level `.model` cards it can add (D, NPN/PNP, NJF/PJF, VDMOS) → pick one, say what part it is (a D card: diode or LED) and its name → **Check**: cleaned by `clean_card` (D-029), measured through the real pipeline on a copy of the library, readings shown with "looks wrong" outside a plausible range → **Add to my models**: saved as `DATA_DIR/models/<type>/<id>.json` + `.lib` and added to the running library. The file never leaves the machine; the upload is the file's text as JSON (no multipart dependency), 2 MB at most.
- **The quick check** (`model_import.CHECKS`): diode VF at 1 and 10 mA (LED 2 and 20 mA); BJT gain and leakage on the tester (D-153), hFE and VBE at 1 mA, 5 V; JFET IDSS and VP at 10 V; MOSFET VGS(th) at 1 mA. They become the record's `validation`. Out of range warns but doesn't block; a card the simulator can't run is refused.
- **Renamed to its id**, so it can't clash in a netlist with a core card of the same SPICE name. A taken id is refused (a user model would otherwise hide a core one, D-011).
- **Origin `user`** (`model_origin.USER`, "Added by you").
- **Measuring lives in the app**: `solum/model_checks.py` (tests and tools import it).
- **`ModelLibrary.add`**: `with_fitter` shares the model dict instead of copying, so an added model is in the simulator's and the checker's library too; the fingerprint is cleared on `add`.
- **Not yet**: removing a user model in the app (delete the two files from `DATA_DIR/models`). (Op-amps: D-195.)
*Alternatives:* a multipart upload (needs `python-multipart`); keeping the card's own name (clashes); refusing an implausible reading (blocks a real odd part).

**D-193 — The germanium tester hint checked against Geofex's own page** (2026-11-03) `models`
- **Source**: R.G. Keen, "The Technology of the Fuzz Face", http://www.geofex.com/Article_Folders/fuzzface/fftech.htm.
- **The method matches the hint**: 9 V, 2.2 MΩ supply to base (switched in), collector through 2.4 kΩ (ideally 2.472 kΩ so volts read as gain ÷ 100); read with the base open (leakage), then pressed; subtract. The simulated tester's 2.4 kΩ (`solum.tester.RC`) only scales the reading, not the currents.
- **The leakage hint** follows Geofex: "100uA is common, 200 happens pretty often. More than 300uA means the device is suspicious, and more than 500uA I would say is bad".

**D-194 — The pre-commit hook skips commits of Markdown notes only** (2026-11-03) `project`
- `scripts/pre-commit` runs its checks unless every staged file is a Markdown file in `docs/` or the top folder. Unit tests per note bought nothing.
- Still checked: `data/spec-sheets/README.md` (the models index test), `docs/circuit.schema.json` (generated and tested), and any commit mixing notes with code.

**D-195 — Op-amps in Tools → Add a model: the user's `.subckt` inside a wrapper with the usual pins, checked as a buffer** (2026-11-03) `models`
- **Found**: every top-level `.subckt` with five nodes or more is offered as an op-amp, with its nodes (in order, up to any `params:`), the comment lines just above it (up to 12; makers name the pins there) and a first guess (+, −, V+, V−, out, then "not connected"). A dropdown per node; the user reads the comment.
- **The wrapper**: the saved card is `.subckt <id> inp inm vpos vneg out` with an `X1` of the user's subcircuit in their node order, and every definition in the file inside it (cleaned by `clean_card`; commands, includes and stray elements dropped). Nested definitions are local in ngspice, so a user's `.subckt TL072` or `.model DX` can't clash with ours (tested). A node left unconnected goes to ground through 1 TΩ.
- **The check** on ±4.5 V: unity buffer at ±0.5 V in, swing to each rail into 10 kΩ, open-loop gain and GBW. The pin order is refused ("the pin order is probably wrong") when the buffer doesn't follow or the output goes the wrong way with + above −. Other readings warn.
- **Package**: single, dual or quad chosen in the form; no package record (no pin numbers drawn, D-140) and no ratings (the supply-limit rule doesn't apply).
- **New quantity**: `buffer_out` (`model_checks.opamp_buffer`).
- **The check runs apart** (`model_import.check_apart`): each Check and Add spawns a fresh process with its own ngspice, killed after 30 s. Some wrong pin orders send ngspice's DC solve spinning; `bg_halt` doesn't stop a DC solve, so the thread runs on and every later run in that process times out, and unloading the library under a live thread would crash the server. So the app's own ngspice never sees an untried card (about 0.6 s a check). Tried all 120 orders on four op-amps: only the right one passes each; the spinning ones are stopped and refused. Any card is checked this way.
*Alternatives:* rewriting the user's `.subckt` line in place (helper models could still clash); reading the pin order from the comment (formats vary too much); ngspice's DC iteration limits (no guarantee); the render pool (D-083: can't kill one stuck worker).

**D-196 — Yours, then stock: the model dropdowns, the parts list and Add a model's name** (2026-11-03) `models`
- **Which are yours**: `Model.yours` (`source.original` is `USER`); `GET /api/models` adds `yours` beside the ids by type.
- **Model dropdowns**: `<optgroup>`s *Added by you* then *Stock*, only once you've added a model of that type; else one plain list. A model no list has (a file from another machine) stays on top, ungrouped. No search: typing in an open dropdown jumps to the name, enough for the list sizes.
- **Parts and datasheets**: on/off toggles Yours · Stock · *Not included* beside Find, all on to start; within each type, yours first. *Not included* lives only in this list (D-197).
- **Add a model's name** starts as the card's own, or `<card>-mine` when taken (then `-mine-2`…), cut to 40 characters (`model_import.suggested_id`). Names keep their case, but an id matching an existing one in any case is refused: ngspice reads names case-blind.
- The Tone timing test (`test_tone_updates_the_curve_quickly`) times the curve itself, not the Bias & headroom pane's measuring after it.
*Alternatives:* an All button with one filter at a time; always two groups (an empty *Added by you*); a Yours tag in each option's text.

**D-197 — Cards we may not ship: listed as *Not included*, each with a "where to get it" ⓘ; nothing downloaded** (2026-11-04) `models`
- **Which**: every card whose licence was *Decide* in D-156's index (LTspice's makers' cards in KiCad-Spice-Library files at the pinned commit; AC127 and 1N34A, which name no maker; Intusoft's J201; ElectroSmash's two AC128 cards; TI's TLC2262 download) and National's LM13700 (D-183). The list is `library/models/not-included.json` (`solum/not_included.py`): per source why it's out and what to get; per card the part, its card name, file and link. No `.lib` text.
- **In the parts list**: a row per card, tagged *Not included*, last in its type; its ⓘ says why, what to get, and to add it with Tools → Add a model. Never in the model dropdowns or Add a model.
- **Once it's in, the entry goes**: a user model added from a card of that name (`Source.card`), or a stock model from the same file under that name.
- The LM13700 can't be added yet (Add a model takes no OTAs; its ⓘ says so). ElectroSmash's cards are printed on a page: copy the `.model` line into a text file first.
- **One ⓘ pop-up for many buttons** (`panels.infoPopup`), so a list redrawn on each keystroke doesn't pile up listeners; `infoButton` is its one-button case. Over a sheet it sits above the shade; Esc shuts it first.
*Alternatives:* a downloader (dropped); one entry per source file (the user looks for a part); hiding an entry by id alone (our own 2N3904 would hide Philips' card).

**D-198 — Trimmers in the Audio pane: a closed fold, three positions, each checked for a saturated stage first** (2026-11-04) `panes`
- **Where**: a closed *Trimmers (advanced)* fold under the sweep row, only when the circuit has a trimmer. A row per trimmer: its name (lights it on the schematic) and Render. Trimmers stay out of Knobs & switches.
- **Positions**: 25, 50 and 75 % (`TRIM_POSITIONS`): a trimmer is set once, and its ends are where a bias is most likely broken.
- **The takes go in the sweep row**, named for the trimmer, so playing, snapshot, Download all and the out-of-date note work as for a pot. The pot dropdown shows blank ("Sweep") after a trimmer renders.
- **A trimmer set by a bias target** is greyed with the reason and no Render; the server refuses it too (every position would be solved back to the target).
- **The check**: `POST /api/render/sweep/check` runs a DC operating point per position (`Simulator.saturated`, the same `saturation` the AC validity and rules use). A position with a stage saturated, cut off, ohmic or railed gets an amber border and a line saying that take is a broken bias, not a sound. It still renders.
- **A Render finishing keeps your pick**: a take picked while Render runs keeps playing; the new Pedal take waits on its button and the status says so.
*Alternatives:* trimmers in the pot sweep's dropdown (wanted apart); free positions (mostly broken biases); skipping saturated positions (hides what was asked for).

**D-199 — Two voices: a stage lights the leg its switch picks** (2026-11-04) `panes`
- A stage lit only parts with a pin on its own nets (`stage_parts`, D-122), so with a switch between a stage and two bias legs, neither leg lit.
- **Now**: a closed contact joins its two nets for `stage_parts` (across chains of closed contacts, never through a supply or ground), so the picked leg lights with the stage and the open one doesn't; flipping re-measures. Fixture `tests/fixtures/circuits/two-voices.json`.
- No "both voices side by side": the chain follows the switch as played.
*Alternatives:* measuring each position and showing two chains; lighting both legs, the open one dimmed.

**D-200 — Part forms: a few words under each box, the rest in the form's ⓘ; the battery says what its wiring does** (2026-11-04) `look`
- **One ⓘ per form**, at the end of its title bar, when any field has more to say. A field's `hint` is a few words; its `about` (how to measure it, the datasheet's range, background) goes in the ⓘ under the field's label, built as it opens, so a hidden row is left out. One pop-up shared by every form (`infoPopup`).
- **Moved into the ⓘ**: datasheet ranges and tester how-tos (hFE, leakage, Idss, Vp), the below-the-sheet explanation, MOSFET enhancement/depletion and body diode, trimmer target detail, the pot's Use as, switch type notes, jack and DC jack battery switching, battery states' source and resistance, inductor presets' source, the guitar's Buffered case and stereo ring, the charge pump's whine, the chip's V+/V− labels. A chip pin says something only when out of the ordinary (not in the model, NC).
- **New lines**: the DC jack, "Centre negative. Wire + to V+: the Power menu's supply comes in here."; the DC source, "Drives its own net. V+ and V− come from Power." (D-091).
- **The battery**: `supply.battery_wiring` is `alone` (no DC jack: it always powers the circuit, the Power menu greyed), `lug` (its + on the DC jack's battery lug: a plug cuts it off) or `beside` (its + elsewhere: it stays connected beside a plug, which Problems warns about, D-185). The Drained row's hint says which; with no DC jack the Power chip's and greyed menu's tooltips say to draw one. `battery_of` reads it. (`apart`: D-202.)
- The Audio pane's Trimmers fold hint moved into an ⓘ the same way.
*Alternatives:* an ⓘ per field (a row of buttons down the form); long text behind a "More" link under each box (the form still grows).

**D-201 — Switch types, a custom switch, rotaries drawn on an arc; schema v22** (2026-11-04) `schema`
- **Built-in types** in `switches.KINDS` (the list as trimmed: D-202). Push buttons have Released/Pressed, held in Knobs where they're put, since the simulation is static. No SPDT on-on-on (a 3-lug toggle has no third way). No push-pull pot (it would need the pot's lugs).
- **Custom** (`CustomSwitch`, kind `custom`): a name, 1–4 poles, 1–12 throws, 2–12 positions; each position joins each pole's common to one throw or leaves it open; drawn as a toggle or (3 throws or more) a rotary. It can't join two throws without the common (make-before-break, bridging). **In the circuit only**: every pole carries the same definition (the circuit check holds them equal), so the server reads a switch's type from its part (`Switch.switch_kind`). Lugs named as the built-ins with that many throws: one throw 1, 2; two as a toggle 2, 1, 3; else C, 1…n. The browser repeats that rule (`kindOf`, `throwLugs`) for pin geometry, parity-tested against the server.
- **The editor**: Custom… at the end of the Type list opens a sheet started from the type picked (so a built-in can be tweaked), with a grid of positions × poles whose choices name the lugs as drawn. Apply changes every pole at once; the form says "Custom: Clip" and links "Edit its contacts…"; another type drops the contacts.
- **Rotaries on an arc** (as KiCad's SW_Rotary): pins unchanged (common left, throws in a column), so no file changes; inside, a pivot, contacts on an arc, leads to the lugs, the wiper to the closed contact.
- **v21 → v22** adds only `custom` (fixture `old/schema-v21.json`).
*Alternatives:* custom types saved in the user's library (the curated list covers most pedals); a text syntax for the contacts (harder to read than a grid); a lug-to-lug join list (allows bridging; a grid of commons covers every listed switch).

**D-202 — A battery powers only the rail it reaches; the switch list trimmed to what's sold** `power`
- **Battery**: it takes over a positive rail only when its + reaches it: on V+, or on the DC jack's battery lug with the jack's + on V+ (`supply._reached`, `battery_rails`). With no DC plug in it powers that rail and the Power menu is greyed. Its + on any other net makes it a supply on that net alone (`battery_wiring` `apart`): `on_battery` is None, the Power menu stays live and drives V+, the chip is hidden (or reads DC jack), and the form says so; its ⓘ lists every way to wire + and − (`fields.BATTERY_WAYS`). On V+ with a jack plugged in, it stays beside the adapter (D-185). `battery_rails` memoises the last circuit (`on_battery` is asked many times a run). Before, a battery on its own net still switched V+'s source off, leaving V+ at 0 V with no warning.
- **Switches** hold what Tayda sells as mini toggles and stomps, and Alpha's SR2511F rotaries. Toggles: SPDT, DPDT, 3PDT, 4PDT on-on; SPDT, DPDT, 3PDT on-off-on; DPDT on-on-on (Honeywell 2NT1-12's middle); SPDT and DPDT (on)-off-(on) momentary (Knobs holds it). SPST and DPST on-off. Two push buttons (normally open, normally closed). DPDT and 3PDT stomps and an SPST momentary one. Selectors: 1P3T–1P6T and 1P12T, 2P3T–2P6T, 3P4T, 4P3T. Custom covers the rest.
- **On-on-on with three distinct positions**: a 1P3T or 2P3T selector, or the DPDT on-on-on toggle (with a jumper, or as a custom switch for another maker's middle). No 3PDT on-on-on toggle was found for sale; Custom draws one.
*Alternatives:* a battery on any net taking V+ over (the chip says battery while V+ is dead); the battery in the Power menu (it isn't a supply plugged in); every Alpha rotary size (rarely stocked).

**D-203 — Ready to build and the parts list** `build`
- **Build checks are rules with `build: true`** (`Rule.build`, `Problem.build`), shown in Problems too; warnings don't block. `cap-no-kind`, `cap-no-rating` (electrolytic or tantalum), `part-no-package` (per model), `switch-custom` (notes); `cap-rating-close`, `resistor-power-close` (warnings); `cap-over-voltage`, `resistor-over-power` and `part-not-simulated` are flagged too. Missing-information checks are one problem naming every part (`Hit.refs`).
- **Margins** (`checks.py`): a capacitor with more than 80 % of its rating across it is too close (`CAP_MARGIN`); a resistor past half its rating runs warm (`POWER_MARGIN`; ¼ W when none set). Rating advice is the smallest of 6.3/10/16/25/35/50/63/100 V that leaves the margin (`cap_rating_advice`; 16 V on 9 V, 25 V on 18 V), from the highest supply when no rating is set.
- **Build notes kept apart**: a build check at note level goes under a closed *Before you build · N* section, uncounted and unmarked on the sheet (`forTheBuild`), so starters don't show a list of "no type" notes over real problems.
- **Exports are made on the server from the last save** (`/api/export/{starter|circuit}/{id}/…`), so the whole package matches the circuit file in it. Unsaved: save first; a block isn't exported alone. Ready to build lists unsaved changes first, then "doesn't simulate", then the build checks, errors first; dismissed ones are counted.
- **The parts list** (`export.bom`): identical parts grouped, on the board then off it, by type then value, refs in order (`refs.ref_key`: C2 before C10). Details: resistor wattage, capacitor type and rating (or "not set"), pot taper (B100k), package and pinout for discrete semiconductors ("TO-92 (EBC): 1 E, 2 B, 3 C"), package for chips; a measured transistor is its own line ("picked for hFE 108"). A chip is one line however many units, a switch one however many poles. Named parts carry their name ("VR1 (Gain)").
- **Off the board**: pots, switches, jacks, DC jack, battery, a Status LED. IN and OUT each count as a ¼" mono jack (stereo when the guitar input is stereo) unless a drawn jack stands for that end (its tip on the end's net, else its label Input/Output). Any other drawn jack is its own.
- **CSV** with a UTF-8 byte-order mark (so a spreadsheet reads µ); **the printable page** is self-contained HTML in ink on white, the same page WeasyPrint turns into the PDF.
*Alternatives:* a separate export-check engine (two owners); one problem per capacitor; exporting what's on screen (package's circuit and bias sheet could disagree); counting input and output only when jacks are drawn (no starter draws them).

**D-204 — The enclosure and the generic hardware** `build`
- **The enclosure is saved with the circuit** (schema v23, `Circuit.enclosure`, no-op migration), picked in File → Properties: 1590A, 1590B, 125B, 1590BB, 1590XX (`solum/circuit/enclosures.py`, outside size as the seller lists it, each with its source), or Custom L × W × H in mm. Build note `enclosure-not-chosen` when none. It's part of the design and the export works from the last save, so it lives in the file.
- **Hardware after the parts**: the enclosure; one knob per pot; an IC socket per DIP chip or charge pump, grouped by package; an LED bezel for the status LED; a 9 V snap per battery. **A fixed checklist** (`CHECKLIST`: board, mounts, hook-up wire, heat-shrink, rubber feet, solder) as *Also* lines with no quantity.
*Alternatives:* the enclosure as an export option in the browser (lost from the package and on another machine); knobs from the pots' shaft type (no such field).

**D-205 — The schematic as SVG and PDF; WeasyPrint for the PDFs** `build`
- **The schematic is drawn by the sheet's own renderer, in the browser** (`web/schematic/printed.js`): the last save's view drawn into a hidden SVG with paper colours (theme.css `.print`), grid and interactive bits removed, cropped, every element's computed style inlined so the file needs no stylesheet. A server-side renderer would be two owners of every symbol. The PDF is made on the server from that SVG (`POST /api/export/…/schematic.pdf`, ≤ 8 MB, an SVG with a viewBox or a 422).
- **One landscape sheet, filled** (`schematic_sheet`): scaled to fill A4 landscape; if that puts its text under 2 mm (about 6 pt), A3 landscape instead. A small circuit grows only until its text is 3.5 mm. Never split across pages: following a wire across sheets is worse on the bench than a larger sheet.
- **WeasyPrint** makes every PDF (`export.pdf`) from the same self-contained pages, in the app's own Lora. It fetches only `data:` and `file:` (`URLFetcher(allowed_protocols=…)`), so a posted SVG can't make the server fetch a URL (tested).
- The theme test reads `:root` only; the `.print` colours have their own contrast test on white.
- **Image growth**: runtime image 230 → 318 MB (+88 MB: the package with Pillow, fontTools, pydyf, and Debian's Pango, HarfBuzz-subset and fonts-dejavu-core).
*Alternatives:* the browser's print-to-PDF (a dialog per page, no PDFs in the zip); a Python port of the symbols (two owners); Chromium in the runtime image (hundreds of MB more); ReportLab (a second layout for every page).

**D-206 — The exported netlists and models list** `build`
- **One self-contained `.cir` per analysis** (`export.export_netlists`), by the one netlist generator from the last save: `op.cir` always; `ac.cir` (1 V at the input) and `tran.cir` when the circuit has a guitar input and an amp output. Targeted trimmers are solved first (`solve_bias`) and the header says what they were set to. Model cards are inlined; a part with measured figures gets its own copy of the card. Each runs as `ngspice -b op.cir`; AC and transient carry `.print` lines (batch mode prints nothing for them otherwise).
- **The waveform is a 1 kHz tone at the *med* pick** (`EXPORT_TONE_HZ`, `EXPORT_LEVEL`), after the circuit's settling time, as the app runs it.
- **Models**: `models.txt` lists each model used (name, kind, pins in order, source, ours or the maker's); `models/<name>.lib` holds each card. `GET /api/export/…/netlists.zip`; a circuit that doesn't simulate is a 422 in plain English.
- **The dev image carries the ngspice CLI** (dev stage only): the sim tests run every exported starter netlist in plain ngspice and match the app's DC voltages within 2 mV.
*Alternatives:* one file with every analysis (another tool expects one); `.include`-ing the cards (breaks on its own); a `.control` block (ngspice-only).

**D-207 — The bias sheet** `build`
- **Its own module** (`solum/bias_sheet.py`), on the same page style as the parts list (`export.page`), as HTML and PDF (`/api/export/…/bias.html`, `bias.pdf`; a circuit that doesn't simulate is a 422).
- **Trimmers**: one with a target says "Set TR1 until Q2's collector reads −0.16 V", with the simulation's turn as a hint; if unreachable, it says so and to check the parts around it. One without a target is at its saved turn, with its wiper's DC.
- **Pots that move the bias** (`POT_MOVES`, 0.1 V): a pot whose end-to-end turn moves any listed pin's DC that much is listed at its saved turn. One `.op` at each end per pot.
- **DC voltages**: every transistor's, chip's (as one chip, IC1) and charge pump's pins, by datasheet pin number where the model has a package, two decimals with a real minus sign. A macromodel's compensation pins aren't listed (model nodes, not what a real pin reads).
- **Current drawn**: each rail's as a positive figure, with a total when several.
- **Check first**: a stage saturated or cut off at DC (`Simulator.saturated`) heads the sheet.
*Alternatives:* every net's DC (a builder probes pins); every pot (most irrelevant to bias); tolerance bands (we'd invent them).

**D-208 — The build notes page** `build`
- **One page** (`solum/build_notes.py`, `notes.html`, `notes.pdf`), from the last save, no simulation: the description, *Knobs* (each pot: name, value and taper, saved turn), *Switches* (type, positions, saved one in bold), *On the sheet* (text blocks, top to bottom then left to right), then notes on parts and nets by ref.
- Trimmers aren't knobs: they're on the bias sheet (D-207).
- No description: the page says where to write one (File → Properties).
*Alternatives:* notes inside the parts list (read at different times on the bench); notes only from the sheet.

**D-209 — The generic wiring diagrams** `build`
- **Three hand-drawn SVGs in `library/wiring/`** (3PDT true-bypass footswitch with status LED, the jacks with the ring switching the battery, the DC jack with the battery lug), each listed in `sources.yaml` with what it follows; a page with drawings and steps (`solum/wiring.py`, `wiring.html`, `wiring.pdf`). A drawing is content, so it lives in the library.
- **Lugs by what they do, not by number**: makers number 3PDT lugs differently, so the drawing names rows (effect throw, commons, bypass throw) and poles (input, LED, output), and the steps say to find the effect row with a meter. The LED pole grounds the LED's cathode with the effect on; the bypass jumper joins the input and output poles' bypass throws.
- **Battery and DC jack as the app simulates them** (D-143, D-185): battery + on the DC jack's battery lug, − on the stereo input jack's ring; the DC jack centre negative, its sleeve the circuit's 9 V, so a plastic-bodied or insulated jack.
- **A positive-ground circuit** (a negative rail and no positive one) is warned at the top: this DC wiring isn't for it, and it can't share a daisy-chain supply. Circuit-specific wiring is for later.
- **Styles inside each drawing**: WeasyPrint doesn't style an inline SVG from the page's CSS, so `wiring_page` writes a `<style>` into each one from `export.PRINT_COLOURS`.
*Alternatives:* drawing the diagrams in code (harder to edit); numbered lugs from one maker's sheet (wrong on another's); leaving the stereo jack out.

**D-210 — The build package** `build`
- **One button, *Build package (zip)***, in File → Export. `POST /api/export/…/package.zip` with the schematic the browser drew (D-205) and the Ready to build rows it showed (worked out in the browser, `readyRows`, so not matched a second time).
- **One folder in the zip** (`<name> build package/`): `index.html`, `circuit.json` (the last save), `parts-list.pdf` and `.csv`, `schematic.pdf` and `.svg`, `bias-sheet.pdf`, `notes.pdf`, `wiring.pdf`, `netlists/` (op, ac, tran, `models.txt`, `models/*.lib`). PDFs, not the HTML pages: one copy each.
- **The index page**: *Ready to build* first (errors, warnings, notes; how many dismissed), or "Nothing open"; then each file, linked. A circuit that doesn't simulate still gets a package without bias sheet and netlists, and the index says why.
- `export.zip_files` takes the folder; `solum/package.py` owns what goes in (`CONTENTS`, `package_files`, `index_page`, `build_package`); the app passes in the simulations (`Simulated`).
*Alternatives:* the package entirely on the server (it can't draw the schematic); HTML pages as well as PDFs (two copies); a flat zip (unzips into the folder's top level).

**D-211 — The starters' capacitor types, ratings and enclosure** `library` `build`
Every shipped starter's Before you build list is empty and its parts list says what to buy.
- **Types in this order**: the main source's words; else the parts list of Aion FX's kit of the same circuit, by ref where numbered the same or by role where not; else the app's capacitor guide (`library/guides/capacitors.yaml`: film in the signal path). Each starter's acceptance file has a `build` section citing the extra sources and saying what came from which.
- **Ratings: 16 V on every electrolytic** whose source gives none: the app's own advice for 9 V (`cap_rating_advice`), and the acceptance files say so. The TS808's source gives 10 V for C16 and C17; C17 has 9 V across it, past the 80 % margin, so both are 16 V and the file says the original used 10 V.
- **No non-polarised electrolytic kind**: the TS808's "1uF NP/50V" C2 and C7 are film, as Aion's kit lists them; likewise the Big Muff's 1 µF caps.
- **Enclosure 125B on every starter**, as Aion's kits list it.
- The corpus test holds starters to no build notes at all.
*Alternatives:* types from memory of the originals (D-019: never); the source's 10 V with its warning (a starter with a problem); a bipolar-electrolytic kind (a schema bump for parts film does as well).

**D-212 — The Tone Bender's clean-up gap is a setting, not the simulator** `library`
Simulated, the Tone Bender MkII barely cleans up with the guitar's volume; owners say a MkII does, best at low Fuzz (reports, no measurements).
- **Explained, not fixed.** The starter matches Aion's Deimos schematic. TR1's target (Q2's collector at −0.16 V, D-184) sits at the high-gain end of Aion's settings: 65 dB at full Fuzz, 45 dB at minimum; at TR1's documented 3:00 start 44 and 33 dB, and Q1's leakage moves it about 12 dB more. Q1's 20-24 dB make up for the volume pot's loss in front of it, which is what lets a Fuzz Face clean up. At the low-gain end of Aion's ranges, low Fuzz and a soft pick, the guitar's volume takes the 3rd and higher harmonics from 52 % to 13 %, leaving mostly 2nd harmonic, as players describe it. Figures in `docs/guide/germanium-study.md` section 5; the acceptance files list it under `omitted`.
- **The starter keeps its bias target**: inside Aion's Q2 reading; moving it to the 3:00 start would leave Q2 outside it. The how-to says where the clean-up is.
- **THD alone misleads here**: it counts the 2nd harmonic, which grows as the fuzz goes. The study splits h2 from the 3rd-8th.
*Alternatives:* TR1 at its 3:00 start with no target (Q2 outside Aion's reading); a less leaky Q1 (outside the middle of Aion's range).

**D-213 — The starters to ship, and Aion FX as the source where it has a clone** `library`
- **New starters**: Aion's Big Muff (the Halo) beside the V3, with its voice switch and a text block listing each Big Muff version's swaps; the Boss BD-2, the Klon Centaur, the Marshall Bluesbreaker, the MXR Dyna Comp and the Boss DS-1. The existing starters stay.
- **Aion FX's schematic is the source wherever Aion has a clone**, with the differences from the original in the acceptance file's `substitutions`. Other published figures (ElectroSmash's) are checks where values match. Aion's licence allows building, commercially too, and its parts lists give every capacitor's type (D-211). (Originals beside them: D-239.)
- **16 V kept** for the TS808's C16 and C17 (10 V parts run close to an unregulated adapter's 9.6-12 V; same sound). **Film kept** for 1 µF non-polarised caps.
- **The Tone Bender MkII starter stays** (D-212): stable at every level and inside Aion's readings.
*Alternatives:* replacing the V3 with the Halo; ElectroSmash's circuits throughout (some figures under a non-commercial licence).

**D-214 — The Halo Big Muff starter, and a starter with no figure to check** `library`
Aion's Halo document gives schematic, parts list and versions sheet but no voltages, gains or frequencies; ElectroSmash's figures are for the V3's values.
- **`big-muff-halo`**: Aion's refs (its RPD drawn as R1), the Gilmour '73 Ram's Head values of its parts list (C10 3n9), the supply filter (D1, R24, C14, C15 to VA), and the Midrange switch as the DPDT on-on-on closing Aion's lugs per position (Mid scoop, Flat mids, Mid hump). No bypass board.
- **Two text blocks** list each of the sheet's 20 versions' differences.
- **The switch's floating caps stay** (Missing pull-down listed in `corpus_warnings.yaml`), as Aion fits no pull-downs there.
- **No checks.** ElectroSmash's "never exceed ± 0.6V" doesn't carry over (the Halo's diodes are in series with 100 nF, the V3's with 1 µF); it's in `omitted` with the reason. **A starter copied from its source's schematic may ship with no checks** (the user's rule); the how-to says so.
*Alternatives:* checking the V3's figures with V3 values set on the Halo (tests the V3 again); corners from 1/(2πRC) (not a published figure, D-019).

**D-215 — The BD-2 starter (Aion's Sapphire), checked against Aion's prototype voltages** (now the Aion version beside the original: D-239, D-256) `library`
Aion's BD-2 clone is the Sapphire; its kit document gives every transistor and IC pin's voltage on Aion's prototype at 9.6 V, ±0.5 V being its own line for a fault.
- **`boss-bd2`** as Aion draws it: Aion's refs (RPD as R35), Bass at 0, Drive the original's 250kA with R9 and R20 left out, as Aion says for that pot. Drive is a dual-gang pot (D-217). JFETs the 2SK209-GR (D-216).
- **Twelve DC checks at 9.6 V with Aion's ±0.5 V**, on nodes a meter doesn't load (VA, VB, JFET sources and drains, the stage outputs, Q8/Q9 emitters). All within 0.15 V. Gates and bases fed through 100k-1M are left out: a 10 MΩ meter reads 4.31 V through 1M as 3.92 V, Aion's 3.93.
- **Acceptance checks take `supply`** (V+ for that check), so a source measured on 9.6 V is checked at 9.6 V.
*Alternatives:* checks relative to VA or VB at 9 V (further from the published numbers).

**D-216 — The 2SK209-GR, our own level-1 card** `models`
Toshiba's sheet (2014-03-01) gives the grades' Idss ranges, VGS(OFF) -0.2 to -1.5 V, and typical curves.
- **`2SK209-GR`** (`J2SK209GR`), level-1 as D-161: Idss 4.11 mA, the geometric middle of GR's 2.6-6.5 mA; Vp -0.487 V from the typical |Yfs|-IDSS line (16.9 mS) by the square law, Vp = -2·Idss/|Yfs|, borne out by the ID-VGS family. LAMBDA 0.006 from ID-VDS; CGS 10 pF, CGD 3 pF from Ciss and Crss. SC-59, 1 source, 2 drain, 3 gate.
- **The VGS(OFF)-IDSS line is not used for Vp**: it's read at 0.1 µA, in the tail where JFETs leave the square law; fitted to it, the BD-2's sources sat 0.1-0.2 V high.
- Checks: Idss 4.36 mA at 10 V, cut-off -0.485 V. In the BD-2 the sources read 4.62-4.65 V against Aion's 4.62-4.65 V. Scripts in `.claude/skills/fit-model/worked/2sk209/`.
*Alternatives:* the J201 card with measured figures (0.27 V high at the sources); Vp from the VGS(OFF) line.

**D-217 — Dual-gang pots (schema v24)** `schema`
- **A dual pot is a part per gang**, as a switch's poles (D-143): `gang` a or b, refs VR1A and VR1B, each placed and wired on its own. Both share value, taper, rotation and label (the file is refused otherwise). Two gangs only.
- **One knob, VR1**, turns both: the view lists one pot control with `refs`; `Circuit.with_part("VR1")` changes both and `Circuit.part("VR1")` gives gang A (`Circuit.units` lists what a control turns, switch poles too). Slider, ranges, sweeps, the audio pot sweep and the bias sheet take the pot's name as a single pot's ref.
- **The editor**: the pot form's Gangs (Single, Dual). Dual adds gang B 80 to the right; Single takes it away. Setting, deleting, renaming or pasting one takes both (the switch-pole code, `unitKey`). Hovering the knob lights both.
- **Parts list**: one line ("A250k", "log (A), dual gang"); one knob.
- Schema v24 only adds `gang`.
*Alternatives:* one symbol with a `gangs` count (the gangs sit in different stages); two pots linked by label (they can drift apart).

**D-218 — The Klon starter (Aion's Refractor), and a charge pump wired as both (schema v25)** (now the Aion version beside the original: D-239, D-244; pump wiring: D-226) `schema` `library`
- **A charge pump's `mode` may be `both`**: 2 × in on `out` (through the doubler's diodes) and −in on a fourth pin, `neg`; one oscillator and quiescent current. The symbol shows 2× and −1×. One part, so one LT1054 in the parts list. (The Klon's LT1054 doubles VA to VB and inverts to −VA at once.)
- **The LT1054 card has its package**: 8-pin DIP, in 8, gnd 3, neg 5 (TI SLVS033G).
- **`klon-centaur`** (Aion's Refractor): IC1's halves named by their pins (our IC1A is pins 1-3), so the bias sheet reads as Aion's table. C16 drawn as film where Aion fits tantalum (it simulates the same; the build notes say so). Seven DC checks at 9.86 V with Aion's ±0.5 V.
- **The mutation test's singular-matrix check counts only warnings naming a circuit node** (a model's inner nodes going singular isn't a floating net; another rule catches it).
- Removing R12 or R20 showed a missing rule (D-220).
*Alternatives:* two pump parts (two LT1054s in the parts list).

**D-219 — The TL071, TL072 and TL074 as our own cards from TI's sheet** `models`
TI's 1989 TL072 macromodel has RP 2.143 kΩ across the supplies, drawing 12.6 mA a channel at 27 V against the sheet's 1.4 mA; the Klon's IC2 loaded the pump nine times too hard (VB 17.63 V against Aion's 17.99).
- **One TL07xC channel, `opamp_card` (D-162), from SLOS080W 5.8 and 5.9 at ±15 V**: AOL 200 V/mV, GBW 3 MHz (the classic die; newer dies 5.25 MHz), 20 V/µs, phase margin 56°, ZO 125 Ω, clamps 1.33 V from each rail, **1.4 mA a channel**. Built by `.claude/skills/fit-model/tools/fit_opamps.py`; all checks pass. Klon: every check within 0.1 V.
- **Tests**: TI's 1989 file is kept as `tests/fixtures/models/TL072_TI_1989.lib` for the Add a model tests (a maker's file as a user adds it). Op-amp pump blocks' ripple and frequency are measured over the last 20 cycles, and `strongest()` removes a straight-line drift, not only the mean.
*Alternatives:* raising the old card's RP only (TI's card with a fix in it); the new die's 5.25 MHz (most pedal TL072s are the classic die).

**D-220 — A rule for an op-amp whose feedback is only capacitors** `rules`
With only a cap from output to − input there's no DC feedback: a real chip's offset times its open-loop gain rails it. The sim's op-amps have no offset, so it showed the output calmly at mid-supply.
- **`opamp-no-dc-feedback`, error, topology**: a signal path from output to − input but none once capacitors are left out (resistors, pots, trimmers, closed switches, inductors, diodes, transistors and other op-amps count; supplies, ground and AC-grounded bias nets block). Never fires with `opamp-no-feedback`, so a stage is reported once. The message says what it needs; the why that the sim can't show the fault; the fix the usual values (100k to 1M). (Wording: D-247, D-295.)
- `graph.signal_edges` gained `dc=True` rather than a second walker.
- Checked by its bad fixture, the known-good corpus and the mutation tester.
*Alternatives:* a warning (the stage doesn't work on a real chip); modelling offset so the sim rails it (every card needs a sheet's offset, and the sign is a coin toss).

**D-221 — A 1N4742A card; the Klon's Z1 drawn; a diode's ref may be Z** `models`
- **1N4742A**: Diodes Incorporated's card from the pinned KiCad-Spice-Library `zener.lib`, as the 1N4738A and 1N4739A; Vishay's 1N4728A-1N4761A sheet: VZ 12 V at IZT 21 mA, ±5 %; simulated 12.02 V. DO-41.
- **A diode's ref may be Z** as well as D (`refs.PREFIXES`), as on most schematics (D-229).
- **The Klon draws Z1** (12 V across VA, protecting the charge pump), with a part note on its job.
*Alternatives:* naming it D5 (not the kit's ref).

**D-222 — Pump switching is a choice in audio renders, off by default** `power` `audio`
With a charge pump the transient's step is capped at 1/20 of a pump cycle (D-093): 2 s of audio took 49.5 s on the Klon, 4.5 s without the switching.
- The Audio pane's Pedal drawer has a **Charge pump switching** box, shown only with a pump, **off by default** (kept for troubleshooting noise). Off, each pump delivers its average current and sets no step cap; on, it switches. `Tran.pump_ripple` (default True, so the Scope keeps the ripple), `Inputs.pump_ripple` and the render request's `pump_ripple` (default False). Part of a take's sources. On the Klon the two takes differ by −94 dB.
*Alternatives:* always off (a pump's whine matters when chasing noise); a coarser step cap (still slow, and the ripple aliases).

**D-223 — A gain slider is spread by what reaches the next block** `panes`
On the BD-2, Q4's R12 runs from the collector into the clipping diodes: a bigger R12 loads the stage less (+4.0 dB own gain) and passes less to the diodes (−10.9 dB). The slider showed only the first (D-123).
- Each gain step also measures the level where the **next row takes the signal** (`fixes._after`: the next row's input, a clipper to ground's node, or the amp's input). The slider is spread and sorted by that (`gain_db`); the stage's own change is `own_db`. A step's text names both when they differ by 1 dB or more. The slider's end label reads "into D2, D3, D4, D5" (`into`). Parts are ranked by whichever a +10 % nudge moves more.
*Alternatives:* leaving such parts out of Find parts (R12 does set how hard the diodes are hit); measuring at the pedal's output (a clipper after it flattens the change).

**D-224 — A discrete op-amp is one stage; a buffer driving a bias net isn't a stage** `panes`
- **Detected** (`stages.discrete_opamps`): two transistors of the same type and model whose emitters or sources share a net that isn't quiet (the pair); a third whose base or gate is on one pair member's collector or drain (that member is the + input); a passive path from the third's output back to the other member's input. No feedback, no op-amp.
- **One stage**: `Stage.inputs` holds its + and − nets; refs output first, labelled in signal order ("Q2, Q3, Q4"), role "discrete op-amp". Measured from its + input; pots in its feedback sit on its block. The BD-2's Q4 now offers C3, R12, VR1B and R8.
- **Drawn as a box**: a double outline with each transistor's job inside (+ in, − in, out); its card explains a discrete op-amp; the ⓘ key has a row.
- **A stage whose output is a quiet net is no stage**: `_stages` checks outputs against `quiet_nets`, not only supplies (the BD-2's IC1A buffering VB was a row).
*Alternatives:* three stages with a box drawn round them (the pair's swing alone means nothing to a player; the gain parts would still be wrong).

**D-225 — Every net that carries power or a bias reference draws as a supply, its name in rose** `power`
- A label draws as a supply bar (the T) when its net is a supply (`rail_nets`: the Power menu's rails, a chip's supply pins, a pump's output) **or a bias reference**: a net a big cap (≥ `AC_GROUND_FARADS`) holds to a supply or ground (`graph.ac_grounds`), such as VREF. The view's nets gain `bias`. Supply bar names take `--sch-supply` (rose on screen, darker on paper), apart from the error colour. Supply bars turn with Space (D-117).
- *Limits*: a divider with no cap to ground looks like a signal net, so its label stays plain.
*Alternatives:* a different symbol for a reference (same T wanted); the error red (a supply would read as a problem).

**D-226 — A charge pump's caps and diodes are drawn parts; old circuits are migrated (schema v26)** `schema` `power`
The schematic should be as realistic as possible: a pump that doesn't work without its parts needs them on the drawing.
- **The chip** draws as the datasheets' numbered 8-pin box (1-4 down the left, 8-5 up the right). Wired pins: `in` (V+, 8), `cap+` (2), `gnd` (3), `cap-` (4), `out` (VOUT, 5); pins 1, 6, 7 drawn (wiring: D-234). `mode`, `neg` and `diode` are gone: **the wiring says what it does** (`solum/circuit/pump.py`, the one owner): a flying cap from CAP+ to CAP- makes an inverter onto VOUT; a cap from CAP+ to a junction with D1 (anode on V+) and D2 (to the output) makes a doubler; both together is the Klon's. A pump missing a part raises a plain error naming it; a chip with nothing wired says how to wire it.
- **Simulation stays averaged** (D-093; a switched model has no DC steady state), fed by the drawn parts. The doubler's charge enters the junction through a copy of the drawn D1's model; the drawn D1 then sits reverse-biased. Output resistance per path: `r_out - 1/(f·c_pump) + 1/(f·C_drawn)` (`netlist.pump_resistance`), with each chip's sheet cap as `c_pump`: TC1044S 10 µF (the text and Figure 3; Figure 1's 1 µF can't give its 60 Ω), ICL7660 10 µF, LT1054 100 µF. CAP+ and CAP- are held at their averages (half V+, half VOUT, through 2 GΩ dividers), as a meter reads them.
- **Known gaps of the averaged model**: the drawn D1 is reversed by about V+ all the time (a real one half of each cycle), so a leaky Schottky's reverse current shows (a 1N5817 doubler unloaded reads 17.95 V). A doubler's pump cap reads about 1.5 × V+ across (real: about V+), so cap-over-voltage could warn early.
- **Rules and views**: a pump's outputs and its own nets (CAP+, CAP-, the junction) are supply nets; pump-no-reservoir checks each output; bias paths run through the pump to the nets it drives.
- **Migration** (`_v25_to_v26`): each pump redrawn at the nearest clear spot with its sheet's cap and its old `diode` as D1, D2, joined to its old nets by labels (an unlabelled net gets one named after the old pin, `U1_OUT`); probes and bias targets follow. Blocks (18 V, −9 V, both, 12 V) save remembering the parts. Rule fixtures may write a pump as `{type: chargepump, supply: V+, double: V18}` (`CircuitBuilder.pump`).
*Alternatives:* a legacy "parts inside" mode (not realistic); a literal switched model (the operating point breaks).

**D-227 — A fixed regulator part (78L12) and the power blocks** `power`
- **Part `regulator`** (schema v27, no migration): pins `in`, `gnd`, `out`, drawn as KiCad's Regulator_Linear box with the model's package numbers; ref IC or U; palette "Regulator" under Signal & power.
- **A behavioural model, as the charge pumps' (D-093)**: `library/models/regulator/78L12.json` holds onsemi MC78L00A/D Rev. 21's typical MC78L12A figures (`v_out` 12 V at `v_in_ref` 19 V, `line` 0.0096 V/V, `r_out` 0.202 Ω, `v_dropout` 1.7 V, `i_bias` 4.2 mA; `vi_max` 35 V; TO-92 out 1, gnd 2, in 3). Netlist (`_regulator`): a B source at min(held, in − dropout), floored at 0 V, corners rounded over 0.1 V (`REG_SMOOTH`, an overflow-free soft min), behind `r_out`; the input draws the output current plus `i_bias`. Input ripple passes at `line` at every frequency (the sheet's 42 dB at 120 Hz agrees within 2 dB).
- **Not modelled** (said in the record's note): current limit and thermal shutdown (no figures), ripple rejection falling at high frequency, sinking current.
- **Rules**: `regulator-input-over-max` (error) and `regulator-dropout` (warning; a 78L12 on 9 V is the case it catches).
- Its output is a bias anchor and supply net; it's in the BOM, on the bias sheet and in Parts and datasheets ("Regulators").
- **Blocks**: `charge-pump-both-chip` (LT1054 doubling and inverting; 1N5817s, where the Klon has 1N4001s: said in the description), `charge-pump-12v-zener` (TC1044S doubler, 1k and a 1N4742A: holds 11.85-11.96 V up to a 5 mA load), `regulator-12v` (doubler, 78L12, 0.33 µF in and 0.1 µF out as onsemi's Figure 2: 11.98 V from no load to 10 mA).
- **Against a maker's model**: onsemi publishes none for the MC78L12A. TI's behavioural PSpice model of the 5 V uA78L (SLVME11), re-divided to 12 V, matched the output but has the 5 V part's regulation and rejection and no bias current (which matters on a charge pump). It has load-dependent dropout, frequency-dependent rejection and a current limit, which ours lacks; ours kept.
*Alternatives:* a maker's SPICE model (transistor-level or encrypted; PSpice mode needed); a DC source on its own net (D-091: no dropout, bias current or BOM line).

**D-228 — The Klon's bypass board drawn; two Klon starters; a switch's spare pole** `library`
- **The standard bypass block** is `true-bypass-3pdt-v1` (3PDT, LED, input grounded when bypassed). No jacks: drawing-only (D-174).
- **Two starters**: the effect and its power alone, and "with footswitch" (`-built`), a fully built schematic: Aion's TRUE BYPASS / BUFFER SLIDE SWITCH and the buffered output (C2 4.7µ, R3 100k, R4 560R off the input buffer); SW1 a 3PDT on-on (Aion fits a 4PDT slide with one pole unused; a 3PDT wires the same), Bypass mode Buffered (default, the original's) or True bypass; SW2 the 3PDT footswitch, lighting LED1 through its LEDR as every 3PDT board does. Our footswitch's lug 1 is On, so Aion's A1/A3 and C1/C3 trade names (said in a note). The board joins the circuit by labels `pcb-in`, `buffer-out`, `effect-out`, `bypass`. Both carry Aion's DC checks.
- **Block `klon-bypass-v1`**: the same board, ports in, send, buffer, return, out.
- **D.SW is dropped**: Aion marks the clip node D.SW and takes it to a pad, but no document says what it joins, and the circuit matches Aion's voltages without it.
- **R27**: see D-233 and D-248.
- **A switch's spare pole** (`connectivity.spare_poles`): a pole with no lug wired while another pole of the switch is. It stays out of the simulation (loose, D-165) but `part-not-simulated` doesn't name it: an unused pole of a bought switch isn't a fault. Every pole must still be drawn (D-143).
- *Limit*: `switch-pulldown-missing` looks only at a net with a capacitor on the switch itself, so removing the Klon's RPD (with R1 between the footswitch and C1) goes unnoticed (mutation gap).

**D-229 — A zener draws as one and is named Z** `editor`
- **What a zener is**: a diode model whose record checks a zener voltage (a `vz` validation). No new field; Add a model's check gives one (D-155). `Model.zener`; `/api/models` lists their ids under `zeners`.
- **The symbol** follows KiCad 9's `Device:D_Zener`: the plain diode with only the cathode bar's top end bent back toward the anode. The view's `draw.zener` carries it, as `draw.depletion` does (D-178).
- **The ref follows the model** when a diode's model changes and its ref was left as it was (`diodeRef`): D1 set to a zener becomes the next free Z, Z1 set to a plain diode the next free D. A typed ref wins. Refs stay free to be D or Z (D-221), so old files and mod guides writing D5 for a zener keep working.
*Alternatives:* a `zener: true` field (a second thing to keep in step with `vz`); a rule warning about a zener named D.

**D-230 — Symbols compared with KiCad 9's: the LED changes, the rest stays** `editor`
- **LED: KiCad's.** The two arrows under the body, right of the cathode bar, pointing down toward K, with open heads (`Device:LED`, mirrored: ours has A on the left).
- **Kept**: the BJT's diagonal leads (changing it moves every transistor's pins); our ground (three bars, KiCad's Earth) and rail bar, as Aion and most pedal schematics draw them; the LM308's compensation pins both at the top (KiCad would split the Rat's 30 pF cap across the chip, which most Rat schematics draw over the top).
- A single op-amp's offset pins are at the bottom beside V−, as in KiCad's TL071.

**D-231 — A toggle, slide or footswitch pole draws in a box, as KiCad's; a rotary doesn't** `editor`
Every non-rotary pole draws as KiCad 9's `SW_SPDT_x2` unit: a box (30 wide, 8 beyond the outer contacts), contacts inside at x ±10, a lead to each lug, the arm from the common to the closed contact. Lugs unchanged (common x −20, throws x 20), so no circuit moves; lug names over the leads outside the box. A rotary keeps its arc and has no box.
*Alternatives:* the box on the rotary too (ours reads better); a box around the whole pole with contacts at the lugs (no room for KiCad's leads).

**D-232 — A resistor may be RPD or LEDR, numbered** `editor`
`refs.PREFIXES["resistor"]` is R, RPD or LEDR, each numbered like every ref (RPD1, LEDR1, LEDR2). Nothing is renamed automatically: spotting a pull-down is guesswork (a JFET buffer's 1M gate resistor sits in the same place). A new resistor is still R. The library uses them where Aion does (RPD1 for the input pull-down, LEDR1 for the LED's resistor in bypass blocks). SPICE reads an element by its first letter, so LEDR1 goes out as `R_LEDR1` (`element_name`). Trimmers stay TR, pots VR.
*Alternatives:* bare RPD and LEDR (one per circuit, sorting differently); automatic LEDR for a resistor in series with an LED (overcomplicating).

**D-233 — The Klon's R27 left out** — superseded by D-248: R27 is back, as Aion draws it. `library`

**D-234 — A charge pump's boost is wired, pin 1 on V+ (schema v28)** `schema` `power`
A schematic is useless for building if parts or wiring are only in notes.
- Pins 1, 6 and 7 can be wired or left open (no problem either way; `pump.SPARE_PINS`). **Pin 1 wired to the chip's V+ is boost**, as on a real board (`PumpWiring.boost`): on a TC1044S the oscillator runs at its boost rate; on an LT1054 (FB/SHDN held high) or an ICL7660 (no-connect) it changes nothing. The `boost` field is gone: `_v27_to_v28` labels a boosted pump's pin 1 with its V+ net (pin 8's label, or a new `U1_IN`). The pump form says how to wire boost; a new pump has pin 1 open. Pins 6 and 7 aren't simulated (LV, OSC, VREF: no listed pedal uses them); an open pin is left off the part card.
- Both Klon starters draw pin 1 to V+ (VA).
*Alternatives:* keeping `boost` and checking it against the wiring (two sources of truth); drawing each chip's own names for pins 1, 6, 7 (they differ by chip; the box shows numbers).

**D-235 — The Boss DS-1 starter, from Aion's Comet, checked against ElectroSmash** (now the Aion version, `-aion`, beside the original: D-239, D-243) `library`
- Drawn from the Comet's schematic (netlist checked against Aion's before writing): Aion's pre-1994 values (C5 470n, C6 250p, C7 1µ), its Mode switch (SPDT on-off-on: Diodes, LEDs, Two diodes; drawn at Diodes, the stock DS-1), D4 as Aion's default, the "OMIT" parts left out, a parts-to-try block in our words. Substitutes: 2N5088 (Aion's), the NJM3404AD as the LM358 card (Aion: the DS-1's chips "are related to the LM358"; later: D-252), red LEDs as APT1608SURCK. C3 (Aion's X5F ceramic) drawn C0G (simulates the same).
- **Checks** are ElectroSmash's figures only where its parts match Aion's: VB, the input high-pass (7.2 Hz), the booster's 35 dB, the op-amp stage's 26.5 dB at full Distortion, the clipping at ±0.7 V. Three are known gaps with the working: Q2's collector (5.8 V on the page, 3.96 V by hand and in the sim); the R12/C9 treble cut (7.2 kHz alone, 4.9 kHz with the tone stack loading the node); the tone notch ("around 500Hz" on the page, 681 Hz by hand, 692 Hz in the sim).
*Alternatives:* ElectroSmash's post-1994 values (Aion is the source where it has a clone, D-213); an NJM3404 card (no sheet in hand then).

**D-236 — The MXR Dyna Comp starter, from Aion's Aurora, checked against its kit's voltages; a spare OTA may be left open** (now the Aion version, `-aion`: D-239) `library`
- Drawn from the Aurora's schematic (LM13700; netlist checked): Aion's default parts with its Q6 output buffer, Release pot (250kC ∥ 390k; "Attack" on the schematic), C17 and Treble switch at Stock; "Omit" parts left out. C11 820p and C12 330p as the schematic labels them (the parts list swaps them; the build notes agree with the schematic). Input trimmer TR1, Sustain VR1, Release VR2, Level VR3. ElectroSmash's analysis is of the stock CA3080 circuit, so none of its figures apply.
- **Checks**: eleven of the kit's readings at 9.6 V with Sustain up and Release down, Aion's ±0.5 V (D-215); the kit's PCB uses the chip's other OTA, so its pins 12 and 16 are read as IC1A's output and iabc. Left out with the working: Q1's base (fed through 940k: a 10 MΩ meter loads it), pins 13-14 ("falling"), pin 15 (open). The OTA output simulates 0.5 V above the kit's reading: the prototype's OTA offset (about 0.8 mV, inside TI's 4 mV max) times its gm, which a card with no offset can't have.
- **A spare OTA isn't a problem**: `unconnected-pin` doesn't report an OTA whose output and iabc are both open (with no bias current it's off, as the datasheets and Aion leave the unused half). One with only one of them open is still reported.
- **Mutations treat every chip unit type as a chip** (op-amps, OTAs, inverters).
*Alternatives:* ElectroSmash's analysis as source (not the Aurora's circuit); the stock output from Q2's emitter (Aion's default is the Q6 buffer).

**D-237 — The Marshall Bluesbreaker starter, from Aion's Cerulean, checked against its kit's voltages** (now the Aion version: D-239, D-257) `library`
- Aion's Cerulean (TL072) adds a Clipping switch (soft, the stock; none; hard), a Mode switch between pre- and post-1995 values, and an internal 2-position DIP shifting Drive's range. Drawn at Clipping Soft, Mode V1, DIP at Normal (the stock circuit), plus Aion's recommended C6. Drive VR1, Tone VR2, Volume VR3; Clipping SW1 (DPDT on-off-on: Soft, Boost, Hard), Mode SW2 (DPDT), Gain DIP SW3 (`dip-2`, D-238), positions named from Aion's figure.
- **Checks**: six of the kit's eight pin readings at 9.6 V, ±0.5 V; pin 3 (a 10 MΩ meter through 1M) left out with that working. Every checked pin within 0.08 V.
- **The OTA cards draw no quiescent current unpowered**: with V+ lifted, the card's fixed quiescent current had no source and ngspice spun past the timeout, wedging the process (D-195, D-279). Both cards' `Bq` now fades out as V+ falls to V− (no figure changes at 9 V). Test in `tests/sim/test_chip_units.py`.
- **The mutation test compares problems by rule and parts**, not rule alone (a circuit already raising `bjt-cut-off` at rest hid a mutation cutting off another transistor).
*Alternatives:* leaving the DIP out (Aion's Medium and High are part of the project); a 1P3T for the gain settings (not the fitted part; wouldn't follow the DIP's override).

**D-238 — A transistor off by design; DIP switches; OTA, unpowered-chip and supply-sag rules** `rules`
- **`off_by_design`** (schema v29, add-only) on a BJT, JFET or MOSFET: off at rest on purpose (a rectifier or a switch). `saturation()` (the one owner) skips "cut off" for it, so neither the cut-off rules nor the Frequency panel's doubt fire; saturated still does. The part form asks *At rest*: on, amplifying, or off by design. The Dyna Comp's envelope rectifiers Q3, Q4 are marked. A dismissal couldn't do this: it doesn't clear the Frequency panel's doubt, and it says "I accept this" rather than "this is how it works".
- **DIP switches**: `dip-2` and `dip-3`, group DIP, on the board in the parts list. A DIP's switches are independent, but the app's multi-pole switch shares one position (D-143), so a DIP of N switches is one N-pole switch whose positions are every combination (All off, 1 on, 2 on, 1 and 2 on…): Knobs, drawing, export and netlist work unchanged. `dip-4` would need 16 positions, over the 12 allowed: waits until needed.
- **Rules** (the book kept at its limit by extending rules): `opamp-railed` and `opamp-input-common-mode` cover OTAs too, with the LM13700's and CA3080's common-mode range from their sheets (3 V from each rail); a spare OTA (`chips.spare_ota`, shared with `unconnected-pin`) is skipped. `opamp-supply-missing` ("Chip not powered") also fires on a chip power pin wired to nothing or only to other chips' power pins, and such a circuit never reaches ngspice. **`supply-sags`** (new, warning): every net on a rail's way in, through diodes, inductors and resistors of 1 kΩ or less, holds at least half the rail, so a reversed protection diode shows on a circuit without op-amps.
*Alternatives:* a "fully on by design" flag (no circuit needs it); independent DIP poles (every multi-pole path would change for one part); separate `ota-*` rules (same physics); a sag threshold in volts (9 V and 18 V would need different ones).

**D-239 — Originals beside the Aion starters; Aion's text rewritten** (2026-11-10) `library`
Every starter drawn from an Aion project that differs from the original (BD-2, DS-1, Dyna Comp, Bluesbreaker, Klon, the Tone Bender's Mode version) is named "(Aion <project>)", its id gaining `-aion`; the original takes the plain id and name and is drawn from a published, cited source (ElectroSmash or the maker's schematic), never from memory. Originals have their own buffers but no footswitch logic. Original parts with no card are fitted from their datasheets where found, else the nearest card stands in, written in `substitutions`. Aion's licence lets projects be built and sold, but its documents' content is copyrighted: the Aion starters' notes are in our words and credit Aion FX with a link (D-246).
*Alternatives:* keeping the current ids for the Aion versions; fitting no new cards.

**D-240 — Cancelling a render** (2026-11-10) `audio`
- While a render runs, Render reads "Cancel render" and Render sweep "Cancel sweep" (both words in the button, one invisible, so nothing moves: D-134); pressing it posts `POST /api/render/{id}/cancel` for each of its jobs.
- `RenderJobs.cancel`: a job not yet handed to a worker is dropped; a running one is told by a **flag file** (`CACHE_DIR/cancelled/<job id>`) checked at each progress report (every 0.2 s) and before caching; the progress callback raises, and `NativeNgspice` halts its run and re-raises (`bg_halt`). A job still running `KILL_AFTER` (5 s) later (a step with no progress reports) has its pool's workers killed (D-040); the pool's other jobs restart on a new one, not failed.
- A cancelled render caches no take; the pedal's simulated output may already be cached, and is correct.
*Alternatives:* a `multiprocessing.Manager` dict or shared array (an extra process, or fixed slots, for what a file does); killing the pool at once (fails every other job on it); `Future.cancel` alone (can't stop a running job).

**D-241 — The Impedance overlay says what the loading does** (2026-11-10) `panes`
The pedal's Zin doesn't depend on the guitar, so switching pickups left the overlay unchanged while saying nothing about loading.
- `impedance_view` adds, at 1 kHz: on the input, the guitar's own source impedance (pickup, volume pot and cable, pedal left out: `guitar_into`), the level at the pedal's input against the guitar unloaded (`20·log10|Zin/(Zs+Zin)|`, complex, so it can rise: a single coil's inductance and a small input cap resonate), and the pickup's resonant peak into the amp and into the pedal (a peak over its 100 Hz level in 500 Hz-20 kHz; under 0.5 dB, "no peak, 3 dB down at …"); on the output, the amp's input impedance, the level it gets, and the pots Zout follows (on the output net or one part from it).
- Drawn: "Zin 33.7 kΩ · +3.1 dB", for a pickup "Resonance 1.23 kHz, +3.7 dB" under it, and "Zout 18.6 kΩ · −0.1 dB"; the rest in the mouse-over (D-249). The resonance line is drawn because the 1 kHz figure barely tells pickups apart while the loaded peak moves a lot.
*Alternatives:* level lost clamped at 0 dB (hides the resonance boost); loss against the guitar straight into the amp (harder to explain); resonance only in the mouse-over.

**D-242 — A pump's power input drawn with a wire, and a note instead of a cap** (2026-11-10) `power`
- V+ labels on a charge pump's pins and an op-amp oscillator's V+ pin sit 20 up on a short wire, so the pin doesn't look unconnected.
- **No input cap inside the blocks**: most pedals already have a bulk cap on V+, and `supply-no-bulk` fires exactly when one is missing. Each pump block's chip note says where pin 8's supply comes from, why the pulses want a bulk cap on V+ (10-100 µF, the Input filter block), that one is enough, and that the warning says when it's missing.
*Alternatives:* a 10 µF cap at pin 8 in every block (a second cap most pedals don't need, hiding the warning where it matters).

**D-243 — The original Boss DS-1, from ElectroSmash** (2026-11-10) `library`
`boss-ds1` is drawn from ElectroSmash's DS-1A (post-1994) schematic with its part numbers, true bypass (Boss's JFET switching left out, D-239), D1 as the board's supply shunt. 1N4001 for the 1N4004. (2SC2240 and NJM3404A cards: D-252.) The treble-cut and tone-notch gaps are the page's, as in the Aion version (D-235).
*Alternatives:* cards from datasheets recalled from memory (D-019).

**D-244 — The original Klon Centaur, from ElectroSmash, and a MAX1044 card** (2026-11-10) `library`
- `klon-centaur` is laid out on the Aion drawing and checked net by net against ElectroSmash's schematic (same part numbers). It differs from Aion's: R2 1M and no RPD, D2/D3 1N34A germaniums, a MAX1044 with 1 µF pump caps, the zener across the supply, and the buffered bypass path (C2, R3, R4) with R243 and R28 always connected. SW1 drawn at effect on, so R242 (shorted then) isn't drawn. Op-amp halves named as ElectroSmash's (U1A, pins 1-3, the input buffer).
- **The MAX1044 card** is ours, from Maxim's sheet (archived copy): table figures where given, boost frequency and current read off its figures, flagged as such.
- **Checks**: the gain stage's 40 dB, the treble shelf's +18.2/−8 dB and unity pass band, the 1N34A clipping pass; the input, feed-forward and output corners are known gaps, each traced to one part (C18, R19, the R243 bleed). Supplies: D-250.
*Alternatives:* drawing it from scratch (same nets); the TC1044S card (the text says TC1044, the schematic MAX1044; the schematic wins).

**D-245 — The original MXR Dyna Comp, from ElectroSmash; a single OTA no longer crashes the rules** (2026-11-10) `rules` `library`
- `mxr-dyna-comp` from ElectroSmash's schematic and stock values (CA3080), its Rtrimmer as TR1 at its middle as the page says, RV1/RV2 as VR1/VR2. Pot tapers B for both, as Aion's Aurora document gives the stock values (cited). Sensitivity counts as a gain knob in the knob test.
- **Checks**: VB, Q2's bias, the resting envelope, the OTA inputs' 1 dB and 4 dB difference and the output corner pass; the OTA's input bias, the input corner and the phase splitter's gain of 1 are known gaps, each the page's own simplification, worked by hand in the file.
- **Bug found**: the rules asked every OTA for its buffer's output pin, which only an LM13700 half has; `graph.bias_anchors` skips pins a part doesn't have.
- Its first run is slow (about 8 s: Q1 clips at a hard pick, so long time constants take the full settling search); the test opening every starter waits up to 40 s.
*Alternatives:* the long-tailed-pair form of the envelope detector (same circuit; the page's numbers follow its form).

**D-246 — Aion's text on the Aion starters in our own words, with a credit** (2026-11-10) `library`
Build-notes blocks are rewritten in our wording, titled "Parts to try (ideas from Aion FX's <project> notes)"; the facts stay. The Big Muff versions table keeps its rows under a reworded intro. Every Aion-based starter gets a "Credit" text block naming the project and document version and linking its project page on aionfx.com (the page, not the PDF, which changes with each version). Part notes were already ours. Starters drawn from ElectroSmash credit it in their Source notes.
*Alternatives:* a credit field in the circuit file (a schema change for what a text block shows on the sheet and PDF).

**D-247 — A path through another op-amp's output isn't DC feedback** (2026-11-10) `rules`
With the Klon's R24 removed, `opamp-no-dc-feedback` saw a resistor path from U2B's output to its − input through U2A's output, which U2A holds itself. The feedback search now follows edges one way around every other op-amp's output: it may reach it through the op-amp and leave through parts, but not enter through a part (`graph.one_way_outputs`, `reachable(directed=True)`). A servo (DC feedback through a second op-amp) still counts. Fixtures: the R24 shape (bad) and a servo (good).
*Alternatives:* blocking other op-amps' outputs outright (would flag a servo).

**D-248 — The Klon's R27 back, as Aion draws it** (2026-11-10) `library`
The original Klon keeps ElectroSmash's R243, the same 68k in the same place as Aion's R27; Aion's switching puts its leak in Buffered bypass rather than in the effect. To be true to the schematics, R27 is back in the Aion Klon with footswitch and the `klon-bypass-v1` block; notes say what it does. Bypassed in Buffered the output is within 1 dB of the input and moves a little with Gain (`test_the_klons_buffered_bypass_lets_a_little_effect_through`); True bypass stays exact. Supersedes D-233.
*Alternatives:* keeping it out (departs from both sources).

**D-249 — The impedance overlay's mouse-over, figures only** (2026-11-10) `panes`
One line per figure, a label and its value: *Input impedance: 33.7 kΩ at 1 kHz*, *Guitar source*, *Level*, *Resonance: … into the amp (1 MΩ), … into the pedal*; for the output *Output impedance*, *Amp input*, *Level*, *Changes with VR1 (Volume)*. A buffered guitar gets no resonance line. The drawn lines are unchanged (D-241).

**D-250 — The original Klon's supplies checked against a replica's measured chart** (2026-11-10) `library`
ElectroSmash's "+16.2V" and "−8.6V" are image readings, so not used as checks. General Guitar Gadgets' Klon Centaur Replica instructions print a voltage chart at a 9.4 V supply (IC2 pin 8 17.1 V, pin 4 −9.1 V): two `dc` checks at `supply: 9.4` with ±0.5 V; both pass. The image readings stay in `omitted`.
*Alternatives:* scaling GGG's figures to 9 V by hand (a figure the source doesn't give).

**D-251 — The plain Tone Bender MkII is the original, after Fuzz Central's trace** (2026-11-10) `library`
`tone-bender-mk2` follows Fuzz Central's trace of an original: R3 100k, no TR1 or TR2 (Aion's bias trimmers), C2 and C5 5µ, Level 100k A, VR2 labelled Attack, OC81Ds at the gains the page suggests (70, 70, 100). The page gives no leakage and the fixed bias rests on it, so the leakages are the middle of Aion's documented ranges (with the card's own leakage Q2 saturates). No checks (no published figure for the original); the file says what the simulation reads. The Aion version keeps its trimmers, with notes saying they're Aion's. Tests needing a trimmer use the Aion version.
*Alternatives:* keeping the plain version as Aion's (two Aion starters, no original).

**D-252 — The Boss DS-1's 2SC2240 and NJM3404A as our own cards** (2026-11-10) `models`
Both fitted from their sheets (Toshiba's 2SC2240, Nisshinbo's NJM3404A) by the usual fitters (D-162, D-187); both DS-1 starters use them.
- **2SC2240**: hFE, VCE(sat) and VBE read by pixel off the 25 °C lines; hFE the typical line (about 300 at 2 mA, a GR unit). VBE from the table's 0.65 V at 2 mA with the slope from hie/hfe; the sheet's linear IC – VBE figure reads 50 mV lower and isn't used. No Early voltage (output curves drawn flat).
- **NJM3404A**: 100 dB, 1.2 MHz, 1.2 V/µs, 60° phase margin assumed (D-169). Swings to 0.95 V of V+ and 5 mV of V−, as the 5 V swing graph draws it (the table's ±15 V figure sinks to the middle, which the card's output stage doesn't model; less relevant than single-supply swing).
- The original's input high-pass reads 8.4 Hz against the page's 7.2 Hz: a known gap (the page ignores Q1's base loading; our card is a typical 300, not a BL grade).
*Alternatives:* keeping the stand-ins; fitting hFE at a BL grade (the curve is the typical part).

**D-253 — Our own 1N34A, fitted to a published typical curve** (2026-11-10) `models`
- The makers' sheets give only limits (BKC: under 1.0 V at 5 mA, leakage under 30 µA at 10 V; NTE: at least 4 mA at 1 V; Taitron: 0.8 pF typical). The only typical curve found is MTM Scientific's (0 to 3 mA, 0.35 V at 1 mA, agreeing with builders' readings of 0.22 to 0.34 V). Fitted to it by pixel and checked against all three makers' limits: IS 5.0 µA, N 1.98, RS 75 Ω, CJO 0.8 pF, BV 65 V. Held-out points within 5 mV. LTspice's card shows as *not included* (D-197).
- Softer than the old card: 0.35 V at 1 mA, 0.73 V at 5 mA. In the Rat a 1N34A pair now clamps at 0.50 V, between the BAT46 and the 1N4148.
*Alternatives:* waiting for a maker's sheet with a curve (none found in two searches); fitting to the limits alone (they don't fix the shape).

**D-254 — An edited circuit's settle search starts where it last ended** (2026-11-10) `sim`
`Simulator` remembers the wait each circuit (by id) last needed (D-122) and starts the next search there. The shorter waits are checked on that same run, shortest first (their windows are the start of its run), so the answer is exactly a fresh search's; a slower circuit doubles on as before. Faster knob turns on slow circuits; the first open is unchanged.
*Alternatives:* the Stages pane's picks in parallel processes (extra server load for little); shorter or looser searches (they'd change the answers).

**D-255 — The BD-2's 2SK184-GR, 2SC2459 and M5218AL as our own cards** (2026-11-10) `models`
- **2SK184-GR** from Toshiba's sheet: its tables are the 2SK209's line for line and its |Yfs|–IDSS line within 1 %, so fitted as D-216: Idss 4.11 mA, Vp −0.482 V. TO-92 mini, 1 drain, 2 gate, 3 source, as Boss numbers them.
- **2SC2459** from Toshiba's sheet, by the D-187 fit (gain about 300, a GR unit). The table gives no VBE, so the linear IC–VBE figure is the only source and may read low (as on the 2SC2240's sheet, D-252); in the BD-2 every 2SC2459 is an emitter follower behind a coupling cap, where that moves nothing heard. ISC free: capped, the fit missed VCE(sat) by 9 mV; free, it leaks 10 nA at 120 V, inside the sheet's 0.1 µA.
- **M5218AL** from Mitsubishi's M5218 sheet (1984 General Purpose ICs data book): 110 dB, 7 MHz, 2.2 V/µs, 3 mA, outputs 0.8 V from each rail behind 180 Ω, 60° phase margin assumed (D-169). (Refined: D-258.)
- **2SA1335-GR: no card** (sheet only behind captchas); the 2N3906 stands in, as in Aion's Sapphire.
*Alternatives:* the 2SK209-GR card under the 2SK184's name (the part's own sheet was found); the 2SC2240 card for the 2SC2459 (not the same part).

**D-256 — The original Boss BD-2, from Boss's service schematic** (2026-11-10) `library`
- `boss-bd2` is drawn from Boss's BD-2 MT board schematic with its refs and values, its netlist checked against the scan stage by stage. Boss's JFET switching is left out by drawing the switching JFETs closed: Q6 at the input and Q4 at the effect's output become wires, so their bias resistors and the caps around them stay as the effect-on signal sees them; the dry path, the flip-flop and the LED aren't drawn. D2 is the board's reverse-polarity shunt (1N4001). C22 and C24 (tantalum on the schematic) are drawn film, as Aion fits.
- **The copies are one 72 dpi scan**, so a few refs' digits blur (6, 8, 9); the readings are in the acceptance file (corrected from a board trace: D-258).
- **No checks**: no published voltages or analysis (D-214); the acceptance file gives the simulation's DC levels for comparison.
*Alternatives:* the switching JFETs as parts held on (five transistors and a flip-flop that do nothing in the sim); leaving out the switch nodes' resistors and caps (not what the effect-on signal sees).

**D-257 — The original Marshall Bluesbreaker, from GGG's replica schematic** (2026-11-10) `library`
- `marshall-bluesbreaker` follows General Guitar Gadgets' "Modernized Marshall Vintage BluesBreaker Replica" (2018-08-29), "based on the original BluesBreaker pedal in a black enclosure", with its refs and values (pots VR1-VR3), netlist checked part by part. Its true bypass and LED aren't drawn. Schematics Online's two unattributed, low-resolution redraws agree on the circuit but differ in a few values and one shows the original's split coupling, which GGG says it combined into C6 0.1µ and R8 10k. GGG is followed throughout as the clearest source with a named author; the differences are in the acceptance file. No figures published, so no checks (D-214).
- **GGG's terms** refuse serving its files from any other site: the circuit is in our own drawing and the PDF stays out of the repo and the Wayback Machine; `docs/maintain/add-a-starter.md` says so for GGG's files.
*Alternatives:* the split coupling from an anonymous redraw (its other values differ); Schematics Online's 1992 redraw (low resolution).

**D-258 — The BD-2 checked against a board trace; 2SC2458 card, M5218AL from its own sheet** (2026-11-10) `models` `library`
- **Refs from the trace**: kanengomibako's traces of three BD-2 boards (Unlicense); the 2009 trace has the same assembly number as Boss's schematic (ASSY 70567645). Every part and value of `boss-bd2` matches it; the labels the scan blurred follow the trace (R6 2.2k, R8 100k, R9 6.8k).
- **2SC2458** (Q2, the supply follower; first read as 2SC2459): our card from Toshiba's sheet by D-163's fit. hFE and VCE(sat) read by pixel at 25 °C; VBE from the IB–VBE figure turned into IC through the hFE line (rows running along a grid line dropped); fT 144 MHz at 1 mA. The sheet's gain line is about 140 (a Y unit); Boss's is a GR.
- **M5218AL** refitted from Mitsubishi's M5218AL/P/FP sheet: as the M5218L sheet except slew rate 3.0 V/µs.
- **2SA1335 stays the 2N3906**: its sheet is one selector-table line, no curves. Raising the card's gain to a mid GR moves the drive stages' gain by 0.3–1.1 dB and DC by under 2 mV; each PNP sits inside its discrete op-amp's loop.
- **D2 stays the 1N4001 card** (one sheet covers 1N4001–1N4007). The 2009 board's other changes (NJM4558LD, 2SA1049) aren't drawn: the starter follows Boss's drawing.
*Alternatives:* drawing the 2009 board (a later production); a 2SA1335 card scaled from the 2N3906 (a guess dressed as a fit).

**D-259 — The blocks' capacitor types and ratings** (2026-11-10) `library`
D-211's order, by block. Blocks cut from a starter take that starter's kinds (Big Muff stage and tone stack; the 9 V input filter, battery blocks and Vref divider from the Rat: 100 nF ceramic decoupling, electrolytics 16 V). The rest have no source that types them, so they follow the capacitor guide: film in the signal path, C0G for pF values, 16 V on every electrolytic (`cap_rating_advice`). The corpus test holds blocks to no build notes too.
*Alternatives:* the AB763's original cap types for the TMB (no cited source on hand; D-019); leaving blocks exempt (a pasted block would bring its own Before you build items).

**D-260 — The block catalogue review** (2026-11-10) `library`
- **Templates re-sourced** (they had made-up starting values, D-073): from a starter stage where one fits, each citing it; else a published circuit (D-261, D-262, D-265, D-266). Every block's values come from a cited source.
- **Reverse-polarity protection**: a 1N5817 in series in the 9 V input filter and the DC jack + battery block, ahead of the filter, as on Aion FX's boards (1N5817, 47 Ω, 100 µF, 100 nF). Chosen over Boss's shunt 1N4001 because a reversed supply is blocked rather than shorted; it costs about 0.15 V at 1 mA, so V+F sits near 8.8 V. The battery-only block has none (a snap fits one way). The sim tests hold the diode's and the 47 Ω's drops separately.
- **New blocks cut from starters** (D-261) and **two Baxandall tone stacks** (D-265).
- **Names "What · how"** (D-264).
*Alternatives:* templates kept as labelled exceptions, or dropped; Boss's shunt diode; a separate protection block.

**D-261 — Blocks cut from starters** (2026-11-10) `library`
Each is cut with the editor's own `extract` and `markPort`, as D-073's Big Muff blocks were, keeping the starter's refs, values, part notes and source (named in the description). Ports `in`, `out` and, where biased from one, `vref`.
- **Clipper and tone · Tube Screamer (TS808)** (`ts808-clipper-tone-v1`); ElectroSmash.
- **Distortion stage · ProCo Rat (gain, clipper, filter)** (`rat-gain-filter-v1`); ElectroSmash. The LM308 runs from V+ (a block can't assume the Rat's filtered V+F).
- **Buffer · transistor (Boss DS-1)** (`bjt-buffer-v1`): the input buffer; ElectroSmash.
- **Treble booster · Rangemaster (germanium)** (`rangemaster-booster-v1`): the whole circuit on V- (positive ground); ElectroSmash.
- **Buffer · JFET (ProCo Rat)** replaces the template follower in `jfet-source-follower-v1` (id kept): the gate held at ground by R8.
The block sim tests hold each (buffers about 0 dB, gain blocks above 10-20 dB at 1 kHz, the Rangemaster's collector near the starter's −7 V).
*Alternatives:* drawing them fresh (values retyped); the Rat's whole input (R1 and the input pull-down belong to the pedal's input jack).

**D-262 — The template blocks' values from cited sources** (2026-11-10) `library`
The op-amp stages' sources use half of a dual op-amp, which `extract` would bring whole (D-140), so these keep single-op-amp drawings with the source's values.
- **Buffer · op-amp (Klon)** (`opamp-unity-buffer-v1`): the Klon's input buffer (ElectroSmash), with R1 10k added in series at the input; a TL071 for the TL072's half.
- **Gain stage · op-amp (TS808)** (`opamp-noninv-stage-v1`): the TS808's clipping stage with Drive at minimum and no diodes; out sits at vref as in the TS808. The sim test works its gain out from the complex formula.
- **Clipper · diodes to ground (Rat)** (`diode-clipper-gnd-v1`): the Rat's R6 1k and 1N4148 pair, now cited.
*Alternatives:* blocks bringing an unused op-amp half; converting a half to a single op-amp in code (new code for two blocks).

**D-263 — A dropped block never joins two of its own nets** (2026-11-10) `editor`
Found by Hypothesis: a pasted block could land with a resistor's two pins on one sheet wire, and `joinsAt` (D-164) took it as a join, shorting the resistor. A drop is a join only if, with the sheet's wires, pins and labels added, no two of the block's own nets become one (`joinsOwnNets`); otherwise it moves to a clear spot. The point-joining is shared with `namesClash` (`drawnNets`, D-189). (Supplies: D-270.)
*Alternatives:* checking only a part's own pins (misses two parts' nets meeting through the sheet or a label).

**D-264 — Block names "What · how"** (2026-11-10) `library`
Every core block is named what it is, then how or whose ("9 V power · supply filter", "Tone stack · Fender TMB", "Gain stage · op-amp (TS808)"), so the A-Z list groups by kind. Ids and file names stay (saved circuits don't link to blocks, D-075); a copy saved to My blocks takes its id from the new name. Tags gain the pedal a block comes from (`klon`, `rat`, `ts808`, `boss`, `rangemaster`).

**D-265 — Two Baxandall tone stacks from Texas Instruments' circuits** (2026-11-10) `library`
- **Tone stack · Baxandall (bass, treble)** (`baxandall-bass-treble-v1`): TI application report SLOA042 (2000), Figure 3, TI's refs, pots 100k linear. TI's input cap (C1, 2.2 µF) moves to the network's input, since a block can't assume TI's mid-supply buffer.
- **Tone stack · Baxandall (bass, mid, treble)** (`baxandall-3-band-v1`): TI TL082-N data sheet (SNOSBW5C), Figure 28, "Three-Band Active Tone Control", all linear, TI's 1 µF in; refs ours, left to right; 0.05 µF drawn as 47n with a note that TI's is 50n.
- Both: TI's input buffer left out (drive from one, e.g. Buffer · op-amp (Klon)); a TL071 on 9 V with + at vref; the output sits at vref. Wiper legs end on a `mix` label at the op-amp's − input so no wire crosses; clockwise boosts. Sim tests: flat within 0.5 dB at 1 kHz; each knob's boost and cut in TI's range.
*Alternatives:* ESP's equaliser page for the 3-band (TI's sheet is the maker's own); the 2-band as Figure 28 minus its mid leg (not a published circuit); keeping TI's input buffers (a second op-amp the user may already have).

**D-266 — The JFET gain stage is Run Off Groove's Fetzer Valve** (2026-11-10) `library`
`jfet-cs-stage-v1` (id kept) is the Fetzer Valve v1.1 (runoffgroove.com, Fig. 1, CC BY-NC-SA 3.0): R3 68k in, R1 1M gate to ground, R2 1k5 with C3 22 µF, TR1 100k drain trimmer (the source says "adjust trim for 4.5v at drain", which the block's bias target does), C2 22n to a 100k audio Volume. A J201. Named "Gain stage · JFET (Fetzer Valve)". Plus an input cap, C1 100n (ours, film; 1.5 Hz with R3 + R1), so it works after a stage at any DC level. The Baxandalls' descriptions say when a buffer is needed (after an op-amp output or follower, none; from the guitar, a pot or a collector, add one).
*Alternatives:* the page's Revisited or Deluxe versions (values that depend on the part).

**D-267 — Notes split three ways: general, on the part, on a named net (schema v30)** (2026-11-10) `schema`
- `notes` is the list of general notes (`{title, text}`, text up to 5000 characters); a part's note is a field on the part (`note`), so a rename, move, copy, paste or delete carries it; net notes are `net_notes`, keyed by net name.
- v29 → v30 moves `part:REF` onto the part (a dual pot's or switch's onto unit A) and `net:NAME` into `net_notes`; a key naming no part becomes a general note titled with the key, so nothing is lost.
- A label renamed when it was its net's last label takes the net's note with it, unless the new name has one. Copy and Save as block keep notes on the nets their labels name. A new pole or gang doesn't copy the first's note.
- Dropping a block adds its description as a general note titled "From block: <name>", ending with "Pasted with new refs: C1 → C7, …" when any ref changed. `texts` (sheet text blocks) are unchanged.
*Alternatives:* keeping the map and rewriting keys on every edit (what broke copying before); rewriting the description's refs on paste (corrupts a source's own refs, "TI's C1").

**D-268 — Starter text boxes that are notes become general notes** (2026-11-10) `editor`
A text box on the schematic is for text that must show on the drawing; tables of versions and "Parts to try" ideas are notes, by topic. Moved word for word: the Halo Big Muff's versions boxes become a "Big Muff versions" note plus one "Version: <name>" note per version; each "Parts to try" box becomes one note per idea ("Try: …" or "About …", ending with the Aion document it comes from); the Klons' bypass boxes a note each; the op-amp charge pumps' "⚠ Built from textbook circuits, not documented" box goes (their descriptions say it and become a note on drop, D-267). Credit and Source boxes stay on the sheet (attribution belongs on a printed schematic, D-246).

**D-269 — Notes right under Problems; the rename notice on the drawing** (2026-11-10) `editor`
The default pane order is Problems, Notes, DC, Probe… (D-095's "DC under Problems" now means under Problems and Notes); a saved order without Notes gets it after Problems (`paneOrder`). The rename notice is drawn over the drawing (D-271), so it's in view wherever the panes are scrolled.

**D-270 — A drop never ties a block's supply or ground to another sheet net** (2026-11-10) `editor`
Found by Hypothesis: a power block's ground wiring landed along an unlabelled signal wire, which D-164 counts as a join and D-189 doesn't refuse. A drop also isn't a join when one of the block's supply or ground labels (V+, V-, GND) would end up on a sheet net whose labels don't carry that name (`shortsToSupply`); the block moves to a clear spot. Joining a signal pin on purpose works as before.

**D-271 — The rename box: in the dialogs' style, over the middle of the drawing; both names looked up** (2026-11-10) `editor`
The notice is a sheet (title "Renamed R5 to R54", Close, body, Show / Hide and Replace bottom right) over the middle of the drawing, not modal, so a note's name can still open it in the Notes pane. A rename looks up the old name (to replace) and the new one: notes already using the new name are listed under "Already say R54" for information; with only those, the box says so and has no Replace.
*Alternatives:* a modal dialog (it would hide the Notes pane the box's links open).

**D-272 — No clips, captures or IRs ship; each Audio drawer says where to get one** (2026-11-10) `audio`
- Tone3000's terms forbid redistributing tones obtained there, and each capture's licence forbids republishing without its author's permission; no openly licensed NAM capture was found. So nothing ships in `library/audio/`: no capture, IR or clip. With Amp at None a render is the pedal's output.
- An empty drawer says so in one line ("No DI clips loaded.", "No amp captures loaded.", "No cab IRs loaded."). The Audio pane's ⓘ says where to get them: a clip is a DI recording up to 10 s; captures and IRs from tone3000.com; with a full-rig capture, Cab at None. The user guide walks through downloading a capture and an IR.
- The built-in layer (`AudioLibrary`'s core folder, `sources.yaml`) stays, empty, so a file whose licence allows it can be added later without code.
*Alternatives:* asking capture authors for permission; shipping a CC0 IR pack alone (link to where IRs are, as for captures).

**D-273 — Work a search repeats is kept: nets per drawing, recent results in memory** (2026-11-10) `sim`
Profiling Find parts on the Big Muff (5.3 s) showed over half was Python repeating work: `connect()` 1,333 times and the same cached operating point unpacked 544 times.
- `connect()` memoises by the drawing's geometry alone (pin positions, wires, labels, which parts are active; `CONNECT_MEMO` 256 drawings): a circuit differing only in values, models or knobs gets the same `Nets` object, which callers must not change.
- `CachedEngine` holds recent results in memory (`RECENT_BYTES` 64 MB, LRU). The disk cache still decides what is cached: a memory hit first asks `SimCache.touch(key)`, so deleting the cache still forces a fresh run. Results are shared, so their vectors are read-only.
- Measured (cold cache, Big Muff): Find parts 5.3 → 1.35 s; warm requests about 40 % quicker.
*Alternatives:* caching on the `Circuit` object (a search makes a new one per try); a faster blob format than `.npz` (helps the first read only, orphans the cache).

**D-274 — The fit script's roots by Brent's method, VCE(sat) by Newton on both junctions** (2026-11-10) `sim`
`scripts/fit_models.py`'s nested bisections took 49 s in one unit test. `_bisect` keeps its contract (the root to 1 pV, the ends when there is none, the first crossing with `step`) but uses Brent's method. `GummelPoon.saturated` solves both junction voltages at once by Newton's method (finite-difference Jacobian, steps held to 50 mV, relative residuals), falling back to the nested search (`_junctions_nested`) when it doesn't settle in 60 steps; on 3,000 random transistors the two agree to 0.1 nV. `make test` 70 → 17 s. The shipped cards were not refitted: a refit's last digits may differ, so review cards when one is next refitted.

**D-275 — The wait before measuring goes by at coarse steps, and hands its state on** (2026-11-10) `sim`
- The settling wait (D-122) ran at the measuring resolution (400 steps a cycle), so a high tone paid for many cycles; ngspice can't change its step limit during a run.
- `Simulator.tran` runs all but the wait's last `SETTLE_CYCLES` at `WAIT_STEPS_PER_CYCLE` (100), keeping only the last point (`Tran.keep_from`), then starts the measuring run there: every node's volts as `.ic` lines with `uic`, each inductor's amps as its own `ic=` (`Tran.state`, `Tran.coil_amps`). The measuring run is 10 fine cycles to take up the hand-over, then the 10 measured; the wait ends on a whole cycle so the sine starts in phase. Not split when the coarse part is under `WAIT_WORTH` (10) cycles, or when an inductor sits inside a model. The settle search (`_settle_run`) runs at coarse steps too (harmonics 1 to 8 survive 100 steps a cycle).
- **Checked** against one fine run: every net's harmonics 1–8 within 0.4 % on the starters (0.85 % on one millivolt node); the settle tolerance is 1 %. A sim test holds it.
- Measured: the Bias & headroom pane's three picks at 3 kHz, Big Muff 10.4 → 2.7 s, Dyna Comp 67 → 18 s.
*Alternatives:* a 40-step wait (a starter moved 2.5 %); settling in cycles (the wait is a time: caps charging); a shooting solver.

**D-276 — A knob's runs go one at a time, the newest position next** (2026-11-10) `panes`
`oneAtATime(fn)` (`web/state.js`): a call made while `fn` runs waits for it to end, then runs once for however many calls came in. The knob's run uses it and counts the Bias & headroom measuring as part of the run. Other runs (a node click, an edit) go at once, so a cached answer isn't stuck behind a slow run.
*Alternatives:* cancelling a run at the server (needs a handle per request, as renders have); making every run wait.

**D-277 — A tone's run records every node, so every view reads the same run** (2026-11-10) `sim`
`Simulator.tran` recorded only the asked-for nets (`.save`), so each asker's netlist and cache key differed: three runs of the same transient. Now the run records every node and keeps only what is measured (the last `MEASURE_CYCLES` and one before, `Tran.keep_from`), its netlist independent of `nodes`, so the first asker runs it and the rest read the cache. A net only loose parts touch is still refused (`require_wired`). Results are up to 2.8 MB each on the starters. Clicking a part or another net after Run: no simulation, about 40 ms.
*Alternatives:* saving top-level nets only (unused pins would have to be told apart first); keeping the whole run (long waits filled the cache).

**D-278 — `solum bench` times the cache and Find parts where the cache lives** (2026-11-10) `project`
Tests keep their cache on tmpfs, which hid a slow cache index (D-126). The bench adds `cache` (ms per put and get, 200 small results) and `find_parts` (the Big Muff's Q4, first and again), run in `CACHE_DIR/bench` (removed afterwards); `make bench` mounts the real cache folder (`BENCH_CACHE`, default `./cache`).

**D-279 — A solve that ignores its halt is told at once, and so is every later run** (2026-11-10) `sim`
`bg_halt` doesn't stop some DC solves (D-195). If ngspice is still running `HALT_WAIT` (5 s) after a halt, the run raises `EngineStuck` ("got stuck on this circuit ... Restart Solum Builder") and later runs raise it at once without touching ngspice; if the thread stops after all, runs go on. A restart button in the page is for later, if it's ever needed.
*Alternatives:* simulations in a replaceable worker process; exiting so Docker restarts the app.

**D-280 — Loose parts kept per drawing; a circuit's operating point solved once per object** (2026-11-11) `sim`
- `loose_parts` memoises by what it depends on (`_loose`: the `Nets` object, anchor nets, each part's ref, type, chip and unit-ness); `Nets` compares by identity (`eq=False`) so it can be the key, and `connect`'s memo makes one object per drawing.
- `Simulator._op` holds the last `OP_MEMO` (8) circuits' operating points by the circuit object itself (`is`, as `supply.battery_rails`), so a circuit must not be changed after it has run.
- Find parts on the bench: first 2.08 → 1.68 s, again 0.73 → 0.40 s.

**D-281 — A large view stays open through canvas clicks; Bias & headroom doesn't jump on a quick answer** (2026-11-11) `panes`
- A canvas click no longer shrinks a large view (withdraws that part of D-127); its title bar, Esc and another view opening still do, and opening another circuit shrinks them all.
- Measuring shows as busy (bar, fade) only after 200 ms (`BUSY_AFTER_MS` in `stages.js`, the fade's `transition` delay in `app.css`), so a quick cached answer doesn't make the panes below jump; `data-loading` is still set at once (logic and tests read it). A UI test holds the pane's height through a move.
- The V+ and V- tiles are in the palette from the start (`buildPalette`), so tiles don't shift after a load.

**D-282 — The browser measured: nothing redrawn is slow; one owner for the repeats found** (2026-11-11) `panes`
- **Measured** (the original Klon, headless Chromium): a knob turn's answer shows 4-5 ms after it arrives; a node click after a run in 24 ms; an edit's drawing in 31 ms. No task over 50 ms. So panes and drawing keep being rebuilt whole on each run or edit: patching in place isn't worth the code. The knob's 120 ms and the edit's 250 ms debounces stay (they keep a drag or held key to one run). Three `timing` tests hold the numbers (`tests/ui/test_viewer.py`).
- **Repeats given one owner**: in `api/app.py`, `attachment`, `page`, `require_sim`, `runnable`, `known`, `take`, `netlist_files`; `cache_from_settings` (`cache.py`): the simulator, API and render jobs share one `SimCache`, and a render worker keeps one for its life; `units.signed_db`. In the browser: `web/storage.js` (`remembered`, `remember`) for everything in `localStorage`; `confirmed` beside `ask`; `twoPin` in `editor/insert.js`; `stages-logic.js` writes volts through `fixed.js`.
- **Looked at and left**: `CircuitStore` opening the index per call (1.5-2 ms; a long-lived connection would need its own locking); `model_checks._bisect` (the cards' checks were fitted with its fixed halvings); formatters with their own formats; `migrations.py`'s own `next_ref` (a migration must not change when the editor's does). (Splitting `web/app.js`: D-284.)

**D-283 — With Auto-run on, a single edit re-runs at once; only bursts wait** (2026-11-11) `panes`
An edit checked with the server first (`tryEdit`: every form's Apply, a slider let go, a Bias & headroom change, a note, a rename) re-runs at once (`setCircuit`'s `now`); edits made straight on the sheet (moves, wires, placing, delete, rotate, undo, redo) still wait for a 250 ms pause, which exists for bursts (a drag, a held key). A seen value now shows about 130 ms after Apply; `test_apply_with_auto_run_reruns_at_once` holds it under 0.25 s.

**D-284 — `web/app.js` split into modules given the root's callbacks** (2026-11-11) `project` `editor` `panes`
- The pattern the panes already used: a module exports one factory, `thing(host, app)`, built once in the root; `app` is a plain object of callbacks (getters for what it reads, one function per thing it asks of the root), typed as a JSDoc typedef in the module. Moved with no behaviour change: `file-dialogs.js`, `block-dialogs.js`, `palette.js`, `app-menus.js`, `power.js`, `inspector.js`, `live-sliders.js`. The root keeps state, open/show, edit/undo, selection and placing, run/render, the knobs' live curve, the Problems panel, the small label/text/find forms, hotkeys. `docs/ARCHITECTURE.md`'s "Where browser code goes" is the guide for new browser code.
- **Modules never see `state`**; they read through getters, so tabs (v2) could gather one open circuit's state into one object by changing the root alone.
- State one module alone uses lives in it (the ports being marked, which part's form is open).
- The palette is its own module (the supply tiles need the tile drawing; Power asks for them, `showSupplyTiles`).
- The menu lists take one callback per command: lists, labels and hints are in `app-menus.js`; what a command does stays where it was.
- `fetchLive`, `drawLive` and the knobs' grab stay in the root (they are the run's drawing); the sliders are handed them. `versionTag`, `parseTag` → `editor/files.js`; `tryButton` → `editor/form.js`; the root's `hint(text)` is the one writer of the canvas hint.
- Candidates if the root grows again: the Problems panel's glue, `render` and its helpers as a results module.

**D-285 — A block's wire lying along a sheet wire is not a drop made to join** (2026-11-11) `editor`
Found by Hypothesis: a power block's battery + wire lay along an op-amp input wire, both ends on it, so `joinsAt` (D-164) took it as a join. A join is an end touching (a pin, label or wire end on a sheet point or wire); when any block wire would lie along a sheet wire for more than a point (`runsAlong`), the drop isn't a join and the block moves to a clear spot. A T, an end meeting, or a crossing is as before. D-270's check stays. If the Hypothesis test (a paste never touches a host net) ever finds a case that is a proper join, the test's property is what should change.

**D-286 — A static check for the browser code, on the node Playwright ships** (2026-11-11) `project`
- With no npm, bundler or type checker, an undeclared or unimported name failed only when its line ran. `scripts/jscheck.js`, run by `make jslint` (part of `make lint`, so `make check`, and the pre-commit hook), reports for every module under `web/` but `vendor/`: a name used but not declared in any enclosing scope, imported, or a browser global (`GLOBALS`, plus any `HTML…Element` / `SVG…Element`); an unused import; an import of a name the other module doesn't export (or a missing file); a file that doesn't parse.
- It parses with acorn, the copy inside node itself (`--expose-internals`), on the node binary Playwright already puts in the dev image: no new dependency. Its own scope walk (function, block, loop, catch, switch, class; `var` hoisted).
- *Limits*: no types, no property names, no unused locals. If a Playwright upgrade moves node's internal acorn, `make jslint` fails at once with a require error; the fix is that path (or vendoring acorn, one file, MIT).
- Tests: `tests/unit/test_jscheck.py` (each finding and declaration kind; the tree itself clean).
*Alternatives:* ESLint or `tsc --checkJs` (need npm; tsc would first need the JSDoc types cleaned up); Deno's `deno check` from PyPI (a 100 MB binary for one error class); a Python JS parser (the PyPI ones stop before optional chaining).

**D-287 — The name is renamed in place by a pencil, at once; Open lists Recent over All circuits** (2026-11-11) `editor`
- **Rename**: a pencil after the name turns it into a box and itself into a tick. Enter or the tick renames; Esc or a click elsewhere restores; no pop-up. What's wrong with a name (empty, taken, ends in a version) is said under the box, which stays open. For a saved user file the rename goes to the server at once (`PATCH`, D-075: every version's file follows, the minor counts one on). Unsaved changes stay unsaved, and every undo step takes the new name and id (`History.amend`), so undo never brings the old name back. A new sheet or unsaved copy has no file: the name is an edit saved with the circuit. A starter, core block or final version says why it can't be renamed. Properties keeps its Name box. File → Rename… and click-to-rename are gone.
- **Open**: two sections, **Recent** (the three last saved, newest first; `RECENT_MAX`) and **All circuits** (by name, A–Z / Z–A). A search shows only matches, no sections. "Last edited" is the file's time on disk from the index, carried as `saved` to the millisecond. A rename counts as a save.
- No draft or auto-save: the Not saved chip is enough.

**D-288 — Licence audit, the models: every model the starters and blocks use may ship; unused unshippable cards leave; a missing model is a Problem** (2026-11-11) `project` `models`
- Every model the starters and blocks name may ship (all *Settled* in the index, D-156): our own fits to makers' sheets, one estimate (OC81D, D-186), behavioural values read from sheets (the charge pumps, the 78L12), and makers' own files with no notice (TI's LM308 and RC4558, Diodes' 1N4742A). The four cards still *Decide* (2N4123, 2N4125, BC109C: makers' cards inside LTspice's all-rights-reserved library; AC127, which names no maker), used by nothing, left the repo; Parts and datasheets lists them as *Not included* (D-197). No library model is flagged.
- **`model-missing`** (topology, error, stops the simulation): a part naming a model the library doesn't have (a card taken out, or one another person added) is named with the fix: "Can't simulate yet: Q1 names the model J999, which isn't in the library", then Tools → Add a model, Parts and datasheets for where to get it, or choose another. `ModelLibrary.get`'s own message says the same without listing every id. The rule book goes from 65 to 66 rules.

**D-289 — Licence audit, the rest: `LICENSE` (MIT with the Commons Clause) and `THIRD-PARTY-NOTICES.md`** (2026-11-11) `project`
- **`LICENSE`**: the Commons Clause condition v1.0 (text checked against commonsclause.com) over the MIT licence: anyone may use, change and share it; nobody may sell it or a product or service whose value is mainly the app. Plus one plain line: designing, building and selling pedals with Solum Builder is allowed. Not legal advice.
- **`THIRD-PARTY-NOTICES.md`** lists what else is in the repo and whose: uPlot (MIT, its licence beside it); Fahkwang and Lora (SIL OFL 1.1, licences beside them; the outlined logo carries Fahkwang outlines, which the OFL allows); the models (D-288); the guides (figures from the sources each names); the wiring drawings (ours); the NAM test models (random weights, made here). No audio ships (D-272). ngspice and the Python packages are installed at image build, not kept in the repo; the notices name them.
- **The starters** are our own drawings of published circuits; part values and measured voltages are facts. Short quotes in the expected-values files stay their authors' and are not under `LICENSE`; ElectroSmash's (CC BY-NC) are reworded (D-292).

**D-290 — The user guide inside the app: Markdown rendered by markdown-it-py, Help → Documentation and Help → Formulas** (2026-11-11) `docs`
- The guide stays Markdown in `docs/guide/` (`README.md` is its first page; page order is the order it links them), readable on GitHub too. `solum/manual.py` reads the pages once at start, renders each to HTML at `/manual/<page>`. Each page carries the page list, its own headings and a search box; the server searches (`/api/manual/search`: sections holding every word, heading matches first, at most 30). Links `other.md#part` are rewritten to the app's addresses, links out open a new tab, pictures are `img/…` (from `docs/guide/img/`). **Help → Documentation** frames the pages in a large window with *Open in a new tab*; **Help → Formulas** opens it on the Formulas page (`formulas.md`, every figure worked by hand). The image copies `docs/guide/` (`GUIDE_DIR`).
- **New dependency: markdown-it-py** (MIT, pure Python, one small dependency, mdurl): the standard library has no Markdown parser, and our own would be a second CommonMark implementation. Tables on; raw HTML not rendered. Heading ids and link rewriting are done on its tokens, no plugin.
*Alternatives:* rendering in the browser (a vendored JS library, away from the search, links rewritten there too); a static site generator (another tool and build step for a handful of pages).

**D-291 — The page's files are sent with `Cache-Control: no-cache`** (2026-11-11) `project`
After an update the browser re-fetched some scripts and took others from cache without asking (ETag and Last-Modified but no Cache-Control), so new code importing a name the old module lacked stopped every module. Everything the web folder serves (`_Checked`, a `StaticFiles` adding the header) and every server-made page (`page()`) carries `Cache-Control: no-cache`: the browser asks before using its copy, and unchanged ones get a 304. Renders keep their year-long immutable header (their address is their content's hash). A browser holding old files from before this needs one hard reload (Ctrl+Shift+R); the README's update steps say so. Test: `test_the_pages_files_are_checked_again_on_every_load`.
*Alternatives:* version numbers in every script address (rewrite every `import` at serve time, or a build step); `no-store` (every load re-sends every file).

**D-292 — Nothing of ElectroSmash's text is in the repo: its figures are said in our own words** (2026-11-11) `library`
ElectroSmash's pages are CC BY-NC 3.0 and the repo's licence lets pedal makers use it commercially. A check in an expected-values file carries either `quote` (the source's own words) or `says` (what the source says, in ours). A file whose source is non-commercial has no `quote`. Figures, formulas with their numbers, part names, links, snapshots and read dates are unchanged (facts, and what a test is checked against); each `says` was written from the quote it replaced, no values moved. Test: `tests/unit/test_expected_sources.py`.

**D-293 — Dragging a wire moves the stretch grabbed, and works in a circuit with a wiring contradiction** (2026-11-11) `editor`
- A click selects a bent wire whole (D-095, so Delete takes all of it), but a wire dragged on its own now moves only the stretch grabbed (`movingItems`); `moveItems` re-lays the neighbours, so the legs stretch and the ends stay on their pins and labels. A group selection still moves whole.
- Two views with the same wiring contradiction match in `sameConnections`, so a wire can be moved in such a circuit; a move that makes, mends or swaps a contradiction is still refused. The price: in an already contradictory circuit a move isn't checked for what it connects (undo is there).
- With a contradiction no net resolves, so clicking a label can't highlight its net; Problems says which labels are joined. Netlists write net names in lower case (`net.lower()` in `solum/netlist.py`; SPICE ignores case); the sheet keeps names as typed.

**D-294 — A chip's pin numbers: the package under the box, the sheet in the ⓘ** (2026-11-11) `editor`
The Chip row's hint is "Pin numbers: 8-pin DIP."; its `about` carries "The pin numbers are from <the sheet>." (D-200). A model with no checked sheet keeps its one-line hint and has no `about`.

**D-295 — `opamp-no-dc-feedback` says "no DC path", not "only through capacitors"** (2026-11-11) `rules`
A capacitor path through a virtual ground made "feedback passes only through capacitors" read wrong where no feedback part was left. The message is "{ref} has no DC path from its output to its − input: it needs a resistor (or a pot) there.", true whichever way the capacitors lie; the fix says "across the feedback capacitor if it has one". The search is unchanged.
*Alternatives:* treating another op-amp's − input as a dead end (could hide a real loop through a second op-amp, the servo D-247 keeps).

**D-296 — The user guide's pages, and screenshots made by a script** (2026-11-11) `docs`
- `docs/guide/` has a page per area plus a first-pedal walkthrough, audio, getting audio, troubleshooting and formulas, in the first page's order. Each was written from the app as it is (menus, panes, forms and ⓘ texts dumped from a scripted browser, code read where a screen doesn't say). The first-pedal walkthrough splices the core block *Gain stage · JFET (Fetzer Valve)* between IN and OUT (values from a cited source, D-266). Heading links use headings without punctuation: the app's `anchor_of` turns a run of other characters into one hyphen, GitHub into one per space.
- **Pictures**: `scripts/guide_shots.py` drives the real app (in-process on a free port, a temporary data folder, real ngspice, an empty cache, as the UI tests do) in a 1600 × 1000 Chromium page per picture, one function per picture, reusing the UI tests' helpers. The PNGs are committed in `docs/guide/img/` so GitHub shows them. The audio picture renders the UI tests' made-up riff through the TS808 with no amp or cab (none ship, D-272). `test_every_picture_the_guide_names_is_there` fails when a page names a missing picture.
*Alternatives:* screenshots by hand (can't be remade); pictures generated at build time (GitHub wouldn't show them, the image would need a browser); a walkthrough circuit drawn from scratch (its values would need a source).

**D-297 — What ships, listed in the guide; maintainers' docs in the top README** (2026-11-11; the maintainers' side moved to `docs/maintain/README.md`: D-305) `project` `docs`
- `docs/guide/whats-included.md` lists every starter and core block by the name the app shows, each in our own words from its description, grouped as the Blocks dialog groups them; models aren't copied there (Parts and datasheets is their list). `test_whats_included_lists_every_starter_and_core_block` fails when one has no row. The guide holds users' pages only.
- The top `README.md` keeps install, run and first steps for users, then everything for maintainers: setting up, make targets and their settings (`LOCAL`, `JOBS`, `BENCH_CACHE`), the `solum` command, benchmarks and profiling, the scripts, the test layers, the project's documents, the how-tos, and working with an AI agent. `docs/maintain/` keeps the how-tos, with `working-docs.md` (each working document, the order of authority, how they're kept and why) and `updating-the-guide.md`.
*Alternatives:* the how-tos as a Maintaining section of the guide (users don't need them).

**D-298 — After a major UI change, ask whether to update the guide now or in a full docs pass** (2026-11-11) `project` `docs`
After a major UI change (a menu, pane, dialog or workflow added, renamed or reworked), the agent asks whether to update `docs/guide/` now or leave it for a full docs pass; if it's left, the maintainer's plan notes which pages and screenshots it affects. `docs/maintain/updating-the-guide.md` says how, and what a full pass does (every page read against the app, every picture remade).
*Alternatives:* updating the guide in every UI commit (whole passes preferred); no rule (changes go unnoticed until a pass).

**D-299 — Studies live in the guide, under Advanced** (2026-11-11) `docs`
The guide's first page ends with an **Advanced** section after Troubleshooting. The germanium page moves there, and the germanium study moves into the guide as `docs/guide/germanium-study.md` (one copy, linked), so the app and GitHub both show it. Later studies a guide page cites go there too; `docs/studies/` is gone.
*Alternatives:* keeping `docs/studies/` and rendering a second folder (more code, the image copying it); a copy in the guide (two to keep in step).

**D-300 — The guide changes page without reloading** (2026-11-11) `docs`
`web/manual.js` catches a plain left click on a link to another guide page, fetches that page's HTML from the same `/manual/<page>` address and swaps in only its `<main>` and page list, then sets the title and pushes the address, so pop-out, reload and Back/Forward work. The list scrolls so the clicked link stays where it was on screen; the open page's own link scrolls to its top. Heading links, links out and modified clicks are left to the browser; a failed fetch loads the address normally. The server is unchanged, so every page works without JavaScript and on GitHub. Test: `test_guide_pages_change_without_reloading`.
*Alternatives:* a JSON endpoint per page with the list built in JS (a second renderer); all pages in one document (bigger first load, anchors to keep unique).

**D-301 — The guide's page list is grouped by the first page's sections** (2026-11-11) `docs`
Each `##` section of `docs/guide/README.md` heads a group in the left-hand list, with the pages it links under it and the open page's headings under that page. The first page decides both order and groups; a new page goes under the section that links it. The first page's own headings aren't listed under it (they are the groups); pages it doesn't link come last.
*Alternatives:* only Advanced grouped (a flat run mixed with one group); group names in a separate list (a second place to keep in step).

**D-302 — Help → Hot keys lists every shortcut from one list beside the key handling** (2026-11-11) `docs`
`hotkeyGroups()` in `web/editor/keys.js` holds the list (Drawing, Parts, Editing, Mouse on the sheet, Elsewhere); part keys come from the palette. Each sheet-key row carries the press and the action it should start, and a test checks every row against `actionFor` and that every action a key can start is listed. Help → Hot keys shows it in two columns. Keys handled elsewhere (a form, a plot, a pane grip) and the mouse are listed by hand in the same function.
*Alternatives:* a table written into the window (drifts from the keys); `actionFor` rebuilt from the list (larger change, no gain the test doesn't give).

**D-303 — Three themes, Solum, Dark and Light, from View → Theme…** (2026-11-12) `look`
`theme.css`'s `:root` stays the Solum theme; `:root[data-theme="dark"]` and `:root[data-theme="light"]` replace the UI, status, schematic and plot roles (Dark: neutral greys, a blue highlight; Light: dark text on white, a blue highlight, the ink logo). View → Theme… (right before Reset pane order) shows the three as cards; a click applies it at once and this browser keeps it (`solum.theme`, nothing kept for Solum). `theme-start.js`, a plain script in the `<head>` of the app and the guide's pages, applies it before the page draws, so no flash; the guide follows the app. Canvas plots re-read their colours after a change (`forgetColours`). Exports and printed schematics keep paper colours. Every theme passes the contrast and hue tests.
*Alternatives:* following the system's light/dark setting (Solum would lose its place as the default); a light theme in the brand's brass (too little contrast on white for text).

**D-304 — A fresh repository for the first public commit; DECISIONS.md pruned once** (2026-11-12) `project` `docs`
- The project is published as a new repository with no history: the first commit is the tree as it stands. The development history stays in the maintainer's private copy.
- Before that commit, this file was pruned once, against its old "never delete an entry" rule: every number kept (code, tests and docs cite them); superseded, reserved and process-only entries cut to one-line stubs; live entries cut to the decision, its reasons and the alternatives turned down; branch, phase and session narrative, test counts and personal details removed. From here on the normal rule holds: entries are added, and a changed decision supersedes the old one with a stub.
- The phase plan (`PHASES.md`) and the other session notes are each maintainer's own, kept in the git-ignored `notes/` folder, not in the repo. Agent instructions are in `AGENTS.md`.
*Alternatives:* publishing the full history (it carries removed cards, personal details and session notes, which a rewrite would have to find in every commit); keeping DECISIONS.md whole (half its length was history a reader doesn't need to check the code).

**D-305 — Maintainers' guide out of the README; no CLAUDE.md; one version number; the cache folder ships empty; About laid out side by side** (2026-11-12) `project` `docs`
- **README**: install, run, first steps and the licence, then a short *Working on Solum Builder* section saying what the maintainers' guide holds, linking to it. Everything else (setting up, make commands, tools, tests, the project's documents, the how-tos, working with an AI agent) is `docs/maintain/README.md`, which GitHub shows when the folder is opened. Users don't need it on the first page.
- **No `CLAUDE.md`**: the agent instructions are `AGENTS.md` only, which Claude Code reads as other agents do.
- **One version number**, `solum/__init__.py`'s `__version__`; `pyproject.toml` reads it (`dynamic = ["version"]`, `[tool.setuptools.dynamic]`). The API's health (`version`, `ngspice`), Help → About and the exports all show it from there. Version 1.0.1 for the first release (the maintainer's private archive is 1.0.0).
- **`cache/` ships empty** (`cache/.gitkeep`; its contents git-ignored), as `data/` already did, so the default `CACHE_DIR` exists on a fresh clone: Podman, unlike Docker, stops when a folder to mount is missing. The README says to create the folders first when they're put elsewhere or the image is run by hand.
- **Help → About**: the logo on the left, the one-line description with Version and Simulator beside it, the credits under both; the sheet keeps its width and gets shorter.
*Alternatives:* `CLAUDE.md` importing `AGENTS.md` (a second file for nothing); the version written in both files (they drift); making the folder in the app at start (a missing bind mount stops the container before the app runs).

**D-306 — A fresh clone works with an agent; DECISIONS.md is searched, not read whole** (2026-11-12) `project` `docs`
- **The agent reads less at the start**: `AGENTS.md` and `docs/maintain/working-docs.md` (how the plan, the decisions log and the module map work), then `notes/PHASES.md`. DECISIONS.md (about 300 KB) is searched by area, and every D-number cited in the code being changed is read.
- **Area tags, not codes**: every heading ends with one or more tags from the Tags table at the top (`` `sim` `panes` ``), so `grep '`panes`'` lists an area's decisions. A unit test fails on a missing or unknown tag or a gap in the numbers. The v1 entries were tagged from their titles in one pass.
- **On a fresh clone** (no `notes/PHASES.md`) the agent gets the machine ready itself (`make dev-image`, `make hooks`, `make check`), asking the person to install Podman or Docker and `make` if they're missing, then turns the person's request into phases and has them agreed before building.
- **Reviewing a change** includes checking that its decisions are recorded; a pull request template asks for the D-numbers.
*Alternatives:* splitting DECISIONS.md by layer, or area codes in the numbers (DU-012): many decisions cross areas, and the D-numbers cited about 2,000 times in the code must stay; a hand-kept index by area (goes stale, and needs someone to sort each entry later); a phase template file to copy (the layout is a few lines in working-docs.md).

**D-307 — Ruff checks the scripts and the agent skills too; the fits' worked scripts are kept as written** (2026-11-12) `project`
- `make ruff` (so `make check` and the pre-commit hook) lints and format-checks `solum`, `tests`, `scripts` and `.claude/skills` (`PY_DIRS` in the Makefile). Agents copy from the tools and the worked starter, and code outside the check drifts: a too-long line got into `scripts/guide_shots.py` unnoticed.
- `.claude/skills/fit-model/worked/` is excluded (`extend-exclude` in `pyproject.toml`): each script is the record of one part's fit, cited by its model record and never run again.
- The minus sign, en dash and times sign are allowed once (`allowed-confusables`): records and messages use them on purpose; the `noqa: RUF001` comments went.
- **Checked**: every fitter, the re-measure, the op-amp checks, the curve reader and the models index were run before and after; their output and every file they wrote were byte-for-byte the same.
*Alternatives:* leaving the scripts and skills unchecked; checking `worked/` too (957 findings in finished records).


**D-308 — The README's logo is a PNG; solumfx.com and the repo linked from the README and About** (2026-11-12) `docs` `look`
- GitHub's mobile app shows no SVG in a README (a broken-image mark), so the README's logo is `docs/guide/img/readme-logo.png`: the silver outlined logo on the Solum theme's ink in a rounded square, drawn at twice the size shown by `scripts/guide_shots.py readme-logo`. The logo itself isn't redrawn (`docs/DESIGN.md`).
- solumfx.com sits under the logo in the README and in Help → About; About also has a Source row linking the repository (`SITE`, `REPO` in `web/help.js`).
*Alternatives:* a `<picture>` of the two SVGs (the GitHub app shows neither).

**D-309 — Specs: new work is specified and planned in `notes/`; finished specs are kept in `docs/specs/`** (2026-11-13) `project` `docs`
- A new piece of work (a feature, a new packaging, a rework) starts with a spec in `notes/<NAME>-SPEC.md` and phases in `notes/PHASES.md`, both local to the maintainer doing it and git-ignored. A small change needs no spec.
- When the feature is finished, its spec is copied to `docs/specs/<NAME>-SPEC.md` in the feature's last pull request, brought up to date: what was built, open questions answered, the building plan taken out, decisions cited.
- `docs/SPEC.md` moved to `docs/specs/ORIGINAL-SPEC.md`: the spec v1 was built from. Specs are consulted for the area being changed, not read at the start of a session. DECISIONS.md still wins over a spec, and the spec is fixed in the same change. Entries before this one that say SPEC.md mean that file.
- `notes/PHASES.md` holds only the work in hand. Finished, accepted work moves to `notes/PHASES-<name>.md`.
- A session reads `AGENTS.md`, `docs/maintain/working-docs.md` (it says what is where), `notes/PHASES.md` and the current phase's spec at its start, and nothing else (the user: keep the first read lean). Specs in `docs/specs/` and DECISIONS.md are consulted.
- Why: the user found the plan had grown too large to read at the start of a session (it held all of v1); the docs didn't say where a contributor starting something new should put their spec and plan; and one ever-growing product spec isn't something a session should have to read to start.
*Alternatives:* removing the original spec (it is the one place that says what v1 as a whole does); keeping one `docs/SPEC.md` and folding each feature into it (it grows without end, and the feature's own reasoning is lost); specs for unfinished work in `docs/` (other people's plans in everyone's clone).
