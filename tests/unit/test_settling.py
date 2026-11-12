"""D-122: whether a wave has settled by a wait, from its windows after the wait, twice it
and four times it (`solum.simulate._repeats`), on waves whose settling is known."""

from collections.abc import Callable

import numpy as np
import pytest

from solum.simulate import MEASURE_CYCLES, SETTLE_HZ, _repeats

Array = np.ndarray
WAIT = 0.05  # s, the first wait the search tries
PEAK = 1.0  # V, the guitar's hard pick


def wave(shape: Callable[[Array], Array]) -> tuple[Array, Array]:
    """A run of the search's length, 400 steps a cycle, as `shape(t)`."""
    t = np.arange(0, 4 * WAIT + MEASURE_CYCLES / SETTLE_HZ + 1e-9, 1 / (SETTLE_HZ * 400))
    return t, shape(t)


def sine(t: Array) -> Array:
    return np.sin(2 * np.pi * SETTLE_HZ * t)


def test_a_steady_sine_has_settled() -> None:
    assert _repeats(*wave(lambda t: 0.5 * sine(t)), WAIT, PEAK)


def test_a_fast_decay_has_settled_and_a_slow_one_has_not() -> None:
    # amplitude 0.5 V growing to 0.6 V with time constant tau: by 50 ms, tau = 5 ms is
    # e^-10 of the way off; tau = 100 ms still 60 % off
    def growing(tau: float) -> Callable[[Array], Array]:
        return lambda t: (0.6 - 0.1 * np.exp(-t / tau)) * sine(t)

    assert _repeats(*wave(growing(0.005)), WAIT, PEAK)
    assert not _repeats(*wave(growing(0.1)), WAIT, PEAK)


def test_a_drift_too_slow_to_see_in_one_doubling_has_not_settled() -> None:
    # 0.4 %/doubling at first, under the 1 % tolerance, but growing with each doubling
    # (a 47 uF clamp): a slow, steady rise in the second harmonic
    t, v = wave(lambda t: 0.5 * sine(t) + (0.01 + 0.08 * t) * np.sin(4 * np.pi * SETTLE_HZ * t))
    assert not _repeats(t, v, WAIT, PEAK)


def test_dc_wandering_alone_is_not_drift() -> None:
    # a reference rail's big cap: the DC creeps 50 mV, the signal on it doesn't change
    assert _repeats(*wave(lambda t: 4.5 + 0.25 * t + 0.01 * sine(t)), WAIT, PEAK)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_spikes_whose_tops_jitter_are_not_drift(seed: int) -> None:
    """A cap after a clipped stage: a narrow spike each edge, its top depending on where
    the steps land (here random, up to 30 %), on a steady clipped wave."""
    rng = np.random.default_rng(seed)

    def spiky(t: Array) -> Array:
        clipped = np.clip(2 * sine(t), -0.6, 0.6)
        cycle = np.floor(t * SETTLE_HZ).astype(int)
        tops = 1 + 0.3 * rng.random(cycle.max() + 1)
        phase = (t * SETTLE_HZ) % 1
        spike = np.where(phase < 0.005, tops[cycle], 0.0)
        return clipped + spike

    assert _repeats(*wave(spiky), WAIT, PEAK)


def test_a_small_signal_counts_against_a_floor() -> None:
    # a net carrying 1 mV whose level grows 10 %: under 5 % of the guitar's peak, the
    # change is tiny next to the floor, so it isn't held up waiting for it
    def faint(t: Array) -> Array:
        return (0.001 - 0.0001 * np.exp(-t / 0.1)) * sine(t)

    assert _repeats(*wave(faint), WAIT, PEAK)
