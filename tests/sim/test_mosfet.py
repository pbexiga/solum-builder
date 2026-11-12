"""A MOSFET (D-175) through ngspice: off, fully on, and its body diode; as a gain stage,
its drain solved by a trimmer and its row in the Bias & headroom pane (D-176).

The 2N7000 card against its sheet (Fairchild Rev. 2.10): with the gate at 0 V the drain
leaks under 1 µA at 48 V (IDSS max), so a 10 kΩ load to 9 V drops under 10 mV; at VGS = 10 V
RDS(on) is 1.2 Ω typical (5 Ω max), so 9 V through 1 kΩ leaves the drain under
9 · 5 / 1005 = 45 mV; turned round (drain pulled 9 V below the source through 1 kΩ, about
8 mA) the body diode conducts at 0.62 to 0.69 V (Figure 8, 25 °C: 1 mA at 0.618 V,
11 mA at 0.688 V).
"""

from pathlib import Path

import pytest

from solum.analysis.dc import mosfet_vds_sat
from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary, load_models
from solum.netlist import Op, generate_netlist
from solum.probe import part_view, stages_view
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


def drain_volts(
    engine: NativeNgspice,
    models: ModelLibrary,
    gate: float,
    supply: float,
    load: float,
    model: str = "2N7000",
) -> float:
    c = (
        CircuitBuilder("mosfet switch")
        .part("V1", "vsource", "VS", "0", value=supply)
        .part("V2", "vsource", "g", "0", value=gate)
        .part("R1", "resistor", "VS", "d", value=load)
        .part("Q1", "mosfet", "d", "g", "0", model=model)
    )
    netlist = generate_netlist(c.build(), models, Op())
    return float(engine.run(netlist.text).plot("op").vectors[netlist.node("d")][0].real)


def test_off_the_drain_sits_at_the_supply(engine: NativeNgspice, models: ModelLibrary) -> None:
    assert drain_volts(engine, models, 0.0, 9.0, 10e3) == pytest.approx(9.0, abs=0.01)


def test_on_the_drain_falls_to_its_on_resistance(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    assert 0.0 < drain_volts(engine, models, 10.0, 9.0, 1e3) < 0.045


def test_the_body_diode_conducts_turned_round(engine: NativeNgspice, models: ModelLibrary) -> None:
    assert -0.69 < drain_volts(engine, models, 0.0, -9.0, 1e3) < -0.62


def common_source() -> CircuitBuilder:
    """A 2N7000 gain stage (D-176): gate at 9 · 1M / 2M5 = 3.6 V, 1 kΩ source leg, the drain
    load a 50k trimmer wired as a rheostat (lug 1 to V+, wiper and lug 3 to the drain)."""
    return (
        CircuitBuilder("common source")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "g", value="100n")
        .part("R1", "resistor", "V+", "g", value="1M5")
        .part("R2", "resistor", "g", "0", value="1M")
        .part(
            "TR1",
            "trimmer",
            "V+",
            "d",
            "d",
            value="50k",
            bias_target={"node": "Q1.D", "volts": 4.5},
        )
        .part("R3", "resistor", "s", "0", value="1k")
        .part("C2", "capacitor", "s", "0", value="22u")
        .part("Q1", "mosfet", "d", "g", "s", model="2N7000")
        .part("C3", "capacitor", "d", "out", value="100n")
        .part("OUT", "amp", "out")
    )


def test_a_trimmer_sets_a_mosfets_drain(engine: NativeNgspice, models: ModelLibrary) -> None:
    sim = Simulator(engine, models)
    c = common_source().build()
    op = sim.op(c)
    assert op.voltages[sim.resolve(c, "Q1.D")] == pytest.approx(4.5, abs=1e-3)
    assert 0 < op.bias["TR1"] < 1


def test_a_mosfet_stage_in_the_bias_pane(engine: NativeNgspice, models: ModelLibrary) -> None:
    """Its room down is to the edge of saturation, VGS - VTO (or 0.2 V), above the source;
    up, to the 9 V rail."""
    sim = Simulator(engine, models)
    c = common_source().build()
    (row,) = stages_view(sim, c)["rows"]
    assert (row["label"], row["role"]) == ("Q1", "gain stage")
    v = sim.op(c).voltages
    d, g, s = (v[sim.resolve(c, f"Q1.{pin}")] for pin in "DGS")
    vto = models.get("2N7000").param("vto")
    assert vto is not None
    assert row["bias"]["up"] == pytest.approx(9.0 - d)
    assert row["bias"]["down"] == pytest.approx(d - s - mosfet_vds_sat(g - s, vto))


def test_a_depletion_mosfet_is_on_at_zero_gate(engine: NativeNgspice, models: ModelLibrary) -> None:
    """D-178, the LND150 against Microchip's DS20005454A: IDSS 1 to 3 mA at VGS 0, VDS 25 V,
    so 25 V through 1 kΩ drops 1 to 3 V; at VGS -3 V (VGS(off) is -1 to -3 V at 100 nA) it's off."""
    assert models.get("LND150").depletion and not models.get("2N7000").depletion
    assert 23.0 < drain_volts(engine, models, 0.0, 26.0, 1e3, "LND150") < 25.0
    assert drain_volts(engine, models, -3.0, 9.0, 10e3, "LND150") == pytest.approx(9.0, abs=0.01)


def test_a_depletion_mosfets_view(engine: NativeNgspice, models: ModelLibrary) -> None:
    """Its transfer curve starts half a volt below VTO, so the dot at VGS 0 is on it."""
    c = (
        CircuitBuilder("self-biased")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "d", value="2k2")
        .part("Q1", "mosfet", "d", "0", "s", model="LND150")
        .part("R2", "resistor", "s", "0", value="1k")
    ).build()
    d = part_view(Simulator(engine, models), c, "Q1", "soft")["detail"]
    vto = models.get("LND150").param("vto")
    assert d["depletion"] and vto is not None
    assert d["curve"]["v"][0] == pytest.approx(min(vto, d["vgs"]) - 0.5, abs=0.01)
    assert d["curve"]["v"][0] < d["vgs"] < 0 < d["curve"]["v"][-1]
