# ruff: noqa: E501  (JavaScript inside strings)
"""Value sliders and live curves in the editor (D-081), in a real browser, including
Phase 6's acceptance: dragging a value slider on a Fender TMB part redraws the curve as
it moves, ngspice agrees once it's let go, and the part keeps the new value."""

import re
from itertools import count
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from solum.circuit.io import circuit_to_dict
from tests.jig import core_block, jig
from tests.ui.conftest import open_circuit, updates, wait_for_update
from tests.ui.test_editor import new_circuit, place

SHEETS = count(1)  # the app keeps its data across tests: a new name each time
CURVE = "Array.from(document.getElementById('frequency-plot')._plot.data[1])"


def open_tmb_sheet(page: Page, base_url: str) -> None:
    """The core Fender TMB block on a sheet: an ideal guitar on its input, a 1M amp on its
    output (the jig drawn beside it), saved as a circuit and opened."""
    page.goto(base_url)
    wait_for_update(page, 0)
    sheet = circuit_to_dict(jig(core_block("fender-tmb"), far=-600))
    made = page.evaluate(
        "(arg) => fetch('api/circuits', {method: 'POST', headers: {'Content-Type': 'application/json'},"
        " body: JSON.stringify({circuit: arg[0], name: arg[1]})}).then((r) => r.json())",
        [sheet, f"TMB sheet {next(SHEETS)}"],
    )
    assert "file" in made, made
    before = updates(page)
    page.goto(f"{base_url}#circuit/{made['file']['link']}")
    wait_for_update(page, before)


def open_inspector(page: Page, ref: str) -> None:
    before = updates(page)
    page.locator(f'g.part[data-ref="{ref}"]').dblclick()
    expect(page.locator("form.popup")).to_be_visible()
    wait_for_update(page, before)  # the part's view, so the panels show its curves
    expect(page.locator("#value-slider")).to_be_enabled()


def drag_to(page: Page, index: int, release: bool = False, slider: str = "value") -> Any:
    """Move a slider (value or rotation) as a drag does (input events), optionally let go
    (change), and read the Frequency curve straight after, before any answer from the
    server."""
    return page.locator(f"#{slider}-slider").evaluate(
        f"""(el, [i, release]) => {{
          el.value = String(i);
          el.dispatchEvent(new Event('input', {{ bubbles: true }}));
          if (release) el.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return {CURVE};
        }}""",
        [index, release],
    )


def saved_value(page: Page) -> str:
    """The open inspector's value: the part's value in the app's circuit."""
    return page.locator("#field-value").input_value()


def test_tmb_value_slider_is_live_and_ngspice_agrees(page: Page, base_url: str) -> None:
    """Phase 6 acceptance (D-081)."""
    open_tmb_sheet(page, base_url)
    open_inspector(page, "C3")
    before = page.evaluate(CURVE)
    # a capacitor's fixed range, whatever its value (D-164)
    expect(page.locator("#value-slider-ends")).to_have_text("10p \N{EN DASH} 470µ")
    slider = page.locator("#value-slider")
    top = int(slider.get_attribute("max") or 0)
    readings = page.locator("#frequency-readings").inner_text()
    with page.expect_response(lambda r: r.url.endswith("/api/curve") and r.status == 200):
        live = drag_to(page, top)
    assert live != before  # redrawn in the browser, at once
    expect(page.locator("#field-value")).to_have_value("470µ")
    # the readings follow the live curve, measured on the server (D-097)
    expect(page.locator("#frequency-readings")).not_to_have_class("readings stale")
    expect(page.locator("#frequency-readings")).not_to_have_text(readings)
    with page.expect_response(lambda r: r.url.endswith("/api/live") and r.status == 200):
        before_run = updates(page)
        drag_to(page, top, release=True)
        wait_for_update(page, before_run)
    expect(page.locator("#frequency-readings")).not_to_have_class("readings stale")
    # ngspice's curve, after the run, is the one the browser drew (D-079 parity; the run's
    # curve comes rounded to 0.01 dB)
    assert page.evaluate(CURVE) == pytest.approx(live, abs=0.01)
    page.locator("form.popup button.primary").click()  # Apply: nothing more to change
    expect(page.locator("form.popup")).to_be_hidden()
    open_inspector(page, "C3")
    assert saved_value(page) == "470µ"


def test_cancel_puts_the_value_back_and_undo_is_one_step(page: Page, base_url: str) -> None:
    open_tmb_sheet(page, base_url)
    open_inspector(page, "R1")
    with page.expect_response(lambda r: r.url.endswith("/api/live")):
        drag_to(page, 0, release=True)
    expect(page.locator("#field-value")).to_have_value("10k")
    page.locator("form.popup [data-action='cancel']").click()
    open_inspector(page, "R1")
    assert saved_value(page) == "100k"
    # a release is one undo step
    with page.expect_response(lambda r: r.url.endswith("/api/live")):
        drag_to(page, 3, release=True)
    page.locator("form.popup button.primary").click()
    page.keyboard.press("Control+z")
    open_inspector(page, "R1")
    assert saved_value(page) == "100k"


def test_snap_to_the_nearest_e12_value(page: Page, base_url: str) -> None:
    open_tmb_sheet(page, base_url)
    open_inspector(page, "R1")
    page.locator("#field-value").fill("50k")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_be_hidden()
    open_inspector(page, "R1")
    snap = page.locator("#value-slider-snap")
    expect(snap).to_have_text("E12: 47k")
    with page.expect_response(lambda r: r.url.endswith("/api/live")):
        snap.click()
    expect(page.locator("#field-value")).to_have_value("47k")
    expect(snap).to_be_hidden()


def test_frequency_readings(page: Page, base_url: str) -> None:
    open_tmb_sheet(page, base_url)
    readings = page.locator("#frequency-readings")
    expect(readings).to_be_visible()
    dip = readings.locator('[data-reading="Dip"] .value')
    expect(dip).to_contain_text("Hz")
    expect(dip).to_contain_text("depth")
    expect(readings.locator('[data-reading="At 1 kHz"] .value')).to_contain_text("dB")


def test_knob_drag_redraws_live(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)  # TS808
    knob = page.locator('input[data-ref="VR2"]')  # Tone
    first = page.evaluate(CURVE)
    with page.expect_response(lambda r: r.url.endswith("/api/live") and r.status == 200):
        knob.dispatch_event("pointerdown")
    page.wait_for_selector('body[data-knob-live="VR2"]', state="attached")
    live = knob.evaluate(
        f"(el) => {{ el.value = '95'; el.dispatchEvent(new Event('input', {{ bubbles: true }})); return {CURVE}; }}"
    )
    assert live != first  # before the debounced run
    before = updates(page)
    wait_for_update(page, before)
    assert page.evaluate(CURVE) == pytest.approx(live, abs=0.1)


def test_capacitor_view_shows_the_output_too(page: Page, base_url: str) -> None:
    open_tmb_sheet(page, base_url)
    open_inspector(page, "C3")
    labels = "document.getElementById('frequency-plot')._plot.series.slice(1).map((s) => s.label)"
    shown = page.evaluate(labels)
    assert len(shown) == 3 and shown[2].endswith("(output)")  # C3's two sides, then the output
    out = shown[2].removesuffix(" (output)")
    # the readings are of its effect on the output
    expect(page.locator("#frequency-readings .readings-net")).to_have_text(out)
    drag_to(page, 0)
    assert page.evaluate(labels) == shown  # the live curve draws the same three


def test_hovering_a_curve_shows_its_values(page: Page, base_url: str) -> None:
    open_tmb_sheet(page, base_url)
    page.locator("#frequency-plot .u-over").hover(position={"x": 120, "y": 60})
    hover = page.locator("#frequency-plot .plot-hover")
    expect(hover).to_be_visible()
    expect(hover.locator(".plot-hover-x")).to_have_text(re.compile(r"^[\d.]+ k?Hz$"))
    expect(hover.locator(".plot-hover-value").first).to_contain_text("dB")
    page.mouse.move(0, 0)
    expect(hover).to_be_hidden()


def test_a_pot_turns_with_a_rotation_slider(page: Page, base_url: str) -> None:
    open_tmb_sheet(page, base_url)
    open_inspector(page, "VR1")
    labels = "document.getElementById('frequency-plot')._plot.series.slice(1).map((s) => s.label)"
    assert page.evaluate(labels) == ["out"]  # VR1's wiper is the output: one curve
    turn = page.locator("#rotation-slider")
    expect(turn).to_be_enabled()
    expect(page.locator("#rotation-slider-ends")).to_have_text("0 % \N{EN DASH} 100 %")
    before = page.evaluate(CURVE)
    assert drag_to(page, 0, slider="rotation") != before  # live, at once
    expect(page.locator("#field-rotation")).to_have_value("0")
    with page.expect_response(lambda r: r.url.endswith("/api/live") and r.status == 200):
        drag_to(page, 0, release=True, slider="rotation")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_be_hidden()
    open_inspector(page, "VR1")
    expect(page.locator("#field-rotation")).to_have_value("0")


def test_the_live_curve_follows_another_selected_part(page: Page, base_url: str) -> None:
    """Open one part, click another: the slider still moves the first, and the curve
    shown (the second's) follows it live."""
    open_tmb_sheet(page, base_url)
    open_inspector(page, "R1")
    before = updates(page)
    page.locator('g.part[data-ref="C2"]').click()
    wait_for_update(page, before)
    first = page.evaluate(CURVE)
    with page.expect_response(lambda r: r.url.endswith("/api/live") and r.status == 200):
        drag_to(page, 0)  # C2's sides weren't in R1's live view: fetched, then drawn
    page.wait_for_function(
        f"(first) => JSON.stringify({CURVE}) !== JSON.stringify(first)", arg=first
    )
    assert drag_to(page, 3) != first


PIXELS = (
    "() => new Promise((done) => requestAnimationFrame(() =>"
    " done(document.querySelector('#frequency-plot canvas').toDataURL())))"
)


def test_the_curve_is_repainted_at_every_step(page: Page, base_url: str) -> None:
    """The plot's pixels, not just its data, change as the slider moves (a reused plot
    whose y range didn't need to widen once kept its old picture until the release)."""
    open_tmb_sheet(page, base_url)
    open_inspector(page, "C3")
    top = int(page.locator("#value-slider").get_attribute("max") or 0)
    pictures = []
    for step in (top, top // 2, top // 2 + 1, top // 2 + 2):
        drag_to(page, step)
        pictures.append(page.evaluate(PIXELS))
    assert len(set(pictures)) == len(pictures)


def test_arrow_keys_wait_for_each_step_to_run(page: Page, base_url: str) -> None:
    """Round 2 (D-127): an arrow key on a part's slider re-runs the circuit; presses
    while that run is out do nothing, so each step is drawn before the next."""
    open_tmb_sheet(page, base_url)
    open_inspector(page, "R1")
    slider = page.locator("#value-slider")
    start = int(slider.input_value())
    slider.focus()
    # the steps load again once the run is drawn
    with page.expect_response(lambda r: r.url.endswith("/api/live")):
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")  # while the first step runs: ignored
        page.keyboard.press("ArrowRight")
        assert int(slider.input_value()) == start + 1
        # greyed while it runs
        expect(page.locator(".slider-row.running #value-slider")).to_have_count(1)
        expect(slider).to_have_attribute("aria-busy", "true")
    page.wait_for_timeout(100)  # the answer handled
    expect(page.locator(".slider-row.running")).to_have_count(0)
    page.keyboard.press("ArrowRight")
    assert int(slider.input_value()) == start + 2


@pytest.mark.usefixtures("half_drawn")  # its runs are refused until it's wired
def test_a_slider_works_on_a_half_drawn_sheet(page: Page, base_url: str) -> None:
    """The user (2026-11-02): with the simulation failing (parts not wired yet), a
    capacitor's or resistor's slider was locked though the value could be typed. It
    moves and applies; only the live curve waits for the wiring (D-164)."""
    new_circuit(page, base_url, "Half drawn")
    place(page, "c", 0, 200)
    page.locator('g.part[data-ref="C1"]').dblclick()
    slider = page.locator("#value-slider")
    expect(slider).to_be_enabled()
    expect(page.locator("#value-slider-ends")).to_have_text("10p \N{EN DASH} 470µ")
    slider.evaluate(
        "(el) => { el.value = '0'; el.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    expect(page.locator("#field-value")).to_have_value("10p")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_be_hidden()
    expect(page.locator('g.part-text[data-ref="C1"] .value')).to_have_text("10p")
    # typed loosely, it's kept and shown in the standard form, drawing and form alike
    page.locator('g.part[data-ref="C1"]').dblclick()
    page.locator("#field-value").fill("100uf")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_be_hidden()
    expect(page.locator('g.part-text[data-ref="C1"] .value')).to_have_text("100µ")
    page.locator('g.part[data-ref="C1"]').dblclick()
    expect(page.locator("#field-value")).to_have_value("100µ")
