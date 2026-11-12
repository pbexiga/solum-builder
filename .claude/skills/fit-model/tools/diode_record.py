"""Write a fitted diode's .lib and .json (D-156); measure afterwards with add_model.py update mode.
write(part) where part holds id, desc, maker, url, sheet, figure, pts [(V, mA)], is_max,
extra (card params), extra_note, is_note, note, checks [(quantity, conditions, datasheet)],
ratings, rating_sources, and optionally split (amps: a two-diode subcircuit) and type."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("fit_models", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)
HELD = (
    "A point of the typical curve the fit was not given (every other point was held out); "
    "±50 mV, as for the "
    "1N4148's "
    "curve points"
)
METHOD = (
    "IS, N and RS by least squares on V = N·Vt·ln(I/IS) + RS·I (scripts/fit_models.py "
    "fit_diode, Vt at "
    "27 "
    "°C) "
    "over "
    "every other curve "
    "point, "
    "the "
    "curve's last point "
    "always "
    "included"
)
PAIR = (
    "Two diodes in parallel (scripts/fit_models.py fit_diode_pair, D-159): the first fitted, "
    "as one diode is, "
    "to "
    "the "
    "points "
    "up to {split:g} mA; "
    "the "
    "second "
    "to the current the "
    "points "
    "above that carry "
    "beyond "
    "the "
    "first"
)


def write(d: dict) -> None:
    typ = d.get("type", "diode")
    pts = [(v, ma / 1000) for v, ma in d["pts"]]
    fitted = pts[0::2] + ([pts[-1]] if len(pts) % 2 == 0 else [])
    held = [p for p in pts if p not in fitted]
    fitted = [(v, ma / 1000) for v, ma in d.get("also", [])] + fitted  # points from another figure
    split = d.get("split")
    name = d["id"].replace("-", "_")
    if split:
        f = fm.fit_diode_pair(fitted, split, is_max=d.get("is_max"))
        card = fm.diode_pair_card(name, f, **d["extra"])
        kind, pins, method = "subckt", ["A", "K"], PAIR.format(split=split * 1e3)
    else:
        f = fm.fit_diode(fitted, is_max=d.get("is_max"))
        card = fm.diode_card(name, f, **d["extra"])
        kind, pins, method = "model", [], METHOD
    folder = Path(f"library/models/{typ}")
    (folder / f"{d['id']}.lib").write_text(
        f"* {d['desc']}\n* Fitted by Solum Builder to {d['sheet']}, {d['figure']} (D-156)\n{card}"
    )
    pick = [held[0], held[len(held) // 2], held[-1]]
    validation = [
        {"quantity": q, "conditions": c, "simulated": 0.0, "datasheet": ds}
        for q, c, ds in d["checks"]
    ]
    for v, i in pick:
        validation.append(
            {
                "quantity": "vf",
                "conditions": {"if": float(f"{i:.6g}")},
                "simulated": 0.0,
                "datasheet": {
                    "source": f"{d['sheet']}, {d['figure']}",
                    "typ": round(v, 4),
                    "tol": 0.05,
                    "note": HELD,
                },
            }
        )
    rec = {
        "id": d["id"],
        "type": typ,
        "description": d["desc"],
        "spice_name": name,
        "kind": kind,
        "pins": pins,
        "card": f"{d['id']}.lib",
        "manufacturer": d["maker"],
        "source": {
            "url": d["url"],
            "retrieved": d.get("retrieved", "2026-10-29"),
            "licence": "Our own fit to the maker's datasheet curve (D-156): the values are "
            "Solum Builder's",
            "original": "Solum Builder fit",
        },
        "fixes": [],
        "ratings": d["ratings"],
        "rating_sources": d["rating_sources"],
        "fit": {
            "sheet": d["sheet"],
            "figure": d["figure"],
            "points": [list(p) for p in fitted],
            "method": "; ".join(
                x for x in (method, d.get("is_note", ""), d.get("extra_note", "")) if x
            ),
            "note": d.get("note", ""),
        },
        "validation": validation,
    }
    old = folder / f"{d['id']}.json"
    if old.exists():  # keep what the fit doesn't own (package, …)
        prev = json.loads(old.read_text())
        for k in ("package",):
            if k in prev:
                rec[k] = prev[k]
    if d.get("description_keep") and old.exists():
        rec["description"] = json.loads(old.read_text())["description"]
    old.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(d["id"], card.strip())
