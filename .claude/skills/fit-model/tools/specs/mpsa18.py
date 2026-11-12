"""MPSA18 (onsemi sheet, Rev. 1): hFE from the table's typicals (D-163). See its note."""

ONA18 = "onsemi MPSA18 data sheet, Rev. 1 (March 2001, MPSA18/D)"
T = lambda sheet, what: f"{sheet}, Electrical Characteristics: {what}"  # noqa: E731
CEN = "Central Semiconductor MPSA18 data sheet (R0, 3 February 2012)"

# Electrical Characteristics, ON characteristics: hFE typical at VCE = 5 V (pulsed)
HFE_TABLE = [(0.01, 580.0), (0.1, 850.0), (1.0, 1100.0), (10.0, 1150.0)]

PARTS = {
    "MPSA18": dict(
        id="MPSA18",
        polarity="NPN",
        maker="onsemi",
        desc="MPSA18 high-gain, low-noise NPN (hFE 500-1500 at 10 mA; VCEO 45 V), our fit to "
        "onsemi's sheet",
        url="https://www.amstzone.org/MPSA18-OnSemi.pdf",
        sheet=ONA18,
        retrieved="2026-11-02",
        hfe=(
            "Electrical Characteristics: hFE typical at IC = 10 µA, 100 µA, 1 mA and 10 mA (VCE "
            "= 5 V)",
            5.0,
            HFE_TABLE,
        ),
        note=(
            "The hFE points are the table's typicals (580 at 10 µA, 850 at 100 µA, 1100 at 1 "
            "mA, 1150 at 10 mA, "
            "VCE = 5 V). Figure 8 draws the gain normalised; its 25 °C curve rises 4.6 times "
            "from 10 µA to 10 "
            "mA "
            "(0.571 to 2.647) against the table's 2 times, so no scaling of it meets the "
            "table's minimums "
            "(400 at 10 µA, 500 at 100 µA) and the 1500 maximum at 10 mA together: the table "
            "wins. The fit is "
            "given the four table points as they are, so no hFE point is held out. VBE and "
            "VCE(sat) are fitted "
            "to 50 mA; above it the card's VCE(sat) runs high (122 against the curve's 107 mV "
            "at 70 mA): "
            "Gummel-Poon has no quasi-saturation, and fitting on to 98 mA put 30 mA 9.5 mV low "
            "instead"
        ),
        hfe_table=True,
        vbe=(
            "Figure 9. “On” Voltages: VBE @ VCE = 5.0 V (TJ = 25 °C)",
            5.0,
            [
                (0.01044, 0.49),
                (0.02, 0.4983),
                (0.05, 0.5167),
                (0.1, 0.5339),
                (0.2, 0.5524),
                (0.5, 0.5767),
                (1, 0.595),
                (2, 0.6117),
                (5, 0.6377),
                (10, 0.6591),
                (20, 0.6822),
                (50, 0.7156),
                (97.9, 0.745),
            ],
        ),
        vcs=(
            "Figure 9: VCE(sat) @ IC/IB = 10 (TJ = 25 °C)",
            10.0,
            [
                (0.01022, 0.01499),
                (0.1, 0.015),
                (0.5, 0.0183),
                (1, 0.02),
                (2, 0.0217),
                (5, 0.0283),
                (10, 0.0384),
                (20, 0.055),
                (30, 0.0683),
                (50, 0.0897),
                (70, 0.1067),
                (97.9, 0.13),
            ],
        ),
        cib=(
            "Figure 11. Capacitance (Cib, TJ = 25 °C)",
            [
                (0.1024, 7.141),
                (0.2, 6.902),
                (0.3, 6.697),
                (0.5, 6.35),
                (0.7, 6.068),
                (1, 5.735),
                (1.5, 5.243),
                (2, 4.828),
                (3, 4.145),
                (4, 3.563),
                (4.742, 3.217),
            ],
        ),
        cob=(
            "Figure 11 (Cob)",
            [
                (0.1008, 4.682),
                (0.2, 4.419),
                (0.3, 4.211),
                (0.5, 3.919),
                (0.7, 3.664),
                (1, 3.398),
                (1.5, 3.074),
                (2, 2.865),
                (3, 2.539),
                (4, 2.316),
                (5, 2.136),
                (7, 1.852),
                (10, 1.578),
                (15, 1.288),
                (20, 1.182),
                (30, 1.106),
                (43.84, 1.079),
            ],
        ),
        vaf=(
            float("inf"),
            "the sheet gives no output admittance or output curves, so none is set (ngspice's "
            "default)",
        ),
        ft=(
            160e6,
            1e-3,
            4.4,
            "Electrical Characteristics: fT 160 MHz typical at IC = 1 mA, VCE = 5 V (VCB ≈ 4.4 V; "
            "Figure 12 reads 167 MHz there)",
        ),
        checks=[
            (
                "hfe",
                {"ic": 1e-5, "vce": 5.0},
                {"min": 400.0, "source": T(ONA18, "hFE at IC = 10 µA, VCE = 5 V")},
            ),
            (
                "hfe",
                {"ic": 1e-4, "vce": 5.0},
                {"min": 500.0, "source": T(ONA18, "hFE at IC = 100 µA, VCE = 5 V")},
            ),
            (
                "hfe",
                {"ic": 1e-3, "vce": 5.0},
                {"min": 500.0, "source": T(ONA18, "hFE at IC = 1 mA, VCE = 5 V")},
            ),
            (
                "hfe",
                {"ic": 1e-2, "vce": 5.0},
                {"min": 500.0, "max": 1500.0, "source": T(ONA18, "hFE at IC = 10 mA, VCE = 5 V")},
            ),
            (
                "vce_sat",
                {"ic": 1e-2, "ib": 5e-4},
                {"max": 0.2, "source": T(ONA18, "VCE(sat) at IC = 10 mA, IB = 0.5 mA")},
            ),
            (
                "vce_sat",
                {"ic": 5e-2, "ib": 5e-3},
                {"max": 0.3, "source": T(ONA18, "VCE(sat) at IC = 50 mA, IB = 5 mA")},
            ),
            (
                "vbe",
                {"ic": 1e-3, "vce": 5.0},
                {"max": 0.7, "source": T(ONA18, "VBE(on) at IC = 1 mA, VCE = 5 V")},
            ),
        ],
        held=[0.3, 3.0, 30.0],
        ratings={"vceo": 45.0, "ic": 0.2},
        rating_sources={
            "vceo": f"{ONA18}, Maximum ratings: VCEO 45 V (the same in {CEN})",
            "ic": f"{ONA18}, Maximum ratings: IC 200 mA continuous (the same in {CEN})",
        },
        package={
            "name": "TO-92 (EBC)",
            "pins": {"E": 1, "B": 2, "C": 3},
            "source": f"{ONA18}, page 1 pinout and page 5 (CASE 29-11, STYLE 1: 1 emitter, 2 "
            "base, 3 collector)",
        },
    ),
}
