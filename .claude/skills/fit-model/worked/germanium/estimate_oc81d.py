"""OC81D, estimated (D-186): no OC81D sheet with curves was found (Mullard Vol. 4 Part III 1968
and Philips 1958-60 / 1965 skip it), so our OC75 fit (D-184) is scaled by the ratio of the two
parts' rows in the transistor cross-reference book, page 242 (data/spec-sheets/
Germanium_OC_crossref.pdf), both columns from the same book:
  hFE min   OC75 55 at 10 mA, OC81D 20 at 5 mA   -> base current × 55/20 (BF × k, ISE ÷ k)
  Cob max   OC75 50 pF, OC81D 40 pF               -> CJC × 0.8
  fT min    OC75 100 kHz, OC81D 200 kHz           -> TF × 0.5
VBE (IS, NF), leakage (BR), VAF, RE and EG stay the OC75's: the table has nothing on them.
Writes OC81D.{lib,json} here; then `run.sh measure.py OC81D` fills its validation.
run.sh estimate_oc81d.py"""
import json
import re
from pathlib import Path

HERE = Path(".claude/skills/fit-model/worked/germanium")
OC75 = Path("library/models/bjt/OC75.lib")
XREF = ("transistor cross-reference book, page 242 (data/spec-sheets/Germanium_OC_crossref.pdf; "
        "datasheetarchive.com DSA841000-11)")
K_HFE = 20 / 55
K_CJC = 40 / 50
K_TF = 100e3 / 200e3


def params(card: str) -> dict[str, str]:
    body = re.search(r"PNP\((.*)\)", card).group(1)
    return dict(kv.split("=") for kv in body.split())


def scaled(p: dict[str, str]) -> dict[str, str]:
    out = dict(p)
    out["bf"] = f"{float(p['bf']) * K_HFE:.4g}"
    out["ise"] = f"{float(p['ise']) / K_HFE:.4g}"
    out["cjc"] = f"{float(p['cjc']) * K_CJC:.4g}"
    out["tf"] = f"{float(p['tf']) * K_TF:.4g}"
    return out


def main() -> None:
    p = scaled(params(OC75.read_text()))
    desc = "OC81D germanium PNP (Mullard, audio driver), estimated from our OC75 fit: no OC81D sheet"
    card = "\n".join([
        f"* {desc}",
        f"* Estimated by Solum Builder (D-186): the OC75 card (D-184) scaled by the OC81D's row",
        f"* against the OC75's in the {XREF}:",
        "* base current x 55/20 (hFE min), CJC x 40/50 (Cob max), TF x 1/2 (fT min).",
        ".model OC81D PNP(" + " ".join(f"{k}={v}" for k, v in p.items()) + ")",
        ""])
    (HERE / "OC81D.lib").write_text(card)
    path = HERE / "OC81D.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    row = f"{XREF}: OC81D row"
    rec = {
        "id": "OC81D", "type": "bjt", "description": desc, "spice_name": "OC81D", "kind": "model",
        "pins": [], "card": "OC81D.lib", "manufacturer": "Mullard",
        "source": {"url": "https://www.datasheetarchive.com (DSA841000-11, kept as data/spec-sheets/Germanium_OC_crossref.pdf)",
                   "retrieved": "2026-11-02",
                   "licence": "Our own estimate (D-186): the values are Solum Builder's",
                   "original": "Solum Builder estimate"},
        "fixes": [],
        "ratings": {"vceo": 16.0, "ic": 0.01},
        "rating_sources": {"vceo": f"{row}: VCE max 16 V", "ic": f"{row}: IC max 10 mA"},
        "package": {"name": "X02 (lead code L03, e b c in a line, as the OC75)", "pins": {"E": 1, "B": 2, "C": 3},
                    "source": f"{row}: package X02, lead info L03 (the OC75, OC71 and OC44 rows are L03 too)"},
        "fit": {
            "sheet": "no OC81D curve sheet: our OC75 fit (D-184) scaled by the cross-reference book's OC81D row",
            "figure": f"{XREF}: the OC75 and OC81D rows (hFE min and its bias, Cob max, fT min)",
            "points": [],
            "method": (".claude/skills/fit-model/worked/germanium/estimate_oc81d.py: the OC75 card with base current x 55/20 "
                       "(BF x 20/55, ISE x 55/20: hFE min 20 at 5 mA against 55 at 10 mA), CJC x 40/50 "
                       "(Cob max 40 pF against 50), TF x 1/2 (fT min 200 kHz against 100 kHz); VBE, "
                       "leakage, VAF and RE kept"),
            "note": ("Estimated, not fitted: no OC81D sheet with curves was found, so this is the OC75's "
                     "shape at the OC81D's lower gain. Give a measured hFE and leakage (D-130)."),
        },
        "validation": old.get("validation", []),
    }
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(card)


if __name__ == "__main__":
    main()
