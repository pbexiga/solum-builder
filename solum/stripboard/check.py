"""The check of a stripboard layout against its circuit (D-367).

The board is read back into nets (strips between cuts, joined by links; each leg puts its
pin on its strip; each pad its off-board ends) and compared, pin for pin, with the
circuit's own nets from `connect`: there is no second notion of a net. Every fault is a
plain-English sentence naming the parts and holes; a layout with none is the circuit.
"""

from collections import defaultdict
from dataclasses import dataclass

from solum.circuit.connectivity import GROUND, Nets, connect
from solum.circuit.parts import PIN_WORDS, pin_offsets
from solum.circuit.schema import POLARISED, Battery, Capacitor, Circuit, DcJack
from solum.export import built_where
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import Hole, Layout, hole_name, segments
from solum.stripboard.footprints import BoardPart, PinRef, board_parts, body_holes, leg_problem

Terminal = PinRef | str  # a board part's pin, or an off-board end ("VR1.1", "V+")
SUPPLY_PARTS = (Battery, DcJack)  # a drawn supply: its own pins are the supply's wires
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


def off_board_ends(circuit: Circuit, nets: Nets, board: dict[str, BoardPart]) -> dict[str, str]:
    """Every off-board wire the board needs, end → net: each off-board part's pin on a net
    the board carries (pot lugs, IN's and OUT's, a jack's), and each supply rail and
    ground the board carries unless a drawn battery or DC jack's pin brings it."""
    carried = {nets.net_of(*pin) for part in board.values() for pin in part.pins.values()}
    ends: dict[str, str] = {}
    brought: set[str] = set()
    for part in circuit.parts:
        if built_where(part) == "board":
            continue
        for pin in pin_offsets(part):
            net = nets.by_pin.get((part.ref, pin))
            if net in carried:
                ends[f"{part.ref}.{pin}"] = net
                if isinstance(part, SUPPLY_PARTS):
                    brought.add(net)
    for supply in sorted({*circuit.power.rails, GROUND} & carried - brought):
        ends[supply] = supply
    return ends


def end_words(end: str) -> str:
    """An off-board end in words: "the input", "ground", "the V- supply", "VR1 lug 1"."""
    named = {"IN.out": "the input", "OUT.in": "the output", GROUND: "ground"}
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
        for pad in layout.pads:
            for end in pad.ends:
                self.where[end] = hole_name(pad.hole)
                self.hole_of[end] = pad.hole

    def __call__(self, terminal: Terminal) -> str:
        at = self.where.get(terminal, "")
        if isinstance(terminal, str):
            return f"the wire to {end_words(terminal)} (pad {at})"
        ref, pin = terminal
        board_ref, leg = self.leg_of.get(terminal, (ref, pin))
        part = self.board.get(board_ref)
        kind = part.kind if part else ""
        original = self.kinds.get(ref)
        if kind == "chip":
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


def _occupants(layout: Layout) -> tuple[dict[Hole, list[str]], list[str]]:
    """Who has a wire or leg in each hole, and the faults of where links and pads are."""
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
    for pad in layout.pads:
        used[pad.hole].append(f"the pad for {', '.join(end_words(e) for e in pad.ends)}")
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
            faults.append(f"{ref} goes off the board: wire it to pads instead.")
        else:
            faults.append(f"{ref} is on the board but not in the circuit.")
    used, occupied = _occupants(layout)
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
        if part.footprint.shape == "axial" and not p.standing:
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


def stripboard_nets(layout: Layout, board: dict[str, BoardPart]) -> dict[Terminal, int]:
    """The board read back into nets: each terminal (a board part's pin, a free leg as
    (ref, "#leg"), a pad's end) → its group; terminals in one group are joined."""
    seg = segments(layout)
    parent: dict[int, int] = {}

    def find(a: int) -> int:
        while parent.get(a, a) != a:
            a = parent[a]
        return a

    for link in layout.links:
        a, b = seg.get(link.a), seg.get(link.b)
        if a is not None and b is not None:
            parent[max(find(a), find(b))] = min(find(a), find(b))
    groups: dict[Terminal, int] = {}
    for placed in layout.parts:
        part = board.get(placed.ref)
        for leg, hole in placed.legs:
            if part is None or hole not in seg:
                continue
            if leg in part.pins:
                groups[part.pins[leg]] = find(seg[hole])
            elif leg in part.free:
                groups[(placed.ref, f"#{leg}")] = find(seg[hole])
    for pad in layout.pads:
        if pad.hole in seg:
            for end in pad.ends:
                groups[end] = find(seg[pad.hole])
    return groups


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


def check_layout(layout: Layout, circuit: Circuit, models: ModelLibrary,
                 table: FootprintTable) -> Checked:  # fmt: skip
    """Check `layout` against `circuit`: every fault in plain English (D-367)."""
    nets = connect(circuit)
    board, faults = board_parts(circuit, models, table)
    off_board = {p.ref for p in circuit.parts if built_where(p) != "board"}
    faults += placement_faults(layout, board, off_board)
    ends = off_board_ends(circuit, nets, board)
    words = _Words(circuit, board, layout)
    seen: dict[str, str] = {}
    for pad in layout.pads:
        for end in pad.ends:
            if end not in ends:
                faults.append(
                    f"Pad {hole_name(pad.hole)} goes to {end!r}, which isn't an off-board "
                    "wire this circuit needs."
                )
            elif end in seen:
                faults.append(
                    f"{_cap(end_words(end))} has two pads ({seen[end]} and "
                    f"{hole_name(pad.hole)}): give it one."
                )
            seen.setdefault(end, hole_name(pad.hole))
    for end in ends:
        if end not in seen:
            faults.append(f"There's no pad for {end_words(end)}.")
    groups = stripboard_nets(layout, board)
    expected: dict[Terminal, str] = {}
    for t in groups:
        if isinstance(t, str):
            if t in ends:
                expected[t] = ends[t]
        elif t[1].startswith("#"):
            expected[t] = f"{t[0]}{t[1]}"  # a free leg: a net of its own
        else:
            expected[t] = nets.net_of(*t)
    by_group: dict[int, list[Terminal]] = defaultdict(list)
    by_net: dict[str, dict[int, list[Terminal]]] = defaultdict(lambda: defaultdict(list))
    for t in sorted(expected, key=_key):
        by_group[groups[t]].append(t)
        by_net[expected[t]][groups[t]].append(t)
    seg = segments(layout)
    for members in by_group.values():
        by_net_here: dict[str, list[Terminal]] = defaultdict(list)
        for t in members:
            by_net_here[expected[t]].append(t)
        found = list(by_net_here.values())
        faults += [_short(*_closest(found[0], other, words, seg), words) for other in found[1:]]
    for split in by_net.values():
        parts = list(split.values())
        for other in parts[1:]:
            faults.append(
                f"{_cap(words(parts[0][0]))} and {words(other[0])} aren't connected on the "
                "board, but the circuit joins them."
            )
    carried = {n for n in by_net if not n.startswith(tuple(f"{r}#" for r in board))}
    return Checked(faults, len(carried))
