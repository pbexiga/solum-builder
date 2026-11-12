# ruff: noqa: E501  (JavaScript inside strings)
"""Blocks in the editor (web/editor/blocks.js), run in Chromium and checked against the
server's connectivity: paste-flatten keeps a block's nets, renumbers refs without
collisions, joins only the supplies and GND, splices into a wire; extract and markPort."""

import json
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from playwright.sync_api import Page

from solum.circuit.connectivity import Nets, connect
from solum.circuit.io import circuit_to_dict, parse_circuit
from solum.circuit.schema import SCHEMA_VERSION, Circuit
from tests.ui.conftest import REPO, run

BLOCKS = sorted(p.stem for p in (REPO / "library" / "blocks").glob("*.json"))
STARTERS = sorted(p.stem for p in (REPO / "library" / "starters").glob("*.json"))
GLOBAL = {"V+", "V-", "GND"}


def load(folder: str, name: str) -> dict[str, Any]:
    """A library file as the app serves it: migrated to the current schema."""
    raw = json.loads((REPO / "library" / folder / f"{name}.json").read_text())
    return circuit_to_dict(parse_circuit(raw))


def paste(js: Page, host: dict[str, Any], block: dict[str, Any], **opts: Any) -> dict[str, Any]:
    result: dict[str, Any] = run(
        js,
        "const b = await m('editor/blocks.js'); return b.pasteBlock(arg.host, arg.block, arg.opts);",
        {"host": host, "block": block, "opts": opts},
    )
    return result


def same_net_pairs(nets: Nets, pins: list[tuple[str, str]]) -> set[frozenset[tuple[str, str]]]:
    return {frozenset((a, b)) for a in pins for b in pins
            if a < b and nets.net_of(*a) == nets.net_of(*b)}  # fmt: skip


def check_paste(host: Circuit, block: Circuit, pasted: Circuit, refs: dict[str, str]) -> None:
    """The block's nets come through the paste unchanged and touch nothing of the host's
    except by the supplies and GND. A part the host already has its one of (a DC jack
    pasted twice) is left out, so isn't in `refs`."""
    bn, pn, hn = connect(block), connect(pasted), connect(host)
    block_pins = [(r, pin) for r, pin in bn.by_pin if r in refs]
    moved = [(refs[r], pin) for r, pin in block_pins]
    rename = dict(zip(block_pins, moved, strict=True))
    expected = {frozenset(rename[p] for p in pair) for pair in same_net_pairs(bn, block_pins)}
    assert same_net_pairs(pn, moved) == expected
    host_pins = set(hn.by_pin)
    for pin in block_pins:
        net = pn.net_of(*rename[pin])
        if bn.net_of(*pin) in GLOBAL:
            assert net == bn.net_of(*pin)
        else:
            assert not host_pins & set(pn.members[net]), f"{pin} joined a host net {net}"
    # the host's own nets are as they were
    for a in host_pins:
        assert pn.net_of(*a) in pn.members
    assert same_net_pairs(pn, sorted(host_pins)) == same_net_pairs(hn, sorted(host_pins))


def test_core_blocks_paste_into_every_starter(js: Page) -> None:
    for name in BLOCKS:
        block = load("blocks", name)
        for starter in STARTERS:
            host = load("starters", starter)
            r = paste(js, host, block, at=[1000, 1000])
            pasted = parse_circuit(r["circuit"])  # unique refs, valid file
            check_paste(parse_circuit(host), parse_circuit(block), pasted, r["refs"])
            assert "provenance" not in r["circuit"]  # a plain copy: nothing links back (D-075)


def test_a_drop_never_ties_a_blocks_ground_to_a_signal_wire(js: Page) -> None:
    """D-270, found by Hypothesis: the DC jack and battery block dropped a third time on the
    Klon (its DC jack left out, the sheet has one) had its ground wiring land along a Klon
    signal wire. That counted as a join (D-164) and grounded R15.2; it now moves aside."""
    circuit = load("starters", "klon-centaur")
    b = load("blocks", "battery-dc-power-v1")
    for i in range(3):
        before = parse_circuit(circuit)
        r = paste(js, circuit, b, at=[400 * i, 205])
        check_paste(before, parse_circuit(b), parse_circuit(r["circuit"]), r["refs"])
        circuit = r["circuit"]


def test_a_block_wire_lying_along_a_sheet_wire_is_not_a_join(js: Page) -> None:
    """D-285, found by Hypothesis: the same block dropped a third time on the Klon at
    (965, -106) had the wire from its battery's + lie along a long Klon wire (U2A's
    inverting input). That counted as a join (D-164) and put the battery on the op-amp's
    input; a wire over a wire isn't a drop made to join, so it now moves aside."""
    circuit = load("starters", "klon-centaur")
    b = load("blocks", "battery-dc-power-v1")
    for i in range(3):
        before = parse_circuit(circuit)
        r = paste(js, circuit, b, at=[165 + 400 * i, -106])
        check_paste(before, parse_circuit(b), parse_circuit(r["circuit"]), r["refs"])
        circuit = r["circuit"]


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    block=st.sampled_from(BLOCKS),
    host=st.sampled_from(STARTERS),
    times=st.integers(1, 3),
    at=st.tuples(st.integers(-2000, 2000), st.integers(-2000, 2000)),
)
def test_pasting_again_and_again_never_collides(js: Page, block: str, host: str, times: int,
                                                at: tuple[int, int]) -> None:  # fmt: skip
    circuit = load("starters", host)
    b = load("blocks", block)
    for i in range(times):
        before = parse_circuit(circuit)
        r = paste(js, circuit, b, at=[at[0] + 400 * i, at[1]])
        assert not set(r["refs"].values()) & {p.ref for p in before.parts}
        check_paste(before, parse_circuit(b), parse_circuit(r["circuit"]), r["refs"])
        circuit = r["circuit"]


def test_paste_details(js: Page) -> None:
    """Refs per prefix, port labels renamed when taken, bias targets and notes follow,
    the block lands on its anchor, a missing supply comes along."""
    host = {
        "schema": 4,
        "id": "h",
        "name": "Host",
        "power": {"rails": {"V-": -9.0}},
        "parts": [
            {"ref": "Q1", "type": "jfet", "model": "J201", "pos": [0, 0]},
            {"ref": "R1", "type": "resistor", "value": "1k", "pos": [100, 0]},
        ],
        "labels": [{"net": "in", "pos": [80, 0]}, {"net": "out", "pos": [120, 0]}],
    }
    block = load("blocks", "jfet-cs-stage-v1")
    q1 = next(p for p in block["parts"] if p["ref"] == "Q1")
    q1["note"] = "the gain stage"
    block["net_notes"] = {"Q1.D": "drain", "in": "input"}
    r = paste(js, host, block, at=[500, 300])
    c = r["circuit"]
    assert r["refs"] == {  # the Fetzer Valve's parts (D-266), renumbered in file order
        "C1": "C1",
        "R3": "R2",
        "Q1": "Q2",
        "R1": "R3",
        "TR1": "TR1",
        "R2": "R4",
        "C3": "C2",
        "C2": "C3",
        "VR1": "VR1",
    }
    assert r["ports"] == {"in": "in_2", "out": "out_2"}
    assert {lb["net"] for lb in c["labels"]} == {"in", "out", "in_2", "out_2", "V+", "GND"}
    rt1 = next(p for p in c["parts"] if p["ref"] == "TR1")
    assert rt1["bias_target"] == {"node": "Q2.D", "volts": 4.5}
    assert next(p for p in c["parts"] if p["ref"] == "Q2")["note"] == "the gain stage"
    assert c["net_notes"] == {"Q2.D": "drain", "in_2": "input"}
    [note] = c["notes"]  # the description, word for word, then the refs that changed
    assert note["title"] == f"From block: {block['name']}"
    assert note["text"] == (f"{block['description']}\n\nPasted with new refs: "
                            "R3 → R2, Q1 → Q2, R1 → R3, R2 → R4, C3 → C2, C2 → C3")  # fmt: skip
    assert c["power"]["rails"] == {"V-": -9.0, "V+": 9.0}  # V+ came along (the size of V-)
    anchor = run(js, "const b = await m('editor/blocks.js'); return b.blockAnchor(arg);", block)
    # clear of the host there, so it lands exactly where dropped
    q = next(p for p in c["parts"] if p["ref"] == "Q2")
    src = next(p for p in block["parts"] if p["ref"] == "Q1")
    assert q["pos"] == [src["pos"][0] - anchor[0] + 500, src["pos"][1] - anchor[1] + 300]
    assert "provenance" not in c  # a plain copy


def test_a_second_guitar_or_amp_is_left_out(js: Page) -> None:
    host = load("starters", "ts808")
    r = paste(js, host, host, at=[3000, 0])
    assert r["skipped"] == ["IN", "OUT"]
    assert "IN" not in r["refs"] and "OUT" not in r["refs"]
    pasted = parse_circuit(r["circuit"])
    assert [p.ref for p in pasted.parts if p.type in ("guitar", "amp")] == ["IN", "OUT"]
    assert len(pasted.parts) == 2 * len(host["parts"]) - 2


def test_a_block_dropped_twice_gives_two_general_notes(js: Page) -> None:
    """9d4: each drop adds its description as a general note; the first kept its refs, so
    it has no refs line, the second says which changed. A copied selection (no
    description) adds none."""
    block = load("blocks", "rangemaster-booster-v1")
    empty = {"schema": block["schema"], "id": "h", "name": "Host", "parts": []}
    once = paste(js, empty, block, at=[0, 0])["circuit"]
    twice = paste(js, once, block, at=[0, 600])["circuit"]
    first, second = twice["notes"]
    assert first["title"] == second["title"] == f"From block: {block['name']}"
    assert first["text"].startswith(block["description"])
    assert second["text"].startswith(block["description"])
    line = second["text"].split("\n\nPasted with new refs: ")[1]
    # every part of the second copy took a new ref, none already used by the first
    moved = dict(pair.split(" → ") for pair in line.split(", "))
    assert set(moved) == {p["ref"] for p in block["parts"]}
    assert not set(moved.values()) & {p["ref"] for p in once["parts"]}
    plain = {**block, "description": ""}
    assert "notes" not in paste(js, empty, plain, at=[0, 0])["circuit"]


def test_paste_moves_to_a_clear_spot(js: Page) -> None:
    """Dropped on top of the TS808, a block moves to the nearest place it touches nothing."""
    host = load("starters", "ts808")
    block = load("blocks", "vref-divider-v1")
    r = run(
        js,
        "const b = await m('editor/blocks.js'); return [b.clearSpot(arg.host, arg.block, [200, 0]), b.clearSpot(arg.host, arg.block, [5000, 5000])];",
        {"host": host, "block": block},
    )
    assert r[1] == [5000, 5000]
    assert r[0] != [200, 0]
    pasted = paste(js, host, block, at=[200, 0])
    assert (
        next(p for p in pasted["circuit"]["parts"] if p["ref"] == pasted["refs"]["R1"])["pos"]
        != block["parts"][0]["pos"]
    )


def test_splice_into_a_wire(js: Page) -> None:
    host = {
        "schema": SCHEMA_VERSION,
        "id": "h",
        "name": "Host",
        "power": {"rails": {"V+": 9.0}},
        "parts": [
            {"ref": "IN", "type": "guitar", "pos": [-200, 0]},
            {"ref": "OUT", "type": "amp", "pos": [400, 0]},
        ],
        "wires": [{"from": [-180, 0], "to": [380, 0]}],
    }
    block = load("blocks", "diode-clipper-gnd-v1")
    r = paste(js, host, block, at=[100, 100], splice=0)
    c = parse_circuit(r["circuit"])
    nets = connect(c)
    assert nets.net_of("IN", "out") == nets.net_of(r["refs"]["R1"], "1")
    assert nets.net_of("OUT", "in") == nets.net_of(r["refs"]["D1"], "A")
    assert nets.net_of("IN", "out") != nets.net_of("OUT", "in")
    assert {lb.net for lb in c.labels} == {"GND"}  # the in/out port labels went
    tmb = load("blocks", "vref-divider-v1")
    message = run(
        js,
        "const b = await m('editor/blocks.js'); try { b.pasteBlock(arg.host, arg.block, { at: [0, 0], splice: 0 }); } catch (e) { return e.message; }",
        {"host": host, "block": tmb},
    )
    assert (
        message
        == "Vref \u00b7 half-supply divider has no in and out ports, so it can't go into a wire. Drop it beside the wire instead."
    )


def test_extract_a_stage_and_mark_ports(js: Page, base_url: str) -> None:
    """Box-select the Big Muff's Q3 stage, take it out, mark in and out: the block holds
    the stage, keeps its ground and supply, and saves as a valid template."""
    view = js.evaluate("fetch('/api/starters/big-muff-pi-v3').then((r) => r.json())")
    r = run(
        js,
        """
        const b = await m('editor/blocks.js');
        const c = arg.circuit;
        const items = b.itemsInBox(c, [455, -150, 770, 160]);
        let block = b.extract(c, arg.view, items);
        block = b.markPort(block, arg.view, 'C5.1', 'in');
        block = b.markPort(block, arg.view, 'q3c', 'out');
        const errors = [];
        for (const [net, name] of [['GND', 'g'], ['q3c', 'out'], ['q3c', 'o u t'], ['tw', 'tone'], ['C5.1', 'q3c']]) {
          try { b.markPort(block, arg.view, net, name); } catch (e) { errors.push(e.message); }
        }
        return { items, block, errors, empty: b.isEmpty({ parts: [], wires: [], labels: [] }), all: b.allItems(c).parts.length };
        """,
        {"circuit": view["circuit"], "view": view},
    )
    assert r["items"]["parts"] == [
        "R23",
        "C5",
        "R19",
        "R20",
        "R17",
        "C12",
        "R18",
        "Q3",
        "R21",
        "C6",
        "D3",
        "D4",
    ]
    block = r["block"]
    assert block["ports"] == {"in": "in", "out": "q3c"}
    assert block["power"] == {"rails": {"V+": 9.0}}
    c = parse_circuit({**block, "template": True})
    nets = connect(c)
    assert nets.net_of("Q3", "E") == nets.net_of("R21", "1")
    assert nets.net_of("R21", "2") == "GND"
    assert nets.net_of("R18", "1") == "V+" or nets.net_of("R18", "2") == "V+"
    assert nets.net_of("C5", "1") == "in"
    assert r["errors"] == [
        "GND is a supply or ground: blocks connect to it by themselves, no port needed.",
        "There's already a port called out.",
        "Give the port a name without spaces or dots, like in or out.",
        "That net doesn't touch the selected parts. Click a wire or pin of the block.",
        "q3c already names another net in this block. Pick another name.",
    ]
    assert r["empty"] is True and r["all"] == len(view["circuit"]["parts"])


def test_no_block_file_is_stale(repo: Path) -> None:
    """Core blocks are templates with ports on labelled nets, and load as the current schema."""
    for name in BLOCKS:
        c = parse_circuit(load("blocks", name))
        assert c.template and c.ports, name


def shifted(circuit: dict[str, Any], dx: int, dy: int) -> dict[str, Any]:
    """Every part, wire and label of `circuit` moved by (dx, dy), as sets to compare."""

    def at(p: list[int]) -> tuple[int, int]:
        return (p[0] + dx, p[1] + dy)

    return {
        "parts": sorted((p["ref"], at(p.get("pos", [0, 0]))) for p in circuit["parts"]),
        "wires": sorted(
            tuple(sorted([at(w["from"]), at(w["to"])])) for w in circuit.get("wires", [])
        ),
        "labels": sorted((lb["net"], at(lb["pos"])) for lb in circuit.get("labels", [])),
    }


def test_moving_everything_moves_every_wire_and_label(js: Page) -> None:
    """Bug: a box over the whole 9 V filter, dragged by R1, left the V+ label and its wire behind."""
    for folder, names in (("blocks", BLOCKS), ("starters", STARTERS)):
        for name in names:
            c = load(folder, name)
            moved = run(
                js,
                "const b = await m('editor/blocks.js'); const e = await m('editor/edit.js');"
                " return e.moveItems(arg, b.allItems(arg), 60, -40);",
                c,
            )
            assert shifted(moved, 0, 0) == shifted(c, 60, -40), name


def test_moving_a_selection_keeps_every_connection(js: Page) -> None:
    """Half the Big Muff boxed and moved: wires to the rest are re-laid, no net changes."""
    host = load("starters", "big-muff-pi-v3")
    xs = sorted(p.get("pos", [0, 0])[0] for p in host["parts"])
    mid = xs[len(xs) // 2]
    moved = run(
        js,
        "const b = await m('editor/blocks.js'); const e = await m('editor/edit.js');"
        " const items = b.itemsInBox(arg.c, [-1e4, -1e4, arg.mid, 1e4]);"
        " return {items, out: e.moveItems(arg.c, items, 40, 200)};",
        {"c": host, "mid": mid},
    )
    assert moved["items"]["wires"] and moved["items"]["labels"]
    before, after = connect(parse_circuit(host)), connect(parse_circuit(moved["out"]))
    pins = sorted(before.by_pin)
    assert same_net_pairs(after, pins) == same_net_pairs(before, pins)


def test_saving_the_whole_sheet_keeps_everything(js: Page) -> None:
    """A box over the whole sheet, taken out as a block, holds every part, wire and label
    (supply and ground labels too), the same as Ctrl+A."""
    for kind, names in (("blocks", BLOCKS), ("starters", STARTERS)):
        for name in names:
            r = run(
                js,
                """
                const view = await (await fetch(`/api/${arg.kind}/${arg.name}`)).json();
                const b = await m('editor/blocks.js');
                const c = view.circuit;
                return { c, boxed: b.extract(c, view, b.itemsInBox(c, [-1e5, -1e5, 1e5, 1e5])),
                         all: b.extract(c, view, b.allItems(c)) };
                """,
                {"kind": kind, "name": name},
            )
            assert shifted(r["boxed"], 0, 0) == shifted(r["c"], 0, 0), name
            assert shifted(r["all"], 0, 0) == shifted(r["c"], 0, 0), name


def test_block_sections_filter_and_sort(js: Page) -> None:
    entries = [
        {"name": n, "layer": layer}
        for n, layer in [
            ("b2", "core"),
            ("Zed", "user"),
            ("a", "core"),
            ("B10", "core"),
            ("alpha", "user"),
        ]
    ]
    r = run(
        js,
        "const b = await m('editor/blocks.js');"
        " const names = (s) => s.map((x) => [x.title, x.rows.map((e) => e.name)]);"
        " const shows = [{user: true, core: true}, {user: false, core: true}, {user: true, core: false}, {user: false, core: false}];"
        " return shows.flatMap((show) => ['az', 'za'].map((o) => names(b.blockSections(arg, show, o))));",
        entries,
    )
    mine, core = ["My blocks", ["alpha", "Zed"]], ["Core blocks", ["a", "b2", "B10"]]
    back = lambda s: [s[0], s[1][::-1]]  # noqa: E731
    both = [[mine, core], [back(mine), back(core)]]
    assert r == [*both, [core], [back(core)], [mine], [back(mine)], *both]  # both off: both show


def test_list_files_current_only_and_versions_newest_first(js: Page) -> None:
    """Open and Blocks list: by name, each name's versions newest major first (whatever
    the sort), only current ones with `currentOnly` (D-076)."""
    entries = [
        {"name": "fuzz", "version": "v1.13", "current": False},
        {"name": "Amp", "version": "v1.0", "current": True},
        {"name": "Fuzz", "version": "v10.0", "current": True},
        {"name": "fuzz", "version": "v2.4", "current": False},
    ]
    r = run(
        js,
        "const f = await m('editor/files.js');"
        " const tags = (l) => l.map((e) => `${e.name} ${e.version}`);"
        " return [tags(f.listFiles([...arg], 'az', false)), tags(f.listFiles([...arg], 'za', false)),"
        " tags(f.listFiles([...arg], 'az', true))];",
        entries,
    )
    assert r == [
        ["Amp v1.0", "Fuzz v10.0", "fuzz v2.4", "fuzz v1.13"],
        ["Fuzz v10.0", "fuzz v2.4", "fuzz v1.13", "Amp v1.0"],
        ["Amp v1.0", "Fuzz v10.0"],
    ]


def test_open_sections_recent_then_all(js: Page) -> None:
    """Open's sections: Recent (the last three saved, newest first, never a file that
    can't be opened, current versions only when asked) over All circuits by name; a
    search gives one untitled section; nothing saved gives no Recent (D-287)."""
    entries = [
        {"name": "Amp", "version": "v1.0", "current": True, "saved": "2026-11-01T10:00:00.000+00:00"},
        {"name": "Fuzz", "version": "v2.0", "current": True, "saved": "2026-11-03T10:00:00.250+00:00"},
        {"name": "Fuzz", "version": "v1.4", "current": False, "saved": "2026-11-05T10:00:00.000+00:00"},
        {"name": "Boost", "version": "v1.0", "current": True, "saved": "2026-11-03T10:00:00.750+00:00"},
        {"name": "broken", "version": "", "current": True, "saved": "2026-11-09T10:00:00.000+00:00", "problem": "bad file"},
        {"name": "Drive", "version": "v1.0", "current": True, "saved": "2026-11-02T10:00:00.000+00:00"},
    ]  # fmt: skip
    r = run(
        js,
        "const f = await m('editor/files.js');"
        " const show = (s) => s.map((x) => [x.key, x.title, x.rows.map((e) => `${e.name} ${e.version}`.trim())]);"
        " return [show(f.openSections(arg, 'az', true, false)), show(f.openSections(arg, 'za', false, false)),"
        " show(f.openSections(arg, 'az', true, true)), show(f.openSections([], 'az', true, false)), f.RECENT_MAX];",
        entries,
    )
    assert r == [
        [
            ["recent", "Recent", ["Boost v1.0", "Fuzz v2.0", "Drive v1.0"]],
            ["all", "All circuits", ["Amp v1.0", "Boost v1.0", "broken", "Drive v1.0", "Fuzz v2.0"]],
        ],
        [
            ["recent", "Recent", ["Fuzz v1.4", "Boost v1.0", "Fuzz v2.0"]],
            ["all", "All circuits", ["Fuzz v2.0", "Fuzz v1.4", "Drive v1.0", "broken", "Boost v1.0", "Amp v1.0"]],
        ],
        [["all", "", ["Amp v1.0", "Boost v1.0", "broken", "Drive v1.0", "Fuzz v2.0"]]],
        [["all", "All circuits", []]],
        3,
    ]  # fmt: skip


def test_toggle_and_add_items(js: Page) -> None:
    """Ctrl+click toggles one thing; Ctrl+Shift+drag adds a box (D-092)."""
    r = run(
        js,
        """
        const b = await m('editor/blocks.js');
        const sel = { parts: ['R1', 'C1'], wires: [2], labels: [], texts: [] };
        return {
          out: b.toggleItems(sel, { parts: ['C1'] }), in: b.toggleItems(sel, { wires: [5] }),
          text: b.toggleItems(sel, { texts: [0] }), back: b.toggleItems(b.toggleItems(sel, { labels: [1] }), { labels: [1] }),
          added: b.addItems(sel, { parts: ['R1', 'Q1'], wires: [2, 3] }),
        };
        """,
    )
    assert r["out"] == {"parts": ["R1"], "wires": [2], "labels": [], "texts": []}
    assert r["in"]["wires"] == [2, 5] and r["in"]["parts"] == ["R1", "C1"]
    assert r["text"]["texts"] == [0]
    assert r["back"] == {"parts": ["R1", "C1"], "wires": [2], "labels": [], "texts": []}
    assert r["added"] == {"parts": ["R1", "C1", "Q1"], "wires": [2, 3], "labels": [], "texts": []}


def test_a_circuits_guitar_and_amp_stay_out_of_blocks_and_deletes(js: Page) -> None:
    """D-146: Delete keeps a circuit's guitar input and amp (not a block's); Save as block
    leaves them out with the wires that end on their pins, keeping the rest."""
    sheet = {
        "schema": 15, "id": "s", "name": "S",
        "parts": [
            {"ref": "IN", "type": "guitar", "pos": [-100, 0]},
            {"ref": "R1", "type": "resistor", "value": "10k", "pos": [0, 0]},
            {"ref": "OUT", "type": "amp", "pos": [100, 0]},
        ],
        "wires": [{"from": [-90, 0], "to": [-20, 0]}, {"from": [20, 0], "to": [40, 0]}],
        "labels": [],
    }  # fmt: skip
    r = run(
        js,
        """
        const b = await m('editor/blocks.js');
        const { pinPositions } = await m('schematic/symbols.js');
        const sheet = arg;
        // the first wire from IN's pin to R1
        const inPin = Object.values(pinPositions(sheet.parts[0]))[0];
        sheet.wires[0].from = inPin;
        return {
          fixed: [...b.fixedRefs(sheet)].sort(),
          inBlock: [...b.fixedRefs({ ...sheet, template: true })],
          items: b.withoutEnds(sheet, { parts: ['IN', 'R1', 'OUT'], wires: [0, 1], labels: [] }),
        };
        """,
        sheet,
    )
    assert r["fixed"] == ["IN", "OUT"]
    assert r["inBlock"] == []  # a block may lose them
    assert r["items"] == {"parts": ["R1"], "wires": [1], "labels": []}


def test_a_paste_dropped_on_a_point_joins_it(js: Page) -> None:
    """The user's bug (2026-11-02): a 1M and its VREF label, copied and dropped with the
    resistor's pin right on a capacitor's pin, jumped away instead of joining it. Landed
    on a point with nothing else under it, it stays and connects (D-164); dropped onto a
    part's body it still moves aside. Its labels keep their turn and role."""
    r = run(
        js,
        """
        const b = await m('editor/blocks.js');
        const host = { parts: [{ ref: 'C8', type: 'capacitor', pos: [0, 60], rot: 90, value: '22n' }],
                       wires: [{ from: [0, 40], to: [40, 40] }], labels: [] };
        const block = { parts: [{ ref: 'R10', type: 'resistor', pos: [0, 20], rot: 90, value: '1M' }],
                        wires: [], labels: [{ net: 'VREF', pos: [0, 0] }, { net: 'GND', pos: [40, 0], rot: 90, role: 'battery' }] };
        // the anchor is the middle of its drawing, (20, 10): R10's pin 2 (0, 40) lands on C8's pin 1
        const joined = b.pasteBlock(host, block, { at: [20, 10] }).circuit;
        const onBody = b.pasteBlock(host, block, { at: [20, 50] }).circuit;
        return { joined: joined.parts.find((p) => p.ref === 'R1').pos, labels: joined.labels,
                 onBody: onBody.parts.find((p) => p.ref === 'R1').pos };
        """,
    )
    assert r["joined"] == [0, 20]
    assert r["onBody"] != [0, 60]
    assert {"net": "GND", "pos": [40, 0], "rot": 90, "role": "battery"} in r["labels"]


def test_a_drop_never_joins_two_named_nets(js: Page) -> None:
    """The 9c bug (2026-11-03): a block's V18 wire end dropped right on the sheet's GND
    label joined them, and the circuit no longer loaded. A drop that would put two
    differently named labels on one net isn't a join (the user, 2026-11-03): the block
    moves to a clear spot. The same name, or a net with no name on one side, still joins."""
    r = run(
        js,
        """
        const b = await m('editor/blocks.js');
        // anchor (20, 0): dropped at (80, 0) the wire runs (60, 0)-(100, 0)
        const block = (net) => ({ parts: [], wires: [{ from: [0, 0], to: [40, 0] }], labels: [{ net, pos: [0, 0] }] });
        const onLabel = (net) => ({ parts: [], wires: [], labels: [{ net, pos: [100, 0] }] });
        // the sheet's label reached along a wire: IN at (300, 0), its wire ends at (100, 0)
        const alongWire = { parts: [], wires: [{ from: [100, 0], to: [300, 0] }], labels: [{ net: 'IN', pos: [300, 0] }] };
        const bare = { parts: [], wires: [{ from: [100, 0], to: [300, 0] }], labels: [] };
        const at = (host, blk) => b.clearSpot(host, blk, [80, 0]);
        return {
          gndOnV18: at(onLabel('GND'), block('V18')),
          sameName: at(onLabel('GND'), block('GND')),
          inOnOut: at(alongWire, block('OUT')),
          inOnIn: at(alongWire, block('IN')),
          noName: at(bare, block('OUT')),
        };
        """,
    )
    assert r["gndOnV18"] != [80, 0]
    assert r["inOnOut"] != [80, 0]
    assert r["sameName"] == [80, 0]
    assert r["inOnIn"] == [80, 0]
    assert r["noName"] == [80, 0]


def test_the_charge_pump_on_the_tone_bender_keeps_its_own_net(js: Page) -> None:
    """Hypothesis's case: the doubler dropped at (15, 285) put a V18 wire end on the
    Tone Bender MkII's GND label at (40, 260)."""
    host = load("starters", "tone-bender-mk2")
    block = load("blocks", "charge-pump-doubler-chip-v1")
    r = paste(js, host, block, at=[15, 285])
    pasted = parse_circuit(r["circuit"])  # loads: GND and V18 stay apart
    check_paste(parse_circuit(host), parse_circuit(block), pasted, r["refs"])


def test_a_drop_never_joins_two_of_the_blocks_own_nets(js: Page) -> None:
    """Hypothesis's case (9d3): a resistor dropped with both pins on one of the sheet's
    wires was taken as a join, shorting it. A drop may join the sheet, but never so that
    two nets of the block become one: then it moves to a clear spot. One pin on the wire
    still joins."""
    r = run(
        js,
        """
        const b = await m('editor/blocks.js');
        const host = { parts: [], wires: [{ from: [-200, 0], to: [200, 0] }], labels: [] };
        const across = { parts: [{ ref: 'R1', type: 'resistor', pos: [0, 0], value: '10k' }], wires: [], labels: [] };
        // the same resistor standing up: only its top pin (0, 0) lands on the wire
        const upright = { parts: [{ ref: 'R1', type: 'resistor', pos: [0, 20], rot: 90, value: '10k' }], wires: [], labels: [] };
        return { across: b.clearSpot(host, across, [0, 0]), upright: b.clearSpot(host, upright, [0, 20]) };
        """,
    )
    assert r["across"] != [0, 0]
    assert r["upright"] == [0, 20]


def test_the_op_amp_doubler_pasted_three_times_on_the_klon_keeps_its_nets(js: Page) -> None:
    """Hypothesis's case (9d3): the third paste at (800, 275) put R3's two pins on one wire."""
    circuit = load("starters", "klon-centaur")
    block = load("blocks", "charge-pump-doubler-opamp-v1")
    for i in range(3):
        before = parse_circuit(circuit)
        r = paste(js, circuit, block, at=[400 * i, 275])
        check_paste(before, parse_circuit(block), parse_circuit(r["circuit"]), r["refs"])
        circuit = r["circuit"]
