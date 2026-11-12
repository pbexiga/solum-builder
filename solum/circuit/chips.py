"""Chips (D-140, D-176): a chip's units, its power pins, and unused units.

A chip's units are op-amps, a 4049's inverters or an LM13700's OTAs (D-180). A single
(TL071, CA3080) is one part with its own V+ and V- pins. A chip of several is one part per
unit, IC1A, IC1B… sharing one model (each unit is called a half, as the file's `half`):
a dual op-amp's two, a quad's four (D-172), a 4049's six, an LM13700's two. Its V+ and V-
pins are on its power unit (IC1C, IC1E, IC1G: D-179), and every unit runs from that unit's
nets. A unit whose signal pins join nothing is unused: it isn't simulated, and the rules
say how to wire it.
"""

from solum.circuit.connectivity import Nets, loose_parts
from solum.circuit.parts import POWER_PINS, pin_offsets
from solum.circuit.schema import CHIP_UNITS, ChipUnit, Circuit, Opamp, Ota, PowerUnit

SIGNAL_PINS = ("+", "-", "out")  # an op-amp's


def signal_pins(part: ChipUnit) -> tuple[str, ...]:
    """A unit's pins other than power (an op-amp's +, - and out): what decides whether
    it's used."""
    if isinstance(part, Opamp):
        return SIGNAL_PINS
    return tuple(p for p in pin_offsets(part) if p not in POWER_PINS)


def halves(circuit: Circuit, part: ChipUnit) -> list[ChipUnit]:
    """Every unit of `part`'s chip, a first (itself alone for a single)."""
    if part.half is None:
        return [part]
    found = [
        p for p in circuit.parts if isinstance(p, CHIP_UNITS) and p.half and p.chip == part.chip
    ]
    return sorted(found, key=lambda p: p.half or "")


def power_part(circuit: Circuit, part: ChipUnit) -> ChipUnit | PowerUnit:
    """The part that carries the chip's V+ and V- pins: its power unit, or a single itself."""
    if part.half is None:
        return part
    return next(p for p in circuit.parts if isinstance(p, PowerUnit) and p.chip == part.chip)


def supply_nets(circuit: Circuit, nets: Nets, part: ChipUnit) -> tuple[str, str]:
    """The nets on the chip's V+ and V- pins."""
    power = power_part(circuit, part)
    return nets.net_of(power.ref, "V+"), nets.net_of(power.ref, "V-")


def spare_ota(circuit: Circuit, nets: Nets, part: ChipUnit) -> bool:
    """An OTA with its output and bias current pin both joined to nothing: off, as the
    datasheets and Aion leave a spare unit (D-236)."""
    if not isinstance(part, Ota):
        return False
    labelled = {lb.net for lb in circuit.labels}
    return all(
        (net := nets.net_of(part.ref, pin)) not in labelled and len(nets.members[net]) == 1
        for pin in ("out", "iabc")
    )


def unused(circuit: Circuit, nets: Nets, part: ChipUnit) -> bool:
    """A chip's unit with none of its signal pins joined to anything (no other pin, no
    label)."""
    if part.half is None:
        return False
    labelled = {lb.net for lb in circuit.labels}
    for pin in signal_pins(part):
        net = nets.net_of(part.ref, pin)
        if net in labelled or len(nets.members[net]) > 1:
            return False
    return True


def unused_halves(circuit: Circuit, nets: Nets) -> set[str]:
    """Refs of the units left unused: not simulated (D-140)."""
    return {p.ref for p in circuit.parts if isinstance(p, CHIP_UNITS) and unused(circuit, nets, p)}


def left_out(circuit: Circuit, nets: Nets) -> set[str]:
    """Refs the simulation leaves out: a chip's unused units (D-140) and the parts no
    current can reach (`loose_parts`, D-165)."""
    return unused_halves(circuit, nets) | loose_parts(circuit, nets)
