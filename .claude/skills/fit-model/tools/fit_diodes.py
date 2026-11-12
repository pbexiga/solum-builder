"""Fit 1N60 and BAT42 (D-156) and write their .lib and .json; measure afterwards with
make run CMD="python .claude/skills/fit-model/tools/add_model.py
    .claude/skills/fit-model/tools/remeasure.py 1N60 BAT42", from the repo root."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("fit_models", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)

N60 = [
    (0.2989, 0.7963),
    (0.4454, 2.4508),
    (0.586, 4.5721),
    (0.7192, 7.1121),
    (0.8431, 10.0709),
    (0.9571, 13.3936),
    (1.0595, 17.0595),
    (1.15, 21.0343),
    (1.2272, 25.27),
]
B42 = [
    (0.1399, 0.01065),
    (0.1448, 0.01287),
    (0.1497, 0.01571),
    (0.1554, 0.01899),
    (0.1603, 0.02292),
    (0.1868, 0.06353),
    (0.2136, 0.176),
    (0.2413, 0.4856),
    (0.2705, 1.329),
    (0.2763, 1.605),
    (0.2828, 1.959),
    (0.2893, 2.366),
    (0.3061, 3.774),
    (0.3253, 5.906),
    (0.3475, 9.019),
    (0.3734, 13.37),
    (0.3889, 16.31),
    (0.4061, 19.7),
    (0.471, 33.86),
    (0.5406, 49.86),
    (0.6129, 68.05),
    (0.6861, 93.04),
    (0.7253, 112.4),
    (0.7612, 135.8),
    (0.7955, 165.7),
    (0.8314, 200.2),
]

XY = "Wuxi Xuyang Electronic 1N60P/1N60 data sheet, rev. b (Point Contact Germanium Diodes)"
VI42 = "Vishay BAT42/BAT43 data sheet, Rev. 2.2, 12-May-2025 (doc 85660)"
HELD = (
    "A point of the typical curve the fit was not given (every other point was held out); "
    "±50 mV, as for the "
    "1N4148's "
    "curve points"
)
PARTS = [
    dict(
        id="1N60",
        desc="1N60 point-contact germanium diode: a very soft, low clipper (our fit to Wuxi "
        "Xuyang's sheet)",
        maker="Wuxi Xuyang Electronic",
        url="https://akizukidenshi.com/goodsaffix/1N60P_1N60_point_rev.b.pdf",
        sheet=XY,
        figure="Forward Characteristics (page 2), read from the PDF's vector drawing",
        pts=N60,
        is_max=50e-6,
        extra={"cjo": 1e-12, "eg": 0.67, "bv": 45.0, "ibv": 100e-6},
        extra_note="CJO is the sheet's 1 pF maximum at −1 V; EG 0.67 eV (germanium); BV 45 V, "
        "the peak reverse "
        "voltage",
        is_note="IS held at 50 µA, half the sheet's 100 µA reverse-current limit at 10 V (IS is "
        "the model's reverse "
        "current): "
        "left free it came "
        "out "
        "at "
        "118 "
        "µA, over the limit, "
        "while "
        "held "
        "at 50 µA the held-out "
        "points "
        "stay within 44 mV. "
        "The "
        "sheet's "
        "typical reverse curve "
        "reads "
        "about 5 µA at 10 "
        "V, "
        "so "
        "the "
        "model leaks more "
        "than "
        "a "
        "typical unit",
        note="The figure is linear and starts at 0.8 mA, so below that the fit follows the "
        "diode equation, not "
        "the "
        "sheet. "
        "A crude, soft curve "
        "(N "
        "4.3): "
        "a "
        "point-contact part, "
        "and "
        "the "
        "sheet's own drawing",
        checks=[
            (
                "vf",
                {"if": 4e-3},
                {
                    "max": 1.0,
                    "source": f"{XY}, Characteristics: forward current at least 4 mA at VF = 1 V",
                    "note": "The sheet gives a minimum current at 1 V; the same limit read as "
                    "VF at 4 mA",
                },
            ),
            (
                "ir",
                {"vr": 10.0},
                {
                    "max": 100e-6,
                    "source": f"{XY}, Characteristics: IR at VR = 10 V, 1N60 100 µA max",
                },
            ),
        ],
        ratings={"if_avg": 0.05, "vr_max": 20.0},
        rating_sources={
            "if_avg": f"{XY}, Absolute Maximum Ratings: average rectified output current 50 mA",
            "vr_max": f"{XY}, Absolute Maximum Ratings: reverse voltage dc 20 V",
        },
    ),
    dict(
        id="BAT42",
        desc="BAT42 small-signal Schottky (30 V): a low clipper, between germanium and silicon "
        "(our fit to Vishay's "
        "sheet)",
        maker="Vishay",
        url="https://wwwlegacy.vishay.com/docs/85660/bat42.pdf",
        sheet=VI42,
        figure="Fig. 2 - Typical Forward Characteristics, Tj = 25 °C, read from the PDF's "
        "vector drawing",
        pts=B42,
        is_max=0.5e-6,
        extra={"cjo": 7e-12, "bv": 30.0, "ibv": 100e-6},
        extra_note="CJO is the sheet's 7 pF typical at 1 V; BV 30 V at 100 µA, the sheet's "
        "breakdown test",
        is_note="IS held under the sheet's 0.5 µA reverse-current limit at 25 V (it fits at "
        "0.23 µA)",
        note="The fit takes every other point plus the curve's last (200 mA), so the sheet's "
        "200 mA limit holds. "
        "Held-out "
        "points are within "
        "22 "
        "mV "
        "up "
        "to "
        "20 mA and 63 mV at "
        "93 "
        "mA, "
        "where the sheet's "
        "curve "
        "bends "
        "more sharply than "
        "one "
        "diode "
        "does",
        checks=[
            (
                "vf",
                {"if": 10e-3},
                {
                    "max": 0.4,
                    "source": f"{VI42}, Electrical characteristics: VF at IF = 10 mA, BAT42",
                },
            ),
            (
                "vf",
                {"if": 50e-3},
                {
                    "max": 0.65,
                    "source": f"{VI42}, Electrical characteristics: VF at IF = 50 mA, BAT42",
                },
            ),
            (
                "vf",
                {"if": 0.2},
                {"max": 1.0, "source": f"{VI42}, Electrical characteristics: VF at IF = 200 mA"},
            ),
            (
                "ir",
                {"vr": 25.0},
                {
                    "max": 0.5e-6,
                    "source": f"{VI42}, Electrical characteristics: leakage current at VR = 25 V",
                },
            ),
        ],
        ratings={"if_avg": 0.2, "vr_max": 30.0},
        rating_sources={
            "if_avg": f"{VI42}: Forward continuous current 200 mA",
            "vr_max": f"{VI42}: Repetitive peak reverse voltage 30 V",
        },
    ),
]

for d in PARTS:
    pts = [(v, ma / 1000) for v, ma in d["pts"]]
    fitted = pts[0::2] + ([pts[-1]] if len(pts) % 2 == 0 else [])
    held = [p for p in pts if p not in fitted]
    f = fm.fit_diode(fitted, is_max=d["is_max"])
    card = fm.diode_card(d["id"], f, **d["extra"])
    folder = Path("library/models/diode")
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
                "conditions": {"if": round(i, 8)},
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
        "type": "diode",
        "description": d["desc"],
        "spice_name": d["id"],
        "kind": "model",
        "pins": [],
        "card": f"{d['id']}.lib",
        "manufacturer": d["maker"],
        "source": {
            "url": d["url"],
            "retrieved": "2026-10-29",
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
            "method": "IS, N and RS by least squares on V = N·Vt·ln(I/IS) + RS·I "
            "(scripts/fit_models.py "
            "fit_diode, Vt at "
            "27 "
            "°C) "
            "over "
            "every other curve "
            "point; " + d["is_note"] + "; " + d["extra_note"],
            "note": d["note"],
        },
        "validation": validation,
    }
    (folder / f"{d['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(d["id"], card.strip())
