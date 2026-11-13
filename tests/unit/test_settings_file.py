"""The settings file (D-310, D-311): the largest cache size and the page's preferences."""

import json
import re
from pathlib import Path

import pytest

from solum.cache import cache_from_settings
from solum.config import load_settings
from solum.settings_file import (
    PREFERENCE_KEYS,
    SETTINGS_FILE,
    Saved,
    SettingsError,
    SettingsFile,
    cache_max_gb,
    with_preferences,
)

WEB = Path(__file__).parents[2] / "web"
PAGE = '<!doctype html>\n<html lang="en">\n<head>\n<script src="theme-start.js"></script></head>'


def test_nothing_kept_until_something_is_changed(tmp_path: Path) -> None:
    file = SettingsFile(tmp_path)
    assert file.load() == Saved(cache_max_gb=None, preferences=None)
    assert not (tmp_path / SETTINGS_FILE).exists()


def test_round_trip_through_the_file(tmp_path: Path) -> None:
    SettingsFile(tmp_path).change(cache_max_gb=3.5, preferences={"solum.theme": "dark"})
    assert json.loads((tmp_path / SETTINGS_FILE).read_text()) == {
        "cache_max_gb": 3.5,
        "preferences": {"solum.theme": "dark"},
    }
    again = SettingsFile(tmp_path).load()  # as after a restart
    assert again == Saved(cache_max_gb=3.5, preferences={"solum.theme": "dark"})


def test_a_change_keeps_what_it_does_not_name(tmp_path: Path) -> None:
    file = SettingsFile(tmp_path)
    file.change(cache_max_gb=1.0)
    assert file.load().preferences is None  # the size alone doesn't mark preferences as set
    file.change(preferences={"solum.autorun": 1, "solum.panes": ["dc", "probe"]})
    file.change(preferences={"solum.theme": "light"})
    assert file.load() == Saved(
        cache_max_gb=1.0,
        preferences={"solum.autorun": 1, "solum.panes": ["dc", "probe"], "solum.theme": "light"},
    )


def test_a_null_forgets_a_preference_and_empty_marks_them_set(tmp_path: Path) -> None:
    file = SettingsFile(tmp_path)
    assert file.change(preferences={}).preferences == {}
    file.change(preferences={"solum.theme": "dark", "solum.autorun": 1})
    assert file.change(preferences={"solum.theme": None}).preferences == {"solum.autorun": 1}


@pytest.mark.parametrize(
    ("size", "message"),
    [(0, "The largest cache size must be more than 0."), (-2, "must be more than 0")],
)
def test_bad_cache_sizes_are_refused_in_plain_english(
    tmp_path: Path, size: float, message: str
) -> None:
    file = SettingsFile(tmp_path)
    with pytest.raises(SettingsError, match=re.escape(message)):
        file.change(cache_max_gb=size)
    assert file.load() == Saved()


def test_only_the_moved_preferences_are_kept(tmp_path: Path) -> None:
    file = SettingsFile(tmp_path)
    with pytest.raises(SettingsError, match=re.escape("'solum.audio' isn't a preference")):
        file.change(preferences={"solum.audio": {"clip": "x"}})
    with pytest.raises(SettingsError, match="too long"):
        file.change(preferences={"solum.panes": ["pane"] * 2000})
    assert file.load() == Saved()


def test_a_garbled_file_is_as_good_as_none(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_FILE).write_text("{not json")
    file = SettingsFile(tmp_path)
    assert file.load() == Saved()
    (tmp_path / SETTINGS_FILE).write_text('{"cache_max_gb": "lots", "preferences": []}')
    assert file.load() == Saved()
    assert file.change(cache_max_gb=2.0) == Saved(cache_max_gb=2.0)


def test_a_change_by_another_process_is_seen(tmp_path: Path) -> None:
    """The render workers' caches read the size the server wrote."""
    here, there = SettingsFile(tmp_path), SettingsFile(tmp_path)
    assert here.load().cache_max_gb is None
    there.change(cache_max_gb=4.0)
    assert here.load().cache_max_gb == pytest.approx(4.0)
    there.change(cache_max_gb=0.25)
    assert here.load().cache_max_gb == pytest.approx(0.25)


def test_the_file_wins_over_the_environment_once_set(tmp_path: Path) -> None:
    settings = load_settings({"DATA_DIR": str(tmp_path), "CACHE_MAX_GB": "5"})
    assert cache_max_gb(settings, Saved()) == pytest.approx(5.0)
    assert cache_max_gb(settings, Saved(cache_max_gb=0.5)) == pytest.approx(0.5)


def test_the_cache_follows_the_file_at_once(tmp_path: Path) -> None:
    env = {"DATA_DIR": str(tmp_path / "d"), "CACHE_DIR": str(tmp_path / "c"), "CACHE_MAX_GB": "5"}
    settings = load_settings(env)
    cache = cache_from_settings(settings)
    assert cache.max_bytes == 5_000_000_000
    SettingsFile(settings.data_dir).change(cache_max_gb=0.5)
    assert cache.max_bytes == 500_000_000


def test_the_page_arrives_with_the_theme_and_the_preferences() -> None:
    saved = Saved(preferences={"solum.theme": "light", "solum.panes": ["dc"]})
    html = with_preferences(PAGE, saved)
    assert '<html data-theme="light" lang="en">' in html
    sent = html.split('<script id="solum-prefs" type="application/json">')[1].split("</script>")[0]
    assert json.loads(sent) == saved.preferences
    # before the early script, which looks for it
    assert html.index("solum-prefs") < html.index("theme-start.js")


def test_the_page_says_when_no_preferences_are_kept_yet() -> None:
    html = with_preferences(PAGE, Saved())
    assert '<script id="solum-prefs" type="application/json">null</script>' in html
    assert "data-theme" not in html
    assert "data-theme" not in with_preferences(PAGE, Saved(preferences={}))


def test_a_preference_cannot_break_out_of_the_page() -> None:
    saved = Saved(preferences={"solum.theme": '"><script>x', "solum.large": ["</script><b>"]})
    html = with_preferences(PAGE, saved)
    assert "data-theme" not in html  # not a theme's name: left off
    assert "</script><b>" not in html
    sent = html.split('type="application/json">')[1].split("</script>")[0]
    assert json.loads(sent) == saved.preferences


def test_the_page_and_the_server_keep_the_same_keys() -> None:
    """storage.js sends these keys to the server and keeps the rest in the browser."""
    js = (WEB / "storage.js").read_text()
    listed = re.search(r"export const SERVER_KEYS = \[(.*?)\];", js, re.S)
    assert listed is not None
    assert tuple(re.findall(r'"([^"]+)"', listed[1])) == PREFERENCE_KEYS


def test_the_early_script_waits_for_the_servers_word() -> None:
    """theme-start.js uses the browser's old theme only when the server keeps none yet."""
    start = (WEB / "theme-start.js").read_text()
    assert 'getElementById("solum-prefs")?.textContent === "null"' in start
