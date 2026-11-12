"""Find the plots on a PDF page and read every curve in them.

plots.py sheet.pdf page [plot#] [curve#,...]
 - with no plot#: lists each plot (its frame, axes mapped from the tick labels) and its
   candidate curves with a short preview;
 - with plot# and curve numbers: prints those curves' points as values.
Axes: grid lines are matched to numeric tick labels (the label's centre nearest the
line); an axis is log when its labelled values grow by ratios, else linear."""

import math
import os
import re
import subprocess
import sys
import tempfile
from itertools import pairwise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgpaths import subpaths

NUM = re.compile(r"^[−-]?\d*\.?\d+[kKmM]?$")


def words(pdf, page):
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-bbox", pdf, "-"],
        capture_output=True,
        text=True,
    ).stdout
    for m in re.finditer(
        r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', out
    ):
        x0, y0, x1, y1 = map(float, m.groups()[:4])
        yield (x0 + x1) / 2, (y0 + y1) / 2, x0, x1, m.group(5).strip()


def value(t):
    t = t.replace("−", "-")
    mult = {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3}.get(t[-1], 1)
    return float(t.rstrip("kKmM")) * mult


def frames(P):
    """Plot frames: groups of long horizontal and vertical lines sharing a span."""
    hs, vs = [], []
    for p, _style in P:
        for (a, b), (c, d) in pairwise(p):
            if abs(b - d) < 0.05 and abs(a - c) > 60:
                hs.append((round(b, 2), round(min(a, c), 1), round(max(a, c), 1)))
            if abs(a - c) < 0.05 and abs(b - d) > 60:
                vs.append((round(a, 2), round(min(b, d), 1), round(max(b, d), 1)))
    boxes = {}
    for y, x0, x1 in hs:
        key = (round(x0), round(x1))
        boxes.setdefault(key, {"h": set(), "v": set()})["h"].add(y)
    out = []
    for (x0, x1), g in boxes.items():
        if len(g["h"]) < 3:
            continue
        y0, y1 = min(g["h"]), max(g["h"])
        v = sorted({x for x, a, b in vs if x0 - 1 <= x <= x1 + 1 and a <= y0 + 1 and b >= y1 - 1})
        if len(v) >= 3:
            out.append({"x": (x0, x1), "y": (y0, y1), "hs": sorted(g["h"]), "vs": v})
    return sorted(out, key=lambda b: (round(b["y"][0] / 50), b["x"][0]))


def line(xs, ys):
    """Theil-Sen: the median pairwise slope, so one label on the wrong line doesn't tilt it."""
    slopes = sorted(
        (y2 - y1) / (x2 - x1)
        for i, (x1, y1) in enumerate(zip(xs, ys, strict=True))
        for x2, y2 in list(zip(xs, ys, strict=True))[i + 1 :]
        if x2 != x1
    )
    if not slopes:
        return None
    b = slopes[len(slopes) // 2]
    off = sorted(y - b * x for x, y in zip(xs, ys, strict=True))
    return off[len(off) // 2], b


def axis(lines, labels, coord):
    """[(line, value)] for the tick labels, and whether the axis is log: position is fitted
    as a straight line in value (or log of the positive values), whichever fits better
    (RMS), and each label is snapped to the grid line nearest that fit."""
    pairs = {}
    for c, t in labels:
        near = min(lines, key=lambda g: abs(g - c))
        if abs(near - c) < 6:
            pairs.setdefault(value(t), near)
    best = None
    for log in (False, True):
        vals = sorted(v for v in pairs if v > 0 or not log)
        if len(vals) < 2:
            continue
        f = (lambda v: math.log10(v)) if log else (lambda v: v)
        xs = [f(v) for v in vals]
        ys = [pairs[v] for v in vals]
        fit = line(xs, ys)
        if fit is None:
            continue
        a, b = fit
        err = sorted((a + b * x - y) ** 2 for x, y in zip(xs, ys, strict=True))
        err = sorted(err)[: max(len(err) - 1, 2)]
        rms = math.sqrt(sum(err) / len(err))
        if best is None or rms < best[0] - 1e-3:
            best = (rms, log, a, b, f, vals)
    if best is None:
        return [], False
    rms, log, a, b, f, vals = best
    out = {}
    for v in vals:
        pred = a + b * f(v)
        near = min(lines, key=lambda g: abs(g - pred))
        if abs(pred - (near if abs(near - pred) < 1.5 else pred)) < 3:
            out[v] = near if abs(near - pred) < 1.5 else round(pred, 2)
    pts = sorted((pos, v) for v, pos in out.items())
    return [q for i, q in enumerate(pts) if i == 0 or q[0] != pts[i - 1][0]], log


def mapper(pts, log):
    f = (lambda v: math.log10(v)) if log else (lambda v: v)
    q = [(p, f(v)) for p, v in pts]

    def m(x):
        for (a, b), (c, d) in pairwise(q):
            if x <= c or (c, d) == q[-1]:
                u = b + (x - a) / (c - a) * (d - b)
                return 10**u if log else u

    return m


def main():
    pdf, page = sys.argv[1], int(sys.argv[2])
    with tempfile.TemporaryDirectory() as d:
        svg = os.path.join(d, "p.svg")
        subprocess.run(
            ["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf, svg], check=True
        )
        P = subpaths(svg)
    W = [w for w in words(pdf, page)]
    plots = frames(P)
    pick = int(sys.argv[3]) if len(sys.argv) > 3 else None
    for n, b in enumerate(plots):
        if pick is not None and n != pick:
            continue
        (x0, x1), (y0, y1) = b["x"], b["y"]
        xl = [
            (cx, t)
            for cx, cy, a, c, t in W
            if NUM.match(t) and y1 < cy < y1 + 14 and x0 - 8 < cx < x1 + 8
        ]
        yl = [
            (cy, t)
            for cx, cy, a, c, t in W
            if NUM.match(t) and x0 - 30 < c < x0 + 1 and y0 - 6 < cy < y1 + 6
        ]
        xa, xlog = axis(b["vs"], xl, "x")
        ya, ylog = axis(b["hs"], yl, "y")
        title = " ".join(
            t for cx, cy, a, c, t in W if x0 - 40 < cx < x1 + 40 and y1 + 14 < cy < y1 + 40
        )[:90]
        if pick is None:
            print(
                f"plot {n}: x {x0}-{x1} y {y0}-{y1} | x {'log' if xlog else 'lin'} {xa} | y "
                f"{'log' if ylog else 'lin'} "
                f"{ya} | {title}"
            )
        if len(xa) < 2 or len(ya) < 2:
            continue
        mx, my = mapper(xa, xlog), mapper(ya, ylog)
        for k, (p, st) in enumerate(P):
            inside = [(x, y) for x, y in p if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1]
            if len(inside) < 3 or len(inside) < 0.8 * len(p):
                continue
            xs = [x for x, y in inside]
            if max(xs) - min(xs) < 15 or all(
                abs(a - c) < 0.05 or abs(bb - d) < 0.05 for (a, bb), (c, d) in pairwise(p)
            ):
                continue
            if "stroke" not in st and "none" not in st:  # filled shapes (labels, arrows)
                continue
            vals = sorted({(float(f"{mx(x):.4g}"), float(f"{my(y):.4g}")) for x, y in inside})
            if pick is None:
                print(
                    f"   curve {k} ({len(vals)} pts) {vals[0]} … {vals[len(vals) // 2]} … "
                    f"{vals[-1]}  [{st.strip()[:25]}]"
                )
            elif str(k) in sys.argv[4].split(","):
                print(k, vals)


main()
