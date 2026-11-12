"""fT - IC (VCE 10 V, 25 °C), page 3: IC 0.1 mA at x 25, 1 mA at x 240.5 (217 px a decade);
fT 100 MHz at y 372, 245 px a decade (from the 50 and 30 MHz lines). The curve is the only
run 5 px or thicker in a column clear of the grid."""
import numpy as np
from PIL import Image
im = np.array(Image.open(".claude/skills/fit-model/worked/c2458/ft.png").convert("L")) < 128
for x in (100, 150, 200, 232, 236, 246, 250, 300, 330, 360):
    col = im[190:610, x]; runs, start = [], None
    for i, v in enumerate(list(col) + [False]):
        if v and start is None: start = i
        if not v and start is not None:
            if i - start >= 5: runs.append((start + i - 1) / 2 + 190)
            start = None
    ma = 10 ** ((x - 240.5) / 217)
    print(round(ma, 3), [round(10 ** (2 + (372 - y) / 245), 1) for y in runs])
