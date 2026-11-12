"""Write a fitted card and its record in the shape of library/models/bjt/AC128.{lib,json}, into
this folder only (.claude/skills/fit-model/worked/germanium/<ID>.{lib,json}). measure.py fills `validation`."""
import json
from pathlib import Path

HERE = Path(".claude/skills/fit-model/worked/germanium")


def write_record(mid: str, f, card: str, m: dict) -> None:
    (HERE / f"{mid}.lib").write_text(
        f"* {m['description']}\n* Fitted by Solum Builder to {m['sheet']}, {m.get('basis', 'its typical curves')} "
        f"(germanium study, .claude/skills/fit-model/worked/germanium/NOTES.md)\n{card}")
    path = HERE / f"{mid}.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    w = m["worst"]
    rec = {
        "id": mid, "type": "bjt", "description": m["description"], "spice_name": mid, "kind": "model",
        "pins": [], "card": f"{mid}.lib", "manufacturer": m["manufacturer"],
        "source": {"url": m["url"], "retrieved": "2026-11-03",
                   "licence": "Our own model fitted to the maker's data sheet (D-163): the values are Solum Builder's",
                   "original": "Solum Builder fit"},
        "fixes": [], "ratings": m["ratings"], "rating_sources": m["rating_sources"], "package": m["package"],
        "fit": {
            "sheet": m["sheet"], "figure": m["figure"], "points": [[ic, ic / ib] for ib, ic in m["points"] if ib > 0],  # (IC, gain), 9c
            "curves": {"transfer": m["points"], **m["curves"]},
            "method": (m["method"] + ". " + (m.get("fitted") or (
                       f"Fitted points within {abs(w['transfer_worst_frac']) * 100:.1f} % (IC at IB) and "
                       f"{abs(w['vbe_worst_V']) * 1e3:.1f} mV (VBE); ICBO {w['icbo_A'] * 1e6:.2f} µA"))
                       + ". Curves read off the raster by pixel (.claude/skills/fit-model/worked/germanium/pix.py)"),
            "note": m.get("note", "Provisional: a germanium-study card, not in the library (the AC128 stands in, D-170)."),
        },
        "validation": old.get("validation", []),
    }
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
