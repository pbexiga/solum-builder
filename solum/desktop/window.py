"""The Mac app's launcher (D-321): one copy at a time, a log, the server on 127.0.0.1, a
native window on it, and what Settings asks of macOS (choosing and moving the folders).

macOS only (pywebview, pyobjc); the parts that aren't are in `folders` and `server`. Run
as the bundle's program, or from source with `SOLUM_RESOURCES` naming a folder laid out as
the bundle's (`make mac-app` makes one).
"""

import fcntl
import logging
import multiprocessing
import os
import subprocess
import sys
import threading
from html import escape
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import IO, Any

from solum.api.serving import LocalServer
from solum.desktop.folders import (
    APP_NAME,
    BUNDLE_ID,
    AppFolders,
    Chosen,
    app_folders,
    entries,
    folder_problem,
    load_chosen,
    move_data,
    save_chosen,
    server_environment,
    write_spinit,
)

log = logging.getLogger("solum.desktop")

NOT_STARTED = """<body style="font: 15px -apple-system; margin: 3em; line-height: 1.5">
<h2>Solum Builder couldn't start</h2>
<p>{why}</p>
<p>The log has the details:<br><code>{log}</code></p>
<p>Quit (Cmd-Q) and open the app again. If it keeps happening, send that file with your
report.</p></body>"""


def resources() -> Path:
    """The bundle's read-only files (see `folders.server_environment`)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(os.environ["SOLUM_RESOURCES"])


def start_logging(folders: AppFolders) -> None:
    """Everything the launcher and the server log goes to the log file, rotated (3 x 1 MB)."""
    folders.logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folders.log_file, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    sys.excepthook = lambda kind, err, trace: log.critical(
        "The launcher stopped", exc_info=(kind, err, trace)
    )


def only_copy(folders: AppFolders) -> IO[str] | None:
    """The lock that says this is the copy running (keep it open), or None if another
    copy holds it."""
    folders.caches.mkdir(parents=True, exist_ok=True)
    lock = folders.lock_file.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


def bring_forward() -> None:
    """Bring the copy already running to the front."""
    import AppKit

    for app in AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(BUNDLE_ID):
        if app.processIdentifier() != os.getpid():
            app.activateWithOptions_(AppKit.NSApplicationActivateAllWindows)


def is_local(path: Path) -> bool:
    """True if `path` is on a disk of this Mac (not a network volume)."""
    import Foundation

    url = Foundation.NSURL.fileURLWithPath_(str(path))
    ok, local, _error = url.getResourceValue_forKey_error_(
        None, Foundation.NSURLVolumeIsLocalKey, None
    )
    return bool(local) if ok else True


class Desktop:
    """What the page asks of the Mac app (`web/desktop.js`), as `window.pywebview.api`.
    Each answer is a dict the page shows; a `problem` is plain English."""

    def __init__(self, folders: AppFolders, server: LocalServer) -> None:
        # underscored: pywebview offers every public attribute to the page
        self._folders = folders
        self._server = server
        self._window: Any = None
        self._busy = threading.Lock()
        self._unsaved = False

    def _now(self) -> Chosen:
        return load_chosen(self._folders)

    def choose_folder(self, kind: str) -> dict[str, Any] | None:
        """The macOS folder picker for the data ("data") or cache ("cache") folder. None if
        cancelled; else the path, a `problem` if it can't be used, and whether the folder
        in use and the one chosen hold files (the page then offers to move them)."""
        import webview

        now = self._now()
        current = now.data_dir if kind == "data" else now.cache_dir
        picked = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(current))
        if not picked:
            return None
        path = Path(picked[0])
        return {
            "path": str(path),
            "problem": folder_problem(kind, path, now, Path.home(), is_local),
            "files_here": bool(entries(current)) if kind == "data" else False,
            "files_there": bool(entries(path)),
        }

    def move_folder(self, kind: str, path: str, move: bool) -> dict[str, Any]:
        """Use `path` as the data or cache folder from now on: with `move`, the files in
        the data folder go with it. The server starts again on it and the page reloads.
        A `problem` instead if it can't be done (nothing has changed then)."""
        with self._busy:
            now = self._now()
            target = Path(path)
            problem = folder_problem(kind, target, now, Path.home(), is_local)
            if problem:
                return {"problem": problem}
            self._server.stop()
            try:
                if kind == "data" and move:
                    move_data(now.data_dir, target)
            except FileExistsError as err:
                problem = (
                    f"That folder already has something called {err}. Nothing was moved. "
                    "Choose an empty folder, or switch without moving the files."
                )
            except OSError as err:
                log.exception("Moving the data folder failed")
                problem = f"The files couldn't all be moved ({err.strerror}). Check both folders."
            if not problem:
                chosen = Chosen(target, now.cache_dir) if kind == "data" else Chosen(
                    now.data_dir, target
                )  # fmt: skip
                save_chosen(self._folders, chosen)
                log.info("The %s folder is now %s", kind, target)
            serve(self._folders, self._server)
            if problem:
                return {"problem": problem}
            self._window.load_url(self._server.url)
            return {"problem": None}

    def set_unsaved(self, unsaved: bool) -> None:
        """The page says whether the open circuit has unsaved changes: closing the window
        or Quit then asks first (a browser asks by itself; this window doesn't)."""
        self._unsaved = bool(unsaved)

    def show_folder(self, kind: str) -> None:
        """Open the data or cache folder in Finder."""
        now = self._now()
        subprocess.run(["/usr/bin/open", str(now.data_dir if kind == "data" else now.cache_dir)],
                       check=False)  # fmt: skip

    def _page_menu(self, item: str) -> None:
        """Open one of the page's own dialogs from the Mac menu bar."""
        self._window.evaluate_js(
            f"window.dispatchEvent(new CustomEvent('solum-desktop', {{detail: '{item}'}}))"
        )


def serve(folders: AppFolders, server: LocalServer) -> bool:
    """Start the server on the folders the settings file names now."""
    chosen = load_chosen(folders)
    chosen.data_dir.mkdir(parents=True, exist_ok=True)
    chosen.cache_dir.mkdir(parents=True, exist_ok=True)
    root = resources()
    os.environ.update(server_environment(root, folders, chosen))
    write_spinit(root / "ngspice" / "lib" / "ngspice", folders.caches / "ngspice-scripts")
    started = server.start()
    log.info("Server %s on port %s", "up" if started else "did not start", server.port)
    return started


def quit_anyway() -> bool:
    """Ask before unsaved changes are lost; True to go on closing."""
    import AppKit

    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_("This circuit has unsaved changes.")
    alert.setInformativeText_("If you quit now, they are lost.")
    alert.addButtonWithTitle_("Cancel")
    alert.addButtonWithTitle_("Quit Anyway")
    return bool(alert.runModal() == AppKit.NSAlertSecondButtonReturn)


def settings_shortcut() -> None:
    """Cmd-, for the app menu's Settings… (pywebview's menu items take no shortcut)."""
    import AppKit
    from PyObjCTools import AppHelper

    def add() -> None:
        menu = AppKit.NSApp.mainMenu().itemAtIndex_(0).submenu()
        item = menu.itemWithTitle_("Settings…")
        if item is not None:
            item.setKeyEquivalent_(",")

    AppHelper.callAfter(add)


def main() -> int:
    import webview
    from webview.menu import Menu, MenuAction

    folders = app_folders(Path.home())
    start_logging(folders)
    lock = only_copy(folders)
    if lock is None:
        bring_forward()
        return 0
    server = LocalServer()
    desktop = Desktop(folders, server)
    try:
        started = serve(folders, server)
        why = "Its server didn't answer in time."
    except Exception as err:
        log.exception("The server couldn't be started")
        started, why = False, str(err)

    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    if started:
        desktop._window = webview.create_window(
            APP_NAME, server.url, js_api=desktop, width=1440, height=900, min_size=(900, 600)
        )
        menu = [Menu("__app__", [MenuAction("Settings…", lambda: desktop._page_menu("settings"))])]

        def closing() -> bool:
            """The window's close button or Quit. Quit never comes back from the window's
            loop, so the server and its render workers are stopped here, not after it."""
            if desktop._unsaved and not quit_anyway():
                return False
            server.stop()
            return True

        desktop._window.events.closing += closing
    else:
        page = NOT_STARTED.format(why=escape(why), log=escape(str(folders.log_file)))
        webview.create_window(APP_NAME, html=page, width=640, height=360)
        menu = []
    # private: with a new port at each launch the page's own storage would only pile up;
    # what must be kept is the server's (D-311)
    webview.start(settings_shortcut if started else None, private_mode=True, menu=menu)
    server.stop()
    lock.close()
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()  # a render worker is this program started again (D-083)
    sys.exit(main())
