"""Rewrite the v11 netlist fixtures of the AC128 circuits from today's netlist (D-170)."""
from pathlib import Path
from solum.circuit.io import load_circuit
from solum.models import load_models
from solum.netlist import Ac, Op, generate_netlist
from solum.models import ModelLibrary
models = load_models([Path("library/models")])
for stem in ("fuzz-face", "dallas-rangemaster", "tone-bender-mk2", "tone-bender-mk2-mode"):
    c = load_circuit(Path(f"library/starters/{stem}.json"))
    for name, a in (("op", Op()), ("ac", Ac())):
        Path(f"tests/fixtures/netlists/v11/{stem}-{name}.cir").write_text(generate_netlist(c, models, a).text)
