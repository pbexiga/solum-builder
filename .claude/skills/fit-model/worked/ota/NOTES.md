# OTA models: CA3080 and LM13700 (Phase 9b, D-149 part type "OTA")

Sheets: **CA3080** = Intersil CA3080/CA3080A data sheet, File Number 475.4 (September 1998),
`data/spec-sheets/CA3080_Intersil.pdf` (11 pp). **LM13700** = TI SNOSBW2F (Nov 1999, rev. Nov 2015),
`data/spec-sheets/LM13700_TI_SNOSBW2F.pdf` (36 pp).

Files here (.claude/skills/fit-model/worked/ota/ only):
- `build_ota.py`: every sheet number (with its source) and the fits; writes `CA3080.lib`, `LM13700.lib`.
- `check_ota.py`: ngspice checks against the tables and figures → `check.log`.
- `pedal_ota.py`: 9 V single-supply VCA sanity checks → `pedal.log`.
- `digit.py`, `frames.py`, `fig18.py`: CA3080 vector figures (axes mapped from frame edges / grid lines).
- `pix.py` + `img/i-NNN.png`: LM13700 raster figures read by pixel (`pdfimages -png -f 6 -l 8`; convert each
  to `.pgm` with `magick i-NNN.png -depth 8 i-NNN.pgm` before running).
- `fit_lin.py`: the rejected attempt to fit a series resistance to Fig 13 "using diodes" (below).

Run (dev container): `podman run --rm -v "$PWD":/src:z -w /src -e PYTHONPATH=/src -e HOME=/tmp solum-builder:dev python .claude/skills/fit-model/worked/ota/<script>.py`

## 1. Maker models (step 1)

- **LM13700:** TI's product page lists "LM13700 PSPICE Model", https://www.ti.com/lit/zip/SNOM267 (SNOM267.ZIP,
  1 KB, `LM13700.MOD`). It is **National Semiconductor's** old transistor-level subcircuit `LM13700/NS`
  (pins: bias, diode bias, +in, −in, out, V−, buffer in, buffer out, V+). Header: "(C) National Semiconductor …
  This material is intended for free software support. The file may be copied, and distributed; however,
  reselling the material is illegal." TI's page adds "TI's Standard Terms and Conditions for Evaluation Items
  apply." So redistribution is allowed by the file's own notice (not resale); TI's page layers its evaluation
  terms on top — a D-159 call for the user. The file itself warns it is single-pole and "over-estimates AC
  bandwidth and phase margin … by over 2X". Downloaded to my scratchpad only, not into the repo.
- **CA3080:** no Renesas/Intersil SPICE model found (Renesas' simulation library pages and a web search; ~3 min).

We built our own anyway, as asked.

## 2. Pinouts

**CA3080** (475.4 p.1, "Pinouts", PDIP/SOIC top view; the metal can uses the same numbers, tab at 8):

| Pin | Function |
|---|---|
| 1 | NC |
| 2 | Inverting input (−) |
| 3 | Non-inverting input (+) |
| 4 | V− |
| 5 | Amplifier bias input (Iabc) |
| 6 | Output |
| 7 | V+ |
| 8 | NC |

**LM13700** (SNOSBW2F p.3, "Pin Configuration and Functions", D/NFG 16-pin top view and Pin Functions table):

| Pin | Function | Pin | Function |
|---|---|---|---|
| 1 | Amp bias input A | 16 | Amp bias input B |
| 2 | Diode bias A | 15 | Diode bias B |
| 3 | Input+ A | 14 | Input+ B |
| 4 | Input− A | 13 | Input− B |
| 5 | Output A | 12 | Output B |
| 6 | V− | 11 | V+ |
| 7 | Buffer input A | 10 | Buffer input B |
| 8 | Buffer output A | 9 | Buffer output B |

Subcircuit pin orders (as the integrator asked):
`.subckt CA3080 inp inn out iabc vp vn` = DIP pins 3 2 6 5 7 4.
`.subckt LM13700_OTA inp inn out iabc dbias bufin bufout vp vn` = amp A pins 3 4 5 1 2 7 8 11 6, amp B 14 13 12 16 15 10 9 11 6.

## 3. Figures used and how they were read

**CA3080: all curves are vector** (pp. 8–10). `plots.py` mis-maps several axes (the "10⁴" tick labels split into
"10" and "4", and the x labels sit off their grid lines), so `digit.py` maps each frame from its edges, checked
against the grid lines printed by `frames.py` (e.g. Fig 16 x: 0.1 µA at 83.2 pt, decades every 49 pt to 1000 µA
at 280.0 pt, not the label centres). Which curve is 25 °C was read off the rendered page (labels and arrows).
Several curves are 3-point polylines (Figs 16, 27): used as drawn.

| Fig | What | Use |
|---|---|---|
| 16 p.8 | Input bias current vs Iabc (25 °C = middle) | fitted: log Ib = 0.8636·log Iabc − 2.851 (A) |
| 17 p.8 | Peak output current vs Iabc (25 °C = middle) | check only (table wins: Ipk = Iabc) |
| 18 p.9 | Peak output voltage / CMR vs Iabc (broken axis, `fig18.py`) | check at 0.1 µA and 1 mA |
| 19 p.9 | Supply current vs Iabc | check only (table: 1 mA at 500 µA) |
| 21 p.9 | gm vs Iabc (25 °C = middle, 2.0 µS at 0.1 µA) | check (gm = Iabc/2VT, = table) |
| 26 p.10 | Input resistance vs Iabc | check (follows from Ib: Rin = 2VT/Ib) |
| 27 p.10 | Amplifier bias voltage vs Iabc (25 °C = middle) | fitted with the table's 0.71 V |
| 28 p.10 | Cin, Cout vs Iabc | table values at 500 µA used (fixed caps) |
| 29 p.10 | Output resistance vs Iabc | check only (table 15 MΩ wins) |
| 14, 15, 23, 25 | offset, offset current, leakage vs T, input current vs Vdiff | not modelled (offsets are per unit; 125 °C) |

**LM13700: all figures are raster** (1-bit images embedded at 320 ppi, Fig 4 at 774 ppi; pp. 6–8), read by
pixel with `pix.py`: frame from the grid lines (37 columns = 4 decades × 9 + 1 confirms 0.1–1000 µA), curves as
dark runs ≥ 7 px tall in columns between grid lines (log grids have a line at every integer, so I sampled at
0.15, 0.25, 0.45, 1.5 … 450, 950 µA), 25 °C = the middle curve where three are drawn.

| Fig | What | Use |
|---|---|---|
| 3 | Input bias current vs Iabc | fitted (quadratic in log-log): 2.66 nA @0.15 µA … 1748 nA @450 µA |
| 4 | Peak output current vs Iabc (one line) | check only; reads 1.2–1.3 × Iabc, table wins (Ipk = Iabc) |
| 5 | Peak output voltage / CMR | not read (broken raster axis); the table's ±14.2/−14.4 and ±13.5 V used |
| 8 | gm vs Iabc | check (gm = Iabc/2VT = table 9600 µS) |
| 9 | Input resistance vs Iabc | check |
| 10 | Amplifier bias voltage vs Iabc (two junctions) | fitted (13 points, 976.6 mV @0.1 µA … 1484.7 mV @1 mA) |
| 11 | Cin, Cout vs Iabc | values at 500 µA used: Cin 5.96 pF, Cout 4.75 pF |
| 12 | Output resistance vs Iabc | fitted: VA = geometric mean of Rout·Iabc = 1504 V |
| 13 | Distortion vs differential input, with/without diodes | check |
| 14, 15 | Output level/noise, noise current | not modelled (no noise) |
| — | Buffer VBE vs current | **the sheet has no such curve**; buffer junctions = the chip's junction (below) |

Electrical characteristics used (all typ, 25 °C, ±15 V, Iabc 500 µA unless stated):
- CA3080 (p.2–3): gm 9600 µS (6700–13000); peak Iout 5 µA @5 µA (CA3080A 3–7), 500 µA @500 µA (350–650);
  Ib 2 µA (max 5); bias voltage 0.71 V; Rin 26 kΩ (min 10); Cin 3.6 pF; Cio 0.024 pF; CMR +13.6/−14.6 V (min ±12);
  Cout 5.6 pF; Rout 15 MΩ; peak out RL=∞ +13.8/−14.5 V @5 µA, +13.5/−14.4 V @500 µA (min ±12); supply 1 mA
  (0.8–1.2); differential input current 0.008 nA at Iabc 0, 4 V; leakage 0.3 nA at 36 V; open-loop BW 2 MHz;
  slew 75 V/µs uncompensated, 50 compensated; CMRR 110 dB; offsets 0.3–0.4 mV (not modelled).
- LM13700 (6.4): gm 9600 µS (6700–13000); peak Iout 5 µA @5 µA, 500 µA (350–650); Ib 0.4 µA (max 5); Rin 26 kΩ
  (min 10); supply 2.6 mA both channels; CMR ±13.5 V (min ±12); differential input current 0.02 nA (max 100);
  leakage 0.2 nA; BW 2 MHz; slew 50 V/µs unity-gain compensated; buffer input current 0.5 µA (max 2) and peak
  buffer output ≥ 10 V under footnote (1) (Iabc 500 µA, 5 kΩ buffer output to −VS, buffer input on the OTA
  output); peak out RL=∞ +14.2/−14.4 V for 5–500 µA (min ±12). Recommended operating conditions: single supply
  **9.5 V min** (9 V pedals are just under it).

## 4. The models

Behavioural core (both parts), the sheet's own circuit description (TI 7.3.1, eq. 1–5):
- **Iabc** is the current into the bias pin, sensed (`Vsense`) through a diode to V− that gives the pin its
  voltage: CA3080 one junction fitted to Fig 27 + table (IS 1.18e-16, N 0.940, RS 16.0 Ω); LM13700 "2 diode
  drops above the negative supply" (TI 8.2.2) as one diode fitted to Fig 10 (IS 2.40e-15, N 2.171, RS 0).
  Iabc = max(I, 0), so a pin pulled below V− or left open gives 0.
- **I5, I4 = Iabc·(1 ± tanh(Vd/2VT))/2**, VT from ngspice's `temper` (so the linearising diodes, ngspice
  junctions at the same temperature, cancel the tanh exactly; gm at 27 °C is 0.7 % above 25 °C).
- **Bandwidth:** one 2 MHz RC pole on I5 and I4 (after the tanh). First tried on Vd: a large step then wound up
  the filtered input and overshot ~3 V in a follower; after the tanh a step slews at Iabc/C, as an OTA does.
- **Output:** I5 sourced from V+, I4 sunk to V−, each × f(headroom) and × (1 + VCE/VA). f(x) = u²/(u² + 0.05²),
  u = max(x, 0): the output device stops dead at the swing limit (so RL = ∞ settles exactly there) with a 50 mV
  knee (judgement: no sheet figure). VA = Rout·Iabc gives Rout = VA/Iabc at balance: CA3080 7500 V (table
  15 MΩ × 500 µA), LM13700 1504 V (Fig 12).
- **Swing:** CA3080 headroom from the table's two points, log in Iabc: V+ 1.095 + 0.15·log10(Iabc/1 µA),
  V− 0.465 + 0.05·log10(Iabc/1 µA) (floored at 0.1 µA). LM13700 0.8 / 0.6 V, constant (table: 5–500 µA).
- **Common-mode range:** both halves × the same f on (V+ − 1.4 − Vcm)·(Vcm − V− − 0.4) for the CA3080 (table
  +13.6/−14.6 V), 1.5/1.5 V for the LM13700 (table ±13.5). Outside it gm goes to zero.
- **Input bias current / resistance:** the inputs draw the pair's base currents I5/β, I4/β (instantaneous Vd),
  β(Iabc) = (Iabc/2)/Ib(Iabc) from the Fig 16 / Fig 3 fit (clamped to the figures' 0.1 µA–1 mA). That gives
  Rin = 2VT/Ib by itself (the pair's own relation; 2 µA × 26 kΩ = 52 mV on both tables).
- **Caps, leakage:** Cin from each input to V−, Cout to V−, CA3080 Cio 0.024 pF (− input to out); Rdiff between
  inputs for the Iabc = 0 differential input current; 2 × Rleak from out to each rail (the leakage line).
- **Supply:** V+ draws k·Iabc at balance (CA3080 k = 2, LM13700 k = 2.6 per amplifier); Iabc/2 of it is the
  output pair, the rest a B-source V+→V−; output current comes from the rail it flows to.
- **LM13700 only:** linearising diodes D2 (diode bias → −in) and D3 (→ +in) as ngspice junctions, N = 1,
  IS 2.66e-16 so one junction drops half of Fig 10 at 500 µA (TI 7.3.1: "all transistors and diodes are identical
  in size"); the Darlington buffer Q12/Q13 (collectors on V+) as two NPNs with that IS and BF 104.3, so the
  buffer input current is the table's 0.5 µA under footnote (1), read as the OTA output at its +14.2 V peak
  driving 5 kΩ to −15 V (that footnote's "peak buffer output voltage" line). Q12/Q13 are the two parts TI says
  differ in size; their IS is an assumption (no buffer VBE figure).

### CA3080.lib
```
* CA3080 operational transconductance amplifier (our model from the sheet)
* Built by Solum Builder from Intersil CA3080/CA3080A data sheet File Number 475.4
* (September 1998), typical figures at 25 degC, +-15 V. Behavioural core: Iout =
* Iabc*tanh(Vd/2VT); bias pin a junction to V-.
.subckt CA3080 inp inn out iabc vp vn
Vsense iabc ib0 0
Dbias ib0 vn DBIAS
Bia ia 0 V=max(i(Vsense),0)
Bw w 0 V=((pwr(max(v(vp)-1.4-(0.5*(v(inp)+v(inn))),0),2)/(pwr(max(v(vp)-1.4-(0.5*(v(inp)+v(inn))),0),2)+0.0025))*(pwr(max((0.5*(v(inp)+v(inn)))-v(vn)-0.4,0),2)/(pwr(max((0.5*(v(inp)+v(inn)))-v(vn)-0.4,0),2)+0.0025)))
Bi5 i5r 0 V=v(ia)*v(w)*0.5*(1+tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))
Bi4 i4r 0 V=v(ia)*v(w)*0.5*(1-tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))
R5 i5r i5 1k
C5 i5 0 7.95775e-11
R4 i4r i4 1k
C4 i4 0 7.95775e-11
Bsrc vp out I=v(i5)*(pwr(max(v(vp)-(1.09515+(0.15)*log10(max(v(ia),1e-7)/1e-6))-v(out),0),2)/(pwr(max(v(vp)-(1.09515+(0.15)*log10(max(v(ia),1e-7)/1e-6))-v(out),0),2)+0.0025))*(1+max(v(vp)-v(out),0)/7500)
Bsnk out vn I=v(i4)*(pwr(max(v(out)-v(vn)-(0.465051+(0.05)*log10(max(v(ia),1e-7)/1e-6)),0),2)/(pwr(max(v(out)-v(vn)-(0.465051+(0.05)*log10(max(v(ia),1e-7)/1e-6)),0),2)+0.0025))*(1+max(v(out)-v(vn),0)/7500)
Cout out vn 5.6e-12
Rleak out vn 2.4e+11
Rleak2 out vp 2.4e+11
Bbp inp vn I=v(ia)*v(w)*0.5*(1+tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))/(0.5*pwr(10,log10(min(max(v(ia),1e-7),1e-3)))/pwr(10,(0.863627)*log10(min(max(v(ia),1e-7),1e-3))+(-2.85139)))
Bbn inn vn I=v(ia)*v(w)*0.5*(1-tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))/(0.5*pwr(10,log10(min(max(v(ia),1e-7),1e-3)))/pwr(10,(0.863627)*log10(min(max(v(ia),1e-7),1e-3))+(-2.85139)))
Rdiff inp inn 5e+11
Cinp inp vn 3.6e-12
Cinn inn vn 3.6e-12
Bq vp vn I=1.5*v(ia)
Cio inn out 2.4e-14
.model DBIAS D(IS=1.17975e-16 N=0.939612 RS=15.9617)
.ends CA3080
```
(The .lib file carries comment lines between these; contents identical.)

### LM13700.lib (one amplifier)
```
.subckt LM13700_OTA inp inn out iabc dbias bufin bufout vp vn
Vsense iabc ib0 0
Dbias ib0 vn DBIAS
Bia ia 0 V=max(i(Vsense),0)
Bw w 0 V=((pwr(max(v(vp)-1.5-(0.5*(v(inp)+v(inn))),0),2)/(pwr(max(v(vp)-1.5-(0.5*(v(inp)+v(inn))),0),2)+0.0025))*(pwr(max((0.5*(v(inp)+v(inn)))-v(vn)-1.5,0),2)/(pwr(max((0.5*(v(inp)+v(inn)))-v(vn)-1.5,0),2)+0.0025)))
Bi5 i5r 0 V=v(ia)*v(w)*0.5*(1+tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))
Bi4 i4r 0 V=v(ia)*v(w)*0.5*(1-tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))
R5 i5r i5 1k
C5 i5 0 7.95775e-11
R4 i4r i4 1k
C4 i4 0 7.95775e-11
Bsrc vp out I=v(i5)*(pwr(max(v(vp)-0.8-v(out),0),2)/(pwr(max(v(vp)-0.8-v(out),0),2)+0.0025))*(1+max(v(vp)-v(out),0)/1503.96)
Bsnk out vn I=v(i4)*(pwr(max(v(out)-v(vn)-0.6,0),2)/(pwr(max(v(out)-v(vn)-0.6,0),2)+0.0025))*(1+max(v(out)-v(vn),0)/1503.96)
Cout out vn 4.75e-12
Rleak out vn 3e+11
Rleak2 out vp 3e+11
Bbp inp vn I=v(ia)*v(w)*0.5*(1+tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))/(0.5*pwr(10,log10(min(max(v(ia),1e-7),1e-3)))/pwr(10,((0.041643)*log10(min(max(v(ia),1e-7),1e-3))+(1.24808))*log10(min(max(v(ia),1e-7),1e-3))+(-2.03586)))
Bbn inn vn I=v(ia)*v(w)*0.5*(1-tanh((v(inp)-v(inn))/(2*(8.617333e-5*(temper+273.15)))))/(0.5*pwr(10,log10(min(max(v(ia),1e-7),1e-3)))/pwr(10,((0.041643)*log10(min(max(v(ia),1e-7),1e-3))+(1.24808))*log10(min(max(v(ia),1e-7),1e-3))+(-2.03586)))
Rdiff inp inn 2.462e+11
Cinp inp vn 5.96e-12
Cinn inn vn 5.96e-12
Bq vp vn I=2.1*v(ia)
D2 dbias inn DLIN
D3 dbias inp DLIN
Q12 vp bufin q13b QBUF
Q13 vp q13b bufout QBUF
.model DBIAS D(IS=2.39893e-15 N=2.1709 RS=0)
.model DLIN D(IS=2.65763e-16 N=1)
.model QBUF NPN(IS=2.65763e-16 BF=104.3)
.ends LM13700_OTA
```

## 5. Checks in ngspice (`check.log`; 25 °C sheet, ngspice at its default 27 °C)

Tolerance: figure points ±15 %, table typicals ±5 % (bias voltage ±20 mV, figure voltages ±25 mV, swing
±50 mV table / ±0.1 V figure, CMR ±0.15 V), and inside every min/max. CMR is measured as the common-mode voltage
where gm falls to half.

### CA3080 (±15 V)

| Check | Sheet (source) | Model | |
|---|---|---|---|
| gm @500 µA | 9600 µS [6700–13000] (table) | 9685 µS | OK |
| gm @0.10 / 1.03 / 11.6 / 620 µA | 2.0 / 19.8 / 222 / 11080 µS (Fig 21) | 1.95 / 19.9 / 224 / 12010 | OK ×4 |
| peak Iout RL=0 @5 µA | 5 µA [A: 3–7] (table) | 5.01 | OK |
| peak Iout RL=0 @500 µA | 500 µA [350–650] (table) | 501 | OK |
| peak Iout @0.10 / 2.19 / 729 µA | 0.104 / 2.19 / 763 µA (Fig 17) | 0.101 / 2.19 / 730 | OK ×3 |
| peak Iout @468 µA | 405 µA (Fig 17) | 469 | **MISS** (+16 %; figure below the table's own 500 typ; table wins) |
| bias voltage @500 µA | 0.71 V (table) | 0.721 | OK |
| bias voltage @0.10 / 420 / 973 µA | 497 / 704 / 734 mV (Fig 27) | 503 / 710 / 740 | OK ×3 |
| Ib @500 µA | 2 µA [max 5] (table) | 1.985 | OK |
| Ib @0.10 / 0.58 / 972 µA | 1.37 / 5.47 / 3568 nA (Fig 16) | 1.30 / 5.82 / 3525 | OK ×3 |
| supply @500 µA | 1 mA [0.8–1.2] (table) | 1.000 | OK |
| supply @0.41 / 9.6 µA | 0.81 / 17.9 µA (Fig 19) | 0.82 / 19.2 | OK ×2 |
| supply @101 µA | 175 µA (Fig 19) | 201 | **MISS** (+15 %; figure ≈1.75·Iabc vs table 2·Iabc) |
| Rin @500 µA | 26 kΩ [min 10] (table) | 26.1 | OK |
| Rin @9.7 / 135 / 440 µA | 0.785 / 0.0762 / 0.0264 MΩ (Fig 26) | 0.788 / 0.0810 / 0.0291 | OK ×3 |
| Rin @0.10 µA | 33.6 MΩ (Fig 26) | 39.9 | **MISS** (+19 %: Fig 16's Ib there gives 2VT/Ib = 37.7 MΩ, the two figures disagree) |
| Rout @500 µA | 15 MΩ (table) | 14.8 | OK |
| Rout @0.19 / 109 / 349 / 945 µA | 34460 / 56.0 / 17.7 / 6.38 MΩ (Fig 29) | 29220 / 68.0 / 21.2 / 7.82 | **MISS ×4** (Fig 29 is ≈ 6100 V/Iabc, 12.2 MΩ at 500 µA; table 15 MΩ wins) |
| open-loop bandwidth @500 µA | 2 MHz (table) | 2.00 | OK |
| Cout / Cin @500 µA, 1 MHz | 5.6 / 3.6 pF (table) | 5.62 / 3.60 | OK |
| CMR + / − @500 µA | +13.6 / −14.6 V [±12] (table) | +13.55 / −14.55 | OK |
| peak out RL=∞ @5 µA | +13.8 / −14.5 V [±12] (table) | +13.80 / −14.50 | OK |
| peak out RL=∞ @500 µA | +13.5 / −14.4 V [±12] (table) | +13.50 / −14.40 | OK |
| peak out @0.10 µA | +14.09 / −14.48 V (Fig 18) | +14.05 / −14.58 | OK / **MISS** (0.10 V) |
| peak out @992 µA | +13.36 / −14.36 V (Fig 18) | +13.46 / −14.39 | **MISS** (0.10 V) / OK |
| diff. input current, Iabc 0, 4 V | 0.008 nA (table) | 0.008 | OK |
| slew, uncompensated | 75 V/µs (table) | 46.2 (follower, no load: Iabc/(Cout + Cin of −in)) | **MISS** (sheet's test load not given; Iabc/Cout alone is 89) |
| converges | Iabc 0; pin open; .dc Iabc 0–2 mA; .tran Iabc via 10 k from a −1…9 V ramp, 9 V single supply | all ran | OK |

### LM13700 (±15 V)

| Check | Sheet (source) | Model | |
|---|---|---|---|
| gm @500 µA | 9600 µS [6700–13000] (table) | 9762 | OK |
| gm @4.5 / 150 / 450 µA | 99.8 / 3185 / 9377 µS (Fig 8) | 87.9 / 2928 / 8785 | OK ×3 (figure runs 7–14 % above the table) |
| peak Iout RL=0 @5 / 500 µA | 5 / 500 µA [350–650] (table) | 5.05 / 505 | OK |
| peak Iout @2.5 / 15 / 45 µA | 3.30 / 19.2 / 55.2 µA (Fig 4) | 2.53 / 15.2 / 45.5 | **MISS ×3** (Fig 4 reads 1.2–1.3 × Iabc; table 1.0 × wins) |
| bias voltage @0.1 / 1 / 10 / 100 / 1000 µA | 977 / 1106 / 1240 / 1366 / 1485 mV (Fig 10) | 985 / 1114 / 1244 / 1373 / 1502 | OK ×5 |
| Ib @500 µA | 0.4 µA [max 5] (table) | 1.99 | **MISS** typ (inside max) — see judgements |
| Ib @0.15 / 1.5 / 15 / 150 / 450 µA | 2.66 / 11.7 / 87.2 / 619 / 1748 nA (Fig 3) | 2.44 / 12.8 / 81.8 / 632 / 1793 | OK ×5 |
| supply @500 µA, one / both | 1.3 / 2.6 mA (table) | 1.302 / 2.605 | OK |
| Rin @500 µA | 26 kΩ [min 10] (table) | 26.1 | OK |
| Rin @1 / 10 / 100 / 1000 µA | 6.28 / 0.886 / 0.105 / 0.0125 MΩ (Fig 9) | 5.48 / 0.889 / 0.119 / 0.0132 | OK ×4 |
| Rin @0.1 µA | 38.4 MΩ (Fig 9) | 27.9 | **MISS** (−27 %; Fig 3 and Fig 9 disagree at their low end) |
| Rout @1 / 10 / 100 / 1000 µA | 1508 / 149 / 14.9 / 1.61 MΩ (Fig 12) | 1485 / 150 / 15.0 / 1.50 | OK ×4 |
| open-loop bandwidth | 2 MHz (table) | 2.00 | OK |
| Cout / Cin @500 µA | 4.75 / 5.96 pF (Fig 11) | 4.75 / 5.96 | OK |
| CMR + / − | ±13.5 V [±12] (table) | +13.45 / −13.45 | OK |
| peak out RL=∞ @5 and 500 µA | +14.2 / −14.4 V [±12] (table) | +14.20 / −14.40 (both) | OK |
| diff. input current, Iabc 0, ±4 V | 0.02 nA [max 100] (table) | 0.020 | OK |
| buffer input current, footnote (1) | 0.5 µA [max 2] (table) | 0.500 | OK |
| peak buffer output, footnote (1) | ≥ 10 V (table) | 12.73 | OK |
| diode drop, 13 k from +15 V (Fig 17's bias) | ~0.7 V (8.2.2 text) | 0.732 | OK |
| bias pin @1 mA on −15 V | ~−13.6 V ("2 VBE", 8.2.2 text) | −13.50 | **MISS** 0.1 V (Fig 10 itself gives 1.485 V = −13.52; figure wins over the text's round 0.7 V) |
| slew | 50 V/µs "unity gain compensated" (table) | 41.2 (follower, no load) | **MISS** (compensation network not given) |
| Fig 13, no diodes, 10 / 20 / 40 / 80 mVpp | 0.065 / 0.26 / 1.16 / 5.0 % | 0.078 / 0.31 / 1.20 / 4.35 | OK ×4 (within 1.5×) |
| Fig 13, with diodes, 57 / 82 / 113 / 141 mVpp | 0.082 / 0.27 / 1.7 / 10.2 % | 0.0003 / 0.0006 / 0.0011 / 0.0017 | **MISS ×4** (model far cleaner, see judgements) |
| converges | as the CA3080 | all ran | OK |

### Pedal sanity checks (`pedal.log`, 9 V single supply, V− at ground, 1 kHz)

CA3080 VCA (signal 300 mV pk via 47 k into +, 1 k from each input to a 10 k/10 k 4.5 V reference, 10 k load to
the reference, Iabc via a resistor from +9 V):

| Rabc | Iabc | Gain | THD | Out DC |
|---|---|---|---|---|
| 1 M | 8.39 µA | −29.5 dB | 0.120 % | 4.499 V |
| 330 k | 25.4 µA | −19.9 dB | 0.119 % | 4.498 V |
| 100 k | 83.4 µA | −9.7 dB | 0.115 % | 4.495 V |
| 33 k | 252 µA | −0.3 dB | 0.107 % | 4.488 V |
| 15 k | 552 µA | +6.2 dB | 0.097 % | 4.476 V |

Gain follows Iabc at 20 dB/decade, as gm = Iabc/2VT. 3 V pk in at 15 k: 18.8 % THD (tanh compression).

LM13700 VCA (TI Fig 17 scaled to 9 V: 4.7 k from +9 V to the diode-bias pin, 500 Ω per input to 4.5 V (Fig 17's
1 k pot centred), 30 k from the source, RL 30 k, buffer into 5 k to ground), 1 V pk in: gain −41.2 / −31.6 /
−21.3 / −11.8 / −5.1 dB for Iabc 7.8 / 23 / 76 / 230 / 502 µA (Rabc 1 M … 15 k); buffer out DC 3.145 V.
Needs a **stiff 4.5 V reference**: the ~0.8 mA diode bias flows into it and pulled a 10 k/10 k divider to 6.4 V
(a real build has the same problem).

Distortion at the OTA output, diodes vs pin open at equal output (Rabc 33 k, Iabc 230 µA):

| Iout/Iabc | Diodes, 4.7 k bias | Pin open | Diodes, 0.8 mA current source | Pin open |
|---|---|---|---|---|
| 0.04 | 0.095 % | 0.012 % | 0.002 % | 0.011 % |
| 0.11 | 0.284 % | 0.108 % | 0.014 % | 0.100 % |
| 0.22 | 0.566 % | 0.430 % | 0.057 % | 0.396 % |
| 0.33 | 0.842 % | 0.962 % | 0.147 % | 0.885 % |
| 0.44 | 1.093 % | 1.730 % | 0.380 % | 1.584 % |

With the diodes fed by a current source (as TI 7.3.2 assumes) distortion drops 4–7×. With a plain 4.7 k from
9 V, the diodes' total current moves with the signal (the inputs ride up by Is·250 Ω, ~5 % of the 4.7 k drop),
which adds a 2nd harmonic ≈ 2.5 %·(Iout/Iabc); the diodes only win above ~0.3 of full scale. That is the circuit,
not the model (TI's 13 k from +15 V moves it 4× less). Worth knowing for the app's LM13700 guidance.

## 6. Judgements and open points (for the user)

1. **Table over figure** (D-163) where they disagree: CA3080 Rout (15 MΩ table vs Fig 29's ~12.2 MΩ at 500 µA),
   supply current (2·Iabc vs Fig 19's ~1.75–1.95), peak output current (= Iabc vs Fig 17 at 468 µA); LM13700
   peak output current (= Iabc vs Fig 4's 1.2–1.3×), gm (Iabc/2VT = table; Fig 8 runs 7–14 % above).
2. **LM13700 input bias current: the figure over the table** (the one exception). The table says 0.4 µA typ,
   but its own Rin 26 kΩ typ needs Ib = 2VT/Rin ≈ 2 µA (the diff pair's Ib·Rin = 2VT, which the CA3080's table
   meets exactly: 2 µA × 26 kΩ), and Fig 3 (1.75 µA at 450 µA) and Fig 9 (22 kΩ at 500 µA) agree with 2 µA.
   The model gives 1.99 µA (inside the 5 µA max). The alternative (0.4 µA) would make Rin 130 kΩ, missing the
   table's Rin and both figures. **User to confirm.**
3. **Fig 13 "using diodes" is a MISS: the model is ~100× cleaner** (0.0003 % vs 0.082 % at 57 mVpp), because
   ideal ngspice junctions and an ideal tanh cancel exactly (TI eq. 7). The real residue comes from junction
   mismatch and ohmic resistances the sheet doesn't give. `fit_lin.py` tried one series resistance on the
   diodes: best 2.2 Ω, rms error ×2.7 (0.26 % vs 0.09 % at 59 mVpp, 0.66 % vs 2.4 % at 118 mVpp): the wrong
   shape, so not kept. The "no diodes" curve (pure tanh) matches within 1.5×. In a pedal the bias resistor's
   own distortion (above) is larger than the chip's residue anyway.
4. **Slew rates** are not checkable: neither sheet gives the uncompensated test load or the compensation; the
   model slews at Iabc / (capacitance on the output) by construction.
5. **Not modelled:** input offset voltage/current (per unit, random sign; 0.3–0.4 mV typ), CMRR (infinite),
   noise (Figs 14, 15), temperature behaviour beyond VT, Iabc-dependence of Cin/Cout (fixed at their 500 µA values:
   at low Iabc Fig 28 gives CA3080 Cout ~2.1 pF vs 5.6, LM13700 Cin ~4.5 vs 5.96 — irrelevant at audio),
   the LM13700 buffer's 20 mA limit (abs max only), the buffer's own VBE curve (none in the sheet).
6. **Swing knee** (50 mV) and the CMR knee use the same smooth step — a judgement, no sheet figure.
7. **9 V single supply** is below the LM13700's recommended 9.5 V minimum (TI 6.2); the model runs there
   (headrooms 0.8/0.6 V, CMR 1.5 V each side → inputs must sit between 1.5 and 7.5 V).
8. The uncompensated CA3080 follower rings (2 MHz pole well under its gm/C crossing): consistent with the sheet
   showing the follower only with a compensation network (Fig 1).

## 7. Draft DECISIONS entry

**D-18x — The OTAs: our own CA3080 and LM13700 models from their sheets** (2026-11-03, Phase 9b; D-159; the
D-149 part type "OTA")
- **Why ours:** Intersil/Renesas publish no CA3080 model. TI's LM13700 download (SNOM267) is National's old
  transistor card, "may be copied and distributed" but under TI's evaluation terms, and it warns it overstates
  bandwidth by 2×. Both are now our behavioural subcircuits built from the sheets (`.claude/skills/fit-model/worked/ota/build_ota.py`).
- **How:** the sheet's own description (TI 7.3.1): the pair splits Iabc as (1 ± tanh(Vd/2VT))/2; one half is
  sourced from V+, the other sunk to V−, each stopping at the sheet's swing limit; Early gives Rout = VA/Iabc;
  a 2 MHz pole on the halves; gm goes to zero outside the common-mode range. Iabc is the current into a junction
  from the bias pin to V− fitted to the bias-voltage figure, so Iabc = 0, a pin left open or pulled below V− all
  just turn it off. The inputs draw the pair's base currents (fitted to the bias-current figure), which gives
  the sheet's input resistance by itself (Ib·Rin = 2VT).
- **CA3080** (Intersil 475.4): every table typical met (gm 9685 µS vs 9600, peak current, bias 0.721 V vs 0.71,
  Ib 1.99 µA vs 2, Rin 26.1 kΩ vs 26, Rout 14.8 MΩ vs 15, 2 MHz, swing to ±0.01 V at 5 and 500 µA, supply 1 mA).
  Vector figures within 15 % except Fig 29 (Rout, the table's 15 MΩ wins) and three single points.
- **LM13700** (TI SNOSBW2F): one amplifier `LM13700_OTA` with its linearising diodes and Darlington buffer as
  ngspice junctions; the dual is two instances. Raster figures read by pixel. Table met except the input bias
  current: **Fig 3's 2 µA over the table's 0.4 µA** (the table's own 26 kΩ needs 2 µA). Distortion without the
  diodes matches Fig 13; with them the model is ~100× cleaner than the figure (ideal junctions cancel exactly;
  the sheet gives nothing to fit the residue to).
- **Pedals:** checked at 9 V single supply (gain follows Iabc at 20 dB/decade; converges from Iabc = 0). The
  LM13700's diodes need a current-source bias (or a large resistor from a high voltage) to help: a 4.7 k from
  9 V adds a 2nd harmonic that beats them below ~0.3 of full scale; and a stiff 4.5 V reference.
- *Alternatives:* TI's National card (licence layered with TI's evaluation terms; known 2× bandwidth error);
  transistor-level models (more parameters than the sheets pin down); the table's 0.4 µA LM13700 bias current
  (misses its own Rin and two figures); a diode series resistance fitted to Fig 13 (wrong shape, ×2.7 rms).
