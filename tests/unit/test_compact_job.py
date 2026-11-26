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
    assert compact_job.steps_for(10) == 10 * compact_job.STEPS_PER_PART
    most = compact_job.MOST_PARTS * compact_job.STEPS_PER_PART
    assert compact_job.steps_for(compact_job.MOST_PARTS + 30) == most


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

    got = compact_job.run(pb, None, circuit, 1, load_settings(), report, stop)
    assert got.stopped and reports
    assert reports[-1] < compact_job.ATTEMPTS * compact_job.steps_for(len(pb.refs))
    assert mp.active_children() == []


def test_every_try_adds_its_own_flat_attempt_when_parts_may_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-403: When needed, a try is five attempts, the fifth lying everything flat with the
    try's first seed, so Try another runs five too and finds its own boards (reusing the
    first try's flat board gave it back, the user, 2026-11-26). Never runs four (all flat
    already). Few steps, to be quick: the steps are counted in the server, so the workers
    take them."""
    monkeypatch.setattr(compact_job, "STEPS_PER_PART", 40)
    circuit = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
    models, table = load_models([LIBRARY / "models"]), footprint_table(LIBRARY)
    settings = load_settings()

    def attempts(choice: StandUp, attempt: int) -> tuple[compact_job.Run, int]:
        layout = Layout(0, 0, (), stand_up=choice)
        pb = problem(layout, circuit, models, table)
        of: list[int] = []
        got = compact_job.run(pb, layout, circuit, attempt, settings,
                              lambda _d, n, _b: of.append(n), threading.Event())  # fmt: skip
        return got, of[-1] // compact_job.steps_for(len(pb.refs))

    for attempt in (1, 2):
        needed, n = attempts("needed", attempt)
        never = attempts("never", attempt)
        assert n == compact_job.ATTEMPTS + 1 and never[1] == compact_job.ATTEMPTS
        assert needed.best is not None and never[0].best is not None


def test_when_no_attempt_finds_a_board_the_rest_of_never_s_seeds_run_flat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-403: When needed falls back to the starting board only where Never would. The
    BD-2 at 2 steps a part: every attempt ends with a problem (a net not joined), so the
    run adds Never's seeds 2–4, flat (seed 1 is the flat attempt): eight attempts in all,
    and no board, as Never's own run."""
    monkeypatch.setattr(compact_job, "STEPS_PER_PART", 2)
    circuit = load_circuit(LIBRARY / "starters" / "boss-bd2.json")
    models, table = load_models([LIBRARY / "models"]), footprint_table(LIBRARY)

    def attempts(choice: StandUp) -> tuple[compact_job.Run, int]:
        layout = Layout(0, 0, (), stand_up=choice)
        pb = problem(layout, circuit, models, table)
        of: list[int] = []
        got = compact_job.run(pb, layout, circuit, 1, load_settings(),
                              lambda _d, n, _b: of.append(n), threading.Event())  # fmt: skip
        return got, of[-1] // compact_job.steps_for(len(pb.refs))

    needed, n = attempts("needed")
    assert needed.best is None and n == 2 * compact_job.ATTEMPTS
    never, n = attempts("never")
    assert never.best is None and n == compact_job.ATTEMPTS
