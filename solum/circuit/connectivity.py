"""Nets from wires, pins and labels.

Points connect when they coincide, when a wire runs between them, or when one sits on
a wire's segment (a T-junction). Crossing wires don't connect. Labels name the net at
their point; the same label name anywhere is the same net (that's how rails like `V+`
and `GND` are global). An unlabelled net is named after its first pin, e.g. `R1.2`.
"""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from solum.circuit.parts import pin_positions
from solum.circuit.schema import (
    CHIP_UNITS,
    AmpInput,
    Bjt,
    Capacitor,
    ChargePump,
    Circuit,
    Diode,
    Guitar,
    Inductor,
    Inverter,
    Jack,
    Jfet,
    Led,
    Mosfet,
    Opamp,
    Ota,
    Point,
    Pot,
    PowerUnit,
    Regulator,
    Resistor,
    Switch,
    Trimmer,
)

GROUND = "GND"

PinRef = tuple[str, str]  # (ref, pin)


class ConnectivityError(ValueError):
    """The wiring is contradictory (plain-English message). `names`: the net labels
    wired together, when that's the problem."""

    def __init__(self, message: str, names: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.names = names


@dataclass(frozen=True, eq=False)
class Nets:
    """A drawing's nets. `connect` hands the same object to every circuit drawn alike, so
    one is told from another by which it is, not by comparing (it can be a memo's key)."""

    by_pin: dict[PinRef, str]
    members: dict[str, tuple[PinRef, ...]]

    def net_of(self, ref: str, pin: str) -> str:
        return self.by_pin[(ref, pin)]

    def resolve(self, name: str) -> str:
        """Net for a net name (`OUT`, `V+`) or a pin reference (`Q1.D`, `R1.2`)."""
        if name in self.members:
            return name
        ref, dot, pin = name.partition(".")
        if dot and (ref, pin) in self.by_pin:
            return self.by_pin[(ref, pin)]
        raise ConnectivityError(
            f"There's no net or pin called {name!r}. Use a net label (like OUT) or a "
            "part pin (like Q1.D)."
        )


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[Point, Point] = {}

    def find(self, p: Point) -> Point:
        self.parent.setdefault(p, p)
        while self.parent[p] != p:
            self.parent[p] = self.parent[self.parent[p]]
            p = self.parent[p]
        return p

    def union(self, a: Point, b: Point) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def on_segment(p: Point, a: Point, b: Point) -> bool:
    """True if p lies on the segment a-b (ends included)."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


# Parts whose pins name an unlabelled net first: "Q4.B" says where you are, "C10.2" doesn't
ACTIVE_PARTS = (Bjt, Jfet, Mosfet, Opamp, Inverter, Ota, ChargePump, Regulator)


def _fallback_name(refs: list[PinRef], active: frozenset[str]) -> str:
    """An unlabelled net's name (D-082): its first transistor or op-amp pin, else its
    first pin (`refs` is sorted)."""
    ref, pin = next((r for r in refs if r[0] in active), refs[0])
    return f"{ref}.{pin}"


CONNECT_MEMO = 256  # drawings whose nets are kept


def connect(circuit: Circuit) -> Nets:
    """The circuit's nets. They depend only on the drawing (where pins, wires and labels
    sit), so a circuit that differs in values alone (a knob turned, a part swapped in a
    search) gets the nets already worked out: a search asks thousands of times (Phase 10).
    The answer is shared: don't change it."""
    pins = tuple(
        (p.ref, name, pos) for p in circuit.parts for name, pos in pin_positions(p).items()
    )
    wires = tuple((w.from_, w.to) for w in circuit.wires)
    labels = tuple((lb.net, lb.pos) for lb in circuit.labels)
    active = frozenset(p.ref for p in circuit.parts if isinstance(p, ACTIVE_PARTS))
    return _nets(pins, wires, labels, active)


@lru_cache(maxsize=CONNECT_MEMO)
def _nets(
    pin_list: tuple[tuple[str, str, Point], ...],
    wires: tuple[tuple[Point, Point], ...],
    labels: tuple[tuple[str, Point], ...],
    active: frozenset[str],
) -> Nets:
    uf = _UnionFind()
    pins = {(ref, name): pos for ref, name, pos in pin_list}
    points = set(pins.values()) | {pos for _, pos in labels}
    for a, b in wires:
        points |= {a, b}
    for p in points:
        uf.find(p)
    for a, b in wires:
        uf.union(a, b)
        for p in points:
            if on_segment(p, a, b):
                uf.union(p, a)
    first_label_point: dict[str, Point] = {}
    for net, pos in labels:
        uf.union(pos, first_label_point.setdefault(net, pos))

    names_by_root: dict[Point, set[str]] = defaultdict(set)
    for net, pos in labels:
        names_by_root[uf.find(pos)].add(net)
    for names in names_by_root.values():
        if len(names) > 1:
            raise ConnectivityError(
                f"Net labels {' and '.join(sorted(names))} are wired together. A net can have "
                "only one name: remove a label or the wire joining them.",
                tuple(sorted(names)),
            )

    pins_by_root: dict[Point, list[PinRef]] = defaultdict(list)
    for pin_ref, pos in sorted(pins.items()):
        pins_by_root[uf.find(pos)].append(pin_ref)
    by_pin: dict[PinRef, str] = {}
    members: dict[str, tuple[PinRef, ...]] = {}
    for root, refs in pins_by_root.items():
        labelled = names_by_root.get(root)
        name = next(iter(labelled)) if labelled else _fallback_name(refs, active)
        members[name] = tuple(refs)
        by_pin.update(dict.fromkeys(refs, name))
    for names in names_by_root.values():  # labelled nets with no pins (e.g. a rail)
        members.setdefault(next(iter(names)), ())
    return Nets(by_pin=by_pin, members=members)


# Parts that pass current only between their own pins: with one pin joined, none flows
PASSIVE_PARTS = (Resistor, Capacitor, Inductor, Pot, Trimmer, Diode, Led, Switch)
GROUNDED_PARTS = (Guitar, AmpInput)  # tied to ground inside, whatever their pins touch
# drawn for the build, absent from the simulation: a jack (D-174), a chip's power unit (its
# chip's op-amps take their supply from its nets, D-179)
DRAWING_ONLY = (Jack, PowerUnit)


def loose_parts(circuit: Circuit, nets: Nets) -> set[str]:
    """Refs of the parts no current can reach, which the simulation leaves out (D-165):
    a group of parts that touches no ground, supply, block port, guitar or amp (a part
    dropped on the sheet, a stage not yet wired in), and a passive part with at most one
    pin joined to the rest (a resistor wired at one end), until none is left. None while
    no part reaches an anchor: then the whole drawing has no ground, not a stray part.
    A drawing-only part (a jack, D-174) is never loose, and no path runs through it; a
    chip's unit counts as joined to its power unit's supply nets.
    The answer depends on the wiring and on what kind each part is, not on values, so it
    is kept per drawing like the nets (a search asks on every netlist; Phase 10)."""
    anchors = frozenset(
        {GROUND, *circuit.power.rails, *(circuit.ports.values() if circuit.template else ())}
    )
    chipped = (PowerUnit, *CHIP_UNITS)  # the only parts with a chip (asking the rest is slow)
    kinds = tuple(
        (p.ref, type(p), p.chip, bool(getattr(p, "half", None)))
        if isinstance(p, chipped)
        else (p.ref, type(p), None, False)
        for p in circuit.parts
    )
    return set(_loose(nets, anchors, kinds))


@lru_cache(maxsize=CONNECT_MEMO)
def _loose(
    nets: Nets, anchors: frozenset[str], kinds: tuple[tuple[str, type, str | None, bool], ...]
) -> frozenset[str]:
    """`loose_parts` from what it depends on: the nets, the anchor nets, and each part's
    ref, type, chip and whether it is one unit of a chip."""

    def refs(*types: type) -> set[str]:
        return {ref for ref, kind, _, _ in kinds if issubclass(kind, types)}

    nets_of: dict[str, set[str]] = defaultdict(set)
    for (ref, _pin), net in nets.by_pin.items():
        nets_of[ref].add(net)
    # a chip's units run from its power unit's supply (D-179, D-180): reached through it
    supply = {
        chip: set(nets_of[ref]) for ref, kind, chip, _ in kinds if issubclass(kind, PowerUnit)
    }
    drawn = refs(*DRAWING_ONLY)  # no path through
    refs_on = {net: {ref for ref, _ in pins} - drawn for net, pins in nets.members.items()}
    for ref, kind, chip, half in kinds:
        if issubclass(kind, CHIP_UNITS) and half:
            for net in supply.get(chip, set()):
                nets_of[ref].add(net)
                refs_on[net].add(ref)
    grounded = refs(*GROUNDED_PARTS)
    # the groups that touch an anchor, searched outward from it
    seen_nets = set(anchors) | {n for ref in grounded for n in nets_of[ref]}
    kept, todo = set(grounded), list(seen_nets)
    while todo:
        for ref in refs_on.get(todo.pop(), ()):
            if ref not in kept:
                kept.add(ref)
                fresh = nets_of[ref] - seen_nets
                seen_nets |= fresh
                todo += fresh
    if not kept:  # nothing grounded yet: no-dc-path says what to do
        return frozenset()
    passive = refs(*PASSIVE_PARTS)

    def joined(ref: str, net: str) -> bool:
        return net in anchors or any(r != ref and r in kept for r in refs_on[net])

    while dangling := {r for r in kept & passive if sum(joined(r, n) for n in nets_of[r]) <= 1}:
        kept -= dangling
    return frozenset({ref for ref, _, _, _ in kinds} - kept - drawn)


def spare_poles(circuit: Circuit, nets: Nets) -> set[str]:
    """Refs of a switch's spare poles: no lug wired to anything while another pole of the
    same switch is (a 4PDT slide used as a 3PDT, as Aion's Klon). Loose, so the simulation
    leaves them out, but nothing to fix: no rule names them."""
    switches = [p for p in circuit.parts if isinstance(p, Switch) and p.pole is not None]
    unwired = {
        p.ref
        for p in switches
        if all(len(nets.members[net]) == 1 for (ref, _), net in nets.by_pin.items() if ref == p.ref)
    }
    in_use = {p.ref[:-1] for p in switches if p.ref not in unwired}
    return {ref for ref in unwired if ref[:-1] in in_use}


def loose_net(nets: Nets, loose: set[str], net: str) -> bool:
    """Only `loose` parts (`loose_parts`) touch `net`: the simulation has nothing there."""
    pins = nets.members.get(net, ())
    return bool(pins) and all(ref in loose for ref, _ in pins)
