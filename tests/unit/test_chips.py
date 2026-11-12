"""Op-amp chips (schema v12, D-140): pairing old op-amps into chips, the schema's checks,
power from real pins (a dual's on its power unit since v19, D-179), unused halves,
datasheet pin numbers, and every starter's and block's netlist matching its v11 one but
for the names."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.chips import halves, power_part, supply_nets, unused, unused_halves
from solum.circuit.connectivity import connect
from solum.circuit.io import CircuitError, load_circuit, parse_circuit
from solum.circuit.parts import pin_positions
from solum.circuit.schema import Inverter, Opamp, Ota, PowerUnit, Trimmer
from solum.models import ModelLibrary, load_models
from solum.netlist import Ac, Op, generate_netlist
from tests.jig import jig

REPO = Path(__file__).parents[2]
OLD = REPO / "tests/fixtures/circuits/old/schema-v11.json"
V11_NETLISTS = REPO / "tests/fixtures/netlists/v11"
Builder = Callable[..., CircuitBuilder]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library/models"])


def _opamp(c: Any, ref: str) -> Opamp:
    p = c.part(ref)
    assert isinstance(p, Opamp)
    return p


def test_old_op_amps_pair_into_chips_in_ref_order() -> None:
    """U1 and U3 share a model and supply: IC1A and IC1B. U2 (on V+F) can't join them, so
    it gets a spare half b; IC2 is taken by a resistor, so it's IC3. The LM308 is a single."""
    c = load_circuit(OLD)
    halves = {p.ref: (p.half, p.model) for p in c.parts if isinstance(p, Opamp)}
    assert halves == {
        "IC1A": ("a", "TL072"), "IC1B": ("b", "TL072"),
        "IC3A": ("a", "TL072"), "IC3B": ("b", "TL072"),
        "IC4": (None, "LM308"),
        "IC5A": ("a", "RC4558"), "IC5B": ("b", "RC4558"),
    }  # fmt: skip
    assert [p.ref for p in c.parts][:4] == ["IC1B", "IC1A", "IC3A", "IC4"]  # file order kept
    assert _opamp(c, "IC1A").pos == (0, 0) and _opamp(c, "IC1B").pos == (400, 0)


def test_the_hidden_supply_becomes_labels_on_the_power_pins() -> None:
    c = load_circuit(OLD)
    nets = connect(c)
    assert supply_nets(c, nets, _opamp(c, "IC1A")) == ("V+", "GND")
    assert supply_nets(c, nets, _opamp(c, "IC1B")) == ("V+", "GND")  # the power unit's
    assert supply_nets(c, nets, _opamp(c, "IC3A")) == ("V+F", "GND")
    assert supply_nets(c, nets, _opamp(c, "IC4")) == ("V+", "GND")
    # IC1A is turned 90°, so its power unit IC1C (v19) is too: 60 beside it, V+ at (40, 60)
    unit = c.part("IC1C")
    assert isinstance(unit, PowerUnit) and (unit.pos, unit.rot) == ((0, 60), 90)
    assert pin_positions(unit)["V+"] == (40, 60)
    rail = next(lb for lb in c.labels if lb.pos == (40, 60))
    assert rail.net == "V+"


def test_a_spare_half_is_placed_clear_and_left_unused() -> None:
    c = load_circuit(OLD)
    nets = connect(c)
    assert {"IC3B", "IC5B"} <= unused_halves(c, nets)  # nothing in this file is wired
    spare = _opamp(c, "IC5B")
    assert spare.pos == (920, 0)  # 120 to the right of IC5A, where nothing is drawn
    assert "V+" not in pin_positions(spare)  # the power unit carries the chip's power


def test_names_of_renamed_parts_follow() -> None:
    c = load_circuit(OLD)
    assert c.part("IC1A").note == "the clipper" and c.net_notes == {"V+F": "filtered"}
    assert (c.probes.in_, c.probes.out) == ("IC1B.+", "IC5A.out")
    rt1 = c.part("TR1")
    assert isinstance(rt1, Trimmer) and rt1.bias_target is not None
    assert rt1.bias_target.node == "IC1A.out"


def _chip(**b: Any) -> dict[str, Any]:
    return {
        "schema": 13, "id": "c", "name": "c",
        "parts": [{"ref": "IC1A", "type": "opamp", "model": "TL072", "half": "a"},
                  {"ref": "IC1B", "type": "opamp", "model": "TL072", "half": "b", **b}],
    }  # fmt: skip


def _v19(data: dict[str, Any], **unit: Any) -> dict[str, Any]:
    """A v19 file of the chip, with its power unit."""
    power = {"ref": "IC1C", "type": "powerunit", "model": "TL072", **unit}
    return {**data, "schema": 19, "parts": [*data["parts"], power]}


def test_a_chip_has_both_halves_and_one_model() -> None:
    assert len(parse_circuit(_chip()).parts) == 3  # v19 adds its power unit (D-179)
    alone = _chip()
    alone["parts"].pop()
    with pytest.raises(CircuitError, match=r"2 op-amps, IC1A and IC1B, but IC1B isn.t in"):
        parse_circuit(alone)
    with pytest.raises(CircuitError, match=r"different models \(TL072 and RC4558\)"):
        parse_circuit(_chip(model="RC4558"))
    with pytest.raises(CircuitError, match="Half B of a chip is IC or U, a number and B"):
        parse_circuit(_chip(ref="IC1x"))


def test_a_dual_has_its_power_unit() -> None:
    """v19 (D-179): IC1C, the chip's model; no power unit without its chip."""
    assert isinstance(parse_circuit(_v19(_chip())).part("IC1C"), PowerUnit)
    with pytest.raises(
        CircuitError, match=r"IC1's power unit \(V\+ and V-\) is IC1C, but it isn't"
    ):
        parse_circuit({**_chip(), "schema": 19})
    with pytest.raises(CircuitError, match=r"is IC1C, but it's named IC1E"):
        parse_circuit(_v19(_chip(), ref="IC1E"))
    with pytest.raises(CircuitError, match=r"different models \(TL072 and RC4558\)"):
        parse_circuit(_v19(_chip(), model="RC4558"))
    with pytest.raises(CircuitError, match="IC2C is a power unit, but chip IC2 has nothing else"):
        parse_circuit(
            _v19(_chip(), ref="IC2C") | {"parts": [_v19(_chip(), ref="IC2C")["parts"][-1]]}
        )
    with pytest.raises(CircuitError, match="A chip's power unit is the chip's ref and the letter"):
        parse_circuit(_v19(_chip(), ref="IC1"))


def _quad(letters: str = "abcd", **d: Any) -> dict[str, Any]:
    parts = [{"ref": f"IC1{x.upper()}", "type": "opamp", "model": "TL074", "half": x}
             for x in letters]  # fmt: skip
    if d:
        parts[-1] |= d
    return {"schema": 18, "id": "c", "name": "c", "parts": parts}


def test_a_quad_has_all_four_halves_and_one_model() -> None:
    """v18 (D-172): a quad is IC1A to IC1D; a chip with a C or D is a quad. v19: its power
    unit is IC1E."""
    assert parse_circuit(_quad()).parts[-1].ref == "IC1E"
    with pytest.raises(CircuitError, match=r"has 4 op-amps, IC1A to IC1D, but IC1B, IC1D isn.t"):
        parse_circuit(_quad("ac"))
    with pytest.raises(CircuitError, match=r"different models \(TL074 and TL072\)"):
        parse_circuit(_quad(model="TL072"))
    with pytest.raises(CircuitError, match="Half D of a chip is IC or U, a number and D"):
        parse_circuit(_quad(ref="IC1E"))


def test_a_quads_halves_run_from_its_power_unit(circuit: Builder) -> None:
    """No half has power pins; their supply is the power unit's (D-179)."""
    b = circuit().rail("V+", 9).part("IC1A", "opamp", model="TL074", half="a")
    b.part("IC1B", "opamp", model="TL074", half="b")
    b.part("IC1C", "opamp", "i", "i", "o", model="TL074", half="c")
    b.part("IC1D", "opamp", model="TL074", half="d")
    c = b.build()
    nets = connect(c)
    ic1a, ic1c, ic1d = (_opamp(c, r) for r in ("IC1A", "IC1C", "IC1D"))
    assert [h.ref for h in halves(c, ic1d)] == ["IC1A", "IC1B", "IC1C", "IC1D"]
    assert power_part(c, ic1c) == c.part("IC1E") and "V+" not in pin_positions(ic1a)
    assert supply_nets(c, nets, ic1c) == supply_nets(c, nets, ic1a) == ("V+", "GND")
    assert unused(c, nets, ic1d) and not unused(c, nets, ic1c)


def test_a_4049_is_six_inverters_and_its_power_unit_g(circuit: Builder) -> None:
    """D-180: IC1A to IC1F and power unit IC1G (VDD on V+, VSS on V-); an inverter is used
    once its in or out joins something."""
    b = circuit().rail("V+", 9).part("IC1A", "inverter", "i", "o", model="CD4049UB", half="a")
    for x in "bcdef":
        b.part(f"IC1{x.upper()}", "inverter", model="CD4049UB", half=x)
    c = b.build()
    nets = connect(c)
    a, f = c.part("IC1A"), c.part("IC1F")
    assert isinstance(a, Inverter) and isinstance(f, Inverter)
    assert power_part(c, f) == c.part("IC1G") and len(halves(c, a)) == 6
    assert supply_nets(c, nets, f) == ("V+", "GND")
    assert unused_halves(c, nets) == {"IC1B", "IC1C", "IC1D", "IC1E", "IC1F"}
    assert set(pin_positions(a)) == {"in", "out"}


def test_a_unit_wired_only_to_itself_is_powered_from_its_unit(
    circuit: Builder, models: ModelLibrary
) -> None:
    """A 4049 inverter with its input tied to its output (self-biased) is simulated: it
    reaches the supply through its power unit, which is drawing only."""
    b = circuit().rail("V+", 9).part("IC1A", "inverter", "x", "x", model="CD4049UB", half="a")
    for x in "bcdef":
        b.part(f"IC1{x.upper()}", "inverter", model="CD4049UB", half=x)
    text = generate_netlist(b.build(), models, Op()).text
    assert "X_IC1A x x v_ 0 CD4049UB_INV" in text
    assert "IC1B" not in text


def test_a_chip_is_one_kind_of_unit_and_complete() -> None:
    """D-180: a 4049 has all six inverters; a chip's units can't mix op-amps and OTAs."""
    inv = [{"ref": f"IC1{x.upper()}", "type": "inverter", "model": "CD4049UB", "half": x}
           for x in "abcdef"]  # fmt: skip
    unit = {"ref": "IC1G", "type": "powerunit", "model": "CD4049UB"}
    data = {"schema": 20, "id": "c", "name": "c", "parts": [*inv, unit]}
    assert len(parse_circuit(data).parts) == 7
    with pytest.raises(CircuitError, match=r"6 inverters, IC1A to IC1F, but IC1C isn.t"):
        parse_circuit({**data, "parts": [p for p in data["parts"] if p["ref"] != "IC1C"]})
    mixed = [{"ref": "IC2A", "type": "opamp", "model": "TL072", "half": "a"},
             {"ref": "IC2B", "type": "ota", "model": "TL072", "half": "b"},
             {"ref": "IC2C", "type": "powerunit", "model": "TL072"}]  # fmt: skip
    with pytest.raises(CircuitError, match="Chip IC2 mixes op-amps and OTAs"):
        parse_circuit({**data, "parts": mixed})


def test_an_ota_single_has_its_power_and_a_dual_half_its_buffer(circuit: Builder) -> None:
    """D-180: a CA3080 carries its own V+ and V-; an LM13700 half has diode bias and a
    buffer, and runs from IC1C."""
    b = circuit().rail("V+", 9).part("IC2", "ota", "p", "m", "o", "b", model="CA3080")
    b.part("IC1A", "ota", "p", "m", "o2", "b2", "d", "o2", "out", model="LM13700", half="a")
    c = b.part("IC1B", "ota", model="LM13700", half="b").build()
    nets = connect(c)
    single, a = c.part("IC2"), c.part("IC1A")
    assert isinstance(single, Ota) and isinstance(a, Ota)
    assert set(pin_positions(single)) == {"+", "-", "out", "iabc", "V+", "V-"}
    assert set(pin_positions(a)) == {"+", "-", "out", "iabc", "dbias", "bufin", "bufout"}
    assert power_part(c, single) is single and power_part(c, a) == c.part("IC1C")
    assert supply_nets(c, nets, a) == ("V+", "GND")
    assert unused_halves(c, nets) == {"IC1B"}


def test_a_half_is_unused_until_a_signal_pin_joins_something(circuit: Builder) -> None:
    b = circuit().part("IC1A", "opamp", "x", "x", "x", model="TL072", half="a")
    b.part("IC1B", "opamp", model="TL072", half="b")
    c = b.build()
    nets = connect(c)
    ic1a, ic1b = _opamp(c, "IC1A"), _opamp(c, "IC1B")
    assert unused(c, nets, ic1b) and not unused(c, nets, ic1a)
    assert halves(c, ic1b) == [ic1a, ic1b] and power_part(c, ic1b) == c.part("IC1C")
    assert power_part(c, ic1a) == c.part("IC1C")
    labelled = circuit().part("IC1A", "opamp", model="TL072", half="a")
    c = labelled.part("IC1B", "opamp", None, None, "OUT", model="TL072", half="b").build()
    assert not unused(c, connect(c), _opamp(c, "IC1B"))  # a label counts


def test_an_unused_half_is_left_out_of_the_netlist(circuit: Builder, models: ModelLibrary) -> None:
    b = circuit().rail("V+", 9).part("IN", "guitar", "in")
    b.part("IC1A", "opamp", "in", "o", "o", model="TL072", half="a")
    b.part("IC1B", "opamp", model="TL072", half="b").part("OUT", "amp", "o")
    text = generate_netlist(b.build(), models, Op()).text
    assert "X_IC1A in o v_ 0 o TL072" in text
    assert "IC1B" not in text


def test_half_b_runs_from_the_power_unit_s_pins(circuit: Builder, models: ModelLibrary) -> None:
    b = circuit().rail("V+", 9).part("IN", "guitar", "in")
    b.part("IC1A", "opamp", "in", "o", "o", model="TL072", half="a", supply=("V+F", "0"))
    b.part("IC1B", "opamp", "o", "p", "p", model="TL072", half="b")
    b.part("R1", "resistor", "V+", "V+F", value="47").part("OUT", "amp", "p")
    text = generate_netlist(b.build(), models, Op()).text
    assert "X_IC1B o p v_f 0 p TL072" in text


@pytest.mark.parametrize(
    ("model", "pins"),
    [
        ("TL072", {("a", "out"): 1, ("a", "-"): 2, ("a", "+"): 3, (None, "V-"): 4,
                   ("b", "+"): 5, ("b", "-"): 6, ("b", "out"): 7, (None, "V+"): 8}),
        ("TL074", {("a", "out"): 1, ("a", "-"): 2, ("a", "+"): 3, (None, "V+"): 4,
                   ("b", "+"): 5, ("b", "-"): 6, ("b", "out"): 7, ("c", "out"): 8,
                   ("c", "-"): 9, ("c", "+"): 10, (None, "V-"): 11, ("d", "+"): 12,
                   ("d", "-"): 13, ("d", "out"): 14}),
        ("RC4558", {("a", "out"): 1, ("a", "+"): 3, ("b", "out"): 7, (None, "V+"): 8}),
        ("TL071", {(None, "null1"): 1, (None, "-"): 2, (None, "+"): 3, (None, "V-"): 4,
                   (None, "null2"): 5, (None, "out"): 6, (None, "V+"): 7, (None, "nc"): 8}),
        ("LM741", {(None, "null1"): 1, (None, "out"): 6, (None, "V+"): 7, (None, "nc"): 8}),
        ("LM308", {(None, "comp1"): 1, (None, "-"): 2, (None, "+"): 3, (None, "V-"): 4,
                   (None, "nc"): 5, (None, "out"): 6, (None, "V+"): 7, (None, "comp2"): 8}),
    ],
)  # fmt: skip
def test_pin_numbers_are_the_datasheet_s(
    models: ModelLibrary, model: str, pins: dict[tuple[str | None, str], int]
) -> None:
    m = models.get(model)
    assert {k: m.pin_number(pin, half) for (half, pin) in pins for k in [(half, pin)]} == pins
    assert m.info.package is not None and m.info.package.source
    assert m.halves == {"TL072": 2, "RC4558": 2, "TL074": 4}.get(model, 1)
    assert m.pin_number("null1", "a") is None if m.halves > 1 else True


def test_every_op_amp_model_has_cited_pin_numbers(models: ModelLibrary) -> None:
    for model_id in models.ids("opamp"):
        package = models.get(model_id).info.package
        assert package is not None, f"{model_id} has no pin numbers"
        pins = 14 if models.get(model_id).halves == 4 else 8
        assert sorted(package.pins.values()) == list(range(1, pins + 1)), model_id


# --- netlists unchanged by chips: same lines, only names differ (D-140) ---


def _tokens(text: str) -> list[list[str]]:
    """A netlist's lines as lower-case tokens, comments left out (SPICE ignores case)."""
    return [line.lower().split() for line in text.splitlines() if not line.startswith("*")]


def _number(token: str) -> bool:
    return re.fullmatch(r"[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?", token) is not None


def same_but_names(old: str, new: str) -> None:
    """`new` is `old` with names changed consistently (one new name per old one): every
    value, every element and every connection is the same."""
    a, b = _tokens(old), _tokens(new)
    assert len(a) == len(b), "a different number of lines"
    names: dict[str, str] = {}
    for line_a, line_b in zip(a, b, strict=True):
        assert len(line_a) == len(line_b), (line_a, line_b)
        for x, y in zip(line_a, line_b, strict=True):
            if _number(x) or _number(y) or "=" in x:
                assert x == y, (line_a, line_b)
            else:
                assert names.setdefault(x, y) == y, f"{x} is {names[x]} and {y}"
    assert len(set(names.values())) == len(names), "two old names became one"


CIRCUITS = sorted([*REPO.glob("library/starters/*.json"), *REPO.glob("library/blocks/*.json")])


@pytest.mark.parametrize("path", CIRCUITS, ids=lambda p: p.stem)
def test_netlists_are_the_v11_ones_but_for_names(path: Path, models: ModelLibrary) -> None:
    c = load_circuit(path)
    if c.template:
        c = jig(c, supply_load=10e3)
    for name, analysis in (("op", Op()), ("ac", Ac())):
        old = V11_NETLISTS / f"{path.stem}-{name}.cir"
        if not old.exists():
            continue  # a block with no input has no AC netlist
        new = generate_netlist(c, models, analysis).text
        if json.loads(path.read_text())["schema"] < 12:
            assert new == old.read_text()  # untouched files: byte for byte
        else:
            same_but_names(old.read_text(), new)


def _v18_dual(*extra: dict[str, Any], **file: Any) -> dict[str, Any]:
    """A v18 TL072 at the origin: half a's V+ at (0, -40), V- at (0, 40); half b far off."""
    parts = [
        {"ref": "IC1A", "type": "opamp", "model": "TL072", "half": "a", "pos": [0, 0]},
        {"ref": "IC1B", "type": "opamp", "model": "TL072", "half": "b", "pos": [0, 400]},
        *extra,
    ]
    return {"schema": 18, "id": "c", "name": "c", "parts": parts, **file}


def test_v19_moves_a_labelled_supply_onto_the_power_unit() -> None:
    """D-179: V+ wired up to its label, GND's label on the pin: the unit goes 60 to the
    right with the same labels on its pins, and no wire is added. GND's label, alone on
    the old pin, moves rather than staying behind on nothing."""
    c = parse_circuit(_v18_dual(
        wires=[{"from": [0, -40], "to": [0, -60]}],
        labels=[{"net": "V+", "pos": [0, -60]}, {"net": "GND", "pos": [0, 40]}],
        power={"rails": {"V+": 9}},
    ))  # fmt: skip
    unit = c.part("IC1C")
    assert isinstance(unit, PowerUnit) and unit.pos == (60, 0) and unit.model == "TL072"
    assert len(c.wires) == 1
    assert sorted((lb.net, lb.pos) for lb in c.labels) == [
        ("GND", (60, 40)), ("V+", (0, -60)), ("V+", (60, -40)),
    ]  # fmt: skip
    assert supply_nets(c, connect(c), _opamp(c, "IC1B")) == ("V+", "GND")


def test_v19_wires_an_unlabelled_supply_to_the_power_unit() -> None:
    """V+ fed through R1 with no label on the net: a wire from the old pin to the unit's."""
    r1 = {"ref": "R1", "type": "resistor", "value": "47", "pos": [-20, -60]}  # pins (-40|0, -60)
    c = parse_circuit(_v18_dual(
        r1, wires=[{"from": [0, -40], "to": [0, -60]}],
        labels=[{"net": "V+", "pos": [-40, -60]}, {"net": "GND", "pos": [0, 40]}],
        power={"rails": {"V+": 9}},
    ))  # fmt: skip
    assert c.part("IC1C").pos == (60, 0)
    # out to (0, -60) on the wire already there, clear of the op-amp's pin row, across and back in
    assert [(w.from_, w.to) for w in c.wires[1:]] == [
        ((0, -60), (60, -60)),
        ((60, -60), (60, -40)),
    ]
    nets = connect(c)
    assert supply_nets(c, nets, _opamp(c, "IC1A"))[0] == nets.net_of("R1", "2")


ACROSS = [
    {"from": [x, -100], "to": [x, 100]} for x in (*range(-200, 0, 20), *range(60, 221, 20))
]  # wires across every spot beside half a


def test_v19_with_no_clear_spot_beside_puts_a_labelled_unit_past_the_drawing() -> None:
    """Wires across every spot beside it, GND labelled: the unit goes 80 right of the
    rightmost point (the wire at x 220), level with half a, with its label."""
    c = parse_circuit(_v18_dual(wires=ACROSS, labels=[{"net": "GND", "pos": [0, 40]}]))
    assert c.part("IC1C").pos == (300, 0)
    assert ("GND", (300, 40)) in {(lb.net, lb.pos) for lb in c.labels}
    assert supply_nets(c, connect(c), _opamp(c, "IC1A"))[1] == "GND"


def test_v19_with_no_clear_spot_and_no_label_puts_the_unit_on_half_a() -> None:
    """Blocked beside, V+ fed through R1 with no label: the unit sits on half a, its pins
    where hers were, so every connection stays."""
    r1 = {"ref": "R1", "type": "resistor", "value": "47", "pos": [-20, -60]}
    c = parse_circuit(_v18_dual(r1, wires=[*ACROSS, {"from": [0, -40], "to": [0, -60]}]))
    assert c.part("IC1C").pos == (0, 0)
    nets = connect(c)
    assert supply_nets(c, nets, _opamp(c, "IC1A"))[0] == nets.net_of("R1", "2")
