/**
 * Live curves while a value slider or a knob moves (D-012, D-079, D-081), no DOM. The
 * server sends the circuit's linear system and, per slider, steps that carry the element
 * values they set; moving a slider here changes only those values, `solver.js` re-solves
 * at once, and ngspice re-runs once the slider is let go.
 */

import { db } from "./fixed.js";
import { solveNodes, toDb } from "./solver.js";

/**
 * @typedef {{value: string | number, si?: number, text: string, elements: Record<string, number>}} Step
 * @typedef {{ref: string, field: "value" | "rotation", series: string | null, index: number,
 *   nearest: string | null, steps: Step[]}} Slider
 * @typedef {{system: import("./solver.js").System | null, nets: Record<string, number>,
 *   sliders: Slider[], valid: boolean}} Live
 */

/** A slider's key, as the server's `steps` request field names it. @param {{ref: string, field: string}} s */
export const sliderKey = (s) => `${s.ref}.${s.field}`;

/**
 * The element values for the sliders' current steps: what `solve` takes in place of the
 * system's own.
 * @param {Slider[]} sliders @param {number[]} indices
 * @returns {Record<string, number>}
 */
export function liveValues(sliders, indices) {
  /** @type {Record<string, number>} */
  const values = {};
  sliders.forEach((s, i) => Object.assign(values, s.steps[indices[i]]?.elements ?? {}));
  return values;
}

/**
 * The curves (dB per frequency) at every net the live view knows, with `values` in place.
 * @param {Live} live @param {Record<string, number>} values
 * @returns {{freq: number[], nodes: Record<string, number[]>} | null} null without a system
 */
export function liveCurves(live, values) {
  if (!live.system) return null;
  const nets = Object.keys(live.nets);
  const solved = solveNodes(live.system, values, nets.map((n) => live.nets[n]));
  return { freq: live.system.freq, nodes: Object.fromEntries(nets.map((n, i) => [n, toDb(solved[i])])) };
}

/**
 * The step nearest a value: a rotation (0-1) on a knob slider.
 * @param {Slider} slider @param {number} rotation
 */
export function nearestStep(slider, rotation) {
  let best = 0;
  slider.steps.forEach((s, i) => {
    if (Math.abs(Number(s.value) - rotation) < Math.abs(Number(slider.steps[best].value) - rotation)) best = i;
  });
  return best;
}

/**
 * The value slider's steps to keep on the next fetch (so its range doesn't jump while
 * it's used), by key.
 * @param {Slider[]} sliders
 * @returns {Record<string, Array<string | number>>}
 */
export function keptSteps(sliders) {
  /** @type {Record<string, Array<string | number>>} */
  const kept = {};
  for (const s of sliders) if (s.field === "value") kept[sliderKey(s)] = s.steps.map((step) => step.value);
  return kept;
}

/** Readings other than a frequency and a gain say what they are. */
const READING_NAMES = /** @type {Record<string, string>} */ ({ depth: "depth ", low: "low ", high: "high " });

/**
 * A curve's readings (the server's, `solum.analysis.measures.readings`) as short texts:
 * a label and its readings joined ("612 Hz · −18.4 dB"), or "—" with the reason.
 * @param {Array<{label: string, none?: string, readings?: Array<{name: string, value: number, unit: string, text: string}>}>} measures
 * @returns {Array<{label: string, text: string, title: string}>}
 */
export function readingRows(measures) {
  return measures.map((m) => {
    if (!m.readings) return { label: m.label, text: "—", title: m.none ?? "" };
    const text = m.readings.map((r) => `${READING_NAMES[r.name] ?? ""}${r.unit === "dB" ? db(r.value) : r.text}`).join(" · ");
    return { label: m.label, text, title: "" };
  });
}
