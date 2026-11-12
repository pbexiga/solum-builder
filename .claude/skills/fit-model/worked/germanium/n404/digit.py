"""2N404 curves read by pixel off RCA's sheet (data/spec-sheets/2N404_RCA.pdf, SPD-100 1969, File
No. 15), pages rendered by `pdftoppm -r 300 -gray` into /scr/2n404/p-N.pgm (pdf page N; the pdf's
order is printed pages 1, 2, 5, 4, 3, 6). Writes n404/data.json.

Fig. 2 (pdf p1): minimum hFE against IC at VCE 0.15, 0.2, 0.3, 0.5 V. x IC 0 at px 1554.5,
  2 mA per 11.55 px minor line; y hFE 0 at px 2450.5, 1 per 11.59 px minor line (60 at 1755).
Figs. 3, 4 (pdf p5, drawn rotated: x is IC, y is VCE): minimum and maximum collector
  characteristics, IB 0.5, 1, 2, 3, 4 mA. Fig. 3 IC 0 at px 1177, -80 mA at 443 (9.175 px/mA);
  Fig. 4 IC 0 at 2283, -200 mA at 1548 (3.675 px/mA); VCE 0 at y 2057 (Fig. 4 2058.5), 1846 px/V.
Figs. 7, 8 (pdf p4): maximum and minimum VBE against IC at IB 0.5, 1, 2, 3, 4 mA (the base
  input characteristic, collector loaded: the transistor saturated, VBE(sat)). x VBE 0 at px 279
  (Fig. 8 1376.5), 0.02 V per 18.77 px (Fig. 8 18.8); y IC 0 at px 1857, 5 mA per 18.93 px.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import load, runs, trace  # noqa: E402

HERE = Path(".claude/skills/fit-model/worked/germanium/n404")
out: dict = {}

# ---- Fig. 2: minimum hFE, four VCE lines ----
im = load("/scr/2n404/p-1.pgm")
X0, PXMA, Y0, PXH = 1554.5, 11.55 / 2, 2450.5, (2450.5 - 1755) / 60
px = lambda ic, h: [X0 + ic * PXMA, Y0 - h * PXH]  # noqa: E731
GUESS = {  # (IC mA, hFE) by eye off the plot, for the tracer to follow
    "0.5": [(1, 22), (8, 32), (20, 40), (32, 41.8), (50, 36.5), (75, 30.5), (100, 26.5)],
    "0.3": [(1, 19.5), (8, 30), (20, 38.5), (32, 40.4), (50, 35), (75, 29.5), (100, 25)],
    "0.2": [(1, 18), (8, 28), (20, 35.5), (30, 37.8), (50, 31), (75, 22.5), (100, 13.5)],
    "0.15": [(1, 16.5), (8, 26), (24, 32.5), (40, 28.5), (60, 20), (80, 12), (100, 7)],
}
fig2 = {}
for vce, g in GUESS.items():
    guess = [px(i, h) for i, h in g]
    pts = trace(im, "col", int(X0 + 2), int(X0 + 99 * PXMA), 12, guess, 3, 120, 7)
    fig2[vce] = [[round((x - X0) / PXMA, 2), round((Y0 - y) / PXH, 2)] for x, y in pts]
out["fig2_min_hfe"] = fig2

# ---- Figs. 3, 4: IC on the flat part of each IB line (VCE 0.3 to 0.68 V) ----
im = load("/scr/2n404/p-5.pgm")


def flat(x0, x1, zero, ic0, pxma, guesses):
    """IC (mA) of each IB line at VCE 0.3 ... 0.68: the thick run nearest the guess, rows +-6."""
    res = {}
    for ib, gx in guesses.items():
        row = []
        for v in (0.3, 0.4, 0.5, 0.6, 0.68):
            y0 = int(zero - v * 1846)
            xs = [r + x0 for y in range(y0 - 6, y0 + 7) for r in runs(im[y, x0:x1] < 120, 4)]
            near = [x for x in xs if abs(x - gx(v)) < 9]
            if near:
                row.append([v, round((ic0 - float(np.median(near))) / pxma, 2)])
        res[ib] = row
    return res


# guesses: px of each line (from the probe, n404/probe.py), linear in VCE between 0.3 and 0.68
lin = lambda a, b: (lambda v: a + (b - a) * (v - 0.3) / 0.38)  # noqa: E731
out["fig3_min_ic"] = flat(360, 1170, 2057, 1177, 9.175, {
    "4": lin(514, 448.5), "3": lin(655.5, 609), "2": lin(804, 754.5), "1": lin(925, 903), "0.5": lin(1045, 1039.5)})
out["fig4_max_ic"] = flat(1465, 2275, 2058.5, 2283, 3.675, {
    "4": lin(1689.5, 1658), "3": lin(1849.5, 1817.5), "2": lin(1939, 1911.5), "1": lin(2012, 1998.5), "0.5": lin(2102.5, 2093)})

# ---- Figs. 7, 8: VBE of each IB line at IC 2.5 ... 37.5 mA (rows between the grid lines) ----
im = load("/scr/2n404/p-4.pgm")
for key, x0, x1, vx0, pitch in (("fig7_max_vbe", 285, 1100, 279, 18.77), ("fig8_min_vbe", 1382, 2200, 1376.5, 18.8)):
    res: dict = {ib: [] for ib in ("0.5", "1", "2", "3", "4")}
    for ic in (2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5):
        y0 = int(round(1857 - ic * 18.93 / 5))
        found = [sorted(r + x0 for r in runs(im[y, x0:x1] < 120, 4)) for y in range(y0 - 3, y0 + 4)]
        found = [f for f in found if len(f) == 5]  # all five lines, none merged
        if found:
            xs = np.median(np.array(found), axis=0)
            for ib, x in zip(res, xs):
                res[ib].append([ic, round((x - vx0) * 0.02 / pitch, 4)])
    out[key] = res

(HERE / "data.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    for kk, vv in v.items():
        print(k, kk, len(vv), vv)
