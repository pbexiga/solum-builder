"""What TI's CD4049UB sheet says (SCHS046L, Aug 1998, rev. Feb 2026), 25 °C only.

Curve points were read off the sheet's vector figures by digitise.py (pages 12-13), thinned
to about 10 per curve with both ends kept. Currents are magnitudes in mA, voltages in V.
"""

SHEET = "TI SCHS046L"

# Figure 5-3 (p. 12), typical output low (sink) current, VGS = VCC: (VDS, ID mA) per VCC.
SINK_TYP = {
    5: [(0.32, 6.03), (0.49, 8.86), (0.78, 11.87), (1.05, 14.04), (1.42, 16.09), (1.82, 17.95),
        (2.31, 18.75), (3.02, 19.34), (3.71, 19.50), (4.97, 19.69)],
    10: [(0.33, 14.06), (0.71, 24.38), (1.29, 36.56), (1.97, 48.17), (3.13, 64.52)],
    15: [(0.20, 10.62), (0.58, 22.82), (1.06, 36.88), (1.55, 50.93), (2.09, 64.84)],
}
# Figure 5-5 (p. 12), typical output high (source) current, |VGS| = VCC: (|VDS|, |ID| mA).
SOURCE_TYP = {
    5: [(0.22, 1.47), (0.36, 2.20), (0.51, 2.70), (0.72, 3.26), (0.93, 3.80), (1.26, 4.47),
        (1.55, 4.93), (2.03, 5.69), (2.47, 6.21), (2.91, 6.70), (3.39, 7.18), (3.94, 7.66), (4.93, 8.15)],
    10: [(0.45, 3.12), (0.95, 6.37), (1.48, 9.39), (1.87, 11.41), (2.48, 14.38), (2.92, 16.36),
         (3.61, 19.23), (4.07, 20.95), (4.76, 23.09), (5.48, 24.92), (6.11, 26.06), (7.59, 27.42)],
    15: [(0.50, 4.54), (0.85, 7.20), (1.15, 9.43), (1.56, 12.27), (1.97, 15.04), (2.54, 18.61),
         (2.95, 21.17), (3.39, 23.85), (3.78, 26.17), (4.38, 29.44), (5.41, 34.92)],
}
# Figure 5-4 / 5-6 (p. 12), MINIMUM sink / source curves (process minimum, not typical).
SINK_MIN = {
    5: [(0.41, 3.16), (0.83, 6.06), (1.19, 7.77), (1.50, 8.83), (2.03, 10.37), (2.86, 10.59), (4.86, 10.59)],
    10: [(0.78, 13.97), (1.18, 21.22), (1.73, 29.06), (2.31, 35.55), (3.13, 44.99), (3.98, 52.70), (5.82, 67.37)],
    15: [(0.94, 18.68), (2.24, 39.46), (3.97, 63.88)],
}
SOURCE_MIN = {
    5: [(0.39, 1.28), (0.68, 1.69), (1.16, 2.27), (1.95, 3.23), (2.81, 4.02), (3.74, 4.72), (5.03, 5.08)],
    10: [(0.44, 2.50), (1.12, 4.47), (2.16, 7.32), (3.18, 9.61), (4.37, 11.56), (5.46, 12.95), (6.47, 13.76), (7.56, 13.83)],
    15: [(0.38, 2.40), (0.88, 4.50), (1.56, 6.98), (2.62, 10.31), (3.84, 13.49), (5.49, 16.61), (7.63, 19.62)],
}
# Figure 5-7 (p. 13): typical VTC, only at -55 °C and 125 °C (no 25 °C curve). Where each
# crosses VO = VI (computed in digitise.py from paths 868-871; which is which from the arrows):
#   VCC 5:  -55 °C path 870, 125 °C path 871; VCC 10: -55 °C path 868, 125 °C path 869.
# 25 °C is taken on the straight line between them at 80/180 of the way from -55 to 125.
VTC_PATHS = {(5, -55): 870, (5, 125): 871, (10, -55): 868, (10, 125): 869}

# 5.3 / 5.5 tables, 25 °C rows (p. 6 and p. 9 repeat them). (VCC, VOUT, min, typ) in mA.
IOL = [(4.5, 0.4, 2.6, 5.2), (5, 0.4, 3.2, 6.4), (10, 0.5, 8, 16), (15, 1.5, 24, 48)]
# Source: the 15 V row prints "VOUT = 1.3V"; read as 13.5 V (VCC - 1.5, as the sink row's 1.5 V,
# and an output at 1.3 V with the input at 0 would not be a source test). Magnitudes.
IOH = [(5, 4.6, 0.65, 1.2), (5, 2.5, 2.1, 3.9), (10, 9.5, 1.65, 3.0), (15, 13.5, 4.3, 8.0)]
# VIL max (CD4049UB rows, p. 7): input low enough that VOUT >= this, (VCC, VOUT, VIL max).
VIL = [(5, 4.5, 1.0), (10, 9.0, 2.0), (15, 13.5, 2.5)]
# VIH min (p. 7, 25 °C): input high enough that VOUT <= this, (VCC, VOUT, VIH min).
VIH = [(5, 0.5, 4.0), (10, 1.0, 8.0), (15, 1.5, 12.5)]
# VOL max 0.05 V, VOH min VCC - 0.05 V (p. 9-10), no load, VIN at the rails.
VOL_MAX = 0.05
VOH_DROP = 0.05
# IDD max (p. 8, 25 °C), µA: (VCC, max). The 15 V row prints "VCC = 4V"; read as 15 V.
IDD = [(5, 1.0), (10, 2.0), (15, 4.0), (20, 20.0)]
IIN_MAX = 0.1e-6  # A, VIN 0 or 18 V, VCC 18 V (p. 10)
# 5.6 AC (p. 11): 25 °C, input tr = tf = 20 ns, CL 50 pF, RL 200 kΩ. (VCC, typ ns, max ns), VIN = VCC.
TPLH = [(5, 60, 120), (10, 32, 65), (15, 25, 50)]
TPHL = [(5, 32, 65), (10, 20, 40), (15, 15, 30)]
TTLH = [(5, 80, 160), (10, 40, 80), (15, 30, 60)]
TTHL = [(5, 30, 60), (10, 20, 40), (15, 15, 30)]
CIN = (15e-12, 22.5e-12)  # typ, max (p. 11)
