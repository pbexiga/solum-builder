"""Editing the board by hand (D-374): a part placed, moved or taken back to the tray, a cut
made or mended, a link laid or lifted. Each edit is applied to the layout and refused, in a
sentence, when it can't be made: legs as the footprint doesn't allow, two things in a hole,
a body over a leg, past the board's edge with auto-grow off. With auto-grow on the board
then fits what's on it (`size.fit_box`). Pure: a `Layout` in, a `Layout` or a sentence out;
whether an edit makes a short is the check's (`check.shorts`), asked by the caller.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

from solum.stripboard.board import Hole, Layout, Link, Placed, hole_name
from solum.stripboard.check import placement_faults
from solum.stripboard.footprints import BoardPart, leg_problem
from solum.stripboard.size import crop, fit_box, used_holes

EditKind = Literal["place", "remove", "cut", "uncut", "link", "unlink"]


class EditError(ValueError):
    """A board edit that can't be made (plain-English message, says why)."""


@dataclass(frozen=True)
class BoardEdit:
    """One edit: `place` puts `ref` with `legs` (and `standing`) on the board, moving it
    when it's already there; `remove` takes `ref` back to the tray; `cut` / `uncut` a cut
    at `holes[0]`; `link` / `unlink` a link from `holes[0]` to `holes[1]`. Holes may be in
    the margin round the board (negative, or past its size)."""

    kind: EditKind
    ref: str = ""
    legs: tuple[tuple[str, Hole], ...] = ()
    standing: bool = False
    holes: tuple[Hole, ...] = ()


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
    in_hole |= {p.hole for p in layout.pads}
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


def _applied(layout: Layout, edit: BoardEdit, board: Mapping[str, BoardPart]) -> Layout:
    holes = edit.holes
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
                started: bool, grow: bool) -> Edited:  # fmt: skip
    """`layout` with `edit` made. `started`: the board has been saved before (an empty one
    is drawn at its start size and becomes just what's on it at the first placement).
    `grow`: auto-grow (D-372): the board fits what's on it; off, an edit past its edge is
    refused. A placement fault the edit brings (two things in a hole, a body over a leg, a
    link over a leg) refuses it, named."""
    after = _applied(layout, edit, board)
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
