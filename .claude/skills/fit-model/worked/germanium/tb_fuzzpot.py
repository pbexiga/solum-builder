"""What the Tone Bender's Fuzz pot (VR2) is wired to, and the small-signal gain at 1 kHz against
its rotation (measured kept, TR1 solved)."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from compare import sim, unbiased  # noqa: E402
from solum.circuit.io import load_circuit  # noqa: E402

base = load_circuit(Path("library/starters/tone-bender-mk2.json"))
for p in base.parts:
    if p.ref in ("VR2", "Q1", "Q2", "Q3", "TR1", "TR2", "VR1"):
        print(p.ref, {k: v for k, v in p.model_dump().items() if k in ("value", "rotation", "taper", "model")})
from solum.circuit.connectivity import connect  # noqa: E402

nets = connect(base)
for ref in ("VR2", "Q1", "Q2", "Q3", "TR2"):
    for (r, pin), net in sorted(nets.by_pin.items()):
        if r == ref:
            print(f"{ref}.{pin} -> {net}: " + ", ".join(f"{a}.{b}" for a, b in nets.members[net] if a != ref))
c0, note = unbiased(base)
print("bias", note)
for rot in (1.0, 0.8, 0.5, 0.2, 0.05, 0.0):
    c = c0.with_part("VR2", rotation=rot)
    c, note = unbiased(c)
    r = sim.ac(c)
    h = r.responses[sim.resolve(c, "out")]
    db = 20 * math.log10(abs(np.interp(3.0, np.log10(r.freq), np.abs(h))))
    op = sim.op(c)
    print(f"VR2 rotation {rot:.2f}: gain at 1 kHz {db:.1f} dB, Q2.C {op.voltages[sim.resolve(c, 'Q2.C')]:.3f} V, TR1 {(op.bias or {}).get('TR1')}, {note[:60]}")
