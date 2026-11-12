"""Is any active stage saturated at DC? If so, an AC (small-signal) plot is meaningless.

The thresholds are deliberately coarse (D-041): they catch a stage that's railed, cut
off or bottomed out, not one that's merely biased off-centre. Phase 5's operating-point
rules give the finer, explained warnings.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from solum.circuit.chips import left_out, spare_ota, supply_nets
from solum.circuit.connectivity import Nets
from solum.circuit.schema import Bjt, Circuit, Jfet, Mosfet, Opamp, Ota
from solum.models import Model, ModelLibrary

# Volts: below this, with the collector past the base (Vce < Vbe), a transistor is
# saturated. Silicon's Vbe is always above it; germanium at low current runs at 0.15-0.2 V
# and amplifies at Vce 0.25 V (the Tone Bender MkII's Q2, D-133).
BJT_VCE_SAT = 0.3
BJT_VCE_FLOOR = 0.1  # volts: below this, bottomed out whatever the base does (D-133)
# Volts: a MOSFET's drain needs at least this over its source to stay out of its ohmic
# region, however little the gate is past VTO: a fitted card conducts below VTO (the
# 2N7000's 1 mA at 2.1 V against VTO 2.4 V, D-175), where the square law's VGS - VTO says 0.
MOSFET_VDS_SAT = 0.2
CUTOFF_CURRENT = 1e-7  # amps: below this a transistor is effectively off
# Volts: an output this close to a supply rail is stuck there. Classic op-amps (TL072,
# 4558) can't swing closer than ~1.5 V, so a railed output sits just inside this.
OPAMP_RAIL_MARGIN = 2.0
# Volts: how close a classic op-amp's output gets to a rail before it clips, as a rule of
# thumb where the model records no output swing (D-106; Phase 9's model pass adds them).
OPAMP_SWING_MARGIN = 1.5


def opamp_input_limits(model: Model, high: float, low: float) -> tuple[float, float] | None:
    """The input voltages the model's datasheet allows on these supplies (its common-mode
    range: `cm_neg_headroom` above the negative supply, `cm_pos_headroom` below the
    positive), or None when the model records neither."""
    ratings = model.info.ratings
    if "cm_neg_headroom" not in ratings and "cm_pos_headroom" not in ratings:
        return None
    return low + ratings.get("cm_neg_headroom", 0.0), high - ratings.get("cm_pos_headroom", 0.0)


def opamp_output_limits(model: Model, high: float, low: float) -> tuple[float, float, bool]:
    """How far the output can swing on these supplies: (lowest, highest, from the
    datasheet). The model's `out_neg_headroom` / `out_pos_headroom` ratings when it
    records them (cited like the input ones, D-077), else `OPAMP_SWING_MARGIN` each side."""
    ratings = model.info.ratings
    datasheet = "out_neg_headroom" in ratings or "out_pos_headroom" in ratings
    return (
        low + ratings.get("out_neg_headroom", OPAMP_SWING_MARGIN),
        high - ratings.get("out_pos_headroom", OPAMP_SWING_MARGIN),
        datasheet,
    )


@dataclass(frozen=True)
class Saturation:
    ref: str
    state: str  # "saturated", "cut off", "triode", "railed"
    message: str


def mosfet_vds_sat(vgs: float, vto: float) -> float:
    """The drain-source voltage below which an N-channel MOSFET leaves saturation (the
    amplifying region): its gate's overdrive VGS - VTO, at least `MOSFET_VDS_SAT`."""
    return max(vgs - vto, MOSFET_VDS_SAT)


def saturation(
    circuit: Circuit,
    nets: Nets,
    voltages: Mapping[str, float],
    currents: Mapping[str, float],
    models: ModelLibrary,
) -> list[Saturation]:
    """Active parts whose DC operating point leaves no room for a small signal."""
    found: list[Saturation] = []

    def v(ref: str, pin: str) -> float:
        return voltages[nets.net_of(ref, pin)]

    def flag(ref: str, state: str, message: str) -> None:
        if state == "cut off" and getattr(circuit.part(ref), "off_by_design", False):
            return  # off at rest on purpose: a rectifier or a switch (D-238)
        found.append(Saturation(ref, state, message))

    skipped = left_out(circuit, nets)
    for part in circuit.parts:
        if part.ref in skipped:
            continue
        if isinstance(part, Bjt):
            model = models.get(part.model)
            ic = currents.get(f"{part.ref}.ic")
            if model.polarity is None or ic is None:
                continue  # subcircuit models: no terminal currents to judge by
            sign = 1.0 if model.polarity == "n" else -1.0
            vce = sign * (v(part.ref, "C") - v(part.ref, "E"))
            vbe = sign * (v(part.ref, "B") - v(part.ref, "E"))
            if abs(ic) < CUTOFF_CURRENT:
                flag(
                    part.ref,
                    "cut off",
                    f"{part.ref} is switched off: no collector current flows, so it doesn't "
                    "amplify.",
                )
            elif vce < BJT_VCE_FLOOR or (vce < BJT_VCE_SAT and vce < vbe):
                flag(
                    part.ref,
                    "saturated",
                    f"{part.ref} is fully on (saturated, Vce = {vce:.2f} V), so it can't amplify.",
                )
        elif isinstance(part, Jfet):
            model = models.get(part.model)
            drain = currents.get(f"{part.ref}.id")
            vto = part.measured.vp if part.measured else model.param("vto")
            if model.polarity is None or drain is None or vto is None:
                continue
            sign = 1.0 if model.polarity == "n" else -1.0
            vds = sign * (v(part.ref, "D") - v(part.ref, "S"))
            vgs = sign * (v(part.ref, "G") - v(part.ref, "S"))
            if abs(drain) < CUTOFF_CURRENT:
                flag(
                    part.ref,
                    "cut off",
                    f"{part.ref} is switched off (pinched off): no drain current flows, so it "
                    "doesn't amplify.",
                )
            elif vds < vgs - sign * vto:
                flag(
                    part.ref,
                    "triode",
                    f"{part.ref} is in its ohmic region (Vds = {vds:.2f} V): it acts as a "
                    "resistor, not an amplifier.",
                )
        elif isinstance(part, Mosfet):
            vto = models.get(part.model).param("vto") or 0.0
            drain = currents.get(f"{part.ref}.id")
            if drain is None:
                continue
            vds = v(part.ref, "D") - v(part.ref, "S")
            vgs = v(part.ref, "G") - v(part.ref, "S")
            if abs(drain) < CUTOFF_CURRENT:
                flag(
                    part.ref,
                    "cut off",
                    f"{part.ref} is switched off: its gate is below its threshold, so no drain "
                    "current flows and it doesn't amplify.",
                )
            elif vds < mosfet_vds_sat(vgs, vto):
                flag(
                    part.ref,
                    "triode",
                    f"{part.ref} is fully on (ohmic, Vds = {vds:.2f} V): it acts as a "
                    "resistor, not an amplifier.",
                )
        elif isinstance(part, Opamp | Ota) and not spare_ota(circuit, nets, part):
            out = v(part.ref, "out")
            pos, neg = supply_nets(circuit, nets, part)
            high, low = voltages[pos], voltages[neg]
            if min(high - out, out - low) < OPAMP_RAIL_MARGIN:
                flag(
                    part.ref,
                    "railed",
                    f"{part.ref}'s output is stuck near a supply rail ({out:.2f} V), so it "
                    "can't swing.",
                )
    return found
