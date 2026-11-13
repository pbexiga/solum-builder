from pathlib import Path

import pytest

from solum.config import load_settings


def test_defaults_point_at_repo_library_and_web() -> None:
    s = load_settings({})
    assert s.port == 8000
    assert (s.library_dir / "bench" / "big-muff.cir").is_file()
    assert (s.web_dir / "index.html").is_file()
    assert s.ngspice_library is None


def test_reads_environment_values() -> None:
    s = load_settings(
        {
            "DATA_DIR": "/d",
            "CACHE_DIR": "/c",
            "PORT": "9001",
            "NGSPICE_LIBRARY": "/x/libngspice.so",
        }
    )
    assert (s.data_dir, s.cache_dir, s.port) == (Path("/d"), Path("/c"), 9001)
    assert s.ngspice_library == "/x/libngspice.so"


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"CACHE_MAX_GB": "lots"}, "CACHE_MAX_GB must be a number"),
        ({"CACHE_MAX_GB": "0"}, "CACHE_MAX_GB must be more than 0"),
        ({"PORT": "eighty"}, "PORT must be a whole number"),
    ],
)
def test_invalid_values_explain_the_fix(env: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_settings(env)


def test_cache_limit() -> None:
    assert load_settings({}).cache_max_gb == 2.0
    assert load_settings({"CACHE_MAX_GB": "0.5"}).cache_max_gb == 0.5
    with pytest.raises(ValueError, match="CACHE_MAX_GB must be a number"):
        load_settings({"CACHE_MAX_GB": "lots"})
    with pytest.raises(ValueError, match="more than 0"):
        load_settings({"CACHE_MAX_GB": "0"})


def test_only_the_launcher_lets_settings_move_the_folders() -> None:
    """D-310: false in Docker and from source; the Mac app's launcher sets the flag."""
    assert load_settings({}).can_move_folders is False
    assert load_settings({"CAN_MOVE_FOLDERS": "1"}).can_move_folders is True
