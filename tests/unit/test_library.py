"""Blocks: core and My blocks both listed, core never changes, saving My blocks."""

from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import parse_circuit, save_circuit
from solum.circuit.schema import Circuit
from solum.library import BlockLibrary
from solum.store import StoreError


def divider(circuit: Callable[[str], CircuitBuilder], name: str = "Vref divider",
            top: str = "10k") -> Circuit:  # fmt: skip
    data = (
        circuit(name)
        .part("R1", "resistor", "V+", "VREF", value=top)
        .part("R2", "resistor", "VREF", "GND", value="10k")
        .part("C1", "capacitor", "VREF", "GND", value="47u")
        .rail("V+", 9.0)
        .data()
    )
    return parse_circuit({**data, "template": True, "ports": {"vref": "VREF"}})


@pytest.fixture
def lib(tmp_path: Path, circuit: Callable[[str], CircuitBuilder]) -> BlockLibrary:
    core = tmp_path / "library" / "blocks"
    save_circuit(divider(circuit), core / "vref-divider-v1.json")
    (core / "broken.json").write_text("{", encoding="utf-8")
    return BlockLibrary(core, tmp_path / "data", tmp_path / "cache")


def test_core_blocks_are_listed_and_read_only(lib: BlockLibrary) -> None:
    entries = lib.entries()
    assert [(e.id, e.layer) for e in entries] == [("broken", "core"), ("vref-divider-v1", "core")]
    broken, vref = entries
    assert broken.problem and "isn't valid JSON" in broken.problem
    assert (vref.name, vref.ports, vref.version, vref.final) == (
        "Vref divider",
        ["vref"],
        "v1.0",
        False,
    )
    block, layer = lib.get("vref-divider")
    assert (layer, block.template) == ("core", True)
    with pytest.raises(StoreError, match="no block called 'vref-divider' in My blocks"):
        lib.save(block)
    with pytest.raises(StoreError, match="can't be deleted"):
        lib.delete("vref-divider")
    with pytest.raises(StoreError, match="no block called 'nope'"):
        lib.get("nope")


def test_my_blocks_sit_beside_core_ones_with_the_same_name(
    lib: BlockLibrary, circuit: Callable[[str], CircuitBuilder]
) -> None:
    """A core block edited and saved under its own name goes to My blocks; the core one
    is listed and found as before (D-075)."""
    core = lib.get("vref-divider", "core")[0]
    c = core.with_part("R1", value="22k").model_copy(
        update={"template": False, "version": core.version}
    )
    made = lib.create(c, "Vref divider")
    assert (made.id, made.template, made.starter, str(made.version)) == (
        "vref-divider-v1",
        True,
        False,
        "v1.0",
    )
    assert [(e.id, e.layer, e.current) for e in lib.entries("vref")] == [
        ("vref-divider-v1", "user", True),
        ("vref-divider-v1", "core", True),
    ]
    assert (lib.link("vref-divider-v1", "core"), lib.link("vref-divider-v1", "user")) == (
        "vref-divider",
        "vref-divider",
    )
    assert lib.get("vref-divider", "core")[0] == core
    assert lib.get("vref-divider")[1] == "user"
    with pytest.raises(StoreError, match="already have a block called Vref divider"):
        lib.create(c, "Vref Divider")
    saved = lib.save(made.with_part("R2", value="1k"))
    assert str(saved.version) == "v1.1" and saved.template is True
    lib.delete("vref-divider")
    with pytest.raises(StoreError, match="no block called 'nope-not-here' in My blocks"):
        lib.delete("nope-not-here")
    assert lib.get("vref-divider")[0] == core


def test_search_and_names(lib: BlockLibrary, circuit: Callable[[str], CircuitBuilder]) -> None:
    c = divider(circuit)
    assert [e.id for e in lib.entries("47u")] == []  # values aren't searched
    assert [e.id for e in lib.entries("brok")] == ["broken"]  # unreadable: found by id
    with pytest.raises(StoreError, match="Give the block a name"):
        lib.create(c, " ")
    with pytest.raises(StoreError, match="no block called 'x' in My blocks"):
        lib.save(c.model_copy(update={"id": "x"}))
