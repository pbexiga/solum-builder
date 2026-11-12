"""onsemi BS170 figures (pixels) against the Fairchild 2N7000 points the card was fitted to."""
import sys
import numpy as np
from scratch.fit.mosfet.bs170_pixels import ppm, runs
from scratch.fit.mosfet.spec_2n7000 import SPEC

d = sys.argv[1]
g = ppm(f"{d}/i-000.ppm")
x = lambda v: 46 + v * (410 - 46) / 5  # noqa: E731
cur = lambda y: (234 - y) / (234 - 8) * 2.0  # noqa: E731
ref = {vg: (np.array([p[0] for p in pts]), np.array([p[1] for p in pts])) for vg, pts in SPEC["output"]["curves"].items()}
for v in (0.5, 1.5, 2.5, 3.8):
    got = sorted(cur(y) for y in runs(g[:, int(round(x(v)))], [8, 64, 121, 178, 234]))
    want = sorted(float(np.interp(v, *ref[vg])) for vg in ref if ref[vg][0][-1] >= v - 0.3)
    print(f"Fig 1 at {v} V: onsemi", [round(a, 3) for a in got])
    print(f"            2N7000 fit pts", [round(a, 3) for a in want])
g = ppm(f"{d}/i-002.ppm")
vg = lambda xx: (xx - 45) / (421 - 45) * 10  # noqa: E731
yy = lambda a: 248 - a / 2.0 * (248 - 14)  # noqa: E731
tv, ti = np.array([p[0] for p in SPEC["transfer"]["points"]]), np.array([p[1] for p in SPEC["transfer"]["points"]])
for a in (0.3, 0.6, 1.0, 1.4, 1.8):
    xs = [vg(c) for c in runs(g[int(round(yy(a))), : g.shape[1] // 2], [45, 120, 195, 270, 345, 421])]
    xs = [v for v in xs if 1.5 < v < 10]
    mid = sorted(xs)[len(xs) // 2] if len(xs) == 3 else None
    print(f"Fig 5 at {a} A: onsemi {[round(v, 2) for v in xs]} 25 C {mid and round(mid, 3)}; 2N7000 fit pts {np.interp(a, ti, tv):.3f} V")
