"""Guidance as the board is built (D-377): where each net's copper is free to take a leg
(the holes marked for a part being carried), the ratsnest (what each net still has to
join), the cuts and links the legs call for (suggested, never made behind the builder's
back), and what to place next.

All of it is read off the board the way the check reads it (`check.read_layout`): one
notion of a net, of a joined group, of who sits in a hole. Pure: a layout and its circuit
in, holes and sentences out.
"""

import heapq
from collections import defaultdict
from dataclasses import dataclass, field, replace
from itertools import pairwise

from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.rules.graph import distances, signal_edges
from solum.stripboard.board import Hole, Layout, Link, hole_name, segments
from solum.stripboard.check import (
    Reading,
    Terminal,
    copper_groups,
    groups_by_net,
    joined_groups,
    occupants,
    read_layout,
    runs,
)
from solum.stripboard.footprints import body_holes

Run = tuple[int, int, int]  # (strip, first column, last column), as `check.runs`


@dataclass(frozen=True)
class Strand:
    """One ratsnest line: two pieces of `net` the board doesn't join yet, by their nearest
    holes."""

    net: str
    a: Hole
    b: Hole


@dataclass(frozen=True)
class Next:
    """The part to place next and why, in a sentence."""

    ref: str
    why: str


@dataclass(frozen=True)
class Guidance:
    """`marks`: each net's free copper holes (runs) on the groups that carry that net and
    no other: where a leg on that net joins it; `ratsnest`: the strands still to join;
    `cuts` and `links`: the ones the legs call for, suggested; `stuck`: a sentence per
    join no suggested link makes, why and what to do; `next`: what to place next (None:
    nothing left, or nothing placeable)."""

    marks: dict[str, list[Run]]
    ratsnest: list[Strand]
    cuts: list[Hole]
    links: list[tuple[Hole, Hole]]
    stuck: list[str]
    next: Next | None


def _blocked(r: Reading) -> tuple[set[Hole], set[Hole], set[Hole]]:
    """The holes something sits in (a leg, a link's end, a pad), the holes under a body
    that a link can't pass under (a standing or radial or chip body), and the holes under
    any body."""
    used = set(occupants(r.layout)[0])
    hard: set[Hole] = set()
    bodies: set[Hole] = set()
    for p in r.layout.parts:
        part = r.board.get(p.ref)
        if part is None:
            continue
        covered = body_holes(part, p.holes, p.standing)
        bodies |= covered
        if not (part.footprint.shape == "axial" and not p.standing):
            hard |= covered
    return used, hard, bodies


def _terminal_holes(r: Reading) -> dict[Terminal, Hole]:
    """Every terminal the board holds in a hole (a leg, a lug's pad) on its net."""
    return {t: r.words.hole_of[t] for t in r.expected if t in r.words.hole_of}


def marks(r: Reading) -> dict[str, list[Run]]:
    """Each net's free copper holes, as runs, on the joined groups carrying only it."""
    copper, _ = joined_groups(r.layout)
    used, _, bodies = _blocked(r)
    only = {g: next(iter(here)) for g, here in groups_by_net(r).items() if len(here) == 1}
    free: dict[str, set[Hole]] = defaultdict(set)
    for hole, group in copper.items():
        if group in only and hole not in used and hole not in bodies:
            free[only[group]].add(hole)
    return {net: runs(holes) for net, holes in sorted(free.items())}


def _distance(a: Hole, b: Hole) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def ratsnest(r: Reading) -> list[Strand]:
    """Per net, the fewest, shortest strands that would join its pieces (a spanning tree
    over its joined groups, each strand between the pieces' nearest holes)."""
    holes = _terminal_holes(r)
    pieces: dict[str, dict[int, list[Hole]]] = defaultdict(lambda: defaultdict(list))
    for t, hole in sorted(holes.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        pieces[r.expected[t]][r.groups[t]].append(hole)
    found = []
    for net in sorted(pieces):
        groups = list(pieces[net].values())
        if len(groups) < 2:
            continue
        joined = {0}
        while len(joined) < len(groups):  # Prim's: the nearest piece not joined yet
            best = min(
                ((_distance(a, b), a, b, j) for i in joined for j in range(len(groups))
                 if j not in joined for a in groups[i] for b in groups[j]),
                key=lambda c: (c[0], c[1][1], c[1][0], c[2][1], c[2][0]),
            )  # fmt: skip
            found.append(Strand(net, best[1], best[2]))
            joined.add(best[3])
    return found


def suggested_cuts(r: Reading) -> list[Hole]:
    """A cut wherever a strip's copper carries two nets side by side: in the first free
    hole after the left one's last terminal (none free between them: no cut can part
    them, and none is suggested)."""
    holes = _terminal_holes(r)
    used, _, _ = _blocked(r)
    seg = segments(r.layout)
    along: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for t, hole in holes.items():
        if hole in seg:
            along[seg[hole]].append((hole[0], r.expected[t]))
    strip_of = {n: h[1] for h, n in seg.items()}
    cuts = []
    for number, row in sorted(along.items()):
        row.sort()
        for (x1, net1), (x2, net2) in pairwise(row):
            if net1 == net2:
                continue
            strip = strip_of[number]
            free = [x for x in range(x1 + 1, x2) if (x, strip) not in used]
            if free:
                cuts.append((free[0], strip))
    return sorted(set(cuts), key=lambda h: (h[1], h[0]))


@dataclass
class _Linking:
    """The board as the link search sees it, the suggested cuts made: `copper` each hole's
    group; `used` the holes something sits in (and the cuts); `hard` the holes under a body
    no link passes under; `bodies` under any body; `crossed` the holes under a link, where
    no link may end; `own` each group carrying one net, that net; `free` each own group's
    free holes by column; `taken` the suggested links' ends; `pieces` each net's groups
    joined into pieces by the suggested links."""

    copper: dict[Hole, int]
    used: set[Hole]
    hard: set[Hole]
    bodies: set[Hole]
    crossed: set[Hole]
    own: dict[int, str]
    free: dict[tuple[int, int], list[Hole]]
    taken: set[Hole] = field(default_factory=set)
    pieces: dict[str, list[list[int]]] = field(default_factory=dict)


def _linking(r: Reading, cuts: list[Hole]) -> tuple[_Linking, list[tuple[Hole, Hole]]]:
    """The link search (`suggested_links`), and what it saw, for `stuck`."""
    cut = replace(r.layout, cuts=r.layout.cuts | set(cuts))
    copper = copper_groups(cut)
    used, hard, bodies = _blocked(r)
    used |= set(cuts)
    crossed = {h for link in r.layout.links for h in link.between}
    nets_of: dict[int, set[str]] = defaultdict(set)
    for t, hole in _terminal_holes(r).items():
        if hole in copper:
            nets_of[copper[hole]].add(r.expected[t])
    own = {g: next(iter(n)) for g, n in nets_of.items() if len(n) == 1}
    free: dict[tuple[int, int], list[Hole]] = defaultdict(list)  # (group, column) → holes
    for hole, group in copper.items():
        if group in own and hole not in used and hole not in bodies:
            free[(group, hole[0])].append(hole)
    k = _Linking(copper, used, hard, bodies, set(crossed), own, free)
    by_net: dict[str, list[int]] = defaultdict(list)
    for g, net in sorted(own.items()):
        by_net[net].append(g)
    links: list[tuple[Hole, Hole]] = []
    for net in sorted(by_net):
        groups = by_net[net]
        heap: list[tuple[int, Hole, Hole, int, int]] = []
        for i, ga in enumerate(groups):
            for gb in groups[i + 1 :]:
                for column in range(cut.columns):
                    for a in free.get((ga, column), ()):
                        for b in free.get((gb, column), ()):
                            if _link_blocker(k, a, b) is None:
                                top, bottom = sorted((a, b), key=lambda h: h[1])
                                heap.append((bottom[1] - top[1], top, bottom, ga, gb))
        heapq.heapify(heap)
        parent = {g: g for g in groups}

        def find(g: int, parent: dict[int, int] = parent) -> int:
            while parent[g] != g:
                g = parent[g]
            return g

        while heap:  # Kruskal's: the shortest link between two pieces not yet joined
            _, top, bottom, ga, gb = heapq.heappop(heap)
            if find(ga) == find(gb) or _link_blocker(k, top, bottom) is not None:
                continue
            parent[find(ga)] = find(gb)
            k.taken |= {top, bottom}
            k.crossed |= set(Link(top, bottom).between)
            links.append((top, bottom))
        pieces: dict[int, list[int]] = defaultdict(list)
        for g in groups:
            pieces[find(g)].append(g)
        k.pieces[net] = list(pieces.values())
    return k, links


def _link_blocker(k: _Linking, a: Hole, b: Hole) -> Hole | None:
    """The first hole in the way of a link from `a` to `b` (an end under a link or on a
    suggested link's end; a leg, pad, link end or cut it passes over, a body it can't pass
    under), or None when it can be laid."""
    for end in (a, b):
        if end in k.crossed or end in k.taken:
            return end
    top, bottom = sorted((a, b), key=lambda h: h[1])
    for h in Link(top, bottom).between:
        if h in k.used or h in k.hard or h in k.taken:
            return h
    return None


def suggested_links(r: Reading, cuts: list[Hole]) -> list[tuple[Hole, Hole]]:
    """With the suggested cuts made, the shortest links joining each net's pieces: down a
    free column, both ends in free copper of the net's own groups, over no leg, pad or
    link end, under no body but a flat resistor's (as the check allows), and no end under
    another link, laid or suggested."""
    return _linking(r, cuts)[1]


def _in_the_way(r: Reading, k: _Linking, hole: Hole) -> tuple[str, str | None]:
    """What sits in `hole`, in words, and the part to move (None: not a part)."""
    name = hole_name(hole)
    for t, h in _terminal_holes(r).items():
        if h == hole:
            board_ref = r.words.leg_of.get(t, ("", ""))[0] if not isinstance(t, str) else None
            return r.words(t), board_ref or None
    for p in r.layout.parts:
        if hole in p.holes.values():
            return f"{p.ref}'s leg at {name}", p.ref
    for link in r.layout.links:
        if hole in (link.a, link.b) or hole in link.between:
            return f"the link from {hole_name(link.a)} to {hole_name(link.b)}", None
    if hole in r.layout.cuts:
        return f"the cut at {name}", None
    for p in r.layout.parts:
        part = r.board.get(p.ref)
        if part and hole in body_holes(part, p.holes, p.standing):
            return f"{p.ref}'s body at {name}", p.ref
    if hole in k.taken or hole in k.crossed:
        return f"a suggested link at {name}", None
    return f"the suggested cut at {name}", None


def stuck(r: Reading, cuts: list[Hole]) -> list[str]:
    """Per net whose pieces no suggested link joins, a sentence saying why and what to do:
    a piece with no free hole for a link, two pieces with no column free on both (both on
    one strip, say), or every link that would join them blocked (by what)."""
    return _stuck(r, _linking(r, cuts)[0])


def _stuck(r: Reading, k: _Linking) -> list[str]:
    holes = _terminal_holes(r)
    said = []
    for net, pieces in sorted(k.pieces.items()):
        if len(pieces) < 2:
            continue
        ordered = sorted(holes.items(), key=lambda kv: (kv[1][1], kv[1][0]))
        ends = [[(t, h) for t, h in ordered if k.copper.get(h) in piece and r.expected[t] == net]
                for piece in pieces]  # fmt: skip
        joined = [0]
        while len(joined) < len(pieces):  # Prim's: the nearest piece not joined yet
            _, i, j, ta, tb = min(
                ((_distance(ha, hb), i, j, ta, tb) for i in joined for j in range(len(pieces))
                 if j not in joined for ta, ha in ends[i] for tb, hb in ends[j]),
                key=lambda c: c[0],
            )  # fmt: skip
            joined.append(j)
            said.append(_why_stuck(r, k, net, pieces[i], pieces[j], ta, tb))
    return said


def _why_stuck(r: Reading, k: _Linking, net: str, ga: list[int], gb: list[int],
               ta: Terminal, tb: Terminal) -> str:  # fmt: skip
    wa, wb = r.words(ta), r.words(tb)
    ha, hb = r.words.hole_of[ta], r.words.hole_of[tb]
    free_a = [h for (g, _), hs in k.free.items() if g in ga for h in hs if h not in k.taken]
    free_b = [h for (g, _), hs in k.free.items() if g in gb for h in hs if h not in k.taken]
    wire = "or join them with a wire across the top."
    for free, w in ((free_a, wa), (free_b, wb)):
        if not free:
            return (f"{net}: nothing can join {w} to the rest of its net: every hole on its "
                    f"copper is taken or under a part. Move a part off that strip to make "
                    f"room, {wire}")  # fmt: skip
    pairs = sorted(((abs(a[1] - b[1]), a, b) for a in free_a for b in free_b if a[0] == b[0]),
                   key=lambda c: (c[0], c[1][0]))  # fmt: skip
    if not pairs:
        if ha[1] == hb[1]:
            strip = ha[1] + 1
            lo, hi = sorted((ha[0], hb[0]))
            between = [(x, ha[1]) for x in range(lo + 1, hi)]
            who, ref = next((_in_the_way(r, k, h) for h in between
                             if h in k.used and h not in r.layout.cuts), ("", None))  # fmt: skip
            if not who:
                who = next((f"the cut at {hole_name(h)}" for h in between
                            if h in r.layout.cuts), "a cut")  # fmt: skip
            move = f"Move {ref} off strip {strip}" if ref else "Move one of them to another strip"
            return (f"{net}: {wa} and {wb} are both on strip {strip}, with {who} between "
                    "them, and a link only joins one strip to another. "
                    f"{move}, {wire}")  # fmt: skip
        return (f"{net}: no column has a free hole on both {wa}'s strip and {wb}'s, so no "
                f"link can join them. Move one so they share a free column, {wire}")  # fmt: skip
    _, a, b = pairs[0]
    hole = _link_blocker(k, a, b)
    who, ref = _in_the_way(r, k, hole) if hole else ("something", None)
    move = f"Move {ref}" if ref else "Move it"
    return (f"{net}: every link that would join {wa} and {wb} is blocked; the shortest, "
            f"{hole_name(a)} to {hole_name(b)}, by {who}. {move}, {wire}")  # fmt: skip


def signal_order(circuit: Circuit, r: Reading) -> dict[str, int]:
    """Each net's distance from the input along the signal path (unreached: none)."""
    start = r.ends.get("IN.out")
    return distances(start, signal_edges(circuit, r.nets)) if start else {}


def next_part(circuit: Circuit, r: Reading) -> Next | None:
    """The part to place next: one whose nets are on the board already first, then the
    nearest the input along the signal, chips and transistors before the rest at the same
    distance."""
    placed = {p.ref for p in r.layout.parts}
    left = sorted(r.board.keys() - placed)
    if not left:
        return None
    holes = _terminal_holes(r)
    on_board: dict[str, list[Terminal]] = defaultdict(list)
    for t in sorted(holes, key=lambda t: (holes[t][1], holes[t][0])):
        on_board[r.expected[t]].append(t)
    order = signal_order(circuit, r)
    far = len(order) + 1
    rank = {"dip": 0, "sil": 0, "inline": 1}

    def nets(ref: str) -> list[str]:
        return [r.nets.net_of(*pin) for pin in r.board[ref].pins.values()]

    def key(ref: str) -> tuple[int, int, int, str]:
        touches = any(net in on_board for net in nets(ref))
        near = min((order.get(n, far) for n in nets(ref)), default=far)
        return (0 if touches else 1, near, rank.get(r.board[ref].footprint.shape, 2), ref)

    ref = min(left, key=key)
    joins = [n for n in sorted(set(nets(ref)), key=lambda n: order.get(n, far)) if n in on_board]
    if joins:
        net = joins[0]
        return Next(ref, f"Next: {ref}. It joins {r.words(on_board[net][0])} ({net}).")
    if min((order.get(n, far) for n in nets(ref)), default=far) < far:
        return Next(ref, f"Next: {ref}, the nearest the input along the signal.")
    return Next(ref, f"Next: {ref}.")


def guidance(layout: Layout, circuit: Circuit, models: ModelLibrary,
             table: FootprintTable) -> Guidance:  # fmt: skip
    """Everything the editor shows to guide the next step on `layout`."""
    r = read_layout(layout, circuit, models, table)
    cuts = suggested_cuts(r)
    k, links = _linking(r, cuts)
    return Guidance(marks(r), ratsnest(r), cuts, links, _stuck(r, k), next_part(circuit, r))
