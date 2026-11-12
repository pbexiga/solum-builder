"""The Notes pane (9d4): general notes added, titled, edited, collapsed and deleted; part
and net notes added from a right-click, listed, selected and edited; an old circuit's
notes; a block dropped twice; the notice after renaming a part that notes mention."""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.ui.conftest import open_circuit, part_pos, wait_for_update
from tests.ui.test_blocks import blank, insert, right_click_at
from tests.ui.test_editor import click_at, drag, inspect, press, views, wait_for_view


def note(page: Page, key: str) -> Locator:
    return page.locator(f'#notes-body [data-note="{key}"]')


def tab(page: Page, name: str) -> None:
    page.locator(f'#notes-body [data-tab="{name}"]').click()


def save_field(page: Page, field: Locator, value: str) -> None:
    """Type into a note's field and leave it: one edit."""
    before = views(page)
    field.fill(value)
    field.press("Control+Enter" if field.evaluate("(e) => e.tagName") == "TEXTAREA" else "Enter")
    wait_for_view(page, before)


def test_general_notes(page: Page, base_url: str) -> None:
    blank(page, base_url)
    expect(page.locator("#notes-body .notes-empty")).to_contain_text("No notes yet")
    before = views(page)
    page.locator("#notes-add").click()
    wait_for_view(page, before)
    title = note(page, "g:0").locator(".note-title")
    expect(title).to_be_focused()  # a new note opens with its title ready to type
    save_field(page, title, "Build")
    save_field(page, note(page, "g:0").locator(".note-text"), "Socket Q1.\nBias TR1 to 4.5 V.")
    expect(page.locator("#dirty")).to_be_visible()  # an edit like any other
    expect(page.locator("#notes-count")).to_have_text("1")
    # a second note: it opens, the first shuts (one open at a time)
    before = views(page)
    page.locator("#notes-add").click()
    wait_for_view(page, before)
    expect(note(page, "g:0")).not_to_have_class("note-item open")
    expect(note(page, "g:0").locator(".note-name")).to_have_text("Build")
    note(page, "g:0").locator(".note-head").click()
    expect(note(page, "g:0").locator(".note-text")).to_have_value("Socket Q1.\nBias TR1 to 4.5 V.")
    expect(note(page, "g:1").locator(".note-text")).to_have_count(0)
    note(page, "g:0").locator(".note-head").click()  # shut again
    expect(page.locator("#notes-body .note-item.open")).to_have_count(0)
    # delete, then undo brings it back
    note(page, "g:0").locator(".note-head").click()
    before = views(page)
    note(page, "g:0").locator(".note-delete").click()
    wait_for_view(page, before)
    expect(page.locator("#notes-body .note-item")).to_have_count(1)
    expect(note(page, "g:0").locator(".note-name")).to_have_text("New note")
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    expect(page.locator("#notes-body .note-item")).to_have_count(2)
    expect(note(page, "g:0").locator(".note-name")).to_have_text("Build")


def test_an_old_circuits_notes_are_listed_and_select_their_part(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")  # a v29 file: its notes moved on load
    tab(page, "parts")
    names = page.locator("#notes-body .note-name").all_inner_texts()
    assert names == ["C3", "C4", "C5", "q1e", "u2o", "VREF"]
    before = int(page.evaluate("Number(document.body.dataset.updates || 0)"))
    note(page, "p:C3").locator(".note-head").click()
    wait_for_update(page, before)
    expect(page.locator('#schematic g.part.selected[data-ref="C3"]')).to_have_count(1)
    expect(page.locator("#probe-body .note")).to_contain_text("a high-pass in the feedback leg")
    # edited in place, and Probe shows the new text
    save_field(page, note(page, "p:C3").locator(".note-text"), "Sets the bass cut.")
    expect(note(page, "p:C3").locator(".note-text")).to_have_value("Sets the bass cut.")


def test_add_a_note_from_a_right_click(page: Page, base_url: str) -> None:
    blank(page, base_url)
    before = views(page)
    drag(page, (-280, 0), (280, 0))  # guitar out → amp in: an unnamed net
    wait_for_view(page, before)
    right_click_at(page, 0, 0)  # on the wire
    expect(page.locator("#ctx-note .menu-label")).to_have_text("Add note…")
    page.locator("#ctx-note").click()
    form = page.locator("form.popup")
    expect(form).to_contain_text("it needs a name first")
    page.locator("#field-net").fill("GND")
    page.locator("#field-note").fill("Straight through.")
    form.locator("button.primary").click()
    expect(form.locator(".error")).to_contain_text("another net's name")  # ground's
    page.locator("#field-net").fill("SIG")
    before = views(page)
    form.locator("button.primary").click()
    wait_for_view(page, before)
    expect(page.locator('#schematic .net-label[data-net="SIG"]')).to_have_count(1)
    expect(note(page, "n:SIG").locator(".note-text")).to_have_value("Straight through.")
    # one undo takes the name and the note
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    expect(page.locator('#schematic .net-label[data-net="SIG"]')).to_have_count(0)
    expect(page.locator("#notes-body .notes-empty")).to_contain_text("No part or net notes")
    # a part: Add note…, then Edit note… opens it in the pane
    right_click_at(page, *part_pos(page, "OUT"))
    page.locator("#ctx-note").click()
    page.locator("#field-note").fill("A 1M input.")
    before = views(page)
    page.locator("form.popup button.primary").click()
    wait_for_view(page, before)
    expect(note(page, "p:OUT").locator(".note-text")).to_have_value("A 1M input.")
    right_click_at(page, *part_pos(page, "OUT"))
    expect(page.locator("#ctx-note .menu-label")).to_have_text("Edit note…")


@pytest.mark.usefixtures("half_drawn")  # the blocks float until wired: refused runs
def test_a_block_dropped_twice_gives_two_general_notes(page: Page, base_url: str) -> None:
    blank(page, base_url)
    name = "Treble booster \u00b7 Rangemaster (germanium)"
    insert(page, name)
    insert(page, name)
    heads = page.locator("#notes-body .note-name").all_inner_texts()
    assert heads == [f"From block: {name}"] * 2
    note(page, "g:1").locator(".note-head").click()
    expect(note(page, "g:1").locator(".note-text")).to_have_value(
        re.compile(r"\n\nPasted with new refs: .+ → ")
    )


def test_renaming_a_part_offers_to_update_the_notes(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    click_at(page, *part_pos(page, "R4"))
    expect(page.locator('#schematic g.part.selected[data-ref="R4"]')).to_have_count(1)
    inspect(page, {"ref": "R40"})
    notice = page.locator("#rename-notice")
    expect(notice).to_contain_text("R4 is mentioned in 1 note (it\u2019s R40 now).")
    notice.locator('[data-action="show"]').click()
    expect(notice.locator(".mentions li")).to_have_count(1)
    expect(notice.locator(".mentions li")).to_contain_text("C3's note")
    expect(notice.locator('[data-action="show"]')).to_have_text("Hide")
    before = views(page)
    notice.locator('[data-action="replace"]').click()
    wait_for_view(page, before)
    expect(notice).to_be_hidden()
    tab(page, "parts")
    note(page, "p:C3").locator(".note-head").click()
    expect(note(page, "p:C3").locator(".note-text")).to_have_value(
        re.compile(r"^With R40, a high-pass")
    )
    # ✕ changes nothing: rename again, close the notice
    click_at(page, *part_pos(page, "R8"))
    inspect(page, {"ref": "R80"})
    expect(notice).to_contain_text("R8 is mentioned in 1 note")
    notice.locator('[data-action="close"]').click()
    expect(notice).to_be_hidden()


def test_the_pane_keeps_its_height_across_tabs_and_scrolls(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "big-muff-aion-halo")  # 20 general notes, a few part notes
    box = page.locator("#notes-body .notes-scroll")
    tall = box.evaluate("(b) => ({ shown: b.clientHeight, all: b.scrollHeight })")
    assert tall["all"] > tall["shown"]  # more notes than fit: it scrolls
    pane = page.locator("#panel-notes")
    height = pane.evaluate("(p) => p.offsetHeight")
    blank(page, base_url)  # no notes at all
    empty = pane.evaluate("(p) => p.offsetHeight")
    tab(page, "parts")
    assert pane.evaluate("(p) => p.offsetHeight") == empty  # swapping tabs doesn't resize it
    assert empty == height  # nor does having notes or none


def test_renaming_back_lists_the_notes_that_already_use_the_name(page: Page, base_url: str) -> None:
    """The user, 2026-11-10: R5 → R54, closed without replacing, then back to R5: nothing
    mentions R54, but 8 notes say R5; the box says so and lists them (nothing to replace).
    It sits over the middle of the drawing (D-271)."""
    open_circuit(page, base_url, "big-muff-aion-halo")
    notice = page.locator("#rename-notice")
    click_at(page, *part_pos(page, "R5"))
    inspect(page, {"ref": "R54"})
    expect(notice).to_contain_text("R5 is mentioned in 8 notes (it\u2019s R54 now).")
    box, canvas = notice.bounding_box(), page.locator("#canvas-body").bounding_box()
    assert box is not None and canvas is not None
    assert abs((box["x"] + box["width"] / 2) - (canvas["x"] + canvas["width"] / 2)) < 2
    assert abs((box["y"] + box["height"] / 2) - (canvas["y"] + canvas["height"] / 2)) < 2
    notice.locator('[data-action="close"]').click()
    click_at(page, *part_pos(page, "R54"))
    inspect(page, {"ref": "R5"})
    expect(notice).to_contain_text("No note mentions R54. 8 notes already say R5.")
    expect(notice.locator('[data-action="replace"]')).to_have_count(0)
    notice.locator('[data-action="show"]').click()
    expect(notice.locator("h3")).to_have_text(["Already say R5"])
    expect(notice.locator(".mentions li input")).to_have_count(0)  # nothing to tick
    expect(notice.locator(".mentions li").first).to_contain_text("Version: ")
