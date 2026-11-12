"""Spec list for `add_model.py` that re-measures any model already in the library, keeping
its record: `add_model.py .claude/skills/fit-model/tools/remeasure.py ID [ID...]`."""

from pathlib import Path

SPECS = [
    {"id": p.stem, "type": p.parent.name, "update": True, "remeasure": True}
    for p in sorted(Path("library/models").glob("*/*.json"))
]
