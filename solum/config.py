"""Runtime settings, read once from the environment (see `.env.example`)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cache_dir: Path
    library_dir: Path
    web_dir: Path
    guide_dir: Path  # the user guide's Markdown pages (Help → Documentation, D-290)
    port: int
    ngspice_library: str | None
    cache_max_gb: float = 2.0
    # Settings may change the two folders: only the Mac app's launcher sets it (D-310)
    can_move_folders: bool = False


def cache_gb(value: object, name: str) -> float:
    """A largest cache size in gigabytes, from the environment or Settings. ValueError in
    plain English, starting with `name`."""
    try:
        size = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number of gigabytes (got {value!r}).") from None
    if not 0 < size < float("inf"):
        raise ValueError(f"{name} must be more than 0.")
    return size


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from `env` (default: the process environment).

    Raises ValueError with a plain-English message for invalid values.
    """
    env = os.environ if env is None else env
    port_text = env.get("PORT", "8000")
    try:
        port = int(port_text)
    except ValueError:
        raise ValueError(f"PORT must be a whole number (got {port_text!r}).") from None
    cache_max_gb = cache_gb(env.get("CACHE_MAX_GB", "2"), "CACHE_MAX_GB")
    return Settings(
        data_dir=Path(env.get("DATA_DIR", "./data")),
        cache_dir=Path(env.get("CACHE_DIR", "./cache")),
        library_dir=Path(env.get("LIBRARY_DIR", str(_REPO_ROOT / "library"))),
        web_dir=Path(env.get("WEB_DIR", str(_REPO_ROOT / "web"))),
        guide_dir=Path(env.get("GUIDE_DIR", str(_REPO_ROOT / "docs" / "guide"))),
        port=port,
        ngspice_library=env.get("NGSPICE_LIBRARY") or None,
        cache_max_gb=cache_max_gb,
        can_move_folders=env.get("CAN_MOVE_FOLDERS", "") == "1",
    )
