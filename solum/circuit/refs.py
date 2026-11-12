"""Part refs (D-141): each part type's prefix, the one owner (the editor's palette
mirrors it, tested). A ref is its type's prefix and a number (R1, VR2, LED3); a chip
may be IC or U (IC1, U2); a resistor R, RPD (an input pull-down) or LEDR (an LED's
resistor), as Aion names them but numbered (RPD1, LEDR2: D-232); an LED LED or D (a
clipping diode swapped for an LED keeps its D1, as mod guides write it); a diode D or
Z (a zener). A dual's halves end in A or B (IC1A, IC1B), a quad's in A to D, a 4049's
six inverters in A to F (D-180), and its power unit in the next letter (IC1C, IC1E,
IC1G: D-179); a switch's poles in A to D (SW1A, D-143), a dual pot's gangs in A and B
(VR1A, D-217); the guitar input is always IN, the amp always OUT and the DC jack always
DC. A knob's or switch's name goes in its label.
"""

import re

PREFIXES: dict[str, tuple[str, ...]] = {
    "resistor": ("R", "RPD", "LEDR"),  # RPD an input pull-down, LEDR an LED's (D-232)
    "capacitor": ("C",),
    "inductor": ("L",),
    "pot": ("VR",),
    "trimmer": ("TR",),
    "switch": ("SW",),
    "diode": ("D", "Z"),  # Z too: a zener, as schematics often name it (Z1, D-221)
    "led": ("LED", "D"),  # D too: a diode swapped for an LED keeps its number (D1)
    "bjt": ("Q",),
    "jfet": ("Q",),
    "mosfet": ("Q",),
    "opamp": ("IC", "U"),
    "inverter": ("IC", "U"),  # one of a 4049's six (D-180)
    "ota": ("IC", "U"),
    "powerunit": ("IC", "U"),  # a chip's power unit: IC1C on a dual (D-179)
    "chargepump": ("IC", "U"),
    "regulator": ("IC", "U"),
    "vsource": ("V",),
    "battery": ("BAT",),
    "jack": ("J",),  # KiCad's
}
FIXED: dict[str, str] = {"guitar": "IN", "amp": "OUT", "dcjack": "DC"}
HALVES = {x: x.upper() for x in "abcdef"}  # a chip's unit → its ref's letter (a 4049's a to f)
POLES = {"a": "A", "b": "B", "c": "C", "d": "D"}  # a switch's pole → its ref's letter (D-143)
NAMED = ("pot", "trimmer", "switch", "jack")  # their name goes in the label
_WHAT = {
    "resistor": "A resistor",
    "capacitor": "A capacitor",
    "inductor": "An inductor",
    "pot": "A pot",
    "trimmer": "A trimmer",
    "switch": "A switch",
    "diode": "A diode",
    "led": "An LED",
    "bjt": "A transistor",
    "jfet": "A JFET",
    "mosfet": "A MOSFET",
    "opamp": "An op-amp",
    "inverter": "An inverter",
    "ota": "An OTA",
    "powerunit": "A chip's power unit",
    "chargepump": "A charge pump",
    "regulator": "A regulator",
    "vsource": "A DC source",
    "battery": "A battery",
    "jack": "A jack",
}


_FIXED_WHAT = {"guitar": "The guitar input", "amp": "The amp", "dcjack": "The DC jack"}


def ref_problem(kind: str, ref: str, half: str | None = None) -> str | None:
    """What's wrong with `ref` for a part of type `kind` (`half`: a chip's half a/b, a
    switch's pole a-d or a dual pot's gang a/b), in plain English with what to do; None
    if it's right."""
    if kind in FIXED:
        fixed = FIXED[kind]
        return None if ref == fixed else f"{_FIXED_WHAT[kind]} is always {fixed}."
    prefixes = PREFIXES[kind]
    if kind == "powerunit":  # the chip's ref and the letter after its last unit (D-179)
        if re.fullmatch(rf"(?:{'|'.join(prefixes)})[1-9][0-9]*[B-H]", ref):
            return None
        return (
            "A chip's power unit is the chip's ref and the letter after its last unit, "
            "like IC1C on a dual op-amp."
        )
    end = half.upper() if half else ""
    if re.fullmatch(rf"(?:{'|'.join(prefixes)})[1-9][0-9]*{end}", ref):
        return None
    example = f"{prefixes[0]}1{end}"
    shape = " or ".join([", ".join(prefixes[:-1]), prefixes[-1]] if len(prefixes) > 1 else prefixes)
    if half and kind == "pot":
        return f"Gang {end} of a dual pot is {shape}, a number and {end}, like {example}."
    if half and kind == "switch":
        return f"Pole {end} of a switch is {shape}, a number and {end}, like {example}."
    if half:
        return f"Half {end} of a chip is {shape}, a number and {end}, like {example}."
    tail = " Put its name in its label." if kind in NAMED else ""
    return f"{_WHAT[kind]}'s ref is {shape} and a number, like {example}.{tail}"


def ref_number(ref: str) -> int | None:
    """The number in a ref (12 in R12, 1 in IC1A), or None."""
    found = re.search(r"([0-9]+)[A-H]?$", ref)
    return int(found.group(1)) if found else None


def ref_key(ref: str) -> tuple[str, int, str]:
    """Sorts refs as a parts list does: by prefix, then number (C2 before C10), then a
    chip's or switch's letter (IC1A before IC1B); a ref with no number after its prefix."""
    found = re.fullmatch(r"([A-Za-z]*?)([0-9]+)([A-Za-z]*)", ref)
    if not found:
        return (ref, 0, "")
    return (found.group(1), int(found.group(2)), found.group(3))
