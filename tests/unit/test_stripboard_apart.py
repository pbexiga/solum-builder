"""A stage's output kept away from its input (P6i2, D-404): a later net's copper beside a
high-gain input's, by `apart.alongside`, and in the board's progress check."""

from collections.abc import Callable
from pathlib import Path

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import connect
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.apart import ALONGSIDE, alongside, apart_warnings
from solum.stripboard.board import Layout, Placed, parse_hole
from solum.stripboard.check import copper_groups, progress
from solum.stripboard.footprints import board_parts
from solum.stripboard.limits import LoudInput

LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)


def _stage(circuit: Callable[..., CircuitBuilder]):  # type: ignore[no-untyped-def]
    """Q1's base fed by C1; its collector (later, in phase as the check would find it,
    `along`) loaded by R2 from V+."""
    c = (
        circuit()
        .rail("V+", 9)
        .part("Q1", "bjt", "c", "b", "e", model="2N2222A")
        .part("C1", "capacitor", "in", "b", value="100n", kind="film")
        .part("R1", "resistor", "e", "0", value="1k")
        .part("R2", "resistor", "V+", "c", value="10k")
        .build()
    )
    board, _ = board_parts(c, MODELS, TABLE)
    return c, board, connect(c)


def _beside(board, cuts: tuple[str, ...] = ()) -> Layout:  # type: ignore[no-untyped-def]
    """Q1's base on strip 3 and its collector on strip 4, with C1 and R2 beside them at
    column B; uncut, both strips' copper runs the board's width."""
    h = parse_hole
    at = {"C": "A4", "B": "A3", "E": "A1"}
    return Layout(12, 8, (
        Placed("Q1", tuple((leg, h(at[board["Q1"].pins[leg][1]])) for leg in board["Q1"].legs)),
        Placed("C1", (("1", h("B2")), ("2", h("B3")))),
        Placed("R2", (("1", h("B6")), ("2", h("B4")))),
    ), frozenset(h(x) for x in cuts))  # fmt: skip


def test_a_later_net_beside_a_high_gain_input_is_found(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    c, board, nets = _stage(circuit)
    base, collector = nets.net_of("Q1", "B"), nets.net_of("Q1", "C")
    loud = [LoudInput("Q1", "B", along=frozenset({collector}))]
    lay = _beside(board)
    found = alongside(lay, board, nets, loud, copper_groups(lay))
    assert [(f.ref, f.pin, f.net, f.later, f.said, f.strips, f.columns) for f in found] == [
        ("Q1", "B", base, collector, "Q1's collector", (2, 3), (0, 11))
    ]
    (said,) = apart_warnings(found)
    assert said.startswith("Strips 3 and 4 run side by side from A to L: Q1's base")
    assert "Q1's collector" in said
    assert any(w == said for w in progress(lay, c, MODELS, TABLE, loud).warnings)


def test_copper_cut_short_or_not_in_phase_isn_t_warned(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    """Cut at C on both strips, they share columns A and B only (under `ALONGSIDE`); with
    no `along` (the collector not in phase), never."""
    _, board, nets = _stage(circuit)
    loud = [LoudInput("Q1", "B", along=frozenset({nets.net_of("Q1", "C")}))]
    cut = _beside(board, ("C3", "C4"))
    assert ALONGSIDE == 3 and alongside(cut, board, nets, loud, copper_groups(cut)) == []
    lay = _beside(board)
    assert alongside(lay, board, nets, [LoudInput("Q1", "B")], copper_groups(lay)) == []
