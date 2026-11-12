"""UI test fixtures: the real app on a free port (real ngspice, temporary cache) and a
headless Chromium page (`UI_BROWSER=firefox` for Firefox, which isn't in the
image). Runs with `make accept`."""

import itertools
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, expect, sync_playwright

from solum.api.app import create_app
from solum.config import load_settings

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    tmp = tmp_path_factory.mktemp("ui")
    settings = load_settings(
        {
            "CACHE_DIR": str(tmp / "cache"),
            "DATA_DIR": str(tmp / "data"),
            "WEB_DIR": str(REPO / "web"),
            "LIBRARY_DIR": str(REPO / "library"),
        }
    )
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The test server didn't start.")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = getattr(p, os.environ.get("UI_BROWSER", "chromium")).launch()
        yield b
        b.close()


@pytest.fixture
def browser_errors() -> list[str]:
    """Errors the page logged; a test that expects one clears this list."""
    return []


@pytest.fixture
def page(browser: Browser, browser_errors: list[str]) -> Iterator[Page]:
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.on("pageerror", lambda e: browser_errors.append(str(e)))
    page.on("console", lambda m: browser_errors.append(m.text) if m.type == "error" else None)
    yield page
    page.close()
    assert browser_errors == [], f"Browser errors: {browser_errors}"


@pytest.fixture
def half_drawn(page: Page, browser_errors: list[str]) -> Iterator[list[str]]:
    """For tests that draw step by step: a half-drawn circuit can't be simulated, so its
    runs are refused (422, "Can't simulate yet: ...") and the browser logs each one.
    Collects the refusals' messages; at the end checks they are only that, and drops the
    logged 422s."""
    refused: list[str] = []
    page.on("response", lambda r: refused.append(r.json()["message"]) if r.status == 422 else None)
    yield refused
    assert all(m.startswith("Can't simulate yet:") for m in refused), set(refused)
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]


def updates(page: Page) -> int:
    return int(page.evaluate("Number(document.body.dataset.updates || 0)"))


def wait_for_update(page: Page, after: int, timeout: float = 15_000) -> None:
    """Wait until the app has finished a run newer than `after`, and the Bias & headroom
    pane its measuring (it fills in after the run, D-106, which moves the panes below)."""
    page.wait_for_function(
        f"Number(document.body.dataset.updates || 0) > {after}"
        " && document.body.dataset.busy === 'false'"
        " && !document.getElementById('stages-body')?.dataset.loading",
        timeout=timeout,
    )


def open_circuit(
    page: Page, base_url: str, circuit_id: str = "ts808", timeout: float = 15_000
) -> None:
    page.goto(f"{base_url}#{circuit_id}")
    wait_for_update(page, 0, timeout)


_saves = itertools.count(1)


def open_fixture(page: Page, base_url: str, name: str) -> None:
    """Save `tests/fixtures/circuits/<name>.json` as a new circuit and open it."""
    page.goto(base_url)
    circuit = json.loads((REPO / "tests" / "fixtures" / "circuits" / f"{name}.json").read_text())
    made = {"circuit": circuit, "name": f"{name} {next(_saves)}"}  # a name is saved once
    saved = page.request.post(f"{base_url}api/circuits", data=made)
    open_circuit(page, base_url, "circuit/" + saved.json()["circuit"]["id"])


def to_screen(page: Page, x: float, y: float) -> tuple[float, float]:
    """Page pixels for a schematic point (through the SVG's current pan and zoom)."""
    sx, sy = page.evaluate(
        """([x, y]) => {
          const svg = document.getElementById('schematic');
          const p = new DOMPoint(x, y).matrixTransform(svg.getScreenCTM());
          return [p.x, p.y];
        }""",
        [x, y],
    )
    return float(sx), float(sy)


def part_pos(page: Page, ref: str) -> tuple[float, float]:
    """A part's position (its symbol's centre) in schematic units."""
    transform = page.locator(f'g.part[data-ref="{ref}"]').get_attribute("transform") or ""
    x, y = transform.split("(", 1)[1].split(")", 1)[0].split()
    return float(x), float(y)


def click_part(page: Page, ref: str) -> None:
    """Click a part's body (not a pin) and wait for its view."""
    before = updates(page)
    page.mouse.click(*to_screen(page, *part_pos(page, ref)))
    wait_for_update(page, before)


@pytest.fixture
def js(page: Page, base_url: str) -> Page:
    """The app page, for importing its DOM-free modules."""
    page.goto(base_url)
    return page


def run(page: Page, body: str, arg: Any = None) -> Any:
    """Evaluate an async function body with `m(name)` importing a web module."""
    return page.evaluate(
        f"async (arg) => {{ const m = (name) => import('/' + name); {body} }}", arg
    )


def info_text(page: Page, pane: str) -> str:
    """Open a pane's ⓘ (D-109), read its pop-up and close it again (Esc)."""
    page.locator(f"#{pane} > summary .info-button").click()
    pop = page.locator(".info-pop:not([hidden])")
    expect(pop).to_have_count(1)
    text = pop.inner_text()
    page.keyboard.press("Escape")
    expect(pop).to_have_count(0)
    return text
