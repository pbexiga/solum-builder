"""Failed runs and refused runs in plain English, through real ngspice (D-054, D-077)."""

import pytest

from solum.circuit.build import CircuitBuilder
from solum.rules.run import CantSimulate, Checker
from solum.sim.engine import SimError
from solum.simulate import Simulator


def half_drawn() -> CircuitBuilder:
    return (
        CircuitBuilder("half drawn")
        .part("C16", "capacitor", None, None, value="47u", kind="electrolytic")
        .part("R3", "resistor", None, None, value="10k")
    )


def test_a_singular_matrix_names_the_nets(checker: Checker, sim: Simulator) -> None:
    with pytest.raises(SimError) as err:
        sim.op(half_drawn().build())
    problems = checker.explain(err.value)
    assert [p.rule for p in problems] == ["sim-no-dc-path"]  # not the failures it causes
    assert (
        problems[0].message == "Can't simulate yet: nets C16.2 and R3.1 have no DC path to ground."
    )
    assert "C16.2" in problems[0].nets
    assert checker.message(err.value) == problems[0].message


def test_the_drawing_is_checked_before_simulating(checker: Checker) -> None:
    with pytest.raises(CantSimulate) as err:
        checker.require_runnable(half_drawn().build())
    assert str(err.value).startswith("Can't simulate yet: nets C16.1, C16.2, R3.1 and 1 more")
    assert err.value.problems[0].rule == "no-dc-path"


def test_a_good_circuit_runs(checker: Checker, sim: Simulator) -> None:
    c = CircuitBuilder().rail("V+", 9).part("R1", "resistor", "V+", "GND", value="10k").build()
    checker.require_runnable(c)
    problems, checked = checker.check(c, sim)
    assert checked
    assert {p.rule for p in problems} == {
        "no-guitar-input",
        "no-amp-output",
        "enclosure-not-chosen",
    }  # notes only


def test_problems_come_errors_first(checker: Checker, sim: Simulator) -> None:
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "GND", value="100")  # too hot: error
        .part("R2", "resistor", "a", None, value="10k")  # wired by one pin: warning
        .part("R3", "resistor", "a", "GND", value="10k")
        .build()
    )
    problems, _ = checker.check(c, sim)
    severities = [p.severity for p in problems]
    assert severities == sorted(severities, key=["error", "warning", "info"].index)
    assert {"resistor-over-power", "part-not-simulated", "no-guitar-input"} <= {
        p.rule for p in problems
    }


def test_without_a_simulator_only_the_drawing_is_checked(checker: Checker) -> None:
    c = CircuitBuilder().rail("V+", 9).part("R1", "resistor", "V+", "GND", value="100").build()
    problems, checked = checker.check(c, None)
    assert not checked and "resistor-over-power" not in {p.rule for p in problems}


def battery_buffer(cable: bool, plus: str = "V+") -> CircuitBuilder:
    """A TL072 buffer biased at half supply, on a battery its stereo input jack switches;
    the battery's + on `plus` (V+, or a net of its own with nothing on V+)."""
    return (
        CircuitBuilder("battery buffer")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": plus, "-": "ring"})
        .part("J1", "jack", stereo=True, label="Input", plug="mono" if cable else "none",
              pins={"T": "in", "R": "ring", "S": "GND"})
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "p", value="100n")
        .part("R1", "resistor", plus, "vb", value="100k")
        .part("R2", "resistor", "vb", "GND", value="100k")
        .part("C2", "capacitor", "vb", "GND", value="10u", kind="electrolytic")
        .part("R3", "resistor", "vb", "p", value="1M")
        .part("IC1", "opamp", "p", "o", "o", model="TL072", supply=(plus, "GND"))
        .part("C3", "capacitor", "o", "out", value="1u", kind="film")
        .part("R4", "resistor", "out", "GND", value="100k")
        .part("OUT", "amp", "out")
    )  # fmt: skip


@pytest.mark.parametrize("plus", ["V+", "VBAT"])
def test_with_the_battery_cut_off_only_the_cable_is_a_problem(
    checker: Checker, sim: Simulator, plus: str
) -> None:
    """D-354: the pedal is off, so its stages' 0 V aren't bias problems (no op-amp warnings
    about a supply the battery warning already explains), whether the battery's + is V+
    or a net of its own (nothing on V+: the battery was the only supply, D-357)."""
    on, _ = checker.check(battery_buffer(cable=True, plus=plus).build(), sim)
    off, checked = checker.check(battery_buffer(cable=False, plus=plus).build(), sim)
    assert checked
    assert {p.rule for p in off} - {p.rule for p in on} == {"battery-cable-out"}
    assert not [p for p in off if checker.book.get(p.rule).layer == "operating_point"]
