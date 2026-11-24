"""The stripboard and what's on it (D-367): pure data, no circuit.

A grid of holes 0.1" apart; the copper strips run along the rows. A hole is (column,
strip), both from 0; on paper the columns are lettered and the strips numbered from 1,
so (5, 6) is F7. A part is its legs in holes; a cut takes the copper off one hole, which
splits its strip there (and holds no leg); a link is a wire along a column joining two
holes. Off-board parts sit beside the board at a spot (any hole, on or off it, as drawn)
and are joined to it by wires: from a lug to a hole (its pad), lug to lug, or loose
(D-375). The board keeps the builder's own notes, each naming parts or none, and the
overlap warnings they dismissed (D-398).
"""

import re
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Any, Literal

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


EDGE = "edge"  # the other side of a body hanging past the board's edge (D-394)
StandUp = Literal["never", "room", "prefer"]  # standing resistors and diodes (D-403)
STAND_UP: tuple[StandUp, ...] = ("never", "room", "prefer")


@dataclass(frozen=True)
class Note:
    """The builder's note on the board (D-398): `text`, about `parts` (refs; none: a
    general note); `overlap` when it was written from an overlap warning, so it goes out of
    date when those parts no longer touch. Never dropped by an edit."""

    text: str
    parts: tuple[str, ...] = ()
    overlap: bool = False


@dataclass(frozen=True)
class Dismissed:
    """An overlap warning the builder dismissed (D-398): two parts, or a part and `EDGE`,
    matched either way round, with their `reason`. It lapses when they no longer touch."""

    parts: tuple[str, str]
    reason: str = ""


def note_from_data(data: Mapping[str, Any]) -> Note:
    """A note from its plain form (`{parts: [C2, R1], text: …, overlap: true}`), or a
    `BoardError` saying what's wrong (its length is the file's to check: `schema`)."""
    text = str(data.get("text") or "").strip()
    if not text:
        raise BoardError("A note needs some text.")
    parts = tuple(dict.fromkeys(str(r).strip() for r in data.get("parts") or () if str(r).strip()))
    return Note(text, parts, bool(data.get("overlap")) and bool(parts))


def note_data(note: Note) -> dict[str, Any]:
    """A note's plain form, what's unsaid left out."""
    found: dict[str, Any] = {"parts": list(note.parts), "text": note.text}
    return found | ({"overlap": True} if note.overlap else {})


def dismissed_from_data(data: Mapping[str, Any]) -> Dismissed:
    """A dismissal from its plain form (`{parts: [C2, R1], reason: …}`), or a `BoardError`."""
    a, b = (str(r) for r in data["parts"])
    if not a or not b or a in (b, EDGE):
        raise BoardError("A dismissed warning names the two parts that touch, or a part and "
                         "the edge.")  # fmt: skip
    return Dismissed((a, b), str(data.get("reason") or "").strip())


def dismissed_data(d: Dismissed) -> dict[str, Any]:
    """A dismissal's plain form."""
    return {"parts": list(d.parts)} | ({"reason": d.reason} if d.reason else {})


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
    notes: tuple[Note, ...] = ()  # the builder's notes (D-398)
    dismissed: tuple[Dismissed, ...] = ()  # overlap warnings dismissed (D-398)
    stand_up: StandUp = "room"  # the layout help's choice that made it (D-403)

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
    off-board}, notes: [{parts: [C2], text: Socket it.}], dismissed: [{parts: [C2, R1]}],
    stand_up: never}`,
    holes by name but
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
        notes = tuple(note_from_data(n) for n in data.get("notes") or ())
        dismissed = tuple(dismissed_from_data(d) for d in data.get("dismissed") or ())
        stand_up = data.get("stand_up") or "room"
        if stand_up not in STAND_UP:
            raise BoardError("Standing resistors and diodes is never, room or prefer.")
        return Layout(columns, strips, parts, frozenset(_holes(data.get("cuts", ()))), links,
                      wires, spots, where, notes, dismissed, stand_up)  # fmt: skip
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
        "notes": [note_data(n) for n in layout.notes],
        "dismissed": [dismissed_data(d) for d in layout.dismissed],
        "stand_up": layout.stand_up,
    }
