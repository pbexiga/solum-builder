/**
 * The Frequency panel's layers (Phase 8b, D-097), no DOM: which layers are on, the marks
 * they put on the plot, and the curves part influence needs. Every measure (knees, peaks,
 * knob bands, what a part moves) comes from the server (`solum.analysis.measures` and
 * `compare`); the browser only solves the nudged curves, with `solver.js`.
 */

import { remember, remembered } from "./storage.js";
import { solveNodes, toDb } from "./solver.js";

/** The layers, in menu order. */
export const LAYERS = [
  { id: "knees", label: "Knees" },
  { id: "peaks", label: "Peaks and dips" },
  { id: "knobs", label: "Knob ranges" },
  { id: "influence", label: "Part influence" },
];

const STORE_KEY = "solum.layers";
/** Where the expanded view's layers are kept: its own set, all on until changed. */
export const EXPANDED_KEY = "solum.layers.expanded";

/**
 * The layers turned on last time in this browser (`fallback` when none were saved or
 * storage is blocked).
 * @param {Storage | null} [storage] undefined: the browser's own @param {string} [key] @param {string[]} [fallback]
 * @returns {Set<string>}
 */
export function loadLayers(storage, key = STORE_KEY, fallback = []) {
  const saved = remembered(key, storage);
  if (!Array.isArray(saved)) return new Set(fallback);
  return new Set(saved.filter((id) => LAYERS.some((l) => l.id === id)));
}

/** @param {Set<string>} layers @param {Storage | null} [storage] @param {string} [key] */
export function saveLayers(layers, storage, key = STORE_KEY) {
  remember(key, [...layers], storage);
}

/**
 * @typedef {{side: string, f: number, db?: number, simple: boolean, text: string}} KneeFeature
 * @typedef {{f: number, db: number, text: string}} PointFeature
 * @typedef {{shape: string, knees: KneeFeature[], peaks: PointFeature[], dips: PointFeature[]}} Features
 * @typedef {{lo: number, hi: number, centre?: number, kind?: string, text?: string}} Band
 * @typedef {{lines: Array<{x: number, label: string}>, points: Array<{x: number, y: number, kind: "peak" | "dip", label: string}>,
 *   bands: Band[], at: number | null, levels: Array<{y: number, label?: string}>, handles: HandleMark[], before?: Before | null}} Marks
 * @typedef {{x: number[], y: number[], dots: Array<{x: number, y: number}>}} Before Edit mode's curve and dots as they were when it started, drawn faint under the curve
 * @typedef {{id: string, ids: string[], x: number, y: number, label: string, active: boolean, idle: boolean}} HandleMark
 *   `ids`: the handles sharing this dot (`id` first: the one it stands for); `idle`: no label, nothing moves them this way (drawn faint)
 */

/** No marks. @returns {Marks} */
export const noMarks = () => ({ lines: [], points: [], bands: [], at: null, levels: [], handles: [], before: null });

/**
 * What the Knees and Peaks layers draw for a curve's features: a dashed line per knee,
 * labelled with its frequency ("−3 dB below peak" when the curve isn't a simple filter, so
 * it isn't read as a band corner), and a marker per peak and dip.
 * @param {Features | null} features @param {Set<string>} layers
 * @returns {Marks}
 */
export function curveMarks(features, layers) {
  const marks = noMarks();
  if (!features) return marks;
  if (layers.has("knees")) {
    for (const k of features.knees) marks.lines.push({ x: k.f, label: k.simple ? k.text : `${k.text} (−3 dB below peak)` });
  }
  if (layers.has("peaks")) {
    for (const p of features.peaks) marks.points.push({ x: p.f, y: p.db, kind: "peak", label: p.text });
    for (const d of features.dips) marks.points.push({ x: d.f, y: d.db, kind: "dip", label: d.text });
  }
  return marks;
}

/**
 * The knob ranges' rows: each knob's name and where it acts, as the server read it.
 * @param {{knobs: Array<{ref: string, label: string, text: string, band: Band | null, valid: boolean}>} | null} ranges
 * @returns {Array<{ref: string, label: string, text: string, band: Band | null, title: string}>}
 */
export function knobRows(ranges) {
  return (ranges?.knobs ?? []).map((k) => ({
    ref: k.ref,
    label: k.label,
    text: k.text,
    band: k.band,
    title: k.valid ? "" : "A stage saturates at one end of this knob, so the curve there isn't trustworthy.",
  }));
}

/**
 * @typedef {{ref: string, elements: Record<string, number>, bias: boolean, knob?: boolean}} Nudge
 * @typedef {import("./live.js").Live & {nudge: number, nudges: Nudge[]}} NudgeLive
 */

/**
 * The curve at `net` (dB per frequency) and the same curve with each part nudged, from
 * the browser's solver: what `/api/influence` ranks. `values` are the sliders' element
 * values (empty: the circuit as it is).
 * @param {NudgeLive} live @param {string} net @param {Record<string, number>} [values]
 * @returns {{freq: number[], base: number[], nudged: Record<string, number[]>} | null} null without a system or net
 */
export function nudgedCurves(live, net, values = {}) {
  if (!live.system || !(net in live.nets)) return null;
  const node = [live.nets[net]];
  const base = toDb(solveNodes(live.system, values, node)[0]);
  /** @type {Record<string, number[]>} */
  const nudged = {};
  for (const n of live.nudges) nudged[n.ref] = toDb(solveNodes(live.system, { ...values, ...n.elements }, node)[0]);
  return { freq: live.system.freq, base, nudged };
}

/**
 * The influence rows to show, each with what it means for a part that also sets a bias.
 * @param {{rows: Array<{ref: string, size: number, change: number, at: number | null, what: string, text: string, band: Band | null}>, hidden: string[]}} result
 * @param {Nudge[]} nudges
 */
export function influenceRows(result, nudges) {
  const bias = new Set(nudges.filter((n) => n.bias).map((n) => n.ref));
  return result.rows.map((r) => ({
    ...r,
    bias: bias.has(r.ref),
    sizeText: `${(r.at ?? r.change) < 0 ? "−" : "+"}${Math.abs(r.at ?? r.change).toFixed(1)} dB`,
  }));
}

// ---- Edit mode's handles (Phase 8b): a dot on each knee, peak and dip; dragging one
// changes the part that moves it. What moves what, and by how much, is the server's
// (`compare.handles`); the page only picks a part and turns a frequency into a step.

/**
 * @typedef {{ref: string, exponent: number, change: number}} HandlePart
 * @typedef {{refs: string[], weights: number[], slope: number, spill: number, pulls?: number[][]}} LevelMove `pulls`: each part's [exponent, slope]
 * @typedef {HandlePart & {kept?: boolean}} RowPart a handle's part as its row offers it (`kept`: changed this session, kept listed though it barely moves it now)
 * @typedef {{id: string, kind: "knee" | "peak" | "dip", side: string | null, f: number, db: number,
 *   label: string, text: string, parts: HandlePart[], levels?: LevelMove[]}} Handle
 */

const SAME_DOT_OCTAVES = 1 / 6; // handles closer than this share one dot
const SAME_PEAK_OCTAVES = 1 / 3; // a peak within this of where it was is the same peak (compare.MATCH_OCTAVES)

const ROOM_DB = 10; // the level axis: room above and below the curve (to drag into in Edit curve)
const NOISE_DB = 0.1; // a measured level change under this says nothing about the way it goes
const WHOLE_SPILL = 0.9; // a level move changing the curve an octave away this much moves all of it ("whole curve")

const CLOSE_PULL = 0.8; // a part moving a handle this much of the best one's is as good a choice

/**
 * The part a handle moves unless one was picked: the first (the server's order) that isn't
 * a knob and doesn't set a bias, else the first; null when nothing moves it. `taken`:
 * parts other handles already move; one of those is passed over for a part that moves
 * this handle nearly as much (CLOSE_PULL), so each dot names its own part where it can.
 * @param {Handle} handle @param {Nudge[]} nudges @param {string} [picked] @param {Set<string>} [taken]
 * @returns {string | null}
 */
export function handlePart(handle, nudges, picked, taken = new Set()) {
  if (picked && handle.parts.some((p) => p.ref === picked)) return picked;
  const by = new Map(nudges.map((n) => [n.ref, n]));
  // a part kept listed only because it was changed (`rowParts`) is never the default
  const plain = handle.parts.filter((p) => !by.get(p.ref)?.bias && !by.get(p.ref)?.knob && !(/** @type {RowPart} */ (p).kept));
  const best = plain[0] ?? handle.parts[0];
  if (!best) return null;
  const free = plain.find((p) => !taken.has(p.ref) && Math.abs(p.exponent) >= CLOSE_PULL * Math.abs(best.exponent));
  return (free ?? best).ref;
}

/**
 * Every handle's part (`handlePart`), knees first, each passing over parts taken before it.
 * @param {Handle[]} handles @param {Nudge[]} nudges @param {Map<string, string>} picked handle id → part picked
 * @returns {Record<string, string | null>}
 */
export function handleParts(handles, nudges, picked) {
  const taken = new Set([...picked.values()]);
  /** @type {Record<string, string | null>} */
  const out = {};
  for (const h of handles) {
    const own = picked.get(h.id);
    if (own) taken.delete(own);
    const ref = handlePart(h, nudges, own, taken);
    out[h.id] = ref;
    if (ref) taken.add(ref);
  }
  return out;
}

/**
 * Where a handle is on a (moved) curve: its knee by side, or the peak or dip nearest
 * where it was (the only one, when the curve has one and it moved further). Null when the
 * curve no longer has it.
 * @param {Handle} handle @param {Features | null} features
 * @returns {{f: number, db: number, text: string} | null}
 */
export function handleAt(handle, features) {
  if (!features) return null;
  if (handle.kind === "knee") {
    const k = features.knees.find((x) => x.side === handle.side && x.simple);
    return k && k.db !== undefined ? { f: k.f, db: k.db, text: k.text } : null;
  }
  const all = handle.kind === "peak" ? features.peaks : features.dips;
  const near = all.length === 1 ? [...all] : all.filter((p) => Math.abs(Math.log2(p.f / handle.f)) <= SAME_PEAK_OCTAVES);
  near.sort((a, b) => Math.abs(Math.log(a.f / handle.f)) - Math.abs(Math.log(b.f / handle.f)));
  return near[0] ? { f: near[0].f, db: near[0].db, text: near[0].text } : null;
}

/**
 * The dots Edit mode draws: one per handle where the curve has it now (none for a handle
 * it has lost: its row says why, `lostReason`; before any curve, where the handle was),
 * labelled with its part (blank when no one part moves it: the dot still shows, faint, so
 * the plot and the list agree). Handles closer than SAME_DOT_OCTAVES share one dot, drawn
 * as a double ring and labelled with each one's part ("C3 · C5"), so a crowded curve stays
 * readable and still says what's there; it stands for the active one, else the first.
 * @param {Handle[]} handles @param {Features | null} features @param {Record<string, string | null>} parts handle id → its part
 * @param {string | null} active
 * @returns {HandleMark[]}
 */
export function handleMarks(handles, features, parts, active) {
  const placed = handles
    .map((h) => ({ h, at: features ? handleAt(h, features) : { f: h.f, db: h.db } }))
    .filter((x) => x.at)
    .map((x) => ({ h: x.h, at: /** @type {{f: number, db: number}} */ (x.at) }));
  /** @type {Array<typeof placed>} */
  const groups = [];
  for (const p of [...placed].sort((a, b) => a.at.f - b.at.f)) {
    const last = groups[groups.length - 1];
    if (last && Math.abs(Math.log2(p.at.f / last[0].at.f)) < SAME_DOT_OCTAVES) last.push(p);
    else groups.push([p]);
  }
  return groups.map((g) => {
    const p = g.find((x) => x.h.id === active) ?? g[0];
    const ids = [p.h.id, ...g.filter((x) => x !== p).map((x) => x.h.id)];
    const label = [...new Set(ids.map((id) => parts[id]).filter(Boolean))].join(" \u00b7 ");
    return { id: p.h.id, ids, x: p.at.f, y: p.at.db, label, active: p.h.id === active, idle: !label };
  });
}

/**
 * Which of a dot's handles a drag takes: Shift+drag (up/down) the first that has a level
 * move (a knee never does), else the one the dot stands for.
 * @param {HandleMark} mark @param {Handle[]} handles @param {boolean} shift
 */
export function grabbed(mark, handles, shift) {
  if (!shift) return mark.id;
  return mark.ids.find((id) => handles.find((h) => h.id === id)?.levels?.length) ?? mark.id;
}

/**
 * Why a handle has no dot on this curve, in a few plain words for its row; null when it has
 * one. A knee is a handle only on a simple curve (one band): with a second bump it's just
 * a point 3 dB under the top, not a corner.
 * @param {Handle} handle @param {Features | null} features
 * @returns {string | null}
 */
export function lostReason(handle, features) {
  if (!features || handleAt(handle, features)) return null;
  if (handle.kind === "knee") {
    const knee = features.knees.find((k) => k.side === handle.side);
    return knee ? "not a corner now: the curve has more than one bump" : "gone: the curve doesn't roll off on this side now";
  }
  const all = handle.kind === "peak" ? features.peaks : features.dips;
  return all.length ? `lost: it moved too far from where it was, among ${all.length} ${handle.kind}s` : `gone: the curve has no ${handle.kind} now`;
}

/**
 * A handle's parts as its row offers them: the server's, then any part changed this
 * session that moved it earlier and has dropped off (it barely moves it at its new value),
 * so a change can always be dragged back.
 * @param {Handle} handle @param {Map<string, HandlePart>} seen parts that moved it this session
 * @param {Set<string>} changed refs changed this session
 * @returns {RowPart[]}
 */
export function rowParts(handle, seen, changed) {
  const listed = new Set(handle.parts.map((p) => p.ref));
  const kept = [...seen.values()].filter((p) => changed.has(p.ref) && !listed.has(p.ref)).map((p) => ({ ...p, kept: true }));
  return [...handle.parts, ...kept];
}

/**
 * The step nearest `want` (SI); `end`: `want` is past the steps, so it stops at an end.
 * @param {number[]} values @param {number} want
 * @returns {{index: number, end: boolean}}
 */
function nearestValueStep(values, want) {
  let index = 0;
  values.forEach((v, i) => {
    if (Math.abs(Math.log(v / want)) < Math.abs(Math.log(values[index] / want))) index = i;
  });
  const end = (index === 0 && want < values[0]) || (index === values.length - 1 && want > values[values.length - 1]);
  return { index, end };
}

/**
 * The step a drag to `target` Hz asks for: the value that puts the handle there, from the
 * last place it was measured (`known`: a value and the frequency it gave) and how the
 * frequency follows the value (`exponent`, d log f / d log value), the nearest step to it.
 * `end`: the target is past the slider's range, so it stops at an end.
 * @param {number[]} values the steps' values (SI) @param {{v: number, f: number}} known
 * @param {number} target @param {number} exponent
 * @returns {{index: number, end: boolean}}
 */
export function seekStep(values, known, target, exponent) {
  return nearestValueStep(values, known.v * (target / known.f) ** (1 / exponent));
}

/**
 * Where a drag asks a handle to go: where it was (`was`) moved by as much as the pointer
 * has moved since the grab, so grabbing a dot off-centre doesn't jump it. Sideways ("x")
 * a ratio, as the frequency axis is log; up/down ("y") in dB.
 * @param {"x" | "y"} axis @param {{f: number, db: number}} was
 * @param {{x: number, y: number}} grab @param {{x: number, y: number}} point the pointer, as plot values
 */
export function dragTarget(axis, was, grab, point) {
  return axis === "x" ? was.f * (point.x / grab.x) : was.db + (point.y - grab.y);
}

/**
 * Edit mode's faint dots for where the knees, peaks and dips were when it started: each
 * corner knee (one with a level), each peak and dip.
 * @param {Features | null} features
 * @returns {Array<{x: number, y: number}>}
 */
export function startDots(features) {
  if (!features) return [];
  const knees = features.knees.filter((k) => k.simple && k.db !== undefined).map((k) => ({ x: k.f, y: /** @type {number} */ (k.db) }));
  return [...knees, ...[...features.peaks, ...features.dips].map((p) => ({ x: p.f, y: p.db }))];
}

// The Frequency plot's bands (D-102): it shows 10 Hz - 30 kHz (the server's PLOT_BAND,
// FabFilter Pro-Q's range), shades outside 20 Hz - 20 kHz lightly, and fits its level axis
// to the curves inside that audible band (the ends may run off the plot).
export const PLOT_BAND = /** @type {[number, number]} */ ([10, 30000]);
export const AUDIBLE = /** @type {[number, number]} */ ([20, 20000]);

/**
 * The lowest and highest level over every series, inside the audible band only; null
 * when there's nothing to fit.
 * @param {{x: number[], series: Array<{values: Array<number | null>}>}} data
 * @returns {[number, number] | null}
 */
export function audibleLevels(data) {
  let lo = Infinity;
  let hi = -Infinity;
  data.x.forEach((f, i) => {
    if (f < AUDIBLE[0] || f > AUDIBLE[1]) return;
    for (const s of data.series) {
      const v = s.values[i];
      if (v === null || v === undefined || !Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  });
  return lo <= hi ? [lo, hi] : null;
}

/**
 * The Frequency plot's level axis, the same in and out of Edit curve so switching doesn't
 * look like a zoom (D-102): `heldRange` of the audible levels. A fresh plot fits afresh; a
 * live one (a slider moving) and Edit curve only widen what's there, so the axis holds still.
 * @param {[number, number] | null} range what's drawn now @param {{x: number[], series: Array<{values: Array<number | null>}>}} data @param {boolean} hold
 * @returns {[number, number] | null}
 */
export function levelAxis(range, data, hold) {
  const levels = audibleLevels(data);
  if (!levels) return range;
  return heldRange(hold ? range : null, levels[0], levels[1]);
}

/**
 * Edit mode's level axis, held still so a drag shows how far the curve moves (an axis
 * that follows the curve keeps a raised peak at the top edge): `lo`–`hi` with ROOM_DB
 * either side, on 5 dB lines; once set it stays, and only widens (by the same room) when
 * a curve leaves it.
 * @param {[number, number] | null} range @param {number} lo @param {number} hi
 * @returns {[number, number]}
 */
export function heldRange(range, lo, hi) {
  if (range && lo >= range[0] && hi <= range[1]) return range;
  const down = Math.floor((lo - ROOM_DB) / 5) * 5;
  const up = Math.ceil((hi + ROOM_DB) / 5) * 5;
  return range ? [Math.min(range[0], down), Math.max(range[1], up)] : [down, up];
}

/** A level move's key (its parts), for the row's menu. @param {LevelMove} move */
export const levelKey = (move) => move.refs.join("+");

/**
 * The level move a peak or dip uses: the one picked in its row, else the server's first
 * (least spill); null for a knee, or when no part moves just its level.
 * @param {Handle} handle @param {string} [picked] a `levelKey`
 * @returns {LevelMove | null}
 */
export function levelMove(handle, picked) {
  const all = handle.levels ?? [];
  return all.find((m) => levelKey(m) === picked) ?? all[0] ?? null;
}

/**
 * A level move as its row's menu shows it: each part with the way it goes to raise the
 * peak ("C3 ↑ R4 ↓"), and "whole curve" when it changes the level an octave away about as
 * much as at the peak (WHOLE_SPILL): more a gain change than a sharper or flatter peak.
 * @param {LevelMove} move
 */
export function levelText(move) {
  const parts = move.refs.map((r, i) => `${r} ${move.weights[i] > 0 ? "\u2191" : "\u2193"}`).join(" ");
  return move.spill >= WHOLE_SPILL ? `${parts} \u00b7 whole curve` : parts;
}

/**
 * The steps a drag to `target` dB asks for: from the last place it was measured
 * (`known`: each part's value and where the peak was), the nearest step of each part's
 * value. With `hold` (a frequency) and a two-part move's `pulls`, both parts' log values
 * solve the level still to go and the way back to `hold` together (each part's slope
 * scaled by what the drag has measured: `move.slope` over the pulls' own), so a big move
 * stays in place; otherwise each changes by its weight x t, t = the dB to go / slope.
 * `end`: a part is at an end of its steps.
 * @param {number[][]} values each part's steps (SI) @param {{v: number[], db: number, f?: number}} known
 * @param {number} target @param {LevelMove} move @param {number | null} [hold]
 * @returns {{indices: number[], end: boolean}}
 */
export function seekLevel(values, known, target, move, hold = null) {
  const logs = levelLogs(known, target, move, hold);
  const found = values.map((steps, k) => nearestValueStep(steps, known.v[k] * Math.exp(logs[k])));
  return { indices: found.map((f) => f.index), end: found.some((f) => f.end) };
}

/** Each part's change in log value for `seekLevel`. @param {{v: number[], db: number, f?: number}} known @param {number} target @param {LevelMove} move @param {number | null} hold */
function levelLogs(known, target, move, hold) {
  const t = (target - known.db) / move.slope;
  const along = move.weights.map((w) => w * t);
  if (hold === null || !known.f || move.pulls?.length !== 2) return along;
  const [[e1, s1], [e2, s2]] = move.pulls;
  const scale = move.slope / (move.weights[0] * s1 + move.weights[1] * s2); // the measured slope over the guessed one
  const [a, b, c, d] = [e1, e2, s1 * scale, s2 * scale];
  const det = a * d - b * c;
  if (!Number.isFinite(det) || Math.abs(det) < 1e-9) return along;
  const toF = Math.log(hold / known.f);
  const toDb = target - known.db;
  return [(d * toF - b * toDb) / det, (a * toDb - c * toF) / det];
}

/**
 * A level move after a drag measured where its parts put the peak: its slope taken from how
 * far the level really went between the two measured points (a secant), so the next steps
 * land where the drag points even where the +10 % estimate is off. `wrong`: the level went
 * the other way by more than NOISE_DB (past here these parts lower it), so the drag stops
 * there. A change under NOISE_DB keeps the slope as it was.
 * @param {LevelMove} move @param {{v: number[], db: number}} before @param {{v: number[], db: number}} after
 * @returns {{move: LevelMove, wrong: boolean}}
 */
export function measuredSlope(move, before, after) {
  const k = move.weights.reduce((best, w, i) => (Math.abs(w) > Math.abs(move.weights[best]) ? i : best), 0);
  const t = Math.log(after.v[k] / before.v[k]) / move.weights[k];
  const change = after.db - before.db;
  if (!Number.isFinite(t) || t === 0 || Math.abs(change) < NOISE_DB) return { move, wrong: false };
  return change / t > 0 ? { move: { ...move, slope: change / t }, wrong: false } : { move, wrong: true };
}

/**
 * The parts changed between two circuits: each part in both whose `fields` differ (its
 * value by default, as Edit curve changes only values), as it was and as it is, written
 * as the part form writes them ("47n", "1N34A", "88 %", "Q1.D 4 V", "none"). Edit
 * curve's and Try changes' Changed lists (D-123).
 * @param {{parts: Array<Record<string, any>>} | null} before
 * @param {{parts: Array<Record<string, any>>} | null} after
 * @param {string[]} [fields]
 * @returns {Array<{ref: string, field: string, from: string, to: string}>}
 */
export function curveChanges(before, after, fields = ["value"]) {
  if (!before || !after) return [];
  const was = new Map(before.parts.map((p) => [p.ref, p]));
  return after.parts.flatMap((p) => {
    const old = was.get(p.ref);
    if (!old) return [];
    return fields
      .filter((f) => (f !== "value" || p.value !== undefined) && fieldText(f, old[f]) !== fieldText(f, p[f]))
      .map((f) => ({ ref: p.ref, field: f, from: fieldText(f, old[f]), to: fieldText(f, p[f]) }));
  });
}

/** A part's field as a changes list writes it. @param {string} field @param {any} v */
function fieldText(field, v) {
  if (v === undefined || v === null) return field === "rotation" ? "50 %" : "none";
  if (field === "rotation") return `${Math.round(v * 100)} %`;
  if (field === "bias_target") return `${v.node} ${v.volts} V`;
  return String(v);
}

/**
 * What Edit curve's Changed list says about each change, from the session's steps
 * (`History.sessionSteps`): `partners` ref → the other parts changed in the same step, per
 * step it changed in (a Shift-drag changes two); `outside` refs changed by a step not made
 * in Edit curve; `others` the labels of outside steps that did more than change values
 * (a part moved, a wire drawn): Keep and Discard take those too.
 * @param {Array<{label: string, source: string, before: any, after: any}>} steps
 * @returns {{partners: Map<string, string[][]>, outside: Set<string>, others: string[]}}
 */
export function changeLinks(steps) {
  /** @type {Map<string, string[][]>} */
  const partners = new Map();
  const outside = new Set();
  const others = [];
  for (const step of steps) {
    const refs = curveChanges(step.before, step.after).map((c) => c.ref);
    for (const ref of refs) {
      const others_ = refs.filter((r) => r !== ref);
      if (others_.length) partners.set(ref, [...(partners.get(ref) ?? []), others_]);
      if (step.source !== "curve") outside.add(ref);
    }
    if (step.source !== "curve" && !valuesOnly(step.before, step.after)) others.push(step.label);
  }
  return { partners, outside, others };
}

/** The two circuits differ only in part values. @param {any} a @param {any} b */
function valuesOnly(a, b) {
  const strip = (/** @type {any} */ c) => JSON.stringify({ ...c, parts: c.parts.map((/** @type {any} */ p) => ({ ...p, value: null })) });
  return strip(a) === strip(b);
}

/**
 * The hover for a part changed along with others: "Changed together with R4; then with
 * C5", and which of them have been put back since (`now`: the refs changed now).
 * @param {string[][]} withEach @param {Set<string>} now
 */
export function partnerText(withEach, now) {
  const each = withEach.map((refs, i) => `${i ? "then with" : "Changed together with"} ${refs.join(" and ")}`).join("; ");
  const back = [...new Set(withEach.flat())].filter((r) => !now.has(r));
  return `${each}.${back.length ? ` ${back.join(", ")} ${back.length > 1 ? "were" : "was"} put back.` : ""} Ctrl+Z or History undoes a whole step.`;
}
