"""*Start for me* (spec, *Automatic help*; D-387): a board laid out from the circuit that
passes the check, the same every run.

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
Several heights are tried for the parts' rows; the board breaking the fewest placement
limits, then the smallest, is kept.

Placement limits (D-367, D-400): a part kept by another's pin (a chip's decoupling cap, an
op-amp's feedback parts, a bypass cap) is laid out with it, its leg on the pin's strip: by
a chip's first column just before the chip (that strip runs left), otherwise just after;
the parts before a chip slide right, a column at a time, until they're close enough.

*Fill the rest* keeps what's on the board and lays out the tray the same way below it,
the buses in between; each piece already on the board of a net with a bus is joined to it
by a link down a free column from its copper. What can't be joined that way is named,
never forced: the builder's own placements are never moved.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from functools import lru_cache

from solum.circuit.connectivity import GROUND
from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import PITCH, Hole, Layout, Link, Placed
from solum.stripboard.check import (
    Reading,
    check_layout,
    groups_by_net,
    joined_groups,
    occupants,
    read_layout,
)
from solum.stripboard.footprints import (
    BoardPart,
    Footprint,
    body_holes,
    dip_legs,
    links_under,
    triangle_legs,
)
from solum.stripboard.guidance import signal_order
from solum.stripboard.limits import (
    Limit,
    LoudInput,
    broken_limits,
    group_met,
    limit_groups,
    placement_limits,
)
from solum.stripboard.quiet import MIXED, calm_nets, guards, kept_clear, noisy_links, quiet_for
from solum.stripboard.wiring import WiringError, wire_for_me

BOTTOM = (GROUND, "V-")  # nets whose bus is a bottom strip (on a new board)
AXIAL_SPREAD = 3  # holes more than its least a flat resistor or diode may span
EXTRA_ROWS = 20  # rows beyond the tallest part's tried for the parts' band
LIMIT_COST = 20  # pass 1: a kept part whose leg can't be on its pin's strip (2 pieces)
SLIDE = 8  # columns the parts before a chip may slide right to sit by its pin

Guarded = dict[str, tuple[str, tuple[str, ...]]]  # a sensitive net's part → (net, its legs)


class StartError(ValueError):
    """Nothing to lay out, or no layout could be made (plain-English message)."""


@dataclass(frozen=True)
class Started:
    """The board laid out, and what's left for the builder to join (empty: it passes)."""

    layout: Layout
    left: tuple[str, ...] = ()


# --- the room links need ------------------------------------------------------------------


@dataclass
class _Room:
    """What's taken on the board while links are laid: `used` holes something sits in (a
    leg, a pad, a cut, a link's end); `bodies` under any body; `hard` under a body no link
    passes under; `over` the holes a link passes over."""

    used: set[Hole] = field(default_factory=set)
    bodies: set[Hole] = field(default_factory=set)
    hard: set[Hole] = field(default_factory=set)
    over: set[Hole] = field(default_factory=set)
    links: list[Link] = field(default_factory=list)
    zone: dict[Hole, str] = field(default_factory=dict)  # kept clear of a sensitive net's parts
    calm: frozenset[str] = frozenset()  # nets whose links may pass them (`quiet.calm_nets`)

    def body(self, part: BoardPart, legs: dict[str, Hole]) -> None:
        covered = body_holes(part, legs, False)
        self.bodies |= covered
        if not links_under(part, False):
            self.hard |= covered

    def free(self, column: int, a: int, b: int, also: "_Room | None" = None) -> bool:
        """Whether a link can run down `column` from strip `a` to strip `b`, clear of
        what's taken here and in `also`."""
        top, bottom = sorted((a, b))
        for room in (self, also) if also else (self,):
            for end in ((column, top), (column, bottom)):
                if end in room.used or end in room.bodies or end in room.over:
                    return False
            for s in range(top + 1, bottom):
                if (column, s) in room.used or (column, s) in room.hard:
                    return False
        return True

    def quiet(self, column: int, a: int, b: int, net: str) -> bool:
        """Whether a link of `net` down `column` keeps clear of every other sensitive net's
        parts placed so far (D-402)."""
        top, bottom = sorted((a, b))
        holes = [(column, s) for s in range(top, bottom + 1)]
        return quiet_for(self.zone, net, holes, self.calm)

    def guard(self, net: str, legs: Iterable[Hole], body: Iterable[Hole]) -> None:
        """A sensitive net's part placed: the holes links of other nets keep out of."""
        for h in kept_clear(legs, body)[1]:
            self.zone[h] = net if self.zone.get(h, net) == net else MIXED

    def link(self, column: int, a: int, b: int) -> None:
        top, bottom = sorted((a, b))
        made = Link((column, top), (column, bottom))
        self.links.append(made)
        self.used |= {made.a, made.b}
        self.over |= set(made.between)


def _room(layout: Layout, board: dict[str, BoardPart], guarded: "Guarded") -> _Room:
    """The room a board already leaves (Fill the rest)."""
    room = _Room(used=set(occupants(layout)[0]) | set(layout.cuts))
    for p in layout.parts:
        part = board.get(p.ref)
        if part is not None:
            covered = body_holes(part, p.holes, p.standing)
            room.bodies |= covered
            if not links_under(part, p.standing):
                room.hard |= covered
            if p.ref in guarded:
                net, legs = guarded[p.ref]
                room.guard(net, [p.holes[lg] for lg in legs if lg in p.holes], covered)
    for link in layout.links:
        room.over |= set(link.between)
    return room


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


def shapes(part: BoardPart, every: bool = False) -> list[_Shape]:
    """Every way `part` stands across the strips: a chip either way up; a line of legs
    top to bottom either way round, at each step its footprint allows (a flat resistor or
    diode from its least span to a few holes more). `every` adds the ways *Build a full
    layout* also tries (D-399): a line of legs along a strip, a resistor or diode stood
    up, a trimmer turned a quarter."""
    return list(_shapes(part.footprint, part.legs, every))


@lru_cache(maxsize=512)
def _shapes(fp: Footprint, names: tuple[str, ...], every: bool) -> tuple[_Shape, ...]:
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
        if every and fp.stand:
            spans.append((fp.stand, True))
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


@dataclass(frozen=True)
class _Block:
    """A part and the parts its pins keep (their limits), laid out together."""

    anchor: str
    limits: tuple[Limit, ...]


def _units(order: list[str], limits: Sequence[Limit]) -> list[str | _Block]:
    """`order` with each part kept by another's pin taken into that part's block (the
    first that keeps it); a part that keeps others isn't taken into another's."""
    todo = set(order)
    anchors = {lim.anchor for lim in limits if lim.anchor in todo}
    owner: dict[str, str] = {}
    kept: dict[str, list[Limit]] = defaultdict(list)
    for lim in limits:
        if lim.anchor in todo and lim.part in todo and lim.part not in anchors | owner.keys():
            owner[lim.part] = lim.anchor
            kept[lim.anchor].append(lim)
    return [_Block(ref, tuple(kept[ref])) if ref in kept else ref
            for ref in order if ref not in owner]  # fmt: skip


def _pieces(r: Reading) -> dict[str, list[int]]:
    """Each net's joined groups on the board that carry it and no other net."""
    found: dict[str, list[int]] = defaultdict(list)
    for group, here in groups_by_net(r).items():
        if len(here) == 1:
            found[next(iter(here))].append(group)
    return found


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


@dataclass(frozen=True)
class _Kept:
    """A block's choices, `start` to `stop` in the band's order, the anchor's at `anchor`."""

    start: int
    stop: int
    anchor: int
    block: _Block


def _carry(r: Reading, choice: _Choice, carried: list[str | None], left: dict[str, int]) -> None:
    """The nets `choice`'s legs carry on along their rows, and its legs no longer to come."""
    part = r.board[choice.ref]
    for leg, (_, y) in sorted(choice.shape.legs.items(), key=lambda kv: kv[1][0]):
        net = _leg_net(r, part, leg)  # a chip's second column last: it carries on
        carried[choice.row + y] = net
        left[net] = left.get(net, 1) - 1


def _best(r: Reading, ref: str, height: int, carried: list[str | None], left: dict[str, int],
          want: tuple[str, int, bool] | None = None) -> tuple[float, _Choice] | None:  # fmt: skip
    """`ref`'s cheapest place in the band (`_try`); `want`: its leg that must be on a row,
    the rows putting it there only (any row, at `LIMIT_COST` more, when none can), and
    whether the part comes before its pin (that leg rightmost, else leftmost, as ties go)."""
    part = r.board[ref]
    best: tuple[tuple[float, int, int, int], _Choice] | None = None
    for k, shape in enumerate(shapes(part)):
        rows = range(shape.up, height - shape.down)
        if want is not None:
            row = want[1] - shape.legs[want[0]][1]
            rows = range(row, row + 1) if row in rows else rows
        x = 0
        if want is not None:  # how far the leg is from the part's side facing its pin
            x = shape.legs[want[0]][0]
            x = max(h[0] for h in shape.legs.values()) - x if want[2] else x
        for row in rows:
            cost, choice = _try(r, part, shape, row, carried, left)
            if want is not None and row + shape.legs[want[0]][1] != want[1]:
                cost += LIMIT_COST
            key = (cost, x, row, k)
            if best is None or key < best[0]:
                best = (key, choice)
    return None if best is None else (best[0][0], best[1])


def _block(r: Reading, block: _Block, height: int, carried: list[str | None],
           left: dict[str, int]) -> tuple[list[_Choice], int] | None:  # fmt: skip
    """A block's places, cheapest in all: for each way the anchor can stand, the parts by
    its first column first, then the anchor, then the rest, each kept part's leg on its
    pin's row; and where the anchor's choice is among them. `carried` and `left` carried
    on past it; None when nothing fits."""
    anchor = r.board[block.anchor]
    best: tuple[tuple[float, int, int], list[_Choice], int, list[str | None],
                dict[str, int]] | None = None  # fmt: skip
    for k, shape in enumerate(shapes(anchor)):
        for row in range(shape.up, height - shape.down):
            c, lf = list(carried), dict(left)
            choices: list[_Choice] = []

            def kept(lims: list[Limit], c: list[str | None] = c, lf: dict[str, int] = lf,
                     row: int = row, shape: _Shape = shape,
                     choices: list[_Choice] = choices) -> float | None:  # fmt: skip
                cost = 0.0
                for lim in lims:
                    to = (lim.leg, row + shape.legs[lim.pin][1], lim.pin in shape.left)
                    found = _best(r, lim.part, height, c, lf, to)
                    if found is None:
                        return None
                    _carry(r, found[1], c, lf)
                    choices.append(found[1])
                    cost += found[0]
                return cost

            first = kept([lim for lim in block.limits if lim.pin in shape.left])
            if first is None:
                continue
            cost, made = _try(r, anchor, shape, row, c, lf)
            _carry(r, made, c, lf)
            at = len(choices)
            choices.append(made)
            rest = kept([lim for lim in block.limits if lim.pin not in shape.left])
            if rest is None:
                continue
            key = (first + cost + rest, row, k)
            if best is None or key < best[0]:
                best = (key, choices, at, c, lf)
    if best is None:
        return None
    _, choices, at, c, lf = best
    carried[:] = c
    left.clear()
    left.update(lf)
    return choices, at


def _choose(r: Reading, units: list[str | _Block], height: int,
            left: dict[str, int]) -> tuple[list[_Choice], list[_Kept]] | None:  # fmt: skip
    """Each part's place in a band `height` rows high, in order (module doc), and the
    blocks among them; `left`: each net's legs still to place (a net cut off while it has
    legs to come costs a piece). None when a part is taller than the band."""
    carried: list[str | None] = [None] * height
    left = dict(left)
    found: list[_Choice] = []
    kept: list[_Kept] = []
    for unit in units:
        if isinstance(unit, _Block):
            made = _block(r, unit, height, carried, left)
            if made is None:
                return None
            choices, at = made
            kept.append(_Kept(len(found), len(found) + len(choices), len(found) + at, unit))
            found += choices
            continue
        best = _best(r, unit, height, carried, left)
        if best is None:
            return None
        _carry(r, best[1], carried, left)
        found.append(best[1])
    return found, kept


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
    left: list[str] = field(default_factory=list)
    guarded: "Guarded" = field(default_factory=dict)

    def copy(self) -> "_Plan":
        """A copy to try on (what's in it is frozen: the containers are copied)."""
        room = self.room
        return _Plan(_Room(set(room.used), set(room.bodies), set(room.hard), set(room.over),
                           list(room.links), dict(room.zone), room.calm), list(self.parts),
                     set(self.cuts), dict(self.last), list(self.left), self.guarded)  # fmt: skip


def _join_pieces(r: Reading, plan: _Plan, bus: dict[str, int]) -> None:
    """Each piece already on the board of a net with a bus, joined to it by a link down
    from its copper: the shortest, the leftmost of those; one that can't be named."""
    holes, _ = joined_groups(r.layout)
    by_group: dict[int, list[Hole]] = defaultdict(list)
    for hole, group in holes.items():
        by_group[group].append(hole)
    for net, groups in sorted(_pieces(r).items()):
        if net not in bus:
            continue
        for group in groups:
            row = bus[net]
            ways = sorted((row - h[1], h[0], h) for h in by_group[group] if h[1] < row)
            free = [h for _, _, h in ways if plan.room.free(h[0], h[1], row)]
            way = next((h for h in free if plan.room.quiet(h[0], h[1], row, net)), None)
            way = way or next(iter(free), None)
            if way is None:
                plan.left.append(
                    f"{net}: no free column runs down from its copper on the board to its "
                    "new strip. Lay a link to join them, or Start over."
                )
                continue
            plan.room.link(way[0], way[1], row)


_Later = tuple[tuple[Hole, int], ...]  # links put off: (the leg's hole, its bus strip)


@dataclass(frozen=True)
class _Spot:
    """Where a part goes: its legs, the cuts it brings, what it takes (its legs, body,
    cuts, links), and the holes kept free beside a piece wired off the board."""

    legs: dict[str, Hole]
    cuts: list[Hole]
    taken: _Room
    kept: set[Hole]
    later: _Later = ()


def _overhangs(part: BoardPart, legs: dict[str, Hole]) -> bool:
    """Whether a round body (an electrolytic's) would hang over the board's left edge,
    half a hole left of column A."""
    if not part.footprint.diameter:
        return False
    middle = sum(h[0] for h in legs.values()) / len(legs)
    return middle - part.footprint.diameter / 2 / PITCH < -0.5


def _fits(r: Reading, plan: _Plan, choice: _Choice, top: int, bus: dict[str, int],
          lone: set[str], shift: int, way: str = "") -> _Spot | None:  # fmt: skip
    """`choice` moved `shift` columns right, if it fits: clear of everything placed, each
    row's first leg right of that row's last column (and of a free hole for its cut), a
    free column for each link (a chip's first column's to its left, the rest to its
    right; a twin's short link nearest), a hole kept beside each leg starting a piece
    wired off the board (`lone`). `way` "left": every link to the part's left (a part
    before a chip's first column, D-400); "later": the links to its right put off (a
    chip whose kept parts come after it, `_lay_later`)."""
    room, part, shape = plan.room, r.board[choice.ref], choice.shape
    legs = {leg: (x + shift, top + choice.row + y) for leg, (x, y) in shape.legs.items()}
    body = body_holes(part, legs, False)
    if min(h[0] for h in [*legs.values(), *body]) < 0 or _overhangs(part, legs):
        return None
    for h in legs.values():
        if h in room.used or h in room.bodies or h in room.over:
            return None
    hard = not links_under(part, False)
    for h in body:
        if h in room.used or h in room.bodies or (hard and h in room.over):
            return None
    taken = _Room(used=set(legs.values()), bodies=set(body), hard=set(body) if hard else set())
    if choice.ref in plan.guarded:  # its own links keep clear of it too
        net, held = plan.guarded[choice.ref]
        taken.guard(net, [legs[lg] for lg in held], body)

    def quiet(c: int, row: int, to: int, net: str) -> bool:
        return room.quiet(c, row, to, net) and taken.quiet(c, row, to, net)

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
    lefts = set(linked) if way == "left" else shape.left
    for leg in (leg for leg in linked if leg in lefts):
        (column, row), to = legs[leg], bus[nets[leg]]
        found = [c for c in range(after[row], column) if room.free(c, row, to, taken)]
        at = next((c for c in found if quiet(c, row, to, nets[leg])), None)
        at = next(iter(found), None) if at is None else at
        if at is None:
            return None
        taken.link(at, row, to)
    later = tuple((legs[leg], bus[nets[leg]]) for leg in linked
                  if leg not in lefts and way == "later")  # fmt: skip
    for leg in (leg for leg in linked if leg not in lefts and way != "later"):
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
    return _Spot(legs, cuts, taken, kept, later)


def _lay(r: Reading, plan: _Plan, choice: _Choice, top: int, bus: dict[str, int],
         lone: set[str], slide: int = 0, way: str = "") -> _Later:  # fmt: skip
    """A part put as far left as it fits (`_fits`), `slide` columns further, and what it
    takes marked; the links it put off (`way`)."""
    shift = slide + max(plan.last.get(top + choice.row + y, -1) + 1 - x
                        for x, y in choice.shape.legs.values())  # fmt: skip
    while (spot := _fits(r, plan, choice, top, bus, lone, shift, way)) is None:
        shift += 1
    room, taken = plan.room, spot.taken
    room.used |= taken.used | spot.kept
    room.bodies |= taken.bodies
    room.hard |= taken.hard
    room.over |= taken.over
    room.links += taken.links
    plan.cuts |= set(spot.cuts)
    for column, row in [*spot.legs.values(), *spot.cuts, *spot.kept,
                        *(h for link in taken.links for h in (link.a, link.b))]:  # fmt: skip
        plan.last[row] = max(plan.last.get(row, -1), column)
    part = r.board[choice.ref]
    plan.parts.append(Placed(choice.ref, tuple((leg, spot.legs[leg]) for leg in part.legs)))
    for h, net in taken.zone.items():
        room.zone[h] = net if room.zone.get(h, net) == net else MIXED
    return spot.later


def _lay_later(plan: _Plan, later: Iterable[tuple[Hole, int]], cuts: frozenset[Hole]) -> bool:
    """Each link put off laid from the leg's strip, right of what's on it now and before
    the next cut; False when one can't be."""
    for (column, row), to in later:
        at = max(column, plan.last.get(row, -1)) + 1
        while not plan.room.free(at, row, to):
            at += 1
        if any((c, row) in plan.cuts or (c, row) in cuts for c in range(column, at + 1)):
            return False
        plan.room.link(at, row, to)
        for end in (row, to):
            plan.last[end] = max(plan.last.get(end, -1), at)
    return True


def _missed(plan: _Plan, block: _Block, cuts: frozenset[Hole]) -> int:
    """How many of `block`'s pins its parts, as laid in `plan`, don't sit by."""
    holes = {(p.ref, leg): h for p in plan.parts for leg, h in p.legs}

    def foreign(h: Hole) -> bool:
        return h in plan.cuts or h in cuts

    return sum(not group_met(holes[key], [holes[(g.part, g.leg)] for g in group], foreign)
               for key, group in limit_groups(block.limits).items())  # fmt: skip


def _lay_block(r: Reading, plan: _Plan, choices: list[_Choice], kept: _Kept, top: int,
               bus: dict[str, int], lone: set[str], cuts: frozenset[Hole]) -> _Plan:  # fmt: skip
    """A block laid: the parts before its anchor with their links on their left, slid
    right a column at a time (up to `SLIDE`); the links on the right of the anchor and
    the parts after it put off until they're all laid (when they can't be, laid as
    usual); until every pin keeps its parts, or as near as that gets."""
    best: tuple[int, int, _Plan] | None = None
    after = kept.stop > kept.anchor + 1
    for slide in range(SLIDE + 1 if kept.anchor > kept.start else 1):
        for put_off in (True, False) if after else (False,):
            trial = plan.copy()
            later: list[tuple[Hole, int]] = []
            for j in range(kept.start, kept.stop):
                if j < kept.anchor:
                    _lay(r, trial, choices[j], top, bus, lone, slide, "left")
                else:
                    later += _lay(r, trial, choices[j], top, bus, lone, 0,
                                  "later" if put_off else "")  # fmt: skip
            if not _lay_later(trial, later, cuts):
                continue
            missed = _missed(trial, kept.block, cuts)
            if best is None or (missed, slide) < best[:2]:
                best = (missed, slide, trial)
            if not missed:
                return trial
    assert best is not None
    return best[2]


def _laid_out(r: Reading, circuit: Circuit, base: Layout, todo: list[str],
              choices: list[_Choice], kept: list[_Kept], height: int,
              guarded: "Guarded", calm: frozenset[str]) -> tuple[Layout, list[str]]:  # fmt: skip
    """`base` with the parts placed as chosen below it, the buses between, every net's
    pieces joined (module doc)."""
    fresh = not base.parts
    pieces = _band_pieces(r, choices)
    on_board = _pieces(r)
    new = {net for c in choices for net in (_leg_net(r, r.board[c.ref], leg) for leg in c.starts)}
    wanted = {n for n in new | on_board.keys() if pieces.get(n, 0) + len(on_board.get(n, ())) > 1}
    order = signal_order(circuit, r)
    rails = list(circuit.power.rails)
    ranked = sorted(wanted, key=lambda n: (0 if n in rails else 1, order.get(n, len(order) + 1), n))
    below = [n for n in BOTTOM if n in wanted] if fresh else []
    above = [n for n in ranked if n not in below]
    start = base.strips if not fresh else 0
    bus = {net: start + k for k, net in enumerate(above)}
    top = start + len(above)
    floor = top + height
    bus |= {net: floor + k for k, net in enumerate(below)}
    plan = _Plan(_room(base, r.board, guarded) if not fresh else _Room(), guarded=guarded)
    plan.room.calm = calm
    _join_pieces(r, plan, bus)
    lone = set(r.ends.values()) - bus.keys()
    blocks = {k.start: k for k in kept}
    i = 0
    while i < len(choices):
        block = blocks.get(i)
        if block is None:
            _lay(r, plan, choices[i], top, bus, lone)
            i += 1
            continue
        plan = _lay_block(r, plan, choices, block, top, bus, lone, base.cuts)
        i = block.stop
    strips = max(floor + len(below) if todo else top, base.strips, 1)
    taken = plan.room.used | plan.room.bodies
    columns = max(max((h[0] for h in taken), default=0) + 1, base.columns, 1)
    layout = replace(base, columns=columns, strips=strips,
                     parts=base.parts + tuple(plan.parts), cuts=base.cuts | plan.cuts,
                     links=base.links + tuple(plan.room.links))  # fmt: skip
    return layout, plan.left


def _legs_to_place(r: Reading, todo: list[str]) -> dict[str, int]:
    count: dict[str, int] = defaultdict(int)
    for ref in todo:
        part = r.board[ref]
        for leg in part.legs:
            count[_leg_net(r, part, leg)] += 1
    return count


def start_for_me(layout: Layout | None, circuit: Circuit, models: ModelLibrary,
                 table: FootprintTable, fill: bool,
                 loud: Sequence[LoudInput] = ()) -> Started:  # fmt: skip
    """*Fill the rest* (`fill`: what's placed kept, the tray laid out) or *Start over* (the
    whole board laid out afresh; the parts' On / Off the board choices kept), with the
    off-board parts beside it and wired; `StartError` when there's nothing to do or a part
    can't go on a board. `loud`: the high-gain stages' inputs for the placement limits
    (`probe.loud_inputs`)."""
    old = layout or Layout(0, 0, ())
    kept = replace(Layout(0, 0, ()), where=old.where, notes=old.notes, dismissed=old.dismissed)
    base = old if fill else kept  # Start over keeps the choices and the notes (D-398)
    r = read_layout(base, circuit, models, table)
    if r.unboardable:
        raise StartError(" ".join(r.unboardable))
    if not r.board:
        raise StartError("Nothing in this circuit goes on a board.")
    placed = {p.ref for p in base.parts}
    todo = _order(circuit, r, sorted(r.board.keys() - placed))
    limits = placement_limits(circuit, r.nets, r.board, loud)
    kept_parts = guards(r.board, r.nets, loud)
    guarded = {g.ref: (g.net, g.legs) for g in kept_parts}
    units = _units(todo, limits)
    tallest = max((min(s.up + s.down for s in shapes(r.board[ref])) for ref in todo), default=0)
    remaining = _legs_to_place(r, todo)
    best: tuple[tuple[int, int, int, int, int], Layout, list[str]] | None = None
    for height in range(tallest + 1, tallest + 2 + EXTRA_ROWS):
        chosen = _choose(r, units, height, remaining)
        if chosen is None:
            continue
        made, left = _laid_out(r, circuit, base, todo, *chosen, height, guarded,
                               calm_nets(kept_parts))  # fmt: skip
        broken = len(broken_limits(made, limits))
        noisy = len(noisy_links(made, r.board, r.nets, kept_parts))
        key = (len(left), broken, made.columns * made.strips, noisy, len(made.links))
        if best is None or key < best[0]:
            best = (key, made, left)
        if not todo:
            break
    if best is None:
        raise StartError("Couldn't lay this board out.")
    _, made, left = best
    with suppress(WiringError):  # nothing to wire
        made = wire_for_me(made, circuit, models, table)
    if fill and replace(made, spots=old.spots) == old:  # off-board parts put beside it only
        raise StartError("Nothing to fill: every part is placed and every net joined.")
    checked = check_layout(made, circuit, models, table)
    if not checked.ok and not left:
        if not fill:
            raise StartError(f"Couldn't lay this board out: {checked.faults[0]}")
        left = [checked.faults[0]]
    return Started(made, tuple(left))
