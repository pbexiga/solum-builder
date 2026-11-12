"""Read raster curve sheets by pixel (after .claude/skills/fit-model/worked/ac128/grid.py, trace.py and
.claude/skills/fit-model/worked/mosfet/bs170_pixels.py).

pix.py grid IMG x0 y0 x1 y1 [FRAC THR]  grid lines in a crop: columns / rows darker than THR over FRAC
pix.py runs IMG col|row A1,A2,.. [MINW THR]   thick dark runs across those columns / rows
pix.py trace IMG col|row LO HI STEP GUESS [MINW THR]
    for each column (col) or row (row) from LO to HI, the centre of the dark run at least
    MINW px wide nearest the guess (GUESS: json [[along, across], ...], linear between)
IMG is a pdfimages page (ppm/pgm); all coordinates are full-resolution pixels (300 dpi).
"""
import json
import sys

import numpy as np


def load(path: str) -> np.ndarray:
    data = open(path, "rb").read()
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
        parts.append(data[k:j])
        k = j
    w, h = int(parts[1]), int(parts[2])
    ch = 3 if parts[0] == b"P6" else 1
    img = np.frombuffer(data[k + 1:k + 1 + w * h * ch], np.uint8).reshape(h, w, ch)
    return img.mean(axis=2)


def axis(pix_vals):
    """pixel -> value through [(pixel, value), ...] labelled major lines, linear between
    (a stretched scan is followed line by line); outside them NaN."""
    p = np.array([a for a, _ in pix_vals], float)
    v = np.array([b for _, b in pix_vals], float)
    o = np.argsort(p)
    return lambda x: float(np.interp(x, p[o], v[o], left=np.nan, right=np.nan))


def groups(idx) -> list[float]:
    out: list[list[int]] = []
    for i in idx:
        if out and i - out[-1][-1] <= 1:
            out[-1].append(int(i))
        else:
            out.append([int(i)])
    return [round(sum(g) / len(g), 1) for g in out]


def grid(img, x0, y0, x1, y1, frac=0.5, thr=128):
    """Grid line positions in a crop; a line whose ink (summed over +-2 px) is over 1.2x
    the median is marked '*' (the darker major lines, every 5th or 10th)."""
    crop = img[y0:y1, x0:x1]
    dark = crop < thr
    out = []
    for axis, off in ((0, x0), (1, y0)):
        ink = (255 - crop).mean(axis=axis)
        pos = groups(np.nonzero(dark.mean(axis=axis) > frac)[0])
        w = [float(ink[max(int(p) - 2, 0):int(p) + 3].sum()) for p in pos]
        med = float(np.median(w)) if w else 0.0
        out.append([f"{off + p:g}{'*' if v > 1.2 * med else ''}" for p, v in zip(pos, w)])
    return out


def runs(line, minw):
    out, start = [], None
    for i, d in enumerate(np.append(line, False)):
        if d and start is None:
            start = i
        if not d and start is not None:
            if i - start >= minw:
                out.append((start + i - 1) / 2)
            start = None
    return out


def trace(img, axis, lo, hi, step, guess, minw=5, thr=110, reach=25):
    g = np.array(guess, float)
    a_img = img.T if axis == "col" else img
    pts = []
    for a in range(lo, hi + 1, step):
        want = float(np.interp(a, g[:, 0], g[:, 1]))
        near = [r for r in runs(a_img[a] < thr, minw) if abs(r - want) < reach]
        if near:
            pts.append((a, round(min(near, key=lambda r: abs(r - want)), 1)))
    return pts


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    im = load(path)
    if cmd == "grid":
        x0, y0, x1, y1 = map(int, sys.argv[3:7])
        xs, ys = grid(im, x0, y0, x1, y1, *[float(v) for v in sys.argv[7:9]])
        print("x", xs)
        print("y", ys)
    elif cmd == "runs":  # pix.py runs IMG col|row A1,A2,... [MINW THR]: thick runs across each
        axis, at = sys.argv[3], [int(v) for v in sys.argv[4].split(",")]
        minw, thr = (int(v) for v in (sys.argv[5:7] or [5, 110]))
        a_img = im.T if axis == "col" else im
        for a in at:
            print(a, runs(a_img[a] < thr, minw))
    elif cmd == "trace":
        axis, lo, hi, step = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
        extra = [int(v) for v in sys.argv[8:10]]
        for a, c in trace(im, axis, lo, hi, step, json.loads(sys.argv[7]), *extra):
            print(a, c)
