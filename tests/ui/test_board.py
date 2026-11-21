"""P6b (D-368): the Board view in a real browser, on the Rangemaster with its hand-made
board (`tests/fixtures/stripboard/rangemaster.yaml`): the toggle, the board drawn, its own
panes in the column, the selection lit on both drawings, the result panes back after; the
Board button (D-370)."""

import itertools
import re
import zipfile
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
    size = "12 × 9 holes (30 × 23 mm), 1 cut, 2 links, 9 wires"
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
    warnings = page.locator("#board-warnings-body")
    expect(warnings).to_have_text("The board matches the circuit.")
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
    # moved by dragging its body: J to L
    drag_to(page, hole_point(page, 9, 5), hole_point(page, 11, 5))
    expect(r2.locator(".leg").first).to_have_attribute("cx", "110")
    expect(warnings).to_have_text("The board matches the circuit.")
    # a cut made and mended with the Cuts tool, a link laid with the Links tool
    page.keyboard.press("c")
    page.mouse.click(*hole_point(page, 9, 4))
    expect(page.locator("#board .cut[data-hole='J5']")).to_have_count(1)
    page.mouse.click(*hole_point(page, 9, 4))
    expect(page.locator("#board .cut[data-hole='J5']")).to_have_count(0)
    page.keyboard.press("k")
    drag_to(page, hole_point(page, 9, 1), hole_point(page, 9, 7))  # J2 to J8, both GND
    expect(page.locator("#board .board-link")).to_have_count(3)
    expect(warnings).to_have_text("The board matches the circuit.")
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
    warnings = page.locator("#board-warnings-body")
    expect(warnings).to_have_text("The board matches the circuit.")
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
    expect(warnings).to_have_text("The board matches the circuit.")
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
    drag_to(page, (box["x"] + 20, box["y"] + box["height"] / 2), hole_point(page, 7, 2))  # H3
    c3 = page.locator("#board .board-part[data-ref='C3']")
    expect(c3).to_have_count(1)
    expect(progress).to_have_text("All 8 nets done.")
    expect(warnings).to_have_text("The board matches the circuit.")
    # flipped: its legs swap strips, named as it's made
    # by its leg at H3, under a wire across the board: the wire doesn't take the click
    page.mouse.click(*hole_point(page, 7, 2))
    expect(c3).to_have_class(re.compile(r"\bboard-part\b.*\bselected\b"))
    page.keyboard.press("f")
    expect(warnings).to_contain_text("C3 is the wrong way round")
    page.keyboard.press("Control+z")
    expect(warnings).to_have_text("The board matches the circuit.")
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
    expect(warnings).to_have_text("The board matches the circuit.")


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


def test_the_realistic_drawing_see_through_and_the_copper_side(page: Page, base_url: str) -> None:
    """D-378: R1's colour bands and C3's stripe drawn, each leg named; See-through makes the
    bodies faint; Copper side turns the board over, mirrored, and a cut clicked there is the
    cut under it (G8), mended."""
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
    assert set(board) == {"parts", "bare", "copper"}
    for side in board.values():
        assert 'class="' not in side and "viewBox=" in side and ">F<" in side  # a column letter
        assert "Suggested" not in side and "drag either end" not in side
    assert "VR1" in board["parts"] and "VR1" not in board["bare"]
    assert ">R1<" in board["parts"] and ">R1<" not in board["copper"]  # labels on the parts side
    menu(page, "file-menu", "menu-export")
    sheet = page.locator("#export")
    with page.expect_download() as got:
        sheet.locator("#export-stripboard-pdf").click()
    assert got.value.suggested_filename.endswith("stripboard.pdf")
    with page.expect_download() as got:
        sheet.locator("#export-package").click()
    with zipfile.ZipFile(got.value.path()) as z:
        assert any(n.endswith("/stripboard.pdf") for n in z.namelist())


def test_start_for_me_sits_in_the_tray_and_the_placed_parts_show_on_request(
    page: Page, base_url: str
) -> None:
    """D-387: *Start for me* at the top of the tray lays an empty board out; the tray then
    lists the placed parts (on the board and beside it) under *Show placed*, above its
    lists; a click selects one."""
    open_with_board(page, base_url, None)
    page.locator("#board-button").click()
    start = page.locator("#board-tray #board-start")
    expect(start).to_be_visible()
    start.click()
    expect(page.locator("#board .board-part").first).to_be_visible()
    expect(start).to_be_hidden()  # the board passes: nothing left to do
    toggle = page.locator("#board-tray .placed-toggle")
    expect(toggle).to_have_text("▸ Show placed (12)")  # 8 on the board, 4 beside it
    expect(page.locator("#board-tray li.placed")).to_have_count(0)
    toggle.click()
    expect(page.locator("#board-tray li.placed")).to_have_count(12)
    on_list = page.locator("#board-tray .tray-section[data-where='board']")
    assert toggle.bounding_box()["y"] < on_list.bounding_box()["y"]  # above the lists
    page.locator("#board-tray li.placed[data-ref='R1']").click()
    expect(page.locator("#board .board-part[data-ref='R1']")).to_have_class(re.compile("selected"))
