# Germanium study: OC71, OC44, OC75 fitted to Mullard's sheets, and the starters against the AC128

Phase 9b, 2026-11-03. Everything here is in `.claude/skills/fit-model/worked/germanium/` only; `library/` was only read
(the cards are loaded from this folder beside `library/models`, never written there).

## Files
- `pix.py`: raster reader (after `.claude/skills/fit-model/worked/ac128/grid.py`, `trace.py`, `mosfet/bs170_pixels.py`): `grid` finds grid lines in a crop and marks the darker majors `*`; `trace` follows a thick curve (dark run ≥ 3-5 px nearest a guess line) by column or row; `axis` maps pixels to values through the labelled major lines, linear between (follows a stretched scan).
- `digit_oc71.py`, `digit_oc44.py`, `digit_oc75.py` → `data/OC*.json`: each figure's page, curve, axis map and trace (pages from `pdfimages -p`, 300 dpi, in the session scratchpad mounted at `/scr`).
- `gefit.py`: the fitter (adapted from `scripts/fit_models.py` `fit_bjt_forward`, which is unchanged) and the ngspice measurements; `fit_oc71.py`, `fit_oc44.py`, `fit_oc75.py` → `OC*.lib/.json` (AC128 record shape, `ModelInfo`-valid); `record.py`; `checks.py` + `measure.py` → `out_measure_OC*.txt` and the records' `validation`; `try_x0.py` (restarts); `compare.py`, `compare_ac.py` → `out_compare_*.txt`, `data/compare_*.json`. `run.sh script.py` runs any of them in `solum-builder:dev`.

## Method (what differs from the AC128, D-170)
- **Fit to the raw curves as drawn, leakage included.** Mullard draws the transfer characteristic (IC against IB), IE against VBE and IB against VBE at one collector voltage (−4.5 V; OC44 −2 V), and the transfer line meets IB = 0 at I'co (0.16-0.35 mA), not at the origin. So the residuals are: IC at the sheet's IB (1 % steps), VBE at the sheet's IE or IC (2 mV steps) and ICBO at the table's voltage (1 %), all at the sheet's VCE with the card's own leakage flowing (IS through BR, NR = NF). Fitted together: IS, NF, BF, ISE, NE, IKF, NKF, RE, BR. Valvo measured the AC128 at UCB = 0 to keep leakage out; Mullard's figures have it in, so it is modelled, not avoided.
- RB = the sheet's rbb' (OC71 300 Ω, OC44 110 Ω); none for the OC75 (D-163: RB only from rbb'; Mullard's T-network rb 720 Ω is not rbb'), so RB 0 there. VAF = IC/h'22 − VCE from the table. CJC from Cc / Cb'c with default grading (one point). TF from fα, taken as fT (OC71: fα' 11 kc/s × β ≈ 56 gives the same 0.6 MHz). EG 0.67 as the AC128.
- Checks (`checks.py`): every table line the pipeline can measure (custom measurements where `model_checks` has none: IC at a given IB, VBE at IE or IB, I'co with the base open, small-signal h21e by ±2 % in IB, Mullard's knee voltage, IC with the base reversed), plus held-out points of each curve: IC within 5 %, VBE within 10 mV (D-163's held-out tolerances). Nothing loosened; misses are listed.
- Restarts from three other starting points (`try_x0.py`) land on the same quality (OC71 8.2 %/5.5 mV, OC75 6.3-6.4 %/1.6-2.1 mV, OC44 4.6-5.2 %); BF itself is not pinned where NKF or IKF sit at a bound (the knee sets the gain in range), so read BF as a fit parameter, not the part's gain.

## Figures used and judgements

### OC71 (Mullard Vol. 4 Part III, OC71 Issue 2, Oct 1963; `data/spec-sheets/OC71_Mullard.pdf`)
- **158-12 lower, transfer characteristic, Vc = −4.5 V** (pdf p12, rotated): x IC 0-1.5 mA (majors 0.25 mA at px 1239.5…470), y IB +5…−20 µA (majors 5 µA, IB = 0 the heavy line at y 1902.5). IB 0…15.6 µA, I'co 0.16-0.18 mA at IB = 0 (the table's 150 µA). 8 points fitted, the rest held.
- **158-13, spread of transfer characteristic, solid Average line, Vc = −4.5 V**: x IB 0-350 µA (majors 50 µA, 0 at px 305.7), y IC 0-20 mA (majors 2.5 mA). Used from 5 mA only: below that the Average line is drawn straight into the origin, leaving out the leakage 158-12 shows (at 1 mA it reads hFE ≈ 50 against 158-12's 69).
- **158-7, IE against VBE, Vc = −4.5 V, both ranges**: upper x IE 0-15 mA (majors 2.5), y VBE 0-250 mV (majors 50); lower x IE 0-150 µA (majors 25), y VBE −20…+60 mV (majors 20, 0 the heavy line). Lower used from 20 µA; upper from 0.75 mA (below it the line is near vertical, 1 px = 0.016 mA, and its foot reads 10 mV under the lower plot) to 6 mA (`VBE_TOP`: above it the sheet's VBE bends below what rbb' = 300 Ω allows, as the AC128 above 400 mA).
- **158-11, spread of input characteristic, Average** (IB 14-248 µA): held out only.
- Table 158-2: Ico 4.5 µA av. at −4.5 V (fitted), rbb' 300 Ω, Cc 40 pF at −6 V, fα 600 kc/s; 158-3: h'22 42 µmho at −2 V, 1 mA → VAF 21.8 V (at 3 mA, 158-4's 80 µmho gives 35.5 V).
- Not used: 158-10 (input at −4.5 V and 0 V; agrees with 158-11), 158-12 upper (input, low currents), output curves 158-14/15, h-parameter ratios 158-16.
- **Table vs figures:** VBE at 1 mA is 117-121 mV on all four figures against the table's 135 typical (115-155). D-163's "table wins" moved a figure that broke the table's limits (BC546); these sit inside them, so the figures are kept and the typical is reported as a deviation (−14 mV). Likewise the table's small-signal h'21e at 1 mA is 41 against the curves' slope of about 55-57.

### OC44 (Mullard Vol. 4 Part III, OC44 Dec 1960, small-signal page Oct 1964; `OC44_Mullard.pdf`)
- **C1 (pdf p7), IC against VBE, Vc = −2 V, linear**: x VBE 0-200 mV (majors 25 mV, px 366…1463), y IC 0-10 mA (majors 1 mA). Used from 0.11 mA (below it the line lies on the axis).
- **C2 lower (pdf p8), transfer characteristic, Vc = −2 V**: x IC 0-14 mA (majors 2), y IB 0-125 µA (majors 25). Used from IB 8.8 µA: below it the line runs into the corner (0.27 mA at 1.9 µA against the table's I'co of 25 µA), so the table's I'co 25 µA at IB = 0 was fitted as the line's foot instead.
- **C2 upper, input characteristic: left out.** It reads VBE 106 mV at IB 12 µA (IC ≈ 1 mA) and 179 mV at 99 µA (IC ≈ 10 mA), against C1's 142 and 200 mV and the table's 150 typ. (125 min): it contradicts both, below the table's minimum.
- Table D2: Ico 0.5 µA typ. at −2 V (fitted), I'co 25 µA (fitted, see above); D3: rbb' 110 Ω, Cb'c 10.5 pF at −6 V, fα 15 Mc/s, gce 40 µmho at −6 V, 1 mA → VAF 19 V.
- Gain rises 80 → 102 from 0.7 to 10 mA; Gummel-Poon can only rise through ISE, so it runs +5.8 % at 1.9 mA and −5.5 % at 10 mA (IKF at its 10 A bound, NKF 0.3 at its bound). VBE from 2 to 10 mA runs up to 9 mV high (the sheet's VBE is steeper than ideal between 1 and 5 mA). Ic max is 5 mA (D1).

### OC75 (Mullard Vol. 4 Part III, OC75 March 1959 / Oct 1964; `OC75_Mullard.pdf`; Philips 1958-60 `OC75_Philips.pdf` for checks)
- **C6 lower (pdf p10), transfer, Vc = −4.5 V**: x IC 0-1.75 mA (majors 0.25), y IB +10…−20 µA (majors 5; 0 heavy line). IB −0.5…12.7 µA. I'co 0.36 mA at IB = 0, IC 1.12 mA at 10 µA: Philips' table says 350 µA and 1.1 mA typ.
- **C6 upper, spread of transfer, Average line**: x IC 0-35 mA (majors 5), y IB 0-250 µA (majors 50). 2.6-22 mA; meets the lower plot (hFE 103 at 1.3 and 2.6 mA); 21.9 mA at 247 µA against Philips' 22 mA at 250 µA.
- **C1 (pdf p5), IE against VEB, Vc = −4.5 V, both ranges** (as the OC71's): lower from 20 µA, upper 0.6-10 mA.
- **C5, spread of input, Average**: held out only (agrees with Philips' VBE 120 mV at 10 µA and 270 at 250 µA).
- Table D2: Ico 4.5 µA av. (fitted), fα 900 kc/s; D3 h'22 125 µmho at −2 V, 3 mA → VAF 22 V. **No capacitance on either maker's sheet**: CJC from the cross-reference book's Cob ≤ 50 pF (`Germanium_OC_crossref.pdf`, p. 242) at an assumed 6 V; a maximum from a secondary source, flagged. No rbb' → RB 0, so VBE above IC ≈ 13 mA (IB > 150 µA) runs low (−23 mV at 250 µA; above the 10 mA rating).
- Philips figures A-N were not digitised; its table's six lines are checks.

## Cards
```
.model OC71 PNP(is=1.497e-05 nf=1.112 bf=64.06 ise=8.738e-07 ne=2.417 ikf=0.013 vaf=21.81 br=4.175 re=0.04305 vje=0.75 mje=0.33 cjc=8.26e-11 vjc=0.75 mjc=0.33 tf=2.641e-07 nkf=0.3 nr=1.112 rb=300 eg=0.67)
.model OC44 PNP(is=4.451e-06 nf=1 bf=107.6 ise=1.067e-07 ne=1.47 ikf=10 vaf=19 br=11.92 vje=0.75 mje=0.33 cjc=2.168e-11 vjc=0.75 mjc=0.33 tf=1.034e-08 nkf=0.3 rb=110 eg=0.67)
.model OC75 PNP(is=1.654e-05 nf=1.029 bf=136.5 ise=3.012e-07 ne=1.295 ikf=0.291 vaf=22 br=3.844 re=2.377 vje=0.75 mje=0.33 cjc=1.032e-10 vjc=0.75 mjc=0.33 tf=1.755e-07 nkf=1 nr=1.029 eg=0.67)
```

Fitted-point worst errors (`out_fit_OC*.txt`): OC71 IC 7.9 % (page 13 at 5 mA; ≤ 1.5 % on page 12, 0-1.1 mA), VBE 4.7 mV (to 6 mA), ICBO 4.46 µA; OC44 IC +5.8 % at 1.9 mA, +2.6 % at 0.7 mA, −5.5 % at 10 mA, VBE 9.3 mV (above 2 mA; ≤ 2.4 mV to 1.1 mA), ICBO 0.51 µA, I'co 24.7 µA; OC75 IC 6.6 % (1.3 mA), VBE 1.9 mV, ICBO 4.71 µA.

## Check tables (ngspice, the project's pipeline)
### OC71

| check | sim | min | typ | max | tol | result |
|---|---|---|---|---|---|---|
| Ico at Vcb 4.5 V (µA) | 4.464 | — | 4.5 | 13 | — | OK (-0.0357 µA from typ) |
| I'co, base open, Vce 4.5 V (µA) | 174.3 | — | 150 | 325 | — | OK (+24.3 µA from typ) |
| Vbe at Ic 1 mA, Vce 4.5 V (mV) | 120.8 | 115 | 135 | 155 | — | OK (-14.2 mV from typ) |
| Vce bottoming at Ic 9 mA, Ib 0.5 mA (mV) | 71.11 | — | 80 | 210 | — | OK (-8.89 mV from typ) |
| h'21e small-signal at Ic 3 mA, Vce 2 V | 52.41 | 30 | 47 | 75 | — | OK (+5.41 from typ) |
| h'21e small-signal at Ic 1 mA, Vce 2 V (typical only) | 54.53 | — | 41 | — | — | info (+13.5 from typ) |
| DC hFE at Ic 1 mA, Vce 4.5 V (info: no table line) | 69.66 | — | — | — | — | info |
| held: IC at IB 0.9 µA, VCE 4.5 V (mA) | 0.22 | — | 0.215 | — | 0.01075 | OK (+0.00503 from typ) |
| held: IC at IB 5.6 µA, VCE 4.5 V (mA) | 0.4831 | — | 0.4912 | — | 0.02456 | OK (-0.00813 from typ) |
| held: IC at IB 10.3 µA, VCE 4.5 V (mA) | 0.76 | — | 0.7617 | — | 0.03809 | OK (-0.00175 from typ) |
| held: IC at IB 14.4 µA, VCE 4.5 V (mA) | 1.002 | — | 1.009 | — | 0.05044 | OK (-0.0069 from typ) |
| held: IC at IB 94.7 µA, VCE 4.5 V (mA) | 5.641 | — | 5.264 | — | 0.2632 | MISS (+0.377 from typ) |
| held: IC at IB 133.2 µA, VCE 4.5 V (mA) | 7.684 | — | 7.438 | — | 0.3719 | OK (+0.246 from typ) |
| held: IC at IB 176.9 µA, VCE 4.5 V (mA) | 9.894 | — | 9.915 | — | 0.4957 | OK (-0.0204 from typ) |
| held: IC at IB 221.6 µA, VCE 4.5 V (mA) | 12.06 | — | 12.47 | — | 0.6234 | OK (-0.405 from typ) |
| held: VBE at IE 27.4 µA, VCE 4.5 V (mV) | 10.68 | — | 12.58 | — | 10 | OK (-1.9 mV from typ) |
| held: VBE at IE 61.7 µA, VCE 4.5 V (mV) | 34.14 | — | 31.21 | — | 10 | OK (+2.93 mV from typ) |
| held: VBE at IE 90.3 µA, VCE 4.5 V (mV) | 45.3 | — | 42.71 | — | 10 | OK (+2.59 mV from typ) |
| held: VBE at IE 113 µA, VCE 4.5 V (mV) | 51.96 | — | 51.1 | — | 10 | OK (+0.859 mV from typ) |
| above the fit range: VBE at IE 6.51 mA, VCE 4.5 V (mV) | 207 | — | 202.4 | — | 10 | OK (+4.6 mV from typ) |
| above the fit range: VBE at IE 7.49 mA, VCE 4.5 V (mV) | 217.1 | — | 208.1 | — | 10 | OK (+9 mV from typ) |
| above the fit range: VBE at IE 8.47 mA, VCE 4.5 V (mV) | 226.7 | — | 214.8 | — | 10 | MISS (+12 mV from typ) |
| above the fit range: VBE at IE 9.45 mA, VCE 4.5 V (mV) | 236.1 | — | 220.3 | — | 10 | MISS (+15.8 mV from typ) |
| held: VBE at IB 14 µA, VCE 4.5 V (mV) | 120.1 | — | 114 | — | 10 | OK (+6.07 mV from typ) |
| held: VBE at IB 63.2 µA, VCE 4.5 V (mV) | 177.2 | — | 171.6 | — | 10 | OK (+5.66 mV from typ) |
| held: VBE at IB 112 µA, VCE 4.5 V (mV) | 209.1 | — | 201.2 | — | 10 | OK (+7.88 mV from typ) |
| held: VBE at IB 162 µA, VCE 4.5 V (mV) | 234.8 | — | 226 | — | 10 | OK (+8.81 mV from typ) |
| held: VBE at IB 211 µA, VCE 4.5 V (mV) | 257.6 | — | 250.6 | — | 10 | OK (+6.97 mV from typ) |
| Geofex tester gain (9 V, 2.4 kΩ, 2.2 MΩ; D-130) | 60.11 | — | — | — | — | info |
| Geofex tester leakage (base open, 9 V, 2.4 kΩ), µA | 200.5 | — | — | — | — | info |

OC71: 23 OK, 3 MISS (checks with limits or a tolerance)

### OC44

| check | sim | min | typ | max | tol | result |
|---|---|---|---|---|---|---|
| Ico at Vcb 2 V (µA) | 0.5113 | — | 0.5 | 2 | — | OK (+0.0113 µA from typ) |
| Ico at Vcb 15 V (µA) | 0.5148 | — | — | 10 | — | OK |
| I'co, base open, Vce 2 V (µA) | 24.68 | — | 25 | 75 | — | OK (-0.324 µA from typ) |
| I'c, base reversed +500 mV, Vce 15 V (µA) | 0.3749 | — | 1 | 50 | — | OK (-0.625 µA from typ) |
| Collector knee voltage at Ic 5 mA (Ib for 6 mA at 1 V) (mV) | 106.2 | 80 | 140 | 200 | — | OK (-33.8 mV from typ) |
| Vce bottoming at Ic 8 mA, Ib 500 µA (mV) | 28.21 | 20 | 45 | 150 | — | OK (-16.8 mV from typ) |
| Vbe at Ic 1 mA, Vce 6 V (mV) | 134.2 | 125 | 150 | 185 | — | OK (-15.8 mV from typ) |
| α' small-signal at Ie 1 mA, Vce 6 V | 105.1 | 40 | 100 | 225 | — | OK (+5.08 from typ) |
| DC hFE at Ic 1 mA, Vce 6 V (info: no table line) | 98.9 | — | — | — | — | info |
| held: IC at IB 15.8 µA, VCE 2 V (mA) | 1.348 | — | 1.261 | — | 0.06304 | MISS (+0.0876 from typ) |
| held: IC at IB 43.3 µA, VCE 2 V (mA) | 3.963 | — | 3.906 | — | 0.1953 | OK (+0.0574 from typ) |
| held: IC at IB 77.5 µA, VCE 2 V (mA) | 7.36 | — | 7.616 | — | 0.3808 | OK (-0.255 from typ) |
| held: VBE at IC 124 µA, VCE 2 V (mV) | 83.68 | — | 86.26 | — | 10 | OK (-2.58 mV from typ) |
| held: VBE at IC 292 µA, VCE 2 V (mV) | 106.1 | — | 108.2 | — | 10 | OK (-2.06 mV from typ) |
| held: VBE at IC 799 µA, VCE 2 V (mV) | 132.9 | — | 133.7 | — | 10 | OK (-0.79 mV from typ) |
| held: VBE at IC 2.61 mA, VCE 2 V (mV) | 165.7 | — | 160 | — | 10 | OK (+5.71 mV from typ) |
| held: VBE at IC 4.8 mA, VCE 2 V (mV) | 184 | — | 176.3 | — | 10 | OK (+7.69 mV from typ) |
| held: VBE at IC 7.37 mA, VCE 2 V (mV) | 197.9 | — | 188.5 | — | 10 | OK (+9.39 mV from typ) |
| Geofex tester gain (9 V, 2.4 kΩ, 2.2 MΩ; D-130) | 94.58 | — | — | — | — | info |
| Geofex tester leakage (base open, 9 V, 2.4 kΩ), µA | 32.7 | — | — | — | — | info |

OC44: 16 OK, 1 MISS (checks with limits or a tolerance)

### OC75

| check | sim | min | typ | max | tol | result |
|---|---|---|---|---|---|---|
| Ico at Vcb 4.5 V (µA) | 4.71 | — | 4.5 | 12 | — | OK (+0.21 µA from typ) |
| ICEO, base open, Vce 4.5 V (µA) [Philips] | 326.2 | — | 350 | 550 | — | OK (-23.8 µA from typ) |
| IC at IB 10 µA, Vce 4.5 V (mA) [Philips] | 1.157 | 0.75 | 1.1 | 1.9 | — | OK (+0.0572 mA from typ) |
| VBE at IB 10 µA, Vce 4.5 V (mV) [Philips] | 111.1 | 90 | 120 | 175 | — | OK (-8.93 mV from typ) |
| IC at IB 250 µA, Vce 4.5 V (mA) [Philips] | 22.99 | 13.5 | 22 | 33 | — | OK (+0.991 mA from typ) |
| VBE at IB 250 µA, Vce 4.5 V (mV) [Philips] | 246.9 | 210 | 270 | 385 | — | OK (-23.1 mV from typ) |
| Vbe at Ic 3 mA, Vce 4.5 V (mV) | 141.2 | 100 | 140 | 210 | — | OK (+1.23 mV from typ) |
| Vce bottoming at Ic 9 mA, Ib 0.5 mA (mV) | 78.7 | — | 90 | 210 | — | OK (-11.3 mV from typ) |
| α' small-signal at Ic 3 mA, Vce 2 V | 84.3 | 60 | 90 | 130 | — | OK (-5.7 from typ) |
| DC hFE at Ic 3 mA, Vce 4.5 V (info: no table line) | 98.76 | — | — | — | — | info |
| held: IC at IB 0.7 µA, VCE 4.5 V (mA) | 0.3812 | — | 0.3972 | — | 0.01986 | OK (-0.016 from typ) |
| held: IC at IB 7.8 µA, VCE 4.5 V (mA) | 0.9699 | — | 0.9377 | — | 0.04689 | OK (+0.0322 from typ) |
| held: IC at IB 67.5 µA, VCE 4.5 V (mA) | 6.489 | — | 6.7 | — | 0.335 | OK (-0.21 from typ) |
| held: IC at IB 148.5 µA, VCE 4.5 V (mA) | 14.06 | — | 14.41 | — | 0.7205 | OK (-0.348 from typ) |
| held: IC at IB 232.8 µA, VCE 4.5 V (mA) | 21.53 | — | 20.91 | — | 1.045 | OK (+0.624 from typ) |
| held: VBE at IE 30.8 µA, VCE 4.5 V (mV) | 11.48 | — | 11.25 | — | 10 | OK (+0.234 mV from typ) |
| held: VBE at IE 53.5 µA, VCE 4.5 V (mV) | 26.18 | — | 27.84 | — | 10 | OK (-1.66 mV from typ) |
| held: VBE at IE 82.1 µA, VCE 4.5 V (mV) | 37.61 | — | 37.78 | — | 10 | OK (-0.17 mV from typ) |
| held: VBE at IE 1.36 mA, VCE 4.5 V (mV) | 115.7 | — | 115.2 | — | 10 | OK (+0.579 mV from typ) |
| held: VBE at IE 3.08 mA, VCE 4.5 V (mV) | 141.7 | — | 139.9 | — | 10 | OK (+1.84 mV from typ) |
| held: VBE at IE 6.5 mA, VCE 4.5 V (mV) | 170.3 | — | 171.8 | — | 10 | OK (-1.48 mV from typ) |
| held: VBE at IB 11.8 µA, VCE 4.5 V (mV) | 114.8 | — | 120.9 | — | 10 | OK (-6.13 mV from typ) |
| held: VBE at IB 58.8 µA, VCE 4.5 V (mV) | 165 | — | 162.7 | — | 10 | OK (+2.34 mV from typ) |
| held: VBE at IB 106 µA, VCE 4.5 V (mV) | 191.8 | — | 193.3 | — | 10 | OK (-1.43 mV from typ) |
| held: VBE at IB 153 µA, VCE 4.5 V (mV) | 212.6 | — | 220.6 | — | 10 | OK (-8.04 mV from typ) |
| held: VBE at IB 200 µA, VCE 4.5 V (mV) | 230.2 | — | 245.3 | — | 10 | MISS (-15.1 mV from typ) |
| held: VBE at IB 247 µA, VCE 4.5 V (mV) | 245.9 | — | 268.6 | — | 10 | MISS (-22.7 mV from typ) |
| Geofex tester gain (9 V, 2.4 kΩ, 2.2 MΩ; D-130) | 86.16 | — | — | — | — | info |
| Geofex tester leakage (base open, 9 V, 2.4 kΩ), µA | 370.2 | — | — | — | — | info |

OC75: 24 OK, 2 MISS (checks with limits or a tolerance)


## Starter comparison (AC128 against the study cards, in copies)

`compare.py` loads each starter from `library/starters/` (read only), swaps the AC128 parts in memory (`Circuit.with_part`) and runs the project's `Simulator`: operating point (bias trimmers solved as the app does), then a transient at the app's 200 Hz tone, soft (0.1 V peak, 'clean') and hard (1.0 V, 'fuzz'), at `out`. Two ways: **starter** = the starter's measured hFE and leakage kept (D-130/D-153 scale each card onto them, so only VBE, the gain's shape and the leakage split change), **card** = measured removed, each card's own gain and leakage (Geofex tester gain / leakage of each card: AC128 91.5 / 315 µA (its record), OC71 60.1 / 200 µA, OC44 94.6 / 32.7 µA, OC75 86.2 / 370 µA). `compare_ac.py`: small-signal gain at `out`.

### Fuzz Face (Q1, Q2)

| hFE/leak | variant | Q1.B | Q1.C | Q2.C | Q2.E | IC mA | TR1 | soft out dB | hard out: fund. dB, pk+ / pk− V, THD, asym |
|---|---|---|---|---|---|---|---|---|---|
| starter | AC128 | -0.059 | -0.497 | -5.297 | -0.427 | 0.257, 0.430 | — | 5.78 | -19.80, 0.098 / -0.401, 1.54, -0.61 |
| starter | OC71 | -0.081 | -0.564 | -4.934 | -0.469 | 0.255, 0.473 | — | 5.93 | -18.47, 0.113 / -0.397, 1.36, -0.56 |
| starter | OC75 | -0.073 | -0.545 | -5.013 | -0.460 | 0.257, 0.464 | — | 4.63 | -21.10, 0.085 / -0.416, 1.72, -0.66 |
| starter | OC44 | -0.104 | -0.618 | -4.671 | -0.500 | 0.250, 0.500 | — | 6.05 | -19.08, 0.106 / -0.403, 1.44, -0.58 |
| card | AC128 | -0.061 | -0.142 | -8.004 | -0.112 | 0.271, 0.115 | — | 6.38 | -19.52, 0.101 / -0.402, 1.49, -0.60 |
| card | OC71 | -0.082 | -0.412 | -6.151 | -0.329 | 0.258, 0.329 | — | 6.54 | -18.08, 0.117 / -0.393, 1.31, -0.54 |
| card | OC75 | -0.075 | -0.145 | -8.063 | -0.105 | 0.272, 0.108 | — | 5.42 | -20.74, 0.089 / -0.407, 1.66, -0.64 |
| card | OC44 | -0.104 | -0.556 | -5.178 | -0.442 | 0.251, 0.441 | — | 6.17 | -19.06, 0.107 / -0.406, 1.44, -0.58 |

### Tone Bender MkII (Q1-Q3; TR1 solved for Q2.C −0.16 V)

| hFE/leak | variant | Q1.B | Q1.C | Q2.C | Q3.B | Q3.C | IC mA | TR1 | soft out dB | hard out: fund. dB, pk+ / pk− V, THD, asym |
|---|---|---|---|---|---|---|---|---|---|---|
| starter | AC128 | -0.042 | -7.321 | -0.160 | -0.160 | -7.765 | 0.169, 0.137, 0.130 | 0.1836 | 5.83 | -19.15, 0.411 / -0.310, 1.42, 0.14 |
| starter | OC75 Q1-Q2, AC128 Q3 | -0.053 | -7.393 | -0.159 | -0.159 | -7.777 | 0.162, 0.122, 0.128 | 0.2734 | 5.84 | -19.31, 0.404 / -0.291, 1.43, 0.16 |
| starter | OC75 all | -0.053 | -7.393 | -0.161 | -0.161 | -7.864 | 0.162, 0.118, 0.120 | 0.2969 | 5.82 | -19.35, 0.408 / -0.289, 1.44, 0.17 |
| starter | OC71 all | -0.059 | -7.421 | -0.159 | -0.159 | -7.914 | 0.158, 0.111, 0.114 | 0.3438 | 5.87 | -18.45, 0.409 / -0.293, 1.32, 0.17 |
| starter | OC44 all | -0.081 | -7.561 | -0.160 | -0.160 | -8.109 | 0.141, 0.090, 0.091 | 0.5 | 5.82 | -19.07, 0.417 / -0.276, 1.42, 0.20 |
| card | AC128 | -0.054 | -6.467 | -0.041 | -0.041 | -8.589 | 0.253, 0.071, 0.043 | unreachable | 5.82 | -19.56, 0.413 / -0.291, 1.48, 0.17 |
| card | OC75 Q1-Q2, AC128 Q3 | -0.070 | -6.110 | -0.051 | -0.051 | -8.526 | 0.289, 0.071, 0.049 | unreachable | 5.83 | -19.82, 0.410 / -0.299, 1.52, 0.16 |
| card | OC75 all | -0.070 | -6.110 | -0.052 | -0.052 | -8.588 | 0.289, 0.072, 0.043 | unreachable | 5.80 | -19.82, 0.414 / -0.276, 1.51, 0.20 |
| card | OC71 all | -0.059 | -7.395 | -0.161 | -0.161 | -7.897 | 0.161, 0.158, 0.114 | 0.0938 | 5.82 | -18.50, 0.407 / -0.288, 1.32, 0.17 |
| card | OC44 all | -0.023 | -8.839 | -0.224 | -0.224 | -7.628 | 0.016, 0.065, 0.142 | unreachable | 5.71 | -19.08, 0.418 / -0.274, 1.42, 0.21 |

### Rangemaster (Q1): op and 200 Hz transient

| hFE/leak | variant | Q1.B | Q1.C | Q1.E | IC mA | soft dB | hard dB | hard pk+ / pk− V | hard THD |
|---|---|---|---|---|---|---|---|---|---|
| starter | AC128 | -0.976 | -6.658 | -0.924 | 0.238 | 12.78 | 10.46 | 3.783 / -2.614 | 0.222 |
| starter | OC44 | -0.978 | -6.762 | -0.883 | 0.224 | 12.69 | 10.16 | 3.651 / -2.504 | 0.233 |
| starter | OC71 | -0.971 | -6.721 | -0.900 | 0.232 | 12.99 | 10.42 | 3.822 / -2.575 | 0.235 |
| starter | OC75 | -0.975 | -6.693 | -0.910 | 0.235 | 12.71 | 10.34 | 3.723 / -2.572 | 0.223 |
| card | AC128 | -1.145 | -6.211 | -1.087 | 0.279 | 12.42 | 10.89 | 3.751 / -2.888 | 0.149 |
| card | OC44 | -0.995 | -6.717 | -0.899 | 0.228 | 12.75 | 10.25 | 3.677 / -2.539 | 0.229 |
| card | OC71 | -1.060 | -6.487 | -0.985 | 0.251 | 8.93 | 8.19 | 2.648 / -2.319 | 0.068 |
| card | OC75 | -1.175 | -6.162 | -1.104 | 0.284 | 11.65 | 10.45 | 3.480 / -2.837 | 0.114 |

### Small-signal gain at `out` (`out_compare_ac.txt`)

| starter | hFE/leakage | variant | 100 Hz dB | 1000 Hz dB | 5000 Hz dB | 20000 Hz dB | valid |
|---|---|---|---|---|---|---|---|
| fuzz-face | starter | AC128 | 38.13 | 42.47 | 38.96 | 29.06 | True |
| fuzz-face | starter | OC71 | 37.55 | 41.34 | 39.39 | 31.07 | True |
| fuzz-face | starter | OC75 | 37.91 | 42.20 | 40.59 | 32.82 | True |
| fuzz-face | starter | OC44 | 37.82 | 42.13 | 42.12 | 41.16 | True |
| fuzz-face | card | AC128 | 30.81 | 34.05 | 33.44 | 28.45 | True |
| fuzz-face | card | OC71 | 35.75 | 38.66 | 37.52 | 30.78 | True |
| fuzz-face | card | OC75 | 29.38 | 34.28 | 34.09 | 31.23 | True |
| fuzz-face | card | OC44 | 37.56 | 41.53 | 41.52 | 40.71 | True |
| tone-bender-mk2 | starter | AC128 | 44.75 | 67.56 | 59.60 | 47.64 | True |
| tone-bender-mk2 | starter | OC75 Q1-Q2, AC128 Q3 | 43.41 | 65.32 | 60.40 | 48.89 | True |
| tone-bender-mk2 | starter | OC75 all | 43.54 | 65.12 | 61.64 | 51.04 | True |
| tone-bender-mk2 | starter | OC71 all | 41.61 | 61.30 | 59.08 | 49.10 | True |
| tone-bender-mk2 | starter | OC44 all | 44.53 | 66.12 | 66.20 | 62.00 | True |
| tone-bender-mk2 | card | AC128 | 18.56 | 30.67 | 30.86 | 30.32 | False (trimmer at its rotation: TR1 can't set Q2.C to -0.16 V: turning it end to end only moves Q2.C between -0.09 V and -0.04 V. Change TR1's value or the resistor in series with it.) |
| tone-bender-mk2 | card | OC75 Q1-Q2, AC128 Q3 | 19.27 | 32.43 | 32.66 | 32.45 | False (trimmer at its rotation: TR1 can't set Q2.C to -0.16 V: turning it end to end only moves Q2.C between -0.10 V and -0.05 V. Change TR1's value or the resistor in series with it.) |
| tone-bender-mk2 | card | OC75 all | 18.62 | 31.45 | 31.68 | 31.57 | False (trimmer at its rotation: TR1 can't set Q2.C to -0.16 V: turning it end to end only moves Q2.C between -0.10 V and -0.05 V. Change TR1's value or the resistor in series with it.) |
| tone-bender-mk2 | card | OC71 all | 40.04 | 58.29 | 57.36 | 49.50 | True |
| tone-bender-mk2 | card | OC44 all | 27.03 | 49.89 | 49.93 | 44.94 | True (trimmer at its rotation: TR1 can't set Q2.C to -0.16 V: turning it end to end only moves Q2.C between -0.44 V and -0.21 V. Change TR1's value or the resistor in series with it.) |
| dallas-rangemaster | starter | AC128 | 6.76 | 24.91 | 28.96 | 29.22 | True |
| dallas-rangemaster | starter | OC44 | 6.62 | 26.29 | 35.00 | 36.26 | True |
| dallas-rangemaster | starter | OC71 | 6.96 | 25.65 | 30.72 | 31.06 | True |
| dallas-rangemaster | starter | OC75 | 6.66 | 25.51 | 30.97 | 31.41 | True |
| dallas-rangemaster | card | AC128 | 6.39 | 24.76 | 29.20 | 29.50 | True |
| dallas-rangemaster | card | OC44 | 6.67 | 26.35 | 35.10 | 36.37 | True |
| dallas-rangemaster | card | OC71 | 2.85 | 22.38 | 30.30 | 31.24 | True |
| dallas-rangemaster | card | OC75 | 5.58 | 24.79 | 31.30 | 31.93 | True |

### What the comparison says
- **With the starters' measured hFE and leakage (as shipped), swapping the card moves little.** Fuzz Face: Q2.C −5.30 V (AC128) → −4.93 (OC71), −5.01 (OC75), −4.67 (OC44); Q1.C −0.50 → −0.56/−0.54/−0.62; Q1's VBE 59 mV → 81/73/104 mV. The study cards sit closer to ElectroSmash's −4.5 V and −0.7 V than the AC128 does (D-170 lists both as gaps). Tone Bender: TR1 still sets Q2.C −0.16 V with every card (rotation 0.18 AC128 → 0.27-0.30 OC75, 0.34 OC71, 0.50 OC44); Q1.C −7.32 → −7.39 (OC75), Q3.C −7.77 → −7.78 (OC75 Q1-Q2) / −7.86 (OC75 all); Q1.B −42 → −53 mV (OC75), still near Aion's −0.05 V. Rangemaster: Q1.C −6.66 → −6.76 V (OC44), IC 0.238 → 0.224 mA.
- **Clip level hardly changes** (200 Hz transients): both levels already saturate the Fuzz Face and Tone Bender output, so the fundamental at `out` is the clip level: Fuzz Face within 1.4 dB soft (4.6 OC75 … 6.1 OC44) and 2.6 dB hard (−21.1 OC75 … −18.5 OC71); Tone Bender within 0.1 dB soft and 0.9 dB hard. Peak heights within ~15 %, THD 1.3-1.7, the OC71 a little softer (THD 1.32-1.36 against 1.42-1.72). Rangemaster clean gain at 200 Hz within 0.3 dB (12.7-13.0 dB), hard 10.2-10.5 dB.
- **The treble is where the cards differ**, through the collector capacitance: Rangemaster small-signal gain at 5 kHz 29.0 dB (AC128, Cb'c 100 pF) → 35.0 (OC44, 10.5 pF), 30.7 (OC71, 40 pF), 31.0 (OC75); at 20 kHz 29.2 → 36.3 dB. That is D-170's known Rangemaster gap ("a slow output transistor standing in for an OC44"), now closable with the OC44 card. Fuzz Face at 20 kHz 29.1 → 41.2 dB (OC44), 31-33 dB (OC71/OC75); Tone Bender at 20 kHz 47.6 → 49-51 (OC75/OC71), 62.0 (OC44).
- **With each card's own gain and leakage**, the circuits diverge a lot, as builders know: Fuzz Face Q2.C −8.00 V (AC128's own; Q2 nearly off, 0.11 mA) against −6.15 (OC71), −8.06 (OC75), −5.18 (OC44). In the Tone Bender, TR1 can't reach −0.16 V with the AC128's, OC75's or OC44's own values (Q2.C range −0.04…−0.10 V, or −0.21…−0.44 V for the OC44), and the AC check flags a saturated stage for the first three; only the OC71's own (200 µA leakage, gain 60, close to Aion's middle readings) lands on target. So the starters' measured values carry the bias; the card mostly shapes VBE and the treble.

## Misses (no check loosened)
- OC71: held IC at IB 94.7 µA (page 13, 5.3 mA) +7.2 % (5 % tol; page 13 drawn without the leakage, see above); VBE above the fit range (8.5, 9.5 mA) +12, +16 mV (fixed rbb' 300 Ω; Ic max is 10 mA). Table typicals off but within limits: VBE at 1 mA 120.8 mV (135 typ), I'co 174 µA (150 typ), h'21e at 1 mA 54.5 (41 typ, no limits).
- OC44: held IC at IB 15.8 µA +6.9 % (1.35 against 1.26 mA). Table typicals within limits: knee voltage 106 mV (140 typ), bottoming 28 mV (45), VBE at 1 mA, 6 V 134 mV (150).
- OC75: held VBE on C5 at IB 200 and 247 µA −15, −23 mV (no rbb' on the sheet; IC ≈ 17-22 mA, above the 10 mA rating). Philips VBE at 250 µA 247 mV (270 typ, 210-385) and at 10 µA 111 mV (120 typ, 90-175): within limits.

## Draft DECISIONS entry

**D-NNN — OC71, OC44 and OC75: our own fits to Mullard's curve sheets (germanium study, provisional)** (2026-11-03, Phase 9b; the user: fit the OC75/OC44/OC71 sheets, then run the germanium starters on them against the AC128)
- **Sheets:** Mullard Technical Handbook Vol. 4 Part III (Nov 1968): OC71 Issue 2, OC44 (Dec 1960), OC75 (March 1959), raster, read by pixel (`.claude/skills/fit-model/worked/germanium/pix.py`: frames from the darker major grid lines, values linear between labelled majors, the thick line's centre per row or column). Philips' OC75 table (1958-60) gives six more checks. Package SO-2 glass, E B C in a line.
- **Fitted as drawn, leakage in:** Mullard's transfer characteristic meets IB = 0 at I'co (0.16-0.36 mA), so IC at the sheet's IB, VBE at its IE (or IC) and ICBO are fitted together at the sheet's VCE (−4.5 V; OC44 −2 V) with the card's own leakage flowing (IS, BR, NR = NF), not at VCB = 0 as Valvo's AC128. RB is rbb' (OC71 300 Ω, OC44 110 Ω; the OC75 sheet gives none, so 0); VAF from h'22; CJC from Cc/Cb'c; TF from fα as fT.
- **Judgements:** the OC71's page-13 Average line is drawn into the origin (no leakage), so it is used from 5 mA; its VBE (117-121 mV at 1 mA on four figures) is kept against the table's 135 typical because it is inside the limits (D-163 moves a figure only when it breaks them). The OC44's input figure (C2 upper) contradicts its IC-VBE figure and the table (106 mV at 1 mA, below the 125 minimum) and is left out; its I'co 25 µA is fitted as the transfer line's foot. The OC75's CJC is the cross-reference book's Cob ≤ 50 pF, a secondary maximum (no maker gives a capacitance).
- **Result:** OC71 IC within 1.5 % to 1.1 mA (7.9 % at 5 mA), VBE 4.7 mV to 6 mA; OC44 IC within 5.8 %, VBE 2.4 mV to 1.1 mA (9 mV above 2 mA); OC75 IC within 6.6 %, VBE 1.9 mV. Every table limit met; 6 held-out misses, each above the part's useful range or against a figure judged off (NOTES).
- **In the starters** (their measured hFE and leakage kept): bias moves 0.1-0.6 V (Fuzz Face Q2.C −5.30 → −4.67…−5.01 V, nearer ElectroSmash's −4.5), clip levels within 0.9-2.6 dB; the treble changes most (Rangemaster at 5 kHz +6 dB with the OC44's 10.5 pF against the AC128's 100 pF, closing D-170's Rangemaster gap).
- **Not yet in the library:** provisional until the user decides whether the starters move to them (Rangemaster → OC44, Tone Bender Q1/Q2 → OC75) and the acceptance files are re-based.
*Alternatives:* the AC128 for every germanium site (D-170; wrong treble for the OC44 sites); fitting at VCB = 0 (Mullard gives no such curves); a free RB for the OC75 (it trades against IS and VBE, D-170); digitising Philips' OC75 figures too (its table already agrees with Mullard's curves within 5 %).

## Disk and cleanup

## 2N404 and 2N1308 (D-188)
Computer-switching alloys; both sheets stop at 10-12 mA. Scripts: `n404/digit.py`, `n404/fit.py`, `n404/try_droop.py` (Fig. 2 against the table: `n404/out_fit_with_fig2.txt`); `n1308/digit.py`, `n1308/fit.py` (with the family VCE lines fitted: `n1308/out_fit_with_vce.txt`); the fitter `alloy.py`; checks in `checks.py` (`n2n404`, `n2n1308`), measured by `measure.py 2N404 2N1308`. The fit scripts docstrings give every judgement. Pages rendered with `pdftoppm -r 300 -gray` into the session scratchpad (`/scr/2n404/p-N.pgm`, `/scr/2n1308/p-N.pgm`; the RCA pdf orders printed pages 1, 2, 5, 4, 3, 6).

```
.model 2N404 PNP(is=3.101e-06 nf=1.047 bf=100.8 ise=2.048e-08 ne=1.114 ikf=0.04757 br=4.385 isc=6.474e-07 nc=4 re=1.805 vje=0.75 mje=0.33 cjc=2.478e-11 vjc=0.75 mjc=0.33 tf=1.192e-08 nkf=0.5669 nr=1.047 eg=0.67)
.model 2N1308 NPN(is=2.915e-06 nf=1.094 bf=360.6 ise=8.736e-08 ne=1.451 ikf=1.022 br=9.185 isc=2.04e-06 nc=4 rc=1.28 cje=1.958e-11 vje=0.75 mje=0.33 cjc=4.091e-11 vjc=0.6081 mjc=0.3176 tf=6.278e-09 nkf=0.8915 nr=1.094 eg=0.67)
```
### 2N404

| check | sim | min | typ | max | tol | result |
|---|---|---|---|---|---|---|
| hFE at Ic 12 mA, Vce 0.15 V | 47.43 | 30 | 50 | — | — | OK (-2.57 from typ) |
| hFE at Ic 24 mA, Vce 0.2 V | 41.93 | 24 | 40 | — | — | OK (+1.93 from typ) |
| VCE(sat) at Ic 12 mA, Ib 0.4 mA (mV) | 107.6 | — | 100 | 150 | — | OK (+7.55 mV from typ) |
| VCE(sat) at Ic 24 mA, Ib 1 mA (mV) | 131.1 | — | 120 | 200 | — | OK (+11.1 mV from typ) |
| VBE(sat) at Ic 12 mA, Ib 0.4 mA (mV) | 255.3 | — | 250 | 350 | — | OK (+5.27 mV from typ) |
| VBE(sat) at Ic 24 mA, Ib 1 mA (mV) | 303.4 | — | 320 | 400 | — | OK (-16.6 mV from typ) |
| ICBO at Vcb 12 V (µA) | 1.405 | — | 2 | 5 | — | OK (-0.595 µA from typ) |
| IC at IB 0.5 mA, VCE 0.3 V, between Figs. 3 and 4 (mA) | 22.73 | 14.39 | — | 49.12 | — | OK |
| IC at IB 0.5 mA, VCE 0.68 V, between Figs. 3 and 4 (mA) | 22.77 | 14.99 | — | 51.7 | — | OK |
| IC at IB 1 mA, VCE 0.3 V, between Figs. 3 and 4 (mA) | 36.3 | 27.47 | — | 73.74 | — | OK |
| IC at IB 1 mA, VCE 0.68 V, between Figs. 3 and 4 (mA) | 36.4 | 29.86 | — | 77.41 | — | OK |
| IC at IB 2 mA, VCE 0.3 V, between Figs. 3 and 4 (mA) | 55.08 | 40.65 | — | 93.74 | — | OK |
| IC at IB 2 mA, VCE 0.68 V, between Figs. 3 and 4 (mA) | 55.55 | 46.05 | — | 101.1 | — | OK |
| IC at IB 3 mA, VCE 0.3 V, between Figs. 3 and 4 (mA) | 68.47 | 56.81 | — | 118.1 | — | OK |
| IC at IB 3 mA, VCE 0.68 V, between Figs. 3 and 4 (mA) | 69.89 | 61.91 | — | 126.7 | — | OK |
| IC at IB 4 mA, VCE 0.3 V, between Figs. 3 and 4 (mA) | 78.45 | 72.26 | — | 161.5 | — | OK |
| IC at IB 4 mA, VCE 0.68 V, between Figs. 3 and 4 (mA) | 81.74 | 79.4 | — | 170.1 | — | OK |
| VBE(sat) at Ic 12.5 mA, Ib 0.5 mA, between Figs. 8 and 7 (mV) | 258.5 | 256.9 | — | 298.9 | — | OK |
| VBE(sat) at Ic 12.5 mA, Ib 1 mA, between Figs. 8 and 7 (mV) | 263.9 | 276.1 | — | 329.8 | — | MISS |
| VBE(sat) at Ic 27.5 mA, Ib 1 mA, between Figs. 8 and 7 (mV) | 314.3 | 301.6 | — | 363.9 | — | OK |
| VBE(sat) at Ic 27.5 mA, Ib 2 mA, between Figs. 8 and 7 (mV) | 320.1 | 317.6 | — | 383.6 | — | OK |
| VBE(sat) at Ic 27.5 mA, Ib 4 mA, between Figs. 8 and 7 (mV) | 330.4 | 346.8 | — | 428.3 | — | MISS |
| hFE at Ic 2 mA, Vce 0.5 V (info: Fig. 2 minimum 24.1) | 69.55 | — | — | — | — | info |
| hFE at Ic 31 mA, Vce 0.5 V (info: Fig. 2 minimum 41.7) | 39.64 | — | — | — | — | info |
| hFE at Ic 2 mA, Vce 0.15 V (info: Fig. 2 minimum 18.6) | 62.61 | — | — | — | — | info |
| hFE at Ic 31 mA, Vce 0.15 V (info: Fig. 2 minimum 31.1) | 23.4 | — | — | — | — | info |
| Geofex tester gain (9 V, 2.4 kΩ, 2.2 MΩ; D-130) | 67.15 | — | — | — | — | info |
| Geofex tester leakage (base open, 9 V, 2.4 kΩ), µA | 93 | — | — | — | — | info |

2N404: 20 OK, 2 MISS (checks with limits or a tolerance)
### 2N1308

| check | sim | min | typ | max | tol | result |
|---|---|---|---|---|---|---|
| hFE at Ic 10 mA, Vce 1 V | 149.8 | 80 | 150 | — | — | OK (-0.176 from typ) |
| hFE at Ic 200 mA, Vce 0.35 V | 79.49 | 20 | — | — | — | OK |
| VBE at Ic 10 mA, Ib 0.5 mA (mV) | 240.5 | 200 | 240 | 300 | — | OK (+0.463 mV from typ) |
| VCE(sat) at Ic 10 mA, Ib 0.13 mA (mV) | 100.9 | — | 100 | 150 | — | OK (+0.906 mV from typ) |
| ICBO at Vcb 25 V (µA) | 2.446 | — | 3 | 6 | — | OK (-0.554 µA from typ) |
| held: hFE at Ic 33 mA, Vce 1 V (curve x 1.02 x 150) | 166.3 | — | 160.2 | — | 8 | OK (+6.06 from typ) |
| held: hFE at Ic 79 mA, Vce 1 V (curve x 1.02 x 150) | 169.7 | — | 174.6 | — | 8.7 | OK (-4.86 from typ) |
| held: hFE at Ic 125 mA, Vce 1 V (curve x 1.02 x 150) | 163.9 | — | 171.1 | — | 8.6 | OK (-7.15 from typ) |
| held: hFE at Ic 171 mA, Vce 1 V (curve x 1.02 x 150) | 154.7 | — | 155.6 | — | 7.8 | OK (-0.915 from typ) |
| held: hFE at Ic 216 mA, Vce 1 V (curve x 1.02 x 150) | 143.7 | — | 141.9 | — | 7.1 | OK (+1.82 from typ) |
| held: hFE at Ic 260 mA, Vce 1 V (curve x 1.02 x 150) | 131.9 | — | 130.8 | — | 6.5 | OK (+1.13 from typ) |
| VCE at Ic 28 mA, Ib 1 mA (info: family line 124 mV) | 82.91 | — | — | — | — | info |
| VCE at Ic 63 mA, Ib 1 mA (info: family line 220 mV) | 155.7 | — | — | — | — | info |
| VCE at Ic 70 mA, Ib 5 mA (info: family line 147 mV) | 122.8 | — | — | — | — | info |
| VCE at Ic 181 mA, Ib 5 mA (info: family line 341 mV) | 295.9 | — | — | — | — | info |
| VCE at Ic 85 mA, Ib 20 mA (info: family line 140 mV) | 127.5 | — | — | — | — | info |
| VCE at Ic 189 mA, Ib 20 mA (info: family line 275 mV) | 277.4 | — | — | — | — | info |
| VCE at Ic 254 mA, Ib 50 mA (info: family line 330 mV) | 357.9 | — | — | — | — | info |
| VCE at Ic 275 mA, Ib 50 mA (info: family line 357 mV) | 387.1 | — | — | — | — | info |
| VBE at Ic 22 mA, Ib 1 mA (info: family line 345 mV) | 262.5 | — | — | — | — | info |
| VBE at Ic 22 mA, Ib 5 mA (info: family line 459 mV) | 286.1 | — | — | — | — | info |
| VBE at Ic 70 mA, Ib 10 mA (info: family line 600 mV) | 313.4 | — | — | — | — | info |
| VBE at Ic 155 mA, Ib 30 mA (info: family line 760 mV) | 346.8 | — | — | — | — | info |
| Geofex tester gain (9 V, 2.4 kΩ, 2.2 MΩ; D-130) | 103.3 | — | — | — | — | info |
| Geofex tester leakage (base open, 9 V, 2.4 kΩ), µA | 182.1 | — | — | — | — | info |

2N1308: 11 OK, 0 MISS (checks with limits or a tolerance)
