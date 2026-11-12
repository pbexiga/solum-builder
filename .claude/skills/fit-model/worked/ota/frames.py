"""Print each plot frame's grid lines on a PDF page (pt), to map axes by hand.
frames.py sheet.pdf page"""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from svgpaths import subpaths  # noqa: E402
import importlib.util
spec = importlib.util.spec_from_file_location("plots_mod", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plots.py"))


def load(pdf, page):
    with tempfile.TemporaryDirectory() as d:
        svg = os.path.join(d, "p.svg")
        subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf, svg], check=True)
        return subpaths(svg)


if __name__ == "__main__":
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plots.py")).read()
    src = src.replace("\nmain()\n", "\n")
    g = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plots.py")}
    exec(compile(src, "plots.py", "exec"), g)
    P = load(sys.argv[1], int(sys.argv[2]))
    for n, b in enumerate(g["frames"](P)):
        print(n, "x", b["x"], "y", b["y"])
        print("   vs", b["vs"])
        print("   hs", b["hs"])
