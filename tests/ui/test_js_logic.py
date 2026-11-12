# ruff: noqa: E501  (JavaScript inside strings)
"""The browser's DOM-free modules, run in Chromium by importing them into the app page.

Includes the parity check that symbol leads end on the pin offsets of
solum/circuit/parts.py (the one owner of pin geometry).
"""

import json
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
        return symbol({ type: 'jack', pins: [], draw: { stereo: true } }).leads;
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
        // a plug knob (the DC jack's Power, a stereo jack's cable, D-185) sets `plugged`, in at 0
        const jacks = { parts: [{ ref: 'DC', type: 'dcjack', plugged: true }, { ref: 'J1', type: 'jack', stereo: true }] };
        const plugs = [{ ref: 'DC', kind: 'switch', refs: ['DC'], plug: true }, { ref: 'J1', kind: 'switch', refs: ['J1'], plug: true }];
        const unplugged = s.withControls(jacks, plugs, { DC: 1, J1: 1 }).parts.map((p) => p.plugged);
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
          same: turned.parts[1] === circuit.parts[1], untouched, kept, unplugged,
          latest: [l.isCurrent(a), l.isCurrent(b)], calls,
          follower: pv('bjt', { stage: { terminal: 'E' } }, { C: { net: 'vp' }, E: { net: 'e' } }),
          diode: pv('diode', {}, { A: { net: 'a' }, K: { net: 'k' } }),
          other: pv('guitar', {}, { out: { net: 'in' } }),
        };
        """,
    )
    assert (result["original"], result["turned"], result["same"]) == (0.5, 0.9, True)
    assert result["unplugged"] == [False, False]
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
        for (const f of [fake(422, { message: 'Plain words.' }), fake(500, undefined), failing]) {
          try { await a.getJson('x', f); out.push('ok'); } catch (e) { out.push([e.message, e.status]); }
        }
        out.push(await a.postJson('x', { a: 1 }, fake(200, { fine: true })));
        return out;
        """,
    )
    assert result[0] == ["Plain words.", 422]
    assert result[1][1] == 500 and "error (500)" in result[1][0]
    assert result[2] == ["Can't reach the Solum Builder server. Is it running?", 0]
    assert result[3] == {"fine": True}


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
