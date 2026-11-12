"""Follower step test for our op-amp models: slew rate, overshoot (small step), supply current."""

from pathlib import Path

import numpy as np

from solum.sim.native import native_engine

e = native_engine()


def vec(p, n):
    return np.array(p.vectors[n] if n in p.vectors else p.vectors[f"v({n})"]).real


for pid, vs, rl in [
    ("NE5532", 15, 2e3),
    ("LM833", 15, 2e3),
    ("OPA2134", 15, 2e3),
    ("CA3260", 7.5, 2e3),
]:
    card = Path(f"library/models/opamp/{pid}.lib").read_text()
    out = []
    for amp in (10.0 if vs > 10 else 5.0, 0.05):
        r = e.run(
            f"* t\n{card}V1 vp 0 {vs}\nV2 0 vn {vs}\nVin in 0 PULSE({-amp} {amp} 2u 1n 1n 20u "
            "40u)\n"
            f"X1 in out vp vn out {pid}\nRL out 0 {rl}\nCL out 0 100p\n.tran 0.002u 12u\n.end\n"
        )
        p = r.plot("tran")
        t = vec(p, "time")
        v = vec(p, "out")
        if amp > 1:
            k = (t > 2.05e-6) & (v > -0.6 * amp) & (v < 0.6 * amp)
            out.append(f"slew {np.polyfit(t[k], v[k], 1)[0] / 1e6:.2f} V/us")
        else:
            out.append(f"overshoot {100 * (v.max() - amp) / (2 * amp):.1f} %")
    r = e.run(f"* t\n{card}V1 vp 0 {vs}\nV2 0 vn {vs}\nX1 0 out vp vn out {pid}\n.op\n.end\n")
    iq = abs(r.plot("op").vectors["v1#branch"][0].real)
    print(pid, *out, f"Iq per amp {iq * 1e3:.2f} mA")
