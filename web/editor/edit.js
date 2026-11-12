/**
 * Editing operations on circuit JSON. Pure: each takes a circuit and returns a new one
 * (the input is never changed), so undo can keep the old object. No DOM. The server
 * validates every result (`POST /api/view`); nothing here re-checks the schema.
 *
 * @typedef {{schema: number, id: string, name: string, parts: any[], wires?: Wire[],
 *   labels?: Label[], texts?: TextBlock[], notes?: Note[], net_notes?: Record<string, string>, probes?: {in?: string, out?: string},
 *   power?: {rails?: Record<string, number>}, [key: string]: any}} Circuit
 * @typedef {{from: number[], to: number[]}} Wire
 * @typedef {{net: string, pos: number[], rot?: number}} Label `rot`: a supply symbol turned (D-117)
 * @typedef {{title?: string, text?: string, pos: number[]}} TextBlock free text on the sheet,
 *   an optional bold title over it (D-091)
 * @typedef {{title?: string, text?: string}} Note a general note (9d4); a part's note is on
 *   the part (`note`), a named net's in `net_notes`
 * @typedef {{parts: string[], wires?: number[], labels?: number[], texts?: number[]}} Items
 */

import { bodyBox, pinPositions, poleStep, textBoxes } from "../schematic/symbols.js";
import { findPath, key, throughBody, worldOf } from "./router.js";

export const GRID = 10;

/**
 * The palette: one entry per placeable part type, with its group, hotkey (shown only in
 * the tile's tooltip, D-057), ref prefix and the fields a new part starts with. `model`
 * is filled from the model library when placed.
 */
export const PALETTE = [
  { key: "r", type: "resistor", name: "Resistor", group: "Passive", prefix: "R", fields: { value: "10k" } },
  { key: "c", type: "capacitor", name: "Capacitor", group: "Passive", prefix: "C", fields: { value: "100n" } },
  { key: "p", type: "pot", name: "Pot", group: "Passive", prefix: "VR", fields: { value: "100k", taper: "B", rotation: 0.5 } },
  { type: "inductor", name: "Inductor", group: "Passive", prefix: "L", fields: { value: "500m" } },
  { key: "t", type: "trimmer", name: "Trimmer", group: "Passive", prefix: "TR", fields: { value: "50k" } },
  { key: "s", type: "switch", name: "Switch", group: "Passive", prefix: "SW", fields: { kind: "spdt" } },
  { key: "d", type: "diode", name: "Diode", group: "Semiconductors", prefix: "D", fields: {}, model: "1N4148" },
  { key: "e", type: "led", name: "LED", group: "Semiconductors", prefix: "LED", fields: {}, model: "APT1608SURCK" },
  { key: "q", type: "bjt", name: "Transistor", group: "Semiconductors", prefix: "Q", fields: {}, model: "2N5089" },
  { key: "j", type: "jfet", name: "JFET", group: "Semiconductors", prefix: "Q", fields: {}, model: "J201" },
  { type: "mosfet", name: "MOSFET", group: "Semiconductors", prefix: "Q", fields: {}, model: "2N7000" },
  // an op-amp is placed as its chip (D-140): a dual as both halves, IC1A and IC1B; a quad as IC1A to IC1D (D-172)
  { key: "u", type: "opamp", name: "Dual op-amp", group: "Semiconductors", prefix: "IC", fields: {}, model: "TL072", halves: 2 },
  { tool: "opamp-quad", type: "opamp", name: "Quad op-amp", group: "Semiconductors", prefix: "IC", fields: {}, model: "TL074", halves: 4 },
  { key: "o", tool: "opamp-single", type: "opamp", name: "Single op-amp", group: "Semiconductors", prefix: "IC", fields: {}, model: "TL071" },
  // a 4049 as its six inverters in two rows, an LM13700 as its two OTAs, each with its power unit (D-180)
  { type: "inverter", name: "Hex inverter", group: "Semiconductors", prefix: "IC", fields: {}, model: "CD4049UB", halves: 6,
    offsets: [[0, 0], [100, 0], [200, 0], [0, 80], [100, 80], [200, 80]], power: [300, 40] },
  { tool: "ota-dual", type: "ota", name: "Dual OTA", group: "Semiconductors", prefix: "IC", fields: {}, model: "LM13700", halves: 2,
    offsets: [[0, 0], [180, 0]], power: [340, 0] },
  { tool: "ota-single", type: "ota", name: "OTA", group: "Semiconductors", prefix: "IC", fields: {}, model: "CA3080" },
  { key: "i", type: "guitar", name: "Guitar in", group: "Signal & power", prefix: "IN", fields: { volume: "250k" }, bare: true },
  { key: "a", type: "amp", name: "Amp out", group: "Signal & power", prefix: "OUT", fields: { value: "1M" }, bare: true },
  { key: "v", type: "vsource", name: "DC source", group: "Signal & power", prefix: "V", fields: { value: "9" } },
  { type: "jack", name: "Jack", group: "Signal & power", prefix: "J", fields: {} },
  { key: "h", type: "dcjack", name: "DC jack", group: "Signal & power", prefix: "DC", fields: {}, bare: true },
  { key: "y", type: "battery", name: "Battery", group: "Signal & power", prefix: "BAT", fields: { volts: 9, state: "fresh" } },
  { key: "k", type: "chargepump", name: "Charge pump", group: "Signal & power", prefix: "IC", model: "TC1044S" },
  { type: "regulator", name: "Regulator", group: "Signal & power", prefix: "IC", fields: {}, model: "78L12" },
];

/**
 * The header's Power presets (D-093, after PedalSpice): one supply or a ± pair. A circuit
 * that runs from V- alone (a PNP Fuzz Face) gets the negative singles instead.
 */
const SINGLE_VOLTS = [9, 12, 18];
const SPLIT_VOLTS = [9, 12, 15];

/**
 * The circuit's main supply: its first rail, as [name, volts].
 * @param {Circuit} circuit @returns {[string, number] | null}
 */
export function mainRail(circuit) {
  const [first] = Object.entries(circuit.power?.rails ?? {});
  return first ?? null;
}

/** @param {number} v */
const volts = (v) => `${String(Math.abs(v))} V`;

/**
 * A supply as the Power menu names it: "9 V", "−9 V", "±9 V", "+12 / −9 V", "no supply".
 * @param {Record<string, number>} rails
 */
export function powerText(rails) {
  const pos = rails["V+"];
  const neg = rails["V-"];
  if (pos !== undefined && neg !== undefined) return pos === -neg ? `±${volts(pos)}` : `+${String(pos)} / −${volts(neg)}`;
  if (pos !== undefined) return volts(pos);
  if (neg !== undefined) return `−${volts(neg)}`;
  return "no supply";
}

/**
 * The Power menu's choices for this circuit: the presets, and the circuit's own supply
 * when it isn't one of them, each with its rails and a key for the <select>.
 * @param {Circuit} circuit
 * @returns {Array<{key: string, text: string, rails: Record<string, number>}>}
 */
export function powerChoices(circuit) {
  const current = circuit.power?.rails ?? {};
  const negative = "V-" in current && !("V+" in current);
  const presets = [
    ...SINGLE_VOLTS.map((v) => (negative ? { "V-": -v } : { "V+": v })),
    ...SPLIT_VOLTS.map((v) => ({ "V+": v, "V-": -v })),
  ];
  const key = (/** @type {Record<string, number>} */ r) => Object.keys(SUPPLIES).filter((n) => n in r).map((n) => `${n}${r[n]}`).join(" ");
  const choices = presets.map((rails) => ({ key: key(rails), text: powerText(rails), rails }));
  if (Object.keys(current).length && !choices.some((c) => c.key === key(current))) {
    choices.unshift({ key: key(current), text: powerText(current), rails: current });
  }
  return choices;
}

/**
 * Set the supply to `rails` (a Power choice), through `setRails`. Throws with a plain
 * message when a rail that goes is still used and can't be handed on.
 * @param {Circuit} circuit @param {Record<string, number>} rails
 */
export function setPower(circuit, rails) {
  /** @type {Record<string, string>} */
  const entries = Object.fromEntries(Object.keys(SUPPLIES).map((n) => [n, n in rails ? String(Math.abs(rails[n])) : ""]));
  return setRails(circuit, entries);
}

/**
 * True when nothing is connected yet (no wires, no labels): a fresh sheet, where there's
 * no signal path to simulate.
 * @param {Circuit} circuit
 */
export const isUnwired = (circuit) => !(circuit.wires ?? []).length && !(circuit.labels ?? []).length;

/** @param {number} v */
export const snap = (v) => Math.round(v / GRID) * GRID;

/** @param {number[]} p @returns {number[]} */
export const snapPoint = (p) => [snap(p[0]), snap(p[1])];

/** @param {number[]} a @param {number[]} b */
export const same = (a, b) => a[0] === b[0] && a[1] === b[1];

/**
 * The next free ref with this prefix: R1, R2… ("bare" types use the prefix alone first:
 * IN, then IN2).
 * @param {Circuit} circuit @param {string} prefix @param {boolean} [bare]
 */
export function nextRef(circuit, prefix, bare = false) {
  const taken = new Set(circuit.parts.map((p) => p.ref));
  if (bare && !taken.has(prefix)) return prefix;
  // a number is free only if its units' or poles' refs are too (IC1 is taken by IC1A or its power unit IC1C, D-140, D-179, or a 4049's IC1G; SW1 by SW1C, D-143)
  const free = (/** @type {string} */ ref) => ![ref, ...[..."ABCDEFG"].map((x) => `${ref}${x}`)].some((r) => taken.has(r));
  for (let n = bare ? 2 : 1; ; n++) if (free(`${prefix}${n}`)) return `${prefix}${n}`;
}

/**
 * A diode's ref after its model changes (D-229): a zener is named Z, as schematics do, so
 * D1 set to a zener becomes the next free Z, and Z1 set to a plain diode the next free D.
 * A ref that isn't a plain D or Z and a number (one you typed) is kept.
 * @param {Circuit} circuit @param {any} part @param {string | undefined} model the new model
 * @param {string[]} zeners the zener models' ids (`/api/models`)
 */
export function diodeRef(circuit, part, model, zeners) {
  if (part.type !== "diode" || !model || model === part.model) return part.ref;
  const zener = zeners.includes(model);
  if (zener && /^D\d+$/.test(part.ref)) return nextRef(circuit, "Z");
  if (!zener && /^Z\d+$/.test(part.ref)) return nextRef(circuit, "D");
  return part.ref;
}

/**
 * The palette entry for a tile (`tool`, or its part type when it has no tool of its own).
 * @param {string} tool
 */
export function paletteEntry(tool) {
  return PALETTE.find((e) => (e.tool ?? e.type) === tool);
}

/** Where an op-amp chip's halves go when it's placed, from half a: a dual's b beside it (D-140), a quad's c and d under a and b (D-172). Other chips' entries give their own `offsets` and `power` (D-180). */
export const HALF_OFFSETS = [[0, 0], [120, 0], [0, 120], [120, 120]];

/** Where a chip's power unit goes, from half a (D-179): right of the halves, a quad's between its rows. */
const POWER_OFFSETS = /** @type {Record<number, number[]>} */ ({ 2: [220, 0], 4: [220, 60] });

/**
 * Every part of the one switch `ref` is a pole of (SW1A → SW1A, SW1B…), or of the dual
 * pot it is a gang of (VR1A → VR1A, VR1B, D-217), or null for a single-pole switch, a
 * single pot or any other part.
 * @param {Circuit} circuit @param {string} ref
 * @returns {string[] | null}
 */
export function poleRefs(circuit, ref) {
  const part = circuit.parts.find((p) => p.ref === ref);
  const key = unitKey(part);
  if (!key || !part[key]) return null;
  const name = ref.slice(0, -1);
  return circuit.parts.filter((p) => p.type === part.type && p[key] && p.ref.slice(0, -1) === name).map((p) => p.ref);
}

/**
 * The field that makes a part one unit of several turned together: a switch's `pole`
 * (D-143), a dual pot's `gang` (D-217); null for anything else.
 * @param {any} part
 * @returns {"pole" | "gang" | null}
 */
export function unitKey(part) {
  return part?.type === "switch" ? "pole" : part?.type === "pot" ? "gang" : null;
}

/**
 * The parts that go together with `ref`: a chip's halves or a switch's poles (itself
 * included); just itself for anything else.
 * @param {Circuit} circuit @param {string} ref
 * @returns {string[]}
 */
export function groupRefs(circuit, ref) {
  return chipRefs(circuit, ref) ?? poleRefs(circuit, ref) ?? [ref];
}

/**
 * A switch's new type from one pole's form (D-143): every pole takes it, with `fields`
 * (its position and label), and poles are added beside the last or taken away to match
 * the type's. `poles`: the new type's count. Refs follow: SW1 becomes SW1A, SW1B… when it
 * gains poles, and back to SW1 with one. A pot's gangs likewise (D-217): VR1 becomes VR1A
 * and VR1B as a dual pot, every gang taking `fields` (value, taper, rotation, label).
 * @param {Circuit} circuit @param {string} ref one pole's ref @param {number} poles
 * @param {Record<string, unknown>} fields
 * @returns {Circuit}
 */
export function setSwitchPoles(circuit, ref, poles, fields) {
  const refs = groupRefs(circuit, ref);
  const name = poleRefs(circuit, ref) ? ref.slice(0, -1) : ref;
  const first = /** @type {any} */ (circuit.parts.find((p) => p.ref === refs[0]));
  const key = unitKey(first) ?? "pole";
  /** @type {any[]} */
  const made = [];
  for (let i = 0; i < poles; i++) {
    const letter = "abcd"[i];
    const old = circuit.parts.find((p) => p.ref === refs[i]);
    const [x, y] = first.pos ?? [0, 0]; // a file leaves out a part's pos at (0, 0)
    // a pole the type gains is stacked under the one before, A over B over C (D-143); a
    // pot's second gang goes beside the first, as a dual pot's drawn (D-217)
    const step = key === "gang" ? [GANG_STEP, 0] : [0, poleStep({ ...first, ...fields })];
    const pos = old?.pos ?? [x + step[0] * i, y + step[1] * i];
    // a new pole is a copy of the first, but not its note
    const part = { ...first, ...(old ?? { note: null }), ...fields, pos, ref: poles > 1 ? `${name}${letter.toUpperCase()}` : name };
    if (poles > 1) part[key] = letter;
    else delete part[key];
    made.push(Object.fromEntries(Object.entries(part).filter(([, v]) => v !== null && v !== undefined)));
  }
  return { ...circuit, parts: circuit.parts.flatMap((p) => (p.ref === refs[0] ? made : refs.includes(p.ref) ? [] : [p])) };
}

/** How far right a dual pot's gang B goes from gang A when the pot is made dual (D-217). */
const GANG_STEP = 80;

/**
 * Every part of the chip `ref` is part of: its units, a first, then its power unit
 * (IC1A, IC1B, IC1C for IC1B; IC1A to IC1E for a quad, D-172, D-179; IC1A to IC1G for a
 * 4049, D-180), or null for a single or any other part.
 * @param {Circuit} circuit @param {string} ref
 * @returns {string[] | null}
 */
export function chipRefs(circuit, ref) {
  const part = circuit.parts.find((p) => p.ref === ref);
  if (!part || !isChipPart(part)) return null;
  const name = ref.slice(0, -1);
  return circuit.parts.filter((p) => isChipPart(p) && p.ref.slice(0, -1) === name).map((p) => p.ref).sort();
}

/** The part types that are a chip's units (D-180): with `half`, one of a chip of several. */
export const CHIP_UNIT_TYPES = ["opamp", "inverter", "ota"];

/**
 * A unit or the power unit of a chip of several: a dual or quad op-amp, a 4049, an LM13700.
 * @param {any} part
 */
export function isChipPart(part) {
  return (CHIP_UNIT_TYPES.includes(part.type) && Boolean(part.half)) || part.type === "powerunit";
}

/**
 * Rename a chip from one half's form (D-140), or a switch from one pole's (D-143): `to`
 * is the new name or a half's or pole's (IC2 or IC2A), and every part of it follows
 * (IC2A, IC2B), with everything naming them.
 * @param {Circuit} circuit @param {string} from a half's or pole's ref @param {string} to
 */
export function renameChip(circuit, from, to) {
  const name = to.replace(/[a-h]$/i, "");
  let out = circuit;
  for (const ref of groupRefs(circuit, from)) out = renamePart(out, ref, `${name}${ref.slice(-1)}`);
  return out;
}

/**
 * The refs a delete takes: each part asked for and, for half of a chip or a pole of a
 * switch, the rest of it (deleting one deletes it all, D-140, D-143).
 * @param {Circuit} circuit @param {string[]} refs
 * @returns {string[]}
 */
export function withChips(circuit, refs) {
  return [...new Set(refs.flatMap((ref) => groupRefs(circuit, ref)))];
}

/**
 * The ref of the part `text` names, ignoring case and spaces ("r 12" finds R12), or null.
 * @param {Circuit} circuit @param {string} text
 * @returns {string | null}
 */
export function findRef(circuit, text) {
  const want = text.replace(/\s+/g, "").toUpperCase();
  return (want && circuit.parts.find((p) => p.ref.toUpperCase() === want)?.ref) || null;
}

/**
 * Which model a new part gets: the palette's choice when the library has it, else the
 * library's first of that type.
 * @param {{model?: string}} entry @param {string[]} available
 */
export function defaultModel(entry, available) {
  if (!entry.model) return undefined;
  return available.includes(entry.model) ? entry.model : available[0];
}

/**
 * A new part from the palette at `pos` (snapped). Dropped on a wire, it goes in series
 * (`inSeries`).
 * @param {Circuit} circuit @param {string} type @param {number[]} pos @param {number} rot
 * @param {Record<string, string[]>} [models] model ids by part type
 * @returns {{circuit: Circuit, ref: string}}
 */
export function addPart(circuit, type, pos, rot = 0, models = {}) {
  const entry = paletteEntry(type);
  if (!entry) throw new Error(`Can't place a ${type}`);
  const ref = nextRef(circuit, entry.prefix, entry.bare);
  const model = defaultModel(entry, models[entry.type] ?? []);
  const at = snapPoint(pos);
  const part = { ref, type: entry.type, pos: at, ...(rot ? { rot } : {}), ...entry.fields, ...(model ? { model } : {}) };
  if (!entry.halves) return { circuit: inSeries({ ...circuit, parts: [...circuit.parts, part] }, [ref]), ref };
  // a chip: every unit and its power unit, laid out from unit a (D-140, D-172, D-179, D-180)
  const halves = (entry.offsets ?? HALF_OFFSETS).slice(0, entry.halves).map(([dx, dy], i) => (
    { ...part, ref: `${ref}${"ABCDEF"[i]}`, half: "abcdef"[i], pos: [at[0] + dx, at[1] + dy] }));
  const [dx, dy] = entry.power ?? POWER_OFFSETS[entry.halves];
  const unit = { ref: `${ref}${"ABCDEFG"[entry.halves]}`, type: "powerunit", pos: [at[0] + dx, at[1] + dy], ...(rot ? { rot } : {}), model: part.model };
  const chip = [...halves, unit];
  return { circuit: inSeries({ ...circuit, parts: [...circuit.parts, ...chip] }, chip.map((h) => h.ref)), ref: `${ref}A` };
}

/**
 * Put parts that landed on a wire in series with it (D-112, D-113): wire running through
 * two of a part's pins (one of them part-way along it) would short them, so it's cut
 * between them. The wire may be in pieces that meet under the part (D-164: a trimmer
 * dropped on a joint stayed shorted). A jumper from one pin to the other stays, even in
 * pieces: the wire is cut only when some of it runs on past a pin. A wire the part only
 * touches with one pin stays too. After placing, moving or turning parts.
 * @param {Circuit} circuit @param {Iterable<string>} refs the parts placed or moved
 * @returns {Circuit}
 */
export function inSeries(circuit, refs) {
  const wanted = new Set(refs);
  let wires = circuit.wires ?? [];
  for (const part of circuit.parts.filter((p) => wanted.has(p.ref))) {
    const pins = Object.values(pinPositions(part));
    for (const [i, a] of pins.entries()) {
      for (const b of pins.slice(i + 1)) wires = cutBetween(wires, a, b);
    }
  }
  return wires === (circuit.wires ?? wires) ? circuit : { ...circuit, wires };
}

/**
 * `wires` with the wire running straight from `a` to `b` taken out, when that stretch is
 * all wire and some of it runs on past `a` or `b` (`inSeries`). The same list otherwise.
 * @param {Wire[]} wires @param {number[]} a @param {number[]} b
 * @returns {Wire[]}
 */
function cutBetween(wires, a, b) {
  const axis = a[1] === b[1] ? 0 : a[0] === b[0] ? 1 : -1;
  if (axis < 0) return wires;
  const other = 1 - axis;
  const [lo, hi] = [Math.min(a[axis], b[axis]), Math.max(a[axis], b[axis])];
  const along = (/** @type {Wire} */ w) => w.from[other] === a[other] && w.to[other] === a[other];
  const span = (/** @type {Wire} */ w) => [Math.min(w.from[axis], w.to[axis]), Math.max(w.from[axis], w.to[axis])];
  const touching = wires.filter((w) => along(w) && span(w)[1] > lo && span(w)[0] < hi);
  if (!touching.length || !touching.some((w) => span(w)[0] < lo || span(w)[1] > hi)) return wires;
  let reach = lo; // is lo..hi all wire?
  for (const [s0, s1] of touching.map(span).sort((x, y) => x[0] - y[0])) {
    if (s0 > reach) return wires;
    reach = Math.max(reach, s1);
  }
  if (reach < hi) return wires;
  const inside = (/** @type {Wire} */ w) => span(w)[0] >= lo && span(w)[1] <= hi;
  return wires.flatMap((w) => (touching.includes(w) ? splitAtJoins([w], [a, b]).filter((piece) => !inside(piece)) : [w]));
}

/**
 * Pins and label points of a circuit, as "x,y" keys.
 * @param {Circuit} circuit
 */
export const anchorPoints = (circuit) => [
  ...circuit.parts.flatMap((p) => Object.values(pinPositions(p))),
  ...(circuit.labels ?? []).map((lb) => lb.pos),
];

/**
 * What a new wire in `circuit` must keep clear of (D-063): part bodies and their text,
 * pins and labels, other wires.
 * @param {Circuit} circuit @param {Wire[]} [wires] the wires to count (default: all)
 */
function worldFor(circuit, wires = circuit.wires ?? []) {
  const anchors = anchorPoints(circuit);
  const inside = (/** @type {number[]} */ b) => anchors.some(([x, y]) => b[0] < x && x < b[2] && b[1] < y && y < b[3]);
  // part text too, unless a pin sits in it (then a wire must be able to reach that pin)
  const text = circuit.parts.flatMap((p) => textBoxes(p, String(p.value ?? p.model ?? ""))).filter((b) => !inside(b));
  return worldOf({ boxes: [...circuit.parts.map(bodyBox), ...text], anchors, wires });
}

/**
 * The tidiest square wire from `a` to `b` (D-063): around part bodies, never over a pin,
 * label or another wire's end, never along another wire. Falls back to a plain elbow
 * (`route`) when there's no clear way nearby. Used when the app lays a wire itself
 * (re-laying after a move).
 * @param {Circuit} circuit @param {number[]} a @param {number[]} b
 * @param {boolean} [horizontal] which way to leave `a`, when it's a toss-up
 * @param {Wire[]} [pending] wires being drawn, not in the circuit yet, to keep clear of too
 * @returns {Wire[]}
 */
export function routeWire(circuit, a, b, horizontal, pending = []) {
  [a, b] = [snapPoint(a), snapPoint(b)];
  const wires = [...(circuit.wires ?? []), ...pending];
  // no clear way (say, a part dropped on top of another): go through bodies and text
  // rather than fall back to an elbow, which could touch a pin or wire and connect to it
  return findPath(a, b, worldFor(circuit, wires), horizontal)
    ?? findPath(a, b, worldOf({ boxes: [], anchors: anchorPoints(circuit), wires }), horizontal)
    ?? route(a, b, horizontal);
}

/**
 * A leg of wire the user draws from `a` to `b`: the plain elbow they aimed for (it may
 * run onto a wire or pin on purpose, which connects), unless it would cut through a part's
 * body; then it goes around (`routeWire`).
 * @param {Circuit} circuit @param {number[]} a @param {number[]} b
 * @param {boolean} [horizontal] @param {Wire[]} [pending]
 * @returns {Wire[]}
 */
export function drawnWire(circuit, a, b, horizontal, pending = []) {
  const direct = route(a, b, horizontal);
  if (!throughBody(direct, circuit.parts.map(bodyBox))) return direct;
  return routeWire(circuit, a, b, horizontal, pending);
}

/**
 * The runs of wire leaving `start`: from wire to wire through plain bends (two wires and
 * nothing else) up to where the run stops (a pin, label, junction, T, or loose end).
 * @param {Wire[]} wires @param {number[]} start @param {(p: number[]) => boolean} isStop
 * @returns {Array<{wires: number[], end: number[]}>}
 */
export function runsFrom(wires, start, isStop) {
  /** @type {Map<string, number[]>} */
  const at = new Map();
  wires.forEach((w, i) => {
    for (const p of [w.from, w.to]) at.set(key(p), [...(at.get(key(p)) ?? []), i]);
  });
  const used = new Set();
  const runs = [];
  for (const first of at.get(key(start)) ?? []) {
    if (used.has(first)) continue;
    const ids = [];
    let here = start;
    for (let j = /** @type {number | undefined} */ (first); j !== undefined; ) {
      used.add(j);
      ids.push(j);
      const w = wires[j];
      here = same(w.from, here) ? w.to : w.from;
      if (same(here, start) || isStop(here)) break;
      j = (at.get(key(here)) ?? []).find((k) => !used.has(k));
    }
    runs.push({ wires: ids, end: here });
  }
  return runs;
}

/**
 * Split wires at every point where something joins them part-way along: another wire's
 * end, a pin or a label. Connections are unchanged (a point on a wire is joined to it
 * either way); each join becomes a wire end, so runs of wire stop there.
 * @param {Wire[]} wires @param {number[][]} anchors pin and label points
 * @returns {Wire[]}
 */
export function splitAtJoins(wires, anchors) {
  const points = [...anchors, ...wires.flatMap((w) => [w.from, w.to])];
  return wires.flatMap((w) => {
    const straight = w.from[0] === w.to[0] || w.from[1] === w.to[1];
    if (!straight) return [w];
    const along = (/** @type {number[]} */ p) => Math.abs(p[0] - w.from[0]) + Math.abs(p[1] - w.from[1]);
    const inside = points.filter((p) => !same(p, w.from) && !same(p, w.to) && same(pointOnWire(w, p), p) && (p[0] === w.from[0] || p[1] === w.from[1]));
    const cuts = [...new Map(inside.map((p) => [key(p), p])).values()].sort((a, b) => along(a) - along(b));
    const stops = [w.from, ...cuts, w.to];
    return stops.slice(1).map((to, i) => ({ from: stops[i], to }));
  });
}

/**
 * Re-lay the wires after points move (a part's pins, or a wire end's ball): each run of
 * wire from a moved point is re-routed from its far end, the way a fresh wire would go
 * (D-063). So dragging a part about never leaves a trail of old bends: the wire always
 * goes the tidiest way from where it's anchored. A run whose two ends moved together
 * just moves with them. Labels on moved points go along when `labels` is set.
 * @param {Circuit} before the circuit before the move @param {Circuit} after with parts moved
 * @param {Array<[number[], number[]]>} moves (old point, new point)
 * @param {{labels?: boolean, joinPins?: boolean}} [opts] `joinPins`: a pin left at a moved
 *   point keeps its connection with a wire to the new point (off when a part is put in
 *   series there: `insertInSeries`)
 * @returns {Circuit}
 */
export function relay(before, after, moves, { labels = true, joinPins = true } = {}) {
  // split first, so a wire that something joins part-way along (a T) is re-laid only up
  // to the join and the joining wire stays connected; `origin` says which wire each piece is from
  const all = before.wires ?? [];
  const points = [...anchorPoints(before), ...all.flatMap((w) => [w.from, w.to])];
  /** @type {number[]} */
  const origin = [];
  const wires = all.flatMap((w, i) => splitAtJoins([w], points).map((piece) => (origin.push(i), piece)));
  const anchors = new Set(anchorPoints(before).map(key));
  /** @type {Map<string, number>} */
  const degree = new Map();
  for (const w of wires) for (const p of [w.from, w.to]) degree.set(key(p), (degree.get(key(p)) ?? 0) + 1);
  const onAnother = (/** @type {number[]} */ p) => wires.some((w) => !same(w.from, p) && !same(w.to, p) && same(pointOnWire(w, p), p));
  // a moved point ends a run too, so wires between two moved points move with them
  const movedKeys = new Set(moves.map(([a]) => key(a)));
  const isStop = (/** @type {number[]} */ p) => anchors.has(key(p)) || movedKeys.has(key(p)) || degree.get(key(p)) !== 2 || onAnother(p);
  const movedTo = (/** @type {number[]} */ p) => moves.find(([a]) => same(a, p))?.[1];

  const dropped = new Set();
  /** @type {Map<number, number[]>} piece -> how far it moved, for pieces moving whole */
  const shiftedBy = new Map();
  /** @type {Array<[number[], number[]]>} */
  const jobs = [];
  /** @type {Array<{pieces: Array<Wire | [number[], number[]]>, ends: number[][]}>} bent runs kept bent (`stretchRun`) */
  const stretched = [];
  for (const [from, to] of moves) {
    for (const run of runsFrom(wires, from, isStop)) {
      if (run.wires.some((i) => dropped.has(i))) continue; // done from its other end
      for (const i of run.wires) dropped.add(i);
      const endTo = movedTo(run.end);
      const [dx, dy] = [to[0] - from[0], to[1] - from[1]];
      if (endTo && endTo[0] - run.end[0] === dx && endTo[1] - run.end[1] === dy) {
        for (const i of run.wires) shiftedBy.set(i, [dx, dy]);
      } else if (!endTo && run.wires.length > 1) {
        stretched.push({ pieces: stretchRun(runPoints(wires, run.wires, from), to), ends: [to, run.end] });
      } else {
        jobs.push([endTo ?? run.end, to]);
      }
    }
  }
  // a moved pin that touched a pin staying put (connected with no wire) keeps that
  // connection with a new wire between them
  const staying = new Set(after.parts.filter((p) => before.parts.includes(p)).flatMap((p) => Object.values(pinPositions(p)).map(key)));
  for (const [from, to] of moves) if (joinPins && staying.has(key(from)) && !same(from, to)) jobs.push([from, to]);
  const moved = (/** @type {number[]} */ p) => movedTo(p) ?? p;
  const placed = { ...after, labels: labels ? (after.labels ?? []).map((lb) => ({ ...lb, pos: moved(lb.pos) })) : after.labels };
  // a wire whose pieces all stayed, or all moved the same way, stays one wire
  const by = (/** @type {Wire} */ w, /** @type {number[]} */ d) => ({ from: [w.from[0] + d[0], w.from[1] + d[1]], to: [w.to[0] + d[0], w.to[1] + d[1]] });
  /** @type {Wire[]} */
  const kept = [];
  /** @type {Wire[]} */
  const shifted = [];
  all.forEach((w, o) => {
    const ids = wires.flatMap((_p, i) => (origin[i] === o ? [i] : []));
    const d = shiftedBy.get(ids[0]);
    if (ids.every((i) => !dropped.has(i))) kept.push(w);
    else if (d && ids.every((i) => shiftedBy.get(i)?.join() === d.join())) shifted.push(by(w, d));
    else {
      for (const i of ids) {
        const di = shiftedBy.get(i);
        if (!dropped.has(i)) kept.push(wires[i]);
        else if (di) shifted.push(by(wires[i], di));
      }
    }
  });
  let out = addWires({ ...placed, wires: kept }, shifted);
  // a bent run keeps its bends unless they'd now touch something: then it's routed afresh
  for (const { pieces, ends } of stretched) {
    const straight = /** @type {Wire[]} */ (pieces.filter((piece) => !Array.isArray(piece)));
    if (!touchesNew(out, straight, ends)) {
      for (const piece of pieces) out = addWires(out, Array.isArray(piece) ? routeWire(out, piece[0], piece[1]) : [piece]);
    } else jobs.push([ends[1], ends[0]]);
  }
  for (const [a, b] of jobs) out = addWires(out, routeWire(out, a, b));
  return out;
}

/**
 * Whether wires `run` (a run being laid between its `ends`) would join something they
 * don't now: a pin, a label or another wire's end on them, or one of their bends on
 * another wire (`relay`, D-164).
 * @param {Circuit} circuit @param {Wire[]} run @param {number[][]} ends
 */
function touchesNew(circuit, run, ends) {
  const own = (/** @type {number[]} */ p) => ends.some((e) => same(e, p));
  const others = circuit.wires ?? [];
  const points = [...anchorPoints(circuit), ...others.flatMap((w) => [w.from, w.to])].filter((p) => !own(p));
  const on = (/** @type {Wire} */ w, /** @type {number[]} */ p) => same(pointOnWire(w, p), p);
  return run.some((w) => points.some((p) => on(w, p)))
    || run.flatMap((w) => [w.from, w.to]).filter((p) => !own(p)).some((p) => others.some((w) => on(w, p)));
}

/**
 * The points of a run of wire pieces, in order from `start` to its far end.
 * @param {Wire[]} wires @param {number[]} ids the run's pieces, from `start` (`runsFrom`)
 * @param {number[]} start @returns {number[][]}
 */
function runPoints(wires, ids, start) {
  const points = [start];
  for (const i of ids) {
    const w = wires[i];
    points.push(same(w.from, points[points.length - 1]) ? w.to : w.from);
  }
  return points;
}

/**
 * A bent run of wire after its first point moves to `to`, its far end staying (D-164,
 * the user: moving a part "fubars the angles"): its bends kept, as KiCad drags. The bend
 * next to the moved point slides with it so that leg stays straight, the next leg only
 * gets longer or shorter; if the far end's leg can't stay straight, that last stretch is
 * routed afresh. Wires, and [a, b] pairs for `routeWire`.
 * @param {number[][]} points the run, the moved point first (`runPoints`)
 * @param {number[]} to @returns {Array<Wire | [number[], number[]]>}
 */
export function stretchRun(points, to) {
  const now = [to, ...points.slice(1)];
  for (let i = 1; i < points.length - 1; i++) {
    const [a, b] = [points[i - 1], points[i]];
    if (a[0] !== b[0] && a[1] !== b[1]) break; // a slanted leg (old files): left to the router
    const slid = a[1] === b[1] ? [b[0], now[i - 1][1]] : [now[i - 1][0], b[1]];
    if (same(slid, b)) break;
    now[i] = slid;
  }
  /** @type {Array<Wire | [number[], number[]]>} */
  const out = [];
  for (let i = 1; i < now.length; i++) {
    const [a, b] = [now[i - 1], now[i]];
    if (same(a, b)) continue;
    out.push(a[0] === b[0] || a[1] === b[1] ? { from: a, to: b } : [a, b]);
  }
  return out;
}

/**
 * The whole wire a piece belongs to, as the user sees it: the pieces joined end to end
 * through bends, up to where the wire ends or meets something (a pin, a label, a branch
 * or a T). Clicking a bent wire selects all of it, so Delete or a drag takes all of it.
 * @param {Circuit} circuit @param {number} index a piece of it
 * @returns {number[]} indices into `circuit.wires`, `index` first
 */
export function wireRun(circuit, index) {
  const wires = circuit.wires ?? [];
  const start = wires[index];
  if (!start) return [];
  const anchors = new Set(anchorPoints(circuit).map(key));
  /** @type {Map<string, number>} */
  const degree = new Map();
  for (const w of wires) for (const p of [w.from, w.to]) degree.set(key(p), (degree.get(key(p)) ?? 0) + 1);
  const onAnother = (/** @type {number[]} */ p) => wires.some((w) => !same(w.from, p) && !same(w.to, p) && same(pointOnWire(w, p), p));
  const isStop = (/** @type {number[]} */ p) => anchors.has(key(p)) || degree.get(key(p)) !== 2 || onAnother(p);
  const run = [index];
  for (let here of [start.from, start.to]) {
    while (!isStop(here)) {
      const next = wires.findIndex((w, k) => !run.includes(k) && (same(w.from, here) || same(w.to, here)));
      if (next < 0) break;
      run.push(next);
      here = same(wires[next].from, here) ? wires[next].to : wires[next].from;
    }
  }
  return run;
}

/**
 * Wires and labels found again by where they are: the wires of `circuit` lying along
 * `wires` and the labels sitting on `spots`. The server's copy of a circuit can reorder
 * the lists and split or join wires, so a selection held by list index goes stale after
 * an edit; this finds it again (D-095).
 * @param {Circuit} circuit @param {Wire[]} wires @param {number[][]} spots
 * @returns {{wires: number[], labels: number[]}}
 */
export function itemsAt(circuit, wires, spots) {
  const along = (/** @type {number[]} */ p) => wires.some((w) => same(pointOnWire(w, p), p));
  return {
    wires: (circuit.wires ?? []).flatMap((w, i) => (along(w.from) && along(w.to) ? [i] : [])),
    labels: (circuit.labels ?? []).flatMap((lb, i) => (spots.some((p) => same(p, lb.pos)) ? [i] : [])),
  };
}

/**
 * The moved items as they are found in the circuit after `moveItems(before, items, dx, dy)`
 * (`itemsAt` where they went). Parts and text blocks keep their names and places. Without
 * this, a second move of the same selection left its wires behind.
 * @param {Circuit} before @param {Circuit} after @param {Items} items
 * @param {number} dx @param {number} dy
 * @returns {Items}
 */
export function itemsAfterMove(before, after, items, dx, dy) {
  [dx, dy] = [snap(dx), snap(dy)];
  const shift = (/** @type {number[]} */ p) => [p[0] + dx, p[1] + dy];
  const wires = (items.wires ?? []).flatMap((i) => (before.wires?.[i] ? [{ from: shift(before.wires[i].from), to: shift(before.wires[i].to) }] : []));
  const spots = (items.labels ?? []).flatMap((i) => (before.labels?.[i] ? [shift(before.labels[i].pos)] : []));
  return { parts: items.parts, ...itemsAt(after, wires, spots), ...(items.texts ? { texts: items.texts } : {}) };
}

/**
 * Whether two views connect the same pins together: pins grouped by net, whatever the nets
 * are called. Moving a wire must keep this (D-095): it may change how a connection runs,
 * never what it connects. A view whose wiring contradicts itself has no nets to compare:
 * it matches only a view with the same contradiction, so a wire can still be pulled out
 * of the way in a circuit that has one (D-293), and a move that makes or mends one is refused.
 * @param {{problem?: string | null, parts: Array<{ref: string, pins: Array<{name: string, net: string | null}>}>}} a
 * @param {typeof a} b
 */
export function sameConnections(a, b) {
  if (a.problem || b.problem) return a.problem === b.problem;
  const groups = (/** @type {typeof a} */ v) => {
    /** @type {Map<string, string[]>} */
    const byNet = new Map();
    for (const p of v.parts) {
      for (const pin of p.pins) {
        if (!pin.net) continue;
        byNet.set(pin.net, [...(byNet.get(pin.net) ?? []), `${p.ref}.${pin.name}`]);
      }
    }
    return [...byNet.values()].map((g) => g.sort().join(" ")).sort().join("|");
  };
  return groups(a) === groups(b);
}

/**
 * Move a selection by (dx, dy), snapped: its parts, wires, labels and text blocks together.
 * Wires from the selection to what stays put are re-laid; labels on moved points go along.
 * @param {Circuit} circuit @param {Items} items
 * @param {number} dx @param {number} dy
 */
export function moveItems(circuit, items, dx, dy) {
  [dx, dy] = [snap(dx), snap(dy)];
  if (!dx && !dy) return circuit;
  const wanted = new Set(items.parts);
  /** @type {Map<string, [number[], number[]]>} */
  const moves = new Map();
  const shift = (/** @type {number[]} */ p) => moves.set(key(p), [p, [p[0] + dx, p[1] + dy]]);
  const parts = circuit.parts.map((p) => {
    if (!wanted.has(p.ref)) return p;
    for (const pin of Object.values(pinPositions(p))) shift(pin);
    const [x, y] = p.pos ?? [0, 0]; // the file leaves out a part at the origin
    return { ...p, pos: [x + dx, y + dy] };
  });
  // a selected wire moves whole: its ends and every point joined part-way along it
  const points = [...anchorPoints(circuit), ...(circuit.wires ?? []).flatMap((w) => [w.from, w.to])];
  for (const i of items.wires ?? []) {
    const w = circuit.wires?.[i];
    if (w) points.filter((p) => same(pointOnWire(w, p), p)).forEach(shift);
  }
  for (const i of items.labels ?? []) {
    const lb = circuit.labels?.[i];
    if (lb) shift(lb.pos);
  }
  const chosen = new Set(items.texts ?? []);
  const texts = (circuit.texts ?? []).map((t, i) => (chosen.has(i) ? { ...t, pos: [t.pos[0] + dx, t.pos[1] + dy] } : t));
  const after = { ...circuit, parts, ...(circuit.texts ? { texts } : {}) };
  return inSeries(moves.size ? relay(circuit, after, [...moves.values()]) : after, wanted);
}

/**
 * Move parts by (dx, dy), snapped, dragging the wire ends and labels on their pins along.
 * @param {Circuit} circuit @param {string[]} refs @param {number} dx @param {number} dy
 */
export const moveParts = (circuit, refs, dx, dy) => moveItems(circuit, { parts: refs }, dx, dy);

/**
 * Rotate a part a quarter turn clockwise about its position; connections follow its pins.
 * @param {Circuit} circuit @param {string} ref
 */
export function rotatePart(circuit, ref) {
  const old = circuit.parts.find((p) => p.ref === ref);
  if (!old) return circuit;
  const rot = ((old.rot ?? 0) + 90) % 360;
  const turned = { ...old, rot };
  if (!rot) delete turned.rot;
  const before = pinPositions(old);
  const after = pinPositions(turned);
  /** @type {Array<[number[], number[]]>} */
  const moves = Object.keys(before).map((name) => [before[name], after[name]]);
  const parts = circuit.parts.map((p) => (p.ref === ref ? turned : p));
  return inSeries(relay(circuit, { ...circuit, parts }, moves), [ref]);
}

/**
 * Remove parts, wires, labels and text blocks. A removed part's note goes with it.
 * @param {Circuit} circuit
 * @param {{parts?: string[], wires?: number[], labels?: number[], texts?: number[]}} what
 */
export function deleteItems(circuit, what) {
  const refs = new Set(what.parts ?? []);
  const wires = new Set(what.wires ?? []);
  const labels = new Set(what.labels ?? []);
  const texts = new Set(what.texts ?? []);
  const out = {
    ...circuit,
    parts: circuit.parts.filter((p) => !refs.has(p.ref)),
    wires: (circuit.wires ?? []).filter((_w, i) => !wires.has(i)),
    labels: (circuit.labels ?? []).filter((_l, i) => !labels.has(i)),
    ...(circuit.texts ? { texts: circuit.texts.filter((_t, i) => !texts.has(i)) } : {}),
  };
  return out;
}

/**
 * The wire segments from `a` to `b` on the grid: one straight segment when they line up,
 * else two with an elbow. `horizontal` says which way the first leg goes; left out, it's
 * horizontal when the span is wider than tall.
 * @param {number[]} a @param {number[]} b @param {boolean} [horizontal]
 * @returns {Wire[]}
 */
export function route(a, b, horizontal) {
  [a, b] = [snapPoint(a), snapPoint(b)];
  if (same(a, b)) return [];
  if (a[0] === b[0] || a[1] === b[1]) return [{ from: a, to: b }];
  const across = horizontal ?? Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]);
  const corner = across ? [b[0], a[1]] : [a[0], b[1]];
  return [{ from: a, to: corner }, { from: corner, to: b }];
}

/**
 * Add wire segments; ones already there (either way round) and zero-length ones aren't added.
 * @param {Circuit} circuit @param {Wire[]} segments
 */
export function addWires(circuit, segments) {
  const wires = [...(circuit.wires ?? [])];
  for (const w of segments) {
    const dup = wires.some((x) => (same(x.from, w.from) && same(x.to, w.to)) || (same(x.from, w.to) && same(x.to, w.from)));
    if (!dup && !same(w.from, w.to)) wires.push(w);
  }
  return { ...circuit, wires };
}

/**
 * Add a wire the user drew from `a` to `b` (`drawnWire`).
 * @param {Circuit} circuit @param {number[]} a @param {number[]} b
 */
export const addWire = (circuit, a, b) => addWires(circuit, drawnWire(circuit, a, b));

/**
 * Drag the wire ends at `from` to `to` (the balls on wire ends, D-062). Every run of wire
 * from that point is re-routed from its far end to `to` (D-063), so a bend stays joined.
 * Labels and parts stay where they are.
 * @param {Circuit} circuit @param {number[]} from @param {number[]} to
 */
export function moveWireEnd(circuit, from, to) {
  to = snapPoint(to);
  if (same(from, to)) return circuit;
  return relay(circuit, circuit, [[from, to]], { labels: false });
}

/**
 * Which wires an edit replaced and which it added (for the live preview while dragging).
 * @param {Wire[]} before @param {Wire[]} after
 * @returns {{added: Wire[], removed: number[]}}
 */
export function wireDiff(before, after) {
  const k = (/** @type {Wire} */ w) => [key(w.from), key(w.to)].sort().join("|");
  const old = new Set(before.map(k));
  const now = new Set(after.map(k));
  return {
    added: after.filter((w) => !old.has(k(w))),
    removed: before.flatMap((w, i) => (now.has(k(w)) ? [] : [i])),
  };
}

/**
 * @typedef {{parts: any[], moved: Array<{ref: string, from: number[], to: number[]}>, wires: {added: Wire[], removed: Wire[]},
 *   labels: {added: Label[], removed: Label[]}, texts: {added: TextBlock[], removed: TextBlock[]}}} EditDiff
 *   what an edit added (parts, wires, labels, text blocks), moved (parts) and took away (wires, labels, text blocks)
 */

/**
 * An edit as what it added, moved and took away (D-124), so it can go into the circuit as
 * it is later (`applyDiff`) and come out again: Try changes' diode arrangements, and the
 * room made for them.
 * @param {Circuit} before @param {Circuit} after @returns {EditDiff}
 */
export function editDiff(before, after) {
  const had = new Set(before.parts.map((p) => p.ref));
  const was = new Map(before.parts.map((p) => [p.ref, p.pos ?? [0, 0]]));
  const tk = (/** @type {TextBlock} */ t) => JSON.stringify([t.pos, t.title ?? "", t.text ?? ""]);
  const textsWere = new Set((before.texts ?? []).map(tk));
  const textsNow = new Set((after.texts ?? []).map(tk));
  const w = wireDiff(before.wires ?? [], after.wires ?? []);
  const labelsWere = new Set((before.labels ?? []).map(labelKey));
  const now = new Set((after.labels ?? []).map(labelKey));
  return {
    parts: after.parts.filter((p) => !had.has(p.ref)),
    moved: after.parts.flatMap((p) => {
      const from = was.get(p.ref);
      return from && !same(from, p.pos ?? [0, 0]) ? [{ ref: p.ref, from, to: p.pos ?? [0, 0] }] : [];
    }),
    wires: { added: w.added, removed: w.removed.map((i) => /** @type {Wire[]} */ (before.wires)[i]) },
    labels: {
      added: (after.labels ?? []).filter((lb) => !labelsWere.has(labelKey(lb))),
      removed: (before.labels ?? []).filter((lb) => !now.has(labelKey(lb))),
    },
    texts: {
      added: (after.texts ?? []).filter((t) => !textsWere.has(tk(t))),
      removed: (before.texts ?? []).filter((t) => !textsNow.has(tk(t))),
    },
  };
}

/**
 * `circuit` with `diff` put in (or, `undo`, taken out): its parts added (removed) and
 * moved (back), its wires, labels and text blocks added and removed by where they are.
 * @param {Circuit} circuit @param {EditDiff} diff @param {{undo?: boolean}} [opts]
 * @returns {Circuit}
 */
export function applyDiff(circuit, diff, { undo = false } = {}) {
  const [wiresIn, wiresOut] = undo ? [diff.wires.removed, diff.wires.added] : [diff.wires.added, diff.wires.removed];
  const [labelsIn, labelsOut] = undo ? [diff.labels.removed, diff.labels.added] : [diff.labels.added, diff.labels.removed];
  const refs = new Set(diff.parts.map((p) => p.ref));
  const wk = (/** @type {Wire} */ w) => [key(w.from), key(w.to)].sort().join("|");
  const dropW = new Set(wiresOut.map(wk));
  const dropL = new Set(labelsOut.map(labelKey));
  const [textsIn, textsOut] = undo ? [diff.texts?.removed ?? [], diff.texts?.added ?? []] : [diff.texts?.added ?? [], diff.texts?.removed ?? []];
  const tk = (/** @type {TextBlock} */ t) => JSON.stringify([t.pos, t.title ?? "", t.text ?? ""]);
  const dropT = new Set(textsOut.map(tk));
  const goes = new Map((diff.moved ?? []).map((m) => [m.ref, undo ? m.from : m.to]));
  const parts = circuit.parts.filter((p) => !refs.has(p.ref)).map((p) => (goes.has(p.ref) ? { ...p, pos: goes.get(p.ref) } : p));
  const wires = (circuit.wires ?? []).filter((w) => !dropW.has(wk(w)));
  const labels = (circuit.labels ?? []).filter((lb) => !dropL.has(labelKey(lb)));
  const texts = [...(circuit.texts ?? []).filter((t) => !dropT.has(tk(t))), ...textsIn];
  return addWires({ ...circuit, parts: undo ? parts : [...parts, ...diff.parts], wires, labels: [...labels, ...labelsIn], ...(circuit.texts || textsIn.length ? { texts } : {}) }, wiresIn);
}

/** A label as where it is and what it names. @param {Label} lb */
const labelKey = (lb) => JSON.stringify([lb.net, lb.pos, lb.rot ?? 0]);

/**
 * The point on wire `w` nearest `p`, on the grid: where a wire drawn onto `w` joins it.
 * @param {Wire} w @param {number[]} p
 */
export function pointOnWire(w, p) {
  const [x, y] = snapPoint(p);
  const clamp = (/** @type {number} */ v, /** @type {number} */ a, /** @type {number} */ b) => Math.min(Math.max(v, Math.min(a, b)), Math.max(a, b));
  if (w.from[1] === w.to[1]) return [clamp(x, w.from[0], w.to[0]), w.from[1]];
  if (w.from[0] === w.to[0]) return [w.from[0], clamp(y, w.from[1], w.to[1])];
  // a slanted wire (old files): its nearer end
  return Math.hypot(x - w.from[0], y - w.from[1]) <= Math.hypot(x - w.to[0], y - w.to[1]) ? w.from : w.to;
}

/**
 * Each wire end in a circuit view, once per point, with what it touches: `pin` (a part's
 * pin or a label: drawn as a filled ball), `bend` (only other wires: no ball, but still
 * a handle) or `loose` (nothing: an open ball, it isn't connected).
 * @param {{parts: any[], labels: any[], wires: any[]}} view
 * @returns {Array<{pos: number[], net: string, kind: "pin" | "bend" | "loose"}>}
 */
export function wireEnds(view) {
  const key = (/** @type {number[]} */ p) => p.join(",");
  const anchors = new Set([...view.parts.flatMap((p) => p.pins.map((/** @type {any} */ pin) => key(pin.pos))), ...view.labels.map((lb) => key(lb.pos))]);
  /** @type {Map<string, {pos: number[], net: string, count: number}>} */
  const ends = new Map();
  for (const w of view.wires) {
    for (const pos of [w.from, w.to]) {
      const k = key(pos);
      const seen = ends.get(k);
      if (seen) seen.count += 1;
      else ends.set(k, { pos, net: w.net ?? "", count: 1 });
    }
  }
  const onAnotherWire = (/** @type {number[]} */ p) => view.wires.some((w) => !same(w.from, p) && !same(w.to, p) && same(pointOnWire(w, p), p) && (w.from[0] === w.to[0] || w.from[1] === w.to[1]));
  return [...ends.values()].map(({ pos, net, count }) => ({
    pos,
    net,
    kind: anchors.has(key(pos)) ? "pin" : count > 1 || onAnotherWire(pos) ? "bend" : "loose",
  }));
}

/**
 * @param {Circuit} circuit @param {string} net @param {number[]} pos
 * @param {number} [rot] a supply symbol's turn (ground, a rail), clockwise (D-117)
 */
export function addLabel(circuit, net, pos, rot = 0) {
  return { ...circuit, labels: [...(circuit.labels ?? []), { net, pos: snapPoint(pos), ...(rot ? { rot } : {}) }] };
}

/**
 * Turn label `index` (a supply's symbol) a quarter turn clockwise about its point (D-117):
 * its net and connection stay as they are.
 * @param {Circuit} circuit @param {number} index
 */
export function rotateLabel(circuit, index) {
  return {
    ...circuit,
    labels: (circuit.labels ?? []).map((lb, i) => {
      if (i !== index) return lb;
      const { rot: _old, ...rest } = lb;
      const rot = ((lb.rot ?? 0) + 90) % 360;
      return rot ? { ...rest, rot } : rest;
    }),
  };
}

/**
 * A text block's words as the file keeps them: trailing space trimmed, empty fields left
 * out. @param {{title?: string, text?: string}} words
 */
const wordsOf = ({ title = "", text = "" }) => ({
  ...(title.trim() ? { title: title.trim() } : {}),
  ...(text.trimEnd() ? { text: text.trimEnd() } : {}),
});

/**
 * Put a text block on the sheet (D-091): `pos` is its top-left corner, snapped. Nothing
 * is added when both the title and the text are empty.
 * @param {Circuit} circuit @param {{title?: string, text?: string}} words @param {number[]} pos
 */
export function addText(circuit, words, pos) {
  const kept = wordsOf(words);
  if (!kept.title && !kept.text) return circuit;
  return { ...circuit, texts: [...(circuit.texts ?? []), { ...kept, pos: snapPoint(pos) }] };
}

/**
 * Change a text block's title and text; both empty removes the block.
 * @param {Circuit} circuit @param {number} index @param {{title?: string, text?: string}} words
 */
export function setText(circuit, index, words) {
  const kept = wordsOf(words);
  if (!kept.title && !kept.text) return deleteItems(circuit, { texts: [index] });
  return { ...circuit, texts: (circuit.texts ?? []).map((t, i) => (i === index ? { ...kept, pos: t.pos } : t)) };
}

/**
 * Rename one label. When it was the last label naming its net, the net's note follows the
 * new name (unless that name has a note of its own).
 * @param {Circuit} circuit @param {number} index @param {string} net
 */
export function renameLabel(circuit, index, net) {
  const from = circuit.labels?.[index]?.net;
  const labels = (circuit.labels ?? []).map((lb, i) => (i === index ? { ...lb, net } : lb));
  const out = { ...circuit, labels };
  const notes = circuit.net_notes ?? {};
  if (from && from !== net && from in notes && !(net in notes) && !labels.some((lb) => lb.net === from)) {
    out.net_notes = Object.fromEntries(Object.entries(notes).map(([k, v]) => [k === from ? net : k, v]));
  }
  return out;
}

/**
 * Set fields on a part; a field set to null or undefined is removed (back to its default).
 * @param {Circuit} circuit @param {string} ref @param {Record<string, unknown>} patch
 */
export function updatePart(circuit, ref, patch) {
  const parts = circuit.parts.map((p) => {
    if (p.ref !== ref) return p;
    const next = { ...p, ...patch };
    for (const [k, v] of Object.entries(patch)) if (v === null || v === undefined) delete next[k];
    return next;
  });
  return { ...circuit, parts };
}

/**
 * Change a part's ref, and everything that names it (its note is on it): bias targets and probes
 * that point at its pins (`Q1.D`), and dismissed problems (its ref, nets named after its
 * pins, D-176).
 * @param {Circuit} circuit @param {string} from @param {string} to
 */
export function renamePart(circuit, from, to) {
  if (from === to) return circuit;
  const pin = (/** @type {string | undefined} */ name) => (name?.startsWith(`${from}.`) ? `${to}${name.slice(from.length)}` : name);
  const parts = circuit.parts.map((p) => {
    const q = p.ref === from ? { ...p, ref: to } : p;
    return q.bias_target ? { ...q, bias_target: { ...q.bias_target, node: pin(q.bias_target.node) } } : q;
  });
  const out = { ...circuit, parts };
  if (circuit.dismissed) {
    out.dismissed = circuit.dismissed.map((/** @type {any} */ d) => ({
      ...d,
      ...(d.refs ? { refs: d.refs.map((/** @type {string} */ r) => (r === from ? to : r)) } : {}),
      ...(d.nets ? { nets: d.nets.map(pin) } : {}),
    }));
  }
  if (circuit.probes) out.probes = Object.fromEntries(Object.entries(circuit.probes).map(([k, v]) => [k, pin(v)]));
  return out;
}

/**
 * Set or clear the trimmer that biases a JFET's or MOSFET's drain (`bias_target` on the
 * trimmer, node `REF.D`). Any other trimmer aimed at that drain loses its target.
 * @param {Circuit} circuit @param {string} ref @param {string | null} trimmer @param {number | null} volts
 */
export function setDrainTarget(circuit, ref, trimmer, volts) {
  const node = `${ref}.D`;
  const parts = circuit.parts.map((p) => {
    if (p.type !== "trimmer") return p;
    if (p.ref === trimmer && volts !== null) return { ...p, bias_target: { node, volts } };
    if (p.bias_target?.node === node) {
      const { bias_target: _gone, ...rest } = p;
      return rest;
    }
    return p;
  });
  return { ...circuit, parts };
}

/**
 * The trimmer and volts aimed at a JFET's or MOSFET's drain, if any.
 * @param {Circuit} circuit @param {string} ref
 * @returns {{trimmer: string, volts: number} | null}
 */
export function drainTarget(circuit, ref) {
  const t = circuit.parts.find((p) => p.type === "trimmer" && p.bias_target?.node === `${ref}.D`);
  return t ? { trimmer: t.ref, volts: t.bias_target.volts } : null;
}

/**
 * The trimmers whose bias target an edit gives or changes (not one it takes off): each is
 * checked against how far it reaches before the edit goes in (D-127).
 * @param {Circuit} before @param {Circuit} after @returns {string[]}
 */
export function movedTargets(before, after) {
  const was = new Map(before.parts.map((p) => [p.ref, JSON.stringify(p.bias_target ?? null)]));
  return after.parts.filter((p) => p.type === "trimmer" && p.bias_target && was.get(p.ref) !== JSON.stringify(p.bias_target)).map((p) => p.ref);
}

/**
 * "4k7, 10k ,22k" → ["4k7", "10k", "22k"] (the server parses the values).
 * @param {string} text
 */
export function splitValues(text) {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

/**
 * The only supply rails (D-069, D-071): V+ is positive, V- negative. The server refuses
 * a file with any other (`schema.SUPPLY_SIGNS`).
 */
export const SUPPLIES = /** @type {const} */ ({ "V+": 1, "V-": -1 });

/**
 * Give every label (an op-amp's power pins' too, D-140) and block port on net `from` the
 * name `to`. @param {Circuit} circuit @param {string} from @param {string} to
 */
function renameNet(circuit, from, to) {
  const n = (/** @type {string} */ net) => (net === from ? to : net);
  return {
    ...circuit,
    labels: (circuit.labels ?? []).map((lb) => (lb.net === from ? { ...lb, net: to } : lb)),
    ...(circuit.ports ? { ports: Object.fromEntries(Object.entries(circuit.ports).map(([k, v]) => [k, n(v)])) } : {}),
  };
}

/**
 * What on the sheet uses net `net` ("3 labels"), or "" when nothing does.
 * @param {Circuit} circuit @param {string} net
 */
function netUses(circuit, net) {
  const labels = (circuit.labels ?? []).filter((lb) => lb.net === net).length;
  return labels ? `${labels} label${labels > 1 ? "s" : ""}` : "";
}

/**
 * Set the supply rails from the Power dialog (D-069): V+ and V- → volts as typed, "" for
 * none. Each takes a size (its sign is fixed: "9" on V- is −9 V). A rail turned off takes
 * its labels and op-amp supplies to the rail left (V- off, V+ on: a V- bar becomes V+);
 * with no rail left it's refused while still in use. Throws with a plain message.
 * @param {Circuit} circuit @param {Partial<Record<keyof typeof SUPPLIES, string>>} entries
 * @returns {Circuit}
 */
export function setRails(circuit, entries) {
  /** @type {Record<string, number>} */
  const rails = {};
  for (const [name, text] of Object.entries(entries)) {
    const t = text.trim().replace(/\s*V$/i, "").replace("\u2212", "-");
    if (!t) continue;
    const v = Number(t);
    if (!Number.isFinite(v) || v === 0) throw new Error(`${name}: give a voltage like 9, or leave it empty for none.`);
    const sign = SUPPLIES[/** @type {keyof typeof SUPPLIES} */ (name)];
    if (sign === 1 && v < 0) throw new Error("V+ is the positive supply. For a negative one, fill in V- instead.");
    rails[name] = sign * Math.abs(v);
  }
  const before = circuit.power?.rails ?? {};
  const gone = Object.keys(before).filter((n) => !(n in rails));
  let next = { ...circuit, power: { ...circuit.power, rails } };
  const [heir] = Object.keys(rails); // gone ones leave at most one rail
  for (const net of gone) {
    const uses = netUses(circuit, net);
    if (!uses) continue;
    // hand them on only when that's a change of polarity: an heir already in use would
    // join two supplies (± → 9 V with both in use, D-093)
    if (heir && !netUses(circuit, heir)) next = renameNet(next, net, heir);
    else throw new Error(`${net} is still used on the sheet (${uses}). Keep ${net}, or delete those first.`);
  }
  return next;
}

/**
 * Drop a Supply tile: a label on rail `net`, adding that rail when the circuit hasn't got
 * it (the size of the main rail, or 9 V), so a V- bar is always a supply (D-069).
 * @param {Circuit} circuit @param {string} net @param {number[]} pos @param {number} [rot]
 */
export function addSupply(circuit, net, pos, rot = 0) {
  const rails = circuit.power?.rails ?? {};
  const withRail = net in rails
    ? circuit
    : { ...circuit, power: { ...circuit.power, rails: { ...rails, [net]: SUPPLIES[/** @type {keyof typeof SUPPLIES} */ (net)] * Math.abs(mainRail(circuit)?.[1] ?? 9) } } };
  return addLabel(withRail, net, pos, rot);
}
