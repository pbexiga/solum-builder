"""The kept board in the build package (P6e, D-386): `stripboard.pdf`, from the browser's
two drawings of the board (parts side, copper side mirrored, as the schematic's, D-205):
the checked line, the cut list, the link list, the numbered off-board wires and the
builder's notes (D-398); each side
filled onto its own sheet to read (`fill_sheet`); then both at real size, to lay against
the board. A board that doesn't match the circuit as saved is never packaged;
`packaged_board` says why in plain English for the package's index.
"""

import base64
import html
from dataclasses import dataclass, field, replace

from solum.circuit.refs import ref_key
from solum.circuit.schema import Circuit
from solum.export import SHEET_MARGIN, bom, fill_sheet, page, view_box
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import Hole, Layout, hole_name
from solum.stripboard.check import check_layout, end_words, note_words, read_layout
from solum.stripboard.offboard import OffItem

PITCH_MM = 2.54  # 0.1" between holes
MM_PER_UNIT = PITCH_MM / 10  # the board drawing: 10 units between holes (board-logic.js STEP)
TEXT_UNITS = 5.6  # the drawing's part labels on paper, board units (app.css .print .board-label)
HEADING_MM = 14.0  # room for a drawing's heading on its sheet
# A4 inside 15 mm margins (export.PAGE_STYLE), less a heading: room at real size
PORTRAIT = (180.0, 267.0 - HEADING_MM)
LANDSCAPE = (267.0, 180.0 - HEADING_MM)
GAP_MM = 6.0  # between the two sides at real size
NOTE_MM = 16.0  # the real-size page's note and 25.4 mm line
CAPTION_MM = 6.0  # a side's caption
JACK_LUGS = {"T": "tip", "R": "ring", "S": "sleeve"}
SHOWN_FAULTS = 3  # a stale board's faults named in the index; the rest counted


@dataclass(frozen=True)
class BoardLists:
    """What to do to the board, each a line: the cuts and links by hole, the off-board
    wires in order (numbered when shown); `size` in holes (columns, strips); `parts` each
    part by ref, its value and what it is, to read the drawings by (the user: the sheet
    means nothing without them); `notes` the builder's, as written (D-398: no out-of-date
    tags on paper)."""

    size: Hole
    cuts: list[str]
    links: list[str]
    wires: list[str]
    parts: list[tuple[str, str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Drawings:
    """The board as the browser drew it (SVG text): the parts side with the off-board parts
    and wires, the parts side without them (`bare`), the copper side mirrored, and the copper
    side as seen from the parts side (`unmirrored`, D-390; empty: left out)."""

    parts: str
    bare: str
    copper: str
    unmirrored: str = ""


@dataclass(frozen=True)
class Packaged:
    """A kept board that goes in the package (`layout`, the nets it carries) or, when
    `layout` is None, `why` it doesn't."""

    layout: Layout | None
    nets: int = 0
    why: str = ""


def packaged_board(circuit: Circuit, models: ModelLibrary, table: FootprintTable) -> Packaged:
    """The circuit's kept board, re-checked against the circuit as it is (D-386): packaged
    only when the check passes; none kept, or a stale one, said why."""
    if circuit.stripboard is None:
        return Packaged(None, why="No stripboard layout kept.")
    layout = circuit.stripboard.layout()
    checked = check_layout(layout, circuit, models, table)
    if checked.ok:
        return Packaged(layout, checked.nets)
    shown = " ".join(checked.faults[:SHOWN_FAULTS])
    more = len(checked.faults) - SHOWN_FAULTS
    rest = f" ({more} more in the Board view.)" if more > 0 else ""
    return Packaged(None, why=f"The stripboard layout doesn't match the circuit as saved, "
                              f"so it's left out: {shown}{rest} Open the Board view to "
                              "finish it.")  # fmt: skip


def _hole_key(hole: Hole) -> tuple[int, int]:
    return hole[1], hole[0]  # strip by strip, left to right


def lug_text(end: str, items: list[OffItem]) -> str:
    """An off-board lug as the package names it: its part as the parts list does, then the
    lug as drawn, a jack's spelt out ("VR1 (Gain) lug 2", "IN (Input) tip"); else
    `end_words`."""
    for item in items:
        for lug in item.lugs:
            if lug.end == end:
                label = JACK_LUGS.get(lug.label, lug.label) if item.kind == "jack" else lug.label
                return f"{item.name} {'lug ' if label[:1].isdigit() else ''}{label}"
    words = end_words(end)
    return words[:1].upper() + words[1:]


def board_lists(layout: Layout, items: list[OffItem]) -> BoardLists:
    """The cut list and link list by hole, strip by strip, and the wires in the off-board
    parts' order (the progress check's: pots in knob order, then the rest), each part's
    lugs in their order."""
    cuts = [hole_name(h) for h in sorted(layout.cuts, key=_hole_key)]
    ends = sorted((sorted((x.a, x.b), key=_hole_key) for x in layout.links),
                  key=lambda pair: _hole_key(pair[0]))  # fmt: skip
    links = [f"{hole_name(a)}–{hole_name(b)}" for a, b in ends]
    order = {lug.end: i for i, lug in enumerate(lug for item in items for lug in item.lugs)}
    wires = []
    for wire in sorted(layout.wires, key=lambda w: order.get(w.lug, len(order))):
        if wire.hole is not None:
            far = hole_name(wire.hole)
        else:
            far = lug_text(wire.to, items) if wire.to is not None else "nothing yet (loose)"
        wires.append(f"{lug_text(wire.lug, items)} to {far}")
    return BoardLists((layout.columns, layout.strips), cuts, links, wires)


def lists_for(layout: Layout, circuit: Circuit, models: ModelLibrary,
              table: FootprintTable) -> BoardLists:  # fmt: skip
    """`board_lists` with the circuit's off-board parts, its parts' values and the
    builder's notes."""
    lists = board_lists(layout, read_layout(layout, circuit, models, table).items)
    return replace(lists, parts=part_values(circuit, models),
                   notes=[note_words(n.parts, n.text) for n in layout.notes])  # fmt: skip


def part_values(circuit: Circuit, models: ModelLibrary) -> list[tuple[str, str, str]]:
    """Each part of the parts list (the hardware aside) by ref, as the parts list names it
    ("VR1 (Gain)"), with its value and what it is, in ref order (C2 before C10)."""
    rows = [(ref, line.value, line.part) for line in bom(circuit, models)
            if line.where != "hardware" for ref in line.refs]  # fmt: skip
    return sorted(rows, key=lambda row: ref_key(row[0].split(" ")[0]))


def size_text(size: Hole) -> str:
    """A board's size in holes and mm: "12 × 9 holes (30 × 23 mm)"."""
    columns, strips = size
    return (f"{columns} × {strips} holes "
            f"({round(columns * PITCH_MM)} × {round(strips * PITCH_MM)} mm)")  # fmt: skip


def real_fit(parts: tuple[float, float], copper: tuple[float, float]) -> tuple[bool, bool, float]:
    """How the two sides (each width, height in mm) go on one A4 page at real size: on a
    landscape page or not, side by side or one above the other, and the scale: 1.0 at the
    first of portrait side by side, landscape side by side, portrait stacked, landscape
    stacked that fits; else shrunk the least of them."""
    (pw, ph), (cw, ch) = parts, copper
    across = pw + cw + GAP_MM, max(ph, ch) + NOTE_MM + CAPTION_MM
    down = max(pw, cw), ph + ch + NOTE_MM + 2 * (GAP_MM + CAPTION_MM)
    ways = [(wide, row) for row in (True, False) for wide in (False, True)]
    scales = []
    for wide, row in ways:
        (w, h), (room_w, room_h) = across if row else down, LANDSCAPE if wide else PORTRAIT
        scale = min(1.0, room_w / w, room_h / h)
        if scale == 1.0:
            return wide, row, 1.0
        scales.append((scale, wide, row))
    scale, wide, row = max(scales)
    return wide, row, scale


def _img(svg: str, alt: str, scale: float) -> str:
    """A drawing at `scale` mm per board unit."""
    w, h = view_box(svg)
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img alt="{alt}" style="width: {w * scale:.2f}mm; height: {h * scale:.2f}mm" '
            f'src="data:image/svg+xml;base64,{data}">')  # fmt: skip


def _to_read(svg: str, title: str, alt: str, name: str) -> tuple[str, str]:
    """A side filled onto its own sheet, its text readable (`fill_sheet`): the section and
    its named page's rule."""
    w, h = view_box(svg)
    sheet, page_w, page_h, scale = fill_sheet(w, h, TEXT_UNITS, (False, True), HEADING_MM)
    rule = f"@page {name} {{ size: {page_w:g}mm {page_h:g}mm; margin: {SHEET_MARGIN:g}mm; }}"
    how = f"{sheet} · {scale / MM_PER_UNIT:.1f}× real size"
    head = f'{html.escape(title)} <span class="scale">· {how}</span>'
    section = f'<section class="sheet {name}"><h2>{head}</h2>{_img(svg, alt, scale)}</section>\n'
    return section, rule


def _real_size(parts_svg: str, copper_svg: str) -> str:
    """Both sides of the board alone at real size on one A4 page (`real_fit`); shrunk only
    when they're bigger than the page, and then said."""
    mm = [tuple(x * MM_PER_UNIT for x in view_box(svg)) for svg in (parts_svg, copper_svg)]
    wide, row, scale = real_fit((mm[0][0], mm[0][1]), (mm[1][0], mm[1][1]))
    if scale == 1.0:
        note = ("<p>Print at 100 % (actual size, not fit to page): this line is 25.4 mm, "
                '10 holes.</p><div class="ruler-mm"></div>')  # fmt: skip
    else:
        note = f'<p class="scaled">Too big for the page at real size: shrunk to {scale:.0%}.</p>'
    sides = ((parts_svg, "Parts side"), (copper_svg, "Copper side"))
    figs = "".join(f"<figure>{_img(svg, alt, MM_PER_UNIT * scale)}<figcaption>{alt}"
                   "</figcaption></figure>" for svg, alt in sides)  # fmt: skip
    cls = "sheet real wide" if wide else "sheet real"
    way = "row" if row else "column"
    return (f'<section class="{cls}"><h2>At real size</h2>{note}'
            f'<div class="sides {way}">{figs}</div></section>\n')  # fmt: skip


STYLE = """
@page wide { size: A4 landscape; }
section.sheet { break-before: page; } section.wide { page: wide; }
section.parts { page: parts; } section.copper { page: copper; }
section.unmirrored { page: unmirrored; }
section.sheet img { display: block; }
h2 .scale { color: var(--brass); font-size: 10pt; }
.ruler-mm { width: 25.4mm; border-top: 1pt solid var(--ink); margin: 2pt 0 8pt; }
ul.holes { columns: 6; padding-left: 0; list-style: none; margin: 0; }
ol.wires { padding-left: 2.2em; margin: 0; }
ul.parts { columns: 3; padding-left: 0; list-style: none; margin: 0; }
ul.parts li { break-inside: avoid; } ul.parts span { color: var(--slate); font-size: 9pt; }
.scaled { color: var(--brass); }
.sides.row figure { display: inline-block; vertical-align: top; margin: 0 6mm 0 0; }
.sides.column figure { margin: 0 0 6mm; }
figcaption { color: var(--slate); font-size: 9pt; margin-top: 2pt; }
"""


def stripboard_page(circuit: Circuit, drawn: Drawings, lists: BoardLists, nets: int) -> str:
    """The board's page for the package: the checked line, the parts by ref with their
    values, the lists, each side on its
    own sheet to read, then the board alone at real size. Raises ValueError for a drawing
    without a viewBox."""
    esc = html.escape

    def listed(title: str, lines: list[str], tag: str, cls: str) -> str:
        items = "".join(f"<li>{esc(x)}</li>" for x in lines)
        found = f'<{tag} class="{cls}">{items}</{tag}>\n' if lines else "<p>None.</p>\n"
        return f"<h2>{title} ({len(lines)})</h2>\n{found}"

    parts, parts_rule = _to_read(
        drawn.parts, "Parts side", "The board from the parts side", "parts"
    )
    copper, copper_rule = _to_read(drawn.copper, "Copper side, mirrored as under the iron (cuts ✕)",
                                   "The board from the copper side", "copper")  # fmt: skip
    unmirrored = ""
    if drawn.unmirrored:
        title = "Copper side, not mirrored: as seen through from the parts side (cuts ✕, links)"
        alt = "The copper side seen from the parts side"
        unmirrored, rule = _to_read(drawn.unmirrored, title, alt, "unmirrored")
        copper_rule += "\n" + rule
    body = (f"<style>{STYLE}{parts_rule}\n{copper_rule}</style>\n"
            f"<p><strong>Every connection on this board matches the circuit ({nets} nets)."
            "</strong> Holes are named by column letter and strip number, as on the drawings "
            "(F7: column F, strip 7).</p>\n")  # fmt: skip
    rows = ""
    for ref, value, part in lists.parts:
        what = "" if part.lower() in value.lower() else f" <span>{esc(part.lower())}</span>"
        rows += f"<li><strong>{esc(ref)}</strong> {esc(value)}{what}</li>"
    body += f'<h2>Parts ({len(lists.parts)})</h2>\n<ul class="parts">{rows}</ul>\n'
    if lists.notes:
        body += listed("Notes", lists.notes, "ul", "notes")
    body += listed("Cuts", lists.cuts, "ul", "holes")
    body += listed("Links", lists.links, "ul", "holes")
    body += listed("Off-board wires", lists.wires, "ol", "wires")
    body += parts + copper + unmirrored + _real_size(drawn.bare, drawn.copper)
    return page(circuit.name, f"Stripboard · {circuit.version} · {size_text(lists.size)}", body)
