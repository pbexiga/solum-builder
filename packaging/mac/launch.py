"""The Mac app's program (D-321): PyInstaller freezes this file."""

import multiprocessing
import os
import sys
import threading
import time


def leave_with_the_app() -> None:
    """In a helper process (a render worker, multiprocessing's resource tracker): end it
    when the app that started it is gone, as after a force quit or a crash. A normal Quit
    stops the workers itself; this is for when the app had no chance to."""
    app = os.getppid()

    def watch() -> None:
        while os.getppid() == app:
            time.sleep(1)
        os._exit(0)

    threading.Thread(target=watch, name="leave-with-the-app", daemon=True).start()


if __name__ == "__main__":
    # The app itself is started with no arguments; its helpers with multiprocessing's.
    if len(sys.argv) > 1:
        leave_with_the_app()
    # then at once: a render worker is this program started again, and must not open a window
    multiprocessing.freeze_support()
    from solum.desktop.window import main

    sys.exit(main())
