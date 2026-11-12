"""Is the Tone Bender starter oscillating? Ideal source at tiny levels: output amplitude, its
strongest frequency, and Q2's collector waveform range."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from compare import sim, unbiased  # noqa: E402
from solum.circuit.io import load_circuit  # noqa: E402

base = load_circuit(Path("library/starters/tone-bender-mk2.json"))
c, note = unbiased(base)
print("bias note:", note)
for level in (1e-4, 1e-3, 0.01, 0.1):
    tr = sim.tran(c, ["out", "Q2.C", "Q1.C"], level)
    t = tr.time
    for n in ("out", "Q2.C", "Q1.C"):
        w = tr.waves[sim.resolve(c, n)]
        m = t > t[-1] - 0.05
        tt, ww = t[m], w[m] - w[m].mean()
        ts = np.linspace(tt[0], tt[-1], 8192)
        ws = np.interp(ts, tt, ww)
        f = np.fft.rfftfreq(len(ws), ts[1] - ts[0])
        a = np.abs(np.fft.rfft(ws))
        k = int(np.argmax(a[1:]) + 1)
        print(f"level {level:g} V {n:5}: pk-pk {w[m].max() - w[m].min():.4f} V, mean {w[m].mean():.3f} V, strongest {f[k]:.0f} Hz, settled {tr.settled}")
