from pathlib import Path
from solum.circuit.io import load_circuit
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator
sim = Simulator(native_engine(), load_models([Path("library/models")]))
def show(stem, qs, **sets):
    c = load_circuit(Path(f"library/starters/{stem}.json"))
    for ref, kw in sets.items(): c = c.with_part(ref, **kw)
    op = sim.op(c)
    out = {q: {pin: round(op.voltages[sim.resolve(c, f"{q}.{pin}")], 4) for pin in "CBE"} for q in qs}
    print(stem, sets or "", out, {k: f"{v*1e6:.1f}uA" for k, v in op.currents.items() if k.split(".")[0] in qs})
show("tone-bender-mk2", ["Q1"])
for lk in ():
    show("tone-bender-mk2", ["Q1"], Q1={"measured": {"hfe": 65.0, "leakage": lk}})
show("fuzz-face", ["Q1", "Q2"])
show("fuzz-face", ["Q1", "Q2"], Q1={"measured": {"hfe": 85.0, "leakage": 2e-4}}, Q2={"measured": {"hfe": 120.0, "leakage": 2e-4}})
show("dallas-rangemaster", ["Q1"])
