"""*Build a full layout* as a job (D-399): the seed sets and budgets, a stopped run ends
its workers, and the flat attempt (D-403)."""

import multiprocessing as mp
import threading
from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard import compact_job
from solum.stripboard.board import Layout, StandUp
from solum.stripboard.compact import problem

LIBRARY = Path(__file__).resolve().parents[2] / "library"


def test_seed_sets_and_budgets() -> None:
    assert compact_job.seeds_for(1) == [1, 2, 3, 4]
    assert compact_job.seeds_for(2) == [5, 6, 7, 8]
    assert compact_job.steps_for(10, False) == 10 * compact_job.STEPS_PER_PART
    assert compact_job.steps_for(10, True) == 4 * compact_job.steps_for(10, False)
    most = compact_job.MOST_PARTS * compact_job.STEPS_PER_PART
    assert compact_job.steps_for(compact_job.MOST_PARTS + 30, False) == most


def test_a_stopped_run_ends_with_its_best_so_far_and_no_worker_left() -> None:
    """Stop set at the first report: every worker stops at its next check; the run says
    it was stopped and leaves no process behind."""
    circuit = load_circuit(LIBRARY / "starters" / "ts808.json")
    models, table = load_models([LIBRARY / "models"]), footprint_table(LIBRARY)
    pb = problem(None, circuit, models, table)
    stop = threading.Event()
    reports: list[int] = []

    def report(done: int, _of: int, _best: object) -> None:
        reports.append(done)
        stop.set()

    got = compact_job.run(pb, None, circuit, (), False, 1, load_settings(), report, stop)
    assert got.stopped and reports
    assert reports[-1] < compact_job.ATTEMPTS * compact_job.steps_for(len(pb.refs), False)
    assert mp.active_children() == []


def test_a_run_adds_the_flat_attempt_once_per_board_when_parts_may_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-403: When needed, a run is five attempts, the fifth lying everything flat, and
    its best is no worse on limits and warnings than that flat board; Try another runs
    four (the flat board kept from the first try); Never runs four (all flat already).
    Few steps, to be quick: the steps are counted in the server, so the workers take them."""
    monkeypatch.setattr(compact_job, "STEPS_PER_PART", 40)
    monkeypatch.setattr(compact_job, "_flat", {})
    circuit = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
    models, table = load_models([LIBRARY / "models"]), footprint_table(LIBRARY)
    settings = load_settings()

    def attempts(choice: StandUp, attempt: int) -> tuple[compact_job.Run, int]:
        layout = Layout(0, 0, (), stand_up=choice)
        pb = problem(layout, circuit, models, table)
        of: list[int] = []
        got = compact_job.run(pb, layout, circuit, (), False, attempt, settings,
                              lambda _d, n, _b: of.append(n), threading.Event())  # fmt: skip
        return got, of[-1] // compact_job.steps_for(len(pb.refs), False)

    first, n = attempts("needed", 1)
    assert n == compact_job.ATTEMPTS + 1 and len(compact_job._flat) == 1
    (flat,) = compact_job._flat.values()
    assert first.best is not None and flat is not None
    assert first.best.key[:2] <= flat.key[:2]
    assert attempts("needed", 2)[1] == compact_job.ATTEMPTS
    assert attempts("never", 1)[1] == compact_job.ATTEMPTS
