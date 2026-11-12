"""Phase margin that gives the sheet's 10 % follower overshoot at the sheet's own load,
by bisection."""

import importlib.util
import sys

import numpy as np

from solum.sim.native import native_engine

sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("fo", ".claude/skills/fit-model/tools/fit_opamps.py")
fo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fo)

e = native_engine()


def vec(p, n):
    return np.array(p.vectors[n] if n in p.vectors else p.vectors[f"v({n})"]).real


def overshoot(pid, pm, vs, rl, cl):
    fit = fo.fm.OpAmpFit(**{**fo.PARTS[pid]["fit"], "phase_margin": pm})
    card = fo.fm.opamp_card(pid, fit)
    r = e.run(
        f"* t\n{card}V1 vp 0 {vs}\nV2 0 vn {vs}\nVin in 0 PULSE(-0.05 0.05 1u 1n 1n 20u 40u)\n"
        f"X1 in out vp vn out {pid}\nRL out 0 {rl}\nCL out 0 {cl}\n.tran 0.001u 4u\n.end\n"
    )
    p = r.plot("tran")
    t = vec(p, "time")
    v = vec(p, "out")
    final = v[t > 3.5e-6].mean()
    return 100 * (v.max() - final) / (final + 0.05)


for pid, vs, rl, cl in [("NE5532", 15, 600, 100e-12), ("CA3260", 7.5, 2e3, 25e-12)]:
    lo, hi = 50.0, 80.0
    for _ in range(14):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if overshoot(pid, mid, vs, rl, cl) > 10 else (lo, mid)
    pm = round((lo + hi) / 2, 1)
    print(
        pid,
        "PM",
        pm,
        "overshoot",
        round(overshoot(pid, pm, vs, rl, cl), 1),
        "unloaded",
        round(overshoot(pid, pm, vs, 1e9, 1e-15), 1),
    )
