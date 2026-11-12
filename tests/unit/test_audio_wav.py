import io
import struct
import wave

import numpy as np
import pytest

from solum.audio.ir import convolve, load_ir
from solum.audio.resample import resample
from solum.audio.wav import Audio, WavError, read_wav, write_wav


def pcm_wav(frames: np.ndarray, rate: int, width: int) -> bytes:
    """A PCM WAV made by the standard library (frames: n x channels ints)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(frames.shape[1])
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 3:
            raw = frames.astype("<i4").tobytes()
            raw = b"".join(raw[i : i + 3] for i in range(0, len(raw), 4))
        else:
            raw = frames.astype(f"<i{width}").tobytes()
        w.writeframes(raw)
    return buf.getvalue()


def test_16_bit_stereo_is_mixed_to_mono() -> None:
    frames = np.array([[16384, 0], [-32768, -32768], [0, 16384]])
    audio = read_wav(pcm_wav(frames, 44100, 2))
    assert audio.rate == 44100
    assert audio.samples == pytest.approx([0.25, -1.0, 0.25])


def test_24_bit_mono() -> None:
    frames = np.array([[2**22], [-(2**23)], [0]])
    audio = read_wav(pcm_wav(frames, 48000, 3))
    assert audio.samples == pytest.approx([0.5, -1.0, 0.0])


def test_float_round_trip() -> None:
    x = np.array([0.0, 0.5, -1.25, 1e-3])  # above full scale survives
    audio = read_wav(write_wav(Audio(96000, x)))
    assert audio.rate == 96000
    assert audio.samples == pytest.approx(x, abs=1e-7)
    assert audio.seconds == pytest.approx(4 / 96000)


def test_extensible_header_is_read() -> None:
    data = bytearray(write_wav(Audio(48000, np.array([0.5]))))
    fmt = struct.pack("<HHIIHH", 0xFFFE, 1, 48000, 192000, 4, 32)
    ext = struct.pack("<HHI", 22, 32, 4) + struct.pack("<H", 3) + bytes(14)
    chunk = b"fmt " + struct.pack("<I", len(fmt + ext)) + fmt + ext
    body = b"WAVE" + chunk + bytes(data[36:])  # data chunk of the plain file
    audio = read_wav(b"RIFF" + struct.pack("<I", len(body)) + body)
    assert audio.samples == pytest.approx([0.5])


@pytest.mark.parametrize("data", [b"", b"ID3 not a wav", b"RIFF\x04\x00\x00\x00WAVE"])
def test_not_a_wav_is_a_plain_error(data: bytes) -> None:
    with pytest.raises(WavError):
        read_wav(data)


def test_unsupported_encoding_says_what_to_do() -> None:
    data = bytearray(write_wav(Audio(48000, np.zeros(2))))
    data[20:22] = struct.pack("<H", 2)  # ADPCM
    with pytest.raises(WavError, match="Export it as"):
        read_wav(bytes(data))


def tone(freq: float, rate: int, seconds: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return np.sin(2 * np.pi * freq * t)


def level(x: np.ndarray) -> float:
    """RMS in dB re a full-scale sine, away from the ends."""
    mid = x[len(x) // 4 : -len(x) // 4]
    return float(20 * np.log10(np.sqrt(2 * np.mean(mid**2))))


@pytest.mark.parametrize(("rate_in", "rate_out"), [(44100, 96000), (48000, 96000), (96000, 48000)])
def test_resampled_tone_keeps_its_level_and_pitch(rate_in: int, rate_out: int) -> None:
    y = resample(tone(1000, rate_in), rate_in, rate_out)
    assert len(y) == round(0.5 * rate_in) * rate_out // rate_in
    assert level(y) == pytest.approx(0.0, abs=0.01)
    spectrum = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    assert np.argmax(spectrum) * rate_out / len(y) == pytest.approx(1000, abs=3)


def test_downsampling_removes_what_would_alias() -> None:
    y = resample(tone(30000, 96000), 96000, 48000)  # would fold to 18 kHz
    assert level(y) < -80


def test_same_rate_and_empty() -> None:
    x = tone(100, 48000, 0.01)
    assert resample(x, 48000, 48000) == pytest.approx(x)
    assert len(resample(np.zeros(0), 44100, 96000)) == 0
    with pytest.raises(ValueError):
        resample(x, 0, 48000)


def test_ir_is_unit_energy_at_the_render_rate() -> None:
    h = np.zeros(4410)
    h[0], h[10] = 1.0, 0.5
    out = load_ir(write_wav(Audio(44100, h)), 48000)
    assert len(out) == 4800
    assert float(np.sum(out**2)) == pytest.approx(1.0)


def test_long_or_silent_ir_is_refused() -> None:
    with pytest.raises(WavError, match="cab IR"):
        load_ir(write_wav(Audio(1000, np.ones(3000))), 48000)
    with pytest.raises(WavError, match="silent"):
        load_ir(write_wav(Audio(48000, np.zeros(100))), 48000)


def test_convolve_matches_direct_convolution() -> None:
    rng = np.random.default_rng(1)
    x, h = rng.normal(size=1000), rng.normal(size=37)
    assert convolve(x, h) == pytest.approx(np.convolve(x, h)[:1000])
    assert len(convolve(np.zeros(0), h)) == 0
