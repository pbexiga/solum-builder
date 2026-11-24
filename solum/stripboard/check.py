"""The check of a stripboard layout against its circuit (D-367).

The board is read back into nets (strips between cuts, joined by links; each leg puts its
pin on its strip; each off-board wire its lug on its pad's strip or with another lug,
D-375) and compared, pin for pin, with the
circuit's own nets from `connect`: there is no second notion of a net. Every fault is a
plain-English sentence naming the parts and holes; a layout with none is the circuit.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from solum.circuit.connectivity import GROUND, Nets, connect
from solum.circuit.parts import PIN_WORDS
from solum.circuit.schema import POLARISED, SUPPLY_SIGNS, Capacitor, Circuit, Part
from solum.export import built_where, chosen_where, why_not_moved
from solum.guides import FootprintTable
from solum.models import ModelError, ModelLibrary
from solum.stripboard.apart import alongside, apart_warnings
from solum.stripboard.board import (
    EDGE,
    PITCH,
    Hole,
    Layout,
    Placed,
    hole_name,
    segments,
)
from solum.stripboard.footprints import (
    BoardPart,
    NoFootprint,
    PinRef,
    board_parts,
    board_refs,
    body_holes,
    body_outline,
    leg_problem,
    links_under,
    one_board_part,
    outline_overlap,
)
from solum.stripboard.limits import LoudInput, limit_warnings, placement_limits
from solum.stripboard.offboard import (
    POWER,
    SLEEVE,
    OffItem,
    default_spots,
    lug_nets,
    off_board_items,
)
from solum.stripboard.quiet import guards, noisy_links, quiet_warnings
from solum.words import listed

Terminal = PinRef | str  # a board part's pin, or an off-board lug ("VR1.1", "IN.S", "V+")
_TWO_PIN_WORDS = {"A": "anode", "K": "cathode"}
_TRIMMER_WORDS = {"1": "lug 1", "2": "wiper", "3": "lug 3"}


@dataclass(frozen=True)
class Checked:
    """`faults`: what's wrong, a sentence each (none: the board is the circuit); `nets`:
    how many of the circuit's nets the board carries."""

    faults: list[str]
    nets: int

    @property
    def ok(self) -> bool:
        return not self.faults


def end_words(end: str) -> str:
    """An off-board lug in words: "the input", "the input jack's sleeve", "ground", "the V-
    supply", "VR1 lug 1"."""
    named = {"IN.out": "the input", "OUT.in": "the output", GROUND: "ground",
             f"IN.{SLEEVE}": "the input jack's sleeve",
             f"OUT.{SLEEVE}": "the output jack's sleeve"}  # fmt: skip
    if end in named:
        return named[end]
    ref, dot, pin = end.partition(".")
    if not dot:
        return f"the {end} supply"
    return f"{ref} lug {pin}" if pin.isdigit() else f"{ref} {pin}"


class _Words:
    """How the check names a terminal: the part's leg and its hole."""

    def __init__(self, circuit: Circuit, board: dict[str, BoardPart], layout: Layout) -> None:
        self.kinds = {p.ref: p for p in circuit.parts}
        self.board = board
        self.where: dict[Terminal, str] = {}
        self.hole_of: dict[Terminal, Hole] = {}
        self.leg_of: dict[Terminal, tuple[str, str]] = {}  # a pin's board part and leg
        for placed in layout.parts:
            part = board.get(placed.ref)
            for leg, hole in placed.legs:
                pin = part.pins.get(leg) if part else None
                if pin is not None:
                    self.where[pin] = hole_name(hole)
                    self.hole_of[pin] = hole
                    self.leg_of[pin] = (placed.ref, leg)
        for wire in layout.wires:
            if wire.hole is not None:
                self.where.setdefault(wire.lug, hole_name(wire.hole))
                self.hole_of.setdefault(wire.lug, wire.hole)

    def __call__(self, terminal: Terminal) -> str:
        at = self.where.get(terminal, "")
        if isinstance(terminal, str):
            return f"{end_words(terminal)}'s wire at {at}" if at else end_words(terminal)
        ref, pin = terminal
        board_ref, leg = self.leg_of.get(terminal, (ref, pin))
        part = self.board.get(board_ref)
        kind = part.kind if part else ""
        original = self.kinds.get(ref)
        if kind in ("chip", "switch"):  # a chip's or a DIP switch's (D-397) numbered pins
            return f"{board_ref}'s pin {leg} ({ref} {pin}) at {at}"
        if pin in PIN_WORDS and kind in ("bjt", "jfet", "mosfet"):
            return f"{ref}'s {PIN_WORDS[pin]} at {at}"
        if kind == "trimmer":
            return f"{ref}'s {_TRIMMER_WORDS[pin]} at {at}"
        if pin in _TWO_PIN_WORDS:
            return f"{ref}'s {_TWO_PIN_WORDS[pin]} at {at}"
        if isinstance(original, Capacitor) and original.kind in POLARISED:
            return f"{ref}'s {'+' if pin == '1' else '−'} leg at {at}"
        return f"{ref}'s leg at {at}"


def occupants(layout: Layout) -> tuple[dict[Hole, list[str]], list[str]]:
    """Who has a wire or leg in each hole, and the faults of where links and wires are."""
    used: dict[Hole, list[str]] = defaultdict(list)
    faults = []
    for placed in layout.parts:
        for _, hole in placed.legs:
            used[hole].append(placed.ref)
    for link in layout.links:
        name = f"the link from {hole_name(link.a)} to {hole_name(link.b)}"
        if link.a[0] != link.b[0] or link.a[1] == link.b[1]:
            faults.append(f"A link runs down a column: {name} doesn't.")
        for hole in (link.a, link.b):
            used[hole].append(name)
    for wire in layout.wires:
        if wire.hole is not None:
            used[wire.hole].append(f"the wire from {end_words(wire.lug)}")
    for hole, who in sorted(used.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if not layout.on_board(hole):
            faults.append(f"{_cap(who[0])} is at {hole_name(hole)}, off the board.")
        elif hole in layout.cuts:
            faults.append(
                f"{_cap(who[0])} is in a cut hole ({hole_name(hole)}): the cut takes its "
                "copper away."
            )
        if len(who) > 1:
            faults.append(f"{_cap(' and '.join(who))} share hole {hole_name(hole)}.")
    return used, faults


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


_SLACK = 0.05  # mm two outlines may meet by, unwarned: one maker's outlines (D-398)


@dataclass(frozen=True)
class Overlap:
    """Two bodies touching between the holes, or one past the board's edge (`parts[1]` is
    `board.EDGE`), D-394; `text` the warning, with no amount (the outlines are one maker's,
    D-398); `reason` the builder's, once dismissed."""

    parts: tuple[str, str]
    text: str
    reason: str = ""


@dataclass(frozen=True)
class NoteState:
    """One of the board's notes as the Notes pane shows it: `why` it's out of date ("C2 and
    R1 no longer touch", "R1 isn't on the board"), or None (D-398)."""

    parts: tuple[str, ...]
    text: str
    overlap: bool
    why: str | None


def outline_overlaps(layout: Layout, board: Mapping[str, BoardPart]) -> list[Overlap]:
    """Bodies by their real outlines (D-394): two touching between holes (a fault only
    when they share a hole: `placement_faults`), or one hanging more than half a hole past
    the board's edge. Warnings, not faults: the builder knows their parts, and may note or
    dismiss each (D-398)."""
    found: list[tuple[str, tuple[float, float, float, float, float]]] = []
    for p in layout.parts:
        part = board.get(p.ref)
        if part is None:
            continue
        outline = body_outline(part, p.holes, p.standing)
        if outline is not None:
            found.append((p.ref, outline))
    overlaps = []
    for i, (a, out_a) in enumerate(found):
        for b, out_b in found[i + 1 :]:
            if outline_overlap(out_a, out_b) > _SLACK:
                overlaps.append(Overlap((a, b), (
                    f"{a} and {b}'s bodies touch: move one a hole further away if you can."
                )))  # fmt: skip
    edge = (-PITCH, -PITCH, layout.columns * PITCH, layout.strips * PITCH)  # half a hole out
    for ref, (x0, y0, x1, y1, _) in found:
        if max(edge[0] - x0, edge[1] - y0, x1 - edge[2], y1 - edge[3]) > _SLACK:
            overlaps.append(Overlap((ref, EDGE), (
                f"{ref} hangs past the board's edge: check it clears the enclosure, or move it in."
            )))  # fmt: skip
    return overlaps


def _pair(parts: Iterable[str]) -> frozenset[str]:
    return frozenset(parts)


def dismissed_apart(layout: Layout, overlaps: list[Overlap]) -> tuple[list[Overlap], list[Overlap]]:
    """The overlaps still warned of, and the ones the builder dismissed, with their reason
    (D-398: matched by the two parts, either way round)."""
    reasons = {_pair(d.parts): d.reason for d in layout.dismissed}
    warned = [o for o in overlaps if _pair(o.parts) not in reasons]
    gone = [replace(o, reason=reasons[_pair(o.parts)]) for o in overlaps
            if _pair(o.parts) in reasons]  # fmt: skip
    return warned, gone


def kept_dismissals(layout: Layout, board: Mapping[str, BoardPart]) -> Layout:
    """`layout` without the dismissals of overlaps it no longer has (D-398: if they come
    back, they're warned of afresh); run after every change to the board. Notes stay."""
    now = {_pair(o.parts) for o in outline_overlaps(layout, board)}
    kept = tuple(d for d in layout.dismissed if _pair(d.parts) in now)
    return layout if len(kept) == len(layout.dismissed) else replace(layout, dismissed=kept)


def note_states(layout: Layout, overlaps: list[Overlap]) -> list[NoteState]:
    """Each of the board's notes, with why it's out of date (D-398): a part it names isn't
    on the board (placed, or beside it), or the parts it was written about no longer touch
    (a note from an overlap warning). Never dropped: the builder deletes their own."""
    here = {p.ref for p in layout.parts} | {ref for ref, _ in layout.spots}
    touching = {_pair(r for r in o.parts if r != EDGE) for o in overlaps}
    found = []
    for n in layout.notes:
        gone = [r for r in n.parts if r not in here]
        why = None
        if gone:
            why = f"{' and '.join(gone)} {'isn' if len(gone) == 1 else 'aren'}'t on the board"
        elif n.overlap and _pair(n.parts) not in touching:
            why = (f"{n.parts[0]} no longer hangs past the edge" if len(n.parts) == 1
                   else f"{' and '.join(n.parts)} no longer touch")  # fmt: skip
        found.append(NoteState(n.parts, n.text, n.overlap, why))
    return found


def note_words(parts: Iterable[str], text: str) -> str:
    """A note as the build sheet prints it: "C2, R1: solder C2 a bit higher.", or the
    text alone for a general note."""
    named = ", ".join(parts)
    return f"{named}: {text}" if named else text


def placement_faults(layout: Layout, board: dict[str, BoardPart],
                     off_board: set[str]) -> list[str]:  # fmt: skip
    """What's wrong with where things sit: parts missing or extra, legs not as the part's
    footprint allows, two things in a hole, a body over a leg, a link under a body."""
    faults = []
    placed = {p.ref: p for p in layout.parts}
    for ref in sorted(board.keys() - placed.keys()):
        faults.append(f"{ref} isn't on the board.")
    for ref in sorted(placed.keys() - board.keys()):
        if ref in off_board:
            faults.append(f"{ref} goes off the board: put it beside the board and wire it.")
        else:
            faults.append(f"{ref} is on the board but not in the circuit.")
    used, occupied = occupants(layout)
    faults += occupied
    bodies: dict[Hole, list[str]] = defaultdict(list)
    flat: set[str] = set()
    for p in layout.parts:
        part = board.get(p.ref)
        if part is None:
            continue
        problem = leg_problem(part, p.holes, p.standing)
        if problem:
            faults.append(problem)
            continue
        if links_under(part, p.standing):
            flat.add(p.ref)
        for hole in body_holes(part, p.holes, p.standing):
            bodies[hole].append(p.ref)
    for hole, owners in sorted(bodies.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        name = hole_name(hole)
        if len(owners) > 1:
            faults.append(f"{' and '.join(owners)}'s bodies overlap at {name}.")
        for who in used.get(hole, []):
            if who.startswith("the link"):
                continue
            faults.append(f"{owners[0]}'s body covers {name}, where {who} goes.")
    for link in layout.links:
        name = f"the link from {hole_name(link.a)} to {hole_name(link.b)}"
        for hole in link.between:
            for who in used.get(hole, []):
                faults.append(f"{_cap(name)} passes over {who} at {hole_name(hole)}.")
            for owner in bodies.get(hole, []):
                if owner not in flat:
                    faults.append(f"{_cap(name)} runs under {owner}'s body at {hole_name(hole)}.")
    return faults


def copper_groups(layout: Layout, holes: Iterable[Hole] | None = None) -> dict[Hole, int]:
    """Each copper hole's joined group: its strip segment's, with links joining segments.
    `holes`: only these (`segments`)."""
    ends = [h for link in layout.links for h in (link.a, link.b)]
    wanted = None if holes is None else set(holes)
    seg = segments(layout, None if wanted is None else wanted | set(ends))
    parent: dict[int, int] = {}

    def find(a: int) -> int:
        while parent.get(a, a) != a:
            a = parent[a]
        return a

    for link in layout.links:
        a, b = seg.get(link.a), seg.get(link.b)
        if a is not None and b is not None:
            parent[max(find(a), find(b))] = min(find(a), find(b))
    return {hole: find(n) for hole, n in seg.items() if wanted is None or hole in wanted}


def joined_groups(layout: Layout, holes: Iterable[Hole] | None = None,
                  ) -> tuple[dict[Hole, int], dict[str, int]]:  # fmt: skip
    """Each copper hole's group and each wired lug's, wires joining them (D-375): a lug
    wired to a hole is in that hole's group, lugs wired together share one; a lug only on
    a loose wire, or wired to a cut hole or one off the board, has none. `holes`: only
    these holes' groups (quick on a big board; the lugs all the same)."""
    wanted = None if holes is None else set(holes)
    copper = copper_groups(layout, None if wanted is None else wanted | set(layout.pads))
    parent: dict[tuple[str, object], tuple[str, object]] = {}

    def find(node: tuple[str, object]) -> tuple[str, object]:
        while parent.get(node, node) != node:
            node = parent[node]
        return node

    def join(a: tuple[str, object], b: tuple[str, object]) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb, key=repr)] = min(ra, rb, key=repr)

    for wire in layout.wires:
        if wire.hole is not None and wire.hole in copper:
            join(("lug", wire.lug), ("copper", copper[wire.hole]))
        elif wire.to is not None:
            join(("lug", wire.lug), ("lug", wire.to))
    members: dict[tuple[str, object], list[tuple[str, object]]] = defaultdict(list)
    for node in list(parent):
        members[find(node)].append(node)
    fresh = layout.strips + len(layout.cuts) + 1  # past every segment's number
    number: dict[tuple[str, object], int] = {}
    for root, nodes in sorted(members.items(), key=lambda kv: repr(kv[0])):
        coppers = [int(str(n[1])) for n in [root, *nodes] if n[0] == "copper"]
        if coppers:
            number[root] = min(coppers)
        else:
            number[root], fresh = fresh, fresh + 1
    found = {h: number.get(find(("copper", g)), g) for h, g in copper.items()
             if wanted is None or h in wanted}  # fmt: skip
    lugs = {str(n[1]): number[find(n)] for n in [*parent, *members] if n[0] == "lug"}
    return found, lugs


def stripboard_nets(layout: Layout, board: dict[str, BoardPart]) -> dict[Terminal, int]:
    """The board read back into nets: each terminal (a board part's pin, a free leg as
    (ref, "#leg"), a wired lug) → its group; terminals in one group are joined."""
    copper, lugs = joined_groups(layout)
    groups: dict[Terminal, int] = {}
    for placed in layout.parts:
        part = board.get(placed.ref)
        for leg, hole in placed.legs:
            if part is None or hole not in copper:
                continue
            if leg in part.pins:
                groups[part.pins[leg]] = copper[hole]
            elif leg in part.free:
                groups[(placed.ref, f"#{leg}")] = copper[hole]
    groups.update(lugs)
    return groups


def runs(holes: set[Hole]) -> list[tuple[int, int, int]]:
    """Holes as runs along their strips, `(strip, first column, last column)`, top to bottom."""
    found: list[tuple[int, int, int]] = []
    for column, strip in sorted(holes, key=lambda h: (h[1], h[0])):
        if found and found[-1][0] == strip and found[-1][2] == column - 1:
            found[-1] = (strip, found[-1][1], column)
        else:
            found.append((strip, column, column))
    return found


def _short(a: Terminal, b: Terminal, words: _Words) -> str:
    """Two terminals the board joins and the circuit doesn't; two pins of a DIP on one
    strip are its missing cut."""
    first, second = words.leg_of.get(a), words.leg_of.get(b)
    holes = words.hole_of.get(a), words.hole_of.get(b)
    if first and second and first[0] == second[0] and holes[0] and holes[1]:
        part = words.board.get(first[0])
        if part and part.footprint.shape == "dip" and holes[0][1] == holes[1][1]:
            return (
                f"The strip under {first[0]} isn't cut between pins {first[1]} and "
                f"{second[1]} (strip {holes[0][1] + 1})."
            )
    return (
        f"{_cap(words(a))} and {words(b)} are joined on the board, but the circuit doesn't "
        "connect them."
    )


def _closest(ones: list[Terminal], others: list[Terminal], words: _Words,
             seg: dict[Hole, int]) -> tuple[Terminal, Terminal]:  # fmt: skip
    """The pair to name for a short: one of each net, on one strip segment if any pair is
    (where the missing cut or the stray leg is), nearest each other."""

    def cost(pair: tuple[Terminal, Terminal]) -> tuple[int, int]:
        a, b = (words.hole_of.get(t) for t in pair)
        if a is None or b is None:
            return (2, 0)
        return (0 if seg.get(a) == seg.get(b) else 1, abs(a[0] - b[0]) + abs(a[1] - b[1]))

    a, b = min(((a, b) for a in ones for b in others), key=cost)
    return (a, b) if words.hole_of.get(a, (0, 0)) <= words.hole_of.get(b, (0, 0)) else (b, a)


def _key(t: Terminal) -> tuple[int, str, str]:
    return (1, t, "") if isinstance(t, str) else (0, t[0], t[1])


def either_way(part: BoardPart, circuit_part: object) -> bool:
    """A two-leg part with no way round: a resistor, a capacitor that isn't polarised. The
    check turns it to fit the board (D-368); a diode, LED or electrolytic keeps its own."""
    if part.footprint.shape not in ("axial", "radial") or len(part.pins) != 2:
        return False
    if isinstance(circuit_part, Capacitor):
        return circuit_part.kind not in POLARISED
    return part.kind == "resistor"


def _expected(groups: dict[Terminal, int], ends: dict[str, str],
              nets: Nets) -> dict[Terminal, str]:  # fmt: skip
    """Each terminal on the board → the net the circuit puts it on (a free leg a net of
    its own, a lug its pin's net; a lug of nothing, none)."""
    expected: dict[Terminal, str] = {}
    for t in groups:
        if isinstance(t, str):
            if t in ends:
                expected[t] = ends[t]
        elif t[1].startswith("#"):
            expected[t] = f"{t[0]}{t[1]}"
        else:
            expected[t] = nets.net_of(*t)
    return expected


_Seen = tuple[dict[Terminal, int], dict[Terminal, str], dict[int, list[str]]]


def _fit(net: str, own: PinRef, other: PinRef, seen: _Seen) -> int:
    """How well a leg holding pin `own` fits `net`: +1 for each terminal on its strip of
    that net, -1 for each of another; the part's own pins (`own`, `other`) aren't counted."""
    groups, expected, mates = seen
    g = groups.get(own)
    if g is None:
        return 0
    others = list(mates[g])
    for mine in (own, other):
        if mine in expected and groups.get(mine) == g:
            others.remove(expected[mine])
    return sum(1 if n == net else -1 for n in others)


def _oriented(layout: Layout, board: dict[str, BoardPart], circuit: Circuit, nets: Nets,
              ends: dict[str, str]) -> Layout:  # fmt: skip
    """`layout` with each either-way part's legs swapped where that fits the board better:
    each leg scores +1 for every terminal on its strip of its own net and -1 for every
    other net's, the rest of the board as it stands; repeated until nothing turns."""
    kinds = {p.ref: p for p in circuit.parts}
    turnable = [p.ref for p in layout.parts if p.ref in board
                and either_way(board[p.ref], kinds.get(p.ref))]  # fmt: skip
    for _ in range(len(turnable) + 1):
        groups = stripboard_nets(layout, board)
        expected = _expected(groups, ends, nets)
        mates: dict[int, list[str]] = defaultdict(list)
        for t, g in groups.items():
            if t in expected:
                mates[g].append(expected[t])
        turned = False
        parts = {p.ref: p for p in layout.parts}
        for ref in turnable:
            placed, part = parts[ref], board[ref]
            (leg_a, hole_a), (leg_b, hole_b) = placed.legs
            pin_a, pin_b = part.pins[leg_a], part.pins[leg_b]

            seen = (groups, expected, mates)
            now = _fit(nets.net_of(*pin_a), pin_a, pin_b, seen) + _fit(
                nets.net_of(*pin_b), pin_b, pin_a, seen
            )
            swapped = _fit(nets.net_of(*pin_b), pin_a, pin_b, seen) + _fit(
                nets.net_of(*pin_a), pin_b, pin_a, seen
            )
            if swapped > now:
                parts[ref] = Placed(ref, ((leg_b, hole_a), (leg_a, hole_b)), placed.standing)
                turned = True
        if not turned:
            return layout
        layout = replace(layout, parts=tuple(parts[p.ref] for p in layout.parts))
    return layout


@dataclass
class Reading:
    """A layout read against its circuit: what both checks start from."""

    nets: Nets
    board: dict[str, BoardPart]
    unboardable: list[str]  # parts the footprints table can't size
    off_board: set[str]
    items: list[OffItem]
    ends: dict[str, str]  # every lug → its net
    needed: set[str]  # the lugs on a net with something else to join
    layout: Layout  # either-way parts turned to fit
    words: _Words
    groups: dict[Terminal, int]
    expected: dict[Terminal, str]


def read_layout(layout: Layout, circuit: Circuit, models: ModelLibrary,
          table: FootprintTable) -> Reading:  # fmt: skip
    nets = connect(circuit)
    board, unboardable = board_parts(circuit, models, table)
    chosen = chosen_where(circuit)
    off_board = {p.ref for p in circuit.parts if built_where(p, chosen) != "board"}
    items = off_board_items(circuit, nets, board, models)
    ends = lug_nets(items)
    count: dict[str, int] = defaultdict(int)
    for part in board.values():
        for pin in part.pins.values():
            count[nets.net_of(*pin)] += 1
    for net in ends.values():
        count[net] += 1
    needed = {end for end, net in ends.items() if count[net] > 1}
    layout = _oriented(layout, board, circuit, nets, ends)
    groups = stripboard_nets(layout, board)
    return Reading(nets, board, unboardable, off_board, items, ends, needed, layout,
                    _Words(circuit, board, layout), groups,
                    _expected(groups, ends, nets))  # fmt: skip


def _wire_faults(r: Reading) -> tuple[list[str], list[str], int]:
    """Wires from or to a lug the circuit has no such lug for, or from a lug to itself;
    the needed lugs not wired to anything yet; how many wires are loose."""
    faults = []
    for wire in r.layout.wires:
        for lug in (wire.lug, wire.to):
            if lug is not None and lug not in r.ends:
                faults.append(f"A wire goes to {lug!r}, which isn't an off-board lug of this "
                              "circuit.")  # fmt: skip
        if wire.to == wire.lug:
            faults.append(f"A wire runs from {end_words(wire.lug)} to itself.")
    loose = sum(w.hole is None and w.to is None for w in r.layout.wires)
    unwired = [end for end in r.ends if end in r.needed and end not in r.groups]
    return faults, unwired, loose


def groups_by_net(r: Reading) -> dict[int, dict[str, list[Terminal]]]:
    """Each joined group of the board → its terminals by the net the circuit wants."""
    found: dict[int, dict[str, list[Terminal]]] = defaultdict(lambda: defaultdict(list))
    for t in sorted(r.expected, key=_key):
        found[r.groups[t]][r.expected[t]].append(t)
    return found


def check_layout(layout: Layout, circuit: Circuit, models: ModelLibrary,
                 table: FootprintTable) -> Checked:  # fmt: skip
    """Check `layout` against `circuit`: every fault in plain English (D-367)."""
    r = read_layout(layout, circuit, models, table)
    faults = [*r.unboardable, *placement_faults(r.layout, r.board, r.off_board)]
    wiring, unwired, _ = _wire_faults(r)
    faults += wiring + [f"{_cap(end_words(end))} isn't wired yet." for end in unwired]
    faults += [f"The wire from {end_words(w.lug)} is loose: solder its other end."
               for w in r.layout.wires if w.hole is None and w.to is None]  # fmt: skip
    by_net: dict[str, dict[int, list[Terminal]]] = defaultdict(lambda: defaultdict(list))
    seg = segments(r.layout)
    for group, here in groups_by_net(r).items():
        found = list(here.values())
        faults += [_short(*_closest(found[0], other, r.words, seg), r.words)
                   for other in found[1:]]  # fmt: skip
        for net, members in here.items():
            by_net[net][group] = members
    for split in by_net.values():
        parts = list(split.values())
        for other in parts[1:]:
            faults.append(
                f"{_cap(r.words(parts[0][0]))} and {r.words(other[0])} aren't connected on "
                "the board, but the circuit joins them."
            )
    carried = {n for n in by_net if not n.startswith(tuple(f"{ref}#" for ref in r.board))}
    return Checked(faults, len(carried))


# --- the progress check: a board in the making (D-368) ------------------------------

NetState = Literal["done", "pieces", "shorted"]


@dataclass(frozen=True)
class Short:
    """A net joined on the board to `other`, said where (the nearest pair)."""

    other: str
    words: str


@dataclass(frozen=True)
class NetProgress:
    """One net the board carries: `placed` of its `total` terminals on the board, in
    `pieces` joined groups; `done` when all are placed, joined and touch no other net;
    `wires` its off-board lugs not wired yet, in words ("VR1 lug 2", "ground")."""

    net: str
    state: NetState
    placed: int
    total: int
    pieces: int
    shorts: tuple[Short, ...] = ()
    wires: tuple[str, ...] = ()  # its lugs not wired yet, in words (D-371, D-375)


@dataclass(frozen=True)
class Reach:
    """A terminal a leg must reach (`R2.1` a board part's leg, `VR1.1` or `GND` an
    off-board lug) and whether the board joins them yet."""

    to: str
    joined: bool


@dataclass(frozen=True)
class LegProgress:
    leg: str
    hole: str | None  # None: not placed
    net: str | None  # None: a leg the circuit doesn't use
    reach: tuple[Reach, ...]


@dataclass(frozen=True)
class Choice:
    """Where a part is built (D-385): `where` on the board or off it, `moved` there by the
    builder's choice (not the parts list's), `why` it can't be moved, in a sentence (None:
    it can)."""

    where: str
    moved: bool
    why: str | None


def move_problem(part: Part, onto: bool, models: ModelLibrary,
                 table: FootprintTable) -> str | None:  # fmt: skip
    """Why `part` can't be moved off the board, or `onto` it (D-385), in a sentence; None
    when it can. Onto the board it needs a footprint."""
    why = why_not_moved(part)
    if why is not None or not onto:
        return why
    try:
        one_board_part(part, models, table)
    except (NoFootprint, ModelError) as err:
        return str(err)
    return None


@dataclass(frozen=True)
class Progress:
    """Where a board stands: `to_place` the parts not on it yet and `wires_to_go` the lugs not
    wired yet (not faults), `loose` how many wires have a free end; `items` every off-board
    part (D-375), `spots` where each is drawn (put there, else its default);
    `unplaceable` a sentence per part that can't go on a board yet (no footprint: it stays in
    the tray, D-370); `nets` each net's progress; `legs` each board part's legs; `faults` what's
    wrong now (placement, pads, a part the wrong way round, a leg on another net's strip);
    `stale` parts no longer in the circuit (D-376: placed, beside the board, or wired to);
    `warnings` the placement limits broken; `overlaps` bodies touching or past the edge,
    `dismissed` the ones the builder dismissed, `notes` theirs with why each is out of date
    (D-398); `done` the full check passes; `shorted` the
    copper carrying two nets (D-374); `rails` the copper carrying only a rail, V+, V- or
    GND, by net, as runs (D-381)."""

    to_place: list[str]
    wires_to_go: list[str]
    loose: int
    items: list[OffItem]
    spots: dict[str, Hole]
    unplaceable: list[str]
    nets: list[NetProgress]
    legs: dict[str, list[LegProgress]]
    faults: list[str]
    stale: list[str]
    warnings: list[str]
    done: bool
    shorted: list[tuple[int, int, int]] = field(default_factory=list)
    rails: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)
    choices: dict[str, Choice] = field(default_factory=dict)
    overlaps: list[Overlap] = field(default_factory=list)
    dismissed: list[Overlap] = field(default_factory=list)
    notes: list[NoteState] = field(default_factory=list)

    @property
    def nets_done(self) -> int:
        return sum(n.state == "done" for n in self.nets)


def _terminal_id(t: Terminal, words: _Words) -> str:
    """A terminal as the editor names it: a board part's `ref.leg` (as the layout holds
    it), an off-board end as it is."""
    if isinstance(t, str):
        return t
    ref, leg = words.leg_of.get(t, t)
    return f"{ref}.{leg}"


def _wrong_way(r: Reading, circuit: Circuit) -> list[tuple[str, str]]:
    """Each polarised two-leg part placed each leg on the other's net: its ref, and the
    fault in words."""
    kinds = {p.ref: p for p in circuit.parts}
    faults = []
    by_group = groups_by_net(r)
    for placed in r.layout.parts:
        part = r.board.get(placed.ref)
        if part is None or len(part.pins) != 2 or part.footprint.shape not in ("axial", "radial"):
            continue
        if either_way(part, kinds.get(placed.ref)) or len(placed.legs) != 2:
            continue
        pins = [part.pins.get(leg) for leg, _ in placed.legs]
        if None in pins or any(p not in r.groups for p in pins):
            continue
        a, b = (p for p in pins if p is not None)
        net_a, net_b = r.nets.net_of(*a), r.nets.net_of(*b)
        here_a, here_b = by_group[r.groups[a]], by_group[r.groups[b]]
        if (len(here_a[net_b]) and len(here_b[net_a]) and len(here_a[net_a]) == 1
                and len(here_b[net_b]) == 1):  # fmt: skip
            faults.append(
                (
                    placed.ref,
                    f"{placed.ref} is the wrong way round: {r.words(a)} and {r.words(b)} are "
                    "each on the other's strip. Turn it.",
                )
            )
    return faults


def _misplaced(r: Reading, wanted: dict[str, list[Terminal]],
               skip: set[str]) -> list[tuple[str, str]]:  # fmt: skip
    """Each placed leg on a strip that carries only other nets (a part rewired in the
    schematic since it was placed, or a leg a strip off), with where it should go: the
    terminals of its own net, the placed ones by hole: the leg's part's ref, and the fault
    in words. Parts in `skip` (already named the wrong way round) are left out."""
    found = []
    by_group = groups_by_net(r)
    for t in sorted(r.words.leg_of, key=_key):
        ref, _ = r.words.leg_of[t]
        if ref in skip or t not in r.groups or t not in r.expected:
            continue
        own = r.expected[t]
        here = by_group[r.groups[t]]
        others = sorted(n for n in here if n != own)
        mates = [m for m in wanted[own] if m != t]
        if not others or len(here[own]) > 1 or not mates:
            continue
        placed = [r.words(m) for m in sorted(mates, key=_key) if m in r.groups]
        unplaced = [m for m in mates if m not in r.groups]
        goes = listed(placed[:3] + ([f"{len(placed) - 3} more"] if len(placed) > 3 else []))
        if not placed:
            many = "s" if len(unplaced) > 1 else ""
            goes = f"{len(unplaced)} terminal{many} not on the board yet"
        found.append(
            (
                ref,
                f"{_cap(r.words(t))} is on the strip of {', '.join(others)}, but the circuit puts "
                f"it on {own}: it should join {goes}.",
            )
        )
    return found


def _wanted(r: Reading) -> dict[str, list[Terminal]]:
    """Every terminal each net has, placed or not."""
    wanted: dict[str, list[Terminal]] = defaultdict(list)
    for part in r.board.values():
        for pin in part.pins.values():
            wanted[r.nets.net_of(*pin)].append(pin)
    for end in sorted(r.needed):
        wanted[r.ends[end]].append(end)
    return wanted


def _misfits(r: Reading, circuit: Circuit,
             wanted: dict[str, list[Terminal]]) -> list[tuple[str, str]]:  # fmt: skip
    """The parts placed the wrong way round, then the legs on another net's strip: each
    its part's ref and the fault in words."""
    turned = _wrong_way(r, circuit)
    return [*turned, *_misplaced(r, wanted, {ref for ref, _ in turned})]


def misfits(layout: Layout, circuit: Circuit, models: ModelLibrary,
            table: FootprintTable) -> list[str]:  # fmt: skip
    """The refs of the parts placed wrongly, in board order: the wrong way round, or a leg
    on a strip carrying only other nets (as the progress check names them). *Tidy up*
    offers them back to the tray."""
    r = read_layout(layout, circuit, models, table)
    found = {ref for ref, _ in _misfits(r, circuit, _wanted(r))}
    return [p.ref for p in r.layout.parts if p.ref in found]


def _gone(r: Reading, circuit: Circuit) -> list[str]:
    """What the board holds of parts the circuit no longer has (D-376): placed board parts
    (one that can't be placed now is still the circuit's: the tray names it), off-board parts
    put beside it, the parts of lugs a wire still runs to."""
    in_circuit = board_refs(circuit) | r.off_board
    gone = {p.ref for p in r.layout.parts} - in_circuit
    gone |= {ref for ref, _ in r.layout.spots} - {i.ref for i in r.items}
    for wire in r.layout.wires:
        for lug in (wire.lug, wire.to):
            if lug is not None and lug not in r.ends:
                gone.add(lug.partition(".")[0] if "." in lug else end_words(lug))
    return sorted(gone)


def progress(layout: Layout, circuit: Circuit, models: ModelLibrary, table: FootprintTable,
             loud: Sequence[LoudInput] = ()) -> Progress:  # fmt: skip
    """The editor's check of a board in the making (D-368): what's left to place, each
    net's progress, each leg's needs, what's wrong now (`loud`: the high-gain stages'
    input pins for the placement limits, `probe.loud_inputs`, D-400). `check_layout`
    still decides a board is done."""
    r = read_layout(layout, circuit, models, table)
    placed = {p.ref for p in r.layout.parts}
    in_circuit = r.board.keys() | r.off_board
    stale = _gone(r, circuit)
    kept = replace(r.layout, parts=tuple(p for p in r.layout.parts if p.ref in in_circuit))
    faults = [f for f in placement_faults(kept, r.board, r.off_board)
              if not f.endswith(" isn't on the board.")]  # fmt: skip
    wiring, unwired, loose = _wire_faults(r)
    wiring = [f for f in wiring if "which isn't an off-board lug" not in f]  # stale, above
    wanted = _wanted(r)
    faults = [*faults, *wiring, *(words for _, words in _misfits(r, circuit, wanted))]
    by_group = groups_by_net(r)
    seg = segments(r.layout)
    nets = []
    for net in sorted(wanted, key=lambda n: (n != GROUND, n)):
        members = sorted(wanted[net], key=_key)
        here = [t for t in members if t in r.groups]
        groups = {r.groups[t] for t in here}
        shorts = []
        for g in sorted(groups):
            for other, theirs in by_group[g].items():
                if other != net:
                    mine = by_group[g][net]
                    words = _short(*_closest(mine, theirs, r.words, seg), r.words)
                    shorts.append(Short(other, words))
        state: NetState = (
            "shorted" if shorts else
            "done" if len(here) == len(members) and len(groups) == 1 else "pieces"
        )  # fmt: skip
        wires = tuple(end_words(t) for t in members if isinstance(t, str) and t in unwired)
        nets.append(NetProgress(net, state, len(here), len(members), len(groups),
                                tuple(shorts), wires))  # fmt: skip
    legs: dict[str, list[LegProgress]] = {}
    holes = {(p.ref, leg): hole_name(h) for p in r.layout.parts for leg, h in p.legs}
    for ref, part in sorted(r.board.items()):
        rows = []
        for leg in part.legs:
            own = part.pins.get(leg)
            need = r.nets.net_of(*own) if own else None
            reach = tuple(
                Reach(_terminal_id(t, r.words),
                      own in r.groups and r.groups.get(t) == r.groups[own])
                for t in (sorted(wanted[need], key=_key) if need and own else ())
                if t != own
            )  # fmt: skip
            rows.append(LegProgress(leg, holes.get((ref, leg)), need, reach))
        legs[ref] = rows
    warnings = limit_warnings(r.layout, placement_limits(circuit, r.nets, r.board, loud))
    warnings += quiet_warnings(
        noisy_links(r.layout, r.board, r.nets, guards(r.board, r.nets, loud))
    )
    beside = alongside(r.layout, r.board, r.nets, loud, copper_groups(r.layout))
    warnings += apart_warnings(beside)
    touching = outline_overlaps(r.layout, r.board)
    overlaps, dismissed = dismissed_apart(layout, touching)
    done = check_layout(layout, circuit, models, table).ok
    mixed = {g for g, here in by_group.items() if len(here) > 1}
    copper = joined_groups(r.layout)[0]
    red = {hole for hole, g in copper.items() if g in mixed}
    spots = {**default_spots(r.items, r.layout), **dict(r.layout.spots)}
    return Progress(sorted(r.board.keys() - placed), unwired, loose, r.items,
                    {i.ref: spots[i.ref] for i in r.items},
                    r.unboardable, nets, legs, faults, stale, warnings, done,
                    runs(red), _rails(by_group, copper),
                    _choices(r, circuit, models, table), overlaps, dismissed,
                    note_states(layout, touching))  # fmt: skip


def _choices(r: Reading, circuit: Circuit, models: ModelLibrary,
             table: FootprintTable) -> dict[str, Choice]:  # fmt: skip
    """Each board part's and off-board part's `Choice`; a chip and an off-board part that
    stands for several circuit parts (a pot's gangs, a switch's poles) stay where they are."""
    chosen = chosen_where(circuit)
    kinds = {p.ref: p for p in circuit.parts}
    found: dict[str, Choice] = {}
    for ref in r.board:
        one = kinds.get(ref)
        why = why_not_moved(one) if one else "A chip stays on the board."
        found[ref] = Choice("board", ref in chosen, why)
    for item in r.items:
        refs = sorted({lug.end.split(".")[0] for lug in item.lugs} & kinds.keys())
        if item.ref == POWER or not refs:
            continue
        part = kinds[refs[0]]
        single = len(refs) == 1
        why = move_problem(part, True, models, table) if single else why_not_moved(part)
        found[item.ref] = Choice("off-board", single and part.ref in chosen, why)
    return found


def _rails(by_group: dict[int, dict[str, list[Terminal]]],
           copper: dict[Hole, int]) -> dict[str, list[tuple[int, int, int]]]:  # fmt: skip
    """The copper carrying only a rail (V+, V-, GND), by net, as runs (D-381); copper that
    also carries another net is a short's, not a rail's."""
    rail = {g: next(iter(here)) for g, here in by_group.items()
            if len(here) == 1 and next(iter(here)) in {GROUND, *SUPPLY_SIGNS}}  # fmt: skip
    holes: dict[str, set[Hole]] = defaultdict(set)
    for hole, g in copper.items():
        if g in rail:
            holes[rail[g]].add(hole)
    return {net: runs(found) for net, found in sorted(holes.items())}


def shorts(layout: Layout, circuit: Circuit, models: ModelLibrary,
           table: FootprintTable) -> dict[frozenset[str], str]:  # fmt: skip
    """Each pair of nets the board joins and the circuit doesn't, with its sentence (the
    nearest pair of terminals): what a board edit is refused for with shorts off (D-374)."""
    r = read_layout(layout, circuit, models, table)
    seg = segments(r.layout)
    found: dict[frozenset[str], str] = {}
    for here in groups_by_net(r).values():
        nets = list(here)
        for i, a in enumerate(nets):
            for b in nets[i + 1 :]:
                words = _short(*_closest(here[a], here[b], r.words, seg), r.words)
                found.setdefault(frozenset((a, b)), words)
    return found
