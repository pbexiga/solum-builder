# ruff: noqa: E501  (JavaScript inside strings)
"""The Audio panel in the browser, incl. Phase 7 acceptance, and `audio-logic.js`."""

import re
import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from playwright.sync_api import Page, expect

from solum.audio.wav import Audio, write_wav
from tests.ui.conftest import info_text, open_circuit, run, wait_for_update

REPO = Path(__file__).parents[2]
NAM = REPO / "tests" / "fixtures" / "nam" / "standard-random.nam"


def plucks(path: Path, seconds: float = 5.0, rate: int = 44100) -> Path:
    """A clip like a played riff: decaying plucked notes, peak 0.5."""
    t = np.arange(int(rate * seconds)) / rate
    notes = [82.4, 110.0, 146.8, 196.0, 110.0]
    x = np.zeros_like(t)
    for i, f in enumerate(notes):
        on = t >= i * seconds / len(notes)
        dt = t[on] - i * seconds / len(notes)
        x[on] += np.exp(-dt * 3) * sum(np.sin(2 * np.pi * f * k * dt) / k for k in (1, 2, 3))
    path.write_bytes(write_wav(Audio(rate, 0.5 * x / np.max(np.abs(x)))))
    return path


def upload(page: Page, kind: str, path: Path) -> None:
    row = page.locator(f'#audio-body select[data-kind="{kind}"]').locator("xpath=..")
    row.locator('input[type="file"]').set_input_files(str(path))
    expect(page.locator(".audio-status")).to_contain_text(f"Added {path.stem}")


def open_chip(page: Page, chip: str) -> None:
    """Open a stage's drawer in the signal chain (one is open at a time). Tried again if
    the click didn't open it: `test_the_audio_settings_are_remembered` has failed here
    under load a few times with the chip still closed (not reproduced alone; most likely
    a pane above still filling in after the reload, moving the chip from under the
    click)."""
    button = page.locator(f'[data-chip="{chip}"]')
    drawer = page.locator(f'[data-drawer="{chip}"]')
    for _ in range(2):
        if button.get_attribute("aria-expanded") != "true":
            button.click()
        if drawer.is_visible():
            return
        page.wait_for_timeout(200)
    if button.get_attribute("aria-expanded") != "true":
        button.click()
    expect(drawer).to_be_visible()


# The loaded take's key, from its download link's path: the link's file name carries the
# time the take was made, so a minute's rollover mid-test would change the whole link.
TAKE_KEY = "new URL(document.querySelector('#audio-body a.button').href).pathname"


def render_and_wait(page: Page, timeout: float = 120_000) -> None:
    page.get_by_role("button", name="Render", exact=True).click()
    page.wait_for_function(
        "() => { const s = document.querySelector('.audio-status'); const b = document.querySelector('#audio-body button.primary');"
        " return !b.disabled && !b.classList.contains('cancel') && s.textContent && !s.textContent.startsWith('Rendering') && !s.textContent.startsWith('Waiting'); }",
        timeout=timeout,
    )


def meter_peak(text: str) -> float:
    """The dBFS figure in the meter's first line ("Amp: … · peaks … dBFS going in")."""
    found = re.search(r"peaks (-?[\d.]+) dBFS", text)
    assert found, text
    return float(found.group(1))


def test_ts808_renders_plays_through_a_capture_and_replays_from_cache(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    """Phase 7 acceptance: a 5 s clip through the TS808 renders, plays through a NAM
    capture, and re-plays instantly from cache."""
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "riff.wav"))
    upload(page, "captures", NAM)
    expect(page.locator('select[data-kind="captures"]')).to_have_value("user:standard-random")
    render_and_wait(page)
    status = page.locator(".audio-status")
    expect(status).to_contain_text("5.0 s")
    meter = page.locator(".audio-meter")
    expect(meter).to_contain_text("Amp: ")
    expect(meter).to_contain_text("Guitar alone: ")
    pedal = page.locator('[data-slot="pedal"]')
    expect(pedal).to_have_attribute("aria-checked", "true")
    expect(page.locator('[data-slot="dry"]')).to_be_enabled()
    # the player has the render loaded and it plays
    page.wait_for_function("document.querySelector('#audio-body audio').readyState >= 2")
    assert page.evaluate("document.querySelector('#audio-body audio').duration") == 5.0
    expect(
        page.locator("#audio-bar-play")
    ).to_be_enabled()  # the shrunk bar's Play, now a take is in
    page.evaluate("document.querySelector('#audio-body audio').muted = true")
    page.evaluate("document.querySelector('#audio-body audio').play()")
    page.wait_for_function("document.querySelector('#audio-body audio').currentTime > 0.2")
    first = page.evaluate("document.querySelector('#audio-body audio').src")
    # A/B keeps the place in the clip, from the take already in memory (no wait to load)
    at = page.evaluate("document.querySelector('#audio-body audio').currentTime")
    page.locator('[data-slot="dry"]').click()
    expect(page.locator('[data-slot="dry"]')).to_have_attribute("aria-checked", "true")
    expect(pedal).to_have_attribute("aria-checked", "false")
    page.wait_for_function(f"document.querySelector('#audio-body audio').currentTime >= {at}")
    assert page.evaluate("document.querySelector('#audio-body audio').src").startswith("blob:")
    # clicking a take starts it when the player is paused
    page.evaluate("document.querySelector('#audio-body audio').pause()")
    page.locator('[data-slot="pedal"]').click()
    page.wait_for_function("!document.querySelector('#audio-body audio').paused")
    page.evaluate("document.querySelector('#audio-body audio').pause()")
    # the same render again comes straight from the cache
    started = time.monotonic()
    render_and_wait(page, timeout=5_000)
    assert time.monotonic() - started < 2.0
    assert page.evaluate("document.querySelector('#audio-body audio').src") == first
    expect(status).to_contain_text("5.0 s")  # a cached take keeps its stats
    # shrunk to its bar, Dry / Pedal still show which one plays (D-115)
    page.locator("#audio-expand").click()
    page.locator("#frequency-expand").click()  # Audio shrinks to its bar
    bar = page.locator("#panel-audio > summary")
    bar.locator('[data-slot="dry"]').click()
    expect(bar.locator('[data-slot="dry"]')).to_have_attribute("aria-checked", "true")
    expect(bar.locator('[data-slot="pedal"]')).to_have_attribute("aria-checked", "false")
    bar.locator('[data-slot="pedal"]').click()
    expect(bar.locator('[data-slot="pedal"]')).to_have_attribute("aria-checked", "true")
    page.locator("#frequency-expand").click()  # Frequency back in the panel
    title(page, "panel-audio")  # Audio's bar opens it large again
    page.locator("#audio-expand").click()
    expect(page.locator(".large-view.expanded")).to_have_count(0)
    page.evaluate("document.querySelector('#audio-body audio').pause()")
    before = meter.text_content() or ""
    # Input turns the amp down by 20 dB: the meter follows; Amp = None disables Input
    page.get_by_label("Amp input (dB)").evaluate(
        "el => { el.value = '-20'; el.dispatchEvent(new Event('input')); }"
    )
    expect(page.locator(".audio-input .meta")).to_have_text(
        "\u221220 dB"
    )  # a minus sign, as the UI writes it
    render_and_wait(page)
    after = meter.text_content() or ""
    assert meter_peak(before) - meter_peak(after) == pytest.approx(20, abs=0.05)
    open_chip(page, "amp")
    page.locator('select[data-kind="captures"]').select_option("")
    expect(page.get_by_label("Amp input (dB)")).to_be_disabled()
    page.get_by_role("checkbox", name="Loop").check()
    assert page.evaluate("document.querySelector('#audio-body audio').loop") is True
    href = page.locator("#audio-body a.button").get_attribute("href") or ""
    response = page.request.get(base_url + href)
    assert response.headers["content-type"] == "audio/wav"
    assert "attachment" in response.headers["content-disposition"]


def test_a_sweep_plays_from_buttons_like_the_slots(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "short.wav", seconds=0.3))
    buttons = page.locator(".audio-sweep [data-slot]")
    # before a sweep: a greyed button per position typed, five to start
    expect(buttons).to_have_text(["5 %", "25 %", "50 %", "75 %", "100 %"])
    expect(buttons.first).to_be_disabled()
    # the dropdown is the row's label: "Sweep" until a pot is picked, and no render before
    pot = page.get_by_label("Pot to sweep")
    expect(pot.locator("option:checked")).to_have_text("Sweep")
    expect(page.get_by_role("button", name="Render sweep")).to_be_disabled()
    expect(page.locator(".audio-sweep-set > .name")).to_have_count(0)
    pot.select_option(index=1)
    page.locator('input[aria-label="Positions (%)"]').fill("0, 100")
    expect(buttons).to_have_text(["0 %", "100 %"])
    page.get_by_role("button", name="Render sweep").click()
    expect(buttons.nth(1)).to_be_enabled(timeout=60_000)
    expect(buttons.first).to_be_enabled()
    knob = page.locator(".audio-sweep .name").text_content() or ""
    # sweep takes aren't drawn on the spectrum: Expected and the live area cover them
    expect(page.locator('[data-curve-label="sweep"]')).to_have_count(0)
    # one player for everything, so Loop holds for the sweep too
    expect(page.locator("#audio-body audio")).to_have_count(1)
    page.get_by_role("checkbox", name="Loop").check()
    buttons.nth(1).click()
    expect(buttons.nth(1)).to_have_attribute("aria-checked", "true")
    assert page.evaluate("document.querySelector('#audio-body audio').loop") is True
    # the click started it, from the take preloaded when it finished
    page.wait_for_function("!document.querySelector('#audio-body audio').paused")
    assert page.evaluate("document.querySelector('#audio-body audio').src").startswith("blob:")
    # the WAV is saved, never opened in place of the app (the Mac app's window), and the
    # two download buttons stay one line tall however narrow the pane (D-312)
    wav = page.locator("#audio-body a.button", has_text="Download WAV")
    expect(wav).to_have_attribute("download", "")
    both = page.locator(".audio-downloads > a.button, .audio-downloads > button")
    expect(both).to_have_count(2)
    one_line = page.get_by_role("button", name="Render", exact=True).bounding_box()
    assert one_line is not None
    for i in range(2):
        expect(both.nth(i)).to_have_css("white-space", "nowrap")
        expect(both.nth(i)).to_have_css("flex-shrink", "0")
        box = both.nth(i).bounding_box()
        assert box is not None and box["height"] == pytest.approx(one_line["height"], abs=2)
    # every take in one zip, each with what it was made from
    with page.expect_download() as download:
        page.get_by_role("button", name="Download all (.zip)").click()
    with zipfile.ZipFile(download.value.path()) as z:
        names = z.namelist()
        notes = z.read("takes.txt").decode()
    wavs = [n for n in names if n.endswith(".wav")]
    assert len(wavs) == 2 and wavs[0].endswith(f"{knob} 0 %.wav")
    assert len(names) == 5  # two takes, the circuit each was rendered from, the note
    assert f"{knob} 100 %" in notes and "Clip: short, medium pick" in notes


def test_opening_another_circuit_stops_the_player(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    """Playing one circuit's take, then opening another whose take is already rendered:
    the player stops, and the new circuit's take is loaded at its start but waits for Play."""
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "switch.wav", seconds=0.5))
    page.get_by_role("checkbox", name="Loop").check()
    render_and_wait(page)
    take = lambda: page.evaluate(TAKE_KEY)  # noqa: E731
    ts808 = take()
    open_circuit(page, base_url, "fuzz-face")
    render_and_wait(page)
    fuzz = take()
    assert fuzz != ts808
    page.evaluate("document.querySelector('#audio-body audio').play()")
    page.wait_for_function("!document.querySelector('#audio-body audio').paused")
    open_circuit(page, base_url, "ts808")
    page.wait_for_function(f"{TAKE_KEY} === {ts808!r}")
    page.wait_for_timeout(500)  # long enough for the loaded take to have started, were it to
    assert page.evaluate("document.querySelector('#audio-body audio').paused") is True
    assert page.evaluate("document.querySelector('#audio-body audio').currentTime") == 0


def test_the_audio_settings_are_remembered(page: Page, base_url: str, tmp_path: Path) -> None:
    """The clip, pick, amp, its input trim, the cab, Loop and the sweep's positions stay as
    last chosen when another pedal is loaded afresh, so they needn't be set again."""
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "first.wav", seconds=0.2))
    upload(page, "clips", plucks(tmp_path / "second.wav", seconds=0.2))
    upload(page, "captures", NAM)
    impulse = np.zeros(480)
    impulse[0] = 0.5
    room = tmp_path / "room.wav"
    room.write_bytes(write_wav(Audio(48000, impulse)))
    upload(page, "irs", room)
    select = lambda kind: page.locator(f'select[data-kind="{kind}"]')  # noqa: E731
    open_chip(page, "guitar")
    first = next(
        v
        for v in select("clips").locator("option").evaluate_all("os => os.map((o) => o.value)")
        if "first" in v
    )
    select("clips").select_option(first)  # not the one just uploaded
    page.locator('[data-audio-level="hard"]').click()
    amp, cab = select("captures").input_value(), select("irs").input_value()
    assert amp.startswith("user:standard-random") and cab.startswith("user:room")
    open_chip(page, "amp")
    page.get_by_label("Amp input (dB)").fill("6")
    page.get_by_role("checkbox", name="Loop").check()
    page.locator('input[aria-label="Positions (%)"]').fill("10, 90")
    # another pedal, loaded afresh (as a new tab would)
    open_circuit(page, base_url, "fuzz-face")
    page.reload()
    wait_for_update(page, 0)
    expect(select("clips")).to_have_value(first)
    expect(page.locator('[data-audio-level="hard"]')).to_have_attribute("aria-checked", "true")
    expect(select("captures")).to_have_value(amp)
    expect(select("irs")).to_have_value(cab)
    expect(page.get_by_label("Amp input (dB)")).to_have_value("6")
    expect(page.get_by_role("checkbox", name="Loop")).to_be_checked()
    assert page.evaluate("document.querySelector('#audio-body audio').loop") is True
    expect(page.locator('input[aria-label="Positions (%)"]')).to_have_value("10, 90")
    # None is remembered too
    open_chip(page, "amp")
    select("captures").select_option("")
    page.reload()
    wait_for_update(page, 0)
    expect(select("captures")).to_have_value("")
    expect(select("irs")).to_have_value(cab)


def test_takes_already_rendered_are_found_without_rendering(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    """A take already rendered for the settings as they are is loaded (not played) without
    pressing Render after a reload; a sweep's takes the same, once its pot is picked.
    Going back to settings rendered before doesn't swap the take that's there (the user,
    2026-10-28: what plays changes only with Render or a take's button); Render then finds
    it at once. Nothing is ever rendered by itself."""
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "found.wav", seconds=0.3))
    render_and_wait(page)
    pedal = page.locator('[data-slot="pedal"]')
    take = lambda: page.evaluate(TAKE_KEY)  # noqa: E731
    first = take()
    # a pick level not rendered yet: nothing is rendered, the take is out of date
    page.locator('[data-chip="guitar"]').click()
    page.locator('[data-audio-level="soft"]').click()
    expect(page.locator(".audio-stale")).to_be_visible()
    page.wait_for_timeout(1000)
    assert take() == first
    render_and_wait(page)
    soft = take()
    assert soft != first
    # back to Medium: the soft take stays, out of date, until Render finds Medium's
    page.locator('[data-audio-level="med"]').click()
    page.wait_for_timeout(1000)
    assert take() == soft
    expect(page.locator(".audio-stale")).to_be_visible()
    render_and_wait(page)
    assert take() == first
    expect(page.locator(".audio-stale")).to_be_hidden()
    # a sweep, then a reload: the take and the sweep's takes are found again
    pot = page.get_by_label("Pot to sweep")
    pot.select_option(index=1)
    page.locator('input[aria-label="Positions (%)"]').fill("0, 100")
    page.get_by_role("button", name="Render sweep").click()
    buttons = page.locator(".audio-sweep [data-slot]")
    expect(buttons.nth(1)).to_be_enabled(timeout=60_000)
    page.reload()
    wait_for_update(page, 0)
    expect(pedal).to_be_enabled(timeout=10_000)
    assert take() == first
    assert page.evaluate("document.querySelector('#audio-body audio').paused") is True
    expect(buttons.first).to_be_disabled()  # no pot picked yet
    pot.select_option(index=1)
    expect(buttons.nth(0)).to_be_enabled(timeout=10_000)
    expect(buttons.nth(1)).to_be_enabled()
    # a position never rendered stays greyed; nothing renders it
    page.locator('input[aria-label="Positions (%)"]').fill("0, 37")
    expect(buttons).to_have_text(["0 %", "37 %"])
    expect(buttons.nth(0)).to_be_enabled()
    page.wait_for_timeout(1500)
    expect(buttons.nth(1)).to_be_disabled()
    expect(page.locator(".audio-sweep button.rendering")).to_have_count(0)


def test_a_bad_upload_is_explained(
    page: Page, base_url: str, tmp_path: Path, browser_errors: list[str]
) -> None:
    open_circuit(page, base_url, "ts808")
    bad = tmp_path / "song.mp3"
    bad.write_bytes(b"ID3 not a wav")
    row = page.locator('#audio-body select[data-kind="clips"]').locator("xpath=..")
    row.locator('input[type="file"]').set_input_files(str(bad))
    expect(page.locator(".audio-status.failed")).to_contain_text("Export the clip as WAV")
    browser_errors[:] = [e for e in browser_errors if "status of 422" not in e]  # expected


def logic(page: Page, body: str, arg: Any = None) -> Any:
    return run(page, f"const a = await m('audio-logic.js'); {body}", arg)


def test_positions_are_parsed_and_checked(js: Page) -> None:
    assert logic(js, "return a.parsePositions('0, 50%, 100');") == {"rotations": [0, 0.5, 1]}
    assert "error" in logic(js, "return a.parsePositions('');")
    assert logic(js, "return a.parsePositions('0 120');") == {
        "error": "120 isn't a position from 0 to 100 %."
    }
    assert "up to 5" in logic(js, "return a.parsePositions('1 2 3 4 5 6');")["error"]


def test_a_take_is_marked_out_of_date_until_rendered_again(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "short.wav", seconds=0.3))
    stale = page.locator(".audio-stale")
    render_and_wait(page)
    expect(stale).to_be_hidden()
    open_chip(page, "guitar")
    page.locator('[data-audio-level="hard"]').click()
    page.locator("#knobs-body input[type=range]").first.evaluate(
        "el => { el.value = String(Number(el.max) * 0.9); el.dispatchEvent(new Event('input')); }"
    )
    expect(stale).to_have_text(
        "Out of date: the knobs and pick level changed since this take. Render to hear them."
    )
    expect(page.locator("#audio-body button.primary")).to_have_class(re.compile(r"\bstale\b"))
    page.locator('[data-audio-level="med"]').click()
    expect(stale).to_have_text("Out of date: the knobs changed since this take. Render to hear it.")
    render_and_wait(page)
    expect(stale).to_be_hidden()


def test_render_sources_ignore_layout_and_name_what_changed(js: Page) -> None:
    out = logic(
        js,
        """
      const circuit = { power: { mode: 'ideal' }, probes: {}, parts: [
        { ref: 'R1', type: 'resistor', value: 1000, pos: [0, 0], rot: 0 },
        { ref: 'VR1', type: 'pot', value: 1e5, rotation: 0.5, pos: [50, 0], rot: 0 } ] };
      const view = { parts: [{ ref: 'R1', pins: [{ name: '1', net: 'in', pos: [0, 0] }, { name: '2', net: 'out', pos: [0, 40] }] },
                             { ref: 'VR1', pins: [] }] };
      const req = { clip: { layer: 'user', id: 'riff' }, capture: null, ir: null, level: 'med', input_db: 0 };
      const base = a.renderSources(circuit, view, req);
      const moved = { ...circuit, parts: circuit.parts.map((p) => ({ ...p, pos: [p.pos[0] + 100, 30], rot: 90 })) };
      const movedView = { parts: view.parts.map((p) => ({ ...p, pins: p.pins.map((q) => ({ ...q, pos: [9, 9] })) })) };
      const rewired = { parts: [{ ...view.parts[0], pins: [view.parts[0].pins[0], { name: '2', net: 'GND' }] }, view.parts[1]] };
      const turned = { ...circuit, parts: [circuit.parts[0], { ...circuit.parts[1], rotation: 0.9 }] };
      const revalued = { ...circuit, parts: [{ ...circuit.parts[0], value: 2200 }, circuit.parts[1]] };
      const diff = (c, v, r) => a.changedSources(base, a.renderSources(c, v, { ...req, ...r }));
      return [
        diff(moved, movedView, {}), diff(circuit, rewired, {}), diff(turned, view, {}), diff(revalued, view, {}),
        diff(turned, view, { level: 'hard', capture: { layer: 'user', id: 'amp' }, ir: { layer: 'core', id: 'cab' }, input_db: -6, clip: { layer: 'user', id: 'b' } }),
        diff(circuit, view, { pump_ripple: true }),
        a.staleText([]), a.staleText(['clip']), a.staleText(['circuit', 'knobs', 'amp']), a.staleText(['amp input', 'cab']),
      ];
    """,
    )
    assert out[0] == []  # moving and turning parts on the sheet keeps the take current
    assert out[1] == ["circuit"]  # a pin on another net
    assert out[2] == ["knobs"]
    assert out[3] == ["circuit"]
    assert out[4] == ["knobs", "clip", "pick level", "amp", "cab", "amp input"]
    assert out[5] == ["pump switching"]
    assert out[6] == ""
    assert out[7] == "Out of date: the clip changed since this take. Render to hear it."
    assert out[8] == (
        "Out of date: the circuit, knobs and amp changed since this take. Render to hear them."
    )
    assert out[9] == (  # only after the pedal: the pedal's output is kept (D-096)
        "Out of date: the amp input and cab changed since this take. Render to hear them."
        " The pedal isn't simulated again, so it's quick."
    )


def test_slots_keep_the_snapshot(js: Page) -> None:
    slots = logic(
        js,
        """
      let s = {pedal: null, dry: null, snapshot: {key: 's', label: 'snap'}};
      s = a.nextSlots(s, {key: 'k1', label: 'one'}, {key: 'd', label: 'dry'});
      const first = s;
      s = a.nextSlots(s, {key: 'k2', label: 'two'}, {key: 'd', label: 'dry'});
      const second = s;
      s = a.nextSlots(s, {key: 'k2', label: 'two again'}, null);
      return [first, second, s];
    """,
    )
    assert set(slots[0]) == {"pedal", "dry", "snapshot"} and slots[0]["snapshot"]["key"] == "s"
    assert slots[1]["pedal"]["key"] == "k2" and slots[1]["snapshot"]["key"] == "s"
    assert slots[2]["dry"] is None and slots[2]["snapshot"]["key"] == "s"


def test_slots_by_id(js: Page) -> None:
    out = logic(
        js,
        """
      const t = (key) => ({key, label: key});
      const slots = {dry: t('d'), pedal: t('p'), snapshot: null};
      const sweep = [t('s0'), null, t('s2')];  // the middle one isn't done
      return [a.takeAt(slots, sweep, 'sweep-2').key, a.takeAt(slots, sweep, 'sweep-1'),
              a.takeAt(slots, sweep, 'snapshot'), a.takeAt(slots, sweep, 'pedal').key];
    """,
    )
    assert out == ["s2", None, None, "p"]


def test_each_take_says_what_it_was_made_from_in_the_zip(js: Page) -> None:
    out = logic(
        js,
        """
      const circuit = {parts: [{ref: 'VR1', rotation: 0.75}, {ref: 'SW1', position: 1}, {ref: 'R1'},
                               {ref: 'J1', type: 'jack', stereo: true, plugged: false}]};
      const controls = [{ref: 'VR1', kind: 'pot', label: 'Drive'}, {ref: 'SW1', kind: 'switch', label: 'Mode'},
                        {ref: 'J1', kind: 'switch', label: 'Input cable', positions: ['Cable in', 'Cable out'], plug: true}];
      const knobs = a.knobsText(controls, circuit);
      const base = {name: 'TS808', clip: 'riff', level: 'med', amp: 'Lonestar', input_db: -6, cab: 'V30', when: 'today'};
      const pedal = {key: 'p', label: 'TS808 · 14:48', notes: a.takeNotes({...base, knobs}), circuit};
      const dry = {key: 'd', label: 'dry', notes: a.takeNotes({...base, knobs: null, amp: 'None'})};
      const sweep = [{key: 's0', label: 'Drive 0 %', notes: 'n0', circuit}, null, {key: 's2', label: 'Drive 0 %', notes: 'n2'}];
      const same = a.zipContents({dry, pedal, snapshot: {...pedal, label: 'snapshot: x'}}, sweep, 'TS808');
      const kept = a.zipContents({dry: null, pedal, snapshot: {key: 'k', label: 'snapshot: y', notes: 'old'}}, [], 'TS808');
      const sources = {knobs: JSON.stringify({VR1: 0.5, VR2: 0.1}), clip: '"c"'};
      return {knobs, pedal: pedal.notes, dry: dry.notes, same, kept: kept.takes.map((t) => t.file),
              without: a.withoutKnob(sources, 'VR1')};
    """,
    )
    assert out["knobs"] == "Drive 75 %, Mode: 2, Input cable: Cable out"
    assert out["pedal"] == (
        "Pedal: TS808\nKnobs: Drive 75 %, Mode: 2, Input cable: Cable out\nClip: riff, medium pick\n"
        "Amp: Lonestar, input \u22126 dB\nCab: V30\nRendered: today"
    )
    assert out["dry"].startswith("Pedal: none (the clip straight into the amp)\nClip: riff")
    assert "Amp: None\n" in out["dry"]  # no input trim without an amp
    assert out["same"]["takes"] == [
        {"key": "d", "file": "TS808 Dry.wav"},
        {"key": "p", "file": "TS808 Pedal.wav"},  # Snapshot is Pedal's take: once
        {"key": "s0", "file": "TS808 Drive 0 %.wav"},
        {"key": "s2", "file": "TS808 Drive 0 % 2.wav"},  # names never clash
    ]
    files = out["same"]["files"]
    assert sorted(files) == ["TS808 Drive 0 %.json", "TS808 Pedal.json", "takes.txt"]
    assert files["takes.txt"].startswith("TS808 Dry.wav\n  Pedal: none")
    assert "\n\nTS808 Drive 0 % 2.wav\n  n2\n" in files["takes.txt"]
    assert out["kept"] == ["TS808 Pedal.wav", "TS808 Snapshot.wav"]
    assert out["without"] == {"knobs": '{"VR2":0.1}', "clip": '"c"'}


def test_amp_meter_text(js: Page) -> None:
    out = logic(
        js,
        """
      const dry = {key: 'd', label: 'dry', amp_in: 0.069, amp_compression: 0.4, amp: true};  // -23.22 dBFS
      const pedal = {key: 'p', label: 'pedal', amp_in: 0.5, amp_compression: 12.3, amp: true};
      return [a.ampText(pedal, dry), a.ampText(dry, dry), a.ampText({...pedal, amp_in: 2, input_db: 6}, dry),
              a.ampText({...pedal, amp: false}, dry), a.ampText(null, dry), a.dbfs(0),
              [0.9, 1, 5.9, 6, 14.9, 15].map(a.ampWord), [0, 3, -6].map(a.trimText)];
    """,
    )
    assert out[0] == (
        "Amp: driven, squashing 12 dB · peaks -6.0 dBFS going in.\n"
        "Guitar alone: clean · peaks -23.2 dBFS going in."
    )
    assert out[1] == "Guitar alone: clean · peaks -23.2 dBFS going in."
    assert out[2].startswith("Amp: driven") and out[2].endswith("Turn the amp input down.")
    assert "\nBoth after the amp input trim of +6 dB.\n" in out[2]
    assert out[3:6] == ["", "", "silence"]
    assert out[6] == ["clean", "breaking up", "breaking up", "driven", "driven", "saturated"]
    assert out[7] == ["0 dB", "+3 dB", "\u22126 dB"]


def test_assets_jobs_and_urls(js: Page) -> None:
    out = logic(
        js,
        """
      const opts = a.assetOptions([{id: 'riff', name: 'riff', kind: 'clips', layer: 'user', detail: '4.0 s'},
                                   {id: 'lead', name: 'lead', kind: 'clips', layer: 'core', detail: ''}]);
      const seen = [];
      const answers = [{id: 'j', state: 'running', progress: 0.5}, {id: 'j', state: 'done', progress: 1, label: 'pedal', seconds: 5, peak: 1.5}];
      const done = await a.waitForJob({id: 'j', state: 'queued', progress: 0}, async () => answers.shift(),
                                      (j) => seen.push(a.jobText(j)), async () => {});
      const loud = {...done, peak: 1.5};  // 20 log10 1.5 = 3.52 dB
      const quiet = {...done, peak: 0.9};
      const texts = [a.jobText(loud, true), a.jobText(loud, false), a.jobText(quiet, true)];
      return {opts, ref: a.assetRef('user:my:riff'), none: a.assetRef(''), seen, texts, url: a.audioUrl('ab', 'TS 808'), done: done.state};
    """,
    )
    assert out["opts"] == [{"value": "user:riff", "label": "riff · 4.0 s"},
                           {"value": "core:lead", "label": "lead"}]  # fmt: skip
    assert out["ref"] == {"layer": "user", "id": "my:riff"} and out["none"] is None
    assert out["seen"][:2] == ["Waiting for a free worker…", "Rendering… 50 %"]
    assert out["seen"][2] == out["texts"][1]  # no amp unless said
    assert out["texts"] == [
        "pedal: 5.0 s. Peaks 3.5 dB over full scale, from the amp capture's own output level; "
        "playback may clip.",
        "pedal: 5.0 s. Peaks 3.5 dB over full scale: turn the circuit's volume down so playback "
        "doesn't clip.",
        "pedal: 5.0 s.",
    ]
    assert out["url"] == "api/render/audio/ab.wav?download=TS%20808" and out["done"] == "done"


def test_cancel_jobs_and_their_text(js: Page) -> None:
    out = logic(
        js,
        """
      const posted = [];
      await a.cancelJobs(['a', 'b', 'a'], async (url) => {
        posted.push(url);
        if (url.includes('/b/')) throw new Error("That render isn't known");
        return {};
      });
      return {posted, text: a.jobText({state: 'cancelled', message: 'Render cancelled.'})};
    """,
    )
    assert out["posted"] == ["api/render/a/cancel", "api/render/b/cancel"]  # each once
    assert out["text"] == "Render cancelled."


def test_a_render_and_a_sweep_can_be_cancelled(page: Page, base_url: str, tmp_path: Path) -> None:
    """D-240: while a render runs, Render is "Cancel render" and Render sweep "Cancel sweep";
    pressing it stops the jobs and nothing new is loaded."""
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "long.wav", seconds=10.0))
    page.get_by_role("button", name="Render", exact=True).click()
    cancel = page.get_by_role("button", name="Cancel render")
    expect(cancel).to_be_enabled()
    cancel.click()
    expect(page.locator(".audio-status")).to_have_text("Render cancelled.", timeout=20_000)
    expect(page.get_by_role("button", name="Render", exact=True)).to_be_enabled()
    expect(page.locator("#audio-body a.button")).to_be_hidden()  # no take loaded
    page.get_by_label("Pot to sweep").select_option(index=1)
    page.locator('input[aria-label="Positions (%)"]').fill("0, 100")
    page.get_by_role("button", name="Render sweep").click()
    page.get_by_role("button", name="Cancel sweep").click()
    expect(page.locator(".audio-status")).to_contain_text("Sweep cancelled", timeout=20_000)
    expect(page.get_by_role("button", name="Render sweep")).to_be_enabled()
    expect(page.locator(".audio-sweep [data-slot]").first).to_be_disabled()  # no take


def test_the_chain_opens_one_drawer_at_a_time_and_the_spectrum_shows_the_takes(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "chain.wav", seconds=0.5))
    guitar = page.locator('[data-chip="guitar"]')
    expect(guitar.locator(".v")).to_have_text("chain")
    expect(guitar.locator(".s")).to_have_text("Medium pick")
    expect(page.locator('[data-chip="amp"] .v')).to_have_text("None")
    expect(page.locator(".drawer:visible")).to_have_count(0)  # all closed to start
    guitar.click()
    expect(page.locator('[data-drawer="guitar"]')).to_be_visible()
    page.locator('[data-chip="amp"]').click()
    expect(page.locator('[data-drawer="guitar"]')).to_be_hidden()
    expect(page.locator('[data-drawer="amp"]')).to_be_visible()
    page.locator('[data-chip="amp"]').click()
    expect(page.locator(".drawer:visible")).to_have_count(0)
    # the Pedal drawer says what loads the circuit and opens the guitar input
    open_chip(page, "pedal")
    expect(page.locator('[data-drawer="pedal"] .note')).to_contain_text("Guitar input: ")
    page.get_by_role("button", name="Edit the guitar input…").click()
    expect(page.locator("#field-source")).to_be_visible()
    page.keyboard.press("Escape")

    # the spectrum is open with its axes before any render; the player sits right under Render
    plot = page.locator(".audio-spectrum")
    expect(plot.locator("canvas")).to_have_count(1)
    order = page.locator(".audio-listen").evaluate(
        "el => [...el.children].map((c) => c.tagName === 'AUDIO' ? 'player' : c.className)"
    )
    assert order[:3] == ["panel-tools audio-render", "player", "panel-tools audio-ab"]
    ab = page.locator(".audio-ab [data-slot]").evaluate_all("bs => bs.map((b) => b.dataset.slot)")
    assert ab == ["dry", "pedal", "snapshot"]
    render_and_wait(page)
    labels = "el => el._plot.series.slice(1).map((s) => s.label)"
    # What you hear is first and the default (D-104); Pedal output next
    views = page.locator("[data-spectrum-view]").evaluate_all(
        "bs => bs.map((b) => b.dataset.spectrumView)"
    )
    assert views == ["heard", "pedal"]
    expect(page.locator('[data-spectrum-view="heard"]')).to_have_attribute("aria-checked", "true")
    page.locator('[data-spectrum-view="pedal"]').click()
    page.wait_for_function(
        "() => document.querySelector('.audio-spectrum')._plot?.series.length === 3"
    )
    assert plot.evaluate(labels) == ["Dry", "Pedal"]  # Pedal (no clipping) starts unticked
    page.locator('[data-curve="expected"]').check()
    assert plot.evaluate(labels) == ["Dry", "Pedal", "Pedal (no clipping)"]
    expect(page.locator('[data-curve-label="live"]')).to_be_hidden()
    page.locator('[data-curve="dry"]').uncheck()
    assert plot.evaluate(labels) == ["Pedal", "Pedal (no clipping)"]
    page.locator('[data-spectrum-view="heard"]').click()
    expect(page.locator('[data-curve-label="expected"]')).to_be_visible()
    expect(page.locator('[data-curve-label="live"]')).to_be_visible()
    assert plot.evaluate(labels) == [
        "Pedal",
        "Pedal (no clipping)",
    ]  # nothing playing: no live area
    # Keep puts the snapshot on the spectrum; right after Keep it's the same take as
    # Pedal, and the panel says so
    page.get_by_role("button", name="Keep as snapshot").click()
    expect(page.locator('[data-curve="snapshot"]')).to_be_checked()
    # the Snapshot button lights up, and again on the next Keep (a replaced snapshot)
    snapshot = page.locator('[data-slot="snapshot"]')
    expect(snapshot).to_have_class(re.compile(r"\bkept\b"))
    snapshot.evaluate("el => el.classList.remove('kept')")
    page.get_by_role("button", name="Keep as snapshot").click()
    expect(snapshot).to_have_class(re.compile(r"\bkept\b"))
    assert plot.evaluate(labels) == ["Pedal", "Snapshot", "Pedal (no clipping)"]
    page.locator('[data-slot="snapshot"]').click()
    expect(page.locator(".audio-status")).to_have_text(
        "Snapshot and Pedal are the same take until you render a change."
    )


def test_spectrum_logic(js: Page) -> None:
    out = logic(
        js,
        """
      const dry = {freq: [100, 1000], pedal: [-20, -200], heard: [-30, -40], di: [0, 0]};
      const take = {freq: [100, 1000], pedal: [-10, -25], heard: [-28, -35], di: [0, 3]};
      const curve = {freq: [10, 10000], db: [6, 6]};
      const series = a.spectrumSeries('heard', {dry, pedal: take, snapshot: null},
        new Set(['dry', 'pedal', 'expected', 'live']), {expected: [1, 2], live: {freq: [50, 100, 1000], levels: [-1, -50, -60]}});
      const before = a.spectrumSeries('pedal', {dry, pedal: take}, new Set(['dry', 'expected']),
        {expected: a.expectedLevels(dry, {...take, pedal: [-20, -27]}, curve)});
      return {
        at: a.atFreqs([10, 100, 1000], [0, 10, 20], [10, Math.sqrt(1000), 1000, 5, 5000]),
        expected: a.expectedLevels({...dry, pedal: [-20, -30]}, take, curve),
        silent: a.expectedLevels(dry, take, curve)[1],
        // every curve on the full bands, by frequency: 100 Hz and 1 kHz land on bands 20 and 40
        heard: series.series.map((s) => [s.label, s.style, s.values.flatMap((v, i) => (v === null ? [] : [[i, v]]))]),
        x: series.x.length,
        // a take from before the bands reached 10 Hz (from 20 Hz) lines up with a newer one
        mixed: a.spectrumSeries('pedal', {dry: {freq: [20, 40], pedal: [-5, -6]}, pedal: {freq: [10, 20, 40], pedal: [-1, -2, -3]}},
          new Set(['dry', 'pedal'])).series.map((s) => s.values.slice(0, 13).flatMap((v, i) => (v === null ? [] : [[i, v]]))),
        diByFreq: a.expectedLevels({freq: [20, 40], pedal: [-20, -20]}, {freq: [10, 20, 40], di: [9, 0, 3]}, curve),
        before: before.series.map((s) => s.label),
        none: a.spectrumSeries('pedal', {dry: null}, new Set(['dry'])),
        smooth: [a.smoothLevels(null, [0], 0.5), a.smoothLevels([0], [-200], 0.5)],
        filled: a.fillEmptyBands([-200, -40, -200, -200, -10, -200]),
        full: a.atFullVolume([-20, -40], 0.5),
        afterAmp: a.expectedLevels(dry, take, curve, 'heard'),
        nolive: a.spectrumSeries('pedal', {dry}, new Set(['dry', 'live']), {live: {freq: [100, 1000], levels: [0, 0]}}).series.map((s) => s.label),
        // the live area goes by frequency: bands from 10 Hz on a take's from 20 Hz line up
        aligned: a.onBands([10, 20, 40], [-1, -2, -3], [20, 40, 80]),
        range: [a.spectrumRange('heard', series), a.spectrumRange('pedal', {series: [{style: 'expected', values: [3.7, null]}]}),
                a.spectrumRange('heard', {series: [{style: 'live', values: [12]}, {style: 'current', values: [-3]}]})],
        // D-105: a heard line's padded top bands (silent) aren't drawn; the hatch from 24 kHz
        padded: a.spectrumSeries('heard', {pedal: {freq: [10 * 2 ** (67 / 6), 10 * 2 ** (69 / 6)], heard: [-30, -200]}},
          new Set(['pedal'])).series[0].values.flatMap((v, i) => (v === null ? [] : [[i, v]])),
        hatch: [a.spectrumHatch('heard', null, new Set()),
                a.spectrumHatch('pedal', {...dry, pedal_top: 24000}, new Set(['dry'])),
                a.spectrumHatch('pedal', dry, new Set(['expected'])).label,  // an older take: 48 kHz
                a.spectrumHatch('pedal', {...dry, pedal_top: 48000}, new Set(['dry'])),  // a 96 kHz clip
                a.spectrumHatch('pedal', {...dry, pedal_top: 24000}, new Set(['pedal'])),  // Dry not shown
                a.spectrumHatch('pedal', {...dry, pedal_top: 22050}, new Set(['dry'])).label],
        chips: [a.chipName('riff · 4.0 s'), a.chipName('lead'), a.chipName('V30 2x12')],
      };
    """,
    )
    assert out["at"] == pytest.approx([0, 5, 20, 0, 20])
    assert out["expected"] == pytest.approx([-14, -27])  # dry + 6 dB curve, less the DI's 3 dB
    assert out["silent"] is None
    assert out["heard"] == [
        ["Playing now", "live", [[14, -1], [20, -50], [40, -60]]],  # first: drawn behind the lines
        ["Dry", "input", [[20, -30], [40, -40]]],
        ["Pedal", "current", [[20, -28], [40, -35]]],
        ["Pedal (no clipping)", "expected", [[20, 1], [40, 2]]],
    ]
    assert out["x"] == 70
    assert out["mixed"] == [[[6, -5], [12, -6]], [[0, -1], [6, -2], [12, -3]]]
    # the DI read at 20 and 40 Hz, not 10 and 20
    assert out["diByFreq"] == pytest.approx([-14, -17])
    assert out["afterAmp"] == pytest.approx([-24, -37])  # the dry take as heard + 6, less the DI
    assert out["nolive"] == ["Dry"]  # no live area before the amp
    assert out["aligned"] == [-2, -3, None]
    assert out["range"] == [
        [-80, 10],  # Expected (at 2 dBFS) counts after the amp too
        [-80, 10],
        [-80, 10],
    ]  # fixed; the live area never moves it
    assert out["before"] == ["Dry", "Pedal (no clipping)"]
    assert (
        out["none"]["series"] == [] and len(out["none"]["x"]) == 70
    )  # empty axes, 10 Hz to 30 kHz
    assert out["full"] == pytest.approx([-13.9794, -33.9794])  # half volume reads 6.02 dB low
    assert out["filled"] == pytest.approx([-200, -40, -30, -20, -10, -200])  # ends stay empty
    assert out["smooth"][0] == [0]
    assert out["smooth"][1][0] == pytest.approx(-3.0103, abs=1e-3)
    assert out["chips"] == ["riff", "lead", "V30 2x12"]
    assert out["padded"] == [[67, -30]]
    assert out["hatch"] == [
        {"from": 24000, "label": "nothing above 24 kHz: takes play at 48 kHz"},
        {"from": 24000, "label": "Dry: nothing above 24 kHz (a 48 kHz clip)"},
        "Dry: nothing above 24 kHz (a 48 kHz clip)",
        None,  # a 96 kHz clip reaches 30 kHz: nothing to hatch before the amp
        None,  # nor with only Pedal, which reaches 30 kHz from the simulation
        "Dry: nothing above 22.1 kHz (a 44.1 kHz clip)",
    ]


def test_clip_text(js: Page) -> None:
    """The note under the spectrum when the pedal clips: the level the output reached on
    the scope tone (its larger peak, as a sine's dBV) and that level less the clean gain."""
    out = logic(
        js,
        """
      const s = (pos, neg, label, thd) => ({peak_pos: pos, peak_neg: neg, clipping: {label, thd}});
      const run = {level: 'med', freq: 200, gainDb: 64.3};
      return [
        a.clipText(s(Math.SQRT2, -1, 'heavy', 0.27), run),
        a.clipText(s(1, -2 * Math.SQRT2, 'light', 0.03), {...run, level: 'hard', gainDb: 20}),
        a.clipText(s(5, -5, 'clean', 0.001), run),
        a.clipLines(a.clipLevels(s(Math.SQRT2, -1, 'heavy', 0.27), run), 'pedal'),
        a.clipLines(a.clipLevels(s(Math.SQRT2, -1, 'heavy', 0.27), run), 'heard'),
        a.clipLines(a.clipLevels(s(5, -5, 'clean', 0.001), run), 'pedal'),
        a.clipLimitsText(a.clipLevels(s(Math.SQRT2, -1, 'heavy', 0.27), run)),
      ];
    """,
    )
    assert out[0] == (
        "The pedal clips (heavy, THD 27 % on the probe's 200 Hz tone at the medium pick)."
        " Its output reached about +0 dBV there, so it can't follow Pedal (no clipping) above that level."
        " With 64 dB of clean gain, it starts clipping at about \u221264 dBV at the guitar:"
        " where Dry sits above that, the pedal clips."
    )
    # Phase 8b: the same two levels as unlabelled dashed lines on the Pedal output view only,
    # said in a line right under the plot
    assert out[3] == [{"y": pytest.approx(0.0, abs=1e-9)}, {"y": pytest.approx(-64.3)}]
    assert out[4] == [] and out[5] == []
    assert out[6] == (
        "Upper line: output reached +0 dBV. Lower line: clipping starts at \u221264 dBV at the"
        " guitar."
    )
    assert "light, THD 3 %" in out[1] and "hard pick" in out[1]
    assert "reached about +6 dBV" in out[1] and "about \u221214 dBV at the guitar" in out[1]
    assert out[2] is None  # a clean output says nothing


def test_the_spectrum_says_where_a_fuzz_clips(page: Page, base_url: str) -> None:
    """The Big Muff clips on the probe's tone, so the spectrum says so, from the last run."""
    open_circuit(page, base_url, "big-muff-pi-v3")
    note = page.locator("[data-clip-note]")
    expect(note).to_be_visible(timeout=30_000)
    expect(note).to_contain_text("The pedal clips (heavy")
    expect(note).to_contain_text("at the guitar")
    # Phase 8b: the two levels as dashed lines on the Pedal output view, off until the Clip
    # levels box is ticked; the line under the plot says what they are
    page.locator(
        '[data-spectrum-view="pedal"]'
    ).click()  # the clip lines are the Pedal output view's
    levels = "document.querySelector('.audio-spectrum')._plot?.marks?.levels.length"
    limits = page.locator("[data-clip-limits]")
    assert page.evaluate(levels) == 0
    expect(limits).to_be_hidden()
    page.locator("[data-clip-lines]").check()
    page.wait_for_function(f"{levels} === 2")
    expect(limits).to_contain_text("Upper line: output reached")
    expect(limits).to_contain_text("Lower line: clipping starts at")
    page.locator("[data-clip-lines]").uncheck()
    page.wait_for_function(f"{levels} === 0")
    expect(limits).to_be_hidden()


def test_guitar_summary(js: Page) -> None:
    pickups = [{"kind": "strat", "name": "Strat single coil"}]
    out = logic(
        js,
        """
      const g = (guitar) => ({parts: [{ref: 'R1', type: 'resistor'}, {ref: 'IN', type: 'guitar', ...guitar}]});
      const pickup = {r: 6380, l: 2.55, c: 151e-12};
      return [
        a.guitarSummary(g({source: 'ideal'}), arg),
        a.guitarSummary(g({source: 'ideal', volume: 500000, rotation: 0.4}), arg),
        a.guitarSummary(g({source: 'pickup', pickup: {...pickup, kind: 'strat'}, cable: 3, volume: 250000, rotation: 0.7}), arg),
        a.guitarSummary(g({source: 'pickup', pickup}), arg),
        a.guitarSummary({parts: []}, arg),
      ];
    """,
        pickups,
    )
    assert out == [
        "Buffered input",
        "Buffered input · vol 4",
        "Strat single coil · 3 m · vol 7",
        "Your pickup",
        "No guitar input",
    ]


def test_sweep_stale_text(js: Page) -> None:
    out = logic(
        js,
        "return [a.sweepStaleText([]), a.sweepStaleText(['circuit']),"
        " a.sweepStaleText(['circuit', 'amp', 'clip'])];",
    )
    assert out == [
        "",
        "The sweep is from an older setup: the circuit changed since. Render sweep to update it.",
        "The sweep is from an older setup: the circuit, amp and clip changed since."
        " Render sweep to update it.",
    ]


def test_trimmer_rows_and_stuck_text(js: Page) -> None:
    """D-198: the Trimmers fold's rows, and the saturation check in words."""
    circuit = {"parts": [
        {"ref": "TR1", "type": "trimmer", "bias_target": {"node": "Q2.C", "volts": -0.16}},
        {"ref": "TR2", "type": "trimmer", "label": "BIAS"},
        {"ref": "VR1", "type": "pot"},
    ]}  # fmt: skip
    assert logic(js, "return a.trimmerRows(arg);", circuit) == [
        {"ref": "TR1", "name": "TR1",
         "held": "Set by its target (Q2.C at -0.16 V). Open it and remove the target to sweep it."},
        {"ref": "TR2", "name": "BIAS · TR2", "held": None},
    ]  # fmt: skip
    assert logic(js, "return a.trimmerRows(null);") == []
    at = [0.25, 0.5, 0.75]
    q2 = [{"ref": "Q2", "state": "saturated"}]
    assert logic(js, "return a.stuckText(arg[0], arg[1]);", [at, [[], [], []]]) == {
        "marks": ["", "", ""],
        "text": "",
    }
    assert logic(js, "return a.stuckText(arg[0], arg[1]);", [at, [[], [], q2]]) == {
        "marks": ["", "", "Q2 saturates"],
        "text": "At 75 % Q2 saturates: that take is a broken bias, not a sound.",
    }
    both = [[{"ref": "Q1", "state": "cut off"}], [], [*q2, {"ref": "U1", "state": "railed"}]]
    assert logic(js, "return a.stuckText(arg[0], arg[1]);", [at, both])["text"] == (
        "At 25 % Q1 switches off and at 75 % Q2 saturates, U1 sticks at a rail:"
        " those takes are a broken bias, not a sound."
    )
    assert logic(js, "return a.sweepStaleText(['circuit'], \"The trimmer's Render\");") == (
        "The sweep is from an older setup: the circuit changed since. The trimmer's Render to update it."
    )


def test_a_trimmer_sweep_renders_from_its_fold(page: Page, base_url: str, tmp_path: Path) -> None:
    """D-198: the Tone Bender's TR1 is set by its target (greyed, saying so); TR2 renders at
    25, 50 and 75 % into the sweep row, checked first for a saturated stage. The Aion
    version: the original has no trimmers (D-251)."""
    open_circuit(page, base_url, "tone-bender-mk2-mode")
    upload(page, "clips", plucks(tmp_path / "trim.wav", seconds=0.2))
    fold = page.locator("#audio-trimmers")
    expect(fold).to_be_visible()
    expect(fold).not_to_have_attribute("open", "")  # closed: it's advanced
    fold.locator("summary").click()
    # what it does is behind the fold's ⓘ, not a paragraph in it (9c's info pass)
    expect(fold.locator("p.hint")).to_have_count(0)
    fold.get_by_role("button", name="About Trimmers").click()
    expect(page.get_by_role("dialog", name="About Trimmers")).to_contain_text(
        "broken bias, not a sound"
    )
    page.keyboard.press("Escape")
    expect(fold).to_have_attribute("open", "")  # the ⓘ doesn't shut the fold
    held = fold.locator('[data-trimmer="TR1"]')
    expect(held).to_have_class("held")
    expect(held).to_contain_text("Set by its target")
    expect(held.locator("[data-trim-render]")).to_have_count(0)
    # the check is answered for the test: Q2 saturates at 75 %
    stuck = [[], [], [{"ref": "Q2", "state": "saturated", "message": "Q2 is fully on"}]]
    page.route("**/api/render/sweep/check", lambda route: route.fulfill(json=stuck))
    fold.locator('[data-trim-render="TR2"]').click()
    buttons = page.locator(".audio-sweep [data-slot]")
    expect(buttons).to_have_text(["25 %", "50 %", "75 %"])
    expect(page.locator(".audio-sweep .name")).to_have_text("TR2")
    # the pot dropdown is blank again: it names what Render sweep turns next
    expect(page.get_by_label("Pot to sweep").locator("option:checked")).to_have_text("Sweep")
    expect(buttons.nth(2)).to_be_enabled(timeout=60_000)
    expect(buttons.nth(2)).to_have_class(re.compile(r"\bstuck\b"))
    expect(buttons.nth(2)).to_have_attribute("title", "TR2 75 % · Q2 saturates")
    expect(buttons.nth(0)).not_to_have_class(re.compile(r"\bstuck\b"))
    expect(page.locator("[data-trim-stuck]")).to_have_text(
        "At 75 % Q2 saturates: that take is a broken bias, not a sound."
    )
    # the name shows it on the schematic, in the picked colour
    fold.locator('[data-trimmer="TR2"] .trim-name').click()
    expect(page.locator('g.part.picked[data-ref="TR2"]')).to_have_count(1)
    # picking a pot makes the pot the next sweep again
    page.get_by_label("Pot to sweep").select_option(index=1)
    expect(page.get_by_role("button", name="Render sweep")).to_be_enabled()


def title(page: Page, pane: str) -> None:
    """Click a pane's title bar on its name (a shrunk bar holds buttons further along)."""
    page.locator(f"#{pane} > summary").click(position={"x": 60, "y": 10})


def test_the_audio_pane_expands(page: Page, base_url: str) -> None:
    """Expand (D-102, D-110): the whole Audio pane large over the canvas, the spectrum left
    (its floor at -80), the player right; shrunk, its bar keeps Render, play and Dry /
    Pedal / Snapshot; Esc and opening another circuit put it back."""
    open_circuit(page, base_url, "ts808")
    plot = page.locator(".audio-spectrum")
    expect(plot.locator("canvas")).to_have_count(1)
    small = plot.bounding_box()
    scales = "(() => { const p = document.querySelector('.audio-spectrum')._plot; return [p.scales.x.min, p.scales.x.max, p.scales.y.min, p.shade]; })()"
    # the Frequency plot's band, shaded outside 20 Hz - 20 kHz, floor at -80 (D-102)
    assert page.evaluate(scales) == [10, 30000, -80, [20, 20000]]
    # Expand is on the title bar, and works on a shut pane too (it opens it)
    title(page, "panel-audio")
    expect(page.locator("#panel-audio")).not_to_have_attribute("open", "")
    expand = page.locator("#panel-audio > summary #audio-expand")
    expect(expand).to_have_text("Expand")
    expand.click()
    audio = page.locator("#panel-audio")
    expect(audio).to_have_class(re.compile(r"\bexpanded\b"))
    page.wait_for_function("document.querySelector('.audio-spectrum')._plot.height > 300")
    big = plot.bounding_box()
    assert small and big and big["width"] > small["width"]
    # large, it's Collapse at the title bar's far right (round 3)
    expect(page.locator("#panel-audio > summary > #audio-expand")).to_have_text("Collapse")
    # the player on the right of the spectrum
    player = page.locator("#audio-player").bounding_box()
    assert player and player["x"] > big["x"] + big["width"]
    expect(page.locator("#audio-player .audio-chain")).to_be_visible()
    # shrunk to its bar: Render, play and the A/B switch stay usable there
    title(page, "panel-audio")
    page.wait_for_function("() => !document.querySelector('#panel-audio').open")
    bar = page.locator("#panel-audio > summary .large-bar-tools")
    expect(bar.get_by_role("button", name="Render", exact=True)).to_be_visible()
    expect(bar.locator("#audio-bar-play")).to_be_visible()
    expect(bar.locator('[data-slot="dry"]')).to_be_visible()
    expect(bar.locator('[data-slot="snapshot"]')).to_be_visible()
    title(page, "panel-audio")  # open again: they're back in the player
    expect(page.locator('#audio-player [data-slot="dry"]')).to_have_count(1)
    expect(
        page.locator("#audio-player").get_by_role("button", name="Render", exact=True)
    ).to_be_visible()
    page.keyboard.press("Escape")  # shrinks it to its bar: still large (D-123)
    page.wait_for_function("() => !document.querySelector('#panel-audio').open")
    expect(audio).to_have_class(re.compile(r"\bexpanded\b"))
    page.locator("#panel-audio > summary .large-collapse").click()
    expect(audio).not_to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator("#panel-audio > summary #audio-expand")).to_have_text("Expand")
    # both large views out: one open at a time, a click on a bar switches (D-102)
    freq = page.locator("#panel-frequency")
    is_open = "el => el.open"
    page.locator("#frequency-expand").click()
    page.locator("#audio-expand").click()
    assert audio.evaluate(is_open) and not freq.evaluate(is_open)
    title(page, "panel-frequency")
    page.wait_for_function("() => !document.querySelector('#panel-audio').open")
    assert freq.evaluate(is_open)
    # Edit curve on, the Frequency view shrunk: its bar says so
    page.locator("#frequency-edit").click()
    title(page, "panel-audio")
    page.wait_for_function("() => !document.querySelector('#panel-frequency').open")
    expect(page.locator("#panel-frequency > summary .large-chip")).to_have_text("Editing")
    expect(page.locator("#panel-frequency > summary .large-chip")).to_be_visible()
    # Esc is the open view's: Audio shrinks to its bar too, the Frequency bar (still editing) stays
    page.keyboard.press("Escape")
    expect(audio).to_have_class(re.compile(r"\bexpanded\b"))
    expect(freq).to_have_class(re.compile(r"\bexpanded\b"))
    # both shrunk to their bars: the bars match and both show, ringed in the accent
    page.wait_for_function(
        "() => { const [a, b] = ['#panel-frequency', '#panel-audio'].map((s) => document.querySelector(s).getBoundingClientRect());"
        " return a.bottom <= b.top || b.bottom <= a.top; }"
    )
    f = page.locator("#panel-frequency > summary").bounding_box()
    s = page.locator("#panel-audio > summary").bounding_box()
    assert f and s and f["height"] == pytest.approx(s["height"], abs=2)
    # shrunk, the bars are the canvas's width (the side panels stay clear) and can't be dragged
    canvas = page.locator(".canvas").bounding_box()
    assert canvas and canvas["x"] <= f["x"] and f["x"] + f["width"] <= canvas["x"] + canvas["width"]
    expect(page.locator("#panel-frequency > summary .grip")).to_be_hidden()
    ring = "el => getComputedStyle(el).borderTopColor"
    assert freq.evaluate(ring) == audio.evaluate(ring) != "rgba(0, 0, 0, 0)"
    # each shrunk bar has a Collapse pinned right; held, as Expand is, only while Edit curve
    # has changes pending (none yet: it would be Done, then back to the panel) (D-107)
    expect(page.locator("#panel-frequency > summary .large-collapse")).to_be_enabled()
    audio_collapse = page.locator("#panel-audio > summary .large-collapse")
    expect(audio_collapse).to_be_enabled()
    audio_collapse.click()
    expect(audio).not_to_have_class(re.compile(r"\bexpanded\b"))
    expect(page.locator('#audio-player [data-slot="dry"]')).to_have_count(1)  # back from the bar
    page.locator("#audio-expand").click()
    title(page, "panel-audio")  # shrink, then open again from its bar
    page.wait_for_function("() => !document.querySelector('#panel-audio').open")
    title(page, "panel-audio")
    # the plot is drawn for the view as it is now, not the bar's width (it was, on reopening)
    page.wait_for_function(
        "() => Math.abs(document.querySelector('.audio-spectrum')._plot.width - document.querySelector('.audio-spectrum').clientWidth) < 4"
    )
    open_circuit(page, base_url, "fuzz-face")  # another circuit shrinks it to its bar (D-127)
    expect(audio).to_have_class(re.compile(r"\bexpanded\b"))
    expect(audio).not_to_have_attribute("open", "")


def test_the_audio_bar_stays_at_the_bottom_with_its_controls_centred(
    page: Page, base_url: str
) -> None:
    """D-111: shrunk, the Audio bar is always the bottom one, its controls in its middle;
    the Spectrum fold comes back as it was left; the ⓘ is in sections."""
    open_circuit(page, base_url, "ts808")
    expect(page.locator("#stage-chain .chain-block")).to_have_count(5, timeout=15_000)
    spectrum = page.locator("#audio-spectrum")
    spectrum.locator("> summary").click()  # shut the Spectrum in the panel
    expect(spectrum).not_to_have_attribute("open", "")
    page.locator("#audio-expand").click()
    expect(spectrum).to_have_attribute("open", "")  # large, it's the spectrum's view
    page.locator("#frequency-expand").click()  # Audio shrinks first...
    page.locator("#stages-expand").click()  # ...then Frequency, above it? No: Audio stays put
    page.wait_for_function("() => !document.querySelector('#panel-frequency').open")
    bars = {
        pane: page.locator(f"#{pane} > summary").bounding_box()
        for pane in ("panel-audio", "panel-frequency")
    }
    assert bars["panel-audio"] and bars["panel-frequency"]
    assert bars["panel-audio"]["y"] > bars["panel-frequency"]["y"]
    tools = page.locator("#panel-audio > summary .large-bar-tools").bounding_box()
    bar = bars["panel-audio"]
    assert tools and abs(tools["x"] + tools["width"] / 2 - (bar["x"] + bar["width"] / 2)) < 2
    # Play is greyed out while the player has no take (earlier tests may have left one
    # rendered for the TS808, which the player then finds already made)
    page.wait_for_function(
        "() => document.querySelector('#audio-bar-play').disabled === !document.querySelector('#audio-body audio').currentSrc"
    )
    # a render's progress shows left of Render without moving the buttons
    page.evaluate("document.querySelector('#panel-audio .large-bar-tools progress').hidden = false")
    progress = page.locator("#panel-audio .large-bar-tools progress").bounding_box()
    render = page.locator("#panel-audio .large-bar-tools").get_by_role("button", name="Render")
    render_box = render.bounding_box()
    assert progress and render_box and progress["x"] + progress["width"] <= render_box["x"]
    assert page.locator("#panel-audio > summary .large-bar-tools").bounding_box() == tools
    page.evaluate("document.querySelector('#panel-audio .large-bar-tools progress').hidden = true")
    # Play turning to Pause keeps its width, so the centred controls don't move (D-116)
    width = lambda: page.evaluate(  # noqa: E731
        "document.querySelector('#audio-bar-play').getBoundingClientRect().width"
    )
    play_width = width()
    page.evaluate("document.querySelector('#audio-bar-play').toggleAttribute('data-playing', true)")
    expect(page.locator("#audio-bar-play")).to_have_text(re.compile("Pause"))
    assert width() == play_width
    assert page.locator("#panel-audio > summary .large-bar-tools").bounding_box() == tools
    page.evaluate(
        "document.querySelector('#audio-bar-play').toggleAttribute('data-playing', false)"
    )
    # a click on a bar switches in one go, before the next frame is drawn: no in-between
    # layout (the one opening still a bar, the other not yet shrunk) to flicker (D-116)
    switched = page.evaluate(
        """() => {
          document.querySelector('#panel-frequency > summary').click();
          const f = document.getElementById('panel-frequency'), s = document.getElementById('panel-stages');
          const a = document.getElementById('panel-audio');
          return [f.open, s.open, a.open, f.getBoundingClientRect().bottom <= s.getBoundingClientRect().top + 1,
                  s.getBoundingClientRect().bottom <= a.getBoundingClientRect().top + 1];
        }"""
    )
    assert switched == [True, False, False, True, True], switched
    # back in the panel, the Spectrum is shut again, as it was left
    page.locator("#panel-audio > summary .large-collapse").click()
    expect(page.locator("#panel-audio")).not_to_have_class(re.compile(r"\bexpanded\b"))
    expect(spectrum).not_to_have_attribute("open", "")
    text = info_text(page, "panel-audio")
    assert "The chain" in text and "Open the Spectrum" in text
    spectrum.locator("> summary").click()
    text = info_text(page, "panel-audio")
    assert "Spectrum: What you hear" in text and "0 dBFS, the top" in text


def test_a_sweep_take_is_kept_and_an_old_sweep_says_so(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    """The user, 2026-10-28: Keep as snapshot keeps the sweep take playing (the lookup that
    follows a sweep switched the player back to Pedal, so Keep kept Pedal); after a change,
    an out-of-date sweep says so and waits for Render sweep (Render alone would lag); the
    progress bar takes the downloads' place, so Render doesn't move while it runs (D-134)."""
    open_circuit(page, base_url, "ts808")
    upload(page, "clips", plucks(tmp_path / "short.wav", seconds=0.3))
    page.get_by_label("Pot to sweep").select_option(index=1)
    page.locator('input[aria-label="Positions (%)"]').fill("0, 100")
    # Render, then Render sweep at once: the pedal take is still rendering
    page.get_by_role("button", name="Render", exact=True).click()
    page.get_by_role("button", name="Render sweep").click()
    buttons = page.locator(".audio-sweep [data-slot]")
    expect(buttons.nth(1)).to_be_enabled(timeout=60_000)
    # 100 % is the pedal take's own setting: the server hands back that job, but the
    # button still says its position (found by the user, 2026-10-28: it said "Pedal")
    assert page.locator(".audio-sweep .name").text_content() == "Guitar volume"
    expect(buttons).to_have_text(["0 %", "100 %"])
    knob = page.locator(".audio-sweep .name").text_content() or ""
    # picked while Render still runs (it waits for the dry take too): Render finishing
    # leaves the pick playing (the user, D-198)
    buttons.nth(1).click()
    expect(page.get_by_role("button", name="Render", exact=True)).to_be_enabled(timeout=60_000)
    page.wait_for_timeout(1500)  # past the lookup that follows a sweep
    expect(buttons.nth(1)).to_have_attribute("aria-checked", "true")
    page.get_by_role("button", name="Keep as snapshot").click()
    snapshot = page.locator('.audio-ab [data-slot="snapshot"]')
    expect(snapshot).to_have_attribute("title", f"snapshot: {knob} 100 %")
    # a change makes the sweep out of date; Render renders the pedal only, nothing moving
    open_chip(page, "guitar")
    page.locator('[data-audio-level="hard"]').click()
    expect(page.locator(".audio-sweep button.stale").first).to_be_visible()
    render = page.get_by_role("button", name="Render", exact=True)
    row = page.locator(".audio-render > *")
    before = [row.nth(i).bounding_box() for i in range(row.count())]
    render.click()
    page.wait_for_function(
        "document.querySelector('.audio-downloads.busy') !== null", timeout=30_000
    )
    assert [row.nth(i).bounding_box() for i in range(row.count())] == before
    expect(page.locator(".audio-downloads.busy")).to_have_count(0, timeout=60_000)
    note = page.locator("[data-sweep-stale]")
    expect(note).to_be_visible()
    expect(note).to_contain_text("Render sweep to update it")
    expect(page.locator(".audio-sweep button.stale").first).to_be_visible()
    page.get_by_role("button", name="Render sweep").click()
    expect(note).to_be_hidden(timeout=60_000)
    expect(page.locator(".audio-sweep button.stale")).to_have_count(0)


def test_pump_switching_shows_only_with_a_charge_pump(page: Page, base_url: str) -> None:
    """A circuit with a charge pump offers its switching in the Pedal drawer, off to start
    (renders about ten times faster); one without has no such box (TODO 2026-11-09)."""
    open_circuit(page, base_url, "klon-centaur-aion")
    open_chip(page, "pedal")
    box = page.locator("[data-pump-ripple]")
    expect(box).to_be_visible()
    expect(box).not_to_be_checked()
    open_circuit(page, base_url, "ts808")
    open_chip(page, "pedal")
    expect(box).to_be_hidden()


def test_an_empty_list_says_so_and_the_info_says_where_to_get_files(
    page: Page, base_url: str, tmp_path: Path
) -> None:
    """Nothing ships in library/audio (D-272: Tone3000's terms forbid bundling its captures
    and IRs, and no clip has a licence on record). A drawer whose list is empty says so in
    one line, gone once a file is uploaded (even with None picked); the pane's ⓘ says where
    to get them, that a full-rig capture needs Cab = None and that clips are up to 10 s."""
    open_circuit(page, base_url, "ts808")
    have = page.request.get(f"{base_url}api/audio").json()
    for chip, kind, text in [
        ("guitar", "clips", "No DI clips loaded."),
        ("amp", "captures", "No amp captures loaded."),
        ("cab", "irs", "No cab IRs loaded."),
    ]:
        open_chip(page, chip)
        note = page.locator(f'[data-empty="{kind}"]')
        expect(note).to_have_text(text)
        expect(note).to_be_hidden() if have[kind] else expect(note).to_be_visible()
    upload(page, "clips", plucks(tmp_path / "empty-note.wav", seconds=0.5))
    open_chip(page, "guitar")
    expect(page.locator('[data-empty="clips"]')).to_be_hidden()
    text = info_text(page, "panel-audio")
    assert "full-rig" in text and "Cab at None" in text and "up to 10 s" in text
    assert text.index("Clips, captures and IRs") < text.index("The chain")  # first (the user)
    page.locator("#panel-audio > summary .info-button").click()
    link = page.locator(".info-pop:not([hidden]) a")
    expect(link).to_have_attribute("href", "https://www.tone3000.com/")
    expect(link).to_have_attribute("target", "_blank")
    page.keyboard.press("Escape")


def test_an_uploaded_amp_and_cab_can_be_deleted(page: Page, base_url: str, tmp_path: Path) -> None:
    """Amps and cabs are deleted as clips are (the user, 2026-11-10): an uploaded one shows
    Delete in its drawer, which asks first; Delete there takes it off the list and the disk.
    The files have names of their own: the tests beside this one upload theirs to the
    same server, and those stay."""
    open_circuit(page, base_url, "ts808")
    amp = tmp_path / "deleteamp.nam"
    amp.write_bytes(NAM.read_bytes())
    upload(page, "captures", amp)
    impulse = np.zeros(480)
    impulse[0] = 0.5
    room = tmp_path / "deleteme.wav"
    room.write_bytes(write_wav(Audio(48000, impulse)))
    upload(page, "irs", room)
    for chip, kind, name in [("amp", "captures", "deleteamp"), ("cab", "irs", "deleteme")]:
        open_chip(page, chip)
        select = page.locator(f'select[data-kind="{kind}"]')
        expect(select).to_have_value(re.compile(f"^user:{name}"))
        delete = page.locator(f'[data-drawer="{chip}"]').get_by_role("button", name="Delete")
        expect(delete).to_be_visible()
        delete.click()  # asks first; Cancel keeps it
        sure = page.locator(".ask")
        expect(sure).to_contain_text(f"Delete {name}")
        sure.get_by_role("button", name="Cancel").click()
        expect(select).to_have_value(re.compile(f"^user:{name}"))
        delete.click()
        sure.get_by_role("button", name="Delete").click()
        expect(select.locator(f'option[value^="user:{name}"]')).to_have_count(0)
        ids = [a["id"] for a in page.request.get(f"{base_url}api/audio").json()[kind]]
        assert not [i for i in ids if i.startswith(name)]
