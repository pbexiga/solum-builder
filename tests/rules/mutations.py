"""Scripted breakages of known-good circuits, for the mutation test (D-013, D-077).

Each mutation is a small, realistic mistake: a part left out, a pin not wired, a
polarised part fitted backwards, a chip's supply swapped. The test checks that some
rule notices each one; the ones nothing notices are rule gaps, and each must be
explained in `mutation_gaps.yaml`.

`python -m tests.rules.mutations` prints the whole report.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from solum.circuit.connectivity import ConnectivityError, connect
from solum.circuit.parts import pin_positions
from solum.circuit.schema import (
    CHIP_UNITS,
    Capacitor,
    Circuit,
    Diode,
    Led,
    Part,
    PowerUnit,
    Switch,
)

Rotation = int


@dataclass(frozen=True)
class Mutation:
    kind: str  # remove-part, lift-pin, reverse, swap-supply
    target: str  # "R3" or "Q1.B"
    circuit: Circuit

    @property
    def key(self) -> str:
        return f"{self.kind} {self.target}"


def _without(circuit: Circuit, refs: set[str]) -> Circuit:
    return circuit.model_copy(update={"parts": [p for p in circuit.parts if p.ref not in refs]})


def remove_part(circuit: Circuit) -> Iterator[Mutation]:
    """Each part left out; a dual's chip (its halves and power unit) and a multi-pole
    switch as a whole (D-140, D-143, D-179)."""
    chips: set[str] = set()
    for p in circuit.parts:
        if (isinstance(p, CHIP_UNITS) and p.half) or isinstance(p, PowerUnit):
            if p.chip not in chips:
                chips.add(p.chip)
                chip = {
                    q.ref
                    for q in circuit.parts
                    if ((isinstance(q, CHIP_UNITS) and q.half) or isinstance(q, PowerUnit))
                    and q.chip == p.chip
                }
                yield Mutation("remove-part", p.chip, _without(circuit, chip))
            continue
        if isinstance(p, Switch) and p.pole:  # a switch as a whole (D-143)
            if p.switch not in chips:
                chips.add(p.switch)
                poles = {
                    q.ref for q in circuit.parts if isinstance(q, Switch) and q.switch == p.switch
                }
                yield Mutation("remove-part", p.switch, _without(circuit, poles))
            continue
        yield Mutation("remove-part", p.ref, _without(circuit, {p.ref}))


def _alone(circuit: Circuit, ref: str, pin: str) -> bool:
    try:
        nets = connect(circuit)
    except ConnectivityError:
        return False
    return len(nets.members[nets.net_of(ref, pin)]) == 1


def lift_pin(circuit: Circuit) -> Iterator[Mutation]:
    """A pin left unwired: the wires ending on it and labels on it go. Skipped when the
    pin still connects (another pin touches it, or a wire runs through it)."""
    for p in circuit.parts:
        for pin, at in pin_positions(p).items():
            if _alone(circuit, p.ref, pin):
                continue  # already open (a spare pin)
            wires = [w for w in circuit.wires if at not in (w.from_, w.to)]
            labels = [lb for lb in circuit.labels if lb.pos != at]
            mutated = circuit.model_copy(update={"wires": wires, "labels": labels})
            if _alone(mutated, p.ref, pin):
                yield Mutation("lift-pin", f"{p.ref}.{pin}", mutated)


def _turned(part: Part) -> Part:
    return part.model_copy(update={"rot": (part.rot + 180) % 360})


def reverse(circuit: Circuit) -> Iterator[Mutation]:
    """Diodes and polarised capacitors turned round (their two pins swap places)."""
    for p in circuit.parts:
        polarised = isinstance(p, Capacitor) and p.kind in ("electrolytic", "tantalum")
        if isinstance(p, Diode | Led) or polarised:
            parts = [_turned(q) if q.ref == p.ref else q for q in circuit.parts]
            yield Mutation("reverse", p.ref, circuit.model_copy(update={"parts": parts}))


def swap_supply(circuit: Circuit) -> Iterator[Mutation]:
    """A chip's power labels swapped: V+'s on its V- pin and the other way, on a single
    or a chip's power unit (D-140, D-179)."""
    for p in circuit.parts:
        if not (isinstance(p, PowerUnit) or (isinstance(p, CHIP_UNITS) and p.half is None)):
            continue
        pins = pin_positions(p)
        pos = next((lb for lb in circuit.labels if lb.pos == pins["V+"]), None)
        neg = next((lb for lb in circuit.labels if lb.pos == pins["V-"]), None)
        if pos is None or neg is None:
            continue  # wired, not labelled
        swapped = {id(pos): neg.net, id(neg): pos.net}
        labels = [
            lb.model_copy(update={"net": swapped[id(lb)]}) if id(lb) in swapped else lb
            for lb in circuit.labels
        ]
        yield Mutation("swap-supply", p.ref, circuit.model_copy(update={"labels": labels}))


OPERATORS = (remove_part, lift_pin, reverse, swap_supply)


def mutations(circuit: Circuit) -> Iterator[Mutation]:
    for operator in OPERATORS:
        yield from operator(circuit)


if __name__ == "__main__":
    from tests.rules.test_mutations import report

    for line in report():
        print(line)
