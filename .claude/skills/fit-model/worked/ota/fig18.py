"""CA3080 Figure 18 (vector, broken y axis): grid rows mapped one by one to their labels."""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from digit import curves  # noqa: E402

ROWS = [(84.72, 15), (99.93, 14.5), (115.53, 14), (128.79, 13.5), (143.99, 13),
        (173.24, -13), (188.45, -13.5), (202.09, -14), (218.86, -14.5), (232.37, -15)]


def yval(p):
    for (a, va), (b, vb) in zip(ROWS, ROWS[1:]):
        if a <= p <= b and abs(va - vb) <= 0.5:
            return va + (p - a) / (b - a) * (vb - va)
    return None


if __name__ == "__main__":
    # raw pt: map x by frame edges (0.1..1000 µA), y left in pt (yb=232.37 at "0", yt=84.72 at "1")
    cs = curves(sys.argv[1], 9, 0, 0.1, 1000, True, 232.37, 84.72, False)
    for k, pts in cs.items():
        out = [(round(x, 3), yval(y)) for x, y in pts]
        print(k, [(x, round(v, 3)) for x, v in out if v is not None])
