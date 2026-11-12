"""Part markings and the unit converter (D-095): numbers checked by hand against the
IEC 60062 colour code and the EIA capacitor code."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from solum.markings import (
    QUANTITIES,
    MarkingError,
    bands_value,
    cap_code,
    conversions,
    in_series,
    neighbours,
    plain,
    read_cap_code,
    resistor_bands,
    tables,
    value_view,
)
from solum.units import E_SERIES, parse_value


def test_e96_is_the_iec_formula() -> None:
    assert len(E_SERIES["E96"]) == 96
    assert list(E_SERIES["E96"]) == [round(10 ** (i / 96), 2) for i in range(96)]


@pytest.mark.parametrize(
    ("ohms", "bands", "colours"),
    [
        (4700, 4, ["yellow", "violet", "red"]),
        (10, 4, ["brown", "black", "black"]),
        (1e6, 4, ["brown", "black", "green"]),
        (0.47, 4, ["yellow", "violet", "silver"]),
        (4.7, 4, ["yellow", "violet", "gold"]),
        (4700, 5, ["yellow", "violet", "black", "brown"]),
        (4120, 5, ["yellow", "brown", "red", "brown"]),
        (4120, 4, None),  # three significant figures need five bands
    ],
)
def test_resistor_bands(ohms: float, bands: int, colours: list[str] | None) -> None:
    assert resistor_bands(ohms, bands) == colours


def test_bands_read_back() -> None:
    assert bands_value(["yellow", "violet", "red", "gold"]) == (4700, 5.0)
    assert bands_value(["Brown", "Black", "Black", "Red", "Brown"]) == (10e3, 1.0)
    assert bands_value(["red", "red", "gold"]) == (pytest.approx(2.2), 20.0)  # no tolerance band
    assert bands_value(["orange", "orange", "brown", "gold", "brown"]) == (pytest.approx(33.1), 1.0)
    assert bands_value(["gray", "purple", "orange", "silver"]) == (87e3, 10.0)  # spelt the US way
    with pytest.raises(MarkingError, match="gold can't be a digit band"):
        bands_value(["gold", "violet", "red", "gold"])
    with pytest.raises(MarkingError, match="3 to 6 bands"):
        bands_value(["red", "red"])


@given(st.sampled_from(E_SERIES["E24"]), st.integers(-1, 6))
def test_bands_round_trip(base: float, power: int) -> None:
    ohms = float(f"{base}e{power}")
    colours = resistor_bands(ohms, 4)
    assert colours is not None
    assert bands_value([*colours, "gold"])[0] == pytest.approx(ohms)


def test_series_membership_and_neighbours() -> None:
    assert in_series(4700) == ["E6", "E12", "E24"]  # not E96: it has 4.64 and 4.75
    assert in_series(4990) == ["E96"]
    assert in_series(4100) == []  # the 4k1 example: no series has it
    assert neighbours(4100, "E24") == (pytest.approx(3900), pytest.approx(4300))
    assert neighbours(4100, "E96") == (pytest.approx(4020), pytest.approx(4120))
    assert neighbours(4700, "E12") == (pytest.approx(4700), pytest.approx(4700))
    assert neighbours(9.9e3, "E12") == (pytest.approx(8200), pytest.approx(10e3))  # next decade


@pytest.mark.parametrize(
    ("farads", "code"),
    [(22e-9, "223"), (100e-9, "104"), (47e-12, "470"), (1e-6, "105"), (4.7e-12, "4p7"),
     (10e-12, "100"), (4.75e-9, None), (100e-6, None)],
)  # fmt: skip
def test_cap_code(farads: float, code: str | None) -> None:
    assert cap_code(farads) == code


def test_read_cap_code() -> None:
    assert read_cap_code("104").farads == pytest.approx(100e-9)
    c = read_cap_code("223j")
    assert (c.farads, c.tolerance) == (pytest.approx(22e-9), "±5 %")
    assert read_cap_code("47").farads == pytest.approx(47e-12)
    assert read_cap_code("4p7").farads == pytest.approx(4.7e-12)
    assert read_cap_code("229").farads == pytest.approx(2.2e-12)  # 9 is x0.1
    with pytest.raises(MarkingError, match="Capacitor codes look like"):
        read_cap_code("hello")


def test_plain_numbers() -> None:
    assert plain(22000) == "22 000"
    assert plain(0.022) == "0.022"
    assert plain(2.2e-8, 6) == "0.000000022"
    assert plain(1234567, 7) == "1 234 567"
    assert plain(-4.7) == "-4.7"
    assert plain(0) == "0"


def test_conversions() -> None:
    assert conversions(22e-9, "F") == [
        ("pF", "22 000"), ("nF", "22"), ("µF", "0.022"), ("F", "0.000000022"),
    ]  # fmt: skip
    assert conversions(4700, "Ω") == [("Ω", "4 700"), ("kΩ", "4.7"), ("MΩ", "0.0047")]
    with pytest.raises(MarkingError, match="No converter"):
        conversions(1, "furlong")


def test_tables_for_the_pickers() -> None:
    t = tables()
    colours = {c["name"]: c for c in t["colours"]}  # type: ignore[attr-defined]
    assert colours["red"] == {"name": "red", "digit": 2, "power": 2, "times": "\u00d7100",
                              "tolerance": 2.0, "letter": "G"}  # fmt: skip
    assert colours["gold"] == {"name": "gold", "digit": None, "power": -1, "times": "\u00d70.1",
                               "tolerance": 5.0, "letter": "J"}  # fmt: skip
    assert colours["orange"]["times"] == "\u00d71k"
    assert colours["white"]["tolerance"] is None
    # every multiplier, the rarely used ones too (the user: "they are real")
    assert [c["times"] for c in t["colours"]] == [  # type: ignore[attr-defined]
        "\u00d71", "\u00d710", "\u00d7100", "\u00d71k", "\u00d710k", "\u00d7100k",
        "\u00d71M", "\u00d710M", "\u00d7100M", "\u00d71G", "\u00d70.1", "\u00d70.01",
    ]  # fmt: skip
    letters = {c["name"]: c["letter"] for c in t["colours"]}  # type: ignore[attr-defined]
    assert letters == {
        "black": None, "brown": "F", "red": "G", "orange": None, "yellow": None, "green": "D",
        "blue": "C", "violet": "B", "grey": None, "white": None, "gold": "J", "silver": "K",
    }  # fmt: skip
    # the card's examples: green blue yellow gold, and red orange violet black brown
    assert t["examples"] == [
        {"bands": ["green", "blue", "yellow", "gold"], "short": "560k", "tolerance": 5.0},
        {"bands": ["red", "orange", "violet", "black", "brown"], "short": "237", "tolerance": 1.0},
    ]
    quantities = {q["unit"]: q for q in t["quantities"]}  # type: ignore[attr-defined]
    assert quantities["F"]["name"] == "Capacitance"
    assert quantities["Ω"]["example"] == "e.g. 4k7, 4700, 2M2"


def test_every_converter_example_reads_in_its_own_unit() -> None:
    for unit, (_, _, examples) in QUANTITIES.items():
        for text in examples.split(", "):
            assert value_view(parse_value(text), unit)["rows"], (unit, text)
