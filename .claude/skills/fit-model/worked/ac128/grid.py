"""Grid lines of a PGM crop: grid.py img.pgm -> x positions and y positions of lines that
are dark over at least FRAC of the image's height/width (major and minor)."""
import sys, numpy as np
def load(path):
    data = open(path, "rb").read(); parts = data.split(maxsplit=4)
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(parts[4][-w * h:], dtype=np.uint8).reshape(h, w)
img = load(sys.argv[1]) < 128
frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
def lines(v):
    idx = np.where(v > frac)[0]; out = []; 
    for i in idx:
        if out and i - out[-1][-1] <= 1: out[-1].append(i)
        else: out.append([i])
    return [round(sum(g) / len(g), 1) for g in out]
print("x", lines(img.mean(axis=0)))
print("y", lines(img.mean(axis=1)))
