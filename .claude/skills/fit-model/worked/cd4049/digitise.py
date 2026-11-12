"""Read the CD4049UB sheet's vector figures (TI SCHS046L, pages 12-13) into values.

Axes are mapped by hand from the grid lines and their tick labels (probe.py prints them),
piecewise-linear between labelled grid lines, because plots.py can't match some labels.
python3 .claude/skills/fit-model/worked/cd4049/digitise.py  -> prints every stroked curve in each figure."""
import os, subprocess, sys, tempfile
sys.path.insert(0, ".claude/skills/fit-model/tools")
from svgpaths import subpaths  # noqa: E402

PDF = "data/spec-sheets/CD4049UB_TI_SCHS046L.pdf"
# figure: (page, frame box (x0,x1,y0,y1) in pt, x [(pt, value)], y [(pt, value)])
FIGS = {
    "5-1": (12, (93, 294, 120, 247), [(94.0, 0), (137.89, 1), (182.4, 2), (226.43, 3), (270.47, 4), (292.96, 4.5)],
            [(144.35, 5), (164.49, 4), (184.2, 3), (204.76, 2), (225.32, 1)]),
    "5-3": (12, (89, 297, 303, 446), [(90.0, 0), (110.4, 1), (130.68, 2), (151.62, 3), (172.57, 4), (193.5, 5), (213.79, 6), (234.72, 7), (255.66, 8)],
            [(321.86, 70), (338.92, 60), (356.52, 50), (374.69, 40), (392.3, 30), (409.91, 20), (427.51, 10), (445.13, 0)]),
    "5-4": (12, (339, 545, 303, 446), [(340.0, 0), (360.38, 1), (380.38, 2), (401.03, 3), (421.68, 4), (442.32, 5), (462.32, 6), (482.97, 7), (503.61, 8)],
            [(321.82, 70), (338.85, 60), (356.42, 50), (374.55, 40), (392.11, 30), (409.69, 20), (427.27, 10), (444.84, 0)]),
    "5-5": (12, (67, 263, 523, 672), [(106.82, -8), (126.34, -7), (145.86, -6), (165.37, -5), (184.29, -4), (203.81, -3), (223.33, -2), (242.85, -1), (261.14, 0)],
            [(524.96, 0), (543.75, -5), (561.41, -10), (579.64, -15), (598.45, -20), (616.67, -25), (634.9, -30), (653.13, -35)]),
    "5-6": (12, (317, 506, 522, 672), [(354.81, -8), (373.66, -7), (392.51, -6), (411.37, -5), (429.63, -4), (448.48, -3), (467.34, -2), (486.18, -1), (503.86, 0)],
            [(523.86, 0), (542.74, -5), (560.49, -10), (578.81, -15), (597.7, -20), (616.0, -25), (634.32, -30), (652.64, -35)]),
    "5-7": (13, (93, 295, 75, 222), [(93.05 + 14.43 * k, k) for k in range(11)],
            [(221.15 - 12.0044 * k, k) for k in range(11)]),
}


def interp(pts, v):
    pts = sorted(pts)
    for (a, x), (b, y) in zip(pts, pts[1:]):
        if v <= b or (b, y) == pts[-1]:
            return x + (v - a) / (b - a) * (y - x)


_cache = {}


def paths(page):
    if page not in _cache:
        with tempfile.TemporaryDirectory() as d:
            svg = os.path.join(d, "p.svg")
            subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), PDF, svg], check=True)
            _cache[page] = subpaths(svg)
    return _cache[page]


def curves(fig):
    """{path index: [(x, y) values]} for the stroked, non-grid paths inside the figure."""
    page, (x0, x1, y0, y1), xm, ym = FIGS[fig]
    out = {}
    for k, (p, st) in enumerate(paths(page)):
        inside = [(x, y) for x, y in p if x0 <= x <= x1 and y0 <= y <= y1]
        if len(inside) < 3 or len(inside) < 0.8 * len(p):
            continue
        if all(abs(a - c) < .05 or abs(b - d) < .05 for (a, b), (c, d) in zip(p, p[1:])):
            continue
        if "stroke" not in st and "none" not in st:
            continue
        out[k] = [(round(interp(xm, x), 4), round(interp(ym, y), 4)) for x, y in inside]
    return out


if __name__ == "__main__":
    for fig in (sys.argv[1:] or FIGS):
        for k, v in curves(fig).items():
            print(fig, k, len(v), v)


def crossing(fig, path):
    """VI where a VTC path crosses VO = VI (linear between its points)."""
    pts = sorted(curves(fig)[path])
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if (b - a) * (d - c) <= 0 and (b - a) != (d - c):
            t = (b - a) / ((b - a) - (d - c))
            return a + t * (c - a)


def slope(fig, path, lo, hi):
    """Steepest drawn dVO/dVI between output levels lo..hi (from points that far apart)."""
    pts = sorted((y, x) for x, y in curves(fig)[path] if lo <= y <= hi)
    return (pts[-1][0] - pts[0][0]) / (pts[-1][1] - pts[0][1])


def vi_at(fig, path, vo):
    """VI where a VTC path first reaches VO = vo, walking from its high-output end."""
    pts = curves(fig)[path]
    if pts[0][1] < pts[-1][1]:
        pts = pts[::-1]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if b >= vo >= d and b != d:
            return a + (vo - b) / (d - b) * (c - a)


def vtc25(vcc, fracs=(0.98, 0.95, 0.9, 0.8, 0.65, 0.5, 0.35, 0.2, 0.1, 0.05)):
    """25 °C VTC points (VI, VO) between Figure 5-7's -55 °C and 125 °C curves (80/180 of the way)."""
    from sheet import VTC_PATHS
    out = []
    for f in fracs:
        cold = vi_at("5-7", VTC_PATHS[(vcc, -55)], f * vcc)
        hot = vi_at("5-7", VTC_PATHS[(vcc, 125)], f * vcc)
        out.append((round(cold + (hot - cold) * 80 / 180, 3), round(f * vcc, 3), round(cold, 3), round(hot, 3)))
    return out
