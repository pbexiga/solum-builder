"""The read-only viewer in a real browser: brand, schematic, probing, knobs, snapshots.

`test_drive_hardens_the_clipping` and `test_tone_updates_the_curve_quickly` are the viewer's
acceptance criteria, checked here on the dev box; the NAS timing is checked by hand
(`solum bench`, D-044).
"""

import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import (
    REPO,
    click_part,
    info_text,
    open_circuit,
    open_fixture,
    updates,
    wait_for_update,
)

SERIES = "document.getElementById('{}')._plot.series.map(s => s.label)"


def click_net(page: Page, net: str) -> None:
    before = updates(page)
    page.locator(f'.net-label[data-net="{net}"] text').first.click()
    wait_for_update(page, before)


def turn(page: Page, ref: str, rotation: float) -> None:
    before = updates(page)
    page.locator(f'input[data-ref="{ref}"]').fill(str(round(rotation * 100)))
    wait_for_update(page, before)


def field(page: Page, name: str) -> str:
    return page.locator(f'#probe-body [data-field="{name}"]').inner_text()


def percent(text: str) -> float:
    return float(text.replace("%", "").replace("\u2212", "-").strip())


def test_page_has_brand_fonts_and_status(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    expect(page.locator("header img.logo")).to_have_attribute(
        "src", "assets/brand/solum-logo-outlined.svg"
    )
    expect(page.locator("#status")).to_have_count(0)  # no simulator badge (D-090)
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.fonts.check('300 15px Fahkwang')")
    # Lora is only fetched once a note uses it: load it to show the file is there
    assert page.evaluate("document.fonts.load('italic 13px Lora').then((f) => f.length)") == 1
    assert page.locator('link[rel="icon"]').get_attribute("href") == (
        "assets/brand/favicon-outlined.svg"
    )


def test_every_part_and_label_is_drawn(page: Page, base_url: str) -> None:
    starter = json.loads((REPO / "library" / "starters" / "ts808.json").read_text())
    open_circuit(page, base_url)
    expect(page.locator("g.part")).to_have_count(len(starter["parts"]))
    expect(page.locator(".net-label")).to_have_count(len(starter["labels"]))
    expect(page.locator("#circuit-name")).to_have_text(starter["name"])
    # opening probes the output: its labels are highlighted
    outs = [lb for lb in starter["labels"] if lb["net"] == "out"]
    assert page.locator('.net-label.probed[data-net="out"]').count() == len(outs) > 0
    # wired: the starter is drawn with wires, ground symbols and rail bars
    expect(page.locator("line.wire")).to_have_count(len(starter["wires"]))
    assert page.locator(".net-label.ground").count() > 0
    assert page.locator(".net-label.rail").count() > 0


def test_drive_hardens_the_clipping(page: Page, base_url: str) -> None:
    """Phase 2 acceptance: the op-amp output's diode clipping hardens as Drive rises."""
    open_circuit(page, base_url)
    click_net(page, "u2o")
    expect(page.locator('[data-testid="probe-name"]')).to_have_text("u2o")
    thd, peaks = [], []
    for rotation in (0.0, 0.5, 1.0):
        turn(page, "VR1", rotation)
        thd.append(percent(field(page, "thd")))
        peaks.append(float(field(page, "peak-pos").split()[0]))
    # it clips even at minimum Drive (gain about 12), and harder at every step up
    assert thd[0] < thd[1] < thd[2] and thd[2] - thd[0] > 5, thd
    assert field(page, "clipping") == "heavy"
    # the diodes hold the swing near their forward drop however much gain is added
    assert all(p < 0.8 for p in peaks), peaks
    # the scope shows the waveform with the scaled input overlaid
    plot = page.evaluate(SERIES.format("scope-plot"))
    assert plot[1:] == ["u2o", "input, scaled"]
    # the notes say what the pick levels are and where the harmonics are read
    # (behind each pane's ⓘ, D-109)
    assert "Soft 0.1 V, Medium 0.3 V, Hard 1 V peak" in info_text(page, "panel-scope")
    assert "measured at u2o" in info_text(page, "panel-harmonics")


@pytest.mark.timing
def test_tone_updates_the_curve_quickly(page: Page, base_url: str) -> None:
    """Phase 2 acceptance: turning Tone updates the curve in under a second. Timed to the
    curve's change, not `wait_for_update`, which also waits for the Bias & headroom pane
    measuring after the run (D-106) and put this at 1.0 s with no change in the curve's
    speed (D-196)."""
    open_circuit(page, base_url)
    curve = "JSON.stringify(document.getElementById('frequency-plot')._plot.data[1])"
    first = page.evaluate(curve)
    start = time.monotonic()
    page.locator('input[data-ref="VR2"]').fill("90")
    page.wait_for_function(f"(first) => {curve} !== first", arg=first, timeout=15_000)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"Tone took {elapsed:.2f} s"


def _timed(page: Page, act: Callable[[], object], counter: str = "updates") -> float:
    """Seconds from `act` until the page's `counter` moves on (`updates`: a run shown;
    `views`: the drawing redrawn), not waiting for Bias & headroom's measuring after it."""
    before = int(page.evaluate(f"Number(document.body.dataset.{counter} || 0)"))
    start = time.monotonic()
    act()
    page.wait_for_function(
        f"(n) => Number(document.body.dataset.{counter} || 0) > n", arg=before, timeout=15_000
    )
    return time.monotonic() - start


@pytest.mark.timing
def test_a_knob_position_seen_before_is_shown_quickly(page: Page, base_url: str) -> None:
    """Phase 10: on the Klon (the biggest starter), a knob back at a position already run
    shows its run in about 0.2 s (0.12 of it the knob's debounce); the cache answers."""
    open_circuit(page, base_url, "klon-centaur", timeout=60_000)
    turn(page, "VR2", 0.37)
    turn(page, "VR2", 0.61)
    elapsed = _timed(page, lambda: page.locator('input[data-ref="VR2"]').first.fill("37"))
    assert elapsed < 0.6, f"A seen knob position took {elapsed:.2f} s"


@pytest.mark.timing
def test_a_node_click_after_a_run_is_quick(page: Page, base_url: str) -> None:
    """Phase 10 (D-273): another net clicked after a run needs no simulation; on the Klon
    it's shown in about 25 ms."""
    open_circuit(page, base_url, "klon-centaur", timeout=60_000)
    click_net(page, "clip")
    elapsed = _timed(page, lambda: page.locator('.net-label[data-net="dry"] text').first.click())
    assert elapsed < 0.3, f"A node click took {elapsed:.2f} s"


@pytest.mark.timing
def test_an_edit_is_drawn_quickly(page: Page, base_url: str) -> None:
    """Phase 10: a part's new value applied (auto-run off, the default) redraws the Klon's
    whole drawing, in about 30 ms."""
    open_circuit(page, base_url, "klon-centaur", timeout=60_000)
    page.locator('g.part[data-ref="R23"]').dblclick()
    page.locator("#field-value").fill("5k1")
    elapsed = _timed(page, lambda: page.locator("form.popup button.primary").click(), "views")
    assert elapsed < 0.3, f"An edit took {elapsed:.2f} s to draw"
    expect(page.locator('g.part-text[data-ref="R23"] .value')).to_have_text("5k1")


@pytest.mark.timing
def test_apply_with_auto_run_reruns_at_once(page: Page, base_url: str) -> None:
    """D-283: with Auto-run on, a form's Apply re-runs without the edit's 250 ms wait (that
    wait is for drags and held keys); a value seen before is shown in about 0.15 s."""
    open_circuit(page, base_url, "klon-centaur", timeout=60_000)
    page.locator("#autorun").check()

    def apply(value: str) -> float:
        click_part(page, "R23")  # its own run ends before the form's is timed
        page.keyboard.press("Enter")
        page.locator("#field-value").fill(value)
        page.wait_for_timeout(1000)  # the form's slider has loaded its steps for the typed value
        before = updates(page)
        # timed in the page, from the click itself: the driver's own click takes 0.1 s
        took = page.evaluate(
            """() => new Promise((done) => {
              const start = performance.now();
              const seen = document.body.dataset.updates;
              new MutationObserver((_m, o) => {
                if (document.body.dataset.updates === seen) return;
                o.disconnect();
                done((performance.now() - start) / 1000);
              }).observe(document.body, { attributes: true, attributeFilter: ["data-updates"] });
              document.querySelector("form.popup button.primary").click();
            })"""
        )
        wait_for_update(page, before, timeout=60_000)
        return float(took)

    apply("5k1")
    apply("4k7")
    elapsed = apply("5k1")
    assert elapsed < 0.25, f"Apply took {elapsed:.2f} s to show its run"


def test_turning_a_knob_keeps_the_panels_scrolled(page: Page, base_url: str) -> None:
    """Redrawing the plots used to jump the results pane back to the top (D-068)."""
    page.set_viewport_size({"width": 1280, "height": 700})
    open_circuit(page, base_url)
    panels = page.locator(".panels")
    panels.evaluate("(el) => { el.scrollTop = el.scrollHeight; }")
    top = panels.evaluate("(el) => el.scrollTop")
    assert top > 100  # the pane really is scrolled
    # set the knob from script: Playwright's fill would scroll its input into view
    before = updates(page)
    page.locator('input[data-ref="VR2"]').evaluate(
        "el => { el.value = '90'; el.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    wait_for_update(page, before)
    page.wait_for_timeout(100)
    assert panels.evaluate("(el) => el.scrollTop") == pytest.approx(top, abs=2)


def test_part_views(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    click_part(page, "VR2")
    labels = page.evaluate(
        "document.getElementById('frequency-plot')._plot.series.map(s => s.label)"
    )
    # the wiper and the output (no rotation overlay: the inspector's slider turns it)
    assert len(labels[1:]) == 2 and labels[2] == "out (output)"
    click_part(page, "D1")
    expect(page.locator("#device-plot .uplot")).to_have_count(1)
    assert field(page, "current").endswith("A")
    click_part(page, "Q1")
    assert field(page, "terminal") == "emitter (follower)"
    click_part(page, "IC1B")
    # RC4558 on 9 V: the datasheet's 3 V headroom from each rail; VREF (4.5 V) is inside
    assert field(page, "common-mode") == "inside 3.00 V to 6.00 V (the datasheet's input range)"
    expect(page.locator("g.part.selected")).to_have_count(1)
    # a pin row in the part view probes that net
    before = updates(page)
    page.locator('#probe-body tr[data-net="u2o"]').click()
    wait_for_update(page, before)
    expect(page.locator('[data-testid="probe-name"]')).to_have_text("u2o")


def test_snapshot_overlay(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    series = SERIES.format("frequency-plot")
    page.locator('[data-freeze="frequency"]').click()
    turn(page, "VR2", 0.1)
    assert page.evaluate(series)[-1] == "snapshot: out"
    page.locator('[data-clear="frequency"]').click()
    assert "snapshot: out" not in page.evaluate(series)
    page.locator('[data-freeze="scope"]').click()
    scope = SERIES.format("scope-plot")
    assert page.evaluate(scope)[-1] == "snapshot: out"


def test_dc_voltages_on_schematic(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    expect(page.locator(".dc-layer text")).to_have_count(0)
    page.locator("#view-menu").click()
    page.locator("#menu-dc").click()
    vref = page.locator('.dc-layer text[data-net="VREF"]')
    assert vref.count() > 1
    volts = float((vref.first.text_content() or "").split()[0])
    assert 4.3 < volts < 4.6  # R33/R32 divider of 9 V


def test_impedance_overlay_and_probe_row(page: Page, base_url: str) -> None:
    """Round 2 (D-127): View → Impedance (off at first) writes Zin under the guitar and
    Zout under the amp, at 1 kHz; the Probe pane has an Impedance row at the probed net
    and the output, looking in with everything connected."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(".z-layer text")).to_have_count(0)
    page.locator("#view-menu").click()
    page.locator("#menu-impedance").click()
    zin = page.locator('.z-layer text[data-z="zin"]')
    zout = page.locator('.z-layer text[data-z="zout"]')
    expect(zin.first).to_have_text(re.compile(r"^Zin [\d.]+ k\u03a9 · "))  # a few hundred k
    expect(zout).to_have_text(re.compile(r"^Zout [\d.]+ (k)?\u03a9 · "))
    assert "at 1 kHz" in (zin.first.locator("title").text_content() or "")
    assert "Changes with" in (zout.locator("title").text_content() or "")  # its Level knob
    # under their parts
    guitar = page.locator('g.part[data-ref="IN"]').bounding_box()
    under = zin.first.bounding_box()
    assert guitar and under and under["y"] > guitar["y"] + guitar["height"] - 2
    row = page.locator('#probe-body td[data-field="impedance"]')
    expect(row).to_have_text(re.compile("\u03a9$"))
    assert "everything connected" in (row.get_attribute("title") or "")
    page.locator("#view-menu").click()
    page.locator("#menu-impedance").click()  # off again
    expect(page.locator(".z-layer text")).to_have_count(0)


def test_the_impedance_overlay_follows_the_pickup(page: Page, base_url: str) -> None:
    """The user, 2026-11-10: on the Rangemaster, switching the guitar from buffered to a
    single coil to a P-90 didn't change the overlay. Now the pickup's source impedance and
    its resonance as the fuzz loads it are said, and change (D-241)."""
    from tests.ui.test_editor import inspect

    open_circuit(page, base_url, "dallas-rangemaster")
    page.locator("#autorun").check()  # each pickup picked runs again
    page.locator("#view-menu").click()
    page.locator("#menu-impedance").click()
    zin = page.locator('.z-layer text[data-z="zin"]')
    expect(zin).to_have_count(1)  # buffered: no resonance line
    expect(zin).to_have_text(re.compile("^Zin 33.7 k\u03a9 · 0.0 dB"))
    seen: list[str] = []
    for pickup in ("strat", "p90"):
        click_part(page, "IN")
        inspect(page, {"source": pickup})
        expect(zin).to_have_count(2)
        if seen:
            expect(zin.nth(1)).not_to_have_text(re.compile("^" + re.escape(seen[-1])))
        seen.append(zin.nth(1).evaluate("(t) => t.firstChild.nodeValue"))
        title = zin.first.locator("title").text_content() or ""
        assert "Guitar source:" in title and "into the amp" in title
    assert seen[0].startswith("Resonance 1.2") and seen[1].startswith("Resonance 7")


def test_every_starter_opens(page: Page, base_url: str) -> None:
    for path in sorted((REPO / "library" / "starters").glob("*.json")):
        # the Dyna Comp's first run waits ~0.4 s of signal for its envelope and C2 to
        # settle (D-245), several seconds on a loaded machine before the panes fill
        open_circuit(page, base_url, path.stem, timeout=40_000)
        expect(page.locator("#error")).to_be_hidden()
        expect(page.locator("#knobs-body input[type=range]").first).to_be_visible()


def test_errors_are_plain_english(page: Page, base_url: str, browser_errors: list[str]) -> None:
    open_circuit(page, base_url)
    page.evaluate("location.hash = 'no-such-circuit'")
    expect(page.locator("#error")).to_have_text(
        "There's no starter circuit called 'no-such-circuit'."
    )
    assert browser_errors == [
        "Failed to load resource: the server responded with a status of 404 (Not Found)"
    ]
    browser_errors.clear()


def test_pan_and_zoom(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    svg = page.locator("#schematic")
    start = svg.get_attribute("viewBox")
    box = svg.bounding_box()
    assert box
    page.mouse.move(box["x"] + 300, box["y"] + 300)
    page.mouse.wheel(0, -400)
    zoomed = (svg.get_attribute("viewBox") or "").split()
    assert float(zoomed[2]) < float((start or "").split()[2])
    page.mouse.down()
    page.mouse.move(box["x"] + 400, box["y"] + 350, steps=5)
    page.mouse.up()
    assert svg.get_attribute("viewBox") != " ".join(zoomed)
    page.locator("#fit-button").click()
    assert svg.get_attribute("viewBox") == start
    width = lambda: float((svg.get_attribute("viewBox") or "").split()[2])  # noqa: E731
    page.locator("#zoom-in").click()
    assert width() == pytest.approx(float((start or "").split()[2]) / 1.25)
    page.locator("#zoom-out").click()
    page.locator("#zoom-out").click()
    assert width() == pytest.approx(float((start or "").split()[2]) / 1.25 / 0.8 / 0.8)


def test_no_requests_leave_the_machine(page: Page, base_url: str) -> None:
    """D-022: fonts and scripts are vendored; nothing is fetched from elsewhere."""
    seen: list[str] = []
    page.on("request", lambda r: seen.append(r.url))
    open_circuit(page, base_url)
    page.evaluate("document.fonts.ready")
    assert seen and all(url.startswith(base_url) for url in seen), seen


def test_static_files_exist(repo: Path) -> None:
    for name in (
        "Fahkwang-ExtraLight.ttf",
        "Fahkwang-Light.ttf",
        "Fahkwang-Regular.ttf",
        "OFL.txt",
    ):
        assert (repo / "web" / "fonts" / "fahkwang" / name).is_file()
    assert (repo / "web" / "fonts" / "lora" / "OFL.txt").is_file()
    assert (repo / "web" / "vendor" / "uplot" / "LICENSE").is_file()


def test_knobs_are_played_not_saved(page: Page, base_url: str) -> None:
    """D-102: turning a knob changes what's heard and seen, not the circuit (no Not saved);
    "Use as opening positions" makes them the circuit's, as one edit Undo takes back."""
    open_circuit(page, base_url)
    opening = page.locator("#knobs-opening")
    expect(opening).to_be_disabled()
    curve = "document.getElementById('frequency-plot')._plot.data[1].join()"
    before = page.evaluate(curve)
    turn(page, "VR2", 0.9)
    assert page.evaluate(curve) != before  # played: the curve follows the knob
    expect(page.locator("#dirty")).to_be_hidden()
    expect(opening).to_be_enabled()
    opening.click()
    expect(page.locator("#dirty")).to_have_text("Not saved")
    expect(opening).to_be_disabled()
    # Undo puts the opening position back at 50 %, and the knob with it (a knob follows its
    # opening position whenever that changes: an edit to it, Undo or Redo)
    page.keyboard.press("Control+z")
    expect(page.locator('input[data-ref="VR2"]')).to_have_value("50")
    expect(opening).to_be_disabled()
    page.keyboard.press("Control+Shift+z")
    expect(page.locator('input[data-ref="VR2"]')).to_have_value("90")  # the redone opening: 90 %


def test_opening_positions_join_edit_curve(page: Page, base_url: str) -> None:
    """Made during Edit curve, "Use as opening positions" joins its session like any edit
    from outside (D-101): Keep and Discard show (not Done), and Discard takes it back."""
    open_circuit(page, base_url)
    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    expect(page.locator("#panel-frequency > summary .large-chip")).to_have_text("Editing")
    turn(page, "VR2", 0.9)
    expect(page.locator("#frequency-keep")).to_have_text("Done")  # a knob turn isn't a change
    page.locator("#knobs-opening").click()
    expect(page.locator("#frequency-keep")).to_have_text("Keep changes")
    expect(page.locator("#curve-others")).to_contain_text("Knob opening positions")
    page.locator("#frequency-discard").click()
    expect(page.locator("#panel-frequency > summary .large-chip")).to_have_count(0)
    expect(page.locator("#knobs-opening")).to_be_disabled()  # back at 50 %, the knob with it
    expect(page.locator('input[data-ref="VR2"]')).to_have_value("50")


def test_a_switch_in_use_lights_its_part(page: Page, base_url: str) -> None:
    """Round 3 (D-127), on a switch (the tone-switch test circuit): hovered, it lights;
    flipped, it stays lit through the redraw and keeps its label; left, it goes out."""
    open_fixture(page, base_url, "switch-tone")
    lit = page.locator('g.part.lit[data-ref="SW1"]')
    knob = page.locator('#knobs-body [data-knob="SW1"]')
    expect(knob).to_be_visible()
    expect(lit).to_have_count(0)
    knob.hover()
    expect(lit).to_have_count(1)
    before = updates(page)
    knob.locator('[data-position="1"]').click()
    expect(knob.locator('[data-position="1"]')).to_have_attribute("aria-checked", "true")
    wait_for_update(page, before)
    expect(lit).to_have_count(1)
    # its ref and label stay (round 3b: the flip took them away), once
    expect(page.locator('g.part-text[data-ref="SW1"] text.ref')).to_have_text("SW1 Tone")
    page.mouse.move(0, 0)
    expect(lit).to_have_count(0)


def test_a_knob_in_use_lights_its_part(page: Page, base_url: str) -> None:
    """Round 3 (D-127): a knob hovered, held (even dragged off it) or turned from the
    keys lights its part on the canvas; it goes out once the knob is left alone."""
    open_circuit(page, base_url, "ts808")
    lit = page.locator('g.part.lit[data-ref="VR2"]')
    knob = page.locator('#knobs-body input[data-ref="VR2"]')
    expect(lit).to_have_count(0)
    knob.hover()
    expect(lit).to_have_count(1)
    page.mouse.move(0, 0)
    expect(lit).to_have_count(0)
    # held: a drag that leaves the knob keeps it lit until let go
    knob.hover()
    page.mouse.down()
    page.mouse.move(0, 0)
    expect(lit).to_have_count(1)
    page.mouse.up()
    expect(lit).to_have_count(0)
    # from the keys: lit until focus moves on
    knob.focus()
    page.keyboard.press("ArrowRight")
    expect(lit).to_have_count(1)
    knob.blur()
    expect(lit).to_have_count(0)
    # over the stage picked in Bias & headroom (VR1 is in IC1B's feedback), the hover shows
    page.locator('#stage-chain .chain-block[data-refs="IC1B"]').click()
    p1 = page.locator('g.part[data-ref="VR1"]')
    expect(p1).to_have_class(re.compile(r"\bpicked\b"))
    stroke = "(e) => getComputedStyle(e.querySelector('path, line')).stroke"
    picked = p1.evaluate(stroke)
    page.locator('#knobs-body input[data-ref="VR1"]').hover()
    expect(page.locator('g.part.lit.picked[data-ref="VR1"]')).to_have_count(1)
    assert p1.evaluate(stroke) != picked


def test_a_battery_with_no_dc_jack_says_to_draw_one(page: Page, base_url: str) -> None:
    """9c: with a battery and no DC jack, the Power chip and the greyed menu say to draw a
    DC jack, not to plug one in."""
    open_fixture(page, base_url, "battery-alone")
    chip = page.locator("#power-chip")
    expect(chip).to_have_text("Battery · 9 V")
    expect(chip).to_have_attribute("title", re.compile(r"draw a DC jack"))
    menu = page.locator("#power")
    expect(menu).to_be_disabled()
    expect(menu).to_have_attribute("title", re.compile(r"Draw a DC jack to use it\.$"))


def test_the_palette_is_whole_before_a_circuit_loads(page: Page, base_url: str) -> None:
    """D-281 (the user, 2026-11-11): the V+ and V- tiles are in the palette as soon as it
    is drawn, not added once the circuit arrives (which moved every tile below them down a
    row after a refresh). The circuit's answer is held back to see the palette before it."""
    held: list[Any] = []
    page.route("**/api/starters/ts808", lambda route: held.append(route))
    page.goto(f"{base_url}#ts808")
    tiles = page.locator("#wiring-tiles > *")
    expect(tiles).to_have_count(5)
    assert [t.get_attribute("data-net") for t in tiles.all()] == [None, None, "V+", "V-", None]
    height = page.locator("#palette").evaluate("(el) => el.scrollHeight")
    assert len(held) == 1  # the circuit hasn't come yet
    held[0].continue_()
    wait_for_update(page, 0)
    assert page.locator("#palette").evaluate("(el) => el.scrollHeight") == height
    expect(page.locator('#wiring-tiles [data-net="V+"]')).to_have_attribute(
        "title", re.compile(r"^Supply V\+ \(9 V\)")
    )


def test_a_window_resize_never_shrinks_the_drawing(page: Page, base_url: str) -> None:
    """The view keeps its scale while the window is being resized, not only once it stops
    (the user, 2026-11-12: the drawing shrank, then grew back after the resize)."""
    page.set_viewport_size({"width": 1600, "height": 1000})
    open_circuit(page, base_url)
    scale = """() => { const s = document.getElementById('schematic');
        return s.viewBox.baseVal.width / s.getBoundingClientRect().width; }"""
    before = page.evaluate(scale)
    page.set_viewport_size({"width": 1200, "height": 800})
    page.wait_for_timeout(50)  # well inside the old 200 ms wait
    assert page.evaluate(scale) == pytest.approx(before, rel=1e-3)
