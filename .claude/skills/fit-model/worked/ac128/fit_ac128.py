"""AC128 fitted to Valvo's data sheet (8.63), its mean curves (D-170). Writes
library/models/bjt/AC128.{lib,json}; measure afterwards with
scripts/in-dev-image.sh add_model.py .claude/skills/fit-model/worked/ac128/spec_measure.py AC128

Curves were read off the raster scan by .claude/skills/fit-model/worked/ac128/trace.py (the thick mean line's
centre per pixel row or column of a 300 dpi render, axes from grid.py's grid lines).
"""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fit_models", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)

SHEET = "Valvo AC128 data sheet (Valvo Halbleiterdioden und Transistoren, 8.63, pages 123-129)"
URL = ("https://alltransistors.com/transistor.php?transistor=21204 (its \"valvo ac128.pdf\": a scan the user "
       "supplied, 7 pages, kept as data/spec-sheets/AC128_Valvo.pdf)")
P = lambda page, what: f"{SHEET}, page {page}: {what}"  # noqa: E731

VCE = None  # every fit point at UCB = 0, as the sheet measures them (no collector leakage flows)
VAF = 29.0  # page 125, IB = 1 mA line: 100.5 mA at 0.29 V to 141.9 mA at 12.27 V
RB = 25.0  # page 124, rbb' at -UCB = 5 V, IE = 1 mA
ICBO = 3.7e-6  # page 129, mean line at 25 °C, -UCB = 10 V (table maximum 10 µA)

# Gain at UCB = 0: to 10 mA from page 126's mean IB-IE line (B = (IE - IB)/IB, IC = IE - IB, readings
# averaged over neighbouring rows); 50 and 300 mA the table's typical 90 (page 124); 750 mA from page
# 126's 0-1 A mean line (86.0; between 250 and 700 mA the trace caught grid lines); 1 A the table's 80
# (the line reads 79.9).
HFE = [(1.0, 78.8), (2.0, 76.6), (3.0, 78.4), (5.0, 79.9), (10.0, 85.8),
       (50.0, 90.0), (300.0, 90.0), (750.0, 86.0), (1000.0, 80.0)]
# VBE: page 127's mean lines at UCB = 0 (IE; IC = IE·B/(B+1), B ≈ 80-90 → × 0.988).
VBE_IE = [(0.459, 77.5), (0.59, 83.4), (0.852, 96.2), (0.984, 100.3), (1.508, 112.4), (2.033, 120.4),
          (3.082, 130.9), (4.0, 137.9), (5.049, 144.6), (6.098, 149.8), (7.016, 153.3), (8.066, 156.5),
          (9.115, 160.0), (9.902, 162.9),
          (103.7, 257.0), (133.6, 270.2), (314.9, 337.8), (396.2, 359.4), (509.9, 383.0), (607.4, 402.7),
          (704.9, 422.5), (802.4, 439.9), (997.4, 470.9)]

h = [(i / 1e3, v) for i, v in HFE]
VBE_TOP = 0.4  # A: above this the sheet's VBE bends below what rbb' = 25 Ω allows (see method)
b = [(i * 0.988 / 1e3, v / 1e3) for i, v in VBE_IE if i * 0.988 / 1e3 <= VBE_TOP]
f = fm.fit_bjt_forward(h, b, VCE, VAF, rb=RB, is_max=1e-3, icbo=(ICBO, 10.0))
cjc, vjc, mjc = fm.fit_junction_cap([(5.0, 100e-12)])  # page 124: Cb'c 100 pF at -UCB = 5 V
f = replace(f, cjc=cjc, vjc=vjc, mjc=mjc)
f = replace(f, tf=fm.bjt_tf(f, 1.5e6, 10e-3, 2.0))  # page 124: f1 1.5 MHz at -UCB = 2 V, IE = 10 mA
card = fm.bjt_card("AC128", f, "PNP", eg=0.67)

worst = {
    "hfe": max(abs(f.forward(i, VCE)[1] / v - 1) for i, v in h),
    "vbe_10mA": max(abs(f.forward(i, VCE)[0] - v) for i, v in b if i < 0.011),
    "vbe_all": max(abs(f.forward(i, VCE)[0] - v) for i, v in b),
    "vbe_1A": f.forward(0.985, VCE)[0] - 0.4709,
}
print(f)
print(card.strip(), {k: round(v, 4) for k, v in worst.items()}, "icbo", f.icbo(10.0))
for i, v in h:
    print(f"  hfe {i*1e3:7.1f} mA sheet {v:5.1f} fit {f.forward(i, VCE)[1]:5.1f}")
for i, v in b:
    print(f"  vbe {i*1e3:7.1f} mA sheet {v*1e3:5.1f} fit {f.forward(i, VCE)[0]*1e3:5.1f}")

DESC = "AC128 germanium PNP (hFE 55-175 at 50 mA), our fit to Valvo's sheet"
folder = Path("library/models/bjt")
(folder / "AC128.lib").write_text(
    f"* {DESC}\n* Fitted by Solum Builder to {SHEET}, its mean curves (D-170)\n{card}")

T = lambda what: P(124, f"Kennwerte, {what}")  # noqa: E731
HELD = "A point of the sheet's mean curve the fit was not given"
checks = [
    ("hfe", {"ic": 0.05, "vcb": 0.0}, {"min": 55.0, "max": 175.0, "source": T("B at UCB = 0, IE = 50 mA: 90 (55...175)")}),
    ("hfe", {"ic": 0.3, "vcb": 0.0}, {"min": 60.0, "max": 175.0, "source": T("B at UCB = 0, IE = 300 mA: 90 (60...175)")}),
    ("hfe", {"ic": 1.0, "vcb": 0.0}, {"min": 45.0, "max": 165.0, "source": T("B at UCB = 0, IE = 1 A: 80 (45...165)")}),
    ("vbe", {"ic": 0.05, "vcb": 0.0}, {"max": 0.3, "source": T("-UBE at UCB = 0, IE = 50 mA: ≤ 300 mV")}),
    ("vbe", {"ic": 0.3, "vcb": 0.0}, {"max": 0.45, "source": T("-UBE at UCB = 0, IE = 300 mA: ≤ 450 mV")}),
    ("icbo", {"vcb": 10.0}, {"max": 1e-5, "source": T("-ICBO at -UCB = 10 V: ≤ 10 µA"),
                             "note": "The card's own is the mean, 3.7 µA (page 129 at 25 °C); a measured unit's leakage replaces it (D-130)"}),
    ("hfe", {"ic": 0.03, "vce": 1.0}, {"typ": 88.1, "tol": 4.4, "source": P(128, "B bei -UCE = 1 V"), "note": HELD + "; within 5 %"}),
    ("hfe", {"ic": 0.15, "vce": 1.0}, {"typ": 90.4, "tol": 4.5, "source": P(128, "B bei -UCE = 1 V"), "note": HELD + "; within 5 %"}),
    ("vbe", {"ic": 0.0015, "vcb": 0.0}, {"typ": 0.1124, "tol": 0.01, "source": P(127, "-UBE against IE, UCB = 0, Mittelwert"), "note": HELD}),
    ("vbe", {"ic": 0.007, "vcb": 0.0}, {"typ": 0.1533, "tol": 0.01, "source": P(127, "-UBE against IE, UCB = 0, Mittelwert"), "note": HELD}),
]
validation = [{"quantity": q, "conditions": c, "simulated": 0.0, "datasheet": d} for q, c, d in checks]
validation += [
    {"quantity": "iceo", "conditions": {"vcc": 9.0, "rc": 2400.0}, "simulated": 0.0,
     "note": "Leakage on the Geofex tester (D-130): base open, collector through 2.4 kΩ to 9 V. The model's own; a measured leakage replaces it."},
    {"quantity": "tester_hfe", "conditions": {"vcc": 9.0, "rc": 2400.0, "rb": 2200000.0}, "simulated": 0.0,
     "note": "Gain on the Geofex tester (D-130, D-153): 9 V, collector through 2.4 kΩ, 2.2 MΩ from base to supply; collector current less the leakage, over the base current. Where a measured transistor's form starts."},
]
rec = {
    "id": "AC128", "type": "bjt", "description": DESC, "spice_name": "AC128", "kind": "model", "pins": [],
    "card": "AC128.lib", "manufacturer": "Valvo (Philips)",
    "source": {"url": URL, "retrieved": "2026-10-29",
               "licence": "Our own model fitted to the maker's data sheet (D-163): the values are Solum Builder's",
               "original": "Solum Builder fit"},
    "fixes": [],
    "ratings": {"vceo": 16.0, "ic": 1.0},
    "rating_sources": {
        "vceo": P(128, "minimum -UCE against ZBE: 16 V with the base open (32 V only with RBE ≤ 500 Ω, page 123)"),
        "ic": P(123, "Absolute Grenzwerte: -IC max. 1 A"),
    },
    "package": {"name": "TO-1 (EBC)", "pins": {"E": 1, "B": 2, "C": 3},
                "source": P(123, "outline: E, B, C in a line, the red dot on the collector side")},
    "fit": {
        "sheet": SHEET,
        "figure": "page 126 IB against IE at UCB = 0 (mean, to 10 mA); page 128 B bei -UCE = 1 V (10 to 500 mA); "
                  "page 127 -UBE against IE at UCB = 0 (mean, both ranges); page 124 table (rbb', Cb'c, f1); "
                  "page 129 ICBO at 25 °C; page 125 output curves (VAF)",
        "points": [list(p) for p in h],
        "curves": {"vbe_on": [list(p) for p in b], "cobo": [[5.0, 100e-12]]},
        "method": (
            "Gummel-Poon (scripts/fit_models.py). IS, NF, BF, ISE, NE, IKF, NKF and RE by least squares on the gain "
            "and VBE points together, taken as at VCE = 1 V (the UCB = 0 curves sit at VCE ≈ VBE, 0.1-0.47 V: the "
            "sheet gives VBE's change with VCE as 0.4 mV/V, and the Early effect moves the gain 2-3 %, less than the "
            "two gain figures disagree at 10 mA: 86 at UCB = 0, 82 at 1 V). RB 25 Ω, the sheet's rbb'. VAF 29 V "
            "from the IB = 1 mA output line (the 2 mA line gives 43 V; the curves above it are heated). BR set so "
            "ICBO at 10 V is the mean 3.7 µA, NR = NF: there is no VCE(sat) curve, and IS alone would leak "
            "far more (an alloy transistor's reverse gain is high). CJC from Cb'c 100 pF at 5 V with the default "
            "grading; no emitter capacitance given. TF from f1 1.5 MHz at 10 mA. EG 0.67 (germanium): with "
            "XTI 3 the card's VBE moves −2.2 mV/K against the sheet's −2.3. "
            f"Fitted points are matched within {worst['hfe'] * 100:.1f} % (gain) and "
            f"{worst['vbe_10mA'] * 1e3:.1f} mV (VBE to 10 mA; {worst['vbe_all'] * 1e3:.0f} mV over the whole curve). "
            "The curves are raster scans, read by .claude/skills/fit-model/worked/ac128/trace.py"),
        "note": ("One AC128 for every unit (D-170): the sheet's gain spread is 55 to 175, so a circuit sets its "
                 "transistors' measured hFE and leakage (D-130). The ElectroSmash cards AC128-B85 and "
                 "AC128-B120 are replaced; old circuits migrate to this card with those gains."),
    },
    "validation": validation,
}
(folder / "AC128.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
