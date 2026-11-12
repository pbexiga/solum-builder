"""2SC2240 hFE - IC (25 °C, VCE 6 V), page 3 of Toshiba's sheet (2003-03-25), read by pixel.
Crop hfe.png (300 dpi page 3, box 300,1330,1280,1830): 225 px a decade on both axes. The 25 °C
line is followed by continuity from 1 mA, where the three lines are well apart."""
import json
import numpy as np
from PIL import Image

im = np.array(Image.open(".claude/skills/fit-model/worked/c2240/hfe.png").convert("L")) < 128
# grid lines are 2-4 px thick, the curves 5-6 px: only runs of 5 px or more are curve (a curve
# lying on a grid line makes a longer run, which is kept)
im[276:, :485] = False  # the legend box
ic = lambda x: 10 ** ((x - 237.0) / 225.0)
hfe = lambda y: 10 ** (3 - (y - 48.5) / 225.5)


def runs(x):
    col, found, start = im[52:390, x], [], None
    for y, v in enumerate(col):
        if v and start is None: start = y
        if not v and start is not None:
            if 5 <= y - start <= 14: found.append((start + y - 1) / 2 + 52)
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

start = runs(240); print("at 1 mA", start)
y0 = min(start, key=lambda v: abs(v - 166.4))  # hFE 300
pts = follow(range(240, 125, -4), y0)[::-1] + follow(range(244, 792, 4), y0)
out = [[round(ic(x), 4), round(hfe(y), 1)] for x, y in pts]
for o in out[::4]: print(o)
json.dump({"hfe": out}, open(".claude/skills/fit-model/worked/c2240/hfe.json", "w"))
