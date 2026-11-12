"""2SC2240 VCE(sat) - IC (25 °C, IC/IB = 10), page 3, read by pixel. Crop vcs.png (300 dpi
page 3, box 1250,1430,2420,2200). Axes: 1 V at y 174, 0.1 V at 413, 0.01 V at 651.5; IC 1 mA
at x 294, 10 at 522, 100 at 748. The 25 °C line is the middle one where the three part
(30 mA, the sheet's arrow), followed by continuity both ways; under 3 mA the lines overlap
within a pixel or two, so it reads the band's middle there."""
import json
import numpy as np
from PIL import Image

im = np.array(Image.open(".claude/skills/fit-model/worked/c2240/vcs.png").convert("L")) < 128
ic = lambda x: 10 ** ((x - 294.0) / 227.0)
v = lambda y: 10 ** (-1 - (y - 413.0) / 238.75)
vert = {x for x in range(im.shape[1]) if im[560:640, x].mean() > 0.8}


def runs(x):
    col, found, start = im[300:560, x], [], None
    for y, d in enumerate(col):
        if d and start is None: start = y
        if not d and start is not None:
            if 5 <= y - start <= 30: found.append(((start + y - 1) / 2 + 300, y - start))
            start = None
    return found


def follow(xs, y0):
    pts, prev = [], y0
    for x in xs:
        if any(abs(x - g) <= 2 for g in vert): continue
        r = runs(x)
        if not r: continue
        band = sorted(t for t in r if 340 < t[0] < 470)
        if x >= 704 and len(band) == 3:  # the three lines apart: the middle is 25 °C
            y, n = band[1]; prev = y; pts.append((x, y, n)); continue
        else:
            y, n = min(r, key=lambda t: abs(t[0] - prev))
        if abs(y - prev) > (8 if x < 650 else 16): continue
        prev = y; pts.append((x, y, n))
    return pts

r0 = runs(640); print("at 33 mA", r0)
y0 = sorted(t[0] for t in r0)[1]
pts = follow(range(640, 140, -4), y0)[::-1] + follow(range(644, 816, 4), y0)
out = [[round(ic(x), 4), round(v(y), 4)] for x, y, n in pts]
for o, p in list(zip(out, pts))[::5]: print(o, p[2])
json.dump({"vcs": out}, open(".claude/skills/fit-model/worked/c2240/vcs.json", "w"))
