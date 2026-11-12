/**
 * Square wire routing on the 10-unit grid (D-063). Pure: no DOM.
 *
 * A wire may not touch anything it isn't meant to connect to, because connectivity joins
 * any point that sits on a wire (a pin, a label, another wire's end: a T). So a route
 * never passes through a part's body, a pin or label (other than its own two ends),
 * another wire's end, or along another wire. It may cross another wire at right angles
 * (crossings don't connect; they're drawn with a hop), but not turn on it.
 *
 * Cost: one per grid step, plus a penalty per bend and per crossing, so the shortest
 * tidy path wins: few bends, few crossings.
 *
 * @typedef {{from: number[], to: number[]}} Segment
 * @typedef {{boxes: number[][], anchors: Set<string>, along: Map<string, number>, ends: Set<string>}} World
 *   `boxes` part bodies [x0, y0, x1, y1] (their insides are off limits); `anchors` pin and
 *   label points; `along` grid points on existing wires → 1 horizontal, 2 vertical, 3 both;
 *   `ends` existing wire ends
 */

const GRID = 10;
const BEND = 3;
const CROSS = 2;
const MARGIN = 300; // how far outside the two ends' box a route may wander
const MAX_VISITS = 60000;
const DIRS = [[GRID, 0], [0, GRID], [-GRID, 0], [0, -GRID]]; // 0 right, 1 down, 2 left, 3 up

/** @param {number[]} p */
export const key = (p) => `${p[0]},${p[1]}`;

/**
 * The world a route must keep clear of.
 * @param {{boxes: number[][], anchors: number[][], wires: Segment[]}} things
 * @returns {World}
 */
export function worldOf({ boxes, anchors, wires }) {
  /** @type {Map<string, number>} */
  const along = new Map();
  const ends = new Set();
  for (const w of wires) {
    ends.add(key(w.from));
    ends.add(key(w.to));
    const horizontal = w.from[1] === w.to[1];
    if (!horizontal && w.from[0] !== w.to[0]) continue; // a slanted wire (old files)
    const bit = horizontal ? 1 : 2;
    const [a, b] = horizontal ? [w.from[0], w.to[0]] : [w.from[1], w.to[1]];
    for (let v = Math.min(a, b); v <= Math.max(a, b); v += GRID) {
      const p = horizontal ? [v, w.from[1]] : [w.from[0], v];
      along.set(key(p), (along.get(key(p)) ?? 0) | bit);
    }
  }
  return { boxes, anchors: new Set(anchors.map(key)), along, ends };
}

/** A small binary heap of [cost, item]. */
class Heap {
  constructor() {
    /** @type {Array<[number, any]>} */
    this.a = [];
  }

  /** @param {number} cost @param {any} item */
  push(cost, item) {
    const a = this.a;
    a.push([cost, item]);
    let i = a.length - 1;
    while (i > 0) {
      const up = (i - 1) >> 1;
      if (a[up][0] <= a[i][0]) break;
      [a[up], a[i]] = [a[i], a[up]];
      i = up;
    }
  }

  pop() {
    const a = this.a;
    const top = a[0];
    const last = /** @type {[number, any]} */ (a.pop());
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const [l, r] = [2 * i + 1, 2 * i + 2];
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]];
        i = m;
      }
    }
    return top;
  }

  get size() {
    return this.a.length;
  }
}

/**
 * The tidiest square path from `a` to `b` (grid points) through `world`, as segments
 * (one per straight run), or null when there's none nearby.
 * @param {number[]} a @param {number[]} b @param {World} world
 * @param {boolean} [horizontal] prefer leaving `a` horizontally (true) or vertically (false)
 * @returns {Segment[] | null}
 */
export function findPath(a, b, world, horizontal) {
  if (a[0] === b[0] && a[1] === b[1]) return [];
  const [ka, kb] = [key(a), key(b)];
  const x0 = Math.min(a[0], b[0]) - MARGIN;
  const x1 = Math.max(a[0], b[0]) + MARGIN;
  const y0 = Math.min(a[1], b[1]) - MARGIN;
  const y1 = Math.max(a[1], b[1]) + MARGIN;
  const inBody = (/** @type {number} */ x, /** @type {number} */ y) =>
    world.boxes.some(([bx0, by0, bx1, by1]) => bx0 < x && x < bx1 && by0 < y && y < by1);
  /**
   * Can a route step onto `p` heading `dir`? @param {number[]} p @param {number} dir
   * @returns {"no" | "free" | "cross"}
   */
  const enter = (p, dir) => {
    const k = key(p);
    if (k === kb) return "free";
    if (p[0] < x0 || p[0] > x1 || p[1] < y0 || p[1] > y1) return "no";
    if (world.anchors.has(k) || world.ends.has(k) || inBody(p[0], p[1])) return "no";
    const on = world.along.get(k) ?? 0;
    if (!on) return "free";
    const mine = dir % 2 === 0 ? 1 : 2; // the direction we'd run along
    return on & mine ? "no" : "cross";
  };
  const h = (/** @type {number[]} */ p) => (Math.abs(p[0] - b[0]) + Math.abs(p[1] - b[1])) / GRID;

  /** @type {Map<string, number>} best cost per point + heading */
  const best = new Map();
  /** @type {Map<string, string | null>} */
  const came = new Map();
  const heap = new Heap();
  const startState = `${ka}|-1`;
  best.set(startState, 0);
  came.set(startState, null);
  heap.push(h(a), { p: a, dir: -1, g: 0, crossing: false, state: startState });
  let visits = 0;
  while (heap.size && visits++ < MAX_VISITS) {
    const { p, dir, g, crossing, state } = heap.pop()[1];
    if (g > (best.get(state) ?? Infinity)) continue;
    if (key(p) === kb) return segmentsOf(state, came);
    for (let d = 0; d < 4; d++) {
      if (dir !== -1 && (d + 2) % 4 === dir) continue; // no doubling back
      if (crossing && d !== dir) continue; // never turn on another wire
      const n = [p[0] + DIRS[d][0], p[1] + DIRS[d][1]];
      const how = enter(n, d);
      if (how === "no") continue;
      let cost = g + 1 + (how === "cross" ? CROSS : 0);
      if (dir !== -1 && d !== dir) cost += BEND;
      if (dir === -1 && horizontal !== undefined && (d % 2 === 0) !== horizontal) cost += BEND;
      const next = `${key(n)}|${d}`;
      if (cost >= (best.get(next) ?? Infinity)) continue;
      best.set(next, cost);
      came.set(next, state);
      heap.push(cost + h(n), { p: n, dir: d, g: cost, crossing: how === "cross", state: next });
    }
  }
  return null;
}

/**
 * Turn the chain of states that reached the goal into straight segments.
 * @param {string} state @param {Map<string, string | null>} came
 * @returns {Segment[]}
 */
function segmentsOf(state, came) {
  /** @type {number[][]} */
  const points = [];
  /** @type {number[]} */
  const dirs = [];
  for (let s = /** @type {string | null} */ (state); s; s = came.get(s) ?? null) {
    const [k, d] = s.split("|");
    points.push(k.split(",").map(Number));
    dirs.push(Number(d));
  }
  points.reverse();
  dirs.reverse();
  /** @type {Segment[]} */
  const out = [];
  let start = points[0];
  for (let i = 1; i < points.length; i++) {
    const last = i === points.length - 1;
    if (last || dirs[i + 1] !== dirs[i]) {
      out.push({ from: start, to: points[i] });
      start = points[i];
    }
  }
  return out;
}

/**
 * True when any of `segments` runs through the inside of a part body.
 * @param {Segment[]} segments @param {number[][]} boxes
 */
export function throughBody(segments, boxes) {
  const inside = (/** @type {number} */ x, /** @type {number} */ y) =>
    boxes.some(([bx0, by0, bx1, by1]) => bx0 < x && x < bx1 && by0 < y && y < by1);
  return segments.some(({ from, to }) => {
    const steps = Math.max(Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1])) / GRID;
    for (let i = 0; i <= steps; i++) {
      const t = steps ? i / steps : 0;
      if (inside(from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t)) return true;
    }
    return false;
  });
}

/**
 * Where wires cross without connecting: a vertical wire passing through a horizontal
 * one's inside (neither ends there). Drawn as a hop on the horizontal wire.
 * @param {Segment[]} wires
 * @returns {Array<{at: number[], wire: number, over: number}>} `wire` the horizontal
 *   wire's index (it gets the hop), `over` the vertical one's
 */
export function crossings(wires) {
  const out = [];
  for (let i = 0; i < wires.length; i++) {
    const h = wires[i];
    if (h.from[1] !== h.to[1] || h.from[0] === h.to[0]) continue;
    const [hx0, hx1] = [Math.min(h.from[0], h.to[0]), Math.max(h.from[0], h.to[0])];
    for (let j = 0; j < wires.length; j++) {
      const v = wires[j];
      if (v.from[0] !== v.to[0] || v.from[1] === v.to[1]) continue;
      const [vy0, vy1] = [Math.min(v.from[1], v.to[1]), Math.max(v.from[1], v.to[1])];
      const [x, y] = [v.from[0], h.from[1]];
      if (hx0 < x && x < hx1 && vy0 < y && y < vy1) out.push({ at: [x, y], wire: i, over: j });
    }
  }
  return out;
}
