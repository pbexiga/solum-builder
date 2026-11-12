"""Tiny helpers: run a netlist through the project's libngspice engine."""
import os

import numpy as np

from solum.sim.native import native_engine

HERE = os.path.dirname(os.path.abspath(__file__))
E = native_engine()
CARD = {p: open(os.path.join(HERE, f"{p}.lib")).read() for p in ("CA3080", "LM13700")}


def run(body, part, kind, opts=""):
    net = f"* ota check\n{CARD[part]}{body}\n{opts}\n.end\n"
    p = E.run(net).plot(kind)
    return {k.lower(): np.array(v) for k, v in p.vectors.items()}


def v(vec, node):
    for k in (node, f"v({node})"):
        if k in vec:
            return vec[k].real
    raise KeyError(f"{node}: {sorted(vec)[:40]}")


def i(vec, src):
    return vec[f"{src.lower()}#branch"].real
