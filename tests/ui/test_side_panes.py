"""P7b (D-408): side panes that hide, in the Schematic and the Board view. Either side
hides and comes back (its key, View's items, its bar at the window's edge; resting on a
hidden side's bar peeks it out over the drawing, its own large view tucked away, and a click
pins it), the drawing staying where it was on screen; remembered after a
reload, per view; an expanded pane stays out when its column hides, and its Collapse shows
the column; a review opening shows the board's hidden right column, which can be hidden
again."""

import re

import pytest
from playwright.sync_api import Page, expect

from solum.yamlio import load_yaml
from tests.ui.conftest import REPO, open_circuit, part_pos, reload_kept, to_screen
from tests.ui.test_board import expect_matches, open_with_board
from tests.ui.test_editor import menu

pytestmark = pytest.mark.ui

HIDDEN = re.compile(r"\bside-hidden\b")


def canvas_width(page: Page) -> float:
    return float(page.locator("section.canvas").bounding_box()["width"])  # type: ignore[index]


def board_x(page: Page, ref: str) -> float:
    box = page.locator(f'#board .board-part[data-ref="{ref}"]').bounding_box()
    assert box
    return float(box["x"])


def test_the_schematic_sides_hide_and_come_back(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    results = page.locator("aside.panels")
    where = to_screen(page, *part_pos(page, "Q1"))
    width = canvas_width(page)
    page.keyboard.press("]")
    expect(results).to_have_class(HIDDEN)
    expect(results).to_be_hidden()
    assert canvas_width(page) == pytest.approx(width + 440, abs=1)
    assert to_screen(page, *part_pos(page, "Q1")) == pytest.approx(where, abs=0.5)
    bar = page.locator(".side-bar.right")
    expect(bar).to_be_visible()
    expect(bar).to_have_attribute("title", "Show the results (])")
    expect(page.locator(".side-bar.left")).to_have_attribute("title", "Hide the parts ([)")

    # the left side too, from View's menu: the drawing still in place
    menu(page, "view-menu", "menu-side-left")
    expect(page.locator("#palette")).to_have_class(HIDDEN)
    assert canvas_width(page) == pytest.approx(width + 440 + 184, abs=1)
    assert to_screen(page, *part_pos(page, "Q1")) == pytest.approx(where, abs=0.5)
    page.locator("#view-menu").click()
    expect(page.locator("#menu-side-left")).to_contain_text("Show left pane")
    page.keyboard.press("Escape")

    # remembered after a reload
    reload_kept(page)
    expect(results).to_have_class(HIDDEN)
    expect(page.locator("#palette")).to_have_class(HIDDEN)

    # the edge tabs bring them back, pinned in place
    page.locator(".side-bar.left").click()
    page.locator(".side-bar.right").click()
    expect(results).not_to_have_class(HIDDEN)
    expect(results).to_be_in_viewport()
    expect(page.locator(".side-bar.right")).to_have_attribute("aria-expanded", "true")
    assert canvas_width(page) == pytest.approx(width, abs=1)


def test_the_board_view_keeps_its_own_sides(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, load_yaml(REPO / "tests/fixtures/stripboard/rangemaster.yaml"))
    page.locator("#board-button").click()
    expect_matches(page)  # checked, so drawn and fitted
    x = board_x(page, "R1")
    page.keyboard.press("[")
    expect(page.locator("#board-tray")).to_have_class(HIDDEN)
    assert board_x(page, "R1") == pytest.approx(x, abs=0.5)  # the board didn't move
    expect(page.locator(".side-bar.left")).to_have_attribute("title", "Show the tray ([)")
    # the Schematic view's palette is its own: still shown there
    page.locator("#board-button").click()
    expect(page.locator("#palette")).not_to_have_class(HIDDEN)
    expect(page.locator(".side-bar.left")).to_have_attribute("title", "Hide the parts ([)")
    page.locator("#board-button").click()
    expect(page.locator(".side-bar.left")).to_have_attribute("title", "Show the tray ([)")
    page.locator(".side-bar.left").click()
    expect(page.locator("#board-tray")).not_to_have_class(HIDDEN)
    assert board_x(page, "R1") == pytest.approx(x, abs=0.5)


def test_a_large_view_stays_out_and_its_collapse_shows_the_column(
    page: Page, base_url: str
) -> None:
    open_circuit(page, base_url, "ts808")
    frequency = page.locator("#panel-frequency")
    page.locator("#frequency-expand").click()
    expect(frequency).to_have_class(re.compile(r"\blarge-view\b"))
    box = frequency.bounding_box()
    page.keyboard.press("]")
    expect(page.locator("aside.panels")).to_have_class(HIDDEN)
    expect(frequency).to_be_visible()
    assert frequency.bounding_box() == box  # as it was: placed against the window
    page.locator("#frequency-expand").click()  # Collapse: back in its column, shown first
    expect(page.locator("aside.panels")).not_to_have_class(HIDDEN)
    expect(frequency).not_to_have_class(re.compile(r"\blarge-view\b"))
    expect(frequency).to_be_in_viewport()


def test_a_review_shows_the_hidden_right_column_once(page: Page, base_url: str) -> None:
    open_with_board(page, base_url, None)
    page.locator("#board-button").click()
    column = page.locator("#board-panels")
    page.locator("#board-settings summary").click()
    page.locator("#board-layout").click()
    dialog = page.locator("#layout-dialog")
    expect(dialog.locator(".layout-takes")).not_to_contain_text("Working out")
    dialog.locator("button[data-answer='layout']").click()
    expect(page.locator(".compact-run")).to_be_visible()
    page.keyboard.press("]")  # hidden while it runs
    expect(column).to_have_class(HIDDEN)
    review = page.locator(".compact-review")
    expect(review).to_be_attached(timeout=90_000)
    expect(page.locator(".compact-run")).to_be_hidden(timeout=90_000)
    # the review opened: the column shown, so its result is seen
    expect(column).not_to_have_class(HIDDEN)
    expect(review).to_be_visible()
    # hidden again during the review; the tab says what it brings back
    page.keyboard.press("]")
    expect(column).to_have_class(HIDDEN)
    expect(page.locator("section.canvas")).to_have_class(re.compile(r"\breviewing\b"))
    bar = page.locator(".side-bar.right")
    expect(bar).to_have_attribute("title", "Show the review (])")
    bar.click()
    expect(column).not_to_have_class(HIDDEN)
    expect(review).to_be_visible()


def bar_point(page: Page, side: str) -> tuple[float, float]:
    """The middle of a side's bar, a quarter of the way down."""
    box = page.locator(f".side-bar.{side}").bounding_box()
    assert box
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 4


def test_the_bar_hides_and_peeks(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    results = page.locator("aside.panels")
    bar = page.locator(".side-bar.right")
    expect(bar).to_have_attribute("aria-expanded", "true")
    expect(bar).to_have_attribute("title", "Hide the results (])")
    where = to_screen(page, *part_pos(page, "Q1"))
    width = canvas_width(page)
    # resting on a shown side's bar doesn't peek
    page.mouse.move(*bar_point(page, "right"))
    page.wait_for_timeout(400)
    expect(results).not_to_have_class(re.compile(r"\bside-peek\b"))
    bar.click()
    expect(results).to_have_class(HIDDEN)
    expect(results).to_be_hidden()
    expect(bar).to_have_attribute("aria-expanded", "false")
    expect(bar).to_have_attribute("title", "Show the results (])")
    wide = canvas_width(page)
    assert wide == pytest.approx(width + 440, abs=1)

    # resting on the hidden side's bar slides it out over the drawing, which doesn't move
    page.mouse.move(400, 400)
    page.mouse.move(*bar_point(page, "right"))
    expect(results).to_have_class(re.compile(r"\bside-peek\b"))
    expect(results).to_be_in_viewport()
    assert canvas_width(page) == pytest.approx(wide, abs=1)
    assert to_screen(page, *part_pos(page, "Q1")) == pytest.approx(where, abs=0.5)
    expect(bar).to_have_attribute("title", "Pin the results (])")
    # the bar stays above the peeking column, so it keeps the pointer
    x, y = bar_point(page, "right")
    hit = page.evaluate(f"document.elementFromPoint({x}, {y}).className")
    assert "side-bar" in hit
    # leaving it slides it back
    page.mouse.move(400, 400)
    expect(results).not_to_have_class(re.compile(r"\bside-peek\b"))
    expect(results).to_be_hidden()

    # peeked again and pinned by a click on the bar: back in its column, the drawing still
    page.mouse.move(*bar_point(page, "right"))
    expect(results).to_have_class(re.compile(r"\bside-peek\b"))
    bar.click()
    expect(results).not_to_have_class(HIDDEN)
    expect(results).not_to_have_class(re.compile(r"\bside-peek\b"))
    assert canvas_width(page) == pytest.approx(width, abs=1)
    assert to_screen(page, *part_pos(page, "Q1")) == pytest.approx(where, abs=0.5)
    expect(bar).to_have_attribute("aria-expanded", "true")


def test_a_peek_slides_back_above_the_canvas_on_either_side(page: Page, base_url: str) -> None:
    """D-408: the pointer off a peeking column, it slides back still drawn over the canvas.
    The left column comes before the canvas in the page, so it went under it at once."""
    open_circuit(page, base_url, "ts808")
    for side, column in (("left", "#palette"), ("right", "aside.panels")):
        bar = page.locator(f".side-bar.{side}")
        bar.click()
        page.mouse.move(700, 400)
        page.wait_for_timeout(400)  # hidden
        bar.hover()
        expect(page.locator(column)).to_have_class(re.compile("side-peek"))
        page.wait_for_timeout(400)  # slid out
        page.mouse.move(700, 400)
        page.wait_for_function(  # the frame it starts sliding back
            "(sel) => !document.querySelector(sel).classList.contains('side-peek')",
            arg=column,
            polling="raf",
        )
        page.wait_for_timeout(40)
        on_top = page.evaluate(
            """(sel) => { const el = document.querySelector(sel);
              const r = el.getBoundingClientRect();
              const x = Math.min(Math.max(r.x + r.width / 2, 20), innerWidth - 20);
              return el.contains(document.elementFromPoint(x, r.y + 120)); }""",
            column,
        )
        assert on_top, f"the {side} column went under the canvas"
        page.wait_for_timeout(400)
        bar.click()
        page.mouse.move(700, 400)


def test_a_peek_covers_its_own_large_view(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    frequency = page.locator("#panel-frequency")
    page.locator("#frequency-expand").click()
    expect(frequency).to_have_class(re.compile(r"\blarge-view\b"))
    page.keyboard.press("]")
    expect(page.locator("aside.panels")).to_have_class(HIDDEN)
    expect(frequency).to_be_visible()  # out as it was
    page.mouse.move(*bar_point(page, "right"))
    expect(page.locator("aside.panels")).to_have_class(re.compile(r"\bside-peek\b"))
    expect(frequency).to_be_hidden()  # tucked away while its column peeks over everything
    page.mouse.move(400, 400)
    expect(page.locator("aside.panels")).not_to_have_class(re.compile(r"\bside-peek\b"))
    expect(frequency).to_be_visible()


def test_a_drag_reaching_the_bar_does_not_peek(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    page.keyboard.press("[")
    palette = page.locator("#palette")
    expect(palette).to_have_class(HIDDEN)
    box = page.locator("section.canvas").bounding_box()
    assert box
    page.mouse.move(box["x"] + 300, box["y"] + 60)
    page.mouse.down()
    page.mouse.move(*bar_point(page, "left"), steps=5)
    page.wait_for_timeout(500)  # longer than the bar's rest before a peek
    expect(palette).not_to_have_class(re.compile(r"\bside-peek\b"))
    page.mouse.up()


def test_a_palette_group_folds_and_stays_folded(page: Page, base_url: str) -> None:
    open_circuit(page, base_url, "ts808")
    passive = page.locator("#palette .palette-group[data-group='Passive']")
    resistor = page.locator("#palette [data-place='resistor']")
    expect(passive).to_have_attribute("open", "")
    expect(resistor).to_be_visible()
    passive.locator("summary").click()
    expect(resistor).to_be_hidden()
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")
    open_circuit(page, base_url, "ts808")  # kept with the layout preferences (D-311)
    expect(page.locator("#palette [data-place='resistor']")).to_be_hidden()
    page.locator("#palette .palette-group[data-group='Passive'] summary").click()
    expect(page.locator("#palette [data-place='resistor']")).to_be_visible()


def test_a_side_column_s_scroll_bar_shows_only_while_hovered(page: Page, base_url: str) -> None:
    """D-409: shown while the pointer is over the column, fading in and out (0.25 s)."""
    open_circuit(page, base_url, "ts808")
    colour = "getComputedStyle(document.getElementById('palette')).scrollbarColor"
    page.mouse.move(800, 400)
    page.wait_for_function(f"{colour}.startsWith('rgba(0, 0, 0, 0)')")
    page.locator("#palette").hover()
    page.wait_for_function(f"!{colour}.startsWith('rgba(0, 0, 0, 0)')")
