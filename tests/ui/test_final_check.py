"""The check before a version becomes final (D-362): Mark as final and New major version…
run Export's Ready to build check on the last save, and list what's open in a window with
Mark as final anyway and Cancel."""

from typing import Any

from playwright.sync_api import Page, expect

from tests.ui.conftest import wait_for_update
from tests.ui.test_blocks import answer
from tests.ui.test_editor import api, menu


def ts808_copy(page: Page, base_url: str, name: str, dismissed: list[Any] | None = None) -> str:
    """The TS808 saved as a circuit of ours called `name`, with C9 (an electrolytic) missing
    its rating, and open. Returns its short link."""
    page.goto(base_url)
    wait_for_update(page, 0)
    circuit = api(page, base_url, "GET", "api/starters/ts808")["circuit"]
    for part in circuit["parts"]:
        if part["ref"] == "C9":
            del part["rating_v"]
    if dismissed:
        circuit["dismissed"] = dismissed
    made = api(page, base_url, "POST", "api/circuits", {"circuit": circuit, "name": name})
    cid = str(made["circuit"]["id"]).rsplit("-v", 1)[0]
    page.goto(f"{base_url}#circuit/{cid}")
    expect(page.locator("#circuit-name")).to_have_text(name)
    return cid


def is_final(page: Page, base_url: str, cid: str) -> bool:
    return bool(api(page, base_url, "GET", f"api/circuits/{cid}")["circuit"].get("final"))


def mark_final(page: Page) -> None:
    menu(page, "file-menu", "menu-properties")
    page.locator("#toggle-final").click()


def test_mark_as_final_checks_first(page: Page, base_url: str) -> None:
    """An electrolytic missing its rating: the window lists it; Cancel leaves the circuit
    as it was; a row closes it and Properties and selects the part; anyway marks it final."""
    cid = ts808_copy(page, base_url, "Final check")
    mark_final(page)
    window = page.locator("#final-check")
    expect(window).to_be_visible()
    expect(window.locator(".ask-title")).to_have_text(
        "“Final check” v1.0 has something outstanding"
    )
    row = window.locator(".export-row", has_text="no voltage rating")
    expect(row).to_contain_text("C9")
    # Enter is Cancel: never final past its problems by a stray key
    expect(window.locator("[data-answer='cancel']")).to_be_focused()
    answer(page, "cancel")
    expect(page.locator("form.popup .error")).to_have_text("Not marked final.")
    assert not is_final(page, base_url, cid)
    page.locator("form.popup [data-action='cancel']").click()
    # a row: the window and Properties close, and its part is selected
    mark_final(page)
    window.locator(".export-row", has_text="no voltage rating").click()
    expect(page.locator(".ask")).to_have_count(0)
    expect(page.locator("form.popup")).to_have_count(0)
    expect(page.locator('g.part.selected[data-ref="C9"]')).to_have_count(1)
    assert not is_final(page, base_url, cid)
    # anyway
    mark_final(page)
    answer(page, "anyway")
    expect(page.locator("#badges")).to_contain_text("final")
    assert is_final(page, base_url, cid)


def test_a_dismissed_problem_does_not_count(page: Page, base_url: str) -> None:
    """The same note dismissed in Problems: nothing is open, so it's marked final at once."""
    cid = ts808_copy(page, base_url, "Final dismissed", [{"rule": "cap-no-rating", "refs": ["C9"]}])
    mark_final(page)
    expect(page.locator("form.popup")).to_have_count(0)
    expect(page.locator("#badges")).to_contain_text("final")
    expect(page.locator(".ask")).to_have_count(0)
    assert is_final(page, base_url, cid)


def test_new_major_version_checks_first(page: Page, base_url: str) -> None:
    """New major version keeps the current version final, so it checks too: Cancel stays
    at v1; anyway goes on to the usual question."""
    ts808_copy(page, base_url, "Major check")
    menu(page, "file-menu", "menu-new-major")
    expect(page.locator("#final-check")).to_be_visible()
    answer(page, "cancel")
    expect(page.locator("#badges")).to_have_text("v1.0")
    menu(page, "file-menu", "menu-new-major")
    page.locator("#final-check [data-answer='anyway']").click()  # the next question follows
    expect(page.locator(".ask-title")).to_have_text("Start version 2 of “Major check”?")
    answer(page, "go")
    expect(page.locator("#badges")).to_have_text("v2.0")
