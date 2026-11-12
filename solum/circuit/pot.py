"""Pot model: rotation + taper → the two resistances either side of the wiper.

Rotation 0 puts the wiper at pin 1 (fully counter-clockwise), 1 at pin 3. A taper gives
the fraction of the track between pin 1 and the wiper, as straight segments between
breakpoints (real carbon tracks are made from a few segments too). See D-035.
"""

import numpy as np

# (rotation, fraction of track from pin 1 to the wiper)
TAPERS: dict[str, tuple[tuple[float, float], ...]] = {
    "B": ((0.0, 0.0), (1.0, 1.0)),  # linear
    "A": ((0.0, 0.0), (0.5, 0.1), (1.0, 1.0)),  # audio (log): 10 % at half rotation
    "C": ((0.0, 0.0), (0.5, 0.9), (1.0, 1.0)),  # reverse audio
    # "G"/"W"/"S" taper, read from the curve on ElectroSmash's TS808 page
    # (Tone pot): steep at the ends, flat through the middle.
    "W": ((0.0, 0.0), (0.1, 0.28), (0.2, 0.37), (0.5, 0.5), (0.8, 0.63), (0.9, 0.72),
          (1.0, 1.0)),
}  # fmt: skip

# A real wiper never reaches 0 ohms; this also keeps the simulator's matrix well-behaved.
MIN_RESISTANCE = 1.0


def taper_fraction(rotation: float, taper: str = "B") -> float:
    """Fraction of the track between pin 1 and the wiper at this rotation (0-1)."""
    if not 0.0 <= rotation <= 1.0:
        raise ValueError(f"Rotation must be between 0 and 1 (got {rotation}).")
    try:
        points = TAPERS[taper]
    except KeyError:
        raise ValueError(f"Unknown taper {taper!r}; use one of {', '.join(TAPERS)}.") from None
    xs, ys = zip(*points, strict=True)
    return float(np.interp(rotation, xs, ys))


def pot_resistances(total: float, rotation: float, taper: str = "B") -> tuple[float, float]:
    """(pin 1 to wiper, wiper to pin 3) in ohms, each at least MIN_RESISTANCE."""
    fraction = taper_fraction(rotation, taper)
    return (
        max(total * fraction, MIN_RESISTANCE),
        max(total * (1.0 - fraction), MIN_RESISTANCE),
    )
