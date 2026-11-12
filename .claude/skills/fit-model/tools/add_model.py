"""Write library/models/<type>/<ID>.{lib,json} from a spec, measuring every validation.

python add_model.py SPECS.py ID [ID...]   (in the dev image: make run CMD="python … add_model.py …")
A spec (a dict in SPECS.py's SPECS) holds: id, type, description, src (local card file),
url, retrieved, licence, original, manufacturer, spice_name, pins, channels, package,
ratings, rating_sources, validation [{quantity, conditions, datasheet}], extract
("subckt" | "model" | "file"), header (extra comment lines for the .lib).
An existing record's fields not in the spec are kept (update mode: `update: True`).
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

from solum.model_checks import measure
from solum.models import Model, ModelInfo, ModelLibrary, clean_card, load_models, logical_lines
from solum.sim.native import native_engine

ROOT = Path("library/models")


def extract(text: str, name: str, how: str) -> str:
    text = text.replace("\r", "")
    if how == "file":
        return text
    lines = text.splitlines()
    if how == "subckt":
        out, inside = [], False
        for ln in lines:
            w = ln.strip().split()
            if (
                not inside
                and len(w) > 1
                and w[0].lower() == ".subckt"
                and w[1].lower() == name.lower()
            ):
                inside = True
            if inside:
                out.append(ln)
                if w and w[0].lower().startswith(".ends"):
                    break
        if not out:
            raise SystemExit(f"no .subckt {name}")
        # .model lines a subckt uses but defines outside it: pull them in too
        body = "\n".join(out)
        return body + "\n"
    for ln in logical_lines(text):
        w = ln.strip().split()
        if len(w) > 1 and w[0].lower() == ".model" and w[1].lower() == name.lower():
            return ln + "\n"
    raise SystemExit(f"no .model {name}")


def main() -> None:
    spec_path, ids = sys.argv[1], sys.argv[2:]
    s = importlib.util.spec_from_file_location("specs", spec_path)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    specs = {sp["id"]: sp for sp in mod.SPECS}
    lib = load_models([ROOT])
    engine = native_engine()
    for mid in ids:
        sp = dict(specs[mid])
        folder = ROOT / sp["type"]
        folder.mkdir(exist_ok=True)
        jpath = folder / f"{mid}.json"
        old = json.loads(jpath.read_text()) if jpath.exists() else {}
        if sp.pop("update", False):
            rec = old
            card_text = (folder / old["card"]).read_text() if old.get("card") else ""
        else:
            raw = extract(
                Path(sp["src"]).read_text(encoding="utf-8", errors="replace"),
                sp.get("extract_name", sp["spice_name"]),
                sp["extract"],
            )
            cleaned = clean_card(raw)
            head = [f"* {sp['description']}", f"* Source: {sp['url']}", *sp.get("header", [])]
            card_text = "\n".join(head) + "\n" + cleaned.text
            if sp.get("rename"):  # spice name clash: rename the model in the card
                a, b = sp["rename"]
                card_text = re.sub(
                    rf"(?i)(\.(?:model|subckt)\s+){re.escape(a)}\b", rf"\g<1>{b}", card_text
                )
            (folder / f"{mid}.lib").write_text(card_text)
            rec = {
                "id": mid,
                "type": sp["type"],
                "description": sp["description"],
                "spice_name": sp.get("rename", [None, sp["spice_name"]])[1],
                "kind": "subckt" if sp.get("pins") else "model",
                "pins": sp.get("pins", []),
                "card": f"{mid}.lib",
                "manufacturer": sp.get("manufacturer") or cleaned.manufacturer,
                "source": {
                    "url": sp["url"],
                    "retrieved": sp["retrieved"],
                    "licence": sp["licence"],
                    "original": sp.get("original", ""),
                },
                "fixes": cleaned.fixes,
                "ratings": {**cleaned.ratings, **sp.get("ratings", {})},
                "rating_sources": sp.get("rating_sources", {}),
            }
            if sp["type"] == "opamp":
                rec["channels"] = sp.get("channels", 1)
        for key in ("description", "ratings", "rating_sources", "package", "channels"):
            if key in sp and sp.get("update_" + key, True):
                rec[key] = (
                    {**rec.get(key, {}), **sp[key]}
                    if key in ("ratings", "rating_sources")
                    else sp[key]
                )
        info = ModelInfo.model_validate({**rec, "validation": []})
        models = ModelLibrary({**{k: lib.get(k) for k in lib.ids()}, mid: Model(info, card_text)})
        vals = [v for v in rec.get("validation", []) if not sp.get("replace_validation")]
        for v in sp.get("validation", []):
            vals.append(dict(v))
        for v in vals:
            if "simulated" not in v or sp.get("remeasure"):
                x = measure(engine, models, models.get(mid), v["quantity"], v["conditions"])
                v["simulated"] = float(f"{x:.6g}")
            d = v.get("datasheet") or {}
            x = v["simulated"]
            ok = (
                (d.get("min") is None or x >= d["min"])
                and (d.get("max") is None or x <= d["max"])
                and (d.get("tol") is None or abs(x - d["typ"]) <= d["tol"])
            )
            print(
                f"{mid:10} {v['quantity']:9} {v['conditions']} sim {x:.6g} sheet min "
                f"{d.get('min')} typ "
                f"{d.get('typ')} max "
                f"{d.get('max')} {'OK' if ok else 'FAIL'}"
            )
        rec["validation"] = vals
        ModelInfo.model_validate(rec)
        jpath.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
