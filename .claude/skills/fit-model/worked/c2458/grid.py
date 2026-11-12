import sys
import numpy as np
from PIL import Image
im = np.array(Image.open(sys.argv[1]).convert("L")) < 128
h, w = im.shape
cols = [x for x in range(w) if im[:, x].mean() > 0.55]
rows = [y for y in range(h) if im[y, :].mean() > 0.55]
print(im.shape); print("cols", cols); print("rows", rows)
