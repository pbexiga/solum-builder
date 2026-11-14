"""The app on a free local port for as long as a block of code needs it: the UI tests'
server and the draw-circuit skill's look at a drawing (D-314)."""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn

from solum.api.app import create_app
from solum.config import Settings

START_SECONDS = 15.0


@contextmanager
def serving(settings: Settings) -> Iterator[str]:
    """Run the app with `settings` on 127.0.0.1 and give its address
    (`http://127.0.0.1:<port>/`); it stops when the block ends."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + START_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The app didn't start. Run `solum serve` to see why.")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
