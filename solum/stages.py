"""Stages and clippers on the signal path, in signal order, and the Bias & headroom
pane's measures (Phase 8c, D-106). Pure: topology from the nets, numbers in, numbers out;
`probe.stages_view` runs the simulations and puts the rows together.

A **stage** is a transistor or an op-amp section the signal passes through. Its kind
comes from where the signal leaves it: the collector or drain (a gain stage), the
emitter or source when the collector or drain sits on a supply (a buffer: a follower),
or an op-amp's output.

A **discrete op-amp** (D-224) is three transistors working as one op-amp, as the BD-2's
Q2, Q3 and Q4: a matched pair sharing their emitters or sources (the inputs), one of
whose collector or drain drives a third transistor (the output), whose output comes back
through passive parts to the other's input (the feedback). It's one stage, measured as an
op-amp is, from its + input to its output: its gain is its feedback's.

A **clipper** is a group of diodes (a pair, or series chains) between the same two
nets, at least one of them on the signal path and neither on a supply other than
ground. Its kind is where it sits: to ground (hard clipping), in feedback (across an
op-amp's or a transistor's output and input: soft clipping), or in series. Protection,
pump and indicator diodes touch a supply or sit off the signal path, so they aren't
clippers.
"""

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from solum.circuit.connectivity import GROUND, Nets
from solum.circuit.parts import closed_contacts, pin_offsets
from solum.circuit.schema import (
    Bjt,
    Circuit,
    Diode,
    Guitar,
    Jfet,
    Led,
    Mosfet,
    Opamp,
    Pot,
    Switch,
    VSource,
)
from solum.netlist import input_part
from solum.rules.graph import distances, quiet_nets, signal_edges
from solum.view import rail_nets

Kind = Literal["stage", "clipper"]

# the bias bar: within this of the middle reads "centred" (position 0.5 ± this)
CENTRED = 0.1
# a clipper driven this many dB or more is clipping; less reads "not clipping yet"
CLIPPING_DB = 1.0
# one kind of harmonic "leads" when it's this many dB above the other
LEADS_DB = 3.0
LEVEL_NAMES = {"soft": "soft", "med": "medium", "hard": "hard"}

# where the signal leaves each kind of transistor, and the pin it's measured against
_OUT_PINS = {"bjt": ("C", "E", "B"), "jfet": ("D", "S", "G"), "mosfet": ("D", "S", "G")}
# (out, common, in) above; the transistors a stage can be
Transistor = Bjt | Jfet | Mosfet


@dataclass(frozen=True)
class Stage:
    """A row of the pane: a stage or a clipper, where it's measured and how far along."""

    kind: Kind
    refs: tuple[str, ...]
    role: str  # gain stage, buffer, op-amp stage; to ground, in feedback, in series
    net: str  # the stage's output terminal; the clipper's node
    order: int  # edges from the guitar along the signal path
    other: str = GROUND  # a clipper's other end: its clamp is read across the two
    inputs: tuple[str, str] | None = None  # a discrete op-amp's + and - input nets (D-224)

    @property
    def label(self) -> str:
        """Its refs; a discrete op-amp's in signal order: + input, - input, output."""
        refs = (*self.refs[1:], self.refs[0]) if self.inputs else self.refs
        return ", ".join(refs)


def signal_stages(circuit: Circuit, nets: Nets) -> list[Stage]:
    """The stages and clippers a signal from the guitar can reach, in signal order (a
    clipper right after the stage whose output it holds). Empty without a guitar input."""
    guitar = input_part(circuit)
    if guitar is None:
        return []
    supplies = rail_nets(circuit, nets)
    quiet = quiet_nets(circuit, nets)
    order = distances(nets.net_of(guitar.ref, "out"), signal_edges(circuit, nets), quiet)
    # a stage whose output is a quiet net (an op-amp buffering VREF) carries no signal
    found = _stages(circuit, nets, quiet, order) + _clippers(circuit, nets, supplies, order)
    return sorted(found, key=lambda s: (s.order, s.kind == "clipper", s.refs))


def stage_parts(circuit: Circuit, nets: Nets, refs: Sequence[str]) -> list[str]:
    """The parts a click on a stage or clipper lights (D-122): its own (`refs`), then
    every part with a pin on one of their nets, other than a supply or ground, in the
    circuit's order. A part joining two stages (a coupling cap) is in both; the guitar
    and the amp aren't parts of a stage. A closed switch contact joins its nets (9c, two
    voices): the leg a switch picks is the stage's, the open one isn't."""
    held = rail_nets(circuit, nets)
    mine = {
        n for n, pins in nets.members.items() if n not in held and any(r in refs for r, _ in pins)
    }
    joins = [
        {nets.net_of(p.ref, a), nets.net_of(p.ref, b)}
        for p in circuit.parts
        if isinstance(p, Switch)
        for a, b in closed_contacts(p)
    ]
    grown = True
    while grown:  # across a chain of closed contacts
        grown = False
        for pair in joins:
            if pair & mine and not pair <= mine and not pair & held:
                mine |= pair
                grown = True
    touching = {r for n in mine for r, _ in nets.members[n]}
    others = [
        p.ref
        for p in circuit.parts
        if p.ref in touching and p.ref not in refs and p.type not in ("guitar", "amp")
    ]
    return [*refs, *others]


@dataclass(frozen=True)
class PotPlace:
    """Where a pot's chip sits on the stage chain (D-122): on a block (`index`: the row),
    on the arrow after a row (`index`; -1: after the guitar), or at the end. `ref` is the
    knob's: a dual pot's name (VR1), on each block its gangs act on (D-217)."""

    ref: str
    at: Literal["block", "arrow", "end"]
    index: int = -1


def pot_places(circuit: Circuit, nets: Nets, rows: Sequence[Stage]) -> list[PotPlace]:
    """Where each pot acts, in the circuit's order (D-122): on the first stage whose input
    pins it touches or whose feedback it's in (a passive path from one of its pins to the
    stage's output and from another to its input, not through the stage; the block wins
    over the path), else on the arrow after the last row the signal reaches before it
    (the fewest steps from the guitar to one of its nets), else at the end: after the last
    row, or when the signal doesn't reach it. The guitar's own volume comes first, on the
    arrow after the guitar."""
    guitar = input_part(circuit)
    quiet = quiet_nets(circuit, nets)
    order = (
        distances(nets.net_of(guitar.ref, "out"), signal_edges(circuit, nets), quiet)
        if guitar
        else {}
    )
    places = []
    if isinstance(guitar, Guitar) and guitar.has_volume:  # before everything
        places.append(PotPlace(guitar.ref, "arrow" if rows else "end"))
    for pot in (p for p in circuit.parts if isinstance(p, Pot)):
        mine = {nets.net_of(pot.ref, pin) for pin in ("1", "2", "3")} - quiet
        passive = signal_edges(circuit, nets, skip=pot.ref, active=False)
        block = next(
            (i for i, r in enumerate(rows)
             if r.kind == "stage" and _acts_on(circuit, nets, r, mine, passive, quiet)),
            None,
        )  # fmt: skip
        if block is not None:
            places.append(PotPlace(pot.knob, "block", block))
            continue
        reached = [order[n] for n in mine if n in order]
        before = [i for i, r in enumerate(rows) if reached and r.order < min(reached)]
        if not reached or not rows or (before and before[-1] == len(rows) - 1):
            places.append(PotPlace(pot.knob, "end"))
        else:
            places.append(PotPlace(pot.knob, "arrow", before[-1] if before else -1))
    return list(dict.fromkeys(places))  # a dual pot's gangs in one place: one chip (D-217)


def signal_input(circuit: Circuit, nets: Nets, stage: Stage) -> str | None:
    """The net where the signal enters a row (D-123): a transistor's base or gate, an
    op-amp's + input, a clipper to ground's own node. None for a clipper in feedback or
    in series (it sits on a stage's own nets). An op-amp's + input may only carry its
    bias (an inverting stage, fed through a resistor to its - input): the caller checks
    the signal reaches it."""
    if stage.kind == "clipper":
        return stage.net if stage.role == "to ground" else None
    if stage.inputs:  # a discrete op-amp: its + input (D-224)
        return stage.inputs[0]
    p = circuit.part(stage.refs[0])
    if isinstance(p, Opamp):
        return nets.net_of(p.ref, "+")
    assert isinstance(p, Transistor)
    return nets.net_of(p.ref, _OUT_PINS[p.type][2])


def _acts_on(
    circuit: Circuit,
    nets: Nets,
    stage: Stage,
    mine: set[str],
    passive: Sequence[tuple[str, str]],
    quiet: set[str],
) -> bool:
    """Whether a pot on nets `mine` touches `stage`'s input pins or is in its feedback."""
    p = circuit.part(stage.refs[0])
    inputs: tuple[str, ...]
    if stage.inputs:  # a discrete op-amp (D-224): as an op-amp, its inputs are nets
        out, inp = stage.net, stage.inputs[1]
        if mine & set(stage.inputs):
            return True
    elif isinstance(p, Opamp):
        out, inputs, inp = nets.net_of(p.ref, "out"), ("+", "-"), nets.net_of(p.ref, "-")
    else:
        assert isinstance(p, Transistor)
        out_pin, common, in_pin = _OUT_PINS[p.type]
        follower = stage.role == "buffer"
        out = nets.net_of(p.ref, common if follower else out_pin)
        inputs = (in_pin,) if follower else (in_pin, common)
        inp = nets.net_of(p.ref, in_pin)
    if not stage.inputs and mine & {nets.net_of(p.ref, pin) for pin in inputs}:
        return True
    to_out = distances(out, passive, quiet | {inp})
    to_in = distances(inp, passive, quiet | {out})
    return any(a in to_out and b in to_in for a in mine for b in mine if a != b)


def _stages(circuit: Circuit, nets: Nets, quiet: set[str], order: Mapping[str, int]) -> list[Stage]:
    """Every op-amp, transistor and discrete op-amp whose output the signal reaches. One
    whose output is quiet (a supply, or a bias net such as VREF: `quiet_nets`) isn't a
    stage: the BD-2's IC1A, buffering VB, carries no signal. A transistor whose collector
    or drain is quiet is a follower, measured at its emitter or source."""
    supplies = quiet
    found = []
    grouped = discrete_opamps(circuit, nets, supplies)
    inside = {ref for d in grouped for ref in d.refs}
    for d in grouped:
        if d.net in order and d.net not in supplies:
            found.append(
                Stage("stage", d.refs, DISCRETE_ROLE, d.net, order[d.net], inputs=d.inputs)
            )
    for p in circuit.parts:
        if p.ref in inside:
            continue
        if isinstance(p, Opamp):
            net, role = nets.net_of(p.ref, "out"), "op-amp stage"
        elif isinstance(p, Transistor):
            out, common, _ = _OUT_PINS[p.type]
            follower = nets.net_of(p.ref, out) in supplies
            net = nets.net_of(p.ref, common if follower else out)
            role = "buffer" if follower else "gain stage"
        else:
            continue
        if net in order and net not in supplies:
            found.append(Stage("stage", (p.ref,), role, net, order[net]))
    return found


DISCRETE_ROLE = "discrete op-amp"


@dataclass(frozen=True)
class DiscreteOpamp:
    """Three transistors working as one op-amp (D-224). `refs`: the output transistor,
    then the + and - input transistors; `net`: its output; `inputs`: the + and - nets."""

    refs: tuple[str, str, str]
    net: str
    inputs: tuple[str, str]


def discrete_opamps(circuit: Circuit, nets: Nets, supplies: set[str]) -> list[DiscreteOpamp]:
    """Every discrete op-amp (D-224): two transistors of the same type and model whose
    emitters or sources share a net that isn't a supply (the pair); a third transistor
    whose base or gate is on one of the pair's collector or drain (that one is the +
    input: through the output stage the signal comes out the same way up); and a passive
    path from the third's output to the other's input that goes round every transistor
    (the feedback). Without that path it isn't an op-amp in use, so it isn't one."""
    parts = [p for p in circuit.parts if isinstance(p, Transistor)]
    passive = signal_edges(circuit, nets, active=False)

    def pin(p: Transistor, i: int) -> str:
        return nets.net_of(p.ref, _OUT_PINS[p.type][i])

    found: list[DiscreteOpamp] = []
    used: set[str] = set()
    for a_i, a in enumerate(parts):
        for b in parts[a_i + 1 :]:
            if a.type != b.type or a.model != b.model or {a.ref, b.ref} & used:
                continue
            tail = pin(a, 1)
            if tail != pin(b, 1) or tail in supplies:
                continue
            for plus, minus in ((a, b), (b, a)):
                driven = next(
                    (t for t in parts
                     if t.ref not in (a.ref, b.ref) and t.ref not in used
                     and pin(t, 2) == pin(plus, 0) and pin(t, 0) not in supplies),
                    None,
                )  # fmt: skip
                if driven is None:
                    continue
                out, back = pin(driven, 0), pin(minus, 2)
                if back not in distances(out, passive, supplies | {GROUND}):
                    continue
                found.append(
                    DiscreteOpamp((driven.ref, plus.ref, minus.ref), out, (pin(plus, 2), back))
                )
                used |= {a.ref, b.ref, driven.ref}
                break
    return found


def _clippers(
    circuit: Circuit, nets: Nets, supplies: set[str], order: Mapping[str, int]
) -> list[Stage]:
    diodes = [p for p in circuit.parts if isinstance(p, Diode | Led)]
    held = supplies | _source_nets(circuit, nets)
    by_ends: dict[frozenset[str], list[str]] = defaultdict(list)
    for chain, chain_ends in _chains(diodes, nets):
        if len(chain_ends) == 2:
            by_ends[frozenset(chain_ends)].extend(chain)
    found = []
    for ends, refs in by_ends.items():
        signal = ends - {GROUND}
        if not signal or signal & held or not signal & set(order):
            continue
        role, node = _clipper_role(circuit, nets, ends, order)
        other = next(iter(ends - {node}))
        found.append(Stage("clipper", tuple(sorted(refs)), role, node, order[node], other))
    return found


def _source_nets(circuit: Circuit, nets: Nets) -> set[str]:
    """Nets a DC source holds (a bias battery, V16): a diode to one isn't a clipper."""
    return {nets.net_of(p.ref, pin) for p in circuit.parts if isinstance(p, VSource)
            for pin in ("+", "-")}  # fmt: skip


def _chains(diodes: Sequence[Diode | Led], nets: Nets) -> list[tuple[list[str], set[str]]]:
    """Diodes joined in series (through nets that hold nothing but those two diodes'
    pins) → each chain's refs and its two end nets."""
    refs = {d.ref for d in diodes}
    inner = {
        net for net, pins in nets.members.items()
        if len(pins) == 2 and all(ref in refs for ref, _ in pins)
    }  # fmt: skip
    parent = {d.ref: d.ref for d in diodes}

    def find(r: str) -> str:
        while parent[r] != r:
            r = parent[r]
        return r

    for net in inner:
        (a, _), (b, _) = nets.members[net]
        parent[find(a)] = find(b)
    chains: dict[str, list[Diode | Led]] = defaultdict(list)
    for d in diodes:
        chains[find(d.ref)].append(d)
    out = []
    for chain in chains.values():
        ends = {nets.net_of(d.ref, pin) for d in chain for pin in ("A", "K")} - inner
        out.append(([d.ref for d in chain], ends))
    return out


def _reaches(circuit: Circuit, nets: Nets, end: str, inp: str) -> bool:
    """Whether a clipper's end is a device's input, or joined to it through one part in
    series and nothing else (the Big Muff's diodes reach the base through a 1 µF cap)."""
    if end == inp:
        return True
    others = {ref for ref, _ in nets.members[end]
              if not isinstance(circuit.part(ref), Diode | Led)}  # fmt: skip
    if len(others) != 1:
        return False
    part = circuit.part(next(iter(others)))
    pins = {nets.net_of(part.ref, pin) for pin in pin_offsets(part)}
    return pins == {end, inp}


def _clipper_role(
    circuit: Circuit, nets: Nets, ends: frozenset[str], order: Mapping[str, int]
) -> tuple[str, str]:
    """Where a clipper sits, and the net it's read at."""
    if GROUND in ends:
        return "to ground", next(iter(ends - {GROUND}))
    for p in circuit.parts:
        if isinstance(p, Opamp):
            out, inp = "out", "-"
        elif isinstance(p, Transistor):
            out, _, inp = _OUT_PINS[p.type]
        else:
            continue
        o, i = nets.net_of(p.ref, out), nets.net_of(p.ref, inp)
        if o in ends and _reaches(circuit, nets, next(iter(ends - {o}), o), i):
            return "in feedback", o
    reached = [n for n in ends if n in order]
    return "in series", max(reached, key=lambda n: order[n])


# ---- measures ------------------------------------------------------------------------


def rail_room(rails: Sequence[float], v: float, direction: int) -> float | None:
    """Distance from `v` to the nearest rail above (direction 1) or below (-1)."""
    beyond = [r for r in rails if (r - v) * direction >= 0]
    if not beyond:
        return None
    return abs((min(beyond) if direction > 0 else max(beyond)) - v)


def device_room(
    out: float,
    common: float,
    sat: float,
    polarity: str,
    follower: bool,
    rails: Sequence[float],
) -> tuple[float | None, float | None]:
    """A transistor stage's room to swing (up, down) at the terminal the signal leaves
    from (the drain/collector, or the source/emitter of a follower): the device bottoms
    out `sat` volts short of its common terminal one way, a rail limits the other.
    n-type: the device limits downward swings at the drain/collector, upward at the
    source/emitter of a follower; p-type mirrors that. Coarse on purpose (D-041)."""
    across = abs(out - common) - sat
    v = common if follower else out
    if (polarity == "n") != follower:
        return rail_room(rails, v, 1), across
    return across, rail_room(rails, v, -1)


def bias_position(up: float, down: float) -> tuple[float, str]:
    """Where a stage's output sits between its limits: 0 at the bottom, 1 at the top,
    and in words (centred, sits high, sits low)."""
    if math.isinf(up) or math.isinf(down):  # no rail beyond, one way or both
        position = 0.5 if math.isinf(up) and math.isinf(down) else float(math.isinf(down))
    else:
        total = up + down
        position = down / total if total > 0 else 0.5
    if abs(position - 0.5) <= CENTRED:
        return position, "centred"
    return position, "sits high" if position > 0.5 else "sits low"


def centring_rank(
    position: float, ratio: float, moved: int, aim: float = 0.5
) -> tuple[bool, int, float]:
    """How a change that moves a stage's bias to `position` ranks among the others, for
    a bias asked for at `aim` (the middle, unless Bias to… says): those that reach it
    first (within `CENTRED`), then those that push fewer other stages off centre
    (`moved`), then the smallest change (`ratio`: new value over old)."""
    return abs(position - aim) > CENTRED, moved, abs(math.log(ratio))


def headroom_db(up: float, down: float, peak: float) -> float | None:
    """Spare room for a sine of `peak` volts, in dB: positive is room left, negative is
    how much it's over (the side with less room limits a sine). None for no signal."""
    room = min(up, down)
    if peak <= 0:
        return None
    return 20 * math.log10(max(room, 1e-9) / peak)


def drive_db(predicted: float, actual: float) -> float:
    """How hard a clipper is driven: dB the level it would pass unclipped is over what
    gets through (0 when nothing is taken off)."""
    if predicted <= 0 or actual <= 0:
        return 0.0
    return max(0.0, 20 * math.log10(predicted / actual))


def harmonic_lead(harmonics_db: Mapping[int, float]) -> str:
    """Which harmonics lead: "even" (asymmetric clipping, 2nd, 4th…), "odd" (symmetric,
    3rd, 5th…) or "both"."""
    even = max(v for k, v in harmonics_db.items() if k % 2 == 0)
    odd = max(v for k, v in harmonics_db.items() if k % 2 == 1)
    if even > odd + LEADS_DB:
        return "even"
    if odd > even + LEADS_DB:
        return "odd"
    return "both"


@dataclass(frozen=True)
class Clips:
    """A row as the top line reads it: its label, what it is, the levels it clips at."""

    label: str
    what: str  # "clipper", or the stage's role
    levels: frozenset[str]


def stage_clips(headroom: float | None, held: bool) -> bool:
    """A stage clips when it's over its room, unless a clipper holds its output."""
    return headroom is not None and not held and headroom < 0


def clipper_clips(drive: float) -> bool:
    return drive >= CLIPPING_DB


def first_to_clip(rows: Sequence[Clips], levels: Sequence[str]) -> str:
    """The pane's top line: the first thing to clip as the pick gets harder (the lowest
    level where anything does, then the earliest in the signal)."""
    for level in levels:
        for row in rows:
            if level in row.levels:
                return f"Clips first: {row.label} ({row.what}), from a {LEVEL_NAMES[level]} pick."
    return "Nothing clips, even at a hard pick."
