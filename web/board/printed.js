/**
 * A circuit's kept board as files for the build package (D-386): the board canvas's own
 * drawing on paper colours, both sides, parts named by ref only (values are in the parts
 * list), with the column letters and strip numbers the cut
 * and link lists name holes by; the guidance, hover labels and grips taken out. The parts
 * side carries the off-board parts and their wires; the copper side is mirrored as it lies
 * under the iron, cuts ✕ and every solder joint. The PDF is made from them on the server,
 * filled to read and at real size (`board-logic.js`'s STEP board units to 0.1"); `bare` is
 * the parts side without the off-board parts, for the real-size page.
 */

import { paperSvg, paperText } from "../print-svg.js";
import { chosenMarks, offBoardDrawing, readBoard } from "./board-logic.js";
import { boardCanvas } from "./canvas.js";

const MARGIN = 6; // board units round the drawing
// what's for the screen only (canvas.js's classes): guidance, grips, hit areas, hover names
const DROP = [".ghost", ".guide", ".ruler-hit", "title", ".link-hit", ".suggest-hit", ".wire-run", ".lug-end", ".leg-name"];
/** @type {import("./canvas.js").CanvasApp} */
const STILL = { onClick() {}, onLine() {}, onPress: () => false, onDrag() {}, onRelease() {}, onHover() {}, onMenu: () => false };

/**
 * Both sides of a circuit's kept board as SVG text, ready to send.
 * @param {any} circuit the circuit, its `stripboard` the board
 * @param {import("./board-logic.js").Progress} progress what `/api/stripboard` answered for it
 * @returns {{parts: string, bare: string, copper: string}}
 */
export function printableBoard(circuit, progress) {
  const board = readBoard(circuit.stripboard);
  /** @param {boolean} copper @param {boolean} [bare] without the off-board parts */
  const side = (copper, bare = false) => {
    const { host, svg } = paperSvg("board-drawing");
    try {
      const canvas = boardCanvas(svg, STILL);
      if (copper) canvas.side(true);
      canvas.draw(board, progress.footprints, circuit, { values: false, rulers: true, paper: true, off: bare ? undefined : offBoardDrawing(progress, board), chosen: chosenMarks(progress) });
      return paperText(svg, DROP, MARGIN, `${circuit.name}: stripboard, ${copper ? "copper side" : "parts side"}`);
    } finally {
      host.remove();
    }
  };
  return { parts: side(false), bare: side(false, true), copper: side(true) };
}
