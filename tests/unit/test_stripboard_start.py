"""The starting board of *Lay it out for me* (`start_for_me`, D-387, D-399): the whole
board laid out afresh, checked, the same every run; a part that can't go on a board is
named."""

from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import layout_from_data
from solum.stripboard.check import check_layout
from solum.stripboard.footprints import board_parts
from solum.stripboard.start import StartError, shapes, start_for_me
from solum.yamlio import load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
RANGEMASTER = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
GOOD = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")


def test_start_over_lays_out_a_checked_board_the_same_every_run() -> None:
    first = start_for_me(None, RANGEMASTER, MODELS, TABLE)
    again = start_for_me(None, RANGEMASTER, MODELS, TABLE)
    assert first == again
    assert check_layout(first.layout, RANGEMASTER, MODELS, TABLE).ok
    board = first.layout
    assert {p.ref for p in board.parts} == set(GOOD["parts"])
    assert board.columns * board.strips <= 12 * 10  # about as tight as by hand (11×9)
    assert {w.lug for w in board.wires} >= {"VR1.1", "VR1.2", "VR1.3", "IN.out", "OUT.in"}


def test_start_over_replaces_the_board_but_keeps_the_on_off_choices() -> None:
    """What's on the board goes (its parts, cuts, links, wires); the parts' On / Off the
    board choices stay."""
    old = layout_from_data({**GOOD, "where": {"VR1": "off-board"}})
    started = start_for_me(old, RANGEMASTER, MODELS, TABLE).layout
    assert started.where == old.where
    assert started.parts != old.parts and not started.cuts & old.cuts - started.cuts
    assert check_layout(started, RANGEMASTER, MODELS, TABLE).ok


def test_a_part_that_can_t_go_on_a_board_is_named() -> None:
    """The BD-2 (Aion)'s Q1 off its adapter (D-392): surface-mount, named."""
    bd2 = load_circuit(LIBRARY / "starters" / "boss-bd2-aion.json").with_part("Q1", adapter=False)
    with pytest.raises(StartError, match="surface-mount"):
        start_for_me(None, bd2, MODELS, TABLE)


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
    made = start_for_me(None, c, MODELS, TABLE)
    assert check_layout(made.layout, c, MODELS, TABLE).ok
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


@pytest.mark.parametrize("name", ["dallas-rangemaster", "fuzz-face", "proco-rat", "ts808"])
def test_start_over_lays_out_the_starters_with_nothing_left(name: str) -> None:
    """With D-410's spans (a resistor flat from 3 apart, film caps 2–4): every leg on its
    net's copper and every net joined, nothing left to the builder."""
    c = load_circuit(LIBRARY / "starters" / f"{name}.json")
    made = start_for_me(None, c, MODELS, TABLE)
    assert check_layout(made.layout, c, MODELS, TABLE).ok
