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
from dataclasses import dataclass, replace
from itertools import pairwise

from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.rules.graph import distances, signal_edges
from solum.stripboard.board import Hole, Layout, Link, segments
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
    `cuts` and `links`: the ones the legs call for, suggested; `next`: what to place next
    (None: nothing left, or nothing placeable)."""

    marks: dict[str, list[Run]]
    ratsnest: list[Strand]
    cuts: list[Hole]
    links: list[tuple[Hole, Hole]]
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


def suggested_links(r: Reading, cuts: list[Hole]) -> list[tuple[Hole, Hole]]:
    """With the suggested cuts made, the shortest links joining each net's pieces: down a
    free column, both ends in free copper of the net's own groups, over no leg, pad or
    link end, under no body but a flat resistor's (as the check allows), and no end under
    another link, laid or suggested."""
    cut = replace(r.layout, cuts=r.layout.cuts | set(cuts))
    copper = copper_groups(cut)
    used, hard, bodies = _blocked(r)
    used |= set(cuts)
    crossed = {h for link in r.layout.links for h in link.between}  # under a link: no end
    nets_of: dict[int, set[str]] = defaultdict(set)
    for t, hole in _terminal_holes(r).items():
        if hole in copper:
            nets_of[copper[hole]].add(r.expected[t])
    own = {g: next(iter(n)) for g, n in nets_of.items() if len(n) == 1}
    free: dict[tuple[int, int], list[Hole]] = defaultdict(list)  # (group, column) → holes
    for hole, group in copper.items():
        if group in own and hole not in used and hole not in bodies:
            free[(group, hole[0])].append(hole)
    by_net: dict[str, list[int]] = defaultdict(list)
    for g, net in sorted(own.items()):
        by_net[net].append(g)
    links: list[tuple[Hole, Hole]] = []
    taken: set[Hole] = set()
    for net in sorted(by_net):
        groups = by_net[net]
        if len(groups) < 2:
            continue
        heap: list[tuple[int, Hole, Hole, int, int]] = []
        for i, ga in enumerate(groups):
            for gb in groups[i + 1 :]:
                for column in range(cut.columns):
                    for a in free.get((ga, column), ()):
                        for b in free.get((gb, column), ()):
                            if a in crossed or b in crossed:
                                continue
                            top, bottom = sorted((a, b), key=lambda h: h[1])
                            over = Link(top, bottom).between
                            if any(h in used or h in hard for h in over):
                                continue
                            heap.append((bottom[1] - top[1], top, bottom, ga, gb))
        heapq.heapify(heap)
        parent = {g: g for g in groups}

        def find(g: int, parent: dict[int, int] = parent) -> int:
            while parent[g] != g:
                g = parent[g]
            return g

        while heap:  # Kruskal's: the shortest link between two pieces not yet joined
            _, top, bottom, ga, gb = heapq.heappop(heap)
            over = Link(top, bottom).between
            if (find(ga) == find(gb) or top in taken or bottom in taken or top in crossed
                    or bottom in crossed or any(h in taken for h in over)):  # fmt: skip
                continue
            parent[find(ga)] = find(gb)
            taken |= {top, bottom}
            crossed |= set(over)
            links.append((top, bottom))
    return links


def _signal_order(circuit: Circuit, r: Reading) -> dict[str, int]:
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
    order = _signal_order(circuit, r)
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
    return Guidance(marks(r), ratsnest(r), cuts, suggested_links(r, cuts),
                    next_part(circuit, r))  # fmt: skip
