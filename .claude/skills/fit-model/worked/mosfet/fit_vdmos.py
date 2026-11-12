"""Fit an ngspice VDMOS card to a MOSFET sheet's typical curves, through ngspice itself.

Each candidate card is simulated: the output curves (ID vs VDS at fixed VGS, one nested
DC sweep), the transfer curve (ID vs VGS at the figure's VDS), VGS(th) diode-connected
(VDS = VGS) at the table's current, and the table's on-voltages. least squares
moves VTO, KP, KSUBTHRES, MTRIODE, LAMBDA, RS and RD (log-scaled) to fit them all, each
point weighted as its spec says (the project's own Levenberg-Marquardt, `scripts/fit_models.py`).
Run in the dev image:
  python .claude/skills/fit-model/worked/mosfet/fit_vdmos.py 2N7000
"""

import importlib
import math
import sys

import numpy as np

from scripts.fit_models import least_squares
from solum.sim.native import NativeNgspice

ENGINE = NativeNgspice("/usr/lib/x86_64-linux-gnu/libngspice.so.0")
DC_PARAMS = ("vto", "kp", "ksubthres", "mtriode", "lambda", "rs", "rd")
LOG_PARAMS = {"kp", "ksubthres", "mtriode", "lambda", "rs", "rd"}


def card(name: str, p: dict[str, float], extra: dict[str, float] | None = None) -> str:
    vals = {**p, **(extra or {})}
    body = " ".join(f"{k}={v:.5g}" for k, v in vals.items())
    return f".model {name} VDMOS({body})"


def _dc(model: str, lines: str) -> list[dict[str, np.ndarray]]:
    res = ENGINE.run(f"fit\n{lines}\n{model}\n.end\n")
    return [{k: np.asarray(v.real if np.iscomplexobj(v) else v) for k, v in p.vectors.items()}
            for p in res.plots if p.kind == "dc"]


def output_curves(model: str, vgs: list[float], vds_top: float, step: float) -> np.ndarray:
    """ID (A) at VDS 0..vds_top for each VGS: rows per VGS."""
    lo, hi = min(vgs), max(vgs)
    gstep = vgs[1] - vgs[0]
    [p] = _dc(model, f"Vd d 0 0\nVg g 0 0\nM1 d g 0 MT\n.dc Vd 0 {vds_top} {step} Vg {lo} {hi} {gstep}")
    n = int(round(vds_top / step)) + 1
    return -np.asarray(p["vd#branch"]).reshape(-1, n)


def transfer(model: str, vds: float, top: float, step: float) -> tuple[np.ndarray, np.ndarray]:
    [p] = _dc(model, f"Vd d 0 {vds}\nVg g 0 0\nM1 d g 0 MT\n.dc Vg 0 {top} {step}")
    return np.asarray(p["v-sweep"]), -np.asarray(p["vd#branch"])


def vth(model: str, current: float) -> float:
    """VGS with VDS = VGS (drain tied to gate) where ID = `current`."""
    [p] = _dc(model, f"Id 0 g 0\nM1 g g 0 MT\n.dc Id {current} {current * 1.0001} {current * 1e-4}")
    return float(np.asarray(p["g"])[0])


def vds_at(model: str, vgs: float, current: float) -> float:
    """VDS with VGS fixed and ID forced: the table's VDS(on)."""
    [p] = _dc(model, f"Vg g 0 {vgs}\nId 0 d 0\nM1 d g 0 MT\n.dc Id {current} {current * 1.0001} {current * 1e-4}")
    return float(np.asarray(p["d"])[0])


def unpack(x: np.ndarray, names: tuple[str, ...]) -> dict[str, float]:
    return {k: float(math.exp(v) if k in LOG_PARAMS else v) for k, v in zip(names, x)}


def residuals(x: np.ndarray, spec: dict, names: tuple[str, ...], fixed: dict[str, float]) -> np.ndarray:
    p = {**fixed, **unpack(x, names)}
    model = card("MT", p)
    out: list[float] = []
    try:
        oc = spec["output"]
        grid = output_curves(model, oc["vgs"], oc["vds_top"], oc["step"])
        vds = np.arange(grid.shape[1]) * oc["step"]
        for row, (vg, pts) in zip(grid, oc["curves"].items()):
            for v, i in pts:
                sim = float(np.interp(v, vds, row))
                out.append(oc["weight"] * math.log(max(sim, 1e-9) / i))
        tr = spec["transfer"]
        vg, idr = transfer(model, tr["vds"], tr["top"], 0.01)
        for v, i in tr["points"]:
            sim = float(np.interp(v, vg, idr))
            out.append(tr["weight"] * math.log(max(sim, 1e-12) / i))
        for v_target, current, w in spec["vth"]:
            out.append(w * (vth(model, current) - v_target))
        for vgs, current, v_target, w in spec["vds_on"]:
            out.append(w * math.log(max(vds_at(model, vgs, current), 1e-6) / v_target))
    except Exception:  # noqa: BLE001  (a card ngspice can't solve: push away from it)
        return np.full(spec["n"], 10.0)
    return np.asarray(out)


def fit(spec: dict) -> dict[str, float]:
    names = tuple(k for k in DC_PARAMS if k not in spec.get("fixed", {}))
    start = spec["start"]
    x0 = np.array([math.log(start[k]) if k in LOG_PARAMS else start[k] for k in names])
    spec["n"] = len(residuals(x0, spec, names, spec.get("fixed", {})))
    lo = [math.log(1e-6) if k in LOG_PARAMS else 0.0 for k in names]
    hi = [math.log(1e3) if k in LOG_PARAMS else 5.0 for k in names]
    x = np.array(least_squares(lambda v: list(residuals(v, spec, names, spec.get("fixed", {}))),
                               list(x0), lo, hi, steps=spec.get("steps", 60)))
    p = {**spec.get("fixed", {}), **unpack(x, names)}
    worst = np.abs(residuals(x, spec, names, spec.get("fixed", {})))
    print("worst residual", worst.max(), "rms", float(np.sqrt(np.mean(worst**2))))
    return p


def report(spec: dict, p: dict[str, float]) -> None:
    model = card("MT", p)
    oc = spec["output"]
    grid = output_curves(model, oc["vgs"], oc["vds_top"], oc["step"])
    vds = np.arange(grid.shape[1]) * oc["step"]
    for row, (vg, pts) in zip(grid, oc["curves"].items()):
        errs = [f"{v:g}V {float(np.interp(v, vds, row)) / i - 1:+.0%}" for v, i in pts]
        print(f"  VGS {vg}: " + ", ".join(errs))
    tr = spec["transfer"]
    vg, idr = transfer(model, tr["vds"], tr["top"], 0.01)
    print("  transfer: " + ", ".join(f"{v:g}V {float(np.interp(v, vg, idr)) / i - 1:+.0%}" for v, i in tr["points"]))
    for v_target, current, _ in spec["vth"]:
        print(f"  VGS(th) at {current * 1e3:g} mA: {vth(model, current):.3f} V (sheet {v_target})")
    for vgs, current, v_target, _ in spec["vds_on"]:
        print(f"  VDS(on) at VGS {vgs}, ID {current * 1e3:g} mA: {vds_at(model, vgs, current):.3f} V (sheet {v_target})")
    for i in (1e-5, 1e-4, 1e-3, 1e-2):
        print(f"  VGS(th)-style at {i * 1e3:g} mA: {vth(model, i):.3f} V")


if __name__ == "__main__":
    mod = importlib.import_module(f"scratch.fit.mosfet.spec_{sys.argv[1].lower()}")
    spec = mod.SPEC
    p = fit(spec)
    print(card(sys.argv[1], p))
    report(spec, p)
