"""Starter knobs turn the right way (found 2026-10-23: the Fuzz Face's Fuzz pot was wired
end for end, so 100 % gave the least gain). Clockwise (rotation 1) on a gain knob gives
more gain at 1 kHz, from a 10k source so the input impedance counts as it does with a
guitar."""

from pathlib import Path

import numpy as np
import pytest

from solum.circuit.io import load_circuit
from solum.circuit.schema import Pot
from solum.models import load_models
from solum.netlist import Ac
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).parents[2]
GAIN_KNOBS = {"fuzz", "attack", "distortion", "sustain", "sensitivity", "drive", "gain"}
KNOBS = [
    (path.stem, part.knob)  # a dual pot by its name, turning both gangs (D-217)
    for path in sorted((REPO / "library" / "starters").glob("*.json"))
    for part in load_circuit(path).parts
    if isinstance(part, Pot)
    and part.gang in (None, "a")
    and (part.label or "").lower() in GAIN_KNOBS
]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def gain_at_1k(sim: Simulator, starter: str, ref: str, rotation: float) -> float:
    circuit = load_circuit(REPO / "library" / "starters" / f"{starter}.json")
    source = {"source": "pickup", "pickup": {"r": "10k", "l": "1n", "c": "1p"}}
    guitar = next(p.ref for p in circuit.parts if p.type == "guitar")
    circuit = circuit.with_part(ref, rotation=rotation).with_part(guitar, **source)
    ac = sim.ac(circuit, Ac(start=1e3, stop=1e3, per_decade=1))
    return float(20 * np.log10(np.abs(ac.responses[circuit.probes.out][0])))


def test_every_starter_has_a_gain_knob_checked() -> None:
    """All but the Rangemaster, whose one knob is its Volume (D-133)."""
    assert {s for s, _ in KNOBS} == {
        "big-muff-aion-halo", "big-muff-pi-v3", "boss-bd2", "boss-bd2-aion", "boss-ds1",
        "boss-ds1-aion", "fuzz-face", "klon-centaur", "klon-centaur-aion",
        "klon-centaur-aion-built", "marshall-bluesbreaker", "marshall-bluesbreaker-aion",
        "mxr-dyna-comp", "mxr-dyna-comp-aion", "proco-rat", "tone-bender-mk2",
        "tone-bender-mk2-mode", "ts808",
    }  # fmt: skip


@pytest.mark.sim
@pytest.mark.parametrize(("starter", "ref"), KNOBS)
def test_gain_knobs_turn_up_clockwise(sim: Simulator, starter: str, ref: str) -> None:
    assert gain_at_1k(sim, starter, ref, 1.0) > gain_at_1k(sim, starter, ref, 0.0) + 1.0


@pytest.mark.sim
def test_the_tone_benders_1_5_mode_has_less_gain(sim: Simulator) -> None:
    """Aion: Mode "bypasses the first transistor for a lower-gain mode" (D-135)."""
    mk2 = gain_at_1k(sim, "tone-bender-mk2-mode", "VR2", 1.0)
    circuit = load_circuit(REPO / "library" / "starters" / "tone-bender-mk2-mode.json")
    one_five = circuit.with_part("SW1", position=1)
    ac = sim.ac(
        one_five.with_part("IN", source="pickup", pickup={"r": "10k", "l": "1n", "c": "1p"}),
        Ac(start=1e3, stop=1e3, per_decade=1),
    )
    gain = float(20 * np.log10(np.abs(ac.responses[circuit.probes.out][0])))
    assert gain < mk2 - 10.0


@pytest.mark.sim
def test_fuzz_face_at_full_fuzz(sim: Simulator) -> None:
    """At 100 % the emitter is bypassed: 42.1 dB through a 10k source (12.4 dB at 0 %)."""
    assert gain_at_1k(sim, "fuzz-face", "VR1", 1.0) == pytest.approx(42.1, abs=0.3)


def fuzz_face_at(sim: Simulator, fuzz: float) -> tuple[float, float]:
    """The Fuzz Face's input impedance at 1 kHz (from a 10k source: Zin = 10k·v/(1 - v)) and
    the gain from Q1's base to Q2's emitter, where the feedback resistor R4 is fed from."""
    circuit = load_circuit(REPO / "library" / "starters" / "fuzz-face.json")
    source = {"source": "pickup", "pickup": {"r": "10k", "l": "1n", "c": "1p"}}
    circuit = circuit.with_part("VR1", rotation=fuzz).with_part("IN", **source)
    ac = sim.ac(circuit, Ac(start=1e3, stop=1e3, per_decade=1))
    assert circuit.probes.in_ is not None
    v = ac.responses[circuit.probes.in_][0]
    base, emitter = (ac.responses[sim.resolve(circuit, n)][0] for n in ("Q1.B", "Q2.E"))
    return float(abs(10e3 * v / (1 - v))), float(abs(emitter / base))


def test_fuzz_face_input_impedance_is_set_by_the_feedback(sim: Simulator) -> None:
    """Phase 8b (D-098): ElectroSmash gives 5.2k-8.4k from its simulation, with no Fuzz
    setting or method (https://electrosmash.com/fuzz-face, snapshot
    http://web.archive.org/web/20260518130743/https://electrosmash.com/fuzz-face, read
    2026-10-23), and no measured build was found. Ours: 6.6k at full Fuzz (Q1 at hFE 85, the
    AC128 card, D-170), where C2 grounds Q2's emitter and Zin is about Q1's rπ (the page's
    own estimate: 8K); and well under 1k
    at low Fuzz, where Q2's emitter follows its base and R4 (100k) feeds the input back:
    Zin ≈ R4/(1 + A), A the gain from Q1's base to Q2's emitter (Miller)."""
    full, _ = fuzz_face_at(sim, 1.0)
    assert 5.2e3 <= full <= 8.4e3  # inside the page's range
    low, gain = fuzz_face_at(sim, 0.0)
    assert low < 1e3
    assert low == pytest.approx(100e3 / (1 + gain), rel=0.1)
