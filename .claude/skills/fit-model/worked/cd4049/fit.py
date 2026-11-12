"""Fit one CD4049UB inverter (inv.py's subcircuit) to TI's SCHS046L, through ngspice.

Stage 1, both sides' DC (VTO, KP, THETA, MTRIODE, LAMBDA, RS, RD for N and for P) together,
from a start read off Figure 5-7 (below), to:
 - Figure 5-3's typical sink curves at VCC 5/10/15 V and Figure 5-5's typical source curves
   (log error per point);
 - the table's typical IOL (weight 3: the table wins where both speak, D-163/D-175);
 - the 5 V sink curve's drawn rise past its knee (3.02 -> 4.97 V), for LAMBDA_n;
 - Figure 5-7, taken at 25 °C between its -55 °C and 125 °C curves: the switching point
   (VO = VI) at 5 and 10 V, VI at VO = 90 % and 10 % of VCC, and the 10 V curve's average slope
   from VO 70 % to 30 % of VCC (sets LAMBDA_p, so the gain).
 Not the table's typical IOH: they sit on the Figure 5-6 MINIMUM curve and contradict
 Figure 5-5 (see NOTES.md); fitted to them the P side lands on LAMBDA = 1, VTO = 3.8 V.
Stage 2, capacitances (CGS, CGD shared by both sides, CJO), DC held: the table's typical CIN
(15 pF, weight 3) and Figure 5-9's power per inverter at 100 kHz (CL 50 pF at 5/10/15 V,
15 pF at 10 V), simulated with the AC table's 20 ns input edges (Figure 5-9 states none).
KSUBTHRES is VDMOS's default (0.1 V): the sheet draws nothing below 1 mA.

python .claude/skills/fit-model/worked/cd4049/fit.py -> prints each stage, writes params.json (then write_lib.py).
"""

import json
import math

import numpy as np

from scratch.fit.cd4049 import inv, sheet
from scripts.fit_models import least_squares

W_TABLE = 3.0
W_VTC = 1.0  # per 50 mV
W_SLOPE = 1.0  # per 20 % of the drawn rise
LOG = {"ksubthres", "kp", "theta", "mtriode", "lambda", "rs", "rd", "cgs", "cgd", "cjo"}
BOUNDS = {"vto": (0.3, 4.0), "kp": (1e-5, 10.0), "theta": (1e-4, 10.0), "mtriode": (0.2, 20.0),
          "lambda": (1e-5, 1.0), "rs": (0.01, 1e4), "rd": (0.01, 1e4), "cgs": (1e-14, 1e-9),
          "cgd": (1e-14, 1e-9), "cjo": (1e-14, 1e-9), "ksubthres": (1e-3, 1.0)}
# Figure 5-7's crossings of VO = VI (digitise.crossing on sheet.VTC_PATHS): (-55 °C, 125 °C).
VTC_X = {5: (2.714, 2.358), 10: (4.385, 4.090)}
VTC_25 = {v: lo + (hi - lo) * 80 / 180 for v, (lo, hi) in VTC_X.items()}
# The VTC's average slope between VO = 70 % and 30 % of VCC, as drawn (digitise.vi_at on the
# same paths): 10 V: -55 °C 30.9, 125 °C 24.5 -> 28.1 at 25 °C. 5 V is not a target: its
# 125 °C curve is drawn vertical there (383), the -55 °C one 18.1.
# Shoulders of the same 25 °C VTC, (VI, VO) at VO = 90 % and 10 % of VCC (digitise.vtc25):
# where the output leaves each rail is what sets the two thresholds.
VTC_SHOULDERS = {5: [(2.204, 4.5), (2.82, 0.5)], 10: [(3.599, 9.0), (4.624, 1.0)]}
VTC_SLOPE_25 = {10: 30.9 + (24.5 - 30.9) * 80 / 180}
# Figure 5-9 (p. 13), read at 100 kHz off its straight lines (digitise59 in NOTES.md): µW.
FIG59 = [(5, 50e-12, 160.0), (10, 50e-12, 919.0), (15, 50e-12, 2786.0), (10, 15e-12, 310.0)]

# Start: thresholds where Figure 5-7's 25 °C VTC leaves the rails at VCC 5 V (VO 4.9 V at VI
# 1.71 V: VTO_n about 1.7; VO 0.25 V at VI 3.10 V: VTO_p about 5 - 3.1 = 1.9), KP from the
# saturated currents at VCC 5 V (Figure 5-3 19.7 mA, Figure 5-5 8.2 mA) as KP/2 (5 - VTO)^2.
# Started from the N curves alone, VTO_n runs to 2.7 V and VTO_n + VTO_p passes 5 V (the 5 V
# switch then happens below both thresholds), so the fit starts from the VTC instead.
START = {"vton": 1.7, "kpn": 3.6e-3, "thetan": 0.05, "mtrioden": 1.4, "lambdan": 0.01, "rsn": 1.0, "rdn": 1.0,
         "vtop": 1.9, "kpp": 1.7e-3, "thetap": 0.05, "mtriodep": 1.0, "lambdap": 0.03, "rsp": 30.0, "rdp": 1.0,
         "ksubthresn": 0.1, "ksubthresp": 0.1, "cgs": 5e-12, "cgd": 3e-12, "cjo": 5e-12}


def _base(k: str) -> str:
    return k[:-1] if k[:-1] in BOUNDS else k


def to_x(p, names):
    return [math.log(p[k]) if _base(k) in LOG else p[k] for k in names]


def to_p(x, names):
    return {k: float(math.exp(v) if _base(k) in LOG else v) for k, v in zip(names, x)}


def run(names, base, res_fn, steps=60):
    x0 = to_x(base, names)
    n = len(res_fn(base))

    def r(x):
        try:
            return res_fn({**base, **to_p(x, names)})
        except Exception:  # noqa: BLE001  (a card ngspice can't solve: push away from it)
            return [10.0] * n

    lo = [math.log(BOUNDS[_base(k)][0]) if _base(k) in LOG else BOUNDS[_base(k)][0] for k in names]
    hi = [math.log(BOUNDS[_base(k)][1]) if _base(k) in LOG else BOUNDS[_base(k)][1] for k in names]
    x = least_squares(r, x0, lo, hi, steps=steps)
    p = {**base, **to_p(x, names)}
    e = np.abs(r(x))
    print(f"  worst {e.max():.3f} rms {np.sqrt(np.mean(e**2)):.3f}", {k: float(f"{p[k]:.4g}") for k in names})
    return p


def rise(pts, a, b):
    """(I(b) - I(a)) / I(b) between two point indices: the drawn rise past the knee."""
    return (pts[b][1] - pts[a][1]) / pts[b][1]


def res_n(p):
    out = []
    for vcc, pts in sheet.SINK_TYP.items():
        v, i = inv.sink(p, vcc, 5.0)
        out += [math.log(max(inv.at(v, i, x), 1e-9) / (y * 1e-3)) for x, y in pts]
        if vcc == 5:
            want = rise(pts, 7, 9)
            got = 1 - inv.at(v, i, pts[7][0]) / inv.at(v, i, pts[9][0])
            out.append(W_SLOPE * (got - want) / (0.2 * want))
    for vcc, vout, _mn, typ in sheet.IOL:
        v, i = inv.sink(p, vcc, 2.0)
        out.append(W_TABLE * math.log(max(inv.at(v, i, vout), 1e-9) / (typ * 1e-3)))
    return out


def res_p(p):
    out = []
    for vcc, pts in sheet.SOURCE_TYP.items():
        v, i = inv.source(p, vcc, 8.0)
        out += [math.log(max(inv.at(v, i, x), 1e-9) / (y * 1e-3)) for x, y in pts]
    for vcc, target in VTC_25.items():
        vi, vo = inv.vtc(p, vcc, 0.002)
        out.append(W_VTC * (inv.switch_point(vi, vo) - target) / 0.05)
        out += [W_VTC * (inv.at(vo[::-1], vi[::-1], y) - x) / 0.1 for x, y in VTC_SHOULDERS[vcc]]
        if vcc in VTC_SLOPE_25:
            got = inv.slope_30_70(vi, vo, vcc)
            out.append(W_SLOPE * math.log(got / VTC_SLOPE_25[vcc]) / 0.2)
    return out


def res_dc(p):
    return res_n(p) + res_p(p)


def res_c(p):
    out = [W_TABLE * math.log(inv.cin(p, 10.0, 0.0) / sheet.CIN[0])]
    for vcc, cl, uw in FIG59:
        out.append(math.log(inv.power(p, vcc, cl, 100e3) * 1e6 / uw))
    return out


def fit() -> dict[str, float]:
    print("stage 1: both sides, DC")
    p = run(tuple(k + s for s in "np" for k in inv.DC if k != "ksubthres"), START, res_dc, steps=100)
    print("stage 2: capacitances")
    p = run(inv.CAPS, p, res_c, steps=30)
    return p


if __name__ == "__main__":
    p = fit()
    print(json.dumps({k: float(f"{v:.5g}") for k, v in p.items()}))
    for vcc in (5, 10):
        vi, vo = inv.vtc(p, vcc, 0.002)
        print(f"  switch at VCC {vcc}: {inv.switch_point(vi, vo):.3f} V (Fig 5-7 25 °C {VTC_25[vcc]:.3f},"
              f" between {VTC_X[vcc][1]} and {VTC_X[vcc][0]})")
    with open(".claude/skills/fit-model/worked/cd4049/params.json", "w") as f:
        json.dump(p, f, indent=1)
