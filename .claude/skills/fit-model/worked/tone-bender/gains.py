"""Tone Bender MkII: stage gains at 1 kHz and DC, stock and with one suspect changed."""
import math
from pathlib import Path
import numpy as np
from solum.circuit.io import load_circuit
from solum.circuit.schema import MeasuredBjt
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator
L = Path("library"); sim = Simulator(native_engine(), load_models([L / "models"]))
base = load_circuit(L / "starters/tone-bender-mk2.json")

def notarget(c, rot):
    return c.with_part("TR1", bias_target=None, rotation=rot)

def meas(c, ref, **kw):
    m = next(p for p in c.parts if p.ref == ref).measured
    return c.with_part(ref, measured=MeasuredBjt(**{**m.model_dump(), **kw}))

VARIANTS = {
    "stock (TR1 solved)": base,
    "TR1 at 3:00 (0.85)": notarget(base, 0.85),
    "Q1 leakage 50uA": meas(base, "Q1", leakage=50e-6),
    "Q1 leakage 300uA": meas(base, "Q1", leakage=300e-6),
    "R1 10k": base.with_part("R1", value="10k"),
    "Q3 leakage 50uA": meas(base, "Q3", leakage=50e-6),
    "Q3 hFE 95": meas(base, "Q3", hfe=95.0),
}
NODES = ("Q1.C", "Q2.C", "Q3.C", "out")
for name, c in VARIANTS.items():
    for fuzz in (1.0, 0.0):
        cc = c.with_part("VR2", rotation=fuzz)
        b = sim.solve_bias(cc).circuit if any(getattr(p, "bias_target", None) for p in cc.parts) else cc
        op = sim.op(b)
        r = sim.ac(b)
        g = {}
        for n in NODES:
            h = r.responses[sim.resolve(b, n)]
            g[n] = 20 * math.log10(abs(np.interp(3.0, np.log10(r.freq), np.abs(h))))
        v = op.voltages
        ic = op.currents
        print(f"{name:22} fuzz {fuzz:.0f} | dB@1k " + " ".join(f"{n} {g[n]:5.1f}" for n in NODES)
              + f" | Q1.C {v['Q1.C']:.2f} Q2.C {v['Q2.C']:.3f} Q3.C {v['Q3.C']:.2f} Ic1 {-ic['Q1.ic']*1e6:.0f}uA Ic3 {-ic['Q3.ic']*1e6:.0f}uA", flush=True)
