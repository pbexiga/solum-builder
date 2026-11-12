import importlib.util, sys
sys.path.insert(0, ".claude/skills/fit-model/tools")
spec = importlib.util.spec_from_file_location("s", ".claude/skills/fit-model/tools/specs/toshiba_2sc1815.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
from bjt_record import grid, interp
d = s.PARTS["2SC1815"]
print("sat", [(round(i / 1e3, 6), round(v, 4)) for i, v in interp(d["vcs"][2], grid(d["vcs"][2]))])
print("hfe", [(round(i / 1e3, 6), round(v, 1)) for i, v in interp(d["hfe"][2], grid(d["hfe"][2]))])
