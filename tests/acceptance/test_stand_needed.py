"""Build a full layout on every starter under When needed (D-403, D-410): it falls back to
Start a board's layout only where Never would, and no part stands that could lie flat.

- No Never run, except where When needed falls back: the flat attempt is Never's seed-1
  board. Where When needed falls back to Start a board's layout, Never must too (its other
  seeds run flat before that, D-403): only then is Never run, to check it.
- **No more standing parts than needed**: laying any one of the full layout's standing
  parts flat again (a leg kept in its hole, each flat shape) can't be done without a
  problem on the board.

Fewer steps than the app's, to be quick: `make layout`, and `make accept` when the
layout code changed (D-405)."""

import threading
from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.guides import footprint_table
from solum.models import ModelLibrary
from solum.stripboard import compact_job
from solum.stripboard.board import Layout, StandUp
from solum.stripboard.compact import Found, Problem, finish, positions, problem, standing_unneeded

LIBRARY = Path(__file__).resolve().parents[2] / "library"
STARTERS = sorted((LIBRARY / "starters").glob("*.json"))
STEPS_PER_PART = 750  # a sixteenth of Quick's: still fails before both search fixes (D-405)

pytestmark = [pytest.mark.acceptance, pytest.mark.layout]


@pytest.mark.parametrize("path", STARTERS, ids=[p.stem for p in STARTERS])
def test_when_needed_falls_back_only_where_never_does_and_stands_nothing_unneeded(
    path: Path, models: ModelLibrary, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(compact_job, "STEPS_PER_PART", STEPS_PER_PART)
    monkeypatch.setattr(compact_job, "_flat", {})
    circuit, table = load_circuit(path), footprint_table(LIBRARY)

    def run(choice: StandUp) -> tuple[Problem, Found | None]:
        layout = Layout(0, 0, (), stand_up=choice)
        pb = problem(layout, circuit, models, table)
        got = compact_job.run(pb, layout, circuit, False, 1, load_settings(),
                              lambda *_: None, threading.Event())  # fmt: skip
        return pb, got.best

    pb, best = run("needed")
    (flat,) = compact_job._flat.values()
    if best is None:  # every board had a problem: Start a board's kept, and Never's too
        assert flat is None
        assert run("never")[1] is None, f"{path.stem}: When needed fell back, Never didn't"
    if best is not None and not (built := finish(pb, best, models, table)).fell_back:
        assert standing_unneeded(pb, positions(pb, built.layout)) == []
