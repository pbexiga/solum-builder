"""Editing the board by hand (D-374): a part placed, moved or taken back to the tray, a cut
made or mended, a link laid or lifted; an off-board part put beside the board or back in
the tray, a wire drawn, moved or taken off (D-375). Each edit is applied to the layout and
refused, in a sentence, when it can't be made: legs as the footprint doesn't allow, two
things in a hole, a body over a leg, past the board's edge with auto-grow off. With
auto-grow on the board then fits what's on it (`size.fit_box`). Pure: a `Layout` in, a
`Layout` or a sentence out; whether an edit makes a short is the check's (`check.shorts`),
asked by the caller.
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from typing import Literal

from solum.stripboard.board import Hole, Layout, Link, Placed, Wire, hole_name
from solum.stripboard.check import placement_faults
from solum.stripboard.footprints import BoardPart, leg_problem
from solum.stripboard.size import crop, fit_box, used_holes

EditKind = Literal["place", "remove", "cut", "uncut", "link", "unlink", "spot", "unspot",
                   "wire", "unwire", "rewire", "route", "clear"]  # fmt: skip


class EditError(ValueError):
    """A board edit that can't be made (plain-English message, says why)."""


@dataclass(frozen=True)
class BoardEdit:
    """One edit: `place` puts `ref` with `legs` (and `standing`) on the board, moving it
    when it's already there; `remove` takes `ref` back to the tray; `cut` / `uncut` a cut
    at `holes[0]`; `link` / `unlink` a link from `holes[0]` to `holes[1]`. Holes may be in
    the margin round the board (negative, or past its size). Off the board (D-375): `spot`
    puts off-board part `ref` with its drawing's corner at `holes[0]` (anywhere), `unspot`
    takes it back to the tray with its wires; `wire` draws a wire from lug `ref` to
    `holes[0]`, to lug `to`, or loose (neither); `rewire` puts wire number `index` so
    instead (its route automatic again), `unwire` takes it off; `route` sets wire `index`'s
    middle runs moved by hand to `runs` (none: routed automatically, D-380). `clear` takes
    off everything of parts the circuit no longer has (D-376): placed parts, off-board parts
    beside the board, wires to their lugs."""

    kind: EditKind
    ref: str = ""
    legs: tuple[tuple[str, Hole], ...] = ()
    standing: bool = False
    holes: tuple[Hole, ...] = ()
    to: str | None = None
    index: int = -1
    runs: tuple[tuple[int, float], ...] = ()


@dataclass(frozen=True)
class Edited:
    """The board after an edit, and `shift`: how far every hole moved when the board grew
    or shrank at its top or left (added to each hole's column and strip), so the page can
    keep the drawing still."""

    layout: Layout
    shift: Hole = (0, 0)


def _name(hole: Hole) -> str:
    return hole_name(hole) if hole[0] >= 0 and hole[1] >= 0 else "the margin"


def _place(layout: Layout, edit: BoardEdit, board: Mapping[str, BoardPart]) -> Layout:
    part = board.get(edit.ref)
    if part is None:
        raise EditError(f"{edit.ref} doesn't go on the board.")
    placed = Placed(edit.ref, edit.legs, edit.standing)
    problem = leg_problem(part, placed.holes, edit.standing)
    if problem:
        raise EditError(problem)
    others = tuple(p for p in layout.parts if p.ref != edit.ref)
    if len(others) == len(layout.parts):
        return replace(layout, parts=(*layout.parts, placed))
    return replace(layout, parts=tuple(placed if p.ref == edit.ref else p for p in layout.parts))


def _remove(layout: Layout, ref: str) -> Layout:
    parts = tuple(p for p in layout.parts if p.ref != ref)
    if len(parts) == len(layout.parts):
        raise EditError(f"{ref} isn't on the board.")
    return replace(layout, parts=parts)


def _cut(layout: Layout, hole: Hole, board: Mapping[str, BoardPart]) -> Layout:
    if not layout.on_board(hole):
        raise EditError("A cut goes in a hole on the board.")
    if hole in layout.cuts:
        raise EditError(f"There's a cut at {hole_name(hole)} already.")
    in_hole = {h for p in layout.parts for _, h in p.legs}
    in_hole |= {h for link in layout.links for h in (link.a, link.b)}
    in_hole |= set(layout.pads)
    if hole in in_hole:
        what = used_holes(layout, board)[hole]
        raise EditError(
            f"{what[:1].upper()}{what[1:]} is in {hole_name(hole)}: a cut there would take "
            "its copper away. Move it first."
        )
    return replace(layout, cuts=layout.cuts | {hole})


def _uncut(layout: Layout, hole: Hole) -> Layout:
    if hole not in layout.cuts:
        raise EditError(f"There's no cut at {_name(hole)}.")
    return replace(layout, cuts=layout.cuts - {hole})


def _link(layout: Layout, a: Hole, b: Hole) -> Layout:
    if a[0] != b[0] or a[1] == b[1]:
        raise EditError("A link runs down a column, from one strip to another.")
    return replace(layout, links=(*layout.links, Link(a, b)))


def _unlink(layout: Layout, a: Hole, b: Hole) -> Layout:
    links = tuple(link for link in layout.links if {link.a, link.b} != {a, b})
    if len(links) == len(layout.links):
        raise EditError(f"There's no link from {_name(a)} to {_name(b)}.")
    return replace(layout, links=links)


def _spot(layout: Layout, edit: BoardEdit, items: Mapping[str, tuple[str, ...]]) -> Layout:
    if edit.ref not in items:
        raise EditError(f"{edit.ref} isn't an off-board part of this circuit.")
    if len(edit.holes) != 1:
        raise EditError("An off-board part is put in one spot.")
    spots = dict(layout.spots)
    spots[edit.ref] = edit.holes[0]
    return replace(layout, spots=tuple(spots.items()))


def _unspot(layout: Layout, ref: str, items: Mapping[str, tuple[str, ...]]) -> Layout:
    lugs = set(items.get(ref, ()))
    spots = tuple((r, at) for r, at in layout.spots if r != ref)
    wires = tuple(w for w in layout.wires if w.lug not in lugs and w.to not in lugs)
    if spots == layout.spots and wires == layout.wires:
        raise EditError(f"{ref} isn't beside the board.")
    return replace(layout, spots=spots, wires=wires)


def _clear(layout: Layout, keep: AbstractSet[str],
           items: Mapping[str, tuple[str, ...]]) -> Layout:  # fmt: skip
    lugs = {lug for ends in items.values() for lug in ends}
    cleared = replace(
        layout,
        parts=tuple(p for p in layout.parts if p.ref in keep),
        spots=tuple((ref, at) for ref, at in layout.spots if ref in items),
        wires=tuple(w for w in layout.wires if w.lug in lugs and (w.to is None or w.to in lugs)),
    )
    if cleared == layout:
        raise EditError("Nothing on the board is gone from the circuit.")
    return cleared


def _new_wire(layout: Layout, edit: BoardEdit, lugs: set[str], skip: int = -1) -> Wire:
    """The wire `edit` draws, refused when a lug isn't one, it runs to itself, or it's
    there already."""
    for lug in (edit.ref, edit.to):
        if lug is not None and lug not in lugs:
            raise EditError(f"{lug!r} isn't a lug of an off-board part of this circuit.")
    if len(edit.holes) > 1 or (edit.holes and edit.to is not None):
        raise EditError("A wire goes from its lug to one hole or one other lug.")
    if edit.to == edit.ref:
        raise EditError("A wire runs from one lug to another, not back to itself.")
    wire = Wire(edit.ref, edit.holes[0] if edit.holes else None, edit.to)
    same = {(wire.lug, wire.hole, wire.to), (wire.to, None, wire.lug)}
    if wire.hole is not None or wire.to is not None:
        for i, w in enumerate(layout.wires):
            if i != skip and (w.lug, w.hole, w.to) in same:
                raise EditError("There's a wire there already.")
    return wire


def _runs(runs: tuple[tuple[int, float], ...]) -> tuple[tuple[int, float], ...]:
    """A wire's moved runs, one per run number (the last given kept), in order, where to a
    hundredth of a hole."""
    if any(i < 1 for i, _ in runs):
        raise EditError(
            "Only a wire's middle runs can be moved: its ends stay at its lug and hole."
        )
    return tuple(sorted({i: round(at, 2) for i, at in runs}.items()))


def _wire_at(layout: Layout, index: int) -> int:
    if not 0 <= index < len(layout.wires):
        raise EditError("There's no such wire.")
    return index


def _applied(layout: Layout, edit: BoardEdit, board: Mapping[str, BoardPart],
             items: Mapping[str, tuple[str, ...]], known: AbstractSet[str]) -> Layout:  # fmt: skip
    holes = edit.holes
    lugs = {lug for ends in items.values() for lug in ends}
    if edit.kind in ("cut", "uncut") and len(holes) != 1:
        raise EditError("A cut is in one hole.")
    if edit.kind in ("link", "unlink") and len(holes) != 2:
        raise EditError("A link has two ends.")
    match edit.kind:
        case "place":
            return _place(layout, edit, board)
        case "remove":
            return _remove(layout, edit.ref)
        case "cut":
            return _cut(layout, holes[0], board)
        case "uncut":
            return _uncut(layout, holes[0])
        case "link":
            return _link(layout, *holes)
        case "unlink":
            return _unlink(layout, *holes)
        case "spot":
            return _spot(layout, edit, items)
        case "unspot":
            return _unspot(layout, edit.ref, items)
        case "wire":
            return replace(layout, wires=(*layout.wires, _new_wire(layout, edit, lugs)))
        case "unwire":
            i = _wire_at(layout, edit.index)
            return replace(layout, wires=layout.wires[:i] + layout.wires[i + 1 :])
        case "clear":
            return _clear(layout, board.keys() | known, items)
        case "rewire":
            i = _wire_at(layout, edit.index)
            wire = _new_wire(layout, edit, lugs, skip=i)
            return replace(layout, wires=(*layout.wires[:i], wire, *layout.wires[i + 1 :]))
        case "route":
            i = _wire_at(layout, edit.index)
            wire = replace(layout.wires[i], runs=_runs(edit.runs))
            return replace(layout, wires=(*layout.wires[:i], wire, *layout.wires[i + 1 :]))


def _edge(layout: Layout, holes: set[Hole]) -> str | None:
    """Which edge of the board the holes go past, in words; None when all are on it."""
    past = [
        ("left", "column", any(h[0] < 0 for h in holes)),
        ("right", "column", any(h[0] >= layout.columns for h in holes)),
        ("top", "strip", any(h[1] < 0 for h in holes)),
        ("bottom", "strip", any(h[1] >= layout.strips for h in holes)),
    ]
    for edge, line, over in past:
        if over:
            return (
                f"That goes past the board's {edge} edge: turn Auto-grow on, or add a {line} "
                "on the rulers."
            )
    return None


def edit_layout(layout: Layout, edit: BoardEdit, board: Mapping[str, BoardPart], *,
                started: bool, grow: bool,
                items: Mapping[str, tuple[str, ...]] | None = None,
                known: AbstractSet[str] = frozenset()) -> Edited:  # fmt: skip
    """`layout` with `edit` made. `items`: each off-board part's lugs (D-375). `known`: the
    circuit's board parts that can't be placed now, which `clear` keeps (D-376). `started`:
    the board has been saved before (an empty one is drawn at its start size and becomes
    just what's on it at the first placement).
    `grow`: auto-grow (D-372): the board fits what's on it; off, an edit past its edge is
    refused. A placement fault the edit brings (two things in a hole, a body over a leg, a
    link over a leg) refuses it, named."""
    after = _applied(layout, edit, board, items or {}, known)
    if not grow:
        edge = _edge(after, set(used_holes(after, board)) - set(used_holes(layout, board)))
        if edge:
            raise EditError(edge)
    was = set(placement_faults(layout, dict(board), set()))
    for fault in placement_faults(after, dict(board), set()):
        if fault in was or fault.endswith((" isn't on the board.", ", off the board.")):
            continue
        raise EditError(fault)
    if not grow:
        return Edited(after)
    keep = fit_box(layout if started else None, after, board)
    if keep is None:
        return Edited(after)
    return Edited(crop(after, keep), (-keep[0], -keep[1]))
