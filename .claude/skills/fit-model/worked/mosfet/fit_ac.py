"""Second stage after fit_vdmos.py: the gate and drain capacitances (sheet figure, 1 MHz,
VGS = 0) and the body diode (IS vs VSD at VGS = 0), fitted through ngspice with the DC card
held. Run: python .claude/skills/fit-model/worked/mosfet/fit_ac.py 2N7000
"""

import importlib
import math
import sys

import numpy as np

from scratch.fit.mosfet.fit_vdmos import ENGINE, card
from scripts.fit_models import least_squares

CAP = ("cgs", "cgdmax", "cgdmin", "a", "cjo", "m", "vj")
DIODE = ("is", "n", "rb")
LINEAR = {"m"}
F = 1e6


def caps(dc: dict[str, float], p: dict[str, float], vds: list[float], vgs: float = 0.0) -> np.ndarray:
    """Rows of (Ciss, Coss, Crss) in farads at each VDS, at `vgs`."""
    lines = []
    for k, v in enumerate(vds):
        lines += [f"Vga{k} ga{k} 0 dc {vgs} ac 1", f"Vda{k} da{k} 0 dc {v}", f"Ma{k} da{k} ga{k} 0 MT",
                  f"Vgb{k} gb{k} 0 dc {vgs}", f"Vdb{k} db{k} 0 dc {v} ac 1", f"Mb{k} db{k} gb{k} 0 MT"]
    net = "caps\n" + "\n".join(lines) + f"\n.ac lin 1 {F} {F}\n{card('MT', {**dc, **p})}\n.end\n"
    vec = ENGINE.run(net).plot("ac").vectors
    w = 2 * math.pi * F
    out = []
    for k in range(len(vds)):
        out.append((abs(vec[f"vga{k}#branch"][0]) / w, abs(vec[f"vdb{k}#branch"][0]) / w,
                    abs(vec[f"vda{k}#branch"][0]) / w))
    return np.asarray(out)


def body(dc: dict[str, float], p: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    net = f"body\nVs s 0 0\nM1 0 s s MT\n.dc Vs 0.2 1.4 0.005\n{card('MT', {**dc, **p})}\n.end\n"
    pl = ENGINE.run(net).plot("dc").vectors
    return np.asarray(pl["v-sweep"]).real, -np.asarray(pl["vs#branch"]).real


def _x(p: dict[str, float], names: tuple[str, ...]) -> list[float]:
    return [p[k] if k in LINEAR else math.log(p[k]) for k in names]


def _p(x: list[float], names: tuple[str, ...]) -> dict[str, float]:
    return {k: (v if k in LINEAR else math.exp(v)) for k, v in zip(names, x)}


def fit_caps(spec: dict, dc: dict[str, float]) -> dict[str, float]:
    cs = spec["caps"]
    vds = [v for v, *_ in cs]
    names = CAP

    def res(x: list[float]) -> list[float]:
        try:
            got = caps(dc, _p(x, names), vds, spec.get("cap_vgs", 0.0))
        except Exception:  # noqa: BLE001
            return [10.0] * (3 * len(vds))
        return [math.log(g / (s * 1e-12)) for row, (_, *sheet) in zip(got, cs)
                for g, s in zip(row, sheet)]

    start = spec["cap_start"]
    lo = [0.2 if k == "m" else math.log(1e-14) for k in names]
    hi = [0.9 if k == "m" else math.log(1e-8) for k in names]
    lo[names.index("vj")], hi[names.index("vj")] = math.log(0.1), math.log(5)
    lo[names.index("a")], hi[names.index("a")] = math.log(1e-3), math.log(100)
    x = least_squares(res, _x(start, names), lo, hi, steps=80)
    r = np.abs(res(x))
    print("caps worst", r.max(), "rms", float(np.sqrt(np.mean(r**2))))
    return _p(x, names)


def fit_body(spec: dict, dc: dict[str, float]) -> dict[str, float]:
    pts = spec["body"]

    def res(x: list[float]) -> list[float]:
        try:
            v, i = body(dc, _p(x, DIODE))
        except Exception:  # noqa: BLE001
            return [10.0] * len(pts)
        return [math.log(max(float(np.interp(vs, v, i)), 1e-12) / ia) for vs, ia in pts]

    lo = [math.log(1e-16), math.log(0.8), math.log(1e-4)]
    hi = [math.log(1e-6), math.log(3), math.log(10)]
    x = least_squares(res, _x(spec["body_start"], DIODE), lo, hi, steps=80)
    r = np.abs(res(x))
    print("body worst", r.max(), "rms", float(np.sqrt(np.mean(r**2))))
    return _p(x, DIODE)


if __name__ == "__main__":
    spec = importlib.import_module(f"scratch.fit.mosfet.spec_{sys.argv[1].lower()}").SPEC
    dc = spec["dc"]
    cp = fit_caps(spec, dc)
    bp = fit_body(spec, dc)
    full = {**dc, **cp, **bp}
    print(card(sys.argv[1], full))
    for (v, *sheet), row in zip(spec["caps"], caps(dc, {**cp, **bp}, [v for v, *_ in spec["caps"]])):
        print(f"  VDS {v:g}: " + ", ".join(f"{n} {g * 1e12:.2f}p ({g / (s * 1e-12) - 1:+.0%})"
                                         for n, g, s in zip(("Ciss", "Coss", "Crss"), row, sheet)))
    v, i = body(dc, {**cp, **bp})
    print("  body: " + ", ".join(f"{vs:g}V {float(np.interp(vs, v, i)) / ia - 1:+.0%}" for vs, ia in spec["body"]))
