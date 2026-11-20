"""Placement limits read from the circuit (D-367): parts that must sit by a chip's pin.

A chip's supply decoupling cap, a charge pump's caps and an op-amp's feedback parts work
as drawn only when their leg is on the pin's own strip, close, with nothing between (a
long run of strip is an antenna and an inductor). The editor shows a broken one as a
warning, not a fault: the board is still the circuit.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from solum.circuit.connectivity import GROUND, Nets
from solum.circuit.schema import POLARISED, Capacitor, ChargePump, Circuit, Opamp, PowerUnit
from solum.stripboard.board import Hole, Layout, hole_name, segments
from solum.stripboard.footprints import BoardPart

REACH = 2  # holes from the pin for one part; each more part on the same pin one more
_WHY = {
    "decoupling": "its decoupling cap",
    "pump": "the charge pump's cap",
    "feedback": "a feedback part",
}


@dataclass(frozen=True)
class Limit:
    """`part`'s leg `leg` must sit by `anchor`'s leg `pin` (board refs and leg names)."""

    part: str
    leg: str
    anchor: str
    pin: str
    why: str  # decoupling, pump, feedback


def _leg_of(board: dict[str, BoardPart]) -> dict[tuple[str, str], tuple[str, str]]:
    """A circuit pin → (board ref, leg)."""
    return {pin: (ref, leg) for ref, part in board.items() for leg, pin in part.pins.items()}


def _two_leg(board: dict[str, BoardPart]) -> list[BoardPart]:
    return [p for p in board.values() if p.footprint.shape in ("axial", "radial")]


def placement_limits(circuit: Circuit, nets: Nets, board: dict[str, BoardPart]) -> list[Limit]:
    """Every limit the circuit sets, in a stable order."""
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
    # an op-amp's feedback: parts from its output to its - input
    for amp in circuit.parts:
        if not isinstance(amp, Opamp) or (amp.ref, "-") not in leg_of:
            continue
        out, minus = nets.net_of(amp.ref, "out"), nets.net_of(amp.ref, "-")
        if out == minus:
            continue
        for part in _two_leg(board):
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


def limit_warnings(layout: Layout, limits: Sequence[Limit]) -> list[str]:
    """Each limit a layout breaks, a sentence each (a warning in the editor)."""
    holes = {(p.ref, leg): hole for p in layout.parts for leg, hole in p.legs}
    seg = segments(layout)
    warnings = []
    for (anchor, pin), group in limit_groups(limits).items():
        at = holes.get((anchor, pin))
        legs = [holes.get((g.part, g.leg)) for g in group]
        if at is None or any(h is None for h in legs):
            continue
        kept = [h for h in legs if h is not None]
        here = seg.get(at)

        def foreign(h: Hole, here: int | None = here) -> bool:
            # on one segment another net's leg would be a short, a fault of its own
            return seg.get(h) != here

        if group_met(at, kept, foreign):
            continue
        refs = " and ".join(g.part for g in group)
        reach = REACH + len(group) - 1
        warnings.append(
            f"{refs} should sit by {anchor}'s pin {pin} at {hole_name(at)} "
            f"({_WHY[group[0].why]}): on its strip within {reach} holes, nothing between."
        )
    return warnings
