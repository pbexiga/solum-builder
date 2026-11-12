"""2SC2240 IC - VBE (25 °C, VCE 6 V), page 3, read by pixel. Crop vbe.png (300 dpi page 3,
box 300,1980,1260,2560). Linear axes: IC 0 at y 479.5, 200 mA at 85; VBE 0 at x 71.5, 0.8 V
at 433.5. The middle of the three lines, read row by row from 10 to 190 mA (below 10 mA the
linear scale can't place it)."""
import json
import numpy as np
from PIL import Image

im = np.array(Image.open(".claude/skills/fit-model/worked/c2240/vbe.png").convert("L")) < 128
ic = lambda y: (479.5 - y) / 1.9725
vbe = lambda x: (x - 71.5) / 452.5
grid_cols = {70, 71, 72, 73, 162, 163, 164, 253, 254, 255, 342, 343, 344, 432, 433, 434, 435}
out = []
for ma in range(10, 195, 10):
    y = round(479.5 - ma * 1.9725)
    row, found, start = im[y, 200:520], [], None
    for x, d in enumerate(row):
        x0 = x + 200
        d = d and x0 not in grid_cols
        if d and start is None: start = x0
        if not d and start is not None:
            if x0 - start >= 3: found.append((start + x0 - 1) / 2)
            start = None
    if len(found) == 3:
        out.append([round(ic(y), 2), round(vbe(found[1]), 4)])
    print(ma, [round(vbe(f), 3) for f in found])
json.dump({"vbe": out}, open(".claude/skills/fit-model/worked/c2240/vbe.json", "w"))
print(out)
