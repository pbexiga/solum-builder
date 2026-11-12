"""The tone-stack blocks through real ngspice against published references: the Fender
TMB against Yeh & Smith's closed-form transfer function, the Big Muff tone stack against
ElectroSmash's notch (D-080).

Reference: D. T. Yeh and J. O. Smith, "Discretization of the '59 Fender Bassman Tone
Stack", Proc. DAFx-06, Montreal, 2006, eq. (1), pp. 2.
https://ccrma.stanford.edu/~dtyeh/papers/yeh06_dafx.pdf (read 2026-10-21). The paper
checked eq. (1) against SPICE ("an exact match") and names Duncan's Tone Stack Calculator
as doing the same numerical analysis (D-080).
"""

import math
from pathlib import Path

import numpy as np
import pytest

from solum.analysis.compare import knob_range
from solum.analysis.measures import notch, to_db
from solum.circuit.pot import taper_fraction
from solum.models import load_models
from solum.probe import knob_ranges
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator
from solum.units import parse_value
from tests.jig import core_block, jig, with_values

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def yeh_smith(
    s: np.ndarray, t: float, l: float, m: float,  # noqa: E741 (the paper's names)
    *, c1: float, c2: float, c3: float, r1: float, r2: float, r3: float, r4: float,
) -> np.ndarray:  # fmt: skip
    """Eq. (1): H(s) = (b1 s + b2 s² + b3 s³) / (a0 + a1 s + a2 s² + a3 s³). t treble, l
    bass, m middle (0-1); R1 treble pot, R2 bass pot, R3 mid pot, R4 slope resistor; C1
    treble cap, C2 bass cap, C3 mid cap. Transcribed term by term from the paper."""
    C1, C2, C3, R1, R2, R3, R4 = c1, c2, c3, r1, r2, r3, r4
    b1 = t * C1 * R1 + m * C3 * R3 + l * (C1 * R2 + C2 * R2) + (C1 * R3 + C2 * R3)
    b2 = (
        t * (C1 * C2 * R1 * R4 + C1 * C3 * R1 * R4)
        - m**2 * (C1 * C3 * R3**2 + C2 * C3 * R3**2)
        + m * (C1 * C3 * R1 * R3 + C1 * C3 * R3**2 + C2 * C3 * R3**2)
        + l * (C1 * C2 * R1 * R2 + C1 * C2 * R2 * R4 + C1 * C3 * R2 * R4)
        + l * m * (C1 * C3 * R2 * R3 + C2 * C3 * R2 * R3)
        + (C1 * C2 * R1 * R3 + C1 * C2 * R3 * R4 + C1 * C3 * R3 * R4)
    )
    c123 = C1 * C2 * C3
    b3 = (
        l * m * (c123 * R1 * R2 * R3 + c123 * R2 * R3 * R4)
        - m**2 * (c123 * R1 * R3**2 + c123 * R3**2 * R4)
        + m * (c123 * R1 * R3**2 + c123 * R3**2 * R4)
        + t * c123 * R1 * R3 * R4
        - t * m * c123 * R1 * R3 * R4
        + t * l * c123 * R1 * R2 * R4
    )
    a0 = 1.0
    a1 = (C1 * R1 + C1 * R3 + C2 * R3 + C2 * R4 + C3 * R4) + m * C3 * R3 + l * (C1 * R2 + C2 * R2)
    a2 = (
        m * (C1 * C3 * R1 * R3 - C2 * C3 * R3 * R4 + C1 * C3 * R3**2 + C2 * C3 * R3**2)
        + l * m * (C1 * C3 * R2 * R3 + C2 * C3 * R2 * R3)
        - m**2 * (C1 * C3 * R3**2 + C2 * C3 * R3**2)
        + l * (C1 * C2 * R2 * R4 + C1 * C2 * R1 * R2 + C1 * C3 * R2 * R4 + C2 * C3 * R2 * R4)
        + (C1 * C2 * R1 * R4 + C1 * C3 * R1 * R4 + C1 * C2 * R3 * R4 + C1 * C2 * R1 * R3
           + C1 * C3 * R3 * R4 + C2 * C3 * R3 * R4)
    )  # fmt: skip
    a3 = (
        l * m * (c123 * R1 * R2 * R3 + c123 * R2 * R3 * R4)
        - m**2 * (c123 * R1 * R3**2 + c123 * R3**2 * R4)
        + m * (c123 * R3**2 * R4 + c123 * R1 * R3**2 - c123 * R1 * R3 * R4)
        + l * c123 * R1 * R2 * R4
        + c123 * R1 * R3 * R4
    )
    result: np.ndarray = (b1 * s + b2 * s**2 + b3 * s**3) / (a0 + a1 * s + a2 * s**2 + a3 * s**3)
    return result


def test_the_transcribed_formula_is_a_passive_cut() -> None:
    # Fig. 2's setting (t = l = m = 0.5, Bassman values): a broad low-mid hump just under
    # 0 dB and a dip near 700 Hz, as plotted; checks the transcription, not our circuit
    f = np.logspace(0, 4.3, 400)
    h = yeh_smith(2j * np.pi * f, 0.5, 0.5, 0.5, c1=250e-12, c2=20e-9, c3=20e-9, r1=250e3,
                  r2=1e6, r3=25e3, r4=56e3)  # fmt: skip
    db = to_db(h)
    assert db.max() < 0
    dip = f[(f > 100) & (f < 5000)][np.argmin(db[(f > 100) & (f < 5000)])]
    assert 500 < dip < 1000
    assert -14 < db[(f > 100) & (f < 5000)].min() < -10


SETTINGS = [(0.5, 0.5, 0.5), (0.2, 0.8, 0.5), (0.8, 0.2, 0.9), (0.95, 0.05, 0.3),
            (0.1, 0.1, 0.1), (0.5, 0.95, 0.95)]  # fmt: skip


@pytest.mark.parametrize(("treble", "bass", "middle"), SETTINGS)
def test_fender_tmb_matches_yeh_smith(
    sim: Simulator, treble: float, bass: float, middle: float
) -> None:
    """Our TMB block is the paper's circuit with its Middle control fully up (m = 1): the
    mid pot is a variable resistor from the mid cap to ground, whose resistance takes the
    place of R3. Treble and bass map to t and l through each pot's taper."""
    block = with_values(core_block("fender-tmb"), {
        "VR1": {"rotation": treble}, "VR2": {"rotation": bass}, "VR3": {"rotation": middle},
    })  # fmt: skip
    # an ideal source and no load, as the formula assumes
    circuit = jig(block, source_ohms=0, load_ohms=1e15)
    ac = sim.ac(circuit)
    assert circuit.probes.out is not None
    ours = to_db(ac.responses[circuit.probes.out])

    def value(ref: str) -> float:
        return parse_value(block.part(ref).value)

    def fraction(ref: str) -> float:
        part = block.part(ref)
        return taper_fraction(part.rotation, part.taper)

    theirs = to_db(yeh_smith(
        2j * np.pi * ac.freq, fraction("VR1"), fraction("VR2"), 1.0,
        c1=value("C1"), c2=value("C2"), c3=value("C3"), r1=value("VR1"),
        r2=value("VR2"), r3=max(fraction("VR3") * value("VR3"), 1.0), r4=value("R1"),
    ))  # fmt: skip
    assert np.abs(ours - theirs).max() < 0.01  # dB, over 10 Hz-100 kHz


def test_big_muff_tone_notch_matches_electrosmash(sim: Simulator) -> None:
    """ElectroSmash, "Big Muff Pi Analysis", Tone Control section
    (https://electrosmash.com/big-muff-pi-analysis, read 2026-10-20; the figure is also in
    tests/fixtures/acceptance/big-muff-pi-v3.expected.yaml): about 6.5 dB more lost at the
    notch, -13.5 dB in all, at 1 kHz. The page analyses the stack on its own, so it's
    taken from an ideal source into no load, Tone at noon."""
    circuit = jig(core_block("big-muff-tone"), source_ohms=0, load_ohms=1e15)
    ac = sim.ac(circuit)
    assert circuit.probes.out is not None
    f, db = notch(ac.freq, ac.responses[circuit.probes.out], (200, 5000))
    assert f == pytest.approx(1000, rel=0.15)
    assert db == pytest.approx(-13.5, abs=1.0)


# ---- knob ranges (Phase 8b): where each TMB knob acts, against eq. (1) ----------------

TMB_KNOBS = {"VR1": "t", "VR2": "l", "VR3": "m"}


@pytest.mark.parametrize("knob", list(TMB_KNOBS))
def test_tmb_knob_ranges_match_yeh_smith(sim: Simulator, knob: str) -> None:
    """Each knob's range (where it acts, as `knob_range` reads it) from our ngspice runs
    and from eq. (1) at the knob's two ends: the band edges agree within a third of an
    octave (Phase 8b's acceptance), and the kind matches."""
    block = with_values(core_block("fender-tmb"), {
        "VR1": {"rotation": 0.5}, "VR2": {"rotation": 0.5}, "VR3": {"rotation": 0.5},
    })  # fmt: skip
    circuit = jig(block, source_ohms=0, load_ohms=1e15)
    assert circuit.probes.out is not None
    ours = {k["ref"]: k for k in knob_ranges(sim, circuit, circuit.probes.out)["knobs"]}

    def value(ref: str) -> float:
        return parse_value(block.part(ref).value)

    def curve(rotation: float | None) -> np.ndarray:
        frac = {r: taper_fraction(block.part(r).rotation, block.part(r).taper) for r in TMB_KNOBS}
        if rotation is not None:
            frac[knob] = taper_fraction(rotation, block.part(knob).taper)
        return yeh_smith(
            2j * np.pi * freq, frac["VR1"], frac["VR2"], 1.0, c1=value("C1"), c2=value("C2"),
            c3=value("C3"), r1=value("VR1"), r2=value("VR2"),
            r3=max(frac["VR3"] * value("VR3"), 1.0), r4=value("R1"),
        )  # fmt: skip

    freq = sim.ac(circuit).freq
    theirs = knob_range(freq, curve(0.0), curve(1.0), curve(None))
    got = ours[knob]
    assert got["valid"] and got["kind"] == theirs["kind"]
    assert got["band"]["kind"] == theirs["band"]["kind"]
    for edge in ("lo", "hi"):
        assert abs(math.log2(got["band"][edge] / theirs["band"][edge])) < 1 / 3
    assert got["swing"] == pytest.approx(theirs["swing"], abs=0.1)


def test_tmb_knobs_act_where_their_names_say(sim: Simulator) -> None:
    """Bass acts on the lows, Treble on the highs, Middle in between."""
    circuit = jig(core_block("fender-tmb"), source_ohms=0, load_ohms=1e15)
    assert circuit.probes.out is not None
    knobs = {k["ref"]: k for k in knob_ranges(sim, circuit, circuit.probes.out)["knobs"]}
    assert knobs["VR2"]["band"]["kind"] == "below"
    assert knobs["VR1"]["band"]["kind"] == "above"
    assert knobs["VR2"]["band"]["hi"] < knobs["VR3"]["band"]["centre"] < knobs["VR1"]["band"]["lo"]
