"""Measure each MOSFET record's validation values through the pipeline and write them in."""
import json
from pathlib import Path

from solum.models import load_models
from solum.sim.native import NativeNgspice
from tests.sim.model_checks import measure

engine = NativeNgspice("/usr/lib/x86_64-linux-gnu/libngspice.so.0")
lib = load_models([Path("library/models")])
for path in sorted(Path("library/models/mosfet").glob("*.json")):
    data = json.loads(path.read_text())
    model = lib.get(data["id"])
    for rec in data["validation"]:
        rec["simulated"] = round(measure(engine, lib, model, rec["quantity"], rec["conditions"]), 6)
        print(data["id"], rec["quantity"], rec["conditions"], rec["simulated"], rec["datasheet"].get("typ"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
