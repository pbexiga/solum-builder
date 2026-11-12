"""2SC1815 from Toshiba's sheet (1997-04-10), curves read by pixel
(.claude/skills/fit-model/worked/c1815/digit.py, gaps.py; data.json). The 25 °C lines.
VBE(on) against IC is the IB-VBE line (VCE 6 V) with each IB turned into IC through the hFE
line (VCE 6 V)."""

import json
import math
from pathlib import Path

import numpy as np

D = json.loads(Path(".claude/skills/fit-model/worked/c1815/data.json").read_text())
SHEET = "Toshiba 2SC1815 data sheet (1997-04-10, 3 pages)"
P2 = "page 2 (by pixel)"
T = lambda what: f"{SHEET}, page 1, electrical characteristics: {what}"  # noqa: E731

# hFE, VCE 6 V: trace's flat run to 31 mA, then gaps.py's column reads of the solid 25 °C line
# (the trace wandered onto the dashed 1 V lines between 33 and 75 mA)
HFE = [(i, h) for i, h in D["hfe"] if i <= 31.0] + [
    (40.0, 139.2),
    (50.0, 139.2),
    (60.0, 139.2),
    (70.0, 139.9),
    (80.0, 139.2),
    (90.0, 137.8),
    (100.0, 133.9),
    (110.0, 131.3),
    (120.0, 127.5),
    (130.0, 122.1),
    (140.0, 118.0),
    (150.0, 113.5),
    (160.0, 108.6),
    (170.0, 104.0),
    (180.0, 100.0),
    (200.0, 91.7),
]


def hfe_at(ma: float) -> float:
    c = sorted(HFE)
    return float(np.interp(math.log10(ma), np.log10([p[0] for p in c]), [p[1] for p in c]))


def ic_of(ib_ua: float) -> float:
    """IC (mA) with IC = IB × hFE(IC)."""
    ic = ib_ua * 1e-3 * 139.2
    for _ in range(50):
        ic = ib_ua * 1e-3 * hfe_at(ic)
    return ic


# one point (29.9 µA, 0.673 V) is the "25" label's box, not the line. Below IC 1 mA the line is
# drawn steeper than a junction can be (IB 1 to 10 µA: 41 mV a decade, against kT/q's 59.5), so
# it's fitted from 1 mA (IB 10 to 100 µA: 62 mV a decade)
VBE_FROM_MA = 1.0
VBE = [
    (round(ic_of(ib), 4), v)
    for ib, v in D["ib_vbe"]
    if not (29 < ib < 31) and VBE_FROM_MA * 0.999 <= ic_of(ib) <= 200.0
]


def middle(vals: list[float], ma: float) -> float | None:
    """The 25 °C line: the middle of the three at each column (the sheet's arrow), labels and
    arrows dropped (under 0.065 V below 20 mA, under 0.5 V above)."""
    keep = sorted(v for v in vals if 0.025 < v < (0.065 if ma < 20 else 0.5))
    return keep[1] if len(keep) == 3 else None


VCS = [(float(k), m) for k, vs in D["vcs_runs"].items() if (m := middle(vs, float(k))) is not None]

PARTS = {
    "2SC1815": dict(
        id="2SC1815",
        polarity="NPN",
        maker="Toshiba",
        retrieved="2026-11-03",
        desc="2SC1815 general-purpose audio NPN (Toshiba; hFE 70-700 in grades O, Y, GR, BL), "
        "our fit to Toshiba's "
        "sheet",
        url="https://www.alldatasheet.com (Toshiba 2SC1815, 1997-04-10, 3 pages; the user "
        "supplied it, kept "
        "as "
        "data/spec-sheets/2SC1815_Toshiba.pdf)",
        sheet=SHEET,
        hfe=(f"hFE – IC, VCE = 6 V, 25 °C ({P2})", 6.0, HFE),
        vbe=(
            "IB – VBE, VCE = 6 V, 25 °C, each IB times the hFE line's gain, from IC 1 mA "
            f"({P2}; below 1 mA "
            "the line is drawn at 41 mV a decade, steeper than a junction's 59.5)",
            6.0,
            VBE,
        ),
        vcs=(f"VCE(sat) – IC, IC/IB = 10, 25 °C ({P2})", 10.0, VCS),
        cob=("page 1, Cob 2.0 pF typ at VCB = 10 V, IE = 0, f = 1 MHz", [(10.0, 2.0)]),
        vaf=(
            math.inf,
            "the sheet's two sources disagree: its hFE lines at VCE 1 V and 6 V coincide up to "
            "30 mA "
            "(VAF over about 170 V at a pixel's resolution), while the IC – VCE line at IB 0.2 "
            "mA rises "
            "26.6 to 29.7 mA from 1 to 5 V (VAF near 32 V), at 30-150 mW where self-heating "
            "raises the gain; "
            "so none is set (ngspice's default)",
        ),
        ft=(
            147e6,
            1e-3,
            9.4,
            "fT – IE figure, page 2: 147 MHz at 1 mA, VCE = 10 V (the table's test point, 80 "
            "MHz min); "
            "1 mA, not the 540 MHz peak, because there's no Cibo to put the low-current "
            "fall in CJE",
        ),
        isc_max=(
            1e-10,
            "left free, the fit sets it at its 1e-8 bound (10 nA of collector leakage, so a "
            "floating base passes 1.4 µA); 3.4 pA meets the VCE(sat) curve about as well (sum "
            "of squares "
            "112.3 against 109.8, worst miss 2.05 against 2.32 mV), and the sheet gives only "
            "ICBO under "
            "0.1 µA, so the bound is not taken as the part's leakage",
        ),
        rb=(50.0, "the table's rbb' (VCE = 10 V, IE = −1 mA, f = 30 MHz: 50 Ω typ)"),
        checks=[
            (
                "hfe",
                {"ic": 2e-3, "vce": 6.0},
                {
                    "min": 70.0,
                    "max": 700.0,
                    "source": T(
                        "hFE(1) at VCE = 6 V, IC = 2 mA: 70 min, 700 max (grades O 70-140, Y "
                        "120-240, GR 200-400, "
                        "BL "
                        "350-700)"
                    ),
                },
            ),
            (
                "hfe",
                {"ic": 0.15, "vce": 6.0},
                {"min": 25.0, "source": T("hFE(2) at VCE = 6 V, IC = 150 mA: 25 min, 100 typ")},
            ),
            (
                "vce_sat",
                {"ic": 0.1, "ib": 0.01},
                {
                    "max": 0.25,
                    "source": T("VCE(sat) at IC = 100 mA, IB = 10 mA: 0.1 typ, 0.25 max"),
                },
            ),
            (
                "icbo",
                {"vcb": 60.0},
                {"max": 1e-7, "source": T("ICBO at VCB = 60 V, IE = 0: 0.1 µA max")},
            ),
        ],
        held=[0.3, 3.0, 30.0],
        note=(
            "The sheet draws one typical gain line (139 from 0.1 to 80 mA at VCE 6 V), inside "
            "the Y grade "
            "(120-240); the card is that unit. GR (200-400) and BL (350-700) parts are common "
            "in pedals: measure "
            "yours (D-130). The table's hFE(0.1 mA)/hFE(2 mA) = 0.95 typ; the line is drawn "
            "flat, and the fit "
            "follows the line."
        ),
        ratings={"vceo": 50.0, "ic": 0.15},
        rating_sources={
            "vceo": f"{SHEET}, page 1, maximum ratings: VCEO 50 V",
            "ic": f"{SHEET}, page 1, maximum ratings: IC 150 mA",
        },
        package={
            "name": "TO-92 (ECB; Toshiba 2-5F1B)",
            "pins": {"E": 1, "C": 2, "B": 3},
            "source": f"{SHEET}, page 1: outline, 1. emitter, 2. collector, 3. base",
        },
    )
}
