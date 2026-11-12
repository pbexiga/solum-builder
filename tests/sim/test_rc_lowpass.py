"""First sim test: an RC low-pass has its -3 dB corner at 1/(2*pi*R*C).

Runs through the whole pipeline: circuit file → nets → netlist → ngspice.
"""

import math
from collections.abc import Callable

import numpy as np
import pytest

from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary
from solum.netlist import Ac, generate_netlist
from solum.sim.native import NativeNgspice

R = 10e3
C = 15.9e-9
CORNER = 1 / (2 * math.pi * R * C)  # 1000.97 Hz


def response(engine: NativeNgspice, circuit: Callable[..., CircuitBuilder], ac: Ac) -> tuple[
        np.ndarray, np.ndarray]:  # fmt: skip
    c = (
        circuit("rc low-pass")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value=R)
        .part("C1", "capacitor", "out", "0", value=C)
        .build()
    )
    netlist = generate_netlist(c, ModelLibrary({}), ac)
    plot = engine.run(netlist.text).plot("ac")
    return plot.vectors["frequency"].real, plot.vectors[netlist.node("out")]


def test_gain_and_phase_at_the_corner(
    engine: NativeNgspice, circuit: Callable[..., CircuitBuilder]
) -> None:
    _, out = response(engine, circuit, Ac(start=CORNER, stop=CORNER * 1.0001, per_decade=1))
    assert 20 * math.log10(abs(out[0])) == pytest.approx(-3.0103, abs=1e-3)
    assert math.degrees(np.angle(out[0])) == pytest.approx(-45.0, abs=0.01)


def test_passband_and_rolloff(
    engine: NativeNgspice, circuit: Callable[..., CircuitBuilder]
) -> None:
    freq, out = response(engine, circuit, Ac(start=10, stop=100e3, per_decade=50))
    gain_db = 20 * np.log10(np.abs(out))
    assert gain_db[0] == pytest.approx(0.0, abs=1e-3)  # 10 Hz: passband
    assert gain_db[-1] == pytest.approx(20 * math.log10(CORNER / freq[-1]), abs=0.01)  # -20 dB/dec
