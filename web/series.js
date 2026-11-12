/**
 * Turns API results into plot series. Pure: no DOM, no uPlot. Each series has a `style`
 * that plots.js maps to the DESIGN.md plot colours: current, output, input, snapshot,
 * sweep-1..12. A series may carry a short `tag` written at the end of its line. `xText`,
 * when the server sends it, is each x value as text ("1.23 kHz") for the hover readout.
 * @typedef {{label: string, values: Array<number|null>, style: string, tag?: string, bold?: boolean, dash?: boolean, dots?: boolean, faint?: boolean}} Series `bold`: drawn heavier (the take playing); `dash`: thin and dashed, in its style's colour; `dots`: a dot at each value, no line; `faint`: as it was before an edit, in `--plot-before`, one legend entry for them all (D-123)
 * @typedef {{x: number[], xText?: string[], series: Series[]}} PlotData
 */

/**
 * A frozen copy of a plot's main series, for A/B overlay.
 * @param {PlotData | null} data @param {string} label
 * @returns {{x: number[], values: Array<number|null>, label: string} | null}
 */
export function snapshotOf(data, label = "snapshot") {
  if (!data || !data.series.length) return null;
  return { x: [...data.x], values: [...data.series[0].values], label };
}

/** @param {PlotData} data @param {ReturnType<typeof snapshotOf>} snapshot */
function withSnapshot(data, snapshot) {
  if (!snapshot) return data;
  const sameGrid =
    snapshot.x.length === data.x.length && snapshot.x.every((v, i) => Math.abs(v - data.x[i]) < 1e-9);
  if (!sameGrid) return data;
  return { ...data, series: [...data.series, { label: snapshot.label, values: snapshot.values, style: "snapshot" }] };
}

/**
 * Frequency response at the probed net, and at the output when that's another net.
 * @param {any} run /api/run result @param {string} net @param {string | null} out
 * @param {ReturnType<typeof snapshotOf>} [snapshot]
 * @returns {PlotData | null}
 */
export function frequencySeries(run, net, out, snapshot = null) {
  if (!run?.ac || !run.ac.nodes[net]) return null;
  /** @type {Series[]} */
  const series = [{ label: net, values: run.ac.nodes[net], style: "current" }];
  if (out && out !== net && run.ac.nodes[out]) {
    series.push({ label: `${out} (output)`, values: run.ac.nodes[out], style: "output" });
  }
  return withSnapshot({ x: run.ac.freq, xText: run.ac.freq_text, series }, snapshot);
}

/**
 * Most values "compare several" takes at once: inspector sweeps, supply voltages and
 * render sweeps (the user, 2026-10-23, D-096). The server's `SWEEP_MAX` enforces it.
 */
export const COMPARE_MAX = 5;

/** Sweep colours in theme.css (`--plot-sweep-1..12`). */
export const SWEEP_STYLES = 12;

/**
 * The sweep style for series i of n, spread evenly over the colour ramp so a few series
 * still differ clearly.
 * @param {number} i @param {number} n
 */
export function sweepStyle(i, n) {
  return `sweep-${n <= 1 ? 1 : 1 + Math.round((i * (SWEEP_STYLES - 1)) / (n - 1))}`;
}

/**
 * One series per curve, with sweep styles and tags.
 * @param {number[]} x @param {Array<Array<number|null>>} curves @param {string[]} tags @param {(tag: string) => string} label
 * @param {string[]} [xText]
 * @returns {PlotData}
 */
function overlay(x, curves, tags, label, xText) {
  return {
    x,
    xText,
    series: curves.map((values, i) => ({ label: label(tags[i]), values, style: sweepStyle(i, curves.length), tag: tags[i] })),
  };
}

/**
 * "Try several values": the frequency response (or the scope) at a net for each value.
 * @param {any} sweep /api/sweep result @param {string} net @param {"ac" | "tran"} which
 * @returns {PlotData | null}
 */
export function valueSweepSeries(sweep, net, which) {
  const data = sweep?.[which];
  if (!data || !data.nodes[net]) return null;
  const x = which === "ac" ? data.freq : data.time_ms;
  return overlay(x, data.nodes[net], sweep.values, (v) => `${sweep.ref} = ${v} (${net})`, data.freq_text);
}

/**
 * Numbers to compare a sweep's runs by, at `net`: DC, gain at 1 kHz and the scope's peaks
 * per run; whether the runs' curves overlap (so the plots look like one line); and the
 * nets whose DC moved most across the runs (where a supply change shows). D-067.
 * @param {any} sweep @param {string} net
 * @returns {{rows: Array<{value: string, dc: number | null, gain: number | null, peak: number[] | null}>,
 *   overlap: boolean, shifts: Array<{net: string, values: number[]}>}}
 */
export function sweepSummary(sweep, net) {
  const ac = sweep.ac?.nodes[net] ?? null;
  const tran = sweep.tran?.nodes[net] ?? null;
  const at1k = ac ? sweep.ac.freq.reduce((best, f, i, fs) => (Math.abs(Math.log(f / 1000)) < Math.abs(Math.log(fs[best] / 1000)) ? i : best), 0) : 0;
  const rows = sweep.values.map((value, i) => ({
    value,
    dc: sweep.dc[net]?.[i] ?? null,
    gain: ac ? ac[i][at1k] : null,
    peak: tran ? [Math.max(...tran[i]), Math.min(...tran[i])] : null,
  }));
  const spread = (/** @type {number[][]} */ curves) =>
    Math.max(...curves[0].map((_v, k) => Math.max(...curves.map((c) => c[k])) - Math.min(...curves.map((c) => c[k]))));
  const scale = tran ? Math.max(...tran.flat().map(Math.abs), 1e-9) : 1;
  const overlap = sweep.values.length > 1 && (!ac || spread(ac) < 0.1) && (!tran || spread(tran) / scale < 0.01);
  const shifts = Object.entries(sweep.dc_all ?? {})
    .map(([n, values]) => ({ net: n, values: /** @type {number[]} */ (values), moved: Math.max(...values) - Math.min(...values) }))
    .filter((x) => x.moved > 0.05)
    .sort((a, b) => b.moved - a.moved)
    .slice(0, 4)
    .map(({ net: n, values }) => ({ net: n, values }));
  return { rows, overlap, shifts };
}

/**
 * A capacitor's two sides (its local filter), and the output when it's neither side, so
 * the cap's effect on the whole circuit shows too.
 * @param {any} curves the part view's `detail.curves`: the response at each side
 * @param {any} run /api/run result, for the output's curve @param {string | null} out
 * @returns {PlotData | null}
 */
export function capacitorSeries(curves, run, out) {
  if (!curves) return null;
  const nets = Object.keys(curves.nodes);
  /** @type {Series[]} */
  const series = nets.map((net, i) => ({ label: net, values: curves.nodes[net], style: i ? "input" : "current" }));
  const output = out && !nets.includes(out) ? run?.ac?.nodes[out] : null;
  if (output?.length === curves.freq.length) series.push({ label: `${out} (output)`, values: output, style: "output" });
  return { x: curves.freq, xText: curves.freq_text, series };
}

/**
 * Scope: the waveform at the net with the input overlaid (scaled by the net's gain).
 * @param {any} run @param {string} net @param {ReturnType<typeof snapshotOf>} [snapshot]
 * @returns {PlotData | null}
 */
export function scopeSeries(run, net, snapshot = null) {
  const node = run?.tran?.nodes[net];
  if (!node) return null;
  /** @type {Series[]} */
  const series = [{ label: net, values: node.wave, style: "current" }];
  if (net !== run.tran.input) {
    series.push({ label: "input, scaled", values: node.overlay, style: "input" });
  }
  return withSnapshot({ x: run.tran.time_ms, series }, snapshot);
}

/**
 * Harmonics 2-8 in dB relative to the fundamental, split even/odd for colouring.
 * @param {{harmonics_db: Record<string, number>} | null | undefined} stats
 * @returns {{x: number[], even: Array<number|null>, odd: Array<number|null>} | null}
 */
export function harmonicBars(stats) {
  if (!stats) return null;
  const x = [2, 3, 4, 5, 6, 7, 8];
  const value = (/** @type {number} */ k) => stats.harmonics_db[String(k)];
  return {
    x,
    even: x.map((k) => (k % 2 === 0 ? value(k) : null)),
    odd: x.map((k) => (k % 2 === 1 ? value(k) : null)),
  };
}

/** Smallest current drawn on a log axis (amps); leakage below this sits on the floor. */
export const CURRENT_FLOOR = 1e-12;

/**
 * A device curve for a diode (I-V) or transistor (transfer), with the operating point
 * and (for a diode) the swing traced on it. Diode and BJT currents are exponential, so
 * they're |I| in amps on a log axis; a JFET's square law is mA on a linear axis.
 * @param {any} partView
 * @returns {{x: number[], y: number[], log: boolean, xLabel: string, point: number[] | null,
 *   swing: {x: number[], y: number[]} | null} | null}
 */
export function deviceCurve(partView) {
  const d = partView?.detail;
  if (!d?.curve) return null;
  const log = partView.type !== "jfet";
  const scale = (/** @type {number} */ i) => (log ? Math.max(Math.abs(i), CURRENT_FLOOR) : i * 1e3);
  const ys = (/** @type {number[]} */ a) => a.map(scale);
  const curve = { x: d.curve.v, y: ys(d.curve.i), log };
  if (partView.type === "diode" || partView.type === "led") {
    return {
      ...curve,
      xLabel: "V across (A to K)",
      point: [d.dc.v, scale(d.dc.i)],
      swing: d.swing ? { x: d.swing.v, y: ys(d.swing.i) } : null,
    };
  }
  const isBjt = partView.type === "bjt";
  const control = isBjt ? d.vbe : d.vgs;
  const current = isBjt ? d.ic : d.id;
  return {
    ...curve,
    xLabel: isBjt ? "Vbe" : "Vgs",
    point: current == null ? null : [control, scale(current)],
    swing: null,
  };
}
