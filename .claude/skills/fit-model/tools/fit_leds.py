"""Fit the three Kingbright LEDs (D-156) and write their .lib and .json (validation is
measured afterwards by add_model.py's update mode). Run from the repo root."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("fit_models", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)

GD = [
    (1.7886, 0.1071),
    (1.8136, 0.3223),
    (1.8335, 0.5374),
    (1.8435, 0.7525),
    (1.8535, 0.8601),
    (1.8585, 1.0743),
    (1.8679, 1.397),
    (1.8829, 2.0415),
    (1.8929, 2.4577),
    (1.9129, 3.5324),
    (1.9229, 3.9627),
    (1.9328, 4.6072),
    (1.9428, 5.0365),
    (1.9478, 5.4536),
    (1.9528, 5.6679),
    (1.9578, 5.9906),
    (1.9678, 6.4208),
    (1.9978, 8.0324),
    (2.0322, 9.9528),
    (2.0672, 11.9815),
    (2.1021, 14.0094),
    (2.1321, 16.0513),
    (2.1665, 17.9717),
]
QB = [
    (2.455, 0.2711),
    (2.5544, 0.8148),
    (2.6538, 1.8998),
    (2.6936, 2.7153),
    (2.7321, 3.5307),
    (2.762, 4.0744),
    (2.8017, 4.8876),
    (2.8415, 5.9396),
    (2.8813, 7.0268),
    (2.941, 8.3837),
    (3.0006, 10.0146),
    (3.069, 12.187),
    (3.1486, 14.5958),
    (3.2182, 17.04),
    (3.2579, 18.3969),
    (3.2964, 19.9924),
    (3.3462, 22.1648),
    (3.3959, 24.6089),
    (3.4556, 27.2918),
    (3.5053, 30.0078),
]
QW = [
    (2.4549, 0.2719),
    (2.5544, 0.8152),
    (2.6539, 1.8995),
    (2.6936, 2.7144),
    (2.7321, 3.5271),
    (2.762, 4.0704),
    (2.8017, 4.8853),
    (2.8813, 7.0562),
    (2.941, 8.379),
    (3.0006, 10.0066),
    (3.069, 12.1775),
    (3.1485, 14.62),
    (3.2181, 17.0294),
    (3.258, 18.3853),
    (3.2965, 20.013),
    (3.3462, 22.1838),
    (3.3959, 24.5932),
    (3.4556, 27.3074),
    (3.5053, 30.0193),
]

KB = "https://www.kingbrightusa.com/images/catalog/SPEC/"
LIC = "Our own fit to the maker's datasheet curve (D-156): the values are Solum Builder's"
LEDS = [
    dict(
        id="WP7113GD",
        colour="green",
        chem="GaP",
        pts=GD,
        url=KB + "WP7113GD.pdf",
        sheet="Kingbright WP7113GD data sheet, Spec No DSAE9335, Rev. V.12B (04/02/2019)",
        test=(10e-3, 2.0, 2.4),
        cjo=15e-12,
        if_max=25e-3,
        ir=10e-6,
    ),
    dict(
        id="WP7113QBC-D",
        colour="blue",
        chem="InGaN",
        pts=QB,
        url=KB + "WP7113QBC-D.pdf",
        sheet="Kingbright WP7113QBC/D data sheet, Spec No DSAG3481, Rev. V.18B (03/26/2025)",
        test=(20e-3, 3.3, 4.0),
        cjo=None,
        if_max=30e-3,
        ir=50e-6,
    ),
    dict(
        id="WP7113QWC-D",
        colour="white",
        chem="InGaN",
        pts=QW,
        url=KB + "WP7113QWC-D.pdf",
        sheet="Kingbright WP7113QWC/D data sheet, Spec No DSAI6407, Rev. V.6B (10/09/2023)",
        test=(20e-3, 3.3, 4.0),
        cjo=100e-12,
        if_max=30e-3,
        ir=50e-6,
    ),
]

for led in LEDS:
    pts = [(v, ma / 1000) for v, ma in led["pts"] if ma >= 1.0]  # linear plot: below 1 mA is noise
    fitted, held = pts[0::2], pts[1::2]
    f = fm.fit_diode(fitted)
    extra = {"bv": 5.0, "ibv": led["ir"]}
    if led["cjo"]:
        extra = {"cjo": led["cjo"], **extra}
    name = led["id"].replace("-", "_")
    card = fm.diode_card(name, f, **extra)
    figure = "Forward Current vs. Forward Voltage (page 3), read from the PDF's vector drawing"
    desc = (
        f"{led['colour'].capitalize()} 5 mm LED, {led['chem']} (our fit to Kingbright "
        f"{led['id'].replace('-', '/')}'s sheet)"
    )
    folder = Path("library/models/led")
    (folder / f"{led['id']}.lib").write_text(
        f"* {desc}\n* Fitted by Solum Builder to {led['sheet']}, {figure} (D-156)\n{card}"
    )
    i_t, typ, mx = led["test"]
    checks = sorted(held, key=lambda p: p[1])
    pick = [checks[0], checks[len(checks) // 2], checks[-1]]
    validation = [
        {
            "quantity": "vf",
            "conditions": {"if": i_t},
            "simulated": 0.0,
            "datasheet": {
                "source": f"{led['sheet']}, Electrical / optical characteristics: VF at IF = "
                f"{i_t * 1000:g} mA",
                "typ": typ,
                "tol": 0.1,
                "max": mx,
                "note": "±0.1 V, as for the red LED (D-118)",
            },
        }
    ]
    for v, i in pick:
        validation.append(
            {
                "quantity": "vf",
                "conditions": {"if": round(i, 6)},
                "simulated": 0.0,
                "datasheet": {
                    "source": f"{led['sheet']}, {figure}",
                    "typ": round(v, 4),
                    "tol": 0.05,
                    "note": "A point of the typical curve the fit was not given (every other "
                    "point was held out); "
                    "±50 "
                    "mV, "
                    "as for the 1N4148's "
                    "curve "
                    "points",
                },
            }
        )
    rec = {
        "id": led["id"],
        "type": "led",
        "description": desc,
        "spice_name": name,
        "kind": "model",
        "pins": [],
        "card": f"{led['id']}.lib",
        "manufacturer": "Kingbright",
        "source": {
            "url": led["url"],
            "retrieved": "2026-10-29",
            "licence": LIC,
            "original": "Solum Builder fit",
        },
        "fixes": [],
        "ratings": {"if_avg": led["if_max"], "vr_max": 5.0},
        "rating_sources": {
            "if_avg": f"{led['sheet']}, Absolute maximum ratings: DC forward current "
            f"{led['if_max'] * 1000:g} "
            "mA",
            "vr_max": f"{led['sheet']}, Absolute maximum ratings: reverse voltage 5 V",
        },
        "fit": {
            "sheet": led["sheet"],
            "figure": figure,
            "points": [list(p) for p in fitted],
            "method": "IS, N and RS by least squares on V = N·Vt·ln(I/IS) + RS·I "
            "(scripts/fit_models.py "
            "fit_diode, Vt at "
            "27 "
            "°C) "
            "over "
            "every other curve "
            "point "
            "from "
            "1 "
            "mA up; "
            + ("CJO is the sheet's capacitance; " if led["cjo"] else "")
            + f"BV 5 V, IBV {led['ir'] * 1e6:g} µA: the sheet's reverse current limit at 5 V",
            "note": "Below 1 mA the linear-scale figure can't be read, so the fit's low-current "
            "behaviour is the "
            "diode "
            "equation's, not the "
            "sheet's",
        },
        "validation": validation,
    }
    (folder / f"{led['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(led["id"], f, card.strip())
