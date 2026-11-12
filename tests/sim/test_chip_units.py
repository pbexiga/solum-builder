"""The 4049 and the OTAs (D-180) through ngspice, as pedals use them.

A 4049 inverter biased by a feedback resistor from out to in sits at its own switching
point (no DC flows in the resistor), and with 100 kΩ in and 1 MΩ back its gain is
10 · A / (A + 11) for an open-loop gain A: TI's Figure 5-7 slope at 10 V, 24.5 to 30.9,
gives 6.9 to 7.4 (the card's A at 9 V is 32, so 7.4).

An OTA's small-signal gain into a load RL is gm · RL with gm = Iabc / 2VT (the sheets'
9600 µS at 500 µA is 500 µA / 52 mV), so it follows the bias current set by a resistor.
"""

from pathlib import Path

import numpy as np
import pytest

from solum.circuit.build import CircuitBuilder
from solum.model_checks import inverter_switch
from solum.models import ModelLibrary, load_models
from solum.netlist import Ac, Op, generate_netlist
from solum.sim.native import NativeNgspice

REPO = Path(__file__).parents[2]
VT = 1.380649e-23 * 300.15 / 1.602176634e-19  # thermal voltage at ngspice's 27 °C


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


def _gain_at_1k(engine: NativeNgspice, models: ModelLibrary, b: CircuitBuilder, node: str) -> float:
    netlist = generate_netlist(b.build(), models, Ac(start=100, stop=10e3, per_decade=10))
    plot = engine.run(netlist.text).plot("ac")
    freq = plot.vectors["frequency"].real
    return float(np.interp(1e3, freq, np.abs(plot.vectors[netlist.node(node)])))


def _op(engine: NativeNgspice, models: ModelLibrary, b: CircuitBuilder) -> dict[str, float]:
    netlist = generate_netlist(b.build(), models, Op())
    vectors = engine.run(netlist.text).plot("op").vectors
    return {net: float(vectors[n][0].real) for net, n in netlist.nodes.items() if n in vectors}


def _stage() -> CircuitBuilder:
    b = CircuitBuilder("4049 stage").rail("V+", 9.0).part("IN", "guitar", "in")
    b.part("C1", "capacitor", "in", "a", value="10u").part("R1", "resistor", "a", "g", value="100k")
    b.part("R2", "resistor", "g", "x", value="1M")
    b.part("IC1A", "inverter", "g", "x", model="CD4049UB", half="a")
    for unit in "bcdef":
        b.part(f"IC1{unit.upper()}", "inverter", "0", model="CD4049UB", half=unit)
    return b.part("OUT", "amp", "x")


def test_a_biased_4049_sits_at_its_switching_point(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    op = _op(engine, models, _stage())
    switch = inverter_switch(engine, models, models.get("CD4049UB"), 9.0)
    assert op["x"] == pytest.approx(switch, abs=2e-3)
    assert op["g"] == pytest.approx(switch, abs=2e-3)


def test_a_biased_4049_amplifies_by_its_feedback_and_open_loop_gain(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    assert 6.9 <= _gain_at_1k(engine, models, _stage(), "x") <= 7.6


def _vca(model: str, rabc: float, supply: tuple[str, str] = ("V+", "0")) -> CircuitBuilder:
    """An OTA amplifier at 9 V: + input on the signal over a stiff 4.5 V reference, - on
    the reference, the output loaded by 10 kΩ to it, Iabc through `rabc` from the supply.
    `supply` is the chip's V+ and V- nets."""
    b = CircuitBuilder("vca").rail("V+", 9.0).part("IN", "guitar", "in")
    b.part("V1", "vsource", "VREF", "0", value=4.5)
    b.part("C2", "capacitor", "in", "p", value="10u")
    b.part("R3", "resistor", "p", "VREF", value="10k")
    b.part("R4", "resistor", "V+", "ib", value=rabc)
    b.part("R5", "resistor", "o", "VREF", value="10k")
    if model.startswith("LM13700"):
        b.part("IC1A", "ota", "p", "VREF", "o", "ib", model=model, half="a", supply=supply)
        b.part("IC1B", "ota", model=model, half="b")
    else:
        b.part("IC1", "ota", "p", "VREF", "o", "ib", model=model, supply=supply)
    return b.part("OUT", "amp", "o")


@pytest.mark.parametrize("model", ["CA3080", "LM13700"])
@pytest.mark.parametrize("rabc", [100e3, 1e6])
def test_an_ota_gain_is_gm_times_its_load(
    engine: NativeNgspice, models: ModelLibrary, model: str, rabc: float
) -> None:
    b = _vca(model, rabc)
    op = _op(engine, models, b)
    iabc = (9.0 - op["ib"]) / rabc
    gain = _gain_at_1k(engine, models, b, "o") / _gain_at_1k(engine, models, b, "p")
    assert gain == pytest.approx(iabc / (2 * VT) * 10e3, rel=0.03)
    # balanced but for the + input's bias current through 10 kΩ (under 1 µA: < 10 mV)
    assert abs(op["p"] - op["VREF"]) < 0.01


@pytest.mark.parametrize("model", ["CA3080", "LM13700"])
def test_an_ota_with_its_supply_pin_open_still_solves(
    engine: NativeNgspice, models: ModelLibrary, model: str
) -> None:
    """Found by the mutation test (D-237): with V+ on nothing, the card's quiescent current
    (a fixed multiple of Iabc out of V+) had no source, ngspice spun past the timeout, and
    every later run in the process timed out with it (D-195). Unpowered, it draws none."""
    netlist = generate_netlist(_vca(model, 100e3, ("VX", "0")).build(), models, Op())
    vectors = engine.run(netlist.text, timeout=10).plot("op").vectors
    assert float(vectors[netlist.node("o")][0].real) == pytest.approx(4.5, abs=0.05)
