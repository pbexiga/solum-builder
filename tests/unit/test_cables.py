import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.cables import battery_cut_off, cables_out, jack_roles, silence
from solum.circuit.connectivity import connect
from solum.circuit.schema import Circuit
from solum.circuit.supply import drawable, no_power, render_refusal


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
        "J1": frozenset({"input", "ring", "battery"}),
        "J2": frozenset({"output"}),
    }


def test_a_jack_on_nothing_that_matters_switches_nothing() -> None:
    c = (
        CircuitBuilder("drawing")
        .part("R1", "resistor", "a", "GND", value="1k")
        .part("J1", "jack", pins={"T": "a", "S": "GND"}, plug="none")
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
        ({"plug": "none"}, {}, True,
         "J1 has no cable in: no guitar reaches the pedal and its battery is cut off."),
        ({}, {"plug": "none"}, False, "J2 has no cable in: nothing reaches the amp."),
        ({"plug": "none"}, {"plug": "none"}, True,
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
        .part("J1", "jack", pins={"T": "x", "R": "ring", "S": "GND"}, stereo=True, plug="none")
        .build()
    )
    assert battery_cut_off(c)
    assert silence(c) is None  # no cable of the input or output is out


def test_a_battery_straight_to_ground_isnt_switched() -> None:
    c = (
        CircuitBuilder("grounded")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": "V+", "-": "GND"})
        .part("R1", "resistor", "V+", "GND", value="10k")
        .part("J1", "jack", pins={"T": "x", "R": "GND", "S": "GND"}, stereo=True, plug="none")
        .build()
    )
    assert not battery_cut_off(c) and silence(c) is None


def test_a_stereo_cable_in_the_input_cuts_the_battery_but_not_the_guitar() -> None:
    """D-355: its ring is its own, so the battery on the jack's ring stays off; the guitar
    still comes in, but with no power there's nothing to draw or render (D-358)."""
    c = _pedal({"plug": "stereo"}, {})
    assert battery_cut_off(c) and silence(c) is None and cables_out(c) == []
    said = "The pedal has no power: J1 has a stereo cable in, so its battery is cut off."
    assert no_power(c) == said and not drawable(c)
    assert render_refusal(c) == f"{said} Put a mono cable in J1 (Knobs) to render."


@pytest.mark.parametrize(
    ("j1", "j2", "draws", "refused"),
    [
        ({}, {}, True, None),
        ({"plug": "none"}, {}, False,
         "J1 has no cable in: no guitar reaches the pedal and its battery is cut off. "
         "Put its cable in (Knobs) to render."),
        ({}, {"plug": "none"}, True,  # powered: the curves stay, the render can't be made
         "J2 has no cable in: nothing reaches the amp. Put its cable in (Knobs) to render."),
    ],
)  # fmt: skip
def test_only_no_power_stops_the_curves_a_cable_out_stops_the_render(
    j1: dict[str, object], j2: dict[str, object], draws: bool, refused: str | None
) -> None:
    """D-358: the curves and the scope need power, a render needs the guitar and the amp
    plugged in as well."""
    c = _pedal(j1, j2)
    assert drawable(c) is draws and render_refusal(c) == refused


def test_a_cable_out_of_a_pedal_on_another_supply_keeps_its_curves() -> None:
    """D-358: the battery on ground (always on): the input cable out leaves it powered."""
    c = (
        CircuitBuilder("grounded")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": "V+", "-": "GND"})
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "out", value="10k")
        .part("OUT", "amp", "out")
        .part("J1", "jack", pins={"T": "in", "S": "GND"}, plug="none")
        .build()
    )
    assert drawable(c) and no_power(c) is None
    assert render_refusal(c) == (
        "J1 has no cable in: no guitar reaches the pedal. Put its cable in (Knobs) to render."
    )


def test_a_ring_used_for_anything_is_a_switch() -> None:
    """D-355: a stereo jack with its ring and sleeve both wired switches them, whatever
    the ring does; with its ring unwired it switches nothing."""
    c = (
        CircuitBuilder("ring")
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "y", value="10k")
        .part("J1", "jack", stereo=True, pins={"T": "x", "R": "y", "S": "GND"})
        .part("J2", "jack", stereo=True, pins={"T": "z", "R": "w", "S": "GND"})
        .build()
    )
    assert jack_roles(c, connect(c)) == {"J1": frozenset({"ring"})}
