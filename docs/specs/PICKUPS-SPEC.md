# Pickups by any three of R, L, C, peak and Q — spec

## Goal
A pickup should be enterable the way it's published or measured (the user's friend, 2026-11-11; the user, 2026-11-16). Some people have R, L and C; makers' sheets give the DC resistance, the inductance and the resonant peak; the friend has the peak and Q. The guitar input's form shows all five and takes any three that fix the pickup (D-363).

## Before
The guitar input (IN) had a pickup from `library/guides/pickups.yaml` (five measured ones, from UIUC) or *Your own values*: Coil R, Coil L and Coil C only (`Pickup`: `r`, `l`, `c`, `kind`; D-096). The model is a series R–L with the winding's C across it, and the netlist uses only R, L and C; that hasn't changed.

## The arithmetic
With ω₀ = 2π·peak, the series R–L with C across has, to the usual approximation (good while Q is above about 2; the guide's own C uses it):
- peak = 1 / (2π·√(LC))
- Q = ω₀·L / R

Three unknowns and two relations, so **any three of the five fix the other two, except L, C and peak** (L and C already give the peak, so R is left open):

| Set | Worked out |
|---|---|
| R, L, C | peak, Q |
| R, L, peak | C = 1/(ω₀²L), Q |
| R, C, peak | L = 1/(ω₀²C), Q |
| R, L, Q | ω₀ = Q·R/L, then C |
| R, C, Q | L = Q²R²C, then peak |
| R, peak, Q | L = Q·R/ω₀, then C |
| L, peak, Q | R = ω₀L/Q, then C |
| C, peak, Q | L = 1/(ω₀²C), then R |
| L, C, Q | peak, then R = ω₀L/Q |
| L, C, peak | refused: L and C already give the peak |

Peak and Q alone can't do it: scaling R and L up and C down by the same factor keeps both but changes how hard the pickup loads the pedal. R is the one recommended: makers always publish it, and a multimeter across the jack reads it.

## The form
- With *Your own values*, and with a measured pickup, the pickup shows **five boxes: Coil R, Coil L, Coil C, Peak, Q**.
- **Three are set, two are worked out.** A set box shows what was typed; a worked-out box is empty with its value as a muted placeholder (`≈ 151p`), updated as the set ones change.
- **Typing into a worked-out box makes it set; the set box typed least recently becomes worked out**, unless that would leave L, C and peak, when the next oldest goes (R, L, C set and a peak typed keeps R, C, peak). Clearing a box un-sets it.
- **A line under the boxes** says what's set and worked out, or what's still needed:

  | Typed | The line | The boxes |
  |---|---|---|
  | nothing | *Type any three of the five. R is the easiest: a multimeter across the jack.* | all open |
  | R | *R set. Two more: any of L, C, peak or Q.* | all open |
  | R, peak | *R and peak set. One more: L, C or Q.* | all open |
  | L, C | *L and C set. One more: R or Q. Not the peak: L and C give it.* | Peak dimmed, its title says why |
  | L, peak | *L and peak set. One more: R or Q. Not C: L and the peak give it.* | C dimmed |
  | C, peak | *C and peak set. One more: R or Q. Not L: the peak and C give it.* | L dimmed |
  | a valid three | *Set: R, peak, Q · worked out: L, C* | the other two show ≈ their values |
  | a fourth | *Set: peak, Q, L · worked out: R, C (R was set first, so it's worked out now)* | updated |

  With two set and neither of them R, the line adds *R is the easiest: a multimeter across the jack.* Typing into a dimmed box is refused with its reason.
- **Hints:** R: *The DC resistance: a multimeter across the guitar's jack reads it.* Peak: *Unloaded: the coil alone, without the guitar's pot and cable (the app adds those).* The form's ⓘ: *Type any three of the five; the other two are worked out. The three you typed last are kept.*, with what the peak and Q mean.
- **Ranges:** a peak up to 30 kHz, a Q from 0.5 to 200, everything above zero; refused in plain English as other values are. Worked-out values aren't range-checked.
- A measured pickup shows its peak and Q worked out (the Strat: 8.11 kHz, Q 20.4). Editing a box turns it into your own values on Apply, as before.
- A divider above Cable separates the pickup's boxes from the cable, volume pot and jack.

## Who works it out
One owner, on the server: `solum/circuit/pickup.py` (`solve`, `pickup_form`, `check_set`). The form (`web/pickup-form.js`) posts the boxes typed, oldest first, to `POST /api/pickup` 150 ms after typing pauses and again on Apply, and shows the answer: which three are set, the worked-out values, the dimmed box, the line, and R, L and C as the file keeps them. The browser keeps only the typing order, and only an answer for the boxes as they are now can refuse a keystroke (D-363).

## The file (schema v32)
- `Pickup` keeps `r`, `l` and `c` (all the simulation reads) and gains `set`: the three typed, as typed, in typing order, e.g. `{"r": "8k2", "peak": "5k2", "q": "2.1"}`. Reopening shows exactly what was typed. A worked-out R, L or C is stored to four figures.
- No `set` (a measured pickup, an older file, or R, L and C typed) reads as R, L and C set. A `set` that doesn't give the file's R, L and C within 1 % is refused. Migration v31 → v32 changes nothing; a test loads a v31 file.

## The guide's pickups
Each measured pickup's C was worked out from its measured unloaded peak as 1 / ((2π·peak)²·L); a unit test checks the stored C gives back the measured peak within 1 %. The form shows each one's peak and Q worked out. Guide: *Your own pickup* in `getting-audio.md`, the IN form in `drawing.md`, the sums in `formulas.md`.

## Out of scope
- A loss resistor so a real pickup's lower measured Q can be matched together with R, L and peak (four numbers; a schema change of its own). Later, if it's needed.
- A switch for a peak measured loaded (with pot and cable) and backing the load out. The hint says unloaded.
- Pickup types with assumed values for a missing R.
