"""The generic wiring diagrams (9d1, D-209): a 3PDT true-bypass footswitch with its status
LED, the jacks, and the DC jack with the battery, as drawings in `library/wiring/` and a
printable page with the steps. The same for every circuit for now; circuit-specific wiring
comes later.
"""

import html
from dataclasses import dataclass
from pathlib import Path

from solum.circuit.schema import Circuit
from solum.export import PRINT_COLOURS, page


@dataclass(frozen=True)
class Diagram:
    file: str  # in library/wiring/
    title: str
    steps: tuple[str, ...]


DIAGRAMS = (
    Diagram(
        "footswitch-3pdt.svg",
        "Footswitch: 3PDT true bypass with the status LED",
        (
            "Seen from the lugs. The middle row are the commons; each pole is a column.",
            "Which outer row is the effect's depends on the switch: with a meter on continuity, "
            "find the row that joins the middle row with the switch on. Lug numbers differ "
            "between makers, so go by what you measure.",
            "Input pole: its common from the input jack's tip, its effect throw to the board's "
            "input. Output pole: its common to the output jack's tip, its effect throw from the "
            "board's output.",
            "A jumper joins the input and output poles' bypass throws: with the effect off, the "
            "guitar goes straight to the amp.",
            "LED pole: its common to ground, its effect throw to the LED's cathode "
            "(\u2212, the short "
            "leg, the flat side). The LED's anode goes to the 9 V through its resistor: the "
            "circuit's, if it draws one.",
        ),
    ),
    Diagram(
        "jacks.svg",
        "Jacks",
        (
            "Tip to the signal (the footswitch's commons), sleeve to ground.",
            "With a battery, use a stereo jack for the input and wire the battery's "
            "\u2212 (black) to "
            "its ring: a guitar's mono plug joins ring and sleeve, so the battery is on only "
            "while a cable is in. Unplug the input when you're done.",
            "Find tip, ring and sleeve with a meter: the lugs sit differently on each jack.",
        ),
    ),
    Diagram(
        "dc-jack.svg",
        "DC jack and battery",
        (
            "2.1 mm, centre negative, as pedal supplies are: the centre pin to ground, the sleeve "
            "to the circuit's 9 V.",
            "The battery's + (red) goes to the battery lug, which touches the sleeve until a plug "
            "goes in: an adapter switches the battery out.",
            "Use a plastic-bodied DC jack, or one that insulates its sleeve from the box: the box "
            "is ground, the sleeve is 9 V.",
        ),
    ),
)

POSITIVE_GROUND = (
    "This circuit runs from \u22129 V (positive ground): this DC jack wiring isn't for it. "
    "Its 9 V and ground swap places, so it can't share a daisy-chain supply with other "
    "pedals. Use a battery, or its own isolated supply, and check the wiring against the "
    "circuit before you power it."
)


def positive_ground(circuit: Circuit) -> bool:
    """True when the circuit has a negative rail and no positive one (a germanium PNP fuzz)."""
    rails = circuit.power.rails
    return any(v < 0 for v in rails.values()) and not any(v > 0 for v in rails.values())


# inside each drawing: WeasyPrint doesn't style an inline SVG from the page's CSS
SVG_STYLE = (
    ".w-wire {{ fill: none; stroke: {ink}; stroke-width: 2; }}"
    " .w-jumper {{ fill: none; stroke: {brass}; stroke-width: 3; }}"
    " .w-lug circle {{ fill: #fff; stroke: {ink}; stroke-width: 2; }}"
    " .w-body {{ fill: {bone}; stroke: {slate}; stroke-width: 1.5; }}"
    " .w-dot {{ fill: {ink}; }}"
    " .w-text {{ fill: {ink}; font-family: Lora, Georgia, serif; font-size: 13px; }}"
    " .w-head {{ font-weight: 600; }}"
    " .w-note {{ fill: {brass}; font-family: Lora, Georgia, serif; font-size: 12px;"
    " font-style: italic; }}"
).format(**PRINT_COLOURS)
PAGE_STYLE = (
    "svg.wiring { width: 100%; max-height: 95mm; display: block; margin: 4pt 0 6pt; }"
    " section.diagram { break-inside: avoid; }"
)


def _svg(wiring_dir: Path, name: str) -> str:
    """The drawing, with its styles written into it."""
    text = (wiring_dir / name).read_text(encoding="utf-8")
    svg = text[text.index("<svg") :]
    head = svg.index(">") + 1
    return f"{svg[:head]}<style>{SVG_STYLE}</style>{svg[head:]}"


def wiring_page(circuit: Circuit, wiring_dir: Path) -> str:
    """The wiring diagrams as a printable page (`export.page`), each with its steps."""
    body = f"<style>{PAGE_STYLE}</style>\n"
    body += (
        "<p>Generic wiring: the same for every pedal for now. Check every lug with a meter.</p>\n"
    )
    if positive_ground(circuit):
        body += f'<p class="warn"><strong>{html.escape(POSITIVE_GROUND)}</strong></p>\n'
    for d in DIAGRAMS:
        steps = "".join(f"<li>{html.escape(s)}</li>" for s in d.steps)
        body += (f'<section class="diagram"><h2>{html.escape(d.title)}</h2>\n'
                 f"{_svg(wiring_dir, d.file)}<ul>{steps}</ul></section>\n")  # fmt: skip
    return page(circuit.name, f"Wiring · {circuit.version}", body)
