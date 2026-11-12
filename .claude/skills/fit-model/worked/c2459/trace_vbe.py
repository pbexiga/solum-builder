"""2SC2459 IC - VBE (25 °C, VCE 6 V), page 2, read by pixel. Crop vbe.png (300 dpi page 2).
Linear axes: IC 0 at y 468.5, 200 mA at 36; VBE 0 at x 169.5, 1.6 V at 893. The middle of the
three lines, read row by row from 10 to 190 mA (below 10 mA the linear scale can't place it)."""
import json
import numpy as np
from PIL import Image

im = np.array(Image.open(".claude/skills/fit-model/worked/c2459/vbe.png").convert("L")) < 128
im[250:300, 260:620] = False  # the temperature labels
ic = lambda y: (468.5 - y) / 2.1625
vbe = lambda x: (x - 169.5) / 452.19
grid_cols = {x for x in range(im.shape[1]) if im[40:460, x].mean() > 0.5}
out = []
for ma in range(10, 195, 10):
    y = round(468.5 - ma * 2.1625)
    row, found, start = im[y, 300:620], [], None
    for x, d in enumerate(row):
        x0 = x + 300
        d = d and x0 not in grid_cols
        if d and start is None: start = x0
        if not d and start is not None:
            if x0 - start >= 3: found.append((start + x0 - 1) / 2)
            start = None
    if len(found) == 3:
        out.append([round(ic(y), 2), round(vbe(found[1]), 4)])
    print(ma, [round(vbe(f), 3) for f in found])
json.dump({"vbe": out}, open(".claude/skills/fit-model/worked/c2459/vbe.json", "w"))
print(out)
