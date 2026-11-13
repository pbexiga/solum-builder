"""The editor in a real browser: place, move, wire, rotate, delete, undo/redo, the
inspector and its sweep, saving and reopening.

`test_redraw_ts808_matches_the_starter` is the editor's acceptance criterion:
the TS808 drawn from scratch with the keyboard shortcuts, inspector, labels and wires,
saved, reloaded, and simulated, gives the starter's results.
"""

import itertools
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import (
    REPO,
    click_part,
    open_circuit,
    part_pos,
    reload_kept,
    to_screen,
    updates,
    wait_for_update,
)


def views(page: Page) -> int:
    return int(page.evaluate("Number(document.body.dataset.views || 0)"))


def wait_for_view(page: Page, after: int) -> None:
    """Wait until the app has drawn a view newer than `after` (an edit was applied)."""
    page.wait_for_function(f"Number(document.body.dataset.views || 0) > {after}", timeout=15_000)


def drawn_refs(page: Page) -> list[str]:
    return sorted(page.eval_on_selector_all("g.part", "(gs) => gs.map((g) => g.dataset.ref)"))


def click_at(page: Page, x: float, y: float) -> None:
    page.mouse.click(*to_screen(page, x, y))


def show_area(page: Page, x0: float, y0: float, x1: float, y1: float) -> None:
    """Zoom out and pan (with the wheel and an empty-space drag, as a user would) until
    the schematic area x0..x1, y0..y1 is on screen."""
    box = page.locator("#schematic").bounding_box()
    assert box is not None
    centre = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    for _ in range(10):
        (ax, ay), (bx, by) = to_screen(page, x0, y0), to_screen(page, x1, y1)
        if bx - ax < 0.9 * box["width"] and by - ay < 0.9 * box["height"]:
            break
        page.mouse.move(*centre)
        page.mouse.wheel(0, 400)
    (ax, ay), (bx, by) = to_screen(page, x0, y0), to_screen(page, x1, y1)
    page.mouse.move((ax + bx) / 2, (ay + by) / 2)
    page.mouse.down()
    page.mouse.move(*centre, steps=8)
    page.mouse.up()
    (ax, ay), (bx, by) = to_screen(page, x0, y0), to_screen(page, x1, y1)
    assert box["x"] < ax and bx < box["x"] + box["width"], "area not on screen (x)"
    assert box["y"] < ay and by < box["y"] + box["height"], "area not on screen (y)"


def menu(page: Page, menu_id: str, item_id: str) -> None:
    """Pick an item from a header menu."""
    page.locator(f"#{menu_id}").click()
    page.locator(f"#{item_id}").click()


def delete_part(page: Page, ref: str) -> None:
    click_part(page, ref)
    before = views(page)
    press(page, "Delete")
    wait_for_view(page, before)


def save_as(page: Page, name: str) -> str:
    """Save the open circuit under a new name (Ctrl+S on a new sheet or a starter asks
    for one); returns the new circuit's id once it's open."""
    press(page, "Control+s")
    page.locator("#field-name").fill(name)
    page.locator("form.popup button.primary").click()
    page.wait_for_function("location.hash.startsWith('#circuit/')")
    expect(page.locator("#circuit-name")).to_have_text(name)
    expect(page.locator("#dirty")).to_be_hidden()
    return str(page.evaluate("location.hash.split('/')[1]"))


def new_circuit(page: Page, base_url: str, name: str) -> str:
    """An empty saved circuit called `name`, open: the start page's new sheet without its
    guitar input and amp, saved through the API (the editor won't delete them, D-146).
    Returns its id."""
    page.goto(base_url)
    wait_for_update(page, 0)
    cid = str(
        page.evaluate(
            """async (name) => {
              const blank = (await (await fetch('api/blank')).json()).circuit;
              const circuit = { ...blank, parts: [], wires: [], labels: [] };
              const r = await fetch('api/circuits', {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({ circuit, name }),
              });
              return (await r.json()).circuit.id;
            }""",
            name,
        )
    )
    cid = cid.rsplit("-v", 1)[0]  # the short link, as Save as opens it (D-075)
    page.goto(f"{base_url}#circuit/{cid}")
    expect(page.locator("#circuit-name")).to_have_text(name)
    expect(page.locator("g.part")).to_have_count(0)
    expect(page.locator("#dirty")).to_be_hidden()
    return cid


def wires(page: Page) -> list[tuple[int, ...]]:
    """The drawn wires as sorted (x1, y1, x2, y2)."""
    js = "(ls) => ls.map((l) => ['x1', 'y1', 'x2', 'y2'].map((a) => Number(l.getAttribute(a))))"
    lines = page.eval_on_selector_all("line.wire", js)
    return sorted(tuple(line) for line in lines)


def drag(page: Page, a: tuple[float, float], b: tuple[float, float]) -> None:
    """A mouse drag between two schematic points."""
    page.mouse.move(*to_screen(page, *a))
    page.mouse.down()
    page.mouse.move(*to_screen(page, *b), steps=6)
    page.mouse.up()


def press(page: Page, key: str) -> None:
    page.keyboard.press(key)


def place(page: Page, key: str, x: float, y: float, turns: int = 0) -> None:
    before = views(page)
    press(page, key)
    for _ in range(turns):
        press(page, "Space")
    click_at(page, x, y)
    wait_for_view(page, before)


def inspect(page: Page, values: dict[str, str]) -> None:
    """Open the inspector on the selected part (Enter), fill it in, apply."""
    press(page, "Enter")
    form = page.locator("form.popup")
    expect(form).to_be_visible()
    before = views(page)
    for name, value in values.items():
        field = page.locator(f"#field-{name}")
        if field.evaluate("(e) => e.tagName") == "SELECT":
            field.select_option(value)
        else:
            field.fill(value)
    form.locator("button.primary").click()
    error = form.locator(".error")
    shown = "document.querySelector('form.popup .error')"
    # the form closes once its edit is shown; nothing changed closes it with no new view
    page.wait_for_function(
        f"Number(document.body.dataset.views || 0) > {before} || ({shown} && !{shown}.hidden)"
        " || !document.querySelector('form.popup')"
    )
    if form.count() and error.is_visible():
        raise AssertionError(f"inspector refused {values}: {error.inner_text()}")


def place_label(page: Page, net: str, x: float, y: float) -> None:
    press(page, "l")
    page.locator("#field-net").fill(net)
    before = views(page)
    press(page, "Enter")
    expect(page.locator("form.popup")).to_have_count(0)
    click_at(page, x, y)
    wait_for_view(page, before)


def api(page: Page, base_url: str, method: str, path: str, body: Any = None) -> Any:
    r = page.request.fetch(f"{base_url}{path}", method=method, data=body)
    assert r.ok, r.text()
    return r.json()


# ---- editing ---------------------------------------------------------------------


def test_place_undo_redo(page: Page, base_url: str) -> None:
    new_circuit(page, base_url, "Undo test")
    place(page, "r", 0, 0)
    place(page, "c", 100, 0, turns=1)
    assert drawn_refs(page) == ["C1", "R1"]
    assert page.locator('g.part[data-ref="C1"]').get_attribute("transform") == (
        "translate(100 0) rotate(90)"
    )
    expect(page.locator("#dirty")).to_be_visible()
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    assert drawn_refs(page) == ["R1"]
    page.locator("#edit-menu").click()
    expect(page.locator("#menu-redo")).to_be_enabled()
    expect(page.locator("#menu-redo .menu-label")).to_have_text("Redo Add C1")
    before = views(page)
    page.locator("#menu-redo").click()  # from the menu this time
    wait_for_view(page, before)
    assert drawn_refs(page) == ["C1", "R1"]
    page.locator("#edit-menu").click()
    expect(page.locator("#menu-undo .menu-label")).to_have_text("Undo Add C1")
    press(page, "Escape")
    expect(page.locator(".menu")).to_have_count(0)


def test_escape_cancels_placing(page: Page, base_url: str) -> None:
    new_circuit(page, base_url, "Escape test")
    press(page, "q")
    expect(page.locator("#schematic")).to_have_class("placing")
    expect(page.locator('.palette [data-place="bjt"]')).to_have_class(re.compile(r"\bactive\b"))
    press(page, "Escape")
    expect(page.locator("#schematic")).not_to_have_class("placing")
    click_at(page, 0, 0)
    assert drawn_refs(page) == []


@pytest.mark.usefixtures("half_drawn")  # floats until wired: refused runs
def test_led_tile_places_the_red_led(page: Page, base_url: str) -> None:
    """With an LED model in the library, the palette has an LED tile (E)."""
    cid = new_circuit(page, base_url, "LED test")
    expect(page.locator('.palette [data-place="led"]')).to_be_visible()
    place(page, "e", 0, 0)
    assert drawn_refs(page) == ["LED1"]
    press(page, "Control+s")
    expect(page.locator("#dirty")).to_be_hidden()
    (part,) = api(page, base_url, "GET", f"api/circuits/{cid}")["circuit"]["parts"]
    assert (part["type"], part["model"]) == ("led", "APT1608SURCK")


@pytest.mark.usefixtures("half_drawn")  # floats until wired: refused runs
def test_move_wire_rotate_delete(page: Page, base_url: str) -> None:
    """Two resistors wired pin to pin; moving one drags the wire end; a wire to a third
    makes a T with a junction dot; rotate and delete through the keyboard."""
    new_circuit(page, base_url, "Wiring test")
    place(page, "r", 0, 0)  # R1 pins (-20, 0), (20, 0)
    place(page, "r", 100, 0)  # R2 pins (80, 0), (120, 0)
    place(page, "r", 50, 80, turns=1)  # R3 vertical: pins (50, 60), (50, 100)

    before = views(page)
    page.mouse.move(*to_screen(page, 20, 0))  # drag from R1.2 to R2.1
    page.mouse.down()
    page.mouse.move(*to_screen(page, 80, 0), steps=6)
    page.mouse.up()
    wait_for_view(page, before)
    wire = page.locator("line.wire")
    expect(wire).to_have_count(1)
    assert wire.get_attribute("data-net") == "R1.2"

    before = views(page)
    page.mouse.move(*to_screen(page, 50, 60))  # from R3's top pin up onto the wire: a T
    page.mouse.down()
    page.mouse.move(*to_screen(page, 50, 0), steps=6)
    page.mouse.up()
    wait_for_view(page, before)
    expect(page.locator("circle.junction")).to_have_count(1)
    assert {w.get_attribute("data-net") for w in page.locator("line.wire").all()} == {"R1.2"}

    before = views(page)
    page.mouse.move(*to_screen(page, 100, 0))  # drag R2 down 40: its wire end follows
    page.mouse.down()
    page.mouse.move(*to_screen(page, 100, 40), steps=6)
    page.mouse.up()
    wait_for_view(page, before)
    assert part_pos(page, "R2") == (100, 40)
    ends = page.eval_on_selector_all(
        "line.wire", "(ls) => ls.map((l) => [l.getAttribute('x2'), l.getAttribute('y2')])"
    )
    assert ["80", "40"] in ends

    click_part(page, "R1")
    before = views(page)
    press(page, "Space")
    wait_for_view(page, before)
    assert page.locator('g.part[data-ref="R1"]').get_attribute("transform") == (
        "translate(0 0) rotate(90)"
    )
    before = views(page)
    press(page, "Delete")
    wait_for_view(page, before)
    assert drawn_refs(page) == ["R2", "R3"]


def test_turned_switch_lug_numbers_read_upright(page: Page, base_url: str) -> None:
    """The user's bug (2026-11-02): a switch turned 180 degrees had its lug numbers upside
    down. Symbol text turns back by the part's turn, so it reads upright (D-164)."""
    new_circuit(page, base_url, "Turned switch")
    place(page, "s", 0, 0, turns=2)
    texts = page.locator('g.part[data-ref="SW1"] text.sym-text')
    expect(texts).not_to_have_count(0)
    for t in texts.all():
        assert (t.get_attribute("transform") or "").startswith("rotate(-180 ")


def test_a_supply_stays_selected_while_space_turns_it(page: Page, base_url: str) -> None:
    """The user (2026-11-02): each Space on GND (or V+, V-) needed a click on it first.
    Clicked once, it stays selected, so Space turns it again and again (D-164)."""
    new_circuit(page, base_url, "Turn ground")
    place(page, "r", 0, 0)
    before = views(page)
    press(page, "g")
    click_at(page, -20, 0)
    wait_for_view(page, before)
    click_at(page, -20, 14)  # its bars
    for turn in (90, 180, 270, 0):
        before = views(page)
        press(page, "Space")
        wait_for_view(page, before)
        turned = page.locator('.net-label.ground[data-net="GND"] > g > g[transform]')
        if turn:
            expect(turned).to_have_attribute("transform", f"rotate({turn})")
        else:
            expect(turned).to_have_count(0)


def label_at(page: Page, net: str) -> str | None:
    return page.locator(f'.net-label[data-net="{net}"]').get_attribute("data-at")


def test_labels_and_grounds_drag(page: Page, base_url: str) -> None:
    """The user's bug (2026-11-02): pressing on a label always started a wire, so GND,
    V+ and net labels couldn't be moved (D-164). Dragged by its symbol or name it moves,
    its wire following; pressed right on its point it still starts a wire."""
    new_circuit(page, base_url, "Label drag")
    place(page, "r", 0, 0)  # R1 pins (-20, 0), (20, 0)
    place_label(page, "OUT", 20, 0)
    before = views(page)
    press(page, "g")
    click_at(page, -20, 0)
    wait_for_view(page, before)

    before = views(page)
    drag(page, (-20, 14), (-20, 54))  # the ground symbol's bars, down 40
    wait_for_view(page, before)
    assert label_at(page, "OUT") == "20,0" and label_at(page, "GND") == "-20,40"
    assert (-20, 0, -20, 40) in wires(page) or (-20, 40, -20, 0) in wires(page)

    box = page.locator('.net-label[data-net="OUT"] text').bounding_box()
    assert box is not None
    before = views(page)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(*to_screen(page, 60, -40), steps=6)  # anywhere 40 right, 40 up or so
    page.mouse.up()
    wait_for_view(page, before)
    assert label_at(page, "OUT") != "20,0"
    assert part_pos(page, "R1") == (0, 0)


def test_wire_mode_and_labels(page: Page, base_url: str) -> None:
    new_circuit(page, base_url, "Label test")
    place(page, "r", 0, 0)
    place_label(page, "OUT", 20, 0)
    expect(page.locator('.net-label[data-net="OUT"]')).to_have_count(1)
    before = views(page)
    press(page, "g")
    click_at(page, -20, 0)
    wait_for_view(page, before)
    expect(page.locator('.net-label.ground[data-net="GND"]')).to_have_count(1)
    # the wire tool: a click starts anywhere, clicks on empty grid add bends, a click on
    # a pin or label finishes; legs are square
    page.locator('[data-tool="wire"]').click()
    before = views(page)
    click_at(page, 0, 60)
    click_at(page, 40, 60)
    page.mouse.move(*to_screen(page, 40, 30))
    expect(page.locator(".overlay .wire-path line")).to_have_count(2)  # a leg, the live leg
    assert views(page) == before  # nothing added until it ends somewhere
    click_at(page, 20, 0)  # the OUT label on R1's pin: vertical leg first, it moved up
    wait_for_view(page, before)
    assert wires(page) == [(0, 60, 40, 60), (40, 0, 20, 0), (40, 60, 40, 0)]
    expect(page.locator('.wire-end.pin[cx="20"][cy="0"]')).to_have_count(1)
    expect(page.locator('.wire-end.loose[cx="0"][cy="60"]')).to_have_count(1)
    # Escape drops a wire half-drawn and stays in the tool; a second Escape leaves it
    click_at(page, 100, 100)
    click_at(page, 100, 140)
    press(page, "Escape")
    expect(page.locator(".overlay .wire-path")).to_have_count(0)
    expect(page.locator('[data-tool="wire"]')).to_have_attribute("aria-pressed", "true")
    press(page, "Escape")
    expect(page.locator('[data-tool="wire"]')).to_have_attribute("aria-pressed", "false")
    # drag the loose end's ball onto the GND symbol's point: it connects there
    before = views(page)
    drag(page, (0, 60), (-20, 0))
    wait_for_view(page, before)
    expect(page.locator(".wire-end.loose")).to_have_count(0)
    assert all(x1 == x2 or y1 == y2 for x1, y1, x2, y2 in wires(page))
    # double-click a label to rename it
    page.locator('.net-label[data-net="OUT"] text').dblclick()
    page.locator("#field-net").fill("SIG")
    before = views(page)
    page.locator("form.popup button.primary").click()
    wait_for_view(page, before)
    expect(page.locator('.net-label[data-net="SIG"]')).to_have_count(1)
    # a wire may end on nothing: from R1's left pin, a second click on the last point ends it
    page.locator('[data-tool="wire"]').click()
    before = views(page)
    click_at(page, -20, 0)
    click_at(page, -20, 100)
    assert views(page) == before
    click_at(page, -20, 100)
    wait_for_view(page, before)
    assert (-20, 0, -20, 100) in wires(page)
    expect(page.locator('.wire-end.loose[cx="-20"][cy="100"]')).to_have_count(1)
    press(page, "Escape")


def test_a_part_dropped_on_a_wire_sits_on_it_in_series(
    page: Page, base_url: str, half_drawn: list[str]
) -> None:
    """A resistor dropped on a wire, even on the edge of its click band, lands on the line
    and the wire is cut between its pins (it isn't shorted)."""
    new_circuit(page, base_url, "Series test")
    page.locator('[data-tool="wire"]').click()
    before = views(page)
    click_at(page, -100, 0)
    click_at(page, 100, 0)
    click_at(page, 100, 0)  # the last point again: the wire ends there
    wait_for_view(page, before)
    press(page, "Escape")
    before = views(page)
    press(page, "r")
    x, y = to_screen(page, 0, 0)
    page.mouse.click(x, y - 3)  # on the wire, a little above the line
    wait_for_view(page, before)
    assert part_pos(page, "R1") == (0, 0)
    assert wires(page) == [(-100, 0, -20, 0), (20, 0, 100, 0)]


def test_inspector_applies_and_refuses(
    page: Page, base_url: str, browser_errors: list[str]
) -> None:
    new_circuit(page, base_url, "Inspector test")
    place(page, "r", 0, 0)
    page.locator('g.part[data-ref="R1"]').dblclick()  # double-click opens the inspector too
    expect(page.locator("form.popup .popup-title .name")).to_have_text("R1")
    page.locator('form.popup [data-action="cancel"]').click()
    inspect(page, {"ref": "R7", "value": "4k7"})
    assert drawn_refs(page) == ["R7"]
    expect(page.locator('g.part-text[data-ref="R7"] .value')).to_have_text("4k7")
    # a value the server can't read: refused in plain English, nothing changes
    press(page, "Enter")
    page.locator("#field-value").fill("4k7k")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup .error")).to_contain_text("Couldn't read the value '4k7k'")
    page.locator("#field-value").fill("4k7F")  # a capacitor's unit on a resistor (D-164)
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup .error")).to_contain_text(
        "is in farads (F), but this value is in ohms"
    )
    browser_errors.clear()  # the browser logs the refused request (422); that's expected
    page.locator('form.popup [data-action="cancel"]').click()
    expect(page.locator('g.part-text[data-ref="R7"] .value')).to_have_text("4k7")


def test_a_switchs_position_names(page: Page, base_url: str) -> None:
    """D-143: named in the form, the positions are the Knobs buttons (what each joins on
    hover) and the drawing says which one it's on; flipping it changes the drawing."""
    new_circuit(page, base_url, "Named positions")
    place(page, "s", 0, 0)
    inspect(page, {"label": "Voice", "name_0": "Thick", "name_1": "Thin"})
    value = page.locator('g.part-text[data-ref="SW1"] .value')
    expect(value).to_have_text("SPDT · Thick")
    knob = page.locator('#knobs-body [data-knob="SW1"]')
    expect(knob.locator("button")).to_have_text(["Thick", "Thin"])
    expect(knob.locator('[data-position="1"]')).to_have_attribute("title", "2: 2\u20133")
    knob.locator('[data-position="1"]').click()
    expect(value).to_have_text("SPDT · Thin")


def test_a_custom_switch_from_its_editor(page: Page, base_url: str) -> None:
    """9c: Custom… opens the editor from the type picked (SPDT: two positions, 2-1 and
    2-3); made a 3-way rotary, Apply makes the switch it, drawn as an arc, three positions
    in Knobs; its form names it and opens the editor again; another type drops it."""
    new_circuit(page, base_url, "Custom switch")
    place(page, "s", 0, 0)
    press(page, "Enter")
    page.locator("#field-kind").select_option("custom")
    editor = page.locator("#custom-switch")
    expect(editor).to_be_visible()
    expect(page.locator("#field-kind")).to_have_value("spdt")  # unchanged until Apply
    expect(editor.locator("[data-join]")).to_have_count(2)
    expect(editor.locator('[data-join="1-0"] option:checked')).to_have_text("2\u20133")
    editor.locator("#custom-name").fill("Clip")
    editor.locator("#custom-throws").select_option("3")
    editor.locator("#custom-positions").select_option("3")
    editor.locator("#custom-look").select_option("rotary")
    editor.locator('[data-position="2"]').fill("LED")
    expect(editor.locator('[data-join="2-0"] option:checked')).to_have_text("C\u20133")
    editor.get_by_role("button", name="Apply").click()
    expect(editor).to_have_count(0)
    expect(page.locator('g.part-text[data-ref="SW1"] .value')).to_have_text("Clip")
    knob = page.locator('#knobs-body [data-knob="SW1"]')
    expect(knob.locator("button")).to_have_text(["1", "2", "LED"])
    # drawn as an arc: its three contacts inside, besides the lugs
    expect(page.locator('g.part[data-ref="SW1"] circle[r="1.5"]')).to_have_count(3)
    press(page, "Enter")
    expect(page.locator("#field-kind option:checked")).to_have_text("Custom: Clip")
    page.get_by_role("button", name="Edit its contacts…").click()
    expect(editor.locator("#custom-name")).to_have_value("Clip")
    editor.get_by_role("button", name="Cancel").click()
    inspect(page, {"kind": "spdt"})
    expect(page.locator('g.part-text[data-ref="SW1"] .value')).to_have_text("SPDT")


def test_try_several_values(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    click_part(page, "R8")
    press(page, "Enter")
    page.locator("#sweep-values").fill("470, 1k, 2k2, 4k7")
    before = updates(page)
    page.locator("#sweep-run").click()
    wait_for_update(page, before)
    expect(page.locator("#sweep-tools")).to_be_visible()
    labels = page.evaluate(
        "document.getElementById('frequency-plot')._plot.series.map(s => s.label)"
    )
    assert [lb.split(" (")[0] for lb in labels[1:]] == [
        "R8 = 470",
        "R8 = 1k",
        "R8 = 2k2",
        "R8 = 4k7",
    ]
    scope = page.evaluate("document.getElementById('scope-plot')._plot.series.length")
    assert scope == 5
    # the runs side by side as numbers: one row per value
    expect(page.locator("#sweep-summary tbody tr")).to_have_count(4)
    page.locator('form.popup [data-action="cancel"]').click()
    page.locator("#sweep-clear").click()
    expect(page.locator("#sweep-tools")).to_be_hidden()


# ---- files -----------------------------------------------------------------------


def test_save_reload_properties_and_search(page: Page, base_url: str) -> None:
    cid = new_circuit(page, base_url, "Saved fuzz")
    place(page, "q", 0, 0)
    press(page, "Control+s")
    expect(page.locator("#dirty")).to_be_hidden()
    menu(page, "file-menu", "menu-properties")
    page.locator("#field-tags").fill("germanium, fuzz")
    expect(page.locator("#field-length")).to_be_hidden()  # Custom's mm only for Custom
    page.locator("#field-enclosure").select_option("custom")
    page.locator("#field-length").fill("100")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup .error")).to_contain_text("length, width and height")
    page.locator("#field-enclosure").select_option("125B")  # D-204
    before = views(page)
    page.locator("form.popup button.primary").click()
    wait_for_view(page, before)
    menu(page, "file-menu", "menu-save")
    expect(page.locator("#dirty")).to_be_hidden()

    page.reload()
    page.wait_for_function("document.querySelectorAll('g.part').length === 1")
    assert drawn_refs(page) == ["Q1"]
    saved = api(page, base_url, "GET", f"api/circuits/{cid}")["circuit"]
    assert saved["tags"] == ["germanium", "fuzz"]
    assert saved["enclosure"] == {"size": "125B"}

    menu(page, "file-menu", "menu-open")
    found = (
        "[...document.querySelectorAll('.open-list [data-circuit]')]"
        ".map((b) => b.firstChild.textContent)"
    )
    page.locator("#field-q").fill("germanium")
    page.wait_for_function(f"{found}.join() === 'Saved fuzz'")
    page.locator("#field-q").fill("2N5089")  # by part model
    page.wait_for_function(f"{found}.join() === 'Saved fuzz'")
    page.locator("#field-q").fill("nothing like it")
    expect(page.locator(".open-list .empty")).to_have_text("No circuits match.")


def test_find_part_selects_and_brings_it_into_view(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    box = page.locator("#schematic").bounding_box()
    assert box is not None
    for _ in range(6):  # zoom right in on the top-left corner: R13 is far off screen
        page.mouse.move(box["x"] + 5, box["y"] + 5)
        page.mouse.wheel(0, -400)

    def on_screen(ref: str) -> bool:
        x, y = to_screen(page, *part_pos(page, ref))
        return box["x"] < x < box["x"] + box["width"] and box["y"] < y < box["y"] + box["height"]

    assert not on_screen("R13")
    press(page, "Control+f")
    page.locator("#field-ref").fill("r99")
    page.locator("#field-ref").press("Enter")
    expect(page.locator(".popup .error")).to_have_text("There's no part R99 on this sheet.")
    before = updates(page)
    page.locator("#field-ref").fill("r 13")
    page.locator("#field-ref").press("Enter")
    expect(page.locator('.found-ring[data-found="R13"]')).to_have_count(1)
    wait_for_update(page, before)
    expect(page.locator(".popup")).to_have_count(0)
    assert on_screen("R13")
    expect(page.locator('g.part.selected[data-ref="R13"]')).to_have_count(1)
    expect(page.locator(".found-ring")).to_have_count(0, timeout=3000)  # the ring fades
    menu(page, "edit-menu", "menu-find")  # also in the Edit menu
    expect(page.locator("#field-ref")).to_be_focused()


def test_starter_menu_and_save_as_a_copy(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    menu(page, "file-menu", "menu-starters")  # File → New from starter ▸
    page.locator("#starter-fuzz-face").click()
    page.wait_for_function("location.hash === '#starter/fuzz-face'")
    expect(page.locator("#circuit-name")).to_have_text("Fuzz Face (AC128)")
    cid = save_as(page, "My Fuzz Face")  # a starter is read-only: Save asks for a name
    assert cid == "my-fuzz-face"
    saved = api(page, base_url, "GET", f"api/circuits/{cid}")["circuit"]
    starter = api(page, base_url, "GET", "api/starters/fuzz-face")["circuit"]
    assert (saved["parts"], saved["wires"]) == (starter["parts"], starter["wires"])
    assert "starter" not in saved


def test_start_page_drag_from_palette_and_wire(page: Page, base_url: str) -> None:
    """The start page is a new sheet with a guitar input and an amp. A resistor dragged
    in from the palette and wired between them gives a signal path; moving it keeps the
    wires square."""
    page.goto(base_url)
    wait_for_update(page, 0)
    expect(page.locator("#circuit-name")).to_have_text("Untitled")
    assert drawn_refs(page) == ["IN", "OUT"]
    expect(page.locator("#probe-body")).to_contain_text("Nothing is wired yet")

    tile = page.locator('.palette [data-place="resistor"]').bounding_box()
    assert tile is not None
    before = views(page)
    page.mouse.move(tile["x"] + tile["width"] / 2, tile["y"] + tile["height"] / 2)
    page.mouse.down()
    page.mouse.move(*to_screen(page, -50, -50), steps=4)
    page.mouse.move(*to_screen(page, 0, 0), steps=4)
    page.mouse.up()
    wait_for_view(page, before)
    assert drawn_refs(page) == ["IN", "OUT", "R1"] and part_pos(page, "R1") == (0, 0)

    for a, b in (((-280, 0), (-20, 0)), ((20, 0), (280, 0))):
        before = views(page)
        drag(page, a, b)
        wait_for_view(page, before)
    click_part(page, "OUT")
    expect(page.locator("#error")).to_be_hidden()
    expect(page.locator("#frequency-plot canvas").first).to_be_visible()

    before = views(page)
    drag(page, (0, 0), (0, 40))
    wait_for_view(page, before)
    lines = page.eval_on_selector_all(
        "line.wire", "(ls) => ls.map((l) => ['x1', 'y1', 'x2', 'y2'].map((a) => l.getAttribute(a)))"
    )
    assert len(lines) == 4
    assert all(x1 == x2 or y1 == y2 for x1, y1, x2, y2 in lines), lines


def test_power_menu_sets_the_main_rail(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    power = page.locator("#power")
    expect(power.locator("option:checked")).to_have_text("9 V")
    expect(page.locator("#power-draw")).to_contain_text("mA")  # what the circuit draws
    before = views(page)
    power.select_option(label="18 V")
    wait_for_view(page, before)
    expect(page.locator("#power-draw")).to_have_class(re.compile("stale"))
    expect(page.locator("#dirty")).to_be_visible()
    # auto-run is off by default: the results are marked out of date until Run
    expect(page.locator("#stale")).to_be_visible()
    expect(page.locator("#run")).to_have_class(re.compile("stale"))
    after = updates(page)
    page.locator("#run").click()
    wait_for_update(page, after)
    expect(page.locator("#stale")).to_be_hidden()
    page.locator("#view-menu").click()
    page.locator("#menu-dc").click()
    page.wait_for_function(
        "parseFloat(document.querySelector('.dc-layer text[data-net=\"VREF\"]')?.textContent) > 8"
    )
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    expect(power.locator("option:checked")).to_have_text("9 V")


def test_a_dc_source_leaves_the_power_menu_alone(page: Page, base_url: str) -> None:
    """V+ is always the Power menu's: placing a DC source changes nothing there, and it
    isn't drawn switched off (D-091; D-061 and D-064 are gone)."""
    page.goto(base_url)
    wait_for_update(page, 0)
    power = page.locator("#power")
    expect(power.locator("option:checked")).to_have_text("9 V")
    place(page, "v", 0, 80)
    expect(power.locator("option:checked")).to_have_text("9 V")
    expect(page.locator('g.part-text[data-ref="V1"] .value')).to_have_text("9 V")


def test_text_block_place_move_edit_delete(page: Page, base_url: str) -> None:
    """The Misc group's Text tile (X): click where it goes, then the editor opens for a
    title and the text (Cancel places nothing); drag it; double-click to edit; Delete
    removes it and undo brings it back (D-091)."""
    new_circuit(page, base_url, "Text test")
    expect(page.locator('#palette [data-tool="text"]')).to_have_count(1)
    press(page, "x")
    click_at(page, 0, 0)
    form = page.locator('form.popup[aria-label="Text"]')
    expect(form).to_be_visible()
    form.locator('[data-action="cancel"]').click()
    expect(page.locator("g.text-block")).to_have_count(0)  # cancelled: nothing placed

    press(page, "x")
    click_at(page, 0, 0)
    expect(page.locator("#field-title")).to_be_focused()
    # the text box fits inside the popup (it used to run off its right edge)
    popup, area = form.bounding_box(), page.locator("#field-text").bounding_box()
    assert popup and area and area["x"] + area["width"] <= popup["x"] + popup["width"]
    page.locator("#field-title").fill("Bias")
    page.locator("#field-text").fill("Q1 drain\nto 4.5 V")
    before = views(page)
    page.locator("#field-text").press("Control+Enter")
    wait_for_view(page, before)
    expect(form).to_have_count(0)
    block = page.locator("g.text-block")
    expect(block).to_have_count(1)
    expect(block.locator("tspan")).to_have_text(["Bias", "Q1 drain", "to 4.5 V"])
    expect(block.locator("tspan.sheet-title")).to_have_text("Bias")
    expect(page.locator("g.text-block.selected")).to_have_count(1)

    before = views(page)
    drag(page, (10, 5), (110, 55))
    wait_for_view(page, before)
    expect(block.locator(".sheet-text")).to_have_attribute("x", "100")
    expect(block.locator(".sheet-text")).to_have_attribute("y", "50")

    page.mouse.dblclick(*to_screen(page, 110, 55))
    expect(page.locator("#field-title")).to_have_value("Bias")
    field = page.locator("#field-text")
    expect(field).to_have_value("Q1 drain\nto 4.5 V")
    field.fill("Q1 drain")
    before = views(page)
    field.press("Control+Enter")
    wait_for_view(page, before)
    expect(block.locator("tspan")).to_have_text(["Bias", "Q1 drain"])

    click_at(page, 110, 55)
    expect(page.locator("g.text-block.selected")).to_have_count(1)
    before = views(page)
    press(page, "Delete")
    wait_for_view(page, before)
    expect(block).to_have_count(0)
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    expect(block).to_have_count(1)

    # copied alone, a text block pastes (the user's bug, 2026-11-02, D-164)
    click_at(page, 110, 55)
    press(page, "Control+c")
    press(page, "Control+v")
    expect(page.locator(".overlay .ghost text")).not_to_have_count(0)  # its preview shows
    before = views(page)
    click_at(page, 110, 205)
    wait_for_view(page, before)
    expect(block).to_have_count(2)


def test_autorun_runs_after_each_edit_and_is_remembered(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    autorun = page.locator("#autorun")
    expect(autorun).not_to_be_checked()
    autorun.check()
    after = updates(page)
    before = views(page)
    page.locator("#power").select_option(label="18 V")
    wait_for_view(page, before)
    wait_for_update(page, after)  # ran by itself
    expect(page.locator("#stale")).to_be_hidden()
    reload_kept(page)
    wait_for_update(page, 0)
    expect(page.locator("#autorun")).to_be_checked()
    page.locator("#autorun").uncheck()
    # Ctrl+Enter runs too
    before = views(page)
    page.locator("#power").select_option(label="12 V")
    wait_for_view(page, before)
    expect(page.locator("#stale")).to_be_visible()
    after = updates(page)
    press(page, "Control+Enter")
    wait_for_update(page, after)
    expect(page.locator("#stale")).to_be_hidden()


@pytest.mark.usefixtures("half_drawn")  # floats until wired: refused runs
def test_supply_symbols_turn(page: Page, base_url: str, half_drawn: list[str]) -> None:
    """D-117: Space turns a ground or rail symbol while placing it and once placed; the
    name stays upright beyond the bar; the net is the same."""
    new_circuit(page, base_url, "Turn supplies")
    place(page, "g", 0, 0, turns=1)
    expect(page.locator('.net-label.ground > g > g[transform="rotate(90)"]')).to_have_count(1)
    tile = page.locator('.palette [data-tool="supply"][data-net="V-"]')
    tile.click()
    press(page, "Space")
    press(page, "Space")
    before = views(page)
    click_at(page, 100, 0)
    wait_for_view(page, before)
    rail = page.locator('.net-label.rail[data-net="V-"]')
    expect(rail.locator('g[transform="rotate(180)"]')).to_have_count(1)
    name = rail.locator("text").first
    assert float(name.get_attribute("y") or 0) > 0  # under the turned bar, upright
    # a placed one turns with Space when it's selected
    before = views(page)
    page.locator('.palette [data-tool="supply"][data-net="V+"]').click()
    click_at(page, 200, 0)
    wait_for_view(page, before)
    page.locator('.net-label.rail[data-net="V+"] .part-hit').click()
    before = views(page)
    press(page, "Space")
    wait_for_view(page, before)
    vplus = page.locator('.net-label.rail[data-net="V+"]')
    expect(vplus.locator('g[transform="rotate(90)"]')).to_have_count(1)
    expect(vplus.locator("text").first).to_have_attribute("text-anchor", "start")


def test_pump_output_bar_turns(page: Page, base_url: str) -> None:
    """A charge pump's output (the Klon's VB) draws as a supply bar, so it turns with
    Space like V+ does, though it isn't one of the Power menu's rails (TODO, 2026-11-09)."""
    open_circuit(page, base_url, "klon-centaur-aion")
    vb = page.locator('.net-label.rail[data-net="VB"]').last
    vb.click()
    before = views(page)
    press(page, "Space")
    wait_for_view(page, before)
    turned = page.locator('.net-label.rail[data-net="VB"] g[transform="rotate(90)"]')
    expect(turned).to_have_count(1)


def test_a_bias_net_draws_as_a_supply_with_its_name_coloured(page: Page, base_url: str) -> None:
    """TODO 2026-11-09: the Klon's VR (a bias reference) draws as a supply bar like V+,
    and every supply's name takes the supply colour, so power stands out."""
    open_circuit(page, base_url, "klon-centaur-aion")
    vr = page.locator('.net-label.rail[data-net="VR"]')
    expect(vr).to_have_count(8)
    colour = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--sch-supply').trim()"
    )
    for net in ("VR", "V+"):
        label = page.locator(f'.net-label.rail[data-net="{net}"] text').first
        fill = label.evaluate("e => getComputedStyle(e).fill")
        swatch = page.evaluate(
            "c => { const e = document.createElement('i'); e.style.color = c;"
            " document.body.append(e); const v = getComputedStyle(e).color; e.remove(); return v }",
            colour,
        )
        assert fill == swatch, net


def test_supply_tile_and_wire_hops(page: Page, base_url: str, half_drawn: list[str]) -> None:
    """The Supply tile places the main rail (V+) as a supply bar; a wire crossing another
    without connecting gets a hop; a wire drawn through a part goes around it."""
    page.goto(base_url)
    wait_for_update(page, 0)
    # the unused V- tile names the menu item that sets its voltage (Custom…, not "Advanced")
    expect(page.locator('.palette [data-tool="supply"][data-net="V-"]')).to_have_attribute(
        "title", re.compile(r"Power → Custom…")
    )
    tile = page.locator('.palette [data-tool="supply"][data-net="V+"]').bounding_box()
    assert tile is not None
    before = views(page)
    page.mouse.move(tile["x"] + tile["width"] / 2, tile["y"] + tile["height"] / 2)
    page.mouse.down()
    page.mouse.move(*to_screen(page, 0, -100), steps=6)
    page.mouse.up()
    wait_for_view(page, before)
    expect(page.locator('.net-label.rail[data-net="V+"]')).to_have_count(1)

    place(page, "r", 0, 60)  # R1: body (-20, 50)..(20, 70), pins (-20, 60) and (20, 60)
    page.locator('[data-tool="wire"]').click()
    before = views(page)
    click_at(page, -60, 0)  # straight across, from the left...
    click_at(page, 60, 0)  # ...a bend...
    click_at(page, 60, 120)  # ...another...
    click_at(page, -20, 120)
    click_at(page, -20, 60)  # ...onto R1's left pin
    wait_for_view(page, before)
    before = views(page)
    click_at(page, 0, -100)  # from V+ straight down through R1 to an empty point...
    click_at(page, 0, 160)
    click_at(page, 60, 160)
    click_at(page, 60, 120)  # ...ending on the first wire
    wait_for_view(page, before)
    lines = wires(page)
    assert all(x1 == x2 or y1 == y2 for x1, y1, x2, y2 in lines)
    # nothing runs through R1's body: the V+ wire went round it
    assert not any(
        x1 == x2 and -20 < x1 < 20 and min(y1, y2) < 60 < max(y1, y2) for x1, y1, x2, y2 in lines
    ), lines
    expect(page.locator("path.wire.hop")).not_to_have_count(0)  # it crosses y = 0 and y = 120


def drop_tile(page: Page, selector: str, x: float, y: float) -> None:
    """Drag a palette tile onto the schematic at (x, y)."""
    tile = page.locator(f".palette {selector}").bounding_box()
    assert tile is not None
    before = views(page)
    page.mouse.move(tile["x"] + tile["width"] / 2, tile["y"] + tile["height"] / 2)
    page.mouse.down()
    page.mouse.move(*to_screen(page, x, y), steps=6)
    page.mouse.up()
    wait_for_view(page, before)


def test_supplies_by_polarity(page: Page, base_url: str) -> None:
    """V+ and V- tiles; dropping V- adds a negative supply; Power → Custom… sets the type
    and sizes; turning V- off moves its bar to V+ (a change of polarity, D-069), and a
    choice that would join two supplies in use is refused (D-093)."""
    page.goto(base_url)
    wait_for_update(page, 0)
    power = page.locator("#power")
    drop_tile(page, '[data-tool="supply"][data-net="V-"]', 0, -100)
    expect(page.locator('.net-label.rail[data-net="V-"]')).to_have_count(1)
    expect(power.locator("option:checked")).to_have_text("±9 V")

    power.select_option("custom")
    expect(power.locator("option:checked")).to_have_text("±9 V")  # the dialog makes the change
    form = page.locator('form.popup[aria-label="Power"]')
    expect(form.locator("#field-type")).to_have_value("both")
    expect(form.locator("#field-neg")).to_have_value("9")  # V-, as a size
    form.locator("#field-type").select_option("pos")
    expect(form.locator("#field-neg")).to_be_hidden()
    before = views(page)
    form.locator("button[type=submit]").click()
    wait_for_view(page, before)
    expect(page.locator('.net-label.rail[data-net="V-"]')).to_have_count(0)
    expect(page.locator('.net-label.rail[data-net="V+"]')).to_have_count(1)
    expect(power.locator("option:checked")).to_have_text("9 V")

    # both rails in use: going back to one would join them
    drop_tile(page, '[data-tool="supply"][data-net="V-"]', 0, -200)
    expect(power.locator("option:checked")).to_have_text("±9 V")
    power.select_option(label="12 V")
    expect(page.locator("#error")).to_contain_text("V- is still used on the sheet (1 label).")
    expect(power.locator("option:checked")).to_have_text("±9 V")


def test_advanced_power_compares_supplies(page: Page, base_url: str) -> None:
    """Comparing supply voltages without building a supply (D-068)."""
    open_circuit(page, base_url)
    power = page.locator("#power")
    power.select_option("custom")
    form = page.locator('form.popup[aria-label="Power"]')
    form.locator("#rail-sweep-values").fill("9, 18")
    after = updates(page)
    form.locator("#rail-sweep-run").click()
    wait_for_update(page, after)
    expect(page.locator("#sweep-title")).to_have_text("V+: 2 supply voltages")
    expect(page.locator("#sweep-net")).to_have_value("out")


def test_delete_saved_circuit(page: Page, base_url: str) -> None:
    cid = new_circuit(page, base_url, "Doomed")
    menu(page, "file-menu", "menu-delete-circuit")
    expect(page.locator(".ask-title")).to_have_text("Delete the circuit \u201cDoomed\u201d (v1.0)?")
    page.locator("[data-answer='delete']").click()
    page.wait_for_function("location.hash === '#new'")
    expect(page.locator("#circuit-name")).to_have_text("Untitled")
    assert f"{cid}-v1" not in [c["id"] for c in api(page, base_url, "GET", "api/circuits")]
    page.locator("#file-menu").click()
    expect(page.locator("#menu-delete-circuit")).to_be_disabled()  # nothing saved to delete


# ---- Phase 3 acceptance ----------------------------------------------------------


def starter_values(part: dict[str, Any]) -> dict[str, str]:
    """What to type into the inspector to make a placed part match the starter's part."""
    # IN and OUT are fixed refs (D-141): their box is read-only
    values = {} if part["type"] in ("guitar", "amp") else {"ref": part["ref"]}
    if "value" in part:
        values["value"] = part["value"]
    if "model" in part:
        values["model"] = part["model"]
    if part["type"] == "capacitor":
        values["kind"] = part.get("kind", "")
        if "rating_v" in part:  # the electrolytics' ratings (D-211)
            values["rating_v"] = f"{part['rating_v']:g}"
    if part["type"] == "pot":
        values["taper"] = part.get("taper", "B")
        values["rotation"] = str(round(part.get("rotation", 0.5) * 100, 1))
        values["label"] = part.get("label", "")
    return values


def segments(c: dict[str, Any]) -> list[list[list[int]]]:
    """A circuit's wires, each end-order free (a wire has no direction)."""
    return sorted(sorted([w["from"], w["to"]]) for w in c["wires"])


def wire_paths(c: dict[str, Any]) -> list[list[tuple[int, int]]]:
    """The circuit's wires as the wire tool draws them: paths of clicks, each ending on a
    pin, label or a wire already drawn (the tool only ends a wire on one), the bends
    between them plain grid points. Paths are ordered so that each ends on something
    that's there by then."""
    from solum.circuit.io import parse_circuit
    from solum.circuit.parts import pin_positions

    circuit = parse_circuit(c)
    fixed = {tuple(p) for part in circuit.parts for p in pin_positions(part).values()}
    fixed |= {tuple(lb.pos) for lb in circuit.labels}
    segs = [(tuple(w.from_), tuple(w.to)) for w in circuit.wires]
    degree: dict[tuple[int, int], int] = {}
    for a, b in segs:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1

    def on(seg: tuple[Any, Any], p: tuple[int, int]) -> bool:
        (x1, y1), (x2, y2) = seg
        return p not in seg and (
            (x1 == x2 == p[0] and min(y1, y2) < p[1] < max(y1, y2))
            or (y1 == y2 == p[1] and min(x1, x2) < p[0] < max(x1, x2))
        )

    def stop(p: tuple[int, int]) -> bool:
        return p in fixed or degree[p] != 2 or any(on(s, p) for s in segs)

    # chains of segments between stop points
    left = set(range(len(segs)))
    chains: list[list[tuple[int, int]]] = []
    for start in sorted(p for p in degree if stop(p)):
        for i in sorted(left):
            if start not in segs[i] or i not in left:
                continue
            chain, here, j = [start], start, i
            while True:
                left.discard(j)
                a, b = segs[j]
                here = b if a == here else a
                chain.append(here)
                if stop(here):
                    break
                j = next(k for k in left if here in segs[k])
            chains.append(chain)
    assert not left, "a closed loop of wires with nothing on it"

    drawn: list[tuple[Any, Any]] = []

    def there(p: tuple[int, int]) -> bool:
        return p in fixed or any(p in s or on(s, p) for s in drawn)

    paths = []
    while chains:
        chain = next(ch for ch in chains if there(ch[-1]) or there(ch[0]))
        chains.remove(chain)
        path = chain if there(chain[-1]) else chain[::-1]
        paths.append(path)
        drawn += list(itertools.pairwise(path))
    return paths


KEYS = {"resistor": "r", "capacitor": "c", "pot": "p", "bjt": "q", "opamp": "u", "diode": "d",
        "guitar": "i", "amp": "a"}  # fmt: skip


def test_redraw_ts808_matches_the_starter(page: Page, base_url: str, half_drawn: list[str]) -> None:
    starter = json.loads((REPO / "library" / "starters" / "ts808.json").read_text())
    cid = new_circuit(page, base_url, "TS808 redrawn")
    points = [p.get("pos", [0, 0]) for p in starter["parts"]] + [
        lb["pos"] for lb in starter["labels"]
    ]
    xs, ys = [x for x, _ in points], [y for _, y in points]
    show_area(page, min(xs) - 30, min(ys) - 30, max(xs) + 30, max(ys) + 30)

    for part in starter["parts"]:
        if part.get("half") == "b" or part["type"] == "powerunit":
            continue  # placed with its half a: a dual is placed as its chip (D-140, D-179)
        x, y = part.get("pos", [0, 0])  # the file leaves out a part at the origin
        place(page, KEYS[part["type"]], x, y, turns=part.get("rot", 0) // 90)
        inspect(page, starter_values(part))
        if part.get("half") == "a":  # then half b, from beside half a to where it's drawn
            b = next(q for q in starter["parts"] if q["ref"] == part["ref"][:-1] + "B")
            before = views(page)
            drag(page, (x + 120, y), tuple(b["pos"]))
            wait_for_view(page, before)
            # and its power unit, from right of the halves (D-179)
            unit = next(q for q in starter["parts"] if q["ref"] == part["ref"][:-1] + "C")
            before = views(page)
            drag(page, (x + 220, y), tuple(unit["pos"]))
            wait_for_view(page, before)
    for label in starter["labels"]:
        place_label(page, label["net"], *label["pos"])
    page.locator('[data-tool="wire"]').click()  # the wire tool: click, click bends, click a pin
    for path in wire_paths(starter):
        before = views(page)
        for point in path:
            click_at(page, *point)
        wait_for_view(page, before)
    press(page, "Escape")
    press(page, "Control+s")
    expect(page.locator("#dirty")).to_be_hidden()
    # Half-drawn, parts may float with no DC path to ground: the panels say so plainly
    # (`half_drawn` checks the refusals). Nothing else may go wrong.
    expect(page.locator("#error")).to_be_hidden()  # finished: it all simulates

    page.reload()
    wait_for_update(page, 0)
    drawn = api(page, base_url, "GET", f"api/circuits/{cid}")["circuit"]
    original = api(page, base_url, "GET", "api/starters/ts808")["circuit"]

    def by_ref(c: dict[str, Any]) -> dict[str, Any]:  # notes aren't drawn (v30: on the part)
        return {p["ref"]: {k: v for k, v in p.items() if k != "note"} for p in c["parts"]}

    assert by_ref(drawn) == by_ref(original)
    assert sorted(map(json.dumps, drawn["labels"])) == sorted(map(json.dumps, original["labels"]))
    assert segments(drawn) == segments(original)
    assert drawn["power"] == original["power"]

    # same results: DC at every net, the response and the scope at the op-amp output
    runs = [
        api(page, base_url, "POST", "api/run", {"circuit": c, "nodes": ["u2o"], "level": "med"})
        for c in (drawn, original)
    ]
    redrawn, reference = runs
    assert redrawn["op"]["voltages"].keys() == reference["op"]["voltages"].keys()
    for net, v in reference["op"]["voltages"].items():
        assert redrawn["op"]["voltages"][net] == pytest.approx(v, abs=1e-6), net
    for net in ("u2o", "out"):
        assert redrawn["ac"]["nodes"][net] == pytest.approx(reference["ac"]["nodes"][net], abs=0.01)
        a, b = redrawn["tran"]["nodes"][net]["stats"], reference["tran"]["nodes"][net]["stats"]
        assert a["gain_db"] == pytest.approx(b["gain_db"], abs=0.01)
        assert a["clipping"]["thd"] == pytest.approx(b["clipping"]["thd"], abs=1e-4)


def test_quick_navigation_opens_the_last_one(page: Page, base_url: str) -> None:
    """Bug: going to a new sheet and straight on to a circuit could end on the new sheet,
    when the new sheet's answer came back last."""
    open_circuit(page, base_url, "ts808")
    page.route("**/api/blank", lambda route: (time.sleep(0.6), route.continue_()))
    for back in ("#starter/fuzz-face", "#starter/fuzz-face"):
        # on to another circuit, or straight back to the one that was open
        page.evaluate(f"location.hash = '#new'; setTimeout(() => (location.hash = '{back}'), 50)")
        page.wait_for_timeout(1500)
        expect(page.locator("#circuit-name")).to_have_text("Fuzz Face (AC128)")


def test_charge_pump_part(page: Page, base_url: str) -> None:
    """K places a charge pump (D-093): a TC1044S drawn as the datasheets' numbered 8-pin
    box (D-226), all eight pins wireable; boost is pin 1 wired to V+, not a setting (D-234)."""
    page.goto(base_url)
    wait_for_update(page, 0)
    place(page, "k", 0, 120)
    pump_text = page.locator('g.part-text[data-ref="IC1"] .value')
    expect(pump_text).to_have_text("TC1044S")
    numbers = page.locator('g.part-text[data-ref="IC1"] .pin-number')
    expect(numbers).to_have_count(8)
    page.locator('g.part[data-ref="IC1"]').dblclick()
    form = page.locator("form.popup")
    expect(form.locator("#field-model")).to_have_value("TC1044S")
    expect(form.locator("#field-mode")).to_have_count(0)
    expect(form.locator("#field-boost")).to_have_count(0)


def test_drag_a_wire_keeps_its_connections(
    page: Page, base_url: str, half_drawn: list[str]
) -> None:
    """D-095: click a wire to select it, then drag it: it moves, re-laid at its ends so it
    still joins the same pins. A drag that would join something else (here R1's pin) is
    refused and the wire stays put."""
    page.goto(base_url)
    wait_for_update(page, 0)
    before = views(page)
    drag(page, (-280, 0), (280, 0))  # guitar out → amp in, straight along y = 0
    wait_for_view(page, before)
    assert wires(page) == [(-280, 0, 280, 0)]
    click_at(page, 0, 0)  # select it
    expect(page.locator("line.wire.selected")).to_have_count(1)
    before = views(page)
    drag(page, (0, 0), (0, 40))
    wait_for_view(page, before)
    drawn = wires(page)
    assert (-280, 40, 280, 40) in drawn or (280, 40, -280, 40) in drawn
    assert all(w[1] != 0 or w[3] != 0 for w in drawn)  # nothing left along y = 0
    menu(page, "edit-menu", "menu-undo")
    page.wait_for_function("document.querySelectorAll('line.wire').length === 1")
    menu(page, "edit-menu", "menu-redo")
    page.wait_for_function("document.querySelectorAll('line.wire').length > 1")
    # R1 upright with its top pin at (0, 80): dragging the wire onto it would join them
    place(page, "r", 0, 100, turns=1)
    assert part_pos(page, "R1") == (0, 100)
    moved = wires(page)
    click_at(page, -40, 40)
    expect(page.locator("line.wire.selected")).to_have_count(3)  # the whole wire, both bends
    before = views(page)
    drag(page, (-40, 40), (-40, 80))
    expect(page.locator("#hint")).to_contain_text("so the wire stayed put")
    assert views(page) == before and wires(page) == moved


def test_dragging_one_stretch_of_a_wire_stretches_the_rest(page: Page, base_url: str) -> None:
    """D-293 (the user: "I would like to stretch that wire up and out so it clears the
    blocks"): a bent wire is selected whole, but a drag moves only the stretch grabbed; its
    legs get longer or shorter and stay on their pins."""
    page.goto(base_url)
    wait_for_update(page, 0)
    before = views(page)
    drag(page, (-280, 0), (280, 0))  # guitar out → amp in
    wait_for_view(page, before)
    click_at(page, 0, 0)
    before = views(page)
    drag(page, (0, 0), (0, 40))  # now a U: down 40, along, up 40
    wait_for_view(page, before)
    click_at(page, -40, 40)
    expect(page.locator("line.wire.selected")).to_have_count(3)
    before = views(page)
    drag(page, (-40, 40), (-40, 120))  # the bottom stretch, 80 further down
    wait_for_view(page, before)
    drawn = {(min(a, c), min(b, d), max(a, c), max(b, d)) for a, b, c, d in wires(page)}
    assert drawn == {(-280, 0, -280, 120), (-280, 120, 280, 120), (280, 0, 280, 120)}


def test_a_bent_wire_is_one_wire(page: Page, base_url: str) -> None:
    """Clicking one leg of a bent wire selects all of it, and Delete takes all of it out
    (it used to split at the bend and delete one leg)."""
    page.goto(base_url)
    wait_for_update(page, 0)
    before = views(page)
    drag(page, (-280, 0), (60, 60))  # from the guitar's out to a loose end: one bend
    wait_for_view(page, before)
    assert len(wires(page)) == 2
    leg = wires(page)[0]
    click_at(page, (leg[0] + leg[2]) / 2, (leg[1] + leg[3]) / 2)
    expect(page.locator("line.wire.selected")).to_have_count(2)
    before = views(page)
    press(page, "Delete")
    wait_for_view(page, before)
    assert wires(page) == []
    menu(page, "edit-menu", "menu-undo")
    page.wait_for_function("document.querySelectorAll('line.wire').length === 2")


def test_a_new_model_builds_the_transistors_form_again(page: Page, base_url: str) -> None:
    """D-138 (the user: "it should change automatically in the form"): picking another
    model shows what that model asks for, with no Apply and reopen. The Big Muff's Q4 is
    a silicon 2N5089 (gain only); an AC128 is germanium (gain and leakage). Typed values
    stay, and Cancel leaves the part as it was."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    page.locator('g.part[data-ref="Q4"]').dblclick()
    form = page.locator("form.popup")
    expect(form.locator("#field-model_hfe")).to_have_value("748")  # tester gain, not BF (D-153)
    expect(form.locator("#field-model_leakage")).to_have_count(0)
    form.locator("#field-ref").fill("Q9")
    form.locator("#field-model").select_option("AC128")
    form = page.locator("form.popup")
    expect(form.locator("#field-model_hfe")).to_have_value("91.5")
    expect(form.locator("#field-model_leakage")).to_have_value("315")
    expect(form.locator("#field-ref")).to_have_value("Q9")
    form.locator("#field-model").select_option("2N5089")
    expect(page.locator("form.popup #field-model_leakage")).to_have_count(0)
    page.locator('form.popup [data-action="cancel"]').click()
    expect(page.locator('g.part-text[data-ref="Q4"] .value')).to_have_text("2N5089")


def test_undo_puts_back_a_moved_selection(page: Page, base_url: str) -> None:
    """D-148: undo a move and the moved parts and wires are selected again, as they were
    (before, the wires dropped out and the next drag moved the parts alone); redo too."""
    page.goto(f"{base_url}#ts808")
    wait_for_update(page, 0)
    page.keyboard.down("Shift")
    drag(page, (40, -60), (230, 90))
    page.keyboard.up("Shift")
    parts = page.locator("g.part.selected")
    lines = page.locator("line.wire.selected")
    n_parts, n_wires = parts.count(), lines.count()
    assert n_parts >= 2 and n_wires >= 1
    ref = str(parts.first.get_attribute("data-ref"))
    x, y = part_pos(page, ref)
    before = views(page)
    drag(page, (x, y), (x + 40, y))
    wait_for_view(page, before)
    expect(parts).to_have_count(n_parts)
    before = views(page)
    press(page, "Control+z")
    wait_for_view(page, before)
    assert part_pos(page, ref) == (x, y)
    expect(parts).to_have_count(n_parts)
    expect(lines).to_have_count(n_wires)  # the wires came back with it
    before = views(page)
    press(page, "Control+Shift+z")
    wait_for_view(page, before)
    assert part_pos(page, ref) == (x + 40, y)
    expect(lines).to_have_count(n_wires)


def test_import_a_solum_builder_file(
    page: Page, base_url: str, tmp_path: Path, browser_errors: list[str]
) -> None:
    """File → Import… (D-315): a circuit file from elsewhere is saved as a new circuit under
    its own name (or another when that's taken) and opened; a netlist is refused in words."""
    circuit = json.loads((REPO / "library" / "starters" / "fuzz-face.json").read_text())
    ours = tmp_path / "shared.json"
    ours.write_text(json.dumps({**circuit, "name": "Shared fuzz", "starter": False}))
    netlist = tmp_path / "fuzz.cir"
    netlist.write_text("* fuzz\nR1 in out 10k\n.end\n")
    open_circuit(page, base_url)

    menu(page, "file-menu", "menu-import")
    page.locator(".popup button[type=submit]").click()
    expect(page.locator(".popup .error")).to_have_text("Choose a file first.")
    page.locator("#import-file").set_input_files(str(netlist))
    expect(page.locator(".popup .error")).to_contain_text("fuzz.cir isn't a Solum Builder file.")
    page.locator("#import-file").set_input_files(str(ours))
    expect(page.locator(".popup .error")).to_be_hidden()
    expect(page.locator("#field-name")).to_have_value("Shared fuzz")
    page.locator(".popup button[type=submit]").click()
    expect(page.locator("#circuit-name")).to_have_text("Shared fuzz")
    assert "Q1" in drawn_refs(page)
    saved = api(page, base_url, "GET", "api/circuits/shared-fuzz")["circuit"]
    assert (saved["id"], saved.get("starter", False)) == ("shared-fuzz-v1", False)

    # the same file again: the name is taken, so the form says so and takes another
    menu(page, "file-menu", "menu-import")
    page.locator("#import-file").set_input_files(str(ours))
    page.locator(".popup button[type=submit]").click()
    taken = "already have a circuit called Shared fuzz"
    expect(page.locator(".popup .error")).to_contain_text(taken)
    browser_errors.clear()  # the refused save's 422
    page.locator("#field-name").fill("Shared fuzz two")
    page.locator(".popup button[type=submit]").click()
    expect(page.locator("#circuit-name")).to_have_text("Shared fuzz two")
