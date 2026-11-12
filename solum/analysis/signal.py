"""Waveform measures at a node: gain vs input, polarity, peaks, harmonics, clipping.

The transient runs a sine at the guitar input; these functions look at a whole number
of cycles at the end (after the circuit has settled), resampled onto an even grid so
the FFT bins land exactly on the harmonics.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from solum.analysis.measures import PLOT_BAND

Array = npt.NDArray[np.float64]
HARMONICS = range(2, 9)  # 2nd to 8th
SAMPLES_PER_CYCLE = 256

# THD bands for the clipping estimate (D-038).
CLIPPING_BANDS: tuple[tuple[float, str], ...] = (
    (0.01, "clean"),
    (0.05, "light"),
    (0.20, "moderate"),
    (math.inf, "heavy"),
)


def last_cycles(time: Array, wave: Array, freq: float, cycles: int) -> Array:
    """The last `cycles` periods of `wave`, resampled to SAMPLES_PER_CYCLE per period."""
    end = time[-1]
    start = end - cycles / freq
    if start < time[0] - 1e-12:
        raise ValueError(f"Need {cycles} cycles of {freq} Hz; the run is too short.")
    n = cycles * SAMPLES_PER_CYCLE
    grid = start + np.arange(n) / (n / (end - start))
    return np.asarray(np.interp(grid, time, wave), dtype=np.float64)


def spectrum(samples: Array, cycles: int, count: int = 8) -> tuple[Array, Array]:
    """(amplitude, phase) of harmonics 1..count. Index 0 is harmonic 1."""
    bins = np.fft.rfft(samples) * 2 / len(samples)
    picked = bins[[cycles * k for k in range(1, count + 1)]]
    return np.abs(picked), np.angle(picked)


def detrend(samples: Array, cycles: int) -> Array:
    """Remove the drift of a coupling cap still charging during the window (left in, it
    leaks into every harmonic). The slope comes from the first and last cycle's averages,
    which are equal for any periodic signal, so a steady waveform is left untouched."""
    means = samples.reshape(cycles, -1).mean(axis=1)
    per_cycle = len(samples) // cycles
    slope = (means[-1] - means[0]) / ((cycles - 1) * per_cycle) if cycles > 1 else 0.0
    x = np.arange(len(samples), dtype=np.float64) - (len(samples) - 1) / 2
    return np.asarray(samples - slope * x, dtype=np.float64)


@dataclass(frozen=True)
class Clipping:
    thd: float  # total harmonic distortion, 0-1 (harmonics 2-8 vs the fundamental)
    label: str  # clean, light, moderate, heavy
    asymmetry: float  # (peak+ - |peak-|) / (peak+ + |peak-|); 0 = symmetric


@dataclass(frozen=True)
class NodeStats:
    dc: float
    amplitude: float  # fundamental, volts peak
    gain_db: float  # fundamental vs the input's fundamental
    polarity: str  # "same" or "inverted"
    peak_pos: float  # above the mean, volts
    peak_neg: float  # below the mean, volts (negative)
    harmonics_db: dict[int, float]  # 2..8, dB relative to the fundamental
    clipping: Clipping


def clipping_label(thd: float) -> str:
    return next(label for limit, label in CLIPPING_BANDS if thd < limit)


def node_stats(time: Array, wave: Array, reference: Array, freq: float, cycles: int) -> NodeStats:
    """Stats for `wave` against the input `reference` over the last `cycles` periods."""
    v = detrend(last_cycles(time, wave, freq, cycles), cycles)
    dc = float(np.mean(v))
    ref = last_cycles(time, reference, freq, cycles)
    amps, phases = spectrum(v, cycles)
    ref_amps, ref_phases = spectrum(ref, cycles, count=1)
    fundamental = float(amps[0])
    floor = max(fundamental, 1e-15)
    shift = math.remainder(float(phases[0] - ref_phases[0]), 2 * math.pi)
    peak_pos, peak_neg = float(v.max() - dc), float(v.min() - dc)
    span = peak_pos - peak_neg
    thd = float(math.sqrt(float(np.sum(amps[1:] ** 2))) / floor)
    return NodeStats(
        dc=dc,
        amplitude=fundamental,
        gain_db=20 * math.log10(floor / max(float(ref_amps[0]), 1e-15)),
        polarity="inverted" if abs(shift) > math.pi / 2 else "same",
        peak_pos=peak_pos,
        peak_neg=peak_neg,
        harmonics_db={
            k: 20 * math.log10(max(float(amps[k - 1]), 1e-15) / floor) for k in HARMONICS
        },
        clipping=Clipping(
            thd=thd,
            label=clipping_label(thd),
            asymmetry=(peak_pos + peak_neg) / span if span > 0 else 0.0,
        ),
    )


BANDS_PER_OCTAVE = 6
SILENT_DB = -200.0  # what `band_levels` reads in a band with nothing in it
BAND_LOW, BAND_HIGH = PLOT_BAND  # the Frequency plot's band, so both plots span the same (D-102)


def band_centres(per_octave: int = BANDS_PER_OCTAVE) -> Array:
    """The centres of the 1/`per_octave`-octave bands from `BAND_LOW` up to `BAND_HIGH`."""
    count = int(np.floor(per_octave * np.log2(BAND_HIGH / BAND_LOW))) + 1
    return np.asarray(BAND_LOW * 2.0 ** (np.arange(count) / per_octave), dtype=np.float64)


def band_levels(
    samples: Array, rate: float, per_octave: int = BANDS_PER_OCTAVE, segment: int = 8192
) -> tuple[Array, Array]:
    """A recording's spectrum as (band centres, level in dB re 1 RMS per band): the power
    in each 1/`per_octave`-octave band, averaged over Hann-windowed half-overlapping
    segments (Welch's method), so a sine of peak A reads 20·log10(A/√2) in its band. A
    silent band reads -200 dB (D-096: the Audio panel's take spectrum). Each segment's
    mean is taken off first, so a DC offset doesn't leak into the lowest bands. Each bin
    stands for the stretch of width `step` around it and a band takes the share of it that
    falls inside, so the lowest bands, narrower than a bin, read true; a band whose
    centre is past half the rate (Nyquist) is left off, and one reaching past it is read
    from its part below Nyquist, scaled to its width (D-102)."""
    x = np.asarray(samples, dtype=np.float64)
    n = min(segment, len(x))
    window = np.hanning(n)
    starts = range(0, max(len(x) - n, 0) + 1, max(n // 2, 1))
    power = np.mean(
        [np.abs(np.fft.rfft((x[s : s + n] - np.mean(x[s : s + n])) * window)) ** 2 for s in starts],
        axis=0,
    )
    power *= 2 / (n * np.sum(window**2))  # one-sided, so the bins of a band sum to its mean square
    power[0] /= 2  # DC isn't doubled
    freq = np.fft.rfftfreq(n, 1 / rate)
    half = 2.0 ** (1 / (2 * per_octave))
    centres = band_centres(per_octave)
    nyquist = rate / 2
    centres = centres[centres < nyquist]
    step = float(freq[1] - freq[0]) if len(freq) > 1 else rate
    # each bin stands for the stretch of width `step` around it; a band takes the share of
    # each bin's power that falls inside it, so a band narrower than a bin isn't over-read
    # the top band can reach past Nyquist: it's read from the part below it, over its width
    lo, hi = freq - step / 2, np.minimum(freq + step / 2, nyquist)
    levels = [
        float(np.sum(power * np.clip(np.minimum(hi, c * half) - np.maximum(lo, c / half), 0, None)))
        / step
        * (c * half - c / half)
        / (min(c * half, nyquist) - c / half)
        for c in centres
    ]
    floor = 10 ** (SILENT_DB / 10)
    return centres, np.asarray(10 * np.log10(np.maximum(levels, floor)), dtype=np.float64)
