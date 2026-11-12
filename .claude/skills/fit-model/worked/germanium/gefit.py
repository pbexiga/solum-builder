"""Germanium alloy PNPs fitted to old Mullard curve sheets (after .claude/skills/fit-model/worked/ac128/fit_ac128.py
and scripts/fit_models.py's fit_bjt_forward, adapted, not edited).

Old sheets draw the raw curves at one collector voltage, leakage included: the transfer
characteristic IC against IB (the line meets IB = 0 at I'co, not at the origin), VBE against
IE, IB against VBE. So the fit is made to those curves as drawn, at the sheet's VCE, with the
model's own leakage flowing (IS, BR): IC at a given IB, VBE at a given IE (or IC), and ICBO
at the table's voltage, all together. Parameters: IS, NF, BF, ISE, NE, IKF, NKF, RE and BR,
NR = NF (as D-170); RB is the sheet's rbb' where given, VAF from its output admittance.
"""
import dataclasses
import importlib.util
import math
from collections.abc import Callable

import numpy as np

_spec = importlib.util.spec_from_file_location("fit_models", "scripts/fit_models.py")
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)
GP = fm.GummelPoon


def terminal(f: GP, vbe_in: float, vce: float) -> tuple[float, float, float, float]:
    """(IC, IB, IE, VBE at the terminals) with the inner emitter junction at `vbe_in` and
    the collector held `vce` from the emitter (RC, RE drops settled in a few rounds)."""
    ic = ib = 0.0
    for _ in range(4):
        ie = ic + ib
        vce_in = vce - ic * f.rc - ie * f.re
        ic, ib = f.currents(vbe_in, vbe_in - vce_in)
    ie = ic + ib
    return ic, ib, ie, vbe_in + ib * f.rb + ie * f.re


def solve(f: GP, which: int, target: float, vce: float) -> tuple[float, float, float, float]:
    """The state where terminal()[which] (0 IC, 1 IB, 2 IE) equals `target` at `vce`."""
    lo, hi = -0.6, 1.0
    while hi - lo > 1e-9:
        mid = (lo + hi) / 2
        if terminal(f, mid, vce)[which] < target:
            lo = mid
        else:
            hi = mid
    return terminal(f, (lo + hi) / 2, vce)


def ic_at_ib(f: GP, ib: float, vce: float) -> float:
    return solve(f, 1, ib, vce)[0]


def vbe_at(f: GP, which: int, i: float, vce: float) -> float:
    return solve(f, which, i, vce)[3]


def ib_at_vbe(f: GP, vbe: float, vce: float) -> float:
    lo, hi = -0.6, 1.0
    while hi - lo > 1e-9:
        mid = (lo + hi) / 2
        if terminal(f, mid, vce)[3] < vbe:
            lo = mid
        else:
            hi = mid
    return terminal(f, (lo + hi) / 2, vce)[1]


@dataclasses.dataclass
class Data:
    vce: float  # the curves' collector voltage (magnitude)
    transfer: list[tuple[float, float]]  # (IB A, IC A)
    vbe: list[tuple[float, float]]  # (I A, VBE V)
    vbe_of: int  # 0: VBE against IC, 2: against IE
    icbo: tuple[float, float]  # (A, at reverse V)
    vaf: float
    rb: float = 0.0
    weights: dict | None = None  # per-curve weight multipliers


def fit(d: Data, x0: list[float] | None = None) -> GP:
    def made(x: np.ndarray) -> GP:
        return GP(is_=10 ** x[0], nf=x[1], bf=10 ** x[2], ise=10 ** x[3], ne=x[4], ikf=10 ** x[5],
                  vaf=d.vaf, re=x[6], nkf=x[7], rb=d.rb, br=10 ** x[8], nr=x[1])

    w = {"transfer": 1.0, "vbe": 1.0, "icbo": 1.0, **(d.weights or {})}

    def residuals(x: np.ndarray) -> list[float]:
        f = made(x)
        r = [w["transfer"] * math.log(max(ic_at_ib(f, ib, d.vce), 1e-12) / ic) / 0.01 for ib, ic in d.transfer]
        r += [w["vbe"] * (vbe_at(f, d.vbe_of, i, d.vce) - v) / 2e-3 for i, v in d.vbe]
        r += [w["icbo"] * math.log(max(f.icbo(d.icbo[1]), 1e-30) / d.icbo[0]) / 0.01]
        return r

    lo = [-9.0, 1.0, 0.5, -12.0, 1.05, -4.0, 0.0, 0.3, -2.0]
    hi = [-3.0, 2.0, 3.5, -1.0, 4.0, 1.0, 10.0, 1.0, 4.0]
    x0 = x0 or [-5.0, 1.05, 1.8, -7.0, 1.5, -1.0, 0.5, 0.5, 0.8]
    x = fm.least_squares(residuals, x0, lo, hi)
    f = made(np.array(x))
    return dataclasses.replace(f, ise=0.0) if x[3] <= lo[3] + 0.01 else f


def report(f: GP, d: Data) -> dict[str, float]:
    t = [ic_at_ib(f, ib, d.vce) / ic - 1 for ib, ic in d.transfer]
    v = [vbe_at(f, d.vbe_of, i, d.vce) - vb for i, vb in d.vbe]
    return {"transfer_worst_frac": max(t, key=abs), "vbe_worst_V": max(v, key=abs),
            "icbo_A": f.icbo(d.icbo[1])}


def card(name: str, f: GP) -> str:
    return fm.bjt_card(name, f, "PNP", eg=0.67)


# ---- ngspice measurements (the real pipeline: CircuitBuilder -> netlist -> libngspice) ----
def library_with(cards: dict[str, str]):
    """The core library plus our cards (id -> json path), none of them written to library/."""
    from pathlib import Path

    from solum.models import ModelLibrary, load_model, load_models

    lib = load_models([Path("library/models")])
    extra = {mid: load_model(Path(p)) for mid, p in cards.items()}
    return ModelLibrary({**{k: lib.get(k) for k in lib.ids()}, **extra})


def _op(engine, models, b):
    from tests.sim.model_checks import _op as op

    return op(engine, models, b)


def sim_ic_at_ib(engine, models, mid: str, ib: float, vce: float) -> float:
    """IC (A) with `ib` drawn out of the base (PNP: into it, conventionally) and the
    collector held `vce` below the emitter; IB 0: base open (1 TΩ)."""
    from solum.circuit.build import CircuitBuilder

    if ib == 0:
        b = (CircuitBuilder("ib").part("V1", "vsource", "VC", "0", value=-vce)
             .part("R2", "resistor", "b", "0", value=1e12)
             .part("Q1", "bjt", "VC", "b", "0", model=mid))
        return abs(_op(engine, models, b)["Q1.ic"])
    rb = 9.8 / ib
    for _ in range(14):
        b = (CircuitBuilder("ib").part("V1", "vsource", "VC", "0", value=-vce)
             .part("V2", "vsource", "VB", "0", value=-10.0)
             .part("R2", "resistor", "VB", "b", value=rb)
             .part("Q1", "bjt", "VC", "b", "0", model=mid))
        op = _op(engine, models, b)
        rb *= abs(op["Q1.ib"]) / ib
    return abs(op["Q1.ic"])


def sim_vbe_at_ib(engine, models, mid: str, ib: float, vce: float) -> float:
    from solum.circuit.build import CircuitBuilder

    rb = 9.8 / ib
    for _ in range(14):
        b = (CircuitBuilder("ib").part("V1", "vsource", "VC", "0", value=-vce)
             .part("V2", "vsource", "VB", "0", value=-10.0)
             .part("R2", "resistor", "VB", "b", value=rb)
             .part("Q1", "bjt", "VC", "b", "0", model=mid))
        op = _op(engine, models, b)
        rb *= abs(op["Q1.ib"]) / ib
    return -op["b"]


def sim_small_hfe(engine, models, mid: str, ic: float, vce: float) -> float:
    """Small-signal current gain dIC/dIB at `ic`, `vce` (1 kc/s is DC for these parts):
    IB found for IC, then ±2 %."""
    lo, hi = ic / 1000, ic / 5
    for _ in range(40):  # IB for IC by bisection on the trimmed-IB measurement
        mid_ib = (lo * hi) ** 0.5
        if sim_ic_at_ib(engine, models, mid, mid_ib, vce) < ic:
            lo = mid_ib
        else:
            hi = mid_ib
        if hi / lo < 1.0005:
            break
    ib = (lo * hi) ** 0.5
    a, b = sim_ic_at_ib(engine, models, mid, ib * 0.98, vce), sim_ic_at_ib(engine, models, mid, ib * 1.02, vce)
    return (b - a) / (0.04 * ib)


def sim_ic_at_vbe(engine, models, mid: str, vbe: float, vce: float) -> float:
    """IC with the base held `vbe` from the emitter (negative: reverse bias, cut off)."""
    from solum.circuit.build import CircuitBuilder

    b = (CircuitBuilder("vb").part("V1", "vsource", "VC", "0", value=-vce)
         .part("V2", "vsource", "b", "0", value=-vbe)
         .part("Q1", "bjt", "VC", "b", "0", model=mid))
    return abs(_op(engine, models, b)["Q1.ic"])


def _ib_for_ic(engine, models, mid, ic, vce):
    lo, hi = ic / 2000, ic / 3
    for _ in range(60):
        m = (lo * hi) ** 0.5
        if sim_ic_at_ib(engine, models, mid, m, vce) < ic:
            lo = m
        else:
            hi = m
        if hi / lo < 1.0002:
            break
    return (lo * hi) ** 0.5


def sim_knee(engine, models, mid: str, ic_set: float, vce_set: float, ic_knee: float) -> float:
    """Mullard's collector knee voltage: IB set so IC = `ic_set` at `vce_set`, then the VCE
    at which IC has fallen to `ic_knee` (OC44 page D2, fig. 1)."""
    ib = _ib_for_ic(engine, models, mid, ic_set, vce_set)
    lo, hi = 0.001, vce_set
    for _ in range(40):
        m = (lo + hi) / 2
        if sim_ic_at_ib(engine, models, mid, ib, m) < ic_knee:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def sim_vbe_at_ie(engine, models, mid: str, ie: float, vce: float) -> float:
    """VBE with `ie` fed into the emitter (grounded base, a resistor from +10 V trimmed), the
    collector at VCE = `vce` (VCB = vce - VBE, settled each round): works down to IE ~ 0,
    where the base current turns round (leakage)."""
    from solum.circuit.build import CircuitBuilder

    re_, vbe = 9.9 / ie, 0.1
    for _ in range(14):
        b = (CircuitBuilder("ie").part("V1", "vsource", "VC", "0", value=-(vce - vbe))
             .part("V2", "vsource", "VE", "0", value=10.0)
             .part("R2", "resistor", "VE", "e", value=re_)
             .part("Q1", "bjt", "VC", "0", "e", model=mid))
        op = _op(engine, models, b)
        vbe = op["e"]
        re_ *= abs(op["Q1.ic"] + op["Q1.ib"]) / ie
    return vbe


def sim_ib_at_vbe(engine, models, mid: str, vbe: float, vce: float) -> float:
    from solum.circuit.build import CircuitBuilder

    b = (CircuitBuilder("vb").part("V1", "vsource", "VC", "0", value=-vce)
         .part("V2", "vsource", "b", "0", value=-vbe)
         .part("Q1", "bjt", "VC", "b", "0", model=mid))
    return -_op(engine, models, b)["Q1.ib"]  # PNP: base current flows out of the base


def check_line(name: str, sim: float, lo=None, hi=None, typ=None, tol=None, unit="", scale=1.0) -> str:
    ok = (lo is None or sim >= lo) and (hi is None or sim <= hi) and (tol is None or abs(sim - typ) <= tol)
    verdict = ("OK" if ok else "MISS") if (lo, hi, tol) != (None, None, None) else "info"
    s = lambda v: "—" if v is None else f"{v * scale:.4g}"  # noqa: E731
    dev = "" if typ is None else f" ({(sim - typ) * scale:+.3g}{unit} from typ)"
    return f"| {name} | {s(sim)} | {s(lo)} | {s(typ)} | {s(hi)} | {s(tol)} | {verdict}{dev} |"


Callable  # noqa: B018 (re-exported for scripts' type hints)
