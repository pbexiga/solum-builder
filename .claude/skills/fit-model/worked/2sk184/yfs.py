"""Digitise the 2SK184 |Yfs|-IDSS line (Toshiba sheet 2007-11-01, page 2, rendered at 300 dpi)."""
import sys
from PIL import Image; import numpy as np
a = np.array(Image.open('.claude/skills/fit-model/worked/2sk184/yfs.png').convert('L')) < 110
# grid lines: columns/rows that are dark over most of the plot
cols = [x for x in range(a.shape[1]) if a[40:640, x].mean() > 0.6]
rows = [y for y in range(a.shape[0]) if a[y, 95:810].mean() > 0.6]
print('cols', cols); print('rows', rows)
if len(sys.argv) > 1:
    X1, X10, Y10, Y100 = map(float, sys.argv[1:5])
    DX = X10 - X1; DY = Y10 - Y100
    pts = []
    for x in range(140, 730, 2):
        ys = np.where(a[300:630, x])[0] + 300
        runs = [r for r in (np.split(ys, np.where(np.diff(ys) > 1)[0] + 1) if len(ys) else []) if 6 <= len(r) <= 14]
        if len(runs) == 1:
            pts.append((10 ** ((x - X1) / DX), 10 * 10 ** ((Y10 - runs[0].mean()) / DY)))
    p = np.array(pts); lx, ly = np.log10(p[:, 0]), np.log10(p[:, 1])
    for _ in range(2):
        k, b = np.polyfit(lx, ly, 1); keep = np.abs(ly - (k * lx + b)) < 0.03; lx, ly = lx[keep], ly[keep]
    print(len(lx), 'pts; |Yfs| = %.4g mS * Idss_mA^%.4f' % (10 ** b, k))
    for i in (1, 4.11, 10): print(i, 'mA ->', round(10 ** b * i ** k, 2), 'mS')
