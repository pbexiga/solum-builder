"""Circuit file schema, as Pydantic models: the single source of truth (D-032).

`docs/circuit.schema.json` is generated from these models (`make schema`) for documentation
and editors; a unit test fails if the committed file is out of date.

Part values are kept as written (`"4k7"`) so files round-trip unchanged; use
`solum.units.parse_value` to get SI floats.
"""

import json
import re
from collections.abc import Callable
from typing import Annotated, Any, Final, Literal, Self, TypeGuard

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)

from solum.circuit.enclosures import CUSTOM as ENCLOSURE_CUSTOM
from solum.circuit.enclosures import SIZES as ENCLOSURE_SIZES
from solum.circuit.enclosures import size_of
from solum.circuit.refs import ref_problem
from solum.circuit.switches import (
    CUSTOM,
    DEFAULT_KIND,
    MAX_POLES,
    MAX_POSITIONS,
    MAX_THROWS,
    POLE_LETTERS,
    Look,
    SwitchKind,
    custom_kind,
    kind_of,
)
from solum.units import format_quantity, format_value, parse_value

SCHEMA_VERSION: Final = 30

Point = tuple[int, int]
Rotation = Literal[0, 90, 180, 270]
Taper = Literal["A", "B", "C", "W"]

# Refs have no "_" so generated SPICE names (`R_VR1_a`) can never collide with a ref.
REF_PATTERN = r"^[A-Za-z][A-Za-z0-9]*$"
# Net names have no "." so they can't be mistaken for a pin reference (`Q1.D`).
NET_PATTERN = r"^[^.\s]+$"
NetName = Annotated[str, Field(pattern=NET_PATTERN)]
ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


def id_from_name(name: str, fallback: str = "circuit") -> str:
    """A circuit id (file name) from its display name: `TS808 (mine)` → `ts808-mine`."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or fallback


def _any_value(value: str | float) -> str | float:
    parse_value(value)
    return value


def _positive_value(value: str | float) -> str | float:
    if parse_value(value) <= 0:
        raise ValueError(f"{value!r} must be greater than zero.")
    return value


def _in_range(
    unit: str, low: float, high: float, example: str
) -> Callable[[str | float], str | float]:
    """A part value in `unit`, between `low` and `high`: far wider than any pedal uses,
    so what it catches is a slip, like 10f (femto) or 10F (farads) for 10µ (D-164).
    Text is kept in its standard form (`100uf` → `100µ`, `4.7k` → `4k7`), as the
    drawing and the form show it (the user, D-164)."""

    def check(value: str | float) -> str | float:
        number = parse_value(value, unit)
        if number <= 0:
            raise ValueError(f"{value!r} must be greater than zero.")
        if not low <= number <= high:
            raise ValueError(
                f"{value!r} is {format_quantity(number, unit)}, outside "
                f"{format_quantity(low, unit)} to {format_quantity(high, unit)}. "
                f"Did you mean something like {example}?"
            )
        return format_value(number, 6) if isinstance(value, str) else value

    return check


AnyValue = Annotated[str | float, AfterValidator(_any_value)]
# wide enough for the app's own test circuits (an open 1e12 ohms, a 1 F AC short)
Ohms = Annotated[str | float, AfterValidator(_in_range("Ω", 1e-3, 1e12, "4k7 or 1M"))]
Farads = Annotated[str | float, AfterValidator(_in_range("F", 1e-13, 1.0, "22n, 100p or 10µ"))]
Henries = Annotated[str | float, AfterValidator(_in_range("H", 1e-9, 100.0, "500m or 10m"))]
PositiveValue = Annotated[str | float, AfterValidator(_positive_value)]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
POSITION_NAME_MAX = 24  # characters in a switch position's name: a word or two (D-143)
NOTE_MAX = 5000  # characters in one note: a block's description fits, a document doesn't
NoteText = Annotated[str, Field(min_length=1, max_length=NOTE_MAX)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Part(_Model):
    ref: str = Field(pattern=REF_PATTERN)
    pos: Point = (0, 0)
    rot: Rotation = 0
    note: str = Field("", max_length=NOTE_MAX)  # the part's note, carried with it (v30)

    @model_validator(mode="after")
    def _ref_fits(self, info: ValidationInfo) -> Self:
        """Each type's refs (v13, D-141): R1, VR1, IC1A… (`refs.py`). A migration reading
        an older file's parts passes `{"old_refs": True}`: v13 fixes them."""
        if info.context and info.context.get("old_refs"):
            return self
        kind = getattr(self, "type")  # noqa: B009 (each part type declares its own)
        letter = next((x for k in ("half", "pole", "gang") if (x := getattr(self, k, None))), None)
        problem = ref_problem(kind, self.ref, letter)
        if problem:
            raise ValueError(f"{self.ref}: {problem}")
        return self


class Resistor(_Part):
    type: Literal["resistor"]
    value: Ohms
    rating_w: float | None = None


POLARISED = ("electrolytic", "tantalum")  # capacitor kinds with a + pin (pin 1)


class Capacitor(_Part):
    """For polarised kinds, pin 1 is +."""

    type: Literal["capacitor"]
    value: Farads
    kind: Literal["film", "ceramic", "c0g", "electrolytic", "tantalum"] | None = None
    rating_v: float | None = None


class Inductor(_Part):
    """A coil (v18, D-173): its inductance `value` (H) in series with its wire's
    `resistance` (Ω, 0 for an ideal one). `kind`: the inductor guide's entry it was filled
    from (`library/guides/inductors.yaml`: measured wah inductors), or None. Pins 1, 2."""

    type: Literal["inductor"]
    value: Henries
    resistance: float = Field(default=0.0, ge=0.0, le=1e4)
    kind: str | None = None


class Pot(_Part):
    """Pins 1 (counter-clockwise end), 2 (wiper), 3 (clockwise end). Rotation 0-1. A dual
    pot (v24, D-217) is a part per gang (`gang` a, b: VR1A, VR1B), each placed on its own,
    of one value, taper, rotation and label: one knob turns both."""

    type: Literal["pot"]
    value: Ohms
    taper: Taper = "B"
    rotation: Fraction = 0.5
    label: str | None = None
    gang: Literal["a", "b"] | None = None

    @property
    def knob(self) -> str:
        """The pot's name: VR1 for VR1A and VR1B, the ref itself for a single pot."""
        return self.ref[:-1] if self.gang else self.ref


class BiasTarget(_Model):
    """Solve the trimmer so that `node` (a net or `REF.PIN`) sits at `volts`."""

    node: str
    volts: float


class Trimmer(_Part):
    """Same pins as a pot. With `bias_target`, rotation is solved before every run."""

    type: Literal["trimmer"]
    value: Ohms
    taper: Taper = "B"
    rotation: Fraction = 0.5
    bias_target: BiasTarget | None = None
    label: str | None = None  # its name (BIAS), v13


Pole = Literal["a", "b", "c", "d"]


class CustomPosition(_Model):
    """One position of a custom switch (9c): its name and, per pole, the throw (1…n) its
    common joins, or None (open)."""

    name: Annotated[str, Field(min_length=1, max_length=POSITION_NAME_MAX)]
    joins: list[int | None] = Field(min_length=1, max_length=MAX_POLES)


class CustomSwitch(_Model):
    """A switch whose contacts its part defines (v22, 9c: the user's "a custom (with
    limits)"): up to 4 poles, 12 throws a pole and 12 positions; each position joins each
    pole's common to one throw or none. `look`: drawn as a toggle (a column) or a rotary
    (an arc, 3 throws or more). Every pole carries the same one."""

    name: Annotated[str, Field(min_length=1, max_length=POSITION_NAME_MAX)]
    throws: int = Field(ge=1, le=MAX_THROWS)
    look: Look = "toggle"
    positions: list[CustomPosition] = Field(min_length=2, max_length=MAX_POSITIONS)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        poles = len(self.positions[0].joins)
        for pos in self.positions:
            if len(pos.joins) != poles:
                raise ValueError(
                    f"Every position of {self.name} needs a choice for each of its {poles} poles."
                )
            if any(j is not None and not 1 <= j <= self.throws for j in pos.joins):
                raise ValueError(
                    f"{self.name} has throws 1 to {self.throws}: pick one of them, or open."
                )
        if self.look == "rotary" and self.throws < 3:
            raise ValueError(f"{self.name}: a rotary has 3 throws or more; draw it as a toggle.")
        return self

    @property
    def kind(self) -> SwitchKind:
        return custom_kind(
            self.name, self.throws, self.look, [(p.name, p.joins) for p in self.positions]
        )


class Switch(_Part):
    """One pole of a switch (v14, D-143), of a type from `switches.py` (`kind`: spdt,
    3pdt, rotary-2p4t, footswitch…). A single-pole switch is one part (SW1); a
    multi-pole one is a part per pole (`pole` a, b…: SW1A, SW1B), each placed on its
    own, all of one type, position and label. Its pins are the pole's lugs: 1, 2, 3 on a
    toggle (2 the common), C and 1…n on a rotary, with the pole's letter on a multi-pole
    switch (A1, A2, A3). `position` is the index into the type's positions; `names`, if
    given, names each position ("Vintage", "Modern"), an empty one keeping the type's."""

    type: Literal["switch"]
    kind: str = DEFAULT_KIND
    pole: Pole | None = None
    position: int = Field(0, ge=0)
    label: str | None = None
    names: list[Annotated[str, Field(max_length=POSITION_NAME_MAX)]] | None = None
    custom: CustomSwitch | None = None  # its own contacts, when `kind` is custom (v22)

    @property
    def switch_kind(self) -> SwitchKind:
        """Its type: the built-in one `kind` names, or its own (`custom`)."""
        if self.kind == CUSTOM and self.custom is not None:
            return self.custom.kind
        return kind_of(self.kind)

    @model_validator(mode="after")
    def _fits_kind(self) -> Self:
        if (self.kind == CUSTOM) != (self.custom is not None):
            raise ValueError(
                f"{self.ref}: a custom switch needs its contacts, and only a custom one has them."
            )
        kind = self.switch_kind
        if kind.poles == 1 and self.pole is not None:
            raise ValueError(f"{self.ref}: a {kind.short} has one pole, so no pole letter.")
        if kind.poles > 1:
            letters = POLE_LETTERS[: kind.poles].lower()
            if self.pole is None or self.pole not in letters:
                raise ValueError(
                    f"{self.ref}: a {kind.short} has poles {', '.join(letters.upper())}; "
                    "each is its own part (SW1A, SW1B…)."
                )
        if self.position >= len(kind.positions):
            raise ValueError(f"{self.ref}: a {kind.short} has {len(kind.positions)} positions.")
        if self.names is not None and len(self.names) != len(kind.positions):
            raise ValueError(
                f"{self.ref}: a {kind.short} has {len(kind.positions)} positions, so give "
                f"{len(kind.positions)} position names (or none)."
            )
        return self

    @property
    def position_names(self) -> list[str]:
        """Each position's name: yours where given, else the type's (1, Off, 2…)."""
        own = self.names or []
        return [
            own[i].strip() if i < len(own) and own[i].strip() else name
            for i, name in enumerate(self.switch_kind.positions)
        ]

    @property
    def switch(self) -> str:
        """The switch's ref: SW1 for SW1A and SW1B, the ref itself for a single pole."""
        return self.ref[:-1] if self.pole else self.ref


class Diode(_Part):
    """Pins A (anode) and K (cathode)."""

    type: Literal["diode"]
    model: str


class Led(_Part):
    """Pins A (anode) and K (cathode). `label`: what it's for ("Status"), v14."""

    type: Literal["led"]
    model: str
    label: str | None = None


class Measured(_Model):
    """Measured JFET parameters; they replace the model's Idss and pinch-off (Vp)."""

    idss: float = Field(gt=0)
    vp: float

    @model_validator(mode="after")
    def _vp_nonzero(self) -> Self:
        if self.vp == 0:
            raise ValueError("vp (pinch-off voltage) can't be 0")
        return self


class Jfet(_Part):
    """Pins D, G, S."""

    type: Literal["jfet"]
    model: str
    measured: Measured | None = None
    off_by_design: bool = False  # off at rest on purpose: a switch or rectifier (v29, D-238)


class MeasuredBjt(_Model):
    """A measured transistor (D-130). `hfe` (v10) replaces the model's BF: a germanium
    part's gain varies far more unit to unit than its model says (an AC128 is sold as
    45-165). `leakage` (v11, amps) is the collector current with the base open, on the
    Geofex tester (9 V, the collector through 2.4 kΩ); None: the model's own."""

    hfe: float = Field(gt=0, le=2000)
    leakage: float | None = Field(None, ge=0, le=0.01)


class Bjt(_Part):
    """Pins C, B, E. `off_by_design` (v29, D-238): off at rest on purpose, as a rectifier
    or a switch is, so being cut off isn't a problem."""

    type: Literal["bjt"]
    model: str
    measured: MeasuredBjt | None = None
    off_by_design: bool = False


class Mosfet(_Part):
    """An N-channel MOSFET (v18, D-175), enhancement or (by its model's VTO) depletion
    (D-178): pins D, G, S. The body diode, from source to drain, is in the model."""

    type: Literal["mosfet"]
    model: str
    off_by_design: bool = False  # off at rest on purpose: a switch (v29, D-238)


Half = Literal["a", "b", "c", "d"]  # a dual's a, b; a quad's a to d (v18)
Unit = Literal["a", "b", "c", "d", "e", "f"]  # a hex inverter's six (v20)


class _ChipUnit(_Part):
    """One unit of a chip (D-176): an op-amp, an inverter or an OTA. `half` is its letter
    on a chip of several (IC1A, IC1B…; the field keeps v12's name for every unit), None
    for a single chip. One model per chip; a chip of several has a `PowerUnit`."""

    model: str

    @property
    def chip(self) -> str:
        """The chip's ref: IC1 for IC1A and IC1B, the ref itself for a single."""
        half = getattr(self, "half", None)
        return self.ref[:-1] if half else self.ref


class Opamp(_ChipUnit):
    """An op-amp (v12, D-140): a single chip (TL071, LM308), or one of a chip's op-amps:
    `half` a or b of a dual (refs IC1A and IC1B since v13, as pedal docs name them), a to
    d of a quad (v18, D-172); one model per chip.
    Pins +, -, out; V+ and V- (power, real pins wired like any other) on a single only: a
    dual's or quad's are on its `PowerUnit` (v19, D-179); comp1/comp2 for models with
    compensation pins; a single's offset null and no-connect pins (null1, null2, nc) only
    with `show_pins`. v11's hidden `supply` became labels on V+ and V-."""

    type: Literal["opamp"]
    half: Half | None = None
    show_pins: bool = False


class Inverter(_ChipUnit):
    """One of a hex CMOS inverter's six (v20, D-180): CD4049UB, IC1A to IC1F, its power
    on unit G (VDD on V+, VSS on V-), as KiCad draws a 4049. Pins in, out."""

    type: Literal["inverter"]
    half: Unit


class Ota(_ChipUnit):
    """An OTA (v20, D-180): a single (CA3080: pins +, -, out, iabc and its own V+ and V-),
    or half a or b of a dual (LM13700: +, -, out, iabc, its linearising diodes' dbias, and
    its buffer's bufin and bufout; the chip's supply on its power unit, IC1C)."""

    type: Literal["ota"]
    half: Literal["a", "b"] | None = None


CHIP_UNITS = (Opamp, Inverter, Ota)
ChipUnit = Opamp | Inverter | Ota
# how many units a chip of each type may have (a single has no half and isn't listed)
CHIP_SIZES: Final[dict[str, tuple[int, ...]]] = {"opamp": (2, 4), "inverter": (6,), "ota": (2,)}
_UNIT_NAMES: Final = {"opamp": "op-amps", "inverter": "inverters", "ota": "OTAs"}


class PowerUnit(_Part):
    """A chip's power unit (v19, D-179), as KiCad draws a TL072's unit C: pins V+ and V-,
    the chip's supply, apart from its units. Its ref is the chip's and the letter after
    the last unit (IC1C on a dual, IC1E on a quad, IC1G on a 4049, D-180); its model is
    the chip's. It joins nothing itself: the chip's units run from the nets on its pins."""

    type: Literal["powerunit"]
    model: str

    @property
    def chip(self) -> str:
        return self.ref[:-1]


class VSource(_Part):
    """Ideal DC voltage source. Pins + and -."""

    type: Literal["vsource"]
    value: AnyValue


class ChargePump(_Part):
    """A charge-pump chip (TC1044S, LT1054...), drawn with its real pins (D-226): in (V+,
    pin 8), cap+ (2), gnd (3), cap- (4) and out (VOUT, 5). Its caps and diodes are drawn
    parts, and their wiring makes it a doubler, an inverter or both (`circuit.pump`).
    Pins 1, 6 and 7 may be wired too; pin 1 on V+ is boost on chips that have it (v28)."""

    type: Literal["chargepump"]
    model: str


class Regulator(_Part):
    """A fixed linear regulator (v27, D-227), such as a 78L12: in, gnd and out, as its
    datasheet names them. Its model's figures (output voltage, dropout, bias current, line
    and load regulation) drive Solum Builder's own model of it."""

    type: Literal["regulator"]
    model: str


class Pickup(_Model):
    """Pickup coil as a series R-L with its own winding capacitance across the output.
    `kind`: the pickup guide's entry it was filled from (`library/guides/pickups.yaml`);
    None for values of your own (D-096)."""

    r: PositiveValue
    l: PositiveValue  # noqa: E741  (inductance; the domain's own letter)
    c: PositiveValue
    kind: str | None = None


class Guitar(_Part):
    """The signal input. One pin, `out`; the other side is ground. `ideal` is a stiff
    source (a buffer or an active pickup in front); with a `pickup`, the guitar's volume
    pot (`volume`, its `taper` and `rotation`; None: no pot) and `cable` metres of lead
    sit between the coil and the circuit (D-096). Ideal ("buffered") ignores the cable;
    its volume pot sits before the buffer, so it turns only the level (D-134)."""

    type: Literal["guitar"]
    source: Literal["ideal", "pickup"] = "ideal"
    pickup: Pickup | None = None
    cable: float = Field(default=0.0, ge=0.0, le=30.0)
    volume: PositiveValue | None = None
    taper: Taper = "A"
    rotation: Fraction = 1.0
    stereo: bool = False  # a stereo input jack: its ring is pin `ring`, on GND with a plug in (v14)

    @property
    def has_volume(self) -> bool:
        """A volume knob to turn: the guitar's volume pot, with a pickup or buffered."""
        return self.volume is not None

    @model_validator(mode="after")
    def _pickup_given(self) -> Self:
        if self.source == "pickup" and self.pickup is None:
            raise ValueError("source 'pickup' needs pickup values (r, l, c)")
        return self


def turns(part: "Part") -> TypeGuard["Pot | Trimmer | Guitar"]:
    """Has a `rotation` a knob turns: a pot, a trimmer, or the guitar's volume (D-096)."""
    return isinstance(part, Pot | Trimmer) or (isinstance(part, Guitar) and part.has_volume)


class DcJack(_Part):
    """The 2.1 mm power jack, centre negative as on pedals (v14, D-143), wired to V+ and
    GND: the Power menu's supply (the wall wart) comes in here. Pins `+` (the sleeve),
    `-` (the centre pin) and `sw` (the battery lug). `plugged`: a plug is in, so `sw` is
    open; with none, `sw` touches the sleeve, so a battery wired to it reaches V+ and the
    Power menu's supply is off. Always DC: one per circuit."""

    type: Literal["dcjack"]
    plugged: bool = True


class Jack(_Part):
    """An input or output jack (v18, D-174), drawn as KiCad draws one: `AudioJack2` (mono,
    TS: pins T and S) or, `stereo`, `AudioJack3` (TRS: T, R and S). Drawing only, for the
    build and its export: the guitar input and the amp are where the simulation's signal
    starts and ends, so a jack carries no signal in it. `label`: what it's for (Input,
    Output). `plugged` (v21, D-185): a stereo jack's cable is in, so its sleeve joins the
    ring to S, the one contact the simulation keeps: a battery wired to the ring is on
    only with a cable in."""

    type: Literal["jack"]
    stereo: bool = False
    label: str | None = None
    plugged: bool = True


class Battery(_Part):
    """A 9 V battery (v14, D-143): `volts` across pins + and -, through `resistance` (its
    internal resistance; None: none). `state`: the battery guide's state the volts came
    from (fresh, half…), None for a voltage you measured. With no DC plug in (or no DC
    jack) it alone powers the circuit: the Power menu's positive supply is off, and V+ is
    whatever the battery's wiring gives it. A DC plug cuts it off only when its + goes
    through the DC jack's battery lug, as wired (D-185)."""

    type: Literal["battery"]
    volts: PositiveValue = 9.0
    state: str | None = "fresh"
    resistance: PositiveValue | None = None


class AmpInput(_Part):
    """The amplifier the pedal drives: a load from pin `in` to ground."""

    type: Literal["amp"]
    value: PositiveValue = "1M"


Part = Annotated[
    Resistor | Capacitor | Inductor | Pot | Trimmer | Switch | Diode | Led | Jfet | Bjt | Mosfet
    | Opamp | Inverter | Ota | PowerUnit | VSource | ChargePump | Regulator | Guitar | AmpInput
    | DcJack | Battery | Jack,
    Field(discriminator="type"),
]  # fmt: skip


class Wire(_Model):
    from_: Point = Field(alias="from")
    to: Point


class Label(_Model):
    """Names the net at `pos`. Same name anywhere = same net. `GND` is ground. `rot`
    turns a supply's symbol (ground, a rail) clockwise; it never changes the net (D-117)."""

    net: NetName
    pos: Point
    rot: Rotation = 0


TEXT_MAX = 2000  # characters in one text block: a paragraph or two, not a document
TITLE_MAX = 100  # characters in its title: one line
SUPPLY_SIGNS = {"V+": 1.0, "V-": -1.0}  # the only rails: V+ positive, V- negative (D-071)


class Power(_Model):
    """The supply: each rail is an ideal DC source. Rails are V+ (positive) and/or V-
    (negative); other supplies are nets the circuit makes itself (a filtered V+F, a VREF
    divider, a DC source's own net). v6 dropped `mode` (D-091)."""

    rails: dict[NetName, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _supplies(self) -> Self:
        for name, volts in self.rails.items():
            sign = SUPPLY_SIGNS.get(name)
            if sign is None:
                raise ValueError(
                    f"supply rails are V+ and V- only, but this file has one called {name!r}. "
                    "Rename it to V+ (positive) or V- (negative) in the file, and its labels "
                    "with it."
                )
            if volts * sign <= 0:
                kind = "positive" if sign > 0 else "negative"
                raise ValueError(f"{name} is the {kind} supply, so it can't be {volts:g} V.")
        return self


class TextBlock(_Model):
    """Free text on the sheet (v6): notes for whoever reads the drawing, not part of the
    circuit. An optional `title` is drawn in bold above `text`; `pos` is the top-left
    corner; lines are split on newlines. A block has a title, text, or both."""

    title: str = Field("", max_length=TITLE_MAX)
    text: str = Field("", max_length=TEXT_MAX)
    pos: Point

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not (self.title.strip() or self.text.strip()):
            raise ValueError("a text block needs a title or some text")
        return self


class Note(_Model):
    """A general note on the circuit (v30, the Notes pane's General tab): a title, its text,
    or both. Notes on a part live on the part (`note`), on a named net in `net_notes`."""

    title: str = Field("", max_length=TITLE_MAX)
    text: str = Field("", max_length=NOTE_MAX)

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not (self.title.strip() or self.text.strip()):
            raise ValueError("a note needs a title or some text")
        return self


class Probes(_Model):
    in_: str | None = Field(None, alias="in")
    out: str | None = None


REASON_MAX = 200  # characters in a dismissed problem's reason: a sentence


class Dismissal(_Model):
    """A problem the user dismissed (D-176): its mark is hidden and the Problems panel lists
    it under Dismissed, with `reason`. It names the problem as the rules do: the rule and
    the refs and nets the problem names (`problems.js` matches them)."""

    rule: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    refs: list[str] = Field(default_factory=list)
    nets: list[str] = Field(default_factory=list)
    reason: str = Field("", max_length=REASON_MAX)


class Version(_Model):
    """A version tag (v5, D-075): `major` changes only when the user starts a new major
    version; `minor` goes up by one on every save that changes the file. Shown `v1.12`."""

    major: int = Field(1, ge=1)
    minor: int = Field(0, ge=0)

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}"


class Enclosure(_Model):
    """The box a circuit is built in (v23, D-204): a standard size (`enclosures.SIZES`) or
    `custom` with its own outside length, width and height in mm."""

    size: str
    length: float | None = Field(None, gt=0, le=1000)
    width: float | None = Field(None, gt=0, le=1000)
    height: float | None = Field(None, gt=0, le=1000)

    @model_validator(mode="after")
    def _known(self) -> Self:
        if self.size == ENCLOSURE_CUSTOM:
            if None in (self.length, self.width, self.height):
                raise ValueError("A custom enclosure needs its length, width and height in mm.")
        elif size_of(self.size) is None:
            names = ", ".join(s.name for s in ENCLOSURE_SIZES)
            raise ValueError(f"Enclosure {self.size!r} isn't one of {names} or custom.")
        elif (self.length, self.width, self.height) != (None, None, None):
            raise ValueError(f"A {self.size} has its own size; give mm only for a custom one.")
        return self


class Circuit(_Model):
    schema_: Literal[30] = Field(alias="schema")
    id: str = Field(pattern=ID_PATTERN)
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)  # free words for search (v2)
    template: bool = False
    starter: bool = False
    version: Version = Field(default_factory=Version)  # v5
    final: bool = False  # a finished version: read-only until unlocked (v5)
    power: Power = Field(default_factory=Power)
    parts: list[Part]
    wires: list[Wire] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    texts: list[TextBlock] = Field(default_factory=list)  # v6
    ports: dict[NetName, NetName] = Field(default_factory=dict)  # port → net (templates)
    probes: Probes = Field(default_factory=Probes)
    notes: list[Note] = Field(default_factory=list)  # general notes (v30)
    net_notes: dict[str, NoteText] = Field(default_factory=dict)  # by net name (v30)
    dismissed: list[Dismissal] = Field(default_factory=list)  # problems dismissed (D-176)
    enclosure: Enclosure | None = None  # the box it's built in (v23, D-204)

    @model_validator(mode="after")
    def _unique_refs(self) -> Self:
        refs = [p.ref for p in self.parts]
        repeated = sorted({r for r in refs if refs.count(r) > 1})
        if "IN" in repeated or "OUT" in repeated:
            raise ValueError("A circuit has one guitar input (IN) and one amp (OUT).")
        if "DC" in repeated:
            raise ValueError("A circuit has one DC jack (DC).")
        if repeated:
            raise ValueError(f"each ref must be unique; repeated: {', '.join(repeated)}")
        return self

    @model_validator(mode="after")
    def _whole_chips(self) -> Self:
        """A chip's units are all there, of one type and one model: a dual's IC1A and IC1B
        (D-140), a quad's IC1A to IC1D (v18, D-172), a 4049's IC1A to IC1F (v20, D-180),
        and its power unit, the next letter (v19, D-179)."""
        chips: dict[str, list[ChipUnit]] = {}
        for p in self.parts:
            if isinstance(p, CHIP_UNITS) and p.half:
                chips.setdefault(p.chip, []).append(p)
        units = {p.chip: p for p in self.parts if isinstance(p, PowerUnit)}
        for chip, stray in units.items():
            if chip not in chips:
                raise ValueError(
                    f"{stray.ref} is a power unit, but chip {chip} has nothing else in the "
                    "file. Delete it, or the chip's other units went missing."
                )
        for chip, found in chips.items():
            kinds = sorted({p.type for p in found})
            if len(kinds) > 1:
                raise ValueError(
                    f"Chip {chip} mixes {' and '.join(_UNIT_NAMES[k] for k in kinds)}; a chip's "
                    "units are all one kind. Rename one of them."
                )
            kind = kinds[0]
            have = "".join(sorted(p.half or "" for p in found)).upper()
            size = next(n for n in CHIP_SIZES[kind] if n >= ord(max(have)) - 64)
            want = "ABCDEF"[:size]
            if have != want:
                missing = ", ".join(f"{chip}{x}" for x in want if x not in have)
                span = f"{chip}A and {chip}B" if size == 2 else f"{chip}A to {chip}{want[-1]}"
                raise ValueError(
                    f"Chip {chip} has {size} {_UNIT_NAMES[kind]}, {span}, but {missing} isn't "
                    "in the file. Add it or delete the chip."
                )
            power = f"{chip}{chr(ord(want[-1]) + 1)}"
            unit = units.get(chip)
            if unit is None or unit.ref != power:
                where = f"it's named {unit.ref}" if unit else "it isn't in the file"
                raise ValueError(
                    f"Chip {chip}'s power unit (V+ and V-) is {power}, but {where}. "
                    "Add it or delete the chip."
                )
            models = list(dict.fromkeys([*(p.model for p in found), unit.model]))
            if len(models) > 1:
                raise ValueError(
                    f"{chip}'s units use different models ({' and '.join(models)}); "
                    "a chip has one model."
                )
        return self

    @model_validator(mode="after")
    def _whole_switches(self) -> Self:
        """A multi-pole switch has every pole, of one type, position and label (D-143)."""
        poles: dict[str, list[Switch]] = {}
        for p in self.parts:
            if isinstance(p, Switch) and p.pole:
                poles.setdefault(p.switch, []).append(p)
        for name, found in poles.items():
            first = found[0]
            want = POLE_LETTERS[: first.switch_kind.poles]
            have = "".join(sorted(p.pole.upper() for p in found if p.pole))
            if have != want:
                missing = ", ".join(f"{name}{x}" for x in want if x not in have)
                raise ValueError(
                    f"Switch {name} is a {first.switch_kind.short} with poles "
                    f"{', '.join(want)}, but {missing or 'some'} isn't in the file. "
                    f"Add it or delete the switch."
                )
            for p in found[1:]:
                same = (first.kind, first.custom, first.position, first.label, first.names)
                if (p.kind, p.custom, p.position, p.label, p.names) != same:
                    raise ValueError(
                        f"{first.ref} and {p.ref} are poles of one switch {name}: they need "
                        "the same type, position, label and position names."
                    )
        return self

    @model_validator(mode="after")
    def _whole_pots(self) -> Self:
        """A dual pot has both gangs, of one value, taper, rotation and label (D-217)."""
        gangs: dict[str, list[Pot]] = {}
        for p in self.parts:
            if isinstance(p, Pot) and p.gang:
                gangs.setdefault(p.knob, []).append(p)
        for name, found in gangs.items():
            have = {p.gang for p in found}
            missing = [f"{name}{x.upper()}" for x in ("a", "b") if x not in have]
            if missing:
                raise ValueError(
                    f"Pot {name} is a dual pot with gangs A and B, but {missing[0]} isn't in "
                    "the file. Add it or delete the pot."
                )
            first = found[0]
            for p in found[1:]:
                same = (first.value, first.taper, first.rotation, first.label)
                if (p.value, p.taper, p.rotation, p.label) != same:
                    raise ValueError(
                        f"{first.ref} and {p.ref} are the gangs of one pot {name}: they need "
                        "the same value, taper, rotation and label."
                    )
        return self

    @model_validator(mode="after")
    def _ports_on_sheet(self) -> Self:
        named = {lb.net for lb in self.labels} | set(self.power.rails)
        for port, net in self.ports.items():
            if net not in named:
                raise ValueError(
                    f"port {port!r} is on net {net!r}, but no label on the sheet is called "
                    f"{net!r}. Put a label named {net} on that net."
                )
        return self

    def part(self, ref: str) -> Part:
        """The part with this ref; a dual pot's name (VR1) gives its gang A, which stands
        for the pot (D-217). KeyError if there is none."""
        for p in self.parts:
            if p.ref == ref:
                return p
        for p in self.parts:
            if isinstance(p, Pot) and p.gang == "a" and p.knob == ref:
                return p
        raise KeyError(f"No part {ref} in this circuit.")

    def units(self, ref: str) -> list[str]:
        """The parts one control turns: a multi-pole switch's poles (SW1, D-143), a dual
        pot's gangs (VR1, D-217); else the part itself, by its ref."""
        found = [
            p.ref
            for p in self.parts
            if (isinstance(p, Switch) and p.pole and p.switch == ref)
            or (isinstance(p, Pot) and p.gang and p.knob == ref)
        ]
        return sorted(found) or [ref]

    def with_part(self, ref: str, **fields: Any) -> "Circuit":
        """A copy with some of one part's fields changed (a knob turned, a value swapped),
        validated like a loaded file. A multi-pole switch's name (SW1) changes every pole
        (D-143), a dual pot's name (VR1) both gangs (D-217). KeyError if there is no such part."""
        units = self.units(ref)
        if units != [ref]:
            out = self
            for unit in units:
                out = out.with_part(unit, **fields)
            return out
        old = self.part(ref)
        new = type(old).model_validate({**old.model_dump(by_alias=True), **fields})
        parts = [new if p.ref == ref else p for p in self.parts]
        return self.model_copy(update={"parts": parts})


def json_schema() -> dict[str, Any]:
    """The JSON Schema for circuit files, generated from `Circuit`."""
    schema = Circuit.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = f"Solum Builder circuit, schema v{SCHEMA_VERSION}"
    return schema


def json_schema_text() -> str:
    return json.dumps(json_schema(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(json_schema_text(), end="")
