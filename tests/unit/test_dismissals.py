"""Dismissed problems in the circuit file (D-176): the field, and what a save keeps."""

from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.dismissals import kept_dismissals
from solum.circuit.io import CircuitError, circuit_to_dict, parse_circuit
from solum.circuit.schema import REASON_MAX, Circuit, Dismissal
from solum.store import CircuitStore


@pytest.fixture
def fuzz(circuit: Callable[[str], CircuitBuilder]) -> Circuit:
    return (
        circuit("Fuzz")
        .part("Q1", "bjt", "c", "b", "GND", model="AC128")
        .part("R1", "resistor", "c", "V+", value="33k")
        .part("C1", "capacitor", "in", "b", value="100n")
        .build()
    )


def dismissed(c: Circuit, *found: Dismissal) -> Circuit:
    return c.model_copy(update={"dismissed": list(found)})


def test_a_dismissal_round_trips_and_an_empty_list_stays_out_of_the_file(fuzz: Circuit) -> None:
    assert "dismissed" not in circuit_to_dict(fuzz)
    data = circuit_to_dict(fuzz) | {
        "dismissed": [{"rule": "bjt-cut-off", "refs": ["Q1"], "reason": "a µ-power fuzz"}]
    }
    c = parse_circuit(data)
    assert c.dismissed == [Dismissal(rule="bjt-cut-off", refs=["Q1"], reason="a µ-power fuzz")]
    assert circuit_to_dict(c)["dismissed"] == [
        {"rule": "bjt-cut-off", "refs": ["Q1"], "reason": "a µ-power fuzz"}
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"refs": ["Q1"]},  # no rule
        {"rule": "Bjt Cut Off"},  # not a rule id
        {"rule": "bjt-cut-off", "reason": "x" * (REASON_MAX + 1)},
        {"rule": "bjt-cut-off", "why": "extra field"},
    ],
)
def test_a_malformed_dismissal_is_refused(fuzz: Circuit, bad: dict[str, object]) -> None:
    with pytest.raises(CircuitError):
        parse_circuit(circuit_to_dict(fuzz) | {"dismissed": [bad]})


def test_dismissals_on_parts_and_nets_still_there_are_kept(fuzz: Circuit) -> None:
    c = dismissed(
        fuzz,
        Dismissal(rule="bjt-cut-off", refs=["Q1"]),
        Dismissal(rule="no-dc-path", nets=["b"]),
        Dismissal(rule="opamp-unpowered", refs=["R1"], nets=["V+"], reason="on purpose"),
    )
    assert kept_dismissals(c) is c


def test_a_dismissal_naming_a_part_or_net_that_is_gone_is_dropped(fuzz: Circuit) -> None:
    keep = Dismissal(rule="bjt-cut-off", refs=["Q1"])
    c = dismissed(
        fuzz,
        keep,
        Dismissal(rule="bjt-cut-off", refs=["Q9"]),  # no Q9
        Dismissal(rule="no-dc-path", nets=["x"]),  # no net x
        Dismissal(rule="unconnected-pin", refs=["Q1"], nets=["gone"]),
    )
    assert kept_dismissals(c).dismissed == [keep]


def test_with_contradicting_wiring_only_the_parts_are_checked(fuzz: Circuit) -> None:
    """Two labels wired together: no nets to look at, so a net-only dismissal stays."""
    data = circuit_to_dict(fuzz)
    labels = [lb for lb in data["labels"] if lb["net"] in ("in", "b")]
    data["wires"] = [*data.get("wires", []), {"from": labels[0]["pos"], "to": labels[1]["pos"]}]
    c = dismissed(
        parse_circuit(data),
        Dismissal(rule="no-dc-path", nets=["x"]),
        Dismissal(rule="bjt-cut-off", refs=["Q9"]),
    )
    assert kept_dismissals(c).dismissed == [Dismissal(rule="no-dc-path", nets=["x"])]


def test_a_save_drops_stale_dismissals(tmp_path: Path, fuzz: Circuit) -> None:
    store = CircuitStore(tmp_path / "data", tmp_path / "cache")
    live = Dismissal(rule="bjt-cut-off", refs=["Q1"], reason="biased later")
    stale = Dismissal(rule="bjt-cut-off", refs=["Q9"])
    created = store.create(dismissed(fuzz, live, stale), "My Fuzz")
    assert store.load(created.id).dismissed == [live]
    saved = store.save(dismissed(created, live, stale))
    assert str(saved.version) == "v1.0"  # only the stale one differed: nothing to save
    assert store.load(created.id).dismissed == [live]
