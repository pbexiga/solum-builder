"""Tone Bender MkII clean-up against the Fuzz pot (VR2) and pick level: Strat through the 250K
volume pot, measured hFE and leakage kept. Output amplitude and THD at `out`, 200 Hz.
run.sh tb_cleanup.py > out_tb_cleanup.txt"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from compare import sim, unbiased  # noqa: E402
from solum.circuit.io import load_circuit  # noqa: E402
from solum.circuit.schema import Pickup  # noqa: E402

base = load_circuit(Path("library/starters/tone-bender-mk2.json"))
c, note = unbiased(base)
g = next(p for p in c.parts if p.type == "guitar").ref
FUZZ, LEVELS_V, VOLS = (1.0, 0.0), (0.02,), (1.0, 0.6, 0.3)
strat = Pickup(r=6380.0, l=2.55, c=151e-12, kind="strat")
for fuzz in (FUZZ):
    for level in LEVELS_V:
        for vol in VOLS:
            cc = c.with_part("VR2", rotation=fuzz).with_part(g, source="pickup", pickup=strat, rotation=vol)
            s = sim.tran(cc, ["out", "Q1.C", "Q2.C"], level).stats
            o, q1, q2 = (s[sim.resolve(cc, n)] for n in ("out", "Q1.C", "Q2.C"))
            print(json.dumps({"fuzz": fuzz, "pick_V": level, "volume": vol * 10, "out_V": round(o.amplitude, 4),
                              "thd": round(o.clipping.thd, 3), "q1c_thd": round(q1.clipping.thd, 3),
                              "q2c_thd": round(q2.clipping.thd, 3)}), flush=True)
