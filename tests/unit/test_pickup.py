"""A pickup by any three of R, L, C, peak and Q (D-363)."""

import math
from itertools import combinations
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.circuit.pickup import (
    QUANTITIES,
    REFUSED,
    PickupError,
    blocked,
    check_set,
    kept,
    pickup_form,
    solve,
    value_of,
)
from solum.guides import pickup_guide
from solum.units import parse_value

REPO = Path(__file__).resolve().parents[2]
EASY = "R is the easiest: a multimeter across the jack."
THREES = [t for t in combinations(QUANTITIES, 3) if set(t) != REFUSED]

# the Strat from the guide: 6.38 kΩ, 2.55 H, 151 pF → 8.11 kHz unloaded, Q = 2π·f·L/R
STRAT = {"r": 6380.0, "l": 2.55, "c": 151e-12}
STRAT_PEAK = 1 / (2 * math.pi * math.sqrt(2.55 * 151e-12))
STRAT_Q = 2 * math.pi * STRAT_PEAK * 2.55 / 6380


def test_the_strat_by_hand() -> None:
    assert pytest.approx(8110, rel=0.001) == STRAT_PEAK  # the guide's measured 8k11
    assert pytest.approx(20.37, rel=0.001) == STRAT_Q
    out = solve(STRAT)
    assert out["peak"] == pytest.approx(STRAT_PEAK, rel=1e-9)
    assert out["q"] == pytest.approx(STRAT_Q, rel=1e-9)


def test_nine_threes_fix_it_and_one_doesnt() -> None:
    assert len(THREES) == 9


@pytest.mark.parametrize("three", THREES, ids=lambda t: "-".join(t))
def test_every_three_gives_the_other_two_back(three: tuple[str, ...]) -> None:
    full = {**STRAT, "peak": STRAT_PEAK, "q": STRAT_Q}
    out = solve({n: full[n] for n in three})
    for name in QUANTITIES:
        assert out[name] == pytest.approx(full[name], rel=0.001)


@given(
    r=st.floats(1e3, 2e4), l=st.floats(0.5, 10), c=st.floats(20e-12, 500e-12),
    three=st.sampled_from(THREES),
)  # fmt: skip
def test_any_pickup_round_trips(r: float, l: float, c: float, three: tuple[str, ...]) -> None:  # noqa: E741
    full = solve({"r": r, "l": l, "c": c})
    out = solve({n: full[n] for n in three})
    assert [out[n] for n in QUANTITIES] == pytest.approx([full[n] for n in QUANTITIES], rel=1e-6)


def test_l_c_and_peak_are_refused() -> None:
    with pytest.raises(PickupError, match="L and C already give the peak"):
        solve({"l": 2.55, "c": 151e-12, "peak": 8110})
    with pytest.raises(PickupError, match="any three"):
        solve({"r": 1, "l": 1})


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [("q", "-2", "greater than zero"), ("q", "0.2", "below 0.5"), ("peak", "40k", "30 kHz"),
     ("r", "8k2F", "farads"), ("peak", "lots", "Couldn't read"), ("x", "1", "no 'x'")],
)  # fmt: skip
def test_values_out_of_range_are_refused(name: str, text: str, message: str) -> None:
    with pytest.raises(PickupError, match=message):
        value_of(name, text)


def test_the_guides_pickups_c_is_their_peak_and_l() -> None:
    """Each measured pickup's stored C gives back its measured unloaded peak (within 1 %)."""
    for p in pickup_guide(REPO / "library").pickups:
        out = solve({n: parse_value(getattr(p, n)) for n in ("r", "l", "c")})
        assert out["peak"] == pytest.approx(parse_value(p.resonance), rel=0.01)


def test_two_set_dims_the_one_that_cant_complete_it() -> None:
    assert blocked(["l", "c"]) == {"peak": "Not the peak: L and C give it."}
    assert blocked(["l", "peak"]) == {"c": "Not C: L and the peak give it."}
    assert blocked(["peak", "c"]) == {"l": "Not L: the peak and C give it."}
    assert blocked(["r", "peak"]) == {}
    assert blocked(["l"]) == {}


def test_a_fourth_turns_the_oldest_into_worked_out() -> None:
    assert kept(["r", "peak", "q"]) == (["r", "peak", "q"], None)
    assert kept(["r", "peak", "q", "l"]) == (["peak", "q", "l"], "r")
    assert kept(["r", "l", "c", "peak"]) == (["r", "c", "peak"], "l")  # not L, C and peak
    assert kept(["r", "peak", "r"]) == (["peak", "r"], None)  # typed again: last


@pytest.mark.parametrize(
    ("typed", "line", "dimmed"),
    [
        ([], "Type any three of the five. R is the easiest: a multimeter across the jack.", {}),
        ([("r", "8k2")], "R set. Two more: any of L, C, peak or Q.", {}),
        ([("r", "8k2"), ("peak", "5k2")], "R and peak set. One more: L, C or Q.", {}),
        ([("l", "2.5"), ("c", "150p")],
         "L and C set. One more: R or Q. Not the peak: L and C give it. "
         f"{EASY}", {"peak": "Not the peak: L and C give it."}),
        ([("l", "2.5"), ("peak", "5k")],
         "L and peak set. One more: R or Q. Not C: L and the peak give it. "
         f"{EASY}", {"c": "Not C: L and the peak give it."}),
        ([("r", "8k2"), ("peak", ""), ("q", "2")], "R and Q set. One more: L, C or peak.", {}),
    ],
)  # fmt: skip
def test_the_line_says_whats_still_needed(
    typed: list[tuple[str, str]], line: str, dimmed: dict[str, str]
) -> None:
    form = pickup_form(typed)
    assert (form.line, form.dimmed, form.values, form.shown) == (line, dimmed, {}, {})


def test_three_set_work_out_the_other_two() -> None:
    """The friend's case: R, peak and Q → L = Q·R/ω, C = 1/(ω²L)."""
    form = pickup_form([("r", "8k2"), ("peak", "5k2"), ("q", "2.1")])
    w = 2 * math.pi * 5200
    assert form.values["l"] == pytest.approx(2.1 * 8200 / w, rel=1e-9)  # 0.527 H
    assert form.values["c"] == pytest.approx(1 / (w * w * form.values["l"]), rel=1e-9)
    assert form.shown == {"l": "527m", "c": "1n78"}
    assert form.line == "Set: R, peak, Q · worked out: L, C"
    assert form.set == {"r": "8k2", "peak": "5k2", "q": "2.1"}
    assert form.stored() == {"r": "8k2", "l": "527m", "c": "1n777"}


def test_a_fourth_says_which_went() -> None:
    form = pickup_form([("r", "8k2"), ("peak", "5k2"), ("q", "2.1"), ("l", "500m")])
    assert (
        form.line == "Set: peak, Q, L · worked out: R, C (R was set first, so it's worked out now)"
    )
    form = pickup_form([("r", "6k38"), ("l", "2.55"), ("c", "151p"), ("peak", "8k")])
    assert form.set == {"r": "6k38", "c": "151p", "peak": "8k"}
    assert form.line.endswith("(L was set first that could go, so it's worked out now)")


def test_typing_into_the_dimmed_box_is_refused() -> None:
    with pytest.raises(PickupError, match=r"Not the peak: L and C give it\."):
        pickup_form([("l", "2.5"), ("c", "150p"), ("peak", "5k")])
    with pytest.raises(PickupError, match="30 kHz"):
        pickup_form([("peak", "50k")])


def test_a_files_set_must_give_its_r_l_and_c() -> None:
    check_set({"r": "6k38", "peak": "8k11", "q": "20.37"}, 6380, 2.55, 151e-12)
    with pytest.raises(PickupError, match="isn't what its set values"):
        check_set({"r": "6k38", "peak": "8k11", "q": "20.37"}, 6380, 5.0, 151e-12)
