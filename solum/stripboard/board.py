"""The stripboard and what's on it (D-367): pure data, no circuit.

A grid of holes 0.1" apart; the copper strips run along the rows. A hole is (column,
strip), both from 0; on paper the columns are lettered and the strips numbered from 1,
so (5, 6) is F7. A part is its legs in holes; a cut takes the copper off one hole, which
splits its strip there (and holds no leg); a link is a wire along a column joining two
holes. Off-board parts sit beside the board at a spot (any hole, on or off it, as drawn)
and are joined to it by wires: from a lug to a hole (its pad), lug to lug, or loose
(D-375). Where two bodies touch, the builder's decision is kept with the board: stand one
taller, bend it out of the way, or accept it (P6h4).
"""

import re
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Any, Literal, get_args

Hole = tuple[int, int]  # (column, strip), from 0
PITCH = 2.54  # mm between holes (0.1")


def column_name(column: int) -> str:
    """0 → A, 25 → Z, 26 → AA; "" off the board's left (a hole in the margin)."""
    name = ""
    column += 1
    while column > 0:
        column, rest = divmod(column - 1, 26)
        name = ascii_uppercase[rest] + name
    return name


def hole_name(hole: Hole) -> str:
    """(5, 6) → "F7": the column's letters, the strip's number."""
    return f"{column_name(hole[0])}{hole[1] + 1}"


_HOLE = re.compile(r"([A-Z]+)([1-9][0-9]*)")


class BoardError(ValueError):
    """A layout's data can't be read (plain-English message)."""


def parse_hole(name: str) -> Hole:
    """ "F7" → (5, 6)."""
    found = _HOLE.fullmatch(name.strip().upper())
    if not found:
        raise BoardError(f"{name!r} isn't a hole: write its column and strip, like F7.")
    column = 0
    for letter in found.group(1):
        column = column * 26 + ascii_uppercase.index(letter) + 1
    return (column - 1, int(found.group(2)) - 1)


@dataclass(frozen=True)
class Placed:
    """A part on the board: `ref` is a part's (R1, Q1) or a chip's (IC1, all its units);
    `legs` its leg names (the part's pins; a chip's pin numbers, "1" to "8") in holes;
    `standing` for a two-leg axial part stood up."""

    ref: str
    legs: tuple[tuple[str, Hole], ...]
    standing: bool = False

    @property
    def holes(self) -> dict[str, Hole]:
        return dict(self.legs)


@dataclass(frozen=True)
class Link:
    """A wire jumper along a column, from hole `a` to hole `b`."""

    a: Hole
    b: Hole

    @property
    def between(self) -> list[Hole]:
        """The holes it passes over, its ends left out."""
        (column, top), (_, bottom) = sorted((self.a, self.b), key=lambda h: h[1])
        return [(column, strip) for strip in range(top + 1, bottom)]


@dataclass(frozen=True)
class Wire:
    """An off-board wire from `lug` (an off-board part's lug: `VR1.1`, `IN.out`, `IN.S`, or
    a supply, `V+`, `GND`) to a hole on the board (`hole`, its pad), to another lug (`to`),
    or loose (neither). `runs`: its drawn route's middle runs moved by hand, each (run
    number, where in holes), drawing only (D-380)."""

    lug: str
    hole: Hole | None = None
    to: str | None = None
    runs: tuple[tuple[int, float], ...] = ()


EDGE = "edge"  # the other side of a body hanging past the board's edge, in a `Decision`
Fix = Literal["taller", "bent", "accept"]
Side = Literal["left", "right", "up", "down"]  # as the parts side shows the board


@dataclass(frozen=True)
class Decision:
    """The builder's decision on two bodies touching (D-394), or one past the board's edge
    (`parts[1]` is `EDGE`): `fix` stand `part` taller (by `mm`, if said), bend `part`
    `toward` a side, or accept it; `note` their own words. `overlap_mm`, the amount it was
    decided at: an overlap by another amount is a new one (the user, 2026-11-24)."""

    parts: tuple[str, str]
    fix: Fix
    overlap_mm: float
    part: str | None = None
    mm: float | None = None
    toward: Side | None = None
    note: str = ""


def decision_problem(d: Decision) -> str | None:
    """Why a decision can't be kept, in a sentence; None when it can."""
    a, b = d.parts
    if not a or not b or a in (b, EDGE):
        return "An overlap's decision names the two parts that touch, or a part and the edge."
    if d.fix not in get_args(Fix):
        return f"{a} and {b}: stand one taller, bend one out of the way, or accept it."
    if b == EDGE and d.fix != "accept":
        return f"{a} hangs past the board's edge: accept it with a note, or move it in."
    if d.fix != "accept" and d.part not in (a, b):
        return f"Say which of {a} and {b} to {'stand taller' if d.fix == 'taller' else 'bend'}."
    if d.fix == "bent" and d.toward not in get_args(Side):
        return f"Say which way {d.part} bends: left, right, up or down."
    if d.mm is not None and (d.fix != "taller" or d.mm <= 0):
        return "How much taller is a length in mm, above 0, for a part stood taller."
    if (d.toward is not None and d.fix != "bent") or (d.part is not None and d.fix == "accept"):
        return f"{a} and {b}: an accepted overlap names no part or side."
    if d.overlap_mm < 0:
        return "An overlap's amount is 0 mm or more."
    return None


def decision_from_data(data: Mapping[str, Any]) -> Decision:
    """A decision from its plain form (`{parts: [C5, TR1], fix: taller, part: C5, mm: 3,
    overlap_mm: 0.3}`), or a `BoardError` saying what's wrong with it."""
    a, b = (str(r) for r in data["parts"])
    mm, part, toward = data.get("mm"), data.get("part"), data.get("toward")
    found = Decision((a, b), data["fix"], round(float(data["overlap_mm"]), 1),
                     None if part is None else str(part),
                     None if mm is None else float(mm), toward,
                     str(data.get("note") or ""))  # fmt: skip
    why = decision_problem(found)
    if why:
        raise BoardError(why)
    return found


def decision_data(d: Decision) -> dict[str, Any]:
    """A decision's plain form, what's unsaid left out."""
    found: dict[str, Any] = {"parts": list(d.parts), "fix": d.fix}
    found |= {k: v for k, v in (("part", d.part), ("mm", d.mm), ("toward", d.toward)) if v}
    if d.note:
        found["note"] = d.note
    return found | {"overlap_mm": d.overlap_mm}


@dataclass(frozen=True)
class Layout:
    columns: int
    strips: int
    parts: tuple[Placed, ...]
    cuts: frozenset[Hole] = frozenset()
    links: tuple[Link, ...] = ()
    wires: tuple[Wire, ...] = ()
    spots: tuple[tuple[str, Hole], ...] = ()  # each off-board part put beside the board
    where: tuple[tuple[str, str], ...] = ()  # a part moved on or off the board by choice
    overlaps: tuple[Decision, ...] = ()  # the builder's decisions on bodies touching (P6h4)

    @property
    def pads(self) -> list[Hole]:
        """The holes wires are soldered into."""
        return [w.hole for w in self.wires if w.hole is not None]

    def on_board(self, hole: Hole) -> bool:
        return 0 <= hole[0] < self.columns and 0 <= hole[1] < self.strips


def segments(layout: Layout, holes: Iterable[Hole] | None = None) -> dict[Hole, int]:
    """Each copper hole's strip segment: the holes of a strip between cuts (and the board's
    ends) share a number, counted strip by strip from the top left. Cut holes have none.
    `holes`: only these (a quick answer on a big board; those off it or cut left out)."""
    found: dict[Hole, int] = {}
    if holes is None:
        number = 0
        for strip in range(layout.strips):
            number += 1
            for column in range(layout.columns):
                if (column, strip) in layout.cuts:
                    number += 1
                    continue
                found[(column, strip)] = number
        return found
    cuts: dict[int, list[int]] = {}
    for c, s in sorted(layout.cuts):
        if layout.on_board((c, s)):
            cuts.setdefault(s, []).append(c)
    first, number = [], 0  # each strip's first segment's number, as the loop above counts
    for strip in range(layout.strips):
        first.append(number + 1)
        number += 1 + len(cuts.get(strip, ()))
    for hole in holes:
        if layout.on_board(hole) and hole not in layout.cuts:
            found[hole] = first[hole[1]] + bisect_left(cuts.get(hole[1], ()), hole[0])
    return found


def _holes(data: Iterable[str]) -> list[Hole]:
    return [parse_hole(h) for h in data]


def layout_from_data(data: Mapping[str, Any]) -> Layout:
    """A layout from its plain form: `{size: [columns, strips], parts: {R1: {1: B2, 2:
    B6}, ...}, standing: [R2], cuts: [F7], links: [[A1, A4]], wires: [{from: VR1.1, hole:
    A1}, {from: VR1.3, lug: IN.S}, {from: V+}], off: {VR1: [2, -6]}, where: {R5:
    off-board}, overlaps: [{parts: [C5, TR1], fix: accept, overlap_mm: 0.3}]}`, holes by
    name but
    an off-board part's spot (it may be off the board) as [column, strip] (the form a
    test or the circuit file writes)."""
    try:
        columns, strips = (int(n) for n in data["size"])
        standing = set(data.get("standing", ()))
        parts = tuple(
            Placed(
                str(ref),
                tuple((str(leg), parse_hole(h)) for leg, h in legs.items()),
                str(ref) in standing,
            )
            for ref, legs in data.get("parts", {}).items()
        )
        links = tuple(Link(*_holes(pair)) for pair in data.get("links", ()))
        wires = tuple(_wire(w) for w in data.get("wires", ()))
        spots = tuple((str(ref), (int(at[0]), int(at[1])))
                      for ref, at in data.get("off", {}).items())  # fmt: skip
        where = tuple((str(ref), str(at)) for ref, at in data.get("where", {}).items())
        overlaps = tuple(decision_from_data(d) for d in data.get("overlaps") or ())
        return Layout(columns, strips, parts, frozenset(_holes(data.get("cuts", ()))), links,
                      wires, spots, where, overlaps)  # fmt: skip
    except (KeyError, TypeError, ValueError) as err:
        if isinstance(err, BoardError):
            raise
        raise BoardError("The stripboard layout's data is incomplete or malformed.") from None


def _wire(data: Mapping[str, Any]) -> Wire:
    hole, to = data.get("hole"), data.get("lug")
    if hole is not None and to is not None:
        raise BoardError("A wire goes from its lug to a hole or to another lug, not both.")
    runs = tuple((int(i), float(at)) for i, at in data.get("runs", ()))
    return Wire(str(data["from"]), parse_hole(hole) if hole is not None else None,
                str(to) if to is not None else None, runs)  # fmt: skip


def wire_data(wire: Wire) -> dict[str, Any]:
    """A wire's plain form: `{from: VR1.1, hole: A1}`, `{from: .., lug: ..}`, `{from: ..}`;
    `runs: [[2, -1.3]]` when its route was moved by hand (D-380)."""
    found: dict[str, Any] = {"from": wire.lug}
    if wire.hole is not None:
        found["hole"] = hole_name(wire.hole)
    if wire.to is not None:
        found["lug"] = wire.to
    if wire.runs:
        found["runs"] = [[i, at] for i, at in wire.runs]
    return found


def layout_data(layout: Layout) -> dict[str, Any]:
    """The plain form `layout_from_data` reads: holes by name, in a stable order."""
    return {
        "size": [layout.columns, layout.strips],
        "parts": {p.ref: {leg: hole_name(h) for leg, h in p.legs} for p in layout.parts},
        "standing": [p.ref for p in layout.parts if p.standing],
        "cuts": [hole_name(h) for h in sorted(layout.cuts, key=lambda h: (h[1], h[0]))],
        "links": [[hole_name(link.a), hole_name(link.b)] for link in layout.links],
        "wires": [wire_data(w) for w in layout.wires],
        "off": {ref: list(at) for ref, at in layout.spots},
        "where": dict(layout.where),
        "overlaps": [decision_data(d) for d in layout.overlaps],
    }
