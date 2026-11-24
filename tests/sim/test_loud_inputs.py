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
    assert loud_inputs(sim, load_circuit(STARTERS / f"{name}.json")) == loud
