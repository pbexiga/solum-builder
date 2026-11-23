"""The board's size (spec, *Board size*; D-372): the board is what's on it.

What's used is every leg, body, cut, link and pad (as the check counts them); the board is
the box round them. Adding at the top or left moves everything along one hole, so hole
names follow the board as it ends up. All pure: a `Layout` in, a `Layout` or a sentence out.
"""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from typing import Literal

from solum.stripboard.board import PITCH, Hole, Layout, Link, Placed, column_name, hole_name
from solum.stripboard.footprints import BoardPart, body_holes, leg_problem

Axis = Literal["column", "strip"]
Box = tuple[int, int, int, int]  # first column, first strip, last column, last strip
START_AREA = 2.5  # an empty board's holes, per hole its parts take (spec)
START_SHAPE = 1.5  # an empty board's columns per strip: wider than tall
START_LEAST = (10, 6)  # an empty board's least columns and strips


class SizeError(ValueError):
    """A size change that can't be made (plain-English message, says why)."""


def used_holes(layout: Layout, board: Mapping[str, BoardPart]) -> dict[Hole, str]:
    """Every hole something is in or over, with what it is (for the sentences): legs and
    bodies by the part's ref, cuts, link ends and the holes a link passes over, pads."""
    used: dict[Hole, str] = {}
    for placed in layout.parts:
        legs = placed.holes
        part = board.get(placed.ref)
        for hole in (body_holes(part, legs, placed.standing) if part else set()) | set(
            legs.values()
        ):
            used[hole] = placed.ref
    for cut in layout.cuts:
        used.setdefault(cut, f"the cut at {hole_name(cut)}")
    for link in layout.links:
        name = f"the link from {hole_name(link.a)} to {hole_name(link.b)}"
        for hole in (link.a, link.b, *link.between):
            used.setdefault(hole, name)
    for pad in layout.pads:
        used.setdefault(pad, f"the wire at {hole_name(pad)}")
    return used


def used_box(layout: Layout, board: Mapping[str, BoardPart]) -> Box | None:
    """The box round `used_holes` (quicker: no sentences; a link's holes lie between its
    ends). None when nothing's on the board."""
    holes: list[Hole] = [*layout.cuts, *layout.pads]
    holes += (h for link in layout.links for h in (link.a, link.b))
    for placed in layout.parts:
        legs = placed.holes
        part = board.get(placed.ref)
        holes += legs.values()
        if part:
            holes += body_holes(part, legs, placed.standing)
    return box(holes)


def box(holes: Iterable[Hole]) -> Box | None:
    """The box round some holes (a set, or a mapping's keys); None when there are none."""
    found = list(holes)
    if not found:
        return None
    columns = [h[0] for h in found]
    strips = [h[1] for h in found]
    return min(columns), min(strips), max(columns), max(strips)


def _moved(layout: Layout, move: Callable[[Hole], Hole]) -> Layout:
    """Every hole on the layout through `move` (its size unchanged)."""
    return replace(
        layout,
        parts=tuple(
            replace(p, legs=tuple((leg, move(h)) for leg, h in p.legs)) for p in layout.parts
        ),
        cuts=frozenset(move(h) for h in layout.cuts),
        links=tuple(Link(move(link.a), move(link.b)) for link in layout.links),
        wires=tuple(
            replace(w, hole=move(w.hole)) if w.hole is not None else w for w in layout.wires
        ),
        spots=tuple((ref, move(at)) for ref, at in layout.spots),
    )


def crop(layout: Layout, keep: Box) -> Layout:
    """The layout with `keep` as its whole board, everything moved so its corner is A1."""
    c0, s0, c1, s1 = keep
    moved = _moved(layout, lambda h: (h[0] - c0, h[1] - s0))
    return replace(moved, columns=c1 - c0 + 1, strips=s1 - s0 + 1)


def fit_box(before: Layout | None, after: Layout, board: Mapping[str, BoardPart]) -> Box | None:
    """The box, in `after`'s holes, that auto-grow makes the board (D-372): grown to take
    in everything on it, and shrunk at an edge only by the lines this edit emptied, so
    lines added by hand stay. `before` None (the first placement on an empty board): just
    what's on it. None when nothing is left on it (its size kept)."""
    used = used_box(after, board)
    if used is None or before is None:
        return used
    was = used_holes(before, board)
    c0, s0 = min(0, used[0]), min(0, used[1])
    c1, s1 = max(after.columns - 1, used[2]), max(after.strips - 1, used[3])

    def emptied(axis: int, line: int) -> bool:
        return any(h[axis] == line for h in was)

    while c0 < used[0] and emptied(0, c0):
        c0 += 1
    while c1 > used[2] and emptied(0, c1):
        c1 -= 1
    while s0 < used[1] and emptied(1, s0):
        s0 += 1
    while s1 > used[3] and emptied(1, s1):
        s1 -= 1
    return c0, s0, c1, s1


def fit(before: Layout | None, after: Layout, board: Mapping[str, BoardPart]) -> Layout:
    """`after` (an edit of `before`, in its holes; a leg may sit off it, in the margin)
    with auto-grow (`fit_box`), everything moved so the board's corner is A1. Nothing
    left on it: its size kept (an empty board, the margin round it)."""
    keep = fit_box(before, after, board)
    return after if keep is None else crop(after, keep)


def trim(layout: Layout, board: Mapping[str, BoardPart]) -> Layout:
    """The empty columns and strips at the edges taken off (inside ones stay: taking those
    out moves parts, *Tidy up*'s job). An empty board can't be trimmed."""
    used = used_box(layout, board)
    if used is None:
        raise SizeError("There's nothing on the board to trim it to.")
    return crop(layout, used)


def line_name(axis: Axis, line: int) -> str:
    """Column 5 → "column F", strip 6 → "strip 7"."""
    return f"column {column_name(line)}" if axis == "column" else f"strip {line + 1}"


def _stretched(layout: Layout, board: Mapping[str, BoardPart], move: Callable[[Hole], Hole],
               words: str) -> Layout:  # fmt: skip
    """The layout moved; a part whose legs end up as its footprint doesn't allow (a chip
    split by a new line, a resistor squeezed shorter than its body) refuses it."""
    moved = _moved(layout, move)
    for old, new in zip(layout.parts, moved.parts, strict=True):
        part = board.get(new.ref)
        if part is None or old.legs == new.legs:
            continue
        if _shape_changed(old, new) and leg_problem(part, new.holes, new.standing):
            raise SizeError(f"{words} would go through {new.ref}: move it first.")
    return moved


def _shape_changed(old: Placed, new: Placed) -> bool:
    """Whether the legs moved apart or together, not just along."""
    (_, a), *rest = old.legs
    (_, b), *more = new.legs
    first = (b[0] - a[0], b[1] - a[1])
    return any(
        (y[0] - x[0], y[1] - x[1]) != first for (_, x), (_, y) in zip(rest, more, strict=True)
    )


def insert_line(layout: Layout, board: Mapping[str, BoardPart], axis: Axis, at: int) -> Layout:
    """An empty column or strip put in before line `at` (0: at the left or top edge; the
    board's size: at the right or bottom), everything from `at` on moving along one hole.
    A part whose legs straddle it stretches when its footprint allows (a resistor), and
    refuses it when not (a chip); a link across a new strip gets longer."""
    size = layout.columns if axis == "column" else layout.strips
    if not 0 <= at <= size:
        raise SizeError(f"There's no {line_name(axis, at)} to insert before.")
    i = 0 if axis == "column" else 1

    def move(h: Hole) -> Hole:
        if h[i] < at:
            return h
        return (h[0] + 1, h[1]) if i == 0 else (h[0], h[1] + 1)

    edge = "A new line here" if at in (0, size) else f"A new line before {line_name(axis, at)}"
    moved = _stretched(layout, board, move, edge)
    grown = (layout.columns + 1, layout.strips) if i == 0 else (layout.columns, layout.strips + 1)
    return replace(moved, columns=grown[0], strips=grown[1])


def remove_line(layout: Layout, board: Mapping[str, BoardPart], axis: Axis, at: int) -> Layout:
    """An empty column or strip taken out, everything past it moving back one hole. Not
    empty (a leg, a body, a cut in a column, a pad) is refused, naming what's there; a link
    passing over a strip shortens, a part straddling it squeezes when its footprint
    allows. Cuts on a removed strip go with it."""
    size = layout.columns if axis == "column" else layout.strips
    name = line_name(axis, at)
    if not 0 <= at < size:
        raise SizeError(f"There's no {name} on the board.")
    if size == 1:
        raise SizeError(f"The board needs at least one {axis}.")
    i = 0 if axis == "column" else 1
    passing = {h for link in layout.links for h in link.between} if i == 1 else set()
    across = {  # parts with legs either side: their bodies may squeeze
        p.ref for p in layout.parts
        if any(h[i] < at for _, h in p.legs) and any(h[i] > at for _, h in p.legs)
    }  # fmt: skip
    for hole, what in sorted(
        used_holes(layout, board).items(), key=lambda kv: (kv[0][1], kv[0][0])
    ):
        if hole[i] != at or hole in passing or what in across:
            continue
        if i == 1 and hole in layout.cuts:
            continue
        raise SizeError(f"{name[0].upper()}{name[1:]} isn't empty: {what} is on it.")

    def move(h: Hole) -> Hole:
        if h[i] <= at:
            return h
        return (h[0] - 1, h[1]) if i == 0 else (h[0], h[1] - 1)

    kept = replace(layout, cuts=frozenset(h for h in layout.cuts if h[i] != at))
    moved = _stretched(kept, board, move, f"Taking out {name}")
    shrunk = (layout.columns - 1, layout.strips) if i == 0 else (layout.columns, layout.strips - 1)
    return replace(moved, columns=shrunk[0], strips=shrunk[1])


def _holes_taken(part: BoardPart) -> int:
    """About how many holes a part takes on the board: its legs' line and its body."""
    fp = part.footprint
    if fp.shape == "dip":
        return (len(fp.order) // 2) * (fp.row_holes + 1)
    if fp.shape == "axial":
        return fp.flat + 1
    if fp.diameter:
        across = math.ceil(fp.diameter / PITCH)
        return max(across * across, len(part.legs))
    if fp.length:
        return math.ceil(fp.length / PITCH) * max(1, math.ceil(fp.width / PITCH))
    return len(part.legs)


def start_size(board: Mapping[str, BoardPart]) -> tuple[int, int]:
    """An empty board's columns and strips, so there's room to start: about two and a half
    times the holes its parts take, wider than tall (spec, *Board size*)."""
    area = START_AREA * sum(_holes_taken(p) for p in board.values())
    columns = max(START_LEAST[0], math.ceil(math.sqrt(area * START_SHAPE)))
    strips = max(START_LEAST[1], math.ceil(area / columns))
    return columns, strips
