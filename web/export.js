/**
 * File → Export (DOM, 9d1, D-203): the Ready to build list, then each output to download
 * or open. The logic is export-logic.js's; everything is made on the server from the last save.
 */

import { getJson, postJson } from "./api.js";
import { printableBoard } from "./board/printed.js";
import { sheet } from "./editor/form.js";
import { exportTarget, exportUrl, fileName, readyRows, savedUrl } from "./export-logic.js";
import { h } from "./panels.js";
import { printableSvg, savedPositions } from "./schematic/printed.js";

const SEVERITY = { error: "Error", warning: "Warning", info: "Note" };

/**
 * The outputs, each a link: `download` saves the file, else it opens in a new tab.
 * @type {Array<{id: string, label: string, file: string, download: boolean, hint: string}>}
 */
const OUTPUTS = [
  { id: "bom-csv", label: "Parts list (CSV)", file: "bom.csv", download: true, hint: "for a spreadsheet or an order" },
  { id: "bom-page", label: "Parts list (page to print)", file: "bom.html", download: false, hint: "on the board, then off it" },
  { id: "bom-pdf", label: "Parts list (PDF)", file: "bom.pdf", download: true, hint: "the same page, A4" },
  { id: "bias-page", label: "Bias sheet (page to print)", file: "bias.html", download: false, hint: "trimmer settings and the DC to check on every transistor and chip" },
  { id: "bias-pdf", label: "Bias sheet (PDF)", file: "bias.pdf", download: true, hint: "the same page, A4" },
  { id: "notes-page", label: "Notes (page to print)", file: "notes.html", download: false, hint: "the description, the sheet's notes, each knob and switch" },
  { id: "notes-pdf", label: "Notes (PDF)", file: "notes.pdf", download: true, hint: "the same page, A4" },
  { id: "wiring-page", label: "Wiring (page to print)", file: "wiring.html", download: false, hint: "generic for now: the footswitch, the jacks, the DC jack" },
  { id: "wiring-pdf", label: "Wiring (PDF)", file: "wiring.pdf", download: true, hint: "the same page, A4" },
  { id: "circuit-json", label: "Circuit file (JSON)", file: "circuit.json", download: true, hint: "the circuit as saved, to keep, share or open again" },
  { id: "netlists", label: "Netlists and models (zip)", file: "netlists.zip", download: true, hint: "for ngspice: DC, frequency response and waveform, with every model's card" },
];

/**
 * Open File → Export.
 * @param {{source: {kind: string, id: string} | null, dirty: boolean, dismissed?: import("./problems.js").Dismissal[],
 *   onPick: (ref: string) => void}} open `onPick`: a row's part clicked (the sheet closes first)
 */
export async function exportSheet(open) {
  const target = exportTarget(open.source);
  if ("why" in target) {
    sheet({ title: "Export", id: "export", body: [h("p", { class: "export-why" }, [target.why])] });
    return;
  }
  const base = exportUrl(target);
  const ready = h("div", { class: "export-ready", "aria-busy": "true" }, [h("p", { class: "empty" }, ["Checking the last save…"])]);
  const links = OUTPUTS.map((o) =>
    h("li", {}, [
      h("a", { href: `${base}/${o.file}`, id: `export-${o.id}`, ...(o.download ? { download: "" } : { target: "_blank", rel: "noopener" }) }, [o.label]),
      h("span", { class: "hint-text" }, [` · ${o.hint}`]),
    ]),
  );
  const schematic = h("button", { type: "button", class: "link", id: "export-schematic-svg" }, ["Schematic (SVG)"]);
  schematic.addEventListener("click", async () => {
    const svg = await schematicSvg(target);
    save(new Blob([svg.text], { type: "image/svg+xml" }), fileName(svg.name, "schematic.svg"));
  });
  links.push(h("li", {}, [schematic, h("span", { class: "hint-text" }, [" \u00b7 the drawing, ink on white"])]));
  const schematicPdf = h("button", { type: "button", class: "link", id: "export-schematic-pdf" }, ["Schematic (PDF)"]);
  schematicPdf.addEventListener("click", async () => {
    const svg = await schematicSvg(target);
    const made = await fetch(`${base}/schematic.pdf`, { method: "POST", body: svg.text, headers: { "Content-Type": "image/svg+xml" } });
    if (made.ok) save(await made.blob(), fileName(svg.name, "schematic.pdf"));
  });
  links.push(h("li", {}, [schematicPdf, h("span", { class: "hint-text" }, [" \u00b7 A4 landscape"])]));
  const boardPdf = h("button", { type: "button", class: "link", id: "export-stripboard-pdf" }, ["Stripboard (PDF)"]);
  const boardNote = h("span", { class: "hint-text", "aria-live": "polite" }, [" \u00b7 the kept board at real size, with its cuts, links and wires"]);
  boardPdf.addEventListener("click", async () => {
    const drawn = await boardSvgs(target);
    if (!drawn.board) return void (boardNote.textContent = " \u00b7 No stripboard layout kept in the last save.");
    const made = await fetch(`${base}/stripboard.pdf`, { method: "POST", body: JSON.stringify(drawn.board), headers: { "Content-Type": "application/json" } });
    if (made.ok) save(await made.blob(), fileName(drawn.name, "stripboard.pdf"));
    else boardNote.textContent = ` \u00b7 ${(await made.json()).message ?? made.statusText}`;
  });
  links.push(h("li", {}, [boardPdf, boardNote]));
  const checking = getJson(`${base}/check`).then((check) => ({ check, ...readyRows(check, open) }));
  const pack = h("button", { type: "button", class: "primary", id: "export-package" }, ["Build package (zip)"]);
  const packNote = h("p", { class: "hint-text", "aria-live": "polite" }, ["Everything below in one zip, with an index page and the circuit file."]);
  pack.addEventListener("click", async () => {
    pack.disabled = true;
    packNote.textContent = "Making the package\u2026";
    try {
      const [svg, drawn, { rows, dismissed }] = await Promise.all([schematicSvg(target), boardSvgs(target), checking]);
      const body = { svg: svg.text, board: drawn.board, ready: rows.map((r) => ({ severity: r.severity, text: r.text })), dismissed };
      const made = await fetch(`${base}/package.zip`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
      if (!made.ok) throw new Error((await made.json()).message ?? made.statusText);
      save(await made.blob(), fileName(svg.name, "build package.zip"));
      packNote.textContent = "Saved. Open index.html in it first.";
    } catch (err) {
      packNote.textContent = `Couldn't make the package: ${/** @type {Error} */ (err).message}`;
    }
    pack.disabled = false;
  });
  const view = sheet({
    title: "Export",
    id: "export",
    body: [h("h3", {}, ["Ready to build"]), ready, h("h3", {}, ["Build package"]), pack, packNote, h("h3", {}, ["Outputs"]), h("ul", { class: "export-outputs" }, links)],
  });
  try {
    const { check, rows, dismissed } = await checking;
    const sub = `${check.name} ${check.version}, as last saved.`;
    const none = h("p", { class: "export-clear" }, ["Nothing to check: every part says what to buy."]);
    const list = rows.length ? readyList(rows, (ref) => { view.close(); open.onPick(ref); }) : [none];
    ready.replaceChildren(h("p", {}, [sub, " Nothing here stops an export."]), ...list, ...dismissedNote(dismissed));
  } catch (err) {
    ready.replaceChildren(h("p", { class: "error" }, [`Couldn't check the last save: ${/** @type {Error} */ (err).message}`]));
  }
  ready.removeAttribute("aria-busy");
}

/**
 * The Ready to build rows as a list (D-203), here and before a version becomes final
 * (D-362): a row naming parts is clicked to pick its first part.
 * @param {import("./export-logic.js").ReadyRow[]} rows @param {(ref: string) => void} pick
 * @returns {Node[]}
 */
export function readyList(rows, pick) {
  const items = rows.map((r) => {
    const li = h("li", { class: `export-row${r.refs.length ? " pick" : ""}` }, [h("span", { class: `severity sev-${r.severity}` }, [SEVERITY[r.severity]]), h("span", {}, [r.text])]);
    if (r.refs.length) li.addEventListener("click", () => pick(r.refs[0]));
    return li;
  });
  return [h("ul", { class: "export-list" }, items)];
}

/** How many build checks were dismissed in Problems, when any. @param {number} n @returns {Node[]} */
export const dismissedNote = (n) => (n ? [h("p", { class: "hint-text" }, [`${n} dismissed in the Problems panel.`])] : []);

/**
 * The last save's schematic, drawn here with the sheet's own renderer (D-205).
 * @param {{kind: string, id: string}} target @returns {Promise<{name: string, text: string}>}
 */
export async function schematicSvg(target) {
  const saved = await getJson(savedUrl(target));
  return { name: saved.circuit.name, text: printableSvg(saved, savedPositions(saved.circuit), saved.circuit.name) };
}

/**
 * The last save's kept board, both sides drawn here with the board canvas (D-386); null
 * when it keeps none.
 * @param {{kind: string, id: string}} target
 * @returns {Promise<{name: string, board: {parts: string, copper: string} | null}>}
 */
export async function boardSvgs(target) {
  const { circuit } = await getJson(savedUrl(target));
  if (!circuit.stripboard) return { name: circuit.name, board: null };
  const progress = await postJson("api/stripboard", { circuit });
  return { name: circuit.name, board: printableBoard(circuit, progress) };
}

/** Hand a file to the browser to save. @param {Blob} blob @param {string} name */
function save(blob, name) {
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.getAttribute("href") ?? ""), 1000);
}
