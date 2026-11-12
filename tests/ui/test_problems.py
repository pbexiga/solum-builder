"""The Problems panel in the browser (Phase 5, D-077)."""

import zipfile

from playwright.sync_api import Page, expect

from tests.ui.conftest import click_part, open_circuit, updates, wait_for_update
from tests.ui.test_editor import (
    api,
    delete_part,
    inspect,
    menu,
    place,
    press,
    save_as,
    views,
    wait_for_view,
)


def test_a_good_starter_has_no_problems(page: Page, base_url: str) -> None:
    """Nothing for the build either: its parts list is filled in (D-211). Notes for the
    build wait under Before you build: not counted, not marked on the sheet (D-203)."""
    open_circuit(page, base_url)
    expect(page.locator("#problems-body > p.empty")).to_have_text("No problems found.")
    expect(page.locator("#problem-count")).to_have_text("")
    expect(page.locator("#problems-build")).to_have_count(0)
    clear_kind(page, "C1")
    run(page)
    build = page.locator("#problems-build")
    expect(build.locator("> summary")).to_have_text("Before you build \u00b7 1")
    expect(build).not_to_have_attribute("open", "")
    expect(page.locator("#problem-count")).to_have_text("")
    expect(page.locator("#schematic .problem-mark")).to_have_count(0)
    build.locator("> summary").click()
    row = build.locator("details.problem[data-rule='cap-no-kind']")
    expect(row.locator(".problem-where")).to_have_text("C1")


def clear_kind(page: Page, ref: str) -> None:
    """Select a capacitor and set its Kind to none."""
    click_part(page, ref)
    inspect(page, {"kind": ""})


def test_export_lists_what_to_check_and_the_parts_list(page: Page, base_url: str) -> None:
    """File → Export (D-203): Ready to build from the last save (changes since aren't in
    it), each row's part a click away; the parts list as CSV and as a page."""
    open_circuit(page, base_url)
    clear_kind(page, "C1")
    clear_kind(page, "C2")
    click_part(page, "C9")
    inspect(page, {"rating_v": ""})
    cid = save_as(page, "Untyped")  # the starters' lists are filled in (D-211)
    delete_part(page, "R2")  # unsaved now
    menu(page, "file-menu", "menu-export")
    sheet = page.locator("#export")
    rows = sheet.locator(".export-row")
    expect(rows.first).to_contain_text("changes since the last save")
    expect(sheet.locator(".export-row", has_text="no voltage rating")).to_have_count(1)
    expect(sheet.locator(".export-row", has_text="have no type")).to_have_count(1)
    href = sheet.locator("#export-bom-csv").get_attribute("href")
    assert href == f"api/export/circuit/{cid}/bom.csv"
    bias = sheet.locator("#export-bias-page")
    assert bias.get_attribute("href") == f"api/export/circuit/{cid}/bias.html"
    assert bias.get_attribute("target") == "_blank"
    notes = sheet.locator("#export-notes-pdf")
    assert notes.get_attribute("href") == f"api/export/circuit/{cid}/notes.pdf"
    assert sheet.locator("#export-wiring-page").get_attribute("target") == "_blank"
    body = page.request.get(f"{base_url}{href}").text()
    assert "RC4558" in body
    for button, name in (("svg", "schematic.svg"), ("pdf", "schematic.pdf")):  # D-205
        with page.expect_download() as got:
            sheet.locator(f"#export-schematic-{button}").click()
        assert got.value.suggested_filename == f"Untyped {name}"
    with page.expect_download() as got:  # D-210: the rows shown go in the index
        sheet.locator("#export-package").click()
    assert got.value.suggested_filename == "Untyped build package.zip"
    with zipfile.ZipFile(got.value.path()) as z:
        index = next(n for n in z.namelist() if n.endswith("/index.html"))
        text = z.read(index).decode()
        svg = z.read(index.replace("index.html", "schematic.svg")).decode()
    assert "changes since the last save" in text and "have no type" in text
    assert 'class="sch-' not in svg and "<svg" in svg  # the printable drawing
    sheet.locator(".export-row", has_text="have no type").click()
    expect(sheet).to_have_count(0)
    expect(page.locator("#schematic .part.selected[data-ref='C1']")).not_to_have_count(0)


def test_an_unsaved_sheet_has_nothing_to_export_yet(page: Page, base_url: str) -> None:
    page.goto(base_url)
    wait_for_update(page, 0)
    menu(page, "file-menu", "menu-export")
    expect(page.locator("#export .export-why")).to_contain_text("Save the circuit first")


def test_breaking_a_circuit_lists_its_problems(page: Page, base_url: str) -> None:
    """Deleting R2, the bias resistor of the TS808's input buffer Q1, leaves Q1's base
    unbiased and Q1 cut off. Each problem says why and what to do, and a click on one
    selects the part it's about."""
    open_circuit(page, base_url)
    delete_part(page, "R2")
    run(page)
    rows = page.locator("#problems-body details.problem")
    expect(rows.first).to_be_visible()
    rules = rows.evaluate_all("rows => rows.map(r => r.dataset.rule)")
    assert {"transistor-input-unbiased", "bjt-cut-off"} <= set(rules)
    expect(page.locator("#problem-count")).to_have_text("\u00b7 2 warnings")

    row = page.locator("#problems-body details.problem[data-rule='bjt-cut-off']")
    row.locator("summary").click()
    expect(row.locator(".problem-message")).to_have_text(
        "Q1 is cut off: no collector current flows."
    )
    expect(row.locator(".problem-body")).to_contain_text("Fix:")
    expect(page.locator("#schematic .part.selected[data-ref='Q1']")).not_to_have_count(0)
    expect(row).to_have_attribute("open", "")  # still open after the probe re-ran


def test_a_floating_net_stops_the_run_with_a_plain_message(
    page: Page, base_url: str, browser_errors: list[str]
) -> None:
    """Two caps in series to ground leave the net between them with no DC path: nothing
    is simulated (ngspice would make up a voltage there) and both the banner and the list
    say why."""
    circuit = page.request.get(f"{base_url}api/starters/ts808").json()["circuit"]
    for ref, pos in (("C98", [880, 900]), ("C99", [880, 1000])):
        circuit["parts"].append({"ref": ref, "type": "capacitor", "value": "47n", "pos": pos})
    for x, y, net in ((860, 900, "GND"), (900, 900, "x"), (860, 1000, "x"), (900, 1000, "GND")):
        circuit["labels"].append({"net": net, "pos": [x, y]})  # the caps' pins (±20)
    made = {"circuit": circuit, "name": "floating x"}
    saved = page.request.post(f"{base_url}api/circuits", data=made).json()["circuit"]["id"]
    open_circuit(page, base_url, f"circuit/{saved}")
    first = page.locator("#problems-body details.problem").first
    expect(first).to_have_attribute("data-rule", "no-dc-path")
    expect(page.locator("#error")).to_have_text(
        "Can't simulate yet: net x has no DC path to ground."
    )
    expect(page.locator("#problems-body")).to_contain_text("wasn't simulated")
    assert all("422" in e for e in browser_errors)  # the refused run, expected
    browser_errors.clear()


def test_a_part_left_hanging_is_named_and_the_rest_runs(page: Page, base_url: str) -> None:
    """The user (2026-11-02): an unwired part stopped every curve. Deleting R1 leaves the
    input cap C1 joined by one pin: no current flows through it, so the simulation leaves
    it out, the circuit still runs, and the Problems panel names it (D-165)."""
    open_circuit(page, base_url)
    delete_part(page, "R1")
    run(page)
    row = page.locator("#problems-body details.problem[data-rule='part-not-simulated']")
    row.locator("summary").click()
    expect(row.locator(".problem-message")).to_have_text(
        "C1 isn't wired into the circuit (pin 2 connects to nothing), "
        "so the simulation leaves it out."
    )
    expect(page.locator("#error")).to_be_hidden()
    expect(page.locator("#problems-body")).not_to_contain_text("wasn't simulated")


def test_problem_marks_and_dismissing(page: Page, base_url: str) -> None:
    """D-176: each problem is marked on the sheet by severity (View → Problem marks hides
    them); the mark's tooltip is the message and a click opens its row. Dismissed with a
    reason, a problem moves to Dismissed and loses its mark; undo and Bring back return it."""
    open_circuit(page, base_url)
    delete_part(page, "R2")  # Q1's base unbiased, Q1 cut off: two warnings
    run(page)
    mark = page.locator("#schematic .problem-mark[data-mark='bjt-cut-off|Q1']")
    expect(mark).to_have_class("problem-mark sev-warning")
    expect(mark.locator("title")).to_have_text("Q1 is cut off: no collector current flows.")
    mark.hover()  # its tooltip; the mark stays put
    menu(page, "view-menu", "menu-marks")
    expect(page.locator("#schematic .problem-mark")).to_have_count(0)
    menu(page, "view-menu", "menu-marks")
    expect(mark).to_be_visible()

    page.evaluate("document.getElementById('panel-problems').open = false")
    mark.click()
    row = page.locator("#problems-body > .problem-list > details.problem[data-rule='bjt-cut-off']")
    expect(row).to_have_attribute("open", "")
    expect(page.locator("#panel-problems")).to_have_attribute("open", "")

    before = views(page)
    row.locator(".problem-dismiss").click()
    page.locator("#field-reason").fill("  a starved fuzz, on purpose ")
    page.locator("form.popup button.primary").click()
    wait_for_view(page, before)
    expect(mark).to_have_count(0)
    expect(page.locator("#problem-count")).to_have_text("· 1 warning")
    gone = page.locator("#problems-dismissed details.problem[data-rule='bjt-cut-off']")
    expect(page.locator("#problems-dismissed > summary")).to_have_text("Dismissed · 1")
    expect(gone.locator(".problem-reason")).to_have_text("Dismissed: a starved fuzz, on purpose")
    expect(row).to_have_count(0)

    before = views(page)
    press(page, "Control+z")  # an edit like any other
    wait_for_view(page, before)
    expect(mark).to_be_visible()
    expect(page.locator("#problems-dismissed")).to_have_count(0)
    before = views(page)
    press(page, "Control+y")
    wait_for_view(page, before)
    expect(mark).to_have_count(0)

    saved = save_as(page, "starved")  # kept with the circuit, reason and all
    file = api(page, base_url, "GET", f"api/circuits/{saved}")["circuit"]
    assert file["dismissed"] == [
        {"rule": "bjt-cut-off", "refs": ["Q1"], "reason": "a starved fuzz, on purpose"}
    ]
    expect(page.locator("#problems-dismissed > summary")).to_have_text("Dismissed · 1")
    expect(mark).to_have_count(0)

    page.locator("#problems-dismissed > summary").click()
    expect(gone).to_have_attribute("open", "")  # it was open when dismissed
    before = views(page)
    gone.locator(".problem-restore").click()
    wait_for_view(page, before)
    expect(mark).to_be_visible()
    expect(page.locator("#problem-count")).to_have_text("· 2 warnings")
    expect(page.locator("#problems-dismissed")).to_have_count(0)


def run(page: Page) -> None:
    before = updates(page)
    press(page, "Control+Enter")
    wait_for_update(page, before)


def test_capacitor_kind_hints_and_advice(page: Page, base_url: str) -> None:
    """D-095: the Kind dropdown says what each kind is for, and a general-purpose ceramic in
    the signal path gets advice that points to Help → Choosing capacitors; the Kind field's
    "Choosing capacitors" link opens that sheet."""
    open_circuit(page, base_url)
    click_part(page, "C3")  # 47n, R4's cap to ground in the TS808's clipping stage
    press(page, "Enter")
    options = page.locator("#field-kind option").all_inner_texts()
    assert "film · signal path, the default for audio" in options
    assert "ceramic · supply decoupling only" in options
    link = page.locator('form.popup button.link[data-help="capacitors"]')
    expect(link).to_have_text("Choosing capacitors")
    link.click()  # opens Help → Choosing capacitors
    expect(page.locator("#capacitor-guide")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#capacitor-guide")).to_have_count(0)
    if page.locator("form.popup").count():
        press(page, "Escape")
    inspect(page, {"kind": "ceramic"})
    run(page)
    row = page.locator("#problems-body details.problem[data-rule='cap-kind-signal-path']")
    row.locator("summary").click()
    expect(row.locator(".problem-message")).to_have_text(
        "C3 is a general-purpose ceramic capacitor in the signal path."
    )
    expect(row.locator(".problem-body")).to_contain_text("Use a film capacitor for C3.")
    menu(page, "help-menu", "menu-capacitors")
    expect(page.locator("#capacitor-guide tr[data-kind='c0g']")).to_contain_text("C0G / NP0")
    page.keyboard.press("Escape")
    expect(page.locator("#capacitor-guide")).to_have_count(0)


def test_a_long_problem_list_scrolls(page: Page, base_url: str, half_drawn: list[str]) -> None:
    """D-095: about six problems show; the rest scroll inside the Problems pane."""
    open_circuit(page, base_url)
    for i in range(8):  # loose resistors under the TS808: each pin left open is a problem
        place(page, "r", 260 + 60 * i, 380)
    run(page)
    rows = page.locator("#problems-body details.problem")
    expect(rows.nth(7)).to_be_attached()
    box = page.locator("#problems-body > .problem-list").evaluate(
        """(l) => {
          const end = l.getBoundingClientRect().bottom + 1;
          const seen = [...l.children].filter((r) => r.getBoundingClientRect().bottom <= end);
          return { shown: l.clientHeight, all: l.scrollHeight, seen: seen.length };
        }"""
    )
    assert box["all"] > box["shown"]  # it scrolls
    assert 5 <= box["seen"] <= 7  # about six rows
