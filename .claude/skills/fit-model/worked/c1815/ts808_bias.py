"""TS808 Q1/Q3 operating points with the 2SC1815 against the 2N5089, and at GR/BL gains."""
from pathlib import Path
from solum.circuit.io import load_circuit
from solum.circuit.schema import MeasuredBjt as Measured
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator

sim = Simulator(native_engine(), load_models([Path("library/models")]))
base = load_circuit(Path("library/starters/ts808.json"))
for label, model, hfe in (("2N5089", "2N5089", None), ("2SC1815 (card, 139)", "2SC1815", None),
                          ("2SC1815 GR 280", "2SC1815", 280.0), ("2SC1815 BL 500", "2SC1815", 500.0)):
    c = base
    for q in ("Q1", "Q3"):
        c = c.with_part(q, model=model, measured=Measured(hfe=hfe) if hfe else None)
    op = sim.op(c)
    v = lambda n: op.voltages[sim.resolve(c, n)]  # noqa: E731
    print(f"{label:22} Vref {v('R2.1') if False else '':}Q1 B {v('Q1.B'):.3f} E {v('Q1.E'):.3f} | Q3 B {v('Q3.B'):.3f} E {v('Q3.E'):.3f}")
