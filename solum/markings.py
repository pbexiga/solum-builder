"""What's printed on parts, and a value in every unit (Tools menu, D-095): resistor colour
bands (IEC 60062), capacitor codes (`223` = 22 nF), standard E-series values, and the
unit converter's rows. Values are SI floats; text parsing goes through `solum.units`."""

import math
from dataclasses import dataclass
from decimal import Decimal

from solum.units import E_SERIES, format_value, parse_value

COLOURS = ("black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "grey", "white")
MULTIPLIERS: dict[str, int] = {**{c: i for i, c in enumerate(COLOURS)}, "gold": -1, "silver": -2}
TOLERANCES: dict[str, float] = {
    "brown": 1.0, "red": 2.0, "green": 0.5, "blue": 0.25, "violet": 0.1, "grey": 0.05,
    "gold": 5.0, "silver": 10.0, "none": 20.0,
}  # fmt: skip
# A resistor's tolerance letter (IEC 60062), as printed beside the value: 4k7J is ±5 %.
# Grey's ±0.05 % has none on the usual charts, so none here.
RESISTOR_LETTERS: dict[float, str] = {
    0.1: "B", 0.25: "C", 0.5: "D", 1.0: "F", 2.0: "G", 5.0: "J", 10.0: "K", 20.0: "M",
}  # fmt: skip
# The help chart's two example resistors, as on the common colour-code card
EXAMPLE_BANDS = (("green", "blue", "yellow", "gold"), ("red", "orange", "violet", "black", "brown"))
# Series by tolerance: what a resistor of that tolerance is usually sold in
SERIES_TOLERANCE = {"E6": 20.0, "E12": 10.0, "E24": 5.0, "E96": 1.0}

# Capacitor code letters (EIA): tolerance in %, or in pF for the small-value ones
CAP_TOLERANCE: dict[str, str] = {
    "B": "±0.1 pF", "C": "±0.25 pF", "D": "±0.5 pF", "F": "±1 %", "G": "±2 %",
    "J": "±5 %", "K": "±10 %", "M": "±20 %", "Z": "+80 % / \u221220 %",
}  # fmt: skip

# The unit converter's quantities: symbol, name, the prefixes it lists, and example
# values for the input's placeholder (each one parses, tested)
QUANTITIES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "F": ("Capacitance", ("p", "n", "µ", ""), "22n, 0.022u, 22000p"),
    "Ω": ("Resistance", ("", "k", "M"), "4k7, 4700, 2M2"),
    "H": ("Inductance", ("µ", "m", ""), "100m, 470u, 1.5"),
    "Hz": ("Frequency", ("", "k", "M"), "720, 1k, 3k2"),
    "V": ("Voltage", ("m", ""), "9, 4.5, 600m"),
    "A": ("Current", ("µ", "m", ""), "2m, 1.97m, 500u"),
    "s": ("Time", ("µ", "m", ""), "10m, 50u, 0.5"),
}
_SCALE = {"p": 1e-12, "n": 1e-9, "µ": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6}


class MarkingError(ValueError):
    """A value or marking that can't be read or shown (plain-English message)."""


def _digits(value: float, n: int) -> tuple[str, int] | None:
    """`value` as `n` significant digits and a power of ten (4700, 2 → ("47", 2)), or
    None when it needs more digits than that."""
    if value <= 0 or not math.isfinite(value):
        return None
    power = math.floor(math.log10(value)) - (n - 1)
    mantissa = value / 10.0**power
    rounded = round(mantissa)
    if rounded >= 10**n:  # 9.995 rounding up to 10.0
        rounded, power = rounded // 10, power + 1
    if abs(mantissa - rounded) > 1e-6 * mantissa:
        return None
    return str(rounded), power


def resistor_bands(ohms: float, bands: int = 4) -> list[str] | None:
    """The colours of a resistor's value bands and multiplier, without the tolerance band:
    4700, 4 → [yellow, violet, red]; 4120, 5 → [yellow, brown, red, brown]. None when the
    value needs more significant digits than the bands have, or is out of the code's range."""
    if bands not in (4, 5):
        raise MarkingError("A resistor colour code has 4 or 5 bands.")
    found = _digits(ohms, bands - 2)
    if found is None or found[1] not in MULTIPLIERS.values():
        return None
    digits, power = found
    by_power = {p: c for c, p in MULTIPLIERS.items()}
    return [COLOURS[int(d)] for d in digits] + [by_power[power]]


def bands_value(colours: list[str]) -> tuple[float, float]:
    """(ohms, tolerance %) from bands read left to right: digits (2 or 3), multiplier,
    then a tolerance band (or none, ±20 %). A 6th band (temperature) is ignored."""
    spelling = {"gray": "grey", "purple": "violet"}
    colours = [spelling.get(c.strip().lower(), c.strip().lower()) for c in colours]
    if len(colours) == 6:
        colours = colours[:5]
    if len(colours) not in (3, 4, 5):
        raise MarkingError("Read 3 to 6 bands: two or three digits, a multiplier, then tolerance.")
    n = 3 if len(colours) == 5 else 2
    digits, multiplier, rest = colours[:n], colours[n], colours[n + 1 :]
    for c in digits:
        if c not in COLOURS:
            raise MarkingError(f"{c} can't be a digit band: digits are black to white.")
    if multiplier not in MULTIPLIERS:
        raise MarkingError(f"{multiplier} can't be a multiplier band.")
    tolerance = rest[0] if rest else "none"
    if tolerance not in TOLERANCES:
        raise MarkingError(f"{tolerance} isn't a tolerance colour.")
    number = int("".join(str(COLOURS.index(c)) for c in digits))
    ohms = float(Decimal(number).scaleb(MULTIPLIERS[multiplier]))
    return ohms, TOLERANCES[tolerance]


def in_series(value: float) -> list[str]:
    """The E-series (E6, E12, E24, E96) that have `value` as a standard value."""
    found = _digits(value, 3)
    if found is None:
        return []
    mantissa = int(found[0]) / 100
    return [s for s in SERIES_TOLERANCE if any(abs(b - mantissa) < 1e-9 for b in E_SERIES[s])]


def neighbours(value: float, series: str) -> tuple[float, float]:
    """The standard values of `series` just below and just above `value` (equal to it at
    both ends when it is one)."""
    if value <= 0 or not math.isfinite(value):
        raise MarkingError("Only positive values have standard neighbours.")
    decade = math.floor(math.log10(value))
    steps = [float(f"{b}e{d}") for d in (decade - 1, decade, decade + 1) for b in E_SERIES[series]]
    below = max(s for s in steps if s <= value * (1 + 1e-9))
    above = min(s for s in steps if s >= value * (1 - 1e-9))
    return below, above


def cap_code(farads: float) -> str | None:
    """The 3-digit code printed on small capacitors: 22 nF → `223`, 100 nF → `104`,
    47 pF → `470`. Below 10 pF it's written with a p (`4p7`). None when the value needs
    three significant digits or is outside the code's range (up to 99 µF)."""
    pf = farads / 1e-12
    if pf <= 0 or not math.isfinite(pf):
        return None
    if pf < 10:
        return format_value(farads, 2)
    found = _digits(pf, 2)
    if found is None:
        return None
    digits, power = found
    return f"{digits}{power}" if 0 <= power <= 6 else None


@dataclass(frozen=True)
class CapCode:
    farads: float
    tolerance: str | None  # "±10 %" for a K, None when there's no letter


def read_cap_code(code: str) -> CapCode:
    """A capacitor's printed code: `104` → 100 nF, `223J` → 22 nF ±5 %, `47` → 47 pF,
    `4p7` → 4.7 pF. A third digit of 8 or 9 means times 0.01 or 0.1 (rare, small values)."""
    text = code.strip().upper().replace(" ", "")
    letter = text[-1] if text and text[-1] in CAP_TOLERANCE else None
    body = text[:-1] if letter else text
    if body.isdigit() and len(body) == 3:
        third = int(body[2])
        if third == 7:
            raise MarkingError(f"{code!r}: a third digit of 7 isn't used in capacitor codes.")
        power = {8: -2, 9: -1}.get(third, third)
        pf = int(body[:2]) * 10.0**power
    elif body.isdigit() and len(body) in (1, 2):
        pf = float(body)  # a plain number on a capacitor is picofarads
    elif "P" in body:
        pf = parse_value(body.lower()) / 1e-12
    else:
        raise MarkingError(
            f"Couldn't read the code {code!r}. Capacitor codes look like 104, 223J, 47 or 4p7."
        )
    return CapCode(pf * 1e-12, CAP_TOLERANCE[letter] if letter else None)


def plain(number: float, digits: int = 4) -> str:
    """A number in plain decimal (no exponent), rounded to `digits` significant figures,
    with spaces between thousands: 22000 → `22 000`, 0.022 → `0.022`."""
    if number == 0:
        return "0"
    rounded = Decimal(f"{number:.{digits - 1}e}")
    text = format(rounded.normalize(), "f")
    whole, _, frac = text.partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    whole = " ".join([whole, *groups]) if groups else whole
    return f"{sign}{whole}.{frac}" if frac else f"{sign}{whole}"


def conversions(value: float, unit: str) -> list[tuple[str, str]]:
    """The converter's rows: `value` in each unit its quantity lists, as (unit, number):
    22e-9, "F" → [("pF", "22 000"), ("nF", "22"), ("µF", "0.022"), ("F", "0.000000022")]."""
    if unit not in QUANTITIES:
        raise MarkingError(f"No converter for {unit!r}; use one of {', '.join(QUANTITIES)}.")
    return [(f"{prefix}{unit}", plain(value / _SCALE[prefix], 6)) for prefix in QUANTITIES[unit][1]]


def value_view(value: float, unit: str) -> dict[str, object]:
    """The unit converter's answer: the value short (`22n`), in each unit, and for a
    capacitance its printed code; for capacitance and resistance, the E-series it's in."""
    view: dict[str, object] = {
        "value": value,
        "short": format_value(value, 4),
        "rows": [{"unit": u, "number": n} for u, n in conversions(value, unit)],
    }
    if unit == "F":
        view["code"] = cap_code(value)
    if unit in ("F", "Ω"):
        view["series"] = in_series(value)
    return view


def resistor_view(ohms: float, tolerance: float | None = None) -> dict[str, object]:
    """The colour-code tool's answer: the value, its 4- and 5-band colours (None when it
    can't be shown with that many), the E-series that have it, and when none do, the
    standard values either side in E24 (5 %) and E96 (1 %)."""
    if ohms <= 0 or not math.isfinite(ohms):
        raise MarkingError("A resistor's value must be above 0 Ω.")
    series = in_series(ohms)
    nearest = [
        {"series": s, "tolerance": SERIES_TOLERANCE[s],
         "below": format_value(lo, 3), "above": format_value(hi, 3)}
        for s in ("E24", "E96")
        for lo, hi in [neighbours(ohms, s)]
    ] if not series else []  # fmt: skip
    return {
        "ohms": ohms,
        "short": format_value(ohms, 4),
        "tolerance": tolerance,
        "bands4": resistor_bands(ohms, 4),
        "bands5": resistor_bands(ohms, 5),
        "series": series,
        "nearest": nearest,
    }


def _times(power: int) -> str:
    """A multiplier band as written: times 1k for a power of 3, times 0.1 for -1."""
    return "\u00d7" + (format_value(10.0**power) if power >= 0 else plain(10.0**power))


def tables() -> dict[str, object]:
    """What the Tools and Help pages build from: the colour code (digit, multiplier as a
    power of ten, tolerance % and its letter), two example resistors read out, and the
    converter's quantities with example values."""
    names = [*COLOURS, "gold", "silver"]
    examples = []
    for bands in EXAMPLE_BANDS:
        ohms, tolerance = bands_value(list(bands))
        short = format_value(ohms, 4)
        examples.append({"bands": list(bands), "short": short, "tolerance": tolerance})
    return {
        "colours": [
            {"name": c, "digit": COLOURS.index(c) if c in COLOURS else None,
             "power": MULTIPLIERS[c], "times": _times(MULTIPLIERS[c]),
             "tolerance": TOLERANCES.get(c),
             "letter": RESISTOR_LETTERS.get(TOLERANCES.get(c, -1.0))}
            for c in names
        ],
        "examples": examples,
        "quantities": [{"unit": u, "name": n, "example": f"e.g. {e}"}
                       for u, (n, _, e) in QUANTITIES.items()],
    }  # fmt: skip
