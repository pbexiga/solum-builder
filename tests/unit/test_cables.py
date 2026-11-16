import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.cables import battery_cut_off, cables_out, jack_roles, silence
from solum.circuit.connectivity import connect
from solum.circuit.schema import Circuit


def _pedal(j1: dict[str, object] | None = None, j2: dict[str, object] | None = None) -> Circuit:
    """A battery-powered buffer: J1 (stereo, its ring the battery's −) into IN's net, J2
    on the amp's net."""
    b = (
        CircuitBuilder("jacks")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": "V+", "-": "ring"})
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="10k")
        .part("R2", "resistor", "V+", "GND", value="10k")
        .part("OUT", "amp", "out")
    )
    if j1 is not None:
        b.part("J1", "jack", pins={"T": "in", "R": "ring", "S": "GND"}, stereo=True, **j1)
    if j2 is not None:
        b.part("J2", "jack", pins={"T": "out", "S": "GND"}, **j2)
    return b.build()


def test_what_each_jacks_cable_switches() -> None:
    c = _pedal({}, {})
    assert jack_roles(c, connect(c)) == {
        "J1": frozenset({"input", "battery"}),
        "J2": frozenset({"output"}),
    }


def test_a_jack_on_nothing_that_matters_switches_nothing() -> None:
    c = (
        CircuitBuilder("drawing")
        .part("R1", "resistor", "a", "GND", value="1k")
        .part("J1", "jack", pins={"T": "a", "S": "GND"}, plugged=False)
        .build()
    )
    assert jack_roles(c, connect(c)) == {}
    assert cables_out(c) == [] and silence(c) is None


def test_with_every_cable_in_nothing_is_silent() -> None:
    c = _pedal({}, {})
    assert cables_out(c) == [] and not battery_cut_off(c) and silence(c) is None


@pytest.mark.parametrize(
    ("j1", "j2", "cut", "said"),
    [
        ({"plugged": False}, {}, True,
         "J1 has no cable in: no guitar reaches the pedal and its battery is cut off."),
        ({}, {"plugged": False}, False, "J2 has no cable in: nothing reaches the amp."),
        ({"plugged": False}, {"plugged": False}, True,
         "J1 has no cable in: no guitar reaches the pedal and its battery is cut off. "
         "J2 has no cable in: nothing reaches the amp."),
    ],
)  # fmt: skip
def test_a_cable_out_says_what_it_cuts(
    j1: dict[str, object], j2: dict[str, object], cut: bool, said: str
) -> None:
    c = _pedal(j1, j2)
    assert battery_cut_off(c) is cut
    assert silence(c) == said


def test_a_ring_only_jack_cuts_the_battery_off_without_silencing() -> None:
    c = (
        CircuitBuilder("ring only")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": "V+", "-": "ring"})
        .part("R1", "resistor", "V+", "GND", value="10k")
        .part("J1", "jack", pins={"T": "x", "R": "ring", "S": "GND"}, stereo=True, plugged=False)
        .build()
    )
    assert battery_cut_off(c)
    assert silence(c) is None  # unpowered, but a signal could still get through


def test_a_battery_straight_to_ground_isnt_switched() -> None:
    c = (
        CircuitBuilder("grounded")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": "V+", "-": "GND"})
        .part("R1", "resistor", "V+", "GND", value="10k")
        .part("J1", "jack", pins={"T": "x", "R": "GND", "S": "GND"}, stereo=True, plugged=False)
        .build()
    )
    assert not battery_cut_off(c) and silence(c) is None
