"""File → Export (9d1, D-203): what a builder takes to the bench, from the circuit's last save.

`ready_to_build` is the check before export: the build checks are rules (`Rule.build`), so
the Problems panel shows them too. `bom` groups identical parts into the lines of a parts
list, on the board or off it (by part type: jacks, the DC jack, switches, pots, the battery
and the status LED are off-board); `bom_csv` and `bom_page` write it out.
"""

import base64
import csv
import html
import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from solum import __version__
from solum.circuit.connectivity import ConnectivityError, connect
from solum.circuit.enclosures import size_of
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
    Jack,
    Jfet,
    Led,
    Mosfet,
    Part,
    Pot,
    Regulator,
    Resistor,
    Switch,
    Trimmer,
)
from solum.models import Model, ModelLibrary
from solum.netlist import Ac, Op, Tran, generate_netlist
from solum.rules.checks import DEFAULT_RATING_W
from solum.rules.run import Checker, Problem
from solum.simulate import LEVELS, MEASURE_CYCLES, STEPS_PER_CYCLE, Simulator
from solum.units import format_quantity, format_value, parse_value
from solum.view import probe_nets

Where = Literal["board", "off-board", "hardware"]
SECTIONS: tuple[tuple[Where, str], ...] = (
    ("board", "On the board"),
    ("off-board", "Off the board"),
    ("hardware", "Hardware"),
)
STATUS_LED = "status"  # an LED with this label (any case) is the bypass LED: off-board


@dataclass(frozen=True)
class ReadyToBuild:
    """The build checks' problems, and whether the circuit simulated (the bias sheet needs
    its operating point)."""

    problems: list[Problem]
    simulates: bool


def ready_to_build(checker: Checker, sim: Simulator | None, circuit: Circuit) -> ReadyToBuild:
    found, checked = checker.check(circuit, sim)
    return ReadyToBuild([p for p in found if p.build], checked)


# ---- the parts list --------------------------------------------------------------------


@dataclass(frozen=True)
class BomLine:
    """One line of the parts list: identical parts together. `refs` in parts-list order,
    each with its name when it has one ("VR1 (Gain)")."""

    where: Where
    part: str  # what it is: "Resistor", "Pot", "Transistor"
    value: str  # "4k7", "B100k", "2N5089"
    details: str  # what else to buy it by: type, rating, taper, package and pinout
    refs: tuple[str, ...]
    count: int | None = None  # how many, when it isn't one per ref (an enclosure)

    @property
    def quantity(self) -> int:
        return len(self.refs) if self.count is None else self.count


ORDER = (  # parts-list order: passives, then semiconductors, then chips, then off-board
    "resistor", "trimmer", "capacitor", "inductor", "diode", "led", "bjt", "jfet", "mosfet",
    "opamp", "inverter", "ota", "chargepump", "regulator", "pot", "switch", "jack", "dcjack",
    "battery",
)  # fmt: skip
_PART_NAMES = {
    "resistor": "Resistor", "trimmer": "Trimmer", "capacitor": "Capacitor",
    "inductor": "Inductor", "diode": "Diode", "led": "LED", "bjt": "Transistor",
    "jfet": "JFET", "mosfet": "MOSFET", "opamp": "Op-amp", "inverter": "Inverter chip",
    "ota": "OTA", "chargepump": "Charge pump", "regulator": "Regulator",
    "pot": "Pot", "switch": "Switch",
    "jack": "Jack", "dcjack": "DC jack", "battery": "Battery",
}  # fmt: skip
_CAP_KINDS = {
    "film": "film", "ceramic": "ceramic (X7R)", "c0g": "ceramic C0G (NP0)",
    "electrolytic": "electrolytic", "tantalum": "tantalum",
}  # fmt: skip
TAPERS = {"A": "log (A)", "B": "linear (B)", "C": "reverse log (C)", "W": "W taper"}
_WATTS = {0.125: "⅛ W", 0.25: "¼ W", 0.5: "½ W"}
VALUED = (Resistor, Capacitor, Inductor, Pot, Trimmer)


def watts_text(watts: float) -> str:
    return _WATTS.get(watts) or format_quantity(watts, "W")


def _named(ref: str, name: str | None) -> str:
    return f"{ref} ({name})" if name else ref


@dataclass(frozen=True)
class _Item:
    """One part to buy (a whole chip, a whole switch) before grouping."""

    type: str
    where: Where
    value: str
    details: str
    ref: str  # its ref as listed (with its name)
    key: str  # its plain ref, for the order
    amount: float = 0.0  # its value in SI units, for the order (0: none)


def _package(models: ModelLibrary, model: str, pinout: bool) -> str:
    if model not in models:
        return "model not in the library"
    package = models.get(model).info.package
    if package is None:
        return "package not in its model: check the datasheet"
    if not pinout:
        return package.name
    pins = ", ".join(f"{n} {pin}" for pin, n in sorted(package.pins.items(), key=lambda x: x[1]))
    return f"{package.name}: {pins}"


def _semi_details(part: Diode | Led | Bjt | Jfet | Mosfet, models: ModelLibrary) -> str:
    details = [_package(models, part.model, pinout=True)]
    if isinstance(part, Bjt) and part.measured is not None:
        picked = f"picked for hFE {part.measured.hfe:g}"
        if part.measured.leakage is not None:
            picked += f", leakage {format_quantity(part.measured.leakage, 'A')}"
        details.append(picked)
    if isinstance(part, Jfet) and part.measured is not None:
        m = part.measured
        details.append(
            f"picked for Idss {format_quantity(m.idss, 'A')}, Vp {format_quantity(m.vp, 'V')}"
        )
    return "; ".join(details)


def _item(part: Part, models: ModelLibrary) -> _Item | None:
    """What buying `part` takes, or None for what isn't bought (the guitar, the amp, a test
    source, a chip's power unit: the chip's first unit stands for it)."""
    ref = part.ref

    def make(where: Where, value: str, details: str, name: str | None = None) -> _Item:
        amount = parse_value(part.value) if isinstance(part, VALUED) else 0.0
        return _Item(part.type, where, value, details, _named(ref, name), ref, amount)

    if isinstance(part, Resistor):
        rating = watts_text(part.rating_w or DEFAULT_RATING_W)
        return make("board", format_value(parse_value(part.value)), rating)
    if isinstance(part, Capacitor):
        kind = _CAP_KINDS[part.kind] if part.kind else "type not set"
        if part.rating_v is not None:
            kind += f", {format_quantity(part.rating_v, 'V')}"
        elif part.kind in POLARISED:
            kind += ", voltage rating not set"
        return make("board", format_value(parse_value(part.value)), kind)
    if isinstance(part, Inductor):
        wire = f"{format_quantity(part.resistance, 'Ω')} wire" if part.resistance else ""
        details = ", ".join(x for x in (part.kind, wire) if x)
        return make("board", format_quantity(parse_value(part.value), "H"), details)
    if isinstance(part, Pot) and part.gang:
        if part.gang != "a":
            return None  # one pot, however many gangs (D-217)
        value = f"{part.taper}{format_value(parse_value(part.value))}"
        name = _named(part.knob, part.label)
        details = f"{TAPERS[part.taper]}, dual gang"
        return _Item(part.type, "off-board", value, details, name, part.knob,
                     parse_value(part.value))  # fmt: skip
    if isinstance(part, Pot | Trimmer):
        value = f"{part.taper}{format_value(parse_value(part.value))}"
        where: Where = "off-board" if isinstance(part, Pot) else "board"
        return make(where, value, TAPERS[part.taper], part.label)
    if isinstance(part, Switch):
        if part.pole not in (None, "a"):
            return None  # one switch, however many poles
        name = _named(part.switch, part.label)
        where = "board" if part.switch_kind.group == "DIP" else "off-board"  # D-238
        return _Item("switch", where, part.switch_kind.name, "", name, part.switch)
    if isinstance(part, Led):
        status = (part.label or "").strip().lower() == STATUS_LED
        return make("off-board" if status else "board", part.model,
                    _semi_details(part, models), part.label)  # fmt: skip
    if isinstance(part, Diode | Bjt | Jfet | Mosfet):
        return make("board", part.model, _semi_details(part, models))
    if isinstance(part, CHIP_UNITS):
        unit: ChipUnit = part
        if unit.half not in (None, "a"):
            return None  # one chip, however many units
        return _Item(part.type, "board", unit.model, _package(models, unit.model, pinout=False),
                     unit.chip, unit.chip)  # fmt: skip
    if isinstance(part, ChargePump | Regulator):
        return make("board", part.model, _package(models, part.model, pinout=False))
    if isinstance(part, Jack):
        what = "stereo (TRS)" if part.stereo else "mono (TS)"
        return make("off-board", '¼" jack', what, part.label)
    if isinstance(part, DcJack):
        return make("off-board", "2.1 mm", "centre negative, with a battery lug")
    if isinstance(part, Battery):
        return make("off-board", f"{part.volts:g} V", "")
    return None


def _covers(circuit: Circuit, jack: Jack, end: Guitar | AmpInput) -> bool:
    """A drawn jack stands for the guitar's or the amp's end: its tip on that end's net,
    else its label says so (Input, Output)."""
    try:
        nets = connect(circuit)
        pin = "out" if isinstance(end, Guitar) else "in"
        if nets.net_of(jack.ref, "T") == nets.net_of(end.ref, pin):
            return True
    except ConnectivityError:
        pass
    want = "input" if isinstance(end, Guitar) else "output"
    return (jack.label or "").strip().lower() == want


def _input_output_jacks(circuit: Circuit) -> list[_Item]:
    """The guitar's and the amp's jacks, for each end no drawn jack stands for: the circuit
    plugs into both. A stereo guitar input (its ring switching a battery) is a stereo jack."""
    jacks = [p for p in circuit.parts if isinstance(p, Jack)]
    found = []
    for p in circuit.parts:
        if not isinstance(p, Guitar | AmpInput) or any(_covers(circuit, j, p) for j in jacks):
            continue
        if isinstance(p, Guitar):
            what = "stereo (TRS)" if p.stereo else "mono (TS)"
            found.append(_Item("jack", "off-board", '¼" jack', what, "IN (Input)", "IN"))
        else:
            found.append(_Item("jack", "off-board", '¼" jack', "mono (TS)", "OUT (Output)", "OUT"))
    return found


# The rest of a build, the same for every pedal: listed, not counted (D-204).
CHECKLIST = (
    "A board: the PCB, or stripboard or perfboard cut to fit",
    "Board mounts: standoffs, or foam tape under the board",
    "Hook-up wire for the jacks, switches, pots and LED (22-24 AWG, a few colours)",
    "Heat-shrink sleeving for the off-board joints",
    "Rubber feet",
    "Solder",
)


def hardware(circuit: Circuit, models: ModelLibrary) -> list[BomLine]:
    """What a build needs besides its parts (D-204): the enclosure, a knob per pot, a socket
    per DIP chip, a bezel for the status LED, the battery's clip."""
    lines = []
    box = circuit.enclosure
    if box is None:
        lines.append(
            BomLine(
                "hardware", "Enclosure", "not chosen", "pick one in File \u2192 Properties", (), 1
            )
        )
    elif (size := size_of(box.size)) is not None:
        lines.append(BomLine("hardware", "Enclosure", size.name, f"{size.text} outside", (), 1))
    else:
        dims = f"{box.length:g} \u00d7 {box.width:g} \u00d7 {box.height:g} mm outside"
        lines.append(BomLine("hardware", "Enclosure", "Custom", dims, (), 1))
    pots = sorted(
        (p for p in circuit.parts if isinstance(p, Pot) and p.gang in (None, "a")),
        key=lambda p: ref_key(p.ref),
    )
    if pots:
        refs = tuple(_named(p.knob, p.label) for p in pots)
        lines.append(BomLine("hardware", "Knob", "", "to fit the pots' shafts", refs))
    sockets: dict[str, list[str]] = {}
    for p in circuit.parts:
        if isinstance(p, (*CHIP_UNITS, ChargePump)) and getattr(p, "half", None) in (None, "a"):
            model = models.get(p.model) if p.model in models else None
            package = model.info.package if model else None
            if package is not None and "DIP" in package.name:
                ref = p.chip if isinstance(p, CHIP_UNITS) else p.ref
                sockets.setdefault(package.name, []).append(ref)
    for name, refs_ in sorted(sockets.items()):
        lines.append(BomLine("hardware", "IC socket", name, "so the chip can be swapped",
                             tuple(sorted(refs_, key=ref_key))))  # fmt: skip
    for p in circuit.parts:
        if isinstance(p, Led) and (p.label or "").strip().lower() == STATUS_LED:
            lines.append(
                BomLine("hardware", "LED bezel", "", f"for {p.model}", (_named(p.ref, p.label),))
            )
    batteries = tuple(p.ref for p in circuit.parts if isinstance(p, Battery))
    if batteries:
        lines.append(BomLine("hardware", "Battery clip", "9 V snap", "", batteries))
    return lines


def bom(circuit: Circuit, models: ModelLibrary) -> list[BomLine]:
    """The parts list: on the board, then off it, by part type (`ORDER`) then value, each
    line's refs in order; then the hardware."""
    items = [i for p in circuit.parts if (i := _item(p, models)) is not None]
    items += _input_output_jacks(circuit)
    groups: dict[tuple[Where, str, str, str], list[_Item]] = {}
    for i in items:
        groups.setdefault((i.where, i.type, i.value, i.details), []).append(i)

    def order(key: tuple[Where, str, str, str]) -> tuple[Any, ...]:
        where, kind, value, _ = key
        first = min(ref_key(i.key) for i in groups[key])
        return (where == "off-board", ORDER.index(kind), groups[key][0].amount, value, first)

    lines = []
    for key in sorted(groups, key=order):
        where, kind, value, details = key
        members = sorted(groups[key], key=lambda i: ref_key(i.key))
        lines.append(BomLine(where, _PART_NAMES[kind], value, details,
                             tuple(i.ref for i in members)))  # fmt: skip
    return lines + hardware(circuit, models)


BOM_COLUMNS = ("Where", "Qty", "Part", "Value", "Details", "Refs")


def _row(line: BomLine) -> tuple[str, ...]:
    where = dict(SECTIONS)[line.where]
    return (where, str(line.quantity), line.part, line.value, line.details, ", ".join(line.refs))


def bom_csv(lines: Iterable[BomLine]) -> str:
    """The parts list, then the checklist (no quantity)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(BOM_COLUMNS)
    writer.writerows(_row(line) for line in lines)
    writer.writerows(("Also", "", item, "", "", "") for item in CHECKLIST)
    return out.getvalue()


# ---- the netlists and their models (D-206) ----------------------------------------------

EXPORT_TONE_HZ = 1000.0  # the exported transient's tone: the usual test tone
EXPORT_LEVEL = "med"  # and its pick (`LEVELS`)
_PIN_ORDER = {"bjt": "C B E", "jfet": "D G S", "mosfet": "D G S", "diode": "A K", "led": "A K"}


@dataclass(frozen=True)
class OutFile:
    """One file of the package: its name in the zip and its text."""

    name: str
    text: str


def _wrapped(text: str, title: str, about: list[str], prints: list[str]) -> str:
    """A generated netlist as a file of its own: our header for its title line, the
    `.print` lines before `.end`."""
    body = text.split("\n", 1)[1].rstrip("\n")
    body = body.removesuffix(".end").rstrip("\n")
    head = [f"* {title}", *(f"* {line}" for line in about)]
    return "\n".join([*head, body, *prints, ".end", ""])


def export_netlists(circuit: Circuit, sim: Simulator) -> list[OutFile]:
    """A self-contained ngspice netlist per analysis (op; ac and tran when there's a guitar
    input), from the last save with each targeted trimmer solved (`solve_bias`); model
    cards inlined. Runs in plain ngspice: `ngspice -b <file>`."""
    biased = sim.solve_bias(circuit)
    c = biased.circuit
    nets = connect(c)
    probes = probe_nets(c, nets)
    set_by = [
        f"{ref} set to {rot:.0%} by its bias target ({c.part(ref).bias_target.node} at "  # type: ignore[union-attr]
        f"{format_quantity(biased.volts[ref], 'V')})"
        for ref, rot in sorted(biased.rotations.items())
    ]
    about = [
        f"{circuit.version}, from its last save, by Solum Builder {__version__}.",
        "Run it in ngspice: ngspice -b <this file>. Model cards are inlined (models.txt lists",
        "them); nodes are the circuit's nets, ground is 0.",
        *set_by,
    ]
    first = generate_netlist(c, sim.models, Op())
    out = [OutFile("op.cir", _wrapped(first.text, f"{c.name}: DC operating point", about, []))]
    if probes.input is None or probes.output is None:
        return out
    node_out = first.node(probes.output)
    ac = generate_netlist(c, sim.models, Ac())
    response = f"{c.name}: frequency response (1 V at the input)"
    prints = [f".print ac vdb({node_out}) vp({node_out})"]
    out.append(OutFile("ac.cir", _wrapped(ac.text, response, about, prints)))
    period = 1 / EXPORT_TONE_HZ
    wait = sim.settling(c).seconds
    tran = Tran(EXPORT_TONE_HZ, LEVELS[EXPORT_LEVEL], wait + MEASURE_CYCLES * period,
                period / STEPS_PER_CYCLE)  # fmt: skip
    text = generate_netlist(c, sim.models, tran).text
    tone, level = format_quantity(EXPORT_TONE_HZ, "Hz"), format_quantity(LEVELS[EXPORT_LEVEL], "V")
    prints = [f".print tran v({first.node(probes.input)}) v({node_out})"]
    title = f"{c.name}: waveform (a {tone} tone at {level} peak)"
    out.append(OutFile("tran.cir", _wrapped(text, title, about, prints)))
    return out


def used_models(circuit: Circuit, models: ModelLibrary) -> list[Model]:
    """Every model the circuit's parts name, by id."""
    ids = {m for p in circuit.parts if (m := getattr(p, "model", None)) and m in models}
    return [models.get(i) for i in sorted(ids)]


def _pins(model: Model) -> str:
    if model.info.kind == "subckt":
        line = next((ln for ln in model.card.splitlines() if ln.lower().startswith(".subckt")), "")
        return " ".join(line.split()[2:]) or "see its .subckt line"
    return _PIN_ORDER.get(model.info.type, "")


def models_list(circuit: Circuit, models: ModelLibrary) -> str:
    """models.txt: each model the netlists use, its kind, its pins in the order the netlist
    gives them, whose card it is and where it came from, and its .lib file."""
    lines = [
        f"Models used by {circuit.name} ({circuit.version})",
        "",
        "The netlists have these cards inlined. Another simulator may need them as files: each",
        "is in models/, as .lib. A measured transistor's netlist card is a copy with its gain",
        "and leakage set (its name ends in its ref); the .lib is the stock card. A part simulated",
        "without a card (a charge pump) is built into the netlist from its record.",
        "",
    ]
    for m in used_models(circuit, models):
        entry = m.catalogue_entry()
        lines += [
            f"{m.id} ({m.info.type}, {m.info.kind})",
            f"  pins, in order: {_pins(m) or 'none: no card'}",
            f"  card: {entry['origin']}"
            + (f", {entry['origin_detail']}" if entry["origin_detail"] else ""),
            *([f"  datasheet: {entry['datasheet']}"] if entry["datasheet"] else []),
            f"  file: models/{m.id}.lib" if m.info.kind != "behavioural" else "  file: none",
            "",
        ]
    return "\n".join(lines)


def model_files(circuit: Circuit, models: ModelLibrary) -> list[OutFile]:
    """Each used model's card as models/<id>.lib."""
    return [OutFile(f"models/{m.id}.lib", m.card if m.card.endswith("\n") else m.card + "\n")
            for m in used_models(circuit, models) if m.info.kind != "behavioural"]  # fmt: skip


def zip_files(files: Iterable[OutFile | tuple[str, bytes]], folder: str = "") -> bytes:
    """Files in one zip (`OutFile` text as UTF-8), inside `folder` when one is given."""
    out = io.BytesIO()
    prefix = f"{folder}/" if folder else ""
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            name, data = (f.name, f.text.encode("utf-8")) if isinstance(f, OutFile) else f
            z.writestr(prefix + name, data)
    return out.getvalue()


# ---- printable pages -------------------------------------------------------------------

# Paper colours: the brand's print tokens (web/theme.css, docs/DESIGN.md), for the pages
# and the drawings in them.
PRINT_COLOURS = {"ink": "#1E1E1B", "bone": "#F0EDE8", "slate": "#3D4145", "brass": "#8B7D5E"}
_ROOT = " ".join(f"--{k}: {v};" for k, v in PRINT_COLOURS.items())
PAGE_STYLE = (
    ":root { "
    + _ROOT
    + " }\n"
    + """
@page { size: A4; margin: 15mm; }
body { font-family: Lora, Georgia, serif; color: var(--ink); background: #fff;
       font-size: 10.5pt; margin: 0; }
h1 { font-weight: 400; font-size: 18pt; margin: 0 0 2pt; }
h2 { font-weight: 400; font-size: 12.5pt; margin: 14pt 0 4pt; color: var(--slate); }
.sub { color: var(--brass); margin: 0 0 10pt; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; vertical-align: top; padding: 3pt 6pt 3pt 0;
         border-bottom: 0.5pt solid var(--bone); }
th { font-weight: 600; border-bottom: 1pt solid var(--slate); }
td.qty { text-align: right; padding-right: 10pt; }
table.bom { table-layout: fixed; }
table.bom col.qty { width: 7%; } table.bom col.part { width: 14%; }
table.bom col.value { width: 14%; } table.bom col.details { width: 40%; }
table.pins { table-layout: fixed; width: 70%; } th.qty { text-align: right; padding-right: 10pt; }
table.pins col.ref { width: 15%; } table.pins col.model { width: 25%; }
table.pins col.num { width: 12%; } table.pins col.pin { width: 20%; }
""".strip()
)


def page(title: str, subtitle: str, body: str) -> str:
    """A printable page of the build package: its own styles, nothing to fetch."""
    esc = html.escape
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{esc(title)}</title><style>{PAGE_STYLE}</style></head>\n"
        f'<body><h1>{esc(title)}</h1><p class="sub">{esc(subtitle)}</p>\n{body}</body></html>\n'
    )


# A schematic on one sheet, filling it (the user, 2026-11-04; D-205). The drawing's values
# and labels are 9 units high (app.css); on paper they stay between these sizes.
SHEETS = (("A4", 297.0, 210.0), ("A3", 420.0, 297.0))  # landscape, mm
SHEET_MARGIN = 12.0  # mm all round
TITLE_SPACE = 16.0  # mm under the top margin for the title
TEXT_UNITS = 9.0  # the drawing's value and label text, schematic units
TEXT_MIN_MM = 2.0  # smaller than this (about 6 pt) is hard to read: go up a sheet size
TEXT_MAX_MM = 3.5  # a small circuit grows only until its text is this big


def _view_box(svg: str) -> tuple[float, float]:
    found = re.search(r'viewBox="[-\d.e]+ [-\d.e]+ ([\d.e]+) ([\d.e]+)"', svg)
    if not found:
        raise ValueError("The drawing has no viewBox.")
    return float(found[1]), float(found[2])


def schematic_sheet(width: float, height: float) -> tuple[str, float, float, float]:
    """The sheet a drawing `width` by `height` (schematic units) goes on, its page size and
    the scale (mm per unit): the smallest sheet where filling it keeps the text readable;
    the largest when none does. Always one sheet: wires followed across pages are worse
    than a larger sheet."""
    for name, w, h in SHEETS:
        room_w, room_h = w - 2 * SHEET_MARGIN, h - 2 * SHEET_MARGIN - TITLE_SPACE
        scale = min(room_w / width, room_h / height, TEXT_MAX_MM / TEXT_UNITS)
        if scale * TEXT_UNITS >= TEXT_MIN_MM or name == SHEETS[-1][0]:
            return name, w, h, scale
    raise AssertionError("unreachable")


def schematic_page(circuit: Circuit, svg: str) -> str:
    """The schematic (the browser's drawing, D-205) filling one landscape sheet, with its
    title."""
    width, height = _view_box(svg)
    sheet, page_w, page_h, scale = schematic_sheet(width, height)
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    size = f"width: {width * scale:.1f}mm; height: {height * scale:.1f}mm"
    body = (
        f"<style>@page {{ size: {page_w:g}mm {page_h:g}mm; margin: {SHEET_MARGIN:g}mm; }} "
        f"img {{ display: block; margin: 0 auto; {size}; }}</style>"
        f'<img alt="Schematic" src="data:image/svg+xml;base64,{data}">\n'
    )
    return page(circuit.name, f"Schematic \u00b7 {circuit.version} \u00b7 {sheet}", body)


def pdf(html_text: str, web_dir: Path) -> bytes:
    """A printable page as PDF (WeasyPrint, D-205), in the app's own Lora. Only the page's
    own data and the app's files are read, nothing from the network: a schematic comes
    from the browser."""
    from weasyprint import CSS, HTML
    from weasyprint.urls import URLFetcher

    lora = (web_dir / "fonts" / "lora" / "Lora[wght].ttf").resolve().as_uri()
    fonts = CSS(string=f'@font-face {{ font-family: Lora; src: url("{lora}"); }}')
    local = URLFetcher(allowed_protocols={"data", "file"})
    document = HTML(string=html_text, url_fetcher=local)
    return cast(bytes, document.write_pdf(stylesheets=[fonts]))


def _bom_table(lines: list[BomLine]) -> str:
    esc = html.escape
    head = "".join(f"<th>{c}</th>" for c in ("Qty", "Part", "Value", "Details", "Refs"))
    rows = "".join(
        f'<tr><td class="qty">{line.quantity}</td><td>{esc(line.part)}</td>'
        f"<td>{esc(line.value)}</td><td>{esc(line.details)}</td>"
        f"<td>{esc(', '.join(line.refs))}</td></tr>"
        for line in lines
    )
    cols = "".join(f'<col class="{c}">' for c in ("qty", "part", "value", "details", "refs"))
    return (
        f'<table class="bom"><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table>\n"
    )


def bom_page(circuit: Circuit, lines: list[BomLine]) -> str:
    body = ""
    for where, title in SECTIONS:
        if found := [x for x in lines if x.where == where]:
            body += f"<h2>{title}</h2>\n{_bom_table(found)}"
    items = "".join(f"<li>{html.escape(item)}</li>" for item in CHECKLIST)
    body += f"<h2>Also</h2>\n<ul>{items}</ul>\n"
    count = sum(x.quantity for x in lines if x.where != "hardware")
    return page(circuit.name, f"Parts list \u00b7 {circuit.version} \u00b7 {count} parts", body)
