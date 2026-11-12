# Solum Builder — visual design

The look follows solumfx.com: dark, warm, quiet, handcrafted. Muted metals and stone rather than bright UI colours. Dark theme is the default (and the only theme in v1).

## Brand assets (`web/assets/brand/`)
| File | Use |
|---|---|
| `solum-logo.svg` | The Solum stamp from solumfx.com, original silver (`#B0B8BD`). Use as-is in the header and about screen |
| `solum-logo-currentcolor.svg` | Same stamp with `currentColor`, for tinting (e.g. brass on hover, muted in empty states) |
| `favicon.svg` | The site's favicon: dark disc, bone rings and wordmark |
| `*-outlined.svg` | The same three files with the wordmark converted to paths. **The app uses these** |

The originals' wordmark is SVG `<text>` set in Fahkwang, and an SVG loaded through `<img>` or as a favicon can't use the page's fonts, so it would fall back to a system sans. `scripts/outline_svg_text.py` converts the text to Fahkwang outlines (HarfBuzz shaping, the original letter-spacing and centring); everything else in the file is copied unchanged (D-046). Never redraw or restyle the logo; if an original changes, re-run the script.

**Header:** stamp at 28–32 px, then `SOLUM` in Fahkwang 300, letter-spacing 0.25em, colour bone, then `BUILDER` in Fahkwang 200, colour cloud. Uppercase only in the wordmark, as on the site.

## Colour tokens
Defined once in `web/theme.css` as CSS custom properties. Nothing else in the codebase hard-codes a colour.

**Themes (D-303):** the tokens below are the **Solum** theme, the default. View → Theme… also offers **Dark** (neutral greys, a blue highlight) and **Light** (dark text on white, a blue highlight): each is a `:root[data-theme="…"]` block in `theme.css` that replaces the UI, status, schematic and plot roles; the brand palette and the resistor bands stay. Light shows the ink logo (`solum-logo-currentcolor-outlined.svg`). Exports and printed schematics keep their own paper colours (`.print`, D-205). Every theme meets the same contrast and hue rules (`tests/unit/test_theme.py`).

**Brand palette (from solumfx.com `:root`)**
| Token | Hex | Site name |
|---|---|---|
| `--ink` | `#1E1E1B` | ink |
| `--bone` | `#F0EDE8` | bone |
| `--slate` | `#3D4145` | slate |
| `--ocean` | `#2C3D4F` | ocean |
| `--cloud` | `#9DA8B0` | cloud |
| `--brass` | `#8B7D5E` | brass |
| `--silver` | `#B0B8BD` | logo stroke colour |

**UI roles** (derived values are marked; tune by eye in Phase 2)
| Role | Value | Use |
|---|---|---|
| `--surface-0` | `--ink` | Page background, schematic canvas |
| `--surface-1` | `#262622` *(derived)* | Panels, palette, inspector |
| `--surface-2` | `#2F2F2B` *(derived)* | Raised: popups, menus, focused panel header |
| `--border` | `--slate` | Panel edges, dividers, grid dots on the canvas (`--grid-dot`, slate at 90 %: faint, but visible enough to place parts by) |
| `--text` | `--bone` | Primary text, part labels |
| `--text-2` | `--cloud` | Secondary text, axis labels, values |
| `--text-3` | `#868E94` *(derived; tuned from `#6E767C` for 4.5:1 on panels)* | Hints, disabled |
| `--accent` | `--brass` | Primary buttons, selection, active knob, Run |
| `--accent-hi` | `#B3A47E` *(derived)* | Accent text and hover on dark (brass itself is too dark for small text) |
| `--info-bg` | `--ocean` | Selected rows, info callouts, probed-net highlight fill |

**Schematic**
| Element | Colour |
|---|---|
| Wires, part symbols | `--cloud` |
| Selected part/wire | `--accent-hi` |
| Stage picked in Bias & headroom (its parts, block, card, chip) | `--picked` (`#D68A4A`, copper; D-127: not an error, so not brick, and apart from the brass highlight) |
| Probed net | `--bone`, 2 px |
| Junction dots | `--cloud` |
| Rail labels (V+, VREF, GND) | `--text-2` |
| DC voltage overlay | `--sch-dc` (`--accent-hi`), monospace |
| Impedance overlay (View → Impedance) | `--sch-impedance` (`#7FA9C9`, steel blue; D-147) |
| Capacitor type (View → Capacitor types) | `--sch-type` (`#B497C8`, lavender; "not-set" in `--text-3` italic; D-147) |
| Selected wire or label | `--accent-hi` |
| Part being placed, wire being drawn | `--accent-hi`, dashed ghost |
| Grid | dots every 10 units, spacing doubled as you zoom out (never closer than 14 px), about 1 px each |

**Plots** (canvas can't read CSS variables; `web/plots.js` reads the `--plot-*` tokens once with `getComputedStyle`)
| Series | Colour | Style |
|---|---|---|
| Current result | `#C9B98F` *(derived, light brass)* | solid 2 px |
| Snapshot / A-B | `--cloud` | dashed |
| Input overlay | `--text-3` | dashed, thin |
| Sweep series (up to 12) | `--plot-sweep-1..12`: one ramp brass → light brass → silver → cloud → bone *(derived)*; n series take n evenly spaced steps (D-055) | solid 1.5 px, value written at each line's right end |
| Grid | `--slate` at 50 % | 1 px |
| Even / odd harmonics | `#C9B98F` / `--cloud` | bars rising from −80 dB (taller = stronger) |
| Second curve "at the output" | `--plot-output` (`--silver`) | solid 1.25 px |
| Operating point on a device curve | `--bone` | dot |
| Knee lines, peak/dip markers, clip levels (D-097) | `--plot-marker` (`--bone`) | dashed 1 px, labelled in mono; peaks and dips a small triangle pointing at the curve |
| Where a knob or part acts (D-097) | `--plot-band` (brass, faint) | shaded band behind the curves |
| Frequency clicked for part influence | `--plot-at` (`--accent-hi`) | solid 1.5 px |
| Edit mode handle (a knee, peak or dip to drag) | `--plot-at` ring, `--plot-handle-fill` inside (`--plot-at` when active) | 5 px dot (6 active), labelled with its part |

Diode and BJT curves plot |I| on a log axis (decades labelled `1n`, `1µ`, `1m`), as datasheets do; a JFET's transfer curve is mA on a linear axis. Log axes draw grid lines at decades only.

**Status** (muted to fit the palette; always paired with an icon and text)
| Status | Colour |
|---|---|
| Error | `#CF7466` *(derived, brick; tuned from `#C2665A` for 4.5:1 on panels)* |
| Warning | `#C9A24A` *(derived, ochre)* |
| OK | `#7FA07A` *(derived, sage)* |

Text roles reach WCAG AA (4.5:1) on `--surface-0` and `--surface-1`; `tests/unit/test_theme.py` checks every text role against `theme.css`. `--brass` is for fills and large elements only (4.1:1).

Layout styles live in `web/app.css` and use only these tokens.

**Editor surfaces (D-057):** the layout follows app.pedalspice.com in structure only, never in colour. The part palette sits left of the canvas on `--surface-1`: two columns of tiles on `--surface-0` with a hairline border, the symbol drawn in `--sch-line` above the name, grouped under small Fahkwang headings (Wiring, Passive, Semiconductors, Signal & power); hover gives a brass edge, the active tool `--info-bg`. Hotkeys appear only in tooltips. Header menus (File, Edit, Blocks, View, Tools, Help; starters are File → New from starter ▸) are quiet text buttons that open a `--surface-2` list with key hints in mono `--text-3`; a submenu opens beside its item, marked ▸. Hairline separators (`--border`) set the logo, the menus, the name and Run apart; Power, Run and Auto-run sit at the far right (D-095). Each result pane's heading has a `--text-3` grip (⋮⋮) at its right to drag it. Zoom buttons (+, −, Fit) sit in the canvas's bottom-right corner. Schematic lines are 1.5 px; ground is the three-bar symbol, a rail is a bar with its name above; resistors and pots are zigzags. The inspector and the circuit dialogs are one popup style, `--surface-2` with a hairline border, pinned to the canvas's top-left corner so it never covers the panels. Primary buttons (Apply, Save, Create) are brass; an unsaved circuit shows "● unsaved" in `--warning` next to its name.

**Large views (D-102, D-105, D-107, D-108, D-110):** every pane's large view comes from one helper, `largeView` in `panels.js`, and one layout: `.large-split` on the body, `.large-side` on the right-hand column, `.large-notes` on its explanations. In the panel, Expand is on the pane's title bar, at the right before the grip, so a shut pane can go large without opening it first; large, it's Collapse, the last item in the pane's tool row at the far right (`.large-toggle`), after the other tools (Layers, Edit curve…). A shrunk bar can keep a few controls (`bar`): the Audio pane's Render, Play and Dry / Pedal / Snapshot. The view itself never scrolls: it has a fixed height, the plot on the left, and a right-hand column with its own scroll. Explanations (what a chart shows, how to read it, how a mode works) are not in the pane at all: they're behind the pane's ⓘ, right after its name in the title bar, in the panel (shut or open) and the large view alike, hidden only on a large view shrunk to its bar (`paneInfo`, D-109). The pop-up opens under it, like History's, and says what's on screen now (the chart picked, Edit curve while editing). Readings stay in the pane (where the pedal clips, a sweep's findings, a problem's why and fix), as do short status lines ("Nudging each part…", `.hint`).

## Typography
| Use | Font |
|---|---|
| Logo, header, panel titles | **Fahkwang** 200–400, uppercase, letter-spaced (as on the site) |
| Prose: node annotations, rule "why" and "fix", calculator explanations | **Lora** 400 / italic 400 |
| UI controls, labels, menus | system UI sans (`system-ui`), for density at 12–13 px |
| Values, units, DC readouts, axis ticks | `ui-monospace` with tabular figures |

Fahkwang and Lora are vendored in `web/fonts/` (both SIL Open Font License; keep the licence files next to them). No requests to Google Fonts at runtime, so the app works offline.

## Feel
- Flat surfaces, hairline `--slate` borders, no gradients or shadows (the logo's fading rule line is the one exception, and it's the logo).
- Generous spacing in panels; the canvas gets the space.
- Motion: none beyond simple fades. The tool should feel calm while you think.
