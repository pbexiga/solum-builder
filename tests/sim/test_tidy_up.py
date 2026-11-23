"""*Tidy up* on the starters' Start for me boards (P6f's *Accept when*, D-388): still
passing the check, none worse in size, cuts or links, and smaller. The quick ones only:
the biggest boards (BD-2, Klon, Dyna Comp) take 5–11 s each."""

from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.check import check_layout
from solum.stripboard.start import start_for_me
from solum.stripboard.tidy import key, tidy_up

LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
SMALLER = {  # Start for me's columns → at most these after Tidy up (measured 2026-11-21)
    "dallas-rangemaster": 9,  # 10×9
    "fuzz-face": 15,  # 18×9
    "tone-bender-mk2": 26,  # 28×12
    "ts808": 46,  # 49×21 (45 until D-389 put the pads on the edge, where Trim can't take them)
    "proco-rat": 48,  # 60×22 (47 until D-389)
}

pytestmark = pytest.mark.sim


@pytest.mark.parametrize("name", list(SMALLER))
def test_tidy_up_makes_start_for_me_boards_smaller(name: str) -> None:
    circuit = load_circuit(LIBRARY / "starters" / f"{name}.json")
    started = start_for_me(None, circuit, MODELS, TABLE, fill=False).layout
    tidied = tidy_up(started, circuit, MODELS, TABLE).layout
    checked = check_layout(tidied, circuit, MODELS, TABLE)
    assert checked.ok, checked.faults[:3]
    assert all(a <= b for a, b in zip(key(tidied)[:3], key(started)[:3], strict=True))
    assert tidied.strips <= started.strips and tidied.columns <= SMALLER[name]
