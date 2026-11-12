"""How much the guitar's volume cleans up each germanium starter, on the AC128 against the pedal's
own part (the starter's measured hFE and leakage kept, D-130). The guitar is a real pickup
(library/guides/pickups.yaml: Strat single coil, PAF humbucker) through its 250K audio-taper
volume pot, so the pot's resistance meets the fuzz's low input impedance as on a real rig.
Medium pick (0.3 V at the pickup) at the app's 200 Hz tone; at `out`: the output's amplitude
(V, and dB against the volume-full one) and THD. (The stats' gain_db is against the signal after
the pot, so it climbs as the volume goes down; not used.)
run.sh volume.py > out_volume.txt"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from compare import sim, unbiased  # noqa: E402
from solum.circuit.io import load_circuit  # noqa: E402
from solum.circuit.schema import Pickup  # noqa: E402

PICKUPS = {"Strat": Pickup(r=6380.0, l=2.55, c=151e-12, kind="strat"),
           "PAF": Pickup(r=8090.0, l=5.29, c=57e-12, kind="paf")}
ROTATIONS = (1.0, 0.8, 0.6, 0.4)
RUNS = {
    "fuzz-face": [("AC128 (the starter's)", {})],
    "tone-bender-mk2": [("OC75 (the starter's)", {}), ("AC128", {q: "AC128" for q in ("Q1", "Q2", "Q3")}),
                        ("OC81D (estimated)", {q: "OC81D" for q in ("Q1", "Q2", "Q3")})],
    "dallas-rangemaster": [("OC44 (the starter's)", {}), ("AC128", {"Q1": "AC128"})],
}

out: dict[str, list[dict]] = {}
for stem, variants in RUNS.items():
    base = load_circuit(Path(f"library/starters/{stem}.json"))
    guitar = next(p for p in base.parts if p.type == "guitar")
    for label, swap in variants:
        c = base
        for ref, model in swap.items():
            c = c.with_part(ref, model=model)
        c, note = unbiased(c)
        for pu_name, pu in PICKUPS.items():
            for rot in ROTATIONS:
                cc = c.with_part(guitar.ref, source="pickup", pickup=pu, rotation=rot)
                tr = sim.tran(cc, ["out"], "med")
                s = tr.stats[sim.resolve(cc, "out")]
                row = {"starter": stem, "variant": label, "pickup": pu_name, "volume": rot * 10,
                       "out_v": round(s.amplitude, 4), "thd": round(s.clipping.thd, 3), "note": note}
                out.setdefault(stem, []).append(row)
                print(json.dumps(row), flush=True)
Path(".claude/skills/fit-model/worked/germanium/data/volume.json").write_text(json.dumps(out, indent=1))
