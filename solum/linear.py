"""A circuit as a linear small-signal system: what the in-browser solver (`web/solver.js`,
D-012) solves while a value slider or knob moves.

Passive elements (R, C, L, sources) come straight from the AC netlist (`solum.netlist`,
the one owner of circuit → elements). Every semiconductor, primitive or subcircuit, is an
N-port admittance measured by ngspice at the circuit's own operating point
(`Simulator.linearise`, D-079), so the system is exactly what ngspice's `.ac` solves,
whatever the model card. Pure functions only: no simulator here.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from solum.netlist import Element, Sensed

GROUND = "0"
Complex = npt.NDArray[np.complex128]


class LinearError(ValueError):
    """The circuit can't be made into a linear system (plain-English message)."""


@dataclass(frozen=True)
class Ports:
    """One semiconductor as an N-port: the SPICE nodes it touches (ground and nodes an
    ideal source holds at 0 V AC left out) and its admittance `y[f, i, j]`, the current
    into port i per volt at port j."""

    nodes: tuple[str, ...]
    y: Complex  # (frequency, port, port)


@dataclass(frozen=True)
class Branch:
    """One linear element. `kind` R, C, L (two nodes, `value` in Ω, F, H), V (+, -;
    `value` is the AC magnitude, 0 for DC sources and the semiconductor sense sources'
    shorts), Y (a semiconductor's ports, `y` per frequency)."""

    kind: str
    name: str
    nodes: tuple[str, ...]
    value: float = 0.0
    y: Complex | None = None


def ac_magnitude(tokens: Sequence[str]) -> float:
    """The AC magnitude of a source line's tokens after the nodes (`DC 0 AC 1` → 1.0)."""
    words = " ".join(tokens).split()
    upper = [w.upper() for w in words]
    return float(words[upper.index("AC") + 1]) if "AC" in upper else 0.0


def held_nodes(elements: Iterable[Element]) -> frozenset[str]:
    """Nodes an ideal voltage source with no AC part ties to ground (rails, a DC source
    part, the guitar while it's quiet): always 0 V in a small-signal analysis. Follows
    chains of such sources."""
    links = [
        (e.tokens[1], e.tokens[2])
        for e in elements
        if e.tokens[0][0].upper() == "V" and ac_magnitude(e.tokens[3:]) == 0.0
    ]
    held, grew = {GROUND}, True
    while grew:
        grew = False
        for a, b in links:
            if (a in held) != (b in held):
                held |= {a, b}
                grew = True
    return frozenset(held)


def port_nodes(sensed: Iterable[Sensed], held: frozenset[str]) -> tuple[str, ...]:
    """A semiconductor's ports: the distinct nodes its pins are on, minus held ones."""
    return tuple(dict.fromkeys(s.node for s in sensed if s.node not in held))


def port_admittance(volts: Complex, currents: Complex) -> Complex:
    """The admittance Y with I = Y·V, from K measurements: `volts` and `currents` are
    (frequency, port, K) with K ≥ ports, linearly independent. Least squares, which is
    exact for consistent data."""
    if volts.shape != currents.shape or volts.shape[2] < volts.shape[1]:
        raise LinearError("Not enough measurements to find a device's admittance.")
    y: Complex = currents @ np.linalg.pinv(volts)
    return y


def branches(elements: Iterable[Element], ports: Mapping[str, Ports]) -> list[Branch]:
    """The linear system: every passive element of an AC netlist, and each semiconductor
    in `ports` (by ref) in place of its device line and sense sources."""
    out: list[Branch] = []
    for e in elements:
        name, letter = e.tokens[0], e.tokens[0][0].upper()
        if e.ref in ports:
            continue  # the device itself, or one of its sense sources
        if letter in "RCL":
            out.append(Branch(letter, name, (e.tokens[1], e.tokens[2]), float(e.tokens[3])))
        elif letter == "V":
            out.append(Branch("V", name, (e.tokens[1], e.tokens[2]), ac_magnitude(e.tokens[3:])))
        else:
            what = e.ref or name
            raise LinearError(f"{what} isn't measured, so it can't be part of a linear system.")
    for ref, p in sorted(ports.items()):
        if p.nodes:
            out.append(Branch("Y", ref, p.nodes, y=p.y))
    return out


def element_values(elements: Iterable[Element]) -> dict[str, float]:
    """Name → value of the passive elements (R, C, L) among `elements`: what a slider's
    step changes (`solum.live`)."""
    return {e.tokens[0]: float(e.tokens[3]) for e in elements if e.tokens[0][0].upper() in "RCL"}


def system_data(found: Sequence[Branch], freq: Sequence[float], output: str) -> dict[str, Any]:
    """The JSON the browser solver takes: frequencies, node names (ground left out, index
    -1), elements with node indices (a Y element's admittance as `re`/`im`, one flat
    row-major port x port list per frequency) and the output node's index."""
    nodes = sorted({n for b in found for n in b.nodes if n != GROUND})
    index = {n: i for i, n in enumerate(nodes)} | {GROUND: -1}
    if output not in index:
        raise LinearError(f"The output node {output!r} isn't in the circuit.")
    elements = []
    for b in found:
        item: dict[str, Any] = {"k": b.kind, "name": b.name, "n": [index[n] for n in b.nodes]}
        if b.y is None:
            item["v"] = b.value
        else:
            flat = b.y.reshape(len(b.y), -1)
            item["re"] = flat.real.tolist()
            item["im"] = flat.imag.tolist()
        elements.append(item)
    return {"freq": list(freq), "nodes": nodes, "elements": elements, "out": index[output]}
