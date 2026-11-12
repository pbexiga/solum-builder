"""The one test jig for blocks: a block made runnable on its own, so sim, parity and
reference tests can measure it."""

from pathlib import Path
from typing import Any

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.circuit.schema import Circuit
from solum.store import resolve_id
from solum.units import format_value

BLOCKS = Path(__file__).parents[1] / "library" / "blocks"
FAR = -100_000  # the jig's parts are drawn far from the block
# the jig's own resistors: numbered past any block's, refs being R and a number (D-141)
JIG_RS, JIG_LOAD, JIG_VREF = "R901", "R902", ("R903", "R904")


def core_block(block_id: str) -> Circuit:
    """A core block by id: its current version, or a version's id."""
    found = resolve_id((p.stem for p in BLOCKS.glob("*.json")), block_id)
    return load_circuit(BLOCKS / f"{found}.json")


def with_values(block: Circuit, values: dict[str, dict[str, Any]]) -> Circuit:
    """`block` with some parts' fields changed (`{"VR1": {"rotation": 0.3}}`)."""
    for ref, fields in values.items():
        block = block.with_part(ref, **fields)
    return block


def jig(
    block: Circuit,
    source_ohms: float = 0.0,
    load_ohms: float = 1e6,
    far: int = FAR,
    supply_load: float | None = None,
) -> Circuit:
    """`block` with an ideal guitar behind `source_ohms` (0: none) on its `in` port and an
    amp of `load_ohms` on `out` (when it has both, and `out` isn't a supply), and a
    100k/100k divider from V+ on a `vref` port; joined to the block by labels, drawn
    `far` away (nearer for a sheet a UI test looks at). A power block (an `out`, no `in`)
    gets a `supply_load` resistor on `out`, when given, and a guitar through 1M so
    transient runs have an input."""
    ports = block.ports
    b = CircuitBuilder("jig")
    probes = None
    if "in" in ports and "out" in ports and ports["out"] not in ("V+", "V-"):
        inp, out = ports["in"], ports["out"]
        if source_ohms > 0:
            b.part("IN", "guitar", "jig_src")
            b.part(JIG_RS, "resistor", "jig_src", inp, value=format_value(source_ohms, 6))
        else:
            b.part("IN", "guitar", inp)
        b.part("OUT", "amp", out, value=format_value(load_ohms, 6))
        probes = {"in": inp, "out": out}
    if supply_load is not None and "out" in ports and "in" not in ports:
        b.part("IN", "guitar", "jig_src")
        b.part(JIG_RS, "resistor", "jig_src", ports["out"], value="1M")
        b.part(JIG_LOAD, "resistor", ports["out"], "0", value=format_value(supply_load, 6))
    if "vref" in ports:
        b.part(JIG_VREF[0], "resistor", "V+", ports["vref"], value="100k")
        b.part(JIG_VREF[1], "resistor", ports["vref"], "0", value="100k")

    def moved(item: dict[str, Any]) -> dict[str, Any]:
        x, y = item["pos"]
        return {**item, "pos": [x + far, y + far]}

    data = circuit_to_dict(block)
    data.update(
        parts=[*data["parts"], *map(moved, b.parts)],
        labels=[*data.get("labels", []), *map(moved, b.labels)],
        template=False,
        ports={},
    )
    if probes:
        data["probes"] = probes
    return parse_circuit(data)
