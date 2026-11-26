"""*Start for me* on every starter (P6f's *Accept when*, D-387): a board that passes the
check, the same every run; well under a second (a timing test, `make perf`); a starter
with a part no board takes is refused in words."""

import time
from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.check import check_layout
from solum.stripboard.start import StartError, start_for_me

LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
STARTERS = sorted((LIBRARY / "starters").glob("*.json"))
NO_BOARD: dict[str, str] = {}  # starter: why it's refused (a part with no footprint)

pytestmark = pytest.mark.sim


@pytest.mark.parametrize("path", STARTERS, ids=[p.stem for p in STARTERS])
def test_start_for_me_lays_out_every_starter(path: Path) -> None:
    circuit = load_circuit(path)
    if path.stem in NO_BOARD:
        with pytest.raises(StartError, match=NO_BOARD[path.stem]):
            start_for_me(None, circuit, MODELS, TABLE)
        return
    first = start_for_me(None, circuit, MODELS, TABLE)
    checked = check_layout(first.layout, circuit, MODELS, TABLE)
    assert checked.ok, checked.faults[:3]
    assert start_for_me(None, circuit, MODELS, TABLE) == first


@pytest.mark.timing
@pytest.mark.parametrize("path", STARTERS, ids=[p.stem for p in STARTERS])
def test_start_for_me_is_quick(path: Path) -> None:
    """Well under a second on a desktop (the Klons, the biggest, ~0.5 s); 2 s leaves room
    for a slow runner, on an idle machine (`make perf`)."""
    circuit = load_circuit(path)
    if path.stem in NO_BOARD:
        return
    began = time.perf_counter()
    start_for_me(None, circuit, MODELS, TABLE)
    assert time.perf_counter() - began < 2.0
