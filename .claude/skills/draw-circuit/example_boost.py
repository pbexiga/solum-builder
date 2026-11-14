"""The worked example for the draw-circuit skill: a clean op-amp boost, drawn by script.

A TL071 as a non-inverting amplifier biased at half the supply; Gain sets the feedback
(gain 1 + (R4 + VR1) / R3: 2 to 23, 6 to 27 dB), Volume follows. Values worked for this
example, not taken from a pedal.

Run in the dev image: make run CMD="python .claude/skills/draw-circuit/example_boost.py"
"""

import sys
from pathlib import Path

from solum.circuit.draw import Drawing, net_differences
from solum.circuit.io import save_circuit

OUT = Path("scratch/drawn/opamp-boost.json")

# 1. The netlist meant: a set of pins per net. Written first, from the design, and never
#    changed to make the drawing pass.
INTENDED = [
    {"IN.out", "R1.1", "C1.1"},  # in
    {"C1.2", "R2.2", "IC1.+"},  # the op-amp's + input, biased at VREF through R2
    {"IC1.-", "R3.2", "R4.1"},  # the feedback node
    {"R3.1", "C2.1"},
    {"R4.2", "VR1.1"},
    {"IC1.out", "VR1.2", "VR1.3", "C3.1"},  # Gain as a variable resistor: wiper to one end
    {"C3.2", "VR2.3"},
    {"VR2.2", "OUT.in"},  # out
    {"R5.1", "C5.1", "IC1.V+"},  # V+
    {"R5.2", "R6.1", "C4.1", "R2.1"},  # VREF
    {"R1.2", "C2.2", "VR2.1", "R6.2", "C4.2", "C5.2", "IC1.V-"},  # GND
]

d = Drawing()
V = 90  # upright: pin 1 on top

# 2. The signal, left to right along y = 0
d.part("IN", "guitar", (0, 0), volume="250k")
d.part("R1", "resistor", (60, 40), V, value="1M", note="Pull-down: no pop from C1.")
d.part("C1", "capacitor", (120, 0), value="100n", kind="film")
d.part("R2", "resistor", (200, -40), V, value="1M", note="Biases the + input at VREF.")
d.part("IC1", "opamp", (300, -20), model="TL071")
d.wire("IN.out", "C1.1")
d.wire((60, 0), "R1.1")
d.wire("C1.2", "IC1.+")
d.wire("R2.2", (200, 0))
d.label("in", "IN.out")
d.label("GND", "R1.2")
d.label("VREF", "R2.1")
d.label("V+", "IC1.V+")
d.label("GND", "IC1.V-")

# 3. Feedback above the op-amp: R4 and Gain from the output back to the - input, R3 and
#    C2 from there to ground
d.part("R3", "resistor", (160, -120), value="4k7")
d.part("C2", "capacitor", (100, -80), V, value="1µ", kind="film",
       note="With R3, gain falls to 1 below 34 Hz.")  # fmt: skip
d.part("R4", "resistor", (300, -120), value="4k7")
d.part("VR1", "pot", (380, -120), value="100k", taper="B", rotation=0.5, label="Gain")
d.wire("IC1.-", (220, -40), (220, -120), "R4.1")
d.wire((220, -120), "R3.2")
d.wire("R3.1", (100, -120), "C2.1")
d.wire("R4.2", "VR1.1")
d.wire("VR1.3", (440, -120), (440, -20))
d.wire("VR1.2", (380, -160), (440, -160), (440, -120))
d.wire("IC1.out", (440, -20))
d.label("GND", "C2.2")

# 4. Output: C3, then Volume (turned so its wiper points down)
d.part("C3", "capacitor", (500, -20), value="1µ", kind="film")
d.part("VR2", "pot", (600, -20), 180, value="100k", taper="A", rotation=1.0, label="Volume")
d.part("OUT", "amp", (740, 60))
d.wire((440, -20), "C3.1")
d.wire("C3.2", "VR2.3")
d.wire("VR2.2", (600, 60), "OUT.in")
d.stub("VR2.1", "GND", dx=40)
d.label("out", "OUT.in")

# 5. The supply, at the top: V+ filtered by C5, halved by R5 and R6 to VREF, held by C4
S = -400
d.part("C5", "capacitor", (100, S + 40), V, value="100µ", kind="electrolytic", rating_v=16.0)
d.part("R5", "resistor", (200, S + 40), V, value="10k")
d.part("R6", "resistor", (200, S + 120), V, value="10k")
d.part("C4", "capacitor", (280, S + 120), V, value="47µ", kind="electrolytic", rating_v=16.0)
d.wire("C5.1", (100, S), (200, S), "R5.1")
d.wire("R5.2", "R6.1")
d.wire((200, S + 80), (280, S + 80), "C4.1")
d.label("V+", (100, S))
d.label("VREF", (280, S + 80))
d.label("GND", "C5.2", "R6.2", "C4.2")

# 6. The file: checked against the netlist meant, then written
circuit = d.circuit(
    "Op-amp boost",
    description="A clean boost: a TL071 non-inverting amplifier, gain 2 to 23 (6 to 27 dB).",
    tags=["boost"],
    power={"rails": {"V+": 9.0}},
    probes={"in": "in", "out": "out"},
    enclosure={"size": "125B"},
    net_notes={"VREF": "4.5 V bias from the R5/R6 divider, held steady by C4."},
)
differences = net_differences(circuit, INTENDED)
if differences:
    sys.exit("\n".join(["The drawing isn't the netlist meant:", *differences]))
OUT.parent.mkdir(parents=True, exist_ok=True)
save_circuit(circuit, OUT)
print(f"wrote {OUT}: {len(circuit.parts)} parts, {len(circuit.wires)} wires")
