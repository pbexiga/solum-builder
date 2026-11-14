"""Slider steps for live curves (`solum/live.py`): ranges, series, kept steps, the element
values each step sets. No ngspice: `live_view` itself is in tests/sim/test_live.py."""

from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.schema import Circuit
from solum.live import (
    CAP_RANGE,
    POT_RANGE,
    RESISTOR_RANGE,
    ROTATION_STEPS,
    LiveError,
    slider,
    value_steps,
)
from solum.models import ModelLibrary, load_models

Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([Path(__file__).parents[2] / "library" / "models"])


@pytest.fixture
def stage(circuit: Builder) -> Circuit:
    return (
        circuit("stage")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "a", value="10k")
        .part("C1", "capacitor", "a", "0", value="47n")
        .part("VR1", "pot", "a", "w", "0", value="100k", taper="A")
        .part("TR1", "trimmer", "w", "b", "0", value="50k",
              bias_target={"node": "w", "volts": 1.0})
        .part("D1", "diode", "b", "0", model="1N4148")
        .part("OUT", "amp", "w", value="470k")
        .build()
    )  # fmt: skip


def test_value_steps_run_a_decade_each_way_through_e12() -> None:
    steps = value_steps(10e3)
    assert steps[0] == pytest.approx(1e3) and steps[-1] == pytest.approx(100e3)
    assert len(steps) == 25  # two decades of E12, both ends included
    assert 4.7e3 in [pytest.approx(s) for s in steps]


def test_an_off_series_value_joins_its_steps() -> None:
    steps = value_steps(50e3)
    assert 50e3 in steps and steps == sorted(steps)


def test_a_capacitor_slider_has_a_fixed_pedal_range() -> None:
    """The user (2026-11-02): 22n gave 2n2-220n, and after Apply at 68n, 6n8-680n. A
    capacitor's steps now run 10p to 470µ whatever its value (D-164)."""
    for value in (22e-9, 68e-9, 1e-6):
        steps = value_steps(value, span=CAP_RANGE)
        assert steps[0] == pytest.approx(10e-12) and steps[-1] == pytest.approx(470e-6)
        assert value in [pytest.approx(s) for s in steps]
    assert value_steps(22e-9, span=CAP_RANGE) == value_steps(68e-9, span=CAP_RANGE)


def test_kept_steps_hold_the_range() -> None:
    assert value_steps(820e3, ["10k", "100k", "1M"]) == [1e4, 1e5, 8.2e5, 1e6]


def test_resistor_slider(stage: Circuit, models: ModelLibrary) -> None:
    s = slider(stage, models, "R1", "value")
    at = s["steps"][s["index"]]
    assert at["value"] == "10k" and at["text"] == "10k"
    assert at["elements"] == {"R1": 10000.0}
    assert s["series"] == "E12" and s["nearest"] is None


def test_a_resistor_slider_has_a_fixed_pedal_range(circuit: Builder, models: ModelLibrary) -> None:
    """The user (2026-11-13): as a capacitor's, a resistor's slider runs over one range
    whatever its value, 10 Ω to 10 MΩ in E12, in place of a tenth to ten times (D-316)."""
    assert RESISTOR_RANGE == (10.0, 10e6)
    ends = []
    for value in ("100", "10k", "2M2"):
        c = circuit().part("R1", "resistor", "a", "0", value=value).build()
        s = slider(c, models, "R1", "value")
        ends.append((s["steps"][0]["text"], s["steps"][-1]["text"], len(s["steps"])))
        assert s["steps"][s["index"]]["value"] == value
    assert ends == [("10", "10M", 73)] * 3  # six decades of E12, both ends included


def test_inductors_and_the_amp_keep_a_decade_each_way(stage: Circuit, models: ModelLibrary) -> None:
    amp = slider(stage, models, "OUT", "value")
    assert (amp["steps"][0]["text"], amp["steps"][-1]["text"]) == ("47k", "4M7")


def test_capacitor_and_amp_sliders(stage: Circuit, models: ModelLibrary) -> None:
    cap = slider(stage, models, "C1", "value")
    assert cap["steps"][cap["index"]]["elements"] == {"C1": pytest.approx(47e-9)}
    amp = slider(stage, models, "OUT", "value")
    assert amp["steps"][amp["index"]]["elements"] == {"R_OUT": pytest.approx(470e3)}


def test_a_typed_value_shows_its_nearest_series_member(
    circuit: Builder, models: ModelLibrary
) -> None:
    c = circuit().part("R1", "resistor", "a", "0", value="50k").build()
    s = slider(c, models, "R1", "value")
    assert s["nearest"] == "47k" and s["steps"][s["index"]]["value"] == "50k"


def test_pots_step_through_the_values_they_are_sold_in(
    stage: Circuit, models: ModelLibrary
) -> None:
    s = slider(stage, models, "VR1", "value")
    assert s["series"] == "pot"
    texts = [step["text"] for step in s["steps"]]
    # every value sold, 1k to 1M, whatever the pot's own (D-316)
    assert texts == ["1k", "2k", "2k5", "5k", "10k", "20k", "25k", "50k", "100k", "200k",
                     "250k", "500k", "1M"]  # fmt: skip
    assert POT_RANGE == (1e3, 1e6)


def test_rotation_slider_applies_the_taper(stage: Circuit, models: ModelLibrary) -> None:
    s = slider(stage, models, "VR1", "rotation")
    assert len(s["steps"]) == ROTATION_STEPS and s["index"] == 50
    half = s["steps"][50]
    assert half["text"] == "50 %"
    # A taper at half rotation: 10 % of the track on the CCW side
    assert half["elements"] == {"R_VR1_a": pytest.approx(1e4), "R_VR1_b": pytest.approx(9e4)}


def test_what_has_no_slider(stage: Circuit, models: ModelLibrary) -> None:
    with pytest.raises(LiveError, match="no value"):
        slider(stage, models, "D1", "value")
    with pytest.raises(LiveError, match="isn't a pot"):
        slider(stage, models, "R1", "rotation")
    with pytest.raises(LiveError, match="bias target"):
        slider(stage, models, "TR1", "rotation")
    with pytest.raises(LiveError, match="no slider"):
        slider(stage, models, "R1", "model")  # type: ignore[arg-type]


def test_the_guitar_volume_is_a_knob(circuit: Builder, models: ModelLibrary) -> None:
    """D-096: a pickup through a 250k audio-taper volume pot, turned to half: 25k to
    ground and 225k in series (an A taper's track is 10 % at half way)."""
    pickup = {"r": "6k38", "l": "2.55", "c": "151p", "kind": "strat"}
    c = (
        circuit()
        .part("IN", "guitar", "in", source="pickup", pickup=pickup, volume="250k", cable=3)
        .part("R1", "resistor", "in", "0", value="1M")
        .build()
    )
    s = slider(c, models, "IN", "rotation")
    assert s["index"] == 100  # on 10
    assert s["steps"][50]["elements"] == {
        "R_IN_coil": pytest.approx(6380), "L_IN": pytest.approx(2.55),
        "C_IN_coil": pytest.approx(151e-12), "C_IN_cable": pytest.approx(300e-12),
        "R_IN_vola": pytest.approx(25e3), "R_IN_volb": pytest.approx(225e3),
    }  # fmt: skip
    buffered = slider(c.with_part("IN", source="ideal", pickup=None), models, "IN", "rotation")
    assert buffered["steps"][50]["elements"] == {"V_IN": pytest.approx(0.1)}  # D-134
    no_pot = c.with_part("IN", source="ideal", pickup=None, volume=None)
    with pytest.raises(LiveError, match="isn't a pot"):
        slider(no_pot, models, "IN", "rotation")
