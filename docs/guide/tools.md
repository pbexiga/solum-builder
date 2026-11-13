# Tools and help sheets

Small calculators and reference sheets, from the Tools and Help menus. Each opens over the sheet; Esc or **Close** shuts it.

## Unit converter

Tools → **Unit converter…**. Type a value the way it's written on a schematic (`22n`, `4k7`, `2M2`) or in plain numbers (`0.000000022`, `4700`), and pick the **Quantity**: capacitance, resistance, inductance, frequency, voltage, current or time. It shows the value in every unit (a capacitance in pF, nF and µF) and whether it's a standard value.

For a capacitor it also reads and writes the **code printed on the part**: `223` is 22 nF, `104K` is 100 nF ±10 %, `4p7` is 4.7 pF.

## Resistor colour code

Tools → **Resistor colour code…** works both ways: type a **Value** to see its bands, or pick the bands (**4 bands** or **5 bands**) to read the value and tolerance. It says whether the value is a standard one (E6, E12, E24…), and if not, the nearest standard values each side. Read a resistor from the end where the bands bunch together; the tolerance band (often gold, or brown on 1 % parts) sits apart at the other end.

## Filter calculator

Tools → **Filter calculator…**. A resistor and a capacitor make a filter: pick **High-pass** (the capacitor in the signal's path, the resistor to ground: a bass cut) or **Low-pass** (the resistor in the path, the capacitor to ground: a treble cut) and type both values. It shows the corner, where the level is 3 dB down, with the sum written out (`1 / (2 × π × 100 kΩ × 1 µF) = 1.59 Hz`), how far the filter turns down a guitar's lowest note (82 Hz), 1 kHz and 5 kHz, and what that means in a sentence. Fill in **Compare with** (either value; a blank one stays the same) to see a second filter beside the first and how far the corner moved: 1µ into 100k passes the whole guitar, and 10µ puts the corner ten times lower still. The sum itself is on [Formulas](formulas.md#rc-corner-frequency).

## Help sheets

- Help → **Documentation…**: this guide, in a large window with a search across every page. The pop-out button beside **Close** (a square with an arrow leaving it) shows the page you're on in its own tab or window.
- Help → **Formulas…**: the sums a pedal builder needs, each with a worked pedal example: [Formulas](formulas.md).
- Help → **Choosing capacitors…**: which kind of capacitor goes where (film, C0G ceramic, other ceramics, electrolytic, tantalum), their usual values and what to watch out for. The kind doesn't change the simulation; it's for the build and the advice in Problems.
- Help → **Resistor colour code and values…**: the colour chart, how values are written (`4k7`, `0R47`, `2M2`, `100p`, `2u2`), and the standard series of values (E12, E24, E96).
- Help → **Hot keys…**: every keyboard and mouse shortcut on one page.
- Help → **About Solum Builder…**: the version, the simulator's, and where the classic circuits come from.

Tools → **Parts and datasheets…** and **Add a model…** are on the [Models](models.md) page.
