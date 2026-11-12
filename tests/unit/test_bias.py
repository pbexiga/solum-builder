"""Bias solver against a stand-in for .op: a drain resistor set by the trimmer."""

from collections.abc import Callable

import pytest

from solum.bias import BiasError, bisect, solve_bias, target_reach
from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.schema import Circuit, Trimmer


def jfet_stage(circuit: Callable[..., CircuitBuilder], volts: float) -> Circuit:
    return (
        circuit()
        .rail("V+", 18.0)
        .part("TR1", "trimmer", "V+", "d", None, value="100k",
              bias_target={"node": "Q1.D", "volts": volts})
        .part("Q1", "jfet", "d", "0", "s", model="J201")
        .build()
    )  # fmt: skip


def fake_op(circuit: Circuit) -> dict[str, float]:
    """Constant 0.2 mA through TR1's pin-1-to-wiper half (rotation * 100k)."""
    trimmer = circuit.part("TR1")
    assert isinstance(trimmer, Trimmer)
    nets = connect(circuit)
    return {nets.net_of("Q1", "D"): 18.0 - 0.2e-3 * trimmer.rotation * 100e3}


def test_solves_to_the_target(circuit: Callable[..., CircuitBuilder]) -> None:
    result = solve_bias(jfet_stage(circuit, 9.0), fake_op)
    assert result.volts["TR1"] == pytest.approx(9.0, abs=1e-3)
    assert result.rotations["TR1"] == pytest.approx(0.45, abs=1e-4)  # 9 V / 0.2 mA = 45k
    solved = result.circuit.part("TR1")
    assert isinstance(solved, Trimmer) and solved.rotation == result.rotations["TR1"]


def test_unreachable_target_says_why(circuit: Callable[..., CircuitBuilder]) -> None:
    """End to end, the trimmer moves the drain from 18 V down to -2 V: 20 V is out of reach."""
    with pytest.raises(
        BiasError, match=r"TR1 can't set d to 20 V: .* between -2\.00 V and 18\.00 V"
    ):
        solve_bias(jfet_stage(circuit, 20.0), fake_op)


def test_no_targets_is_a_no_op(circuit: Callable[..., CircuitBuilder]) -> None:
    c = circuit().part("R1", "resistor", "a", "0", value=1).build()
    assert solve_bias(c, lambda _: {}).circuit == c


def test_bisect_finds_where_a_falling_function_reaches_the_target() -> None:
    found = bisect(lambda x: 10 - x * x, 0.0, 3.0, 6.0, 1e-6)
    assert found is not None
    x, y = found
    assert x == pytest.approx(2.0, abs=1e-5) and y == pytest.approx(6.0, abs=1e-6)


def test_bisect_says_none_outside_what_the_ends_reach() -> None:
    assert bisect(lambda x: x, 0.0, 1.0, 2.0, 1e-3) is None


def test_a_targets_reach_is_the_trimmer_turned_end_to_end(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """D-127: what the trimmer's form checks a new target against."""
    reach = target_reach(jfet_stage(circuit, 9.0), "TR1", fake_op)
    assert (reach.low, reach.high) == pytest.approx((-2.0, 18.0))
    assert reach.text == "With TR1 (100k), Q1.D can go from -2.00 V to 18.00 V."
    assert reach.holds(9.0) and reach.holds(18.0005)
    assert not reach.holds(20.0)
    assert reach.target == 9.0 and reach.reached
    assert not target_reach(jfet_stage(circuit, 20.0), "TR1", fake_op).reached
    with pytest.raises(BiasError, match="Q1 isn't a trimmer with a bias target"):
        target_reach(jfet_stage(circuit, 9.0), "Q1", fake_op)
    with pytest.raises(BiasError, match="RT9 isn't"):
        target_reach(jfet_stage(circuit, 9.0), "RT9", fake_op)
