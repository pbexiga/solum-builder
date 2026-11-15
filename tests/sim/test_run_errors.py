"""A refused or failed run's error says where it points, so the page can mark it (D-345)."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from solum.api.app import create_app
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import circuit_to_dict
from solum.config import load_settings

REPO = Path(__file__).parents[2]
STUCK = REPO / "tests" / "fixtures" / "rule-models" / "bjt"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """The app, with the test transistor that can't be solved among the user's models."""
    models = tmp_path / "data" / "models" / "bjt"
    models.mkdir(parents=True)
    for f in STUCK.glob("TESTSTUCK.*"):
        shutil.copy(f, models / f.name)
    settings = load_settings({"DATA_DIR": str(tmp_path / "data"),
                              "CACHE_DIR": str(tmp_path / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    return TestClient(create_app(settings))


def run(client: TestClient, b: CircuitBuilder) -> tuple[int, dict[str, Any]]:
    got = client.post("/api/run", json={"circuit": circuit_to_dict(b.build()), "nodes": []})
    return got.status_code, got.json()


def latch(model: str) -> CircuitBuilder:
    return (
        CircuitBuilder("latch")
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "a", value="10k")
        .part("R2", "resistor", "V+", "c", value="4k7")
        .part("Q1", "bjt", "c", "a", "e", model=model)
        .part("R3", "resistor", "e", "GND", value="1k")
        .part("Q2", "bjt", "a", "c", "GND", model=model)
    )


def test_a_run_that_gets_stuck_names_the_part(client: TestClient) -> None:
    status, body = run(client, latch("TESTSTUCK"))
    assert status == 422
    assert body["message"].endswith("It got stuck at Q1.")
    assert body["where"] == {"refs": ["Q1"], "nets": [], "at": []}


def test_a_missing_model_names_the_part(client: TestClient) -> None:
    status, body = run(client, latch("NOSUCH1"))
    assert status == 422
    assert body["message"].startswith("Can't simulate yet: Q1 names the model NOSUCH1")
    assert body["where"]["refs"] == ["Q1"]


def test_a_floating_net_names_the_net(client: TestClient) -> None:
    b = (
        CircuitBuilder("floating")
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "GND", value="10k")
        .part("C1", "capacitor", "GND", "f", value="100n")
        .part("C2", "capacitor", "f", "GND", value="100n")
    )
    status, body = run(client, b)
    assert status == 422
    assert body["where"]["nets"] == ["f"] and body["where"]["refs"] == []


def test_an_unreachable_bias_target_names_the_trimmer(client: TestClient) -> None:
    target = {"node": "Q1.D", "volts": 12}
    b = (
        CircuitBuilder("jfet")
        .rail("V+", 9)
        .part("TR1", "trimmer", "V+", "d", "d", value="50k", bias_target=target)
        .part("Q1", "jfet", "d", "GND", "GND", model="J201")
    )
    status, body = run(client, b)
    assert status == 422
    assert body["message"].startswith("TR1 can't set d to 12 V")
    assert body["where"]["refs"] == ["TR1"]


def test_a_run_that_works_has_no_error(client: TestClient) -> None:
    status, body = run(client, latch("2N3904"))
    assert status == 200 and "where" not in body


def test_a_measured_gain_no_model_reaches_names_the_transistor(client: TestClient) -> None:
    """A measured transistor whose model can't be made to read its gain is a plain error
    on that part, not "something went wrong" (D-345)."""
    measured = {"hfe": 85, "leakage": 9.8e-6}
    b = (
        CircuitBuilder("measured")
        .rail("V+", 9)
        .part("R1", "resistor", "V+", "c", value="10k")
        .part("R2", "resistor", "V+", "b", value="1M")
        .part("Q1", "bjt", "c", "b", "GND", model="TESTSTUCK", measured=measured)
    )
    status, body = run(client, b)
    assert status == 422
    assert body["message"].startswith("The TESTSTUCK model can't be made to read a gain of 85")
    assert body["where"]["refs"] == ["Q1"]
