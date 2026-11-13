/**
 * Help menu pages (DOM, D-095): Documentation (the user guide's pages in a large window,
 * D-290), Choosing capacitors (from the capacitor guide the server
 * serves, the same text as the inspector's hints), Resistor colour code (the chart, from
 * the server's colour table), Hot keys and About. Also the resistor drawing the Tools calculator uses.
 */

import { getJson } from "./api.js";
import { sheet } from "./editor/form.js";
import { hotkeyGroups } from "./editor/keys.js";
import { h } from "./panels.js";

const SVG = "http://www.w3.org/2000/svg";

/**
 * Help → Documentation and Help → Formulas (D-290): the user guide in a large window. The
 * pages are the server's (`/manual/<page>`, each with the page list and a search box), so
 * the window only frames them; the pop-out button (an icon: the Mac app has no tabs to
 * name, D-312) shows the page it is on in a tab of its own, or in the Mac app outside
 * its window. Escape closes it from inside the page too.
 * @param {string} [page] the page to open on (the first page when left out)
 */
export function manualSheet(page = "") {
  const frame = /** @type {HTMLIFrameElement} */ (h("iframe", { class: "manual-frame", src: `manual/${page}`, title: "Solum Builder guide" }));
  const popOut = h("button", { type: "button", id: "manual-pop-out", class: "icon-button", title: "Open this page in its own tab or window", "aria-label": "Open this page in its own tab or window" }, [popOutIcon()]);
  popOut.addEventListener("click", () => window.open(frame.contentWindow?.location.href ?? frame.src, "_blank", "noopener"));
  const { close } = sheet({ title: "Documentation", id: "manual", wide: true, head: [popOut], body: [frame] });
  const onMessage = (/** @type {MessageEvent} */ e) => {
    if (!frame.isConnected) return window.removeEventListener("message", onMessage);
    if (e.source === frame.contentWindow && e.data === "manual-close") close();
  };
  window.addEventListener("message", onMessage);
}

/** The open-externally mark: a square with an arrow leaving its top right corner. */
function popOutIcon() {
  const svg = document.createElementNS(SVG, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 16 16", width: "14", height: "14", fill: "none", stroke: "currentColor", "stroke-width": "1.5", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", "M6.5 3.5h-3v9h9v-3M9.5 2.5h4v4M13.5 2.5l-6 6");
  svg.append(path);
  return svg;
}

/** Help → Choosing capacitors. */
export async function capacitorSheet() {
  const guide = await getJson("api/guides/capacitors");
  const rows = guide.kinds.map((/** @type {any} */ k) =>
    h("tr", { "data-kind": k.kind }, [
      h("td", {}, [k.name]),
      h("td", { class: "values" }, [k.values]),
      h("td", {}, [k.use]),
      h("td", {}, [k.watch]),
    ]),
  );
  sheet({
    title: guide.title,
    id: "capacitor-guide",
    wide: true,
    body: [
      h("p", {}, [guide.intro]),
      h("table", {}, [
        h("thead", {}, [h("tr", {}, ["Kind", "Typical values", "Use it for", "Watch out for"].map((t) => h("th", {}, [t])))]),
        h("tbody", {}, rows),
      ]),
    ],
  });
}

/**
 * A resistor drawn with its bands; with `labels`, each band is named above and read out
 * below (the Help chart's examples).
 * @param {string[]} colours left to right, tolerance last
 * @param {Array<[string, string]>} [labels] per band: [what it is, what it says]
 */
export function resistorDrawing(colours, labels) {
  const svg = document.createElementNS(SVG, "svg");
  const top = labels ? 18 : 0;
  svg.setAttribute("viewBox", `0 0 260 ${60 + (labels ? 36 : 0)}`);
  svg.setAttribute("class", "resistor-drawing");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Bands: ${colours.join(", ")}`);
  const add = (/** @type {string} */ tag, /** @type {Record<string, string>} */ attrs, /** @type {string} */ text = "") => {
    const el = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text) el.textContent = text;
    svg.append(el);
    return el;
  };
  add("line", { x1: "0", y1: String(top + 30), x2: "260", y2: String(top + 30), class: "lead" });
  add("rect", { x: "50", y: String(top + 10), width: "160", height: "40", rx: "14", class: "body" });
  // the value bands bunch at the left; the tolerance band sits apart at the right
  const xs = [...colours.slice(0, -1).map((_, i) => 72 + i * 22), 182];
  colours.forEach((c, i) => {
    add("rect", { x: String(xs[i]), y: String(top + 10), width: "11", height: "40", fill: `var(--band-${c})`, "data-band": c });
    if (!labels) return;
    const [role, says] = labels[i];
    const x = String(xs[i] + 5.5);
    add("text", { x, y: "12", class: "band-role" }, role);
    add("text", { x, y: String(top + 68), class: "band-says" }, says);
  });
  return svg;
}

/** One chart row's tolerance: "±1 % (F)", or blank. @param {any} c */
const toleranceText = (c) => (c.tolerance === null ? "" : `±${c.tolerance} %${c.letter ? ` (${c.letter})` : ""}`);

/**
 * An example resistor from the chart, its bands labelled.
 * @param {any} example {bands, short, tolerance} @param {Map<string, any>} byName
 */
function exampleResistor(example, byName) {
  const n = example.bands.length;
  const nth = ["1st", "2nd", "3rd"];
  const labels = /** @type {Array<[string, string]>} */ (example.bands.map((/** @type {string} */ b, /** @type {number} */ i) => {
    const c = byName.get(b);
    if (i < n - 2) return [nth[i], String(c.digit)];
    if (i === n - 2) return ["mult.", c.times];
    return ["tol.", toleranceText(c)];
  }));
  return h("figure", { class: "band-example", "data-bands": String(n) }, [
    h("figcaption", {}, [`${n} bands: ${example.short}Ω ±${example.tolerance} %`]),
    resistorDrawing(example.bands, labels),
  ]);
}

/** The colour chart: one row per colour, painted that colour. @param {any[]} colours */
function colourChart(colours) {
  const heads = ["Colour", "1st band", "2nd band", "3rd band", "Multiplier", "Tolerance"];
  return h("table", { class: "colour-chart" }, [
    h("thead", {}, [h("tr", {}, heads.map((t) => h("th", {}, [t])))]),
    h("tbody", {}, colours.map((c) => {
      const digit = c.digit === null ? "" : String(c.digit);
      return h("tr", { "data-colour": c.name, style: `background: var(--band-${c.name})` }, [
        h("th", {}, [c.name]), h("td", {}, [digit]), h("td", {}, [digit]), h("td", {}, [digit]),
        h("td", {}, [c.times]), h("td", {}, [toleranceText(c)]),
      ]);
    })),
  ]);
}

/** How values are written: R, k and M in place of the decimal point (IEC 60062's RKM code). */
function writingValues() {
  const examples = [
    ["0R47", "0.47 Ω"], ["4R7", "4.7 Ω"], ["470R", "470 Ω (R alone just says ohms)"],
    ["1k", "1 kΩ = 1 000 Ω"], ["4k7", "4.7 kΩ = 4 700 Ω"], ["47k", "47 kΩ"],
    ["4k1", "4.1 kΩ: written correctly, but not a value you can buy (see below)"],
    ["1M", "1 MΩ = 1 000 000 Ω"], ["2M2", "2.2 MΩ"],
    ["100p", "100 pF"], ["4n7", "4.7 nF"], ["2u2", "2.2 µF (u stands in for µ)"],
  ];
  return [
    h("h3", {}, ["Writing values: R, k and M"]),
    h("p", {}, ["On schematics the letter goes where the decimal point would be, and says the multiplier: R is ohms (×1), k is thousands, M is millions. Capacitors do the same with p, n and µ (or u). A printed decimal point can vanish in a photocopy or a small font; a letter can't, so 4k7 can't be misread as 47k. A tolerance letter may follow: 4k7J is 4k7 ±5 %."]),
    h("table", {}, [h("tbody", {}, examples.map(([w, m]) => h("tr", {}, [h("td", {}, [h("code", {}, [w])]), h("td", {}, [m])])))]),
    h("p", {}, ["Upper or lower case k both work (4K7 is 4k7). M and m don't: M is mega and m is milli, so 1M is a million ohms and 1m a thousandth. Solum Builder reads 4k7, 4.7k, 4700 and 4.7 kΩ as the same value."]),
    h("h3", {}, ["Standard values"]),
    h("p", {}, ["Resistors are made in series of preferred values, the same steps in every decade. E12 (±10 %): 10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82. E24 (±5 %) adds 11, 13, 16, 20, 24, 30, 36, 43, 51, 62, 75, 91. E96 (±1 %, 5-band parts) has 96 steps. A value like 4k1 is in none of them: use 3k9 or 4k3 (E24), or 4k02 or 4k12 (E96). Tools → Resistor colour code shows the nearest standard values of any value."]),
  ];
}

/** Help → Resistor colour code: the chart, two examples, and how values are written. */
export async function resistorGuideSheet() {
  const { colours, examples } = await getJson("api/tools");
  const byName = new Map(colours.map((/** @type {any} */ c) => [c.name, c]));
  sheet({
    title: "Resistor colour code and values",
    id: "resistor-guide",
    wide: true,
    body: [
      h("p", {}, ["Read from the end where the bands bunch together; the tolerance band (often gold, or brown on 1 % parts) sits apart at the other end. 4 bands: two digits, a multiplier, tolerance. 5 bands: three digits, a multiplier, tolerance (the 3rd band column is for 5-band parts). The rarer multipliers and tolerances are real, just seldom seen on pedal parts."]),
      h("div", { class: "band-examples" }, examples.map((/** @type {any} */ e) => exampleResistor(e, byName))),
      colourChart(colours),
      ...writingValues(),
    ],
  });
}

/** Help → Hot keys: every shortcut, from the editor's own list (keys.js). */
export function hotkeysSheet() {
  sheet({
    title: "Hot keys",
    id: "hotkeys",
    wide: true,
    body: [
      h("p", {}, ["On a Mac, ⌘ works wherever Ctrl is shown. Keys typed into a box are the box's, not shortcuts."]),
      h("div", { class: "hotkey-groups" }, hotkeyGroups().map((g) => h("section", {}, [
        h("h3", {}, [g.title]),
        h("table", {}, [h("tbody", {}, g.rows.map((r) => h("tr", {}, [h("td", { class: "values" }, [r.keys]), h("td", {}, [r.does])])))]),
      ]))),
    ],
  });
}

/**
 * A link that opens in a new tab.
 * @param {string} href
 * @param {string} text
 */
function link(href, text) {
  return h("a", { href, target: "_blank", rel: "noopener" }, [text]);
}

/** Help → About Solum Builder. */
const SITE = "https://solumfx.com";
const REPO = "https://github.com/pbexiga/solum-builder";

export async function aboutSheet() {
  const health = await getJson("api/health");
  sheet({
    title: "About Solum Builder",
    id: "about",
    body: [
      h("div", { class: "about-head" }, [
        h("div", { class: "about-brand" }, [
          h("img", { class: "about-logo", src: "assets/brand/solum-logo-outlined.svg", alt: "Solum Builder" }),
          link(SITE, "solumfx.com"),
        ]),
        h("div", {}, [
          h("p", {}, ["A circuit simulator for guitar-pedal builders: draw a circuit, probe any point, turn the knobs, check it against plain-English rules, and hear it through an amp model."]),
          h("table", {}, [
            h("tbody", {}, [
              h("tr", {}, [h("td", {}, ["Version"]), h("td", { class: "values" }, [health.version])]),
              h("tr", {}, [h("td", {}, ["Simulator"]), h("td", { class: "values" }, [health.ngspice ? `ngspice ${health.ngspice}` : "not available"])]),
              h("tr", {}, [h("td", {}, ["Source"]), h("td", {}, [link(REPO, "github.com/pbexiga/solum-builder")])]),
            ]),
          ]),
        ]),
      ]),
      h("p", {}, ["Built on ngspice (simulation), uPlot (plots) and the Fahkwang typeface. The classic circuits follow published analyses (",
        link("https://www.electrosmash.com", "ElectroSmash"), ", ", link("https://aionfx.com", "Aion FX"), " and others), each cited in its file."]),
    ],
  });
}
