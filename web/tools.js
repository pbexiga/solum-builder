/**
 * Tools menu pages (DOM, D-095): the unit converter, the resistor colour-code
 * calculator (its chart is in Help), the Calculators window (D-320), the parts list (Parts and datasheets, 9c) and Add a
 * model (9c). Every number is read and written by the server
 * (`/api/tools/*`, solum/markings.py, the one SI owner, D-045); this module only lays out
 * what it answers.
 */

import { getJson, postJson } from "./api.js";
import { sheet } from "./editor/form.js";
import { resistorDrawing, resistorGuideSheet } from "./help.js";
import { h, infoPopup } from "./panels.js";
import { ORIGIN_TAGS, SHOWS, checksText, excludedText, originText, partGroups } from "./parts.js";
import { debounce, latestOnly } from "./state.js";
import { remember, remembered } from "./storage.js";

/** @returns {Promise<{colours: any[], quantities: Array<{unit: string, name: string, example: string}>, filters: Record<string, string>}>} */
const tables = () => getJson("api/tools");

/**
 * A labelled input row in a tool sheet.
 * @param {string} id @param {string} label @param {string} placeholder
 */
function inputRow(id, label, placeholder) {
  const input = /** @type {HTMLInputElement} */ (h("input", { id, type: "text", autocomplete: "off", spellcheck: "false", placeholder }));
  return { input, row: h("div", { class: "form-row" }, [h("label", { for: id }, [label]), input, h("span", { class: "unit" }, [])]) };
}

/**
 * Ask the server, showing its plain-English message on a bad value; only the newest
 * answer is shown.
 * @param {HTMLElement} error @param {() => string} url @param {(body: any) => void} show
 */
function asker(error, url, show) {
  const latest = latestOnly();
  return debounce(async () => {
    const ticket = latest.next();
    try {
      const body = await getJson(url());
      if (!latest.isCurrent(ticket)) return;
      error.hidden = true;
      show(body);
    } catch (err) {
      if (!latest.isCurrent(ticket)) return;
      error.hidden = false;
      error.textContent = /** @type {Error} */ (err).message;
    }
  }, 150);
}

/** Tools → Unit converter. */
export async function converterSheet() {
  const { quantities } = await tables();
  const quantity = /** @type {HTMLSelectElement} */ (h("select", { id: "tool-quantity" }));
  for (const q of quantities) quantity.append(new Option(`${q.name} (${q.unit})`, q.unit));
  const value = inputRow("tool-value", "Value", "");
  const code = inputRow("tool-code", "Code on the part", "e.g. 223, 104K, 4p7");
  const error = h("p", { class: "error", role: "alert", hidden: "" });
  const result = h("div", { class: "tool-result", id: "tool-result" });
  const ask = asker(error, () => {
    const unit = encodeURIComponent(quantity.value);
    return fromCode ? `api/tools/convert?unit=${unit}&code=${encodeURIComponent(code.input.value)}` : `api/tools/convert?unit=${unit}&value=${encodeURIComponent(value.input.value)}`;
  }, (body) => {
    if (fromCode) value.input.value = body.short;
    else if (quantity.value === "F") code.input.value = body.code ?? "";
    result.replaceChildren(
      h("table", {}, [h("tbody", {}, body.rows.map((/** @type {any} */ r) => h("tr", {}, [h("td", { class: "values" }, [r.number]), h("td", {}, [r.unit])])))]),
      ...(quantity.value === "F" ? [h("p", {}, [body.code ? `Printed on the part as ${body.code}.` : "Too precise for a printed code (it takes two significant figures)."])] : []),
      ...(body.tolerance ? [h("p", {}, [`The letter gives the tolerance: ${body.tolerance}.`])] : []),
      ...(body.series ? [h("p", {}, [body.series.length ? `A standard value (${body.series.join(", ")}).` : "Not a standard E-series value."])] : []),
    );
  });
  let fromCode = false;
  const showCode = () => {
    code.row.hidden = quantity.value !== "F";
    value.input.placeholder = quantities.find((q) => q.unit === quantity.value)?.example ?? "";
  };
  quantity.addEventListener("change", () => {
    showCode();
    fromCode = false;
    if (value.input.value.trim()) ask();
  });
  value.input.addEventListener("input", () => {
    fromCode = false;
    if (value.input.value.trim()) ask();
  });
  code.input.addEventListener("input", () => {
    fromCode = true;
    if (code.input.value.trim()) ask();
  });
  showCode();
  sheet({
    title: "Unit converter",
    id: "unit-converter",
    body: [
      h("p", {}, ["Type a value the way it's written on a schematic (22n, 4k7, 2M2) or in plain numbers (0.000000022, 4700). On a capacitor, you can also type the code printed on it."]),
      h("div", { class: "form-row" }, [h("label", { for: "tool-quantity" }, ["Quantity"]), quantity, h("span", { class: "unit" }, [])]),
      value.row,
      code.row,
      error,
      result,
    ],
  });
  value.input.focus();
}

/**
 * A labelled select in a tool sheet. @param {string} id @param {string} label
 * @param {Record<string, string>} options value → text
 */
function selectRow(id, label, options) {
  const select = /** @type {HTMLSelectElement} */ (h("select", { id }));
  for (const [value, text] of Object.entries(options)) select.append(new Option(text, value));
  return { select, row: h("div", { class: "form-row" }, [h("label", { for: id }, [label]), select, h("span", { class: "unit" }, [])]) };
}

/** @param {{input: HTMLInputElement}} row the row's value for an address */
const typed = (row) => encodeURIComponent(row.input.value.trim());

/**
 * One calculator in the Calculators window (D-320): its rows, and its answer asked of the
 * server whenever a field changes and `ready` says there is enough to ask with.
 * @param {{key: string, intro: string, rows: Node[], fields: Array<HTMLInputElement | HTMLSelectElement>,
 *   url: () => string, ready: () => boolean, show: (body: any) => Node[]}} spec
 */
function calculator({ key, intro, rows, fields, url, ready, show }) {
  const error = h("p", { class: "error", role: "alert", hidden: "" });
  const result = h("div", { class: "tool-result", id: `${key}-result` });
  const ask = asker(error, url, (body) => result.replaceChildren(...show(body)));
  const changed = () => {
    if (ready()) return ask();
    result.replaceChildren();
    error.hidden = true;
  };
  for (const el of fields) el.addEventListener(el.tagName === "SELECT" ? "change" : "input", changed);
  return h("div", { class: "calculator", id: `calc-${key}`, hidden: "" }, [h("p", {}, [intro]), ...rows, error, result]);
}

/** A filter as the server works it out: its parts and corner, the sum, what it does, its levels. @param {any} f */
function filterAnswer(f) {
  return h("div", { class: "filter-answer" }, [
    h("h3", {}, [`${f.r} and ${f.c}: ${f.corner_text}`]),
    h("p", { class: "values" }, [f.working]),
    h("p", {}, [f.effect]),
    h("table", {}, [h("tbody", {}, [h("tr", {}, f.levels.map((/** @type {any} */ lv) => h("th", {}, [`at ${lv.freq}`]))), h("tr", {}, f.levels.map((/** @type {any} */ lv) => h("td", { class: "values" }, [lv.db])))])]),
  ]);
}

/** Rows of a small two-column answer table. @param {Array<[string, string]>} rows */
const answerTable = (rows) => h("table", {}, [h("tbody", {}, rows.map(([a, b]) => h("tr", {}, [h("th", {}, [a]), h("td", { class: "values" }, [b])])))]);

/** Filter: the corner from R and C, and a second pair to compare (D-319). @param {Record<string, string>} kinds */
function filterCalculator(kinds) {
  const kind = selectRow("filter-kind", "Filter", kinds);
  const r = inputRow("filter-r", "Resistor", "e.g. 100k");
  const c = inputRow("filter-c", "Capacitor", "e.g. 1u, 47n");
  const r2 = inputRow("filter-r2", "Compare with R", "the same");
  const c2 = inputRow("filter-c2", "and C", "e.g. 10u");
  return calculator({
    key: "filter",
    intro: "A resistor and a capacitor make a filter. Type both, the way they're written on a schematic, to see where it starts cutting and what that does to a guitar. Fill in Compare with to see what another value would do.",
    rows: [kind.row, r.row, c.row, r2.row, c2.row],
    fields: [kind.select, r.input, c.input, r2.input, c2.input],
    ready: () => Boolean(r.input.value.trim() && c.input.value.trim()),
    url: () => `api/tools/filter?kind=${kind.select.value}&r=${typed(r)}&c=${typed(c)}&r2=${typed(r2)}&c2=${typed(c2)}`,
    show: (body) => [
      h("p", {}, [`The corner, where the level is 3 dB down: ${body.formula}`]),
      ...body.filters.map(filterAnswer),
      ...(body.change ? [h("p", { id: "filter-change" }, [body.change])] : []),
    ],
  });
}

/** Filter: the part a corner needs, given the other (D-320). @param {Record<string, string>} kinds @param {Record<string, string>} series */
function filterPartCalculator(kinds, series) {
  const kind = selectRow("part-kind", "Filter", kinds);
  const freq = inputRow("part-freq", "Corner (Hz)", "e.g. 100, 1k");
  const r = inputRow("part-r", "Resistor", "e.g. 1M, or blank to find it");
  const c = inputRow("part-c", "Capacitor", "e.g. 47n, or blank to find it");
  const values = selectRow("part-series", "Standard values", series);
  const one = () => Boolean(r.input.value.trim()) !== Boolean(c.input.value.trim());
  return calculator({
    key: "filter-part",
    intro: "Start from the corner you want: type it and one of the two parts, and leave the other blank. It works out the blank one and the nearest value you can buy.",
    rows: [kind.row, freq.row, r.row, c.row, values.row],
    fields: [kind.select, freq.input, r.input, c.input, values.select],
    ready: () => Boolean(freq.input.value.trim()) && one(),
    url: () => `api/tools/filter/part?kind=${kind.select.value}&freq=${typed(freq)}&r=${typed(r)}&c=${typed(c)}&series=${values.select.value}`,
    show: (body) => [
      h("p", {}, [`The ${body.find}: ${body.formula}`]),
      h("h3", { id: "part-answer" }, [`${body.exact}: use ${body.standard} (${body.series})`]),
      h("p", {}, [`With ${body.standard} the corner is ${body.filter.corner_text}, ${body.corner_off} from the one asked for.`]),
      filterAnswer(body.filter),
    ],
  });
}

/** Voltage divider, and how far a load pulls its middle down (D-320). */
function dividerCalculator() {
  const supply = inputRow("div-supply", "Supply (V)", "e.g. 9");
  supply.input.value = "9";
  const r1 = inputRow("div-r1", "Top resistor", "from the supply, e.g. 10k");
  const r2 = inputRow("div-r2", "Bottom resistor", "to ground, e.g. 10k");
  const load = inputRow("div-load", "Load on the middle", "optional, e.g. 1M");
  return calculator({
    key: "divider",
    intro: "Two resistors from the supply to ground make a lower voltage in the middle: a bias (VREF) or a level. Whatever the middle feeds sits in parallel with the bottom resistor, so give it as the load to see how far the voltage drops.",
    rows: [supply.row, r1.row, r2.row, load.row],
    fields: [supply.input, r1.input, r2.input, load.input],
    ready: () => Boolean(supply.input.value.trim() && r1.input.value.trim() && r2.input.value.trim()),
    url: () => `api/tools/divider?supply=${typed(supply)}&r1=${typed(r1)}&r2=${typed(r2)}&load=${typed(load)}`,
    show: (body) => [
      h("h3", { id: "div-middle" }, [`The middle: ${body.middle}`]),
      h("p", { class: "values" }, [body.working]),
      h("p", {}, [`It draws ${body.current} from the supply, and looks like ${body.source} (R1 ‖ R2) to what it feeds. ${body.holds}`]),
      ...(body.sag ? [h("p", { id: "div-sag" }, [body.sag])] : []),
    ],
  });
}

/** Parallel and series: values combined, and a value made from standard parts (D-320). @param {Record<string, string>} series */
function combineCalculator(series) {
  const kind = selectRow("comb-kind", "Parts", { resistor: "Resistors", capacitor: "Capacitors" });
  const values = inputRow("comb-values", "Combine", "e.g. 10k, 22k");
  const target = inputRow("comb-target", "Make this value", "e.g. 6k5");
  const choice = selectRow("comb-series", "From", series);
  return calculator({
    key: "combine",
    intro: "List values to see them in series and in parallel, or type a value you need to find the standard parts that make it. Resistors add in series; capacitors add in parallel.",
    rows: [kind.row, values.row, target.row, choice.row],
    fields: [kind.select, values.input, target.input, choice.select],
    ready: () => Boolean(values.input.value.trim() || target.input.value.trim()),
    url: () => `api/tools/combine?kind=${kind.select.value}&values=${typed(values)}&target=${typed(target)}&series=${choice.select.value}`,
    show: (body) => [
      ...(body.totals ? [h("h3", {}, [body.totals.listed]), answerTable([["In series", body.totals.series], ["In parallel", body.totals.parallel]])] : []),
      ...(body.make
        ? [
            h("h3", {}, [`To make ${body.make.value} from ${body.make.series} values`]),
            h("table", { id: "comb-make" }, [h("tbody", {}, body.make.options.map((/** @type {any} */ o) => h("tr", {}, [h("th", {}, [o.how]), h("td", { class: "values" }, [o.makes]), h("td", { class: "values" }, [o.off])])))]),
          ]
        : []),
    ],
  });
}

/** Decibels and voltage ratios, either way, and a signal through them (D-320). */
function dbCalculator() {
  const db = inputRow("db-db", "Level (dB)", "e.g. 22, -6");
  const times = inputRow("db-times", "Ratio (times)", "e.g. 12.6, 0.5");
  const volts = inputRow("db-volts", "Signal in", "optional, e.g. 300m");
  let from = "db"; // the box typed in last: the other is filled from the answer
  db.input.addEventListener("input", () => (from = "db"));
  times.input.addEventListener("input", () => (from = "times"));
  return calculator({
    key: "db",
    intro: "Gains in the app are in dB. Type a level in dB or a ratio in times and the other fills in. Every 6 dB doubles the voltage and every 20 dB makes it ten times; minus halves it and divides it. Give a signal to see what comes out.",
    rows: [db.row, times.row, volts.row],
    fields: [db.input, times.input, volts.input],
    ready: () => Boolean((from === "db" ? db : times).input.value.trim()),
    url: () => (from === "db" ? `api/tools/db?db=${typed(db)}` : `api/tools/db?times=${typed(times)}`) + `&volts=${typed(volts)}`,
    show: (body) => {
      if (from === "db") times.input.value = body.times;
      else db.input.value = body.db.replace(" dB", "");
      return [h("p", { class: "values" }, [body.working]), ...(body.out ? [h("p", { id: "db-out" }, [body.out])] : [])];
    },
  });
}

const CALCULATORS = {
  filter: "Filter: the corner from R and C",
  "filter-part": "Filter: a part for the corner you want",
  divider: "Voltage divider",
  combine: "Parallel and series",
  db: "Decibels",
};

/**
 * Tools → Calculators… (D-319, D-320): one window, a picker at the top; the last one used
 * opens again. The server works every sum out (`solum/calculators.py`).
 */
export async function calculatorsSheet() {
  const { filters, series } = await tables();
  const pick = selectRow("calc-pick", "Calculator", CALCULATORS);
  const sections = [filterCalculator(filters), filterPartCalculator(filters, series), dividerCalculator(), combineCalculator(series), dbCalculator()];
  const showPicked = () => {
    for (const s of sections) s.hidden = s.id !== `calc-${pick.select.value}`;
    remember("solum.calculator", pick.select.value);
    /** @type {HTMLInputElement | null} */ (sections.find((s) => !s.hidden)?.querySelector("input"))?.focus();
  };
  const last = remembered("solum.calculator");
  if (typeof last === "string" && last in CALCULATORS) pick.select.value = last;
  pick.select.addEventListener("change", showPicked);
  sheet({ title: "Calculators", id: "calculators", body: [pick.row, ...sections] });
  showPicked();
}

/** Tools → Resistor colour code. */
export async function resistorSheet() {
  const { colours } = await tables();
  let count = 4;
  const value = inputRow("tool-ohms", "Value", "e.g. 4k7, 470R, 2M2");
  const error = h("p", { class: "error", role: "alert", hidden: "" });
  const drawing = h("div", { class: "drawing" });
  const result = h("div", { class: "tool-result", id: "tool-result" });
  const picks = h("div", { class: "band-picks" });
  /** @type {HTMLSelectElement[]} */
  let selects = [];
  const option = (/** @type {any} */ c, /** @type {string} */ text) => new Option(`${c.name} · ${text}`, c.name);
  const buildSelects = (/** @type {string[]} */ chosen) => {
    const digits = colours.filter((c) => c.digit !== null);
    const roles = [...Array(count - 2).fill("digit"), "multiplier", "tolerance"];
    selects = roles.map((role, i) => {
      const s = /** @type {HTMLSelectElement} */ (h("select", { "data-role": role, "aria-label": `Band ${i + 1}: ${role}`, id: `band-${i + 1}` }));
      const list = role === "digit" ? digits : role === "multiplier" ? colours : colours.filter((c) => c.tolerance !== null);
      for (const c of list) s.append(option(c, role === "digit" ? String(c.digit) : role === "multiplier" ? c.times : `±${c.tolerance} %`));
      s.value = chosen[i];
      s.addEventListener("change", () => {
        fromBands = true;
        ask();
      });
      return s;
    });
    picks.replaceChildren(...selects.map((s, i) => h("label", { class: "band-pick" }, [h("span", {}, [`Band ${i + 1}`]), s])));
  };
  const draw = () => drawing.replaceChildren(resistorDrawing(selects.map((s) => s.value)));
  let fromBands = false;
  const ask = asker(error, () =>
    fromBands ? `api/tools/resistor?bands=${selects.map((s) => s.value).join(",")}` : `api/tools/resistor?value=${encodeURIComponent(value.input.value)}`,
  (body) => {
    if (fromBands) value.input.value = body.short;
    const bands = count === 4 ? body.bands4 : body.bands5;
    if (!fromBands && bands) {
      const tolerance = selects.at(-1)?.value ?? (count === 4 ? "gold" : "brown");
      buildSelects([...bands, tolerance]);
    }
    if (bands || fromBands) draw();
    else drawing.replaceChildren(); // the bands shown would be another value
    const tol = fromBands ? body.tolerance : Number(colours.find((c) => c.name === selects.at(-1)?.value)?.tolerance);
    const lines = [h("p", { class: "tool-value" }, [`${body.short} \u00b1${tol} %`])];
    if (!bands) lines.push(h("p", { class: "warning" }, [count === 4 ? `${body.short} needs three significant figures: use 5 bands.` : `${body.short} can't be shown with ${count} bands.`]));
    lines.push(h("p", {}, [body.series.length ? `A standard value (${body.series.join(", ")}).` : `Not a standard value. Nearest: ${body.nearest.map((/** @type {any} */ n) => `${n.below} or ${n.above} (${n.series}, ${n.tolerance} %)`).join("; ")}.`]));
    result.replaceChildren(...lines);
  });
  const setCount = (/** @type {number} */ n) => {
    count = n;
    for (const b of toggle) b.setAttribute("aria-pressed", String(Number(b.dataset.bands) === n));
    buildSelects(n === 4 ? ["yellow", "violet", "red", "gold"] : ["yellow", "violet", "black", "brown", "brown"]);
    fromBands = !value.input.value.trim(); // keep the value typed, in the new number of bands
    ask();
  };
  const toggle = [4, 5].map((n) => {
    const b = h("button", { type: "button", "data-bands": String(n), "aria-pressed": String(n === count) }, [`${n} bands`]);
    b.addEventListener("click", () => setCount(n));
    return b;
  });
  value.input.addEventListener("input", () => {
    fromBands = false;
    if (value.input.value.trim()) ask();
  });
  buildSelects(["yellow", "violet", "red", "gold"]);
  value.input.value = "4k7";
  const guideLink = h("button", { type: "button", id: "open-resistor-guide" }, ["Colour chart and how values are written…"]);
  guideLink.addEventListener("click", () => void resistorGuideSheet());
  sheet({
    title: "Resistor colour code",
    id: "resistor-code",
    wide: true,
    body: [
      h("div", { class: "tool-grid" }, [
        h("div", {}, [
          value.row,
          h("div", { class: "form-row" }, [h("span", {}, ["Bands"]), h("span", { class: "segmented" }, toggle), h("span", {}, [])]),
          picks,
          error,
        ]),
        h("div", {}, [drawing, result]),
      ]),
      h("p", { class: "hint-text" }, ["Read from the end where the bands bunch together; the tolerance band (often gold, or brown on 1 % parts) sits apart at the other end."]),
      guideLink,
    ],
  });
  fromBands = false;
  ask();
}

/** @type {ReturnType<typeof infoPopup> | null} the ⓘ pop-up the parts list's rows share (made once) */
let partInfo = null;

/**
 * A card we may not ship in the parts list (9c): its id, description and *Not included*,
 * with an ⓘ that says why, what to get (with its link) and how to add it.
 * @param {import("./parts.js").PartEntry} e
 */
function excludedEntry(e) {
  partInfo ??= infoPopup({ inSheet: true });
  const [why, get, add] = excludedText(e);
  const info = partInfo.button(`${e.id}, not included`, () => [
    why,
    h("p", { class: "note" }, [get, " ", h("a", { href: e.url ?? "", target: "_blank", rel: "noopener noreferrer" }, [`${e.url} ↗`])]),
    add,
  ], "Why it isn't included, and where to get it");
  return h("div", { class: "part-entry part-excluded", "data-part": e.id, "data-origin": "excluded" }, [
    h("div", { class: "part-row" }, [
      h("span", { class: "part-id" }, [e.id]),
      h("span", { class: "part-desc" }, [e.description]),
      h("span", { class: "part-origin origin-excluded" }, [ORIGIN_TAGS.excluded]),
      info,
    ]),
  ]);
}

/**
 * One model in the parts list: its id, description, where its card came from and its
 * datasheet link; opened, its origin, the sheet it was fitted to, its caveats and checks.
 * A card not included has a row of its own (`excludedEntry`).
 * @param {import("./parts.js").PartEntry} e
 */
function partEntry(e) {
  if (e.origin === "excluded") return excludedEntry(e);
  const link = e.datasheet ? h("a", { href: e.datasheet, target: "_blank", rel: "noopener noreferrer", class: "part-sheet" }, ["Datasheet ↗"]) : h("span", {}, []);
  const body = [h("p", {}, [originText(e)])];
  if (e.figure) body.push(h("p", { class: "part-figure" }, [`From the sheet: ${e.figure}.`]));
  if (e.note) body.push(h("p", { class: "part-note" }, [e.note]));
  body.push(h("p", {}, [checksText(e)]));
  if (e.unchecked.length) body.push(h("ul", { class: "part-unchecked" }, e.unchecked.map((u) => h("li", {}, [h("strong", {}, [`${u.name}: `]), u.note]))));
  if (e.package) body.push(h("p", { class: "hint-text" }, [`Package and pin numbers: ${e.package}.`]));
  return h("details", { class: "part-entry", "data-part": e.id }, [
    h("summary", {}, [
      h("span", { class: "part-id" }, [e.id]),
      h("span", { class: "part-desc" }, [e.description]),
      h("span", { class: `part-origin origin-${e.origin}` }, [ORIGIN_TAGS[e.origin]]),
      link,
    ]),
    h("div", { class: "part-body" }, body),
  ]);
}

/** Tools → Parts and datasheets (9c): every model the app knows, by type. */
export async function partsSheet() {
  /** @type {import("./parts.js").PartEntry[]} */
  const entries = await getJson("api/models/catalogue");
  const search = /** @type {HTMLInputElement} */ (h("input", { id: "parts-search", type: "search", autocomplete: "off", spellcheck: "false", placeholder: "e.g. 2N5089, germanium, op-amp" }));
  const list = h("div", { class: "parts-list", id: "parts-list" });
  // toggles, all on to start: each shows or hides its kind of part (9c)
  const filters = Object.entries(SHOWS).map(([key, [label]]) => {
    const b = h("button", { type: "button", "data-show": key, "aria-pressed": "true" }, [label]);
    b.addEventListener("click", () => {
      b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
      show();
    });
    return b;
  });
  const show = () => {
    const on = filters.filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => /** @type {string} */ (b.dataset.show));
    const groups = partGroups(entries, search.value, on);
    list.replaceChildren(
      ...(groups.length ? [] : [h("p", {}, [on.length ? "No part matches that." : "Turn on Yours, Stock or Not included to see parts."])]),
      ...groups.flatMap((g) => [h("h3", {}, [`${g.name} · ${g.entries.length}`]), ...g.entries.map(partEntry)]),
    );
  };
  search.addEventListener("input", show);
  show();
  sheet({
    title: "Parts and datasheets",
    id: "parts-datasheets",
    wide: true,
    body: [
      h("p", {}, ["Every part model Solum Builder simulates with, and where each came from. Open one for what its datasheet covers and where the model is a guess. Datasheet links open the maker's (or an archive's) copy; most can't be shipped with the app. Cards marked Not included can't be shipped either: their ⓘ says where to get each."]),
      h("div", { class: "form-row parts-find" }, [h("label", { for: "parts-search" }, ["Find"]), search, h("span", { class: "segmented", role: "group", "aria-label": "Show" }, filters)]),
      list,
    ],
  });
  search.focus();
}

/** Part types a card can be added as, in words. */
const ADD_AS = /** @type {Record<string, string>} */ ({ diode: "Diode", led: "LED", bjt: "Transistor (BJT)", jfet: "JFET", mosfet: "MOSFET", opamp: "Op-amp" });
/** An op-amp's pins, as the server names them, and in words. */
const OPAMP_PINS = [["+", "+ (non-inverting in)"], ["-", "− (inverting in)"], ["V+", "V+ (positive supply)"], ["V-", "V− (negative supply)"], ["out", "out"], ["", "not connected"]];

/**
 * An op-amp card's pin dropdowns, one per node of its `.subckt`, pre-filled with the
 * server's guess (the usual order), and the maker's comment above the line, which often
 * names them.
 * @param {{name: string, nodes: string[], comment: string, guess: string[]}} found
 * @param {() => void} changed
 */
function pinRows(found, changed) {
  const selects = found.nodes.map((node, i) => {
    const select = /** @type {HTMLSelectElement} */ (h("select", { id: `model-pin-${i}`, "data-node": node }));
    select.replaceChildren(...OPAMP_PINS.map(([value, text]) => new Option(text, value)));
    select.value = found.guess[i] ?? "";
    select.addEventListener("change", changed);
    return select;
  });
  const rows = found.nodes.map((node, i) => h("div", { class: "form-row" }, [h("label", { for: `model-pin-${i}` }, [`Node ${node}`]), selects[i], h("span", { class: "unit" }, [])]));
  const said = found.comment ? [h("p", {}, ["The maker's comment above the .subckt line:"]), h("pre", { class: "model-comment" }, [found.comment])] : [];
  return {
    pins: () => selects.map((s) => s.value),
    el: h("div", { id: "model-pins" }, [
      h("p", {}, [`Which pin is on each of ${found.name}'s nodes, in the order its .subckt line gives them. They start in the usual order (+, −, V+, V−, out); makers' comments often say otherwise. The check wires it as a buffer and tells you if the order looks wrong.`]),
      ...said,
      ...rows,
    ]),
  };
}

/**
 * Tools → Add a model (9c): pick a SPICE file, choose one of its `.model` cards and what
 * part it is, check it (the server cleans it and measures it), then add it to your models.
 * @param {() => Promise<void>} onAdded refreshes the app's model lists
 */
export async function addModelSheet(onAdded) {
  const file = /** @type {HTMLInputElement} */ (h("input", { type: "file", id: "model-file", accept: ".lib,.mod,.model,.txt,.cir,.sp,.spi" }));
  const card = /** @type {HTMLSelectElement} */ (h("select", { id: "model-card" }));
  const as = /** @type {HTMLSelectElement} */ (h("select", { id: "model-as" }));
  const name = inputRow("model-id", "Name in Solum Builder", "e.g. 2N3904-mine");
  const channels = /** @type {HTMLSelectElement} */ (h("select", { id: "model-channels" }));
  channels.replaceChildren(new Option("one (a single)", "1"), new Option("two (a dual)", "2"), new Option("four (a quad)", "4"));
  const channelRow = h("div", { class: "form-row", hidden: "" }, [h("label", { for: "model-channels" }, ["In a package"]), channels, h("span", { class: "unit" }, [])]);
  const pinsAt = h("div", {});
  /** @type {(() => string[]) | null} */
  let pins = null;
  const check = h("button", { type: "button", id: "model-check" }, ["Check"]);
  const add = /** @type {HTMLButtonElement} */ (h("button", { type: "button", class: "primary", id: "model-add", disabled: "" }, ["Add to my models"]));
  const error = h("p", { class: "error", role: "alert", hidden: "" });
  const result = h("div", { class: "tool-result", id: "model-result" });
  const choose = h("div", { hidden: "" }, [
    h("div", { class: "form-row" }, [h("label", { for: "model-card" }, ["Card"]), card, h("span", { class: "unit" }, [])]),
    h("div", { class: "form-row" }, [h("label", { for: "model-as" }, ["It's a"]), as, h("span", { class: "unit" }, [])]),
    channelRow,
    pinsAt,
    name.row,
    h("div", { class: "button-row" }, [check, add]),
  ]);
  /** @type {{text: string, filename: string, cards: Array<{name: string, spice_type: string, part_types: string[], nodes: string[], comment: string, guess: string[], suggested: string}>}} */
  let upload = { text: "", filename: "", cards: [] };
  const fail = (/** @type {unknown} */ err) => {
    error.hidden = false;
    error.textContent = /** @type {Error} */ (err).message;
  };
  const changed = () => {
    add.disabled = true;
    result.replaceChildren();
    error.hidden = true;
  };
  const pickCard = () => {
    const found = upload.cards.find((c) => c.name === card.value);
    as.replaceChildren(...(found?.part_types ?? []).map((t) => new Option(ADD_AS[t] ?? t, t)));
    const subckt = found?.spice_type === "SUBCKT";
    const rows = subckt && found ? pinRows(found, changed) : null;
    pins = rows?.pins ?? null;
    pinsAt.replaceChildren(...(rows ? [rows.el] : []));
    channelRow.hidden = !subckt;
    channels.value = "1";
    name.input.value = found?.suggested ?? card.value; // `<card>-mine` when the name's taken
    changed();
  };
  file.addEventListener("change", async () => {
    const f = file.files?.[0];
    if (!f) return;
    changed();
    choose.hidden = true;
    try {
      const text = await f.text();
      const body = await postJson("api/models/import", { text, filename: f.name });
      upload = { text, filename: f.name, cards: body.cards };
      card.replaceChildren(...body.cards.map((/** @type {any} */ c) => new Option(c.spice_type === "SUBCKT" ? `${c.name} (.subckt, ${c.nodes.length} nodes)` : `${c.name} (${c.spice_type})`, c.name)));
      choose.hidden = false;
      pickCard();
    } catch (err) {
      fail(err);
    }
  });
  card.addEventListener("change", pickCard);
  as.addEventListener("change", changed);
  channels.addEventListener("change", changed);
  name.input.addEventListener("input", changed);
  const ask = (/** @type {boolean} */ save) => postJson("api/models/import", { text: upload.text, filename: upload.filename, card: card.value, part_type: as.value, id: name.input.value, save, ...(pins ? { pins: pins(), channels: Number(channels.value) } : {}) });
  check.addEventListener("click", async () => {
    changed();
    check.setAttribute("aria-busy", "true");
    try {
      const body = await ask(false);
      const odd = body.checks.filter((/** @type {any} */ c) => !c.plausible);
      result.replaceChildren(
        h("table", {}, [h("tbody", {}, body.checks.map((/** @type {any} */ c) => h("tr", { class: c.plausible ? "" : "odd" }, [h("td", {}, [c.name]), h("td", { class: "values" }, [c.text]), h("td", {}, [c.at]), h("td", {}, [c.plausible ? "" : "looks wrong"])])))]),
        ...(odd.length ? [h("p", { class: "warning" }, [`${odd.length === 1 ? "One reading looks" : "Some readings look"} wrong for a ${ADD_AS[as.value] ?? as.value}. Check the card is the part you meant before adding it.`])] : []),
        ...(body.fixes.length ? [h("p", {}, [`Cleaned for the simulator: ${body.fixes.join("; ")}.`])] : []),
      );
      add.disabled = false;
    } catch (err) {
      fail(err);
    } finally {
      check.removeAttribute("aria-busy");
    }
  });
  add.addEventListener("click", async () => {
    add.disabled = true;
    try {
      const body = await ask(true);
      await onAdded();
      result.append(h("p", { class: "ok", id: "model-added" }, [`Added ${body.model.id}. It's in the model lists now, and in Tools → Parts and datasheets.`]));
      /** @type {HTMLElement | null} */ (view.el.querySelector(".sheet-close"))?.focus(); // Add is spent: keep Esc working
    } catch (err) {
      fail(err);
    }
  });
  const view = sheet({
    title: "Add a model",
    id: "new-model",
    body: [
      h("p", {}, ["Add a part from a maker's SPICE file (.lib, .mod): a diode, LED, transistor, JFET or MOSFET .model card, or an op-amp .subckt. Solum Builder cleans it for the simulator and measures it, so you can see it behaves like the part. It's saved with your circuits and stays on this machine."]),
      h("div", { class: "form-row" }, [h("label", { for: "model-file" }, ["File"]), file, h("span", { class: "unit" }, [])]),
      error,
      choose,
      result,
    ],
  });
}
