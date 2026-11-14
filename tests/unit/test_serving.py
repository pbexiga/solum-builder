"""The app on a free local port (D-321, D-314): the Mac app's server and the UI tests'."""

import json
import urllib.request
from pathlib import Path

import pytest

from solum.api.serving import HOST, LocalServer, free_port, serving, wait_for_health
from solum.config import load_settings


def test_a_free_port_is_on_this_machine_only() -> None:
    assert HOST == "127.0.0.1"
    assert 1024 < free_port() < 65536


def test_waiting_for_a_server_that_isnt_there_gives_up() -> None:
    assert wait_for_health(free_port(), seconds=0.2) is False


def test_the_server_starts_answers_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    server = LocalServer()
    server.stop()  # nothing started: nothing to do
    assert server.start() is True
    assert server.url == f"http://127.0.0.1:{server.port}/"
    with urllib.request.urlopen(server.url + "api/settings") as r:
        assert json.load(r)["data_dir"] == str(tmp_path / "data")
    first = server.port
    server.stop()
    assert wait_for_health(first, seconds=0.2) is False
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "moved"))  # a moved folder: started again
    assert server.start() is True
    with urllib.request.urlopen(server.url + "api/settings") as r:
        assert json.load(r)["data_dir"] == str(tmp_path / "moved")
    server.stop()


def test_serving_gives_the_address_for_the_block_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    with serving(load_settings()) as url:
        port = int(url.rsplit(":", 1)[1].rstrip("/"))
        assert url == f"http://127.0.0.1:{port}/"
        assert wait_for_health(port, seconds=5) is True
    assert wait_for_health(port, seconds=0.2) is False
