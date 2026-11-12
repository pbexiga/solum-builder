import sys
from PIL import Image
import numpy as np
im = np.array(Image.open(sys.argv[1]).convert("L")) < 128
h, w = im.shape
rows = [(y, im[y].mean()) for y in range(h) if im[y].mean() > 0.5]
cols = [(x, im[:, x].mean()) for x in range(w) if im[:, x].mean() > 0.35]
print("rows", [r[0] for r in rows]); print("cols", [c[0] for c in cols])
