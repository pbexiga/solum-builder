"""The Mac app's launcher (D-321 to D-323): the parts that need no Mac."""

import json
import os
from pathlib import Path

import pytest

from solum.config import load_settings
from solum.desktop.folders import (
    CODE_MODELS,
    AppFolders,
    Chosen,
    app_folders,
    entries,
    folder_problem,
    is_synced,
    load_chosen,
    move_data,
    save_chosen,
    server_environment,
    spinit_text,
    write_spinit,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def folders(home: Path) -> AppFolders:
    return app_folders(home)


def local(_path: Path) -> bool:
    return True


def test_the_apps_places_are_the_macs_usual_ones(home: Path, folders: AppFolders) -> None:
    library = home / "Library"
    assert folders.support == library / "Application Support" / "Solum Builder"
    assert folders.caches == library / "Caches" / "Solum Builder"
    assert folders.log_file == library / "Logs" / "Solum Builder" / "solum.log"
    assert folders.settings_file == folders.support / "settings.json"


def test_with_no_settings_file_the_folders_are_the_defaults(folders: AppFolders) -> None:
    assert load_chosen(folders) == Chosen(folders.support, folders.caches)


def test_chosen_folders_are_kept_and_read_back(folders: AppFolders, tmp_path: Path) -> None:
    chosen = Chosen(tmp_path / "My pedals", tmp_path / "cache é")
    save_chosen(folders, chosen)
    assert load_chosen(folders) == chosen
    assert [p.name for p in folders.support.iterdir()] == ["settings.json"]  # no temp file left


def test_folders_in_the_home_folder_follow_it_to_another_mac(home: Path, tmp_path: Path) -> None:
    """Migration Assistant copies the settings file to a Mac where the home folder may have
    another name: folders in it are kept as `~/…` (D-323)."""
    folders = app_folders(home)
    save_chosen(folders, Chosen(home / "Documents" / "Pedals", folders.caches))
    kept = json.loads(folders.settings_file.read_text())
    assert kept == {"data_dir": "~/Documents/Pedals", "cache_dir": "~/Library/Caches/Solum Builder"}
    moved = tmp_path / "Users" / "someone-else"
    (moved / "Library" / "Application Support").mkdir(parents=True)
    folders.support.rename(moved / "Library" / "Application Support" / "Solum Builder")
    there = app_folders(moved)
    assert there.home == moved
    assert load_chosen(there) == Chosen(moved / "Documents" / "Pedals", there.caches)


@pytest.mark.parametrize(
    "text", ["", "not json", "[1, 2]", '{"data_dir": 5}', '{"data_dir": "relative/path"}']
)
def test_a_damaged_settings_file_gives_the_defaults(folders: AppFolders, text: str) -> None:
    folders.support.mkdir(parents=True)
    folders.settings_file.write_text(text)
    assert load_chosen(folders) == Chosen(folders.support, folders.caches)


def test_one_folder_can_be_set_without_the_other(folders: AppFolders, tmp_path: Path) -> None:
    folders.support.mkdir(parents=True)
    folders.settings_file.write_text(json.dumps({"cache_dir": str(tmp_path / "c")}))
    assert load_chosen(folders) == Chosen(folders.support, tmp_path / "c")


@pytest.mark.parametrize(
    ("inside", "synced"),
    [
        ("Library/Mobile Documents/com~apple~CloudDocs/Solum", True),
        ("Library/CloudStorage/OneDrive-Personal/cache", True),
        ("Dropbox/solum", True),
        ("Dropbox (Personal)/solum", True),
        ("Google Drive/My Drive/x", True),
        ("OneDrive - Work/x", True),
        ("Documents/Solum Builder", False),
        ("Library/Caches/Solum Builder", False),
        ("Music/boxes", False),  # "box" must start the folder's name
    ],
)
def test_folders_a_sync_service_keeps_are_known_by_where_they_are(
    home: Path, inside: str, synced: bool
) -> None:
    assert is_synced(home / inside, home) is synced


def test_a_folder_outside_the_home_folder_is_not_synced(home: Path, tmp_path: Path) -> None:
    assert is_synced(tmp_path / "Volumes" / "Dropbox", home) is False


def test_what_is_wrong_with_a_new_folder(home: Path, folders: AppFolders) -> None:
    now = Chosen(folders.support, folders.caches)
    for made in (folders.support, folders.caches, home / "Pedals", home / "Dropbox" / "c"):
        made.mkdir(parents=True)
    assert folder_problem("data", home / "Pedals", now, home, local) is None
    assert folder_problem("cache", home / "Pedals", now, home, local) is None
    assert folder_problem("data", home / "Dropbox" / "c", now, home, local) is None  # data may sync
    assert folder_problem("data", home / "nowhere", now, home, local) == (
        "Choose a folder that exists."
    )
    assert folder_problem("data", Path("relative"), now, home, local) == (
        "Choose a folder that exists."
    )
    assert folder_problem("data", folders.support, now, home, local) == (
        "That is the folder in use now."
    )
    inside = folders.caches / "deeper"
    inside.mkdir()
    assert "apart from the cache folder" in str(folder_problem("data", inside, now, home, local))
    assert "apart from the circuits folder" in str(
        folder_problem("cache", folders.support.parent, now, home, local)
    )
    assert "sync service" in str(folder_problem("cache", home / "Dropbox" / "c", now, home, local))
    assert "network disk" in str(
        folder_problem("cache", home / "Pedals", now, home, lambda _p: False)
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write anywhere")
def test_a_folder_that_cant_be_written_is_refused(home: Path, folders: AppFolders) -> None:
    locked = home / "locked"
    locked.mkdir(parents=True)
    locked.chmod(0o500)
    try:
        now = Chosen(folders.support, folders.caches)
        assert "can't write" in str(folder_problem("data", locked, now, home, local))
    finally:
        locked.chmod(0o700)


def test_moving_takes_the_persons_files_and_leaves_the_launchers(tmp_path: Path) -> None:
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "circuits").mkdir(parents=True)
    (old / "circuits" / "fuzz.json").write_text("{}")
    (old / "solum-settings.json").write_text("{}")
    (old / "settings.json").write_text("{}")  # the launcher's own
    (old / ".DS_Store").write_text("")
    new.mkdir()
    assert [p.name for p in entries(old)] == ["circuits", "solum-settings.json"]
    move_data(old, new)
    assert sorted(p.name for p in new.iterdir()) == ["circuits", "solum-settings.json"]
    assert (new / "circuits" / "fuzz.json").read_text() == "{}"
    assert sorted(p.name for p in old.iterdir()) == [".DS_Store", "settings.json"]
    assert entries(tmp_path / "missing") == []


def test_moving_onto_a_file_already_there_moves_nothing(tmp_path: Path) -> None:
    old, new = tmp_path / "old", tmp_path / "new"
    for folder in (old / "audio", old / "circuits", new / "circuits"):
        folder.mkdir(parents=True)
    with pytest.raises(FileExistsError, match="circuits"):
        move_data(old, new)
    assert sorted(p.name for p in old.iterdir()) == ["audio", "circuits"]


def test_spinit_names_each_code_model_in_single_quotes() -> None:
    text = spinit_text(Path("/Applications/Solum Builder.app/Contents/Frameworks/ngspice"))
    lines = text.splitlines()
    assert lines[1] == "if $?xspice_enabled" and lines[-1] == "end"
    assert lines[2] == (
        " codemodel '/Applications/Solum Builder.app/Contents/Frameworks/ngspice/spice2poly.cm'"
    )
    assert len([ln for ln in lines if ln.startswith(" codemodel '")]) == len(CODE_MODELS)


def test_a_code_model_path_with_a_quote_goes_through_a_link(tmp_path: Path) -> None:
    models = tmp_path / "O'Brien's apps" / "ngspice"
    models.mkdir(parents=True)
    (models / "analog.cm").write_text("x")
    write_spinit(models, tmp_path / "scripts")
    text = (tmp_path / "scripts" / "spinit").read_text()
    named = Path(text.splitlines()[3].split("'")[1])  # analog.cm
    assert text.count("'") == 2 * len(CODE_MODELS)
    assert named.read_text() == "x"
    write_spinit(models, tmp_path / "scripts")  # again: the link is replaced, not an error
    write_spinit(tmp_path, tmp_path / "scripts")  # no quote: named as it is
    assert f"'{tmp_path / 'analog.cm'}'" in (tmp_path / "scripts" / "spinit").read_text()


def test_the_servers_environment_is_what_the_settings_read(
    folders: AppFolders, tmp_path: Path
) -> None:
    root = tmp_path / "Solum Builder.app" / "Contents" / "Frameworks"
    env = server_environment(root, folders, Chosen(tmp_path / "d", tmp_path / "c"))
    settings = load_settings(env)
    assert settings.data_dir == tmp_path / "d" and settings.cache_dir == tmp_path / "c"
    assert settings.library_dir == root / "library" and settings.web_dir == root / "web"
    assert settings.guide_dir == root / "docs" / "guide"
    assert settings.ngspice_library == str(root / "ngspice" / "lib" / "libngspice.0.dylib")
    assert settings.can_move_folders is True
    assert env["SPICE_SCRIPTS"] == str(folders.caches / "ngspice-scripts")
    assert env["DYLD_FALLBACK_LIBRARY_PATH"] == str(root)
    assert env["FONTCONFIG_FILE"] == str(root / "fonts" / "fonts.conf")
