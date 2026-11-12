"""A measured transistor through ngspice (D-130): its hFE moves the Fuzz Face's bias."""

from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.models import ModelLibrary, load_models
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator
from solum.tester import FitError, fit_bjt, read_tester

REPO = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def models() -> ModelLibrary:
    return load_models([REPO / "library" / "models"])


def test_the_models_own_gain_as_measured_changes_nothing(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    """The form starts a measured part at the model's own gain and leakage, as the tester
    reads them (D-153): given back unchanged, the circuit doesn't move."""
    sim = Simulator(engine, models)
    c = load_circuit(REPO / "library" / "starters" / "fuzz-face.json")
    c = c.with_part("Q1", measured=None).with_part("Q2", measured=None)  # the starter's are set
    same = c
    for ref in ("Q1", "Q2"):
        spec = models.get(c.part(ref).model).bjt_spec()
        assert spec is not None
        same = same.with_part(ref, measured={"hfe": spec["hfe"], "leakage": spec["leakage"]})
    a, b = sim.op(c).voltages, sim.op(same).voltages
    for net in ("Q1.C", "Q2.C", "Q2.E"):
        assert b[sim.resolve(c, net)] == pytest.approx(a[sim.resolve(c, net)], abs=0.01)


def test_q1s_gain_sets_the_bias_and_q2s_hardly(engine: NativeNgspice, models: ModelLibrary) -> None:
    """The Fuzz Face's DC loop runs Q2's emitter back to Q1's base (R4 and the Fuzz pot), so
    Q1's gain sets where both sit: a weaker Q1 needs more base current, which the loop
    takes from Q2's emitter, and Q2.C swings towards 0 V (-1.9 V at hFE 40, -4.4 V at 85,
    -5.5 V at 150). Q2's own gain moves Q2.C by a tenth of a volt from 60 to 200. This is
    why builders pick Q1 for low gain and set Q2's collector with a trimmer."""
    sim = Simulator(engine, models)
    c = load_circuit(REPO / "library" / "starters" / "fuzz-face.json")
    q2c = sim.resolve(c, "Q2.C")

    def at(h1: float, h2: float) -> float:
        both = c.with_part("Q1", measured={"hfe": h1}).with_part("Q2", measured={"hfe": h2})
        return sim.op(both).voltages[q2c]

    weak, typical, hot = at(40, 120), at(85, 120), at(150, 120)
    assert weak > typical + 2 > hot + 2  # -9 V supply: nearer 0 V is higher
    assert abs(at(85, 60) - at(85, 200)) < 0.15


@pytest.mark.parametrize(
    ("model", "hfe"),
    [
        ("AC128", 60),
        ("AC128", 150),
        ("2N3906", 200),
        ("2N5089", 700),  # 900 with 250 µA leaks past the tester's 3.7 mA ceiling (2.4k from 9 V)
        ("MPSA06", 200),
    ],
)
@pytest.mark.parametrize("leakage", [None, 50e-6, 250e-6])
def test_the_tester_reads_a_measured_transistor_back(
    engine: NativeNgspice, models: ModelLibrary, model: str, hfe: float, leakage: float | None
) -> None:
    """D-153: the gain scale and Icbo are fitted on the simulated tester, so it reads the
    measured gain and leakage back (within the fit's 0.1 %), whatever the card's BF is: the
    MPSA06's is 1222 against a tester gain of 84 (at the tester's small current its base
    recombination, ISE, sets the gain), so BF and ISE scale together."""
    m = models.get(model)
    fit = fit_bjt(engine, models, m, hfe, leakage)
    read = read_tester(engine, models, m, fit)
    assert read.gain == pytest.approx(hfe, rel=2e-3)
    if leakage is not None:
        assert read.leakage == pytest.approx(leakage, rel=2e-3)


def test_a_gain_no_bf_reaches_says_so(engine: NativeNgspice, models: ModelLibrary) -> None:
    with pytest.raises(FitError, match="can't be made to read a gain of 1e\\+06"):
        fit_bjt(engine, models, models.get("2N404"), 1e6, None)


def test_the_simulator_fits_measured_transistors(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    sim = Simulator(engine, models)
    fit = sim.models.bjt_fit(models.get("2N404"), 100.0, None)
    assert 1.4 < fit.scale < 1.6  # the tester reads the card at 67: to 100 is about 1.49


def test_q1s_leakage_pushes_q2s_collector_towards_the_supply(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    """A leaky Q1 draws more collector current, so its collector (Q2's base) moves towards
    0 V, Q2 conducts less, and Q2.C falls towards -9 V: about -4.4 V with the cards' own
    10-14 µA, -5.3 V with 100 µA in both, -7.2 V with 300 µA. Q2's leakage alone moves it
    far less (its emitter resistor's feedback)."""
    sim = Simulator(engine, models)
    c = load_circuit(REPO / "library" / "starters" / "fuzz-face.json")
    q2c = sim.resolve(c, "Q2.C")

    def at(l1: float, l2: float) -> float:
        leaky = c.with_part("Q1", measured={"hfe": 85, "leakage": l1})
        leaky = leaky.with_part("Q2", measured={"hfe": 120, "leakage": l2})
        return sim.op(leaky).voltages[q2c]

    base = sim.op(c).voltages[q2c]
    assert at(100e-6, 100e-6) < base - 0.5
    assert at(300e-6, 300e-6) < at(100e-6, 100e-6) - 1.5
    assert abs(at(100e-6, 250e-6) - at(100e-6, 100e-6)) < 0.1


def test_the_tone_bender_mk2s_q1_is_biased_by_its_leakage(
    engine: NativeNgspice, models: ModelLibrary
) -> None:
    """Q1 has no resistor from its base to the supply, only 100k to ground: its collector
    current is its own leakage times its gain. Aion's Deimos notes say Q1 "must have a
    certain minimum amount of leakage" (100-300 µA): at 50 µA the collector sits within half
    a volt of the supply, and more leakage pulls it up (-8.54 V, -7.32 V at 200 µA, -6.48 V
    at 300; the AC128 card, D-170)."""
    sim = Simulator(engine, models)
    c = load_circuit(REPO / "library" / "starters" / "tone-bender-mk2.json")
    q1c = sim.resolve(c, "Q1.C")

    def at(leak: float) -> float:
        return sim.op(c.with_part("Q1", measured={"hfe": 65, "leakage": leak})).voltages[q1c]

    low, mid, high = at(50e-6), at(200e-6), at(300e-6)
    assert low < -8.4  # within 0.6 V of the -9 V supply: hardly conducting
    assert low < mid - 0.5 < high - 1.0
