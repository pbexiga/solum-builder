"""Our 2N1308 against Central's 2N1304 card (theirs; compared, never shipped: no redistribution)
and Central's sheet's hfe 140 at VCB 5 V, IE 1 mA (all four types)."""
import sys, math
sys.path.insert(0, ".claude/skills/fit-model/worked/germanium")
import gefit as g
fm = g.fm
GP = fm.GummelPoon
ours = GP(is_=2.915e-06, nf=1.094, bf=360.6, ise=8.736e-08, ne=1.451, ikf=1.022, vaf=math.inf, re=0.0,
          nkf=0.5, br=9.185, isc=2.04e-06, nc=4.0, rc=1.28, rb=0.0, nr=1.094)
central = GP(is_=93.351e-9, nf=1.0, bf=120, ise=0.0, ne=1.5, ikf=10e-3, vaf=100.0, re=0.0,
             nkf=0.5, br=0.78983, isc=93.351e-9, nc=2.0, rc=0.0, rb=0.0, nr=1.0)
def small(f, ic, vce):
    d = ic * 0.02
    ib = lambda i: i / f.forward(i, vce)[1]
    return 2 * d / (ib(ic + d) - ib(ic - d))
for name, f in (("ours 2N1308", ours), ("Central 2N1304", central)):
    print(name, "DC hFE at VCE 5 V:", {ma: round(f.forward(ma * 1e-3, 5.0)[1], 1) for ma in (0.3, 1, 3, 10, 30, 100)})
    print(name, "  small-signal hfe at 1 mA, VCE 5.2 V:", round(small(f, 1e-3, 5.2), 1),
          "| hFE 10 mA 1 V:", round(f.forward(10e-3, 1.0)[1], 1), "| hFE 200 mA 0.35 V:", round(f.forward(0.2, 0.35)[1], 1))
