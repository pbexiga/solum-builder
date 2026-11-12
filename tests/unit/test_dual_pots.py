"""Dual-gang pots (v24, D-217): one pot of two gangs, VR1A and VR1B, turned by one knob."""

from pathlib import Path

import pytest

from solum.build_notes import knobs
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import SCHEMA_VERSION, Circuit, Pot
from solum.export import bom
from solum.live import slider
from solum.models import load_models
from solum.view import controls

LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])
OLD_V23 = Path(__file__).parents[1] / "fixtures" / "circuits" / "old" / "schema-v23.json"


def dual(**b: object) -> CircuitBuilder:
    """A 250kA dual pot, VR1A from `in` to ground and VR1B from `x` to ground."""
    gang = {"value": "250k", "taper": "A", "rotation": 0.5, "label": "Drive"}
    return (
        CircuitBuilder()
        .part("R1", "resistor", "in", "x", value="10k")
        .part("VR1A", "pot", "in", "out", "GND", gang="a", **gang)
        .part("VR1B", "pot", "x", "y", "GND", gang="b", **(gang | b))
    )


def test_a_dual_pots_gangs_are_one_knob() -> None:
    c = dual().build()
    assert [p.knob for p in c.parts if isinstance(p, Pot)] == ["VR1", "VR1"]
    knob = [k for k in controls(c) if k["kind"] == "pot"]
    assert [(k["ref"], k["label"], k["refs"]) for k in knob] == [("VR1", "Drive", ["VR1A", "VR1B"])]


def test_its_name_turns_both_gangs_and_finds_gang_a() -> None:
    c = dual().build().with_part("VR1", rotation=0.2)
    assert [getattr(c.part(r), "rotation") for r in ("VR1A", "VR1B")] == [0.2, 0.2]  # noqa: B009
    assert c.part("VR1").ref == "VR1A"


@pytest.mark.parametrize("field", ["value", "taper", "rotation", "label"])
def test_its_gangs_agree(field: str) -> None:
    other = {"value": "500k", "taper": "B", "rotation": 0.9, "label": "Tone"}[field]
    with pytest.raises(ValueError, match="gangs of one pot"):
        dual(**{field: other}).build()


def test_both_gangs_are_in_the_file() -> None:
    with pytest.raises(ValueError, match="VR1B isn't in the file"):
        CircuitBuilder().part("VR1A", "pot", "a", "b", "GND", value="250k", gang="a").build()


@pytest.mark.parametrize(("ref", "gang"), [("VR1", "a"), ("VR1A", None), ("VR1B", "a")])
def test_a_gangs_ref_ends_in_its_letter(ref: str, gang: str | None) -> None:
    with pytest.raises(ValueError):
        Pot(ref=ref, type="pot", value="250k", gang=gang)  # type: ignore[arg-type]


def test_the_parts_list_has_one_dual_pot_and_one_knob() -> None:
    lines = bom(dual().build(), MODELS)
    pots = [x for x in lines if x.part == "Pot"]
    assert [(x.value, x.details, x.refs) for x in pots] == [
        ("A250k", "log (A), dual gang", ("VR1 (Drive)",))
    ]
    assert [x.refs for x in lines if x.part == "Knob"] == [("VR1 (Drive)",)]
    assert [(k.ref, k.what) for k in knobs(dual().build())] == [("VR1", "A250k dual gang, log (A)")]


def test_the_knobs_slider_moves_both_gangs() -> None:
    s = slider(dual().build(), MODELS, "VR1", "rotation")
    first, last = s["steps"][0]["elements"], s["steps"][-1]["elements"]
    gang_b = [k for k in first if "VR1B" in k]
    assert gang_b and all(first[k] != last[k] for k in gang_b)
    assert any("VR1A" in k and first[k] != last[k] for k in first)


def test_a_v23_file_loads_as_v24_with_single_pots() -> None:
    c = load_circuit(OLD_V23)
    assert c.schema_ == SCHEMA_VERSION
    assert all(p.gang is None for p in c.parts if isinstance(p, Pot))


def test_the_bd2s_drive_is_one_dual_pot(repo: Path) -> None:
    c: Circuit = load_circuit(repo / "library" / "starters" / "boss-bd2-aion.json")
    drive = [k for k in controls(c) if k["label"] == "Drive"]
    assert [k["refs"] for k in drive] == [["VR1A", "VR1B"]]
