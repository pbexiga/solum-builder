"""Write library/models/mosfet/{2N7000,BS170}.{json,lib} from the fits (D-175)."""
import json
from pathlib import Path

from scratch.fit.mosfet import spec_2n7000 as s
from solum.models import ModelCard
from solum.netlist import spice_number

OUT = Path("library/models/mosfet")
CARD = {"vto": 2.3973, "kp": 0.4838, "ksubthres": 0.24488, "mtriode": 1.1919, "lambda": 1e-06,
        "rs": 1.0742, "rd": 1.0117e-06, "cgs": 1.7221e-11, "cgdmax": 3.7315e-11, "cgdmin": 2.0146e-12,
        "a": 0.30204, "cjo": 2.6453e-11, "m": 0.40407, "vj": 1.0171, "is": 9.1033e-13, "n": 1.1464,
        "rb": 0.12828}
SHEET_2N = "Fairchild 2N7000/2N7002/NDS7002A data sheet, Rev. 2.10 (onsemi)"
URL_2N = "https://www.farnell.com/datasheets/2304304.pdf"
SHEET_BS = "Fairchild BS170/MMBF170 data sheet, Rev. E2 (March 2010)"
URL_BS = "https://www.logosfoundation.org/instrum_gwr/display/BS170.pdf"
METHOD = (
    "ngspice VDMOS fitted through ngspice itself with the project's Levenberg-Marquardt "
    "(scripts/fit_models.py): VTO, KP, KSUBTHRES, MTRIODE, LAMBDA, RS, RD to Figure 1 (output "
    "curves, VGS 3-10 V, half weight), Figure 5 (transfer, 25 °C, VDS 10 V), the table's VGS(th) "
    "2.1 V at 1 mA (weight 20: the curves start at 0.05 A, so the threshold anchors the low end) "
    "and VDS(on) 0.6 V (10 V, 500 mA) and 0.14 V (4.5 V, 75 mA); then, with those held, CGS, "
    "CGDMAX, CGDMIN, A, CJO, M, VJ to Figure 9 (Ciss, Coss, Crss at VGS 0, 1 MHz) and IS, N, RB "
    "to Figure 8 (body diode, 25 °C). Scripts: .claude/skills/fit-model/worked/mosfet/ (not committed); points are "
    "read off the sheet's vector drawing")
NOTE_2N = (
    "Output curves within about 12 %, capacitances within 7 %, body diode within 6 %. Figure 5's "
    "low end (10 mA at 2.58 V) disagrees with the table's VGS(th) (1 mA at 2.1 V); the table wins "
    "(D-163), so the card runs above the figure there (+66 % at 10 mA, +30 % at 2 A)")
OUTPUT = {f"output_vgs_{vg:g}": pts for vg, pts in s.SPEC["output"]["curves"].items()}
CURVES = {**OUTPUT,
          "ciss": [(v, c * 1e-12) for v, c, _, _ in s.SPEC["caps"]],
          "coss": [(v, c * 1e-12) for v, _, c, _ in s.SPEC["caps"]],
          "crss": [(v, c * 1e-12) for v, _, _, c in s.SPEC["caps"]],
          "body_diode": s.SPEC["body"]}


def record(id_, sheet, url, package, fit_note, validation, desc):
    card = ModelCard(id_, "VDMOS", {k: spice_number(v) for k, v in CARD.items()})
    (OUT / f"{id_}.lib").write_text(
        f"* {desc}\n* Built by Solum Builder from {sheet} (D-175)\n{card.text()}\n")
    return {
        "id": id_, "type": "mosfet", "description": desc, "spice_name": id_, "kind": "model",
        "pins": [], "card": f"{id_}.lib", "manufacturer": "Fairchild",
        "source": {"url": url, "retrieved": "2026-11-02",
                   "licence": "Our own model built from the maker's data sheet (D-159, D-161): the values are Solum Builder's",
                   "original": "Solum Builder fit"},
        "fixes": [], "ratings": {"vds_max": 60.0, "id_max": 0.5 if id_ == "BS170" else 0.2},
        "rating_sources": {"vds_max": f"{sheet}, Absolute Maximum Ratings: VDSS",
                           "id_max": f"{sheet}, Absolute Maximum Ratings: ID continuous"},
        "package": package,
        "fit": {"sheet": SHEET_2N,
                "figure": "Figure 5. Transfer Characteristics (25 °C, VDS = 10 V); Figure 1. On-Region Characteristics; Figure 8. Body Diode Forward Voltage (25 °C); Figure 9. Capacitance Characteristics",
                "points": s.SPEC["transfer"]["points"], "method": METHOD, "note": fit_note,
                "curves": CURVES},
        "validation": validation,
    }


def v(quantity, cond, ds):
    return {"quantity": quantity, "conditions": cond, "simulated": 0.0, "datasheet": ds}


n7 = record("2N7000", SHEET_2N, URL_2N,
    {"name": "TO-92 (SGD)", "pins": {"S": 1, "G": 2, "D": 3},
     "source": f"{SHEET_2N}, page 1: TO-92 pin drawing, 1. Source 2. Gate 3. Drain"},
    NOTE_2N,
    [v("vgs_th", {"id": 1e-3}, {"min": 0.8, "typ": 2.1, "max": 3.0, "tol": 0.1,
        "source": f"{SHEET_2N}, On Characteristics: VGS(th) at VDS = VGS, ID = 1 mA"}),
     v("vds_on", {"vgs": 10.0, "id": 0.5}, {"typ": 0.6, "max": 2.5, "tol": 0.1,
        "source": f"{SHEET_2N}, On Characteristics: VDS(on) at VGS = 10 V, ID = 500 mA"}),
     v("vds_on", {"vgs": 4.5, "id": 0.075}, {"typ": 0.14, "max": 0.4, "tol": 0.02,
        "source": f"{SHEET_2N}, On Characteristics: VDS(on) at VGS = 4.5 V, ID = 75 mA"})],
    "2N7000 N-channel enhancement MOSFET, 60 V 200 mA (our model from Fairchild's sheet)")
bs = record("BS170", SHEET_BS, URL_BS,
    {"name": "TO-92 (DGS)", "pins": {"D": 1, "G": 2, "S": 3},
     "source": f"{SHEET_BS}, page 1 TO-92 drawing (D, G, S) and page 2 Ordering Information: pin array DGS"},
    NOTE_2N + ". The BS170 is the same Fairchild die: its sheet's figures are the 2N7000's "
    "(drawn as images, so not read again) and its table agrees with this card: VGS(th), "
    "RDS(on) 1.31 Ω against 1.2 typical, gFS 294 mS against 320, Ciss/Coss/Crss at 10 V "
    "23.6/16.5/6.4 pF against 24/17/7",
    [v("vgs_th", {"id": 1e-3}, {"min": 0.8, "typ": 2.1, "max": 3.0, "tol": 0.1,
        "source": f"{SHEET_BS}, On Characteristics: VGS(th) at VDS = VGS, ID = 1 mA"}),
     v("vds_on", {"vgs": 10.0, "id": 0.2}, {"typ": 0.24, "max": 1.0, "tol": 0.04,
        "source": f"{SHEET_BS}, On Characteristics: RDS(on) 1.2 Ω typical, 5 Ω max at VGS = 10 V, ID = 200 mA (times 200 mA)"})],
    "BS170 N-channel enhancement MOSFET, 60 V 500 mA (our model, the 2N7000's die, checked against Fairchild's BS170 sheet)")
for r in (n7, bs):
    (OUT / f"{r['id']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n")
