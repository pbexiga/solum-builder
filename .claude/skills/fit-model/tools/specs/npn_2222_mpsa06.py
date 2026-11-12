"""2N2222A (from Fairchild's PN2222A sheet) and MPSA06 (onsemi MPSA05/D), D-163."""

T = lambda sheet, what: f"{sheet}, Electrical Characteristics: {what}"  # noqa: E731

FPN = "Fairchild PN2222A/MMBT2222A/PZT2222A data sheet, Rev. A1 (August 2004)"
DIO = "Diotec 2N2222A data sheet (version 2026-03-10)"
ONA06 = "onsemi MPSA05/MPSA06/MPSA55/MPSA56 data sheet, Rev. 2 (January 2006, MPSA05/D)"

PARTS = {
    "2N2222A": dict(
        id="2N2222A",
        polarity="NPN",
        maker="Fairchild (onsemi)",
        desc=(
            "2N2222A general-purpose NPN switch and amplifier (VCEO 40 V), our fit to "
            "Fairchild's PN2222A "
            "sheet: "
            "the PN2222A is the 2N2222A die in a TO-92 case"
        ),
        url="https://ee6131b.mit.edu/document/pn2222a.pdf",
        sheet=FPN,
        hfe=(
            "Figure 1. Typical Pulsed Current Gain vs Collector Current (25 °C, VCE = 5 V)",
            5.0,
            [
                (0.09997, 209.6),
                (10.33, 195.2),
                (20.49, 192.3),
                (30.78, 191.1),
                (51.33, 186.3),
                (71.87, 182.1),
                (102.6, 176.2),
                (143.6, 169.0),
                (204.8, 159.5),
                (255.2, 151.2),
                (305.8, 142.3),
                (354.8, 131.0),
                (396.0, 120.2),
                (450.6, 105.4),
                (502.9, 91.03),
            ],
        ),
        vbe=(
            "Figure 4. Base-Emitter On Voltage vs Collector Current (25 °C, VCE = 5 V; drawn as "
            "straight segments)",
            5.0,
            [
                (0.09996, 0.5396),
                (0.9994, 0.6199),
                (4.999, 0.6697),
                (9.994, 0.6896),
                (24.98, 0.7195),
            ],
        ),
        vcs=(
            "Figure 2. Collector-Emitter Saturation Voltage vs Collector Current (β = 10, 25 °C)",
            10.0,
            [
                (1.0, 0.06133),
                (3.279, 0.05244),
                (5.548, 0.05022),
                (7.83, 0.048),
                (10.09, 0.04844),
                (14.65, 0.04933),
                (19.23, 0.05022),
                (23.81, 0.05111),
                (30.57, 0.05466),
                (39.77, 0.05955),
                (51.06, 0.06533),
                (60.13, 0.0711),
                (69.22, 0.07734),
                (78.61, 0.08266),
                (89.67, 0.08888),
                (106.1, 0.09821),
                (126.0, 0.1107),
                (151.1, 0.1253),
                (203.8, 0.1533),
                (251.0, 0.1778),
                (300.9, 0.2022),
                (351.1, 0.2267),
                (402.2, 0.2498),
                (450.5, 0.272),
                (484.4, 0.2884),
            ],
        ),
        cib=(
            "Figure 6. Emitter Transition and Output Capacitance vs Reverse Bias Voltage (Cte)",
            [
                (0.0999, 21.0),
                (0.2001, 20.0),
                (0.3374, 19.08),
                (0.501, 18.21),
                (0.775, 16.87),
                (1.162, 15.62),
                (1.889, 14.08),
                (2.861, 12.58),
                (4.14, 11.24),
                (5.989, 9.697),
            ],
        ),
        cob=(
            "Figure 6 (Cob)",
            [
                (0.0999, 9.005),
                (0.3002, 7.91),
                (0.5775, 7.083),
                (1.105, 6.278),
                (2.385, 5.363),
                (4.993, 4.602),
                (9.936, 3.977),
                (19.31, 3.396),
                (34.42, 2.949),
                (49.83, 2.703),
            ],
        ),
        vaf=(
            float("inf"),
            "the sheet's output admittance (Figures 10 and 12) is drawn only relative to its "
            "value at "
            "10 mA, 10 V, with no absolute value, so none is set (ngspice's default)",
        ),
        ft=(
            300e6,
            20e-3,
            20.0 - 0.7122,
            "the table's fT, 300 MHz minimum at IC = 20 mA, VCE = 20 V (the sheet draws no fT "
            "figure, so its "
            "minimum is used); VCB = 20 V less VBE(on) 0.71 V read from Figure 4 at 20 mA",
        ),
        checks=[
            (
                "hfe",
                {"ic": 1e-4, "vce": 10.0},
                {"min": 35.0, "source": T(FPN, "hFE at IC = 0.1 mA, VCE = 10 V")},
            ),
            (
                "hfe",
                {"ic": 1e-3, "vce": 10.0},
                {"min": 50.0, "source": T(FPN, "hFE at IC = 1.0 mA, VCE = 10 V")},
            ),
            (
                "hfe",
                {"ic": 1e-2, "vce": 10.0},
                {"min": 75.0, "source": T(FPN, "hFE at IC = 10 mA, VCE = 10 V")},
            ),
            (
                "hfe",
                {"ic": 0.15, "vce": 10.0},
                {
                    "min": 100.0,
                    "max": 300.0,
                    "source": T(FPN, "hFE at IC = 150 mA, VCE = 10 V (pulsed)"),
                },
            ),
            (
                "hfe",
                {"ic": 0.5, "vce": 10.0},
                {"min": 40.0, "source": T(FPN, "hFE at IC = 500 mA, VCE = 10 V (pulsed)")},
            ),
            (
                "vce_sat",
                {"ic": 0.15, "ib": 0.015},
                {
                    "max": 0.3,
                    "source": f"{DIO}, Characteristics: VCEsat at IC = 150 mA, IB = 15 mA",
                    "note": "Fairchild's table gives the same 0.3 V limit but prints its "
                    "condition as 'VCE "
                    "= "
                    "10 "
                    "V' "
                    "with no base current, so Diotec's 2N2222A line is used",
                },
            ),
            (
                "vce_sat",
                {"ic": 0.5, "ib": 0.05},
                {
                    "max": 1.0,
                    "source": f"{DIO}, Characteristics: VCEsat at IC = 500 mA, IB = 50 mA",
                    "note": "Fairchild's table gives the same 1.0 V limit but prints its "
                    "condition as 'VCE "
                    "= "
                    "10 "
                    "V' "
                    "with no base current, so Diotec's 2N2222A line is used",
                },
            ),
        ],
        held=[0.3, 3.0, 30.0],
        top_ma=200.0,
        note=(
            "Fitted to Fairchild's PN2222A sheet: the PN2222A is the 2N2222A die in a TO-92 "
            "case, and the record "
            "keeps "
            "the 2N2222A name. The sheet draws 125 °C, 25 °C and −40 °C curves; the 25 °C ones "
            "are used. Its gain "
            "and "
            "VBE(on) curves are at VCE = 5 V, its table at 10 V (no Early voltage is set, so "
            "they are the same "
            "here). "
            "fT is the table's 300 MHz minimum (no typical figure), so the card is, if "
            "anything, slow above "
            "a few MHz. Fairchild's table prints its VCE(sat) conditions as 'VCE = 10 V'; those "
            "two limits are "
            "checked at Diotec's 2N2222A conditions (IB = IC/10), which give the same limits. "
            "Fitted up to 200 "
            "mA: "
            "above it Gummel-Poon's knee can't follow the gain curve's shape (fitted on to 500 "
            "mA it read 135 "
            "against 143 at 300 mA). This card reads high above 200 mA instead (134 against the "
            "curve's 92 at "
            "500 mA; the table's 40 minimum there still holds); a pedal never runs one there"
        ),
    ),
    "MPSA06": dict(
        id="MPSA06",
        polarity="NPN",
        maker="onsemi",
        desc="MPSA06 80 V general-purpose NPN amplifier (IC 500 mA), our fit to onsemi's "
        "MPSA05/06 sheet",
        url="https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/2576/MPSA05,%2006,%2055,%2056%20Rev2.pdf",
        sheet=ONA06,
        hfe=(
            "Figure 10. MPSA05/06 DC Current Gain (25 °C, VCE = 1.0 V)",
            1.0,
            [
                (0.5041, 93.98),
                (0.757, 104.2),
                (1.134, 115.7),
                (1.72, 128.5),
                (2.646, 141.7),
                (3.825, 153.7),
                (5.555, 166.4),
                (8.099, 178.2),
                (11.66, 190.7),
                (16.2, 201.5),
                (22.49, 211.4),
                (30.76, 219.1),
                (43.73, 222.9),
                (50.67, 224.3),
                (58.32, 224.1),
                (77.19, 220.8),
                (100.0, 213.5),
                (135.1, 194.2),
                (158.7, 175.8),
                (191.4, 154.5),
                (229.4, 135.4),
                (271.9, 118.2),
                (316.3, 102.9),
                (398.0, 79.66),
                (494.3, 61.84),
            ],
        ),
        vbe=(
            'Figure 12. MPSA05/06 "ON" Voltages: VBE(on) at VCE = 1.0 V (25 °C)',
            1.0,
            [
                (0.5117, 0.5708),
                (0.7562, 0.5773),
                (1.13, 0.5854),
                (1.738, 0.595),
                (2.683, 0.6058),
                (5.387, 0.6232),
                (9.926, 0.6409),
                (19.19, 0.66),
                (39.37, 0.6817),
                (51.9, 0.6909),
                (64.99, 0.7006),
                (81.3, 0.7115),
                (102.2, 0.7242),
                (127.2, 0.7344),
                (158.4, 0.7446),
                (197.2, 0.7555),
                (240.8, 0.7675),
                (290.4, 0.7801),
                (347.5, 0.7939),
                (414.7, 0.8089),
                (496.1, 0.8249),
            ],
        ),
        vcs=(
            "Figure 12 (VCE(sat) at IC/IB = 10, 25 °C)",
            10.0,
            [
                (0.5117, 0.06751),
                (0.7674, 0.05999),
                (1.167, 0.05292),
                (1.825, 0.04669),
                (2.876, 0.04166),
                (3.774, 0.03795),
                (4.956, 0.03535),
                (6.275, 0.03341),
                (7.937, 0.03167),
                (10.52, 0.03048),
                (14.2, 0.0295),
                (19.17, 0.0296),
                (26.55, 0.03167),
                (35.6, 0.03402),
                (47.89, 0.03667),
                (61.13, 0.04057),
                (77.07, 0.04667),
                (89.95, 0.05193),
                (106.5, 0.05808),
                (129.1, 0.06477),
                (155.8, 0.07166),
                (193.8, 0.08039),
                (236.8, 0.09092),
                (288.2, 0.1027),
                (350.4, 0.115),
                (417.6, 0.1289),
                (496.1, 0.145),
            ],
        ),
        cib=(
            "Figure 4. MPSA05/06 Capacitance (Cibo, 25 °C)",
            [
                (0.103, 51.88),
                (0.1748, 50.66),
                (0.2897, 48.8),
                (0.4379, 47.11),
                (0.6626, 44.98),
                (1.074, 41.28),
                (1.647, 37.6),
                (2.416, 33.63),
                (3.382, 29.91),
                (4.008, 28.11),
            ],
        ),
        cob=(
            "Figure 4 (Cobo)",
            [
                (0.1017, 17.32),
                (0.1543, 16.32),
                (0.2412, 15.27),
                (0.428, 13.9),
                (0.9339, 12.07),
                (2.097, 10.25),
                (3.911, 8.763),
                (7.619, 7.268),
                (14.85, 5.839),
                (27.29, 4.911),
                (44.27, 4.449),
                (80.99, 4.19),
            ],
        ),
        vaf=(
            float("inf"),
            "the sheet gives no output admittance or output curves, so none is set (ngspice's "
            "default)",
        ),
        ft=(
            196.9e6,
            10.08e-3,
            2.0 - 0.6409,
            "Figure 2 (MPSA05/06 Current-Gain-Bandwidth Product, VCE = 2.0 V): 197 MHz at 10 "
            "mA, the table's "
            "condition (100 MHz minimum); VCB = 2 V less VBE(on) 0.64 V read from Figure 12 at "
            "10 mA",
        ),
        checks=[
            (
                "hfe",
                {"ic": 1e-2, "vce": 1.0},
                {"min": 100.0, "source": T(ONA06, "hFE at IC = 10 mA, VCE = 1.0 V")},
            ),
            (
                "hfe",
                {"ic": 0.1, "vce": 1.0},
                {"min": 100.0, "source": T(ONA06, "hFE at IC = 100 mA, VCE = 1.0 V")},
            ),
            (
                "vce_sat",
                {"ic": 0.1, "ib": 0.01},
                {"max": 0.25, "source": T(ONA06, "VCE(sat) at IC = 100 mA, IB = 10 mA")},
            ),
            (
                "vbe",
                {"ic": 0.1, "vce": 1.0},
                {"max": 1.2, "source": T(ONA06, "VBE(on) at IC = 100 mA, VCE = 1.0 V")},
            ),
        ],
        fit_grid=[0.52, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 490.0],
        held=[0.7, 3.0, 30.0, 300.0],
        note=(
            "The MPSA05 and MPSA06 share the sheet's figures and its gain, saturation and "
            "VBE(on) limits; the "
            "MPSA06 differs in its 80 V ratings. The table gives hFE minimums only (100 at 10 "
            "and 100 mA), no range, "
            "so the typical 25 °C curve is used as drawn. The fit grid is the 1-2-5 steps plus "
            "the curves' "
            "ends (0.52 and 490 mA), because the curves start at 0.5 mA"
        ),
    ),
}
