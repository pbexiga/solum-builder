"""`solum.filters`: Tools → Filter calculator (D-319)."""

import math

import pytest

from solum.filters import FilterError, corner_hz, effect, filter_view, level_db


def test_the_corner_is_one_over_two_pi_r_c() -> None:
    # the guide's Formulas page: 4k7 and 47n give 720 Hz, 22n into 1M gives 7.2 Hz
    assert corner_hz(4700.0, 47e-9) == pytest.approx(720.5, abs=0.1)
    assert corner_hz(1e6, 22e-9) == pytest.approx(7.23, abs=0.01)
    assert corner_hz(1e5, 1e-6) == pytest.approx(1 / (2 * math.pi * 0.1))  # 1.59 Hz


def test_levels_of_a_one_pole_filter() -> None:
    # 3 dB down at the corner, 20 dB a decade beyond it, next to nothing a decade inside
    for kind in ("high", "low"):
        assert level_db(kind, 1000.0, 1000.0) == pytest.approx(-3.01, abs=0.01)
    assert level_db("high", 1000.0, 100.0) == pytest.approx(-20.04, abs=0.01)
    assert level_db("high", 1000.0, 10_000.0) == pytest.approx(-0.04, abs=0.01)
    assert level_db("low", 1000.0, 10_000.0) == pytest.approx(-20.04, abs=0.01)
    assert level_db("low", 1000.0, 100.0) == pytest.approx(-0.04, abs=0.01)


def test_the_users_example_one_micro_and_a_hundred_k() -> None:
    """The user (2026-11-13): 1 µF into 100 kΩ is about 1.6 Hz, so every guitar frequency
    passes; with 10 µF the corner is ten times lower."""
    view = filter_view("high", "100k", "1u", c2="10u")
    first, second = view["filters"]
    assert (first["r"], first["c"], first["corner_text"]) == ("100k", "1µ", "1.59 Hz")
    assert first["working"] == "1 / (2 × π × 100 kΩ × 1 µF) = 1.59 Hz"
    assert first["effect"] == "Far below a guitar's lowest note (82 Hz): the whole guitar passes."
    assert [lv["freq"] for lv in first["levels"]] == ["82 Hz", "1 kHz", "5 kHz"]
    assert [lv["db"] for lv in first["levels"]] == ["0.0 dB", "0.0 dB", "0.0 dB"]
    cut = filter_view("high", "10k", "100n")["filters"][0]  # 159 Hz
    assert [lv["db"] for lv in cut["levels"]] == ["−6.8 dB", "−0.1 dB", "0.0 dB"]
    assert (second["r"], second["c"], second["corner_text"]) == ("100k", "10µ", "159 mHz")
    assert view["change"].startswith("The corner moves 10 times lower, from 1.59 Hz to 159 mHz")


def test_what_a_corner_does_in_words() -> None:
    assert effect("high", 50.0) == (
        "Just under a guitar's lowest note (82 Hz): the lowest notes are down 1.4 dB."
    )
    assert effect("high", 720.0).startswith("Cuts bass: everything below about 720 Hz")
    assert effect("high", 9000.0).startswith("Above what a guitar speaker puts out")
    assert effect("low", 720.0).startswith("Cuts treble: everything above about 720 Hz")
    assert effect("low", 7000.0) == (
        "Just above what a guitar speaker puts out (about 5 kHz): the top is down 1.8 dB."
    )
    assert effect("low", 30_000.0).startswith("Far above what a guitar speaker puts out")
    assert effect("low", 20.0).startswith("Below a guitar's lowest note")


def test_one_filter_has_no_comparison_and_the_same_corner_says_so() -> None:
    assert "change" not in filter_view("low", "4k7", "47n")
    same = filter_view("low", "10k", "100n", r2="100k", c2="10n")
    assert same["change"] == "The same corner: R × C hasn't changed."
    up = filter_view("low", "10k", "100n", r2="1k")
    assert up["change"].startswith("The corner moves 10 times higher, from 159 Hz to 1.59 kHz")


@pytest.mark.parametrize(
    ("args", "says"),
    [
        (("band", "10k", "100n"), "Choose high-pass or low-pass."),
        (("high", "", "100n"), "value"),
        (("high", "4k7F", "100n"), "ohms"),
        (("high", "0", "100n"), "The resistor must be above 0."),
    ],
)
def test_values_it_cant_use_are_refused_in_words(args: tuple[str, str, str], says: str) -> None:
    with pytest.raises(FilterError) as err:
        filter_view(*args)
    assert says in str(err.value)
