"""The linear system for the browser solver (`solum.linear`): pure parts, no ngspice.
Parity with ngspice itself is tests/parity."""

import numpy as np
import pytest

from solum.linear import (
    Branch,
    LinearError,
    Ports,
    ac_magnitude,
    branches,
    element_values,
    held_nodes,
    port_admittance,
    port_nodes,
    system_data,
)
from solum.netlist import Element, Sensed


def el(ref: str | None, *tokens: str) -> Element:
    return Element(ref, tokens)


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [(("DC 0 AC 1",), 1.0), (("DC", "0", "AC", "0.5"), 0.5), (("DC", "9"), 0.0), ((), 0.0)],
)
def test_ac_magnitude(tokens: tuple[str, ...], expected: float) -> None:
    assert ac_magnitude(tokens) == expected


def test_held_nodes_follow_quiet_sources_to_ground() -> None:
    elements = [
        el(None, "V_RAIL1", "v_", "0", "DC", "9"),
        el("VB", "VB", "bat", "v_", "DC", "1.5"),  # stacked on the rail: held too
        el("IN", "V_IN", "in", "0", "DC 0 AC 1"),  # drives the signal: not held
        el("R1", "R1", "in", "a", "1000"),
        el("V2", "V2", "x", "y", "DC", "1"),  # floating source: not held
    ]
    assert held_nodes(elements) == {"0", "v_", "bat"}


def test_port_nodes_merge_shared_nodes_and_skip_held_ones() -> None:
    sensed = [
        Sensed("+", "in", "in", "V_SU1_p"),
        Sensed("-", "o", "o", "V_SU1_m"),
        Sensed("out", "o", "o", "V_SU1_out"),  # a follower: out and - share a node
        Sensed("V+", "V+", "v_", "V_SU1_Vp"),
        Sensed("V-", "GND", "0", "V_SU1_Vm"),
    ]
    assert port_nodes(sensed, frozenset({"0", "v_"})) == ("in", "o")


def test_port_admittance_recovers_a_known_matrix() -> None:
    rng = np.random.default_rng(1)
    y = rng.normal(size=(4, 3, 3)) + 1j * rng.normal(size=(4, 3, 3))  # 4 frequencies
    volts = rng.normal(size=(4, 3, 5)) + 1j * rng.normal(size=(4, 3, 5))  # 5 runs
    found = port_admittance(volts, y @ volts)
    assert np.allclose(found, y, rtol=1e-10, atol=1e-12)


def test_port_admittance_needs_enough_runs() -> None:
    with pytest.raises(LinearError, match="Not enough"):
        port_admittance(np.ones((1, 3, 2), complex), np.ones((1, 3, 2), complex))


def test_branches_replace_devices_with_their_ports() -> None:
    y = np.ones((2, 1, 1), complex)
    elements = [
        el("IN", "V_IN", "in", "0", "DC 0 AC 1"),
        el("C1", "C1", "in", "a", "1e-07"),
        el("D1", "V_SD1_A", "a", "s_d1_a", "DC", "0"),
        el("D1", "V_SD1_K", "0", "s_d1_k", "DC", "0"),
        el("D1", "D1", "s_d1_a", "s_d1_k", "1N4148"),
        el("OUT", "R_AMP", "a", "0", "1000000"),
    ]
    found = branches(elements, {"D1": Ports(("a",), y)})
    assert [(b.kind, b.name, b.nodes, b.value) for b in found] == [
        ("V", "V_IN", ("in", "0"), 1.0),
        ("C", "C1", ("in", "a"), 1e-7),
        ("R", "R_AMP", ("a", "0"), 1e6),
        ("Y", "D1", ("a",), 0.0),
    ]
    assert found[-1].y is y


def test_a_device_with_every_port_held_drops_out() -> None:
    elements = [el("D1", "D1", "v_", "0", "1N4148")]
    assert branches(elements, {"D1": Ports((), np.zeros((2, 0, 0), complex))}) == []


def test_an_unmeasured_device_is_refused() -> None:
    with pytest.raises(LinearError, match="Q1 isn't measured"):
        branches([el("Q1", "Q1", "c", "b", "e", "2N5089")], {})


def test_element_values_are_the_passive_ones() -> None:
    elements = [
        el("VR1", "R_VR1_a", "a", "b", "5000"),
        el("VR1", "R_VR1_b", "b", "c", "95000"),
        el("C1", "C1", "a", "0", "1e-08"),
        el("IN", "V_IN", "a", "0", "DC 0 AC 1"),
    ]
    assert element_values(elements) == {"R_VR1_a": 5000.0, "R_VR1_b": 95000.0, "C1": 1e-8}


def test_system_data_indexes_nodes_and_flattens_admittances() -> None:
    y = np.array([[[1 + 2j, 3 + 4j], [5 + 6j, 7 + 8j]]])  # one frequency, two ports
    found = [Branch("R", "R1", ("b", "0"), 1000.0), Branch("Y", "Q1", ("a", "b"), y=y)]
    data = system_data(found, [1000.0], "b")
    assert data["nodes"] == ["a", "b"] and data["out"] == 1 and data["freq"] == [1000.0]
    assert data["elements"][0] == {"k": "R", "name": "R1", "n": [1, -1], "v": 1000.0}
    q1 = data["elements"][1]
    assert q1["n"] == [0, 1]
    assert q1["re"] == [[1.0, 3.0, 5.0, 7.0]] and q1["im"] == [[2.0, 4.0, 6.0, 8.0]]
    with pytest.raises(LinearError, match="output node 'zz'"):
        system_data(found, [1000.0], "zz")
