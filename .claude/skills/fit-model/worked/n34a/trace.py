"""Trace MTM Scientific's 1N34A curve (dioper.jpg): frame 56..555 px = 0..0.6 V, 339..59 px = 0..3 mA."""
import json
import numpy as np
from PIL import Image
a = np.asarray(Image.open(".claude/skills/fit-model/worked/n34a/dioper.jpg").convert("L")).astype(int)
GR, GC = [59, 106, 152, 199, 246, 293, 339], [56, 139, 222, 306, 389, 472, 555]
v = lambda x: (x - 56) / (555 - 56) * 0.6
ma = lambda y: (339 - y) / (339 - 59) * 3.0
pts = []
for x in range(57, 555):
    if any(abs(x - c) <= 1 for c in GC):
        continue
    ys = [y for y in range(60, 337) if a[y, x] < 110 and all(abs(y - r) > 1 for r in GR)]
    if ys and max(ys) - min(ys) < 12:
        pts.append((round(v(x), 4), round(ma(float(np.mean(ys))), 4)))
json.dump(pts, open(".claude/skills/fit-model/worked/n34a/curve.json", "w"))
for p in pts[::25]: print(p)
print(len(pts), pts[0], pts[-1])
