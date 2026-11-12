"""What changes between frequency curves (Phase 8b): where a knob acts on a curve
(`knob_range`) and which parts shape it most (`influence`). Built on `measures`, the one
owner of curve measures; the curves come from ngspice (a knob at its ends) or from the
browser's solver (each part nudged, D-097). Pure: curves in, numbers and text out.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from solum.analysis.measures import (
    Array,
    Extremum,
    Knee,
    Response,
    crossing,
    extrema,
    knees,
    plotted,
    to_db,
)
from solum.units import format_quantity

DB_FLOOR = -120.0  # a curve below this (a volume at zero) counts as this
HALF = 0.5  # a change acts on the band where it is at least half its largest
KNOB_MIN_DB = 0.5  # a knob that changes the curve less than this barely acts on it
MOVES = 0.25  # a knee or peak "moves" when it shifts by a quarter of the nudge or more
MATCH_OCTAVES = 1 / 3  # a nudged curve's peak is the same peak within this
INFLUENCE_FLOOR_DB = 0.05  # parts moving the curve less than this are hidden
INFLUENCE_SHARE = 0.1  # ...and so are parts moving it under a tenth of the top one
MINUS = "\u2212"  # the minus sign shown in text
BIG_DB = 60.0  # changes count up to this ("60+ dB"): a volume near zero is a level change
MAX_HANDLES = 6  # handles on one curve at most: knees first, then peaks and dips
SAME_PULL = 0.05  # parts moving a handle within this of each other (exponent) count as level
LEVEL_MIN = 2.0  # dB per unit log value: a level move slower than this needs far-off values
LEVEL_AWAY_OCTAVES = 1.0  # a level move's spill: what it does this far from the peak or dip
LEVEL_CHOICES = 4  # level moves offered per peak or dip


class CurveError(ValueError):
    """Curves sent to be measured that don't fit together (plain-English message)."""


def curves_from_db(freq: Sequence[float], *curves: Sequence[float]) -> tuple[Array, list[Array]]:
    """Curves given in dB (the browser's) as magnitudes the measures take, on `freq`
    (ascending, positive, at least 3 points); every curve must have one value per
    frequency."""
    f = np.asarray(freq, dtype=np.float64)
    if f.ndim != 1 or len(f) < 3 or not np.all(f > 0) or not np.all(np.diff(f) > 0):
        raise CurveError("The frequencies must be at least 3 positive values, rising.")
    out = []
    for c in curves:
        db = np.asarray(c, dtype=np.float64)
        if db.shape != f.shape or not np.all(np.isfinite(db)):
            raise CurveError("Each curve needs one finite level per frequency.")
        out.append(10 ** (db / 20))
    return f, out


def _db(h: Response) -> Array:
    return np.maximum(to_db(h), DB_FLOOR)


def _hz(f: float) -> str:
    return format_quantity(f, "Hz")


def _amount(x: float) -> str:
    """A size in dB without its unit: "0.8", "12", "60+" (a volume near zero)."""
    size = abs(x)
    return f"{BIG_DB:.0f}+" if size >= BIG_DB else f"{size:.1f}" if size < 10 else f"{size:.0f}"


def _signed(x: float) -> str:
    """A change in dB with its sign ("+0.8 dB", "-12 dB")."""
    return f"{MINUS if x < 0 else '+'}{_amount(x)} dB"


@dataclass(frozen=True)
class Band:
    """Where a change acts: `lo`-`hi` Hz (a sweep end when it reaches it), `centre` where
    it is largest, and `kind`: "below" (reaches the low end: a shelf), "above", "band", or
    "everywhere" (both ends: the whole curve's level)."""

    lo: float
    hi: float
    centre: float
    kind: str

    @property
    def where(self) -> str:
        if self.kind == "everywhere":
            return "everywhere"
        if self.kind == "below":
            return f"below {_hz(self.hi)}"
        if self.kind == "above":
            return f"above {_hz(self.lo)}"
        return f"{_hz(self.lo)}\u2013{_hz(self.hi)}"

    @property
    def place(self) -> str:
        """`where` to follow a level: "above 1 kHz", "at 200 Hz-2 kHz", "everywhere"."""
        return f"at {self.where}" if self.kind == "band" else self.where

    def data(self) -> dict[str, Any]:
        return {"lo": self.lo, "hi": self.hi, "centre": self.centre, "kind": self.kind,
                "text": self.where}  # fmt: skip


def act_band(freq: Array, delta: Array) -> Band | None:
    """The band around the largest change where the change (dB) is at least HALF of it,
    its edges interpolated on a log-frequency axis. None when nothing changes."""
    size = np.minimum(np.abs(delta), BIG_DB)
    m = int(np.argmax(size))
    if size[m] == 0:
        return None
    target = size[m] * HALF
    lo = hi = m
    while lo > 0 and size[lo - 1] >= target:
        lo -= 1
    while hi < len(size) - 1 and size[hi + 1] >= target:
        hi += 1
    at_low, at_high = lo == 0, hi == len(size) - 1
    f_lo = float(freq[0]) if at_low else crossing(freq, size, lo - 1, lo, target)
    f_hi = float(freq[-1]) if at_high else crossing(freq, size, hi, hi + 1, target)
    kind = {(True, True): "everywhere", (True, False): "below", (False, True): "above"}.get(
        (at_low, at_high), "band"
    )
    return Band(f_lo, f_hi, float(freq[m]), kind)


KNOB_KINDS = {"below": "shelf", "above": "shelf", "band": "band", "everywhere": "level"}


def _range_text(up: float, down: float) -> str:
    """How far the knob moves the curve from where it is now: "±12 dB", "+3 / -9 dB",
    "-24 dB" (already at the top)."""
    if up < 0.05:
        return _signed(down)
    if down > -0.05:
        return _signed(up)
    if abs(up + down) <= 1:
        return f"±{_amount((up - down) / 2)} dB"
    return f"+{_amount(up)} / {_signed(down)}"


def knob_range(freq: Array, at_min: Response, at_max: Response, now: Response) -> dict[str, Any]:
    """Where a knob acts on a curve, comparing the curve with the knob at its minimum and
    maximum: the band where the change is at least half its largest (`act_band`), the
    whole swing there, how far it goes up and down from `now` (the knob where it is), and
    whether it's a shelf, a band or the level. `text`: "below 150 Hz, ±12 dB, shelf"."""
    freq, (at_min, at_max, now) = plotted(freq, at_min, at_max, now)
    lo, hi, here = _db(at_min), _db(at_max), _db(now)
    delta = hi - lo
    band = act_band(freq, delta)
    if band is None or float(np.abs(delta).max()) < KNOB_MIN_DB:
        return {"band": None, "swing": float(np.abs(delta).max()), "up": 0.0, "down": 0.0,
                "kind": None, "text": "barely changes this curve"}  # fmt: skip
    m = int(np.argmax(np.abs(delta)))
    up = float(max(lo[m], hi[m]) - here[m])
    down = float(min(lo[m], hi[m]) - here[m])
    kind = KNOB_KINDS[band.kind]
    return {
        "band": band.data(),
        "swing": float(abs(delta[m])),
        "up": up,
        "down": down,
        "kind": kind,
        "text": f"{band.where}, {_range_text(up, down)}, {kind}",
    }


def _exponent(before: float, after: float, nudge: float) -> float:
    """How a frequency follows a part's value: d log f / d log value, from one nudge (-1
    for an RC corner's C or R, which f goes as 1/value)."""
    return math.log(after / before) / math.log1p(nudge)


def _shift(before: float, after: float, nudge: float) -> float:
    """How far a frequency moved, as a share of the nudge (1: in step with the part)."""
    return abs(_exponent(before, after, nudge))


KNEE_WORDS = {"low": "bass roll-off", "high": "treble roll-off"}


def _knee_text(before: Knee, after: Knee) -> str:
    move = f"{_hz(before.f)} \u2192 {_hz(after.f)}"
    if before.simple:
        return f"moves the {before.side} knee ({KNEE_WORDS[before.side]}), {move}"
    side = "below" if before.side == "low" else "above"
    return f"moves the {MINUS}3 dB point {side} the peak, {move}"


def _knee_moved(
    freq: Array, nudged: Array, nudge: float, before: list[Knee]
) -> tuple[float, str, str] | None:
    """(share, what, text) for the knee the nudge moved most, if any."""
    after = {k.side: k for k in knees(freq, 10 ** (nudged / 20))}
    shifts = [(_shift(k.f, after[k.side].f, nudge), k) for k in before if k.side in after]
    if not shifts:
        return None
    share, knee = max(shifts, key=lambda s: s[0])
    return share, f"{knee.side} knee", _knee_text(knee, after[knee.side])


def _extremum_moved(
    freq: Array, nudged: Array, nudge: float, before: tuple[list[Extremum], list[Extremum]]
) -> tuple[float, str, str] | None:
    """(share, what, text) for the peak or dip the nudge moved most (matched within
    MATCH_OCTAVES), if any."""
    found = extrema(freq, 10 ** (nudged / 20))
    best = None
    for what, was, now in zip(("peak", "dip"), before, found, strict=True):
        for e in was:
            near = [n for n in now if abs(math.log2(n.f / e.f)) <= MATCH_OCTAVES]
            if not near:
                continue
            n = min(near, key=lambda n: abs(math.log(n.f / e.f)))
            share = _shift(e.f, n.f, nudge)
            if best is None or share > best[0]:
                best = (share, what, f"moves the {what}, {_hz(e.f)} \u2192 {_hz(n.f)}")
    return best


def _moved(
    freq: Array, nudged: Array, nudge: float, base_knees: list[Knee],
    base_extrema: tuple[list[Extremum], list[Extremum]],
) -> tuple[str, str] | None:  # fmt: skip
    """(what, text) when the nudge moves a knee, a peak or a dip by at least MOVES of
    itself. Knees come first on a simple curve (a filter's corners); on a shaped one, where
    knees are only points 3 dB below the peak, peaks and dips do. None: only the gain."""
    knee = _knee_moved(freq, nudged, nudge, base_knees)
    bump = _extremum_moved(freq, nudged, nudge, base_extrema)
    simple = any(k.simple for k in base_knees)
    for found in (knee, bump) if simple else (bump, knee):
        if found and found[0] >= MOVES:
            return found[1], found[2]
    return None


def influence(
    freq: Array,
    base: Response,
    nudged: Mapping[str, Response],
    nudge: float,
    at: float | None = None,
    avoid: Sequence[str] = (),
) -> dict[str, Any]:
    """Which parts move a curve most, from the curve with each part nudged by `nudge`
    (0.1: +10 %): each part's largest change (or its change at `at` Hz, to sort by what
    shapes the curve there), what it moves (a knee, a peak or dip, else the gain in a band)
    and where. Rows largest first; parts that barely matter (under INFLUENCE_FLOOR_DB, or
    under INFLUENCE_SHARE of the top one) are listed only by ref in `hidden`. `handles`:
    the curve's knees, peaks and dips with the parts that move each (`handles`; `avoid`:
    parts its level moves leave out). Only the plotted band counts (`plotted`)."""
    freq, (base, *cut) = plotted(freq, base, *nudged.values())
    nudged = dict(zip(nudged, cut, strict=True))
    b = _db(base)
    base_knees = knees(freq, 10 ** (b / 20))
    base_extrema = extrema(freq, 10 ** (b / 20))
    logf = np.log10(freq)
    rows: list[dict[str, Any]] = []
    for ref, h in nudged.items():
        n = _db(h)
        delta = n - b
        m = int(np.argmax(np.abs(delta)))
        here = None if at is None else float(np.interp(math.log10(at), logf, delta))
        band = act_band(freq, delta)
        moved = _moved(freq, n, nudge, base_knees, base_extrema) if band else None
        gain = f"{_signed(float(delta[m]))} {band.place}" if band else ""
        what, text = moved or ("gain", gain)
        if moved and gain:
            text = f"{text}; {gain}"
        rows.append({
            "ref": ref,
            "size": abs(here) if here is not None else float(abs(delta[m])),
            "change": float(delta[m]),
            "at": here,
            "what": what,
            "text": text,
            "band": band.data() if band else None,
        })  # fmt: skip
    rows.sort(key=lambda r: (-r["size"], r["ref"]))
    top = rows[0]["size"] if rows else 0.0
    keep = max(INFLUENCE_FLOOR_DB, INFLUENCE_SHARE * top)
    return {
        "rows": [r for r in rows if r["size"] >= keep],
        "hidden": [r["ref"] for r in rows if r["size"] < keep],
        "at": at,
        "at_text": None if at is None else _hz(at),
        "handles": handles(freq, base, nudged, nudge, avoid),
    }


def _nearest(found: list[Extremum], f: float) -> Extremum | None:
    """The one of `found` nearest `f`, within MATCH_OCTAVES (the same peak, moved)."""
    near = [n for n in found if abs(math.log2(n.f / f)) <= MATCH_OCTAVES]
    return min(near, key=lambda n: abs(math.log(n.f / f))) if near else None


def level_moves(
    freq: Array, f: float, pulls: Mapping[str, tuple[float, float, Array]], nudge: float
) -> list[dict[str, Any]]:
    """Ways to raise a peak or dip at `f` without moving it sideways (Edit curve's up/down),
    from how each part pulls it: `pulls` ref → (exponent: d log f / d log value, slope:
    dB / d log value, the nudged curve's change in dB). A part with no sideways pull
    (under SAME_PULL) does it alone; two that pull sideways change together, in the ratio
    that cancels their pulls (one up, one down when both pull the same way). Each move:
    `refs`, `weights` (each part's log value changes by its weight x t, the largest
    weight ±1), `slope` (dB per unit t, > 0) and `spill` (the most it changes the curve an
    octave or more away, as a share of what it does to the peak), `pulls` (each part's
    exponent and slope, so a drag can hold the frequency as well as set the level). Least
    spill first, then the fastest; at most LEVEL_CHOICES, none slower than LEVEL_MIN."""
    away = np.abs(np.log2(freq / f)) >= LEVEL_AWAY_OCTAVES
    alone = sorted(r for r, (e, _, _) in pulls.items() if abs(e) < SAME_PULL)
    sideways = sorted(r for r in pulls if r not in alone)
    found: list[tuple[list[str], Array]] = [([r], np.array([1.0])) for r in alone]
    for i, a in enumerate(sideways):
        for b in sideways[i + 1 :]:
            weights = np.array([pulls[b][0], -pulls[a][0]])
            found.append(([a, b], weights / np.max(np.abs(weights))))
    moves: list[tuple[float, float, list[str], Array]] = []
    for refs, weights in found:
        slope = float(weights @ [pulls[r][1] for r in refs])
        if slope < 0:
            weights, slope = -weights, -slope
        if slope < LEVEL_MIN:
            continue
        change = sum(w * pulls[r][2] for r, w in zip(refs, weights, strict=True))
        spill = float(np.max(np.abs(np.asarray(change)[away]), initial=0.0))
        moves.append((spill / math.log1p(nudge) / slope, slope, refs, weights))
    moves.sort(key=lambda m: (round(m[0], 1), -m[1]))
    return [
        {
            "refs": refs,
            "weights": [float(w) for w in weights],
            "slope": slope,
            "spill": spill,
            "pulls": [[float(pulls[r][0]), float(pulls[r][1])] for r in refs],
        }
        for spill, slope, refs, weights in moves[:LEVEL_CHOICES]
    ]


def handles(
    freq: Array,
    base: Response,
    nudged: Mapping[str, Response],
    nudge: float,
    avoid: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """The curve's handles (Phase 8b, the Frequency panel's Edit mode): each knee of a
    simple curve, each peak and dip (at most MAX_HANDLES), with the parts that move it,
    from the curve with each part nudged by `nudge`. Per part: `exponent` (d log f /
    d log value, so a drag to a frequency gives a value) and `change` (its largest change
    to the curve, dB: what it does besides). Parts moving it under MOVES of the nudge are
    left out; the rest go by how far they move it (to SAME_PULL), then by least change
    besides (of two moving it alike, the one that does least else). A peak or dip also
    gets `levels`: ways to raise it without moving it (`level_moves`). Parts in `avoid`
    (knobs, parts that set a bias) move nothing here, sideways or up/down (D-100)."""
    b = _db(base)
    found: list[dict[str, Any]] = []
    for k in knees(freq, 10 ** (b / 20)):
        if k.simple:
            label = f"{k.side.capitalize()} knee ({KNEE_WORDS[k.side]})"
            found.append({"id": f"knee-{k.side}", "kind": "knee", "side": k.side, "f": k.f,
                          "label": label})  # fmt: skip
    peaks, dips = extrema(freq, 10 ** (b / 20))
    for kind, points in (("peak", peaks), ("dip", dips)):
        for i, e in enumerate(points):
            found.append({"id": f"{kind}-{i}", "kind": kind, "side": None, "f": e.f,
                          "label": kind.capitalize()})  # fmt: skip
    found = found[:MAX_HANDLES]
    logf = np.log10(freq)
    for handle in found:
        handle["db"] = float(np.interp(math.log10(handle["f"]), logf, b))
        handle["text"] = _hz(handle["f"])
        handle["parts"] = []
        handle["pulls"] = {}
    for ref, h in nudged.items():
        n = _db(h)
        change = float(np.max(np.minimum(np.abs(n - b), BIG_DB)))
        after_knees = {k.side: k.f for k in knees(freq, 10 ** (n / 20))}
        after_peaks, after_dips = extrema(freq, 10 ** (n / 20))
        for handle in found:
            if handle["kind"] == "knee":
                f_after = after_knees.get(handle["side"])
            else:
                moved = _nearest(after_peaks if handle["kind"] == "peak" else after_dips,
                                 handle["f"])  # fmt: skip
                f_after = moved.f if moved else None
            if f_after is None:
                continue
            exponent = _exponent(handle["f"], f_after, nudge)
            if abs(exponent) >= MOVES and ref not in avoid:
                handle["parts"].append({"ref": ref, "exponent": exponent, "change": change})
            if handle["kind"] != "knee" and ref not in avoid:
                db_after = float(np.interp(math.log10(f_after), logf, n))
                slope = (db_after - handle["db"]) / math.log1p(nudge)
                handle["pulls"][ref] = (exponent, slope, n - b)
    for handle in found:
        pulls = handle.pop("pulls")
        if handle["kind"] != "knee":
            handle["levels"] = level_moves(freq, handle["f"], pulls, nudge)
        handle["parts"].sort(
            key=lambda p: (-round(abs(p["exponent"]) / SAME_PULL), p["change"], p["ref"])
        )
    return found
