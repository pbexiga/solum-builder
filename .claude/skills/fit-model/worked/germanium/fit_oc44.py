"""OC44 fitted to Mullard's sheet (Vol. 4 Part III: OC44 of Dec 1960, small-signal page Oct
1964), its typical curves read by pixel (digit_oc44.py -> data/OC44.json). Writes
.claude/skills/fit-model/worked/germanium/OC44.{lib,json} (never library/). Run: run.sh fit_oc44.py"""
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g  # noqa: E402
from fit_oc71 import thin  # noqa: E402
from record import write_record  # noqa: E402

D = json.loads(Path(".claude/skills/fit-model/worked/germanium/data/OC44.json").read_text())
SHEET = "Mullard OC44 data sheet (Mullard Technical Handbook Vol. 4 Part III, Nov 1968: OC44 of Dec 1960, pages D1-D5 and C1-C6)"
P = lambda page, what: f"{SHEET}, page {page}: {what}"  # noqa: E731

VCE = 2.0  # both curves used are at Vc = -2 V
RB = 110.0  # page D3: rbb' 110 Ω typ. (40-250) at Vce = -6 V, Ie = 1 mA
VAF = 1e-3 / 40e-6 - 6.0  # page D3: gce 40 µmho typ. at Vce = -6 V, Ie = 1 mA -> 19 V
ICBO = (0.5e-6, 2.0)  # page D2: Ico 0.5 µA typ. (2.0 max) at Vcb = -2 V

# transfer: page C2 lower from IB = 8.8 µA (below it the line runs into the corner: 0.27 mA
# at 1.9 µA against the table's I'co of 25 µA)
tr = [p for p in D["c2_transfer"] if p[0] >= 8.0]
TRANSFER = [(ib * 1e-6, ic * 1e-3) for ib, ic in thin(tr, 8)]
ICO_E = (0.0, 25e-6)  # page D2: I'co 25 µA typ. (75 max) at Vce = -2 V, Ib = 0: the transfer line's foot
TRANSFER_FIT = TRANSFER + [ICO_E]
HELD_T = [(ib * 1e-6, ic * 1e-3) for ib, ic in tr if (ib * 1e-6, ic * 1e-3) not in TRANSFER]
# VBE against IC: page C1 from 0.11 mA (below it the line lies on the axis)
VBE = [(i * 1e-3, v * 1e-3) for i, v in thin(D["c1_ic_vbe"], 12)]
HELD_V = [(i * 1e-3, v * 1e-3) for i, v in D["c1_ic_vbe"] if (i * 1e-3, v * 1e-3) not in VBE]

data = g.Data(vce=VCE, transfer=TRANSFER_FIT, vbe=VBE, vbe_of=0, icbo=ICBO, vaf=VAF, rb=RB)

if __name__ == "__main__":
    f = g.fit(data)
    cjc, vjc, mjc = g.fm.fit_junction_cap([(6.0, 10.5e-12)])  # page D3: Cb'c 10.5 pF typ. at Vce = -6 V
    f = dataclasses.replace(f, cjc=cjc, vjc=vjc, mjc=mjc)
    f = dataclasses.replace(f, tf=g.fm.bjt_tf(f, 15e6, 1e-3, 6.0))  # page D3: fα 15 Mc/s typ., taken as fT
    card = g.card("OC44", f)
    rep = g.report(f, data)
    print(f)
    print(card.strip())
    print({k: float(f"{float(v):.4g}") for k, v in rep.items()})
    for ib, ic in TRANSFER:
        print(f"  IB {ib*1e6:7.2f} µA  IC sheet {ic*1e3:7.4f} fit {g.ic_at_ib(f, ib, VCE)*1e3:7.4f} mA  hFE {ic/ib:6.1f}")
    print(f"  I'co sheet 25 µA fit {g.ic_at_ib(f, 0.0, VCE)*1e6:.1f} µA")
    for i, v in VBE:
        print(f"  IC {i*1e3:8.4f} mA  VBE sheet {v*1e3:6.1f} fit {g.vbe_at(f, 0, i, VCE)*1e3:6.1f} mV")
    write_record("OC44", f, card, {
        "sheet": SHEET,
        "description": "OC44 germanium PNP (Mullard, r.f.), our fit to Mullard's sheet",
        "manufacturer": "Mullard",
        "url": "https://frank.pocnet.net/other/Mullard/Mullard_Volume4PartIII_transistors_1968-11.pdf "
               "(Mullard Vol. 4 Part III, Nov 1968; pages 115-126 extracted, kept as data/spec-sheets/OC44_Mullard.pdf)",
        "ratings": {"vceo": 10.0, "ic": 0.005},
        "rating_sources": {
            "vceo": P("D1", "absolute maximum ratings, grounded emitter: Vce(d.c.) max. -10 V (base-ground impedance < 1 kΩ or Vbe > 300 mV reverse)"),
            "ic": P("D1", "absolute maximum ratings: Ic max. 5.0 mA (averaged over 20 ms; 10 mA peak)"),
        },
        "package": {"name": "SO-2 glass (EBC)", "pins": {"E": 1, "B": 2, "C": 3},
                    "source": P("D5", "outline and dimensions (V.A.S.C.A. SO-2/SB3-2): e, b, c in a line, the dot on the collector side")},
        "figure": ("page C2 transfer characteristic at Vc = -2 V (IB 8.8 to 98 µA); page C1 IC against VBE at Vc = -2 V "
                   "(0.11 to 10 mA); page D2 table (Ico); page D3 (rbb', Cb'c, fα, gce)"),
        "points": [[ib, ic] for ib, ic in TRANSFER],
        "curves": {"vbe_on": [list(p) for p in VBE], "cobo": [[6.0, 10.5e-12]]},
        "method": "see NOTES.md (germanium study): transfer, VBE-IC and Ico fitted together at Vc = -2 V, leakage included",
        "worst": rep,
    })
