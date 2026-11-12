"""The render pipeline's pieces that need no ngspice: levels, clips, the dry path."""

import json
from pathlib import Path

import numpy as np
import pytest

from solum.audio.nam import Layer, LayerArray, NamModel, activation
from solum.audio.render import (
    DEFAULT_INPUT_DBU,
    MAX_CLIP_SECONDS,
    RATE,
    SIM_RATE,
    Inputs,
    RenderError,
    clip_gain,
    compression_db,
    full_scale_volts,
    read_clip,
    render,
    render_key,
    source_path,
    source_text,
    take_spectra,
    timeout_message,
    write_source,
)
from solum.audio.wav import Audio, WavError, read_wav, write_wav
from solum.circuit.build import CircuitBuilder
from solum.models import ModelLibrary
from solum.sim.engine import SimTimeout
from solum.simulate import Simulator, recording_limit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nam"


class NoEngine:
    """Dry renders never simulate."""

    name = "none"

    def version(self) -> str:
        return "0"

    def run(self, netlist: str, timeout: float | None = None, progress: object = None) -> None:
        raise AssertionError("a dry render ran the simulator")


SIM = Simulator(NoEngine(), ModelLibrary({}))  # type: ignore[arg-type]


def tone_wav(
    freq: float = 1000, rate: int = 48000, seconds: float = 0.2, amp: float = 0.5
) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    return write_wav(Audio(rate, amp * np.sin(2 * np.pi * freq * t)))


def test_full_scale_of_a_dbu_level() -> None:
    assert full_scale_volts(0) == pytest.approx(0.7746 * np.sqrt(2))  # 1.095 V peak
    assert full_scale_volts(DEFAULT_INPUT_DBU) == pytest.approx(4.361, abs=1e-3)


def test_a_clips_peak_becomes_the_pick_level() -> None:
    clip = read_clip(tone_wav(amp=0.5))
    assert clip_gain(clip, "med") == pytest.approx(0.3 / 0.5, rel=1e-3)
    assert clip_gain(clip, "hard") == pytest.approx(1.0 / 0.5, rel=1e-3)
    with pytest.raises(ValueError, match="Level must be"):
        clip_gain(clip, "loud")


def test_long_or_silent_clips_are_refused() -> None:
    long = write_wav(Audio(1000, np.ones(int(1000 * MAX_CLIP_SECONDS) + 1)))
    with pytest.raises(WavError, match="up to 10 s"):
        read_clip(long)
    with pytest.raises(WavError, match="silent"):
        read_clip(write_wav(Audio(48000, np.zeros(10))))


def test_source_file_is_named_by_content_and_written_once(tmp_path: Path) -> None:
    data = tone_wav(rate=48000, seconds=0.01)
    path = source_path(tmp_path, data)
    assert path == source_path(tmp_path, data) != source_path(tmp_path, tone_wav(seconds=0.02))
    n = write_source(path, read_clip(data))
    assert n == 0.01 * SIM_RATE
    rows = np.loadtxt(path)
    assert rows.shape == (n, 2)
    assert rows[1, 0] == pytest.approx(1 / SIM_RATE)
    stamp = path.stat().st_mtime_ns
    write_source(path, read_clip(data))
    assert path.stat().st_mtime_ns == stamp


def test_dry_render_is_the_guitar_at_the_default_level(tmp_path: Path) -> None:
    seen: list[float] = []
    out = render(SIM, None, Inputs(tone_wav(rate=44100)), tmp_path, seen.append)
    audio = read_wav(out.wav)
    assert audio.rate == RATE
    assert out.seconds == pytest.approx(0.2)
    assert out.peak == pytest.approx(0.3 / full_scale_volts(DEFAULT_INPUT_DBU), rel=2e-3)
    assert out.amp_in == pytest.approx(out.peak, rel=2e-3)  # no capture: what goes in comes out
    assert seen[-1] == 1.0


def test_a_96_khz_pedal_line_reaches_30_khz_and_the_heard_line_stops_at_24() -> None:
    # D-105: the pedal take's own line is read from the 96 kHz simulation; what's heard is
    # 48 kHz, so its bands above the 23 kHz one are silent, not missing
    t = np.arange(SIM_RATE // 2) / SIM_RATE
    volts = 0.5 * np.sin(2 * np.pi * 1000 * t) + 0.1 * np.sin(2 * np.pi * 27000 * t)
    heard = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(RATE // 2) / RATE)
    spectra = take_spectra(SIM, None, volts, heard, SIM_RATE)
    freq = np.array(spectra["freq"])
    assert freq[-1] == pytest.approx(10 * 2 ** (69 / 6))  # the last band, 29 kHz
    assert len(spectra["pedal"]) == len(spectra["heard"]) == len(spectra["di"]) == len(freq)
    near = int(np.argmin(abs(np.log2(freq / 27000))))
    assert spectra["pedal"][near] == pytest.approx(20 * np.log10(0.1 / np.sqrt(2)), abs=1.0)
    k1 = int(np.argmin(abs(np.log2(freq / 1000))))
    # the same 1 kHz level at either rate (same resolution: the segment follows the rate)
    assert spectra["pedal"][k1] == pytest.approx(spectra["heard"][k1], abs=0.1)
    assert all(v == -200.0 for v in np.array(spectra["heard"])[freq > 24000])
    assert spectra["pedal_top"] == 48000


@pytest.mark.parametrize(
    ("rate", "bands", "top"), [(96000, 70, 48000), (48000, 68, 24000), (44100, 68, 22050)]
)
def test_a_dry_take_is_read_at_the_clips_own_rate(
    tmp_path: Path, rate: int, bands: int, top: float
) -> None:
    # D-105: a 96 kHz clip's Dry line reaches 30 kHz; what's heard is 48 kHz either way
    out = render(SIM, None, Inputs(tone_wav(27000 if rate == 96000 else 1000, rate)), tmp_path)
    s = out.spectra
    assert s["pedal_top"] == top
    assert len(s["freq"]) == len(s["pedal"]) == len(s["heard"]) == bands  # type: ignore[arg-type]
    if rate == 96000:  # the 27 kHz tone is there before the amp, gone after it
        freq = np.array(s["freq"])
        near = int(np.argmin(abs(np.log2(freq / 27000))))
        assert s["pedal"][near] > -40  # type: ignore[index]
        assert s["heard"][near] == -200.0  # type: ignore[index]


def test_dry_render_through_a_capture_and_an_ir(tmp_path: Path) -> None:
    nam = (FIXTURES / "standard-random.nam").read_bytes()
    ir = np.zeros(480)
    ir[0] = 1.0
    plain = render(SIM, None, Inputs(tone_wav(), nam), tmp_path)
    with_ir = render(SIM, None, Inputs(tone_wav(), nam, write_wav(Audio(48000, ir))), tmp_path)
    assert read_wav(with_ir.wav).samples == pytest.approx(read_wav(plain.wav).samples, abs=1e-6)
    assert plain.peak > 0


def test_a_capture_with_an_input_level_is_driven_at_it(tmp_path: Path) -> None:
    doc = json.loads((FIXTURES / "standard-random.nam").read_text())
    louder = json.dumps({**doc, "metadata": {"input_level_dbu": DEFAULT_INPUT_DBU - 20}})
    quiet = render(SIM, None, Inputs(tone_wav(amp=0.01), (FIXTURES / "standard-random.nam")
                                     .read_bytes()), tmp_path)  # fmt: skip
    hot = render(SIM, None, Inputs(tone_wav(amp=0.01), louder.encode()), tmp_path)
    assert hot.peak > 3 * quiet.peak  # 20 dB more into the same (mostly linear) model


def test_dry_keys_follow_every_input(tmp_path: Path) -> None:
    nam = (FIXTURES / "standard-random.nam").read_bytes()
    base = Inputs(tone_wav(), nam)
    key = render_key(SIM, None, base, tmp_path)
    assert key == render_key(SIM, None, Inputs(tone_wav(), nam), tmp_path)
    others = [
        Inputs(tone_wav(), nam, level="hard"),
        Inputs(tone_wav(freq=500), nam),
        Inputs(tone_wav()),
        Inputs(tone_wav(), nam, write_wav(Audio(48000, np.ones(4)))),
        Inputs(tone_wav(), nam, input_db=-6),
    ]
    assert len({key, *(render_key(SIM, None, i, tmp_path) for i in others)}) == 6
    # Without a capture there's no amp Input to turn: the same render.
    assert render_key(SIM, None, Inputs(tone_wav(), input_db=-6), tmp_path) == render_key(
        SIM, None, Inputs(tone_wav()), tmp_path
    )


def test_input_trim_drives_the_capture(tmp_path: Path) -> None:
    """The amp's Input sits between the pedal and the capture; loudness after the amp is
    the player's volume, not part of the render (D-096)."""
    nam = (FIXTURES / "standard-random.nam").read_bytes()
    base = render(SIM, None, Inputs(tone_wav(), nam), tmp_path)
    hot = render(SIM, None, Inputs(tone_wav(), nam, input_db=20), tmp_path)
    full_scale = full_scale_volts(DEFAULT_INPUT_DBU)
    assert base.amp_in == pytest.approx(0.3 / full_scale, rel=2e-3)  # the pick level, in dBFS
    assert hot.amp_in == pytest.approx(10 * base.amp_in, rel=1e-6)
    assert hot.peak != pytest.approx(10 * base.peak, rel=0.01)  # through the model, not a gain


@pytest.mark.parametrize("db", [21, -41])
def test_input_out_of_range_is_refused(tmp_path: Path, db: float) -> None:
    inputs = Inputs(tone_wav(), (FIXTURES / "standard-random.nam").read_bytes(), input_db=db)
    with pytest.raises(RenderError, match="must be between -40 and \\+20 dB"):
        render_key(SIM, None, inputs, tmp_path)


def clipper() -> NamModel:
    """A capture that is a hard clipper at ±1 and nothing else (gain 1 below it)."""
    one = np.ones((1, 1, 1), np.float32)
    zero = np.zeros(1, np.float32)
    layer = Layer(1, activation("Hardtanh"), one, zero, np.zeros((1, 1), np.float32),
                  np.zeros((1, 1), np.float32), zero)  # fmt: skip
    array = LayerArray(np.ones((1, 1), np.float32), (layer,), one, None)
    return NamModel((array,), 1.0, 1, 48000, None, "clipper")


@pytest.mark.parametrize(("peak", "squashed"), [(0.5, False), (4.0, True)])
def test_compression_is_how_much_the_amp_squashes(peak: float, squashed: bool) -> None:
    t = np.arange(4800) / 48000
    x = peak * np.sin(2 * np.pi * 1000 * t)
    y = np.clip(x, -1, 1)
    expected = 20 * np.log10(np.sqrt(np.mean(x**2)) / np.sqrt(np.mean(y**2)))  # gain 1 if clean
    assert (expected > 6) == squashed  # a sine 12 dB over the clip level loses ~7.4 dB
    assert compression_db(clipper(), x, y) == pytest.approx(expected, abs=0.01)


def test_a_render_through_a_capture_reports_its_compression(tmp_path: Path) -> None:
    nam = (FIXTURES / "standard-random.nam").read_bytes()
    out = render(SIM, None, Inputs(tone_wav(), nam), tmp_path)
    assert out.amp_compression == pytest.approx(0, abs=0.5)  # this random model is near linear
    assert render(SIM, None, Inputs(tone_wav()), tmp_path).amp_compression == 0  # no capture


def plain_circuit(pump: bool = False) -> CircuitBuilder:
    c = (
        CircuitBuilder("timeout")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="1k")
        .part("OUT", "amp", "out")
    )
    return c.part("U3", "chargepump", "V+", "V18", "0", model="TC1044S") if pump else c


def test_a_render_limit_follows_the_clip() -> None:
    assert recording_limit(2) == pytest.approx(90)
    assert recording_limit(10) == pytest.approx(330)


def test_a_timed_out_render_names_the_charge_pump() -> None:
    """The user (D-095): say it timed out and why, a charge pump first of all. Measured:
    a 2 s take through the Big Muff with a pump needed 144 s against its 90 s limit."""
    said = timeout_message(plain_circuit(pump=True).build(), 2, 90, 0.625)
    assert said.startswith(
        "The render was stopped: a 2 s clip may run for up to 90 s, and it had got through"
        " 62 % of it. At that pace the whole clip needs about 2 min 20 s, 72 times longer"
    )
    assert "The likely cause is the charge pump (U3)" in said
    assert "Render a shorter clip, or leave the pump out while you tune" in said


def test_a_timed_out_render_without_a_pump_points_at_oscillators() -> None:
    said = timeout_message(plain_circuit().build(), 10, 330, 0.0)
    assert said.startswith("The render was stopped: a 10 s clip may run for up to 5 min 30 s.")
    assert "an op-amp charge pump block" in said
    assert "charge pump (" not in said


class SlowEngine:
    """Gets a quarter of the way, then runs out of time."""

    name = "slow"

    def version(self) -> str:
        return "0"

    def run(self, netlist: str, timeout: float | None = None, progress: object = None) -> None:
        assert callable(progress)
        progress(0.25)
        raise SimTimeout("stopped", timeout or 0.0)


def test_a_render_that_times_out_says_why(tmp_path: Path) -> None:
    sim = Simulator(SlowEngine(), ModelLibrary({}))  # type: ignore[arg-type]
    seconds = 0.2
    with pytest.raises(RenderError, match=r"got through 25 % of it") as err:
        render(sim, plain_circuit().build(), Inputs(tone_wav(seconds=seconds)), tmp_path)
    assert f"may run for up to {round(recording_limit(seconds))} s" in str(err.value)


def test_a_source_file_reads_as_numpy_would_write_it() -> None:
    """`source_text` is `np.savetxt`'s output, formatted a block of rows at a time: the
    same bytes, over a block's edge and in a last, short block."""
    import io

    import solum.audio.render as module

    rng = np.random.default_rng(3)
    n = 2 * module.SOURCE_ROWS + 7
    t, x = np.arange(n) / SIM_RATE, rng.normal(size=n) * 0.3
    want = io.BytesIO()
    np.savetxt(want, np.column_stack([t, x]), fmt=("%.10g", "%.8g"))
    assert source_text(t, x).encode() == want.getvalue()
    assert source_text(t[:2], np.array([0.25, -1e-9])) == "0 0.25\n1.041666667e-05 -1e-09\n"
    assert source_text(t[:0], x[:0]) == ""
