"""The germanium starters with the AC128 card against each germanium-study card substituted, in
copies (library/starters/ is only read). For each: the DC operating point and a clean (soft,
0.1 V) and a fuzz (hard, 1.0 V) transient at the app's 200 Hz tone, through the project's own
Simulator. Two ways: the starter's measured hFE and leakage kept (only the card's shape, VBE and
leakage split change), and each card's own (measured removed).
run.sh compare.py [stem ...] > out_compare.txt"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g  # noqa: E402
from solum.circuit.io import load_circuit  # noqa: E402
from solum.sim.native import native_engine  # noqa: E402
from solum.simulate import Simulator  # noqa: E402

HERE = Path(".claude/skills/fit-model/worked/germanium")
CARDS = {m: str(HERE / f"{m}.json") for m in ("OC71", "OC75", "OC44", "OC81D")}
sim = Simulator(native_engine(), g.library_with(CARDS))

STARTERS = {
    "fuzz-face": (["Q1", "Q2"], [("AC128", {}), ("OC71", {"Q1": "OC71", "Q2": "OC71"}),
                                 ("OC75", {"Q1": "OC75", "Q2": "OC75"}), ("OC44", {"Q1": "OC44", "Q2": "OC44"})]),
    "tone-bender-mk2": (["Q1", "Q2", "Q3"], [
        ("AC128 all", {"Q1": "AC128", "Q2": "AC128", "Q3": "AC128"}), ("OC75 Q1-Q2, AC128 Q3", {"Q1": "OC75", "Q2": "OC75"}),
        ("OC75 all", {"Q1": "OC75", "Q2": "OC75", "Q3": "OC75"}),
        ("OC81D all", {"Q1": "OC81D", "Q2": "OC81D", "Q3": "OC81D"}), ("OC71 all", {"Q1": "OC71", "Q2": "OC71", "Q3": "OC71"}),
        ("OC44 all", {"Q1": "OC44", "Q2": "OC44", "Q3": "OC44"})]),
    "dallas-rangemaster": (["Q1"], [("AC128", {}), ("OC44", {"Q1": "OC44"}), ("OC71", {"Q1": "OC71"}), ("OC75", {"Q1": "OC75"})]),
}


def variant(c, swap, own):
    for p in c.parts:
        if p.ref in swap or (own and getattr(p, "measured", None) is not None):
            fields = {}
            if p.ref in swap:
                fields["model"] = swap[p.ref]
            if own:
                fields["measured"] = None
            if fields:
                c = c.with_part(p.ref, **fields)
    return c


def unbiased(c):
    """A starter whose bias trimmer can't reach its target with this card: the trimmer left at
    the starter's rotation (the message says how far it could move the node)."""
    from solum.bias import BiasError

    try:
        sim.solve_bias(c)
        return c, ""
    except BiasError as err:
        for p in c.parts:
            if getattr(p, "bias_target", None) is not None:
                c = c.with_part(p.ref, bias_target=None)
        return c, str(err)


def run(stem, qs, label, c):
    c, note = unbiased(c)
    op = sim.op(c)
    v = {f"{q}.{pin}": op.voltages[sim.resolve(c, f"{q}.{pin}")] for q in qs for pin in "CBE"}
    ic = {q: op.currents.get(f"{q}.ic") for q in qs}
    row = {"variant": label, "op": {k: round(x, 4) for k, x in v.items()},
           "ic_mA": {q: round(abs(x) * 1e3, 4) for q, x in ic.items() if x is not None},
           "bias": {k: round(r, 4) for k, r in (op.bias or {}).items()}, "note": note}
    nodes = ["out"] + [f"{q}.C" for q in qs]
    for level in ("soft", "hard"):
        tr = sim.tran(c, nodes, level)
        st = {}
        for n in nodes:
            s = tr.stats[sim.resolve(c, n)]
            st[n] = {"gain_db": round(s.gain_db, 2), "amp_V": round(s.amplitude, 4), "pk+": round(s.peak_pos, 4),
                     "pk-": round(s.peak_neg, 4), "thd": round(s.clipping.thd, 3), "asym": round(s.clipping.asymmetry, 3)}
        row[level] = st
    return row


if __name__ == "__main__":
    out = {}
    for stem in sys.argv[1:] or list(STARTERS):
        qs, variants = STARTERS[stem]
        base = load_circuit(Path(f"library/starters/{stem}.json"))
        for own in (False, True):
            key = f"{stem} / {'cards own hFE and leakage' if own else 'starter measured hFE and leakage'}"
            out[key] = []
            for label, swap in variants:
                row = run(stem, qs, label, variant(base, swap, own))
                out[key].append(row)
                print(key, json.dumps(row), flush=True)
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / f"compare_{'_'.join(sys.argv[1:]) or 'all'}.json").write_text(json.dumps(out, indent=1))
