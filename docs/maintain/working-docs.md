# The working documents

Solum Builder is built mostly by AI agents, one session at a time, with a person deciding what gets built. Every session starts cold: the agent knows nothing about the project beyond what it reads. The files in `docs/`, with the maintainer's own notes in `notes/`, are how one session hands over to the next. A decision that isn't written down gets debated again; a function that isn't in the module map gets written twice; a session that ends without a note leaves the next one guessing.

So these files are part of the code. A change that makes one of them wrong updates it in the same commit.

## What each file is for

| File | What it holds | Updated when |
|---|---|---|
| `AGENTS.md` | The working agreement: what the project is, the stack, coding standards, testing, how a session starts and ends. The agent reads it at the start of every session. | A rule changes (rarely). |
| `notes/PHASES.md` | The plan for the work in hand: phases, each with a checklist and *Accept when*; dated notes of what each session did; the **Next session** note. Local and git-ignored: each maintainer keeps their own (a fresh clone has none; start one). | Every session: tick what's done, add a dated note, rewrite Next session. |
| `notes/<NAME>-SPEC.md` | The spec for a new piece of work (a feature, a new packaging, a rework): what it's for, what the person gets, how it works, what's out of scope, the open questions. Local and git-ignored, like the plan. | Before the work is planned; then as the person's answers settle its open questions. |
| `docs/DECISIONS.md` | Numbered decisions, `D-001` onwards, newest at the bottom: the context, what was decided, and the alternatives turned down. Each heading ends with area tags (listed at the top); searched by tag, not read whole. | Any choice a later session would otherwise re-open: a library, a format, an algorithm, a trade-off, a change the user asked for. |
| `docs/ARCHITECTURE.md` | The data flow, the **module map** (one line per module and public function), where browser code goes, the other files. | Any new public function or module, or one that moves. |
| `docs/SPEC.md` | The product spec: the original spec the app was built from, kept current, so it says what the app does today. Not where new work is planned. | When DECISIONS overrides it, in the same change. |
| `docs/DESIGN.md` | The look: brand assets, colour tokens, type, layout. | When the look changes. |
| `notes/TESTLIST-*.md` | Local and git-ignored, like PHASES.md. The person's checks by hand: what to open, do and see, for what the automated tests can't judge (does it read well, look right). | When a feature needs eyes or ears. |
| `docs/guide/` | The users' guide, shown in the app (Help → Documentation). See [Updating the guide](updating-the-guide.md). | After a major UI change, now or in a later full docs pass, as the person decides (D-298). |
| `docs/guide/` *Advanced* | Studies: write-ups of investigations whose figures a guide page or decision cites, shown in the guide's Advanced section (D-299). | When a study is done. |
| `docs/NAS.md` | Running the image on a NAS. | When deployment changes. |
| `docs/circuit.schema.json` | The circuit file's JSON Schema, generated (`make schema`); a test fails when it's stale. | Never by hand. |

## Order of authority

When two disagree, the newer wins: **DECISIONS.md over SPEC.md**, and the fix to SPEC.md goes in the same change. When the person asks for something that conflicts with `AGENTS.md`, the person wins, and the change is recorded in DECISIONS.md.

## DECISIONS.md

One entry per decision a future session would otherwise re-debate, numbered in order. Numbers are never reused or removed. A decision that changes gets a new entry, and the old one becomes a one-line stub: `**D-NNN — Title** (date) — superseded by D-xxx: <what replaced it>.` Write each entry as `**D-NNN — Title** (date)`, then:

- **What was decided**, precisely enough to check the code against.
- **Why**: what prompted it (a bug, the person's request, a measurement) and the reason, in a line or two.
- ***Alternatives:*** what was considered and why not. This stops the next session proposing them again.

Leave out how the work went (branches, sessions, test counts): the decision and its reasons are what a later reader checks the code against. The file was pruned this way once, before the first public commit (D-304).

Each heading ends with the area tags that fit, from the Tags table at the top of the file (`` `editor` `schema` ``). `grep -n '`editor`' docs/DECISIONS.md` lists an area's decisions. A unit test (`tests/unit/test_decisions.py`) fails on a missing or unknown tag, or a gap in the numbers; a new tag goes in the table first.

Code, commits, tests and other docs point to entries by number (`D-284`), so the reason for a line of code is one search away.

## ARCHITECTURE.md's module map

The first rule of the working agreement is *reuse before you write*: before writing a function, look for one that does the job. The module map is where that search starts. Each module has a row naming its public functions and what they do. Some concepts have exactly one owner (units parsing, netlist generation, running ngspice, the pot model and others listed in `AGENTS.md`); the map shows where each lives. A function missing from the map gets written again, and then there are two to keep in step.

## Where the notes live

`notes/` is at the top of the repo and git-ignored. It holds what belongs to one maintainer's work and not to the project: specs for work in hand, the plan, test lists. Nothing in the repo depends on it, and a fresh clone has none. What the project needs to keep from a piece of work goes into the repo as it's built: the decisions into DECISIONS.md, what the app now does into SPEC.md, the modules into ARCHITECTURE.md.

## Starting something new

A new piece of work gets its own spec and its own phases, both in `notes/`:

1. **The spec**, `notes/<NAME>-SPEC.md` (for the Mac app, `notes/MAC-APP-SPEC.md`). The agent drafts it from what the person asks for, after reading the code it touches: the goal, what the person gets, how it works, what's out of scope, the decisions it will need, the open questions. The person reads it and answers the questions. A small change (a fix, one dialog) needs no spec: it goes straight into the plan.
2. **The phases**, in `notes/PHASES.md`, written from the spec in the layout below and agreed by the person before anything is built.
3. **The work**, a phase at a time. As each phase lands, its decisions go into DECISIONS.md and SPEC.md is brought up to date, so that when the work is done the repo says everything a later session needs and the spec in `notes/` can be thrown away.

`docs/SPEC.md` is never where new work is planned: it describes the app as it is.

## PHASES.md

`notes/PHASES.md` holds the work in hand and nothing else. When a body of work is finished and accepted, move its phases and session notes to an archive beside it (`notes/PHASES-<name>.md`), so the plan a session reads at its start stays short.

Work happens in phases; a session works only on the current one. Something needed from a later phase is noted there, not built. Each phase's checklist gets ticked as items land, and the person accepts a phase against its *Accept when* line.

A session ends by:

1. running the full test suite (`make check`, `make accept`);
2. ticking the phase's checklist;
3. adding its decisions to DECISIONS.md;
4. updating ARCHITECTURE.md's module map;
5. writing a 3-5 line **Next session** note at the bottom of PHASES.md: what's done, what's next, anything waiting on the person.

The next session reads `AGENTS.md`, this page and PHASES.md first, and searches DECISIONS.md for the area it's changing (D-306).

On a fresh clone there's no `notes/` folder. The agent gets the machine ready (`make dev-image`, `make hooks`, `make check`), asks what to work on, writes a spec in `notes/` if the work needs one (see Starting something new), and writes the plan in `notes/PHASES.md` in this layout for the person to agree:

```markdown
# Plan

## Phase 1: <goal in a few words>
<What it's for, in a line or two.>
- [ ] <item>
- [ ] <item>
*Accept when:* <what the person checks to accept it>

## Notes
2026-11-12: <what this session did>

## Next session
<3-5 lines: what's done, what's next, anything waiting on the person>
```

## What doesn't go here

- **Throwaway work** (exploration scripts, dumps, scratch screenshots) goes in `scratch/`, which git ignores.
- **An agent's own memory** (Claude Code keeps notes per machine, outside the repo) is for working preferences only. Anything the project depends on goes in these files, where every session and every person sees it.
