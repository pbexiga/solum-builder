"""*Start for me* on every starter (P6f's *Accept when*, D-387): a board that passes the
check, the same every run, well under a second; a starter with a part no board takes is
refused in words."""

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
NO_BOARD = {  # a part with no through-hole footprint: refused, not laid out
    "marshall-bluesbreaker-aion": "DIP switches",
}

pytestmark = pytest.mark.sim


@pytest.mark.parametrize("path", STARTERS, ids=[p.stem for p in STARTERS])
def test_start_for_me_lays_out_every_starter(path: Path) -> None:
    circuit = load_circuit(path)
    if path.stem in NO_BOARD:
        with pytest.raises(StartError, match=NO_BOARD[path.stem]):
            start_for_me(None, circuit, MODELS, TABLE, fill=False)
        return
    began = time.perf_counter()
    first = start_for_me(None, circuit, MODELS, TABLE, fill=False)
    took = time.perf_counter() - began
    checked = check_layout(first.layout, circuit, MODELS, TABLE)
    assert checked.ok, checked.faults[:3]
    assert first.left == ()
    assert start_for_me(None, circuit, MODELS, TABLE, fill=False) == first
    assert took < 2.0  # well under a second on a desktop; room for a slow CI runner
