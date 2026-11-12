"""`CircuitBuilder.from_spec`: rule fixtures written as plain data."""

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect


def test_a_spec_builds_the_same_circuit_as_the_calls() -> None:
    spec = {
        "name": "divider",
        "rails": {"V+": 9},
        "probes": {"in": "a", "out": "b"},
        "parts": [
            {"ref": "R1", "type": "resistor", "nets": ["V+", "a"], "value": "10k"},
            {"ref": "SW1", "type": "switch", "kind": "spdt", "pins": {"2": "a", "1": "b"}},
        ],
        "template": True,
    }
    built = CircuitBuilder.from_spec(spec).build()
    by_hand = (
        CircuitBuilder("divider")
        .rail("V+", 9)
        .probe("a", "b")
        .part("R1", "resistor", "V+", "a", value="10k")
        .part("SW1", "switch", kind="spdt", pins={"2": "a", "1": "b"})
    )
    by_hand.extra = {"template": True}
    assert built == by_hand.build()
    assert built.template and built.power.rails == {"V+": 9}
    assert connect(built).net_of("SW1", "1") == "b"


def test_extra_labels_are_added() -> None:
    spec = {"parts": [{"ref": "R1", "type": "resistor", "nets": ["a", None], "value": "1k"}],
            "labels": [{"net": "x", "pos": [120, 100]}]}  # fmt: skip
    assert connect(CircuitBuilder.from_spec(spec).build()).net_of("R1", "2") == "x"
