"""Bias solver: turn each trimmer with a `bias_target` until its node sits at the target.

Bisection over the trimmer's rotation, one `.op` per step (cached, ~1 ms each). Assumes
the node voltage moves one way as the trimmer turns, which holds for a trimmer setting a
drain or collector load.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from solum.circuit.connectivity import connect
from solum.circuit.schema import Circuit, Trimmer
from solum.units import format_value

TOLERANCE = 1e-3  # volts
MAX_STEPS = 60
MAX_PASSES = 4  # several trimmers can interact; repeat until all hold

OpFunction = Callable[[Circuit], Mapping[str, float]]  # circuit → node voltages by net


class BiasError(ValueError):
    """A bias target can't be reached (plain-English message)."""


@dataclass(frozen=True)
class BiasResult:
    circuit: Circuit  # with each targeted trimmer's rotation set
    rotations: dict[str, float]  # trimmer ref → solved rotation
    volts: dict[str, float]  # trimmer ref → its node's voltage at that rotation


def bias_trimmers(circuit: Circuit) -> list[Trimmer]:
    return [p for p in circuit.parts if isinstance(p, Trimmer) and p.bias_target is not None]


def solve_bias(circuit: Circuit, op: OpFunction) -> BiasResult:
    """Solve every targeted trimmer. Returns the circuit unchanged if there are none."""
    nets = connect(circuit)
    rotations: dict[str, float] = {}
    volts: dict[str, float] = {}
    for _ in range(MAX_PASSES):
        settled = True
        for trimmer in bias_trimmers(circuit):
            target = trimmer.bias_target
            assert target is not None
            node = nets.resolve(target.node)
            now = op(circuit)[node]
            if abs(now - target.volts) <= TOLERANCE:
                rotations[trimmer.ref], volts[trimmer.ref] = trimmer.rotation, now
                continue
            settled = False
            rotation, reached = _bisect(circuit, trimmer.ref, node, target.volts, op)
            circuit = circuit.with_part(trimmer.ref, rotation=rotation)
            rotations[trimmer.ref], volts[trimmer.ref] = rotation, reached
        if settled:
            break
    return BiasResult(circuit, rotations, volts)


def bisect(
    at: Callable[[float], float],
    lo: float,
    hi: float,
    target: float,
    tolerance: float,
    v_lo: float | None = None,
    v_hi: float | None = None,
) -> tuple[float, float] | None:
    """The x in [lo, hi] where a function that moves one way reaches `target` (within
    `tolerance`), and its value there; None when `target` is outside what the ends reach.
    Pass the ends' values if they're already known."""
    v_lo = at(lo) if v_lo is None else v_lo
    v_hi = at(hi) if v_hi is None else v_hi
    if not min(v_lo, v_hi) - tolerance <= target <= max(v_lo, v_hi) + tolerance:
        return None
    rising = v_hi > v_lo
    mid, v_mid = lo, v_lo
    for _ in range(MAX_STEPS):
        mid = (lo + hi) / 2
        v_mid = at(mid)
        if abs(v_mid - target) <= tolerance:
            break
        if (v_mid < target) == rising:
            lo = mid
        else:
            hi = mid
    return mid, v_mid


@dataclass(frozen=True)
class Reach:
    """How far a targeted trimmer moves its node, turned end to end (the others as they
    are): what a target can be (D-127)."""

    ref: str
    value: str  # the trimmer's, as written ("25k")
    node: str  # as its target names it ("Q1.D")
    low: float
    high: float
    target: float  # its target's volts

    @property
    def text(self) -> str:
        """ "With RT1 (25k), Q1.D can go from 2.10 V to 8.70 V." """
        return (
            f"With {self.ref} ({self.value}), {self.node} can go from {self.low:.2f} V "
            f"to {self.high:.2f} V."
        )

    def holds(self, volts: float) -> bool:
        return self.low - TOLERANCE <= volts <= self.high + TOLERANCE

    @property
    def reached(self) -> bool:
        """Whether its target is within reach."""
        return self.holds(self.target)


def target_reach(circuit: Circuit, ref: str, op: OpFunction) -> Reach:
    """The volts trimmer `ref` can hold its target's node at (it must have a target)."""
    trimmer = next((p for p in circuit.parts if p.ref == ref), None)
    if not isinstance(trimmer, Trimmer) or trimmer.bias_target is None:
        raise BiasError(f"{ref} isn't a trimmer with a bias target.")
    node = connect(circuit).resolve(trimmer.bias_target.node)
    v_lo, v_hi = (op(circuit.with_part(ref, rotation=r))[node] for r in (0.0, 1.0))
    value = trimmer.value if isinstance(trimmer.value, str) else format_value(trimmer.value)
    target = trimmer.bias_target
    return Reach(ref, value, target.node, min(v_lo, v_hi), max(v_lo, v_hi), target.volts)


def _bisect(
    circuit: Circuit, ref: str, node: str, target: float, op: OpFunction
) -> tuple[float, float]:
    def at(rotation: float) -> float:
        return op(circuit.with_part(ref, rotation=rotation))[node]

    v_lo, v_hi = at(0.0), at(1.0)
    found = bisect(at, 0.0, 1.0, target, TOLERANCE, v_lo, v_hi)
    if found is None:
        raise BiasError(
            f"{ref} can't set {node} to {target:g} V: turning it end to end only moves "
            f"{node} between {min(v_lo, v_hi):.2f} V and {max(v_lo, v_hi):.2f} V. Change "
            f"{ref}'s value or the resistor in series with it."
        )
    return found
