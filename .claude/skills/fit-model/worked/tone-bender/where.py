from pathlib import Path
from solum.circuit.io import load_circuit
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator
L = Path("library"); sim = Simulator(native_engine(), load_models([L / "models"]))
c0 = sim.solve_bias(load_circuit(L / "starters/tone-bender-mk2.json")).circuit
N = ["Q1.C", "Q2.B", "Q2.C", "Q3.E", "Q3.C", "out"]
for fuzz in (0.0, 1.0):
    c = c0.with_part("VR2", rotation=fuzz)
    for lv in (0.0001, 0.0003):
        s = sim.tran(c, N, lv).stats
        print(f"fuzz {fuzz:.0f} in {lv*1e3:.1f} mV | " + " | ".join(
            f"{n} {s[sim.resolve(c,n)].amplitude*1e3:7.2f}mV {s[sim.resolve(c,n)].clipping.thd*100:3.0f}% h2 {s[sim.resolve(c,n)].harmonics_db.get(2,-99):4.0f} h3 {s[sim.resolve(c,n)].harmonics_db.get(3,-99):4.0f}" for n in N), flush=True)
