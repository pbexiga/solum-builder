"""The starting board (D-387; *Lay it out for me*'s, D-399): a board laid out from the
circuit that passes the check, the same every run.

The parts go left to right in signal order, each across the strips in columns of its own.
A strip carries a net along: a part whose leg lands on a strip already carrying that leg's
net joins it there, with nothing to add; a leg landing on a strip carrying another net
gets a cut at the left of its part's columns, and starts a new piece of its own net. Each
part's rows and way round are chosen so that as many legs as possible join (the fewest
pieces). When the parts are placed, every net left in more than one piece gets a bus: one
strip the full width of the board, above the parts (ground's and V-'s below on a new
board), and the leg that started each piece is linked to it up a column of its part's own.
So the layout can't fail: a piece's link column is its part's, clear of every other leg.
A part with two legs on one net (a trimmer as a variable resistor, a buffer's output tied
to its input) has them on neighbouring strips: the second is joined to the first by a short
link beside the part, never a bus (the user, 2026-11-23).
Several heights are tried for the parts' rows; the smallest board is kept.

Since P8's R3 it has no button of its own: it is *Lay it out for me*'s starting board
(D-399), and *Fill the rest* went with it.
"""

from collections import defaultdict
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Literal

from solum.circuit.connectivity import GROUND
from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import PITCH, Hole, Layout, Link, Placed, StandUp
from solum.stripboard.check import (
    Reading,
    check_layout,
    read_layout,
)
from solum.stripboard.footprints import (
    BoardPart,
    Footprint,
    body_holes,
    dip_legs,
    triangle_legs,
)
from solum.stripboard.guidance import signal_order
from solum.stripboard.wiring import WiringError, wire_for_me

BOTTOM = (GROUND, "V-")  # nets whose bus is a bottom strip (on a new board)
AXIAL_SPREAD = 3  # holes more than its least a flat resistor or diode may span
Stand = Literal["none", "first", "last"]  # standing tried (D-403): not at all, before
# lying flat, or after it
EXTRA_ROWS = 20  # rows beyond the tallest part's tried for the parts' band


class StartError(ValueError):
    """Nothing to lay out, or no layout could be made (plain-English message)."""


@dataclass(frozen=True)
class Started:
    """The board laid out."""

    layout: Layout


# --- the room links need ------------------------------------------------------------------


@dataclass
class _Room:
    """What's taken on the board while links are laid: `used` holes something sits in (a
    leg, a pad, a cut, a link's end); `bodies` under any body (a link may pass under one,
    not end there); `over` the holes a link passes over."""

    used: set[Hole] = field(default_factory=set)
    bodies: set[Hole] = field(default_factory=set)
    over: set[Hole] = field(default_factory=set)
    links: list[Link] = field(default_factory=list)

    def free(self, column: int, a: int, b: int, also: "_Room | None" = None) -> bool:
        """Whether a link can run down `column` from strip `a` to strip `b`, clear of
        what's taken here and in `also`."""
        top, bottom = sorted((a, b))
        for room in (self, also) if also else (self,):
            for end in ((column, top), (column, bottom)):
                if end in room.used or end in room.bodies or end in room.over:
                    return False
            for s in range(top + 1, bottom):
                if (column, s) in room.used:
                    return False
        return True

    def link(self, column: int, a: int, b: int) -> None:
        top, bottom = sorted((a, b))
        made = Link((column, top), (column, bottom))
        self.links.append(made)
        self.used |= {made.a, made.b}
        self.over |= set(made.between)


# --- a part's shapes: its legs across the strips ------------------------------------------


@dataclass(frozen=True)
class _Shape:
    """A part across the strips: its legs' holes from the top-left leg's column and the
    top leg's strip, the rows its body reaches above and below them, and its first column
    of legs (a chip's: those links go left)."""

    legs: dict[str, Hole]
    up: int  # body rows above the top leg
    down: int  # rows from the top leg to the lowest hole it takes
    left: frozenset[str] = frozenset()
    standing: bool = False


def _shaped(part: BoardPart, legs: dict[str, Hole], standing: bool = False) -> _Shape:
    xs = min(h[0] for h in legs.values())
    ys = min(h[1] for h in legs.values())
    legs = {leg: (x - xs, y - ys) for leg, (x, y) in legs.items()}
    taken = body_holes(part, legs, standing) | set(legs.values())
    up = max(0, -min(h[1] for h in taken))
    down = max(h[1] for h in taken)
    left = (
        frozenset(leg for leg, h in legs.items() if h[0] == 0)
        if part.footprint.shape == "dip"
        else frozenset()
    )
    return _Shape(legs, up, down, left, standing)


def shapes(part: BoardPart, every: bool = False, stand: Stand = "none") -> list[_Shape]:
    """Every way `part` stands across the strips: a chip either way up; a line of legs
    top to bottom either way round, at each step its footprint allows (a flat resistor or
    diode from its least span to a few holes more). `every` adds the ways *Build a full
    layout* also tries (D-399): a line of legs along a strip, a trimmer turned a quarter.
    `stand`: a resistor or diode stood up too, tried `first` or `last` (D-403)."""
    return list(_shapes(part.footprint, part.legs, every, stand))


def stand_order(stand_up: StandUp) -> Stand:
    """How the starting board tries standing a part (D-403): first when preferred;
    otherwise not (when needed, it's the search that stands one, where lying flat can't
    do as well)."""
    order: dict[StandUp, Stand] = {"prefer": "first", "needed": "none", "never": "none"}
    return order[stand_up]


@lru_cache(maxsize=512)
def _shapes(fp: Footprint, names: tuple[str, ...], every: bool,
            stand: Stand) -> tuple[_Shape, ...]:  # fmt: skip
    """`shapes`, by what they depend on: the footprint and the legs' names."""
    part = BoardPart("", fp, {})
    if fp.shape == "dip":
        return tuple(
            _shaped(part, dip_legs(len(fp.order), (0, 0), t, fp.row_holes)) for t in (False, True)
        )
    if fp.shape == "triangle":  # 1 and 3 across the strips, either way up (D-393)
        turns = range(4) if every else (0, 2)
        return tuple(
            _shaped(part, triangle_legs(t, swapped=m)) for t in turns for m in (False, True)
        )
    spans = [(step, False) for step in fp.steps]
    if fp.shape == "axial":
        spans = [(step, False) for step in range(fp.flat, fp.flat + 1 + AXIAL_SPREAD)]
        if stand != "none" and fp.stand:
            spans.insert(0 if stand == "first" else len(spans), (fp.stand, True))
    ways = ((0, 1), (1, 0)) if every else ((0, 1),)
    found = []
    for step, standing in spans:
        for order in (names, names[::-1]):
            for dx, dy in ways:
                legs = {leg: (k * step * dx, k * step * dy) for k, leg in enumerate(order)}
                found.append(_shaped(part, legs, standing))
    return tuple(found)


def _box(holes: Iterable[Hole]) -> tuple[int, int, int, int]:
    found = list(holes)
    xs, ys = [h[0] for h in found], [h[1] for h in found]
    return min(xs), min(ys), max(xs), max(ys)


# --- the circuit as the layout sees it ----------------------------------------------------


def _leg_net(r: Reading, part: BoardPart, leg: str) -> str:
    """The net a leg joins; a free or no-connect leg one of its own, joined to nothing."""
    pin = part.pins.get(leg)
    if pin is None or leg in part.free:
        return f"{part.ref}#{leg}"
    return r.nets.net_of(*pin)


def _order(circuit: Circuit, r: Reading, refs: Iterable[str]) -> list[str]:
    """The parts left to right: nearest the input along the signal first, chips and
    transistors before the rest at the same distance."""
    order = signal_order(circuit, r)
    far = len(order) + 1
    rank = {"dip": 0, "sil": 0, "inline": 1}

    def key(ref: str) -> tuple[int, int, str]:
        part = r.board[ref]
        near = min((order.get(r.nets.net_of(*p), far) for p in part.pins.values()), default=far)
        return (near, rank.get(part.footprint.shape, 2), ref)

    return sorted(refs, key=key)


# --- pass 1: each part's rows and way round -----------------------------------------------


@dataclass(frozen=True)
class _Choice:
    """A part's place in the band: its shape, its top leg's row, the legs that start a
    piece of their net, the rows cut at its left, and each leg joined by a short link to
    another of its own on the same net (`twins`: leg → that leg)."""

    ref: str
    shape: _Shape
    row: int
    starts: frozenset[str]
    cuts: frozenset[int]
    twins: tuple[tuple[str, str], ...] = ()


def _carry(r: Reading, choice: _Choice, carried: list[str | None], left: dict[str, int]) -> None:
    """The nets `choice`'s legs carry on along their rows, and its legs no longer to come."""
    part = r.board[choice.ref]
    for leg, (_, y) in sorted(choice.shape.legs.items(), key=lambda kv: kv[1][0]):
        net = _leg_net(r, part, leg)  # a chip's second column last: it carries on
        carried[choice.row + y] = net
        left[net] = left.get(net, 1) - 1


def _best(r: Reading, ref: str, height: int, carried: list[str | None], left: dict[str, int],
          stand: Stand = "none") -> tuple[float, _Choice] | None:  # fmt: skip
    """`ref`'s cheapest place in the band (`_try`)."""
    best: tuple[tuple[float, int, int], _Choice] | None = None
    for k, shape in enumerate(shapes(r.board[ref], stand=stand)):
        for row in range(shape.up, height - shape.down):
            cost, choice = _try(r, r.board[ref], shape, row, carried, left)
            key = (cost, row, k)
            if best is None or key < best[0]:
                best = (key, choice)
    return None if best is None else (best[0][0], best[1])


def _choose(r: Reading, order: list[str], height: int, left: dict[str, int],
            stand: Stand = "none") -> list[_Choice] | None:  # fmt: skip
    """Each part's place in a band `height` rows high, in order (module doc); `left`: each
    net's legs still to place (a net cut off while it has legs to come costs a piece).
    None when a part is taller than the band."""
    carried: list[str | None] = [None] * height
    left = dict(left)
    found: list[_Choice] = []
    for ref in order:
        best = _best(r, ref, height, carried, left, stand)
        if best is None:
            return None
        _carry(r, best[1], carried, left)
        found.append(best[1])
    return found


def _try(r: Reading, part: BoardPart, shape: _Shape, row: int, carried: list[str | None],
         left: dict[str, int]) -> tuple[float, _Choice]:  # fmt: skip
    """The cost of `part` in `shape` with its top leg on `row`: a piece started 10, a
    leg linked to its twin 2, a cut 3, a net cut off with legs still to come 5 more."""
    starts, cuts, twins = set(), set(), []
    cost = 0.0
    anchors: dict[tuple[str, bool], str] = {}  # (net, in a chip's first column) → its leg
    nets = {leg: _leg_net(r, part, leg) for leg in shape.legs}
    for leg, (x, y) in shape.legs.items():  # the legs joining a strip of their net first
        if not (shape.left and x > 0) and carried[row + y] == nets[leg]:
            anchors.setdefault((nets[leg], leg in shape.left), leg)
    for leg, (x, y) in shape.legs.items():
        net = nets[leg]
        here = carried[row + y]
        behind = bool(shape.left) and x > 0  # behind a chip's middle cut: a piece of its own
        if here == net and not behind:
            continue
        side = (net, leg in shape.left)  # a chip's two columns are linked on their own sides
        twin = anchors.get(side)
        if twin is not None and shape.legs[twin][1] != y:
            twins.append((leg, twin))
            cost += 2
        else:
            anchors.setdefault(side, leg)
            starts.add(leg)
            cost += 10
        if not behind and here is not None:
            cuts.add(row + y)
            cost += 3 + 5 * (left.get(here, 0) > 0)
    return cost, _Choice(part.ref, shape, row, frozenset(starts), frozenset(cuts), tuple(twins))


def _band_pieces(r: Reading, choices: list[_Choice]) -> dict[str, int]:
    """How many pieces each net is in across the band."""
    count: dict[str, int] = defaultdict(int)
    for choice in choices:
        part = r.board[choice.ref]
        for leg in choice.starts:
            count[_leg_net(r, part, leg)] += 1
    return count


# --- pass 2: the columns, the cuts and the links ------------------------------------------


@dataclass
class _Plan:
    """The layout being made: the parts placed, the cuts, the room left, and each band
    row's last column taken (a leg, a cut, a link's end, a hole kept for a wire): what
    comes next on that row goes to its right."""

    room: _Room
    parts: list[Placed] = field(default_factory=list)
    cuts: set[Hole] = field(default_factory=set)
    last: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _Spot:
    """Where a part goes: its legs, the cuts it brings, what it takes (its legs, body,
    cuts, links), and the holes kept free beside a piece wired off the board."""

    legs: dict[str, Hole]
    cuts: list[Hole]
    taken: _Room
    kept: set[Hole]


def _overhangs(part: BoardPart, legs: dict[str, Hole]) -> bool:
    """Whether a round body (an electrolytic's) would hang over the board's left edge,
    half a hole left of column A."""
    if not part.footprint.diameter:
        return False
    middle = sum(h[0] for h in legs.values()) / len(legs)
    return middle - part.footprint.diameter / 2 / PITCH < -0.5


def _fits(r: Reading, plan: _Plan, choice: _Choice, top: int, bus: dict[str, int],
          lone: set[str], shift: int) -> _Spot | None:  # fmt: skip
    """`choice` moved `shift` columns right, if it fits: clear of everything placed, each
    row's first leg right of that row's last column (and of a free hole for its cut), a
    free column for each link (a chip's first column's to its left, the rest to its
    right; a twin's short link nearest), a hole kept beside each leg starting a piece
    wired off the board (`lone`)."""
    room, part, shape = plan.room, r.board[choice.ref], choice.shape
    legs = {leg: (x + shift, top + choice.row + y) for leg, (x, y) in shape.legs.items()}
    body = body_holes(part, legs, shape.standing)
    if min(h[0] for h in [*legs.values(), *body]) < 0 or _overhangs(part, legs):
        return None
    for h in legs.values():
        if h in room.used or h in room.bodies or h in room.over:
            return None
    for h in body:
        if h in room.used or h in room.bodies:
            return None
    taken = _Room(used=set(legs.values()), bodies=set(body))

    first: dict[int, int] = {}
    for x, y in legs.values():
        first[y] = min(first.get(y, x), x)
    cuts: list[Hole] = []
    after: dict[int, int] = {}  # each row's least column a link end may take
    for row, column in first.items():
        last = plan.last.get(row, -1)
        if column <= last:
            return None
        after[row] = last + 1
        if row - top in choice.cuts:
            free = (c for c in range(last + 1, column) if (c, row) not in room.over)
            cut = next(free, None)
            if cut is None:
                return None
            cuts.append((cut, row))
            after[row] = cut + 1
    if shape.left:
        for row, column in first.items():
            middle = (column + 1, row)
            if middle in room.over or middle in room.used:
                return None
            cuts.append(middle)
    taken.used |= set(cuts)
    right = max(h[0] for h in [*legs.values(), *body]) + 1
    for leg, twin in choice.twins:  # first, so they're nearest the part
        (column, row), (other, to) = legs[leg], legs[twin]
        if leg in shape.left:
            span = range(max(after[row], after[to]), min(column, other))
            at = next((c for c in span if room.free(c, row, to, taken)), None)
            if at is None:
                return None
        else:
            at = right
            while not room.free(at, row, to, taken):
                at += 1
        taken.link(at, row, to)
    nets = {leg: _leg_net(r, part, leg) for leg in legs}
    linked = [leg for leg in part.legs if leg in choice.starts and nets[leg] in bus]
    for leg in (leg for leg in linked if leg in shape.left):
        (column, row), to = legs[leg], bus[nets[leg]]
        at = next((c for c in range(after[row], column) if room.free(c, row, to, taken)), None)
        if at is None:
            return None
        taken.link(at, row, to)
    for leg in (leg for leg in linked if leg not in shape.left):
        row, to = legs[leg][1], bus[nets[leg]]
        at = right
        while not room.free(at, row, to, taken):
            at += 1
        taken.link(at, row, to)
    kept: set[Hole] = set()
    for leg in (leg for leg in choice.starts if nets[leg] in lone):
        column, row = legs[leg]
        hole = (column + 1, row)
        while any(hole in held for held in (taken.used, taken.bodies, taken.over, room.used,
                                             room.bodies, room.over)):  # fmt: skip
            hole = (hole[0] + 1, row)
        kept.add(hole)
    return _Spot(legs, cuts, taken, kept)


def _lay(r: Reading, plan: _Plan, choice: _Choice, top: int, bus: dict[str, int],
         lone: set[str]) -> None:  # fmt: skip
    """A part put as far left as it fits (`_fits`), and what it takes marked."""
    shift = max(plan.last.get(top + choice.row + y, -1) + 1 - x
                for x, y in choice.shape.legs.values())  # fmt: skip
    while (spot := _fits(r, plan, choice, top, bus, lone, shift)) is None:
        shift += 1
    room, taken = plan.room, spot.taken
    room.used |= taken.used | spot.kept
    room.bodies |= taken.bodies
    room.over |= taken.over
    room.links += taken.links
    plan.cuts |= set(spot.cuts)
    for column, row in [*spot.legs.values(), *spot.cuts, *spot.kept,
                        *(h for link in taken.links for h in (link.a, link.b))]:  # fmt: skip
        plan.last[row] = max(plan.last.get(row, -1), column)
    part = r.board[choice.ref]
    plan.parts.append(Placed(choice.ref, tuple((leg, spot.legs[leg]) for leg in part.legs),
                             choice.shape.standing))  # fmt: skip


def _laid_out(r: Reading, circuit: Circuit, base: Layout, todo: list[str],
              choices: list[_Choice], height: int) -> Layout:  # fmt: skip
    """`base` (its choices only) with the parts placed as chosen, the buses above and
    below them, every net's pieces joined (module doc)."""
    pieces = _band_pieces(r, choices)
    new = {net for c in choices for net in (_leg_net(r, r.board[c.ref], leg) for leg in c.starts)}
    wanted = {n for n in new if pieces.get(n, 0) > 1}
    order = signal_order(circuit, r)
    rails = list(circuit.power.rails)
    ranked = sorted(wanted, key=lambda n: (0 if n in rails else 1, order.get(n, len(order) + 1), n))
    below = [n for n in BOTTOM if n in wanted]
    above = [n for n in ranked if n not in below]
    bus = {net: k for k, net in enumerate(above)}
    top = len(above)
    floor = top + height
    bus |= {net: floor + k for k, net in enumerate(below)}
    plan = _Plan(_Room())
    lone = set(r.ends.values()) - bus.keys()
    for choice in choices:
        _lay(r, plan, choice, top, bus, lone)
    strips = max(floor + len(below) if todo else top, 1)
    taken = plan.room.used | plan.room.bodies
    columns = max(max((h[0] for h in taken), default=0) + 1, 1)
    return replace(
        base,
        columns=columns,
        strips=strips,
        parts=tuple(plan.parts),
        cuts=frozenset(plan.cuts),
        links=tuple(plan.room.links),
    )


def _legs_to_place(r: Reading, todo: list[str]) -> dict[str, int]:
    count: dict[str, int] = defaultdict(int)
    for ref in todo:
        part = r.board[ref]
        for leg in part.legs:
            count[_leg_net(r, part, leg)] += 1
    return count


def start_for_me(layout: Layout | None, circuit: Circuit, models: ModelLibrary,
                 table: FootprintTable, stand_up: StandUp | None = None) -> Started:  # fmt: skip
    """The starting board for *Lay it out for me* (D-399; its own button went with P8's
    R3): the whole board laid out afresh, the parts' On / Off the board choices and the
    notes kept, with the off-board parts beside it and wired; `StartError` when a part
    can't go on a board or nothing does. `stand_up`: standing resistors and diodes
    (`stand_order`; None: the board's own choice), kept with the board made (D-403)."""
    old = layout or Layout(0, 0, ())
    stand_up = stand_up or old.stand_up
    stand = stand_order(stand_up)
    base = replace(
        Layout(0, 0, ()),
        where=old.where,
        notes=old.notes,
        dismissed=old.dismissed,
        stand_up=stand_up,
    )  # its choices and notes kept (D-398)
    r = read_layout(base, circuit, models, table)
    if r.unboardable:
        raise StartError(" ".join(r.unboardable))
    if not r.board:
        raise StartError("Nothing in this circuit goes on a board.")
    todo = _order(circuit, r, sorted(r.board))
    tallest = max((min(s.up + s.down for s in shapes(r.board[ref])) for ref in todo), default=0)
    remaining = _legs_to_place(r, todo)
    best: tuple[tuple[int, int], Layout] | None = None
    for height in range(tallest + 1, tallest + 2 + EXTRA_ROWS):
        chosen = _choose(r, todo, height, remaining, stand)
        if chosen is not None:
            made = _laid_out(r, circuit, base, todo, chosen, height)
            key = (made.columns * made.strips, len(made.links))
            if best is None or key < best[0]:
                best = (key, made)
        if not todo:
            break
    if best is None:
        raise StartError("Couldn't lay this board out.")
    made = best[1]
    with suppress(WiringError):  # nothing to wire
        made = wire_for_me(made, circuit, models, table)
    checked = check_layout(made, circuit, models, table)
    if not checked.ok:
        raise StartError(f"Couldn't lay this board out: {checked.faults[0]}")
    return Started(made)
