"""Our own level-1 2SK184-GR from Toshiba's sheet, as the 2SK209-GR (D-216). Run in the dev image
from the repo root: python .claude/skills/fit-model/worked/2sk184/fit_2sk184.py

Idss: the geometric middle of the GR grade. Vp: from the sheet's typical |Yfs|-IDSS line
(digitised by .claude/skills/fit-model/worked/2sk184/yfs.py) through the square law, gm0 = 2·Idss/|Vp|.
"""

import importlib.util
import json
from pathlib import Path

from solum.model_checks import measure
from solum.models import Model, ModelInfo, ModelLibrary, load_models
from solum.sim.native import native_engine

spec = importlib.util.spec_from_file_location("fm", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)

SHEET = "Toshiba 2SK184 data sheet (2007-11-01)"
URL = "https://www.rfparts.com/fileuploader/download/download/?d=0&file=custom%2Fupload%2FFile-1737740953.pdf"
ID = "2SK184-GR"
NAME = "J2SK184GR"
DESC = "2SK184-GR low-noise N-channel JFET, GR grade (the Boss BD-2's; our model from Toshiba's sheet)"

idss = fm.middle(2.6e-3, 6.5e-3)
yfs = 8.91e-3 * (idss * 1e3) ** 0.4594  # |Yfs| at VGS = 0, the sheet's typical line
vp = -2 * idss / yfs
lam = 0.006  # as the 2SK209-GR's (see method)
fit = fm.JfetFit(idss, vp, lam=lam, cgs=10e-12, cgd=3e-12)
method = (
    f"Idss the geometric middle of the GR grade's 2.6-6.5 mA ({idss * 1e3:.3g} mA). Vp "
    f"{vp:.3g} V from the typical |Yfs|-IDSS figure ({yfs * 1e3:.3g} mS at that Idss) by "
    "the square law, Vp = -2·Idss/|Yfs|, as the 2SK209-GR (D-216): the sheet's tables and "
    "figures are the 2SK209's, its |Yfs| line within 1 % of that one's. The VGS(OFF)-IDSS "
    "figure is read at 0.1 µA, in the tail a square law doesn't follow, so it isn't used. "
    "BETA = Idss/Vp². LAMBDA 0.006 as the 2SK209-GR's: the 2SK184's ID-VDS figure (low "
    "voltage region, VGS = 0) is as flat as that one's at the figure's resolution. CGD = Crss 3 pF, CGS = Ciss − Crss = 10 pF "
    "(typical)."
)
checks = [
    ("idss", {"vds": 10.0}, {"min": 2.6e-3, "max": 6.5e-3,
                             "source": f"{SHEET}, Electrical Characteristics: IDSS at VDS = 10 V, GR 2.6~6.5 mA"}),
    ("vp", {"vds": 10.0, "id": 1e-7}, {"min": -1.5, "max": -0.2,
                                       "source": f"{SHEET}, Electrical Characteristics: VGS(OFF) at VDS = 10 V, ID = 0.1 µA"}),
]  # fmt: skip

folder = Path("library/models/jfet")
card = fm.jfet_card(NAME, fit)
lib_text = f"* {DESC}\n* Built by Solum Builder from {SHEET} (D-161, D-216, D-255)\n{card}"
(folder / f"{ID}.lib").write_text(lib_text)
rec = {
    "id": ID, "type": "jfet", "description": DESC, "spice_name": NAME, "kind": "model",
    "pins": [], "card": f"{ID}.lib", "manufacturer": "Toshiba",
    "source": {"url": URL, "retrieved": "2026-11-10",
               "licence": "Our own model built from the maker's data sheet (D-159, D-161): the values are Solum Builder's",
               "original": "Solum Builder fit"},
    "datasheet": URL, "fixes": [], "ratings": {},
    "package": {"name": "TO-92 mini (Toshiba 2-4E1C)", "pins": {"D": 1, "G": 2, "S": 3},
                "source": f"{SHEET}, page 1: 1. Drain 2. Gate 3. Source"},
    "fit": {"sheet": SHEET,
            "figure": "|Yfs| - IDSS, ID - VGS and ID - VDS (typical, page 2)",
            "points": [[0.0, idss], [vp, 0.0]], "method": method,
            "note": "Real units spread over the grade's range; a circuit's measured Idss and Vp replace these (D-130)"},
}  # fmt: skip
info = ModelInfo.model_validate({**rec, "validation": []})
lib = load_models([Path("library/models")])
models = ModelLibrary({**{k: lib.get(k) for k in lib.ids() if k != ID}, ID: Model(info, lib_text)})
engine = native_engine()
rec["validation"] = []
for q, cond, sheet in checks:
    sim = float(f"{measure(engine, models, models.get(ID), q, cond):.6g}")
    ok = sheet.get("min", -1e9) <= sim <= sheet.get("max", 1e9)
    print(q, cond, sim, "OK" if ok else "FAIL")
    rec["validation"].append({"quantity": q, "conditions": cond, "simulated": sim, "datasheet": sheet})
ModelInfo.model_validate(rec)
(folder / f"{ID}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
print(card.strip())
