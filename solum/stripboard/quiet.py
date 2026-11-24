"""Quiet links (D-402): no link under, or beside, a part on a sensitive net.

A sensitive net is the one a high-gain stage's signal enters by (`probe.loud_inputs`,
D-400): a little pickup there is amplified with the guitar. A link carrying another net
with signal on it (not ground, a rail or a reference: AC-quiet, as `loud_inputs` reads
them) that runs under such a part's body, or has an end or a passing hole in, or in one of the
eight holes round, the part's leg on that net or its body, is warned about; so is one
under a chip whose high-gain input pin it is, or round that pin. A link of the sensitive
net itself is let be (it is that node), so is a quiet net's (nothing on it to pick up),
and links under other parts stay allowed (D-401).
Never a refusal: the board is still the circuit.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from solum.circuit.connectivity import GROUND, Nets
from solum.stripboard.board import Hole, Layout, Link, hole_name, segments
from solum.stripboard.footprints import BoardPart, body_holes
from solum.stripboard.limits import WHY, LoudInput, pin_said

AROUND = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


@dataclass(frozen=True)
class Guard:
    """A part a link should keep clear of: its board `ref`, the sensitive `net`, the legs
    on it (`legs`), the high-gain input it is or feeds (`anchor`, `pin`: board ref and
    leg, for the words), and the nets whose links may pass it (`calm`: ground and the nets
    AC-quiet beside the input)."""

    ref: str
    net: str
    legs: tuple[str, ...]
    anchor: str
    pin: str
    calm: frozenset[str] = frozenset({GROUND})


def guards(board: Mapping[str, BoardPart], nets: Nets, loud: Sequence[LoudInput]) -> list[Guard]:
    """Each part on a sensitive net, in a stable order: a chip only for the input pin that
    is its own (its other legs carry other nets), any other part for its legs on the net."""
    leg_of = {pin: (ref, leg) for ref, part in board.items() for leg, pin in part.pins.items()}
    found: list[Guard] = []
    seen: set[str] = set()
    for entry in loud:
        net = nets.by_pin.get((entry.ref, entry.pin))
        anchor = leg_of.get((entry.ref, entry.pin))
        if net is None or net == GROUND or anchor is None or net in seen:
            continue
        seen.add(net)
        for ref, part in sorted(board.items()):
            if part.footprint.shape == "dip":
                legs = tuple(lg for lg, pin in part.pins.items()
                             if pin == (entry.ref, entry.pin))  # fmt: skip
            else:
                legs = tuple(lg for lg, pin in part.pins.items() if nets.net_of(*pin) == net)
            if legs:
                found.append(Guard(ref, net, legs, *anchor, entry.quiet | {GROUND}))
    return found


def calm_nets(found: Sequence[Guard]) -> frozenset[str]:
    """The nets whose links may pass every guarded part (quiet beside every input): the
    layout help's shortcut, where the warnings ask each part's own."""
    sets = [g.calm for g in found]
    return frozenset.intersection(*sets) if sets else frozenset()


def kept_clear(legs: Iterable[Hole], body: Iterable[Hole]) -> tuple[set[Hole], set[Hole]]:
    """The holes a link keeps out of round a guarded part: under it (`body`) and beside
    (the eight holes round each guarded leg and body hole), as (under, all)."""
    under = set(body)
    clear = set(under)
    for x, y in [*legs, *under]:
        clear.add((x, y))
        clear.update((x + dx, y + dy) for dx, dy in AROUND)
    return under, clear


MIXED = "\0"  # a hole kept clear of two sensitive nets: every link keeps out


def zone_of(layout: Layout, board: Mapping[str, BoardPart],
            found: Sequence[Guard]) -> dict[Hole, str]:  # fmt: skip
    """The holes links of another net keep out of on `layout`, each with its sensitive net
    (`MIXED` near two)."""
    placed = {p.ref: p for p in layout.parts}
    zone: dict[Hole, str] = {}
    for g in found:
        p = placed.get(g.ref)
        if p is None:
            continue
        holes = p.holes
        body = body_holes(board[g.ref], holes, p.standing)
        for h in kept_clear([holes[lg] for lg in g.legs if lg in holes], body)[1]:
            zone[h] = g.net if zone.get(h, g.net) == g.net else MIXED
    return zone


def quiet_for(zone: Mapping[Hole, str], net: str, holes: Iterable[Hole],
              calm: frozenset[str] = frozenset()) -> bool:  # fmt: skip
    """Whether a link of `net` over `holes` keeps clear of every other sensitive net (a
    `calm` net's always does)."""
    return net in calm or all(zone.get(h, net) == net for h in holes)


def link_holes(link: Link) -> list[Hole]:
    """A link's ends and the holes it passes over."""
    return [link.a, *link.between, link.b]


@dataclass(frozen=True)
class Noisy:
    """A link too near a sensitive net's part: `under` its body, or beside it."""

    link: Link
    guard: Guard
    under: bool


def noisy_links(layout: Layout, board: Mapping[str, BoardPart], nets: Nets,
                found: Sequence[Guard]) -> list[Noisy]:  # fmt: skip
    """Each link `layout` lays too near a guarded part (the first it's near), in the
    layout's order."""
    if not found or not layout.links:
        return []
    placed = {p.ref: p for p in layout.parts}
    zones = []
    for g in found:
        p = placed.get(g.ref)
        if p is None:
            continue
        holes = p.holes
        part = board[g.ref]
        body = body_holes(part, holes, p.standing)
        legs = [holes[lg] for lg in g.legs if lg in holes]
        zones.append((g, *kept_clear(legs, body)))
    if not zones:
        return []
    seg = segments(layout)
    on: dict[int, set[str]] = {}  # each segment's nets, from the legs on it
    for q in layout.parts:
        bp = board.get(q.ref)
        if bp is None:
            continue
        for leg, hole in q.legs:
            pin = bp.pins.get(leg)
            if pin is not None and hole in seg:
                on.setdefault(seg[hole], set()).add(nets.net_of(*pin))
    noisy = []
    for link in layout.links:
        own = on.get(seg.get(link.a, -1), set()) | on.get(seg.get(link.b, -1), set())
        over = link_holes(link)
        for g, under, clear in zones:
            if g.net in own or (own and own <= g.calm):
                continue
            if any(h in clear for h in over):
                noisy.append(Noisy(link, g, any(h in under for h in over)))
                break
    return noisy


def quiet_warnings(noisy: Sequence[Noisy]) -> list[str]:
    """Each noisy link in a sentence (a warning in the editor)."""
    said = []
    for n in noisy:
        a, b = sorted((n.link.a, n.link.b), key=lambda h: (h[1], h[0]))
        where = "under" if n.under else "beside"
        on = (f"by {pin_said(n.guard.anchor, n.guard.pin)}" if n.guard.ref == n.guard.anchor
              else f"on {pin_said(n.guard.anchor, n.guard.pin)}")  # fmt: skip
        said.append(
            f"The link from {hole_name(a)} to {hole_name(b)} runs {where} {n.guard.ref}, {on} "
            f"({WHY['input']}): move it a column or two, so it picks up no noise there."
        )
    return said
