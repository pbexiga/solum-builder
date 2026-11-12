# CD4049UB, one inverter: our own fit to TI SCHS046L

Sheet: `data/spec-sheets/CD4049UB_TI_SCHS046L.pdf` (TI, CD4049UB and CD4050B, SCHS046L, Aug 1998, rev. Feb 2026).
Files here: `sheet.py` (every number used, with page), `digitise.py` + `probe.py` (vector figures to values, host python),
`inv.py` (the subcircuit and the measurements), `fit.py` (writes `params.json`), `write_lib.py` (writes `CD4049UB.lib`),
`check.py` (the table below, saved in `check.out`), `stage_test.py` (a Red Llama-style stage).
Run in the dev image: `podman run --rm -v "$PWD":/src:z -w /src -e PYTHONPATH=/src -e HOME=/tmp solum-builder:dev python .claude/skills/fit-model/worked/cd4049/fit.py`
(then `write_lib.py`, `check.py`).

## A maker's card?
TI publishes "CD4049UB PSPICE Model (Rev. A)", SCHM019A.ZIP (https://www.ti.com/lit/zip/SCHM019, linked from
https://www.ti.com/product/CD4049UB). It is a **behavioural logic-gate model** ("generic logic gate behavioral pspice
model V2 ... automated model which generalizes parts under same family", a NAND with tied inputs, switch-model output):
no transistors, so no linear region, so useless for a biased inverter. Its notice: "(C) Copyright 2019 Texas
Instruments Incorporated. All rights reserved", an as-is disclaimer, no grant to redistribute; so it may not ship
(D-159) even if it were useful. Not used.

## The card (`CD4049UB.lib`)
```
* CD4049UB, one inverter of six (unbuffered hex inverter), for linear (biased) use
* Our own fit to TI's CD4049UB/CD4050B data sheet SCHS046L (Aug 1998, rev. Feb 2026), 25 C typical
* Pins: in out vdd vss. Per chip (PDIP-16 CD4049UBE): VCC 1, VSS 8; inputs A3 B5 C7 D9 E11 F14,
* outputs G2 H4 I6 J10 K12 L15; 13 and 16 not connected.
* N and P channel: ngspice VDMOS, source on its rail; body diodes are the output's drain-bulk diodes.
* DIN: the input diode to VSS (sheet p. 1 schematic); DSUP: the VSS->VDD diode; ngspice default values.
.subckt CD4049UB_INV in out vdd vss
MN out in vss CD4049UB_N
MP out in vdd CD4049UB_P
DIN vss in CD4049UB_D
DSUP vss vdd CD4049UB_D
.model CD4049UB_N VDMOS(vto=1.3915 kp=0.0031091 theta=0.048075 mtriode=1.7236 lambda=0.0094943
+ rs=1.2486 rd=0.01 ksubthres=0.1 cgs=2.463e-12 cgdmax=5.0373e-12 cgdmin=5.0373e-12 cjo=4.6998e-12)
.model CD4049UB_P VDMOS(pchan vto=-0.43687 kp=0.0012393 theta=0.12275 mtriode=1.9884
+ lambda=0.031518 rs=27.07 rd=0.01 ksubthres=0.1 cgs=2.463e-12 cgdmax=5.0373e-12 cgdmin=5.0373e-12
+ cjo=4.6998e-12)
.model CD4049UB_D D
.ends CD4049UB_INV
```

**Why VDMOS:** a CMOS inverter with each body on its source is two three-terminal MOSFETs. ngspice's VDMOS (already
used for 2N7000/LND150, D-175/D-178) adds what level 1 lacks: MTRIODE (saturation at (VGS-VTO)/MTRIODE) and THETA
(mobility reduction), needed because Figure 5-3's 5 V curve saturates at a ~2.3 V knee while the 10 V and 15 V curves
nearly overlap at low VDS. A first level-1 fit (with RS/RD) missed Figure 5-3 by -33 %/+29 % and drove LAMBDA to 0
(open-loop gain ~14 000). VDMOS's body diode is the real output drain-bulk diode (OUT->VDD, VSS->OUT); KSUBTHRES (left
at the default 0.1 V) keeps the VTC smooth. Capacitances are VDMOS's CGS, CGD (CGDMAX = CGDMIN: linear), CJO (output
junction), shared by both sides (the sheet can't separate them).
**Input protection:** the sheet's schematic (p. 1) draws diodes from VSS to IN (either side of an unvalued R) and
VSS to VCC, and **no IN->VCC diode** (p. 1: VIH may exceed VCC). Modelled as DIN (VSS->in) and DSUP (VSS->vdd) at
ngspice's default diode values (the sheet gives none); the R is left out (no value). Note p. 17 says the opposite
("input clamp diodes to VCC"); the schematic and p. 1 are followed.

## Pinout, PDIP-16 (CD4049UBE): Figure 4-1 and "Pin Functions: CD4049UB", p. 3
| Pin | Name | Function | | Pin | Name | Function |
|---|---|---|---|---|---|---|
| 1 | VCC | supply + | | 16 | NC | not connected |
| 2 | G | output 1 (G = not A) | | 15 | L | output 6 (L = not F) |
| 3 | A | input 1 | | 14 | F | input 6 |
| 4 | H | output 2 (H = not B) | | 13 | NC | not connected |
| 5 | B | input 2 | | 12 | K | output 5 (K = not E) |
| 6 | I | output 3 (I = not C) | | 11 | E | input 5 |
| 7 | C | input 3 | | 10 | J | output 4 (J = not D) |
| 8 | VSS | supply − | | 9 | D | input 4 |

Inverters (in -> out): A3->G2, B5->H4, C7->I6, D9->J10, E11->K12, F14->L15. Same pinout for D, DW, NS, PW. P. 15:
pin 16 (NC) is not connected internally. (KiCad-style units: six inverter units plus a power unit with VCC 1, VSS 8.)

## Figures (all vector: `pdfimages -list` finds no images on pp. 12-13; read with `digitise.py`)
Axes were mapped by hand from the grid lines and tick labels (`probe.py`), piecewise linear between labelled lines,
because `plots.py` could not match some labels (Figure 5-1's x labels, Figures 5-5/5-6 above the plot, Figure 5-9).
| Figure | Page | What | Used for |
|---|---|---|---|
| 5-1 min/max VTC, 5 V, 25 °C | 12 | process extremes | check: switch between them (1.096 / 3.986 V) |
| 5-2, 5-4 (part), 5-8 | 12-13 | CD4050B | not used |
| 5-3 typical sink, VGS = 5/10/15 V | 12 | ID vs VDS (10 V and 15 V drawn as 5-segment polylines) | fit (N) |
| 5-4 minimum sink | 12 | ID vs VDS | check (≥ min) |
| 5-5 typical source, VGS = -5/-10/-15 V | 12 | ID vs VDS | fit (P) |
| 5-6 minimum source | 12 | ID vs VDS | check (≥ min) |
| 5-7 typical VTC vs temperature, 5 and 10 V | 13 | **only -55 °C and 125 °C drawn**; which is which from the label arrows | fit and check, 25 °C taken 80/180 of the way from -55 to 125 °C |
| 5-9 power per inverter vs f, CL 50/15 pF | 13 | log-log straight lines | stage-2 fit and check, read at 100 kHz (x: 10 kHz at 216.6 pt, 49.6 pt/decade; y: 10^3 µW at 350.1 pt, 34.8 pt/decade, from the minor grid) |
| 8-2 power vs input rise time | 18 | | not used |

Figure 5-7 readings (`digitise.crossing`, `vi_at`): VO = VI at 5 V: 2.714 (-55 °C), 2.358 (125 °C) -> 2.556 V at 25 °C;
at 10 V: 4.385, 4.090 -> 4.254 V. Average slope VO 70 % -> 30 % of VCC: 10 V: 30.9 / 24.5 -> 28.1; 5 V: 18.1 / 383 (the
125 °C curve is drawn vertical there), so 5 V is a check only.

## Electrical characteristics used (25 °C)
- IOL min/typ (p. 6 and p. 9): 4.5 V @0.4 V 2.6/5.2 mA; 5 V @0.4 V 3.2/6.4; 10 V @0.5 V 8/16; 15 V @1.5 V 24/48.
- IOH min/typ: 5 V @4.6 V -0.65/-1.2 mA; 5 V @2.5 V -2.1/-3.9; 10 V @9.5 V -1.65/-3; 15 V -4.3/-8 (row printed
  "VOUT = 1.3V": read as 13.5 V, VCC − 1.5 V like the sink row).
- VOL ≤ 0.05 V, VOH ≥ VCC − 0.05 V (p. 9-10). VIL max (CD4049UB, p. 7): 1 / 2 / 2.5 V for VOUT ≥ 4.5 / 9 / 13.5 V at
  5/10/15 V. VIH min: 4 / 8 / 12.5 V for VOUT ≤ 0.5 / 1 / 1.5 V.
- IDD max (chip, p. 8): 1 / 2 / 4 / 20 µA at 5/10/15/20 V (the 15 V row prints "VCC = 4V"; read as 15 V). Typ 0.02 µA.
- IIN ≤ ±0.1 µA at 18 V (p. 10). CIN 15 typ / 22.5 max pF (p. 11).
- AC (p. 11; CL 50 pF, RL 200 kΩ, input tr = tf = 20 ns): tPLH 60/32/25 typ, 120/65/50 max ns at 5/10/15 V;
  tPHL 32/20/15, 65/40/30; tTLH 80/40/30, 160/80/60; tTHL 30/20/15, 60/40/30.
- Recommended VCC 3-18 V (p. 6).

## Judgements
1. **Table typical IOH vs Figure 5-5.** The table's typical source currents are about the Figure 5-6 *minimum*
   curve (5 V at 0.4 V: table typ 1.2 mA, Fig 5-6 min 1.28 mA, Fig 5-5 typ 2.0 mA; at 2.5 V: 3.9 / 3.7 / 6.2 mA),
   while the table's typical IOL agrees with Figure 5-3. Figure 5-5 is consistent with Figure 5-7's switching
   points (P:N strength ratio); fitted to the table's IOH instead, the P side lands on LAMBDA = 1 and VTO = 3.8 V.
   So **Figure 5-5 is used and the four "IOH typ" lines are reported as misses** (the model is 1.3-2x the table's typ;
   every IOH **min** line passes). This departs from "the table wins" (D-163/D-175) because here the table's typ
   contradicts two figures, not one.
2. **No 25 °C VTC is drawn**: taken on the straight line between -55 °C and 125 °C (80/180 of the way).
3. **Thresholds.** Started from the N curves alone, VTO_n runs to 2.7 V and VTO_n + VTO_p passes 5 V, so at 5 V the
   switch happens below both thresholds (gain ~1000 at 5 V, switch at 2.6 V even at 3 V supply). The fit starts
   instead from where Figure 5-7's 25 °C VTC leaves the rails (VTO_n ~1.7, VTO_p ~1.9 V) and fits everything jointly.
   It ends at VTO_n 1.39 V, VTO_p 0.44 V — the P threshold is low for real CMOS, but nothing in the sheet pins it
   better; the curve shapes are about equally good across VTO 1.4-2.7 V.
4. **Gain (LAMBDA_p)** is set by Figure 5-7's drawn 10 V slope (25 °C value 28.1); LAMBDA_n by Figure 5-3's 5 V
   plateau. These are drawn lines; the gain is only as good as the drawing (5 V: -55 °C drawn 18, model 69).
5. **Speed vs the AC table.** With the DC strengths of Figures 5-3/5-5, the AC table's typical times would need about
   70 pF extra on the output, which Figure 5-9 (power ∝ C) rules out (at 5 V it implies ~64 pF total with the 50 pF
   load). Capacitances are fitted to CIN and Figure 5-9; the model then switches about 2x faster than the typical
   times and meets every max.
6. **IDD** of the model is one inverter's leakage (nA), against the chip's limit; it passes trivially (no leakage
   model beyond VDMOS defaults).

## Check (ngspice, 25 °C) — `check.py`, criteria fixed before running
Typical curves ±20 % per point; minimum curves and min/max lines: the right side; Figure 5-7: the 25 °C value between
the -55 °C and 125 °C curves; Figure 5-9 ±25 %; table typicals ±20 %.

| Check | Model | Sheet (25 °C) | |
|---|---|---|---|
| Fig 5-3 typ sink, VCC 5 V (10 pts) | -25% to -9% | ±20 % (typ curve) | MISS |
| Fig 5-3 typ sink, VCC 10 V (5 pts) | -32% to +4% | ±20 % (typ curve) | MISS |
| Fig 5-3 typ sink, VCC 15 V (5 pts) | -25% to +15% | ±20 % (typ curve) | MISS |
| Fig 5-4 min sink, VCC 5 V (7 pts) | lowest +57% vs min | ≥ min curve | OK |
| Fig 5-4 min sink, VCC 10 V (7 pts) | lowest +19% vs min | ≥ min curve | OK |
| Fig 5-4 min sink, VCC 15 V (3 pts) | lowest +93% vs min | ≥ min curve | OK |
| Fig 5-5 typ source, VCC 5 V (13 pts) | -15% to +36% | ±20 % (typ curve) | MISS |
| Fig 5-5 typ source, VCC 10 V (12 pts) | +0% to +20% | ±20 % (typ curve) | OK |
| Fig 5-5 typ source, VCC 15 V (11 pts) | +2% to +19% | ±20 % (typ curve) | OK |
| Fig 5-6 min source, VCC 5 V (7 pts) | lowest +66% vs min | ≥ min curve | OK |
| Fig 5-6 min source, VCC 10 V (8 pts) | lowest +41% vs min | ≥ min curve | OK |
| Fig 5-6 min source, VCC 15 V (7 pts) | lowest +48% vs min | ≥ min curve | OK |
| Fig 5-1 VTC at 5 V: switch between min and max curves | 2.566 V | 1.096-3.986 V | OK |
| Fig 5-7 switch (VO = VI), VCC 5 V | 2.566 V | 2.358-2.714 V (125/-55 °C) | OK |
| Fig 5-7 VI at VO = 90% VCC, VCC 5 V | 2.40 V | 2.00-2.37 V | MISS |
| Fig 5-7 VI at VO = 10% VCC, VCC 5 V | 2.64 V | 2.69-2.92 V | MISS |
| Fig 5-7 slope VO 70->30 % VCC, VCC 5 V | 68.6 | 18.1-383.1 (drawn) | OK |
| Fig 5-7 switch (VO = VI), VCC 10 V | 4.257 V | 4.09-4.385 V (125/-55 °C) | OK |
| Fig 5-7 VI at VO = 90% VCC, VCC 10 V | 3.45 V | 3.42-3.74 V | OK |
| Fig 5-7 VI at VO = 10% VCC, VCC 10 V | 4.65 V | 4.52-4.71 V | OK |
| Fig 5-7 slope VO 70->30 % VCC, VCC 10 V | 28.2 | 24.5-30.9 (drawn) | OK |
| Fig 5-9 power at 100 kHz, VCC 5 V, CL 50 pF | 179 µW | 160 µW ±25 % | OK |
| Fig 5-9 power at 100 kHz, VCC 10 V, CL 50 pF | 737 µW | 919 µW ±25 % | OK |
| Fig 5-9 power at 100 kHz, VCC 15 V, CL 50 pF | 1783 µW | 2786 µW ±25 % | MISS |
| Fig 5-9 power at 100 kHz, VCC 10 V, CL 15 pF | 393 µW | 310 µW ±25 % | MISS |
| IOL at VCC 4.5 V, VOUT 0.4 V | 4.81 mA | min 2.6 | OK |
| IOL typ at VCC 4.5 V, VOUT 0.4 V | 4.81 mA | typ 5.2 ±20 % | OK |
| IOL at VCC 5 V, VOUT 0.4 V | 5.56 mA | min 3.2 | OK |
| IOL typ at VCC 5 V, VOUT 0.4 V | 5.56 mA | typ 6.4 ±20 % | OK |
| IOL at VCC 10 V, VOUT 0.5 V | 14.33 mA | min 8 | OK |
| IOL typ at VCC 10 V, VOUT 0.5 V | 14.33 mA | typ 16 ±20 % | OK |
| IOL at VCC 15 V, VOUT 1.5 V | 55.64 mA | min 24 | OK |
| IOL typ at VCC 15 V, VOUT 1.5 V | 55.64 mA | typ 48 ±20 % | OK |
| IOH at VCC 5 V, VOUT 4.6 V | -2.20 mA | min -0.65 | OK |
| IOH typ at VCC 5 V, VOUT 4.6 V | -2.20 mA | typ -1.2 ±20 % | MISS |
| IOH at VCC 5 V, VOUT 2.5 V | -7.91 mA | min -2.1 | OK |
| IOH typ at VCC 5 V, VOUT 2.5 V | -7.91 mA | typ -3.9 ±20 % | MISS |
| IOH at VCC 10 V, VOUT 9.5 V | -4.00 mA | min -1.65 | OK |
| IOH typ at VCC 10 V, VOUT 9.5 V | -4.00 mA | typ -3.0 ±20 % | MISS |
| IOH at VCC 15 V, VOUT 13.5 V | -13.52 mA | min -4.3 | OK |
| IOH typ at VCC 15 V, VOUT 13.5 V | -13.52 mA | typ -8.0 ±20 % | MISS |
| VOL at VCC 5 V (VIN = VCC, no load) | 7.47e-05 mV | ≤ 50 mV | OK |
| VOH at VCC 5 V (VIN = 0, no load) | 5.0000 V | ≥ 4.95 V | OK |
| VOL at VCC 10 V (VIN = VCC, no load) | 4.34e-05 mV | ≤ 50 mV | OK |
| VOH at VCC 10 V (VIN = 0, no load) | 10.0000 V | ≥ 9.95 V | OK |
| VOL at VCC 15 V (VIN = VCC, no load) | 3.63e-05 mV | ≤ 50 mV | OK |
| VOH at VCC 15 V (VIN = 0, no load) | 15.0000 V | ≥ 14.95 V | OK |
| VIL max 1.0 V at VCC 5 V: VOUT | 5.000 V | ≥ 4.5 V | OK |
| VIL max 2.0 V at VCC 10 V: VOUT | 9.923 V | ≥ 9.0 V | OK |
| VIL max 2.5 V at VCC 15 V: VOUT | 14.781 V | ≥ 13.5 V | OK |
| VIH min 4.0 V at VCC 5 V: VOUT | 0.017 V | ≤ 0.5 V | OK |
| VIH min 8.0 V at VCC 10 V: VOUT | 0.062 V | ≤ 1.0 V | OK |
| VIH min 12.5 V at VCC 15 V: VOUT | 0.078 V | ≤ 1.5 V | OK |
| IDD at VCC 5 V (one inverter; the limit is the chip's) | 0.00115 µA | ≤ 1.0 µA | OK |
| IDD at VCC 10 V (one inverter; the limit is the chip's) | 0.00131 µA | ≤ 2.0 µA | OK |
| IDD at VCC 15 V (one inverter; the limit is the chip's) | 0.00148 µA | ≤ 4.0 µA | OK |
| IDD at VCC 20 V (one inverter; the limit is the chip's) | 0.00164 µA | ≤ 20.0 µA | OK |
| IIN at VCC 18 V, VIN 0 or 18 V | 1.8e-05 µA | ≤ 0.1 µA | OK |
| CIN (VCC 10 V, input low / high) | 15.0 / 15.0 pF | typ 15, max 22.5 pF | OK |
| tPLH at VCC 5 V | 27.8 ns | typ 60, max 120 | OK |
| tPLH at VCC 10 V | 17.3 ns | typ 32, max 65 | OK |
| tPLH at VCC 15 V | 14.4 ns | typ 25, max 50 | OK |
| tPHL at VCC 5 V | 17.2 ns | typ 32, max 65 | OK |
| tPHL at VCC 10 V | 8.8 ns | typ 20, max 40 | OK |
| tPHL at VCC 15 V | 6.2 ns | typ 15, max 30 | OK |
| tTLH at VCC 5 V | 39.2 ns | typ 80, max 160 | OK |
| tTLH at VCC 10 V | 25.5 ns | typ 40, max 80 | OK |
| tTLH at VCC 15 V | 21.2 ns | typ 30, max 60 | OK |
| tTHL at VCC 5 V | 17.9 ns | typ 30, max 60 | OK |
| tTHL at VCC 10 V | 10.3 ns | typ 20, max 40 | OK |
| tTHL at VCC 15 V | 9.3 ns | typ 15, max 30 | OK |
| Works at VCC 3 V (rec. min): VOH / VOL / switch | 3.000 / 0.00014 mV / 1.84 V | rail to rail | OK |

60 OK, 12 MISS

**Misses, in short:** Figure 5-3 points at low VDS (−25..−32 %, the first vertices of 5-segment polylines; the 5 V curve
sits 9-25 % low); Figure 5-5 at 5 V (+36 % at 1.5 V); Figure 5-7's 5 V shoulders by 0.03-0.05 V (the drawn 5 V
transition is wider than the model's); Figure 5-9 at 15 V (−36 %, likely crowbar current with the unknown input
edges) and 10 V/15 pF (+27 %); the four IOH typicals (judgement 1).

## Pedal numbers (no load, open loop):
  VCC  5 V: switching point VO = VI = 2.566 V, small-signal gain 68.5 (36.7 dB), 30-70 % slope 68.6, Rout at the switch 13.8 kΩ
  VCC  9 V: switching point VO = VI = 3.930 V, small-signal gain 32.0 (30.1 dB), 30-70 % slope 31.8, Rout at the switch 3.4 kΩ
  VCC 10 V: switching point VO = VI = 4.257 V, small-signal gain 28.4 (29.1 dB), 30-70 % slope 28.2, Rout at the switch 2.7 kΩ
  VCC 15 V: switching point VO = VI = 5.833 V, small-signal gain 18.8 (25.5 dB), 30-70 % slope 17.9, Rout at the switch 1.3 kΩ
  VCC 9 V, output at a rail: sink on-resistance 37 Ω, source on-resistance 128 Ω


Red Llama-style stage (`stage_test.py`: 9 V, 1 MΩ feedback, 100 kΩ + 100 nF in, 100 pF load): biased at 3.930 V,
closed-loop gain 7.4 (ideal 10; open-loop 32 with Rout 3.4 kΩ against the 1 MΩ), 6.65 at 10 kHz, 1.46 at 100 kHz.

## Draft DECISIONS entry
**D-1xx — The CD4049UB as our own VDMOS pair fitted to TI's sheet** (2026-11-03, Phase 9b; the D-149 part type "CMOS inverter (CD4049UBE)", under D-159)
- **No maker's card to ship:** TI's CD4049UB PSpice model (SCHM019A) is a behavioural logic gate (no linear region)
  under "all rights reserved"; not usable for a biased inverter, and not shippable.
- **The model:** one inverter, `.subckt CD4049UB_INV in out vdd vss`: an N- and a P-channel VDMOS with their sources
  on the rails (MTRIODE and THETA follow the sheet's early-saturating, overlapping curves where level 1 missed by a
  third), the body diodes as the output's own; the input diode to VSS and the VSS-VDD diode the sheet's schematic
  draws (no input diode to VDD: the input may go above VCC). The chip is six of these plus a power unit (D-176/D-179):
  PDIP-16 VCC 1, VSS 8, A3→G2, B5→H4, C7→I6, D9→J10, E11→K12, F14→L15, 13 and 16 NC (sheet p. 3).
- **Fitted** through ngspice to TI SCHS046L's vector figures: typical sink (Fig 5-3) and source (Fig 5-5) curves, the
  table's typical IOL, and the voltage transfer curve taken at 25 °C between Figure 5-7's -55 °C and 125 °C curves
  (switching point at 5 and 10 V, where it leaves the rails, its 10 V slope for the gain); then the capacitances to
  CIN (15 pF) and Figure 5-9's power per inverter.
- **Results:** switching point 2.566 V at 5 V and 4.257 V at 10 V (sheet, 25 °C: about 2.56 and 4.25); at 9 V it biases
  itself at 3.93 V with an open-loop gain of 32 (30 dB) and 3.4 kΩ out; every min/max line met (IOL, IOH, VOL, VOH, VIL,
  VIH, IDD, IIN, CIN, all propagation and transition times); curves within about −32 %/+36 % (worst at the low-VDS ends
  of the coarse 10 V/15 V polylines).
- **Departures:** the table's typical IOH are about the sheet's *minimum* source curve and contradict Figure 5-5 and
  Figure 5-7, so Figure 5-5 is used and the model is 1.3–2× the table's IOH typ (every IOH min met). The model is about
  twice as fast as the AC table's typical times (within every max): matching them would need ~70 pF more on the output,
  which Figure 5-9's power rules out. The gain rests on the drawn VTC slope (no gain figure in the sheet).
*Alternatives:* level-1 MOSFETs (−33 %/+29 % on Figure 5-3, LAMBDA to zero: a gain of thousands); fitting the table's
IOH typicals (a P side with LAMBDA 1, VTO 3.8 V); fitting the AC times with output capacitance (Figure 5-9 off by 2×);
TI's behavioural model (logic only, all rights reserved).
