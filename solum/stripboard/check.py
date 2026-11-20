"""The check of a stripboard layout against its circuit (D-367).

The board is read back into nets (strips between cuts, joined by links; each leg puts its
pin on its strip; each pad its off-board ends) and compared, pin for pin, with the
circuit's own nets from `connect`: there is no second notion of a net. Every fault is a
plain-English sentence naming the parts and holes; a layout with none is the circuit.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Literal

from solum.circuit.connectivity import GROUND, Nets, connect
from solum.circuit.parts import PIN_WORDS, pin_offsets
from solum.circuit.schema import POLARISED, Battery, Capacitor, Circuit, DcJack, Switch
from solum.export import bom, built_where, is_status_led
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import Hole, Layout, Placed, hole_name, segments
from solum.stripboard.footprints import BoardPart, PinRef, board_parts, body_holes, leg_problem
from solum.stripboard.limits import limit_warnings, placement_limits

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
    its own, a pad's end its wire's net; a pad for nothing, none)."""
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
class _Reading:
    """A layout read against its circuit: what both checks start from."""

    nets: Nets
    board: dict[str, BoardPart]
    unboardable: list[str]  # parts the footprints table can't size
    off_board: set[str]
    ends: dict[str, str]
    layout: Layout  # either-way parts turned to fit
    words: _Words
    groups: dict[Terminal, int]
    expected: dict[Terminal, str]


def _read(layout: Layout, circuit: Circuit, models: ModelLibrary,
          table: FootprintTable) -> _Reading:  # fmt: skip
    nets = connect(circuit)
    board, unboardable = board_parts(circuit, models, table)
    off_board = {p.ref for p in circuit.parts if built_where(p) != "board"}
    ends = off_board_ends(circuit, nets, board)
    layout = _oriented(layout, board, circuit, nets, ends)
    groups = stripboard_nets(layout, board)
    return _Reading(nets, board, unboardable, off_board, ends, layout,
                    _Words(circuit, board, layout), groups,
                    _expected(groups, ends, nets))  # fmt: skip


def _pad_faults(layout: Layout, ends: dict[str, str]) -> tuple[list[str], list[str]]:
    """Pads for nothing or twice over, and the ends that have no pad yet."""
    faults = []
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
    return faults, [end for end in ends if end not in seen]


def _by_group(r: _Reading) -> dict[int, dict[str, list[Terminal]]]:
    """Each joined group of the board → its terminals by the net the circuit wants."""
    found: dict[int, dict[str, list[Terminal]]] = defaultdict(lambda: defaultdict(list))
    for t in sorted(r.expected, key=_key):
        found[r.groups[t]][r.expected[t]].append(t)
    return found


def check_layout(layout: Layout, circuit: Circuit, models: ModelLibrary,
                 table: FootprintTable) -> Checked:  # fmt: skip
    """Check `layout` against `circuit`: every fault in plain English (D-367)."""
    r = _read(layout, circuit, models, table)
    faults = [*r.unboardable, *placement_faults(r.layout, r.board, r.off_board)]
    pads, missing = _pad_faults(r.layout, r.ends)
    faults += pads + [f"There's no pad for {end_words(end)}." for end in missing]
    by_net: dict[str, dict[int, list[Terminal]]] = defaultdict(lambda: defaultdict(list))
    seg = segments(r.layout)
    for group, here in _by_group(r).items():
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
    `pieces` joined groups; `done` when all are placed, joined and touch no other net."""

    net: str
    state: NetState
    placed: int
    total: int
    pieces: int
    shorts: tuple[Short, ...] = ()


@dataclass(frozen=True)
class Reach:
    """A terminal a leg must reach (`R2.1` a board part's leg, `VR1.1` or `GND` an
    off-board wire's end) and whether the board joins them yet."""

    to: str
    joined: bool


@dataclass(frozen=True)
class LegProgress:
    leg: str
    hole: str | None  # None: not placed
    net: str | None  # None: a leg the circuit doesn't use
    reach: tuple[Reach, ...]


@dataclass(frozen=True)
class OffBoardPart:
    """An off-board part as the tray lists it, one per thing bought (a switch however many
    poles, a dual pot once, the guitar's and amp's jacks when none is drawn): `ref` with
    its name ("VR1 (Gain)"), what it is, its value and details, as the parts list says."""

    ref: str
    part: str
    value: str
    details: str


def off_board_parts(circuit: Circuit, models: ModelLibrary) -> list[OffBoardPart]:
    """The off-board parts, from the parts list's own off-board lines (D-203), in its order."""
    return [OffBoardPart(ref, line.part, line.value, line.details)
            for line in bom(circuit, models) if line.where == "off-board"
            for ref in line.refs]  # fmt: skip


@dataclass(frozen=True)
class Progress:
    """Where a board stands: `to_place` the parts and `pads_to_place` the off-board wires not on it
    yet (not faults); `off_board` the off-board parts not yet beside it (every one until they
    can be dragged in); `stock` the bypass hardware the schematic doesn't draw (`stock_bypass`);
    `unplaceable` a sentence per part that can't go on a board yet (no footprint: it stays in
    the tray, D-370); `nets` each net's progress; `legs` each board part's legs; `faults` what's
    wrong now (placement, pads, a part the wrong way round); `stale` parts no longer in the
    circuit; `warnings` the placement limits broken; `done` the full check passes."""

    to_place: list[str]
    pads_to_place: list[str]
    off_board: list[OffBoardPart]
    stock: list[str]
    unplaceable: list[str]
    nets: list[NetProgress]
    legs: dict[str, list[LegProgress]]
    faults: list[str]
    stale: list[str]
    warnings: list[str]
    done: bool

    @property
    def nets_done(self) -> int:
        return sum(n.state == "done" for n in self.nets)


STOCK_FOOTSWITCH = "footswitch"
STOCK_LED = "status LED"


def stock_bypass(circuit: Circuit) -> list[str]:
    """The stock bypass hardware the Board view offers (D-370): a 3PDT footswitch unless
    the schematic draws a latching footswitch, a status LED unless it draws one (an LED
    labelled "status"). Never both a drawn one and the stock one."""
    stomp = any(
        isinstance(p, Switch) and p.switch_kind.positions == ("On", "Bypassed")
        for p in circuit.parts
    )  # the latching stomps (switches.py's `_stomp`), not a momentary one
    led = any(is_status_led(p) for p in circuit.parts)
    return [name for name, drawn in ((STOCK_FOOTSWITCH, stomp), (STOCK_LED, led)) if not drawn]


def _terminal_id(t: Terminal, words: _Words) -> str:
    """A terminal as the editor names it: a board part's `ref.leg` (as the layout holds
    it), an off-board end as it is."""
    if isinstance(t, str):
        return t
    ref, leg = words.leg_of.get(t, t)
    return f"{ref}.{leg}"


def _wrong_way(r: _Reading, circuit: Circuit) -> list[str]:
    """Each polarised two-leg part placed each leg on the other's net."""
    kinds = {p.ref: p for p in circuit.parts}
    faults = []
    by_group = _by_group(r)
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
                f"{placed.ref} is the wrong way round: {r.words(a)} and {r.words(b)} are "
                "each on the other's strip. Turn it."
            )
    return faults


def progress(layout: Layout, circuit: Circuit, models: ModelLibrary,
             table: FootprintTable) -> Progress:  # fmt: skip
    """The editor's check of a board in the making (D-368): what's left to place, each
    net's progress, each leg's needs, what's wrong now. `check_layout` still decides a
    board is done."""
    r = _read(layout, circuit, models, table)
    placed = {p.ref for p in r.layout.parts}
    in_circuit = r.board.keys() | r.off_board
    stale = sorted(placed - in_circuit)
    kept = replace(r.layout, parts=tuple(p for p in r.layout.parts if p.ref in in_circuit))
    faults = [f for f in placement_faults(kept, r.board, r.off_board)
              if not f.endswith(" isn't on the board.")]  # fmt: skip
    pads, missing = _pad_faults(r.layout, r.ends)
    faults = [*faults, *pads, *_wrong_way(r, circuit)]
    # every terminal each net has, placed or not
    wanted: dict[str, list[Terminal]] = defaultdict(list)
    for part in r.board.values():
        for pin in part.pins.values():
            wanted[r.nets.net_of(*pin)].append(pin)
    for end, net in r.ends.items():
        wanted[net].append(end)
    by_group = _by_group(r)
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
        nets.append(NetProgress(net, state, len(here), len(members), len(groups), tuple(shorts)))
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
    warnings = limit_warnings(r.layout, placement_limits(circuit, r.nets, r.board))
    done = check_layout(layout, circuit, models, table).ok
    return Progress(sorted(r.board.keys() - placed), missing,
                    off_board_parts(circuit, models), stock_bypass(circuit),
                    r.unboardable, nets, legs, faults, stale, warnings, done)  # fmt: skip
