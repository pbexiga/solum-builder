"""Pedal sanity checks at 9 V single supply (V- at ground, inputs biased at mid-supply).

CA3080: a VCA (the Dyna Comp's gain cell): signal 300 mV peak via 47 k into + (1 k to the
4.5 V reference on each input), output to the reference through 10 k, Iabc through a
resistor from +9 V (the envelope/LFO's job in a pedal).
LM13700: TI's Figure 17 VCA scaled to 9 V with a stiff 4.5 V reference: 13 k -> 4.7 k from +9 V to the diode-bias pin,
the 1 k offset pot centred (500 ohm per input to 4.5 V), 30 k from the source, RL 30 k to
4.5 V, the Darlington buffer into 5 k to ground, Iabc from +9 V through a resistor.
Prints Iabc, gain at 1 kHz and THD; the LM13700 with its diodes biased and with the
diode-bias pin open (same output level by scaling the input)."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_ota import OPTS, thd  # noqa: E402
from sim import i, run, v  # noqa: E402

REF = "V1 vp 0 9\nRr1 vp ref 10k\nRr2 ref 0 10k\nCr ref 0 100u\n"
# the LM13700's diode bias (~0.8 mA) flows into the reference through the 500 ohm resistors,
# which pulls a 10 k/10 k divider up to 6.4 V: it needs a stiff (buffered) 4.5 V reference
REF_STIFF = "V1 vp 0 9\nVref ref 0 4.5\n"


def ca3080(rabc, amp=0.3):
    body = (REF + f"Vs s 0 SIN(0 {amp} 1k)\nCs s s1 1u\nRs s1 inp 47k\nRp inp ref 1k\nRn inn ref 1k\n"
            f"RL out ref 10k\nRabc vp ib {rabc}\nVsense ib ibx 0\nX1 inp inn out ibx vp 0 CA3080\n")
    r = run(body + ".tran 1u 8m 0 1u", "CA3080", "tran", OPTS)
    d, fund = thd(r["time"].real, v(r, "out"), 1e3)
    iabc = i(r, "Vsense")[-1]
    return iabc, fund / amp, d, float(np.mean(v(r, "out")))


def lm13700(rabc, diodes, amp=1.0, node="bo"):
    db = {True: "RD vp db 4.7k\n", "isrc": "Id vp db 0.8m\n"}.get(diodes, "")
    body = (REF_STIFF + f"Vs s 0 SIN(0 {amp} 1k)\nCs s s1 10u\nRin s1 inp 30k\nRA inp ref 500\nRB inn ref 500\n"
            f"{db}RL out ref 30k\nRo bo 0 5k\nRabc vp ib {rabc}\nVsense ib ibx 0\n"
            "X1 inp inn out ibx db out bo vp 0 LM13700_OTA\n")
    r = run(body + ".tran 1u 8m 0 1u", "LM13700", "tran", OPTS)
    d, fund = thd(r["time"].real, v(r, node), 1e3)
    return i(r, "Vsense")[-1], fund / amp, d, float(np.mean(v(r, node))), fund


def main():
    print("CA3080 VCA, 9 V single supply, 300 mV peak in:")
    for rabc in ("1Meg", "330k", "100k", "33k", "15k"):
        ia, g, d, dc = ca3080(rabc)
        print(f"  Rabc {rabc:>5s}: Iabc {ia*1e6:7.2f} uA  gain {g:7.4f} ({20*math.log10(g):6.1f} dB)  "
              f"THD {d:.3f} %  out DC {dc:.3f} V")
    ia, g, d, dc = ca3080("15k", amp=3.0)
    print(f"  overdriven (3 V peak in, 15 k): THD {d:.1f} %  out DC {dc:.3f} V")
    print("LM13700 VCA (TI Fig 17 at 9 V), buffer output, 1 V peak in:")
    for rabc in ("1Meg", "330k", "100k", "33k", "15k"):
        ia, g, d, dc, fund = lm13700(rabc, True)
        print(f"  diodes biased, Rabc {rabc:>5s}: Iabc {ia*1e6:7.2f} uA  gain {g:7.4f} "
              f"({20*math.log10(g):6.1f} dB)  THD {d:.3f} %  out DC {dc:.3f} V")
    print("LM13700 distortion at the OTA output, diodes biased vs pin open, same output level (Rabc 33 k):")
    _, g0, _, _, _ = lm13700("33k", False, amp=0.05, node="out")
    for amp in (1.0, 3.0, 6.0, 9.0, 12.0):
        ia, _, d1, _, f1 = lm13700("33k", True, amp=amp, node="out")
        a0 = f1 / g0  # input that gives the same output without the diodes
        _, _, d0, _, f0 = lm13700("33k", False, amp=a0, node="out")
        print(f"  out {f1:.3f} V peak (Iout/Iabc {f1/30e3/ia:.2f}): with diodes THD {d1:.3f} %, "
              f"pin open THD {d0:.3f} % (out {f0:.3f} V, input {a0:.3f} V peak)")
    print("  the same with the diodes fed by a 0.8 mA current source (as TI 7.3.2 assumes) instead of 4.7 k:")
    for amp in (1.0, 3.0, 6.0, 9.0, 12.0):
        ia, _, d1, _, f1 = lm13700("33k", "isrc", amp=amp, node="out")
        a0 = f1 / g0
        _, _, d0, _, f0 = lm13700("33k", False, amp=a0, node="out")
        print(f"  out {f1:.3f} V peak (Iout/Iabc {f1/30e3/ia:.2f}): with diodes THD {d1:.3f} %, "
              f"pin open THD {d0:.3f} %")

if __name__ == "__main__":
    main()
