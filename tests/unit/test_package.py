"""The build package's index page (9d1, D-210)."""

from solum.circuit.build import CircuitBuilder
from solum.package import ReadyRow, index_page

NAMES = ["circuit.json", "parts-list.pdf", "parts-list.csv", "schematic.pdf", "schematic.svg",
         "notes.pdf", "wiring.pdf", "netlists/op.cir", "netlists/models.txt"]  # fmt: skip


def test_open_items_come_first_then_each_file() -> None:
    c = CircuitBuilder("Fuzz & co").build()
    ready = [ReadyRow("warning", "C2 <close> to its rating"), ReadyRow("info", "No enclosure")]
    text = index_page(c, NAMES, ready, dismissed=2)
    assert "<h1>Fuzz &amp; co</h1>" in text and "Build package · v1.0" in text
    assert text.index("Ready to build") < text.index("In this package")
    assert "<strong>Warning</strong>: C2 &lt;close&gt; to its rating" in text
    assert "<strong>Note</strong>: No enclosure" in text and "2 dismissed" in text
    assert '<a href="netlists/">netlists/</a>' in text and '<a href="circuit.json">' in text
    assert "bias-sheet.pdf" not in text  # not in the package, so not listed


def test_nothing_open_and_no_simulation() -> None:
    text = index_page(CircuitBuilder("x").build(), NAMES[:7], [], 0, "it has no supply.")
    assert "Nothing open" in text and "dismissed" not in text
    assert "netlists/" not in text and "No bias sheet or netlists: it has no supply." in text
