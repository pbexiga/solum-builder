"""Switch types (D-143): the one owner of what each kind of switch is, its lugs, its
positions and which contacts close in each.

A switch is picked by its type (SPDT, 3PDT, a 2P4T selector…), not by poles and throws.
Each pole is drawn as its own part: a single-pole switch is SW1, a multi-pole one is
SW1A, SW1B… (one switch, one knob, one type and position on every pole), as Aion FX's
documents draw them. A pole's lugs are named as on the part: a toggle's 1, 2, 3 (2 the
common, the middle lug), a rotary's C and 1…n. A multi-pole switch's lugs carry the
pole's letter (A1-A3, B1-B3), so a lug name is the same on the schematic, the form and
an export.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

POLE_LETTERS = "ABCD"  # a multi-pole switch's poles, in its refs (SW1A…) and lug names (A1…)
DEFAULT_KIND = "spdt"
CUSTOM = "custom"  # the kind of a switch whose contacts its part defines (9c)
# a custom switch's limits (9c, the user: "a custom (with limits)")
MAX_POLES, MAX_THROWS, MAX_POSITIONS = len(POLE_LETTERS), 12, 12
Look = Literal["toggle", "rotary"]  # how a pole is drawn: a column of contacts, or an arc


@dataclass(frozen=True)
class SwitchKind:
    """One type of switch. `closed[position][pole]` is the lug that pole's common joins
    at that position, or None when the pole is open."""

    id: str
    name: str  # as the form lists it: "DPDT on-off-on toggle"
    short: str  # under the symbol: "DPDT on-off-on"
    group: str  # the form's heading: Toggle, Selector, Footswitch
    poles: int
    lugs: tuple[str, ...]  # one pole's lugs, the common first
    positions: tuple[str, ...]  # each position's name, as Knobs shows it
    closed: tuple[tuple[str | None, ...], ...]
    hint: str = ""
    look: Look = "toggle"

    @property
    def common(self) -> str:
        return self.lugs[0]

    @property
    def throws(self) -> tuple[str, ...]:
        """One pole's lugs other than the common, in drawing order."""
        return self.lugs[1:]


def _toggle(
    id_: str, short: str, poles: int, centre_off: bool = False, momentary: bool = False
) -> SwitchKind:
    """A toggle: lugs 1, 2, 3 per pole, 2 the common; on-on joins 1 then 3, on-off-on
    opens all poles in the middle. A momentary one, (on)-off-(on), is an on-off-on whose
    ends spring back to Off."""
    up, down = ("1",) * poles, ("3",) * poles
    positions: tuple[str, ...]
    closed: tuple[tuple[str | None, ...], ...]
    if centre_off or momentary:
        positions, closed = ("1", "Off", "2"), (up, (None,) * poles, down)
    else:
        positions, closed = ("1", "2"), (up, down)
    kind = " (on)-off-(on)" if momentary else " on-off-on" if centre_off else ""
    name = f"{short}{kind} toggle" + (" (momentary)" if momentary else "")
    hint = TOGGLE_MOMENTARY_HINT if momentary else ""
    return SwitchKind(id_, name, f"{short}{kind}", "Toggle", poles, ("2", "1", "3"),
                      positions, closed, hint)  # fmt: skip


def _single_throw(id_: str, short: str, poles: int) -> SwitchKind:
    """On-off: lugs 1 and 2 per pole, joined when on."""
    return SwitchKind(id_, f"{short} on-off toggle", short, "Toggle", poles, ("1", "2"),
                      ("Off", "On"), ((None,) * poles, ("2",) * poles))  # fmt: skip


def _dip(switches: int) -> SwitchKind:
    """A DIP switch on the board (D-238): `switches` independent on-off switches, lugs 1
    and 2 each. As one switch of that many poles its positions are every combination,
    switch 1 the lowest bit: All off, 1 on, 2 on, 1 and 2 on…"""
    positions: list[str] = []
    closed: list[tuple[str | None, ...]] = []
    for combo in range(2**switches):
        on = [str(n + 1) for n in range(switches) if combo >> n & 1]
        if not on or len(on) == switches > 2:
            positions.append("All on" if on else "All off")
        else:
            positions.append(f"{' and '.join(on)} on")
        closed.append(tuple("2" if combo >> n & 1 else None for n in range(switches)))
    name = f"DIP switch, {switches} positions"
    return SwitchKind(f"dip-{switches}", name, f"DIP-{switches}", "DIP", switches, ("1", "2"),
                      tuple(positions), tuple(closed), DIP_HINT)  # fmt: skip


def _rotary(poles: int, throws: int) -> SwitchKind:
    """A selector: a common C and lugs 1…n per pole; position k joins C to k. Named by its
    poles and throws alone (the user, D-164): a rotary (Lorlin type) or a slide switch
    wires the same. The id keeps "rotary" so files don't change."""
    lugs = tuple(str(n) for n in range(1, throws + 1))
    name = f"{poles}P{throws}T"
    return SwitchKind(f"rotary-{poles}p{throws}t", name, name, "Selector", poles,
                      ("C", *lugs), lugs, tuple((lug,) * poles for lug in lugs),
                      SELECTOR_HINT, "rotary")  # fmt: skip


def _stomp(id_: str, short: str, poles: int, hint: str = "") -> SwitchKind:
    """A latching footswitch: lugs 1, 2, 3 per pole (2 the common), On joins 1, Bypassed 3."""
    return SwitchKind(id_, f"{short} footswitch (stomp)", f"{short} footswitch", "Footswitch",
                      poles, ("2", "1", "3"), ("On", "Bypassed"),
                      (("1",) * poles, ("3",) * poles), hint)  # fmt: skip


def _momentary(id_: str, name: str, short: str, group: str, normally_open: bool) -> SwitchKind:
    """A momentary contact, lugs 1 and 2: normally open joins them while pressed, normally
    closed opens them. Knobs holds it where it's put, to hear each."""
    held: tuple[tuple[str | None, ...], ...] = ((None,), ("2",))
    return SwitchKind(id_, name, short, group, 1, ("1", "2"), ("Released", "Pressed"),
                      held if normally_open else held[::-1], MOMENTARY_HINT)  # fmt: skip


DIP_HINT = ("A DIP switch, inside on the board: each of its switches is on or off by "
            "itself, so its positions are every combination.")  # fmt: skip
SELECTOR_HINT = ("A rotary or slide switch: each position joins the common (C) to one lug. "
                 "For an on-on-on toggle, see DPDT on-on-on.")  # fmt: skip
TOGGLE_MOMENTARY_HINT = ("Momentary: on the pedal each end springs back to Off. Knobs holds it "
                         "where you put it, so you can hear each.")  # fmt: skip
MOMENTARY_HINT = ("Momentary: on the pedal it springs back to Released. Knobs holds it where "
                  "you put it, so you can hear each.")  # fmt: skip


# The DPDT on-on-on (a 3-way toggle): makers wire its middle differently. These are
# Honeywell's 2NT1-12 (DigiKey forum, "Wiring a DPDT switch to act like a SP3T": keyway
# 1-2, 4-5; centre 2-3, 4-5; opposite 2-3, 5-6), its lugs 4-6 being our B1-B3.
_ON_ON_ON = SwitchKind(
    "dpdt-on-on-on", "DPDT on-on-on toggle (3-way)", "DPDT on-on-on", "Toggle", 2,
    ("2", "1", "3"), ("1", "2", "3"), (("1", "1"), ("3", "1"), ("3", "3")),
    "The middle position differs between makers. These are Honeywell's 2NT1-12 "
    "(1: A2-A1 and B2-B1, 2: A2-A3 and B2-B1, 3: A2-A3 and B2-B3); check yours with a "
    "meter.",
)  # fmt: skip

STOMP_HINT = "On: each pole's 2 joins its 1; Bypassed: its 3."

# The form lists them in this order: the toggles pedals use most first (on-on, on-off-on,
# on-on-on; the user, 2026-11-04), then on-off, push buttons, footswitches, selectors.
# Only what's sold (the user, "trim to what's sold"; Tayda's mini toggles and stomps,
# Alpha's SR2511F rotaries: 1P3T to 1P6T and 1P12T, 2P3T to 2P6T, 3P4T, 4P3T). Anything
# else is a custom switch.
KINDS: dict[str, SwitchKind] = {
    k.id: k
    for k in (
        _toggle("spdt", "SPDT", 1),
        _toggle("dpdt", "DPDT", 2),
        _toggle("3pdt", "3PDT", 3),
        _toggle("4pdt", "4PDT", 4),
        _toggle("spdt-on-off-on", "SPDT", 1, centre_off=True),
        _toggle("dpdt-on-off-on", "DPDT", 2, centre_off=True),
        _toggle("3pdt-on-off-on", "3PDT", 3, centre_off=True),
        _ON_ON_ON,
        _toggle("spdt-momentary", "SPDT", 1, momentary=True),
        _toggle("dpdt-momentary", "DPDT", 2, momentary=True),
        _single_throw("spst", "SPST", 1),
        _single_throw("dpst", "DPST", 2),
        _momentary("push-no", "Push button, normally open", "push NO", "Push button", True),
        _momentary("push-nc", "Push button, normally closed", "push NC", "Push button", False),
        _stomp("footswitch-dpdt", "DPDT", 2, STOMP_HINT),
        _stomp(
            "footswitch",
            "3PDT",
            3,
            "On: each pole's 2 joins its 1 (the effect, the LED "
            "lit); Bypassed: its 3. The True bypass block wires one.",
        ),
        _momentary(
            "footswitch-momentary",
            "SPST momentary footswitch (soft-touch, tap tempo)",
            "momentary footswitch",
            "Footswitch",
            True,
        ),
        _dip(2),
        _dip(3),
        *(
            _rotary(p, t)
            for p, throws in ((1, (3, 4, 5, 6, 12)), (2, (3, 4, 5, 6)), (3, (4,)), (4, (3,)))
            for t in throws
        ),
    )
}


def throw_lugs(throws: int, look: Look) -> tuple[str, ...]:
    """A custom pole's lugs, the common first, named as the built-in types with that many
    throws name theirs: one throw 1, 2 (an SPST's); two drawn as a toggle 2, 1, 3; else C
    and 1…n (a selector's)."""
    if throws == 1:
        return ("1", "2")
    if throws == 2 and look == "toggle":
        return ("2", "1", "3")
    return ("C", *(str(n) for n in range(1, throws + 1)))


def custom_kind(
    name: str, throws: int, look: Look, positions: Sequence[tuple[str, Sequence[int | None]]]
) -> SwitchKind:
    """A switch type from its part's own definition (9c): its name, throws per pole, look,
    and each position's name with, per pole, the throw (1…n) its common joins or None."""
    lugs = throw_lugs(throws, look)
    closed = tuple(tuple(None if j is None else lugs[j] for j in joins) for _, joins in positions)
    return SwitchKind(CUSTOM, name, name, "Custom", len(positions[0][1]), lugs,
                      tuple(n for n, _ in positions), closed, "", look)  # fmt: skip


def kind_of(kind_id: str) -> SwitchKind:
    """The switch type with this id. ValueError (plain English) if there's none."""
    if kind_id not in KINDS:
        raise ValueError(f"There's no switch type {kind_id!r}; pick one from the list.")
    return KINDS[kind_id]


def lug_name(kind: SwitchKind, pole: str | None, lug: str) -> str:
    """A lug's pin name on a pole's part: A2 on a multi-pole switch's pole A, 2 on a
    single-pole one."""
    return f"{pole.upper()}{lug}" if pole else lug


def pole_contacts(kind: SwitchKind, pole: str | None, position: int) -> list[tuple[str, str, bool]]:
    """Every (common, throw, closed) contact of one pole at `position`, as pin names."""
    index = POLE_LETTERS.index(pole.upper()) if pole else 0
    joined = kind.closed[position][index]
    common = lug_name(kind, pole, kind.common)
    return [(common, lug_name(kind, pole, t), t == joined) for t in kind.throws]


def contacts_text(kind: SwitchKind, position: int) -> str:
    """What a position joins on every pole, in words: "A2\u2013A1, B2\u2013B1", or "open"
    (the Knobs pane's tooltip, D-143)."""
    letters: list[str | None] = list(POLE_LETTERS[: kind.poles]) if kind.poles > 1 else [None]
    joined = [
        f"{common}\u2013{throw}"
        for pole in letters
        for common, throw, closed in pole_contacts(kind, pole, position)
        if closed
    ]
    return ", ".join(joined) or "open"


def catalogue() -> list[dict[str, object]]:
    """Every switch type, for the form's picker and the symbol: id, names, lugs,
    positions and which lug each pole's common joins in each (GET /api/switches)."""
    return [
        {"id": k.id, "name": k.name, "short": k.short, "group": k.group, "poles": k.poles,
         "lugs": list(k.lugs), "positions": list(k.positions),
         "closed": [list(c) for c in k.closed], "hint": k.hint, "look": k.look}
        for k in KINDS.values()
    ]  # fmt: skip


def from_poles_throws(poles: int, throws: int, position: int) -> tuple[str, int]:
    """A v13 switch's (poles, throws, position) as a type and position (the v14
    migration). Throws map in order onto the type's throws; a single-throw pole of three
    or four poles becomes a PDT with lug 3 left spare. ValueError for a rotary of three
    or four poles, which no file had."""
    if throws == 1:
        kind = {1: "spst", 2: "dpst", 3: "3pdt", 4: "4pdt"}[poles]
        if poles <= 2:
            return kind, position
        return kind, 0 if position == 1 else 1  # closed: lug 1; open: lug 3, unwired
    if throws == 2:
        return {1: "spdt", 2: "dpdt", 3: "3pdt", 4: "4pdt"}[poles], position
    if poles > 2:
        raise ValueError(
            f"A {poles}-pole switch with {throws} throws has no switch type; redraw it "
            "with a rotary of up to two poles."
        )
    return f"rotary-{poles}p{throws}t", position
