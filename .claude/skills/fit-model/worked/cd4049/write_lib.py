"""Write CD4049UB.lib from params.json (fit.py's result): python .claude/skills/fit-model/worked/cd4049/write_lib.py"""
import json

from scratch.fit.cd4049 import inv

p = json.load(open(".claude/skills/fit-model/worked/cd4049/params.json"))
head = """* CD4049UB, one inverter of six (unbuffered hex inverter), for linear (biased) use
* Our own fit to TI's CD4049UB/CD4050B data sheet SCHS046L (Aug 1998, rev. Feb 2026), 25 C typical
* Pins: in out vdd vss. Per chip (PDIP-16 CD4049UBE): VCC 1, VSS 8; inputs A3 B5 C7 D9 E11 F14,
* outputs G2 H4 I6 J10 K12 L15; 13 and 16 not connected.
* N and P channel: ngspice VDMOS, source on its rail; body diodes are the output's drain-bulk diodes.
* DIN: the input diode to VSS (sheet p. 1 schematic); DSUP: the VSS->VDD diode; ngspice default values.
"""
body = inv.subckt(p)
lines = []
for ln in body.splitlines():
    while len(ln) > 100:  # SPICE continuation lines
        cut = ln.rfind(" ", 0, 100)
        lines.append(ln[:cut]); ln = "+" + ln[cut:]
    lines.append(ln)
open(".claude/skills/fit-model/worked/cd4049/CD4049UB.lib", "w").write(head + "\n".join(lines) + "\n")
print(head + "\n".join(lines))
