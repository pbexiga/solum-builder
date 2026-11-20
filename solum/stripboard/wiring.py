"""*Wire it for me* (spec, *Off-board parts and wires*; D-375): every off-board part not
yet beside the board put at its default spot, and every lug still to wire given a wire to
the nearest free hole on a strip that carries its net and no other; a lug whose net isn't
on the board yet is wired to another lug of its net that is (or will be) wired, if any.
Never moves a part or a wire already there; the same board always wires the same way.
"""

import math
from dataclasses import replace

from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import Hole, Layout, Wire
from solum.stripboard.check import groups_by_net, joined_groups, read_layout
from solum.stripboard.offboard import LUG_GAP, OffItem, default_spots
from solum.stripboard.size import used_holes


class WiringError(ValueError):
    """Nothing could be wired (plain-English message, says why)."""


def _lug_holes(items: list[OffItem], spots: dict[str, Hole]) -> dict[str, tuple[float, float]]:
    """Where each lug is drawn, in holes (offboard's drawing: lugs along the bottom)."""
    found: dict[str, tuple[float, float]] = {}
    for item in items:
        column, strip = spots[item.ref]
        for i, lug in enumerate(item.lugs):
            found[lug.end] = (column + 1 + LUG_GAP * i, strip + item.size[1] - 1)
    return found


def wire_for_me(layout: Layout, circuit: Circuit, models: ModelLibrary,
                table: FootprintTable) -> Layout:  # fmt: skip
    """`layout` with its off-board parts beside it and its lugs wired (module doc)."""
    r = read_layout(layout, circuit, models, table)
    spots = {**default_spots(r.items, layout), **dict(layout.spots)}
    kept = dict(layout.spots)
    for item in r.items:
        kept.setdefault(item.ref, spots[item.ref])
    places = _lug_holes(r.items, spots)
    holes, _ = joined_groups(r.layout)
    clean = {g: next(iter(nets)) for g, nets in groups_by_net(r).items() if len(nets) == 1}
    taken = set(used_holes(layout, r.board))
    wired = {t for t in r.groups if isinstance(t, str)}
    anchors: set[str] = set()  # lugs of a net not on the board, the next of its net comes to
    loose = {w.lug for w in layout.wires if w.hole is None and w.to is None}
    wires = [w for w in layout.wires if not (w.hole is None and w.to is None)]
    added = 0
    for item in r.items:
        for lug in item.lugs:
            if lug.end not in r.needed or lug.end in wired:
                continue
            x, y = places[lug.end]
            free = [h for h, g in holes.items() if clean.get(g) == lug.net and h not in taken]
            if free:
                hole = min(free, key=lambda h: (math.hypot(h[0] - x, h[1] - y), h[1], h[0]))
                wires.append(Wire(lug.end, hole))
                taken.add(hole)
            else:
                mates = sorted(e for e in wired | anchors if r.ends.get(e) == lug.net)
                if not mates:
                    anchors.add(lug.end)
                    continue
                wires.append(Wire(lug.end, None, mates[0]))
            wired.add(lug.end)
            added += 1
    wires += [w for w in layout.wires if w.lug in loose and w.lug not in wired]
    if not added and kept == dict(layout.spots):
        raise WiringError(
            "Nothing to wire: every lug is wired, or its net isn't on the board yet "
            "(place the parts first)."
        )
    return replace(layout, wires=tuple(wires), spots=tuple(kept.items()))
