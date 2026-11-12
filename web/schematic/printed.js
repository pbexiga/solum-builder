/**
 * A circuit's schematic as a file (D-205): the sheet's own renderer, on paper colours
 * (theme.css `.print`), with the grid and everything you click on taken out, cropped to the
 * drawing, its styles written onto each element so it needs no stylesheet. For the build
 * package and the schematic's download; the PDF is made from it on the server.
 */

import { Schematic } from "./render.js";

const SVG = "http://www.w3.org/2000/svg";
const MARGIN = 20; // schematic units around the drawing
// interactive or on-screen-only layers (render.js's classes)
const DROP = [".grid", "defs", ".hit", ".part-hit", ".pin-hit", ".end-hit", ".text-hit", ".overlay", ".dc-layer", ".z-layer", ".mark-layer"];
const STYLES = ["fill", "stroke", "stroke-width", "stroke-dasharray", "opacity", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline"];

/**
 * Each switch pole's saved position, by ref (the drawing shows the switch as it was saved).
 * @param {any} circuit @returns {Record<string, number>}
 */
export function savedPositions(circuit) {
  return Object.fromEntries(circuit.parts.filter((/** @type {any} */ p) => p.type === "switch").map((/** @type {any} */ p) => [p.ref, p.position ?? 0]));
}

/**
 * The schematic of a circuit view as SVG text, ready to save.
 * @param {any} view the server's circuit view @param {Record<string, number>} positions
 * @param {string} title for the file's `<title>`
 * @returns {string}
 */
export function printableSvg(view, positions, title) {
  const host = document.createElement("div");
  host.className = "print";
  host.setAttribute("style", "position: fixed; left: -20000px; top: 0; width: 1200px; height: 900px;");
  const svg = /** @type {SVGSVGElement} */ (document.createElementNS(SVG, "svg"));
  svg.setAttribute("width", "1200");
  svg.setAttribute("height", "900");
  host.append(svg);
  document.body.append(host);
  try {
    new Schematic(svg, /** @type {any} */ ({})).draw(view, positions, { fit: false });
    for (const sel of DROP) svg.querySelectorAll(sel).forEach((n) => n.remove());
    // every style read before any class goes: the rules match on the ancestors' classes
    const nodes = [...svg.querySelectorAll("*")];
    const styled = nodes.map((node) => {
      const cs = getComputedStyle(node);
      if (cs.display === "none" || cs.visibility === "hidden") return null;
      /** @type {Array<[string, string]>} */
      const found = STYLES.map((prop) => [prop, cs.getPropertyValue(prop)]);
      if (cs.getPropertyValue("vector-effect") === "non-scaling-stroke") found.push(["vector-effect", "non-scaling-stroke"]);
      return found.filter(([, v]) => v && v !== "normal" && v !== "auto");
    });
    nodes.forEach((node, i) => {
      const found = styled[i];
      if (!found) return node.remove();
      for (const [prop, v] of found) node.setAttribute(prop, v);
      node.removeAttribute("class");
      for (const a of [...node.attributes]) if (a.name.startsWith("data-")) node.removeAttribute(a.name);
    });
    const root = /** @type {SVGGraphicsElement} */ (svg.firstElementChild);
    const box = root.getBBox();
    const [x, y, w, h] = [box.x - MARGIN, box.y - MARGIN, box.width + 2 * MARGIN, box.height + 2 * MARGIN];
    svg.setAttribute("xmlns", SVG);
    svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
    svg.setAttribute("width", String(Math.round(w)));
    svg.setAttribute("height", String(Math.round(h)));
    const name = document.createElementNS(SVG, "title");
    name.textContent = title;
    const paper = document.createElementNS(SVG, "rect");
    const white = getComputedStyle(host).getPropertyValue("--surface-0").trim();
    for (const [k, v] of Object.entries({ x, y, width: w, height: h, fill: white })) paper.setAttribute(k, String(v));
    svg.prepend(name, paper);
    return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(svg)}\n`;
  } finally {
    host.remove();
  }
}
