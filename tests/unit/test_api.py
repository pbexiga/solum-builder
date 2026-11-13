import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solum.api import app as app_module
from solum.cache import cache_from_settings
from solum.config import load_settings
from solum.model_import import Added, make_model
from solum.models import ModelLibrary, ModelType
from solum.sim.engine import EngineUnavailable, SimResult
from tests.unit.test_model_import import FILE, fake_measure


class FakeEngine:
    name = "native"

    def version(self) -> str:
        return "44.2"

    def run(self, netlist: str) -> SimResult:
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
        "cache_max_gb": 3.0,
        "cache_used_bytes": 0,
        "can_move_folders": False,
        "preferences": None,
    }
    assert not (tmp_path / "data" / "solum-settings.json").exists()


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
    assert labels == ["Guitar volume", "Distortion", "Tone", "Level"]


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
    monkeypatch.setattr(app_module, "engine_from_settings", lambda _s: FakeEngine())
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
    assert models["led"] == ["APT1608SURCK", "WP7113GD", "WP7113QBC-D", "WP7113QWC-D"]
    assert models["chargepump"] == ["ICL7660", "LT1054", "MAX1044", "TC1044S"]
    assert models["mosfet"] == ["2N7000", "BS170", "LND150"]
    assert models["regulator"] == ["78L12"]
    assert set(models) == {
        "diode", "led", "jfet", "bjt", "mosfet", "opamp", "inverter", "ota", "chargepump",
        "regulator",
        "yours", "zeners",
    }  # fmt: skip
    assert models["yours"] == []  # the user's own models' ids (9c), none in a fresh DATA_DIR
    # the diodes whose record checks a zener voltage: a diode set to one is named Z
    assert models["zeners"] == ["1N4738A", "1N4739A", "1N4742A"]


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
                          "refs", "nets", "build"}  # fmt: skip
    assert first["nets"] == ["a"]


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
