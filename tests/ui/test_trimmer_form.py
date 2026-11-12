"""A trimmer's form with a bias target (D-127): Remove and Add target swap in place, the
rotation box and its slider follow, and a rotation out of range is said as the box is
left. The JFET test circuit: TR1 holds Q1.D at 9 V. Also the JFET's own form: its Idss
and Vp are the model's or yours, picked."""

import re

from playwright.sync_api import Page, expect

from tests.ui.conftest import open_fixture, updates, wait_for_update

REACH = re.compile(r"^With TR1 \(50k\), Q1\.D can go from .* Checked on Apply\.$")


def open_rt1(page: Page) -> None:
    page.locator('g.part[data-ref="TR1"]').dblclick()
    expect(page.locator("form.popup")).to_be_visible()


def hint_of(page: Page, name: str):  # type: ignore[no-untyped-def]
    return page.locator(f"#field-{name}").locator("xpath=..").locator(".hint-text")


def test_remove_and_add_target_swap_in_place(page: Page, base_url: str) -> None:
    """Remove target hides the target there and then, frees Rotation (and its slider) and
    brings Add target back; Add target puts it back as it was, with no Apply between."""
    open_fixture(page, base_url, "jfet-drive")
    open_rt1(page)
    form = page.locator("form.popup")
    rotation = page.locator("#field-rotation")
    add = page.locator("#field-rotation-add")
    turn = page.locator("#rotation-slider")
    expect(rotation).to_have_js_property("readOnly", True)
    expect(add).to_be_hidden()
    expect(turn).to_be_hidden()  # the target turns it
    expect(page.locator("#field-bias_node")).to_have_value("Q1.D")
    expect(hint_of(page, "bias_volts")).to_have_text(REACH)
    expect(hint_of(page, "rotation")).to_contain_text("Set by its bias target")
    solved = rotation.input_value()
    # Remove: the target goes, Add target comes back, Rotation and its slider are free
    page.locator("#field-bias_volts-remove").click()
    expect(page.locator("#field-bias_node")).to_be_hidden()
    expect(page.locator("#field-bias_volts")).to_be_hidden()
    expect(add).to_be_visible()
    expect(rotation).to_have_js_property("readOnly", False)
    expect(rotation).to_have_value(solved)  # it stays where the target left it
    expect(hint_of(page, "rotation")).to_have_text(
        "Turned by hand from here, once Apply takes the target off."
    )
    expect(turn).to_be_visible()
    expect(turn).to_be_enabled(timeout=15_000)
    # Add: back as it was, the volts at the node's voltage now
    add.click()
    expect(add).to_be_hidden()
    expect(page.locator("#field-bias_node")).to_have_value("Q1.D")
    expect(page.locator("#field-bias_volts")).to_have_value(re.compile(r"^\d+\.\d\d$"))
    expect(hint_of(page, "bias_volts")).to_have_text(REACH)
    expect(rotation).to_have_js_property("readOnly", True)
    expect(turn).to_be_hidden()
    expect(form.locator(".error")).to_be_hidden()
    # Cancel leaves the target as it was
    page.locator("#field-bias_volts-remove").click()
    form.locator('[data-action="cancel"]').click()
    open_rt1(page)
    expect(page.locator("#field-bias_volts")).to_have_value("9")


def test_a_rotation_out_of_range_is_said_as_the_box_is_left(page: Page, base_url: str) -> None:
    """The user's bug: remove the target, type 120 %, Add target: the box went locked at
    120 % and Apply refused it. Now 120 % is said at once, and Add target puts the box
    back (the target turns it), so Apply goes through."""
    open_fixture(page, base_url, "jfet-drive")
    open_rt1(page)
    form = page.locator("form.popup")
    error = form.locator(".error")
    rotation = page.locator("#field-rotation")
    solved = rotation.input_value()
    page.locator("#field-bias_volts-remove").click()
    rotation.fill("120")
    rotation.press("Tab")
    expect(error).to_have_text("Rotation goes from 0 to 100 %.")
    rotation.fill("50")
    rotation.press("Tab")
    expect(error).to_be_hidden()
    rotation.fill("-5")
    rotation.press("Tab")
    expect(error).to_have_text("Rotation goes from 0 to 100 %.")
    rotation.fill("abc")
    rotation.press("Tab")
    expect(error).to_have_text("Rotation must be a number.")
    rotation.fill("120")
    rotation.press("Tab")
    page.locator("#field-rotation-add").click()
    expect(error).to_be_hidden()
    expect(rotation).to_have_value(solved)
    expect(rotation).to_have_js_property("readOnly", True)
    page.locator("#field-bias_volts").fill("9")
    form.locator("button.primary").click()
    expect(form).to_be_hidden()
    # Apply with a bad rotation and no target still refuses
    open_rt1(page)
    page.locator("#field-bias_volts-remove").click()
    rotation.fill("150")
    form.locator("button.primary").click()
    expect(error).to_have_text("Rotation goes from 0 to 100 %.")
    expect(form).to_be_visible()


def test_a_target_removed_on_apply_is_gone_from_the_jfet_too(page: Page, base_url: str) -> None:
    """The drain target is the trimmer's target, seen from Q1's form: removed in one, it's
    gone from both. Reopened, TR1 offers Add target; a target out of reach is refused,
    one in reach goes in, and Q1's form shows it."""
    open_fixture(page, base_url, "jfet-drive")
    open_rt1(page)
    form = page.locator("form.popup")
    page.locator("#field-bias_volts-remove").click()
    page.locator("#field-rotation").fill("40")
    form.locator("button.primary").click()
    expect(form).to_be_hidden()
    page.locator('g.part[data-ref="Q1"]').dblclick()
    expect(page.locator("#field-drain_volts")).to_have_value("")
    expect(page.locator("#field-drain_trimmer")).to_have_value("")
    form.locator('[data-action="cancel"]').click()
    open_rt1(page)
    expect(page.locator("#field-rotation")).to_have_value("40")
    expect(page.locator("#field-bias_node")).to_be_hidden()
    expect(hint_of(page, "rotation")).to_have_text(
        "Turned by hand. To hold a voltage instead: Add target."
    )
    expect(page.locator("#rotation-slider")).to_be_visible()
    page.locator("#field-rotation-add").click()
    expect(hint_of(page, "rotation")).to_have_text(
        "Turned to the target on Apply, and again on every run."
    )
    expect(page.locator("#rotation-slider")).to_be_hidden()
    expect(hint_of(page, "bias_volts")).to_have_text(REACH)
    page.locator("#field-bias_volts").fill("30")
    form.locator("button.primary").click()
    expect(form.locator(".error")).to_contain_text("can go from")
    page.locator("#field-bias_volts").fill("8")
    form.locator("button.primary").click()
    expect(form).to_be_hidden()
    page.locator('g.part[data-ref="Q1"]').dblclick()
    expect(page.locator("#field-drain_volts")).to_have_value("8")
    expect(page.locator("#field-drain_trimmer")).to_have_value("TR1")


def test_turning_it_after_remove_target_takes_the_target_off(page: Page, base_url: str) -> None:
    """Rotation's slider shows once the target is removed in the form; turning it is an
    edit, so it takes the target off then (the DC overlay's held colour goes)."""
    open_fixture(page, base_url, "jfet-drive")
    page.locator("#view-menu").click()
    page.locator("#menu-dc").click()
    held = page.locator(".dc-layer text.held")
    expect(held).to_have_count(1)
    open_rt1(page)
    page.locator("#field-bias_volts-remove").click()
    turn = page.locator("#rotation-slider")
    expect(turn).to_be_enabled(timeout=15_000)
    turn.focus()
    turn.press("ArrowRight")
    expect(held).to_have_count(0, timeout=15_000)
    page.locator("form.popup button.primary").click()
    expect(page.locator("form.popup")).to_be_hidden()
    expect(held).to_have_count(0)


def test_a_jfets_idss_and_vp_are_the_models_or_yours(page: Page, base_url: str) -> None:
    """Round 3b: picked, not left blank. The test JFET has measured values (0.6 mA,
    -0.8 V); the model's are a J201's (0.447 mA, -0.671 V), where yours start."""
    open_fixture(page, base_url, "jfet-drive")
    page.locator('g.part[data-ref="Q1"]').dblclick()
    form = page.locator("form.popup")
    spec = page.locator("#field-jfet_spec")
    idss = page.locator("#field-idss")
    expect(spec).to_have_value("measured")
    expect(idss).to_have_value("0.6")
    expect(page.locator("#field-vp")).to_have_value("-0.8")
    idss.fill("abc")
    idss.press("Tab")
    expect(form.locator(".error")).to_have_text("Measured Idss must be a number.")
    idss.fill("")
    idss.press("Tab")
    expect(form.locator(".error")).to_be_hidden()
    form.locator("button.primary").click()
    expect(form.locator(".error")).to_have_text(
        "Give your JFET's measured Idss and Vp, or pick the model's."
    )
    spec.select_option("model")
    expect(idss).to_be_hidden()
    form.locator("button.primary").click()
    expect(form).to_be_hidden()
    page.locator('g.part[data-ref="Q1"]').dblclick()
    expect(spec).to_have_value("model")
    expect(idss).to_be_hidden()
    spec.select_option("measured")
    expect(idss).to_have_value("0.447")
    expect(page.locator("#field-vp")).to_have_value("-0.671")


def test_a_source_trimmer_holds_the_drain(page: Page, base_url: str) -> None:
    """Round 3b: a trimmer in the source leg (TR1, source to ground; RD a fixed 10k) still
    holds the drain: Add target offers Q1.D, not Q1.S, at its voltage now, with how far
    the trimmer moves it; applied, the drain is the held node."""
    open_fixture(page, base_url, "jfet-source-trim")
    open_rt1(page)
    form = page.locator("form.popup")
    page.locator("#field-rotation-add").click()
    node = page.locator("#field-bias_node")
    expect(node).to_have_value("Q1.D")
    expect(node).to_have_js_property("readOnly", True)
    expect(page.locator("#field-bias_volts")).to_have_value(re.compile(r"^\d+\.\d\d$"))
    reach = r"^With TR1 \(5k\), Q1\.D can go from .* Checked on Apply\.$"
    expect(hint_of(page, "bias_volts")).to_have_text(re.compile(reach))
    form.locator("button.primary").click()
    expect(form).to_be_hidden()
    before = updates(page)
    page.locator("#run").click()  # auto-run is off on a new sheet
    wait_for_update(page, before)
    page.locator("#view-menu").click()
    page.locator("#menu-dc").click()
    held = page.locator(".dc-layer text.held title")
    expect(held).to_have_count(1)
    expect(held).to_have_text(re.compile(r"^target .* V, held by TR1 at \d+ %$"))
