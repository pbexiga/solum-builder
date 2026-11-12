"""2SC2458 curves (25 °C) from page 2 of Toshiba's sheet (2003-03-27), read by pixel off the 300 dpi
render (crops from crop.py). Axes from the grid lines (grid.py):
hfe.png: IC 0.1 mA at x 44, 206.2 px a decade; hFE 10 at y 614, 239 px a decade.
vcs.png: IC 0.1 mA at x 65, 207.7 px a decade; VCE(sat) 0.01 V at y 616, 239 px a decade.
vbe.png: VBE 0 at x 65.5, 0.2 V per 72.05 px; IB 1 µA at y 531, 155.7 px a decade.
Rows where the IB - VBE line touches a vertical grid line are dropped (it reads off-centre
there). The IB - VBE figure (VCE 6 V) becomes IC - VBE through the hFE line at the same VCE."""
import json
import numpy as np
from PIL import Image

D = ".claude/skills/fit-model/worked/c2458/"
load = lambda n: np.array(Image.open(D + n).convert("L")) < 128  # noqa: E731


def runs(line, lo=4, hi=12):
    found, start = [], None
    for i, v in enumerate(list(line) + [False]):
        if v and start is None: start = i
        if not v and start is not None:
            if lo <= i - start <= hi: found.append((start + i - 1) / 2)
            start = None
    return found


def follow(im, xs, y0, jump=8):
    pts, prev = [], y0
    for x in xs:
        r = runs(im[:, x])
        if not r: continue
        y = min(r, key=lambda v: abs(v - prev))
        if abs(y - prev) > jump: continue
        prev = y; pts.append((x, y))
    return pts


# hFE: the solid 25 °C line, about 139 at 1 mA (y 340.5); the dashed VCE = 1 V lines lie below it.
im = load("hfe.png"); im[:200, 420:] = False  # legend
im[250:290, 160:330] = False; im[310:333, 260:320] = False; im[345:372, 260:320] = False  # labels
pts = follow(im, range(250, 40, -3), 340.5)[::-1] + follow(im, range(253, 740, 3), 340.5)
hfe = [[round(10 ** (-1 + (x - 44) / 206.2), 4), round(10 ** (1 + (614 - y) / 239), 1)] for x, y in pts]
# vcs: the middle line, about 0.04 V at 1 mA.
im = load("vcs.png"); im[:200, 440:] = False; im[400:445, 230:400] = False; im[460:590, 270:380] = False
y0 = 616 - 239 * (np.log10(0.04) + 2)
pts = follow(im, range(273, 60, -3), y0, 6)[::-1] + follow(im, range(276, 760, 3), y0, 6)
vcs = [[round(10 ** (-1 + (x - 65) / 207.7), 4), round(10 ** (-2 + (616 - y) / 239), 4)] for x, y in pts]
# IB - VBE: the middle of the three lines, row by row.
im = load("vbe.png"); im[300:350, 80:400] = False; im[:150, 420:] = False
ibv = []
for y in range(60, 612, 6):
    r = [c for c in runs(im[y, 70:420], 4, 14)]
    # a line crossing a vertical grid line (0.2 V steps) merges with it and reads off-centre
    if len(r) == 3 and min(abs(r[1] + 70 - g) for g in (137, 209, 281, 353.5)) > 12:
        ibv.append((10 ** ((531 - y) / 155.7), (r[1] + 70 - 65.5) / 72.05 * 0.2))
hx = np.log10([h[0] for h in hfe]); hy = [h[1] for h in hfe]
vbe = []
for ib_ua, v in ibv:
    ic = ib_ua * 1e-3 * 139
    for _ in range(20):
        ic = ib_ua * 1e-3 * float(np.interp(np.log10(ic), hx, hy))
    vbe.append([round(ic, 4), round(v, 4)])
vbe.sort()
json.dump({"hfe": hfe, "vcs": vcs, "vbe": vbe, "ib_vbe": [[round(a, 4), round(b, 4)] for a, b in ibv]},
          open(D + "curves.json", "w"))
for k, v in (("hfe", hfe), ("vcs", vcs), ("vbe", vbe)):
    print(k, len(v), v[::max(1, len(v) // 10)])
