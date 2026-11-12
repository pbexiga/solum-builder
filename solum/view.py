"""What the viewer draws: parts with their pin positions and nets, labels, wires, net
anchors, probes and the knob controls. Geometry comes from `solum.circuit.parts` and nets
from `solum.circuit.connectivity`, so the browser never re-derives either.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from solum.circuit.chips import supply_nets, unused_halves
from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, connect, on_segment
from solum.circuit.io import circuit_to_dict
from solum.circuit.parts import COMP_PINS, pin_positions
from solum.circuit.pump import pump_wiring
from solum.circuit.schema import (
    CHIP_UNITS,
    POLARISED,
    AmpInput,
    Battery,
    Bjt,
    Capacitor,
    ChargePump,
    Circuit,
    DcJack,
    Diode,
    Guitar,
    Inverter,
    Jack,
    Jfet,
    Label,
    Mosfet,
    Opamp,
    Ota,
    Part,
    Point,
    Pot,
    PowerUnit,
    Regulator,
    Switch,
    VSource,
)
from solum.circuit.supply import battery_wiring, power_chip
from solum.circuit.switches import POLE_LETTERS, contacts_text, lug_name
from solum.models import ModelError, ModelLibrary
from solum.netlist import input_part
from solum.units import format_value, parse_value


@dataclass(frozen=True)
class ProbeNets:
    """The nets every view compares against: the guitar input and the pedal output."""

    input: str | None
    output: str | None


def probe_nets(circuit: Circuit, nets: Nets) -> ProbeNets:
    """`probes.in` / `probes.out` if set, else the guitar's and the amp's nets."""

    def pick(name: str | None, fallback: tuple[str, str] | None) -> str | None:
        if name:
            try:
                return nets.resolve(name)
            except ConnectivityError:
                pass
        return nets.net_of(*fallback) if fallback else None

    guitar = input_part(circuit)
    amp = next((p for p in circuit.parts if isinstance(p, AmpInput)), None)
    return ProbeNets(
        input=pick(circuit.probes.in_, (guitar.ref, "out") if guitar else None),
        output=pick(circuit.probes.out, (amp.ref, "in") if amp else None),
    )


def rail_nets(circuit: Circuit, nets: Nets) -> set[str]:
    """Supply nets: the power rails, every chip's supply nets (its V+ and V- pins'),
    each charge pump's outputs (D-093) and its own nets (CAP+, CAP-, a doubler's diode
    junction: D-226), each regulator's input and output (D-227), and GND."""
    rails = {*circuit.power.rails, GROUND}
    for p in circuit.parts:
        if isinstance(p, CHIP_UNITS):
            rails |= set(supply_nets(circuit, nets, p))
        elif isinstance(p, ChargePump):  # its outputs, and the nets inside it (no signal)
            wiring = pump_wiring(circuit, nets, p)
            rails |= {*wiring.driven, nets.net_of(p.ref, "cap+"), nets.net_of(p.ref, "cap-")}
        elif isinstance(p, Regulator):  # what it takes and what it makes (D-227)
            rails |= {nets.net_of(p.ref, "in"), nets.net_of(p.ref, "out")}
    return rails


def part_text(part: Part, pickups: Mapping[str, str] | None = None) -> str:
    """The value line drawn under a part's ref: `4k7`, `500k A`, `2N5089`. A guitar's is
    what it simulates (D-137): the pickup's name from the guide (`pickups`: kind → name),
    "Your pickup" for values of your own, or "Buffered"."""
    match part:
        case Pot():
            return f"{part.value} {part.taper}"
        case Switch():  # a multi-pole switch's type once, under its last pole (D-143)
            switch = part.switch_kind
            last = part.pole is None or part.pole == POLE_LETTERS[switch.poles - 1].lower()
            return switch.short if last else ""
        case VSource():
            return f"{format_value(parse_value(part.value))} V"
        case Battery():
            state = f" {part.state}" if part.state else ""
            return f"{parse_value(part.volts):g} V{state}"
        case DcJack():
            return "plugged in" if part.plugged else "unplugged"
        case Jack():
            return part.label or ("stereo" if part.stereo else "mono")
        case Guitar():
            if part.source != "pickup" or part.pickup is None:
                return "Buffered"
            kind = part.pickup.kind
            return (pickups or {}).get(kind, "pickup") if kind else "Your pickup"
        case AmpInput():
            return f"amp {part.value}"
    model = getattr(part, "model", None)
    if model is not None:
        return str(model)
    value = getattr(part, "value", None)
    if value is None:
        return ""
    return value if isinstance(value, str) else format_value(value)


def drawn_pins(
    circuit: Circuit, nets: Nets, part: Part, models: ModelLibrary | None = None
) -> dict[str, tuple[Point, str]]:
    """Pin name → (position, net) for the pins that are drawn and probed: all of them,
    except op-amp compensation pins that connect to nothing on a model without them (most
    have none; with `models`, an LM308's are drawn, D-140)."""
    labelled = {lb.net for lb in circuit.labels}
    pins = {}
    for name, pos in pin_positions(part).items():
        net = nets.net_of(part.ref, name)
        wired = len(nets.members[net]) > 1 or net in labelled
        if name in COMP_PINS and not wired and name not in _model_pins(part, models):
            continue
        pins[name] = (pos, net)
    return pins


def controls(circuit: Circuit) -> list[dict[str, Any]]:
    """One knob per pot (a dual pot's gangs share it, D-217) and one selector per switch,
    in file order (SPEC §1); the guitar's volume is a pot like the others (D-096)."""
    found: list[dict[str, Any]] = []
    for p in circuit.parts:
        if isinstance(p, Guitar) and p.has_volume:
            found.append(
                {"ref": p.ref, "kind": "pot", "label": "Guitar volume", "value": p.volume,
                 "taper": p.taper, "rotation": p.rotation}
            )  # fmt: skip
        elif isinstance(p, Pot) and p.gang in (None, "a"):  # one per dual pot (D-217)
            knob: dict[str, Any] = {
                "ref": p.knob, "kind": "pot", "label": p.label or p.knob, "value": p.value,
                "taper": p.taper, "rotation": p.rotation,
            }  # fmt: skip
            if p.gang:
                knob["refs"] = circuit.units(p.knob)
            found.append(knob)
        elif isinstance(p, Switch) and p.pole in (None, "a"):  # one per switch (D-143)
            poles = [q.ref for q in circuit.parts if isinstance(q, Switch) and q.switch == p.switch]
            kind = p.switch_kind
            found.append(
                {"ref": p.switch, "kind": "switch", "label": p.label or p.switch,
                 "refs": poles, "position": p.position, "positions": p.position_names,
                 "contacts": [f"{name}: {contacts_text(kind, i)}"
                              for i, name in enumerate(kind.positions)]}
            )  # fmt: skip
        elif isinstance(p, DcJack) and any(isinstance(q, Battery) for q in circuit.parts):
            found.append(  # the jack's plug picks the supply (D-143): a switch, in effect
                {"ref": p.ref, "kind": "switch", "label": "Power", "refs": [p.ref],
                 "position": 0 if p.plugged else 1, "positions": ["DC jack", "Battery"],
                 "plug": True}
            )  # fmt: skip
        elif (
            isinstance(p, Jack) and p.stereo and any(isinstance(q, Battery) for q in circuit.parts)
        ):
            found.append(  # a stereo jack's cable switches a battery on its ring (D-185)
                {"ref": p.ref, "kind": "switch", "label": f"{p.label or p.ref} cable",
                 "refs": [p.ref], "position": 0 if p.plugged else 1,
                 "positions": ["Cable in", "Cable out"], "plug": True}
            )  # fmt: skip
    return found


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def _wire_ways(circuit: Circuit, at: Point) -> set[Point]:
    """The directions wires leave point `at` in (both ways for one passing through)."""
    ways: set[Point] = set()
    for w in circuit.wires:
        ends = (w.from_, w.to)
        if at in ends:
            far = w.to if at == w.from_ else w.from_
            ways.add((_sign(far[0] - at[0]), _sign(far[1] - at[1])))
        elif on_segment(at, w.from_, w.to):
            d = (_sign(w.to[0] - w.from_[0]), _sign(w.to[1] - w.from_[1]))
            ways |= {d, (-d[0], -d[1])}
    return ways


SIDES: tuple[Point, ...] = ((0, -1), (0, 1), (1, 0), (-1, 0))
"""Where a label off a pin puts its text, in order of preference: above, below, right, left."""


def _label_view(lb: Label, side: Point) -> dict[str, Any]:
    """A label as the canvas draws it."""
    return {"net": lb.net, "pos": list(lb.pos), "side": list(side), "rot": lb.rot}


def label_sides(circuit: Circuit) -> list[Point]:
    """For each label, the unit direction its text goes: away from the part whose pin it
    sits on (clear of the symbol); off a pin, the first of `SIDES` no wire leaves the
    label by, so the text doesn't sit on a wire (D-114)."""
    away: dict[Point, Point] = {}
    for p in circuit.parts:
        for pos in pin_positions(p).values():
            dx, dy = pos[0] - p.pos[0], pos[1] - p.pos[1]
            away.setdefault(pos, (_sign(dx), 0) if abs(dx) >= abs(dy) else (0, _sign(dy)))

    def free(at: Point) -> Point:
        ways = _wire_ways(circuit, at)
        return next((s for s in SIDES if s not in ways), SIDES[0])

    return [away.get(lb.pos) or free(lb.pos) for lb in circuit.labels]


def junctions(circuit: Circuit) -> list[Point]:
    """Points where three or more wire ends, pins or passing wires meet (drawn as dots)."""
    pins = [pos for p in circuit.parts for pos in pin_positions(p).values()]
    ends = [pt for w in circuit.wires for pt in (w.from_, w.to)]
    found = []
    for pt in sorted(set(ends)):
        through = sum(
            1 for w in circuit.wires if pt not in (w.from_, w.to) and on_segment(pt, w.from_, w.to)
        )
        if ends.count(pt) + pins.count(pt) + 2 * through >= 3:
            found.append(pt)
    return found


def wire_nets(circuit: Circuit, nets: Nets) -> list[str | None]:
    """The net each wire belongs to (None for a wire that touches nothing)."""
    known: dict[Point, str] = {lb.pos: lb.net for lb in circuit.labels}
    for p in circuit.parts:
        for name, pos in pin_positions(p).items():
            known[pos] = nets.net_of(p.ref, name)
    result: list[str | None] = [None] * len(circuit.wires)
    changed = True
    while changed:  # spread nets along chains of wires
        changed = False
        for i, w in enumerate(circuit.wires):
            if result[i] is not None:
                continue
            hit = next((n for pt, n in known.items() if on_segment(pt, w.from_, w.to)), None)
            if hit is not None:
                result[i] = hit
                known[w.from_] = known[w.to] = hit
                changed = True
    return result


def _model_pins(part: Part, models: ModelLibrary | None) -> set[str]:
    """The pins a part's model simulates (an op-amp subcircuit's), if known."""
    model = getattr(part, "model", None)
    if models is None or model is None or model not in models:
        return set()
    return set(models.get(model).info.pins)


def _pin_number(part: Part, pin: str, models: ModelLibrary | None) -> int | None:
    """A chip unit's pin's datasheet number (D-140, D-180), a power unit's (D-179) or a
    regulator's (D-227), when its model's record has them."""
    chips = (*CHIP_UNITS, PowerUnit, Regulator)
    if not isinstance(part, chips) or models is None or part.model not in models:
        return None
    half = part.half if isinstance(part, CHIP_UNITS) else None
    return models.get(part.model).pin_number(pin, half)


def switch_draw(part: Switch) -> dict[str, Any]:
    """A pole's symbol (D-143): its lugs (the common first), at each position the lug its
    common joins (None: open), and its look (a toggle's column, a rotary's arc, 9c)."""
    kind = part.switch_kind
    index = POLE_LETTERS.index(part.pole.upper()) if part.pole else 0
    return {
        "kind": part.kind, "pole": part.pole, "look": kind.look,
        "names": part.position_names if part.names else None, "position": part.position,
        "lugs": [lug_name(kind, part.pole, lug) for lug in kind.lugs],
        "closed": [None if (lug := c[index]) is None else lug_name(kind, part.pole, lug)
                   for c in kind.closed],
    }  # fmt: skip


def _draw_fields(part: Part) -> dict[str, Any]:
    """What a symbol needs beyond its type: a capacitor's kind, a switch's poles/throws,
    a chip unit's chip and half, a power unit's chip."""
    if isinstance(part, Capacitor):
        # its kind for View → Capacitor types ("100n film")
        return {"polarised": part.kind in POLARISED, "kind": part.kind}
    if isinstance(part, Switch):
        return switch_draw(part)
    if isinstance(part, DcJack):
        return {"plugged": part.plugged}
    if isinstance(part, Jack) and part.stereo:
        return {"stereo": True, "plugged": part.plugged}
    if isinstance(part, Guitar | Jack):
        return {"stereo": part.stereo}
    if isinstance(part, Opamp):
        return {"chip": part.chip, "half": part.half, "show_pins": part.show_pins}
    if isinstance(part, Inverter | Ota):
        return {"chip": part.chip, "half": part.half}
    if isinstance(part, PowerUnit):
        return {"chip": part.chip}
    return {}


def _polarity(part: Part, models: ModelLibrary | None) -> str | None:
    if models is None or not isinstance(part, Bjt | Jfet | Mosfet):
        return None
    try:
        return models.get(part.model).polarity
    except ModelError:
        return None


def _part_entry(
    p: Part,
    pins: list[dict[str, Any]],
    models: ModelLibrary | None,
    pickups: Mapping[str, str] | None,
) -> dict[str, Any]:
    return {
        "ref": p.ref, "type": p.type, "pos": list(p.pos), "rot": p.rot,
        "text": part_text(p, pickups),
        "label": getattr(p, "label", None), "pins": pins,
        "note": p.note or None, "polarity": _polarity(p, models),
        "draw": _draw_fields(p) | _model_draw(p, models),
    }  # fmt: skip


def _model_draw(part: Part, models: ModelLibrary | None) -> dict[str, Any]:
    """What a part's model changes in its drawing: a depletion MOSFET's solid channel
    (D-178), a zener's bent cathode bar (D-229)."""
    if models is None or not isinstance(part, Mosfet | Diode):
        return {}
    try:
        model = models.get(part.model)
    except ModelError:
        return {}
    if isinstance(part, Mosfet):
        return {"depletion": True} if model.depletion else {}
    return {"zener": True} if model.zener else {}


def text_entries(circuit: Circuit) -> list[dict[str, Any]]:
    """The sheet's text blocks (D-091): drawn, never part of the circuit."""
    return [{"title": t.title, "text": t.text, "pos": list(t.pos)} for t in circuit.texts]


def _unconnected_view(
    circuit: Circuit,
    models: ModelLibrary | None,
    problem: str,
    pickups: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Geometry only, for wiring that contradicts itself mid-edit (two labels joined):
    the editor can still draw it and undo, and `problem` says what's wrong."""
    parts = [
        _part_entry(
            p,
            [{"name": n, "pos": list(pos), "net": None} for n, pos in pin_positions(p).items()
             if n not in COMP_PINS],
            models, pickups,
        )
        for p in circuit.parts
    ]  # fmt: skip
    return {
        "circuit": circuit_to_dict(circuit),
        "parts": parts,
        "labels": [
            _label_view(lb, side)
            for lb, side in zip(circuit.labels, label_sides(circuit), strict=True)
        ],
        "wires": [{"from": list(w.from_), "to": list(w.to), "net": None} for w in circuit.wires],
        "texts": text_entries(circuit),
        "junctions": [list(j) for j in junctions(circuit)],
        "nets": {},
        "probes": {"in": None, "out": None},
        "controls": controls(circuit),
        "power": power_chip(circuit),
        "battery_wiring": None,
        "problem": problem,
    }


def circuit_view(
    circuit: Circuit,
    models: ModelLibrary | None = None,
    pickups: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Everything the schematic, the knobs panel and the probes need, as JSON-ready data.
    With `models`, transistors carry their polarity (`n`/`p`) for the symbol's arrow;
    with `pickups` (the guide's kind → name), the guitar shows its pickup's name.
    When the wiring contradicts itself, nets are left out and `problem` says why."""
    try:
        nets = connect(circuit)
    except ConnectivityError as err:
        return _unconnected_view(circuit, models, str(err), pickups)
    rails = rail_nets(circuit, nets)
    from solum.rules.graph import ac_grounds  # graph builds on this module's rail_nets

    biased = ac_grounds(circuit, nets, rails)

    parts = [
        _part_entry(
            p,
            [{"name": name, "pos": list(pos), "net": net, "number": _pin_number(p, name, models)}
             for name, (pos, net) in drawn_pins(circuit, nets, p, models).items()],
            models, pickups,
        )
        for p in circuit.parts
    ]  # fmt: skip
    spare = unused_halves(circuit, nets)
    for entry in parts:
        if entry["ref"] in spare:
            entry["draw"]["unused"] = True

    anchors: dict[str, list[Point]] = {name: [] for name in nets.members}
    for lb in circuit.labels:
        anchors[lb.net].append(lb.pos)
    for name, members in nets.members.items():
        if not anchors[name] and members:
            ref, pin = members[0]
            anchors[name].append(pin_positions(circuit.part(ref))[pin])

    probes = probe_nets(circuit, nets)
    return {
        "circuit": circuit_to_dict(circuit),
        "parts": parts,
        "labels": [
            _label_view(lb, side)
            for lb, side in zip(circuit.labels, label_sides(circuit), strict=True)
        ],
        "wires": [
            {"from": list(w.from_), "to": list(w.to), "net": net}
            for w, net in zip(circuit.wires, wire_nets(circuit, nets), strict=True)
        ],
        "texts": text_entries(circuit),
        "junctions": [list(j) for j in junctions(circuit)],
        "nets": {
            name: {
                "anchors": [list(a) for a in anchors[name]],
                "rail": name in rails,
                # a bias net a big cap holds still (VREF, the Klon's VR): drawn as a supply
                "bias": name in biased,
                "note": circuit.net_notes.get(name),
            }
            for name in sorted(nets.members)
        },
        "probes": {"in": probes.input, "out": probes.output},
        "controls": controls(circuit),
        "power": power_chip(circuit),
        "battery_wiring": battery_wiring(circuit, nets),
        "problem": None,
    }
