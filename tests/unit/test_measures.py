import math

import numpy as np
import pytest

from solum.analysis.measures import (
    CURVE_MEASURES,
    MEASURES,
    Knee,
    band_edges,
    corner_3db,
    curve_shape,
    extrema,
    features,
    gain_at,
    knees,
    measure,
    notch,
    notch_depth,
    peak,
    plotted,
    readings,
    shelf,
)

FREQ = np.logspace(1, 5, 801)


def lowpass(fc: float) -> np.ndarray:
    return 1 / (1 + 1j * FREQ / fc)


def highpass(fc: float) -> np.ndarray:
    return (1j * FREQ / fc) / (1 + 1j * FREQ / fc)


def test_rc_corner_matches_formula() -> None:
    fc = 1 / (2 * math.pi * 1e3 * 0.22e-6)  # TS808 R7/C5: 723.4 Hz
    # 3 dB below the sweep's own peak, read off a 200 points/decade curve: within 0.5 %
    assert corner_3db(FREQ, lowpass(fc), "high") == pytest.approx(fc, rel=5e-3)
    assert corner_3db(FREQ, highpass(fc), "low") == pytest.approx(fc, rel=5e-3)


def test_band_pass_edges() -> None:
    """Edges are 3 dB below the (slightly < 0 dB) peak, so they sit a little outside."""
    h = highpass(100) * lowpass(5000)
    assert corner_3db(FREQ, h, "low") == pytest.approx(100, rel=0.05)
    assert corner_3db(FREQ, h, "high") == pytest.approx(5000, rel=0.05)


def test_gain_at_and_peak() -> None:
    h = 10 * lowpass(1000)
    assert gain_at(FREQ, h, 1000) == pytest.approx(20 - 3.0103, abs=0.01)
    assert peak(FREQ, h) == (pytest.approx(10), pytest.approx(20, abs=1e-3))
    with pytest.raises(ValueError, match="outside the sweep"):
        gain_at(FREQ, h, 1)


def test_notch() -> None:
    f0 = 1000.0
    h = (1 - (FREQ / f0) ** 2) / (1 - (FREQ / f0) ** 2 + 1j * FREQ / f0)  # band-stop
    f, db = notch(FREQ, h)
    assert f == pytest.approx(f0, rel=0.02)
    assert db < -30
    assert notch(FREQ, h, band=(10, 100))[0] == pytest.approx(100, rel=0.02)


def test_corner_errors() -> None:
    with pytest.raises(ValueError, match="doesn't fall 3 dB"):
        corner_3db(FREQ, np.ones_like(FREQ, dtype=complex), "high")
    with pytest.raises(ValueError, match="side must be"):
        corner_3db(FREQ, lowpass(100), "middle")


def test_corner_with_another_drop() -> None:
    # a first-order low-pass is 1 dB down where |1 + jf/fc|² = 10^0.1: f = fc·√(10^0.1 - 1)
    fc = 1000.0
    expected = fc * math.sqrt(10**0.1 - 1)  # 508.8 Hz
    assert corner_3db(FREQ, lowpass(fc), "high", drop=1.0) == pytest.approx(expected, rel=5e-3)


def test_band_edges_are_both_corners() -> None:
    h = highpass(100) * lowpass(5000)
    low, high = band_edges(FREQ, h)
    assert (low, high) == (corner_3db(FREQ, h, "low"), corner_3db(FREQ, h, "high"))
    assert low == pytest.approx(100, rel=0.05) and high == pytest.approx(5000, rel=0.05)


def band_stop(f0: float, q: float = 1.0) -> np.ndarray:
    s = 1j * FREQ / f0
    return (1 + s**2) / (1 + s / q + s**2)


def test_notch_depth_is_below_the_lower_shoulder() -> None:
    # a band-stop (f0 = 1 kHz, off the grid) after a -6 dB high shelf: shoulders at 0 dB
    # (low side) and -6 dB (high side), so the depth counts from -6 dB
    h = band_stop(1010) * (1 + 1j * FREQ / 2000) / (1 + 1j * FREQ / 1000)
    _, low = notch(FREQ, h)
    high_shoulder = float(20 * np.log10(np.abs(h[FREQ > 1010]).max()))
    assert -6.1 < high_shoulder < -5.0  # the wide notch still pulls the top end down a little
    assert notch_depth(FREQ, h) == pytest.approx(low - high_shoulder)
    assert notch_depth(FREQ, h) < -30


def test_no_dip_no_notch_depth() -> None:
    with pytest.raises(ValueError, match="no dip"):
        notch_depth(FREQ, lowpass(1000))


def test_shelf() -> None:
    # 1 + jf/f1 over 1 + jf/f2 (f1 = 100, f2 = 1000): a +20 dB high shelf, midpoint in dB
    # at the geometric mean, √(f1·f2) = 316 Hz
    h = (1 + 1j * FREQ / 100) / (1 + 1j * FREQ / 1000)
    low, high, f = shelf(FREQ, h)
    # the sweep's ends (10 Hz, 100 kHz) are 0.04 dB short of the shelf's levels
    assert low == pytest.approx(0, abs=0.05) and high == pytest.approx(20, abs=0.05)
    assert f == pytest.approx(math.sqrt(100 * 1000), rel=0.01)
    with pytest.raises(ValueError, match="no shelf"):
        shelf(FREQ, np.ones_like(FREQ, dtype=complex))


def test_measure_by_name() -> None:
    h = 10 * lowpass(1000)
    [gain] = measure("gain_at", FREQ, h, f=1000)
    assert (gain.name, gain.unit) == ("gain", "dB")
    assert gain.value == pytest.approx(20 - 3.0103, abs=0.01)
    [corner] = measure("corner", FREQ, h, side="high")
    assert corner.value == pytest.approx(1000, rel=5e-3) and corner.unit == "Hz"
    names = [r.name for r in measure("notch", FREQ, band_stop(1000))]
    assert names == ["f", "gain", "depth"]
    assert set(MEASURES) == {"gain_at", "peak", "notch", "corner", "band_edges", "shelf"}
    with pytest.raises(ValueError, match="Unknown measure"):
        measure("bogus", FREQ, h)
    with pytest.raises(ValueError, match="doesn't take"):
        measure("peak", FREQ, h, f=3)


def test_curve_readings_for_the_frequency_panel() -> None:
    rows = {r["label"]: r for r in readings(FREQ, 10 * lowpass(1000))}
    assert list(rows) == [d["label"] for d in CURVE_MEASURES]
    at = rows["At 1 kHz"]["readings"][0]
    assert at["value"] == pytest.approx(16.99, abs=0.01) and at["text"] == "17.0 dB"
    [high] = rows["High -3 dB"]["readings"]
    assert high["unit"] == "Hz" and high["value"] == pytest.approx(1000, rel=5e-3)
    assert high["text"] == "998 Hz"  # 3 significant figures (format_quantity)
    # a low-pass has no low corner and no dip: each says why
    assert "readings" not in rows["Low -3 dB"] and "3 dB" in rows["Low -3 dB"]["none"]
    assert "no dip" in rows["Dip"]["none"]


# ---- curve features: the Frequency panel's Knees and Peaks layers (Phase 8b) ----------


def resonance(f0: float, q: float) -> np.ndarray:
    """A second-order band-pass: unity at f0, falling 6 dB/octave either side."""
    s = 1j * FREQ / f0
    return (s / q) / (1 + s / q + s**2)


def peaking(f0: float, gain: float, q: float = 2.0) -> np.ndarray:
    """A flat line with a bump of `gain` (linear) at f0: a mid boost."""
    s = 1j * FREQ / f0
    return (1 + gain * s / q + s**2) / (1 + s / q + s**2)


def test_extrema_find_a_resonance_and_a_notch() -> None:
    peaks, dips = extrema(FREQ, resonance(1000, 5))
    assert [round(p.f) for p in peaks] == [pytest.approx(1000, rel=0.01)]
    assert peaks[0].db == pytest.approx(0, abs=0.01)
    assert dips == []
    f0 = 1000.0
    band_stop = (1 - (FREQ / f0) ** 2) / (1 - (FREQ / f0) ** 2 + 1j * FREQ / f0)
    peaks, dips = extrema(FREQ, band_stop)
    assert peaks == [] and len(dips) == 1 and dips[0].f == pytest.approx(f0, rel=0.01)


def test_extrema_need_prominence_and_skip_the_ends() -> None:
    assert extrema(FREQ, lowpass(1000)) == ([], [])  # the top is at an end: no peak
    small = peaking(1000, 10 ** (0.5 / 20))  # a 0.5 dB bump: under EXTREMA_DB
    assert extrema(FREQ, small) == ([], [])
    assert len(extrema(FREQ, small, prominence=0.2)[0]) == 1


def test_extrema_lie_between_grid_points() -> None:
    coarse = np.logspace(1, 5, 81)  # 20 points a decade: 12 % apart
    s = 1j * coarse / 1234.0
    peaks, _ = extrema(coarse, (s / 5) / (1 + s / 5 + s**2))
    assert peaks[0].f == pytest.approx(1234, rel=0.01)


@pytest.mark.parametrize(
    ("h", "shape"),
    [
        (lowpass(1000), "low-pass"),
        (highpass(100), "high-pass"),
        (highpass(100) * lowpass(5000), "band"),
        (resonance(1000, 5), "band"),
        (np.ones_like(FREQ, dtype=complex), "flat"),
        (1.2 * lowpass(1e9), "flat"),  # 1.6 dB: no knees
        ((1 + 1j * FREQ / 100) / (1 + 1j * FREQ / 1000), "shaped"),  # a 20 dB shelf
        (peaking(1000, 4), "shaped"),  # a bump on a flat line
        (lowpass(1000) * peaking(100, 0.25), "shaped"),  # a dip
    ],
)
def test_curve_shape(h: np.ndarray, shape: str) -> None:
    assert curve_shape(FREQ, h) == shape


def test_knees_are_the_corners_on_simple_curves() -> None:
    assert knees(FREQ, lowpass(1000)) == [Knee("high", pytest.approx(1000, rel=5e-3), True)]
    found = knees(FREQ, highpass(100) * lowpass(5000))
    assert [(k.side, k.simple) for k in found] == [("low", True), ("high", True)]
    assert found[0].f == corner_3db(FREQ, highpass(100) * lowpass(5000), "low")
    assert knees(FREQ, np.ones_like(FREQ, dtype=complex)) == []


def test_knees_on_a_shelf_are_only_3db_below_the_peak() -> None:
    shelf_up = (1 + 1j * FREQ / 100) / (1 + 1j * FREQ / 1000)
    assert [(k.side, k.simple) for k in knees(FREQ, shelf_up)] == [("low", False)]


def test_features_as_numbers_and_text() -> None:
    got = features(FREQ, highpass(100) * lowpass(5000))
    assert got["shape"] == "band"
    assert [k["side"] for k in got["knees"]] == ["low", "high"]
    assert got["knees"][0]["text"].endswith("Hz")
    # each knee's level: 3 dB under the top (where Edit mode's handle sits)
    top = got["peaks"][0]["db"]
    assert [k["db"] for k in got["knees"]] == [pytest.approx(top - 3, abs=0.01)] * 2
    assert got["peaks"][0]["text"].endswith("Hz")  # the hump's top, between the corners
    assert 100 < got["peaks"][0]["f"] < 5000
    assert got["dips"] == []
    flat = features(FREQ, np.ones_like(FREQ, dtype=complex))
    assert flat == {"shape": "flat", "knees": [], "peaks": [], "dips": []}


def test_plotted_band_and_features_on_it() -> None:
    """The layers describe 10 Hz - 30 kHz only (D-102): a treble corner at 60 kHz is off
    the plot, so the curve there is a high-pass with one knee."""
    f, (h,) = plotted(FREQ, highpass(100) * lowpass(60e3))
    assert f[0] == pytest.approx(10) and f[-1] <= 30e3 and len(f) == len(h)
    got = features(FREQ, highpass(100) * lowpass(60e3))
    assert [k["side"] for k in got["knees"]] == ["low"]
    narrow = np.array([40e3, 50e3, 60e3])  # nothing in the band: left whole
    assert plotted(narrow, narrow)[0] is narrow


def test_measures_take_a_magnitude_too() -> None:
    """The browser sends dB; the measures work on |h| alone."""
    h = highpass(100) * lowpass(5000)
    assert readings(FREQ, np.abs(h)) == readings(FREQ, h)
