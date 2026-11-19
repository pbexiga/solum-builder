"""Jacks whose cable matters, and what the plug in them does (D-354, D-355, D-364).

A jack is drawing only (D-174), but its contacts switch things on a real pedal, so
what's in it (`plug`: a mono plug, a stereo plug, none) means something there:
- `input`: its T is on the guitar's net (plugged into IN, D-353): no cable, no guitar;
- `output`: its T is on the amp's net: no cable, nothing reaches the amp;
- `ring`: a stereo jack with its ring and sleeve both wired: only a mono plug's long
  sleeve joins them (a stereo plug's ring is its own);
- `battery`: a `ring` whose ring takes the battery's − (D-185): without a mono plug the
  battery is cut off and, when it alone powers the circuit, the pedal is off.
A jack with none of these is a drawing and what's in it changes nothing.

The guitar input (IN) is an input jack too (D-364): always `input`, and its ring (a
stereo IN's, its sleeve being ground) a `ring` or `battery` as a jack's. A J drawn into
IN (`jacks_into`) takes over: IN's own plug steps aside, as if it weren't there. All of
this is per input part, so a second input (stereo's IN R) gets the same.
"""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, connect
from solum.circuit.schema import AmpInput, Battery, Circuit, Guitar, Jack, Plug

Role = Literal["input", "output", "ring", "battery"]
Socket = Jack | Guitar  # a part with a plug in it


@dataclass(frozen=True)
class CableOut:
    ref: str  # the jack
    roles: frozenset[Role]


def _inputs(circuit: Circuit) -> list[Guitar]:
    """The input parts (today IN alone; stereo's IN R would be one more)."""
    return [p for p in circuit.parts if isinstance(p, Guitar)]


def jacks_into(circuit: Circuit, nets: Nets, guitar: Guitar) -> list[Jack]:
    """The jacks drawn into an input part: their T on its net (D-353, D-364)."""
    net = nets.net_of(guitar.ref, "out")
    return [p for p in circuit.parts if isinstance(p, Jack) and nets.net_of(p.ref, "T") == net]


def _ring_roles(circuit: Circuit, nets: Nets, ring: str, sleeve: str | None) -> set[Role]:
    """A ring's roles: `ring` with it and the sleeve both wired (None: the guitar input's
    sleeve, ground inside it), `battery` too when it takes the battery's − (not ground)."""
    if len(nets.members[ring]) < 2 or (sleeve is not None and len(nets.members[sleeve]) < 2):
        return set()
    battery = next((p for p in circuit.parts if isinstance(p, Battery)), None)
    if battery is not None and ring == nets.net_of(battery.ref, "-") != GROUND:
        return {"ring", "battery"}
    return {"ring"}


def jack_roles(circuit: Circuit, nets: Nets) -> dict[str, frozenset[Role]]:
    """What each jack's cable switches (see the module's note), each input part's own
    included unless a J is drawn into it; jacks that switch nothing are left out."""
    inputs = _inputs(circuit)
    amp = next((p for p in circuit.parts if isinstance(p, AmpInput)), None)
    found: dict[str, frozenset[Role]] = {}
    for guitar in inputs:
        if not jacks_into(circuit, nets, guitar):
            roles: set[Role] = {"input"}
            if guitar.stereo:
                roles |= _ring_roles(circuit, nets, nets.net_of(guitar.ref, "ring"), None)
            found[guitar.ref] = frozenset(roles)
    tips = {nets.net_of(g.ref, "out") for g in inputs}
    for jack in (p for p in circuit.parts if isinstance(p, Jack)):
        tip = nets.net_of(jack.ref, "T")
        roles = set()
        if tip in tips:
            roles.add("input")
        if amp is not None and tip == nets.net_of(amp.ref, "in"):
            roles.add("output")
        if jack.stereo:
            sleeve = nets.net_of(jack.ref, "S")
            roles |= _ring_roles(circuit, nets, nets.net_of(jack.ref, "R"), sleeve)
        if roles:
            found[jack.ref] = frozenset(roles)
    return found


def ring_problem(circuit: Circuit) -> str | None:
    """Why the drawing is refused, or None (D-364): a J drawn into a stereo input part
    whose ring is wired would give the one jack two rings."""
    stereo = [g for g in _inputs(circuit) if g.stereo]
    if not stereo or not any(isinstance(p, Jack) for p in circuit.parts):
        return None  # the usual case, kept cheap (every parse asks)
    try:
        nets = connect(circuit)
    except ConnectivityError:
        return None  # said elsewhere
    for guitar in stereo:
        into = jacks_into(circuit, nets, guitar)
        if into and len(nets.members[nets.net_of(guitar.ref, "ring")]) > 1:
            j = into[0].ref
            return (
                f"{guitar.ref}'s ring is wired: move those wires to {j}'s R first, or unplug {j}."
            )
    return None


def switching_jacks(circuit: Circuit) -> dict[str, frozenset[Role]]:
    """`jack_roles` as drawn: what each jack's cable switches (Knobs gives those a cable
    switch); none while the wiring contradicts itself (two labels joined mid-edit, D-335)."""
    if not any(isinstance(p, Socket) for p in circuit.parts):
        return {}
    with suppress(ConnectivityError):
        return jack_roles(circuit, connect(circuit))
    return {}


def cable_key(jack: Socket) -> str:
    """Its cable switch's key in Knobs: the jack's ref, or `IN.plug` for the guitar input,
    whose ref is its volume knob's (D-364)."""
    return f"{jack.ref}.plug" if isinstance(jack, Guitar) else jack.ref


def plugs(jack: Socket) -> tuple[Plug, ...]:
    """What can go in it, for its Knobs switch: a stereo plug only in a stereo jack (in a
    mono one it's a mono plug)."""
    return ("mono", "stereo", "none") if jack.stereo else ("mono", "none")


PLUG_NAMES: dict[Plug, str] = {"mono": "Mono cable", "stereo": "Stereo cable", "none": "Cable out"}


def plug_names(jack: Socket) -> list[str]:
    """Its Knobs switch's positions, by `plugs`: a mono jack's cable is just in or out."""
    return [PLUG_NAMES[p] for p in plugs(jack)] if jack.stereo else ["Cable in", "Cable out"]


def _with(circuit: Circuit, fits: Callable[[Plug], bool]) -> list[CableOut]:
    """The jacks that switch something and have a plug that `fits` in them."""
    if not any(isinstance(p, Socket) and fits(p.plug) for p in circuit.parts):
        return []  # the usual case, without working out the nets
    roles = switching_jacks(circuit)
    return [
        CableOut(p.ref, roles[p.ref])
        for p in circuit.parts
        if isinstance(p, Socket) and fits(p.plug) and p.ref in roles
    ]


def cables_out(circuit: Circuit) -> list[CableOut]:
    """The jacks that switch something and have no cable in."""
    return _with(circuit, lambda plug: plug == "none")


def battery_cutter(circuit: Circuit) -> Socket | None:
    """The jack cutting the battery off: its ring takes the battery's − and there's no
    mono plug in it (no cable, or a stereo one). None when the battery isn't cut off."""
    cut = [c for c in _with(circuit, lambda plug: plug != "mono") if "battery" in c.roles]
    if not cut:
        return None
    jack = circuit.part(cut[0].ref)
    assert isinstance(jack, Socket)
    return jack


def battery_cut_off(circuit: Circuit) -> bool:
    """The battery's − goes to a jack's ring with no mono plug in it, so it's cut off."""
    return battery_cutter(circuit) is not None


def plug_said(jack: Socket) -> str:
    """What's in a jack that leaves its ring open, as a message says it."""
    return "has no cable in" if jack.plug == "none" else "has a stereo cable in"


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
    sentence per jack, saying too what else it cuts), or None. A render is refused with
    it; the curves and the scope still show a powered circuit (D-358)."""
    out = [c for c in cables_out(circuit) if c.roles & {"input", "output"}]
    return " ".join(_why(c) for c in out) if out else None
