"""The 2N7000 card against the BS170 sheet's table (Fairchild Rev. E2, page 2)."""
import numpy as np
from scratch.fit.mosfet.fit_vdmos import ENGINE, vth, vds_at, transfer
from scratch.fit.mosfet.fit_ac import caps
CARD = {"vto": 2.3973, "kp": 0.4838, "ksubthres": 0.24488, "mtriode": 1.1919, "lambda": 1e-06,
        "rs": 1.0742, "rd": 1.0117e-06, "cgs": 1.7221e-11, "cgdmax": 3.7315e-11, "cgdmin": 2.0146e-12,
        "a": 0.30204, "cjo": 2.6453e-11, "m": 0.40407, "vj": 1.0171, "is": 9.1033e-13, "n": 1.1464, "rb": 0.12828}
from scratch.fit.mosfet.fit_vdmos import card
m = card("MT", CARD)
print("VGS(th) 1 mA:", round(vth(m, 1e-3), 3), "(sheet 2.1)")
print("RDS(on) 10 V 200 mA:", round(vds_at(m, 10, 0.2) / 0.2, 3), "ohm (sheet 1.2)")
vg, i = transfer(m, 10, 10, 0.001)
k = int(np.argmin(abs(i - 0.2)))
print("gFS at VDS 10 V, 200 mA:", round(float((i[k + 1] - i[k - 1]) / (vg[k + 1] - vg[k - 1])) * 1e3), "mS (sheet 320)")
print("Ciss/Coss/Crss at 10 V:", [round(c * 1e12, 2) for c in caps(CARD, {}, [10.0])[0]], "pF (sheet 24/17/7)")
