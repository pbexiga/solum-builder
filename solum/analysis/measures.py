"""Frequency-response measures (the one owner).

All take `freq` (Hz, ascending) and a complex response `h`, and work in dB. `measure`
is the entry point by name (`MEASURES`); `readings` gives the Frequency panel's row
(`CURVE_MEASURES`) as text.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from solum.units import format_quantity

Array = npt.NDArray[np.float64]
Complex = npt.NDArray[np.complex128]
Response = Complex | Array  # a complex response, or its magnitude (a curve from the browser)


# The Frequency plot's band (D-102): FabFilter Pro-Q's 10 Hz - 30 kHz, which takes in a
# 6-string bass's low B (30.9 Hz). ngspice sweeps wider; the panel's layers (knees, peaks,
# knob bands, part influence) describe only this band, so they say only what's on the plot.
PLOT_BAND = (10.0, 30e3)


def plotted(freq: Array, *responses: Response) -> tuple[Array, list[Response]]:
    """`freq` and each response cut to PLOT_BAND (left whole when fewer than 3 points
    would remain: a narrow test grid)."""
    lo, hi = PLOT_BAND
    keep = (freq >= lo * (1 - 1e-9)) & (freq <= hi * (1 + 1e-9))
    if int(keep.sum()) < 3:
        return freq, list(responses)
    return freq[keep], [r[keep] for r in responses]


def to_db(h: Response) -> Array:
    return 20 * np.log10(np.maximum(np.abs(h), 1e-15))


def gain_at(freq: Array, h: Response, f: float) -> float:
    """Gain in dB at `f`, interpolated on a log-frequency axis."""
    if not freq[0] <= f <= freq[-1]:
        raise ValueError(f"{f} Hz is outside the sweep ({freq[0]:g}-{freq[-1]:g} Hz).")
    return float(np.interp(math.log10(f), np.log10(freq), to_db(h)))


def peak(freq: Array, h: Response) -> tuple[float, float]:
    """(frequency, dB) of the highest gain, between grid points when it's inside the sweep
    (as the Peaks layer marks it)."""
    db = to_db(h)
    i = int(np.argmax(db))
    if 0 < i < len(db) - 1:
        top = _refine(freq, db, i)
        return top.f, top.db
    return float(freq[i]), float(db[i])


def notch(freq: Array, h: Response, band: tuple[float, float] | None = None) -> tuple[float, float]:
    """(frequency, dB) of the lowest gain, optionally within `band` (Hz)."""
    db = to_db(h)
    mask = np.ones_like(freq, dtype=bool) if band is None else (freq >= band[0]) & (freq <= band[1])
    i = int(np.flatnonzero(mask)[np.argmin(db[mask])])
    return float(freq[i]), float(db[i])


def corner_3db(freq: Array, h: Response, side: str, drop: float = 3.0) -> float:
    """Where gain falls `drop` dB (3 by default) below its peak: `side` "low" (the
    high-pass edge, below the peak) or "high"."""
    db = to_db(h)
    top = int(np.argmax(db))
    target = db[top] - drop
    if side == "high":
        idx = np.flatnonzero(db[top:] < target)
        if not len(idx):
            raise ValueError(
                f"The response doesn't fall {drop:g} dB above its peak within the sweep."
            )
        i = top + int(idx[0])
        lo, hi = i - 1, i
    elif side == "low":
        idx = np.flatnonzero(db[: top + 1] < target)
        if not len(idx):
            raise ValueError(
                f"The response doesn't fall {drop:g} dB below its peak within the sweep."
            )
        lo, hi = int(idx[-1]), int(idx[-1]) + 1
    else:
        raise ValueError('side must be "low" or "high"')
    return crossing(freq, db, lo, hi, target)


def crossing(freq: Array, db: Array, lo: int, hi: int, target: float) -> float:
    """Where the line between points lo and hi (log frequency, dB) reaches `target`."""
    x = np.log10(freq[[lo, hi]])
    y = db[[lo, hi]]
    return float(10 ** (x[0] + (target - y[0]) * (x[1] - x[0]) / (y[1] - y[0])))


def notch_depth(freq: Array, h: Response, band: tuple[float, float] | None = None) -> float:
    """How far the notch (lowest point, within `band`) dips below the lower of its two
    shoulders, the highest points either side of it in the sweep (negative dB).
    ValueError when the lowest point is at an end: the response has no dip."""
    f, low = notch(freq, h, band)
    i = int(np.searchsorted(freq, f))
    db = to_db(h)
    if i == 0 or i == len(freq) - 1 or not (db[:i].max() > low < db[i + 1 :].max()):
        raise ValueError("The response has no dip within the sweep.")
    return float(low - min(db[:i].max(), db[i + 1 :].max()))


def band_edges(freq: Array, h: Response, drop: float = 3.0) -> tuple[float, float]:
    """(low, high) edges of the pass band: `drop` dB below the peak on either side."""
    return corner_3db(freq, h, "low", drop), corner_3db(freq, h, "high", drop)


SHELF_MIN_DB = 1.0  # smaller steps between the ends aren't called a shelf


def shelf(freq: Array, h: Response) -> tuple[float, float, float]:
    """(gain at the low end, gain at the high end, frequency of the step's midpoint in dB):
    a bypass-cap or tone shelf. ValueError when the ends differ by under SHELF_MIN_DB."""
    db = to_db(h)
    low, high = float(db[0]), float(db[-1])
    if abs(high - low) < SHELF_MIN_DB:
        raise ValueError(
            f"The response has no shelf: its ends differ by under {SHELF_MIN_DB:g} dB."
        )
    mid = (low + high) / 2
    above = db > mid if high > low else db < mid
    i = int(np.argmax(above))
    return low, high, crossing(freq, db, i - 1, i, mid)


EXTREMA_DB = 1.0  # a peak or dip must stand this far above (below) what's around it
STILL_FALLING = 3.0  # dB/octave at a sweep end: a roll-off still going, not a shelf
FLAT_DB = 3.0  # a curve that varies less than this is flat: it has no knees


@dataclass(frozen=True)
class Extremum:
    """A peak or a dip inside the sweep: its frequency (between grid points) and level."""

    f: float
    db: float


def _prominence(db: Array, i: int) -> float:
    """How far point i stands above the higher of the lowest points either side of it,
    looking out until the curve rises above it again (or the sweep ends)."""
    left = db[i::-1]
    right = db[i:]
    lo = []
    for side in (left, right):
        higher = np.flatnonzero(side > db[i])
        lo.append(float(side[: higher[0] if len(higher) else len(side)].min()))
    return float(db[i] - max(lo))


def _refine(freq: Array, db: Array, i: int) -> Extremum:
    """The top of a parabola through points i-1, i, i+1 on a log-frequency axis."""
    x = np.log10(freq[i - 1 : i + 2])
    y = db[i - 1 : i + 2]
    bend = y[0] - 2 * y[1] + y[2]
    p = 0.0 if bend == 0 else float(np.clip(0.5 * (y[0] - y[2]) / bend, -1, 1))
    step = (x[2] - x[0]) / 2
    return Extremum(float(10 ** (x[1] + p * step)), float(y[1] - 0.25 * (y[0] - y[2]) * p))


def extrema(
    freq: Array, h: Response, prominence: float = EXTREMA_DB
) -> tuple[list[Extremum], list[Extremum]]:
    """(peaks, dips) inside the sweep, each standing at least `prominence` dB clear of the
    curve around it; never at a sweep end (a curve that only falls has no peak)."""
    db = to_db(h)
    found: tuple[list[Extremum], list[Extremum]] = ([], [])
    for sign, out in ((1.0, found[0]), (-1.0, found[1])):
        y = sign * db
        for i in range(1, len(y) - 1):
            if y[i] > y[i - 1] and y[i] >= y[i + 1] and _prominence(y, i) >= prominence:
                e = _refine(freq, y, i)
                out.append(Extremum(e.f, sign * e.db))
    return found


def _end_slope(freq: Array, db: Array, side: str) -> float:
    """dB per octave the curve falls over the last half octave at one end of the sweep,
    going outwards (positive: still falling there)."""
    octaves = np.log2(freq / freq[0]) if side == "low" else np.log2(freq[-1] / freq)
    inner = int(np.flatnonzero(octaves <= 0.5)[-1 if side == "low" else 0])
    end = 0 if side == "low" else len(freq) - 1
    span = abs(octaves[inner] - octaves[end]) or 1.0
    return float((db[inner] - db[end]) / span)


def curve_shape(freq: Array, h: Response) -> str:
    """What kind of curve it is, for reading its knees: "low-pass", "high-pass", "band" (one
    hump), "flat" (varies under FLAT_DB), or "shaped" (shelves, several bumps, a dip)."""
    db = to_db(h)
    if db.max() - db.min() < FLAT_DB:
        return "flat"
    peaks, dips = extrema(freq, h)
    falling = {side: _end_slope(freq, db, side) >= STILL_FALLING for side in ("low", "high")}
    top = int(np.argmax(db))
    if dips or len(peaks) > 1:
        return "shaped"
    if peaks:
        return "band" if falling["low"] and falling["high"] else "shaped"
    if top == 0 and falling["high"]:
        return "low-pass"
    if top == len(db) - 1 and falling["low"]:
        return "high-pass"
    return "shaped"


@dataclass(frozen=True)
class Knee:
    """Where the curve is 3 dB below its peak on one side. `simple`: a low-pass, high-pass
    or one-hump curve, where it's the band's corner; otherwise only a point 3 dB below the
    peak (on a shelf, say), not to be read as a corner."""

    side: str  # "low" or "high"
    f: float
    simple: bool


def knees(freq: Array, h: Response) -> list[Knee]:
    """The -3 dB knees of a curve (`corner_3db`), low first; none on a flat curve."""
    shape = curve_shape(freq, h)
    if shape == "flat":
        return []
    found = []
    for side in ("low", "high"):
        try:
            f = corner_3db(freq, h, side)
        except ValueError:
            continue
        found.append(Knee(side, f, shape != "shaped"))
    return found


def features(freq: Array, h: Response) -> dict[str, Any]:
    """A curve's shape, knees, peaks and dips, as numbers and text: the Frequency panel's
    Knees and Peaks layers (Phase 8b). A knee's `db` is the curve's level there (where
    Edit mode's handle sits). Only the plotted band counts (`plotted`)."""
    freq, (h,) = plotted(freq, h)
    peaks, dips = extrema(freq, h)
    logf, db = np.log10(freq), to_db(h)

    def point(e: Extremum) -> dict[str, Any]:
        return {"f": e.f, "db": e.db, "text": format_quantity(e.f, "Hz")}

    return {
        "shape": curve_shape(freq, h),
        "knees": [
            {
                "side": k.side,
                "f": k.f,
                "db": float(np.interp(math.log10(k.f), logf, db)),
                "simple": k.simple,
                "text": format_quantity(k.f, "Hz"),
            }
            for k in knees(freq, h)
        ],
        "peaks": [point(e) for e in peaks],
        "dips": [point(e) for e in dips],
    }


@dataclass(frozen=True)
class Reading:
    """One number a measure gives: `name` ("f", "gain", "depth", "low", "high"…)."""

    name: str
    value: float
    unit: str  # "Hz" or "dB"


def _gain_at(freq: Array, h: Response, f: float) -> list[Reading]:
    return [Reading("gain", gain_at(freq, h, f), "dB")]


def _peak(freq: Array, h: Response) -> list[Reading]:
    f, db = peak(freq, h)
    return [Reading("f", f, "Hz"), Reading("gain", db, "dB")]


def _notch(freq: Array, h: Response, band: Sequence[float] | None = None) -> list[Reading]:
    span = (float(band[0]), float(band[1])) if band else None
    depth = notch_depth(freq, h, span)
    f, db = notch(freq, h, span)
    return [Reading("f", f, "Hz"), Reading("gain", db, "dB"), Reading("depth", depth, "dB")]


def _corner(freq: Array, h: Response, side: str, drop: float = 3.0) -> list[Reading]:
    return [Reading("f", corner_3db(freq, h, side, drop), "Hz")]


def _band_edges(freq: Array, h: Response, drop: float = 3.0) -> list[Reading]:
    low, high = band_edges(freq, h, drop)
    return [Reading("low", low, "Hz"), Reading("high", high, "Hz")]


def _shelf(freq: Array, h: Response) -> list[Reading]:
    low, high, f = shelf(freq, h)
    return [Reading("low", low, "dB"), Reading("high", high, "dB"), Reading("f", f, "Hz")]


MEASURES: dict[str, Callable[..., list[Reading]]] = {
    "gain_at": _gain_at,  # f
    "peak": _peak,
    "notch": _notch,  # band (optional)
    "corner": _corner,  # side, drop (optional)
    "band_edges": _band_edges,  # drop (optional)
    "shelf": _shelf,
}


def measure(kind: str, freq: Array, h: Response, **args: Any) -> list[Reading]:
    """A measure by name with its arguments (`measure("gain_at", freq, h, f=1000)`).
    ValueError, in plain English, when the response hasn't got that feature."""
    try:
        fn = MEASURES[kind]
    except KeyError:
        raise ValueError(f"Unknown measure {kind!r}; use one of {', '.join(MEASURES)}.") from None
    try:
        return fn(freq, h, **args)
    except TypeError as err:
        raise ValueError(f"Measure {kind!r} got arguments it doesn't take: {err}") from None


# What the Frequency panel reads off every curve (D-081).
CURVE_MEASURES: tuple[dict[str, Any], ...] = (
    {"kind": "gain_at", "f": 1000.0, "label": "At 1 kHz"},
    {"kind": "peak", "label": "Peak"},
    {"kind": "corner", "side": "low", "label": "Low -3 dB"},
    {"kind": "corner", "side": "high", "label": "High -3 dB"},
    {"kind": "notch", "label": "Dip"},
)


def _reading_text(r: Reading) -> str:
    return format_quantity(r.value, "Hz") if r.unit == "Hz" else f"{r.value:.1f} dB"


def readings(
    freq: Array, h: Response, declared: Sequence[dict[str, Any]] = CURVE_MEASURES
) -> list[dict[str, Any]]:
    """Each declared measure (kind, its arguments, a label) with its readings as numbers
    and text, or `none`: why the curve hasn't got it."""
    out = []
    for d in declared:
        args = {k: v for k, v in d.items() if k not in ("kind", "label")}
        item: dict[str, Any] = {"label": d.get("label", d["kind"]), "kind": d["kind"]}
        try:
            found = measure(d["kind"], freq, h, **args)
        except ValueError as err:
            item["none"] = str(err)
        else:
            item["readings"] = [
                {"name": r.name, "value": r.value, "unit": r.unit, "text": _reading_text(r)}
                for r in found
            ]
        out.append(item)
    return out
