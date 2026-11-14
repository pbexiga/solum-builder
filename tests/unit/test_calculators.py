"""`solum.calculators`: Tools → Calculators… (D-319, D-320)."""

import math

import pytest

from solum.calculators import (
    FilterError,
    combine_view,
    corner_hz,
    db_view,
    divider_view,
    effect,
    filter_part_view,
    filter_view,
    level_db,
)


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


# ---- a filter's part from its corner


def test_a_capacitor_from_the_corner_and_the_resistor() -> None:
    """A bass cut at 100 Hz into a 1M input: C = 1 / (2π × 100 × 1M) = 1.59 nF; E12's
    nearest is 1n5, which puts the corner at 106 Hz, 6.1 % high."""
    view = filter_part_view("high", "100", r="1M")
    assert view["find"] == "capacitor"
    assert view["formula"] == "C = 1 / (2 × π × f × R)"
    assert (view["exact"], view["standard"], view["series"]) == ("1.59 nF", "1n5", "E12")
    assert view["filter"]["corner_text"] == "106 Hz" and view["corner_off"] == "+6.1 %"
    assert view["filter"]["c"] == "1n5" and view["filter"]["r"] == "1M"


def test_a_resistor_from_the_corner_and_the_capacitor() -> None:
    # the Tube Screamer's treble cut: 720 Hz with 47n wants 4.70 kΩ, which is 4k7
    view = filter_part_view("low", "720", c="47n")
    assert (view["find"], view["exact"], view["standard"]) == ("resistor", "4.7 kΩ", "4k7")
    assert view["corner_off"] == "+0.1 %"  # 4k7 itself gives 720.5 Hz
    # 1 kHz with 47n wants 3.39 kΩ: E12's nearest is 3k3, E24's 3k3 too, E6's 3k3
    assert [
        filter_part_view("low", "1k", c="47n", series=s)["standard"] for s in ("E12", "E24", "E6")
    ] == ["3k3"] * 3


@pytest.mark.parametrize(
    ("args", "says"),
    [
        (("high", "100", "1M", "1n"), "leave the other blank"),
        (("high", "100", "", ""), "leave the other blank"),
        (("high", "0", "1M", ""), "corner frequency must be above 0"),
    ],
)
def test_finding_a_part_needs_exactly_one(args: tuple[str, str, str, str], says: str) -> None:
    with pytest.raises(FilterError, match=says):
        filter_part_view(*args)
    with pytest.raises(FilterError, match="Choose one of E12"):
        filter_part_view("high", "100", r="1M", series="E3")


# ---- voltage divider


def test_a_divider_and_what_it_feeds() -> None:
    """9 V through 10k and 10k: 4.5 V, 450 µA, and it looks like 5k to what it feeds. A
    100k load: 10k ‖ 100k = 9.09k, so 9 × 9.09 / 19.09 = 4.29 V, 4.8 % down."""
    view = divider_view("9", "10k", "10k")
    assert view["middle"] == "4.5 V"
    assert view["working"] == "9 V × 10 kΩ / (10 kΩ + 10 kΩ) = 4.5 V"
    assert (view["current"], view["source"]) == ("450 µA", "5 kΩ")
    assert view["holds"] == (
        "It holds within 1 % for anything above 495 kΩ on its middle, and 10 % above 45 kΩ."
    )
    assert "sag" not in view
    loaded = divider_view("9V", "10k", "10k", load="100k")
    assert loaded["loaded"] == "4.29 V"
    assert loaded["sag"] == "The load pulls the middle down 4.8 %, from 4.5 V to 4.29 V."


def test_a_divider_refuses_what_it_cant_use() -> None:
    with pytest.raises(FilterError, match=r"The top resistor must be above 0\."):
        divider_view("9", "0", "10k")
    with pytest.raises(FilterError, match="volts"):
        divider_view("9F", "10k", "10k")


# ---- parallel and series


def test_values_combined_both_ways() -> None:
    """10k and 22k: 32k in series, 10 × 22 / 32 = 6.88k in parallel. Capacitors the other
    way round: two 100n make 200n in parallel and 50n in series."""
    r = combine_view("resistor", values="10k, 22k")["totals"]
    assert r == {"listed": "10k, 22k", "series": "32 kΩ", "parallel": "6.88 kΩ"}
    c = combine_view("capacitor", values="100n;100n")["totals"]
    assert (c["series"], c["parallel"]) == ("50 nF", "200 nF")


def test_a_value_made_from_standard_parts() -> None:
    """6k5 isn't in E12: one 6k8 is 4.6 % high; 4k7 and 1k8 in series make it exactly; a
    pair in parallel comes within a fraction of a percent."""
    make = combine_view("resistor", target="6k5")["make"]
    assert (make["value"], make["series"]) == ("6.5 kΩ", "E12")
    one, added, parallel = make["options"]
    assert one == {"how": "one 6k8", "makes": "6.8 kΩ", "off": "+4.6 %"}
    assert added == {"how": "4k7 and 1k8 in series", "makes": "6.5 kΩ", "off": "0 %"}
    assert parallel["how"].endswith("in parallel")
    assert abs(float(parallel["off"].replace("\u2212", "-").rstrip(" %"))) < 0.5
    # capacitors add in parallel: 150n is 100n and 47n... or the nearest E12 pair
    caps = combine_view("capacitor", target="150n")["make"]["options"]
    assert caps[0] == {"how": "one 150n", "makes": "150 nF", "off": "0 %"}
    assert caps[1]["how"].endswith("in parallel") and caps[2]["how"].endswith("in series")


def test_combining_needs_something_to_do() -> None:
    with pytest.raises(FilterError, match="List some resistor values"):
        combine_view("resistor")
    with pytest.raises(FilterError, match="at most 6"):
        combine_view("resistor", values="1k,1k,1k,1k,1k,1k,1k")
    with pytest.raises(FilterError, match="Choose resistors or capacitors"):
        combine_view("inductor", values="1m")


# ---- decibels


def test_decibels_and_ratios_either_way() -> None:
    """+22 dB is 10^(22/20) = 12.6 times; twice is +6.0 dB, half −6.0 dB; a 0.3 V signal
    through +20 dB comes out at 3 V."""
    assert db_view(db="22") == {
        "db": "+22.0 dB",
        "times": "12.6",
        "working": "20 × log10(12.6) = +22.0 dB",
    }
    assert db_view(times="2")["db"] == "+6.0 dB"
    assert db_view(times="0.5x")["db"] == "\u22126.0 dB"
    assert db_view(db="-6 dB")["times"] == "0.501"
    assert db_view(db="20", volts="0.3")["out"] == "300 mV in, 3 V out"


@pytest.mark.parametrize(
    ("args", "says"),
    [
        ({}, "not both"),
        ({"db": "6", "times": "2"}, "not both"),
        ({"times": "0"}, "above 0"),
        ({"db": "loud"}, "Couldn't read 'loud' as decibels"),
    ],
)
def test_decibels_refuse_what_they_cant_use(args: dict[str, str], says: str) -> None:
    with pytest.raises(FilterError, match=says):
        db_view(**args)
