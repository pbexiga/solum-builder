import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.cables import (
    battery_cut_off,
    cables_out,
    jack_roles,
    jacks_into,
    ring_problem,
    silence,
)
from solum.circuit.connectivity import connect
from solum.circuit.io import CircuitError
from solum.circuit.schema import Circuit
from solum.circuit.supply import drawable, no_power, render_refusal


def _pedal(j1: dict[str, object] | None = None, j2: dict[str, object] | None = None) -> Circuit:
    """A battery-powered buffer: J1 (TRS, its ring the battery's −) into IN's net, J2
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
        b.part("J1", "jack", pins={"T": "in", "R": "ring", "S": "GND"}, trs=True, **j1)
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
        .part("J1", "jack", pins={"T": "x", "R": "ring", "S": "GND"}, trs=True, plug="none")
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
        .part("J1", "jack", pins={"T": "x", "R": "GND", "S": "GND"}, trs=True, plug="none")
        .build()
    )
    assert not battery_cut_off(c) and silence(c) is None


def test_a_stereo_cable_in_the_input_cuts_the_battery_but_not_the_guitar() -> None:
    """D-355: its ring is its own, so the battery on the jack's ring stays off; the guitar
    still comes in, but with no power there's nothing to draw or render (D-358)."""
    c = _pedal({"plug": "trs"}, {})
    assert battery_cut_off(c) and silence(c) is None and cables_out(c) == []
    said = "The pedal has no power: J1 has a TRS cable in, so its battery is cut off."
    assert no_power(c) == said and not drawable(c)
    assert render_refusal(c) == f"{said} Put a TS cable in J1 (Knobs) to render."


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
    """D-355: a TRS jack with its ring and sleeve both wired switches them, whatever
    the ring does; with its ring unwired it switches nothing."""
    c = (
        CircuitBuilder("ring")
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "y", value="10k")
        .part("J1", "jack", trs=True, pins={"T": "x", "R": "y", "S": "GND"})
        .part("J2", "jack", trs=True, pins={"T": "z", "R": "w", "S": "GND"})
        .build()
    )
    assert jack_roles(c, connect(c)) == {"J1": frozenset({"ring"})}


def _guitar_pedal(trs: bool, ring: str | None = "ring", **guitar: object) -> CircuitBuilder:
    """A battery-powered buffer with no J drawn: IN's own jack, TRS with its ring on
    `ring` (the battery's −) or TS."""
    pins = {"out": "in", "ring": ring} if trs and ring else {"out": "in"}
    return (
        CircuitBuilder("IN's jack")
        .rail("V+", 9)
        .part("BAT1", "battery", pins={"+": "V+", "-": "ring"})
        .part("IN", "guitar", pins=pins, trs=trs, **guitar)
        .part("R1", "resistor", "in", "out", value="10k")
        .part("R2", "resistor", "V+", "GND", value="10k")
        .part("OUT", "amp", "out")
    )


def test_the_guitar_input_is_an_input_jack() -> None:
    """D-364: with no J drawn into it, IN's own cable switches the guitar; a TRS IN
    with the battery's − on its ring switches the battery as J1 does."""
    ts = _guitar_pedal(False).build()
    assert jack_roles(ts, connect(ts)) == {"IN": frozenset({"input"})}
    trs = _guitar_pedal(True).build()
    assert jack_roles(trs, connect(trs)) == {"IN": frozenset({"input", "ring", "battery"})}
    unwired = _guitar_pedal(True, ring=None).build()
    assert jack_roles(unwired, connect(unwired)) == {"IN": frozenset({"input"})}


def test_the_guitar_inputs_cable_out_refuses_a_render_and_keeps_the_curves() -> None:
    """D-354, D-358 for IN's own cable: a TS IN cuts no battery, so the pedal stays
    powered and is drawn."""
    c = _guitar_pedal(False, plug="none").build()
    said = "IN has no cable in: no guitar reaches the pedal."
    assert silence(c) == said and not battery_cut_off(c)
    assert drawable(c) and render_refusal(c) == f"{said} Put its cable in (Knobs) to render."


@pytest.mark.parametrize(
    ("plug", "cut", "silent"),
    [("ts", False, None),
     ("trs", True, None),
     ("none", True, "IN has no cable in: no guitar reaches the pedal and its battery is cut off.")],
)  # fmt: skip
def test_a_stereo_guitar_inputs_ring_cuts_the_battery_as_a_jacks(
    plug: str, cut: bool, silent: str | None
) -> None:
    c = _guitar_pedal(True, plug=plug).build()
    assert battery_cut_off(c) is cut and silence(c) == silent
    if plug == "trs":
        assert no_power(c) == (
            "The pedal has no power: IN has a TRS cable in, so its battery is cut off."
        )


def test_a_jack_drawn_into_the_guitar_input_takes_its_plug_over() -> None:
    """D-364: J1 on IN's net is the input jack; IN's own plug (here out) steps aside."""
    b = _guitar_pedal(False, plug="none")
    b.part("J1", "jack", pins={"T": "in", "S": "GND"})
    c = b.build()
    assert jack_roles(c, connect(c)) == {"J1": frozenset({"input"})}
    assert [j.ref for j in jacks_into(c, connect(c), c.part("IN"))] == ["J1"]  # type: ignore[arg-type]
    assert silence(c) is None and render_refusal(c) is None
    unplugged = c.with_part("J1", plug="none")
    assert silence(unplugged) == "J1 has no cable in: no guitar reaches the pedal."


def test_a_jack_into_a_stereo_guitar_input_with_its_ring_wired_is_refused() -> None:
    """D-364: one jack, two rings. With IN's ring unwired J1 just takes over."""
    b = _guitar_pedal(True)
    b.part("J1", "jack", pins={"T": "in", "S": "GND"})
    with pytest.raises(CircuitError, match=r"IN's ring is wired: move those wires to J1's R "
                       r"first, or unplug J1\."):  # fmt: skip
        b.build()
    ok = _guitar_pedal(True, ring=None)
    ok.part("J1", "jack", pins={"T": "in", "S": "GND"})
    c = ok.build()
    assert ring_problem(c) is None and jack_roles(c, connect(c)) == {"J1": frozenset({"input"})}
