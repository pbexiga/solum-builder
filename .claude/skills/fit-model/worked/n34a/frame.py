import numpy as np
from PIL import Image
a = np.asarray(Image.open(".claude/skills/fit-model/worked/n34a/dioper.jpg").convert("L")).astype(int)
dark = a < 80
rows = [y for y in range(a.shape[0]) if dark[y].sum() > 300]
cols = [x for x in range(a.shape[1]) if dark[:, x].sum() > 200]
print("rows", rows); print("cols", cols)
print("bg", np.median(a[100:300, 100:500]))
