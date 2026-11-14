# Third-party notices

Solum Builder's own code, rules, drawings, guides and fitted models are under the
licence in `LICENSE` (MIT with the Commons Clause). The files and text below come from
other people and keep their own terms; `LICENSE` does not cover them.

## Code in this repository

| What | Where | Whose | Licence |
|---|---|---|---|
| uPlot 1.6.31 (the charts) | `web/vendor/uplot/` | Leon Sorokin, https://github.com/leeoniya/uPlot | MIT, `web/vendor/uplot/LICENSE` |

## Fonts

| What | Where | Whose | Licence |
|---|---|---|---|
| Fahkwang | `web/fonts/fahkwang/` | The Fahkwang Project Authors, https://github.com/cadsondemak/Fah-Kwang | SIL Open Font License 1.1, `web/fonts/fahkwang/OFL.txt` |
| Lora | `web/fonts/lora/` | The Lora Project Authors, https://github.com/cyrealtype/Lora-Cyrillic (Reserved Font Name "Lora") | SIL Open Font License 1.1, `web/fonts/lora/OFL.txt` |

The `-outlined` logo files in `web/assets/brand/` carry the wordmark's letters as
Fahkwang outlines (the OFL allows it). The logo itself is Solum Builder's.

## SPICE models (`library/models/`)

Every model's record (`<type>/<id>.json`) names its source, and
`data/spec-sheets/README.md` lists them all with each one's licence review.

- **Solum Builder's own** (most of them): fitted to, or estimated from, the makers'
  published data sheets. The values are ours; each record names the sheet.
- **Values read from the maker's data sheet:** ICL7660 (Renesas), LT1054 (Texas
  Instruments), MAX1044 (Analog Devices), TC1044S (Microchip), 78L12 (onsemi).
- **Makers' own model files**, published by the maker with no licence notice and copied
  unchanged, each with its source line: Texas Instruments' op-amp macromodels (LF353,
  LM308, LM358, LM741, MC1458, OP07, RC4558, TL061, TL062; and `TL072_TI_1989.lib` in
  `tests/fixtures/models/`), Diodes Incorporated's zeners (1N4738A, 1N4739A, 1N4742A),
  Philips' JFETs (2N5485, J113). They remain their makers'.

Cards whose terms don't allow passing them on are not in this repository.
`library/models/not-included.json` lists them, and the app says where to get each one
(Tools → Parts and datasheets); you add them yourself with Tools → Add a model.

## Starter circuits (`library/starters/`) and their expected values (`tests/fixtures/acceptance/`)

The starters are drawn for Solum Builder from published schematics and analyses of
classic pedals. Each expected-values file names its sources, with a link and the date
read, so a test can be checked against the page it came from. Some carry short quotes
(a row of a voltage table, a phrase), which remain their authors':

- **ElectroSmash** (https://www.electrosmash.com), circuit analyses published under
  CC BY-NC 3.0. None of its text is here: its figures and formulas are cited and said in
  our own words. Big Muff Pi, Boss DS-1, Dallas Rangemaster, Fuzz Face, Klon Centaur, MXR
  Dyna Comp, ProCo Rat, Tube Screamer.
- **Aion FX** (https://aionfx.com), project and kit documentation, © Aion FX: Aurora,
  Cerulean, Comet, Deimos, Halo, Helios, Refractor, Sapphire, Solaris, Stratus. Aion FX's
  terms allow building its projects, commercially too.
- **General Guitar Gadgets**, "Modernized Marshall Vintage BluesBreaker Replica Schematic".
- **Fuzz Central**, "Sola Sound ToneBender Professional MKII".
- **Boss**, the BD-2 Blues Driver service schematic.

The pedals' names belong to their makers and are used only to say which circuit a
starter follows. Solum Builder is not connected with any of them.

## Guides and drawings

- `library/guides/*.yaml`: figures taken from the sources each file names (pickup
  measurements, battery discharge curves, wah inductor measurements).
- `library/wiring/*.svg`: drawn for Solum Builder; `library/wiring/sources.yaml` says
  what each follows.
- `tests/fixtures/nam/`: random-weight test models made for this project with
  neural-amp-modeler (MIT); no amp capture or recording ships.

## Not in this repository, installed when the image is built

ngspice 44.2 (BSD-3-Clause; built from the project's source release, as for the Mac app below), and from PyPI: FastAPI (MIT), Uvicorn
(BSD-3-Clause), NumPy (BSD-3-Clause), Pydantic (MIT), PyYAML (MIT), WeasyPrint
(BSD-3-Clause). Each comes with its own licence.

## Not in this repository, inside the Mac app (`Solum Builder.app`)

`make mac-app` builds or fetches these and puts them in the app; each keeps its own
licence.

- **ngspice 44.2** (BSD-3-Clause; its XSPICE code models and other parts under their own
  permissive terms, see ngspice's `COPYING`), built from the project's source release.
- **Python 3.12** (PSF License), from python-build-standalone, and from PyPI the packages
  above with what they need, plus **pywebview** (BSD-3-Clause) and **pyobjc** (MIT) for
  the window. **PyInstaller**'s bootloader (GPL-2.0 with an exception that allows
  bundling programs under any licence) starts the app.
- **The PDF libraries, from conda-forge**: Pango, GLib, FriBidi and libintl (LGPL-2.1 or
  later), HarfBuzz and Graphite2 (MIT and LGPL-2.1/MPL), fontconfig, FreeType (FreeType
  License), libpng, zlib, PCRE2, libffi, libexpat, bzip2, ICU, libiconv (LGPL), libc++
  (Apache-2.0 with LLVM exceptions). They are separate library files in the app
  (`Contents/Frameworks/`), as the LGPL asks: you may replace them with your own builds.
  `packaging/mac/pdflibs.lock` lists the exact packages.
