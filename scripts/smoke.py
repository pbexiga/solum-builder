"""Smoke test of a running Solum Builder server, as a user meets it: health, the page,
starters run with no error-level problems, and the build package's PDFs. The release run
points it at the Docker image on x86-64 (D-346); `mac_smoke.py` runs the same checks on the
Mac app's own server. Standard library only, so it runs with any Python 3.

Usage: python3 scripts/smoke.py http://127.0.0.1:8000 [expected version]
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# the Rat: the op-amp transients that broke on ARM64 (D-322, D-327); the Fuzz Face: its
# measured transistors' gain fit (D-130)
STARTERS = ("ts808", "proco-rat", "big-muff-pi-v3", "fuzz-face")
PDFS = ("bom.pdf", "bias.pdf", "notes.pdf", "wiring.pdf")


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Any = None, raw: bytes | None = None,
             params: dict[str, str] | None = None) -> tuple[int, bytes]:  # fmt: skip
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(url, data=data, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=300) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def json(self, method: str, path: str, **kw: Any) -> Any:
        status, data = self.call(method, path, **kw)
        assert status == 200, f"{method} {path}: {status} {data[:300]!r}"
        return json.loads(data)


def wait_for_health(client: Client, seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            if client.call("GET", "/api/health")[0] == 200:
                return
        except OSError:
            pass
        assert time.monotonic() < deadline, f"No answer from {client.base} in {seconds:g} s."
        time.sleep(0.5)


def check_server(client: Client, version: str | None = None) -> dict[str, Any]:
    """Every check; gives the starters' circuits by id, for a caller's further checks."""
    health = client.json("GET", "/api/health")
    assert health["engine"] == "native" and health["ngspice"] == "44.2", health
    assert version is None or health["version"] == version, (health["version"], version)
    print(f"  health: Solum Builder {health['version']}, ngspice {health['ngspice']}")
    status, page = client.call("GET", "/")
    assert status == 200 and b"<title>" in page, f"the page: {status} {page[:200]!r}"
    status, script = client.call("GET", "/app.js")
    assert status == 200 and b"import" in script, f"app.js: {status}"
    print("  the page and its scripts are served")
    circuits = {}
    for sid in STARTERS:
        circuits[sid] = client.json("GET", f"/api/starters/{sid}")["circuit"]
        run = client.json("POST", "/api/run", body={"circuit": circuits[sid]})
        assert {"op", "ac", "tran"} <= set(run), sorted(run)
        assert client.json("POST", "/api/stages", body={"circuit": circuits[sid]})["rows"]
        found = client.json("POST", "/api/problems", body={"circuit": circuits[sid]})
        errors = [p["message"] for p in found["problems"] if p["severity"] == "error"]
        assert found["checked_op"] and not errors, (sid, errors)
        print(f"  ran {sid}: DC, frequency, transient, stages, no errors in Problems")
    for name in PDFS:
        status, data = client.call("GET", f"/api/export/starter/ts808/{name}")
        assert status == 200 and data[:5] == b"%PDF-", f"{name}: {status} {data[:200]!r}"
    print(f"  exported {len(PDFS)} PDFs")
    return circuits


def main(base: str, version: str | None) -> int:
    client = Client(base)
    wait_for_health(client)
    check_server(client, version)
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
