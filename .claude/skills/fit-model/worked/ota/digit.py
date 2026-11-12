"""Read the vector curves of one plot frame, the axes mapped from the frame's edges.
digit.py sheet.pdf page frame# xleft xright xlog ybottom ytop ylog [curve#...]
(xlog/ylog: 1 or 0). The edges' values are read off the rendered page (checked against
the grid lines with frames.py), since several sheets' tick labels sit off their lines."""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frames import load  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "plots.py")).read().replace("\nmain()\n", "\n")
g = {"__file__": os.path.join(HERE, "..", "plots.py")}
exec(compile(src, "plots.py", "exec"), g)


def axis(p0, p1, v0, v1, log):
    if log:
        a, b = math.log10(v0), math.log10(v1)
        return lambda p: 10 ** (a + (p - p0) / (p1 - p0) * (b - a))
    return lambda p: v0 + (p - p0) / (p1 - p0) * (v1 - v0)


def curves(pdf, page, frame, xl, xr, xlog, yb, yt, ylog):
    P = load(pdf, page)
    b = g["frames"](P)[frame]
    (x0, x1), (y0, y1) = b["x"], b["y"]
    mx = axis(x0, x1, xl, xr, xlog)
    my = axis(y1, y0, yb, yt, ylog)
    out = {}
    for k, (p, st) in enumerate(P):
        inside = [(x, y) for x, y in p if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1]
        if len(inside) < 3 or len(inside) < 0.8 * len(p):
            continue
        xs = [x for x, y in inside]
        if max(xs) - min(xs) < 15:
            continue
        if all(abs(a - c) < .05 or abs(bb - d) < .05 for (a, bb), (c, d) in zip(p, p[1:])):
            continue
        if "stroke" not in st and "none" not in st:
            continue
        out[k] = sorted((mx(x), my(y)) for x, y in inside)
    return out


if __name__ == "__main__":
    a = sys.argv
    cs = curves(a[1], int(a[2]), int(a[3]), float(a[4]), float(a[5]), a[6] == "1",
                float(a[7]), float(a[8]), a[9] == "1")
    want = a[10:]
    for k, pts in cs.items():
        if want and str(k) not in want:
            continue
        print(k, len(pts), " ".join(f"({x:.4g},{y:.4g})" for x, y in pts))
