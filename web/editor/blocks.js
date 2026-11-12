/**
 * Blocks in the editor (D-010, D-072): choosing items with a box, taking a selection out
 * as a block, marking its ports, and pasting a block into a circuit (paste-flatten).
 * Pure, like edit.js: each function returns new objects and never touches the DOM.
 *
 * Paste-flatten copies the block's parts in with fresh refs (R1 → the next free R),
 * moves it to where it's dropped (or the nearest spot where it touches nothing), keeps the supply rails and GND (so they connect by
 * themselves), and renames every other label to a name the circuit doesn't use yet, so
 * nothing joins a net by accident: the ports arrive as labels to wire up. Dropped on a
 * wire, the block is spliced in: the wire goes and its two ends are wired to the block's
 * in and out ports.
 *
 * @typedef {import("./edit.js").Circuit} Circuit
 * @typedef {import("./edit.js").Wire} Wire
 * @typedef {{parts: string[], wires: number[], labels: number[], texts?: number[]}} Items
 */

import { pinPositions } from "../schematic/symbols.js";
import { SUPPLIES, addWires, isChipPart, mainRail, nextRef, pointOnWire, routeWire, same, snap, snapPoint, withChips } from "./edit.js";
import { listFiles } from "./files.js";
import { key } from "./router.js";

/** Part types a circuit has one of: a paste leaves them out when the circuit has one. */
const ONE_PER_CIRCUIT = new Set(["guitar", "amp", "dcjack"]);

/** A circuit's guitar input and amp (D-146): its own, so never deleted from a circuit and
 * never saved into a block. */
const SHEET_ENDS = new Set(["guitar", "amp"]);

/**
 * The refs of a circuit's guitar input and amp, which can't be deleted (D-146); none in a
 * block (`template`), which shouldn't have them.
 * @param {Circuit} circuit @returns {Set<string>}
 */
export function fixedRefs(circuit) {
  if (circuit.template) return new Set();
  return new Set(circuit.parts.filter((p) => SHEET_ENDS.has(p.type)).map((p) => p.ref));
}

/**
 * `items` without the guitar input and amp, for Save as block (D-146): a block is what
 * goes between them. The wires that end on their pins stay behind too.
 * @param {Circuit} circuit @param {Items} items @returns {Items}
 */
export function withoutEnds(circuit, items) {
  const ends = circuit.parts.filter((p) => SHEET_ENDS.has(p.type));
  const pins = new Set(ends.flatMap((p) => Object.values(pinPositions(p)).map(String)));
  const refs = new Set(ends.map((p) => p.ref));
  const wires = circuit.wires ?? [];
  return {
    ...items,
    parts: items.parts.filter((r) => !refs.has(r)),
    wires: items.wires.filter((i) => !pins.has(String(wires[i]?.from)) && !pins.has(String(wires[i]?.to))),
  };
}

/** Nets that connect by name across the whole sheet: the supplies and ground. */
const GLOBAL = new Set([...Object.keys(SUPPLIES), "GND"]);

/** @param {string} net */
export const isGlobal = (net) => GLOBAL.has(net);

/** @param {number[]} p @param {number[]} box [x1, y1, x2, y2] in any order */
function inside(p, box) {
  const [x1, x2] = [Math.min(box[0], box[2]), Math.max(box[0], box[2])];
  const [y1, y2] = [Math.min(box[1], box[3]), Math.max(box[1], box[3])];
  return x1 <= p[0] && p[0] <= x2 && y1 <= p[1] && p[1] <= y2;
}

/**
 * What a box drawn on the sheet takes in: parts whose position is inside it, wires with
 * both ends inside, labels and text blocks inside (by their corner).
 * @param {Circuit} circuit @param {number[]} box [x1, y1, x2, y2]
 * @returns {Items}
 */
export function itemsInBox(circuit, box) {
  return {
    parts: circuit.parts.filter((p) => inside(p.pos ?? [0, 0], box)).map((p) => p.ref),
    wires: (circuit.wires ?? []).flatMap((w, i) => (inside(w.from, box) && inside(w.to, box) ? [i] : [])),
    labels: (circuit.labels ?? []).flatMap((lb, i) => (inside(lb.pos, box) ? [i] : [])),
    texts: (circuit.texts ?? []).flatMap((t, i) => (inside(t.pos, box) ? [i] : [])),
  };
}

/** @param {Circuit} circuit @returns {Items} */
export const allItems = (circuit) => ({
  parts: circuit.parts.map((p) => p.ref),
  wires: (circuit.wires ?? []).map((_w, i) => i),
  labels: (circuit.labels ?? []).map((_l, i) => i),
  texts: (circuit.texts ?? []).map((_t, i) => i),
});

const KINDS = /** @type {const} */ (["parts", "wires", "labels", "texts"]);

/**
 * `items` with each thing in `item` taken out if it's there, put in if it isn't
 * (Ctrl+click on one part, wire, label or text block).
 * @param {Items} items @param {Partial<Items>} item @returns {Items}
 */
export function toggleItems(items, item) {
  /** @type {any} */
  const out = { parts: [], wires: [], labels: [], texts: [] };
  for (const kind of KINDS) {
    const have = /** @type {any[]} */ (items[kind] ?? []);
    const flip = /** @type {any[]} */ (item[kind] ?? []);
    out[kind] = [...have.filter((x) => !flip.includes(x)), ...flip.filter((x) => !have.includes(x))];
  }
  return out;
}

/**
 * Everything in `a` and in `b` (a box drawn with Ctrl held adds to the selection).
 * @param {Items} a @param {Partial<Items>} b @returns {Items}
 */
export function addItems(a, b) {
  /** @type {any} */
  const out = {};
  for (const kind of KINDS) out[kind] = [...new Set([...(a[kind] ?? []), ...(b[kind] ?? [])])];
  return out;
}

/** @param {Items | null | undefined} items */
export const isEmpty = (items) => !items || !(items.parts.length + items.wires.length + items.labels.length + (items.texts?.length ?? 0));

/**
 * Take selected items out as a block of their own (copy, or "Save as block"). Wires
 * between two selected parts' pins come along even when not selected; a selected label
 * that touches nothing that came along is left behind. A selected pin on
 * a supply or GND keeps that connection: it gets a label of its own unless a selected
 * wire or label already reaches it. The selected parts carry their notes; the notes on
 * the nets its labels name and the selected text blocks come along.
 * @param {Circuit} circuit
 * @param {{parts: any[]}} view the circuit's view (each part's pins with their nets)
 * @param {Items} items
 * @returns {Circuit}
 */
export function extract(circuit, view, items) {
  const refs = new Set(withChips(circuit, items.parts)); // half a chip takes the chip (D-140)
  const parts = circuit.parts.filter((p) => refs.has(p.ref));
  const pinKeys = new Set(parts.flatMap((p) => Object.values(pinPositions(p)).map(String)));
  const chosen = new Set(items.wires);
  const wires = (circuit.wires ?? []).filter((w, i) => chosen.has(i) || (pinKeys.has(String(w.from)) && pinKeys.has(String(w.to))));
  // a label comes along only if it's on something that does (a pin or a wire)
  const onWires = (/** @type {number[]} */ q) => wires.some((w) => same(pointOnWire(w, q), q));
  const labels = (circuit.labels ?? []).filter((lb, i) => items.labels.includes(i) && (pinKeys.has(String(lb.pos)) || onWires(lb.pos)));
  const reached = new Set([...wires.flatMap((w) => [String(w.from), String(w.to)]), ...labels.map((lb) => String(lb.pos))]);
  for (const vp of view.parts) {
    if (!refs.has(vp.ref)) continue;
    for (const pin of vp.pins) {
      if (pin.net && isGlobal(pin.net) && !reached.has(String(pin.pos))) {
        labels.push({ net: pin.net, pos: pin.pos });
        reached.add(String(pin.pos));
      }
    }
  }
  const used = new Set(labels.map((lb) => lb.net));
  const rails = Object.fromEntries(Object.entries(circuit.power?.rails ?? {}).filter(([n]) => used.has(n)));
  const netNotes = Object.fromEntries(Object.entries(circuit.net_notes ?? {}).filter(([n]) => used.has(n)));
  const texts = (circuit.texts ?? []).filter((_t, i) => (items.texts ?? []).includes(i));
  return {
    schema: circuit.schema, id: "selection", name: "Selection", power: { rails }, parts, wires, labels,
    ...(texts.length ? { texts } : {}), ...(Object.keys(netNotes).length ? { net_notes: netNotes } : {}),
  };
}

/**
 * Mark a port on a block taken out of `view`'s circuit: the net clicked becomes a port
 * called `name`. A net with a label in the block keeps it; otherwise a label `name` goes
 * on one of the block's pins on that net. Throws with a plain message.
 * @param {Circuit} block from `extract` @param {{parts: any[]}} view @param {string} net
 * @param {string} name
 * @returns {Circuit}
 */
export function markPort(block, view, net, name) {
  name = name.trim();
  if (!name || /[.\s]/.test(name)) throw new Error("Give the port a name without spaces or dots, like in or out.");
  if (isGlobal(net)) throw new Error(`${net} is a supply or ground: blocks connect to it by themselves, no port needed.`);
  const ports = { ...(block.ports ?? {}) };
  if (name in ports) throw new Error(`There's already a port called ${name}.`);
  const labelled = (block.labels ?? []).find((lb) => lb.net === net);
  if (labelled) return { ...block, ports: { ...ports, [name]: net } };
  if ((block.labels ?? []).some((lb) => lb.net === name)) throw new Error(`${name} already names another net in this block. Pick another name.`);
  const refs = new Set(block.parts.map((p) => p.ref));
  const pin = view.parts.filter((p) => refs.has(p.ref)).flatMap((p) => p.pins).find((p) => p.net === net);
  if (!pin) throw new Error("That net doesn't touch the selected parts. Click a wire or pin of the block.");
  return { ...block, labels: [...(block.labels ?? []), { net: name, pos: pin.pos }], ports: { ...ports, [name]: name } };
}

/**
 * A ref's letters: R12 → R, VR1 → VR, IN → IN (no number: a "bare" ref).
 * @param {string} ref
 */
const prefixOf = (ref) => ref.replace(/\d+$/, "");

/**
 * The points a block's drawing covers.
 * @param {Circuit} block
 */
const pointsOf = (block) => [
  ...block.parts.map((p) => p.pos ?? [0, 0]),
  ...(block.wires ?? []).flatMap((w) => [w.from, w.to]),
  ...(block.labels ?? []).map((lb) => lb.pos),
  ...(block.texts ?? []).map((t) => t.pos),
];

/**
 * The point of a block that lands where it's dropped: the middle of its drawing, on
 * the grid (also where the placing ghost is held).
 * @param {Circuit} block @returns {number[]}
 */
export function blockAnchor(block) {
  const pts = pointsOf(block);
  if (!pts.length) return [0, 0];
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [snap((Math.min(...xs) + Math.max(...xs)) / 2), snap((Math.min(...ys) + Math.max(...ys)) / 2)];
}

const CLEARANCE = 20; // room kept around a pasted block
const SEARCH = 3000; // how far to look for a clear spot

/**
 * The box a block's drawing covers once its anchor is at `at`, padded by CLEARANCE.
 * @param {Circuit} block @param {number[]} at
 */
function boxAt(block, at) {
  const [ax, ay] = blockAnchor(block);
  const pts = pointsOf(block).map((p) => [p[0] - ax + at[0], p[1] - ay + at[1]]);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs) - CLEARANCE, Math.min(...ys) - CLEARANCE, Math.max(...xs) + CLEARANCE, Math.max(...ys) + CLEARANCE];
}

/**
 * True when a segment a-b (or a point, a = b) meets the box.
 * @param {number[]} a @param {number[]} b @param {number[]} box
 */
function meets(a, b, box) {
  const [x1, y1, x2, y2] = box;
  return Math.max(a[0], b[0]) >= x1 && Math.min(a[0], b[0]) <= x2 && Math.max(a[1], b[1]) >= y1 && Math.min(a[1], b[1]) <= y2;
}

/**
 * The drawing's points joined into nets: wire ends, labels, `points` (pins), and any of
 * them part-way along a wire; with `byName`, labels with the same name too. Returns the
 * net (a root point's key) of a point.
 * @param {Wire[]} wires @param {Array<{net: string, pos: number[]}>} labels
 * @param {number[][]} [points] @param {boolean} [byName]
 * @returns {(p: number[]) => string}
 */
function drawnNets(wires, labels, points = [], byName = false) {
  /** @type {Map<string, string>} */
  const up = new Map();
  const find = (/** @type {string} */ k) => {
    while (up.has(k) && up.get(k) !== k) k = /** @type {string} */ (up.get(k));
    return k;
  };
  const join = (/** @type {string} */ a, /** @type {string} */ b) => up.set(find(a), find(b));
  const all = [...wires.flatMap((w) => [w.from, w.to]), ...labels.map((lb) => lb.pos), ...points];
  for (const w of wires) {
    join(key(w.from), key(w.to));
    for (const p of all) if (same(pointOnWire(w, p), p)) join(key(p), key(w.from));
  }
  if (byName) {
    /** @type {Map<string, string>} */
    const first = new Map();
    for (const lb of labels) {
      const there = first.get(lb.net);
      if (there) join(key(lb.pos), there);
      else first.set(lb.net, key(lb.pos));
    }
  }
  return (p) => find(key(p));
}

/**
 * Whether wires and labels put two differently named labels on one net (GND and V18, IN
 * and OUT). Only the drawing's points count: wire ends, labels, and points part-way along
 * a wire. The server's connectivity check says the same once the circuit is saved; this
 * is just what a drop needs to know first (D-189).
 * @param {Wire[]} wires @param {Array<{net: string, pos: number[]}>} labels
 */
function namesClash(wires, labels) {
  const netOf = drawnNets(wires, labels);
  /** @type {Map<string, string>} */
  const named = new Map();
  for (const lb of labels) {
    const root = netOf(lb.pos);
    if ((named.get(root) ?? lb.net) !== lb.net) return true;
    named.set(root, lb.net);
  }
  return false;
}

/**
 * Whether a dropped block's pins, landing on the sheet, would join two of the block's own
 * nets (a resistor with both pins on one wire, 9d3): the sheet's wires, pins and labels
 * (same name, same net) with the block's, against the block's alone.
 * @param {{wires: Wire[], labels: Array<{net: string, pos: number[]}>, pins: number[][]}} sheet
 * @param {{wires: Wire[], labels: Array<{net: string, pos: number[]}>, pins: number[][]}} block
 */
function joinsOwnNets(sheet, block) {
  const own = drawnNets(block.wires, block.labels, block.pins, true);
  const both = drawnNets([...sheet.wires, ...block.wires], [...sheet.labels, ...block.labels], [...sheet.pins, ...block.pins], true);
  /** @type {Map<string, string>} */
  const seen = new Map(); // a net of the two together → the block's own net found on it
  for (const pin of block.pins) {
    const net = both(pin);
    if ((seen.get(net) ?? own(pin)) !== own(pin)) return true;
    seen.set(net, own(pin));
  }
  return false;
}

/**
 * Whether a dropped block's supply or ground (a V+, V- or GND label of its own) would land
 * on a net of the sheet that isn't that same supply: a battery's ground drawn along a
 * signal wire would short it. Sheet nets are judged by their labels, so a sheet net that
 * already carries that supply's label (its ground symbols) is fine.
 * @param {{wires: Wire[], labels: Array<{net: string, pos: number[]}>, pins: number[][]}} sheet
 * @param {{wires: Wire[], labels: Array<{net: string, pos: number[]}>, pins: number[][]}} block
 */
function shortsToSupply(sheet, block) {
  const supplies = block.labels.filter((lb) => isGlobal(lb.net));
  if (!supplies.length) return false;
  const own = drawnNets(sheet.wires, sheet.labels, sheet.pins, true);
  /** @type {Map<string, Set<string>>} a sheet net → the names its labels give it */
  const names = new Map();
  for (const lb of sheet.labels) names.set(own(lb.pos), new Set([...(names.get(own(lb.pos)) ?? []), lb.net]));
  const both = drawnNets([...sheet.wires, ...block.wires], [...sheet.labels, ...block.labels], [...sheet.pins, ...block.pins], true);
  const points = [...sheet.pins, ...sheet.labels.map((lb) => lb.pos), ...sheet.wires.flatMap((w) => [w.from, w.to])];
  for (const lb of supplies) {
    const net = both(lb.pos);
    if (points.some((p) => both(p) === net && !names.get(own(p))?.has(lb.net))) return true;
  }
  return false;
}

/**
 * Whether two straight wires lie along each other for more than a point: one drawn over
 * the other, not a touch at an end or a crossing.
 * @param {Wire} a @param {Wire} b
 */
function runsAlong(a, b) {
  for (const k of [0, 1]) { // 0: both vertical on one x; 1: both horizontal on one y
    if (a.from[k] !== a.to[k] || b.from[k] !== b.to[k] || a.from[k] !== b.from[k]) continue;
    const o = 1 - k;
    const from = Math.max(Math.min(a.from[o], a.to[o]), Math.min(b.from[o], b.to[o]));
    const to = Math.min(Math.max(a.from[o], a.to[o]), Math.max(b.from[o], b.to[o]));
    if (to > from) return true;
  }
  return false;
}

/**
 * Whether a block dropped at `at` is put there to join the sheet (the user, D-164: it
 * jumped away instead): a pin, label or wire end of it lands right on a pin, label or
 * wire of the sheet, and everything else of the sheet stays out of its drawing. Never
 * when the join would put two differently named labels on one net (D-189), or the block's
 * supply or ground on a sheet net that isn't that supply (D-270), or when a wire of the
 * block would lie along a wire of the sheet (D-285: a join is an end touching, not a wire
 * drawn over another).
 * @param {Circuit} host @param {Circuit} block @param {number[]} at @param {number} [skip]
 */
function joinsAt(host, block, at, skip) {
  const [ax, ay] = blockAnchor(block);
  const move = (/** @type {number[]} */ p) => [p[0] - ax + at[0], p[1] - ay + at[1]];
  const ends = [
    ...block.parts.flatMap((p) => Object.values(pinPositions(p))),
    ...(block.labels ?? []).map((lb) => lb.pos),
    ...(block.wires ?? []).flatMap((w) => [w.from, w.to]),
  ].map(move);
  const wires = (host.wires ?? []).filter((_w, i) => i !== skip);
  const isEnd = (/** @type {number[]} */ p) => ends.some((e) => e[0] === p[0] && e[1] === p[1]);
  const onWire = (/** @type {import("./edit.js").Wire} */ w) => ends.find((e) => same(pointOnWire(w, e), e));
  const hostPoints = [...host.parts.flatMap((p) => Object.values(pinPositions(p))), ...(host.labels ?? []).map((lb) => lb.pos)];
  if (!hostPoints.some(isEnd) && !wires.some(onWire)) return false;
  const drawn = [...pointsOf(block).map(move), ...ends]; // its drawing, pins too, unpadded
  const xs = drawn.map((p) => p[0]);
  const ys = drawn.map((p) => p[1]);
  const box = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  if (host.parts.some((p) => meets(p.pos ?? [0, 0], p.pos ?? [0, 0], box))) return false; // a body under it
  if (hostPoints.some((p) => meets(p, p, box) && !isEnd(p))) return false; // a pin it'd touch by accident
  if (!wires.every((w) => !meets(w.from, w.to, box) || onWire(w))) return false;
  const blockWires = (block.wires ?? []).map((w) => ({ from: move(w.from), to: move(w.to) }));
  if (blockWires.some((b) => wires.some((w) => runsAlong(b, w)))) return false;
  const blockLabels = (block.labels ?? []).map((lb) => ({ net: lb.net, pos: move(lb.pos) }));
  if (namesClash([...wires, ...blockWires], [...(host.labels ?? []), ...blockLabels])) return false;
  const blockPins = block.parts.flatMap((p) => Object.values(pinPositions(p))).map(move);
  const hostPins = host.parts.flatMap((p) => Object.values(pinPositions(p)));
  const sheet = { wires, labels: host.labels ?? [], pins: hostPins };
  const mine = { wires: blockWires, labels: blockLabels, pins: blockPins };
  return !joinsOwnNets(sheet, mine) && !shortsToSupply(sheet, mine);
}

/**
 * Where a block dropped at `at` can go without touching anything on the sheet (so it
 * never joins a net by landing on it): `at` when that's clear, or when it's dropped to
 * join (`joinsAt`), else the nearest clear grid point. `skip`: a wire to ignore (the one
 * it's spliced into).
 * @param {Circuit} host @param {Circuit} block @param {number[]} at @param {number} [skip]
 * @returns {number[]}
 */
export function clearSpot(host, block, at, skip) {
  [at] = [snapPoint(at)];
  if (joinsAt(host, block, at, skip)) return at;
  const things = [
    ...host.parts.flatMap((p) => [p.pos ?? [0, 0], ...Object.values(pinPositions(p))]).map((p) => [p, p]),
    ...(host.labels ?? []).map((lb) => [lb.pos, lb.pos]),
    ...(host.wires ?? []).filter((_w, i) => i !== skip).map((w) => [w.from, w.to]),
  ];
  const clear = (/** @type {number[]} */ p) => !things.some(([a, b]) => meets(a, b, boxAt(block, p)));
  for (let r = 0; r <= SEARCH; r += 2 * CLEARANCE) {
    // the ring at distance r, nearest points first
    const ring = [];
    for (let d = -r; d <= r; d += 2 * CLEARANCE) ring.push([d, -r], [d, r], [-r, d], [r, d]);
    ring.sort((p, q) => Math.hypot(p[0], p[1]) - Math.hypot(q[0], q[1]));
    for (const [dx, dy] of ring) if (clear([at[0] + dx, at[1] + dy])) return [at[0] + dx, at[1] + dy];
  }
  return at;
}

/**
 * The block's ports a wire is spliced through: `in` and `out` when it has them, else
 * its first two ports that aren't supplies. Null when it has fewer than two.
 * @param {Circuit} block @returns {[string, string] | null}
 */
export function splicePorts(block) {
  const ports = Object.keys(block.ports ?? {}).filter((p) => !isGlobal(block.ports[p]));
  if (ports.includes("in") && ports.includes("out")) return ["in", "out"];
  return ports.length >= 2 ? [ports[0], ports[1]] : null;
}

/**
 * Paste a block into a circuit (paste-flatten). Returns the new circuit, the refs the
 * block's parts got (block ref → new ref), the net each port landed on, the parts
 * left out (a guitar input or amp when the circuit already has one), and where its
 * wires, labels and text blocks went (`placed`, to select them: `itemsAt`).
 * @param {Circuit} host @param {Circuit} block
 * The block's parts are copied: nothing in the circuit links back to the block (D-075).
 * @param {{at: number[], splice?: number}} opts `at`: where the block's anchor goes (or
 *   the nearest clear spot, `clearSpot`); `splice`: a wire of `host` to splice into
 * @returns {{circuit: Circuit, refs: Record<string, string>, ports: Record<string, string>, skipped: string[], placed: {wires: Wire[], spots: number[][], texts: number[]}}}
 */
export function pasteBlock(host, block, { at, splice }) {
  const hostTypes = new Set(host.parts.map((p) => p.type));
  const skipped = block.parts.filter((p) => ONE_PER_CIRCUIT.has(p.type) && hostTypes.has(p.type)).map((p) => p.ref);
  if (skipped.length) block = { ...block, parts: block.parts.filter((p) => !skipped.includes(p.ref)) };
  // refs: the next free one per prefix, in the block's order
  /** @type {Record<string, string>} */
  const refs = {};
  let taken = { ...host, parts: [...host.parts] };
  for (const p of block.parts) {
    if (refs[p.ref]) continue; // a chip's other half, numbered with it
    if (isChipPart(p) || (p.type === "switch" && p.pole) || (p.type === "pot" && p.gang)) {
      // a chip (IC1A, IC1B), a switch's poles (SW1A…) or a dual pot's gangs (VR1A, VR1B)
      // take one new number (D-140, D-143, D-217)
      const chip = p.ref.slice(0, -1);
      const ref = nextRef(taken, prefixOf(chip));
      const letters = block.parts.filter((q) => q.ref.slice(0, -1) === chip && (isChipPart(q) || q.pole || q.gang)).map((q) => q.ref.slice(-1));
      for (const x of letters) refs[`${chip}${x}`] = `${ref}${x}`;
      taken = { ...taken, parts: [...taken.parts, ...letters.map((x) => ({ ref: `${ref}${x}` }))] };
      continue;
    }
    const prefix = prefixOf(p.ref);
    const ref = nextRef(taken, prefix, prefix === p.ref);
    refs[p.ref] = ref;
    taken = { ...taken, parts: [...taken.parts, { ref }] };
  }
  const pin = (/** @type {string} */ name) => {
    const [ref, ...rest] = name.split(".");
    return refs[ref] && rest.length ? [refs[ref], ...rest].join(".") : name;
  };

  // nets: supplies and GND keep their names, every other label gets one not used here
  const usedNets = new Set([...(host.labels ?? []).map((lb) => lb.net), ...Object.keys(host.power?.rails ?? {})]);
  /** @type {Record<string, string>} */
  const nets = {};
  for (const net of new Set((block.labels ?? []).map((lb) => lb.net))) {
    if (isGlobal(net)) continue;
    let name = net;
    for (let n = 2; usedNets.has(name); n++) name = `${net}_${n}`;
    nets[net] = name;
    usedNets.add(name);
  }
  const net = (/** @type {string} */ n) => nets[n] ?? n;

  const [ax, ay] = blockAnchor(block);
  // placed with the names it will have, so a join is judged on those (D-189)
  const named = { ...block, labels: (block.labels ?? []).map((lb) => ({ ...lb, net: net(lb.net) })) };
  const [tx, ty] = clearSpot(host, named, at, splice);
  const move = (/** @type {number[]} */ p) => [p[0] - ax + tx, p[1] - ay + ty];
  const parts = block.parts.map((p) => {
    const q = { ...p, ref: refs[p.ref], pos: move(p.pos ?? [0, 0]) };
    if (q.bias_target) q.bias_target = { ...q.bias_target, node: net(pin(q.bias_target.node)) };
    return q;
  });
  const wires = (block.wires ?? []).map((w) => ({ from: move(w.from), to: move(w.to) }));
  let labels = (block.labels ?? []).map((lb) => ({ ...lb, net: net(lb.net), pos: move(lb.pos) })); // its turn too
  const ports = Object.fromEntries(Object.entries(block.ports ?? {}).map(([k, v]) => [k, net(v)]));

  // the parts carry their own notes; net notes follow the nets' new names, and a block's
  // description becomes a general note (never rewritten: it cites the source's refs)
  const netNotes = { ...(host.net_notes ?? {}) };
  for (const [name, text] of Object.entries(block.net_notes ?? {})) netNotes[net(pin(name))] = text;
  const fromBlock = blockNote(block, refs);

  // supplies the block uses that the circuit hasn't got yet come along
  const rails = { ...(host.power?.rails ?? {}) };
  const usedRails = new Set(labels.map((lb) => lb.net));
  for (const [name, volts] of Object.entries(block.power?.rails ?? {})) {
    if (usedRails.has(name) && !(name in rails)) {
      const main = mainRail(host);
      rails[name] = main ? Math.sign(volts) * Math.abs(main[1]) : volts;
    }
  }

  /** @type {Circuit} */
  let out = {
    ...host,
    power: { ...host.power, rails },
    parts: [...host.parts, ...parts],
    wires: [...(host.wires ?? []), ...wires],
    labels: [...(host.labels ?? []), ...labels],
    ...(block.texts?.length ? { texts: [...(host.texts ?? []), ...block.texts.map((t) => ({ ...t, pos: move(t.pos) }))] } : {}),
    ...(Object.keys(netNotes).length ? { net_notes: netNotes } : {}),
    ...(fromBlock ? { notes: [...(host.notes ?? []), fromBlock] } : {}),
  };
  if (splice !== undefined) out = spliceInto(out, host, splice, block, ports);
  const texts = (block.texts ?? []).map((_, i) => (host.texts?.length ?? 0) + i);
  return { circuit: out, refs, ports, skipped, placed: { wires, spots: labels.map((lb) => lb.pos), texts } };
}

/** Characters in a note's title and text (`schema.TITLE_MAX`, `schema.NOTE_MAX`). */
export const NOTE_TITLE_MAX = 100;
export const NOTE_MAX = 5000;

/**
 * The general note a dropped block adds (9d4): its whole description, titled with where
 * it came from, ending with a line naming the refs the paste changed (the description
 * itself is never rewritten). Null for a block with no description (a copied selection).
 * @param {Circuit} block @param {Record<string, string>} refs block ref → ref in the circuit
 * @returns {{title: string, text: string} | null}
 */
export function blockNote(block, refs) {
  const description = (block.description ?? "").trim();
  if (!description) return null;
  const moved = Object.entries(refs).filter(([from, to]) => from !== to).map(([from, to]) => `${from} \u2192 ${to}`);
  const tail = moved.length ? `\n\nPasted with new refs: ${moved.join(", ")}` : "";
  return {
    title: `From block: ${block.name}`.slice(0, NOTE_TITLE_MAX),
    text: description.slice(0, NOTE_MAX - tail.length) + tail,
  };
}

/**
 * Splice a just-pasted block into wire `index` of the circuit before the paste: the wire
 * goes, and its ends are wired to the block's in and out port labels (which go too).
 * Each end goes to the nearer port. Throws when the block has no two ports.
 * @param {Circuit} pasted @param {Circuit} host @param {number} index @param {Circuit} block
 * @param {Record<string, string>} ports port → net in `pasted`
 */
function spliceInto(pasted, host, index, block, ports) {
  const names = splicePorts(block);
  const wire = (host.wires ?? [])[index];
  if (!wire) return pasted;
  if (!names) throw new Error(`${block.name} has no in and out ports, so it can't go into a wire. Drop it beside the wire instead.`);
  const hostLabels = (host.labels ?? []).length;
  const find = (/** @type {string} */ port) => (pasted.labels ?? []).findIndex((lb, i) => i >= hostLabels && lb.net === ports[port]);
  const [inAt, outAt] = names.map(find);
  if (inAt < 0 || outAt < 0) throw new Error(`${block.name}'s ports have no label to wire to.`);
  const labels = /** @type {import("./edit.js").Label[]} */ (pasted.labels);
  const [pIn, pOut] = [labels[inAt].pos, labels[outAt].pos];
  const d = (/** @type {number[]} */ a, /** @type {number[]} */ b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
  const [a, b] = d(wire.from, pIn) + d(wire.to, pOut) <= d(wire.to, pIn) + d(wire.from, pOut) ? [wire.from, wire.to] : [wire.to, wire.from];
  let out = {
    ...pasted,
    wires: (pasted.wires ?? []).filter((_w, i) => i !== index),
    labels: labels.filter((_l, i) => i !== inAt && i !== outAt),
  };
  for (const [from, to] of [[a, pIn], [pOut, b]]) if (!same(from, to)) out = addWires(out, routeWire(out, from, to));
  return out;
}

/**
 * The block list as the Blocks dialog shows it: My blocks, then Core blocks, each listed
 * by `listFiles` (by name, newest major first; only current versions with `currentOnly`).
 * `show` says which sections are on; at least one always is (with both off, both show).
 * @template {{name: string, layer: string, version?: string, current?: boolean}} E
 * @param {E[]} entries @param {{user: boolean, core: boolean}} show @param {"az" | "za"} order
 * @param {boolean} [currentOnly]
 * @returns {Array<{layer: "user" | "core", title: string, rows: E[]}>}
 */
export function blockSections(entries, show, order, currentOnly = false) {
  const none = !show.user && !show.core;
  /** @type {Array<["user" | "core", string]>} */
  const layers = [["user", "My blocks"], ["core", "Core blocks"]];
  return layers.filter(([layer]) => none || show[layer]).map(([layer, title]) => ({ layer, title, rows: listFiles(entries.filter((e) => e.layer === layer), order, currentOnly) }));
}
