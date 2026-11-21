"""On the board or off it, by the builder's choice (D-385): a part moved off is an off-board
part wired like a pot, one moved on goes back in the tray, the choice kept with the board
and followed by the parts list. On the hand-made Rangemaster layout
(`tests/fixtures/stripboard/rangemaster.yaml`): R2 sits from J4 (Q1's base strip) to J8."""

import json
from pathlib import Path
from typing import Any

import pytest

from solum.circuit.io import circuit_to_dict, load_circuit
from solum.circuit.schema import Circuit
from solum.export import bom, built_where, chosen_where, movable_where, why_not_moved
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Wire, layout_data, layout_from_data
from solum.stripboard.check import check_layout, move_problem, progress
from solum.stripboard.edit import BoardEdit, EditError, edit_layout
from solum.stripboard.footprints import board_parts
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD: dict[str, Any] = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")
STATUS = {"ref": "LED1", "pos": [600, 600], "type": "led", "model": "WP7113SURDK",
          "label": "Status"}  # fmt: skip


def with_board(board: dict[str, Any], extra: list[dict[str, Any]] | None = None) -> Circuit:
    """The Rangemaster carrying `board` (the choices are read from the circuit's board)."""
    data = circuit_to_dict(RANGEMASTER)
    data["parts"] = [*data["parts"], *(extra or [])]
    plain = json.loads(json.dumps(board))  # the YAML's leg names are numbers
    return Circuit.model_validate({**data, "stripboard": plain})


def without_r2(**more: Any) -> dict[str, Any]:
    parts = {k: v for k, v in GOOD["parts"].items() if k != "R2"}
    return {**GOOD, "parts": parts, "where": {"R2": "off-board"}, **more}


def edit(board: dict[str, Any], change: BoardEdit, circuit: Circuit) -> dict[str, Any]:
    items = {i.ref: tuple(lug.end for lug in i.lugs)
             for i in progress(layout_from_data(board), circuit, MODELS, TABLE).items}  # fmt: skip
    parts = board_parts(circuit, MODELS, TABLE)[0]
    done = edit_layout(layout_from_data(board), change, parts, started=True, grow=False,
                       items=items, usual=movable_where(circuit))  # fmt: skip
    return layout_data(done.layout)


def test_the_choice_wins_over_the_parts_list_only_where_a_part_may_move() -> None:
    r2, vr1 = RANGEMASTER.part("R2"), RANGEMASTER.part("VR1")
    assert built_where(r2) == "board"
    assert built_where(r2, {"R2": "off-board"}) == "off-board"
    assert built_where(vr1, {"VR1": "board"}) == "off-board"  # no footprint for a pot
    assert why_not_moved(vr1) == "There's no board footprint for a pot yet."
    assert why_not_moved(r2) is None
    assert movable_where(RANGEMASTER) == {
        r: "board" for r in ("C1", "C2", "C3", "C4", "Q1", "R1", "R2", "R3")
    }
    assert chosen_where(RANGEMASTER) == {}  # no board, no choices


def test_a_resistor_moved_off_is_an_off_board_part_with_two_lugs() -> None:
    circuit = with_board(without_r2())
    p = progress(layout_from_data(without_r2()), circuit, MODELS, TABLE)
    assert "R2" not in p.to_place
    r2 = next(i for i in p.items if i.ref == "R2")
    assert (r2.kind, r2.value, [lug.label for lug in r2.lugs]) == ("resistor", "68k", ["1", "2"])
    assert sorted(p.wires_to_go)[-2:] == ["R2.1", "R2.2"]
    assert p.choices["R2"].where == "off-board" and p.choices["R2"].moved
    assert p.choices["R2"].why is None
    assert p.choices["R1"].where == "board" and not p.choices["R1"].moved
    assert p.choices["VR1"].why == "There's no board footprint for a pot yet."
    lines = {(line.where, line.part): line.refs for line in bom(circuit, MODELS)}
    assert lines[("off-board", "Resistor")] == ("R2",)


def test_a_resistor_moved_off_and_wired_to_its_holes_passes_the_check() -> None:
    wires = [*GOOD["wires"], {"from": "R2.1", "hole": "J4"}, {"from": "R2.2", "hole": "J8"}]
    board = without_r2(wires=wires)
    assert check_layout(layout_from_data(board), with_board(board), MODELS, TABLE).ok
    miswired = without_r2(wires=[*GOOD["wires"], {"from": "R2.1", "hole": "J5"},
                                 {"from": "R2.2", "hole": "J8"}])  # fmt: skip
    found = check_layout(layout_from_data(miswired), with_board(miswired), MODELS, TABLE)
    assert not found.ok and any("R2" in f for f in found.faults)


def test_moving_off_takes_the_part_off_and_keeps_the_choice() -> None:
    moved = edit(GOOD, BoardEdit("where", "R2", to="off-board"), with_board(GOOD))
    assert "R2" not in moved["parts"] and moved["where"] == {"R2": "off-board"}


def test_back_to_the_parts_list_s_place_drops_the_choice_and_the_wires() -> None:
    board = without_r2(wires=[*GOOD["wires"], {"from": "R2.1", "hole": "J4"}],
                       off={"R2": [3, -8]})  # fmt: skip
    back = edit(board, BoardEdit("where", "R2"), with_board(board))
    assert back["where"] == {} and "R2" not in back["off"]
    assert all(w["from"] != "R2.1" for w in back["wires"])
    assert len(back["wires"]) == len(GOOD["wires"])


def test_a_move_that_cant_be_made_is_refused_in_a_sentence() -> None:
    circuit = with_board(GOOD)
    with pytest.raises(EditError, match="VR1 can't be moved on or off the board"):
        edit(GOOD, BoardEdit("where", "VR1", to="board"), circuit)
    with pytest.raises(EditError, match="R2 is on the board already"):
        edit(GOOD, BoardEdit("where", "R2", to="board"), circuit)


def test_the_status_led_goes_on_the_board_by_choice() -> None:
    off = with_board(GOOD, [STATUS])
    assert built_where(off.part("LED1"), chosen_where(off)) == "off-board"
    assert move_problem(off.part("LED1"), True, MODELS, TABLE) is None
    on_board = {**GOOD, "where": {"LED1": "board"}}
    on = with_board(on_board, [STATUS])
    p = progress(layout_from_data(on_board), on, MODELS, TABLE)
    assert "LED1" in p.to_place and p.choices["LED1"].moved
    assert all(i.ref != "LED1" for i in p.items)
    assert not [line for line in bom(on, MODELS) if line.part == "LED bezel"]
    assert [line.refs for line in bom(off, MODELS) if line.part == "LED bezel"] == [
        ("LED1 (Status)",)
    ]


def test_moving_on_takes_its_spot_and_wires_away() -> None:
    board = {**GOOD, "off": {"LED1": [2, -6]}, "wires": [*GOOD["wires"], {"from": "LED1.A"}]}
    circuit = with_board(board, [STATUS])
    on = edit(board, BoardEdit("where", "LED1", to="board"), circuit)
    assert on["where"] == {"LED1": "board"} and "LED1" not in on["off"]
    assert Wire("LED1.A", None) not in layout_from_data(on).wires
