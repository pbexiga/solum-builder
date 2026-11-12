"""2N1308 curves read by pixel off TI's sheet (data/spec-sheets/2N1302-2N1309_TI.pdf, bulletin
DL-S 1136, August 1959), page 5 rendered by `pdftoppm -r 300 -gray` into /scr/2n1308/p-5.pgm.
The sheet's "design characteristics" apply to all eight types (2N1302-2N1309), PNP and NPN, except
where a curve says otherwise (here only the normalised hFE, drawn per polarity). Writes
n1308/data.json; n1308/draw.txt is an overlay for `magick -draw` (n1308/ov.png).

Top left, normalised hFE against IC (unity at 25 mA): x IC 0, 100, 200, 300 mA at px 206, 485,
  765.5, 1052.5; y 1.3 ... 0.1 at px 725.5 ... 1403.5 (56.5 px per 0.1).
Top right, VCE against IC, IB 1, 5, 10, 20, 50 mA: x IC 0 ... 300 mA at px 1336 ... 2025 (50 mA per
  114.8 px); y VCE 0 ... 0.6 V at px 1363.5 ... 689.5 (0.1 V per 112.3 px).
Bottom right, Cob normalised to unity at VCB 5 V: x VCB 0, 5, 10, 15, 20 V at px 1290.5, 1504.5,
  1716, 1926.5, 2135.5; y 0, 1.0, 2.0 at px 2570.5, 2293, 2009.5.
Bottom left, VBE against IC, IB 1, 5, 10, 30, 50 mA: x IC 0, 100, 200, 300 mA at px 178, 463.5,
  749.5, 1036; y VBE 0 ... 1.0 V at px 2593 ... 2029 (0.1 V per 56.4 px).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
from pix import axis, load, trace  # noqa: E402

HERE = Path(".claude/skills/fit-model/worked/germanium/n1308")
im = load("/scr/2n1308/p-5.pgm")
out: dict = {}
draw: list[str] = []


def read(name, xa, ya, guide, lo, hi, step=10, minw=4, thr=120, reach=12):
    """Trace one curve by column from IC `lo` to `hi` mA, following `guide` [(IC, value), ...]."""
    xinv = axis([(v, p) for p, v in xa])
    yinv = axis([(v, p) for p, v in ya])
    xv, yv = axis(xa), axis(ya)
    g = [[xinv(i), yinv(v)] for i, v in guide]
    pts = trace(im, "col", int(xinv(lo)), int(xinv(hi)), step, g, minw, thr, reach)
    out[name] = [[round(xv(x), 2), round(yv(y), 4)] for x, y in pts]
    draw.extend(f"fill red circle {x:.0f},{y:.0f} {x + 3:.0f},{y:.0f}" for x, y in pts)


HX = [(206, 0), (485, 100), (765.5, 200), (1052.5, 300)]
HY = [(725.5, 1.3), (782.5, 1.2), (839.5, 1.1), (894.5, 1.0), (951, 0.9), (1008.5, 0.8), (1063.5, 0.7),
      (1120.5, 0.6), (1177, 0.5), (1234.5, 0.4), (1291.5, 0.3), (1347, 0.2), (1403.5, 0.1)]
read("hfe_norm_npn", HX, HY, [(17, 0.975), (25, 1.01), (40, 1.075), (60, 1.12), (90, 1.145), (150, 1.08),
                              (200, 0.96), (250, 0.88), (300, 0.81)], 22, 298, 8)

VX = [(1336, 0), (1450.8, 50), (1565.6, 100), (1680.4, 150), (1795.2, 200), (1910, 250), (2025, 300)]
VY = [(1363.5, 0.0), (1251, 0.1), (1139, 0.2), (1027, 0.3), (913.5, 0.4), (800, 0.5), (689.5, 0.6)]
for ib, guide, lo, hi in (
    ("1", [(25, 0.115), (100, 0.32)], 28, 96),
    ("5", [(25, 0.07), (300, 0.545)], 70, 296),
    ("10", [(50, 0.10), (300, 0.47)], 70, 296),
    ("20", [(75, 0.13), (300, 0.415)], 85, 296),
    ("50", [(250, 0.325), (300, 0.385)], 254, 296),
):
    read(f"vce_ib{ib}", VX, VY, guide, lo, hi, 8, reach=8)

BX = [(178, 0), (463.5, 100), (749.5, 200), (1036, 300)]
BY = [(2593, 0.0), (2538, 0.1), (2481, 0.2), (2426, 0.3), (2369, 0.4), (2312, 0.5), (2255, 0.6), (2198, 0.7),
      (2141, 0.8), (2085, 0.9), (2029, 1.0)]
for ib, guide, lo, hi in (
    ("1", [(20, 0.34), (100, 0.40), (200, 0.43), (300, 0.43)], 22, 296),
    ("5", [(20, 0.455), (100, 0.57), (200, 0.685), (300, 0.745)], 22, 296),
    ("10", [(60, 0.58), (100, 0.625), (200, 0.725), (300, 0.795)], 62, 296),
    ("30", [(150, 0.755), (200, 0.795), (300, 0.85)], 152, 296),
    ("50", [(230, 0.855), (300, 0.88)], 232, 296),
):
    read(f"vbe_ib{ib}", BX, BY, guide, lo, hi, 8, reach=8)

CX = [(1290.5, 0), (1504.5, 5), (1716, 10), (1926.5, 15), (2135.5, 20)]
CY = [(2570.5, 0.0), (2293, 1.0), (2009.5, 2.0)]
read("cob_norm", CX, CY, [(0.6, 1.6), (2, 1.3), (5, 1.0), (10, 0.83), (20, 0.68)], 0.7, 19.8, 6, reach=10)

(HERE / "data.json").write_text(json.dumps(out, indent=1))
(HERE / "draw.txt").write_text("\n".join(draw) + "\n")
for k, v in out.items():
    print(k, len(v), v[:: max(1, len(v) // 6)])
