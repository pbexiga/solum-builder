# Adding a starter circuit

A starter is a real pedal, drawn from a published source, that opens from File → New from starter. Each one is also an acceptance test: the simulation has to match the source's measured or worked figures (D-019). This page says what a new one needs, then lists the pedals we'd like next.

## What a starter needs

1. **A published source with numbers.** Aion FX's schematic wherever Aion has a clone of the pedal, its differences from the original written in `substitutions` (D-213). A circuit analysis or a build document that gives voltages, gains or frequencies you can check (ElectroSmash's analyses, Aion FX's build documents, R.G. Keen's Geofex pages). For an original's schematic, look first in Schematics Online's library (https://schematicsonline.com/; the user, 2026-11-10: a good, wide collection of makers' schematics), then archive.org and Hobby Hour, and General Guitar Gadgets (https://generalguitargadgets.com/; the user, 2026-11-10: good schematics of the pedals they sell as kits; their PDFs refuse being served from any other site, so draw from them but don't copy or archive them, D-257); check each file's terms before drawing from it. Where no published figure fits the drawn values, a starter copied faithfully from its source's schematic may ship with no checks: say why in `omitted` (D-214). Archive it in the Wayback Machine and note its licence. **Never fill expected values from memory.**
2. **Models that exist.** Every transistor, diode, op-amp and chip in it has a card in `library/models/` (Tools → Parts and datasheets lists them). If the original part has none, use the nearest one and say so in the acceptance file's `substitutions` (e.g. the Big Muff's BC239s as BC549Cs, D-167). Germanium transistors get the middle of the source's hFE and leakage ranges as measured figures (see [the guide's germanium page](../guide/germanium.md)).
3. **A drawing with real wires** that reads like the source's schematic: signal left to right, supply at the top, ground at the bottom, every part labelled as the source numbers it. Knobs named as on the pedal (Gain, Tone, Level), switch positions named (the Tone Bender's Mode: MkII, 1.5).
4. **Notes** on the parts and nets that matter (what C3 does, why Q1 has no base resistor), the description (what the pedal is, its year, the source, any substitution) and bias targets on trimmers where the source gives a reading to set.
5. **The parts list filled in:** each capacitor's type, each electrolytic's voltage rating, the enclosure. From the source first; else a kit's parts list of the same circuit; else the capacitor guide (`library/guides/capacitors.yaml`). Ratings with no source get the app's advice (16 V on a 9 V pedal). Ready to build must show nothing open (D-211).
6. **No problems.** Problems is empty. A warning that is true of the real circuit may stay, listed in `tests/rules/corpus_warnings.yaml` with the reason (the Tone Bender Mode's floating capacitors, D-135).

## Steps

1. Draw it in the app, from File → New sheet, and save it. Set File → Properties: name, description, enclosure. (An agent can't draw in the app: it writes a script that places the parts and wires and checks the drawn nets against the intended netlist, as `.claude/skills/build-starter/make_klon.py` does, then goes on from step 3.)
2. Copy the saved file from `DATA_DIR/circuits/` into `library/starters/<id>.json`, set `"starter": true` and give it a plain id (`proco-rat`, `ts808`).
3. Write `tests/fixtures/acceptance/<id>.expected.yaml` (copy one that's close):
   - `source`: title, url, Wayback snapshot, date read, licence;
   - `substitutions`: each change from the source and why;
   - `checks`: each published figure as a `dc` (with `supply` when the source measured on another supply, e.g. Aion's 9.6 V), `gain`, `corner`, `notch` or `clip` check, with its tolerance and a `quote` of the source's words, or `says`, the same in our own words, when the source's licence is non-commercial (ElectroSmash: never quote it, D-292) (a value read off a graph is `from: image` with the image link, and waits for the user's confirmation);
   - `omitted`: published figures you can't check, and why;
   - `build`: extra sources for the parts list and what came from where.
4. Run `make check`, then `make accept`. The mutation test breaks the starter in scripted ways and expects a rule to notice each: a breakage no rule can see goes in `tests/rules/mutation_gaps.yaml` with the reason.
5. A check the simulation misses after a fair look gets `known_gap` with the worked reason, not a looser tolerance.

## Wish list

Each needs a source with figures before it can go in. Chosen to ship (D-213): Aion's Halo Big Muff, Boss DS-1, Klon Centaur, MXR Dyna Comp, Marshall Bluesbreaker, Boss BD-2. In: all six, each with its original beside the Aion version (D-239, D-256, D-257).

| Pedal | Where to look | Notes |
|---|---|---|
| Boss BD-2 Blues Driver (in, D-215, D-256) | Boss's service schematic (Schematics Online); Aion's Sapphire documents | The original in as `boss-bd2`, drawn from Boss's schematic with no checks (it prints no figures, D-256). Aion's version in as `boss-bd2-aion`, checked against the kit document's prototype voltages (D-215). |
| Klon Centaur (in, D-218, D-244) | ElectroSmash's Klon analysis; Aion's Refractor documents | The original in as `klon-centaur`, checked net by net against ElectroSmash's schematic and against its worked figures (D-244). Aion's version in as `klon-centaur-aion`, checked against the kit document's prototype voltages (D-218). |
| Boss DS-1 Distortion (in, D-235, D-243) | ElectroSmash's DS-1 analysis; Aion's Comet documents | The original in as `boss-ds1`, drawn from ElectroSmash's schematic and checked against its figures (D-243). Aion's version in as `boss-ds1-aion` (D-235). |
| MXR Distortion + | ElectroSmash's Distortion + analysis | An op-amp and germanium diodes to ground (our 1N34A, D-253). |
| MXR Dyna Comp (in, D-236, D-245) | ElectroSmash's Dyna Comp analysis; Aion's Aurora documents | The original in as `mxr-dyna-comp` (CA3080), drawn from ElectroSmash's schematic and checked against its figures (D-245). Aion's version in as `mxr-dyna-comp-aion` (LM13700), checked against the kit document's prototype voltages (D-236). |
| Electro-Harmonix LPB-1 | none found yet | One transistor booster. |
| Aion Halo Big Muff (in, D-214) | Aion's Halo document | In as `big-muff-aion-halo`, with no checks (D-214). |
| Marshall Bluesbreaker (in, D-237, D-257) | GGG's replica schematic; Aion's Cerulean documents | The original in as `marshall-bluesbreaker`, drawn from General Guitar Gadgets' replica schematic with no checks (no figures published, D-257). Aion's version in as `marshall-bluesbreaker-aion`, checked against the kit document's prototype voltages (D-237). ElectroSmash has no analysis of it. |
| MXR MicroAmp | ElectroSmash's MicroAmp analysis | Not on the earlier list; a clean op-amp boost. |
| Marshall Guv'nor | ElectroSmash's Guv'nor analysis | Not on the earlier list. |

ElectroSmash's pages are CC BY-NC 3.0: draw from them and cite their figures, in our own words only (D-292). Aion FX's documents allow building, commercially too.
