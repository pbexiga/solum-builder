"""Circuit schema: validation, plain-English errors, round trips, migrations."""

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from solum.circuit.connectivity import connect
from solum.circuit.io import (
    CircuitError,
    circuit_to_dict,
    load_circuit,
    parse_circuit,
    save_circuit,
)
from solum.circuit.migrations import MigrationError, migrate
from solum.circuit.refs import ref_key
from solum.circuit.schema import (
    SCHEMA_VERSION,
    Bjt,
    Guitar,
    Jfet,
    Trimmer,
    id_from_name,
    json_schema_text,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "circuits" / "jfet-drive.json"


@pytest.fixture
def data() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text())
    return loaded


def test_loads_the_spec_example(data: dict[str, Any]) -> None:
    c = load_circuit(FIXTURE)
    assert c.name == "Example JFET drive"
    q1 = c.part("Q1")
    assert isinstance(q1, Jfet) and q1.measured is not None
    assert q1.measured.idss == pytest.approx(0.6e-3)
    rt1 = c.part("TR1")
    assert isinstance(rt1, Trimmer) and rt1.bias_target is not None
    assert rt1.bias_target.node == "Q1.D"
    assert c.wires[0].from_ == (20, 100)
    assert c.probes.in_ == "IN.out"


def test_round_trip_keeps_the_file_as_written(data: dict[str, Any], tmp_path: Path) -> None:
    c = parse_circuit(data)
    out = tmp_path / "sub" / "c.json"
    save_circuit(c, out)
    assert load_circuit(out) == c
    assert json.loads(out.read_text()) == circuit_to_dict(c)
    assert circuit_to_dict(c)["parts"][1]["value"] == "22n"  # values stay as typed
    assert [p.name for p in tmp_path.rglob("*")] == ["sub", "c.json"]  # no temp files left


def test_saved_file_has_no_defaults(data: dict[str, Any]) -> None:
    saved = circuit_to_dict(parse_circuit(data))
    assert saved["schema"] == SCHEMA_VERSION
    assert "template" not in saved
    assert "rot" not in saved["parts"][0]


def _error(data: dict[str, Any]) -> str:
    with pytest.raises(CircuitError) as err:
        parse_circuit(data)
    return str(err.value)


def test_bad_value_names_the_part(data: dict[str, Any]) -> None:
    data["parts"][2]["value"] = "4k7k"
    assert "part R1 value: Couldn't read the value '4k7k'" in _error(data)


def test_zero_resistance_is_rejected(data: dict[str, Any]) -> None:
    data["parts"][2]["value"] = 0
    assert "part R1 value: 0.0 must be greater than zero" in _error(data)


def test_duplicate_refs(data: dict[str, Any]) -> None:
    data["parts"][5]["ref"] = "R1"
    assert "each ref must be unique; repeated: R1" in _error(data)


def test_unknown_field_is_caught(data: dict[str, Any]) -> None:
    data["parts"][2]["valu"] = "10k"
    assert "part R1 valu: Extra inputs are not permitted" in _error(data)


def test_unknown_part_type(data: dict[str, Any]) -> None:
    data["parts"][2]["type"] = "transformer"
    assert "part R1" in _error(data)


def test_pickup_source_needs_values(data: dict[str, Any]) -> None:
    data["parts"][0]["source"] = "pickup"
    assert "needs pickup values" in _error(data)


def test_switch_position_past_last_throw(data: dict[str, Any]) -> None:
    data["parts"].append({"ref": "SW1", "type": "switch", "kind": "rotary-1p3t", "position": 3})
    assert "a 1P3T has 3 positions" in _error(data)


def test_switch_position_names_one_per_position(data: dict[str, Any]) -> None:
    """D-143: names are optional, but one for each of the type's positions."""
    data["parts"].append({"ref": "SW1", "type": "switch", "kind": "spdt", "names": ["Thick"]})
    assert "has 2 positions, so give 2 position names (or none)" in _error(data)
    data["parts"][-1]["names"] = ["Thick", "x" * 25]
    assert "at most 24 characters" in _error(data)
    data["parts"][-1]["names"] = ["Thick", "Thin"]
    assert parse_circuit(data).part("SW1").position_names == ["Thick", "Thin"]  # type: ignore[union-attr]


def test_switch_kind_must_exist(data: dict[str, Any]) -> None:
    data["parts"].append({"ref": "SW1", "type": "switch", "kind": "5pdt"})
    assert "no switch type '5pdt'" in _error(data)


def test_multi_pole_switch_needs_every_pole() -> None:
    """D-143: a DPDT is SW1A and SW1B, one type, position and label."""
    data: dict[str, Any] = {"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": []}
    data["parts"].append({"ref": "SW1A", "type": "switch", "kind": "dpdt", "pole": "a"})
    assert "SW1B isn't in the file" in _error(data)
    data["parts"].append({"ref": "SW1B", "type": "switch", "kind": "dpdt", "pole": "b",
                          "position": 1})  # fmt: skip
    assert "need the same type, position, label and position names" in _error(data)
    data["parts"][-1]["position"] = 0
    parse_circuit(data)
    data["parts"].append({"ref": "SW2", "type": "switch", "kind": "dpdt"})
    assert "each is its own part" in _error(data)


def test_pole_refs_end_in_their_letter() -> None:
    data: dict[str, Any] = {"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": []}
    data["parts"] += [{"ref": "SW1A", "type": "switch", "kind": "dpdt", "pole": "a"},
                      {"ref": "SW1C", "type": "switch", "kind": "dpdt", "pole": "b"}]  # fmt: skip
    assert "Pole B of a switch is SW, a number and B, like SW1B." in _error(data)


def test_one_dc_jack() -> None:
    data: dict[str, Any] = {"schema": SCHEMA_VERSION, "id": "x", "name": "x",
                            "parts": [{"ref": "DC", "type": "dcjack"}] * 2}  # fmt: skip
    assert "A circuit has one DC jack (DC)." in _error(data)
    data["parts"] = [{"ref": "J1", "type": "dcjack"}]
    assert "The DC jack is always DC." in _error(data)


def test_unicode_micro_value(data: dict[str, Any]) -> None:
    data["parts"][6]["value"] = "1µ"
    assert circuit_to_dict(parse_circuit(data))["parts"][6]["value"] == "1µ"


def test_empty_circuit_is_valid() -> None:
    c = parse_circuit({"schema": 1, "id": "empty", "name": "Empty", "parts": []})
    assert c.parts == []


def test_unreadable_files(tmp_path: Path) -> None:
    with pytest.raises(CircuitError, match="Couldn't read"):
        load_circuit(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{ nope")
    with pytest.raises(CircuitError, match="isn't valid JSON"):
        load_circuit(bad)
    bad.write_text("[1, 2]")
    with pytest.raises(CircuitError, match="expected a JSON object"):
        load_circuit(bad)


def test_newer_schema_is_refused(data: dict[str, Any]) -> None:
    data["schema"] = SCHEMA_VERSION + 1
    assert "newer Solum Builder" in _error(data)


def test_missing_schema_is_refused(data: dict[str, Any]) -> None:
    del data["schema"]
    assert 'no "schema" version' in _error(data)


def test_migrations_run_in_order(data: dict[str, Any]) -> None:
    """With a pretend v2 and v3, a v1 file is upgraded step by step."""
    steps = {
        1: lambda d: {**d, "tags": []},
        2: lambda d: {**d, "tags": [*d["tags"], "v3"]},
    }
    data["schema"] = 1
    original = copy.deepcopy(data)
    upgraded = migrate(data, steps, current=3)
    assert upgraded["schema"] == 3
    assert upgraded["tags"] == ["v3"]
    assert data == original  # input untouched


def test_missing_migration_step(data: dict[str, Any]) -> None:
    data["schema"] = 1
    with pytest.raises(MigrationError, match="can't be upgraded"):
        migrate(data, {}, current=2)


def test_committed_json_schema_is_current(repo: Path) -> None:
    committed = (repo / "docs" / "circuit.schema.json").read_text()
    assert committed == json_schema_text(), "Run `make schema` and commit the result."


def test_with_part_changes_one_part_and_validates(data: dict[str, Any]) -> None:
    c = parse_circuit(data)
    turned = c.with_part("TR1", rotation=0.25)
    rt1 = turned.part("TR1")
    assert isinstance(rt1, Trimmer) and rt1.rotation == pytest.approx(0.25)
    assert c.part("TR1") != rt1  # the original is untouched
    assert turned.part("R1") == c.part("R1")
    swapped = c.with_part("R1", value="4k7")
    assert circuit_to_dict(swapped)["parts"][2]["value"] == "4k7"
    with pytest.raises(ValueError, match="less than or equal to 1"):
        c.with_part("TR1", rotation=1.5)
    with pytest.raises(KeyError):
        c.with_part("R99", value="1k")


def test_schema_v1_file_loads_as_current(repo: Path) -> None:
    """v2 added `tags`, v3 power mode `custom`, v4 the provenance map, v5 the version tag
    (and dropped provenance), v6 text blocks (and dropped the power mode); a v1 file
    loads unchanged and saves as v6 at v1.0."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v1.json")
    assert c.schema_ == SCHEMA_VERSION == 30
    assert c.tags == [] and c.texts == []
    assert [p.ref for p in c.parts] == ["R1", "R2"]
    assert circuit_to_dict(c)["schema"] == 30
    assert (str(c.version), c.final) == ("v1.0", False)


def test_schema_v2_file_loads_as_current(repo: Path) -> None:
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v2.json")
    assert c.schema_ == SCHEMA_VERSION
    assert c.tags == ["divider"]
    assert c.power.rails == {"V+": pytest.approx(9.0)}


@pytest.mark.parametrize("old", ["schema-v3.json", "schema-v4.json"])
def test_provenance_is_dropped_and_the_version_starts_at_1_0(repo: Path, old: str) -> None:
    """v5: a pasted block is a plain copy; the record of where it came from goes (D-075)."""
    c = load_circuit(repo / "tests/fixtures/circuits/old" / old)
    assert c.schema_ == SCHEMA_VERSION
    data = circuit_to_dict(c)
    assert "provenance" not in data
    assert data["version"] == {"major": 1, "minor": 0}
    assert list(data)[:4] == ["schema", "id", "name", "version"]


def test_version_tag(data: dict[str, Any]) -> None:
    data["version"] = {"major": 2, "minor": 12}
    data["final"] = True
    c = parse_circuit(data)
    assert (str(c.version), c.final) == ("v2.12", True)
    assert circuit_to_dict(c)["final"] is True
    data["version"] = {"major": 0, "minor": 1}
    assert "greater than or equal to 1" in _error(data)
    data["version"] = {"major": 1, "minor": -1}
    assert "greater than or equal to 0" in _error(data)
    data["version"] = {"major": 1}
    assert str(parse_circuit(data).version) == "v1.0"


def test_ports_must_name_a_net_on_the_sheet(data: dict[str, Any]) -> None:
    data["labels"] = [{"net": "IN", "pos": [0, 0]}]
    data["power"] = {"rails": {"V+": 9.0}}
    data["ports"] = {"in": "IN", "supply": "V+"}
    assert parse_circuit(data).ports == {"in": "IN", "supply": "V+"}
    data["ports"]["out"] = "OUT"
    assert "port 'out' is on net 'OUT', but no label on the sheet is called 'OUT'" in _error(data)


def test_a_v5_own_supply_becomes_the_ideal_one(repo: Path) -> None:
    """v6 (D-091): a DC source driving V+ or V- from GND goes and sets the rail (12 V on
    V+; 9 V drawn GND → V- is -9 V), its note with it; the bias battery V2 stays."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v5-own-supply.json")
    assert c.power.rails == {"V+": pytest.approx(12.0), "V-": pytest.approx(-9.0)}
    assert [p.ref for p in c.parts] == ["R1", "V2", "R2"]
    assert [(p.ref, p.note) for p in c.parts if p.note] == [("V2", "a bias battery")]
    nets = connect(c)
    assert (nets.net_of("R1", "1"), nets.net_of("R1", "2")) == ("V+", "V-")
    assert "mode" not in circuit_to_dict(c)["power"]


def test_a_v5_supply_through_a_series_resistor_keeps_the_resistor(repo: Path) -> None:
    """The old charge pump: V1 (16 V) → R1 (50 Ω) → V+. V1 goes, V+ is 16 V, and a V+
    label takes V1's + pin, so R1 and C1 are still drawn where they were."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v5-series.json")
    assert c.power.rails == {"V+": pytest.approx(16.0)}
    assert [p.ref for p in c.parts] == ["R1", "C1"]
    assert {"net": "V+", "pos": [0, 0]} in [
        lb.model_dump(mode="json", exclude_defaults=True) for lb in c.labels
    ]
    assert connect(c).net_of("R1", "1") == "V+"


def test_a_v6_file_has_no_power_mode(data: dict[str, Any]) -> None:
    data["schema"] = SCHEMA_VERSION
    data["power"] = {"mode": "ideal", "rails": {"V+": 9.0}}
    assert "power.mode: Extra inputs are not permitted" in _error(data)


def test_text_blocks_round_trip(data: dict[str, Any]) -> None:
    data["texts"] = [{"text": "Bias Q1 to 4.5 V\nwith TR1", "pos": [40, -80]}]
    c = parse_circuit(data)
    assert c.texts[0].text == "Bias Q1 to 4.5 V\nwith TR1" and c.texts[0].pos == (40, -80)
    assert circuit_to_dict(c)["texts"] == data["texts"]
    data["texts"] = [{"title": "Bias", "pos": [0, 0]}]  # a title alone will do
    assert parse_circuit(data).texts[0].text == ""
    data["texts"] = [{"title": " ", "text": "", "pos": [0, 0]}]
    assert "needs a title or some text" in _error(data)
    data["texts"] = [{"title": "x" * 101, "text": "a", "pos": [0, 0]}]
    assert "at most 100 characters" in _error(data)
    data["texts"] = [{"text": "x" * 2001, "pos": [0, 0]}]
    assert "at most 2000 characters" in _error(data)


@pytest.mark.parametrize(
    ("rails", "message"),
    [
        (
            {"VBAT": 9.0},
            "power: supply rails are V+ and V- only, but this file has one called 'VBAT'. "
            "Rename it to V+ (positive) or V- (negative) in the file, and its labels with it.",
        ),
        (
            {"GND": 1.0},
            "power: supply rails are V+ and V- only, but this file has one called 'GND'.",
        ),
        ({"V+": -9.0}, "power: V+ is the positive supply, so it can't be -9 V."),
        ({"V-": 9.0}, "power: V- is the negative supply, so it can't be 9 V."),
        ({"V-": 0.0}, "power: V- is the negative supply, so it can't be 0 V."),
    ],
)
def test_rails_are_v_plus_and_v_minus_only(
    data: dict[str, Any], rails: dict[str, float], message: str
) -> None:
    """D-071: a file naming any other rail is refused with a plain message."""
    data["power"] = {"rails": rails}
    assert message in _error(data)
    data["power"] = {"rails": {"V+": 9.0, "V-": -9.0}}
    assert parse_circuit(data).power.rails == {"V+": 9.0, "V-": -9.0}


def test_tags_round_trip(data: dict[str, Any]) -> None:
    data["tags"] = ["fuzz", "germanium"]
    assert circuit_to_dict(parse_circuit(data))["tags"] == ["fuzz", "germanium"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("TS808 (mine)", "ts808-mine"), ("  Big Muff π  ", "big-muff"), ("!!!", "circuit")],
)
def test_id_from_name(name: str, expected: str) -> None:
    assert id_from_name(name) == expected


def test_schema_v7_pickup_keeps_its_sound(repo: Path) -> None:
    """v8 split the guitar's lead from its coil (D-096); a v7 pickup's one capacitance
    stays the coil's, with no cable and no volume pot, so it simulates as before."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v7.json")
    assert c.schema_ == SCHEMA_VERSION
    guitar = c.part("IN")
    assert isinstance(guitar, Guitar) and guitar.pickup is not None
    assert (guitar.pickup.c, guitar.pickup.kind) == ("500p", None)
    assert (guitar.cable, guitar.volume) == (0.0, None)


def test_schema_v8_labels_come_upright_and_a_turn_round_trips(repo: Path) -> None:
    """v9 let a supply's symbol be turned (D-117): a v8 file's labels load unturned, and a
    turn is saved (an unturned label saves without one, as before)."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v8.json")
    assert c.schema_ == SCHEMA_VERSION
    assert [(lb.net, lb.rot) for lb in c.labels] == [("GND", 0), ("V+", 0)]
    data = circuit_to_dict(c)
    assert "rot" not in data["labels"][0]
    data["labels"][1]["rot"] = 180
    assert parse_circuit(data).labels[1].rot == 180
    assert circuit_to_dict(parse_circuit(data))["labels"][1]["rot"] == 180


def test_schema_v6_file_loads_unchanged(repo: Path) -> None:
    """v7 only added the charge-pump part (D-093): a v6 file keeps everything."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v6.json")
    assert c.schema_ == SCHEMA_VERSION
    assert [p.ref for p in c.parts] == ["R1"] and c.power.rails == {"V+": 9.0}
    assert c.texts[0].text == "Saved before charge pumps."


def test_schema_v9_transistors_use_their_models_gain(repo: Path) -> None:
    """v10 let a transistor carry its measured hFE (D-130): a v9 one has none, and a
    measured one round-trips."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v9.json")
    assert c.schema_ == SCHEMA_VERSION
    q1 = c.part("Q1")
    assert isinstance(q1, Bjt) and q1.measured is None
    data = circuit_to_dict(c)
    assert "measured" not in data["parts"][0]
    data["parts"][0]["measured"] = {"hfe": 92}
    assert circuit_to_dict(parse_circuit(data))["parts"][0]["measured"] == {"hfe": 92}
    with pytest.raises(ValueError, match="hfe"):
        parse_circuit({**data, "parts": [{**data["parts"][0], "measured": {"hfe": 0}}]})


def test_schema_v10_measured_transistors_leak_as_their_model(repo: Path) -> None:
    """v11 added `measured.leakage` (D-130): a v10 measured part has none (its model's
    own), and a leakage round-trips; more than 10 mA is refused."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v10.json")
    assert c.schema_ == SCHEMA_VERSION
    q1 = c.part("Q1")
    assert isinstance(q1, Bjt) and q1.measured is not None
    assert (q1.measured.hfe, q1.measured.leakage) == (92, None)
    data = circuit_to_dict(c)
    assert data["parts"][0]["measured"] == {"hfe": 92}
    data["parts"][0]["measured"]["leakage"] = 1.5e-4
    assert circuit_to_dict(parse_circuit(data))["parts"][0]["measured"]["leakage"] == 1.5e-4
    with pytest.raises(ValueError, match="leakage"):
        data["parts"][0]["measured"]["leakage"] = 0.5
        parse_circuit(data)


def test_refs_fit_their_part_type() -> None:
    """D-141: a ref is its type's prefix and a number; a chip IC or U; IN and OUT fixed;
    one guitar input and one amp."""

    def part(ref: str, kind: str, **fields: Any) -> dict[str, Any]:
        return {"ref": ref, "type": kind, **fields}

    good = [
        part("R1", "resistor", value="1k"),
        part("RPD1", "resistor", value="2M2"),  # Aion's names, numbered (D-232)
        part("LEDR1", "resistor", value="4k7"),
        part("LEDR2", "resistor", value="4k7"),
        part("VR2", "pot", value="100k"),
        part("TR1", "trimmer", value="10k"),
        part("SW1", "switch"),
        part("LED3", "led", model="RED"),
        part("Z1", "diode", model="1N4742A"),  # a zener's usual ref (D-221)
        part("U4", "chargepump", model="TC1044S"),
        part("IC1A", "opamp", model="TL072", half="a"),
        part("IC1B", "opamp", model="TL072", half="b"),
        part("IC1C", "powerunit", model="TL072"),  # its power unit (v19, D-179)
        part("IN", "guitar"),
        part("OUT", "amp"),
    ]
    parse_circuit({"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": good})
    for bad, says in [
        (part("FUZZ", "pot", value="1k"), "A pot's ref is VR and a number, like VR1. Put its name"),
        (part("RT1", "trimmer", value="10k"), "A trimmer's ref is TR and a number, like TR1."),
        (part("L1", "led", model="RED"), "An LED's ref is LED or D and a number, like LED1."),
        (part("Q1", "diode", model="1N4148"), "A diode's ref is D or Z and a number"),
        (part("R0", "resistor", value="1k"), "A resistor's ref is R, RPD or LEDR and a number"),
        (part("LEDR", "resistor", value="1k"), "A resistor's ref is R, RPD or LEDR and a number"),
        (part("X1", "opamp", model="TL071"), "An op-amp's ref is IC or U and a number, like IC1."),
        (part("AMP", "amp"), "The amp is always OUT."),
    ]:
        with pytest.raises(CircuitError, match=re.escape(says)):
            parse_circuit({"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": [bad]})
    two = [part("IN", "guitar"), part("IN", "guitar")]
    with pytest.raises(CircuitError, match=re.escape("A circuit has one guitar input (IN)")):
        parse_circuit({"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": two})


def test_v12_refs_are_renamed_to_fit() -> None:
    """D-141: P1 → VR1 (number kept), FUZZ → the next pot number with Fuzz as its label,
    RB → after the highest R, IC1a → IC1A, AMP → OUT; notes, probes and targets follow."""
    v12 = {
        "schema": 12, "id": "x", "name": "x",
        "parts": [
            {"ref": "R7", "type": "resistor", "value": "1k"},
            {"ref": "RB", "type": "resistor", "value": "1k"},
            {"ref": "P1", "type": "pot", "value": "100k", "label": "Gain"},
            {"ref": "FUZZ", "type": "pot", "value": "100k"},
            {"ref": "RT1", "type": "trimmer", "value": "10k",
             "bias_target": {"node": "Q1.C", "volts": 4.5}},
            {"ref": "Q1", "type": "bjt", "model": "2N5089"},
            {"ref": "L2", "type": "led", "model": "RED"},
            {"ref": "S1", "type": "switch"},
            {"ref": "IC1a", "type": "opamp", "model": "TL072", "half": "a"},
            {"ref": "IC1b", "type": "opamp", "model": "TL072", "half": "b"},
            {"ref": "AMP", "type": "amp"},
        ],
        "probes": {"out": "IC1a.out"},
        "notes": {"part:FUZZ": "the fuzz", "part:AMP": "the amp"},
    }  # fmt: skip
    c = parse_circuit(v12)
    assert [p.ref for p in c.parts] == [
        "R7", "R8", "VR1", "VR2", "TR1", "Q1", "LED2", "SW1", "IC1A", "IC1B", "OUT", "IC1C"
    ]  # fmt: skip
    assert [getattr(p, "label", None) for p in c.parts[2:4]] == ["Gain", "Fuzz"]
    trimmer = c.part("TR1")
    assert isinstance(trimmer, Trimmer) and trimmer.bias_target is not None
    assert trimmer.bias_target.node == "Q1.C"
    assert c.probes.out == "IC1A.out"
    assert [(p.ref, p.note) for p in c.parts if p.note] == [("VR2", "the fuzz"), ("OUT", "the amp")]


def test_schema_v15_ring_label_becomes_ground(repo: Path) -> None:
    """v16 grounds the battery's - always (D-164): v15's IN_ring label is a GND label,
    its port gone, and its net is ground."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v15.json")
    assert c.schema_ == SCHEMA_VERSION
    assert "IN_ring" not in c.ports and "IN_ring" not in connect(c).members
    assert connect(c).net_of("BAT1", "-") == "GND"
    assert circuit_to_dict(c)["labels"][0] == {"net": "GND", "pos": [-100, 80]}


def test_schema_v16_ac128_cards_become_one_measured_ac128(repo: Path) -> None:
    """v17 has one AC128 (D-170): a part on either old card keeps its own measured gain and
    leakage, and takes what the old card read on the tester where it had none."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v16.json")
    parts = {p["ref"]: p for p in circuit_to_dict(c)["parts"]}
    assert {r: parts[r]["model"] for r in parts} == {
        "Q1": "AC128", "Q2": "AC128", "Q3": "AC128", "Q4": "2N3906"
    }  # fmt: skip
    assert parts["Q1"]["measured"] == {"hfe": 79.4, "leakage": 9.8e-6}
    assert parts["Q2"]["measured"] == {"hfe": 130, "leakage": 1.4e-5}
    assert parts["Q3"]["measured"] == {"hfe": 65, "leakage": 0.0002}
    assert "measured" not in parts["Q4"]


def test_values_are_kept_in_standard_form(data: dict[str, Any]) -> None:
    """The user (2026-11-02): 100u or 100uf showed as typed; the form and the drawing
    show the standard form (D-164). Numbers stay numbers."""
    cap = next(i for i, p in enumerate(data["parts"]) if p["type"] == "capacitor")
    for typed, kept in (("100uf", "100µ"), ("100u", "100µ"), ("0.047u", "47n"), ("22nF", "22n")):
        data["parts"][cap]["value"] = typed
        assert circuit_to_dict(parse_circuit(data))["parts"][cap]["value"] == kept
    data["parts"][2]["value"] = "4.7 kΩ"
    assert circuit_to_dict(parse_circuit(data))["parts"][2]["value"] == "4k7"
    data["parts"][2]["value"] = 4700.0
    assert circuit_to_dict(parse_circuit(data))["parts"][2]["value"] == 4700.0


@pytest.mark.parametrize(
    ("index", "value", "message"),
    [
        (2, "4k7F", "is in farads (F), but this value is in ohms (Ω)"),
        (2, "10f", "outside 1 mΩ to 1 TΩ"),
        (2, "4k7Ω", None),
        (2, "4.7 kohm", None),
    ],
)
def test_a_resistor_value_is_in_ohms_and_in_range(
    data: dict[str, Any], index: int, value: str, message: str | None
) -> None:
    """The user (2026-11-02): a value box took any letter (D-164)."""
    data["parts"][index]["value"] = value
    if message is None:
        parse_circuit(data)
    else:
        assert message in _error(data)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("10F", "is 10 F, outside 100 fF to 1 F. Did you mean something like 22n, 100p or 10µ?"),
        ("10f", "is 10 fF, outside 100 fF to 1 F"),
        ("4k7F", "is 4.7 kF, outside 100 fF to 1 F"),
        ("100kΩ", "is in ohms (Ω), but this value is in farads (F)"),
        ("10u", None),
        ("22nF", None),
        ("1p", None),
    ],
)
def test_a_capacitor_value_is_in_farads_and_in_range(
    data: dict[str, Any], value: str, message: str | None
) -> None:
    cap = next(i for i, p in enumerate(data["parts"]) if p["type"] == "capacitor")
    data["parts"][cap]["value"] = value
    if message is None:
        parse_circuit(data)
    else:
        assert message in _error(data)


def test_refs_sort_as_a_parts_list_does() -> None:
    refs = ["C10", "C2", "IC1B", "IC1A", "VR1", "C1", "IN", "R3", "LED1", "SW1B", "SW1A"]
    assert sorted(refs, key=ref_key) == [
        "C1", "C2", "C10", "IC1A", "IC1B", "IN", "LED1", "R3", "SW1A", "SW1B", "VR1",
    ]  # fmt: skip


def test_a_v22_file_loads_as_v23_with_no_enclosure(repo: Path) -> None:
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v22.json")
    assert c.schema_ == SCHEMA_VERSION and c.enclosure is None


def test_a_v26_file_loads_as_v27_unchanged(repo: Path) -> None:
    """v27 only adds the regulator part (D-227)."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v26.json")
    assert c.schema_ == SCHEMA_VERSION and [p.ref for p in c.parts] == ["U1", "C1", "C2"]


def test_a_v28_file_loads_as_v29_with_nothing_off_by_design(repo: Path) -> None:
    """v29 only adds a transistor's `off_by_design` (D-238)."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v28.json")
    assert c.schema_ == SCHEMA_VERSION and c.parts[0].off_by_design is False  # type: ignore[union-attr]


def test_a_v29_files_notes_move_to_their_part_net_or_the_general_list(repo: Path) -> None:
    """v30 (9d4): `part:REF` goes on the part (a dual pot's name on gang A), `net:NAME`
    into `net_notes`, and a note naming no part becomes a general note, so none is lost."""
    c = load_circuit(repo / "tests/fixtures/circuits/old/schema-v29.json")
    assert c.schema_ == SCHEMA_VERSION
    assert {p.ref: p.note for p in c.parts} == {"R1": "sets the gain", "VR1A": "the volume",
                                                "VR1B": "", "C1": ""}  # fmt: skip
    assert c.net_notes == {"VREF": "half the supply", "Q1.D": "the drain"}
    assert [(n.title, n.text) for n in c.notes] == [("part:R9", "a part since deleted")]
    saved = circuit_to_dict(c)
    assert "note" not in saved["parts"][3]  # an empty note isn't written


def test_a_general_note_needs_a_title_or_text() -> None:
    from pydantic import ValidationError

    from solum.circuit.schema import Note

    assert Note(title="Build", text="").title == "Build"
    with pytest.raises(ValidationError):
        Note(title="  ", text="")


def test_an_enclosure_is_a_standard_size_or_custom_with_its_mm() -> None:
    from pydantic import ValidationError

    from solum.circuit.enclosures import size_of
    from solum.circuit.schema import Enclosure

    assert Enclosure(size="125B").size == "125B"
    assert size_of("125B") is not None and size_of("125B").text == "122 \u00d7 66 \u00d7 39.5 mm"  # type: ignore[union-attr]
    assert Enclosure(size="custom", length=100, width=50, height=30).length == 100
    for bad in ({"size": "1590Z"}, {"size": "custom", "length": 100},
                {"size": "1590B", "length": 100, "width": 50, "height": 30}):  # fmt: skip
        with pytest.raises(ValidationError):
            Enclosure(**bad)
