"""Write library/models/mosfet/LND150.{json,lib} from fit_lnd150.py (D-178)."""
import json
from pathlib import Path

from scratch.fit.mosfet.fit_lnd150 import CAPS, CURVES, RSOURCE
from solum.models import ModelCard
from solum.netlist import spice_number

OUT = Path("library/models/mosfet")
CARD = {"vto": -1.2748, "kp": 0.0021146, "ksubthres": 0.16338, "mtriode": 0.52403,
        "lambda": 0.005317, "rs": 17.537, "rd": 1e-06, "cgs": 7.1957e-12, "cgdmax": 6.8769e-12,
        "cgdmin": 4.032e-14, "a": 0.25989, "cjo": 4.6761e-12, "m": 0.2, "vj": 0.13176}
SHEET = "Microchip LND150/LND250 data sheet DS20005454A (2018)"
URL = "https://ww1.microchip.com/downloads/en/DeviceDoc/LND150-LND250-N-Channel-Depletion-Mode-DMOS-FETs-Data-Sheet-20005454A.pdf"
DESC = "LND150 N-channel depletion MOSFET, 500 V 30 mA (our model from Microchip's sheet)"
METHOD = (
    "ngspice VDMOS fitted through ngspice itself with the project's Levenberg-Marquardt "
    "(scripts/fit_models.py): VTO, KP, KSUBTHRES, MTRIODE, LAMBDA (at most 0.01: the drawn curves "
    "are flat past the knee), RS to Figure 2-4 (Saturation Characteristics, VDS 0-5 V, VGS -1 to "
    "+1 V; points past the knee weighted 3, where pedals use it), the table's RDS(on) 850 ohm at "
    "VGS 0, ID 0.5 mA (weight 3) and VGS(off) at 100 nA, VDS 25 V, the range's middle -2 V "
    "(D-161, weight 0.5); then, with those held, CGS, CGDMAX, CGDMIN, A, CJO, M, VJ to Figure 2-9 "
    "(VGS -10 V, 1 MHz). Body diode left at VDMOS's defaults: the sheet gives only VSD <= 0.9 V "
    "at 1 mA. Figures 2-2 and 2-8 are at VDS 400 V (about 0.6 W in the part, self-heated: ID at "
    "VGS 0 reads 1.5 mA there against 1.7 mA in Figure 2-4) and were left out. Scripts: "
    ".claude/skills/fit-model/worked/mosfet/fit_lnd150.py (not committed); points are read off the sheet's vector drawing")
NOTE = (
    "Figure 2-4 past the knee within 6 %; the knees run up to 35 % high at VGS 0.5 and 1 V "
    "(a gate above its source; the drawn knees are sharper than VDMOS's). RDS(on) 791 ohm "
    "(850 typ), VGS(off) -1.74 V (-1 to -3), IDSS at 25 V 1.85 mA (1 to 3), gFS at 1 mA 2.1 mS "
    "(2 typ), capacitances within 21 % (7.53/1.97/0.33 pF at 25 V against 7.5/2/0.5 typ), VSD at "
    "1 mA 0.55 V (0.9 max). Held out: Figure 2-10 (ID against a source resistor, gate to ground, "
    "25 C) runs 23 to 43 % below the card: that figure's own unit reads about 1.4 mA at VGS 0 "
    "against Figure 2-4's 1.7 mA, so the sheet's samples differ by that much")


def v(quantity, cond, ds):
    return {"quantity": quantity, "conditions": cond, "simulated": 0.0, "datasheet": ds}


card = ModelCard("LND150", "VDMOS", {k: spice_number(x) for k, x in CARD.items()})
(OUT / "LND150.lib").write_text(f"* {DESC}\n* Built by Solum Builder from {SHEET} (D-178)\n{card.text()}\n")
record = {
    "id": "LND150", "type": "mosfet", "description": DESC, "spice_name": "LND150", "kind": "model",
    "pins": [], "card": "LND150.lib", "manufacturer": "Microchip (Supertex)",
    "source": {"url": URL, "retrieved": "2026-11-02",
               "licence": "Our own model built from the maker's data sheet (D-159, D-161): the values are Solum Builder's",
               "original": "Solum Builder fit"},
    "fixes": [], "ratings": {"vds_max": 500.0, "id_max": 0.03},
    "rating_sources": {"vds_max": f"{SHEET}, DC Electrical Characteristics: BVDSX 500 V min",
                       "id_max": f"{SHEET}, Thermal Characteristics: ID continuous 30 mA (TO-92)"},
    "package": {"name": "TO-92 (SGD)", "pins": {"S": 1, "G": 2, "D": 3},
                "source": f"{SHEET}, Table 3-1: TO-92 pin function table, 1 Source, 2 Gate, 3 Drain"},
    "fit": {"sheet": SHEET,
            "figure": "Figure 2-4. Saturation Characteristics; Figure 2-9. Capacitance vs. Drain-to-Source Voltage",
            "points": CURVES[0.0], "method": METHOD, "note": NOTE,
            "curves": {**{f"output_vgs_{vg:g}": pts for vg, pts in CURVES.items()},
                       "ciss": [(x, c * 1e-12) for x, c, _, _ in CAPS],
                       "coss": [(x, c * 1e-12) for x, _, c, _ in CAPS],
                       "crss": [(x, c * 1e-12) for x, _, _, c in CAPS],
                       "id_vs_rsource": [(r, i * 1e-3) for r, i in RSOURCE]}},
    "validation": [
        v("idss", {"vds": 25.0}, {"min": 1e-3, "max": 3e-3,
          "source": f"{SHEET}, DC Electrical Characteristics: IDSS 1 to 3 mA at VGS = 0, VDS = 25 V"}),
        v("vp", {"vds": 25.0, "id": 1e-7}, {"min": -3.0, "max": -1.0,
          "source": f"{SHEET}, DC Electrical Characteristics: VGS(OFF) -1 to -3 V at ID = 100 nA, VDS = 25 V"}),
        v("vds_on", {"vgs": 0.0, "id": 5e-4}, {"typ": 0.425, "max": 0.5, "tol": 0.05,
          "source": f"{SHEET}, DC Electrical Characteristics: RDS(ON) 850 ohm typ, 1000 max at VGS = 0, ID = 0.5 mA (times 0.5 mA)"}),
    ],
}
(OUT / "LND150.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
