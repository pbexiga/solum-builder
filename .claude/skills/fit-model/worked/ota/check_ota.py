"""Measure our CA3080 and LM13700 models in ngspice against their sheets (25 degC figures;
ngspice runs at its default 27 degC, as the app does).

  podman run --rm -v "$PWD":/src:z -w /src -e PYTHONPATH=/src -e HOME=/tmp \
      solum-builder:dev python .claude/skills/fit-model/worked/ota/check_ota.py

Prints one line per check: what, sheet value (source), model value, OK/MISS.
A typical value is OK within the stated tolerance (figures read off a plot: 15 %, or
the stated mV); a min/max line is OK inside its limits."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import i, run, v  # noqa: E402

ROWS = []
TOL_FIG = 0.15


def row(part, what, sheet, src, model, ok, unit=""):
    ROWS.append((part, what, sheet, src, model, unit, "OK" if ok else "MISS"))
    print(f"{part:8s} | {what:44s} | {sheet:>16s} | {src:28s} | {model:>12s} {unit:5s} | {'OK' if ok else 'MISS'}",
          flush=True)


def typ(part, what, sheet_v, src, model_v, unit, tol=TOL_FIG, lo=None, hi=None, fmt="{:.4g}"):
    ok = abs(model_v - sheet_v) <= tol * abs(sheet_v)
    if lo is not None:
        ok = ok and model_v >= lo
    if hi is not None:
        ok = ok and model_v <= hi
    lim = ""
    if lo is not None or hi is not None:
        lim = f" [{'' if lo is None else fmt.format(lo)}..{'' if hi is None else fmt.format(hi)}]"
    row(part, what, fmt.format(sheet_v) + lim, src, fmt.format(model_v), ok, unit)


def typ_abs(part, what, sheet_v, src, model_v, unit, tol_abs, lo=None, hi=None):
    ok = abs(model_v - sheet_v) <= tol_abs
    if lo is not None:
        ok = ok and model_v >= lo
    if hi is not None:
        ok = ok and model_v <= hi
    lim = "" if lo is None and hi is None else f" [{lo if lo is not None else ''}..{hi if hi is not None else ''}]"
    row(part, what, f"{sheet_v:.4g}{lim}", src, f"{model_v:.4g}", ok, unit)


# ------------------------------------------------------------------ netlist pieces
def inst(part, inp="inp", inn="inn", out="out", iabc="ib", vp="vp", vn="vn", db="db",
         bi="bi", bo="bo", name="X1"):
    if part == "CA3080":
        return f"{name} {inp} {inn} {out} {iabc} {vp} {vn} CA3080\n"
    return f"{name} {inp} {inn} {out} {iabc} {db} {bi} {bo} {vp} {vn} LM13700_OTA\n"


def lm_extra(part):
    # LM13700 table conditions: buffer inputs grounded, outputs open; pins 2, 15 open
    return "Vbi bi 0 0\n" if part == "LM13700" else ""


SUP = "V1 vp 0 15\nV2 vn 0 -15\n"


def op_gm(part, iabc, vd=10e-6):
    """Small-signal gm: output held at 0 V, inputs +-vd/2 (DC, symmetric difference)."""
    out = []
    for s in (+1, -1):
        r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 {s*vd/2}\nVn inn 0 {-s*vd/2}\nVo out 0 0\n"
                + lm_extra(part) + inst(part) + ".op", part, "op")
        out.append(i(r, "Vo")[0])
    return (out[0] - out[1]) / (2 * vd)


def op_peak_iout(part, iabc):
    r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 0.5\nVn inn 0 -0.5\nVo out 0 0\n" + lm_extra(part)
            + inst(part) + ".op", part, "op")
    return i(r, "Vo")[0]


def op_basic(part, iabc):
    """Bias voltage (pin above V-), input bias current (mean of both inputs), V+ current."""
    r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 0\nVn inn 0 0\nVo out 0 0\n" + lm_extra(part)
            + inst(part) + ".op", part, "op")
    return (v(r, "ib")[0] + 15, -(r["vp#branch"][0].real + r["vn#branch"][0].real) / 2,
            -i(r, "V1")[0])


def op_rin(part, iabc, vd=20e-6):
    cur = []
    for s in (+1, -1):
        r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 {s*vd/2}\nVn inn 0 {-s*vd/2}\nVo out 0 0\n"
                + lm_extra(part) + inst(part) + ".op", part, "op")
        cur.append(-r["vp#branch"][0].real)
    return 2 * vd / (cur[0] - cur[1])


def op_rout(part, iabc):
    cur = []
    for vo in (1.0, -1.0):
        r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 0\nVn inn 0 0\nVo out 0 {vo}\n" + lm_extra(part)
                + inst(part) + ".op", part, "op")
        cur.append(i(r, "Vo")[0])
    return -2.0 / (cur[0] - cur[1])  # current into the output falls as it rises


def op_swing(part, iabc):
    res = []
    for s in (+1, -1):
        r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 {s*0.5}\nVn inn 0 {-s*0.5}\n" + lm_extra(part)
                + inst(part) + ".op", part, "op")
        res.append(v(r, "out")[0])
    return res


def ac_bw_caps(part, iabc):
    """gm(f) with the output held: -3 dB point; output and input capacitance at 1 MHz."""
    r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 0 AC 1\nVn inn 0 0\nVo out 0 0\n" + lm_extra(part)
            + inst(part) + ".ac dec 50 1k 100Meg", part, "ac")
    f = r["frequency"].real
    g = np.abs(r["vo#branch"])
    g0 = g[0]
    k = np.nonzero(g < g0 / math.sqrt(2))[0][0]
    f3 = f[k - 1] * (f[k] / f[k - 1]) ** ((math.log(g0 / math.sqrt(2)) - math.log(g[k - 1]))
                                          / (math.log(g[k]) - math.log(g[k - 1])))
    # output capacitance: AC on the output, inputs held
    r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 0\nVn inn 0 0\nVo out 0 0 AC 1\n" + lm_extra(part)
            + inst(part) + ".ac lin 1 1Meg 1Meg", part, "ac")
    cout = abs(np.imag(r["vo#branch"][0])) / (2 * math.pi * 1e6)
    r = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 0 AC 1\nVn inn 0 0\nVo out 0 0\n" + lm_extra(part)
            + inst(part) + ".ac lin 1 1Meg 1Meg", part, "ac")
    cin = abs(np.imag(r["vp#branch"][0])) / (2 * math.pi * 1e6)
    return f3, cout, cin


def cmr(part, iabc):
    """Common-mode voltage where gm has fallen to half of its mid-range value, each side."""
    g0 = op_gm(part, iabc)
    out = []
    for lo, hi in ((10.0, 15.0), (-15.0, -10.0)):
        a, b = lo, hi
        up = hi > 0
        for _ in range(30):
            m = (a + b) / 2
            r1 = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 {m+5e-6}\nVn inn 0 {m-5e-6}\nVo out 0 0\n"
                     + lm_extra(part) + inst(part) + ".op", part, "op")
            r2 = run(SUP + f"Ib 0 ib {iabc}\nVp inp 0 {m-5e-6}\nVn inn 0 {m+5e-6}\nVo out 0 0\n"
                     + lm_extra(part) + inst(part) + ".op", part, "op")
            g = (i(r1, "Vo")[0] - i(r2, "Vo")[0]) / 2e-5
            inside = g > g0 / 2
            if up:
                a, b = (m, b) if inside else (a, m)
            else:
                a, b = (a, m) if inside else (m, b)
        out.append((a + b) / 2)
    return out


def converge(part):
    """DC op with Iabc 0 and the pin open, a DC sweep of Iabc 0..2 mA, and a transient with
    Iabc swept by an LFO-like ramp from 0 (9 V single supply, inputs at mid-supply)."""
    msgs = []
    for desc, ib in (("Iabc = 0", "Ib 0 ib 0\n"), ("bias pin open", "")):
        r = run("V1 vp 0 9\nV2 vn 0 0\nVm m 0 4.5\nVp inp m 0\nVn inn m 0\nRL out m 10k\n" + ib
                + lm_extra(part).replace(" 0 0", " m 0") + inst(part) + ".op", part, "op")
        msgs.append(f"{desc}: out {v(r, 'out')[0]:.4f} V")
    r = run(SUP + "Ib 0 ib 0\nVp inp 0 1m\nVn inn 0 0\nRL out 0 10k\n" + lm_extra(part) + inst(part)
            + ".dc Ib 0 2m 10u", part, "dc")
    msgs.append(f"DC sweep Iabc 0..2 mA: {len(v(r, 'out'))} points, out at 2 mA {v(r, 'out')[-1]:.3f} V")
    r = run("V1 vp 0 9\nV2 vn 0 0\nVm m 0 4.5\nVs inp m SIN(0 20m 1k)\nVn inn m 0\nRL out m 10k\n"
            "Vc c 0 PWL(0 -1 10m 9 20m -1)\nRc c ib 10k\n" + lm_extra(part).replace(" 0 0", " m 0")
            + inst(part) + ".tran 2u 20m", part, "tran")
    msgs.append(f"tran, Iabc from a 10 k resistor swept -1..9 V: {len(r['time'])} points, "
                f"|out-4.5| max {np.max(np.abs(v(r, 'out') - 4.5)):.3f} V")
    return msgs


def thd(t, y, f0, cycles=4):
    """THD (%) of the last `cycles` periods (uniform resample)."""
    t1 = t[-1]; t0 = t1 - cycles / f0
    n = 4096
    tt = np.linspace(t0, t1, n, endpoint=False)
    yy = np.interp(tt, t, y)
    yy = yy - yy.mean()
    spec = np.abs(np.fft.rfft(yy)) / n * 2
    fund = spec[cycles]
    harm = math.sqrt(sum(spec[cycles * k] ** 2 for k in range(2, 10)))
    return 100 * harm / fund, fund


VT27 = 8.617333e-5 * 300.15
OPTS = ".options reltol=1e-6 abstol=1e-15 vntol=1e-9"


def fig13_point(diodes, amp):
    """LM13700 Fig 13 conditions: +-15 V, Iabc 1 mA, RL 10 kOhm. Without diodes the input
    is a differential voltage of amp peak; with them (TI 8.2.2 / Fig 17: 13 kOhm from V+ to
    the diodes biased by an ideal 1 mA and the signal an ideal current of amp peak. Returns (x mVpp as the figure defines it, THD %)."""
    f0 = 1e3
    if diodes:
        # ideal current bias, as the figure's formula assumes (TI 7.3.2): ID 1 mA into the
        # diode-bias pin (TI 8.3.1's recommended value; the figure doesn't say), the signal an
        # ideal current into +, 0.5 mA sunk from +, - held at 0 V
        body = (SUP + f"Ib 0 ib 1m\nId 0 db 1m\nIs 0 inp SIN(0 {amp} {f0})\nIsink inp 0 0.5m\n"
                "Vfix inn 0 0\nRL out 0 10k\nVbi bi 0 0\n")
    else:
        body = SUP + f"Ib 0 ib 1m\nVs inp 0 SIN(0 {amp} {f0})\nVn inn 0 0\nRL out 0 10k\nVbi bi 0 0\n"
    r = run(body + inst("LM13700") + f".tran 0.5u {6/f0} 0 0.5u", "LM13700", "tran", OPTS)
    t = r["time"].real; y = v(r, "out")
    d, fund = thd(t, y, f0)
    if diodes:
        ipk = fund / 10e3  # output current peak
        m = min(ipk / 1e-3, 0.999999)
        x = 2 * VT27 * math.log((1 + m) / (1 - m)) * 1e3  # the figure's VIN(peak) formula, x2 for pp
    else:
        x = 2 * amp * 1e3
    return x, d


# Fig 13 (raster, by pixel): x mVpp at each distortion level (%)
FIG13_NO = [(0.03, 7.22), (0.07, 10.33), (0.15, 15.4), (0.25, 19.7), (0.45, 25.89), (0.7, 31.38),
            (1.5, 45.22), (2.5, 57.62), (4.5, 76.01), (7, 93.19), (15, 131.2)]
FIG13_DI = [(0.03, 33.89), (0.07, 53.35), (0.15, 70.38), (0.25, 80.21), (0.45, 92.12), (0.7, 98.73),
            (1.5, 110.8), (2.5, 118.3), (4.5, 126.3), (7, 133.8), (15, 147.9)]


def fig_interp(pts, x):
    """Distortion (%) the figure gives at x mVpp (log-log interpolation)."""
    xs = [p[1] for p in pts]; ds = [p[0] for p in pts]
    if x < xs[0] or x > xs[-1]:
        return None
    return 10 ** np.interp(math.log10(x), np.log10(xs), np.log10(ds))


def check_common(part, src, figs):
    P = part
    # ---- gm
    g = op_gm(P, 500e-6)
    typ(P, "gm at Iabc 500 uA (uS)", 9600, src["tbl"], g * 1e6, "uS", lo=6700, hi=13000, tol=0.05)
    for ia, gs in figs["gm"]:
        typ(P, f"gm at {ia*1e6:g} uA (uS)", gs, figs["gm_src"], op_gm(P, ia) * 1e6, "uS")
    # ---- peak output current
    typ(P, "peak Iout RL=0, Iabc 5 uA (uA)", 5, src["tbl"], op_peak_iout(P, 5e-6) * 1e6, "uA",
        tol=0.05, **({"lo": 3, "hi": 7} if P == "CA3080" else {}))
    typ(P, "peak Iout RL=0, Iabc 500 uA (uA)", 500, src["tbl"], op_peak_iout(P, 500e-6) * 1e6, "uA",
        lo=350, hi=650, tol=0.05)
    for ia, ip in figs["ipk"]:
        typ(P, f"peak Iout at {ia*1e6:g} uA (uA)", ip, figs["ipk_src"], op_peak_iout(P, ia) * 1e6, "uA")
    # ---- bias voltage, input bias current, supply current
    vb, ib, isup = op_basic(P, 500e-6)
    if "vb_tbl" in src:
        typ_abs(P, "amplifier bias voltage at 500 uA (V)", src["vb_tbl"][0], src["vb_tbl"][1], vb, "V", 0.02)
    for ia, vv in figs["vb"]:
        typ_abs(P, f"bias voltage at {ia*1e6:g} uA (mV)", vv * 1e3, figs["vb_src"],
                op_basic(P, ia)[0] * 1e3, "mV", 25)
    typ(P, "input bias current at 500 uA (uA)", src["ib_tbl"], src["tbl"], ib * 1e6, "uA",
        hi=5, tol=0.15)
    for ia, ii in figs["ib"]:
        typ(P, f"input bias current at {ia*1e6:g} uA (nA)", ii * 1e9, figs["ib_src"],
            op_basic(P, ia)[1] * 1e9, "nA")
    lim = {"lo": 0.8, "hi": 1.2} if P == "CA3080" else {}
    typ(P, "supply current at 500 uA, one amp (mA)", src["isup"], src["tbl"], isup * 1e3, "mA",
        tol=0.05, **lim)
    for ia, ss in figs.get("isup", []):
        typ(P, f"supply current at {ia*1e6:g} uA (uA)", ss, figs["isup_src"],
            op_basic(P, ia)[2] * 1e6, "uA")
    # ---- input / output resistance
    rin = op_rin(P, 500e-6)
    typ(P, "input resistance at 500 uA (kOhm)", 26, src["tbl"], rin / 1e3, "kOhm", lo=10, tol=0.15)
    for ia, rr in figs["rin"]:
        typ(P, f"input resistance at {ia*1e6:g} uA (MOhm)", rr, figs["rin_src"], op_rin(P, ia) / 1e6, "MOhm")
    if "rout_tbl" in src:
        typ(P, "output resistance at 500 uA (MOhm)", src["rout_tbl"], src["tbl"],
            op_rout(P, 500e-6) / 1e6, "MOhm", tol=0.05)
    for ia, rr in figs["rout"]:
        typ(P, f"output resistance at {ia*1e6:g} uA (MOhm)", rr, figs["rout_src"], op_rout(P, ia) / 1e6, "MOhm")
    # ---- bandwidth and capacitances
    f3, cout, cin = ac_bw_caps(P, 500e-6)
    typ(P, "open-loop bandwidth at 500 uA (MHz)", 2, src["tbl"], f3 / 1e6, "MHz", tol=0.05)
    typ(P, "output capacitance at 500 uA, 1 MHz (pF)", src["cout"][0], src["cout"][1], cout * 1e12, "pF", tol=0.05)
    typ(P, "input capacitance at 500 uA, 1 MHz (pF)", src["cin"][0], src["cin"][1], cin * 1e12, "pF", tol=0.05)
    # ---- common-mode range and output swing (+-15 V)
    cp, cn = cmr(P, 500e-6)
    typ_abs(P, "CMR + at 500 uA (gm half) (V)", src["cmr"][0], src["tbl"], cp, "V", 0.15, lo=12)
    typ_abs(P, "CMR - at 500 uA (gm half) (V)", src["cmr"][1], src["tbl"], cn, "V", 0.15, hi=-12)
    for ia, (sp, sn) in src["swing"].items():
        mp, mn = op_swing(P, ia)
        typ_abs(P, f"peak out + RL=inf, {ia*1e6:g} uA (V)", sp, src["tbl"], mp, "V", 0.05, lo=12)
        typ_abs(P, f"peak out - RL=inf, {ia*1e6:g} uA (V)", sn, src["tbl"], mn, "V", 0.05, hi=-12)
    for ia, sp, sn in figs.get("swing", []):
        mp, mn = op_swing(P, ia)
        typ_abs(P, f"peak out + at {ia*1e6:g} uA (V)", sp, figs["swing_src"], mp, "V", 0.1)
        typ_abs(P, f"peak out - at {ia*1e6:g} uA (V)", sn, figs["swing_src"], mn, "V", 0.1)
    # ---- differential input current at Iabc 0, 4 V
    r = run(SUP + "Ib 0 ib 0\nVp inp 0 2\nVn inn 0 -2\nVo out 0 0\n" + lm_extra(P) + inst(P) + ".op", P, "op")
    idiff = abs(r["vp#branch"][0].real)
    typ(P, "differential input current Iabc 0, 4 V (nA)", src["idiff"][0], src["tbl"], idiff * 1e9,
        "nA", tol=0.15, hi=src["idiff"][1])
    for m in converge(P):
        row(P, "converges: " + m[:44], "-", "robustness", "ran", True)


def slew_follower(part, iabc):
    """Unity-gain follower (output to inn), no load: 10 V step, slope 20-80 %."""
    r = run(SUP + f"Ib 0 ib {iabc}\nVs inp 0 PULSE(-5 5 1u 1n 1n 5u 10u)\n" + lm_extra(part)
            + inst(part, inn="out") + ".tran 2n 4u", part, "tran")
    t = r["time"].real; y = v(r, "out")
    k = (t > 1e-6) & (y > -3) & (y < 3)
    return np.polyfit(t[k], y[k], 1)[0] / 1e6


def main():
    ca_src = {"tbl": "475.4 p.2-3 table", "ib_tbl": 2.0, "isup": 1.0, "rout_tbl": 15,
              "vb_tbl": (0.71, "475.4 p.2 table"), "cout": (5.6, "475.4 p.2 table"),
              "cin": (3.6, "475.4 p.2 table"), "cmr": (13.6, -14.6),
              "swing": {5e-6: (13.8, -14.5), 500e-6: (13.5, -14.4)}, "idiff": (0.008, None)}
    ca_figs = {
        "gm_src": "Fig 21 p.9 vector", "gm": [(0.1009e-6, 2.0), (1.027e-6, 19.76), (11.57e-6, 222.1),
                                             (619.9e-6, 11080)],
        "ipk_src": "Fig 17 p.8 vector", "ipk": [(0.101e-6, 0.1041), (2.189e-6, 2.188), (467.7e-6, 405.1),
                                               (728.9e-6, 763.4)],
        "vb_src": "Fig 27 p.10 vector", "vb": [(0.1017e-6, 0.4967), (420e-6, 0.7043), (973.2e-6, 0.7335)],
        "ib_src": "Fig 16 p.8 vector", "ib": [(0.1031e-6, 1.371e-9), (0.5841e-6, 5.465e-9), (972.3e-6, 3568e-9)],
        "isup_src": "Fig 19 p.9 vector", "isup": [(0.412e-6, 0.8136), (9.592e-6, 17.86), (100.6e-6, 174.7)],
        "rin_src": "Fig 26 p.10 vector", "rin": [(0.1027e-6, 33.61), (9.657e-6, 0.7851), (134.6e-6, 0.07616),
                                                (439.7e-6, 0.02637)],
        "rout_src": "Fig 29 p.10 vector", "rout": [(0.1917e-6, 3.446e4), (108.7e-6, 55.99), (348.8e-6, 17.65),
                                                  (945.4e-6, 6.378)],
        "swing_src": "Fig 18 p.9 vector", "swing": [(0.102e-6, 14.086, -14.478), (992e-6, 13.355, -14.362)],
    }
    check_common("CA3080", ca_src, ca_figs)
    sr = slew_follower("CA3080", 500e-6)
    typ("CA3080", "slew, uncompensated follower, no load (V/us)", 75, "475.4 p.3 table", sr, "V/us")

    lm_src = {"tbl": "SNOSBW2F 6.4 table", "ib_tbl": 0.4, "isup": 1.3,
              "cout": (4.75, "Fig 11 raster/pixel"), "cin": (5.96, "Fig 11 raster/pixel"),
              "cmr": (13.5, -13.5), "swing": {5e-6: (14.2, -14.4), 500e-6: (14.2, -14.4)},
              "idiff": (0.02, 100)}
    lm_figs = {
        "gm_src": "Fig 8 raster/pixel", "gm": [(4.5e-6, 99.79), (150e-6, 3185), (450e-6, 9377)],
        "ipk_src": "Fig 4 raster/pixel", "ipk": [(2.5e-6, 3.298), (15e-6, 19.15), (45e-6, 55.15)],
        "vb_src": "Fig 10 raster/pixel", "vb": [(0.1e-6, 0.9766), (1e-6, 1.1063), (10e-6, 1.2396),
                                               (100e-6, 1.3658), (1000e-6, 1.4847)],
        "ib_src": "Fig 3 raster/pixel", "ib": [(0.15e-6, 2.66e-9), (1.5e-6, 11.7e-9), (15e-6, 87.2e-9),
                                              (150e-6, 619e-9), (450e-6, 1748e-9)],
        "rin_src": "Fig 9 raster/pixel", "rin": [(0.1e-6, 38.35), (1e-6, 6.283), (10e-6, 0.8862),
                                                (100e-6, 0.1049), (1000e-6, 0.0125)],
        "rout_src": "Fig 12 raster/pixel", "rout": [(1e-6, 1507.6), (10e-6, 148.6), (100e-6, 14.89),
                                                   (1000e-6, 1.608)],
    }
    check_common("LM13700", lm_src, lm_figs)
    P = "LM13700"
    # supply current, both channels (two instances)
    r = run(SUP + "Ib1 0 ib1 500u\nIb2 0 ib2 500u\nVbi bi 0 0\nVbi2 bi2 0 0\n"
            + inst(P, "0", "0", "o1", "ib1", name="X1") + inst(P, "0", "0", "o2", "ib2", db="db2", bi="bi2",
                                                            bo="bo2", name="X2")
            + "Ro1 o1 0 1G\nRo2 o2 0 1G\n.op", P, "op")
    typ(P, "supply current, both channels, 500 uA (mA)", 2.6, "SNOSBW2F 6.4 table", -i(r, "V1")[0] * 1e3,
        "mA", tol=0.05)
    # buffer: footnote (1)
    r = run(SUP + "Ib 0 ib 500u\nVp inp 0 0.5\nVn inn 0 -0.5\nRo bo vn 5k\n" + inst(P, bi="out") + ".op", P, "op")
    # buffer input current = OTA output current into bufin; read as Iout from the sink side
    ibuf = None
    rr = run(SUP + "Ib 0 ib 500u\nVp inp 0 0.5\nVn inn 0 -0.5\nVb out bi 0\nRo bo vn 5k\n" + inst(P) + ".op",
             P, "op")
    ibuf = i(rr, "Vb")[0]
    typ(P, "buffer input current, footnote (1) (uA)", 0.5, "SNOSBW2F 6.4 table", ibuf * 1e6, "uA",
        tol=0.15, hi=2)
    vbo = v(r, "bo")[0]
    row(P, "peak buffer output, footnote (1) (V)", "min 10", "SNOSBW2F 6.4 table", f"{vbo:.3f}", vbo >= 10, "V")
    # application text: pin voltages (approximate, not in the spec table)
    r = run(SUP + "Ib 0 ib 1m\nRD vp db 13k\nRA inp 0 1k\nRB inn 0 1k\nVo out 0 0\nVbi bi 0 0\n" + inst(P) + ".op",
            P, "op")
    dd = v(r, "db")[0] - v(r, "inp")[0]
    row(P, "diode drop, 13 k from +15 V (V)", "~0.7", "SNOSBW2F 8.2.2 text", f"{dd:.3f}",
        abs(dd - 0.7) < 0.05, "V")
    row(P, "bias pin at Iabc 1 mA, -15 V supply (V)", "~-13.6", "SNOSBW2F 8.2.2 text", f"{v(r, 'ib')[0]:.3f}",
        abs(v(r, "ib")[0] + 13.6) < 0.1, "V")
    sr = slew_follower(P, 500e-6)
    row(P, "slew, follower, no load (V/us)", "50 (compens.)", "SNOSBW2F 6.4 table", f"{sr:.4g}", False, "V/us")
    # Fig 13 distortion
    print("\nFig 13 (Iabc 1 mA, RL 10 k, +-15 V; with diodes: ideal 1 mA diode bias, ideal signal current):")
    for diodes, amps, pts in ((False, [5e-3, 10e-3, 20e-3, 40e-3], FIG13_NO),
                              (True, [150e-6, 250e-6, 330e-6, 400e-6, 440e-6], FIG13_DI)):
        for a in amps:
            x, d = fig13_point(diodes, a)
            fd = fig_interp(pts, x)
            name = "with diodes" if diodes else "no diodes"
            if fd is None:
                row(P, f"Fig 13 {name}: {x:.1f} mVpp THD (%)", "off figure", "Fig 13 raster/pixel", f"{d:.4g}",
                    True, "%")
            else:
                ok = abs(math.log10(d / fd)) <= math.log10(1.5)
                row(P, f"Fig 13 {name}: {x:.1f} mVpp THD (%)", f"{fd:.3g}", "Fig 13 raster/pixel", f"{d:.4g}",
                    ok, "%")


if __name__ == "__main__":
    main()
