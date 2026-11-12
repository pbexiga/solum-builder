"""Crops of page 2's plots for placing trace guides (PNG in /scr/t1815)."""
import sys
sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import numpy as np
from pix import load

im = load("/scr/t1815/hi-2.pgm").astype(np.uint8)
CROPS = {"hfe": (1380, 575, 2105, 1180), "vcs": (345, 1365, 1070, 1970), "ibvbe": (345, 2150, 1070, 2760),
         "ft": (1380, 2150, 2105, 2760), "icvce": (340, 575, 1065, 1180)}


def png(path, a):
    import struct
    import zlib
    h, w = a.shape
    raw = b"".join(b"\x00" + a[r].tobytes() for r in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


for name, (x0, y0, x1, y1) in CROPS.items():
    png(f"/scr/t1815/crop_{name}.png", im[y0:y1, x0:x1])
