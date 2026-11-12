"""2SC2458 from Toshiba's sheet (2003-03-27, 4 pages), curves read by pixel off the 300 dpi render
of pages 2 and 3 (.claude/skills/fit-model/worked/c2458/trace.py, ft.py). The 25 °C lines.

VBE: the sheet gives an IB - VBE figure (VCE 6 V), not IC - VBE; its middle line is turned into
IC through the hFE - IC line at the same VCE (trace.py). The sheet draws one typical gain line,
about 140 (a Y-grade unit); the Boss BD-2's Q2 is a GR (200-400), where it's the supply's
emitter follower and the gain moves VA by a few tens of millivolts."""

import json
import math
from pathlib import Path

SHEET = "Toshiba 2SC2458 data sheet (2003-03-27, 4 pages)"
T = lambda what: f"{SHEET}, page 1, electrical characteristics: {what}"  # noqa: E731
C = json.loads(Path(".claude/skills/fit-model/worked/c2458/curves.json").read_text())

PARTS = {
    "2SC2458": dict(
        id="2SC2458",
        polarity="NPN",
        maker="Toshiba",
        retrieved="2026-11-10",
        desc="2SC2458 general-purpose audio NPN (Toshiba; hFE 70-700 in grades O, Y, GR, BL; "
        "VCEO 50 V): the Boss "
        "BD-2's "
        "supply follower, "
        "our "
        "fit "
        "to "
        "Toshiba's sheet",
        url="https://doc.platan.ru/pdf/datasheets/toshiba/2SC2458.pdf (Toshiba 2SC2458, "
        "2003-03-27, 4 pages; "
        "distributor mirror)",
        sheet=SHEET,
        hfe=(
            "hFE – IC, VCE = 6 V, 25 °C (page 2, by pixel, the solid line from 0.1 to 150 mA)",
            6.0,
            [tuple(p) for p in C["hfe"] if p[0] <= 150],
        ),
        vbe=(
            "IB – VBE, VCE = 6 V, 25 °C (page 2, by pixel, the middle line from 0.3 to 1000 µA, "
            "less 0.5 to 35 µA "
            "where "
            "it "
            "runs along the 0.6 "
            "V "
            "grid "
            "line "
            "and can't be read), "
            "IC "
            "= "
            "hFE "
            "· "
            "IB from the hFE – "
            "IC "
            "line",
            6.0,
            [tuple(p) for p in C["vbe"]],
        ),
        vcs=(
            "VCE(sat) – IC, IC/IB = 10, 25 °C (page 2, by pixel, the middle line)",
            10.0,
            [tuple(p) for p in C["vcs"]],
        ),
        cob=("page 1, Cob 2.0 pF typ at VCB = 10 V, IE = 0, f = 1 MHz", [(10.0, 2.0)]),
        vaf=(
            math.inf,
            "the IC – VCE figures (page 2) draw the low-current lines flat; the h-parameter "
            "figures give hoe "
            "per "
            "grade "
            "but "
            "crowd too much to "
            "read, "
            "so "
            "none is set (ngspice's "
            "default)",
        ),
        ft=(
            144e6,
            1e-3,
            10.0,
            "page 3, fT – IC (by pixel, .claude/skills/fit-model/worked/c2458/ft.py): 144 MHz "
            "at IC = 1 mA, VCE "
            "= "
            "10 "
            "V; "
            "the "
            "table gives 80 MHz "
            "min",
        ),
        checks=[
            (
                "hfe",
                {"ic": 2e-3, "vce": 6.0},
                {
                    "min": 70.0,
                    "max": 700.0,
                    "source": T(
                        "hFE at VCE = 6 V, IC = 2 mA: 70 min, 700 max (O 70-140, Y 120-240, GR "
                        "200-400, BL 350-700)"
                    ),
                },
            ),
            (
                "vce_sat",
                {"ic": 0.1, "ib": 1e-2},
                {
                    "max": 0.25,
                    "source": T("VCE(sat) at IC = 100 mA, IB = 10 mA: 0.1 V typ, 0.25 V max"),
                },
            ),
            (
                "icbo",
                {"vcb": 50.0},
                {"max": 1e-7, "source": T("ICBO at VCB = 50 V, IE = 0: 0.1 µA max")},
            ),
        ],
        held=[0.3, 3.0, 30.0],
        note=(
            "The sheet draws one typical gain line (about 140 from 0.1 to 75 mA at VCE 6 V, "
            "falling to 115 at "
            "150 "
            "mA), "
            "a "
            "Y-grade unit; "
            "the BD-2's 2SC2458-GR has 200-400. The VBE comes from the IB – VBE figure through "
            "that gain line."
        ),
        ratings={"vceo": 50.0, "ic": 0.15},
        rating_sources={
            "vceo": f"{SHEET}, page 1, maximum ratings: VCEO 50 V",
            "ic": f"{SHEET}, page 1, maximum ratings: IC 150 mA",
        },
        package={
            "name": "TO-92 mini (ECB; Toshiba 2-4E1A)",
            "pins": {"E": 1, "C": 2, "B": 3},
            "source": f"{SHEET}, page 1: outline 2-4E1A, 1. emitter, 2. collector, 3. base",
        },
    )
}
