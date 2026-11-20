/**
 * The Board view (D-368): *Schematic* / *Board*, two views of the open circuit on the one
 * canvas. In the Board view the canvas shows the stripboard (`canvas.js`) and the result
 * panes' column holds the board's own panes instead, reorderable and remembered under
 * their own key (`solum.boardPanes`): Schematic (the drawing, smaller), Tray, Nets,
 * Warnings, Settings. Back in the Schematic view the result panes are as they were.
 * Selecting a part or a net on either drawing lights it on both. The board's state comes
 * from the server's progress check (`POST /api/stripboard`) after every change.
 */

import { postJson } from "../api.js";
import { h } from "../panels.js";
import { reorderable } from "../panes.js";
import { Schematic } from "../schematic/render.js";
import { latestOnly } from "../state.js";
import { boardCanvas } from "./canvas.js";
import { boardRefOf, netWords, netsLine, partsOnNet, readBoard, sizeLine, trayRows } from "./board-logic.js";

/**
 * @typedef {import("../schematic/render.js").Selection} Selection
 * @typedef {import("./board-logic.js").Progress} Progress
 * @typedef {{
 *   circuit: () => any,
 *   view: () => any,
 *   positions: () => Record<string, number>,
 *   selection: () => Selection | null,
 *   select: (selection: Selection | null) => void,
 *   resting: () => Selection | null,
 *   shown: (board: boolean) => void,
 * }} BoardApp
 *   `resting`: what's selected when the empty canvas is clicked (the root's own choice);
 *   `shown`: told when the view changes, so the root sets its hint (`hint`) and buttons
 */

const HINT = "The board, parts side. Click a part to select it on both drawings. Drag the board to pan, scroll to zoom.";

/**
 * @param {HTMLElement} host the canvas's body @param {BoardApp} app
 */
export function boardView(host, app) {
  const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));
  const svg = /** @type {SVGSVGElement} */ (/** @type {unknown} */ ($("board")));
  const column = $("board-panels");
  const results = /** @type {HTMLElement} */ (document.querySelector(".panels"));
  const sizeNote = $("board-size");
  const schematicButton = $("show-schematic");
  const boardButton = $("show-board");
  let active = false;
  let fitted = false;
  let resultsScroll = 0;
  /** @type {{reset: () => void} | null} */
  let panes = null;
  /** @type {Progress | null} */
  let progress = null;
  /** @type {any} the circuit `progress` is of */
  let checked = null;
  const requests = latestOnly();

  const canvas = boardCanvas(svg, {
    onPart: (ref) => {
      const refs = progress?.footprints[ref]?.refs ?? [ref];
      app.select(refs.length === 1
        ? { kind: "part", id: refs[0] }
        : { kind: "items", id: "", items: { parts: refs, wires: [], labels: [] } });
    },
    onEmpty: () => app.select(app.resting()),
  });
  const sheet = new Schematic(/** @type {SVGSVGElement} */ (/** @type {unknown} */ ($("board-sheet"))), {
    onNet: (net) => app.select({ kind: "net", id: net }),
    onPart: (ref) => app.select({ kind: "part", id: ref }),
    onEmpty: () => app.select(app.resting()),
  });

  schematicButton.addEventListener("click", () => show(false));
  boardButton.addEventListener("click", () => show(true));
  // the small schematic only selects: a part dragged there goes back where it was
  /** @type {number[] | null} */
  let pressed = null;
  $("board-sheet").addEventListener("pointerdown", (e) => { pressed = [e.clientX, e.clientY]; }, true);
  window.addEventListener("pointerup", (e) => {
    if (pressed && Math.hypot(e.clientX - pressed[0], e.clientY - pressed[1]) > 3) requestAnimationFrame(() => drawSheet());
    pressed = null;
  }, true);

  /** @param {boolean} board */
  function show(board) {
    if (board === active) return;
    if (board) resultsScroll = results.scrollTop;
    active = board;
    document.body.dataset.show = board ? "board" : "schematic";
    svg.toggleAttribute("hidden", !board); // an SVG element has no `hidden` property
    column.hidden = !board;
    sizeNote.hidden = !board;
    schematicButton.setAttribute("aria-pressed", String(!board));
    boardButton.setAttribute("aria-pressed", String(board));
    if (board) {
      panes ??= reorderable(column, "solum.boardPanes");
      drawSheet(true);
      draw();
      void update();
    } else {
      results.scrollTop = resultsScroll; // hidden, the list may forget where it was
    }
    app.shown(board);
  }

  function drawSheet(fit = false) {
    const view = app.view();
    if (!view) return;
    sheet.draw(view, app.positions(), { fit });
    sheet.select(app.selection());
  }

  function draw() {
    const circuit = app.circuit();
    const board = readBoard(circuit?.stripboard);
    canvas.draw(board, progress?.footprints ?? {}, circuit, { fit: !fitted });
    fitted = true;
    sizeNote.textContent = sizeLine(board);
    light(app.selection());
  }

  /** The progress check of the circuit as it is now, and the panes and board drawn from it. */
  async function update() {
    const circuit = app.circuit();
    if (!active || !circuit || circuit === checked) return;
    const token = requests.next();
    try {
      const found = /** @type {Progress} */ (await postJson("api/stripboard", { circuit }));
      if (!requests.isCurrent(token)) return;
      progress = found;
      checked = circuit;
    } catch (err) {
      if (!requests.isCurrent(token)) return;
      progress = null;
      checked = null;
      $("board-warnings-body").replaceChildren(h("p", { class: "error" }, [`Couldn't check the board: ${/** @type {Error} */ (err).message}`]));
      return;
    }
    draw();
    fillPanes();
  }

  function fillPanes() {
    if (!progress) return;
    const circuit = app.circuit();
    const rows = trayRows(progress, circuit);
    $("board-tray-count").textContent = rows.length ? `· ${rows.length}` : "";
    $("board-tray-body").replaceChildren(rows.length
      ? h("ul", { class: "board-list" }, rows.map((r) => h("li", { "data-ref": r.ref }, [
        h("span", { class: "ref" }, [r.ref]), " ", h("span", { class: "value" }, [r.value]), " ", h("span", { class: "shape" }, [r.shape]),
      ])))
      : h("p", { class: "empty" }, ["Every part is on the board."]));
    $("board-nets-count").textContent = progress.nets.length ? `· ${progress.nets_done}/${progress.nets.length}` : "";
    $("board-nets-body").replaceChildren(
      h("p", { class: "board-progress" }, [netsLine(progress)]),
      h("ul", { class: "board-list" }, progress.nets.map((n) => {
        const row = h("li", { class: `net-${n.state}`, "data-net": n.net }, [h("span", { class: "net" }, [n.net]), " ", h("span", { class: "state" }, [netWords(n)])]);
        row.addEventListener("click", () => app.select({ kind: "net", id: n.net }));
        return row;
      })),
    );
    const said = [...progress.faults, ...progress.stale.map((ref) => `${ref} is no longer in the circuit.`), ...progress.warnings];
    $("board-warnings-count").textContent = said.length ? `· ${said.length}` : "";
    $("board-warnings-body").replaceChildren(said.length
      ? h("ul", { class: "board-list warnings" }, said.map((text, i) => h("li", { class: i < progress.faults.length + progress.stale.length ? "fault" : "warning" }, [text])))
      : h("p", { class: "empty" }, [progress.done ? "The board matches the circuit." : "Nothing wrong so far."]));
    if (!$("board-settings-body").childElementCount) $("board-settings-body").append(h("p", { class: "empty" }, ["The editor's settings come with placing parts."]));
  }

  /** Light the selection on the board. @param {Selection | null} selection */
  function light(selection) {
    if (!selection || selection.resting || !progress) return canvas.light([]);
    const fps = progress.footprints;
    const onBoard = (/** @type {string[]} */ refs) => [...new Set(refs.map((r) => boardRefOf(fps, r)).filter((r) => r !== null))];
    if (selection.kind === "part") return canvas.light(onBoard([selection.id]));
    if (selection.kind === "items") return canvas.light(onBoard(selection.items?.parts ?? []));
    canvas.light(partsOnNet(progress, selection.id));
  }

  return {
    /** Whether the Board view is showing. */
    active: () => active,
    /** The line under the canvas in the Board view. */
    hint: HINT,
    show,
    /** The circuit changed or was opened: drawn again, re-checked. */
    changed() {
      if (!active) return;
      drawSheet();
      draw();
      void update();
    },
    /** The selection changed. @param {Selection | null} selection */
    select(selection) {
      if (!active) return;
      sheet.select(selection);
      light(selection);
    },
    /** A circuit opened: the Schematic view again, the next board fitted when shown. */
    opened() {
      fitted = false;
      progress = null;
      checked = null;
      show(false);
    },
    zoomBy: (/** @type {number} */ factor) => canvas.zoomBy(factor),
    fit: () => canvas.fit(),
    /** View → Reset pane order, for the board's panes too. */
    resetPanes: () => panes?.reset(),
  };
}
