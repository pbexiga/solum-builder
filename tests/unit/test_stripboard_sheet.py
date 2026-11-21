"""The kept board in the build package (P6e, D-386): re-checked before it goes in, its
lists, and its page (each side filled to read, then both at real size)."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import load_circuit, parse_circuit
from solum.circuit.schema import Circuit
from solum.export import fill_sheet
from solum.guides import footprint_table
from solum.models import load_models
from solum.package import index_page
from solum.stripboard.board import layout_data, layout_from_data
from solum.stripboard.sheet import (
    Drawings,
    lists_for,
    packaged_board,
    real_fit,
    size_text,
    stripboard_page,
)
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def with_board(data: dict[str, Any], circuit: Circuit = RANGEMASTER) -> Circuit:
    dumped = circuit.model_dump(mode="json", by_alias=True, exclude_none=True)
    return parse_circuit({**dumped, "stripboard": layout_data(layout_from_data(data))})


def svg(width: float, height: float) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-6 -6 {width} {height}">'
            "<circle cx='0' cy='0' r='1'/></svg>")  # fmt: skip


def test_a_checked_board_goes_in_with_the_nets_it_carries() -> None:
    kept = packaged_board(with_board(GOOD), MODELS, TABLE)
    assert kept.layout is not None and kept.why == ""
    assert kept.nets == 8


def test_no_board_kept_is_a_note_not_a_fault() -> None:
    kept = packaged_board(RANGEMASTER, MODELS, TABLE)
    assert kept.layout is None and kept.why == "No stripboard layout kept."


def test_a_stale_board_is_left_out_saying_what_doesnt_match() -> None:
    """The circuit changed after the board was laid out (R2 gone): never packaged."""
    dumped = RANGEMASTER.model_dump(mode="json", by_alias=True, exclude_none=True)
    dumped["parts"] = [p for p in dumped["parts"] if p["ref"] != "R2"]
    dumped["wires"] = []  # its wires went with it; the check reads the board only
    kept = packaged_board(with_board(GOOD, parse_circuit(dumped)), MODELS, TABLE)
    assert kept.layout is None
    assert kept.why.startswith("The stripboard layout doesn't match the circuit as saved")
    assert "R2" in kept.why and kept.why.endswith("Open the Board view to finish it.")


def test_the_lists_name_each_hole_and_number_the_wires_in_the_parts_order() -> None:
    c = with_board(GOOD)
    assert c.stripboard is not None
    lists = lists_for(c.stripboard.layout(), c, MODELS, TABLE)
    assert lists.size == (12, 9)
    assert lists.cuts == ["G8"]
    assert lists.links == ["B1–B8", "K2–K8"]
    assert lists.wires == [
        "VR1 (Volume) lug 1 to D1", "VR1 (Volume) lug 2 to A7", "VR1 (Volume) lug 3 to A5",
        "IN (Input) tip to A6", "IN (Input) sleeve to D2",
        "OUT (Output) tip to A9", "OUT (Output) sleeve to IN (Input) sleeve",
        "Power V- to A1", "Power GND to A2",
    ]  # fmt: skip


def test_size_in_holes_and_mm() -> None:
    assert size_text((12, 9)) == "12 × 9 holes (30 × 23 mm)"


def test_the_two_sides_at_real_size_go_the_way_they_fit() -> None:
    assert real_fit((30, 23), (30, 23)) == (False, True, 1.0)  # side by side, portrait
    assert real_fit((97, 112), (97, 112)) == (True, True, 1.0)  # the TS808's: landscape
    assert real_fit((150, 100), (150, 100)) == (False, False, 1.0)  # one above the other
    *_, scale = real_fit((300, 300), (300, 300))
    assert scale < 1.0  # bigger than any A4 way: shrunk, and the page says so


def test_a_tall_side_is_filled_onto_a_portrait_sheet_readable() -> None:
    """A board 40 × 50 holes (400 × 500 units, labels 3.2 units): A4 can't keep its text
    at 2 mm, A3 portrait fills best."""
    sheet, w, h, scale = fill_sheet(400, 500, 3.2, (False, True), 14)
    assert (sheet, w, h) == ("A3", 297.0, 420.0)
    assert scale * 3.2 >= 2.0


def test_the_page_says_its_checked_and_has_the_lists_and_both_scales() -> None:
    c = with_board(GOOD)
    assert c.stripboard is not None
    lists = lists_for(c.stripboard.layout(), c, MODELS, TABLE)
    drawn = Drawings(svg(250, 200), svg(130, 100), svg(130, 100))
    text = stripboard_page(c, drawn, lists, 8)
    assert "Every connection on this board matches the circuit (8 nets)." in text
    assert "Stripboard · v1.0 · 12 × 9 holes (30 × 23 mm)" in text
    assert "<li>G8</li>" in text and "<li>B1–B8</li>" in text
    assert '<ol class="wires"><li>VR1 (Volume) lug 1 to D1</li>' in text
    assert "@page parts { size: 297mm 210mm" in text  # filled onto A4, landscape
    assert "At real size" in text and "this line is 25.4 mm" in text
    assert "width: 33.02mm; height: 25.40mm" in text  # 130 × 100 units at 0.254 mm


def test_a_drawing_without_a_view_box_is_refused() -> None:
    c = with_board(GOOD)
    assert c.stripboard is not None
    lists = lists_for(c.stripboard.layout(), c, MODELS, TABLE)
    with pytest.raises(ValueError):
        stripboard_page(c, Drawings("<svg/>", svg(1, 1), svg(1, 1)), lists, 8)


def test_the_index_lists_the_board_when_it_went_in() -> None:
    text = index_page(RANGEMASTER, ["circuit.json", "stripboard.pdf"], [], 0)
    assert '<a href="stripboard.pdf">' in text
