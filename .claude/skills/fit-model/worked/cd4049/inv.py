"""One CD4049UB inverter as an ngspice subcircuit, and the measurements the fit and the check share.

The subcircuit (`CD4049UB_INV in out vdd vss`): an N- and a P-channel VDMOS (ngspice's
three-terminal MOSFET, as the 2N7000/LND150 cards, D-175/D-178), each source on its rail,
which is what a CMOS inverter is when each body is tied to its source. VDMOS rather than
level 1: MTRIODE lets the channel saturate at (VGS - VTO)/MTRIODE and THETA reduces the
mobility, which Figure 5-3's curves need (level 1 left -33 %/+29 % misses and VTO near 3 V);
its body diode is the output's own drain-bulk diode (OUT->VDD, VSS->OUT); KSUBTHRES gives
a smooth VTC. Gate capacitances are VDMOS's CGS (to the rail) and CGD (CGDMAX = CGDMIN, so
linear); CJO the output junctions. Plus the input diode the sheet's schematic draws (p. 1):
VSS->IN (no IN->VDD diode: the input may go above VCC, p. 1); its and the supply diode's
values are ngspice's defaults (the sheet gives none).
Run in the dev image (PYTHONPATH=/src).
"""

import math

import numpy as np

from solum.sim.native import NativeNgspice

ENGINE = NativeNgspice("/usr/lib/x86_64-linux-gnu/libngspice.so.0")

DC = ("vto", "kp", "theta", "mtriode", "lambda", "rs", "rd", "ksubthres")
CAPS = ("cgs", "cgd", "cjo")


def card(name: str, p: dict[str, float], s: str) -> str:
    """The VDMOS .model line for side s ('n' or 'p'); p holds vto as a magnitude."""
    vals = {k: p[k + s] for k in DC}
    vals["vto"] = vals["vto"] if s == "n" else -vals["vto"]
    vals.update(cgs=p["cgs"], cgdmax=p["cgd"], cgdmin=p["cgd"], cjo=p["cjo"])
    body = " ".join(f"{k}={v:.5g}" for k, v in vals.items())
    return f".model {name} VDMOS({'pchan ' if s == 'p' else ''}{body})"


def subckt(p: dict[str, float]) -> str:
    """The .subckt text for parameters p."""
    return "\n".join([
        ".subckt CD4049UB_INV in out vdd vss",
        "MN out in vss CD4049UB_N",
        "MP out in vdd CD4049UB_P",
        "DIN vss in CD4049UB_D",
        "DSUP vss vdd CD4049UB_D",
        card("CD4049UB_N", p, "n"),
        card("CD4049UB_P", p, "p"),
        ".model CD4049UB_D D",
        ".ends CD4049UB_INV",
    ])


def _plots(p: dict[str, float], body: str, kind: str = "dc") -> list[dict[str, np.ndarray]]:
    res = ENGINE.run(f"inv\n{subckt(p)}\n{body}\n.end\n")
    return [{k: np.asarray(v.real if np.iscomplexobj(v) else v) for k, v in pl.vectors.items()}
            for pl in res.plots if pl.kind == kind]


def sink(p: dict[str, float], vcc: float, vds_top: float) -> tuple[np.ndarray, np.ndarray]:
    """Input at VCC (N on): output forced 0..vds_top, sink current (A) into OUT."""
    [r] = _plots(p, f"Vdd vdd 0 {vcc}\nVin in 0 {vcc}\nVo o 0 0\nX1 in o vdd 0 CD4049UB_INV\n"
                    f".dc Vo 0 {vds_top} 0.01")
    return r["v-sweep"], -r["vo#branch"]


def source(p: dict[str, float], vcc: float, vds_top: float) -> tuple[np.ndarray, np.ndarray]:
    """Input at 0 (P on): output forced VCC down by 0..vds_top; returns (|VDS|, source current A)."""
    [r] = _plots(p, f"Vdd vdd 0 {vcc}\nVin in 0 0\nVo o 0 {vcc}\nX1 in o vdd 0 CD4049UB_INV\n"
                    f".dc Vo {vcc - vds_top} {vcc} 0.01")
    v = vcc - r["v-sweep"]
    return v[::-1], r["vo#branch"][::-1]


def at(xs: np.ndarray, ys: np.ndarray, x: float) -> float:
    return float(np.interp(x, xs, ys))


def vtc(p: dict[str, float], vcc: float, step: float = 0.001, load: str = "") -> tuple[np.ndarray, np.ndarray]:
    """Output voltage against input, no load (or `load`, netlist lines on node o)."""
    [r] = _plots(p, f"Vdd vdd 0 {vcc}\nVin in 0 0\nX1 in o vdd 0 CD4049UB_INV\n{load}\n"
                    f".dc Vin 0 {vcc} {step}")
    return r["v-sweep"], r["o"]


def switch_point(vi: np.ndarray, vo: np.ndarray) -> float:
    """VI where VO = VI."""
    d = vo - vi
    k = int(np.nonzero(d <= 0)[0][0])
    return float(vi[k - 1] + d[k - 1] / (d[k - 1] - d[k]) * (vi[k] - vi[k - 1]))


def gain_ac(p: dict[str, float], vcc: float) -> tuple[float, float]:
    """(small-signal gain |dVO/dVI| at VO = VI, that voltage): open loop, no load, an AC run
    at 1 kHz biased at the switching point."""
    vi, vo = vtc(p, vcc, 0.0005)
    vs = switch_point(vi, vo)
    res = ENGINE.run(f"inv\n{subckt(p)}\nVdd vdd 0 {vcc}\nVin in 0 dc {vs:.6f} ac 1\n"
                     f"X1 in o vdd 0 CD4049UB_INV\n.ac lin 1 1k 1k\n.end\n")
    return float(abs(res.plot("ac").vectors["o"][0])), vs


def slope_30_70(vi: np.ndarray, vo: np.ndarray, vcc: float) -> float:
    """Average |dVO/dVI| between VO = 70 % and 30 % of VCC (as read off the drawn figure)."""
    hi = at(vo[::-1], vi[::-1], 0.7 * vcc)
    lo = at(vo[::-1], vi[::-1], 0.3 * vcc)
    return 0.4 * vcc / (lo - hi)


def tran(p: dict[str, float], vcc: float, rising_in: bool) -> dict[str, float]:
    """The sheet's AC test (p. 11): input edge 0<->VCC in 20 ns, CL 50 pF, RL 200 kΩ (to VSS).
    Returns tp (50 % in to 50 % out) and tt (10-90 % of the output), in ns."""
    a, b = (0, vcc) if rising_in else (vcc, 0)
    res = ENGINE.run(f"inv\n{subckt(p)}\nVdd vdd 0 {vcc}\n"
                     f"Vin in 0 PULSE({a} {b} 50n 20n 20n 1u 2u)\nX1 in o vdd 0 CD4049UB_INV\n"
                     f"CL o 0 50p\nRL o 0 200k\n.tran 0.05n 400n 0 0.05n\n.end\n")
    v = res.plot("tran").vectors
    t, vin, vo = (np.asarray(v[k].real) for k in ("time", "in", "o"))

    def cross(y: np.ndarray, level: float, up: bool) -> float:
        s = y - level
        idx = np.nonzero((s[:-1] < 0) & (s[1:] >= 0) if up else (s[:-1] > 0) & (s[1:] <= 0))[0]
        k = int(idx[0])
        return float(t[k] + (level - y[k]) / (y[k + 1] - y[k]) * (t[k + 1] - t[k]))

    out_up = not rising_in
    t_in = cross(vin, vcc / 2, rising_in)
    t_out = cross(vo, vcc / 2, out_up)
    t10 = cross(vo, 0.1 * vcc if out_up else 0.9 * vcc, out_up)
    t90 = cross(vo, 0.9 * vcc if out_up else 0.1 * vcc, out_up)
    return {"tp": (t_out - t_in) * 1e9, "tt": (t90 - t10) * 1e9}


def cin(p: dict[str, float], vcc: float, vin: float) -> float:
    """Input capacitance (F) at 100 kHz with the input held at `vin` (the output at a rail)."""
    res = ENGINE.run(f"inv\n{subckt(p)}\nVdd vdd 0 {vcc}\nVin in 0 dc {vin} ac 1\n"
                     f"X1 in o vdd 0 CD4049UB_INV\n.ac lin 1 100k 100k\n.end\n")
    i = res.plot("ac").vectors["vin#branch"][0]
    return float(abs(i)) / (2 * math.pi * 1e5)


def supply_current(p: dict[str, float], vcc: float, vin: float) -> float:
    """Quiescent current (A) from VDD with the input at `vin`, no load."""
    [r] = _plots(p, f"Vdd vdd 0 {vcc}\nVin in 0 {vin}\nX1 in o vdd 0 CD4049UB_INV\n"
                    f".dc Vdd {vcc} {vcc} 1")
    return float(-r["vdd#branch"][0])


def input_current(p: dict[str, float], vcc: float, vin: float) -> float:
    [r] = _plots(p, f"Vdd vdd 0 {vcc}\nVin in 0 {vin}\nX1 in o vdd 0 CD4049UB_INV\n"
                    f".dc Vin {vin} {vin} 1")
    return float(-r["vin#branch"][0])


def power(p: dict[str, float], vcc: float, cl: float, f: float, edge: float = 20e-9) -> float:
    """Average supply power (W) driving a square wave 0..VCC at f into CL (Figure 5-9's test,
    Figure 6-5): measured over the second period. The sheet doesn't state the input edges;
    `edge` defaults to the AC table's 20 ns."""
    per = 1 / f
    res = ENGINE.run(f"inv\n{subckt(p)}\nVdd vdd 0 {vcc}\n"
                     f"Vin in 0 PULSE(0 {vcc} 0 {edge} {edge} {per / 2 - edge} {per})\n"
                     f"X1 in o vdd 0 CD4049UB_INV\nCL o 0 {cl}\n"
                     f".tran {per / 4000} {2 * per} 0 {per / 4000}\n.end\n")
    v = res.plot("tran").vectors
    t, i = np.asarray(v["time"].real), -np.asarray(v["vdd#branch"].real)
    m = t >= per
    return float(vcc * np.trapezoid(i[m], t[m]) / (t[m][-1] - t[m][0]))


def rout(p: dict[str, float], vcc: float, vin: float) -> float:
    """Small-signal output resistance (Ω) with the input held at `vin` (1 A AC into OUT)."""
    res = ENGINE.run(f"inv\n{subckt(p)}\nVdd vdd 0 {vcc}\nVin in 0 dc {vin}\n"
                     f"X1 in o vdd 0 CD4049UB_INV\nIo 0 o dc 0 ac 1\n.ac lin 1 1k 1k\n.end\n")
    return float(abs(res.plot("ac").vectors["o"][0]))
