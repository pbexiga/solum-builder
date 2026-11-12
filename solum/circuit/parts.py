"""Pin names and positions for each part type: the one place symbol geometry is defined.

Offsets are in schematic units (the grid is 10) relative to the part's `pos`, before
rotation. Rotation is clockwise on screen (y grows downwards). Phase 2 draws symbols
from the same table.
"""

from functools import cache

from solum.circuit.schema import Guitar, Jack, Opamp, Ota, Part, Point, Switch
from solum.circuit.switches import lug_name, pole_contacts

COMP_PINS = ("comp1", "comp2")  # op-amp compensation pins; most models have none
POWER_PINS = ("V+", "V-")  # a chip's supply pins: on a single, or a dual's power unit (D-179)
EXTRA_PINS = ("null1", "null2", "nc")  # a single's pins no model simulates, drawn on request
# What each op-amp pin is, for the form and the Problems (D-140)
OPAMP_PIN_ROLES = {
    "+": "non-inverting input", "-": "inverting input", "out": "output",
    "V+": "positive supply", "V-": "negative supply", "comp1": "compensation",
    "comp2": "compensation", "null1": "offset null", "null2": "offset null",
    "nc": "no internal connection",
}  # fmt: skip

TWO_PIN: dict[str, Point] = {"1": (-20, 0), "2": (20, 0)}

PIN_OFFSETS: dict[str, dict[str, Point]] = {
    "resistor": TWO_PIN,
    "capacitor": TWO_PIN,
    "inductor": TWO_PIN,
    "pot": {"1": (-20, 0), "2": (0, -20), "3": (20, 0)},
    "trimmer": {"1": (-20, 0), "2": (0, -20), "3": (20, 0)},
    "diode": {"A": (-20, 0), "K": (20, 0)},
    "led": {"A": (-20, 0), "K": (20, 0)},
    "jfet": {"D": (20, -20), "G": (-20, 0), "S": (20, 20)},
    "bjt": {"C": (20, -20), "B": (-20, 0), "E": (20, 20)},
    "mosfet": {"D": (20, -20), "G": (-20, 0), "S": (20, 20)},
    "opamp": {
        "+": (-40, 20),
        "-": (-40, -20),
        "out": (40, 0),
        "comp1": (-20, -40),
        "comp2": (20, -40),
        "V+": (0, -40),
        "V-": (0, 40),
        "null1": (-20, 40),
        "null2": (20, 40),
        "nc": (30, -40),
    },
    # one of a 4049's six inverters (D-180): in on the left, out on the right
    "inverter": {"in": (-30, 0), "out": (30, 0)},
    # an OTA (D-180), drawn as an op-amp with its bias current in under the right of the
    # triangle; a single's V+ and V- as an op-amp single's; a dual's half has its
    # linearising diodes' bias under the left and its buffer beside it, lower right
    "ota": {
        "+": (-40, 20),
        "-": (-40, -20),
        "out": (40, 0),
        "iabc": (20, 40),
        "V+": (0, -40),
        "V-": (0, 40),
        "dbias": (-20, 40),
        "bufin": (60, 40),
        "bufout": (100, 40),
    },
    # a chip's power unit (D-179): V+ above, V- below, as the op-amp's were
    "powerunit": {"V+": (0, -40), "V-": (0, 40)},
    "vsource": {"+": (0, -20), "-": (0, 20)},
    # the 8-pin box as the datasheets draw it (D-226): 1-4 down the left, 8-5 up the right;
    # pins 1, 6 and 7 (boost or FB, LV or VREF, OSC) may be wired or left open: pin 1 on
    # the chip's V+ is boost on a chip that has it (`pump.pump_wiring`)
    "chargepump": {
        "in": (40, -30),
        "out": (40, 30),
        "gnd": (-40, 10),
        "cap+": (-40, -10),
        "cap-": (-40, 30),
        "1": (-40, -30),
        "7": (40, -10),
        "6": (40, 10),
    },
    # a fixed regulator as KiCad's Regulator_Linear draws it (D-227): in left, out right,
    # ground below
    "regulator": {"in": (-40, 0), "out": (40, 0), "gnd": (0, 40)},
    "guitar": {"out": (20, 0)},
    "battery": {"+": (0, -20), "-": (0, 20)},
    # the DC jack (D-143): sleeve (+) and centre (-) to the right, the battery lug under
    # drawn as KiCad's Barrel_Jack_Switch: centre (-), battery lug, sleeve (+) (D-143)
    "dcjack": {"+": (60, 20), "-": (60, -20), "sw": (60, 0)},  # pin order kept: +, -, sw
    "amp": {"in": (-20, 0)},
    # input and output jacks as KiCad's AudioJack2 (S over T) and AudioJack3 (S, R, T) draw
    # them, 2.54 mm to 20 (D-174); the mono's, the stereo's in `jack_pins`
    "jack": {"T": (40, 0), "S": (40, -20)},
}
STEREO_JACK: dict[str, Point] = {"T": (40, 20), "R": (40, 0), "S": (40, -20)}


def throw_offsets(throws: int) -> list[int]:
    """Where a pole's throws sit, top to bottom, as KiCad draws switches (v15, D-143):
    one level with the common (SPST); two a step above and below it, the middle left for
    a centre-off; three or more 20 apart, centred on it."""
    if throws == 1:
        return [0]
    if throws == 2:
        return [-20, 20]
    return [20 * i - 10 * (throws - 1) for i in range(throws)]


def switch_pins(switch: Switch) -> dict[str, Point]:
    """One pole's lugs (D-143): the common at (-20, 0), the others down the right at
    `throw_offsets`, in the type's order (a toggle's 1 above, 3 below)."""
    kind = switch.switch_kind
    pins = {lug_name(kind, switch.pole, kind.common): (-20, 0)}
    for lug, y in zip(kind.throws, throw_offsets(len(kind.throws)), strict=True):
        pins[lug_name(kind, switch.pole, lug)] = (20, y)
    return pins


def closed_contacts(switch: Switch) -> list[tuple[str, str]]:
    """The (common, lug) pin pairs of this pole that connect at the switch's position."""
    return [(c, t) for c, t, closed in pole_contacts(switch.switch_kind, switch.pole,
                                                     switch.position) if closed]  # fmt: skip


def switch_contacts(switch: Switch) -> list[tuple[str, str]]:
    """Every (common, lug) pin pair of this pole, open or closed."""
    return [(c, t) for c, t, _ in pole_contacts(switch.switch_kind, switch.pole, 0)]


def opamp_pins(part: Opamp) -> dict[str, Point]:
    """An op-amp's pins (D-140): a chip's halves have no power pins (its power unit has
    them, D-179), and a single's offset and no-connect pins exist only while `show_pins`."""
    pins = dict(PIN_OFFSETS["opamp"])
    if part.half is not None:
        for name in POWER_PINS:
            del pins[name]
    if part.half is not None or not part.show_pins:
        for name in EXTRA_PINS:
            del pins[name]
    return pins


OTA_DUAL_PINS = ("dbias", "bufin", "bufout")  # an LM13700 half's own (D-180)


def ota_pins(part: Ota) -> dict[str, Point]:
    """An OTA's pins (D-180): a single's power pins, or a dual's half's diode bias and
    buffer (its power is on the chip's power unit)."""
    drop = OTA_DUAL_PINS if part.half is None else POWER_PINS
    return {k: v for k, v in PIN_OFFSETS["ota"].items() if k not in drop}


RING_PIN: Point = (0, 20)  # a stereo input jack's ring lug, under the guitar (D-143)


VARYING = frozenset({"switch", "opamp", "ota", "guitar", "jack"})  # pins depend on the part


def pin_offsets(part: Part) -> dict[str, Point]:
    """Pin name → offset before rotation."""
    if part.type not in VARYING:
        return PIN_OFFSETS[part.type]
    if isinstance(part, Switch):
        return switch_pins(part)
    if isinstance(part, Opamp):
        return opamp_pins(part)
    if isinstance(part, Ota):
        return ota_pins(part)
    if isinstance(part, Guitar) and part.stereo:
        return {**PIN_OFFSETS["guitar"], "ring": RING_PIN}
    if isinstance(part, Jack) and part.stereo:
        return STEREO_JACK
    return PIN_OFFSETS[part.type]


def rotate(offset: Point, rot: int) -> Point:
    x, y = offset
    for _ in range(rot // 90):
        x, y = -y, x
    return (x, y)


@cache
def _turned(kind: str, rot: int) -> tuple[tuple[str, int, int], ...]:
    """A fixed-pin type's offsets at `rot`: worked out once (every `connect` asks for
    every part's pins; Phase 10)."""
    return tuple((name, *rotate(offset, rot)) for name, offset in PIN_OFFSETS[kind].items())


def pin_positions(part: Part) -> dict[str, Point]:
    """Pin name → absolute schematic position."""
    px, py = part.pos
    if part.type not in VARYING:
        return {name: (px + dx, py + dy) for name, dx, dy in _turned(part.type, part.rot)}
    return {
        name: (px + dx, py + dy)
        for name, (dx, dy) in ((n, rotate(o, part.rot)) for n, o in pin_offsets(part).items())
    }
