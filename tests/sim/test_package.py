"""The build package (9d1, D-210) through the API with the real simulator."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.audio.bundle import safe_file_name
from solum.circuit.schema import SCHEMA_VERSION
from solum.config import load_settings

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
       '<line x1="0" y1="0" x2="10" y2="10" stroke="black"/></svg>')  # fmt: skip


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    return TestClient(create_app(load_settings()))


def test_the_tone_bender_package_holds_every_output(client: TestClient) -> None:
    """The Aion version: its bias trimmers give it a bias sheet (D-251)."""
    body = {"svg": SVG, "ready": [{"severity": "info", "text": "No enclosure chosen."}],
            "dismissed": 1}  # fmt: skip
    got = client.post("/api/export/starter/tone-bender-mk2-mode/package.zip", json=body)
    assert got.status_code == 200
    folder = safe_file_name("Tone Bender MkII (Aion Deimos, Mode switch) build package")
    assert f'filename="{folder}.zip"' in got.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(got.content))
    folder += "/"
    names = {n.removeprefix(folder) for n in z.namelist()}
    assert all(n.startswith(folder) for n in z.namelist())
    assert names >= {"index.html", "circuit.json", "parts-list.pdf", "parts-list.csv",
                     "schematic.pdf", "schematic.svg", "bias-sheet.pdf", "notes.pdf",
                     "wiring.pdf", "netlists/op.cir", "netlists/ac.cir", "netlists/tran.cir",
                     "netlists/models.txt", "netlists/models/OC75.lib"}  # fmt: skip
    for pdf in ("parts-list.pdf", "schematic.pdf", "bias-sheet.pdf", "notes.pdf", "wiring.pdf"):
        assert z.read(folder + pdf).startswith(b"%PDF")
    index = z.read(folder + "index.html").decode()
    assert "<strong>Note</strong>: No enclosure chosen." in index and "1 dismissed" in index
    assert '<a href="bias-sheet.pdf">' in index
    saved = json.loads(z.read(folder + "circuit.json"))
    assert saved["name"] == "Tone Bender MkII (Aion Deimos, Mode switch)"
    assert saved["schema"] == SCHEMA_VERSION
    assert z.read(folder + "parts-list.csv").startswith("\ufeff".encode())


def test_a_drawing_that_isnt_one_is_refused(client: TestClient) -> None:
    got = client.post("/api/export/starter/ts808/package.zip", json={"svg": "<svg>no size</svg>"})
    assert got.status_code == 422, got.text
    assert "drawing of the circuit" in got.json()["message"]


STARTERS = sorted((Path(__file__).resolve().parents[2] / "library" / "starters").glob("*.json"))


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_every_starter_makes_a_whole_package(client: TestClient, path: Path) -> None:
    """9d1's acceptance: each output, for any starter, with the bias sheet and netlists."""
    got = client.post(f"/api/export/starter/{path.stem}/package.zip", json={"svg": SVG})
    assert got.status_code == 200, got.text
    names = {n.split("/", 1)[1] for n in zipfile.ZipFile(io.BytesIO(got.content)).namelist()}
    assert {"index.html", "circuit.json", "bias-sheet.pdf", "netlists/op.cir"} <= names


REPO = Path(__file__).resolve().parents[2]
BOARD = {"parts": SVG, "bare": SVG, "copper": SVG}


def saved_with_board(client: TestClient, drop: str = "") -> str:
    """The Rangemaster saved with P6a's hand-made board; `drop`: a part taken out of the
    circuit afterwards, so the board is stale. Its id."""
    from solum.stripboard.board import layout_data, layout_from_data
    from solum.yamlio import load_yaml

    circuit = json.loads((REPO / "library" / "starters" / "dallas-rangemaster.json").read_text())
    board = load_yaml(REPO / "tests" / "fixtures" / "stripboard" / "rangemaster.yaml")
    circuit["stripboard"] = layout_data(layout_from_data(board))
    if drop:
        circuit["parts"] = [p for p in circuit["parts"] if p["ref"] != drop]
        circuit["wires"] = []
    got = client.post("/api/circuits", json={"circuit": circuit, "name": f"Board {drop}"})
    assert got.status_code == 200, got.text
    return str(got.json()["circuit"]["id"])


def package_names(client: TestClient, url: str) -> tuple[set[str], str]:
    got = client.post(url, json={"svg": SVG, "board": BOARD})
    assert got.status_code == 200, got.text
    z = zipfile.ZipFile(io.BytesIO(got.content))
    names = {n.split("/", 1)[1]: n for n in z.namelist()}
    return set(names), z.read(names["index.html"]).decode()


def test_a_kept_board_goes_in_the_package_and_a_stale_one_is_said(client: TestClient) -> None:
    """P6e (D-386): the board re-checked against the circuit as saved."""
    good = saved_with_board(client)
    names, index = package_names(client, f"/api/export/circuit/{good}/package.zip")
    assert "stripboard.pdf" in names and '<a href="stripboard.pdf">' in index
    alone = client.post(f"/api/export/circuit/{good}/stripboard.pdf", json=BOARD)
    assert alone.status_code == 200 and alone.content.startswith(b"%PDF")
    stale = saved_with_board(client, drop="R2")
    names, index = package_names(client, f"/api/export/circuit/{stale}/package.zip")
    assert "stripboard.pdf" not in names
    assert "<strong>Note</strong>: The stripboard layout doesn&#x27;t match the circuit" in index
    refused = client.post(f"/api/export/circuit/{stale}/stripboard.pdf", json=BOARD)
    assert refused.status_code == 422 and "R2" in refused.json()["message"]


def test_no_board_kept_is_a_note_in_the_package(client: TestClient) -> None:
    names, index = package_names(client, "/api/export/starter/ts808/package.zip")
    assert "stripboard.pdf" not in names
    assert "<strong>Note</strong>: No stripboard layout kept." in index
    got = client.post("/api/export/starter/ts808/stripboard.pdf", json=BOARD)
    assert got.status_code == 422 and got.json()["message"] == "No stripboard layout kept."
