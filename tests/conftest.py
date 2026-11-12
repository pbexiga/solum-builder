"""Shared test fixtures. Circuits are built with `solum.circuit.build.CircuitBuilder`
(the one circuit builder, also used by the app's part views)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder

REPO = Path(__file__).resolve().parent.parent
LAYERS = ("unit", "sim", "acceptance", "parity", "rules", "ui")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark each test with its layer, taken from its folder under tests/."""
    for item in items:
        parts = Path(str(item.fspath)).relative_to(REPO / "tests").parts
        if parts and parts[0] in LAYERS and parts[0] != "unit":
            item.add_marker(getattr(pytest.mark, parts[0]))


@pytest.fixture
def circuit() -> Callable[..., CircuitBuilder]:
    """Factory for fresh `CircuitBuilder`s."""
    return CircuitBuilder


@pytest.fixture
def repo() -> Path:
    return REPO
