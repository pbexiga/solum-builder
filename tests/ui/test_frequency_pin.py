# ruff: noqa: E501  (JavaScript inside strings)
"""P5 (D-366): the Frequency pane's pinned net, lines hidden from the plot's key, and the
zoom, in a real browser on the TS808 (its clipping stage's input is the net `q1e`)."""

import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import click_part, open_circuit, run, updates, wait_for_update
from tests.ui.test_editor import inspect, press, views, wait_for_view

PLOT = "document.getElementById('frequency-plot')._plot"
LABELS = f"{PLOT}.series.slice(1).map((s) => s.label)"
SHOWN = f"{PLOT}.series.slice(1).filter((s) => s.show).map((s) => s.label)"
PINNED = "q1e (pinned)"


def label_box(page: Page, net: str) -> dict[str, float]:
    box = page.locator(f'#schematic .net-label[data-net="{net}"]').first.bounding_box()
    assert box is not None
    return box


def pin_from_menu(page: Page, net: str) -> None:
    """Right-click the net's label → Pin frequency here, and wait for the run with its curve."""
    box = label_box(page, net)
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, button="right")
    before = updates(page)
    page.locator("#ctx-pin").click()
    wait_for_update(page, before)


def key(page: Page, label: str) -> None:
    """Click a line's entry in the plot's key, and wait for the panes to be drawn again."""
    page.locator("#frequency-plot .u-legend .u-series").filter(
        has_text=re.compile(rf"^\s*{re.escape(label)}\s*$")
    ).click()


def readings_net(page: Page) -> str:
    return page.locator("#frequency-readings .readings-net").inner_text()


def x_range(page: Page) -> tuple[float, float]:
    lo, hi = page.evaluate(f"[{PLOT}.scales.x.min, {PLOT}.scales.x.max]")
    return float(lo), float(hi)


def drag_plot(page: Page, f0: float, f1: float) -> None:
    """Drag across the Frequency plot from f0 to f1 (Hz)."""
    box = page.locator("#frequency-plot .u-over").bounding_box()
    assert box is not None
    x0, x1 = page.evaluate(f"[{PLOT}.valToPos({f0}, 'x'), {PLOT}.valToPos({f1}, 'x')]")
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + x0, y)
    page.mouse.down()
    page.mouse.move(box["x"] + (x0 + x1) / 2, y, steps=4)
    page.mouse.move(box["x"] + x1, y, steps=4)
    page.mouse.up()


def test_the_pin_holds_while_parts_are_selected_and_edited(page: Page, base_url: str) -> None:
    """P5's acceptance: pin the clipping stage's input, click through C3 and R7's place
    (R6 here) changing their values: the pinned curve stays, the selection's follows."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator("#frequency-pin-chip")).to_be_hidden()
    pin_from_menu(page, "q1e")
    expect(page.locator("#frequency-pin-chip")).to_be_visible()
    expect(page.locator("#frequency-pin-net")).to_have_text("q1e")
    expect(page.locator("#frequency-pin")).to_have_attribute("aria-pressed", "true")
    assert PINNED in page.evaluate(LABELS)
    pinned = page.evaluate(f"{PLOT}.data[{LABELS}.indexOf('{PINNED}') + 1]")
    for ref, value in (("C3", "100n"), ("R6", "47k")):
        click_part(page, ref)
        labels = page.evaluate(LABELS)
        assert PINNED in labels and "out (output)" in labels, labels
        inspect(page, {"value": value})
        before = updates(page)
        page.locator("#run").click()  # auto-run is off
        wait_for_update(page, before)
        expect(page.locator("#frequency-pin-net")).to_have_text("q1e")
        assert PINNED in page.evaluate(LABELS)
    # q1e is before the clipping stage: C3 and R6 (its feedback) leave its curve alone
    now = page.evaluate(f"{PLOT}.data[{LABELS}.indexOf('{PINNED}') + 1]")
    assert now == pytest.approx(pinned, abs=0.05)
    # the readings are the selection's; hidden, the pinned net's; with neither, OUT's
    assert readings_net(page) not in ("q1e", "out")
    key(page, page.evaluate(LABELS)[0])
    expect(page.locator("#frequency-readings .readings-net")).to_have_text("q1e")
    assert page.evaluate(SHOWN)[0] != page.evaluate(LABELS)[0]
    key(page, PINNED)
    expect(page.locator("#frequency-readings .readings-net")).to_have_text("out")
    # still hidden after another part is selected (only opening a circuit brings them back)
    click_part(page, "C3")
    assert PINNED not in page.evaluate(SHOWN)
    # the pin button again unpins (a view setting: nothing to undo)
    page.locator("#frequency-pin").click()
    expect(page.locator("#frequency-pin-chip")).to_be_hidden()
    assert PINNED not in page.evaluate(LABELS)


def test_the_chips_x_unpins_and_pin_pins_the_selection(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    before = updates(page)
    page.locator("#frequency-pin").click()  # nothing but OUT selected: OUT
    wait_for_update(page, before)
    expect(page.locator("#frequency-pin-net")).to_have_text("out")
    pin_from_menu(page, "q1e")  # pinning again moves it
    expect(page.locator("#frequency-pin-net")).to_have_text("q1e")
    page.locator("#frequency-unpin").click()
    expect(page.locator("#frequency-pin-chip")).to_be_hidden()
    assert PINNED not in page.evaluate(LABELS)
    # Try several values shows its sweep at the pinned net
    pin_from_menu(page, "q1e")
    click_part(page, "R6")
    press(page, "Enter")
    page.locator("#sweep-values").fill("10k, 100k")
    before = updates(page)
    page.locator("#sweep-run").click()
    wait_for_update(page, before)
    expect(page.locator("#sweep-net")).to_have_value("q1e")
    expect(page.locator("#sweep-net option:checked")).to_have_text("q1e (pinned)")


def test_a_deleted_net_unpins_with_its_note_and_undo_leaves_it_unpinned(
    page: Page, base_url: str
) -> None:
    open_circuit(page, base_url, "ts808")
    pin_from_menu(page, "q1e")
    box = label_box(page, "q1e")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    before = views(page)
    press(page, "Delete")  # the label goes: the net is renamed, so q1e is gone
    wait_for_view(page, before)
    expect(page.locator("#frequency-pin-chip")).to_be_hidden()
    expect(page.locator("#frequency-pin-note")).to_have_text(
        "The pinned net q1e is gone from the drawing, so it's unpinned."
    )
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    expect(page.locator('#schematic .net-label[data-net="q1e"]')).to_have_count(1)
    expect(page.locator("#frequency-pin-chip")).to_be_hidden()


def test_opening_another_circuit_unpins_and_shows_every_line(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    pin_from_menu(page, "q1e")
    key(page, PINNED)
    page.wait_for_function(f"!{SHOWN}.includes('{PINNED}')")
    key(page, "out (output)")
    page.wait_for_function(f"!{SHOWN}.includes('out (output)')")
    drag_plot(page, 200, 3000)
    expect(page.locator("#frequency-unzoom")).to_be_visible()
    before = updates(page)
    page.goto(f"{base_url}#fuzz-face")  # the same page: only its hash changes
    wait_for_update(page, before)
    expect(page.locator("#frequency-pin-chip")).to_be_hidden()
    expect(page.locator("#frequency-pin-note")).to_be_hidden()
    expect(page.locator("#frequency-unzoom")).to_be_hidden()
    assert page.evaluate(SHOWN) == page.evaluate(LABELS)


def test_zoom_holds_through_a_knob_drag_and_a_double_click_resets(
    page: Page, base_url: str
) -> None:
    open_circuit(page, base_url, "ts808")
    full = x_range(page)
    drag_plot(page, 200, 3000)
    page.wait_for_function(f"{PLOT}.scales.x.max < 5000")
    lo, hi = x_range(page)
    assert lo == pytest.approx(200, rel=0.05) and hi == pytest.approx(3000, rel=0.05)
    expect(page.locator("#frequency-unzoom")).to_have_text(
        re.compile(r"^Reset zoom (19\d|20\d) Hz – (2\.9\d|3\.\d+) kHz$")
    )
    # the level axis fits what's in view: no wider than the full plot's
    # a knob drag (live, then its run) keeps it
    knob = page.locator('input[data-ref="VR2"]')
    with page.expect_response(lambda r: r.url.endswith("/api/live") and r.status == 200):
        knob.dispatch_event("pointerdown")
    page.wait_for_selector('body[data-knob-live="VR2"]', state="attached")
    before = updates(page)
    knob.evaluate(
        "(el) => { el.value = '90'; el.dispatchEvent(new Event('input', { bubbles: true })); }"
    )
    assert x_range(page) == pytest.approx((lo, hi), rel=1e-6)
    wait_for_update(page, before)
    assert x_range(page) == pytest.approx((lo, hi), rel=1e-6)
    # the large view keeps its own
    page.locator("#frequency-expand").click()
    page.wait_for_function(f"{PLOT}.scales.x.max > 20000")
    expect(page.locator("#frequency-unzoom")).to_be_hidden()
    page.locator("#frequency-expand").click()
    page.wait_for_function(f"{PLOT}.scales.x.max < 5000")
    # a double-click goes back
    page.locator("#frequency-plot .u-over").dblclick()
    page.wait_for_function(f"{PLOT}.scales.x.max > 20000")
    assert x_range(page) == pytest.approx(full, rel=1e-6)
    expect(page.locator("#frequency-unzoom")).to_be_hidden()


def test_a_click_still_ranks_and_reset_zoom_goes_back(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    page.locator("#layers-button").click()
    page.locator("#layer-influence").click()
    expect(page.locator("#influence-rows li").first).to_be_visible(timeout=15_000)
    drag_plot(page, 100, 1000)
    page.wait_for_function(f"{PLOT}.scales.x.max < 2000")
    assert page.evaluate(f"{PLOT}.marks.at") is None  # a drag isn't a pick
    box = page.locator("#frequency-plot .u-over").bounding_box()
    assert box is not None
    with page.expect_response(lambda r: r.url.endswith("/api/influence")):
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    at: Any = page.evaluate(f"{PLOT}.marks.at")
    assert at is not None and 100 < at < 1000
    page.locator("#frequency-unzoom").click()
    page.wait_for_function(f"{PLOT}.scales.x.max > 20000")


def test_view_logic(js: Page) -> None:
    got = run(
        js,
        """
        const v = await m('frequency-view-logic.js');
        const data = { x: [10, 100, 1000], series: [
          { label: 'n1', values: [0, 1, 2], style: 'current', role: 'selection' },
          { label: 'out (output)', values: [3, 4, 5], style: 'output', role: 'output' }] };
        const pinned = v.withPinned(data, { nodes: { q: [6, 7, 8] } }, 'q');
        const readings = { q: [], out: [] };
        return {
          pinned: pinned.series.map((s) => [s.label, s.role]),
          noPin: v.withPinned(data, { nodes: {} }, 'q') === data,
          shortGrid: v.withPinned(data, { nodes: { q: [1] } }, 'q') === data,
          hidden: [...v.hiddenLabels(pinned, new Set(['output', 'pinned']))],
          role: v.roleOf(pinned, 'q (pinned)'),
          visible: v.visibleOnly(pinned, new Set(['selection'])).series.length,
          shown: v.readingsNet({ shown: 'n1', pinned: 'q', out: 'out', hidden: new Set(), readings }),
          toPinned: v.readingsNet({ shown: 'n1', pinned: 'q', out: 'out', hidden: new Set(['selection']), readings }),
          toOut: v.readingsNet({ shown: 'n1', pinned: null, out: 'out', hidden: new Set(['selection']), readings }),
          bothHidden: v.readingsNet({ shown: 'n1', pinned: 'q', out: 'out', hidden: new Set(['selection', 'pinned']), readings }),
          zoom: v.zoomRange(3000, 200),
          clamped: v.zoomRange(5, 50000),
          narrow: v.zoomRange(1000, 1001).map((f) => Math.round(f)),
          text: v.zoomText([210, 3100], [100, 200, 3162, 10000], ['100 Hz', '200 Hz', '3.16 kHz', '10 kHz']),
          gone: [v.pinGone('q', { a: 1 }), v.pinGone('q', { q: 1 }), v.pinGone(null, {})],
        };
        """,
    )
    assert got == {
        "pinned": [["n1", "selection"], ["out (output)", "output"], ["q (pinned)", "pinned"]],
        "noPin": True,
        "shortGrid": True,
        "hidden": ["out (output)", "q (pinned)"],
        "role": "pinned",
        "visible": 2,
        "shown": "n1",
        "toPinned": "q",
        "toOut": "out",
        "bothHidden": "out",
        "zoom": [200, 3000],
        "clamped": None,
        "narrow": [933, 1072],
        "text": "200 Hz – 3.16 kHz",
        "gone": [True, False, False],
    }
