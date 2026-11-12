"""LND150 (depletion VDMOS, negative VTO) from Microchip DS20005454A (2018).

DC: Figure 2-4 Saturation Characteristics (VDS 0-5 V, VGS -1 to +1 V, read off the vector
drawing with raw.py: frame x 350.1-487.5 pt = 0-5 V, y 285.5-148.2 pt = 0-6 mA), plus the
table: RDS(on) 850 ohm typ at VGS 0, ID 0.5 mA; VGS(off) -1 to -3 V at ID 100 nA, VDS 25 V
(middle -2 V, D-161). Figures 2-2 and 2-8 are at VDS = 400 V (self-heated, ~0.6 W): left out.
Caps: Figure 2-9 (VGS = -10 V, 1 MHz). Held out: IDSS 1-3 mA at VDS 25 V; gFS 2 mS typ at 1 mA;
Figure 2-10 ID vs RSOURCE (25 C); VSD <= 0.9 V at 1 mA.
Run in the dev image: python .claude/skills/fit-model/worked/mosfet/fit_lnd150.py
"""
import math

import numpy as np

from scratch.fit.mosfet.fit_vdmos import ENGINE, LOG_PARAMS, _dc, card, output_curves, vds_at
from scripts.fit_models import least_squares

mA = 1e-3
CURVES = {
    -1.0: [(0.0174, 0.01396), (0.0857, 0.04618), (0.2322, 0.07839), (0.4834, 0.09303), (1.311, 0.09303), (4.976, 0.09303)],
    -0.5: [(0.1157, 0.09491), (0.3925, 0.3052), (0.728, 0.5155), (1.019, 0.6111), (1.813, 0.6111), (4.991, 0.6111)],
    0.0: [(0.24, 0.2677), (0.8072, 0.8568), (1.475, 1.443), (2.016, 1.701), (3.665, 1.696), (4.991, 1.701)],
    0.5: [(0.3644, 0.5136), (1.222, 1.645), (2.222, 2.777), (3.012, 3.291), (4.15, 3.291), (4.976, 3.291)],
    1.0: [(0.6, 0.8926), (1.962, 2.779), (3.594, 4.666), (4.976, 5.524)],
}
CURVES = {vg: [(v, i * mA) for v, i in pts] for vg, pts in CURVES.items()}
# Figure 2-9, VGS = -10 V: Ciss flat at 7.77 pF (path 923); Coss (925), Crss (924), pF
CAPS = [(1.0, 7.77, 4.6, 0.95), (3.272, 7.77, 2.681, 0.80), (9.791, 7.77, 2.293, 0.55),
        (19.96, 7.77, 2.14, 0.3843), (33.84, 7.77, 2.03, 0.2681)]
# Figure 2-10, 25 C (path 1015): RSOURCE (ohm), ID (mA), gate tied to the source resistor's foot
RSOURCE = [(16.21, 1.398), (75.93, 1.197), (297.0, 0.8085), (1359.0, 0.3827), (10190.0, 0.06949)]
NAMES = ("vto", "kp", "ksubthres", "mtriode", "lambda", "rs")


def vgs_off(model: str, vds: float, current: float) -> float:
    [p] = _dc(model, f"Vd d 0 {vds}\nVg g 0 0\nM1 d g 0 MT\n.dc Vg -6 0 0.002")
    vg, i = np.asarray(p["v-sweep"]).real, -np.asarray(p["vd#branch"]).real
    return float(np.interp(math.log(current), np.log(np.maximum(i, 1e-15)), vg))


def id_at(model: str, vgs: float, vds: float) -> float:
    [p] = _dc(model, f"Vd d 0 {vds}\nVg g 0 {vgs}\nM1 d g 0 MT\n.dc Vd {vds} {vds} 1")
    return float(-np.asarray(p["vd#branch"]).real[0])


def self_bias(model: str, r: float, vdd: float = 25.0) -> float:
    [p] = _dc(model, f"Vd d 0 {vdd}\nM1 d 0 s MT\nRs s 0 {r}\n.dc Vd {vdd} {vdd} 1")
    return float(-np.asarray(p["vd#branch"]).real[0])


def unpack(x):
    return {k: (math.exp(v) if k in LOG_PARAMS else v) for k, v in zip(NAMES, x)}


def residuals(x):
    p = {**unpack(x), "rd": 1e-6}
    m = card("MT", p)
    out = []
    try:
        grid = output_curves(m, list(CURVES), 5.0, 0.01)
        vds = np.arange(grid.shape[1]) * 0.01
        for row, (vg, pts) in zip(grid, CURVES.items()):
            # past the knee (the drawn curve flat, VDS > 1.5 overdrive): where pedals use it
            out += [(3.0 if v > 1.5 * (vg + 1.33) else 1.0)
                    * math.log(max(float(np.interp(v, vds, row)), 1e-12) / i) for v, i in pts]
        out.append(3.0 * math.log(vds_at(m, 0.0, 0.5e-3) / 0.425))  # RDS(on) 850 ohm
        out.append(0.5 * (vgs_off(m, 25.0, 100e-9) + 2.0))  # VGS(off) middle
    except Exception:  # noqa: BLE001
        return [10.0] * 32
    return out


def report(p):
    m = card("MT", p)
    grid = output_curves(m, list(CURVES), 5.0, 0.01)
    vds = np.arange(grid.shape[1]) * 0.01
    for row, (vg, pts) in zip(grid, CURVES.items()):
        print(f"  VGS {vg:+}: " + ", ".join(f"{v:g}V {float(np.interp(v, vds, row)) / i - 1:+.0%}" for v, i in pts))
    print(f"  RDS(on) 0.5 mA: {vds_at(m, 0.0, 0.5e-3) / 0.5e-3:.0f} ohm (850 typ, 1000 max)")
    print(f"  VGS(off) 100 nA, 25 V: {vgs_off(m, 25.0, 100e-9):.3f} V (-1 to -3)")
    print(f"  IDSS 25 V: {id_at(m, 0.0, 25.0) * 1e3:.3f} mA (1 to 3)")
    i1 = 1e-3
    vg = vgs_off(m, 25.0, i1)
    g = (id_at(m, vg + 0.01, 25.0) - id_at(m, vg - 0.01, 25.0)) / 0.02
    print(f"  gFS at 1 mA, 25 V: {g * 1e3:.2f} mS (2 typ, 1 min)")
    print("  ID vs RSOURCE (25 V): " + ", ".join(f"{r:g}: {self_bias(m, r) * 1e3:.3f} ({self_bias(m, r) / (i * mA) - 1:+.0%})" for r, i in RSOURCE))


def stage_one():
    start = {"vto": -1.3, "kp": 2e-3, "ksubthres": 0.1, "mtriode": 1.5, "lambda": 1e-3, "rs": 10.0}
    x0 = [math.log(start[k]) if k in LOG_PARAMS else start[k] for k in NAMES]
    lo = [-5.0 if k == "vto" else math.log(1e-7) for k in NAMES]
    hi = [0.0 if k == "vto" else math.log(1e4) for k in NAMES]
    hi[NAMES.index("lambda")] = math.log(0.01)  # the figure's curves are flat past the knee
    x = least_squares(residuals, x0, lo, hi, steps=80)
    r = np.abs(residuals(x))
    print("worst", r.max(), "rms", float(np.sqrt(np.mean(r**2))))
    p = {**unpack(x), "rd": 1e-6}
    print(card("LND150", p))
    report(p)


DC = {"vto": -1.2748, "kp": 0.0021146, "ksubthres": 0.16338, "mtriode": 0.52403,
      "lambda": 0.005317, "rs": 17.537, "rd": 1e-06}


def stage_two():
    """Caps to Figure 2-9 with the DC card held; the body diode left at VDMOS's defaults
    (the sheet gives only VSD <= 0.9 V at 1 mA), checked."""
    from scratch.fit.mosfet.fit_ac import body, caps, fit_caps
    spec = {"caps": CAPS, "cap_vgs": -10.0,
            "cap_start": {"cgs": 7e-12, "cgdmax": 2e-12, "cgdmin": 0.2e-12, "a": 1.0,
                          "cjo": 3e-12, "m": 0.5, "vj": 0.8}}
    cp = fit_caps(spec, DC)
    full = {**DC, **cp}
    print(card("LND150", full))
    for (v, *sheet), row in zip(CAPS, caps(DC, cp, [v for v, *_ in CAPS], -10.0)):
        print(f"  VDS {v:g}: " + ", ".join(f"{n} {g * 1e12:.2f}p ({g / (s * 1e-12) - 1:+.0%})"
                                         for n, g, s in zip(("Ciss", "Coss", "Crss"), row, sheet)))
    print("  table at 25 V:", [round(c * 1e12, 2) for c in caps(DC, cp, [25.0], -10.0)[0]], "(7.5, 2, 0.5 typ; 10, 3.5, 1 max)")
    v, i = body(DC, cp)
    print(f"  VSD at 1 mA: {float(np.interp(1e-3, i, v)):.3f} V (0.9 max)")


if __name__ == "__main__":
    import sys
    stage_two() if sys.argv[1:] == ["caps"] else stage_one()
