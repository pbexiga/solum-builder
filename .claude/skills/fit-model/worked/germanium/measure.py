"""Measure a germanium-study card in ngspice (the project's pipeline) against its sheet:
run.sh measure.py OC71 [OC44 OC75]. Prints a markdown table (OK/MISS with numbers) and fills
the record's `validation` (the quantities tests/sim/model_checks.py knows) with the simulated
values. The card is loaded from this folder, beside library/models (nothing written there)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g  # noqa: E402
from checks import CHECKS  # noqa: E402
from solum.sim.native import native_engine  # noqa: E402
from tests.sim.model_checks import measure as std_measure  # noqa: E402

HERE = Path(".claude/skills/fit-model/worked/germanium")
engine = native_engine()
STD = ("hfe", "vbe", "vce_sat", "vbe_sat", "icbo", "iceo", "tester_hfe")


def run(models, mid, kind, c):
    if kind in STD:
        return std_measure(engine, models, models.get(mid), kind, c)
    if kind.endswith("_info") and kind[:-5] in STD:  # a line shown, not recorded
        return std_measure(engine, models, models.get(mid), kind[:-5], c)
    if kind == "ic_at_ib":
        return g.sim_ic_at_ib(engine, models, mid, c["ib"], c["vce"])
    if kind == "vbe_at_ie":
        return g.sim_vbe_at_ie(engine, models, mid, c["ie"], c["vce"])
    if kind == "vbe_at_ib":
        return g.sim_vbe_at_ib(engine, models, mid, c["ib"], c["vce"])
    if kind == "ic_at_vbe":
        return g.sim_ic_at_vbe(engine, models, mid, c["vbe"], c["vce"])
    if kind == "knee":
        return g.sim_knee(engine, models, mid, c["ic_set"], c["vce_set"], c["ic"])
    if kind == "small_hfe":
        return g.sim_small_hfe(engine, models, mid, c["ic"], c["vce"])
    raise ValueError(kind)


for mid in sys.argv[1:]:
    models = g.library_with({mid: str(HERE / f"{mid}.json")})
    rec = json.loads((HERE / f"{mid}.json").read_text())
    print(f"\n### {mid}\n\n| check | sim | min | typ | max | tol | result |\n|---|---|---|---|---|---|---|")
    validation, n_ok, n_miss = [], 0, 0
    for ch in CHECKS[mid]:
        x = run(models, mid, ch["kind"], ch["c"])
        d = ch.get("d", {})
        sc, unit = ch.get("scale", 1.0), ch.get("unit", "")
        line = g.check_line(ch["name"], x, d.get("min"), d.get("max"), d.get("typ"), d.get("tol"), unit, sc)
        if d.get("min") is not None or d.get("max") is not None or d.get("tol") is not None:
            n_ok, n_miss = (n_ok + 1, n_miss) if line.split("|")[-2].strip().startswith("OK") else (n_ok, n_miss + 1)
        print(line.replace("| OK", "| OK").replace(" |", f" |", 1))
        if ch["kind"] in STD:
            v = {"quantity": ch["kind"], "conditions": ch["c"], "simulated": float(f"{x:.6g}")}
            missed = "MISS" in line.split("|")[-2]
            if d and missed:  # a known miss: its limits kept in words, so the library's test doesn't assert them
                lim = ", ".join(f"{k} {d[k] * sc:.4g}{unit}" for k in ("min", "typ", "max") if d.get(k) is not None)
                v["datasheet"] = {"source": ch["src"], "note": f"Outside the sheet's line ({lim}): {ch.get('miss', 'see the fit notes')}"}
            elif d:
                v["datasheet"] = {k: d[k] for k in ("min", "typ", "max", "tol") if d.get(k) is not None} | {"source": ch["src"]}
            if ch.get("note"):
                v["note"] = ch["note"]
            validation.append(v)
    print(f"\n{mid}: {n_ok} OK, {n_miss} MISS (checks with limits or a tolerance)")
    rec["validation"] = validation
    from solum.models import ModelInfo

    ModelInfo.model_validate(rec)  # the record is in the library's shape
    (HERE / f"{mid}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
