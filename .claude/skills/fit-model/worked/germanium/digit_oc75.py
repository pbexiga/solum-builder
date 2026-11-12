"""OC75 curves read by pixel off Mullard's sheet (data/spec-sheets/OC75_Mullard.pdf, Mullard
Vol. 4 Part III, sheets of March 1959): pdfimages pages at /scr/OC75. Axes as digit_oc71.py.
Writes data/OC75.json."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import axis, load, trace  # noqa: E402


def page(n):
    return load(f"/scr/OC75/i-{n:03d}-{n - 1:03d}.ppm")


out = {}
im = page(10)
# Page C6 (pdf 10) upper: spread of transfer characteristic, Vc = -4.5 V, the solid Average
# line. x IC (mA) majors every 5; y IB (µA) majors every 50.
icx = axis([(1228, 0), (1100.5, 5), (974, 10), (847, 15), (720, 20), (593, 25), (466.5, 30), (341, 35)])
iby = axis([(1123.5, 0), (999.5, 50), (872, 100), (741, 150), (616, 200), (492.5, 250)])
pts = trace(im, "row", 500, 1060, 35, [[490, 668], [700, 830], [900, 990], [1110, 1215]], 4, 120)
out["c6_transfer_avg"] = sorted([[round(iby(y), 2), round(icx(x), 4)] for y, x in pts])  # [IB µA, IC mA]
# Page C6 lower: transfer characteristic, Vc = -4.5 V (IB +10 to -15 µA). x IC (mA) majors
# every 0.25; y IB majors every 5 (into the base positive here).
icx = axis([(1228, 0), (1101, 0.25), (974.5, 0.5), (847.5, 0.75), (721, 1.0), (593.5, 1.25), (467.5, 1.5), (341.5, 1.75)])
iby = axis([(2009, -10), (1884.5, -5), (1758, 0), (1630.5, 5), (1506, 10), (1382, 15), (1251.5, 20)])
pts = trace(im, "row", 1440, 1990, 30, [[1436, 560], [1756, 1050], [1880, 1224], [2000, 1230]], 4, 120)
out["c6_transfer"] = sorted([[round(iby(y), 3), round(icx(x), 4)] for y, x in pts])
# Page C1 (pdf 5): emitter current against emitter-base voltage, Vc = -4.5 V. Upper: x IE (mA)
# majors every 2.5, y VBE (mV) majors every 50. Lower: x IE (µA) majors every 25, y VBE majors
# every 20.
im = page(5)
ie = axis([(1333.5, 0), (1180.5, 2.5), (1026.5, 5), (873.5, 7.5), (720.5, 10), (567.5, 12.5)])
vu = axis([(1092, 0), (941, 50), (784.5, 100), (631, 150), (482, 200)])
up = trace(im, "col", 725, 1145, 35, [[720, 516], [900, 560], [1100, 620], [1200, 665]], 4, 120)
up += trace(im, "col", 1160, 1295, 15, [[1145, 662], [1200, 692], [1250, 725], [1280, 750], [1300, 790]], 4, 120)
out["c1_vbe_ie_mA"] = sorted([[round(ie(x), 4), round(vu(y), 2)] for x, y in up])  # [IE mA, VBE mV]
iel = axis([(1333.5, 0), (1180.5, 25), (1026.5, 50), (873.5, 75), (720.5, 100), (567.5, 125)])
vl = axis([(2008.5, -20), (1861, 0), (1705.5, 20), (1552.5, 40), (1403.5, 60)])
lo = trace(im, "col", 725, 1215, 35, [[720, 1536], [1020, 1660], [1150, 1760], [1220, 1870]], 4, 120)
out["c1_vbe_ie_uA"] = sorted([[round(iel(x), 2), round(vl(y), 2)] for x, y in lo])  # [IE µA, VBE mV]
# Page C5 (pdf 9): spread of input characteristic, Vc = -4.5 V, the solid Average line. x IB
# (µA) majors every 100 (labelled), y VBE (mV) majors every 50.
ibx = axis([(1362.5, 0), (1043.5, 100), (724.5, 200), (404, 300)])
vy = axis([(2010, 0), (1850.5, 50), (1692.5, 100), (1536, 150), (1372.5, 200), (1213.5, 250), (1054.5, 300), (890.5, 350), (732.5, 400)])
pts = trace(page(9), "col", 575, 1325, 50, [[570, 1154], [825, 1279], [900, 1320], [1000, 1378], [1100, 1441], [1200, 1515], [1275, 1577], [1330, 1630]], 3, 140)
out["c5_input_avg"] = sorted([[round(ibx(x), 2), round(vy(y), 2)] for x, y in pts])  # [IB µA, VBE mV]

Path(".claude/skills/fit-model/worked/germanium/data/OC75.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, len(v), v)
