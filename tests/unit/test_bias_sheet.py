"""The bias sheet's words and page (9d1), from readings made up here."""

from solum.bias_sheet import (
    BiasSheet,
    PartReadings,
    PinReading,
    bias_page,
    node_words,
    supply_text,
    volts_text,
)
from solum.circuit.build import CircuitBuilder


def test_volts_read_as_a_meter_shows_them() -> None:
    assert volts_text(-0.1605) == "\u22120.16 V"
    assert volts_text(4.5) == "4.50 V"
    assert volts_text(0.0) == "0.00 V"


def test_a_target_node_in_words() -> None:
    assert node_words("Q2.C") == "Q2's collector"
    assert node_words("J1.D") == "J1's drain"
    assert node_words("IC1A.out") == "IC1A's pin out"
    assert node_words("VB") == "the VB net"


def test_the_current_drawn() -> None:
    assert supply_text({"V+": 1.82e-3}) == "The circuit draws 1.82 mA from V+."
    assert supply_text({"V-": -393e-6}) == "The circuit draws 393 µA from V-."
    both = supply_text({"V+": 2e-3, "V-": -1e-3})
    assert both == "The circuit draws 2 mA from V+, 1 mA from V- (3 mA in all)."
    assert supply_text({}) == "The circuit has no supply."


def _sheet(**changes: object) -> BiasSheet:
    base: dict[str, object] = {
        "trimmers": ["Set TR1 until Q2's collector reads \u22120.16 V."],
        "pots": [],
        "parts": [
            PartReadings("Q1", "2N5089", [PinReading("C", 3, 4.2), PinReading("B", 2, 0.65)])
        ],
        "supply": {"V+": 1e-3},
        "warnings": [],
    }
    return BiasSheet(**(base | changes))  # type: ignore[arg-type]


def test_the_page_has_only_the_sections_it_needs() -> None:
    c = CircuitBuilder("Fuzz <one>").build()
    text = bias_page(c, _sheet())
    assert "<h1>Fuzz &lt;one&gt;</h1>" in text and "Bias sheet · v1" in text
    assert "<h2>Trimmers</h2>" in text and "Q2&#x27;s collector" in text
    assert "Check first" not in text and "Pots that move" not in text
    assert "<td>Q1</td><td>2N5089</td><td>3</td><td>C</td>" in text
    assert "<td></td><td></td><td>2</td><td>B</td>" in text  # the part named once
    assert "1 mA from V+" in text


def test_a_warning_comes_first() -> None:
    text = bias_page(
        CircuitBuilder("x").build(), _sheet(warnings=["Q1 is saturated."], trimmers=[])
    )
    assert text.index("Check first") < text.index("Current drawn")
    assert "<h2>Trimmers</h2>" not in text
