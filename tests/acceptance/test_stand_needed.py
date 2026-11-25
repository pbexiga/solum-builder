"""Build a full layout on every starter (D-403, D-404): the search's own counts agree with
the check's, and standing when needed is never worse than Never's first board.

- **The search counts as the check does**: the best board's limits broken and warnings
  (links near a high-gain input's parts, strips alongside one) as the search scored them
  equal what the check finds on it, laid out and again wired; a rule the two count
  differently (a bus's copper was left out of the search's strips alongside) would
  otherwise drop good boards silently.
- No Never run, except where When needed falls back: the flat attempt is Never's seed-1
  board, its counts checked here, and it's what the guarantee compares against. Where
  When needed falls back to Start a board's layout, Never must too (its other seeds run
  flat before that, D-403): only then is Never run, to check it.
- **When needed is no worse than Never's seed 1**: a When needed run includes a flat
  attempt, Never's own first board, and ranks limits, then warnings, first. Not Never's
  best of four: the gap to that is seed-to-seed variance, what Try another is for. When
  the flat attempt found no board without a problem there's nothing for it to beat
  (BD-2 Aion at these steps: a gap the first version of this test fell into).
- **No more standing parts than needed**: laying any one of the full layout's standing
  parts flat again (a leg kept in its hole, each flat shape) can't be done, or breaks a
  limit or adds a warning.

Fewer steps than the app's, to be quick: `make layout`, and `make accept` when the
layout code changed (D-405)."""

import threading
from pathlib import Path

import pytest

from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.config import load_settings
from solum.guides import footprint_table
from solum.models import ModelLibrary
from solum.probe import loud_inputs
from solum.simulate import Simulator
from solum.stripboard import compact_job
from solum.stripboard.apart import alongside
from solum.stripboard.board import Layout, StandUp
from solum.stripboard.check import copper_groups, read_layout
from solum.stripboard.compact import (
    Found,
    Problem,
    board_of,
    finish,
    lay_flat,
    positions,
    problem,
    standing_unneeded,
)
from solum.stripboard.limits import LoudInput, broken_limits, placement_limits
from solum.stripboard.quiet import guards, noisy_links

LIBRARY = Path(__file__).resolve().parents[2] / "library"
STARTERS = sorted((LIBRARY / "starters").glob("*.json"))
STEPS_PER_PART = 750  # a sixteenth of Quick's: still fails before both search fixes (D-405)

pytestmark = [pytest.mark.acceptance, pytest.mark.layout]


def counted(board: Layout, circuit: Circuit, models: ModelLibrary,
            loud: list[LoudInput]) -> tuple[int, int]:  # fmt: skip
    """The check's count: placement limits broken, then warnings."""
    table = footprint_table(LIBRARY)
    r, nets = read_layout(board, circuit, models, table), connect(circuit)
    broken = len(broken_limits(board, placement_limits(circuit, nets, r.board, loud)))
    warned = len(noisy_links(board, r.board, nets, guards(r.board, nets, loud)))
    warned += len(alongside(board, r.board, nets, loud, copper_groups(board)))
    return broken, warned


@pytest.mark.parametrize("path", STARTERS, ids=[p.stem for p in STARTERS])
def test_the_search_counts_as_the_check_and_needed_beats_never_s_first_board(
    path: Path, sim: Simulator, models: ModelLibrary, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(compact_job, "STEPS_PER_PART", STEPS_PER_PART)
    monkeypatch.setattr(compact_job, "_flat", {})
    circuit, table = load_circuit(path), footprint_table(LIBRARY)
    loud = loud_inputs(sim, circuit)

    def agrees(pb: Problem, found: Found) -> tuple[int, int]:
        """`found`'s counts, the search's equal to the check's laid out and wired."""
        searched = counted(board_of(pb, found), circuit, models, loud)
        assert found.key[:2] == searched, f"{path.stem}: searched {found.key[:2]}"
        if pb.stand_up == "needed":  # finishing lays unneeded standing parts flat first
            flat = lay_flat(pb, found)
            assert flat.key[:2] == counted(board_of(pb, flat), circuit, models, loud)
            searched = flat.key[:2]
        built = finish(pb, found, models, table)
        if not built.fell_back:
            assert counted(built.layout, circuit, models, loud) == searched
        return searched

    def run(choice: StandUp) -> tuple[Problem, Found | None]:
        layout = Layout(0, 0, (), stand_up=choice)
        pb = problem(layout, circuit, models, table, loud)
        got = compact_job.run(pb, layout, circuit, loud, False, 1, load_settings(),
                              lambda *_: None, threading.Event())  # fmt: skip
        return pb, got.best

    pb, best = run("needed")
    (flat,) = compact_job._flat.values()
    if best is None:  # every board had a problem: Start a board's kept, and Never's too
        assert flat is None
        assert run("never")[1] is None, f"{path.stem}: When needed fell back, Never didn't"
    elif flat is None:  # no flat board without a problem: nothing for it to beat
        agrees(pb, best)
    else:
        assert agrees(pb, best) <= agrees(pb, flat)
    if best is not None and not (built := finish(pb, best, models, table)).fell_back:
        assert standing_unneeded(pb, positions(pb, built.layout)) == []
