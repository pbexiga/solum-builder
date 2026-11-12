"""Fit our own SPICE models to datasheet curves, the last resort of D-156.

Used only where every published card is off limits or none exists. The fitted record
keeps its points and method (`ModelInfo.fit`), so a fit can be repeated from them.

Diode: the forward curve V = N·Vt·ln(I/IS) + RS·I is linear in (N·Vt, N·Vt·ln IS, RS),
so a least-squares solve gives IS, N and RS directly; Vt is taken at ngspice's 27 °C, so
the simulation lands on the sheet's curve.
"""

import dataclasses
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

BOLTZMANN = 1.380649e-23
CHARGE = 1.602176634e-19
SIM_TEMP_C = 27.0  # ngspice's default TEMP and TNOM
N_MIN = 1.0  # a junction's emission coefficient is never below 1
IS_MIN = 1e-26  # ngspice raises a smaller IS to its floor (CKTepsmin, 1e-28) without saying


def thermal_voltage(temp_c: float = SIM_TEMP_C) -> float:
    return BOLTZMANN * (temp_c + 273.15) / CHARGE


@dataclass(frozen=True)
class DiodeFit:
    is_: float  # saturation current, A
    n: float  # emission coefficient
    rs: float  # series resistance, ohms

    def volts(self, amps: float, temp_c: float = SIM_TEMP_C) -> float:
        """The fitted forward voltage at `amps`."""
        return self.n * thermal_voltage(temp_c) * math.log(amps / self.is_ + 1) + self.rs * amps

    def amps(self, volts: float, temp_c: float = SIM_TEMP_C) -> float:
        """The forward current at `volts` (the inverse of `volts`)."""
        return _inverse(lambda i: self.volts(i, temp_c), volts)


@dataclass(frozen=True)
class DiodePair:
    """Two diodes in parallel: `low` follows the curve at small currents, `high` adds the
    current the sheet's curve gains above them (a curve one diode can't follow, D-159)."""

    low: DiodeFit
    high: DiodeFit

    def volts(self, amps: float, temp_c: float = SIM_TEMP_C) -> float:
        return _inverse(lambda v: self.low.amps(v, temp_c) + self.high.amps(v, temp_c), amps)


def _inverse(f: Callable[[float], float], target: float) -> float:
    """x with f(x) = target for a rising f, by bisection on a log scale (x from 1e-18 to 10)."""
    lo, hi = -18.0 * math.log(10), math.log(10.0)
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(math.exp(mid)) < target:
            lo = mid
        else:
            hi = mid
    return math.exp((lo + hi) / 2)


def fit_diode(
    points: list[tuple[float, float]], temp_c: float = SIM_TEMP_C, is_max: float | None = None
) -> DiodeFit:
    """IS, N, RS from forward-curve points [(volts, amps), ...] (at least three).

    `is_max`: the most IS may be, usually the sheet's maximum reverse current (IS is the
    model's reverse current), so a soft forward curve can't make the part leak more."""
    if len(points) < 3:
        raise ValueError("a diode fit needs at least three points")
    v = np.array([p[0] for p in points])
    i = np.array([p[1] for p in points])
    if (i <= 0).any():
        raise ValueError("forward currents must be above zero")
    order = np.argsort(i)
    if (np.diff(v[order]) <= 0).any():
        raise ValueError("the points don't rise with current")
    a_mat = np.column_stack([np.log(i), np.ones_like(i), i])
    (slope, offset, rs), *_ = np.linalg.lstsq(a_mat, v, rcond=None)
    if rs < 0:  # no series resistance shows in these points: fit the exponential alone
        (slope, offset), *_ = np.linalg.lstsq(a_mat[:, :2], v, rcond=None)
        rs = 0.0
    vt = thermal_voltage(temp_c)
    if slope / vt < N_MIN:  # unphysical: hold N at its floor and fit IS and RS alone
        slope = N_MIN * vt
        (offset, rs), *_ = np.linalg.lstsq(a_mat[:, 1:], v - slope * np.log(i), rcond=None)
        rs = max(float(rs), 0.0)
    is_ = math.exp(-offset / slope)
    if is_ < IS_MIN:  # ngspice would raise it to its floor
        return _with_is(IS_MIN, i, v, vt)
    if is_max is not None and is_ > is_max:
        return _with_is(is_max, i, v, vt)
    return DiodeFit(is_=is_, n=float(slope / vt), rs=float(rs))


def _with_is(is_: float, i: np.ndarray, v: np.ndarray, vt: float) -> DiodeFit:
    """N and RS by least squares with IS pinned."""
    (slope, rs), *_ = np.linalg.lstsq(np.column_stack([np.log(i / is_), i]), v, rcond=None)
    return DiodeFit(is_=is_, n=float(slope / vt), rs=max(float(rs), 0.0))


def diode_card(name: str, fit: DiodeFit, **extra: float) -> str:
    """A `.model` line for the fit, with extra params (CJO, BV, IBV, EG...)."""
    params = {"is": fit.is_, "n": fit.n, "rs": fit.rs, **extra}
    body = " ".join(f"{k}={v:.4g}" for k, v in params.items())
    return f".model {name} D({body})\n"


def fit_diode_pair(
    points: list[tuple[float, float]], split: float, is_max: float | None = None
) -> DiodePair:
    """`low` fitted to the points up to `split` amps; `high` to the current the points above
    it carry beyond `low` at the same voltage. `is_max` caps both IS (their sum is the
    reverse current)."""
    low = fit_diode([p for p in points if p[1] <= split], is_max=is_max)
    extra = [(v, i - low.amps(v)) for v, i in points if i > split]
    if len([e for e in extra if e[1] > 0]) < 3:
        raise ValueError("fewer than three points above the split carry current beyond one diode")
    return DiodePair(low=low, high=fit_diode([e for e in extra if e[1] > 0], is_max=is_max))


def diode_pair_card(name: str, pair: DiodePair, **extra: float) -> str:
    """A two-pin subcircuit (1 anode, 2 cathode) of the pair; extras go on `low`."""
    low = diode_card(f"{name}_low", pair.low, **extra).strip()
    high = diode_card(f"{name}_high", pair.high).strip()
    return (
        f".subckt {name} 1 2\n*        A K\nD1 1 2 {name}_low\nD2 1 2 {name}_high\n"
        f"{low}\n{high}\n.ends\n"
    )


def middle(lo: float, hi: float) -> float:
    """The geometric middle of a datasheet range (same sign as its ends): a JFET's Idss
    and cut-off spread over decades, so a typical unit sits nearer the low end (D-161)."""
    if lo * hi <= 0:
        raise ValueError("a range's ends must have the same sign")
    return math.copysign(math.sqrt(lo * hi), lo)


def jfet_vp(vgs: float, id_: float, idss: float) -> float:
    """Cut-off voltage from a sheet's gate voltage at a drain current, for a unit with
    `idss` (square law: ID = Idss·(1 − VGS/Vp)²)."""
    if not 0 < id_ < idss:
        raise ValueError("the drain current must be between zero and Idss")
    return vgs / (1 - math.sqrt(id_ / idss))


@dataclass(frozen=True)
class JfetFit:
    """A level-1 JFET from its sheet: Idss (A) and Vp (V, negative for N-channel), with
    the output conductance's λ and the capacitances where the sheet gives them."""

    idss: float
    vp: float
    lam: float = 0.0
    cgs: float = 0.0
    cgd: float = 0.0

    @property
    def beta(self) -> float:
        return self.idss / self.vp**2


def jfet_card(name: str, fit: JfetFit, channel: str = "NJF") -> str:
    """A `.model` line: VTO, BETA and the optional LAMBDA, CGS, CGD."""
    params = {"vto": fit.vp, "beta": fit.beta, "lambda": fit.lam, "cgs": fit.cgs, "cgd": fit.cgd}
    body = " ".join(f"{k}={v:.4g}" for k, v in params.items() if v or k in ("vto", "beta"))
    return f".model {name} {channel}({body})\n"


@dataclass(frozen=True)
class OpAmpFit:
    """An op-amp channel from its sheet's typical figures (D-162).

    aol_db: open-loop gain; gbw: gain-bandwidth (Hz); slew: V/s; phase_margin: degrees at
    unity gain (sets a second pole); rout: output resistance (Ω), with head_pos/head_neg
    the output's distance from each rail at no load (V); iq: quiescent supply current (A);
    rin: differential input resistance (Ω)."""

    aol_db: float
    gbw: float
    slew: float
    phase_margin: float
    rout: float
    head_pos: float
    head_neg: float
    iq: float
    rin: float = 1e12

    IMAX = 10e-6  # the gain stage's current limit, A: sets the scale of C1, R1 and gm

    @property
    def c1(self) -> float:
        return self.IMAX / self.slew  # slew = Imax / C1

    @property
    def gm(self) -> float:
        """GBW = gm / (2π·C1), raised by 1/cos(90° − PM) so the gain still crosses 1 at
        `gbw` with the second pole in."""
        return 2 * math.pi * self.gbw * self.c1 / math.cos(math.radians(90 - self.phase_margin))

    @property
    def r1(self) -> float:
        return 10 ** (self.aol_db / 20) / self.gm  # Aol = gm·R1

    @property
    def second_pole(self) -> float:
        """Hz: where a pole leaves `phase_margin` at the unity-gain frequency."""
        return self.gbw / math.tan(math.radians(90 - self.phase_margin))


def opamp_card(name: str, fit: OpAmpFit) -> str:
    """A five-pin subcircuit (1 +, 2 −, 3 V+, 4 V−, 5 out): a slew-limited
    transconductance into R1‖C1 (gain, bandwidth, slew), clamped short of the rails, a
    second pole, then an output resistance; the output current is drawn from the rail
    it would come from, and the quiescent current flows rail to rail."""
    rp = 1e3
    cp = 1 / (2 * math.pi * rp * fit.second_pole)
    g = lambda x: f"{x:.6g}"  # noqa: E731
    return "\n".join(
        [
            f".subckt {name} 1 2 3 4 5",
            "* pins: + - V+ V- out. Built by Solum Builder from the sheet's typical figures "
            "(D-162)",
            f"Rin 1 2 {g(fit.rin)}",
            "Rc1 1 mid 1e12",
            "Rc2 2 mid 1e12",
            "Emid mid 4 3 4 0.5",
            f"Bgm mid g I={g(fit.IMAX)}*tanh({g(fit.gm / fit.IMAX)}*(V(1)-V(2)))",
            f"R1 g mid {g(fit.r1)}",
            f"C1 g mid {g(fit.c1)}",
            f"Vhp 3 hp DC {g(fit.head_pos)}",
            f"Vhn hn 4 DC {g(fit.head_neg)}",
            "Dhi g hp DCLAMP",
            "Dlo hn g DCLAMP",
            "Ebuf b 0 g 0 1",
            f"Rp b p {g(rp)}",
            f"Cp p 0 {g(cp)}",
            "Eout o 0 p 0 1",
            "Vsense o o2 0",
            f"Rout o2 5 {g(fit.rout)}",
            "Bsrc 3 0 I=max(i(Vsense),0)",
            "Bsnk 0 4 I=max(-i(Vsense),0)",
            f"Iq 3 4 DC {g(fit.iq)}",
            ".model DCLAMP D(is=1e-15 n=0.05)",
            ".ends",
            "",
        ]
    )


@dataclass(frozen=True)
class GummelPoon:
    """Gummel-Poon parameters (ngspice's names, magnitudes for a PNP) fitted to a sheet's
    typical curves (D-163). VAR is left at ngspice's default (∞): the sheets show the
    forward region and saturation, not reverse operation. RB only where a sheet gives
    rbb' (D-170)."""

    is_: float  # transport saturation current, A
    nf: float  # forward emission coefficient
    bf: float  # ideal forward beta
    ise: float  # base-emitter leakage saturation current, A (beta's fall at low current)
    ne: float  # its emission coefficient
    ikf: float  # forward knee current, A (beta's fall at high current)
    vaf: float  # forward Early voltage, V
    re: float = 0.0
    rc: float = 0.0
    br: float = 1.0  # ideal reverse beta
    isc: float = 0.0  # base-collector leakage saturation current, A (VCE(sat) at low current)
    nc: float = 2.0
    cje: float = 0.0
    vje: float = 0.75
    mje: float = 0.33
    cjc: float = 0.0
    vjc: float = 0.75
    mjc: float = 0.33
    tf: float = 0.0
    nkf: float = 0.5  # the knee's roll-off exponent (ngspice's NKF; 0.5 is classic Gummel-Poon)
    nr: float = 1.0  # reverse emission coefficient (the collector junction's NF)
    rb: float = 0.0  # base resistance, Ω (a sheet's rbb')

    def currents(self, vbe: float, vbc: float, temp_c: float = SIM_TEMP_C) -> tuple[float, float]:
        """Collector and base current (A) at the inner junction voltages, as ngspice's
        bjtload computes them (its gmin terms left out)."""
        vt = thermal_voltage(temp_c)
        cbe = self.is_ * _expm1(vbe / (self.nf * vt))
        cbc = self.is_ * _expm1(vbc / (self.nr * vt))
        q1 = 1 / (1 - vbc / self.vaf)
        qb = q1 * (1 + max(0.0, 1 + 4 * cbe / self.ikf) ** self.nkf) / 2
        cbcn = self.isc * _expm1(vbc / (self.nc * vt))
        ib = cbe / self.bf + self.ise * _expm1(vbe / (self.ne * vt)) + cbc / self.br + cbcn
        return (cbe - cbc) / qb - cbc / self.br - cbcn, ib

    def forward(self, ic: float, vce: float | None) -> tuple[float, float]:
        """(VBE at the terminals, hFE) with `ic` flowing at `vce`, or with the collector
        tied to the base (None: old sheets' "VCB = 0", where no collector leakage flows).
        IC is known, so the RC and RE drops are too, bar the small base current: a few
        rounds settle it. VBE is the first that carries `ic`: a germanium card's IC turns
        over at junction voltages a silicon card never reaches (IS 1e8 times larger)."""
        vbe = ib = 0.0
        for _ in range(4):
            if vce is None:
                vbc = ic * self.rc - ib * self.rb
                vbe = _bisect(lambda v, vbc=vbc: self.currents(v, vbc)[0], ic, 0.0, 1.5, 0.05)
                ib = self.currents(vbe, vbc)[1]
            else:
                inner = vce - ic * self.rc - (ic + ib) * self.re
                vbe = _bisect(
                    lambda v, inner=inner: self.currents(v, v - inner)[0], ic, 0.0, 1.5, 0.05
                )
                ib = self.currents(vbe, vbe - inner)[1]
        return vbe + (ic + ib) * self.re + ib * self.rb, ic / ib

    def icbo(self, vcb: float) -> float:
        """Collector-base leakage (A) with the emitter open and `vcb` reverse across:
        the emitter junction floats to where its current cancels the collector's."""
        vbc = -vcb
        vbe = _bisect(lambda v: sum(self.currents(v, vbc)), 0.0, -1.0, 0.5)
        return self.currents(vbe, vbc)[0]

    def iebo(self, veb: float) -> float:
        """Emitter-base leakage (A) with the collector open and `veb` reverse across: the
        collector junction floats to where the collector current is zero."""
        vbe = -veb
        vbc = _bisect(lambda v: self.currents(vbe, v)[0], 0.0, -1.0, 0.5)
        return -self.currents(vbe, vbc)[1]

    def saturated(self, ic: float, ib: float) -> tuple[float, float]:
        """(VBE, VCE) at the terminals with `ib` driven in and `ic` drawn out (forced beta
        ic/ib < hFE): the sheets' VBE(sat) and VCE(sat)."""
        vbe, vbc = self._junctions(ic, ib) or self._junctions_nested(ic, ib)
        drop_e = (ic + ib) * self.re
        return vbe + ib * self.rb + drop_e, vbe - vbc + ic * self.rc + drop_e

    def _junctions(self, ic: float, ib: float) -> tuple[float, float] | None:
        """The inner (VBE, VBC) carrying `ic` and `ib`, by Newton's method on both at once
        (a finite-difference Jacobian; each step held to 50 mV, as the junctions'
        exponentials need). None if it hasn't settled to `ROOT_TOLERANCE` in 60 steps:
        `_junctions_nested` then finds it the slow, sure way. Some 40 times fewer calls of
        `currents` than the nested search (Phase 10, D-274)."""
        if ic <= 0 or ib <= 0:
            return None
        vt = thermal_voltage()
        vbe = min(self.nf * vt * math.log1p(ic / self.is_), 1.2)
        vbc = vbe - 0.1
        h = 1e-7
        for _ in range(60):
            c0, b0 = self.currents(vbe, vbc)
            c1, b1 = self.currents(vbe + h, vbc)
            c2, b2 = self.currents(vbe, vbc + h)
            # relative residuals: the two currents differ by the forced beta
            f0, g0 = (c0 - ic) / ic, (b0 - ib) / ib
            fe, fc = (c1 - c0) / (h * ic), (c2 - c0) / (h * ic)
            ge, gc = (b1 - b0) / (h * ib), (b2 - b0) / (h * ib)
            det = fe * gc - fc * ge
            if det == 0 or not math.isfinite(det):
                return None
            de, dc = (-f0 * gc + g0 * fc) / det, (-g0 * fe + f0 * ge) / det
            big = max(abs(de), abs(dc))
            scale = min(1.0, 0.05 / big) if big else 1.0
            vbe, vbc = vbe + scale * de, vbc + scale * dc
            if not (-1.0 < vbe < 2.0 and -3.0 < vbc < 2.0):
                return None
            if big < ROOT_TOLERANCE / 10:
                return vbe, vbc
        return None

    def _junctions_nested(self, ic: float, ib: float) -> tuple[float, float]:
        def vbc_for(vbe: float) -> float:  # ic falls as the collector junction turns on
            return _bisect(lambda v: -self.currents(vbe, v)[0], -ic, vbe - 2.0, vbe + 0.2)

        vbe = _bisect(lambda v: self.currents(v, vbc_for(v))[1], ib, -0.2, 1.5)
        return vbe, vbc_for(vbe)

    def vce_sat(self, ic: float, ib: float) -> float:
        """VCE with `ib` driven in and `ic` drawn out (forced beta ic/ib < hFE)."""
        return self.saturated(ic, ib)[1]


def least_squares(
    residuals: Callable[[np.ndarray], list[float]],
    x0: list[float],
    lo: list[float],
    hi: list[float],
    steps: int = 200,
) -> list[float]:
    """x within [lo, hi] minimising the sum of squared residuals: Levenberg-Marquardt with
    a forward-difference Jacobian, each step clipped to the bounds (numpy only; scipy
    isn't a dependency)."""
    low, high = np.array(lo, dtype=float), np.array(hi, dtype=float)
    x = np.clip(np.array(x0, dtype=float), low, high)
    r = np.array(residuals(x))
    damping = 1e-3
    for _ in range(steps):
        jac = np.empty((len(r), len(x)))
        for k in range(len(x)):
            h = 1e-4 * max(1.0, abs(x[k]))
            step = x.copy()
            step[k] = step[k] + h if step[k] + h <= high[k] else step[k] - h
            jac[:, k] = (np.array(residuals(step)) - r) / (step[k] - x[k])
        a_mat, g = jac.T @ jac, jac.T @ r
        while True:
            trial = np.clip(
                x - np.linalg.solve(a_mat + damping * np.diag(np.diag(a_mat) + 1e-12), g), low, high
            )
            r_trial = np.array(residuals(trial))
            if r_trial @ r_trial < r @ r:
                done = (r @ r - r_trial @ r_trial) < 1e-10 * (r @ r) + 1e-14
                x, r, damping = trial, r_trial, max(damping / 3, 1e-9)
                break
            damping *= 4
            if damping > 1e8:
                return [float(v) for v in x]
        if done:
            break
    return [float(v) for v in x]


ROOT_TOLERANCE = 1e-12  # volts: `_bisect`'s answer is this close


def _expm1(x: float) -> float:
    """exp(x) - 1, held below overflow (a search may try absurd junction voltages)."""
    return math.expm1(min(x, 200.0))


def _bisect(
    f: Callable[[float], float], target: float, lo: float, hi: float, step: float = 0.0
) -> float:
    """x in [lo, hi] with f(x) = target for a rising f, to 1 pV (junction voltages: fine
    enough that a fit's finite differences see the model, not the search). With `step`,
    the first crossing, bracketed in steps of that size first: for an f that rises, then
    turns over (a germanium card's collector current, past ~0.6 V). An f that never
    reaches the target gives `hi`, one always past it `lo`. The root is found by Brent's
    method (bisection that takes a secant or quadratic step when one lands inside the
    bracket): 3-4 times fewer calls of f than plain halving (Phase 10, D-274)."""
    while step and lo + step < hi and f(lo + step) < target:
        lo += step
    hi = min(hi, lo + step) if step else hi
    a, b = lo, hi
    fa, fb = f(a) - target, f(b) - target
    if fa >= 0:
        return lo
    if fb < 0:
        return hi
    c, fc = a, fa
    d = e = b - a
    while True:
        if abs(fc) < abs(fb):
            a, b, c = b, c, b
            fa, fb, fc = fb, fc, fb
        tol = 4e-16 * abs(b) + ROOT_TOLERANCE / 2
        half = (c - b) / 2
        if abs(half) <= tol or fb == 0:
            return b
        if abs(e) >= tol and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p, q = 2 * half * s, 1 - s
            else:
                q, r = fa / fc, fb / fc
                p = s * (2 * half * q * (q - r) - (b - a) * (r - 1))
                q = (q - 1) * (r - 1) * (s - 1)
            q = -q if p > 0 else q
            p = abs(p)
            if 2 * p < min(3 * half * q - abs(tol * q), abs(e * q)):
                e, d = d, p / q
            else:
                d = e = half
        else:
            d = e = half
        a, fa = b, fb
        b += d if abs(d) > tol else math.copysign(tol, half)
        fb = f(b) - target
        if (fb > 0) == (fc > 0):
            c, fc = a, fa
            d = e = b - a


def fit_bjt_forward(
    hfe: list[tuple[float, float]],
    vbe: list[tuple[float, float]],
    vce: float | None,
    vaf: float,
    rb: float = 0.0,
    is_max: float = 1e-11,
    icbo: tuple[float, float] | None = None,
) -> GummelPoon:
    """IS, NF, BF, ISE, NE, IKF, NKF and RE by least squares on a typical hFE curve
    [(ic, hfe), ...] and VBE(on) curve [(ic, vbe), ...], both at `vce` (None: VCB = 0, see
    `GummelPoon.forward`), with the Early
    voltage `vaf` given (from the sheet's output admittance) and RB if the sheet gives
    rbb'. hFE is weighed in 1 % steps and VBE in 2 mV steps. IS may reach `is_max`, ISE a
    hundred times that (silicon's 1e-11 A; germanium's IS is microamps, D-170).

    `icbo` (amps, at reverse volts) fits BR too, NR = NF as in `fit_bjt_saturation`, for
    a sheet with a leakage figure and no VCE(sat) curve (germanium, D-170): IS alone
    would leak far more than such a sheet allows, and the emitter junction's ISE leaks
    when it floats, so the leakage is fitted with the gain, not after it."""
    if len(hfe) < 3 or len(vbe) < 3:
        raise ValueError("a BJT fit needs at least three hFE and three VBE points")
    start = fit_diode([(v, i) for i, v in vbe])
    x0 = [math.log10(start.is_), min(max(start.n, 1.0), 2.0),
          math.log10(max(h for _, h in hfe)), math.log10(start.is_), 1.5,
          math.log10(max(i for i, _ in hfe + vbe)), min(start.rs, 10.0), 0.5]  # fmt: skip

    def made(x: np.ndarray) -> GummelPoon:
        made = GummelPoon(is_=10 ** x[0], nf=x[1], bf=10 ** x[2], ise=10 ** x[3], ne=x[4],
                          ikf=10 ** x[5], vaf=vaf, re=x[6], nkf=x[7], rb=rb)  # fmt: skip
        return made if icbo is None else dataclasses.replace(made, br=10 ** x[8], nr=x[1])

    def residuals(x: np.ndarray) -> list[float]:
        f = made(x)
        r = [math.log(max(f.forward(i, vce)[1], 1e-3) / h) / 0.01 for i, h in hfe]
        r += [(f.forward(i, vce)[0] - v) / 2e-3 for i, v in vbe]
        return r if icbo is None else [*r, math.log(max(f.icbo(icbo[1]), 1e-30) / icbo[0]) / 0.01]

    lo = [-18.0, 1.0, 1.0, -20.0, 1.05, -4.0, 0.0, 0.3]
    top = math.log10(is_max)
    hi = [top, 2.0, 3.5, top + 2, 4.0, 1.0, 10.0, 1.0]  # near NKF 1, IC levels off near IKF/2
    if icbo is not None:  # BR 0.01 to 10^4
        x0, lo, hi = [*x0, 1.0], [*lo, -2.0], [*hi, 4.0]
    x0 = [min(v, h - 1e-6) for v, h in zip(x0, hi, strict=True)]
    x = least_squares(residuals, x0, lo, hi)
    return _floored(made(x), x[3] <= lo[3] + 0.01, "ise")


def fit_bjt_saturation(
    fit: GummelPoon,
    points: list[tuple[float, float]],
    forced: float,
    hfe: list[tuple[float, float]] | None = None,
    vce: float = 0.0,
    isc_max: float = 1e-8,
) -> GummelPoon:
    """BR, RC, ISC and NC by least squares on a VCE(sat) curve [(ic, vce), ...] taken at
    ic/ib = `forced` (2 mV steps): ISC's leakage lifts VCE(sat) at low current, RC at
    high. The forward fit's hFE points [(ic, hfe), ...] at `vce`, if given, are held in
    1 % steps: ISC's leakage also adds to the base current, so a large ISC can meet the
    VCE(sat) curve and wreck a high-gain part's hFE at low current. NR is set to NF: both
    junctions come from one process, and with NR held at 1 a part with NF 1.2 sits a tenth
    of a volt high in VCE(sat) whatever else is fitted (fitted freely, NR trades off
    against ISC, NC and BR and isn't pinned). `isc_max` caps ISC where the curve can't
    choose it (the 2SC1815: 10 nA of leakage at the 1e-8 bound or 3 pA fit it about as
    well, D-187)."""

    def made(x: np.ndarray) -> GummelPoon:
        return dataclasses.replace(fit, br=10 ** x[0], rc=x[1], isc=10 ** x[2], nc=x[3], nr=fit.nf)

    def residuals(x: np.ndarray) -> list[float]:
        f = made(x)
        r = [(f.vce_sat(i, i / forced) - v) / 2e-3 for i, v in points]
        return r + [math.log(max(f.forward(i, vce)[1], 1e-3) / h) / 0.01 for i, h in hfe or []]

    top = math.log10(isc_max)
    x0 = [0.0, 1.0, min(math.log10(fit.ise or fit.is_), top), 1.5]
    x = least_squares(residuals, x0, [-2.0, 0.0, -20.0, 1.05], [2.0, 50.0, top, 4.0])
    return _floored(made(x), x[2] <= -20.0 + 0.01, "isc")


def _floored(fit: GummelPoon, floored: bool, term: str) -> GummelPoon:
    """`fit` with a leakage term the fit drove to its floor set to 0: the curve doesn't
    need it, and a 1e-20 with its exponent at a bound reads as if it meant something."""
    return dataclasses.replace(fit, **{term: 0.0}) if floored else fit


def fit_junction_cap(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """(CJ0, VJ, M) of C = CJ0 / (1 + V/VJ)^M from [(reverse volts, farads), ...], by
    least squares on log C (VJ 0.3 to 1.2 V, M 0.2 to 0.7). One point can't pin VJ and M:
    it sets CJ0 with ngspice's defaults (0.75 V, 0.33)."""
    if len(points) == 1:
        ((volts, farads),) = points
        return farads * (1 + volts / 0.75) ** 0.33, 0.75, 0.33
    v = np.array([p[0] for p in points])
    c = np.array([p[1] for p in points])

    def residuals(x: np.ndarray) -> list[float]:
        return list(np.log(10 ** x[0] / (1 + v / x[1]) ** x[2] / c) / 0.01)

    top = math.log10(float(c.max()))
    x = least_squares(residuals, [top, 0.75, 0.33], [top - 1, 0.3, 0.2], [top + 1, 1.2, 0.7])
    return 10 ** x[0], x[1], x[2]


def bjt_tf(fit: GummelPoon, ft: float, ic: float, vcb: float) -> float:
    """Forward transit time from the sheet's fT at `ic` and `vcb`: 1/(2π·fT) less the
    time the junction capacitances take to charge through 1/gm. The emitter junction is
    forward biased, where SPICE's capacitance is about twice CJE (FC 0.5)."""
    cjc = fit.cjc / (1 + vcb / fit.vjc) ** fit.mjc
    charge = (2 * fit.cje + cjc) * fit.nf * thermal_voltage() / ic
    return max(1 / (2 * math.pi * ft) - charge, 0.0)


def bjt_card(name: str, fit: GummelPoon, polarity: str = "NPN", **extra: float) -> str:
    """A `.model` line with every fitted parameter (zeros, and a VAF of inf, left out:
    ngspice's defaults), then any extra params (germanium's EG)."""
    params = {"is": fit.is_, "nf": fit.nf, "bf": fit.bf, "ise": fit.ise,
              "ne": fit.ne if fit.ise else 0.0,
              "ikf": fit.ikf, "vaf": fit.vaf, "br": fit.br, "isc": fit.isc,
              "nc": fit.nc if fit.isc else 0.0, "re": fit.re, "rc": fit.rc,
              "cje": fit.cje, "vje": fit.vje, "mje": fit.mje, "cjc": fit.cjc,
              "vjc": fit.vjc, "mjc": fit.mjc, "tf": fit.tf,
              "nkf": fit.nkf if fit.nkf != 0.5 else 0.0,
              "nr": fit.nr if fit.nr != 1.0 else 0.0, "rb": fit.rb, **extra}  # fmt: skip
    body = " ".join(f"{k}={v:.4g}" for k, v in params.items() if v and math.isfinite(v))
    return f".model {name} {polarity}({body})\n"
