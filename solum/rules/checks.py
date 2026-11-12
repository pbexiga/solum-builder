"""The checks behind the rule files: one function per rule, registered by name (D-077).

A check looks at a `Context` (the circuit and its nets; after `.op` also the operating
point; for a failed run, the error) and yields a `Hit` per thing it found: which part
and nets to highlight and the values its rule's texts fill in (`{ref}`, `{volts}`...).
Thresholds that are design choices, not datasheet values, are named constants here.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import cached_property

from solum.analysis.dc import Saturation, opamp_input_limits, saturation
from solum.bias import BiasError
from solum.circuit.chips import halves, spare_ota, supply_nets, unused_halves
from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, loose_parts, spare_poles
from solum.circuit.parts import (
    COMP_PINS,
    EXTRA_PINS,
    OPAMP_PIN_ROLES,
    POWER_PINS,
    closed_contacts,
    pin_offsets,
    switch_contacts,
)
from solum.circuit.pot import MIN_RESISTANCE
from solum.circuit.pump import SPARE_PINS, pump_wiring
from solum.circuit.refs import ref_key
from solum.circuit.schema import (
    CHIP_UNITS,
    POLARISED,
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
    PowerUnit,
    Regulator,
    Resistor,
    Switch,
    Trimmer,
    VSource,
)
from solum.circuit.supply import battery_of, live_rails, on_battery, supply_volts
from solum.circuit.switches import CUSTOM
from solum.models import Model, ModelLibrary
from solum.netlist import NetlistError, pump_frequency
from solum.rules import graph
from solum.rules.rule import Layer
from solum.sim.engine import SimError, singular_nodes
from solum.simulate import OpResult
from solum.units import format_quantity, parse_value
from solum.view import probe_nets, rail_nets

# Design choices (D-077), not datasheet values:
JFET_VDS_LOW = 1.0  # volts: less leaves a JFET stage almost no room to swing (SPEC §4)
GATE_FORWARD = 0.5  # volts: a JFET gate this far forward of its source conducts
DEFAULT_RATING_W = 0.25  # watts: the usual pedal resistor, when no rating is given
REVERSE_LIMIT = 0.5  # volts: a polarised cap reversed by more is fitted the wrong way
OUTPUT_DC_LIMIT = 0.1  # volts: more DC at the output thumps the amp when switched
SHORT_OHMS = 1.0  # ohms: a resistor this small between two supplies is a short
SHOWN_NETS = 3  # nets named in a message before "and N more"
AUDIO_TOP = 20e3  # hertz: a pump below this can be heard as a whine (D-093)
C0G_TOP = 10e-9  # farads: C0G ceramics are sold up to about this (capacitor guide, D-095)
# Build checks (9d1, D-203):
CAP_MARGIN = 0.8  # a capacitor with more than this share of its rating across it is too close
POWER_MARGIN = 0.5  # a resistor dissipating more than this share of its rating runs hot
CAP_RATINGS = (6.3, 10.0, 16.0, 25.0, 35.0, 50.0, 63.0, 100.0)  # volts: electrolytics sold
SUPPLY_PATH_OHMS = 1e3  # a supply filter resistor is under this (10-100 Ω); more biases (D-238)
SAG_SHARE = 0.5  # a supply-path net under this share of its rail has lost the supply (D-238)


@dataclass(frozen=True)
class Hit:
    """One thing a check found: what to highlight and what to fill the texts with."""

    ref: str | None = None
    nets: tuple[str, ...] = ()
    values: Mapping[str, str] = field(default_factory=dict)
    refs: tuple[str, ...] = ()  # more parts to highlight, after `ref` (a grouped problem)


@dataclass
class Context:
    """What the checks look at. `nets` is None when the wiring contradicts itself."""

    circuit: Circuit
    models: ModelLibrary
    nets: Nets | None
    wiring_error: ConnectivityError | None = None
    op: OpResult | None = None
    error: Exception | None = None  # a failed run (sim_error layer)
    nodes: Mapping[str, str] = field(default_factory=dict)  # SPICE node → net, for errors

    @property
    def n(self) -> Nets:
        assert self.nets is not None, "topology checks run only on consistent wiring"
        return self.nets

    def net(self, part: Part, pin: str) -> str:
        return self.n.net_of(part.ref, pin)

    def v(self, part: Part, pin: str) -> float:
        assert self.op is not None
        return self.op.voltages[self.net(part, pin)]

    def volts(self, net: str) -> float:
        assert self.op is not None
        return self.op.voltages[net]

    def parts[T: Part](self, kind: type[T]) -> list[T]:
        """The parts of `kind` that are simulated: a chip's unused half isn't (D-140), nor
        a loose part (D-165)."""
        return [p for p in self.circuit.parts if isinstance(p, kind) and self.simulated(p)]

    def simulated(self, part: Part) -> bool:
        return part.ref not in self.spare | self.loose

    @cached_property
    def spare(self) -> set[str]:
        """A chip's unused halves: left out of the netlist and of every rule but their own."""
        return unused_halves(self.circuit, self.n)

    @cached_property
    def loose(self) -> set[str]:
        """Parts no current can reach: left out of the netlist (D-165)."""
        return loose_parts(self.circuit, self.n)

    def supply(self, part: ChipUnit) -> tuple[str, str]:
        """The nets on a chip's V+ and V- pins."""
        return supply_nets(self.circuit, self.n, part)

    def model(
        self, part: Diode | Led | Jfet | Bjt | Mosfet | ChipUnit | ChargePump | Regulator
    ) -> Model:
        return self.models.get(part.model)

    @cached_property
    def supplies(self) -> set[str]:
        return rail_nets(self.circuit, self.n)

    @cached_property
    def hard(self) -> set[str]:
        """Nets held at a fixed voltage by a supply: GND, rails, DC source pins."""
        found = set(self.supplies)
        for p in self.parts(VSource):
            found |= {self.net(p, "+"), self.net(p, "-")}
        battery = battery_of(self.circuit, self.n)
        if battery is not None:
            found |= {self.net(battery, "+"), self.net(battery, "-")}
        return found

    @cached_property
    def quiet(self) -> set[str]:
        """Nets a signal can't pass through: supplies and AC-grounded bias nets."""
        return graph.quiet_nets(self.circuit, self.n)

    @cached_property
    def known_volts(self) -> dict[str, float]:
        """Nets whose voltage the file states: GND and the rails."""
        return {GROUND: 0.0, **live_rails(self.circuit)}

    @cached_property
    def biased(self) -> set[str]:
        """Nets whose DC voltage something sets (see `graph.bias_edges`)."""
        joined = graph.groups(self.n.members, graph.bias_edges(self.circuit, self.n))
        anchors = graph.bias_anchors(self.circuit, self.n)
        return {net for net, group in joined.items() if group & anchors}

    @cached_property
    def saturated(self) -> list[Saturation]:
        assert self.op is not None
        return saturation(self.circuit, self.n, self.op.voltages, self.op.currents, self.models)


CheckFn = Callable[[Context], Iterator[Hit]]
CHECKS: dict[str, tuple[Layer, CheckFn]] = {}


def check(layer: Layer) -> Callable[[CheckFn], CheckFn]:
    """Register a check under its function name for rule files to name."""

    def register(fn: CheckFn) -> CheckFn:
        CHECKS[fn.__name__] = (layer, fn)
        return fn

    return register


def listing(items: list[str], shown: int = SHOWN_NETS) -> str:
    """`a, b and c`; past `shown` items, `a, b, c and 2 more`."""
    if len(items) > shown:
        return f"{', '.join(items[:shown])} and {len(items) - shown} more"
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _input_name(pin: str) -> str:
    """An op-amp input as printed: `+`, or a real minus sign (U+2212)."""
    return "+" if pin == "+" else chr(0x2212)


def _v(x: float) -> str:
    return f"{x:.2f} V"


# ---- topology -----------------------------------------------------------------------


@check("topology")
def labels_joined(ctx: Context) -> Iterator[Hit]:
    if ctx.wiring_error is not None:
        yield Hit(values={"labels": listing(list(ctx.wiring_error.names))})


def _pins_left_open(part: Part) -> set[str]:
    """Pins that may sensibly connect to nothing: a pot's ends (wired as a variable
    resistor), a switch's throws (a spare position), unused compensation pins, a
    stereo jack's ring and a charge pump's pins 1, 6 and 7."""
    if isinstance(part, Pot | Trimmer):
        return {"1", "3"}
    if isinstance(part, Switch):
        return {throw for _, throw in switch_contacts(part)}
    if isinstance(part, DcJack):
        return {"sw"}  # the battery lug: only a battery uses it (D-143)
    if isinstance(part, Guitar):
        return {"ring"}  # a stereo jack's ring: only a battery uses it
    if isinstance(part, Jack):
        return {"R"}  # a stereo jack's ring: a battery's switch, or nothing (D-174)
    if isinstance(part, Ota):  # an LM13700's diodes and buffer are used or not (D-180)
        return {"dbias", "bufin", "bufout"}
    if isinstance(part, ChargePump):  # boost or FB, LV or VREF, OSC (v28)
        return set(SPARE_PINS)
    return {*COMP_PINS, *EXTRA_PINS} if isinstance(part, Opamp) else set()


def _open_pins(ctx: Context, part: Part) -> str | None:
    """`pins 1 and 2`: the part's pins that connect to nothing (pins that may be left
    open aside, and a spare OTA's output and bias current together), or None."""
    ports = set(ctx.circuit.ports.values()) if ctx.circuit.template else set()
    found = [
        pin
        for pin in pin_offsets(part)
        if pin not in _pins_left_open(part)
        and len(ctx.n.members[net := ctx.net(part, pin)]) == 1
        and net not in ctx.supplies
        and net not in ports
    ]
    if isinstance(part, Ota) and spare_ota(ctx.circuit, ctx.n, part):
        found = [pin for pin in found if pin not in ("out", "iabc")]  # off, as datasheets leave it
    if not found:
        return None
    return f"{'pin' if len(found) == 1 else 'pins'} {listing(found, 9)}"


@check("topology")
def unconnected_pin(ctx: Context) -> Iterator[Hit]:
    for part in ctx.circuit.parts:
        if part.ref in ctx.spare | ctx.loose:
            continue  # their own warnings say what to do
        if pins := _open_pins(ctx, part):
            yield Hit(part.ref, values={"pins": pins})


@check("topology")
def part_not_simulated(ctx: Context) -> Iterator[Hit]:
    """A part no current reaches, left out of the simulation (D-165)."""
    spare = spare_poles(ctx.circuit, ctx.n)
    for part in ctx.circuit.parts:
        if part.ref in ctx.loose - spare:
            pins = _open_pins(ctx, part)
            verb = "connect" if pins and pins.startswith("pins") else "connects"
            yield Hit(part.ref, values={"open": f" ({pins} {verb} to nothing)" if pins else ""})


@check("topology")
def model_missing(ctx: Context) -> Iterator[Hit]:
    """A part naming a model the library doesn't have (a card that isn't included, or one
    another user added): the circuit opens and draws, and this says which model to add."""
    for part in ctx.circuit.parts:
        model = getattr(part, "model", None)
        if model and model not in ctx.models:
            yield Hit(part.ref, values={"model": model})


@check("topology")
def no_dc_path(ctx: Context) -> Iterator[Hit]:
    edges = graph.spice_edges(ctx.circuit, ctx.n)
    with_pins = [n for n, pins in ctx.n.members.items() if any(r not in ctx.loose for r, _ in pins)]
    joined = graph.groups([*with_pins, GROUND], edges)
    floating = sorted(n for n in with_pins if GROUND not in joined[n])
    if floating:
        which = f"net {floating[0]} has" if len(floating) == 1 else f"nets {listing(floating)} have"
        yield Hit(nets=tuple(floating), values={"which": which})


@check("topology")
def opamp_no_feedback(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Opamp):
        out, minus = ctx.net(p, "out"), ctx.net(p, "-")
        edges = graph.signal_edges(ctx.circuit, ctx.n, skip=p.ref)
        if minus not in graph.reachable(out, edges, blocked=ctx.quiet):
            yield Hit(p.ref, (minus, out))


@check("topology")
def opamp_no_dc_feedback(ctx: Context) -> Iterator[Hit]:
    """Feedback through capacitors only (opamp-no-feedback covers none at all); a path
    through another op-amp's output from the outside isn't feedback (D-247)."""
    for p in ctx.parts(Opamp):
        out, minus = ctx.net(p, "out"), ctx.net(p, "-")
        signal = graph.signal_edges(ctx.circuit, ctx.n, skip=p.ref)
        if minus not in graph.reachable(out, signal, blocked=ctx.quiet):
            continue
        steady = graph.signal_edges(ctx.circuit, ctx.n, skip=p.ref, dc=True)
        arcs = graph.one_way_outputs(ctx.circuit, ctx.n, steady, p.ref)
        if minus not in graph.reachable(out, arcs, blocked=ctx.quiet, directed=True):
            yield Hit(p.ref, (minus, out))


@check("topology")
def opamp_input_unbiased(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Opamp):
        for pin in ("+", "-"):
            net = ctx.net(p, pin)
            if net not in ctx.biased:
                yield Hit(p.ref, (net,), {"input": _input_name(pin)})


@check("topology")
def transistor_input_unbiased(ctx: Context) -> Iterator[Hit]:
    for p in [
        p for p in ctx.circuit.parts if isinstance(p, Bjt | Jfet | Mosfet) and ctx.simulated(p)
    ]:
        pin, name = ("B", "base") if isinstance(p, Bjt) else ("G", "gate")
        net = ctx.net(p, pin)
        if net not in ctx.biased:
            yield Hit(p.ref, (net,), {"pin": name})


@check("topology")
def opamp_supply_missing(ctx: Context) -> Iterator[Hit]:
    powered = {GROUND, *ctx.circuit.power.rails}
    holders = _power_holders(ctx)
    power_pins = {(p.ref, pin) for p in holders for pin in POWER_PINS}
    for p in holders:
        for pin in POWER_PINS:
            supply = ctx.net(p, pin)
            if supply in powered or set(ctx.n.members[supply]) - power_pins:
                continue
            if any(lb.net == supply for lb in ctx.circuit.labels):
                where = f"is on {supply}, which isn't a supply here"
                yield Hit(p.ref, (supply,), {"where": where, "pin": pin})
            else:  # wired to nothing, or only to other chips' supply pins (D-237)
                alone = len(ctx.n.members[supply]) == 1
                where = "connects to nothing" if alone else "connects only to chips' supply pins"
                yield Hit(p.ref, (supply,), {"where": where, "pin": pin})


def _power_holders(ctx: Context) -> list[ChipUnit | PowerUnit]:
    """The parts with a chip's V+ and V- pins: singles and power units (D-179, D-180)."""
    return [p for p in ctx.circuit.parts
            if isinstance(p, PowerUnit) or (isinstance(p, CHIP_UNITS) and not p.half)]  # fmt: skip


@check("topology")
def opamp_output_on_supply(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Opamp):
        out = ctx.net(p, "out")
        if out in ctx.supplies:
            yield Hit(p.ref, (out,), {"net": out})


def _pin(ctx: Context, p: ChipUnit, pin: str) -> str:
    """`pin 7` from the model's datasheet numbers, else the pin's name (`out`)."""
    number = ctx.model(p).pin_number(pin, p.half)
    return f"pin {number}" if number else pin


@check("topology")
def opamp_half_unused(ctx: Context) -> Iterator[Hit]:
    """A chip's half with nothing on it: wire it as a buffer (D-140)."""
    for p in ctx.circuit.parts:
        if not isinstance(p, Opamp) or p.ref not in ctx.spare:
            continue
        pos, neg = ctx.supply(p)
        if "VREF" in ctx.n.members:
            mid = "VREF"
        else:
            high = ctx.known_volts.get(pos)
            low = ctx.known_volts.get(neg, 0.0)
            volts = format_quantity((high + low) / 2, "V") if high is not None else "half-supply"
            mid = f"a {volts} point (two equal resistors, 100k each, from {pos} to {neg})"
        yield Hit(
            p.ref,
            values={
                "chip": p.chip, "model": p.model, "out": _pin(ctx, p, "out"),
                "minus": _pin(ctx, p, "-"), "plus": _pin(ctx, p, "+"), "mid": mid,
            },
        )  # fmt: skip


_UNIT_NOUNS = {"inverter": "inverters", "ota": "OTAs"}


@check("topology")
def chip_unit_unused(ctx: Context) -> Iterator[Hit]:
    """A 4049's inverter or an LM13700's OTA with nothing on it (D-180): a CMOS input
    left floating draws current and can oscillate, so it's tied to a supply; an OTA's
    inputs go to ground and its bias current is left off."""
    for p in ctx.circuit.parts:
        if not isinstance(p, Inverter | Ota) or p.ref not in ctx.spare:
            continue
        pos, neg = ctx.supply(p)
        if isinstance(p, Inverter):
            how = (f"Tie its input ({_pin(ctx, p, 'in')}) to {neg} (or {pos}), and leave its "
                   f"output ({_pin(ctx, p, 'out')}) unconnected.")  # fmt: skip
        else:
            how = (f"Wire its + and − inputs ({_pin(ctx, p, '+')}, {_pin(ctx, p, '-')}) to "
                   f"{neg}, and leave its bias input ({_pin(ctx, p, 'iabc')}) unconnected so it "
                   "draws no current.")  # fmt: skip
        n = len(halves(ctx.circuit, p))
        yield Hit(
            p.ref,
            values={"chip": p.chip, "model": p.model, "units": f"{n} {_UNIT_NOUNS[p.type]}",
                    "how": how},
        )  # fmt: skip


@check("topology")
def opamp_pin_not_simulated(ctx: Context) -> Iterator[Hit]:
    """A wired pin the model has no node for: offset null, no-connect, or compensation on
    a model without it (D-140). The simulation leaves it open."""
    for p in ctx.parts(Opamp):
        simulated = set(ctx.model(p).info.pins)
        for pin in (*COMP_PINS, *EXTRA_PINS):
            if pin in simulated or pin not in pin_offsets(p):
                continue
            net = ctx.net(p, pin)
            if len(ctx.n.members[net]) > 1 or any(lb.net == net for lb in ctx.circuit.labels):
                yield Hit(
                    p.ref,
                    (net,),
                    {"pin": _pin(ctx, p, pin), "role": OPAMP_PIN_ROLES[pin], "model": p.model},
                )


@check("topology")
def opamp_inputs_tied(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Opamp):
        if ctx.net(p, "+") == ctx.net(p, "-"):
            yield Hit(p.ref, (ctx.net(p, "+"),))


@check("topology")
def transistor_pins_shorted(ctx: Context) -> Iterator[Hit]:
    # Base to collector is a diode-connected transistor and gate to source a JFET current
    # source: both deliberate, so not flagged.
    # A MOSFET's gate to drain is a diode-connected one, also deliberate.
    pairs = {"bjt": (("C", "E"), ("B", "E")), "jfet": (("D", "S"),), "mosfet": (("D", "S"),)}
    for p in [
        p for p in ctx.circuit.parts if isinstance(p, Bjt | Jfet | Mosfet) and ctx.simulated(p)
    ]:
        for a, b in pairs[p.type]:
            if ctx.net(p, a) == ctx.net(p, b):
                yield Hit(p.ref, (ctx.net(p, a),), {"pins": f"{a} and {b}"})


@check("topology")
def part_shorted(ctx: Context) -> Iterator[Hit]:
    for p in [
        q
        for q in ctx.circuit.parts
        if isinstance(q, Resistor | Capacitor | Inductor | Diode | Led | Pot | Trimmer)
    ]:
        found = {ctx.net(p, pin) for pin in pin_offsets(p)}
        if len(found) == 1:
            yield Hit(p.ref, tuple(found))


@check("topology")
def led_no_resistor(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Led):
        a, k = ctx.net(p, "A"), ctx.net(p, "K")
        if a != k and a in ctx.hard and k in ctx.hard:
            yield Hit(p.ref, (a, k), {"anode": a, "cathode": k})


@check("topology")
def diode_across_supply(ctx: Context) -> Iterator[Hit]:
    known = ctx.known_volts
    for p in ctx.parts(Diode):
        a, k = ctx.net(p, "A"), ctx.net(p, "K")
        if a in known and k in known and known[a] > known[k]:
            yield Hit(p.ref, (a, k), {"anode": a, "cathode": k})


@check("topology")
def dc_source_on_supply(ctx: Context) -> Iterator[Hit]:
    """V+ and V- come from the Power menu only (D-091): a DC source on one fights it."""
    rails = ctx.circuit.power.rails
    for p in ctx.parts(VSource):
        on = [net for pin in ("+", "-") if (net := ctx.net(p, pin)) in rails]
        if on:
            yield Hit(p.ref, tuple(on), {"net": on[0]})


def _bulk_to_ground(ctx: Context, net: str) -> bool:
    """A capacitor big enough to hold a supply up (`graph.AC_GROUND_FARADS`) from `net`
    to ground."""
    for p in ctx.parts(Capacitor):
        ends = {ctx.net(p, "1"), ctx.net(p, "2")}
        if ends == {net, GROUND} and parse_value(p.value) >= graph.AC_GROUND_FARADS:
            return True
    return False


@check("topology")
def pump_in_audio_band(ctx: Context) -> Iterator[Hit]:
    """A charge pump's ripple is at its pump frequency: below 20 kHz it can whine."""
    for p in ctx.parts(ChargePump):
        wiring = pump_wiring(ctx.circuit, ctx.n, p)
        try:
            freq = pump_frequency(p, ctx.models, wiring.boost)
        except NetlistError:
            continue  # not a pump chip: the run says so
        if freq < AUDIO_TOP:
            yield Hit(p.ref, tuple(wiring.outputs), {"freq": format_quantity(freq, "Hz")})


@check("topology")
def pump_no_reservoir(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(ChargePump):
        for out in pump_wiring(ctx.circuit, ctx.n, p).outputs:
            if not _bulk_to_ground(ctx, out):
                yield Hit(p.ref, (out,), {"net": out})


@check("topology")
def supply_no_bulk(ctx: Context) -> Iterator[Hit]:
    """Each supply an IC runs from (op-amps' supplies, pumps' inputs) has a bulk cap to
    ground. A block is a fragment, pasted into a circuit that has its own."""
    if ctx.circuit.template:
        return
    users: dict[str, str] = {}
    for p in ctx.circuit.parts:
        if isinstance(p, Opamp):
            nets = list(ctx.supply(p))
        elif isinstance(p, ChargePump):
            nets = [ctx.net(p, "in")]
        else:
            continue
        for net in nets:
            users.setdefault(net, p.ref)
    for net, ref in users.items():
        known = net in ctx.circuit.power.rails or ctx.n.members.get(net)
        if net != GROUND and known and not _bulk_to_ground(ctx, net):
            yield Hit(ref, (net,), {"net": net})


def _supply_path(ctx: Context, net: str) -> Iterator[tuple[Diode | Inductor | Resistor, str]]:
    """The parts a supply passes through from `net` (diodes, inductors, resistors under
    `SUPPLY_PATH_OHMS`) and the net at each one's other end."""
    path: list[Diode | Inductor | Resistor] = [
        *ctx.parts(Diode), *ctx.parts(Inductor), *ctx.parts(Resistor)
    ]  # fmt: skip
    for p in path:
        if isinstance(p, Resistor) and parse_value(p.value) > SUPPLY_PATH_OHMS:
            continue
        ends = [ctx.net(p, pin) for pin in (("A", "K") if isinstance(p, Diode) else ("1", "2"))]
        if net in ends and ends[0] != ends[1]:
            yield p, ends[1] if ends[0] == net else ends[0]


@check("operating_point")
def supply_sags(ctx: Context) -> Iterator[Hit]:
    """Every net on a rail's way in holds at least half of it (D-238): a protection diode
    fitted backwards starves a circuit no op-amp rule would catch (the Dyna Comp's)."""
    rails = ctx.circuit.power.rails
    for rail, rail_volts in rails.items():
        if not rail_volts or rail not in ctx.n.members:
            continue
        paths: dict[str, tuple[str, ...]] = {rail: ()}
        queue = [rail]
        while queue:
            net = queue.pop(0)
            for p, other in _supply_path(ctx, net):
                if other in paths or other == GROUND or other in rails:
                    continue
                paths[other] = (*paths[net], p.ref)
                queue.append(other)
        sagged = [n for n in paths if n != rail and ctx.volts(n) / rail_volts < SAG_SHARE]
        if sagged:
            named = {lb.net for lb in ctx.circuit.labels}
            # the circuit's own name for it (VA) if it has one, else the first net it's lost by
            net = min(sagged, key=lambda n: (n not in named, len(paths[n])))
            parts = paths[net]
            yield Hit(parts[0], (net,), refs=parts[1:], values={
                "net": net, "volts": _v(ctx.volts(net)), "rail": rail,
                "rail_volts": _v(rail_volts), "parts": listing(list(parts), 9),
            })  # fmt: skip


def cap_advice(farads: float) -> str:
    """Which kind to use instead, by value (the capacitor guide, D-095)."""
    if farads <= C0G_TOP:
        return "a C0G (NP0) ceramic or a film capacitor"
    if farads < graph.AC_GROUND_FARADS:
        return "a film capacitor"
    return "a film capacitor, or an electrolytic for big values"


@check("topology")
def cap_kind_signal_path(ctx: Context) -> Iterator[Hit]:
    """A general-purpose ceramic or a tantalum with a pin on a signal net. Caps between
    quiet nets (a supply, or a bias net another big cap holds still, to ground) are
    decoupling: left alone. The cap itself doesn't count, or every big one would make
    its own net quiet (a tone or bypass cap)."""
    for p in ctx.parts(Capacitor):
        if p.kind not in ("ceramic", "tantalum"):
            continue
        quiet = ctx.supplies | graph.ac_grounds(ctx.circuit, ctx.n, ctx.supplies, skip=p.ref)
        signal = tuple(n for n in (ctx.net(p, "1"), ctx.net(p, "2")) if n not in quiet)
        if signal:
            kind = "general-purpose ceramic" if p.kind == "ceramic" else p.kind
            yield Hit(p.ref, signal, {"kind": kind, "advice": cap_advice(parse_value(p.value))})


@check("topology")
def rail_shorted(ctx: Context) -> Iterator[Hit]:
    known = ctx.known_volts

    def shorts(x: str, y: str) -> bool:
        return x in known and y in known and known[x] != known[y]

    for p in ctx.parts(Resistor):
        a, b = ctx.net(p, "1"), ctx.net(p, "2")
        if parse_value(p.value) <= SHORT_OHMS and shorts(a, b):
            yield Hit(p.ref, (a, b), {"a": a, "b": b})
    for s in ctx.parts(Switch):
        for c, t in closed_contacts(s):
            a, b = ctx.net(s, c), ctx.net(s, t)
            if shorts(a, b):
                yield Hit(s.ref, (a, b), {"a": a, "b": b})


@check("topology")
def switch_pulldown_missing(ctx: Context) -> Iterator[Hit]:
    """A net that only a switch ties to a DC voltage floats in the switch's other
    positions; a capacitor on it charges up and pops when it's switched back in."""
    caps = {ctx.net(c, pin) for c in ctx.parts(Capacitor) for pin in ("1", "2")}
    for s in ctx.parts(Switch):
        others = [  # the whole switch out: all its poles (D-143)
            p for p in ctx.circuit.parts if not (isinstance(p, Switch) and p.switch == s.switch)
        ]
        without = ctx.circuit.model_copy(update={"parts": others})
        edges = graph.bias_edges(without, ctx.n)
        joined = graph.groups(ctx.n.members, edges)
        anchors = graph.bias_anchors(without, ctx.n)
        pins = sorted({ctx.net(s, pin) for pin in pin_offsets(s)})
        for net in pins:
            if net in caps and not joined[net] & anchors:
                yield Hit(s.ref, (net,), {"net": net})


@check("topology")
def bias_target_unknown(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Trimmer):
        if p.bias_target is None:
            continue
        try:
            ctx.n.resolve(p.bias_target.node)
        except ConnectivityError:
            yield Hit(p.ref, values={"node": p.bias_target.node})


@check("topology")
def signal_path_broken(ctx: Context) -> Iterator[Hit]:
    probes = probe_nets(ctx.circuit, ctx.n)
    if probes.input is None or probes.output is None:
        return
    edges = graph.signal_edges(ctx.circuit, ctx.n)
    if probes.output not in graph.reachable(probes.input, edges, blocked=ctx.quiet):
        yield Hit(
            nets=(probes.input, probes.output),
            values={"input": probes.input, "output": probes.output},
        )


@check("topology")
def no_guitar_input(ctx: Context) -> Iterator[Hit]:
    if not ctx.circuit.template and not ctx.parts(Guitar):
        yield Hit()


@check("topology")
def no_amp_output(ctx: Context) -> Iterator[Hit]:
    if not ctx.circuit.template and not ctx.parts(AmpInput):
        yield Hit()


@check("topology")
def battery_cable_out(ctx: Context) -> Iterator[Hit]:
    """The battery alone powers the circuit, its - goes to a stereo jack's ring, and that
    jack's cable is out: the ring is open, so the battery is cut off (D-185)."""
    battery = on_battery(ctx.circuit)
    if battery is None:
        return
    minus = ctx.net(battery, "-")
    for j in ctx.parts(Jack):
        if j.stereo and not j.plugged and ctx.net(j, "R") == minus:
            yield Hit(j.ref, (minus,), {"battery": battery.ref})


@check("topology")
def battery_beside_adapter(ctx: Context) -> Iterator[Hit]:
    """The battery's + is on a supply rail, not the DC jack's battery lug, so a DC plug
    doesn't cut it off: it stays connected beside the adapter (D-185)."""
    battery = next(iter(ctx.parts(Battery)), None)
    jack = next(iter(ctx.parts(DcJack)), None)
    if battery is None or jack is None:
        return
    plus = ctx.net(battery, "+")
    if plus in ctx.circuit.power.rails and plus != ctx.net(jack, "sw"):
        yield Hit(battery.ref, (plus,), {"jack": jack.ref, "net": plus})


# ---- operating point ----------------------------------------------------------------


def _saturated(
    ctx: Context, kind: type[Part] | tuple[type[Part], ...], state: str
) -> Iterator[Hit]:
    for s in ctx.saturated:
        part = ctx.circuit.part(s.ref)
        if isinstance(part, kind) and s.state == state:
            yield Hit(s.ref, values={"detail": s.message})


@check("operating_point")
def opamp_railed(ctx: Context) -> Iterator[Hit]:
    for hit in _saturated(ctx, (Opamp, Ota), "railed"):  # an OTA too (D-238)
        part = ctx.circuit.part(str(hit.ref))
        yield Hit(hit.ref, (ctx.net(part, "out"),), {"volts": _v(ctx.v(part, "out"))})


@check("operating_point")
def bjt_saturated(ctx: Context) -> Iterator[Hit]:
    for hit in _saturated(ctx, Bjt, "saturated"):
        part = ctx.circuit.part(str(hit.ref))
        sign = 1.0 if ctx.model(part).polarity == "n" else -1.0  # type: ignore[arg-type]
        vce = sign * (ctx.v(part, "C") - ctx.v(part, "E"))
        yield Hit(hit.ref, values={"vce": _v(vce)})


@check("operating_point")
def bjt_cut_off(ctx: Context) -> Iterator[Hit]:
    yield from _saturated(ctx, Bjt, "cut off")


@check("operating_point")
def jfet_cut_off(ctx: Context) -> Iterator[Hit]:
    yield from _saturated(ctx, Jfet, "cut off")


@check("operating_point")
def jfet_ohmic(ctx: Context) -> Iterator[Hit]:
    for hit in _saturated(ctx, Jfet, "triode"):
        part = ctx.circuit.part(str(hit.ref))
        yield Hit(hit.ref, values={"vds": _v(abs(ctx.v(part, "D") - ctx.v(part, "S")))})


def _jfet_sign(ctx: Context, p: Jfet) -> float | None:
    polarity = ctx.model(p).polarity
    return None if polarity is None else (1.0 if polarity == "n" else -1.0)


@check("operating_point")
def jfet_vds_low(ctx: Context) -> Iterator[Hit]:
    flagged = {s.ref for s in ctx.saturated}
    for p in ctx.parts(Jfet):
        sign = _jfet_sign(ctx, p)
        if sign is None or p.ref in flagged:
            continue
        vds = sign * (ctx.v(p, "D") - ctx.v(p, "S"))
        if vds < JFET_VDS_LOW:
            yield Hit(p.ref, (ctx.net(p, "D"),), {"vds": _v(vds), "limit": _v(JFET_VDS_LOW)})


@check("operating_point")
def jfet_gate_forward(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Jfet):
        sign = _jfet_sign(ctx, p)
        if sign is None:
            continue
        vgs = sign * (ctx.v(p, "G") - ctx.v(p, "S"))
        if vgs > GATE_FORWARD:
            yield Hit(p.ref, (ctx.net(p, "G"),), {"vgs": _v(vgs)})


def _supply_volts(ctx: Context, p: Opamp | Ota) -> tuple[float, float]:
    pos, neg = ctx.supply(p)
    return ctx.volts(pos), ctx.volts(neg)


@check("operating_point")
def opamp_input_common_mode(ctx: Context) -> Iterator[Hit]:
    """Op-amps' and OTAs' inputs (D-238); a spare OTA's grounded inputs are fine."""
    chips: list[Opamp | Ota] = [*ctx.parts(Opamp), *ctx.parts(Ota)]
    for p in chips:
        if spare_ota(ctx.circuit, ctx.n, p):
            continue
        high, low = _supply_volts(ctx, p)
        limits = opamp_input_limits(ctx.model(p), high, low)
        if limits is None:
            continue
        span = f"the {_v(limits[0])} to {_v(limits[1])} the {p.model} handles on this supply"
        if limits[0] > limits[1]:  # a supply too low for the chip (D-238)
            span = f"any range: the {p.model} has none on {_v(high - low)} of supply"
        for pin in ("+", "-"):
            v = ctx.v(p, pin)
            if not limits[0] <= v <= limits[1]:
                yield Hit(
                    p.ref,
                    (ctx.net(p, pin),),
                    {"input": _input_name(pin), "volts": _v(v), "range": span},
                )


@check("operating_point")
def opamp_supply_over_max(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Opamp):
        high, low = _supply_volts(ctx, p)
        limit = ctx.model(p).info.ratings.get("vs_max")
        if limit is not None and high - low > limit:
            yield Hit(p.ref, values={"volts": _v(high - low), "limit": _v(limit), "model": p.model})


@check("topology")
def opamp_supply_reversed(ctx: Context) -> Iterator[Hit]:
    """From the supply voltages the file states (ngspice can't solve a reversed op-amp)."""
    known = ctx.known_volts
    for p in _power_holders(ctx):
        pos, neg = ctx.net(p, "V+"), ctx.net(p, "V-")
        if pos not in known or neg not in known:
            continue
        high, low = known[pos], known[neg]
        if high <= low:
            yield Hit(p.ref, values={"pos": pos, "neg": neg, "high": _v(high), "low": _v(low)})


def _over(value: float, limit: float | None) -> bool:
    return limit is not None and value > limit


@check("operating_point")
def bjt_over_vce(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Bjt):
        vce = abs(ctx.v(p, "C") - ctx.v(p, "E"))
        limit = ctx.model(p).info.ratings.get("vceo")
        if _over(vce, limit):
            yield Hit(p.ref, values={"vce": _v(vce), "limit": _v(limit or 0), "model": p.model})


@check("operating_point")
def bjt_over_current(ctx: Context) -> Iterator[Hit]:
    assert ctx.op is not None
    for p in ctx.parts(Bjt):
        ic = abs(ctx.op.currents.get(f"{p.ref}.ic", 0.0))
        limit = ctx.model(p).info.ratings.get("ic")
        if _over(ic, limit):
            yield Hit(
                p.ref,
                values={
                    "current": format_quantity(ic, "A"),
                    "limit": format_quantity(limit or 0, "A"),
                    "model": p.model,
                },
            )


@check("operating_point")
def diode_over_current(ctx: Context) -> Iterator[Hit]:
    assert ctx.op is not None
    for p in [p for p in ctx.circuit.parts if isinstance(p, Diode | Led) and ctx.simulated(p)]:
        current = ctx.op.currents.get(f"{p.ref}.id", 0.0)
        limit = ctx.model(p).info.ratings.get("if_avg")
        if _over(current, limit):
            yield Hit(
                p.ref,
                values={
                    "current": format_quantity(current, "A"),
                    "limit": format_quantity(limit or 0, "A"),
                    "model": p.model,
                },
            )


@check("operating_point")
def diode_over_reverse(ctx: Context) -> Iterator[Hit]:
    for p in [p for p in ctx.circuit.parts if isinstance(p, Diode | Led) and ctx.simulated(p)]:
        reverse = ctx.v(p, "K") - ctx.v(p, "A")
        limit = ctx.model(p).info.ratings.get("vr_max")
        if _over(reverse, limit):
            yield Hit(
                p.ref, values={"volts": _v(reverse), "limit": _v(limit or 0), "model": p.model}
            )


@check("operating_point")
def resistor_over_power(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Resistor):
        across = ctx.v(p, "1") - ctx.v(p, "2")
        power = across * across / max(parse_value(p.value), MIN_RESISTANCE)
        rating = p.rating_w or DEFAULT_RATING_W
        if power > rating:
            given = "its" if p.rating_w else "the usual"
            yield Hit(
                p.ref,
                values={
                    "power": format_quantity(power, "W"),
                    "rating": f"{given} {format_quantity(rating, 'W')} rating",
                },
            )


@check("operating_point")
def pump_supply_over_max(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(ChargePump):
        across = ctx.v(p, "in") - ctx.v(p, "gnd")
        limit = ctx.model(p).info.ratings.get("vs_max")
        if limit is not None and across > limit:
            yield Hit(p.ref, values={"volts": _v(across), "limit": _v(limit), "model": p.model})


@check("operating_point")
def regulator_input_over_max(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Regulator):
        across = ctx.v(p, "in") - ctx.v(p, "gnd")
        limit = ctx.model(p).info.ratings.get("vi_max")
        if limit is not None and across > limit:
            yield Hit(p.ref, values={"volts": _v(across), "limit": _v(limit), "model": p.model})


@check("operating_point")
def regulator_dropout(ctx: Context) -> Iterator[Hit]:
    """Less than its output plus its dropout across a regulator: it can't hold its output."""
    for p in ctx.parts(Regulator):
        params = ctx.model(p).info.params
        across = ctx.v(p, "in") - ctx.v(p, "gnd")
        needs = params["v_out"] + params["v_dropout"]
        if across < needs:
            values = {"volts": _v(across), "needs": _v(needs), "model": p.model,
                      "vout": _v(params["v_out"])}  # fmt: skip
            yield Hit(p.ref, (ctx.net(p, "in"), ctx.net(p, "out")), values)


@check("operating_point")
def cap_over_voltage(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Capacitor):
        across = abs(ctx.v(p, "1") - ctx.v(p, "2"))
        if _over(across, p.rating_v):
            yield Hit(p.ref, values={"volts": _v(across), "limit": _v(p.rating_v or 0)})


@check("operating_point")
def electrolytic_reversed(ctx: Context) -> Iterator[Hit]:
    for p in ctx.parts(Capacitor):
        if p.kind not in POLARISED:
            continue
        across = ctx.v(p, "1") - ctx.v(p, "2")
        if across < -REVERSE_LIMIT:
            yield Hit(
                p.ref, (ctx.net(p, "1"), ctx.net(p, "2")), {"volts": _v(-across), "kind": p.kind}
            )


@check("operating_point")
def output_dc(ctx: Context) -> Iterator[Hit]:
    out = probe_nets(ctx.circuit, ctx.n).output
    if out is not None and out in (ctx.op.voltages if ctx.op else {}):
        v = ctx.volts(out)
        if abs(v) > OUTPUT_DC_LIMIT:
            yield Hit(nets=(out,), values={"net": out, "volts": _v(v)})


# ---- build checks (9d1, D-203): what the parts list needs to say what to buy -----------


def _refs(parts: list[Part]) -> tuple[str, ...]:
    return tuple(sorted((p.ref for p in parts), key=ref_key))


@check("topology")
def cap_no_kind(ctx: Context) -> Iterator[Hit]:
    """Capacitors with no type: one problem for them all."""
    found = _refs([p for p in ctx.circuit.parts if isinstance(p, Capacitor) and p.kind is None])
    if found:
        which = f"{found[0]} has" if len(found) == 1 else f"{listing(list(found))} have"
        yield Hit(found[0], refs=found[1:], values={"which": which})


def cap_rating_advice(volts: float) -> str:
    """The smallest rating sold with `volts` inside `CAP_MARGIN` of it."""
    rating = next((r for r in CAP_RATINGS if volts <= CAP_MARGIN * r), None)
    if rating is None:
        return f"one rated well above {format_quantity(volts, 'V')}"
    return f"{format_quantity(rating, 'V')} or more"


@check("topology")
def cap_no_rating(ctx: Context) -> Iterator[Hit]:
    """Electrolytics and tantalums with no voltage rating (the advice from the highest
    supply: no capacitor sees more without a charge pump, which its own rule checks)."""
    found = _refs(
        [p for p in ctx.circuit.parts
         if isinstance(p, Capacitor) and p.kind in POLARISED and p.rating_v is None]
    )  # fmt: skip
    if found:
        top = max((abs(v) for v in supply_volts(ctx.circuit).values()), default=9.0)
        which = f"{found[0]} has" if len(found) == 1 else f"{listing(list(found))} have"
        advice = cap_rating_advice(top)
        yield Hit(found[0], refs=found[1:], values={"which": which, "advice": advice})


# parts bought by model: a package with pin numbers says how they go in the board
PACKAGED = (Diode, Led, Jfet, Bjt, Mosfet, *CHIP_UNITS, ChargePump)


@check("topology")
def part_no_package(ctx: Context) -> Iterator[Hit]:
    """A transistor, diode or chip whose model has no package (pin numbers): one problem
    per model, naming every part on it, a chip's units included."""
    by_model: dict[str, list[Part]] = {}
    for p in ctx.circuit.parts:
        model = getattr(p, "model", None)
        if (
            isinstance(p, PACKAGED)
            and model
            and model in ctx.models
            and ctx.models.get(model).info.package is None
        ):
            by_model.setdefault(model, []).append(p)
    for model, parts in sorted(by_model.items()):
        refs = _refs(parts)
        yield Hit(refs[0], refs=refs[1:], values={"model": model, "parts": listing(list(refs))})


@check("topology")
def switch_custom(ctx: Context) -> Iterator[Hit]:
    """A custom switch (its own contacts) names no part to buy: once per switch."""
    seen: set[str] = set()
    for p in ctx.circuit.parts:
        if isinstance(p, Switch) and p.kind == CUSTOM and p.switch not in seen:
            seen.add(p.switch)
            yield Hit(p.ref, values={"switch": p.switch})


@check("topology")
def enclosure_not_chosen(ctx: Context) -> Iterator[Hit]:
    """A circuit (not a block) with no enclosure: the parts list can't name one (D-204)."""
    if ctx.circuit.enclosure is None and not ctx.circuit.template:
        yield Hit()


@check("operating_point")
def cap_rating_close(ctx: Context) -> Iterator[Hit]:
    """Within its rating but with less room than `CAP_MARGIN` leaves (over it,
    cap-over-voltage says so)."""
    for p in ctx.parts(Capacitor):
        across = abs(ctx.v(p, "1") - ctx.v(p, "2"))
        if p.rating_v is not None and CAP_MARGIN * p.rating_v < across <= p.rating_v:
            advice = cap_rating_advice(across)
            values = {"volts": _v(across), "limit": _v(p.rating_v), "advice": advice}
            yield Hit(p.ref, values=values)


@check("operating_point")
def resistor_power_close(ctx: Context) -> Iterator[Hit]:
    """Within its rating (or the usual ¼ W) but past `POWER_MARGIN` of it."""
    for p in ctx.parts(Resistor):
        across = ctx.v(p, "1") - ctx.v(p, "2")
        power = across * across / max(parse_value(p.value), MIN_RESISTANCE)
        rating = p.rating_w or DEFAULT_RATING_W
        if POWER_MARGIN * rating < power <= rating:
            given = "its" if p.rating_w else "the usual"
            yield Hit(
                p.ref,
                values={
                    "power": format_quantity(power, "W"),
                    "rating": f"{given} {format_quantity(rating, 'W')} rating",
                    "share": f"{power / rating:.0%}",
                },
            )


# ---- failed runs --------------------------------------------------------------------


def _log_has(ctx: Context, *phrases: str) -> bool:
    """The failed run's log mentions a phrase, and no singular matrix: a floating net makes
    ngspice's later steps fail too, and sim_no_dc_path already says why."""
    log = ctx.error.log if isinstance(ctx.error, SimError) else []
    if singular_nodes(log):
        return False
    return any(phrase in line.lower() for line in log for phrase in phrases)


@check("sim_error")
def sim_no_dc_path(ctx: Context) -> Iterator[Hit]:
    if not isinstance(ctx.error, SimError):
        return
    by_node = {node.lower(): net for node, net in ctx.nodes.items()}
    found = [by_node[n.lower()] for n in singular_nodes(ctx.error.log) if n.lower() in by_node]
    if found:
        which = f"net {found[0]} has" if len(found) == 1 else f"nets {listing(found)} have"
        yield Hit(nets=tuple(found), values={"which": which})


@check("sim_error")
def sim_timestep_too_small(ctx: Context) -> Iterator[Hit]:
    if _log_has(ctx, "timestep too small"):
        yield Hit()


@check("sim_error")
def sim_no_convergence(ctx: Context) -> Iterator[Hit]:
    if _log_has(
        ctx,
        "gmin stepping failed",
        "source stepping failed",
        "iteration limit reached",
        "no convergence",
    ):
        yield Hit()


@check("sim_error")
def bias_unreachable(ctx: Context) -> Iterator[Hit]:
    if isinstance(ctx.error, BiasError):
        yield Hit(values={"detail": str(ctx.error)})


@check("sim_error")
def sim_failed(ctx: Context) -> Iterator[Hit]:
    if ctx.error is not None:
        yield Hit(values={"detail": str(ctx.error)})
