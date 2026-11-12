"""Trace a thick curve in a raster scan (PGM): trace.py img.pgm axis lo hi guess.json
axis 'row': for each row y in [lo, hi] find the dark run (>= MINW px wide) whose centre is
nearest the guess x(y) (linear between guess points), print y, x. 'col': the same, by column."""
import json, sys
import numpy as np

MINW = int(__import__("os").environ.get("MINW", "5"))
THR = int(__import__("os").environ.get("THR", "110"))

def load(path):
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(maxsplit=4)
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(parts[4][-w * h:], dtype=np.uint8).reshape(h, w)

def main():
  pass
img = load(sys.argv[1]); axis = sys.argv[2]; lo, hi = int(sys.argv[3]), int(sys.argv[4])
g = np.array(json.loads(sys.argv[5]), float)  # [[along, across], ...]
if axis == "col":
    img = img.T
for a in range(lo, hi + 1, int(sys.argv[6]) if len(sys.argv) > 6 else 1):
    guess = float(np.interp(a, g[:, 0], g[:, 1]))
    line = img[a] < THR
    runs, start = [], None
    for i, d in enumerate(line):
        if d and start is None: start = i
        if not d and start is not None:
            if i - start >= MINW: runs.append((start + i - 1) / 2)
            start = None
    near = [r for r in runs if abs(r - guess) < 25]
    if near:
        print(a, round(min(near, key=lambda r: abs(r - guess)), 1))
