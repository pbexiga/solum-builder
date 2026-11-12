"""Build a circuit in code: the one circuit builder (tests and the app's test jigs use it).

Each part is placed on a grid and every connected pin gets a net label, so the result is
an ordinary circuit file (current schema) that goes through the real pipeline.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from pydantic import TypeAdapter

from solum.circuit.io import parse_circuit
from solum.circuit.parts import POWER_PINS, pin_offsets, pin_positions
from solum.circuit.schema import SCHEMA_VERSION, Circuit, Guitar, Part, id_from_name

GRID_X, GRID_Y, PER_ROW = 200, 400, 8
DEFAULT_SUPPLY = ("V+", "GND")  # a chip's power pins unless `supply` says otherwise
CHIP_TYPES = ("opamp", "inverter", "ota")  # parts with a chip's power (D-180)
_PART = TypeAdapter[Part](Part)


@dataclass
class CircuitBuilder:
    """`part("R1", "resistor", "in", "out", value="10k")` connects pins in the order the
    part type lists them (resistor 1, 2; bjt C, B, E; opamp +, -, out; ...). Use
    `pins={"1C": "a"}` for any pin by name, and None to leave a pin unconnected.
    Net "0" is ground. A chip's power pins (op-amp, inverter, OTA) go to
    `supply=(pos, neg)`, V+ and GND by default: a single's own, a chip of several's on its
    power unit, which `data()` adds (IC1C, IC1E, IC1G: D-179) from unit a's `supply` (or
    `pins` V+ and V-).
    """

    name: str = "test circuit"
    parts: list[dict[str, Any]] = field(default_factory=list)
    labels: list[dict[str, Any]] = field(default_factory=list)
    rails: dict[str, float] = field(default_factory=dict)
    probes: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)  # more file fields (template, wires…)
    power: dict[str, tuple[str, dict[str, str | None]]] = field(default_factory=dict)

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> Self:
        """A builder from plain data, as rule fixtures write it (D-077):
        `{rails: {V+: 9}, probes: {in, out},
          parts: [{ref: R1, type: resistor, nets: [a, b], value: 10k}, ...]}`;
        `nets` and `pins` are `part`'s arguments; a charge pump with `supply` is `pump`'s
        (`{ref: U1, type: chargepump, supply: V+, double: V18, model: TC1044S}`, its parts
        after the others so their refs are free); any other key is a file field
        (`template`, `ports`, `wires`, `labels` added to the builder's own)."""
        data = dict(spec)
        b = cls(name=data.pop("name", "fixture"))
        for name, volts in data.pop("rails", {}).items():
            b.rail(name, volts)
        probes = data.pop("probes", {})
        b.probe(probes.get("in"), probes.get("out"))
        parts = data.pop("parts", [])
        wired = [p for p in parts if p["type"] == "chargepump" and "supply" in p]
        for p in [*(p for p in parts if p not in wired), *wired]:  # a pump's parts: free refs
            fields = dict(p)
            ref, kind = fields.pop("ref"), fields.pop("type")
            if p in wired:
                b.pump(ref, fields.pop("supply"), **fields)
            else:
                b.part(ref, kind, *fields.pop("nets", []), pins=fields.pop("pins", None), **fields)
        b.labels += data.pop("labels", [])
        b.extra = data
        return b

    def part(
        self,
        ref: str,
        type: str,
        *nets: str | None,
        pins: dict[str, str | None] | None = None,
        **fields: Any,
    ) -> Self:
        i = len(self.parts)
        pos = [GRID_X * (i % PER_ROW) + 100, GRID_Y * (i // PER_ROW) + 100]
        if type in CHIP_TYPES:
            supply = fields.pop("supply", DEFAULT_SUPPLY)
            power = dict(zip(POWER_PINS, supply, strict=True)) | {
                k: v for k, v in (pins or {}).items() if k in POWER_PINS
            }
            if fields.get("half") is None:  # a single's own power pins
                pins = power | (pins or {})
            else:  # the chip's power unit's (D-179), added by `data()`
                if fields["half"] == "a":
                    self.power[ref[:-1]] = (fields["model"], power)
                pins = {k: v for k, v in (pins or {}).items() if k not in POWER_PINS}
        data = {"ref": ref, "type": type, "pos": pos, **fields}
        model = _PART.validate_python(data)
        names = list(pin_offsets(model))
        if len(nets) > len(names):
            raise ValueError(f"{ref}: {len(nets)} nets for pins {names}")
        positions = pin_positions(model)
        for pin, net in (dict(zip(names, nets, strict=False)) | (pins or {})).items():
            if net is not None:
                label = "GND" if net in ("0", "GND") else net
                self.labels.append({"net": label, "pos": list(positions[pin])})
        self.parts.append(data)
        return self

    def pump(
        self,
        ref: str,
        supply: str,
        double: str | None = None,
        invert: str | None = None,
        cap: str = "10u",
        diode: str = "1N5817",
        **fields: Any,
    ) -> Self:
        """A charge pump wired as the datasheet's doubler onto `double`, inverter onto
        `invert`, or both (D-226): the chip, its pump cap and diodes, its flying cap, on
        the next free C and D refs. No reservoirs: add those as parts. `boost=True` wires
        pin 1 to `supply`, as a TC1044S's boost is wired."""

        def next_ref(prefix: str) -> str:
            taken = {p["ref"] for p in self.parts}
            return next(f"{prefix}{n}" for n in range(1, 1000) if f"{prefix}{n}" not in taken)

        fields.setdefault("model", "TC1044S")
        cp, cm = f"{ref}_cp", f"{ref}_cm"
        boost: dict[str, str | None] | None = {"1": supply} if fields.pop("boost", False) else None
        self.part(ref, "chargepump", supply, invert or "0", "0", cp, cm, pins=boost, **fields)
        if invert:
            self.part(next_ref("C"), "capacitor", cp, cm, value=cap, kind="electrolytic")
        if double:
            junction = f"{ref}_j"
            self.part(next_ref("C"), "capacitor", junction, cp, value=cap, kind="electrolytic")
            self.part(next_ref("D"), "diode", supply, junction, model=diode)
            self.part(next_ref("D"), "diode", junction, double, model=diode)
        return self

    def rail(self, name: str, volts: float) -> Self:
        self.rails[name] = volts
        return self

    def probe(self, inp: str | None = None, out: str | None = None) -> Self:
        if inp:
            self.probes["in"] = inp
        if out:
            self.probes["out"] = out
        return self

    def _power_units(self) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        """Each chip's power unit, after its last unit, with its pins' labels."""
        out: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for chip, (model, supply) in self.power.items():
            last = max(p["half"] for p in self.parts if p.get("half") and p["ref"][:-1] == chip)
            i = len(self.parts) + len(out)
            pos = [GRID_X * (i % PER_ROW) + 100, GRID_Y * (i // PER_ROW) + 100]
            data = {"ref": f"{chip}{chr(ord(last.upper()) + 1)}", "type": "powerunit",
                    "model": model, "pos": pos}  # fmt: skip
            positions = pin_positions(_PART.validate_python(data))
            labels = [{"net": "GND" if net in ("0", "GND") else net, "pos": list(positions[pin])}
                      for pin, net in supply.items() if net is not None]  # fmt: skip
            out.append((data, labels))
        return out

    def data(self) -> dict[str, Any]:
        units = self._power_units()
        return {
            "schema": SCHEMA_VERSION,
            "id": id_from_name(self.name, "test"),
            "name": self.name,
            "power": {"rails": dict(self.rails)},
            "parts": [dict(p) for p in self.parts] + [u for u, _ in units],
            "labels": [dict(lb) for lb in self.labels] + [lb for _, lbs in units for lb in lbs],
            "probes": dict(self.probes),
            **self.extra,
        }

    def build(self) -> Circuit:
        return parse_circuit(self.data())


def guitar_into(guitar: Guitar, load: str, rotation: float | None = None) -> Circuit:
    """The guitar alone, its pickup, cable and volume pot as they are (at `rotation`, if
    given), into a load of `load` ohms (an amp part, OUT) on net `in`: what a DI records
    (D-096), or the guitar with the pedal left out (D-241)."""
    fields = guitar.model_dump(include={"source", "pickup", "cable", "volume", "taper", "rotation"})
    if rotation is not None:
        fields["rotation"] = rotation
    return (
        CircuitBuilder("guitar")
        .part(guitar.ref, "guitar", "in", **fields)
        .part("OUT", "amp", "in", value=load)
        .build()
    )
