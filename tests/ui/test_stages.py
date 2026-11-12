"""The Bias & headroom pane in the browser (Phase 8c, D-106): the stage chain, its cards
and the test tones (D-122)."""

import json
import re
from typing import Any

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.ui.conftest import (
    REPO,
    info_text,
    open_circuit,
    open_fixture,
    part_pos,
    run,
    to_screen,
    updates,
    wait_for_update,
)

CHAIN = "#stage-chain .chain-block"


def labels(page: Page) -> list[str]:
    texts = "(es) => es.map((e) => e.textContent)"
    return list(page.eval_on_selector_all(f"{CHAIN} .ref", texts))


def block(page: Page, refs: str) -> Locator:
    """A block on the chain showing: the panel's, or the strip over the large view's chart."""
    return page.locator(f'.chain-block[data-refs="{refs}"]').filter(visible=True)


def open_card(page: Page, refs: str) -> Locator:
    """Click a block (if its card isn't open) and return the card (its top, its knobs and
    the rest)."""
    card = page.locator(f'#stage-card[data-refs="{refs}"]')
    if not card.count():
        block(page, refs).click()
    expect(card).to_be_visible()
    return page.locator("#stages-card-body")


def test_the_ts808s_stages_in_signal_order(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    assert labels(page) == ["Q1", "IC1B", "D1, D2", "IC1A", "Q3"]
    expect(page.locator("#stages-summary")).to_have_text(
        "Clips first: D1, D2 (clipper), from a soft pick."
    )
    # the guitar, the blocks and the amp, an arrow between each
    expect(page.locator("#stage-chain .chain-end")).to_have_text(["Guitar", "Amp"])
    expect(page.locator("#stage-chain .chain-arrow")).to_have_count(6)
    # a block: its name, its own gain at the tone, what it is, how it clips
    clipper = block(page, "D1 D2")
    expect(clipper.locator(".role")).to_have_text("diodes in feedback")
    expect(clipper.locator(".mark").first).to_have_text("soft")
    expect(clipper.locator(".block-gain")).to_have_text(re.compile(r"^±\d+ mV$"))
    expect(block(page, "IC1B").locator(".block-gain")).to_have_text(re.compile(r"^\+\d+ dB$"))
    assert "Clamps at ±" in (clipper.get_attribute("title") or "")  # the sentence is its tooltip
    # the solid bar on its left (it clips at a hard pick) says so in the tooltip; Q1 has none
    expect(clipper).to_have_class(re.compile(r"\bclips\b"))
    # solid on a clipper too, whose outline is dashed (round 2)
    assert clipper.evaluate("(e) => getComputedStyle(e).borderLeftStyle") == "solid"
    assert clipper.evaluate("(e) => getComputedStyle(e).borderTopStyle") == "dashed"
    assert "solid bar on its left" in (clipper.get_attribute("title") or "")
    assert "solid bar" not in (block(page, "Q1").get_attribute("title") or "")
    # hover lights its parts on the schematic: the device and what touches its pins
    block(page, "Q1").hover()
    for ref in ("Q1", "R1", "C2"):
        expect(page.locator(f'g.part.lit[data-ref="{ref}"]')).to_have_count(1)
    expect(page.locator('g.part.lit[data-ref="IC1A"]')).to_have_count(0)
    # a click keeps them lit, in the picked colour (D-127), and opens its card; the
    # coupling cap is IC1B's too
    card = open_card(page, "IC1B")
    page.locator("#stages-summary").hover()
    expect(page.locator("g.part.lit")).to_have_count(0)
    expect(page.locator('g.part.picked[data-ref="C2"]')).to_have_count(1)
    expect(page.locator('g.part.picked[data-ref="VR1"]')).to_have_count(1)  # Drive, in its feedback
    picked = "(e) => getComputedStyle(e.querySelector('path, line')).stroke"
    u2, lit = page.locator('g.part[data-ref="IC1B"]'), page.locator('g.part[data-ref="Q1"]')
    block(page, "Q1").hover()  # a hover lights over it, in the ordinary colour; IC1B stays
    expect(page.locator('g.part.lit[data-ref="Q1"]')).to_have_count(1)
    expect(page.locator('g.part.picked[data-ref="IC1B"]')).to_have_count(1)
    assert u2.evaluate(picked) != lit.evaluate(picked)
    page.locator("#stages-summary").hover()
    expect(card.locator(".stage-cell").first).to_have_text("Soft held")
    card = open_card(page, "Q1")
    # the 2SC1815's gain (139, the sheet's line) through R2's 510K drops its base to 3.4 V,
    # the emitter to 2.85 V of 9 (centred with the 2N5089's 860, before D-187)
    expect(card.locator(".bias-place")).to_have_text("sits low")
    expect(card.locator(".bias-bar i:not(.aim)")).to_have_count(1)
    expect(card.locator(".card-text")).to_contain_text("of room up")
    assert "unclipped" in (card.locator(".stage-cell").first.get_attribute("title") or "")
    # the RC4558's swing is its datasheet's (D-150): no rule-of-thumb asterisk
    expect(open_card(page, "IC1A").locator(".bias-place sup")).to_have_count(0)
    card = open_card(page, "D1 D2")
    expect(card.locator(".clamp-text")).to_have_text(re.compile(r"^±\d+ mV$"))
    expect(card.locator('.stage-cell[data-level="soft"]')).to_contain_text("driven")
    # no Probe: the Waveform section is the probe (D-127); a second click on the block
    # shuts the card and puts its parts out
    expect(card.locator(".card-probe")).to_have_count(0)
    block(page, "D1 D2").click()
    expect(page.locator("#stage-card")).to_have_count(0)
    page.locator("#stages-summary").hover()
    expect(page.locator("g.part.lit, g.part.picked")).to_have_count(0)


def test_the_big_muff_and_a_change(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    assert labels(page) == ["Q4", "Q3", "D3, D4", "Q2", "D1, D2", "Q1"]
    roles = page.eval_on_selector_all(
        f'{CHAIN}[data-kind="clipper"] .role', "(es) => es.map((e) => e.textContent)"
    )
    assert roles == ["diodes in feedback", "diodes in feedback"]
    # Q4 sits high: lopsided
    expect(block(page, "Q4").locator(".mark")).to_contain_text(["lopsided"])


def test_a_shut_pane_measures_when_opened(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "fuzz-face")
    page.locator("#panel-stages > summary").click()  # shut
    page.goto(f"{base_url}#proco-rat")
    expect(page.locator("#panel-stages")).not_to_have_attribute("open", "")
    page.locator("#panel-stages > summary").click()  # open: measured now
    expect(page.locator(CHAIN)).to_have_count(3, timeout=15_000)
    assert labels(page) == ["IC1", "D1, D2", "Q1"]


def test_the_other_tones_on_demand(page: Page, base_url: str) -> None:
    """D-122: 200 Hz on every change; another tone when picked; Measure all; then the
    worst tone named, each block's worst tone and a card's table by tone. No Auto
    (D-127): a change measures the tone picked."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    tones = page.locator("#stage-tones [data-tone]")
    expect(tones).to_have_text(["100 Hz", "200 Hz", "1 kHz", "3 kHz"])
    expect(page.locator('#stage-tones [data-tone="200"]')).to_have_attribute("aria-checked", "true")
    expect(page.locator("#stage-tones .unmeasured")).to_have_count(3)
    expect(page.locator("#stages-tone-note")).to_have_text("Click a tone to measure it.")
    expect(page.locator("#stage-tones #stages-tone-note")).to_have_count(1)  # right of the chips
    expect(page.locator("#stages-tone-progress")).to_be_hidden()
    u2 = block(page, "IC1B").locator(".block-gain")
    at200 = u2.inner_text()
    page.locator('#stage-tones [data-tone="100"]').click()
    expect(page.locator('#stage-tones [data-tone="100"]')).not_to_have_class(
        re.compile("unmeasured"), timeout=15_000
    )
    expect(u2).not_to_have_text(at200)  # its own gain at 100 Hz: the 720 Hz corner
    page.locator("#stages-measure-all").click()
    # a bar while each tone is measured (D-127), in the note's place, gone when they all are
    expect(page.locator("#stage-tones #stages-tone-progress")).to_be_visible()
    expect(page.locator("#stages-tone-note")).to_be_hidden()
    expect(page.locator("#stage-tones .unmeasured")).to_have_count(0, timeout=60_000)
    expect(page.locator("#stages-tone-progress")).to_be_hidden()
    expect(page.locator("#stages-tone-note")).to_have_text("Measured at every tone.")
    expect(page.locator("#stages-measure-all")).to_be_hidden()
    expect(page.locator("#stages-summary")).to_contain_text(re.compile("Worst at|worst tone"))
    card = open_card(page, "D1 D2")
    expect(card.locator("#stage-tones-table tbody tr")).to_have_count(4)
    expect(card.locator("#stage-tones-table tr.here th")).to_have_text("100 Hz")
    # the tone picked stays through a card, shutting the pane and the large view; another
    # circuit starts at 200 Hz (D-127)
    expect(page.locator('#stage-tones [data-tone="100"]')).to_have_attribute("aria-checked", "true")
    page.locator("#panel-stages > summary").click()  # shut
    page.locator("#panel-stages > summary").click()  # open
    expect(page.locator('#stage-tones [data-tone="100"]')).to_have_attribute("aria-checked", "true")
    expect(page.locator("#stage-tones .unmeasured")).to_have_count(0)
    at3k = page.locator('#stage-tones [data-tone="3000"]')
    at3k.click()
    page.locator("#stages-expand").click()
    expect(at3k).to_have_attribute("aria-checked", "true")
    page.locator("#stages-expand").click()
    expect(at3k).to_have_attribute("aria-checked", "true")
    page.goto(f"{base_url}#big-muff-pi-v3")
    expect(page.locator('#stage-tones [data-tone="200"]')).to_have_attribute("aria-checked", "true")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    expect(page.locator("#stages-tone-note")).to_have_text("Click a tone to measure it.")


def test_pot_chips_sit_where_they_act_and_turn_the_same_knob(page: Page, base_url: str) -> None:
    """D-122: the Rat's Distortion on IC1, its Filter on the arrow into the diodes, Volume
    on the last arrow; a chip opens the Knobs & switches pane's own control, and turning
    either moves both."""
    open_circuit(page, base_url, "proco-rat")
    expect(page.locator(CHAIN)).to_have_count(3, timeout=15_000)
    expect(block(page, "IC1").locator(".pot-chip")).to_have_text(
        [re.compile(r"^Distortion \d+ %$")]
    )
    arrows = page.locator("#stage-chain .chain-arrow")
    expect(arrows).to_have_count(4)  # guitar → IC1 → D1, D2 → Q1 → amp
    expect(arrows.nth(1).locator(".pot-chip")).to_have_text([re.compile(r"^Filter \d+ %$")])
    expect(arrows.nth(3).locator(".pot-chip")).to_have_text([re.compile(r"^Volume \d+ %$")])
    chip = page.locator('.pot-chip[data-pot="VR2"]')
    chip.hover()
    expect(page.locator('g.part.lit[data-ref="VR2"]')).to_have_count(1)
    chip.click()
    # a chip on an arrow opens a card of its own (D-123): where it acts, its knob
    pop = page.locator("#pot-pop")
    expect(pop).to_be_visible()
    expect(page.locator("#pot-card")).to_contain_text("Between IC1 and D1, D2")
    expect(chip).to_have_attribute("aria-expanded", "true")
    expect(page.locator("#stage-card")).to_have_count(0)
    pop.locator('input[data-ref="VR2"]').fill("80")
    expect(page.locator('#knobs-body input[data-ref="VR2"]')).to_have_value("80")
    expect(chip).to_have_text("Filter 80 %")
    # measured again with the knob there: the chip and its control stay
    page.wait_for_timeout(1500)
    expect(page.locator('.pot-chip[data-pot="VR2"]')).to_have_text("Filter 80 %")
    expect(pop.locator('input[data-ref="VR2"]')).to_have_value("80")
    # the Knobs pane's knob moves the chip's too
    page.locator('#knobs-body input[data-ref="VR2"]').fill("20")
    expect(pop.locator('input[data-ref="VR2"]')).to_have_value("20")
    expect(page.locator('.pot-chip[data-pot="VR2"]')).to_have_text("Filter 20 %")
    # the card holds one thing: IC1's card has its own knob, not the Filter
    block(page, "IC1").click()
    expect(page.locator("#pot-card")).to_have_count(0)
    expect(pop.locator("input[data-ref]")).to_have_count(1)
    expect(pop.locator('input[data-ref="VR1"]')).to_be_visible()
    # a chip on a block opens that block's card; clicking an arrow's chip twice shuts it
    block(page, "IC1").click()
    expect(page.locator("#stages-card-body")).to_be_hidden()
    page.locator('.pot-chip[data-pot="VR1"]').click()
    expect(page.locator('#stage-card[data-refs="IC1"]')).to_be_visible()
    # every chip toggles, a block's too (Phase 8d: Distortion on the TS808's IC1B didn't)
    page.locator('.pot-chip[data-pot="VR1"]').click()
    expect(page.locator("#stages-card-body")).to_be_hidden()
    page.locator('.pot-chip[data-pot="VR2"]').click()
    expect(page.locator("#pot-card")).to_be_visible()
    page.locator('.pot-chip[data-pot="VR2"]').click()
    expect(page.locator("#stages-card-body")).to_be_hidden()


def test_cell_wording(js: Page) -> None:
    out = run(
        js,
        """
      const s = await m('stages-logic.js');
      const stage = {kind: 'stage', state: null};
      const clipper = {kind: 'clipper', state: null};
      return [
        s.cellText(stage, {headroom_db: 12.4}), s.cellText(stage, {headroom_db: 3.2}),
        s.cellText(stage, {headroom_db: -4.6}), s.cellText(stage, {headroom_db: -2, held: true}),
        s.cellText(stage, {headroom_db: null}),
        s.cellText({...stage, state: 'Q1 is saturated'}, {headroom_db: 5}),
        s.cellText(clipper, {drive_db: 9.4, clips: true}),
        s.cellText(clipper, {drive_db: 0.4, clips: false}),
        s.biasMark({bias: {position: 0.5, place: 'centred'}, state: null}),
        s.biasMark({bias: {position: 1.3, place: 'sits high'}, state: null}),
        s.biasMark({bias: {position: 0.2, place: 'sits low'}, state: 'saturated'}),
        s.roleText({kind: 'clipper', role: 'to ground', net: 'clip'}),
        s.clipperText({clamp: {text: 'Clamps at ±450 mV across it (hard pick).'},
                       levels: {hard: {harmonics: 'odd'}}}),
      ];
    """,
    )
    assert out == [
        {"text": "12 dB spare", "tone": "ok"},
        {"text": "3 dB spare", "tone": "near"},
        {"text": "over by 5 dB", "tone": "over"},
        {"text": "held", "tone": "held"},
        {"text": "no signal", "tone": "off"},
        {"text": "—", "tone": "off"},  # a saturated stage's readings mean little
        {"text": "driven 9 dB", "tone": "clip"},
        {"text": "not clipping", "tone": "ok"},
        {"at": 50, "tone": "ok"},
        {"at": 100, "tone": "near"},  # held to the bar
        {"at": 20, "tone": "over"},
        "clipper to ground · clip",
        "Clamps at ±450 mV across it (hard pick). "
        "Mostly odd harmonics (3rd, 5th): it clips both ways alike.",
    ]


def test_chain_wording(js: Page) -> None:
    out = run(
        js,
        """
      const s = await m('stages-logic.js');
      const cell = (o) => ({clips: false, ...o});
      const clipper = (role, even, clips) => ({kind: 'clipper', role, state: null,
        clamp: {even}, levels: {hard: cell({clips, drive_db: 9})}});
      const stage = (place, headroom) => ({kind: 'stage', role: 'gain stage', state: null,
        bias: {place}, levels: {hard: cell({clips: headroom < 0, headroom_db: headroom})}});
      const marks = (r) => s.blockMarks(r).map((m) => `${m.text}:${m.tone}`);
      const data = (rows, first) => ({rows, summary: '', note: null, picks: {}, tone: 0,
                                      settled: true, first});
      // a row per tone: the clipper driven hardest at 3 kHz
      const by = new Map([[100, data([clipper('to ground', true, false)])],
                          [200, data([clipper('to ground', true, true)])],
                          [1000, data([clipper('to ground', true, true)])],
                          [3000, data([{...clipper('to ground', true, true),
                                         levels: {hard: cell({clips: true, drive_db: 15})}}])]]);
      return {
        marks: [marks(clipper('to ground', true, true)),
                marks(clipper('in feedback', false, false)),
                marks(clipper('in series', true, false)), marks(stage('centred', 4)),
                marks(stage('sits high', -3))],
        role: [s.blockRole(clipper('to ground', true, false)), s.blockRole(stage('centred', 1))],
        db: [s.signedDb(38.4), s.signedDb(-6.2), s.signedDb(0.3)],
        names: [s.toneName(1000), s.toneName(3000), s.toneName(200)],
        rowWorst: s.rowWorst(by, 0), one: s.rowWorst(new Map([[200, by.get(200)]]), 0),
        worst: s.worstTone(by), partial: s.worstTone(new Map([[200, by.get(200)]])),
        settled: [s.settledText({settled: true}), s.settledText({settled: false}),
                  s.settledText({settled: null})],
        spots: [s.chipSpot({at: 'block', index: 1}, 3), s.chipSpot({at: 'arrow', index: -1}, 3),
                s.chipSpot({at: 'arrow', index: 0}, 3), s.chipSpot({at: 'end', index: -1}, 3)],
        where: [{at: 'block', index: 0}, {at: 'arrow', index: -1}, {at: 'arrow', index: 0},
                {at: 'end', index: -1}].map((p) => s.potWhere(p, [{label: 'U1'}, {label: 'Q1'}])),
      };
    """,
    )
    assert out["marks"] == [
        ["hard:clip"],
        ["soft:ok", "lopsided:near"],  # an uneven pair
        ["in series:ok"],
        [],
        ["clips:over", "lopsided:near"],  # out of room at a hard pick, biased high
    ]
    assert out["role"] == ["diodes to ground", "gain stage"]
    assert out["db"] == ["+38 dB", "\u22126 dB", "0 dB"]
    assert out["names"] == ["1 kHz", "3 kHz", "200 Hz"]
    assert out["rowWorst"] == 3000 and out["one"] is None
    # 200 Hz clips from a hard pick as the others do (100 Hz doesn't): driven most at 3 kHz
    assert out["worst"] == 3000 and out["partial"] is None
    assert out["settled"][0] is None
    assert out["settled"][1].startswith("Still settling after 0.4 s")
    assert "oscillator of its own" in out["settled"][2]
    # the arrows: 0 after the guitar, 3 into the amp (where a pot at the end goes)
    assert out["spots"] == [{"block": 1}, {"arrow": 0}, {"arrow": 1}, {"arrow": 3}]
    assert out["where"][0].startswith("On U1: it sets how much it amplifies")
    assert out["where"][1].startswith("Between the guitar and U1")
    assert out["where"][2].startswith("Between U1 and Q1: it sets what Q1 gets")
    assert out["where"][3].startswith("After the last stage")


def test_the_level_diagram_and_curve_data(js: Page) -> None:
    out = run(
        js,
        """
      const s = await m('stages-logic.js');
      const cell = (up, predicted) => ({up, down: up / 2, predicted});
      const levels = (k) => ({soft: cell(0.1 * k, 0.1 * k), med: cell(0.3 * k, 0.3 * k),
                              hard: cell(1, 1 * k)});
      const data = {picks: {soft: 0.1, med: 0.3, hard: 1}, summary: '', note: null, rows: [
        {label: 'Q1', net: 'a', state: null, levels: levels(10), limit: 1},
        {label: 'D1, D2', net: 'a', state: null, levels: levels(10), limit: 0.5},
        {label: 'Q2', net: 'b', state: 'saturated', levels: levels(1), limit: null},
      ]};
      const d = s.levelDiagram(data);
      const lit = s.levelCurve(data.rows, [{amplitude: 1, rows: [{net: 'a', peak: 1}]}], 'a');
      const curve = s.levelCurve(data.rows, [
        {amplitude: 1, rows: [{net: 'a', peak: 1}, {net: 'b', peak: 0.1}]},
        {amplitude: 0.01, rows: [{net: 'a', peak: 0.1}, {net: 'b', peak: 0.01}]},
      ]);
      return {
        x: d.x, names: d.xText, labels: d.series.map((x) => x.label),
        hard: d.series[4].values, hardUnclipped: d.series[5].values, limit: d.series[6].values,
        dashed: d.series.map((x) => !!x.dash),
        curveX: curve.x, curveLabels: curve.series.map((x) => x.label),
        guitar: curve.series[0].values, first: curve.series[1].values,
        sweep: [s.SWEEP_LEVELS.length, s.SWEEP_LEVELS[0], s.SWEEP_LEVELS[11]],
        picks: s.pickLines(data.picks).map((l) => l.label),
        bold: lit.series.map((x) => !!x.bold),
        none: [s.dbv(0), s.dbv(null), s.dbv(Infinity)],
      };
    """,
    )
    assert out["x"] == [0, 1, 2, 3]
    assert out["names"] == ["Guitar", "Q1", "D1, D2", "Q2"]
    assert out["labels"] == ["Soft", "Soft, unclipped", "Medium", "Medium, unclipped",
                             "Hard", "Hard, unclipped", "Limit"]  # fmt: skip
    # dBV: the guitar's hard pick is 1 V (0 dBV); the saturated row has no points
    assert out["hard"] == [0, 0, 0, None]
    assert out["hardUnclipped"][:3] == [0, pytest.approx(20), pytest.approx(20)]
    assert out["limit"] == [None, 0, pytest.approx(-6.02, abs=0.01), None]
    assert out["dashed"] == [False, True, False, True, False, True, False]
    # sorted by the guitar's level; a clipper and its stage share a line
    assert out["curveX"] == [-40, 0]
    assert out["curveLabels"] == ["Guitar", "Q1 · D1, D2", "Q2"]
    assert out["guitar"] == [-40, 0] and out["first"] == [-20, 0]
    assert out["sweep"][0] == 12
    assert out["sweep"][1] == pytest.approx(0.003) and out["sweep"][2] == pytest.approx(3)
    assert out["picks"] == ["Soft pick", "Medium pick", "Hard pick"]
    assert out["bold"] == [False, True, False]  # the hovered row's line
    assert out["none"] == [None, None, None]


def test_the_large_view_draws_the_diagram_then_the_curve(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    expect(page.locator("#stages-main")).to_be_hidden()  # no chart in the panel
    page.locator("#stages-expand").click()
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    expect(page.locator("#stages-plot canvas")).to_have_count(1)
    points = "() => document.getElementById('stages-plot')._plot.data[0].length"
    assert page.evaluate(points) == 6  # the guitar and five blocks
    # the chain sits beside the chart
    plot, rows = (
        page.locator("#stages-plot").bounding_box(),
        page.locator("#stages-side").bounding_box(),
    )
    assert plot and rows and rows["x"] > plot["x"] + plot["width"] - 1
    page.locator('[data-stages-chart="curve"]').click()
    expect(page.locator("#stages-progress")).to_contain_text("of 12 levels")
    expect(page.locator("#stages-progress progress")).to_be_visible()  # a bar fills as it goes
    page.wait_for_function(f"({points})() === 12", timeout=30_000)
    expect(page.locator("#stages-progress")).to_be_hidden()
    # measured once: back and forth draws it at once
    page.locator('[data-stages-chart="diagram"]').click()
    page.locator('[data-stages-chart="curve"]').click()
    assert page.evaluate(points) == 12
    expect(page.locator("#stages-progress")).to_be_hidden()
    page.keyboard.press("Escape")  # shrinks it to its bar (D-123)
    page.wait_for_function("() => !document.querySelector('#panel-stages').open")
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))


def test_the_large_view_puts_the_chain_over_the_charts(page: Page, base_url: str) -> None:
    """D-122, Phase 8d: expanded, the chain is a strip over the chart, framed, centred and
    laid out the same over both charts; the side column keeps the summary and the card."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    expect(page.locator("#stage-strip-chain")).to_have_count(0)
    page.locator("#stages-expand").click()
    strip = page.locator("#stage-strip-chain .chain-block")
    expect(strip).to_have_count(5)
    expect(page.locator("#stage-chain")).to_be_hidden()
    expect(page.locator("#stages-summary")).to_be_visible()
    frame = page.locator("#stage-strip")
    assert frame.evaluate("(e) => getComputedStyle(e).borderTopStyle") == "solid"

    def boxes() -> list[dict[str, float]]:
        # the strip is drawn again when a measuring comes back: read it once it holds still
        for _ in range(40):
            out = [strip.nth(i).bounding_box() for i in range(5)]
            if all(out):
                return [b for b in out if b]
            page.wait_for_timeout(50)
        raise AssertionError("the strip's five blocks were never all drawn at once")

    def centred() -> None:  # as much room left of the guitar as right of the amp
        ends = page.locator("#stage-strip-chain .chain-end")
        f, g, a = frame.bounding_box(), ends.nth(0).bounding_box(), ends.nth(1).bounding_box()
        assert f and g and a
        assert abs((g["x"] - f["x"]) - (f["x"] + f["width"] - a["x"] - a["width"])) < 4

    centred()
    # an arrow has a head: wider than a hairline, and drawn (not a text glyph)
    glyph = page.locator("#stage-strip-chain .arrow-glyph").first
    assert glyph.inner_text() == ""
    head = glyph.evaluate("(e) => getComputedStyle(e, '::after').borderLeftWidth")
    assert float(head.removesuffix("px")) >= 6
    over_diagram = boxes()
    # a click opens the card in the side column; the strip stays put
    block(page, "IC1A").click()
    expect(page.locator("#stage-card")).to_be_visible()
    assert boxes() == over_diagram
    # a tone being measured greys the chart and the strip
    page.locator('#stage-tones [data-tone="1000"]').click()
    expect(page.locator("#stages-body")).to_have_attribute("data-loading", "true")
    expect(page.locator("#stages-plot canvas").first).to_be_visible()
    expect(page.locator("#stages-body")).not_to_have_attribute(
        "data-loading", "true", timeout=15_000
    )
    over_diagram = boxes()  # at 1 kHz: its words differ
    # over the curve the same layout, each block in its line's colour
    page.locator('[data-stages-chart="curve"]').click()
    expect(page.locator("#stage-strip-chain")).to_have_class(re.compile("keyed"))
    expect(page.locator("#stages-progress")).to_be_hidden(timeout=30_000)
    centred()
    # nothing moves or changes size between the charts (round 2): the line is a shadow
    for got, was in zip(boxes(), over_diagram, strict=True):
        assert got == pytest.approx(was, abs=0.5)
    colour = "(e) => getComputedStyle(e).boxShadow"
    assert strip.nth(0).evaluate(colour) != strip.nth(4).evaluate(colour)
    # a line hidden in the legend fades its block, and back (round 2)
    first = strip.nth(0)
    label = first.get_attribute("data-line")
    assert label
    key = page.locator("#stages-plot .u-legend .u-series").filter(
        has_text=re.compile(rf"^\s*{re.escape(label)}\s*$")
    )
    key.click()
    expect(first).to_have_class(re.compile("line-off"))
    expect(strip.nth(4)).not_to_have_class(re.compile("line-off"))
    key.click()
    expect(first).not_to_have_class(re.compile("line-off"))
    key.click()
    page.locator('[data-stages-chart="diagram"]').click()
    expect(page.locator("#stage-strip-chain")).not_to_have_class(re.compile("keyed"))
    assert first.evaluate(colour) == "none"
    expect(first).not_to_have_class(re.compile("line-off"))  # the diagram has no legend
    page.locator('[data-stages-chart="curve"]').click()
    expect(first).to_have_class(re.compile("line-off"))  # still hidden on the curve
    page.locator('[data-stages-chart="diagram"]').click()


def test_the_big_muffs_strip_stays_inside_its_pane(page: Page, base_url: str) -> None:
    """Phase 8d: the Big Muff's Volume chip ran over the right pane when the strip lined
    up with the diagram's columns."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    page.locator("#stages-expand").click()
    frame = page.locator("#stage-strip").bounding_box()
    assert frame
    for chip in page.locator("#stage-strip-chain .pot-chip").all():
        box = chip.bounding_box()
        assert (
            box
            and frame["x"] <= box["x"]
            and box["x"] + box["width"] <= frame["x"] + frame["width"]
        )


def test_hovering_a_block_lights_its_place_on_the_charts(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    page.locator("#stages-expand").click()
    bands = "() => document.getElementById('stages-plot')._plot.marks.bands"
    block(page, "IC1A").hover()  # the 4th block: x = 4
    assert page.evaluate(bands) == [{"lo": pytest.approx(3.6), "hi": pytest.approx(4.4)}]
    page.locator("#stages-summary").hover()
    assert page.evaluate(bands) == []
    page.locator('[data-stages-chart="curve"]').click()
    points = "() => document.getElementById('stages-plot')._plot.data[0].length"
    page.wait_for_function(f"({points})() === 12", timeout=30_000)
    widths = (
        "() => document.getElementById('stages-plot')._plot.series.slice(1).map((s) => s.width)"
    )
    plain = page.evaluate(widths)
    block(page, "IC1A").hover()
    lit = page.evaluate(widths)
    labels = page.evaluate(
        "() => document.getElementById('stages-plot')._plot.series.map((s) => s.label)"
    )
    i = labels.index("IC1A") - 1
    assert lit[i] > plain[i] and [w for k, w in enumerate(lit) if k != i] == [
        w for k, w in enumerate(plain) if k != i
    ]


def test_the_explanations_are_behind_the_info_button(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    # the panes that explain something have one, right after their name; the others don't
    for pane in (
        "panel-frequency",
        "panel-stages",
        "panel-scope",
        "panel-harmonics",
        "panel-audio",
    ):
        expect(page.locator(f"#{pane} > summary .info-button")).to_have_count(1)
    for pane in ("panel-problems", "panel-dc", "panel-probe", "panel-knobs"):
        expect(page.locator(f"#{pane} > summary .info-button")).to_have_count(0)
    # no explanations in the panes themselves
    expect(page.locator("#stages-body .note")).to_have_count(0)
    # a click opens it without shutting the pane; a click elsewhere closes it
    page.locator("#panel-stages > summary .info-button").click()
    pop = page.locator(".info-pop:not([hidden])")
    expect(pop).to_contain_text("The chain: each stage and clipper")
    expect(pop).to_contain_text("A solid bar on its left: it clips at a hard pick")
    expect(pop).not_to_contain_text("Find diodes")  # that's Try changes' own ⓘ (D-127)
    expect(pop).not_to_contain_text("Level diagram")  # no chart in the panel
    expect(page.locator("#panel-stages")).to_have_attribute("open", "")
    page.locator("#stages-summary").click()
    expect(pop).to_have_count(0)
    # a shut pane keeps its ⓘ (the user) and its Expand, which opens it large (D-110)
    page.locator("#panel-harmonics > summary").click()
    expect(page.locator("#panel-harmonics")).not_to_have_attribute("open", "")
    assert "overtones" in info_text(page, "panel-harmonics")
    expect(page.locator("#panel-harmonics")).not_to_have_attribute(
        "open", ""
    )  # the ⓘ didn't open it
    page.locator("#panel-stages > summary").click(position={"x": 60, "y": 10})  # shut
    page.locator("#panel-stages > summary #stages-expand").click()
    expect(page.locator("#panel-stages")).to_have_attribute("open", "")
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    # large, Collapse is at the title bar's far right, where a shrunk bar's is (round 3)
    collapse = page.locator("#panel-stages > summary > #stages-expand")
    expect(collapse).to_have_text("Collapse")
    expect(page.locator("#stages-tools #stages-expand")).to_have_count(0)
    bar = page.locator("#panel-stages > summary").bounding_box()
    at = collapse.bounding_box()
    assert bar and at and bar["x"] + bar["width"] - (at["x"] + at["width"]) < 16
    collapse.click()
    expect(page.locator("#panel-stages > summary #stages-expand")).to_have_text("Expand")
    # in the large view it's in the title bar and says what the chart shows; Esc closes it
    # and leaves the large view open
    page.locator("#stages-expand").click()
    text = info_text(page, "panel-stages")
    assert "Level diagram" in text and "The dots are each stage's limit" in text
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    # Try changes has its own ⓘ, one pop-up however often its box is drawn (D-127)
    open_card(page, "Q1")
    open_card(page, "IC1A")
    page.locator("#try-changes .info-button").click()
    pop = page.locator(".info-pop:not([hidden])")
    expect(pop).to_contain_text("Centre, on a stage that sits high or low")
    expect(pop).to_contain_text("Find diodes measures each kind")
    page.keyboard.press("Escape")
    expect(pop).to_have_count(0)
    expect(page.locator('.info-pop[aria-label="About Try changes"]')).to_have_count(1)
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    page.locator('[data-stages-chart="curve"]').click()
    assert "Where a line bends flat" in info_text(page, "panel-stages")
    # shrunk to its bar (another large view opened), no ⓘ
    page.locator("#frequency-expand").click()
    expect(page.locator("#panel-stages > summary .info-button")).to_be_hidden()
    # Frequency's says what's on screen: the curve, then Edit curve while editing
    assert "small-signal curve" in info_text(page, "panel-frequency")
    page.locator("#frequency-edit").click()
    assert "Drag a dot sideways" in info_text(page, "panel-frequency")
    expect(page.locator("#panel-frequency")).to_have_class(re.compile("large-view"))
    expect(page.locator("#frequency-layers .note")).to_have_count(0)


def test_centre_tries_a_resistor_and_keeps_or_discards_it(page: Page, base_url: str) -> None:
    """D-119, D-123: the Big Muff's Q4 sits high; Centre in its card lists resistor values;
    Try puts one in, in Try changes' session (in History), and the card reads centred;
    Discard changes in the top bar puts it back without measuring again."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    card = open_card(page, "Q4")
    expect(card.locator(".bias-place")).to_have_text("sits high")
    # in the panel, Try changes takes you to the large view, where the fixes are (D-122)
    card.locator(".try-changes").click()
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    # only a stage off centre offers Centre
    expect(open_card(page, "Q3").locator(".centre-button")).to_have_count(0)
    card = open_card(page, "Q4")
    card.locator(".centre-button").click()
    box = page.locator("#fix-box")
    first = box.locator(".fix-option").first
    expect(first).to_contain_text("Q4 centred", timeout=15_000)
    expect(page.locator("#probe-body")).not_to_contain_text("Q4")  # Centre isn't a probe
    expect(page.locator("#stages-keep")).to_be_hidden()  # nothing tried yet
    first.locator("button").click()
    expect(card.locator(".bias-place")).to_have_text("centred", timeout=15_000)
    expect(first.locator("button")).to_have_text("Trying")
    expect(page.locator("#try-changes-list")).to_contain_text("\N{RIGHTWARDS ARROW}")
    collapse = page.locator("#panel-stages > summary > #stages-expand")
    expect(collapse).to_be_disabled()  # Keep or Discard first
    page.locator("#history-button").click()
    pane = page.locator("#history-pane")
    expect(pane.locator(".history-heading").first).to_have_text("Bias & headroom (in progress)")
    page.locator("#history-button").click()
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url) if r.url.endswith("/api/stages") else None)
    page.locator("#stages-discard").click()
    expect(card.locator(".bias-place")).to_have_text("sits high", timeout=15_000)
    expect(box).to_have_count(0)
    expect(page.locator("#try-changed")).to_be_hidden()
    page.wait_for_timeout(500)
    assert asked == []  # the chain from before, not measured again
    expect(collapse).to_be_enabled()


def test_try_changes_over_many_blocks_is_one_step(page: Page, base_url: str) -> None:
    """D-123: Try on one block, then another; Changed lists both, ↺ puts one back, the
    level diagram shows the chain as it was (faint, Before turns it off); Keep changes
    makes one History step naming every part."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    page.locator("#stages-expand").click()
    card = open_card(page, "Q4")
    card.locator(".centre-button").click()
    box = page.locator("#fix-box")
    box.locator(".fix-option").first.locator("button").click(timeout=15_000)
    expect(card.locator(".bias-place")).to_have_text("centred", timeout=15_000)
    faint = (
        "() => document.getElementById('stages-plot')._plot.series"
        ".filter((s) => s.label === 'Before').length"
    )
    page.wait_for_function(f"({faint})() === 3")  # one per pick
    keys = page.locator("#stages-plot .u-legend .u-series:visible", has_text="Before")
    expect(keys).to_have_count(1)  # one legend entry for them all
    page.locator("#stages-before").click()
    page.wait_for_function(f"({faint})() === 0")
    page.locator("#stages-before").click()
    # another block: Q4's change stays in
    card = open_card(page, "D3 D4")
    card.locator("#diode-find").click()
    led = box.locator(
        '.fix-option[data-option="D3, D4 \N{RIGHTWARDS ARROW} APT1608SURCK (red LED)"]'
    )
    led.locator("button").click(timeout=15_000)
    items = page.locator("#try-changes-list li")
    expect(items.filter(has_text="APT1608SURCK")).to_have_count(2, timeout=15_000)
    refs = items.evaluate_all("els => els.map((e) => e.dataset.ref)")
    assert refs[-2:] == ["D3", "D4"] and len(refs) >= 3
    # ↺ puts D4 back alone: a diode again, not an LED with a diode's model
    items.filter(has_text="D4").locator(".put-back").click()
    expect(items.filter(has_text="D4")).to_have_count(0, timeout=15_000)
    expect(led.locator("button")).to_have_text("Try")  # D4 isn't an LED now
    # an LED and a 1N4148 now: the pair clips lopsided
    expect(block(page, "D3 D4").locator(".mark")).to_contain_text(["lopsided"], timeout=15_000)
    page.locator("#stages-keep").click()
    expect(page.locator("#try-changed")).to_be_hidden()
    page.locator("#history-button").click()
    expect(page.locator("#history-pane .history-step.current")).to_have_text(
        "Bias & headroom: " + ", ".join(refs[:-1])
    )


def test_diode_arrangements_add_parts_and_take_them_out(page: Page, base_url: str) -> None:
    """D-124: on the Rat, Find diodes also offers two in series, 2 + 1 and a resistor in
    series (to ground). Trying one adds its parts beside the diodes; trying another in
    the same box takes them out first; ↺ on an added part takes out all it came with;
    Discard leaves the circuit as it was."""
    open_circuit(page, base_url, "proco-rat")
    expect(page.locator(CHAIN).first).to_be_visible(timeout=15_000)
    page.locator("#stages-expand").click()
    card = open_card(page, "D1 D2")
    expect(card.locator('[data-try-line="clipper"]')).to_contain_text("a resistor in series")
    card.locator("#diode-find").click()
    box = page.locator("#fix-box")
    resistor = box.locator(".fix-option", has_text="2k2 in series")
    resistor.locator("button").click(timeout=30_000)
    items = page.locator("#try-changes-list li")
    expect(items).to_have_text(
        [
            "R13 added: 2k2 \N{ANTICLOCKWISE OPEN CIRCLE ARROW}",
            "R14 added: 2k2 \N{ANTICLOCKWISE OPEN CIRCLE ARROW}",
        ],
        timeout=15_000,
    )
    expect(resistor.locator("button")).to_have_text("Trying")
    expect(box.locator(".fix-option", has_text="1k in series").locator("button")).to_have_text(
        "Try"
    )
    doubled = box.locator(".fix-option", has_text="Two in series")
    doubled.locator("button").click()
    expect(items).to_have_count(2, timeout=15_000)
    expect(items.first).to_contain_text("D3 added: 1N4148")
    expect(page.locator('g.part[data-ref="R13"]')).to_have_count(0)
    expect(page.locator('g.part[data-ref="D4"]')).to_have_count(1)
    items.first.locator(".put-back").click()  # D3 out takes D4 with it
    expect(page.locator("#try-changes-list")).to_have_text("Nothing changed now.", timeout=15_000)
    expect(page.locator('g.part[data-ref="D4"]')).to_have_count(0)
    resistor.locator("button").click()
    expect(items).to_have_count(2, timeout=15_000)
    page.locator("#stages-discard").click()
    expect(page.locator("#try-changed")).to_be_hidden()
    expect(page.locator('g.part[data-ref="R13"]')).to_have_count(0)


def cramped_rat() -> dict[str, Any]:
    """The Rat with its diodes on a ground wire and a cap tucked under each: no room
    beside them for a part in series (D-124)."""
    c = json.loads((REPO / "library" / "starters" / "proco-rat.json").read_text())
    c["starter"] = False
    c["labels"] = [lb for lb in c["labels"] if lb["pos"] not in ([530, 40], [650, 40])]
    c["wires"].append({"from": [530, 40], "to": [690, 40]})
    c["labels"] += [{"net": "GND", "pos": [690, 40]}]
    for ref, x in (("C20", 530), ("C21", 650)):
        c["parts"].append({"ref": ref, "type": "capacitor", "value": "100n", "pos": [x, 70]})
        c["labels"] += [{"net": "GND", "pos": [x - 20, 70]}, {"net": "GND", "pos": [x + 20, 70]}]
    return c


def test_room_is_made_for_an_arrangement_and_said_so(page: Page, base_url: str) -> None:
    """D-124: where there's no room beside the diodes, the option says it makes room
    first and what it moves; trying it is two History steps (the room, then the parts),
    Changed has a line for the room that lights what moved, and ↺ on it puts the parts
    back where they were."""
    page.goto(base_url)
    saved = page.request.post(
        f"{base_url}api/circuits", data={"circuit": cramped_rat(), "name": "Cramped Rat"}
    )
    open_circuit(page, base_url, "circuit/" + saved.json()["circuit"]["id"])
    expect(page.locator(CHAIN).first).to_be_visible(timeout=15_000)
    c20 = part_pos(page, "C20")
    page.locator("#stages-expand").click()
    open_card(page, "D1 D2").locator("#diode-find").click()
    doubled = page.locator("#fix-box .fix-option", has_text="Two in series")
    expect(doubled.locator(".room-note")).to_have_text(
        re.compile(r"Makes room first: moves C20, C21 and \d+ others down\."), timeout=30_000
    )
    doubled.locator("button").click()
    room = page.locator("#try-changes-list li.room-made")
    expect(room).to_have_text(re.compile(r"Moved .* down to make room"), timeout=15_000)
    assert part_pos(page, "C20")[1] == c20[1] + 40
    page.locator("#history-button").click()
    steps = page.locator("#history-pane .history-step")
    expect(steps.filter(has_text="Made room for D3, D4: moved")).to_have_count(1)
    expect(steps.filter(has_text="Diodes D1, D2: Two in series")).to_have_count(1)
    page.locator("#history-button").click()
    room.hover()  # lights what moved
    expect(page.locator('g.part.lit[data-ref="C20"]')).to_have_count(1)
    room.locator(".put-back").click()
    expect(page.locator("#try-changes-list")).to_have_text("Nothing changed now.", timeout=15_000)
    assert part_pos(page, "C20") == c20
    expect(page.locator('g.part[data-ref="D3"]')).to_have_count(0)


def test_bias_to_by_dragging_the_mark(page: Page, base_url: str) -> None:
    """D-123: in the large view a stage's bias mark drags; the aim's volts show while it
    moves, and letting go lists what puts it there; Try moves the stage there."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    page.locator("#stages-expand").click()
    card = open_card(page, "Q4")
    bar = card.locator(".bias-bar.aimable")
    box = bar.bounding_box()
    assert box
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] * 0.6, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.3, y, steps=5)
    expect(page.locator("#bias-aim")).to_contain_text("Aim: ")
    page.mouse.up()
    fix = page.locator("#fix-box")
    expect(fix.locator(".fix-title")).to_have_text("Bias Q4")
    first = fix.locator(".fix-option").first
    expect(first).to_contain_text("Q4 sits low", timeout=15_000)
    expect(card.locator(".bias-bar i.aim")).to_be_visible()  # the aim stays drawn
    first.locator("button").click()
    expect(card.locator(".bias-place")).to_have_text("sits low", timeout=15_000)
    page.locator("#stages-discard").click()
    expect(card.locator(".bias-place")).to_have_text("sits high", timeout=15_000)


def test_the_bias_bar_shows_how_far_it_can_go(page: Page, base_url: str) -> None:
    """D-123: the hatched ends of a stage's bias bar are what no part next to it reaches;
    the TS808's IC1A, biased from the shared reference, can't be aimed at all."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    page.locator("#stages-expand").click()
    card = open_card(page, "IC1A")
    expect(card.locator("#bias-reach")).to_contain_text("Can't be aimed. An op-amp's output sits")
    expect(card.locator(".bias-bar.aimable")).to_have_count(0)
    page.locator("#stages-expand").click()
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    page.locator("#stages-expand").click()
    card = open_card(page, "Q4")
    expect(card.locator(".bias-bar .out-of-reach")).to_have_count(1)  # below about 13 %
    expect(card.locator("#bias-reach")).to_contain_text(
        "hatched ends are more than one part change can reach"
    )
    bar = card.locator(".bias-bar.aimable")
    expect(bar).to_have_attribute("aria-valuemin", re.compile(r"^1\d$"))
    # its ends in volts under it: what it sets is the output's DC
    expect(card.locator(".bias-scale")).to_have_text(re.compile(r"^\d+\.\d+ Voutput DC\d+\.\d+ V$"))
    bar.focus()
    for _ in range(20):
        page.keyboard.press("ArrowLeft")
    low = int(bar.get_attribute("aria-valuenow") or 0)
    assert 10 <= low <= 16  # the aim stops at the edge of what's reached


def test_gain_and_diode_swaps(page: Page, base_url: str) -> None:
    """D-123, D-125: Gain gives a slider for each part that sets a stage's gain, read as it
    moves and tried when let go; a capacitor opens Edit curve instead. Find diodes
    measures each kind; Try and Keep changes as for Centre."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    page.locator("#stages-expand").click()
    card = open_card(page, "IC1B")
    card.locator("#gain-find").click()
    fix = page.locator("#fix-box")
    expect(fix.locator(".fix-title")).to_have_text("Gain IC1B")
    r6 = fix.locator('.gain-part[data-part="R6"]')
    expect(r6.locator(".gain-bar")).to_be_visible(timeout=20_000)
    expect(r6.locator(".gain-value")).to_have_text("51k")
    # S marks where a soft pick starts clipping, the bar tinted from there up (D-127)
    expect(r6.locator(".clip-mark.clip-soft")).to_have_text("S")
    zone = r6.locator(".clip-zone.clip-soft")
    expect(zone).to_have_count(1)
    assert zone.evaluate("(e) => e.style.right") == "0px"
    expect(r6.locator(".gain-ends")).to_have_text(re.compile(r"^\u2212\d+ dBinto IC1A\+\d+ dB$"))
    expect(fix.locator('.gain-part[data-part="C3"] [data-edit-curve="C3"]')).to_be_visible()
    # the arrow keys read each value at once, nothing tried
    bar = r6.locator(".gain-bar")
    bar.focus()
    for _ in range(2):  # 51k (its own) → 56k → 68k: E12 (D-127)
        page.keyboard.press("ArrowRight")
    expect(r6.locator(".gain-value")).to_have_text("68k")
    expect(r6.locator(".gain-text")).to_contain_text("R6 68k: gain +")
    expect(r6.locator(".gain-chain")).to_contain_text("Clips first: D1, D2")
    expect(page.locator("#stages-keep")).to_be_hidden()
    gain = block(page, "IC1B").locator(".block-gain").inner_text()
    page.keyboard.press("Enter")  # tried: measured, and in Changed
    expect(page.locator("#try-changes-list")).to_contain_text("R6 51k \u2192 68k", timeout=15_000)
    expect(block(page, "IC1B").locator(".block-gain")).not_to_have_text(gain, timeout=15_000)
    expect(r6.locator(".gain-value")).to_have_text("68k")
    page.locator("#stages-discard").click()
    card = open_card(page, "D1 D2")
    expect(page.locator("#fix-box")).to_have_count(0)  # the gain box was IC1B's
    card.locator("#diode-find").click()
    led = fix.locator('.fix-option[data-option="D1, D2 \u2192 APT1608SURCK (red LED)"]')
    expect(led).to_contain_text("clamps at ±1.", timeout=15_000)
    led.locator("button").click()
    expect(block(page, "D1 D2").locator(".block-gain")).to_have_text(
        re.compile(r"^±1\.\d+ V$"), timeout=15_000
    )
    page.locator("#stages-keep").click()
    page.locator("#history-button").click()
    expect(page.locator("#history-pane .history-step.current")).to_have_text(
        "Bias & headroom: D1, D2"
    )


def test_fix_logic(js: Page) -> None:
    out = run(
        js,
        """
      const s = await m('stages-logic.js');
      const stage = (place, state = null) => ({kind: 'stage', state, bias: {place}});
      const r9 = {set: {R9: {value: '270k'}}, undo: {R9: {value: '470k'}}, label: 'R9 470k → 270k'};
      const r14 = {set: {R14: {value: '91k'}}, undo: {R14: {value: '47k'}}, label: 'R14 47k → 91k'};
      const hold = {set: {TR1: {rotation: 0.6, bias_target: {node: 'Q1.D', volts: 6}}},
                    undo: {TR1: {rotation: 0.5, bias_target: null}}, label: 'hold'};
      const turn = {set: {TR1: {rotation: 0.6}}, undo: {TR1: {rotation: 0.5}}, label: 'turn'};
      const bias = {v: 4, up: 5, down: 4};
      const start = {parts: [{ref: 'R9', value: '470k'}, {ref: 'R14', value: '47k'},
                             {ref: 'TR1', value: '25k', rotation: 0.5}]};
      return [
        s.canCentre(stage('sits high')), s.canCentre(stage('centred')),
        s.canCentre(stage('centred', 'Q1 is saturated')),
        s.canCentre({kind: 'clipper', state: null}),
        s.tryPatches(null, r9, start), s.tryPatches(r9, r14, start), s.tryPatches(r9, r9, start),
        s.tryPatches(hold, turn, start),
        s.fixLabel('Centre Q4', r9),
        s.fixTitle('bias', {refs: ['Q4'], label: 'Q4'}),
        s.fixTitle('bias', {refs: ['Q4'], label: 'Q4'}, 0.3),
        s.fixTitle('clipper', {refs: ['D1', 'D2'], label: 'D1, D2'}),
        s.biasAim(bias, 0.5), s.biasAim({v: 4, up: null, down: 4}, 0.5),
      ];
    """,
    )
    assert out[:4] == [True, False, True, False]
    assert out[4:8] == [
        {"R9": {"value": "270k"}},
        {"R9": {"value": "470k"}, "R14": {"value": "91k"}},
        {"R9": {"value": "270k"}},
        {"TR1": {"rotation": 0.6, "bias_target": None}},  # turning after holding drops the target
    ]
    assert out[8:12] == ["Centre Q4: R9 470k → 270k", "Centre Q4", "Bias Q4", "Diodes D1, D2"]
    # the bar spans 0 V (4 V down) to 9 V (5 V up): halfway is 4.5 V
    assert out[12] == {
        "v": 4.5,
        "up": 4.5,
        "down": 4.5,
        "text": "Aim: 4.50 V, 4.50 V up, 4.50 V down",
    }
    assert out[13] is None


def test_a_gain_capacitor_opens_edit_curve_on_it(page: Page, base_url: str) -> None:
    """D-125: C3 sets where IC1B's curve bends more than its drive, so the gain box gives
    it Edit curve, opened by part on C3's slider, rather than a slider of its own. With a
    value tried, it asks first: Cancel stays in Bias & headroom, Keep makes its History step."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    page.locator("#stages-expand").click()
    open_card(page, "IC1B").locator("#gain-find").click()
    bar = page.locator('#fix-box .gain-part[data-part="R6"] .gain-bar')
    bar.focus(timeout=20_000)
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    expect(page.locator("#try-changes-list")).to_contain_text("R6 51k \u2192", timeout=15_000)
    edit = page.locator('#fix-box [data-edit-curve="C3"]')
    edit.click()
    ask = page.locator(".ask")
    expect(ask.locator(".ask-title")).to_have_text("Bias & headroom: keep the changes?")
    ask.locator('[data-answer="cancel"]').click()
    expect(ask).to_have_count(0)
    expect(page.locator("#panel-stages")).to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("#panel-frequency")).not_to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("#try-changes-list")).to_contain_text("R6 51k \u2192")
    edit.click()
    ask.locator('[data-answer="keep"]').click()
    expect(page.locator("#panel-frequency")).to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("body")).to_have_attribute("data-frequency-editing", "true")
    expect(page.locator("#edit-by-part")).to_have_attribute("aria-checked", "true")
    slider = page.locator('#curve-edit #influence-rows li[data-ref="C3"] #influence-value-slider')
    expect(slider).to_be_enabled(timeout=15_000)
    page.locator("#history-button").click()
    expect(page.locator("#history-pane")).to_contain_text("Bias & headroom: R6")


def test_gain_slider_logic(js: Page) -> None:
    """D-125: a slider's steps placed by their gain, the nearest one to a point, the
    marks where each pick starts clipping, and a step as a Try."""
    out = run(
        js,
        """
      const s = await m('stages-logic.js');
      const st = (value, gain_db, soft, med, now = false) =>
        ({value, gain_db, now, clips: {soft, med, hard: true}, text: '', chain: ''});
      const steps = [st('5k1', -6, false, false), st('51k', 0, false, true, true),
                     st('100k', 3, true, true), st('510k', 12, true, true)];
      const spots = s.gainSpots(steps);
      const part = {ref: 'R6', kind: 'resistor', value: '51k', nudge_db: 0.4, text: '', steps};
      return [spots, s.nearestStep(spots, 0.5), s.nearestStep(spots, 0.9),
              s.clipMarks(steps).map((k) => [k.level, Math.round(k.at * 100), k.up]),
              s.stepOption(part, steps[3]), s.stepOption(part, steps[1]).label,
              s.gainSpots([st('1k', 0, false, false)])];
    """,
    )
    assert out[0] == [0, pytest.approx(1 / 3), 0.5, 1]
    assert out[1:3] == [2, 3]
    # soft clips from 100k up (between 51k and 100k), medium from 51k up; hard all along: no mark
    assert out[3] == [["soft", 42, True], ["med", 17, True]]
    assert out[4] == {
        "ref": "R6",
        "set": {"R6": {"value": "510k"}},
        "undo": {"R6": {"value": "51k"}},
        "label": "R6 51k \u2192 510k",
        "text": "",
    }
    assert out[5] == "R6 back to 51k"
    assert out[6] == [0.5]


def test_try_changes_session_logic(js: Page) -> None:
    """D-123: an option reads Trying while its values are in; the Changed list and the
    History step say what the session changed."""
    out = run(
        js,
        """
      const s = await m('stages-logic.js');
      const L = await m('layers.js');
      const before = {parts: [{ref: 'R9', value: '470k'}, {ref: 'D1', model: '1N4148'},
        {ref: 'TR1', value: '25k', rotation: 0.5, bias_target: {node: 'Q1.D', volts: 9}}]};
      const after = {parts: [{ref: 'R9', value: '270k'}, {ref: 'D1', model: '1N34A'},
        {ref: 'TR1', value: '25k', rotation: 0.88, bias_target: {node: 'Q1.D', volts: 4}}]};
      const target = {set: {TR1: {rotation: 0.88, bias_target: {node: 'Q1.D', volts: 4}}},
                      undo: {}, label: 't', text: ''};
      const changes = L.curveChanges(before, after, s.TRY_FIELDS);
      return {
        lines: changes.map(s.changeText), label: s.tryLabel(changes), none: s.tryLabel([]),
        in: [s.optionIn(target, after), s.optionIn(target, before)],
        gone: s.optionIn({set: {TR1: {bias_target: null}}, undo: {}, label: '', text: ''},
                         {parts: [{ref: 'TR1'}]}),
        back: s.startFields(before, 'TR1', ['rotation', 'model']),
        tried: s.triedOption([
          {set: {D2: {model: 'LED'}}, undo: {}, label: 'lopsided', text: ''},
          {set: {D1: {model: 'LED'}, D2: {model: 'LED'}}, undo: {}, label: 'pair', text: ''},
          {set: {D1: {model: '1N34A'}, D2: {model: '1N34A'}}, undo: {}, label: 'ge', text: ''},
        ], {parts: [{ref: 'D1', model: 'LED'}, {ref: 'D2', model: 'LED'}]}).label,
      };
    """,
    )
    assert out["lines"] == [
        "R9 470k \N{RIGHTWARDS ARROW} 270k",
        "D1 1N4148 \N{RIGHTWARDS ARROW} 1N34A",
        "TR1 rotation 50 % \N{RIGHTWARDS ARROW} 88 %",
        "TR1 target Q1.D 9 V \N{RIGHTWARDS ARROW} Q1.D 4 V",
    ]
    assert out["label"] == "Bias & headroom: R9, D1, TR1" and out["none"] == "Bias & headroom"
    assert out["in"] == [True, False] and out["gone"] is True
    assert out["back"] == {"rotation": 0.5, "model": None}
    assert out["tried"] == "pair"  # its lopsided half is in too, but the pair is what's tried


def test_one_session_at_a_time_asks_first(page: Page, base_url: str) -> None:
    """D-120, D-123: Edit curve while Try changes has a change in asks Keep / Discard /
    Cancel; Cancel leaves both as they were, Discard puts the value back and Edit starts.
    A Try while Edit curve is open with nothing changed ends Edit quietly."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    card = open_card(page, "Q4")
    card.locator(".try-changes").click()  # the large view
    card.locator(".centre-button").click()
    page.locator("#fix-box .fix-option button").first.click()
    expect(card.locator(".bias-place")).to_have_text("centred", timeout=15_000)

    page.locator("#frequency-expand").click()
    page.locator("#frequency-edit").click()
    ask = page.locator(".ask")
    expect(ask.locator(".ask-title")).to_have_text("Bias & headroom: keep the changes?")
    ask.locator('[data-answer="cancel"]').click()
    expect(ask).to_have_count(0)
    expect(page.locator("#frequency-edit")).to_be_visible()  # Edit didn't start
    expect(page.locator("#stages-keep")).to_have_count(1)  # Try changes is still open
    expect(page.locator("#fix-box")).to_have_count(1)

    page.locator("#frequency-edit").click()
    ask.locator('[data-answer="discard"]').click()
    expect(page.locator("#frequency-keep")).to_have_text("Done")  # Edit is on
    expect(page.locator("#fix-box")).to_have_count(0)
    # Bias & headroom is a bar now (Frequency is the large view): opened, it measures again
    page.locator("#panel-stages > summary").click(position={"x": 60, "y": 10})
    expect(card.locator(".bias-place")).to_have_text("sits high", timeout=15_000)

    # Edit curve open, nothing changed: a Try ends it without asking
    card = open_card(page, "Q1")
    card.locator(".centre-button").click()
    page.locator("#fix-box .fix-option button").first.click()
    expect(card.locator(".bias-place")).to_have_text("centred", timeout=15_000)
    expect(ask).to_have_count(0)
    expect(page.locator("#frequency-keep")).to_be_hidden()
    page.locator("#history-button").click()
    expect(page.locator("#history-pane .history-heading").first).to_have_text(
        "Bias & headroom (in progress)"
    )


def test_an_arrow_shows_what_the_parts_between_lose(page: Page, base_url: str) -> None:
    """D-123: the Big Muff's tone stack loses over 5 dB at 200 Hz into Q1: the arrow
    says so, in the panel and on the strip; a loss under 1 dB isn't shown."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator(CHAIN)).to_have_count(6, timeout=15_000)
    into_q1 = page.locator('#stage-chain .chain-arrow[data-arrow="5"] .arrow-loss')
    expect(into_q1).to_have_text(re.compile("^\N{MINUS SIGN}\\d+ dB$"))
    assert int(into_q1.inner_text()[1:].split()[0]) > 5
    page.locator("#stages-expand").click()
    strip = page.locator('#stage-strip-chain .chain-arrow[data-arrow="5"] .arrow-loss')
    expect(strip).to_have_text(into_q1.inner_text())
    out = run(
        page,
        """
      const s = await m('stages-logic.js');
      return [s.arrowLoss({'200': -11.2}, 200), s.arrowLoss({'200': -0.4}, 200),
              s.arrowLoss(null, 200), s.arrowLoss({'200': 2}, 200)];
    """,
    )
    assert out == ["\N{MINUS SIGN}11 dB", None, None, "+2 dB"]


def test_a_targeted_trimmers_rotation_follows_each_run(page: Page, base_url: str) -> None:
    """Phase 8d (D-127): with a bias target set, the trimmer's Rotation in its form is
    greyed and shows the turn that reaches the target, updated after each run (here a new
    supply); emptying the target makes it editable again. Opening the form at once asks
    for no curve at the part's ref (its sliders asked before its view came back: a 422)."""
    open_fixture(page, base_url, "jfet-drive")
    page.locator('g.part[data-ref="TR1"]').dblclick()
    box = page.locator("#field-rotation")
    expect(box).to_have_js_property("readOnly", True)
    grey = "(e) => getComputedStyle(e).borderTopStyle"
    assert box.evaluate(grey) == "dashed"
    first = box.input_value()
    page.locator("#power").select_option(label="18 V")
    page.locator("#run").click()
    expect(box).not_to_have_value(first, timeout=15_000)
    # the turn it was solved to is in the form's ⓘ (D-200)
    page.locator("form.popup .popup-title .info-button").click()
    expect(page.get_by_role("dialog", name="About TR1")).to_contain_text(
        f"The last run turned it to {box.input_value()} %"
    )
    page.keyboard.press("Escape")
    page.locator("#field-bias_volts").fill("")
    expect(box).to_have_js_property("readOnly", False)
    assert box.evaluate(grey) == "solid"


def test_a_held_node_is_marked_on_the_dc_overlay(page: Page, base_url: str) -> None:
    """Round 2 (D-127): with View → DC voltages on, the drain TR1 holds at 9 V reads
    "9.00 V" in the held colour, its tooltip the target and TR1's turn; other nets are
    plain (round 3: a colour, not a mark)."""
    open_fixture(page, base_url, "jfet-drive")
    page.locator("#view-menu").click()
    page.locator("#menu-dc").click()
    held = page.locator(".dc-layer text.held")
    expect(held.first).to_have_text(re.compile("^9\\.00 Vtarget"))  # then its <title>
    colour = "(e) => getComputedStyle(e).fill"
    plain_colour = page.locator(".dc-layer text:not(.held)").first.evaluate(colour)
    assert held.first.evaluate(colour) != plain_colour
    title = held.first.locator("title").text_content() or ""
    assert re.fullmatch(r"target 9(\.0)? V, held by TR1 at \d+ %", title), title
    expect(page.locator(".dc-layer text.unmet")).to_have_count(0)
    plain = page.locator(".dc-layer text:not(.held)")
    assert plain.count() > 0


def test_a_cards_waveform_section(page: Page, base_url: str) -> None:
    """Round 2 (D-127): the picked block's Waveform section, under the tones and the
    tone note, open at first: the three picks overlaid, what the axes are, and a table of
    their peaks, clipping and THD. It stays open through a re-measure and on another
    block's card; once shut it stays shut there too; with no card there's none."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator(CHAIN)).to_have_count(5, timeout=15_000)
    expect(page.locator("#stage-waves")).to_have_count(0)
    open_card(page, "IC1B")
    waves = page.locator("#stage-waves")
    expect(waves).to_have_attribute("open", "")
    expect(waves.locator(":scope > summary")).to_have_text("Waveform IC1B")
    # under the tone note, above the chain and the card
    after = "(w, sel) => !!(w.compareDocumentPosition(document.querySelector(sel)) & 4)"
    before = "(w, sel) => !!(w.compareDocumentPosition(document.querySelector(sel)) & 2)"
    assert waves.evaluate(before, "#stages-tone-note")
    assert waves.evaluate(after, "#stages-card-body")
    expect(waves.locator("#stages-wave-plot canvas").first).to_be_visible(timeout=15_000)
    # what the plot shows is in the pane's ⓘ (round 3b: not one of its own)
    expect(waves.locator(".info-button")).to_have_count(0)
    info = info_text(page, "panel-stages")
    assert "last two cycles of the tone" in info and "volts to ground" in info
    keys = waves.locator(".u-legend .u-series")
    expect(keys).to_contain_text(["Soft", "Medium", "Hard"])
    # the readings: folded, shut at first (round 3b)
    readings = waves.locator("#stage-wave-readings")
    expect(readings).not_to_have_attribute("open", "")
    table = waves.locator("#stage-wave-table")
    expect(table).to_be_hidden()
    readings.locator("summary").click()
    expect(table.locator("thead th.wave-pick")).to_have_text(["Soft", "Medium", "Hard"])
    expect(table.locator("tbody th")).to_have_text(["Peak +", "Peak \u2212", "Clipping", "THD"])
    expect(table.locator("tbody tr").first.locator("td").first).to_have_text(re.compile(r"^\+\d"))
    expect(table.locator("tbody tr").last.locator("td").first).to_have_text(re.compile(r"%$"))
    # a re-measure (another tone) keeps it open
    page.locator('#stage-tones [data-tone="1000"]').click()
    expect(page.locator("#stages-body")).not_to_have_attribute(
        "data-loading", "true", timeout=15_000
    )
    expect(page.locator("#stage-waves")).to_have_attribute("open", "")
    expect(page.locator("#stages-wave-plot canvas").first).to_be_visible(timeout=15_000)
    # another block's card: a plot there in the same frame (a cached one, or an empty
    # frame till it comes: no flicker, round 3b), the fold left as it was
    switched = """() => {
      document.querySelector('#stage-chain .chain-block[data-refs="Q1"]').click();
      return !!document.querySelector('#stages-wave-plot canvas');
    }"""
    assert page.evaluate(switched)
    expect(page.locator("#stage-wave-readings")).to_have_attribute("open", "")
    # still open; shut, it stays shut on the next card
    open_card(page, "Q1")
    expect(page.locator("#stage-waves")).to_have_attribute("open", "")
    expect(page.locator("#stage-waves .wave-of")).to_have_text("Q1")
    page.locator("#stage-waves > summary").click()
    open_card(page, "IC1B")
    expect(page.locator("#stage-waves")).not_to_have_attribute("open", "")
    open_card(page, "Q1")
    # its card shut: no Waveform
    block(page, "Q1").click()
    expect(page.locator("#stage-waves")).to_have_count(0)
    # no Probe in the card
    expect(open_card(page, "IC1B").locator(".card-probe")).to_have_count(0)


def test_waveform_logic(js: Page) -> None:
    got = js.evaluate(
        """async () => {
      const s = await import('/stages-logic.js');
      const cell = (up, down, thd, clipping) => ({up, down, thd, clipping});
      const row = {levels: {soft: cell(0.5, 0.48, 0.004, 'clean'),
        med: cell(1.2, 1.1, 0.03, 'soft'), hard: cell(1.5, 1.5, 0.21, 'hard')}};
      const waves = {soft: [1, 2], med: [3, 4], hard: [5, 6]};
      const series = s.waveSeries({time_ms: [0, 1], waves});
      const lines = series.series.map((l) => [l.label, l.style, l.values]);
      return {table: s.waveTable(row), x: series.x, lines};
    }"""
    )
    assert got["table"] == [
        {"name": "Peak +", "cells": ["+0.50 V", "+1.20 V", "+1.50 V"]},
        {"name": "Peak \u2212", "cells": ["\u22120.48 V", "\u22121.10 V", "\u22121.50 V"]},
        {"name": "Clipping", "cells": ["clean", "soft", "hard"]},
        {"name": "THD", "cells": ["0.4 %", "3 %", "21 %"]},
    ]
    assert got["x"] == [0, 1]
    assert got["lines"] == [
        ["Soft", "sweep-12", [1, 2]],
        ["Medium", "sweep-6", [3, 4]],
        ["Hard", "sweep-1", [5, 6]],
    ]


def test_a_voice_switch_moves_the_stage_it_lights(page: Page, base_url: str) -> None:
    """9c, two voices: Q1's emitter leg is picked by SW1 (Voice). Picked, Q1 lights the leg
    the switch closes; flipped in Knobs, the chain is measured again and the other leg
    lights instead."""
    open_fixture(page, base_url, "two-voices")
    picked = lambda ref: page.locator(f'g.part.picked[data-ref="{ref}"]')  # noqa: E731
    open_card(page, "Q1")
    expect(picked("SW1")).to_have_count(1)
    expect(picked("R3")).to_have_count(1)  # the Clean leg, lug 1
    expect(picked("R4")).to_have_count(0)
    page.locator('#knobs-body [data-knob="SW1"] [data-position="1"]').click()
    expect(picked("R4")).to_have_count(1, timeout=15_000)  # the Hot leg, measured again
    expect(picked("C3")).to_have_count(1)
    expect(picked("R3")).to_have_count(0)


def test_the_info_starts_with_a_key_to_the_chain(page: Page, base_url: str) -> None:
    """TODO 2026-11-09: the ⓘ opens on a key, each look drawn as the chain draws it: the
    solid bar of a block that clips at a hard pick (3 px, as the chain's), a clipper's
    dashed outline, the picked block's copper, the marks and an arrow's loss."""
    open_circuit(page, base_url, "ts808")
    page.locator("#panel-stages > summary .info-button").click()
    key = page.locator(".info-pop:not([hidden]) [data-chain-key]")
    expect(key.locator(".key-row")).to_have_count(7)
    expect(key.locator(".key-row").first).to_contain_text("it clips at a hard pick")
    bar = key.locator(".key-block.clips").evaluate("e => getComputedStyle(e).borderLeftWidth")
    assert bar == "3px"
    dashed = key.locator('.key-block[data-kind="clipper"]')
    assert dashed.evaluate("e => getComputedStyle(e).borderTopStyle") == "dashed"


def test_a_discrete_op_amp_is_one_box(page: Page, base_url: str) -> None:
    """D-224: the BD-2's Q2, Q3 and Q4 are one block, a double outline with each one's
    job inside; its card says what it is. IC1A, buffering VB, isn't on the chain."""
    open_circuit(page, base_url, "boss-bd2-aion")
    box = page.locator('.chain-block.discrete[data-refs="Q4 Q2 Q3"]')
    expect(box).to_be_visible(timeout=30_000)
    expect(box.locator(".discrete-part")).to_have_text(["Q2 + in", "Q3 \u2212 in", "Q4 out"])
    assert box.evaluate("e => getComputedStyle(e).borderTopStyle") == "double"
    expect(page.locator('.chain-block[data-refs="IC1A"]')).to_have_count(0)
    box.click()
    expect(page.locator("#stage-card .discrete-text")).to_contain_text(
        "Q2 and Q3 are a differential pair"
    )


def test_moving_a_part_leaves_the_pane_where_it_is(page: Page, base_url: str) -> None:
    """D-281 (the user, 2026-11-11): with Auto-run on, dropping a moved part measures the
    pane again; the answer comes straight back (the circuit is electrically the same), and
    the pane must not change height on the way: its progress bar took the note's place for
    a frame or two, a line shorter, and every pane under it jumped."""
    open_circuit(page, base_url, "ts808")
    page.locator("#autorun").check()
    page.locator("#panel-stages").scroll_into_view_if_needed()
    page.evaluate(
        """() => {
          const pane = document.getElementById('panel-stages');
          window.__heights = new Set();
          const tick = () => {
            window.__heights.add(Math.round(pane.getBoundingClientRect().height));
            requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        }"""
    )
    x, y = part_pos(page, "R4")
    before = updates(page)
    page.mouse.move(*to_screen(page, x, y))
    page.mouse.down()
    page.mouse.move(*to_screen(page, x + 40, y + 40), steps=6)
    page.mouse.up()
    wait_for_update(page, before)
    page.wait_for_timeout(300)
    assert part_pos(page, "R4") == (x + 40, y + 40)
    assert len(page.evaluate("[...window.__heights]")) == 1
