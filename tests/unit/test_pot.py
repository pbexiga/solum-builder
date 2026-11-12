import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.circuit.pot import MIN_RESISTANCE, TAPERS, pot_resistances, taper_fraction


@pytest.mark.parametrize(
    ("rotation", "taper", "fraction"),
    [
        (0.5, "B", 0.5),
        (0.25, "B", 0.25),
        (0.5, "A", 0.1),
        (0.75, "A", 0.55),  # halfway along the second segment: 0.1 + 0.9 / 2
        (0.5, "C", 0.9),
        (0.5, "W", 0.5),
        (0.1, "W", 0.28),
        (1.0, "A", 1.0),
    ],
)
def test_taper_fraction(rotation: float, taper: str, fraction: float) -> None:
    assert taper_fraction(rotation, taper) == pytest.approx(fraction)


def test_halves_sum_to_the_track() -> None:
    low, high = pot_resistances(100e3, 0.5, "A")
    assert (low, high) == (pytest.approx(10e3), pytest.approx(90e3))


def test_ends_never_reach_zero_ohms() -> None:
    assert pot_resistances(500e3, 0.0, "A") == (MIN_RESISTANCE, pytest.approx(500e3))
    assert pot_resistances(500e3, 1.0, "A") == (pytest.approx(500e3), MIN_RESISTANCE)


@given(st.sampled_from(sorted(TAPERS)), st.floats(0, 1), st.floats(0, 1))
def test_tapers_are_monotonic(taper: str, a: float, b: float) -> None:
    lo, hi = sorted((a, b))
    assert taper_fraction(lo, taper) <= taper_fraction(hi, taper)


@given(st.floats(0, 1))
def test_c_mirrors_a(x: float) -> None:
    assert taper_fraction(x, "C") == pytest.approx(1 - taper_fraction(1 - x, "A"))


def test_bad_inputs() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        taper_fraction(1.5)
    with pytest.raises(ValueError, match="Unknown taper"):
        taper_fraction(0.5, "Z")
