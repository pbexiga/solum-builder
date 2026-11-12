"""What the viewer gets: pin positions and nets, anchors, rails, probes, controls."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect, on_segment
from solum.circuit.io import load_circuit, parse_circuit
from solum.circuit.parts import pin_positions
from solum.circuit.refs import PREFIXES
from solum.circuit.schema import SCHEMA_VERSION
from solum.models import load_models
from solum.view import (
    circuit_view,
    controls,
    junctions,
    label_sides,
    part_text,
    probe_nets,
    rail_nets,
    switch_draw,
    wire_nets,
)

Builder = Callable[..., CircuitBuilder]
REPO = Path(__file__).parents[2]


def stage(circuit: Builder) -> CircuitBuilder:
    return (
        circuit("stage")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "p", value="100n")
        .part("U1", "opamp", "p", "n", "o", model="TL072")
        .part("VR1", "pot", "n", "n", "o", value="100k", taper="A", rotation=0.3, label="Gain")
        .part("SW1", "switch", pins={"C": "o", "1": "x"}, kind="rotary-1p3t", label="Clip")
        .part("OUT", "amp", "o")
        .part("R1", "resistor", "V+", "p", value="1M")
    )


def test_pins_carry_positions_and_nets(circuit: Builder) -> None:
    c = stage(circuit).build()
    view = circuit_view(c)
    vr1 = next(p for p in view["parts"] if p["ref"] == "VR1")
    positions = pin_positions(c.part("VR1"))
    assert {p["name"]: tuple(p["pos"]) for p in vr1["pins"]} == positions
    assert {p["name"]: p["net"] for p in vr1["pins"]} == {"1": "n", "2": "n", "3": "o"}
    assert vr1["text"] == "100k A" and vr1["label"] == "Gain"


def test_unconnected_comp_pins_are_not_drawn(circuit: Builder) -> None:
    view = circuit_view(stage(circuit).build())
    u1 = next(p for p in view["parts"] if p["ref"] == "U1")
    assert [p["name"] for p in u1["pins"]] == ["+", "-", "out", "V+", "V-"]


def test_connected_comp_pins_are_drawn(circuit: Builder) -> None:
    c = (
        circuit("lm308")
        .part("U1", "opamp", "p", "n", "o", model="LM308", pins={"comp1": "a", "comp2": "b"})
        .part("C1", "capacitor", "a", "b", value="30p")
        .build()
    )
    u1 = next(p for p in circuit_view(c)["parts"] if p["ref"] == "U1")
    assert {p["name"] for p in u1["pins"]} >= {"comp1", "comp2"}


def test_nets_rails_and_anchors(circuit: Builder) -> None:
    view = circuit_view(stage(circuit).build())
    assert view["nets"]["V+"]["rail"]
    assert not view["nets"]["o"]["rail"]
    # every label of a net is an anchor for its DC readout
    assert len(view["nets"]["o"]["anchors"]) == 4  # U1.out, VR1.3, SW1.C, OUT.in


def test_unlabelled_net_is_anchored_at_its_first_pin() -> None:
    c = load_circuit(REPO / "tests" / "fixtures" / "circuits" / "jfet-drive.json")
    view = circuit_view(c)
    nets = connect(c)
    unlabelled = [n for n in nets.members if n not in {lb.net for lb in c.labels}]
    assert unlabelled
    for name in unlabelled:
        ref, pin = nets.members[name][0]
        assert view["nets"][name]["anchors"] == [list(pin_positions(c.part(ref))[pin])]


def test_probes_fall_back_to_guitar_and_amp(circuit: Builder) -> None:
    c = stage(circuit).build()
    probes = probe_nets(c, connect(c))
    assert (probes.input, probes.output) == ("in", "o")
    named = stage(circuit).probe("in", "VR1.1").build()
    assert probe_nets(named, connect(named)).output == "n"


def test_probe_without_amp_or_guitar_is_none(circuit: Builder) -> None:
    c = circuit().part("R1", "resistor", "a", "0", value="1k").build()
    probes = probe_nets(c, connect(c))
    assert (probes.input, probes.output) == (None, None)


def test_the_guitar_volume_is_listed_with_the_knobs(circuit: Builder) -> None:
    """D-096: a guitar with a volume pot has a knob, with a pickup or buffered (D-134);
    without a pot, none."""
    pickup = {"r": "6k38", "l": "2.55", "c": "151p"}
    c = circuit().part("IN", "guitar", "in", source="pickup", pickup=pickup, volume="500k")
    assert controls(c.build()) == [
        {"ref": "IN", "kind": "pot", "label": "Guitar volume", "value": "500k", "taper": "A",
         "rotation": 1.0},
    ]  # fmt: skip
    buffered = circuit().part("IN", "guitar", "in", volume="500k").build()
    assert [k["label"] for k in controls(buffered)] == ["Guitar volume"]
    assert controls(circuit().part("IN", "guitar", "in").build()) == []


def test_controls_for_pots_and_switches(circuit: Builder) -> None:
    assert controls(stage(circuit).build()) == [
        {"ref": "VR1", "kind": "pot", "label": "Gain", "value": "100k", "taper": "A",
         "rotation": 0.3},
        {"ref": "SW1", "kind": "switch", "label": "Clip", "refs": ["SW1"], "position": 0,
         "positions": ["1", "2", "3"], "contacts": ["1: C\u20131", "2: C\u20132", "3: C\u20133"]},
    ]  # fmt: skip


def test_a_multi_pole_switch_is_one_control(circuit: Builder) -> None:
    """D-143: SW1A and SW1B turn together, under SW1."""
    c = (
        circuit()
        .part("SW1A", "switch", kind="footswitch", pole="a", label="Bypass")
        .part("SW1B", "switch", kind="footswitch", pole="b", label="Bypass")
        .part("SW1C", "switch", kind="footswitch", pole="c", label="Bypass")
        .build()
    )
    assert controls(c) == [
        {"ref": "SW1", "kind": "switch", "label": "Bypass", "refs": ["SW1A", "SW1B", "SW1C"],
         "position": 0, "positions": ["On", "Bypassed"],
         "contacts": ["On: A2\u2013A1, B2\u2013B1, C2\u2013C1",
                      "Bypassed: A2\u2013A3, B2\u2013B3, C2\u2013C3"]},
    ]  # fmt: skip


def test_named_positions_show_on_the_knob_and_the_drawing(circuit: Builder) -> None:
    """D-143: your names on the buttons (an empty one keeps the type's), what each
    position joins in the tooltip, and the names on the drawing."""
    names = ["Vintage", "", "Modern"]
    c = circuit().part("SW1", "switch", kind="spdt-on-off-on", label="Mode", names=names).build()
    (knob,) = controls(c)
    assert knob["positions"] == ["Vintage", "Off", "Modern"]
    assert knob["contacts"] == ["1: 2\u20131", "Off: open", "2: 2\u20133"]
    assert switch_draw(c.part("SW1"))["names"] == ["Vintage", "Off", "Modern"]  # type: ignore[arg-type]
    plain = circuit().part("SW1", "switch").build()
    assert switch_draw(plain.part("SW1"))["names"] is None  # type: ignore[arg-type]


def test_a_battery_makes_the_dc_jack_a_power_switch(circuit: Builder) -> None:
    """D-143: with a battery, Knobs picks the supply: the DC jack plugged in or not."""
    jack = circuit().part("DC", "dcjack")
    assert controls(jack.build()) == []
    c = jack.part("BAT1", "battery").build()
    assert controls(c) == [
        {
            "ref": "DC",
            "kind": "switch",
            "label": "Power",
            "refs": ["DC"],
            "position": 0,
            "positions": ["DC jack", "Battery"],
            "plug": True,
        },
    ]


def test_rail_nets_include_opamp_supplies(circuit: Builder) -> None:
    c = (
        circuit()
        .rail("V+", 9.0)
        .part("U1", "opamp", "p", "n", "o", model="TL072", supply=("V+F", "GND"))
        .pump("U2", "V+", double="V18", boost=True)
        .build()
    )
    # a pump's output, and its own nets (D-226): CAP+, CAP- and the diodes' junction
    assert rail_nets(c, connect(c)) == {"V+", "V+F", "V18", "GND", "U2_cp", "U2_cm", "U2_j"}
    view = circuit_view(c)
    assert view["nets"]["V18"]["rail"]
    # boost is drawn, pin 1 on V+, not written (D-234)
    assert next(p for p in view["parts"] if p["ref"] == "U2")["text"] == "TC1044S"


@pytest.mark.parametrize(
    ("data", "text"),
    [
        ({"type": "resistor", "value": "4k7"}, "4k7"),
        ({"type": "bjt", "model": "2N5089"}, "2N5089"),
        ({"type": "pot", "value": "500k", "taper": "W"}, "500k W"),
        ({"type": "switch", "kind": "spst"}, "SPST"),
        ({"type": "switch", "kind": "rotary-1p4t"}, "1P4T"),
        ({"type": "battery", "volts": 7.4, "state": "half"}, "7.4 V half"),
        ({"type": "dcjack", "plugged": False}, "unplugged"),
        ({"type": "guitar"}, "Buffered"),
        ({"type": "amp"}, "amp 1M"),
        ({"type": "vsource", "value": 9}, "9 V"),
        ({"type": "vsource", "value": "4.5"}, "4.5 V"),
    ],
)
def test_part_text(data: dict[str, object], text: str) -> None:
    ref = {"guitar": "IN", "amp": "OUT", "dcjack": "DC"}.get(str(data["type"]))
    ref = ref or PREFIXES[str(data["type"])][0] + "1"
    c = parse_circuit({"schema": SCHEMA_VERSION, "id": "t", "name": "t",
                       "parts": [{"ref": ref, **data}]})  # fmt: skip
    assert part_text(c.parts[0]) == text


def test_a_guitars_text_names_its_pickup() -> None:
    """D-137: the guide's name for a measured pickup, "Your pickup" for your own values."""
    coil = {"r": "6k38", "l": "2.55", "c": "151p"}
    parts = [
        {"ref": "IN", "type": "guitar", "source": "pickup", "pickup": {**coil, "kind": "strat"}},
        {"ref": "IN", "type": "guitar", "source": "pickup", "pickup": coil},
    ]
    strat, own = (parse_circuit({"schema": 1, "id": "t", "name": "t", "parts": [p]}) for p in parts)
    names = {"strat": "Strat single coil"}
    assert [part_text(c.parts[0], names) for c in (strat, own)] == [
        "Strat single coil",
        "Your pickup",
    ]
    assert part_text(strat.parts[0]) == "pickup"  # no guide given
    assert circuit_view(strat, pickups=names)["parts"][0]["text"] == "Strat single coil"


def test_every_starter_view_is_json(repo: Path) -> None:
    for path in sorted((repo / "library" / "starters").glob("*.json")):
        view = circuit_view(load_circuit(path))
        json.dumps(view)
        assert view["probes"] == {"in": "in", "out": "out"}
        assert view["circuit"]["id"] == path.stem


def test_no_library_circuit_has_a_zero_length_wire_or_a_label_on_nothing(repo: Path) -> None:
    """Bugs: klon-centaur-aion-built had a wire from a pin to itself, and klon-bypass-v1 two
    labels left where its guitar and amp were cut away; taking the whole sheet as a block
    dropped them (the editor keeps neither)."""
    for folder in ("starters", "blocks"):
        for path in sorted((repo / "library" / folder).glob("*.json")):
            c = load_circuit(path)
            assert not [w for w in c.wires if w.from_ == w.to], path.name
            pins = {pt for p in c.parts for pt in pin_positions(p).values()}
            on_wire = [
                lb for lb in c.labels if any(on_segment(lb.pos, w.from_, w.to) for w in c.wires)
            ]
            loose = [lb.net for lb in c.labels if lb.pos not in pins and lb not in on_wire]
            assert not loose, path.name


def test_every_starter_text_box_sits_next_to_its_circuit_and_clear_of_it(repo: Path) -> None:
    """A starter opens fitted to everything on its sheet: a Credit box 690 below the Halo
    Big Muff zoomed the view right out (9d4). Each box is within 100 of the circuit and
    covers no pin, label or wire (its size estimated as the editor does, D-091)."""
    for path in sorted((repo / "library" / "starters").glob("*.json")):
        c = load_circuit(path)
        pts = [pt for p in c.parts for pt in pin_positions(p).values()]
        pts += [lb.pos for lb in c.labels] + [pt for w in c.wires for pt in (w.from_, w.to)]
        x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
        x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
        for t in c.texts:
            lines = ([t.title] if t.title else []) + (t.text or "").split("\n")
            tx, ty = t.pos
            box = (tx - 3, ty - 3, tx + 6.4 * max(map(len, lines)) + 3, ty + 13 * len(lines) + 2)
            gap = max(x0 - tx, tx - x1, y0 - ty, ty - y1, 0)
            assert gap <= 100, f"{path.name}: {t.title} is {gap} from the circuit"
            covered = [w for w in c.wires if _crosses(box, w.from_, w.to)]
            covered += [p for p in pts if _crosses(box, p, p)]
            assert not covered, f"{path.name}: {t.title} covers {covered[:3]}"


def _crosses(box: tuple[float, ...], a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether the straight segment a-b (sheet wires run across or down) meets the box."""
    return (
        min(a[0], b[0]) <= box[2]
        and max(a[0], b[0]) >= box[0]
        and min(a[1], b[1]) <= box[3]
        and max(a[1], b[1]) >= box[1]
    )


def wired() -> dict[str, object]:
    """R1 and R2 in series on a wire, with a wire tee'd off the middle to R3 (T-junction),
    and one wire that touches nothing."""
    return {
        "schema": 1, "id": "wired", "name": "wired",
        "parts": [
            {"ref": "R1", "type": "resistor", "value": "1k", "pos": [100, 100]},  # pins 80, 120
            {"ref": "R2", "type": "resistor", "value": "1k", "pos": [200, 100]},  # pins 180, 220
            {"ref": "R3", "type": "resistor", "value": "1k", "pos": [150, 180], "rot": 90},
        ],
        "wires": [
            {"from": [120, 100], "to": [180, 100]},  # R1.2 - R2.1, passes (150, 100)
            {"from": [150, 100], "to": [150, 160]},  # tee down to R3.1 (150, 160)
            {"from": [400, 400], "to": [420, 400]},  # floating
        ],
        "labels": [{"net": "IN", "pos": [80, 100]}, {"net": "GND", "pos": [150, 200]}],
    }  # fmt: skip


def test_junction_dot_at_a_tee() -> None:
    assert junctions(parse_circuit(wired())) == [(150, 100)]


def test_wire_nets_follow_pins_and_chains() -> None:
    c = parse_circuit(wired())
    assert wire_nets(c, connect(c)) == ["R1.2", "R1.2", None]


def test_label_sides_point_away_from_the_part() -> None:
    c = parse_circuit(wired())
    # IN sits on R1.1 (left end): text goes left; GND on R3.2 (rotated, bottom): down
    assert label_sides(c) == [(-1, 0), (0, 1)]


def test_a_label_off_a_pin_keeps_its_text_off_the_wires() -> None:
    """D-114: a label on a wire end, not a pin: its text goes above, unless a wire leaves
    upwards, then below, then right, then left."""
    c = parse_circuit(
        {
            "schema": 1, "id": "l", "name": "l", "parts": [],
            "wires": [
                {"from": [0, 0], "to": [0, -50]},  # A at the foot of a wire going up
                {"from": [100, 0], "to": [100, 50]},  # B at the top of a wire going down
                {"from": [200, -50], "to": [200, 50]},  # C on a wire passing through
                {"from": [300, 0], "to": [350, 0]},  # D at the end of a wire going right
                {"from": [300, 0], "to": [300, -40]},  # E: up from D's point too
                {"from": [300, 0], "to": [300, 40]},
            ],
            "labels": [
                {"net": "A", "pos": [0, 0]}, {"net": "B", "pos": [100, 0]},
                {"net": "C", "pos": [200, 0]}, {"net": "D", "pos": [300, 0]},
            ],
        }
    )  # fmt: skip
    assert label_sides(c) == [(0, 1), (0, -1), (1, 0), (-1, 0)]


def test_transistor_polarity_comes_from_the_model(circuit: Builder) -> None:
    models = load_models([REPO / "library" / "models"])
    c = (
        circuit()
        .part("Q1", "bjt", "c", "b", "e", model="AC128")
        .part("Q2", "jfet", "d", "g", "s", model="J201")
        .part("R1", "resistor", "c", "0", value="1k")
        .build()
    )
    parts = {p["ref"]: p for p in circuit_view(c, models)["parts"]}
    assert (parts["Q1"]["polarity"], parts["Q2"]["polarity"]) == ("p", "n")
    assert parts["R1"]["polarity"] is None
    assert circuit_view(c)["parts"][0]["polarity"] is None  # no library given


def test_a_depletion_mosfet_is_drawn_so(circuit: Builder) -> None:
    """D-178: the model says depletion (VTO below 0), the drawing gets a solid channel."""
    models = load_models([REPO / "library" / "models"])
    c = (
        circuit()
        .part("Q1", "mosfet", "d", "0", "s", model="LND150")
        .part("Q2", "mosfet", "d", "g", "0", model="2N7000")
        .build()
    )
    parts = {p["ref"]: p for p in circuit_view(c, models)["parts"]}
    assert parts["Q1"]["draw"] == {"depletion": True}
    assert parts["Q2"]["draw"] == {}
    assert circuit_view(c)["parts"][0]["draw"] == {}  # no library given


def test_a_zener_is_drawn_so(circuit: Builder) -> None:
    """A zener model (its record checks a zener voltage) gets KiCad's bent cathode bar."""
    models = load_models([REPO / "library" / "models"])
    c = (
        circuit()
        .part("Z1", "diode", "a", "0", model="1N4742A")
        .part("D1", "diode", "a", "0", model="1N4148")
        .build()
    )
    parts = {p["ref"]: p for p in circuit_view(c, models)["parts"]}
    assert parts["Z1"]["draw"] == {"zener": True}
    assert parts["D1"]["draw"] == {}


def test_contradictory_wiring_still_draws() -> None:
    """Mid-edit, a wire can join two labels. The view keeps the geometry (so the editor can
    draw and undo) and says what's wrong instead of failing."""
    data = wired()
    data["wires"] = [*data["wires"], {"from": [80, 100], "to": [150, 200]}]  # IN to GND
    view = circuit_view(parse_circuit(data))
    assert view["problem"] is not None and "GND and IN are wired together" in view["problem"]
    assert view["nets"] == {}
    assert [p["ref"] for p in view["parts"]] == ["R1", "R2", "R3"]
    assert view["parts"][0]["pins"] == [
        {"name": "1", "pos": [80, 100], "net": None},
        {"name": "2", "pos": [120, 100], "net": None},
    ]
    assert len(view["wires"]) == 4 and view["junctions"] == [[150, 100]]
    json.dumps(view)


def test_valid_view_has_no_problem() -> None:
    assert circuit_view(parse_circuit(wired()))["problem"] is None


def test_text_blocks_are_drawn_but_not_part_of_the_circuit(circuit: Builder) -> None:
    """D-091: a text block reaches the view as drawn and adds no net."""
    plain = circuit().part("R1", "resistor", "a", "GND", value="1k")
    noted = circuit().part("R1", "resistor", "a", "GND", value="1k")
    noted.extra = {"texts": [{"text": "Bias\nnotes", "pos": [40, -30]}]}
    view = circuit_view(noted.build())
    assert view["texts"] == [{"title": "", "text": "Bias\nnotes", "pos": [40, -30]}]
    assert view["nets"] == circuit_view(plain.build())["nets"]
    assert circuit_view(plain.build())["texts"] == []


def test_a_bias_net_a_big_cap_holds_is_drawn_as_a_supply() -> None:
    """TODO 2026-11-09: a net carrying a bias reference (the TS808's VREF, the Klon's VR,
    the BD-2's VB: each held by a big cap to ground) is flagged `bias`, so its labels draw
    as a supply bar; a signal net isn't."""
    for name, net in (("ts808", "VREF"), ("klon-centaur-aion", "VR"), ("boss-bd2-aion", "VB")):
        nets = circuit_view(load_circuit(REPO / "library" / "starters" / f"{name}.json"))["nets"]
        assert nets[net]["bias"] and not nets[net]["rail"], name
        assert not nets["in"]["bias"] and not nets["V+"]["bias"], name
