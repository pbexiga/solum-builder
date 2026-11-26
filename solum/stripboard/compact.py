"""*Build a full layout* (D-399): the whole board laid out afresh and made as small as
the search can, wired and checked; the same board for the same circuit everywhere.

It starts from Start a board's base (`start_for_me`, Start over), squeezes it (each line
taken out while nothing gets worse), then anneals: a fixed number of steps per seed, the
temperature by step, never by clock. The state is each board part's shape and spot;
everything else is derived from it: a cut in the middle of each gap between two nets'
legs on a strip, the links joining each net's pieces (shortest first, down a column clear
of legs, cuts and other links; under a body is fine, D-410), a bus on a free strip for a
net still in pieces, free copper for each off-board wire's pad. The cost is the board's
area first, then cuts and links, their length and how deep the pads sit; problems (no
room for a cut, a piece left unjoined, a pad with no hole) cost a forbidding penalty.
Standing resistors and diodes follow the board's choice (D-403): never tried; when
needed, each costs more than any room it saves (`STAND`), and the best board has the
fewest standing before size; preferred, free. Holes taken (legs and bodies) never
overlap, and a move
that would make two bodies' real outlines touch is refused; the touching pairs Start a
board leaves are let be (overlaps are warnings the builder decides on, D-398).

A step is quick because the board isn't re-read whole: each part's legs are kept by strip
as it moves, and only the strips a move touches have their cuts and pieces worked out
again. The area and the cuts are a lower bound on the cost, so a move that can't be
accepted is refused from them alone, before its links are laid (the same decisions as
deriving everything, sooner).
"""

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, replace

from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import PITCH, Hole, Layout, Link, Placed, StandUp
from solum.stripboard.check import check_layout, read_layout
from solum.stripboard.footprints import (
    BoardPart,
    Outline,
    body_holes,
    body_outline,
    leg_problem,
    outline_overlap,
)
from solum.stripboard.start import Stand, shapes, start_for_me
from solum.stripboard.wiring import WiringError, wire_for_me

NC = -1  # a no-connect leg: shares any strip, joins nothing
SLACK = 0.05  # mm two outlines may meet by: as the overlap warnings' (D-398)
WEIGHT = 10_000.0  # a problem's cost: more than any board's area is worth
STAND = 450.0  # a standing part, when needed (D-403): more than the room it saves
TEMP = (100.0, 2.0)  # the temperature at the first step and the last
CELL = 8  # holes: the side of a square of the outlines' grid
CHECK = 256  # steps between asking whether to go on
LO, HI = -(10**6), 10**6  # a strip's first and last piece reach the board's edges

Pos = tuple[int, int, int]  # a part's shape (index) and its legs' top-left hole
_Bussed = tuple[int, list[tuple[int, int, int]]]  # a bus's strip, the links down to it


class CompactError(ValueError):
    """The board can't be built (plain-English message)."""


@dataclass(frozen=True)
class _Variant:
    """A part's shape: its legs (leg, dx, dy from the legs' top-left), the holes it takes
    (legs and body), its body's holes, its outline (mm, at the origin) and the least box
    (columns, strips) it needs on the board."""

    legs: tuple[tuple[str, int, int], ...]
    standing: bool
    taken: tuple[Hole, ...]
    body: tuple[Hole, ...]
    outline: Outline | None
    ext: tuple[int, int, int, int]
    reach: tuple[int, int, int, int]  # the holes its outline's box spans (for the grid)
    at: dict[str, Hole]  # each leg's hole from the legs' top-left


def _variant(part: BoardPart, legs: dict[str, Hole], standing: bool) -> _Variant | None:
    x0 = min(h[0] for h in legs.values())
    y0 = min(h[1] for h in legs.values())
    legs = {k: (h[0] - x0, h[1] - y0) for k, h in legs.items()}
    if leg_problem(part, legs, standing):
        return None
    body = body_holes(part, legs, standing)
    taken = sorted(set(legs.values()) | body)
    out = body_outline(part, legs, standing)
    ax, ay = min(h[0] for h in taken), min(h[1] for h in taken)
    bx, by = max(h[0] for h in taken), max(h[1] for h in taken)
    if out:
        ax = min(ax, math.floor((out[0] + SLACK) / PITCH + 1))
        ay = min(ay, math.floor((out[1] + SLACK) / PITCH + 1))
        bx = max(bx, math.ceil((out[2] - SLACK) / PITCH - 1))
        by = max(by, math.ceil((out[3] - SLACK) / PITCH - 1))
    reach = (0, 0, 0, 0)
    if out:
        reach = (math.floor(out[0] / PITCH), math.floor(out[1] / PITCH),
                 math.ceil(out[2] / PITCH), math.ceil(out[3] / PITCH))  # fmt: skip
    return _Variant(tuple((leg, h[0], h[1]) for leg, h in legs.items()), standing,
                    tuple(taken), tuple(sorted(body)), out, (ax, ay, bx, by),
                    reach, legs)  # fmt: skip


@dataclass
class Problem:
    """The circuit as the search sees it: the board parts (`refs`, sorted), each leg's net
    as a number (`NC` for a no-connect), how many pads each net needs for the off-board
    wires, each part's shapes, and the base board the search starts from."""

    circuit: Circuit
    base: Layout
    board: dict[str, BoardPart]
    refs: list[str]
    pads: dict[int, int]
    variants: dict[str, list[_Variant]]
    nets: dict[str, list[tuple[tuple[int, int, int], ...]]]  # ref → per shape: (dx, dy, net)
    net_of: dict[tuple[str, str], int]
    stand_up: StandUp = "needed"  # standing resistors and diodes (D-403)

    @property
    def stand_cost(self) -> bool:
        """Whether a standing part counts against a board (When needed, D-403)."""
        return self.stand_up == "needed"

    def shape_of(self, ref: str, legs: dict[str, Hole], standing: bool) -> int:
        """The index of the shape `legs` stand in, added if it isn't one of `shapes`'."""
        v = _variant(self.board[ref], legs, standing)
        if v is None:
            raise CompactError(f"{ref} isn't placed as its footprint allows.")
        found = self.variants[ref]
        for i, w in enumerate(found):
            if (w.legs, w.standing) == (v.legs, v.standing):
                return i
        found.append(v)
        self.nets[ref].append(self._nets(ref, v))
        return len(found) - 1

    def _nets(self, ref: str, v: _Variant) -> tuple[tuple[int, int, int], ...]:
        return tuple((dx, dy, self.net_of[ref, leg]) for leg, dx, dy in v.legs)


def problem(layout: Layout | None, circuit: Circuit, models: ModelLibrary,
            table: FootprintTable, stand_up: StandUp | None = None) -> Problem:  # fmt: skip
    """The search's view of `circuit`, from Start a board's base (Start over, untidied:
    the parts' On / Off the board choices and the notes kept, D-398); `stand_up`: standing
    resistors and diodes (None: the board's own choice, D-403); `StartError` as Start a
    board's."""
    chosen = stand_up or (layout.stand_up if layout else "needed")
    base = start_for_me(layout, circuit, models, table, fill=False, stand_up="never").layout
    base = replace(base, stand_up=chosen)  # the search stands parts, not its base (D-403)
    r = read_layout(base, circuit, models, table)
    names: dict[str, int] = {}
    net_of: dict[tuple[str, str], int] = {}
    refs = sorted(r.board)
    for ref in refs:
        part = r.board[ref]
        for leg in part.legs:
            pin = part.pins.get(leg)
            if leg in part.free:
                net_of[ref, leg] = names.setdefault(f"{ref}#{leg}", len(names))
            elif pin is None:
                net_of[ref, leg] = NC
            else:
                net_of[ref, leg] = names.setdefault(r.nets.net_of(*pin), len(names))
    pads: dict[int, int] = defaultdict(int)
    for item in r.items:
        for lug in item.lugs:
            if lug.end in r.needed and lug.net in names:
                pads[names[lug.net]] += 1
    pb = Problem(circuit, base, r.board, refs, dict(sorted(pads.items())), {}, {}, net_of,
                 stand_up=base.stand_up)  # fmt: skip
    stand: Stand = "none" if base.stand_up == "never" else "last"
    for ref in refs:
        found: dict[tuple[object, bool], _Variant] = {}
        for shape in shapes(r.board[ref], every=True, stand=stand):
            v = _variant(r.board[ref], shape.legs, shape.standing)
            if v is not None:
                found.setdefault((v.legs, v.standing), v)
        pb.variants[ref] = list(found.values())
        pb.nets[ref] = [pb._nets(ref, v) for v in pb.variants[ref]]
    start_pos(pb)  # the base's own shapes added now: every copy's shapes number the same
    return pb


def _moved(o: Outline, x: int, y: int) -> Outline:
    return (o[0] + x * PITCH, o[1] + y * PITCH, o[2] + x * PITCH, o[3] + y * PITCH, o[4])


def _cells(v: _Variant, x: int, y: int) -> list[tuple[int, int]]:
    """The outlines' grid squares `v` at (x, y) reaches: two outlines that touch share one."""
    a, b, c, d = v.reach
    return [(i, j) for i in range((x + a) // CELL, (x + c) // CELL + 1)
            for j in range((y + b) // CELL, (y + d) // CELL + 1)]  # fmt: skip


@dataclass(frozen=True)
class _Row:
    """A strip's legs worked out: each net's pieces (net, first column, last; the first
    and last reach `LO` / `HI`, the board's edges), its cuts' columns, and the gaps between
    two nets' legs with no hole for a cut (`shorts`)."""

    pieces: tuple[tuple[int, int, int], ...]
    cuts: tuple[int, ...]
    shorts: int


def _row(legs: dict[int, int]) -> _Row:
    cores: list[list[int]] = []  # [net, first leg's column, last's]
    for x in sorted(legs):
        n = legs[x]
        if n == NC:
            continue
        if cores and cores[-1][0] == n:
            cores[-1][2] = x
        else:
            cores.append([n, x, x])
    pieces, cuts, shorts = [], [], 0
    left = LO
    for i, (n, _, hi) in enumerate(cores):
        right = HI
        if i + 1 < len(cores):
            nxt = cores[i + 1][1]
            gap = [g for g in range(hi + 1, nxt) if g not in legs]
            if gap:
                cut = gap[len(gap) // 2]
                cuts.append(cut)
                pieces.append((n, left, cut - 1))
                left = cut + 1
                continue
            shorts += 1
            right = nxt - 1
        pieces.append((n, left, right))
        left = right + 1
    return _Row(tuple(pieces), tuple(cuts), shorts)


@dataclass
class Derived:
    """A state's board: its cost, its problems, the box it fills (columns and strips,
    first and last), its cuts, how many links and their length, each net's links
    (column, top strip, bottom strip), and its standing parts that count (D-403)."""

    cost: float
    problems: int
    box: tuple[int, int, int, int]
    cuts: set[Hole]
    count: int
    length: int
    joins: dict[int, list[tuple[int, int, int]]]
    stood: int = 0  # its standing parts, counted when only needed ones should stand (D-403)

    @property
    def area(self) -> int:
        x0, y0, x1, y1 = self.box
        return (x1 - x0 + 1) * (y1 - y0 + 1)

    @property
    def links(self) -> list[Link]:
        return [Link((c, top), (c, bot)) for v in self.joins.values() for c, top, bot in v]


class State:
    """Each board part's (shape, column, strip), with what the steps ask kept up to date
    as parts move: the holes taken, the legs by strip, the bodies, the outlines by grid
    square, each strip's pieces and cuts."""

    def __init__(self, pb: Problem, pos: dict[str, Pos]) -> None:
        self.pb = pb
        self.pos: dict[str, Pos] = {}
        self.occ: dict[Hole, str] = {}
        self.legs: dict[Hole, int] = {}
        self.rows: dict[int, dict[int, int]] = {}
        self.bodies: set[Hole] = set()
        self.grid: dict[tuple[int, int], set[str]] = defaultdict(set)
        self.ends: set[Hole] = set()  # legs and bodies: no link's end goes here
        self.mids: set[Hole] = set()  # legs: no link passes over
        self.dirty: set[int] = set()
        self.done: dict[int, _Row] = {}
        self.count: dict[int, int] = defaultdict(int)  # each net's pieces
        self.cuts = 0
        self.shorts = 0
        self.joins = 0  # pieces less nets: the least links (or buses) to join them
        self.box: tuple[int, int, int, int] | None = None  # the parts' (None: work it out)
        self.standing = 0  # parts standing
        for ref in pb.refs:
            self.pos[ref] = pos[ref]
            self._put(ref)

    def _v(self, ref: str) -> _Variant:
        return self.pb.variants[ref][self.pos[ref][0]]

    def _outline(self, ref: str) -> Outline | None:
        vi, x, y = self.pos[ref]
        o = self.pb.variants[ref][vi].outline
        return _moved(o, x, y) if o else None

    def _put(self, ref: str) -> None:
        vi, x, y = self.pos[ref]
        v = self.pb.variants[ref][vi]
        self.standing += v.standing
        for dx, dy in v.taken:
            h = (x + dx, y + dy)
            if h in self.occ:
                raise CompactError(f"{ref} and {self.occ[h]} share a hole on the base board.")
            self.occ[h] = ref
        for dx, dy, n in self.pb.nets[ref][vi]:
            self.legs[x + dx, y + dy] = n
            self.ends.add((x + dx, y + dy))
            self.mids.add((x + dx, y + dy))
            self.rows.setdefault(y + dy, {})[x + dx] = n
            self.dirty.add(y + dy)
        for dx, dy in v.body:
            self.bodies.add((x + dx, y + dy))
            self.ends.add((x + dx, y + dy))
        if v.outline:
            for cell in _cells(v, x, y):
                self.grid[cell].add(ref)
        if self.box:
            ax, ay, bx, by = v.ext
            x0, y0, x1, y1 = self.box
            self.box = (min(x0, x + ax), min(y0, y + ay), max(x1, x + bx), max(y1, y + by))

    def _take(self, ref: str) -> None:
        vi, x, y = self.pos[ref]
        v = self.pb.variants[ref][vi]
        self.standing -= v.standing
        for dx, dy in v.taken:
            del self.occ[x + dx, y + dy]
        for dx, dy, _ in self.pb.nets[ref][vi]:
            del self.legs[x + dx, y + dy]
            self.ends.discard((x + dx, y + dy))
            self.mids.discard((x + dx, y + dy))
            row = self.rows[y + dy]
            del row[x + dx]
            if not row:
                del self.rows[y + dy]
            self.dirty.add(y + dy)
        for dx, dy in v.body:
            self.bodies.discard((x + dx, y + dy))
            self.ends.discard((x + dx, y + dy))
        if v.outline:
            for cell in _cells(v, x, y):
                self.grid[cell].discard(ref)
        if self.box:
            ax, ay, bx, by = v.ext
            x0, y0, x1, y1 = self.box
            if x + ax == x0 or y + ay == y0 or x + bx == x1 or y + by == y1:
                self.box = None

    def _free(self, ref: str) -> bool:
        """Whether `ref` at its (new) spot takes no hole taken and touches no body."""
        vi, x, y = self.pos[ref]
        v = self.pb.variants[ref][vi]
        occ = self.occ
        for dx, dy in v.taken:
            if (x + dx, y + dy) in occ:
                return False
        if v.outline:
            a = _moved(v.outline, x, y)
            seen: set[str] = set()
            for cell in _cells(v, x, y):
                for other in self.grid.get(cell, ()):
                    if other in seen:
                        continue
                    seen.add(other)
                    b = self._outline(other)
                    if (b and b[0] < a[2] and a[0] < b[2] and b[1] < a[3] and a[1] < b[3]
                            and outline_overlap(a, b) > SLACK):  # fmt: skip
                        return False
        return True

    def move(self, changes: dict[str, Pos]) -> dict[str, Pos] | None:
        """Several parts to new spots at once; None (and nothing changed) if refused."""
        old = {ref: self.pos[ref] for ref in changes}
        for ref in changes:
            self._take(ref)
        put: list[str] = []
        for ref, p in changes.items():
            self.pos[ref] = p
            if not self._free(ref):
                for done in put:
                    self._take(done)
                for r, q in old.items():
                    self.pos[r] = q
                    self._put(r)
                return None
            self._put(ref)
            put.append(ref)
        return old

    def undo(self, old: dict[str, Pos]) -> None:
        for ref in old:
            self._take(ref)
        for ref, p in old.items():
            self.pos[ref] = p
            self._put(ref)

    def _refresh(self) -> None:
        count = self.count
        for y in self.dirty:
            gone = self.done.pop(y, None)
            if gone:
                self.cuts -= len(gone.cuts)
                self.shorts -= gone.shorts
                for n, _, _ in gone.pieces:
                    count[n] -= 1
                    self.joins -= count[n] > 0
            legs = self.rows.get(y)
            if legs:
                row = _row(legs)
                self.done[y] = row
                self.cuts += len(row.cuts)
                self.shorts += row.shorts
                for n, _, _ in row.pieces:
                    self.joins += count[n] > 0
                    count[n] += 1
        self.dirty.clear()

    def parts_box(self) -> tuple[int, int, int, int]:
        if self.box:
            return self.box
        x0 = y0 = HI
        x1 = y1 = LO
        variants = self.pb.variants
        for ref, (vi, x, y) in self.pos.items():
            ax, ay, bx, by = variants[ref][vi].ext
            x0, y0 = min(x0, x + ax), min(y0, y + ay)
            x1, y1 = max(x1, x + bx), max(y1, y + by)
        self.box = (x0, y0, x1, y1)
        return self.box

    def stood(self) -> int:
        """The standing parts that count against the board (When needed, D-403)."""
        return self.standing if self.pb.stand_cost else 0

    def lower(self) -> float:
        """A lower bound on `derive`'s cost: the parts' area and standing parts, the cuts,
        the shorts, and a link at least a strip long for each join a net needs (or a
        problem, dearer)."""
        self._refresh()
        x0, y0, x1, y1 = self.parts_box()
        area = (x1 - x0 + 1) * (y1 - y0 + 1)
        return (100 * area + STAND * self.stood() + 3 * self.cuts + 4 * self.joins
                + WEIGHT * self.shorts)  # fmt: skip

    def derive(self) -> "Derived":
        """The board this state makes (module doc) and its cost."""
        self._refresh()
        x0, y0, x1, y1 = self.parts_box()
        stops, mids = self.ends, self.mids
        cuts: set[Hole] = set()
        found: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        for y, row in self.done.items():
            cuts.update((c, y) for c in row.cuts)
            for n, lo, hi in row.pieces:
                found[n].append((y, max(lo, x0), min(hi, x1)))
        pieces = {n: tuple(sorted(ps)) for n, ps in found.items()}
        ends: set[Hole] = set()
        over: set[Hole] = set()
        joins: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        buses: dict[int, int] = {}

        def clear(c: int, top: int, bot: int) -> bool:
            for h in ((c, top), (c, bot)):
                if h in stops or h in cuts or h in ends or h in over:
                    return False
            for q in range(top + 1, bot):
                h = (c, q)
                if h in mids or h in cuts or h in ends:
                    return False
            return True

        def lay(n: int, c: int, top: int, bot: int) -> None:
            joins[n].append((c, top, bot))
            ends.update(((c, top), (c, bot)))
            over.update((c, q) for q in range(top + 1, bot))

        taken_rows = set(self.rows)
        todo = {n for n, ps in pieces.items() if len(ps) > 1}
        # links: shortest first over every net's pieces (Kruskal)
        parent: dict[tuple[int, int], tuple[int, int]] = {}
        cands = []
        for n in todo:
            ps = pieces[n]
            for i in range(len(ps)):
                parent[n, i] = (n, i)
                ra, la, ha = ps[i]
                for j in range(i + 1, len(ps)):
                    rb, lb, hb = ps[j]
                    if ra != rb and max(la, lb) <= min(ha, hb):
                        cands.append((abs(ra - rb), n, i, j, max(la, lb), min(ha, hb)))
        cands.sort()

        def find(k: tuple[int, int]) -> tuple[int, int]:
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        for _, n, i, j, lo, hi in cands:
            a, b = find((n, i)), find((n, j))
            if a == b:
                continue
            ra, rb = pieces[n][i][0], pieces[n][j][0]
            top, bot = min(ra, rb), max(ra, rb)
            pick = next((c for c in range(lo, hi + 1) if clear(c, top, bot)), None)
            if pick is not None:
                parent[a] = b
                lay(n, pick, top, bot)
        # buses: a net still in pieces takes a free strip (or a new one above or below),
        # each of its joined groups linked to it down a free column
        unjoined = 0
        for n in sorted(todo):
            ps = pieces[n]
            comps: dict[tuple[int, int], list[int]] = defaultdict(list)
            for i in range(len(ps)):
                comps[find((n, i))].append(i)
            if len(comps) < 2:
                continue
            bus = self._bus(ps, comps, taken_rows, (x0, y0, x1, y1), clear)
            if bus is None:
                unjoined += len(comps) - 1
                continue
            r, got = bus
            taken_rows.add(r)
            buses[n] = r
            y0, y1 = min(y0, r), max(y1, r)
            for c, top, bot in got:
                lay(n, c, top, bot)
        # pads: free copper on the net, the shallowest holes
        padless = 0
        depth = 0
        for n, k in self.pb.pads.items():
            free = []
            copper = pieces.get(n, ())
            if n in buses:
                copper = (*copper, (buses[n], x0, x1))
            for y, lo, hi in copper:
                # a hole's depth rises from the piece's ends inwards: its k shallowest
                # free holes are among the first k free from each end
                dy = min(y - y0, y1 - y)
                had, x = 0, lo
                while x <= hi and had < k:
                    h = (x, y)
                    if not (h in stops or h in cuts or h in ends or h in over):
                        free.append(min(x - x0, x1 - x, dy))
                        had += 1
                    x += 1
                had, z = 0, hi
                while z >= x and had < k:
                    h = (z, y)
                    if not (h in stops or h in cuts or h in ends or h in over):
                        free.append(min(z - x0, x1 - z, dy))
                        had += 1
                    z -= 1
            if len(free) < k:
                padless += k - len(free)
            free.sort()
            depth += sum(free[:k])
        problems = self.shorts + unjoined + padless
        stood = self.stood()
        area = (x1 - x0 + 1) * (y1 - y0 + 1)
        count = sum(len(v) for v in joins.values())
        length = sum(bot - top for v in joins.values() for _, top, bot in v)
        cost = (100 * area + 3 * (len(cuts) + count) + length + 0.5 * depth
                + STAND * stood + WEIGHT * problems)  # fmt: skip
        return Derived(cost, problems, (x0, y0, x1, y1), cuts, count, length, dict(joins), stood)

    @staticmethod
    def _bus(ps: tuple[tuple[int, int, int], ...], comps: dict[tuple[int, int], list[int]],
             taken_rows: set[int], box: tuple[int, int, int, int],
             clear: Callable[[int, int, int], bool]) -> "_Bussed | None":  # fmt: skip
        """The strip a net's joined groups `comps` are bussed on, and the links down to it:
        the free strip (or a new one above or below, dearer) with the least links' length;
        None when none has a free column for every group."""
        x0, y0, x1, y1 = box
        best: tuple[int, int, list[tuple[int, int, int]]] | None = None
        rows_of = [sorted({ps[i][0] for i in members}) for members in comps.values()]
        edge = 300 * (x1 - x0 + 1)
        tried = []  # each free strip's least total, for the hopeless to be skipped
        for r in range(y0 - 1, y1 + 2):
            if r not in taken_rows:
                least = sum(min(abs(q - r) for q in qs) for qs in rows_of)
                tried.append((least + (edge if r in (y0 - 1, y1 + 1) else 0), r))
        tried.sort()
        for least, r in tried:
            if best is not None and (least, r) > (best[0], best[1]):
                break
            total = edge if r in (y0 - 1, y1 + 1) else 0
            got: list[tuple[int, int, int]] = []
            columns: set[int] = set()  # one link per column to a bus (two would meet)
            for members in comps.values():
                pick = None
                for i in members:
                    py, lo, hi = ps[i]
                    top, bot = min(py, r), max(py, r)
                    if pick and pick[0] <= bot - top:
                        continue
                    for c in range(lo, hi + 1):
                        if c not in columns and clear(c, top, bot):
                            pick = (bot - top, c, top, bot)
                            break
                if pick is None:
                    break
                got.append(pick[1:])
                columns.add(pick[1])
                total += pick[0]
            else:
                if best is None or (total, r) < (best[0], best[1]):
                    best = (total, r, got)
        return None if best is None else (best[1], best[2])


# standing parts when only needed ones should stand (D-403), area, cuts + links, links' length
Key = tuple[int, int, int, int]


def key(d: Derived) -> Key:
    return (d.stood, d.area, len(d.cuts) + d.count, d.length)


@dataclass(frozen=True)
class Found:
    """The best board a seed found: its key, its size, and each part's spot."""

    key: Key
    seed: int
    columns: int
    strips: int
    cuts: int
    links: int
    pos: tuple[tuple[str, Pos], ...]


def _found(d: Derived, seed: int, pos: dict[str, Pos]) -> Found:
    x0, y0, x1, y1 = d.box
    return Found(key(d), seed, x1 - x0 + 1, y1 - y0 + 1, len(d.cuts), d.count,
                 tuple(pos.items()))  # fmt: skip


def start_pos(pb: Problem) -> dict[str, Pos]:
    """Each part's spot on the base board."""
    return positions(pb, pb.base)


def positions(pb: Problem, layout: Layout) -> dict[str, Pos]:
    """Each part's spot on `layout` as the search numbers it (its shape, its legs'
    top-left)."""
    pos = {}
    for p in layout.parts:
        holes = p.holes
        x, y = min(h[0] for h in holes.values()), min(h[1] for h in holes.values())
        pos[p.ref] = (pb.shape_of(p.ref, holes, p.standing), x, y)
    return pos


def _shift(pos: dict[str, Pos], axis: int, line: int, sign: int) -> dict[str, Pos]:
    """Every part past `line` (right of / below it for `sign` 1, left / above for -1)
    one hole back towards it."""
    changes = {}
    for ref, (vi, x, y) in pos.items():
        at = x if axis == 0 else y
        if (at > line) if sign > 0 else (at < line):
            changes[ref] = (vi, x - sign, y) if axis == 0 else (vi, x, y - sign)
    return changes


def squeeze(st: State, cur: Derived) -> Derived:
    """Each line taken out (everything past it one hole in) while nothing gets worse."""
    changed = True
    while changed:
        changed = False
        for axis in (0, 1):
            x0, y0, x1, y1 = cur.box
            lo, hi = (x0, x1) if axis == 0 else (y0, y1)
            for line in range(hi, lo - 1, -1):
                changes = _shift(st.pos, axis, line, 1)
                if not changes or (old := st.move(changes)) is None:
                    continue
                if st.lower() >= cur.cost:
                    st.undo(old)
                    continue
                new = st.derive()
                if new.problems <= cur.problems and new.cost < cur.cost:
                    cur, changed = new, True
                else:
                    st.undo(old)
    return cur


Going = Callable[[int, Found | None], bool]  # (steps done, best so far) → go on?


def search(pb: Problem, steps: int, seed: int, going: Going | None = None,
           flat: bool = False) -> Found | None:  # fmt: skip
    """The smallest board one seed finds in `steps` steps (module doc), or None when every
    board it saw had a problem. `going` is asked every `CHECK` steps; False stops early
    with the best so far; it's told the steps done at the end. `flat`: no standing shape
    chosen (the flat attempt, D-403: the same board as Never's search with this seed)."""
    rng = random.Random(seed)
    shapes = {ref: [i for i, v in enumerate(pb.variants[ref]) if not (flat and v.standing)]
              for ref in pb.refs}  # fmt: skip
    st = State(pb, start_pos(pb))
    refs = pb.refs
    cur = squeeze(st, st.derive())
    best = _found(cur, seed, st.pos) if not cur.problems else None
    t0, t1 = TEMP
    done = steps
    for step in range(steps):
        if going and step % CHECK == 0 and not going(step, best):
            done = step
            break
        temp = t0 * (t1 / t0) ** (step / steps)
        changes = _move(rng, st, cur, refs, shapes)
        if not changes or (old := st.move(changes)) is None:
            continue
        # accepted when cost < cur.cost + temp·(−ln r), or no worse (Metropolis)
        r = rng.random()
        limit = cur.cost - temp * math.log(r) if r > 0 else math.inf
        lower = st.lower()
        if lower > cur.cost and lower >= limit:
            st.undo(old)
            continue
        new = st.derive()
        if new.cost <= cur.cost or new.cost < limit:
            cur = new
            if not new.problems and (best is None or key(new) < best.key):
                best = _found(new, seed, st.pos)
        else:
            st.undo(old)
    if going:
        going(done, best)
    return best


def _move(rng: random.Random, st: State, cur: Derived, refs: list[str],
          shapes: dict[str, list[int]]) -> dict[str, Pos]:  # fmt: skip
    """A random move: a long jump, a shift, another shape (a leg kept in its hole), a swap
    of two parts' spots, or a squeeze of everything past a line; `shapes`: each part's
    shapes it may take."""
    variants = st.pb.variants
    kind = rng.random()
    if kind < 0.05:  # a long jump: anywhere on the board, any shape
        ref = rng.choice(refs)
        x0, y0, x1, y1 = cur.box
        return {ref: (rng.choice(shapes[ref]), rng.randint(x0, x1), rng.randint(y0, y1))}
    if kind < 0.45:  # shift one part
        ref = rng.choice(refs)
        vi, x, y = st.pos[ref]
        step = 1 if rng.random() < 0.7 else rng.randint(2, 5)
        dx, dy = rng.choice(((step, 0), (-step, 0), (0, step), (0, -step)))
        if rng.random() < 0.2:
            dx, dy = rng.randint(-step, step), rng.randint(-step, step)
        return {ref: (vi, x + dx, y + dy)}
    if kind < 0.65:  # another shape, a leg kept in its hole
        ref = rng.choice(refs)
        vi, x, y = st.pos[ref]
        vs = variants[ref]
        if len(shapes[ref]) < 2:
            return {}
        wi = rng.choice(shapes[ref])
        if wi == vi:
            return {}
        leg, ox, oy = rng.choice(vs[vi].legs)
        nx, ny = next((dx, dy) for lg, dx, dy in vs[wi].legs if lg == leg)
        return {ref: (wi, x + ox - nx, y + oy - ny)}
    if kind < 0.80:  # swap two parts' spots
        a, b = rng.sample(refs, 2)
        (va, xa, ya), (vb, xb, yb) = st.pos[a], st.pos[b]
        return {a: (va, xb, yb), b: (vb, xa, ya)}
    x0, y0, x1, y1 = cur.box  # squeeze: everything past a line one hole in
    axis = 0 if rng.random() < 0.5 else 1
    line = rng.randint(x0, x1) if axis == 0 else rng.randint(y0, y1)
    sign = 1 if rng.random() < 0.5 else -1
    return _shift(st.pos, axis, line, sign)


def best_of(found: Iterable[Found | None]) -> Found | None:
    """The best over seeds: the smallest key, then the lowest seed."""
    return min((f for f in found if f), key=lambda f: (f.key, f.seed), default=None)


def board_of(pb: Problem, found: Found) -> Layout:
    """`found` as a board (not yet wired), keeping the base's On / Off choices, notes and
    dismissals."""
    st = State(pb, dict(found.pos))
    d = st.derive()
    x0, y0, x1, y1 = d.box
    parts = []
    for ref in pb.refs:
        vi, x, y = st.pos[ref]
        v = pb.variants[ref][vi]
        legs = {leg: (x + dx - x0, y + dy - y0) for leg, dx, dy in v.legs}
        parts.append(Placed(ref, tuple((leg, legs[leg]) for leg in pb.board[ref].legs),
                            v.standing))  # fmt: skip
    cuts = frozenset((x - x0, y - y0) for x, y in d.cuts)
    links = tuple(Link((k.a[0] - x0, k.a[1] - y0), (k.b[0] - x0, k.b[1] - y0)) for k in d.links)
    return replace(pb.base, columns=x1 - x0 + 1, strips=y1 - y0 + 1, parts=tuple(parts),
                   cuts=cuts, links=links, wires=(), spots=())  # fmt: skip


@dataclass(frozen=True)
class Built:
    """The board built: `layout` wired and checked, and whether it's the base because the
    search did no better (`fell_back`)."""

    layout: Layout
    fell_back: bool


def _flat_again(st: State, cur: Derived, ref: str) -> Derived | None:
    """Standing `ref` laid flat (each flat shape, a leg kept in its hole) where that fits
    with no problem; the move left made and the board it makes, else None and nothing
    changed."""
    vi, x, y = st.pos[ref]
    v = st.pb.variants[ref][vi]
    for wi, w in enumerate(st.pb.variants[ref]):
        if w.standing:
            continue
        for leg, (ox, oy) in v.at.items():
            nx, ny = w.at[leg]
            if (old := st.move({ref: (wi, x + ox - nx, y + oy - ny)})) is None:
                continue
            d = st.derive()
            if not d.problems:
                return d
            st.undo(old)
    return None


def standing_unneeded(pb: Problem, pos: dict[str, Pos]) -> list[str]:
    """The standing parts on the board at `pos` that could lie flat again (`_flat_again`):
    standing only for room (D-403)."""
    st = State(pb, dict(pos))
    cur = st.derive()
    found = []
    for ref in pb.refs:
        if st._v(ref).standing:
            was = dict(st.pos)
            if _flat_again(st, cur, ref) is not None:
                found.append(ref)
                st.undo({ref: was[ref]})
    return found


def lay_flat(pb: Problem, found: Found) -> Found:
    """When needed (D-403): `found` with each standing part that can lie flat laid flat
    again (`_flat_again`), in the parts' order, until none can be: the search prefers fewer standing
    parts only among the boards it saw."""
    st = State(pb, dict(found.pos))
    cur = st.derive()
    changed = True
    while changed:
        changed = False
        for ref in pb.refs:
            if st._v(ref).standing and (d := _flat_again(st, cur, ref)) is not None:
                cur, changed = d, True
    return _found(cur, found.seed, st.pos)


def finish(pb: Problem, found: Found | None, models: ModelLibrary,
           table: FootprintTable) -> Built:  # fmt: skip
    """`found` wired (Wire it for me) and checked, its unneeded standing parts laid flat
    when needed (`lay_flat`); the base when there's nothing found, it doesn't pass the
    check, or it's no better than the base (standing parts when needed, then size)."""
    if found is not None and pb.stand_up == "needed":
        found = lay_flat(pb, found)
    was = State(pb, start_pos(pb)).derive()
    if found is None or found.key[:2] >= key(was)[:2]:
        return Built(pb.base, True)
    return finish_layout(pb, board_of(pb, found), models, table)


def finish_layout(pb: Problem, board: Layout, models: ModelLibrary,
                  table: FootprintTable) -> Built:  # fmt: skip
    """A board the search found (`board_of`; the best so far when the builder stops it)
    wired and checked; the base when it doesn't pass the check, or isn't smaller."""
    base = pb.base
    with suppress(WiringError):  # nothing to wire
        board = wire_for_me(replace(board, wires=()), pb.circuit, models, table)
    if not check_layout(board, pb.circuit, models, table).ok:
        return Built(base, True)
    smaller = board.columns * board.strips < base.columns * base.strips
    return Built(board, False) if smaller else Built(base, True)
