"""OC71 curves read by pixel off Mullard's sheet (data/spec-sheets/OC71_Mullard.pdf, Mullard
Vol. 4 Part III, Issue 2): page images from `pdfimages -p` (300 dpi), mounted at /scr/OC71.
Axes: each labelled major grid line's pixel (pix.py grid, the darker lines marked '*'),
values between them linear (np.interp), so a stretched scan is followed line by line.
Writes data/OC71.json: {curve: [[x, y], ...]} in mA / µA / mV as named."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import axis, load, trace  # noqa: E402


def page(n):
    return load(f"/scr/OC71/i-{n:03d}-{n - 1:03d}.ppm")


out = {}
# Page 13 (158-13), spread of transfer characteristic, grounded emitter, Vc = -4.5 V: the
# solid 'Average' line. x IB (µA) majors every 50; y IC (mA) majors every 2.5.
ib = axis([(305.7, 0), (465, 50), (625, 100), (784, 150), (944, 200), (1103.5, 250), (1263, 300), (1421, 350)])
ic = axis([(2029.5, 0), (1872.5, 2.5), (1717, 5), (1556, 7.5), (1394.5, 10), (1238, 12.5), (1074, 15), (912.5, 17.5), (757, 20)])
pts = trace(page(13), "row", 1140, 2020, 20, [[1140, 1103], [2029, 306]], 4, 120)
out["p13_transfer_avg"] = [[round(ib(x), 2), round(ic(y), 4)] for y, x in pts]  # [IB µA, IC mA]

# Page 12 (158-12), lower: transfer characteristic, grounded emitter, Vc = -4.5 V (IB +5 to
# -20 µA; base current into the base drawn negative). x IC (mA) majors every 0.25; y IB.
icx = axis([(1239.5, 0), (1111, 0.25), (983, 0.5), (855, 0.75), (727, 1.0), (598, 1.25), (470, 1.5)])
iby = axis([(2028, -5), (1902.5, 0), (1776, 5), (1649, 10), (1519, 15), (1393, 20)])  # µA into the base
pts = trace(page(12), "row", 1505, 2025, 15, [[1496, 680], [1900, 1170], [2030, 1232]], 4, 120)
out["p12_transfer"] = [[round(iby(y), 3), round(icx(x), 4)] for y, x in pts if y != 1805]  # [IB µA, IC mA]

# Page 7 (158-7), emitter current against emitter-base voltage, Vc = -4.5 V. Upper: x IE (mA)
# majors every 2.5, y VBE (mV) majors every 50. Lower: x IE (µA) majors every 25, y VBE
# majors every 20 (0 is the heavy line; + forward).
ie = axis([(449, 15), (603, 12.5), (756, 10), (909.5, 7.5), (1062.5, 5), (1216.5, 2.5), (1370, 0)])
vu = axis([(1271, 0), (1115.5, 50), (957, 100), (805, 150), (651, 200), (475, 250)])
im7 = page(7)
up = trace(im7, "col", 760, 1290, 30, [[760, 572], [1000, 655], [1060, 682], [1150, 725], [1250, 790], [1290, 840]], 4, 120)
up += [(x, y) for y, x in trace(im7, "row", 860, 1265, 25, [[850, 1282], [900, 1309], [1000, 1339], [1100, 1356], [1265, 1368]], 4, 120)]
out["p7_vbe_ie_mA"] = sorted([[round(ie(x), 4), round(vu(y), 2)] for x, y in up if ie(x) >= 0.25])  # the steep foot: the lower plot  # [IE mA, VBE mV]
iel = axis([(449, 150), (602, 125), (755.5, 100), (908.5, 75), (1061.5, 50), (1214.5, 25), (1366.5, 0)])
vl = axis([(2039, -20), (1888, 0), (1737, 20), (1583.5, 40), (1425, 60)])
lo = trace(im7, "col", 640, 1325, 35, [[636, 1480], [900, 1600], [1120, 1700], [1250, 1820], [1325, 1935]], 4, 120)
out["p7_vbe_ie_uA"] = sorted([[round(iel(x), 2), round(vl(y), 2)] for x, y in lo])  # [IE µA, VBE mV]

# Page 11 (158-11), spread of input characteristic, grounded emitter, Vc = -4.5 V: the solid
# 'Average' line. x IB (µA) majors every 50, y VBE (mV) majors every 50.
ibx = axis([(1370.5, 0), (1208, 50), (1045.5, 100), (883.5, 150), (721.5, 200), (559.5, 250), (397, 300)])
vy = axis([(2039.5, 0), (1882, 50), (1715, 100), (1554.5, 150), (1391, 200), (1226.5, 250), (1067, 300), (904, 350), (739, 400)])
pts = trace(page(11), "col", 565, 1345, 40, [[560, 1164], [1050, 1390], [1250, 1560], [1340, 1690]], 5, 110)
out["p11_input_avg"] = sorted([[round(ibx(x), 2), round(vy(y), 2)] for x, y in pts])  # [IB µA, VBE mV]

Path(".claude/skills/fit-model/worked/germanium/data").mkdir(exist_ok=True)
Path(".claude/skills/fit-model/worked/germanium/data/OC71.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, len(v), v[:: max(1, len(v) // 12)])
