"""List vector paths in a page SVG inside a box (pt): svgpaths.py page.svg x0 y0 x1 y1"""

import re
import sys
import xml.etree.ElementTree as ET


def mat(t):
    m = re.match(r"matrix\(([^)]*)\)", t or "")
    if not m:
        return (1, 0, 0, 1, 0, 0)
    return tuple(float(x) for x in re.split(r"[ ,]+", m.group(1).strip()))


def mul(a, b):  # a∘b
    return (
        a[0] * b[0] + a[2] * b[1],
        a[1] * b[0] + a[3] * b[1],
        a[0] * b[2] + a[2] * b[3],
        a[1] * b[2] + a[3] * b[3],
        a[0] * b[4] + a[2] * b[5] + a[4],
        a[1] * b[4] + a[3] * b[5] + a[5],
    )


def points(d, m):
    """On-curve points: M/L endpoints, and each cubic sampled at t = 1/4, 1/2, 3/4, 1."""
    toks = re.findall(r"[MLCZmlcz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    pts, cmd, k = [], "M", 0
    while k < len(toks):
        if toks[k] in "MLCZmlcz":
            cmd = toks[k]
            k += 1
            continue
        if cmd in "ML":
            pts.append((float(toks[k]), float(toks[k + 1])))
            k += 2
        elif cmd == "C":
            (x0, y0) = pts[-1]
            c = [float(t) for t in toks[k : k + 6]]
            k += 6
            for t in (0.25, 0.5, 0.75, 1.0):
                u = 1 - t
                pts.append(
                    (
                        u**3 * x0 + 3 * u * u * t * c[0] + 3 * u * t * t * c[2] + t**3 * c[4],
                        u**3 * y0 + 3 * u * u * t * c[1] + 3 * u * t * t * c[3] + t**3 * c[5],
                    )
                )
        else:
            k += 1
    return [(m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]) for x, y in pts]


def walk(el, m, out):
    m = mul(m, mat(el.get("transform")))
    tag = el.tag.split("}")[-1]
    if tag == "path" and el.get("d"):
        out.append(
            (
                points(el.get("d"), m),
                el.get("style", "")
                + " "
                + str(el.get("stroke-width", ""))
                + " "
                + str(el.get("stroke", ""))
                + " "
                + str(el.get("fill", "")),
            )
        )
    for c in el:
        walk(c, m, out)


def paths(svg):
    out = []
    walk(ET.parse(svg).getroot(), (1, 0, 0, 1, 0, 0), out)
    return out


if __name__ == "__main__":
    svg, x0, y0, x1, y1 = sys.argv[1], *map(float, sys.argv[2:6])
    for i, (p, st) in enumerate(paths(svg)):
        if p and all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in p):
            xs = [x for x, _ in p]
            ys = [y for _, y in p]
            print(
                i, len(p), f"x {min(xs):.1f}-{max(xs):.1f} y {min(ys):.1f}-{max(ys):.1f}", st[:90]
            )


def subpaths(svg):
    """Like paths(), but each M...-started piece of a path on its own."""
    out = []

    def walk2(el, m):
        m = mul(m, mat(el.get("transform")))
        if el.tag.split("}")[-1] == "path" and el.get("d"):
            st = " ".join(str(el.get(k, "")) for k in ("stroke-width", "stroke", "fill"))
            for piece in re.split(r"(?=M)", el.get("d")):
                if piece.strip():
                    out.append((points(piece, m), st))
        for c in el:
            walk2(c, m)

    walk2(ET.parse(svg).getroot(), (1, 0, 0, 1, 0, 0))
    return out
