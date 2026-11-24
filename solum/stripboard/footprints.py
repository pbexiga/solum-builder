"""Each board part's footprint (D-367): how its legs may sit and what its body covers,
from the footprints table (`library/guides/footprints.yaml`), and which circuit pin each
leg carries. A chip of several units is one board part (IC1), its legs its pin numbers.
"""

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cache
from itertools import pairwise
from typing import Literal

from solum.circuit.parts import pin_offsets
from solum.circuit.schema import (
    CHIP_UNITS,
    POLARISED,
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
from solum.circuit.switches import POLE_LETTERS, lug_name
from solum.export import built_where, chosen_where
from solum.guides import FootprintTable, InlineSize, RadialSize
from solum.markings import resistor_bands
from solum.models import Model, ModelError, ModelLibrary
from solum.rules.checks import DEFAULT_RATING_W
from solum.stripboard.board import PITCH, Hole
from solum.units import parse_value

Shape = Literal["axial", "radial", "inline", "triangle", "dip", "sil"]
PinRef = tuple[str, str]
SURFACE_MOUNT = ("SMD", "SC-59", "SC-70", "SOT-", "SOD-")  # in a package's name


@dataclass(frozen=True)
class Footprint:
    """`steps`: the leg spacings allowed, in holes (a radial's span, an inline's step);
    `flat`/`stand`: an axial's least span lying flat and its span standing; the body in mm
    (`length` along the legs' line, `width` across, or `diameter`; none: covers no hole);
    `order`: the legs in a line or a chip's, in pin order; `row_holes`: a DIP's rows apart;
    `package`: the table's package it was sized by, for the drawing (an inline part's)."""

    shape: Shape
    steps: tuple[int, ...] = ()
    flat: int = 0
    stand: int = 0
    length: float = 0.0
    width: float = 0.0
    diameter: float = 0.0
    order: tuple[str, ...] = ()
    row_holes: int = 0
    package: str = ""


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
                     diameter=size.diameter, order=order, package=size.package or "")  # fmt: skip


ADAPTER_PACKAGE = "TO-92"  # what a surface-mount transistor's adapter takes (D-392)
ADAPTER_ORDER = {"jfet": ("D", "S", "G")}  # Aion's JFET adapter, as the J201; others keep 1-2-3


def surface_mount(model: Model) -> bool:
    """Whether the model's package is surface-mount (its name says so)."""
    package = model.info.package
    return package is not None and any(word in package.name for word in SURFACE_MOUNT)


def _package(model: Model, ref: str, adapter: bool = False) -> str:
    """The model's package, or the adapter's when a surface-mount part is on one (D-392)."""
    if model.info.package is None:
        raise NoFootprint(
            f"{ref}'s model {model.info.id} has no package with pin numbers, so its legs "
            "can't be placed. Choose a model that has one."
        )
    package = model.info.package.name
    if surface_mount(model):
        if adapter:
            return ADAPTER_PACKAGE
        raise NoFootprint(
            f"{ref}'s {model.info.id} is surface-mount ({package}): it can't go on a "
            "stripboard. Choose a through-hole model for it, or put it on a TO-92 adapter "
            "(its Mounting)."
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
    raise NoFootprint(f"There's no board size for {part.type}s ({ref}) yet.")


def _three_leg(part: Bjt | Jfet | Mosfet | Regulator, models: ModelLibrary,
               table: FootprintTable) -> BoardPart:  # fmt: skip
    model = models.get(part.model)
    on_adapter = getattr(part, "adapter", False) and surface_mount(model)
    package = _package(model, part.ref, on_adapter)
    size = _by_package(table.inline, package)
    if size is None:
        raise NoFootprint(f"There's no board size for {part.ref}'s package ({package}) yet.")
    order = ADAPTER_ORDER.get(part.type, _pin_order(model)) if on_adapter else _pin_order(model)
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


def _dip_switch(ref: str, poles: Sequence[Switch], table: FootprintTable) -> BoardPart:
    """A DIP switch, its poles together as a chip's DIP (D-397): switch k (pole k) from
    pin k, its lug 1, to the pin across from it, its lug 2."""
    kind = poles[0].switch_kind
    count = 2 * kind.poles
    pins: dict[str, PinRef] = {}
    for part in poles:
        k = POLE_LETTERS.index(part.pole.upper()) + 1 if part.pole else 1
        pins[str(k)] = (part.ref, lug_name(kind, part.pole, "1"))
        pins[str(count + 1 - k)] = (part.ref, lug_name(kind, part.pole, "2"))
    size = table.dip_switch
    order = tuple(str(n) for n in range(1, count + 1))
    shape = Footprint("dip", length=kind.poles * PITCH + size.extra, width=size.width,
                      order=order, row_holes=size.row_holes)  # fmt: skip
    return BoardPart(ref, shape, pins, kind="switch")


def board_ref(part: Part) -> str:
    """The board part a circuit part is on: a chip unit's chip (`IC1` for `IC1A`), a
    switch pole's switch (`SW3` for `SW3A`), else its own ref."""
    if isinstance(part, Switch):
        return part.switch
    return part.chip if isinstance(part, (PowerUnit, *CHIP_UNITS)) else part.ref


def board_refs(circuit: Circuit) -> set[str]:
    """Every board part the circuit has, placeable now or not (D-376)."""
    chosen = chosen_where(circuit)
    return {board_ref(p) for p in circuit.parts if built_where(p, chosen) == "board"}


def one_board_part(part: Part, models: ModelLibrary, table: FootprintTable) -> BoardPart:
    """A part that isn't a chip's unit as it goes on the board; `NoFootprint` or
    `ModelError` saying why when it can't."""
    if isinstance(part, ChargePump):
        return _chip(part.ref, [part], models.get(part.model), table)
    if isinstance(part, Switch):
        if part.switch_kind.group != "DIP":
            raise NoFootprint(f"There's no board size for a {part.switch_kind.short} switch yet.")
        return _dip_switch(part.switch, [part], table)
    if isinstance(part, Bjt | Jfet | Mosfet | Regulator):
        return _three_leg(part, models, table)
    if isinstance(part, Trimmer):
        order = ("1", "2", "3")
        pins = {pin: (part.ref, pin) for pin in order}
        if part.style == "inline":
            return BoardPart(part.ref, _inline(table.trimmer, order), pins, kind="trimmer")
        size = table.trimmer_triangle
        shape = Footprint("triangle", (1,), length=size.length, width=size.width, order=order)
        return BoardPart(part.ref, shape, pins, kind="trimmer")
    footprint = two_leg_footprint(part, models, table)
    pins = {pin: (part.ref, pin) for pin in pin_offsets(part)}
    return BoardPart(part.ref, footprint, pins, kind=part.type)


def board_parts(circuit: Circuit, models: ModelLibrary,
                table: FootprintTable) -> tuple[dict[str, BoardPart], list[str]]:  # fmt: skip
    """The parts that go on the board, by board ref, and what can't go on one (plain
    English, one sentence per part)."""
    found: dict[str, BoardPart] = {}
    problems: list[str] = []
    chips: dict[str, list[ChipUnit | PowerUnit]] = {}
    switches: dict[str, list[Switch]] = {}
    chosen = chosen_where(circuit)
    for part in circuit.parts:
        if built_where(part, chosen) != "board":
            continue
        try:
            if isinstance(part, (PowerUnit, *CHIP_UNITS)):
                chips.setdefault(part.chip, []).append(part)
            elif isinstance(part, Switch) and part.switch_kind.group == "DIP":
                switches.setdefault(part.switch, []).append(part)
            else:
                found[part.ref] = one_board_part(part, models, table)
        except (NoFootprint, ModelError) as err:
            if str(err) not in problems:
                problems.append(str(err))
    for chip, units in chips.items():
        try:
            model = models.get(units[0].model)
            found[chip] = _chip(chip, units, model, table)
        except (NoFootprint, ModelError) as err:
            problems.append(str(err))
    for ref, poles in switches.items():
        found[ref] = _dip_switch(ref, poles, table)
    return found, problems


def look(part: BoardPart, circuit_part: Part | None) -> dict[str, object]:
    """How a board part is marked, for its realistic drawing (D-378): a resistor's colour
    bands (`markings.resistor_bands`, 4 bands with a gold 5 % one; none when its value has
    no code), the leg on a polarised capacitor's − stripe, the leg at a diode's band or an
    LED's flat (the cathode), a TO-92's flat face (its legs as read from the face, left to
    right: the package's pin order)."""
    if isinstance(circuit_part, Resistor):
        try:
            bands = resistor_bands(parse_value(circuit_part.value))
        except ValueError:
            bands = None
        return {"bands": [*bands, "gold"]} if bands else {}
    if isinstance(circuit_part, Capacitor) and circuit_part.kind in POLARISED:
        return {"minus": "2"}
    if isinstance(circuit_part, Diode | Led):
        return {"cathode": "K"}
    if part.footprint.package == "TO-92":
        return {"face": True}
    return {}


def drawing_data(parts: dict[str, BoardPart], circuit: Circuit) -> dict[str, dict[str, object]]:
    """What the Board view draws each board part from (D-368), as plain JSON: its shape,
    legs in order, the spacings allowed, the body in mm, `refs` the circuit parts on it
    (a chip's units), so selecting it lights them on the schematic, and `look`, its markings
    (D-378)."""
    kinds = {p.ref: p for p in circuit.parts}
    out: dict[str, dict[str, object]] = {}
    for ref, part in sorted(parts.items()):
        fp = part.footprint
        out[ref] = {
            "shape": fp.shape, "kind": part.kind, "legs": list(part.legs),
            "steps": list(fp.steps), "flat": fp.flat, "stand": fp.stand,
            "length": fp.length, "width": fp.width, "diameter": fp.diameter,
            "row_holes": fp.row_holes,
            "refs": sorted({pin[0] for pin in part.pins.values()} or {ref}),
            "look": look(part, kinds.get(ref)),
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


TRIANGLE = {"1": (1, 0), "2": (0, 1), "3": (1, 2)}  # its own way: 1 above 3, the wiper left


def triangle_legs(turns: int, at: Hole = (0, 0), swapped: bool = False) -> dict[str, Hole]:
    """A triangle trimmer's legs (D-393) turned a quarter clockwise `turns` times, the
    corner of their box at `at`; `swapped`: mirrored, its ends 1 and 3 changed round (it
    turns the other way to set, which a trimmer doesn't mind: the user)."""
    legs = dict(TRIANGLE)
    if swapped:
        legs["1"], legs["3"] = legs["3"], legs["1"]
    for _ in range(turns % 4):
        legs = {leg: (-y, x) for leg, (x, y) in legs.items()}
    x0, y0 = min(x for x, _ in legs.values()), min(y for _, y in legs.values())
    return {leg: (x - x0 + at[0], y - y0 + at[1]) for leg, (x, y) in legs.items()}


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
    if fp.shape == "triangle":
        x0, y0 = min(x for x, _ in legs.values()), min(y for _, y in legs.values())
        if all(legs != triangle_legs(t, (x0, y0), m) for t in range(4) for m in (False, True)):
            return (
                f"{part.ref}'s legs: 1 and 3 two holes apart in a line, the wiper (2) a hole "
                "back from the middle of them."
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
    """The holes the part's body covers, its own legs left out (legs already checked); a
    chip's, the holes between its rows (D-401)."""
    fp = part.footprint
    if standing or not (fp.diameter or fp.length or fp.shape == "dip"):
        return set()
    x0 = min(h[0] for h in legs.values())
    y0 = min(h[1] for h in legs.values())
    shape = _body_shape(fp, frozenset((h[0] - x0, h[1] - y0) for h in legs.values()))
    return {(x + x0, y + y0) for x, y in shape}


def links_under(part: BoardPart, standing: bool) -> bool:
    """Whether a link may pass under the part's body: a flat resistor's or diode's, or a
    chip's between its rows (D-401); never a leg or a wire's hole."""
    return part.footprint.shape == "dip" or (part.footprint.shape == "axial" and not standing)


LEAD = 0.6  # mm: a ¼ W resistor's or a small diode's lead, bent over a standing body (D-403)
Outline = tuple[float, float, float, float, float]  # x0, y0, x1, y1 in mm; radius (0: a box)


def body_outline(part: BoardPart, legs: dict[str, Hole], standing: bool) -> Outline | None:
    """The body's real outline in mm (hole (0, 0) at 0, 0), centred as `_body_shape`
    centres it: a circle's box and radius, or a box (radius 0); None for no body (D-394).
    A standing part's body is over its first leg, its lead bent over to the other: a box
    along the legs as wide as the body, from the body's far side to the lead's (D-403)."""
    fp = part.footprint
    if standing:
        if not fp.width:
            return None
        r = fp.width / 2
        (ax, ay), (bx, by) = legs[part.legs[0]], legs[part.legs[-1]]
        ux, uy = (bx > ax) - (bx < ax), (by > ay) - (by < ay)  # from the body to the lead
        ends = [(ax * PITCH - ux * r, ay * PITCH - uy * r),
                (bx * PITCH + ux * LEAD / 2, by * PITCH + uy * LEAD / 2)]  # fmt: skip
        across = (r * abs(uy), r * abs(ux))  # half the body's width, across the legs' line
        x0, x1 = sorted(x for x, _ in ends)
        y0, y1 = sorted(y for _, y in ends)
        return x0 - across[0], y0 - across[1], x1 + across[0], y1 + across[1], 0.0
    if not (fp.diameter or fp.length or fp.width):
        return None
    xs, ys = [h[0] for h in legs.values()], [h[1] for h in legs.values()]
    cx, cy = (min(xs) + max(xs)) / 2 * PITCH, (min(ys) + max(ys)) / 2 * PITCH
    if fp.diameter:
        r = fp.diameter / 2
        return cx - r, cy - r, cx + r, cy + r, r
    along_x = fp.shape != "dip" and max(xs) - min(xs) >= max(ys) - min(ys)
    length = fp.length or (len(fp.order) // 2) * PITCH
    hx, hy = (length / 2, fp.width / 2) if along_x else (fp.width / 2, length / 2)
    return cx - hx, cy - hy, cx + hx, cy + hy, 0.0


def outline_overlap(a: Outline, b: Outline) -> float:
    """How far two bodies' outlines run into each other, in mm (0 or less: apart): two
    circles by their centres, a circle and a box by the box's point nearest the centre (the
    centre inside the box: the radius plus its way to the nearest side), two boxes by the
    lesser of their overlaps across and along (D-394). Used against a small margin only:
    the outlines are one maker's, so the amount is never shown (D-398)."""
    if a[4] and b[4]:
        ax, ay, bx, by = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return a[4] + b[4] - math.hypot(ax - bx, ay - by)
    if a[4] or b[4]:
        circle, box = (a, b) if a[4] else (b, a)
        cx, cy = (circle[0] + circle[2]) / 2, (circle[1] + circle[3]) / 2
        if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
            return circle[4] + min(cx - box[0], box[2] - cx, cy - box[1], box[3] - cy)
        nx, ny = min(max(cx, box[0]), box[2]), min(max(cy, box[1]), box[3])
        return circle[4] - math.hypot(cx - nx, cy - ny)
    return min(min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1]))


@cache
def _body_shape(fp: Footprint, legs: frozenset[Hole]) -> frozenset[Hole]:
    """A body's holes for legs placed from (0, 0): the same wherever the part sits, so
    worked out once per footprint and leg shape (*Tidy up* asks thousands of times)."""
    xs = [h[0] for h in legs]
    ys = [h[1] for h in legs]
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
    return frozenset(covered - legs)
