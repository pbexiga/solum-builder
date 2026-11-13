"""FastAPI app: `/api/*` routes plus the static web UI.

Every error the user can cause comes back as `{"message": "<plain English>"}` with a 4xx
status; anything unexpected is logged here and answered with a plain 500 message, never
a traceback (AGENTS.md).
"""

import json
import logging
import queue
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, get_args

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field as Limit
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from solum import __version__
from solum.analysis.compare import CurveError, curves_from_db, influence
from solum.analysis.measures import features, readings
from solum.audio.assets import KINDS, AssetError, AssetLayer, AudioLibrary, Kind
from solum.audio.bundle import safe_file_name, zip_takes
from solum.audio.jobs import RenderJobs, spectra_key
from solum.audio.nam import NamError
from solum.audio.render import Inputs, RenderError, render_key
from solum.audio.wav import WavError
from solum.bias import BiasError
from solum.bias_sheet import bias_page, bias_sheet
from solum.build_notes import notes_page
from solum.cache import cache_from_settings, content_hash
from solum.circuit.connectivity import ConnectivityError
from solum.circuit.enclosures import SIZES as ENCLOSURE_SIZES
from solum.circuit.io import CircuitError, circuit_to_dict, load_circuit, parse_circuit
from solum.circuit.schema import Circuit, Trimmer, turns
from solum.circuit.switches import catalogue
from solum.config import Settings, load_settings
from solum.export import (
    OutFile,
    bom,
    bom_csv,
    bom_page,
    export_netlists,
    model_files,
    models_list,
    pdf,
    ready_to_build,
    schematic_page,
    zip_files,
)
from solum.filters import KINDS as FILTER_KINDS
from solum.filters import FilterError, filter_view
from solum.fixes import (
    FIXES_VERSION,
    Arranged,
    FixError,
    bias_options,
    bias_reach,
    clipper_options,
    gain_options,
)
from solum.guides import (
    GuideError,
    battery_guide,
    capacitor_guide,
    inductor_guide,
    pickup_guide,
)
from solum.library import BlockLibrary, Layer
from solum.linear import LinearError
from solum.live import NUDGE, Field, LiveError, live_view
from solum.manual import ManualError, load_manual, page_html
from solum.markings import (
    MarkingError,
    bands_value,
    read_cap_code,
    resistor_view,
    tables,
    value_view,
)
from solum.model_import import cards_in, check_apart, save_model, suggested_id
from solum.models import CHIP_TYPES, Model, ModelError, ModelType, Quantity
from solum.netlist import NetlistError
from solum.not_included import catalogue_entries, load_not_included
from solum.package import ReadyRow, Simulated, build_package
from solum.probe import (
    SWEEP_MAX,
    Progress,
    SweepError,
    impedance_view,
    knob_ranges,
    part_view,
    run_view,
    stage_levels,
    stage_waves,
    stages_view,
    sweep_view,
)
from solum.rules.run import RUN_ERRORS, CantSimulate, Checker, rule_book
from solum.settings_file import SettingsError, SettingsFile, cache_max_gb, with_preferences
from solum.sim.engine import EngineUnavailable, SimEngine, SimError, engine_from_settings
from solum.simulate import (
    MAX_AMPLITUDE,
    TONE_HZ,
    TONES,
    Simulator,
    model_library,
    simulator_from_settings,
)
from solum.store import CircuitStore, StoreError, blank_circuit, split_id
from solum.units import parse_value
from solum.view import circuit_view
from solum.wiring import wiring_page

log = logging.getLogger("solum.api")
SCHEMATIC_MAX = 8_000_000  # bytes: a drawn schematic is well under this (D-205)

USER_ERRORS = (
    CircuitError, ConnectivityError, NetlistError, BiasError, ModelError, StoreError, SweepError,
    CantSimulate, LiveError, LinearError, AssetError, NamError, RenderError, WavError,
    MarkingError, CurveError, FixError, SettingsError, FilterError,
)  # fmt: skip
# what makes a render request fail; a lookup (`cached_only`) answers "not rendered" instead
LOOKUP_MISSES = (*USER_ERRORS, SimError, HTTPException)
Level = Literal["soft", "med", "hard"]


class SettingsChange(BaseModel):
    """What Settings (or the page, for its preferences) changes; what is left out stays."""

    cache_max_gb: float | None = None
    preferences: dict[str, Any] | None = None  # a null forgets one


class RunRequest(BaseModel):
    circuit: dict[str, Any]
    nodes: list[str] = []
    level: Level = "med"


class PartRequest(BaseModel):
    circuit: dict[str, Any]
    ref: str
    level: Level = "med"


class CircuitRequest(BaseModel):
    circuit: dict[str, Any]


def check_tone(tone: float) -> None:
    """A tone the pane measures at, or a plain 422 (D-122)."""
    if tone not in TONES:
        listed = ", ".join(f"{t:g}" for t in TONES)
        raise HTTPException(422, f"Pick one of the test tones: {listed} Hz.")


class StagesRequest(BaseModel):
    circuit: dict[str, Any]
    tone: float = TONE_HZ  # Hz, one of TONES (D-122)
    progress: bool = False  # answer step by step, for a progress bar (`progressing`, D-127)


class LevelRequest(BaseModel):
    circuit: dict[str, Any]
    amplitude: float  # the guitar's peak, in volts
    tone: float = TONE_HZ


class WavesRequest(BaseModel):
    circuit: dict[str, Any]
    net: str  # a row's net
    tone: float = TONE_HZ


class ReachRequest(BaseModel):
    circuit: dict[str, Any]
    ref: str  # a trimmer with a bias target


class FixRequest(BaseModel):
    circuit: dict[str, Any]
    ref: str  # the stage or clipper to change
    progress: bool = False  # answer step by step, for a progress bar (`progressing`, D-123)


class BiasRequest(FixRequest):
    target: float | None = None  # where to put it, 0 (bottom of its room) to 1 (top); None centres


class ArrangedIn(BaseModel):
    key: str
    circuit: dict[str, Any]
    series: list[tuple[str, str, str, str]]  # new ref, its pin on the diode's, diode, its pin
    room: dict[str, Any] | None = None  # the sheet with room made first, if it was


class ClipperRequest(FixRequest):
    arranged: list[ArrangedIn] = []  # placed by the browser (D-124)


class CreateRequest(BaseModel):
    circuit: dict[str, Any] | None = None  # None: a blank circuit
    name: str | None = None


class BlockRequest(BaseModel):
    circuit: dict[str, Any]
    name: str


class InfoRequest(BaseModel):
    """File → Properties: what can change about a saved circuit or block (D-075)."""

    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    final: bool | None = None


class Control(BaseModel):
    ref: str
    field: Field


class LiveRequest(BaseModel):
    """What a value slider or knob needs to redraw the curves while it moves (D-081)."""

    circuit: dict[str, Any]
    nets: list[str] = []  # the nets whose curves are shown
    controls: list[Control]
    steps: dict[str, list[str | float]] = {}  # value sliders' steps to keep, by "REF.value"
    nudge: bool = False  # also every part nudged, for part influence (Phase 8b)


class CurveRequest(BaseModel):
    """A curve the browser solved (dB per frequency), to be measured (Phase 8b, D-097)."""

    freq: list[float]
    db: list[float]


class InfluenceRequest(BaseModel):
    """The curve and the curve with each part nudged, solved in the browser (D-097)."""

    freq: list[float]
    base: list[float]
    nudged: dict[str, list[float]]
    nudge: float = NUDGE
    at: float | None = None  # sort by the change at this frequency
    avoid: list[str] = []  # parts Edit curve's level moves leave out: knobs, bias parts


class KnobsRequest(BaseModel):
    circuit: dict[str, Any]
    net: str


class SweepRequest(BaseModel):
    circuit: dict[str, Any]
    ref: str
    field: str = "value"
    values: list[str]
    nodes: list[str] = []
    level: Level = "med"


class AssetRef(BaseModel):
    id: str
    layer: AssetLayer = "core"


class RenderRequest(BaseModel):
    """A clip through the circuit (None: dry, the guitar straight into the amp), then an
    amp capture and a cab IR if picked (D-083)."""

    circuit: dict[str, Any] | None = None
    clip: AssetRef
    capture: AssetRef | None = None
    ir: AssetRef | None = None
    level: Level = "med"
    input_db: float = 0.0  # the amp's Input trim (checked by the render, `TRIM_DB`)
    pump_ripple: bool = False  # charge pumps switch: their whine heard, ~10x slower
    cached_only: bool = False  # look it up only: a take already rendered, never a new render


class ZipTake(BaseModel):
    key: str
    file: str


class ZipRequest(BaseModel):
    """Finished takes by cache key, each with its file name in the zip, and text files to
    go beside them (what each take was made from)."""

    name: str
    takes: list[ZipTake]
    files: dict[str, str] = {}


class ReadyRowRequest(BaseModel):
    severity: Literal["error", "warning", "info"]
    text: str = Limit(max_length=2000)


class PackageRequest(BaseModel):
    """The build package (D-210): the schematic the browser drew of the last save, and the
    Ready to build rows it showed."""

    svg: str = Limit(max_length=SCHEMATIC_MAX)
    ready: list[ReadyRowRequest] = Limit(default_factory=list, max_length=500)
    dismissed: int = Limit(0, ge=0)


class ModelImportRequest(BaseModel):
    """Tools → Add a model (9c): a file's text and name; with a `card`, the card to add,
    as which part, under what id, checked and (with `save`) saved."""

    text: str = Limit(max_length=2_000_000)  # a SPICE library, not a dump
    filename: str
    card: str = ""
    part_type: ModelType = "bjt"
    id: str = ""
    pins: list[str] | None = None  # an op-amp's: the pin on each node of its .subckt
    channels: int = 1  # an op-amp's: how many to a package
    save: bool = False


class RenderSweepRequest(RenderRequest):
    """The same render at several rotations of one pot (rendered in parallel)."""

    ref: str
    rotations: list[float]


class SweepCheckRequest(BaseModel):
    """A sweep's positions, to check for a saturated stage before rendering them."""

    circuit: dict[str, Any]
    ref: str
    rotations: list[float]


def health_report(engine: SimEngine | None, problem: str | None) -> dict[str, Any]:
    """What `/api/health` returns: app version and which simulator is active."""
    if engine is None:
        return {"status": "degraded", "version": __version__, "engine": None, "message": problem}
    return {
        "status": "ok",
        "version": __version__,
        "engine": engine.name,
        "ngspice": engine.version(),
    }


def attachment(data: bytes, media: str, name: str, **headers: str) -> Response:
    """A file to save under `name` (made safe for the header)."""
    disposition = f'attachment; filename="{safe_file_name(name)}"'
    return Response(data, media_type=media, headers={**headers, "Content-Disposition": disposition})


CHECK_AGAIN = {"Cache-Control": "no-cache"}  # keep a copy, but ask if it changed before using it


def page(html: str) -> Response:
    """A page made here (opens in a tab, not downloaded); never shown from an old copy."""
    return Response(html, media_type="text/html; charset=utf-8", headers=CHECK_AGAIN)


class _Checked(StaticFiles):
    """The page's own files, each asked for again on every load (answered 304 when it hasn't
    changed). Without this a browser guesses how long to keep each script, so after an
    update new code imports from old and the page stops before drawing (D-291)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update(CHECK_AGAIN)
        return response


def starter_paths(library_dir: Path) -> dict[str, Path]:
    """Starter circuit id → file (`library/starters/<id>.json`)."""
    return {p.stem: p for p in sorted((library_dir / "starters").glob("*.json"))}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    try:
        engine: SimEngine | None = engine_from_settings(settings)
        problem = None
    except EngineUnavailable as err:
        engine, problem = None, str(err)
    renders = cache_from_settings(settings)  # the one cache: simulations, renders, searches
    kept = SettingsFile(settings.data_dir)  # what Settings changed, and the page's preferences
    sim = simulator_from_settings(settings, engine, renders) if engine else None
    models = sim.models if sim else model_library(settings)
    starters = starter_paths(settings.library_dir)
    not_included = load_not_included(settings.library_dir / "models")
    store = CircuitStore(settings.data_dir, settings.cache_dir)
    store.sync()  # files edited while the app was off are re-indexed now
    library = BlockLibrary(settings.library_dir / "blocks", settings.data_dir, settings.cache_dir)
    checker = Checker(rule_book(settings.library_dir), models)
    audio = AudioLibrary(settings.library_dir / "audio", settings.data_dir)
    jobs = RenderJobs(settings, renders)

    # the guitar's text on the schematic names its pickup (D-137)
    try:
        pickup_names = {p.kind: p.name for p in pickup_guide(settings.library_dir).pickups}
    except GuideError:  # a broken guide: the pickup's name stays "pickup"
        pickup_names = {}

    def view_of(circuit: Circuit) -> dict[str, Any]:
        return circuit_view(circuit, models, pickup_names)

    def file_view(circuit: Circuit, kind: Literal["circuit", "block"],
                  layer: Literal["user", "core", "starter"]) -> dict[str, Any]:  # fmt: skip
        """A saved circuit's or block's view with `file`: what it is, where its file is
        (`<data>/…` for the user's, `<core>/…` and `<starters>/…` for the app's), when it
        was saved, and whether it can be changed (D-075)."""
        out = view_of(circuit)
        name = f"{circuit.id}.json"
        own = store if kind == "circuit" else library.user
        out["file"] = {
            "kind": kind,
            "layer": layer,
            "path": {
                "user": f"<data>/{own.kind}/{name}",
                "core": f"<core>/blocks/{name}",
                "starter": f"<starters>/{name}",
            }[layer],
            "saved": own.modified(circuit.id) if layer == "user" else None,
            "readonly": layer != "user" or circuit.final,
            "link": {
                "user": own.link(circuit.id),
                "core": library.link(circuit.id, "core"),
                "starter": circuit.id,
            }[layer],
        }
        # the current version links by its short id, which has no version in it
        out["file"]["current"] = split_id(out["file"]["link"])[1] is None
        return out

    app = FastAPI(title="Solum Builder", version=__version__)
    app.state.engine = engine

    def error_text(err: BaseException) -> str:
        """What the page shows for an error: a user error's own words, a failed run
        explained by the error rules (D-077), or a plain line (the details go to the log)."""
        if isinstance(err, SimError):
            return checker.message(err)
        if isinstance(err, StarletteHTTPException):
            return str(err.detail)
        if isinstance(err, USER_ERRORS):
            return str(err)
        log.exception("Unexpected error", exc_info=err)
        return "Something went wrong inside Solum Builder. The server log has details."

    async def user_error(_request: Request, err: Exception) -> JSONResponse:
        return JSONResponse({"message": error_text(err)}, status_code=422)

    for error in (*USER_ERRORS, SimError):
        app.add_exception_handler(error, user_error)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, err: StarletteHTTPException) -> JSONResponse:
        return JSONResponse({"message": error_text(err)}, status_code=err.status_code)

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, err: Exception) -> JSONResponse:
        return JSONResponse({"message": error_text(err)}, status_code=500)

    def progressing(asked: bool, work: Callable[[Progress], dict[str, Any]]) -> Any:
        """A search's answer (D-123). Asked for its progress, one JSON line per step
        (`{"done", "of"}`), then `{"result"}`, or `{"message"}` for an error found on the
        way; an error before the first step is the usual 422. Otherwise just the result."""
        if not asked:
            return work(lambda _done, _of: None)
        lines: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()

        def run() -> None:
            try:
                lines.put({"result": work(lambda done, of: lines.put({"done": done, "of": of}))})
            except Exception as err:  # told to the page as a message line
                lines.put(err)

        threading.Thread(target=run, daemon=True).start()
        first = lines.get()
        if isinstance(first, BaseException):
            raise first

        def body() -> Iterator[str]:
            item: dict[str, Any] | BaseException = first
            while not isinstance(item, BaseException) and "result" not in item:
                yield json.dumps(item) + "\n"
                item = lines.get()
            text = {"message": error_text(item)} if isinstance(item, BaseException) else item
            yield json.dumps(text) + "\n"

        return StreamingResponse(body(), media_type="application/x-ndjson")

    def searched(
        kind: str, req: FixRequest, s: Simulator, work: Callable[[Progress], dict[str, Any]]
    ) -> Any:
        """A fix search's answer (`progressing`), kept in the cache by the request (circuit,
        stage, aim or arrangements), the engine and the models, so asking again for the
        same circuit is instant; any change to it is a new key (D-127)."""
        asked = json.dumps(req.model_dump(exclude={"progress"}), sort_keys=True)
        key = content_hash(FIXES_VERSION, kind, asked, s.engine.name, s.engine.version(),
                           s.models.fingerprint)  # fmt: skip
        kept = renders.get_bytes(key)
        if kept is not None:
            found: dict[str, Any] = json.loads(kept)
            return progressing(req.progress, lambda _step: found)

        def run(step: Progress) -> dict[str, Any]:
            out = work(step)
            renders.put_bytes(key, json.dumps(out).encode())
            return out

        return progressing(req.progress, run)

    def require_sim() -> Simulator:
        if sim is None:
            raise HTTPException(503, problem or "The simulator isn't available.")
        return sim

    def simulator(circuit: Circuit) -> Simulator:
        """The simulator, once the drawing is fit to simulate (CantSimulate if not)."""
        runner = require_sim()
        checker.require_runnable(circuit)
        return runner

    def runnable(data: dict[str, Any]) -> tuple[Simulator, Circuit]:
        """A posted circuit with the simulator for it (`simulator`)."""
        circuit = parse_circuit(data)
        return simulator(circuit), circuit

    def known(cid: str) -> str:
        """A saved circuit's id as asked for, or a plain 404."""
        if not store.has(cid):
            raise HTTPException(404, f"There's no saved circuit called {cid!r}.")
        return cid

    def take(key: str, what: str = "That render") -> bytes:
        """A finished render's bytes from the cache, or a plain 404."""
        data = renders.get_bytes(key) if key.isalnum() else None
        if data is None:
            raise HTTPException(404, f"{what} isn't in the cache any more; render again.")
        return data

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return health_report(engine, problem)

    def settings_view() -> dict[str, Any]:
        saved = kept.load()
        return {
            "data_dir": str(settings.data_dir.resolve()),
            "cache_dir": str(settings.cache_dir.resolve()),
            "host_data_dir": settings.host_data_dir,
            "host_cache_dir": settings.host_cache_dir,
            "cache_max_gb": cache_max_gb(settings, saved),
            "cache_used_bytes": renders.size(),
            "can_move_folders": settings.can_move_folders,
            "preferences": saved.preferences,
        }

    @app.get("/api/settings")
    def read_settings() -> dict[str, Any]:
        """What File → Settings… shows (D-310), and the page's preferences (D-311)."""
        return settings_view()

    @app.put("/api/settings")
    def change_settings(change: SettingsChange) -> dict[str, Any]:
        """Keep a new largest cache size (it holds at once: the oldest results go now if
        the cache is over it) and/or some of the page's preferences."""
        kept.change(change.cache_max_gb, change.preferences)
        if change.cache_max_gb is not None:
            renders.trim()
        return settings_view()

    @app.get("/api/starters")
    def list_starters() -> list[dict[str, str]]:
        found = []
        for sid, path in starters.items():
            c = load_circuit(path)
            found.append({"id": sid, "name": c.name, "description": c.description})
        return found

    def saved_view(c: Circuit, own: CircuitStore) -> dict[str, Any]:
        """What a save answers: the file's id, name, version tag as saved, and the id to
        link to (the short one for a current version, D-076)."""
        return {"id": c.id, "name": c.name, "version": str(c.version), "final": c.final,
                "link": own.link(c.id)}  # fmt: skip

    @app.get("/api/starters/{sid}")
    def open_starter(sid: str) -> dict[str, Any]:
        if sid not in starters:
            raise HTTPException(404, f"There's no starter circuit called {sid!r}.")
        return file_view(load_circuit(starters[sid]), "circuit", "starter")

    @app.get("/api/models")
    def list_models() -> dict[str, list[str]]:
        """Model ids by part type, for the inspector's model dropdown, under `yours` the ids
        the user added (the dropdown lists them first, 9c), and under `zeners` the diodes
        that are zeners (a diode set to one is named Z)."""
        by_type = {t: models.ids(t) for t in get_args(ModelType)}
        return by_type | {
            "yours": [i for i in models.ids() if models.get(i).yours],
            "zeners": [i for i in models.ids("diode") if models.get(i).zener],
        }

    @app.get("/api/models/catalogue")
    def model_catalogue() -> list[dict[str, Any]]:
        """Every model the app knows, by type then id, with its datasheet link and caveats
        (Tools → Parts and datasheets, 9c: `Model.catalogue_entry`), then the cards we may
        not ship, each after a stock model of the same id (`not_included`)."""
        entries = [models.get(i).catalogue_entry() for i in models.ids()]
        entries += catalogue_entries(not_included, models)
        return sorted(entries, key=lambda e: (e["type"], e["id"], e["origin"] == "excluded"))

    @app.post("/api/models/import")
    def import_model(req: ModelImportRequest) -> dict[str, Any]:
        """The cards in an uploaded file (an op-amp `.subckt` with its nodes); or, for one of
        them, its quick check, and with `save` it joins the user's models (`DATA_DIR/models`)
        and this library."""
        if not req.card:
            found = cards_in(req.text)
            return {"cards": [{"name": f.name, "spice_type": f.spice_type,
                               "part_types": list(f.part_types), "nodes": list(f.nodes),
                               "comment": f.comment, "guess": list(f.guess),
                               "suggested": suggested_id(f.name, models)}
                              for f in found]}  # fmt: skip
        require_sim()
        added = check_apart(req.text, req.card, req.part_type, req.id or req.card,
                            req.filename, models, req.pins, req.channels,
                            settings.ngspice_library)  # fmt: skip
        if req.save:
            save_model(added.model, settings.data_dir)
            models.add(added.model)
        return {"model": added.model.catalogue_entry(), "checks": added.checks,
                "fixes": added.fixes, "saved": req.save}  # fmt: skip

    @app.get("/api/models/jfets")
    def jfet_specs() -> dict[str, dict[str, Any]]:
        """Each level-1 JFET model's Idss and Vp, where a JFET form's measured values start,
        and the datasheet's range for each (`range`, where the record has one)."""
        return _specs("jfet", lambda m: m.jfet_spec(), ("idss", "vp"))

    @app.get("/api/models/bjts")
    def bjt_specs() -> dict[str, dict[str, Any]]:
        """Each transistor model card's gain and leakage, where a transistor form's measured
        ones start (D-130), and the datasheet's hFE range (`range`, where it has one)."""
        return _specs("bjt", lambda m: m.bjt_spec(), ("hfe",))

    @app.get("/api/models/chips")
    def chip_specs() -> dict[str, dict[str, Any]]:
        """Each chip model's chip (D-140, D-180: op-amps, inverters, OTAs): its type, how
        many units, the pins it simulates and its datasheet pin numbers, for their forms."""
        return {
            i: spec for kind in CHIP_TYPES for i in models.ids(kind)
            if (spec := models.get(i).chip_spec())
        }  # fmt: skip

    def _specs(
        kind: ModelType,
        spec: Callable[[Model], dict[str, float | bool] | None],
        ranged: tuple[Quantity, ...],
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for i in models.ids(kind):
            own = spec(models.get(i))
            if own is not None:
                found = {q: models.get(i).datasheet_range(q) for q in ranged}
                out[i] = {**own, "range": {q: r for q, r in found.items() if r is not None}}
        return out

    @app.get("/api/guides/capacitors")
    def capacitors() -> dict[str, Any]:
        """Help → Choosing capacitors and the inspector's kind hints (D-095)."""
        return capacitor_guide(settings.library_dir).model_dump()

    @app.get("/api/guides/pickups")
    def pickups() -> dict[str, Any]:
        """The guitar input's pickup choices, measured (D-096)."""
        return pickup_guide(settings.library_dir).model_dump()

    @app.get("/api/guides/inductors")
    def inductors() -> dict[str, Any]:
        """The inductor form's presets: measured wah inductors (D-173)."""
        return inductor_guide(settings.library_dir).model_dump()

    @app.get("/api/guides/batteries")
    def batteries() -> dict[str, Any]:
        """The battery's states as it drains, from its datasheet (D-143)."""
        return battery_guide(settings.library_dir).model_dump()

    @app.get("/api/switches")
    def switch_types() -> list[dict[str, object]]:
        """Every switch type: the switch form's picker and each pole's lugs (D-143)."""
        return catalogue()

    @app.get("/api/tools")
    def tool_tables() -> dict[str, Any]:
        """The colour code, the converter's quantities and the filter calculator's kinds,
        for the Tools pages' pickers."""
        return {**tables(), "filters": FILTER_KINDS}

    @app.get("/api/tools/convert")
    def convert(unit: str, value: str = "", code: str = "") -> dict[str, Any]:
        """Tools → Unit converter: a value (`22n`) or a capacitor code (`223`) in each unit."""
        try:
            if code:
                read = read_cap_code(code)
                return {**value_view(read.farads, "F"), "tolerance": read.tolerance}
            return value_view(parse_value(value), unit)
        except ValueError as err:
            raise MarkingError(str(err)) from None

    @app.get("/api/tools/resistor")
    def resistor(value: str = "", bands: str = "") -> dict[str, Any]:
        """Tools → Resistor colour code, from a value (`4k7`) or bands (`yellow,violet,red`)."""
        if bands:
            ohms, tolerance = bands_value(bands.split(","))
            return resistor_view(ohms, tolerance)
        try:
            ohms = parse_value(value)
        except ValueError as err:
            raise MarkingError(str(err)) from None
        return resistor_view(ohms)

    @app.get("/api/tools/filter")
    def rc_filter(kind: str, r: str, c: str, r2: str = "", c2: str = "") -> dict[str, Any]:
        """Tools → Filter calculator (D-319): an RC high-pass or low-pass from `r` and `c`
        as typed, and a second pair to compare."""
        return filter_view(kind, r, c, r2, c2)

    @app.post("/api/view")
    def view(req: CircuitRequest) -> dict[str, Any]:
        """The circuit view of an edited circuit (the editor posts after every edit)."""
        return view_of(parse_circuit(req.circuit))

    @app.get("/api/circuits")
    def list_circuits(q: str = "") -> list[dict[str, Any]]:
        return [asdict(e) for e in store.entries(q)]

    @app.get("/api/blank")
    def blank() -> dict[str, Any]:
        """The start page: an unsaved sheet with a guitar input and an amp output."""
        return view_of(blank_circuit("Untitled"))

    @app.get("/api/circuits/{cid}")
    def open_circuit(cid: str) -> dict[str, Any]:
        return file_view(store.load(known(cid)), "circuit", "user")

    @app.post("/api/circuits")
    def create_circuit(req: CreateRequest) -> dict[str, Any]:
        """Save as a new circuit (new id from the name): a copy of `circuit` (also how a
        starter is copied), or a blank one."""
        source = parse_circuit(req.circuit) if req.circuit else blank_circuit(req.name or "")
        created = store.create(source, req.name)
        return file_view(created, "circuit", "user")

    @app.put("/api/circuits/{cid}")
    def save_circuit(cid: str, req: CircuitRequest) -> dict[str, Any]:
        circuit = parse_circuit({**req.circuit, "id": store.resolve(cid) or cid})
        if circuit.starter:
            raise HTTPException(422, "Starters are read-only. Save this as a new circuit.")
        known(cid)
        return saved_view(store.save(circuit), store)

    @app.patch("/api/circuits/{cid}")
    def circuit_info(cid: str, req: InfoRequest) -> dict[str, Any]:
        """Rename (the file follows), describe, tag, lock or unlock a saved circuit."""
        return file_view(store.update_info(cid, **req.model_dump()), "circuit", "user")

    @app.post("/api/circuits/{cid}/major")
    def circuit_major(cid: str) -> dict[str, Any]:
        """Mark the current version final and carry on at the next major (D-076)."""
        current, final = store.new_major(cid)
        return {**file_view(current, "circuit", "user"), "final_copy": saved_view(final, store)}

    @app.delete("/api/circuits/{cid}")
    def delete_circuit(cid: str) -> dict[str, Any]:
        found = store.resolve(known(cid)) or cid
        store.delete(found)
        return {"deleted": found}

    @app.get("/api/blocks")
    def list_blocks(q: str = "") -> list[dict[str, Any]]:
        """Blocks to insert: My Blocks first, then core."""
        return [asdict(e) for e in library.entries(q)]

    @app.get("/api/blocks/{bid}")
    def open_block(bid: str, layer: Layer | None = None) -> dict[str, Any]:
        """A block's view (its circuit is what gets pasted), with its layer and version."""
        block, found = library.get(bid, layer)
        return file_view(block, "block", found)

    @app.post("/api/blocks")
    def create_block(req: BlockRequest) -> dict[str, Any]:
        """Save a circuit (or a selection from one) as a new block in My Blocks."""
        return file_view(library.create(parse_circuit(req.circuit), req.name), "block", "user")

    @app.put("/api/blocks/{bid}")
    def save_block(bid: str, req: CircuitRequest) -> dict[str, Any]:
        saved = library.save(parse_circuit({**req.circuit, "id": library.user.resolve(bid) or bid}))
        return saved_view(saved, library.user)

    @app.patch("/api/blocks/{bid}")
    def block_info(bid: str, req: InfoRequest) -> dict[str, Any]:
        """Rename (the file follows), describe, tag, lock or unlock one of My blocks."""
        library.get(bid, "user")  # core blocks never change
        return file_view(library.user.update_info(bid, **req.model_dump()), "block", "user")

    @app.post("/api/blocks/{bid}/major")
    def block_major(bid: str) -> dict[str, Any]:
        """Freeze the block as "<name> v<major>" (final) and carry on at the next major."""
        library.get(bid, "user")
        current, final = library.user.new_major(bid)
        final_copy = saved_view(final, library.user)
        return {**file_view(current, "block", "user"), "final_copy": final_copy}

    @app.delete("/api/blocks/{bid}")
    def delete_block(bid: str) -> dict[str, Any]:
        library.delete(bid)
        return {"deleted": bid}

    @app.post("/api/live")
    def live(req: LiveRequest) -> dict[str, Any]:
        """The linear system and slider steps for a live curve while a control moves."""
        circuit = parse_circuit(req.circuit)
        controls = [(c.ref, c.field) for c in req.controls]
        try:
            runner = simulator(circuit)
        except CantSimulate:
            # half drawn: no curve yet, but a slider still changes the value (D-164)
            return live_view(require_sim(), circuit, req.nets, controls, req.steps, simulate=False)
        return live_view(runner, circuit, req.nets, controls, req.steps, req.nudge)

    @app.post("/api/curve")
    def curve(req: CurveRequest) -> dict[str, Any]:
        """A live curve's features and readings, so they follow a slider (D-097)."""
        freq, (h,) = curves_from_db(req.freq, req.db)
        return {"features": features(freq, h), "readings": readings(freq, h)}

    @app.post("/api/influence")
    def part_influence(req: InfluenceRequest) -> dict[str, Any]:
        """Which nudged parts move the curve most, and what they move (D-097)."""
        refs = list(req.nudged)
        freq, (base, *nudged) = curves_from_db(req.freq, req.base, *req.nudged.values())
        nudged_by = dict(zip(refs, nudged, strict=True))
        return influence(freq, base, nudged_by, req.nudge, req.at, req.avoid)

    @app.post("/api/knobs")
    def knobs(req: KnobsRequest) -> dict[str, Any]:
        """Where each knob acts on the curve at a net, through ngspice (Phase 8b)."""
        return knob_ranges(*runnable(req.circuit), req.net)

    @app.post("/api/stages")
    def stages(req: StagesRequest) -> Any:
        """The Bias & headroom pane: each stage's bias and, at every pick level, how close
        each stage and clipper is to clipping, at one of the test tones (Phase 8c,
        D-106, D-122)."""
        check_tone(req.tone)
        s, circuit = runnable(req.circuit)
        return progressing(req.progress, lambda step: stages_view(s, circuit, req.tone, step))

    @app.post("/api/stages/level")
    def stages_level(req: LevelRequest) -> dict[str, Any]:
        """Each stage's peak with the guitar at one level: a point of the pane's level
        in -> out curve, which the page asks for a dozen times (Phase 8c)."""
        if not 0 < req.amplitude <= MAX_AMPLITUDE:
            raise HTTPException(422, f"Pick an input level above 0 V, up to {MAX_AMPLITUDE:g} V.")
        check_tone(req.tone)
        return stage_levels(*runnable(req.circuit), req.amplitude, req.tone)

    @app.post("/api/trimmer/reach")
    def trimmer_reach(req: ReachRequest) -> dict[str, Any]:
        """The volts a targeted trimmer can hold its node at, turned end to end, and
        whether its target is among them: its form checks a new target so (D-127)."""
        s, circuit = runnable(req.circuit)
        reach = s.target_reach(circuit, req.ref)
        return {"ref": reach.ref, "node": reach.node, "low": reach.low, "high": reach.high,
                "text": reach.text, "holds": reach.reached}  # fmt: skip

    @app.post("/api/stages/waves")
    def stages_waves(req: WavesRequest) -> dict[str, Any]:
        """A block's waveform at the three picks, for its card (D-127): the pane's own
        transients, from the cache once it has measured the tone."""
        check_tone(req.tone)
        return stage_waves(*runnable(req.circuit), req.net, req.tone)

    @app.post("/api/stages/bias")
    def stages_bias(req: BiasRequest) -> Any:
        """What moves one stage's bias to the middle (Centre, D-119) or to a target (Bias
        to…, D-123): a trimmer's turn or target, or a resistor value, each with where it
        then sits and what else changes."""
        if req.target is not None and not 0 <= req.target <= 1:
            raise HTTPException(422, "Pick a place from the bottom (0) to the top (1) of its room.")
        s, circuit = runnable(req.circuit)
        return searched(
            "bias", req, s, lambda step: bias_options(s, circuit, req.ref, req.target, step)
        )

    @app.post("/api/stages/reach")
    def stages_reach(req: FixRequest) -> dict[str, Any]:
        """How far Bias to… can move one stage's bias (D-123): the part of its bias bar
        any one part next to it reaches."""
        return bias_reach(*runnable(req.circuit), req.ref)

    @app.post("/api/stages/gain")
    def stages_gain(req: FixRequest) -> Any:
        """The parts that move one stage's own gain most, a slider of values for each
        resistor and pot, with what clips first at each (D-123, D-125)."""
        s, circuit = runnable(req.circuit)
        return searched(
            "gain", req, s, lambda step: gain_options(s, circuit, req.ref, progress=step)
        )

    @app.post("/api/stages/clipper")
    def stages_clipper(req: ClipperRequest) -> Any:
        """Diodes to swap into one clipper, and the arrangements the browser placed (two
        in series, 2 + 1, a resistor), each measured at a hard pick (D-118, D-123, D-124)."""
        s, circuit = runnable(req.circuit)
        arranged = [
            Arranged(
                a.key,
                parse_circuit(a.circuit),
                tuple(a.series),
                parse_circuit(a.room) if a.room else None,
            )
            for a in req.arranged
        ]
        return searched(
            "clipper",
            req,
            s,
            lambda step: clipper_options(s, circuit, req.ref, progress=step, arranged=arranged),
        )

    @app.post("/api/sweep")
    def sweep(req: SweepRequest) -> dict[str, Any]:
        s, circuit = runnable(req.circuit)
        return sweep_view(s, circuit, req.ref, req.field, req.values, req.nodes, req.level)

    @app.post("/api/run")
    def run(req: RunRequest) -> dict[str, Any]:
        return run_view(*runnable(req.circuit), req.nodes, req.level)

    @app.post("/api/impedance")
    def impedance(req: CircuitRequest) -> dict[str, Any]:
        """The View → Impedance overlay (D-127): Zin at the guitar, Zout at the amp."""
        return impedance_view(*runnable(req.circuit))

    @app.post("/api/problems")
    def problems(req: CircuitRequest) -> dict[str, Any]:
        """Every problem in the circuit (SPEC §4): the drawing, then the operating point
        (`checked_op` says whether it ran) or the failed run explained."""
        found, checked = checker.check(parse_circuit(req.circuit), sim)
        return {"problems": [asdict(p) for p in found], "checked_op": checked}

    @app.post("/api/part")
    def part(req: PartRequest) -> dict[str, Any]:
        circuit = parse_circuit(req.circuit)
        if req.ref not in {p.ref for p in circuit.parts}:
            raise HTTPException(404, f"There's no part {req.ref} in this circuit.")
        return part_view(simulator(circuit), circuit, req.ref, req.level, pickup_names)

    @app.get("/api/audio")
    def list_audio() -> dict[str, list[dict[str, Any]]]:
        """Clips, amp captures and cab IRs: the user's uploads, then the built-in ones."""
        return {kind: [asdict(e) for e in audio.entries(kind)] for kind in KINDS}

    @app.post("/api/audio/{kind}")
    async def upload_audio(kind: Kind, name: str, request: Request) -> dict[str, Any]:
        """Upload a clip (WAV), an amp capture (.nam) or a cab IR (WAV): the file is the
        request body, `name` its file name (no multipart, so no extra dependency)."""
        return asdict(audio.add(kind, name, await request.body()))

    @app.delete("/api/audio/{kind}/{asset_id}")
    def delete_audio(kind: Kind, asset_id: str) -> dict[str, Any]:
        audio.delete(kind, asset_id)
        return {"deleted": asset_id}

    def render_inputs(req: RenderRequest) -> Inputs:
        def read(kind: Kind, ref: AssetRef | None) -> bytes | None:
            return audio.read(kind, ref.id, ref.layer) if ref else None

        clip = read("clips", req.clip)
        assert clip is not None
        return Inputs(clip, read("captures", req.capture), read("irs", req.ir), req.level,
                      req.input_db, req.pump_ripple)  # fmt: skip

    def start_render(
        circuit: Circuit | None, inputs: Inputs, label: str, cached_only: bool = False
    ) -> dict[str, Any] | None:
        runner = simulator(circuit) if circuit is not None else require_sim()
        key = render_key(runner, circuit, inputs, settings.cache_dir)
        data = circuit_to_dict(circuit) if circuit else None
        job = jobs.submit(key, label, data, inputs, cached_only)
        return job.view() if job else None

    @app.post("/api/render")
    def start(req: RenderRequest) -> dict[str, Any] | None:
        """Start a render job (or answer at once from the cache): poll `/api/render/{id}`,
        then fetch `/api/render/audio/{key}.wav`. With `cached_only`, null unless it's
        already rendered (or rendering), and null rather than an error."""
        try:
            circuit = parse_circuit(req.circuit) if req.circuit is not None else None
            return start_render(circuit, render_inputs(req), "pedal" if circuit else "dry",
                                req.cached_only)  # fmt: skip
        except LOOKUP_MISSES:
            if req.cached_only:
                return None
            raise

    @app.post("/api/render/sweep")
    def start_sweep(req: RenderSweepRequest) -> list[dict[str, Any] | None]:
        """One render job per rotation of the pot `ref`; they run side by side. With
        `cached_only`, null for each position not already rendered, never an error."""
        try:
            return sweep_jobs(req)
        except LOOKUP_MISSES:
            if req.cached_only:
                return [None] * len(req.rotations)
            raise

    def swept(data: dict[str, Any] | None, ref: str, rotations: list[float]) -> Circuit:
        """The circuit a sweep turns `ref` in, or a plain error: a pot or trimmer, and
        not a trimmer its bias target sets (every position would sound the same)."""
        if data is None:
            raise HTTPException(422, "A render sweep needs a circuit.")
        circuit = parse_circuit(data)
        if not 1 <= len(rotations) <= SWEEP_MAX:
            raise HTTPException(422, f"Pick 1 to {SWEEP_MAX} positions.")
        try:
            knob = circuit.part(ref)
        except KeyError:
            raise HTTPException(404, f"There's no part {ref} in this circuit.") from None
        if not turns(knob):
            raise HTTPException(422, f"{ref} isn't a pot; only pots can be swept.")
        if isinstance(knob, Trimmer) and knob.bias_target is not None:
            raise HTTPException(422, f"{ref} is set by its bias target, so turning it changes "
                                "nothing. Open it and remove the target to sweep it.")  # fmt: skip
        return circuit

    @app.post("/api/render/sweep/check")
    def check_sweep(req: SweepCheckRequest) -> list[list[dict[str, str]]]:
        """Per position, the stages saturated or cut off at DC: a take there is a broken
        bias, not a sound (the trimmer sweep marks them, D-198)."""
        circuit = swept(req.circuit, req.ref, req.rotations)
        sim = simulator(circuit)
        return [
            [asdict(s) for s in sim.saturated(circuit.with_part(req.ref, rotation=r))]
            for r in req.rotations
        ]

    def sweep_jobs(req: RenderSweepRequest) -> list[dict[str, Any] | None]:
        circuit = swept(req.circuit, req.ref, req.rotations)
        inputs = render_inputs(req)
        return [
            start_render(circuit.with_part(req.ref, rotation=r), inputs,
                         f"{req.ref} at {round(r * 100)} %", req.cached_only)
            for r in req.rotations
        ]  # fmt: skip

    @app.get("/api/render/{job_id}")
    def render_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "That render isn't known (the server may have restarted).")
        return job.view()

    @app.post("/api/render/{job_id}/cancel")
    def cancel_render(job_id: str) -> dict[str, Any]:
        """Stop a render (D-240): a queued one is dropped, a running one stops within a
        moment. A finished one is answered as it is."""
        job = jobs.cancel(job_id)
        if job is None:
            raise HTTPException(404, "That render isn't known (the server may have restarted).")
        return job.view()

    @app.get("/api/render/spectrum/{key}")
    def rendered_spectrum(key: str) -> Any:
        """A finished render's spectra (D-096): band centres, the pedal's output, the take
        as heard, and the guitar's own colour as a DI has it."""
        data = take(spectra_key(key) if key.isalnum() else "")
        return Response(data, media_type="application/json")

    @app.get("/api/render/audio/{key}.wav")
    def rendered(key: str, download: str | None = None) -> Response:
        """A finished render (from the cache). `download=<name>` saves it as a file."""
        keep = {"Cache-Control": "private, max-age=31536000, immutable"}
        if download:
            return attachment(take(key), "audio/wav", f"{safe_file_name(download)}.wav", **keep)
        return Response(take(key), media_type="audio/wav", headers=keep)

    @app.post("/api/render/zip")
    def zipped(req: ZipRequest) -> Response:
        """Finished takes in one zip, with `files` beside them."""
        takes = [(t.file, take(t.key, t.file)) for t in req.takes]
        name = f"{safe_file_name(req.name)}.zip"
        return attachment(zip_takes(takes, req.files), "application/zip", name)

    # ---- File → Export (9d1, D-203): from the circuit's last save ------------------------

    def saved_circuit(kind: str, cid: str) -> Circuit:
        """The file as last saved: a starter, or one of the user's circuits."""
        if kind == "starter" and cid in starters:
            return load_circuit(starters[cid])
        if kind == "circuit" and store.has(cid):
            return store.load(cid)
        raise HTTPException(
            404, "Only a saved circuit or a starter can be exported; save it first."
        )

    @app.get("/api/enclosures")
    def enclosures() -> list[dict[str, Any]]:
        """The standard enclosure sizes, for File → Properties (D-204)."""
        return [asdict(e) | {"text": e.text} for e in ENCLOSURE_SIZES]

    @app.get("/api/export/{kind}/{cid}/check")
    def export_check(kind: str, cid: str) -> dict[str, Any]:
        """Ready to build: the build checks' problems on the last save, and whether it
        simulates (the bias sheet needs it)."""
        c = saved_circuit(kind, cid)
        ready = ready_to_build(checker, sim, c)
        return {"name": c.name, "version": str(c.version), "simulates": ready.simulates,
                "problems": [asdict(p) for p in ready.problems]}  # fmt: skip

    @app.get("/api/export/{kind}/{cid}/bom.csv")
    def export_bom_csv(kind: str, cid: str) -> Response:
        c = saved_circuit(kind, cid)
        data = bom_csv(bom(c, models)).encode("utf-8-sig")  # the mark Excel reads UTF-8 by
        return attachment(data, "text/csv; charset=utf-8", f"{c.name} parts list.csv")

    def pdf_download(page_html: str, name: str) -> Response:
        return attachment(pdf(page_html, settings.web_dir), "application/pdf", name)

    @app.get("/api/export/{kind}/{cid}/bom.pdf")
    def export_bom_pdf(kind: str, cid: str) -> Response:
        c = saved_circuit(kind, cid)
        return pdf_download(bom_page(c, bom(c, models)), f"{c.name} parts list.pdf")

    @app.post("/api/export/{kind}/{cid}/schematic.pdf")
    async def export_schematic_pdf(kind: str, cid: str, request: Request) -> Response:
        """The schematic as PDF, from the SVG the browser drew of the last save (D-205)."""
        c = saved_circuit(kind, cid)
        svg = (await request.body()).decode("utf-8", "replace")
        try:
            if len(svg) > SCHEMATIC_MAX or "<svg" not in svg:
                raise ValueError("not a drawing")
            drawn = schematic_page(c, svg)
        except ValueError:
            raise HTTPException(422, "That isn't a schematic drawing; export it again.") from None
        return pdf_download(drawn, f"{c.name} schematic.pdf")

    @app.get("/api/export/{kind}/{cid}/netlists.zip")
    def export_netlist_zip(kind: str, cid: str) -> Response:
        """The ngspice netlists (op, ac, tran) with models.txt and each model's .lib (D-206)."""
        c = saved_circuit(kind, cid)
        try:
            files = netlist_files(c, simulator(c))
        except RUN_ERRORS as err:
            raise HTTPException(422, f"The saved circuit {no_run(err)}") from None
        return attachment(zip_files(files), "application/zip", f"{c.name} netlists.zip")

    def netlist_files(c: Circuit, s: Simulator) -> list[OutFile]:
        """The netlists, models.txt and each model's .lib (D-206)."""
        extra = [OutFile("models.txt", models_list(c, models)), *model_files(c, models)]
        return [*export_netlists(c, s), *extra]

    def no_run(err: Exception) -> str:
        return f"doesn't simulate: {checker.message(err)}"

    def bias_of(kind: str, cid: str) -> str:
        """The last save's bias sheet as a page, or a 422 when it doesn't simulate."""
        c = saved_circuit(kind, cid)
        try:
            sheet = bias_sheet(c, simulator(c))
        except RUN_ERRORS as err:
            raise HTTPException(422, f"The saved circuit {no_run(err)}") from None
        return bias_page(c, sheet)

    @app.get("/api/export/{kind}/{cid}/bias.html")
    def export_bias_page(kind: str, cid: str) -> Response:
        """The bias sheet as a page to print (opens in a tab)."""
        return page(bias_of(kind, cid))

    @app.get("/api/export/{kind}/{cid}/bias.pdf")
    def export_bias_pdf(kind: str, cid: str) -> Response:
        c = saved_circuit(kind, cid)
        return pdf_download(bias_of(kind, cid), f"{c.name} bias sheet.pdf")

    @app.get("/api/export/{kind}/{cid}/notes.html")
    def export_notes_page(kind: str, cid: str) -> Response:
        """The build notes as a page to print (opens in a tab)."""
        return page(notes_page(saved_circuit(kind, cid)))

    @app.get("/api/export/{kind}/{cid}/notes.pdf")
    def export_notes_pdf(kind: str, cid: str) -> Response:
        c = saved_circuit(kind, cid)
        return pdf_download(notes_page(c), f"{c.name} notes.pdf")

    @app.get("/api/export/{kind}/{cid}/wiring.html")
    def export_wiring_page(kind: str, cid: str) -> Response:
        """The generic wiring diagrams as a page to print (opens in a tab)."""
        return page(wiring_page(saved_circuit(kind, cid), settings.library_dir / "wiring"))

    @app.get("/api/export/{kind}/{cid}/wiring.pdf")
    def export_wiring_pdf(kind: str, cid: str) -> Response:
        c = saved_circuit(kind, cid)
        page_html = wiring_page(c, settings.library_dir / "wiring")
        return pdf_download(page_html, f"{c.name} wiring.pdf")

    @app.post("/api/export/{kind}/{cid}/package.zip")
    def export_package(kind: str, cid: str, req: PackageRequest) -> Response:
        """The build package: every output, the circuit file and an index, in one zip."""
        c = saved_circuit(kind, cid)
        try:
            s = simulator(c)
            simulated = Simulated(bias_sheet(c, s), netlist_files(c, s))
        except HTTPException as err:
            simulated = Simulated(None, [], str(err.detail))
        except RUN_ERRORS as err:
            simulated = Simulated(None, [], f"the saved circuit {no_run(err)}")
        ready = [ReadyRow(r.severity, r.text) for r in req.ready]
        dirs = (settings.web_dir, settings.library_dir / "wiring")
        try:
            files = build_package(c, models, req.svg, simulated, ready, req.dismissed, dirs)
        except ValueError:
            raise HTTPException(422, "That isn't a schematic drawing; export it again.") from None
        name = safe_file_name(f"{c.name} build package")
        return attachment(zip_files(files, folder=name), "application/zip", f"{name}.zip")

    @app.get("/api/export/{kind}/{cid}/bom.html")
    def export_bom_page(kind: str, cid: str) -> Response:
        """The parts list as a page to print (opens in a tab, not downloaded)."""
        c = saved_circuit(kind, cid)
        return page(bom_page(c, bom(c, models)))

    manual = load_manual(settings.guide_dir)

    @app.get("/manual")
    def manual_root() -> Response:
        return RedirectResponse("/manual/")

    @app.get("/manual/")
    @app.get("/manual/{slug}")
    def manual_page(slug: str = "") -> Response:
        """A page of the user guide (Help → Documentation, D-290); `/manual/` is the first."""
        try:
            return page(with_preferences(page_html(manual, manual.get(slug)), kept.load()))
        except ManualError as err:
            raise HTTPException(404, str(err)) from None

    @app.get("/api/manual/search")
    def manual_search(q: str = "") -> list[dict[str, Any]]:
        """The guide's sections holding every word of `q`, a match in a heading first."""
        return [asdict(r) for r in manual.search(q)]

    @app.get("/")
    @app.get("/index.html")
    def app_page() -> Response:
        """The app's page, with the theme and the preferences kept here put in (D-311)."""
        html = (settings.web_dir / "index.html").read_text(encoding="utf-8")
        return page(with_preferences(html, kept.load()))

    if (settings.guide_dir / "img").is_dir():  # the guide's pictures, linked as `img/…`
        app.mount("/manual/img", StaticFiles(directory=settings.guide_dir / "img"), name="guide")
    app.mount("/", _Checked(directory=settings.web_dir, html=True), name="web")
    return app
