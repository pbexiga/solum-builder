/**
 * Draws a circuit view as SVG and turns pointer gestures into edits. Geometry (pin
 * positions, nets, label sides, junctions) comes from the server's circuit view;
 * symbols.js draws the parts; viewport.js does the pan/zoom arithmetic. The schematic
 * never changes the circuit itself: it reports gestures through the handlers.
 *
 * Gestures: click a net (wire, label, pin) or a part to probe it; drag a part to move
 * it; drag from a pin, label or wire to draw a wire; drag a wire end's ball to move that
 * end; drag empty space to pan; scroll to zoom; double-click a part or label to edit it.
 * Shift+drag on empty space draws a box that selects what's inside; Shift+click adds or
 * removes a part; dragging a selected part moves the whole selection (D-072). Ctrl+click
 * (Cmd+click) puts one part, wire, label or text block in the selection or takes it out,
 * and Ctrl+Shift+drag adds a box to it (D-092). Text
 * blocks (D-091) are drawn from the view's `texts`: click selects one, drag moves it,
 * double-click edits it.
 * While placing, a ghost (a part, a label, or a whole block) follows the pointer and a
 * click drops it, saying which wire it was dropped on (to splice a block in).
 *
 * Wire tool (D-062): a click starts a wire anywhere; each later click on empty grid adds
 * a bend (legs are square, the first leg going the way the pointer first moved); a click
 * on a pin, label, wire or wire end finishes it there, and so does a second click on the
 * last point (a double-click), on empty grid too: a wire may end on nothing, as it may
 * start on nothing. Escape or right-click drops it.
 *
 * Problem marks (D-176, as KiCad's ERC markers): a small mark by severity on the pin or
 * part a problem names (`problems.js` says where); its tooltip is the message, and a click
 * on it reports the problem (`onMark`).
 */

import { dcText, impedanceText } from "../fixed.js";
import { GRID, pointOnWire, route, snap, snapPoint, wireEnds } from "../editor/edit.js";
import { crossings } from "../editor/router.js";
import { problemMarks } from "../problems.js";
import { labelText, placeText, rotateOffset, supplySymbol, supplyText, symbol, TEXT_LINE, TEXT_SIZE, textBox, textLines, typeLine, typeSet, valueLine } from "./symbols.js";
import { boundsOf, fitView, panBy, resizeView, revealPoint, viewBoxText, zoomAt } from "./viewport.js";

const SVG = "http://www.w3.org/2000/svg";
const DRAG_THRESHOLD = 4; // pixels before a press becomes a drag
const LABEL_POINT = 3; // schematic units from a label's point where a press draws a wire, not drags it
const GRID_EXTENT = 100000; // the grid rect's half-size, schematic units
const GRID_MIN_PX = 14;
const FOUND_MS = 1600; // how long Find part rings the part
const HOP = 4; // radius of the hop where wires cross
const MARK = 7; // a problem mark's size, schematic units
const MARK_GAP = 9; // between marks on one spot, side by side
const MAX_FIT_SCALE = 2; // screen pixels per schematic unit when fitting a small circuit // closest the grid dots are drawn, in screen pixels

/**
 * @param {string} tag @param {Record<string, string | number>} [attrs] @param {Element} [parent]
 * @returns {SVGElement}
 */
function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  parent?.appendChild(node);
  return node;
}

/**
 * @param {import("./symbols.js").Shape} shape @param {Element} parent
 * @param {number} [rot] the part's turn: text is turned back about its middle, so lug
 *   numbers and signs read upright however the part is turned (D-164)
 */
function drawShape(shape, parent, rot = 0) {
  if ("line" in shape) {
    const [x1, y1, x2, y2] = shape.line;
    return el("line", { x1, y1, x2, y2 }, parent);
  }
  if ("path" in shape) return el("path", { d: shape.path, class: shape.fill ? "filled" : "" }, parent);
  if ("circle" in shape) {
    const [cx, cy, r] = shape.circle;
    return el("circle", { cx, cy, r, class: shape.fill ? "filled" : "" }, parent);
  }
  if ("rect" in shape) {
    const [x, y, width, height] = shape.rect;
    return el("rect", { x, y, width, height }, parent);
  }
  const t = el("text", { x: shape.at[0], y: shape.at[1], class: "sym-text", "text-anchor": shape.anchor ?? "middle" }, parent);
  if (shape.size) t.setAttribute("font-size", String(shape.size));
  if (rot) t.setAttribute("transform", `rotate(${-rot} ${shape.at[0]} ${Number(shape.at[1]) - (shape.size ?? TEXT_SIZE) * 0.35})`);
  t.textContent = shape.text;
  return t;
}

/**
 * A text block, top-left at `pos`: its title in bold, then its lines, over a hit box that
 * also shows the selection. @param {{title?: string, text?: string}} block
 * @param {number[]} pos @param {Element} parent
 */
function drawText(block, pos, parent) {
  const [x0, y0, x1, y1] = textBox(block, pos);
  const hit = el("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 2, class: "text-hit" }, parent);
  const t = el("text", { x: pos[0], y: pos[1], class: "sheet-text" }, parent);
  textLines(block).forEach(({ line, title }, n) => {
    const span = el("tspan", { x: pos[0], dy: n ? TEXT_LINE : TEXT_SIZE, ...(title ? { class: "sheet-title" } : {}) }, t);
    span.textContent = line || "\u00a0";
  });
  // fit the box to the text as drawn (the estimate stands when it can't be measured)
  const drawn = /** @type {SVGTextElement} */ (t).getBBox?.();
  if (drawn?.width) {
    const pad = 3;
    for (const [k, v] of Object.entries({ x: drawn.x - pad, y: drawn.y - pad, width: drawn.width + 2 * pad, height: drawn.height + 2 * pad })) hit.setAttribute(k, String(v));
  }
}

/** @param {{title?: string, text?: string}} block @param {number[]} pos */
const textCorners = (block, pos) => {
  const [x0, y0, x1, y1] = textBox(block, pos);
  return [[x0, y0], [x1, y1]];
};

/**
 * GND labels draw as a ground symbol; a net that carries power (V+, V-, a chip's supply,
 * a pump's output) or a bias reference (VREF: a big cap holds it still) as a supply bar.
 * @param {any} view @param {string} net @returns {"ground" | "rail" | null}
 */
export function supplyKind(view, net) {
  if (net === "GND") return "ground";
  return view.nets[net]?.rail || view.nets[net]?.bias ? "rail" : null;
}

/**
 * A supply's symbol (ground, a rail bar) at the origin of `parent`, turned `rot` clockwise
 * with its name kept upright beyond the bar (D-117); `hit` adds the box that takes clicks.
 * @param {"ground" | "rail"} kind @param {string} net @param {number} rot @param {Element} parent
 * @param {boolean} [hit]
 */
function drawSupply(kind, net, rot, parent, hit = false) {
  const sym = supplySymbol(kind);
  const turned = el("g", rot ? { transform: `rotate(${rot})` } : {}, parent);
  if (hit) {
    const [bx, by, bw, bh] = sym.box;
    el("rect", { x: bx, y: by, width: bw, height: bh, class: "part-hit" }, turned);
  }
  drawShapes(sym.shapes, turned);
  const at = supplyText(kind, rot);
  if (at) el("text", { x: at.x, y: at.y, "text-anchor": at.anchor }, parent).textContent = net;
}

/**
 * Draw a symbol's shapes into `parent` (also used for the palette's tile icons).
 * @param {import("./symbols.js").Shape[]} shapes @param {Element} parent
 */
export function drawShapes(shapes, parent) {
  for (const s of shapes) drawShape(s, parent);
}

/**
 * @typedef {{parts: string[], wires: number[], labels: number[], texts?: number[]}} Items
 * @typedef {{kind: "net" | "part" | "items", id: string, wire?: number, run?: number[], label?: number, items?: Items}} Selection
 *   `wire`: the piece clicked; `run`: the whole wire it's part of (`edit.wireRun`, D-095)
 * @typedef {{
 *   onNet: (net: string, item: {wire?: number, label?: number}) => void,
 *   onPart: (ref: string) => void,
 *   onToggle?: (item: {parts?: string[], wires?: number[], labels?: number[], texts?: number[]}) => void,
 *   onBox?: (box: number[], add: boolean) => void,
 *   onEdit?: (ref: string) => void,
 *   onEditLabel?: (index: number) => void,
 *   onText?: (index: number) => void,
 *   onEditText?: (index: number) => void,
 *   onMove?: (items: Items, dx: number, dy: number) => unknown,
 *   onWire?: (segments: import("../editor/edit.js").Wire[]) => void,
 *   onMoveEnd?: (from: number[], to: number[]) => void,
 *   route?: (a: number[], b: number[], horizontal?: boolean, pending?: import("../editor/edit.js").Wire[]) => import("../editor/edit.js").Wire[],
 *   preview?: (change: {items: Items, dx: number, dy: number} | {from: number[], to: number[]}) => {added: import("../editor/edit.js").Wire[], removed: number[]} | null,
 *   onPlace?: (pos: number[], wire?: number) => void,
 *   onEmpty?: () => void,
 *   onContext?: (x: number, y: number, item: {parts?: string[], wires?: number[], labels?: number[], texts?: number[]} | null) => void,
 *   onMark?: (key: string) => void,
 * }} Handlers
 * @typedef {{parts: any[], wires: any[], labels: any[], nets: Record<string, any>, anchor: number[]}} BlockGhost
 *   a block's view, drawn with `anchor` under the pointer
 * @typedef {{part?: any, label?: string, text?: {title?: string, text?: string}, supply?: "ground" | "rail", block?: BlockGhost, rot: number}} Ghost
 * @typedef {{anchor: number[], segments: import("../editor/edit.js").Wire[], horizontal: boolean | null}} WirePath
 *   a wire being drawn with the wire tool: the bends so far, the last one (`anchor`), and
 *   which way the next leg leaves it (null until the pointer has moved a grid step)
 */

export class Schematic {
  /** @param {SVGSVGElement} svg @param {Handlers} handlers */
  constructor(svg, handlers) {
    this.svg = svg;
    this.handlers = handlers;
    /** @type {any} */
    this.view = null;
    /** @type {Record<string, number>} */
    this.positions = {};
    /** View → Capacitor types: each capacitor's type after its value */
    this.capTypes = false;
    /** @type {import("./viewport.js").ViewBox} */
    this.vb = { x: 0, y: 0, w: 100, h: 100 };
    /** @type {{width: number, height: number} | null} the size the view was last laid out for */
    this.shown = null;
    // the view follows the canvas's size as it changes, so a resize never squeezes the drawing
    new ResizeObserver(() => this.shown && this.resized()).observe(svg);
    this.dcLayer = el("g", { class: "dc-layer" });
    this.zLayer = el("g", { class: "z-layer" });
    this.markLayer = el("g", { class: "mark-layer" });
    /** @type {import("../problems.js").Problem[]} the problems marked (`showMarks`), marked again with the circuit */
    this.problems = [];
    /** @type {{lit?: string[], picked?: string[]}} the parts `highlight` lit, lit again after a redraw */
    this.lit = {};
    /** @type {{voltages: Record<string, number>, held: any[]} | null} the DC voltages shown (`showDc`), drawn again with the circuit */
    this.dc = null;
    /** @type {any} the impedance overlay shown (`showImpedance`), drawn again with the circuit */
    this.impedance = null;
    this.overlay = el("g", { class: "overlay" });
    /** @type {Ghost | null} */
    this.ghost = null;
    this.wireMode = false;
    /** @type {WirePath | null} */
    this.path = null;
    /** @type {number[] | null} where a wire would end under the pointer (wire tool) */
    this.target = null;
    /** @type {number[]} */
    this.pointer = [0, 0];
    /** @type {{pos: number[], wire?: number} | null} where the ghost would drop (`dropSpot`) */
    this.spot = null;
    /** @type {Selection | null} */
    this.selection = null;
    this.listen();
  }

  /**
   * Draw a circuit view. `positions` holds each switch's current position. The view is
   * fitted to the circuit only when `fit` is set (opening a circuit, not editing it).
   * @param {any} view @param {Record<string, number>} positions @param {{fit?: boolean}} [opts]
   */
  draw(view, positions = {}, { fit = true } = {}) {
    this.view = view;
    this.positions = positions;
    this.svg.replaceChildren();
    const defs = el("defs", {}, this.svg);
    const pattern = el("pattern", { id: "grid", width: 10, height: 10, patternUnits: "userSpaceOnUse" }, defs);
    el("circle", { cx: 0, cy: 0, r: 0.7, class: "grid-dot" }, pattern);
    el("rect", { x: -GRID_EXTENT, y: -GRID_EXTENT, width: 2 * GRID_EXTENT, height: 2 * GRID_EXTENT, fill: "url(#grid)", class: "grid" }, this.svg);

    const root = el("g", { class: "schematic" }, this.svg);
    const wires = el("g", { class: "wires" }, root);
    view.wires.forEach((/** @type {any} */ w, /** @type {number} */ i) => {
      const attrs = { x1: w.from[0], y1: w.from[1], x2: w.to[0], y2: w.to[1], "data-net": w.net ?? "", "data-wire": i };
      el("line", { ...attrs, class: "wire" }, wires);
      el("line", { ...attrs, class: "hit" }, wires);
    });
    // a wire crossing another without connecting hops over it (D-063)
    for (const c of crossings(view.wires)) {
      const [x, y] = c.at;
      el("line", { x1: x - HOP, y1: y, x2: x + HOP, y2: y, class: "hop-mask" }, wires);
      el("path", { d: `M${x},${y - HOP} L${x},${y + HOP}`, class: "wire hop", "data-net": view.wires[c.over].net ?? "" }, wires);
      el("path", { d: `M${x - HOP},${y} A${HOP},${HOP} 0 0 1 ${x + HOP},${y}`, class: "wire hop", "data-net": view.wires[c.wire].net ?? "" }, wires);
    }
    for (const [x, y] of view.junctions) el("circle", { cx: x, cy: y, r: 2.6, class: "junction filled" }, wires);

    const parts = el("g", { class: "parts" }, root);
    for (const p of view.parts) this.drawPart(p, positions[p.ref], parts);

    const labels = el("g", { class: "labels" }, root);
    view.labels.forEach((/** @type {any} */ lb, /** @type {number} */ i) => {
      const supply = supplyKind(view, lb.net);
      const g = el("g", { class: `net-label${supply ? ` ${supply}` : ""}`, "data-net": lb.net, "data-label": i, "data-at": lb.pos.join(",") }, labels);
      if (supply) {
        drawSupply(supply, lb.net, lb.rot ?? 0, el("g", { transform: `translate(${lb.pos[0]} ${lb.pos[1]})` }, g), true);
        return;
      }
      el("circle", { cx: lb.pos[0], cy: lb.pos[1], r: 1.8, class: "pin-dot filled" }, g);
      const at = labelText(lb.pos, lb.side);
      const t = el("text", { x: at.x, y: at.y, "text-anchor": at.anchor }, g);
      t.textContent = lb.net;
    });
    const texts = el("g", { class: "texts" }, root);
    (view.texts ?? []).forEach((/** @type {any} */ t, /** @type {number} */ i) => {
      const g = el("g", { class: "text-block", "data-text": i }, texts);
      drawText(t, t.pos, g);
    });
    // wire ends: a ball where a wire meets a pin or label (open when it meets nothing),
    // and a handle on every end to drag it elsewhere
    const ends = el("g", { class: "wire-ends" }, root);
    for (const end of wireEnds(view)) {
      const [cx, cy] = end.pos;
      if (end.kind !== "bend") el("circle", { cx, cy, r: 2, class: `wire-end ${end.kind}` }, ends);
      el("circle", { cx, cy, r: 4, class: "end-hit", "data-net": end.net, "data-at": end.pos.join(",") }, ends);
    }
    root.appendChild(this.dcLayer);
    root.appendChild(this.zLayer);
    root.appendChild(this.markLayer);
    this.svg.appendChild(this.overlay);
    this.drawOverlay();
    if (fit) this.fit();
    else this.apply();
    this.drawDc();
    this.drawImpedance();
    this.drawMarks();
    for (const [cls, refs] of Object.entries(this.lit)) this.highlight(refs, cls === "picked"); // through a redraw (a switch flipped, D-127)
  }

  /** @param {any} p @param {number | undefined} position @param {Element} parent */
  drawPart(p, position, parent) {
    const sym = symbol(p, position);
    const g = el("g", { class: "part", "data-ref": p.ref, transform: `translate(${p.pos[0]} ${p.pos[1]}) rotate(${p.rot})` }, parent);
    // a DC source the ideal supply replaces (D-064): faded, and says so
    const [bx, by, bw, bh] = sym.box;
    el("rect", { x: bx, y: by, width: bw, height: bh, class: "part-hit" }, g);
    for (const s of sym.shapes) drawShape(s, g, p.rot ?? 0);
    // pin hit targets: clicking a pin probes its net, dragging from it draws a wire
    for (const pin of p.pins) {
      const lead = sym.leads[pin.name];
      if (lead) el("circle", { cx: lead[0], cy: lead[1], r: 4, class: "pin-hit", "data-net": pin.net ?? "", "data-at": pin.pos.join(",") }, g);
    }
    const text = el("g", { class: "part-text", "data-ref": p.ref }, parent);
    const ref = placeText(sym, p.rot, 0);
    const value = placeText(sym, p.rot, 1);
    const refText = el("text", { x: p.pos[0] + ref.x, y: p.pos[1] + ref.y, "text-anchor": ref.anchor, class: "ref" }, text);
    // a knob's label is shown after its ref, unless it only repeats it (VOLUME Volume)
    refText.textContent = p.label && p.label.toLowerCase() !== p.ref.toLowerCase() ? `${p.ref} ${p.label}` : p.ref;
    const valueText = el("text", { x: p.pos[0] + value.x, y: p.pos[1] + value.y, "text-anchor": value.anchor, class: "value" }, text);
    valueText.textContent = valueLine(p, position);
    const type = this.capTypes ? typeLine(p) : ""; // View → Capacitor types (D-144): under the value
    if (type) el("text", { x: p.pos[0] + value.x, y: p.pos[1] + value.y + TEXT_LINE, "text-anchor": value.anchor, class: typeSet(p) ? "value cap-type" : "value cap-type unset" }, text).textContent = type;
    // a chip's pin numbers (D-140), upright whichever way the part is turned
    for (const { at, text: number } of Object.values(sym.numbers ?? {})) {
      const [dx, dy] = rotateOffset([Number(at[0]), Number(at[1])], p.rot);
      const anchor = p.rot ? "middle" : String(at[2]);
      el("text", { x: p.pos[0] + dx, y: p.pos[1] + dy, "text-anchor": anchor, class: "pin-number" }, text).textContent = number;
    }
    if (p.draw?.unused) g.classList.add("unused"); // a chip's spare half: not simulated
  }

  /** Re-draw one switch at a new position (knob change). @param {string} ref @param {number} position */
  redrawPart(ref, position) {
    this.positions[ref] = position;
    const part = this.view?.parts.find((/** @type {any} */ p) => p.ref === ref);
    const old = this.svg.querySelector(`g.part[data-ref="${CSS.escape(ref)}"]`);
    if (!part || !old) return;
    const holder = el("g", {});
    this.drawPart(part, position, holder);
    const [shape, text] = [...holder.children]; // its symbol and its ref and label
    const oldText = this.svg.querySelector(`g.part-text[data-ref="${CSS.escape(ref)}"]`);
    old.replaceWith(shape);
    if (oldText && text) oldText.replaceWith(text); // round 3b: the label went with the flip
    for (const [cls, refs] of Object.entries(this.lit)) this.highlight(refs, cls === "picked"); // a switch flipped while in use stays lit
  }

  fit() {
    if (!this.view) return;
    const points = [
      ...this.view.parts.map((/** @type {any} */ p) => p.pos),
      ...this.view.labels.map((/** @type {any} */ l) => l.pos),
      ...(this.view.texts ?? []).flatMap((/** @type {any} */ t) => textCorners(t, t.pos)),
      ...this.view.wires.flatMap((/** @type {any} */ w) => [w.from, w.to]),
    ];
    const { width, height } = this.size();
    this.vb = fitView(boundsOf(points, 60), width, height);
    // a small circuit is shown at MAX_FIT_SCALE, not blown up to fill the screen
    const minW = width / MAX_FIT_SCALE;
    if (this.vb.w < minW) this.vb = zoomAt(this.vb, this.vb.x + this.vb.w / 2, this.vb.y + this.vb.h / 2, this.vb.w / minW);
    this.apply();
  }

  /** After the canvas resizes: the same zoom and middle, the drawing not re-fitted (D-164), kept up as it changes. */
  resized() {
    const now = this.size();
    if (this.shown && (now.width !== this.shown.width || now.height !== this.shown.height)) this.vb = resizeView(this.vb, this.shown, now);
    this.apply();
  }

  size() {
    const r = this.svg.getBoundingClientRect();
    return { width: r.width || 800, height: r.height || 600 };
  }

  apply() {
    this.svg.setAttribute("viewBox", viewBoxText(this.vb));
    this.shown = this.size(); // what the view was laid out for (`resized`)
    // grid dots: the snap grid (10) doubled until they're at least GRID_MIN_PX apart on
    // screen, each about a pixel across at any zoom
    const unitsPerPx = this.vb.w / this.size().width;
    let spacing = GRID;
    while (spacing / unitsPerPx < GRID_MIN_PX) spacing *= 2;
    const pattern = this.svg.querySelector("#grid");
    pattern?.setAttribute("width", String(spacing));
    pattern?.setAttribute("height", String(spacing));
    pattern?.firstElementChild?.setAttribute("r", String(1.1 * unitsPerPx));
  }

  /**
   * Highlight a probed net (and the clicked wire or label) or a selected part.
   * @param {Selection | null} selection
   */
  select(selection) {
    this.selection = selection;
    for (const node of this.svg.querySelectorAll(".probed, .selected")) node.classList.remove("probed", "selected");
    if (!selection) return;
    if (selection.kind === "items") {
      const items = /** @type {Items} */ (selection.items);
      for (const ref of items.parts) for (const node of this.svg.querySelectorAll(`[data-ref="${CSS.escape(ref)}"]`)) node.classList.add("selected");
      for (const i of items.wires) this.svg.querySelector(`line.wire[data-wire="${i}"]`)?.classList.add("selected");
      for (const i of items.labels) this.svg.querySelector(`[data-label="${i}"]`)?.classList.add("selected");
      for (const i of items.texts ?? []) this.svg.querySelector(`[data-text="${i}"]`)?.classList.add("selected");
    } else if (selection.kind === "net") {
      for (const node of this.svg.querySelectorAll(`[data-net="${CSS.escape(selection.id)}"]`)) node.classList.add("probed");
      for (const i of selection.run ?? (selection.wire !== undefined ? [selection.wire] : [])) this.svg.querySelector(`line.wire[data-wire="${i}"]`)?.classList.add("selected");
      if (selection.label !== undefined) this.svg.querySelector(`[data-label="${selection.label}"]`)?.classList.add("selected");
    } else {
      for (const node of this.svg.querySelectorAll(`[data-ref="${CSS.escape(selection.id)}"]`)) node.classList.add("selected");
    }
  }

  /**
   * Show (or hide, with null) each net's DC voltage next to its labels; a net a trimmer
   * holds to a target is in its own colour (`.held`), its tooltip the target and the turn (D-127).
   * @param {Record<string, number> | null} voltages
   * @param {Array<{net: string, ref: string, volts: number, reached: number, rotation: number, met: boolean}>} [held]
   */
  showDc(voltages, held = []) {
    this.dc = voltages ? { voltages, held } : null;
    this.drawDc();
  }

  /** The DC voltages, where the drawing has their labels and pins now. Each says what it
   * sits by (`data-dc-label`, `data-at`), so a dragged selection takes it along. */
  drawDc() {
    this.dcLayer.replaceChildren();
    if (!this.dc || !this.view) return;
    const { voltages, held } = this.dc;
    const targets = new Map(held.map((t) => [t.net, t]));
    /** @param {Record<string, string>} attrs @param {string} net */
    const write = (attrs, net) => {
      const d = dcText(voltages[net], targets.get(net));
      const cls = `dc${targets.has(net) ? (d.met ? " held" : " held unmet") : ""}`;
      const t = el("text", { ...attrs, class: cls, "data-net": net }, this.dcLayer);
      t.textContent = d.text;
      if (d.title) el("title", {}, t).textContent = d.title;
    };
    const placed = new Set();
    this.view.labels.forEach((/** @type {any} */ lb, /** @type {number} */ i) => {
      const v = voltages[lb.net];
      if (v === undefined) return;
      const supply = supplyKind(this.view, lb.net);
      if (supply === "ground") {
        placed.add(lb.net);
        return;
      }
      const at = supply ? { x: lb.pos[0] + 11, y: 0, anchor: "start", dcY: lb.pos[1] - 7 } : labelText(lb.pos, lb.side);
      write({ x: String(at.x), y: String(at.dcY), "text-anchor": at.anchor, "data-dc-label": String(i) }, lb.net);
      placed.add(lb.net);
    });
    // nets with no label: at their anchor (first pin)
    for (const [net, info] of Object.entries(this.view.nets)) {
      if (placed.has(net) || voltages[net] === undefined) continue;
      for (const [x, y] of /** @type {any} */ (info).anchors) {
        write({ x: String(x + 4), y: String(y - 5), "text-anchor": "start", "data-at": `${x},${y}` }, net);
      }
    }
  }

  /**
   * Show (or hide, with null) the View → Impedance overlay (D-127): Zin under the guitar,
   * Zout under the amp, from `POST /api/impedance`; a saturated stage says so instead.
   * @param {{freq: number, zin: any, zout: any} | null} z
   */
  showImpedance(z) {
    this.impedance = z;
    this.drawImpedance();
  }

  drawImpedance() {
    this.zLayer.replaceChildren();
    const z = this.impedance;
    if (!z || !this.view) return;
    for (const key of /** @type {const} */ (["zin", "zout"])) {
      const end = z[key];
      // under the part and its own words (its ref, its value): all that carries its ref
      const drawn = end ? [...this.svg.querySelectorAll(`[data-ref="${CSS.escape(end.ref)}"]`)].map((n) => n.getBoundingClientRect()).filter((r) => r.width || r.height) : [];
      if (!drawn.length) continue; // not drawn, or not laid out (hidden)
      const [x0, y0] = this.toSchematic(Math.min(...drawn.map((r) => r.left)), Math.min(...drawn.map((r) => r.top)));
      const [x1, y1] = this.toSchematic(Math.max(...drawn.map((r) => r.right)), Math.max(...drawn.map((r) => r.bottom)));
      const { lines, title } = impedanceText(key, end);
      lines.forEach((line, i) => {
        const t = el("text", { x: (x0 + x1) / 2, y: y1 + 12 + i * 11, "text-anchor": "middle", class: `impedance${end.saturated ? " unmet" : ""}${i ? " sub" : ""}`, "data-z": key, "data-for": end.ref }, this.zLayer);
        t.textContent = line;
        el("title", {}, t).textContent = title;
      });
    }
  }

  /**
   * Mark these problems on the sheet (D-176); none clears the marks. The circuit's own
   * dismissals (in the view) leave theirs out, so an undone dismissal marks again.
   * @param {import("../problems.js").Problem[]} problems
   */
  showMarks(problems) {
    this.problems = problems;
    this.drawMarks();
  }

  drawMarks() {
    this.markLayer.replaceChildren();
    if (!this.view) return;
    /** @type {Map<string, number>} marks already on each spot: the next goes beside them */
    const taken = new Map();
    for (const mark of problemMarks(this.problems, this.view.circuit?.dismissed, this.view)) {
      const { spot } = mark;
      const at = spot.kind === "part" ? this.partCorner(spot.ref) : [spot.pos[0] + MARK, spot.pos[1] - MARK];
      if (!at) continue;
      const id = spot.kind === "net" ? `net:${spot.net}` : spot.kind === "pin" ? `pin:${spot.ref}.${spot.pin}` : `part:${spot.ref}`;
      const n = taken.get(id) ?? 0;
      taken.set(id, n + 1);
      const [x, y] = [at[0] + n * MARK_GAP, at[1]];
      const g = el("g", { class: `problem-mark sev-${mark.severity}`, "data-mark": mark.key, "data-for": spot.kind === "net" ? spot.net : spot.ref, ...(spot.kind === "pin" ? { "data-pin": spot.pin } : {}) }, this.markLayer);
      const r = MARK / 2;
      if (mark.severity === "error") el("rect", { x: x - r, y: y - r, width: MARK, height: MARK, rx: 1 }, g);
      else if (mark.severity === "warning") el("path", { d: `M${x},${y - r - 1} L${x + r + 1},${y + r} L${x - r - 1},${y + r} Z` }, g);
      else el("circle", { cx: x, cy: y, r }, g);
      el("title", {}, g).textContent = mark.message;
    }
  }

  /**
   * Where a part's mark goes: just off its symbol's top right corner, as drawn (turned).
   * @param {string} ref @returns {number[] | null}
   */
  partCorner(ref) {
    const p = this.view.parts.find((/** @type {any} */ q) => q.ref === ref);
    if (!p) return null;
    const [bx, by, bw, bh] = symbol(p, this.positions[ref]).box;
    const corners = [[bx, by], [bx + bw, by + bh]].map((c) => rotateOffset(c, p.rot ?? 0));
    return [Math.max(...corners.map((c) => c[0])) + p.pos[0] + 2, Math.min(...corners.map((c) => c[1])) + p.pos[1] - 2];
  }

  /**
   * Start placing: a ghost part (or net label) follows the pointer until a click drops
   * it (`onPlace`) or `stopPlacing` is called. @param {Ghost} ghost
   */
  startPlacing(ghost) {
    this.ghost = ghost;
    this.spot = null;
    this.wireMode = false;
    this.svg.classList.add("placing");
    this.drawGhost();
  }

  stopPlacing() {
    this.ghost = null;
    this.svg.classList.remove("placing");
    this.overlay.replaceChildren();
  }

  /** Turn the ghost a quarter turn (Space while placing). */
  rotateGhost() {
    if (!this.ghost?.part && !this.ghost?.supply) return; // blocks are dropped as drawn; a plain label's name finds its own side
    this.ghost.rot = (this.ghost.rot + 90) % 360;
    this.drawGhost();
  }

  /** @param {boolean} on wire mode: clicks draw wires (see the wire tool above) */
  setWireMode(on) {
    this.wireMode = on;
    this.path = null;
    this.target = null;
    if (on) this.stopPlacing();
    this.svg.classList.toggle("wiring", on);
    this.drawOverlay();
  }

  /** Drop the wire being drawn, if any. @returns {boolean} there was one */
  cancelWire() {
    if (!this.path) return false;
    this.path = null;
    this.drawOverlay();
    return true;
  }

  /**
   * Where a wire drawn to `target` would end: a pin, label or wire end's point, or the
   * nearest point on a wire. Null over anything else (empty grid, a part's body).
   * @param {Element | null} target @param {number[]} at
   * @returns {number[] | null}
   */
  terminalAt(target, at) {
    const anchored = target?.closest(".end-hit, .pin-hit, .net-label");
    if (anchored) return /** @type {string} */ (anchored.getAttribute("data-at")).split(",").map(Number);
    const wire = target?.closest("line.hit")?.getAttribute("data-wire");
    if (wire != null && this.view) return pointOnWire(this.view.wires[Number(wire)], at);
    return null;
  }

  /**
   * A click with the wire tool: start a wire, add a bend, or finish: on a terminal, or
   * anywhere with a second click on the last point (a double-click).
   * @param {Element | null} target @param {number[]} at
   */
  wireClick(target, at) {
    const end = this.terminalAt(target, at);
    const point = end ?? snapPoint(at);
    const path = this.path;
    if (!path) {
      this.path = { anchor: point, segments: [], horizontal: null };
      return this.drawOverlay();
    }
    const again = point[0] === path.anchor[0] && point[1] === path.anchor[1]; // the last point, clicked again
    const legs = again ? [] : this.routeLeg(path.anchor, point, path.horizontal ?? undefined, path.segments);
    path.segments.push(...legs);
    if ((end || again) && path.segments.length) {
      this.path = null;
      this.drawOverlay();
      return this.handlers.onWire?.(path.segments);
    }
    if (legs.length) Object.assign(path, { anchor: point, horizontal: null });
    this.drawOverlay();
  }

  /**
   * Where the ghost would drop with the pointer over `under`: the grid point under it or,
   * over a wire (a part, label or supply, not a block), the nearest point on that wire, so
   * a click on the wire's edge still lands on the line. `wire`: the wire it's over.
   * @param {Element | null} under @returns {{pos: number[], wire?: number}}
   */
  dropSpot(under) {
    const hit = under?.closest("line.hit")?.getAttribute("data-wire");
    if (hit == null) return { pos: snapPoint(this.pointer) };
    const wire = Number(hit);
    const w = this.ghost?.block ? undefined : this.view?.wires[wire];
    return { pos: w ? pointOnWire(w, this.pointer) : snapPoint(this.pointer), wire };
  }

  /** The overlay: the placing ghost, or the wire being drawn. */
  drawOverlay() {
    if (this.ghost) return this.drawGhost();
    this.overlay.replaceChildren();
    if (this.wireMode && this.target) el("circle", { cx: this.target[0], cy: this.target[1], r: 4, class: "wire-target" }, this.overlay);
    const path = this.path;
    if (!path) return;
    const g = el("g", { class: "ghost wire-path" }, this.overlay);
    const to = this.target ?? snapPoint(this.pointer);
    for (const w of [...path.segments, ...this.routeLeg(path.anchor, to, path.horizontal ?? undefined, path.segments)]) {
      el("line", { x1: w.from[0], y1: w.from[1], x2: w.to[0], y2: w.to[1] }, g);
    }
    const start = path.segments[0]?.from ?? path.anchor;
    el("circle", { cx: start[0], cy: start[1], r: 2, class: "filled" }, g);
  }

  /**
   * A leg of wire from `a` to `b`, routed by the app (around parts, D-063), or a plain
   * elbow without one.
   * @param {number[]} a @param {number[]} b @param {boolean} [horizontal]
   * @param {import("../editor/edit.js").Wire[]} [pending]
   */
  routeLeg(a, b, horizontal, pending = []) {
    return this.handlers.route?.(snapPoint(a), snapPoint(b), horizontal, pending) ?? route(a, b, horizontal);
  }

  /**
   * Show how wires will be re-laid while dragging: the new ones as a ghost; the ones they
   * replace hidden, with the end and junction dots only they had (left showing, they
   * looked like wires stuck behind until the drop, the user, D-095). Null clears it.
   * @param {{added: any[], removed: number[]} | null} diff
   */
  showRelay(diff) {
    for (const node of this.svg.querySelectorAll(".relaying")) node.classList.remove("relaying");
    this.overlay.replaceChildren();
    if (!diff) return;
    const gone = new Set(diff.removed.map(String));
    /** @type {Set<string>} */
    const left = new Set();
    /** @type {Set<string>} */
    const kept = new Set();
    for (const line of this.svg.querySelectorAll("line.wire")) {
      const ends = [`${line.getAttribute("x1")},${line.getAttribute("y1")}`, `${line.getAttribute("x2")},${line.getAttribute("y2")}`];
      const removed = gone.has(line.getAttribute("data-wire") ?? "");
      if (removed) line.classList.add("relaying");
      for (const p of ends) (removed ? left : kept).add(p);
    }
    for (const dot of this.svg.querySelectorAll("circle.junction, circle.wire-end")) {
      const at = `${dot.getAttribute("cx")},${dot.getAttribute("cy")}`;
      if (left.has(at) && !kept.has(at)) dot.classList.add("relaying");
    }
    const g = el("g", { class: "ghost relay" }, this.overlay);
    for (const w of diff.added) el("line", { x1: w.from[0], y1: w.from[1], x2: w.to[0], y2: w.to[1] }, g);
  }

  /** Lock which way the next leg goes once the pointer has moved a grid step from the last bend. */
  followPath() {
    const path = this.path;
    if (!path) return;
    const [dx, dy] = [this.pointer[0] - path.anchor[0], this.pointer[1] - path.anchor[1]];
    if (Math.max(Math.abs(dx), Math.abs(dy)) < GRID) path.horizontal = null;
    else if (path.horizontal === null) path.horizontal = Math.abs(dx) >= Math.abs(dy);
  }

  drawGhost() {
    this.overlay.replaceChildren();
    if (!this.ghost) return;
    const [x, y] = this.spot?.pos ?? snapPoint(this.pointer);
    const g = el("g", { class: "ghost", transform: `translate(${x} ${y})` }, this.overlay);
    if (this.ghost.block) {
      const b = this.ghost.block;
      const inner = el("g", { transform: `translate(${-b.anchor[0]} ${-b.anchor[1]})` }, g);
      for (const p of b.parts) {
        const pg = el("g", { transform: `translate(${p.pos[0]} ${p.pos[1]}) rotate(${p.rot})` }, inner);
        for (const s of symbol(p, 0).shapes) drawShape(s, pg, p.rot ?? 0);
      }
      for (const w of b.wires) el("line", { x1: w.from[0], y1: w.from[1], x2: w.to[0], y2: w.to[1] }, inner);
      for (const lb of b.labels) {
        const supply = supplyKind(b, lb.net);
        if (supply) {
          drawSupply(supply, lb.net, lb.rot ?? 0, el("g", { transform: `translate(${lb.pos[0]} ${lb.pos[1]})` }, inner));
        } else {
          el("circle", { cx: lb.pos[0], cy: lb.pos[1], r: 1.8, class: "filled" }, inner);
          el("text", { x: lb.pos[0], y: lb.pos[1] - 6, "text-anchor": "middle" }, inner).textContent = lb.net;
        }
      }
      for (const t of b.texts ?? []) drawText(t, t.pos, inner);
    } else if (this.ghost.text !== undefined) {
      drawText(this.ghost.text, [0, 0], g);
    } else if (this.ghost.part) {
      const inner = el("g", { transform: `rotate(${this.ghost.rot})` }, g);
      for (const s of symbol({ ...this.ghost.part, pins: [] }).shapes) drawShape(s, inner, this.ghost.rot);
    } else if (this.ghost.supply) {
      drawSupply(this.ghost.supply, this.ghost.label ?? "", this.ghost.rot, g);
    } else {
      el("circle", { cx: 0, cy: 0, r: 1.8, class: "filled" }, g);
      const t = el("text", { x: 0, y: -6, "text-anchor": "middle" }, g);
      t.textContent = this.ghost.label ?? "";
    }
  }

  /**
   * Follow a pointer that's outside the svg's own events (a part dragged from the
   * palette): move the ghost there when it's over the canvas, hide it when it isn't.
   * @param {number} clientX @param {number} clientY @returns {boolean} over the canvas
   */
  hover(clientX, clientY) {
    const r = this.svg.getBoundingClientRect();
    const inside = clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom;
    this.pointer = this.toSchematic(clientX, clientY);
    this.spot = this.dropSpot(document.elementFromPoint(clientX, clientY));
    if (inside) this.drawGhost();
    else this.overlay.replaceChildren();
    return inside;
  }

  /** Zoom about the centre of the view (the +/− buttons). @param {number} factor > 1 zooms in */
  zoomBy(factor) {
    this.vb = zoomAt(this.vb, this.vb.x + this.vb.w / 2, this.vb.y + this.vb.h / 2, factor);
    this.apply();
  }

  /**
   * Light up some parts without selecting them (a part influence row hovered, D-097);
   * none clears it. `picked`: the picked layer instead (a stage clicked in Bias &
   * headroom, in its own colour, D-127), kept while the ordinary highlight comes and goes.
   * @param {string[]} refs @param {boolean} [picked]
   */
  highlight(refs, picked = false) {
    const cls = picked ? "picked" : "lit";
    this.lit[cls] = refs;
    for (const node of this.svg.querySelectorAll(`.${cls}`)) node.classList.remove(cls);
    for (const ref of refs) for (const node of this.svg.querySelectorAll(`[data-ref="${CSS.escape(ref)}"]`)) node.classList.add(cls);
  }

  /**
   * Bring part `ref` into view (centred if it was off screen or near an edge) and ring it
   * for a moment so the eye finds it (Find part). False if there's no such part.
   * @param {string} ref @returns {boolean}
   */
  reveal(ref) {
    const part = this.view?.parts.find((/** @type {any} */ p) => p.ref === ref);
    const g = this.svg.querySelector(`g.part[data-ref="${CSS.escape(ref)}"]`);
    if (!part || !g) return false;
    this.vb = revealPoint(this.vb, part.pos[0], part.pos[1]);
    this.apply();
    const r = g.getBoundingClientRect();
    const [x0, y0] = this.toSchematic(r.left, r.top);
    const [x1, y1] = this.toSchematic(r.right, r.bottom);
    const pad = 8;
    this.svg.querySelector(".found-ring")?.remove();
    const ring = el("rect", { x: x0 - pad, y: y0 - pad, width: x1 - x0 + 2 * pad, height: y1 - y0 + 2 * pad, rx: 6, class: "found-ring", "data-found": ref }, this.svg);
    setTimeout(() => ring.remove(), FOUND_MS);
    return true;
  }

  /** @param {import("../editor/edit.js").Wire[]} wires */
  drawWirePreview(wires) {
    this.overlay.replaceChildren();
    const g = el("g", { class: "ghost" }, this.overlay);
    for (const w of wires) el("line", { x1: w.from[0], y1: w.from[1], x2: w.to[0], y2: w.to[1] }, g);
  }

  /**
   * What a press on `target` starts: moving a wire end (its ball), a wire from a pin,
   * label or wire, a move of a part, or a pan. A press on anything in a selection of
   * several items moves them all (`grabsSelection`, D-113). With the wire tool on, a drag
   * only pans (or moves a wire end): its clicks draw.
   * @param {Element | null} target @param {number[]} at schematic point under the pointer
   * @returns {{kind: "wire" | "end", from: number[]} | {kind: "move", ref?: string, text?: number, wire?: number, label?: number, all?: boolean} | {kind: "pan"} | {kind: "box"}}
   */
  gestureAt(target, at) {
    if (!this.wireMode && this.grabsSelection(target)) return { kind: "move", all: true };
    const end = target?.closest(".end-hit");
    if (end) return { kind: "end", from: /** @type {string} */ (end.getAttribute("data-at")).split(",").map(Number) };
    if (this.wireMode) return { kind: "pan" };
    const label = target?.closest(".net-label");
    if (label) {
      // a label drags by its symbol or name (D-164); right on its point, it starts a wire
      const pos = /** @type {string} */ (label.getAttribute("data-at")).split(",").map(Number);
      if (Math.hypot(at[0] - pos[0], at[1] - pos[1]) <= LABEL_POINT) return { kind: "wire", from: pos };
      return { kind: "move", label: Number(label.getAttribute("data-label")) };
    }
    const pin = target?.closest(".pin-hit");
    if (pin) return { kind: "wire", from: /** @type {string} */ (pin.getAttribute("data-at")).split(",").map(Number) };
    if (target?.classList.contains("hit")) {
      // a selected wire drags (D-095); any other starts a new wire from the point pressed
      const wire = Number(target.getAttribute("data-wire"));
      if (target.hasAttribute("data-wire") && this.inSelection({ wires: [wire] })) return { kind: "move", wire };
      return { kind: "wire", from: snapPoint(at) };
    }
    const text = target?.closest("g.text-block")?.getAttribute("data-text");
    if (text != null) return { kind: "move", text: Number(text) };
    const ref = target?.closest("g.part")?.getAttribute("data-ref");
    if (ref) return { kind: "move", ref };
    return { kind: "pan" };
  }

  listen() {
    // right-click: select what's under the pointer (unless it's in the selection already,
    // so a group stays selected), then ask for the menu (D-095)
    this.svg.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      if (this.ghost || this.path) return; // placing or drawing a wire: Esc cancels those
      const target = /** @type {Element} */ (e.target);
      const item = this.itemAt(target);
      if (item && !this.inSelection(item)) this.click(target);
      this.handlers.onContext?.(e.clientX, e.clientY, item);
    });
    /** @type {{x: number, y: number, vb: import("./viewport.js").ViewBox, moved: boolean, at: number[], last: string,
     *   add: boolean, ctrl: boolean, gesture: ReturnType<Schematic["gestureAt"]>} | null} */
    let press = null;
    this.svg.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const at = this.toSchematic(e.clientX, e.clientY);
      /** @type {ReturnType<Schematic["gestureAt"]>} */
      let gesture = this.ghost ? { kind: "pan" } : this.gestureAt(/** @type {Element} */ (e.target), at);
      if (gesture.kind === "pan" && e.shiftKey && !this.ghost && !this.wireMode) gesture = { kind: "box" };
      const ctrl = e.ctrlKey || e.metaKey;
      press = { x: e.clientX, y: e.clientY, vb: { ...this.vb }, moved: false, at, gesture, last: "", add: e.shiftKey || ctrl, ctrl };
      this.svg.setPointerCapture(e.pointerId);
    });
    this.svg.addEventListener("pointermove", (e) => {
      this.pointer = this.toSchematic(e.clientX, e.clientY);
      if (!press) {
        if (this.wireMode) {
          this.target = this.terminalAt(/** @type {Element} */ (e.target), this.pointer);
          this.followPath();
          this.drawOverlay();
        } else if (this.ghost) {
          this.spot = this.dropSpot(/** @type {Element} */ (e.target));
          this.drawGhost();
        }
        return;
      }
      const dx = e.clientX - press.x;
      const dy = e.clientY - press.y;
      if (!press.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      press.moved = true;
      const g = press.gesture;
      if (g.kind === "box") {
        this.overlay.replaceChildren();
        const [x1, y1] = press.at;
        const [x2, y2] = this.pointer;
        el("rect", { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1), class: "select-box" }, this.overlay);
      } else if (g.kind === "pan") {
        this.svg.classList.add("panning");
        this.vb = panBy(press.vb, dx, dy, this.size().width);
        this.apply();
      } else if (g.kind === "wire") {
        this.drawWirePreview(this.routeLeg(g.from, this.pointer));
      } else if (g.kind === "end") {
        const to = snapPoint(this.pointer);
        if (to.join() !== press.last) this.showRelay(this.handlers.preview?.({ from: g.from, to }) ?? null);
        press.last = to.join();
      } else {
        const [mx, my] = [snap(this.pointer[0] - press.at[0]), snap(this.pointer[1] - press.at[1])];
        const items = this.movingItems(g);
        // what a moved part or label carries along: its DC voltage and impedance readings
        const refs = new Set(items.parts);
        const pins = (this.view?.parts ?? []).filter((/** @type {any} */ p) => refs.has(p.ref)).flatMap((/** @type {any} */ p) => p.pins.map((/** @type {any} */ pin) => pin.pos.join(",")));
        const nodes = [
          ...items.parts.flatMap((ref) => [...this.svg.querySelectorAll(`[data-ref="${CSS.escape(ref)}"], [data-for="${CSS.escape(ref)}"]`)]),
          ...items.labels.flatMap((i) => [...this.svg.querySelectorAll(`[data-label="${i}"]:not(line), [data-dc-label="${i}"]`)]),
          ...pins.flatMap((at) => [...this.dcLayer.querySelectorAll(`[data-at="${at}"]`)]),
          ...(items.texts ?? []).flatMap((i) => [...this.svg.querySelectorAll(`[data-text="${i}"]`)]),
        ];
        for (const node of nodes) {
          node.setAttribute("data-drag", "true");
          /** @type {SVGElement} */ (node).style.translate = `${mx}px ${my}px`;
        }
        // the wires follow live, re-laid the way they will be on drop
        if (`${mx},${my}` !== press.last) this.showRelay(mx || my ? (this.handlers.preview?.({ items, dx: mx, dy: my }) ?? null) : null);
        press.last = `${mx},${my}`;
      }
    });
    this.svg.addEventListener("pointerup", (e) => {
      if (!press) return;
      const { moved, gesture, at, add, ctrl } = press;
      press = null;
      this.svg.classList.remove("panning");
      const here = this.toSchematic(e.clientX, e.clientY);
      if (!moved) {
        // pointer capture retargets events to the svg: find what's under the pointer
        const under = /** @type {Element | null} */ (document.elementFromPoint(e.clientX, e.clientY));
        if (this.ghost) {
          const spot = this.dropSpot(under);
          return this.handlers.onPlace?.(spot.pos, spot.wire);
        }
        return this.wireMode ? this.wireClick(under, here) : this.click(under, add);
      }
      if (gesture.kind === "box") {
        this.overlay.replaceChildren();
        return this.handlers.onBox?.([at[0], at[1], here[0], here[1]], ctrl); // Ctrl+Shift+drag adds
      }
      if (gesture.kind === "wire" || gesture.kind === "end") {
        this.drawOverlay();
        // let go over a pin, label or wire: the end lands exactly there
        const under = /** @type {Element | null} */ (document.elementFromPoint(e.clientX, e.clientY));
        const to = this.terminalAt(under?.closest(".end-hit")?.getAttribute("data-at") === gesture.from.join(",") ? null : under, here) ?? snapPoint(here);
        if (to[0] === gesture.from[0] && to[1] === gesture.from[1]) return;
        this.showRelay(null);
        if (gesture.kind === "wire") this.handlers.onWire?.(this.routeLeg(gesture.from, to));
        else this.handlers.onMoveEnd?.(gesture.from, to);
      } else if (gesture.kind === "move") {
        const [dx, dy] = [snap(here[0] - at[0]), snap(here[1] - at[1])];
        // the preview stays until the move is drawn (or refused): cleared first, the old
        // wires showed for a moment, then jumped (the user, 2026-10-29, D-164)
        const done = () => {
          this.showRelay(null);
          for (const node of this.svg.querySelectorAll("[data-drag]")) /** @type {SVGElement} */ (node).style.translate = "";
        };
        if (dx || dy) Promise.resolve(this.handlers.onMove?.(this.movingItems(gesture), dx, dy)).finally(done);
        else done();
      }
    });
    this.svg.addEventListener("pointerleave", () => {
      if (this.ghost) this.overlay.replaceChildren();
    });
    // right-click drops the wire being drawn
    this.svg.addEventListener("contextmenu", (e) => {
      if (this.cancelWire()) e.preventDefault();
    });
    this.svg.addEventListener("dblclick", (e) => {
      if (this.wireMode) return; // two clicks of the wire tool, not an edit
      // pointer capture retargets the event to the svg: find what's under the pointer
      const target = /** @type {Element | null} */ (document.elementFromPoint(e.clientX, e.clientY));
      const label = target?.closest("[data-label]")?.getAttribute("data-label");
      if (label != null) return this.handlers.onEditLabel?.(Number(label));
      const text = target?.closest("[data-text]")?.getAttribute("data-text");
      if (text != null) return this.handlers.onEditText?.(Number(text));
      const ref = target?.closest("[data-ref]")?.getAttribute("data-ref");
      if (ref) this.handlers.onEdit?.(ref);
    });
    this.svg.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const pt = this.toSchematic(e.clientX, e.clientY);
        this.vb = zoomAt(this.vb, pt[0], pt[1], Math.exp(-e.deltaY * 0.001));
        this.apply();
      },
      { passive: false },
    );
  }

  /**
   * Whether a press on `target` grabs the selection of several items: it's on one of them
   * (a part or its pin, a wire or its end's ball, a label, a text block). Then the drag
   * moves them all, instead of starting a wire or moving one wire end (D-113).
   * @param {Element | null} target
   */
  grabsSelection(target) {
    const items = this.selection?.kind === "items" ? this.selection.items : null;
    if (!items || !target) return false;
    const attr = (/** @type {string} */ sel, /** @type {string} */ name) => target.closest(sel)?.getAttribute(name);
    const ref = attr("g.part", "data-ref");
    const wire = attr("line.hit", "data-wire");
    const label = attr("[data-label]", "data-label");
    const text = attr("g.text-block", "data-text");
    const end = attr(".end-hit", "data-at");
    const v = this.view;
    const endSelected = end != null && v && (
      v.wires.some((/** @type {any} */ w, /** @type {number} */ i) => items.wires.includes(i) && (w.from.join() === end || w.to.join() === end))
      || v.parts.some((/** @type {any} */ p) => items.parts.includes(p.ref) && p.pins.some((/** @type {any} */ pin) => pin.pos.join() === end))
      || v.labels.some((/** @type {any} */ lb, /** @type {number} */ i) => items.labels.includes(i) && lb.pos.join() === end));
    return Boolean((ref && items.parts.includes(ref)) || (wire != null && items.wires.includes(Number(wire)))
      || (label != null && items.labels.includes(Number(label))) || (text != null && (items.texts ?? []).includes(Number(text))) || endSelected);
  }

  /**
   * What a drag on a part, text block or selected wire moves: the whole selection when
   * it's in it (or `all`, a press `grabsSelection` found in it).
   * @param {{ref?: string, text?: number, wire?: number, label?: number, all?: boolean}} on @returns {Items}
   */
  movingItems({ ref, text, wire, label, all }) {
    const items = this.selection?.kind === "items" ? this.selection.items : null;
    if (all && items) return items;
    const inside = ref !== undefined ? items?.parts.includes(ref) : wire !== undefined ? items?.wires.includes(wire)
      : label !== undefined ? items?.labels.includes(label) : items?.texts?.includes(/** @type {number} */ (text));
    if (items && inside) return items;
    if (ref !== undefined) return { parts: [ref], wires: [], labels: [] };
    if (label !== undefined) return { parts: [], wires: [], labels: [label] };
    // a wire dragged on its own: only the stretch grabbed moves, the rest of the wire
    // stretching to follow, so a wire can be pulled clear of what it crosses (D-293)
    if (wire !== undefined) return { parts: [], wires: [wire], labels: [] };
    return { parts: [], wires: [], labels: [], texts: [/** @type {number} */ (text)] };
  }

  /**
   * Whether `item` (one thing, from `itemAt`) is in the selection already.
   * @param {{parts?: string[], wires?: number[], labels?: number[], texts?: number[]}} item
   */
  inSelection(item) {
    const sel = this.selection;
    if (!sel) return false;
    if (sel.kind === "items" && sel.items) {
      const items = sel.items;
      return Boolean(item.parts?.some((r) => items.parts.includes(r)) || item.wires?.some((w) => items.wires.includes(w))
        || item.labels?.some((l) => items.labels.includes(l)) || item.texts?.some((t) => (items.texts ?? []).includes(t)));
    }
    if (sel.kind === "part") return item.parts?.[0] === sel.id;
    const wires = sel.run ?? (sel.wire !== undefined ? [sel.wire] : []);
    return (item.wires?.[0] !== undefined && wires.includes(item.wires[0])) || (item.labels?.[0] !== undefined && item.labels[0] === sel.label);
  }

  /**
   * The one thing under the pointer, as items (for Ctrl+click), or null.
   * @param {Element | null} target
   */
  itemAt(target) {
    const text = target?.closest("[data-text]")?.getAttribute("data-text");
    if (text != null) return { texts: [Number(text)] };
    const ref = target?.closest("[data-ref]")?.getAttribute("data-ref");
    if (ref) return { parts: [ref] };
    const label = target?.closest("[data-label]")?.getAttribute("data-label");
    if (label != null) return { labels: [Number(label)] };
    const wire = target?.closest("[data-wire]")?.getAttribute("data-wire");
    if (wire != null) return { wires: [Number(wire)] };
    return null;
  }

  /**
   * @param {Element | null} target
   * @param {boolean} [add] Ctrl (or Shift) held: put the thing clicked in the selection,
   *   or take it out; a click on empty space then changes nothing
   */
  click(target, add = false) {
    const mark = target?.closest("[data-mark]")?.getAttribute("data-mark");
    if (mark != null) return this.handlers.onMark?.(mark);
    if (add) {
      const item = this.itemAt(target);
      if (item) this.handlers.onToggle?.(item);
      return;
    }
    const text = target?.closest("[data-text]")?.getAttribute("data-text");
    if (text != null) return this.handlers.onText?.(Number(text));
    const netNode = target?.closest("[data-net]");
    const net = netNode?.getAttribute("data-net");
    if (net) {
      const wire = netNode?.getAttribute("data-wire");
      const label = netNode?.getAttribute("data-label");
      return this.handlers.onNet(net, {
        ...(wire != null ? { wire: Number(wire) } : {}),
        ...(label != null ? { label: Number(label) } : {}),
      });
    }
    const ref = target?.closest("[data-ref]")?.getAttribute("data-ref");
    if (ref) return this.handlers.onPart(ref);
    // a wire that touches nothing has no net, but can still be selected (to delete it)
    const wire = target?.closest("[data-wire]")?.getAttribute("data-wire");
    if (wire != null) return this.handlers.onNet("", { wire: Number(wire) });
    this.handlers.onEmpty?.();
  }

  /** @param {number} clientX @param {number} clientY @returns {number[]} */
  toSchematic(clientX, clientY) {
    const r = this.svg.getBoundingClientRect();
    return [this.vb.x + ((clientX - r.left) / r.width) * this.vb.w, this.vb.y + ((clientY - r.top) / r.height) * this.vb.h];
  }
}
