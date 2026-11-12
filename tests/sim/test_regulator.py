"""The fixed regulator (D-227) through ngspice, against onsemi's MC78L12A figures: 12 V at
19 V in, 120 mV over 14.5-27 V (line), 20 mV over 1-100 mA (load), 1.7 V dropout, and
4.2 mA of bias current drawn from the input."""

from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary, load_models
from solum.netlist import NetlistError
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    models: ModelLibrary = load_models([REPO / "library" / "models"])
    return Simulator(engine, models)


def regulated(sim: Simulator, vin: float, load: str = "1M", model: str = "78L12") -> float:
    b = (
        CircuitBuilder("reg").rail("V+", 9)
        .part("V1", "vsource", "VS", "0", value=vin)
        .part("U1", "regulator", "VS", "o", "0", model=model)
        .part("R1", "resistor", "o", "0", value=load)
    )  # fmt: skip
    return sim.op(b.build()).voltages["o"]


def test_twelve_volts_at_the_sheets_input(sim: Simulator) -> None:
    assert regulated(sim, 19.0) == pytest.approx(12.0, abs=1e-3)


def test_line_and_load_regulation(sim: Simulator) -> None:
    line = regulated(sim, 27.0) - regulated(sim, 14.5)
    assert line == pytest.approx(0.12, abs=0.005)  # the sheet's 120 mV
    # 1 mA (12k) to 100 mA (120 Ω): the sheet's 20 mV
    load = regulated(sim, 19.0, "12k") - regulated(sim, 19.0, "120")
    assert load == pytest.approx(0.02, abs=0.002)


def test_below_dropout_the_output_follows_the_input(sim: Simulator) -> None:
    assert regulated(sim, 9.0) == pytest.approx(9.0 - 1.7, abs=0.01)
    assert regulated(sim, 0.0) == pytest.approx(0.0, abs=1e-3)
    # the corner is rounded over 0.1 V: 13.7 V in holds 11.9 V
    assert 11.85 < regulated(sim, 13.7) < 11.95


def test_a_model_of_another_type_is_refused(sim: Simulator) -> None:
    with pytest.raises(NetlistError, match="not a regulator"):
        regulated(sim, 19.0, model="TC1044S")


def test_the_input_draws_the_load_and_the_bias_current(sim: Simulator) -> None:
    b = (
        CircuitBuilder("reg").rail("V+", 19)
        .part("U1", "regulator", "V+", "o", "0", model="78L12")
        .part("R1", "resistor", "o", "0", value="1k2")
    )  # fmt: skip
    op = sim.op(b.build())
    assert op.supply["V+"] == pytest.approx(op.voltages["o"] / 1200 + 4.2e-3, rel=1e-3)
