"""Small-signal gain at the output (1 V at the guitar input, its pickup and volume as the starter
has them) at 100 Hz, 1 kHz, 5 kHz and 20 kHz for each starter variant of compare.py: where the
junction capacitances (AC128 Cb'c 100 pF; OC44 10.5 pF, OC71 40 pF, OC75 50 pF max) show.
run.sh compare_ac.py > out_compare_ac.txt"""
import math
import sys

import numpy as np

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from compare import STARTERS, sim, unbiased, variant  # noqa: E402
from solum.circuit.io import load_circuit  # noqa: E402
from pathlib import Path  # noqa: E402

FREQS = (100.0, 1e3, 5e3, 20e3)
print("| starter | hFE/leakage | variant | " + " | ".join(f"{f:g} Hz dB" for f in FREQS) + " | valid |")
print("|---|---|---|" + "---|" * (len(FREQS) + 1))
for stem, (qs, variants) in ((s, STARTERS[s]) for s in (sys.argv[1:] or STARTERS)):
    base = load_circuit(Path(f"library/starters/{stem}.json"))
    for own in (False, True):
        for label, swap in variants:
            c, note = unbiased(variant(base, swap, own))
            r = sim.ac(c)
            h = r.responses[sim.resolve(c, "out")]
            db = [20 * math.log10(abs(np.interp(math.log10(f), np.log10(r.freq), np.abs(h)))) for f in FREQS]
            print(f"| {stem} | {'card' if own else 'starter'} | {label} | " + " | ".join(f"{d:.2f}" for d in db) + f" | {r.valid}{' (trimmer at its rotation: ' + note + ')' if note else ''} |", flush=True)
