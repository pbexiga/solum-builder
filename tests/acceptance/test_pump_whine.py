"""Phase 8's acceptance (D-093): a JFET gain stage on V18 from the charge-pump doubler
(TC1044S) whines with its 10 kHz oscillator (a 5 kHz pump) and doesn't with boost on
(45 kHz, a 22.5 kHz pump), heard through the real render path: a clip played through
the circuit, gridded, resampled to the 48 kHz WAV the user listens to.

Thresholds are design choices, not published values: the whine is "audible" when the
pump's tone is within 80 dB of a soft note (measured: about 66 dB below), and "none"
means nothing but the note and its harmonics above -110 dB in 100 Hz-20 kHz."""

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from solum.audio.render import RATE, Inputs, render
from solum.audio.wav import Audio, read_wav, write_wav
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.parts import pin_positions
from solum.circuit.schema import Label
from solum.simulate import Simulator

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).parents[2]
NOTE = 440.0
AUDIBLE_DB = -80.0  # the pump tone against the note: louder than this is a whine
SILENT_DB = -110.0  # nothing else in the band may be louder than this


def spectrum_db(wav: bytes) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Frequencies and levels in dB against the note, over the take's second half."""
    x = read_wav(wav).samples
    x = x[len(x) // 2 :]
    window = np.hanning(len(x))
    level = np.abs(np.fft.rfft(x * window))
    freq = np.fft.rfftfreq(len(x), 1 / RATE)
    note = level[np.argmin(np.abs(freq - NOTE))]
    return freq, 20 * np.log10(level / note + 1e-20)


def take(sim: Simulator, boost: bool, tmp_path: Path) -> tuple[np.ndarray, np.ndarray]:
    circuit = load_circuit(REPO / "tests/fixtures/circuits/pump-whine.json")
    if boost:  # pin 1 on the chip's V+ (D-234)
        supply = connect(circuit).net_of("U2", "in")
        pin1 = pin_positions(circuit.part("U2"))["1"]
        labels = [*circuit.labels, Label(net=supply, pos=pin1)]
        circuit = circuit.model_copy(update={"labels": labels})
    t = np.arange(int(0.5 * 48000)) / 48000
    clip = write_wav(Audio(48000, 0.5 * np.sin(2 * np.pi * NOTE * t)))
    return spectrum_db(
        render(sim, circuit, Inputs(clip=clip, level="soft", pump_ripple=True), tmp_path).wav
    )


def others(freq: np.ndarray) -> np.ndarray:
    """100 Hz-20 kHz, away from the note's harmonics."""
    near_note = np.zeros_like(freq, dtype=bool)
    for k in range(1, int(20000 / NOTE) + 2):
        near_note |= np.abs(freq - k * NOTE) < 25
    return (freq > 100) & (freq < 20000) & ~near_note


def test_a_5_khz_pump_whines(sim: Simulator, tmp_path: Path) -> None:
    freq, db = take(sim, False, tmp_path)
    band = others(freq)
    loudest = freq[band][np.argmax(db[band])]
    assert loudest == pytest.approx(5000, abs=5)  # the pump: 10 kHz oscillator halved
    assert db[band].max() > AUDIBLE_DB


def test_boost_takes_the_whine_out_of_hearing(sim: Simulator, tmp_path: Path) -> None:
    freq, db = take(sim, True, tmp_path)
    assert db[others(freq)].max() < SILENT_DB
