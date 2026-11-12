"""Audio renders through real ngspice: levels and filtering survive the whole pipeline
(clip → 96 kHz file → transient → 48 kHz), keys, progress."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from solum.audio.render import DEFAULT_INPUT_DBU, Inputs, full_scale_volts, render, render_key
from solum.audio.wav import Audio, read_wav, write_wav
from solum.cache import SimCache
from solum.circuit.build import CircuitBuilder
from solum.circuit.schema import Circuit
from solum.models import ModelLibrary
from solum.netlist import NetlistError
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

Builder = Callable[..., CircuitBuilder]


@pytest.fixture
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, ModelLibrary({}))


def tone(freq: float, seconds: float = 0.1, rate: int = 44100) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    return write_wav(Audio(rate, 0.8 * np.sin(2 * np.pi * freq * t)))


def level_db(wav: bytes) -> float:
    """Steady-state peak in dB re the dry tone's peak at the default level."""
    y = read_wav(wav).samples
    tail = y[len(y) // 2 :]
    peak = np.sqrt(2 * np.mean(tail**2))
    return float(20 * np.log10(peak / (0.3 / full_scale_volts(DEFAULT_INPUT_DBU))))


def lowpass(circuit: Builder, c: float = 15.9e-9) -> Circuit:
    """10k / 15.9n: corner 1001 Hz, into a 10M amp (a light load)."""
    return (
        circuit("rc")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value=10e3)
        .part("C1", "capacitor", "out", "0", value=c)
        .part("OUT", "amp", "out", value="10M")
        .build()
    )


def test_the_corner_of_a_lowpass_is_3_db_down(
    sim: Simulator, circuit: Builder, tmp_path: Path
) -> None:
    passband = render(sim, lowpass(circuit), Inputs(tone(50)), tmp_path)
    corner = render(sim, lowpass(circuit), Inputs(tone(1001)), tmp_path)
    assert level_db(passband.wav) == pytest.approx(0.0, abs=0.05)
    assert level_db(corner.wav) == pytest.approx(-3.01, abs=0.1)


def test_keys_follow_the_circuit_and_progress_reaches_the_end(
    sim: Simulator, circuit: Builder, tmp_path: Path
) -> None:
    inputs = Inputs(tone(200))
    key = render_key(sim, lowpass(circuit), inputs, tmp_path)
    assert key == render_key(sim, lowpass(circuit), inputs, tmp_path)
    assert key != render_key(sim, lowpass(circuit, 10e-9), inputs, tmp_path)
    assert key != render_key(sim, None, inputs, tmp_path)
    seen: list[float] = []
    render(sim, lowpass(circuit), inputs, tmp_path, seen.append)
    assert seen == sorted(seen) and seen[-1] == 1.0


def test_no_amp_output_is_a_plain_error(sim: Simulator, circuit: Builder, tmp_path: Path) -> None:
    c = (
        circuit("no amp")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "0", value="1k")
        .build()
    )
    with pytest.raises(NetlistError, match="amp output"):
        render(sim, c, Inputs(tone(200)), tmp_path)


STRAT = {"r": "6k38", "l": "2.55", "c": "151p", "kind": "strat"}


def guitar_into(circuit: Builder, amp: str, pickup: bool) -> Circuit:
    """A guitar straight into an amp input of `amp` ohms: a Strat on 3 m of cable through
    its 250k volume pot, or (no pickup) a buffered guitar."""
    fields = {"source": "pickup", "pickup": STRAT, "cable": 3, "volume": "250k"} if pickup else {}
    return (
        circuit("guitar").part("IN", "guitar", "in", **fields).part("OUT", "amp", "in", value=amp)
    ).build()


@pytest.mark.parametrize("freq", [200, 2000, 5000])
def test_into_a_high_impedance_input_a_pickup_leaves_the_clip_as_recorded(
    sim: Simulator, circuit: Builder, tmp_path: Path, freq: int
) -> None:
    """D-096: the clip is a DI, so its pickup's colour is taken out before the guitar's
    pickup puts it back. Into a 1M input that's the DI's own load, so the take is the clip
    as recorded, even at 5 kHz where a Strat on 3 m of cable peaks (the user's choice:
    the pickup changes only how the circuit reacts)."""
    with_pickup = render(sim, guitar_into(circuit, "1M", True), Inputs(tone(freq)), tmp_path)
    buffered = render(sim, guitar_into(circuit, "1M", False), Inputs(tone(freq)), tmp_path)
    assert level_db(with_pickup.wav) == pytest.approx(level_db(buffered.wav), abs=0.1)


def test_into_a_low_impedance_input_a_pickup_sags(
    sim: Simulator, circuit: Builder, tmp_path: Path
) -> None:
    """Into 10k (a Fuzz Face's input is a few kΩ) the pickup sags against what the DI
    heard. At 200 Hz the coil is 6.38k + j·2π·200·2.55 = 6.38k + j3.2k; the 250k pot sits
    across each load: 10k‖250k = 9.62k here, 1M‖250k = 200k for the DI. So the take is
    |9.62k / (9.62k + 6.38k + j3.2k)| / |200k / (200k + 6.38k + j3.2k)| = -4.3 dB from
    the buffered guitar's (cable and coil C don't matter at 200 Hz)."""
    coil = 6380 + 2j * np.pi * 200 * 2.55
    fuzz, di = 1 / (1 / 10e3 + 1 / 250e3), 1 / (1 / 1e6 + 1 / 250e3)
    expected = 20 * np.log10(abs(fuzz / (fuzz + coil)) / abs(di / (di + coil)))
    assert expected == pytest.approx(-4.3, abs=0.05)
    loaded = render(sim, guitar_into(circuit, "10k", True), Inputs(tone(200)), tmp_path)
    buffered = render(sim, guitar_into(circuit, "10k", False), Inputs(tone(200)), tmp_path)
    assert level_db(loaded.wav) - level_db(buffered.wav) == pytest.approx(expected, abs=0.1)


class Counting:
    """The real engine, counting its runs."""

    def __init__(self, engine: NativeNgspice) -> None:
        self.engine, self.runs, self.name = engine, 0, engine.name

    def version(self) -> str:
        return self.engine.version()

    def run(self, netlist: str, timeout: float | None = None, progress: object = None) -> object:
        self.runs += 1
        return self.engine.run(netlist, timeout, progress)  # type: ignore[arg-type]


def test_a_change_after_the_pedal_doesnt_simulate_again(
    engine: NativeNgspice, circuit: Builder, tmp_path: Path
) -> None:
    """D-096: the pedal's output is kept, so another Input trim or capture only re-runs
    the amp (a charge-pump circuit would otherwise take minutes again)."""
    counting = Counting(engine)
    sim = Simulator(counting, ModelLibrary({}))  # type: ignore[arg-type]
    cache = SimCache(tmp_path, 10**8)
    nam = (Path(__file__).parents[1] / "fixtures" / "nam" / "standard-random.nam").read_bytes()
    render(sim, lowpass(circuit), Inputs(tone(200), nam), tmp_path, cache=cache)
    first = counting.runs
    assert first >= 1
    render(sim, lowpass(circuit), Inputs(tone(200), nam, input_db=-6), tmp_path, cache=cache)
    assert counting.runs == first
    render(sim, lowpass(circuit, 10e-9), Inputs(tone(200), nam), tmp_path, cache=cache)
    assert counting.runs > first  # a circuit change simulates
