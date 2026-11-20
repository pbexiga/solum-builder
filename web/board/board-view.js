/**
 * The Board view (D-368): *Schematic* / *Board*, two views of the open circuit on the one
 * canvas, switched by the header's Board button (D-370: quiet with no board, marked once
 * one is started, pressed in the Board view). In the Board view the canvas shows the
 * stripboard (`canvas.js`), the Tray takes the palette's place on the left (D-371), and
 * the result panes' column holds the board's own panes instead, reorderable and
 * remembered under their own key (`solum.boardPanes`): Warnings, Schematic (the drawing,
 * smaller), Nets, Settings. Back in the Schematic view the result panes are as they were.
 * Selecting a part or a net on either drawing lights it on both. The board's state comes
 * from the server's progress check (`POST /api/stripboard`) after every change.
 */

import { postJson } from "../api.js";
import { openMenu } from "../menus.js";
import { h } from "../panels.js";
import { reorderable } from "../panes.js";
import { Schematic } from "../schematic/render.js";
import { latestOnly } from "../state.js";
import { remember, remembered } from "../storage.js";
import { boardCanvas } from "./canvas.js";
import { BOARD_SETTINGS, boardRefOf, drawnBoard, lineChanges, netWords, netsLine, offBoardRows, partsOnNet, readBoard, readSettings, sizeLine, trayGroups, trayRows } from "./board-logic.js";

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
 *   editBoard: (stripboard: any, label: string) => void,
 *   showError: (message: string) => void,
 * }} BoardApp
 *   `resting`: what's selected when the empty canvas is clicked (the root's own choice);
 *   `shown`: told when the view changes, so the root sets its hint (`hint`) and buttons;
 *   `editBoard`: the circuit with this board (its plain form; null: none, Settings' *Remove
 *   board*, D-370), one undo step
 */

const BUTTON_TITLE = "Lay out a stripboard for this circuit";
const SETTINGS_KEY = "solum.board"; // the editor's settings, kept by the server (D-311)
const HINT = "The board, parts side. Click a part to select it on both drawings. Drag the board to pan, scroll to zoom.";

/**
 * @param {HTMLElement} host the canvas's body @param {BoardApp} app
 */
export function boardView(host, app) {
  const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));
  const svg = /** @type {SVGSVGElement} */ (/** @type {unknown} */ ($("board")));
  const column = $("board-panels");
  const tray = $("board-tray");
  const results = /** @type {HTMLElement} */ (document.querySelector(".panels"));
  const sizeNote = $("board-size");
  const sizeText = $("board-size-text");
  const trimButton = /** @type {HTMLButtonElement} */ ($("board-trim"));
  const button = $("board-button");
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
  let settings = readSettings(remembered(SETTINGS_KEY));

  const canvas = boardCanvas(svg, {
    onPart: (ref) => selectPart(ref),
    onEmpty: () => app.select(app.resting()),
    onLine: (axis, line, x, y) => openMenu(x, y, lineChanges(axis, line).map((c) => ({ label: c.label, run: () => void resize(c.change, c.label, c.axis, c.at) }))),
  });
  trimButton.addEventListener("click", () => void resize("trim", "Trim the board"));

  /**
   * A size change from the server (D-372), applied as an edit; one that can't be made
   * says why.
   * @param {"insert" | "remove" | "trim"} change @param {string} label
   * @param {"column" | "strip"} [axis] @param {number} [at]
   */
  async function resize(change, label, axis = "column", at = 0) {
    try {
      const { stripboard } = await postJson("api/stripboard/size", { circuit: app.circuit(), change, axis, at });
      app.editBoard(stripboard, label);
    } catch (err) {
      app.showError(/** @type {Error} */ (err).message);
    }
  }
  /** Select a board part (a chip: its units) or a circuit part on both drawings. @param {string} ref */
  function selectPart(ref) {
    const refs = progress?.footprints[ref]?.refs ?? [ref];
    app.select(refs.length === 1
      ? { kind: "part", id: refs[0] }
      : { kind: "items", id: "", items: { parts: refs, wires: [], labels: [] } });
  }
  const sheet = new Schematic(/** @type {SVGSVGElement} */ (/** @type {unknown} */ ($("board-sheet"))), {
    onNet: (net) => app.select({ kind: "net", id: net }),
    onPart: (ref) => app.select({ kind: "part", id: ref }),
    onEmpty: () => app.select(app.resting()),
  });

  button.addEventListener("click", () => show(!active));
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
    tray.hidden = !board;
    sizeNote.hidden = !board;
    button.setAttribute("aria-pressed", String(board));
    button.title = board ? "Back to the schematic" : BUTTON_TITLE;
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
    const started = Boolean(board.columns);
    const drawn = drawnBoard(board, progress?.start_size);
    canvas.draw(drawn, progress?.footprints ?? {}, circuit, { fit: !fitted, values: settings.values, rulers: started, fixed: !settings.grow });
    fitted ||= Boolean(drawn.columns); // an empty board's size comes with the first check
    sizeText.textContent = sizeLine(board);
    trimButton.hidden = !started;
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
    const inCircuit = new Set((circuit?.parts ?? []).map((/** @type {any} */ p) => p.ref));
    const row = (/** @type {import("./board-logic.js").TrayRow} */ r) => {
      const item = h("li", { "data-ref": r.ref }, [
        ...(r.mark ? [h("span", { class: `fp fp-${r.mark}`, "aria-hidden": "true" })] : []),
        h("span", { class: "ref" }, [r.ref]), " ", ...(r.value ? [h("span", { class: "value" }, [r.value]), " "] : []), h("span", { class: "shape" }, [r.shape]),
      ]);
      const pick = r.select && (progress?.footprints[r.select] || inCircuit.has(r.select)) ? r.select : null;
      if (pick) {
        item.classList.add("pickable");
        item.addEventListener("click", () => selectPart(pick));
      }
      return item;
    };
    const groups = trayGroups(trayRows(progress, circuit));
    const on = groups.reduce((n, g) => n + g.rows.length, 0);
    const off = offBoardRows(progress);
    const unplaceable = progress.unplaceable;
    const left = on + off.length + unplaceable.length;
    /** @param {string} title @param {number} count @param {HTMLElement[]} body */
    const section = (title, count, body) => (count ? [h("h3", {}, [title, " ", h("span", { class: "count" }, [String(count)])]), ...body] : []);
    $("board-tray-count").textContent = left ? `· ${left} left` : "";
    $("board-tray-body").replaceChildren(
      ...(on || unplaceable.length
        ? section("On the board", on, groups.flatMap((g) => [h("p", { class: "board-subhead" }, [g.title]), h("ul", { class: "board-list" }, g.rows.map(row))]))
        : [h("p", { class: "empty done" }, ["✓ Every part is on the board."])]),
      ...section("Off the board", off.length, [h("ul", { class: "board-list off-board" }, off.map(row))]),
      ...section("Can't be placed yet", unplaceable.length, [h("ul", { class: "board-list unplaceable" }, unplaceable.map((text) => h("li", {}, [text])))]),
    );
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
    fillSettings();
  }

  /** Settings: the editor's settings, remembered per viewer; *Remove board* at the bottom once one is started. */
  function fillSettings() {
    const boxes = BOARD_SETTINGS.map((setting) => {
      const box = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", "data-setting": setting.key }));
      box.checked = settings[setting.key];
      box.disabled = !setting.acts;
      box.addEventListener("change", () => {
        settings = { ...settings, [setting.key]: box.checked };
        remember(SETTINGS_KEY, settings);
        draw();
      });
      const label = h("label", { class: setting.acts ? "board-setting" : "board-setting later" }, [box, " ", setting.label]);
      label.title = setting.acts ? setting.title : `${setting.title}. Comes with placing parts.`;
      return label;
    });
    const remove = h("button", { type: "button", id: "remove-board", class: "remove-board" }, ["Remove board"]);
    remove.title = "Take every part, cut, link and wire off the board (Undo brings them back)";
    remove.addEventListener("click", () => app.editBoard(null, "Remove board"));
    $("board-settings-body").replaceChildren(...boxes, ...(app.circuit()?.stripboard ? [remove] : []));
  }

  /** The button marked once the open circuit has a board. */
  function mark() {
    button.classList.toggle("marked", Boolean(app.circuit()?.stripboard));
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
      mark();
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
      mark();
    },
    zoomBy: (/** @type {number} */ factor) => canvas.zoomBy(factor),
    fit: () => canvas.fit(),
    /** View → Reset pane order, for the board's panes too. */
    resetPanes: () => panes?.reset(),
  };
}
