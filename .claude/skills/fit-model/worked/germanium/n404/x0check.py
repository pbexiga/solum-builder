import sys; sys.path.insert(0, ".claude/skills/fit-model/worked/germanium"); sys.path.insert(0, ".claude/skills/fit-model/worked/germanium/n404")
import numpy as np, alloy as a
from fit import SPEC
free = [n for n in a.NAMES if n not in (SPEC.fixed or {})]
f, ks = a.made(SPEC, np.array([SPEC.x0[n] for n in free] + [0.0, 0.0]))
print("\n".join(a.report(f, SPEC, ks)[:8]))
