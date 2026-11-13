# Formulas

The sums that come up when you design or change a pedal, each with an example you can check on a calculator. Values are written the way parts are marked: `4k7` is 4.7 kΩ, `22n` is 22 nF, `1M` is 1 MΩ.

Tools → Unit converter changes between pF, nF and µF and reads capacitor codes; Tools → Resistor colour code finds the nearest standard value to the one a sum gives you.

## Resistors in series

Resistances in a row add up:

`R = R1 + R2`

A `10k` and a `4k7` in series make 14.7 kΩ. A series resistor can only make the total bigger.

## Resistors in parallel

Side by side, the total is always smaller than the smallest one:

`R = (R1 × R2) / (R1 + R2)`

Two equal resistors in parallel make half of one: `500k` beside `500k` is 250 kΩ. A `100k` beside a `22k` is (100 × 22) / 122 = 18.0 kΩ.

### Making a 500k pot behave like a 250k

You need a 250k pot and only have a 500k. Put a `500k` resistor across the two lugs you use, not in series with it: in series it would only add.

- Used as a variable resistor (the wiper and one end), the most you now get is 500k beside 500k = 250 kΩ.
- The feel changes too. Halfway round, the pot's 250k sits beside the 500k: (250 × 500) / 750 = 167 kΩ, not the 125 kΩ a real 250k pot gives at half. The resistance rises quickly at first and flattens towards the end.

## Voltage divider

Two resistors from a voltage to ground, with the output taken between them:

`Vout = Vin × R2 / (R1 + R2)`

R1 is the top resistor, R2 the one to ground.

- Two `10k` resistors across a 9 V supply give 9 × 10 / 20 = 4.5 V: the half-supply reference most op-amp pedals bias their inputs to.
- A `100k` over a `22k` gives 9 × 22 / 122 = 1.62 V.

A divider only holds its voltage while little current is drawn from the middle. Whatever it feeds sits in parallel with R2.

## RC corner frequency

A resistor and a capacitor make a filter. Its corner, where the level is 3 dB down, is at:

`f = 1 / (2 × π × R × C)`

with R in ohms, C in farads and f in hertz.

- **Treble cut (low-pass):** the Tube Screamer's `4k7` and `47n` to ground give 1 / (2 × π × 4700 × 0.000000047) = 720 Hz.
- **Bass cut (high-pass):** an input capacitor of `22n` into a `1M` resistor gives 1 / (2 × π × 1000000 × 0.000000022) = 7.2 Hz, well below a guitar's lowest note (82 Hz), so nothing is lost.
- A `10k` with a `100n` gives 159 Hz.

Making either part ten times bigger moves the corner ten times lower. Tools → **Filter calculator…** does this sum for any two values and says what the filter does to a guitar.

## Capacitors in parallel and in series

Capacitors work the other way round from resistors.

- In parallel they add: `C = C1 + C2`. A `100n` beside a `47n` is 147 nF.
- In series: `C = (C1 × C2) / (C1 + C2)`. Two `100n` in series make 50 nF.

## A capacitor's impedance

A capacitor passes high frequencies more easily than low ones. At a frequency f it stands in the way like a resistance of:

`Xc = 1 / (2 × π × f × C)`

A `100n` capacitor is 1.59 kΩ at 1 kHz, ten times that at 100 Hz, and a tenth of it at 10 kHz.

## LED resistor

The resistor sets the LED's current:

`R = (Vsupply − Vled) / I`

A red LED drops about 2 V. On 9 V, for 2 mA: (9 − 2) / 0.002 = 3.5 kΩ; use a `3k3` or `3k9`. The common `4k7` gives (9 − 2) / 4700 = 1.5 mA, plenty for a modern LED. Blue and white LEDs drop about 3 V.

## Gain from two resistors

An op-amp stage's gain is set by its feedback resistors.

**Non-inverting** (the signal goes to the + input; Rf is from the output to the − input, Rg from the − input to ground or the reference):

`gain = 1 + Rf / Rg`

The Tube Screamer's drive stage has Rg = `4k7` and Rf = `51k` plus the 500k Drive pot:

- Drive at minimum: 1 + 51 / 4.7 = 11.9 times (21.5 dB).
- Drive at maximum: 1 + 551 / 4.7 = 118 times (41.5 dB).

**Inverting** (the signal goes through Rin to the − input; Rf is from the output to the − input):

`gain = −Rf / Rin`

The minus sign means the output is upside down; the size of the gain is Rf / Rin. A `100k` over a `10k` gives 10 times (20 dB).

## Decibels

Decibels compare two voltages:

`dB = 20 × log10(Vout / Vin)`

| Times | dB |
|---|---|
| 2 | +6 |
| 10 | +20 |
| 100 | +40 |
| 0.5 | −6 |
| 0.1 | −20 |

Gains in a row multiply; their decibels add.

## Ohm's law and power

`V = I × R`  and  `P = V × I`

- A pedal drawing 20 mA from 9 V uses 9 × 0.02 = 0.18 W.
- A `100` Ω resistor in the supply line with 20 mA through it drops 0.02 × 100 = 2 V and turns 0.02 × 0.02 × 100 = 0.04 W into heat, well inside a ¼ W resistor.
