"""Jacks whose cable matters, and what the plug in them does (D-354, D-355).

A jack is drawing only (D-174), but its contacts switch things on a real pedal, so
what's in it (`Jack.plug`: a mono plug, a stereo plug, none) means something there:
- `input`: its T is on the guitar's net (plugged into IN, D-353): no cable, no guitar;
- `output`: its T is on the amp's net: no cable, nothing reaches the amp;
- `ring`: a stereo jack with its ring and sleeve both wired: only a mono plug's long
  sleeve joins them (a stereo plug's ring is its own);
- `battery`: a `ring` whose ring takes the battery's − (D-185): without a mono plug the
  battery is cut off and, when it alone powers the circuit, the pedal is off.
A jack with none of these is a drawing and what's in it changes nothing.
"""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, connect
from solum.circuit.schema import AmpInput, Battery, Circuit, Guitar, Jack, Plug

Role = Literal["input", "output", "ring", "battery"]


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
        ring = nets.net_of(jack.ref, "R") if jack.stereo else None
        sleeve = nets.net_of(jack.ref, "S")
        if ring is not None and len(nets.members[ring]) > 1 and len(nets.members[sleeve]) > 1:
            roles.add("ring")
            if battery is not None and ring == nets.net_of(battery.ref, "-") != GROUND:
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


def plugs(jack: Jack) -> tuple[Plug, ...]:
    """What can go in it, for its Knobs switch: a stereo plug only in a stereo jack (in a
    mono one it's a mono plug)."""
    return ("mono", "stereo", "none") if jack.stereo else ("mono", "none")


PLUG_NAMES: dict[Plug, str] = {"mono": "Mono cable", "stereo": "Stereo cable", "none": "Cable out"}


def plug_names(jack: Jack) -> list[str]:
    """Its Knobs switch's positions, by `plugs`: a mono jack's cable is just in or out."""
    return [PLUG_NAMES[p] for p in plugs(jack)] if jack.stereo else ["Cable in", "Cable out"]


def _with(circuit: Circuit, fits: Callable[[Plug], bool]) -> list[CableOut]:
    """The jacks that switch something and have a plug that `fits` in them."""
    if not any(isinstance(p, Jack) and fits(p.plug) for p in circuit.parts):
        return []  # the usual case, without working out the nets
    roles = switching_jacks(circuit)
    return [
        CableOut(p.ref, roles[p.ref])
        for p in circuit.parts
        if isinstance(p, Jack) and fits(p.plug) and p.ref in roles
    ]


def cables_out(circuit: Circuit) -> list[CableOut]:
    """The jacks that switch something and have no cable in."""
    return _with(circuit, lambda plug: plug == "none")


def battery_cut_off(circuit: Circuit) -> bool:
    """The battery's − goes to a jack's ring with no mono plug in it (no cable, or a stereo
    one), so it's cut off."""
    return any("battery" in c.roles for c in _with(circuit, lambda plug: plug != "mono"))


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
