"""The off-board parts beside the board and their lugs (spec, *Off-board parts and wires*;
D-375): what's dragged in whole and wired to the board.

An off-board part is one thing bought, as the parts list counts it (D-203: a pot however
many gangs, a switch however many poles, the guitar's and amp's jacks when none is drawn),
plus *Power*, the supplies the board needs that no drawn battery or DC jack brings. Each
has its lugs, each lug an end a wire starts from: a circuit part's pin (`VR1.2`,
`VR1A.3`, `SW1.1`), a jack's sleeve the schematic doesn't draw (`IN.S`), or a supply
(`V+`, `GND`). Pure, from the circuit and its nets.

Each part's drawing is its `shape` (D-384): most are a box with their lugs in a row along
the bottom; a switch is drawn as the real one seen from behind, its lugs where they are
on it: a footswitch a square of lugs and a toggle a slim one (poles across, each pole's
lugs down, the common in the middle: lug 1 at the top, 3 at the bottom), a rotary its lugs
round a ring with the commons inside. This module is the one owner of where each lug is
(`OffItem.places`); the page draws them there and `wiring` measures from them.
"""

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from solum.circuit.connectivity import GROUND, Nets
from solum.circuit.parts import pin_offsets
from solum.circuit.schema import AmpInput, Battery, Circuit, DcJack, Guitar, Part, Pot, Switch
from solum.circuit.switches import POLE_LETTERS, SwitchKind, lug_name
from solum.export import bom, built_where
from solum.models import ModelLibrary
from solum.stripboard.board import Hole, Layout
from solum.stripboard.footprints import BoardPart

POWER = "power"  # the off-board part that stands for the supplies no drawn part brings
SUPPLY_PARTS = (Battery, DcJack)  # a drawn supply: its own pins are the supply's wires
SLEEVE = "S"  # an undrawn jack's sleeve: `IN.S`, on ground
LUG_GAP = 2  # holes between an off-board part's lugs as drawn
GAP = 2  # free holes between off-board parts, and between them and the margin
MARGIN = 3  # the free holes the page draws round the board (board-logic.js's MARGIN)
ROW, STOMP, TOGGLE, ROTARY = "row", "stomp", "toggle", "rotary"  # how a part is drawn
Place = tuple[float, float]  # a lug's place in holes from its drawing's top-left hole


@dataclass(frozen=True)
class Lug:
    """An end a wire starts from: `end` as wires name it, `label` as drawn ("2", "T",
    "V+"), `net` the circuit's net it's on."""

    end: str
    label: str
    net: str


@dataclass(frozen=True)
class OffItem:
    """An off-board part beside the board: `ref` its name ("VR1", "IN", "SW1", "power"),
    `name` with its label as the parts list says it ("VR1 (Gain)"), `kind` what it's drawn
    as (pot, jack, switch, dcjack, battery, led, power), `value` and `details` as the parts
    list has them; `lugs` in order. `shape` how it's drawn (row, stomp, toggle, rotary),
    `size` its drawing's (columns, strips) in holes and `places` each lug's place in it,
    in holes from its top-left hole (a ring's on the half-hole grid)."""

    ref: str
    name: str
    kind: str
    value: str
    details: str
    lugs: tuple[Lug, ...]
    shape: str = ROW
    size: Hole = (3, 3)
    places: tuple[Place, ...] = ()


def row_drawing(count: int) -> tuple[Hole, tuple[Place, ...]]:
    """A box with `count` lugs in a row along its bottom, `LUG_GAP` holes apart."""
    width = max(3, LUG_GAP * count + 1)
    return (width, 3), tuple((1.0 + LUG_GAP * i, 2.0) for i in range(count))


def grid_drawing(cells: list[tuple[int, int]], square: bool) -> tuple[Hole, tuple[Place, ...]]:
    """Lugs on a grid `LUG_GAP` holes apart, each (across, down) of `cells`, a hole clear
    of the edge; `square`: the drawing as tall as it's wide, the lugs in its middle."""
    across = max(c for c, _ in cells) + 1
    down = max(r for _, r in cells) + 1
    width, height = LUG_GAP * across + 1, LUG_GAP * down + 1
    side = max(width, height)
    dx, dy = ((side - width) // 2, (side - height) // 2) if square else (0, 0)
    size = (side, side) if square else (width, height)
    return size, tuple((1.0 + dx + LUG_GAP * c, 1.0 + dy + LUG_GAP * r) for c, r in cells)


def _half(v: float) -> float:
    return round(v * 2) / 2


def ring_drawing(poles: int, throws: int) -> tuple[Hole, list[list[Place]]]:
    """A rotary seen from behind: each pole's throws in turn round a ring from the top,
    clockwise, its common inside at the middle of its throws (the centre on a single pole).
    Per pole, its common's place then its throws'."""
    outer = poles * throws
    radius = max(2.5, _half(1.8 * outer / (2 * math.pi) + 0.25))
    side = math.ceil(2 * radius) + 3
    centre = (side - 1) / 2

    def at(angle: float, r: float) -> Place:
        a = math.radians(angle)
        return (_half(centre + r * math.cos(a)), _half(centre + r * math.sin(a)))

    found: list[list[Place]] = []
    for p in range(poles):
        middle = -90 + 360 * (p * throws + throws / 2) / outer
        common = at(middle, radius * 0.4) if poles > 1 else (_half(centre),) * 2
        found.append([common] + [at(-90 + 360 * (p * throws + t + 0.5) / outer, radius)
                                 for t in range(throws)])  # fmt: skip
    return (side, side), found


def switch_drawing(kind: SwitchKind) -> tuple[str, Hole, dict[str, Place]]:
    """A switch's shape, size and each lug's place by its pin name (A2, or 2 on a single
    pole), every pole's, drawn or not (D-384)."""
    letters = [p for p in POLE_LETTERS[: kind.poles].lower()] if kind.poles > 1 else [None]
    if kind.look == "rotary":
        size, rings = ring_drawing(kind.poles, len(kind.throws))
        places = {lug_name(kind, pole, lug): at for pole, ring in zip(letters, rings, strict=True)
                  for lug, at in zip(kind.lugs, ring, strict=True)}  # fmt: skip
        return ROTARY, size, places
    throws = list(kind.throws)
    half = len(throws) // 2
    down = [*throws[:half], kind.common, *throws[half:]]  # lug 1 at the top, the common mid
    keys = [lug_name(kind, pole, lug) for pole in letters for lug in kind.lugs]
    cells = [(i, down.index(lug)) for i in range(len(letters)) for lug in kind.lugs]
    shape = STOMP if kind.group == "Footswitch" else TOGGLE
    size, at = grid_drawing(cells, square=shape == STOMP)
    return shape, size, dict(zip(keys, at, strict=True))


def _lug_label(part: Part, pin: str, several: bool) -> str:
    """A lug's label: its pin ("2", "T", "+"), with the gang when a pot has several
    ("A2"; a switch pole's pins carry their letter already); a guitar's or amp's signal
    pin is its jack's tip."""
    label = "T" if isinstance(part, Guitar | AmpInput) and pin in ("out", "in") else pin
    label = "R" if isinstance(part, Guitar) and pin == "ring" else label
    return f"{part.ref[-1]}{label}" if several and not isinstance(part, Switch) else label


def _drawing(parts: list[Part], pins: list[str]) -> tuple[str, Hole, tuple[Place, ...]]:
    """How an off-board part is drawn, each of its lugs' `pins` placed: a switch by its
    type; anything else a row of lugs."""
    if isinstance(parts[0], Switch):
        shape, size, places = switch_drawing(parts[0].switch_kind)
        if all(pin in places for pin in pins):
            return shape, size, tuple(places[pin] for pin in pins)
    return (ROW, *row_drawing(len(pins)))


def _parts_of(circuit: Circuit, base: str, kind: str) -> list[Part]:
    """The circuit parts one parts-list item stands for: the guitar for `IN`, the amp for
    `OUT`, a pot's gangs, a switch's poles, else the part itself."""
    if kind == "jack" and base in ("IN", "OUT"):
        wanted = Guitar if base == "IN" else AmpInput
        found: list[Part] = [p for p in circuit.parts if isinstance(p, wanted)]
        if found:
            return found
    return [p for p in circuit.parts if built_where(p) == "off-board" and (
        p.ref == base or (isinstance(p, Pot) and p.knob == base)
        or (isinstance(p, Switch) and p.switch == base))]  # fmt: skip


def _kind(parts: list[Part]) -> str:
    part = parts[0]
    if isinstance(part, Guitar | AmpInput):
        return "jack"
    return part.type


def off_board_items(circuit: Circuit, nets: Nets, board: Mapping[str, BoardPart],
                    models: ModelLibrary) -> list[OffItem]:  # fmt: skip
    """Every off-board part the Board view shows beside the board, in the parts list's
    order, then *Power* when the board needs a supply no drawn part brings."""
    items: list[OffItem] = []
    brought: set[str] = set()
    for line in bom(circuit, models):
        if line.where != "off-board":
            continue
        for named in line.refs:
            base = named.split(" ")[0]
            parts = _parts_of(circuit, base, line.part.lower())
            if not parts:
                continue
            several = len(parts) > 1
            lugs = [Lug(f"{p.ref}.{pin}", _lug_label(p, pin, several), nets.net_of(p.ref, pin))
                    for p in parts for pin in pin_offsets(p)]  # fmt: skip
            if isinstance(parts[0], Guitar | AmpInput):
                lugs.append(Lug(f"{parts[0].ref}.{SLEEVE}", SLEEVE, GROUND))
            if isinstance(parts[0], SUPPLY_PARTS):
                brought |= {lug.net for lug in lugs}
            shape, size, places = _drawing(parts, [lug.end.split(".")[1] for lug in lugs])
            items.append(OffItem(base, named, _kind(parts), line.value, line.details,
                                 tuple(lugs), shape, size, places))  # fmt: skip
    carried = {nets.net_of(*pin) for part in board.values() for pin in part.pins.values()}
    supplies = sorted({*circuit.power.rails, GROUND} & carried - brought,
                      key=lambda s: (s == GROUND, s))  # fmt: skip
    if supplies:
        size, places = row_drawing(len(supplies))
        items.append(OffItem(POWER, "Power", "power", "", "the supply's wires",
                             tuple(Lug(s, s, s) for s in supplies), ROW, size, places))  # fmt: skip
    return items


def lug_nets(items: Iterable[OffItem]) -> dict[str, str]:
    """Every lug's end → its net."""
    return {lug.end: lug.net for item in items for lug in item.lugs}


def _natural(text: str) -> list[object]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def default_spots(items: list[OffItem], layout: Layout) -> dict[str, Hole]:
    """Where each off-board part is drawn when it hasn't been put anywhere (spec, *Wire it
    for me*): pots and the rest along the top in knob order, the input jack at the right,
    the output at the left, *Power* at the bottom left corner; footswitches below the
    board, side by side round its middle, and then the jacks at the bottom of their sides,
    so the wires between them are short (D-384). Each spot its drawing's top left hole,
    clear of the board's margin."""
    spots: dict[str, Hole] = {}
    above = -MARGIN - GAP
    below = layout.strips + MARGIN + GAP - 1
    left = -MARGIN - GAP
    right = layout.columns + MARGIN + GAP - 1
    stomps = [i for i in items if i.shape == STOMP]
    span = sum(i.size[0] for i in stomps) + GAP * (len(stomps) - 1)
    under = max(left + GAP, (layout.columns - span) // 2)
    jacks = 0 if not stomps else max(0, layout.strips - 3)
    column = 0
    for item in sorted(items, key=lambda i: (i.kind != "pot", _natural(i.ref))):
        width, height = item.size
        if item.ref == "IN":
            spots[item.ref] = (right, jacks)
        elif item.ref == "OUT":
            spots[item.ref] = (left - width + 1, jacks)
        elif item.ref == POWER:
            spots[item.ref] = (left - width + 1, below)
        elif item.shape == STOMP:
            spots[item.ref] = (under, below)
            under += width + GAP
        else:
            spots[item.ref] = (column, above - height + 1)
            column += width + GAP
    return spots
