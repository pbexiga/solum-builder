import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.units import (
    E_SERIES,
    format_quantity,
    format_value,
    parse_spice_number,
    parse_value,
    series_values,
    signed_db,
    snap_to_series,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4k7", 4700.0),
        ("2M2", 2.2e6),
        ("22n", 22e-9),
        ("100p", 100e-12),
        ("1µ", 1e-6),  # micro sign U+00B5
        ("1μ", 1e-6),  # Greek mu U+03BC
        ("1u", 1e-6),
        ("10uF", 10e-6),
        ("0.047u", 47e-9),
        ("0.22µF", 220e-9),
        ("470pF", 470e-12),
        ("4R7", 4.7),
        ("100R", 100.0),
        ("1M", 1e6),
        ("1Meg", 1e6),
        ("1m", 1e-3),
        ("1.5k", 1500.0),
        ("10K", 1e4),
        ("100kΩ", 1e5),
        ("1kohm", 1e3),
        ("4.5V", 4.5),
        ("4.7 kΩ", 4700.0),
        ("1kHz", 1e3),
        ("20m", 0.02),
        ("1e3", 1000.0),
        ("-0.6", -0.6),
        (" 4k7 ", 4700.0),
        ("0", 0.0),
        ("1f", 1e-15),
    ],
)
def test_parse_value(text: str, expected: float) -> None:
    assert parse_value(text) == pytest.approx(expected, rel=1e-12)


def test_parse_numbers_pass_through() -> None:
    assert parse_value(4700) == 4700.0
    assert parse_value(2.2e-8) == pytest.approx(2.2e-8)


@pytest.mark.parametrize("bad", ["", "k", "4k7k", "4.7k7", "1e3k", "abc", "1 0k", "nan", "1x"])
def test_parse_rejects_with_plain_message(bad: str) -> None:
    with pytest.raises(ValueError, match=r"value|styles|exponent|finite"):
        parse_value(bad)


@pytest.mark.parametrize("bad", [True, float("inf"), float("nan")])
def test_parse_rejects_non_values(bad: float) -> None:
    with pytest.raises(ValueError):
        parse_value(bad)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (4700.0, "4k7"),
        (2.2e6, "2M2"),
        (22e-9, "22n"),
        (100e-12, "100p"),
        (1e-6, "1µ"),
        (1e6, "1M"),
        (1000.0, "1k"),
        (1500.0, "1k5"),
        (470.0, "470"),
        (4.5, "4.5"),
        (0.6, "600m"),
        (0.0, "0"),
        (-0.6, "-600m"),
        (220e-9, "220n"),
        (4990.0, "4k99"),
        (999.6, "1k"),  # rounds up into the next prefix
    ],
)
def test_format_value(value: float, text: str) -> None:
    assert format_value(value) == text


_PREFIXES = ["p", "n", "µ", "m", "", "k", "M"]


@st.composite
def canonical_values(draw: st.DrawFn) -> str:
    """Strings in format_value's own style: 1-3 significant digits and a prefix."""
    digits = str(draw(st.integers(1, 999)))
    split = draw(st.integers(1, len(digits)))
    whole, frac = digits[:split], digits[split:].rstrip("0")
    prefix = draw(st.sampled_from(_PREFIXES))
    if not frac:
        return f"{whole}{prefix}"
    return f"{whole}{prefix}{frac}" if prefix else f"{whole}.{frac}"


@given(canonical_values())
def test_format_parse_round_trip(text: str) -> None:
    assert format_value(parse_value(text)) == text


@given(st.floats(min_value=1e-14, max_value=1e9, allow_nan=False))
def test_parse_of_format_is_within_rounding(x: float) -> None:
    assert parse_value(format_value(x)) == pytest.approx(x, rel=5e-3)


@pytest.mark.parametrize(
    ("value", "series", "expected"),
    [
        (5000.0, "E12", 4700.0),
        (5300.0, "E12", 5600.0),
        (9500.0, "E12", 10000.0),  # closer to the next decade
        (51e3, "E24", 51e3),
        (48e-9, "E6", 47e-9),
        (1.0, "E12", 1.0),
    ],
)
def test_snap_to_series(value: float, series: str, expected: float) -> None:
    assert snap_to_series(value, series) == expected


def test_snap_results_are_exact_series_members() -> None:
    assert snap_to_series(3.3e-9 * 1.01) == 3.3e-9
    assert all(len(v) in (6, 12, 24, 96) for k, v in E_SERIES.items() if k.startswith("E"))


def test_pot_series() -> None:
    assert series_values(1e3, 1e6, "pot") == [
        1e3, 2e3, 2.5e3, 5e3, 1e4, 2e4, 2.5e4, 5e4, 1e5, 2e5, 2.5e5, 5e5, 1e6
    ]  # fmt: skip
    assert snap_to_series(240e3, "pot") == 250e3


@pytest.mark.parametrize("bad", [0.0, -1.0, float("inf")])
def test_snap_rejects_non_positive(bad: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        snap_to_series(bad)


def test_series_values_in_a_range() -> None:
    assert series_values(1000, 2200, "E6") == [1000.0, 1500.0, 2200.0]
    assert series_values(8e-9, 12e-9) == [8.2e-9, 10e-9, 12e-9]  # E12, ends inclusive
    assert series_values(4700, 4700) == [4700.0]
    assert len(series_values(1e3, 1e6)) == 37  # three decades of E12, plus 1M


@given(st.floats(1e-12, 1e7), st.floats(1.0, 1000.0))
def test_series_values_are_sorted_members(low: float, ratio: float) -> None:
    values = series_values(low, low * ratio)
    assert values == sorted(values)
    assert all(snap_to_series(v) == pytest.approx(v) for v in values)
    assert all(low * (1 - 1e-9) <= v <= low * ratio * (1 + 1e-9) for v in values)


@pytest.mark.parametrize(("low", "high"), [(0.0, 1.0), (2.0, 1.0), (1.0, float("inf"))])
def test_series_values_rejects_bad_ranges(low: float, high: float) -> None:
    with pytest.raises(ValueError, match="needs 0 < low"):
        series_values(low, high)


def test_snap_rejects_unknown_series() -> None:
    with pytest.raises(ValueError, match="Unknown series"):
        snap_to_series(1.0, "E7")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1.434K", 1434.0), ("5.16M", 5.16e-3), ("1Meg", 1e6), ("4.352E-9", 4.352e-9),
     ("100mA", 0.1), ("25", 25.0), ("2.3m", 2.3e-3), ("-.6", -0.6), ("10p", 1e-11)],
)  # fmt: skip
def test_parse_spice_number(text: str, expected: float) -> None:
    assert parse_spice_number(text) == pytest.approx(expected)


def test_parse_spice_number_rejects_words() -> None:
    with pytest.raises(ValueError, match="SPICE number"):
        parse_spice_number("PHILIPS")


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (0.0012, "A", "1.2 mA"),
        (4.5, "V", "4.5 V"),
        (4700.0, "Ω", "4.7 kΩ"),
        (-0.00045, "A", "-450 µA"),
        (2.026e-3, "W", "2.03 mW"),
        (0.0, "V", "0 V"),
        (1e-20, "A", "1.00e-20 A"),
        (1e6, "Ω", "1 MΩ"),
    ],
)
def test_format_quantity(value: float, unit: str, text: str) -> None:
    assert format_quantity(value, unit) == text


@pytest.mark.parametrize(
    ("text", "unit", "expected"),
    [("22nF", "F", 22e-9), ("4k7Ω", "Ω", 4700.0), ("4k7 ohms", "Ω", 4700.0), ("10u", "F", 10e-6)],
)
def test_parse_with_the_parts_unit(text: str, unit: str, expected: float) -> None:
    assert parse_value(text, unit) == pytest.approx(expected)


def test_parse_refuses_another_unit() -> None:
    """D-164: a unit after the value must be the part's."""
    with pytest.raises(ValueError, match=r"'4k7F' is in farads \(F\), but this value is in ohms"):
        parse_value("4k7F", "Ω")
    assert parse_value("4k7F") == pytest.approx(4700.0)  # with no unit asked for: as before


def test_lowercase_f_after_a_prefix_is_farads() -> None:
    """10uf and 100pf are how builders write them; a bare 10f is still femto (D-164)."""
    assert parse_value("10uf", "F") == pytest.approx(10e-6)
    assert parse_value("100pf") == pytest.approx(100e-12)
    assert parse_value("10f") == pytest.approx(10e-15)
    with pytest.raises(ValueError, match="is in farads"):
        parse_value("10uf", "Ω")


@pytest.mark.parametrize(
    ("db", "text"),
    [
        (3.14, "+3.1 dB"),
        (-0.4, "\u22120.4 dB"),
        (0.0, "+0.0 dB"),
        (-0.04, "+0.0 dB"),
        (-12, "\u221212.0 dB"),
    ],
)
def test_signed_db(db: float, text: str) -> None:
    assert signed_db(db) == text
