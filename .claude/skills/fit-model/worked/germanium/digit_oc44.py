"""OC44 curves read by pixel off Mullard's sheet (data/spec-sheets/OC44_Mullard.pdf, Mullard
Vol. 4 Part III, Dec 1960 / Oct 1964): pdfimages pages at /scr/OC44. Axes as digit_oc71.py
(labelled major grid lines, linear between). Writes data/OC44.json."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import axis, load, trace  # noqa: E402


def page(n):
    return load(f"/scr/OC44/i-{n:03d}-{n - 1:03d}.ppm")


out = {}
# Page C1 (pdf page 7): IC against VBE, grounded base or emitter, Vc = -2 V. x VBE (mV) majors
# every 25; y IC (mA) majors every 1 (labels every 2).
vx = axis([(366, 0), (504, 25), (641, 50), (778.5, 75), (915, 100), (1052.5, 125), (1189.5, 150), (1326, 175), (1463, 200)])
iy = axis([(2035.5, 0), (1898.5, 1), (1762, 2), (1627.5, 3), (1490, 4), (1353, 5), (1217, 6), (1082, 7), (941, 8), (803, 9), (668, 10)])
im = page(7)
pts = [(x, y) for y, x in trace(im, "row", 680, 1890, 50, [[668, 1463], [940, 1410], [1490, 1320], [1760, 1200], [1890, 1130]], 4, 120)]
pts += trace(im, "col", 820, 1140, 20, [[820, 2020], [900, 2009], [1000, 1980], [1060, 1951], [1100, 1926], [1140, 1885]], 4, 120)
out["c1_ic_vbe"] = sorted([[round(iy(y), 4), round(vx(x), 2)] for x, y in pts])  # [IC mA, VBE mV]
# Page C2 (pdf page 8), lower: transfer characteristic, Vc = -2 V. x IC (mA) majors every 2;
# y IB (µA) majors every 25.
icx = axis([(1195, 0), (1066.5, 2), (939, 4), (810.5, 6), (683, 8), (555, 10), (426.5, 12), (298.5, 14)])
iby = axis([(2044.5, 0), (1918.5, 25), (1790.5, 50), (1662.5, 75), (1536, 100), (1410, 125)])
im = page(8)
pts = trace(im, "row", 1545, 2035, 35, [[1545, 554], [1685, 757], [1860, 988], [2000, 1150], [2040, 1180]], 4, 120)
out["c2_transfer"] = sorted([[round(iby(y), 3), round(icx(x), 4)] for y, x in pts])  # [IB µA, IC mA]
# Page C2, upper: input characteristic, Vc = -2 V. x IB (µA) majors every 20; y Vb (mV) majors
# every 50. Read for the record; left out of the fit (it contradicts C1 and the table, NOTES).
ibx = axis([(1195, 0), (1066.5, 20), (939, 40), (810.5, 60), (683, 80), (555, 100), (426.5, 120)])
vy = axis([(1278.5, 0), (1151.5, 50), (1024.5, 100), (897, 150), (765.5, 200), (637.5, 250), (511.5, 300)])
pts = trace(im, "col", 560, 1110, 50, [[556, 820], [860, 900], [1080, 980], [1150, 1050]], 4, 120)
pts += [(x, y) for y, x in trace(im, "row", 1030, 1150, 30, [[980, 1080], [1080, 1160], [1200, 1190]], 4, 120)]
out["c2_input"] = sorted([[round(ibx(x), 2), round(vy(y), 2)] for x, y in pts])  # [IB µA, VBE mV]

Path(".claude/skills/fit-model/worked/germanium/data/OC44.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, len(v), v)
