"""The app on a free port of this machine, from a thread: the Mac app's server (D-321), the UI
tests' server and the draw-circuit skill's look at a drawing (D-314). One owner for both."""

import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from solum.config import Settings

HOST = "127.0.0.1"  # never 0.0.0.0: nothing on the network reaches the app
START_SECONDS = 30.0


def free_port() -> int:
    """A port nothing is listening on (the system picks one)."""
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def wait_for_health(port: int, seconds: float = START_SECONDS) -> bool:
    """True once `/api/health` answers; False if it hasn't within `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.05)
    return False


class LocalServer:
    """The app served on a free port of 127.0.0.1 from a thread; `stop` ends it and its
    render workers. With no `settings` they are read from the environment at each `start`,
    so a second `start` after `stop` serves the folders the environment names then."""

    def __init__(self, settings: Settings | None = None, log_level: str = "info") -> None:
        self.port = 0
        self._settings = settings
        self._log_level = log_level
        self._server: Any = None
        self._app: Any = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    def start(self, seconds: float = START_SECONDS) -> bool:
        """Start serving; True once the app answers, False if it didn't in `seconds`."""
        # imported here: the Mac app's second copy only brings the first forward, quickly
        import uvicorn

        from solum.api.app import create_app

        self.port = free_port()
        self._app = create_app(self._settings)
        config = uvicorn.Config(
            self._app, host=HOST, port=self.port, log_config=None, log_level=self._log_level
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="server", daemon=True)
        self._thread.start()
        return wait_for_health(self.port, seconds)

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._app.state.jobs.close()
        self._server = self._app = self._thread = None


@contextmanager
def serving(settings: Settings) -> Iterator[str]:
    """Run the app with `settings` on 127.0.0.1 and give its address
    (`http://127.0.0.1:<port>/`); it stops when the block ends."""
    server = LocalServer(settings, log_level="warning")
    try:
        if not server.start():
            raise RuntimeError("The app didn't start. Run `solum serve` to see why.")
        yield server.url
    finally:
        server.stop()
