"""2SC2240 from Toshiba's sheet (2003-03-25, 6 pages), curves read by pixel off the 300 dpi
rasters (.claude/skills/fit-model/worked/c2240/trace.py, trace_vcs.py; hfe.json, vcs.json).
The 25 °C lines.

VBE: the table's 0.65 V typ at VCE 6 V, IC 2 mA, with the slope the h-parameter figure gives
(page 4, VCE 6 V, 25 °C): dVBE/dIC = hie / hfe, read at 0.1 to 5 mA and integrated from 2 mA.
The IC - VBE figure (page 3, linear axes) isn't used: it reads 0.645 V at 10 mA, 50 mV under
the table and the h-parameters (they give 0.69 V there), and its scale can't place the pedal
range (under 5 mA it's within 10 px of the axis)."""

import json
import math
from pathlib import Path

import numpy as np

SHEET = "Toshiba 2SC2240 data sheet (2003-03-25, 6 pages)"
T = lambda what: f"{SHEET}, page 2, electrical characteristics: {what}"  # noqa: E731
D = Path(".claude/skills/fit-model/worked/c2240")
HFE = [tuple(p) for p in json.loads((D / "hfe.json").read_text())["hfe"] if p[0] <= 105]
VCS = [tuple(p) for p in json.loads((D / "vcs.json").read_text())["vcs"]]

# page 4, h PARAMETER - IC (by pixel): IC mA -> hie kΩ, and hfe
HIE = [
    (0.106, 52.7),
    (0.159, 36.1),
    (0.248, 24.1),
    (0.332, 18.2),
    (0.557, 11.3),
    (0.866, 7.46),
    (2.43, 2.86),
    (3.781, 1.89),
    (5.077, 1.44),
]
HFE_AC = [
    (0.106, 220.6),
    (0.248, 232.2),
    (0.332, 235.2),
    (0.557, 241.4),
    (0.866, 246.1),
    (1.348, 250.9),
    (2.43, 254.1),
    (5.077, 254.1),
]


def _logi(pts, x):
    xs, ys = zip(*pts, strict=True)
    return float(10 ** np.interp(math.log10(x), np.log10(xs), np.log10(ys)))


def vbe_at(ma: float) -> float:
    """0.65 V at 2 mA plus the integral of hie/hfe (kΩ × mA = V) from 2 mA."""
    grid = np.geomspace(2.0, ma, 400)
    slope = [_logi(HIE, i) / _logi(HFE_AC, i) for i in grid]
    return 0.65 + float(np.trapezoid(slope, grid))


VBE = [(i, round(vbe_at(i), 4)) for i in (0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0)]

PARTS = {
    "2SC2240": dict(
        id="2SC2240",
        polarity="NPN",
        maker="Toshiba",
        retrieved="2026-11-10",
        desc="2SC2240 low-noise audio NPN (Toshiba; hFE 200-700 in grades GR, BL; VCEO 120 V): "
        "the Boss DS-1's, "
        "our "
        "fit "
        "to "
        "Toshiba's sheet",
        url="https://static.chipdip.ru/lib/249/DOC000249963.pdf (Toshiba 2SC2240, 2003-03-25, 6 "
        "pages; distributor "
        "mirror)",
        sheet=SHEET,
        hfe=(
            "hFE – IC, VCE = 6 V, 25 °C (page 3, by pixel; to 105 mA, past which the three "
            "temperature lines "
            "bunch)",
            6.0,
            HFE,
        ),
        vbe=(
            "VBE from the table's 0.65 V typ at VCE = 6 V, IC = 2 mA, and the h PARAMETER – IC "
            "figure's hie/hfe "
            "(page 4, VCE = 6 V, 25 °C) integrated from it; the linear IC – VBE figure "
            "disagrees with both "
            "by "
            "50 "
            "mV "
            "and isn't used",
            6.0,
            VBE,
        ),
        vcs=(
            "VCE(sat) – IC, IC/IB = 10, 25 °C (page 3, by pixel; under 3 mA the three lines "
            "overlap and the band's "
            "middle "
            "is read)",
            10.0,
            VCS,
        ),
        cob=("page 2, Cob 3.0 pF typ at VCB = 10 V, IE = 0, f = 1 MHz", [(10.0, 3.0)]),
        vaf=(
            math.inf,
            "the IC – VCE figures (page 3) draw the lines flat within a pixel or two from 1 to "
            "10 V; no output admittance "
            "in "
            "the table, so none "
            "is "
            "set "
            "(ngspice's default)",
        ),
        ft=(100e6, 1e-3, 6.0, "page 2: fT 100 MHz typ at VCE = 6 V, IC = 1 mA"),
        isc_max=(
            1e-10,
            "capped as the 2SC1815's (D-187): the sheet gives only ICBO under 0.1 µA at 120 V, "
            "so the fitter's bound "
            "isn't "
            "taken as the part's "
            "leakage",
        ),
        checks=[
            (
                "hfe",
                {"ic": 2e-3, "vce": 6.0},
                {
                    "min": 200.0,
                    "max": 700.0,
                    "source": T(
                        "hFE at VCE = 6 V, IC = 2 mA: 200 min, 700 max (GR 200-400, BL 350-700)"
                    ),
                },
            ),
            (
                "vce_sat",
                {"ic": 1e-2, "ib": 1e-3},
                {"max": 0.3, "source": T("VCE(sat) at IC = 10 mA, IB = 1 mA: 0.3 V max")},
            ),
            (
                "vbe",
                {"ic": 2e-3, "vce": 6.0},
                {"typ": 0.65, "tol": 0.03, "source": T("VBE at VCE = 6 V, IC = 2 mA: 0.65 V typ")},
            ),
            (
                "icbo",
                {"vcb": 120.0},
                {
                    "max": 1e-4,
                    "source": T(
                        "ICBO at VCB = 120 V, IE = 0: 0.1 µA max (printed as 0.1 mA in this "
                        "copy's units column; "
                        "0.1 "
                        "µA "
                        "in "
                        "Toshiba's other small-signal "
                        "sheets)"
                    ),
                },
            ),
        ],
        held=[0.3, 3.0, 30.0],
        note=(
            "The sheet draws one typical gain line (about 300 to 320 from 1 to 30 mA at VCE 6 "
            "V), a GR-grade unit; "
            "a BL part (350-700) is common: measure yours (D-130). The h-parameter figure's "
            "small-signal hfe "
            "(220 "
            "to "
            "254) "
            "sits under the DC line, as usual."
        ),
        ratings={"vceo": 120.0, "ic": 0.1},
        rating_sources={
            "vceo": f"{SHEET}, page 1, maximum ratings: VCEO 120 V",
            "ic": f"{SHEET}, page 1, maximum ratings: IC 100 mA",
        },
        package={
            "name": "TO-92 (ECB; Toshiba 2-5F1B)",
            "pins": {"E": 1, "C": 2, "B": 3},
            "source": f"{SHEET}, page 1: outline 2-5F1B (JEDEC TO-92), 1. emitter, 2. "
            "collector, 3. base",
        },
    )
}
