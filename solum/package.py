"""The build package (9d1, D-210): one zip of everything File → Export makes, from the last
save, with an index page that lists what's in it and the Ready to build items still open.

The browser sends what only it has: the schematic it drew (D-205) and the Ready to build
rows it showed (dismissals and unsaved changes are worked out there, `export-logic.js`).
The app runs the simulations and passes in the bias sheet and netlists, or why there are
none; everything else is made here.
"""

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from solum.bias_sheet import BiasSheet, bias_page
from solum.build_notes import notes_page
from solum.circuit.io import circuit_to_json
from solum.circuit.schema import Circuit
from solum.export import OutFile, bom, bom_csv, bom_page, page, pdf, schematic_page
from solum.models import ModelLibrary
from solum.wiring import wiring_page

Severity = Literal["error", "warning", "info"]
SEVERITY_WORDS = {"error": "Error", "warning": "Warning", "info": "Note"}


@dataclass(frozen=True)
class ReadyRow:
    severity: Severity
    text: str


@dataclass(frozen=True)
class Simulated:
    """What the simulations gave: the bias sheet and netlists, or why there are none."""

    bias: BiasSheet | None
    netlists: list[OutFile]  # the netlists, models.txt and models/*.lib, as named in the zip
    why_not: str = ""  # plain English, when there's no bias sheet


# each file of the package, in the index's order: (name, what it is)
CONTENTS = (
    ("parts-list.pdf", "The parts list: on the board, off it, the hardware, and what else to buy."),
    ("parts-list.csv", "The same parts list for a spreadsheet or an order."),
    ("schematic.pdf", "The schematic on one sheet."),
    ("schematic.svg", "The schematic as a drawing, to open in a browser or Inkscape."),
    ("bias-sheet.pdf", "What to set and measure: the trimmers, the DC on every pin, the current."),
    ("notes.pdf", "The description, the knobs and switches, the notes on the sheet."),
    ("wiring.pdf", "Generic wiring: the footswitch, the jacks, the DC jack."),
    ("netlists/", "ngspice netlists (DC, frequency response, waveform) and every model's card."),
)


def package_files(
    circuit: Circuit,
    models: ModelLibrary,
    svg: str,
    simulated: Simulated,
    web_dir: Path,
    wiring_dir: Path,
) -> list[OutFile | tuple[str, bytes]]:
    """Every file but the index: the circuit file, the PDFs, the CSV, the SVG, the netlists.
    Raises ValueError for a drawing that isn't one (`schematic_page`)."""
    lines = bom(circuit, models)
    files: list[OutFile | tuple[str, bytes]] = [
        OutFile("circuit.json", circuit_to_json(circuit)),
        ("parts-list.pdf", pdf(bom_page(circuit, lines), web_dir)),
        OutFile("parts-list.csv", "﻿" + bom_csv(lines)),
        ("schematic.pdf", pdf(schematic_page(circuit, svg), web_dir)),
        OutFile("schematic.svg", svg),
    ]
    if simulated.bias is not None:
        files.append(("bias-sheet.pdf", pdf(bias_page(circuit, simulated.bias), web_dir)))
    files.append(("notes.pdf", pdf(notes_page(circuit), web_dir)))
    files.append(("wiring.pdf", pdf(wiring_page(circuit, wiring_dir), web_dir)))
    files += [OutFile(f"netlists/{f.name}", f.text) for f in simulated.netlists]
    return files


def _name(f: OutFile | tuple[str, bytes]) -> str:
    return f.name if isinstance(f, OutFile) else f[0]


def index_page(
    circuit: Circuit,
    names: list[str],
    ready: list[ReadyRow],
    dismissed: int,
    why_not: str = "",
) -> str:
    """The package's index: Ready to build first (what's still open), then each file."""
    esc = html.escape
    body = "<h2>Ready to build</h2>\n"
    if ready:
        rows = "".join(f"<li><strong>{SEVERITY_WORDS[r.severity]}</strong>: {esc(r.text)}</li>"
                       for r in ready)  # fmt: skip
        body += f"<p>Still open when this was exported:</p>\n<ul>{rows}</ul>\n"
    else:
        body += "<p>Nothing open: every part says what to buy.</p>\n"
    if dismissed:
        body += f"<p>{dismissed} dismissed in the Problems panel.</p>\n"
    links = ""
    for file, what in CONTENTS:
        if any(n == file or (n.startswith(file) and file.endswith("/")) for n in names):
            links += (
                f'<tr><td><a href="{esc(file)}">{esc(file)}</a></td><td>{esc(what)}</td></tr>\n'
            )
    links += ('<tr><td><a href="circuit.json">circuit.json</a></td><td>The circuit file, to open '
              "in Solum Builder (File → Open).</td></tr>\n")  # fmt: skip
    body += f"<h2>In this package</h2>\n<table>{links}</table>\n"
    if why_not:
        body += f"<p>No bias sheet or netlists: {esc(why_not)}</p>\n"
    return page(circuit.name, f"Build package · {circuit.version} · as last saved", body)


def build_package(
    circuit: Circuit,
    models: ModelLibrary,
    svg: str,
    simulated: Simulated,
    ready: list[ReadyRow],
    dismissed: int,
    dirs: tuple[Path, Path],
) -> list[OutFile | tuple[str, bytes]]:
    """The package's files, the index first. `dirs`: the web folder (fonts) and the wiring
    drawings' folder."""
    web_dir, wiring_dir = dirs
    files = package_files(circuit, models, svg, simulated, web_dir, wiring_dir)
    index = index_page(circuit, [_name(f) for f in files], ready, dismissed, simulated.why_not)
    return [OutFile("index.html", index), *files]
