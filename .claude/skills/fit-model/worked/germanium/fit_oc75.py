"""OC75 fitted to Mullard's sheet (Vol. 4 Part III: OC75 of March 1959, small-signal page Oct
1964), its typical curves read by pixel (digit_oc75.py -> data/OC75.json); Philips' table (OC75
of 1958-60) gives checks. Writes .claude/skills/fit-model/worked/germanium/OC75.{lib,json} (never library/).
Run: run.sh fit_oc75.py"""
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g  # noqa: E402
from fit_oc71 import thin  # noqa: E402
from record import write_record  # noqa: E402

D = json.loads(Path(".claude/skills/fit-model/worked/germanium/data/OC75.json").read_text())
SHEET = "Mullard OC75 data sheet (Mullard Technical Handbook Vol. 4 Part III, Nov 1968: OC75 of March 1959, pages D1-D4 and C1-C11)"
PHILIPS = "Philips OC75 data sheet (1958-60, pages 1-3 and A-N; kept as data/spec-sheets/OC75_Philips.pdf)"
XREF = "transistor cross-reference book, page 242 (data/spec-sheets/Germanium_OC_crossref.pdf)"
P = lambda page, what: f"{SHEET}, page {page}: {what}"  # noqa: E731
PH = lambda page, what: f"{PHILIPS}, page {page}: {what}"  # noqa: E731

VCE = 4.5  # every curve used is at Vc = -4.5 V
RB = 0.0  # no rbb' on either sheet (Mullard's T-network rb 720 Ω is not rbb'): ngspice's default (D-163)
VAF = 3e-3 / 125e-6 - 2.0  # page D3: h'22 = 125 µmho at Vc = -2 V, Ie = 3 mA -> 22 V
ICBO = (4.5e-6, 4.5)  # page D2: Ico 4.5 µA av. (14 max) at Vc = -4.5 V (Philips: 4.5, < 12)

# transfer: page C6 lower from IB = 0 (I'co 0.31 mA), upper Average line (2.6 to 22 mA); the
# two meet (103 at 1.3 mA and 2.6 mA)
lo_t = [p for p in D["c6_transfer"] if p[0] >= -0.5]
up_t = D["c6_transfer_avg"]
TRANSFER = [(ib * 1e-6, ic * 1e-3) for ib, ic in thin(lo_t, 6) + thin(up_t, 7)]
HELD_T = [(ib * 1e-6, ic * 1e-3) for ib, ic in lo_t + up_t if (ib * 1e-6, ic * 1e-3) not in TRANSFER]
# VBE against IE: page C1 lower (IE >= 20 µA) and upper (from 0.6 mA)
lo_v = [p for p in D["c1_vbe_ie_uA"] if p[0] >= 20]
up_v = D["c1_vbe_ie_mA"]
VBE = [(i * 1e-6, v * 1e-3) for i, v in thin(lo_v, 5)] + [(i * 1e-3, v * 1e-3) for i, v in thin(up_v, 9)]
HELD_V = [(i * 1e-6, v * 1e-3) for i, v in lo_v] + [(i * 1e-3, v * 1e-3) for i, v in up_v]
HELD_V = [p for p in HELD_V if p not in VBE]

data = g.Data(vce=VCE, transfer=TRANSFER, vbe=VBE, vbe_of=2, icbo=ICBO, vaf=VAF, rb=RB)

if __name__ == "__main__":
    f = g.fit(data)
    # no capacitance on Mullard's or Philips' OC75 sheet: the cross-reference book's Cob <= 50 pF
    # (a maximum; the book gives no voltage, 6 V taken as Mullard's fα condition; see NOTES)
    cjc, vjc, mjc = g.fm.fit_junction_cap([(6.0, 50e-12)])
    f = dataclasses.replace(f, cjc=cjc, vjc=vjc, mjc=mjc)
    f = dataclasses.replace(f, tf=g.fm.bjt_tf(f, 900e3, 1e-3, 6.0))  # page D2: fα 900 kc/s (Vc = -6 V, Ie = 1 mA), as fT
    card = g.card("OC75", f)
    rep = g.report(f, data)
    print(f)
    print(card.strip())
    print({k: float(f"{float(v):.4g}") for k, v in rep.items()})
    for ib, ic in TRANSFER:
        print(f"  IB {ib*1e6:7.2f} µA  IC sheet {ic*1e3:7.4f} fit {g.ic_at_ib(f, ib, VCE)*1e3:7.4f} mA")
    for i, v in VBE:
        print(f"  IE {i*1e3:8.4f} mA  VBE sheet {v*1e3:6.1f} fit {g.vbe_at(f, 2, i, VCE)*1e3:6.1f} mV")
    write_record("OC75", f, card, {
        "sheet": SHEET,
        "description": "OC75 germanium PNP (Mullard, high-gain audio), our fit to Mullard's sheet",
        "manufacturer": "Mullard",
        "url": "https://frank.pocnet.net/other/Mullard/Mullard_Volume4PartIII_transistors_1968-11.pdf "
               "(Mullard Vol. 4 Part III, Nov 1968; pages 197-211 extracted, kept as data/spec-sheets/OC75_Mullard.pdf)",
        "ratings": {"vceo": 20.0, "ic": 0.01},
        "rating_sources": {
            "vceo": P("D1", "limiting values, grounded emitter: Vc max. (d.c.) -20 V (base-ground impedance < 500 Ω or Vbe > 500 mV reverse)"),
            "ic": P("D1", "limiting values: Ic max. 10 mA (averaged over 20 ms; 50 mA peak)"),
        },
        "package": {"name": "SO-2 glass (EBC)", "pins": {"E": 1, "B": 2, "C": 3},
                    "source": P("D4", "outline and dimensions (V.A.S.C.A. SO-2/SB3-2): e, b, c in a line, the dot on the collector side")},
        "figure": ("page C6 transfer characteristic at Vc = -4.5 V (IB 0 to 13 µA) and its Average spread line (2.6 to 22 mA); "
                   "page C1 IE against VBE at Vc = -4.5 V (both ranges); page D2 table (Ico, fα); page D3 h'22 (VAF); "
                   f"Cob from the {XREF} (a maximum: neither maker's sheet gives a capacitance)"),
        "points": [[ib, ic] for ib, ic in TRANSFER],
        "curves": {"vbe_ie": [list(p) for p in VBE], "cobo": [[6.0, 50e-12]]},
        "method": "see NOTES.md (germanium study): transfer, VBE-IE and Ico fitted together at Vc = -4.5 V, leakage included; RB 0 (no rbb' given)",
        "worst": rep,
    })
