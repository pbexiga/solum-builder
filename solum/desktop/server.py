"""The Mac app's server: the same FastAPI app, on this machine only, in a thread (D-321)."""

import socket
import threading
import time
import urllib.request
from typing import Any

HOST = "127.0.0.1"  # never 0.0.0.0: nothing on the network reaches the app


def free_port() -> int:
    """A port nothing is listening on (the system picks one)."""
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def wait_for_health(port: int, seconds: float = 30.0) -> bool:
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
    render workers. The settings are read from the environment when it starts, so a
    second `start` after `stop` serves the folders the environment names then."""

    def __init__(self) -> None:
        self.port = 0
        self._server: Any = None
        self._app: Any = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    def start(self, seconds: float = 30.0) -> bool:
        """Start serving; True once the app answers, False if it didn't in `seconds`."""
        import uvicorn

        from solum.api.app import create_app

        self.port = free_port()
        self._app = create_app()
        config = uvicorn.Config(self._app, host=HOST, port=self.port, log_config=None)
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
