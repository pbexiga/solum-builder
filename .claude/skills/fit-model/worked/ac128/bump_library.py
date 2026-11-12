"""Bump library circuits/blocks to the current schema with the real migrations; report diffs."""
import json, pathlib
from solum.circuit.migrations import migrate
for p in sorted(pathlib.Path("library").glob("*/*.json")):
    if p.parent.name == "models": continue
    text = p.read_text(); d = json.loads(text)
    if "schema" not in d: continue
    out = json.dumps(migrate(d), indent=2, ensure_ascii=False) + "\n"
    if json.dumps(d, indent=2, ensure_ascii=False) + "\n" != text:
        print("FORMAT DIFFERS", p); continue
    if out != text:
        p.write_text(out)
