"""Reorderable result panes (Phase 8 part 4): drag a pane's grip or use the arrow keys;
the order, each pane open or shut, and the list's scroll survive a reload (D-121); View →
Reset pane order brings back the default order with every pane open but DC, which always
starts shut."""

import re

from playwright.sync_api import Page, expect

from tests.ui.conftest import open_circuit, reload_kept, run, wait_for_update
from tests.ui.test_editor import menu

DEFAULT = [
    "panel-problems", "panel-notes", "panel-dc", "panel-probe", "panel-frequency",
    "panel-stages", "panel-scope", "panel-harmonics", "panel-knobs", "panel-audio",
]  # fmt: skip


def order(page: Page) -> list[str]:
    return list(page.eval_on_selector_all(".panels > details", "(ds) => ds.map((d) => d.id)"))


def drag_grip(page: Page, pane: str, onto: str) -> None:
    """Drag `pane` by its grip to just above `onto`'s heading."""
    grip = page.locator(f'[data-grip="{pane}"]').bounding_box()
    target = page.locator(f"#{onto} > summary").bounding_box()
    assert grip is not None and target is not None
    page.mouse.move(grip["x"] + grip["width"] / 2, grip["y"] + grip["height"] / 2)
    page.mouse.down()
    page.mouse.move(target["x"] + 40, target["y"] + 4, steps=10)
    page.mouse.up()


def test_drag_a_pane_and_reset(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    assert order(page) == DEFAULT
    page.evaluate("document.querySelector('#panel-knobs').scrollIntoView()")
    drag_grip(page, "panel-knobs", "panel-frequency")
    moved = ["panel-problems", "panel-notes", "panel-dc", "panel-probe", "panel-knobs",
             "panel-frequency", "panel-stages", "panel-scope", "panel-harmonics",
             "panel-audio"]  # fmt: skip
    assert order(page) == moved
    # dragging by the grip never opens or shuts a pane
    assert page.eval_on_selector("#panel-knobs", "(d) => d.open")
    page.locator("#panel-scope > summary").click()  # shut one
    reload_kept(page)
    open_circuit(page, base_url)
    assert order(page) == moved
    menu(page, "view-menu", "menu-reset-panes")
    assert order(page) == DEFAULT
    opened = page.eval_on_selector_all(
        ".panels > details", "(ds) => ds.filter((d) => d.open).map((d) => d.id)"
    )
    # Scope reopened; DC starts shut, as on load
    assert opened == [p for p in DEFAULT if p != "panel-dc"]
    reload_kept(page)
    open_circuit(page, base_url)
    assert order(page) == DEFAULT


def test_arrow_keys_move_a_pane(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    grip = page.locator('[data-grip="panel-scope"]')
    grip.focus()
    for _ in range(3):  # past Bias & headroom and Frequency, then Probe
        page.keyboard.press("ArrowUp")
    top = ["panel-problems", "panel-notes", "panel-dc", "panel-scope", "panel-probe",
           "panel-frequency"]  # fmt: skip
    assert order(page)[:6] == top
    expect(grip).to_be_focused()
    for _ in range(3):
        page.keyboard.press("ArrowDown")
    assert order(page) == DEFAULT


def opened(page: Page) -> list[str]:
    return list(
        page.eval_on_selector_all(
            ".panels > details", "(ds) => ds.filter((d) => d.open).map((d) => d.id)"
        )
    )


# the pane list's scroll as each frame was painted, from when it is first shown (read
# just after the paint: in the frame itself the resize callbacks haven't run yet)
FRAMES = """
window.__tops = [];
const tick = () => setTimeout(() => {
  const el = document.querySelector('.panels');
  if (el && el.dataset.ready) window.__tops.push(el.scrollTop);
  if (window.__tops.length < 1000) requestAnimationFrame(tick);
}, 0);
requestAnimationFrame(tick);
"""


def test_open_and_shut_panes_and_the_scroll_survive_a_reload(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    page.locator("#panel-dc > summary").click(position={"x": 40, "y": 10})  # open
    page.locator("#panel-scope > summary").click(position={"x": 40, "y": 10})  # shut
    page.locator("#panel-knobs > summary").click(position={"x": 40, "y": 10})  # shut
    want = [p for p in DEFAULT if p not in ("panel-scope", "panel-knobs")]
    assert opened(page) == want
    page.evaluate("document.querySelector('.panels').scrollTop = 400")
    page.wait_for_timeout(400)  # the scroll is saved once it settles
    page.add_init_script(FRAMES)
    reload_kept(page)
    wait_for_update(page, 0)
    assert opened(page) == want
    page.wait_for_timeout(500)  # the panes have filled in
    tops = page.evaluate("window.__tops")
    assert tops and set(tops) == {400}, tops  # there from the first frame: no jump from the top
    # a pane restored shut still draws when opened
    page.locator("#panel-scope > summary").click(position={"x": 40, "y": 10})
    expect(page.locator("#panel-scope canvas").first).to_be_visible()
    menu(page, "view-menu", "menu-reset-panes")
    reload_kept(page)
    wait_for_update(page, 0)
    assert opened(page) == [p for p in DEFAULT if p != "panel-dc"]


def test_large_views_come_back_as_bars(page: Page, base_url: str) -> None:
    """D-121: panes out as large views stay out after a reload, shrunk to their bars, and
    their panel state (open) is kept for when they go back."""
    open_circuit(page, base_url)
    page.locator("#stages-expand").click()
    page.locator("#frequency-expand").click()  # Bias & headroom shrinks to its bar
    expect(page.locator("#panel-stages")).not_to_have_attribute("open", "")
    reload_kept(page)
    wait_for_update(page, 0)
    for pane in ("panel-stages", "panel-frequency"):
        expect(page.locator(f"#{pane}")).to_have_class(re.compile("large-view"))
        expect(page.locator(f"#{pane}")).not_to_have_attribute("open", "")
    # the bars stack in the order they shrank: Bias & headroom at the bottom
    bottoms = [
        page.eval_on_selector(f"#{p}", "(d) => parseFloat(d.style.bottom)")
        for p in ("panel-stages", "panel-frequency")
    ]
    assert bottoms[0] < bottoms[1]
    # a bar opens its view; Collapse puts it back in its panel, open
    page.locator("#panel-frequency > summary").click(position={"x": 60, "y": 10})
    expect(page.locator("#panel-frequency")).to_have_attribute("open", "")
    page.locator("#frequency-expand").click()
    expect(page.locator("#panel-frequency")).not_to_have_class(re.compile("large-view"))
    expect(page.locator("#panel-frequency")).to_have_attribute("open", "")
    reload_kept(page)
    wait_for_update(page, 0)
    expect(page.locator("#panel-frequency")).not_to_have_class(re.compile("large-view"))
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    # opening another circuit leaves them as bars (D-127); Reset panes puts them back
    open_circuit(page, base_url, "big-muff-pi-v3")
    expect(page.locator("#panel-stages")).to_have_class(re.compile("large-view"))
    expect(page.locator("#panel-stages")).not_to_have_attribute("open", "")
    menu(page, "view-menu", "menu-reset-panes")
    expect(page.locator("#panel-stages")).not_to_have_class(re.compile("large-view"))


def test_a_large_view_is_one_height_and_shrinks_when_the_window_is_short(
    page: Page, base_url: str
) -> None:
    """Round 2 (D-127): 560 px, anchored 16 px from the bottom, whatever the window's
    height; a window too short to leave 200 px of canvas above it shrinks it to its bar."""
    open_circuit(page, base_url)
    page.locator("#frequency-expand").click()
    view = page.locator("#panel-frequency")
    expect(view).to_have_attribute("open", "")

    def box() -> dict[str, float]:
        b = view.bounding_box()
        assert b
        return b

    for height in (1000, 1200):
        page.set_viewport_size({"width": 1600, "height": height})
        expect(view).to_have_attribute("open", "")
        assert box()["height"] == 560
        assert box()["y"] + box()["height"] == height - 16
    page.set_viewport_size({"width": 1600, "height": 700})  # 124 px of canvas above it
    expect(view).not_to_have_attribute("open", "")
    expect(view).to_have_class(re.compile("large-view"))  # a bar, not back in the column
    page.set_viewport_size({"width": 1600, "height": 1000})
    expect(view).not_to_have_attribute("open", "")  # it stays a bar till asked


def test_pane_order_logic(js: Page) -> None:
    result = run(
        js,
        """
        const p = await m('panes.js');
        const d = ['a', 'b', 'c', 'd'];
        return {
          none: p.paneOrder(null, d),
          junk: p.paneOrder('x', d),
          saved: p.paneOrder(['c', 'a', 'b', 'd'], d),
          gone: p.paneOrder(['c', 'zz', 'a', 'b', 'd', 'c'], d),
          added: p.paneOrder(['c', 'a', 'd'], d),  // b is new: it goes after a
          first: p.paneOrder(['c', 'b', 'd'], d),  // a is new and first: it leads
          up: p.movePane(d, 'c', 0),
          down: p.movePane(d, 'a', 9),
          missing: p.movePane(d, 'z', 0),
          opens: [...p.openStates(
            {a: false, b: 'yes', zz: true}, new Map([['a', true], ['b', true], ['c', false]]))],
          noOpens: [...p.openStates(null, new Map([['a', true]]))],
        };
        """,
    )
    assert result["none"] == result["junk"] == ["a", "b", "c", "d"]
    assert result["saved"] == result["gone"] == ["c", "a", "b", "d"]
    assert result["added"] == ["c", "a", "b", "d"]
    assert result["first"] == ["a", "c", "b", "d"]
    assert result["up"] == ["c", "a", "b", "d"]
    assert result["down"] == ["b", "c", "d", "a"]
    assert result["missing"] == ["a", "b", "c", "d"]
    # saved yes/no wins; anything else, or a pane it doesn't know, starts as the page does
    assert result["opens"] == [["a", False], ["b", True], ["c", False]]
    assert result["noOpens"] == [["a", True]]


def test_dc_starts_shut_and_scrolls(page: Page, base_url: str) -> None:
    """D-095: DC sits under Problems and Notes (D-269), starts shut, and its long list of
    nets scrolls."""
    open_circuit(page, base_url)
    expect(page.locator("#panel-dc")).not_to_have_attribute("open", "")
    assert order(page)[:3] == ["panel-problems", "panel-notes", "panel-dc"]
    page.locator("#panel-dc > summary").click()
    expect(page.locator("#dc-body tr").first).to_be_visible()
    box = page.locator("#dc-body .dc-list").evaluate(
        "(l) => ({ shown: l.clientHeight, all: l.scrollHeight })"
    )
    assert box["all"] > box["shown"]  # the TS808 has more nets than fit
    assert 150 <= box["shown"] <= 220  # about the Harmonics plot (190 px)
    # supplies first, then the guitar's and the amp's nets, then the rest
    nets = page.locator("#dc-body tr").evaluate_all("(rs) => rs.map((r) => r.dataset.net)")
    assert nets[:4] == ["GND", "V+", "in", "out"]
    expect(page.locator('#dc-body tr[data-net="out"] th')).to_have_text("out to amp")
