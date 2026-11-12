"""Find the six plots' frames and grid lines on Toshiba's page 2 (300 dpi, /scr/t1815/hi-2.pgm)."""
import sys
sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import numpy as np
from pix import groups, load

im = load("/scr/t1815/hi-2.pgm")
d = im < 128
print(im.shape)
for name, (c0, c1) in {"L": (200, 1250), "R": (1250, 2500)}.items():
    rows = np.nonzero(d[:, c0:c1].mean(axis=1) > 0.3)[0]
    print(name, "rows", groups(rows))
for name, (r0, r1) in {"top": (550, 1250), "mid": (1350, 2050), "bot": (2150, 2850)}.items():
    cols = np.nonzero(d[r0:r1, :].mean(axis=0) > 0.3)[0]
    print(name, "cols", groups(cols))
