"""2N1308 fitted to TI's sheet (2N1302-2N1309, bulletin DL-S 1136, August 1959;
data/spec-sheets/2N1302-2N1309_TI.pdf). Curves read by n1308/digit.py -> n1308/data.json. Writes
.claude/skills/fit-model/worked/germanium/2N1308.{lib,json}. Run: run.sh n1308/fit.py

TI's curves are "design characteristics" for all eight types, PNP and NPN, except where a curve
says otherwise; the table gives each type's design centre. So:
- the level is the 2N1308's own table column (weighted x3, the table wins, D-163): hFE 150 at
  10 mA, VCE 1 V; VBE 0.24 V at 10 mA, IB 0.5 mA; VCE(sat) 0.10 V at 10 mA, IB 0.13 mA; ICBO 3 µA at
  25 V; IEBO 2 µA at 25 V (a symmetrical alloy: the emitter junction is rated 25 V too);
- the gain against current is the normalised N-P-N curve (unity at 25 mA, 22 to 300 mA), its
  shape only (a free level), at VCE 1 V (the curve names no voltage; the table's hFE is at 1 V);
- the family's VCE against IC lines (IB 1 to 50 mA) give only the bulk resistance, RC 1.28 Ω: their
  slope at IB 20 and 50 mA (deep saturation, where VCE is IC x RC plus 5 mV), which the types share.
  Fitted as drawn, the lines pull the gain down (a lower-gain type's lines: at a given IB its VCE
  is higher) and the table's VCE(sat) misses by 30 mV (n1308/out_fit_with_vce.txt); so they are
  checks, as are the family's VBE against IC lines: the table's VBE centre differs by type (0.35 V
  for the 2N1302 to 0.24 V for the 2N1308, same test), so a family line is no one type's.
Nothing below 10 mA: the card's gain there is its own extrapolation (the curve falls towards low
current from its 90 mA peak, and the card carries that on).
"""
import dataclasses
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import alloy as a  # noqa: E402
from record import write_record  # noqa: E402

D = json.loads(Path(".claude/skills/fit-model/worked/germanium/n1308/data.json").read_text())
SHEET = "TI 2N1302-2N1309 data sheet (bulletin DL-S 1136, August 1959)"
P = lambda page, what: f"{SHEET}, page {page}: {what}"  # noqa: E731
T = lambda what: P(2, f"N-P-N design characteristics at 25 °C, 2N1308, {what}")  # noqa: E731
F = lambda what: P(5, f"design characteristics (all types), {what} (by pixel)")  # noqa: E731
W = 3.0

TABLE = [
    a.Point("hfe", 10e-3, 1.0, 150.0, weight=W, src=T("hFE at IC 10 mA, VCE 1 V: 80 min, 150 design centre")),
    a.Point("vbe_sat", 10e-3, 0.5e-3, 0.24, weight=W, src=T("VBE at IC 10 mA, IB 0.5 mA: 0.20 min, 0.24 centre, 0.30 max V")),
    a.Point("vce_sat", 10e-3, 0.13e-3, 0.10, weight=W, src=T("VCE(sat) at IC 10 mA, IB 0.13 mA: 0.10 centre, 0.15 max V")),
    a.Point("icbo", 25.0, 0.0, 3e-6, weight=W, src=T("ICBO at VCB 25 V: 3 centre, 6 max µA")),
    a.Point("iebo", 25.0, 0.0, 2e-6, weight=W, src=T("IEBO at VEB 25 V: 2 centre, 6 max µA")),
]
HFE = [a.Point("hfe", ic * 1e-3, 1.0, 150.0 * n, group="hfe", src=F("normalised N-P-N hFE against IC"))
       for ic, n in D["hfe_norm_npn"][::8]]
VCE = [a.Point("vce_sat", ic * 1e-3, float(ib) * 1e-3, v, src=F(f"VCE against IC at IB {ib} mA"))
       for ib in ("1", "5", "10", "20", "50") for ic, v in D[f"vce_ib{ib}"][::(4 if ib in ("1", "50") else 10)]]

X0 = dict(is_=-6.0, nf=1.05, bf=2.3, ise=-8.0, ne=1.6, ikf=-0.7, re=0.3, nkf=0.5, br=1.0, isc=-8.0, nc=1.5, rc=0.8)
RC = 1.28  # page 5, VCE against IC: (0.3837 - 0.3304) / (295.6 - 253.9 mA) at IB 50 mA; (0.4079 - 0.1402) / (293.9 - 84.9 mA) at 20 mA
SPEC = a.Spec(points=TABLE + HFE, vaf=math.inf, rb=0.0, x0=X0, hi=dict(bf=3.5, br=3.0), fixed={"rc": RC, "re": 0.0})

COB = [(v, 20e-12 * n) for v, n in D["cob_norm"][::6]]  # the 20 pF maximum at 5 V, the family's shape

NOTE = ("Our own fit by pixel from TI's sheet: the 2N1308's table column (its design centres at 10 mA) with the "
        "family's normalised N-P-N gain curve (22-300 mA) and saturation lines. Nothing on the sheet goes below 10 mA, so "
        "at a pedal's 0.3-2 mA, and on the tester, the gain is the card's extrapolation. Cob is the sheet's 20 pF maximum "
        "(no typical given). Germanium units vary widely (hFE 80 min at 10 mA, no max): give a measured hFE and leakage (D-130).")

if __name__ == "__main__":
    f, ks = a.fit(SPEC)
    cjc, vjc, mjc = a.fm.fit_junction_cap(COB)
    cje, vje, mje = a.fm.fit_junction_cap([(5.0, 10e-12)])  # page 2: Cib 10 pF at VEB 5 V (the centre column)
    f = dataclasses.replace(f, cjc=cjc, vjc=vjc, mjc=mjc, cje=cje, vje=vje, mje=mje)
    f = dataclasses.replace(f, tf=a.fm.bjt_tf(f, 20e6, 1e-3, 5.0))  # page 2: fαb 20 MHz centre (VCB 5 V, IE 1 mA), as fT
    card = a.fm.bjt_card("2N1308", f, "NPN", eg=0.67)
    print(f)
    print(card.strip())
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in ks.items()})
    print("\n".join(a.report(f, SPEC, ks)))
    print("hFE at VCE 4.5 V:", {ma: round(f.forward(ma * 1e-3, 4.5)[1], 1) for ma in (0.1, 0.3, 1, 3, 10, 30, 100, 200)})
    print("hFE at 200 mA, 0.35 V (table min 20):", round(f.forward(0.2, 0.35)[1], 1))
    print("VBE(on) at VCE 4.5 V (mV):", {ma: round(f.forward(ma * 1e-3, 4.5)[0] * 1e3, 1) for ma in (0.1, 0.3, 1, 3, 10)})
    w = {k: a.worst(f, SPEC, ks, k, "*" if k == "hfe" else None) for k in ("hfe", "vce_sat", "vbe_sat")}
    write_record("2N1308", f, card, {
        "sheet": SHEET,
        "basis": "its table's design centres and the family's design curves",
        "note": NOTE,
        "description": "2N1308 germanium NPN (TI alloy junction, high-frequency computer switching; the 2N1309 is its PNP twin), our fit to TI's sheet",
        "manufacturer": "Texas Instruments",
        "url": "https://bitsavers.mirrorservice.org/components/ti/discrete/transistors/2N1302_2N1304_2N1306_2N1308_2N1303_2N1305_2N1307_2N1309.pdf "
               "(kept as data/spec-sheets/2N1302-2N1309_TI.pdf)",
        "ratings": {"vceo": 15.0, "ic": 0.3},
        "rating_sources": {
            "vceo": P(1, "maximum ratings at 25 °C case: collector-emitter voltage 15 V (2N1308, 9)"),
            "ic": P(1, "maximum ratings: collector current 300 mA"),
        },
        "package": {"name": "TO-5 (EBC; base on the case)", "pins": {"E": 1, "B": 2, "C": 3},
                    "source": P(1, "mechanical data: outline, emitter, base, collector around the tab; the base is connected internally to the case")},
        "figure": ("page 2 table, 2N1308 column (hFE, VBE, VCE(sat), ICBO, IEBO, Cib, fαb; Cob's 20 pF maximum); page 5 design curves: "
                   "normalised N-P-N hFE against IC (its shape), VCE against IC at IB 20 and 50 mA (their slope, RC), normalised Cob against VCB (its shape)"),
        "points": [[p.a, p.value] for p in TABLE if p.kind == "hfe"] + [[p.a, ks["hfe"] * p.value] for p in HFE],
        "curves": {"cobo": [[v, c] for v, c in COB], "cibo": [[5.0, 10e-12]],
                   "vce_sat": [[p.a, p.value] for p in TABLE if p.kind == "vce_sat"], "vbe_sat": [[p.a, p.value] for p in TABLE if p.kind == "vbe_sat"]},
        "method": (".claude/skills/fit-model/worked/germanium/alloy.py: the 2N1308's table column (x3 weight) with the family's normalised N-P-N "
                   f"gain curve at VCE 1 V (its shape, a free level: {ks['hfe']:.3g} x 150 at unity), leakage included; IS, NF, BF, ISE, "
                   "NE, IKF, NKF, BR, ISC, NC free, NR = NF; RC 1.28 Ω from the slope of the family's VCE lines at IB 20 and 50 mA, "
                   "RE 0. No rbb' on the sheet, so "
                   "RB 0; no output curves, so no VAF. CJC from Cob: the 20 pF maximum at 5 V with the family's normalised curve "
                   "(no typical given); CJE from Cib 10 pF at 5 V (one point); TF from fαb 20 MHz taken as fT"),
        "fitted": (f"Fitted points within {abs(w['hfe']) * 100:.1f} % (hFE, the curve; the table's 150 within 0.1 %), {abs(w['vce_sat']) * 1e3:.1f} mV (VCE(sat)) and "
                   f"{abs(w['vbe_sat']) * 1e3:.1f} mV (VBE); ICBO {f.icbo(25.0) * 1e6:.2f} µA, IEBO {f.iebo(25.0) * 1e6:.2f} µA"),
        "worst": {},
    })
