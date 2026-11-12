"""2SC2459 hFE - IC (25 °C, VCE 6 V), page 2 of Toshiba's sheet (2003-03-27), read by pixel.
Crop hfe.png (300 dpi page 2): IC 1 mA at x 241.5, 10 at 468, 100 at 693.5; hFE 100 at y 381.5,
10 at 622. The 25 °C line followed by continuity from 1 mA (as .claude/skills/fit-model/worked/c2240/trace.py)."""
import json
import numpy as np
from PIL import Image

im = np.array(Image.open(".claude/skills/fit-model/worked/c2459/hfe.png").convert("L")) < 128
im[:170, 465:] = False  # the legend box
im[190:230, 270:450] = False  # "Ta = 100°C"
im[275:300, 350:410] = False  # "25"
im[315:345, 350:410] = False  # "-25"
ic = lambda x: 10 ** ((x - 241.5) / 226.0)
hfe = lambda y: 10 ** (2 - (y - 381.5) / 240.25)


def runs(x):
    col, found, start = im[150:560, x], [], None
    for y, v in enumerate(col):
        if v and start is None: start = y
        if not v and start is not None:
            if 5 <= y - start <= 14: found.append((start + y - 1) / 2 + 150)
            start = None
    return found


def follow(xs, y0):
    pts, prev = [], y0
    for x in xs:
        r = runs(x)
        if not r: continue
        y = min(r, key=lambda v: abs(v - prev))
        if abs(y - prev) > (10 if x < 650 else 28): continue
        prev = y; pts.append((x, y))
    return pts

start = runs(244); print("at 1 mA", start, [round(hfe(s)) for s in start])
y0 = min(start, key=lambda v: abs(v - 266.6))  # hFE 300
pts = follow(range(244, 128, -4), y0)[::-1] + follow(range(248, 800, 4), y0)
out = [[round(ic(x), 4), round(hfe(y), 1)] for x, y in pts]
for o in out[::4]: print(o)
json.dump({"hfe": [o for o in out if o[0] <= 105]}, open(".claude/skills/fit-model/worked/c2459/hfe.json", "w"))
