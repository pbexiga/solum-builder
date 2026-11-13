"""What Settings changes while the app runs, kept in `DATA_DIR/solum-settings.json` (D-310,
D-311): the largest cache size, which wins over `CACHE_MAX_GB` once set, and the page's
preferences (theme, pane order…), which `web/storage.js` reads and writes through
`/api/settings`. The folders stay the environment's (`solum/config.py`)."""

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from solum.config import Settings, cache_gb

SETTINGS_FILE = "solum-settings.json"
# the page's keys kept here and not in the browser (D-311); storage.js has the same list
PREFERENCE_KEYS = (
    "solum.theme",
    "solum.large",
    "solum.autorun",
    "solum.panes",
    "solum.panes.open",
)
PREFERENCE_BYTES = 4000  # the most one preference may take as JSON: they are a few names each


class SettingsError(ValueError):
    """A setting that can't be kept, in plain English."""


@dataclass(frozen=True)
class Saved:
    """The file's contents. `cache_max_gb` None: never set, the environment's holds.
    `preferences` None: never set, so a browser's own old ones are carried over (D-311)."""

    cache_max_gb: float | None = None
    preferences: dict[str, Any] | None = None


def _read(path: Path) -> Saved:
    """The file as it is; a missing or garbled one is as good as none (it is written
    whole on the next change)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        size = data.get("cache_max_gb")
        prefs = data.get("preferences")
        return Saved(
            cache_max_gb=None if size is None else cache_gb(size, "The largest cache size"),
            preferences={k: v for k, v in prefs.items() if k in PREFERENCE_KEYS}
            if isinstance(prefs, dict)
            else None,
        )
    except (OSError, ValueError, AttributeError):
        return Saved()


def _checked(changes: dict[str, Any]) -> dict[str, Any]:
    for key, value in changes.items():
        if key not in PREFERENCE_KEYS:
            raise SettingsError(f"{key!r} isn't a preference Solum Builder keeps.")
        if len(json.dumps(value)) > PREFERENCE_BYTES:
            raise SettingsError(f"The preference {key!r} is too long to keep.")
    return changes


class SettingsFile:
    """The settings file of one data folder. `load` is cheap enough to call on every use:
    the file is read again only when it has changed, so a change made by the server is
    seen by the render workers' caches too."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / SETTINGS_FILE
        self._lock = threading.Lock()
        self._seen: tuple[tuple[int, int] | None, Saved] | None = None

    def _stamp(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def load(self) -> Saved:
        stamp = self._stamp()
        seen = self._seen
        if seen is None or seen[0] != stamp:
            seen = (stamp, _read(self.path) if stamp else Saved())
            self._seen = seen
        return seen[1]

    def _write(self, saved: Saved) -> Saved:
        data: dict[str, Any] = {}
        if saved.cache_max_gb is not None:
            data["cache_max_gb"] = saved.cache_max_gb
        if saved.preferences is not None:
            data["preferences"] = saved.preferences
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # written beside it and renamed: a reader never sees half a file
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=SETTINGS_FILE, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        Path(name).replace(self.path)
        return saved

    def change(
        self, cache_max_gb: float | None = None, preferences: dict[str, Any] | None = None
    ) -> Saved:
        """Keep a new largest cache size, and/or these preferences over the ones kept (a
        null forgets one; `{}` only marks them as set). SettingsError for a bad value."""
        if cache_max_gb is not None:
            try:
                cache_max_gb = cache_gb(cache_max_gb, "The largest cache size")
            except ValueError as err:
                raise SettingsError(str(err)) from None
        with self._lock:
            now = self.load()
            prefs = now.preferences
            if preferences is not None:
                merged = {**(prefs or {}), **_checked(preferences)}
                prefs = {k: v for k, v in merged.items() if v is not None}
            size = now.cache_max_gb if cache_max_gb is None else cache_max_gb
            return self._write(Saved(cache_max_gb=size, preferences=prefs))


def cache_max_gb(settings: Settings, saved: Saved) -> float:
    """The largest cache size in force: the file's once set, else `CACHE_MAX_GB` (D-310)."""
    return settings.cache_max_gb if saved.cache_max_gb is None else saved.cache_max_gb


_THEME = re.compile(r"[a-z]+")


def with_preferences(html: str, saved: Saved) -> str:
    """A page of ours with what the browser needs before it draws (D-311): the theme on
    `<html>`, so it never flashes in another one, and the preferences as JSON in
    `<script id="solum-prefs">` at the top of `<head>`, where `web/storage.js` reads them
    (`null`: none kept yet, and `web/theme-start.js` uses the browser's old choice)."""
    prefs = saved.preferences
    theme = (prefs or {}).get("solum.theme")
    if isinstance(theme, str) and _THEME.fullmatch(theme):
        html = html.replace("<html", f'<html data-theme="{theme}"', 1)
    sent = json.dumps(prefs).replace("<", "\\u003c")  # never ends the script early
    block = f'<head><script id="solum-prefs" type="application/json">{sent}</script>'
    return html.replace("<head>", block, 1)
