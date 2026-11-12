"""Per-point misses of the 2SC1815 fit (the card's GummelPoon against the fitted points)."""
import importlib.util
import json
import sys
sys.path.insert(0, ".claude/skills/fit-model/tools")
spec = importlib.util.spec_from_file_location("s", ".claude/skills/fit-model/tools/specs/toshiba_2sc1815.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
from bjt_record import fm, grid, interp  # noqa: E402
d = s.PARTS["2SC1815"]
rec = json.loads(open("library/models/bjt/2SC1815.json").read())
h = [(i / 1e3, v) for i, v in interp(d["hfe"][2], grid(d["hfe"][2]))]
b = [(i / 1e3, v) for i, v in interp(d["vbe"][2], grid(d["vbe"][2]))]
f = fm.fit_bjt_forward(h, b, 6.0, float("inf"), rb=50.0)
for i, v in h:
    print(f"hfe {i*1e3:8.3f} mA sheet {v:7.1f} fit {f.forward(i, 6.0)[1]:7.1f}")
for i, v in b:
    print(f"vbe {i*1e3:8.3f} mA sheet {v:.4f} fit {f.forward(i, 6.0)[0]:.4f}")
print(f)
