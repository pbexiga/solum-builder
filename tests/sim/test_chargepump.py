"""The charge pump (D-093) through the real pipeline: its DC level, its ripple at the pump
frequency, the current it draws from V+, and the live solver measuring it."""

from pathlib import Path

import numpy as np
import pytest

from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary, load_models
from solum.probe import op_data
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]
RIPPLE = 0.094  # V peak to peak: 9.4 mA from a 10 µF reservoir at 5 kHz (see below)


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


@pytest.fixture
def sim(engine: NativeNgspice, models: ModelLibrary) -> Simulator:
    return Simulator(engine, models)


def strongest(t: np.ndarray, x: np.ndarray) -> float:
    """The strongest frequency above 1 kHz in `x` (sampled evenly at times `t`), less any
    straight-line drift (a reservoir still settling would leak into the lowest bins)."""
    level = np.polyval(np.polyfit(t - t[0], x, 1), t - t[0])
    spectrum = np.abs(np.fft.rfft((x - level) * np.hanning(len(x))))
    freq = np.fft.rfftfreq(len(x), t[1] - t[0])
    above = freq > 1000
    return float(freq[above][np.argmax(spectrum[above])])


def pumped(mode: str = "doubler", load: str = "18k", boost: bool = False,
           model: str = "TC1044S") -> CircuitBuilder:  # fmt: skip
    """9 V → the pump, its parts drawn with its sheet's cap (D-226) → `o` with a 10 µF
    reservoir and a resistor load; a guitar into a divider on `o` so the transient and AC
    runs have an input."""
    return (
        CircuitBuilder("pump").rail("V+", 9.0)
        .part("C1", "capacitor", "o", "0", value="10u")
        .part("R2", "resistor", "o", "0", value=load)
        .part("IN", "guitar", "g")
        .part("R1", "resistor", "g", "o", value="1M")
        .pump("U1", "V+", **{"double" if mode == "doubler" else "invert": "o"}, model=model,
              boost=boost, cap="100u" if model == "LT1054" else "10u")  # the sheet's cap
    )  # fmt: skip


def test_doubler_dc_is_twice_the_supply_less_two_diodes_and_its_resistance(
    sim: Simulator,
) -> None:
    op = sim.op(pumped().build())
    v = op.voltages["o"]
    i = v / 18e3
    # 2 x 9 V, less two 1N5817 drops at ~1 mA (about 0.2 V each) and 60 Ω x 1 mA
    assert 17.4 < v < 17.7
    # V+ delivers the load current twice over (the doubler's ratio) plus 80 µA quiescent,
    # plus what the drawn D1, reverse-biased in the averaged model, leaks back (D-226)
    leak = -op.currents["D1.id"]
    assert 0 < leak < 1e-4
    assert op.supply["V+"] == pytest.approx(2 * i + 80e-6 + 9 / 1e6 + leak, rel=0.02)


def test_inverter_dc_and_supply_current(sim: Simulator) -> None:
    op = sim.op(pumped("inverter", load="9k").build())
    v = op.voltages["o"]
    assert v == pytest.approx(-(9 - 60 * abs(v) / 9e3), abs=0.01)  # -9 V behind 60 Ω
    assert op.supply["V+"] == pytest.approx(abs(v) / 9e3 + 80e-6, rel=0.02)


def test_ripple_is_at_the_pump_frequency_and_its_average_is_the_dc_level(
    sim: Simulator, models: ModelLibrary
) -> None:
    c = pumped(load="1k8").build()  # ~10 mA, so the ripple is well above numerical noise
    dc = sim.op(c).voltages["o"]
    run = sim.tran(c, ["o"], "soft")
    t, v = run.time, run.waves["o"]
    late = t > t[-1] / 2
    # The diodes carry the charge in pulses at twice the average current, so each drops
    # about N·Vt·ln 2 more than at DC (N from the 1N5817's card; Vt at 27 °C).
    n = models.get("1N5817").param("n")
    assert n is not None
    assert float(np.mean(v[late])) == pytest.approx(dc - 2 * n * 0.025865 * np.log(2), abs=0.02)
    # The ICL7660/TC1044S ripple formula (ICL7660 data sheet page 9, no ESR):
    # I / (2 f C) = 9.4 mA / (2 x 5 kHz x 10 µF) = 94 mV peak to peak
    assert float(np.ptp(v[late])) == pytest.approx(RIPPLE, rel=0.15)
    grid = np.arange(t[late][0], t[-1], 1e-6)
    x = np.interp(grid, t, v)
    assert strongest(grid, x) == pytest.approx(5000, rel=0.02)


def test_boost_moves_the_pump_above_the_audio_band(sim: Simulator) -> None:
    run = sim.tran(pumped(load="1k8", boost=True).build(), ["o"], "soft")
    t, v = run.time, run.waves["o"]
    late = t > t[-1] / 2
    grid = np.arange(t[late][0], t[-1], 2e-7)
    assert strongest(grid, np.interp(grid, t, v)) == pytest.approx(22500, rel=0.02)
    # the same formula at 4.5 x the pump frequency
    assert float(np.ptp(v[late])) == pytest.approx(RIPPLE / 4.5, rel=0.15)


def test_pin_1_on_v_plus_of_a_chip_without_boost_changes_nothing(sim: Simulator) -> None:
    """D-234: an ICL7660's pin 1 is a no-connect, so wiring it to V+ (as a TC1044S's boost
    is wired) pumps the same, with no error."""
    plain = sim.op(pumped(model="ICL7660").build()).voltages["o"]
    tied = sim.op(pumped(boost=True, model="ICL7660").build()).voltages["o"]
    assert tied == pytest.approx(plain, abs=1e-6)


def test_the_live_solver_measures_the_pump_as_a_device(sim: Simulator) -> None:
    lin = sim.linearise(pumped().build())
    assert "U1" in lin.ports
    assert lin.ports["U1"].nodes  # its output, at least (V+ and ground are held)


def test_the_run_reports_each_supplys_current_as_text(sim: Simulator) -> None:
    supply = op_data(sim.op(pumped("inverter", load="9k").build()))["supply"]
    assert supply["V+"]["text"].endswith(" mA")
    assert supply["V+"]["amps"] == pytest.approx(9 / 9e3 + 80e-6, rel=0.02)


def test_one_chip_wired_as_both_doubles_and_inverts_at_once(sim: Simulator) -> None:
    """D-218, the Klon's wiring: 2 x in through the diodes and -in on VOUT, each as it
    would be alone, and V+ delivers both loads' currents (the doubler's twice) plus one
    quiescent. CAP+ and CAP- read half V+ and half VOUT, as a meter does (D-226)."""
    c = (
        CircuitBuilder("both").rail("V+", 9.0)
        .part("C1", "capacitor", "o", "0", value="10u")
        .part("R2", "resistor", "o", "0", value="18k")
        .part("C2", "capacitor", "n", "0", value="10u")
        .part("R3", "resistor", "n", "0", value="9k")
        .pump("U1", "V+", double="o", invert="n")
    ).build()  # fmt: skip
    op = sim.op(c)
    vo, vn = op.voltages["o"], op.voltages["n"]
    assert 17.4 < vo < 17.7  # as the doubler alone
    assert vn == pytest.approx(-(9 - 60 * abs(vn) / 9e3), abs=0.01)  # as the inverter alone
    supply = 2 * vo / 18e3 + abs(vn) / 9e3 + 80e-6 - op.currents["D1.id"]  # D1's leak, above
    assert op.supply["V+"] == pytest.approx(supply, rel=0.02)
    assert op.voltages["U1_cp"] == pytest.approx(4.5, abs=0.01)
    assert op.voltages["U1_cm"] == pytest.approx(vn / 2, abs=0.01)


def test_a_smaller_pump_cap_drops_more(sim: Simulator) -> None:
    """D-226: the drawn cap sets the output resistance. 1 uF at 5 kHz: 240 ohms, not 60,
    so at ~1 mA the doubler reads about 0.18 V lower."""
    big = sim.op(pumped().build()).voltages["o"]
    small = (
        CircuitBuilder("pump").rail("V+", 9.0)
        .part("C1", "capacitor", "o", "0", value="10u")
        .part("R2", "resistor", "o", "0", value="18k")
        .pump("U1", "V+", double="o", cap="1u")
    ).build()  # fmt: skip
    assert big - sim.op(small).voltages["o"] == pytest.approx(180 * big / 18e3, rel=0.1)
