"""P6b (D-368): the Board view in a real browser, on the Rangemaster with its hand-made
board (`tests/fixtures/stripboard/rangemaster.yaml`): the toggle, the board drawn, its own
panes in the column, the selection lit on both drawings, the result panes back after; the
Board button (D-370)."""

import itertools
import json
import re
import zipfile
from typing import Any

import pytest
from playwright.sync_api import Page, Route, expect

from solum.yamlio import load_yaml
from tests.ui.conftest import REPO, click_part, open_circuit, reload_kept
from tests.ui.test_editor import menu
from tests.ui.test_panes import order as pane_ids

pytestmark = pytest.mark.ui

_saves = itertools.count(1)


def open_with_board(page: Page, base_url: str, board: dict[str, Any] | None,
                    starter: str = "dallas-rangemaster") -> None:  # fmt: skip
    """The Rangemaster starter (or `starter`) saved as a circuit carrying `board`, and
    opened."""
    page.goto(base_url)
    circuit = page.request.get(f"{base_url}api/starters/{starter}").json()["circuit"]
    if board is not None:
        circuit["stripboard"] = board
    made = {"circuit": circuit, "name": f"Rangemaster board {next(_saves)}"}
    saved = page.request.post(f"{base_url}api/circuits", data=made)
    assert saved.ok, saved.text()
    open_circuit(page, base_url, "circuit/" + saved.json()["circuit"]["id"])


def expect_matches(page: Page) -> None:
    """Nothing to warn about: every net done, no fault, every placement limit met."""
    expect(page.locator("#board-warnings-body")).to_contain_text("The board matches the circuit.")


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
    size = "12 × 9 holes (30 × 23 mm), 1 cut, 2 links, 9 wires"
    expect(page.locator("#board-size-text")).to_have_text(size)
    expect(page.locator("#board .cut")).to_have_count(1)
    expect(page.locator("#board .link")).to_have_count(2)
    # every part placed, every net joined: the progress check says so
    expect(page.locator("#board-tray-body")).to_contain_text("Every part is on the board.")
    expect(page.locator("#board-nets-body .board-progress")).to_have_text("All 8 nets done.")
    expect_matches(page)
    # the small schematic is drawn in its pane
    expect(page.locator("#board-sheet .part[data-ref='Q1']")).to_have_count(1)

    # a part clicked on the board is selected on both drawings
    page.locator("#board .board-part[data-ref='Q1']").click()
    expect(page.locator("#board .board-part[data-ref='Q1']")).to_have_class(
        re.compile(r"\bboard-part\b.*\bselected\b")
    )
    expect(page.locator("#board-sheet .part[data-ref='Q1']")).to_have_class("part selected")
    # and one clicked on the small schematic lights on the board
    page.locator("#board-sheet .part[data-ref='R2']").click()
    expect(page.locator("#board .board-part[data-ref='R2']")).to_have_class(
        re.compile(r"\bboard-part\b.*\bselected\b")
    )
    expect(page.locator("#board .board-part[data-ref='Q1']")).not_to_have_class(
        re.compile(r"\bselected\b")
    )

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
    # guitar's and amp's jacks, Power (D-375); nothing stock (D-385)
    expect(page.locator("#board-tray")).to_be_visible()
    expect(page.locator("#board-tray-count")).to_have_text("· 12 left")
    expect(page.locator("#board-tray-body li[data-ref]")).to_have_count(12)
    kinds = ["Resistors", "Capacitors", "Transistors"]
    expect(page.locator("#board-tray-body .board-subhead")).to_have_text(kinds)
    expect(page.locator("#board-tray-body li[data-ref='Q1']")).to_contain_text("in a line")
    off = page.locator("#board-tray-body .off-board li")  # each with its move button (D-385)
    expect(off).to_have_text([
        "VR1 (Volume) A10k log (A)↑ On board", 'IN (Input) ¼" jack TS↑ On board',
        'OUT (Output) ¼" jack TS↑ On board', "Power the supply's wires",
    ])  # fmt: skip
    # a row selects its part on the small schematic
    page.locator("#board-tray-body li[data-ref='R2']").click()
    expect(page.locator("#board-sheet .part[data-ref='R2']")).to_have_class("part selected")
    # the lugs to wire are with their nets
    c2 = page.locator("#board-nets-body li[data-net='C2.1']")
    expect(c2).to_contain_text("a wire from VR1 lug 2")
    expect(page.locator("#board-nets-body .board-progress")).to_have_text(
        "0 of 8 nets done; 9 lugs to wire."
    )


def test_a_long_nets_list_scrolls_in_its_own_pane(page: Page, base_url: str) -> None:
    """The TS808's 24 nets scroll inside Nets (as Problems' rows do, D-077), the list up to
    half the window (at least 300 px), so the other panes stay in reach."""
    open_with_board(page, base_url, None, "ts808")
    page.locator("#board-button").click()
    nets = page.locator("#board-nets-body .net-list")
    expect(nets.locator("li")).to_have_count(24)
    shown, whole, window = nets.evaluate("e => [e.clientHeight, e.scrollHeight, innerHeight]")
    assert shown <= max(300, window / 2) < whole


def test_the_board_panes_keep_their_own_order(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, None)
    page.locator("#board-button").click()
    ids = page.eval_on_selector_all("#board-panels > details", "(ds) => ds.map((d) => d.id)")
    assert ids == ["board-warnings", "board-notes", "board-schematic", "board-nets",
                   "board-settings"]  # fmt: skip
    grip = page.locator("[data-grip='board-nets']")
    grip.focus()
    grip.press("ArrowUp")
    moved = page.eval_on_selector_all("#board-panels > details", "(ds) => ds.map((d) => d.id)")
    assert moved == ["board-warnings", "board-notes", "board-nets", "board-schematic",
                     "board-settings"]  # fmt: skip
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


def test_highlight_rails_tints_the_supply_and_ground_copper(page: Page, base_url: str) -> None:
    """D-381: off by default; on, the Rangemaster's V- copper (its supply, PNP) and GND
    copper are tinted, nothing else; off again, gone."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    rails = page.locator("#board .strip[data-rail]")
    expect(rails).to_have_count(0)
    page.locator("#board-settings > summary").click()
    box = page.locator("#board-settings-body input[data-setting='rails']")
    expect(box).not_to_be_checked()
    box.check()
    expect(page.locator("#board .strip.rail-supply[data-rail='V-']")).to_have_count(2)
    expect(page.locator("#board .strip.rail-ground[data-rail='GND']")).to_have_count(2)
    expect(rails).to_have_count(4)
    box.uncheck()
    expect(rails).to_have_count(0)
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")


def test_see_through_from_its_button_or_t(page: Page, base_url: str) -> None:
    """See-through (D-378) from the toolbar's button or T as well as Settings: the parts
    faint, their outlines and labels kept; the button shows whether it's on."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    button = page.locator("#board-see")
    expect(button).to_have_attribute("aria-pressed", "false")
    button.click()
    expect(page.locator("#board .board.see-through")).to_have_count(1)
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#board .board-label[data-ref='R1']")).to_be_visible()
    page.keyboard.press("t")
    expect(page.locator("#board .board.see-through")).to_have_count(0)
    expect(button).to_have_attribute("aria-pressed", "false")
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
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links, 9 wires")
    expect(page.locator("#dirty")).to_be_visible()
    page.locator("#board .ruler[data-axis='column'][data-line='1']").click()
    page.get_by_text("Remove column B").click()
    expect(page.locator("#refusal .refusal-text")).to_have_text(
        "Column B isn't empty: the wire at B1 is on it."
    )
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]  # the refusal
    page.locator("#board-trim").click()
    expect(size).to_have_text("11 × 9 holes (28 × 23 mm), 1 cut, 2 links, 9 wires")
    page.keyboard.press("Control+z")
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links, 9 wires")
    page.keyboard.press("Control+z")
    expect(size).to_have_text("12 × 9 holes (30 × 23 mm), 1 cut, 2 links, 9 wires")
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
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links, 9 wires")
    page.locator("#history-button").click()
    current = page.locator("#history-rows .history-step.current")
    expect(current).to_have_text("Insert a column left of A")
    page.locator("#history-button").click()
    page.keyboard.press("Control+z")
    expect(size).to_have_text("12 × 9 holes (30 × 23 mm), 1 cut, 2 links, 9 wires")
    page.keyboard.press("Control+z")  # the board's history at its start: R1 stays deleted
    page.keyboard.press("Control+Shift+z")
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links, 9 wires")
    page.locator("#board-button").click()  # back to the schematic
    expect(page.locator('g.part[data-ref="R1"]')).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(page.locator('g.part[data-ref="R1"]')).to_have_count(1)
    show_board(page)
    # the schematic's undo kept the board
    expect(size).to_have_text("13 × 9 holes (33 × 23 mm), 1 cut, 2 links, 9 wires")
    expect(page.locator("#dirty")).to_be_visible()


def hole_point(page: Page, column: int, strip: int) -> tuple[float, float]:
    """A hole's middle on the screen (board units: 10 a hole, D-369)."""
    point = page.evaluate(
        """([c, s]) => {
          const svg = document.getElementById('board');
          const p = new DOMPoint(c * 10, s * 10).matrixTransform(svg.getScreenCTM());
          return [p.x, p.y];
        }""",
        [column, strip],
    )
    return point[0], point[1]


def drag_to(page: Page, start: tuple[float, float], end: tuple[float, float]) -> None:
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, steps=4)
    page.mouse.move(*end, steps=4)
    page.mouse.up()


def test_parts_are_placed_turned_moved_cut_and_linked_by_hand(
    page: Page, base_url: str, browser_errors: list[str]
) -> None:
    """D-374: R2 dragged from the tray onto the board finishes the Rangemaster; turned along
    a strip it shorts two nets, the copper red; with shorts off the same turn is refused;
    moved by dragging; a cut made and mended, a link laid; each an undo step."""
    board = load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml")
    del board["parts"]["R2"]
    open_with_board(page, base_url, board)
    show_board(page)
    tray_r2 = page.locator("#board-tray-body li[data-ref='R2']")
    expect(tray_r2).to_be_visible()
    box = tray_r2.bounding_box()
    assert box
    drag_to(page, (box["x"] + 20, box["y"] + box["height"] / 2), hole_point(page, 9, 5))  # J6
    r2 = page.locator("#board .board-part[data-ref='R2']")
    expect(r2).to_have_count(1)
    # R2 biases Q1's base, so no limit keeps it by the base (D-400 amended): no warning
    expect(page.locator("#board-warnings-body")).to_contain_text("The board matches the circuit.")
    expect(page.locator("#board-warnings-body li.fault")).to_have_count(0)
    expect(page.locator("#dirty")).to_be_visible()
    page.keyboard.press("Control+z")
    expect(r2).to_have_count(0)
    page.keyboard.press("Control+Shift+z")
    expect(r2).to_have_count(1)
    # turned along strip 6 (the input's): a short, red
    page.mouse.click(*hole_point(page, 9, 5))
    page.keyboard.press(" ")
    expect(page.locator("#board .strip.shorted")).not_to_have_count(0)
    expect(page.locator("#board-nets-body .net-shorted").first).to_be_visible()
    page.keyboard.press("Control+z")
    expect(page.locator("#board .strip.shorted")).to_have_count(0)
    # shorts off: the same turn refused, saying why
    page.locator("#board-settings > summary").click()
    page.locator("#board-settings-body input[data-setting='shorts']").uncheck()
    page.mouse.click(*hole_point(page, 9, 5))
    page.keyboard.press(" ")
    expect(page.locator("#refusal")).to_be_visible()
    expect(page.locator("#refusal .refusal-text")).to_contain_text("Shorts are off in Settings.")
    page.locator("#board-settings-body input[data-setting='shorts']").check()
    # moved by dragging its body: J to H, by Q1's base, nothing left to warn about
    drag_to(page, hole_point(page, 9, 5), hole_point(page, 7, 5))
    expect(r2.locator(".leg").first).to_have_attribute("cx", "70")
    expect_matches(page)
    # a cut made and mended with the Cuts tool, a link laid with the Links tool
    page.keyboard.press("c")
    page.mouse.click(*hole_point(page, 9, 4))
    expect(page.locator("#board .cut[data-hole='J5']")).to_have_count(1)
    page.mouse.click(*hole_point(page, 9, 4))
    expect(page.locator("#board .cut[data-hole='J5']")).to_have_count(0)
    page.keyboard.press("k")
    drag_to(page, hole_point(page, 11, 1), hole_point(page, 11, 7))  # L2 to L8, both GND
    expect(page.locator("#board .board-link")).to_have_count(3)
    expect_matches(page)
    page.keyboard.press("Escape")
    expect(page.locator("#board-tools button[data-tool='parts']")).to_have_attribute(
        "aria-pressed", "true"
    )
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]  # the refusal
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")


def lug_point(page: Page, end: str) -> tuple[float, float]:
    box = page.locator(f"#board .off-items .lug[data-lug='{end}'] .lug-ring").bounding_box()
    assert box
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_an_off_board_part_is_put_beside_the_board_and_wired(
    page: Page, base_url: str, browser_errors: list[str]
) -> None:
    """D-375: VR1 dragged out of the tray beside the board; its three lugs wired to their
    holes finish the Rangemaster; a wire's end moved, left loose from its menu (counted in
    Nets), undone; VR1 back to the tray takes its wires; Wire it for me puts it back."""
    board = load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml")
    board["wires"] = [w for w in board["wires"] if not w["from"].startswith("VR1")]
    open_with_board(page, base_url, board)
    show_board(page)
    tray_vr1 = page.locator("#board-tray-body li[data-ref='VR1 (Volume)']")
    expect(tray_vr1).to_be_visible()
    box = tray_vr1.bounding_box()
    assert box
    drag_to(page, (box["x"] + 20, box["y"] + box["height"] / 2), hole_point(page, 4, -8))
    vr1 = page.locator("#board .off-items .off-item[data-item='VR1']")
    expect(vr1).to_have_count(1)
    expect(tray_vr1).to_have_count(0)
    wires = page.locator("#board .off-wire")
    for end, hole in (("VR1.1", (3, 0)), ("VR1.2", (0, 6)), ("VR1.3", (0, 4))):  # D1, A7, A5
        drag_to(page, lug_point(page, end), hole_point(page, *hole))
    expect(wires).to_have_count(9)  # the six kept, and VR1's three
    expect_matches(page)
    expect(page.locator("#board-size-text")).to_contain_text("9 wires")
    # left loose from the wire's menu: still to do; undone
    last = wires.last.locator(".far-end")
    last.click(button="right")
    page.get_by_role("menuitem", name="Leave its end loose").click()
    expect(page.locator("#board .off-wire.loose")).to_have_count(1)
    expect(page.locator("#board-nets-body .board-progress")).to_contain_text("1 loose")
    page.keyboard.press("Control+z")
    expect(page.locator("#board .off-wire.loose")).to_have_count(0)
    # back to the tray, its wires with it
    vr1.locator(".off-body").click(button="right")
    page.get_by_role("menuitem", name="Back to the tray, with its wires").click()
    expect(vr1).to_have_count(0)
    expect(wires).to_have_count(6)
    expect(page.locator("#board-tray-body li[data-ref='VR1 (Volume)']")).to_be_visible()
    # Wire it for me: VR1 out beside the board again and wired, one undo step
    page.locator("#board-wire").click()
    expect(vr1).to_have_count(1)
    expect_matches(page)
    expect(page.locator("#board-wire")).to_be_hidden()
    page.keyboard.press("Control+z")
    expect(vr1).to_have_count(0)
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")


def test_a_wire_is_moved_by_its_middle_and_routed_for_me_again(page: Page, base_url: str) -> None:
    """D-380: a wire's upright run dragged sideways stays where it's put (one undo step);
    the wire's menu's Route it for me puts it back where the router draws it."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    wire = page.locator("#board .off-wire:has(.wire-run.upright)").first.get_attribute("data-wire")
    run = f"#board .off-wire[data-wire='{wire}'] .wire-run.upright"

    def middle() -> tuple[float, float]:
        """A point on the run with nothing else on top (not where another wire crosses)."""
        box = page.evaluate(
            "(sel) => document.querySelector(sel).getBoundingClientRect().toJSON()", run
        )
        x = box["x"] + box["width"] / 2
        for f in (0.25, 0.75, 0.1, 0.9, 0.5):
            y = box["y"] + box["height"] * f
            on = page.evaluate(
                "([x, y, sel]) => document.elementFromPoint(x, y) === document.querySelector(sel)",
                [x, y, run],
            )
            if on:
                return x, y
        raise AssertionError("the run is covered all along")

    def wait_at(test: str, x: float) -> None:
        page.wait_for_function(
            f"""([sel, x]) => {{ const b = document.querySelector(sel)?.getBoundingClientRect();
                 return b && ({test}); }}""",
            arg=[run, x],
        )

    x, y = middle()
    drag_to(page, (x, y), (x - 40, y))
    wait_at("b.x + b.width / 2 < x - 20", x)
    moved = middle()[0]
    page.keyboard.press("Control+z")
    wait_at("Math.abs(b.x + b.width / 2 - x) < 1", x)
    page.keyboard.press("Control+Shift+z")
    wait_at("Math.abs(b.x + b.width / 2 - x) < 1", moved)
    page.mouse.click(*middle(), button="right")  # the run's hit line is see-through
    page.get_by_role("menuitem", name="Route it for me").click()
    wait_at("Math.abs(b.x + b.width / 2 - x) < 1", x)
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")


def test_a_part_deleted_from_the_schematic_is_flagged_and_cleared(
    page: Page, base_url: str
) -> None:
    """D-376: R2 deleted in the schematic stays on the board, said in Warnings with one
    click to clear; Clear them takes it off as one step of the board's history."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    click_part(page, "R2")
    page.keyboard.press("Delete")
    expect(page.locator('g.part[data-ref="R2"]')).to_have_count(0)
    show_board(page)
    stale = page.locator("#board-warnings-body .board-stale")
    expect(stale).to_contain_text("R2 is no longer in the circuit.")
    expect(page.locator("#board .board-part.stale[data-ref='R2']")).to_have_count(1)
    stale.get_by_role("button", name="Clear them").click()
    expect(page.locator("#board .board-part[data-ref='R2']")).to_have_count(0)
    expect(stale).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(page.locator("#board .board-part.stale[data-ref='R2']")).to_have_count(1)


def test_a_part_placed_finishes_its_nets_and_the_board_is_saved_as_it_was(
    page: Page, base_url: str
) -> None:
    """P6b's tests item and *Accept when*: C3 dragged from the tray finishes its two nets;
    flipped, it's named the wrong way round as it's made; undone; saved, reloaded and
    shown again as it was."""
    board = load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml")
    del board["parts"]["C3"]
    open_with_board(page, base_url, board)
    show_board(page)
    progress = page.locator("#board-nets-body .board-progress")
    warnings = page.locator("#board-warnings-body")
    expect(progress).to_have_text("6 of 8 nets done.")
    tray_c3 = page.locator("#board-tray-body li[data-ref='C3']")
    box = tray_c3.bounding_box()
    assert box
    drag_to(page, (box["x"] + 20, box["y"] + box["height"] / 2), hole_point(page, 5, 2))  # F3
    c3 = page.locator("#board .board-part[data-ref='C3']")
    expect(c3).to_have_count(1)
    expect(progress).to_have_text("All 8 nets done.")
    expect_matches(page)
    # flipped: its legs swap strips, named as it's made
    # by its leg at F3, under a wire across the board: the wire doesn't take the click
    page.mouse.click(*hole_point(page, 5, 2))
    expect(c3).to_have_class(re.compile(r"\bboard-part\b.*\bselected\b"))
    page.keyboard.press("f")
    expect(warnings).to_contain_text("C3 is the wrong way round")
    page.keyboard.press("Control+z")
    expect_matches(page)
    # saved, reloaded: the board as it was
    page.keyboard.press("Control+s")
    expect(page.locator("#dirty")).to_be_hidden()
    page.reload()
    expect(page.locator("#board-button")).to_be_visible()
    show_board(page)
    expect(c3).to_have_count(1)
    expect(page.locator("#board .board-part")).to_have_count(8)
    expect(page.locator("#board-size-text")).to_have_text(
        "12 × 9 holes (30 × 23 mm), 1 cut, 2 links, 9 wires"
    )
    expect(progress).to_have_text("All 8 nets done.")
    expect_matches(page)


def test_the_guidance_marks_suggests_and_says_what_is_next(page: Page, base_url: str) -> None:
    """D-377: the Rangemaster without R3, its cut and links: the tray says R3 is next; the
    ratsnest and the faded cut and links show; a suggested cut clicked is made (an undo
    step), the rest made with one button; a selected part's needs leg by leg; a part
    carried from the tray marks the holes where its legs would join their nets."""
    board = load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml")
    del board["parts"]["R3"]
    board["standing"], board["cuts"], board["links"] = [], [], []
    open_with_board(page, base_url, board)
    show_board(page)
    expect(page.locator("#board-tray-body .board-next")).to_contain_text("Next: R3.")
    expect(page.locator("#board-tray-body li[data-ref='R3']")).to_have_class(re.compile("next"))
    accept = page.locator("#board-accept")
    expect(accept).to_have_text("Make the suggested cut and 2 links")
    suggested = page.locator("#board .suggested")
    expect(suggested).to_have_count(3)
    expect(page.locator("#board .rat")).not_to_have_count(0)
    # one suggested cut clicked: made, one undo step
    page.locator("#board .suggested[data-suggest='cut']").click()
    expect(page.locator("#board .cut")).to_have_count(1)
    expect(accept).to_have_text("Make the suggested 2 links")
    page.keyboard.press("Control+z")
    expect(page.locator("#board .cut")).to_have_count(0)
    # all of them with the button
    accept.click()
    expect(page.locator("#board .cut")).to_have_count(1)
    expect(page.locator("#board .link")).to_have_count(2)
    expect(suggested).to_have_count(0)
    expect(accept).to_be_hidden()
    expect(page.locator("#board .rat")).to_have_count(0)
    # Q1 selected: its needs, leg by leg (its emitter still needs R3)
    page.locator("#board .board-part[data-ref='Q1']").click()
    needs = page.locator("#board-needs")
    expect(needs).to_be_visible()
    expect(needs.locator("li.need").first).to_contain_text("E")
    expect(needs).to_contain_text("R3 leg 1 not placed yet")
    expect(needs).to_contain_text("✓")
    # R3 picked up from the tray: the holes its legs would join are marked
    page.locator("#board-tray-body .board-next").click()
    page.mouse.move(*hole_point(page, 6, 4))
    expect(page.locator("#board .ghost .mark")).not_to_have_count(0)
    page.keyboard.press("Escape")
    expect(page.locator("#board .ghost .mark")).to_have_count(0)


def test_a_part_kept_by_a_placed_pin_is_next_and_marked_by_it(page: Page, base_url: str) -> None:
    """D-400: the Rangemaster with only Q1 placed (E3, B4, C5): the tray names C1 next, on
    the high-gain stage's input, saying why; carried, it's marked only by Q1's base, within
    2 holes either side on its strip (it alone is kept there, R1 and R2 biasing it: C4, D4,
    F4, G4; its other leg's net isn't on the board yet)."""
    board = load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml")
    board["parts"] = {"Q1": board["parts"]["Q1"]}
    board["standing"], board["cuts"], board["links"], board["wires"] = [], [], [], []
    open_with_board(page, base_url, board)
    show_board(page)
    expect(page.locator("#board-tray-body .board-next")).to_contain_text(
        "Next: C1, by Q1's base: the high-gain stage's input."
    )
    page.locator("#board-tray-body .board-next").click()
    page.mouse.move(*hole_point(page, 9, 7))
    expect(page.locator("#board .ghost .mark")).to_have_count(4)
    page.keyboard.press("Escape")


def test_the_realistic_drawing_see_through_and_the_copper_side(page: Page, base_url: str) -> None:
    """D-378: R1's colour bands and C3's stripe drawn, each leg named; See-through makes the
    bodies faint; Hide parts shows the copper side (unmirrored, D-390), and a cut clicked
    there is the cut under it (G8), mended."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    expect(page.locator("#board .board-part[data-ref='R1'] .band")).to_have_count(4)
    expect(page.locator("#board .board-part[data-ref='C3'] .stripe")).to_have_count(1)
    expect(page.locator("#board .board-part[data-ref='Q1'] .leg-name")).to_have_text(
        ["E", "B", "C"]
    )
    page.locator("#board-settings > summary").click()
    page.locator("#board-settings-body input[data-setting='seeThrough']").check()
    expect(page.locator("#board g.board.see-through")).to_have_count(1)
    page.locator("#board-flip").click()
    expect(page.locator("#board-flip")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#board g.board.copper")).to_have_count(1)
    expect(page.locator("#board .board-label").first).to_be_hidden()
    page.keyboard.press("c")
    page.locator("#board .cut").click()
    expect(page.locator("#board .cut")).to_have_count(0)
    page.keyboard.press("Control+z")
    page.locator("#board-flip").click()
    expect(page.locator("#board-flip")).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#board g.board.copper")).to_have_count(0)


def test_a_placed_trimmer_is_made_in_line_from_its_menu(page: Page, base_url: str) -> None:
    """D-393: the Tone Bender (Mode)'s TR1 placed as a triangle (B1, A2, B3); its menu makes
    it an in-line trimmer, back in the tray to place again, one undo step; Undo puts it back."""
    page.goto(base_url)
    circuit = page.request.get(f"{base_url}api/starters/tone-bender-mk2-mode").json()["circuit"]
    circuit["stripboard"] = {"size": [6, 6], "parts": {"TR1": {"1": "B1", "2": "A2", "3": "B3"}}}
    saved = page.request.post(
        f"{base_url}api/circuits", data={"circuit": circuit, "name": "TB trimmer"}
    )
    assert saved.ok, saved.text()
    open_circuit(page, base_url, "circuit/" + saved.json()["circuit"]["id"])
    show_board(page)
    tr1 = page.locator("#board .board-part[data-ref='TR1']")
    expect(tr1).to_have_count(1)
    tr1.click(button="right")
    page.get_by_text("Make it an in-line trimmer").click()
    expect(tr1).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(tr1).to_have_count(1)


def test_hide_parts_shows_the_copper_unmirrored_and_mirror_turns_it_over(
    page: Page, base_url: str
) -> None:
    """D-390 (the user, 2026-11-23): Hide parts shows the copper side as seen from the parts
    side, unmirrored, with its cuts and its links (in their own colour, visible); Mirror on
    the bar turns it over as you hold the board to solder, and turning Mirror on from the
    parts side shows the copper side mirrored; off again, unmirrored."""
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    show_board(page)
    board = page.locator("#board g.board")
    link = page.locator("#board .links .link-end").first  # a line is zero-wide to Playwright
    page.locator("#board-flip").click()  # Hide parts
    expect(page.locator("#board-flip")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#board g.board.copper")).to_have_count(1)
    expect(board).not_to_have_attribute("transform", re.compile("scale"))
    expect(link).to_be_visible()
    expect(page.locator("#board .cut")).to_have_count(1)
    page.locator("#board-mirror").click()
    expect(page.locator("#board-mirror")).to_have_attribute("aria-pressed", "true")
    expect(board).to_have_attribute("transform", re.compile(r"scale\(-1 1\)"))
    expect(link).to_be_visible()
    page.locator("#board-flip").click()  # back to the parts side: never mirrored
    expect(page.locator("#board g.board.copper")).to_have_count(0)
    expect(board).not_to_have_attribute("transform", re.compile("scale"))
    page.locator("#board-mirror").click()  # off
    page.locator("#board-mirror").click()  # on from the parts side: the copper side, mirrored
    expect(page.locator("#board g.board.copper")).to_have_count(1)
    expect(page.locator("#board-flip")).to_have_attribute("aria-pressed", "true")
    expect(board).to_have_attribute("transform", re.compile(r"scale\(-1 1\)"))
    page.locator("#board-mirror").click()
    expect(board).not_to_have_attribute("transform", re.compile("scale"))


def test_a_join_no_link_can_make_is_explained_in_warnings(page: Page, base_url: str) -> None:
    """The base at C4 and J4 on one strip, C2's leg between them (D-377): Warnings says why
    no link can join them and what to move."""
    board = {"size": [12, 9], "cuts": ["D4", "G4", "D8"],
             "parts": {"R1": {"1": "C8", "2": "C4"}, "R2": {"1": "J4", "2": "J8"},
                       "C2": {"1": "F4", "2": "F6"}}}  # fmt: skip
    open_with_board(page, base_url, board)
    show_board(page)
    warning = page.locator("#board-warnings-body li.warning")
    expect(warning).to_contain_text("a link only joins one strip to another")
    expect(warning).to_contain_text("Move C2 off strip 4")


def test_ratsnest_lines_all_or_only_the_part_in_focus(page: Page, base_url: str) -> None:
    """*Ratsnest lines: all* (D-377): on, every strand shows; off, none until a part is
    selected, then that part's nets' strands, lit."""
    board = {"size": [12, 9], "cuts": ["D4", "G4", "D8"],
             "parts": {"R1": {"1": "C8", "2": "C4"}, "R2": {"1": "J4", "2": "J8"},
                       "C2": {"1": "F4", "2": "F6"}}}  # fmt: skip
    open_with_board(page, base_url, board)
    show_board(page)
    line = page.locator("#board line.rat[data-net='Q1.B']")
    found = "document.querySelector(\"#board line.rat[data-net='Q1.B']\")"

    def showing(yes: bool) -> None:  # a level line has no height: Playwright calls it hidden
        page.wait_for_function(
            f"(l => l && (getComputedStyle(l).display {'!' if yes else '='}== 'none'))({found})"
        )

    showing(True)
    page.locator("#board-settings > summary").click()
    box = page.locator("#board-settings-body input[data-setting='rats']")
    expect(box).to_be_checked()
    box.uncheck()
    showing(False)
    page.locator("#board .board-part[data-ref='R1']").click()
    showing(True)
    expect(line).to_have_class(re.compile(r"\blit\b"))
    page.mouse.click(*hole_point(page, 10, 1))  # an empty hole: nothing selected
    showing(False)
    box.check()
    showing(True)


def test_a_part_is_moved_between_the_tray_s_lists_by_choice(page: Page, base_url: str) -> None:
    """D-385: in the tray, R2's button moves it to *Off the board*, marked as the builder's
    choice; dragged back to *On the board*, the choice is gone; a pot's button refuses with
    why; Ctrl+Z undoes a move."""
    open_with_board(page, base_url, {"size": [12, 9]})
    page.locator("#board-button").click()
    r2 = page.locator("#board-tray .tray-section[data-where='board'] li[data-ref='R2']")
    r2.hover()
    r2.locator(".where-move").click()
    off = page.locator("#board-tray-body .off-board li", has_text="R2")
    expect(off).to_contain_text("off the board: your choice")
    expect(r2).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(r2).to_have_count(1)
    page.keyboard.press("Control+Shift+z")
    expect(off).to_have_count(1)
    target = page.locator("#board-tray .tray-section[data-where='board'] h3")
    off.drag_to(target)
    expect(r2).to_have_count(1)
    expect(off).to_have_count(0)
    pot = page.locator("#board-tray-body .off-board li", has_text="VR1")
    pot.hover()
    pot.locator(".where-move").click(force=True)  # greyed, yet a click says why
    expect(page.locator("#refusal")).to_contain_text("There's no board footprint for a pot yet.")


def test_the_kept_board_is_exported_drawn_by_the_board_canvas(page: Page, base_url: str) -> None:
    """P6e (D-386): File → Export's *Stripboard (PDF)* and the package carry the kept board,
    drawn here on paper (parts side with the off-board parts, the board alone, the copper
    side mirrored) with the column letters, without the guidance or grips."""
    from tests.ui.test_editor import menu

    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    target = page.evaluate("() => ({kind: 'circuit', id: location.hash.split('/').pop()})")
    drawn = page.evaluate("async (t) => (await import('/export.js')).boardSvgs(t)", target)
    board = drawn["board"]
    assert set(board) == {"parts", "bare", "copper", "unmirrored"}
    for side in board.values():
        assert 'class="' not in side and "viewBox=" in side and ">F<" in side  # a column letter
        assert "Suggested" not in side and "drag either end" not in side
    assert "VR1" in board["parts"] and "VR1" not in board["bare"]
    assert ">R1<" in board["parts"] and ">R1<" not in board["copper"]  # labels on the parts side
    assert "copper side, mirrored" in board["copper"] and "not mirrored" in board["unmirrored"]
    menu(page, "file-menu", "menu-export")
    sheet = page.locator("#export")
    with page.expect_download() as got:
        sheet.locator("#export-stripboard-pdf").click()
    assert got.value.suggested_filename.endswith("stripboard.pdf")
    with page.expect_download() as got:
        sheet.locator("#export-package").click()
    with zipfile.ZipFile(got.value.path()) as z:
        assert any(n.endswith("/stripboard.pdf") for n in z.namelist())


# A starter whose Start board Tidy up makes smaller (the Rangemaster's no longer: its input
# limit keeps C1 by Q1's base, D-400 amended).
TIDIES = "tone-bender-mk2"


def layout(page: Page, choice: str, compact: bool | None = None) -> None:
    """Open *Layout…* in the board's Settings, pick `choice` (and set *Make the board
    compact*) and press Continue: the confirmation is then showing."""
    settings = page.locator("#board-settings")
    if settings.get_attribute("open") is None:
        settings.locator("summary").click()
    page.locator("#board-layout").click()
    dialog = page.locator("#layout-dialog")
    dialog.locator(f".layout-choice[data-layout='{choice}'] input").check()
    if compact is not None:
        dialog.locator("#layout-compact").set_checked(compact)
    dialog.locator("button[data-answer='go']").click()


def test_the_layout_dialog_starts_fills_and_tidies_each_confirmed_and_one_undo_step(
    page: Page, base_url: str
) -> None:
    """P6h2: *Layout…* in the board's Settings opens the choices; on an empty board Fill the
    rest and Tidy up are greyed with the reason and Start a board is chosen. Each choice
    is confirmed, saying what will happen; each is one undo step. Once parts are placed
    nothing is chosen at first and Continue waits for a choice. On the Tone Bender MK2
    Start a board without *Make the board compact* lays out 34 columns, Tidy up makes them
    30 (D-388); Start a board on a board with parts names what it replaces, and Cancel
    changes nothing."""
    open_with_board(page, base_url, None, TIDIES)
    page.locator("#board-button").click()
    page.locator("#board-settings summary").click()
    page.locator("#board-layout").click()
    dialog = page.locator("#layout-dialog")
    for greyed in ("fill", "tidy"):
        row = dialog.locator(f".layout-choice[data-layout='{greyed}']")
        expect(row.locator("input")).to_be_disabled()
        expect(row).to_contain_text("Nothing is placed yet")
    expect(dialog.locator(".layout-choice[data-layout='start'] input")).to_be_checked()
    dialog.locator("#layout-compact").set_checked(False)
    dialog.locator("button[data-answer='go']").click()
    expect(page.locator(".ask-text")).to_contain_text("Lays out the whole board: 14 parts")
    page.locator(".ask-buttons button[data-answer='layout']").click()
    size = page.locator("#board-size-text")
    expect(size).to_contain_text("34 × 13 holes")
    layout(page, "tidy")
    expect(page.locator(".ask-text")).to_contain_text("make the board smaller")
    page.locator(".ask-buttons button[data-answer='layout']").click()
    expect(size).to_contain_text("30 × 13 holes")
    page.locator("#board-layout").click()  # parts placed: nothing chosen, Continue waits
    expect(dialog.locator("input[name='layout']:checked")).to_have_count(0)
    expect(dialog.locator("button[data-answer='go']")).to_be_disabled()
    expect(dialog.locator(".layout-choice[data-layout='start']")).to_contain_text("Start over")
    dialog.locator(".layout-choice[data-layout='start'] input").check()
    dialog.locator("button[data-answer='go']").click()
    expect(page.locator(".ask-text")).to_contain_text(
        "This replaces everything on the board: 14 parts,"
    )
    expect(page.locator(".ask-buttons button[data-answer='layout']")).to_have_text(
        "Replace the board"
    )
    page.locator(".ask-buttons button[data-answer='cancel']").click()
    expect(size).to_contain_text("30 × 13 holes")
    page.keyboard.press("Control+z")  # the tidy: one step
    expect(size).to_contain_text("34 × 13 holes")
    page.keyboard.press("Control+z")  # the layout: one step
    expect(size).to_have_text("Empty board")


def test_the_layout_dialog_s_standing_choice_is_kept_with_the_board(
    page: Page, base_url: str
) -> None:
    """D-403: the dialog's last line, Standing resistors and diodes, opens on the board's
    own choice (When needed on a new board). Start a board with Prefer stands the
    Fuzz Face's resistors (10 × 6 for 10 × 10 flat) and the board keeps the choice: the
    dialog opens on Prefer next time; Never then lays everything flat again."""
    open_with_board(page, base_url, None, "fuzz-face")
    page.locator("#board-button").click()
    page.locator("#board-settings summary").click()
    page.locator("#board-layout").click()
    dialog = page.locator("#layout-dialog")
    expect(dialog.locator(".layout-standing")).to_contain_text("Standing resistors and diodes")
    expect(dialog.locator("input[name='layout-stand'][value='needed']")).to_be_checked()
    dialog.locator("input[name='layout-stand'][value='prefer']").check()
    dialog.locator("#layout-compact").set_checked(False)
    dialog.locator("button[data-answer='go']").click()
    page.locator(".ask-buttons button[data-answer='layout']").click()
    size = page.locator("#board-size-text")
    expect(size).to_contain_text("10 × 6 holes")
    page.locator("#board-layout").click()
    expect(dialog.locator("input[name='layout-stand'][value='prefer']")).to_be_checked()
    dialog.locator(".layout-choice[data-layout='start'] input").check()
    dialog.locator("input[name='layout-stand'][value='never']").check()
    dialog.locator("button[data-answer='go']").click()
    page.locator(".ask-buttons button[data-answer='layout']").click()
    expect(size).to_contain_text("10 × 10 holes")


def test_the_tray_shows_the_placed_parts_on_request(page: Page, base_url: str) -> None:
    """D-387: once laid out, the tray lists the placed parts (on the board and beside it)
    under *Show placed*, above its lists; a click selects one."""
    open_with_board(page, base_url, None, TIDIES)
    page.locator("#board-button").click()
    layout(page, "start", compact=True)
    page.locator(".ask-buttons button[data-answer='layout']").click()
    expect(page.locator("#board-size-text")).to_contain_text("30 × 13 holes")
    toggle = page.locator("#board-tray .placed-toggle")
    expect(toggle).to_have_text("▸ Show placed (19)")  # 14 on the board, 5 beside it
    expect(page.locator("#board-tray li.placed")).to_have_count(0)
    toggle.click()
    expect(page.locator("#board-tray li.placed")).to_have_count(19)
    on_list = page.locator("#board-tray .tray-section[data-where='board']")
    assert toggle.bounding_box()["y"] < on_list.bounding_box()["y"]  # above the lists
    page.locator("#board-tray li.placed[data-ref='R1']").click()
    expect(page.locator("#board .board-part[data-ref='R1']")).to_have_class(re.compile("selected"))


def test_the_layout_says_what_its_doing_while_it_works(page: Page, base_url: str) -> None:
    """A big board takes seconds to tidy (D-388): while it does, the Layout button says so
    and can't be pressed again, and the working bar shows."""
    held: list[Route] = []
    page.route("**/api/stripboard/tidy", lambda route: held.append(route))
    open_with_board(page, base_url, None, TIDIES)
    page.locator("#board-button").click()
    layout(page, "start", compact=True)
    page.locator(".ask-buttons button[data-answer='layout']").click()
    button = page.locator("#board-layout")
    expect(button).to_have_text("Tidying…")
    expect(button).to_be_disabled()
    expect(page.locator("#board-working")).to_be_visible()
    held[0].continue_()
    expect(page.locator("#board-size-text")).to_contain_text("30 × 13 holes")
    expect(page.locator("#board-working")).to_be_hidden()
    expect(button).to_have_text("Layout…")


def open_overlapping(page: Page, base_url: str) -> None:
    """D-394's case (`tests/fixtures/circuits/old/schema-v39.json`): trimmer TR1 and
    electrolytic C1 whose bodies touch, saved and opened in the Board view."""
    page.goto(base_url)
    circuit = json.loads((REPO / "tests/fixtures/circuits/old/schema-v39.json").read_text())
    made = {"circuit": circuit, "name": f"Overlapping {next(_saves)}"}
    saved = page.request.post(f"{base_url}api/circuits", data=made)
    assert saved.ok, saved.text()
    open_circuit(page, base_url, "circuit/" + saved.json()["circuit"]["id"])
    show_board(page)


def test_an_overlap_is_noted_dismissed_brought_back_and_marked(
    page: Page, base_url: str, browser_errors: list[str]
) -> None:
    """D-398: the warning with no amount, its mark on the board (a click opens its row);
    Note… writes a note about the two, kept in the board's Notes pane; moving C1 away puts
    the note out of date (Undo: back); Dismiss… hides the warning and its mark, Bring back
    shows it; View → Problem marks hides the board's marks; a general note added, edited,
    deleted; each step undone by the board's own Undo."""
    open_overlapping(page, base_url)
    warning = page.locator("#board-warnings-body li.overlap")
    expect(warning).to_contain_text("TR1 and C1's bodies touch: move one a hole further away")
    mark = page.locator("#board .board-marks .problem-mark")
    expect(mark).to_have_count(1)
    mark.click()
    expect(warning).to_have_class(re.compile(r"\bflash\b"))

    # a note from the warning: Parts filled in
    warning.get_by_role("button", name="Note…").click()
    expect(page.locator("#field-parts")).to_have_value("TR1, C1")
    page.locator("#field-text").fill("Solder C1 a little higher.")
    page.get_by_role("button", name="Save").click()
    note = page.locator("#board-notes-body .board-note").first
    expect(note).to_have_text(re.compile(r"^TR1, C1: Solder C1 a little higher\."))
    expect(page.locator("#board-notes-count")).to_have_text("· 1")
    expect(warning).to_have_count(1)  # a note doesn't dismiss

    # C1 moved a column away: they no longer touch, the note is out of date; Undo: back
    page.locator("#board .board-part[data-ref='C1']").click()
    drag_to(page, hole_point(page, 3, 0), hole_point(page, 4, 0))
    expect(note).to_have_class(re.compile(r"\bout-of-date\b"))
    expect(note).to_contain_text("(TR1 and C1 no longer touch)")
    expect(warning).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(note).not_to_have_class(re.compile(r"\bout-of-date\b"))

    # dismissed with a reason: no warning, no mark; brought back
    warning.get_by_role("button", name="Dismiss…").click()
    page.locator("#field-reason").fill("Low trimmer")
    page.get_by_role("button", name="Dismiss", exact=True).click()
    expect(warning).to_have_count(0)
    expect(mark).to_have_count(0)
    gone = page.locator("#board-warnings-body .dismissed li")
    expect(gone).to_contain_text("(Low trimmer)")
    gone.get_by_role("button", name="Bring back").click()
    expect(warning).to_have_count(1)
    expect(mark).to_have_count(1)

    # View → Problem marks hides the board's marks too
    menu(page, "view-menu", "menu-marks")
    expect(mark).to_have_count(0)
    menu(page, "view-menu", "menu-marks")
    expect(mark).to_have_count(1)

    # a general note, edited (its refs kept), then deleted; Undo brings it back
    page.locator("#board-notes-add").click()
    page.locator("#field-text").fill("Socket nothing.")
    page.get_by_role("button", name="Save").click()
    general = page.locator("#board-notes-body .board-note").nth(1)
    expect(general).to_have_text(re.compile(r"^Socket nothing\."))
    note.get_by_role("button", name="Edit…").click()
    expect(page.locator("#field-parts")).to_have_value("TR1, C1")
    page.locator("#field-text").fill("Higher.")
    page.get_by_role("button", name="Save").click()
    expect(note).to_have_text(re.compile(r"^TR1, C1: Higher\."))
    general.get_by_role("button", name="Delete").click()
    expect(page.locator("#board-notes-body .board-note")).to_have_count(1)
    page.keyboard.press("Control+z")
    expect(page.locator("#board-notes-body .board-note")).to_have_count(2)

    # a ref the board hasn't is refused in the form
    page.locator("#board-notes-add").click()
    page.locator("#field-parts").fill("R9")
    page.locator("#field-text").fill("x")
    page.get_by_role("button", name="Save").click()
    expect(page.locator("form.popup .error")).to_have_text("There's no R9 among the board's parts.")
    browser_errors.clear()  # that refusal's 422


def test_build_a_full_layout_reviewed_tried_again_kept_and_undone(
    page: Page, base_url: str
) -> None:
    """D-399: *Build a full layout* on the Rangemaster's empty board, Quick, its time
    worked out; the running window, then the review bar: After | Before | Both (top and
    bottom), Try another and back to try 1, Keep try 1 (one undo step). Then Thorough,
    stopped early: its best kept for the review, and the old board kept."""
    open_with_board(page, base_url, None)
    page.locator("#board-button").click()
    page.locator("#board-settings summary").click()
    page.locator("#board-layout").click()
    dialog = page.locator("#layout-dialog")
    expect(dialog.locator("input[name='layout-speed']").first).to_be_disabled()
    dialog.locator(".layout-choice[data-layout='full'] input").check()
    dialog.locator("input[name='layout-speed'][value='quick']").check()
    expect(dialog.locator(".layout-time[data-time='quick']")).not_to_contain_text("Working out")
    expect(dialog).to_contain_text("Check it, and adjust it if you need to")
    dialog.locator("button[data-answer='go']").click()
    expect(page.locator(".ask-text")).to_contain_text("you can stop early")
    page.locator(".ask-buttons button[data-answer='layout']").click()
    review = page.locator(".compact-review")
    expect(review).to_be_visible(timeout=90_000)
    expect(page.locator(".compact-run")).to_be_hidden()
    expect(review.locator(".compact-figures")).to_contain_text("→ After")
    expect(review.locator("[data-review='old']")).to_have_text("Keep the base board")
    expect(page.locator("#board-tray")).to_have_js_property("inert", True)
    review.locator("[data-mode='both']").click()
    expect(page.locator("#canvas-body")).to_have_class(re.compile("split"))
    expect(page.locator(".board-before")).to_be_visible()
    expect(page.locator(".compact-title.bottom")).to_contain_text("After, try 1")
    review.locator("[data-mode='before']").click()
    expect(page.locator(".board-before")).to_be_hidden()
    review.locator("[data-mode='after']").click()
    review.locator("[data-review='another']").click()
    expect(review.locator(".compact-try")).to_have_text("Try 2 of 2", timeout=90_000)
    review.locator("[data-try='prev']").click()
    expect(review.locator(".compact-try")).to_have_text("Try 1 of 2")
    review.locator("[data-review='keep']").click()
    expect(review).to_be_hidden()
    expect(page.locator("#board .board-part")).to_have_count(8)
    expect(page.locator("#board-tray")).to_have_js_property("inert", False)
    kept = page.locator("#board-size-text").inner_text()
    page.keyboard.press("Control+z")
    expect(page.locator("#board .board-part")).to_have_count(0)
    page.keyboard.press("Control+Shift+z")
    expect(page.locator("#board-size-text")).to_have_text(kept)
    # Thorough, stopped early: the best so far wired and checked, then the old board kept
    page.locator("#board-layout").click()
    dialog.locator(".layout-choice[data-layout='full'] input").check()
    dialog.locator("input[name='layout-speed'][value='thorough']").check()
    dialog.locator("button[data-answer='go']").click()
    expect(page.locator(".ask-text")).to_contain_text("replaces everything on the board: 8 parts")
    page.locator(".ask-buttons button[data-answer='layout']").click()
    stop = page.locator(".compact-run [data-run='stop']")
    expect(stop).to_be_enabled(timeout=60_000)
    expect(page.locator("#board")).to_have_class(re.compile("dimmed"))
    stop.click()
    expect(review).to_be_visible(timeout=30_000)
    expect(review.locator("[data-review='old']")).to_have_text("Keep the old board")
    review.locator("[data-review='old']").click()
    expect(review).to_be_hidden()
    expect(page.locator("#board-size-text")).to_have_text(kept)
