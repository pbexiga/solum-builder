"""Draw a circuit in code, with real wires: what an agent does in place of the editor
(D-314). Parts are placed by position, wires run pin to pin, labels name nets, and
`net_differences` compares the drawn connectivity with the netlist that was meant, so a
wire that touches the wrong pin is found before anyone opens the file.

`CircuitBuilder` (`build.py`) is the other way to make a circuit in code: no wires, a net
label on every pin. That suits tests; this is for a drawing a person will read.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from pydantic import TypeAdapter, ValidationError

from solum.circuit.connectivity import connect
from solum.circuit.io import parse_circuit
from solum.circuit.parts import pin_positions
from solum.circuit.schema import SCHEMA_VERSION, Circuit, Part, Point, id_from_name

_PART = TypeAdapter[Part](Part)
Place = str | tuple[int, int]  # a pin ("R1.2") or a point on the sheet


class DrawingError(ValueError):
    """A step of the drawing can't be done as written (plain English, says what to do)."""


@dataclass
class Drawing:
    """A sheet being drawn. `parts`, `wires`, `labels` and `texts` are the file's own
    lists, as plain data."""

    parts: list[dict[str, Any]] = field(default_factory=list)
    wires: list[dict[str, Any]] = field(default_factory=list)
    labels: list[dict[str, Any]] = field(default_factory=list)
    texts: list[dict[str, Any]] = field(default_factory=list)
    _placed: dict[str, Part] = field(default_factory=dict, repr=False)

    def part(self, ref: str, type_: str, pos: tuple[int, int], rot: int = 0, **fields: Any) -> None:
        """Place a part: `part("R1", "resistor", (100, 0), value="10k")`. `rot` turns it
        clockwise (90 puts a two-pin part's pin 1 on top). `fields` are the part type's
        own (`schema.py`): value, model, kind, taper, label, half…"""
        if ref in self._placed:
            raise DrawingError(f"{ref} is placed twice. Give one of them another ref.")
        data = {"ref": ref, "pos": list(pos), "type": type_, **fields}
        if rot:
            data["rot"] = rot
        try:
            self._placed[ref] = _PART.validate_python(data)
        except ValidationError as err:
            lines = "; ".join(e["msg"].removeprefix("Value error, ") for e in err.errors())
            raise DrawingError(f"{ref} ({type_}) can't be placed: {lines}") from None
        self.parts.append(data)

    def pins(self, ref: str) -> dict[str, Point]:
        """Where each of a placed part's pins is on the sheet."""
        if ref not in self._placed:
            raise DrawingError(f"There's no part {ref} yet. Place it before wiring to it.")
        return pin_positions(self._placed[ref])

    def pin(self, ref: str, name: str) -> Point:
        """Where one pin is: `pin("Q1", "B")`."""
        pins = self.pins(ref)
        if name not in pins:
            raise DrawingError(f"{ref} has no pin {name!r}. Its pins are {', '.join(pins)}.")
        return pins[name]

    def at(self, place: Place) -> Point:
        """A point on the sheet from a pin (`"R1.2"`) or a point."""
        if isinstance(place, str):
            ref, _, name = place.partition(".")
            return self.pin(ref, name)
        return (place[0], place[1])

    def wire(self, *path: Place) -> None:
        """A wire through the places given, one straight piece between each two:
        `wire("R1.2", (140, 0), "C1.1")`. A piece that isn't level or upright is refused."""
        for a, b in pairwise(self.at(p) for p in path):
            if a == b:
                raise DrawingError(f"A wire from {a} to itself: drop one of the two places.")
            if a[0] != b[0] and a[1] != b[1]:
                raise DrawingError(
                    f"The wire from {a} to {b} is diagonal. Add a corner: {(b[0], a[1])} "
                    f"or {(a[0], b[1])}."
                )
            self.wires.append({"from": list(a), "to": list(b)})

    def label(self, net: str, *places: Place, rot: int = 0) -> None:
        """Name the net at each place: `label("GND", "R2.2", "C1.2")`. The same name
        anywhere is the same net. `rot` turns a supply's or ground's symbol."""
        for place in places:
            entry: dict[str, Any] = {"net": net, "pos": list(self.at(place))}
            if rot:
                entry["rot"] = rot
            self.labels.append(entry)

    def stub(self, pin: str, net: str, dx: int = 0, dy: int = 0, *, rot: int = 0) -> None:
        """A short wire from a pin, `dx` across or `dy` down, with the net's label at its
        end: keeps a label clear of the part's own text."""
        a = self.at(pin)
        b = (a[0] + dx, a[1] + dy)
        self.wire(a, b)
        self.label(net, b, rot=rot)

    def text(self, pos: tuple[int, int], title: str = "", text: str = "") -> None:
        """A block of free text on the sheet, its top-left corner at `pos`."""
        self.texts.append({"title": title, "text": text, "pos": list(pos)})

    def circuit(self, name: str, **fields: Any) -> Circuit:
        """The drawing as a circuit of the current schema, validated like a loaded file
        (`CircuitError` in plain English). `fields` are any more of the file's own:
        `power={"rails": {"V+": 9.0}}`, `description`, `tags`, `probes`, `notes`…"""
        data: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "id": id_from_name(name),
            "name": name,
            "parts": self.parts,
            "wires": self.wires,
            "labels": self.labels,
            **fields,
        }
        if self.texts:
            data["texts"] = self.texts
        return parse_circuit(data)


def _names(pins: Iterable[str]) -> str:
    return ", ".join(sorted(pins))


def net_differences(circuit: Circuit, intended: Iterable[Iterable[str]]) -> list[str]:
    """How a circuit's drawn nets differ from the netlist meant, one plain line each; none
    when they agree. `intended` is a set of pins (`"R1.2"`, `"Q1.B"`) per net; a pin
    meant to be left open is a set of its own or left out. A pin left out must join
    nothing: it is reported when the drawing wires it to another pin."""
    nets = connect(circuit)
    drawn = {f"{p.ref}.{name}" for p in circuit.parts for name in pin_positions(p)}
    want = {frozenset(group) for group in intended}
    listed = frozenset().union(*want)
    lines = [
        f"{pin} is in the intended netlist, but the drawing has no such pin."
        for pin in sorted(listed - drawn)
    ]
    have: set[frozenset[str]] = set()
    for members in nets.members.values():
        on_sheet = {f"{ref}.{name}" for ref, name in members} & drawn
        if on_sheet & listed:
            have.add(frozenset(on_sheet & listed))
        if len(on_sheet) > 1:
            lines += [
                f"{pin} is left out of the intended netlist, but the drawing joins it to "
                f"{_names(on_sheet - {pin})}."
                for pin in sorted(on_sheet - listed)
            ]
    missing, extra = sorted(want - have, key=sorted), sorted(have - want, key=sorted)
    lines += [f"Not drawn as one net: {_names(group)}." for group in missing]
    lines += [f"Drawn as one net, but not meant: {_names(group)}." for group in extra]
    return lines
