"""Cab impulse responses: load an IR WAV and convolve with it.

An IR is scaled to unit energy (the sum of its squared samples is 1), so swapping cabs
changes the tone, not the overall loudness of broadband sound. Captures and IRs are
recorded at very different levels, and the loudness of the amp belongs to the amp.
"""

import numpy as np
import numpy.typing as npt

from solum.audio.resample import resample
from solum.audio.wav import WavError, read_wav

Array = npt.NDArray[np.float64]

MAX_IR_SECONDS = 2.0  # cab IRs are a few hundred ms; longer files are rooms or mistakes


def load_ir(data: bytes, rate: int) -> Array:
    """An IR WAV at `rate`, unit energy. WavError (plain English) if unusable."""
    audio = read_wav(data)
    if audio.seconds > MAX_IR_SECONDS:
        raise WavError(
            f"This IR is {audio.seconds:.1f} s long; a cab IR is under {MAX_IR_SECONDS:g} s. "
            "Pick a cab IR, not a room or reverb."
        )
    h = resample(audio.samples, audio.rate, rate)
    energy = float(np.sum(h * h))
    if energy == 0:
        raise WavError("This IR is silent.")
    return np.asarray(h / np.sqrt(energy), dtype=np.float64)


def convolve(x: Array, h: Array) -> Array:
    """`x` through the IR `h` (FFT convolution), cut to `x`'s length."""
    if len(x) == 0 or len(h) == 0:
        return np.zeros(len(x))
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)
    return np.asarray(y[: len(x)], dtype=np.float64)
