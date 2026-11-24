"""Placement limits read from the circuit (D-367, D-400): parts that must sit by a pin.

A chip's supply decoupling cap, a charge pump's caps, an op-amp's feedback parts, a
regulator's input and output caps, a transistor's emitter (or source) bypass cap and the
parts on a high-gain stage's input work as drawn only when their leg is on the pin's own
strip, close, with nothing between (a long run of strip is an antenna and an inductor).
The editor shows a broken one as a warning, not a fault: the board is still the circuit.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from solum.circuit.connectivity import GROUND, Nets
from solum.circuit.parts import PIN_WORDS
from solum.circuit.schema import (
    POLARISED,
    Bjt,
    Capacitor,
    ChargePump,
    Circuit,
    Jfet,
    Opamp,
    PowerUnit,
    Regulator,
)
from solum.stripboard.board import Hole, Layout, hole_name, segments
from solum.stripboard.footprints import BoardPart
from solum.units import parse_value
from solum.words import listed

REACH = 2  # holes from the pin for one part; each more part on the same pin one more
WHY = {  # each limit's reason, as the warnings and Place next say it
    "decoupling": "its decoupling cap",
    "pump": "the charge pump's cap",
    "feedback": "a feedback part",
    "regulator": "the regulator's cap",
    "bypass": "its bypass cap",
    "input": "the high-gain stage's input",
}
BYPASSED = {"bjt": "E", "jfet": "S"}  # the pin a bypass cap sits by


class LoudInput(NamedTuple):
    """A high-gain stage's input pin (device ref, pin), as `probe.loud_inputs` finds it, and
    the nets AC-quiet beside it (a rail, Vref behind its cap: below 1 % of its signal). A
    part on the input whose other leg is on one (or on ground) biases it: not kept.
    `along`: the later nets in phase with it, kept off the strips beside it (P6i2)."""

    ref: str
    pin: str
    quiet: frozenset[str] = frozenset()
    along: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Limit:
    """`part`'s leg `leg` must sit by `anchor`'s leg `pin` (board refs and leg names)."""

    part: str
    leg: str
    anchor: str
    pin: str
    why: str  # decoupling, pump, feedback


def pin_said(anchor: str, pin: str) -> str:
    """A keeping pin in words: "Q1's emitter", "IC1's pin 7"."""
    return f"{anchor}'s {PIN_WORDS[pin]}" if pin in PIN_WORDS else f"{anchor}'s pin {pin}"


def _leg_of(board: dict[str, BoardPart]) -> dict[tuple[str, str], tuple[str, str]]:
    """A circuit pin → (board ref, leg)."""
    return {pin: (ref, leg) for ref, part in board.items() for leg, pin in part.pins.items()}


def _two_leg(board: dict[str, BoardPart]) -> list[BoardPart]:
    return [p for p in board.values() if p.footprint.shape in ("axial", "radial")]


def placement_limits(circuit: Circuit, nets: Nets, board: dict[str, BoardPart],
                     loud: Sequence[LoudInput] = ()) -> list[Limit]:  # fmt: skip
    """Every limit the circuit sets, in a stable order. `loud`: each high-gain stage's
    input pin as `probe.loud_inputs` finds them (it needs a run)."""
    leg_of = _leg_of(board)
    parts = {p.ref: p for p in circuit.parts}
    found: list[Limit] = []

    def near(part: BoardPart, net: str, anchor: tuple[str, str] | None, why: str) -> None:
        if anchor is None:
            return
        leg = next((lg for lg, pin in part.pins.items() if nets.net_of(*pin) == net), None)
        if leg is not None:
            found.append(Limit(part.ref, leg, anchor[0], anchor[1], why))

    caps = [p for p in _two_leg(board) if isinstance(parts.get(p.ref), Capacitor)]
    farads = {p.ref: parse_value(p.value) for p in circuit.parts if isinstance(p, Capacitor)}
    taken: set[str] = set()
    # decoupling: a non-polarised cap from a chip's supply pin to ground, one chip each
    for unit in circuit.parts:
        if not isinstance(unit, PowerUnit | Opamp) or (unit.ref, "V+") not in leg_of:
            continue
        for pin in ("V+", "V-"):
            net = nets.by_pin.get((unit.ref, pin))
            if net is None or net == GROUND:
                continue
            for cap in caps:
                ends = {nets.net_of(*p) for p in cap.pins.values()}
                kind = getattr(parts[cap.ref], "kind", None)
                if cap.ref not in taken and ends == {net, GROUND} and kind not in POLARISED:
                    near(cap, net, leg_of.get((unit.ref, pin)), "decoupling")
                    taken.add(cap.ref)
                    break
    # a charge pump's caps: on its flying pins, and from its output to ground
    for pump in circuit.parts:
        if not isinstance(pump, ChargePump):
            continue
        for pin in ("cap+", "cap-", "out"):
            net = nets.by_pin.get((pump.ref, pin))
            if net is None:
                continue
            for cap in caps:
                ends = {nets.net_of(*p) for p in cap.pins.values()}
                if net in ends and (pin != "out" or ends == {net, GROUND}):
                    near(cap, net, leg_of.get((pump.ref, pin)), "pump")
    # a regulator's caps: the smallest from its input to ground, and from its output
    for reg in circuit.parts:
        if not isinstance(reg, Regulator):
            continue
        for pin in ("in", "out"):
            net = nets.by_pin.get((reg.ref, pin))
            if net is None or net == GROUND:
                continue
            here = [c for c in caps if {nets.net_of(*p) for p in c.pins.values()} == {net, GROUND}]
            if here:
                cap = min(here, key=lambda c: (farads[c.ref], c.ref))
                near(cap, net, leg_of.get((reg.ref, pin)), "regulator")
    # a transistor's bypass cap: from its emitter (a JFET's source) to ground
    for device in circuit.parts:
        if not isinstance(device, Bjt | Jfet):
            continue
        pin = BYPASSED[device.type]
        net = nets.by_pin.get((device.ref, pin))
        if net is None or net == GROUND:
            continue
        for cap in caps:
            if {nets.net_of(*p) for p in cap.pins.values()} == {net, GROUND}:
                near(cap, net, leg_of.get((device.ref, pin)), "bypass")
    # a high-gain stage's input: every two-leg part in series with the signal on the net
    # it enters by (its other leg not on ground or an AC-quiet net), kept by the first such
    # pin on it (two inputs on one net can't both keep them)
    heard: set[str] = set()
    for ref, pin, quiet, _ in loud:
        net = nets.by_pin.get((ref, pin))
        if net is None or net == GROUND or net in heard:
            continue
        heard.add(net)
        for part in _two_leg(board):
            ends = {nets.net_of(*p) for p in part.pins.values()}
            if net in ends and not (ends - {net}) & (quiet | {GROUND}):
                near(part, net, leg_of.get((ref, pin)), "input")
    # an op-amp's feedback: parts from its output to its - input
    for amp in circuit.parts:
        if not isinstance(amp, Opamp) or (amp.ref, "-") not in leg_of:
            continue
        out, minus = nets.net_of(amp.ref, "out"), nets.net_of(amp.ref, "-")
        if out == minus:
            continue
        for part in board.values():  # a trimmer set as a variable resistor too
            if {nets.net_of(*p) for p in part.pins.values()} == {out, minus}:
                near(part, minus, leg_of[(amp.ref, "-")], "feedback")
    return found


def group_met(pin: Hole, legs: Sequence[Hole], foreign: Callable[[Hole], bool]) -> bool:
    """The one rule: every leg on the pin's strip, within `REACH` holes (one more for each
    other leg kept by the same pin), and no hole between them `foreign` (another net's
    leg, or a cut)."""
    reach = REACH + len(legs) - 1
    for leg in legs:
        if leg[1] != pin[1] or abs(leg[0] - pin[0]) > reach:
            return False
        step = 1 if leg[0] > pin[0] else -1
        if any(foreign((x, pin[1])) for x in range(pin[0] + step, leg[0], step)):
            return False
    return True


def limit_groups(limits: Sequence[Limit]) -> dict[tuple[str, str], list[Limit]]:
    """The limits by the pin that keeps them, in order."""
    groups: dict[tuple[str, str], list[Limit]] = {}
    for limit in limits:
        groups.setdefault((limit.anchor, limit.pin), []).append(limit)
    return groups


def broken_limits(layout: Layout, limits: Sequence[Limit],
                  turnable: frozenset[str] = frozenset()) -> list[tuple[str, str]]:  # fmt: skip
    """The pins (anchor, pin) whose limits `layout` breaks, all its parts placed. A part
    in `turnable` (two legs, either way round, as the check turns them) counts by its leg
    on the pin's strip, whichever it is."""
    holes = {(p.ref, leg): hole for p in layout.parts for leg, hole in p.legs}
    other = {(p.ref, a): b for p in layout.parts if p.ref in turnable and len(p.legs) == 2
             for (a, _), (_, b) in (p.legs, p.legs[::-1])}  # fmt: skip
    seg = segments(layout)
    found = []
    for key, group in limit_groups(limits).items():
        at = holes.get(key)
        here = seg.get(at) if at else None
        legs = []
        for g in group:
            leg = holes.get((g.part, g.leg))
            turned = other.get((g.part, g.leg))
            if turned is not None and here is not None and leg and seg.get(leg) != here:
                leg = turned if seg.get(turned) == here else leg
            legs.append(leg)
        if at is None or any(h is None for h in legs):
            continue

        def foreign(h: Hole, here: int | None = here) -> bool:
            # on one segment another net's leg would be a short, a fault of its own
            return seg.get(h) != here

        if not group_met(at, [h for h in legs if h is not None], foreign):
            found.append(key)
    return found


def _what_breaks(part: str, pin: Hole, leg: Hole, reach: int, cuts: frozenset[Hole]) -> str:
    """Why one leg breaks its limit, in a sentence: another strip, too far, a cut between."""
    if leg[1] != pin[1]:
        return f"{part}: it's on another strip."
    step = 1 if leg[0] > pin[0] else -1
    cut = next(((x, pin[1]) for x in range(pin[0] + step, leg[0], step) if (x, pin[1]) in cuts),
               None)  # fmt: skip
    away = abs(leg[0] - pin[0])
    said = [f"it's {away} holes away"] if away > reach else []
    if cut is not None:
        said.append(f"the cut at {hole_name(cut)} is between them")
    return f"{part}: {' and '.join(said)}." if said else ""


def limit_warnings(layout: Layout, limits: Sequence[Limit]) -> list[str]:
    """Each limit a layout breaks, a sentence each (a warning in the editor), saying what
    breaks it: another strip, too far, or a cut between."""
    holes = {(p.ref, leg): hole for p in layout.parts for leg, hole in p.legs}
    groups = limit_groups(limits)
    warnings = []
    for anchor, pin in broken_limits(layout, limits):
        group, at = groups[(anchor, pin)], holes[(anchor, pin)]
        refs = listed([g.part for g in group])
        reach = REACH + len(group) - 1
        why = [_what_breaks(g.part, at, holes[(g.part, g.leg)], reach, layout.cuts)
               for g in group]  # fmt: skip
        warnings.append(
            f"{refs} should sit by {pin_said(anchor, pin)} at {hole_name(at)} "
            f"({WHY[group[0].why]}): on its strip within {reach} holes, nothing between. "
            + " ".join(w for w in why if w)
        )
    return warnings
