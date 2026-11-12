"""Small-signal follower overshoot at each sheet's own test conditions."""

from pathlib import Path

import numpy as np

from solum.sim.native import native_engine

e = native_engine()


def vec(p, n):
    return np.array(p.vectors[n] if n in p.vectors else p.vectors[f"v({n})"]).real


for pid, vs, rl, cl in [
    ("NE5532", 15, 600, 100e-12),
    ("CA3260", 7.5, 2e3, 25e-12),
    ("CA3260", 7.5, 1e9, 1e-15),
    ("LM833", 15, 2e3, 1e-15),
    ("OPA2134", 15, 2e3, 1e-15),
    ("TLC2262", 5, 50e3, 1e-15),
    ("NE5532", 15, 1e9, 1e-15),
]:
    card = Path(f"library/models/opamp/{pid}.lib").read_text()
    r = e.run(
        f"* t\n{card}V1 vp 0 {vs}\nV2 0 vn {vs}\nVin in 0 PULSE(-0.05 0.05 1u 1n 1n 20u 40u)\n"
        f"X1 in out vp vn out {pid}\nRL out 0 {rl}\nCL out 0 {cl}\n.tran 0.001u 4u\n.end\n"
    )
    p = r.plot("tran")
    t = vec(p, "time")
    v = vec(p, "out")
    final = v[(t > 3.5e-6)].mean()
    print(
        f"{pid:8} RL {rl:g} CL {cl:g}: overshoot {100 * (v.max() - final) / (final + 0.05):.1f} %"
    )
