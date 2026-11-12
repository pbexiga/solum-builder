"""2SC2459 from Toshiba's sheet (2003-03-27, 3 pages), curves read by pixel off the 300 dpi
render of page 2 (.claude/skills/fit-model/worked/c2459/trace.py, trace_vbe.py, trace_vcs.py).
The 25 °C lines.

VBE: the sheet's table gives none, so the linear IC - VBE figure is the only source: the middle
line from 10 to 190 mA (below 10 mA the scale can't place it). The same figure on the
2SC2240's sheet reads 50 mV under that sheet's table at 10 mA (D-252), so this card's VBE may sit
as low; in the BD-2 the 2SC2459s are emitter followers, where that moves a DC level by 50 mV."""

import json
import math
from pathlib import Path

SHEET = "Toshiba 2SC2459 data sheet (2003-03-27, 3 pages)"
T = lambda what: f"{SHEET}, page 1, electrical characteristics: {what}"  # noqa: E731
D = Path(".claude/skills/fit-model/worked/c2459")
HFE = [tuple(p) for p in json.loads((D / "hfe.json").read_text())["hfe"] if p[0] <= 55]
VCS = [tuple(p) for p in json.loads((D / "vcs.json").read_text())["vcs"]]
VBE = [tuple(p) for p in json.loads((D / "vbe.json").read_text())["vbe"]]

PARTS = {
    "2SC2459": dict(
        id="2SC2459",
        polarity="NPN",
        maker="Toshiba",
        retrieved="2026-11-10",
        desc="2SC2459 audio NPN (Toshiba; hFE 200-700 in grades GR, BL; VCEO 120 V): the Boss "
        "BD-2's, our fit to "
        "Toshiba's "
        "sheet",
        url="https://doc.platan.ru/pdf/datasheets/toshiba/2SC2459.pdf (Toshiba 2SC2459, "
        "2003-03-27, 3 pages; "
        "distributor mirror)",
        sheet=SHEET,
        hfe=(
            "hFE – IC, VCE = 6 V, 25 °C (page 2, by pixel; to 55 mA, past which the three "
            "temperature lines "
            "cross)",
            6.0,
            HFE,
        ),
        vbe=(
            "IC – VBE, VCE = 6 V, 25 °C (page 2, by pixel, 10 to 190 mA; the table gives no VBE)",
            6.0,
            VBE,
        ),
        vcs=(
            "VCE(sat) – IC, IC/IB = 10, 25 °C (page 2, by pixel; under 30 mA the three lines "
            "overlap and the band's "
            "middle "
            "is read)",
            10.0,
            VCS,
        ),
        cob=("page 1, Cob 3.0 pF typ at VCB = 10 V, IE = 0, f = 1 MHz", [(10.0, 3.0)]),
        vaf=(
            math.inf,
            "the IC – VCE figures (page 2) draw the lines flat from 1 to 10 V; no output "
            "admittance in the "
            "table, "
            "so "
            "none is set (ngspice's "
            "default)",
        ),
        ft=(100e6, 1e-3, 6.0, "page 1: fT 100 MHz typ at VCE = 6 V, IC = 1 mA"),
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
                "icbo",
                {"vcb": 120.0},
                {
                    "max": 1e-4,
                    "source": T(
                        "ICBO at VCB = 120 V, IE = 0: 0.1 µA max (printed as 0.1 mA in this "
                        "copy's units column, "
                        "as "
                        "on "
                        "the "
                        "2SC2240's)"
                    ),
                },
            ),
        ],
        held=[0.3, 3.0, 30.0],
        note=(
            "The sheet draws one typical gain line (about 300 to 314 from 1 to 45 mA at VCE 6 "
            "V), a GR-grade unit, "
            "as "
            "the "
            "BD-2's "
            "2SC2459-GR. The VBE comes from the linear IC – VBE figure alone (no table value); "
            "on the 2SC2240's "
            "sheet "
            "the "
            "same "
            "figure reads 50 mV under the table (D-252), so a real unit's VBE may be that much "
            "higher. ISC is left "
            "free "
            "(not "
            "capped as the 2SC2240's): "
            "capped, the fit misses "
            "the "
            "VCE(sat) curve by "
            "9 "
            "mV "
            "at "
            "30 "
            "mA; free, it leaks "
            "10 "
            "nA "
            "at "
            "120 V, inside the "
            "sheet's "
            "0.1 "
            "µA."
        ),
        ratings={"vceo": 120.0, "ic": 0.1},
        rating_sources={
            "vceo": f"{SHEET}, page 1, maximum ratings: VCEO 120 V",
            "ic": f"{SHEET}, page 1, maximum ratings: IC 100 mA",
        },
        package={
            "name": "TO-92 mini (ECB; Toshiba 2-4E1A)",
            "pins": {"E": 1, "C": 2, "B": 3},
            "source": f"{SHEET}, page 1: outline 2-4E1A, 1. emitter, 2. collector, 3. base",
        },
    )
}
