# Contributing

Thanks for wanting to help. Read `AGENTS.md` first: it is the working agreement for this repo
(coding standards, testing layers, where code goes), and it applies to people as much as to agents.

## Proposing a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the idea before
   you spend time on it.
2. Fork the repo and make a branch.
3. Keep the change small and focused, with its tests written alongside the code.
4. Open a pull request and fill in the template. Every pull request is reviewed by the owner
   (see `CODEOWNERS`); nothing merges without that.

## Before you open the pull request

- `make check` must pass (ruff, the browser-code check, mypy, unit, sim, rules and parity tests).
  For UI or classic-circuit changes, `make accept` too.
- Any choice a later contributor would otherwise re-debate (a library, a format, an algorithm, a
  trade-off) goes in `docs/DECISIONS.md` in the same change.
- New public functions or modules get a line in the module map in `docs/ARCHITECTURE.md`.
- Follow `docs/DESIGN.md` for anything visual. Don't redraw the logo.
- Expected values for classic circuits come from published sources, stored with a link. Never
  fill them in from memory.

## Licence

By contributing you agree that your contribution is released under the repo's licence: MIT with
the Commons Clause (see `LICENSE`).

## Security problems

Don't report these in public. See `SECURITY.md`.
