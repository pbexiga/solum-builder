"""Rangemaster's two AC checks with the AC128 card as fitted, and with its speed (CJC, TF) removed."""
import re, shutil, tempfile
from pathlib import Path
from solum.circuit.io import load_circuit
from solum.models import load_models
from solum.sim.native import native_engine
from solum.simulate import Simulator
from tests.acceptance.expected import load_expected, run_check
exp = load_expected(Path("tests/fixtures/acceptance/dallas-rangemaster.expected.yaml"))
c = load_circuit(Path("library/starters/dallas-rangemaster.json"))
tmp = Path(tempfile.mkdtemp()); shutil.copytree("library/models", tmp / "models")
lib = tmp / "models/bjt/AC128.lib"
for label, sub in (("as fitted", None), ("no CJC, TF", r"cjc=\S+ |tf=\S+ "), ("no TF", r"tf=\S+ "), ("no CJC", r"cjc=\S+ ")):
    if sub: lib.write_text(re.sub(sub, "", Path("library/models/bjt/AC128.lib").read_text()))
    sim = Simulator(native_engine(), load_models([tmp / "models"]))
    for ch in exp.checks:
        if ch.id in ("input-high-pass", "gain-volume-max"):
            print(label, ch.id, [o.detail for o in run_check(sim, c, ch)])
