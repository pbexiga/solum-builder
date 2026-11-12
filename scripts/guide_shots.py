"""The user guide's screenshots (docs/guide/img/), made by driving the real app.

Usage (in the dev container, from the repo's top folder):

    make run CMD="python scripts/guide_shots.py"          # every picture
    make run CMD="python scripts/guide_shots.py sweep"    # only the ones named

Each picture is one function below, named as its file. The app runs in-process on a free
port with a temporary data folder, as the UI tests do (real ngspice, empty cache), in a
1600 x 1000 Chromium window. Run it again whenever the screens change, and look at what
changed before committing the pictures.
"""

import socket
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from solum.api.app import create_app
from solum.config import load_settings
from tests.ui.conftest import click_part, part_pos, updates, wait_for_update
from tests.ui.test_audio import plucks, render_and_wait, upload
from tests.ui.test_editor import click_at, delete_part, menu, save_as, views, wait_for_view

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "guide" / "img"
SIZE = {"width": 1600, "height": 1000}


@contextmanager
def server() -> Iterator[str]:
    tmp = Path(tempfile.mkdtemp(prefix="guide-shots-"))
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
    srv = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    srv.should_exit = True


def shoot(page: Page, name: str, selector: str | None = None) -> None:
    """The window, or one element of it, as docs/guide/img/<name>.png."""
    page.wait_for_timeout(400)  # let a redraw finish
    target = page.locator(selector).first if selector else page
    target.screenshot(path=str(OUT / f"{name}.png"))
    print("wrote", name)


def opened(page: Page, base: str, circuit: str = "ts808", probe: str | None = "IC1A") -> None:
    """A starter open and run, with a part probed."""
    page.goto(f"{base}#{circuit}")
    wait_for_update(page, 0, 120_000)
    if probe:
        click_part(page, probe)


def run_now(page: Page) -> None:
    before = updates(page)
    page.locator("#run").click()
    wait_for_update(page, before, 120_000)


def expand(page: Page, pane: str) -> None:
    page.locator(f"#{pane}-expand").click()
    page.wait_for_timeout(800)


# --- one function per picture -------------------------------------------------------


def overview(page: Page, base: str) -> None:
    opened(page, base)
    shoot(page, "overview")


def first_pedal(page: Page, base: str) -> None:
    """first-pedal-wire and first-pedal-run: IN wired to OUT, then the Fetzer Valve block
    spliced into the wire and run."""
    page.goto(base)
    page.wait_for_timeout(800)
    (ix, iy), (ox, _) = part_pos(page, "IN"), part_pos(page, "OUT")
    page.locator('.palette [data-tool="wire"]').click()
    before = views(page)
    click_at(page, ix + 20, iy)  # IN's pin end
    click_at(page, ox - 20, iy)  # OUT's pin end
    wait_for_view(page, before)
    page.keyboard.press("Escape")
    shoot(page, "first-pedal-wire", "section.canvas")
    menu(page, "blocks-menu", "menu-insert-block")
    page.locator("button.insert", has_text="Fetzer Valve").click()
    page.wait_for_selector("svg#schematic.placing")
    before = views(page)
    click_at(page, (ix + ox) / 2, iy)  # on the wire
    wait_for_view(page, before)
    run_now(page)
    page.mouse.click(5, 990)  # nothing selected
    shoot(page, "first-pedal-run")


def probe_net(page: Page, base: str) -> None:
    opened(page, base, probe=None)
    page.locator("#panel-dc > summary").click()
    before = updates(page)
    page.locator("#dc-body tr", has_text="VREF").first.click()
    wait_for_update(page, before)
    shoot(page, "probe-net", "#panel-probe")


def view_overlays(page: Page, base: str) -> None:
    opened(page, base, probe=None)
    for item in ("menu-dc", "menu-impedance", "menu-cap-types"):
        menu(page, "view-menu", item)
        page.wait_for_timeout(1500)
    shoot(page, "view-overlays", "section.canvas")


def frequency_large(page: Page, base: str) -> None:
    """frequency-large, and readme-frequency: the large view alone."""
    opened(page, base)
    expand(page, "frequency")
    page.wait_for_selector("#knob-ranges li, #knob-ranges .knob-range", timeout=60_000)
    shoot(page, "frequency-large")
    shoot(page, "readme-frequency", "#panel-frequency")  # the large view alone, for the top README


def edit_curve(page: Page, base: str) -> None:
    opened(page, base)
    expand(page, "frequency")
    page.locator("#frequency-edit").click()
    page.wait_for_selector("#curve-edit", timeout=60_000)
    page.wait_for_timeout(3000)  # the handles are found after the curve
    shoot(page, "edit-curve")


def sweep(page: Page, base: str) -> None:
    opened(page, base)
    save_as(page, "Sweep")
    click_part(page, "C3")
    page.keyboard.press("Enter")
    page.locator("#sweep-values").fill("22n, 47n, 100n")
    page.locator("form.popup button", has_text="Try").click()
    page.wait_for_selector("#sweep-tools:not([hidden])", timeout=120_000)
    page.locator("#sweep-net").select_option(label="out (output)")
    page.wait_for_timeout(1500)
    page.keyboard.press("Escape")
    shoot(page, "sweep")


def bias_headroom(page: Page, base: str) -> None:
    """bias-headroom (and readme-bias-headroom, the large view alone) and try-changes:
    IC1B's card, then its gain sliders."""
    opened(page, base)
    expand(page, "stages")
    page.locator("#panel-stages .chain-block", has_text="IC1B").first.click()
    page.wait_for_timeout(4000)
    shoot(page, "bias-headroom")
    shoot(page, "readme-bias-headroom", "#panel-stages")  # the large view alone, for the top README
    page.locator("#panel-stages button", has_text="Find parts").first.click()
    page.wait_for_selector(".fix-parts-head", timeout=180_000)
    page.wait_for_timeout(1000)
    page.locator(".fix-parts-head").scroll_into_view_if_needed()
    shoot(page, "try-changes")


def problems(page: Page, base: str) -> None:
    opened(page, base, probe=None)
    save_as(page, "Broken")
    delete_part(page, "R2")
    run_now(page)
    rows = page.locator("#problems-body details.problem")
    for i in range(rows.count()):
        rows.nth(i).locator("summary").click()
    shoot(page, "problems", "#panel-problems")


def blocks_dialog(page: Page, base: str) -> None:
    page.goto(base)
    page.wait_for_timeout(800)
    menu(page, "blocks-menu", "menu-insert-block")
    page.wait_for_timeout(800)
    shoot(page, "blocks-dialog", "form.popup")


def open_dialog(page: Page, base: str) -> None:
    for name, circuit in (
        ("My Screamer", "ts808"),
        ("Rat with LEDs", "proco-rat"),
        ("Bluesbreaker mods", "marshall-bluesbreaker"),
        ("Fuzz on a board", "fuzz-face"),
    ):
        opened(page, base, circuit, probe=None)
        save_as(page, name)
    menu(page, "file-menu", "menu-open")
    page.wait_for_timeout(800)
    shoot(page, "open-dialog", "form.popup")


def export(page: Page, base: str) -> None:
    opened(page, base, probe=None)
    menu(page, "file-menu", "menu-export")
    page.wait_for_selector("#export .export-clear, #export .export-list", timeout=60_000)
    shoot(page, "export", "#export")


def audio_large(page: Page, base: str) -> None:
    """A made-up riff (plucked notes) through the TS808, no amp or cab: the pedal's output.
    Also readme-audio, the large view alone."""
    opened(page, base, probe=None)
    upload(page, "clips", plucks(Path(tempfile.mkdtemp()) / "riff.wav", seconds=4.0))
    render_and_wait(page, timeout=600_000)
    expand(page, "audio")  # the large view shows the spectrum
    page.wait_for_timeout(1500)
    shoot(page, "audio-large")
    shoot(page, "readme-audio", "#panel-audio")  # the large view alone, for the top README


def readme(page: Page, base: str) -> None:
    """The top README's picture: the TS808 run, its output probed, the DC voltages on the
    drawing, and Probe, Frequency and Scope at the top of the panes."""
    opened(page, base, probe=None)
    menu(page, "view-menu", "menu-dc")
    page.locator("#panel-dc > summary").click()
    before = updates(page)
    page.locator("#dc-body tr", has_text="out").first.click()
    wait_for_update(page, before)
    for pane in ("problems", "notes", "dc", "stages"):
        page.locator(f"#panel-{pane}[open] > summary").click()
    page.evaluate(  # Probe, Frequency, Scope at the top, as dragging their title bars would
        """() => { const a = document.querySelector("aside.panels");
        for (const id of ["scope", "frequency", "probe"])
          a.prepend(document.getElementById(`panel-${id}`));
        a.scrollTop = 0; }"""
    )
    page.mouse.click(5, 990)  # nothing selected
    shoot(page, "readme")


def readme_logo(page: Page, base: str) -> None:
    """The top README's logo as a PNG (GitHub's app shows no SVG in a README): the silver logo
    on the Solum theme's ink (--ink), in a rounded square, drawn at twice the size it's shown."""
    page.goto(base)
    page.set_content(
        '<body style="margin:0;background:transparent">'
        '<div id="logo" style="width:360px;height:360px;border-radius:56px;background:#1E1E1B;'
        'display:flex;align-items:center;justify-content:center">'
        f'<img src="{base}assets/brand/solum-logo-outlined.svg" style="width:296px;height:296px">'
        "</div></body>"
    )
    page.wait_for_function("document.querySelector('#logo img').complete")
    page.locator("#logo").screenshot(path=str(OUT / "readme-logo.png"), omit_background=True)
    print("wrote", "readme-logo")


SHOTS: dict[str, Callable[[Page, str], None]] = {
    "overview": overview,
    "first-pedal": first_pedal,
    "probe-net": probe_net,
    "view-overlays": view_overlays,
    "frequency-large": frequency_large,
    "edit-curve": edit_curve,
    "sweep": sweep,
    "bias-headroom": bias_headroom,
    "problems": problems,
    "blocks-dialog": blocks_dialog,
    "open-dialog": open_dialog,
    "export": export,
    "audio-large": audio_large,
    "readme": readme,
    "readme-logo": readme_logo,
}


def main(names: list[str]) -> None:
    unknown = set(names) - set(SHOTS)
    if unknown:
        sys.exit(f"No such picture: {', '.join(sorted(unknown))}. Pictures: {', '.join(SHOTS)}")
    OUT.mkdir(parents=True, exist_ok=True)
    with server() as base, sync_playwright() as p:
        browser: Browser = p.chromium.launch()
        for name in names or SHOTS:
            page = browser.new_page(viewport=SIZE)  # each picture starts from a fresh page
            page.on("pageerror", lambda e: print("page error:", e))
            SHOTS[name](page, base)
            page.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
