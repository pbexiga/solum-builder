"""An inductor (D-173) through ngspice: an RL low-pass's corner and its wire's DC loss.

L = 100 mH in series, R = 1 kΩ to ground. With an ideal coil the corner is R / (2πL) =
1591.5 Hz at -3.01 dB. With 100 Ω of wire the passband is 1000 / 1100 = -0.828 dB and the
corner moves to (R + Rw) / (2πL) = 1750.7 Hz, where the gain is 3.01 dB under that.
"""

import math
from collections.abc import Callable

import pytest

from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary
from solum.netlist import Ac, Op, generate_netlist
from solum.sim.native import NativeNgspice

L = 0.1
R = 1e3


def gain_db(engine: NativeNgspice, c: CircuitBuilder, f: float) -> float:
    netlist = generate_netlist(
        c.build(), ModelLibrary({}), Ac(start=f, stop=f * 1.0001, per_decade=1)
    )
    out = engine.run(netlist.text).plot("ac").vectors[netlist.node("out")]
    return 20 * math.log10(abs(out[0]))


def rl(circuit: Callable[..., CircuitBuilder], wire: float) -> CircuitBuilder:
    return (
        circuit("rl low-pass")
        .part("IN", "guitar", "in")
        .part("L1", "inductor", "in", "out", value=L, resistance=wire)
        .part("R1", "resistor", "out", "0", value=R)
    )


def test_an_ideal_coils_corner(
    engine: NativeNgspice, circuit: Callable[..., CircuitBuilder]
) -> None:
    corner = R / (2 * math.pi * L)
    assert gain_db(engine, rl(circuit, 0), corner) == pytest.approx(-3.0103, abs=1e-3)


def test_the_wire_lowers_the_passband_and_moves_the_corner(
    engine: NativeNgspice, circuit: Callable[..., CircuitBuilder]
) -> None:
    passband = 20 * math.log10(R / (R + 100))  # -0.828 dB
    assert gain_db(engine, rl(circuit, 100), 1.0) == pytest.approx(passband, abs=1e-3)
    corner = (R + 100) / (2 * math.pi * L)
    assert gain_db(engine, rl(circuit, 100), corner) == pytest.approx(passband - 3.0103, abs=1e-3)


def test_dc_drops_across_the_wire(
    engine: NativeNgspice, circuit: Callable[..., CircuitBuilder]
) -> None:
    """9 V through 100 Ω of wire into 1 kΩ: 9 * 1000 / 1100 = 8.182 V."""
    c = (
        circuit("rl dc")
        .rail("V+", 9.0)
        .part("L1", "inductor", "V+", "out", value=L, resistance=100)
    )
    c.part("R1", "resistor", "out", "0", value=R)
    netlist = generate_netlist(c.build(), ModelLibrary({}), Op())
    v = engine.run(netlist.text).plot("op").vectors[netlist.node("out")]
    assert float(v[0].real) == pytest.approx(9 * 1000 / 1100, abs=1e-4)
