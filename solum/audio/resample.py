"""Sample-rate conversion (the one owner): band-limited, any ratio, numpy only.

Each output sample is a Kaiser-windowed sinc over the input around its position. The
cutoff sits a little below the lower of the two Nyquist frequencies, so going down
(96 kHz → 48 kHz after the circuit) removes what would alias, and going up adds nothing
above the input's band. Rates are whole numbers, so the output positions fall on a
repeating set of fractional offsets (`up` phases); their coefficients are computed once.
"""

from math import gcd

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]

ZEROS = 32  # sinc zero crossings each side of the centre (sets the filter's steepness)
CUTOFF = 0.94  # passband edge as a fraction of the lower Nyquist frequency
KAISER_BETA = 9.0  # stopband about -90 dB
MAX_PHASES = 2048  # beyond this many phases, coefficients are computed per sample
_CHUNK = 16384  # output samples per block (bounds memory: chunk x taps floats)


def _kernel(dist: Array, cut: float, half: int) -> Array:
    """Windowed sinc at distances `dist` (input samples) from the output position."""
    t = np.clip(dist / (half + 1), -1.0, 1.0)
    window = np.i0(KAISER_BETA * np.sqrt(1.0 - t * t)) / np.i0(KAISER_BETA)
    return np.asarray(cut * np.sinc(cut * dist) * window, dtype=np.float64)


def resample(x: Array, rate_in: int, rate_out: int) -> Array:
    """`x` at `rate_in` as `rate_out` samples; length `round(len(x) * rate_out / rate_in)`."""
    x = np.asarray(x, dtype=np.float64)
    if rate_in <= 0 or rate_out <= 0:
        raise ValueError("Sample rates must be positive.")
    if rate_in == rate_out or len(x) == 0:
        return x.copy()
    g = gcd(rate_in, rate_out)
    up, down = rate_out // g, rate_in // g  # output n sits at input n * down / up
    n_out = round(len(x) * up / down)
    cut = CUTOFF * min(1.0, up / down)
    half = int(np.ceil(ZEROS / cut))
    offsets = np.arange(-half, half + 1)
    padded = np.concatenate([np.zeros(half), x, np.zeros(half + 2)])
    table = None
    if up <= MAX_PHASES:
        frac = np.arange(up)[:, None] / up  # fractional position of each phase
        table = _kernel(frac - offsets[None, :], cut, half)
    out = np.empty(n_out)
    for start in range(0, n_out, _CHUNK):
        n = np.arange(start, min(start + _CHUNK, n_out))
        base, phase = np.divmod(n * down, up)
        if table is not None:
            h = table[phase]
        else:
            h = _kernel((phase / up)[:, None] - offsets[None, :], cut, half)
        taps = base[:, None] + offsets[None, :] + half
        out[start : start + len(n)] = np.einsum("ij,ij->i", h, padded[taps])
    return out
