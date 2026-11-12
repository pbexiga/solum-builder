"""Phase 1 acceptance: the classic circuits in library/starters/ match the values
published for them (tests/fixtures/acceptance/*.expected.yaml, D-019 and D-034)."""

from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.simulate import Simulator
from tests.acceptance.conftest import REPO
from tests.acceptance.expected import Check, load_expected, run_check

EXPECTED = REPO / "tests" / "fixtures" / "acceptance"
STARTERS = REPO / "library" / "starters"


def _cases() -> list[tuple[Path, Check]]:
    return [
        (STARTERS / f"{e.circuit}.json", check)
        for path in sorted(EXPECTED.glob("*.expected.yaml"))
        for e in [load_expected(path)]
        for check in e.checks
    ]


def _marks(check: Check) -> list[pytest.MarkDecorator]:
    if check.pending:
        return [pytest.mark.skip(reason=f"pending: {check.pending}")]
    if check.known_gap:
        return [pytest.mark.xfail(reason=check.known_gap, strict=True)]
    return []


def _params() -> list[object]:
    return [
        pytest.param(
            path,
            check,
            id=f"{path.stem}:{check.id}",
            marks=_marks(check),
        )
        for path, check in _cases()
    ]


@pytest.mark.parametrize(("circuit_path", "check"), _params())
def test_published_value(sim: Simulator, circuit_path: Path, check: Check) -> None:
    outcomes = run_check(sim, load_circuit(circuit_path), check)
    failed = [o.detail for o in outcomes if not o.passed]
    assert not failed, f"{check.id}: " + "; ".join(failed)


def test_every_starter_has_expected_values() -> None:
    covered = {load_expected(p).circuit for p in EXPECTED.glob("*.expected.yaml")}
    assert covered == {p.stem for p in STARTERS.glob("*.json")}


def test_values_read_from_images_are_confirmed() -> None:
    """A value read off an image needs the user's check before it counts (D-042)."""
    unconfirmed = [
        f"{path.stem}:{check.id}"
        for path, check in _cases()
        if check.from_ == "image" and check.confirmed is None
    ]
    assert not unconfirmed, f"Ask the user to confirm: {', '.join(unconfirmed)}"


def test_every_starter_says_where_its_parts_list_comes_from() -> None:
    """Each starter's capacitor types, ratings and enclosure are cited (9d2, D-211)."""
    missing = [p.stem for p in EXPECTED.glob("*.expected.yaml") if load_expected(p).build is None]
    assert not missing, f"no `build` section: {', '.join(sorted(missing))}"
