# ruff: noqa: E501  (JavaScript inside strings)
"""`web/live.js`, the live curves' DOM-free logic, run in the browser."""

import math
from typing import Any

import pytest
from playwright.sync_api import Page

from tests.ui.conftest import run

SLIDERS: list[dict[str, Any]] = [
    {"ref": "R1", "field": "value", "series": "E12", "index": 1, "nearest": None,
     "steps": [{"value": "1k", "text": "1k", "elements": {"R1": 1000.0}},
               {"value": "10k", "text": "10k", "elements": {"R1": 10000.0}}]},
    {"ref": "VR1", "field": "rotation", "series": None, "index": 1, "nearest": None,
     "steps": [{"value": 0.0, "text": "0 %", "elements": {"R_VR1_a": 1.0, "R_VR1_b": 1e4}},
               {"value": 0.5, "text": "50 %", "elements": {"R_VR1_a": 5e3, "R_VR1_b": 5e3}},
               {"value": 1.0, "text": "100 %", "elements": {"R_VR1_a": 1e4, "R_VR1_b": 1.0}}]},
]  # fmt: skip
# 1 V at node "in" (index 0) through R1 (10k) to "out" (index 1), R2 (10k) to ground
DIVIDER = {
    "system": {
        "freq": [100.0, 1000.0], "nodes": ["in", "out"], "out": -1,
        "elements": [{"k": "V", "name": "VIN", "n": [0, -1], "v": 1.0},
                     {"k": "R", "name": "R1", "n": [0, 1], "v": 1e4},
                     {"k": "R", "name": "R2", "n": [1, -1], "v": 1e4}],
    },
    "nets": {"in": 0, "out": 1, "GND": -1},
    "sliders": SLIDERS[:1],
    "valid": True,
}  # fmt: skip


def live(page: Page, body: str, arg: Any = None) -> Any:
    return run(page, f"const l = await m('live.js'); {body}", arg)


def test_live_values_take_every_slider_at_its_step(js: Page) -> None:
    assert live(js, "return l.liveValues(arg, [0, 2]);", SLIDERS) == {
        "R1": 1000.0, "R_VR1_a": 1e4, "R_VR1_b": 1.0,
    }  # fmt: skip


def test_live_curves_solve_every_net(js: Page) -> None:
    # within 1e-6 dB: the solver's GMIN (1e-12 S to ground) shifts a 10k divider by ~4e-8 dB
    curves = live(js, "return l.liveCurves(arg, {});", DIVIDER)
    assert curves["freq"] == [100.0, 1000.0]
    assert curves["nodes"]["in"] == pytest.approx([0.0, 0.0], abs=1e-9)
    assert curves["nodes"]["out"] == pytest.approx([20 * math.log10(0.5)] * 2, abs=1e-6)
    # R1 at its 1k step: 10k / 11k
    moved = live(js, "return l.liveCurves(arg, {R1: 1000});", DIVIDER)
    assert moved["nodes"]["out"][0] == pytest.approx(20 * math.log10(10 / 11), abs=1e-6)
    assert live(js, "return l.liveCurves({...arg, system: null}, {});", DIVIDER) is None


def test_nearest_step_and_kept_steps(js: Page) -> None:
    nearest = live(js, "return [0.1, 0.3, 0.9].map((r) => l.nearestStep(arg[1], r));", SLIDERS)
    assert nearest == [0, 1, 2]
    # only value sliders keep their steps
    assert live(js, "return l.keptSteps(arg);", SLIDERS) == {"R1.value": ["1k", "10k"]}
    assert live(js, "return l.sliderKey(arg[1]);", SLIDERS) == "VR1.rotation"


def test_reading_rows(js: Page) -> None:
    rows = live(js, "return l.readingRows(arg);", [
        {"label": "Dip", "readings": [{"name": "f", "value": 612.0, "unit": "Hz", "text": "612 Hz"},
                                      {"name": "gain", "value": -18.43, "unit": "dB", "text": "-18.4 dB"},
                                      {"name": "depth", "value": -9.0, "unit": "dB", "text": "-9.0 dB"}]},
        {"label": "Low -3 dB", "none": "The response doesn't fall 3 dB below its peak within the sweep."},
    ])  # fmt: skip
    minus = "\N{MINUS SIGN}"  # fixed.js writes negative dB with a true minus
    text = f"612 Hz \N{MIDDLE DOT} {minus}18.4 dB \N{MIDDLE DOT} depth {minus}9.0 dB"
    assert rows[0] == {"label": "Dip", "text": text, "title": ""}
    assert rows[1]["text"] == "\N{EM DASH}" and "3 dB" in rows[1]["title"]
