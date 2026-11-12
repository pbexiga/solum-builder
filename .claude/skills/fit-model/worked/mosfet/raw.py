"""Curves inside one plot frame of a PDF page, mapped with axes given by hand (linear).

raw.py sheet.pdf page x0 x1 xlo xhi y0 y1 ylo yhi [xlog|ylog|xlog,ylog]  (frame in PDF
points: x0/x1 left/right, y0 top, y1 bottom; xlo/xhi, ylo/yhi the axis values there)
Prints each stroked curve's points as values: for figures plots.py maps wrongly."""
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from svgpaths import subpaths  # noqa: E402

pdf, page = sys.argv[1], int(sys.argv[2])
x0, x1, xlo, xhi, y0, y1, ylo, yhi = map(float, sys.argv[3:11])
with tempfile.TemporaryDirectory() as d:
    svg = os.path.join(d, "p.svg")
    subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf, svg], check=True)
    P = subpaths(svg)
logs = sys.argv[11].split(",") if len(sys.argv) > 11 else []


def scale(t, lo, hi, log):
    if log:
        return 10 ** (math.log10(lo) + t * (math.log10(hi) - math.log10(lo)))
    return lo + t * (hi - lo)


mx = lambda x: scale((x - x0) / (x1 - x0), xlo, xhi, "xlog" in logs)  # noqa: E731
my = lambda y: scale((y1 - y) / (y1 - y0), ylo, yhi, "ylog" in logs)  # noqa: E731
for k, (p, st) in enumerate(P):
    inside = [(x, y) for x, y in p if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1]
    if len(inside) < 3 or len(inside) < 0.8 * len(p):
        continue
    if all(abs(a - c) < .05 or abs(b - d) < .05 for (a, b), (c, d) in zip(p, p[1:])):
        continue  # grid lines
    if "stroke" not in st and "none" not in st:
        continue
    pts = sorted({(float(f"{mx(x):.4g}"), float(f"{my(y):.4g}")) for x, y in inside})
    print(k, len(pts), pts)
