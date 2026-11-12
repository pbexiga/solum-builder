import dataclasses, math, importlib.util
import numpy as np
spec = importlib.util.spec_from_file_location("fm", "scripts/fit_models.py"); fm = importlib.util.module_from_spec(spec); spec.loader.exec_module(fm)
start = fm.GummelPoon(is_=1.064e-13, nf=1.021, bf=152.7, ise=3.655e-14, ne=1.42, ikf=1.098, vaf=math.inf, nkf=1.0, rb=50.0)
pts = [(2e-4, 0.0399), (5e-4, 0.0386), (1e-3, 0.0382), (2e-3, 0.0375), (5e-3, 0.0382), (1e-2, 0.0404), (2e-2, 0.0505), (5e-2, 0.0782), (0.1, 0.1192)]
gain = [(2e-4, 139.2), (2e-3, 139.2), (2e-2, 139.2), (5e-2, 139.2), (0.1, 133.9)]
def made(x): return dataclasses.replace(start, br=10 ** x[0], rc=x[1], isc=10 ** x[2], nc=x[3], nr=start.nf)
def res(x):
    f = made(x)
    return [(f.vce_sat(i, i / 10) - v) / 2e-3 for i, v in pts] + [math.log(max(f.forward(i, 6.0)[1], 1e-3) / h) / 0.01 for i, h in gain]
for s0 in (-13.4, -16.0, -18.0, -11.0):
    for top in (-8.0, -10.0):
        x = fm.least_squares(res, [0.0, 1.0, min(s0, top), 1.5], [-2.0, 0.0, -20.0, 1.05], [2.0, 50.0, top, 4.0])
        r = res(np.array(x)); print(s0, top, [round(v, 3) for v in x], round(sum(v * v for v in r), 3), round(max(abs(v) for v in r[:len(pts)]) * 2, 2), "mV")
