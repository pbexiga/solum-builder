"""Fit the BJTs named on the command line (or all) from their sheets' curves (D-163)."""

import importlib.util as _ilu
import sys
from pathlib import Path as _P

sys.path.insert(0, ".claude/skills/fit-model/tools")
from bjt_record import build

ON3904 = "onsemi 2N3904 data sheet, Rev. 2 (July 2021, 2N3904/D)"
T = lambda sheet, what: f"{sheet}, Electrical Characteristics: {what}"  # noqa: E731
PARTS = {
    "2N3904": dict(
        id="2N3904",
        polarity="NPN",
        maker="onsemi",
        desc="2N3904 general-purpose NPN (switching and small-signal; pairs with the 2N3906), "
        "our fit to onsemi's "
        "sheet",
        url="https://www.farnell.com/datasheets/3770732.pdf",
        sheet=ON3904,
        hfe=(
            "Figure 1. Typical Pulsed Current Gain vs. Collector Current (25 °C)",
            5.0,
            [
                (0.1, 231.4),
                (2.139, 228.9),
                (4.18, 227.7),
                (7.699, 225.0),
                (14.16, 219.7),
                (25.91, 210.4),
                (46.98, 195.8),
                (59.41, 187.8),
                (69.89, 181.2),
                (81.76, 173.3),
                (93.89, 163.8),
                (100.0, 159.1),
            ],
        ),
        vbe=(
            "Figure 4. Base-Emitter On Voltage vs. Collector Current (25 °C)",
            5.0,
            [
                (0.1, 0.608),
                (0.4997, 0.6493),
                (1.779, 0.682),
                (6.364, 0.7148),
                (22.72, 0.7499),
                (80.33, 0.7893),
                (100.4, 0.797),
            ],
        ),
        vcs=(
            "Figure 2. Collector-Emitter Saturation Voltage vs. Collector Current (β = 10, 25 °C)",
            10.0,
            [
                (0.1, 0.07621),
                (0.3802, 0.06329),
                (0.6603, 0.0576),
                (0.9386, 0.05412),
                (1.224, 0.05206),
                (1.505, 0.05043),
                (15.66, 0.05184),
                (21.94, 0.0576),
                (30.16, 0.06499),
                (39.09, 0.075),
                (49.7, 0.08687),
                (59.82, 0.09674),
                (70.06, 0.1063),
                (80.01, 0.1159),
                (90.02, 0.1253),
                (100.0, 0.1347),
            ],
        ),
        cib=(
            "Figure 6. Capacitance vs. Reverse Bias Voltage (Cibo)",
            [
                (0.09999, 4.291),
                (0.1571, 4.258),
                (0.2531, 4.201),
                (0.5508, 3.977),
                (0.9992, 3.697),
                (1.791, 3.351),
                (3.186, 3.0),
                (5.659, 2.683),
                (8.011, 2.498),
            ],
        ),
        cob=(
            "Figure 6 (Cobo)",
            [
                (0.09999, 3.446),
                (0.1855, 3.39),
                (0.3021, 3.297),
                (0.4889, 3.157),
                (0.7517, 3.0),
                (1.289, 2.735),
                (2.025, 2.498),
                (3.05, 2.267),
                (4.991, 2.0),
                (6.641, 1.853),
                (8.219, 1.746),
                (10.22, 1.635),
                (12.43, 1.566),
                (15.33, 1.496),
                (18.89, 1.45),
                (23.38, 1.419),
                (29.22, 1.393),
                (34.29, 1.378),
                (40.08, 1.378),
            ],
        ),
        vaf=(
            1e-3 / 8.688e-6 - 10,
            "from Figure 16 (Output Admittance): hoe 8.69 µS at 1 mA, VCE = 10 V, so VAF = "
            "IC/hoe − VCE",
        ),
        ft=(
            590e6,
            10e-3,
            39.3,
            "Figure 9 (Current Gain and Phase Angle vs. Frequency): |hfe| reaches 0 dB at 590 "
            "MHz, IC = 10 mA, "
            "VCE "
            "= "
            "40 "
            "V; "
            "the table gives 300 "
            "MHz "
            "minimum at 20 V",
        ),
        checks=[
            (
                "hfe",
                {"ic": 1e-4, "vce": 1.0},
                {"min": 40.0, "source": T(ON3904, "hFE at IC = 0.1 mA, VCE = 1 V")},
            ),
            (
                "hfe",
                {"ic": 1e-3, "vce": 1.0},
                {"min": 70.0, "source": T(ON3904, "hFE at IC = 1 mA, VCE = 1 V")},
            ),
            (
                "hfe",
                {"ic": 1e-2, "vce": 1.0},
                {"min": 100.0, "max": 300.0, "source": T(ON3904, "hFE at IC = 10 mA, VCE = 1 V")},
            ),
            (
                "hfe",
                {"ic": 5e-2, "vce": 1.0},
                {"min": 60.0, "source": T(ON3904, "hFE at IC = 50 mA, VCE = 1 V")},
            ),
            (
                "hfe",
                {"ic": 0.1, "vce": 1.0},
                {"min": 30.0, "source": T(ON3904, "hFE at IC = 100 mA, VCE = 1 V")},
            ),
            (
                "vce_sat",
                {"ic": 1e-2, "ib": 1e-3},
                {"max": 0.2, "source": T(ON3904, "VCE(sat) at IC = 10 mA, IB = 1 mA")},
            ),
            (
                "vce_sat",
                {"ic": 5e-2, "ib": 5e-3},
                {"max": 0.3, "source": T(ON3904, "VCE(sat) at IC = 50 mA, IB = 5 mA")},
            ),
        ],
        held=[0.3, 3.0, 30.0],
    ),
}

FS5088 = "Fairchild 2N5088/2N5089/MMBT5088/MMBT5089 data sheet, Rev A (2001; onsemi's copy)"
F5088 = dict(
    maker="onsemi (Fairchild)",
    polarity="NPN",
    url="https://datasheet.lcsc.com/datasheet/pdf/84abd93136f2ca0ef8a7d59b0be01699.pdf?productCode=C3201678",
    sheet=FS5088,
    vbe=(
        "Base-Emitter ON Voltage vs Collector Current (25 °C)",
        5.0,
        [
            (0.1, 0.573),
            (0.1973, 0.591),
            (0.3789, 0.6089),
            (0.6462, 0.6246),
            (1.073, 0.6369),
            (1.913, 0.6536),
            (3.839, 0.6738),
            (6.461, 0.6905),
            (9.116, 0.7006),
            (12.52, 0.7095),
            (15.97, 0.7184),
            (19.74, 0.7262),
            (24.07, 0.7352),
            (29.11, 0.7441),
            (33.67, 0.7508),
            (40.0, 0.7576),
        ],
    ),
    vcs=(
        "Collector-Emitter Saturation Voltage vs Collector Current (β = 10, 25 °C)",
        10.0,
        [
            (0.1, 0.04223),
            (0.5004, 0.04324),
            (0.9999, 0.04392),
            (2.009, 0.04696),
            (3.615, 0.05135),
            (5.616, 0.0571),
            (8.634, 0.06318),
            (12.14, 0.06993),
            (16.37, 0.07771),
            (20.73, 0.08648),
            (25.71, 0.09628),
            (31.54, 0.1081),
            (39.52, 0.1206),
            (49.0, 0.1351),
            (60.44, 0.1537),
            (73.38, 0.1716),
            (84.99, 0.1912),
            (98.96, 0.2111),
        ],
    ),
    cib=(
        "Input and Output Capacitance vs Reverse Bias Voltage (Cte)",
        [
            (0.8953, 3.202),
            (1.747, 2.872),
            (2.672, 2.599),
            (3.813, 2.326),
            (4.58, 2.18),
            (5.478, 2.07),
            (6.116, 2.006),
            (6.725, 1.953),
            (7.391, 1.919),
            (8.173, 1.907),
        ],
    ),
    cob=(
        "the same figure (Cob)",
        [
            (0.001, 4.395),
            (0.4045, 3.948),
            (0.852, 3.584),
            (1.343, 3.254),
            (1.877, 2.988),
            (2.541, 2.733),
            (3.192, 2.541),
            (3.899, 2.372),
            (4.739, 2.233),
            (5.594, 2.122),
            (6.725, 2.0),
            (8.0, 1.901),
            (20.0, 1.052),
        ],
    ),
    vaf=(
        float("inf"),
        "the sheet gives no output admittance or output curves, so none is set (ngspice's default)",
    ),
    ft=(
        175e6,
        8.07e-3,
        3.0,
        "Contours of Constant Gain Bandwidth Product: the 175 MHz contour's lowest point, 8 mA "
        "at VCE = 3.7 V",
    ),
    held=[0.03, 0.3, 3.0, 30.0],
)
HFE5088 = (
    "Typical Pulsed Current Gain vs Collector Current (25 °C, VCE = 5 V)",
    5.0,
    [
        (0.01, 482.3),
        (0.03, 519.2),
        (0.09999, 548.9),
        (0.3, 577.3),
        (1.0, 595.8),
        (3.0, 592.9),
        (10.0, 544.7),
        (19.94, 479.4),
        (30.0, 412.8),
        (99.99, 43.98),
    ],
)
FAMILY = (
    "The sheet draws one typical gain curve for both parts (548.9 at 100 µA). Its shape is kept "
    "and its level set "
    "to "
    "the geometric middle of this part's 100 µA range ({lo:g} to {hi:g}: {mid:.0f}), as for the "
    "JFETs' ranges (D-161, "
    "D-163). "
    "The curve falls steeply past 20 mA (44 at 100 mA, times the same factor); NKF, the knee's "
    "exponent, follows "
    "it"
)
for pid, lo, hi, at1, at10, vceo in (
    ("2N5088", 300, 900, 350, 300, 30),
    ("2N5089", 400, 1200, 450, 400, 25),
):
    mid = (lo * hi) ** 0.5
    PARTS[pid] = dict(
        F5088,
        id=pid,
        hfe=HFE5088,
        hfe_scale=mid / 548.9,
        desc=f"{pid} high-gain, low-noise NPN (hFE {lo}-{hi} at 100 µA; VCEO {vceo} V), our fit "
        "to Fairchild's sheet",
        note=FAMILY.format(lo=lo, hi=hi, mid=mid),
        checks=[
            (
                "hfe",
                {"ic": 1e-4, "vce": 5.0},
                {
                    "min": float(lo),
                    "max": float(hi),
                    "source": T(FS5088, f"hFE at IC = 100 µA, VCE = 5 V, {pid[2:]}"),
                },
            ),
            (
                "hfe",
                {"ic": 1e-3, "vce": 5.0},
                {"min": float(at1), "source": T(FS5088, f"hFE at IC = 1 mA, VCE = 5 V, {pid[2:]}")},
            ),
            (
                "hfe",
                {"ic": 1e-2, "vce": 5.0},
                {
                    "min": float(at10),
                    "source": T(FS5088, f"hFE at IC = 10 mA, VCE = 5 V, {pid[2:]}"),
                },
            ),
            (
                "vce_sat",
                {"ic": 1e-2, "ib": 1e-3},
                {"max": 0.5, "source": T(FS5088, "VCE(sat) at IC = 10 mA, IB = 1 mA")},
            ),
            (
                "vbe",
                {"ic": 1e-2, "vce": 5.0},
                {"max": 0.8, "source": T(FS5088, "VBE(on) at IC = 10 mA, VCE = 5 V")},
            ),
        ],
    )

# More parts: one file per part or family in .claude/skills/fit-model/tools/specs/, each defining
# PARTS (same dict shape as above; see bjt_record.py's docstring). Run: fit_bjts.py ID [ID...]

for _f in sorted(_P(".claude/skills/fit-model/tools/specs").glob("*.py")):
    _s = _ilu.spec_from_file_location(_f.stem, _f)
    _m = _ilu.module_from_spec(_s)
    _s.loader.exec_module(_m)
    PARTS.update(_m.PARTS)

if __name__ == "__main__":
    for k in sys.argv[1:] or PARTS:
        build(PARTS[k])
