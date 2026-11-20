"""The editor's progress check (D-368): a board in the making, part by part, and the
placement limits shown as warnings."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import layout_from_data, parse_hole
from solum.stripboard.check import Progress, check_layout, progress, stock_bypass
from solum.stripboard.footprints import board_parts
from solum.stripboard.limits import Limit, group_met, limit_warnings, placement_limits
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")
BOARD_REFS = ["C1", "C2", "C3", "C4", "Q1", "R1", "R2", "R3"]


def run(data: dict[str, Any], circuit: Circuit = RANGEMASTER) -> Progress:
    return progress(layout_from_data(data), circuit, MODELS, TABLE)


def edited(**changes: Any) -> dict[str, Any]:
    data = {**GOOD, **changes}
    if "parts" in changes:
        data["parts"] = {**GOOD["parts"], **changes["parts"]}
    return data


def states(p: Progress) -> dict[str, str]:
    return {n.net: n.state for n in p.nets}


def test_an_empty_board_has_everything_to_place_and_no_faults() -> None:
    p = run({"size": [12, 9]})
    assert p.to_place == BOARD_REFS
    assert sorted(p.pads_to_place) == ["GND", "IN.out", "OUT.in", "V-", "VR1.1", "VR1.2",
                                       "VR1.3"]  # fmt: skip
    assert p.faults == [] and p.stale == [] and not p.done
    assert set(states(p).values()) == {"pieces"}
    assert all(n.placed == 0 and n.pieces == 0 for n in p.nets)
    assert p.nets[0].net == "GND"  # ground first


def test_a_part_with_no_footprint_is_unplaceable_not_a_fault() -> None:
    """D-370: the tool opens whatever the circuit's state; a part it can't size is named
    for the tray and left out of `to_place`, never a fault."""
    data = RANGEMASTER.model_dump(mode="json", exclude_none=True)
    for part in data["parts"]:
        if part["ref"] == "C1":
            del part["kind"]
    p = run({"size": [12, 9]}, Circuit.model_validate(data))
    assert "C1" not in p.to_place and p.faults == []
    assert len(p.unplaceable) == 1 and "C1" in p.unplaceable[0]


def test_the_finished_rangemaster_is_done_net_by_net() -> None:
    p = run(GOOD)
    assert p.done and p.faults == [] and p.to_place == [] and p.pads_to_place == []
    assert p.nets_done == len(p.nets) == len(connect(RANGEMASTER).members)
    assert all(n.placed == n.total and n.pieces == 1 for n in p.nets)


def test_a_part_not_yet_placed_is_to_place_not_a_fault() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "C4"}
    p = run({**GOOD, "parts": parts})
    assert p.to_place == ["C4"] and p.faults == [] and not p.done
    c4 = {n.net for n in p.nets if n.state == "pieces"}
    assert c4 == {connect(RANGEMASTER).net_of("C4", pin) for pin in ("1", "2")}
    assert p.nets_done == len(p.nets) - 2


def test_a_short_names_the_other_net_and_where() -> None:
    p = run(edited(cuts=[]))  # G8's cut missed: V- and GND on strip 8
    shorted = {n.net: n for n in p.nets if n.state == "shorted"}
    assert set(shorted) == {"V-", "GND"}
    assert shorted["V-"].shorts[0].other == "GND"
    assert "R1's leg at C8 and R2's leg at J8 are joined" in shorted["V-"].shorts[0].words
    assert not p.done


def test_a_reversed_electrolytic_is_named() -> None:
    p = run(edited(parts={"C3": {"1": "H3", "2": "H2"}}))
    assert p.faults == [
        "C3 is the wrong way round: C3's + leg at H3 and C3's − leg at H2 are each on the "
        "other's strip. Turn it."
    ]


def test_a_resistor_or_film_cap_has_no_way_round() -> None:
    """D-368: the check turns an either-way part to fit; the full check passes it too."""
    turned = edited(parts={"R1": {"1": "C4", "2": "C8"}, "C1": {"1": "F4", "2": "F6"}})
    assert check_layout(layout_from_data(turned), RANGEMASTER, MODELS, TABLE).ok
    assert run(turned).done


def test_a_part_gone_from_the_circuit_is_stale_not_a_fault() -> None:
    p = run(edited(parts={"R9": {"1": "L1", "2": "L5"}}))
    assert p.stale == ["R9"] and p.faults == [] and not p.done


def test_each_leg_says_what_it_must_reach_and_whether_it_does() -> None:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "R2"}
    p = run({**GOOD, "parts": parts})
    r1 = {leg.leg: leg for leg in p.legs["R1"]}
    assert r1["2"].hole == "C4" and r1["2"].net == connect(RANGEMASTER).net_of("Q1", "B")
    assert {(x.to, x.joined) for x in r1["2"].reach} == {("Q1.B", True), ("C1.2", True),
                                                         ("R2.1", False)}  # fmt: skip
    assert [leg.hole for leg in p.legs["R2"]] == [None, None]


# --- placement limits ----------------------------------------------------------------


def _two_buffers(circuit: Callable[..., CircuitBuilder]) -> Circuit:
    return (
        circuit()
        .rail("V+", 9)
        .part("IC1A", "opamp", "in", "a", "a", model="TL072", half="a")
        .part("IC1B", "opamp", "in2", "b", "b", model="TL072", half="b")
        .part("C1", "capacitor", "V+", "0", value="100n", kind="ceramic")
        .build()
    )


def test_a_decoupling_cap_must_sit_by_its_chip_s_supply_pin(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    c = _two_buffers(circuit)
    board, _ = board_parts(c, MODELS, TABLE)
    limits = placement_limits(c, connect(c), board)
    assert limits == [Limit("C1", "1", "IC1", "8", "decoupling")]
    chip = {"1": "E3", "2": "E4", "3": "E5", "4": "E6", "8": "H3", "7": "H4", "6": "H5",
            "5": "H6"}  # fmt: skip
    far = layout_from_data({"size": [14, 8], "parts": {"IC1": chip,
                            "C1": {"1": "L3", "2": "L2"}}})  # fmt: skip
    assert limit_warnings(far, limits) == [
        "C1 should sit by IC1's pin 8 at H3 (its decoupling cap): on its strip within 2 "
        "holes, nothing between."
    ]
    near = layout_from_data({"size": [14, 8], "parts": {"IC1": chip,
                             "C1": {"1": "J3", "2": "J2"}}})  # fmt: skip
    assert limit_warnings(near, limits) == []


def test_group_met_counts_holes_from_the_pin_one_more_per_extra_leg() -> None:
    pin = parse_hole("E3")
    clear: Callable[[tuple[int, int]], bool] = lambda h: False  # noqa: E731
    assert group_met(pin, [parse_hole("G3")], clear)  # 2 holes away
    assert not group_met(pin, [parse_hole("H3")], clear)  # 3
    assert group_met(pin, [parse_hole("H3"), parse_hole("C3")], clear)  # 3 with two legs
    assert not group_met(pin, [parse_hole("G4")], clear)  # another strip
    assert not group_met(pin, [parse_hole("G3")], lambda h: h == parse_hole("F3"))


def test_the_tray_lists_off_board_parts_as_the_parts_list_does() -> None:
    """The Rangemaster's pot, and the guitar's and amp's jacks it doesn't draw."""
    p = run({"size": [12, 9]})
    assert [(o.ref, o.part, o.value) for o in p.off_board] == [
        ("VR1 (Volume)", "Pot", "A10k"), ("IN (Input)", "Jack", '¼" jack'),
        ("OUT (Output)", "Jack", '¼" jack'),
    ]  # fmt: skip


def test_stock_bypass_only_when_the_schematic_draws_none() -> None:
    """D-370: a drawn footswitch or status LED replaces the stock one; never both."""
    assert stock_bypass(RANGEMASTER) == ["footswitch", "status LED"]
    klon = load_circuit(LIBRARY / "starters" / "klon-centaur-aion-built.json")
    assert stock_bypass(klon) == ["status LED"]  # its LED1 isn't labelled "status"
    data = klon.model_dump(mode="json", exclude_none=True)
    data["parts"] = [p for p in data["parts"] if p["ref"] not in ("SW2B", "SW2C")]
    for part in data["parts"]:
        if part["ref"] == "LED1":
            part["label"] = "Status"
        if part["type"] == "switch" and part["kind"] == "footswitch":
            part["kind"] = "footswitch-momentary"  # a tap-tempo switch is no bypass
            part.pop("pole", None)
            part["ref"] = "SW2"
    data["wires"] = []  # the poles' wires went with them; stock_bypass reads only parts
    assert stock_bypass(Circuit.model_validate(data)) == ["footswitch"]


def test_each_net_names_its_off_board_wires_still_to_land() -> None:
    """D-371: the wire ends are listed with their nets (the Nets pane), not in the tray."""
    empty = {n.net: n.wires for n in run({"size": [12, 9]}).nets}
    assert empty["V-"] == ("V-", "VR1.1") and empty["C2.1"] == ("VR1.2",)
    assert sum(len(w) for w in empty.values()) == 7
    assert all(n.wires == () for n in run(GOOD).nets)
