"""The browser's band levels (`web/bands.js`, the Audio panel's live line) against the
server's `band_levels` (D-096): the same recording reads the same in every band."""

import numpy as np
import pytest
from playwright.sync_api import Page

from solum.analysis.signal import band_levels
from tests.ui.conftest import run

RATE = 48000


def browser_bands(page: Page, samples: np.ndarray, rate: int) -> dict[str, list[float]]:
    result: dict[str, list[float]] = run(
        page,
        "const b = await m('bands.js'); return b.bandLevels(arg.x, arg.rate);",
        {"x": samples.tolist(), "rate": rate},
    )
    return result


@pytest.mark.parametrize(("seconds", "offset"), [(0.2, 0.0), (1.0, 0.0), (1.0, 0.3)])
def test_band_levels_match_the_server(js: Page, seconds: float, offset: float) -> None:
    """Every band from 10 Hz up to Nyquist (D-102), each taking its share of the bins it
    overlaps, a DC offset taken off."""
    rng = np.random.default_rng(7)
    t = np.arange(int(RATE * seconds)) / RATE
    x = offset + 0.5 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 3100 * t)
    x += 0.01 * rng.standard_normal(len(t))
    centres, levels = band_levels(x, RATE)
    got = browser_bands(js, x, RATE)
    assert got["freq"] == pytest.approx(centres.tolist(), rel=1e-12)
    assert got["levels"] == pytest.approx(levels.tolist(), abs=0.01)


def test_a_sine_reads_its_rms_and_silence_reads_the_floor(js: Page) -> None:
    t = np.arange(RATE) / RATE
    got = browser_bands(js, np.sin(2 * np.pi * 1000 * t), RATE)
    band = int(np.argmin(np.abs(np.array(got["freq"]) - 1000)))
    assert got["levels"][band] == pytest.approx(20 * np.log10(1 / np.sqrt(2)), abs=0.05)
    silent = browser_bands(js, np.zeros(RATE), RATE)
    assert set(silent["levels"]) == {-200.0}
