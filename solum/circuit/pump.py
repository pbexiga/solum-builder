"""A charge pump's wiring (D-226), the one owner: what its drawn parts make it.

The chip (TC1044S, ICL7660, LT1054: one 8-pin family) has its real pins: V+ 8 (`in`),
CAP+ 2, GND 3, CAP- 4 and VOUT 5 (`out`). As on a real board, the wiring decides what it
does (Microchip DS21348A, Figures 3, 8 and 9):
- an inverter: a flying cap from CAP+ to CAP-; VOUT is the negative output;
- a doubler: a pump cap from CAP+ to the junction of two diodes, D1 from V+ into the
  junction and D2 from it to the output; VOUT goes to ground;
- both at once (the Klon): the two together, VOUT the negative output.
Pin 1 wired to V+ is boost on a chip that has a boost pin (TC1044S: the oscillator runs
faster); on the others it does nothing (LT1054's FB/SHDN held high, ICL7660's no-connect).
Pins 6 and 7 may be wired as the sheet suggests; the model leaves them open.
A pump missing a part it needs doesn't pump: `problems` says what's missing.
"""

from dataclasses import dataclass

from solum.circuit.connectivity import Nets
from solum.circuit.schema import Capacitor, ChargePump, Circuit, Diode

PIN_NUMBERS = {"in": 8, "cap+": 2, "gnd": 3, "cap-": 4, "out": 5}  # the family's DIP-8
SPARE_PINS = ("1", "6", "7")  # boost or FB, LV or VREF, OSC: may be left open


@dataclass(frozen=True)
class Doubler:
    """A doubler's drawn parts: the pump cap from CAP+ to `junction`, D1 (`low`) from V+
    into it, D2 (`high`) from it to `out`."""

    cap: Capacitor
    low: Diode
    high: Diode
    junction: str
    out: str


@dataclass(frozen=True)
class PumpWiring:
    doubler: Doubler | None
    flying: Capacitor | None  # an inverter's flying cap, CAP+ to CAP-
    negative: str | None  # an inverter's output (VOUT's net)
    problems: tuple[str, ...]
    boost: bool = False  # pin 1 on V+: boost, on a chip that has a boost pin

    @property
    def mode(self) -> str:
        """`doubler`, `inverter`, `both`, or "" (it pumps nothing)."""
        if self.doubler and self.negative:
            return "both"
        return "doubler" if self.doubler else "inverter" if self.negative else ""

    @property
    def outputs(self) -> list[str]:
        """The nets it supplies: the doubled one, then the negative one."""
        return [n for n in (self.doubler and self.doubler.out, self.negative) if n]

    @property
    def driven(self) -> list[str]:
        """Every net the pump sets: its outputs and a doubler's diode junction."""
        return [*([self.doubler.junction] if self.doubler else []), *self.outputs]


def _other(nets: Nets, part: Capacitor | Diode, pin: str) -> str:
    return nets.net_of(part.ref, {"1": "2", "2": "1", "A": "K", "K": "A"}[pin])


def pump_wiring(circuit: Circuit, nets: Nets, pump: ChargePump) -> PumpWiring:
    """What `pump`'s drawn parts make it (see the module doc)."""
    pin = {name: nets.net_of(pump.ref, name) for name in PIN_NUMBERS}
    caps = [c for c in circuit.parts if isinstance(c, Capacitor)]
    on_cap = [(c, p) for c in caps for p in ("1", "2") if nets.net_of(c.ref, p) == pin["cap+"]]
    flying = next((c for c, p in on_cap if _other(nets, c, p) == pin["cap-"]), None)
    skip = {pin["cap-"], pin["cap+"], pin["gnd"], pin["in"]}
    pumped = next(((c, _other(nets, c, p)) for c, p in on_cap if _other(nets, c, p) not in skip),
                  None)  # fmt: skip
    problems: list[str] = []
    doubler = None
    if pumped:
        cap, junction = pumped
        diodes = [d for d in circuit.parts if isinstance(d, Diode)]
        low = next((d for d in diodes if nets.net_of(d.ref, "K") == junction
                    and nets.net_of(d.ref, "A") == pin["in"]), None)  # fmt: skip
        high = next((d for d in diodes if nets.net_of(d.ref, "A") == junction
                     and nets.net_of(d.ref, "K") not in (junction, pin["in"])), None)  # fmt: skip
        if low is None:
            problems.append(
                f"{pump.ref}'s doubler needs a diode from {pin['in']} into {cap.ref}: its anode "
                f"on {pin['in']}, its cathode where {cap.ref} meets the second diode."
            )
        if high is None:
            problems.append(
                f"{pump.ref}'s doubler needs a diode from {cap.ref} to its output: its anode "
                f"where {cap.ref} meets the first diode, its cathode on the output."
            )
        if low and high:
            doubler = Doubler(cap, low, high, junction, nets.net_of(high.ref, "K"))
    negative = None
    if flying is not None:
        if pin["out"] == pin["gnd"]:
            problems.append(
                f"{pump.ref}'s flying cap {flying.ref} pumps into ground: pin 5 (OUT) is the "
                "negative output. Give it its own net, with a reservoir cap to ground."
            )
        else:
            negative = pin["out"]
    if not pumped and flying is None:
        problems.append(
            f"{pump.ref} pumps nothing yet: draw a flying cap from pin 2 (CAP+) to pin 4 "
            "(CAP\u2212) for \u2212V+ on pin 5, or a cap from pin 2 to two diodes for 2 \u00d7 V+ "
            "(the charge-pump blocks show both)."
        )
    boost = nets.net_of(pump.ref, "1") == pin["in"]
    return PumpWiring(doubler, flying, negative, tuple(problems), boost)
