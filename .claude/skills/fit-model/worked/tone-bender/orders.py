"""Tone Bender MkII and Fuzz Face against the guitar's volume: level, the 2nd harmonic and the
odd/high-order rest (3rd-8th, rms) at `out`, Strat, 200 Hz."""
import math
from pathlib import Path
from solum.circuit.io import load_circuit
from solum.circuit.schema import MeasuredBjt, Pickup
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator
L = Path("library"); sim = Simulator(native_engine(), load_models([L / "models"]))
strat = Pickup(r=6380.0, l=2.55, c=151e-12, kind="strat")
tb = load_circuit(L / "starters/tone-bender-mk2.json")
def meas(c, ref, **kw):
    m = next(p for p in c.parts if p.ref == ref).measured
    return c.with_part(ref, measured=MeasuredBjt(**{**m.model_dump(), **kw}))
ff = load_circuit(L / "starters/fuzz-face.json")
gff = next(p for p in ff.parts if p.type == "guitar").ref
V = {
    "TB stock, Fuzz min": (tb.with_part("VR2", rotation=0.0), "IN"),
    "TB stock, Fuzz full": (tb, "IN"),
    "TB 3:00 Q1 50uA, Fuzz min": (meas(tb.with_part("TR1", bias_target=None, rotation=0.85), "Q1", leakage=50e-6).with_part("VR2", rotation=0.0), "IN"),
    "TB 3:00 Q1 100uA, Fuzz min": (meas(tb.with_part("TR1", bias_target=None, rotation=0.85), "Q1", leakage=100e-6).with_part("VR2", rotation=0.0), "IN"),
    "TB 3:00 Q1 stock, Fuzz min": (tb.with_part("TR1", bias_target=None, rotation=0.85).with_part("VR2", rotation=0.0), "IN"),
    "TB 3:00 Q1 stock, Fuzz half": (tb.with_part("TR1", bias_target=None, rotation=0.85).with_part("VR2", rotation=0.5), "IN"),
    "Fuzz Face, Fuzz full": (ff, gff),
}
import sys
for name, (c, g) in ((k, V[k]) for k in (sys.argv[1:] or V)):
    c = sim.solve_bias(c).circuit
    for pick in (0.1, 0.3):
        row, ref = [], None
        for vol in (1.0, 0.6, 0.4, 0.2):
            cc = c.with_part(g, source="pickup", pickup=strat, rotation=vol)
            s = sim.tran(cc, ["out"], pick).stats[sim.resolve(cc, "out")]
            ref = ref or s.amplitude
            h = {k: 10 ** (v / 20) for k, v in s.harmonics_db.items()}
            rest = math.sqrt(sum(h[k] ** 2 for k in range(3, 9) if k in h))
            row.append(f"v{vol*10:.0f} {20*math.log10(s.amplitude/ref):+5.1f}dB h2 {h.get(2,0)*100:3.0f}% h3+ {rest*100:3.0f}%")
        print(f"{name:26} pick {pick} | " + " | ".join(row), flush=True)
