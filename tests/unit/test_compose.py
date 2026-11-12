"""`docker compose` builds the runtime image, not the Dockerfile's last stage (the dev image)."""

from pathlib import Path

from solum.yamlio import load_yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_builds_the_runtime_stage() -> None:
    service = load_yaml(ROOT / "compose.yaml")["services"]["solum-builder"]
    assert service["build"]["target"] == "runtime"
    assert "FROM ${BASE} AS runtime" in (ROOT / "Dockerfile").read_text()
