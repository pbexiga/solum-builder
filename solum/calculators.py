"""Tools → Calculators… (D-319, D-320): the sums a builder does by hand, worked out with
the numbers shown. Pure; values parsed and written by `units`.

- An RC filter's corner from its parts (`filter_view`), and a part from the corner
  (`filter_part_view`).
- A voltage divider, and how far a load pulls its middle down (`divider_view`).
- Resistors or capacitors in series and in parallel, and the standard pair that makes a
  value (`combine_view`).
- Decibels and voltage ratios (`db_view`).
"""

import math
from typing import Any, Literal

from solum.units import (
    format_quantity,
    format_value,
    parse_value,
    series_values,
    signed_db,
    snap_to_series,
)

Kind = Literal["high", "low"]
OHM = "\u03a9"
KINDS: dict[str, str] = {
    "high": "High-pass (bass cut): the capacitor in the signal's path, the resistor to ground",
    "low": "Low-pass (treble cut): the resistor in the signal's path, the capacitor to ground",
}
LOW_E_HZ = 82.0  # a guitar's lowest note (the guide's Formulas page)
SPEAKER_HZ = 5000.0  # a guitar speaker falls off above about 5 kHz (the guide's Audio page)
LEVEL_HZ = (LOW_E_HZ, 1000.0, SPEAKER_HZ)
CLEAR = 4.0  # a corner this many times outside the guitar's range costs under 0.3 dB at its edge


class FilterError(ValueError):
    """A value a calculator can't use (plain-English message)."""


SERIES_CHOICES: dict[str, str] = {
    "E12": "E12 (the usual kit values)",
    "E24": "E24 (5 % resistors)",
    "E6": "E6 (most capacitors)",
}


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


def _series(series: str) -> str:
    if series not in SERIES_CHOICES:
        raise FilterError(f"Choose one of {', '.join(SERIES_CHOICES)}.")
    return series


def _off(got: float, wanted: float) -> str:
    """How far a standard value lands from the one asked for: "+2.1 %", "0 %"."""
    pct = (got / wanted - 1.0) * 100.0
    return "0 %" if abs(pct) < 0.05 else f"{pct:+.1f} %".replace("-", "\u2212")


# ---- a filter's part from its corner ---------------------------------------------------

FIND_C = "C = 1 / (2 \u00d7 \u03c0 \u00d7 f \u00d7 R)"
FIND_R = "R = 1 / (2 \u00d7 \u03c0 \u00d7 f \u00d7 C)"


def filter_part_view(
    kind: str, freq: str, r: str = "", c: str = "", series: str = "E12"
) -> dict[str, Any]:
    """The other part of an RC filter with corner `freq`, given one of `r` or `c`: its exact
    value, the nearest standard one in `series`, and the filter that one makes (as
    `filter_view` gives it, so its corner, levels and effect)."""
    if kind not in KINDS:
        raise FilterError("Choose high-pass or low-pass.")
    which: Kind = "high" if kind == "high" else "low"
    corner = _read(freq, "Hz", "corner frequency")
    if bool(r.strip()) == bool(c.strip()):
        raise FilterError(
            "Give the resistor or the capacitor, and leave the other blank to find it."
        )
    series = _series(series)
    if r.strip():
        ohms = _read(r, OHM, "resistor")
        exact, unit, name = 1.0 / (2.0 * math.pi * corner * ohms), "F", "capacitor"
        standard = snap_to_series(exact, series)
        made = _filter(which, ohms, standard)
    else:
        farads = _read(c, "F", "capacitor")
        exact, unit, name = 1.0 / (2.0 * math.pi * corner * farads), OHM, "resistor"
        standard = snap_to_series(exact, series)
        made = _filter(which, standard, farads)
    return {
        "kind": which,
        "find": name,
        "formula": FIND_C if unit == "F" else FIND_R,
        "exact": format_quantity(exact, unit),
        "standard": format_value(standard, 4),
        "series": series,
        "corner_off": _off(made["corner"], corner),
        "filter": made,
    }


# ---- voltage divider -------------------------------------------------------------------


def _parallel(*values: float) -> float:
    return 1.0 / sum(1.0 / v for v in values)


def divider_view(supply: str, r1: str, r2: str, load: str = "") -> dict[str, Any]:
    """A divider from `supply` through `r1` (top) and `r2` (to ground): the middle's voltage,
    the current it draws, what it looks like to what it feeds (R1 ‖ R2), and with a `load`
    from the middle to ground, how far that pulls the middle down."""
    volts = _read(supply, "V", "supply")
    top, bottom = _read(r1, OHM, "top resistor"), _read(r2, OHM, "bottom resistor")
    middle = volts * bottom / (top + bottom)
    source = _parallel(top, bottom)
    view: dict[str, Any] = {
        "middle": format_quantity(middle, "V"),
        "working": (
            f"{format_quantity(volts, 'V')} \u00d7 {format_quantity(bottom, OHM)} / "
            f"({format_quantity(top, OHM)} + {format_quantity(bottom, OHM)}) = "
            f"{format_quantity(middle, 'V')}"
        ),
        "current": format_quantity(volts / (top + bottom), "A"),
        "source": format_quantity(source, OHM),
        # a load 99 times R1 ‖ R2 pulls the middle down 1 %
        "holds": (
            f"It holds within 1 % for anything above {format_quantity(99 * source, OHM)} "
            f"on its middle, and 10 % above {format_quantity(9 * source, OHM)}."
        ),
    }
    if load.strip():
        loaded_r = _read(load, OHM, "load")
        loaded = volts * _parallel(bottom, loaded_r) / (top + _parallel(bottom, loaded_r))
        sag = (1.0 - loaded / middle) * 100.0
        view["loaded"] = format_quantity(loaded, "V")
        view["sag"] = (
            f"The load pulls the middle down {sag:.1f} %, from {format_quantity(middle, 'V')} "
            f"to {format_quantity(loaded, 'V')}."
        )
    return view


# ---- parallel and series ---------------------------------------------------------------

PART_UNITS = {"resistor": OHM, "capacitor": "F"}
COMBINE_MAX = 6
PAIR_SPAN = 1000.0  # a pair's smaller part may be this many times smaller than the value


def _values(text: str, unit: str, name: str) -> list[float]:
    items = [t for t in (x.strip() for x in text.replace(";", ",").split(",")) if t]
    if len(items) > COMBINE_MAX:
        raise FilterError(f"Combine at most {COMBINE_MAX} at once (got {len(items)}).")
    return [_read(t, unit, name) for t in items]


def _pair(target: float, add: bool, series: str) -> tuple[float, float, float]:
    """The two standard values whose sum (`add`) or reciprocal sum makes `target` most
    nearly: (a, b, what they make), a ≥ b for a sum, a ≤ b otherwise."""
    if add:  # both parts below the value
        steps = series_values(target / PAIR_SPAN, target, series)
        made = ((a, b, a + b) for a in steps for b in steps if b <= a)
    else:  # both above it
        steps = series_values(target, target * PAIR_SPAN, series)
        made = ((a, b, _parallel(a, b)) for a in steps for b in steps if b >= a)
    return min(made, key=lambda m: abs(math.log(m[2] / target)))


def combine_view(
    kind: str, values: str = "", target: str = "", series: str = "E12"
) -> dict[str, Any]:
    """Resistors or capacitors (`kind`) combined: the `values` listed (`10k, 22k`) in series
    and in parallel; and the value `target` made from standard parts of `series`: the
    nearest single value and the nearest pair each way, with how far each lands from it."""
    if kind not in PART_UNITS:
        raise FilterError("Choose resistors or capacitors.")
    unit, name = PART_UNITS[kind], kind
    resistor = kind == "resistor"
    view: dict[str, Any] = {"kind": kind}
    parts = _values(values, unit, name) if values.strip() else []
    if parts:
        listed = ", ".join(format_value(v, 4) for v in parts)
        added, reciprocal = sum(parts), _parallel(*parts)
        view["totals"] = {
            "listed": listed,
            # resistors add in series, capacitors in parallel
            "series": format_quantity(added if resistor else reciprocal, unit),
            "parallel": format_quantity(reciprocal if resistor else added, unit),
        }
    if target.strip():
        want = _read(target, unit, "value")
        series = _series(series)
        single = snap_to_series(want, series)
        options = [
            {
                "how": f"one {format_value(single, 4)}",
                "makes": format_quantity(single, unit),
                "off": _off(single, want),
            }
        ]
        for add in (True, False):
            a, b, made = _pair(want, add, series)
            together = "in series" if add == resistor else "in parallel"
            options.append(
                {
                    "how": f"{format_value(a, 4)} and {format_value(b, 4)} {together}",
                    "makes": format_quantity(made, unit),
                    "off": _off(made, want),
                }
            )
        view["make"] = {"value": format_quantity(want, unit), "series": series, "options": options}
    if not parts and not target.strip():
        raise FilterError(f"List some {name} values to combine, or a value to make.")
    return view


# ---- decibels --------------------------------------------------------------------------


def _number(text: str, strip: str, name: str) -> float:
    cleaned = text.strip().removesuffix(strip).strip().replace("\u2212", "-")
    try:
        value = float(cleaned)
    except ValueError:
        raise FilterError(
            f"Couldn't read {text.strip()!r} as {name}: type a number, like 6 or -3.5."
        ) from None
    if not math.isfinite(value):
        raise FilterError(f"{name.capitalize()} must be a finite number.")
    return value


def db_view(db: str = "", times: str = "", volts: str = "") -> dict[str, Any]:
    """Decibels and voltage ratios, either way: `db` (`+22`, `-6 dB`) or `times` (`12.6`,
    `0.5x`), and with a signal of `volts` in, what comes out."""
    if bool(db.strip()) == bool(times.strip()):
        raise FilterError("Give a level in dB or a ratio in times, not both.")
    if db.strip():
        level = _number(db.lower(), "db", "decibels")
        ratio = 10.0 ** (level / 20.0)
    else:
        ratio = _number(times.lower().replace("\u00d7", ""), "x", "a ratio")
        if ratio <= 0:
            raise FilterError("A ratio must be above 0 (0.5 is half, 2 is twice).")
        level = 20.0 * math.log10(ratio)
    view: dict[str, Any] = {
        "db": signed_db(level),
        "times": f"{ratio:.3g}",
        "working": f"20 \u00d7 log10({ratio:.3g}) = {signed_db(level)}",
    }
    if volts.strip():
        given = _read(volts, "V", "signal")
        view["out"] = f"{format_quantity(given, 'V')} in, {format_quantity(given * ratio, 'V')} out"
    return view
