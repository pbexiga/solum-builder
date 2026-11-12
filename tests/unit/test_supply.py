"""Which supply powers the circuit (D-143, D-185): the Power menu's through the DC jack, a
battery wired through the DC jack's battery lug and a stereo jack's ring, or both."""

from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.schema import Circuit
from solum.circuit.supply import (
    battery_of,
    battery_wiring,
    live_rails,
    on_battery,
    power_chip,
    supply_volts,
)
from solum.models import ModelLibrary, load_models
from solum.netlist import NetlistError, Op, generate_netlist, rail_sources
from solum.rules import graph
from solum.view import circuit_view, controls

Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([Path(__file__).parents[2] / "library" / "models"])


def pedal(circuit: Builder, plugged: bool = True) -> CircuitBuilder:
    """A pedal wired as a real one: the battery's + on the DC jack's battery lug, its -
    on the guitar jack's ring; the jack's sleeve is V+."""
    return (
        circuit()
        .rail("V+", 9.0)
        .part("IN", "guitar", "in", stereo=True, pins={"ring": "bneg"})
        .part("DC", "dcjack", "V+", "0", "bpos", plugged=plugged)
        .part("BAT1", "battery", "bpos", "bneg", volts=7.4, state="half")
        .part("R1", "resistor", "V+", "0", value="10k")
    )


def test_a_plug_in_the_dc_jack_keeps_the_power_menus_supply(circuit: Builder) -> None:
    c = pedal(circuit).build()
    assert battery_of(c, connect(c)) is None
    assert on_battery(c) is None
    assert live_rails(c) == {"V+": 9.0} == supply_volts(c)


def test_unplugged_the_battery_powers_it(circuit: Builder) -> None:
    c = pedal(circuit, plugged=False).build()
    assert battery_of(c, connect(c)) is c.part("BAT1") is on_battery(c)
    assert live_rails(c) == {}
    assert supply_volts(c) == {"V+": pytest.approx(7.4)}
    assert rail_sources(c) == {"V+": "V_BAT1"}  # the current draw is the battery's


def test_a_battery_without_a_dc_jack_always_powers_it(circuit: Builder) -> None:
    c = circuit().rail("V+", 9.0).rail("V-", -9.0).part("BAT1", "battery", "V+", "0").build()
    assert battery_of(c, connect(c)) is not None
    assert live_rails(c) == {"V-": -9.0}  # negative rails stay


def test_how_the_battery_is_wired(circuit: Builder) -> None:
    """9c: what the battery's form says follows its wiring: on its own (no DC jack), through
    the DC jack's battery lug, or beside the adapter (its + elsewhere)."""
    alone = circuit().rail("V+", 9.0).part("BAT1", "battery", "V+", "0").build()
    lug = pedal(circuit).build()
    beside = (
        circuit()
        .rail("V+", 9.0)
        .part("DC", "dcjack", "V+", "0", None)
        .part("BAT1", "battery", "V+", "0")
        .build()
    )
    none = circuit().rail("V+", 9.0).part("R1", "resistor", "V+", "0", value="1k").build()
    apart = own_net(circuit)
    assert [battery_wiring(c, connect(c)) for c in (alone, lug, beside, none, apart)] == [
        "alone",
        "lug",
        "beside",
        None,
        "apart",
    ]


def own_net(circuit: Builder) -> Circuit:
    """A battery whose + is on a net of its own (VB), no DC jack, and a load on V+."""
    return (
        circuit()
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "0", value="10k")
        .part("BAT1", "battery", "vb", "0", volts=8)
        .part("R2", "resistor", "vb", "0", value="10k")
        .build()
    )


def test_a_battery_off_the_rails_leaves_v_plus_to_the_power_menu(
    circuit: Builder, models: ModelLibrary
) -> None:
    """9c (the user): the battery takes over a rail only when its + reaches it (on it, or
    on the DC jack's battery lug with the jack's + on it). On a net of its own it's just a
    supply there: the Power menu keeps V+ (its dropdown live), and the chip says nothing."""
    c = own_net(circuit)
    assert on_battery(c) is None
    assert live_rails(c) == {"V+": 9.0} == supply_volts(c)
    assert power_chip(c) is None
    lines = generate_netlist(c, models, Op()).text.splitlines()
    assert any(ln.startswith("V_RAIL1 ") for ln in lines)  # V+ from the Power menu
    assert any(ln.startswith("V_BAT1 ") for ln in lines)  # and the battery on its own net


def test_netlist_on_battery(models: ModelLibrary, circuit: Builder) -> None:
    lines = generate_netlist(pedal(circuit, plugged=False).build(), models, Op()).text.splitlines()
    assert "V_BAT1 bpos bneg DC 7.4" in lines
    assert "R_DC_sw bpos v_ 0.01" in lines  # the battery lug on the sleeve
    assert "R_IN_ring bneg 0 0.01" in lines  # the cable's sleeve on the ring
    assert not any(line.startswith("V_RAIL") for line in lines)


def test_netlist_on_the_dc_jack(models: ModelLibrary, circuit: Builder) -> None:
    lines = generate_netlist(pedal(circuit).build(), models, Op()).text.splitlines()
    assert "V_RAIL1 v_ 0 DC 9" in lines
    assert "R_DC_sw bpos v_ 1e+12" in lines  # the plug lifts the lug
    assert not any(line.startswith("V_BAT1") for line in lines)


def test_internal_resistance_is_in_series(models: ModelLibrary, circuit: Builder) -> None:
    c = circuit().rail("V+", 9.0).part("BAT1", "battery", "V+", "0", resistance="2").build()
    lines = generate_netlist(c, models, Op()).text.splitlines()
    assert "R_BAT1 bat1_cell v_ 2" in lines
    assert "V_BAT1 bat1_cell 0 DC 9" in lines


def test_the_jacks_are_drawn_in_their_state(circuit: Builder) -> None:
    parts = {p["ref"]: p for p in circuit_view(pedal(circuit, plugged=False).build())["parts"]}
    assert parts["DC"]["draw"] == {"plugged": False}
    assert parts["IN"]["draw"] == {"stereo": True}
    assert {pin["name"] for pin in parts["IN"]["pins"]} == {"out", "ring"}


def test_bias_follows_the_plug(circuit: Builder) -> None:
    on_battery = pedal(circuit, plugged=False).build()
    edges = graph.bias_edges(on_battery, connect(on_battery))
    assert ("bpos", "V+") in edges
    plugged = pedal(circuit).build()
    assert ("bpos", "V+") not in graph.bias_edges(plugged, connect(plugged))


def test_the_power_chip_follows_the_dc_jacks_switch(circuit: Builder) -> None:
    """D-145: with a battery and a DC jack, one chip per position of the jack's Power
    switch (0 plugged in, 1 the battery), whichever way the file has it."""
    for plugged in (True, False):
        chip = power_chip(pedal(circuit, plugged=plugged).build())
        assert chip == {
            "control": "DC",
            "positions": [
                {"text": "DC jack", "battery": False},
                {"text": "Battery · 7.4 V", "battery": True},
            ],
        }


def test_the_power_chip_with_one_or_neither(circuit: Builder) -> None:
    jack_only = circuit().rail("V+", 9.0).part("DC", "dcjack", "V+", "0", "x").build()
    battery_only = circuit().part("BAT1", "battery", "V+", "0", volts=9.0, state="fresh").build()
    neither = circuit().rail("V+", 9.0).part("R1", "resistor", "V+", "0", value="10k").build()
    assert power_chip(jack_only) == {"text": "DC jack", "battery": False}
    assert power_chip(battery_only) == {"text": "Battery · 9 V", "battery": True}
    assert power_chip(neither) is None


def beside(circuit: Builder, resistance: str | None = "2") -> CircuitBuilder:
    """A DC jack plugged in, and a battery wired straight to V+ instead of its lug."""
    return (
        circuit()
        .rail("V+", 9.0)
        .part("DC", "dcjack", "V+", "0")
        .part("BAT1", "battery", "V+", "0", volts=9.6, resistance=resistance)
        .part("R1", "resistor", "V+", "0", value="10k")
    )


def test_a_battery_off_the_lug_stays_beside_the_adapter(
    models: ModelLibrary, circuit: Builder
) -> None:
    """D-185: the plug cuts the battery off only through the battery lug; wired to V+
    directly it stays connected, through its internal resistance."""
    c = beside(circuit).build()
    assert battery_of(c, connect(c)) is c.part("BAT1")
    assert on_battery(c) is None
    assert live_rails(c) == {"V+": 9.0} == supply_volts(c)
    assert rail_sources(c) == {"V+": "V_RAIL1"}  # the draw is the adapter's
    lines = generate_netlist(c, models, Op()).text.splitlines()
    assert "V_RAIL1 v_ 0 DC 9" in lines
    assert "V_BAT1 bat1_cell 0 DC 9.6" in lines
    assert ("V+", "GND") in graph.bias_edges(c, connect(c))


def test_two_ideal_supplies_on_one_net_say_what_to_do(
    models: ModelLibrary, circuit: Builder
) -> None:
    with pytest.raises(NetlistError, match=r"battery lug .* internal resistance"):
        generate_netlist(beside(circuit, resistance=None).build(), models, Op())


def ring_pedal(circuit: Builder, cable: bool = True) -> CircuitBuilder:
    """A battery-only pedal switched by a stereo input jack: - on the ring, S on ground."""
    return (
        circuit()
        .rail("V+", 9.0)
        .part("BAT1", "battery", "V+", "bneg")
        .part("J1", "jack", stereo=True, label="Input", plugged=cable,
              pins={"T": "tip", "R": "bneg", "S": "0"})
        .part("R1", "resistor", "V+", "0", value="10k")
    )  # fmt: skip


@pytest.mark.parametrize(("cable", "ohms"), [(True, "0.01"), (False, "1e+12")])
def test_a_stereo_jacks_cable_joins_the_ring_to_the_sleeve(
    models: ModelLibrary, circuit: Builder, cable: bool, ohms: str
) -> None:
    c = ring_pedal(circuit, cable).build()
    lines = generate_netlist(c, models, Op()).text.splitlines()
    assert f"R_J1_ring bneg 0 {ohms}" in lines
    assert (("bneg", "GND") in graph.bias_edges(c, connect(c))) is cable


def test_an_unwired_ring_adds_nothing(models: ModelLibrary, circuit: Builder) -> None:
    c = (
        circuit()
        .part("BAT1", "battery", "V+", "0")
        .part("J1", "jack", stereo=True, pins={"T": "tip", "S": "0"})
        .part("R1", "resistor", "V+", "0", value="10k")
        .build()
    )
    assert not any("J1" in line for line in generate_netlist(c, models, Op()).text.splitlines())


def test_the_cable_is_a_knob_with_a_battery(circuit: Builder) -> None:
    c = ring_pedal(circuit, cable=False).build()
    knob = next(k for k in controls(c) if k["ref"] == "J1")
    assert knob == {
        "ref": "J1", "kind": "switch", "label": "Input cable", "refs": ["J1"],
        "position": 1, "positions": ["Cable in", "Cable out"], "plug": True,
    }  # fmt: skip
    parts = {p["ref"]: p for p in circuit_view(c)["parts"]}
    assert parts["J1"]["draw"] == {"stereo": True, "plugged": False}
    no_battery = circuit().part("J1", "jack", stereo=True).build()
    assert controls(no_battery) == []
