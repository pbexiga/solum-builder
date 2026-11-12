"""The build notes page (9d1): the circuit's description and general notes, the notes on
its sheet and on its parts and nets, and each control: every knob with its value and saved
turn, every switch with its positions and the one it's saved at. Pure: the circuit in, a
page out.
"""

import html
from dataclasses import dataclass

from solum.circuit.refs import ref_key
from solum.circuit.schema import Circuit, Pot, Switch, TextBlock
from solum.export import TAPERS, page
from solum.units import format_value, parse_value


@dataclass(frozen=True)
class Control:
    ref: str  # VR1 (a dual pot's name too); SW1 for a switch of several poles
    name: str  # its label, or "" when it has none
    what: str  # "B100k, linear (B)"; "DPDT on-on"
    setting: str  # "at 50% of its turn"; "MkII"
    positions: tuple[str, ...] = ()  # a switch's, in order


def knobs(circuit: Circuit) -> list[Control]:
    """Each pot, by ref (a dual pot once, by its name, D-217): its value and taper (as the
    parts list writes them) and saved turn."""
    pots = sorted(
        (p for p in circuit.parts if isinstance(p, Pot) and p.gang in (None, "a")),
        key=lambda p: ref_key(p.ref),
    )
    return [
        Control(
            p.knob,
            p.label or "",
            f"{p.taper}{format_value(parse_value(p.value))}{' dual gang' if p.gang else ''}, "
            f"{TAPERS[p.taper]}",
            f"at {p.rotation:.0%} of its turn",
        )
        for p in pots
    ]


def switches(circuit: Circuit) -> list[Control]:
    """Each switch once (its first pole stands for the rest), by ref, with its positions."""
    found = [p for p in circuit.parts if isinstance(p, Switch) and p.pole in (None, "a")]
    return [
        Control(
            s.switch,
            s.label or "",
            s.switch_kind.short,
            s.position_names[s.position],
            tuple(s.position_names),
        )
        for s in sorted(found, key=lambda p: ref_key(p.switch))
    ]


def sheet_texts(circuit: Circuit) -> list[TextBlock]:
    """The sheet's text blocks as you'd read them: top to bottom, then left to right."""
    return sorted(circuit.texts, key=lambda t: (t.pos[1], t.pos[0]))


def item_notes(circuit: Circuit, kind: str) -> list[tuple[str, str]]:
    """The notes on parts (`kind` "part") or nets ("net"), by ref or name."""
    if kind == "part":
        found = [(p.ref, p.note) for p in circuit.parts if p.note]
    else:
        found = list(circuit.net_notes.items())
    return sorted(found, key=lambda kv: ref_key(kv[0]))


def _paragraphs(text: str) -> str:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return "".join(f"<p>{html.escape(b).replace(chr(10), '<br>')}</p>\n" for b in blocks)


def _who(c: Control) -> str:
    return f"{html.escape(c.name)} ({html.escape(c.ref)})" if c.name else html.escape(c.ref)


def _controls(circuit: Circuit) -> str:
    body = ""
    if pots := knobs(circuit):
        rows = "".join(f"<tr><td>{_who(k)}</td><td>{html.escape(k.what)}</td>"
                       f"<td>{html.escape(k.setting)}</td></tr>\n" for k in pots)  # fmt: skip
        body += ("<h2>Knobs</h2>\n<table><tr><th>Knob</th><th>Pot</th><th>As saved</th></tr>\n"
                 f"{rows}</table>\n")  # fmt: skip
    if found := switches(circuit):
        rows = ""
        for s in found:
            each = " · ".join(
                f"<strong>{html.escape(p)}</strong>" if p == s.setting else html.escape(p)
                for p in s.positions
            )
            rows += f"<tr><td>{_who(s)}</td><td>{html.escape(s.what)}</td><td>{each}</td></tr>\n"
        body += ("<h2>Switches</h2>\n<p>The saved position in bold.</p>\n<table><tr><th>Switch"
                 f"</th><th>Type</th><th>Positions</th></tr>\n{rows}</table>\n")  # fmt: skip
    return body


def _notes(title: str, notes: list[tuple[str, str]]) -> str:
    if not notes:
        return ""
    items = "".join(
        f"<li><strong>{html.escape(k)}</strong>: {html.escape(v)}</li>" for k, v in notes
    )
    return f"<h2>{title}</h2>\n<ul>{items}</ul>\n"


def notes_page(circuit: Circuit) -> str:
    """The build notes as a printable page (`export.page`)."""
    body = _paragraphs(circuit.description) or "<p>No description yet (File → Properties).</p>\n"
    for n in circuit.notes:  # the general notes, in the order the Notes pane lists them
        title = f"<h3>{html.escape(n.title)}</h3>\n" if n.title.strip() else ""
        body += title + _paragraphs(n.text)
    body += _controls(circuit)
    if texts := sheet_texts(circuit):
        body += "<h2>On the sheet</h2>\n"
        for t in texts:
            title = f"<h3>{html.escape(t.title)}</h3>\n" if t.title.strip() else ""
            body += title + _paragraphs(t.text)
    body += _notes("On the parts", item_notes(circuit, "part"))
    body += _notes("On the nets", item_notes(circuit, "net"))
    return page(circuit.name, f"Notes · {circuit.version}", body)
