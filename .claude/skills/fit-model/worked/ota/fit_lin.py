"""Fit the linearising diodes' series resistance to LM13700 Fig 13 ("using diodes").

With ideal junctions the diodes cancel the pair's tanh exactly (TI 7.3.2, eq. 7), and the
model gives ~0.0003 % at half scale where Fig 13 shows ~0.07 %. The real chip's residue is
the junctions' ohmic resistance not matching; one RS on the diodes stands for it.
Test (the figure's own conditions and formula): +-15 V, Iabc 1 mA, RL 10 kOhm; diodes
biased by an ideal 1 mA (TI 8.3.1 recommends 1 mA; the figure doesn't say), the signal an
ideal current into the + input, 0.5 mA sunk from it, the - input held at 0 V.
x = 2 * VT ln((Iabc+Ipk)/(Iabc-Ipk)) in mVpp, THD of the output."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from check_ota import FIG13_DI, OPTS, VT27, fig_interp, thd  # noqa: E402

BASE = sim.CARD["LM13700"]


def point(rs, a):
    sim.CARD["LM13700"] = BASE.replace(".model DLIN D(", f".model DLIN D(RS={rs} ")
    r = sim.run("V1 vp 0 15\nV2 vn 0 -15\nIb 0 ib 1m\nRL out 0 10k\nVbi bi 0 0\nId 0 db 1m\n"
                f"Is 0 inp SIN(0 {a} 1k)\nIsink inp 0 0.5m\nVfix inn 0 0\n"
                "X1 inp inn out ib db bi bo vp vn LM13700_OTA\n.tran 0.5u 6m 0 0.5u", "LM13700", "tran", OPTS)
    d, fund = thd(r["time"].real, sim.v(r, "out"), 1e3)
    m = min(fund / 10e3 / 1e-3, 0.999999)
    return 2 * VT27 * math.log((1 + m) / (1 - m)) * 1e3, d


AMPS = [150e-6, 250e-6, 330e-6, 400e-6, 440e-6]


def err(rs, show=False):
    e = []
    for a in AMPS:
        x, d = point(rs, a)
        fd = fig_interp(FIG13_DI, x)
        if show:
            print(f"   RS {rs:.3f}: x {x:.1f} mVpp THD {d:.4g} % (figure {fd if fd is None else round(fd, 4)})")
        if fd is not None:
            e.append(math.log10(d / fd) ** 2)
    return math.sqrt(np.mean(e))


if __name__ == "__main__":
    best = min((err(r), r) for r in np.arange(0.2, 3.01, 0.2))
    lo, hi = best[1] - 0.2, best[1] + 0.2
    for _ in range(12):  # golden-section on the bracket
        m1, m2 = lo + 0.382 * (hi - lo), lo + 0.618 * (hi - lo)
        if err(m1) < err(m2):
            hi = m2
        else:
            lo = m1
    rs = (lo + hi) / 2
    print(f"best RS {rs:.4f} ohm, rms log10 error {err(rs, show=True):.3f}")
