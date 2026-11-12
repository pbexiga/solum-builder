"""A charge pump's drawn parts (D-226): what its wiring makes it, and v25 files migrated."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import parse_circuit
from solum.circuit.parts import pin_positions
from solum.circuit.pump import pump_wiring
from solum.circuit.schema import ChargePump, Circuit
from solum.models import ModelLibrary, load_models
from solum.netlist import pump_frequency

LIBRARY = Path(__file__).parents[2] / "library"


def wiring(c: Circuit, ref: str = "U1") -> Any:
    pump = c.part(ref)
    assert isinstance(pump, ChargePump)
    return pump_wiring(c, connect(c), pump)


@pytest.mark.parametrize(
    ("outputs", "mode"),
    [
        ({"double": "o"}, "doubler"),
        ({"invert": "n"}, "inverter"),
        ({"double": "o", "invert": "n"}, "both"),
    ],
)
def test_the_wiring_makes_the_mode(outputs: dict[str, str], mode: str) -> None:
    c = CircuitBuilder().rail("V+", 9.0).pump("U1", "V+", **outputs).build()
    found = wiring(c)
    assert found.mode == mode and not found.problems
    assert found.outputs == [outputs[k] for k in ("double", "invert") if k in outputs]
    if "double" in outputs:
        d = found.doubler
        assert (d.cap.ref, d.low.ref, d.high.ref, d.junction) == (
            "C2" if "invert" in outputs else "C1",
            "D1",
            "D2",
            "U1_j",
        )
        assert found.driven[0] == "U1_j"


def test_a_lone_chip_pumps_nothing_and_says_how_to_wire_it() -> None:
    c = CircuitBuilder().rail("V+", 9.0).part("U1", "chargepump", "V+", "0", "0",
                                              model="TC1044S").build()  # fmt: skip
    found = wiring(c)
    assert found.mode == "" and found.outputs == []
    assert found.problems == (
        "U1 pumps nothing yet: draw a flying cap from pin 2 (CAP+) to pin 4 (CAP\u2212) for "
        "\u2212V+ on pin 5, or a cap from pin 2 to two diodes for 2 \u00d7 V+ (the charge-pump "
        "blocks show both).",
    )


def test_a_doubler_without_its_first_diode_says_which() -> None:
    c = (
        CircuitBuilder().rail("V+", 9.0)
        .part("U1", "chargepump", "V+", "0", "0", "cp", model="TC1044S")
        .part("C1", "capacitor", "j", "cp", value="10u")
        .part("D2", "diode", "j", "o", model="1N5817")
    ).build()  # fmt: skip
    found = wiring(c)
    assert found.doubler is None
    assert found.problems == (
        "U1's doubler needs a diode from V+ into C1: its anode on V+, its cathode where C1 "
        "meets the second diode.",
    )


# --- v25 files: the parts drawn in (D-226) ---


def v25(pump: dict[str, Any], **file: Any) -> dict[str, Any]:
    """A v25 file with `pump` at the origin (in at (-40, 0), out (40, 0), gnd (0, 40), neg
    (40, 20)) and a 10 µF reservoir C1 off to the right on its output."""
    reservoir = {"ref": "C1", "type": "capacitor", "pos": [300, 40], "rot": 90, "value": "10µ",
                 "kind": "electrolytic"}  # fmt: skip
    return {"schema": 25, "id": "c", "name": "c", "power": {"rails": {"V+": 9.0}},
            "parts": [{"ref": "U1", "type": "chargepump", "pos": [0, 0], "model": "TC1044S",
                       **pump}, reservoir], **file}  # fmt: skip


def drawn_points(c: Circuit, refs: set[str]) -> set[tuple[int, int]]:
    return {at for p in c.parts if p.ref in refs for at in pin_positions(p).values()}


def test_v25_doubler_gets_its_cap_and_diodes_on_its_old_nets() -> None:
    """Labels on its pins (as the blocks have them): the chip moves to a clear spot, its
    pins keep their nets, and D2 drives V18. Labels alone on old pins go."""
    c = parse_circuit(v25({"boost": True}, labels=[
        {"net": "V+", "pos": [-40, 0]}, {"net": "GND", "pos": [0, 40]},
        {"net": "V18", "pos": [40, 0]}, {"net": "V18", "pos": [300, 20]},
        {"net": "GND", "pos": [300, 60]},
    ]))  # fmt: skip
    nets = connect(c)
    assert [p.ref for p in c.parts] == ["C1", "U1", "C2", "D1", "D2"]
    assert c.part("U1") == ChargePump(ref="U1", type="chargepump", pos=c.part("U1").pos,
                                      model="TC1044S")  # fmt: skip
    assert wiring(c).boost  # v28: boost is pin 1 wired to V+
    assert nets.net_of("U1", "in") == nets.net_of("D1", "A") == "V+"
    assert nets.net_of("U1", "gnd") == nets.net_of("U1", "out") == "GND"
    assert nets.net_of("D2", "K") == nets.net_of("C1", "1") == "V18"
    assert c.part("C2").value == "10µ" and c.part("D1").model == "1N5817"
    found = wiring(c)
    assert found.mode == "doubler" and found.doubler.cap.ref == "C2"
    assert not any(tuple(lb.pos) in {(-40, 0), (0, 40), (40, 0)} for lb in c.labels)


def test_v25_inverter_draws_its_flying_cap_and_keeps_an_unlabelled_net() -> None:
    """Its output wired straight to the reservoir, no label: the net gets one named after
    the pin (U1_OUT) where the old pin was, so the reservoir stays on it."""
    wires = [{"from": [40, 0], "to": [300, 0]}, {"from": [300, 0], "to": [300, 20]}]
    labels = [{"net": "V+", "pos": [-40, 0]}, {"net": "GND", "pos": [0, 40]},
              {"net": "GND", "pos": [300, 60]}]  # fmt: skip
    c = parse_circuit(v25({"mode": "inverter", "model": "LT1054"}, wires=wires, labels=labels))
    nets = connect(c)
    assert nets.net_of("U1", "out") == nets.net_of("C1", "1") == "U1_OUT"
    assert {nets.net_of("C2", "1"), nets.net_of("C2", "2")} == {
        nets.net_of("U1", "cap+"),
        nets.net_of("U1", "cap-"),
    }
    assert c.part("C2").value == "100µ"  # the LT1054 sheet's cap: it simulates as before
    assert wiring(c).mode == "inverter"


def test_v25_both_keeps_neg_and_probes_and_targets_follow() -> None:
    """The Klon's: `out` doubled, `neg` inverted. A probe on the old `out` goes to D2's
    cathode, one on `neg` to VOUT; a trimmer's target likewise. The new parts touch
    nothing that was drawn."""
    trimmer = {"ref": "TR1", "type": "trimmer", "pos": [-300, 0], "value": "10k",
               "bias_target": {"node": "U1.neg", "volts": -8.0}}  # fmt: skip
    data = v25({"mode": "both", "model": "LT1054", "diode": "1N4001"},
               labels=[{"net": "V+", "pos": [-40, 0]}, {"net": "GND", "pos": [0, 40]},
                       {"net": "VB", "pos": [40, 0]}, {"net": "-VA", "pos": [40, 20]}],
               probes={"in": "U1.out", "out": "U1.neg"})  # fmt: skip
    data["parts"].append(trimmer)
    old_points = {(300, 20), (300, 60), (-320, 0), (-280, 0), (-300, 20)}
    c = parse_circuit(data)
    nets = connect(c)
    assert nets.net_of("D2", "K") == "VB" and nets.net_of("U1", "out") == "-VA"
    assert c.part("D1").model == c.part("D2").model == "1N4001"
    assert c.probes.in_ == "D2.K" and c.probes.out == "U1.out"
    assert c.part("TR1").bias_target.node == "U1.out"
    assert not drawn_points(c, {"U1", "C2", "C3", "D1", "D2"}) & old_points
    assert wiring(c).mode == "both"


def pumped(boost: bool, model: str = "TC1044S") -> Circuit:
    return (CircuitBuilder().rail("V+", 9.0).pump("U1", "V+", invert="VN", boost=boost, model=model)
            .part("C9", "capacitor", "VN", "0", value="10u").build())  # fmt: skip


def test_pin_1_on_v_plus_is_boost_and_left_open_is_not() -> None:
    """D-234: boost is wired, as on a real board: pin 1 on the chip's V+, not a setting."""
    assert wiring(pumped(True)).boost
    assert not wiring(pumped(False)).boost
    left_open = pumped(False)
    assert connect(left_open).net_of("U1", "1") != "V+"


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([LIBRARY / "models"])


def test_boost_raises_the_pump_only_on_a_chip_with_a_boost_pin(models: ModelLibrary) -> None:
    """A TC1044S boosted pumps at its sheet's 22.5 kHz (5 kHz without); pin 1 on V+ of an
    LT1054 is its FB/SHDN held high: 25 kHz either way, and no error."""
    tc = pumped(True).part("U1")
    lt = pumped(True, "LT1054").part("U1")
    assert isinstance(tc, ChargePump) and isinstance(lt, ChargePump)
    assert pump_frequency(tc, models, True) == pytest.approx(22500.0)
    assert pump_frequency(tc, models, False) == pytest.approx(5000.0)
    assert pump_frequency(lt, models, True) == pytest.approx(25000.0)


def test_v27_boost_becomes_a_label_on_pin_1() -> None:
    """v28 (D-234): a v27 pump with `boost` gets its V+ net's label at pin 1 (the label on
    pin 8's net); one without gets nothing; `boost` is gone from both."""

    def v27(boost: bool) -> dict[str, Any]:
        return {"schema": 27, "id": "c", "name": "c", "power": {"rails": {"V+": 9.0}},
                "parts": [{"ref": "U1", "type": "chargepump", "pos": [100, 100], "rot": 90,
                           "model": "TC1044S", "boost": boost}],
                "wires": [{"from": [130, 140], "to": [130, 160]}],  # pin 8, turned, to a label
                "labels": [{"net": "V+", "pos": [130, 160]}]}  # fmt: skip

    boosted = parse_circuit(v27(True))
    assert [(lb.net, lb.pos) for lb in boosted.labels] == [("V+", (130, 160)), ("V+", (130, 60))]
    assert pin_positions(boosted.part("U1"))["1"] == (130, 60)
    assert wiring(boosted).boost
    plain = parse_circuit(v27(False))
    assert len(plain.labels) == 1 and not wiring(plain).boost
