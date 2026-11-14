"""The worked example for the build-starter skill: Aion FX's Refractor (Klon Centaur) drawn
as a starter by script (D-213). The starters it made have been edited in the app since, so
it writes to scratch/example/ now, not over them. A new starter's script writes to
library/starters/.


Parts placed by hand to follow Aion's
drawing, wires pin to pin, the drawn connectivity checked against the intended netlist.
Run in the dev image: make run CMD="python .claude/skills/build-starter/make_klon.py"
"""

import json
from pathlib import Path

from solum.circuit.draw import Drawing, net_differences
from solum.circuit.io import parse_circuit

OUT = Path("scratch/example/klon-centaur.json")  # the circuit alone, to start from
OUT_BUILT = Path("scratch/example/klon-centaur-built.json")  # with its bypass board

# The drawing's steps (`solum/circuit/draw.py`): part() places a part, wire() runs pin
# to pin ("R1.2") or point to point, label() names nets, stub() ends a short wire in a
# label.
sheet = Drawing()
part, wire, label, stub = sheet.part, sheet.wire, sheet.label, sheet.stub
parts, wires, labels = sheet.parts, sheet.wires, sheet.labels


R = "resistor"
C = "capacitor"
V = 90  # vertical: pin 1 on top
FILM = {"kind": "film"}

# --- Supply (top): VA is V+; R29/R30 make VR; IC3 (LT1054) doubles to VB and inverts to -VA
S = -400
label("V+", (0, S))
part("C17", C, (60, S + 40), V, value="100µ", kind="electrolytic", rating_v=16.0)
part("R29", R, (160, S), value="27k")
part("R30", R, (220, S + 40), V, value="27k")
part("C18", C, (280, S + 40), V, value="47µ", kind="electrolytic", rating_v=16.0)
wire((0, S), "R29.1")
wire((60, S), "C17.1")
part("Z1", "diode", (-60, S + 40), 270, model="1N4742A")  # cathode up, on VA
wire((0, S), (-60, S), "Z1.K")
wire("R29.2", (280, S))
wire((220, S), "R30.1")
wire((280, S), "C18.1")
label("VR", (280, S))
# IC3 as Aion draws it (D-226): D3 from VA and D4 to VB left of the chip, C20 from their
# junction to pin 2, C21 from pin 2 to pin 4, VOUT (pin 5) is -VA
part("IC3", "chargepump", (540, S), model="LT1054")
part("D3", "diode", (400, S - 50), 180, model="1N4001")  # anode right, on VA
part("D4", "diode", (300, S - 50), 180, model="1N4001")
part(
    "C20", C, (340, S - 30), V, value="10µ", kind="electrolytic", rating_v=25.0
)  # + at the junction
part("C21", C, (420, S + 10), V, value="10µ", kind="electrolytic", rating_v=25.0)  # + on pin 2
wire("D3.K", "D4.A")
wire("C20.2", "IC3.cap+")
wire("C21.2", "IC3.cap-")
part("C22", C, (680, S + 40), V, value="10µ", kind="electrolytic", rating_v=25.0)
part("C19", C, (740, S + 40), V, value="10µ", kind="electrolytic", rating_v=16.0)
part("IC1C", "powerunit", (840, S + 20), model="TL072")
part("IC2C", "powerunit", (920, S + 20), model="TL072")
label("V+", "IC3.in", "IC1C.V+", "D3.A")
label("VB", "D4.K", "C22.1", "IC2C.V+")
for _p in ("C19.2", "IC2C.V-"):  # bottom pins: the bar points down, clear of the part
    label("-VA", _p, rot=180)
label("-VA", "IC3.out", rot=90)
label("GND", "IC3.gnd", rot=90)
label("GND", "C17.2", "Z1.A", "R30.2", "C18.2", "C22.2", "IC1C.V-")
label("GND", "C19.1", rot=180)  # top pin: points up

# --- Input buffer (Aion's IC1A, pins 5-7: our IC1B)
label("pcb-in", (20, 0))
part("RPD1", R, (40, 40), V, value="2M")  # Aion's RPD
part("R1", R, (80, 0), value="10k")
part("C1", C, (140, 0), value="100n", **FILM)
part("R2", R, (180, -40), V, value="2M")
part("IC1B", "opamp", (240, -20), model="TL072", half="b")
wire((20, 0), "R1.1")
wire((40, 0), "RPD1.1")
wire("R1.2", "C1.1")
wire("C1.2", "IC1B.+")
wire("R2.2", (180, 0))
label("VR", "R2.1")
wire("IC1B.-", (200, -80), (300, -80), (300, -20))
wire("IC1B.out", (300, -20))
# Buffered output (Aion's top wire): C2, R3 to ground, R4 to the bypass board
part("C2", C, (340, -300), value="4.7µ", kind="electrolytic", rating_v=25.0)  # + to the buffer
part("R3", R, (380, -280), V, value="100k")
part("R4", R, (440, -300), value="560")
wire((300, -80), (300, -300), "C2.1")
wire("C2.2", "R4.1")
label("GND", "R3.2")
label("buffer-out", "R4.2")

# --- Clean path from the buffer: C3 into R6 || C5 (to the gain stage) and R7, C16, R19
part("C3", C, (340, -20), value="100n", **FILM)
part("R6", R, (420, -20), value="10k")
part("C5", C, (420, -80), value="68n", **FILM)
part("R7", R, (420, -200), value="1k5")
part("C16", C, (460, -160), V, value="1µ", **FILM)  # Aion's tantalum, D-218
part("R19", R, (500, -200), value="15k")
wire((300, -20), "C3.1")
wire("C3.2", "R6.1")
wire((380, -20), (380, -80), "C5.1")
wire("C5.2", (460, -80), (460, -20))
wire("R6.2", (460, -20))
wire((380, -80), (380, -200), "R7.1")
wire("R7.2", (460, -200), "C16.1")
wire((460, -200), "R19.1")
wire("R19.2", (1220, -200), (1220, 0))

# --- Gain stage (Aion's IC1B, pins 1-3: our IC1A), Gain A between its inputs
part("VR1A", "pot", (560, -100), value="100k", taper="B", rotation=0.5, label="Gain", gang="a")
part("R10", R, (620, -100), value="2k")
part("R11", R, (680, -100), value="15k")
part("C7", C, (680, -160), value="82n", **FILM)
part("R12", R, (780, -100), value="422k")
part("C8", C, (780, -160), value="390p", kind="c0g")
part("IC1A", "opamp", (760, 0), model="TL072", half="a")
wire((460, -20), (460, 20), "IC1A.+")
wire("VR1A.1", (540, 20))
label("VR", "VR1A.2")
wire("VR1A.3", "R10.1")
wire("R10.2", "R11.1")
wire((640, -100), (640, -160), "C7.1")
wire("C7.2", (720, -160))
wire("R11.2", (720, -100))
wire((720, -160), (720, -100), "IC1A.-")
wire((720, -160), "C8.1")
wire((720, -100), "R12.1")
wire("C8.2", (840, -160), (840, 0))
wire("R12.2", (840, -100))
wire("IC1A.out", (840, 0))

# --- Clipping: C9, R13, D1/D2 to ground; C10 on to the summing amp
part("C9", C, (880, 0), value="1µ", **FILM)
part("R13", R, (940, 0), value="1k")
part("D1", "diode", (1040, 40), V, model="BAT41")
# D2's text is on its left, D1's on its right: they face away from each other
part("D2", "diode", (960, 40), 270, model="BAT41")
part("C10", C, (1080, 0), value="1µ", **FILM)
part("R16", R, (1160, 0), value="47k")
part("C11", C, (1120, 60), V, value="2n2", **FILM)
part("R15", R, (1120, 140), V, value="22k")
wire((840, 0), "C9.1")
wire("C9.2", "R13.1")
wire("R13.2", "C10.1")
wire((1040, 0), "D1.A")
wire((960, 0), "D2.K")
wire("C10.2", "R16.1")
wire((1120, 0), "C11.1")
wire("C11.2", "R15.1")
wire("R15.2", (1120, 200))
label("clip", "R13.2")

# --- Gain B: the clean signal's share, through R5 || C4 and C6/R9, R8 to VR
part("R5", R, (300, 300), V, value="5k1")
part("C4", C, (360, 300), V, value="68n", **FILM)
part("R8", R, (300, 380), V, value="1k5")
part("C6", C, (360, 380), V, value="390n", **FILM)
part("R9", R, (360, 440), V, value="1k")
part("VR1B", "pot", (440, 340), value="100k", taper="B", rotation=0.5, label="Gain", gang="b")
wire((300, -20), "R5.1")
wire((300, 260), (360, 260), "C4.1")
wire("R5.2", (300, 340), (360, 340), "C4.2")
wire((300, 340), "R8.1")
wire((360, 340), "C6.1")
wire("C6.2", "R9.1")
wire((360, 340), "VR1B.1")
wire("VR1B.2", (440, 200), (1280, 200))
label("VR", "VR1B.3")
for _r in ("R8.2", "R9.2"):  # bottom pins: the supply bar points down
    label("VR", _r, rot=180)

# --- Summing amp (IC2A) and its mix of R16, R19, R17 and C12/R18
part("R17", R, (1220, 140), V, value="27k")
part("C12", C, (1280, 80), V, value="27n", **FILM)
part("R18", R, (1280, 140), V, value="12k")
part("IC2A", "opamp", (1360, 20), model="TL072", half="a")
part("R20", R, (1360, -60), value="392k")
part("C13", C, (1360, -120), value="820p", kind="c0g")
wire("R16.2", "IC2A.-")
wire((1220, 0), "R17.1")
wire((1220, 40), (1280, 40), "C12.1")
wire("C12.2", "R18.1")
wire("R17.2", (1220, 200))
wire("R18.2", (1280, 200))
label("VR", "IC2A.+")
wire((1300, 0), (1300, -120), "C13.1")
wire((1300, -60), "R20.1")
wire("C13.2", (1420, -120), (1420, 20))
wire("R20.2", (1420, -60))
wire("IC2A.out", (1420, 20))

# --- Treble (IC2B) and Output
part("R22", R, (1520, 20), value="100k")
part("IC2B", "opamp", (1700, 40), model="TL072", half="b")
part("R24", R, (1680, -40), value="100k")
part("R21", R, (1480, 220), value="1k8")
part("VR2", "pot", (1560, 160), V, value="10k", taper="B", rotation=0.5, label="Treble")
part("R23", R, (1660, 120), value="4k7")
part("C14", C, (1600, 80), V, value="3n9", **FILM)
part("C15", C, (1800, 40), value="4.7µ", kind="electrolytic", rating_v=25.0)
part("R25", R, (1860, 40), value="560")
part("VR3", "pot", (1900, 80), 270, value="10k", taper="B", rotation=0.5, label="Output")
wire((1420, 20), "R22.1")
wire("R22.2", "IC2B.-")
label("VR", "IC2B.+")
wire((1600, 20), (1600, -40), "R24.1")
wire("R24.2", (1760, -40), (1760, 40))
wire("IC2B.out", (1760, 40))
wire((1440, 20), (1440, 220), "R21.1")
wire("R21.2", (1560, 220), "VR2.3")
wire("VR2.1", (1560, 120), "R23.1")
wire("R23.2", (1760, 120), (1760, 40))
wire("VR2.2", (1600, 160), "C14.2")
wire("C14.1", (1600, 20))
wire((1760, 40), "C15.1")
wire("C15.2", "R25.1")
wire("R25.2", (1900, 40), "VR3.3")
wire("VR3.2", (1880, 120))
label("effect-out", (1880, 120))
label("GND", "RPD1.2", "D1.K", "D2.A", "VR3.1", "C16.2")


# --- Bypass board (Aion's TRUE BYPASS / BUFFER SLIDE SWITCH), joined by labels.
# SW1 is a 3PDT on-on (Aion fits a 4PDT slide, one pole unused; its lugs 1-9 are our A1-C3).
# SW2 is the 3PDT
# footswitch: Aion's FSA and FSC, with FSB lighting the LED as on every 3PDT board. Our
# footswitch lug 1 is On, so Aion's A1/A3 and C1/C3 trade names here.
SLIDE = {"type": "switch", "kind": "3pdt", "label": "Bypass mode",
         "names": ["True bypass", "Buffered"], "position": 1}  # fmt: skip
STOMP = {"type": "switch", "kind": "footswitch", "label": "Bypass"}
BX = 1560
for i, pole in enumerate("cba"):
    part(f"SW1{pole.upper()}", SLIDE["type"], (BX, 340 + 120 * i), pole=pole,
         **{k: v for k, v in SLIDE.items() if k != "type"})  # fmt: skip
stub("SW1C.C2", "pcb-in", -40)
stub("SW1C.C3", "in", 40)
stub("SW1B.B2", "bypass", -40)
stub("SW1B.B1", "in", 40)
stub("SW1B.B3", "buffer-out", 40)
stub("SW1A.A1", "effect-out", 40)
stub("SW1A.A3", "out", 40)
# R26 from the buffer meets SW1A's common; R28 holds it to ground. Aion's R27 (the effect to
# the same point) is left out (D-233)
part("R26", R, (1420, 540), V, value="68k")
part("R28", R, (1460, 620), V, value="100k")
wire("R26.2", (1420, 580))
wire((1420, 580), (1460, 580), "SW1A.A2")
wire((1460, 580), "R28.1")
label("buffer-out", "R26.1")
label("GND", "R28.2")
FX = 1860
for i, pole in enumerate("abc"):
    part(f"SW2{pole.upper()}", STOMP["type"], (FX, 340 + 120 * i), pole=pole,
         **{k: v for k, v in STOMP.items() if k != "type"})  # fmt: skip
stub("SW2A.A2", "in", -40)
stub("SW2A.A1", "pcb-in", 40)
part("LEDR1", R, (1720, 460), value="10k")  # Aion's LEDR
part("LED1", "led", (1780, 460), model="APT1608SURCK")
label("V+", "LEDR1.1")
wire("LEDR1.2", "LED1.A")
wire("LED1.K", (1820, 460), "SW2B.B2")
stub("SW2B.B1", "GND", 40, rot=270)
stub("SW2C.C2", "out", -40)
stub("SW2C.C1", "effect-out", 40)
stub("SW2C.C3", "bypass", 40)
part("IN", "guitar", (1340, 340), volume="250k")
part("OUT", "amp", (2060, 700))
label("in", "IN.out")
label("out", "OUT.in")

# Intended nets, read off Aion's schematic. Our IC1A is Aion's IC1B (pins 1-3, the gain
# stage) and our IC1B Aion's IC1A (pins 5-7, the input buffer), so pin numbers match the
# chip and Aion's voltage table. RPD1 is Aion's RPD.
INTENDED = [
    {"RPD1.1", "R1.1", "SW1C.C2", "SW2A.A1"}, {"R1.2", "C1.1"}, {"C1.2", "R2.2", "IC1B.+"},
    {"IC1B.-", "IC1B.out", "C3.1", "R5.1", "C4.1", "C2.1"},
    {"C2.2", "R4.1", "R3.1"}, {"R4.2", "R26.1", "SW1B.B3"},
    {"IN.out", "SW1C.C3", "SW1B.B1", "SW2A.A2"}, {"SW1B.B2", "SW2C.C3"},
    {"SW1C.C1"}, {"SW2A.A3"}, {"SW2B.B3"},
    {"R26.2", "R28.1", "SW1A.A2"}, {"OUT.in", "SW1A.A3", "SW2C.C2"},
    {"LEDR1.2", "LED1.A"}, {"LED1.K", "SW2B.B2"},
    {"C3.2", "R6.1", "C5.1", "R7.1"}, {"R7.2", "C16.1", "R19.1"},
    {"R6.2", "C5.2", "VR1A.1", "IC1A.+"}, {"VR1A.3", "R10.1"},
    {"R10.2", "R11.1", "C7.1"},
    {"R11.2", "C7.2", "IC1A.-", "R12.1", "C8.1"},
    {"IC1A.out", "R12.2", "C8.2", "C9.1"}, {"C9.2", "R13.1"},
    {"R13.2", "D1.A", "D2.K", "C10.1"}, {"C10.2", "C11.1", "R16.1"}, {"C11.2", "R15.1"},
    {"R16.2", "R19.2", "R17.1", "C12.1", "IC2A.-", "R20.1", "C13.1"}, {"C12.2", "R18.1"},
    {"R5.2", "C4.2", "C6.1", "R8.1", "VR1B.1"}, {"C6.2", "R9.1"},
    {"VR1B.2", "R15.2", "R17.2", "R18.2"},
    {"IC2A.out", "R20.2", "C13.2", "R22.1", "R21.1"}, {"R21.2", "VR2.3"},
    {"VR2.2", "C14.2"}, {"VR2.1", "R23.1"},
    {"R22.2", "C14.1", "IC2B.-", "R24.1"},
    {"IC2B.out", "R24.2", "R23.2", "C15.1"}, {"C15.2", "R25.1"}, {"R25.2", "VR3.3"},
    {"VR3.2", "SW1A.A1", "SW2C.C1"},
    {"R29.1", "C17.1", "Z1.K", "IC3.in", "IC1C.V+", "D3.A", "LEDR1.1"},
    {"D3.K", "D4.A", "C20.1"}, {"C20.2", "C21.1", "IC3.cap+"}, {"C21.2", "IC3.cap-"},
    {"R29.2", "R30.1", "C18.1", "R2.1", "VR1A.2", "R8.2", "R9.2", "VR1B.3", "IC2A.+",
     "IC2B.+"},
    {"D4.K", "C22.1", "IC2C.V+"}, {"IC3.out", "C19.2", "IC2C.V-"},
    {"RPD1.2", "D1.K", "D2.A", "VR3.1", "C16.2", "C17.2", "Z1.A", "R30.2", "C18.2", "IC3.gnd",
     "C22.2", "C19.1", "IC1C.V-", "R3.2", "R28.2", "SW2B.B1"},
]  # fmt: skip

BUILD_NOTES = [
    {
        "title": "Build notes (1 of 2): not on the drawing",
        "text": (
            "From Aion FX's Refractor documents.\n"
            "IC3 (LT1054, or TC1044SCPA): pin 1 to VA, as Aion wires it."
        ),
        "pos": [0, 560],
    },
    {
        "title": "Build notes (2 of 2): parts to try",
        "text": (
            "From Aion FX's build notes.\n"
            "D1, D2: the original's germaniums measure about 0.35 V at\n"
            "   5 mA (Peak Atlas DCA55). BAT41 Schottkys are drawn, as\n"
            "   Aion's; Russian D9E (or D9B, D9D, D9J, D9K, D9L) are a\n"
            "   near match. Other 1N34As don't sound the same.\n"
            "C14 6n8 or 8n2 (3n9 drawn): more treble; the best-liked mod.\n"
            "C1 390n film for bass guitar.\n"
            "C16: Aion and the original fit a 1µ tantalum (+ to R7);\n"
            "   film is drawn, the usual advice in the signal path.\n"
            "IC1 LF353 or JRC4558D, IC2 NE5532 (both TL072 drawn).\n"
            "C9, C10: 1µ film (drawn), or electrolytic as the original,\n"
            "   + towards IC1A for C9 and towards R16 for C10 (the DC sides).\n"
            "Run it as the designer meant: Gain around 9-10 o'clock,\n"
            "   Output up, into a clean valve amp."
        ),
        "pos": [600, 560],
    },
    {
        "title": "Bypass board",
        "text": (
            "Aion's true bypass / buffer slide switch, as the KTR's.\n"
            "SW1, a 3PDT on-on slide or toggle, sets Bypass mode:\n"
            "   Buffered (the original Centaur's): the input buffer\n"
            "   always runs; bypassed, it drives the output through C2,\n"
            "   R4. True bypass: in goes straight to out.\n"
            "SW2, the 3PDT footswitch (Aion's FSA, FSC; FSB lights the\n"
            "   LED through LEDR1). Here lug 1 is On, so\n"
            "   Aion's A1/A3 and C1/C3 trade names.\n"
            "R26 and R28 hold the buffer's output at ground when\n"
            "   it isn't in use, so switching doesn't pop. Aion also\n"
            "   draws R27 68k from the effect to R28: left out, as\n"
            "   in Buffered it leaked the effect in when bypassed.\n"
            "Flip both in Knobs."
        ),
        "pos": [1340, 800],
    },
]

data = {
    "schema": 27,
    "id": "klon-centaur-built",
    "name": "Klon Centaur, with footswitch",
    "version": {"major": 1, "minor": 0},
    "description": (
        "Klon Centaur Professional Overdrive (1994) as Aion FX's Refractor (document 2.0.1), "
        "the KTR's circuit drawn whole, its true or buffered bypass board and footswitch "
        "included: an input buffer, then a dual Gain pot that turns "
        "up a gain stage clipping into two diodes while it turns down a clean copy of the "
        "signal; a summing amp adds the two, then Treble and Output. An LT1054 makes 18 V and "
        "-9 V for the summing and treble amps. D1, D2 are BAT41 Schottkys, Aion's choice for "
        "the original's germaniums."
    ),
    "tags": ["overdrive"],
    "starter": True,
    "power": {"rails": {"V+": 9.0}},
    "parts": parts,
    "wires": wires,
    "labels": labels,
    "texts": BUILD_NOTES,
    "probes": {"in": "in", "out": "out"},
    "notes": {
        "part:RPD1": "Aion's RPD: the input pull-down for true bypass. The KTR added it and "
        "made R2 2M, so the input is still 1M.",
        "part:IC1B": "Input buffer (Aion's IC1A, pins 5-7), biased at VR by R2.",
        "part:IC1A": "Gain stage (Aion's IC1B, pins 1-3): non-inverting, gain set by R12 "
        "over R10, R11 and Gain A.",
        "part:VR1A": "Gain A, between the gain stage's inputs with its wiper on VR: at 0 "
        "the + input sits on VR and the stage passes nothing; turned up, it "
        "lets the signal in and raises the gain.",
        "part:VR1B": "Gain B: the clean signal's way to the summing amp (through R15, R17 "
        "and C12/R18). At 0 it carries the most clean signal; turned up, less.",
        "part:C16": "With R7 and R19, a second clean path into the summing amp: mostly "
        "lows and mids (C16 shunts the highs).",
        "part:D1": "Clipping: D1 and D2 to ground, one each way, after R13. The output "
        "of the gain stage swings far more than they let through.",
        "part:IC2A": "Summing amp: adds the clipped signal (R16), the clean ones (R19, and "
        "Gain B's share) and inverts; runs on 18 V and -9 V for headroom.",
        "part:VR2": "Treble: an active tone control around IC2B (R21, R23, C14).",
        "part:IC3": "LT1054 charge pump, doubling VA to VB (about 18 V) and inverting it to "
        "-VA (about -9 V): IC2's supply.",
        "part:Z1": "12 V zener across VA: protects the charge pump from too high a supply "
        "(the LT1054 doubles it). At 9-10 V it carries only leakage.",
        "part:R29": "R29 and R30 make VR, half of VA, the bias for every op-amp input; C18 "
        "smooths it.",
        "part:C2": "With R4, the buffered output: the input buffer's signal for the "
        "bypass board, used when bypassed in Buffered mode. R3 keeps C2 "
        "charged so switching doesn't pop.",
        "part:SW1A": "Bypass mode: Buffered or True bypass. Any 3PDT on-on, slide or toggle; "
        "Aion fits a 4PDT slide (E-Switch EG4208) with one pole unused. "
        "Aion's lugs 1-9 are A1-C3 here.",
        "part:SW2A": "The 3PDT footswitch (Aion's FSA and FSC; B lights the LED). Lug 1 "
        "is On here, so Aion's A1/A3 and C1/C3 trade names.",
        "part:R26": "R26 ties the buffer's output to R28, which holds it at ground so the "
        "footswitch doesn't pop. Aion also draws R27 68k from the effect's output "
        "to the same point; it's left out: bypassed in Buffered it leaked the "
        "effect into the output about 22 dB under the dry signal, and the Output "
        "pot already holds the effect's output at ground.",
    },
    "enclosure": {"size": "125B"},
}


def check_and_write(data: dict, intended: list[set[str]], out: Path) -> None:
    differences = net_differences(parse_circuit(data), intended)
    assert not differences, "\n".join([f"{out}: not the intended netlist", *differences])
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out, len(data["parts"]), "parts", len(data["wires"]), "wires")


check_and_write(data, INTENDED, OUT_BUILT)

# --- The plain starter: the effect and its power, no bypass board (the user, 2026-11-09:
# "one is an example of a fully built schematic and the other is the circuit i can use as
# a starter to build something new"). Cut from the built one.
BYPASS_BOX = (1300, 300, 2100, 720)
BUFFER_BOX = (290, -310, 470, -240)  # C2, R3, R4
BYPASS_REFS = {"C2", "R3", "R4", "R26", "R28", "LEDR1", "LED1",
               "SW1A", "SW1B", "SW1C", "SW2A", "SW2B", "SW2C"}  # fmt: skip


def cut(x: int, y: int) -> bool:
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in (BYPASS_BOX, BUFFER_BOX))


PLAIN_NETS = {"pcb-in": "in", "effect-out": "out"}
plain_parts = [p for p in parts if p["ref"] not in BYPASS_REFS and p["ref"] not in ("IN", "OUT")]
plain_parts += [
    {"ref": "OUT", "pos": [2000, 120], "type": "amp"},
    {"ref": "IN", "type": "guitar", "volume": "250k"},  # at the origin, its pin on "in"
]
plain_wires = [w for w in wires if not (cut(*w["from"]) or cut(*w["to"]))]
plain_wires.append({"from": [1880, 120], "to": [1980, 120]})
plain_labels = [
    dict(lb, net=PLAIN_NETS.get(lb["net"], lb["net"])) for lb in labels if not cut(*lb["pos"])
]
plain_intended = []
for group in INTENDED:
    kept = {pin for pin in group if pin.split(".")[0] not in BYPASS_REFS | {"IN", "OUT"}}
    if "RPD1.1" in kept:
        kept.add("IN.out")
    if "VR3.2" in kept:
        kept.add("OUT.in")
    if kept:
        plain_intended.append(kept)
plain_notes = {k: v for k, v in data["notes"].items() if k.split(":")[1] not in BYPASS_REFS}
plain = dict(
    data,
    id="klon-centaur",
    name="Klon Centaur",
    description=(
        "Klon Centaur Professional Overdrive (1994) as Aion FX's Refractor (document 2.0.1), "
        "the KTR's circuit: an input buffer, then a dual Gain pot that turns up a gain stage "
        "clipping into two diodes while it turns down a clean copy of the signal; a summing "
        "amp adds the two, then Treble and Output. An LT1054 makes 18 V and -9 V for the "
        "summing and treble amps. D1, D2 are BAT41 Schottkys, Aion's choice for the "
        "original's germaniums. The effect and its power only: Klon Centaur, with "
        "footswitch draws the bypass board too."
    ),
    parts=plain_parts,
    wires=plain_wires,
    labels=plain_labels,
    texts=[
        dict(
            BUILD_NOTES[0],
            text=BUILD_NOTES[0]["text"]
            + (
                "\nBypass: Aion's true / buffered board isn't drawn here; see\n"
                "   the starter Klon Centaur, with footswitch (or the Klon\n"
                "   bypass block). It takes the buffer's output through C2\n"
                "   4.7µ and R4 560R, R3 100k to ground."
            ),
        ),
        BUILD_NOTES[1],
    ],
    notes=plain_notes,
)
check_and_write(plain, plain_intended, OUT)
