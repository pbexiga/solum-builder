"""SI values at the edges: parse `4k7`, `2M2`, `22n`, `100p`, `1µ`; format back; E-series snapping.

Internal values are SI floats (ohms, farads, volts, hertz, seconds). Strings exist only in
files and the UI. Electronics convention, not SPICE's: `M` is mega and `m` is milli.
"""

import math
import re

PREFIXES: dict[str, float] = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "U": 1e-6,
    "µ": 1e-6,  # U+00B5 micro sign
    "μ": 1e-6,  # U+03BC Greek mu
    "m": 1e-3,
    "R": 1.0,  # "4R7" = 4.7 ohms
    "r": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "meg": 1e6,
    "Meg": 1e6,
    "MEG": 1e6,
    "G": 1e9,
    "T": 1e12,
}

# Prefix letters used when formatting, by power of ten.
_FORMAT_PREFIX = {
    -15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T",
}  # fmt: skip

_VALUE = re.compile(
    r"""
    (?P<num>[+-]?(?:\d+(?P<point>\.\d*)?|\.\d+)(?P<exp>[eE][+-]?\d+)?)
    (?P<prefix>meg|Meg|MEG|[fpnuUµμmRrkKMGT])?
    (?P<frac>\d+)?
    (?P<unit>F|f|Ω|[oO]hms?|H|V|A|Hz|s)?
    """,
    re.X,
)

E_SERIES: dict[str, tuple[float, ...]] = {
    "E6": (1.0, 1.5, 2.2, 3.3, 4.7, 6.8),
    "E12": (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2),
    "E24": (
        1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
    ),
    # 1 % resistors (IEC 60063): round(10 ** (i / 96), 2), with no exceptions (a test checks)
    "E96": (
        1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30,
        1.33, 1.37, 1.40, 1.43, 1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74,
        1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
        2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09,
        3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
        4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
        5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32,
        7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76,
    ),
    # Not an IEC series: the values pots and trimmers are sold in (1k, 2k, 5k, 10k, 20k,
    # 25k, 50k, 100k, 250k, 500k, 1M); pot value sliders step through it.
    "pot": (1.0, 2.0, 2.5, 5.0),
}  # fmt: skip


UNIT_NAMES = {"F": "farads (F)", "Ω": "ohms (Ω)", "H": "henries (H)", "V": "volts (V)",
              "A": "amps (A)", "Hz": "hertz (Hz)", "s": "seconds (s)"}  # fmt: skip


def parse_value(value: str | float, unit: str | None = None) -> float:
    """SI float from a part value: `"4k7"` → 4700.0, `"22nF"` → 2.2e-08, `1e3` → 1000.0.

    With `unit` (a key of UNIT_NAMES), a unit written after the value must be that one
    (D-164): `"4k7F"` isn't a resistor's value. Raises ValueError with a plain-English
    message for anything else.
    """
    if isinstance(value, bool):
        raise ValueError(f"{value!r} isn't a value. Use a number like 4k7, 22n or 100.")
    number = float(value) if isinstance(value, int | float) else _parse_text(value, unit)
    if not math.isfinite(number):
        raise ValueError(f"{value!r} isn't a finite value.")
    return number


def _parse_text(text: str, unit: str | None = None) -> float:
    cleaned = re.sub(r"(?<=[\d.])\s+(?=\D)", "", text.strip())  # "4.7 kΩ" is fine
    match = _VALUE.fullmatch(cleaned)
    if not cleaned or match is None:
        raise ValueError(
            f"Couldn't read the value {text!r}. Write it like 4k7, 2M2, 22n, 100p, 1µ or 0.047u."
        )
    prefix, frac = match["prefix"], match["frac"]
    if frac and (match["point"] or match["exp"]):
        raise ValueError(f"{text!r} mixes styles: write 4k7 or 4.7k, not 4.7k7.")
    if prefix and match["exp"]:
        raise ValueError(f"{text!r} has both an exponent and a prefix; use one.")
    written = match["unit"]
    if written and written.lower().startswith("ohm"):
        written = "Ω"
    elif written == "f":  # 10uf, 100pf: farads after a prefix (a bare 10f is femto)
        written = "F"
    if unit and written and written != unit:
        raise ValueError(
            f"{text!r} is in {UNIT_NAMES[written]}, but this value is in {UNIT_NAMES[unit]}. "
            "Leave the unit off (22n, 4k7) or write this one."
        )
    mantissa = match["num"] + (f".{frac}" if frac else "")
    return float(mantissa) * PREFIXES.get(prefix or "", 1.0)


def format_value(value: float, digits: int = 3) -> str:
    """Short display form: 4700 → `4k7`, 2.2e-8 → `22n`, 1e6 → `1M`, 4.5 → `4.5`.

    Rounds to `digits` significant figures. `parse_value(format_value(x))` returns x
    whenever x has at most `digits` significant figures.
    """
    split = _split(value, digits)
    if isinstance(split, str):
        return split
    sign, whole, frac, prefix = split
    if not frac:
        return f"{sign}{whole}{prefix}"
    if prefix:
        return f"{sign}{whole}{prefix}{frac}"
    return f"{sign}{whole}.{frac}"


def format_quantity(value: float, unit: str, digits: int = 3) -> str:
    """A measured quantity for display: 0.0012, "A" → `1.2 mA`; 4.5, "V" → `4.5 V`.

    Same rounding and prefixes as `format_value`, written the way meters show it.
    """
    split = _split(value, digits)
    if isinstance(split, str):
        return f"{split} {unit}"
    sign, whole, frac, prefix = split
    return f"{sign}{whole}{'.' + frac if frac else ''} {prefix}{unit}"


def signed_db(db: float) -> str:
    """A change in dB to one decimal, signed, its minus U+2212: "+3.1 dB"; under 0.05 dB
    either way is "+0.0 dB"."""
    return f"{0.0 if abs(db) < 0.05 else db:+.1f} dB".replace("-", "\u2212")


def _split(value: float, digits: int) -> tuple[str, str, str, str] | str:
    """(sign, whole digits, fraction digits, prefix), or a finished string for 0 and
    values outside the prefix range (plain scientific notation)."""
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    rounded = float(f"{magnitude:.{digits - 1}e}")
    power = min(max(math.floor(math.log10(rounded) / 3) * 3, -15), 12)
    mantissa = rounded / 10.0**power
    text = f"{mantissa:.{digits}g}"
    if "e" in text:
        return f"{sign}{rounded:.{digits - 1}e}".replace("e+0", "e").replace("e-0", "e-")
    whole, _, frac = text.partition(".")
    return sign, whole, frac, _FORMAT_PREFIX[power]


def snap_to_series(value: float, series: str = "E12") -> float:
    """Nearest standard value (by ratio) in an E-series: 5000 → 4700.0 in E12."""
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"Only positive values can be snapped to {series} (got {value!r}).")
    try:
        bases = E_SERIES[series]
    except KeyError:
        raise ValueError(f"Unknown series {series!r}; use one of {', '.join(E_SERIES)}.") from None
    decade = math.floor(math.log10(value))
    candidates = [float(f"{b}e{decade}") for b in bases] + [float(f"1e{decade + 1}")]
    return min(candidates, key=lambda c: abs(math.log(c / value)))


def series_values(low: float, high: float, series: str = "E12") -> list[float]:
    """Every value of an E-series from `low` to `high` inclusive, ascending:
    (1000, 2200, "E6") → [1000.0, 1500.0, 2200.0]. A value slider's steps."""
    if not 0 < low <= high or not math.isfinite(high):
        raise ValueError(f"A range of values needs 0 < low <= high (got {low!r}, {high!r}).")
    try:
        bases = E_SERIES[series]
    except KeyError:
        raise ValueError(f"Unknown series {series!r}; use one of {', '.join(E_SERIES)}.") from None
    out = []
    for decade in range(math.floor(math.log10(low)), math.floor(math.log10(high)) + 1):
        for b in bases:
            v = float(f"{b}e{decade}")
            if low * (1 - 1e-9) <= v <= high * (1 + 1e-9):
                out.append(v)
    return out


_SPICE_SCALE = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "mil": 25.4e-6,
    "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
}  # fmt: skip
_SPICE_NUMBER = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpf])?[a-z]*")


def parse_spice_number(text: str) -> float:
    """A number as SPICE reads it: case-insensitive, `M` is milli, `MEG` is mega.

    Only for model cards and ngspice output. Part values use `parse_value`.
    """
    match = _SPICE_NUMBER.fullmatch(text.strip().lower())
    if match is None:
        raise ValueError(f"{text!r} isn't a SPICE number.")
    return float(match[1]) * _SPICE_SCALE.get(match[2] or "", 1.0)
