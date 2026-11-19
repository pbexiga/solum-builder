"""The user guide's screenshots (docs/guide/img/), made by driving the real app.

Usage (in the dev container, from the repo's top folder):

    make run CMD="python scripts/guide_shots.py"          # every picture
    make run CMD="python scripts/guide_shots.py sweep"    # only the ones named

Each picture is one function below, named as its file. The app runs in-process on a free
port with a temporary data folder, as the UI tests do (real ngspice, empty cache), in a
1600 x 1000 Chromium window. Run it again whenever the screens change, and look at what
changed before committing the pictures.
"""

import json
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, Page, Route, sync_playwright

from solum.api.serving import serving
from solum.circuit.draw import Drawing
from solum.circuit.io import circuit_to_dict
from solum.config import load_settings
from solum.settings_file import SETTINGS_FILE
from tests.ui.conftest import click_part, open_circuit, part_pos, updates, wait_for_update
from tests.ui.test_audio import plucks, render_and_wait, upload
from tests.ui.test_editor import click_at, delete_part, menu, save_as, views, wait_for_view

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "guide" / "img"
SIZE = {"width": 1600, "height": 1000}


@contextmanager
def server() -> Iterator[tuple[str, Path]]:
    """The app's address, and its data folder."""
    tmp = Path(tempfile.mkdtemp(prefix="guide-shots-"))
    settings = load_settings(
        {
            "CACHE_DIR": str(tmp / "cache"),
            "DATA_DIR": str(tmp / "data"),
            "WEB_DIR": str(REPO / "web"),
            "LIBRARY_DIR": str(REPO / "library"),
        }
    )
    with serving(settings) as base:
        yield base, settings.data_dir


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


def frequency_pin(page: Page, base: str) -> None:
    """The Frequency pane with q1e (the clipping stage's input) pinned, C3 selected, and
    zoomed to 100 Hz - 5 kHz (D-366)."""
    opened(page, base, probe=None)
    panes_on_top(page, "frequency")
    box = page.locator('#schematic .net-label[data-net="q1e"]').first.bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, button="right")
    before = updates(page)
    page.locator("#ctx-pin").click()
    wait_for_update(page, before, 120_000)
    click_part(page, "C3")
    plot = "document.getElementById('frequency-plot')._plot"
    over = page.locator("#frequency-plot .u-over").bounding_box()
    assert over is not None
    x0, x1 = page.evaluate(f"[{plot}.valToPos(100, 'x'), {plot}.valToPos(5000, 'x')]")
    y = over["y"] + over["height"] / 2
    page.mouse.move(over["x"] + x0, y)
    page.mouse.down()
    page.mouse.move(over["x"] + x1, y, steps=8)
    page.mouse.up()
    page.mouse.move(5, 990)  # off the plot: no hover box over the lines
    shoot(page, "frequency-pin", "#panel-frequency")


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


def battery_buffer(
    dc: bool = False, electrolytic: bool = False, own_jack: bool = False
) -> dict[str, object]:
    """A JFET buffer on a battery: J1 (TRS) plugged into IN, its ring switching the
    battery, and J2 plugged into OUT (D-353 to D-355). Net-checked when it was drawn.
    `dc`: a DC jack in the battery's place and J1 TS; `electrolytic`: C2 a 10µ
    electrolytic with no rating; `own_jack`: no J1, IN's own jack TRS with the
    battery's − on its ring (D-364)."""
    d = Drawing()
    d.part("IN", "guitar", (0, 0), volume="250k", trs=own_jack)
    if not own_jack:
        d.part("J1", "jack", (-100, 0) if dc else (-100, -20), trs=not dc, label="Input")
        d.wire("J1.T", (0, 0))  # J1's T plugs into IN's middle
    d.part("C1", "capacitor", (80, 0), value="100n", kind="film")
    d.part("R1", "resistor", (140, 40), 90, value="1M")
    d.part("Q1", "jfet", (200, 0), model="J201")
    d.part("R2", "resistor", (220, 80), 90, value="10k")
    if electrolytic:
        d.part("C2", "capacitor", (280, 20), value="10µ", kind="electrolytic")
    else:
        d.part("C2", "capacitor", (280, 20), value="1µ", kind="film")
    d.part("R3", "resistor", (340, 60), 90, value="1M")
    d.part("OUT", "amp", (420, 20))
    d.part("J2", "jack", (490, 20), 180, label="Output")
    d.wire("IN.out", "C1.1")
    d.wire("C1.2", "Q1.G")
    d.wire((140, 0), "R1.1")
    d.wire("Q1.S", (220, 40), "R2.1")
    d.wire((220, 20), "C2.1")
    d.wire("C2.2", "OUT.in")
    d.wire((340, 20), "R3.1")
    d.wire("J2.T", (430, 20))  # J2's T plugs into OUT's end
    if dc:
        d.part("DC", "dcjack", (-80, -160))  # clear of J1's ground
        d.stub("DC.+", "V+", dx=40)
        d.label("V+", "Q1.D")
        d.stub("DC.-", "GND", dx=80)
    elif own_jack:
        d.part("BAT1", "battery", (-120, 60))  # its − level with the bend under IN's ring
        d.label("V+", "BAT1.+", "Q1.D")
        d.wire("IN.ring", (0, 80), "BAT1.-")
    else:
        d.part("BAT1", "battery", (-20, -100))  # right of J1: its - drops onto R
        d.label("V+", "BAT1.+", "Q1.D")
        d.wire("BAT1.-", (-20, -20), "J1.R")
    d.label("GND", "R1.2", "R2.2", "R3.2")
    if not own_jack:
        d.stub("J1.S", "GND", dy=-40, rot=180)
    d.stub("J2.S", "GND", dy=20)
    power = {"power": {"rails": {"V+": 9.0}}} if dc else {}
    return circuit_to_dict(d.circuit("Battery buffer", probes={"in": "in", "out": "out"}, **power))


def opened_drawn(page: Page, base: str, circuit: dict[str, object], name: str) -> None:
    """A circuit drawn here, saved as `name` and open."""
    page.goto(base)
    saved = page.request.post(f"{base}api/circuits", data={"circuit": circuit, "name": name})
    open_circuit(page, base, "circuit/" + saved.json()["circuit"]["id"])


def panes_on_top(page: Page, *panes: str) -> None:
    """These panes at the top of the Results column, the first on top, as dragging their
    title bars would."""
    page.evaluate(
        """(ids) => { const a = document.querySelector("aside.panels");
        for (const id of ids) {
          const el = document.getElementById(`panel-${id}`);
          el.open = true; a.prepend(el); }
        a.prepend(document.getElementById("error"));
        a.scrollTop = 0; }""",
        list(reversed(panes)),
    )


def jacks(page: Page, base: str) -> None:
    """A battery buffer with its input cable pulled: the jacks plugged into IN and OUT, the
    Input cable switch in Knobs, and the Frequency pane saying why there's no curve."""
    opened_drawn(page, base, battery_buffer(), "Battery buffer")
    panes_on_top(page, "knobs", "frequency")
    before = updates(page)
    page.locator('#knobs-body [data-knob="J1"] [data-position="2"]').click()  # Cable out
    wait_for_update(page, before, 120_000)
    page.mouse.click(5, 990)  # nothing selected
    shoot(page, "jacks")


def in_jack(page: Page, base: str) -> None:
    """The battery buffer with no J1: IN's own TRS jack switches the battery (D-364),
    its Guitar cable switch in Knobs at TRS cable, so the battery is cut off."""
    opened_drawn(page, base, battery_buffer(own_jack=True), "Buffer on IN's jack")
    panes_on_top(page, "knobs", "frequency")
    before = updates(page)
    page.locator('#knobs-body [data-knob="IN.plug"] [data-position="1"]').click()  # TRS cable
    wait_for_update(page, before, 120_000)
    page.mouse.click(5, 990)  # nothing selected
    shoot(page, "in-jack")


def dc_jack_power(page: Page, base: str) -> None:
    """The buffer on a DC jack alone, unplugged (D-359): its Power switch in Knobs, the
    chip *DC jack · unplugged* and the no-power banner."""
    opened_drawn(page, base, battery_buffer(dc=True), "DC buffer")
    panes_on_top(page, "knobs", "dc")
    before = updates(page)
    page.locator('#knobs-body [data-knob="DC"] [data-position="1"]').click()  # Unplugged
    wait_for_update(page, before, 120_000)
    page.mouse.click(5, 990)  # nothing selected
    shoot(page, "dc-jack-power")


def no_power(page: Page, base: str) -> None:
    """A clean boost (a TL061 on a battery switched by J1) with the cable out (D-359): the
    banner, and DC voltages and Probe saying why there are no readings."""
    page.goto(base)
    fixture = REPO / "tests" / "fixtures" / "circuits" / "boost-battery-jack.json"
    opened_drawn(page, base, json.loads(fixture.read_text()), "Clean boost")
    panes_on_top(page, "knobs", "dc", "probe")
    before = updates(page)
    page.locator('#knobs-body [data-knob="J1"] [data-position="2"]').click()  # Cable out
    wait_for_update(page, before, 120_000)
    before = updates(page)
    page.locator("#error").click()  # selects J1
    wait_for_update(page, before, 120_000)
    shoot(page, "no-power", "aside.panels")


def ratings(page: Page, base: str) -> None:
    """Before you build's *Electrolytic with no voltage rating*, opened on its *Use
    suggested ratings* button (D-360)."""
    opened_drawn(page, base, battery_buffer(electrolytic=True), "Buffer to build")
    build = page.locator("#problems-build")
    build.locator("> summary").click()
    build.locator("details.problem[data-rule='cap-no-rating'] > summary").click()
    page.mouse.click(5, 990)
    shoot(page, "ratings", "#panel-problems")


def final_check(page: Page, base: str) -> None:
    """Properties → Mark as final on the buffer with C2 an electrolytic with no rating:
    the check before final lists it (D-362)."""
    opened_drawn(page, base, battery_buffer(electrolytic=True), "Buffer to finish")
    menu(page, "file-menu", "menu-properties")
    page.locator("#toggle-final").click()
    page.wait_for_selector("#final-check .export-row")
    shoot(page, "final-check", "#final-check")


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
    """Four circuits of the user's own: the ones the pictures before saved are deleted."""
    for entry in page.request.get(f"{base}api/circuits").json():
        page.request.delete(f"{base}api/circuits/{entry['id']}")
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


def import_dialog(page: Page, base: str) -> None:
    """File → Import… with a friend's circuit file chosen: its name filled in."""
    opened(page, base, probe=None)
    circuit = json.loads((REPO / "library" / "starters" / "fuzz-face.json").read_text())
    shared = Path(tempfile.mkdtemp()) / "fuzz-from-sam.json"
    shared.write_text(json.dumps({**circuit, "name": "Fuzz from Sam", "starter": False}))
    menu(page, "file-menu", "menu-import")
    page.locator("#import-file").set_input_files(str(shared))
    page.wait_for_function("document.querySelector('#field-name').value !== ''")
    shoot(page, "import-dialog", "form.popup")


def export(page: Page, base: str) -> None:
    opened(page, base, probe=None)
    menu(page, "file-menu", "menu-export")
    page.wait_for_selector("#export .export-clear, #export .export-list", timeout=60_000)
    shoot(page, "export", "#export")


def settings(page: Page, base: str) -> None:
    """File → Settings… as Docker shows it: the folders are the container's (the script's
    own are temporary ones, which nobody would see)."""
    opened(page, base, probe=None)

    def as_docker(route: Route) -> None:
        answer = route.fetch()
        shown = {**answer.json(), "data_dir": "/data", "cache_dir": "/cache",
                 "host_data_dir": "./data", "host_cache_dir": "./cache"}  # fmt: skip
        route.fulfill(response=answer, json=shown)

    page.route("**/api/settings", as_docker)
    menu(page, "file-menu", "menu-settings")
    page.wait_for_selector("#settings .theme-option")
    shoot(page, "settings", "#settings")
    page.unroute("**/api/settings")


def settings_mac(page: Page, base: str) -> None:
    """Settings in the Mac app: its default folders, with Change… and Show in Finder. The
    launcher's functions (`window.pywebview.api`, web/desktop.js) are stand-ins here."""
    page.add_init_script("window.pywebview = {api: {set_unsaved: async () => {}}};")
    opened(page, base, probe=None)
    home = "/Users/you/Library"

    def as_mac(route: Route) -> None:
        answer = route.fetch()
        shown = {**answer.json(), "can_move_folders": True,
                 "data_dir": f"{home}/Application Support/Solum Builder",
                 "cache_dir": f"{home}/Caches/Solum Builder",
                 "host_data_dir": None, "host_cache_dir": None}  # fmt: skip
        route.fulfill(response=answer, json=shown)

    page.route("**/api/settings", as_mac)
    menu(page, "file-menu", "menu-settings")
    page.wait_for_selector("#settings .theme-option")
    shoot(page, "settings-mac", "#settings")
    page.unroute("**/api/settings")


def calculators(page: Page, base: str) -> None:
    """Tools → Calculators…, the filter: the user's 1 µF into 100 kΩ, compared with 10 µF."""
    opened(page, base, probe=None)
    menu(page, "tools-menu", "menu-calculators")
    page.locator("#calc-pick").select_option("filter")
    page.locator("#filter-r").fill("100k")
    page.locator("#filter-c").fill("1u")
    page.locator("#filter-c2").fill("10u")
    page.wait_for_selector("#filter-change")
    shoot(page, "calculators", "#calculators")


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
    "frequency-pin": frequency_pin,
    "edit-curve": edit_curve,
    "sweep": sweep,
    "bias-headroom": bias_headroom,
    "problems": problems,
    "jacks": jacks,
    "in-jack": in_jack,
    "dc-jack-power": dc_jack_power,
    "no-power": no_power,
    "ratings": ratings,
    "final-check": final_check,
    "blocks-dialog": blocks_dialog,
    "open-dialog": open_dialog,
    "import-dialog": import_dialog,
    "export": export,
    "settings": settings,
    "settings-mac": settings_mac,
    "calculators": calculators,
    "audio-large": audio_large,
    "readme": readme,
    "readme-logo": readme_logo,
}


def main(names: list[str]) -> None:
    unknown = set(names) - set(SHOTS)
    if unknown:
        sys.exit(f"No such picture: {', '.join(sorted(unknown))}. Pictures: {', '.join(SHOTS)}")
    OUT.mkdir(parents=True, exist_ok=True)
    with server() as (base, data), sync_playwright() as p:
        browser: Browser = p.chromium.launch()
        for name in names or SHOTS:
            # each picture starts as a first visit: a fresh page, and no preferences kept
            # by the server (D-311) from the one before (a pane left expanded)
            (data / SETTINGS_FILE).unlink(missing_ok=True)
            page = browser.new_page(viewport=SIZE)
            page.on("pageerror", lambda e: print("page error:", e))
            SHOTS[name](page, base)
            page.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
