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
Several heights are tried for the parts' rows; the smallest board is kept.

*Fill the rest* keeps what's on the board and lays out the tray the same way below it,
the buses in between; each piece already on the board of a net with a bus is joined to it
by a link down a free column from its copper. What can't be joined that way is named,
never forced: the builder's own placements are never moved.
"""

from collections import defaultdict
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field, replace

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
from solum.stripboard.footprints import BoardPart, body_holes, dip_legs, triangle_legs
from solum.stripboard.guidance import signal_order
from solum.stripboard.wiring import WiringError, wire_for_me

BOTTOM = (GROUND, "V-")  # nets whose bus is a bottom strip (on a new board)
AXIAL_SPREAD = 3  # holes more than its least a flat resistor or diode may span
EXTRA_ROWS = 20  # rows beyond the tallest part's tried for the parts' band


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

    def body(self, part: BoardPart, legs: dict[str, Hole]) -> None:
        covered = body_holes(part, legs, False)
        self.bodies |= covered
        if part.footprint.shape != "axial":
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

    def link(self, column: int, a: int, b: int) -> None:
        top, bottom = sorted((a, b))
        made = Link((column, top), (column, bottom))
        self.links.append(made)
        self.used |= {made.a, made.b}
        self.over |= set(made.between)


def _room(layout: Layout, board: dict[str, BoardPart]) -> _Room:
    """The room a board already leaves (Fill the rest)."""
    room = _Room(used=set(occupants(layout)[0]) | set(layout.cuts))
    for p in layout.parts:
        part = board.get(p.ref)
        if part is not None:
            covered = body_holes(part, p.holes, p.standing)
            room.bodies |= covered
            if not (part.footprint.shape == "axial" and not p.standing):
                room.hard |= covered
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


def _shaped(part: BoardPart, legs: dict[str, Hole]) -> _Shape:
    xs = min(h[0] for h in legs.values())
    ys = min(h[1] for h in legs.values())
    legs = {leg: (x - xs, y - ys) for leg, (x, y) in legs.items()}
    taken = body_holes(part, legs, False) | set(legs.values())
    up = max(0, -min(h[1] for h in taken))
    down = max(h[1] for h in taken)
    left = (
        frozenset(leg for leg, h in legs.items() if h[0] == 0)
        if part.footprint.shape == "dip"
        else frozenset()
    )
    return _Shape(legs, up, down, left)


def shapes(part: BoardPart) -> list[_Shape]:
    """Every way `part` stands across the strips: a chip either way up; a line of legs
    top to bottom either way round, at each step its footprint allows (a flat resistor or
    diode from its least span to a few holes more)."""
    fp = part.footprint
    if fp.shape == "dip":
        return [
            _shaped(part, dip_legs(len(fp.order), (0, 0), t, fp.row_holes)) for t in (False, True)
        ]
    if fp.shape == "triangle":  # 1 and 3 across the strips, either way up (D-393)
        return [_shaped(part, triangle_legs(t, swapped=m)) for t in (0, 2) for m in (False, True)]
    names = part.legs
    steps = fp.steps
    if fp.shape == "axial":
        steps = tuple(range(fp.flat, fp.flat + 1 + AXIAL_SPREAD))
    found = []
    for step in steps:
        for order in (names, names[::-1]):
            found.append(_shaped(part, {leg: (0, k * step) for k, leg in enumerate(order)}))
    return found


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
    piece of their net, the rows cut at its left."""

    ref: str
    shape: _Shape
    row: int
    starts: frozenset[str]
    cuts: frozenset[int]


def _choose(r: Reading, todo: list[str], height: int, left: dict[str, int]) -> list[_Choice] | None:
    """Each part's place in a band `height` rows high, in order (module doc); `left`: each
    net's legs still to place (a net cut off while it has legs to come costs a piece).
    None when a part is taller than the band."""
    carried: list[str | None] = [None] * height
    left = dict(left)
    found = []
    for ref in todo:
        part = r.board[ref]
        best: tuple[tuple[float, int, int], _Choice] | None = None
        for k, shape in enumerate(shapes(part)):
            for row in range(shape.up, height - shape.down):
                cost, choice = _try(r, part, shape, row, carried, left)
                key = (cost, row, k)
                if best is None or key < best[0]:
                    best = (key, choice)
        if best is None:
            return None
        choice = best[1]
        for leg, (_, y) in sorted(choice.shape.legs.items(), key=lambda kv: kv[1][0]):
            net = _leg_net(r, part, leg)  # a chip's second column last: it carries on
            carried[choice.row + y] = net
            left[net] = left.get(net, 1) - 1
        found.append(choice)
    return found


def _try(r: Reading, part: BoardPart, shape: _Shape, row: int, carried: list[str | None],
         left: dict[str, int]) -> tuple[float, _Choice]:  # fmt: skip
    """The cost of `part` in `shape` with its top leg on `row`: a piece started 10, a cut
    3, a net cut off with legs still to come 5 more."""
    starts, cuts = set(), set()
    cost = 0.0
    for leg, (x, y) in shape.legs.items():
        net = _leg_net(r, part, leg)
        here = carried[row + y]
        if shape.left and x > 0:  # behind a chip's middle cut: always a piece of its own
            starts.add(leg)
            cost += 10
            continue
        if here == net:
            continue
        starts.add(leg)
        cost += 10
        if here is not None:
            cuts.add(row + y)
            cost += 3 + 5 * (left.get(here, 0) > 0)
    return cost, _Choice(part.ref, shape, row, frozenset(starts), frozenset(cuts))


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
            way = next((h for _, _, h in ways if plan.room.free(h[0], h[1], row)), None)
            if way is None:
                plan.left.append(
                    f"{net}: no free column runs down from its copper on the board to its "
                    "new strip. Lay a link to join them, or Start over."
                )
                continue
            plan.room.link(way[0], way[1], row)


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
    right), a hole kept beside each leg starting a piece wired off the board (`lone`)."""
    room, part, shape = plan.room, r.board[choice.ref], choice.shape
    legs = {leg: (x + shift, top + choice.row + y) for leg, (x, y) in shape.legs.items()}
    body = body_holes(part, legs, False)
    if min(h[0] for h in [*legs.values(), *body]) < 0 or _overhangs(part, legs):
        return None
    for h in legs.values():
        if h in room.used or h in room.bodies or h in room.over:
            return None
    hard = part.footprint.shape != "axial"
    for h in body:
        if h in room.used or h in room.bodies or (hard and h in room.over):
            return None
    taken = _Room(used=set(legs.values()), bodies=set(body), hard=set(body) if hard else set())
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
    nets = {leg: _leg_net(r, part, leg) for leg in legs}
    linked = [leg for leg in part.legs if leg in choice.starts and nets[leg] in bus]
    for leg in (leg for leg in linked if leg in shape.left):
        (column, row), to = legs[leg], bus[nets[leg]]
        found = (c for c in range(after[row], column) if room.free(c, row, to, taken))
        at = next(found, None)
        if at is None:
            return None
        taken.link(at, row, to)
    right = max(h[0] for h in [*legs.values(), *body]) + 1
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
    room.hard |= taken.hard
    room.over |= taken.over
    room.links += taken.links
    plan.cuts |= set(spot.cuts)
    for column, row in [*spot.legs.values(), *spot.cuts, *spot.kept,
                        *(h for link in taken.links for h in (link.a, link.b))]:  # fmt: skip
        plan.last[row] = max(plan.last.get(row, -1), column)
    part = r.board[choice.ref]
    plan.parts.append(Placed(choice.ref, tuple((leg, spot.legs[leg]) for leg in part.legs)))


def _laid_out(r: Reading, circuit: Circuit, base: Layout, todo: list[str],
              choices: list[_Choice], height: int) -> tuple[Layout, list[str]]:  # fmt: skip
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
    plan = _Plan(_room(base, r.board) if not fresh else _Room())
    _join_pieces(r, plan, bus)
    lone = set(r.ends.values()) - bus.keys()
    for choice in choices:
        _lay(r, plan, choice, top, bus, lone)
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
                 table: FootprintTable, fill: bool) -> Started:  # fmt: skip
    """*Fill the rest* (`fill`: what's placed kept, the tray laid out) or *Start over* (the
    whole board laid out afresh; the parts' On / Off the board choices kept), with the
    off-board parts beside it and wired; `StartError` when there's nothing to do or a part
    can't go on a board."""
    old = layout or Layout(0, 0, ())
    base = old if fill else Layout(0, 0, (), where=old.where)
    r = read_layout(base, circuit, models, table)
    if r.unboardable:
        raise StartError(" ".join(r.unboardable))
    if not r.board:
        raise StartError("Nothing in this circuit goes on a board.")
    placed = {p.ref for p in base.parts}
    todo = _order(circuit, r, sorted(r.board.keys() - placed))
    tallest = max((min(s.up + s.down for s in shapes(r.board[ref])) for ref in todo), default=0)
    remaining = _legs_to_place(r, todo)
    best: tuple[tuple[int, int, int], Layout, list[str]] | None = None
    for height in range(tallest + 1, tallest + 2 + EXTRA_ROWS):
        choices = _choose(r, todo, height, remaining)
        if choices is None:
            continue
        made, left = _laid_out(r, circuit, base, todo, choices, height)
        key = (len(left), made.columns * made.strips, len(made.links))
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
