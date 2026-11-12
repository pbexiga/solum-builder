"""Measure a device model's datasheet characteristics through the real pipeline.

Used by `tests/sim/test_models.py` to re-check every model's validation record, and when
a model is added (Tools → Add a model, `solum.model_import`), to fill that record in.
"""

import math
from collections.abc import Callable

import numpy as np

from solum import tester
from solum.circuit.build import CircuitBuilder
from solum.models import Model, ModelLibrary
from solum.netlist import Ac, Op, generate_netlist
from solum.sim.engine import SimEngine
from solum.units import format_value


def _op(engine: SimEngine, models: ModelLibrary, b: CircuitBuilder) -> dict[str, float]:
    netlist = generate_netlist(b.build(), models, Op())
    vectors = engine.run(netlist.text).plot("op").vectors
    out = {
        net: float(vectors[node][0].real) for net, node in netlist.nodes.items() if node in vectors
    }
    for ref, name in netlist.devices.items():
        for key in ("ic", "ib", "id"):
            vec = f"@{name.lower()}[{key}]"
            if vec in vectors:
                out[f"{ref}.{key}"] = float(vectors[vec][0].real)
    return out


def diode_vf(
    engine: SimEngine, models: ModelLibrary, model: Model, current: float, reverse: bool = False
) -> float:
    """Forward voltage at `current` amps (10 V through a resistor, sized again from the
    drop found, so an LED's 2 V lands as close to `current` as a 0.6 V diode's).
    `reverse`: the zener voltage instead, the diode turned round on a 30 V supply."""
    supply, drop = (30.0, 5.0) if reverse else (10.0, 0.65)
    anode, cathode = ("0", "a") if reverse else ("a", "0")
    for _ in range(3):
        b = (
            CircuitBuilder("vf").part("V1", "vsource", "VS", "0", value=supply)
            .part("R1", "resistor", "VS", "a", value=(supply - drop) / current)
            .part("D1", model.info.type, anode, cathode, model=model.id)
        )  # fmt: skip
        drop = _op(engine, models, b)["a"]
    return drop


def diode_ir(engine: SimEngine, models: ModelLibrary, model: Model, volts: float) -> float:
    """Reverse current at `volts` across the diode, read off a 100 Ω sense resistor."""
    b = (
        CircuitBuilder("ir").part("V1", "vsource", "VS", "0", value=volts)
        .part("R1", "resistor", "VS", "k", value=100.0)
        .part("D1", model.info.type, "0", "k", model=model.id)
    )  # fmt: skip
    return (volts - _op(engine, models, b)["k"]) / 100.0


def _bjt_held(
    engine: SimEngine,
    models: ModelLibrary,
    model: Model,
    ic: float,
    vce: float | None,
    vcb: float | None,
) -> dict[str, float]:
    """The operating point with the collector held at `vce`, or at `vcb` above the base
    (old sheets: "VCB = 0"), and exactly `ic` flowing (the base resistor from 10 V is
    trimmed until it does)."""
    sign = 1.0 if model.polarity == "n" else -1.0
    if (vce is None) == (vcb is None):
        raise ValueError("give vce or vcb")
    plus, minus, volts = ("VC", "0", vce) if vcb is None else ("VC", "b", vcb)
    rb = (10.0 - 0.65) / (ic / 250.0 if vcb is None else ic)
    for _ in range(12):
        b = (
            CircuitBuilder("held")
            .part("V1", "vsource", plus, minus, value=sign * float(volts or 0.0))
            .part("V2", "vsource", "VB", "0", value=sign * 10.0)
            .part("R2", "resistor", "VB", "b", value=rb)
            .part("Q1", "bjt", "VC", "b", "0", model=model.id)
        )  # fmt: skip
        op = _op(engine, models, b)
        rb *= abs(op["Q1.ic"]) / ic
    return {"vbe": sign * op["b"], "hfe": op["Q1.ic"] / op["Q1.ib"]}


def bjt_hfe(
    engine: SimEngine,
    models: ModelLibrary,
    model: Model,
    ic: float,
    vce: float | None = None,
    vcb: float | None = None,
) -> float:
    """DC current gain Ic/Ib at exactly `ic`, the collector held at `vce` or `vcb`."""
    return _bjt_held(engine, models, model, ic, vce, vcb)["hfe"]


def bjt_vbe(
    engine: SimEngine,
    models: ModelLibrary,
    model: Model,
    ic: float,
    vce: float | None = None,
    vcb: float | None = None,
) -> float:
    """Base-emitter voltage at exactly `ic`, the collector held at `vce` or `vcb`."""
    return _bjt_held(engine, models, model, ic, vce, vcb)["vbe"]


def bjt_icbo(engine: SimEngine, models: ModelLibrary, model: Model, vcb: float) -> float:
    """Collector-base leakage with the emitter open (1 TΩ to ground) and `vcb` across."""
    sign = 1.0 if model.polarity == "n" else -1.0
    b = (
        CircuitBuilder("icbo")
        .part("V1", "vsource", "VC", "0", value=sign * vcb)
        .part("R1", "resistor", "e", "0", value=1e12)
        .part("Q1", "bjt", "VC", "0", "e", model=model.id)
    )  # fmt: skip
    return abs(_op(engine, models, b)["Q1.ic"])


def bjt_saturated(
    engine: SimEngine, models: ModelLibrary, model: Model, ic: float, ib: float
) -> tuple[float, float]:
    """(VBE, VCE) with `ib` driven into the base and `ic` drawn through the collector, each
    set by a resistor from 10 V trimmed until the current is exact: VBE(sat), VCE(sat)."""
    sign = 1.0 if model.polarity == "n" else -1.0
    rb, rc = 9.3 / ib, 9.9 / ic
    for _ in range(12):
        b = (
            CircuitBuilder("vcesat")
            .part("V1", "vsource", "V", "0", value=sign * 10.0)
            .part("R1", "resistor", "V", "c", value=rc)
            .part("R2", "resistor", "V", "b", value=rb)
            .part("Q1", "bjt", "c", "b", "0", model=model.id)
        )  # fmt: skip
        op = _op(engine, models, b)
        rb *= abs(op["Q1.ib"]) / ib
        rc *= abs(op["Q1.ic"]) / ic
    return sign * op["b"], sign * op["c"]


def bjt_tester(model_conditions: dict[str, float]) -> None:
    """The tester's figures are fixed (`solum.tester`); a record must name the same ones."""
    fixed = {"vcc": tester.VCC, "rc": tester.RC, "rb": tester.RB}
    for key, value in model_conditions.items():
        if not math.isclose(value, fixed[key], rel_tol=1e-6):
            raise ValueError(f"the tester's {key} is {fixed[key]:g}")


def _jfet_id(
    engine: SimEngine, models: ModelLibrary, model: Model, vgs: float, vds: float
) -> float:
    b = (
        CircuitBuilder("jfet")
        .part("V1", "vsource", "VD", "0", value=vds)
        .part("V2", "vsource", "VG", "0", value=vgs)
        .part("Q1", "jfet", "VD", "VG", "0", model=model.id)
    )  # fmt: skip
    return abs(_op(engine, models, b)["Q1.id"])


def _drain_id(
    engine: SimEngine, models: ModelLibrary, model: Model, vgs: float, vds: float
) -> float:
    """A JFET's or a depletion MOSFET's drain current (both are on at VGS = 0)."""
    if model.info.type == "mosfet":
        return _mosfet_id(engine, models, model, vgs, vds)
    return _jfet_id(engine, models, model, vgs, vds)


def jfet_idss(engine: SimEngine, models: ModelLibrary, model: Model, vds: float) -> float:
    """IDSS: the drain current at VGS = 0, of a JFET or a depletion MOSFET."""
    sign = 1.0 if model.polarity == "n" else -1.0
    return _drain_id(engine, models, model, 0.0, sign * vds)


def jfet_vp(engine: SimEngine, models: ModelLibrary, model: Model, vds: float, id: float) -> float:
    """Gate-source cut-off voltage (a JFET's Vp, a depletion MOSFET's VGS(off)): where
    drain current falls to `id` (bisection)."""
    sign = 1.0 if model.polarity == "n" else -1.0
    on, off = 0.0, -sign * 10.0
    for _ in range(40):
        mid = (on + off) / 2
        if _drain_id(engine, models, model, mid, sign * vds) > id:
            on = mid
        else:
            off = mid
    return (on + off) / 2


def _mosfet_id(
    engine: SimEngine, models: ModelLibrary, model: Model, vgs: float, vds: float | None
) -> float:
    """Drain current at `vgs`, the drain at `vds` (None: tied to the gate)."""
    b = CircuitBuilder("mosfet").part("V2", "vsource", "VG", "0", value=vgs)
    drain = "VG"
    if vds is not None:
        b.part("V1", "vsource", "VD", "0", value=vds)
        drain = "VD"
    b.part("Q1", "mosfet", drain, "VG", "0", model=model.id)
    return abs(_op(engine, models, b)["Q1.id"])


def _bisect(f: Callable[[float], float], lo: float, hi: float, target: float) -> float:
    """Where a rising f crosses `target` between lo and hi."""
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
    return (lo + hi) / 2


def mosfet_vgs_th(engine: SimEngine, models: ModelLibrary, model: Model, id: float) -> float:
    """Gate threshold as sheets test it: drain tied to gate (VDS = VGS), at `id` amps."""
    return _bisect(lambda v: _mosfet_id(engine, models, model, v, None), 0.0, 10.0, id)


def mosfet_vds_on(
    engine: SimEngine, models: ModelLibrary, model: Model, vgs: float, id: float
) -> float:
    """Drain-source on-voltage at `vgs`, where the drain current reaches `id` amps."""
    return _bisect(lambda v: _mosfet_id(engine, models, model, vgs, v), 0.0, 20.0, id)


def opamp_open_loop(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, comp: float = 0.0
) -> tuple[float, float]:
    """(DC open-loop gain in dB, unity-gain frequency in Hz) on ±`supply`.

    DC feedback through 10 MΩ keeps the output centred; 1 F decouples it for AC.
    """
    b = (
        CircuitBuilder("aol")
        .part("V1", "vsource", "VP", "0", value=supply)
        .part("V2", "vsource", "VN", "0", value=-supply)
        .part("IN", "guitar", "p")
        .part("U1", "opamp", "p", "n", "out", model=model.id, supply=("VP", "VN"),
              pins={"comp1": "cmp1", "comp2": "cmp2"})
        .part("R1", "resistor", "out", "n", value=10e6)
        .part("C1", "capacitor", "n", "0", value=1.0)
        .part("R2", "resistor", "out", "0", value=10e3)
    )  # fmt: skip
    if comp:
        b.part("C2", "capacitor", "cmp1", "cmp2", value=comp)
    netlist = generate_netlist(b.build(), models, Ac(start=0.1, stop=100e6, per_decade=50))
    plot = engine.run(netlist.text).plot("ac")
    freq = plot.vectors["frequency"].real
    gain = np.abs(plot.vectors[netlist.node("out")])
    above = np.nonzero(gain < 1.0)[0][0]
    f_unity = math.exp(np.interp(0.0, -np.log(gain[above - 1 : above + 1]),
                                 np.log(freq[above - 1 : above + 1])))  # fmt: skip
    return 20 * math.log10(gain[0]), f_unity


def opamp_swing(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, load: float
) -> tuple[float, float]:
    """How close the output gets to each rail (V below the positive, V above the negative)
    on ±`supply`, driven hard each way open loop into `load` to ground: the datasheet's
    maximum peak output swing, as headroom."""
    out: list[float] = []
    for drive in (1.0, -1.0):
        b = (
            CircuitBuilder("swing")
            .part("V1", "vsource", "VP", "0", value=supply)
            .part("V2", "vsource", "VN", "0", value=-supply)
            .part("V3", "vsource", "p", "0", value=drive)
            .part("U1", "opamp", "p", "0", "out", model=model.id, supply=("VP", "VN"),
                  pins={"comp1": "cmp1", "comp2": "cmp2"})
            .part("R1", "resistor", "out", "0", value=load)
        )  # fmt: skip
        out.append(_op(engine, models, b)["out"])
    return supply - out[0], out[1] + supply


def opamp_buffer(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, vin: float
) -> float:
    """The output (V) of the op-amp wired as a unity buffer (output to -) on ±`supply`, with
    `vin` on +: it follows the input when the model's pins are in the right order."""
    b = (
        CircuitBuilder("buffer")
        .part("V1", "vsource", "VP", "0", value=supply)
        .part("V2", "vsource", "VN", "0", value=-supply)
        .part("V3", "vsource", "p", "0", value=vin)
        .part("U1", "opamp", "p", "out", "out", model=model.id, supply=("VP", "VN"),
              pins={"comp1": "cmp1", "comp2": "cmp2"})
        .part("R1", "resistor", "out", "0", value=10e3)
    )  # fmt: skip
    return _op(engine, models, b)["out"]


def _ota_out(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, iabc: float, vd: float
) -> float:
    """An OTA's output current (A) into 100 Ω to ground on ±`supply`, with `vd` volts across
    its inputs and its bias current set to `iabc` by a resistor from the positive supply
    (resized until the current through it is `iabc`). An LM13700's half b is left unused."""
    pin = -supply + 0.7  # where the bias pin sits, first guess
    for _ in range(4):
        rabc = (supply - pin) / iabc
        b = (
            CircuitBuilder("ota")
            .part("V1", "vsource", "VP", "0", value=supply)
            .part("V2", "vsource", "VN", "0", value=-supply)
            .part("V3", "vsource", "p", "0", value=vd)
            .part("R1", "resistor", "VP", "ib", value=rabc)
            .part("R2", "resistor", "out", "0", value=100.0)
        )  # fmt: skip
        if model.halves == 2:
            b.part(
                "U1A", "ota", "p", "0", "out", "ib", model=model.id, half="a", supply=("VP", "VN")
            )
            b.part("U1B", "ota", model=model.id, half="b")
        else:
            b.part("U1", "ota", "p", "0", "out", "ib", model=model.id, supply=("VP", "VN"))
        op = _op(engine, models, b)
        pin = op["ib"]
    return op["out"] / 100.0


def ota_gm(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, iabc: float
) -> float:
    """Transconductance (S) at bias current `iabc`: the change in output current from 1 mV
    below to 1 mV above zero across the inputs, per volt (a card's input offset cancels)."""
    up = _ota_out(engine, models, model, supply, iabc, 1e-3)
    return (up - _ota_out(engine, models, model, supply, iabc, -1e-3)) / 2e-3


def ota_iout_max(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, iabc: float
) -> float:
    """Peak output current (A) at bias current `iabc`: the inputs 1 V apart."""
    return _ota_out(engine, models, model, supply, iabc, 1.0)


def _inverter(model: Model, supply: float, inp: str, out: str) -> CircuitBuilder:
    """One CMOS inverter of a hex chip (unit a, the rest unused) on `supply` volts."""
    b = CircuitBuilder("inverter").part("V1", "vsource", "VP", "0", value=supply)
    b.part("U1A", "inverter", inp, out, model=model.id, half="a", supply=("VP", "0"))
    for x in "bcdef":
        b.part(f"U1{x.upper()}", "inverter", model=model.id, half=x)
    return b


def inverter_switch(engine: SimEngine, models: ModelLibrary, model: Model, supply: float) -> float:
    """The switching point (V): input tied to output, where VO = VI."""
    return _op(engine, models, _inverter(model, supply, "x", "x"))["x"]


def inverter_drive(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, vout: float, sink: bool
) -> float:
    """The output current (A, a magnitude) with the output held at `vout`: sinking with the
    input at the supply (IOL), else sourcing with it at 0 V (IOH). The output is pulled
    through 1 Ω from a source moved until the output sits at `vout`."""

    def at(volts: float) -> float:
        b = _inverter(model, supply, "VP" if sink else "0", "o")
        b.part("V2", "vsource", "pull", "0", value=volts).part(
            "R1", "resistor", "pull", "o", value=1.0
        )
        return _op(engine, models, b)["o"]

    span = 0.5 if sink else -0.5  # the pull's reach past the output, beyond any drive
    pull = _bisect(at, min(vout, vout + span), max(vout, vout + span), vout)
    return abs(pull - vout) / 1.0


def pump_vout(
    engine: SimEngine,
    models: ModelLibrary,
    model: Model,
    supply: float,
    load: float,
    mode: str = "inverter",
) -> float:
    """A charge pump's output (V) from `supply` with `load` amps drawn by a resistor, its
    parts drawn with the sheet's cap (D-226)."""
    vout = 2 * supply if mode == "doubler" else -supply
    cap = format_value(model.info.params["c_pump"])
    for _ in range(8):
        b = (
            CircuitBuilder("pump").part("V1", "vsource", "VS", "0", value=supply)
            .part("R2", "resistor", "o", "0", value=abs(vout) / load)
            .pump("U1", "VS", **{"double" if mode == "doubler" else "invert": "o"},
                  model=model.id, cap=cap)
        )  # fmt: skip
        vout = _op(engine, models, b)["o"]
    return vout


def regulator_vout(
    engine: SimEngine, models: ModelLibrary, model: Model, supply: float, load: float
) -> float:
    """A regulator's output (V) from `supply` with `load` amps drawn by a resistor sized for
    its nominal output."""
    b = (
        CircuitBuilder("regulator").part("V1", "vsource", "VS", "0", value=supply)
        .part("U1", "regulator", "VS", "o", "0", model=model.id)
        .part("R2", "resistor", "o", "0", value=model.info.params["v_out"] / load)
    )  # fmt: skip
    return _op(engine, models, b)["o"]


def measure(engine: SimEngine, models: ModelLibrary, model: Model, quantity: str,
            conditions: dict[str, float]) -> float:  # fmt: skip
    """One validation quantity under the given conditions (see `Validation`)."""
    c = conditions
    match quantity:
        case "vf":
            return diode_vf(engine, models, model, c["if"])
        case "vz":
            return diode_vf(engine, models, model, c["iz"], reverse=True)
        case "ir":
            return diode_ir(engine, models, model, c["vr"])
        case "hfe":
            return bjt_hfe(engine, models, model, c["ic"], c.get("vce"), c.get("vcb"))
        case "vbe":
            return bjt_vbe(engine, models, model, c["ic"], c.get("vce"), c.get("vcb"))
        case "vce_sat":
            return bjt_saturated(engine, models, model, c["ic"], c["ib"])[1]
        case "vbe_sat":
            return bjt_saturated(engine, models, model, c["ic"], c["ib"])[0]
        case "icbo":
            return bjt_icbo(engine, models, model, c["vcb"])
        case "iceo":
            bjt_tester(c)
            return tester.read_tester(engine, models, model).leakage
        case "tester_hfe":
            bjt_tester(c)
            return tester.read_tester(engine, models, model).gain
        case "idss":
            return jfet_idss(engine, models, model, c["vds"])
        case "vp":
            return jfet_vp(engine, models, model, c["vds"], c["id"])
        case "vgs_th":
            return mosfet_vgs_th(engine, models, model, c["id"])
        case "vds_on":
            return mosfet_vds_on(engine, models, model, c["vgs"], c["id"])
        case "aol_db":
            return opamp_open_loop(engine, models, model, c["supply"], c.get("comp", 0.0))[0]
        case "gbw":
            return opamp_open_loop(engine, models, model, c["supply"], c.get("comp", 0.0))[1]
        case "swing_pos":
            return opamp_swing(engine, models, model, c["supply"], c["load"])[0]
        case "swing_neg":
            return opamp_swing(engine, models, model, c["supply"], c["load"])[1]
        case "buffer_out":
            return opamp_buffer(engine, models, model, c["supply"], c["vin"])
        case "v_switch":
            return inverter_switch(engine, models, model, c["supply"])
        case "iol":
            return inverter_drive(engine, models, model, c["supply"], c["vout"], sink=True)
        case "ioh":
            return inverter_drive(engine, models, model, c["supply"], c["vout"], sink=False)
        case "gm":
            return ota_gm(engine, models, model, c["supply"], c["iabc"])
        case "iout_max":
            return ota_iout_max(engine, models, model, c["supply"], c["iabc"])
        case "vout" if model.info.type == "regulator":
            return regulator_vout(engine, models, model, c["supply"], c["load"])
        case "vout":
            mode = "doubler" if c.get("doubler") else "inverter"
            return pump_vout(engine, models, model, c["supply"], c["load"], mode)
    raise ValueError(f"unknown quantity {quantity}")
