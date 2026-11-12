"""`solum.probe.freq_axis`: the frequency grid the plots get, with each value as text."""

import numpy as np

from solum.probe import freq_axis


def test_freq_axis_writes_each_frequency_as_the_app_does() -> None:
    axis = freq_axis(np.array([10.0, 998.4, 1234.5, 100_000.0]))
    assert axis["freq"] == [10.0, 998.4, 1234.5, 100_000.0]  # 6 figures: these are exact
    assert axis["freq_text"] == ["10 Hz", "998 Hz", "1.23 kHz", "100 kHz"]
