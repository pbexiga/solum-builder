"""2N404 fitted to RCA's sheet (SPD-100 1969, File No. 15, 9-66; data/spec-sheets/2N404_RCA.pdf).
Curves read by n404/digit.py -> n404/data.json. Writes .claude/skills/fit-model/worked/germanium/2N404.{lib,json}.
Run: run.sh n404/fit.py

The sheet has no typical curves: its table gives typicals (hFE, VCE(sat), VBE(sat), ICBO,
IEBO, fhfb, Cob) and its figures a minimum and a maximum. So:
- the level comes from the table's typicals (weighted x3: few points, and the table wins, D-163);
- nothing below the table's 12 mA: Fig. 2 (minimum hFE, VCE 0.15-0.5 V, from about 1 mA) is the
  only figure that goes lower, and it disagrees with the rest of the sheet: it reads 1.2-1.75x the
  table's minimums and Fig. 3's, and its gain rises from 12 to 32 mA where the table's typicals
  and minimums and Fig. 3 all fall (50 -> 40, 30 -> 24). Fitting its rise below 12 mA against the
  table's fall above it misses the table by 9-10 % and Fig. 2 by up to 30 %, from three starts,
  and lands on a gain about flat from 0.3 to 12 mA (n404/try_droop.py, out_fit_with_fig2.txt).
  Left free below 12 mA, the card's gain rises instead (79 at 1 mA against 50 at 12: the knee
  the high-current fall needs, with nothing to hold it), against Fig. 2 and every germanium sheet
  fitted so far. So the leakage-free gain (VCB = 0) at 0.5, 1, 2, 5 and 12 mA is held equal, its
  level free: the card's gain is flat below the sheet, and the tester figure is that extrapolation;
- the gain's fall at high current from the geometric middle of Figs. 3 (minimum) and 4
  (maximum) collector characteristics, IB 0.5-4 mA at VCE 0.3 and 0.68 V, also up to a factor.
Figs. 3/4 (each line between them), 7/8 (VBE(sat) between them) and Fig. 2 (info) are then checks.
"""
import dataclasses
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import alloy as a  # noqa: E402
from record import write_record  # noqa: E402

D = json.loads(Path(".claude/skills/fit-model/worked/germanium/n404/data.json").read_text())
SHEET = "RCA 2N404, 2N404A, 2N581, 2N582 data sheet (File No. 15, 9-66; RCA SPD-100 Semiconductor Products Databook, 1969)"
P = lambda page, what: f"{SHEET}, page {page}: {what}"  # noqa: E731
T = lambda what: P(2, f"electrical characteristics at 25 °C, {what}")  # noqa: E731
W = 3.0  # the table's weight

TABLE = [
    a.Point("hfe", 12e-3, 0.15, 50.0, weight=W, src=T("hFE at VCE -0.15 V, IC -12 mA: 30 min, 50 typ")),
    a.Point("hfe", 24e-3, 0.20, 40.0, weight=W, src=T("hFE at VCE -0.2 V, IC -24 mA: 24 min, 40 typ")),
    a.Point("vce_sat", 12e-3, 0.4e-3, 0.10, weight=W, src=T("VCE(sat) at IC -12 mA, IB -0.4 mA: 0.1 typ, 0.15 max")),
    a.Point("vce_sat", 24e-3, 1e-3, 0.12, weight=W, src=T("VCE(sat) at IC -24 mA, IB -1 mA: 0.12 typ, 0.2 max")),
    a.Point("vbe_sat", 12e-3, 0.4e-3, 0.25, weight=W, src=T("VBE(sat) at IC -12 mA, IB -0.4 mA: 0.25 typ, 0.35 max")),
    a.Point("vbe_sat", 24e-3, 1e-3, 0.32, weight=W, src=T("VBE(sat) at IC -24 mA, IB -1 mA: 0.32 typ, 0.4 max")),
    a.Point("icbo", 12.0, 0.0, 2e-6, weight=W, src=T("ICBO at VCB -12 V: 2 typ, 5 max µA")),
    a.Point("iebo", 2.5, 0.0, 1e-6, weight=W, src=T("IEBO at VEB -2.5 V: 1 typ µA")),
]



def middle(ib: str, v: float) -> float | None:
    lo = dict(map(tuple, D["fig3_min_ic"][ib])).get(v)
    hi = dict(map(tuple, D["fig4_max_ic"][ib])).get(v)
    return None if lo is None or hi is None else math.sqrt(lo * hi)


F34 = [a.Point("ic_at_ib", float(ib) * 1e-3, v, m * 1e-3, group="fig34",
               src=P(3, f"Figs. 3 and 4, geometric middle of the minimum and maximum lines, IB -{ib} mA, VCE -{v} V (by pixel)"))
       for ib in ("0.5", "1", "2", "3", "4") for v in (0.3, 0.68) if (m := middle(ib, v))]

NOTE = ("Our own fit by pixel from RCA's sheet. The sheet has no typical curves: the card is its table's typicals "
        "(12 and 24 mA, near saturation) with the shape of the middle of its minimum and maximum curves to 110 mA. Nothing "
        "on the sheet goes below 12 mA that agrees with the table (Fig. 2 contradicts it), so the gain is held flat below "
        "12 mA: at a pedal's 0.3-2 mA, and on the tester, the figure is the card's extrapolation. Germanium units vary "
        "widely (hFE 30 min at 12 mA, no max): give a measured hFE and leakage (D-130).")
FLAT = [a.Point("hfe", ma * 1e-3, None, 50.0, group="flat", src="held flat below the sheet's 12 mA (see the docstring)")
        for ma in (0.5, 1.0, 2.0, 5.0, 12.0)]

X0 = dict(is_=-6.0, nf=1.05, bf=2.0, ise=-7.0, ne=1.6, ikf=-1.0, re=0.5, nkf=0.5, br=0.7, isc=-7.0, nc=1.5, rc=0.5)
SPEC = a.Spec(points=TABLE + F34 + FLAT, vaf=math.inf, rb=0.0, x0=X0, hi=dict(bf=3.0, br=2.5))

if __name__ == "__main__":
    f, ks = a.fit(SPEC)
    cjc, vjc, mjc = a.fm.fit_junction_cap([(6.0, 12e-12)])  # page 2: Cob 12 typ, 20 max pF at VCB -6 V
    f = dataclasses.replace(f, cjc=cjc, vjc=vjc, mjc=mjc)
    f = dataclasses.replace(f, tf=a.fm.bjt_tf(f, 13e6, 1e-3, 6.0))  # page 2: fhfb 13 MHz typ (VCB -6 V, IE 1 mA), as fT
    card = a.fm.bjt_card("2N404", f, "PNP", eg=0.67)
    print(f)
    print(card.strip())
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in ks.items()})
    print("\n".join(a.report(f, SPEC, ks)))
    print("tester-range hFE at VCE 4.5 V:", {ma: round(f.forward(ma * 1e-3, 4.5)[1], 1) for ma in (0.1, 0.3, 1, 3, 10, 30)})
    print("VBE(on) at VCE 4.5 V (mV):", {ma: round(f.forward(ma * 1e-3, 4.5)[0] * 1e3, 1) for ma in (0.1, 0.3, 1, 3, 10)})
    w = {k: a.worst(f, SPEC, ks, k, None) for k in ("hfe", "vce_sat", "vbe_sat")}
    write_record("2N404", f, card, {
        "sheet": SHEET,
        "basis": "its table's typicals and the middle of its minimum and maximum curves",
        "note": NOTE,
        "description": "2N404 germanium PNP (RCA alloy junction, medium-speed computer switching), our fit to RCA's sheet",
        "manufacturer": "RCA",
        "url": "https://bitsavers.mirrorservice.org/components/rca/SPD-100_RCA_Semiconductor_Products_Databook_1969/2N.pdf "
               "(RCA SPD-100, 1969; File No. 15, pages 39-44 extracted, kept as data/spec-sheets/2N404_RCA.pdf)",
        "ratings": {"vceo": 24.0, "ic": 0.1},
        "rating_sources": {
            "vceo": P(1, "maximum ratings: VCEV (VEB = 1 V) -24 V (no VCEO given; VCBO -25 V)"),
            "ic": P(1, "maximum ratings: collector current -100 mA"),
        },
        "package": {"name": "TO-5 (EBC)", "pins": {"E": 1, "B": 2, "C": 3},
                    "source": P(6, "terminal diagram (bottom view): lead 1 emitter, 2 base, 3 collector")},
        "figure": ("page 2 table (typical hFE, VCE(sat), VBE(sat), ICBO, IEBO, fhfb, Cob); Fig. 2 minimum hFE, its shape to 30 mA; "
                   "Figs. 3 and 4 minimum and maximum collector characteristics, their geometric middle's shape"),
        "points": [[p.a, p.value] for p in TABLE if p.kind == "hfe"]
                  + [[ks["fig34"] * p.value, ks["fig34"] * p.value / p.a] for p in F34 if p.b == 0.68],
        "curves": {"cobo": [[6.0, 12e-12]], "vce_sat": [[p.a, p.value] for p in TABLE if p.kind == "vce_sat"],
                   "vbe_sat": [[p.a, p.value] for p in TABLE if p.kind == "vbe_sat"]},
        "method": (".claude/skills/fit-model/worked/germanium/alloy.py: the table's typicals (x3 weight) with the shape of "
                   f"the middle of Figs. 3/4 (up to a free factor, {ks['fig34']:.3g}), at the sheet's own VCE (0.15-0.68 V), "
                   "leakage included; IS, NF, BF, ISE, NE, IKF, NKF, RE, BR, ISC, NC, RC free, NR = NF. Below the table's 12 mA the "
                   "leakage-free gain is held flat (0.5 to 12 mA, its level free): the sheet's one lower figure, Fig. 2, contradicts "
                   "the table (see the note). "
                   "No rbb' on the sheet, so RB 0; no output curves above 0.7 V, so no VAF. CJC from Cob 12 pF at 6 V (one point), "
                   "TF from fhfb 13 MHz taken as fT"),
        "fitted": (f"Fitted points within {abs(w['hfe']) * 100:.1f} % (hFE), {abs(w['vce_sat']) * 1e3:.1f} mV (VCE(sat)) and "
                   f"{abs(w['vbe_sat']) * 1e3:.1f} mV (VBE(sat)) of the table; ICBO {f.icbo(12.0) * 1e6:.2f} µA, IEBO {f.iebo(2.5) * 1e6:.2f} µA"),
        "worst": {},
    })
