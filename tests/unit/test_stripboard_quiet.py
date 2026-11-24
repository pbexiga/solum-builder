"""Quiet links (D-402): a link too near a high-gain input's parts is warned about, by
`quiet.noisy_links`, and in the board's progress check."""

from collections.abc import Callable
from pathlib import Path

from solum.circuit.build import CircuitBuilder
from solum.circuit.connectivity import Nets, connect
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.guides import footprint_table
from solum.models import load_models
from solum.stripboard.board import Layout, Link, Placed, parse_hole
from solum.stripboard.check import progress
from solum.stripboard.footprints import BoardPart, board_parts
from solum.stripboard.limits import LoudInput
from solum.stripboard.quiet import guards, kept_clear, noisy_links, quiet_warnings

LIBRARY = Path(__file__).resolve().parents[2] / "library"
MODELS = load_models([LIBRARY / "models"])
TABLE = footprint_table(LIBRARY)
LOUD = [LoudInput("Q1", "B", frozenset({"V+"}))]


def _stage(circuit: Callable[..., CircuitBuilder]) -> tuple[Circuit, dict[str, BoardPart], Nets]:
    """A transistor stage: R1 (collector to base) on the high-gain base, R2 its load, not."""
    c = (
        circuit()
        .rail("V+", 9)
        .part("Q1", "bjt", "c", "b", "0", model="2N2222A")
        .part("C1", "capacitor", "in", "b", value="100n", kind="film")
        .part("R1", "resistor", "c", "b", value="470k")
        .part("R2", "resistor", "V+", "c", value="10k")
        .build()
    )
    board, _ = board_parts(c, MODELS, TABLE)
    return c, board, connect(c)


def _h(*names: str) -> tuple[tuple[int, int], ...]:
    return tuple(parse_hole(n) for n in names)


def _placed(board: dict[str, BoardPart], links: tuple[Link, ...]) -> Layout:
    """R1 flat on strip 11 (C11 to G11, its base leg at G11, a cut at E11 under it so its
    legs don't share copper), R2 flat on strip 21; Q1 and C1 far off on the right."""
    q1 = board["Q1"].legs
    parts = (
        Placed("R1", (("1", parse_hole("C11")), ("2", parse_hole("G11")))),
        Placed("R2", (("1", parse_hole("C21")), ("2", parse_hole("G21")))),
        Placed("Q1", tuple(zip(q1, _h("Z3", "Z4", "Z5"), strict=True))),
        Placed("C1", (("1", parse_hole("X8")), ("2", parse_hole("X9")))),
    )
    return Layout(30, 25, parts, frozenset({parse_hole("E11")}), links)


def test_the_parts_on_a_high_gain_input_are_guarded() -> None:
    """Each part on the input's net, by its legs on it; a chip only by the input pin."""
    ts808 = load_circuit(LIBRARY / "starters" / "ts808.json")
    board, _ = board_parts(ts808, MODELS, TABLE)
    found = {g.ref: g.legs for g in guards(board, connect(ts808), [LoudInput("IC1B", "+")])}
    assert found["IC1"] == ("5",)
    assert all(g.anchor == "IC1" and g.pin == "5"
               for g in guards(board, connect(ts808), [LoudInput("IC1B", "+")]))  # fmt: skip
    assert guards(board, connect(ts808), []) == []


def test_kept_clear_is_the_eight_holes_round_each_leg_and_body_hole() -> None:
    under, clear = kept_clear([(5, 5)], [(6, 5)])
    assert under == {(6, 5)}
    assert len(clear) == 3 * 4  # a 3 × 4 block round the two holes
    assert (4, 4) in clear and (7, 6) in clear and (8, 5) not in clear


def test_a_link_under_or_beside_an_input_part_is_noisy_one_by_another_part_isn_t(
    circuit: Callable[..., CircuitBuilder],
) -> None:
    _, board, nets = _stage(circuit)
    kept = guards(board, nets, LOUD)
    assert {g.ref for g in kept} == {"C1", "Q1", "R1"}
    under = Link(parse_hole("D10"), parse_hole("D12"))  # across R1's body
    beside = Link(parse_hole("H12"), parse_hole("H14"))  # a hole off R1's base leg, diagonally
    far = Link(parse_hole("M1"), parse_hole("M5"))
    tone = Link(parse_hole("D20"), parse_hole("D22"))  # across R2: not on the input
    own = Link(parse_hole("H11"), parse_hole("H14"))  # the base's own net: let be
    layout = _placed(board, (under, beside, far, tone, own))
    noisy = noisy_links(layout, board, nets, kept)
    assert [(n.link, n.guard.ref, n.under) for n in noisy] == [
        (under, "R1", True),
        (beside, "R1", False),
    ]
    assert quiet_warnings(noisy) == [
        "The link from D10 to D12 runs under R1, on Q1's base (the high-gain stage's "
        "input): move it a column or two, so it picks up no noise there.",
        "The link from H12 to H14 runs beside R1, on Q1's base (the high-gain stage's "
        "input): move it a column or two, so it picks up no noise there.",
    ]


def test_no_loud_input_no_noisy_link(circuit: Callable[..., CircuitBuilder]) -> None:
    _, board, nets = _stage(circuit)
    layout = _placed(board, (Link(parse_hole("D10"), parse_hole("D12")),))
    assert noisy_links(layout, board, nets, guards(board, nets, [])) == []


def test_the_progress_check_warns_of_a_noisy_link(circuit: Callable[..., CircuitBuilder]) -> None:
    c, board, _ = _stage(circuit)
    layout = _placed(board, (Link(parse_hole("D10"), parse_hole("D12")),))
    said = progress(layout, c, MODELS, TABLE, LOUD).warnings
    assert any(w.startswith("The link from D10 to D12 runs under R1") for w in said)
    quiet = progress(layout, c, MODELS, TABLE).warnings
    assert not any(w.startswith("The link from") for w in quiet)


def test_a_quiet_net_s_link_may_pass() -> None:
    """The Rangemaster's V- link down column B passes R1's leg on Q1's base: V- is quiet
    beside the base (`probe.loud_inputs`), nothing on it to pick up, so it's let be; were
    V- carrying signal, it would be warned."""
    from solum.stripboard.board import layout_from_data
    from solum.yamlio import load_yaml

    repo = LIBRARY.parent
    rangemaster = load_circuit(LIBRARY / "starters" / "dallas-rangemaster.json")
    layout = layout_from_data(load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml"))
    board, _ = board_parts(rangemaster, MODELS, TABLE)
    nets = connect(rangemaster)
    calm = guards(board, nets, [LoudInput("Q1", "B", frozenset({"GND", "V-"}))])
    assert noisy_links(layout, board, nets, calm) == []
    loud = guards(board, nets, [LoudInput("Q1", "B")])
    assert [(n.link.a, n.guard.ref) for n in noisy_links(layout, board, nets, loud)] == [
        (parse_hole("B1"), "R1")
    ]
