"""Knob ranges and part influence (Phase 8b): curves with answers worked out by hand."""

import math
import re

import numpy as np
import pytest

from solum.analysis.compare import (
    INFLUENCE_FLOOR_DB,
    CurveError,
    act_band,
    curves_from_db,
    handles,
    influence,
    knob_range,
    level_moves,
)
from solum.analysis.measures import plotted, to_db

FREQ = np.logspace(1, 5, 801)


def lowpass(fc: float) -> np.ndarray:
    return 1 / (1 + 1j * FREQ / fc)


def test_act_band_on_a_rising_shelf() -> None:
    """|1 + jf/1k| in dB reaches 40 dB at 100 kHz; half of that, 20 dB, is where
    |1 + jf/fc| = 10: f = 1k·√99 ≈ 9.95 kHz. It reaches the top end: "above"."""
    band = act_band(FREQ, to_db(1 + 1j * FREQ / 1000))
    assert band is not None
    assert band.kind == "above"
    assert band.lo == pytest.approx(1000 * math.sqrt(99), rel=0.01)
    assert band.hi == FREQ[-1]
    assert band.where == "above 9.95 kHz"


def test_act_band_on_a_bump() -> None:
    """A bump exp(-x²/2) in octaves x from 1 kHz is at half height at x = ±√(2 ln 2) =
    ±1.177 octaves: 442 Hz to 2.26 kHz."""
    octaves = np.log2(FREQ / 1000)
    band = act_band(FREQ, 6 * np.exp(-(octaves**2) / 2))
    assert band is not None and band.kind == "band"
    width = math.sqrt(2 * math.log(2))
    assert band.lo == pytest.approx(1000 / 2**width, rel=0.01)
    assert band.hi == pytest.approx(1000 * 2**width, rel=0.01)
    assert band.centre == pytest.approx(1000, rel=0.02)


def test_act_band_everywhere_and_nowhere() -> None:
    band = act_band(FREQ, np.full_like(FREQ, -0.8))
    assert band is not None and band.kind == "everywhere" and band.where == "everywhere"
    assert act_band(FREQ, np.zeros_like(FREQ)) is None


def test_knob_range_only_on_the_plot() -> None:
    """A knob acting above 50 kHz: its band ends where the plot does (30 kHz), not at
    the sweep's 100 kHz (D-102)."""
    got = knob_range(FREQ, np.ones_like(FREQ), 1 + 1j * FREQ / 50e3, np.ones_like(FREQ))
    assert got["band"] is not None and got["band"]["hi"] <= 30e3
    # the swing is what it does at 30 kHz: |1 + j·0.6| = 1.34 dB, not the 6.99 dB at 100 kHz
    assert got["swing"] == pytest.approx(20 * math.log10(abs(1 + 0.6j)), abs=0.05)


def bass_shelf(boost: float) -> np.ndarray:
    """`boost` (linear) at low frequencies, 1 at high: boost·(1 + jf/(100·boost))/(1 + jf/100)."""
    return boost * (1 + 1j * FREQ / (100 * boost)) / (1 + 1j * FREQ / 100)


def test_knob_range_of_a_bass_shelf() -> None:
    """A bass knob from flat to a 12 dB shelf (x4 below 100 Hz, 1 above 400 Hz), now at a
    6 dB shelf. Half the change, 6 dB (x2), is where 16(1 + f²/400²) = 4(1 + f²/100²):
    f = 200 Hz. From now it goes 6 dB up and 6 dB down."""
    got = knob_range(FREQ, np.ones_like(FREQ), bass_shelf(4), bass_shelf(2))
    assert got["kind"] == "shelf"
    assert got["band"]["kind"] == "below"
    assert got["band"]["hi"] == pytest.approx(200, rel=0.01)
    assert got["swing"] == pytest.approx(20 * math.log10(4), abs=0.05)  # 12.0 at 10 Hz
    assert got["up"] == pytest.approx(6.0, abs=0.05)
    assert got["down"] == pytest.approx(-6.0, abs=0.05)
    assert re.fullmatch(r"below 20[01] Hz, ±6\.0 dB, shelf", got["text"])


def test_knob_range_from_the_top_and_off_centre() -> None:
    at_top = knob_range(FREQ, np.ones_like(FREQ), bass_shelf(4), bass_shelf(4))
    assert re.fullmatch("below 20[01] Hz, \N{MINUS SIGN}12 dB, shelf", at_top["text"])
    near = knob_range(FREQ, np.ones_like(FREQ), bass_shelf(4), bass_shelf(1.5))
    assert re.fullmatch(r"below 20[01] Hz, \+8\.5 / \u22123\.5 dB, shelf", near["text"])


def test_knob_range_of_a_volume_reads_as_level() -> None:
    """At zero the curve is nothing at all: changes count up to 60 dB, so it's everywhere."""
    got = knob_range(FREQ, np.full_like(FREQ, 1e-20), np.ones_like(FREQ), np.full_like(FREQ, 0.5))
    assert got["kind"] == "level"
    assert got["text"] == "everywhere, +6.0 / \N{MINUS SIGN}60+ dB, level"


def test_knob_range_that_barely_acts() -> None:
    same = knob_range(FREQ, lowpass(1000), 1.01 * lowpass(1000), lowpass(1000))
    assert same["band"] is None and same["text"] == "barely changes this curve"


def test_influence_ranks_and_says_what_moves() -> None:
    """A low-pass at 1 kHz: its capacitor +10 % moves the corner to 1k/1.1 = 909 Hz; a gain
    resistor lifts everything by 0.8 dB; a third part barely matters."""
    base = lowpass(1000)
    nudged = {
        "C1": lowpass(1000 / 1.1),
        "RG": base * 10 ** (0.8 / 20),
        "R9": base * 1.001,
    }
    got = influence(FREQ, base, nudged, 0.1)
    assert [r["ref"] for r in got["rows"]] == ["C1", "RG"]
    assert got["hidden"] == ["R9"]
    c1, rg = got["rows"]
    assert c1["what"] == "high knee"
    # the corner is 3 dB below the sweep's top, at 10 Hz a hair under 0 dB: 998 Hz
    assert re.match(r"moves the high knee \(treble roll-off\), 99\d Hz → 90\d Hz", c1["text"])
    assert c1["size"] == pytest.approx(20 * math.log10(1.1), abs=0.01)  # far above the corner
    assert c1["band"]["kind"] == "above"
    assert rg["what"] == "gain" and rg["text"] == "+0.8 dB everywhere"


def test_influence_at_a_frequency_sorts_by_the_change_there() -> None:
    base = lowpass(1000)
    nudged = {"C1": lowpass(1000 / 1.1), "RG": base * 10 ** (0.8 / 20)}
    got = influence(FREQ, base, nudged, 0.1, at=100)
    assert [r["ref"] for r in got["rows"]] == ["RG"]  # C1 changes 100 Hz by 0.03 dB
    assert got["rows"][0]["at"] == pytest.approx(0.8, abs=1e-6)
    assert got["at_text"] == "100 Hz"
    assert influence(FREQ, base, nudged, 0.1, at=20000)["rows"][0]["ref"] == "C1"


def test_influence_on_a_shaped_curve_names_the_peak() -> None:
    """A mid bump on a flat line: its capacitor +10 % moves the bump down by √1.1."""

    def bump(f0: float) -> np.ndarray:
        s = 1j * FREQ / f0
        return (1 + 4 * s / 2 + s**2) / (1 + s / 2 + s**2)

    got = influence(FREQ, bump(1000), {"C5": bump(1000 / math.sqrt(1.1))}, 0.1)
    row = got["rows"][0]
    assert row["what"] == "peak"
    assert row["text"].startswith("moves the peak, 1 kHz → 953 Hz")


def test_influence_floor() -> None:
    base = lowpass(1000)
    got = influence(FREQ, base, {"R1": base * 10 ** (0.01 / 20)}, 0.1)
    assert got["rows"] == [] and got["hidden"] == ["R1"]
    assert INFLUENCE_FLOOR_DB > 0.01


def test_handles_on_a_band_pass() -> None:
    """A band-pass made of a 100 Hz high-pass and a 2 kHz low-pass: two knee handles and
    its top. The
    high-pass C +10 % moves the low knee as 1/C (exponent -1); a gain resistor moves
    nothing, so it's left out; a part that moves the knee as much but also lifts the
    level goes after the one that only moves it."""

    def band(lo: float, hi: float, gain: float = 1.0) -> np.ndarray:
        s = 1j * FREQ
        return gain * (s / lo) / (1 + s / lo) / (1 + s / hi)

    base = band(100, 2000)
    nudged = {
        "RG": band(100, 2000, 1.1),
        "R4": band(100 / 1.1, 2000, 1.1),
        "C3": band(100 / 1.1, 2000),
        "C5": band(100, 2000 / 1.1),
    }
    got = handles(FREQ, base, nudged, 0.1)
    assert [h["id"] for h in got] == ["knee-low", "knee-high", "peak-0"]  # the hump's top
    low, high, top = got
    assert low["label"] == "Low knee (bass roll-off)"
    # a little under 100 Hz: the corners are close, so the top is 0.4 dB under 1 and the
    # knee (3 dB under the top) sits where the high-pass alone is down 3.4 dB
    assert 85 < low["f"] < 100
    assert low["db"] == pytest.approx(-3.0 + to_db(np.array([base.max()]))[0], abs=0.05)
    assert [p["ref"] for p in low["parts"]] == ["C3", "R4"]
    # about -1 (1/C); a little less, as the corners interact (the drag corrects for it)
    assert low["parts"][0]["exponent"] == pytest.approx(-1.0, abs=0.1)
    c3, r4 = low["parts"]
    assert r4["change"] > c3["change"] + 0.5  # R4 also lifts the level by 0.8 dB
    assert [p["ref"] for p in high["parts"]] == ["C5"]
    # the top sits between the corners (sqrt(100 x 2000)): each corner moves it by about half
    assert top["f"] == pytest.approx(math.sqrt(100 * 2000), rel=0.05)
    assert {p["ref"] for p in top["parts"]} == {"C3", "R4", "C5"}
    assert "levels" not in low and "levels" in top  # knees move sideways only
    # influence's handles are the same, on the plotted band (D-102)
    f, (b, *cut) = plotted(FREQ, base, *nudged.values())
    on_plot = handles(f, b, dict(zip(nudged, cut, strict=True)), 0.1)
    assert influence(FREQ, base, nudged, 0.1)["handles"] == on_plot
    assert [h["id"] for h in on_plot] == [h["id"] for h in got]
    # knobs and parts that set a bias move nothing in Edit curve, sideways included
    avoided = handles(FREQ, base, nudged, 0.1, avoid=["C3"])
    assert [p["ref"] for p in avoided[0]["parts"]] == ["R4"]


def test_handles_on_a_peak_and_none_on_a_shaped_curves_knees() -> None:
    """A mid bump: one peak handle (its C moves it by 1/sqrt(C): exponent -0.5); the
    curve is shaped, so its -3 dB points get no handles."""

    def bump(f0: float) -> np.ndarray:
        s = 1j * FREQ / f0
        return (1 + 4 * s / 2 + s**2) / (1 + s / 2 + s**2)

    [peak] = handles(FREQ, bump(1000), {"C5": bump(1000 / math.sqrt(1.1))}, 0.1)
    assert peak["id"] == "peak-0" and peak["label"] == "Peak" and peak["text"] == "1 kHz"
    assert peak["parts"][0]["exponent"] == pytest.approx(-0.5, abs=0.02)
    assert handles(FREQ, np.ones_like(FREQ), {}, 0.1) == []  # flat: nothing to grab


def boost(f0: float, gain: float, scale: float = 1.0) -> np.ndarray:
    """A resonant boost at f0, `gain` times up at its top (|H(j)| = gain), x `scale`."""
    s = 1j * FREQ / f0
    return scale * (1 + gain * s / 2 + s**2) / (1 + s / 2 + s**2)


def test_level_moves_cancel_the_sideways_pulls() -> None:
    """A 4x (12 dB) boost at 1 kHz. CA and CB both pull it down by 1/sqrt (exponent
    -0.5), CA raising it by 1.1^0.5 (4.34 dB per unit log value: 0.5 x 20/ln 10), CB
    lowering it as much: CA up and CB down by the same ratio keeps it at 1 kHz and raises
    it 8.69 dB per unit, and less far from it. RG raises everything (a gain:
    8.69 dB per unit, no sideways pull) so it does it alone, but spills 1:1. RS is too
    slow (0.87 dB per unit); RK is a knob (avoided)."""
    base = boost(1000, 4)
    nudged = {
        "CA": boost(1000 / math.sqrt(1.1), 4 * math.sqrt(1.1)),
        "CB": boost(1000 / math.sqrt(1.1), 4 / math.sqrt(1.1)),
        "RG": boost(1000, 4, 1.1),
        "RS": boost(1000, 4, 1.1**0.1),
        "RK": boost(1000, 4, 1.5),
    }
    [peak] = handles(FREQ, base, nudged, 0.1, avoid=["RK"])
    assert peak["f"] == pytest.approx(1000, rel=0.01)
    pair, alone = peak["levels"]
    assert pair["refs"] == ["CA", "CB"]
    assert pair["weights"] == pytest.approx([1, -1], abs=0.02)
    assert pair["slope"] == pytest.approx(2 * 0.5 * 20 / math.log(10), rel=0.03)
    assert pair["spill"] < 0.8  # a broad boost: an octave out it still moves 2/3 as much
    # each part's own pulls, for a drag that holds the frequency: CA (-0.5, +4.34), CB (-0.5, -4.34)
    assert [x for p in pair["pulls"] for x in p] == pytest.approx(
        [-0.5, 4.34, -0.5, -4.34], abs=0.05
    )
    assert alone["refs"] == ["RG"] and alone["weights"] == [1.0]
    assert alone["slope"] == pytest.approx(20 / math.log(10), rel=0.01)
    assert alone["spill"] == pytest.approx(1.0, abs=0.02)
    # without the avoid list the knob is the fastest single part
    assert ["RK"] in [m["refs"] for m in handles(FREQ, base, nudged, 0.1)[0]["levels"]]


def test_level_moves_none() -> None:
    """Parts that only pull sideways, all alike: no ratio of them changes the level."""
    pulls = {r: (-0.5, 0.0, np.zeros_like(FREQ)) for r in ("C1", "C2")}
    assert level_moves(FREQ, 1000, pulls, 0.1) == []
    assert level_moves(FREQ, 1000, {}, 0.1) == []


def test_curves_from_db() -> None:
    freq, (h,) = curves_from_db([10, 100, 1000], [0, -20, -40])
    assert list(freq) == [10, 100, 1000]
    assert list(h) == pytest.approx([1, 0.1, 0.01])
    with pytest.raises(CurveError, match="rising"):
        curves_from_db([10, 10, 1000], [0, 0, 0])
    with pytest.raises(CurveError, match="one finite level"):
        curves_from_db([10, 100, 1000], [0, 0])
