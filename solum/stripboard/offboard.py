"""The off-board parts beside the board and their lugs (spec, *Off-board parts and wires*;
D-375): what's dragged in whole and wired to the board.

An off-board part is one thing bought, as the parts list counts it (D-203: a pot however
many gangs, a switch however many poles, the guitar's and amp's jacks when none is drawn),
plus *Power*, the supplies the board needs that no drawn battery or DC jack brings. Each
has its lugs, each lug an end a wire starts from: a circuit part's pin (`VR1.2`,
`VR1A.3`, `SW1.1`), a jack's sleeve the schematic doesn't draw (`IN.S`), or a supply
(`V+`, `GND`). Pure, from the circuit and its nets.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from solum.circuit.connectivity import GROUND, Nets
from solum.circuit.parts import pin_offsets
from solum.circuit.schema import AmpInput, Battery, Circuit, DcJack, Guitar, Part, Pot, Switch
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
    list has them; `lugs` in order; `size` its drawing's (columns, strips) in holes."""

    ref: str
    name: str
    kind: str
    value: str
    details: str
    lugs: tuple[Lug, ...]

    @property
    def size(self) -> Hole:
        return (max(3, LUG_GAP * len(self.lugs) + 1), 3)


def _lug_label(part: Part, pin: str, several: bool) -> str:
    """A lug's label: its pin ("2", "T", "+"), with the gang or pole when the item has
    several ("A2"); a guitar's or amp's signal pin is its jack's tip."""
    label = "T" if isinstance(part, Guitar | AmpInput) and pin in ("out", "in") else pin
    label = "R" if isinstance(part, Guitar) and pin == "ring" else label
    return f"{part.ref[-1]}{label}" if several else label


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
            items.append(OffItem(base, named, _kind(parts), line.value, line.details,
                                 tuple(lugs)))  # fmt: skip
    carried = {nets.net_of(*pin) for part in board.values() for pin in part.pins.values()}
    supplies = sorted({*circuit.power.rails, GROUND} & carried - brought,
                      key=lambda s: (s == GROUND, s))  # fmt: skip
    if supplies:
        items.append(OffItem(POWER, "Power", "power", "", "the supply's wires",
                             tuple(Lug(s, s, s) for s in supplies)))  # fmt: skip
    return items


def lug_nets(items: Iterable[OffItem]) -> dict[str, str]:
    """Every lug's end → its net."""
    return {lug.end: lug.net for item in items for lug in item.lugs}


def _natural(text: str) -> list[object]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def default_spots(items: list[OffItem], layout: Layout) -> dict[str, Hole]:
    """Where each off-board part is drawn when it hasn't been put anywhere (spec, *Wire it
    for me*): pots and the rest along the top in knob order, the input jack at the right,
    the output at the left, *Power* at the bottom left corner; each spot its drawing's top
    left hole, clear of the board's margin."""
    spots: dict[str, Hole] = {}
    above = -MARGIN - GAP
    left = -MARGIN - GAP
    right = layout.columns + MARGIN + GAP - 1
    column = 0
    for item in sorted(items, key=lambda i: (i.kind != "pot", _natural(i.ref))):
        width, height = item.size
        if item.ref == "IN":
            spots[item.ref] = (right, 0)
        elif item.ref == "OUT":
            spots[item.ref] = (left - width + 1, 0)
        elif item.ref == POWER:
            spots[item.ref] = (left - width + 1, layout.strips + MARGIN + GAP - 1)
        else:
            spots[item.ref] = (column, above - height + 1)
            column += width + GAP
    return spots
