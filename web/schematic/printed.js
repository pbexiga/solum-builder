/**
 * A circuit's schematic as a file (D-205): the sheet's own renderer, on paper colours
 * (theme.css `.print`), with the grid and everything you click on taken out, cropped to the
 * drawing, its styles written onto each element so it needs no stylesheet. For the build
 * package and the schematic's download; the PDF is made from it on the server.
 */

import { paperSvg, paperText } from "../print-svg.js";
import { Schematic } from "./render.js";

const MARGIN = 20; // schematic units around the drawing
// interactive or on-screen-only layers (render.js's classes)
const DROP = [".grid", "defs", ".hit", ".part-hit", ".pin-hit", ".end-hit", ".text-hit", ".overlay", ".dc-layer", ".z-layer", ".mark-layer"];

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
  const { host, svg } = paperSvg();
  try {
    new Schematic(svg, /** @type {any} */ ({})).draw(view, positions, { fit: false });
    return paperText(svg, DROP, MARGIN, title);
  } finally {
    host.remove();
  }
}
