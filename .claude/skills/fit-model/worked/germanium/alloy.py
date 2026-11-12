"""Alloy switching transistors (RCA 2N404, TI 2N1308) fitted to their sheets: computer
transistors of 1959-66 whose sheets give a table of typicals at 10-24 mA, near saturation,
and curves that are either typical (TI) or a minimum and a maximum (RCA).

Points (magnitudes; PNP and NPN alike), each with its residual:
  hfe      (IC A, VCE V)  -> hFE           1 % in log
  ic_at_ib (IB A, VCE V)  -> IC A          1 % in log
  vbe_sat  (IC A, IB A)   -> VBE V         2 mV
  vce_sat  (IC A, IB A)   -> VCE V         2 mV
  icbo     (VCB V, -)     -> A             1 % in log
  iebo     (VEB V, -)     -> A             1 % in log
A point may name a `group`: the group's values are matched up to one free factor (a curve whose
shape the sheet gives but not its level, e.g. a minimum curve standing for the typical part).

Parameters: IS, NF, BF, ISE, NE, IKF, NKF, RE, BR, ISC, NC, RC, NR = NF (D-170); RB from rbb'
where the sheet gives one, VAF fixed (or none). scripts/fit_models.py's GummelPoon does the
physics (the same equations as ngspice's bjtload).
"""
import dataclasses
import math
import sys

import numpy as np

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g  # noqa: E402

fm = g.fm
GP = fm.GummelPoon


@dataclasses.dataclass(frozen=True)
class Point:
    kind: str
    a: float
    b: float
    value: float
    group: str | None = None
    weight: float = 1.0
    src: str = ""


def model_value(f: GP, p: Point) -> float:
    if p.kind == "hfe":
        return f.forward(p.a, p.b)[1]
    if p.kind == "ic_at_ib":
        return g.ic_at_ib(f, p.a, p.b)
    if p.kind == "vbe_sat":
        return f.saturated(p.a, p.b)[0]
    if p.kind == "vce_sat":
        return f.saturated(p.a, p.b)[1]
    if p.kind == "icbo":
        return f.icbo(p.a)
    if p.kind == "iebo":
        return f.iebo(p.a)
    raise ValueError(p.kind)


LOG = ("hfe", "ic_at_ib", "icbo", "iebo")


def residual(f: GP, p: Point, scale: float = 1.0) -> float:
    got = model_value(f, p)
    if p.kind in LOG:
        return p.weight * math.log(max(got, 1e-30) / (scale * p.value)) / 0.01
    return p.weight * (got - p.value) / 2e-3


NAMES = ["is_", "nf", "bf", "ise", "ne", "ikf", "re", "nkf", "br", "isc", "nc", "rc"]
LOGS = {"is_", "bf", "ise", "ikf", "br", "isc"}
LO = dict(is_=-9.0, nf=1.0, bf=0.5, ise=-12.0, ne=1.05, ikf=-4.0, re=0.0, nkf=0.3, br=-2.0, isc=-14.0, nc=1.0, rc=0.0)
HI = dict(is_=-3.0, nf=2.0, bf=3.5, ise=-1.0, ne=4.0, ikf=1.0, re=10.0, nkf=1.0, br=4.0, isc=-2.0, nc=4.0, rc=20.0)
X0 = dict(is_=-5.5, nf=1.05, bf=1.8, ise=-7.0, ne=1.5, ikf=-1.0, re=0.5, nkf=0.5, br=0.5, isc=-8.0, nc=1.5, rc=0.5)


@dataclasses.dataclass
class Spec:
    points: list[Point]
    vaf: float = math.inf
    rb: float = 0.0
    fixed: dict | None = None  # parameters held (e.g. {"ise": 0.0} or {"rc": 0.0})
    x0: dict | None = None
    hi: dict | None = None
    lo: dict | None = None


def groups(spec: Spec) -> list[str]:
    return sorted({p.group for p in spec.points if p.group})


def made(spec: Spec, x: np.ndarray) -> tuple[GP, dict[str, float]]:
    free = [n for n in NAMES if n not in (spec.fixed or {})]
    vals = dict(spec.fixed or {})
    for n, v in zip(free, x):
        vals[n] = 10 ** v if n in LOGS else float(v)
    ks = {gname: 10 ** float(v) for gname, v in zip(groups(spec), x[len(free):])}
    f = GP(is_=vals["is_"], nf=vals["nf"], bf=vals["bf"], ise=vals["ise"], ne=vals["ne"], ikf=vals["ikf"],
           vaf=spec.vaf, re=vals["re"], nkf=vals["nkf"], br=vals["br"], isc=vals["isc"], nc=vals["nc"],
           rc=vals["rc"], rb=spec.rb, nr=vals["nf"])
    return f, ks


def fit(spec: Spec) -> tuple[GP, dict[str, float]]:
    free = [n for n in NAMES if n not in (spec.fixed or {})]
    lo = {**LO, **(spec.lo or {})}
    hi = {**HI, **(spec.hi or {})}
    x0 = {**X0, **(spec.x0 or {})}
    gs = groups(spec)

    def residuals(x: np.ndarray) -> list[float]:
        f, ks = made(spec, x)
        return [residual(f, p, ks.get(p.group, 1.0) if p.group else 1.0) for p in spec.points]

    x = fm.least_squares(residuals, [x0[n] for n in free] + [0.0] * len(gs),
                         [lo[n] for n in free] + [-1.0] * len(gs), [hi[n] for n in free] + [1.0] * len(gs))
    f, ks = made(spec, np.array(x))
    at_bound = [n for n, v in zip(free, x) if abs(v - lo[n]) < 1e-3 or abs(v - hi[n]) < 1e-3]
    return f, {**ks, "_at_bound": at_bound}  # type: ignore[dict-item]


def report(f: GP, spec: Spec, ks: dict) -> list[str]:
    lines = []
    for p in spec.points:
        k = ks.get(p.group, 1.0) if p.group else 1.0
        got = model_value(f, p)
        want = k * p.value if p.kind in LOG else p.value
        err = f"{(got / want - 1) * 100:+.1f} %" if p.kind in LOG else f"{(got - want) * 1e3:+.1f} mV"
        lines.append(f"  {p.kind:8s} {p.a:.4g} {p.b if p.b is not None else 'VCB=0'}  sheet {want:.4g}  fit {got:.4g}  {err}  {p.group or ''}")
    return lines


def worst(f: GP, spec: Spec, ks: dict, kind: str, group: str | None = "*") -> float:
    errs = []
    for p in spec.points:
        if p.kind != kind or (group != "*" and p.group != group):
            continue
        k = ks.get(p.group, 1.0) if p.group else 1.0
        got = model_value(f, p)
        errs.append(got / (k * p.value) - 1 if kind in LOG else got - p.value)
    return max(errs, key=abs) if errs else 0.0
