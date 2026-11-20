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
 *
 * Editing (D-374): a part is carried from the tray (dragged, or clicked then the board
 * clicked) or picked up off the board, turned, flipped, stood up or lengthened on the way
 * (keys, or a placed part's right-click menu), and put down; the Cuts and Links tools cut
 * and mend strips, lay and lift links. Each edit goes to the server
 * (`POST /api/stripboard/edit`), which refuses it in a sentence or answers the new board,
 * applied as one step of the board's own history (`editBoard`, D-370).
 */

import { postJson } from "../api.js";
import { openMenu } from "../menus.js";
import { h } from "../panels.js";
import { reorderable } from "../panes.js";
import { Schematic } from "../schematic/render.js";
import { latestOnly } from "../state.js";
import { remember, remembered } from "../storage.js";
import { boardCanvas } from "./canvas.js";
import { BOARD_SETTINGS, boardRefOf, drawnBoard, firstPose, holeName, legsAt, legsData, lineChanges, linkFrom, middleOf, moveWords, netWords, netsLine, offBoardRows, partsOnNet, posed, poseOf, readBoard, readSettings, sizeLine, trayGroups, trayRows } from "./board-logic.js";

/**
 * @typedef {import("../schematic/render.js").Selection} Selection
 * @typedef {import("./board-logic.js").Progress} Progress
 * @typedef {import("./board-logic.js").Hole} Hole
 * @typedef {import("./board-logic.js").Pose} Pose
 * @typedef {"turn" | "flip" | "stand" | "longer" | "shorter"} PoseMove
 * @typedef {{ref: string, pose: Pose, grab: Hole, from: "tray" | "board"}} Carried
 *   a part on its way: `grab` the pointer's hole from the part's middle
 * @typedef {{
 *   circuit: () => any,
 *   view: () => any,
 *   positions: () => Record<string, number>,
 *   selection: () => Selection | null,
 *   select: (selection: Selection | null) => void,
 *   resting: () => Selection | null,
 *   shown: (board: boolean) => void,
 *   editBoard: (stripboard: any, label: string) => void,
 *   refuse: (message: string) => void,
 * }} BoardApp
 *   `resting`: what's selected when the empty canvas is clicked (the root's own choice);
 *   `shown`: told when the view changes, so the root sets its hint (`hint`) and buttons;
 *   `editBoard`: the circuit with this board (its plain form; null: none, Settings' *Remove
 *   board*, D-370), one undo step
 */

const BUTTON_TITLE = "Lay out a stripboard for this circuit";
const SETTINGS_KEY = "solum.board"; // the editor's settings, kept by the server (D-311)
const HINT = "Drag a part from the tray onto the board: Space turns it, F flips it, S stands it up. C makes cuts, K lays links; right-click a part for more.";
const POSE_MOVES = /** @type {PoseMove[]} */ (["turn", "flip", "stand", "longer", "shorter"]);
const MOVE_KEYS = { turn: "Space", flip: "F", stand: "S", longer: "+", shorter: "−" };

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

  const tools = $("board-tools");
  /** @type {"parts" | "cuts" | "links"} */
  let tool = "parts";
  /** @type {Carried | null} */
  let carry = null;
  /** @type {Hole | null} the hole the pointer was last over */
  let aim = null;
  /** @type {{ref: string, hole: Hole} | null} a placed part pressed, not yet dragged */
  let pressedPart = null;
  /** @type {Hole | null} where a link being laid starts */
  let linkStart = null;
  /** @type {{x: number, y: number} | null} a press on a tray row */
  let trayPress = null;

  const canvas = boardCanvas(svg, {
    onClick: (spot) => {
      if (tool === "cuts") return void toggleCut(spot.hole);
      if (spot.ref) selectPart(spot.ref);
      else app.select(app.resting());
    },
    onLine: (axis, line, x, y) => openMenu(x, y, lineChanges(axis, line).map((c) => ({ label: c.label, run: () => void resize(c.change, c.label, c.axis, c.at) }))),
    onPress: (spot) => {
      if (carry) return true; // picked up from the tray: this press puts it down
      if (tool === "links") {
        linkStart = spot.link ? null : spot.hole;
        if (spot.link) void boardEdit({ kind: "unlink", holes: spot.link }, `Lift the link ${spot.link.map(holeName).join("–")}`);
        return true;
      }
      if (tool !== "parts" || !spot.ref || !placedLegs(spot.ref)) return false;
      pressedPart = { ref: spot.ref, hole: spot.hole };
      return true;
    },
    onDrag: (hole) => {
      aim = hole;
      if (linkStart) return canvas.ghost({ link: linkFrom(linkStart, hole) ?? [linkStart, linkStart] });
      if (pressedPart && !carry) pickUp(pressedPart.ref, pressedPart.hole);
      showCarried();
    },
    onRelease: (hole, moved) => {
      const pressed = pressedPart;
      pressedPart = null;
      if (linkStart) {
        const link = linkFrom(linkStart, hole);
        linkStart = null;
        canvas.ghost(null);
        if (link) void boardEdit({ kind: "link", holes: link }, "Lay a link");
        return;
      }
      if (carry) return void putDown(hole);
      if (pressed && !moved) selectPart(pressed.ref);
    },
    onHover: (hole) => {
      aim = hole;
      if (carry) return showCarried();
      canvas.ghost(hole && tool !== "parts" ? { hole } : null);
    },
    onMenu: (ref, x, y) => partMenu(ref, x, y),
  });
  trimButton.addEventListener("click", () => void resize("trim", "Trim the board"));
  for (const b of tools.querySelectorAll("button")) b.addEventListener("click", () => {
    setTool(/** @type {any} */ (b.getAttribute("data-tool")));
    b.blur(); // the board's keys act again
  });
  // a tray row dragged and let go: on the board it's put down, elsewhere dropped; not moved, it stays picked up
  window.addEventListener("pointerup", (e) => {
    if (!trayPress || !carry) return void (trayPress = null);
    const moved = Math.hypot(e.clientX - trayPress.x, e.clientY - trayPress.y) > 3;
    trayPress = null;
    if (!moved) return;
    const over = /** @type {Element | null} */ (e.target)?.closest?.("#board");
    if (over) void putDown(canvas.holeAt(e.clientX, e.clientY));
    else drop();
  });

  /** @param {"parts" | "cuts" | "links"} which */
  function setTool(which) {
    tool = which;
    drop();
    for (const b of tools.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.getAttribute("data-tool") === which));
    svg.dataset.tool = which;
    canvas.ghost(null);
  }

  /** A placed part's legs, or null when it isn't on the board. @param {string} ref */
  function placedLegs(ref) {
    return readBoard(app.circuit()?.stripboard).parts.find((p) => p.ref === ref) ?? null;
  }

  /** Pick a placed part up off the board, held where it was pressed. @param {string} ref @param {Hole} hole */
  function pickUp(ref, hole) {
    const fp = progress?.footprints[ref];
    const placed = placedLegs(ref);
    if (!fp || !placed) return;
    const middle = middleOf(placed.legs);
    carry = { ref, from: "board", pose: poseOf(fp, placed.legs, placed.standing) ?? firstPose(fp), grab: [hole[0] - middle[0], hole[1] - middle[1]] };
    svg.classList.add("carrying");
  }

  /** Pick a part up from the tray, held by its middle. @param {string} ref */
  function pickFromTray(ref) {
    const fp = progress?.footprints[ref];
    if (!fp) return;
    setTool("parts");
    carry = { ref, from: "tray", pose: firstPose(fp), grab: [0, 0] };
    svg.classList.add("carrying");
    showCarried();
  }

  /** Where the carried part's legs would go with the pointer at `hole`. @param {Carried} c @param {Hole} hole */
  function carriedLegs(c, hole) {
    const fp = /** @type {import("./board-logic.js").Footprint} */ (progress?.footprints[c.ref]);
    return legsAt(fp, c.pose, [hole[0] - c.grab[0], hole[1] - c.grab[1]]);
  }

  function showCarried() {
    const fp = carry && progress?.footprints[carry.ref];
    if (!carry || !fp || !aim) return canvas.ghost(null);
    canvas.ghost({ part: { fp, legs: carriedLegs(carry, aim), standing: carry.pose.standing } });
  }

  /** Put the carried part down with the pointer at `hole`. @param {Hole} hole */
  async function putDown(hole) {
    const c = carry;
    drop();
    if (!c) return;
    const legs = carriedLegs(c, hole);
    const was = placedLegs(c.ref);
    if (was && was.standing === c.pose.standing && legs.every(([leg, h]) => was.legs.some(([l, w]) => l === leg && w[0] === h[0] && w[1] === h[1]))) return;
    await boardEdit({ kind: "place", ref: c.ref, legs: legsData(legs), standing: c.pose.standing }, `${c.from === "tray" ? "Place" : "Move"} ${c.ref}`);
  }

  /** Nothing carried any more. */
  function drop() {
    carry = null;
    linkStart = null;
    svg.classList.remove("carrying");
    canvas.ghost(null);
  }

  /** The board part selected, when it's one placed part. */
  function selectedPlaced() {
    const selection = app.selection();
    if (!selection || selection.resting || !progress) return null;
    const refs = selection.kind === "part" ? [selection.id] : selection.kind === "items" ? (selection.items?.parts ?? []) : [];
    const on = [...new Set(refs.map((r) => boardRefOf(progress?.footprints ?? {}, r)))];
    return on.length === 1 && on[0] && placedLegs(on[0]) ? on[0] : null;
  }

  /**
   * Turn, flip, stand or lengthen the part carried, or else the selected placed part
   * about its middle (one edit). False when there's no part to do it to.
   * @param {PoseMove} move
   */
  function repose(move, ref = selectedPlaced()) {
    if (carry) {
      const fp = progress?.footprints[carry.ref];
      const next = fp && posed(fp, carry.pose, move);
      if (next) carry = { ...carry, pose: next };
      showCarried();
      return true;
    }
    const fp = ref ? progress?.footprints[ref] : null;
    const placed = ref ? placedLegs(ref) : null;
    if (!ref || !fp || !placed) return false;
    const pose = poseOf(fp, placed.legs, placed.standing) ?? firstPose(fp);
    const next = posed(fp, pose, move);
    if (!next) return true;
    const legs = legsAt(fp, next, middleOf(placed.legs));
    void boardEdit({ kind: "place", ref, legs: legsData(legs), standing: next.standing }, `${moveWords(move, pose)} ${ref}`);
    return true;
  }

  /** A placed part's menu: each pose move it allows, and back to the tray. @param {string} ref @param {number} x @param {number} y */
  function partMenu(ref, x, y) {
    const fp = progress?.footprints[ref];
    const placed = placedLegs(ref);
    if (!fp || !placed) return;
    selectPart(ref);
    const pose = poseOf(fp, placed.legs, placed.standing) ?? firstPose(fp);
    const items = POSE_MOVES.filter((move) => posed(fp, pose, move)).map((move) => ({ label: `${moveWords(move, pose)}  (${MOVE_KEYS[move]})`, run: () => void repose(move, ref) }));
    openMenu(x, y, [...items, { label: "Back to the tray  (Del)", run: () => void boardEdit({ kind: "remove", ref }, `${ref} back to the tray`) }]);
  }

  /** Cut the strip at a hole, or mend the cut there. @param {Hole} hole */
  function toggleCut(hole) {
    const cut = readBoard(app.circuit()?.stripboard).cuts.some((c) => c[0] === hole[0] && c[1] === hole[1]);
    return boardEdit({ kind: cut ? "uncut" : "cut", holes: [hole] }, `${cut ? "Mend the cut" : "Cut"} at ${holeName(hole)}`);
  }

  /**
   * One hand edit of the board (D-374), made by the server with the editor's settings and
   * applied as one undo step; refused, its sentence shown.
   * @param {Record<string, unknown>} change @param {string} label
   */
  async function boardEdit(change, label) {
    try {
      const { stripboard, shift } = await postJson("api/stripboard/edit", { circuit: app.circuit(), ...change, grow: settings.grow, shorts: settings.shorts });
      if (shift[0] || shift[1]) canvas.shift(shift);
      app.editBoard(stripboard, label);
    } catch (err) {
      app.refuse(/** @type {Error} */ (err).message);
    }
  }

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
      app.refuse(/** @type {Error} */ (err).message);
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

  button.addEventListener("click", (e) => {
    show(!active);
    if (e.detail) button.blur(); // clicked: Space then turns a part, not the view back
  });
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
    tools.hidden = !board;
    if (!board) setTool("parts");
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
    canvas.draw(drawn, progress?.footprints ?? {}, circuit, { fit: !fitted, values: settings.values, rulers: started, fixed: !settings.grow, shorted: checked === circuit ? progress?.shorted ?? [] : [] });
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
      if (r.mark && progress?.footprints[r.ref]) {
        item.classList.add("carriable");
        item.title = "Drag onto the board, or click and then click the board";
        item.addEventListener("pointerdown", (e) => {
          if (e.button !== 0) return;
          e.preventDefault(); // no text selection while dragging (and no focus move: blur by hand)
          /** @type {HTMLElement | null} */ (document.activeElement)?.blur?.();
          trayPress = { x: e.clientX, y: e.clientY };
          pickFromTray(r.ref);
        });
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
    /**
     * A Board view key (`boardActionFor`); false when it does nothing here.
     * @param {string} action
     */
    key(action) {
      if (action === "cancel") {
        if (carry || linkStart) drop();
        else if (tool !== "parts") setTool("parts");
        else return false;
        return true;
      }
      if (action === "parts" || action === "cuts" || action === "links") return setTool(action), true;
      if (action === "remove") {
        const ref = carry?.from === "board" ? carry.ref : selectedPlaced();
        if (!ref) return false;
        drop();
        void boardEdit({ kind: "remove", ref }, `${ref} back to the tray`);
        return true;
      }
      return POSE_MOVES.includes(/** @type {PoseMove} */ (action)) && repose(/** @type {PoseMove} */ (action));
    },
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
      drop();
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
