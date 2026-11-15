"""Smoke test of the built Mac app (D-326): start it with an empty home folder, and through
its own server run starters, export the PDFs and render a clip through an amp capture;
check it loads no library from outside itself, then quit it and check nothing is left.

Usage: python scripts/mac_smoke.py "dist/Solum Builder.app" [a folder outside the bundle
whose libraries it must not load ...]
"""

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from smoke import Client, check_server

from solum.audio.wav import Audio, write_wav

REPO = Path(__file__).resolve().parents[1]


def wait_for_port(log: Path, process: "subprocess.Popen[bytes]", seconds: float = 60) -> int:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert process.poll() is None, f"The app stopped at once (exit {process.returncode})."
        if log.exists() and (found := re.search(r"Server up on port (\d+)", log.read_text())):
            return int(found[1])
        time.sleep(0.2)
    raise AssertionError(f"The app's server didn't start in {seconds:g} s; see {log}")


def copies_running(app: Path) -> list[str]:
    # -i: the same folder may be spelt in another case than the processes were started by
    out = subprocess.run(["/usr/bin/pgrep", "-if", str(app / "Contents" / "MacOS")],
                         capture_output=True, text=True, check=False)  # fmt: skip
    return out.stdout.split()


def loaded_from(pid: int, outside: list[str]) -> list[str]:
    """The libraries the app has loaded from Homebrew or the folders in `outside`."""
    maps = subprocess.run(["/usr/bin/vmmap", str(pid)], capture_output=True, text=True, check=False)
    paths = {line.split()[-1] for line in maps.stdout.splitlines() if "/" in line}
    return sorted(p for p in paths if p.startswith(("/opt/homebrew", "/usr/local", *outside)))


def drive(client: Client, home: Path) -> None:
    circuits = check_server(client)  # what the Docker image is checked for too (D-346)
    settings = client.json("GET", "/api/settings")
    assert settings["can_move_folders"] is True
    assert settings["data_dir"].startswith(str(home)), settings["data_dir"]
    t = np.arange(44100) / 44100
    clip = write_wav(Audio(44100, 0.5 * np.sin(2 * np.pi * 196 * t)))
    capture = (REPO / "tests" / "fixtures" / "nam" / "standard-random.nam").read_bytes()
    riff = client.json("POST", "/api/audio/clips", raw=clip, params={"name": "smoke.wav"})
    amp = client.json("POST", "/api/audio/captures", raw=capture, params={"name": "smoke.nam"})
    job = client.json("POST", "/api/render", body={
        "circuit": circuits["ts808"], "clip": {"id": riff["id"], "layer": "user"},
        "capture": {"id": amp["id"], "layer": "user"}})  # fmt: skip
    deadline = time.monotonic() + 120
    while job["state"] in ("queued", "running"):
        assert time.monotonic() < deadline, "The render didn't finish in 2 minutes."
        time.sleep(0.2)
        job = client.json("GET", f"/api/render/{job['id']}")
    assert job["state"] == "done", job
    status, wav = client.call("GET", f"/api/render/audio/{job['key']}.wav")
    assert status == 200 and wav[:4] == b"RIFF"
    print("  rendered a clip through a capture (a worker process)")


def start_long_render(client: Client) -> None:
    """Start an 8 s render and return once a worker is busy with it."""
    circuit = client.json("GET", "/api/starters/ts808")["circuit"]
    t = np.arange(8 * 44100) / 44100
    clip = write_wav(Audio(44100, 0.5 * np.sin(2 * np.pi * 147 * t)))
    riff = client.json("POST", "/api/audio/clips", raw=clip, params={"name": "long.wav"})
    job = client.json("POST", "/api/render", body={
        "circuit": circuit, "clip": {"id": riff["id"], "layer": "user"}})  # fmt: skip
    deadline = time.monotonic() + 30
    while job["state"] == "queued" or (job["state"] == "running" and job["progress"] == 0):
        assert time.monotonic() < deadline, "The long render didn't start."
        time.sleep(0.1)
        job = client.json("GET", f"/api/render/{job['id']}")
    assert job["state"] == "running", job


def gone_within(app: Path, seconds: float) -> list[str]:
    """The app's processes still there after waiting up to `seconds` for them to end."""
    deadline = time.monotonic() + seconds
    while (left := copies_running(app)) and time.monotonic() < deadline:
        time.sleep(0.2)
    return left


def launch(app: Path, home: Path) -> "tuple[subprocess.Popen[bytes], Client, float]":
    log = home / "Library" / "Logs" / "Solum Builder" / "solum.log"
    log.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("DYLD_")}
    env["HOME"] = str(home)
    started = time.monotonic()
    program = str(app / "Contents" / "MacOS" / "Solum Builder")
    quiet = subprocess.DEVNULL  # or a worker left behind would hold this script's output open
    process = subprocess.Popen([program], env=env, stdout=quiet, stderr=quiet)
    port = wait_for_port(log, process)
    return process, Client(f"http://127.0.0.1:{port}"), time.monotonic() - started


def log_errors(home: Path) -> list[str]:
    lines = (home / "Library" / "Logs" / "Solum Builder" / "solum.log").read_text().splitlines()
    return [ln for ln in lines if " ERROR " in ln or " CRITICAL " in ln]


def main(app: Path, outside: list[str]) -> int:
    import AppKit

    assert not copies_running(app), "Quit the copy of this app that is running first."
    with tempfile.TemporaryDirectory(prefix="solum-smoke-") as tmp:
        home = Path(tmp).resolve()
        process, client, took = launch(app, home)
        try:
            print(f"  server up {took:.1f} s after launch")
            drive(client, home)
            foreign = loaded_from(process.pid, outside)
            assert not foreign, f"Loaded from outside the app: {foreign}"
            start_long_render(client)
            running = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
                process.pid
            )
            assert running is not None and running.terminate(), "The app didn't take Quit."
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
        left = gone_within(app, 3)
        assert not left, f"Processes left after Quit during a render: {left}"
        errors = log_errors(home)
        assert not errors, "The log has errors:\n" + "\n".join(errors[:10])
        print("  quit during a render: no process left, no errors in the log")

        process, client, _took = launch(app, home)
        try:
            start_long_render(client)
            process.kill()  # a force quit, or a crash: the app gets no chance to stop anything
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
        left = gone_within(app, 5)
        assert not left, f"Processes left after a force quit during a render: {left}"
        print("  force quit during a render: its helpers ended too")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve(), sys.argv[2:]))
