"""Tools → Filter calculator (D-319): a resistor and a capacitor as a one-pole filter. Its
corner worked from the parts, the sum written out, how far it turns a guitar's lowest note,
1 kHz and 5 kHz down, and what that means in words. Pure; values parsed by `units`.
"""

import math
from typing import Any, Literal

from solum.units import format_quantity, format_value, parse_value

Kind = Literal["high", "low"]
KINDS: dict[str, str] = {
    "high": "High-pass (bass cut): the capacitor in the signal's path, the resistor to ground",
    "low": "Low-pass (treble cut): the resistor in the signal's path, the capacitor to ground",
}
LOW_E_HZ = 82.0  # a guitar's lowest note (the guide's Formulas page)
SPEAKER_HZ = 5000.0  # a guitar speaker falls off above about 5 kHz (the guide's Audio page)
LEVEL_HZ = (LOW_E_HZ, 1000.0, SPEAKER_HZ)
CLEAR = 4.0  # a corner this many times outside the guitar's range costs under 0.3 dB at its edge


class FilterError(ValueError):
    """A value the calculator can't use (plain-English message)."""


def corner_hz(ohms: float, farads: float) -> float:
    """A one-pole RC filter's corner, where it is 3 dB down: 1 / (2πRC)."""
    return 1.0 / (2.0 * math.pi * ohms * farads)


def level_db(kind: Kind, corner: float, freq: float) -> float:
    """How far a one-pole filter with this corner turns `freq` down, in dB (0 or below)."""
    ratio = freq / corner if kind == "high" else corner / freq
    return 20.0 * math.log10(ratio / math.hypot(1.0, ratio))


def _level(db: float) -> str:
    """A level against the untouched signal: "0.0 dB", "\u22123.0 dB" (never above 0)."""
    return "0.0 dB" if db > -0.05 else f"\u2212{-db:.1f} dB"


def effect(kind: Kind, corner: float) -> str:
    """What a filter with this corner does to a guitar's signal, in a sentence."""
    at = format_quantity(corner, "Hz")
    low, top = format_quantity(LOW_E_HZ, "Hz"), format_quantity(SPEAKER_HZ, "Hz")
    if kind == "high":
        if corner <= LOW_E_HZ / CLEAR:
            return f"Far below a guitar's lowest note ({low}): the whole guitar passes."
        if corner <= LOW_E_HZ:
            lost = -level_db(kind, corner, LOW_E_HZ)
            return (
                f"Just under a guitar's lowest note ({low}): the lowest notes are down "
                f"{lost:.1f} dB."
            )
        if corner <= SPEAKER_HZ:
            return (
                f"Cuts bass: everything below about {at} is turned down, 6 dB more each "
                "time the frequency halves."
            )
        return f"Above what a guitar speaker puts out (about {top}): nearly all of it is cut."
    if corner >= SPEAKER_HZ * CLEAR:
        return f"Far above what a guitar speaker puts out (about {top}): nothing you'd hear is cut."
    if corner >= SPEAKER_HZ:
        lost = -level_db(kind, corner, SPEAKER_HZ)
        return (
            f"Just above what a guitar speaker puts out (about {top}): the top is down "
            f"{lost:.1f} dB."
        )
    if corner >= LOW_E_HZ:
        return (
            f"Cuts treble: everything above about {at} is turned down, 6 dB more each "
            "time the frequency doubles."
        )
    return f"Below a guitar's lowest note ({low}): nearly all of it is cut."


def _filter(kind: Kind, ohms: float, farads: float) -> dict[str, Any]:
    corner = corner_hz(ohms, farads)
    r, c = format_quantity(ohms, "Ω"), format_quantity(farads, "F")
    return {
        "r": format_value(ohms, 4),
        "c": format_value(farads, 4),
        "corner": corner,
        "corner_text": format_quantity(corner, "Hz"),
        "working": f"1 / (2 × π × {r} × {c}) = {format_quantity(corner, 'Hz')}",
        "levels": [
            {"freq": format_quantity(f, "Hz"), "db": _level(level_db(kind, corner, f))}
            for f in LEVEL_HZ
        ],
        "effect": effect(kind, corner),
    }


def _moved(first: dict[str, Any], second: dict[str, Any]) -> str:
    """What changing the parts did to the corner, in a sentence."""
    ratio = second["corner"] / first["corner"]
    if abs(ratio - 1.0) < 1e-9:
        return "The same corner: R × C hasn't changed."
    times = f"{max(ratio, 1 / ratio):.3g}"
    way = "higher" if ratio > 1 else "lower"
    return (
        f"The corner moves {times} times {way}, from {first['corner_text']} to "
        f"{second['corner_text']}: a bigger R or C lowers it, a smaller one raises it."
    )


def _read(text: str, unit: str, name: str) -> float:
    try:
        value = parse_value(text, unit)
    except ValueError as err:
        raise FilterError(str(err)) from None
    if value <= 0 or not math.isfinite(value):
        raise FilterError(f"The {name} must be above 0.")
    return value


def filter_view(kind: str, r: str, c: str, r2: str = "", c2: str = "") -> dict[str, Any]:
    """The calculator's answer: the filter from `r` and `c` as typed (`100k`, `1u`), and,
    when `r2` or `c2` is given, a second one to compare (a blank one keeps the first's)
    with what the change did. Each: its corner, the sum written out, its level at
    `LEVEL_HZ` and its `effect`."""
    if kind not in KINDS:
        raise FilterError("Choose high-pass or low-pass.")
    which: Kind = "high" if kind == "high" else "low"
    ohms, farads = _read(r, "Ω", "resistor"), _read(c, "F", "capacitor")
    filters = [_filter(which, ohms, farads)]
    if r2.strip() or c2.strip():
        other_r = _read(r2, "Ω", "resistor") if r2.strip() else ohms
        other_c = _read(c2, "F", "capacitor") if c2.strip() else farads
        filters.append(_filter(which, other_r, other_c))
    view: dict[str, Any] = {"kind": which, "formula": "f = 1 / (2 × π × R × C)", "filters": filters}
    if len(filters) == 2:
        view["change"] = _moved(filters[0], filters[1])
    return view
