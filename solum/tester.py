"""The Geofex transistor tester (D-130) simulated, and a measured transistor fitted on it
(D-153): the gain and leakage that make the simulated tester read what the builder's did.

The tester: a 9 V battery, the emitter to its common end, the collector through 2.4 kΩ to
the supply. Leakage is the collector current with the base open; gain is the collector
current with 2.2 MΩ from base to supply, less the leakage, over the base current.
"""

from dataclasses import dataclass

from solum.circuit.build import CircuitBuilder
from solum.models import BjtFit, Model, ModelLibrary
from solum.netlist import Op, generate_netlist
from solum.sim.engine import SimEngine

VCC = 9.0
RC = 2.4e3
RB = 2.2e6
RTOL = 1e-3  # the fit stops once the tester reads within 0.1 %
MAX_STEPS = 30
SCALE_RANGE = (1e-3, 1e3)  # a thousandth to a thousand times the card's gain
_fits: dict[tuple[str, str, float, float | None], BjtFit] = {}  # a fit depends on the card


class FitError(ValueError):
    """A measured gain or leakage the tester can't be made to read (plain English)."""


@dataclass(frozen=True)
class Reading:
    gain: float  # (collector current with the base fed, less the leakage) / base current
    leakage: float  # amps: collector current, base open


def _collector(
    engine: SimEngine, models: ModelLibrary, model: Model, fit: BjtFit | None, base_fed: bool
) -> tuple[float, float]:
    """(collector current, base current) on the tester; `fit`: the card's gain scale and Icbo
    set as a measured part's would be, None for the card as it is."""
    sign = 1.0 if model.polarity == "n" else -1.0
    measured = None
    if fit is not None:  # the values are placeholders: the fitter below returns `fit`
        measured = {"hfe": 1.0, "leakage": 0.0}
        models = models.with_fitter(lambda _m, _h, _l: fit)
    b = (
        CircuitBuilder("tester")
        .part("V1", "vsource", "VS", "0", value=sign * VCC)
        .part("R3", "resistor", "VS", "c", value=RC)
        .part("Q1", "bjt", "c", "b", "0", model=model.id, measured=measured)
        .part("R2", "resistor", "b", "VS" if base_fed else "0", value=RB if base_fed else 1e12)
    )  # fmt: skip
    netlist = generate_netlist(b.build(), models, Op())
    vectors = engine.run(netlist.text).plot("op").vectors
    volts = {n: float(vectors[v][0].real) for n, v in netlist.nodes.items() if v in vectors}
    vs, vc, vb = volts["VS"], volts["c"], volts.get("b", 0.0)
    return abs(vs - vc) / RC, abs(vs - vb) / RB if base_fed else 0.0


def read_tester(
    engine: SimEngine, models: ModelLibrary, model: Model, fit: BjtFit | None = None
) -> Reading:
    """What the tester reads for `model` (with `fit`'s gain scale and Icbo, if given)."""
    leak, _ = _collector(engine, models, model, fit, base_fed=False)
    ic, ib = _collector(engine, models, model, fit, base_fed=True)
    return Reading((ic - leak) / ib, leak)


def fit_bjt(
    engine: SimEngine, models: ModelLibrary, model: Model, hfe: float, leakage: float | None
) -> BjtFit:
    """The gain scale and Icbo that make the tester read `hfe` and `leakage` (None: the
    card's own leakage, Icbo 0). Each step scales the gain by how far it reads off and adds
    the missing leakage over the gain; a few steps settle it. Remembered per card and
    values."""
    key = (model.id, model.card, hfe, leakage)
    if key in _fits:
        return _fits[key]
    own = read_tester(engine, models, model)
    fit = BjtFit(hfe / own.gain, 0.0)
    for _ in range(MAX_STEPS):
        read = read_tester(engine, models, model, fit)
        leak_ok = leakage is None or abs(read.leakage - leakage) <= max(RTOL * leakage, 1e-9)
        if abs(read.gain - hfe) <= RTOL * hfe and leak_ok:
            _fits[key] = fit
            return fit
        scale = fit.scale * hfe / read.gain
        if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
            break
        icbo = fit.icbo if leakage is None else fit.icbo + (leakage - read.leakage) / (hfe + 1)
        fit = BjtFit(scale, icbo)
    raise FitError(
        f"The {model.id} model can't be made to read a gain of {hfe:g}"
        + ("" if leakage is None else f" with {leakage * 1e6:.3g} µA of leakage")
        + " on the tester. Check the measurement, or pick a model nearer your transistor."
    )
