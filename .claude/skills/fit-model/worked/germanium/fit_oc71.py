"""OC71 fitted to Mullard's sheet (Vol. 4 Part III, OC71 Issue 2, Oct 1963), its typical
curves read by pixel (digit_oc71.py -> data/OC71.json). Writes .claude/skills/fit-model/worked/germanium/OC71.{lib,json}
(never library/). Run: run.sh fit_oc71.py"""
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g  # noqa: E402
from record import write_record  # noqa: E402

D = json.loads(Path(".claude/skills/fit-model/worked/germanium/data/OC71.json").read_text())
SHEET = "Mullard OC71 data sheet (Mullard Technical Handbook Vol. 4 Part III, Nov 1968: OC71 Issue 2, pages 158-1 to 158-20)"
P = lambda page, what: f"{SHEET}, page 158-{page}: {what}"  # noqa: E731

VCE = 4.5  # every curve used is at Vc = -4.5 V
RB = 300.0  # page 158-2: rbb' 300 Ω (Vc = -6 V, Ie = 1 mA)
VAF = 1e-3 / 42e-6 - 2.0  # page 158-3: h'22 = 42 µmho at Vc = -2 V, Ie = 1 mA -> 21.8 V
ICBO = (4.5e-6, 4.5)  # page 158-2: Ico 4.5 µA av. (13 max) at Vc = -4.5 V
VBE_TOP = 6.1  # mA: above it the sheet's VBE bends below what rbb' = 300 Ω allows (as the AC128, D-170)


def thin(pts, n):
    k = max(1, round(len(pts) / n))
    return pts[::k] if pts[::k][-1] == pts[-1] else pts[::k] + [pts[-1]]


# transfer: page 12's typical line from IB = 0 (I'co) up (IB > 0 into the base); page 13's
# Average line from 5 mA (below that it is drawn straight into the origin, leaving out the
# leakage page 12 shows: 0.16 mA at IB = 0; see NOTES).
p12 = sorted([p for p in D["p12_transfer"] if p[0] >= -0.01])
p13 = sorted([p for p in D["p13_transfer_avg"] if p[1] >= 4.9])
TRANSFER = [(ib * 1e-6, ic * 1e-3) for ib, ic in thin(p12, 8) + thin(p13, 6)]
HELD_T = [(ib * 1e-6, ic * 1e-3) for ib, ic in sorted(p12 + p13) if (ib * 1e-6, ic * 1e-3) not in TRANSFER]
# VBE against IE: page 7 lower (IE >= 20 µA) and upper from 0.75 mA (below that the upper
# plot's line is near vertical, 1 px = 0.016 mA, and its foot sits 10 mV under the lower plot)
lo = [p for p in D["p7_vbe_ie_uA"] if p[0] >= 20]
up = [p for p in D["p7_vbe_ie_mA"] if 0.75 <= p[0] <= VBE_TOP]
VBE = [(i * 1e-6, v * 1e-3) for i, v in thin(lo, 6)] + [(i * 1e-3, v * 1e-3) for i, v in thin(up, 10)]
HELD_V = [(i * 1e-6, v * 1e-3) for i, v in lo] + [(i * 1e-3, v * 1e-3) for i, v in up]
HELD_V = [p for p in HELD_V if p not in VBE]

data = g.Data(vce=VCE, transfer=TRANSFER, vbe=VBE, vbe_of=2, icbo=ICBO, vaf=VAF, rb=RB)

if __name__ == "__main__":
    f = g.fit(data)
    cjc, vjc, mjc = g.fm.fit_junction_cap([(6.0, 40e-12)])  # page 158-2: Cc 40 pF at Vc = -6 V
    f = dataclasses.replace(f, cjc=cjc, vjc=vjc, mjc=mjc)
    # page 158-2: fα 600 kc/s (Vc = -6 V, Ie = 1 mA), taken as fT (fα' 11 kc/s × β ≈ 56 gives
    # 0.62 MHz, the same)
    f = dataclasses.replace(f, tf=g.fm.bjt_tf(f, 600e3, 1e-3, 6.0))
    card = g.card("OC71", f)
    rep = g.report(f, data)
    print(f)
    print(card.strip())
    print({k: round(v, 5) if abs(v) > 1e-3 else v for k, v in rep.items()})
    for ib, ic in TRANSFER:
        print(f"  IB {ib*1e6:7.2f} µA  IC sheet {ic*1e3:7.4f} fit {g.ic_at_ib(f, ib, VCE)*1e3:7.4f} mA  hFE {ic/ib if ib else 0:6.1f}")
    for i, v in VBE:
        print(f"  IE {i*1e3:8.4f} mA  VBE sheet {v*1e3:6.1f} fit {g.vbe_at(f, 2, i, VCE)*1e3:6.1f} mV")
    write_record("OC71", f, card, {
        "sheet": SHEET,
        "description": "OC71 germanium PNP (Mullard, small-signal audio), our fit to Mullard's sheet",
        "manufacturer": "Mullard",
        "url": "https://frank.pocnet.net/other/Mullard/Mullard_Volume4PartIII_transistors_1968-11.pdf "
               "(Mullard Vol. 4 Part III, Nov 1968; pages 159-178 extracted, kept as data/spec-sheets/OC71_Mullard.pdf)",
        "ratings": {"vceo": 20.0, "ic": 0.01},
        "rating_sources": {
            "vceo": P(1, "limiting values, grounded emitter: Vc max. (d.c.) -20 V (base-ground impedance < 500 Ω or Vbe > 500 mV reverse)"),
            "ic": P(1, "limiting values: Ic max. 10 mA (averaged over 20 ms; 50 mA peak)"),
        },
        "package": {"name": "SO-2 glass (EBC)", "pins": {"E": 1, "B": 2, "C": 3},
                    "source": P(6, "outline and dimensions (V.A.S.C.A. SO-2/SB3-2): e, b, c in a line, the dot on the collector side")},
        "figure": ("page 158-12 transfer characteristic at Vc = -4.5 V (IB 0 to 16 µA); page 158-13 Average transfer line "
                   "(5 to 14 mA); page 158-7 IE against VBE at Vc = -4.5 V (both ranges); page 158-2 table (Ico, rbb', Cc, fα); "
                   "page 158-3 h'22 (VAF)"),
        "points": [[ib, ic] for ib, ic in TRANSFER],
        "curves": {"vbe_ie": [list(p) for p in VBE], "cobo": [[6.0, 40e-12]]},
        "method": "see NOTES.md (germanium study): transfer, VBE-IE and Ico fitted together at Vc = -4.5 V, leakage included",
        "worst": rep,
    })
