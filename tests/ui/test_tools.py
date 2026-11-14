# ruff: noqa: E501  (JavaScript inside strings)
"""Tools and Help menus in the browser (D-095): the unit converter, the resistor colour
code, Parts and datasheets (9c), and About. Every number comes from the server; these
check the pages show it."""

import re
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from solum.config import Settings
from solum.settings_file import SETTINGS_FILE
from tests.ui.conftest import open_circuit, reload_kept, run, wait_for_update
from tests.ui.test_editor import menu


def test_unit_converter(page: Page, base_url: str, browser_errors: list[str]) -> None:
    open_circuit(page, base_url)
    menu(page, "tools-menu", "menu-converter")
    expect(page.locator("#tool-value")).to_have_attribute("placeholder", "e.g. 22n, 0.022u, 22000p")
    page.locator("#tool-value").fill("22n")
    result = page.locator("#tool-result")
    expect(result).to_contain_text("22 000pF")
    expect(result).to_contain_text("0.022µF")
    expect(page.locator("#tool-code")).to_have_value("223")
    page.locator("#tool-code").fill("104K")
    expect(page.locator("#tool-value")).to_have_value("100n")
    expect(result).to_contain_text("±10 %")
    page.locator("#tool-quantity").select_option("Ω")
    expect(page.locator("#tool-code")).to_be_hidden()
    # the examples follow the quantity (the user, D-095)
    expect(page.locator("#tool-value")).to_have_attribute("placeholder", "e.g. 4k7, 4700, 2M2")
    page.locator("#tool-value").fill("4k7k")
    expect(page.locator("#unit-converter .error")).to_contain_text("Couldn't read the value")
    assert all("422" in e for e in browser_errors)
    browser_errors.clear()
    page.keyboard.press("Escape")
    expect(page.locator("#unit-converter")).to_have_count(0)


def test_resistor_colour_code(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    menu(page, "tools-menu", "menu-resistor")
    result = page.locator("#resistor-code #tool-result")
    expect(result).to_contain_text("4k7 ±5 %")
    bands = page.locator("#resistor-code .resistor-drawing rect[data-band]")
    expect(bands).to_have_count(4)
    assert bands.evaluate_all("rs => rs.map(r => r.dataset.band)") == [
        "yellow", "violet", "red", "gold",
    ]  # fmt: skip
    page.locator("#tool-ohms").fill("4k1")
    expect(result).to_contain_text("Not a standard value. Nearest: 3k9 or 4k3 (E24, 5 %)")
    expect(result).to_contain_text("4k02 or 4k12 (E96, 1 %)")
    page.locator("#tool-ohms").fill("4k12")
    expect(result).to_contain_text("needs three significant figures: use 5 bands")
    page.locator('[data-bands="5"]').click()
    expect(bands).to_have_count(5)
    assert bands.evaluate_all("rs => rs.map(r => r.dataset.band)")[:4] == [
        "yellow", "brown", "red", "brown",
    ]  # fmt: skip
    # pick the bands: brown black black red brown is 10k ±1 %
    for i, colour in enumerate(["brown", "black", "black", "red", "brown"], start=1):
        page.locator(f"#band-{i}").select_option(colour)
    expect(page.locator("#tool-ohms")).to_have_value("10k")
    expect(result).to_contain_text("10k ±1 %")
    # the chart is in Help; the calculator links to it
    page.locator("#open-resistor-guide").click()
    expect(page.locator("#resistor-guide")).to_be_visible()
    expect(page.locator("#resistor-code")).to_have_count(0)


def test_resistor_colour_chart(page: Page, base_url: str) -> None:
    """Help → Resistor colour code (D-095): the chart like the paper card, every colour
    painted, every multiplier, the tolerance letters, and two labelled examples."""
    open_circuit(page, base_url)
    menu(page, "help-menu", "menu-resistor-guide")
    guide = page.locator("#resistor-guide")
    rows = guide.locator(".colour-chart tbody tr")
    expect(rows).to_have_count(12)
    blue = guide.locator('.colour-chart tr[data-colour="blue"]')
    expect(blue).to_contain_text("\u00d71M")
    expect(blue).to_contain_text("±0.25 % (C)")
    expect(guide.locator('.colour-chart tr[data-colour="white"]')).to_contain_text("\u00d71G")
    expect(guide.locator('.colour-chart tr[data-colour="silver"]')).to_contain_text("\u00d70.01")
    painted = blue.evaluate("(r) => getComputedStyle(r).backgroundColor")
    assert painted == "rgb(47, 109, 181)"  # --band-blue
    four = guide.locator('.band-example[data-bands="4"]')
    expect(four.locator("figcaption")).to_have_text("4 bands: 560kΩ ±5 %")
    says = four.locator(".band-says").evaluate_all("(ts) => ts.map((t) => t.textContent)")
    assert says == ["5", "6", "\u00d710k", "±5 % (J)"]
    five = guide.locator('.band-example[data-bands="5"]')
    expect(five.locator("figcaption")).to_have_text("5 bands: 237Ω ±1 %")
    roles = five.locator(".band-role").evaluate_all("(ts) => ts.map((t) => t.textContent)")
    assert roles == ["1st", "2nd", "3rd", "mult.", "tol."]
    expect(guide).to_contain_text("4.7 kΩ = 4 700 Ω")


def test_hot_keys(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    menu(page, "help-menu", "menu-hotkeys")
    keys = page.locator("#hotkeys")
    expect(keys.locator("h3")).to_have_count(5)
    expect(keys).to_contain_text("Ctrl+Shift+Z or Ctrl+Y")
    expect(keys.locator("tr", has_text="Resistor")).to_contain_text("R")
    page.keyboard.press("Escape")
    expect(keys).to_have_count(0)


def test_about(page: Page, base_url: str) -> None:
    open_circuit(page, base_url)
    menu(page, "help-menu", "menu-about")
    about = page.locator("#about")
    expect(about).to_contain_text("ngspice")
    expect(about.locator("img.about-logo")).to_have_attribute(
        "src", "assets/brand/solum-logo-outlined.svg"
    )
    expect(about).not_to_contain_text("runs on this computer")
    expect(about.locator('a[href="https://www.electrosmash.com"]')).to_have_text("ElectroSmash")
    expect(about.locator('a[href="https://aionfx.com"]')).to_have_text("Aion FX")
    expect(about.locator('a[href="https://solumfx.com"]')).to_have_text("solumfx.com")
    expect(about.locator('a[href="https://github.com/pbexiga/solum-builder"]')).to_be_visible()
    assert about.locator("a").evaluate_all(
        "(as) => as.every((a) => a.target === '_blank' && a.rel === 'noopener')"
    )
    page.locator("#about .sheet-close").click()
    expect(page.locator("#about")).to_have_count(0)


def test_parts_and_datasheets(page: Page, base_url: str, browser_errors: list[str]) -> None:
    """9c: every model by type, its datasheet link, and opened, its caveats from its record."""
    open_circuit(page, base_url)
    menu(page, "tools-menu", "menu-parts")
    sheet = page.locator("#parts-datasheets")
    expect(sheet.locator("h3").first).to_contain_text("Transistors (BJT)")
    n404 = sheet.locator('[data-part="2N404"]')
    expect(n404.locator(".part-origin")).to_have_text("Our fit")
    expect(n404.locator("a.part-sheet")).to_have_attribute(
        "href", re.compile(r"^https://bitsavers")
    )
    n404.locator(".part-desc").click()
    expect(n404.locator(".part-note")).to_contain_text("held flat below 12 mA")
    expect(n404.locator(".part-unchecked li").first).to_contain_text("VBE(sat):")
    page.locator("#parts-search").fill("germanium diode")
    expect(sheet.locator(".part-entry")).not_to_have_count(0)
    expect(sheet.locator('[data-part="2N404"]')).to_have_count(0)
    # our own 1N34A (D-253); LTspice's card beside it, not included
    expect(sheet.locator('details[data-part="1N34A"] .part-origin')).to_have_text("Our fit")
    expect(sheet.locator('[data-part="1N34A"][data-origin="excluded"]')).to_have_count(1)
    # a card we may not ship (9c): listed with an ⓘ saying why and where to get it
    page.locator("#parts-search").fill("AC128")
    excluded = sheet.locator('[data-part="AC128-B120"]')
    expect(excluded.locator(".part-origin")).to_have_text("Not included")
    expect(sheet.locator('[data-part="AC128"] .part-origin')).to_have_text("Our fit")
    excluded.locator(".info-button").click()
    pop = page.locator(".info-pop.in-sheet")
    expect(pop).to_be_visible()
    expect(pop).to_contain_text("CC BY-NC")
    expect(pop).to_contain_text("GERPNP_HIGHGAIN, with Tools → Add a model")
    expect(pop.locator("a")).to_have_attribute("href", "https://www.electrosmash.com/fuzz-face")
    page.keyboard.press("Escape")  # the pop-up first, then the sheet
    expect(pop).to_be_hidden()
    expect(sheet).to_have_count(1)
    # taken out in 9e's licence audit (D-288): listed once, as not included
    page.locator("#parts-search").fill("BC109C")
    expect(sheet.locator('[data-part="BC109C"] .part-origin')).to_have_text("Not included")
    page.locator("#parts-search").fill("zzz")
    expect(sheet).to_contain_text("No part matches that.")
    assert not browser_errors
    page.keyboard.press("Escape")
    expect(sheet).to_have_count(0)


def test_parts_list_words(js: Page) -> None:
    """The list's logic (web/parts.js): types in order, search over id, description and
    maker, and the origin and checks in words."""
    r = run(
        js,
        """
        const p = await m('parts.js');
        const e = (id, type, origin, extra = {}) => ({ id, type, description: id + ' part', maker: 'Philips', origin,
          origin_detail: 'BJT.lib', datasheet: '', package: '', sheet: '', figure: '', note: '', checks: 3, unchecked: [], ...extra });
        const all = [e('1N34A', 'diode', 'library'), e('BC109C', 'bjt', 'library'), e('X1', 'widget', 'maker')];
        return {
          order: p.partGroups(all, '').map((g) => g.name),
          search: p.partGroups(all, 'philips bc1').flatMap((g) => g.entries.map((x) => x.id)),
          library: p.originText(all[1]),
          unnamed: p.originText({ ...all[1], maker: '' }),
          checks: p.checksText(e('A', 'bjt', 'ours', { checks: 1, unchecked: [{ quantity: 'gbw', name: 'Gain-bandwidth', note: 'n' }] })),
          none: p.checksText(e('A', 'bjt', 'ours', { checks: 0 })),
          yoursFirst: p.partGroups([...all, e('ZZ-mine', 'bjt', 'user')], '').map((g) => g.entries.map((x) => x.id)),
          yours: p.partGroups([...all, e('ZZ-mine', 'bjt', 'user')], '', ['yours']).map((g) => g.entries.map((x) => x.id)),
          stock: p.partGroups([...all, e('ZZ-mine', 'bjt', 'user')], 'bc', ['stock']).map((g) => g.entries.map((x) => x.id)),
          nothing: p.partGroups(all, '', []).length,
          excluded: p.partGroups([...all, e('BC109C', 'bjt', 'excluded'), e('ZZ-mine', 'bjt', 'user')], '')[0].entries.map((x) => x.origin),
          stockOnly: p.partGroups([...all, e('BC109C', 'bjt', 'excluded')], 'bc', ['stock']).map((g) => g.entries.map((x) => x.origin)),
          excludedOnly: p.partGroups([...all, e('BC109C', 'bjt', 'excluded')], '', ['excluded']).map((g) => g.entries.map((x) => x.origin)),
          words: p.excludedText(e('2N3904', 'bjt', 'excluded', { why: 'Whose terms.', get: 'the file BJT.lib', card: '2N3904' })),
          ota: p.excludedText(e('LM13700', 'ota', 'excluded', { why: 'W.', get: 'X', card: 'LM13700/NS' }))[2],
        };
        """,
    )
    assert r["order"] == ["Transistors (BJT)", "Diodes", "widget"]
    assert r["search"] == ["BC109C"]
    assert r["library"].startswith(
        "Philips' card, as published in a SPICE library (KiCad-Spice-Library, BJT.lib)"
    )
    assert r["unnamed"].startswith("A card with no maker named")
    assert r["checks"] == ("Meets the 1 datasheet limit it's checked against. Compared with 1 more "
                           "figure the sheet gives no limit for:")  # fmt: skip
    assert r["none"] == "No datasheet limits to check it against."
    # 9c: within a type, yours first; the filter buttons keep yours or the stock ones
    assert r["yoursFirst"] == [["ZZ-mine", "BC109C"], ["1N34A"], ["X1"]]
    assert r["yours"] == [["ZZ-mine"]]
    assert r["stock"] == [["BC109C"]]
    assert r["nothing"] == 0
    # 9c: the cards not included come last in their type, behind their own toggle
    assert r["excluded"] == ["user", "library", "excluded"]
    assert r["stockOnly"] == [["library"]]
    assert r["excludedOnly"] == [["excluded"]]
    assert r["words"] == [
        "Not included with Solum Builder. Whose terms.",
        "To use it, get the file BJT.lib:",
        "Then add its card, 2N3904, with Tools → Add a model; once added, your copy shows in "
        "this list instead.",
    ]
    assert r["ota"].startswith("Tools → Add a model doesn't take OTAs yet")


def test_add_a_model(page: Page, base_url: str) -> None:
    """9c: a maker's file uploaded, a card checked, then added: it's in the parts list."""
    open_circuit(page, base_url)
    menu(page, "tools-menu", "menu-add-model")
    text = (
        "* acme\n.model Q2N3904X NPN(IS=1E-14 VAF=100 BF=300 IKF=0.4 mfg=Acme vceo=40)\n"
        ".model D1N4148X D(IS=2.52n RS=.568 N=1.752 Iave=200m Vpk=75)\n"
    )
    page.locator("#model-file").set_input_files(
        {"name": "acme.lib", "mimeType": "text/plain", "buffer": text.encode()}
    )
    expect(page.locator("#model-card option")).to_have_count(2)
    page.locator("#model-card").select_option("D1N4148X")
    expect(page.locator("#model-as option")).to_have_text(["Diode", "LED"])
    expect(page.locator("#model-id")).to_have_value("D1N4148X")
    page.locator("#model-id").fill("D-ui-acme")
    expect(page.locator("#model-add")).to_be_disabled()
    page.locator("#model-check").click()
    result = page.locator("#model-result")
    expect(result).to_contain_text("Forward voltage")
    expect(result).to_contain_text("Cleaned for the simulator: moved iave=200m")
    page.locator("#model-add").click()
    expect(page.locator("#model-added")).to_contain_text("Added D-ui-acme")
    page.keyboard.press("Escape")
    # a diode's model dropdown: yours first, then the stock ones (9c)
    page.locator('g.part[data-ref="D1"]').dblclick()
    model = page.locator("form.popup #field-model")
    expect(model.locator("optgroup")).to_have_count(2)
    assert model.locator("optgroup").evaluate_all("gs => gs.map((g) => g.label)") == [
        "Added by you",
        "Stock",
    ]
    expect(model.locator('optgroup[label="Added by you"] option')).to_contain_text(["D-ui-acme"])
    expect(model).to_have_value("1N4148")
    page.keyboard.press("Escape")
    menu(page, "tools-menu", "menu-parts")
    added = page.locator('[data-part="D-ui-acme"]')
    expect(added.locator(".part-origin")).to_have_text("Yours")
    # toggles, all on to start: Stock and Not included off leave yours; Yours off too, none
    stock_toggle = page.locator('#parts-datasheets [data-show="stock"]')
    expect(stock_toggle).to_have_attribute("aria-pressed", "true")
    page.locator('#parts-datasheets [data-show="excluded"]').click()
    stock_toggle.click()
    expect(stock_toggle).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#parts-datasheets .part-origin:not(.origin-user)")).to_have_count(0)
    expect(added).to_have_count(1)
    page.locator('#parts-datasheets [data-show="yours"]').click()
    expect(added).to_have_count(0)
    expect(page.locator("#parts-list")).to_contain_text("Turn on Yours, Stock or Not included")
    page.keyboard.press("Escape")
    # its name is taken now: the same card starts as D1N4148X, a different id, but a
    # stock name starts as <card>-mine (a stock model is never replaced)
    menu(page, "tools-menu", "menu-add-model")
    stock = ".model 1N4148 D(IS=2.52n RS=.568 N=1.752)\n"
    page.locator("#model-file").set_input_files(
        {"name": "x.lib", "mimeType": "text/plain", "buffer": stock.encode()}
    )
    expect(page.locator("#model-id")).to_have_value("1N4148-mine")


def test_add_an_op_amp(page: Page, base_url: str, browser_errors: list[str]) -> None:
    """9c: an op-amp .subckt: its pins pre-filled in the usual order beside the maker's
    comment; swapped inputs refused as a wrong pin order; put right, it's added as a dual."""
    lib = Path(__file__).parents[1] / "fixtures" / "models" / "TL072_TI_1989.lib"  # TI's file
    open_circuit(page, base_url)
    menu(page, "tools-menu", "menu-add-model")
    page.locator("#model-file").set_input_files(
        {"name": "tl072.lib", "mimeType": "text/plain", "buffer": lib.read_bytes()}
    )
    expect(page.locator("#model-card option")).to_have_text(["TL072 (.subckt, 5 nodes)"])
    expect(page.locator("#model-as option")).to_have_text(["Op-amp"])
    expect(page.locator(".model-comment")).to_contain_text("NON-INVERTING INPUT")
    expect(page.locator("#model-pin-0")).to_have_value("+")
    expect(page.locator("#model-pin-4")).to_have_value("out")
    page.locator("#model-id").fill("TL072-ui")
    page.locator("#model-pin-0").select_option("-")
    page.locator("#model-pin-1").select_option("+")
    page.locator("#model-check").click()
    expect(page.locator("#new-model .error")).to_contain_text("pin order is probably wrong")
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]  # the refusal
    page.locator("#model-pin-0").select_option("+")
    page.locator("#model-pin-1").select_option("-")
    page.locator("#model-channels").select_option("2")
    page.locator("#model-check").click()
    expect(page.locator("#model-result")).to_contain_text("Output as a buffer")
    page.locator("#model-add").click()
    expect(page.locator("#model-added")).to_contain_text("Added TL072-ui")


def test_guide_pages_change_without_reloading(page: Page, base_url: str) -> None:
    """D-300: a page picked in the guide's list replaces only the page and the list, so the
    guide doesn't flash; the picked link stays where it was on screen (the first page's
    sections above it fold away); its own page's link goes to the top without reloading; and
    Back and Forward still work."""
    page.set_viewport_size({"width": 1200, "height": 400})
    page.goto(f"{base_url}manual/")
    page.evaluate("window.stayed = true")
    link = page.locator("#manual-pages a", has_text="Formulas")
    link.scroll_into_view_if_needed()
    top = link.evaluate("a => a.getBoundingClientRect().top")
    link.click()
    expect(page.locator("main h1")).to_have_text("Formulas")
    expect(page).to_have_url(re.compile(r"/manual/formulas$"))
    expect(page).to_have_title(re.compile(r"^Formulas"))
    expect(page.locator("#manual-pages a[aria-current='page']")).to_have_text("Formulas")
    expect(page.locator("#manual-pages a.part", has_text="Voltage divider")).to_be_visible()
    assert page.evaluate("window.stayed") is True
    current = page.locator("#manual-pages a[aria-current='page']")
    assert current.evaluate("a => a.getBoundingClientRect().top") == pytest.approx(top, abs=1)
    page.locator("#manual-pages a.part", has_text="Voltage divider").click()
    expect(page.locator("#voltage-divider")).to_be_in_viewport()
    current.click()  # the page it's on: back to its top, still no reload
    expect(page.locator("main h1")).to_be_in_viewport()
    assert page.evaluate("window.stayed") is True
    page.go_back()  # the top of Formulas, then its Voltage divider
    expect(page.locator("#voltage-divider")).to_be_in_viewport()
    page.go_back()
    page.go_back()
    expect(page.locator("main h1")).to_have_text("Solum Builder guide")
    page.go_forward()
    expect(page.locator("main h1")).to_have_text("Formulas")
    assert page.evaluate("window.stayed") is True


def test_help_documentation_opens_the_guide_with_search(page: Page, base_url: str) -> None:
    """D-290: Help → Documentation shows the guide's pages in a large window: the page
    list, a search by section, links between pages; Help → Formulas opens on that page;
    Escape closes it, from inside the page too."""
    page.goto(base_url)
    page.locator("#help-menu").click()
    page.locator("#menu-documentation").click()
    guide = page.frame_locator("#manual iframe")
    expect(guide.locator("main h1")).to_have_text("Solum Builder guide")
    expect(guide.locator("#manual-pages a[aria-current='page']")).to_have_text(
        "Solum Builder guide"
    )
    guide.locator("#manual-search").fill("divider")
    # the Formulas section (Tools' Calculators section names it too, D-320)
    result = guide.locator("#manual-results a", has_text="Formulas \u203a Voltage divider")
    expect(result.locator(".where")).to_have_text("Formulas \u203a Voltage divider")
    expect(guide.locator("#manual-pages")).to_be_hidden()
    result.click()
    expect(guide.locator("main h1")).to_have_text("Formulas")
    expect(guide.locator("#voltage-divider")).to_be_in_viewport()
    expect(guide.locator("#manual-pages a.part", has_text="LED resistor")).to_be_visible()
    guide.locator("#manual-search").fill("zzzz")
    expect(guide.locator("#manual-results .empty")).to_have_text(
        "Nothing in the guide matches that."
    )
    # the page it is on, in a tab of its own: an icon with a tooltip, no "tab" in words (D-312)
    pop_out = page.locator("#manual-pop-out")
    expect(pop_out).to_have_text("")
    expect(pop_out.locator("svg")).to_be_visible()
    expect(pop_out).to_have_attribute("title", "Open this page in its own tab or window")
    expect(pop_out).to_have_attribute("aria-label", "Open this page in its own tab or window")
    with page.context.expect_page() as tab:
        page.locator("#manual-pop-out").click()
    assert tab.value.url.endswith("/manual/formulas#voltage-divider")
    tab.value.close()
    guide.locator("main h1").click()
    page.keyboard.press("Escape")  # pressed inside the guide's page
    expect(page.locator("#manual")).to_have_count(0)
    page.locator("#help-menu").click()
    page.locator("#menu-formulas").click()
    expect(page.frame_locator("#manual iframe").locator("main h1")).to_have_text("Formulas")
    page.locator("#manual .sheet-close").click()
    expect(page.locator("#manual")).to_have_count(0)


def kept_settings(page: Page, base_url: str) -> Any:
    return page.request.get(f"{base_url}api/settings").json()


def test_settings_theme(page: Page, base_url: str) -> None:
    """D-303, D-310, D-311: File → Settings… puts a theme on at once; the server keeps it
    and sends the next visit's page with it on (the app's and the guide's), for any
    browser; View no longer has Theme…."""
    open_circuit(page, base_url)
    background = "() => getComputedStyle(document.body).backgroundColor"
    solum = page.evaluate(background)
    page.locator("#view-menu").click()
    expect(page.locator("#menu-reset-panes")).to_be_visible()
    expect(page.locator("#menu-theme")).to_have_count(0)
    page.keyboard.press("Escape")
    menu(page, "file-menu", "menu-settings")
    theme = page.locator("#settings")
    expect(theme.locator(".theme-option")).to_have_count(3)
    expect(theme.locator('[data-theme-id="solum"]')).to_have_attribute("aria-pressed", "true")
    with page.expect_response(lambda r: r.url.endswith("api/settings") and r.request.method == "PUT"):  # fmt: skip
        theme.locator('[data-theme-id="light"]').click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    assert page.evaluate(background) == "rgb(244, 245, 247)"  # --surface-0, light
    expect(page.locator("header img.logo")).to_have_css(
        "content",
        'url("http://'
        + base_url.split("//")[1]
        + 'assets/brand/solum-logo-currentcolor-outlined.svg")',
    )
    page.keyboard.press("Escape")
    expect(theme).to_have_count(0)
    assert kept_settings(page, base_url)["preferences"]["solum.theme"] == "light"
    # the next visit arrives light, from the server: nothing of it is in this browser
    assert page.evaluate("localStorage.getItem('solum.theme')") is None
    assert '<html data-theme="light"' in page.request.get(base_url).text()
    reload_kept(page)
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    page.goto(base_url + "manual/")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    # back to Solum: the attribute goes and nothing is kept
    open_circuit(page, base_url)
    menu(page, "file-menu", "menu-settings")
    with page.expect_response(lambda r: r.url.endswith("api/settings") and r.request.method == "PUT"):  # fmt: skip
        page.locator('#settings [data-theme-id="solum"]').click()
    expect(page.locator("html")).not_to_have_attribute("data-theme", "light")
    assert page.evaluate(background) == solum
    assert "solum.theme" not in kept_settings(page, base_url)["preferences"]


def test_settings_folders_and_cache_size(page: Page, base_url: str, ui_settings: Settings) -> None:
    """D-310: Settings shows the two folders (changed in `.env` here: only the Mac app's
    launcher lets them move) and the cache; a new largest size holds at once, is still
    there after a reload, and a bad one is refused in plain English."""
    open_circuit(page, base_url)
    menu(page, "file-menu", "menu-settings")
    sheet = page.locator("#settings")
    expect(sheet.locator("#settings-data-dir .settings-path")).to_have_text(
        str(ui_settings.data_dir.resolve())
    )
    expect(sheet.locator("#settings-data-dir .settings-how")).to_have_text(
        "To change it, set DATA_DIR (in .env or the environment), then restart."
    )
    expect(sheet.locator(".settings-host")).to_have_count(0)  # not in a container
    expect(sheet.locator("#settings-cache-dir .settings-path")).to_have_text(
        str(ui_settings.cache_dir.resolve())
    )
    expect(sheet.locator("#settings-cache-dir .settings-how")).to_contain_text("CACHE_DIR")
    size = sheet.locator("#settings-cache-size")
    expect(size).to_have_value("2")
    expect(sheet.locator("#settings-cache-used")).to_have_text(
        re.compile(r"^Using \d+ MB of 2\.0 GB now\.$")
    )
    size.fill("0")
    size.press("Enter")
    expect(sheet.locator(".error")).to_have_text("The largest cache size must be more than 0.")
    assert kept_settings(page, base_url)["cache_max_gb"] == 2
    size.fill("1.5")
    size.press("Enter")
    expect(sheet.locator("#settings-cache-used")).to_contain_text("of 1.5 GB now.")
    expect(sheet.locator(".error")).to_be_hidden()
    assert kept_settings(page, base_url)["cache_max_gb"] == 1.5  # no restart
    page.reload()
    wait_for_update(page, 0)
    menu(page, "file-menu", "menu-settings")
    expect(page.locator("#settings-cache-size")).to_have_value("1.5")


def test_a_browsers_old_preferences_are_carried_over_once(
    page: Page, base_url: str, ui_settings: Settings
) -> None:
    """D-311: a browser that chose a theme and a pane order before they moved to the
    server keeps them: the first visit starts in its theme (no flash) and hands them over;
    what stays in the browser is left alone."""
    page.goto(base_url)  # the page's origin, to fill its storage as an older version left it
    page.evaluate(
        """() => {
          localStorage.setItem("solum.theme", '"dark"');
          localStorage.setItem("solum.autorun", "1");
          localStorage.setItem("solum.panes.open", '{"panel-scope": false}');
          localStorage.setItem("solum.capTypes", "1");
        }"""
    )
    (ui_settings.data_dir / SETTINGS_FILE).unlink()
    with page.expect_response(lambda r: r.url.endswith("api/settings") and r.request.method == "PUT"):  # fmt: skip
        page.reload()
    # on from the first paint: the early script ran before any module
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#autorun")).to_be_checked()
    assert page.eval_on_selector("#panel-scope", "(d) => d.open") is False
    page.wait_for_function("!document.documentElement.hasAttribute('data-saving')")
    kept = kept_settings(page, base_url)["preferences"]
    assert (kept["solum.theme"], kept["solum.autorun"]) == ("dark", 1)
    assert kept["solum.panes.open"]["panel-scope"] is False
    page.wait_for_function("localStorage.getItem('solum.theme') === null")
    assert '<html data-theme="dark"' in page.request.get(base_url).text()
    left = page.evaluate("Object.keys(localStorage)")
    assert "solum.capTypes" in left  # the browser's own: stays
    assert not {"solum.theme", "solum.autorun", "solum.panes", "solum.panes.open"} & set(left)
    # from now on they are the server's: a browser's stale copy changes nothing
    page.evaluate("localStorage.setItem('solum.theme', '\"light\"')")
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.evaluate("localStorage.getItem('solum.theme')") is None


def test_calculators(page: Page, base_url: str, browser_errors: list[str]) -> None:
    """Tools → Calculators… (D-319, D-320): one window, a picker, each calculator asked of
    the server as you type, the last one used opening again."""
    open_circuit(page, base_url)
    menu(page, "tools-menu", "menu-calculators")
    pick = page.locator("#calc-pick")
    expect(pick).to_have_value("filter")

    # Filter, with the user's example: 1 µF into 100 kΩ, then 10 µF
    page.locator("#filter-r").fill("100k")
    page.locator("#filter-c").fill("1u")
    result = page.locator("#filter-result")
    expect(result.locator(".filter-answer h3")).to_have_text(["100k and 1µ: 1.59 Hz"])
    expect(result).to_contain_text("1 / (2 × π × 100 kΩ × 1 µF) = 1.59 Hz")
    expect(result).to_contain_text("the whole guitar passes")
    page.locator("#filter-c2").fill("10u")
    expect(page.locator("#filter-change")).to_contain_text("The corner moves 10 times lower")
    page.locator("#filter-c").fill("47x")
    expect(page.locator("#calc-filter .error")).to_contain_text("Couldn't read the value")

    # the same calculator from the corner: 100 Hz into 1M wants 1.59 nF, so 1n5
    page.locator("#filter-c2").fill("")
    expect(page.locator("#filter-series")).to_be_hidden()
    page.locator("#filter-freq").fill("100")
    expect(page.locator("#calc-filter .error")).to_contain_text("leave the third blank")
    expect(page.locator("#filter-series")).to_be_visible()
    page.locator("#filter-r").fill("1M")
    page.locator("#filter-c").fill("")
    expect(page.locator("#filter-found")).to_have_text("1.59 nF: use 1n5 (E12)")
    expect(result).to_contain_text("106 Hz, +6.1 %")

    # Voltage divider: 9 V, 10k and 10k, then a 100k load
    pick.select_option("divider")
    expect(page.locator("#div-supply")).to_have_value("9")
    page.locator("#div-r1").fill("10k")
    page.locator("#div-r2").fill("10k")
    expect(page.locator("#div-middle")).to_have_text("The middle: 4.5 V")
    page.locator("#div-load").fill("100k")
    expect(page.locator("#div-sag")).to_have_text(
        "The load pulls the middle down 4.8 %, from 4.5 V to 4.29 V."
    )

    # Parallel and series: 10k and 22k; 6k5 from E12 parts
    pick.select_option("combine")
    page.locator("#comb-values").fill("10k, 22k")
    expect(page.locator("#combine-result")).to_contain_text("6.88 kΩ")
    page.locator("#comb-target").fill("6k5")
    expect(page.locator("#comb-make tr").nth(1)).to_contain_text("4k7 and 1k8 in series")

    # Decibels, either way
    pick.select_option("db")
    page.locator("#db-db").fill("20")
    expect(page.locator("#db-times")).to_have_value("10")
    page.locator("#db-volts").fill("300m")
    expect(page.locator("#db-out")).to_have_text("300 mV in, 3 V out")
    page.locator("#db-times").fill("2")
    expect(page.locator("#db-db")).to_have_value("+6.0")

    assert all("422" in e for e in browser_errors)
    browser_errors.clear()
    # the last calculator used opens again
    page.keyboard.press("Escape")
    menu(page, "tools-menu", "menu-calculators")
    expect(pick).to_have_value("db")
