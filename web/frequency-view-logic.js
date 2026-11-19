/**
 * The Frequency plot's view (P5, D-366), no DOM: a pinned net drawn over the curves, lines
 * hidden from the plot's key, and a zoom to a frequency range. Which line is which goes by
 * its `role` (`series.js`): the selection's, the output's, the pinned net's, a snapshot.
 */

import { PLOT_BAND } from "./layers.js";

/** @typedef {import("./series.js").PlotData} PlotData */

/** The roles a line in the key can have, hidden or shown by a click on it. */
export const ROLES = /** @type {const} */ (["selection", "output", "pinned", "snapshot"]);

/** The narrowest zoom: a fifth of an octave, so a slip of the mouse doesn't zoom to nothing. */
const ZOOM_MIN_RATIO = 2 ** 0.2;

/**
 * The pinned net's line added to a plot (an overlay: the rest stay as they are). Nothing
 * when there's no pin, or the AC result has no curve for it (yet).
 * @param {PlotData | null} data @param {any} ac an AC result (`run.ac`, or the live solve's)
 * @param {string | null} pinned
 * @returns {PlotData | null}
 */
export function withPinned(data, ac, pinned) {
  const values = pinned ? ac?.nodes?.[pinned] : null;
  if (!data || !values || values.length !== data.x.length) return data;
  return { ...data, series: [...data.series, { label: `${pinned} (pinned)`, values, style: "pinned", role: "pinned" }] };
}

/**
 * The labels of the lines whose role is hidden (what `linePlot` takes as `hidden`).
 * @param {PlotData | null} data @param {Set<string>} roles
 * @returns {Set<string>}
 */
export function hiddenLabels(data, roles) {
  return new Set((data?.series ?? []).filter((s) => s.role && roles.has(s.role)).map((s) => s.label));
}

/**
 * The role of the line with this label (a key clicked), or null.
 * @param {PlotData | null} data @param {string} label
 * @returns {string | null}
 */
export function roleOf(data, label) {
  return data?.series.find((s) => s.label === label)?.role ?? null;
}

/**
 * The plot with its hidden lines left out (for fitting the level axis to what shows).
 * @param {PlotData} data @param {Set<string>} roles
 * @returns {PlotData}
 */
export function visibleOnly(data, roles) {
  const kept = data.series.filter((s) => !(s.role && roles.has(s.role)));
  return kept.length ? { ...data, series: kept } : data;
}

/**
 * Which net the readings are for: the selection's curve as before; with it hidden, the
 * pinned net's (when shown and the run has its readings); with neither, the output's.
 * @param {{shown: string, pinned: string | null, out: string | null, hidden: Set<string>, readings: Record<string, any> | null | undefined}} at
 *   `shown`: the net the selection's readings are for (`curveReadings`)
 * @returns {string}
 */
export function readingsNet({ shown, pinned, out, hidden, readings }) {
  if (!hidden.has("selection")) return shown;
  if (pinned && !hidden.has("pinned") && readings?.[pinned]) return pinned;
  return out ?? shown;
}

/**
 * A zoom from a drag between two frequencies: low to high, inside the plot's band, at
 * least a fifth of an octave wide (widened about its middle); null when it's the whole band.
 * @param {number} a @param {number} b
 * @returns {[number, number] | null}
 */
export function zoomRange(a, b) {
  let lo = Math.max(Math.min(a, b), PLOT_BAND[0]);
  let hi = Math.min(Math.max(a, b), PLOT_BAND[1]);
  if (!(lo > 0) || !(hi > 0)) return null;
  if (hi / lo < ZOOM_MIN_RATIO) {
    const mid = Math.sqrt(lo * hi);
    lo = Math.max(mid / Math.sqrt(ZOOM_MIN_RATIO), PLOT_BAND[0]);
    hi = Math.min(lo * ZOOM_MIN_RATIO, PLOT_BAND[1]);
  }
  return lo <= PLOT_BAND[0] && hi >= PLOT_BAND[1] ? null : [lo, hi];
}

/**
 * A zoom as the Reset zoom button says it ("200 Hz – 3.16 kHz"): each end as the server
 * writes the nearest frequency on the curve's grid (`xText`, D-081).
 * @param {[number, number]} range @param {number[]} x @param {string[] | undefined} xText
 * @returns {string}
 */
export function zoomText(range, x, xText) {
  const near = (/** @type {number} */ f) => {
    let best = 0;
    x.forEach((v, i) => {
      if (Math.abs(Math.log(v / f)) < Math.abs(Math.log(x[best] / f))) best = i;
    });
    return xText?.[best] ?? `${Math.round(x[best] ?? f)} Hz`;
  };
  return `${near(range[0])} – ${near(range[1])}`;
}

/**
 * Whether the pinned net is gone from the drawing (a wire or part deleted, a label renamed).
 * @param {string | null} pinned @param {Record<string, unknown> | null | undefined} nets the view's nets
 */
export function pinGone(pinned, nets) {
  return Boolean(pinned && nets && !(pinned in nets));
}
