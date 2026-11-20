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
 *
 * Off the board (D-375): an off-board part is dragged out of the tray and put beside the
 * board, or moved by its body; a wire is drawn by dragging from a lug to a hole, to
 * another lug, or let go away from the board (loose); either end of a wire is dragged to
 * move it; a wire's or an off-board part's right-click menu takes it off.
 *
 * Guidance (D-377, from the progress check's `guidance`): the holes where a carried part's
 * legs would join their nets are marked; the ratsnest shows what each net still has to
 * join, a selected or carried part's lit; the cuts and links the legs call for are drawn
 * faded, a click makes one, *Make the suggested …* makes them all; the needs card names a
 * carried or selected part's legs and what each must reach (`needs.js`); with *What to
 * place next* on, the tray says which part is next and why.
 */

import { postJson } from "../api.js";
import { openMenu } from "../menus.js";
import { h } from "../panels.js";
import { reorderable } from "../panes.js";
import { Schematic } from "../schematic/render.js";
import { latestOnly } from "../state.js";
import { remember, remembered } from "../storage.js";
import { boardCanvas } from "./canvas.js";
import { needsCard } from "./needs.js";
import { BOARD_SETTINGS, boardRefOf, drawnBoard, firstPose, holeName, isOut, itemRefs, legNeeds, legsAt, legsData, lineChanges, linkFrom, lugPlaces, markedHoles, runAt, middleOf, moveWords, netWords, netsLine, netsOf, offBoardRows, partsOnNet, posed, poseOf, readBoard, readSettings, shownHoles, sizeLine, spotFor, staleLine, suggestionsLine, trayGroups, trayRows, wireLine, wireObstacles, wireRoutes } from "./board-logic.js";

/**
 * @typedef {import("../schematic/render.js").Selection} Selection
 * @typedef {import("./board-logic.js").Progress} Progress
 * @typedef {import("./board-logic.js").Hole} Hole
 * @typedef {import("./board-logic.js").Pose} Pose
 * @typedef {"turn" | "flip" | "stand" | "longer" | "shorter"} PoseMove
 * @typedef {{ref: string, pose: Pose, grab: Hole, from: "tray" | "board"}} Carried
 *   a part on its way: `grab` the pointer's hole from the part's middle
 * @typedef {import("./board-logic.js").OffItem} OffItem
 * @typedef {{item: OffItem, grab: Hole, from: "tray" | "board"}} CarriedItem
 *   an off-board part on its way: `grab` the pointer's hole from its spot
 * @typedef {{lug: string, index: number, end: "new" | "far" | "lug"}} Wiring
 *   a wire being drawn from `lug` (`new`), or wire `index`'s far end or lug end being moved
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
const HINT = "Drag a part from the tray onto the board: Space turns it, F flips it, S stands it up. C makes cuts, K lays links. Drag from a pot's or jack's lug to a hole to wire it, a wire's middle to move it; right-click for more.";
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
  const wireButton = /** @type {HTMLButtonElement} */ ($("board-wire"));
  const acceptButton = /** @type {HTMLButtonElement} */ ($("board-accept"));
  const needs = needsCard($("board-needs"));
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
  /** @type {CarriedItem | null} */
  let carryItem = null;
  /** @type {{ref: string, hole: Hole} | null} an off-board part pressed, not yet dragged */
  let pressedItem = null;
  /** @type {Wiring | null} */
  let wiring = null;
  /** @type {{index: number, run: number, at: number | null} | null} a wire's middle run being dragged (D-380) */
  let bending = null;

  const canvas = boardCanvas(svg, {
    onClick: (spot) => {
      if (spot.suggest) return void acceptOne(spot.suggest);
      if (tool === "cuts") return void toggleCut(spot.hole);
      if (spot.ref) selectPart(spot.ref);
      else app.select(app.resting());
    },
    onLine: (axis, line, x, y) => openMenu(x, y, lineChanges(axis, line).map((c) => ({ label: c.label, run: () => void resize(c.change, c.label, c.axis, c.at) }))),
    onPress: (spot) => {
      if (carry || carryItem) return true; // picked up from the tray: this press puts it down
      if (spot.suggest) return false; // a click makes it
      if (tool === "parts" && spot.wire?.end === "run") {
        bending = { index: spot.wire.index, run: spot.wire.run, at: null };
        return true;
      }
      if (tool === "parts" && spot.wire) {
        const w = boardNow().wires[spot.wire.index];
        if (w) wiring = { lug: w.lug, index: spot.wire.index, end: spot.wire.end };
        return Boolean(w);
      }
      if (tool === "parts" && spot.lug) return (wiring = { lug: spot.lug, index: -1, end: "new" }), true;
      if (tool === "parts" && spot.item) return (pressedItem = { ref: spot.item, hole: spot.hole }), true;
      if (tool === "links") {
        linkStart = spot.link ? null : spot.hole;
        if (spot.link) void boardEdit({ kind: "unlink", holes: spot.link }, `Lift the link ${spot.link.map(holeName).join("–")}`);
        return true;
      }
      if (tool !== "parts" || !spot.ref || !placedLegs(spot.ref)) return false;
      pressedPart = { ref: spot.ref, hole: spot.hole };
      return true;
    },
    onDrag: (hole, point) => {
      aim = hole;
      if (bending) return showBending(point);
      if (wiring) return showWiring(point);
      if (pressedItem && !carryItem) pickItem(pressedItem.ref, pressedItem.hole);
      if (carryItem) return showCarriedItem();
      if (linkStart) return canvas.ghost({ link: linkFrom(linkStart, hole) ?? [linkStart, linkStart] });
      if (pressedPart && !carry) pickUp(pressedPart.ref, pressedPart.hole);
      showCarried();
    },
    onRelease: (hole, moved, spot) => {
      const pressed = pressedPart;
      pressedPart = null;
      const item = pressedItem;
      pressedItem = null;
      if (bending) return void endBending(moved);
      if (wiring) return void endWiring(hole, moved, spot);
      if (carryItem) return void putItem(hole);
      if (item && !moved) return selectItem(item.ref);
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
      if (carryItem) return showCarriedItem();
      canvas.ghost(hole && tool !== "parts" ? { hole } : null);
    },
    onMenu: (spot, x, y) => {
      if (spot.wire) return wireMenu(spot.wire.index, x, y), true;
      if (spot.item) return itemMenu(spot.item, x, y), true;
      if (spot.ref) return partMenu(spot.ref, x, y), true;
      return false;
    },
  });
  trimButton.addEventListener("click", () => void resize("trim", "Trim the board"));
  wireButton.addEventListener("click", () => void wireForMe());
  acceptButton.addEventListener("click", () => void boardEdit({ kind: "suggested" }, acceptButton.textContent ?? "Make the suggested cuts and links"));
  const flipButton = $("board-flip");
  flipButton.addEventListener("click", (e) => {
    canvas.flip((copper) => flipButton.setAttribute("aria-pressed", String(copper)));
    if (e.detail) flipButton.blur(); // clicked: the board's keys act again
  });
  for (const b of tools.querySelectorAll("button[data-tool]")) b.addEventListener("click", () => {
    setTool(/** @type {any} */ (b.getAttribute("data-tool")));
    b.blur(); // the board's keys act again
  });
  // a tray row dragged and let go: on the board it's put down, elsewhere dropped; not moved, it stays picked up
  window.addEventListener("pointerup", (e) => {
    if (!trayPress || !(carry || carryItem)) return void (trayPress = null);
    const moved = Math.hypot(e.clientX - trayPress.x, e.clientY - trayPress.y) > 3;
    trayPress = null;
    if (!moved) return;
    const over = /** @type {Element | null} */ (e.target)?.closest?.("#board");
    const hole = canvas.holeAt(e.clientX, e.clientY);
    if (!over) drop();
    else if (carryItem) void putItem(hole);
    else void putDown(hole);
  });

  /** @param {"parts" | "cuts" | "links"} which */
  function setTool(which) {
    tool = which;
    drop();
    for (const b of tools.querySelectorAll("button[data-tool]")) b.setAttribute("aria-pressed", String(b.getAttribute("data-tool") === which));
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
    focus();
  }

  /** Pick a part up from the tray, held by its middle. @param {string} ref */
  function pickFromTray(ref) {
    const fp = progress?.footprints[ref];
    if (!fp) return;
    setTool("parts");
    carry = { ref, from: "tray", pose: firstPose(fp), grab: [0, 0] };
    svg.classList.add("carrying");
    showCarried();
    focus();
  }

  /** Where the carried part's legs would go with the pointer at `hole`. @param {Carried} c @param {Hole} hole */
  function carriedLegs(c, hole) {
    const fp = /** @type {import("./board-logic.js").Footprint} */ (progress?.footprints[c.ref]);
    return legsAt(fp, c.pose, [hole[0] - c.grab[0], hole[1] - c.grab[1]]);
  }

  function showCarried() {
    const fp = carry && progress?.footprints[carry.ref];
    const guide = guidanceNow();
    const marks = carry && progress && guide ? markedHoles(progress, guide, carry.ref) : [];
    if (!carry || !fp || !aim) return canvas.ghost(marks.length ? { marks } : null);
    canvas.ghost({ marks, part: { fp, legs: carriedLegs(carry, aim), standing: carry.pose.standing } });
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

  /** The board as the open circuit holds it. */
  function boardNow() {
    return readBoard(app.circuit()?.stripboard);
  }

  /** An off-board part by its ref. @param {string} ref */
  const itemOf = (ref) => progress?.items.find((i) => i.ref === ref) ?? null;

  /** Where each drawn lug is, for the board as it is. */
  function lugsNow() {
    return progress ? lugPlaces(progress, boardNow()) : {};
  }

  /** An off-board lug in words: "VR1 lug 2", "IN T", "Power V+". @param {string} end */
  function lugWords(end) {
    const item = progress?.items.find((i) => i.lugs.some((l) => l.end === end));
    const lug = item?.lugs.find((l) => l.end === end);
    if (!item || !lug) return end;
    const name = item.kind === "power" ? "Power" : item.ref;
    return /^\d/.test(lug.label) ? `${name} lug ${lug.label}` : `${name} ${lug.label}`;
  }

  /** Pick an off-board part up off the canvas, held where it was pressed. @param {string} ref @param {Hole} hole */
  function pickItem(ref, hole) {
    const item = itemOf(ref);
    if (!item || !progress) return;
    const at = boardNow().spots[ref] ?? progress.spots[ref];
    carryItem = { item, grab: [hole[0] - at[0], hole[1] - at[1]], from: "board" };
    svg.classList.add("carrying");
  }

  /** Pick an off-board part up from the tray, held by its middle. @param {string} ref */
  function pickItemFromTray(ref) {
    const item = itemOf(ref);
    if (!item) return;
    setTool("parts");
    const at = spotFor(item, [0, 0]);
    carryItem = { item, grab: [-at[0], -at[1]], from: "tray" };
    svg.classList.add("carrying");
    showCarriedItem();
  }

  function showCarriedItem() {
    if (!carryItem || !aim) return canvas.ghost(null);
    canvas.ghost({ item: { item: carryItem.item, at: [aim[0] - carryItem.grab[0], aim[1] - carryItem.grab[1]] } });
  }

  /** Put the carried off-board part down with the pointer at `hole`. @param {Hole} hole */
  async function putItem(hole) {
    const c = carryItem;
    drop();
    if (!c) return;
    const at = [hole[0] - c.grab[0], hole[1] - c.grab[1]];
    const was = boardNow().spots[c.item.ref];
    if (was && was[0] === at[0] && was[1] === at[1]) return;
    await boardEdit({ kind: "spot", ref: c.item.ref, holes: [at] }, `${c.from === "tray" ? "Put" : "Move"} ${c.item.ref} beside the board`);
  }

  /** Select an off-board part's circuit parts on both drawings. @param {string} ref */
  function selectItem(ref) {
    const item = itemOf(ref);
    const refs = item ? itemRefs(item) : [];
    if (!refs.length) return;
    app.select(refs.length === 1 ? { kind: "part", id: refs[0] } : { kind: "items", id: "", items: { parts: refs, wires: [], labels: [] } });
  }

  /**
   * Where a wire's end at the pointer would land: another lug, a hole on the board or in
   * its margin, else nowhere (loose).
   * @param {import("./canvas.js").Spot} spot @param {Hole} hole @param {string} from the wire's lug
   * @returns {{holes?: Hole[], to?: string}}
   */
  function landing(spot, hole, from) {
    if (spot.lug && spot.lug !== from) return { to: spot.lug };
    if (spot.lug || spot.item) return {};
    const { c0, s0, c1, s1 } = shownHoles(drawnBoard(boardNow(), progress?.start_size));
    const inside = hole[0] >= c0 && hole[0] <= c1 && hole[1] >= s0 && hole[1] <= s1;
    return inside ? { holes: [hole] } : {};
  }

  /** The fixed end of the wire being drawn or moved, in board units. @param {Wiring} w */
  function anchorOf(w) {
    const lugs = lugsNow();
    if (w.end !== "lug") return lugs[w.lug] ? [lugs[w.lug].x, lugs[w.lug].y] : null;
    const line = wireLine(boardNow().wires[w.index], lugs);
    return line ? [line.x2, line.y2] : null;
  }

  /** The wire on its way, from its fixed end to the pointer. @param {[number, number]} point */
  function showWiring(point) {
    const from = wiring && anchorOf(wiring);
    if (!from) return canvas.ghost(null);
    canvas.ghost({ wire: { x1: from[0], y1: from[1], x2: point[0], y2: point[1] } });
  }

  /**
   * A wire drawn or an end let go: a new wire from its lug, a far end moved, or a lug end
   * moved to another lug. Not moved: a lug's click selects its part.
   * @param {Hole} hole @param {boolean} moved @param {import("./canvas.js").Spot} spot
   */
  async function endWiring(hole, moved, spot) {
    const w = wiring;
    wiring = null;
    canvas.ghost(null);
    if (!w) return;
    if (!moved) {
      if (w.end === "new") {
        const item = progress?.items.find((i) => i.lugs.some((l) => l.end === w.lug));
        if (item) selectItem(item.ref);
      }
      return;
    }
    if (w.end === "new") {
      const to = landing(spot, hole, w.lug);
      return boardEdit({ kind: "wire", ref: w.lug, ...to }, `Wire ${lugWords(w.lug)}`);
    }
    const wire = boardNow().wires[w.index];
    if (!wire) return;
    if (w.end === "far") {
      const to = landing(spot, hole, wire.lug);
      return boardEdit({ kind: "rewire", index: w.index, ref: wire.lug, ...to }, `Move the wire from ${lugWords(wire.lug)}`);
    }
    if (!spot.lug || spot.lug === wire.lug) return; // a wire starts at a lug
    const far = wire.hole ? { holes: [wire.hole] } : wire.to ? { to: wire.to } : {};
    await boardEdit({ kind: "rewire", index: w.index, ref: spot.lug, ...far }, `Move a wire to ${lugWords(spot.lug)}`);
  }

  /**
   * The wires' routes as drawn, with wire `index`'s runs as `runs` when given (D-380).
   * @param {number} [index] @param {Array<[number, number]>} [runs]
   */
  function routes(index = -1, runs = []) {
    const { wires, items } = offBoard();
    const lines = wires.map((w) => (w.index === index && w.line ? { ...w.line, runs } : w.line));
    const all = wireRoutes(lines, boardNow(), wireObstacles(boardNow(), progress?.footprints ?? {}, items));
    return { all, at: wires.findIndex((w) => w.index === index) };
  }

  /** Wire `index`'s run moved with the pointer, shown faint. @param {[number, number]} point */
  function showBending(point) {
    if (!bending) return;
    const { index, run } = bending;
    const kept = (boardNow().wires[index]?.runs ?? []).filter(([i]) => i !== run);
    const now = routes(index, kept);
    const route = now.all[now.at];
    if (!route || run > route.length - 3) return;
    bending.at = runAt(route, run, point, boardNow());
    const moved = routes(index, [...kept, [run, bending.at]]);
    canvas.ghost({ route: moved.all[moved.at] ?? undefined });
  }

  /** A run let go: kept where it was put, one undo step. @param {boolean} moved */
  async function endBending(moved) {
    const bent = bending;
    bending = null;
    canvas.ghost(null);
    const wire = bent ? boardNow().wires[bent.index] : null;
    if (!bent || !wire || !moved || bent.at === null) return;
    const runs = [...(wire.runs ?? []).filter(([i]) => i !== bent.run), [bent.run, bent.at]];
    await boardEdit({ kind: "route", index: bent.index, runs }, `Move the wire from ${lugWords(wire.lug)}`);
  }

  /** A wire's menu: route it for me again, leave its end loose, or take it off. @param {number} index @param {number} x @param {number} y */
  function wireMenu(index, x, y) {
    const wire = boardNow().wires[index];
    if (!wire) return;
    const words = lugWords(wire.lug);
    openMenu(x, y, [
      ...(wire.runs?.length ? [{ label: "Route it for me", run: () => void boardEdit({ kind: "route", index, runs: [] }, `Route the wire from ${words} again`) }] : []),
      ...(wire.hole || wire.to ? [{ label: "Leave its end loose", run: () => void boardEdit({ kind: "rewire", index, ref: wire.lug }, `Loosen the wire from ${words}`) }] : []),
      { label: "Take the wire off", run: () => void boardEdit({ kind: "unwire", index }, `Take off the wire from ${words}`) },
    ]);
  }

  /** An off-board part's menu: back to the tray, with its wires. @param {string} ref @param {number} x @param {number} y */
  function itemMenu(ref, x, y) {
    selectItem(ref);
    openMenu(x, y, [{ label: "Back to the tray, with its wires", run: () => void boardEdit({ kind: "unspot", ref }, `${ref} back to the tray`) }]);
  }

  /** The off-board parts beside the board and their wires, as the canvas draws them. */
  function offBoard() {
    if (!progress) return { items: [], wires: [] };
    const board = boardNow();
    const lugs = lugPlaces(progress, board);
    const shown = progress.items.filter((i) => isOut(i, board));
    const wires = board.wires.flatMap((wire, index) => {
      const line = wireLine(wire, lugs);
      const far = wire.hole ? holeName(wire.hole) : wire.to ? lugWords(wire.to) : "loose";
      return line ? [{ index, line, title: `${lugWords(wire.lug)} to ${far}: drag either end to move it`, pad: Boolean(wire.hole) }] : [];
    });
    return { items: shown.map((item) => ({ item, at: board.spots[item.ref] ?? progress?.spots[item.ref] ?? /** @type {Hole} */ ([0, 0]) })), wires };
  }

  /** Nothing carried any more. */
  function drop() {
    carry = null;
    carryItem = null;
    pressedItem = null;
    wiring = null;
    bending = null;
    linkStart = null;
    svg.classList.remove("carrying");
    canvas.ghost(null);
    focus();
  }

  /** The guidance for the circuit as it is now (null: not checked yet). */
  function guidanceNow() {
    return progress && checked === app.circuit() ? progress.guidance : null;
  }

  /** The board part the guidance is about: the one carried, else the one selected (placed or not). */
  function focused() {
    if (carry) return carry.ref;
    const selection = app.selection();
    if (!selection || selection.resting || !progress) return null;
    const refs = selection.kind === "part" ? [selection.id] : selection.kind === "items" ? (selection.items?.parts ?? []) : [];
    const on = [...new Set(refs.map((r) => boardRefOf(progress?.footprints ?? {}, r)))];
    return on.length === 1 ? on[0] : null;
  }

  /** The needs card and the lit ratsnest follow the part carried or selected. */
  function focus() {
    const ref = focused();
    if (!ref || !progress) {
      needs.hide();
      return canvas.lightNets(new Set());
    }
    needs.show(ref, legNeeds(progress, ref, lugWords));
    canvas.lightNets(netsOf(progress, ref));
  }

  /** A suggested cut or link clicked: made, one undo step. @param {{kind: "cut" | "link", holes: Hole[]}} s */
  function acceptOne(s) {
    if (s.kind === "cut") return boardEdit({ kind: "cut", holes: s.holes }, `Cut at ${holeName(s.holes[0])}`);
    return boardEdit({ kind: "link", holes: s.holes }, `Lay the link ${s.holes.map(holeName).join("–")}`);
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
  /** *Wire it for me* (D-375): the server's wiring, one undo step; nothing to do says why. */
  async function wireForMe() {
    try {
      const { stripboard } = await postJson("api/stripboard/wire", { circuit: app.circuit() });
      app.editBoard(stripboard, "Wire it for me");
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
    const guide = guidanceNow();
    canvas.draw(drawn, progress?.footprints ?? {}, circuit, {
      fit: !fitted, values: settings.values, rulers: started, fixed: !settings.grow, shorted: checked === circuit ? progress?.shorted ?? [] : [], off: offBoard(), seeThrough: settings.seeThrough,
      guide: guide ? { rats: guide.ratsnest, cuts: guide.cuts, links: guide.links } : undefined,
    });
    fitted ||= Boolean(drawn.columns && progress); // an empty board's size and the off-board parts come with the first check
    sizeText.textContent = sizeLine(board);
    trimButton.hidden = !started;
    wireButton.hidden = !started || !progress || (!progress.wires_to_go.length && !progress.loose && progress.items.every((i) => isOut(i, board)));
    const suggestions = guide ? suggestionsLine(guide) : "";
    acceptButton.textContent = suggestions;
    acceptButton.hidden = !suggestions;
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
      if (r.item) {
        const ref = r.item;
        item.classList.add("carriable");
        item.title = "Drag out beside the board, or click and then click where it goes";
        item.addEventListener("pointerdown", (e) => {
          if (e.button !== 0) return;
          e.preventDefault();
          /** @type {HTMLElement | null} */ (document.activeElement)?.blur?.();
          trayPress = { x: e.clientX, y: e.clientY };
          pickItemFromTray(ref);
        });
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
    const off = offBoardRows(progress, readBoard(circuit?.stripboard));
    const unplaceable = progress.unplaceable;
    const left = on + off.length + unplaceable.length;
    /** @param {string} title @param {number} count @param {HTMLElement[]} body */
    const section = (title, count, body) => (count ? [h("h3", {}, [title, " ", h("span", { class: "count" }, [String(count)])]), ...body] : []);
    $("board-tray-count").textContent = left ? `· ${left} left` : "";
    const next = settings.next ? progress.guidance.next : null;
    $("board-tray-body").replaceChildren(
      ...(next ? [nextNote(next)] : []),
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
    const said = [...progress.faults, ...progress.warnings];
    const stale = staleLine(progress.stale);
    $("board-warnings-count").textContent = said.length + progress.stale.length ? `· ${said.length + progress.stale.length}` : "";
    $("board-warnings-body").replaceChildren(
      ...(stale ? [staleNote(stale)] : []),
      ...(said.length
        ? [h("ul", { class: "board-list warnings" }, said.map((text, i) => h("li", { class: i < progress.faults.length ? "fault" : "warning" }, [text])))]
        : stale ? [] : [h("p", { class: "empty" }, [progress.done ? "The board matches the circuit." : "Nothing wrong so far."])]),
    );
    fillSettings();
    if (next) $("board-tray-body").querySelector(`.board-list li[data-ref="${CSS.escape(next.ref)}"]`)?.classList.add("next");
  }

  /** *What to place next* (D-377): the part and why; a click picks it up. @param {{ref: string, why: string}} next */
  function nextNote(next) {
    const note = h("p", { class: "board-next" }, [next.why]);
    note.title = "Click to pick it up, then click the board where it goes";
    note.addEventListener("click", () => pickFromTray(next.ref));
    return note;
  }

  /**
   * The parts gone from the schematic, said once, with one click to take them all off the
   * board (D-376): placed parts, off-board parts beside it, their wires.
   * @param {string} text
   */
  function staleNote(text) {
    const clear = h("button", { type: "button", class: "clear-stale" }, ["Clear them"]);
    clear.title = "Take them off the board, with their wires (Undo brings them back)";
    clear.addEventListener("click", () => void boardEdit({ kind: "clear" }, "Clear what's gone from the circuit"));
    return h("div", { class: "board-stale" }, [h("span", {}, [text]), " ", clear]);
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
        fillPanes();
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

  /** Light the selection on the board, off-board parts too. @param {Selection | null} selection */
  function light(selection) {
    focus();
    if (!selection || selection.resting || !progress) return canvas.light([]);
    const fps = progress.footprints;
    const items = progress.items;
    const onBoard = (/** @type {string[]} */ refs) => [...new Set(refs.map((r) => boardRefOf(fps, r)).filter((r) => r !== null))];
    const beside = (/** @type {string[]} */ refs) => items.filter((i) => itemRefs(i).some((r) => refs.includes(r))).map((i) => i.ref);
    if (selection.kind === "part") return canvas.light(onBoard([selection.id]), beside([selection.id]));
    if (selection.kind === "items") return canvas.light(onBoard(selection.items?.parts ?? []), beside(selection.items?.parts ?? []));
    canvas.light(partsOnNet(progress, selection.id), items.filter((i) => i.lugs.some((l) => l.net === selection.id)).map((i) => i.ref));
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
        if (carry || carryItem || wiring || linkStart) drop();
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
