# ruff: noqa: E501  (JavaScript inside strings)
"""The editor's DOM-free modules (web/editor/*.js), run in Chromium: edit operations,
undo/redo, hotkeys, inspector fields, and the browser's pin geometry against parts.py."""

import json
from typing import Any

import pytest
from playwright.sync_api import Page

from solum.circuit.connectivity import connect, on_segment
from solum.circuit.io import parse_circuit
from solum.circuit.parts import PIN_OFFSETS, ota_pins, pin_positions, rotate, switch_pins
from solum.circuit.schema import SCHEMA_VERSION, Ota, Switch
from solum.circuit.switches import catalogue
from tests.ui.conftest import REPO, run

POS = (100, 40)


def expected_pins(offsets: dict[str, tuple[int, int]], rot: int) -> dict[str, list[int]]:
    return {
        n: [POS[0] + dx, POS[1] + dy]
        for n, (dx, dy) in ((n, rotate(o, rot)) for n, o in offsets.items())
    }


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_pin_positions_match_parts_table(js: Page, rot: int) -> None:
    sw = Switch(type="switch", ref="SW1B", kind="rotary-2p3t", pole="b")
    cases = {t: {"type": t} for t in PIN_OFFSETS}
    cases["switch"] = {"type": "switch", "kind": "rotary-2p3t", "pole": "b"}
    cases["opamp"] = {"type": "opamp", "show_pins": True}  # a single with all its pins
    got = run(
        js,
        """
        const { pinPositions, setSwitchKinds } = await m('schematic/symbols.js');
        setSwitchKinds(arg.kinds);
        const out = {};
        for (const [t, part] of Object.entries(arg.cases)) out[t] = pinPositions({ ...part, pos: arg.pos, rot: arg.rot });
        return out;
        """,
        {"cases": cases, "pos": list(POS), "rot": rot, "kinds": catalogue()},
    )
    expected = {t: expected_pins(PIN_OFFSETS[t], rot) for t in PIN_OFFSETS}
    expected["switch"] = expected_pins(switch_pins(sw), rot)
    # an OTA's table is a single's pins and a dual half's together (D-180): a single here
    expected["ota"] = expected_pins(ota_pins(Ota(type="ota", ref="IC1", model="CA3080")), rot)
    assert got == expected


def test_refs_and_new_parts(js: Page) -> None:
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R1' }, { ref: 'R3' }, { ref: 'IN' }] };
        const placed = e.addPart({ parts: [] }, 'resistor', [103, 47]);
        const diode = e.addPart({ parts: [] }, 'diode', [0, 0], 90, { diode: ['1N4148', 'X'] });
        const fallback = e.addPart({ parts: [] }, 'diode', [0, 0], 0, { diode: ['X'] });
        return {
          next: e.nextRef(c, 'R'), bareFree: e.nextRef({ parts: [] }, 'IN', true), bareTaken: e.nextRef(c, 'IN', true),
          placed, diode: diode.circuit.parts[0], fallback: fallback.circuit.parts[0].model,
        };
        """,
    )
    assert (r["next"], r["bareFree"], r["bareTaken"]) == ("R2", "IN", "IN2")
    assert r["placed"] == {
        "circuit": {"parts": [{"ref": "R1", "type": "resistor", "pos": [100, 50], "value": "10k"}]},
        "ref": "R1",
    }
    assert r["diode"] == {"ref": "D1", "type": "diode", "pos": [0, 0], "rot": 90, "model": "1N4148"}
    assert r["fallback"] == "X"  # the palette's model isn't in the library: the first one is


def test_a_part_dropped_on_a_wire_goes_in_series(js: Page) -> None:
    """A two-pin part placed, moved or turned onto a wire, both pins on it, cuts the wire
    between them, so it isn't shorted (D-112, D-113); across a wire (one pin on it), or
    with a jumper drawn from pin to pin, the wires stay."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [], wires: [{ from: [0, 50], to: [0, 60] }, { from: [-100, 0], to: [100, 0] }] };
        const capOff = e.addPart(c, 'capacitor', [0, 100]).circuit;
        const upright = e.addPart(c, 'capacitor', [0, -100], 90).circuit;
        return {
          inline: e.addPart(c, 'resistor', [0, 0]).circuit.wires,
          atEnd: e.addPart({ parts: [], wires: [{ from: [-20, 0], to: [100, 0] }] }, 'resistor', [0, 0]).circuit.wires,
          across: e.addPart(c, 'resistor', [0, 0], 90).circuit.wires,
          jumper: e.addPart({ parts: [], wires: [{ from: [-20, 0], to: [20, 0] }] }, 'resistor', [0, 0]).circuit.wires,
          moved: e.moveParts(capOff, ['C1'], 0, -100).wires,
          turned: e.rotatePart(e.moveParts(upright, ['C1'], 0, 100), 'C1').wires,
        };
        """,
    )
    rest = {"from": [0, 50], "to": [0, 60]}
    cut = [rest, {"from": [-100, 0], "to": [-20, 0]}, {"from": [20, 0], "to": [100, 0]}]
    assert r["inline"] == r["moved"] == cut
    assert r["atEnd"] == [{"from": [20, 0], "to": [100, 0]}]
    assert r["across"] == [rest, {"from": [-100, 0], "to": [100, 0]}]
    assert r["jumper"] == [{"from": [-20, 0], "to": [20, 0]}]
    assert sorted(map(str, r["turned"])) == sorted(map(str, cut))


def test_a_part_dropped_on_a_wire_joint_goes_in_series(js: Page) -> None:
    """The user's bug (2026-11-02): a trimmer dropped where two pieces of wire meet under
    it stayed shorted, lugs 1 and 3 on one net (D-164). Any part: the pieces are cut. A
    jumper in two pieces, pin to pin, stays."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const two = { parts: [], wires: [{ from: [0, 0], to: [100, 0] }, { from: [100, 0], to: [200, 0] }] };
        const three = { parts: [], wires: [{ from: [0, 0], to: [90, 0] }, { from: [90, 0], to: [110, 0] }, { from: [110, 0], to: [200, 0] }] };
        return {
          trimmer: e.addPart(two, 'trimmer', [100, 0]).circuit.wires,
          resistor: e.addPart(two, 'resistor', [100, 0]).circuit.wires,
          three: e.addPart(three, 'resistor', [100, 0]).circuit.wires,
          gap: e.addPart({ parts: [], wires: [{ from: [0, 0], to: [90, 0] }, { from: [110, 0], to: [200, 0] }] }, 'resistor', [100, 0]).circuit.wires,
          jumper: e.addPart({ parts: [], wires: [{ from: [80, 0], to: [100, 0] }, { from: [100, 0], to: [120, 0] }] }, 'resistor', [100, 0]).circuit.wires,
        };
        """,
    )
    cut = [{"from": [0, 0], "to": [80, 0]}, {"from": [120, 0], "to": [200, 0]}]
    assert r["trimmer"] == r["resistor"] == r["three"] == cut
    assert r["gap"] == [{"from": [0, 0], "to": [90, 0]}, {"from": [110, 0], "to": [200, 0]}]
    assert r["jumper"] == [{"from": [80, 0], "to": [100, 0]}, {"from": [100, 0], "to": [120, 0]}]


def test_upright_two_pin_text_sits_together(js: Page) -> None:
    """Turned upright, a resistor's value sits right under its ref, on the same side."""
    r = run(
        js,
        """
        const s = await m('schematic/symbols.js');
        const sym = s.symbol({ type: 'resistor', pins: [], draw: {} });
        return [0, 90, 180, 270].map((rot) => [s.placeText(sym, rot, 0), s.placeText(sym, rot, 1)]);
        """,
    )
    flat, right, flipped, left = r
    assert flat == [{"x": 0, "y": -12, "anchor": "middle"}, {"x": 0, "y": 22, "anchor": "middle"}]
    assert flipped == flat
    for ref, value in (right, left):
        assert (value["x"], value["anchor"]) == (ref["x"], ref["anchor"])
        assert value["y"] == pytest.approx(ref["y"] + 10)
    assert right[0]["anchor"] == "start" and left[0]["anchor"] == "end"


def test_wire_routing(js: Page) -> None:
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [], wires: [{ from: [50, 0], to: [0, 0] }] };
        return {
          wide: e.route([0, 0], [50, 20]), tall: e.route([0, 0], [10, 50]), straight: e.route([0, 0], [0, 33]),
          none: e.route([1, 1], [2, 2]), dedup: e.addWire(c, [0, 0], [50, 0]).wires.length,
        };
        """,
    )
    assert r["wide"] == [
        {"from": [0, 0], "to": [50, 0]},
        {"from": [50, 0], "to": [50, 20]},
    ]  # horizontal first
    assert r["tall"] == [
        {"from": [0, 0], "to": [0, 50]},
        {"from": [0, 50], "to": [10, 50]},
    ]  # vertical first
    assert r["straight"] == [{"from": [0, 0], "to": [0, 30]}]  # snapped to the 10 grid
    assert r["none"] == []
    assert r["dedup"] == 1  # the same segment, reversed, isn't added twice


def assert_path(
    wires: list[dict[str, list[int]]],
    a: tuple[int, int],
    b: tuple[int, int],
    bends: int,
    clear_of: list[tuple[int, int, int, int]] = (),  # type: ignore[assignment]
) -> None:
    """`wires` are one square path from a to b with `bends` bends, through no box's inside."""
    ends: dict[tuple[int, int], int] = {}
    for w in wires:
        (x1, y1), (x2, y2) = w["from"], w["to"]
        assert x1 == x2 or y1 == y2, f"slanted wire {w}"
        for x0, y0, xb, yb in clear_of:
            steps = max(abs(x2 - x1), abs(y2 - y1)) // 10
            for i in range(steps + 1):
                x, y = x1 + (x2 - x1) * i // max(steps, 1), y1 + (y2 - y1) * i // max(steps, 1)
                assert not (x0 < x < xb and y0 < y < yb), f"{w} runs through {clear_of}"
        for p in ((x1, y1), (x2, y2)):
            ends[p] = ends.get(p, 0) + 1
    assert {p for p, n in ends.items() if n == 1} == {a, b}, wires
    assert len(wires) == bends + 1, wires


def test_four_turns_leave_the_wires_as_they_began(js: Page) -> None:
    """The user (2026-11-13): V+ down through R1 to ground, a wire from under R1 across to
    R2, R2 to ground; turning R2 a full circle left the straight wire with kinks, more
    each time round. A turned part's wires are routed afresh (D-317), so four turns bring
    back the wires it began with, and eight the same again."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R1', type: 'resistor', pos: [0, 0], rot: 90, value: '100k' },
                            { ref: 'R2', type: 'resistor', pos: [100, 60], rot: 90, value: '10k' }],
                    wires: [{ from: [0, -60], to: [0, -20] }, { from: [0, 20], to: [0, 100] },
                            { from: [0, 40], to: [100, 40] }, { from: [100, 80], to: [100, 120] }],
                    labels: [{ net: 'V+', pos: [0, -60] }, { net: 'GND', pos: [0, 100] }, { net: 'GND', pos: [100, 120] }] };
        const ends = (x) => x.wires.map((w) => [w.from, w.to].map(String).sort().join(' ')).sort();
        const seen = [];
        let x = c;
        for (let i = 0; i < 8; i++) seen.push(ends((x = e.rotatePart(x, 'R2'))));
        return { began: ends(c), seen };
        """,
    )
    assert r["seen"][3] == r["seen"][7] == r["began"]
    assert r["seen"][:4] == r["seen"][4:]  # each turn the same the second time round


def test_move_and_rotate_drag_connections_along(js: Page) -> None:
    """R1 at (100, 100) has pins at (80, 100) and (120, 100). A wire leaves pin 2 and a
    label sits on pin 1; both follow the part, and the wire stays square."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R1', type: 'resistor', pos: [100, 100], value: '1k' }, { ref: 'R2', type: 'resistor', pos: [300, 100], value: '1k' }],
                    wires: [{ from: [120, 100], to: [200, 100] }], labels: [{ net: 'IN', pos: [80, 100] }, { net: 'X', pos: [280, 100] }] };
        const before = JSON.stringify(c);
        const moved = e.moveParts(c, ['R1'], 21, 29);
        const turned = e.rotatePart(c, 'R1');
        const back = e.rotatePart(e.rotatePart(e.rotatePart(turned, 'R1'), 'R1'), 'R1');
        return { moved, turned, back: back.parts[0], unchanged: JSON.stringify(c) === before, still: e.moveParts(c, ['R1'], 2, 3) === c };
        """,
    )
    moved = r["moved"]
    assert moved["parts"][0]["pos"] == [120, 130]  # (21, 29) snaps to (20, 30)
    assert moved["parts"][1]["pos"] == [300, 100]
    # the wire is re-laid from its far end to the moved pin: square, one bend, clear of R1
    assert_path(moved["wires"], (200, 100), (140, 130), bends=1, clear_of=[(100, 120, 140, 140)])
    assert moved["labels"] == [{"net": "IN", "pos": [100, 130]}, {"net": "X", "pos": [280, 100]}]
    turned = r["turned"]
    assert turned["parts"][0]["rot"] == 90  # pins now at (100, 80) and (100, 120)
    # turned R1's body is (90, 80)..(110, 120): the wire goes round it to the lower pin
    assert_path(turned["wires"], (200, 100), (100, 120), bends=1, clear_of=[(90, 80, 110, 120)])
    assert turned["labels"][0] == {"net": "IN", "pos": [100, 80]}
    assert "rot" not in r["back"]  # four quarter turns: back to the default
    assert r["unchanged"] and r["still"]


def test_delete_rename_update(js: Page) -> None:
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = {
          parts: [{ ref: 'Q1', type: 'jfet', model: 'J201', note: 'first stage' }, { ref: 'TR1', type: 'trimmer', value: '50k', bias_target: { node: 'Q1.D', volts: 9 } },
                  { ref: 'Q10', type: 'jfet', model: 'J201' }, { ref: 'TR2', type: 'trimmer', value: '50k', bias_target: { node: 'Q10.D', volts: 4 } }],
          wires: [{ from: [0, 0], to: [10, 0] }, { from: [0, 0], to: [0, 10] }], labels: [{ net: 'A', pos: [0, 0] }, { net: 'B', pos: [9, 9] }],
          net_notes: { A: 'input', B: 'the bias' }, probes: { in: 'Q1.G', out: 'OUT' },
          dismissed: [{ rule: 'jfet-vds-low', refs: ['Q1'], nets: ['Q1.D'], reason: 'on purpose' }, { rule: 'no-dc-path', nets: ['Q10.S'] }],
        };
        const deleted = e.deleteItems(c, { parts: ['Q1'], wires: [0], labels: [1] });
        const renamed = e.renamePart(c, 'Q1', 'Q5');
        const updated = e.updatePart(c, 'TR1', { value: '100k', bias_target: null });
        const target = e.setDrainTarget(c, 'Q1', 'TR2', 7.5);
        const cleared = e.setDrainTarget(c, 'Q1', null, null);
        return { deleted, renamed, updated: updated.parts[1], target: target.parts.map((p) => p.bias_target ?? null),
                 found: e.drainTarget(target, 'Q1'), none: e.drainTarget(cleared, 'Q1'), relabel: e.renameLabel(c, 1, 'C'),
                 onto: e.renameLabel(c, 1, 'A').net_notes };
        """,
    )
    d = r["deleted"]
    assert [p["ref"] for p in d["parts"]] == ["TR1", "Q10", "TR2"]
    assert d["wires"] == [{"from": [0, 0], "to": [0, 10]}]
    assert d["labels"] == [{"net": "A", "pos": [0, 0]}]
    assert d["net_notes"] == {"A": "input", "B": "the bias"}  # the deleted part's note went with it
    n = r["renamed"]
    assert n["parts"][0]["ref"] == "Q5"
    assert n["parts"][1]["bias_target"] == {"node": "Q5.D", "volts": 9}
    assert n["parts"][3]["bias_target"] == {"node": "Q10.D", "volts": 4}  # Q10 isn't Q1
    assert n["parts"][0]["note"] == "first stage"  # the note is on the part
    assert n["probes"] == {"in": "Q5.G", "out": "OUT"}
    assert n["dismissed"] == [  # dismissed problems follow the part and its pins' nets (D-176)
        {"rule": "jfet-vds-low", "refs": ["Q5"], "nets": ["Q5.D"], "reason": "on purpose"},
        {"rule": "no-dc-path", "nets": ["Q10.S"]},
    ]
    assert r["updated"] == {"ref": "TR1", "type": "trimmer", "value": "100k"}
    assert r["target"] == [
        None,
        None,
        None,
        {"node": "Q1.D", "volts": 7.5},
    ]  # TR1 lost Q1.D, TR2 gained it
    assert r["found"] == {"trimmer": "TR2", "volts": 7.5}
    assert r["none"] is None
    assert r["relabel"]["labels"][1] == {"net": "C", "pos": [9, 9]}
    # B's only label renamed: its note follows; onto A, which has a note, it stays put
    assert r["relabel"]["net_notes"] == {"A": "input", "C": "the bias"}
    assert r["onto"] == {"A": "input", "B": "the bias"}


def test_find_ref_ignores_case_and_spaces(js: Page) -> None:
    got = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R12' }, { ref: 'R1' }, { ref: 'IN' }] };
        return ['r12', ' R 1 ', 'in', 'R2', '', '  ', 'R'].map((t) => e.findRef(c, t));
        """,
    )
    assert got == ["R12", "R1", "IN", None, None, None, None]


def test_split_values(js: Page) -> None:
    r = run(js, "const e = await m('editor/edit.js'); return e.splitValues(' 4k7, 10k ,,22k ');")
    assert r == ["4k7", "10k", "22k"]


def test_set_rails_by_polarity(js: Page) -> None:
    """Power → Advanced (D-069): V+ and V- take a size, their sign is fixed; a rail turned
    off hands its labels (an op-amp's power pins' too) to the rail left; with none left,
    refused."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const err = (f) => { try { f(); return null; } catch (x) { return x.message; } };
        const lab = (net) => ({ net, pos: [0, 0] });
        const fuzz = { parts: [{ ref: 'IC1', type: 'opamp' }], labels: [lab('V-'), lab('out'), lab('V-')], power: { rails: { 'V-': -9 } } };
        const swapped = e.setRails(fuzz, { 'V+': '9', 'V-': '' });
        const both = e.setRails(fuzz, { 'V+': '12V', 'V-': '\u221212' });
        const back = e.setRails(both, { 'V+': '12', 'V-': '' });
        return {
          swapped: [swapped.power.rails, swapped.labels.map((l) => l.net)],
          both: [both.power.rails, both.labels.map((l) => l.net)],
          back: back.labels.map((l) => l.net),
          none: err(() => e.setRails(fuzz, { 'V+': '', 'V-': '' })),
          unused: e.setRails({ parts: [], labels: [], power: { rails: { 'V-': -9 } } }, { 'V+': '', 'V-': '' }).power.rails,
          negativeVplus: err(() => e.setRails(fuzz, { 'V+': '-9', 'V-': '9' })),
          zero: err(() => e.setRails(fuzz, { 'V+': '', 'V-': '0' })),
          words: err(() => e.setRails(fuzz, { 'V+': 'nine', 'V-': '' })),
        };
        """,
    )
    # IC1's power pin label (the second V-) is a label like any other (D-140)
    assert r["swapped"] == [{"V+": 9}, ["V+", "out", "V+"]]
    assert r["both"] == [{"V+": 12, "V-": -12}, ["V-", "out", "V-"]]
    assert r["back"] == ["V+", "out", "V+"]  # one rail left: the V- bar joins it
    assert r["none"] == "V- is still used on the sheet (2 labels). Keep V-, or delete those first."
    assert r["unused"] == {}
    assert (
        r["negativeVplus"] == "V+ is the positive supply. For a negative one, fill in V- instead."
    )
    assert (
        r["zero"]
        == r["words"].replace("V+", "V-")
        == "V-: give a voltage like 9, or leave it empty for none."
    )


def test_supply_tile_adds_its_rail(js: Page) -> None:
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [], labels: [], power: { rails: { 'V+': 12 } } };
        const minus = e.addSupply(c, 'V-', [10, 21]);
        return { minus: [minus.power.rails, minus.labels], again: e.addSupply(minus, 'V-', [0, 0]).power.rails,
                 bare: e.addSupply({ parts: [] }, 'V+', [0, 0]).power.rails };
        """,
    )
    assert r["minus"] == [{"V+": 12, "V-": -12}, [{"net": "V-", "pos": [10, 20]}]]
    assert r["again"] == {"V+": 12, "V-": -12}
    assert r["bare"] == {"V+": 9}


def test_history_amend_changes_every_kept_state(js: Page) -> None:
    """A file rename: the done and the undone steps all take the new name (D-287)."""
    r = run(
        js,
        """
        const { History } = await m('editor/history.js');
        const h = new History();
        h.record({ name: 'old', n: 1 }, 'one'); h.record({ name: 'old', n: 2 }, 'two');
        h.undo({ name: 'old', n: 3 });
        h.amend((c) => ({ ...c, name: 'new' }));
        const redone = h.redo({ name: 'new', n: 2 });
        return [redone, h.undo(redone), h.undo({ name: 'new', n: 2 }), h.labels];
        """,
    )
    assert r == [
        {"name": "new", "n": 3},
        {"name": "new", "n": 2},
        {"name": "new", "n": 1},
        {"undo": None, "redo": "one"},
    ]


def test_history(js: Page) -> None:
    r = run(
        js,
        """
        const { History } = await m('editor/history.js');
        const h = new History(2);
        h.record('a', 'one'); h.record('b', 'two');
        const labels = h.labels;
        const u1 = h.undo('c'), u2 = h.undo('b'), u3 = h.undo('a');
        const r1 = h.redo('a');
        h.record('b2', 'three');  // a new edit clears redo
        const afterNew = h.labels;
        const limited = new History(2); limited.record(1, 'x'); limited.record(2, 'y'); limited.record(3, 'z');
        const kept = [limited.undo(4), limited.undo(3), limited.undo(2)];
        const d = new History(); d.record('a', 'one'); d.discard();
        // an edit session: squash keeps its steps as one, rollback forgets them
        const sq = new History(); sq.record('a', 'one'); const m1 = sq.mark(); sq.record('b', 'two'); sq.record('c', 'three');
        sq.squash(m1, 'session');
        const squashed = [sq.labels.undo, sq.undo('d'), sq.labels.undo];
        const rb = new History(); rb.record('a', 'one'); const m2 = rb.mark(); rb.record('b', 'two'); rb.rollback(m2);
        const empty = new History(); const m3 = empty.mark(); empty.squash(m3, 'session');
        const lim = new History(2); lim.record(1, 'x'); const m4 = lim.mark(); lim.record(2, 'y'); lim.record(3, 'z'); lim.squash(m4, 's');
        return { labels, u: [u1, u2, u3], r1, afterNew, kept, discarded: d.labels, squashed, rolledBack: rb.labels.undo,
          emptySession: empty.labels.undo, limited: [lim.labels.undo, lim.undo(4), lim.undo(2)] };
        """,
    )
    assert r["labels"] == {"undo": "two", "redo": None}
    assert r["u"] == ["b", "a", None]
    assert r["r1"] == "b"
    assert r["afterNew"] == {"undo": "three", "redo": None}
    assert r["kept"] == [3, 2, None]  # only the newest two steps are kept
    assert r["discarded"] == {"undo": None, "redo": None}
    assert r["squashed"] == ["session", "b", "one"]  # undo goes back to before the session
    assert r["rolledBack"] == "one"
    assert r["emptySession"] is None  # nothing recorded: no step
    assert r["limited"] == ["s", 2, None]  # the mark holds when the limit drops old steps


def test_history_puts_back_the_selection(js: Page) -> None:
    """D-148: undo and redo give back the selection that went with each circuit: undo the
    one before the edit, redo the one there was when it was undone; a squash keeps the
    first step's."""
    r = run(
        js,
        """
        const { History } = await m('editor/history.js');
        const h = new History();
        h.record('a', 'move', '', 'wires 1,2');    // 'a' with two wires selected, moved to 'b'
        h.record('b', 'value', '', 'R1');          // R1 picked on 'b', its value changed: 'c'
        const u1 = [h.undo('c', 'R1 now'), h.restored];
        const u2 = [h.undo('b', 'clicked C3'), h.restored];
        const r1 = [h.redo('a', 'wires 1,2'), h.restored];
        const r2 = [h.redo('b', 'R1'), h.restored];
        const none = new History(); none.record('a', 'x'); const n = [none.undo('b'), none.restored];
        const sq = new History(); const m0 = sq.mark(); sq.record('a', 'one', '', 'first'); sq.record('b', 'two', '', 'second');
        sq.squash(m0, 'session');
        return { u1, u2, r1, r2, n, squashed: [sq.undo('c', 'now'), sq.restored] };
        """,
    )
    assert r["u1"] == ["b", "R1"]
    assert r["u2"] == ["a", "wires 1,2"]  # the moved wires are selected again
    assert r["r1"] == ["b", "clicked C3"]  # what was selected there when it was undone
    assert r["r2"] == ["c", "R1 now"]
    assert r["n"] == ["a", None]  # recorded with no selection: none to put back
    assert r["squashed"] == ["a", "first"]


def test_history_session_and_rows(js: Page) -> None:
    """Edit curve's session (D-101): undo stops at its start and redo at its end; the
    History pane's rows, newest first, with how far each is and what's out of reach; the
    session's steps with the states before and after each; Discard keeps redo from before."""
    r = run(
        js,
        """
        const { History } = await m('editor/history.js');
        const h = new History();
        h.record('c0', 'Move R1'); h.record('c1', 'Add C2');
        const mark = h.begin();
        h.record('c2', 'Change C3', 'curve'); h.record('c3', 'Move R9');  // one from outside
        const rows = h.rows().map((x) => [x.label, x.kind, x.go, x.session, x.locked, x.source]);
        const steps = h.sessionSteps('c4').map((x) => [x.label, x.source, x.before, x.after]);
        const u = [h.undo('c4'), h.undo('c3'), h.atSessionStart, h.undo('c2'), h.labels];
        const undoneRows = h.rows().slice(0, 2).map((x) => [x.label, x.kind, x.go]);
        const re = h.redo('c2');
        h.squash(mark, 'Edit curve: C3');
        const kept = [h.session, h.labels.undo, h.undo('c4'), h.labels.undo];
        // Discard keeps the redo steps from before the session
        const d = new History(); d.record('a', 'one'); d.record('b', 'two'); d.undo('c');
        const m2 = d.begin(); const before = d.redo('b') === null; d.rollback(m2);
        return { rows, steps, u, undoneRows, re, kept, before, afterDiscard: d.labels };
        """,
    )
    assert r["rows"] == [
        ["Move R9", "current", 0, True, False, ""],
        ["Change C3", "done", -1, True, False, "curve"],
        ["Add C2", "done", -2, False, False, ""],  # where the session began: reachable
        ["Move R1", "done", -3, False, True, ""],  # older: locked until Keep or Discard
        ["Opened", "start", -4, False, True, ""],
    ]
    assert r["steps"] == [["Change C3", "curve", "c2", "c3"], ["Move R9", "", "c3", "c4"]]
    assert r["u"] == ["c3", "c2", True, None, {"undo": None, "redo": "Change C3"}]
    assert r["undoneRows"] == [["Move R9", "undone", 2], ["Change C3", "undone", 1]]
    assert r["re"] == "c3"
    # Keep: the session is one step (the undone one dropped), and undo works on the circuit again
    assert r["kept"] == [None, "Edit curve: C3", "c2", "Add C2"]
    assert r["before"] is True  # in a session, redo from before it is out of reach
    assert r["afterDiscard"] == {"undo": "one", "redo": "two"}


def test_hotkeys(js: Page) -> None:
    presses = [
        {"key": "r"},
        {"key": "R", "shift": True},
        {"key": "j"},
        {"key": " "},
        {"key": "Delete"},
        {"key": "Backspace"},
        {"key": "z", "ctrl": True},
        {"key": "Z", "ctrl": True, "shift": True},
        {"key": "y", "ctrl": True},
        {"key": "s", "meta": True},
        {"key": "Escape"},
        {"key": "l"},
        {"key": "g"},
        {"key": "w"},
        {"key": "r", "alt": True},
        {"key": "x"},
        {"key": "c", "ctrl": True},
        {"key": "Enter", "ctrl": True},
        {"key": "Enter"},
        {"key": "v", "meta": True},
        {"key": "a", "ctrl": True},
        {"key": "b"},
        {"key": "q", "ctrl": True},
        {"key": "f", "ctrl": True},
    ]
    got = run(
        js, "const k = await m('editor/keys.js'); return arg.map((p) => k.actionFor(p));", presses
    )
    assert got == [
        {"action": "place", "type": "resistor"},
        {"action": "place", "type": "resistor"},
        {"action": "place", "type": "jfet"},
        {"action": "rotate"},
        {"action": "delete"},
        {"action": "delete"},
        {"action": "undo"},
        {"action": "redo"},
        {"action": "redo"},
        {"action": "save"},
        {"action": "cancel"},
        {"action": "label"},
        {"action": "ground"},
        {"action": "wire"},
        None,
        {"action": "text"},  # X: a text block (D-091)
        {"action": "copy"},
        {"action": "run"},
        {"action": "inspect"},
        {"action": "paste"},
        {"action": "selectAll"},
        {"action": "insertBlock"},
        None,
        {"action": "find"},
    ]


def test_the_hot_keys_list_matches_what_the_keys_do(js: Page) -> None:
    """Help → Hot keys reads keys.js's own list: each row that names a key does what it
    says, every action a key can start is listed, and every palette key is there."""
    got = run(
        js,
        """const k = await m('editor/keys.js'); const e = await m('editor/edit.js');
        const rows = k.hotkeyGroups().flatMap((g) => g.rows);
        const tied = rows.filter((r) => r.press);
        return {
          wrong: tied.filter((r) => k.actionFor(r.press)?.action !== r.action).map((r) => r.keys),
          actions: [...new Set(tied.map((r) => r.action))].sort(),
          parts: rows.filter((r) => r.action === 'place').length,
          palette: e.PALETTE.filter((p) => p.key).length,
        };""",
        None,
    )
    assert got["wrong"] == []
    assert got["actions"] == sorted(
        [
            "place",
            "wire",
            "ground",
            "label",
            "text",
            "insertBlock",
            "rotate",
            "inspect",
            "delete",
            "cancel",
            "undo",
            "redo",
            "copy",
            "paste",
            "selectAll",
            "find",
            "save",
            "run",
        ]
    )
    assert got["parts"] == got["palette"] == 17


def test_palette_hotkeys_are_unique(js: Page) -> None:
    keys = run(js, "const e = await m('editor/edit.js'); return e.PALETTE.map((p) => p.key);")
    keys = [k for k in keys if k is not None]  # a tile may have none (Quad op-amp, Inductor)
    reserved = {"l", "g", "w", "x", "b"}  # the keys keys.js takes
    assert len(keys) == len(set(keys)) and not reserved & set(keys)


def test_a_measured_parts_hint_gives_the_datasheet_range(js: Page) -> None:
    """The model is one typical unit; yours can be anywhere in the datasheet's range, said
    when the record has one (J201, 2N3904), and said to be missing when not."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const j201 = { idss: { min: 2e-4, max: 1e-3 }, vp: { min: -1.5, max: -0.3 } };
        return [
          f.unitHint('J201', [['Idss', j201.idss, 1e3, ' mA'], ['Vp', j201.vp, 1, ' V']]),
          f.unitHint('2N3904', [['hFE', { min: 100, max: 300, at: { ic: 0.01 } }, 1, '']]),
          f.unitHint('AC128', [['hFE', undefined, 1, '']]),
          f.unitHint('OC81D', [['hFE', undefined, 1, '']], true),
        ];
        """,
    )
    assert r == [
        "The model is one typical J201. Your unit can be anywhere in the datasheet's range: "
        "Idss 0.2\u20131 mA, Vp \u22121.5 to \u22120.3 V. Measure yours to simulate it.",
        "The model is one typical 2N3904. Your unit can be anywhere in the datasheet's range: "
        "hFE 100\u2013300 at 10 mA. Measure yours to simulate it.",
        "The model is one typical AC128. Yours differs, and this model's datasheet range "
        "isn't in yet. Measure yours to simulate it.",
        "The model is an estimate: no OC81D datasheet with curves was found, so it's a "
        "related part's shape scaled to the OC81D's published figures. Measure yours to "
        "simulate it.",
    ]


def test_a_tester_gain_below_the_sheets_curve_says_so(js: Page) -> None:
    """9b: the MPSA06's tester gain (near 0.34 mA) is below its sheet's curve (0.52 mA)."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        return [f.belowSheet({ hfe: 84, tester_ic: 3.43e-4, sheet_low_ic: 5.2e-4 }).about,
                f.belowSheet({ hfe: 234 })];
        """,
    )
    assert r == [
        "What the model reads on a 9 V tester. The tester runs it near 0.34 mA, below the "
        "0.52 mA where its datasheet's gain curve starts, so this figure is the model's "
        "extrapolation, not the sheet's.",
        {},
    ]


def test_a_forms_info_says_each_shown_fields_about(js: Page) -> None:
    """9c's info pass: a field's `about` goes in the form's ⓘ under its label; a row
    hidden when it opens is left out; a form with none has no ⓘ."""
    r = run(
        js,
        """
        const form = await m('editor/form.js');
        const host = document.createElement('div');
        document.body.append(host);
        const fields = [
          { name: 'a', label: 'Gain', kind: 'text', value: '', hint: 'Short.', about: 'The long way.' },
          { name: 'b', label: 'Hidden', kind: 'text', value: '', about: 'Not shown.', hidden: true },
          { name: 'c', label: 'Leakage', kind: 'text', value: '', about: ['One.', 'Two.'] },
        ];
        form.openForm(host, { title: 'Q1', fields, onSubmit: async () => null });
        host.querySelector('.popup-title .info-button').click();
        const pop = [...document.querySelectorAll('.info-pop')].find((p) => !p.hidden);
        const said = [...pop.children].map((e) => [e.tagName, e.textContent]);
        form.openForm(host, { title: 'R1', fields: [{ name: 'v', label: 'Value', kind: 'text', value: '' }], onSubmit: async () => null });
        const none = host.querySelectorAll('.popup-title .info-button').length;
        form.closeForm();
        return { said, none, shut: pop.hidden };
        """,
    )
    assert r["said"] == [
        ["H4", "Q1"],
        ["H5", "Gain"],
        ["P", "The long way."],
        ["H5", "Leakage"],
        ["P", "One."],
        ["P", "Two."],
    ]
    assert r["none"] == 0
    assert r["shut"]  # opening another form shut it


def test_a_batterys_form_says_what_its_wiring_does(js: Page) -> None:
    """9c: the battery's Drained hint follows the view's `battery_wiring`: alone (no DC
    jack), on the DC jack's battery lug, or beside the adapter."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const part = { ref: 'BAT1', type: 'battery', volts: 9 };
        const hint = (w) => f.inspectorFields(part, { circuit: { parts: [part] }, models: {}, view: { battery_wiring: w } })
          .find((x) => x.name === 'state').hint ?? null;
        return ['alone', 'lug', 'beside', 'apart', null].map(hint);
        """,
    )
    assert r == [
        "It powers the circuit: the Power menu is greyed.",
        "It powers the circuit while no plug is in the DC jack (Knobs → Power).",
        "Its + isn't on the DC jack's battery lug: it stays connected with a plug in.",
        "A supply on its own net: V+ comes from the Power menu.",
        None,
    ]


def test_a_batterys_info_lists_every_way_to_wire_it(js: Page) -> None:
    """D-202 (the user: "make sure that makes it into the ⓘ"): whatever its wiring, the
    battery's ⓘ has its own case first, then every way to wire its + and its - (minus)."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const part = { ref: 'BAT1', type: 'battery', volts: 9 };
        const about = (w) => f.inspectorFields(part, { circuit: { parts: [part] }, models: {}, view: { battery_wiring: w } })
          .find((x) => x.name === 'state').about;
        return { apart: about('apart'), none: about(null), ways: f.BATTERY_WAYS };
        """,
    )
    ways = r["ways"]
    assert r["apart"][0].startswith("Its + reaches no supply rail")
    assert r["apart"][1 : 1 + len(ways)] == ways == r["none"][: len(ways)]
    text = " ".join(ways)
    for case in ("no DC jack drawn", "battery lug", "beside a DC jack", "any other net", "ring"):
        assert case in text


def test_a_mosfets_form_picks_a_model_and_sweeps_models(js: Page) -> None:
    """D-175: the model, then (D-176) the drain target and its trimmer, as a JFET's; a model
    change patches it; a drain target set here goes on the trimmer; sweeping tries models."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const part = { ref: 'Q3', type: 'mosfet', model: '2N7000' };
        const trimmer = { ref: 'TR1', type: 'trimmer', value: '50k', bias_target: { node: 'Q3.D', volts: 4.5 } };
        const models = { mosfet: ['2N7000', 'BS170'] };
        const fields = f.inspectorFields(part, { circuit: { parts: [part, trimmer] }, models });
        return {
          fields: fields.map((x) => [x.name, x.value]),
          options: fields[1].options,
          patch: f.editFrom(part, { ref: 'Q3', model: 'BS170' }, {}).patch,
          drain: f.editFrom(part, { ref: 'Q3', model: '2N7000', drain_volts: '5', drain_trimmer: 'TR1' }, {}).drain,
          sweep: f.sweepField(part),
        };
        """,
    )
    assert r["fields"] == [
        ["ref", "Q3"],
        ["model", "2N7000"],
        ["drain_volts", "4.5"],
        ["drain_trimmer", "TR1"],
        ["at_rest", ""],  # D-238
    ]
    assert [o[0] for o in r["options"]] == ["2N7000", "BS170"]
    assert r["patch"] == {"model": "BS170"}
    assert r["drain"] == {"trimmer": "TR1", "volts": 5}
    assert r["sweep"] == "model"


def test_a_model_dropdown_lists_yours_then_stock(js: Page) -> None:
    """9c (the user, 2026-11-03: yours first): two groups once you've added a model of that
    type, one plain list until then; a model no list has (a file from elsewhere) stays on
    top, as before. A chip's dropdown groups the same way."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const options = (part, models) => f.inspectorFields(part, { circuit: { parts: [part] }, models, chips: {} }).find((x) => x.name === 'model').options;
        const q = { ref: 'Q1', type: 'mosfet', model: '2N7000' };
        return {
          plain: options(q, { mosfet: ['2N7000', 'BS170'], yours: [] }),
          grouped: options(q, { mosfet: ['2N7000', 'BS170', 'MY-FET'], yours: ['MY-FET', 'D-acme'] }),
          missing: options({ ...q, model: 'OLD' }, { mosfet: ['2N7000', 'MY-FET'], yours: ['MY-FET'] }),
          noYours: options(q, { mosfet: ['2N7000'] }),
          opamp: options({ ref: 'IC1', type: 'opamp', model: 'TL071' }, { opamp: ['MY-OA', 'TL071'], yours: ['MY-OA'] }),
        };
        """,
    )
    assert r["plain"] == [["2N7000", "2N7000"], ["BS170", "BS170"]]
    assert r["grouped"] == [
        ["MY-FET", "MY-FET", "Added by you"],
        ["2N7000", "2N7000", "Stock"],
        ["BS170", "BS170", "Stock"],
    ]
    assert r["missing"] == [
        ["OLD", "OLD"],
        ["MY-FET", "MY-FET", "Added by you"],
        ["2N7000", "2N7000", "Stock"],
    ]
    assert r["noYours"] == [["2N7000", "2N7000"]]
    assert r["opamp"] == [["MY-OA", "MY-OA", "Added by you"], ["TL071", "TL071", "Stock"]]


def test_an_inductors_form_fills_from_a_measured_one(js: Page) -> None:
    """D-173: a preset fills L and wire resistance; values typed over it are your own."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const inductors = [{ kind: 'fasel-red', name: 'Fasel red (toroid)', measured: 'x', l: '666m', r: '15.65' }];
        const part = { ref: 'L1', type: 'inductor', value: '666m', resistance: 15.65, kind: 'fasel-red' };
        const fields = f.inspectorFields(part, { circuit: { parts: [part] }, models: {}, inductors });
        const edit = (values) => f.editFrom(part, { ref: 'L1', ...values }, { inductors }).patch;
        return {
          fields: fields.map((x) => [x.name, x.value]),
          options: fields[1].options, fills: fields[1].fills,
          kept: edit({ kind: 'fasel-red', value: '666m', resistance: '15.65' }),
          typed: edit({ kind: 'fasel-red', value: '600m', resistance: '15.65' }),
          own: edit({ kind: 'own', value: '1', resistance: '' }),
          sweep: f.sweepPrompt(part).placeholder,
        };
        """,
    )
    assert r["fields"] == [["ref", "L1"], ["kind", "fasel-red"], ["value", "666m"],
                           ["resistance", "15.65"]]  # fmt: skip
    assert r["options"] == [["fasel-red", "Fasel red (toroid) (666mH, 15.65 Ω)"],
                            ["own", "Your own values"]]  # fmt: skip
    assert r["fills"] == {"fasel-red": {"value": "666m", "resistance": "15.65"}}
    assert r["kept"] == {"value": "666m", "kind": "fasel-red", "resistance": 15.65}
    assert r["typed"]["kind"] is None
    assert r["own"] == {"value": "1", "kind": None, "resistance": None}
    assert r["sweep"] == "e.g. 400m, 500m, 660m"


def test_inspector_fields_for_a_transistors_gain(js: Page) -> None:
    """D-130: the model's gain or a measured one, which starts at the model's; nothing for
    a subcircuit model (no card to copy)."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const q = { ref: 'Q1', type: 'bjt', model: 'AC128' };
        const ctx = { circuit: { parts: [q] }, models: { bjt: ['AC128'] }, bjts: { 'AC128': { hfe: 85, leakage: 9.815e-6, germanium: true } } };
        const stock = f.inspectorFields(q, ctx).map((x) => [x.name, x.value]);
        const mine = f.inspectorFields({ ...q, measured: { hfe: 64 } }, ctx).map((x) => [x.name, x.value]);
        const none = f.inspectorFields({ ...q, model: 'X' }, ctx).map((x) => x.name);
        const edit = f.editFrom(q, { ref: 'Q1', model: 'AC128', bjt_spec: 'measured', hfe: '72', leakage: '150' }).patch;
        const back = f.editFrom(q, { ref: 'Q1', model: 'AC128', bjt_spec: 'model', hfe: '72' }).patch;
        let error = null;
        try { f.editFrom(q, { ref: 'Q1', bjt_spec: 'measured', hfe: '80', leakage: '' }); } catch (e) { error = e.message; }
        // silicon: its model has no leakage, so the form asks for the gain only
        const si = { ref: 'Q4', type: 'bjt', model: '2N5089' };
        const sictx = { circuit: { parts: [si] }, models: { bjt: ['2N5089'] }, bjts: { '2N5089': { hfe: 1434, leakage: 0, germanium: false } } };
        const silicon = f.inspectorFields(si, sictx).map((x) => [x.name, x.label]);
        const siEdit = f.editFrom(si, { ref: 'Q4', model: '2N5089', bjt_spec: 'measured', hfe: '900' }).patch;
        return { stock, mine, none, edit, back, error, silicon, siEdit };
        """,
    )
    # a v10 measured part (no leakage) starts its leakage box at the model's
    # (9.815e-6 A in µA is 9.81499…, so toPrecision(3) gives "9.81")
    # the model's own values show, read-only, while it's picked (the user, 2026-10-28)
    model = [["model_hfe", "85"], ["model_leakage", "9.81"]]
    at_rest = ["at_rest", ""]
    assert r["stock"][2:] == [
        ["bjt_spec", "model"],
        *model,
        ["hfe", "85"],
        ["leakage", "9.81"],
        at_rest,
    ]
    assert r["mine"][2:] == [
        ["bjt_spec", "measured"],
        *model,
        ["hfe", "64"],
        ["leakage", "9.81"],
        at_rest,
    ]
    assert "bjt_spec" not in r["none"]
    assert r["edit"]["measured"] == {"hfe": 72, "leakage": pytest.approx(150e-6)}
    assert r["back"]["measured"] is None
    assert r["error"] == "Give your transistor's measured hFE and leakage, or pick the model's."
    assert r["silicon"][2:] == [
        ["bjt_spec", "Gain"],
        ["model_hfe", "Model's hFE"],
        ["hfe", "Measured hFE"],
        ["at_rest", "At rest"],
    ]
    assert r["siEdit"]["measured"] == {"hfe": 900}


def test_a_transistor_can_be_off_by_design(js: Page) -> None:
    """D-238: each transistor's form asks whether it's off at rest on purpose (a rectifier,
    a switch); picking it sets `off_by_design`, picking back removes it."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const parts = [{ ref: 'Q1', type: 'bjt', model: '2N5089' }, { ref: 'Q2', type: 'jfet', model: 'J201' },
                       { ref: 'Q3', type: 'mosfet', model: '2N7000' }];
        const at = (q) => f.inspectorFields(q, { circuit: { parts }, models: {} }).find((x) => x.name === 'at_rest')?.value;
        const q = parts[0];
        return {
          shown: parts.map(at), marked: at({ ...q, off_by_design: true }),
          off: f.editFrom(q, { ref: 'Q1', model: '2N5089', at_rest: 'off' }).patch.off_by_design,
          on: f.editFrom({ ...q, off_by_design: true }, { ref: 'Q1', model: '2N5089', at_rest: '' }).patch.off_by_design,
        };
        """,
    )
    assert r == {"shown": ["", "", ""], "marked": "off", "off": True, "on": None}


def test_inspector_fields_for_a_jfet(js: Page) -> None:
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const jfet = { ref: 'Q1', type: 'jfet', model: 'J201', measured: { idss: 0.0006, vp: -0.8 } };
        const circuit = { parts: [jfet, { ref: 'TR1', type: 'trimmer', value: '50k', bias_target: { node: 'Q1.D', volts: 9 } }] };
        const jfets = { J201: { idss: 0.000567, vp: -0.9 } };
        const fields = f.inspectorFields(jfet, { circuit, models: { jfet: ['2N5457', 'J201'] }, jfets });
        // no measured values: the model's picked, and yours start at the model's
        const stock = f.inspectorFields({ ...jfet, measured: undefined }, { circuit, models: { jfet: ['J201'] }, jfets });
        const own = { jfet_spec: 'measured' };
        const edit = f.editFrom(jfet, { ref: 'Q2', model: '2N5457', ...own, idss: '0.8', vp: '-1.2', drain_volts: '8.5', drain_trimmer: 'TR1' });
        // the model's picked: what's in the boxes doesn't count
        const plain = f.editFrom(jfet, { ref: 'Q1', model: 'J201', jfet_spec: 'model', idss: '0.8', vp: '-1.2', drain_volts: '', drain_trimmer: '' });
        const errors = [];
        for (const values of [{ ...own, idss: '0.8', vp: '' }, { ...own, idss: 'lots', vp: '1' }, { jfet_spec: 'model', drain_volts: '9', drain_trimmer: '' }]) {
          try { f.editFrom(jfet, { ref: 'Q1', ...values }); errors.push(null); } catch (e) { errors.push(e.message); }
        }
        return { fields: fields.map((x) => [x.name, x.value]), stock: stock.filter((x) => ['jfet_spec', 'idss', 'vp'].includes(x.name)).map((x) => [x.name, x.value, x.showIf ?? null]), models: fields[1].options, edit, plain, errors, sweep: [f.sweepField(jfet), f.sweepField({ type: 'resistor' }), f.sweepField({ type: 'switch' })] };
        """,
    )
    assert r["fields"] == [
        ["ref", "Q1"],
        ["model", "J201"],
        ["jfet_spec", "measured"],
        ["model_idss", "0.567"],
        ["model_vp", "-0.9"],
        ["idss", "0.6"],
        ["vp", "-0.8"],
        ["drain_volts", "9"],
        ["drain_trimmer", "TR1"],
        ["at_rest", ""],  # D-238
    ]
    shown = {"field": "jfet_spec", "not": "model"}
    assert r["stock"] == [
        ["jfet_spec", "model", None],
        ["idss", "0.567", shown],
        ["vp", "-0.9", shown],
    ]
    assert r["models"] == [["2N5457", "2N5457"], ["J201", "J201"]]
    assert r["edit"] == {
        "patch": {"model": "2N5457", "measured": {"idss": 0.0008, "vp": -1.2}},
        "ref": "Q2",
        "drain": {"trimmer": "TR1", "volts": 8.5},
    }
    assert r["plain"]["patch"]["measured"] is None and r["plain"]["drain"] == {
        "trimmer": None,
        "volts": None,
    }
    assert r["errors"] == [
        "Give your JFET's measured Idss and Vp, or pick the model's.",
        "Measured Idss must be a number.",
        "Pick the trimmer that sets the drain voltage.",
    ]
    assert r["sweep"] == ["model", "value", None]


def test_guitar_pickup_fields(js: Page) -> None:
    """D-096: the pickup list fills the coil and the pot; a measured pickup keeps its kind
    until its coil is changed; no pickup clears the coil, cable and pot."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const pickups = [{ kind: 'strat', name: 'Strat single coil', r: '6k38', l: '2.55', c: '151p', volume: '250k' }];
        const ctx = { circuit: { parts: [] }, models: {}, pickups };
        const ideal = { ref: 'IN', type: 'guitar' };
        const strat = { ref: 'IN', type: 'guitar', source: 'pickup', cable: 3, volume: '250k',
                        pickup: { r: '6k38', l: '2.55', c: '151p', kind: 'strat' } };
        const form = { ref: 'IN', source: 'strat', pickup_r: '6k38', pickup_l: '2.55', pickup_c: '151p', cable: '3', volume: '250k' };
        const fields = f.inspectorFields(ideal, ctx);
        return {
          ideal: fields.map((x) => [x.name, x.value, x.showIf?.not ?? null]),
          options: fields[1].options,
          fills: fields[1].fills,
          strat: f.inspectorFields(strat, ctx).map((x) => [x.name, x.value]),
          kept: f.editFrom(strat, form, { pickups }).patch,
          own: f.editFrom(strat, { ...form, pickup_r: '7k', volume: '' }, { pickups }).patch,
          none: f.editFrom(strat, { ...form, source: 'ideal' }, { pickups }).patch,
        };
        """,
    )
    assert r["ideal"] == [
        ["ref", "IN", None], ["source", "ideal", None], ["pickup_r", "6k38", "ideal"],
        ["pickup_l", "2.55", "ideal"], ["pickup_c", "151p", "ideal"], ["cable", "3", "ideal"],
        ["volume", "", None],  # buffered with no pot: empty, so applying adds none (D-134)
        ["stereo", "mono", None],  # a stereo jack's ring switches a battery (D-143)
    ]  # fmt: skip
    assert r["options"] == [
        ["ideal", "Buffered"], ["strat", "Strat single coil"],
        ["custom", "Your own values"],
    ]  # fmt: skip
    assert r["fills"] == {
        "strat": {"pickup_r": "6k38", "pickup_l": "2.55", "pickup_c": "151p", "volume": "250k"}
    }
    assert r["strat"][1] == ["source", "strat"]
    assert r["kept"] == {
        "source": "pickup", "cable": 3, "volume": "250k",
        "pickup": {"r": "6k38", "l": "2.55", "c": "151p", "kind": "strat"},
    }  # fmt: skip
    assert r["own"]["pickup"] == {"r": "7k", "l": "2.55", "c": "151p", "kind": None}
    assert r["own"]["volume"] is None
    assert r["none"] == {"source": None, "pickup": None, "cable": None, "volume": "250k"}


def test_inspector_fields_for_pots_and_switches(js: Page) -> None:
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        (await m('schematic/symbols.js')).setSwitchKinds(arg);
        const ctx = { circuit: { parts: [] }, models: {} };
        const pot = { ref: 'VR1', type: 'pot', value: '100k', taper: 'A', rotation: 0.625 };
        const sw = { ref: 'SW1A', type: 'switch', kind: 'dpdt-on-off-on', pole: 'a', position: 1 };
        return {
          pot: f.inspectorFields(pot, ctx).map((x) => [x.name, x.value]),
          potEdit: f.editFrom(pot, { ref: 'VR1', value: '250k', taper: 'B', rotation: '100', label: '' }).patch,
          over: ['150', '-1'].map((rotation) => { try { f.editFrom(pot, { ref: 'VR1', rotation }); return null; } catch (e) { return e.message; } }),
          sw: f.inspectorFields(sw, ctx).map((x) => [x.name, x.value]),
          swEdit: f.editFrom(sw, { ref: 'SW1A', kind: 'rotary-1p4t', position: '3', label: 'Clip' }).patch,
          swFewer: f.editFrom(sw, { ref: 'SW1A', kind: 'spdt', position: '2', label: '' }).patch,
          swNamed: f.editFrom(sw, { ref: 'SW1A', kind: 'dpdt-on-off-on', position: '1', label: '', name_0: ' Thick ', name_1: '', name_2: 'Thin' }).patch.names,
          swUnnamed: f.editFrom(sw, { ref: 'SW1A', kind: 'dpdt-on-off-on', position: '1', label: '', name_0: '', name_1: '', name_2: '' }).patch.names,
          swRetyped: f.editFrom(sw, { ref: 'SW1A', kind: 'spdt', position: '0', label: '', name_0: 'Thick', name_1: '', name_2: 'Thin' }).patch.names,
          swNames: f.inspectorFields({ ...sw, names: ['Thick', '', 'Thin'] }, ctx).filter((x) => x.name.startsWith('name_')).map((x) => [x.label, x.value]),
          trim: f.editFrom({ ref: 'TR1', type: 'trimmer' }, { ref: 'TR1', value: '50k', taper: 'B', rotation: '', bias_node: 'Q1.D', bias_volts: '9' }).patch,
        };
        """,
        catalogue(),
    )
    assert r["pot"] == [
        ["ref", "VR1"],
        ["value", "100k"],
        ["taper", "A"],
        ["gangs", "1"],  # Single; Dual makes it a dual pot (D-217)
        ["rotation", "62.5"],
        ["label", ""],
    ]
    assert r["potEdit"] == {
        "value": "250k",
        "label": None,
        "taper": "B",
        "rotation": 1,
    }
    assert r["over"] == ["Rotation goes from 0 to 100 %."] * 2  # refused, not clamped (D-127)
    assert r["sw"] == [  # D-143: a type, its positions by name, and what this pole joins
        ["ref", "SW1A"],
        ["kind", "dpdt-on-off-on"],
        ["position", "1"],
        ["contacts", "1: A2\u2013A1 · Off: open · 2: A2\u2013A3"],
        ["label", ""],
        ["name_0", ""],
        ["name_1", ""],
        ["name_2", ""],
    ]
    assert r["swEdit"] == {"label": "Clip", "kind": "rotary-1p4t", "position": 3, "names": None}
    assert r["swFewer"] == {
        "label": None,
        "kind": "spdt",
        "position": 0,
        "names": None,
    }  # past its last: the first
    # D-143: a name per position, an empty one the type's; none typed, or a type changed
    # under them, and there are none
    assert r["swNamed"] == ["Thick", "", "Thin"]
    assert r["swUnnamed"] is None
    assert r["swRetyped"] is None
    assert r["swNames"] == [["Name for 1", "Thick"], ["Name for Off", ""], ["Name for 2", "Thin"]]
    assert r["trim"] == {
        "value": "50k",
        "taper": "B",
        "bias_target": {"node": "Q1.D", "volts": 9},  # the target turns it: no rotation
    }


def test_sweep_series(js: Page) -> None:
    r = run(
        js,
        """
        const s = await m('series.js');
        const sweep = { ref: 'R1', field: 'value', values: ['1k', '10k'], nodes: ['a', 'out'],
                        ac: { freq: [10, 100], nodes: { a: [[0, -1], [0, -6]] } }, tran: { time_ms: [0, 1], nodes: { a: [[0, 1], [0, 0.5]] } } };
        const ac = s.valueSweepSeries(sweep, 'a', 'ac');
        return { styles: [[0, 1], [0, 5], [2, 5], [4, 5], [11, 12]].map(([i, n]) => s.sweepStyle(i, n)),
                 ac: ac.series.map((x) => [x.label, x.style, x.tag]), x: ac.x, scope: s.valueSweepSeries(sweep, 'a', 'tran').x,
                 missing: s.valueSweepSeries(sweep, 'out', 'ac'), noTran: s.valueSweepSeries({ ...sweep, tran: null }, 'a', 'tran') };
        """,
    )
    assert r["styles"] == ["sweep-1", "sweep-1", "sweep-7", "sweep-12", "sweep-12"]
    assert r["ac"] == [["R1 = 1k (a)", "sweep-1", "1k"], ["R1 = 10k (a)", "sweep-12", "10k"]]
    assert r["x"] == [10, 100] and r["scope"] == [0, 1]
    assert r["missing"] is None and r["noTran"] is None


def test_wire_tool_helpers(js: Page) -> None:
    """The wire tool's pieces: a leg's direction, adding a path, moving a wire end (the
    ball), joining a wire mid-way, and which ends get a ball."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R1', type: 'resistor', pos: [0, 0], value: '1k' }],
                    wires: [{ from: [20, 0], to: [60, 0] }, { from: [60, 0], to: [60, 40] }], labels: [] };
        const view = {
          parts: [{ pins: [{ pos: [-20, 0] }, { pos: [20, 0] }] }], labels: [{ pos: [100, 100] }],
          wires: [{ from: [20, 0], to: [60, 0], net: 'R1.2' }, { from: [60, 0], to: [60, 40], net: 'R1.2' },
                  { from: [30, 0], to: [30, -30], net: 'R1.2' }, { from: [100, 100], to: [100, 60], net: 'X' }],
        };
        return {
          vertical: e.route([0, 0], [50, 20], false), horizontal: e.route([0, 0], [10, 50], true),
          added: e.addWires(c, [{ from: [60, 40], to: [60, 0] }, { from: [5, 5], to: [5, 5] }, { from: [60, 40], to: [100, 40] }]).wires,
          moved: e.moveWireEnd(c, [60, 40], [90, 40]).wires,
          bend: e.moveWireEnd(c, [60, 0], [60, -20]).wires,
          same: e.moveWireEnd(c, [60, 40], [61, 41]) === c,
          onWire: [e.pointOnWire({ from: [0, 0], to: [100, 0] }, [43, 12]), e.pointOnWire({ from: [0, 0], to: [0, 50] }, [7, 90])],
          ends: Object.fromEntries(e.wireEnds(view).map((x) => [x.pos.join(','), x.kind])),
        };
        """,
    )
    assert r["vertical"] == [{"from": [0, 0], "to": [0, 20]}, {"from": [0, 20], "to": [50, 20]}]
    assert r["horizontal"] == [{"from": [0, 0], "to": [10, 0]}, {"from": [10, 0], "to": [10, 50]}]
    # the reversed duplicate and the zero-length segment are dropped
    assert r["added"] == [
        {"from": [20, 0], "to": [60, 0]},
        {"from": [60, 0], "to": [60, 40]},
        {"from": [60, 40], "to": [100, 40]},
    ]
    # the loose end's ball moved: the run is re-laid from R1.2 (its far end) to the new point
    assert_path(r["moved"], (20, 0), (90, 40), bends=1, clear_of=[(-20, -10, 20, 10)])
    # dragging the bend: both runs from it are re-laid to the new point, so the wire still
    # goes from R1.2 to the loose end, now through (60, -20)
    count: dict[tuple[int, ...], int] = {}
    for w in r["bend"]:
        assert w["from"][0] == w["to"][0] or w["from"][1] == w["to"][1]
        for pt in (tuple(w["from"]), tuple(w["to"])):
            count[pt] = count.get(pt, 0) + 1
    assert {pt for pt, n in count.items() if n == 1} == {(20, 0), (60, 40)}
    assert count[(60, -20)] == 2
    assert r["same"] is True  # snapped back onto the same point: nothing to do
    assert r["onWire"] == [[40, 0], [0, 50]]
    assert r["ends"] == {
        "20,0": "pin",  # on R1.2
        "60,0": "bend",  # two wires
        "60,40": "loose",
        "30,0": "bend",  # a T onto the first wire
        "30,-30": "loose",
        "100,100": "pin",  # a label
        "100,60": "loose",
    }


def test_text_blocks_are_edited_moved_selected_and_copied(js: Page) -> None:
    """Text blocks (D-091): placed snapped (nothing when empty), a title and text edited
    (both empty removes it), moved with a selection
    (no wires re-laid for them), taken in by a box, copied and pasted with the rest."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const b = await m('editor/blocks.js');
        const s = await m('schematic/symbols.js');
        const k = await m('editor/keys.js');
        const c = e.addText(e.addPart({ parts: [] }, 'resistor', [0, 0]).circuit, { title: '', text: 'Bias\\nnotes  ' }, [33, 47]);
        const moved = e.moveItems(c, { parts: [], texts: [0] }, 100, -50);
        const both = e.moveItems(c, { parts: ['R1'], texts: [0] }, 20, 0);
        const box = b.itemsInBox(c, [20, 40, 60, 60]);
        const copy = b.extract(c, { parts: [] }, { parts: [], wires: [], labels: [], texts: [0] });
        const pasted = b.pasteBlock({ parts: [] }, copy, { at: [500, 500] }).circuit;
        return {
          placed: c.texts, edited: e.setText(c, 0, { title: ' Q1 ', text: 'Bias' }).texts,
          emptied: e.setText(c, 0, { title: ' ', text: '  ' }).texts, nothing: e.addText(c, { title: '', text: ' ' }, [0, 0]) === c,
          moved: moved.texts[0].pos, same: moved.parts[0] === c.parts[0], both: [both.texts[0].pos, both.parts[0].pos],
          deleted: e.deleteItems(c, { texts: [0] }).texts, box, copy: copy.texts, pasted: pasted.texts,
          isEmpty: b.isEmpty({ parts: [], wires: [], labels: [], texts: [0] }), all: b.allItems(c).texts,
          hitBox: s.textBox({ text: 'ab\\nabcd' }, [0, 0]), titled: s.textBox({ title: 'Bias', text: 'ab' }, [0, 0]), key: k.actionFor({ key: 'x' }),
        };
        """,
    )
    assert r["placed"] == [{"text": "Bias\nnotes", "pos": [30, 50]}]  # snapped to the grid
    assert r["edited"] == [{"title": "Q1", "text": "Bias", "pos": [30, 50]}]
    assert r["emptied"] == [] and r["nothing"] is True
    assert r["moved"] == [130, 0] and r["same"] is True
    assert r["both"] == [[50, 50], [20, 0]]
    assert r["deleted"] == []
    assert r["box"]["texts"] == [0] and r["box"]["parts"] == []
    assert r["copy"] == [{"text": "Bias\nnotes", "pos": [30, 50]}]
    assert len(r["pasted"]) == 1 and r["pasted"][0]["text"] == "Bias\nnotes"
    assert r["isEmpty"] is False and r["all"] == [0]
    # 4 characters wide at 5.6, two lines (10 + 13) plus padding
    assert r["hitBox"] == pytest.approx([-3, -3, 4 * 5.6 + 3, 13 + 10 + 3 + 2])
    assert r["titled"] == pytest.approx([-3, -3, 4 * 6.4 + 3, 13 + 10 + 3 + 2])  # bold is wider
    assert r["key"] == {"action": "text"}


def test_router_goes_around_and_keeps_clear(js: Page) -> None:
    """findPath: around a body, never over a pin, never along a wire; crossing a wire is
    allowed but not turning on it. crossings() finds the hops."""
    r = run(
        js,
        """
        const t = await m('editor/router.js');
        const body = t.worldOf({ boxes: [[30, -20, 70, 20]], anchors: [], wires: [] });
        const pin = t.worldOf({ boxes: [], anchors: [[50, 0]], wires: [] });
        const along = t.worldOf({ boxes: [], anchors: [], wires: [{ from: [-50, 0], to: [150, 0] }] });
        const cross = t.worldOf({ boxes: [], anchors: [], wires: [{ from: [50, -100], to: [50, 100] }] });
        return {
          around: t.findPath([0, 0], [100, 0], body), pin: t.findPath([0, 0], [100, 0], pin),
          along: t.findPath([0, 0], [100, 0], along), cross: t.findPath([0, 0], [100, 0], cross),
          same: t.findPath([0, 0], [0, 0], body),
          hops: t.crossings([{ from: [0, 0], to: [100, 0] }, { from: [50, -50], to: [50, 50] }, { from: [100, 0], to: [100, 50] }, { from: [0, 0], to: [0, 30] }]),
          through: [t.throughBody([{ from: [0, 0], to: [100, 0] }], [[30, -20, 70, 20]]), t.throughBody([{ from: [0, 20], to: [100, 20] }], [[30, -20, 70, 20]])],
        };
        """,
    )
    for path in (r["around"], r["pin"], r["along"]):
        assert path[0]["from"] == [0, 0] and path[-1]["to"] == [100, 0]
        assert len(path) > 1  # it had to leave the straight line
    assert all(
        not (30 < x < 70 and -20 < y < 20) for w in r["around"] for x, y in (w["from"], w["to"])
    )
    assert all(
        w["from"][1] != 0 or w["to"][1] != 0 for w in r["along"][1:-1]
    )  # off the wire's line
    assert r["cross"] == [{"from": [0, 0], "to": [100, 0]}]  # straight over the other wire
    assert r["same"] == []
    assert r["hops"] == [{"at": [50, 0], "wire": 0, "over": 1}]  # ends touching aren't hops
    assert r["through"] == [True, False]  # along the box's edge is fine


def test_dragging_a_part_about_leaves_no_trail(js: Page) -> None:
    """Moving a part up, right, then down leaves one bend, as one move to the end does:
    a straight wire is re-laid from its far end (D-063), a bent one keeps its bend and
    slides it (D-164), so nothing piles up either way."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R1', type: 'resistor', pos: [0, 0], value: '1k' }, { ref: 'R2', type: 'resistor', pos: [200, 0], value: '1k' }],
                    wires: [{ from: [20, 0], to: [180, 0] }], labels: [] };
        const steps = e.moveParts(e.moveParts(e.moveParts(c, ['R1'], 0, -80), ['R1'], 60, 0), ['R1'], 0, 160);
        const once = e.moveParts(c, ['R1'], 60, 80);
        const diff = e.wireDiff(c.wires, once.wires);
        return { steps: steps.wires, once: once.wires, diff };
        """,
    )
    for wires in (r["steps"], r["once"]):
        assert_path(
            wires, (80, 80), (180, 0), bends=1, clear_of=[(40, 70, 80, 90), (180, -10, 220, 10)]
        )
    assert r["diff"]["removed"] == [0] and r["diff"]["added"] == r["once"]


def test_moving_a_part_keeps_the_bends_of_its_wire(js: Page) -> None:
    """The user (2026-11-02): moving a part with a bent wire "fubars the angles". The
    bend next to the part slides with it, the rest stays (D-164); a bend that would land
    on something is routed afresh instead. Moving one leg of an L keeps the L."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const parts = [{ ref: 'R1', type: 'resistor', pos: [0, 0], value: '1k' }, { ref: 'R2', type: 'resistor', pos: [200, 100], value: '1k', rot: 90 }];
        // R1.2 (20, 0) right to (200, 0), down to R2.1 (200, 80)
        const c = { parts, wires: [{ from: [20, 0], to: [200, 0] }, { from: [200, 0], to: [200, 80] }], labels: [] };
        return {
          down: e.moveParts(c, ['R1'], 0, 20).wires,
          left: e.moveParts(c, ['R1'], -40, 0).wires,
          leg: e.moveItems(c, { parts: [], wires: [1], labels: [] }, 20, 0).wires,
        };
        """,
    )
    seg = lambda a, b: {"from": list(a), "to": list(b)}  # noqa: E731
    assert sorted(map(str, r["down"])) == sorted(
        map(str, [seg((20, 20), (200, 20)), seg((200, 20), (200, 80))])
    )
    assert sorted(map(str, r["left"])) == sorted(
        map(str, [seg((-20, 0), (200, 0)), seg((200, 0), (200, 80))])
    )
    # the vertical leg moved right: the horizontal one stretches to meet it, then a jog
    # back to R2's pin, which stayed
    nets = {frozenset(map(tuple, (w["from"], w["to"]))) for w in r["leg"]}
    assert frozenset({(20, 0), (220, 0)}) in nets


STARTERS = ("ts808", "fuzz-face", "proco-rat", "big-muff-pi-v3")
MOVES = ((0, 40), (40, 0), (-60, -30), (30, 90))


def _groups(data: dict[str, Any]) -> set[frozenset[tuple[str, str]]]:
    nets = connect(parse_circuit(data))
    return {frozenset(m) for m in nets.members.values() if m}


def _lands(after: dict[str, Any], before: dict[str, Any], ref: str) -> bool:
    """A moved or turned part's pin now sits on a pin, label or wire it wasn't on: a new
    connection the user made by dropping it there (not the editor's doing)."""
    old, new = parse_circuit(before), parse_circuit(after)
    mine_old = set(pin_positions(old.part(ref)).values())
    points = [pos for p in old.parts if p.ref != ref for pos in pin_positions(p).values()]
    points += [lb.pos for lb in old.labels]
    for pos in pin_positions(new.part(ref)).values():
        if pos in points:
            return True
        for w in old.wires:
            if w.from_ not in mine_old and w.to not in mine_old and on_segment(pos, w.from_, w.to):
                return True
    return False


@pytest.mark.parametrize("starter", STARTERS)
def test_moving_or_turning_any_part_keeps_its_connections(js: Page, starter: str) -> None:
    """Every part of every starter, moved four ways and turned: the nets are unchanged,
    unless a pin was dropped onto something (then it connects, as it should). Covers wires
    joining part-way along another (T), pins touching pins with no wire, and parts dropped
    on top of others (D-063)."""
    data = json.loads((REPO / "library" / "starters" / f"{starter}.json").read_text())
    before = _groups(data)
    results = run(
        js,
        """
        const e = await m('editor/edit.js');
        const out = [];
        for (const p of arg.c.parts) {
          for (const [dx, dy] of arg.moves) out.push([p.ref, `move ${dx},${dy}`, e.moveParts(arg.c, [p.ref], dx, dy)]);
          out.push([p.ref, 'turn', e.rotatePart(arg.c, p.ref)]);
        }
        return out;
        """,
        {"c": data, "moves": MOVES},
    )
    broken = []
    for ref, how, after in results:
        if _lands(after, data, ref):
            continue
        if _groups(after) != before:
            broken.append(f"{ref} {how}")
    assert not broken, broken


def test_sweep_prompt_fits_the_part(js: Page) -> None:
    """The inspector's compare row asks for the right kind of values: voltages for a DC
    source (not resistor values), models from the library for a transistor."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        return [f.sweepPrompt({ type: 'vsource' }), f.sweepPrompt({ type: 'resistor' }),
                f.sweepPrompt({ type: 'bjt' }, ['2N5088', '2N5089', 'BC549C', 'MPSA18']), f.sweepPrompt({ type: 'switch' })];
        """,
    )
    assert r[0] == {
        "label": "Compare supply voltages, overlaid on the plots (up to 5)",
        "placeholder": "e.g. 9, 12, 18",
    }
    assert r[1]["placeholder"] == "e.g. 4k7, 10k, 22k"
    assert r[2] == {
        "label": "Compare models, overlaid on the plots (up to 5)",
        "placeholder": "e.g. 2N5088, 2N5089, BC549C",
    }
    assert r[3] is None


def test_sweep_summary(js: Page) -> None:
    """Runs compared as numbers: DC, gain at the point nearest 1 kHz, peaks; overlap when
    the curves agree within 0.1 dB and 1 %; the nets whose DC moved most (D-067)."""
    r = run(
        js,
        """
        const s = await m('series.js');
        const base = { ref: 'V1', field: 'value', values: ['9', '18'], nodes: ['out'],
          dc: { out: [0, 0] }, dc_all: { VREF: [4.5, 9], q1e: [3.9, 8.2], out: [0, 0], tiny: [1, 1.01] },
          ac: { freq: [100, 900, 5000], nodes: { out: [[1, 20, 3], [1, 20.05, 3]] } },
          tran: { time_ms: [0, 1, 2], nodes: { out: [[0, 0.5, -0.5], [0, 0.502, -0.5]] } } };
        const apart = { ...base, ac: { ...base.ac, nodes: { out: [[1, 20, 3], [1, 26, 3]] } } };
        return { same: s.sweepSummary(base, 'out'), apart: s.sweepSummary(apart, 'out') };
        """,
    )
    same = r["same"]
    assert same["rows"] == [
        {"value": "9", "dc": 0, "gain": 20, "peak": [0.5, -0.5]},
        {"value": "18", "dc": 0, "gain": 20.05, "peak": [0.502, -0.5]},
    ]
    assert same["overlap"] is True
    assert [x["net"] for x in same["shifts"]] == ["VREF", "q1e"]  # out and tiny didn't move
    assert r["apart"]["overlap"] is False


def test_power_presets_and_text(js: Page) -> None:
    """The Power menu (D-093): 9/12/18 V and ±9/±12/±15 V; a V- circuit gets negative
    singles; a supply that's none of them is listed first; Custom… sets any."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const err = (f) => { try { f(); return null; } catch (x) { return x.message; } };
        const lab = (net) => ({ net, pos: [0, 0] });
        const c = (rails, labels = [], parts = []) => ({ parts, labels, power: { rails } });
        const texts = (circuit) => e.powerChoices(circuit).map((x) => x.text);
        const both = c({ 'V+': 9, 'V-': -9 }, [lab('V+'), lab('V-')]);
        const onlyNeg = c({ 'V+': 9, 'V-': -9 }, [lab('V-')]);
        return {
          plus: texts(c({ 'V+': 9 })),
          minus: texts(c({ 'V-': -9 })),
          odd: texts(c({ 'V+': 12, 'V-': -9 })),
          text: [e.powerText({}), e.powerText({ 'V+': 9 }), e.powerText({ 'V-': -9 }), e.powerText({ 'V+': 12, 'V-': -12 }), e.powerText({ 'V+': 12, 'V-': -9 })],
          split: e.setPower(c({ 'V+': 9 }, [lab('V+')]), { 'V+': 12, 'V-': -12 }).power.rails,
          // ± → 9 V with both rails in use would join them: refused
          joined: err(() => e.setPower(both, { 'V+': 9 })),
          // only V- in use: dropping it is a change of polarity, so its bar becomes V+
          handed: e.setPower(onlyNeg, { 'V+': 9 }).labels.map((l) => l.net),
        };
        """,
    )
    assert r["plus"] == ["9 V", "12 V", "18 V", "±9 V", "±12 V", "±15 V"]
    assert r["minus"] == ["\u22129 V", "\u221212 V", "\u221218 V", "±9 V", "±12 V", "±15 V"]
    assert r["odd"][0] == "+12 / \u22129 V" and len(r["odd"]) == 7
    assert r["text"] == ["no supply", "9 V", "\u22129 V", "±12 V", "+12 / \u22129 V"]
    assert r["split"] == {"V+": 12, "V-": -12}
    assert r["joined"] == "V- is still used on the sheet (1 label). Keep V-, or delete those first."
    assert r["handed"] == ["V+"]


def test_inspector_fields_for_a_charge_pump(js: Page) -> None:
    """D-226: its model; what it does comes from the parts wired to it, boost too (D-234)."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const ctx = { circuit: {}, models: { chargepump: ['ICL7660', 'LT1054', 'TC1044S'] } };
        const pump = { ref: 'U1', type: 'chargepump', model: 'TC1044S' };
        const fields = f.inspectorFields(pump, ctx);
        return {
          names: fields.map((x) => [x.name, x.value]),
          about: fields.filter((x) => x.about).map((x) => x.name),
          edit: f.editFrom(pump, { ref: 'U1', model: 'LT1054' }).patch,
        };
        """,
    )
    assert r["names"] == [["ref", "U1"], ["model", "TC1044S"]]
    assert r["about"] == ["model"]  # one about per form (D-200)
    assert r["edit"] == {"model": "LT1054"}


def test_same_connections(js: Page) -> None:
    """D-095: a dragged wire may change how a connection runs, never what it connects."""
    result = run(
        js,
        """
        const e = await m('editor/edit.js');
        const view = (nets, problem = null) => ({ problem, parts: [
          { ref: 'R1', pins: [{ name: '1', net: nets[0] }, { name: '2', net: nets[1] }] },
          { ref: 'R2', pins: [{ name: '1', net: nets[2] }, { name: '2', net: null }] },
        ] });
        const a = view(['in', 'mid', 'mid']);
        return {
          renamed: e.sameConnections(a, view(['x', 'R1.2', 'R1.2'])),
          split: e.sameConnections(a, view(['in', 'mid', 'R2.1'])),
          joined: e.sameConnections(a, view(['in', 'in', 'in'])),
          problem: e.sameConnections(a, view(['in', 'mid', 'mid'], 'GND and IN are wired together')),
          stillBroken: e.sameConnections(view([null, null, null], 'send and return are wired together'),
                                         view([null, null, null], 'send and return are wired together')),
          otherBreak: e.sameConnections(view([null, null, null], 'send and return are wired together'),
                                        view([null, null, null], 'GND and IN are wired together')),
        };
        """,
    )
    assert result == {
        "renamed": True,
        "split": False,
        "joined": False,
        "problem": False,
        "stillBroken": True,  # D-293: nothing to compare, and the contradiction is the same
        "otherBreak": False,
    }


def test_items_after_move(js: Page) -> None:
    """Moved wires and labels are found again by where they went, even when the list is
    reordered and a wire comes back in two pieces."""
    result = run(
        js,
        """
        const e = await m('editor/edit.js');
        const before = { parts: [], wires: [{ from: [0, 0], to: [40, 0] }, { from: [0, 50], to: [40, 50] }],
                         labels: [{ net: 'A', pos: [0, 0] }, { net: 'B', pos: [0, 50] }] };
        const after = { parts: [], wires: [{ from: [0, 50], to: [40, 50] }, { from: [20, 20], to: [40, 20] }, { from: [0, 20], to: [20, 20] }],
                        labels: [{ net: 'B', pos: [0, 50] }, { net: 'A', pos: [0, 20] }] };
        return e.itemsAfterMove(before, after, { parts: ['R1'], wires: [0], labels: [0] }, 0, 20);
        """,
    )
    assert result == {"parts": ["R1"], "wires": [1, 2], "labels": [1]}


def test_wire_run(js: Page) -> None:
    """A bent wire is one wire: its pieces up to a pin, a label, a branch or a T."""
    result = run(
        js,
        """
        const e = await m('editor/edit.js');
        const c = { parts: [{ ref: 'R1', type: 'resistor', pos: [0, 0] }],  // pins at (-20, 0) and (20, 0)
          labels: [{ net: 'OUT', pos: [100, 60] }],
          wires: [
            { from: [20, 0], to: [60, 0] },     // 0: from R1.2 ...
            { from: [60, 0], to: [60, 60] },    // 1: ... a bend ...
            { from: [60, 60], to: [100, 60] },  // 2: ... to the OUT label
            { from: [-20, 0], to: [-60, 0] },   // 3: R1.1 to a branch at (-60, 0)
            { from: [-60, 0], to: [-60, 40] },  // 4
            { from: [-60, 0], to: [-60, -40] }, // 5
            { from: [60, 30], to: [80, 30] },   // 6: a T onto piece 1 (its end is on 1's middle)
          ] };
        return { bent: e.wireRun(c, 1).sort(), end: e.wireRun(c, 2).sort(), branch: e.wireRun(c, 3), tee: e.wireRun(c, 6), none: e.wireRun(c, 9) };
        """,
    )
    assert result == {"bent": [0, 1, 2], "end": [0, 1, 2], "branch": [3], "tee": [6], "none": []}


def test_a_targeted_trimmer_shows_where_the_last_run_turned_it(js: Page) -> None:
    """D-123: the target turns it on every run, so Rotation reads that turn, read-only."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const rt = { ref: 'TR1', type: 'trimmer', value: '25k', rotation: 0.5, bias_target: { node: 'Q1.D', volts: 4 } };
        const pick = (fields) => fields.find((x) => x.name === 'rotation');
        const ctx = { circuit: { parts: [rt] }, models: {} };
        const solved = pick(f.inspectorFields(rt, { ...ctx, bias: { TR1: 0.88 } }));
        const unrun = pick(f.inspectorFields(rt, ctx));
        const free = pick(f.inspectorFields({ ...rt, bias_target: undefined }, ctx));
        const names = (p) => f.inspectorFields(p, ctx).map((x) => x.name);
        const node = f.inspectorFields(rt, ctx).find((x) => x.name === 'bias_node');
        const volts = f.inspectorFields(rt, ctx).find((x) => x.name === 'bias_volts');
        const shape = { targeted: names(rt), free: names({ ...rt, bias_target: undefined }), node, volts };
        // either target field cleared takes it off, keeping the rotation typed (the solved turn)
        const base = { ref: 'TR1', value: '25k', taper: 'B', rotation: '88' };
        const noVolts = f.editFrom(rt, { ...base, bias_node: 'Q1.D', bias_volts: '' }).patch;
        const noNode = f.editFrom(rt, { ...base, bias_node: '', bias_volts: '4' }).patch;
        const kept = f.editFrom(rt, { ...base, bias_node: 'Q1.D', bias_volts: '4.5' }).patch;
        // in the form: Rotation unlocks as soon as the target is cleared
        const form = await m('editor/form.js');
        const host = document.createElement('div');
        document.body.append(host);
        const opened = form.openForm(host, { title: 'TR1', fields: f.inspectorFields(rt, { ...ctx, bias: { TR1: 0.88 } }), onSubmit: async () => null });
        const box = host.querySelector('#field-rotation');
        const locked = box.readOnly;
        const voltsBox = host.querySelector('#field-bias_volts');
        voltsBox.value = '';
        voltsBox.dispatchEvent(new Event('input'));
        const unlocked = !box.readOnly;
        opened.close();
        // Remove target: the volts emptied (the node's pick kept), both hidden, Add target
        // back, Rotation free with its hand-turned hint; Add target: back as it was
        const now = { ...ctx, target: { node: 'Q1.D', volts: 4.2 } };
        const again = form.openForm(host, { title: 'TR1', fields: f.inspectorFields(rt, now), onSubmit: async () => null });
        const add = host.querySelector('#field-rotation-add');
        const rotationHint = () => host.querySelector('#field-rotation').closest('.form-row').querySelector('.hint-text').textContent;
        const addAtFirst = add.hidden;
        host.querySelector('#field-bias_volts-remove').click();
        const removed = {
          values: ['bias_node', 'bias_volts'].map((n) => host.querySelector(`#field-${n}`).value),
          hidden: ['bias_node', 'bias_volts'].map((n) => host.querySelector(`#field-${n}`).closest('.form-row').hidden),
          add: !add.hidden,
          free: !host.querySelector('#field-rotation').readOnly,
          why: rotationHint(),
        };
        add.click();
        const readded = { add: add.hidden, volts: host.querySelector('#field-bias_volts').value, locked: host.querySelector('#field-rotation').readOnly, why: rotationHint() };
        again.close();
        const e = await m('editor/edit.js');
        const parts = (t) => ({ parts: [{ ref: 'TR1', type: 'trimmer', bias_target: t }, { ref: 'R1', type: 'resistor' }] });
        const at4 = { node: 'Q1.D', volts: 4 };
        const moved = [
          e.movedTargets(parts(at4), parts(at4)),
          e.movedTargets(parts(at4), parts({ ...at4, volts: 5 })),
          e.movedTargets(parts(null), parts(at4)),
          e.movedTargets(parts(at4), parts(null)),
        ];
        // a target given: what the Rotation box says doesn't count (it's not checked either)
        const over = f.editFrom({ ...rt, bias_target: undefined }, { ...base, rotation: '120', bias_node: 'Q1.D', bias_volts: '4' }).patch;
        return { solved, unrun, free, noVolts, noNode, kept, locked, unlocked, shape, removed, readded, addAtFirst, moved, over };
        """,
    )
    assert r["solved"]["value"] == "88" and r["solved"]["readonly"]
    assert r["solved"]["lockedHint"] == "Set by its bias target (within 1 mV)."
    assert "88 %" in r["solved"]["about"] and "within 1 mV" in r["solved"]["about"]
    assert r["unrun"]["value"] == "50" and r["unrun"]["readonly"]
    assert not r["free"].get("readonly") and r["free"]["value"] == "50"
    assert r["noVolts"]["bias_target"] is None and r["noNode"]["bias_target"] is None
    assert r["noVolts"]["rotation"] == 0.88
    assert r["kept"]["bias_target"] == {"node": "Q1.D", "volts": 4.5}
    assert r["locked"] and r["unlocked"]
    # D-127: the node is picked from those it could hold; no target and nothing it could
    # hold, no target fields (a hint says where)
    assert r["shape"]["targeted"] == [
        "ref",
        "value",
        "taper",
        "rotation",
        "bias_node",
        "bias_volts",
        "label",
    ]
    assert r["shape"]["free"] == ["ref", "value", "taper", "rotation", "label"]
    assert r["shape"]["node"]["readonly"] and r["shape"]["node"]["value"] == "Q1.D"
    assert r["shape"]["volts"]["remove"]["label"] == "Remove target"
    assert "Drain target in a JFET's form" in r["free"]["hint"]
    assert r["removed"]["values"] == ["", ""] and r["removed"]["hidden"] == [True, True]
    assert r["addAtFirst"] and r["removed"]["add"] and r["removed"]["free"]
    assert r["removed"]["why"] == "Turned by hand from here, once Apply takes the target off."
    assert r["readded"]["add"] and r["readded"]["locked"] and r["readded"]["volts"] == "4.20"
    assert r["readded"]["why"].startswith("Set by its bias target")
    assert "rotation" not in r["over"] and r["over"]["bias_target"] == {"node": "Q1.D", "volts": 4}
    assert r["moved"] == [[], ["TR1"], ["TR1"], []]


def test_add_target_on_a_trimmer(js: Page) -> None:
    """Round 3b (D-127): the node a trimmer holds is the drain or collector of the one
    transistor it's wired to, whichever pin it touches; none for a balance trim between
    two transistors, a trimmer on no transistor, or a node another trimmer holds. Add
    target's fields start hidden and fill on Add: the node, at its voltage now."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const pin = (name, net) => ({ name, net });
        const q = (ref, type, d, g, s) => type === 'jfet' || type === 'mosfet'
          ? { ref, type, pins: [pin('D', d), pin('G', g), pin('S', s)] }
          : { ref, type, pins: [pin('C', d), pin('B', g), pin('E', s)] };
        const rt = (ref, a, w, b) => ({ ref, type: 'trimmer', pins: [pin('1', a), pin('2', w), pin('3', b)] });
        const nets = { 'V+': { rail: true }, GND: { rail: true } };
        const view = (parts, held = []) => ({ nets, parts, circuit: { parts: held } });
        const at = (v, ref = 'TR1') => f.targetNode(ref, v, { d1: 7.123, c2: 4.5 });
        const cases = {
          drain: at(view([rt('TR1', 'V+', 'd1', 'd1'), q('Q1', 'jfet', 'd1', 'g1', 's1')])),
          source: at(view([rt('TR1', 's1', 'GND', 'GND'), q('Q1', 'jfet', 'd1', 'g1', 's1')])),
          collector: at(view([rt('TR1', 'V+', 'c2', 'c2'), q('Q2', 'bjt', 'c2', 'b2', 'GND')])),
          divider: at(view([rt('TR1', 'V+', 'b2', 'GND'), q('Q2', 'bjt', 'c2', 'b2', 'GND')])),
          mosfet: at(view([rt('TR1', 'V+', 'd1', 'd1'), q('Q3', 'mosfet', 'd1', 'g1', 's1')])),
          // Q1's drain straight into Q2's base: Q1's drain, not "two transistors"
          coupled: at(view([rt('TR1', 'V+', 'd1', 'd1'), q('Q1', 'jfet', 'd1', 'g1', 's1'), q('Q2', 'bjt', 'c2', 'd1', 'GND')])),
          balance: at(view([rt('TR1', 'e1', 'tail', 'e2'), q('Q1', 'bjt', 'c1', 'b1', 'e1'), q('Q2', 'bjt', 'c2', 'b2', 'e2')])),
          tone: at(view([rt('TR1', 'a', 'b', 'GND')])),
          held: at(view([rt('TR1', 'V+', 'd1', 'd1'), q('Q1', 'jfet', 'd1', 'g1', 's1')], [{ ref: 'TR2', bias_target: { node: 'Q1.D', volts: 9 } }])),
        };
        const part = { ref: 'TR1', type: 'trimmer', value: '50k', taper: 'B', rotation: 0.4 };
        const fields = f.inspectorFields(part, { circuit: { parts: [] }, models: {}, target: cases.drain });
        const by = (n) => fields.find((x) => x.name === n);
        const none = f.inspectorFields(part, { circuit: { parts: [] }, models: {}, target: null });
        return { cases, names: fields.map((x) => x.name), rotation: by('rotation'),
          node: by('bias_node'), volts: by('bias_volts'), none: none.map((x) => x.name),
          noneHint: none.find((x) => x.name === 'rotation').hint };
        """,
    )
    assert r["cases"] == {
        "drain": {"node": "Q1.D", "volts": 7.123},
        "source": {"node": "Q1.D", "volts": 7.123},
        "collector": {"node": "Q2.C", "volts": 4.5},
        "divider": {"node": "Q2.C", "volts": 4.5},
        "mosfet": {"node": "Q3.D", "volts": 7.123},
        "coupled": {"node": "Q1.D", "volts": 7.123},
        "balance": None,
        "tone": None,
        "held": None,
    }
    assert r["names"] == ["ref", "value", "taper", "rotation", "bias_node", "bias_volts", "label"]
    assert r["rotation"]["add"] == {
        "label": "Add target",
        "fields": ["bias_node", "bias_volts"],
        "values": {"bias_node": "Q1.D", "bias_volts": "7.12"},
    }
    assert r["rotation"]["hint"] == "Turned by hand. To hold a voltage instead: Add target."
    assert r["node"]["hidden"] and r["node"]["readonly"] and r["node"]["value"] == ""
    assert r["volts"]["hidden"] and r["volts"]["value"] == ""
    assert r["none"] == ["ref", "value", "taper", "rotation", "label"]
    assert "Drain target in a JFET's form" in r["noneHint"]


def test_a_part_goes_in_series_beside_a_pin(js: Page) -> None:
    """D-124: a part put in series with a pin goes beside it along the part's line, the
    wires that left the pin re-laid to its far end (into a lead long enough, or moving a
    rail the pin sat on); boxed in, it goes to a clear spot with a wire back; a pin
    touching another part's pin directly takes nothing."""

    def sheet(parts: list[Any], wires: list[Any], labels: list[Any]) -> dict[str, Any]:
        return {
            "schema": 9,
            "id": "t",
            "name": "t",
            "parts": parts,
            "wires": wires,
            "labels": labels,
        }

    r1 = {"ref": "R1", "type": "resistor", "value": "1k", "pos": [100, 0]}  # pins at x 80 and 120
    left = {"net": "L", "pos": [80, 0]}
    cases = {
        # a lead 60 long from R1.2 to a label: the diode fits in it
        "lead": sheet(
            [r1], [{"from": [120, 0], "to": [180, 0]}], [left, {"net": "N", "pos": [180, 0]}]
        ),
        # R1.2 sits part-way along a rail
        "rail": sheet(
            [r1, {"ref": "R5", "type": "resistor", "value": "1k", "pos": [120, 70], "rot": 90}],
            [{"from": [120, -50], "to": [120, 50]}],
            [left, {"net": "N", "pos": [120, -50]}],
        ),
        # a part right beside each end: no room along the line
        "boxed": sheet(
            [
                r1,
                {"ref": "R8", "type": "resistor", "value": "1k", "pos": [50, 0]},
                {"ref": "R9", "type": "resistor", "value": "1k", "pos": [150, 0]},
            ],
            [{"from": [120, 0], "to": [120, -40]}],
            [
                {"net": "N", "pos": [120, -40]},
                {"net": "X", "pos": [170, 0]},
                {"net": "Y", "pos": [30, 0]},
            ],
        ),
        # R1.2 touches R9.1 with no wire between
        "touching": sheet(
            [r1, {"ref": "R9", "type": "resistor", "value": "1k", "pos": [140, 0]}],
            [],
            [left, {"net": "N", "pos": [160, 0]}],
        ),
    }
    out = run(
        js,
        """
      const { insertInSeries } = await m('editor/insert.js');
      const d = {ref: 'D9', type: 'diode', model: '1N4148'};
      const at = (c, spot) => insertInSeries(c, 'R1', '2', d, 'A', {spot});
      return Object.fromEntries(Object.entries(arg).map(([k, c]) => [k, {beside: at(c, false), any: at(c, true)}]));
    """,
        cases,
    )
    for name in ("lead", "rail"):
        placed = out[name]["beside"]
        (d9,) = [p for p in placed["parts"] if p["ref"] == "D9"]
        assert d9["pos"] == [140, 0] and d9.get("rot", 0) == 0  # anode on R1.2, along its line
        nets = connect(parse_circuit(placed))
        assert set(nets.members[nets.net_of("R1", "2")]) == {("R1", "2"), ("D9", "A")}
        assert nets.net_of("D9", "K") == "N"
    rail = connect(parse_circuit(out["rail"]["beside"]))
    assert rail.net_of("R5", "1") == "N"  # the rail's two ends still joined, at D9's cathode
    assert out["boxed"]["beside"] is None
    boxed = out["boxed"]["any"]
    nets = connect(parse_circuit(boxed))
    assert set(nets.members[nets.net_of("R1", "2")]) == {("R1", "2"), ("D9", "A")}
    assert nets.net_of("D9", "K") == "N" and nets.net_of("R9", "1") != "N"
    assert out["touching"]["beside"] is None and out["touching"]["any"] is None


def test_room_is_made_by_moving_everything_past_a_line(js: Page) -> None:
    """D-124: with no room beside a pin, the sheet is split past it and everything beyond
    moves out a part's length: wires across the line stretch, a pin parted from what it
    touched gets a straight wire across the gap, so every pin is joined as before; then
    the part fits beside the pin. A pin touching another part's pin gets room the same way."""

    def r(ref: str, pos: list[int], rot: int = 0) -> dict[str, Any]:
        return {
            "ref": ref,
            "type": "resistor",
            "value": "1k",
            "pos": pos,
            **({"rot": rot} if rot else {}),
        }

    def d(ref: str, pos: list[int]) -> dict[str, Any]:
        return {"ref": ref, "type": "diode", "model": "1N4148", "pos": pos, "rot": 90}

    def gnd(*points: list[int]) -> list[dict[str, Any]]:
        return [{"net": "GND", "pos": p} for p in points]

    cramped = {  # two diodes from a signal line to a ground bus, a cap tucked under them
        "schema": 9, "id": "t", "name": "t",
        "parts": [d("D1", [100, 20]), d("D2", [200, 20]), {"ref": "C1", "type": "capacitor", "value": "100n", "pos": [100, 70]},
                  r("R5", [400, 100], 90), r("R6", [300, 120], 90)],
        "wires": [{"from": [60, 0], "to": [240, 0]}, {"from": [100, 40], "to": [240, 40]}, {"from": [300, -40], "to": [300, 100]}],
        "labels": [{"net": "S", "pos": [60, 0]}, {"net": "S", "pos": [400, 80]}, {"net": "X", "pos": [300, -40]},
                   *gnd([240, 40], [80, 70], [120, 70], [400, 120], [300, 140])],
    }  # fmt: skip
    touching = {  # R1's pin on R9's, no wire between
        "schema": 9, "id": "t", "name": "t", "parts": [r("R1", [100, 0]), r("R9", [140, 0])], "wires": [],
        "labels": [{"net": "L", "pos": [80, 0]}, {"net": "N", "pos": [160, 0]}],
    }  # fmt: skip
    out = run(
        js,
        """
      const { insertInSeries, makeRoom } = await m('editor/insert.js');
      const part = {ref: 'D9', type: 'diode', model: '1N4148'};
      const [cramped, touching] = arg;
      const room = makeRoom(cramped, 'D1', 'K');
      const room2 = makeRoom(touching, 'R1', '2');
      return {
        before: insertInSeries(cramped, 'D1', 'K', part, 'A', {spot: false}),
        room, after: insertInSeries(room.circuit, 'D1', 'K', part, 'A', {spot: false}),
        room2, after2: insertInSeries(room2.circuit, 'R1', '2', part, 'A', {spot: false}),
      };
    """,
        [cramped, touching],
    )

    def joined(c: dict[str, Any]) -> set[frozenset[tuple[str, str]]]:
        return {frozenset(g) for g in connect(parse_circuit(c)).members.values()}

    assert out["before"] is None  # C1 is in the way
    room = out["room"]
    assert room["way"] == "down" and room["moved"] == ["C1", "R6", "R5"]  # nearest first
    parts = {p["ref"]: p["pos"] for p in room["circuit"]["parts"]}
    assert parts["D1"] == [100, 20] and parts["D2"] == [200, 20] and parts["C1"] == [100, 110]
    assert {"from": [300, -40], "to": [300, 140]} in room["circuit"][
        "wires"
    ]  # stretched, still straight
    assert joined(room["circuit"]) == joined(cramped)
    (d9,) = [p for p in out["after"]["parts"] if p["ref"] == "D9"]
    assert d9["pos"] == [100, 60]  # straight under D1, in the gap
    assert out["room2"]["moved"] == ["R9"] and joined(out["room2"]["circuit"]) == joined(touching)
    assert out["after2"] is not None


def test_a_dual_is_placed_renamed_and_deleted_as_its_chip(js: Page) -> None:
    """A dual op-amp is placed as both halves, IC1A and IC1B beside it, and its power unit
    IC1C right of them; the next chip is IC2; renaming a half renames the chip; deleting a
    half takes the rest (D-140, D-179)."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const one = e.addPart({ parts: [] }, 'opamp', [0, 0], 0, { opamp: ['TL071', 'TL072'] });
        const two = e.addPart(one.circuit, 'opamp', [0, 200]);
        const single = e.addPart(two.circuit, 'opamp-single', [0, 400]);
        const quad = e.addPart(single.circuit, 'opamp-quad', [0, 600], 0, { opamp: ['TL072', 'TL074'] });
        const renamed = e.renameChip(single.circuit, 'IC2B', 'IC7');
        return {
          ref: one.ref,
          halves: one.circuit.parts.map((p) => [p.ref, p.half ?? p.type, p.pos, p.model]),
          second: two.ref, single: [single.ref, single.circuit.parts.at(-1).half ?? null],
          partner: [e.chipRefs(two.circuit, 'IC1A'), e.chipRefs(two.circuit, 'IC2B'), e.chipRefs(single.circuit, 'IC3')],
          quad: [quad.ref, quad.circuit.parts.slice(-5).map((p) => [p.ref, p.half ?? p.type, p.pos, p.model])],
          quadDeletes: e.withChips(quad.circuit, ['IC4C']).sort(),
          quadRenamed: e.renameChip(quad.circuit, 'IC4E', 'IC9').parts.slice(-5).map((p) => p.ref),
          renamed: renamed.parts.map((p) => p.ref),
          deletes: e.withChips(single.circuit, ['IC1B', 'IC3']).sort(),
        };
        """,
    )
    assert r["ref"] == "IC1A"
    assert r["halves"] == [
        ["IC1A", "a", [0, 0], "TL072"], ["IC1B", "b", [120, 0], "TL072"],
        ["IC1C", "powerunit", [220, 0], "TL072"],
    ]  # fmt: skip
    assert r["second"] == "IC2A"
    assert r["single"] == ["IC3", None]
    assert r["partner"] == [["IC1A", "IC1B", "IC1C"], ["IC2A", "IC2B", "IC2C"], None]
    # a quad (D-172): IC4A to IC4D, c and d under a and b, its power unit IC4E between the rows
    assert r["quad"] == ["IC4A", [
        ["IC4A", "a", [0, 600], "TL074"], ["IC4B", "b", [120, 600], "TL074"],
        ["IC4C", "c", [0, 720], "TL074"], ["IC4D", "d", [120, 720], "TL074"],
        ["IC4E", "powerunit", [220, 660], "TL074"],
    ]]  # fmt: skip
    assert r["quadDeletes"] == ["IC4A", "IC4B", "IC4C", "IC4D", "IC4E"]
    assert r["quadRenamed"] == ["IC9A", "IC9B", "IC9C", "IC9D", "IC9E"]
    assert r["renamed"] == ["IC1A", "IC1B", "IC1C", "IC7A", "IC7B", "IC7C", "IC3"]
    assert r["deletes"] == ["IC1A", "IC1B", "IC1C", "IC3"]


def test_a_4049_and_an_lm13700_are_placed_and_deleted_as_their_chips(js: Page) -> None:
    """D-180: a hex inverter is placed as IC1A to IC1F in two rows of three with its power
    unit IC1G; a dual OTA as IC2A and IC2B with IC2C; a CA3080 is a single. Renaming or
    deleting one unit takes the chip."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const hex = e.addPart({ parts: [] }, 'inverter', [0, 0], 0, { inverter: ['CD4049UB'] });
        const ota = e.addPart(hex.circuit, 'ota-dual', [0, 300], 0, { ota: ['CA3080', 'LM13700'] });
        const single = e.addPart(ota.circuit, 'ota-single', [0, 500], 0, { ota: ['CA3080', 'LM13700'] });
        return {
          hex: [hex.ref, hex.circuit.parts.map((p) => [p.ref, p.half ?? p.type, p.pos, p.model])],
          ota: [ota.ref, ota.circuit.parts.slice(-3).map((p) => [p.ref, p.half ?? p.type, p.pos, p.model])],
          single: [single.ref, single.circuit.parts.at(-1).half ?? null, single.circuit.parts.at(-1).model],
          deletes: e.withChips(single.circuit, ['IC1D', 'IC2C']).sort(),
          renamed: e.renameChip(single.circuit, 'IC1G', 'IC5').parts.slice(0, 7).map((p) => p.ref),
        };
        """,
    )
    assert r["hex"] == ["IC1A", [
        ["IC1A", "a", [0, 0], "CD4049UB"], ["IC1B", "b", [100, 0], "CD4049UB"],
        ["IC1C", "c", [200, 0], "CD4049UB"], ["IC1D", "d", [0, 80], "CD4049UB"],
        ["IC1E", "e", [100, 80], "CD4049UB"], ["IC1F", "f", [200, 80], "CD4049UB"],
        ["IC1G", "powerunit", [300, 40], "CD4049UB"],
    ]]  # fmt: skip
    assert r["ota"] == ["IC2A", [
        ["IC2A", "a", [0, 300], "LM13700"], ["IC2B", "b", [180, 300], "LM13700"],
        ["IC2C", "powerunit", [340, 300], "LM13700"],
    ]]  # fmt: skip
    assert r["single"] == ["IC3", None, "CA3080"]
    assert r["deletes"] == [*(f"IC1{x}" for x in "ABCDEFG"), "IC2A", "IC2B", "IC2C"]
    assert r["renamed"] == [f"IC5{x}" for x in "ABCDEFG"]


def test_inspector_fields_for_op_amp_chips(js: Page) -> None:
    """A half's form: its model (duals only), the chip with its datasheet, a row per pin
    with its number, net and handling, and the other half; the power unit's, the chip's V+
    and V-; a single can draw all its pins (D-140, D-179)."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const pkg = (pins) => ({ name: '8-pin DIP', pins, source: 'the sheet' });
        const chips = {
          TL072: { halves: 2, simulated: ['+', '-', 'out', 'V+', 'V-'], package: pkg({ 'a.out': 1, 'a.-': 2, 'a.+': 3, 'V-': 4, 'b.+': 5, 'b.-': 6, 'b.out': 7, 'V+': 8 }) },
          TL074: { halves: 4, simulated: ['+', '-', 'out', 'V+', 'V-'], package: { name: '14-pin DIP', source: 'the sheet', pins: { 'a.out': 1, 'a.-': 2, 'a.+': 3, 'V+': 4, 'b.+': 5, 'b.-': 6, 'b.out': 7, 'c.out': 8, 'c.-': 9, 'c.+': 10, 'V-': 11, 'd.+': 12, 'd.-': 13, 'd.out': 14 } } },
          TL071: { halves: 1, simulated: ['+', '-', 'out', 'V+', 'V-'], package: pkg({ null1: 1, '-': 2, '+': 3, 'V-': 4, null2: 5, out: 6, 'V+': 7, nc: 8 }) },
        };
        const pins = (ref, nets) => ({ ref, pins: Object.entries(nets).map(([name, net]) => ({ name, net })) });
        const view = {
          labels: [{ net: 'V+' }, { net: 'GND' }, { net: 'in' }],
          parts: [pins('IC1A', { '+': 'in', '-': 'IC1A.-', out: 'IC1A.out' }),
                  { ...pins('IC1B', { '+': 'IC1B.+', '-': 'IC1B.-', out: 'IC1B.out' }), draw: { unused: true } },
                  pins('IC1C', { 'V+': 'V+', 'V-': 'GND' })],
        };
        const half = (ref, model) => ({ ref, type: 'opamp', model, half: ref.at(-1).toLowerCase() });
        const unit = (ref, model) => ({ ref, type: 'powerunit', model });
        const circuit = { parts: [half('IC1A', 'TL072'), half('IC1B', 'TL072'), unit('IC1C', 'TL072'),
          ...['A', 'B', 'C', 'D'].map((x) => half(`IC3${x}`, 'TL074')), unit('IC3E', 'TL074')] };
        const ctx = { circuit, models: { opamp: ['TL071', 'TL072', 'TL074'] }, chips, view };
        const a = f.inspectorFields({ ref: 'IC1A', type: 'opamp', model: 'TL072', half: 'a' }, ctx);
        const c = f.inspectorFields(half('IC3C', 'TL074'), { ...ctx, view: { labels: [], parts: [{ ref: 'IC3D', pins: [], draw: { unused: true } }] } });
        const single = f.inspectorFields({ ref: 'IC2', type: 'opamp', model: 'TL071' }, ctx);
        const power = f.inspectorFields(unit('IC1C', 'TL072'), ctx);
        return {
          a: a.map((x) => [x.name, x.label, x.value]),
          models: a.find((x) => x.name === 'model').options,
          single: single.map((x) => x.name),
          quad: c.filter((x) => ['model', 'chip', 'pin_out', 'other_half'].includes(x.name)).map((x) => [x.name, x.value, x.hint ?? '']),
          chipAbout: c.find((x) => x.name === 'chip').about,
          quadModels: c.find((x) => x.name === 'model').options,
          quadPins: c.filter((x) => x.name.startsWith('pin_')).map((x) => x.label),
          power: power.map((x) => [x.name, x.label, x.value]),
          powerModels: power.find((x) => x.name === 'model').options,
          powerRef: f.editFrom(unit('IC1C', 'TL072'), { ref: 'IC5' }).ref,
          shown: f.editFrom({ ref: 'IC2', type: 'opamp' }, { ref: 'IC2', show_pins: 'on' }).patch.show_pins,
        };
        """,
    )
    assert r["a"] == [
        ["ref", "Ref", "IC1A"],
        ["model", "Model", "TL072"],
        ["chip", "Chip", "IC1, a dual: IC1A and IC1B, powered from IC1C"],
        ["pin_out", "Pin 1 · out", "not connected"],
        ["pin_-", "Pin 2 · − in", "not connected"],
        ["pin_+", "Pin 3 · + in", "in"],
        ["other_half", "Other half", "IC1B, not used"],
    ]
    assert r["models"] == [["TL072", "TL072"]]
    assert r["power"] == [
        ["ref", "Ref", "IC1C"],
        ["model", "Model", "TL072"],
        ["chip", "Chip", "IC1, a dual: IC1A and IC1B, powered from IC1C"],
        ["pin_V-", "Pin 4 · V−", "GND"],
        ["pin_V+", "Pin 8 · V+", "V+"],
        ["other_half", "Op-amps", "IC1A, in use; IC1B, not used"],
    ]
    assert r["powerModels"] == [["TL072", "TL072"]]
    assert r["powerRef"] == "IC5C"
    assert r["quad"] == [
        [
            "model",
            "TL074",
            "One model for the chip: changing it changes IC3A, IC3B, IC3C, IC3D and IC3E.",
        ],
        [
            "chip",
            "IC3, a quad: IC3A to IC3D, powered from IC3E",
            "Pin numbers: 14-pin DIP.",  # where they come from is in the ⓘ, not under the box
        ],
        ["pin_out", "not drawn", r["quad"][2][2]],
        [
            "other_half",
            "IC3A, in use; IC3B, in use; IC3D, not used",
            "Problems says how to wire it as a buffer. IC3E carries the chip's V+ and V-.",
        ],
    ]
    assert r["chipAbout"] == "The pin numbers are from the sheet."
    assert r["quadModels"] == [["TL074", "TL074"]]
    assert r["quadPins"] == ["Pin 8 · out", "Pin 9 · − in", "Pin 10 · + in"]
    assert r["single"][-1] == "show_pins"
    assert r["shown"] is True


def test_palette_refs_follow_the_ref_rules(js: Page) -> None:
    """D-141: each palette tile starts its parts on its type's first prefix (refs.py), and
    the parts it places pass the schema's ref check; IN and OUT are fixed."""
    from solum.circuit.refs import FIXED, PREFIXES, ref_problem

    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        (await m('schematic/symbols.js')).setSwitchKinds(arg);
        let c = { parts: [] };
        const placed = [];
        for (const entry of e.PALETTE) {
          if (!entry.prefix) continue;
          const before = c.parts.length;
          c = e.addPart(c, entry.tool ?? entry.type, [placed.length * 200, 0]).circuit;
          placed.push([entry.type, entry.prefix, ...c.parts.slice(before).map((p) => [p.type, p.ref, p.half ?? p.pole ?? null])]);
        }
        return placed;
        """,
        catalogue(),
    )
    for kind, prefix, *parts in r:
        assert prefix == FIXED.get(kind, PREFIXES.get(kind, ("?",))[0]), kind
        for part_type, ref, half in parts:  # a chip's power unit has a type of its own (D-179)
            assert ref_problem(part_type, ref, half) is None, (part_type, ref)


def test_a_switch_is_placed_renamed_retyped_and_deleted_whole(js: Page) -> None:
    """D-143: a footswitch is placed as its three poles side by side; the next switch is
    SW2; renaming a pole renames the switch; a new type adds or takes away poles; deleting
    a pole takes the switch."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        (await m('schematic/symbols.js')).setSwitchKinds(arg);
        // a footswitch is a switch given that type (D-143): its form adds the poles
        const placed = e.addPart({ parts: [] }, 'switch', [0, 0]);
        const fs = { circuit: e.setSwitchPoles(placed.circuit, placed.ref, 3, { kind: 'footswitch' }), ref: 'SW1A' };
        const two = e.addPart(fs.circuit, 'switch', [0, 200]);
        const renamed = e.renameChip(two.circuit, 'SW1B', 'SW5');
        const dpdt = e.setSwitchPoles(two.circuit, 'SW2', 2, { kind: 'dpdt', position: 1, label: 'Mode' });
        const back = e.setSwitchPoles(dpdt, 'SW2B', 1, { kind: 'spdt', position: 0 });
        // a part at (0, 0) has no pos in the file
        const origin = e.setSwitchPoles({ parts: [{ ref: 'SW1', type: 'switch' }] }, 'SW1', 2, { kind: 'dpdt' });
        const pick = (c) => c.parts.map((p) => [p.ref, p.kind, p.pole ?? null, p.pos, p.position ?? 0]);
        return {
          ref: fs.ref, poles: pick(fs.circuit), second: two.ref,
          renamed: renamed.parts.map((p) => p.ref), dpdt: pick(dpdt), back: pick(back),
          deletes: e.withChips(two.circuit, ['SW1B']).sort(), groups: e.groupRefs(two.circuit, 'SW2'),
          origin: origin.parts.map((p) => [p.ref, p.pos]),
        };
        """,
        catalogue(),
    )
    assert r["ref"] == "SW1A"
    assert r["poles"] == [
        ["SW1A", "footswitch", "a", [0, 0], 0],
        ["SW1B", "footswitch", "b", [0, 80], 0],  # stacked, A over B over C, 80 apart (poleStep)
        ["SW1C", "footswitch", "c", [0, 160], 0],
    ]
    assert r["second"] == "SW2"
    assert r["renamed"] == ["SW5A", "SW5B", "SW5C", "SW2"]
    assert r["dpdt"][3:] == [
        ["SW2A", "dpdt", "a", [0, 200], 1],
        ["SW2B", "dpdt", "b", [0, 280], 1],
    ]
    assert r["back"][3:] == [["SW2", "spdt", None, [0, 200], 0]]
    assert r["deletes"] == ["SW1A", "SW1B", "SW1C"]
    assert r["groups"] == ["SW2"]
    assert r["origin"] == [["SW1A", [0, 0]], ["SW1B", [0, 80]]]
    for circuit in ("dpdt", "back"):
        parts = [{"ref": p[0], "type": "switch", "kind": p[1], "pole": p[2], "position": p[4]}
                 for p in r[circuit]]  # fmt: skip
        parse_circuit(
            {"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": parts}
        )  # the server takes it


def test_a_dual_pot_is_made_renamed_pasted_and_deleted_whole(js: Page) -> None:
    """D-217: a pot made Dual becomes VR1A and VR1B side by side, every gang taking the
    form's value, taper, rotation and label; renaming, pasting and deleting take both;
    Single takes gang B away again."""
    r = run(
        js,
        """
        const e = await m('editor/edit.js');
        const b = await m('editor/blocks.js');
        const placed = e.addPart({ parts: [] }, 'pot', [0, 0]);
        const fields = { value: '250k', taper: 'A', rotation: 0.3, label: 'Drive' };
        const dual = e.setSwitchPoles(placed.circuit, 'VR1', 2, fields);
        const renamed = e.renameChip(dual, 'VR1B', 'VR4');
        const single = e.setSwitchPoles(dual, 'VR1B', 1, fields);
        const copy = b.extract(dual, { parts: ['VR1A', 'VR1B'] }, { parts: ['VR1A', 'VR1B'], wires: [], labels: [], texts: [] });
        const pasted = b.pasteBlock(dual, copy, { at: [400, 400] }).circuit;
        const pick = (c) => c.parts.map((p) => [p.ref, p.gang ?? null, p.pos, p.value, p.taper, p.rotation, p.label]);
        return {
          dual: pick(dual), renamed: renamed.parts.map((p) => p.ref), single: pick(single),
          pasted: pasted.parts.map((p) => p.ref), deletes: e.withChips(dual, ['VR1B']).sort(),
          groups: e.groupRefs(placed.circuit, 'VR1'),
        };
        """,
    )
    assert r["dual"] == [
        ["VR1A", "a", [0, 0], "250k", "A", 0.3, "Drive"],
        ["VR1B", "b", [80, 0], "250k", "A", 0.3, "Drive"],  # beside gang A
    ]
    assert r["renamed"] == ["VR4A", "VR4B"]
    assert r["single"] == [["VR1", None, [0, 0], "250k", "A", 0.3, "Drive"]]
    assert r["pasted"] == ["VR1A", "VR1B", "VR2A", "VR2B"]
    assert r["deletes"] == ["VR1A", "VR1B"]
    assert r["groups"] == ["VR1"]
    parts = [{"ref": p[0], "type": "pot", "gang": p[1], "value": p[3], "taper": p[4],
              "rotation": p[5], "label": p[6]} for p in r["dual"]]  # fmt: skip
    parse_circuit({"schema": SCHEMA_VERSION, "id": "x", "name": "x", "parts": parts})


def test_a_diode_set_to_a_zener_is_named_z(js: Page) -> None:
    """D-229: a diode's ref follows its model when left as it was: D1 set to a zener is
    the next free Z, Z1 set back to a plain diode the next free D; a typed ref wins, and a
    ref of your own (CLIP1) is kept."""
    r = run(
        js,
        """
        const f = await m('editor/fields.js');
        const d1 = { ref: 'D1', type: 'diode', model: '1N4148' };
        const z1 = { ref: 'Z1', type: 'diode', model: '1N4742A' };
        const circuit = { parts: [d1, z1, { ref: 'D2', type: 'diode', model: '1N4148' }] };
        const ctx = { circuit, zeners: ['1N4742A', '1N4739A'] };
        const ref = (part, values) => f.editFrom(part, { ref: part.ref, ...values }, ctx).ref;
        return {
          toZener: ref(d1, { model: '1N4739A' }),
          toPlain: ref(z1, { model: '1N914' }),
          zenerToZener: ref(z1, { model: '1N4739A' }),
          same: ref(d1, { model: '1N4148' }),
          typed: ref(d1, { model: '1N4739A', ref: 'D7' }),
          own: ref({ ...d1, ref: 'CLIP1' }, { model: '1N4739A' }),
          noCircuit: f.editFrom(d1, { ref: 'D1', model: '1N4739A' }, {}).ref,
        };
        """,
    )
    assert r == {
        "toZener": "Z2",
        "toPlain": "D3",
        "zenerToZener": "Z1",
        "same": "D1",
        "typed": "D7",
        "own": "CLIP1",
        "noCircuit": "D1",
    }
