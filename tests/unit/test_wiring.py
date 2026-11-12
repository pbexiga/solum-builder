"""The generic wiring page (9d1, D-209): its drawings, their sources, the positive-ground note."""

import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.wiring import DIAGRAMS, positive_ground, wiring_page

LIBRARY = Path(__file__).resolve().parents[2] / "library"
WIRING = LIBRARY / "wiring"


def test_every_drawing_is_an_svg_with_its_source() -> None:
    listed = {f["file"]: f for f in yaml.safe_load((WIRING / "sources.yaml").read_text())["files"]}
    assert set(listed) == {d.file for d in DIAGRAMS} == {p.name for p in WIRING.glob("*.svg")}
    for d in DIAGRAMS:
        root = ET.parse(WIRING / d.file).getroot()
        assert root.get("viewBox") and root.get("class") == "wiring"
        assert listed[d.file]["sources"] and listed[d.file]["follows"]


def test_the_page_carries_each_drawing_styled_inside_it() -> None:
    text = wiring_page(load_circuit(LIBRARY / "starters" / "ts808.json"), WIRING)
    assert text.count('<svg xmlns="http://www.w3.org/2000/svg"') == 3
    assert text.count("<style>.w-wire") == 3 and "stroke: #1E1E1B" in text
    assert "<?xml" not in text and "positive ground" not in text
    assert "Footswitch: 3PDT true bypass" in text and "Wiring · v1.0" in text


def test_a_positive_ground_circuit_is_warned() -> None:
    tone_bender = load_circuit(LIBRARY / "starters" / "tone-bender-mk2.json")
    assert positive_ground(tone_bender)
    assert "positive ground" in wiring_page(tone_bender, WIRING)
    assert not positive_ground(CircuitBuilder("x").rail("V+", 9.0).build())
    both = CircuitBuilder("x").rail("V+", 9.0).rail("V-", -9.0).build()
    assert not positive_ground(both)  # a bipolar supply isn't positive ground
