"""2SC1815 curves read by pixel off Toshiba's sheet (scratch/datasheets/2SC1815.pdf, 1997-04-10,
page 2; `pdftoppm -f 2 -l 2 -r 300 -gray` to /scr/t1815/hi-2.pgm). The 25 °C lines only.
Log axes: pixel -> log10(value), linear between the decade lines found by frames.py.
Writes data.json: hfe [mA, hFE] at VCE 6 V; ib_vbe [µA, V] at VCE 6 V; vcs [mA, V] at IC/IB 10;
ft [mA, MHz] at VCE 10 V; ic_vce_02 [V, mA] at IB 0.2 mA.
run.sh digit.py"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import load, runs, trace  # noqa: E402

im = load("/scr/t1815/hi-2.pgm")


def lin(p0, v0, p1, v1):
    return lambda p: v0 + (p - p0) * (v1 - v0) / (p1 - p0)


def logax(p0, v0, p1, v1):
    f = lin(p0, math.log10(v0), p1, math.log10(v1))
    return lambda p: 10 ** f(p)


# right column x (IC mA): 0.1 at 1389, 100 at 1999.5 (decades 203.5 px)
x_r = logax(1389, 0.1, 1999.5, 100.0)
# left column, middle plot x (IC mA): 0.1 at 354, 100 at 963.5
x_l = logax(354, 0.1, 963.5, 100.0)
out = {}

# hFE - IC (top right): y 3000 at 583, 10 at 1170. Solid 25 °C line, VCE = 6 V.
y = logax(583, 3000.0, 1170, 10.0)
g = [[1380, 900], [1895, 900], [1980, 908], [2063, 943]]
pts = trace(im, "col", 1392, 2060, 6, g, 4, 110, 8)
out["hfe"] = [[round(x_r(a), 4), round(y(c), 2)] for a, c in pts]

# IB - VBE (bottom left): x VBE 0 at 352, 2.0 at 1059 (linear); y IB 1000 µA at 2208.5,
# 1 µA at 2668. The middle (25 °C) line, VCE = 6 V; traced by row.
xv = lin(352, 0.0, 1059, 2.0)
yi = logax(2208.5, 1000.0, 2668, 1.0)
g = [[2195, 630], [2290, 607], [2450, 583], [2590, 567], [2670, 557], [2748, 545]]
pts = trace(im, "row", 2196, 2745, 6, g, 3, 110, 10)
out["ib_vbe"] = sorted([[round(yi(r), 4), round(xv(c), 4)] for r, c in pts])

# VCE(sat) - IC (middle left): y 3 V at 1376, 0.01 V at 1963. The middle line at low IC (the
# arrow "25"); its runs across each column are listed so the three lines can be told apart.
yv = logax(1376, 3.0, 1963, 0.01)
cols = list(range(360, 1056, 12))
out["vcs_runs"] = {round(x_l(c), 4): [round(yv(r), 5) for r in runs(im.T[c][1380:1955] < 110, 3) for r in [r + 1380]]
                   for c in cols}

# fT - IE (bottom right): x 0.1 at 1387, 100 at 1997; y 3000 MHz at 2160, 10 at 2748.
xe = logax(1387, 0.1, 1997, 100.0)
yf = logax(2160, 3000.0, 2748, 10.0)
g = [[1388, 2630], [1600, 2500], [1790, 2370], [1930, 2337], [2063, 2394]]
pts = trace(im, "col", 1392, 2060, 12, g, 4, 110, 15)
out["ft"] = [[round(xe(a), 4), round(yf(c), 2)] for a, c in pts]

# IC - VCE (top left): x VCE 0 at 348.5, 8 at 1056; y IC 0 at 1169.5, 240 at 583. IB = 0.2 mA.
xc = lin(348.5, 0.0, 1056, 8.0)
yc = lin(1169.5, 0.0, 583, 240.0)
g = [[360, 1115], [450, 1110], [600, 1106], [800, 1100], [810, 1100]]
pts = trace(im, "col", 400, 805, 15, g, 3, 110, 10)
out["ic_vce_02"] = [[round(xc(a), 4), round(yc(c), 3)] for a, c in pts]

Path(".claude/skills/fit-model/worked/c1815/data.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, len(v), v if k != "vcs_runs" else "")
for k, v in out["vcs_runs"].items():
    print("vcs", k, v)
