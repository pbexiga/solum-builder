"""*Start for me* (D-387): Start over and Fill the rest on the Rangemaster, each board
checked; what Fill the rest can't join is named; nothing to do says so."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Layout, layout_from_data
from solum.stripboard.check import check_layout
from solum.stripboard.footprints import board_parts
from solum.stripboard.limits import Limit, LoudInput, broken_limits, placement_limits
from solum.stripboard.start import StartError, _Block, _units, shapes, start_for_me
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def without(*refs: str, **changes: Any) -> Layout:
    """The hand-made board with these parts back in the tray and no wires."""
    parts = {k: v for k, v in GOOD["parts"].items() if k not in refs}
    return layout_from_data({**GOOD, "parts": parts, "wires": [], **changes})


def test_start_over_lays_out_a_checked_board_the_same_every_run() -> None:
    first = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False)
    again = start_for_me(None, RANGEMASTER, MODELS, TABLE, fill=False)
    assert first == again and first.left == ()
    assert check_layout(first.layout, RANGEMASTER, MODELS, TABLE).ok
    board = first.layout
    assert {p.ref for p in board.parts} == set(GOOD["parts"])
    assert board.columns * board.strips <= 12 * 10  # about as tight as by hand (11×9)
    assert {w.lug for w in board.wires} >= {"VR1.1", "VR1.2", "VR1.3", "IN.out", "OUT.in"}


def test_start_over_replaces_the_board_but_keeps_the_on_off_choices() -> None:
    """What's on the board goes (its parts, cuts, links, wires); the parts' On / Off the
    board choices stay."""
    old = layout_from_data({**GOOD, "where": {"VR1": "off-board"}})
    started = start_for_me(old, RANGEMASTER, MODELS, TABLE, fill=False).layout
    assert started.where == old.where
    assert started.parts != old.parts and not started.cuts & old.cuts - started.cuts
    assert check_layout(started, RANGEMASTER, MODELS, TABLE).ok


@pytest.mark.parametrize("tray", [("R2",), ("C3", "R3"), ("Q1",), ("C1", "C2", "C3", "C4")])
def test_fill_the_rest_keeps_what_s_placed_and_lays_out_the_tray(tray: tuple[str, ...]) -> None:
    before = without(*tray)
    filled = start_for_me(before, RANGEMASTER, MODELS, TABLE, fill=True)
    board = filled.layout
    assert filled.left == () and check_layout(board, RANGEMASTER, MODELS, TABLE).ok
    assert board.parts[: len(before.parts)] == before.parts  # nothing moved
    assert before.cuts <= board.cuts and board.links[: len(before.links)] == before.links
    assert {p.ref for p in board.parts} == set(GOOD["parts"])
    assert board.columns >= before.columns and board.strips > before.strips  # laid out below


def test_fill_the_rest_with_nothing_to_do_says_so() -> None:
    with pytest.raises(StartError, match="Nothing to fill"):
        start_for_me(layout_from_data(GOOD), RANGEMASTER, MODELS, TABLE, fill=True)


def test_fill_the_rest_names_a_piece_it_can_t_join_and_moves_nothing() -> None:
    """Q1 alone, every other hole of its strips cut: no free hole for a link to start
    from, so its emitter's and base's nets (each with legs in the tray) are named, and Q1
    stays where it is; the board doesn't pass (the progress check shows the rest)."""
    boxed = {"size": [3, 3], "parts": {"Q1": {"E": "B1", "B": "B2", "C": "B3"}},
             "cuts": ["A1", "C1", "A2", "C2", "A3", "C3"]}  # fmt: skip
    filled = start_for_me(layout_from_data(boxed), RANGEMASTER, MODELS, TABLE, fill=True)
    assert [s.split(":")[0] for s in filled.left] == ["Q1.B", "Q1.E"]
    assert all("no free column" in s for s in filled.left)
    assert filled.layout.parts[0] == layout_from_data(boxed).parts[0]
    assert not check_layout(filled.layout, RANGEMASTER, MODELS, TABLE).ok


def test_a_part_that_can_t_go_on_a_board_is_named() -> None:
    """The BD-2 (Aion)'s Q1 off its adapter (D-392): surface-mount, named."""
    bd2 = load_circuit(LIBRARY / "starters" / "boss-bd2-aion.json").with_part("Q1", adapter=False)
    with pytest.raises(StartError, match="surface-mount"):
        start_for_me(None, bd2, MODELS, TABLE, fill=False)


def test_shapes_stand_each_part_across_the_strips() -> None:
    """A chip either way up; a transistor's legs down a column either way round; a flat
    resistor from its least span to three holes more, either way round."""
    board, _ = board_parts(RANGEMASTER, MODELS, TABLE)
    q1 = shapes(board["Q1"])
    assert all({x for x, _ in s.legs.values()} == {0} for s in q1)
    assert q1[0].legs == {"E": (0, 0), "B": (0, 1), "C": (0, 2)}
    assert q1[1].legs == {"C": (0, 0), "B": (0, 1), "E": (0, 2)}
    r1 = shapes(board["R1"])
    flat = board["R1"].footprint.flat
    assert [s.legs["2"][1] + s.legs["1"][1] for s in r1[::2]] == [
        flat,
        flat + 1,
        flat + 2,
        flat + 3,
    ]


def test_a_part_with_two_legs_on_one_net_gets_a_short_link_beside_it() -> None:
    """A trimmer as a variable resistor (its wiper tied to one end) and two op-amp
    buffers (out tied to -, on the chip's same side: 1 and 2, 7 and 6): the tied legs'
    strips are joined by a link right beside the part, not by a long link to a bus (the
    user, 2026-11-23)."""
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "a", value="100n", kind="film")
        .part("TR1", "trimmer", "a", "b", "b", value="10k")
        .part("IC1A", "opamp", "b", "o", "o", model="TL072", half="a")
        .part("IC1B", "opamp", "o", "p", "p", model="TL072", half="b")
        .part("R1", "resistor", "p", "GND", value="10k")
        .part("OUT", "amp", "p")
    ).build()
    made = start_for_me(None, c, MODELS, TABLE, fill=False)
    assert made.left == () and check_layout(made.layout, c, MODELS, TABLE).ok
    board = made.layout
    legs = {p.ref: dict(p.legs) for p in board.parts}
    for ref, a, b in (("TR1", "2", "3"), ("IC1", "1", "2"), ("IC1", "7", "6")):
        rows = sorted((legs[ref][a][1], legs[ref][b][1]))
        columns = [h[0] for h in legs[ref].values()]
        beside = [
            link
            for link in board.links
            if (link.a[1], link.b[1]) == tuple(rows)
            and min(columns) - 3 <= link.a[0] <= max(columns) + 3
        ]
        assert beside, f"{ref}: no short link beside it in {board.links}"


# --- placement limits (D-367, D-400) -------------------------------------------------
# The high-gain stages' inputs as `probe.loud_inputs` finds them (it needs ngspice).
LOUD = {
    "dallas-rangemaster": [LoudInput("Q1", "B", frozenset({"GND", "V-"}))],
    "fuzz-face":[LoudInput("Q1", "B", frozenset({"GND", "V-"})),
                  LoudInput("Q2", "B", frozenset({"GND", "Q1.B", "V-", "in"}))],
    "proco-rat": [LoudInput("IC1", "+", frozenset({"GND", "IC1.comp1", "V+", "VREF"}))],
}  # fmt: skip
# What Start still breaks: the Rat's C4 (feedback, pin 2) lands a hole too far, the chip's
# own link left of pin 1 taking the nearer column (Build a full layout meets it).
BROKEN = {"proco-rat": [("IC1", "2")]}


def test_units_take_each_kept_part_into_the_block_of_the_part_whose_pin_keeps_it() -> None:
    """In the order given; a part kept by two pins goes with the first; a part that keeps
    others (a transistor kept by a chip's pin) stays a block of its own."""
    limits = [Limit("C1", "1", "IC1", "8", "decoupling"), Limit("R4", "2", "IC1", "2", "feedback"),
              Limit("R4", "1", "Q1", "E", "bypass"), Limit("Q1", "B", "IC1", "1", "input"),
              Limit("C2", "1", "Q1", "E", "bypass")]  # fmt: skip
    order = ["R1", "Q1", "C2", "IC1", "C1", "R4", "R9"]
    assert _units(order, limits) == [
        "R1",
        _Block("Q1", (limits[4],)),
        _Block("IC1", (limits[0], limits[1])),
        "R9",
    ]
    assert _units(["R1", "R2"], limits) == ["R1", "R2"]


@pytest.mark.parametrize("name", sorted(LOUD))
def test_start_over_breaks_no_placement_limit(name: str) -> None:
    """The Rangemaster and Fuzz Face (bypass caps, the parts in series on each base) and the
    Rat (its chip's decoupling cap, feedback parts, the input on +): every kept part by its
    pin, but for those in `BROKEN`."""
    c = load_circuit(LIBRARY / "starters" / f"{name}.json")
    limits = placement_limits(c, connect(c), board_parts(c, MODELS, TABLE)[0], LOUD[name])
    assert limits
    made = start_for_me(None, c, MODELS, TABLE, fill=False, loud=LOUD[name])
    assert made.left == () and check_layout(made.layout, c, MODELS, TABLE).ok
    assert broken_limits(made.layout, limits) == BROKEN.get(name, [])


def test_a_chip_s_kept_parts_sit_by_their_pins() -> None:
    """A boost: the feedback resistor goes before the chip by pin 2 (the first column, its
    strip runs left), the decoupling cap after it by pin 7, each on the pin's strip."""
    c = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "p", value="100n", kind="film")
        .part("R1", "resistor", "p", "vb", value="1M")
        .part("R2", "resistor", "V+", "vb", value="10k")
        .part("R3", "resistor", "vb", "GND", value="10k")
        .part("C2", "capacitor", "vb", "GND", value="10u", kind="electrolytic")
        .part("IC1", "opamp", "p", "m", "o", model="TL071")
        .part("R4", "resistor", "o", "m", value="100k")
        .part("R5", "resistor", "m", "g", value="4k7")
        .part("C4", "capacitor", "g", "GND", value="1u", kind="film")
        .part("C5", "capacitor", "V+", "GND", value="100n", kind="ceramic")
        .part("C6", "capacitor", "o", "out", value="1u", kind="film")
        .part("R6", "resistor", "out", "GND", value="100k")
        .part("OUT", "amp", "out")
    ).build()
    limits = placement_limits(c, connect(c), board_parts(c, MODELS, TABLE)[0])
    assert [(lim.part, lim.pin) for lim in limits] == [("C5", "7"), ("R4", "2")]
    made = start_for_me(None, c, MODELS, TABLE, fill=False)
    assert made.left == () and check_layout(made.layout, c, MODELS, TABLE).ok
    assert broken_limits(made.layout, limits) == []
    legs = {p.ref: dict(p.legs) for p in made.layout.parts}
    pin2, pin7 = legs["IC1"]["2"], legs["IC1"]["7"]
    assert legs["R4"]["2"][1] == pin2[1] and legs["R4"]["2"][0] < pin2[0]
    assert legs["C5"]["1"][1] == pin7[1] and legs["C5"]["1"][0] > pin7[0]
