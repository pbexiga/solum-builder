"""Fit a BJT to its sheet's typical curves and write its .lib and .json (D-163).
Measure afterwards, from the repo root:
    make run CMD="python .claude/skills/fit-model/tools/add_model.py
        .claude/skills/fit-model/tools/remeasure.py ID..."

build(spec) takes a dict:
  id, polarity ("NPN"/"PNP"), desc, maker, url, sheet (citation), retrieved
  hfe: (figure text, vce, [(mA, hfe)...])     typical hFE curve, 25 °C
  vbe: (figure text, vce, [(mA, V)...])       VBE(on) curve
  vcs: (figure text, forced beta, [(mA, V)...])  VCE(sat) curve
  cib, cob: (figure text, [(V, pF)...])       capacitance curves (reverse volts); cib may be
                                              absent (no Cib on the sheet: CJE left out)
  rb: (ohms, how)                              RB from the sheet's rbb' (else ngspice's 0)
  isc_max: (amps, how)                         a cap on ISC where the VCE(sat) curve can't choose it
  vaf: (volts, how)                            Early voltage and where it came from
  ft: (Hz, ic A, vcb V, how)                   fT and its conditions
  checks: [(quantity, conditions, datasheet)]  the sheet's own limits
  fit_grid: mA values to fit at (default the decade 1-2-5 steps inside each curve)
  hfe_table: True when hfe's points are the table's typicals: fitted as they are, no held-out hFE
  held: mA values for the held-out checks
  note: anything the record should say
  ratings, rating_sources, package: for a part with no record yet (else the old record's are kept)
"""

import importlib.util
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location("fit_models", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)

HELD = (
    "A point of the sheet's typical curve the fit was not given (it was fitted at "
    "1-2-5 steps per decade, this sits between them)"
)


SAT_TOL = (
    "; within 7 % here, not 5 mV: the card's VCE(sat) is nearly straight against IC, the sheet's "
    "curve bends a little between 10 and 50 mA (Gummel-Poon has no quasi-saturation)"
)


def tol_for(q, typ, tol):
    """hFE within 5 %; VBE 10 mV; VCE(sat) 5 mV or 7 %, whichever is larger (a log axis)."""
    if q == "hfe":
        return round(0.05 * typ, 1)
    return round(max(tol, 0.07 * typ), 4) if q == "vce_sat" else tol


def interp(curve, xs):
    """The digitised curve read at xs (log x, linear y), only inside its span."""
    c = sorted(curve)
    lx = np.log10([p[0] for p in c])
    y = [p[1] for p in c]
    return [
        (x, float(np.interp(math.log10(x), lx, y)))
        for x in xs
        if c[0][0] * 0.999 <= x <= c[-1][0] * 1.001
    ]


def grid(curve, top=None):
    lo, hi = min(p[0] for p in curve), max(p[0] for p in curve)
    hi = min(hi, top) if top else hi
    steps = [m * 10.0**e for e in range(-4, 4) for m in (1, 2, 5)]
    return [s for s in steps if lo * 0.999 <= s <= hi * 1.001]


def build(d):
    hfe_fig, hfe_vce, hfe_curve = d["hfe"]
    scale = d.get("hfe_scale", 1.0)  # a family curve set to this part's range (see note)
    hfe_curve = [(i, v * scale) for i, v in hfe_curve]
    vbe_fig, vbe_vce, vbe_curve = d["vbe"]
    vcs_fig, forced, vcs_curve = d["vcs"]
    assert hfe_vce == vbe_vce, "hFE and VBE must share a VCE for the joint fit"
    if d.get("hfe_table"):  # the table's typical points, not a curve: fit them as they are
        h = [(i / 1e3, v) for i, v in sorted(hfe_curve)]
    else:
        h = [
            (i / 1e3, v)
            for i, v in interp(hfe_curve, d.get("fit_grid") or grid(hfe_curve, d.get("top_ma")))
        ]
    b = [
        (i / 1e3, v)
        for i, v in interp(vbe_curve, d.get("fit_grid") or grid(vbe_curve, d.get("top_ma")))
    ]
    s = [
        (i / 1e3, v)
        for i, v in interp(vcs_curve, d.get("fit_grid") or grid(vcs_curve, d.get("top_ma")))
    ]
    vaf, vaf_how = d["vaf"]
    rb, rb_how = d.get("rb", (0.0, ""))
    f = fm.fit_bjt_forward(h, b, hfe_vce, vaf, rb=rb)
    f = fm.fit_bjt_saturation(
        f, s, forced, h, hfe_vce, **({"isc_max": d["isc_max"][0]} if "isc_max" in d else {})
    )
    caps = {}
    for key, name in (("cib", "e"), ("cob", "c")):
        if key not in d:
            continue
        fig, pts = d[key]
        cj, vj, m = fm.fit_junction_cap([(v, c * 1e-12) for v, c in pts])
        caps.update({f"cj{name}": cj, f"vj{name}": vj, f"mj{name}": m})
    f = replace(f, **caps)
    ft, ft_ic, ft_vcb, ft_how = d["ft"]
    f = replace(f, tf=fm.bjt_tf(f, ft, ft_ic, ft_vcb))
    card = fm.bjt_card(d["id"], f, d["polarity"])

    folder = Path("library/models/bjt")
    (folder / f"{d['id']}.lib").write_text(
        f"* {d['desc']}\n* Fitted by Solum Builder to {d['sheet']}, its typical curves "
        f"(D-163)\n{card}"
    )

    worst = {
        "hfe": max(abs(f.forward(i, hfe_vce)[1] / v - 1) for i, v in h),
        "vbe": max(abs(f.forward(i, vbe_vce)[0] - v) for i, v in b),
        "vcs": max(abs(f.vce_sat(i, i / forced) - v) for i, v in s),
    }
    src = lambda fig: f"{d['sheet']}, {fig}"  # noqa: E731
    validation = [
        {"quantity": q, "conditions": c, "simulated": 0.0, "datasheet": ds}
        for q, c, ds in d["checks"]
    ]
    for ma in d["held"]:
        for q, curve, fig, cond, tol in (
            ("hfe", hfe_curve, hfe_fig, {"vce": hfe_vce}, None),
            ("vbe", vbe_curve, vbe_fig, {"vce": vbe_vce}, 0.01),
            ("vce_sat", vcs_curve, vcs_fig, {"ib": round(ma / 1e3 / forced, 9)}, 0.005),
        ):
            got = interp(curve, [ma])
            if not got or (q == "hfe" and d.get("hfe_table")):  # no curve between table points
                continue
            typ = round(got[0][1], 4 if q != "hfe" else 1)
            validation.append(
                {
                    "quantity": q,
                    "conditions": {"ic": round(ma / 1e3, 9), **cond},
                    "simulated": 0.0,
                    "datasheet": {
                        "typ": typ,
                        "tol": tol_for(q, typ, tol),
                        "source": src(fig),
                        "note": HELD
                        + ("; within 5 %" if q == "hfe" else "")
                        + (
                            f"; the curve times {scale:.4g} (see the fit's note)"
                            if q == "hfe" and scale != 1
                            else ""
                        )
                        + (SAT_TOL if q == "vce_sat" and typ * 0.07 > 0.005 else ""),
                    },
                }
            )
    old = (
        json.loads((folder / f"{d['id']}.json").read_text())
        if (folder / f"{d['id']}.json").exists()
        else {}
    )
    tester = [v for v in old.get("validation", []) if v["quantity"] == "tester_hfe"]
    validation += tester
    rec = {
        "id": d["id"],
        "type": "bjt",
        "description": d["desc"],
        "spice_name": d["id"],
        "kind": "model",
        "pins": [],
        "card": f"{d['id']}.lib",
        "manufacturer": d["maker"],
        "source": {
            "url": d["url"],
            "retrieved": d.get("retrieved", "2026-10-29"),
            "licence": "Our own model fitted to the maker's data sheet (D-163): the values are "
            "Solum Builder's",
            "original": "Solum Builder fit",
        },
        "fixes": [],
        "ratings": d.get("ratings", old.get("ratings", {})),
        "rating_sources": d.get("rating_sources", old.get("rating_sources", {})),
        **(
            {"package": d.get("package", old.get("package"))}
            if d.get("package", old.get("package"))
            else {}
        ),
        "fit": {
            "sheet": d["sheet"],
            "figure": "; ".join(
                [hfe_fig, vbe_fig, vcs_fig]
                + [d[k][0] for k in ("cib", "cob") if k in d]
                + ([ft_how] if ft_how else [])
            ),
            "points": [list(p) for p in h],
            "curves": {
                "vbe_on": [list(p) for p in b],
                "vce_sat": [list(p) for p in s],
                **{f"{k}o": [[v, c * 1e-12] for v, c in d[k][1]] for k in ("cib", "cob") if k in d},
            },
            "method": (
                "Gummel-Poon (scripts/fit_models.py). IS, NF, BF, ISE, NE, IKF, NKF and RE by "
                "least squares on "
                "the "
                f"hFE and VBE(on) curves at VCE = {hfe_vce:g} V together (points: the curves "
                "read at 1-2-5 steps"
                + (f"; the hFE curve times {scale:.4g}, see note" if scale != 1 else "")
                + "); "
                + (
                    f"VAF {vaf:.4g} V, {vaf_how}"
                    if math.isfinite(vaf)
                    else f"no Early voltage (VAF left out): {vaf_how}"
                )
                + ". BR, ISC, NC and RC by least squares on the VCE(sat) curve, the hFE points "
                "held, NR = NF, at "
                f"IC/IB = {forced:g}. "
                + (
                    "CJE, VJE, MJE from Cibo and CJC, VJC, MJC from Cobo against reverse voltage. "
                    if "cib" in d
                    else "CJC from Cobo (one point: VJC, MJC ngspice's defaults); no Cibo on "
                    "the sheet, so CJE "
                    "is "
                    "left "
                    "out. "
                )
                + (f"RB {rb:g} Ω, {rb_how}. " if rb else "")
                + (
                    f"ISC at most {d['isc_max'][0]:g} A: {d['isc_max'][1]}. "
                    if "isc_max" in d
                    else ""
                )
                + f"TF from fT {ft / 1e6:g} MHz at {ft_ic * 1e3:g} mA ({ft_how}), less the "
                "junctions' charging "
                "time. "
                f"Fitted curves are matched within {worst['hfe'] * 100:.1f} % (hFE), "
                f"{worst['vbe'] * 1e3:.1f} "
                "mV "
                "(VBE) "
                f"and {worst['vcs'] * 1e3:.1f} mV (VCE(sat)). {'' if rb else 'RB, '}VAR, TR and "
                "the temperature terms "
                "are "
                f"ngspice's defaults: the sheet doesn't pin them"
            ),
            "note": d.get("note", ""),
        },
        "validation": validation,
    }
    if not rec["fit"]["note"]:
        del rec["fit"]["note"]
    (folder / f"{d['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    print(d["id"], card.strip(), {k: round(v, 4) for k, v in worst.items()})
