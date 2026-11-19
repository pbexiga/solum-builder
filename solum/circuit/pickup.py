"""A pickup by any three of its coil R, L, C, unloaded peak and Q (D-363).

The model is a series R-L with the winding's C across it. To the usual approximation
(good while Q is above about 2): peak = 1 / (2π·√(LC)) and Q = 2π·peak·L / R. Three
unknowns and two relations, so any three of the five fix the other two, except L, C and
peak (L and C already give the peak, so R is left open).

`pickup_form` is what the guitar's form shows as you type (one owner: the browser doesn't
repeat it): which three are set, the other two worked out, which box can't complete it and
why, and the line under the boxes.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from solum.units import format_value, parse_value

Quantity = Literal["r", "l", "c", "peak", "q"]
QUANTITIES: Final[tuple[str, ...]] = ("r", "l", "c", "peak", "q")
NAMES: Final[dict[str, str]] = {"r": "R", "l": "L", "c": "C", "peak": "peak", "q": "Q"}
UNITS: Final[dict[str, str | None]] = {"r": "Ω", "l": "H", "c": "F", "peak": "Hz", "q": None}
REFUSED: Final = frozenset({"l", "c", "peak"})  # L and C already give the peak
PEAK_MAX: Final = 30e3  # Hz: a pickup's unloaded peak is a few kHz
Q_MIN: Final = 0.5  # below it the coil has no peak at all
Q_MAX: Final = 200.0
EASIEST: Final = "R is the easiest: a multimeter across the jack."


class PickupError(ValueError):
    """A pickup's values that can't be used, said in plain English."""


def _the(name: str) -> str:
    """The quantity as a sentence names it: "the peak", but "L"."""
    return f"the {NAMES[name]}" if name == "peak" else NAMES[name]


def _joined(names: Sequence[str], last: str = "and") -> str:
    words = [NAMES[n] for n in names]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} {last} {words[-1]}"


def value_of(name: str, text: str | float) -> float:
    """One box's value as an SI float, checked: positive, a peak up to 30 kHz, a Q from
    0.5 to 200. Raises PickupError saying what to type."""
    if name not in QUANTITIES:
        raise PickupError(f"A pickup has no {name!r}: give its R, L, C, peak or Q.")
    try:
        x = parse_value(text, UNITS[name])
    except ValueError as err:
        raise PickupError(f"{NAMES[name]}: {err}") from None
    if x <= 0:
        raise PickupError(f"{NAMES[name]} must be greater than zero.")
    if name == "peak" and x > PEAK_MAX:
        raise PickupError(
            "The peak goes up to 30 kHz: a pickup's unloaded peak is a few kHz (like 5k2)."
        )
    if name == "q" and not Q_MIN <= x <= Q_MAX:
        raise PickupError(
            "Q goes from 0.5 to 200: below 0.5 a pickup has no peak (published ones are 1 to 30)."
        )
    return x


def solve(given: Mapping[str, float]) -> dict[str, float]:
    """All five from any valid three (SI floats; peak in Hz). Raises PickupError for
    fewer or more than three, or L, C and peak together."""
    names = set(given)
    if len(names) != 3 or not names <= set(QUANTITIES):
        raise PickupError("Give any three of the pickup's R, L, C, peak and Q.")
    if names == REFUSED:
        raise PickupError(
            "L, C and the peak can't fix the pickup: L and C already give the peak, so R "
            "is left open. Give R or Q instead of one of them."
        )
    r, l, c = given.get("r"), given.get("l"), given.get("c")  # noqa: E741
    peak, q = given.get("peak"), given.get("q")
    if peak is not None:
        w = 2 * math.pi * peak
    elif l is not None and c is not None:
        w = 1 / math.sqrt(l * c)
    elif r is not None and l is not None and q is not None:
        w = q * r / l
    else:  # R, C and Q
        assert r is not None and c is not None and q is not None
        l = q * q * r * r * c  # noqa: E741
        w = 1 / math.sqrt(l * c)
    if l is None:
        if c is not None:
            l = 1 / (w * w * c)  # noqa: E741
        else:  # R and Q with the peak
            assert r is not None and q is not None
            l = q * r / w  # noqa: E741
    if r is None:
        assert q is not None
        r = w * l / q
    return {"r": r, "l": l, "c": 1 / (w * w * l), "peak": w / (2 * math.pi), "q": w * l / r}


def blocked(names: Sequence[str]) -> dict[str, str]:
    """With two set, the box that can't be the third (L, C and peak together), with why:
    {"peak": "Not the peak: L and C give it."}. Empty otherwise."""
    if len(names) != 2 or not set(names) < REFUSED:
        return {}
    (left,) = REFUSED - set(names)
    a, b = names
    return {left: f"Not {_the(left)}: {_the(a)} and {_the(b)} give it."}


def kept(typed: Sequence[str]) -> tuple[list[str], str | None]:
    """The set boxes when a fourth is typed: the three typed last, unless they're L, C and
    peak; then the one typed least recently that leaves a valid three goes. Returns the
    kept names (in typing order) and the one dropped, if any."""
    names = list(dict.fromkeys(reversed(typed)))[::-1][-4:]  # typed again: its last time
    if len(names) <= 3:
        return names, None
    drop = names[0] if set(names[1:]) != REFUSED else names[1]
    return [n for n in names if n != drop], drop


@dataclass(frozen=True)
class PickupForm:
    """What the pickup's five boxes show: `set` (name → text as typed, in typing order),
    `values` (all five as SI floats once three are set), `shown` (each worked-out box's
    value as text, `151p`), `dimmed` (a box that can't complete it → why), `line` (the
    words under the boxes) and `dropped` (a set box a fourth turned into a worked-out one)."""

    set: dict[str, str]
    values: dict[str, float] = field(default_factory=dict)
    shown: dict[str, str] = field(default_factory=dict)
    dimmed: dict[str, str] = field(default_factory=dict)
    line: str = ""
    dropped: str | None = None

    def stored(self) -> dict[str, str]:
        """R, L and C as the file keeps them: as typed if set, else worked out to four figures."""
        return {n: self.set.get(n) or format_value(self.values[n], 4) for n in ("r", "l", "c")}


def pickup_form(typed: Sequence[tuple[str, str]]) -> PickupForm:
    """The form from the boxes typed, oldest first (a box typed again comes last; an empty
    one isn't set). Raises PickupError for a value that can't be used, or a third that can't
    complete it (the dimmed box)."""
    texts = {name: text.strip() for name, text in typed}
    order = list(dict.fromkeys(reversed([n for n, t in typed if t.strip()])))[::-1]
    for name in order:
        value_of(name, texts[name])
    if len(order) == 3 and set(order) == REFUSED:
        raise PickupError(next(iter(blocked(order[:2]).values())))
    names, dropped = kept(order)
    chosen = {n: texts[n] for n in names}
    if len(names) < 3:
        return PickupForm(set=chosen, dimmed=blocked(names), line=_guide_line(names))
    values = solve({n: value_of(n, t) for n, t in chosen.items()})
    others = [n for n in QUANTITIES if n not in chosen]
    shown = {n: format_value(values[n]) for n in others}
    listed = (", ".join(NAMES[n] for n in group) for group in (names, others))
    line = "Set: {} · worked out: {}".format(*listed)
    if dropped:
        why = "set first" if dropped == order[-4] else "set first that could go"
        line += f" ({NAMES[dropped]} was {why}, so it's worked out now)"
    return PickupForm(set=chosen, values=values, shown=shown, line=line, dropped=dropped)


def _guide_line(names: Sequence[str]) -> str:
    """The line while fewer than three are set: what's still needed."""
    if not names:
        return f"Type any three of the five. {EASIEST}"
    left = [n for n in QUANTITIES if n not in names]
    if len(names) == 1:
        return f"{NAMES[names[0]]} set. Two more: any of {_joined(left, 'or')}."
    no = blocked(names)
    can = [n for n in left if n not in no]
    line = f"{_joined(names)} set. One more: {_joined(can, 'or')}."
    if no:
        line += " " + next(iter(no.values()))
    if "r" not in names:
        line += f" {EASIEST}"
    return line


def check_set(set_: Mapping[str, str], r: float, l: float, c: float) -> None:  # noqa: E741
    """A file's `pickup.set` against its R, L and C: three valid boxes whose pickup is the
    one stored (within 1 %). Raises PickupError."""
    given = {n: value_of(n, t) for n, t in set_.items()}
    values = solve(given)
    for name, stored in (("r", r), ("l", l), ("c", c)):
        if not math.isclose(values[name], stored, rel_tol=0.01):
            raise PickupError(
                f"The pickup's {NAMES[name]} isn't what its set values "
                f"({', '.join(set_)}) give. Type them again in the guitar's form."
            )
