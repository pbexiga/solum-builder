"""The build notes page (9d1): description, sheet and part notes, knobs and switches."""

from pathlib import Path

from solum.build_notes import item_notes, knobs, notes_page, sheet_texts, switches
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Note, TextBlock

LIBRARY = Path(__file__).resolve().parents[2] / "library"


def test_the_ts808_knobs_as_saved() -> None:
    got = knobs(load_circuit(LIBRARY / "starters" / "ts808.json"))
    assert [(k.ref, k.name, k.what, k.setting) for k in got] == [
        ("VR1", "Distortion", "A500k, log (A)", "at 50% of its turn"),
        ("VR2", "Tone", "W20k, W taper", "at 50% of its turn"),
        ("VR3", "Level", "A100k, log (A)", "at 100% of its turn"),
    ]


def test_a_switch_of_two_poles_is_one_switch_with_its_positions() -> None:
    got = switches(load_circuit(LIBRARY / "starters" / "tone-bender-mk2-mode.json"))
    assert len(got) == 1
    mode = got[0]
    assert (mode.ref, mode.name) == ("SW1", "Mode")
    assert mode.positions == ("MkII", "1.5") and mode.setting == "MkII"  # named (9d2)


def test_notes_on_parts_and_nets_by_ref() -> None:
    c = load_circuit(LIBRARY / "starters" / "ts808.json")
    assert [k for k, _ in item_notes(c, "part")] == ["C3", "C4", "C5"]
    assert [k for k, _ in item_notes(c, "net")] == ["VREF", "q1e", "u2o"]


def test_sheet_texts_read_top_to_bottom() -> None:
    c = CircuitBuilder("x").build()
    low, high = TextBlock(title="Low", pos=(0, 300)), TextBlock(text="High", pos=(400, 10))
    c = c.model_copy(update={"texts": [low, high]})
    assert [t.title or t.text for t in sheet_texts(c)] == ["High", "Low"]


def test_the_page() -> None:
    c = load_circuit(LIBRARY / "starters" / "tone-bender-mk2-mode.json")
    text = notes_page(c)
    assert "<h1>Tone Bender" in text and "Notes · v" in text
    assert "<h2>Knobs</h2>" in text and "Fuzz (VR2)" in text
    assert "<h2>Switches</h2>" in text and "<strong>" in text
    assert "Aion FX" in text  # the description


def test_a_bare_circuit_says_it_has_no_description() -> None:
    text = notes_page(CircuitBuilder("<b>").build())
    assert "No description yet" in text and "&lt;b&gt;" in text
    assert "Knobs" not in text and "On the parts" not in text


def test_general_part_and_net_notes_on_the_page() -> None:
    """9d4: the general notes after the description, in their order; part and net notes
    in their lists."""
    c = CircuitBuilder("x").part("R1", "resistor", "a", "b", value="10k", note="sets the gain")
    c = c.build().model_copy(update={
        "notes": [Note(title="Build", text="Socket Q1."), Note(text="Untitled")],
        "net_notes": {"VREF": "half the supply"},
    })  # fmt: skip
    text = notes_page(c)
    assert text.index("<h3>Build</h3>") < text.index("Socket Q1.") < text.index("Untitled")
    assert "<strong>R1</strong>: sets the gain" in text
    assert "<strong>VREF</strong>: half the supply" in text


def test_the_big_muffs_versions_are_notes_not_sheet_text() -> None:
    """9d4 follow-up (D-268): one general note per version; only the credit stays on the sheet."""
    c = load_circuit(LIBRARY / "starters" / "big-muff-aion-halo.json")
    titles = [n.title for n in c.notes]
    assert titles[0] == "Big Muff versions"
    assert len([t for t in titles if t.startswith("Version: ")]) == 19
    assert next(n for n in c.notes if n.title == "Version: Foxey Lady").text.startswith("R6 15k")
    assert [t.title for t in c.texts] == ["Credit"]
