"""Phase 10 profiling: time the heavy requests through the API with the cache on a real disk.
Usage (in the dev container): python scripts/prof.py [--profile NAME] [starter ...]
"""

import cProfile
import json
import pstats
import shutil
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.config import load_settings

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "scratch" / "perf" / "cache"
DATA = REPO / "scratch" / "perf" / "data"


def client(fresh: bool) -> TestClient:
    if fresh:
        shutil.rmtree(CACHE, ignore_errors=True)
    s = load_settings(
        {"DATA_DIR": str(DATA), "CACHE_DIR": str(CACHE), "LIBRARY_DIR": str(REPO / "library")}
    )
    return TestClient(create_app(s))


def scenarios(c: TestClient, sid: str):
    circ = c.get(f"/api/starters/{sid}").json()["circuit"]
    yield "run", lambda: c.post("/api/run", json={"circuit": circ})
    yield "problems", lambda: c.post("/api/problems", json={"circuit": circ})
    yield "impedance", lambda: c.post("/api/impedance", json={"circuit": circ})
    st = {}

    def stages():
        r = c.post("/api/stages", json={"circuit": circ})
        st.update(r.json())
        return r

    yield "stages200", stages
    other = next((p["ref"] for p in circ["parts"] if p["type"] in ("bjt", "opamp", "jfet")), None)
    if other:
        yield (
            "click-part",
            lambda: (
                c.post("/api/part", json={"circuit": circ, "ref": other}),
                c.post(
                    "/api/run",
                    json={
                        "circuit": circ,
                        "nodes": [other + (".C" if other.startswith("Q") else ".out")],
                    },
                ),
            )[1],
        )
    yield "stages3k", lambda: c.post("/api/stages", json={"circuit": circ, "tone": 3000})
    yield "level", lambda: c.post("/api/stages/level", json={"circuit": circ, "amplitude": 0.5})
    rows = st.get("rows", [])
    stage = next((r["label"] for r in rows if r.get("role") == "gain stage"), None)
    if stage:
        yield "gain", lambda: c.post("/api/stages/gain", json={"circuit": circ, "ref": stage})
        yield "bias", lambda: c.post("/api/stages/bias", json={"circuit": circ, "ref": stage})
    clip = next((p["ref"] for p in circ["parts"] if p["type"] == "diode"), None)
    if clip:
        yield "clipper", lambda: c.post("/api/stages/clipper", json={"circuit": circ, "ref": clip})
    pot = next((p["ref"] for p in circ["parts"] if p["type"] == "pot"), None)
    if pot:
        import copy

        turned = copy.deepcopy(circ)
        for p in turned["parts"]:
            if p["ref"] == pot:
                p["rotation"] = 0.37
        yield "knob-run", lambda: c.post("/api/run", json={"circuit": turned})
        yield "knob-stages", lambda: c.post("/api/stages", json={"circuit": turned})


def main() -> None:
    args = sys.argv[1:]
    prof = None
    if args and args[0] == "--profile":
        prof, args = args[1], args[2:]
    out = {}
    for sid in args or ["ts808", "big-muff-pi-v3", "proco-rat"]:
        for mode in ("cold", "warm"):
            c = client(fresh=mode == "cold")
            for name, call in scenarios(c, sid):
                pr = cProfile.Profile() if prof == f"{name}-{mode}" else None
                t = time.perf_counter()
                if pr:
                    pr.enable()
                r = call()
                if pr:
                    pr.disable()
                dt = time.perf_counter() - t
                out.setdefault(f"{sid}:{name}", {})[mode] = round(dt, 3)
                if r.status_code != 200:
                    out[f"{sid}:{name}"]["err"] = r.text[:200]
                if pr:
                    pstats.Stats(pr).sort_stats("cumulative").print_stats(45)
    for k, v in out.items():
        print(f"{k:32s} {json.dumps(v)}")


main()
