"""The bias sheet (9d1): what to set and measure on the bench, from the circuit's last save
simulated at export. Each trimmer's setting (to its target, or at its saved turn), the
pots that move the bias, the DC on every transistor's and chip's pins, and the current
the circuit draws. `bias_sheet` runs the simulations; `bias_page` writes the page.
"""

import html
from collections import defaultdict
from dataclasses import dataclass

from solum.circuit.connectivity import Nets, connect
from solum.circuit.parts import pin_offsets
from solum.circuit.refs import ref_key
from solum.circuit.schema import (
    CHIP_UNITS,
    Bjt,
    ChargePump,
    Circuit,
    Jfet,
    Mosfet,
    Part,
    Pot,
    PowerUnit,
    Regulator,
    Trimmer,
)
from solum.export import page
from solum.models import ModelLibrary
from solum.simulate import OpResult, Simulator
from solum.units import format_quantity

POT_MOVES = 0.1  # volts: a pot whose turn moves any pin's DC this much moves the bias
PIN_WORDS = {
    "C": "collector",
    "B": "base",
    "E": "emitter",
    "D": "drain",
    "G": "gate",
    "S": "source",
}
# the parts whose pins are read
MEASURED = (Bjt, Jfet, Mosfet, *CHIP_UNITS, PowerUnit, ChargePump, Regulator)
# a macromodel's compensation pins are its own inner nodes: a real chip's read otherwise
UNREAD_PINS = {"comp1", "comp2"}


@dataclass(frozen=True)
class PinReading:
    pin: str  # as the sheet names it: "C", "A out", "V+"
    number: int | None  # its datasheet pin number, when the model has a package
    volts: float


@dataclass(frozen=True)
class PartReadings:
    ref: str  # a chip's ref (IC1) for all its units
    model: str
    pins: list[PinReading]  # by pin number, then name


@dataclass(frozen=True)
class BiasSheet:
    trimmers: list[str]  # what to set, one line each
    pots: list[str]  # the pots that move the bias, at their saved turn
    parts: list[PartReadings]
    supply: dict[str, float]  # rail → amps it delivers (negative on a negative rail)
    warnings: list[str]  # stages saturated or cut off at DC


def volts_text(volts: float) -> str:
    """Volts as a meter on its volts range shows them: 2 decimals, a real minus sign."""
    return f"{volts:.2f} V".replace("-", "\u2212")


def node_words(node: str) -> str:
    """A bias target's node in words: "Q2.C" → "Q2's collector", a net → "the VB net"."""
    ref, dot, pin = node.partition(".")
    if not dot:
        return f"the {node} net"
    return f"{ref}'s {PIN_WORDS.get(pin, f'pin {pin}')}"


def _named(part: Part) -> str:
    label = getattr(part, "label", None)
    ref = part.knob if isinstance(part, Pot) else part.ref  # a dual pot by its name (D-217)
    return f"{ref} ({label})" if label else ref


def trimmer_lines(circuit: Circuit, op: OpResult, nets: Nets) -> list[str]:
    """Each trimmer's setting: to its target, or at its saved turn with its wiper's DC."""
    held = {h.ref: h for h in op.held}
    lines = []
    for t in sorted(
        (p for p in circuit.parts if isinstance(p, Trimmer)), key=lambda p: ref_key(p.ref)
    ):
        name = _named(t)
        if (h := held.get(t.ref)) is None:
            wiper = op.voltages.get(nets.net_of(t.ref, "2"))
            reads = f"; its wiper reads {volts_text(wiper)}" if wiper is not None else ""
            lines.append(f"{name}: at {t.rotation:.0%} of its turn, as saved{reads}.")
        elif h.met:
            lines.append(
                f"Set {name} until {node_words(h.node)} reads {volts_text(h.volts)}"
                f" (about {h.rotation:.0%} of its turn in the simulation)."
            )
        else:
            lines.append(
                f"Set {name} until {node_words(h.node)} reads {volts_text(h.volts)}. The "
                f"simulation gets only {volts_text(h.reached)}, at {h.rotation:.0%}: check the "
                "parts around it before you power up."
            )
    return lines


def _chip_pin(part: Part, pin: str) -> str:
    half = getattr(part, "half", None)
    return f"{half.upper()} {pin}" if half else pin


def part_readings(
    circuit: Circuit, nets: Nets, volts: dict[str, float], models: ModelLibrary
) -> list[PartReadings]:
    """The DC on each transistor's and chip's pins, a chip's units together, by ref."""
    pins: dict[str, list[PinReading]] = defaultdict(list)
    model_of: dict[str, str] = {}
    for part in circuit.parts:
        if not isinstance(part, MEASURED):
            continue
        ref = getattr(part, "chip", part.ref)
        model_of[ref] = part.model
        model = models.get(part.model) if part.model in models else None
        for pin in pin_offsets(part).keys() - UNREAD_PINS:
            net = nets.net_of(part.ref, pin)
            if net not in volts:
                continue
            number = model.pin_number(pin, getattr(part, "half", None)) if model else None
            pins[ref].append(PinReading(_chip_pin(part, pin), number, volts[net]))
    return [
        PartReadings(
            ref,
            model_of[ref],
            sorted(pins[ref], key=lambda r: (r.number is None, r.number or 0, r.pin)),
        )
        for ref in sorted(pins, key=ref_key)
    ]


def _pin_order(r: PinReading) -> tuple[bool, int, str]:
    return (r.number is None, r.number or 0, r.pin)


def _readings(parts: list[PartReadings]) -> dict[tuple[str, str], float]:
    return {(p.ref, r.pin): r.volts for p in parts for r in p.pins}


def pot_lines(circuit: Circuit, sim: Simulator, parts: list[PartReadings]) -> list[str]:
    """The pots whose turn moves some pin's DC by `POT_MOVES` or more: the readings are at
    their saved turn. Others (a volume, a tone) don't matter to the bias."""
    nets = connect(circuit)
    lines = []
    for pot in sorted(
        (p for p in circuit.parts if isinstance(p, Pot) and p.gang in (None, "a")),
        key=lambda p: ref_key(p.ref),
    ):
        ends = []
        for turn in (0.0, 1.0):
            turned = circuit.with_part(pot.knob, rotation=turn)  # a dual pot's both gangs
            ends.append(_readings(part_readings(turned, nets, sim.op(turned).voltages, sim.models)))
        spread = max((abs(ends[0][k] - ends[1].get(k, ends[0][k])) for k in ends[0]), default=0.0)
        if spread >= POT_MOVES:
            lines.append(
                f"{_named(pot)} at {pot.rotation:.0%} of its turn, as saved: turning it moves "
                f"these readings (up to {spread:.1f} V)."
            )
    return lines


def bias_sheet(circuit: Circuit, sim: Simulator) -> BiasSheet:
    """The bias sheet of `circuit`, simulated (each targeted trimmer solved). Raises the
    simulator's errors (`RUN_ERRORS`) when it doesn't simulate."""
    op = sim.op(circuit)
    nets = connect(circuit)
    parts = part_readings(circuit, nets, op.voltages, sim.models)
    warnings = [s.message for s in sim.saturated(circuit)]
    return BiasSheet(trimmer_lines(circuit, op, nets), pot_lines(circuit, sim, parts), parts,
                     op.supply, warnings)  # fmt: skip


def supply_text(supply: dict[str, float]) -> str:
    """The current drawn, rail by rail: "The circuit draws 1.2 mA from V+."."""
    if not supply:
        return "The circuit has no supply."
    each = [f"{format_quantity(abs(a), 'A')} from {rail}" for rail, a in sorted(supply.items())]
    total = sum(abs(a) for a in supply.values())
    total_text = f" ({format_quantity(total, 'A')} in all)" if len(supply) > 1 else ""
    return f"The circuit draws {', '.join(each)}{total_text}."


def _list(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in lines) + "</ul>\n"


def _pins_table(parts: list[PartReadings]) -> str:
    rows = ""
    for p in parts:
        for i, r in enumerate(p.pins):
            who = (
                f"<td>{html.escape(p.ref)}</td><td>{html.escape(p.model)}</td>"
                if i == 0
                else "<td></td><td></td>"
            )
            number = "" if r.number is None else str(r.number)
            rows += (f"<tr>{who}<td>{number}</td><td>{html.escape(r.pin)}</td>"
                     f'<td class="qty">{volts_text(r.volts)}</td></tr>\n')  # fmt: skip
    cols = "".join(f'<col class="{c}">' for c in ("ref", "model", "num", "pin", "volts"))
    head = '<tr><th>Part</th><th>Model</th><th>Pin</th><th></th><th class="qty">Reads</th></tr>'
    return f'<table class="pins"><colgroup>{cols}</colgroup>{head}\n{rows}</table>\n'


def bias_page(circuit: Circuit, sheet: BiasSheet) -> str:
    """The bias sheet as a printable page (`export.page`)."""
    body = ""
    if sheet.warnings:
        body += f"<h2>Check first</h2>\n{_list(sheet.warnings)}"
    if sheet.trimmers:
        body += f"<h2>Trimmers</h2>\n{_list(sheet.trimmers)}"
    if sheet.pots:
        body += f"<h2>Pots that move the bias</h2>\n{_list(sheet.pots)}"
    body += f"<h2>Current drawn</h2>\n<p>{html.escape(supply_text(sheet.supply))}</p>\n"
    if sheet.parts:
        body += (
            "<h2>DC voltages</h2>\n<p>Black lead on ground. Expect your readings to differ a "
            "little: parts vary, transistors most.</p>\n" + _pins_table(sheet.parts)
        )
    return page(circuit.name, f"Bias sheet · {circuit.version} · as last saved", body)
