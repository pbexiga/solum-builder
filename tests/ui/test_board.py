"""P6b (D-368): the Board view in a real browser, on the Rangemaster with its hand-made
board (`tests/fixtures/stripboard/rangemaster.yaml`): the toggle, the board drawn, its own
panes in the column, the selection lit on both drawings, the result panes back after."""

import itertools
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from solum.yamlio import load_yaml
from tests.ui.conftest import REPO, open_circuit
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
    page.locator("#show-board").click()
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
    expect(page.locator("#board-size")).to_have_text("12 × 9, 1 cut, 2 links")
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
    page.locator("#show-schematic").click()
    expect(page.locator("aside.panels")).to_be_visible()
    expect(page.locator("#board")).to_be_hidden()
    expect(page.locator("#board-panels")).to_be_hidden()
    assert pane_ids(page) == results
    expect(page.locator("#schematic .part[data-ref='R2']")).to_have_class("part selected")


def test_a_circuit_without_a_board_shows_its_parts_to_place(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, None)
    page.locator("#show-board").click()
    expect(page.locator("#board-size")).to_have_text("Empty board")
    # the 8 board parts, then the 7 off-board wire ends (VR1's lugs, the supply, IN, OUT)
    expect(page.locator("#board-tray-body li")).to_have_count(15)
    expect(page.locator("#board-tray-body li", has_text="off-board wire")).to_have_count(7)
    expect(page.locator("#board-tray-body li[data-ref='Q1']")).to_contain_text("in a line")
    expect(page.locator("#board-nets-body .board-progress")).to_have_text("0 of 8 nets done.")


def test_the_board_panes_keep_their_own_order(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, None)
    page.locator("#show-board").click()
    ids = page.eval_on_selector_all("#board-panels > details", "(ds) => ds.map((d) => d.id)")
    assert ids == [
        "board-schematic",
        "board-tray",
        "board-nets",
        "board-warnings",
        "board-settings",
    ]
    grip = page.locator("[data-grip='board-nets']")
    grip.focus()
    grip.press("ArrowUp")
    moved = page.eval_on_selector_all("#board-panels > details", "(ds) => ds.map((d) => d.id)")
    assert moved == [
        "board-schematic",
        "board-nets",
        "board-tray",
        "board-warnings",
        "board-settings",
    ]
    # the result panes' order is its own
    page.locator("#show-schematic").click()
    assert pane_ids(page)[0] == "panel-problems"
