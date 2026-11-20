/**
 * The board canvas (D-368): the stripboard drawn in SVG at real proportions, parts side,
 * parts as outlines with ref and value. Pans (drag the empty board), zooms (wheel, the
 * canvas's buttons), and tells the root what was clicked. The shapes come from
 * `board-logic.js`; the board and footprints from the root.
 */

import { fitView, panBy, viewBoxText, zoomAt, resizeView } from "../schematic/viewport.js";
import { STEP, holeName, holeXY, labelAt, partShapes, shownHoles, valueOf } from "./board-logic.js";

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
 * @typedef {{
 *   onPart: (ref: string) => void,
 *   onEmpty: () => void,
 * }} CanvasApp
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
    vb = fitView({
      minX: holes.c0 * STEP - FIT_PAD, minY: holes.s0 * STEP - FIT_PAD,
      maxX: holes.c1 * STEP + FIT_PAD, maxY: holes.s1 * STEP + FIT_PAD,
    }, width, height);
    const minW = width / MAX_FIT_SCALE;
    if (vb.w < minW) vb = zoomAt(vb, vb.x + vb.w / 2, vb.y + vb.h / 2, vb.w / minW);
    apply();
  }

  /**
   * Draw a board. `fit`: fit the view to it (the first time it's shown).
   * @param {Board} board @param {Record<string, Footprint>} footprints @param {any} circuit
   * @param {{fit?: boolean}} [opts]
   */
  function draw(board, footprints, circuit, { fit: fitting = false } = {}) {
    holes = shownHoles(board);
    svg.replaceChildren();
    const root = el("g", { class: "board" }, svg);
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
      el("line", { x1, y1, x2, y2, class: "link" }, links);
      for (const [x, y] of [[x1, y1], [x2, y2]]) el("circle", { cx: x, cy: y, r: STEP * 0.18, class: "link-end" }, links);
    }
    const pads = el("g", { class: "pads" }, root);
    for (const pad of board.pads) {
      const [x, y] = holeXY(pad.hole);
      const g = el("g", { class: "pad", "data-hole": holeName(pad.hole) }, pads);
      el("circle", { cx: x, cy: y, r: STEP * 0.3, class: "pad-ring" }, g);
      el("title", {}, g).textContent = `${holeName(pad.hole)}: ${pad.ends.join(", ")}`;
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
      el("tspan", { x: lx, dy: "-0.15em", class: "ref" }, text).textContent = placed.ref;
      const value = valueOf(circuit, placed.ref, fp.refs);
      if (value) el("tspan", { x: lx, dy: "1.05em", class: "value" }, text).textContent = value;
    }
    if (fitting || !shown) fit();
    else apply();
    light(lit);
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

  svg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const start = { x: e.clientX, y: e.clientY, vb };
    let moved = false;
    const target = /** @type {Element} */ (e.target);
    const onMove = (/** @type {PointerEvent} */ ev) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (!moved && Math.hypot(dx, dy) < CLICK_PX) return;
      moved = true;
      svg.classList.add("panning");
      vb = panBy(start.vb, dx, dy, size().width);
      apply();
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      svg.classList.remove("panning");
      if (moved) return;
      const ref = target.closest(".board-part")?.getAttribute("data-ref");
      if (ref) app.onPart(ref);
      else app.onEmpty();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  });

  return {
    draw,
    light,
    fit,
    /** @param {number} factor */
    zoomBy(factor) {
      vb = zoomAt(vb, vb.x + vb.w / 2, vb.y + vb.h / 2, factor);
      apply();
    },
  };
}
