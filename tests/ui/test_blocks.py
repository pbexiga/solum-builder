# ruff: noqa: E501  (JavaScript inside strings)
"""Blocks in a real browser (Phase 4): insert a core block, splice one into a wire, box
select + copy/paste, save a selection as a block with ports, the Blocks dialog (core
blocks edited as unsaved copies), the save prompt, version tags and final versions, and
Phase 4's acceptance: the Big Muff rebuilt from blocks simulates the same as the starter."""

from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import click_part, part_pos, to_screen, wait_for_update
from tests.ui.conftest import run as run_js
from tests.ui.test_editor import (
    api,
    click_at,
    drag,
    drawn_refs,
    menu,
    new_circuit,
    place,
    press,
    save_as,
    views,
    wait_for_view,
    wires,
)


def saved(page: Page, cid: str) -> dict[str, Any]:
    data: dict[str, Any] = page.evaluate(
        f"fetch('/api/circuits/{cid}').then((r) => r.json()).then((v) => v.circuit)"
    )
    return data


def blank(page: Page, base_url: str) -> None:
    page.goto(base_url)
    wait_for_update(page, 0)


def click_low(page: Page) -> None:
    """Click near the bottom middle of the canvas (on screen, whatever the zoom)."""
    box = page.locator("#schematic").bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.85)


def insert(page: Page, name: str) -> None:
    """Blocks → Insert block…, pick `name`, click the sheet low down."""
    menu(page, "blocks-menu", "menu-insert-block")
    page.locator("button.insert", has_text=name).click()
    page.wait_for_selector("svg#schematic.placing")
    before = views(page)
    click_low(page)
    wait_for_view(page, before)


@pytest.mark.usefixtures("half_drawn")  # floats until wired: refused runs
def test_insert_a_core_block(page: Page, base_url: str) -> None:
    blank(page, base_url)
    insert(page, "Fender TMB")
    assert {"VR1", "VR2", "VR3", "C1", "C2", "C3", "R1"} <= set(drawn_refs(page))
    assert "SW1" not in drawn_refs(page)  # a plain TMB, no Thick switch (D-073)
    # the pasted block is selected, so it can be dragged as one
    assert page.locator("g.part.selected").count() == 7
    cid = save_as(page, "Tone test")
    c = saved(page, cid)
    assert "provenance" not in c  # a plain copy of the block's parts (D-075)
    labels = {lb["net"] for lb in c["labels"]}
    assert {"in", "out", "GND"} <= labels  # the ports arrive as labels to wire up


def test_splice_a_block_into_a_wire(page: Page, base_url: str) -> None:
    blank(page, base_url)
    before = views(page)
    drag(page, (-280, 0), (280, 0))  # guitar out → amp in
    wait_for_view(page, before)
    menu(page, "blocks-menu", "menu-insert-block")
    page.locator("button.insert", has_text="Clipper \u00b7 diodes to ground").click()
    page.wait_for_selector("svg#schematic.placing")
    before = views(page)
    click_at(page, 0, 0)  # on the wire
    wait_for_view(page, before)
    cid = save_as(page, "Splice test")
    c = saved(page, cid)
    assert {p["ref"] for p in c["parts"]} == {"IN", "OUT", "R1", "D1", "D2"}
    assert {lb["net"] for lb in c["labels"]} == {"GND"}
    nets = page.evaluate(f"fetch('/api/circuits/{cid}').then((r) => r.json()).then((v) => v.parts)")
    net = {(p["ref"], pin["name"]): pin["net"] for p in nets for pin in p["pins"]}
    assert net[("IN", "out")] == net[("R1", "1")]
    assert net[("OUT", "in")] == net[("D1", "A")] == net[("R1", "2")]


def test_box_select_copy_and_paste(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}#ts808")
    wait_for_update(page, 0)
    count = len(drawn_refs(page))
    # Shift+drag a box around the input stage
    a, b = to_screen(page, 40, -60), to_screen(page, 230, 90)
    page.keyboard.down("Shift")
    page.mouse.move(*a)
    page.mouse.down()
    page.mouse.move(*b, steps=6)
    page.mouse.up()
    page.keyboard.up("Shift")
    picked = page.locator("g.part.selected").count()
    assert picked >= 2
    press(page, "Control+c")
    press(page, "Control+v")
    page.wait_for_selector("svg#schematic.placing")
    before = views(page)
    click_low(page)
    wait_for_view(page, before)
    assert len(drawn_refs(page)) == count + picked
    # the pasted wires are selected with the parts, so a drag right away takes them along
    # (the user, D-095: the parts went and the wires stayed)
    ends = """() => [...document.querySelectorAll('line.wire.selected')]
        .map((l) => ['x1', 'y1', 'x2', 'y2'].map((a) => Number(l.getAttribute(a))).join()).sort()"""
    wires = page.evaluate(ends)
    assert len(wires) >= 2
    ref = page.locator("g.part.selected").first.get_attribute("data-ref") or ""
    x, y = part_pos(page, ref)
    before = views(page)
    drag(page, (x, y), (x, y + 40))
    wait_for_view(page, before)
    assert part_pos(page, ref) == (x, y + 40)
    moved = [
        ",".join(str(int(v) + (40 if i % 2 else 0)) for i, v in enumerate(w.split(",")))
        for w in wires
    ]
    assert page.evaluate(ends) == sorted(moved)
    press(page, "Delete")  # the pasted copy is selected: Delete takes it all out again
    page.wait_for_function(f"document.querySelectorAll('g.part').length === {count}")
    press(page, "Control+z")
    page.wait_for_function(f"document.querySelectorAll('g.part').length === {count + picked}")


def test_a_press_on_any_selected_item_moves_the_selection(page: Page, base_url: str) -> None:
    """D-113: with several items selected, dragging from one of them (a label, a wire end's
    ball, not only a part or a wire) moves them all, instead of starting a wire or moving
    that one end."""
    for grab in (
        (900, -280),
        (860, -280),
    ):  # the VREF label; the ball where C16's wire meets the bus
        page.goto(f"{base_url}#ts808")
        page.reload()
        wait_for_update(page, 0)
        a, b = to_screen(page, 820, -320), to_screen(page, 940, -200)
        page.keyboard.down("Shift")
        page.mouse.move(*a)
        page.mouse.down()
        page.mouse.move(*b, steps=6)
        page.mouse.up()
        page.keyboard.up("Shift")
        expect(page.locator('g.part.selected[data-ref="C16"]')).to_have_count(1)
        expect(page.locator('.net-label.selected[data-net="VREF"]')).to_have_count(1)
        before = views(page)
        drag(page, grab, (grab[0], grab[1] + 40))
        wait_for_view(page, before)
        assert part_pos(page, "C16") == (860, -200), grab
        expect(page.locator('.net-label[data-net="VREF"][data-at="900,-240"]')).to_have_count(1)
        assert page.locator(".overlay .wire-path").count() == 0


def test_ctrl_click_adds_and_removes_one_item(
    page: Page, base_url: str, half_drawn: list[str]
) -> None:
    """Typical click selection (D-092): after a Shift+drag box, Ctrl+click takes one part
    out or puts one in (a wire too); Ctrl+Shift+drag adds a box; from scratch, a click
    then Ctrl+clicks build a selection."""
    page.goto(f"{base_url}#ts808")
    wait_for_update(page, 0)
    page.keyboard.down("Shift")
    drag(page, (40, -60), (230, 90))
    page.keyboard.up("Shift")
    selected = page.locator("g.part.selected")
    picked = sorted(selected.evaluate_all("(gs) => gs.map((g) => g.dataset.ref)"))
    assert len(picked) >= 2
    hit = lambda ref: page.locator(f'g.part[data-ref="{ref}"] .part-hit')  # noqa: E731
    hit(picked[0]).click(modifiers=["ControlOrMeta"])
    expect(selected).to_have_count(len(picked) - 1)
    expect(page.locator(f'g.part.selected[data-ref="{picked[0]}"]')).to_have_count(0)
    hit(picked[0]).click(modifiers=["ControlOrMeta"])
    expect(selected).to_have_count(len(picked))
    outside = "OUT"  # the amp: alone where it sits, so a small box takes only it
    assert outside in drawn_refs(page) and outside not in picked
    hit(outside).click(modifiers=["ControlOrMeta"])
    expect(selected).to_have_count(len(picked) + 1)
    # a wire, Ctrl+clicked at its middle, joins the selection too
    chosen = page.locator("line.wire.selected")
    had = chosen.count()  # the box took in the wires inside it
    x1, y1, x2, y2 = next(w for w in wires(page) if not (40 <= w[0] <= 230 and -60 <= w[1] <= 90))
    page.keyboard.down("ControlOrMeta")
    click_at(page, (x1 + x2) / 2, (y1 + y2) / 2)
    page.keyboard.up("ControlOrMeta")
    expect(chosen).to_have_count(had + 1)
    expect(selected).to_have_count(len(picked) + 1)  # the parts are still selected
    # Ctrl+Shift+drag adds a second box instead of replacing the selection
    page.keyboard.down("Shift")
    drag(page, (40, -60), (230, 90))
    page.keyboard.up("Shift")
    expect(selected).to_have_count(len(picked))  # a plain box replaces it
    page.keyboard.down("ControlOrMeta")
    page.keyboard.down("Shift")
    ox, oy = part_pos(page, outside)
    drag(page, (ox - 33, oy - 37), (ox + 33, oy + 37))  # a small box around it
    page.keyboard.up("Shift")
    page.keyboard.up("ControlOrMeta")
    expect(page.locator(f'g.part.selected[data-ref="{outside}"]')).to_have_count(1)
    for ref in picked:
        expect(page.locator(f'g.part.selected[data-ref="{ref}"]')).to_have_count(1)
    # from scratch: click one part, Ctrl+click another
    hit(picked[0]).click()
    hit(outside).click(modifiers=["ControlOrMeta"])
    expect(selected).to_have_count(2)
    count = len(drawn_refs(page))
    press(page, "Delete")  # the amp stays (D-146): only the other part goes
    page.wait_for_function(f"document.querySelectorAll('g.part').length === {count - 1}")
    assert outside in drawn_refs(page) and picked[0] not in drawn_refs(page)
    expect(page.locator("#hint")).to_contain_text("every circuit has a guitar input and an amp")


def test_save_selection_as_block_with_ports(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}#big-muff-pi-v3")
    wait_for_update(page, 0)
    page.keyboard.down("Shift")
    drag(page, (455, -150), (770, 160))
    page.keyboard.up("Shift")
    assert page.locator("g.part.selected").count() == 12
    menu(page, "blocks-menu", "menu-save-block")
    page.locator("#field-name").fill("Muff stage")
    click_at(page, 450, 80)  # C5's input pin: in
    click_at(page, 750, 60)  # the q3c label: out
    expect(page.locator("#port-list input")).to_have_count(2)
    assert page.locator("#port-list input").nth(0).input_value() == "in"
    assert page.locator("#port-list input").nth(1).input_value() == "out"
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_have_count(0)
    expect(page.locator("#hint")).to_contain_text("Saved Muff stage in My blocks (v1.0)")
    block = page.evaluate("fetch('/api/blocks/muff-stage').then((r) => r.json())")
    assert block["file"]["layer"] == "user"
    assert block["circuit"]["ports"] == {"in": "in", "out": "q3c"}
    # the same name again: asked first, then replaced (not a second "muff-stage-2")
    menu(page, "blocks-menu", "menu-save-block")
    page.locator("#field-name").fill("muff stage")
    page.locator("#field-description").fill("again")
    page.locator("form.popup button.primary").click()
    expect(page.locator(".ask-title")).to_contain_text(
        "already have a block called \u201cMuff stage\u201d"
    )
    page.locator("[data-answer='replace']").click()
    expect(page.locator("#hint")).to_contain_text("Replaced Muff stage in My blocks (v1.1)")
    again = page.evaluate("fetch('/api/blocks/muff-stage').then((r) => r.json())")["circuit"]
    assert again["description"] == "again" and again["name"] == "Muff stage"
    mine = [
        b["id"]
        for b in page.evaluate("fetch('/api/blocks?q=muff').then((r) => r.json())")
        if b["layer"] == "user"
    ]
    assert mine == ["muff-stage-v1"]


def answer(page: Page, value: str) -> None:
    """Answer the question on screen (the save prompt and the like)."""
    page.locator(f".ask [data-answer='{value}']").click()
    expect(page.locator(".ask")).to_have_count(0)


def test_edit_a_core_block_opens_an_unsaved_copy(page: Page, base_url: str) -> None:
    """Edit on a core block: a copy, never saved until you save it (a stray click leaves
    no file); saving asks for a name and puts it in My blocks; the core block stays."""
    blank(page, base_url)
    menu(page, "blocks-menu", "menu-insert-block")
    page.locator("[data-edit-block='jfet-cs-stage-v1'][data-layer='core']").click()
    page.wait_for_function("location.hash === '#copy/core:jfet-cs-stage-v1'")
    expect(page.locator("#circuit-name")).to_have_text("Gain stage \u00b7 JFET (Fetzer Valve)")
    expect(page.locator("#badges")).to_have_text("Block")
    expect(page.locator("#dirty")).to_have_text("Never saved")
    # not changed: leaving asks nothing and leaves no file behind
    menu(page, "file-menu", "menu-new")
    page.wait_for_function("location.hash === '#new'")
    mine = [
        b
        for b in page.evaluate("fetch('/api/blocks').then((r) => r.json())")
        if b["layer"] == "user"
    ]
    assert not [b for b in mine if b["name"].startswith("Gain stage \u00b7 JFET (Fetzer Valve)")]
    # again, changed and saved: Save asks for a name (the core block's name to start with)
    page.go_back()
    page.wait_for_function("location.hash === '#copy/core:jfet-cs-stage-v1'")
    expect(page.locator("#circuit-name")).to_have_text("Gain stage \u00b7 JFET (Fetzer Valve)")
    page.locator("g.part[data-ref='R2']").dblclick()
    page.locator("#field-value").fill("8k2")
    before = views(page)
    page.locator("form.popup button.primary").click()
    wait_for_view(page, before)
    press(page, "Control+s")
    expect(page.locator("form.popup .popup-title")).to_contain_text("Save as a new block")
    assert page.locator("#field-name").input_value() == "Gain stage \u00b7 JFET (Fetzer Valve)"
    page.locator("form.popup button.primary").click()
    page.wait_for_function("location.hash === '#block/gain-stage-jfet-fetzer-valve'")
    expect(page.locator("#badges")).to_have_text("Blockv1.0")
    expect(page.locator("#dirty")).to_be_hidden()
    core = page.evaluate("fetch('/api/blocks/jfet-cs-stage?layer=core').then((r) => r.json())")
    assert core["file"]["readonly"] is True
    assert [p["value"] for p in core["circuit"]["parts"] if p["ref"] == "R2"] == ["1k5"]


def test_the_save_prompt(page: Page, base_url: str) -> None:
    """Unsaved changes, then anything that replaces them: Save / Don't Save / Cancel. Back
    and Forward ask too, and Cancel puts the address back."""
    cid = new_circuit(page, base_url, "Prompt test")
    place(page, "r", 0, 0)
    expect(page.locator("#dirty")).to_have_text("Not saved")
    # Cancel: nothing happens
    menu(page, "file-menu", "menu-new")
    expect(page.locator(".ask-title")).to_have_text(
        "Do you want to save the changes to \u201cPrompt test\u201d?"
    )
    expect(page.locator(".ask-text")).to_have_text(
        "Your changes will be lost if you don't save them."
    )
    expect(page.locator(".ask button")).to_have_text(["Don't Save", "Cancel", "Save"])
    assert page.evaluate("document.activeElement.dataset.answer") == "save"
    answer(page, "cancel")
    assert page.evaluate("location.hash") == f"#circuit/{cid}"
    expect(page.locator("#dirty")).to_be_visible()
    # Back: asked too; Cancel keeps us here and the history as it was
    page.go_back()
    expect(page.locator(".ask")).to_be_visible()
    answer(page, "cancel")
    page.wait_for_function(f"location.hash === '#circuit/{cid}'")
    assert "R1" in drawn_refs(page)
    # Save: saved, then on to the new sheet
    menu(page, "file-menu", "menu-new")
    answer(page, "save")
    page.wait_for_function("location.hash === '#new'")
    assert [p["ref"] for p in saved(page, cid)["parts"]] == ["R1"]
    # Don't Save: the change is gone
    page.goto(f"{base_url}#circuit/{cid}")
    page.wait_for_function("document.querySelector('#circuit-name').textContent === 'Prompt test'")
    place(page, "c", 0, 80)
    menu(page, "file-menu", "menu-new")
    answer(page, "discard")
    page.wait_for_function("location.hash === '#new'")
    assert [p["ref"] for p in saved(page, cid)["parts"]] == ["R1"]


def test_versions_rename_and_final(page: Page, base_url: str) -> None:
    """The version tag counts saves; Rename renames the file; New major version keeps the
    old one as final in its own file (same name) and the short link follows the newest;
    a final version can be unlocked for a fix and counts on (D-075, D-076)."""
    cid = new_circuit(page, base_url, "Version test")
    expect(page.locator("#badges")).to_have_text("v1.0")
    place(page, "r", 0, 0)
    press(page, "Control+s")
    expect(page.locator("#badges")).to_have_text("v1.1")
    # rename with the pencil: the file is renamed there and then (D-287)
    page.locator("#rename-button").click()
    page.locator("#name-box").fill("Fuzz build")
    press(page, "Enter")
    page.wait_for_function("location.hash === '#circuit/fuzz-build'")
    expect(page.locator("#dirty")).to_be_hidden()
    expect(page.locator("#badges")).to_have_text("v1.2")
    ids = [c["id"] for c in api(page, base_url, "GET", "api/circuits")]
    assert "fuzz-build-v1" in ids and "version-test-v1" not in ids and cid == "version-test"
    menu(page, "file-menu", "menu-properties")
    expect(page.locator("[data-info='file']")).to_have_text("<data>/circuits/fuzz-build-v1.json")
    expect(page.locator("[data-info='version']")).to_have_text("v1.2")
    page.locator("form.popup [data-action='cancel']").click()
    # a new major version: v1 kept as final, this one at v2.0, same name and link
    menu(page, "file-menu", "menu-new-major")
    expect(page.locator(".ask-title")).to_have_text("Start version 2 of \u201cFuzz build\u201d?")
    answer(page, "go")
    expect(page.locator("#badges")).to_have_text("v2.0")
    assert page.evaluate("location.hash") == "#circuit/fuzz-build"
    expect(page.locator("#circuit-name")).to_have_text("Fuzz build")
    listed = [
        (c["id"], c["name"], c["version"], c["final"], c["current"])
        for c in api(page, base_url, "GET", "api/circuits?q=fuzz%20build")
    ]
    assert listed == [
        ("fuzz-build-v2", "Fuzz build", "v2.0", False, True),
        ("fuzz-build-v1", "Fuzz build", "v1.2", True, False),
    ]
    # Open lists current versions only, until that's switched off (and remembered)
    menu(page, "file-menu", "menu-open")
    rows = page.locator(".open-list [data-circuit]", has_text="Fuzz build")
    expect(rows).to_have_count(1)
    expect(rows).to_have_text(["Fuzz buildv2.0"])
    page.locator("[data-list-current]").click()
    expect(rows).to_have_text(["Fuzz buildv2.0", "Fuzz buildv1.2 \u00b7 final"])
    # the final one is read-only; unlock it for a fix, and it counts on in v1
    page.locator("[data-circuit='fuzz-build-v1']").click()
    page.wait_for_function("location.hash === '#circuit/fuzz-build-v1'")
    expect(page.locator("#badges")).to_have_text("v1.2final \u00b7 read-only")
    page.locator("#rename-button").click()
    expect(page.locator("#error")).to_contain_text("final version, so it's read-only")
    expect(page.locator("#name-box")).to_be_hidden()
    menu(page, "file-menu", "menu-properties")
    page.locator("#toggle-final").click()
    answer(page, "unlock")
    expect(page.locator("#badges")).to_have_text("v1.2")
    place(page, "c", 0, 80)
    press(page, "Control+s")
    expect(page.locator("#badges")).to_have_text("v1.3")


def test_pencil_rename(page: Page, base_url: str, browser_errors: list[str]) -> None:
    """The pencil after the name opens it for editing: Enter or the tick renames the file
    at once, Esc or a click elsewhere puts the old name back, a taken name is said under
    the box; unsaved changes stay unsaved and undo never brings the old name back (D-287)."""
    new_circuit(page, base_url, "Taken name")
    new_circuit(page, base_url, "Pencil test")
    expect(page.locator("#menu-rename")).to_have_count(0)
    page.locator("#circuit-name").click()  # the name itself no longer renames
    expect(page.locator("#name-box")).to_be_hidden()
    place(page, "r", 0, 0)
    place(page, "c", 0, 80)
    expect(page.locator("#dirty")).to_have_text("Not saved")
    # Esc, then a click elsewhere: the old name stays
    page.locator("#rename-button").click()
    expect(page.locator("#name-box")).to_be_focused()
    expect(page.locator("#name-box")).to_have_value("Pencil test")
    page.locator("#name-box").fill("Dropped")
    press(page, "Escape")
    expect(page.locator("#name-box")).to_be_hidden()
    page.locator("#rename-button").click()
    page.locator("#name-box").fill("Dropped")
    page.locator("#run").focus()
    expect(page.locator("#name-box")).to_be_hidden()
    expect(page.locator("#circuit-name")).to_have_text("Pencil test")
    # a taken name and an empty one are said under the box, which stays open
    page.locator("#rename-button").click()
    page.locator("#name-box").fill("taken NAME")
    press(page, "Enter")
    expect(page.locator("#name-error")).to_contain_text("already have a circuit called Taken name")
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]  # the refusal
    page.locator("#name-box").fill("  ")
    page.locator("#rename-button").click()  # the tick
    expect(page.locator("#name-error")).to_have_text("Give the circuit a name.")
    # the tick renames: the file, the link and the version follow; the edits stay unsaved
    page.locator("#name-box").fill("Pencil done")
    page.locator("#rename-button").click()
    page.wait_for_function("location.hash === '#circuit/pencil-done'")
    expect(page.locator("#circuit-name")).to_have_text("Pencil done")
    expect(page.locator("#name-box")).to_be_hidden()
    expect(page.locator("#badges")).to_have_text("v1.1")
    expect(page.locator("#dirty")).to_have_text("Not saved")
    on_disk = api(page, base_url, "GET", "api/circuits/pencil-done")["circuit"]
    assert (on_disk["name"], on_disk["parts"]) == ("Pencil done", [])
    ids = [c["id"] for c in api(page, base_url, "GET", "api/circuits")]
    assert "pencil-done-v1" in ids and "pencil-test-v1" not in ids
    # undo an edit from before the rename: the new name stays, and Save keeps the file
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    expect(page.locator("#circuit-name")).to_have_text("Pencil done")
    press(page, "Control+s")
    expect(page.locator("#badges")).to_have_text("v1.2")
    saved = api(page, base_url, "GET", "api/circuits/pencil-done")["circuit"]
    assert (saved["name"], [p["ref"] for p in saved["parts"]]) == ("Pencil done", ["R1"])
    # a new sheet has no file: its name is an edit, saved with it
    menu(page, "file-menu", "menu-new")
    page.wait_for_function("location.hash === '#new'")
    page.locator("#rename-button").click()
    page.locator("#name-box").fill("Sketch")
    before = views(page)
    press(page, "Enter")
    wait_for_view(page, before)
    expect(page.locator("#circuit-name")).to_have_text("Sketch")
    expect(page.locator("#dirty")).to_have_text("Never saved")


def test_open_lists_recent_then_all(page: Page, base_url: str) -> None:
    """Open: Recent (the last three saved, newest first) over All circuits (by name);
    a search shows only its matches, with no sections (D-287)."""
    for name in ("Delta", "Alpha", "Charlie", "Bravo"):
        new_circuit(page, base_url, name)
    menu(page, "file-menu", "menu-open")
    # other tests' circuits are listed too
    mine = "['Alpha', 'Bravo', 'Charlie', 'Delta'].includes(n)"
    names = (
        "[...document.querySelectorAll('.open-list [{0}]')].map((b) => b.firstChild.textContent)"
        f".filter((n) => {mine}).join()"
    )
    page.wait_for_function(f"{names.format('data-recent')} === 'Bravo,Charlie,Alpha'")
    assert page.evaluate(names.format("data-circuit")) == "Alpha,Bravo,Charlie,Delta"
    expect(page.locator(".open-list .block-section")).to_have_text(["Recent", "All circuits"])
    page.locator("[data-list-order='za']").click()  # sorts All circuits; Recent stays
    assert page.evaluate(names.format("data-circuit")) == "Delta,Charlie,Bravo,Alpha"
    assert page.evaluate(names.format("data-recent")) == "Bravo,Charlie,Alpha"
    page.locator("[data-list-order='az']").click()
    page.locator("#field-q").fill("alph")
    page.wait_for_function(f"{names.format('data-circuit')} === 'Alpha'")
    expect(page.locator(".open-list .block-section")).to_have_count(0)
    expect(page.locator(".open-list [data-recent]")).to_have_count(0)
    page.locator("#field-q").fill("")
    page.wait_for_function(f"{names.format('data-recent')} === 'Bravo,Charlie,Alpha'")
    page.locator("[data-recent='charlie-v1']").click()
    page.wait_for_function("location.hash === '#circuit/charlie'")


def test_block_manager(page: Page, base_url: str) -> None:
    """Blocks dialog: Core and My blocks toggles (one always on), A-Z / Z-A (remembered),
    version tags, Edit and Delete on my blocks, Edit only on core ones."""
    blank(page, base_url)
    api(
        page,
        base_url,
        "POST",
        "api/blocks",
        {
            "circuit": api(page, base_url, "GET", "api/blocks/vref-divider")["circuit"],
            "name": "Manager test",
        },
    )
    api(page, base_url, "POST", "api/blocks/manager-test/major")
    menu(page, "blocks-menu", "menu-insert-block")
    sections = page.locator(".block-section")
    expect(sections).to_have_text(["My blocks", "Core blocks"])
    # current versions only to start with; switched off, older ones under the newest
    mine = page.locator(".block-row:has(button.insert[data-layer='user'])", has_text="Manager")
    expect(mine).to_have_count(1)
    expect(mine.locator(".tag")).to_have_text(["v2.0"])
    page.locator("[data-list-current]").click()
    expect(mine.locator(".tag")).to_have_text(["v2.0", "v1.0 \u00b7 final"])
    expect(mine.locator("button.insert")).to_have_text(["Manager test", "Manager test"])
    page.locator("[data-list-current]").click()
    core = page.locator("button.insert[data-layer='core']")
    names = core.all_inner_texts()

    # as the menu sorts them (the browser's collation): case ignored, numbers by value
    expected = page.evaluate(
        "(names) => [...names].sort((a, b) => a.localeCompare(b, undefined,"
        " { sensitivity: 'base', numeric: true }))",
        names,
    )
    assert names == expected and "Vref \u00b7 half-supply divider" in names
    page.locator("[data-block-order='za']").click()
    assert core.all_inner_texts() == names[::-1]
    page.locator("[data-block-show='user']").click()  # My blocks off
    expect(sections).to_have_text(["Core blocks"])
    page.locator("[data-block-show='core']").click()  # the last one on: stays on
    expect(sections).to_have_text(["Core blocks"])
    assert page.locator("[data-delete-block]").count() == 0  # core blocks can't be deleted
    expect(
        page.locator(".block-row", has_text="Vref \u00b7 half-supply divider").locator(".tag")
    ).to_have_text("v1.2")
    page.locator("[data-block-show='user']").click()
    page.locator("[data-block-show='core']").click()
    expect(sections).to_have_text(["My blocks"])
    # remembered next time
    press(page, "Escape")
    menu(page, "blocks-menu", "menu-insert-block")
    expect(sections).to_have_text(["My blocks"])
    page.locator("[data-block-show='core']").click()
    page.locator("[data-block-order='az']").click()
    # delete mine, after asking
    page.locator("[data-delete-block='manager-test-v2']").click()
    expect(page.locator(".ask-title")).to_have_text(
        "Delete your block \u201cManager test\u201d (v2.0)?"
    )
    answer(page, "delete")
    expect(page.locator("[data-delete-block='manager-test-v2']")).to_have_count(0)
    expect(mine.locator(".tag")).to_have_text(["v1.0 \u00b7 final"])  # v1 is current now


def test_drag_a_boxed_sheet_moves_everything(page: Page, base_url: str) -> None:
    """Bug: box over the whole 9 V filter, drag by R1: the V+ label and its wire stayed put."""
    page.goto(f"{base_url}#copy/core:input-filter-9v")
    wait_for_update(page, 0)
    page.keyboard.down("Shift")
    drag(page, (-60, -40), (200, 100))
    page.keyboard.up("Shift")
    assert page.locator("g.part.selected").count() == 4  # D1, R1, C1, C2
    before = views(page)
    drag(page, (40, 0), (100, 80))  # by R1
    wait_for_view(page, before)
    menu(page, "file-menu", "menu-save-as")
    page.locator("#field-name").fill("Moved filter")
    page.locator("form.popup button.primary").click()
    page.wait_for_function("location.hash === '#block/moved-filter'")
    moved = page.evaluate("fetch('/api/blocks/moved-filter').then((r) => r.json())")["circuit"]
    labels = sorted((lb["net"], tuple(lb["pos"])) for lb in moved["labels"])
    assert labels == [
        ("GND", (150, 140)),
        ("GND", (200, 140)),
        ("V+", (20, 80)),
        ("V+F", (220, 80)),
    ]
    ends = sorted(tuple(sorted([tuple(w["from"]), tuple(w["to"])])) for w in moved["wires"])
    assert ends == [
        ((60, 80), (80, 80)),
        ((120, 80), (220, 80)),
        ((150, 80), (150, 100)),
        ((200, 80), (200, 100)),
    ]


# ---- Phase 4 acceptance ----------------------------------------------------------

# Big Muff gain stage block refs → the starter's refs, per stage; refs left out are deleted
STAGES = {
    "Q4": {"C5": "C1", "R19": "R2", "R20": "R14", "R17": "R9", "C12": "C10", "R18": "R13",
           "Q3": "Q4", "R21": "R22"},  # the input booster: no clipping diodes
    "Q3": {r: r for r in ("C5", "R19", "R20", "R17", "C12", "R18", "Q3", "R21", "C6", "D3", "D4")},
    "Q2": {"C5": "C13", "R19": "R12", "R20": "R16", "R17": "R15", "C12": "C11", "R18": "R11",
           "Q3": "Q2", "R21": "R10", "C6": "C7", "D3": "D1", "D4": "D2"},
    "Q1": {"C5": "C3", "R20": "R3", "R18": "R6", "Q3": "Q1", "R21": "R4"},  # output stage
}  # fmt: skip
TONE = {**{r: r for r in ("R8", "C8", "C9", "R5")}, "VR1": "VR2"}  # the block's VR1 is the Muff's

REBUILD = """
const b = await m('editor/blocks.js');
const e = await m('editor/edit.js');
const get = async (url) => (await fetch(url)).json();
const starter = await get('/api/starters/big-muff-pi-v3');
const blocks = { stage: await get('/api/blocks/big-muff-stage'), tone: await get('/api/blocks/big-muff-tone') };
const S = starter.circuit;
const pinAt = {};  // "REF.PIN" → where that pin was in the starter, and its net
const netAt = {};
for (const p of starter.parts) for (const pin of p.pins) [pinAt[`${p.ref}.${pin.name}`], netAt[`${p.ref}.${pin.name}`]] = [pin.pos, pin.net];
const jobs = [...Object.entries(arg.stages).map(([q, map]) => ({ q, map, block: blocks.stage })), { q: 'tone', map: arg.tone, block: blocks.tone }];
// take the stages and the tone stack out of the starter: what's left is the glue
// (input, Sustain, Volume, output) with the wires that went to the stages
let c = e.deleteItems(S, { parts: jobs.flatMap((j) => Object.values(j.map)).concat(['C6', 'D3', 'D4']) });
let n = 0;
const pending = [];
for (const job of jobs) {
  const { block } = job;
  const pasted = b.pasteBlock(c, block.circuit, { at: [0, 1000 + 400 * n++] });
  c = pasted.circuit;
  // wire up each port: its label is renamed to a net at the starter's pin it stood for
  for (const [port, net] of Object.entries(block.circuit.ports)) {
    const pin = block.parts.flatMap((p) => p.pins.map((x) => ({ ...x, ref: p.ref }))).find((x) => x.net === net && job.map[x.ref]);
    const where = `${job.map[pin.ref]}.${pin.name}`;
    const at = pinAt[where];
    const name = netAt[where].includes('.') ? `${job.q}_${port}` : netAt[where];  // a named net keeps its name
    c = e.addLabel(c, name, at);
    c = { ...c, labels: c.labels.map((lb) => (lb.net === pasted.ports[port] ? { ...lb, net: name } : lb)) };
  }
  // parts this stage hasn't got go; the rest take the starter's refs and values
  const drop = Object.keys(pasted.refs).filter((r) => !job.map[r]).map((r) => pasted.refs[r]);
  if (job.q === 'Q1') {
    // no series base resistor: C3 joins the base; R7 (kept) biases it from V+
    for (const [r, pinName] of [['C5', '2'], ['Q3', 'B']]) {
      const part = c.parts.find((p) => p.ref === pasted.refs[r]);
      c = e.addLabel(c, 'q1b', e.snapPoint((await import('/schematic/symbols.js')).pinPositions(part)[pinName]));
    }
    c = e.addLabel(c, 'q1b', pinAt['R7.2']);
  }
  c = e.deleteItems(c, { parts: drop });
  for (const [from, to] of Object.entries(job.map)) pending.push([pasted.refs[from], to]);
}
pending.forEach(([from], i) => { c = e.renamePart(c, from, `T${i}`); });
pending.forEach(([, to], i) => {
  c = e.renamePart(c, `T${i}`, to);
  const { ref, pos, rot, ...fields } = S.parts.find((p) => p.ref === to);
  c = e.updatePart(c, to, fields);
});
return c;
"""


def test_rebuild_big_muff_from_blocks(page: Page, base_url: str) -> None:
    """Phase 4's acceptance: the Big Muff rebuilt by pasting blocks (4 BJT stages from the
    gain-stage block, and the tone stack) has the starter's parts and connections, and
    simulates the same."""
    page.goto(base_url)
    c = run_js(page, REBUILD, {"stages": STAGES, "tone": TONE})
    starter = api(page, base_url, "GET", "api/starters/big-muff-pi-v3")
    rebuilt = api(page, base_url, "POST", "api/view", {"circuit": c})
    assert rebuilt["problem"] is None

    def parts(view: dict[str, Any]) -> dict[str, Any]:
        return {p["ref"]: {k: v for k, v in p.items() if k not in ("pos", "rot")}
                for p in view["circuit"]["parts"]}  # fmt: skip

    assert parts(rebuilt) == parts(starter)

    def partition(view: dict[str, Any]) -> set[frozenset[str]]:
        nets: dict[str, set[str]] = {}
        for p in view["parts"]:
            for pin in p["pins"]:
                nets.setdefault(pin["net"], set()).add(f"{p['ref']}.{pin['name']}")
        return {frozenset(members) for members in nets.values()}

    assert partition(rebuilt) == partition(starter)

    runs = [
        api(page, base_url, "POST", "api/run", {"circuit": v["circuit"], "nodes": ["out"]})
        for v in (rebuilt, starter)
    ]
    mine, reference = runs
    name_of = {
        f"{p['ref']}.{pin['name']}": pin["net"] for p in rebuilt["parts"] for pin in p["pins"]
    }
    for p in starter["parts"]:
        for pin in p["pins"]:
            v = reference["op"]["voltages"][pin["net"]]
            got = mine["op"]["voltages"][name_of[f"{p['ref']}.{pin['name']}"]]
            assert got == pytest.approx(v, abs=1e-6), f"{p['ref']}.{pin['name']}"
    assert mine["ac"]["nodes"]["out"] == pytest.approx(reference["ac"]["nodes"]["out"], abs=0.01)
    a, b = mine["tran"]["nodes"]["out"]["stats"], reference["tran"]["nodes"]["out"]["stats"]
    assert a["gain_db"] == pytest.approx(b["gain_db"], abs=0.01)
    assert a["clipping"]["thd"] == pytest.approx(b["clipping"]["thd"], abs=1e-4)


def right_click_at(page: Page, x: float, y: float) -> None:
    page.mouse.click(*to_screen(page, x, y), button="right")
    expect(page.locator(".menu").first).to_be_visible()


def test_right_click_menu(page: Page, base_url: str) -> None:
    """D-095: right-click → Blocks ▸ Insert or manage blocks… (the same menu as the
    header's; no separate block list) → the block follows the pointer until a click drops
    it (on a wire: spliced in); a part's own items (Delete); the header menus as submenus
    (Edit ▸ Undo); empty space has no part items; Paste floats too."""
    blank(page, base_url)
    before = views(page)
    drag(page, (-280, 0), (280, 0))  # guitar out → amp in
    wait_for_view(page, before)
    right_click_at(page, 0, 0)  # on the wire
    expect(page.locator("#ctx-blocks")).to_have_count(0)  # no separate block list
    page.locator("#ctx-blocks-menu").hover()
    page.locator(".menu #menu-insert-block").click()
    page.locator("button.insert", has_text="Clipper \u00b7 diodes to ground (Rat)").click()
    # it follows the pointer, as from the Blocks dialog, until a click drops it
    page.wait_for_selector("svg#schematic.placing")
    assert {"IN", "OUT"} == set(drawn_refs(page))
    before = views(page)
    click_at(page, 0, 0)  # on the wire: spliced in
    wait_for_view(page, before)
    assert {"IN", "OUT", "R1", "D1", "D2"} == set(drawn_refs(page))
    right_click_at(page, *part_pos(page, "R1"))
    expect(page.locator("#ctx-inspect .menu-label")).to_have_text("Edit R1\u2026")
    before = views(page)
    page.locator("#ctx-delete").click()
    wait_for_view(page, before)
    assert "R1" not in drawn_refs(page)
    box = page.locator("#schematic").bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + 30, box["y"] + 30, button="right")  # empty space
    expect(page.locator(".menu").first).to_be_visible()
    expect(page.locator("#ctx-delete")).to_have_count(0)
    page.locator("#ctx-edit-menu").hover()
    before = views(page)
    page.locator(".menu #menu-undo").click()
    wait_for_view(page, before)
    assert "R1" in drawn_refs(page)
    expect(page.locator(".menu")).to_have_count(0)
    # copy R1, then right-click → Paste: it floats until the click
    click_part(page, "R1")
    press(page, "Control+c")
    page.mouse.click(box["x"] + 30, box["y"] + 30, button="right")
    page.locator("#ctx-paste").click()
    page.wait_for_selector("svg#schematic.placing")
    before = views(page)
    click_low(page)
    wait_for_view(page, before)
    assert len(drawn_refs(page)) == 6


def test_a_box_selection_moves_whole_twice(page: Page, base_url: str) -> None:
    """A box-selected group keeps its wires and labels after a move, so a second drag (by
    one of its parts, nothing clicked in between) moves all of it again."""
    page.goto(f"{base_url}#ts808")
    wait_for_update(page, 0)
    a, b = to_screen(page, 40, -60), to_screen(page, 230, 90)
    page.keyboard.down("Shift")
    page.mouse.move(*a)
    page.mouse.down()
    page.mouse.move(*b, steps=6)
    page.mouse.up()
    page.keyboard.up("Shift")
    selected = "document.querySelectorAll('line.wire.selected').length"
    wires_picked = page.evaluate(selected)
    labels_picked = page.locator(".net-label.selected").count()
    assert wires_picked >= 2
    ref = page.locator("g.part.selected").first.get_attribute("data-ref") or ""
    # mid-drag, the wires being re-laid and their end dots are hidden, not left behind
    # at the old place (the user saw them as ghosts until the drop, D-095)
    x, y = part_pos(page, ref)
    page.mouse.move(*to_screen(page, x, y))
    page.mouse.down()
    page.mouse.move(*to_screen(page, x, y + 40), steps=6)
    left = page.evaluate("""() => {
      const shown = (n) => getComputedStyle(n).visibility !== 'hidden';
      const ends = (ls) => new Set(ls.flatMap((l) => [`${l.getAttribute('x1')},${l.getAttribute('y1')}`, `${l.getAttribute('x2')},${l.getAttribute('y2')}`]));
      const lines = [...document.querySelectorAll('line.wire')];
      const hidden = ends(lines.filter((l) => !shown(l)));
      const kept = ends(lines.filter(shown));
      const dots = [...document.querySelectorAll('circle.wire-end, circle.junction')].filter(shown)
        .filter((d) => { const at = `${d.getAttribute('cx')},${d.getAttribute('cy')}`; return hidden.has(at) && !kept.has(at); });
      return { hidden: hidden.size, dots: dots.length };
    }""")
    assert left["hidden"] > 0 and left["dots"] == 0
    before = views(page)
    page.mouse.up()
    wait_for_view(page, before)
    assert page.evaluate(selected) == wires_picked
    for step in (1, 2):
        x, y = part_pos(page, ref)
        before = views(page)
        drag(page, (x, y), (x, y + 40))
        wait_for_view(page, before)
        assert part_pos(page, ref) == (x, y + 40), f"move {step}"
        assert page.evaluate(selected) == wires_picked, f"wires dropped after move {step}"
        assert page.locator(".net-label.selected").count() == labels_picked


def box_select(page: Page) -> None:
    page.keyboard.down("Shift")
    drag(page, (40, -60), (230, 90))
    page.keyboard.up("Shift")
    assert page.locator("g.part.selected").count() >= 2


def test_any_other_drag_lets_go_of_the_selection(
    page: Page, base_url: str, half_drawn: list[str]
) -> None:
    """D-095: with a box selection, drawing a wire (or dragging a part outside it) lets go
    of the whole selection, as a click on empty space does; the user saw the parts stay
    selected and the wires not."""
    page.goto(f"{base_url}#ts808")
    wait_for_update(page, 0)
    box_select(page)
    # a wire outside the selection: draw a new wire off its middle
    x1, y1, x2, _ = page.evaluate("""() => {
      const l = [...document.querySelectorAll('line.wire:not(.selected)')]
        .find((w) => Math.abs(w.getAttribute('x1') - w.getAttribute('x2')) >= 40);
      return ['x1', 'y1', 'x2', 'y2'].map((a) => Number(l.getAttribute(a)));
    }""")
    mid = ((x1 + x2) / 2, y1)
    before = views(page)
    drag(page, mid, (mid[0], mid[1] + 60))
    wait_for_view(page, before)
    expect(page.locator("g.part.selected")).to_have_count(0)
    expect(page.locator("line.wire.selected")).to_have_count(0)
    # dragging a part that isn't in the selection lets go of it too
    box_select(page)
    outside = page.locator("g.part:not(.selected)").first.get_attribute("data-ref") or ""
    x, y = part_pos(page, outside)
    before = views(page)
    drag(page, (x, y), (x, y + 40))
    wait_for_view(page, before)
    expect(page.locator("g.part.selected")).to_have_count(0)
    expect(page.locator("line.wire.selected")).to_have_count(0)


def dc_texts(page: Page) -> list[tuple[str, str, str, str]]:
    """Every DC voltage on the drawing: (net, x, y, text), in a stable order."""
    rows = page.eval_on_selector_all(
        ".dc-layer text",
        "(ts) => ts.map((t) => [t.dataset.net, t.getAttribute('x'), t.getAttribute('y'), t.textContent])",
    )
    return sorted(tuple(r) for r in rows)


def test_dc_voltages_show_on_a_block_just_added(page: Page, base_url: str) -> None:
    """The user, 2026-11-10: on the Rangemaster with View → DC voltages on, a second 12 V
    pump block showed no voltages until DC was turned off and on again."""
    page.goto(f"{base_url}#dallas-rangemaster")
    wait_for_update(page, 0)
    page.locator("#autorun").check()
    menu(page, "view-menu", "menu-dc")
    for n in range(2):
        updates = int(page.evaluate("Number(document.body.dataset.updates || 0)"))
        insert(page, "12 V supply \u00b7 charge pump and zener")
        wait_for_update(page, updates)
        shown = dc_texts(page)
        menu(page, "view-menu", "menu-dc")  # off and on again: what it should have shown
        menu(page, "view-menu", "menu-dc")
        assert page.locator("g.part.selected").count() == 8  # the block is still selected
        assert shown == dc_texts(page), f"after block {n + 1}"
    assert {"V18", "V12"} <= {net for net, *_ in shown}
