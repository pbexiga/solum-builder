"""Smoke test of CD4049UB.lib as a Red Llama-style stage: 1M in->out feedback, 9 V, CL 100 pF,
driven through 100 nF + 100 kΩ. Prints the bias and the closed-loop gain across frequency."""
import numpy as np

from scratch.fit.cd4049.inv import ENGINE

net = """stage
.include /src/.claude/skills/fit-model/worked/cd4049/CD4049UB.lib
Vdd vdd 0 9
Vs a 0 dc 0 ac 1
C1 a b 100n
R2 b i 100k
R1 o i 1Meg
X1 i o vdd 0 CD4049UB_INV
CL o 0 100p
.ac dec 10 10 10Meg
.end
"""
pl = ENGINE.run(net).plot("ac").vectors
f, vo = np.asarray(pl["frequency"].real), np.abs(np.asarray(pl["o"]))
for fx in (100, 1e3, 1e4, 1e5, 1e6):
    print(f"{fx:>9.0f} Hz: gain {np.interp(fx, f, vo):.2f}")
op = ENGINE.run(net.replace(".ac dec 10 10 10Meg", ".op"))
print({k: float(np.asarray(v).real[0]) for k, v in op.plots[0].vectors.items() if k in ("o", "i")})
