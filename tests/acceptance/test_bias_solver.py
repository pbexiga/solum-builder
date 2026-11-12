"""Phase 1 acceptance: a JFET common-source stage with a 9 V drain target solves to
9.0 ± 0.1 V for each JFET model in the library (and with measured Idss/Vp)."""

from typing import Any

import pytest

from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary, load_models
from solum.simulate import Simulator
from tests.acceptance.conftest import REPO

JFETS = load_models([REPO / "library" / "models"]).ids("jfet")


def common_source(model: str, measured: dict[str, float] | None = None) -> CircuitBuilder:
    extra: dict[str, Any] = {"measured": measured} if measured else {}
    return (
        CircuitBuilder(f"{model} common source")
        .rail("V+", 18.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "g", value="100n")
        .part("R1", "resistor", "g", "0", value="1M")
        .part("Q1", "jfet", "d", "g", "s", model=model, **extra)
        .part("R2", "resistor", "s", "0", value="1k")
        .part("C2", "capacitor", "s", "0", value="22u")
        .part("TR1", "trimmer", "V+", "d", None, value="100k",
              bias_target={"node": "Q1.D", "volts": 9.0})
    )  # fmt: skip


@pytest.mark.parametrize("model", JFETS)
def test_drain_solves_to_9v(sim: Simulator, models: ModelLibrary, model: str) -> None:
    c = common_source(model).build()
    op = sim.op(c)
    assert op.voltages[sim.resolve(c, "Q1.D")] == pytest.approx(9.0, abs=0.1)
    assert sim.ac(c).valid  # biased into its active region, so the AC curve is usable


def test_measured_part_solves_too(sim: Simulator) -> None:
    c = common_source("J201", {"idss": 0.45e-3, "vp": -0.6}).build()
    assert sim.op(c).voltages[sim.resolve(c, "Q1.D")] == pytest.approx(9.0, abs=0.1)
