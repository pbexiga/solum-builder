"""File → Export (9d1, D-203): the parts list, grouped, on and off the board (no ngspice)."""

import csv
import io
import json
import urllib.request
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Enclosure
from solum.export import (
    BOM_COLUMNS,
    CHECKLIST,
    BomLine,
    bom,
    bom_csv,
    bom_page,
    pdf,
    schematic_page,
    schematic_sheet,
    watts_text,
)
from solum.models import load_models

LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])


def parts(lines: list[BomLine]) -> list[BomLine]:
    return [x for x in lines if x.where != "hardware"]


def lines_of(builder: CircuitBuilder) -> list[BomLine]:
    """The parts, without the hardware."""
    return parts(bom(builder.build(), MODELS))


def test_the_ts808_parts_list_matches_its_file() -> None:
    """Checked by hand against library/starters/ts808.json: 17 resistors, 11 capacitors,
    2 diodes, 2 transistors, one RC4558 (its power unit isn't another chip), 3 pots, and the
    input and output jacks (none drawn)."""
    lines = parts(bom(load_circuit(LIBRARY / "starters" / "ts808.json"), MODELS))
    by_part: dict[str, int] = {}
    for line in lines:
        by_part[line.part] = by_part.get(line.part, 0) + line.quantity
    assert by_part == {"Resistor": 17, "Capacitor": 11, "Diode": 2, "Transistor": 2,
                       "Op-amp": 1, "Pot": 3, "Jack": 2}  # fmt: skip
    ten_k = next(x for x in lines if x.part == "Resistor" and x.value == "10k")
    assert ten_k.refs == ("R3", "R5", "R9", "R14", "R32", "R33", "R35")
    assert ten_k.details == "¼ W" and ten_k.where == "board"
    chip = next(x for x in lines if x.part == "Op-amp")
    assert (chip.value, chip.details, chip.refs) == ("RC4558", "8-pin DIP", ("IC1",))
    q = next(x for x in lines if x.part == "Transistor")
    assert q.refs == ("Q1", "Q3") and q.details.endswith(": 1 E, 2 C, 3 B")
    assert [x.value for x in lines if x.part == "Resistor"] == [
        "100",
        "220",
        "1k",
        "4k7",
        "10k",
        "51k",
        "510k",
    ]  # fmt: skip  (by value, not as text)
    pots = [x for x in lines if x.part == "Pot"]
    assert all(x.where == "off-board" for x in pots)
    assert {x.refs for x in pots} == {("VR1 (Distortion)",), ("VR2 (Tone)",), ("VR3 (Level)",)}
    assert lines[-1].part == "Jack" and lines[-1].refs == ("IN (Input)", "OUT (Output)")


def test_identical_parts_group_and_different_ones_do_not() -> None:
    lines = lines_of(
        CircuitBuilder()
        .part("C2", "capacitor", "a", "GND", value="100n", kind="film")
        .part("C10", "capacitor", "a", "GND", value="100n", kind="film")
        .part("C3", "capacitor", "a", "GND", value="100n", kind="ceramic")
        .part("C1", "capacitor", "a", "GND", value="10u", kind="electrolytic", rating_v=16)
        .part("C4", "capacitor", "a", "GND", value="10u", kind="electrolytic")
        .part("C5", "capacitor", "a", "GND", value="1n")
    )
    assert [(x.value, x.details, x.refs) for x in lines] == [
        ("1n", "type not set", ("C5",)),
        ("100n", "film", ("C2", "C10")),  # equal values: by their first ref
        ("100n", "ceramic (X7R)", ("C3",)),
        ("10µ", "electrolytic, 16 V", ("C1",)),
        ("10µ", "electrolytic, voltage rating not set", ("C4",)),
    ]


def test_a_chip_and_a_switch_are_one_line_each_however_many_units_or_poles() -> None:
    lines = lines_of(
        CircuitBuilder()
        .rail("V+", 9)
        .part("IC1A", "opamp", "a", "b", "b", model="TL072", half="a")
        .part("IC1B", "opamp", "a", "c", "c", model="TL072", half="b")
        .part("SW1A", "switch", "a", "b", "c", kind="dpdt", pole="a", label="Mode")
        .part("SW1B", "switch", "a", "b", "c", kind="dpdt", pole="b", label="Mode")
    )
    assert [(x.part, x.value, x.refs, x.where) for x in lines if x.part != "Jack"] == [
        ("Op-amp", "TL072", ("IC1",), "board"),
        ("Switch", "DPDT toggle", ("SW1 (Mode)",), "off-board"),
    ]


def test_a_dip_switch_is_on_the_board() -> None:
    """D-238: a DIP sits on the board (Aion's internal gain DIP), not on the box like a toggle."""
    lines = lines_of(
        CircuitBuilder()
        .rail("V+", 9)
        .part("SW1A", "switch", "a", "b", kind="dip-2", pole="a", label="Gain")
        .part("SW1B", "switch", "a", "c", kind="dip-2", pole="b", label="Gain")
    )
    assert [(x.part, x.value, x.refs, x.where) for x in lines if x.part == "Switch"] == [
        ("Switch", "DIP switch, 2 positions", ("SW1 (Gain)",), "board"),
    ]


def test_off_board_by_type_and_the_status_led() -> None:
    lines = lines_of(
        CircuitBuilder()
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "a", value="4k7", rating_w=0.5)
        .part("LED1", "led", "a", "GND", model="WP7113GD", label="Status")
        .part("LED2", "led", "a", "GND", model="WP7113GD")
        .part("DC", "dcjack", "V+", "GND")
        .part("BAT1", "battery", "b", "GND")
        .part("J1", "jack", "c", "GND", stereo=True, label="Input")
        .part("J2", "jack", "d", "GND", label="Output")
    )
    rows = [(x.where, x.part, x.value, x.details, x.refs) for x in lines]
    assert rows[0] == ("board", "Resistor", "4k7", "½ W", ("R1",))
    assert rows[1][:3] == ("board", "LED", "WP7113GD") and rows[1][4] == ("LED2",)
    off = [r for r in rows if r[0] == "off-board"]
    assert [(r[1], r[4]) for r in off] == [
        ("LED", ("LED1 (Status)",)),
        ("Jack", ("J1 (Input)",)),  # mono and stereo are different parts
        ("Jack", ("J2 (Output)",)),
        ("DC jack", ("DC",)),
        ("Battery", ("BAT1",)),
    ]
    assert {r[3] for r in off if r[1] == "Jack"} == {"mono (TS)", "stereo (TRS)"}


def test_measured_transistors_are_bought_separately() -> None:
    lines = lines_of(
        CircuitBuilder()
        .part("Q2", "bjt", "a", "b", "GND", model="AC128", measured={"hfe": 80})
        .part("Q1", "bjt", "a", "b", "GND", model="AC128", measured={"hfe": 80})
        .part("Q3", "bjt", "a", "b", "GND", model="AC128")
    )
    q = [x for x in lines if x.part == "Transistor"]
    assert [x.refs for x in q] == [("Q1", "Q2"), ("Q3",)]
    assert q[0].details.endswith("picked for hFE 80")


def test_a_model_with_no_package_says_so(tmp_path: Path) -> None:
    """Every library model has a package, so a user's model without one is made here."""
    record = json.loads((LIBRARY / "models" / "chargepump" / "ICL7660.json").read_text())
    del record["package"]
    (tmp_path / "chargepump").mkdir()
    (tmp_path / "chargepump" / "ICL7660.json").write_text(json.dumps(record))
    circuit = CircuitBuilder().rail("V+", 9).part("IC1", "chargepump", "V+", "o", "GND",
                                                  model="ICL7660").build()  # fmt: skip
    lines = parts(bom(circuit, load_models([tmp_path])))
    assert lines[0].details == "package not in its model: check the datasheet"


def test_csv_and_page() -> None:
    lines = bom(load_circuit(LIBRARY / "starters" / "fuzz-face.json"), MODELS)
    rows = list(csv.reader(io.StringIO(bom_csv(lines))))
    assert tuple(rows[0]) == BOM_COLUMNS
    assert len(rows) == len(lines) + 1 + len(CHECKLIST)
    assert sum(int(r[1]) for r in rows[1:] if r[1]) == sum(x.quantity for x in lines)
    assert rows[-1][0] == "Also" and rows[-1][1] == ""
    page = bom_page(load_circuit(LIBRARY / "starters" / "fuzz-face.json"), lines)
    for title in ("On the board", "Off the board", "Hardware", "Also"):
        assert f"<h2>{title}</h2>" in page
    assert "v1.0 \u00b7" in page and "vv" not in page
    assert "AC128" in page and "http" not in page  # nothing to fetch


def test_watts() -> None:
    assert watts_text(0.25) == "¼ W"
    assert watts_text(2.0) == "2 W"


def test_one_drawn_jack_leaves_the_other_end_counted() -> None:
    """A jack drawn on the input (its tip on the guitar's net) stands for IN; the output
    still needs one. A drawn jack is matched by its wiring, else by its label."""
    wired = lines_of(
        CircuitBuilder()
        .part("IN", "guitar", "in")
        .part("J1", "jack", "in", "GND", stereo=True)
        .part("R1", "resistor", "in", "out", value="1k")
        .part("OUT", "amp", "out")
    )
    jacks = [(x.details, x.refs) for x in wired if x.part == "Jack"]
    assert jacks == [("stereo (TRS)", ("J1",)), ("mono (TS)", ("OUT (Output)",))]
    labelled = lines_of(
        CircuitBuilder()
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="1k")
        .part("OUT", "amp", "out")
        .part("J2", "jack", "x", "GND", label="Output")
    )
    assert [x.refs for x in labelled if x.part == "Jack"] == [("IN (Input)", "J2 (Output)")]


def test_hardware_follows_the_parts() -> None:
    """D-204: the enclosure (chosen or not), a knob per pot, a socket per DIP chip, a bezel
    for the status LED and the battery's clip."""
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("VR2", "pot", "a", "b", "GND", value="100k", label="Tone")
        .part("VR1", "pot", "a", "b", "GND", value="100k", label="Gain")
        .part("IC1A", "opamp", "a", "b", "b", model="TL072", half="a")
        .part("IC1B", "opamp", "a", "c", "c", model="TL072", half="b")
        .part("IC2", "opamp", "a", "d", "d", model="TL071")
        .part("LED1", "led", "a", "GND", model="WP7113GD", label="Status")
        .part("BAT1", "battery", "V+", "GND")
    )
    lines = [x for x in bom(c.build(), MODELS) if x.where == "hardware"]
    rows = [(x.part, x.value, x.quantity, x.refs) for x in lines]
    assert rows[0] == ("Enclosure", "not chosen", 1, ())
    assert ("Knob", "", 2, ("VR1 (Gain)", "VR2 (Tone)")) in rows
    assert ("IC socket", "8-pin DIP", 2, ("IC1", "IC2")) in rows
    assert ("LED bezel", "", 1, ("LED1 (Status)",)) in rows
    assert ("Battery clip", "9 V snap", 1, ("BAT1",)) in rows
    chosen = c.build().model_copy(update={"enclosure": Enclosure(size="1590B")})
    box = bom(chosen, MODELS)[-5]
    assert (box.value, box.details) == ("1590B", "112 \u00d7 60.5 \u00d7 31 mm outside")


def test_pages_become_pdfs_and_fetch_nothing_from_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-205: WeasyPrint makes each page a PDF; a schematic from the browser can't make the
    server fetch a URL (only data: and the app's own files)."""
    c = load_circuit(LIBRARY / "starters" / "tone-bender-mk2-mode.json")
    web = LIBRARY.parent / "web"
    parts_pdf = pdf(bom_page(c, bom(c, MODELS)), web)
    assert parts_pdf.startswith(b"%PDF") and len(parts_pdf) > 5000
    svg = (LIBRARY.parent / "tests" / "fixtures" / "schematic-tone-bender.svg").read_text()
    drawn = pdf(schematic_page(c, svg), web)
    assert drawn.startswith(b"%PDF")
    page_html = schematic_page(c, svg)
    assert "data:image/svg+xml;base64," in page_html and "297mm 210mm" in page_html
    called = []
    sneaky = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><image href="http://example.invalid/x.png"/></svg>'

    monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", lambda _s, r: called.append(r))
    assert pdf(schematic_page(c, sneaky), web).startswith(b"%PDF")
    assert called == []


@pytest.mark.parametrize(
    ("width", "height", "sheet", "text_mm"),
    [
        (900, 500, "A4", 2.73),  # a starter-sized drawing fills A4 (273 mm across)
        (200, 100, "A4", 3.5),  # a small one grows only until its text is 3.5 mm
        (1500, 600, "A3", 2.38),  # on A4 its text would be 1.6 mm: A3
        (4000, 2000, "A3", 0.89),  # too big even for A3: still one sheet
    ],
)
def test_a_schematic_fills_one_sheet(
    width: float, height: float, sheet: str, text_mm: float
) -> None:
    name, _, _, scale = schematic_sheet(width, height)
    assert name == sheet
    assert scale * 9 == pytest.approx(text_mm, abs=0.01)
