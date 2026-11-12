"""Check the fitted CD4049UB_INV against every 25 °C figure and table line of TI SCHS046L it can measure.

python .claude/skills/fit-model/worked/cd4049/check.py [params.json]  (dev image) -> a Markdown table, plus the
pedal numbers (gain and bias at 9 V, output resistance).

Criteria, fixed before looking at results:
 - min/max table lines and minimum curves: the right side of the limit (OK) or not (MISS);
 - typical curves (Figures 5-3, 5-5): every point within ±20 %;
 - Figure 5-7 (only -55 °C and 125 °C drawn): the 25 °C value between the two curves;
 - Figure 5-9: within ±25 % (read off straight lines on a log-log plot; edges assumed 20 ns);
 - table typicals are reported, OK within ±20 %.
"""

import json
import sys

import numpy as np

from scratch.fit.cd4049 import inv, sheet
from scratch.fit.cd4049.fit import FIG59, VTC_X

# Figure 5-7's VI at VO = 90 % / 10 % of VCC, (-55 °C, 125 °C): digitise.vi_at on the host
# (the dev image has no poppler).
SHOULDERS = {(5, 0.9): (2.369, 1.997), (5, 0.1): (2.924, 2.689), (10, 0.9): (3.744, 3.416), (10, 0.1): (4.706, 4.522)}
ROWS: list[tuple[str, str, str, str]] = []


def row(what: str, got: str, want: str, ok: bool) -> None:
    ROWS.append((what, got, want, "OK" if ok else "MISS"))


def curves(p, data, fn, typ: bool, label: str) -> None:
    for vcc, pts in data.items():
        v, i = fn(p, vcc, 8.0)
        errs = [inv.at(v, i, x) * 1e3 / y - 1 for x, y in pts]
        if typ:
            worst = max(errs, key=abs)
            row(f"{label}, VCC {vcc} V ({len(pts)} pts)", f"{min(errs):+.0%} to {max(errs):+.0%}",
                "±20 % (typ curve)", abs(worst) <= 0.20)
        else:
            row(f"{label}, VCC {vcc} V ({len(pts)} pts)", f"lowest {min(errs):+.0%} vs min",
                "≥ min curve", min(errs) >= 0)


def main(path: str) -> None:
    p = json.load(open(path))
    curves(p, sheet.SINK_TYP, inv.sink, True, "Fig 5-3 typ sink")
    curves(p, sheet.SINK_MIN, inv.sink, False, "Fig 5-4 min sink")
    curves(p, sheet.SOURCE_TYP, inv.source, True, "Fig 5-5 typ source")
    curves(p, sheet.SOURCE_MIN, inv.source, False, "Fig 5-6 min source")

    vi, vo = inv.vtc(p, 5, 0.001)
    sw = inv.switch_point(vi, vo)
    row("Fig 5-1 VTC at 5 V: switch between min and max curves", f"{sw:.3f} V", "1.096-3.986 V",
        1.096 <= sw <= 3.986)
    for vcc in (5, 10):
        vi, vo = inv.vtc(p, vcc, 0.001)
        sw = inv.switch_point(vi, vo)
        cold, hot = VTC_X[vcc]
        row(f"Fig 5-7 switch (VO = VI), VCC {vcc} V", f"{sw:.3f} V", f"{hot}-{cold} V (125/-55 °C)",
            hot <= sw <= cold)
        for frac in (0.9, 0.1):
            c, h = SHOULDERS[(vcc, frac)]
            got = inv.at(vo[::-1], vi[::-1], frac * vcc)
            row(f"Fig 5-7 VI at VO = {frac:.0%} VCC, VCC {vcc} V", f"{got:.2f} V", f"{min(c, h):.2f}-{max(c, h):.2f} V",
                min(c, h) <= got <= max(c, h))
        s = inv.slope_30_70(vi, vo, vcc)
        drawn = {5: (18.1, 383.1), 10: (24.5, 30.9)}[vcc]
        row(f"Fig 5-7 slope VO 70->30 % VCC, VCC {vcc} V", f"{s:.1f}", f"{drawn[0]}-{drawn[1]} (drawn)",
            drawn[0] <= s <= drawn[1])
    for vcc, cl, uw in FIG59:
        got = inv.power(p, vcc, cl, 100e3) * 1e6
        row(f"Fig 5-9 power at 100 kHz, VCC {vcc} V, CL {cl * 1e12:.0f} pF", f"{got:.0f} µW", f"{uw:.0f} µW ±25 %",
            abs(got / uw - 1) <= 0.25)

    for vcc, vout, mn, typ in sheet.IOL:
        v, i = inv.sink(p, vcc, 2.0)
        got = inv.at(v, i, vout) * 1e3
        row(f"IOL at VCC {vcc} V, VOUT {vout} V", f"{got:.2f} mA", f"min {mn}", got >= mn)
        row(f"IOL typ at VCC {vcc} V, VOUT {vout} V", f"{got:.2f} mA", f"typ {typ} ±20 %", abs(got / typ - 1) <= 0.2)
    for vcc, vout, mn, typ in sheet.IOH:
        v, i = inv.source(p, vcc, vcc - vout + 0.5)
        got = inv.at(v, i, vcc - vout) * 1e3
        row(f"IOH at VCC {vcc} V, VOUT {vout} V", f"-{got:.2f} mA", f"min -{mn}", got >= mn)
        row(f"IOH typ at VCC {vcc} V, VOUT {vout} V", f"-{got:.2f} mA", f"typ -{typ} ±20 %", abs(got / typ - 1) <= 0.2)
    for vcc in (5, 10, 15):
        vi, vo = inv.vtc(p, vcc, 0.01)
        row(f"VOL at VCC {vcc} V (VIN = VCC, no load)", f"{vo[-1] * 1e3:.3g} mV", "≤ 50 mV", vo[-1] <= sheet.VOL_MAX)
        row(f"VOH at VCC {vcc} V (VIN = 0, no load)", f"{vo[0]:.4f} V", f"≥ {vcc - 0.05:.2f} V",
            vo[0] >= vcc - sheet.VOH_DROP)
    for vcc, vout, vil in sheet.VIL:
        vi, vo = inv.vtc(p, vcc, 0.001)
        got = inv.at(vi, vo, vil)
        row(f"VIL max {vil} V at VCC {vcc} V: VOUT", f"{got:.3f} V", f"≥ {vout} V", got >= vout)
    for vcc, vout, vih in sheet.VIH:
        vi, vo = inv.vtc(p, vcc, 0.001)
        got = inv.at(vi, vo, vih)
        row(f"VIH min {vih} V at VCC {vcc} V: VOUT", f"{got:.3f} V", f"≤ {vout} V", got <= vout)
    for vcc, mx in sheet.IDD:
        got = max(inv.supply_current(p, vcc, 0), inv.supply_current(p, vcc, vcc)) * 1e6
        row(f"IDD at VCC {vcc} V (one inverter; the limit is the chip's)", f"{got:.3g} µA", f"≤ {mx} µA", got <= mx)
    got = max(abs(inv.input_current(p, 18, 0)), abs(inv.input_current(p, 18, 18)))
    row("IIN at VCC 18 V, VIN 0 or 18 V", f"{got * 1e6:.2g} µA", "≤ 0.1 µA", got <= sheet.IIN_MAX)
    c_lo, c_hi = inv.cin(p, 10, 0) , inv.cin(p, 10, 10)
    row("CIN (VCC 10 V, input low / high)", f"{c_lo * 1e12:.1f} / {c_hi * 1e12:.1f} pF", "typ 15, max 22.5 pF",
        max(c_lo, c_hi) <= sheet.CIN[1])
    for name, rows, rising, key in (("tPLH", sheet.TPLH, False, "tp"), ("tPHL", sheet.TPHL, True, "tp"),
                                    ("tTLH", sheet.TTLH, False, "tt"), ("tTHL", sheet.TTHL, True, "tt")):
        for vcc, typ, mx in rows:
            got = inv.tran(p, vcc, rising)[key]
            row(f"{name} at VCC {vcc} V", f"{got:.1f} ns", f"typ {typ}, max {mx}", got <= mx)
    vi, vo = inv.vtc(p, 3, 0.001)
    row("Works at VCC 3 V (rec. min): VOH / VOL / switch", f"{vo[0]:.3f} / {vo[-1] * 1e3:.2g} mV / {inv.switch_point(vi, vo):.2f} V",
        "rail to rail", vo[0] >= 2.95 and vo[-1] <= 0.05)

    print("| Check | Model | Sheet (25 °C) | |\n|---|---|---|---|")
    for r in ROWS:
        print("| " + " | ".join(r) + " |")
    print(f"\n{sum(r[3] == 'OK' for r in ROWS)} OK, {sum(r[3] == 'MISS' for r in ROWS)} MISS")

    print("\nPedal numbers (no load, open loop):")
    for vcc in (5, 9, 10, 15):
        g, vs = inv.gain_ac(p, vcc)
        vi, vo = inv.vtc(p, vcc, 0.0005)
        print(f"  VCC {vcc:>2} V: switching point VO = VI = {vs:.3f} V, small-signal gain {g:.1f} ({20 * np.log10(g):.1f} dB),"
              f" 30-70 % slope {inv.slope_30_70(vi, vo, vcc):.1f}, Rout at the switch {inv.rout(p, vcc, vs) / 1e3:.1f} kΩ")
    for vcc in (9,):
        v, i = inv.sink(p, vcc, 0.2)
        vs_, is_ = inv.source(p, vcc, 0.2)
        print(f"  VCC 9 V, output at a rail: sink on-resistance {0.1 / inv.at(v, i, 0.1):.0f} Ω,"
              f" source on-resistance {0.1 / inv.at(vs_, is_, 0.1):.0f} Ω")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".claude/skills/fit-model/worked/cd4049/params.json")
