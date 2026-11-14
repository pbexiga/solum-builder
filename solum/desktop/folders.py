"""Where the Mac app keeps things, and the environment its server runs with (D-321, D-323).

Nothing here needs macOS: the paths are worked out from a home folder, and the checks that
ask the system (is this volume local?) take the answer as an argument.
"""

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Solum Builder"
BUNDLE_ID = "com.solumfx.solum-builder"  # the app's id to macOS; never change it (D-329)
SETTINGS_FILE = "settings.json"  # the launcher's own; the server's is `solum-settings.json`
CODE_MODELS = ("spice2poly", "analog", "digital", "xtradev", "xtraevt", "table")
# Folders a sync service owns, by where they sit in the home folder: SQLite's locks don't
# hold on files a service uploads and replaces.
_SYNCED_UNDER = ("Library/Mobile Documents", "Library/CloudStorage")
_SYNCED_NAMES = ("dropbox", "onedrive", "google drive", "googledrive", "icloud drive", "box")


@dataclass(frozen=True)
class AppFolders:
    """The app's fixed places in a home folder."""

    support: Path  # the launcher's settings file; the default data folder
    caches: Path  # the default cache folder; ngspice's init file
    logs: Path

    @property
    def home(self) -> Path:
        return self.support.parents[2]  # ~/Library/Application Support/Solum Builder

    @property
    def settings_file(self) -> Path:
        return self.support / SETTINGS_FILE

    @property
    def log_file(self) -> Path:
        return self.logs / "solum.log"

    @property
    def lock_file(self) -> Path:
        return self.caches / "running.lock"


def app_folders(home: Path) -> AppFolders:
    library = home / "Library"
    return AppFolders(
        support=library / "Application Support" / APP_NAME,
        caches=library / "Caches" / APP_NAME,
        logs=library / "Logs" / APP_NAME,
    )


@dataclass(frozen=True)
class Chosen:
    """The two folders the person may move (Settings): where they are now."""

    data_dir: Path
    cache_dir: Path


def load_chosen(folders: AppFolders) -> Chosen:
    """The folders from the launcher's settings file; the defaults for a missing or
    unreadable file, or a missing entry (a damaged file must not stop the app starting).
    A folder in the home folder is kept as `~/…`, so the file still holds on another Mac
    with another user name (Migration Assistant copies it, D-323)."""
    try:
        kept = json.loads(folders.settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = {}
    if not isinstance(kept, dict):
        kept = {}

    def folder(key: str, default: Path) -> Path:
        value = kept.get(key)
        if not isinstance(value, str):
            return default
        if value == "~" or value.startswith("~/"):
            return folders.home / value[2:]
        return Path(value) if Path(value).is_absolute() else default

    return Chosen(folder("data_dir", folders.support), folder("cache_dir", folders.caches))


def save_chosen(folders: AppFolders, chosen: Chosen) -> None:
    """Write the settings file whole (a temporary file, then a rename)."""
    folders.support.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"data_dir": home_relative(chosen.data_dir, folders.home),
                       "cache_dir": home_relative(chosen.cache_dir, folders.home)},
                      indent=2)  # fmt: skip
    fd, temp = tempfile.mkstemp(dir=folders.support, prefix=".settings-")
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(text + "\n")
    os.replace(temp, folders.settings_file)


def home_relative(path: Path, home: Path) -> str:
    """`path` as `~/…` when it is in `home`, else as it is."""
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def is_synced(path: Path, home: Path) -> bool:
    """True if `path` is inside a folder a sync service keeps (iCloud Drive, Dropbox,
    OneDrive, Google Drive, Box), judged by where it is."""
    try:
        inside = path.resolve().relative_to(home.resolve())
    except ValueError:
        return False
    text = inside.as_posix()
    if any(text == under or text.startswith(under + "/") for under in _SYNCED_UNDER):
        return True
    return any(_service_folder(part.lower()) for part in inside.parts)


def _service_folder(name: str) -> bool:
    """A sync service's folder name: the service's, alone or with more after a space,
    dash or bracket ("Dropbox (Personal)", "OneDrive - Work"; not "boxes")."""
    return any(
        name == service or (name.startswith(service) and not name[len(service)].isalnum())
        for service in _SYNCED_NAMES
    )


def folder_problem(
    kind: str, path: Path, now: Chosen, home: Path, is_local: Callable[[Path], bool]
) -> str | None:
    """Why `path` can't be the new data ("data") or cache ("cache") folder, in plain
    English, or None. `is_local` says whether a folder is on a disk of this Mac."""
    current, other = (
        (now.data_dir, now.cache_dir) if kind == "data" else (now.cache_dir, now.data_dir)
    )
    if not path.is_absolute() or not path.is_dir():
        return "Choose a folder that exists."
    target = path.resolve()
    if target == current.resolve():
        return "That is the folder in use now."
    if _within(target, other.resolve()) or _within(other.resolve(), target):
        what = "cache" if kind == "data" else "circuits"
        return f"Choose a folder apart from the {what} folder: one can't be inside the other."
    if not os.access(target, os.W_OK):
        return "Solum Builder can't write in that folder. Choose another, or change who may."
    if kind == "cache":
        if is_synced(target, home):
            return (
                "The cache can't be in a folder that iCloud Drive, Dropbox or another sync "
                "service keeps: its index would be damaged. Choose a folder on this Mac."
            )
        if not is_local(target):
            return (
                "The cache can't be on a network disk: its index needs a disk of this Mac. "
                "Choose a folder on this Mac."
            )
    return None


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def entries(folder: Path) -> list[Path]:
    """What a data folder holds that is the person's: everything but the launcher's own
    settings file and hidden files (`.DS_Store`)."""
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.name != SETTINGS_FILE and not p.name.startswith(".")
    )


def move_data(old: Path, new: Path) -> None:
    """Move the person's files from the old data folder into the new one. Raises
    FileExistsError naming the first file already there, before moving anything."""
    moving = entries(old)
    for item in moving:
        if (new / item.name).exists():
            raise FileExistsError(item.name)
    for item in moving:
        shutil.move(str(item), str(new / item.name))


def spinit_text(models: Path) -> str:
    """ngspice's start-up file for code models in `models`. The paths are in single
    quotes: the only way its `codemodel` command takes a path with a space in it (D-322)."""
    lines = ["* Solum Builder: the ngspice init file, written at each start", "if $?xspice_enabled"]
    lines += [f" codemodel '{models / (name + '.cm')}'" for name in CODE_MODELS]
    return "\n".join([*lines, "end", ""])


def write_spinit(models: Path, scripts: Path) -> None:
    """Write `spinit` in `scripts` for the code models in `models`. A path with a single
    quote in it can't be quoted for ngspice: the file then names a link to the folder,
    made beside it under a name without one."""
    scripts.mkdir(parents=True, exist_ok=True)
    if "'" in str(models):
        link = Path(tempfile.gettempdir()) / f"solum-code-models-{os.getuid()}"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(models, target_is_directory=True)
        models = link
    (scripts / "spinit").write_text(spinit_text(models), encoding="utf-8")


def server_environment(resources: Path, folders: AppFolders, chosen: Chosen) -> dict[str, str]:
    """The environment the app's server (and its render workers) run with: the bundle's
    read-only files in `resources`, the person's two folders, and the flag that lets
    Settings move them (D-310). `resources` holds `library/`, `web/`, `docs/guide/`,
    `ngspice/` (the library and its code models) and `fonts/fonts.conf`."""
    return {
        "DATA_DIR": str(chosen.data_dir),
        "CACHE_DIR": str(chosen.cache_dir),
        "LIBRARY_DIR": str(resources / "library"),
        "WEB_DIR": str(resources / "web"),
        "GUIDE_DIR": str(resources / "docs" / "guide"),
        "NGSPICE_LIBRARY": str(resources / "ngspice" / "lib" / "libngspice.0.dylib"),
        "SPICE_SCRIPTS": str(folders.caches / "ngspice-scripts"),
        "CAN_MOVE_FOLDERS": "1",
        # WeasyPrint opens Pango and the rest by bare name; cffi then asks
        # ctypes.util.find_library, which reads this when called (D-324)
        "DYLD_FALLBACK_LIBRARY_PATH": str(resources),
        "FONTCONFIG_FILE": str(resources / "fonts" / "fonts.conf"),
    }
