"""BC548, BC549C, BC550C from onsemi's BC546-BC550 family sheet (D-163): one typical gain curve
for every type and grade, its shape kept and its level set per part to the geometric middle of
that part's hFE range at the table's 2 mA, as the 2N5088/2N5089 in fit_bjts.py."""

import math
from itertools import pairwise


def _at(curve, x):
    """The digitised curve read at x (log x, linear y)."""
    c = sorted(curve)
    for (x0, y0), (x1, y1) in pairwise(c):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * math.log(x / x0) / math.log(x1 / x0)
    raise ValueError(x)


# The table's typicals win over the figures where they disagree (as for the MPSA18): Figure 2 reads
# 0.675 V at 2 mA (table: 660 mV typical) and 0.727 V at 10 mA (table: 720 mV maximum); Figure 5
# reads 2.16 pF at 10 V (table: 3.5 pF typical). Each figure keeps its shape and is moved onto
# the table.
VBE_FIG = [
    (0.1, 0.5797),
    (0.3563, 0.6204),
    (1.093, 0.6561),
    (3.352, 0.6918),
    (10.28, 0.7276),
    (31.58, 0.7635),
    (100.0, 0.8),
]
VBE_SHIFT = 0.660 - _at(VBE_FIG, 2.0)
COB_FIG = [
    (1.0, 4.792),
    (1.529, 4.115),
    (3.405, 3.092),
    (7.6, 2.345),
    (17.01, 1.802),
    (38.23, 1.408),
    (50.02, 1.299),
]
COB_SCALE = 3.5 / _at(COB_FIG, 10.0)
SHEET = "onsemi BC546/BC547/BC548/BC549/BC550 data sheet, Rev. 2 (April 2021, BC550/D)"
T = lambda what: f"{SHEET}, Electrical Characteristics: {what}"  # noqa: E731

FBC = dict(
    maker="onsemi",
    polarity="NPN",
    sheet=SHEET,
    url="https://sy-dep-epc-lpc.web.cern.ch/components/datasheets/epc-lpc%20(converters)/BC550_NPN%20BJT_On%20Semiconductor.pdf",
    vbe=(
        "Figure 2. Transfer Characteristics (IC against VBE, VCE = 5 V; read as VBE(on) "
        "against IC), moved "
        f"{VBE_SHIFT * 1e3:+.1f} mV onto the table's 660 mV typical at 2 mA (the figure reads "
        "0.727 V at 10 mA, "
        f"above the table's 720 mV maximum)",
        5.0,
        [(i, v + VBE_SHIFT) for i, v in VBE_FIG],
    ),
    vcs=(
        "Figure 4. Collector-Emitter Saturation Voltage (IC = 10 IB)",
        10.0,
        [
            (1.0, 0.03705),
            (1.651, 0.03589),
            (2.338, 0.03618),
            (3.311, 0.03727),
            (4.684, 0.03905),
            (7.078, 0.04207),
            (9.974, 0.04616),
            (13.97, 0.05194),
            (19.62, 0.05971),
            (32.52, 0.07463),
            (47.26, 0.09015),
            (67.97, 0.112),
            (97.78, 0.1459),
            (132.2, 0.1873),
            (169.8, 0.2336),
            (217.2, 0.2932),
            (300.3, 0.4003),
        ],
    ),
    cib=(
        "Electrical Characteristics: Cib 9 pF typical at VEB = 0.5 V (the sheet draws no Cib "
        "curve: one point "
        "sets CJE, with ngspice's default VJE 0.75 V and MJE 0.33)",
        [(0.5, 9.0)],
    ),
    cob=(
        f"Figure 5. Output Capacitance (Cob, IE = 0, f = 1 MHz), times {COB_SCALE:.3f} onto the "
        "table's 3.5 pF "
        f"typical at VCB = 10 V (the figure reads 2.16 pF there)",
        [(v, c * COB_SCALE) for v, c in COB_FIG],
    ),
    vaf=(
        float("inf"),
        "the sheet gives no output admittance, and its Figure 1 output curves disagree with "
        "each other "
        "(IB = 50 µA flat from 5 to 15 V; 100 µA rising 0.28 mA/V; 150 µA 0.15 mA/V), so none "
        "is set (ngspice's "
        "default)",
    ),
    ft=(
        300e6,
        10e-3,
        4.27,
        "Electrical Characteristics: fT 300 MHz typical at IC = 10 mA, VCE = 5 V (Figure 6 reads "
        "294 MHz there); VCB = 5 V less VBE 0.73 V from Figure 2",
    ),
    held=[0.3, 3.0, 30.0],
    top_ma=100.0,  # IC is rated 100 mA DC; the figures run on to 300 mA
)
HFE = (
    "Figure 3. DC Current Gain (VCE = 5 V; one typical curve for every type and grade)",
    5.0,
    [
        (1.0, 200.0),
        (21.91, 200.0),
        (31.86, 199.7),
        (46.34, 196.9),
        (67.34, 190.2),
        (97.69, 178.6),
        (141.6, 161.2),
        (182.3, 138.2),
        (225.3, 107.1),
        (276.0, 72.2),
        (300.1, 60.04),
    ],
)
FAMILY = (
    "The sheet draws one typical gain curve for the whole BC546-BC550 family (200 at 2 mA, flat "
    "from 1 to 20 mA) "
    "and doesn't say which grade it is drawn for (200 sits where its groups A, 110-220, and B, "
    "200-450, meet). "
    "Its shape is kept and its level set to the geometric middle of this part's 2 mA range "
    "({rng}: {lo:g} to "
    "{hi:g}, so {mid:.0f}), as for the 2N5088/89 (D-161, D-163). The curve is drawn from 1 mA "
    "only, so below "
    "1 mA the gain follows from the VBE(on) curve and the model's leakage term alone"
)
CHECKS = [
    (
        "vce_sat",
        {"ic": 1e-2, "ib": 5e-4},
        {"max": 0.25, "source": T("VCE(sat) at IC = 10 mA, IB = 0.5 mA")},
    ),
    (
        "vce_sat",
        {"ic": 0.1, "ib": 5e-3},
        {"max": 0.6, "source": T("VCE(sat) at IC = 100 mA, IB = 5 mA")},
    ),
    (
        "vbe",
        {"ic": 2e-3, "vce": 5.0},
        {"min": 0.58, "max": 0.7, "source": T("VBE(on) at VCE = 5 V, IC = 2 mA")},
    ),
    (
        "vbe",
        {"ic": 1e-2, "vce": 5.0},
        {"max": 0.72, "source": T("VBE(on) at VCE = 5 V, IC = 10 mA")},
    ),
]
PARTS = {}
for pid, lo, hi, rng, cite, desc in (
    (
        "BC548",
        110,
        800,
        "the table's range for the type, all grades together",
        "hFE at VCE = 5 V, IC = 2 mA",
        "BC548 general-purpose NPN (any gain group, hFE 110-800 at 2 mA; VCEO 30 V)",
    ),
    (
        "BC549C",
        420,
        800,
        "gain group C",
        "hFE at VCE = 5 V, IC = 2 mA, and hFE Classification C",
        "BC549C low-noise NPN, gain group C (hFE 420-800 at 2 mA; VCEO 30 V)",
    ),
    (
        "BC550C",
        420,
        800,
        "gain group C",
        "hFE at VCE = 5 V, IC = 2 mA, and hFE Classification C",
        "BC550C low-noise NPN, gain group C (hFE 420-800 at 2 mA; VCEO 45 V)",
    ),
):
    mid = (lo * hi) ** 0.5
    PARTS[pid] = dict(
        FBC,
        id=pid,
        hfe=HFE,
        hfe_scale=mid / 200.0,
        desc=f"{desc}, our fit to onsemi's sheet",
        note=FAMILY.format(rng=rng, lo=lo, hi=hi, mid=mid),
        checks=[
            (
                "hfe",
                {"ic": 2e-3, "vce": 5.0},
                {"min": float(lo), "max": float(hi), "source": T(cite)},
            ),
            *CHECKS,
        ],
    )
