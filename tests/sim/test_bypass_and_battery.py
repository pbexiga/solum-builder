"""The footswitch and battery blocks through real ngspice (D-143): bypassed, the dry
signal; on, the effect; on a battery, the circuit runs at the battery's voltage."""

from pathlib import Path

import numpy as np
import pytest

from solum.analysis.measures import gain_at
from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import circuit_to_dict, parse_circuit
from solum.circuit.schema import Circuit
from solum.models import load_models
from solum.sim.native import NativeNgspice
from solum.simulate import OpResult, Simulator
from tests.jig import FAR, core_block, jig

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def with_parts(circuit: Circuit, extra: CircuitBuilder) -> Circuit:
    """`circuit` with `extra`'s parts, joined to it by their labels, drawn far away."""

    def moved(item: dict[str, object]) -> dict[str, object]:
        x, y = item["pos"]  # type: ignore[misc]
        return {**item, "pos": [x + 2 * FAR, y + 2 * FAR]}

    data = circuit_to_dict(circuit)
    data["parts"] += [moved(p) for p in extra.parts]
    data["labels"] = [*data.get("labels", []), *(moved(lb) for lb in extra.labels)]
    return parse_circuit(data)


def with_effect(block_id: str) -> Circuit:
    """The bypass block in the jig, with a stand-in effect between send and return: a
    10k/10k divider, so On is 6 dB down and Bypassed isn't."""
    effect = (
        CircuitBuilder()
        .part("R801", "resistor", "send", "return", value="10k")
        .part("R802", "resistor", "return", "0", value="10k")
    )
    return with_parts(jig(core_block(block_id)), effect)


def gain_db(sim: Simulator, c: Circuit) -> float:
    ac = sim.ac(c)
    assert ac.valid, [s.message for s in ac.saturated]
    assert c.probes.out is not None
    return gain_at(ac.freq, ac.responses[c.probes.out], 1000.0)


@pytest.mark.parametrize("block", ["true-bypass-3pdt-v1", "buffered-bypass-3pdt-v1"])
def test_on_goes_through_the_effect_and_bypassed_does_not(sim: Simulator, block: str) -> None:
    c = with_effect(block)
    on = gain_db(sim, c)
    bypassed = gain_db(sim, c.with_part("SW1", position=1))
    if "buffered" in block:
        # The JFET follower loses a little, and its output impedance (a few hundred ohms
        # plus its output cap) driving the 20k stand-in costs a little more when on.
        assert -1.5 < bypassed < 0.0
        assert on == pytest.approx(bypassed - 6.02, abs=0.6)
    else:  # true bypass is a wire
        assert bypassed == pytest.approx(0.0, abs=0.01)
        assert on == pytest.approx(-6.02, abs=0.1)


def test_the_status_led_lights_only_when_on(sim: Simulator) -> None:
    """On, V+ feeds the LED through 4k7: about (9 V - its drop) / 4k7; bypassed, nothing."""
    c = with_effect("true-bypass-3pdt-v1")
    lit = sim.op(c)
    nets = connect(c)
    drop = lit.voltages[nets.net_of("LED1", "A")] - lit.voltages[nets.net_of("LED1", "K")]
    assert 1.5 < drop < 2.5  # a red LED, lit
    assert lit.supply["V+"] == pytest.approx((9.0 - drop) / 4700, rel=0.02)
    assert sim.op(c.with_part("SW1", position=1)).supply["V+"] == pytest.approx(0.0, abs=1e-6)


def powered(
    state: dict[str, object], plugged: bool | None, block_id: str = "battery-dc-power-v1"
) -> Circuit:
    """A power block with a plain (mono) guitar input, and 1 mA drawn from V+F; the
    battery's - is on its battery ground (D-164). `plugged`: the DC jack's plug (None:
    the block has no DC jack)."""
    block = core_block(block_id).with_part("BAT1", **state)
    rest = (
        CircuitBuilder()
        .part("IN", "guitar", "in")
        .part("R801", "resistor", "V+F", "0", value="9k")
        .part("OUT", "amp", "in")
    )
    c = with_parts(jig(block), rest)
    return c if plugged is None else c.with_part("DC", plugged=plugged)


def after_filter(c: Circuit, result: OpResult, volts: float, ohms: float = 47) -> None:
    """V+F is `volts` less the reverse-polarity Schottky's drop (D-260) and the filter's
    47 ohm drop (plus a battery's own resistance in `ohms`) at the current drawn."""
    v = result.voltages
    diode = v["V+"] - v[connect(c).net_of("D1", "K")]
    assert 0.1 < diode < 0.3  # a 1N5817 at about 1 mA
    i = (volts - diode) / (9000 + ohms)
    assert v["V+F"] == pytest.approx(volts - diode - ohms * i, abs=0.01)


def test_plugged_in_the_supply_powers_it(sim: Simulator) -> None:
    c = powered({"volts": 7.4, "state": "half"}, plugged=True)
    after_filter(c, sim.op(c), 9.0)


@pytest.mark.parametrize(("volts", "state"), [(9.0, "fresh"), (7.4, "half"), (5.5, "flat")])
def test_unplugged_the_battery_powers_it(sim: Simulator, volts: float, state: str) -> None:
    c = powered({"volts": volts, "state": state}, plugged=False)
    result = sim.op(c)
    after_filter(c, result, volts)
    i = result.voltages["V+F"] / 9000
    assert result.supply["V+"] == pytest.approx(i, rel=0.02)  # the draw is the battery's


def test_a_tired_battery_sags_under_load_through_its_resistance(sim: Simulator) -> None:
    c = powered({"volts": 7.4, "state": None, "resistance": "20"}, plugged=False)
    v = sim.op(c).voltages
    diode = v["V+"] - v[connect(c).net_of("D1", "K")]
    i = (7.4 - diode) / (9000 + 47 + 20)
    assert v["V+F"] == pytest.approx(7.4 - diode - 67 * i, abs=0.01)


@pytest.mark.parametrize(("volts", "state"), [(9.0, "fresh"), (6.6, "low")])
def test_a_battery_only_pedal_runs_on_its_battery(sim: Simulator, volts: float, state: str) -> None:
    """D-143: no DC jack, so the battery is the supply: V+ is the battery, its - on
    ground (D-164), the filter's 47 ohm drop after it."""
    result = sim.op(powered({"volts": volts, "state": state}, None, "battery-power-v1"))
    i = volts / (9000 + 47)
    assert result.voltages["V+"] == pytest.approx(volts, abs=0.01)
    assert result.voltages["V+F"] == pytest.approx(volts - 47 * i, abs=0.01)
    assert result.supply["V+"] == pytest.approx(i, rel=0.02)


def test_the_battery_block_alone_is_grounded(sim: Simulator) -> None:
    """The user's bug (2026-11-02): with no stereo input to ground it, v15's IN_ring left
    the battery floating (V+ 0 V, IN_ring -9 V). Its battery ground is ground (D-164)."""
    v = sim.op(core_block("battery-power-v1")).voltages
    assert v["V+"] == pytest.approx(9.0, abs=1e-3)
    assert v["V+F"] == pytest.approx(9.0, abs=1e-3)


def ring_pedal(cable: bool) -> Circuit:
    """A battery-only pedal switched by its stereo input jack (D-185): the battery's - on
    the ring, the sleeve on ground, 1 mA drawn from V+."""
    return (
        CircuitBuilder()
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("BAT1", "battery", "V+", "bneg")
        .part("J1", "jack", stereo=True, label="Input", plugged=cable,
              pins={"T": "in", "R": "bneg", "S": "0"})
        .part("R1", "resistor", "V+", "0", value="9k")
        .part("OUT", "amp", "in")
        .build()
    )  # fmt: skip


def test_a_cable_in_the_stereo_jack_switches_the_battery_on(sim: Simulator) -> None:
    on = sim.op(ring_pedal(cable=True))
    assert on.voltages["V+"] == pytest.approx(9.0, abs=0.01)
    assert on.supply["V+"] == pytest.approx(1e-3, rel=0.02)
    off = sim.op(ring_pedal(cable=False))
    assert off.voltages["V+"] == pytest.approx(0.0, abs=1e-3)  # the ring open: no supply


def test_a_battery_off_the_lug_stays_beside_the_adapter(sim: Simulator) -> None:
    """D-185: wired to V+ instead of the DC jack's battery lug, a 9.6 V battery behind 2 Ω
    pushes (9.6 - 9) / 2 = 0.3 A into the 9 V adapter, which holds V+."""
    c = (
        CircuitBuilder()
        .rail("V+", 9.0)
        .part("DC", "dcjack", "V+", "0")
        .part("BAT1", "battery", "V+", "0", volts=9.6, resistance="2")
        .part("R1", "resistor", "V+", "0", value="9k")
        .build()
    )
    result = sim.op(c)
    assert result.voltages["V+"] == pytest.approx(9.0, abs=1e-6)
    assert result.supply["V+"] == pytest.approx(1e-3 - 0.3, rel=0.01)  # the adapter takes it in


@pytest.mark.sim
def test_the_klons_buffered_bypass_lets_a_little_effect_through(sim: Simulator) -> None:
    """D-248 (R27 back, as Aion draws it; D-233 undone): bypassed in Buffered, R27 lets the
    effect into the output under the dry buffer, so the level moves with Gain but stays
    within 1 dB of the input at noon. True bypass is exact. On, both modes sound the same."""
    from solum.circuit.io import load_circuit
    from solum.netlist import Ac

    base = load_circuit(REPO / "library" / "starters" / "klon-centaur-aion-built.json")

    def gain(mode: int, footswitch: int, drive: float) -> float:
        c = base
        for ref in ("SW1A", "SW1B", "SW1C"):
            c = c.with_part(ref, position=mode)
        for ref in ("SW2A", "SW2B", "SW2C", "VR1A", "VR1B"):
            c = c.with_part(
                ref, **({"position": footswitch} if ref[0] == "S" else {"rotation": drive})
            )
        ac = sim.ac(c, Ac(start=1000, stop=1000, per_decade=1))
        return float(20 * np.log10(abs(ac.responses["out"][0] / ac.responses["in"][0])))

    buffered, true_bypass, on, off = 1, 0, 0, 1
    noon, full = gain(buffered, off, 0.5), gain(buffered, off, 1.0)
    assert abs(noon) < 1.0
    assert abs(full - noon) > 0.1  # the leak follows the Gain
    assert gain(true_bypass, off, 1.0) == pytest.approx(0.0, abs=0.01)
    assert gain(buffered, on, 0.5) == pytest.approx(gain(true_bypass, on, 0.5), abs=0.01)
