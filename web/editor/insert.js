/**
 * A new two-pin part put in series with a part's pin (D-124): the diode arrangements of
 * Bias & headroom's Try changes (a second diode, a resistor). Pure: takes a circuit and
 * returns a new one, no DOM. The server checks the result connects as asked before it's
 * measured (`solum/fixes.py`, `_series_check`).
 */

import { bodyBox, pinOffsets, pinPositions, rotateOffset, textBoxes } from "../schematic/symbols.js";
import { clearSpot } from "./blocks.js";
import { addWires, anchorPoints, GRID, pointOnWire, relay, routeWire, runsFrom, same, splitAtJoins, wireDiff } from "./edit.js";
import { key } from "./router.js";

const REACH = 16 * GRID; // how far from the pin a clear spot is looked for first
const SPOTS = 8; // the nearest clear spots tried there: the tidiest wiring wins
const CROSSING = 20 * GRID; // a new wire crossing another counts as this much more wire

/**
 * @typedef {import("./edit.js").Circuit} Circuit
 * @typedef {import("./edit.js").Wire} Wire
 */

/**
 * Where pin `pin` of two-pin part `ref` is (`at`) and its other pin (`back`); null when
 * `ref` isn't a two-pin part with that pin.
 * @param {Circuit} circuit @param {string} ref @param {string} pin
 * @returns {{at: number[], back: number[]} | null}
 */
function twoPin(circuit, ref, pin) {
  const host = circuit.parts.find((p) => p.ref === ref);
  const pins = host ? pinPositions(host) : {};
  const at = pins[pin];
  const back = Object.entries(pins).find(([name]) => name !== pin)?.[1];
  return at && back && Object.keys(pins).length === 2 ? { at, back } : null;
}

/**
 * `circuit` with two-pin `part` in series with pin `pin` of part `ref`: its pin `near`
 * takes that pin's place on the net, its other pin takes the net. Right beside the pin,
 * along the part's line, with the wires that left the pin re-laid to the new part's far
 * end (and a label on the pin moved there); with no room there, at a clear spot near
 * it, either way round, with a wire back to the pin: of the nearest few, the one whose
 * new wires are shortest, a wire crossing another counting extra (`CROSSING`); failing
 * those, the nearest clear spot further off. Null when it can't go in: the pin touches another
 * part's pin directly (no wire to move off it), or the part isn't a two-pin one.
 * @param {Circuit} circuit @param {string} ref @param {string} pin
 * @param {Record<string, any>} part the new part (its `pos` and `rot` are set here)
 * @param {string} near the new part's pin that joins `ref`'s
 * @param {{spot?: boolean}} [opts] `spot`: with no room beside the pin, use a clear spot
 *   (off: null instead, so another pin can be tried beside first)
 * @returns {Circuit | null}
 */
export function insertInSeries(circuit, ref, pin, part, near, { spot = true } = {}) {
  const ends = twoPin(circuit, ref, pin);
  if (!ends) return null;
  const { at, back } = ends;
  if (circuit.parts.some((p) => p.ref !== ref && Object.values(pinPositions(p)).some((q) => same(q, at)))) return null;
  const lined = onLine(part, near, at, [Math.sign(at[0] - back[0]), Math.sign(at[1] - back[1])]);
  if (!lined) return null;
  const add = (/** @type {Record<string, any>} */ p) => ({ ...circuit, parts: [...circuit.parts, p] });
  const far = (/** @type {Record<string, any>} */ p) => /** @type {number[]} */ (Object.entries(pinPositions(p)).find(([name]) => name !== near)?.[1]);
  if (roomFor(circuit, lined, at)) return relay(circuit, add(lined), [[at, far(lined)]], { joinPins: false });
  if (!spot) return null;
  const wired = (/** @type {Record<string, any>} */ p) => {
    const out = relay(circuit, add(p), [[at, far(p)]], { joinPins: false });
    return addWires(out, routeWire(out, at, pinPositions(p)[near]));
  };
  const turns = [lined.rot ?? 0, ((lined.rot ?? 0) + 90) % 360];
  /** @type {Array<Record<string, any>>} */
  const spots = [];
  for (let dx = -REACH; dx <= REACH; dx += 2 * GRID) {
    for (let dy = -REACH; dy <= REACH; dy += 2 * GRID) {
      for (const rot of turns) {
        const { rot: _rot, ...plain } = lined;
        spots.push({ ...plain, pos: [at[0] + dx, at[1] + dy], ...(rot ? { rot } : {}) }); // no rot 0: the file leaves it out
      }
    }
  }
  const tried = spots
    .sort((a, b) => Math.hypot(a.pos[0] - at[0], a.pos[1] - at[1]) - Math.hypot(b.pos[0] - at[0], b.pos[1] - at[1]))
    .filter((p) => roomFor(circuit, p, null))
    .slice(0, SPOTS)
    .map(wired);
  if (tried.length) return tried.reduce((best, c) => (untidiness(circuit, c) < untidiness(circuit, best) ? c : best));
  const clear = clearSpot(circuit, { ...circuit, parts: [lined], wires: [], labels: [], texts: [] }, lined.pos);
  return same(clear, lined.pos) ? null : wired({ ...lined, pos: clear }); // nowhere clear: null
}

/**
 * Room for a part in series with pin `pin` of part `ref` (D-124): the sheet split by a
 * line across the part's pin, between its body and the pin, and everything past the line
 * moved out `length` (a two-pin part's length), as a schematic editor's "insert space".
 * A part goes by its middle: it moves whole or stays whole. Wires crossing the line get
 * longer; where a pin and what it touched end up on either side of the gap (`ref`'s own
 * pin and what's on it, a part cut by the line), a straight wire across the gap joins
 * them again, so every connection is kept. The server checks that before anything is
 * measured. Null when `ref` isn't a two-pin part or nothing is past the line.
 * @param {Circuit} circuit @param {string} ref @param {string} pin @param {number} [length]
 * @returns {{circuit: Circuit, moved: string[], way: string} | null} `moved`: the parts
 *   that moved, nearest the pin first; `way`: "down", "up", "right" or "left"
 */
export function makeRoom(circuit, ref, pin, length = 4 * GRID) {
  const ends = twoPin(circuit, ref, pin);
  if (!ends) return null;
  const { at, back } = ends;
  const d = [Math.sign(at[0] - back[0]), Math.sign(at[1] - back[1])];
  const cut = [at[0] - (d[0] * GRID) / 2, at[1] - (d[1] * GRID) / 2]; // half a step: nothing on the grid sits on it
  const past = (/** @type {number[]} */ p) => (p[0] - cut[0]) * d[0] + (p[1] - cut[1]) * d[1] > 0;
  const shift = (/** @type {number[]} */ p) => (past(p) ? [p[0] + d[0] * length, p[1] + d[1] * length] : p);
  const moving = new Set(circuit.parts.filter((p) => p.ref !== ref && past(p.pos ?? [0, 0])).map((p) => p.ref));
  const wires = circuit.wires ?? [];
  const labels = circuit.labels ?? [];
  if (!moving.size && !wires.some((w) => past(w.from) || past(w.to)) && !labels.some((lb) => past(lb.pos))) return null;
  // a pin parted from what it touched: a staying part's pin past the line (what's on it
  // moves on), or a moving part's pin before it (what's on it stays)
  /** @type {Array<{ref: string, at: number[]}>} */
  const pinsAt = circuit.parts.flatMap((p) => Object.values(pinPositions(p)).map((q) => ({ ref: p.ref, at: q })));
  const parted = pinsAt.filter(({ ref: r, at: q }) => (moving.has(r) ? !past(q) : past(q)));
  const stretches = parted.flatMap(({ ref: r, at: q }) => {
    const mine = moving.has(r);
    const touched = wires.some((w) => same(w.from, q) || same(w.to, q) || same(pointOnWire(w, q), q))
      || labels.some((lb) => same(lb.pos, q))
      || pinsAt.some((o) => o.ref !== r && same(o.at, q) && moving.has(o.ref) !== mine);
    return touched ? [{ from: q, to: [q[0] + d[0] * length, q[1] + d[1] * length] }] : [];
  });
  const moved = {
    ...circuit,
    parts: circuit.parts.map((p) => (moving.has(p.ref) ? { ...p, pos: shift(p.pos ?? [0, 0]) } : p)),
    wires: wires.map((w) => ({ from: shift(w.from), to: shift(w.to) })),
    labels: labels.map((lb) => ({ ...lb, pos: shift(lb.pos) })),
    texts: (circuit.texts ?? []).map((t) => ({ ...t, pos: shift(t.pos) })),
  };
  // a moved wire already running across the gap there joins them: no second wire over it
  const covered = (/** @type {Wire} */ s) => moved.wires.some((w) => same(pointOnWire(w, s.from), s.from) && same(pointOnWire(w, s.to), s.to));
  const way = d[1] > 0 ? "down" : d[1] < 0 ? "up" : d[0] > 0 ? "right" : "left";
  const away = (/** @type {string} */ r) => {
    const [x, y] = circuit.parts.find((p) => p.ref === r)?.pos ?? [0, 0];
    return Math.hypot(x - at[0], y - at[1]);
  };
  const nearest = [...moving].sort((a, b) => away(a) - away(b)); // named nearest first
  return { circuit: addWires(moved, stretches.filter((s) => !covered(s))), moved: nearest, way };
}

/**
 * How untidy the wires an insertion added are: their length, plus `CROSSING` for each
 * place one crosses a wire it doesn't join.
 * @param {Circuit} before @param {Circuit} after
 */
function untidiness(before, after) {
  const { added } = wireDiff(before.wires ?? [], after.wires ?? []);
  const fresh = new Set(added);
  const others = (after.wires ?? []).filter((w) => !fresh.has(w));
  const length = added.reduce((n, w) => n + Math.abs(w.to[0] - w.from[0]) + Math.abs(w.to[1] - w.from[1]), 0);
  const across = (/** @type {Wire} */ a, /** @type {Wire} */ b) => {
    const [h, v] = a.from[1] === a.to[1] ? [a, b] : [b, a];
    if (h.from[1] !== h.to[1] || v.from[0] !== v.to[0]) return false; // not one across the other
    const [x, y] = [v.from[0], h.from[1]];
    const inside = (/** @type {number} */ t, /** @type {number} */ p, /** @type {number} */ q) => Math.min(p, q) < t && t < Math.max(p, q);
    return inside(x, h.from[0], h.to[0]) && inside(y, v.from[1], v.to[1]);
  };
  return length + CROSSING * added.reduce((n, a) => n + others.filter((b) => across(a, b)).length, 0);
}

/**
 * `part` turned so its pins run along direction `d` (near to far) with pin `near` at `at`;
 * null when no turn does (it isn't a two-pin part).
 * @param {Record<string, any>} part @param {string} near @param {number[]} at @param {number[]} d
 */
function onLine(part, near, at, d) {
  for (const rot of [0, 90, 180, 270]) {
    const off = Object.fromEntries(Object.entries(pinOffsets(part)).map(([name, o]) => [name, rotateOffset(o, rot)]));
    const other = Object.keys(off).find((name) => name !== near);
    if (!off[near] || !other) return null;
    const run = [off[other][0] - off[near][0], off[other][1] - off[near][1]];
    if (Math.sign(run[0]) === d[0] && Math.sign(run[1]) === d[1]) {
      const { rot: _old, ...rest } = part;
      return { ...rest, pos: [at[0] - off[near][0], at[1] - off[near][1]], ...(rot ? { rot } : {}) };
    }
  }
  return null;
}

/** @type {WeakMap<Circuit, {wires: Wire[], anchors: Set<string>, degree: Map<string, number>}>} */
const sheets = new WeakMap();

/**
 * A circuit's wires split where things join them, its pin and label points, and how many
 * wire ends meet at each point: what `roomFor` reads, worked out once per circuit.
 * @param {Circuit} circuit
 */
function sheetOf(circuit) {
  const known = sheets.get(circuit);
  if (known) return known;
  const wires = splitAtJoins(circuit.wires ?? [], anchorPoints(circuit));
  /** @type {Map<string, number>} */
  const degree = new Map();
  for (const w of wires) for (const p of [w.from, w.to]) degree.set(key(p), (degree.get(key(p)) ?? 0) + 1);
  const sheet = { wires, anchors: new Set(anchorPoints(circuit).map(key)), degree };
  sheets.set(circuit, sheet);
  return sheet;
}

/**
 * Whether `part`, placed beside the pin at `at`, is clear of everything but what moves
 * away from that pin (the wires leaving it, up to where they meet something, and a label
 * on it): no pin or wire end within a grid step of its body, nor a label (its symbol)
 * within two, no other wire through it, no other part's body or text over it or its own
 * text. `at` null:
 * a spot away from the pin, where nothing moves.
 * @param {Circuit} circuit @param {Record<string, any>} part @param {number[] | null} at
 */
function roomFor(circuit, part, at) {
  const { wires, anchors, degree } = sheetOf(circuit);
  const runs = at ? runsFrom(wires, at, (p) => anchors.has(key(p)) || degree.get(key(p)) !== 2) : [];
  const leaving = new Set(runs.flatMap((r) => r.wires));
  const kept = wires.filter((_w, i) => !leaving.has(i));
  const body = bodyBox(part);
  const near = [body[0] - GRID, body[1] - GRID, body[2] + GRID, body[3] + GRID];
  const inBox = (/** @type {number[]} */ p, /** @type {number[]} */ b) => b[0] <= p[0] && p[0] <= b[2] && b[1] <= p[1] && p[1] <= b[3];
  const inside = (/** @type {number[]} */ p) => body[0] < p[0] && p[0] < body[2] && body[1] < p[1] && p[1] < body[3];
  // where the leaving wires end (a rail the diode's lead met) may sit close: the wire
  // re-laid to the far pin ends there; a part fits into a lead longer than itself
  const ends = new Set(runs.map((r) => key(r.end)));
  const off = (/** @type {number[]} */ p) => !at || !same(p, at);
  const points = [
    ...circuit.parts.flatMap((p) => [p.pos ?? [0, 0], ...Object.values(pinPositions(p))]),
    ...kept.flatMap((w) => [w.from, w.to]),
  ].filter(off);
  if (points.some((p) => (ends.has(key(p)) ? inside(p) : inBox(p, near)))) return false;
  const wide = [body[0] - 2 * GRID, body[1] - 2 * GRID, body[2] + 2 * GRID, body[3] + 2 * GRID];
  if ((circuit.labels ?? []).some((lb) => off(lb.pos) && !ends.has(key(lb.pos)) && inBox(lb.pos, wide))) return false;
  // a wire into the body; one along its edge (a rail the far pin lands on) is fine
  const crosses = (/** @type {Wire} */ w) => Math.max(w.from[0], w.to[0]) > body[0] && Math.min(w.from[0], w.to[0]) < body[2]
    && Math.max(w.from[1], w.to[1]) > body[1] && Math.min(w.from[1], w.to[1]) < body[3]
    || [w.from, w.to].some(inside);
  if (kept.some(crosses)) return false;
  const overlaps = (/** @type {number[]} */ b) => b[0] < body[2] && body[0] < b[2] && b[1] < body[3] && body[1] < b[3];
  const meets = (/** @type {number[]} */ a, /** @type {number[]} */ b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  const words = (/** @type {Record<string, any>} */ p) => textBoxes(p, String(p.value ?? p.model ?? ""));
  const own = words(part);
  return !circuit.parts.some((p) => [bodyBox(p), ...words(p)].some((b) => overlaps(b) || own.some((t) => meets(t, b))));
}
