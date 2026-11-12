"""PNP parts fitted to Fairchild's sheets (D-163): the 2N3906 and the 2N5087.

The 2N5087 comes from data/spec-sheets/2N5086-2N5087_Fairchild.pdf: 2N5087_Fairchild.pdf (and the
rs-online URL it came from) is Fairchild's BC807/BC808 sheet, not a 2N5087 one."""

FS3906 = "Fairchild 2N3906/MMBT3906/PZT3906 data sheet, Rev A (2001)"
T = lambda sheet, what: f"{sheet}, Electrical Characteristics: {what}"  # noqa: E731

PARTS = {
    "2N3906": dict(
        id="2N3906",
        polarity="PNP",
        maker="onsemi (Fairchild)",
        desc="2N3906 general-purpose PNP (switching and small-signal; pairs with the 2N3904), "
        "our fit to Fairchild's "
        "sheet",
        url="https://sy-dep-epc-lpc.web.cern.ch/components/datasheets/epc-lpc%20(converters)/2N3906%20Transistor%20(FAIRCHILD).pdf",
        sheet=FS3906,
        retrieved="2026-10-29",
        hfe=(
            "Typical Pulsed Current Gain vs Collector Current (page 3; the 25 °C curve, VCE = 1 V)",
            1.0,
            [
                (0.1, 109.0),
                (2.13, 131.8),
                (4.163, 136.3),
                (6.201, 137.5),
                (10.32, 138.2),
                (14.4, 137.3),
                (20.53, 134.7),
                (30.73, 129.2),
                (42.73, 122.4),
                (51.05, 117.7),
                (61.27, 111.8),
                (70.9, 105.7),
                (81.6, 99.29),
                (89.63, 94.34),
                (100.0, 87.5),
            ],
        ),
        vbe=(
            "Base Emitter ON Voltage vs Collector Current (page 3; the 25 °C curve, VCE = 1 V)",
            1.0,
            [
                (0.1, 0.6),
                (0.5, 0.6423),
                (1.0, 0.6612),
                (5.006, 0.7047),
                (10.0, 0.7259),
                (25.0, 0.7565),
            ],
        ),
        vcs=(
            "Collector-Emitter Saturation Voltage vs Collector Current (page 3; β = 10, the 25 "
            "°C curve: the middle "
            "one, "
            "its label's arrow ends on it)",
            10.0,
            [
                (1.0, 0.0419),
                (2.339, 0.04331),
                (5.006, 0.04578),
                (10.33, 0.05106),
                (15.67, 0.05633),
                (19.66, 0.06021),
                (25.06, 0.06585),
                (31.69, 0.07254),
                (39.75, 0.08099),
                (49.06, 0.09085),
                (61.04, 0.1039),
                (71.76, 0.1158),
                (81.02, 0.1264),
                (100.8, 0.15),
                (125.0, 0.1796),
                (150.6, 0.212),
                (178.5, 0.2497),
                (200.0, 0.2796),
            ],
        ),
        cib=(
            "Common-Base Open Circuit Input and Output Capacitance vs Reverse Bias Voltage "
            "(page 3, Cibo)",
            [
                (0.1, 7.698),
                (0.1524, 7.461),
                (0.2385, 7.171),
                (0.3549, 6.868),
                (0.5299, 6.513),
                (0.7911, 6.118),
                (1.096, 5.737),
                (1.473, 5.368),
                (1.986, 4.987),
                (2.597, 4.632),
                (3.396, 4.263),
                (4.192, 3.96),
                (4.985, 3.708),
            ],
        ),
        cob=(
            "the same figure (Cobo)",
            [
                (0.1, 9.053),
                (0.1508, 8.618),
                (0.2329, 8.092),
                (0.3316, 7.605),
                (0.4641, 7.092),
                (0.5847, 6.684),
                (0.6906, 6.382),
                (0.8939, 5.895),
                (1.247, 5.329),
                (2.46, 4.211),
                (3.316, 3.696),
                (4.486, 3.192),
                (5.729, 2.808),
                (7.145, 2.543),
                (8.583, 2.344),
                (10.0, 2.252),
            ],
        ),
        vaf=(
            1e-3 / 29.98e-6 - 10,
            "from the Output Admittance figure (page 5): hoe 30.0 µS at 1 mA, VCE = 10 V, "
            "so VAF = IC/hoe − VCE",
        ),
        ft=(
            250e6,
            10e-3,
            20.0 - 0.726,
            "the Electrical Characteristics table: fT 250 MHz minimum at IC = 10 mA, "
            "VCE = 20 V (the sheet draws no fT figure, so its minimum is used)",
        ),
        checks=[
            (
                "hfe",
                {"ic": 1e-4, "vce": 1.0},
                {"min": 60.0, "source": T(FS3906, "hFE at IC = 0.1 mA, VCE = 1.0 V")},
            ),
            (
                "hfe",
                {"ic": 1e-3, "vce": 1.0},
                {"min": 80.0, "source": T(FS3906, "hFE at IC = 1.0 mA, VCE = 1.0 V")},
            ),
            (
                "hfe",
                {"ic": 1e-2, "vce": 1.0},
                {"min": 100.0, "max": 300.0, "source": T(FS3906, "hFE at IC = 10 mA, VCE = 1.0 V")},
            ),
            (
                "hfe",
                {"ic": 5e-2, "vce": 1.0},
                {"min": 60.0, "source": T(FS3906, "hFE at IC = 50 mA, VCE = 1.0 V")},
            ),
            (
                "hfe",
                {"ic": 0.1, "vce": 1.0},
                {"min": 30.0, "source": T(FS3906, "hFE at IC = 100 mA, VCE = 1.0 V")},
            ),
            (
                "vce_sat",
                {"ic": 1e-2, "ib": 1e-3},
                {"max": 0.25, "source": T(FS3906, "VCE(sat) at IC = 10 mA, IB = 1.0 mA")},
            ),
            (
                "vce_sat",
                {"ic": 5e-2, "ib": 5e-3},
                {"max": 0.4, "source": T(FS3906, "VCE(sat) at IC = 50 mA, IB = 5.0 mA")},
            ),
        ],
        held=[0.3, 3.0, 30.0],
        top_ma=100.0,  # the hFE curve's end; see note
        note=(
            "The VCE(sat) curve runs to 200 mA; the fit stops at 100 mA, where the hFE curve "
            "ends. Fitted to 200 "
            "mA, "
            "the card's nearly straight VCE(sat) (no quasi-saturation in Gummel-Poon) missed "
            "the curve's upturn "
            "by "
            "12 "
            "mV "
            "at 100 mA (137 against 149 mV); stopped at 100 mA it is within 1 mV there. NKF, "
            "the knee's exponent, "
            "ends "
            "at "
            "its bound of 1 to "
            "follow "
            "the "
            "gain's fall past "
            "20 "
            "mA "
            "(138 "
            "at "
            "10 mA, 87.5 at 100 "
            "mA); "
            "with "
            "IKF 0.46 A the card's "
            "current "
            "tops out near IKF/2 "
            "= "
            "0.23 "
            "A, "
            "above the 200 mA "
            "rating"
        ),
    ),
}

FS5087 = "Fairchild 2N5086/2N5087/MMBT5086/MMBT5087 data sheet (1997, Process 62)"
LO5087, HI5087 = 250.0, 800.0  # hFE at IC = 100 µA, VCE = 5 V, 2N5087 (Electrical Characteristics)
# the 25 °C curve at 100 µA (on its drawn straight segment, 205.5 at 10 µA to 203.3 at 2.05 mA)
HFE5087_AT_100UA = 204.5
PARTS["2N5087"] = dict(
    id="2N5087",
    polarity="PNP",
    maker="onsemi (Fairchild)",
    desc="2N5087 low-noise, high-gain PNP (hFE 250-800 at 100 µA; VCEO 50 V), our fit to "
    "Fairchild's sheet",
    url="https://farnell.com/datasheets/59723.pdf",
    sheet=FS5087,
    retrieved="2026-11-02",
    hfe=(
        "Typical Pulsed Current Gain vs Collector Current (page 3; the 25 °C curve, drawn at "
        "VCB = 5 V and "
        "taken here as VCE = 5 V, see note)",
        5.0,
        [
            (0.01, 205.5),
            (2.051, 203.3),
            (4.088, 200.0),
            (6.136, 196.7),
            (10.21, 189.3),
            (14.29, 182.6),
            (20.42, 171.9),
            (30.62, 158.5),
            (40.61, 146.3),
            (50.96, 135.6),
            (63.07, 122.6),
            (75.43, 111.5),
            (87.15, 100.0),
            (100.0, 89.25),
        ],
    ),
    hfe_scale=(LO5087 * HI5087) ** 0.5 / HFE5087_AT_100UA,
    vbe=(
        "Base Emitter ON Voltage vs Collector Current (page 3; the 25 °C curve, VCE = 5 V)",
        5.0,
        [
            (0.1, 0.5925),
            (0.4995, 0.635),
            (0.9999, 0.6537),
            (4.995, 0.6987),
            (10.0, 0.7212),
            (25.0, 0.7575),
        ],
    ),
    vcs=(
        "Collector-Emitter Saturation Voltage vs Collector Current (page 3; β = 10, the 25 °C "
        "curve: the middle "
        "one, "
        "its label's arrow ends on it)",
        10.0,
        [
            (0.1, 0.05219),
            (0.4349, 0.05291),
            (1.103, 0.05402),
            (2.105, 0.05584),
            (5.118, 0.06168),
            (8.112, 0.06752),
            (10.82, 0.07299),
            (15.49, 0.08248),
            (20.19, 0.09233),
            (24.89, 0.1022),
            (30.12, 0.1139),
            (35.11, 0.1252),
            (40.94, 0.138),
            (45.14, 0.1482),
            (50.0, 0.1596),
        ],
    ),
    cib=(
        "Input and Output Capacitance vs Reverse Bias Voltage (page 3, f = 1 MHz, Cibo)",
        [
            (0.0, 7.512),
            (0.8173, 6.488),
            (1.635, 5.78),
            (2.496, 5.17),
            (3.416, 4.708),
            (4.571, 4.317),
            (5.729, 4.098),
            (6.799, 4.0),
            (7.985, 3.805),
        ],
    ),
    cob=(
        "the same figure (Cobo)",
        [
            (0.0, 6.098),
            (0.5545, 5.561),
            (1.401, 4.951),
            (2.233, 4.39),
            (3.226, 3.927),
            (4.307, 3.512),
            (5.538, 3.147),
            (6.828, 2.951),
            (8.0, 2.805),
            (20.0, 2.292),
        ],
    ),
    vaf=(
        float("inf"),
        "the sheet gives no output admittance or output curves, so none is set (ngspice's default)",
    ),
    ft=(
        312.5e6,
        10.43e-3,
        5.0 - 0.7212,
        "Gain Bandwidth Product vs Collector Current (page 4, VCE = 5 V): 312.5 MHz at "
        "10.4 mA, near its 313 MHz peak; the table gives 40 MHz minimum at 500 µA",
    ),
    checks=[
        (
            "hfe",
            {"ic": 1e-4, "vce": 5.0},
            {
                "min": LO5087,
                "max": HI5087,
                "source": T(FS5087, "hFE at IC = 100 µA, VCE = 5.0 V, 2N5087"),
            },
        ),
        (
            "hfe",
            {"ic": 1e-3, "vce": 5.0},
            {"min": 250.0, "source": T(FS5087, "hFE at IC = 1.0 mA, VCE = 5.0 V, 2N5087")},
        ),
        (
            "hfe",
            {"ic": 1e-2, "vce": 5.0},
            {"min": 250.0, "source": T(FS5087, "hFE at IC = 10 mA, VCE = 5.0 V, 2N5087")},
        ),
        (
            "vce_sat",
            {"ic": 1e-2, "ib": 1e-3},
            {"max": 0.3, "source": T(FS5087, "VCE(sat) at IC = 10 mA, IB = 1.0 mA")},
        ),
        (
            "vbe",
            {"ic": 1e-3, "vce": 5.0},
            {"max": 0.85, "source": T(FS5087, "VBE(on) at IC = 1.0 mA, VCE = 5.0 V")},
        ),
    ],
    held=[0.03, 0.3, 3.0, 30.0],
    note=(
        "The sheet draws one typical gain curve for the 2N5086 and 2N5087 "
        f"({HFE5087_AT_100UA:g} "
        "at "
        "100 "
        "µA). Its shape is "
        "kept and its level set to the geometric middle of the 2N5087's 100 µA range "
        f"({LO5087:g} to {HI5087:g}: "
        f"{(LO5087 * HI5087) ** 0.5:.0f}), as for the 2N5088/89 (D-163). The gain figure is "
        "drawn at VCB = 5 "
        "V "
        "and "
        "the "
        "VBE(on) figure at VCE = 5 V; both are fitted at VCE = 5 V. The 0.6-0.7 V between them "
        "makes no difference "
        "to "
        "this card, which has no Early voltage (the sheet gives no output admittance)"
    ),
)
