"""Each board part's footprint (D-367): how its legs may sit and what its body covers,
from the footprints table (`library/guides/footprints.yaml`), and which circuit pin each
leg carries. A chip of several units is one board part (IC1), its legs its pin numbers.
"""

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Literal

from solum.circuit.parts import pin_offsets
from solum.circuit.schema import (
    CHIP_UNITS,
    Bjt,
    Capacitor,
    ChargePump,
    ChipUnit,
    Circuit,
    Diode,
    Jfet,
    Led,
    Mosfet,
    Part,
    PowerUnit,
    Regulator,
    Resistor,
    Switch,
    Trimmer,
)
from solum.export import built_where
from solum.guides import FootprintTable, InlineSize, RadialSize
from solum.models import Model, ModelError, ModelLibrary
from solum.rules.checks import DEFAULT_RATING_W
from solum.stripboard.board import Hole
from solum.units import parse_value

PITCH = 2.54  # mm between holes
Shape = Literal["axial", "radial", "inline", "dip", "sil"]
PinRef = tuple[str, str]
SURFACE_MOUNT = ("SMD", "SC-59", "SC-70", "SOT-", "SOD-")  # in a package's name


@dataclass(frozen=True)
class Footprint:
    """`steps`: the leg spacings allowed, in holes (a radial's span, an inline's step);
    `flat`/`stand`: an axial's least span lying flat and its span standing; the body in mm
    (`length` along the legs' line, `width` across, or `diameter`; none: covers no hole);
    `order`: the legs in a line or a chip's, in pin order; `row_holes`: a DIP's rows apart."""

    shape: Shape
    steps: tuple[int, ...] = ()
    flat: int = 0
    stand: int = 0
    length: float = 0.0
    width: float = 0.0
    diameter: float = 0.0
    order: tuple[str, ...] = ()
    row_holes: int = 0


@dataclass(frozen=True)
class BoardPart:
    """A part as the board sees it: `pins` the circuit pin on each leg; `free` legs carry
    a pin the drawing doesn't use (a chip's offset null): alone on their strip; any other
    leg not in `pins` is a no-connect, free to share."""

    ref: str
    footprint: Footprint
    pins: dict[str, PinRef]
    free: frozenset[str] = field(default_factory=frozenset)
    kind: str = ""  # its type, for the words: resistor, bjt, chip...

    @property
    def legs(self) -> tuple[str, ...]:
        """Its leg names: in a line's or a chip's order, else its pins'."""
        return self.footprint.order or tuple(self.pins)


class NoFootprint(ValueError):
    """A part the table has no size for (plain-English message)."""


def _by_package[S: RadialSize | InlineSize](sizes: Iterable[S], package: str) -> S | None:
    """The entry whose `package` starts the model's package name, the longest match."""
    fits = [s for s in sizes if s.package and package.startswith(s.package)]
    return max(fits, key=lambda s: len(s.package or ""), default=None)


def _radial(size: RadialSize) -> Footprint:
    return Footprint("radial", tuple(size.holes), length=size.length, width=size.width,
                     diameter=size.diameter)  # fmt: skip


def _inline(size: InlineSize, order: tuple[str, ...]) -> Footprint:
    return Footprint("inline", tuple(size.holes), length=size.length, width=size.width,
                     diameter=size.diameter, order=order)  # fmt: skip


def _package(model: Model, ref: str) -> str:
    if model.info.package is None:
        raise NoFootprint(
            f"{ref}'s model {model.info.id} has no package with pin numbers, so its legs "
            "can't be placed. Choose a model that has one."
        )
    package = model.info.package.name
    if any(word in package for word in SURFACE_MOUNT):
        raise NoFootprint(
            f"{ref}'s {model.info.id} is surface-mount ({package}): it can't go on a "
            "stripboard. Choose a through-hole model for it."
        )
    return package


def _pin_order(model: Model) -> tuple[str, ...]:
    pins = model.info.package.pins if model.info.package else {}
    return tuple(sorted(pins, key=lambda p: pins[p]))


def two_leg_footprint(part: Part, models: ModelLibrary, table: FootprintTable) -> Footprint:
    """A resistor's, capacitor's, diode's or on-board LED's footprint."""
    ref = part.ref
    if isinstance(part, Resistor):
        watts = part.rating_w or DEFAULT_RATING_W
        size = next((s for s in table.axial["resistor"] if (s.max_watts or 0) >= watts), None)
        if size is None:
            raise NoFootprint(f"There's no board size for a {watts:g} W resistor ({ref}) yet.")
        return Footprint("axial", flat=size.flat, stand=size.stand, length=size.length,
                         width=size.diameter)  # fmt: skip
    if isinstance(part, Diode):
        package = _package(models.get(part.model), ref)
        axial = next((s for s in table.axial["diode"] if package.startswith(s.package or "-")),
                     None)  # fmt: skip
        if axial is None:
            raise NoFootprint(f"There's no board size for {ref}'s package ({package}) yet.")
        return Footprint("axial", flat=axial.flat, stand=axial.stand, length=axial.length,
                         width=axial.diameter)  # fmt: skip
    if isinstance(part, Led):
        package = _package(models.get(part.model), ref)
        led = _by_package(table.radial["led"], package)
        if led is None:
            raise NoFootprint(f"There's no board size for {ref}'s package ({package}) yet.")
        return _radial(led)
    if isinstance(part, Capacitor):
        if part.kind is None:
            raise NoFootprint(
                f"{ref} has no type, so its size isn't known: set its type (film, "
                "electrolytic...) in its properties."
            )
        sizes = table.radial.get(part.kind)
        if sizes is None:
            raise NoFootprint(f"There's no board size for {part.kind} capacitors ({ref}) yet.")
        value = parse_value(part.value)
        cap = next((s for s in sizes if parse_value(s.max_value or "0") >= value * 0.999), None)
        if cap is None:
            raise NoFootprint(f"There's no board size for a {part.kind} as big as {ref} yet.")
        return _radial(cap)
    if isinstance(part, Switch):
        raise NoFootprint(f"There's no board size for DIP switches ({part.switch}) yet.")
    raise NoFootprint(f"There's no board size for {part.type}s ({ref}) yet.")


def _three_leg(part: Bjt | Jfet | Mosfet | Regulator, models: ModelLibrary,
               table: FootprintTable) -> BoardPart:  # fmt: skip
    model = models.get(part.model)
    package = _package(model, part.ref)
    size = _by_package(table.inline, package)
    if size is None:
        raise NoFootprint(f"There's no board size for {part.ref}'s package ({package}) yet.")
    order = _pin_order(model)
    pins = {pin: (part.ref, pin) for pin in order}
    return BoardPart(part.ref, _inline(size, order), pins, kind=part.type)


_CHIP_PACKAGE = re.compile(r"(\d+)-pin (DIP|SIL)")


def _chip(ref: str, units: Sequence[Part], model: Model, table: FootprintTable) -> BoardPart:
    """A chip, its units and power unit together: legs by pin number."""
    package = _package(model, ref)
    found = _CHIP_PACKAGE.match(package)
    if found is None:
        raise NoFootprint(f"There's no board size for {ref}'s package ({package}) yet.")
    count = int(found.group(1))
    order = tuple(str(n) for n in range(1, count + 1))
    pins: dict[str, PinRef] = {}
    for unit in units:
        half = getattr(unit, "half", None)
        for pin in pin_offsets(unit):
            number = model.pin_number(pin, half) or (int(pin) if pin.isdigit() else None)
            if number is not None:
                pins[str(number)] = (unit.ref, pin)
    named = model.info.package.pins if model.info.package else {}
    free = frozenset(str(n) for p, n in named.items() if p != "nc" and str(n) not in pins)
    if found.group(2) == "DIP":
        shape = Footprint("dip", width=table.dip.width, order=order, row_holes=table.dip.row_holes)
    else:
        shape = Footprint("sil", (1,), length=count * PITCH, width=table.sil.width, order=order)
    return BoardPart(ref, shape, pins, free, kind="chip")


def board_parts(circuit: Circuit, models: ModelLibrary,
                table: FootprintTable) -> tuple[dict[str, BoardPart], list[str]]:  # fmt: skip
    """The parts that go on the board, by board ref, and what can't go on one (plain
    English, one sentence per part)."""
    found: dict[str, BoardPart] = {}
    problems: list[str] = []
    chips: dict[str, list[ChipUnit | PowerUnit]] = {}
    for part in circuit.parts:
        if built_where(part) != "board":
            continue
        try:
            if isinstance(part, (PowerUnit, *CHIP_UNITS)):
                chips.setdefault(part.chip, []).append(part)
            elif isinstance(part, ChargePump):
                found[part.ref] = _chip(part.ref, [part], models.get(part.model), table)
            elif isinstance(part, Bjt | Jfet | Mosfet | Regulator):
                found[part.ref] = _three_leg(part, models, table)
            elif isinstance(part, Trimmer):
                order = ("1", "2", "3")
                pins = {pin: (part.ref, pin) for pin in order}
                found[part.ref] = BoardPart(part.ref, _inline(table.trimmer, order), pins,
                                            kind="trimmer")  # fmt: skip
            else:
                footprint = two_leg_footprint(part, models, table)
                pins = {pin: (part.ref, pin) for pin in pin_offsets(part)}
                found[part.ref] = BoardPart(part.ref, footprint, pins, kind=part.type)
        except (NoFootprint, ModelError) as err:
            if str(err) not in problems:
                problems.append(str(err))
    for chip, units in chips.items():
        try:
            model = models.get(units[0].model)
            found[chip] = _chip(chip, units, model, table)
        except (NoFootprint, ModelError) as err:
            problems.append(str(err))
    return found, problems


def drawing_data(parts: dict[str, BoardPart]) -> dict[str, dict[str, object]]:
    """What the Board view draws each board part from (D-368), as plain JSON: its shape,
    legs in order, the spacings allowed, the body in mm, and `refs` the circuit parts on it
    (a chip's units), so selecting it lights them on the schematic."""
    out: dict[str, dict[str, object]] = {}
    for ref, part in sorted(parts.items()):
        fp = part.footprint
        out[ref] = {
            "shape": fp.shape, "kind": part.kind, "legs": list(part.legs),
            "steps": list(fp.steps), "flat": fp.flat, "stand": fp.stand,
            "length": fp.length, "width": fp.width, "diameter": fp.diameter,
            "row_holes": fp.row_holes,
            "refs": sorted({pin[0] for pin in part.pins.values()} or {ref}),
        }  # fmt: skip
    return out


def _line(holes: list[Hole]) -> tuple[int, int] | None:
    """The unit step from each hole to the next when they're in a straight row or column
    with equal gaps, as (dx, dy) in holes, else None."""
    (x0, y0), (x1, y1) = holes[0], holes[1]
    dx, dy = x1 - x0, y1 - y0
    if (dx == 0) == (dy == 0):
        return None
    for (ax, ay), (bx, by) in pairwise(holes):
        if (bx - ax, by - ay) != (dx, dy):
            return None
    return dx, dy


def dip_legs(pins: int, pin1: Hole, turned: bool = False, row_holes: int = 3) -> dict[str, Hole]:
    """A DIP's legs: pin 1 at `pin1`, pins down the left column and back up the right one
    `row_holes` to the right; `turned` (180°): pin 1 at `pin1` going up, the other row to
    the left."""
    half = pins // 2
    x, y = pin1
    sign = -1 if turned else 1
    legs = {}
    for k in range(half):
        legs[str(k + 1)] = (x, y + sign * k)
        legs[str(pins - k)] = (x + sign * row_holes, y + sign * k)
    return legs


def leg_problem(part: BoardPart, legs: dict[str, Hole], standing: bool) -> str | None:
    """What's wrong with where the legs are, in plain English, or None."""
    fp = part.footprint
    names = set(part.legs)
    if set(legs) != names:
        want = ", ".join(sorted(names))
        return f"{part.ref} needs exactly its legs placed ({want})."
    if standing and fp.shape != "axial":
        return f"{part.ref} can't be stood up: only resistors and diodes stand."
    if fp.shape in ("axial", "radial"):
        a, b = legs.values()
        if a[0] != b[0] and a[1] != b[1]:
            return f"{part.ref}'s legs must be in one row or one column."
        span = abs(a[0] - b[0]) + abs(a[1] - b[1])
        if fp.shape == "radial" and span not in fp.steps:
            return f"{part.ref}'s legs must be {_holes_text(fp.steps)} apart."
        if fp.shape == "axial" and standing and span != fp.stand:
            return f"{part.ref} standing has its legs {_holes_text((fp.stand,))} apart."
        if fp.shape == "axial" and not standing and span < fp.flat:
            return f"{part.ref} lying flat needs its legs at least {fp.flat} holes apart."
        return None
    if fp.shape == "dip":
        count = len(fp.order)
        pin1 = legs["1"]
        options = (dip_legs(count, pin1, t, fp.row_holes) for t in (False, True))
        if legs not in list(options):
            return (
                f"{part.ref} sits across the strips: pins 1 to {count // 2} down one column, "
                f"the rest back up the column {fp.row_holes} holes over."
            )
        return None
    step = _line([legs[n] for n in fp.order])
    if step is None or abs(step[0] + step[1]) not in fp.steps:
        return f"{part.ref}'s legs go in a line, in order, {_holes_text(fp.steps)} apart."
    return None


def _holes_text(steps: tuple[int, ...]) -> str:
    words = [f"{n} hole" + ("s" if n > 1 else "") for n in steps]
    return " or ".join(words)


def body_holes(part: BoardPart, legs: dict[str, Hole], standing: bool) -> set[Hole]:
    """The holes the part's body covers, its own legs left out (legs already checked)."""
    fp = part.footprint
    if standing or not (fp.diameter or fp.length):
        return set()
    xs = [h[0] for h in legs.values()]
    ys = [h[1] for h in legs.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    along_x = max(xs) - min(xs) >= max(ys) - min(ys)
    if fp.shape == "dip":
        along_x = False  # its length runs down the columns, its width across them
    reach = math.ceil(max(fp.diameter, fp.length, fp.width) / PITCH) + 1
    covered = set()
    for x in range(math.floor(cx) - reach, math.ceil(cx) + reach + 1):
        for y in range(math.floor(cy) - reach, math.ceil(cy) + reach + 1):
            dx, dy = (x - cx) * PITCH, (y - cy) * PITCH
            if fp.diameter:
                inside = dx * dx + dy * dy < (fp.diameter / 2) ** 2 - 1e-6
            else:
                length = fp.length or (len(fp.order) // 2) * PITCH
                hx, hy = (length, fp.width) if along_x else (fp.width, length)
                inside = abs(dx) < hx / 2 - 1e-6 and abs(dy) < hy / 2 - 1e-6
            if inside:
                covered.add((x, y))
    return covered - set(legs.values())
