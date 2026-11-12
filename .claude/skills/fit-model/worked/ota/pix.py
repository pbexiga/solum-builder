"""Read LM13700 (TI SNOSBW2F) raster figures by pixel. The figures are 1-bit images
embedded in the PDF (pdfimages, img/i-NNN.png -> .pgm by ImageMagick). The plot frame is
taken from the grid lines (rows/columns more than half dark); curves are the thick
strokes left after eroding with a k x k square (grid lines are 2-3 px, curves 6-9 px).
pix.py frames | pix.py <fig> (see FIGS)"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def pgm(n):
    data = open(os.path.join(HERE, "img", f"i-{n:03d}.pgm"), "rb").read()
    parts, k = [], 0
    while len(parts) < 4:
        while data[k:k + 1].isspace():
            k += 1
        if data[k:k + 1] == b"#":
            k = data.index(b"\n", k)
            continue
        j = k
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(data[k:j]); k = j
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(data[k + 1:k + 1 + w * h], np.uint8).reshape(h, w) < 128


def groups(idx):
    out, cur = [], []
    for i in idx:
        if cur and i != cur[-1] + 1:
            out.append(cur); cur = []
        cur.append(int(i))
    if cur:
        out.append(cur)
    return out


def gridlines(d, axis, frac=0.5):
    return [(g[0] + g[-1]) / 2 for g in groups(np.nonzero(d.mean(axis=axis) > frac)[0])]


def erode(d, k):
    h, w = d.shape
    out = np.ones((h - k + 1, w - k + 1), bool)
    for i in range(k):
        for j in range(k):
            out &= d[i:h - k + 1 + i, j:w - k + 1 + j]
    pad = np.zeros_like(d)
    pad[k // 2:k // 2 + out.shape[0], k // 2:k // 2 + out.shape[1]] = out
    return pad


def axis(p0, p1, v0, v1, log):
    if log:
        a, b = math.log10(v0), math.log10(v1)
        return (lambda p: 10 ** (a + (p - p0) / (p1 - p0) * (b - a)),
                lambda v: p0 + (math.log10(v) - a) / (b - a) * (p1 - p0))
    return (lambda p: v0 + (p - p0) / (p1 - p0) * (v1 - v0),
            lambda v: p0 + (v - v0) / (v1 - v0) * (p1 - p0))


def column(n, xs, xspec, yspec, k=5, rows=None):
    """For each x value: the y values of thick strokes crossing that column."""
    d = pgm(n)
    rws, cls = gridlines(d, 1), gridlines(d, 0)
    x0, x1 = cls[0], cls[-1]
    y0, y1 = rws[0], rws[-1]  # top, bottom
    _, px = axis(x0, x1, *xspec)
    vy, _ = axis(y1, y0, *yspec)
    d = d.copy()
    for r in rws:  # blank the grid rows so thick decade lines don't read as curves
        d[max(int(r) - 3, 0):int(r) + 4, :] = False
    e = erode(d, k)
    out = {}
    for x in xs:
        c = int(round(px(x)))
        c = min(max(c, int(x0) + 4), int(x1) - 4)
        runs = groups(np.nonzero(e[int(y0) + 3:int(y1) - 2, c])[0] + int(y0) + 3)
        out[x] = [round(vy((g[0] + g[-1]) / 2), 4) for g in runs]
    return out


def row(n, ys, xspec, yspec, k=5):
    """For each y value: the x values of thick strokes crossing that row."""
    d = pgm(n)
    rws, cls = gridlines(d, 1), gridlines(d, 0)
    x0, x1 = cls[0], cls[-1]
    y0, y1 = rws[0], rws[-1]
    vx, _ = axis(x0, x1, *xspec)
    _, py = axis(y1, y0, *yspec)
    e = erode(d, k)
    out = {}
    for y in ys:
        r = int(round(py(y)))
        runs = groups(np.nonzero(e[r, int(x0) + 3:int(x1) - 2])[0] + int(x0) + 3)
        out[y] = [round(vx((g[0] + g[-1]) / 2), 4) for g in runs]
    return out


IABC = (0.1, 1000, True)
DEC = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
OFF = [0.15, 0.25, 0.45, 1.5, 2.5, 4.5, 15, 25, 45, 150, 250, 450, 950]  # between grid columns
FIGS = {
    # fig: (image, y axis (bottom, top, log), x values)
    "3": (3, (1, 1e4, True)),        # input bias current, nA
    "4": (2, (1, 1e4, True)),        # peak output current, uA
    "8": (10, (10, 1e5, True)),      # gm, umho
    "9": (9, (0.01, 100, True)),     # input resistance, Mohm
    "10": (8, (0, 2000, False)),     # amplifier bias voltage, mV
    "11": (7, (0, 7, False)),        # capacitance, pF
    "12": (6, (1, 1e4, True)),       # output resistance, Mohm
}

if __name__ == "__main__":
    what = sys.argv[1]
    if what == "frames":
        for n in range(15):
            if os.path.exists(os.path.join(HERE, "img", f"i-{n:03d}.pgm")):
                d = pgm(n)
                r, c = gridlines(d, 1), gridlines(d, 0)
                print(n, d.shape, "rows", r[0], r[-1], len(r), "cols", c[0], c[-1], len(c))
    elif what in FIGS:
        n, ys = FIGS[what]
        k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        for x, v in column(n, OFF, IABC, ys, k).items():
            print(x, v)


def column_runs(n, xs, xspec, yspec, minrun):
    """Like column, without erosion: dark runs at least minrun px tall in an off-grid
    column (grid rows are 2-6 px; a curve crossing one merges with it, moving its centre
    by at most half the grid line)."""
    d = pgm(n)
    rws, cls = gridlines(d, 1), gridlines(d, 0)
    x0, x1 = cls[0], cls[-1]
    y0, y1 = rws[0], rws[-1]
    _, px = axis(x0, x1, *xspec)
    vy, _ = axis(y1, y0, *yspec)
    out = {}
    for x in xs:
        c = min(max(int(round(px(x))), int(x0) + 8), int(x1) - 8)
        runs = groups(np.nonzero(d[int(y0) + 8:int(y1) - 7, c])[0] + int(y0) + 8)
        out[x] = [(round(vy((g[0] + g[-1]) / 2), 4), len(g)) for g in runs if len(g) >= minrun]
    return out


def row_runs(n, ys, xspec, yspec, minrun):
    """For each y value: x values of dark runs at least minrun px wide in that row."""
    d = pgm(n)
    rws, cls = gridlines(d, 1), gridlines(d, 0)
    x0, x1 = cls[0], cls[-1]
    y0, y1 = rws[0], rws[-1]
    vx, _ = axis(x0, x1, *xspec)
    _, py = axis(y1, y0, *yspec)
    out = {}
    for y in ys:
        r = int(round(py(y)))
        runs = groups(np.nonzero(d[r, int(x0) + 8:int(x1) - 7])[0] + int(x0) + 8)
        out[y] = [(round(vx((g[0] + g[-1]) / 2), 2), len(g)) for g in runs if len(g) >= minrun]
    return out


def fig13():
    """Figure 13, distortion (%) vs differential input (mVpp): x positions of both curves."""
    for y, v in row_runs(14, [0.025, 0.03, 0.045, 0.07, 0.15, 0.25, 0.45, 0.7, 1.5, 2.5, 4.5, 7, 15],
                         (1, 1000, True), (0.01, 100, True), 8).items():
        print(y, v)
