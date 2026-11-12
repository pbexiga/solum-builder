"""Try a card before it goes in the library:
    python try_model.py TYPE ID CARD SPICE_NAME PINS [channels]
PINS: comma-separated roles in the subckt's order (opamp) or '' for a .model."""

import os
import sys
from pathlib import Path

from solum import model_checks as mc
from solum.models import Model, ModelInfo, ModelLibrary, Source, load_models
from solum.sim.native import native_engine

typ, mid, card_path, spice, pins = sys.argv[1:6]
channels = int(sys.argv[6]) if len(sys.argv) > 6 else 1
card = Path(card_path).read_text(encoding="utf-8", errors="replace").replace("\r", "")
info = ModelInfo(
    id=mid,
    type=typ,
    description="trial",
    spice_name=spice,
    kind="subckt" if pins else "model",
    pins=pins.split(",") if pins else [],
    card="x",
    source=Source(url="x", retrieved="x", licence="x"),
    channels=min(channels, 2),
)
lib = load_models([Path("library/models")])
models = ModelLibrary({**{k: lib.get(k) for k in lib.ids()}, mid: Model(info=info, card=card)})
m = models.get(mid)
eng = native_engine()

if os.environ.get("PSA"):
    eng._command("set ngbehavior=psa")
if typ == "opamp":
    for vs in [float(x) for x in os.environ.get("VS", "15").split(",")]:
        try:
            aol, gbw = mc.opamp_open_loop(eng, models, m, vs)
            sp, sn = mc.opamp_swing(eng, models, m, vs, 10e3)
            print(
                f"{mid} ±{vs}: aol {aol:.2f} dB  gbw {gbw / 1e6:.3f} MHz  swing headroom "
                f"+{sp:.3f} -{sn:.3f} "
                "V"
            )
        except Exception as e:
            print(f"{mid} ±{vs}: FAILED {e}")
            for msg in [m for m in getattr(e, "log", []) if "type mismatch" not in m][:40]:
                print("   ", msg)
            break
