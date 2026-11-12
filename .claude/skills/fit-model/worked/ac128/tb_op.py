"""Tone Bender MkII op point with the AC128 card: the transistors' terminals and currents."""
from pathlib import Path
from solum.circuit.io import load_circuit
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator
c = load_circuit(Path("library/starters/tone-bender-mk2.json"))
sim = Simulator(native_engine(), load_models([Path("library/models")]))
op = sim.op(c)
for q in ("Q1", "Q2", "Q3"):
    print(q, {pin: round(op.voltages[sim.resolve(c, f"{q}.{pin}")], 4) for pin in "CBE"})
print("R2.1", round(op.voltages[sim.resolve(c, "R2.1")], 3))
print({k: v for k, v in op.__dict__.items() if k != "voltages"} if hasattr(op, "__dict__") else "")
for p in c.parts:
    if p.ref in ("TR1", "TR2", "R1", "R2", "R3", "R4", "R5", "R6"): print(p.ref, getattr(p, "value", ""), getattr(p, "rotation", ""))
