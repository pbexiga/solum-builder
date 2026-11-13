"""`docker compose` builds the runtime image, not the Dockerfile's last stage (the dev image)."""

import re
from pathlib import Path

from solum.yamlio import load_yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_builds_the_runtime_stage() -> None:
    service = load_yaml(ROOT / "compose.yaml")["services"]["solum-builder"]
    assert service["build"]["target"] == "runtime"
    assert "FROM ${BASE} AS runtime" in (ROOT / "Dockerfile").read_text()


def test_compose_runs_without_an_env_file_and_names_the_host_folders() -> None:
    """D-313: every variable has a default, and Settings is told the two host folders by
    the same expressions the mounts use."""
    text = (ROOT / "compose.yaml").read_text()
    service = load_yaml(ROOT / "compose.yaml")["services"]["solum-builder"]
    assert service["volumes"] == ["${DATA_DIR:-./data}:/data", "${CACHE_DIR:-./cache}:/cache"]
    assert service["environment"]["HOST_DATA_DIR"] == "${DATA_DIR:-./data}"
    assert service["environment"]["HOST_CACHE_DIR"] == "${CACHE_DIR:-./cache}"
    assert all(":-" in use for use in re.findall(r"\$\{[^}]*\}", text))
