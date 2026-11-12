"""Every core block through real ngspice, in a small jig: a guitar input on its `in`
port, an amp on `out`, a 100k/100k divider on `vref`. Numbers you can check by hand."""

from pathlib import Path

import numpy as np
import pytest

from solum.analysis.measures import gain_at
from solum.circuit.schema import Circuit
from solum.models import ModelLibrary, load_models
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator
from tests.jig import BLOCKS, core_block, jig
from tests.sim.test_chargepump import strongest

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    models: ModelLibrary = load_models([REPO / "library" / "models"])
    return Simulator(engine, models)


def jigged(name: str) -> Circuit:
    return jig(core_block(name))


def gain_1k(sim: Simulator, c: Circuit) -> float:
    ac = sim.ac(c)
    assert ac.valid, [s.message for s in ac.saturated]
    out = c.probes.out
    assert out is not None
    return gain_at(ac.freq, ac.responses[out], 1000.0)


def test_every_block_simulates(sim: Simulator) -> None:
    for path in sorted(BLOCKS.glob("*.json")):
        c = jigged(path.stem)
        sim.op(c)
        if c.probes.out:
            gain_1k(sim, c)


def test_gain_stages(sim: Simulator) -> None:
    # non-inverting, the TS808's values (D-260): 1 + R2 / (R3 + 1/(jwC3)), 51k, 4k7, 47n;
    # the leg's 720 Hz corner is near 1 kHz, so 19.7 dB there, not 1 + 51k/4k7 (21.5 dB)
    leg = 4.7e3 + 1 / (2j * np.pi * 1e3 * 47e-9)
    expected = 20 * np.log10(abs(1 + 51e3 / leg))
    assert gain_1k(sim, jigged("opamp-noninv-stage")) == pytest.approx(expected, abs=0.2)
    assert gain_1k(sim, jigged("opamp-unity-buffer")) == pytest.approx(0.0, abs=0.1)
    follower = jigged("jfet-source-follower")  # the Rat's output buffer (D-260)
    assert -1.5 < gain_1k(sim, follower) < 0.0
    op = sim.op(follower).voltages
    assert op["Q1.G"] == pytest.approx(0.0, abs=0.01)  # R8 holds the gate at ground
    assert 1.0 < op["Q1.S"] < 6.0  # the source at the 2N5458's own Vgs
    assert gain_1k(sim, jigged("bjt-buffer")) == pytest.approx(0.0, abs=0.5)  # DS-1's
    cs = jigged("jfet-cs-stage")  # the Fetzer Valve (D-266)
    op = sim.op(cs)
    assert op.voltages["Q1.D"] == pytest.approx(4.5, abs=0.05)  # the drain, solved by TR1
    assert "TR1" in op.bias
    assert gain_1k(sim, cs.with_part("VR1", rotation=1.0)) > 10.0  # Volume full up
    assert gain_1k(sim, cs.with_part("VR1", rotation=0.0)) < -40.0  # down: the wiper on GND
    assert gain_1k(sim, jigged("big-muff-stage")) > 10.0
    # cut from starters (D-260): the knobs at half, the diodes off in a small-signal run
    assert gain_1k(sim, jigged("ts808-clipper-tone")) > 10.0
    assert gain_1k(sim, jigged("rat-gain-filter")) > 20.0
    booster = jigged("rangemaster-booster")
    assert gain_1k(sim, booster) > 10.0
    assert sim.op(booster).voltages["Q1.C"] == pytest.approx(-7.0, abs=1.0)  # as the starter


def test_passive_blocks(sim: Simulator) -> None:
    assert gain_1k(sim, jigged("diode-clipper-gnd")) == pytest.approx(0.0, abs=0.1)  # 1k into 1M
    tmb = gain_1k(sim, jigged("fender-tmb"))
    muff = gain_1k(sim, jigged("big-muff-tone"))
    assert tmb < -5.0 and muff < -5.0  # passive tone stacks lose level


def gain_hz(sim: Simulator, c: Circuit, hz: float) -> float:
    ac = sim.ac(c)
    assert ac.valid, [s.message for s in ac.saturated]
    out = c.probes.out
    assert out is not None
    return gain_at(ac.freq, ac.responses[out], hz)


@pytest.mark.parametrize(
    ("name", "knob", "hz", "low", "high"),
    [
        # TI SLOA042: "approximately -20 dB of cut, to flat, to approximately 20 dB of boost"
        ("baxandall-bass-treble", "VR1", 20.0, 15.0, 22.0),
        ("baxandall-bass-treble", "VR2", 20e3, 12.0, 22.0),
        # TI TL082-N Figure 28's curves: each band to about +-20 dB; the bass reaches it
        # only near 10 Hz, so it's checked part-way up its slope, at 50 Hz (C5 rolls the
        # very bottom off unevenly)
        ("baxandall-3-band", "VR1", 50.0, 8.0, 16.0),
        ("baxandall-3-band", "VR2", 1e3, 15.0, 22.0),
        ("baxandall-3-band", "VR3", 20e3, 15.0, 25.0),
    ],
)
def test_baxandall_blocks(
    sim: Simulator, name: str, knob: str, hz: float, low: float, high: float
) -> None:
    """Flat with every knob half-way; clockwise boosts and anticlockwise cuts by about
    the same, as TI's curves show (D-265)."""
    c = jigged(name)
    assert gain_hz(sim, c, 1e3) == pytest.approx(0.0, abs=0.5)
    boost = gain_hz(sim, c.with_part(knob, rotation=1.0), hz)
    cut = gain_hz(sim, c.with_part(knob, rotation=0.0), hz)
    assert low < boost < high
    assert cut == pytest.approx(-boost, abs=2.0)


def test_power_blocks(sim: Simulator) -> None:
    assert sim.op(jigged("vref-divider")).voltages["vref"] == pytest.approx(4.5, abs=1e-3)
    assert sim.op(jigged("input-filter-9v")).voltages["V+F"] == pytest.approx(9.0, abs=1e-3)
    # The pumps run from V+ and drive nets of their own (D-091, D-093). Unloaded: 2 x 9 V
    # and -9 V, the doubler's less ~0.05 V for what its drawn D1 (a 1N5817 Schottky,
    # reverse-biased in the averaged model) leaks back to V+ (D-226).
    doubler = jigged("charge-pump-doubler-chip")
    assert sim.op(doubler).voltages["V18"] == pytest.approx(17.95, abs=0.02)
    inverter = jigged("charge-pump-inverter-chip")
    assert sim.op(inverter).voltages["VNEG"] == pytest.approx(-9.0, abs=1e-3)
    # The Klon's: one LT1054 doing both (D-226). VNEG carries the doubler's draw through
    # the chip as well, so it sits ~0.25 V short of -9 V.
    both = sim.op(jigged("charge-pump-both-chip")).voltages
    assert both["V18"] == pytest.approx(17.7, abs=0.05)
    assert both["VNEG"] == pytest.approx(-8.75, abs=0.05)


@pytest.mark.parametrize(
    ("load", "low", "high"),
    [(None, 11.9, 12.0), (2.4e3, 11.8, 12.0), (1.2e3, 8.0, 11.0)],
)
def test_zener_after_a_doubler(sim: Simulator, load: float | None, low: float, high: float) -> None:
    """R1 (1k) passes (17.2 V - 12 V) / 1k = 5.2 mA: a 1N4742A holds V12 near 12 V while
    the load draws less (2.4k at 12 V: 5 mA), and lets it fall once it draws more (1.2k:
    10 mA)."""
    c = jig(core_block("charge-pump-12v-zener"), supply_load=load)
    assert low < sim.op(c).voltages["V12"] < high


@pytest.mark.parametrize(
    ("name", "net", "load", "low", "high", "dc"),
    [
        # V+ + the TL072's swing (about 1.5 V to 7.5 V on 9 V) - two Schottky drops
        ("charge-pump-doubler-opamp", "VDBL", 15e3, 14.3, 14.9, 8.8),
        # -(the swing - two Schottky drops)
        ("charge-pump-inverter-opamp", "VNEG", 9.1e3, -5.9, -5.4, 0.0),
    ],
)
def test_pumps_without_a_chip(
    sim: Simulator, name: str, net: str, load: float, low: float, high: float, dc: float
) -> None:
    """The op-amp oscillator pumps (D-094) at about 1 mA, near 22 kHz (R4 x C1). DC doesn't
    see the oscillation (the doubler shows V+ through its diodes, the inverter 0 V); the
    transient does."""
    c = jig(core_block(name), supply_load=load)
    assert sim.op(c).voltages[net] == pytest.approx(dc, abs=0.1)
    run = sim.tran(c, [net], "soft")
    assert run.settled is None  # its own oscillator: too slow to search (D-122)
    t, v = run.time, run.waves[net]
    late = t > t[-1] / 2
    assert low < float(np.mean(v[late])) < high
    # Ripple and frequency over the last 20 cycles: the mean still creeps a few mV over the
    # second half, which would swamp both. I / (f x C3) = 1 mA / (22 kHz x 10 uF) = 4.5 mV
    tail = t > t[-1] - 20 / 22e3
    assert float(np.ptp(v[tail])) < 0.01
    grid = np.arange(t[tail][0], t[-1], 2e-7)
    assert strongest(grid, np.interp(grid, t, v)) == pytest.approx(22e3, rel=0.05)


@pytest.mark.parametrize("load", [None, 2.4e3, 1.2e3])
def test_regulator_after_a_doubler(sim: Simulator, load: float | None) -> None:
    """A 78L12 holds V12 at 12 V (less 0.2 ohm x the load) from the doubler's ~17 V, with
    or without a 10 mA load (D-227), where the zener block above lets it fall."""
    v = sim.op(jig(core_block("regulator-12v"), supply_load=load)).voltages
    assert v["V12"] == pytest.approx(11.98, abs=0.01)
    assert v["V18"] > 13.7 + 2.0  # well clear of its dropout
