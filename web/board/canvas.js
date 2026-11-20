/**
 * The board canvas (D-368): the stripboard drawn in SVG at real proportions, parts side,
 * parts as outlines with ref and value, shorted copper red (D-374). Pans (drag the empty
 * board), zooms (wheel, the canvas's buttons), and tells the view what was clicked,
 * pressed, dragged and hovered, as holes; draws the view's ghost (a part being carried, a
 * link being laid, the hole a tool would act on). The shapes come from `board-logic.js`;
 * the board and footprints from the view.
 */

import { fitView, panBy, viewBoxText, zoomAt, resizeView } from "../schematic/viewport.js";
import { STEP, columnName, holeName, holeXY, labelAt, partShapes, shortedRects, shownHoles, valueOf } from "./board-logic.js";

const SVG = "http://www.w3.org/2000/svg";
const FIT_PAD = STEP; // board units round the shown holes when fitting
const MAX_FIT_SCALE = 6; // screen pixels per board unit when fitting a small board
const CLICK_PX = 4; // a press that moves less than this is a click, not a pan

/**
 * @param {string} tag @param {Record<string, string | number>} [attrs] @param {Element} [parent]
 * @returns {SVGElement}
 */
function el(tag, attrs = {}, parent) {
  const node = /** @type {SVGElement} */ (document.createElementNS(SVG, tag));
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  parent?.appendChild(node);
  return node;
}

/**
 * @typedef {import("./board-logic.js").Hole} Hole
 * @typedef {{ref: string | null, hole: Hole, link: [Hole, Hole] | null}} Spot
 *   what's under the pointer: a board part's ref, the nearest hole, a link's ends
 * @typedef {{
 *   onClick: (spot: Spot) => void,
 *   onLine: (axis: "column" | "strip", line: number, x: number, y: number) => void,
 *   onPress: (spot: Spot) => boolean,
 *   onDrag: (hole: Hole) => void,
 *   onRelease: (hole: Hole, moved: boolean) => void,
 *   onHover: (hole: Hole | null) => void,
 *   onMenu: (ref: string, x: number, y: number) => void,
 * }} CanvasApp
 *   `onClick`: a press that didn't move (and the view didn't take); `onLine`: a ruler's mark
 *   clicked (a column's letter, a strip's number), at (x, y) in the window; `onPress`: true
 *   when the view takes the press (moving a part, laying a link), so it's dragged through
 *   `onDrag` and ended by `onRelease` instead of panning; `onHover`: the pointer over the
 *   board with no button down (null: it left); `onMenu`: a part right-clicked
 * @typedef {{part?: {fp: Footprint, legs: Array<[string, Hole]>, standing: boolean}, link?: [Hole, Hole], hole?: Hole}} Ghost
 *   what the view is about to do, drawn faint over the board
 * @typedef {import("./board-logic.js").Board} Board
 * @typedef {import("./board-logic.js").Footprint} Footprint
 */

/**
 * @param {SVGSVGElement} svg @param {CanvasApp} app
 */
export function boardCanvas(svg, app) {
  /** @type {import("../schematic/viewport.js").ViewBox} */
  let vb = { x: 0, y: 0, w: 100, h: 100 };
  /** @type {{width: number, height: number} | null} */
  let shown = null;
  /** @type {{c0: number, s0: number, c1: number, s1: number} | null} */
  let holes = null;
  /** @type {string[]} */
  let lit = [];
  /** @type {Ghost | null} */
  let ghosted = null;
  let pressing = false; // a press on the board is being dragged: no hover then

  const size = () => {
    const r = svg.getBoundingClientRect();
    return { width: r.width || 800, height: r.height || 600 };
  };
  const apply = () => {
    svg.setAttribute("viewBox", viewBoxText(vb));
    shown = size();
  };
  const toBoard = (/** @type {number} */ clientX, /** @type {number} */ clientY) => {
    const r = svg.getBoundingClientRect();
    return [vb.x + ((clientX - r.left) / (r.width || 1)) * vb.w, vb.y + ((clientY - r.top) / (r.height || 1)) * vb.h];
  };
  new ResizeObserver(() => {
    if (!shown || svg.getBoundingClientRect().width === 0) return; // hidden: keep the view
    const now = size();
    if (now.width !== shown.width || now.height !== shown.height) vb = resizeView(vb, shown, now);
    apply();
  }).observe(svg);

  function fit() {
    if (!holes) return;
    const { width, height } = size();
    vb = fitView({ // the rulers sit a hole outside the margin
      minX: (holes.c0 - 1) * STEP - FIT_PAD, minY: (holes.s0 - 1) * STEP - FIT_PAD,
      maxX: holes.c1 * STEP + FIT_PAD, maxY: holes.s1 * STEP + FIT_PAD,
    }, width, height);
    const minW = width / MAX_FIT_SCALE;
    if (vb.w < minW) vb = zoomAt(vb, vb.x + vb.w / 2, vb.y + vb.h / 2, vb.w / minW);
    apply();
  }

  /** The hole nearest a point in the window. @param {number} clientX @param {number} clientY @returns {Hole} */
  const holeAt = (clientX, clientY) => {
    const [x, y] = toBoard(clientX, clientY);
    return [Math.round(x / STEP), Math.round(y / STEP)];
  };

  /**
   * Draw a board. `fit`: fit the view to it (the first time it's shown).
   * @param {Board} board @param {Record<string, Footprint>} footprints @param {any} circuit
   * @param {{fit?: boolean, values?: boolean, rulers?: boolean, fixed?: boolean, shorted?: Array<[number, number, number]>}} [opts]
   *   `values`: label parts with their values too; `rulers`: the columns' letters and the
   *   strips' numbers, each a menu of size changes (a board that's started); `fixed`: auto-grow
   *   off, the margin greyed (D-372); `shorted`: the copper carrying two nets, red (D-374)
   */
  function draw(board, footprints, circuit, { fit: fitting = false, values = true, rulers = false, fixed = false, shorted = [] } = {}) {
    holes = shownHoles(board);
    svg.replaceChildren();
    const root = el("g", { class: fixed ? "board board-fixed" : "board" }, svg);
    const { c0, s0, c1, s1 } = holes;
    const half = STEP / 2;
    // the margin's holes, faint; the board itself, its strips and holes
    el("rect", { x: c0 * STEP - half, y: s0 * STEP - half, width: (c1 - c0 + 1) * STEP, height: (s1 - s0 + 1) * STEP, class: "board-margin" }, root);
    const cuts = new Set(board.cuts.map(holeName));
    if (board.columns && board.strips) {
      el("rect", { x: -half, y: -half, width: board.columns * STEP, height: board.strips * STEP, class: "board-base" }, root);
      const strips = el("g", { class: "strips" }, root);
      for (let s = 0; s < board.strips; s++) {
        el("rect", { x: -half + 0.6, y: s * STEP - half + 0.8, width: board.columns * STEP - 1.2, height: STEP - 1.6, rx: 1, class: "strip" }, strips);
      }
      for (const r of shortedRects(shorted)) el("rect", { x: r.x + 0.6, y: r.y + 0.8, width: r.w - 1.2, height: r.h - 1.6, rx: 1, class: "strip shorted" }, strips);
    }
    const dots = el("g", { class: "holes" }, root);
    for (let s = s0; s <= s1; s++) {
      for (let c = c0; c <= c1; c++) {
        const on = c >= 0 && s >= 0 && c < board.columns && s < board.strips;
        if (on && cuts.has(holeName([c, s]))) continue;
        el("circle", { cx: c * STEP, cy: s * STEP, r: STEP * 0.14, class: on ? "hole" : "hole off" }, dots);
      }
    }
    const marks = el("g", { class: "cuts" }, root);
    for (const cut of board.cuts) {
      const [x, y] = holeXY(cut);
      const d = STEP * 0.28;
      el("path", { d: `M${x - d},${y - d} L${x + d},${y + d} M${x - d},${y + d} L${x + d},${y - d}`, class: "cut", "data-hole": holeName(cut) }, marks);
    }
    const links = el("g", { class: "links" }, root);
    for (const [a, b] of board.links) {
      const [x1, y1] = holeXY(a);
      const [x2, y2] = holeXY(b);
      const g = el("g", { class: "board-link", "data-a": a.join(","), "data-b": b.join(",") }, links);
      el("line", { x1, y1, x2, y2, class: "link-hit" }, g);
      el("line", { x1, y1, x2, y2, class: "link" }, g);
      for (const [x, y] of [[x1, y1], [x2, y2]]) el("circle", { cx: x, cy: y, r: STEP * 0.18, class: "link-end" }, g);
    }
    const pads = el("g", { class: "pads" }, root);
    for (const pad of board.pads) {
      const [x, y] = holeXY(pad.hole);
      const g = el("g", { class: "pad", "data-hole": holeName(pad.hole) }, pads);
      el("circle", { cx: x, cy: y, r: STEP * 0.3, class: "pad-ring" }, g);
      el("title", {}, g).textContent = `${holeName(pad.hole)}: ${pad.ends.join(", ")}`;
    }
    if (rulers) {
      const ruled = el("g", { class: "rulers" }, root);
      const mark = (/** @type {"column" | "strip"} */ axis, /** @type {number} */ line, /** @type {number} */ x, /** @type {number} */ y, /** @type {string} */ text) => {
        const g = el("g", { class: "ruler", "data-axis": axis, "data-line": line }, ruled);
        el("rect", { x: x - half, y: y - half, width: STEP, height: STEP, class: "ruler-hit" }, g);
        el("text", { x, y, "text-anchor": "middle", "dominant-baseline": "central" }, g).textContent = text;
        el("title", {}, g).textContent = `${axis === "column" ? "Column" : "Strip"} ${text}: insert or remove`;
      };
      for (let c = 0; c < board.columns; c++) mark("column", c, c * STEP, (s0 - 1) * STEP, columnName(c));
      for (let s = 0; s < board.strips; s++) mark("strip", s, (c0 - 1) * STEP, s * STEP, String(s + 1));
    }
    const parts = el("g", { class: "board-parts" }, root);
    const labels = el("g", { class: "board-labels" }, root); // over every body
    for (const placed of board.parts) {
      const fp = footprints[placed.ref];
      const g = el("g", { class: fp ? "board-part" : "board-part stale", "data-ref": placed.ref }, parts);
      if (!fp) {
        // no longer in the circuit, or no footprint: its legs only, marked
        for (const [, hole] of placed.legs) el("circle", { cx: holeXY(hole)[0], cy: holeXY(hole)[1], r: STEP * 0.3, class: "leg" }, g);
        continue;
      }
      const order = new Map(fp.legs.map((leg, i) => [leg, i]));
      const legs = [...placed.legs].sort((a, b) => (order.get(a[0]) ?? 0) - (order.get(b[0]) ?? 0));
      const shapes = partShapes(fp, legs, placed.standing);
      for (const s of shapes.filter((s) => s.kind === "lead")) el("line", { x1: s.x1, y1: s.y1, x2: s.x2, y2: s.y2, class: "lead" }, g);
      for (const s of shapes) {
        if (s.kind === "rect") el("rect", { x: s.x, y: s.y, width: s.w, height: s.h, rx: Math.min(s.h / 3, 3), transform: `rotate(${s.angle} ${s.cx} ${s.cy})`, class: "body" }, g);
        else if (s.kind === "circle") el("circle", { cx: s.cx, cy: s.cy, r: s.r, class: "body" }, g);
      }
      for (const [, hole] of legs) el("circle", { cx: holeXY(hole)[0], cy: holeXY(hole)[1], r: STEP * 0.16, class: "leg" }, g);
      const [lx, ly] = labelAt(shapes);
      const text = el("text", { x: lx, y: ly, class: "board-label", "text-anchor": "middle", "data-ref": placed.ref }, labels);
      const value = values ? valueOf(circuit, placed.ref, fp.refs) : "";
      el("tspan", { x: lx, dy: value ? "-0.15em" : "0.35em", class: "ref" }, text).textContent = placed.ref;
      if (value) el("tspan", { x: lx, dy: "1.05em", class: "value" }, text).textContent = value;
    }
    el("g", { class: "ghost" }, root);
    if (fitting || !shown) fit();
    else apply();
    light(lit);
    ghost(ghosted);
  }

  /** Draw what the view is about to do, faint (null: nothing). @param {Ghost | null} what */
  function ghost(what) {
    ghosted = what;
    const layer = svg.querySelector(".ghost");
    if (!layer) return;
    layer.replaceChildren();
    if (what?.part) {
      const { fp, legs, standing } = what.part;
      for (const s of partShapes(fp, legs, standing)) {
        if (s.kind === "lead") el("line", { x1: s.x1, y1: s.y1, x2: s.x2, y2: s.y2, class: "lead" }, layer);
        else if (s.kind === "rect") el("rect", { x: s.x, y: s.y, width: s.w, height: s.h, rx: Math.min(s.h / 3, 3), transform: `rotate(${s.angle} ${s.cx} ${s.cy})`, class: "body" }, layer);
        else el("circle", { cx: s.cx, cy: s.cy, r: s.r, class: "body" }, layer);
      }
      for (const [, hole] of legs) el("circle", { cx: holeXY(hole)[0], cy: holeXY(hole)[1], r: STEP * 0.2, class: "leg" }, layer);
    }
    if (what?.link) {
      const [[x1, y1], [x2, y2]] = what.link.map(holeXY);
      el("line", { x1, y1, x2, y2, class: "link" }, layer);
    }
    if (what?.hole) {
      const [x, y] = holeXY(what.hole);
      el("circle", { cx: x, cy: y, r: STEP * 0.36, class: "aim" }, layer);
    }
  }

  /** Light the board parts `refs` (the selection). @param {string[]} refs */
  function light(refs) {
    lit = refs;
    for (const node of svg.querySelectorAll(".board-part.selected")) node.classList.remove("selected");
    for (const node of svg.querySelectorAll(".board-label.selected")) node.classList.remove("selected");
    for (const ref of refs) {
      svg.querySelector(`.board-part[data-ref="${CSS.escape(ref)}"]`)?.classList.add("selected");
      svg.querySelector(`.board-label[data-ref="${CSS.escape(ref)}"]`)?.classList.add("selected");
    }
  }

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [x, y] = toBoard(e.clientX, e.clientY);
    vb = zoomAt(vb, x, y, Math.exp(-e.deltaY * 0.001));
    apply();
  }, { passive: false });

  /** What's under a pointer event. @param {MouseEvent} e @returns {Spot} */
  const spotOf = (e) => {
    const target = /** @type {Element} */ (e.target);
    const link = target.closest(".board-link");
    const ends = link ? ["data-a", "data-b"].map((k) => /** @type {Hole} */ (String(link.getAttribute(k)).split(",").map(Number))) : null;
    return { ref: target.closest(".board-part")?.getAttribute("data-ref") ?? null, hole: holeAt(e.clientX, e.clientY), link: /** @type {[Hole, Hole] | null} */ (ends) };
  };

  svg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const start = { x: e.clientX, y: e.clientY, vb };
    let moved = false;
    const target = /** @type {Element} */ (e.target);
    const ruler = target.closest(".ruler");
    const spot = spotOf(e);
    const taken = !ruler && app.onPress(spot);
    pressing = true;
    const onMove = (/** @type {PointerEvent} */ ev) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (!moved && Math.hypot(dx, dy) < CLICK_PX) return;
      moved = true;
      if (taken) return app.onDrag(holeAt(ev.clientX, ev.clientY));
      svg.classList.add("panning");
      vb = panBy(start.vb, dx, dy, size().width);
      apply();
    };
    const onUp = (/** @type {PointerEvent} */ ev) => {
      window.removeEventListener("pointermove", onMove);
      svg.classList.remove("panning");
      pressing = false;
      if (taken) return app.onRelease(holeAt(ev.clientX, ev.clientY), moved);
      if (moved) return;
      if (ruler) return app.onLine(/** @type {"column" | "strip"} */ (ruler.getAttribute("data-axis")), Number(ruler.getAttribute("data-line")), e.clientX, e.clientY);
      app.onClick(spot);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  });

  svg.addEventListener("pointermove", (e) => {
    if (!pressing) app.onHover(holeAt(e.clientX, e.clientY)); // a drag from the tray too
  });
  svg.addEventListener("pointerleave", () => app.onHover(null));
  svg.addEventListener("contextmenu", (e) => {
    const ref = spotOf(e).ref;
    if (!ref) return;
    e.preventDefault();
    app.onMenu(ref, e.clientX, e.clientY);
  });

  return {
    draw,
    light,
    fit,
    ghost,
    holeAt,
    /** Every hole moved by (dx, dy) (the board grew or shrank at its top or left): the view follows, so the drawing stays still. @param {Hole} by */
    shift([dx, dy]) {
      vb = { ...vb, x: vb.x + dx * STEP, y: vb.y + dy * STEP };
      apply();
    },
    /** @param {number} factor */
    zoomBy(factor) {
      vb = zoomAt(vb, vb.x + vb.w / 2, vb.y + vb.h / 2, factor);
      apply();
    },
  };
}
