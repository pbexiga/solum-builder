# Tools and help sheets

Small calculators and reference sheets, from the Tools and Help menus. Each opens over the sheet; Esc or **Close** shuts it.

## Unit converter

Tools → **Unit converter…**. Type a value the way it's written on a schematic (`22n`, `4k7`, `2M2`) or in plain numbers (`0.000000022`, `4700`), and pick the **Quantity**: capacitance, resistance, inductance, frequency, voltage, current or time. It shows the value in every unit (a capacitance in pF, nF and µF) and whether it's a standard value.

For a capacitor it also reads and writes the **code printed on the part**: `223` is 22 nF, `104K` is 100 nF ±10 %, `4p7` is 4.7 pF.

## Resistor colour code

Tools → **Resistor colour code…** works both ways: type a **Value** to see its bands, or pick the bands (**4 bands** or **5 bands**) to read the value and tolerance. It says whether the value is a standard one (E6, E12, E24…), and if not, the nearest standard values each side. Read a resistor from the end where the bands bunch together; the tolerance band (often gold, or brown on 1 % parts) sits apart at the other end.

## Calculators

Tools → **Calculators…** holds the sums a builder does by hand, each worked out as you type, with the numbers shown. Pick one at the top; the one you used last opens next time. Type values the way they're written on a schematic (`100k`, `47n`, `2M2`).

- **Filter: the corner from R and C.** A resistor and a capacitor make a filter: pick **High-pass** (the capacitor in the signal's path, the resistor to ground: a bass cut) or **Low-pass** (the resistor in the path, the capacitor to ground: a treble cut) and type both. It shows the corner, where the level is 3 dB down, with the sum written out (`1 / (2 × π × 100 kΩ × 1 µF) = 1.59 Hz`), how far the filter turns down a guitar's lowest note (82 Hz), 1 kHz and 5 kHz, and what that means in a sentence. Fill in **Compare with** (either value; a blank one stays the same) to see a second filter beside the first and how far the corner moved: 1µ into 100k passes the whole guitar, and 10µ puts the corner ten times lower still.
- **Filter: a part for the corner you want.** Type the corner and one of the two parts, leave the other blank, and pick which standard values you have. It works out the blank part, the nearest value you can buy, and where that value really puts the corner: a 100 Hz bass cut into a 1M input wants 1.59 nF, so 1n5, which gives 106 Hz.
- **Voltage divider.** The supply and two resistors give the voltage in the middle, the current the pair draws, and what the middle looks like to whatever it feeds (the two resistors in parallel), with the load it holds within 1 % and 10 % for. Give the **Load on the middle** to see how far it pulls the voltage down: 9 V through 10k and 10k is 4.5 V, and a 100k load drops it to 4.29 V.
- **Parallel and series.** List resistors or capacitors (`10k, 22k`) to see them in series and in parallel. Or type a value you need under **Make this value**: it gives the nearest single standard value and the nearest pair each way, with how far each lands. 6k5 isn't a standard value; 4k7 and 1k8 in series make it exactly.
- **Decibels.** Type a level in dB or a ratio in times and the other fills in: +20 dB is ten times, +6 dB twice, −6 dB half. Give a **Signal in** to see what comes out: 300 mV through +20 dB is 3 V.

The sums themselves are on [Formulas](formulas.md).

## Help sheets

- Help → **Documentation…**: this guide, in a large window with a search across every page. The pop-out button beside **Close** (a square with an arrow leaving it) shows the page you're on in its own tab or window.
- Help → **Formulas…**: the sums a pedal builder needs, each with a worked pedal example: [Formulas](formulas.md).
- Help → **Choosing capacitors…**: which kind of capacitor goes where (film, C0G ceramic, other ceramics, electrolytic, tantalum), their usual values and what to watch out for. The kind doesn't change the simulation; it's for the build and the advice in Problems.
- Help → **Resistor colour code and values…**: the colour chart, how values are written (`4k7`, `0R47`, `2M2`, `100p`, `2u2`), and the standard series of values (E12, E24, E96).
- Help → **Hot keys…**: every keyboard and mouse shortcut on one page.
- Help → **About Solum Builder…**: the version, the simulator's, and where the classic circuits come from.

Tools → **Parts and datasheets…** and **Add a model…** are on the [Models](models.md) page.
