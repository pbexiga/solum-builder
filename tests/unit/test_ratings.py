"""Capacitor ratings (D-360): what a supply calls for, filled on choosing the type and by
*Use suggested ratings*."""

from collections.abc import Callable

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.ratings import (
    cap_rating,
    cap_rating_view,
    rating_fill,
    suggested_cap_rating,
    supply_top,
)
from solum.view import circuit_view

Builder = Callable[..., CircuitBuilder]


@pytest.mark.parametrize(
    ("volts", "rating"),
    [(5.0, 6.3), (9.0, 16.0), (12.8, 16.0), (12.9, 25.0), (18.0, 25.0), (80.0, 100.0)],
)
def test_the_smallest_rating_sold_with_room(volts: float, rating: float) -> None:
    """Inside 80 % of it: 9 V needs 11.25 V, so 16 V; 18 V needs 22.5 V, so 25 V."""
    assert cap_rating(volts) == rating


def test_past_the_largest_rating_there_is_none() -> None:
    assert cap_rating(81.0) is None


def test_the_supply_by_its_size_whatever_the_plugs(circuit: Builder) -> None:
    """A rating is for when the pedal's powered: the battery cut off still counts."""
    menu = circuit().rail("V+", 18.0).rail("V-", -9.0).build()
    battery = circuit().part("BAT1", "battery", "V+", "0", volts=9.6).build()
    assert supply_top(menu) == 18.0 and supply_top(battery) == pytest.approx(9.6)
    assert supply_top(circuit().part("R1", "resistor", "a", "0", value="1k").build()) is None


def test_the_rating_on_choosing_the_type(circuit: Builder) -> None:
    nine = circuit().rail("V+", 9.0).part("C1", "capacitor", "V+", "0", value="10u").build()
    assert suggested_cap_rating(nine) == 16.0
    assert cap_rating_view(nine) == {"volts": 16.0, "kinds": ["electrolytic", "tantalum"]}
    assert circuit_view(nine)["cap_rating"] == cap_rating_view(nine)
    eighteen = circuit().rail("V+", 18.0).build()
    assert suggested_cap_rating(eighteen) == 25.0
    none = circuit().part("C1", "capacitor", "a", "0", value="10u").build()
    assert suggested_cap_rating(none) is None and cap_rating_view(none) is None


def caps(circuit: Builder) -> CircuitBuilder:
    """9 V; C1 to C3 electrolytic (no rating, 6.3 V and 10 V), C4 a tantalum rated well
    over, C5 a film with no rating, C6 an electrolytic at 25 V."""
    return (
        circuit()
        .rail("V+", 9.0)
        .part("C1", "capacitor", "V+", "0", value="100u", kind="electrolytic")
        .part("C2", "capacitor", "V+", "0", value="100u", kind="electrolytic", rating_v=6.3)
        .part("C3", "capacitor", "V+", "0", value="100u", kind="electrolytic", rating_v=10)
        .part("C4", "capacitor", "V+", "0", value="10u", kind="tantalum", rating_v=35)
        .part("C5", "capacitor", "V+", "0", value="100n", kind="film")
        .part("C6", "capacitor", "half", "0", value="10u", kind="electrolytic")
    )


def test_use_suggested_ratings_fills_the_empty_ones_from_the_supply(circuit: Builder) -> None:
    """Without the DC, only the empty ones: C1 and C6; the film stays unset."""
    c = caps(circuit).build()
    assert rating_fill(c, connect(c), None) == {"C1": 16.0, "C6": 16.0}


def test_use_suggested_ratings_fixes_the_wrong_ones_from_the_dc(circuit: Builder) -> None:
    """9 V across: over 6.3 V (C2) and too close to 10 V (C3) are wrong, both to 16 V; C4's
    35 V is fine. C6 has 4.5 V across but no rating: the supply's 16 V."""
    c = caps(circuit).build()
    dc = {"V+": 9.0, "half": 4.5, "GND": 0.0}
    assert rating_fill(c, connect(c), dc) == {"C1": 16.0, "C2": 16.0, "C3": 16.0, "C6": 16.0}


def test_nothing_to_fill_with_no_supply(circuit: Builder) -> None:
    c = circuit().part("C1", "capacitor", "a", "0", value="10u", kind="electrolytic").build()
    assert rating_fill(c, connect(c), None) == {}
