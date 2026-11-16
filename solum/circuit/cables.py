"""Jacks whose cable matters, and what pulling it does (D-354).

A jack is drawing only (D-174), but three of its contacts switch something on a real
pedal, so its cable in / out toggle (`Jack.plugged`) means something there:
- `input`: its T is on the guitar's net (plugged into IN, D-353): no cable, no guitar;
- `output`: its T is on the amp's net: no cable, nothing reaches the amp;
- `battery`: a stereo jack whose ring takes the battery's − (D-185): no cable, the
  battery is cut off and, when it alone powers the circuit, the pedal is off.
A jack with none of these is a drawing and its cable changes nothing.
"""

from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, connect
from solum.circuit.schema import AmpInput, Battery, Circuit, Guitar, Jack

Role = Literal["input", "output", "battery"]


@dataclass(frozen=True)
class CableOut:
    ref: str  # the jack
    roles: frozenset[Role]


def jack_roles(circuit: Circuit, nets: Nets) -> dict[str, frozenset[Role]]:
    """What each jack's cable switches (see the module's note); jacks that switch nothing
    are left out."""
    guitar = next((p for p in circuit.parts if isinstance(p, Guitar)), None)
    amp = next((p for p in circuit.parts if isinstance(p, AmpInput)), None)
    battery = next((p for p in circuit.parts if isinstance(p, Battery)), None)
    found: dict[str, frozenset[Role]] = {}
    for jack in (p for p in circuit.parts if isinstance(p, Jack)):
        tip = nets.net_of(jack.ref, "T")
        roles: set[Role] = set()
        if guitar is not None and tip == nets.net_of(guitar.ref, "out"):
            roles.add("input")
        if amp is not None and tip == nets.net_of(amp.ref, "in"):
            roles.add("output")
        if battery is not None and jack.stereo:
            minus = nets.net_of(battery.ref, "-")
            if minus != GROUND and nets.net_of(jack.ref, "R") == minus:
                roles.add("battery")
        if roles:
            found[jack.ref] = frozenset(roles)
    return found


def switching_jacks(circuit: Circuit) -> dict[str, frozenset[Role]]:
    """`jack_roles` as drawn: what each jack's cable switches (Knobs gives those a cable
    switch); none while the wiring contradicts itself (two labels joined mid-edit, D-335)."""
    if not any(isinstance(p, Jack) for p in circuit.parts):
        return {}
    with suppress(ConnectivityError):
        return jack_roles(circuit, connect(circuit))
    return {}


def cables_out(circuit: Circuit) -> list[CableOut]:
    """The jacks whose cable is out and switches something."""
    if not any(isinstance(p, Jack) and not p.plugged for p in circuit.parts):
        return []  # the usual case, without working out the nets
    roles = switching_jacks(circuit)
    return [
        CableOut(p.ref, roles[p.ref])
        for p in circuit.parts
        if isinstance(p, Jack) and not p.plugged and p.ref in roles
    ]


def battery_cut_off(circuit: Circuit) -> bool:
    """A cable out cuts the battery off: its − goes to that jack's ring."""
    return any("battery" in c.roles for c in cables_out(circuit))


def _why(c: CableOut) -> str:
    parts = []
    if "input" in c.roles:
        parts.append("no guitar reaches the pedal")
    if "output" in c.roles:
        parts.append("nothing reaches the amp")
    if "battery" in c.roles:
        parts.append("its battery is cut off")
    said = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"{c.ref} has no cable in: {said}."


def silence(circuit: Circuit) -> str | None:
    """Why no signal can go through, with the input's or the output's cable out (one
    sentence per jack, saying too what else it cuts), or None. Curves, the scope and a
    render say this instead of showing a result. A cut-off battery alone isn't silence:
    the guitar still reaches the circuit, unpowered, and a true bypass still passes it,
    so that's simulated (`battery_cut_off`)."""
    out = [c for c in cables_out(circuit) if c.roles & {"input", "output"}]
    return " ".join(_why(c) for c in out) if out else None


def plays(circuit: Circuit) -> bool:
    """Whether a signal goes through: a guitar input and no cable out (`silence`). The
    curves, the scope, live curves and a render need it."""
    return any(isinstance(p, Guitar) for p in circuit.parts) and silence(circuit) is None
