"""Circuit → SPICE netlist. The only code that writes netlists from circuits.

One netlist holds one analysis (D-028). Nets map to SPICE nodes (`GND` is node 0);
`Netlist.nodes` keeps that map so results can be read back by net name.
"""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from solum.circuit.chips import left_out, supply_nets
from solum.circuit.connectivity import GROUND, Nets, connect, loose_net, loose_parts
from solum.circuit.parts import POWER_PINS, closed_contacts, pin_offsets, switch_contacts
from solum.circuit.pot import pot_resistances
from solum.circuit.pump import pump_wiring
from solum.circuit.schema import (
    AmpInput,
    Battery,
    Bjt,
    Capacitor,
    ChargePump,
    ChipUnit,
    Circuit,
    DcJack,
    Diode,
    Guitar,
    Inductor,
    Inverter,
    Jack,
    Jfet,
    Led,
    Mosfet,
    Opamp,
    Ota,
    Part,
    Pot,
    Regulator,
    Resistor,
    Switch,
    Trimmer,
    VSource,
)
from solum.circuit.supply import battery_of, live_rails, on_battery
from solum.models import Model, ModelCard, ModelLibrary, model_cards_text
from solum.units import parse_value

SWITCH_ON = 0.01  # ohms across a closed contact
SWITCH_OFF = 1e12  # ohms across an open one (keeps unused throws from floating)
# Typical guitar cable (Sound On Sound, "Choosing guitar cables"; library/guides/pickups.yaml)
CABLE_FARADS_PER_METRE = 100e-12
PUMP_STEPS = 20  # transient steps per pump cycle: within 0.2 dB of 100 steps (D-093)
PUMP_EDGE = 8  # sharpness of its on/off switching (tanh of this x a sine; D-093)
PUMP_LEAK = 1e9  # ohms holding a pump's inner node and CAP+/CAP- pins (keeps them from floating)


class NetlistError(ValueError):
    """The circuit can't be turned into a netlist (plain-English message)."""


@dataclass(frozen=True)
class Op:
    """DC operating point, plus each transistor's current (for saturation checks)."""


@dataclass(frozen=True)
class Ac:
    """Small-signal frequency response with a 1 V AC source at the guitar input."""

    start: float = 10.0
    stop: float = 100e3
    per_decade: int = 50
    # For measuring each semiconductor as an N-port (`Simulator.linearise`, D-079): `sense`
    # puts a 0 V source in series with every semiconductor pin, so its current can be read;
    # `inject` (a net) drives 1 A AC into that net instead of 1 V at the guitar input.
    sense: bool = False
    inject: str | None = None
    # `open`: the guitar or the amp left out, 1 GΩ to ground in its place so its net keeps
    # a path at DC: an impedance looking into the circuit from there (D-127).
    open: str | None = None


@dataclass(frozen=True)
class Tran:
    """Transient with a sine at the guitar input. `save` lists nets to keep (empty = all).

    With `source_file`, the guitar plays a recording instead of the sine: a text file of
    "time volts" lines read by XSPICE's `filesource`, scaled by `gain` (audio renders;
    a file is as fast as the built-in sine, an inline PWL source ~50 times slower).

    `pump_ripple` False runs every charge pump at its average: no switching, so no 25 kHz
    steps to follow (an audio render about ten times faster; its whine is left out).

    `keep_from`: only the points from that time on come back (a wait's last point is all
    that's wanted of it). `state` and `coil_amps`: where the run begins instead of the
    operating point, each SPICE node's volts and each inductor's amps (by its element
    name in lower case) as an earlier run left them (`Simulator.tran`'s wait, D-275)."""

    freq: float
    amplitude: float
    stop: float
    max_step: float
    save: tuple[str, ...] = ()
    source_file: str | None = None
    gain: float = 1.0
    pump_ripple: bool = True
    keep_from: float = 0.0
    state: tuple[tuple[str, float], ...] = ()
    coil_amps: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class Dc:
    """DC sweep of one ideal source (a `vsource` part, by ref), for device curves."""

    source: str
    start: float
    stop: float
    step: float


Analysis = Op | Ac | Tran | Dc


@dataclass(frozen=True)
class Element:
    """One element line as tokens (`("R1", "in", "out", "10000")`) and the part it came
    from (None for the ideal supply's sources)."""

    ref: str | None
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class Sensed:
    """A semiconductor pin with a 0 V sense source (`Ac.sense`): the net it's on, its SPICE
    node, and the source whose current (`<source>#branch`) flows into the pin."""

    pin: str
    net: str
    node: str
    source: str


@dataclass(frozen=True)
class Netlist:
    text: str
    nodes: dict[str, str]  # net name → SPICE node
    devices: dict[str, str] = field(default_factory=dict)  # ref → SPICE device for currents
    elements: tuple[Element, ...] = ()
    sensed: dict[str, tuple["Sensed", ...]] = field(default_factory=dict)  # `Ac.sense`

    def node(self, net: str) -> str:
        try:
            return self.nodes[net]
        except KeyError:
            raise KeyError(f"No net {net!r} in this netlist.") from None


def spice_number(value: float) -> str:
    return f"{value:.12g}"


def node_names(nets: Iterable[str]) -> dict[str, str]:
    """A unique, ngspice-safe node name for each net, in sorted net order. GND → 0."""
    names: dict[str, str] = {}
    used = {"0"}
    for net in sorted(set(nets)):
        if net == GROUND:
            names[net] = "0"
            continue
        base = re.sub(r"[^a-z0-9_]", "_", net.lower())
        if base == "0" or not base.strip("_"):
            base = f"n{base}"
        name, i = base, 2
        while name in used:
            name, i = f"{base}_{i}", i + 1
        used.add(name)
        names[net] = name
    return names


def element_name(letter: str, ref: str, suffix: str = "") -> str:
    """SPICE element name: `R1` stays `R1`, a pot `VR1` becomes `R_VR1_a`."""
    base = ref if ref[0].upper() == letter else f"{letter}_{ref}"
    return f"{base}_{suffix}" if suffix else base


@dataclass
class _Emitter:
    circuit: Circuit
    nets: Nets
    models: ModelLibrary
    nodes: dict[str, str]
    lines: list[str] = field(default_factory=list)
    used_models: list[Model] = field(default_factory=list)
    extra_cards: list[str] = field(default_factory=list)
    devices: dict[str, str] = field(default_factory=dict)
    elements: list[Element] = field(default_factory=list)
    current: str | None = None  # the part being emitted
    sense: bool = False
    ripple: bool = True  # charge pumps switch (False: their average, `Tran.pump_ripple`)
    sensed: dict[str, tuple[Sensed, ...]] = field(default_factory=dict)

    def pin(self, part: Part, pin: str) -> str:
        return self.nodes[self.nets.net_of(part.ref, pin)]

    def rail(self, net: str) -> str:
        return self.nodes[net]

    def connected(self, part: Part, pin: str) -> bool:
        """The pin joins something: another pin or a label."""
        net = self.nets.net_of(part.ref, pin)
        return len(self.nets.members[net]) > 1 or any(lb.net == net for lb in self.circuit.labels)

    def add(self, *items: str) -> None:
        self.lines.append(" ".join(items))
        self.elements.append(Element(self.current, items))

    def model(self, part: Diode | Led | Jfet | Bjt | Mosfet | ChipUnit, kind: str) -> Model:
        model = self.models.get(part.model)
        if model.info.type != kind:
            raise NetlistError(
                f"{part.ref} uses {part.model}, which is a {model.info.type} model, not a "
                f"{kind} model. Pick a {kind} model."
            )
        self.used_models.append(model)
        return model

    def device(self, part: Part, letter: str, model: Model, pins: dict[str, str]) -> None:
        """A semiconductor: a primitive (`D`, `J`, `Q`) or an `X` subcircuit instance."""
        if model.info.kind == "subckt":
            try:  # the model's own pins, in its order (unused comp pins left out)
                pins = {role: pins[role] for role in model.info.pins}
            except KeyError as err:
                raise NetlistError(
                    f"Model {model.id} has a pin {err} that {part.ref} lacks."
                ) from None
        if self.sense:
            pins = self.sense_pins(part, pins)
        if model.info.kind == "subckt":
            self.add(element_name("X", part.ref), *pins.values(), model.info.spice_name)
            return
        name = element_name(letter, part.ref)
        self.devices[part.ref] = name
        self.add(name, *pins.values(), self.model_name(part, model))

    def sense_pins(self, part: Part, pins: dict[str, str]) -> dict[str, str]:
        """Each pin moved to an inner node behind a 0 V source (`Ac.sense`)."""
        net_of = {node: net for net, node in self.nodes.items()}
        used = set(self.nodes.values())
        inner, found = {}, []
        for pin, node in pins.items():
            # pin names like V+ and V- must stay apart: + → p, - → m
            spelled = re.sub(r"[^A-Za-z0-9]", "_", pin.replace("+", "p").replace("-", "m"))
            safe = f"{part.ref}_{spelled}".lower()
            name, i = f"s_{safe}", 2
            while name in used:
                name, i = f"s_{safe}_{i}", i + 1
            used.add(name)
            source = element_name("V", f"S{part.ref}", spelled)
            self.add(source, node, name, "DC", "0")
            inner[pin] = name
            found.append(Sensed(pin, net_of[node], node, source))
        self.sensed[part.ref] = tuple(found)
        return inner

    def model_name(self, part: Part, model: Model) -> str:
        if isinstance(part, Jfet) and part.measured is not None:
            return self.measured_jfet(part, model)
        if isinstance(part, Bjt) and part.measured is not None:
            return self.measured_bjt(part, model)
        return model.info.spice_name

    def measured_bjt(self, part: Bjt, model: Model) -> str:
        """A copy of the model card with its gain scaled to the measured hFE (D-130, D-153)."""
        card = model.statement
        assert part.measured is not None
        if card is None or model.bjt_spec() is None:
            raise NetlistError(
                f"{part.ref}: a measured gain needs a transistor model card; {model.id} isn't "
                "one. Pick another model or use the model's gain."
            )
        fit = self.models.bjt_fit(model, part.measured.hfe, part.measured.leakage)
        params = {**card.params, "bf": spice_number((model.param("bf") or 100.0) * fit.scale)}
        if (ise := model.param("ise")) is not None:
            params["ise"] = spice_number(ise / fit.scale)
        name = f"{card.name}_{part.ref}"
        self.extra_cards.append(ModelCard(name, card.type, params).text())
        return name

    def measured_jfet(self, part: Jfet, model: Model) -> str:
        """A copy of the model card with VTO and BETA set from measured Idss and Vp."""
        card = model.statement
        assert part.measured is not None
        if card is None or model.jfet_spec() is None:
            raise NetlistError(
                f"{part.ref}: measured Idss/Vp need a level-1 JFET model; {model.id} isn't one. "
                "Pick another model or remove the measured values."
            )
        vp, idss = part.measured.vp, part.measured.idss
        if (vp > 0) != (model.polarity == "p"):
            sign = "negative" if model.polarity == "n" else "positive"
            raise NetlistError(f"{part.ref}: an {model.id}'s pinch-off voltage is {sign}.")
        params = {**card.params, "vto": spice_number(vp), "beta": spice_number(idss / vp**2)}
        name = f"{card.name}_{part.ref}"
        self.extra_cards.append(ModelCard(name, card.type, params).text())
        return name


def _resistor(e: _Emitter, p: Resistor) -> None:
    e.add(
        element_name("R", p.ref), e.pin(p, "1"), e.pin(p, "2"), spice_number(parse_value(p.value))
    )


def _capacitor(e: _Emitter, p: Capacitor) -> None:
    e.add(
        element_name("C", p.ref), e.pin(p, "1"), e.pin(p, "2"), spice_number(parse_value(p.value))
    )


def _inductor(e: _Emitter, p: Inductor) -> None:
    """The coil, with its wire's resistance in series where it has one (D-173)."""
    one, two = e.pin(p, "1"), e.pin(p, "2")
    if p.resistance > 0:
        mid = f"{p.ref.lower()}_wire"
        e.add(element_name("R", p.ref, "wire"), one, mid, spice_number(p.resistance))
        one = mid
    e.add(element_name("L", p.ref), one, two, spice_number(parse_value(p.value)))


def _pot(e: _Emitter, p: Pot | Trimmer) -> None:
    low, high = pot_resistances(parse_value(p.value), p.rotation, p.taper)
    e.add(element_name("R", p.ref, "a"), e.pin(p, "1"), e.pin(p, "2"), spice_number(low))
    e.add(element_name("R", p.ref, "b"), e.pin(p, "2"), e.pin(p, "3"), spice_number(high))


def _switch(e: _Emitter, p: Switch) -> None:
    """A resistor per contact of the pole, open or closed (D-143: one part per pole)."""
    closed = set(closed_contacts(p))
    for common, throw in switch_contacts(p):
        e.add(
            element_name("R", p.ref, throw),
            e.pin(p, common),
            e.pin(p, throw),
            spice_number(SWITCH_ON if (common, throw) in closed else SWITCH_OFF),
        )


def _diode(e: _Emitter, p: Diode | Led) -> None:
    model = e.model(p, p.type)
    e.device(p, "D", model, {"A": e.pin(p, "A"), "K": e.pin(p, "K")})


def _jfet(e: _Emitter, p: Jfet) -> None:
    model = e.model(p, "jfet")
    e.device(p, "J", model, {k: e.pin(p, k) for k in ("D", "G", "S")})


def _mosfet(e: _Emitter, p: Mosfet) -> None:
    """ngspice's VDMOS: three pins, the body diode inside (D-175)."""
    model = e.model(p, "mosfet")
    e.device(p, "M", model, {k: e.pin(p, k) for k in ("D", "G", "S")})


def _bjt(e: _Emitter, p: Bjt) -> None:
    model = e.model(p, "bjt")
    pins = {k: e.pin(p, k) for k in ("C", "B", "E")}
    e.device(p, "Q", model, pins)
    if p.measured is not None and p.measured.leakage is not None:
        icbo = e.models.bjt_fit(model, p.measured.hfe, p.measured.leakage).icbo
        if icbo != 0:
            _leak(e, p, model, pins, icbo)


def _leak(e: _Emitter, p: Bjt, model: Model, pins: dict[str, str], icbo: float) -> None:
    """A measured leakage (D-130): a hidden current from collector to base, Icbo, which
    the transistor's gain turns into its leakage with the base open. It makes up the
    difference from the model's own, so the Geofex tester reads yours (`BjtFit`); a part
    leaking less than its model takes some of the model's away. No single model parameter
    is leakage alone (IS, ISC and BR all shape the junctions too)."""
    c, b = pins["C"], pins["B"]
    ends = (b, c) if model.polarity == "p" else (c, b)  # inside: N side to P side
    e.add(element_name("I", p.ref, "leak"), *ends, "DC", spice_number(icbo))


def _chip_unit(e: _Emitter, p: ChipUnit) -> None:
    """An op-amp, inverter or OTA (D-180): its model's subcircuit on its own pins, run from
    the chip's supply (a single's own V+ and V-, else its power unit's, D-179)."""
    model = e.model(p, p.type)
    pins = {k: e.pin(p, k) for k in pin_offsets(p) if k not in POWER_PINS}
    pos, neg = supply_nets(e.circuit, e.nets, p)
    pins |= {"V+": e.rail(pos), "V-": e.rail(neg)}
    e.device(p, "X", model, pins)


def _vsource(e: _Emitter, p: VSource) -> None:
    value = spice_number(parse_value(p.value))
    e.add(element_name("V", p.ref), e.pin(p, "+"), e.pin(p, "-"), "DC", value)


def _battery(e: _Emitter, p: Battery) -> None:
    """The battery (D-143): its voltage, behind its internal resistance if it has one.
    Left out when a DC plug cuts it off through the jack's battery lug; wired anywhere
    else it stays beside the adapter (D-185), which needs that resistance: two ideal
    supplies on one net have no solution."""
    if battery_of(e.circuit, e.nets) is not p:
        return
    plus = e.pin(p, "+")
    if on_battery(e.circuit) is None and p.resistance is None:
        net = e.nets.net_of(p.ref, "+")
        if net in live_rails(e.circuit):
            raise NetlistError(
                f"{p.ref}'s + is on {net}, so with the DC plug in the battery and the adapter "
                f"both hold {net}, which can't be simulated. Wire {p.ref}'s + to the DC jack's "
                "battery lug (bat) so the plug cuts it off, or give the battery an internal "
                "resistance."
            )
    if p.resistance is not None:
        inner = f"{p.ref.lower()}_cell"
        e.add(element_name("R", p.ref), inner, plus, spice_number(parse_value(p.resistance)))
        plus = inner
    e.add(element_name("V", p.ref), plus, e.pin(p, "-"), "DC", spice_number(parse_value(p.volts)))


def _dcjack(e: _Emitter, p: DcJack) -> None:
    """The DC jack's battery lug (D-143): on the sleeve with no plug in, open with one.
    The sleeve and centre are only where the Power menu's supply comes in."""
    if e.connected(p, "sw"):
        joined = SWITCH_OFF if p.plugged else SWITCH_ON
        e.add(element_name("R", p.ref, "sw"), e.pin(p, "sw"), e.pin(p, "+"), spice_number(joined))


def _jack(e: _Emitter, p: Jack) -> None:
    """A stereo jack's ring (D-185): a cable's sleeve joins it to S with a cable in, open
    with none. The rest of a jack is drawing only (D-174)."""
    if p.stereo and e.connected(p, "R") and e.connected(p, "S"):
        joined = SWITCH_ON if p.plugged else SWITCH_OFF
        e.add(element_name("R", p.ref, "ring"), e.pin(p, "R"), e.pin(p, "S"), spice_number(joined))


def _amp(e: _Emitter, p: AmpInput) -> None:
    e.add(element_name("R", p.ref), e.pin(p, "in"), "0", spice_number(parse_value(p.value)))


def pump_frequency(part: ChargePump, models: ModelLibrary, boost: bool) -> float:
    """How often the pump moves charge (Hz): its chip's pump frequency, boosted when
    `boost` (pin 1 on V+, `PumpWiring.boost`) and the chip has a boost pin. NetlistError
    for a chip that isn't a charge pump."""
    model = models.get(part.model)
    if model.info.type != "chargepump":
        raise NetlistError(
            f"{part.ref} uses {part.model}, which is a {model.info.type} model, not a charge "
            "pump. Pick a charge-pump chip."
        )
    params = model.info.params
    return params["f_pump_boost"] if boost and "f_pump_boost" in params else params["f_pump"]


def pump_resistance(
    part: ChargePump, cap: Capacitor, models: ModelLibrary, boost: bool = False
) -> float:
    """The pump's output resistance with the cap drawn (D-226): the sheet's, measured with
    its own cap (`c_pump`), less that cap's share 1/(f·C) plus the drawn cap's, at the
    pump frequency in use."""
    params = models.get(part.model).info.params
    freq, sheet = pump_frequency(part, models, boost), params["r_out"]
    drawn = parse_value(cap.value)
    if drawn <= 0:
        raise NetlistError(f"{cap.ref} has no value, so {part.ref} can't pump. Give it one.")
    return sheet - 1 / (freq * params["c_pump"]) + 1 / (freq * drawn)


def _chargepump(e: _Emitter, p: ChargePump) -> None:
    """The averaged pump (D-093), fed by its drawn parts (D-226): an ideal doubler (2 x in,
    into the diodes' junction through a copy of D1) or inverter (-in, on VOUT), less the
    chip's own drop, behind its output resistance with the drawn cap (`pump_resistance`),
    delivering its charge in half-cycle pulses at the pump frequency. At time 0 (and so in
    .op and .ac) the pulses sit at their average, so DC and small-signal results are the
    pump's steady state. The input draws the output current times the ratio, plus the
    chip's quiescent current. CAP+ and CAP- sit at their averages, half V+ and half VOUT,
    as a meter reads them (Aion's Klon: 5.02 and -4.66 V)."""
    wiring = pump_wiring(e.circuit, e.nets, p)
    if wiring.problems:
        raise NetlistError(wiring.problems[0])
    params = e.models.get(p.model).info.params
    drop = params.get("v_drop", 0.0)
    boosted = wiring.boost and "f_pump_boost" in params
    i_q = params.get("i_q_boost", params["i_q"]) if boosted else params["i_q"]
    pins = {k: e.pin(p, k) for k in ("in", "gnd", "cap+", "cap-", "out")}
    if wiring.doubler:
        pins["junction"] = e.rail(wiring.doubler.junction)
    if e.sense:
        pins = e.sense_pins(p, pins)
    vin, gnd = pins["in"], pins["gnd"]
    # its charge in half-cycle pulses; without ripple, their average (the pulses at t = 0)
    freq = spice_number(2 * math.pi * pump_frequency(p, e.models, wiring.boost))
    gate = f"(1+tanh({PUMP_EDGE}*sin({freq}*time)))" if e.ripple else "1"
    draws: list[str] = []
    if wiring.doubler:
        node = f"{p.ref.lower()}_pump_sw"
        r_out = spice_number(pump_resistance(p, wiring.doubler.cap, e.models, wiring.boost))
        charge = f"{gate}*(2*v({vin},{gnd})-{spice_number(drop)}-v({node},{gnd}))/{r_out}"
        e.add(element_name("B", p.ref, "dbl"), gnd, node, f"I={{{charge}}}")
        draws.append(f"2*{charge}")
        _doubler_diode(e, p, wiring.doubler.low, node, pins["junction"], gnd)
    if wiring.negative and wiring.flying:
        out = pins["out"]
        r_out = spice_number(pump_resistance(p, wiring.flying, e.models, wiring.boost))
        charge = f"{gate}*(-v({vin},{gnd})+{spice_number(drop)}-v({out},{gnd}))/{r_out}"
        e.add(element_name("B", p.ref, "out"), gnd, out, f"I={{{charge}}}")
        draws.append(f"-1*{charge}")
    e.add(element_name("B", p.ref, "in"), vin, gnd, f"I={{{'+'.join(draws)}+{spice_number(i_q)}}}")
    # CAP+ and CAP- at their averages, as a meter reads them: half V+, half VOUT
    for name, pin, ends in (("cp", "cap+", (vin, gnd)), ("cm", "cap-", (gnd, pins["out"]))):
        for i, end in enumerate(ends, 1):
            leak = spice_number(2 * PUMP_LEAK)
            e.add(element_name("R", p.ref, f"{name}{i}"), pins[pin], end, leak)


def _doubler_diode(e: _Emitter, p: ChargePump, low: Diode, node: str, junction: str,
                   gnd: str) -> None:  # fmt: skip
    """The pump's charge reaches the junction through a copy of D1, the diode it flows
    through in a real doubler (drawn D1, from V+, then sits reverse-biased)."""
    diode = e.models.get(low.model)
    if diode.info.type != "diode":
        raise NetlistError(f"{low.ref} uses {low.model}, which isn't a diode model. Pick a diode.")
    if diode.info.kind == "subckt":
        raise NetlistError(
            f"{low.ref} is a zener ({low.model}), but {p.ref}'s doubler needs a plain diode "
            "there, such as the 1N5817."
        )
    e.used_models.append(diode)
    e.add(element_name("R", p.ref, "leak"), node, gnd, spice_number(PUMP_LEAK))
    e.add(element_name("D", p.ref, "1"), node, junction, diode.info.spice_name)


REG_SMOOTH = 0.1  # volts: how gently the regulator's output bends into dropout and to 0 V


def _soft_min(a: str, b: str) -> str:
    """min(a, b) with its corner rounded over REG_SMOOTH volts, smooth for Newton and never
    overflowing: min less a softplus of the gap."""
    w = spice_number(REG_SMOOTH)
    return f"(min({a},{b})-{w}*ln(1+exp(-abs(({a})-({b}))/{w})))"


def _regulator(e: _Emitter, p: Regulator) -> None:
    """A fixed linear regulator (D-227), from its sheet's figures: `v_out` (at `v_in_ref`
    in, moving `line` volts per input volt), never above the input less `v_dropout`, nor
    below 0 V; behind `r_out` (its load regulation). The input draws the output current
    plus `i_bias`. Ripple on the input passes at `line` (the sheet's ripple rejection, about
    the same), at every frequency."""
    model = e.models.get(p.model)
    if model.info.type != "regulator":
        raise NetlistError(
            f"{p.ref} uses {p.model}, which is a {model.info.type} model, not a regulator. "
            "Pick a regulator."
        )
    k = model.info.params
    pins = {name: e.pin(p, name) for name in ("in", "gnd", "out")}
    if e.sense:
        pins = e.sense_pins(p, pins)
    vin, gnd, out = pins["in"], pins["gnd"], pins["out"]
    inner = f"{p.ref.lower()}_reg"
    vi = f"v({vin},{gnd})"
    held = (
        f"{spice_number(k['v_out'])}+{spice_number(k['line'])}*({vi}-{spice_number(k['v_in_ref'])})"
    )
    headroom = f"{vi}-{spice_number(k['v_dropout'])}"
    w = spice_number(REG_SMOOTH)
    m = _soft_min(held, headroom)
    floor = f"(max({m},0)+{w}*ln(1+exp(-abs({m})/{w})))"
    r_out = spice_number(k["r_out"])
    e.add(element_name("B", p.ref, "v"), inner, gnd, f"V={{{floor}}}")
    e.add(element_name("R", p.ref, "out"), inner, out, r_out)
    draw = f"(v({inner},{gnd})-v({out},{gnd}))/{r_out}+{spice_number(k['i_bias'])}"
    e.add(element_name("B", p.ref, "in"), vin, gnd, f"I={{{draw}}}")


def _emit(e: _Emitter, part: Part, analysis: Analysis) -> None:
    e.current = part.ref
    match part:
        case Resistor():
            _resistor(e, part)
        case Capacitor():
            _capacitor(e, part)
        case Inductor():
            _inductor(e, part)
        case Pot() | Trimmer():
            _pot(e, part)
        case Switch():
            _switch(e, part)
        case Diode() | Led():
            _diode(e, part)
        case Jfet():
            _jfet(e, part)
        case Bjt():
            _bjt(e, part)
        case Mosfet():
            _mosfet(e, part)
        case Opamp() | Inverter() | Ota():
            _chip_unit(e, part)
        case VSource():
            _vsource(e, part)
        case ChargePump():
            _chargepump(e, part)
        case Regulator():
            _regulator(e, part)
        case AmpInput():
            _amp(e, part)
        case Battery():
            _battery(e, part)
        case DcJack():
            _dcjack(e, part)
        case Jack():
            _jack(e, part)
        case Guitar():
            _guitar(e, part, analysis)


OPEN_OHMS = 1e9  # what a part left out leaves at its pin: nothing, but a path at DC


def _leave_out(e: _Emitter, p: Part) -> None:
    """The guitar or the amp, left out (`Ac.open`)."""
    pin = {Guitar: "out", AmpInput: "in"}.get(type(p))
    if pin is None:
        raise NetlistError(f"Only the guitar or the amp can be left out, not {p.ref}.")
    e.add(element_name("R", f"{p.ref}_open"), e.pin(p, pin), "0", spice_number(OPEN_OHMS))


def _guitar(e: _Emitter, p: Guitar, analysis: Analysis) -> None:
    if isinstance(analysis, Ac):
        stimulus = "DC 0 AC 0" if analysis.inject else "DC 0 AC 1"
    elif isinstance(analysis, Tran):
        stimulus = f"DC 0 SIN(0 {spice_number(analysis.amplitude)} {spice_number(analysis.freq)})"
    else:
        stimulus = "DC 0"
    if p.stereo and e.connected(p, "ring"):  # the cable's sleeve joins the jack's ring (D-143)
        e.add(element_name("R", p.ref, "ring"), e.pin(p, "ring"), "0", spice_number(SWITCH_ON))
    out = e.pin(p, "out")
    recording = analysis.source_file if isinstance(analysis, Tran) else None
    if p.source == "ideal":
        level = 1.0
        if p.volume is not None:  # a buffer after the guitar's volume: only its level turns
            low, high = pot_resistances(parse_value(p.volume), p.rotation, p.taper)
            level = low / (low + high)
        _guitar_source(e, p, out, _scaled(stimulus, level), recording, analysis, level)
        return
    assert p.pickup is not None
    name = f"{out}_{p.ref.lower()}"
    src, mid = f"{name}_emf", f"{name}_coil"
    coil = f"{name}_pu" if p.volume is not None else out
    _guitar_source(e, p, src, stimulus, recording, analysis)
    e.add(element_name("R", p.ref, "coil"), src, mid, spice_number(parse_value(p.pickup.r)))
    e.add(element_name("L", p.ref), mid, coil, spice_number(parse_value(p.pickup.l)))
    e.add(element_name("C", p.ref, "coil"), coil, "0", spice_number(parse_value(p.pickup.c)))
    if p.volume is not None:  # the volume pot: lug 3 the coil, wiper the output, lug 1 ground
        low, high = pot_resistances(parse_value(p.volume), p.rotation, p.taper)
        e.add(element_name("R", p.ref, "vola"), "0", out, spice_number(low))
        e.add(element_name("R", p.ref, "volb"), out, coil, spice_number(high))
    if p.cable > 0:
        farads = p.cable * CABLE_FARADS_PER_METRE
        e.add(element_name("C", p.ref, "cable"), out, "0", spice_number(farads))


def _scaled(stimulus: str, level: float) -> str:
    """A guitar stimulus at `level` times its size: the AC magnitude and a SIN's
    amplitude (`DC 0 AC 1`, `DC 0 SIN(0 0.3 200)`); the DC stays 0."""
    if level == 1.0:
        return stimulus
    words = stimulus.split()
    for i, w in enumerate(words[:-1]):
        if w in ("AC", "SIN(0"):
            words[i + 1] = spice_number(float(words[i + 1]) * level)
    return " ".join(words)


def _guitar_source(
    e: _Emitter,
    p: Guitar,
    node: str,
    stimulus: str,
    recording: str | None,
    analysis: Analysis,
    level: float = 1.0,
) -> None:
    """The guitar's voltage source: `stimulus`, or a recording played from a file, at
    `level` times its size (a buffered guitar's volume, D-134)."""
    if recording is None:
        e.add(element_name("V", p.ref), node, "0", stimulus)
        return
    if '"' in recording or "\n" in recording:
        raise NetlistError("The recording's file name can't be used.")
    assert isinstance(analysis, Tran)
    model = f"rec_{p.ref.lower()}"
    e.add(element_name("A", p.ref), f"%vd([{node} 0])", model)
    e.extra_cards.append(
        f'.model {model} filesource (file="{recording}" amploffset=[0] '
        f"amplscale=[{spice_number(analysis.gain * level)}] timeoffset=0 timescale=1 "
        "timerelative=false amplstep=false)"
    )


def rail_sources(circuit: Circuit) -> dict[str, str]:
    """Rail net → the SPICE source that holds it (`V_RAIL1`...), whose branch current is
    what the supply delivers; on a battery, the battery's source for the positive rails
    (D-143)."""
    battery = on_battery(circuit)
    live = live_rails(circuit)
    sources = {}
    for i, name in enumerate(sorted(circuit.power.rails), start=1):
        if name in live:
            sources[name] = element_name("V", f"RAIL{i}")
        elif battery is not None:
            sources[name] = element_name("V", battery.ref)
    return sources


def input_part(circuit: Circuit) -> Guitar | None:
    """The circuit's guitar input (there is at most one: it's always IN, D-141)."""
    return next((p for p in circuit.parts if isinstance(p, Guitar)), None)


def _analysis_lines(analysis: Analysis, e: _Emitter, netlist_nodes: dict[str, str]) -> list[str]:
    if isinstance(analysis, Op):
        currents = []
        for ref, name in sorted(e.devices.items()):
            part = e.circuit.part(ref)
            if isinstance(part, Bjt):
                currents += [f"@{name.lower()}[ic]", f"@{name.lower()}[ib]"]
            elif isinstance(part, Jfet | Mosfet | Diode | Led):
                currents.append(f"@{name.lower()}[id]")
        return ([f".save all {' '.join(currents)}"] if currents else []) + [".op"]
    if isinstance(analysis, Dc):
        source = element_name("V", analysis.source)
        sweep = (analysis.start, analysis.stop, analysis.step)
        return [f".dc {source} {' '.join(spice_number(x) for x in sweep)}"]
    if isinstance(analysis, Ac):
        return [f".ac dec {analysis.per_decade} {spice_number(analysis.start)} "
                f"{spice_number(analysis.stop)}"]  # fmt: skip
    lines = []
    if analysis.save:
        saved = [f"v({netlist_nodes[n]})" for n in analysis.save if netlist_nodes[n] != "0"]
        lines.append(f".save {' '.join(saved)}")
    pumps = [
        pump_frequency(p, e.models, pump_wiring(e.circuit, e.nets, p).boost)
        for p in e.circuit.parts
        if isinstance(p, ChargePump) and analysis.pump_ripple
    ]
    step = spice_number(min([analysis.max_step, *(1 / (PUMP_STEPS * f) for f in pumps)]))
    tran = f".tran {step} {spice_number(analysis.stop)} {spice_number(analysis.keep_from)} {step}"
    if analysis.state:
        lines += [f".ic v({node})={volts!r}" for node, volts in analysis.state]
        tran += " uic"  # start from the .ic lines and the inductors' ic=, not a DC solve
    lines.append(tran)
    return lines


def _with_currents(lines: list[str], coil_amps: tuple[tuple[str, float], ...]) -> list[str]:
    """`lines` with each inductor starting at its current (`Tran.coil_amps`)."""
    amps = dict(coil_amps)
    return [
        f"{line} ic={amps[name]!r}" if (name := line.split()[0].lower()) in amps else line
        for line in lines
    ]


def generate_netlist(
    circuit: Circuit, models: ModelLibrary, analysis: Analysis, nets: Nets | None = None
) -> Netlist:
    """The SPICE netlist for one analysis of `circuit`. Deterministic for equal inputs."""
    e = _emitter(circuit, models, nets)
    nets, nodes = e.nets, e.nodes
    e.sense = isinstance(analysis, Ac) and analysis.sense
    e.ripple = not isinstance(analysis, Tran) or analysis.pump_ripple
    guitar = input_part(circuit)
    if guitar is None and isinstance(analysis, Ac | Tran):
        raise NetlistError("Add a guitar input to the circuit to see its response.")
    if isinstance(analysis, Dc):
        swept = next((p for p in circuit.parts if p.ref == analysis.source), None)
        if not isinstance(swept, VSource):
            raise NetlistError(
                f"A DC sweep needs a voltage source to sweep; {analysis.source} isn't one."
            )
    if isinstance(analysis, Ac) and analysis.inject:
        if analysis.inject not in nodes:
            raise NetlistError(f"There's no net {analysis.inject!r} to drive.")
        require_wired(circuit, nets, analysis.inject)
    if isinstance(analysis, Tran):
        for net in analysis.save:
            if net not in nodes:
                raise NetlistError(f"There's no net {net!r} to record.")
            require_wired(circuit, nets, net)

    e.current = None
    sources = rail_sources(circuit)
    for name, volts in sorted(live_rails(circuit).items()):
        e.add(sources[name], nodes[name], "0", "DC", spice_number(volts))
    opened = analysis.open if isinstance(analysis, Ac) else None
    skipped = left_out(circuit, nets)  # unused halves and loose parts (D-140, D-165)
    for part in circuit.parts:
        if part.ref in skipped:
            continue
        if part.ref == opened:
            _leave_out(e, part)
        else:
            _emit(e, part, analysis)
    e.current = None
    if isinstance(analysis, Ac) and analysis.inject:
        e.add("I_INJECT", "0", nodes[analysis.inject], "DC", "0", "AC", "1")

    cards = model_cards_text(e.used_models)
    coil_amps = analysis.coil_amps if isinstance(analysis, Tran) else ()
    body = [
        f"* {circuit.name}".replace("\n", " "),
        *(_with_currents(e.lines, coil_amps) if coil_amps else e.lines),
        *([cards] if cards else []),
        *e.extra_cards,
        *_analysis_lines(analysis, e, nodes),
        ".end",
    ]
    return Netlist(
        text="\n".join(body) + "\n",
        nodes=nodes,
        devices=e.devices,
        elements=tuple(e.elements),
        sensed=e.sensed,
    )


def require_wired(circuit: Circuit, nets: Nets, net: str) -> None:
    """NetlistError if only loose parts touch `net`: the simulation leaves them out, so
    it has nothing to record or drive there (D-165)."""
    loose = loose_parts(circuit, nets)
    if loose_net(nets, loose, net):
        refs = sorted({ref for ref, _ in nets.members[net]})
        verb, them = ("isn't", "it") if len(refs) == 1 else ("aren't", "them")
        raise NetlistError(
            f"{' and '.join(refs)} {verb} wired into the circuit yet, so the simulation "
            f"leaves {them} out and there's nothing to measure here. Wire {them} in first."
        )


def _emitter(circuit: Circuit, models: ModelLibrary, nets: Nets | None) -> _Emitter:
    nets = nets or connect(circuit)
    rail_nets = set(circuit.power.rails)
    nodes = node_names([*nets.members, *rail_nets, GROUND])
    return _Emitter(circuit, nets, models, nodes)


def part_elements(
    circuit: Circuit,
    parts: Iterable[Part],
    models: ModelLibrary,
    analysis: Analysis,
    nets: Nets | None = None,
) -> list[tuple[Element, ...]]:
    """The elements each of `parts` would add to `circuit`'s netlist: copies of its parts
    with other values (a slider's steps), wired as the circuit's own part with that ref."""
    e = _emitter(circuit, models, nets)
    out = []
    for part in parts:
        e.elements = []
        _emit(e, part, analysis)
        out.append(tuple(e.elements))
    return out
