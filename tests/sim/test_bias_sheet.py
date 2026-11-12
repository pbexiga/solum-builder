"""The bias sheet (9d1) from the starters and small circuits, through real ngspice."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.bias_sheet import bias_sheet, supply_text
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.models import load_models
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

LIBRARY = Path(__file__).resolve().parents[2] / "library"
STARTERS = LIBRARY / "starters"
Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([LIBRARY / "models"]))


def pins(sheet_parts: list, ref: str) -> dict[str, tuple[int | None, float]]:  # type: ignore[type-arg]
    part = next(p for p in sheet_parts if p.ref == ref)
    return {r.pin: (r.number, r.volts) for r in part.pins}


def test_the_tone_bender_says_how_to_set_its_trimmer(sim: Simulator) -> None:
    sheet = bias_sheet(load_circuit(STARTERS / "tone-bender-mk2-mode.json"), sim)
    assert sheet.trimmers[0].startswith("Set TR1 until Q2's collector reads \u22120.16 V (about ")
    assert sheet.trimmers[1].startswith("TR2: at 10% of its turn, as saved; its wiper reads ")
    # the solved trimmer holds its target on the sheet's own readings
    assert pins(sheet.parts, "Q2")["C"][1] == pytest.approx(-0.16, abs=2e-3)
    assert [p.ref for p in sheet.parts] == ["Q1", "Q2", "Q3"]
    assert list(sheet.supply) == ["V-"] and sheet.supply["V-"] < 0
    drawn = supply_text(sheet.supply)
    assert drawn.startswith("The circuit draws ") and "\u2212" not in drawn
    assert sheet.pots == [] and sheet.warnings == []


def test_a_chip_is_one_part_with_its_pin_numbers(sim: Simulator) -> None:
    sheet = bias_sheet(load_circuit(STARTERS / "ts808.json"), sim)
    ic1 = pins(sheet.parts, "IC1")
    assert [n for n, _ in ic1.values()] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert ic1["V+"][1] == pytest.approx(9.0, abs=1e-3) and ic1["V-"][1] == pytest.approx(
        0.0, abs=1e-6
    )
    assert ic1["A out"][1] == pytest.approx(4.5, abs=0.1)  # biased at half the supply
    assert sheet.trimmers == []


def test_compensation_pins_are_not_read(sim: Simulator) -> None:
    sheet = bias_sheet(load_circuit(STARTERS / "proco-rat.json"), sim)
    assert set(pins(sheet.parts, "IC1")) == {"+", "-", "out", "V+", "V-"}


def test_a_pot_that_moves_the_bias_is_listed(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("pot-biased stage")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="100n")
        .part("VR1", "pot", "V+", "b", "0", value="100k", rotation=0.5, label="Bias")
        .part("R1", "resistor", "V+", "c", value="10k")
        .part("R2", "resistor", "e", "0", value="1k")
        .part("Q1", "bjt", "c", "b", "e", model="2N5089")
        .part("C2", "capacitor", "c", "out", value="100n")
        .part("VR2", "pot", "out", "vol", "0", value="100k", label="Volume")
        .part("OUT", "amp", "vol")
        .build()
    )
    sheet = bias_sheet(c, sim)
    assert len(sheet.pots) == 1
    assert sheet.pots[0].startswith("VR1 (Bias) at 50% of its turn, as saved: turning it moves")


def test_a_saturated_stage_is_flagged(sim: Simulator, circuit: Builder) -> None:
    c = (
        circuit("hard-on BJT")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "b", value="100n")
        .part("R6", "resistor", "V+", "b", value="10k")
        .part("R7", "resistor", "V+", "c", value="10k")
        .part("Q1", "bjt", "c", "b", "0", model="2N5089")
        .build()
    )
    assert bias_sheet(c, sim).warnings


def test_the_bias_sheet_opens_and_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(load_settings()))
    page = client.get("/api/export/starter/tone-bender-mk2-mode/bias.html")
    assert page.status_code == 200 and "Set TR1 until Q2&#x27;s collector" in page.text
    got = client.get("/api/export/starter/tone-bender-mk2-mode/bias.pdf")
    assert got.status_code == 200 and got.content.startswith(b"%PDF")
    assert "bias sheet.pdf" in got.headers["content-disposition"]
