import json
import math
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from solum.api import app as app_module
from solum.cache import cache_from_settings
from solum.circuit.io import circuit_to_dict, load_circuit, parse_circuit
from solum.config import load_settings
from solum.model_import import Added, make_model
from solum.models import ModelLibrary, ModelType
from solum.sim.engine import EngineUnavailable, SimError, SimResult
from solum.yamlio import load_yaml
from tests.unit.test_model_import import FILE, fake_measure


class FakeEngine:
    name = "native"

    def version(self) -> str:
        return "44.2"

    def run(self, netlist: str, timeout: float | None = None,
            progress: object = None) -> SimResult:  # fmt: skip
        raise SimError("These tests don't simulate.")


class CrashingEngine(FakeEngine):
    def run(self, netlist: str, timeout: float | None = None,
            progress: object = None) -> SimResult:  # fmt: skip
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _private_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """DATA_DIR and CACHE_DIR in a temp folder, never the repo."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))


def client(monkeypatch: pytest.MonkeyPatch, engine_factory: object) -> TestClient:
    monkeypatch.setattr(app_module, "engine_from_settings", engine_factory)
    return TestClient(app_module.create_app(load_settings()))


def test_health_reports_active_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    body = client(monkeypatch, lambda _s: FakeEngine()).get("/api/health").json()
    assert body["status"] == "ok"
    assert (body["engine"], body["ngspice"]) == ("native", "44.2")


def test_health_explains_missing_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_s: object) -> None:
        raise EngineUnavailable("ngspice isn't installed.")

    body = client(monkeypatch, missing).get("/api/health").json()
    assert body == {
        "status": "degraded",
        "version": body["version"],
        "engine": None,
        "message": "ngspice isn't installed.",
    }


def test_settings_show_the_folders_and_the_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """D-310: what File → Settings… shows; nothing is written until something changes."""
    monkeypatch.setenv("CACHE_MAX_GB", "3")
    body = client(monkeypatch, lambda _s: FakeEngine()).get("/api/settings").json()
    assert body == {
        "data_dir": str(tmp_path / "data"),
        "cache_dir": str(tmp_path / "cache"),
        "host_data_dir": None,
        "host_cache_dir": None,
        "cache_max_gb": 3.0,
        "cache_used_bytes": 0,
        "can_move_folders": False,
        "preferences": None,
    }
    assert not (tmp_path / "data" / "solum-settings.json").exists()


def test_settings_name_the_host_folders_in_a_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-313: compose passes the folders as the host names them, for the dialog to show."""
    monkeypatch.setenv("HOST_DATA_DIR", "/volume1/solum/data")
    monkeypatch.setenv("HOST_CACHE_DIR", "./cache")
    body = client(monkeypatch, lambda _s: FakeEngine()).get("/api/settings").json()
    assert (body["host_data_dir"], body["host_cache_dir"]) == ("/volume1/solum/data", "./cache")


def test_settings_say_when_the_folders_can_move(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAN_MOVE_FOLDERS", "1")
    c = client(monkeypatch, lambda _s: FakeEngine())
    assert c.get("/api/settings").json()["can_move_folders"] is True


def test_cache_size_changes_at_once_and_survives_a_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """D-310: the new size holds without a restart (the oldest results go now), and once
    set it wins over CACHE_MAX_GB."""
    monkeypatch.setenv("CACHE_MAX_GB", "2")
    c = client(monkeypatch, lambda _s: FakeEngine())
    cache = cache_from_settings(load_settings())
    for key in ("a", "b", "c"):
        cache.put_bytes(key, bytes(400_000))
    assert c.get("/api/settings").json()["cache_used_bytes"] == 1_200_000
    body = c.put("/api/settings", json={"cache_max_gb": 0.001}).json()
    assert body["cache_max_gb"] == pytest.approx(0.001)
    assert body["cache_used_bytes"] == 800_000  # the oldest went
    assert not cache.has("a") and cache.has("c")
    restarted = client(monkeypatch, lambda _s: FakeEngine())
    assert restarted.get("/api/settings").json()["cache_max_gb"] == pytest.approx(0.001)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"cache_max_gb": 0}, "The largest cache size must be more than 0."),
        (
            {"preferences": {"solum.nope": 1}},
            "'solum.nope' isn't a preference Solum Builder keeps.",
        ),
    ],
)
def test_bad_settings_are_refused_in_plain_english(
    monkeypatch: pytest.MonkeyPatch, change: dict[str, object], message: str
) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    refused = c.put("/api/settings", json=change)
    assert refused.status_code == 422
    assert refused.json() == {"message": message}


def test_preferences_are_kept_and_sent_inside_the_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-311: the theme is on the app's page and the guide's as they arrive (no flash of
    another), with the preferences for storage.js; `null` until some are kept."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    for url in ("/", "/index.html", "/manual/"):
        first = c.get(url).text
        assert '<script id="solum-prefs" type="application/json">null</script>' in first
        assert "data-theme" not in first.split("<body")[0]
    kept = c.put("/api/settings", json={"preferences": {"solum.theme": "dark", "solum.autorun": 1}})
    assert kept.json()["preferences"] == {"solum.theme": "dark", "solum.autorun": 1}
    for url in ("/", "/index.html", "/manual/"):
        page = c.get(url)
        assert page.headers["cache-control"] == "no-cache"  # never an old copy's theme
        assert '<html data-theme="dark" lang="en">' in page.text
        assert '"solum.autorun": 1' in page.text.split("</script>")[0]
    forgot = c.put("/api/settings", json={"preferences": {"solum.theme": None}})
    assert forgot.json()["preferences"] == {"solum.autorun": 1}
    assert "data-theme" not in c.get("/").text.split("<body")[0]


def test_index_page_is_served(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    page = c.get("/")
    assert page.status_code == 200
    assert "Solum Builder" in page.text
    assert c.get("/theme.css").status_code == 200
    assert c.get("/assets/brand/solum-logo.svg").status_code == 200


def test_the_pages_files_are_checked_again_on_every_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-291: without this a browser keeps some scripts and re-fetches others after an update,
    and new code importing from old fails: nothing draws."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    for path in ("/", "/app.js", "/editor/files.js", "/theme.css", "/manual/"):
        assert c.get(path).headers["cache-control"] == "no-cache", path
    script = c.get("/app.js")
    again = c.get("/app.js", headers={"If-None-Match": script.headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "no-cache"


def test_no_colour_literals_outside_theme(repo: Path) -> None:
    """DESIGN.md: colours are defined only in web/theme.css (vendored code aside)."""
    import re

    web = repo / "web"
    offenders = [
        p
        for p in web.rglob("*")
        if p.suffix in {".js", ".html", ".css"}
        and p.name != "theme.css"
        and p.relative_to(web).parts[0] != "vendor"
        and re.search(r"#[0-9a-fA-F]{3,8}\b", p.read_text())
    ]
    assert offenders == []


def test_starters_are_listed_and_open(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    starters = c.get("/api/starters").json()
    assert {s["id"] for s in starters} == {
        "big-muff-aion-halo",
        "big-muff-pi-v3",
        "boss-bd2",
        "boss-bd2-aion",
        "boss-ds1",
        "boss-ds1-aion",
        "dallas-rangemaster",
        "fuzz-face",
        "klon-centaur",
        "klon-centaur-aion",
        "klon-centaur-aion-built",
        "marshall-bluesbreaker",
        "marshall-bluesbreaker-aion",
        "mxr-dyna-comp",
        "mxr-dyna-comp-aion",
        "proco-rat",
        "tone-bender-mk2",
        "tone-bender-mk2-mode",
        "ts808",
    }
    view = c.get("/api/starters/ts808").json()
    assert view["circuit"]["name"] == "Ibanez TS808 Tube Screamer"
    labels = [k["label"] for k in view["controls"]]
    assert labels == ["Guitar volume", "Distortion", "Tone", "Level", "Guitar cable"]


def test_unknown_starter_is_a_plain_404(monkeypatch: pytest.MonkeyPatch) -> None:
    r = client(monkeypatch, lambda _s: FakeEngine()).get("/api/starters/nope")
    assert r.status_code == 404
    assert r.json() == {"message": "There's no starter circuit called 'nope'."}


def test_invalid_circuit_is_a_plain_422(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"circuit": {"schema": 1, "id": "x", "name": "x", "parts": [
        {"ref": "R1", "type": "resistor", "value": "4k7k"}]}}  # fmt: skip
    r = client(monkeypatch, lambda _s: FakeEngine()).post("/api/run", json=body)
    assert r.status_code == 422
    assert "part R1 value" in r.json()["message"]


def test_unknown_part_is_a_plain_404(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    circuit = c.get("/api/starters/ts808").json()["circuit"]
    r = c.post("/api/part", json={"circuit": circuit, "ref": "R99"})
    assert (r.status_code, r.json()) == (404, {"message": "There's no part R99 in this circuit."})


def test_engine_crash_is_a_plain_500_without_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_module, "engine_from_settings", lambda _s: CrashingEngine())
    app = app_module.create_app(load_settings())
    c = TestClient(app, raise_server_exceptions=False)
    circuit = c.get("/api/starters/ts808").json()["circuit"]
    r = c.post("/api/run", json={"circuit": circuit, "nodes": ["u2o"]})
    assert r.status_code == 500
    assert r.json() == {
        "message": "Something went wrong inside Solum Builder. The server log has details."
    }


def test_no_simulator_is_a_plain_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_s: object) -> None:
        raise EngineUnavailable("ngspice isn't installed.")

    c = client(monkeypatch, missing)
    circuit = c.get("/api/starters/ts808").json()["circuit"]
    r = c.post("/api/run", json={"circuit": circuit})
    assert (r.status_code, r.json()) == (503, {"message": "ngspice isn't installed."})


def test_models_by_type(monkeypatch: pytest.MonkeyPatch) -> None:
    models = client(monkeypatch, lambda _s: FakeEngine()).get("/api/models").json()
    assert models["jfet"] == [
        "2N5457",
        "2N5458",
        "2N5485",
        "2SK184-GR",
        "2SK209-GR",
        "J113",
        "J201",
        "MPF102",
        "MPF4393",
        "PF5102",
    ]
    assert "TL072" in models["opamp"]
    assert models["diode"] == [
        "1N34A", "1N4001", "1N4148", "1N4738A", "1N4739A", "1N4742A", "1N5817", "1N60", "1N914",
        "1SS133", "BAT41", "BAT42", "BAT46", "BAT48"
    ]  # fmt: skip
    assert models["led"] == [
        "APT1608SURCK", "WP710A10SURDK", "WP7113GD", "WP7113QBC-D", "WP7113QWC-D", "WP7113SURDK"
    ]  # fmt: skip
    assert models["chargepump"] == ["ICL7660", "LT1054", "MAX1044", "TC1044S"]
    assert models["mosfet"] == ["2N7000", "BS170", "LND150"]
    assert models["regulator"] == ["78L12"]
    assert set(models) == {
        "diode", "led", "jfet", "bjt", "mosfet", "opamp", "inverter", "ota", "chargepump",
        "regulator",
        "yours", "zeners", "smd",
    }  # fmt: skip
    assert models["yours"] == []  # the user's own models' ids (9c), none in a fresh DATA_DIR
    # the diodes whose record checks a zener voltage: a diode set to one is named Z
    assert models["zeners"] == ["1N4738A", "1N4739A", "1N4742A"]
    # the surface-mount models: a part of one is offered a TO-92 adapter (D-392)
    assert "2SK209-GR" in models["smd"] and "J201" not in models["smd"]


def test_jfet_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JFET form's measured Idss and Vp start at the model's (J201: 0.447 mA, -0.671 V),
    with the datasheet's range, which your unit can be anywhere in."""
    specs = client(monkeypatch, lambda _s: FakeEngine()).get("/api/models/jfets").json()
    j201 = specs["J201"]
    assert (j201["idss"], j201["vp"]) == (
        pytest.approx(0.4472e-3, rel=1e-3),
        pytest.approx(-0.6708),
    )
    assert j201["range"]["idss"] == {"min": 0.2e-3, "max": 1e-3, "at": {"vds": 20.0}}
    assert (j201["range"]["vp"]["min"], j201["range"]["vp"]["max"]) == (-1.5, -0.3)


def test_capacitor_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    guide = client(monkeypatch, lambda _s: FakeEngine()).get("/api/guides/capacitors").json()
    assert guide["title"] == "Choosing capacitors"
    assert guide["kinds"][0]["kind"] == "film"


def test_inductor_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    guide = client(monkeypatch, lambda _s: FakeEngine()).get("/api/guides/inductors").json()
    assert guide["title"] == "Wah inductors"
    assert guide["inductors"][0] == {"kind": "fasel-red", "name": "Fasel red (toroid)",
        "measured": "Dunlop red Fasel, toroid core (the measurer's average)", "l": "666m",
        "r": "15.65"}  # fmt: skip


def test_view_of_an_edited_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    circuit = c.get("/api/starters/ts808").json()["circuit"]
    circuit["parts"] = [p for p in circuit["parts"] if p["ref"] != "R1"]
    view = c.post("/api/view", json={"circuit": circuit}).json()
    assert "R1" not in {p["ref"] for p in view["parts"]}
    assert view["problem"] is None
    bad = {
        **circuit,
        "parts": [*circuit["parts"], {"ref": "R2", "type": "resistor", "value": "1k"}],
    }
    r = c.post("/api/view", json={"circuit": bad})
    assert r.status_code == 422 and "repeated: R2" in r.json()["message"]


def test_save_and_reopen_a_copy_of_a_starter(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    starter = c.get("/api/starters/ts808").json()
    path = "<starters>/ts808.json"
    assert starter["file"] == {"kind": "circuit", "layer": "starter", "path": path,
                               "saved": None, "readonly": True, "link": "ts808",
                               "current": True}  # fmt: skip
    created = c.post(
        "/api/circuits", json={"circuit": starter["circuit"], "name": "My TS808"}
    ).json()
    cid = created["circuit"]["id"]
    assert cid == "my-ts808-v1" and "starter" not in created["circuit"]
    assert created["circuit"]["version"] == {"major": 1, "minor": 0}
    assert created["file"]["path"] == "<data>/circuits/my-ts808-v1.json"
    assert (created["file"]["link"], created["file"]["current"]) == ("my-ts808", True)
    assert created["file"]["readonly"] is False and created["file"]["saved"].endswith("+00:00")
    edited = {**created["circuit"], "tags": ["overdrive"]}
    saved = c.put(f"/api/circuits/{cid}", json={"circuit": edited}).json()
    assert saved == {"id": cid, "name": "My TS808", "version": "v1.1", "final": False,
                     "link": "my-ts808"}  # fmt: skip
    assert c.get("/api/circuits/my-ts808").json()["circuit"]["id"] == cid  # the short id
    assert c.get(f"/api/circuits/{cid}").json()["circuit"]["tags"] == ["overdrive"]
    listed = c.get("/api/circuits", params={"q": "overdrive"}).json()
    assert [(e["id"], e["version"], e["final"]) for e in listed] == [(cid, "v1.1", False)]
    assert listed[0]["models"] == ["1N4148", "2SC1815", "RC4558"]
    assert c.get("/api/circuits", params={"q": "fuzz"}).json() == []


def test_a_taken_name_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    starter = c.get("/api/starters/fuzz-face").json()["circuit"]
    a = c.post("/api/circuits", json={"circuit": starter, "name": "Face"}).json()
    r = c.post("/api/circuits", json={"circuit": a["circuit"]})
    assert (r.status_code, r.json()["message"]) == (
        422, "You already have a circuit called Face (its file is face-v1.json). Pick another name."
    )  # fmt: skip


def test_properties_rename_lock_and_new_major(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    c.post("/api/circuits", json={"name": "Scratch"})
    view = c.patch("/api/circuits/scratch", json={"name": "Muff build", "tags": ["muff"]}).json()
    assert (view["circuit"]["id"], view["file"]["path"]) == (
        "muff-build-v1",
        "<data>/circuits/muff-build-v1.json",
    )
    assert view["circuit"]["version"] == {"major": 1, "minor": 1}
    assert c.get("/api/circuits/scratch").status_code == 404
    major = c.post("/api/circuits/muff-build/major").json()
    assert major["circuit"]["version"] == {"major": 2, "minor": 0}
    assert (major["circuit"]["id"], major["file"]["link"]) == ("muff-build-v2", "muff-build")
    assert major["final_copy"] == {"id": "muff-build-v1", "name": "Muff build",
                                   "version": "v1.1", "final": True,
                                   "link": "muff-build-v1"}  # fmt: skip
    final = c.get("/api/circuits/muff-build-v1").json()
    assert (final["file"]["readonly"], final["file"]["current"]) == (True, False)
    r = c.put("/api/circuits/muff-build-v1", json={"circuit": {**final["circuit"], "tags": []}})
    assert r.status_code == 422 and "final version, so it's read-only" in r.json()["message"]
    unlocked = c.patch("/api/circuits/muff-build-v1", json={"final": False}).json()
    assert unlocked["file"]["readonly"] is False
    c.post("/api/circuits", json={"name": "Other"})
    r = c.patch("/api/circuits/muff-build", json={"name": "other"})
    assert r.status_code == 422 and "already have a circuit called Other" in r.json()["message"]
    renamed = c.patch("/api/circuits/muff-build", json={"name": "Big Muff"}).json()
    assert renamed["file"]["link"] == "big-muff"
    assert [e["id"] for e in c.get("/api/circuits", params={"q": "big"}).json()] == [
        "big-muff-v2", "big-muff-v1"
    ]  # fmt: skip


def test_save_errors_are_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    starter = c.get("/api/starters/ts808").json()["circuit"]
    r = c.put("/api/circuits/ts808", json={"circuit": starter})
    assert (r.status_code, r.json()["message"]) == (
        422, "Starters are read-only. Save this as a new circuit."
    )  # fmt: skip
    r = c.put("/api/circuits/nope", json={"circuit": {**starter, "starter": False}})
    assert (r.status_code, r.json()["message"]) == (404, "There's no saved circuit called 'nope'.")
    r = c.get("/api/circuits/nope")
    assert (r.status_code, r.json()["message"]) == (404, "There's no saved circuit called 'nope'.")


def test_sweep_request_errors_are_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    circuit = c.get("/api/starters/ts808").json()["circuit"]

    def sweep(**body: object) -> tuple[int, str]:
        r = c.post("/api/sweep", json={"circuit": circuit, **body})
        return r.status_code, r.json()["message"]

    assert sweep(ref="R99", values=["1k"]) == (422, "There's no part R99 in this circuit.")
    assert sweep(ref="R1", values=[]) == (
        422, "List at least one value to try, separated by commas."
    )  # fmt: skip
    assert sweep(ref="R1", values=["1k"] * 6) == (
        422, "Try at most 5 values at once (got 6)."
    )  # fmt: skip
    assert sweep(ref="R1", field="rotation", values=["1"])[1].startswith("Only a part's value")
    assert sweep(ref="D1", values=["1k"]) == (422, "D1 has no value to try other values of.")
    code, message = sweep(ref="R1", values=["1k", "4k7k"])
    assert code == 422 and message.startswith("R1: can't use '4k7k'.")


def test_new_blank_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    view = c.post("/api/circuits", json={"name": "Scratchpad"}).json()
    assert view["circuit"]["name"] == "Scratchpad"
    assert view["circuit"]["id"] == "scratchpad-v1"
    assert [p["ref"] for p in view["circuit"]["parts"]] == ["IN", "OUT"]
    r = c.post("/api/circuits", json={"name": ""})
    assert (r.status_code, r.json()["message"]) == (422, "Give the circuit a name.")


def test_blank_sheet_has_input_and_output(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    view = c.get("/api/blank").json()
    circuit = view["circuit"]
    assert (circuit["name"], circuit["power"]) == ("Untitled", {"rails": {"V+": 9.0}})
    assert [(p["ref"], p["type"], p["pos"]) for p in circuit["parts"]] == [
        ("IN", "guitar", [-300, 0]), ("OUT", "amp", [300, 0]),
    ]  # fmt: skip
    assert view["probes"] == {"in": "IN.out", "out": "OUT.in"}
    assert c.get("/api/circuits").json() == []  # nothing saved


def test_delete_saved_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    c.post("/api/circuits", json={"name": "Gone soon"})
    assert c.delete("/api/circuits/gone-soon").json() == {"deleted": "gone-soon-v1"}
    assert c.get("/api/circuits").json() == []
    r = c.delete("/api/circuits/gone-soon")
    assert (r.status_code, r.json()["message"]) == (
        404, "There's no saved circuit called 'gone-soon'."
    )  # fmt: skip


def test_blocks_are_listed_opened_and_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    listed = c.get("/api/blocks").json()
    by_id = {e["id"]: e for e in listed}
    tmb = by_id["fender-tmb-v1"]
    assert (tmb["layer"], tmb["ports"], tmb["current"]) == ("core", ["in", "out"], True)
    assert (tmb["version"], tmb["final"]) == ("v1.3", False)  # no Thick switch; cap kinds; name
    found = [e["id"] for e in c.get("/api/blocks", params={"q": "tone stack"}).json()]
    assert found == [
        "baxandall-3-band-v1",
        "baxandall-bass-treble-v1",
        "big-muff-tone-v1",
        "fender-tmb-v1",
    ]
    core = c.get("/api/blocks/vref-divider").json()
    path = "<core>/blocks/vref-divider-v1.json"
    assert core["file"] == {"kind": "block", "layer": "core", "path": path,
                            "saved": None, "readonly": True, "link": "vref-divider",
                            "current": True}  # fmt: skip
    assert core["circuit"]["ports"] == {"vref": "vref"}
    r = c.put("/api/blocks/vref-divider", json={"circuit": core["circuit"]})
    assert (r.status_code, r.json()["message"]) == (
        422, "There's no block called 'vref-divider' in My blocks."
    )  # fmt: skip
    r = c.patch("/api/blocks/vref-divider", json={"name": "Mine now"})
    assert (r.status_code, r.json()["message"]) == (422, "There's no block called 'vref-divider'.")
    # edited and saved under its own name: a block of mine beside the core one
    mine = c.post("/api/blocks", json={"circuit": core["circuit"], "name": "Vref divider"}).json()
    assert (
        mine["file"]["layer"] == "user"
        and mine["file"]["path"] == "<data>/blocks/vref-divider-v1.json"
    )
    edited = {**mine["circuit"], "description": "mine"}
    assert c.put("/api/blocks/vref-divider", json={"circuit": edited}).json()["version"] == "v1.1"
    listed = {(e["id"], e["layer"]) for e in c.get("/api/blocks").json()}
    assert {("vref-divider-v1", "user"), ("vref-divider-v1", "core")} <= listed
    assert (
        c.get("/api/blocks/vref-divider", params={"layer": "core"}).json()["file"]["layer"]
        == "core"
    )
    renamed = c.patch("/api/blocks/vref-divider", json={"name": "My vref"}).json()
    assert renamed["circuit"]["id"] == "my-vref-v1"
    major = c.post("/api/blocks/my-vref/major").json()
    assert (major["circuit"]["id"], major["final_copy"]["id"]) == ("my-vref-v2", "my-vref-v1")
    assert c.delete("/api/blocks/my-vref-v1").json() == {"deleted": "my-vref-v1"}
    r = c.delete("/api/blocks/vref-divider")
    assert (r.status_code, r.json()["message"]) == (422, "Core blocks can't be deleted.")
    r = c.get("/api/blocks/nope")
    assert (r.status_code, r.json()["message"]) == (422, "There's no block called 'nope'.")


def test_save_a_selection_as_a_block(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    block = c.get("/api/blocks/diode-clipper-gnd").json()["circuit"]
    made = c.post("/api/blocks", json={"circuit": {**block, "template": False}, "name": "Clip"})
    body = made.json()
    assert body["file"]["layer"] == "user" and body["circuit"]["id"] == "clip-v1"
    assert body["circuit"]["template"] is True
    bad = {**block, "ports": {"x": "nowhere"}}
    r = c.post("/api/blocks", json={"circuit": bad, "name": "Bad"})
    assert (
        r.status_code == 422 and "no label on the sheet is called 'nowhere'" in r.json()["message"]
    )


def _half_drawn() -> dict[str, object]:
    from solum.circuit.build import CircuitBuilder

    # net a has no DC path; R1, wired to nothing, is left out of the simulation (D-165)
    builder = CircuitBuilder("half drawn").part("C1", "capacitor", "a", "0", value="47u")
    builder = builder.part("C2", "capacitor", "a", "0", value="47u")
    return builder.part("R1", "resistor", "b", None, value="10k").data()


def test_a_floating_circuit_is_refused_before_simulating(monkeypatch: pytest.MonkeyPatch) -> None:
    """FakeEngine can't run anything, so a 422 here means the drawing was checked first."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    res = c.post("/api/run", json={"circuit": _half_drawn(), "nodes": []})
    assert res.status_code == 422
    assert res.json()["message"].startswith("Can't simulate yet: net a has")


def test_problems_lists_every_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    body = c.post("/api/problems", json={"circuit": _half_drawn()}).json()
    assert body["checked_op"] is False  # the floating nets stop the simulation
    rules = [p["rule"] for p in body["problems"]]
    assert rules[0] == "no-dc-path" and "part-not-simulated" in rules
    first = body["problems"][0]
    assert set(first) == {"rule", "layer", "severity", "title", "message", "why", "fix",
                          "refs", "nets", "build", "at"}  # fmt: skip
    assert first["nets"] == ["a"]


def test_problems_say_which_ratings_to_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-360: an electrolytic with no rating on 9 V gets 16 V, and the rows that offer it."""

    def missing(_s: object) -> None:
        raise EngineUnavailable("ngspice isn't installed.")

    from solum.circuit.build import CircuitBuilder

    circuit = (
        CircuitBuilder("caps")
        .rail("V+", 9.0)
        .part("R1", "resistor", "V+", "0", value="10k")
        .part("C1", "capacitor", "V+", "0", value="100u", kind="electrolytic")
        .data()
    )
    body = client(monkeypatch, missing).post("/api/problems", json={"circuit": circuit}).json()
    assert body["ratings"] == {
        "set": {"C1": 16.0},
        "rules": ["cap-no-rating", "cap-over-voltage", "cap-rating-close"],
    }


def test_a_model_that_isnt_there_opens_draws_and_says_which_to_add(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-288: a circuit naming a model this library doesn't have (a card that isn't
    included, or one someone else added) still gets its view; Problems names the part and
    the model and says how to add it, and a run is refused with the same line."""
    from solum.circuit.build import CircuitBuilder

    builder = CircuitBuilder("borrowed").part("R1", "resistor", "V+", "d", value="10k")
    circuit = builder.part("Q1", "jfet", "d", "0", "0", model="J999").data()
    c = client(monkeypatch, lambda _s: FakeEngine())
    assert c.post("/api/view", json={"circuit": circuit}).status_code == 200
    body = c.post("/api/problems", json={"circuit": circuit}).json()
    first = body["problems"][0]
    line = "Can't simulate yet: Q1 names the model J999, which isn't in the library."
    assert (first["rule"], first["refs"], first["message"]) == ("model-missing", ["Q1"], line)
    assert "Tools \u2192 Add a model" in first["fix"] and body["checked_op"] is False
    res = c.post("/api/run", json={"circuit": circuit, "nodes": []})
    assert (res.status_code, res.json()["message"]) == (422, line)


def test_the_guide_is_served_as_pages_with_a_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-290: `/manual/` is the guide's first page, `/manual/<page>` the others; an unknown
    page is a plain 404; the search answers by section."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    first = c.get("/manual/")
    assert first.status_code == 200 and first.headers["content-type"].startswith("text/html")
    assert '<h1 id="solum-builder-guide">' in first.text
    assert c.get("/manual", follow_redirects=False).headers["location"] == "/manual/"
    assert '<h2 id="voltage-divider">' in c.get("/manual/formulas").text
    missing = c.get("/manual/nope")
    assert (missing.status_code, missing.json()["message"]) == (
        404,
        "The guide has no page called 'nope'.",
    )
    found = c.get("/api/manual/search", params={"q": "led resistor"}).json()
    assert found[0] == {
        "slug": "formulas",
        "title": "Formulas",
        "heading": "LED resistor",
        "anchor": "led-resistor",
        "snippet": found[0]["snippet"],
    }
    assert "The resistor sets the LED's current" in found[0]["snippet"]


def test_problems_without_a_simulator_checks_the_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_s: object) -> None:
        raise EngineUnavailable("ngspice isn't installed.")

    body = client(monkeypatch, missing).post("/api/problems", json={"circuit": _half_drawn()})
    assert body.status_code == 200 and body.json()["checked_op"] is False


def test_export_works_from_the_last_save(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-203: a starter or a saved circuit by id; an unsaved one is refused plainly."""

    def missing(_s: object) -> None:
        raise EngineUnavailable("ngspice isn't installed.")

    c = client(monkeypatch, missing)
    check = c.get("/api/export/starter/ts808/check").json()
    assert check["name"] and check["simulates"] is False  # no simulator here
    assert check["problems"] == []  # a starter's parts list is filled in (D-211)
    starter = c.get("/api/starters/ts808").json()["circuit"]
    for cap in (p for p in starter["parts"] if p["type"] == "capacitor"):
        cap.pop("kind", None)
    untyped = c.post("/api/circuits", json={"circuit": starter, "name": "Untyped"}).json()
    problems = c.get(f"/api/export/circuit/{untyped['circuit']['id']}/check").json()["problems"]
    assert {p["rule"] for p in problems} >= {"cap-no-kind"}
    assert all(p["build"] for p in problems)
    csv_file = c.get("/api/export/starter/ts808/bom.csv")
    assert csv_file.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_file.headers["content-disposition"]
    assert csv_file.content.startswith("\ufeff".encode())  # so a spreadsheet reads µ right
    assert "RC4558" in csv_file.content.decode("utf-8-sig")
    assert "<h2>On the board</h2>" in c.get("/api/export/starter/ts808/bom.html").text
    assert c.get("/api/export/starter/ts808/bom.pdf").content.startswith(b"%PDF")
    assert "<h2>Knobs</h2>" in c.get("/api/export/starter/ts808/notes.html").text
    assert c.get("/api/export/starter/ts808/notes.pdf").content.startswith(b"%PDF")
    assert "3PDT" in c.get("/api/export/starter/ts808/wiring.html").text
    wiring = c.get("/api/export/starter/ts808/wiring.pdf")
    assert (
        wiring.content.startswith(b"%PDF") and "wiring.pdf" in wiring.headers["content-disposition"]
    )
    assert c.get("/api/export/starter/ts808/bias.html").status_code == 503  # no simulator
    circuit_file = c.get(f"/api/export/circuit/{untyped['circuit']['id']}/circuit.json")
    assert circuit_file.headers["content-type"].startswith("application/json")
    assert 'filename="Untyped.json"' in circuit_file.headers["content-disposition"]
    opened = parse_circuit(circuit_file.json())  # the file as saved, opens again (D-334)
    assert opened.name == "Untyped" and len(opened.parts) == len(starter["parts"])
    line = '<line x1="0" y1="0" x2="10" y2="10" stroke="black"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">{line}</svg>'
    drawn = c.post("/api/export/starter/ts808/schematic.pdf", content=svg)
    assert drawn.status_code == 200 and drawn.content.startswith(b"%PDF")
    assert "schematic.pdf" in drawn.headers["content-disposition"]
    for bad in ("not a drawing", '<svg xmlns="http://www.w3.org/2000/svg"></svg>'):  # no size
        refused = c.post("/api/export/starter/ts808/schematic.pdf", content=bad)
        assert refused.status_code == 422 and "export it again" in refused.json()["message"]
    saved = c.post("/api/circuits", json={"name": "Mine"}).json()["circuit"]["id"]
    assert c.get(f"/api/export/circuit/{saved}/bom.csv").status_code == 200
    gone = c.get("/api/export/circuit/nope/check")
    assert gone.status_code == 404 and "save it first" in gone.json()["message"]


def test_live_gives_sliders_for_a_circuit_without_input(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    block = c.get("/api/blocks/vref-divider").json()["circuit"]
    ref = block["parts"][0]["ref"]
    body = c.post(
        "/api/live", json={"circuit": block, "controls": [{"ref": ref, "field": "value"}]}
    ).json()
    assert body["system"] is None and body["sliders"][0]["ref"] == ref


def test_live_explains_a_part_with_no_slider(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    block = c.get("/api/blocks/vref-divider").json()["circuit"]
    r = c.post("/api/live", json={"circuit": block, "controls": [{"ref": "R99", "field": "value"}]})
    assert r.status_code == 422
    assert r.json() == {"message": "There's no part R99 in this circuit."}


def test_unit_converter(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    body = c.get("/api/tools/convert", params={"value": "22n", "unit": "F"}).json()
    assert (body["short"], body["code"], body["series"]) == ("22n", "223", ["E6", "E12", "E24"])
    assert body["rows"][0] == {"unit": "pF", "number": "22 000"}
    coded = c.get("/api/tools/convert", params={"code": "104K", "unit": "F"}).json()
    assert (coded["short"], coded["tolerance"]) == ("100n", "±10 %")
    bad = c.get("/api/tools/convert", params={"value": "4k7k", "unit": "Ω"})
    assert bad.status_code == 422 and "Couldn't read the value" in bad.json()["message"]


def test_resistor_colour_code(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    body = c.get("/api/tools/resistor", params={"value": "4k1"}).json()
    assert body["bands4"] == ["yellow", "brown", "red"] and body["series"] == []
    assert body["nearest"] == [
        {"series": "E24", "tolerance": 5.0, "below": "3k9", "above": "4k3"},
        {"series": "E96", "tolerance": 1.0, "below": "4k02", "above": "4k12"},
    ]
    read = c.get("/api/tools/resistor", params={"bands": "yellow,violet,red,gold"}).json()
    assert (read["short"], read["tolerance"], read["nearest"]) == ("4k7", 5.0, [])
    bad = c.get("/api/tools/resistor", params={"bands": "gold,red,red"})
    assert bad.status_code == 422 and "can't be a digit band" in bad.json()["message"]


def test_curve_features_for_a_live_curve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 8b: the browser's curve (dB), measured on the server (one owner)."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    freq = [10 * 10 ** (k / 50) for k in range(201)]
    db = [-10 * math.log10(1 + (f / 1000) ** 2) for f in freq]  # a 1 kHz low-pass
    body = c.post("/api/curve", json={"freq": freq, "db": db}).json()
    assert body["features"]["shape"] == "low-pass"
    [knee] = body["features"]["knees"]
    assert knee["side"] == "high" and knee["f"] == pytest.approx(1000, rel=0.01)
    assert body["readings"][0]["label"] == "At 1 kHz"
    bad = c.post("/api/curve", json={"freq": [1, 2], "db": [0, 0]})
    assert bad.status_code == 422 and "at least 3" in bad.json()["message"]


def test_influence_route(monkeypatch: pytest.MonkeyPatch) -> None:
    c = client(monkeypatch, lambda _s: FakeEngine())
    freq = [10 * 10 ** (k / 50) for k in range(201)]

    def lowpass(fc: float) -> list[float]:
        return [-10 * math.log10(1 + (f / fc) ** 2) for f in freq]

    body = c.post("/api/influence", json={
        "freq": freq, "base": lowpass(1000),
        "nudged": {"C1": lowpass(1000 / 1.1), "R1": lowpass(1000)}, "at": 2000,
    }).json()  # fmt: skip
    assert [r["ref"] for r in body["rows"]] == ["C1"] and body["hidden"] == ["R1"]
    assert body["rows"][0]["what"] == "high knee" and body["at_text"] == "2 kHz"


def test_adding_a_model_lists_checks_and_saves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """9c, Tools → Add a model: a file's cards, then one checked, then saved into the user's
    models and the running library (the parts list and the model lists show it)."""

    def in_process(text: str, card: str, part: ModelType, mid: str, filename: str,
                   models: ModelLibrary, pins: list[str] | None, channels: int,
                   _library: str | None) -> Added:  # fmt: skip
        return make_model(text, card, part, mid, filename, models, fake_measure, pins, channels)

    monkeypatch.setattr("solum.api.app.check_apart", in_process)
    c = client(monkeypatch, lambda _s: FakeEngine())
    listed = c.post("/api/models/import", json={"text": FILE, "filename": "acme.lib"}).json()
    assert [x["name"] for x in listed["cards"]] == ["Q2N3904X", "D1N4148X", "OPAX"]
    assert listed["cards"][2]["nodes"] == ["1", "2", "3", "4", "5", "6"]
    assert [x["suggested"] for x in listed["cards"]] == ["Q2N3904X", "D1N4148X", "OPAX"]
    ask = {"text": FILE, "filename": "acme.lib", "card": "D1N4148X", "part_type": "diode",
           "id": "1N4148-acme"}  # fmt: skip
    checked = c.post("/api/models/import", json=ask).json()
    assert checked["saved"] is False and checked["model"]["origin"] == "user"
    assert "1N4148-acme" not in c.get("/api/models").json()["diode"]
    saved = c.post("/api/models/import", json={**ask, "save": True}).json()
    assert saved["saved"] is True
    listed_now = c.get("/api/models").json()
    assert "1N4148-acme" in listed_now["diode"] and listed_now["yours"] == ["1N4148-acme"]
    assert (tmp_path / "data" / "models" / "diode" / "1N4148-acme.json").exists()
    again = c.post("/api/models/import", json={**ask, "save": True})
    assert again.status_code == 422 and "already a model" in again.json()["message"]
    bad = c.post("/api/models/import", json={"text": "* nothing", "filename": "x.lib"})
    assert bad.status_code == 422 and "op-amp .subckt" in bad.json()["message"]
    opamp = {"text": FILE, "filename": "acme.lib", "card": "OPAX", "part_type": "opamp",
             "id": "OPAX-mine", "pins": ["out", "-", "+", "V-", "V+", ""], "channels": 2,
             "save": True}  # fmt: skip
    assert c.post("/api/models/import", json=opamp).json()["saved"] is True
    assert c.get("/api/models/chips").json()["OPAX-mine"]["halves"] == 2


def test_the_parts_list_has_every_model_by_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """9c, Tools → Parts and datasheets: every model, ordered by type then id, and the cards
    we may not ship, each after a stock model of the same id."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    body = c.get("/api/models/catalogue").json()
    ids = [m["id"] for m in body if m["origin"] != "excluded"]
    assert len(ids) == len(set(ids)) and "2N404" in ids and "TL072" in ids
    keys = [(m["type"], m["id"], m["origin"] == "excluded") for m in body]
    assert keys == sorted(keys)
    assert ("bjt", "2N3904", True) in keys and ("ota", "LM13700", True) in keys
    assert next(m for m in body if m["id"] == "OC81D")["origin"] == "estimate"


def test_transistor_gains_for_the_form(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-130, D-153: each BJT card's gain on the Geofex tester, where a measured hFE starts
    (the AC128: BF 107.8, read at 91.5), with its datasheet range (D-170)."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    gains = c.get("/api/models/bjts").json()
    assert gains["AC128"] == {
        "hfe": pytest.approx(91.47, abs=0.01),
        "leakage": pytest.approx(315.2e-6, rel=1e-3),
        "germanium": True,
        "tester_ic": pytest.approx(91.47 * 9.0 / 2.2e6 + 315.2e-6, rel=1e-3), "sheet_low_ic": 1e-3,
        "range": {"hfe": {"min": 55.0, "max": 175.0, "at": {"ic": 0.05, "vcb": 0.0}}},
    }  # fmt: skip
    assert gains["2N3904"]["range"]["hfe"] == {
        "min": 100.0, "max": 300.0, "at": {"ic": 0.01, "vce": 1.0}
    }  # fmt: skip
    assert gains["2N3906"]["leakage"] == 0.0  # silicon: none recorded
    assert gains["2N3906"]["germanium"] is False


def test_pickup_form_works_out_the_other_two(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-363: the guitar form asks as you type; the server says what the boxes show."""
    c = client(monkeypatch, lambda _s: FakeEngine())
    body = c.post(
        "/api/pickup", json={"typed": [["r", "8k2"], ["peak", "5k2"], ["q", "2.1"]]}
    ).json()
    assert body["shown"] == {"l": "527m", "c": "1n78"}
    assert body["stored"] == {"r": "8k2", "l": "527m", "c": "1n777"}
    assert body["line"] == "Set: R, peak, Q · worked out: L, C"
    two = c.post("/api/pickup", json={"typed": [["l", "2.5"], ["c", "150p"]]}).json()
    assert two["dimmed"] == {"peak": "Not the peak: L and C give it."} and two["stored"] is None
    bad = c.post("/api/pickup", json={"typed": [["l", "2.5"], ["c", "150p"], ["peak", "5k"]]})
    assert bad.status_code == 422 and bad.json()["message"] == "Not the peak: L and C give it."


def test_stripboard_reports_the_open_circuit_s_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-368: the progress check of the board the circuit carries; none yet, an empty one."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    empty = c.post("/api/stripboard", json={"circuit": data}).json()
    assert empty["to_place"] == ["C1", "C2", "C3", "C4", "Q1", "R1", "R2", "R3"]
    assert empty["nets_done"] == 0 and empty["done"] is False and empty["faults"] == []
    q1, r3 = empty["footprints"]["Q1"], empty["footprints"]["R3"]
    assert q1["shape"] == "inline" and q1["legs"] == ["E", "B", "C"] and q1["refs"] == ["Q1"]
    assert r3["shape"] == "axial" and r3["stand"] > 0 and r3["length"] > 0
    board = load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")
    done = c.post("/api/stripboard", json={"circuit": {**data, "stripboard": board}}).json()
    assert done["done"] is True and done["nets_done"] == len(done["nets"])
    assert done["items"][0]["ref"] == "VR1" and done["items"][0]["size"] == [7, 3]
    assert done["spots"]["IN"] == [16, 0] and done["wires_to_go"] == []
    assert done["guidance"]["next"] is None and done["guidance"]["ratsnest"] == []
    assert empty["guidance"]["next"]["ref"] == "C1"  # nearest the input (D-377)
    assert json.dumps(done)  # plain JSON all through
    bad = c.post("/api/stripboard", json={"circuit": {**data, "stripboard": {"size": [0, 1]}}})
    assert bad.status_code == 422 and "one column" in bad.text


def test_stripboard_warns_of_a_link_near_a_high_gain_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-402: with Q1's base found high gain, a link of a net with signal on it beside R1's
    base leg is warned about in words; the fixture's own V- link (quiet) is let be."""
    from solum.stripboard.limits import LoudInput

    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    loud = [LoudInput("Q1", "B", frozenset({"GND", "V-"}))]
    monkeypatch.setattr(app_module, "loud_inputs", lambda _sim, _c: loud)
    c = client(monkeypatch, lambda _s: FakeEngine())
    board = load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")
    quiet = c.post("/api/stripboard", json={"circuit": {**data, "stripboard": board}}).json()
    assert not any(w.startswith("The link from") for w in quiet["warnings"])
    near = {**board, "links": [*board["links"], ["D5", "D6"]]}  # the collector's strip, by C4
    said = c.post("/api/stripboard", json={"circuit": {**data, "stripboard": near}}).json()
    assert any(w.startswith("The link from D5 to D6 runs beside") for w in said["warnings"])


def test_stripboard_size_changes_the_open_circuit_s_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-372: a line inserted, taken out or the board trimmed, as the board's new plain
    form; a change that can't be made says why. An empty board starts sized from its parts."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    assert c.post("/api/stripboard", json={"circuit": data}).json()["start_size"] == [11, 8]
    none = c.post("/api/stripboard/size", json={"circuit": data, "change": "trim"})
    assert none.status_code == 422 and "Place something" in none.json()["message"]
    board = {**data, "stripboard": load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")}
    trimmed = c.post("/api/stripboard/size", json={"circuit": board, "change": "trim"}).json()
    assert trimmed["stripboard"]["size"] == [11, 9]
    grown = c.post(
        "/api/stripboard/size",
        json={"circuit": board, "change": "insert", "axis": "column", "at": 0},
    )
    assert grown.json()["stripboard"]["parts"]["Q1"] == {"E": "F3", "B": "F4", "C": "F5"}
    refused = c.post(
        "/api/stripboard/size",
        json={"circuit": board, "change": "remove", "axis": "column", "at": 0},
    )
    assert (
        refused.status_code == 422
        and refused.json()["message"] == "Column A isn't empty: the wire at A1 is on it."
    )


def test_stripboard_edit_places_moves_and_refuses_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-374: a hand edit as the board's new plain form and how far it moved; the first
    placement on no board makes one; a refused edit says why; with shorts off, a short is
    refused."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    first = c.post(
        "/api/stripboard/edit",
        json={"circuit": data, "kind": "place", "ref": "R2", "legs": {"1": [3, 2], "2": [3, 6]}},
    ).json()
    assert first == {
        "stripboard": {"size": [1, 5], "parts": {"R2": {"1": "A1", "2": "A5"}}, "standing": [],
                       "cuts": [], "links": [], "wires": [], "off": {}, "where": {},
                       "notes": [], "dismissed": [], "stand_up": "needed"},
        "shift": [-3, -2],
    }  # fmt: skip
    board = {**data, "stripboard": load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")}
    refused = c.post(
        "/api/stripboard/edit", json={"circuit": board, "kind": "cut", "holes": [[8, 3]]}
    )
    assert refused.status_code == 422 and refused.json()["message"].startswith("R2 is in I4")
    mend = {"circuit": board, "kind": "uncut", "holes": [[6, 7]]}
    assert c.post("/api/stripboard/edit", json=mend).json()["stripboard"]["cuts"] == []
    short = c.post("/api/stripboard/edit", json={**mend, "shorts": False})
    assert short.status_code == 422
    assert short.json()["message"].endswith("Shorts are off in Settings.")
    bare = {**data, "stripboard": {**board["stripboard"], "cuts": [], "links": []}}
    accepted = c.post("/api/stripboard/edit", json={"circuit": bare, "kind": "suggested"}).json()
    assert accepted["stripboard"]["cuts"] == ["D8"]  # every suggestion, one edit (D-377)
    assert sorted(accepted["stripboard"]["links"]) == [["B1", "B8"], ["G2", "G8"]]
    nothing = c.post("/api/stripboard/edit", json={"circuit": board, "kind": "suggested"})
    assert nothing.status_code == 422 and nothing.json()["message"].startswith("Nothing to suggest")


def test_board_notes_and_dismissals_through_the_edit_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-398: `note-add` keeps the builder's note, `dismiss` the warning on two parts; the
    check then lists the note and the dismissed warning apart; a note naming a part the
    board hasn't, or with no text, is a 422 in words."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "tests/fixtures/circuits/old/schema-v39.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    found = c.post("/api/stripboard", json={"circuit": data}).json()
    assert found["overlaps"] == [{"parts": ["TR1", "C1"], "reason": "",
                                  "text": "TR1 and C1's bodies touch: move one a hole "
                                          "further away if you can."}]  # fmt: skip
    note = {"parts": ["C1", "TR1"], "text": "Solder C1 higher.", "overlap": True}
    noted = c.post("/api/stripboard/edit",
                   json={"circuit": data, "kind": "note-add", "note": note}).json()  # fmt: skip
    assert noted["stripboard"]["notes"] == [note]
    data = {**data, "stripboard": noted["stripboard"]}
    gone = c.post("/api/stripboard/edit", json={"circuit": data, "kind": "dismiss", "ref": "C1",
                                                "to": "TR1", "reason": "fine"}).json()  # fmt: skip
    assert gone["stripboard"]["dismissed"] == [{"parts": ["C1", "TR1"], "reason": "fine"}]
    after = c.post("/api/stripboard",
                   json={"circuit": {**data, "stripboard": gone["stripboard"]}}).json()  # fmt: skip
    assert after["overlaps"] == [] and after["dismissed"][0]["reason"] == "fine"
    assert after["notes"] == [{**note, "why": None}]
    bad = c.post("/api/stripboard/edit", json={"circuit": data, "kind": "note-add",
                                               "note": {"parts": ["R9"], "text": "x"}})  # fmt: skip
    assert bad.status_code == 422
    assert bad.json()["message"] == "There's no R9 among the board's parts."
    empty = c.post("/api/stripboard/edit", json={"circuit": data, "kind": "note-add",
                                                 "note": {"text": " "}})  # fmt: skip
    assert empty.status_code == 422 and empty.json()["message"] == "A note needs some text."


def test_stripboard_start_lays_out_or_fills_the_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-387: Start over on an empty board, Fill the rest on one with parts; nothing to
    fill is a 422 in words."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    over = c.post("/api/stripboard/start", json={"circuit": data}).json()
    assert over["left"] == [] and set(over["stripboard"]["parts"]) >= {"Q1", "R1", "C4"}
    started = {**data, "stripboard": over["stripboard"]}
    assert c.post("/api/stripboard", json={"circuit": started}).json()["done"] is True
    good = load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")
    part = {**good, "parts": {k: v for k, v in good["parts"].items() if k != "R2"}}
    body = {"circuit": {**data, "stripboard": part}, "fill": True}
    filled = c.post("/api/stripboard/start", json=body).json()
    assert filled["left"] == [] and filled["stripboard"]["parts"]["Q1"] == good["parts"]["Q1"]
    full = c.post("/api/stripboard/start",
                  json={"circuit": {**data, "stripboard": good}, "fill": True})  # fmt: skip
    assert full.status_code == 422 and "Nothing to fill" in full.json()["message"]


def test_stripboard_tidy_makes_the_board_smaller_or_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-388: Start for me's board tidied (smaller, still done); a part placed wrongly is
    asked about first, then laid out again with `mend`; no board is a 422 in words."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    over = c.post("/api/stripboard/start", json={"circuit": data}).json()["stripboard"]
    tidied = c.post("/api/stripboard/tidy", json={"circuit": {**data, "stripboard": over}}).json()
    (w, h), (w0, h0) = tidied["stripboard"]["size"], over["size"]
    assert w * h < w0 * h0 and tidied["mended"] == []
    done = {**data, "stripboard": tidied["stripboard"]}
    assert c.post("/api/stripboard", json={"circuit": done}).json()["done"] is True
    good = load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")
    moved = {
        **data,
        "stripboard": {**good, "parts": {**good["parts"], "R2": {"1": "J5", "2": "J9"}}},
    }
    asked = c.post("/api/stripboard/tidy", json={"circuit": moved}).json()
    assert asked["refs"] == ["R2"] and "placed wrongly" in asked["ask"]
    mended = c.post("/api/stripboard/tidy", json={"circuit": moved, "mend": True}).json()
    assert mended["mended"] == ["R2"]
    bare = c.post("/api/stripboard/tidy", json={"circuit": data})
    assert bare.status_code == 422 and "nothing on the board" in bare.json()["message"]


def test_stripboard_edit_puts_off_board_parts_and_wires(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-375: an off-board part put beside the board, a wire drawn to a hole, moved to a
    lug, its route moved by hand (D-380), taken off; the part back to the tray takes its
    wires; refusals say why."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    board = {**data, "stripboard": load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")}
    c = client(monkeypatch, lambda _s: FakeEngine())

    def edit(**change: Any) -> Any:
        return c.post("/api/stripboard/edit", json={"circuit": board, **change})

    spot = edit(kind="spot", ref="VR1", holes=[[2, -8]]).json()["stripboard"]
    assert spot["off"] == {"VR1": [2, -8]} and spot["size"] == [12, 9]
    unknown = edit(kind="spot", ref="VR9", holes=[[2, -8]])
    assert unknown.status_code == 422 and "VR9 isn't an off-board part" in unknown.json()["message"]
    wires = board["stripboard"]["wires"]
    i = next(n for n, w in enumerate(wires) if w["from"] == "VR1.2")
    moved = edit(kind="rewire", index=i, ref="VR1.2", holes=[[6, 6]]).json()["stripboard"]
    assert moved["wires"][i] == {"from": "VR1.2", "hole": "G7"}
    to_lug = edit(kind="rewire", index=i, ref="VR1.2", to="IN.out").json()["stripboard"]
    assert to_lug["wires"][i] == {"from": "VR1.2", "lug": "IN.out"}
    loose = edit(kind="wire", ref="VR1.2").json()["stripboard"]
    assert loose["wires"][-1] == {"from": "VR1.2"}
    shared = edit(kind="wire", ref="VR1.2", holes=[[4, 2]])  # Q1's emitter
    assert shared.status_code == 422 and "share hole E3" in shared.json()["message"]
    twice = edit(kind="wire", ref="VR1.1", holes=[[3, 0]])
    assert twice.json()["message"] == "There's a wire there already."
    routed = edit(kind="route", index=i, runs=[[2, -1.234], [1, 3.5], [2, -1.5]]).json()
    assert routed["stripboard"]["wires"][i]["runs"] == [[1, 3.5], [2, -1.5]]  # D-380
    on_routed = {**board, "stripboard": routed["stripboard"]}
    again = c.post("/api/stripboard/edit", json={"circuit": on_routed, "kind": "rewire",
                   "index": i, "ref": "VR1.2", "holes": [[6, 6]]}).json()["stripboard"]  # fmt: skip
    assert "runs" not in again["wires"][i]  # an end moved: routed automatically again
    end_run = edit(kind="route", index=i, runs=[[0, 2.0]])
    assert end_run.status_code == 422 and "middle runs" in end_run.json()["message"]
    off = edit(kind="unwire", index=i).json()["stripboard"]
    assert len(off["wires"]) == len(wires) - 1
    back = {**board, "stripboard": spot}
    gone = c.post(
        "/api/stripboard/edit", json={"circuit": back, "kind": "unspot", "ref": "VR1"}
    ).json()["stripboard"]
    assert gone["off"] == {} and not any(w["from"].startswith("VR1") for w in gone["wires"])


def test_stripboard_edit_clears_what_the_circuit_no_longer_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-376: one edit takes off a part deleted from the schematic, with nothing else."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    good = load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")
    parts = {**good["parts"], "R9": {"1": "L1", "2": "L5"}}
    board = {**data, "stripboard": {**good, "parts": parts}}
    c = client(monkeypatch, lambda _s: FakeEngine())
    stale = c.post("/api/stripboard", json={"circuit": board}).json()["stale"]
    assert stale == ["R9"]
    cleared = c.post("/api/stripboard/edit", json={"circuit": board, "kind": "clear"})
    assert "R9" not in cleared.json()["stripboard"]["parts"]
    assert len(cleared.json()["stripboard"]["parts"]) == len(good["parts"])


def test_stripboard_edit_moves_a_part_off_the_board_and_refuses_a_pot_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-385: a part moved off the board by choice; one with no footprint can't go on."""
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    good = load_yaml(repo / "tests/fixtures/stripboard/rangemaster.yaml")
    board = {**data, "stripboard": good}
    c = client(monkeypatch, lambda _s: FakeEngine())
    off = {"circuit": board, "kind": "where", "ref": "R2", "to": "off-board"}
    moved = c.post("/api/stripboard/edit", json=off).json()["stripboard"]
    assert moved["where"] == {"R2": "off-board"} and "R2" not in moved["parts"]
    after = c.post("/api/stripboard", json={"circuit": {**data, "stripboard": moved}}).json()
    assert after["choices"]["R2"] == {"where": "off-board", "moved": True, "why": None}
    pot = c.post("/api/stripboard/edit",
                 json={"circuit": board, "kind": "where", "ref": "VR1", "to": "board"})  # fmt: skip
    assert pot.status_code == 422
    assert pot.json()["message"] == "There's no board footprint for a pot yet."


# --- Build a full layout (D-399) -------------------------------------------------------


def _compact_lines(c: TestClient, data: dict[str, Any], **ask: Any) -> list[dict[str, Any]]:
    body = {"circuit": data, "progress": True, **ask}
    with c.stream("POST", "/api/stripboard/compact", json=body) as r:
        assert r.status_code == 200
        return [json.loads(line) for line in r.iter_lines() if line]


def test_build_a_full_layout_streams_the_base_progress_and_a_checked_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Rangemaster (few steps, for speed): the base first, then the steps done of the
    budget (four attempts and the flat one, D-403) and each new best, then a wired board
    that passes the check, and the same board again (the flat board kept); *Try another*
    is another seed set."""
    from solum.stripboard import compact_job

    monkeypatch.setattr(compact_job, "STEPS_PER_PART", 300)
    monkeypatch.setattr(compact_job, "_flat", {})
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    lines = _compact_lines(c, data)
    assert set(lines[0]) == {"base"} and lines[0]["base"]["stripboard"]["parts"]
    progress = lines[1:-1]
    assert progress and all(line["of"] == 5 * 300 * 8 for line in progress)  # 8 board parts
    assert progress[-1]["done"] == progress[-1]["of"]
    assert any("best" in line for line in progress)
    result = lines[-1]["result"]
    assert result["fell_back"] is False and result["stopped"] is False
    board = {**data, "stripboard": result["stripboard"]}
    assert c.post("/api/stripboard", json={"circuit": board}).json()["done"] is True
    assert result["columns"] * result["strips"] < 9 * 12  # the hand-made board's 11 × 9 or so
    assert _compact_lines(c, data)[-1]["result"] == result
    other = c.post("/api/stripboard/compact", json={"circuit": data, "attempt": 2}).json()
    assert {"stripboard", "columns", "fell_back"} <= set(other)


def test_stop_s_finish_wires_and_checks_the_best_so_far(monkeypatch: pytest.MonkeyPatch) -> None:
    """A best board as streamed (not wired) sent back: wired, passing the check; nothing
    for a board is a 422 in words."""
    from solum.stripboard import compact_job

    monkeypatch.setattr(compact_job, "STEPS_PER_PART", 300)
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    c = client(monkeypatch, lambda _s: FakeEngine())
    best = [line["best"] for line in _compact_lines(c, data) if "best" in line][-1]
    assert best["stripboard"]["wires"] == []
    done = c.post("/api/stripboard/compact/finish",
                  json={"circuit": data, "board": best["stripboard"]}).json()  # fmt: skip
    assert done["stopped"] is True and done["stripboard"]["wires"]
    board = {**data, "stripboard": done["stripboard"]}
    assert c.post("/api/stripboard", json={"circuit": board}).json()["done"] is True
    empty = {**data, "parts": [p for p in data["parts"] if p["type"] in ("guitar", "amp")]}
    refused = c.post("/api/stripboard/compact/estimate", json={"circuit": empty})
    assert refused.status_code == 422 and "board" in refused.json()["message"]


def test_the_time_estimate_is_this_circuit_s_on_this_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Half a second of real steps timed: Thorough takes longer than Quick, both more
    than the workers' start."""
    from solum.stripboard import compact_job

    monkeypatch.setattr(compact_job, "SAMPLE", 0.1)
    repo = Path(__file__).resolve().parents[2]
    data = circuit_to_dict(load_circuit(repo / "library/starters/dallas-rangemaster.json"))
    got = (
        client(monkeypatch, lambda _s: FakeEngine())
        .post("/api/stripboard/compact/estimate", json={"circuit": data})
        .json()
    )
    assert compact_job.SPAWN < got["quick"] < got["thorough"]
