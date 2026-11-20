"""P6b (D-368): the Board view in a real browser, on the Rangemaster with its hand-made
board (`tests/fixtures/stripboard/rangemaster.yaml`): the toggle, the board drawn, its own
panes in the column, the selection lit on both drawings, the result panes back after; the
Board button (D-370)."""

import itertools
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from solum.yamlio import load_yaml
from tests.ui.conftest import REPO, click_part, open_circuit, reload_kept
from tests.ui.test_panes import order as pane_ids

pytestmark = pytest.mark.ui

_saves = itertools.count(1)


def open_with_board(page: Page, base_url: str, board: dict[str, Any] | None) -> None:
    """The Rangemaster starter saved as a circuit carrying `board`, and opened."""
    page.goto(base_url)
    circuit = page.request.get(f"{base_url}api/starters/dallas-rangemaster").json()["circuit"]
    if board is not None:
        circuit["stripboard"] = board
    made = {"circuit": circuit, "name": f"Rangemaster board {next(_saves)}"}
    saved = page.request.post(f"{base_url}api/circuits", data=made)
    assert saved.ok, saved.text()
    open_circuit(page, base_url, "circuit/" + saved.json()["circuit"]["id"])


def show_board(page: Page) -> None:
    page.locator("#board-button").click()
    expect(page.locator("#board .board-part").first).to_be_visible()


def test_the_board_view_shows_the_board_and_its_own_panes(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    results = pane_ids(page)
    show_board(page)
    expect(page.locator("#schematic")).to_be_hidden()
    expect(page.locator("aside.panels")).to_be_hidden()
    expect(page.locator("#palette")).to_be_hidden()
    expect(page.locator("#board-panels")).to_be_visible()
    assert page.locator("#board .board-part").count() == 8
    size = "12 × 9 holes (30 × 23 mm), 1 cut, 2 links"
    expect(page.locator("#board-size-text")).to_have_text(size)
    expect(page.locator("#board .cut")).to_have_count(1)
    expect(page.locator("#board .link")).to_have_count(2)
    # every part placed, every net joined: the progress check says so
    expect(page.locator("#board-tray-body")).to_contain_text("Every part is on the board.")
    expect(page.locator("#board-nets-body .board-progress")).to_have_text("All 8 nets done.")
    expect(page.locator("#board-warnings-body")).to_contain_text("The board matches the circuit.")
    # the small schematic is drawn in its pane
    expect(page.locator("#board-sheet .part[data-ref='Q1']")).to_have_count(1)

    # a part clicked on the board is selected on both drawings
    page.locator("#board .board-part[data-ref='Q1']").click()
    expect(page.locator("#board .board-part[data-ref='Q1']")).to_have_class("board-part selected")
    expect(page.locator("#board-sheet .part[data-ref='Q1']")).to_have_class("part selected")
    # and one clicked on the small schematic lights on the board
    page.locator("#board-sheet .part[data-ref='R2']").click()
    expect(page.locator("#board .board-part[data-ref='R2']")).to_have_class("board-part selected")
    expect(page.locator("#board .board-part[data-ref='Q1']")).to_have_class("board-part")

    # the schematic's keys don't act in the Board view: Delete leaves R2 in the circuit
    page.keyboard.press("Delete")
    expect(page.locator("#board .board-part[data-ref='R2']")).to_have_count(1)
    assert page.evaluate("document.getElementById('dirty').hidden")

    # back to the Schematic view: the result panes as they were, R2 still selected
    page.locator("#board-button").click()
    expect(page.locator("aside.panels")).to_be_visible()
    expect(page.locator("#board")).to_be_hidden()
    expect(page.locator("#board-panels")).to_be_hidden()
    expect(page.locator("#board-tray")).to_be_hidden()
    expect(page.locator("#palette")).to_be_visible()
    assert pane_ids(page) == results
    expect(page.locator("#schematic .part[data-ref='R2']")).to_have_class("part selected")


def test_a_circuit_without_a_board_shows_its_parts_to_place(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, None)
    page.locator("#board-button").click()
    expect(page.locator("#board-size-text")).to_have_text("Empty board")
    # the Tray on the left (D-371): the 8 board parts by kind; off the board VR1, the
    # guitar's and amp's jacks, the stock footswitch and status LED (D-370)
    expect(page.locator("#board-tray")).to_be_visible()
    expect(page.locator("#board-tray-count")).to_have_text("· 13 left")
    expect(page.locator("#board-tray-body li[data-ref]")).to_have_count(13)
    kinds = ["Resistors", "Capacitors", "Transistors"]
    expect(page.locator("#board-tray-body .board-subhead")).to_have_text(kinds)
    expect(page.locator("#board-tray-body li[data-ref='Q1']")).to_contain_text("in a line")
    off = page.locator("#board-tray-body .off-board li")
    expect(off).to_have_text([
        "VR1 (Volume) A10k log (A)", 'IN (Input) ¼" jack TS', 'OUT (Output) ¼" jack TS',
        "Footswitch 3PDT stock, true bypass", "Status LED stock",
    ])  # fmt: skip
    # a row selects its part on the small schematic
    page.locator("#board-tray-body li[data-ref='R2']").click()
    expect(page.locator("#board-sheet .part[data-ref='R2']")).to_have_class("part selected")
    # the wire ends are with their nets
    c2 = page.locator("#board-nets-body li[data-net='C2.1']")
    expect(c2).to_contain_text("a wire from VR1.2")
    expect(page.locator("#board-nets-body .board-progress")).to_have_text("0 of 8 nets done.")


def test_the_board_panes_keep_their_own_order(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, None)
    page.locator("#board-button").click()
    ids = page.eval_on_selector_all("#board-panels > details", "(ds) => ds.map((d) => d.id)")
    assert ids == ["board-warnings", "board-schematic", "board-nets", "board-settings"]
    grip = page.locator("[data-grip='board-nets']")
    grip.focus()
    grip.press("ArrowUp")
    moved = page.eval_on_selector_all("#board-panels > details", "(ds) => ds.map((d) => d.id)")
    assert moved == ["board-warnings", "board-nets", "board-schematic", "board-settings"]
    # the result panes' order is its own
    page.locator("#board-button").click()
    assert pane_ids(page)[0] == "panel-problems"


def test_visiting_the_board_changes_nothing_until_placed(page: Page, base_url: str) -> None:
    """D-370: the Board button opens an empty board; leaving before placing anything leaves
    the circuit as it was, the button quiet."""
    open_with_board(page, base_url, None)
    button = page.locator("#board-button")
    expect(button).not_to_have_class("board-button marked")
    expect(button).to_have_attribute("aria-pressed", "false")
    button.click()
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#board-size-text")).to_have_text("Empty board")
    expect(page.locator("#remove-board")).to_have_count(0)
    button.click()
    expect(button).to_have_attribute("aria-pressed", "false")
    expect(page.locator("aside.panels")).to_be_visible()
    assert page.evaluate("document.getElementById('dirty').hidden")
    expect(button).not_to_have_class("board-button marked")
    # Tools → Stripboard layout does the same as the button
    page.locator("#tools-menu").click()
    page.locator("#menu-board").click()
    expect(button).to_have_attribute("aria-pressed", "true")


def test_a_board_marks_the_button_and_can_be_removed(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    button = page.locator("#board-button")
    expect(button).to_have_class("board-button marked")
    show_board(page)
    page.locator("#board-settings summary").click()
    page.locator("#remove-board").click()
    # one undo step: the view stays on the empty board, the button quiet, Not saved
    expect(page.locator("#board-size-text")).to_have_text("Empty board")
    expect(page.locator("#board .board-part")).to_have_count(0)
    expect(button).not_to_have_class("board-button marked")
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#dirty")).to_be_visible()
    page.keyboard.press("Control+z")
    expect(page.locator("#board .board-part")).to_have_count(8)
    expect(button).to_have_class("board-button marked")


def test_show_values_is_a_setting_remembered(page: Page, base_url: str) -> None:
    """The editor's settings (spec, *Editor settings*): Show values on by default; off, the
    labels are refs only, and it stays off after a reload (the server keeps it, D-311)."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    label = page.locator("#board .board-label[data-ref='R1']")
    expect(label.locator(".value")).to_have_count(1)
    page.locator("#board-settings > summary").click()
    box = page.locator("#board-settings-body input[data-setting='values']")
    expect(box).to_be_checked()
    expect(page.locator("#board-settings-body input[data-setting='next']")).to_be_disabled()
    box.uncheck()
    expect(label.locator(".value")).to_have_count(0)
    expect(label.locator(".ref")).to_have_text("R1")
    reload_kept(page)
    show_board(page)
    expect(page.locator("#board .board-label[data-ref='R1'] .value")).to_have_count(0)
    expect(page.locator("#board-settings")).to_have_attribute("open", "")  # kept open too
    page.locator("#board-settings-body input[data-setting='values']").check()
    expect(page.locator("#board .board-label[data-ref='R1'] .value")).to_have_count(1)
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")


def test_the_board_size_changes_by_hand(
    page: Page, base_url: str, browser_errors: list[str]
) -> None:
    """D-372: a column added on its ruler mark, one that isn't empty refused with what's on
    it, Trim takes the empty edges off; each an undo step. Auto-grow off greys the margin."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    size = page.locator("#board-size-text")
    page.locator("#board .ruler[data-axis='column'][data-line='0']").click()
    page.get_by_text("Insert a column left of A").click()
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links")
    expect(page.locator("#dirty")).to_be_visible()
    page.locator("#board .ruler[data-axis='column'][data-line='1']").click()
    page.get_by_text("Remove column B").click()
    expect(page.locator("#error")).to_have_text("Column B isn't empty: the pad at B1 is on it.")
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]  # the refusal
    page.locator("#board-trim").click()
    expect(size).to_have_text("11 × 9 holes (28 × 23 mm), 1 cut, 2 links")
    page.keyboard.press("Control+z")
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links")
    page.keyboard.press("Control+z")
    expect(size).to_have_text("12 × 9 holes (30 × 23 mm), 1 cut, 2 links")
    # auto-grow off: the margin greyed
    page.locator("#board-settings > summary").click()
    page.locator("#board-settings-body input[data-setting='grow']").uncheck()
    expect(page.locator("#board g.board")).to_have_class("board board-fixed")
    page.locator("#board-settings-body input[data-setting='grow']").check()
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")


def test_the_board_has_its_own_undo_history(page: Page, base_url: str) -> None:
    """D-370: a schematic edit, then a board edit; Ctrl+Z in each view undoes only its own,
    and the History pane lists the steps of the view showing."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    click_part(page, "R1")
    page.keyboard.press("Delete")
    expect(page.locator('g.part[data-ref="R1"]')).to_have_count(0)
    show_board(page)
    size = page.locator("#board-size-text")
    page.locator("#board .ruler[data-axis='column'][data-line='0']").click()
    page.get_by_text("Insert a column left of A").click()
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links")
    page.locator("#history-button").click()
    current = page.locator("#history-rows .history-step.current")
    expect(current).to_have_text("Insert a column left of A")
    page.locator("#history-button").click()
    page.keyboard.press("Control+z")
    expect(size).to_have_text("12 × 9 holes (30 × 23 mm), 1 cut, 2 links")
    page.keyboard.press("Control+z")  # the board's history at its start: R1 stays deleted
    page.keyboard.press("Control+Shift+z")
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links")
    page.locator("#board-button").click()  # back to the schematic
    expect(page.locator('g.part[data-ref="R1"]')).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(page.locator('g.part[data-ref="R1"]')).to_have_count(1)
    show_board(page)
    # the schematic's undo kept the board
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links")
    expect(page.locator("#dirty")).to_be_visible()
