"""High-gain stages for the placement limits (D-400, P6i3), through real ngspice: a stage
input on the signal path whose gain to the output (the last pot's input) reaches 25 dB
with the pots as set, all down or all up, or 20 dB on a node of 470 kΩ or more with the
guitar out."""

from pathlib import Path

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.models import load_models
from solum.probe import loud_inputs
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator

REPO = Path(__file__).resolve().parents[2]
STARTERS = REPO / "library" / "starters"


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


@pytest.mark.parametrize(
    ("name", "loud"),
    [
        # the input buffer and the clipping stage (28 dB to the Level with the Drive up),
        # not the buffers after them
        ("ts808", [("Q1", "B"), ("IC1B", "+")]),
        ("proco-rat", [("IC1", "+")]),
        ("dallas-rangemaster", [("Q1", "B")]),
        ("fuzz-face", [("Q1", "B")]),  # Q2's base: under 15 dB to the Volume
        ("mxr-dyna-comp", [("Q1", "B")]),  # 36 dB to the Output with Sensitivity up
        ("boss-ds1", [("Q2", "B"), ("Q1", "B")]),  # not Q3, the buffer after the Tone
    ],
)
def test_the_high_gain_stages_are_found_by_their_gain_to_the_output(
    sim: Simulator, name: str, loud: list[tuple[str, str]]
) -> None:
    found = loud_inputs(sim, load_circuit(STARTERS / f"{name}.json"))
    assert [(x.ref, x.pin) for x in found] == loud


def test_each_input_comes_with_the_nets_ac_quiet_beside_it(sim: Simulator) -> None:
    """D-400 narrowed (P6h5e): a net under 1 % of the input's signal is quiet: the rails,
    ground and the Rat's Vref behind its cap, not the input's own net nor the stage's
    output."""
    (rat,) = loud_inputs(sim, load_circuit(STARTERS / "proco-rat.json"))
    assert {"GND", "V+", "VREF"} <= rat.quiet
    assert "IC1.+" not in rat.quiet and "IC1.out" not in rat.quiet
    (q1,) = loud_inputs(sim, load_circuit(STARTERS / "dallas-rangemaster.json"))
    assert {"GND", "V-"} <= q1.quiet and "Q1.B" not in q1.quiet


def booster(bias: str, gain: str, follower: bool = False) -> Circuit:
    """The guitar into a TL071 with `bias` from + to Vref (its impedance with the guitar
    out), non-inverting with 1 + `gain`/10k (or a follower), into the amp."""
    b = (
        CircuitBuilder()
        .rail("V+", 9)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "p", value="100n", kind="film")
        .part("R1", "resistor", "p", "vb", value=bias)
        .part("R2", "resistor", "V+", "vb", value="10k")
        .part("R3", "resistor", "vb", "GND", value="10k")
        .part("C2", "capacitor", "vb", "GND", value="10u", kind="electrolytic")
        .part("C5", "capacitor", "V+", "GND", value="100n", kind="ceramic")
        .part("C6", "capacitor", "o", "out", value="1u", kind="film")
        .part("R6", "resistor", "out", "GND", value="100k")
        .part("OUT", "amp", "out")
    )
    if follower:
        return b.part("IC1", "opamp", "p", "o", "o", model="TL071").build()
    return (
        b.part("IC1", "opamp", "p", "m", "o", model="TL071")
        .part("R4", "resistor", "o", "m", value=gain)
        .part("R5", "resistor", "m", "g", value="10k")
        .part("C4", "capacitor", "g", "GND", value="10u", kind="electrolytic")
        .build()
    )


def test_a_unity_buffer_never_counts(sim: Simulator) -> None:
    assert loud_inputs(sim, booster("1M", "", follower=True)) == []


def test_a_high_impedance_node_before_a_small_stage_counts(sim: Simulator) -> None:
    """A 1 + 100k/10k stage, 21 dB: on a 1 MΩ-biased input (1 MΩ with the guitar out) it
    counts; on a 100 kΩ one it doesn't (under 25 dB); 1 + 220k/10k, 27 dB, counts on
    either."""
    assert [(x.ref, x.pin) for x in loud_inputs(sim, booster("1M", "100k"))] == [("IC1", "+")]
    assert loud_inputs(sim, booster("100k", "100k")) == []
    assert [(x.ref, x.pin) for x in loud_inputs(sim, booster("100k", "220k"))] == [("IC1", "+")]


def test_each_input_comes_with_the_later_nets_in_phase_with_it(sim: Simulator) -> None:
    """P6i2 (D-404): the Fuzz Face's Q2 collector (the output, two inversions on: in phase
    with Q1's base) is kept off its side; Q1's own collector (inverted), its emitter (its own
    pin, grounded) and Q2's emitter (joined to the base by the feedback resistor) aren't.
    A non-inverting booster's output is in phase with its +; its − input (its own
    feedback, meant) isn't listed."""
    (q1,) = loud_inputs(sim, load_circuit(STARTERS / "fuzz-face.json"))
    assert "out" in q1.along and "q2c" in q1.along
    assert "Q2.E" not in q1.along  # joined to Q1's base by R1, its feedback: meant
    assert "q1c" not in q1.along and "GND" not in q1.along  # Q1's collector, inverted
    (amp,) = loud_inputs(sim, booster("100k", "220k"))
    assert "o" in amp.along and "m" not in amp.along
