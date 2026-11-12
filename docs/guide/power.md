# Power

A pedal's power starts at the adapter's DC plug: mains is never simulated. There are four power parts, and most circuits need none of them.

## The Power menu

**Power**, in the header, is the supply plugged into the pedal: 9 V, 12 V, 18 V, ±9 V, ±12 V or ±15 V, or **Custom…** for any other. It always sets **V+** (and **V−** on a ± supply): every V+ bar on the sheet is that supply. It's ideal and perfectly clean.

**Custom…** sets the type, **+** (for most pedals: NPN transistors, op-amps), **−** (for PNP circuits like the Fuzz Face, which run from −9 V) or **±** (a split supply), and the voltage of each side. Its **Compare supply voltages** box runs the circuit at up to five voltages, overlaid on the plots: does it still work on a flat battery, how much more headroom at 18 V?

Beside the menu, after a run, is the current the circuit draws from the supply (*1.82 mA*): what to size a battery or an adapter by.

18 V or −9 V made *inside* the pedal from a 9 V supply is a charge pump's job, on its own net: see [Charge pumps and regulators](#charge-pumps-and-regulators).

## Which parts to draw

| You want to… | Draw |
|---|---|
| just power the circuit | nothing: the Power menu does it |
| draw the power section, for a full drawing and the parts list | a **DC jack** |
| run it from a battery, or switch between plugged in and battery | a **DC jack** and a **battery** (the *9 V power · DC jack and battery* block) |
| hold another net at a voltage of its own | a **DC source** |

### DC jack

The DC jack draws the real jack: its sleeve **+** wired to V+, its centre **−** to ground (centre negative, as pedal supplies are), and its battery lug. It makes no voltage of its own: to the simulation it's a V+ label and a ground. It's there for a full drawing, the parts list and export. There's one per circuit, always called DC.

With a battery wired to its lug, Knobs & switches gets a **Power** switch: **DC jack** (a plug in: the Power menu's supply powers the pedal and the battery is cut off) or **Battery** (no plug: the battery lug touches the sleeve and the battery powers it). A chip left of the Power menu says which: *DC jack*, or *Battery · 7.4 V* with the menu greyed.

### Battery

A 9 V battery, its voltage picked by how used it is (from Energizer's 522 datasheet, on a pedal's load): **Fresh (9 V)**, **Half used (7.4 V)**, **Low (6.6 V)**, **Nearly flat (5.5 V)**, or your own measured voltage. An internal resistance is optional; measure it as the drop in volts on a known load, divided by the current.

Where its **+** goes decides what it powers:

- **On V+, no DC jack drawn**: it powers the pedal, and the Power menu is greyed.
- **On the DC jack's battery lug** (the jack's + on V+): it powers the pedal while no plug is in; plug one in (Knobs → Power) and the Power menu's supply takes over, the battery cut off. This is how pedals are wired.
- **On V+ beside a DC jack**: unplugged, it powers the pedal; plugged in, it stays connected beside the supply. It then needs an internal resistance for the circuit to run, and Problems warns that the jack doesn't switch it.
- **On any other net**: it powers only what's on that net, and the Power menu keeps V+.

Its **−** goes to ground, or to a stereo input jack's ring, so that plugging a guitar cable in switches it on: the cable's sleeve joins the ring to ground. Set the input jack to stereo (in the IN part's form, or a Jack part) and Knobs gets a **Cable** switch (in: the ring joins the sleeve); with the cable out, Problems says the battery is cut off.

### DC source

An ideal voltage of its own, on a net other than V+ and V−: a steady 4.5 V reference to rule out a divider, a second separate supply, a test voltage on a node. Label the parts it powers with its net's name. It can't go on V+ or V−, which the Power menu supplies: Problems says so and the circuit doesn't run until it's moved.

## Charge pumps and regulators

A voltage the pedal makes itself, like 18 V from a 9 V supply for more headroom, or −9 V for an op-amp's negative side, comes from a **charge pump** part (ICL7660, LT1054, MAX1044, TC1044S) wired as its datasheet shows: a flying cap from pin 2 to pin 4 makes −V+ on pin 5; a cap from pin 2 to two diodes makes 2 × V+. The **Charge pump** blocks have them drawn, with chips or with an op-amp. A **regulator** (78L12) holds 12 V from a pump's 18 V; the *12 V supply* blocks have that drawn too.

A charge pump switches at its own frequency. Problems warns when that is inside the audio band (a TC1044S pumps at about 22 kHz only with pin 1, *boost*, wired to V+). To hear its whine, turn on *Charge pump switching* in the Audio pane's Pedal drawer; renders are then about ten times slower.

## Problems about power

Problems checks that a chip has power and the right way round, that nothing shorts a supply, that no supply is over a chip's maximum, that a supply isn't mostly lost in its filter (a diode in backwards), that a supply has a bulk capacitor where it comes in, and that a regulator's input is high enough to regulate.
