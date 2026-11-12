"""How the VCE(sat) fit and ICBO move if ISC is capped (the D-163 fit puts it at its 1e-8 bound)."""
import dataclasses
import importlib.util
import math
import sys
sys.path.insert(0, ".claude/skills/fit-model/tools")
spec = importlib.util.spec_from_file_location("s", ".claude/skills/fit-model/tools/specs/toshiba_2sc1815.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
from bjt_record import fm, grid, interp  # noqa: E402
d = s.PARTS["2SC1815"]
h = [(i / 1e3, v) for i, v in interp(d["hfe"][2], grid(d["hfe"][2]))]
b = [(i / 1e3, v) for i, v in interp(d["vbe"][2], grid(d["vbe"][2]))]
sat = [(i / 1e3, v) for i, v in interp(d["vcs"][2], grid(d["vcs"][2]))]
f0 = fm.fit_bjt_forward(h, b, 6.0, math.inf, rb=50.0)
for top in (-8.0, -9.0, -10.0, -11.0, -12.0):
    def made(x, f0=f0):
        return dataclasses.replace(f0, br=10 ** x[0], rc=x[1], isc=10 ** x[2], nc=x[3], nr=f0.nf)
    def res(x):
        f = made(x)
        return [(f.vce_sat(i, i / 10) - v) / 2e-3 for i, v in sat] + [math.log(max(f.forward(i, 6.0)[1], 1e-3) / hh) / 0.01 for i, hh in h]
    x = fm.least_squares(res, [0.0, 1.0, min(math.log10(f0.ise), top - 1e-6), 1.5], [-2.0, 0.0, -20.0, 1.05], [2.0, 50.0, top, 4.0])
    f = made(x)
    worst = max(abs(f.vce_sat(i, i / 10) - v) for i, v in sat)
    lows = [(round(i * 1e3, 2), round(v * 1e3, 1), round(f.vce_sat(i, i / 10) * 1e3, 1)) for i, v in sat if i <= 3e-3]
    print(f"isc<=1e{top:.0f}: isc={f.isc:.3g} nc={f.nc:.3g} br={f.br:.3g} rc={f.rc:.3g} worst {worst*1e3:.1f} mV icbo(9V) {f.icbo(9.0)*1e9:.3g} nA  low-I [mA, sheet mV, fit mV] {lows}")
