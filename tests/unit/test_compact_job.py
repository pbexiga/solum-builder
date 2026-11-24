"""*Build a full layout* as a job (D-399): the seed sets and budgets, and a stopped run
ends its workers."""

import multiprocessing as mp
import threading
from pathlib import Path

from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard import compact_job
from solum.stripboard.compact import problem

LIBRARY = Path(__file__).resolve().parents[2] / "library"


def test_seed_sets_and_budgets() -> None:
    assert compact_job.seeds_for(1) == [1, 2, 3, 4]
    assert compact_job.seeds_for(2) == [5, 6, 7, 8]
    assert compact_job.steps_for(10, False) == 10 * compact_job.STEPS_PER_PART
    assert compact_job.steps_for(10, True) == 4 * compact_job.steps_for(10, False)


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
