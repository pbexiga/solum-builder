"""The shipped guides (D-095): the capacitor guide covers every kind the schema allows,
once each, and the rule's advice picks a kind by value."""

import math
from pathlib import Path
from typing import get_args

import pytest

from solum.circuit.schema import Capacitor, Inductor
from solum.guides import GuideError, capacitor_guide, inductor_guide, pickup_guide
from solum.rules.checks import cap_advice
from solum.units import parse_value

REPO = Path(__file__).parents[2]


def test_every_capacitor_kind_has_one_entry() -> None:
    guide = capacitor_guide(REPO / "library")
    kinds = [k.kind for k in guide.kinds]
    schema_kinds = get_args(get_args(Capacitor.model_fields["kind"].annotation)[0])
    assert sorted(kinds) == sorted(schema_kinds)
    assert len(set(kinds)) == len(kinds)
    assert guide.kind("c0g").name.startswith("C0G")
    assert "\n" not in guide.kind("ceramic").watch  # folded YAML is one line


def test_each_pickups_c_is_its_measured_resonance() -> None:
    """C = 1 / ((2π f)² L), from the UIUC measurements (D-096): a '57/'62 Strat middle
    pickup, 2.55 H resonating at 8.11 kHz unloaded, has about 151 pF."""
    guide = pickup_guide(REPO / "library")
    kinds = [p.kind for p in guide.pickups]
    assert kinds == ["strat", "tele", "p90", "paf", "hot"]
    for p in guide.pickups:
        henries, f = parse_value(p.l), parse_value(p.resonance)
        assert parse_value(p.c) == pytest.approx(1 / ((2 * math.pi * f) ** 2 * henries), rel=0.01)
    strat = guide.pickups[0]
    assert (strat.r, strat.l, strat.volume) == ("6k38", "2.55", "250k")
    assert "\n" not in guide.intro


def test_wah_inductors_are_measured_ones_an_inductor_takes() -> None:
    """D-173: Stickman393's sheet at 1 kHz; the red Fasel 666 mH with 15.65 Ω of wire.
    Each preset fills an inductor part the schema accepts."""
    guide = inductor_guide(REPO / "library")
    kinds = [i.kind for i in guide.inductors]
    assert len(set(kinds)) == len(kinds)
    red = guide.inductors[0]
    assert (red.kind, parse_value(red.l), parse_value(red.r)) == (
        "fasel-red",
        pytest.approx(0.666),
        pytest.approx(15.65),
    )
    for i in guide.inductors:
        part = Inductor(
            ref="L1", type="inductor", value=i.l, resistance=parse_value(i.r), kind=i.kind
        )
        assert 0.4 < parse_value(part.value) < 0.8 and 10 < part.resistance < 40, i.kind
    assert "\n" not in guide.intro and "pedalpcb" in guide.source


def test_a_bad_guide_says_so(tmp_path: Path) -> None:
    (tmp_path / "guides").mkdir()
    (tmp_path / "guides" / "capacitors.yaml").write_text("title: x\nintro: y\nkinds: []\n")
    with pytest.raises(GuideError, match=r"capacitors\.yaml isn't a valid guide"):
        capacitor_guide(tmp_path)


@pytest.mark.parametrize(
    ("farads", "advice"),
    [
        (100e-12, "a C0G (NP0) ceramic or a film capacitor"),
        (10e-9, "a C0G (NP0) ceramic or a film capacitor"),
        (100e-9, "a film capacitor"),
        (10e-6, "a film capacitor, or an electrolytic for big values"),
    ],
)
def test_cap_advice_by_value(farads: float, advice: str) -> None:
    assert cap_advice(farads) == advice
