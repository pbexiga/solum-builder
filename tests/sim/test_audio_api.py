"""The audio routes with the real engine and worker processes (D-083)."""

import io
import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.audio.wav import Audio, read_wav, write_wav
from solum.circuit.io import load_circuit
from solum.config import load_settings

REPO = Path(__file__).parents[2]
NAM = REPO / "tests" / "fixtures" / "nam" / "standard-random.nam"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = load_settings({"DATA_DIR": str(tmp_path / "data"),
                              "CACHE_DIR": str(tmp_path / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    return TestClient(create_app(settings))


def clip(seconds: float = 0.2) -> bytes:
    t = np.arange(int(44100 * seconds)) / 44100
    return write_wav(Audio(44100, 0.5 * np.sin(2 * np.pi * 196 * t)))


def ts808() -> dict[str, Any]:
    return load_circuit(REPO / "library" / "starters" / "ts808.json").model_dump(
        mode="json", by_alias=True
    )


def finish(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    deadline = time.monotonic() + 120
    while job["state"] in ("queued", "running"):
        assert time.monotonic() < deadline
        time.sleep(0.1)
        job = client.get(f"/api/render/{job['id']}").json()
    return job


def upload(client: TestClient, kind: str, name: str, data: bytes) -> dict[str, Any]:
    r = client.post(f"/api/audio/{kind}", params={"name": name}, content=data)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def test_upload_render_play_and_replay_from_cache(client: TestClient) -> None:
    riff = upload(client, "clips", "Riff.wav", clip())
    amp = upload(client, "captures", "amp.nam", NAM.read_bytes())
    listed = client.get("/api/audio").json()
    assert [c["id"] for c in listed["clips"] if c["layer"] == "user"] == ["riff"]
    request = {"circuit": ts808(), "clip": {"id": riff["id"], "layer": "user"},
               "capture": {"id": amp["id"], "layer": "user"}}  # fmt: skip
    # looking it up only: not rendered yet, so nothing, and nothing is started
    lookup = {**request, "cached_only": True}
    assert client.post("/api/render", json=lookup).json() is None
    time.sleep(0.3)
    assert client.post("/api/render", json=lookup).json() is None
    job = finish(client, client.post("/api/render", json=request).json())
    assert job["state"] == "done", job["message"]
    wav = client.get(f"/api/render/audio/{job['key']}.wav", params={"download": "ts808 a"})
    assert wav.headers["content-type"] == "audio/wav"
    assert 'filename="ts808 a.wav"' in wav.headers["content-disposition"]
    assert read_wav(wav.content).seconds == pytest.approx(0.2)
    spectra = client.get(f"/api/render/spectrum/{job['key']}").json()  # D-096
    assert set(spectra) == {"freq", "pedal", "heard", "di", "pedal_top"}
    assert spectra["pedal_top"] == 48000  # the 96 kHz simulation (D-105)
    # the pedal line from the 96 kHz simulation: 10 Hz to 30 kHz (D-105)
    assert len(spectra["pedal"]) == len(spectra["heard"]) == len(spectra["freq"]) == 70
    assert spectra["heard"][-2:] == [-200.0, -200.0]  # 48 kHz: nothing above the 23 kHz band
    assert spectra["di"] == [0.0] * 70  # the starter's guitar has no pickup
    assert client.get("/api/render/spectrum/nothere").status_code == 404
    again = client.post("/api/render", json=request).json()
    assert again["state"] == "done" and again["key"] == job["key"]  # instant, from cache
    found = client.post("/api/render", json=lookup).json()  # a lookup finds it now
    assert found["state"] == "done" and found["key"] == job["key"]
    assert found["seconds"] == pytest.approx(0.2)  # with its stats
    dry = finish(client, client.post("/api/render", json={**request, "circuit": None}).json())
    assert dry["state"] == "done" and dry["label"] == "dry" and dry["key"] != job["key"]


def test_render_sweep_runs_one_job_per_position(client: TestClient) -> None:
    riff = upload(client, "clips", "riff.wav", clip(0.1))
    pot = next(p["ref"] for p in ts808()["parts"] if p["type"] == "pot")
    sweep = {"circuit": ts808(), "clip": {"id": riff["id"], "layer": "user"},
             "ref": pot, "rotations": [0.0, 0.5, 1.0]}  # fmt: skip
    lookup = {**sweep, "rotations": [0.0, 0.25], "cached_only": True}
    assert client.post("/api/render/sweep", json=lookup).json() == [None, None]
    jobs = client.post("/api/render/sweep", json=sweep).json()
    done = [finish(client, j) for j in jobs]
    # a lookup has the positions rendered, and nothing for the others
    found = client.post("/api/render/sweep", json=lookup).json()
    assert found[0]["key"] == done[0]["key"] and found[1] is None
    assert [j["label"] for j in done] == [f"{pot} at 0 %", f"{pot} at 50 %", f"{pot} at 100 %"]
    assert all(j["state"] == "done" for j in done)
    assert len({j["key"] for j in done}) == 3
    # all of them in one zip, with a note beside them (D-096)
    takes = [{"key": j["key"], "file": f"TS808 {j['label']}.wav"} for j in done]
    r = client.post("/api/render/zip", json={"name": "TS808", "takes": takes,
                                              "files": {"takes.txt": "notes"}})  # fmt: skip
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="TS808.zip"' in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.namelist() == [t["file"] for t in takes] + ["takes.txt"]
        assert read_wav(z.read(takes[0]["file"])).seconds == pytest.approx(0.1)
    gone = client.post(
        "/api/render/zip", json={"name": "x", "takes": [{"key": "ab12", "file": "Old.wav"}]}
    )
    assert gone.status_code == 404 and "Old.wav isn't in the cache" in gone.json()["message"]


def tone_bender(target: bool = True) -> dict[str, Any]:
    circuit = load_circuit(REPO / "library" / "starters" / "tone-bender-mk2-mode.json")
    if not target:
        circuit = circuit.with_part("TR1", bias_target=None)
    return circuit.model_dump(mode="json", by_alias=True)


def test_a_trimmer_sweep_marks_the_positions_that_saturate(client: TestClient) -> None:
    """D-198: TR1 turned by hand (its target removed) saturates Q2 from about 75 %; TR2
    never does. A trimmer its target sets can't be swept or checked."""
    check = {"circuit": tone_bender(target=False), "ref": "TR1", "rotations": [0.25, 0.5, 0.75]}
    found = client.post("/api/render/sweep/check", json=check).json()
    assert found[:2] == [[], []]
    assert [(s["ref"], s["state"]) for s in found[2]] == [("Q2", "saturated")]
    assert "Q2 is fully on" in found[2][0]["message"]
    held = {**check, "circuit": tone_bender()}
    other = client.post("/api/render/sweep/check", json={**held, "ref": "TR2"}).json()
    assert other == [[], [], []]
    for url, extra in (("/api/render/sweep/check", {}),
                       ("/api/render/sweep", {"clip": {"id": "x", "layer": "user"}})):  # fmt: skip
        r = client.post(url, json={**held, **extra})
        assert r.status_code == 422
        assert r.json()["message"] == (
            "TR1 is set by its bias target, so turning it changes nothing. "
            "Open it and remove the target to sweep it."
        )


def test_plain_errors(client: TestClient) -> None:
    r = client.post("/api/audio/clips", params={"name": "x.mp3"}, content=b"ID3....")
    assert r.status_code == 422 and "WAV" in r.json()["message"]
    r = client.post("/api/render", json={"clip": {"id": "nope", "layer": "user"}})
    assert r.status_code == 422 and "no clip called 'nope'" in r.json()["message"]
    # looking up only never fails: a missing clip or a half-drawn circuit just finds nothing
    for bad in (
        {"clip": {"id": "nope", "layer": "user"}},
        {"clip": {"id": "nope", "layer": "user"}, "ref": "VR1", "rotations": [0.5]},
    ):
        route = "/api/render/sweep" if "ref" in bad else "/api/render"
        r = client.post(route, json={**bad, "circuit": {"parts": "no"}, "cached_only": True})
        assert r.status_code == 200 and r.json() in (None, [None]), r.text
    assert client.get("/api/render/unknown").status_code == 404
    assert client.get("/api/render/audio/ab12.wav").status_code == 404
    assert client.delete("/api/audio/clips/nope").status_code == 422
