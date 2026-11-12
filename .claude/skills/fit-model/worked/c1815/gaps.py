"""The dark runs at chosen currents on the hFE and fT plots, where trace lost the line."""
import math
import sys
sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import load, runs

im = load("/scr/t1815/hi-2.pgm")
col = lambda x0, ma: round(x0 + 203.5 * (math.log10(ma) + 1))  # noqa: E731
hy = lambda r: 10 ** (math.log10(3000) + (r - 583) * (1 - math.log10(3000)) / (1170 - 583))  # noqa: E731
fy = lambda r: 10 ** (math.log10(3000) + (r - 2160) * (1 - math.log10(3000)) / (2748 - 2160))  # noqa: E731
for ma in (140, 150, 160, 170, 180, 190, 200, 205):
    c = col(1389, ma) + 4
    print("hfe", ma, c, [round(hy(r + 583), 1) for r in runs(im.T[c][583:1170] < 110, 3)])
for ma in ():
    c = col(1387 - 2, ma) + 2
    c = round(1387 + 203.33 * (math.log10(ma) + 1)) + 4
    print("ft", ma, c, [round(fy(r + 2160), 1) for r in runs(im.T[c][2160:2748] < 110, 3)])
