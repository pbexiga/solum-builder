"""Each card's checks against its sheet: the table's min/typ/max lines and held-out points of
the curves (points the fit was not given: IC at IB within 5 %, VBE within 10 mV, as D-163's
held-out hFE and VBE). Quantities: model_checks' (hfe, vbe, vce_sat, icbo, iceo, tester_hfe)
and gefit's (ic_at_ib, vbe_at_ie, vbe_at_ib, small_hfe). Currents in A, volts in V
(magnitudes, PNP)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")

CHECKS: dict[str, list[dict]] = {}
TESTER = [
    {"name": "Geofex tester gain (9 V, 2.4 kΩ, 2.2 MΩ; D-130)", "kind": "tester_hfe",
     "c": {"vcc": 9.0, "rc": 2400.0, "rb": 2200000.0}, "src": "", "note": "The card's own gain on the tester (where a measured form starts)"},
    {"name": "Geofex tester leakage (base open, 9 V, 2.4 kΩ), µA", "kind": "iceo",
     "c": {"vcc": 9.0, "rc": 2400.0}, "scale": 1e6, "src": "", "note": "The card's own leakage on the tester"},
]


def held(points, kind, vce, every, tol_frac=None, tol_v=None, src="", scale=1.0, unit=""):
    out = []
    for a, b in points[::every]:
        if kind == "ic_at_ib":
            out.append({"name": f"held: IC at IB {a*1e6:.1f} µA, VCE {vce:g} V (mA)", "kind": kind,
                        "c": {"ib": a, "vce": vce}, "d": {"typ": b, "tol": b * tol_frac}, "scale": 1e3, "src": src})
        elif kind in ("vbe_at_ie", "vbe_at_ib"):
            key = "ie" if kind == "vbe_at_ie" else "ib"
            lbl = f"{a*1e3:.3g} mA" if a >= 1e-3 else f"{a*1e6:.3g} µA"
            out.append({"name": f"held: VBE at {key.upper()} {lbl}, VCE {vce:g} V (mV)", "kind": kind,
                        "c": {key: a, "vce": vce}, "d": {"typ": b, "tol": tol_v}, "scale": 1e3, "unit": " mV", "src": src})
    return out


def oc71() -> list[dict]:
    import fit_oc71 as f

    T = lambda what: f.P(2, f"characteristics at Tj = 25 °C, {what}")  # noqa: E731
    c = [
        {"name": "Ico at Vcb 4.5 V (µA)", "kind": "icbo", "c": {"vcb": 4.5}, "d": {"typ": 4.5e-6, "max": 13e-6},
         "scale": 1e6, "unit": " µA", "src": T("Ico (Vc = -4.5 V, Ie = 0): 4.5 av., 13 max µA"),
         "note": "Fitted to the average; a measured unit's leakage replaces it (D-130)"},
        {"name": "I'co, base open, Vce 4.5 V (µA)", "kind": "ic_at_ib", "c": {"ib": 0.0, "vce": 4.5},
         "d": {"typ": 150e-6, "max": 325e-6}, "scale": 1e6, "unit": " µA", "src": T("I'co (Vc = -4.5 V, Ib = 0): 150 av., 325 max µA")},
        {"name": "Vbe at Ic 1 mA, Vce 4.5 V (mV)", "kind": "vbe", "c": {"ic": 1e-3, "vce": 4.5},
         "d": {"min": 0.115, "typ": 0.135, "max": 0.155}, "scale": 1e3, "unit": " mV",
         "src": T("Vbe (Vc = -4.5 V, Ic = 1 mA): -115 min, -135 av., -155 max mV")},
        {"name": "Vce bottoming at Ic 9 mA, Ib 0.5 mA (mV)", "kind": "vce_sat", "c": {"ic": 9e-3, "ib": 0.5e-3},
         "d": {"typ": 0.080, "max": 0.210}, "scale": 1e3, "unit": " mV",
         "src": T("collector bottoming voltage (Ic = 9 mA, Ib = 0.5 mA): -80 av., -210 max mV")},
        {"name": "h'21e small-signal at Ic 3 mA, Vce 2 V", "kind": "small_hfe", "c": {"ic": 3e-3, "vce": 2.0},
         "d": {"min": 30.0, "typ": 47.0, "max": 75.0}, "src": f.P(4, "grounded emitter h'21: 30 min, 47 av., 75 max (Vc = -2 V, Ie = 3 mA, 1 kc/s)")},
        {"name": "h'21e small-signal at Ic 1 mA, Vce 2 V (typical only)", "kind": "small_hfe", "c": {"ic": 1e-3, "vce": 2.0},
         "d": {"typ": 41.0}, "src": f.P(3, "grounded emitter h'21: 41 (Vc = -2 V, Ie = 1 mA)")},
        {"name": "DC hFE at Ic 1 mA, Vce 4.5 V (info: no table line)", "kind": "hfe", "c": {"ic": 1e-3, "vce": 4.5}, "src": ""},
    ]
    S12 = f.P(12, "transfer characteristic, Vc = -4.5 V (by pixel)")
    S13 = f.P(13, "spread of transfer characteristic, Average line (by pixel)")
    S7 = f.P(7, "IE against Vbe, Vc = -4.5 V (by pixel)")
    S11 = f.P(11, "spread of input characteristic, Average line (by pixel)")
    ht = [p for p in f.HELD_T if p[1] < 2e-3]
    hh = [p for p in f.HELD_T if p[1] >= 2e-3]
    c += held(ht, "ic_at_ib", 4.5, 5, tol_frac=0.05, src=S12)
    c += held(hh, "ic_at_ib", 4.5, 6, tol_frac=0.05, src=S13)
    c += held(f.HELD_V, "vbe_at_ie", 4.5, 3, tol_v=0.010, src=S7)
    above = [(i * 1e-3, v * 1e-3) for i, v in f.D["p7_vbe_ie_mA"] if i > f.VBE_TOP][::2]
    for ch in held(above, "vbe_at_ie", 4.5, 1, tol_v=0.010, src=S7):
        ch["name"] = ch["name"].replace("held:", "above the fit range:")
        c.append(ch)
    inp = [(ib * 1e-6, v * 1e-3) for ib, v in f.D["p11_input_avg"]]
    c += held(inp, "vbe_at_ib", 4.5, 4, tol_v=0.010, src=S11)
    return c + TESTER


def oc44() -> list[dict]:
    import fit_oc44 as f

    T = lambda what: f.P("D2", f"characteristics at Tj = 25 °C, {what}")  # noqa: E731
    c = [
        {"name": "Ico at Vcb 2 V (µA)", "kind": "icbo", "c": {"vcb": 2.0}, "d": {"typ": 0.5e-6, "max": 2.0e-6},
         "scale": 1e6, "unit": " µA", "src": T("Ico (Vcb = -2 V, Ie = 0): 0.5 typ., 2.0 max µA"),
         "note": "Fitted with the gain; a measured unit's leakage replaces it (D-130)"},
        {"name": "Ico at Vcb 15 V (µA)", "kind": "icbo", "c": {"vcb": 15.0}, "d": {"max": 10e-6},
         "scale": 1e6, "unit": " µA", "src": T("Ico (Vcb = -15 V, Ie = 0): 10 max µA")},
        {"name": "I'co, base open, Vce 2 V (µA)", "kind": "ic_at_ib", "c": {"ib": 0.0, "vce": 2.0},
         "d": {"typ": 25e-6, "max": 75e-6}, "scale": 1e6, "unit": " µA", "src": T("I'co (Vce = -2 V, Ib = 0): 25 typ., 75 max µA")},
        {"name": "I'c, base reversed +500 mV, Vce 15 V (µA)", "kind": "ic_at_vbe", "c": {"vbe": -0.5, "vce": 15.0},
         "d": {"typ": 1.0e-6, "max": 50e-6}, "scale": 1e6, "unit": " µA", "src": T("I'c (Vce = -15 V, Vbe = +500 mV): 1.0 typ., 50 max µA")},
        {"name": "Collector knee voltage at Ic 5 mA (Ib for 6 mA at 1 V) (mV)", "kind": "knee",
         "c": {"ic_set": 6e-3, "vce_set": 1.0, "ic": 5e-3}, "d": {"min": 0.080, "typ": 0.140, "max": 0.200},
         "scale": 1e3, "unit": " mV", "src": T("Vce(knee) at Ic = 5 mA (fig. 1: Ib adjusted so Ic = 6 mA at Vce = -1 V): -80 min, -140 typ., -200 max mV")},
        {"name": "Vce bottoming at Ic 8 mA, Ib 500 µA (mV)", "kind": "vce_sat", "c": {"ic": 8e-3, "ib": 0.5e-3},
         "d": {"min": 0.020, "typ": 0.045, "max": 0.150}, "scale": 1e3, "unit": " mV",
         "src": T("collector bottoming voltage (Ic = 8 mA, Ib = 500 µA): -20 min, -45 typ., -150 max mV")},
        {"name": "Vbe at Ic 1 mA, Vce 6 V (mV)", "kind": "vbe", "c": {"ic": 1e-3, "vce": 6.0},
         "d": {"min": 0.125, "typ": 0.150, "max": 0.185}, "scale": 1e3, "unit": " mV",
         "src": T("base input voltage (Vce = -6 V, Ic = 1 mA): -125 min, -150 typ., -185 max mV")},
        {"name": "α' small-signal at Ie 1 mA, Vce 6 V", "kind": "small_hfe", "c": {"ic": 1e-3, "vce": 6.0},
         "d": {"min": 40.0, "typ": 100.0, "max": 225.0}, "src": f.P("D3", "α' (at 1 kc/s, Vc = -6 V, Ie = 1 mA): 40 min, 100 typ., 225 max")},
        {"name": "DC hFE at Ic 1 mA, Vce 6 V (info: no table line)", "kind": "hfe", "c": {"ic": 1e-3, "vce": 6.0}, "src": ""},
    ]
    S2 = f.P("C2", "transfer characteristic, Vc = -2 V (by pixel)")
    S1 = f.P("C1", "IC against Vbe, Vc = -2 V (by pixel)")
    c += held(f.HELD_T, "ic_at_ib", 2.0, 2, tol_frac=0.05, src=S2)
    for ch in held(f.HELD_V, "vbe_at_ie", 2.0, 5, tol_v=0.010, src=S1):  # C1 is against IC: check it so
        ch["kind"], ch["c"] = "vbe", {"ic": ch["c"]["ie"], "vce": 2.0}
        ch["name"] = ch["name"].replace("at IE", "at IC")
        c.append(ch)
    return c + TESTER


def oc75() -> list[dict]:
    import fit_oc75 as f

    T = lambda what: f.P("D2", f"characteristics at Tj = 25 °C, {what}")  # noqa: E731
    H = lambda what: f.PH(3, f"common emitter, {what}")  # noqa: E731
    c = [
        {"name": "Ico at Vcb 4.5 V (µA)", "kind": "icbo", "c": {"vcb": 4.5}, "d": {"typ": 4.5e-6, "max": 12e-6},
         "scale": 1e6, "unit": " µA", "src": T("Ico (Vc = -4.5 V, Ie = 0): 4.5 av., 14 max µA") + "; " + f.PH(2, "-ICBO (-VCB = 4.5 V) = 4.5, < 12 µA") + " (the tighter maximum)",
         "note": "Fitted to the average; a measured unit's leakage replaces it (D-130)"},
        {"name": "ICEO, base open, Vce 4.5 V (µA) [Philips]", "kind": "ic_at_ib", "c": {"ib": 0.0, "vce": 4.5},
         "d": {"typ": 350e-6, "max": 550e-6}, "scale": 1e6, "unit": " µA", "src": H("-ICEO (-VCE = 4.5 V) = 350, < 550 µA")},
        {"name": "IC at IB 10 µA, Vce 4.5 V (mA) [Philips]", "kind": "ic_at_ib", "c": {"ib": 10e-6, "vce": 4.5},
         "d": {"min": 0.75e-3, "typ": 1.1e-3, "max": 1.9e-3}, "scale": 1e3, "unit": " mA", "src": H("-IC (-VCE = 4.5 V, -IB = 10 µA) = 1.1, > 0.75, < 1.9 mA")},
        {"name": "VBE at IB 10 µA, Vce 4.5 V (mV) [Philips]", "kind": "vbe_at_ib", "c": {"ib": 10e-6, "vce": 4.5},
         "d": {"min": 0.090, "typ": 0.120, "max": 0.175}, "scale": 1e3, "unit": " mV", "src": H("-VBE (-VCE = 4.5 V, -IB = 10 µA) = 120, > 90, < 175 mV")},
        {"name": "IC at IB 250 µA, Vce 4.5 V (mA) [Philips]", "kind": "ic_at_ib", "c": {"ib": 250e-6, "vce": 4.5},
         "d": {"min": 13.5e-3, "typ": 22e-3, "max": 33e-3}, "scale": 1e3, "unit": " mA", "src": H("-IC (-VCE = 4.5 V, -IB = 250 µA) = 22, > 13.5, < 33 mA")},
        {"name": "VBE at IB 250 µA, Vce 4.5 V (mV) [Philips]", "kind": "vbe_at_ib", "c": {"ib": 250e-6, "vce": 4.5},
         "d": {"min": 0.210, "typ": 0.270, "max": 0.385}, "scale": 1e3, "unit": " mV", "src": H("-VBE (-VCE = 4.5 V, -IB = 250 µA) = 270, > 210, < 385 mV")},
        {"name": "Vbe at Ic 3 mA, Vce 4.5 V (mV)", "kind": "vbe", "c": {"ic": 3e-3, "vce": 4.5},
         "d": {"min": 0.100, "typ": 0.140, "max": 0.210}, "scale": 1e3, "unit": " mV",
         "src": T("base input voltage (Vc = -4.5 V, Ic = 3 mA): -100 min, -140 av., -210 max mV")},
        {"name": "Vce bottoming at Ic 9 mA, Ib 0.5 mA (mV)", "kind": "vce_sat", "c": {"ic": 9e-3, "ib": 0.5e-3},
         "d": {"typ": 0.090, "max": 0.210}, "scale": 1e3, "unit": " mV",
         "src": T("collector bottoming voltage (Ic = 9 mA, Ib = 0.5 mA): -90 av., -210 max mV")},
        {"name": "α' small-signal at Ic 3 mA, Vce 2 V", "kind": "small_hfe", "c": {"ic": 3e-3, "vce": 2.0},
         "d": {"min": 60.0, "typ": 90.0, "max": 130.0}, "src": f.P("D2", "α' (Vc = -2 V, Ie = 3 mA): 60 min, 90 av., 130 max; Philips h21e 90 (> 65, < 130)")},
        {"name": "DC hFE at Ic 3 mA, Vce 4.5 V (info: no table line)", "kind": "hfe", "c": {"ic": 3e-3, "vce": 4.5}, "src": ""},
    ]
    S6 = f.P("C6", "transfer characteristic and its Average spread line, Vc = -4.5 V (by pixel)")
    S1 = f.P("C1", "IE against Veb, Vc = -4.5 V (by pixel)")
    S5 = f.P("C5", "spread of input characteristic, Average line (by pixel)")
    c += held(f.HELD_T, "ic_at_ib", 4.5, 3, tol_frac=0.05, src=S6)
    c += held(f.HELD_V, "vbe_at_ie", 4.5, 3, tol_v=0.010, src=S1)
    inp = [(ib * 1e-6, v * 1e-3) for ib, v in f.D["c5_input_avg"]]
    c += held(inp, "vbe_at_ib", 4.5, 3, tol_v=0.010, src=S5)
    return c + TESTER


def oc81d() -> list[dict]:
    """The estimate (D-186) has one table line: the cross-reference book's hFE min."""
    src = ("transistor cross-reference book, page 242 (data/spec-sheets/Germanium_OC_crossref.pdf): OC81D row, "
           "hFE 20 min at IC 5 mA (no VCE given; the OC75's 4.5 V assumed)")
    return [
        {"name": "DC hFE at Ic 5 mA, Vce 4.5 V (cross-reference min 20)", "kind": "hfe", "c": {"ic": 5e-3, "vce": 4.5},
         "d": {"min": 20.0}, "src": src},
        {"name": "Vbe at Ic 3 mA, Vce 4.5 V (info: the OC75's, kept)", "kind": "vbe", "c": {"ic": 3e-3, "vce": 4.5}, "src": ""},
        {"name": "Ico at Vcb 4.5 V (info: the OC75's, kept)", "kind": "icbo", "c": {"vcb": 4.5}, "scale": 1e6, "unit": " µA", "src": ""},
    ] + TESTER


def _load(path: str, name: str):
    """A fit script by path under its own module name (n404/ and n1308/ both have a fit.py)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, f".claude/skills/fit-model/worked/germanium/{path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def n2n404() -> list[dict]:
    """2N404 (RCA): the table's limits; each line of Figs. 3/4 (IC between the minimum and maximum
    curves) and 7/8 (VBE(sat) between them); Fig. 2's minimum hFE as information only (it
    contradicts the table, see n404/fit.py)."""
    f = _load("n404/fit.py", "fit_2n404")

    T = f.T
    c = [
        {"name": "hFE at Ic 12 mA, Vce 0.15 V", "kind": "hfe", "c": {"ic": 12e-3, "vce": 0.15}, "d": {"min": 30.0, "typ": 50.0},
         "src": T("hFE at VCE -0.15 V, IC -12 mA: 30 min, 50 typ")},
        {"name": "hFE at Ic 24 mA, Vce 0.2 V", "kind": "hfe", "c": {"ic": 24e-3, "vce": 0.2}, "d": {"min": 24.0, "typ": 40.0},
         "src": T("hFE at VCE -0.2 V, IC -24 mA: 24 min, 40 typ")},
        {"name": "VCE(sat) at Ic 12 mA, Ib 0.4 mA (mV)", "kind": "vce_sat", "c": {"ic": 12e-3, "ib": 0.4e-3},
         "d": {"typ": 0.10, "max": 0.15}, "scale": 1e3, "unit": " mV", "src": T("VCE(sat) at IC -12 mA, IB -0.4 mA: 0.1 typ, 0.15 max V")},
        {"name": "VCE(sat) at Ic 24 mA, Ib 1 mA (mV)", "kind": "vce_sat", "c": {"ic": 24e-3, "ib": 1e-3},
         "d": {"typ": 0.12, "max": 0.20}, "scale": 1e3, "unit": " mV", "src": T("VCE(sat) at IC -24 mA, IB -1 mA: 0.12 typ, 0.2 max V")},
        {"name": "VBE(sat) at Ic 12 mA, Ib 0.4 mA (mV)", "kind": "vbe_sat", "c": {"ic": 12e-3, "ib": 0.4e-3},
         "d": {"typ": 0.25, "max": 0.35}, "scale": 1e3, "unit": " mV", "src": T("VBE(sat) at IC -12 mA, IB -0.4 mA: 0.25 typ, 0.35 max V")},
        {"name": "VBE(sat) at Ic 24 mA, Ib 1 mA (mV)", "kind": "vbe_sat", "c": {"ic": 24e-3, "ib": 1e-3},
         "d": {"typ": 0.32, "max": 0.40}, "scale": 1e3, "unit": " mV", "src": T("VBE(sat) at IC -24 mA, IB -1 mA: 0.32 typ, 0.4 max V")},
        {"name": "ICBO at Vcb 12 V (µA)", "kind": "icbo", "c": {"vcb": 12.0}, "d": {"typ": 2e-6, "max": 5e-6},
         "scale": 1e6, "unit": " µA", "src": T("ICBO at VCB -12 V, IE 0: 2 typ, 5 max µA"),
         "note": "Fitted with the saturation and the IEBO; a measured unit's leakage replaces it (D-130)"},
    ]
    S3 = f.P(3, "Figs. 3 (minimum) and 4 (maximum) collector characteristics (by pixel)")
    for ib in ("0.5", "1", "2", "3", "4"):
        lo, hi = dict(map(tuple, f.D["fig3_min_ic"][ib])), dict(map(tuple, f.D["fig4_max_ic"][ib]))
        for v in (0.3, 0.68):
            if v in lo and v in hi:
                c.append({"name": f"IC at IB {ib} mA, VCE {v:g} V, between Figs. 3 and 4 (mA)", "kind": "ic_at_ib",
                          "c": {"ib": float(ib) * 1e-3, "vce": v}, "d": {"min": lo[v] * 1e-3, "max": hi[v] * 1e-3},
                          "scale": 1e3, "unit": " mA", "src": S3})
    S7 = f.P(4, "Figs. 7 (maximum) and 8 (minimum) base characteristics, VBE against IC at fixed IB (by pixel)")
    for ib, ic in (("0.5", 12.5), ("1", 12.5), ("1", 27.5), ("2", 27.5), ("4", 27.5)):
        hi, lo = dict(map(tuple, f.D["fig7_max_vbe"][ib])), dict(map(tuple, f.D["fig8_min_vbe"][ib]))
        c.append({"name": f"VBE(sat) at Ic {ic:g} mA, Ib {ib} mA, between Figs. 8 and 7 (mV)", "kind": "vbe_sat",
                  "c": {"ic": ic * 1e-3, "ib": float(ib) * 1e-3}, "d": {"min": lo[ic], "max": hi[ic]},
                  "scale": 1e3, "unit": " mV", "src": S7,
                  "miss": "the sheet gives no rbb', so RB is 0 (D-163) and VBE(sat) rises less with the base current than Figs. 7/8 "
                          "draw: 12-16 mV under Fig. 8's minimum at IB 1-4 mA, under 1 mV at a pedal's base current"})
    S2 = f.P(1, "Fig. 2, minimum hFE (by pixel); information only: it reads above the table's minimum, see the fit's note")
    for vce in ("0.5", "0.15"):
        line = dict((round(i), h) for i, h in f.D["fig2_min_hfe"][vce])
        for ma in (2, 12, 31):
            if ma in line:
                c.append({"name": f"hFE at Ic {ma} mA, Vce {vce} V (info: Fig. 2 minimum {line[ma]:.1f})", "kind": "hfe_info",
                          "c": {"ic": ma * 1e-3, "vce": float(vce)}, "src": S2})
    return c + TESTER


CHECKS["2N404"] = n2n404()

def n2n1308() -> list[dict]:
    """2N1308 (TI): its table column's limits; held-out points of the normalised gain curve (at the
    fit's level, within 5 %); the family's VCE and VBE lines as information (no one type's)."""
    import json as _json

    f = _load("n1308/fit.py", "fit_2n1308")

    T = f.T
    c = [
        {"name": "hFE at Ic 10 mA, Vce 1 V", "kind": "hfe", "c": {"ic": 10e-3, "vce": 1.0}, "d": {"min": 80.0, "typ": 150.0},
         "src": T("hFE at IC 10 mA, VCE 1 V: 80 min, 150 design centre")},
        {"name": "hFE at Ic 200 mA, Vce 0.35 V", "kind": "hfe", "c": {"ic": 0.2, "vce": 0.35}, "d": {"min": 20.0},
         "src": T("hFE at IC 200 mA, VCE 0.35 V: 20 min")},
        {"name": "VBE at Ic 10 mA, Ib 0.5 mA (mV)", "kind": "vbe_sat", "c": {"ic": 10e-3, "ib": 0.5e-3},
         "d": {"min": 0.20, "typ": 0.24, "max": 0.30}, "scale": 1e3, "unit": " mV", "src": T("VBE at IC 10 mA, IB 0.5 mA: 0.20 min, 0.24 centre, 0.30 max V")},
        {"name": "VCE(sat) at Ic 10 mA, Ib 0.13 mA (mV)", "kind": "vce_sat", "c": {"ic": 10e-3, "ib": 0.13e-3},
         "d": {"typ": 0.10, "max": 0.15}, "scale": 1e3, "unit": " mV", "src": T("VCE(sat) at IC 10 mA, IB 0.13 mA: 0.10 centre, 0.15 max V")},
        {"name": "ICBO at Vcb 25 V (µA)", "kind": "icbo", "c": {"vcb": 25.0}, "d": {"typ": 3e-6, "max": 6e-6},
         "scale": 1e6, "unit": " µA", "src": T("ICBO at VCB 25 V, IE 0: 3 centre, 6 max µA"),
         "note": "Fitted with the IEBO; a measured unit's leakage replaces it (D-130)"},
    ]
    rec = _json.loads(Path(".claude/skills/fit-model/worked/germanium/2N1308.json").read_text())
    level = float(rec["fit"]["method"].split("a free level: ")[1].split(" x")[0])
    curve = f.D["hfe_norm_npn"]
    used = {round(p.a * 1e3, 2) for p in f.HFE}
    for ic, n in curve[4::16]:
        if round(ic, 2) not in used:
            typ = round(150.0 * n * level, 1)
            c.append({"name": f"held: hFE at Ic {ic:.0f} mA, Vce 1 V (curve x {level:g} x 150)", "kind": "hfe",
                      "c": {"ic": round(ic * 1e-3, 6), "vce": 1.0}, "d": {"typ": typ, "tol": round(0.05 * typ, 1)},
                      "src": f.F("normalised N-P-N hFE against IC, at the fit's level"),
                      "note": "A point of the normalised curve the fit was not given, within 5 %"})
    for ib in ("1", "5", "20", "50"):
        for ic, v in f.D[f"vce_ib{ib}"][::max(1, len(f.D[f"vce_ib{ib}"]) // 2)][:2]:
            c.append({"name": f"VCE at Ic {ic:.0f} mA, Ib {ib} mA (info: family line {v * 1e3:.0f} mV)", "kind": "vce_sat_info",
                      "c": {"ic": ic * 1e-3, "ib": float(ib) * 1e-3}, "scale": 1e3, "src": ""})
    for ib in ("1", "5", "10", "30"):
        ic, v = f.D[f"vbe_ib{ib}"][0]
        c.append({"name": f"VBE at Ic {ic:.0f} mA, Ib {ib} mA (info: family line {v * 1e3:.0f} mV)", "kind": "vbe_sat_info",
                  "c": {"ic": ic * 1e-3, "ib": float(ib) * 1e-3}, "scale": 1e3, "src": ""})
    return c + TESTER


CHECKS["2N1308"] = n2n1308()
CHECKS["OC81D"] = oc81d()
CHECKS["OC71"] = oc71()
CHECKS["OC44"] = oc44()
CHECKS["OC75"] = oc75()
if __name__ == "__main__":
    print(json.dumps({k: len(v) for k, v in CHECKS.items()}))
    Path  # noqa: B018
