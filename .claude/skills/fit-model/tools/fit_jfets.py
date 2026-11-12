"""Our own level-1 JFETs from their sheets (D-161): run in the dev image from the repo root."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("fm", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)
ON57 = "onsemi 2N5457/D Rev. 6 (Feb 2010)"
FJ = "Fairchild J201/J202 data sheet (1997)"
IF = "InterFET J201/J202 data sheet IF35018.R00 (June 2019)"
M102 = "onsemi MPF102/D Rev. 3 (January 2006)"
M4393 = "onsemi MPF4392/D Rev. 6 (February 2012)"
P51 = "Fairchild PF5102 data sheet, Rev. B0 (2011)"
LIC = (
    "Our own model built from the maker's data sheet (D-159, D-161): the values are Solum Builder's"
)
mid = fm.middle
PARTS = []


def part(**k):
    PARTS.append(k)


idss, vp = mid(0.2e-3, 1.0e-3), mid(-0.3, -1.5)
part(
    id="J201",
    name="J201",
    desc="J201 low-pinch-off N-channel JFET (our model from Fairchild's and InterFET's sheets)",
    maker="Fairchild",
    url="https://www.rlocman.ru/i/File/2025/08/26/J201.PDF",
    sheet=f"{FJ}; {IF}",
    fit=fm.JfetFit(idss, vp, lam=1e-6 / idss, cgs=3e-12, cgd=1e-12),
    method="Idss and Vp the geometric middles of the sheets' ranges (0.2-1.0 mA, -0.3 to -1.5 "
    f"V): {idss * 1e3:.3g} "
    "mA, "
    f"{vp:.3g} V; BETA "
    "= "
    "Idss/Vp²; "
    "LAMBDA from InterFET's "
    "typical "
    "output conductance, "
    "1 "
    "µS "
    "/ "
    "Idss; CGD = Crss "
    "1 "
    "pF, "
    "CGS "
    "= "
    "Ciss − Crss = 3 pF "
    "(InterFET "
    "typical)",
    pts=[(0.0, idss), (vp, 0.0)],
    checks=[
        (
            "idss",
            {"vds": 20.0},
            {
                "min": 0.2e-3,
                "max": 1e-3,
                "source": f"{FJ}, Electrical Characteristics: IDSS at VDS = 20 V",
            },
        ),
        (
            "vp",
            {"vds": 20.0, "id": 1e-8},
            {
                "min": -1.5,
                "max": -0.3,
                "source": f"{FJ}, Electrical Characteristics: VGS(off) at VDS = 20 V, ID = 10 nA",
            },
        ),
    ],
)
idss = 3e-3
vp = fm.jfet_vp(-2.5, 100e-6, idss)
part(
    id="2N5457",
    name="J2N5457",
    desc="2N5457 N-channel JFET (our model from onsemi's sheet)",
    maker="onsemi",
    url="https://www.rlocman.ru/i/File/2018/03/29/2N5457-D.pdf",
    sheet=ON57,
    fit=fm.JfetFit(idss, vp, lam=10e-6 / idss, cgs=3e-12, cgd=1.5e-12),
    method=f"Idss the sheet's typical 3 mA; Vp {vp:.3g} V from its typical VGS of -2.5 V at 100 "
    "µA (square law); "
    "BETA "
    "= "
    "Idss/Vp²; LAMBDA "
    "= "
    "typical "
    "|Yos| 10 µS / Idss; "
    "CGD "
    "= "
    "Crss "
    "1.5 pF, CGS = Ciss "
    "− "
    "Crss "
    "= "
    "3 "
    "pF (typical). Its "
    "gm "
    "at "
    "VGS "
    "= "
    f"0 is {2 * idss / abs(vp) * 1e3:.2g} mS against the typical 3 mS: one square law can't "
    "meet both, and the "
    "bias "
    "point "
    "matters more in a "
    "pedal",
    pts=[(0.0, idss), (-2.5, 100e-6)],
    checks=[
        (
            "idss",
            {"vds": 15.0},
            {
                "min": 1e-3,
                "typ": 3e-3,
                "max": 5e-3,
                "source": f"{ON57}, Electrical Characteristics",
            },
        ),
        (
            "vp",
            {"vds": 15.0, "id": 1e-8},
            {
                "min": -6.0,
                "max": -0.5,
                "source": f"{ON57}, Electrical Characteristics (VGS(off) at iD = 10 nA)",
            },
        ),
        (
            "vp",
            {"vds": 15.0, "id": 100e-6},
            {
                "typ": -2.5,
                "tol": 0.05,
                "source": f"{ON57}, Electrical Characteristics (VGS at iD = 100 µA, typical)",
                "note": "Fitted to, so a check of the arithmetic, not of the model",
            },
        ),
    ],
)
idss = 6e-3
vp = fm.jfet_vp(-3.5, 200e-6, idss)
part(
    id="2N5458",
    name="J2N5458",
    desc="2N5458 N-channel JFET (Rat output buffer; our model from onsemi's sheet)",
    maker="onsemi",
    url="https://www.rlocman.ru/i/File/2018/03/29/2N5457-D.pdf",
    sheet=ON57,
    fit=fm.JfetFit(idss, vp, lam=10e-6 / idss, cgs=3e-12, cgd=1.5e-12),
    method=f"Idss the sheet's typical 6 mA; Vp {vp:.3g} V from its typical VGS of -3.5 V at 200 "
    "µA (square law); "
    "BETA "
    "= "
    "Idss/Vp²; LAMBDA "
    "= "
    "typical "
    "|Yos| 10 µS / Idss; "
    "CGD "
    "= "
    "Crss "
    "1.5 pF, CGS = Ciss "
    "− "
    "Crss "
    "= "
    "3 "
    "pF (typical)",
    pts=[(0.0, idss), (-3.5, 200e-6)],
    checks=[
        (
            "idss",
            {"vds": 15.0},
            {
                "min": 2e-3,
                "typ": 6e-3,
                "max": 9e-3,
                "source": f"{ON57}, Electrical Characteristics",
            },
        ),
        (
            "vp",
            {"vds": 15.0, "id": 1e-8},
            {
                "min": -7.0,
                "max": -1.0,
                "source": f"{ON57}, Electrical Characteristics (VGS(off) at iD = 10 nA)",
            },
        ),
        (
            "vp",
            {"vds": 15.0, "id": 200e-6},
            {
                "typ": -3.5,
                "tol": 0.05,
                "source": f"{ON57}, Electrical Characteristics (VGS at iD = 200 µA, typical)",
                "note": "Fitted to, so a check of the arithmetic, not of the model",
            },
        ),
    ],
)
idss = mid(2e-3, 20e-3)
vgs = mid(-0.5, -7.5)
vp = fm.jfet_vp(vgs, 0.2e-3, idss)
part(
    id="MPF102",
    name="MPF102",
    desc="MPF102 N-channel JFET (our model from onsemi's sheet)",
    maker="onsemi",
    url="https://www.rlocman.ru/i/File/2025/11/27/MPF102-D.PDF",
    sheet=M102,
    fit=fm.JfetFit(idss, vp, cgs=4e-12, cgd=3e-12),
    method=f"Idss the geometric middle of 2-20 mA ({idss * 1e3:.3g} mA); VGS at 0.2 mA the "
    "middle of -0.5 to "
    "-7.5 "
    "V "
    f"({vgs:.3g} V), so "
    "Vp "
    f"{vp:.3g} "
    "V (square law); BETA "
    "= "
    "Idss/Vp²; CGD = Crss "
    "3 "
    "pF, "
    "CGS "
    "= Ciss − Crss = 4 "
    "pF "
    "(the "
    "sheet's maxima: it "
    "gives "
    "no "
    "typicals); no LAMBDA "
    "(the "
    "sheet gives output "
    "conductance "
    "only at 100 MHz)",
    pts=[(0.0, idss), (vgs, 0.2e-3)],
    checks=[
        (
            "idss",
            {"vds": 15.0},
            {"min": 2e-3, "max": 20e-3, "source": f"{M102}, Electrical Characteristics: IDSS"},
        ),
        (
            "vp",
            {"vds": 15.0, "id": 0.2e-3},
            {
                "min": -7.5,
                "max": -0.5,
                "source": f"{M102}, Electrical Characteristics: VGS at ID = 0.2 mA",
            },
        ),
        (
            "vp",
            {"vds": 15.0, "id": 2e-9},
            {
                "min": -8.0,
                "source": f"{M102}, Electrical Characteristics: VGS(off) at ID = 2 nA, -8 V max",
            },
        ),
    ],
)
idss = mid(5e-3, 30e-3)
vp = mid(-0.5, -3.0)
part(
    id="MPF4393",
    name="MPF4393",
    desc="MPF4393 N-channel JFET switch (our model from onsemi's sheet)",
    maker="onsemi",
    url="https://www.rlocman.ru/i/File/2025/11/27/MPF4392-D.PDF",
    sheet=M4393,
    fit=fm.JfetFit(idss, vp, cgs=3.5e-12, cgd=2.5e-12),
    method=f"Idss and Vp the geometric middles of 5-30 mA and -0.5 to -3.0 V ({idss * 1e3:.3g} "
    f"mA, {vp:.3g} V); "
    "BETA "
    "= "
    "Idss/Vp²; CGD = Crss "
    "2.5 "
    "pF, "
    "CGS = Ciss − Crss "
    "= "
    "3.5 "
    "pF "
    "(typical). Its gm "
    "at "
    "5 "
    "mA "
    "is "
    f"{2 * idss / abs(vp) * (5e-3 / idss) ** 0.5 * 1e3:.3g} mS against the sheet's typical 12 "
    "mS, and its on-resistance "
    f"{abs(vp) / (2 * idss):.3g} "
    "Ω "
    "against 100 Ω max",
    pts=[(0.0, idss), (vp, 0.0)],
    checks=[
        (
            "idss",
            {"vds": 15.0},
            {
                "min": 5e-3,
                "max": 30e-3,
                "source": f"{M4393}, Electrical Characteristics: IDSS, MPF4393",
            },
        ),
        (
            "vp",
            {"vds": 15.0, "id": 1e-8},
            {
                "min": -3.0,
                "max": -0.5,
                "source": f"{M4393}, Electrical Characteristics: VGS at ID = 10 nA, MPF4393",
            },
        ),
    ],
)
idss = mid(4e-3, 20e-3)
vp = mid(-0.7, -1.6)
part(
    id="PF5102",
    name="PF5102",
    desc="PF5102 N-channel JFET (our model from Fairchild's sheet)",
    maker="Fairchild",
    url="https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/721/PF5102.pdf",
    sheet=P51,
    fit=fm.JfetFit(idss, vp, cgs=10e-12, cgd=6e-12),
    method=f"Idss and Vp the geometric middles of 4-20 mA and -0.7 to -1.6 V ({idss * 1e3:.3g} "
    f"mA, {vp:.3g} V); "
    "BETA "
    "= "
    "Idss/Vp²; CGD = Crss "
    "6 "
    "pF, "
    "CGS "
    "= Ciss − Crss = 10 "
    "pF "
    "(the "
    "sheet's maxima: no "
    "typicals); "
    "no LAMBDA (the sheet "
    "gives "
    "only a maximum output "
    "conductance). Its "
    "gm "
    "at "
    "VGS "
    "= "
    f"0 is {2 * idss / abs(vp) * 1e3:.3g} mS against 11 mS min",
    pts=[(0.0, idss), (vp, 0.0)],
    checks=[
        (
            "idss",
            {"vds": 15.0},
            {"min": 4e-3, "max": 20e-3, "source": f"{P51}, Electrical Characteristics: IDSS"},
        ),
        (
            "vp",
            {"vds": 15.0, "id": 1e-9},
            {
                "min": -1.6,
                "max": -0.7,
                "source": f"{P51}, Electrical Characteristics: VGS(off) at ID = 1 nA",
            },
        ),
    ],
)

PKG = {
    "MPF102": "onsemi MPF102/D Rev. 3, page 1: TO-92 Style 5, 1 drain, 2 source, 3 gate",
    "MPF4393": "onsemi MPF4392/D Rev. 6, page 1: TO-92 Style 5, 1 drain, 2 source, 3 gate",
    "PF5102": "Fairchild PF5102 Rev. B0, page 1: 1. Drain 2. Source 3. Gate",
}
folder = Path("library/models/jfet")
for p in PARTS:
    card = fm.jfet_card(p["name"], p["fit"])
    (folder / f"{p['id']}.lib").write_text(
        f"* {p['desc']}\n* Built by Solum Builder from {p['sheet']} (D-161)\n{card}"
    )
    old = folder / f"{p['id']}.json"
    prev = json.loads(old.read_text()) if old.exists() else {}
    rec = {
        "id": p["id"],
        "type": "jfet",
        "description": p["desc"],
        "spice_name": p["name"],
        "kind": "model",
        "pins": [],
        "card": f"{p['id']}.lib",
        "manufacturer": p["maker"],
        "source": {
            "url": p["url"],
            "retrieved": "2026-10-29",
            "licence": LIC,
            "original": "Solum Builder fit",
        },
        "fixes": [],
        "ratings": prev.get("ratings", {}),
        "package": prev.get("package")
        or {"name": "TO-92 (DSG)", "pins": {"D": 1, "S": 2, "G": 3}, "source": PKG[p["id"]]},
        "fit": {
            "sheet": p["sheet"],
            "figure": "Electrical characteristics (no typical DC curve on the sheet)",
            "points": [list(x) for x in p["pts"]],
            "method": p["method"],
            "note": "Real units spread over the sheet's whole range; a circuit's measured Idss "
            "and Vp replace these "
            "(D-130)",
        },
        "validation": [
            {"quantity": q, "conditions": c, "simulated": 0.0, "datasheet": d}
            for q, c, d in p["checks"]
        ],
    }
    if prev.get("rating_sources"):
        rec["rating_sources"] = prev["rating_sources"]
    old.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(p["id"], card.strip())
