"""Build our CA3080 and LM13700 OTA models from their sheets (behavioural core, real
ngspice junctions where the sheet's behaviour is a junction's).

Writes .claude/skills/fit-model/worked/ota/CA3080.lib and LM13700.lib and prints the fitted values.
Run in the dev container (numpy):
  podman run --rm -v "$PWD":/src:z -w /src -e PYTHONPATH=/src -e HOME=/tmp \
      solum-builder:dev python .claude/skills/fit-model/worked/ota/build_ota.py

Sheets: CA3080 = Intersil CA3080/CA3080A data sheet, File Number 475.4 (Sept 1998),
data/spec-sheets/CA3080_Intersil.pdf. LM13700 = TI SNOSBW2F (Nov 1999, rev Nov 2015),
data/spec-sheets/LM13700_TI_SNOSBW2F.pdf. Every number below names its source.

Core (one amplifier), the sheet's own circuit description (TI 7.3.1, eq. 1-5):
  I5 = Iabc*(1+t)/2, I4 = Iabc*(1-t)/2, t = tanh(Vd/2VT)  (Vd through the 2 MHz pole)
  Iout = I5*fp*(1+(vp-out)/VA) - I4*fn*(1+(out-vn)/VA)
 - Iabc is the current into the bias pin, sensed through the pin's junction to V-.
 - fp, fn: the output devices saturate as out comes within Hp of V+ / Hn of V-:
   f(x) = u^2/(u^2+VS^2), u = max(x, 0)  (zero beyond the limit, smooth at it).
 - VA (Early) sets the output resistance Rout = VA/Iabc at balance.
 - w: the input pair works only inside the common-mode range (same f on each side).
 - Base currents I5/beta and I4/beta are drawn by the inputs (bias current and, with it,
   the input resistance 2VT/Ib: Ib*Rin = 2VT is the diff pair's own relation).
 - Supply: I5 path from V+, I4 path to V-, plus (k-0.5)*Iabc V+ to V-, so the V+
   current at balance is k*Iabc (the sheet's supply current).
"""
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
VT25 = 8.617333e-5 * 298.15  # thermal voltage at the sheets' 25 degC (fitting only)
VS_KNEE = 0.05  # V: width of the output/CMR saturation knee (judgement: no sheet figure)


def fit_junction(points, n_junctions=1):
    """Least squares V = N*VT*ln(I/IS) + RS*I (linear in N*VT, N*VT*ln IS, RS).
    points: [(I amps, V volts)]. Returns IS, N (for one ngspice diode), RS."""
    i = np.array([p[0] for p in points]); v = np.array([p[1] for p in points])
    a = np.vstack([np.log(i), np.ones_like(i), i]).T
    (nvt, b, rs), *_ = np.linalg.lstsq(a, v, rcond=None)
    if rs < 0:  # the points bend the other way: no series resistance, refit without it
        (nvt, b), *_ = np.linalg.lstsq(a[:, :2], v, rcond=None)
        rs = 0.0
    n = nvt / VT25
    is_ = math.exp(-b / nvt)
    return is_, n, rs


def fit_loglog(points, deg):
    """log10(y) as a polynomial of log10(x)."""
    x = np.log10([p[0] for p in points]); y = np.log10([p[1] for p in points])
    return np.polyfit(x, y, deg)


def poly_expr(c, var):
    """Horner form of a numpy polyfit coefficient list in var."""
    s = f"{c[0]:.6g}"
    for k in c[1:]:
        s = f"({s})*{var}+({k:.6g})"
    return s


# ---------------------------------------------------------------- CA3080 (Intersil 475.4)
CA = {
    "gm_table": (500e-6, 9600e-6),           # p.2 Forward transconductance, typ 9600 uS at 500 uA
    "rout_table": (500e-6, 15e6),            # p.2 Output resistance, typ 15 MOhm at 500 uA
    "cout": 5.6e-12,                         # p.2 Output capacitance, typ 5.6 pF (500 uA, 1 MHz)
    "cin": 3.6e-12,                          # p.2 Input capacitance, typ 3.6 pF
    "cio": 0.024e-12,                        # p.2 Input-to-output capacitance, typ 0.024 pF
    "bw": 2e6,                               # p.3 Open-loop bandwidth, typ 2 MHz
    "k_supply": 1e-3 / 500e-6,               # p.3 Amplifier supply current 1 mA typ at 500 uA
    "rdiff": 4.0 / 0.008e-9,                 # p.2 Differential input current 0.008 nA at 4 V, Iabc 0
    "rleak": 36.0 / 0.3e-9,                  # p.3 Leakage current 0.3 nA typ at VTP 36 V, Iabc 0
    # p.2 CMR typ +13.6 / -14.6 V on +-15 V at 500 uA -> 1.4 V below V+, 0.4 V above V-
    "cmr": (1.4, 0.4),
    # p.3 Peak output voltage RL=inf: +13.8/-14.5 at 5 uA, +13.5/-14.4 at 500 uA (+-15 V)
    "swing": {5e-6: (1.2, 0.5), 500e-6: (1.5, 0.6)},
    # Fig 27 (p.10, vector, 25 degC curve, 3-point polyline) + table 0.71 V at 500 uA (p.2)
    "vbias": [(0.1017e-6, 0.4967), (420e-6, 0.7043), (973.2e-6, 0.7335), (500e-6, 0.71)],
    # Fig 16 (p.8, vector, 25 degC = middle curve, 3-point polyline), nA
    "ib": [(0.1031e-6, 1.371e-9), (0.5841e-6, 5.465e-9), (972.3e-6, 3568e-9)],
}

# ------------------------------------------------------------ LM13700 (TI SNOSBW2F)
LM = {
    "gm_table": (500e-6, 9600e-6),           # 6.4 Forward transconductance typ 9600 uS (500 uA)
    "cout": 4.75e-12,                        # Fig 11 (raster, pixel) C_OUT at 500 uA
    "cin": 5.96e-12,                         # Fig 11 (raster, pixel) C_IN at 500 uA
    "bw": 2e6,                               # 6.4 Open-loop bandwidth typ 2 MHz
    "k_supply": 2.6e-3 / 2 / 500e-6,         # 6.4 Supply current 2.6 mA both channels, 500 uA
    # 6.4 Differential input current 0.02 nA typ at +-4 V, Iabc 0; 3.75 pA of it already flows
    # through the linearising diodes' ngspice gmin (measured by check_ota.py), so Rdiff
    # carries the rest
    "rdiff": 4.0 / (0.02e-9 - 3.75e-12),
    "rleak": 30.0 / 0.2e-9,                  # 6.4 Leakage current 0.2 nA typ (Iabc 0; +-15 V)
    "cmr": (1.5, 1.5),                       # 6.4 Common-mode range typ +-13.5 V on +-15 V
    # 6.4 Peak output voltage RL=inf, 5 uA <= Iabc <= 500 uA: +14.2 / -14.4 typ
    "swing": {5e-6: (0.8, 0.6), 500e-6: (0.8, 0.6)},
    # Fig 10 (raster, pixel) amplifier bias voltage, 25 degC (middle) curve: two junctions
    "vbias": [(0.1e-6, 0.9766), (0.2e-6, 1.0108), (0.5e-6, 1.0685), (1e-6, 1.1063),
              (2e-6, 1.1477), (5e-6, 1.2000), (10e-6, 1.2396), (20e-6, 1.2793),
              (50e-6, 1.3279), (100e-6, 1.3658), (200e-6, 1.4018), (500e-6, 1.4523),
              (1000e-6, 1.4847)],
    # Fig 3 (raster, pixel) input bias current, 25 degC (middle) curve, nA
    "ib": [(0.15e-6, 2.66e-9), (0.25e-6, 3.31e-9), (1.5e-6, 11.7e-9), (2.5e-6, 18.1e-9),
           (4.5e-6, 29.9e-9), (15e-6, 87.2e-9), (25e-6, 133e-9), (45e-6, 225e-9),
           (150e-6, 619e-9), (250e-6, 1002e-9), (450e-6, 1748e-9)],
    # Fig 12 (raster, pixel) output resistance, MOhm
    "rout_fig": [(0.2e-6, 7658.8e6), (0.5e-6, 2986.2e6), (1e-6, 1507.6e6), (2e-6, 761.1e6),
                 (5e-6, 296.8e6), (10e-6, 148.6e6), (20e-6, 73.77e6), (50e-6, 29.99e6),
                 (100e-6, 14.89e6), (200e-6, 7.392e6), (500e-6, 2.955e6), (1000e-6, 1.608e6)],
    # 6.4 Buffer input current typ 0.5 uA, footnote (1): Iabc 500 uA, 5 kOhm buffer
    # output to -VS, buffer input on the OTA output (read as: the OTA output at its peak,
    # the same footnote's "peak buffer output voltage" line)
    "ibuf": 0.5e-6,
}


def swing_expr(sw, which, iabc):
    """Headroom (V) as a + b*log10(Iabc/1uA), Iabc floored at 0.1 uA (sheet's range)."""
    (i1, h1), (i2, h2) = sorted((i, v[which]) for i, v in sw.items())
    if abs(h2 - h1) < 1e-12:
        return f"{h1:.4g}"
    b = (h2 - h1) / math.log10(i2 / i1)
    a = h1 - b * math.log10(i1 / 1e-6)
    return f"({a:.6g}+({b:.6g})*log10(max({iabc},1e-7)/1e-6))"


def core(p, ib_coef, va, diode_card, extra=""):
    """The subcircuit body shared by both parts (nodes inp inn out vp vn; bias pin via Vsense)."""
    vt = "(8.617333e-5*(temper+273.15))"
    cbw = 1.0 / (2 * math.pi * 1e3 * p["bw"])
    iabc = "max(i(Vsense),0)"
    hp, hn = swing_expr(p["swing"], 0, "v(ia)"), swing_expr(p["swing"], 1, "v(ia)")
    l = "log10(min(max(v(ia),1e-7),1e-3))"  # figure range 0.1 uA .. 1 mA
    # beta(Iabc) = (Iabc/2)/Ib(Iabc), Ib from the figure's log-log polynomial
    beta = f"(0.5*pwr(10,{l})/pwr(10,{poly_expr(ib_coef, l)}))"
    f = lambda x: f"(pwr(max({x},0),2)/(pwr(max({x},0),2)+{VS_KNEE**2:.6g}))"  # noqa: E731
    vcm = "(0.5*(v(inp)+v(inn)))"
    w = f"({f(f'v(vp)-{p['cmr'][0]}-{vcm}')}*{f(f'{vcm}-v(vn)-{p['cmr'][1]}')})"
    return f"""Vsense iabc ib0 0
Dbias ib0 vn DBIAS
* Iabc as a voltage (1 V per A) for the expressions
Bia ia 0 V={iabc}
* input-pair window: the common-mode range
Bw w 0 V={w}
* the pair's halves I5 (to the output's source mirror) and I4 (to the sink), then the
* open-loop bandwidth pole ({p['bw']/1e6:g} MHz) on each, in the mirrors (after the tanh,
* so a large step slews at Iabc/C instead of winding up a filtered input voltage)
Bi5 i5r 0 V=v(ia)*v(w)*0.5*(1+tanh((v(inp)-v(inn))/(2*{vt})))
Bi4 i4r 0 V=v(ia)*v(w)*0.5*(1-tanh((v(inp)-v(inn))/(2*{vt})))
R5 i5r i5 1k
C5 i5 0 {cbw:.6g}
R4 i4r i4 1k
C4 i4 0 {cbw:.6g}
* output: source from V+, sink to V-, each stopping at the swing limit; Early sets Rout
Bsrc vp out I=v(i5)*{f(f'v(vp)-{hp}-v(out)')}*(1+max(v(vp)-v(out),0)/{va:.6g})
Bsnk out vn I=v(i4)*{f(f'v(out)-v(vn)-{hn}')}*(1+max(v(out)-v(vn),0)/{va:.6g})
Cout out vn {p['cout']:.4g}
Rleak out vn {2*p['rleak']:.4g}
Rleak2 out vp {2*p['rleak']:.4g}
* input bias currents: the pair's base currents (unfiltered Vd), into the tail at V-
Bbp inp vn I=v(ia)*v(w)*0.5*(1+tanh((v(inp)-v(inn))/(2*{vt})))/{beta}
Bbn inn vn I=v(ia)*v(w)*0.5*(1-tanh((v(inp)-v(inn))/(2*{vt})))/{beta}
Rdiff inp inn {p['rdiff']:.4g}
Cinp inp vn {p['cin']:.4g}
Cinn inn vn {p['cin']:.4g}
* quiescent: V+ draws {p['k_supply']:g} x Iabc at balance (Iabc/2 of it is the output pair)
Bq vp vn I={p['k_supply'] - 0.5:.6g}*v(ia)
{extra}{diode_card}"""


def build():
    out = {}
    # ---- CA3080
    is_, n, rs = fit_junction(CA["vbias"])
    ibc = fit_loglog(CA["ib"], 1)
    va = CA["rout_table"][0] * CA["rout_table"][1]
    card = f".model DBIAS D(IS={is_:.6g} N={n:.6g} RS={rs:.6g})\n"
    body = core(CA, ibc, va, card, extra=f"Cio inn out {CA['cio']:.4g}\n")
    head = ("* CA3080 operational transconductance amplifier (our model from the sheet)\n"
            "* Built by Solum Builder from Intersil CA3080/CA3080A data sheet File Number 475.4\n"
            "* (September 1998), typical figures at 25 degC, +-15 V. Behavioural core: Iout =\n"
            "* Iabc*tanh(Vd/2VT); bias pin a junction to V-.\n"
            ".subckt CA3080 inp inn out iabc vp vn\n")
    open(os.path.join(HERE, "CA3080.lib"), "w").write(head + body + ".ends CA3080\n")
    out["CA3080"] = dict(IS=is_, N=n, RS=rs, ib_coef=list(ibc), VA=va)

    # ---- LM13700
    is2, n2, rs2 = fit_junction(LM["vbias"])  # two junctions in series as one diode
    ibl = fit_loglog(LM["ib"], 2)
    va2 = math.exp(np.mean([math.log(i * r) for i, r in LM["rout_fig"]]))
    # one junction (all transistors and diodes identical, TI 7.3.1): half of Fig 10 at
    # 500 uA, as an N=1 junction so the linearising diodes match the tanh exactly
    vj = 1.4523 / 2
    isj = 500e-6 / math.exp(vj / VT25)
    # Darlington beta from the buffer-input line: OTA output at its +swing limit
    # (+-15 V: 14.2 V), buffer out = 14.2 - two VBEs, 5 kOhm to -15 V
    vout = 15 - LM["swing"][500e-6][0]
    beta = 100.0
    for _ in range(50):
        il = (vout - 2 * 0.75 - (-15)) / 5e3
        for _ in range(20):
            i13 = il; i12 = i13 / (beta + 1)
            vbe = VT25 * math.log(i13 / isj) + VT25 * math.log(i12 / isj)
            il = (vout - vbe + 15) / 5e3
        beta = math.sqrt(il / LM["ibuf"]) - 1
    card2 = (f".model DBIAS D(IS={is2:.6g} N={n2:.6g} RS={rs2:.6g})\n"
             f".model DLIN D(IS={isj:.6g} N=1)\n"
             f".model QBUF NPN(IS={isj:.6g} BF={beta:.4g})\n")
    lin = ("* linearising diodes D2 (to -input) and D3 (to +input), anodes on the diode-bias pin\n"
           "D2 dbias inn DLIN\nD3 dbias inp DLIN\n"
           "* Darlington buffer Q12, Q13, collectors on V+\n"
           "Q12 vp bufin q13b QBUF\nQ13 vp q13b bufout QBUF\n")
    body2 = core(LM, ibl, va2, card2, extra=lin)
    head2 = ("* LM13700 operational transconductance amplifier, one of two (our model from the sheet)\n"
             "* Built by Solum Builder from TI LM13700 data sheet SNOSBW2F (November 1999,\n"
             "* revised November 2015), typical figures at 25 degC, +-15 V. Behavioural core:\n"
             "* Iout = Iabc*tanh(Vd/2VT); bias pin two junctions to V-; linearising diodes and the\n"
             "* Darlington buffer as junctions. The dual is two instances on shared vp/vn.\n"
             ".subckt LM13700_OTA inp inn out iabc dbias bufin bufout vp vn\n")
    open(os.path.join(HERE, "LM13700.lib"), "w").write(head2 + body2 + ".ends LM13700_OTA\n")
    out["LM13700"] = dict(IS_bias=is2, N_bias=n2, RS_bias=rs2, ib_coef=list(ibl), VA=va2,
                          IS_junction=isj, BF_buffer=beta)
    return out


if __name__ == "__main__":
    for k, v in build().items():
        print(k, {a: (b if isinstance(b, list) else float(f"{b:.6g}")) for a, b in v.items()})
