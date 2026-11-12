"""Read onsemi MMBF170/D Rev. 9 figures (raster) by pixel: frame from the grid lines,
then dark pixels down a column at a given x value."""
import sys
import numpy as np


def ppm(path):
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
        parts.append(data[k:j]); k = j
    w, h = int(parts[1]), int(parts[2])
    img = np.frombuffer(data[k + 1:k + 1 + w * h * 3], np.uint8).reshape(h, w, 3)
    return img.mean(axis=2)


def lines(dark, axis, frac):
    """Indices of rows (axis=1) or columns (axis=0) more than frac dark."""
    s = dark.mean(axis=axis)
    idx = np.nonzero(s > frac)[0]
    groups, cur = [], [idx[0]] if len(idx) else []
    for i in idx[1:]:
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            groups.append(cur); cur = [i]
    if cur:
        groups.append(cur)
    return [float(np.mean(g)) for g in groups]


def frames():
    g = ppm(sys.argv[1])
    half = g[:, : g.shape[1] // 2]
    dark = half < 128
    print("rows", lines(dark, 1, 0.5))
    print("cols", lines(dark, 0, 0.5))


def runs(col, skip):
    """Centres of dark runs in a pixel column, leaving out grid rows."""
    idx = [i for i in np.nonzero(col < 128)[0] if all(abs(i - s) > 1.5 for s in skip)]
    out, cur = [], []
    for i in idx:
        if cur and i != cur[-1] + 1:
            out.append(float(np.mean(cur))); cur = []
        cur.append(i)
    if cur:
        out.append(float(np.mean(cur)))
    return out


def fig1(path):
    g = ppm(path)
    x = lambda v: 46 + v * (410 - 46) / 5  # noqa: E731
    i = lambda y: (234 - y) / (234 - 8) * 2.0  # noqa: E731
    grid = [8, 64, 121, 178, 234]
    for v in (0.5, 1.0, 2.0, 3.0, 4.5):
        print(f"Fig 1 VDS {v} V:", [round(i(y), 3) for y in runs(g[:, int(round(x(v)))], grid)])


def fig5(path):
    g = ppm(path)
    v = lambda x: (x - 45) / (421 - 45) * 10  # noqa: E731
    y = lambda a: 248 - a / 2.0 * (248 - 14)  # noqa: E731
    cols = [45, 120, 195, 270, 345, 421]
    for a in (0.1, 0.2, 0.4, 0.8, 1.2, 1.6, 1.9):
        row = g[int(round(y(a))), : g.shape[1] // 2]
        print(f"Fig 5 ID {a} A: VGS", [round(v(x), 3) for x in runs(row, cols)])


def fig9(path):
    g = ppm(path)
    import math
    x = lambda vds: 42 + math.log10(vds) * (408 - 42) / math.log10(50)  # noqa: E731
    c = lambda yy: 10 ** ((263 - yy) / (263 - 38) * math.log10(60))  # noqa: E731
    grid = [38, 48, 60, 76, 98, 136, 142, 149, 156, 165, 175, 187, 203, 225, 263]
    for vds in (1.02, 2, 5, 10, 25, 50):
        col = int(round(min(x(vds), 406)))
        print(f"Fig 9 VDS {vds} V: pF", [round(c(yy), 2) for yy in runs(g[:, col], grid)])


if __name__ == "__main__":
    d = sys.argv[1]
    fig1(f"{d}/i-000.ppm"); fig5(f"{d}/i-002.ppm"); fig9(f"{d}/i-006.ppm")
