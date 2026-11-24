"""High-gain stages for the placement limits (D-400), through real ngspice: a stage on
the signal path whose own gain reaches 10× with the pots as set, all down or all up."""

from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.models import load_models
from solum.probe import loud_inputs
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).resolve().parents[2]
STARTERS = REPO / "library" / "starters"


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


@pytest.mark.parametrize(
    ("name", "loud"),
    [
        ("ts808", [("IC1B", "+")]),  # the clipping stage, not the buffers either side
        ("proco-rat", [("IC1", "+")]),
        ("dallas-rangemaster", [("Q1", "B")]),
        ("mxr-dyna-comp", []),  # a compressor: no stage of 10×
    ],
)
def test_the_high_gain_stages_are_found_by_their_own_gain(
    sim: Simulator, name: str, loud: list[tuple[str, str]]
) -> None:
    found = loud_inputs(sim, load_circuit(STARTERS / f"{name}.json"))
    assert [(x.ref, x.pin) for x in found] == loud


def test_each_input_comes_with_the_nets_ac_quiet_beside_it(sim: Simulator) -> None:
    """D-400 narrowed (P6h5e): a net under 1 % of the input's signal is quiet: the rails,
    ground and the Rat's Vref behind its cap, not the input's own net nor the stage's
    output."""
    (rat,) = loud_inputs(sim, load_circuit(STARTERS / "proco-rat.json"))
    assert {"GND", "V+", "VREF"} <= rat.quiet
    assert "IC1.+" not in rat.quiet and "IC1.out" not in rat.quiet
    (q1,) = loud_inputs(sim, load_circuit(STARTERS / "dallas-rangemaster.json"))
    assert {"GND", "V-"} <= q1.quiet and "Q1.B" not in q1.quiet
