# ruff: noqa: E501  (JavaScript inside strings)
"""The notes' logic (web/notes-logic.js, 9d4), run in Chromium: general, part and net
notes set and removed, the Parts tab's order, whole-word mentions of a renamed name and
replacing the ticked ones, and naming a net before its note."""

from playwright.sync_api import Page

from tests.ui.conftest import run


def test_general_part_and_net_notes(js: Page) -> None:
    r = run(
        js,
        """
        const n = await m('notes-logic.js');
        const c = { parts: [{ ref: 'R10', type: 'resistor' }, { ref: 'R2', type: 'resistor', note: 'old' }], labels: [{ net: 'TONE', pos: [0, 0] }] };
        const one = n.addNote(c, { title: ' Build ', text: 'Socket Q1.  ' });
        const two = n.addNote(one, { title: 'Bias' });
        const edited = n.setNote(two, 1, { title: 'Bias', text: 'TR1 to 4.5 V' });
        const emptied = n.setNote(two, 0, { title: ' ', text: '' });
        const parts = n.setPartNote(n.setPartNote(c, 'R10', ' sets the gain '), 'R2', '');
        const nets = n.setNetNote(n.setNetNote(c, 'VREF', 'half'), 'TONE', 'the tone');
        return { c, one: one.notes, edited: edited.notes, emptied: emptied.notes, gone: n.deleteNote(one, 0),
                 parts: parts.parts, nets: nets.net_notes, cleared: n.setNetNote(n.setNetNote(c, 'X', 'x'), 'X', ''),
                 items: n.itemNotes({ ...parts, parts: [...parts.parts, { ref: 'C1', note: 'film' }], net_notes: { VREF: 'half', TONE: 't' } }),
                 named: [n.isNamedNet(c, 'TONE'), n.isNamedNet({ ...c, power: { rails: { 'V+': 9 } } }, 'V+'), n.isNamedNet(c, 'Q1.D')] };
        """,
    )
    assert r["c"]["parts"][1] == {
        "ref": "R2",
        "type": "resistor",
        "note": "old",
    }  # never changed in place
    assert r["one"] == [{"title": "Build", "text": "Socket Q1."}]  # trimmed
    assert r["edited"][1] == {"title": "Bias", "text": "TR1 to 4.5 V"}
    assert r["emptied"] == [{"title": "Bias"}]  # no title or text left: it goes
    assert "notes" not in r["gone"]
    assert r["parts"] == [
        {"ref": "R10", "type": "resistor", "note": "sets the gain"},
        {"ref": "R2", "type": "resistor"},
    ]
    assert r["nets"] == {"VREF": "half", "TONE": "the tone"}
    assert "net_notes" not in r["cleared"]
    assert [(i["kind"], i["id"]) for i in r["items"]] == [
        ("part", "C1"),
        ("part", "R10"),
        ("net", "TONE"),
        ("net", "VREF"),
    ]
    assert r["named"] == [True, True, False]


def test_whole_word_mentions_and_replacing_the_ticked_ones(js: Page) -> None:
    r = run(
        js,
        """
        const n = await m('notes-logic.js');
        const c = {
          parts: [{ ref: 'C9', note: 'Was C7 on the board; C70 is another.' }, { ref: 'R1' }],
          notes: [{ title: 'C7 and TI', text: "TI's C7 is 22n. Swap C7 (and IC7, C7A) later." }],
          net_notes: { VREF: 'C7 holds it.' },
        };
        const found = n.mentions(c, [{ from: 'C7', to: 'C9' }]);
        const ticked = found.filter((x) => !(x.field === 'text' && x.where.kind === 'general' && x.start === 5));
        return {
          words: n.wordsAt('C7, C70, IC7, C7A, (C7) C7', 'C7'),
          found: found.map((x) => [x.where.kind, x.field, x.start, x.label, x.before, x.after]),
          count: n.notesCount(found),
          all: n.replaceMentions(c, found),
          some: n.replaceMentions(c, ticked),
          chip: n.renamesOf(['IC1A', 'IC1B', 'IC1C'], ['IC2A', 'IC2B', 'IC2C']),
          one: n.renamesOf(['C7'], ['C9']),
          same: n.renamesOf(['C7'], ['C7']),
        };
        """,
    )
    assert r["words"] == [0, 20, 24]
    assert [f[:4] for f in r["found"]] == [
        ["general", "title", 0, "C7 and TI"],
        ["general", "text", 5, "C7 and TI"],
        ["general", "text", 21, "C7 and TI"],
        ["part", "text", 4, "C9's note"],
        ["net", "text", 0, "VREF's note"],
    ]
    assert r["found"][1][4:] == ["TI's ", " is 22n. Swap C7 (and IC7, C7A\u2026"]
    assert r["count"] == 3
    assert r["all"]["notes"] == [
        {"title": "C9 and TI", "text": "TI's C9 is 22n. Swap C9 (and IC7, C7A) later."}
    ]
    assert r["all"]["parts"][0]["note"] == "Was C9 on the board; C70 is another."
    assert r["all"]["net_notes"] == {"VREF": "C9 holds it."}
    # TI's own C7 left unticked: kept as the source wrote it
    assert r["some"]["notes"][0]["text"] == "TI's C7 is 22n. Swap C9 (and IC7, C7A) later."
    assert r["chip"] == [
        {"from": "IC1", "to": "IC2"},
        {"from": "IC1A", "to": "IC2A"},
        {"from": "IC1B", "to": "IC2B"},
        {"from": "IC1C", "to": "IC2C"},
    ]
    assert r["one"] == [{"from": "C7", "to": "C9"}]
    assert r["same"] == []


def test_an_unnamed_net_takes_a_label_before_its_note(js: Page) -> None:
    r = run(
        js,
        """
        const n = await m('notes-logic.js');
        const c = { parts: [], wires: [{ from: [0, 0], to: [100, 0] }], labels: [{ net: 'TONE', pos: [0, 50] }] };
        const err = (f) => { try { f(); return null; } catch (e) { return e.message; } };
        return {
          named: n.nameNet(c, 0, [43, 7], 'MID').labels,
          taken: err(() => n.nameNet(c, 0, [40, 0], 'TONE')),
          gnd: err(() => n.nameNet(c, 0, [40, 0], 'GND')),
          spaced: err(() => n.nameNet(c, 0, [40, 0], 'A B')),
          empty: err(() => n.nameNet(c, 0, [40, 0], '')),
        };
        """,
    )
    assert r["named"][1] == {"net": "MID", "pos": [40, 0]}  # on the wire, on the grid
    assert "another net's name" in r["taken"] and "another net's name" in r["gnd"]
    assert "no spaces or dots" in r["spaced"]
    assert "Give the net a name" in r["empty"]
