"""Waveform stats on synthetic signals with known answers."""

import math

import numpy as np
import pytest

from solum.analysis.signal import (
    band_centres,
    band_levels,
    clipping_label,
    last_cycles,
    node_stats,
    spectrum,
)

F = 200.0
T = np.linspace(0, 20 / F, 20 * 400 + 1)  # 20 cycles, 400 points each
IN = 0.1 * np.sin(2 * math.pi * F * T)


def test_clean_gain_and_polarity() -> None:
    out = 4.5 - 1.0 * np.sin(2 * math.pi * F * T)  # x10, inverted, on a 4.5 V bias
    s = node_stats(T, out, IN, F, cycles=10)
    assert s.gain_db == pytest.approx(20.0, abs=1e-3)
    assert s.polarity == "inverted"
    assert s.dc == pytest.approx(4.5, abs=1e-6)
    assert (s.peak_pos, s.peak_neg) == (pytest.approx(1.0, abs=1e-4), pytest.approx(-1.0, abs=1e-4))
    assert s.clipping.label == "clean"
    assert all(db < -80 for db in s.harmonics_db.values())


def test_hard_clipping_is_square_wave_like() -> None:
    out = np.clip(100 * IN, -0.6, 0.6)  # 10 V wanted, diodes to ground at ±0.6 V
    s = node_stats(T, out, IN, F, cycles=10)
    assert s.polarity == "same"
    assert s.peak_pos == pytest.approx(0.6, abs=1e-6)
    assert s.harmonics_db[2] < -80  # symmetric: no even harmonics
    assert s.harmonics_db[3] == pytest.approx(-9.54, abs=0.5)  # close to a square wave's 1/3
    assert s.clipping.label == "heavy"


def test_mild_overdrive_is_moderate() -> None:
    s = node_stats(T, np.clip(10 * IN, -0.6, 0.6), IN, F, cycles=10)  # 1 V wanted
    assert s.clipping.label == "moderate"
    assert s.clipping.asymmetry == pytest.approx(0.0, abs=1e-6)


def test_asymmetric_clipping_makes_even_harmonics() -> None:
    out = np.clip(10 * IN, -0.3, 0.9)
    s = node_stats(T, out, IN, F, cycles=10)
    assert s.harmonics_db[2] > -20
    assert s.clipping.asymmetry > 0.2


def test_known_harmonic_level() -> None:
    w = 2 * math.pi * F * T
    out = np.sin(w) + 0.1 * np.sin(2 * w)
    assert node_stats(T, out, IN, F, 10).harmonics_db[2] == pytest.approx(-20.0, abs=0.01)


def test_spectrum_bins() -> None:
    samples = last_cycles(T, 0.5 * np.cos(2 * math.pi * F * T), F, 4)
    amps, _ = spectrum(samples, 4, count=3)
    assert amps == pytest.approx([0.5, 0, 0], abs=1e-4)


def test_run_too_short() -> None:
    with pytest.raises(ValueError, match="too short"):
        last_cycles(T, IN, F, 50)


@pytest.mark.parametrize(("thd", "label"), [(0.0, "clean"), (0.03, "light"), (0.1, "moderate"),
                                            (0.5, "heavy")])  # fmt: skip
def test_clipping_label(thd: float, label: str) -> None:
    assert clipping_label(thd) == label


def test_slow_drift_does_not_leak_into_harmonics() -> None:
    drift = 0.5 * np.exp(-T / 0.1)  # a coupling cap still settling (tau 100 ms)
    out = np.sin(2 * math.pi * F * T) + drift
    s = node_stats(T, out, IN, F, cycles=10)
    assert all(db < -40 for db in s.harmonics_db.values())
    assert s.clipping.label == "clean"


def test_band_centres_are_sixth_octaves_from_10_hz() -> None:
    """The Frequency plot's band, 10 Hz - 30 kHz (D-102)."""
    c = band_centres()
    assert c[0] == 10.0 and c[6] == pytest.approx(20.0) and c[-1] <= 30e3
    assert len(c) == 70  # 6 per octave over log2(3000) = 11.55 octaves


def test_bands_stop_at_nyquist_and_the_lowest_read_true() -> None:
    """At 48 kHz nothing is above 24 kHz, so bands past it are left off. The bands under
    40 Hz are narrower than the 5.9 Hz bin spacing: some hold no bin, some one whole bin.
    White noise still reads its share of the power for each band's width in all of them
    (the 11.2 Hz band used to read 6.5 dB high, the user's bump at the left edge).
    A DC offset doesn't show in the low bands."""
    rate = 48000
    centres, white = band_levels(np.random.default_rng(2).normal(0, 1, 8 * rate), rate)
    half = 2 ** (1 / 12)
    assert centres[-1] < 24e3 < centres[-1] * half  # the top band reaches past Nyquist...
    top = 10 * math.log10(centres[-1] * (half - 1 / half) / 24e3)
    assert white[-1] == pytest.approx(top, abs=1.0)  # ...and reads over its whole width
    low = centres <= 40
    expected = 10 * np.log10(centres[low] * (half - 1 / half) / 24e3)
    assert white[low] == pytest.approx(expected, abs=1.5)
    t = np.arange(rate) / rate
    _, offset = band_levels(1.0 + 0.1 * np.sin(2 * np.pi * 1000 * t), rate)
    assert offset[0] < -80  # the 1 V offset would read near 0 dB here; this is the tone's leakage


def test_a_sine_reads_its_rms_in_its_band() -> None:
    """D-096: a 1 kHz sine of peak 0.5 is 0.354 V RMS, -9.03 dB, in the band around
    1016 Hz (20·2^(34/6)); a band far away is empty; white noise's bands add up to the
    share of its power they span."""
    rate = 48000
    t = np.arange(rate) / rate
    centres, levels = band_levels(0.5 * np.sin(2 * np.pi * 1000 * t), rate)
    k = int(np.argmin(np.abs(centres - 1000)))
    assert centres[k] == pytest.approx(1016, abs=1)
    assert levels[k] == pytest.approx(20 * math.log10(0.5 / math.sqrt(2)), abs=0.1)
    assert levels[k - 12] < levels[k] - 60  # two octaves down
    noise = np.random.default_rng(1).normal(0, 1, 4 * rate)
    centres, white = band_levels(noise, rate)
    # the bands hold the share of the total mean square (1) that their span has of 0-24 kHz
    half = 2 ** (1 / 12)
    span = centres[-1] * half - centres[0] / half
    total = 10 * math.log10(float(np.sum(10 ** (white / 10))))
    assert total == pytest.approx(10 * math.log10(span / 24e3), abs=0.2)


def test_a_short_or_silent_take_still_has_levels() -> None:
    centres, levels = band_levels(np.zeros(1000), 48000)
    assert len(levels) == len(centres) and np.all(levels == -200)
