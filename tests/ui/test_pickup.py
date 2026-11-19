"""The guitar's pickup by any three of R, L, C, peak and Q (D-363)."""

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import click_part, open_circuit

pytestmark = pytest.mark.ui


def open_guitar(page: Page) -> None:
    click_part(page, "IN")
    page.keyboard.press("Enter")
    expect(page.locator("#field-source")).to_be_visible()


def placeholder(page: Page, name: str) -> str:
    return page.locator(f"#field-pickup_{name}").get_attribute("placeholder") or ""


def test_r_peak_and_q_give_l_and_c_and_reopening_shows_what_was_typed(
    page: Page, base_url: str
) -> None:
    """The user's buddy enters R, peak and Q and sees L and C worked out; reopening shows
    what he typed."""
    open_circuit(page, base_url, "ts808")
    open_guitar(page)
    page.locator("#field-source").select_option("custom")
    line = page.locator("#pickup-line")
    expect(line).to_have_text("Set: R, L, C · worked out: peak, Q")
    page.locator("#field-pickup_r").fill("8k2")
    page.locator("#field-pickup_peak").fill("5k2")
    page.locator("#field-pickup_q").fill("2.1")
    expect(line).to_have_text(
        "Set: R, peak, Q · worked out: L, C (C was set first, so it's worked out now)"
    )
    expect(page.locator("#field-pickup_l")).to_have_value("")
    assert (placeholder(page, "l"), placeholder(page, "c")) == ("≈ 527m", "≈ 1n78")
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_have_count(0)
    open_guitar(page)
    values = {
        n: page.locator(f"#field-pickup_{n}").input_value() for n in ("r", "l", "c", "peak", "q")
    }
    assert values == {"r": "8k2", "l": "", "c": "", "peak": "5k2", "q": "2.1"}
    expect(line).to_have_text("Set: R, peak, Q · worked out: L, C")
    assert placeholder(page, "c") == "≈ 1n78"


def test_a_guide_pickup_shows_its_peak_and_l_c_dims_the_peak(page: Page, base_url: str) -> None:
    """A Strat from the guide shows 8.11 kHz; with only L and C set the peak is dimmed and
    typing into it is refused with why."""
    open_circuit(page, base_url, "ts808")
    open_guitar(page)
    page.locator("#field-source").select_option("strat")
    expect(page.locator("#field-pickup_peak")).to_have_attribute("placeholder", "≈ 8k11")
    assert placeholder(page, "q") == "≈ 20.4"
    page.locator("#field-pickup_r").fill("")
    line = page.locator("#pickup-line")
    expect(line).to_contain_text("L and C set. One more: R or Q. Not the peak: L and C give it.")
    peak = page.locator("#field-pickup_peak")
    expect(peak.locator("xpath=..")).to_have_class("form-row dimmed")
    assert peak.get_attribute("title") == "Not the peak: L and C give it."
    peak.press_sequentially("5")
    expect(peak).to_have_value("")
    expect(page.locator("form.popup .error")).to_have_text("Not the peak: L and C give it.")
    page.locator("#field-pickup_q").fill("20")
    expect(line).to_have_text("Set: L, C, Q · worked out: R, peak")
    expect(page.locator("form.popup .error")).to_be_hidden()
