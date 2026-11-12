"""Which nets conduct to which, three ways, for the topology rules (D-077).

- **spice**: what ngspice sees at DC. Every resistor, pot, switch contact (open ones are
  1 TΩ in the netlist), diode and transistor junction is a path (ngspice puts a tiny
  conductance across junctions), and an op-amp joins all its pins and supplies. A net
  outside ground's group makes ngspice fail with "singular matrix".
- **bias**: what really sets a DC voltage: resistors, pots, closed switch contacts, the
  guitar and amp, sources. A net is *biased* when its group holds ground, a supply, an
  op-amp output or a transistor's collector, emitter, drain or source.
- A block's (template's) ports count as driven from outside.
- **signal**: where a signal can travel: through every part but sources, not through
  ground or a supply.
"""

from collections import defaultdict
from collections.abc import Iterable

from solum.circuit.chips import left_out, supply_nets
from solum.circuit.connectivity import GROUND, Nets
from solum.circuit.parts import closed_contacts, pin_offsets, switch_contacts
from solum.circuit.pump import pump_wiring
from solum.circuit.schema import (
    AmpInput,
    Battery,
    Bjt,
    Capacitor,
    ChargePump,
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
from solum.circuit.supply import battery_of, live_rails
from solum.units import parse_value
from solum.view import rail_nets

Edge = tuple[str, str]
# A design choice (D-077): coupling caps in a signal path go between signal nets, while
# bias nets (VREF) and supply filters sit on caps of 1 µF or more to a supply.
AC_GROUND_FARADS = 1e-6


def _chain(nets: Nets, part: Part, pins: Iterable[str]) -> list[Edge]:
    """Every pair of the part's pins: a path may go between any two, even when one of
    them sits on a supply that a search won't cross (an emitter follower's collector)."""
    found = [nets.net_of(part.ref, pin) for pin in pins]
    return [(a, b) for i, a in enumerate(found) for b in found[i + 1 :]]


def _all_pins(nets: Nets, part: Part) -> list[Edge]:
    return _chain(nets, part, pin_offsets(part))


def _ports(circuit: Circuit) -> list[Edge]:
    """A block's ports are driven by whatever it's pasted into: count them as connected."""
    return [(net, GROUND) for net in circuit.ports.values()] if circuit.template else []


def spice_edges(circuit: Circuit, nets: Nets) -> list[Edge]:
    """DC paths as ngspice sees them (see the module doc)."""
    edges: list[Edge] = [(rail, GROUND) for rail in live_rails(circuit)]
    edges += _ports(circuit)
    skipped = left_out(circuit, nets)  # not simulated (D-140, D-165)
    for p in circuit.parts:
        if p.ref in skipped:
            continue
        match p:
            case Jack() if p.stereo:  # only its ring's contact to S, open or closed (D-185)
                edges.append((nets.net_of(p.ref, "R"), nets.net_of(p.ref, "S")))
            case Capacitor() | Jack() | PowerUnit():  # drawing only (D-174, D-179)
                pass
            case Opamp() | Inverter() | Ota():  # an output is driven from the supply
                pins = pin_offsets(p)
                outs = [nets.net_of(p.ref, pin) for pin in ("out", "bufout") if pin in pins]
                edges += _all_pins(nets, p)
                edges += [(out, s) for out in outs for s in supply_nets(circuit, nets, p)]
            case Guitar():
                edges += _guitar_edges(nets, p)
            case AmpInput():
                edges.append((nets.net_of(p.ref, "in"), GROUND))
            case Battery():
                edges += _battery_edges(circuit, nets, p)
            case Switch():  # a resistor per contact, open or closed: within its pole only
                edges += [(nets.net_of(p.ref, c), nets.net_of(p.ref, t))
                          for c, t in switch_contacts(p)]  # fmt: skip
            case DcJack():  # only its battery lug is in the netlist, a contact to the sleeve
                edges.append((nets.net_of(p.ref, "sw"), nets.net_of(p.ref, "+")))
            case _:
                edges += _all_pins(nets, p)
    return edges


def bias_edges(circuit: Circuit, nets: Nets) -> list[Edge]:
    """Paths that really set a DC voltage (see the module doc)."""
    edges: list[Edge] = [(rail, GROUND) for rail in live_rails(circuit)]
    edges += _ports(circuit)
    for p in circuit.parts:
        match p:
            case Resistor() | Pot() | Trimmer():
                edges += _all_pins(nets, p)
            case Switch():
                edges += [_chain(nets, p, pair)[0] for pair in closed_contacts(p)]
            case Guitar():
                edges += _guitar_edges(nets, p)
            case AmpInput():
                edges.append((nets.net_of(p.ref, "in"), GROUND))
            case VSource():
                edges += _all_pins(nets, p)
            case ChargePump():  # its pins, and the nets it drives through its parts (D-226)
                pins = [nets.net_of(p.ref, pin) for pin in pin_offsets(p)]
                edges += [(pins[0], n) for n in [*pins[1:], *pump_wiring(circuit, nets, p).driven]]
            case Regulator():  # its pins: the output is driven from the input (D-227)
                edges += _all_pins(nets, p)
            case Battery():
                edges += _battery_edges(circuit, nets, p)
            case DcJack() if not p.plugged:
                edges.append((nets.net_of(p.ref, "sw"), nets.net_of(p.ref, "+")))
            case Jack() if p.stereo and p.plugged:  # a cable's sleeve joins R and S
                edges.append((nets.net_of(p.ref, "R"), nets.net_of(p.ref, "S")))
    return edges


def _guitar_edges(nets: Nets, part: Guitar) -> list[Edge]:
    """The guitar's signal to ground and, on a stereo jack, its ring (the cable's sleeve
    joins it, D-143)."""
    edges = [(nets.net_of(part.ref, "out"), GROUND)]
    if part.stereo:
        edges.append((nets.net_of(part.ref, "ring"), GROUND))
    return edges


def _battery_edges(circuit: Circuit, nets: Nets, part: Battery) -> list[Edge]:
    """A battery's two pins, while it's connected (D-143, D-185); cut off by a DC plug
    through the jack's battery lug."""
    return _all_pins(nets, part) if battery_of(circuit, nets) is part else []


def bias_anchors(circuit: Circuit, nets: Nets) -> set[str]:
    """Nets whose DC voltage something drives: ground, supplies, live DC sources, op-amp
    outputs and transistors' collector/emitter/drain/source."""
    found = {GROUND, *live_rails(circuit)}
    driven = {
        "opamp": ("out",),
        "inverter": ("out",),
        # an OTA's own out is a current (its load sets the voltage); only a dual's half
        # has a buffer to drive one, so a single (CA3080) drives nothing
        "ota": ("bufout",),
        "bjt": ("C", "E"),
        "jfet": ("D", "S"),
        "mosfet": ("D", "S"),
        "regulator": ("out",),
    }
    for p in circuit.parts:
        for pin in driven.get(p.type, ()):
            if (p.ref, pin) in nets.by_pin:
                found.add(nets.net_of(p.ref, pin))
        if isinstance(p, ChargePump):
            found |= set(pump_wiring(circuit, nets, p).driven)
        if isinstance(p, VSource) or (isinstance(p, Battery) and battery_of(circuit, nets) is p):
            found |= {nets.net_of(p.ref, "+"), nets.net_of(p.ref, "-")}
    return found


def signal_edges(
    circuit: Circuit, nets: Nets, skip: str | None = None, active: bool = True, dc: bool = False
) -> list[Edge]:
    """Where a signal can pass (every part but sources, the guitar and the amp; an op-amp
    from each input to its output). `skip` leaves one part out; `active=False` leaves out
    op-amps and transistors (the passive paths around them: a stage's feedback); `dc=True`
    leaves out capacitors (where a steady voltage can pass)."""
    edges: list[Edge] = []
    for p in circuit.parts:
        if p.ref == skip or (dc and isinstance(p, Capacitor)):
            continue
        match p:
            case Opamp() | Ota() if active:
                out = nets.net_of(p.ref, "out")
                edges += [(nets.net_of(p.ref, pin), out) for pin in ("+", "-")]
                if "bufin" in pin_offsets(p):  # an LM13700's buffer (D-180)
                    edges.append((nets.net_of(p.ref, "bufin"), nets.net_of(p.ref, "bufout")))
            case Inverter() if active:
                edges.append((nets.net_of(p.ref, "in"), nets.net_of(p.ref, "out")))
            case Switch():
                edges += [_chain(nets, p, pair)[0] for pair in closed_contacts(p)]
            case Jfet() | Bjt() | Mosfet() if active:
                edges += _all_pins(nets, p)
            case Resistor() | Capacitor() | Inductor() | Pot() | Trimmer() | Diode() | Led():
                edges += _all_pins(nets, p)
    return edges


def ac_grounds(
    circuit: Circuit, nets: Nets, supplies: set[str], skip: str | None = None
) -> set[str]:
    """Nets a big capacitor (≥ `AC_GROUND_FARADS`) ties to a supply or ground: bias nets
    such as VREF, which carry no signal. A signal search must not pass through them.
    `skip` leaves one capacitor out (does a net stay quiet without it?)."""
    found = set()
    for p in circuit.parts:
        if p.ref == skip:
            continue
        if isinstance(p, Capacitor) and parse_value(p.value) >= AC_GROUND_FARADS:
            a, b = nets.net_of(p.ref, "1"), nets.net_of(p.ref, "2")
            if a in supplies and b not in supplies:
                found.add(b)
            elif b in supplies and a not in supplies:
                found.add(a)
    return found


def groups(nets: Iterable[str], edges: Iterable[Edge]) -> dict[str, frozenset[str]]:
    """Net → the set of nets it's joined to through `edges` (itself included)."""
    parent: dict[str, str] = {}

    def find(n: str) -> str:
        parent.setdefault(n, n)
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for n in nets:
        find(n)
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    members: dict[str, set[str]] = defaultdict(set)
    for n in list(parent):
        members[find(n)].add(n)
    return {n: frozenset(members[find(n)]) for n in parent}


def reachable(
    start: str, edges: Iterable[Edge], blocked: Iterable[str] = (), directed: bool = False
) -> set[str]:
    """Nets reachable from `start` along `edges`, never passing through a `blocked` net
    (a blocked net can be reached but not crossed). `directed=True` follows each edge
    from its first net to its second only."""
    return set(distances(start, edges, blocked, directed))


def distances(
    start: str, edges: Iterable[Edge], blocked: Iterable[str] = (), directed: bool = False
) -> dict[str, int]:
    """Each net reachable from `start` (as `reachable`) → the fewest edges to it: how far
    along the signal path it is (Phase 8c's signal order)."""
    stop = set(blocked)
    adjacent: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adjacent[a].add(b)
        if not directed:
            adjacent[b].add(a)
    found, frontier = {start: 0}, [start]
    while frontier:
        nxt: list[str] = []
        for here in frontier:
            if here in stop and here != start:
                continue
            for n in sorted(adjacent[here]):
                if n not in found:
                    found[n] = found[here] + 1
                    nxt.append(n)
        frontier = nxt
    return found


def one_way_outputs(circuit: Circuit, nets: Nets, edges: Iterable[Edge], skip: str) -> list[Edge]:
    """`edges` as one-way arcs (for `reachable(directed=True)`) where an op-amp's output
    is driven, every op-amp's but `skip`'s: a path may reach an output through the op-amp
    and leave it through a part, but not enter it through a part and pass on, since the
    op-amp holds that net's voltage itself (a feedback search, D-247)."""
    outs, driving = set(), set()
    for p in circuit.parts:
        if isinstance(p, Opamp) and p.ref != skip:
            out = nets.net_of(p.ref, "out")
            outs.add(out)
            driving |= {(nets.net_of(p.ref, pin), out) for pin in ("+", "-")}
    arcs: list[Edge] = []
    for a, b in edges:
        if (a, b) in driving or a in outs:
            arcs.append((a, b))
        elif b in outs:
            arcs.append((b, a))
        else:
            arcs += [(a, b), (b, a)]
    return arcs


def quiet_nets(circuit: Circuit, nets: Nets) -> set[str]:
    """Nets a signal can't pass through: supplies (`rail_nets`) and AC-grounded bias nets."""
    supplies = rail_nets(circuit, nets)
    return supplies | ac_grounds(circuit, nets, supplies)
