"""2SC2459 VCE(sat) - IC (25 °C, IC/IB = 10), page 2, read by pixel. Crop vcs.png (300 dpi
page 2). Axes: 1 V at y 49.5, 0.1 V at 267.5; IC 1 mA at x 327, 10 at 552.5. The 25 °C line is
the middle one where the three part (past 18 mA), followed by continuity back; under 30 mA the
lines overlap within a few pixels, so it reads the band's middle there."""
import json
import numpy as np
from PIL import Image

im = np.array(Image.open(".claude/skills/fit-model/worked/c2459/vcs.png").convert("L")) < 128
im[255:295, 480:660] = False  # "Ta = 100°C"
im[336:420, 560:740] = False  # the "25" and "-25" labels and arrows
ic = lambda x: 10 ** ((x - 327.0) / 225.5)
v = lambda y: 10 ** (-1 - (y - 267.5) / 218.0)
vert = {x for x in range(im.shape[1]) if im[60:400, x].mean() > 0.7}


def runs(x):
    col, found, start = im[200:336, x], [], None
    for y, d in enumerate(col):
        if d and start is None: start = y
        if not d and start is not None:
            if 5 <= y - start <= 30: found.append(((start + y - 1) / 2 + 200, y - start))
            start = None
    return found


def follow(xs, y0):
    pts, prev = [], y0
    for x in xs:
        if any(abs(x - g) <= 2 for g in vert): continue
        r = runs(x)
        if not r: continue
        band = sorted(t for t in r if 200 < t[0] < 336)
        if x >= 640 and len(band) == 3:
            y, n = band[1]; prev = y; pts.append((x, y, n)); continue
        y, n = min(r, key=lambda t: abs(t[0] - prev))
        if abs(y - prev) > (8 if x < 650 else 16): continue
        prev = y; pts.append((x, y, n))
    return pts

r0 = runs(760); print("at 70 mA", r0)
y0 = sorted(t[0] for t in r0)[len(r0) // 2]
pts = follow(range(760, 170, -3), y0)[::-1] + follow(range(763, 860, 3), y0)
out = [[round(ic(x), 4), round(v(y), 4)] for x, y, n in pts]
for o, p in list(zip(out, pts))[::6]: print(o, p[2])
json.dump({"vcs": out}, open(".claude/skills/fit-model/worked/c2459/vcs.json", "w"))
