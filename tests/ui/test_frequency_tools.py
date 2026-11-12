# ruff: noqa: E501  (JavaScript inside strings)
"""The Frequency panel's tools (Phase 8b, D-097) in a real browser, including the phase's
acceptance on the TS808: Part influence lists C3/R4 as moving the low knee and the tone
network as moving the treble; double-clicking C3 opens Edit curve by part with its slider
(D-102), and dragging it moves the knee marker live."""

import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import info_text, open_circuit, run, updates, wait_for_update

MARKS = "document.getElementById('frequency-plot')._plot.marks"


def layer(page: Page, layer_id: str) -> None:
    """Turn a layer on or off from the Layers menu."""
    page.locator("#layers-button").click()
    page.locator(f"#layer-{layer_id}").click()


def influence(page: Page) -> dict[str, str]:
    """The influence rows shown: ref → what it moves."""
    rows = page.locator("#influence-rows li")
    expect(rows.first).to_be_visible(timeout=15_000)
    found: list[list[str]] = rows.evaluate_all(
        "els => els.map((e) => [e.dataset.ref, e.querySelector('.what').textContent])"
    )
    return dict((ref, what) for ref, what in found)


def knee_lines(page: Page) -> list[float]:
    return [float(x) for x in page.evaluate(f"{MARKS}.lines.map((l) => l.x)")]


def test_ts808_part_influence_and_a_live_knee(page: Page, base_url: str) -> None:
    """Phase 8b acceptance (probing `out`, the TS808's output)."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator("#frequency-readings .readings-net")).to_have_text("out")
    layer(page, "influence")
    rows = influence(page)
    top = list(rows)[:4]
    assert set(top) == {"C3", "R4", "C5", "R8"}, rows
    for ref in ("C3", "R4"):
        assert rows[ref].startswith("moves the low knee"), rows[ref]
    for ref in ("C5", "R8"):  # the tone network's fixed low-pass, R8/C5
        assert rows[ref].startswith("moves the high knee (treble roll-off)"), rows[ref]
    assert "sets bias" not in page.locator('#influence-rows li[data-ref="C3"]').inner_text()

    layer(page, "knees")
    [low, high] = knee_lines(page)
    assert 250 < low < 450 and 1500 < high < 2500  # 329 Hz and 1.92 kHz from ngspice

    # outside Edit curve the list is for reading: a click opens nothing (D-102)
    expect(page.locator("#influence-edit-note")).to_have_text(
        "Double-click a part to open it in the editor (Edit curve)."
    )
    pick = page.locator('#influence-rows li[data-ref="C3"] button.influence-pick')
    pick.click()
    expect(page.locator("#influence-value-slider")).to_have_count(0)
    expect(page.locator("#panel-frequency")).not_to_have_class(re.compile(r"\bexpanded\b"))
    # a double-click opens the large view in Edit curve by part, C3's slider in its row
    pick.dblclick()
    expect(page.locator("#panel-frequency")).to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    expect(page.locator("#edit-by-part")).to_have_attribute("aria-checked", "true")
    slider = page.locator('#curve-edit #influence-rows li[data-ref="C3"] #influence-value-slider')
    expect(slider).to_be_enabled()
    expect(page.locator("#influence-value-slider-ends")).to_have_text(
        "10p \N{EN DASH} 470µ"
    )  # D-164
    # 470n, ten times C3: E12 from 10p, four decades (48 steps) then 4.7's place (8)
    ten_times = 4 * 12 + 8
    with page.expect_response(lambda r: r.url.endswith("/api/curve") and r.status == 200):
        slider.evaluate(
            "(el, i) => { el.value = String(i); el.dispatchEvent(new Event('input', {bubbles: true})); }",
            ten_times,
        )
    # the knee marker followed the drag (no ngspice run yet): a 10x C3 drops the low knee
    # (in Edit curve the knee is a dot, not a line)
    knee = f"({MARKS}.handles.find((h) => h.id === 'knee-low')?.x ?? 1e9)"
    page.wait_for_function(f"{knee} < {low * 0.8}")
    expect(page.locator("#frequency-readings")).not_to_have_class(re.compile(r"\bstale\b"))
    # letting go applies it and re-runs; the row and its slider stay open, and the change
    # joins Edit curve (not "outside Edit curve")
    before = updates(page)
    slider.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles: true}))")
    wait_for_update(page, before)
    expect(page.locator("#influence-value-slider")).to_be_visible()
    expect(page.locator("#curve-changes")).to_contain_text("C3 47n \N{RIGHTWARDS ARROW}")
    expect(page.locator("#curve-changes .tag")).to_have_count(0)
    expect(page.locator("#frequency-keep")).to_have_text("Keep changes")
    # By curve has the dots' rows; the part's slider goes with the switch
    page.locator("#edit-by-curve").click()
    expect(page.locator("#handle-rows")).to_be_visible(timeout=15_000)
    expect(page.locator("#influence-value-slider")).to_have_count(0)
    page.locator("#frequency-discard").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "false")


def test_click_the_curve_to_rank_at_a_frequency(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    layer(page, "influence")
    influence(page)
    box = page.locator("#frequency-plot .u-over").bounding_box()
    assert box is not None
    with page.expect_response(lambda r: r.url.endswith("/api/influence")):
        page.mouse.click(box["x"] + 3, box["y"] + box["height"] / 2)  # the low end
    expect(page.locator(".influence-at:not(.influence-note)")).to_contain_text(
        "What shapes the curve at"
    )
    at = page.evaluate(f"{MARKS}.at")
    assert at is not None and at < 15
    first = page.locator("#influence-rows li").first.get_attribute("data-ref")
    assert first in {"C1", "R2", "R5", "C2"}  # the input's high-pass corners, below 20 Hz
    with page.expect_response(lambda r: r.url.endswith("/api/influence")):
        page.locator("#influence-all").click()
    assert page.evaluate(f"{MARKS}.at") is None


@pytest.mark.parametrize("starter", ["ts808", "big-muff-pi-v3"])
def test_frequency_axes(page: Page, base_url: str, starter: str) -> None:
    """D-102: 10 Hz - 30 kHz, shaded outside 20 Hz - 20 kHz; the level axis fitted to the
    audible band, the same in and out of Edit curve; on the Big Muff too (it spanned
    ~150 dB in Edit, from the curve's far ends)."""
    scale = "(() => { const p = document.getElementById('frequency-plot')._plot; return [p.scales.x.min, p.scales.x.max, p.scales.y.min, p.scales.y.max, p.shade]; })()"
    open_circuit(page, base_url, starter)
    x0, x1, y0, y1, shade = page.evaluate(scale)
    assert x0 == pytest.approx(10) and x1 == pytest.approx(30000)
    assert shade == [20, 20000]
    assert y0 % 5 == 0 and y1 % 5 == 0 and y1 - y0 < 90, (starter, y0, y1)
    page.locator("#frequency-expand").click()
    page.wait_for_function("document.getElementById('frequency-plot')._plot.height > 300")
    expanded = page.evaluate(scale)
    page.locator("#frequency-edit").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    page.wait_for_timeout(200)
    assert page.evaluate(scale) == expanded  # switching to Edit doesn't look like a zoom
    assert expanded[2:4] == [y0, y1]
    page.locator("#frequency-keep").click()
    assert page.evaluate(scale) == expanded


def test_knob_hover_shades_its_band(page: Page, base_url: str) -> None:
    """Hovering a knob in the Knobs panel shades where it acts, as an influence row does,
    with the Knob ranges layer off too (D-102)."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator("body")).to_have_attribute("data-layers", "")
    page.locator('#knobs-body input[data-ref="VR2"]').hover()
    page.wait_for_function(f"{MARKS}.bands.length === 1", timeout=15_000)
    assert page.evaluate(f"{MARKS}.bands[0].kind") == "above"
    page.mouse.move(0, 0)
    page.wait_for_function(f"{MARKS}.bands.length === 0")
    layer(page, "knobs")
    expect(page.locator('#knob-ranges li[data-knob="VR2"]')).to_contain_text(
        "shelf", timeout=15_000
    )
    page.locator('#knobs-body input[data-ref="VR2"]').hover()
    page.wait_for_function(f"{MARKS}.bands.length === 1")
    assert page.evaluate(f"{MARKS}.bands[0].kind") == "above"
    page.mouse.move(0, 0)
    page.wait_for_function(f"{MARKS}.bands.length === 0")


def test_knob_hover_shades_while_editing_the_curve(page: Page, base_url: str) -> None:
    """In Edit curve, a knob's hover shades where it acts too, as a By part row does (it
    didn't: Edit curve dropped it)."""
    open_circuit(page, base_url, "ts808")
    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    page.wait_for_function(f"{MARKS}.handles.length > 0", timeout=15_000)
    knob = page.locator('#knobs-body input[data-ref="VR2"]')
    knob.dispatch_event("pointerenter")  # the Knobs panel may sit under the large view
    page.wait_for_function(f"{MARKS}.bands.length === 1", timeout=15_000)
    assert page.evaluate(f"{MARKS}.bands[0].kind") == "above"
    assert page.evaluate(f"{MARKS}.handles.length") > 0  # the dots stay
    knob.dispatch_event("pointerleave")
    page.wait_for_function(f"{MARKS}.bands.length === 0")


def test_knob_ranges_listed_and_shaded(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    layer(page, "knobs")
    tone = page.locator('#knob-ranges li[data-knob="VR2"]')
    expect(tone).to_contain_text("Tone:", timeout=15_000)
    expect(tone).to_contain_text("shelf")
    expect(page.locator('#knob-ranges li[data-knob="VR3"]')).to_contain_text("level")
    tone.hover()
    band: Any = page.evaluate(f"{MARKS}.bands[0]")
    assert band["kind"] == "above" and 500 < band["lo"] < 1200
    page.mouse.move(0, 0)
    assert page.evaluate(f"{MARKS}.bands.length") == 0


def test_layers_are_remembered_and_expand(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    layer(page, "peaks")
    expect(page.locator("body")).to_have_attribute("data-layers", "peaks")
    [peak] = page.evaluate(f"{MARKS}.points")
    assert peak["kind"] == "peak" and 600 < peak["x"] < 1000
    page.reload()
    wait_for_update(page, 0)
    expect(page.locator("body")).to_have_attribute("data-layers", "peaks")
    small = page.locator("#frequency-plot").bounding_box()
    page.locator("#frequency-expand").click()
    expect(page.locator("#panel-frequency")).to_have_class(re.compile(r"\bexpanded\b"))
    page.wait_for_function("document.getElementById('frequency-plot')._plot.height > 300")
    big = page.locator("#frequency-plot").bounding_box()
    assert small and big and big["width"] > small["width"]
    # expanded keeps its own layers, all on by default; its Layers menu works over the panel
    expect(page.locator("body")).to_have_attribute("data-layers", "knees peaks knobs influence")
    layer(page, "knees")
    expect(page.locator("body")).to_have_attribute("data-layers", "peaks knobs influence")
    layer(page, "knees")
    page.locator("#frequency-expand").click()
    expect(page.locator("#panel-frequency")).not_to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("body")).to_have_attribute("data-layers", "peaks")
    layer(page, "peaks")


def test_layers_logic(page: Page, base_url: str) -> None:
    page.goto(base_url)
    got = run(
        page,
        """
      const L = await m('layers.js');
      const store = new Map();
      const storage = {getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v)};
      L.saveLayers(new Set(['knees', 'bogus']), storage);
      const loaded = [...L.loadLayers(storage)];
      const features = {shape: 'shaped', knees: [{side: 'low', f: 100, simple: false, text: '100 Hz'}],
        peaks: [{f: 500, db: 3, text: '500 Hz'}], dips: []};
      const marks = L.curveMarks(features, new Set(['knees', 'peaks']));
      const none = L.curveMarks(features, new Set());
      const broken = {getItem: () => { throw new Error('blocked'); }};
      // the level axis fits 20 Hz - 20 kHz only (D-102): the 10 Hz and 30 kHz points are off it
      const data = {x: [10, 20, 1000, 20000, 30000], series: [{values: [-120, -12, 3, -7, -150]}, {values: [null, -2, 8, 1, 40]}]};
      const fit = L.levelAxis(null, data, false);
      const held = L.levelAxis([-40, 40], data, true);
      const refit = L.levelAxis([-40, 40], data, false);
      const widened = L.levelAxis([-10, 10], data, true);
      return {loaded, marks, none, blocked: [...L.loadLayers(broken)], fit, held, refit, widened,
        empty: L.audibleLevels({x: [10, 30000], series: [{values: [1, 2]}]})};
    """,
    )
    assert got["loaded"] == ["knees"]
    assert got["marks"]["lines"] == [{"x": 100, "label": "100 Hz (\N{MINUS SIGN}3 dB below peak)"}]
    assert got["marks"]["points"] == [{"x": 500, "y": 3, "kind": "peak", "label": "500 Hz"}]
    assert got["none"]["lines"] == [] and got["blocked"] == []
    # -12 .. 8 dB with 10 dB room on 5 dB lines; held (live, Edit) only widens
    assert got["fit"] == [-25, 20] and got["refit"] == [-25, 20]
    assert got["held"] == [-40, 40] and got["widened"] == [-25, 20]
    assert got["empty"] is None


@pytest.mark.parametrize("starter", ["big-muff-pi-v3", "fuzz-face"])
def test_influence_on_other_starters(page: Page, base_url: str, starter: str) -> None:
    open_circuit(page, base_url, starter)
    layer(page, "influence")
    assert influence(page)
    layer(page, "influence")


def test_handle_logic(page: Page, base_url: str) -> None:
    """Edit mode's handles, no DOM: the part a handle moves, its dots, the step a drag asks for."""
    page.goto(base_url)
    got = run(
        page,
        """
      const L = await m('layers.js');
      const knee = {id: 'knee-low', kind: 'knee', side: 'low', f: 300, db: -3, label: 'Low knee', text: '300 Hz',
        parts: [{ref: 'R14', exponent: -1, change: 1}, {ref: 'VR1', exponent: -1, change: 1}, {ref: 'C3', exponent: -0.9, change: 0.2}]};
      const peak = {id: 'peak-0', kind: 'peak', side: null, f: 320, db: 0, label: 'Peak', text: '320 Hz', parts: [{ref: 'C5', exponent: -0.5, change: 1}]};
      const nudges = [{ref: 'R14', bias: true, knob: false}, {ref: 'VR1', bias: false, knob: true}, {ref: 'C3', bias: false, knob: false}];
      const features = {shape: 'band', knees: [{side: 'low', f: 250, db: -4, simple: true, text: '250 Hz'}], peaks: [{f: 330, db: 1, text: '330 Hz'}], dips: []};
      const parts = {'knee-low': 'C3', 'peak-0': 'C5'};
      const values = [1e-9, 2.2e-9, 4.7e-9, 10e-9, 22e-9, 47e-9];
      return {
        part: L.handlePart(knee, nudges),
        pickedPart: L.handlePart(knee, nudges, 'R14'),
        gone: L.handlePart(knee, nudges, 'R99'),
        none: L.handlePart({...knee, parts: []}, nudges),
        at: L.handleAt(knee, features),
        peakAt: L.handleAt(peak, features),
        lost: L.handleAt(peak, {...features, peaks: [{f: 3000, db: 1, text: '3 kHz'}, {f: 30, db: 1, text: '30 Hz'}]}),
        only: L.handleAt(peak, {...features, peaks: [{f: 3000, db: 1, text: '3 kHz'}]}),
        noDot: L.handleMarks([peak], {...features, peaks: []}, parts, null),
        marks: L.handleMarks([knee, peak], features, parts, null),
        activeMark: L.handleMarks([knee, peak], features, parts, 'peak-0'),
        apart: L.handleMarks([knee, {...peak, f: 3000}], null, parts, null).map((x) => x.id),
        // no one part moves the peak: its dot still shows, unlabelled
        unlabelled: L.handleMarks([knee, peak], features, {'knee-low': 'C3', 'peak-0': null}, null).map((x) => x.label),
        unlabelledIdle: L.handleMarks([knee, peak], features, {'knee-low': 'C3', 'peak-0': null}, null).map((x) => x.idle),
        // the TS808's case: both corners move every knee about as much, so each dot gets its own part
        shared: L.handleParts([
          {...knee, parts: [{ref: 'C3', exponent: -0.54, change: 0.76}, {ref: 'C5', exponent: -0.47, change: 0.83}]},
          {...knee, id: 'knee-high', side: 'high', parts: [{ref: 'C5', exponent: -0.51, change: 0.83}, {ref: 'C3', exponent: -0.46, change: 0.76}]},
          {...peak, parts: [{ref: 'C3', exponent: -0.5, change: 0.76}, {ref: 'R4', exponent: -0.5, change: 0.78}, {ref: 'R9', exponent: -0.3, change: 0}]},
        ], nudges, new Map()),
        keptPick: L.handleParts([knee], nudges, new Map([['knee-low', 'VR1']])),
        seek: L.seekStep(values, {v: 10e-9, f: 1000}, 500, -1),
        past: L.seekStep(values, {v: 10e-9, f: 1000}, 10, -1),
        changes: L.curveChanges({parts: [{ref: 'C3', value: '47n'}, {ref: 'R4', value: '4k7'}, {ref: 'IN'}, {ref: 'R9', value: '1k'}]},
          {parts: [{ref: 'C3', value: '100n'}, {ref: 'R4', value: '4k7'}, {ref: 'IN'}, {ref: 'R10', value: '1k'}]}),
        noChanges: L.curveChanges(null, {parts: []}),
        // a knee and a peak 0.1 octave apart: one double dot naming both; Shift takes the peak
        sharedDot: L.handleMarks([knee, {...peak, levels: [{refs: ['C5'], weights: [1], slope: 4, spill: 1}]}],
          {...features, peaks: [{f: 268, db: 1, text: '268 Hz'}]}, parts, null),
        lostKnee: L.lostReason(knee, {...features, knees: [{...features.knees[0], simple: false}]}),
        goneKnee: L.lostReason(knee, {...features, knees: []}),
        lostPeak: L.lostReason(peak, {...features, peaks: [{f: 3000, db: 1, text: ''}, {f: 30, db: 1, text: ''}]}),
        found: L.lostReason(knee, features),
        // R14 moved the knee earlier and was changed: kept in the menu, marked; C9 wasn't changed
        rowParts: L.rowParts({...knee, parts: [knee.parts[2]]},
          new Map([['R14', knee.parts[0]], ['C9', {ref: 'C9', exponent: -0.4, change: 0}]]), new Set(['R14', 'C3'])),
        keptNotDefault: L.handlePart({...knee, parts: [{ref: 'R15', exponent: -2, change: 0, kept: true}, {ref: 'C3', exponent: -0.9, change: 0}]}, []),
      };
    """,
    )
    assert got["part"] == "C3"  # R14 sets a bias and VR1 is a knob
    assert got["pickedPart"] == "R14" and got["gone"] == "C3" and got["none"] is None
    assert got["at"] == {"f": 250, "db": -4, "text": "250 Hz"}
    assert got["peakAt"] == {"f": 330, "db": 1, "text": "330 Hz"} and got["lost"] is None
    assert got["only"]["f"] == 3000  # the one peak, moved far
    assert got["noDot"] == []  # a peak the curve lost isn't drawn where it was
    # 250 Hz and 330 Hz are 0.4 octave apart: two dots
    assert [x["id"] for x in got["marks"]] == ["knee-low", "peak-0"]
    assert got["marks"][0] == {
        "id": "knee-low",
        "ids": ["knee-low"],
        "x": 250,
        "y": -4,
        "label": "C3",
        "active": False,
        "idle": False,
    }
    assert got["activeMark"][1]["active"] is True
    assert got["apart"] == ["knee-low", "peak-0"]
    assert got["unlabelled"] == ["C3", ""]
    [both] = got["sharedDot"]
    assert both["ids"] == ["knee-low", "peak-0"] and both["label"] == "C3 \N{MIDDLE DOT} C5"
    assert got["lostKnee"].startswith("not a corner now") and got["goneKnee"].startswith("gone")
    assert got["lostPeak"].startswith("lost") and got["found"] is None
    assert [(p["ref"], p.get("kept", False)) for p in got["rowParts"]] == [
        ("C3", False),
        ("R14", True),
    ]
    assert got["keptNotDefault"] == "C3"
    assert got["unlabelledIdle"] == [False, True]  # drawn faint
    assert got["shared"] == {"knee-low": "C3", "knee-high": "C5", "peak-0": "R4"}  # R9 too weak
    assert got["keptPick"] == {"knee-low": "VR1"}
    assert got["seek"] == {"index": 4, "end": False}  # half the frequency: twice the C, 22n
    assert got["past"] == {"index": 5, "end": True}  # 100x the C is past 47n
    # Keep / Discard: only values that changed (a part added or removed isn't a curve edit)
    assert got["changes"] == [{"ref": "C3", "field": "value", "from": "47n", "to": "100n"}]
    assert got["noChanges"] == []


def test_level_logic(page: Page, base_url: str) -> None:
    """Edit curve's up/down (D-100), no DOM: where a drag asks a dot to go, the level move a
    peak uses, how its row names it, the steps a drag to a level asks for, and the faint
    dots for where the curve's knees and peaks were."""
    page.goto(base_url)
    got = run(
        page,
        """
      const L = await m('layers.js');
      const pair = {refs: ['C3', 'R4'], weights: [1, -1], slope: 8, spill: 0.4};
      const gain = {refs: ['R6'], weights: [1], slope: 4, spill: 1};
      const peak = {id: 'peak-0', kind: 'peak', side: null, f: 800, db: 20, label: 'Peak', text: '800 Hz', parts: [], levels: [pair, gain]};
      const caps = [10e-9, 22e-9, 47e-9, 100e-9, 220e-9];
      const res = [1e3, 2.2e3, 4.7e3, 10e3, 22e3];
      return {
        // grabbed 2 dB above a peak at +20 dB, 1 kHz, and moved 4 dB up / to 1.5x the frequency
        up: L.dragTarget('y', {f: 1000, db: 20}, {x: 900, y: 22}, {x: 950, y: 26}),
        side: L.dragTarget('x', {f: 1000, db: 20}, {x: 900, y: 22}, {x: 1350, y: 30}),
        dots: L.startDots({shape: 'band', knees: [{side: 'low', f: 300, db: -3, simple: true, text: ''}, {side: 'high', f: 5000, db: -3, simple: false, text: ''}],
          peaks: [{f: 800, db: 20, text: ''}], dips: [{f: 2000, db: 5, text: ''}]}),
        noDots: L.startDots(null),
        // C3 doubled and R4 halved (t = ln 2) raised it 3 dB: 4.33 dB per unit, not the 8 guessed
        secant: L.measuredSlope(pair, {v: [47e-9, 4.7e3], db: 20}, {v: [94e-9, 2.35e3], db: 23}),
        wrongWay: L.measuredSlope(pair, {v: [47e-9, 4.7e3], db: 20}, {v: [94e-9, 2.35e3], db: 19}),
        noise: L.measuredSlope(pair, {v: [47e-9, 4.7e3], db: 20}, {v: [94e-9, 2.35e3], db: 19.95}),
        first: L.levelKey(L.levelMove(peak)), picked: L.levelKey(L.levelMove(peak, 'R6')),
        gone: L.levelKey(L.levelMove(peak, 'C9+R1')),
        knee: L.levelMove({...peak, kind: 'knee', levels: undefined}),
        texts: [L.levelText(pair), L.levelText(gain)],
        // +6.2 dB at 8 dB per unit: t = 0.77, x2.17 and /2.17 → 100n and 2k2
        up6: L.seekLevel([caps, res], {v: [47e-9, 4.7e3], db: 20}, 26.2, pair),
        none: L.seekLevel([caps, res], {v: [47e-9, 4.7e3], db: 20}, 20, pair),
        // C3 and R4 both pull the peak down as 1/sqrt (exponent -0.5), C3 raising it 4 dB per
        // unit and R4 lowering it 4. At the level asked but at a quarter of the frequency to
        // hold (800 Hz): both log values -ln 4 (x0.25, the level unchanged): 11.75n → 10n, 1k175 → 1k
        links: (() => {
          const c = (v, wires = []) => ({parts: [{ref: 'C3', value: v[0]}, {ref: 'R4', value: v[1]}, {ref: 'C5', value: v[2]}, {ref: 'R9', value: v[3]}], wires});
          const l = L.changeLinks([
            {label: 'Change C3, R4', source: 'curve', before: c(['47n', '4k7', '10n', '1k']), after: c(['100n', '2k2', '10n', '1k'])},
            {label: 'Change R9', source: '', before: c(['100n', '2k2', '10n', '1k']), after: c(['100n', '2k2', '10n', '2k'])},
            {label: 'Change C3, C5', source: 'curve', before: c(['100n', '2k2', '10n', '2k']), after: c(['47n', '2k2', '22n', '2k'])},
            {label: 'Add wire', source: '', before: c(['47n', '2k2', '22n', '2k']), after: c(['47n', '2k2', '22n', '2k'], [1])},
          ]);
          return {partners: Object.fromEntries(l.partners), outside: [...l.outside], others: l.others};
        })(),
        hover: L.partnerText([['R4'], ['C5']], new Set(['C3', 'R4'])),
        holdF: L.seekLevel([caps, res], {v: [47e-9, 4.7e3], db: 20, f: 200}, 20, {...pair, pulls: [[-0.5, 4], [-0.5, -4]]}, 800),
        past: L.seekLevel([caps, res], {v: [47e-9, 4.7e3], db: 20}, 60, pair),
        held: L.heldRange(null, -34, 26),
        kept: L.heldRange([-45, 40], -30, 38),
        wider: L.heldRange([-45, 40], -30, 43),
      };
    """,
    )
    assert got["up"] == pytest.approx(24) and got["side"] == pytest.approx(1500)
    # a knee that is only "3 dB below the peak" (not a corner) gets no dot, as in Edit mode
    assert got["dots"] == [{"x": 300, "y": -3}, {"x": 800, "y": 20}, {"x": 2000, "y": 5}]
    assert got["noDots"] == []
    assert got["secant"]["wrong"] is False
    assert got["secant"]["move"]["slope"] == pytest.approx(3 / 0.6931, rel=1e-3)
    assert got["wrongWay"]["wrong"] is True and got["wrongWay"]["move"]["slope"] == 8
    assert got["noise"] == {"move": got["noise"]["move"], "wrong": False}
    assert got["noise"]["move"]["slope"] == 8
    assert got["first"] == "C3+R4" and got["picked"] == "R6" and got["gone"] == "C3+R4"
    assert got["knee"] is None
    assert got["texts"] == [
        "C3 \N{UPWARDS ARROW} R4 \N{DOWNWARDS ARROW}",
        "R6 \N{UPWARDS ARROW} \N{MIDDLE DOT} whole curve",
    ]
    assert got["up6"] == {"indices": [3, 1], "end": False}
    assert got["none"] == {"indices": [2, 2], "end": False}
    assert got["holdF"] == {"indices": [0, 0], "end": False}
    # the Changed list: C3 and R4 changed together (a Shift-drag), C3 later with C5; R9 changed
    # from the inspector; a wire drawn outside is listed apart
    links = got["links"]
    assert links["partners"] == {"C3": [["R4"], ["C5"]], "R4": [["C3"]], "C5": [["C3"]]}
    assert links["outside"] == ["R9"] and links["others"] == ["Add wire"]
    assert (
        got["hover"]
        == "Changed together with R4; then with C5. C5 was put back. Ctrl+Z or History undoes a whole step."
    )
    assert got["past"] == {"indices": [4, 0], "end": True}
    # the level axis held while editing: 10 dB of room, on 5 dB lines; widened only when left
    assert got["held"] == [-45, 40] and got["kept"] == [-45, 40] and got["wider"] == [-45, 55]


def test_close_handles_share_a_dot(page: Page, base_url: str) -> None:
    page.goto(base_url)
    got = run(
        page,
        """
      const L = await m('layers.js');
      const a = {id: 'knee-high', kind: 'knee', side: 'high', f: 1000, db: -3, label: 'High knee', text: '1 kHz', parts: [{ref: 'C5', exponent: -1, change: 1}]};
      const b = {id: 'dip-0', kind: 'dip', side: null, f: 1080, db: -6, label: 'Dip', text: '1.08 kHz', parts: [{ref: 'R8', exponent: -1, change: 1}]};
      const parts = {'knee-high': 'C5', 'dip-0': 'R8'};
      return [L.handleMarks([a, b], null, parts, null).map((x) => x.id), L.handleMarks([a, b], null, parts, 'dip-0').map((x) => x.id)];
    """,
    )
    assert got == [["knee-high"], ["dip-0"]]  # one dot: the first's, or the active one's


def handle_point(page: Page, handle_id: str) -> tuple[float, float]:
    """Where a handle's dot is on screen."""
    xy: list[float] = page.evaluate(
        """(id) => {
        const p = document.getElementById('frequency-plot')._plot;
        const h = p.marks.handles.find((x) => x.id === id);
        const r = p.over.getBoundingClientRect();
        return [r.left + p.valToPos(h.x, 'x'), r.top + p.valToPos(h.y, 'y')];
      }""",
        handle_id,
    )
    return xy[0], xy[1]


def test_ts808_drag_the_low_knee(page: Page, base_url: str) -> None:
    """Edit curve on the TS808 (the large view's button; the small panel has none);
    the low knee's dot names C3 (R4 also sets the gain); dragging it down an octave makes C3
    bigger as it goes, and letting go applies it and re-runs, the knee lower."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator("#frequency-edit")).to_be_hidden()
    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    row = page.locator('#handle-rows li[data-handle="knee-low"]')
    expect(row).to_be_visible(timeout=15_000)
    expect(row.locator("select")).to_have_value("C3")
    page.wait_for_function(f"{MARKS}.handles.some((h) => h.id === 'knee-low')")
    marks: Any = page.evaluate(f"{MARKS}.handles")
    knee = next(x for x in marks if x["id"] == "knee-low")
    assert knee["label"] == "C3" and 250 < knee["x"] < 450

    x, y = handle_point(page, "knee-low")
    page.mouse.move(x, y)
    page.mouse.down()
    expect(page.locator("#handle-slider input[type=range]")).to_be_enabled()
    start = int(page.locator("#handle-slider input[type=range]").input_value())
    box = page.locator("#frequency-plot .u-over").bounding_box()
    assert box is not None
    target = page.evaluate(
        "(f) => document.getElementById('frequency-plot')._plot.valToPos(f, 'x')", knee["x"] / 2
    )
    for i in range(1, 6):
        page.mouse.move(x + (box["x"] + target - x) * i / 5, y)
    expect(page.locator("#handle-note")).to_contain_text("C3 47n →")
    assert int(page.locator("#handle-slider input[type=range]").input_value()) > start
    before = updates(page)
    page.mouse.up()
    wait_for_update(page, before)
    page.wait_for_function(
        f"{MARKS}.handles.some((h) => h.id === 'knee-low' && h.x < {knee['x'] * 0.7})"
    )
    # Keep / Discard: the change is listed, and Discard changes puts it back (the knee too)
    expect(page.locator("#curve-changes")).to_contain_text("C3 47n →")
    expect(page.locator("#frequency-keep")).to_have_text("Keep changes")
    expect(page.locator("#frequency-discard")).to_be_visible()
    expect(page.locator("#dirty")).to_be_visible()
    expect(page.locator("#frequency-expand")).to_be_disabled()  # Keep or Discard first
    bar_collapse = page.locator("#panel-frequency > summary .large-collapse")
    expect(bar_collapse).to_be_disabled()  # its bar's too
    before = updates(page)
    page.locator("#frequency-discard").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "false")
    expect(page.locator("#panel-frequency")).to_have_class(re.compile(r"\bexpanded\b"))
    wait_for_update(page, before)
    page.wait_for_function(f"{MARKS}.lines.some((l) => Math.abs(l.x - {knee['x']}) < 5)")
    expect(page.locator("#frequency-edit")).to_be_visible()
    expect(page.locator("#frequency-discard")).to_be_hidden()
    # a transaction: the chip is back off and there's nothing to undo
    expect(page.locator("#dirty")).to_be_hidden()
    page.locator("#edit-menu").click()
    expect(page.locator("#menu-undo .menu-label")).to_have_text("Undo")
    page.keyboard.press("Escape")
    expect(page.locator(".menu")).to_have_count(0)
    page.keyboard.press("Escape")  # shrinks it to its bar, never collapses (D-123)
    page.wait_for_function("() => !document.querySelector('#panel-frequency').open")
    expect(page.locator("#panel-frequency")).to_have_class(re.compile(r"\bexpanded\b"))


def test_ts808_drag_the_peak_up(page: Page, base_url: str) -> None:
    """Up/down (D-100): the TS808's mid hump. Its row's up/down menu starts on C3 up with
    R4 down (the gain leg's corner stays put, its gain rises); Shift+dragging the dot up
    4 dB moves both sliders, and letting go applies both and re-runs: the peak higher, in
    the same place, over a faint copy of the curve as it was, its row saying where it was.
    The dots stay on the plot all through the re-run."""
    open_circuit(page, base_url, "ts808")
    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    row = page.locator('#handle-rows li[data-handle="peak-0"]')
    expect(row).to_be_visible(timeout=15_000)
    expect(row.locator("select.handle-level")).to_have_value("C3+R4")
    expect(row.locator("select.handle-level option").first).to_contain_text(
        "C3 \N{UPWARDS ARROW} R4 \N{DOWNWARDS ARROW}"
    )
    expect(
        page.locator('#handle-rows li[data-handle="knee-low"] select.handle-level')
    ).to_have_count(0)
    page.wait_for_function(f"{MARKS}.handles.some((h) => h.id === 'peak-0')")
    peak = next(x for x in page.evaluate(f"{MARKS}.handles") if x["id"] == "peak-0")
    peak_text = row.locator(".value").inner_text()
    expect(row.locator(".was")).to_have_count(0)  # nothing moved yet
    scale = "(() => { const y = document.getElementById('frequency-plot')._plot.scales.y; return [y.min, y.max]; })()"
    held = page.evaluate(scale)
    assert held[1] >= peak["y"] + 10  # room to drag into
    # the curve as it was, drawn faint, with a dot where the peak was
    before_dots = page.evaluate(f"{MARKS}.before.dots")
    assert any(abs(d["x"] - peak["x"]) < 1 and abs(d["y"] - peak["y"]) < 0.01 for d in before_dots)
    assert page.evaluate(f"{MARKS}.before.x.length") > 50
    # holding Shift, the dot names its up/down parts
    page.keyboard.down("Shift")
    page.wait_for_function(
        f"{MARKS}.handles.some((h) => h.id === 'peak-0' && h.label.startsWith('C3 '))"
    )
    # ...and a knee, which can't go up or down, is drawn faint
    page.wait_for_function(f"{MARKS}.handles.some((h) => h.id === 'knee-low' && h.idle)")
    # the side pane: rows, a line, the changes; the help is behind the ⓘ (D-109), and Esc
    # closes it without leaving Edit curve
    expect(page.locator("#curve-edit hr")).to_have_count(1)
    expect(page.locator("#curve-edit .note")).to_have_count(0)
    assert "Shift+drag moves a peak or dip" in info_text(page, "panel-frequency")
    expect(page.locator("#frequency-keep")).to_be_visible()

    x, y = handle_point(page, "peak-0")
    box = page.locator("#frequency-plot .u-over").bounding_box()
    assert box is not None
    target = box["y"] + page.evaluate(
        "(db) => document.getElementById('frequency-plot')._plot.valToPos(db, 'y')", peak["y"] + 4
    )
    page.mouse.move(x, y)
    page.mouse.down()
    page.keyboard.up("Shift")  # Shift counts when the dot is grabbed
    for i in range(1, 6):
        page.mouse.move(
            x + 8, y + (target - y) * i / 5
        )  # a little sideways too: it's still up/down
    sliders = page.locator("#handle-slider input[type=range]")
    expect(sliders).to_have_count(2)
    expect(page.locator("#handle-note")).to_contain_text("C3 47n \N{RIGHTWARDS ARROW}")
    expect(page.locator("#handle-note")).to_contain_text("R4 4k7 \N{RIGHTWARDS ARROW}")
    expect(page.locator("#handle-note")).to_contain_text("peak +20.")
    page.wait_for_function(
        f"{MARKS}.handles.some((h) => h.id === 'peak-0' && h.label.startsWith('C3 '))"
    )
    assert page.evaluate(scale) == held
    # the fewest dots on the plot from here until the re-run's parts are back
    page.evaluate(
        f"window.fewestDots = 99; window.dotWatch = setInterval(() => {{ window.fewestDots = Math.min(window.fewestDots, {MARKS}.handles.length); }}, 5)"
    )
    before = updates(page)
    page.mouse.up()
    wait_for_update(page, before)
    page.wait_for_function(
        f"{MARKS}.handles.some((h) => h.id === 'peak-0' && h.y > {peak['y'] + 2}"
        f" && Math.abs(Math.log2(h.x / {peak['x']})) < 0.15)"
    )
    expect(page.locator("#curve-edit .hint", has_text="Finding")).to_have_count(0)
    page.wait_for_timeout(300)  # the new parts in
    assert page.evaluate("clearInterval(window.dotWatch), window.fewestDots") >= 3
    assert page.evaluate(scale) == held  # the axis held still through the drag and the re-run
    expect(row.locator(".was")).to_contain_text(f"was {peak_text}")
    expect(page.locator("#curve-changes")).to_contain_text("C3 47n \N{RIGHTWARDS ARROW}")
    expect(page.locator("#curve-changes")).to_contain_text("R4 4k7 \N{RIGHTWARDS ARROW}")
    # changed together: a dot on each, and the hover names the other
    for ref, other in (("C3", "R4"), ("R4", "C3")):
        line = page.locator(f'#curve-changes li[data-ref="{ref}"]')
        expect(line.locator(".linked-dot")).to_have_count(1)
        expect(line).to_have_attribute("title", re.compile(f"Changed together with {other}"))


def test_keep_is_one_undo_step_and_the_view_shrinks_by_its_title(page: Page, base_url: str) -> None:
    """Two value changes in Edit mode: Collapse waits; the title shrinks the large view to
    its title bar and back; Keep leaves Edit (the view stays) as one undo step, the chip on."""
    open_circuit(page, base_url, "ts808")
    panel = page.locator("#panel-frequency")
    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    row = page.locator('#handle-rows li[data-handle="knee-high"]')
    expect(row).to_be_visible(timeout=15_000)
    row.click()
    slider = page.locator("#handle-slider input[type=range]")
    for _ in range(2):  # two releases: two edits
        expect(slider).to_be_enabled()
        before = updates(page)
        slider.focus()
        page.keyboard.press("ArrowRight")
        slider.dispatch_event("change")
        wait_for_update(page, before)
    expect(page.locator("#curve-changes")).to_contain_text("C5 220n →")
    expect(page.locator("#frequency-expand")).to_be_disabled()

    size = panel.bounding_box()
    page.locator("#panel-frequency > summary").click()
    expect(panel).not_to_have_attribute("open", "")
    shrunk = panel.bounding_box()
    assert size and shrunk and shrunk["height"] < size["height"] / 3
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    page.locator("#panel-frequency > summary").click()
    expect(panel).to_have_attribute("open", "")

    page.locator("#frequency-keep").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "false")
    expect(panel).to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("#frequency-expand")).to_be_enabled()
    expect(page.locator("#dirty")).to_be_visible()
    page.locator("#edit-menu").click()
    expect(page.locator("#menu-undo .menu-label")).to_have_text("Undo Frequency curve: C5")
    page.locator("#menu-undo").click()  # one step back to 220n
    page.locator("#edit-menu").click()
    expect(page.locator("#menu-undo .menu-label")).to_have_text("Undo")
    expect(page.locator("#menu-redo .menu-label")).to_have_text("Redo Frequency curve: C5")


def test_edit_keeps_the_view_size_and_another_circuit_shrinks_it(page: Page, base_url: str) -> None:
    """The large view is one size, editing or not; Done with nothing changed leaves Edit;
    opening another circuit goes back to the circuit editor (`backToEditor`), Edit off and
    the view shrunk to its bar (D-127), not put back in the column."""
    open_circuit(page, base_url, "ts808")
    panel = page.locator("#panel-frequency")
    page.locator("#frequency-expand").click()
    expect(panel).to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("#frequency-expand")).to_have_text("Collapse")
    size = panel.bounding_box()
    page.locator("#frequency-edit").click()
    expect(page.locator('#handle-rows li[data-handle="knee-low"]')).to_be_visible(timeout=15_000)
    editing = panel.bounding_box()
    assert size and editing and abs(size["height"] - editing["height"]) < 1
    expect(page.locator("#frequency-edit")).to_be_hidden()
    expect(page.locator("#frequency-discard")).to_be_hidden()  # nothing changed yet
    expect(page.locator("#frequency-keep")).to_have_text("Done")
    expect(page.locator("#curve-changes")).to_have_text("No values changed yet.")
    page.locator("#frequency-keep").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "false")
    expect(panel).to_have_class(re.compile(r"\bexpanded\b"))

    page.locator("#frequency-edit").click()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    before = updates(page)
    page.goto(f"{base_url}#fuzz-face")
    wait_for_update(page, before)
    expect(panel).to_have_class(re.compile(r"\bexpanded\b"))  # still a large view, as a bar
    expect(panel).not_to_have_attribute("open", "")
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "false")
    panel.locator("> summary").click(position={"x": 60, "y": 10})  # its bar opens it again
    expect(panel).to_have_attribute("open", "")
    expect(page.locator("#frequency-edit")).to_be_visible()  # Edit off: its button back


def test_a_canvas_click_leaves_a_large_view_open_and_reset_panes_collapses(
    page: Page, base_url: str
) -> None:
    """D-281 (the user, 2026-11-11; D-127 had a canvas click shrink it): a large view stays
    open through clicks on the canvas and in the right pane: only its title bar, Esc or
    another view opening shrinks it. View -> Reset panes puts it back in the column, asking
    first with Edit curve's changes unsaved (Cancel leaves everything as it was)."""
    open_circuit(page, base_url, "ts808")
    panel = page.locator("#panel-frequency")
    page.locator("#frequency-expand").click()
    page.locator("#panel-knobs > summary").scroll_into_view_if_needed()
    page.locator("#panel-knobs").click(position={"x": 30, "y": 40})
    expect(panel).to_have_attribute("open", "")
    page.mouse.click(300, 150)  # the canvas, above the view
    page.wait_for_timeout(150)
    expect(panel).to_have_attribute("open", "")
    expect(panel).to_have_class(re.compile(r"\bexpanded\b"))
    panel.locator("> summary").click(position={"x": 60, "y": 10})  # its title bar shrinks it
    expect(panel).not_to_have_attribute("open", "")
    panel.locator("> summary").click(position={"x": 60, "y": 10})
    page.locator("#frequency-edit").click()
    drag_knee_lower(page)
    page.locator("#view-menu").click()
    page.locator("#menu-reset-panes").click()
    ask = page.locator(".ask")
    expect(ask.locator(".ask-title")).to_have_text("Frequency curve: keep the changes?")
    ask.locator('[data-answer="cancel"]').click()
    expect(panel).to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    page.locator("#view-menu").click()
    page.locator("#menu-reset-panes").click()
    ask.locator('[data-answer="discard"]').click()
    expect(panel).not_to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "false")
    expect(page.locator("#frequency-expand")).to_have_text("Expand")


def drag_knee_lower(page: Page) -> None:
    """Drag the TS808's low knee half an octave down and let go (one Edit curve step)."""
    page.wait_for_function(f"{MARKS}.handles.some((h) => h.id === 'knee-low' && !h.idle)")
    knee = next(x for x in page.evaluate(f"{MARKS}.handles") if x["id"] == "knee-low")
    x, y = handle_point(page, "knee-low")
    box = page.locator("#frequency-plot .u-over").bounding_box()
    assert box is not None
    target = box["x"] + page.evaluate(
        "(f) => document.getElementById('frequency-plot')._plot.valToPos(f, 'x')", knee["x"] / 1.5
    )
    page.mouse.move(x, y)
    page.mouse.down()
    expect(page.locator("#handle-slider input[type=range]")).to_be_enabled()
    for i in range(1, 6):
        page.mouse.move(x + (target - x) * i / 5, y)
    before = updates(page)
    page.mouse.up()
    wait_for_update(page, before)


def test_edit_curve_history(page: Page, base_url: str) -> None:
    """D-101: while Edit curve is on the History button says so (outlined; hovering it shows a card); its steps show in the History pane
    under "Edit curve (in progress)"; Ctrl+Z steps back through them and stops at the
    session's start (the card says so); Ctrl+Shift+Z redoes; Keep makes them one step."""
    open_circuit(page, base_url, "ts808")
    page.locator("#history-button").hover()
    expect(page.locator("#history-tip")).to_be_hidden()  # not editing: no card
    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    page.locator("#history-button").hover()
    expect(page.locator("#history-tip")).to_contain_text("You're editing the curve")
    expect(page.locator('#handle-rows li[data-handle="knee-low"]')).to_be_visible(timeout=15_000)
    drag_knee_lower(page)
    expect(page.locator("#curve-changes")).to_contain_text("C3 47n \N{RIGHTWARDS ARROW}")

    page.locator("#history-button").click()
    pane = page.locator("#history-pane")
    expect(pane).to_be_visible()
    expect(pane.locator(".history-heading").first).to_have_text("Frequency curve (in progress)")
    expect(pane.locator(".history-step.current")).to_have_text("Change C3")
    # nothing before the session here: "Opened" is where it began, so it can be reached
    expect(pane.locator(".history-heading").nth(1)).to_have_text("Before Frequency curve")
    expect(pane.locator(".history-step.start")).to_be_enabled()

    before = updates(page)
    page.keyboard.press("Control+z")  # the pane follows
    expect(pane.locator(".history-step.undone")).to_have_text("Change C3")
    wait_for_update(page, before)
    expect(page.locator("#curve-changes")).to_have_text("No values changed yet.")
    page.keyboard.press("Control+z")  # the session's start: no further
    expect(page.locator("#history-tip")).to_contain_text("where you started editing the curve")
    before = updates(page)
    page.keyboard.press("Control+Shift+z")
    wait_for_update(page, before)
    expect(page.locator("#curve-changes")).to_contain_text("C3 47n \N{RIGHTWARDS ARROW}")

    page.keyboard.press("Escape")  # closes the pane only: Edit stays on
    expect(pane).to_be_hidden()
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    page.locator("#frequency-keep").click()
    page.locator("#history-button").hover()
    expect(page.locator("#history-tip")).to_be_hidden()
    page.locator("#history-button").click()
    expect(pane.locator(".history-step.current")).to_have_text("Frequency curve: C3")
    expect(pane.locator(".history-heading")).to_have_count(0)
