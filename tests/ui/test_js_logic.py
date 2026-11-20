# ruff: noqa: E501  (JavaScript inside strings)
"""The browser's DOM-free modules, run in Chromium by importing them into the app page.

Includes the parity check that symbol leads end on the pin offsets of
solum/circuit/parts.py (the one owner of pin geometry).
"""

import json
from itertools import pairwise
from typing import Any

import pytest
from playwright.sync_api import Page

from solum.circuit.parts import PIN_OFFSETS, STEREO_JACK, opamp_pins, ota_pins, switch_pins
from solum.circuit.schema import Opamp, Ota, Switch
from solum.circuit.switches import catalogue
from tests.ui.conftest import REPO, run


def test_symbol_leads_match_parts_table(js: Page) -> None:
    # an OTA's table is a single's pins and a dual's half's together: checked below
    offsets = {t: {k: list(v) for k, v in pins.items()} for t, pins in PIN_OFFSETS.items()
               if t != "ota"}  # fmt: skip
    leads = run(
        js,
        """
        const { symbol } = await m('schematic/symbols.js');
        const out = {};
        for (const type of Object.keys(arg)) {
          const pins = Object.keys(arg[type]).map((name) => ({ name }));
          out[type] = symbol({ type, pins, draw: type === "opamp" ? { show_pins: true } : {} }).leads;
        }
        return out;
        """,
        offsets,
    )
    assert leads == offsets


@pytest.mark.parametrize(
    ("half", "show_pins"),
    [(None, False), (None, True), ("a", False), ("b", False), ("b", True), ("d", False)],
)
def test_opamp_leads_match_parts_table(js: Page, half: str | None, show_pins: bool) -> None:
    """D-140: halves b to d (a quad's, D-172) have no power pins; a single's spare pins
    only while drawn."""
    ref = "IC1" + (half or "").upper()
    part = Opamp(type="opamp", ref=ref, model="TL072", half=half, show_pins=show_pins)  # type: ignore[arg-type]
    expected = {k: list(v) for k, v in opamp_pins(part).items()}
    leads = run(
        js,
        """
        const { pinOffsets } = await m('schematic/symbols.js');
        return pinOffsets({ type: 'opamp', ...arg });
        """,
        {"half": half, "show_pins": show_pins},
    )
    assert leads == expected


@pytest.mark.parametrize("half", [None, "a", "b"])
def test_ota_leads_match_parts_table(js: Page, half: str | None) -> None:
    """D-180: a single OTA (CA3080) has its power pins; an LM13700 half its diode bias and
    buffer instead."""
    part = Ota(type="ota", ref="IC1" + (half or "").upper(), model="LM13700", half=half)  # type: ignore[arg-type]
    leads = run(
        js,
        """
        const { pinOffsets } = await m('schematic/symbols.js');
        return pinOffsets({ type: 'ota', ...arg });
        """,
        {"half": half},
    )
    assert leads == {k: list(v) for k, v in ota_pins(part).items()}


def test_a_stereo_jacks_leads_match_parts_table(js: Page) -> None:
    """D-174: KiCad's AudioJack3, S over R over T."""
    leads = run(
        js,
        """
        const { symbol } = await m('schematic/symbols.js');
        return symbol({ type: 'jack', pins: [], draw: { trs: true } }).leads;
        """,
    )
    assert leads == {k: list(v) for k, v in STEREO_JACK.items()}


@pytest.mark.parametrize(
    ("kind", "pole"),
    [("spst", None), ("spdt-on-off-on", None), ("dpdt-on-on-on", "b"), ("rotary-2p6t", "a"),
     ("footswitch", "c"), ("push-nc", None), ("rotary-1p12t", None), ("4pdt", "d"),
     ("dpdt-momentary", "b")],
)  # fmt: skip
def test_switch_leads_match_parts_table(js: Page, kind: str, pole: str | None) -> None:
    """D-143: a pole's lugs, from the server's switch types, where parts.py puts them."""
    ref = "SW1" + (pole or "").upper()
    sw = Switch(type="switch", ref=ref, kind=kind, pole=pole)  # type: ignore[arg-type]
    expected = {k: list(v) for k, v in switch_pins(sw).items()}
    leads = run(
        js,
        """
        const { pinOffsets, setSwitchKinds } = await m('schematic/symbols.js');
        setSwitchKinds(arg.kinds);
        return pinOffsets({ type: 'switch', kind: arg.kind, pole: arg.pole });
        """,
        {"kinds": catalogue(), "kind": kind, "pole": pole},
    )
    assert leads == expected


CUSTOMS = [
    {"name": "3-way", "throws": 2, "positions": [{"name": "Up", "joins": [1, 1]},
     {"name": "Mid", "joins": [1, 2]}, {"name": "Down", "joins": [2, None]}]},
    {"name": "Clip", "throws": 4, "look": "rotary", "positions": [{"name": n, "joins": [j]}
     for n, j in (("Si", 1), ("Off", None), ("LED", 4))]},
    {"name": "Kill", "throws": 1, "positions": [{"name": "On", "joins": [1]},
     {"name": "Off", "joins": [None]}]},
]  # fmt: skip


@pytest.mark.parametrize("custom", CUSTOMS)
def test_a_custom_switch_matches_the_server(js: Page, custom: dict[str, Any]) -> None:
    """9c: the browser's custom type (kindOf, for lugs before the view has them) is the
    server's (`custom_kind`): lugs where parts.py puts them, the same contacts."""
    poles = len(custom["positions"][0]["joins"])
    pole = "b" if poles > 1 else None
    sw = Switch(type="switch", ref="SW1" + (pole or "").upper(), kind="custom", pole=pole,
                custom=custom)  # type: ignore[arg-type]  # fmt: skip
    kind = sw.switch_kind
    got = run(
        js,
        """
        const { pinOffsets, kindOf } = await m('schematic/symbols.js');
        const part = { type: 'switch', kind: 'custom', pole: arg.pole, custom: arg.custom };
        const k = kindOf(part);
        return { leads: pinOffsets(part), lugs: k.lugs, closed: k.closed, poles: k.poles, look: k.look };
        """,
        {"custom": custom, "pole": pole},
    )
    assert got["leads"] == {k: list(v) for k, v in switch_pins(sw).items()}
    assert got["lugs"] == list(kind.lugs) and got["poles"] == kind.poles
    assert got["closed"] == [list(c) for c in kind.closed] and got["look"] == kind.look


def test_the_custom_editor_starts_from_a_type_and_resizes(js: Page) -> None:
    """9c: Custom… starts from the type picked (its throws by number, in drawing order);
    resizing keeps what was set, a new pole copies pole A, a new position joins the next
    throw, a join past the last throw opens, a rotary under 3 throws is a toggle; each
    join's choices name the lugs as drawn."""
    r = run(
        js,
        """
        const { setSwitchKinds, switchKind } = await m('schematic/symbols.js');
        const c = await m('editor/custom-switch.js');
        setSwitchKinds(arg);
        const from = c.customFrom(switchKind('dpdt-on-on-on'));
        const grown = c.resize(from, { poles: 3, throws: 2, positions: 4 });
        const rotary = c.customFrom(switchKind('rotary-1p4t'));
        const shrunk = c.resize(rotary, { poles: 1, throws: 2, positions: 3 });
        const problems = [c.customProblem(from), c.customProblem({ ...from, name: ' ' }),
          c.customProblem({ ...from, positions: [from.positions[0], { name: '', joins: [1, 1] }] })];
        return { from, grown, shrunk, toggle: c.joinChoices(from, 1), dial: c.joinChoices(rotary, 0), problems };
        """,
        catalogue(),
    )
    assert r["from"] == {
        "name": "My DPDT on-on-on",
        "throws": 2,
        "look": "toggle",
        "positions": [
            {"name": "1", "joins": [1, 1]},
            {"name": "2", "joins": [2, 1]},
            {"name": "3", "joins": [2, 2]},
        ],
    }
    assert [p["joins"] for p in r["grown"]["positions"]] == [
        [1, 1, 1],
        [2, 1, 2],
        [2, 2, 2],
        [2, 2, 2],
    ]
    assert r["grown"]["positions"][3]["name"] == "Position 4"
    assert r["shrunk"]["look"] == "toggle"
    assert [p["joins"] for p in r["shrunk"]["positions"]] == [[1], [2], [None]]
    assert r["toggle"] == [["", "open"], ["1", "B2\u2013B1"], ["2", "B2\u2013B3"]]
    assert r["problems"] == [
        None,
        "Give the switch a name, like Clip or Voice.",
        "Give position 2 a name, like On or Vintage.",
    ]
    assert r["dial"][1:] == [
        ["1", "C\u20131"],
        ["2", "C\u20132"],
        ["3", "C\u20133"],
        ["4", "C\u20134"],
    ]


def test_viewport_math(js: Page) -> None:
    result = run(
        js,
        """
        const v = await m('schematic/viewport.js');
        const fit = v.fitView({ minX: 0, minY: 0, maxX: 200, maxY: 100 }, 400, 400);
        const z = v.zoomAt({ x: 0, y: 0, w: 200, h: 100 }, 50, 25, 2);
        const p = v.panBy({ x: 0, y: 0, w: 200, h: 100 }, 100, -50, 400);
        const b = v.boundsOf([[10, 20], [30, -5]], 5);
        const vb = { x: 0, y: 0, w: 200, h: 100 };
        const inside = v.revealPoint(vb, 100, 50);
        const edge = v.revealPoint(vb, 195, 50);
        const off = v.revealPoint(vb, 1000, -300);
        const grown = v.resizeView(vb, { width: 400, height: 200 }, { width: 800, height: 300 });
        return { fit, z, p, b, inside, edge, off, grown };
        """,
    )
    assert result["fit"] == {"x": 0, "y": -50, "w": 200, "h": 200}  # square area: pad height
    # the point under the cursor stays put: (50 - 0) / 200 == (50 - z.x) / z.w
    z = result["z"]
    assert (z["w"], z["h"]) == (100, 50)
    assert (50 - z["x"]) / z["w"] == pytest.approx(0.25)
    assert result["p"] == {"x": -50, "y": 25, "w": 200, "h": 100}  # 0.5 units per pixel
    assert result["b"] == {"minX": 5, "minY": -10, "maxX": 35, "maxY": 25}
    # revealPoint: a point well inside stays put; near an edge or off screen it's centred
    assert result["inside"] == {"x": 0, "y": 0, "w": 200, "h": 100}
    assert result["edge"] == {"x": 95, "y": 0, "w": 200, "h": 100}
    assert result["off"] == {"x": 900, "y": -350, "w": 200, "h": 100}
    # resizeView: same 0.5 units per pixel, same middle (100, 50): no re-fit (D-164)
    assert result["grown"] == {"x": -100, "y": -25, "w": 400, "h": 150}


def test_one_at_a_time_runs_the_newest_call_once(js: Page) -> None:
    """D-276: calls made while a run is in flight share one run after it."""
    result = run(
        js,
        """
        const s = await m('state.js');
        const started = [];
        const ends = [];
        let position = 0;
        const run = s.oneAtATime(() => new Promise((done, fail) => {
          const at = position;
          started.push(at);
          ends.push(() => (at === 2 ? fail(new Error('boom')) : done(at)));
        }));
        position = 1;
        const first = run();
        position = 2; const second = run();
        position = 3; const third = run();
        position = 2; const fourth = run(); // the newest when the first ends
        const whileFirst = [...started];
        ends[0]();
        const one = await first;
        await new Promise((r) => setTimeout(r));
        const afterFirst = [...started];
        ends[1](); // that run fails: its callers hear of it, and the next call still runs
        const failed = await Promise.allSettled([second, third, fourth]);
        position = 5;
        const last = run();
        ends[2]();
        return {
          whileFirst, one, afterFirst, same: second === third && third === fourth,
          failed: failed.map((f) => f.status), last: await last, started,
        };
        """,
    )
    assert result["whileFirst"] == [1]
    assert result["one"] == 1
    assert result["afterFirst"] == [1, 2] and result["same"]
    assert result["failed"] == ["rejected"] * 3
    assert result["last"] == 5 and result["started"] == [1, 2, 5]


def test_state_helpers(js: Page) -> None:
    result = run(
        js,
        """
        const s = await m('state.js');
        const circuit = { parts: [{ ref: 'VR1', rotation: 0.5 }, { ref: 'R1' }] };
        const controls = [{ ref: 'VR1', kind: 'pot', rotation: 0.5 }, { ref: 'P9', kind: 'pot', rotation: 0.5 }];
        const turned = s.withControls(circuit, controls, { VR1: 0.9, P9: 1 });
        const untouched = s.withControls(circuit, controls, { VR1: 0.5 }) === circuit;
        // a field's knob (the DC jack's Power, a jack's cable, D-185, D-355) sets that field
        const jacks = { parts: [{ ref: 'DC', type: 'dcjack', plugged: true }, { ref: 'J1', type: 'jack', trs: true }] };
        const plugs = [{ ref: 'DC', kind: 'switch', refs: ['DC'], field: 'plugged', values: [true, false] },
                       { ref: 'J1', kind: 'switch', refs: ['J1'], field: 'plug', values: ['ts', 'trs', 'none'] }];
        const turnedJacks = s.withControls(jacks, plugs, { DC: 1, J1: 1 }).parts;
        const unplugged = [turnedJacks[0].plugged, turnedJacks[1].plug];
        // the guitar's volume and its cable (keyed IN.plug) both set on IN (D-364)
        const guitar = { parts: [{ ref: 'IN', type: 'guitar', rotation: 1, plug: 'ts' }] };
        const both = [{ ref: 'IN', kind: 'pot', rotation: 1 },
                      { ref: 'IN.plug', kind: 'switch', refs: ['IN'], field: 'plug', values: ['ts', 'none'] }];
        const played = s.withControls(guitar, both, { IN: 0.4, 'IN.plug': 1 }).parts[0];
        const guitarBoth = [played.rotation, played.plug];
        // knobs stay turned across edits, unless their opening position changed; new ones open there
        const kept = s.keptControls(
          [{ ref: 'VR1', kind: 'pot', rotation: 0.5 }, { ref: 'VR2', kind: 'pot', rotation: 0.3 }, { ref: 'SW1', kind: 'switch', position: 1 }],
          [{ ref: 'VR1', kind: 'pot', rotation: 0.5 }, { ref: 'SW1', kind: 'switch', position: 0 }],
          { VR1: 0.9, SW1: 0, GONE: 1 });

        const l = s.latestOnly();
        const a = l.next(), b = l.next();
        // debounce with fake timers: only the last call runs
        const timers = { pending: [], setTimeout(fn) { this.pending.push(fn); return this.pending.length; },
                         clearTimeout(id) { this.pending[id - 1] = null; } };
        const calls = [];
        const d = s.debounce((x) => calls.push(x), 100, timers);
        d(1); d(2); d(3);
        timers.pending.forEach((fn) => fn && fn());
        const pv = (type, detail, pins) => s.focusNet({ type, detail, pins });
        return {
          original: circuit.parts[0].rotation, turned: turned.parts[0].rotation,
          same: turned.parts[1] === circuit.parts[1], untouched, kept, unplugged, guitarBoth,
          latest: [l.isCurrent(a), l.isCurrent(b)], calls,
          follower: pv('bjt', { stage: { terminal: 'E' } }, { C: { net: 'vp' }, E: { net: 'e' } }),
          diode: pv('diode', {}, { A: { net: 'a' }, K: { net: 'k' } }),
          other: pv('guitar', {}, { out: { net: 'in' } }),
        };
        """,
    )
    assert (result["original"], result["turned"], result["same"]) == (0.5, 0.9, True)
    assert result["unplugged"] == [False, "trs"]
    assert result["guitarBoth"] == [0.4, "none"]
    assert result["untouched"] is True  # nothing differs: the same circuit
    assert result["kept"] == {"VR1": 0.9, "VR2": 0.3, "SW1": 1}
    assert result["latest"] == [False, True]
    assert result["calls"] == [3]
    assert (result["follower"], result["diode"], result["other"]) == ("e", "a", "in")


def test_fixed_formatting(js: Page) -> None:
    result = run(
        js,
        """
        const f = await m('fixed.js');
        return [f.volts(4.5), f.volts(-0.6), f.volts(-0.001), f.volts(null), f.db(6.02),
                f.db(-12.34), f.pct(0.115), f.rotationText(0.625)];
        """,
    )
    assert result == ["4.50 V", "\u22120.60 V", "0.00 V", "—", "+6.0 dB", "\u221212.3 dB",
                      "11.5 %", "63 %"]  # fmt: skip


def test_a_held_nets_dc_text(js: Page) -> None:
    """D-127: a net a trimmer holds to a target (drawn in its own colour): its tooltip the
    target and the turn; one the run didn't get to says what it got."""
    r = run(
        js,
        """
        const f = await m('fixed.js');
        const held = { ref: 'TR1', volts: 4.5, reached: 4.5004, rotation: 0.612, met: true };
        return [f.dcText(4.5004), f.dcText(4.5004, held),
                f.dcText(4.31, { ...held, reached: 4.31, rotation: 1, met: false })];
        """,
    )
    assert r == [
        {"text": "4.50 V", "title": None, "met": True},
        {"text": "4.50 V", "title": "target 4.5 V, held by TR1 at 61 %", "met": True},
        {"text": "4.31 V", "title": "target 4.5 V, not met: TR1 at 100 % gets 4.31 V",
         "met": False},
    ]  # fmt: skip


def test_series(js: Page) -> None:
    result = run(
        js,
        """
        const s = await m('series.js');
        const run = { ac: { freq: [10, 100], nodes: { a: [0, 1], out: [2, 3] } },
                      tran: { input: 'in', time_ms: [0, 1], nodes: { a: { wave: [1, 2], overlay: [1, 1] } } } };
        const snap = s.snapshotOf(s.frequencySeries(run, 'a', 'out'), 'snap');
        const withSnap = s.frequencySeries(run, 'a', 'out', snap);
        const otherGrid = s.frequencySeries(run, 'a', 'out', { ...snap, x: [1, 2, 3] });
        const bars = s.harmonicBars({ harmonics_db: { 2: -40, 3: -10, 4: -50, 5: -20, 6: -60, 7: -30, 8: -70 } });
        const diode = s.deviceCurve({ type: 'diode', detail: {
          curve: { v: [-1, 0, 0.6], i: [-1e-9, 0, 1e-3] }, dc: { v: 0, i: 0 }, swing: null } });
        const jfet = s.deviceCurve({ type: 'jfet', detail: {
          curve: { v: [-1, 0], i: [0, 2e-3] }, vgs: -0.5, id: 1e-3 } });
        return {
          styles: withSnap.series.map((x) => x.style), labels: withSnap.series.map((x) => x.label),
          otherGrid: otherGrid.series.length, sameNet: s.frequencySeries(run, 'out', 'out').series.length,
          none: s.frequencySeries({ ac: null }, 'a', 'out'), scope: s.scopeSeries(run, 'a').series.map((x) => x.style),
          bars, diode, jfet,
        };
        """,
    )
    assert result["styles"] == ["current", "output", "snapshot"]
    assert result["labels"] == ["a", "out (output)", "snap"]
    assert result["otherGrid"] == 2  # a snapshot from another sweep grid isn't drawn
    assert result["sameNet"] == 1
    assert result["none"] is None
    assert result["scope"] == ["current", "input"]
    assert result["bars"]["even"] == [-40, None, -50, None, -60, None, -70]
    assert result["bars"]["odd"] == [None, -10, None, -20, None, -30, None]
    diode = result["diode"]
    assert diode["log"] and diode["y"] == [1e-9, 1e-12, 1e-3]  # |I|, floored at 1 pA
    assert diode["point"] == [0, 1e-12]
    jfet = result["jfet"]
    assert not jfet["log"] and jfet["y"] == [0, 2] and jfet["point"] == [-0.5, 1]  # mA


def test_capacitor_series_adds_the_output(js: Page) -> None:
    result = run(
        js,
        """
        const s = await m('series.js');
        const curves = { freq: [10, 100], freq_text: ['10 Hz', '100 Hz'], nodes: { in: [0, 0], b: [-3, -1] } };
        const run = { ac: { freq: [10, 100], nodes: { in: [0, 0], b: [-3, -1], out: [20, 30] } } };
        const show = (d) => d && { series: d.series.map((x) => [x.label, x.style]), xText: d.xText };
        return [show(s.capacitorSeries(curves, run, 'out')), show(s.capacitorSeries(curves, run, 'b')),
                show(s.capacitorSeries(curves, null, null)), s.capacitorSeries(null, run, 'out')];
        """,
    )
    assert result[0] == {
        "series": [["in", "current"], ["b", "input"], ["out (output)", "output"]],
        "xText": ["10 Hz", "100 Hz"],
    }
    assert result[1]["series"] == [["in", "current"], ["b", "input"]]  # out is a side already
    assert result[2]["series"] == [["in", "current"], ["b", "input"]]
    assert result[3] is None


def test_api_error_messages(js: Page) -> None:
    result = run(
        js,
        """
        const a = await m('api.js');
        const fake = (status, body) => async () => ({ ok: status < 400, status,
          json: async () => { if (body === undefined) throw new Error('not json'); return body; } });
        const failing = async () => { throw new TypeError('network'); };
        const out = [];
        const where = { refs: ['Q1'], nets: [], at: [] };
        for (const f of [fake(422, { message: 'Plain words.' }), fake(500, undefined), failing,
                         fake(422, { message: 'Stuck.', where })]) {
          try { await a.getJson('x', f); out.push('ok'); } catch (e) { out.push([e.message, e.status, e.where]); }
        }
        out.push(await a.postJson('x', { a: 1 }, fake(200, { fine: true })));
        return out;
        """,
    )
    assert result[0] == ["Plain words.", 422, None]
    assert result[1][1] == 500 and "error (500)" in result[1][0]
    assert result[2] == ["Can't reach the Solum Builder server. Is it running?", 0, None]
    # a failed run says where it points (D-345)
    assert result[3] == ["Stuck.", 422, {"refs": ["Q1"], "nets": [], "at": []}]
    assert result[4] == {"fine": True}


def test_a_search_with_its_progress(js: Page) -> None:
    """D-123: postProgress reads a step per line, across chunks, then the result; an error
    line or a plain error answer is an ApiError with its message."""
    result = run(
        js,
        """
        const a = await m('api.js');
        const stream = (chunks) => async (_url, init) => ({ ok: true, status: 200,
          headers: new Headers({ 'content-type': 'application/x-ndjson' }),
          sent: JSON.parse(init.body),
          body: new ReadableStream({ start(c) { for (const x of chunks) c.enqueue(new TextEncoder().encode(x)); c.close(); } }) });
        const steps = [];
        let sent = null;
        const fetchFn = async (url, init) => { sent = JSON.parse(init.body); return stream(
          ['{"done": 0, "of": 2}\\n{"do', 'ne": 1, "of": 2}\\n', '{"result": {"options": [1]}}\\n'])(url, init); };
        const got = await a.postProgress('x', { ref: 'D3' }, (d, o) => steps.push([d, o]), fetchFn);
        const errors = [];
        for (const f of [stream(['{"done": 0, "of": 1}\\n{"message": "Plain words."}\\n']), stream(['{"done": 0, "of": 1}\\n']),
                         async () => ({ ok: false, status: 422, headers: new Headers(), body: null, json: async () => ({ message: 'Not a stage.' }) })]) {
          try { await a.postProgress('x', {}, () => {}, f); errors.push('ok'); } catch (e) { errors.push(e.message); }
        }
        return { got, steps, sent, errors };
        """,
    )
    assert result["got"] == {"options": [1]} and result["steps"] == [[0, 2], [1, 2]]
    assert result["sent"] == {"ref": "D3", "progress": True}
    assert result["errors"] == [
        "Plain words.",
        "The search stopped before it finished. Try again.",
        "Not a stage.",
    ]


def test_problem_helpers(js: Page) -> None:
    result = run(
        js,
        """
        const p = await m('problems.js');
        const mk = (severity, refs, nets) => ({ rule: 'r', severity, refs, nets });
        return {
          none: p.problemCounts([]),
          counts: p.problemCounts([mk('error', [], []), mk('warning', [], []), mk('warning', [], []),
                                   mk('info', [], [])]),
          part: p.problemTarget(mk('error', ['Q1'], ['a'])),
          net: p.problemTarget(mk('error', [], ['a', 'b'])),
          nothing: p.problemTarget(mk('info', [], [])),
          key: p.problemKey(mk('error', ['Q1'], ['a'])),
        };
        """,
    )
    assert result["none"] == ""
    assert result["counts"] == "1 error, 2 warnings, 1 note"
    assert result["part"] == {"kind": "part", "id": "Q1"}
    assert result["net"] == {"kind": "net", "id": "a"}
    assert result["nothing"] is None
    assert result["key"] == "r|Q1|a"


def test_export_logic(js: Page) -> None:
    """D-203: a starter or a saved circuit exports from its last save; Ready to build puts
    unsaved changes and a circuit that won't simulate first, then the checks, errors first,
    leaving out dismissed ones. Notes for the build stay off the sheet and out of the count."""
    result = run(
        js,
        """
        const e = await m('export-logic.js');
        const p = await m('problems.js');
        const note = { rule: 'cap-no-kind', severity: 'info', refs: ['C1', 'C2'], nets: [], message: 'C1 and C2 have no type.', build: true };
        const hot = { rule: 'resistor-power-close', severity: 'warning', refs: ['R1'], nets: [], message: 'R1 runs warm.', build: true };
        const over = { rule: 'cap-over-voltage', severity: 'error', refs: ['C3'], nets: [], message: 'C3 is over.', build: true };
        const check = { problems: [note, hot, over], simulates: false };
        return {
          starter: e.exportTarget({ kind: 'starter', id: 'ts808' }),
          saved: e.exportTarget({ kind: 'circuit', id: 'my-fuzz-v1' }),
          fresh: 'why' in e.exportTarget({ kind: 'new', id: '' }),
          copy: e.exportTarget({ kind: 'copy', id: 'core:vref-divider' }).why,
          none: 'why' in e.exportTarget(null),
          url: e.exportUrl({ kind: 'circuit', id: 'a b' }),
          clean: e.readyRows({ problems: [], simulates: true }, { dirty: false }),
          all: e.readyRows(check, { dirty: true, dismissed: [{ rule: 'resistor-power-close', refs: ['R1'] }] }),
          build: [note, hot, over].map(p.forTheBuild),
        };
        """,
    )
    assert result["starter"] == {"kind": "starter", "id": "ts808"}
    assert result["saved"] == {"kind": "circuit", "id": "my-fuzz-v1"}
    assert result["fresh"] and result["none"]
    assert result["copy"].startswith("Blocks aren't exported")
    assert result["url"] == "api/export/circuit/a%20b"
    assert result["clean"] == {"rows": [], "dismissed": 0}
    rows = result["all"]["rows"]
    assert [r["severity"] for r in rows] == ["warning", "warning", "error", "info"]
    assert "changes since the last save" in rows[0]["text"]
    assert "doesn't simulate" in rows[1]["text"]
    assert rows[2]["refs"] == ["C3"] and rows[3]["refs"] == ["C1", "C2"]
    assert result["all"]["dismissed"] == 1
    assert result["build"] == [True, False, False]


def test_what_counts_before_final(js: Page) -> None:
    """D-362: the check before a version becomes final is Ready to build's (`readyRows`) on
    the last save: a build note counts (an electrolytic with no rating), a circuit that
    doesn't simulate counts, a dismissed note doesn't, and a block goes straight through."""
    result = run(
        js,
        """
        const e = await m('export-logic.js');
        const note = { rule: 'cap-no-rating', severity: 'info', refs: ['C9'], nets: [], message: 'C9 has no voltage rating.', build: true };
        const gone = [{ rule: 'cap-no-rating', refs: ['C9'] }];
        return {
          note: e.readyRows({ problems: [note], simulates: true }, { dirty: false }).rows.length,
          silent: e.readyRows({ problems: [], simulates: false }, { dirty: false }).rows.length,
          dismissed: e.readyRows({ problems: [note], simulates: true }, { dirty: false, dismissed: gone }),
          block: 'why' in e.exportTarget({ kind: 'block', id: 'my-stage-v1' }),
        };
        """,
    )
    assert result["note"] == 1 and result["silent"] == 1
    assert result["dismissed"] == {"rows": [], "dismissed": 1}
    assert result["block"]


def test_dismissed_problems(js: Page) -> None:
    """D-176: a dismissal names its problem by rule, refs and nets; dismissing keeps the
    reason (trimmed, left out when empty), dismissing again replaces it, and bringing a
    problem back takes the list out of the circuit once it's empty."""
    result = run(
        js,
        """
        const p = await m('problems.js');
        const cut = { rule: 'bjt-cut-off', severity: 'warning', refs: ['Q1'], nets: [], message: 'Q1 is cut off.' };
        const open = { rule: 'no-dc-path', severity: 'error', refs: [], nets: ['x'], message: 'x floats.' };
        const other = { ...cut, refs: ['Q2'] };
        const c = { parts: [], notes: {} };
        const one = p.dismissProblem(c, cut, '  biased later ');
        const two = p.dismissProblem(one, open, '   ');
        const again = p.dismissProblem(two, cut, 'a starved fuzz');
        return {
          c, one, two, again,
          split: p.splitDismissed([cut, open, other], two.dismissed),
          none: p.splitDismissed([cut], undefined),
          of: p.dismissalOf(other, two.dismissed) ?? null,
          back: p.restoreProblem(two, cut),
          empty: p.restoreProblem(p.restoreProblem(two, cut), open),
        };
        """,
    )
    assert result["c"] == {"parts": [], "notes": {}}  # never changed in place
    assert result["one"]["dismissed"] == [
        {"rule": "bjt-cut-off", "refs": ["Q1"], "reason": "biased later"}
    ]
    assert result["two"]["dismissed"][1] == {"rule": "no-dc-path", "nets": ["x"]}
    assert result["again"]["dismissed"] == [
        {"rule": "no-dc-path", "nets": ["x"]},
        {"rule": "bjt-cut-off", "refs": ["Q1"], "reason": "a starved fuzz"},
    ]
    split = result["split"]
    assert [x["refs"] for x in split["active"]] == [["Q2"]]
    assert [(x["problem"]["rule"], x["reason"]) for x in split["dismissed"]] == [
        ("bjt-cut-off", "biased later"),
        ("no-dc-path", ""),
    ]
    assert len(result["none"]["active"]) == 1
    assert result["of"] is None  # same rule, another part
    assert result["back"]["dismissed"] == [{"rule": "no-dc-path", "nets": ["x"]}]
    assert result["empty"] == {"parts": [], "notes": {}}


def test_problem_marks(js: Page) -> None:
    """D-176: a mark goes on the pin of the problem's part that's on its net (one only),
    else on the part; a net-only problem at the net's anchor; none for a part that's gone;
    a dismissed problem has no mark."""
    result = run(
        js,
        """
        const p = await m('problems.js');
        const view = {
          parts: [{ ref: 'Q1', pins: [{ name: 'C', net: 'c', pos: [10, -20] }, { name: 'B', net: 'b', pos: [-20, 0] }, { name: 'E', net: 'GND', pos: [10, 20] }] },
                  { ref: 'R1', pins: [{ name: '1', net: 'x', pos: [0, 0] }, { name: '2', net: 'x', pos: [0, 40] }] }],
          nets: { c: { anchors: [[10, -20]] }, x: { anchors: [[0, 0]] }, lonely: { anchors: [] } },
        };
        const mk = (rule, severity, refs, nets) => ({ rule, severity, refs, nets, message: `${rule}!` });
        const spots = [mk('a', 'error', ['Q1'], ['b']), mk('b', 'warning', ['Q1'], []), mk('c', 'info', ['R1'], ['x']),
                       mk('d', 'error', [], ['x', 'c']), mk('e', 'error', ['Q9'], ['c']), mk('f', 'error', [], ['lonely']),
                       mk('g', 'error', [], [])].map((x) => p.markSpot(x, view));
        const marks = p.problemMarks([mk('a', 'error', ['Q1'], ['b']), mk('b', 'warning', ['Q1'], []), mk('e', 'error', ['Q9'], [])],
                                     [{ rule: 'b', refs: ['Q1'] }], view);
        return { spots, marks };
        """,
    )
    assert result["spots"] == [
        {"kind": "pin", "ref": "Q1", "pin": "B", "pos": [-20, 0]},
        {"kind": "part", "ref": "Q1"},
        {"kind": "part", "ref": "R1"},  # both its pins are on x
        {"kind": "net", "net": "x", "pos": [0, 0]},
        None,
        None,
        None,
    ]
    assert result["marks"] == [
        {
            "key": "a|Q1|b",
            "severity": "error",
            "message": "a!",
            "spot": {"kind": "pin", "ref": "Q1", "pin": "B", "pos": [-20, 0]},
        }
    ]


def test_the_printed_schematic_stands_alone(js: Page) -> None:
    """D-205: the TS808's last save drawn by the sheet's own renderer on paper colours, with
    nothing to click and no stylesheet needed: every part, cropped to the drawing."""
    result = run(
        js,
        """
        const { schematicSvg } = await m('export.js');
        const { fileName } = await m('export-logic.js');
        const { text } = await schematicSvg({ kind: 'starter', id: 'ts808' });
        const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
        const svg = doc.documentElement;
        const lines = [...doc.querySelectorAll('line')];
        return {
          ok: !doc.querySelector('parsererror'), viewBox: svg.getAttribute('viewBox'),
          title: doc.querySelector('title').textContent,
          classes: doc.querySelectorAll('[class]').length, data: /data-/.test(text),
          strokes: [...new Set(lines.map((l) => l.getAttribute('stroke')))],
          refs: [...doc.querySelectorAll("text")].map((t) => t.textContent).filter((t) => /^(R|C|Q|D|IC|VR)[0-9]+[A-C]?$/.test(t)),
          hits: /pointer-events|transparent/.test(text),
          name: fileName('Fuzz / Face: v2', 'schematic.svg'),
        };
        """,
    )
    assert result["ok"] and result["title"] == "Ibanez TS808 Tube Screamer"
    assert result["viewBox"] and result["classes"] == 0 and not result["data"]
    assert result["strokes"] == ["rgb(30, 30, 27)"]  # ink (theme.css .print), nothing else
    parts = json.loads((REPO / "library" / "starters" / "ts808.json").read_text())["parts"]
    drawn = {p["ref"] for p in parts if p["type"] not in ("pot", "guitar", "amp")}
    assert set(result["refs"]) == drawn  # every part's ref (a pot shows its name instead)
    assert not result["hits"]
    assert result["name"] == "Fuzz Face v2 schematic.svg"


def test_an_leds_arrows_are_under_it_by_the_cathode_as_kicads(js: Page) -> None:
    """KiCad's Device:LED: the arrows sit below the body (y down), right of the cathode bar
    at x 6, and point down toward K, the lead's far end."""
    lines = run(
        js,
        """
        const { symbol } = await m('schematic/symbols.js');
        const led = symbol({ type: 'led', pins: [{ name: 'A' }, { name: 'K' }], draw: {} });
        const diode = symbol({ type: 'diode', pins: [{ name: 'A' }, { name: 'K' }], draw: {} });
        return { led: led.shapes.length, diode: diode.shapes.length, arrows: led.shapes.slice(diode.shapes.length) };
        """,
    )
    assert lines["led"] == lines["diode"] + 4
    shafts = [s["line"] for s in lines["arrows"] if "line" in s]
    assert shafts == [[8, 4, 14, 10], [14, 4, 20, 10]]
    assert all("fill" not in s for s in lines["arrows"])  # open heads


def test_a_toggle_pole_is_boxed_as_kicads_and_a_rotary_is_not(js: Page) -> None:
    """D-231: a toggle, slide or footswitch pole draws its contacts in a box (KiCad's
    SW_SPDT_x2), each led out to its lug at the same pins; a rotary keeps its arc, unboxed."""
    out = run(
        js,
        """
        const { symbol } = await m('schematic/symbols.js');
        const pole = (lugs, look, closed) => symbol({ type: 'switch', pins: [], draw: { lugs, look, closed } }, 0);
        const spdt = pole(['A2', 'A1', 'A3'], 'toggle', ['A1']);
        const rotary = pole(['A1', 'A2', 'A3', 'A4'], 'rotary', ['A2']);
        return { spdt: spdt.shapes, spdtLeads: spdt.leads, rotary: rotary.shapes };
        """,
    )
    rects = [s["rect"] for s in out["spdt"] if "rect" in s]
    assert rects == [[-15, -28, 30, 56]]
    assert out["spdtLeads"] == {"A2": [-20, 0], "A1": [20, -20], "A3": [20, 20]}
    lines = [s["line"] for s in out["spdt"] if "line" in s]
    assert [-20, 0, -12, 0] in lines and [12, -20, 20, -20] in lines and [12, 20, 20, 20] in lines
    assert [-8, 0, 8.5, -20] in lines  # the arm on A1
    assert not any("rect" in s for s in out["rotary"])


def test_impedance_overlay_text(js: Page) -> None:
    """D-241: Zin and Zout with what the loading does to the level; a pickup's resonance as
    the pedal loads it on a second line; the mouse-over gives the figures, one per line
    (D-249)."""
    r = run(
        js,
        """
        const f = await m('fixed.js');
        const zin = { ref: 'IN', net: 'in', ohms: 33700, text: '33.7 kΩ', freq: 1000, saturated: null,
          level_db: 3.07, level_text: '+3.1 dB', source: '17 kΩ', amp: '1 MΩ',
          resonance: { alone: { text: '7.18 kHz, +3.8 dB' }, loaded: { text: '1.23 kHz, +3.7 dB' } } };
        const zout = { ref: 'OUT', net: 'out', ohms: 18600, text: '18.6 kΩ', freq: 1000, saturated: null,
          level_db: -0.08, level_text: '\u22120.1 dB', load: '1 MΩ', follows: ['VR1 (Volume)'] };
        return [f.impedanceText('zin', zin), f.impedanceText('zin', { ...zin, resonance: null }),
                f.impedanceText('zout', zout), f.impedanceText('zout', { ...zout, saturated: 'Q1 is saturated.' })];
        """,
    )
    assert r[0]["lines"] == ["Zin 33.7 k\u03a9 · +3.1 dB", "Resonance 1.23 kHz, +3.7 dB"]
    assert r[0]["title"].split("\n") == [
        "Input impedance: 33.7 k\u03a9 at 1 kHz",
        "Guitar source: 17 k\u03a9",
        "Level: +3.1 dB",
        "Resonance: 7.18 kHz, +3.8 dB into the amp (1 M\u03a9), 1.23 kHz, +3.7 dB into the pedal",
    ]
    assert r[1]["lines"] == ["Zin 33.7 k\u03a9 · +3.1 dB"] and "Resonance" not in r[1]["title"]
    assert r[2]["lines"] == ["Zout 18.6 k\u03a9 · \u22120.1 dB"]
    assert r[2]["title"].split("\n") == [
        "Output impedance: 18.6 k\u03a9 at 1 kHz",
        "Amp input: 1 M\u03a9",
        "Level: \u22120.1 dB",
        "Changes with VR1 (Volume)",
    ]
    assert r[3] == {"lines": ["Zout: saturated"], "title": "Output impedance: Q1 is saturated."}


def test_server_preferences_are_read_at_once_and_sent_in_order(js: Page) -> None:
    """D-311: storage.js holds the server's preferences as the page was served; changes
    go one request at a time, the ones made meanwhile together, a null forgetting a key;
    the browser's stale copies are dropped."""
    got = run(
        js,
        """
        const { serverKept } = await m('storage.js');
        const store = new Map([["solum.theme", '"light"'], ["solum.audio", '{"clip":"a"}']]);
        const local = {getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k)};
        const sent = [];
        let finish = [];
        const send = (changes) => { sent.push(changes); return new Promise((ok) => finish.push(ok)); };
        const kept = serverKept({"solum.theme": "dark", "solum.autorun": 1}, local, send);
        const first = [kept.get("solum.theme"), kept.get("solum.autorun"), kept.get("solum.panes")];
        const local0 = [...store.keys()];
        kept.set("solum.autorun", 1);  // as it is: nothing is sent
        kept.set("solum.panes", ["a", "b"]);
        kept.set("solum.panes", ["b", "a"]);
        kept.set("solum.theme", null);
        const whileBusy = sent.length;
        finish.shift()();
        await new Promise((r) => setTimeout(r));
        const read = [kept.get("solum.theme"), kept.get("solum.panes")];
        kept.set("solum.autorun", 0);
        kept.flush();  // the page is leaving: what waits goes now
        return {first, local0, whileBusy, sent, read};
        """,
    )
    assert got["first"] == ["dark", 1, None]
    assert got["local0"] == ["solum.audio"]  # the server has them: the browser's copy went
    assert got["whileBusy"] == 1
    assert got["sent"] == [
        {"solum.panes": ["a", "b"]},
        {"solum.panes": ["b", "a"], "solum.theme": None},
        {"solum.autorun": 0},
    ]
    assert got["read"] == [None, ["b", "a"]]


def test_a_browsers_old_preferences_go_to_the_server_once(js: Page) -> None:
    """D-311: the server keeps none yet (`null`): this browser's old values are used and
    sent (an empty set too, so it is asked once), and dropped here only once it has them;
    a server that can't be reached leaves them for the next visit."""
    got = run(
        js,
        """
        const { serverKept } = await m('storage.js');
        const fill = () => new Map([["solum.theme", '"dark"'], ["solum.panes", '["x"]'], ["solum.layers", '["knees"]']]);
        const localOf = (store) => ({getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k)});
        const out = {};
        for (const [name, answer] of [["ok", () => Promise.resolve({})], ["down", () => Promise.reject(new Error("down"))]]) {
          const store = fill();
          const sent = [];
          const kept = serverKept(null, localOf(store), (c) => { sent.push(c); return answer(); });
          const read = [kept.get("solum.theme"), kept.get("solum.panes"), kept.get("solum.large")];
          await new Promise((r) => setTimeout(r));
          out[name] = {sent, read, left: [...store.keys()].sort()};
        }
        const sent = [];
        serverKept(null, null, (c) => { sent.push(c); return Promise.resolve({}); });  // storage blocked
        out.blocked = sent;
        return out;
        """,
    )
    carried = {"solum.theme": "dark", "solum.panes": ["x"]}
    assert got["ok"] == {"sent": [carried], "read": ["dark", ["x"], None], "left": ["solum.layers"]}
    assert got["down"]["sent"] == [carried]
    assert got["down"]["left"] == ["solum.layers", "solum.panes", "solum.theme"]
    assert got["blocked"] == [{}]


def test_settings_sizes_and_what_is_wrong_with_one(js: Page) -> None:
    got = run(
        js,
        """
        const { sizeText, cacheSizeProblem } = await m('settings.js');
        return {
          sizes: [0, 340e6, 999.4e6, 1e9, 1.25e9, 20e9].map(sizeText),
          problems: ["2", " 0,5 ", "0", "-1", "", "lots"].map(cacheSizeProblem),
        };
        """,
    )
    assert got["sizes"] == ["0 MB", "340 MB", "999 MB", "1.0 GB", "1.3 GB", "20.0 GB"]
    more = "The largest cache size must be more than 0."
    number = "Type the largest cache size as a number of gigabytes, such as 2 or 0.5."
    assert got["problems"] == [None, None, more, more, number, number]


def test_what_settings_asks_before_the_data_folder_moves(js: Page) -> None:
    """The Mac app's Change… (D-323): nothing to ask when the folder in use is empty; else
    move the files or leave them, worded by whether the new folder has files already."""
    got = run(
        js,
        """
        const { moveQuestion } = await m('settings.js');
        const picked = (here, there) => ({ path: "/Users/me/Pedals", problem: null, files_here: here, files_there: there });
        return [moveQuestion(picked(false, false)), moveQuestion(picked(false, true)),
                moveQuestion(picked(true, false)), moveQuestion(picked(true, true))];
        """,
    )
    assert got[0] is None and got[1] is None
    assert got[2]["stay"] == "Start empty" and "Move them to /Users/me/Pedals" in got[2]["text"]
    assert got[3]["stay"] == "Use what is there"
    assert "/Users/me/Pedals has files already" in got[3]["text"]


def test_the_mac_apps_functions_are_absent_in_a_browser(js: Page) -> None:
    got = run(
        js,
        """
        const { desktopApi, desktopMenus } = await m('desktop.js');
        const before = desktopApi();
        globalThis.pywebview = { api: { show_folder: () => {} } };
        const seen = [];
        desktopMenus({ settings: () => seen.push("settings") });
        window.dispatchEvent(new CustomEvent("solum-desktop", { detail: "settings" }));
        window.dispatchEvent(new CustomEvent("solum-desktop", { detail: "unknown" }));
        const after = typeof desktopApi()?.show_folder;
        delete globalThis.pywebview;
        return { before, after, seen };
        """,
    )
    assert got == {"before": None, "after": "function", "seen": ["settings"]}


def test_the_mac_app_is_told_when_unsaved_work_comes_and_goes(js: Page) -> None:
    """Closing the Mac app's window asks first when there is unsaved work (D-321): the page
    tells it when that changes, and only then."""
    got = run(
        js,
        """
        const { desktopUnsaved } = await m('desktop.js');
        const told = [];
        globalThis.pywebview = { api: { set_unsaved: (now) => told.push(now) } };
        let dirty = false;
        desktopUnsaved(() => dirty);
        const wait = () => new Promise((done) => setTimeout(done, 1200));
        await wait();
        dirty = true;
        await wait();
        await wait();
        dirty = false;
        await wait();
        delete globalThis.pywebview;
        return told;
        """,
    )
    assert got == [True, False]


def test_pin_list_numbers_a_chip_as_counted_on_it(js: Page) -> None:
    """D-336: a chip's pins by datasheet number in number order, its function after; any
    other part's by name, as drawn."""
    chip = {"out": {"net": "o", "number": 7}, "+": {"net": "p", "number": 5},
            "-": {"net": "n", "number": 6}}  # fmt: skip
    resistor = {"1": {"net": "a", "number": None}, "2": {"net": "b", "number": None}}
    got = run(
        js,
        "const { pinList } = await m('panels.js'); return arg.map(pinList);",
        [chip, resistor],
    )
    assert [r["label"] for r in got[0]] == ["5 (+)", "6 (-)", "7 (out)"]
    assert [r["net"] for r in got[0]] == ["p", "n", "o"]
    assert [r["label"] for r in got[1]] == ["pin 1", "pin 2"]


def test_a_dropped_supply_turns_clear_of_its_wire(js: Page) -> None:
    """D-338: as drawn when clear (a rail's bar up, ground down), else away from the wire,
    else to the side: never on the wire it lands on."""
    got = run(
        js,
        """
        const { clearSupplyRot } = await m('editor/edit.js');
        const c = { parts: [], wires: [{ from: [0, 0], to: [0, 40] }] };
        const spots = [[0, 0, 'rail'], [0, 40, 'rail'], [0, 20, 'rail'], [0, 0, 'ground'],
                       [0, 40, 'ground'], [100, 100, 'rail']].map(([x, y, k]) => clearSupplyRot(c, [x, y], k));
        // a resistor at the origin (no pos in the file): its left pin's lead runs right
        const r = { parts: [{ ref: 'R1', type: 'resistor', value: '1k' }], wires: [] };
        return [...spots, clearSupplyRot(r, [-20, 0], 'ground')];
        """,
    )
    assert got == [0, 180, 90, 180, 0, 0, 0]


def test_drawn_pins_keep_dc_only_on_the_same_net(js: Page) -> None:
    """D-337: after an edit the pin list is the drawing's; a voltage stays only beside the
    net it was measured on."""
    got = run(
        js,
        """
        const { drawnPins } = await m('panels.js');
        return drawnPins({ 1: { net: 'a', dc: 1 }, 2: { net: 'b', dc: 2 } },
          [{ name: '1', net: 'a', number: null }, { name: '2', net: 'c' }, { name: '3', net: 'd', number: 3 }]);
        """,
    )
    assert got == {
        "1": {"net": "a", "dc": 1, "number": None},
        "2": {"net": "c", "dc": None, "number": None},
        "3": {"net": "d", "dc": None, "number": 3},
    }


def test_the_power_chip_follows_the_cable_and_dc_switches(js: Page) -> None:
    """D-357: a battery entry reads "cut off" while a jack's cable switch sits where it cuts
    the battery off (its opening position `at` when untouched); the DC jack's entry wins."""
    got = run(
        js,
        """
        const { chipNow } = await m('editor/edit.js');
        const cut = { text: "Battery · cut off", jacks: { J1: { at: 0, positions: [1, 2] } } };
        const alone = { text: "Battery · 9 V", battery: true, cut_off: cut };
        const both = { control: "DC", positions: [{ text: "DC jack", battery: false }, { text: "Battery · 9 V", battery: true }], cut_off: cut };
        return [chipNow(alone, {}), chipNow(alone, { J1: 2 }), chipNow(both, { DC: 0, J1: 2 }),
                chipNow(both, { DC: 1, J1: 1 }), chipNow(both, { DC: 1 }), chipNow(null, {})];
        """,
    )
    assert [c and c["text"] for c in got] == [
        "Battery · 9 V", "Battery · cut off", "DC jack", "Battery · cut off", "Battery · 9 V", None,
    ]  # fmt: skip


def test_the_board_tray_and_settings(js: Page) -> None:
    """The Board view's tray: on-board parts with footprint, off-board parts as the parts
    list names them, then the stock bypass (D-370); the editor's settings read with
    defaults for anything missing or garbled."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        const progress = {
          to_place: ['R1', 'IC1'], wires_to_go: [], loose: 0, unplaceable: [],
          footprints: { R1: { shape: 'axial', kind: 'resistor', legs: ['1', '2'], refs: ['R1'] }, IC1: { shape: 'dip', kind: 'chip', legs: ['1','2','3','4','5','6','7','8'], refs: ['IC1A', 'IC1B'] } },
          items: [
            { ref: 'VR1', name: 'VR1 (Gain)', kind: 'pot', value: 'B100k', details: 'linear (B)', lugs: [{ end: 'VR1.1', label: '1', net: 'a' }], size: [3, 3] },
            { ref: 'SW1', name: 'SW1', kind: 'switch', value: 'SPDT', details: '', lugs: [{ end: 'SW1.1', label: '1', net: 'b' }], size: [3, 3] },
            { ref: 'IN', name: 'IN (Input)', kind: 'jack', value: '¼" jack', details: 'TS', lugs: [{ end: 'IN.out', label: 'T', net: 'in' }], size: [3, 3] },
          ],
          spots: { VR1: [0, -7], SW1: [5, -7], IN: [16, 0] },
          stock: ['footswitch', 'status LED'],
        };
        const circuit = { parts: [{ ref: 'R1', value: '4k7' }, { ref: 'IC1A', model: 'TL072' }] };
        return {
          on: b.trayRows(progress, circuit).map(({ ref, value, shape }) => ({ ref, value, shape })),
          groups: b.trayGroups(b.trayRows(progress, circuit)).map((g) => [g.title, g.rows.map((r) => r.ref)]),
          wires: b.netWords({ net: 'x', state: 'pieces', placed: 1, total: 3, pieces: 1, shorts: [], wires: ['VR1 lug 2'] }),
          off: b.offBoardRows(progress, b.readBoard({ size: [4, 4], wires: [{ from: 'IN.out', hole: 'A1' }] })).map(({ ref, value, shape, item }) => ({ ref, value, shape, item })),
          none: b.readSettings(null),
          some: b.readSettings({ values: false, grow: 'yes' }),
        };
        """,
    )
    assert got["on"] == [{"ref": "R1", "value": "4k7", "shape": "axial"},
                         {"ref": "IC1", "value": "TL072", "shape": "DIP-8"}]  # fmt: skip
    assert got["off"] == [  # IN is wired (a board from pads): beside the board, not in the tray
        {"ref": "VR1 (Gain)", "value": "B100k", "shape": "linear (B)", "item": "VR1"},
        {"ref": "SW1", "value": "SPDT", "shape": "switch", "item": "SW1"},
        {"ref": "Footswitch", "value": "3PDT", "shape": "stock, true bypass", "item": None},
        {"ref": "Status LED", "value": "", "shape": "stock", "item": None},
    ]
    assert got["groups"] == [["Resistors", ["R1"]], ["Chips", ["IC1"]]]
    assert got["wires"] == "1 of 3 placed; a wire from VR1 lug 2"
    assert got["none"] == {"values": True, "next": True, "shorts": True, "grow": True,
                           "seeThrough": False}  # fmt: skip
    assert got["some"] == {**got["none"], "values": False}  # a garbled one at its default


def test_the_board_size_offers_and_the_empty_board(js: Page) -> None:
    """D-372: a ruler mark's size changes; an empty board drawn at its starting size; the
    header line with the size in mm (D-373)."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        const empty = b.readBoard(null);
        return {
          column: b.lineChanges('column', 5),
          strip: b.lineChanges('strip', 0).map((c) => c.label),
          empty: [b.drawnBoard(empty, [11, 8]).columns, b.drawnBoard(empty, [11, 8]).strips],
          kept: b.drawnBoard(b.readBoard({ size: [12, 9] }), [11, 8]).columns,
          line: b.sizeLine({ columns: 24, strips: 1, cuts: ['A1'], links: [], wires: [] }),
          wired: b.sizeLine({ columns: 2, strips: 2, cuts: [], links: [], wires: [{}, {}] }),
          emptyLine: b.sizeLine({ columns: 0, strips: 0, cuts: [], links: [], wires: [] }),
        };
        """,
    )
    assert got["column"] == [
        {"label": "Insert a column left of F", "change": "insert", "axis": "column", "at": 5},
        {"label": "Insert a column right of F", "change": "insert", "axis": "column", "at": 6},
        {"label": "Remove column F", "change": "remove", "axis": "column", "at": 5},
    ]
    assert got["strip"] == ["Insert a strip above 1", "Insert a strip below 1", "Remove strip 1"]
    assert got["empty"] == [11, 8] and got["kept"] == 12
    # D-373: the size in mm as cut midway between hole lines (24 × 2.54 = 60.96)
    assert got["line"] == "24 × 1 holes (61 × 3 mm), 1 cut, 0 links"
    assert got["wired"] == "2 × 2 holes (5 × 5 mm), 0 cuts, 0 links, 2 wires"
    assert got["emptyLine"] == "Empty board"


def test_a_carried_part_turns_flips_stands_and_lands_by_its_middle(js: Page) -> None:
    """D-374: a part's legs in each pose, held by its middle; the pose a placed part sits
    in read back from its legs; the moves each footprint allows; a link laid down a column;
    the Board view's own keys."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        const k = await m('editor/keys.js');
        const r = { shape: 'axial', legs: ['1', '2'], steps: [], flat: 4, stand: 1, refs: ['R1'] };
        const q = { shape: 'inline', legs: ['E', 'B', 'C'], steps: [1, 2], flat: 0, stand: 0, refs: ['Q1'] };
        const ic = { shape: 'dip', legs: ['1','2','3','4','5','6','7','8'], steps: [], flat: 0, stand: 0, row_holes: 3, refs: ['IC1A'] };
        const first = b.firstPose(r);
        const turned = b.posed(r, first, 'turn');
        const standing = b.posed(r, first, 'stand');
        const placedQ = b.legsAt(q, b.posed(q, b.firstPose(q), 'flip'), [5, 5]);
        return {
          first,
          down: b.legsAt(r, first, [5, 5]),
          turned: b.legsAt(r, turned, [5, 5]),
          standing: b.legsAt(r, standing, [5, 5]),
          longer: b.posed(r, first, 'longer').span,
          shorter: b.posed(r, first, 'shorter'),
          flippedQ: placedQ,
          poseQ: b.poseOf(q, placedQ, false),
          poseTurned: b.poseOf(r, b.legsAt(r, b.posed(r, turned, 'turn'), [2, 2]), false),
          wideQ: b.posed(q, b.firstPose(q), 'longer').span,
          chip: b.legsAt(ic, b.firstPose(ic), [4, 4]),
          chipTurn: b.posed(ic, b.firstPose(ic), 'turn').turns,
          chipFlip: b.posed(ic, b.firstPose(ic), 'flip'),
          link: b.linkFrom([3, 1], [6, 5]),
          noLink: b.linkFrom([3, 1], [6, 1]),
          red: b.runRects([[7, 0, 11]]),
          keys: [' ', 'f', 's', '+', '-', 'Delete', 'c', 'k', 'p', 'Escape', 'r'].map((key) => k.boardActionFor({ key })?.action ?? null),
          ctrl: k.boardActionFor({ key: 'z', ctrl: true }),
        };
        """,
    )
    assert got["first"] == {"turns": 0, "flipped": False, "standing": False, "span": 4}
    assert got["down"] == [["1", [5, 3]], ["2", [5, 7]]]  # across the strips, middle at F6
    assert got["turned"] == [["1", [7, 5]], ["2", [3, 5]]]  # a quarter turn about its middle
    assert got["standing"] == [["1", [5, 4]], ["2", [5, 5]]]
    assert got["longer"] == 5 and got["shorter"] is None
    assert got["flippedQ"] == [["C", [5, 4]], ["B", [5, 5]], ["E", [5, 6]]]
    # a line turned half round is the same legs as flipped: the first match is kept
    assert got["poseQ"] == {"turns": 2, "flipped": False, "standing": False, "span": 1}
    assert got["poseTurned"]["turns"] == 2 and got["wideQ"] == 2
    assert got["chip"][:2] == [["1", [2, 2]], ["2", [2, 3]]] and got["chip"][7] == ["8", [5, 2]]
    assert got["chipTurn"] == 2 and got["chipFlip"] is None
    assert got["link"] == [[3, 1], [3, 5]] and got["noLink"] is None
    assert got["red"] == [{"x": -5, "y": 65, "w": 120, "h": 10}]
    assert got["keys"] == ["turn", "flip", "stand", "longer", "shorter", "remove", "cuts",
                           "links", "parts", "cancel", None]  # fmt: skip
    assert got["ctrl"] is None


def test_off_board_parts_lugs_and_wires_are_drawn_where_they_sit(js: Page) -> None:
    """D-375: an off-board part's lugs along the bottom of its drawing, two holes apart; a
    wire from its lug to a hole, to another lug, or hanging loose; a part dropped from the
    tray held by its middle; the Nets line counts the lugs still to wire."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        const pot = { ref: 'VR1', name: 'VR1', kind: 'pot', value: '', details: '', size: [7, 3],
          lugs: ['1', '2', '3'].map((n) => ({ end: `VR1.${n}`, label: n, net: n })) };
        const jack = { ref: 'IN', name: 'IN', kind: 'jack', value: '', details: '', size: [5, 3],
          lugs: [{ end: 'IN.out', label: 'T', net: 'in' }, { end: 'IN.S', label: 'S', net: 'GND' }] };
        const board = b.readBoard({ size: [4, 4], off: { VR1: [0, -7] },
          wires: [{ from: 'VR1.1', hole: 'B2' }, { from: 'VR1.3', lug: 'IN.S' }, { from: 'VR1.2' }] });
        const progress = { items: [pot, jack], spots: { VR1: [9, 9], IN: [8, 0] } };
        const lugs = b.lugPlaces(progress, board);
        return {
          shape: b.itemShape(pot, [0, -7]),
          lugs: Object.keys(lugs),
          wires: board.wires.map((w) => b.wireLine(w, lugs)),
          spot: b.spotFor(pot, [10, -5]),
          out: [b.isOut(pot, board), b.isOut(jack, board), b.isOut(jack, b.readBoard({ size: [1, 1] }))],
          refs: [b.itemRefs(pot), b.itemRefs({ ...jack, kind: 'power' })],
          line: b.netsLine({ nets: [{}, {}], nets_done: 1, wires_to_go: ['VR1.2'], loose: 1 }),
          done: b.netsLine({ nets: [{}], nets_done: 1, wires_to_go: [], loose: 0 }),
        };
        """,
    )
    assert got["shape"]["body"] == {"x": -5, "y": -75, "w": 70, "h": 20}
    assert [(lug["x"], lug["y"]) for lug in got["shape"]["lugs"]] == [
        (10, -50),
        (30, -50),
        (50, -50),
    ]
    assert got["lugs"] == ["VR1.1", "VR1.2", "VR1.3", "IN.out", "IN.S"]
    hole, lug, loose = got["wires"]
    assert {k: hole[k] for k in ("x1", "y1", "x2", "y2", "loose", "hole")} == {
        "x1": 10, "y1": -50, "x2": 10, "y2": 10, "loose": False, "hole": True,
    }  # fmt: skip
    assert hole["box"] == got["shape"]["body"]
    assert (lug["x2"], lug["y2"], lug["loose"]) == (110, 20, False)  # IN at its default spot
    assert loose["loose"] is True and loose["y2"] > loose["y1"]
    assert got["spot"] == [7, -6]
    assert got["out"] == [True, True, False]
    assert got["refs"] == [["VR1"], []]
    assert got["line"] == "1 of 2 nets done; 1 lug to wire, 1 loose."
    assert got["done"] == "All 1 nets done."


def test_off_board_wires_are_routed_round_the_parts_and_hop_where_they_cross(js: Page) -> None:
    """D-379: each wire leaves its lug downward and reaches its hole in square runs on the
    half-hole grid, never through a part's body (a board part's or an off-board part's),
    going round the board's side rather than across it; two wires never lie along each
    other; lug to lug ends coming up into the other lug; a crossing hops on its level run.
    D-380: a run moved by hand stays where it was put; a dragged run snaps to a gap's
    middle over the board, to the half-hole grid beside it."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        const board = { columns: 10, strips: 8 };
        const jack = { x: -75, y: 0, w: 50, h: 20 };
        const wall = { x: 12, y: 18, w: 16, h: 24 };  // a part's body over D3–C4
        const obstacles = { boxes: [jack, wall], lines: [] };
        const left = { x1: -60, y1: 25, x2: 30, y2: 30, loose: false, hole: true, box: jack };
        const left2 = { x1: -40, y1: 25, x2: 0, y2: 60, loose: false, hole: true, box: jack };
        const lugs = { x1: -60, y1: 25, x2: -40, y2: 25, loose: false, hole: false, box: jack };
        const routes = b.wireRoutes([left, left2, lugs, null], board, obstacles);
        const moved = b.wireRoutes([{ ...left, runs: [[1, 4.5], [9, 1]] }, left2, lugs, null], board, obstacles)[0];
        const cross = b.wireHops([[[0, 0], [100, 0]], [[50, -40], [50, 40]]]);
        const route = routes[0];
        return {
          routes, moved, cross,
          snaps: [b.runAt([[0, 0], [0, 30], [90, 30], [90, 40]], 1, [0, 47], board), b.runAt([[-60, 0], [-60, 10], [-23, 10], [-23, 40]], 2, [-23.4, 0], board)],
          path: b.routePath([[0, 0], [100, 0], [100, 50]], cross[0]),
          along: b.pointAlong([[0, 0], [10, 0], [10, 10]], 15),
        };
        """,
    )
    left, left2, lugs, missing = got["routes"]
    assert missing is None

    def runs(route: list[list[float]]) -> list[tuple[list[float], list[float]]]:
        return list(pairwise(route))

    def inside(x: float, y: float, b: dict[str, float]) -> bool:
        return b["x"] < x < b["x"] + b["w"] and b["y"] < y < b["y"] + b["h"]

    jack = {"x": -75, "y": 0, "w": 50, "h": 20}
    wall = {"x": 12, "y": 18, "w": 16, "h": 24}
    for route, end in ((left, [30, 30]), (left2, [0, 60])):
        assert route[0] == [-60 if route is left else -40, 25] and route[-1] == end
        assert route[1][0] == route[0][0] and route[1][1] > route[0][1]  # down from the lug
        for a, b in runs(route):
            assert a[0] == b[0] or a[1] == b[1]  # square
            for t in (k / 20 for k in range(21)):
                x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                assert not inside(x, y, jack) and not inside(x, y, wall)
    # beside the board it runs on the half-hole grid; over it, in the gaps between holes
    for a, _b in runs(left)[1:-1]:
        assert a[0] % 5 == 0 and a[1] % 5 == 0
    # no two runs along each other
    for a, b in runs(left):
        for c, d in runs(left2):
            if a[1] == b[1] == c[1] == d[1]:
                overlap = min(max(a[0], b[0]), max(c[0], d[0])) - max(
                    min(a[0], b[0]), min(c[0], d[0])
                )
                assert overlap <= 0
    assert lugs[0] == [-60, 25] and lugs[-1] == [-40, 25]
    assert lugs[-2][0] == -40 and lugs[-2][1] > 25  # up into the other lug
    assert (
        got["moved"][1][1] == 45 and got["moved"][2][1] == 45
    )  # run 1 put at 4.5 holes; run 9 ignored
    assert got["snaps"] == [
        4.5,
        -2.5,
    ]  # a gap's middle over the board; the half-hole grid beside it
    assert got["cross"] == [[[0, 50]], []]  # the level run hops, the upright doesn't
    assert "A3,3 0 0 1 53,0" in got["path"] and "Q100,0" in got["path"]
    assert got["along"] == [10, 5]


def test_parts_gone_from_the_circuit_are_said_in_one_sentence(js: Page) -> None:
    """D-376: the Warnings pane's line above its Clear them button."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        return [b.staleLine([]), b.staleLine(['R7']), b.staleLine(['R7', 'R9', 'VR9'])];
        """,
    )
    assert got == [
        "",
        "R7 is no longer in the circuit.",
        "R7, R9 and VR9 are no longer in the circuit.",
    ]


def test_a_board_part_is_drawn_with_its_markings(js: Page) -> None:
    """D-378: a resistor's colour bands from its first leg, a diode's band at the cathode, an
    electrolytic's stripe, a TO-92's D-shaped body, a chip's notch and pin-1 dot."""
    got = run(
        js,
        """
        const b = await m('board/board-logic.js');
        const axial = { shape: 'axial', kind: 'resistor', legs: ['1', '2'], steps: [], flat: 4, stand: 1, length: 6.3, width: 2.5, diameter: 0, row_holes: 0, refs: ['R1'] };
        const legs = [['1', [0, 0]], ['2', [4, 0]]];
        const kinds = (shapes) => shapes.map((s) => s.kind === 'band' ? s.colour : s.kind === 'path' ? s.cls : s.kind);
        const resistor = b.partShapes({ ...axial, look: { bands: ['yellow', 'violet', 'red', 'gold'] } }, legs, false);
        const diode = b.partShapes({ ...axial, kind: 'diode', look: { cathode: '2' } }, legs, false);
        const cap = b.partShapes({ ...axial, shape: 'radial', diameter: 5, look: { minus: '2' } }, [['1', [0, 0]], ['2', [0, 1]]], false);
        const to92 = b.partShapes({ ...axial, shape: 'inline', length: 4.6, width: 4.2, look: { face: true } }, [['E', [0, 0]], ['B', [1, 0]], ['C', [2, 0]]], false);
        const chip = b.partShapes({ ...axial, shape: 'dip', kind: 'chip', length: 0, width: 6.4, legs: ['1','2','3','4','5','6','7','8'] },
          [['1', [0, 0]], ['2', [0, 1]], ['3', [0, 2]], ['4', [0, 3]], ['5', [3, 3]], ['6', [3, 2]], ['7', [3, 1]], ['8', [3, 0]]], false);
        const firstBand = resistor.find((s) => s.kind === 'band');
        return { resistor: kinds(resistor), firstBandX: firstBand.cx, diode: kinds(diode), diodeBandX: diode.find((s) => s.kind === 'band').cx,
                 cap: kinds(cap), capAngle: cap.find((s) => s.kind === 'path').angle, to92: kinds(to92), chip: kinds(chip),
                 label: b.legLabel({ ...axial, shape: 'dip' }, '3') };
        """,
    )
    assert got["resistor"] == ["lead", "lead", "rect", "yellow", "violet", "red", "gold"]
    assert got["firstBandX"] < 20  # the first band toward the first leg (x 0), the middle is 20
    assert got["diode"] == ["lead", "lead", "rect", "cathode"] and got["diodeBandX"] > 20
    assert got["cap"] == ["lead", "lead", "circle", "stripe"] and got["capAngle"] == 90
    assert got["to92"] == ["lead", "lead", "lead", "body"]
    assert got["chip"] == ["rect", "notch", "dot"] and got["label"] == "pin 3"
