/**
 * uPlot wrappers for the panels. Colours come from theme.css, read once (canvas can't
 * use CSS variables). Each call replaces the plot in its element.
 */

import uPlot from "./vendor/uplot/uPlot.esm.js";

const HEIGHT = 190;
const HARMONIC_FLOOR_DB = -80; // bars rise from here, so a stronger harmonic is a taller bar
// Decade labels for the log frequency axis: a fixed table, not a formatter.
const DECADES = new Map([[10, "10"], [100, "100"], [1000, "1k"], [10000, "10k"], [100000, "100k"]]);
// Decade labels for current on a log axis (amps): a fixed table, not a formatter.
const AMP_DECADES = new Map([
  [-12, "1p"], [-11, "10p"], [-10, "100p"], [-9, "1n"], [-8, "10n"], [-7, "100n"], [-6, "1µ"],
  [-5, "10µ"], [-4, "100µ"], [-3, "1m"], [-2, "10m"], [-1, "100m"], [0, "1"],
]);
const AXIS_FONT = "11px ui-monospace, monospace";
const SWEEP_COLOURS = 12; // --plot-sweep-1..12 in theme.css

/** @type {Record<string, string> | null} */
let palette = null;

/** After a theme change (D-303): the next plot reads the colours again. */
export function forgetColours() {
  palette = null;
}

function colours() {
  if (palette) return palette;
  const css = getComputedStyle(document.documentElement);
  const read = (/** @type {string} */ name) => css.getPropertyValue(name).trim();
  palette = {
    current: read("--plot-current"),
    output: read("--plot-output"),
    snapshot: read("--plot-snapshot"),
    input: read("--plot-input"),
    grid: read("--plot-grid"),
    axis: read("--plot-axis"),
    even: read("--plot-harm-even"),
    odd: read("--plot-harm-odd"),
    marker: read("--plot-marker"),
    live: read("--plot-live"),
    "live-fill": read("--plot-live-fill"),
    band: read("--plot-band"),
    at: read("--plot-at"),
    bg: read("--plot-handle-fill"),
    before: read("--plot-before"),
    outside: read("--plot-outside"),
    hatch: read("--plot-hatch"),
  };
  for (let i = 1; i <= SWEEP_COLOURS; i++) palette[`sweep-${i}`] = read(`--plot-sweep-${i}`);
  return palette;
}

/** @param {string} style */
function seriesStyle(style) {
  const c = colours();
  const base = { stroke: c[style] ?? c.current, width: 1.25 };
  if (style === "current") return { ...base, width: 2 };
  if (style === "snapshot") return { ...base, dash: [6, 4] };
  if (style === "input") return { ...base, dash: [3, 3], width: 1 };
  if (style === "expected") return { ...base, stroke: c.marker, dash: [8, 4], width: 1.5 };
  // what's playing: a faint filled area under the fixed lines, down to the plot's floor
  if (style === "live") return { stroke: c.live, fill: c["live-fill"], width: 1, fillTo: (/** @type {uPlot} */ u) => u.scales.y.min ?? 0 };
  if (style.startsWith("sweep-")) return { ...base, width: 1.5 };
  return base;
}

/** A faint series: the chart as it was (Try changes' "before", D-123), thin, no dots. */
function faint() {
  return { stroke: colours().before, width: 1.25, dash: undefined, points: { show: false } };
}

/**
 * Faint series share one legend entry: the first one's (they all say the same, "Before").
 * Rows are matched by label: uPlot's legend has a row for x only in some setups.
 * @param {uPlot} plot @param {import("./series.js").PlotData} data
 */
function oneFaintKey(plot, data) {
  const faint = new Set(data.series.filter((s) => s.faint).map((s) => s.label));
  const seen = new Set();
  for (const row of /** @type {NodeListOf<HTMLElement>} */ (plot.root.querySelectorAll(".u-legend .u-series"))) {
    const label = row.textContent?.trim() ?? "";
    if (!faint.has(label)) continue;
    row.hidden = seen.has(label);
    seen.add(label);
  }
}

/** A series drawn as dots alone, filled in its colour. @param {string} style */
function dots(style) {
  const stroke = seriesStyle(style).stroke;
  return { paths: () => null, points: { show: true, size: 10, width: 1, stroke, fill: stroke } };
}

/** @param {string} label @param {(u: uPlot, splits: number[]) => string[]} [values] */
function axis(label, values) {
  const c = colours();
  return {
    label,
    stroke: c.axis,
    font: AXIS_FONT,
    labelFont: AXIS_FONT,
    grid: { stroke: c.grid, width: 1 },
    ticks: { stroke: c.grid, width: 1 },
    ...(values ? { values } : {}),
  };
}

/** Keeps only the splits that fall on a decade. */
const decadesOnly = (/** @type {uPlot} */ _u, /** @type {number[]} */ splits) =>
  splits.map((v) => (Number.isInteger(Math.round(Math.log10(v) * 1e6) / 1e6) ? v : null));

/** Labels, ticks and grid lines at decades only (a log axis is too busy otherwise). */
function decadeAxis(/** @type {any} */ ax, /** @type {any} */ filter) {
  return { ...ax, filter, grid: { ...ax.grid, filter }, ticks: { ...ax.ticks, filter } };
}

/** @param {HTMLElement} el */
function replace(el, /** @type {uPlot.Options} */ opts, /** @type {uPlot.AlignedData} */ data, height = HEIGHT) {
  // hold the old height until the new plot has laid itself out (uPlot sizes it a moment
  // later): otherwise the panels shrink for an instant and Firefox jumps the scroll (D-068)
  el.style.minHeight = `${el.offsetHeight}px`;
  requestAnimationFrame(() => {
    el.style.minHeight = "";
  });
  // @ts-ignore: the plot is kept on its element so the next update can replace it
  el._plot?.destroy();
  el.replaceChildren();
  const plot = new uPlot({ width: Math.max(el.clientWidth, 240), height, ...opts }, data, el);
  // @ts-ignore
  el._plot = plot;
  return plot;
}

/**
 * How a line plot writes the values under the cursor: `y` for each series' value, `x` for
 * the x value when the data has no `xText`.
 * `legend: false` when the page draws its own (the Audio panel's curve toggles).
 * `marks`: lines, points, shaded bands and levels drawn over the plot (the Frequency
 * panel's layers, the Audio spectrum's clip lines; `setMarks` changes them in place).
 * `onPick(x)`: a click on the plot, at that x value. `height` in px (default 190).
 * `shade`: the x band left clear; the plot either side of it is shaded lightly (the
 * Frequency plot's 20 Hz - 20 kHz, D-102).
 * `hatch`: from `from` up, the plot is hatched with `label` in its top corner: where no
 * recording can hold anything (the Audio spectrum above 24 kHz, D-105).
 * `xNames`: the x values are 0, 1, 2…, one per name, and the axis writes the names (the
 * Bias & headroom level diagram's stages).
 * `hidden`: the labels of lines drawn hidden (their legend key off); `onToggle(label,
 * shown)`: a legend key clicked (the Bias & headroom strip fades a hidden line's block).
 * `onDrag(id, point, phase)`: a handle in `marks.handles` grabbed ("start"), dragged
 * ("move") and let go ("end"), at `point`: x and y values, the pixels from where it
 * was grabbed (dx, dy; up is negative), and whether Shift was held when it was grabbed.
 * @typedef {{log?: boolean, xLabel: string, yLabel: string, xRange?: [number, number], yRange?: [number, number], shade?: [number, number], hatch?: {from: number, label: string} | null,
 *   xNames?: string[], hover?: {x: (x: number) => string, y: (y: number) => string}, legend?: boolean,
 *   marks?: import("./layers.js").Marks, onPick?: (x: number) => void, height?: number,
 *   hidden?: Set<string>, onToggle?: (label: string, shown: boolean) => void,
 *   onDrag?: (id: string, point: DragPoint, phase: "start" | "move" | "end") => void}} LineOpts
 * @typedef {{x: number, y: number, dx: number, dy: number, shift: boolean}} DragPoint
 */

/**
 * A box beside the cursor with the values at the dot on each line: the x value, then each
 * shown series' value. It follows the cursor and keeps inside the plot.
 * @param {import("./series.js").PlotData} data @param {NonNullable<LineOpts["hover"]>} hover
 */
function hoverReadout(data, hover) {
  const tip = document.createElement("div");
  tip.className = "plot-hover";
  tip.hidden = true;
  const GAP = 12;
  return {
    init: [(/** @type {uPlot} */ u) => u.over.appendChild(tip)],
    setCursor: [
      (/** @type {uPlot} */ u) => {
        const { idx, left, top } = u.cursor;
        if (idx == null || left == null || top == null || left < 0) {
          tip.hidden = true;
          return;
        }
        const rows = [];
        const head = document.createElement("div");
        head.className = "plot-hover-x";
        // values from the plot itself: a live plot changes them in place (liveLinePlot)
        head.textContent = data.xText?.[idx] ?? hover.x(/** @type {number} */ (u.data[0][idx]));
        rows.push(head);
        data.series.forEach((s, i) => {
          const v = u.data[i + 1][idx];
          if (v == null || s.faint || !u.series[i + 1].show) return;
          const row = document.createElement("div");
          const mark = document.createElement("span");
          mark.className = "plot-hover-mark";
          mark.style.background = /** @type {string} */ (u.series[i + 1].stroke instanceof Function ? colours().current : u.series[i + 1].stroke);
          const name = document.createElement("span");
          name.className = "plot-hover-name";
          name.textContent = s.label;
          const value = document.createElement("span");
          value.className = "plot-hover-value";
          value.textContent = hover.y(v);
          row.append(mark, name, value);
          rows.push(row);
        });
        tip.replaceChildren(...rows);
        tip.hidden = false;
        // beside the cursor, flipped to the other side near the plot's right or bottom edge
        const w = tip.offsetWidth;
        const h = tip.offsetHeight;
        const x = left + GAP + w > u.over.clientWidth ? left - GAP - w : left + GAP;
        const y = Math.min(Math.max(top - h / 2, 0), Math.max(u.over.clientHeight - h, 0));
        tip.style.transform = `translate(${Math.max(x, 0)}px, ${y}px)`;
      },
    ],
  };
}

/**
 * @param {HTMLElement} el
 * @param {import("./series.js").PlotData} data
 * @param {LineOpts} opts
 */
export function linePlot(el, data, opts) {
  const decades = (/** @type {uPlot} */ _u, /** @type {number[]} */ splits) =>
    splits.map((v) => DECADES.get(Math.round(v)) ?? "");
  const names = opts.xNames;
  const named = names && { ...axis(opts.xLabel, (_u, splits) => splits.map((v) => names[v] ?? "")), incrs: [1] };
  const xRange = opts.xRange ?? (names ? /** @type {[number, number]} */ ([-0.35, names.length - 0.65]) : null);
  const plot = replace(
    el,
    {
      scales: {
        x: { time: false, ...(opts.log ? { distr: 3 } : {}), ...(xRange ? { range: xRange } : {}) },
        y: opts.yRange ? { range: opts.yRange } : {},
      },
      axes: [
        named || (opts.log ? decadeAxis(axis(opts.xLabel, decades), decadesOnly) : axis(opts.xLabel)),
        axis(opts.yLabel),
      ],
      series: [{}, ...data.series.map((s) => ({ label: s.label, ...seriesStyle(s.style), ...(s.bold ? { width: 2.75 } : {}), ...(s.dash ? { dash: [5, 4], width: 1 } : {}), points: { show: !!names, size: 5 }, ...(s.dots ? dots(s.style) : {}), ...(s.faint ? faint() : {}), ...(opts.hidden?.has(s.label) ? { show: false } : {}) }))],
      legend: { show: opts.legend ?? true, live: false },
      cursor: { drag: { x: false, y: false } },
      hooks: {
        drawClear: [(/** @type {uPlot} */ u) => drawBands(u)],
        draw: [(/** @type {uPlot} */ u) => drawTags(u, data), (/** @type {uPlot} */ u) => drawMarks(u)],
        ...(opts.hover ? hoverReadout(data, opts.hover) : {}),
        ...(opts.onToggle ? { setSeries: [toggled(opts.onToggle)] } : {}),
      },
    },
    [data.x, ...data.series.map((s) => s.values)],
    opts.height,
  );
  oneFaintKey(plot, data);
  // @ts-ignore: the marks live on the plot, so `setMarks` can change them in place
  plot.marks = opts.marks ?? null;
  // @ts-ignore: read by `drawBands`
  plot.shade = opts.shade ?? null;
  // @ts-ignore: read by `drawBands`
  plot.hatch = opts.hatch ?? null;
  if (opts.onPick) {
    const pick = opts.onPick;
    plot.over.addEventListener("click", (/** @type {MouseEvent} */ e) => {
      const left = e.clientX - plot.over.getBoundingClientRect().left;
      pick(plot.posToVal(left, "x"));
    });
    plot.over.classList.add("pickable");
  }
  // @ts-ignore: read by the container's pointer handlers (`dragHandles`)
  plot.onDrag = opts.onDrag ?? null;
  if (opts.onDrag) dragHandles(el);
  return plot; // uPlot draws on its next commit, with the marks already set

}

/** uPlot's setSeries hook, passing on a line shown or hidden. @param {(label: string, shown: boolean) => void} f */
function toggled(f) {
  return (/** @type {uPlot} */ u, /** @type {number | null} */ i, /** @type {{show?: boolean}} */ o) => {
    if (i && o?.show !== undefined) f(String(u.series[i].label ?? ""), o.show);
  };
}

const GRAB_PX = 10; // a press this close to a handle grabs it

/**
 * Handles on the plot in `el` can be dragged. The listeners sit on `el`, not the plot, so
 * a drag carries on when a live frame draws a new plot under it; they read the plot there
 * now. Bound once per element.
 * @param {HTMLElement} el
 */
function dragHandles(el) {
  // @ts-ignore
  if (el._dragHandles) return;
  // @ts-ignore
  el._dragHandles = true;
  /** @type {string | null} */
  let held = null;
  let from = { x: 0, y: 0 };
  let shift = false; // held when grabbed: the whole drag is up/down
  const plotNow = () => /** @type {any} */ (el)._plot;
  /** @param {PointerEvent} e */
  const where = (e) => {
    const r = plotNow().over.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  /** @param {PointerEvent} e @returns {import("./layers.js").HandleMark | null} */
  const near = (e) => {
    const plot = plotNow();
    if (!plot?.onDrag || !plot.over.contains(e.target)) return null;
    const { x, y } = where(e);
    let best = null;
    let gap = GRAB_PX;
    for (const h of plot.marks?.handles ?? []) {
      const d = Math.hypot(plot.valToPos(h.x, "x") - x, plot.valToPos(h.y, "y") - y);
      if (d < gap) [best, gap] = [h, d];
    }
    return best;
  };
  /** @param {PointerEvent} e @returns {import("./plots.js").DragPoint} */
  const pointAt = (e) => {
    const p = where(e);
    const plot = plotNow();
    return { x: plot.posToVal(p.x, "x"), y: plot.posToVal(p.y, "y"), dx: p.x - from.x, dy: p.y - from.y, shift };
  };
  el.addEventListener("pointerdown", (e) => {
    const h = near(e);
    if (!h) return;
    held = h.id;
    from = where(e);
    shift = e.shiftKey;
    el.setPointerCapture(e.pointerId);
    el.classList.add("dragging");
    e.preventDefault();
    plotNow().onDrag(held, pointAt(e), "start");
  });
  el.addEventListener("pointermove", (e) => {
    if (held) plotNow()?.onDrag?.(held, pointAt(e), "move");
    else {
      el.classList.toggle("grabbable", !!near(e));
      el.classList.toggle("shift", e.shiftKey); // the cursor says which way a drag goes
    }
  });
  const end = (/** @type {PointerEvent} */ e) => {
    if (!held) return;
    const id = held;
    held = null;
    el.classList.remove("dragging");
    if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    plotNow()?.onDrag?.(id, pointAt(e), "end");
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
}

/**
 * Change the marks on the plot in `el` and redraw it (nothing when it has no plot).
 * @param {HTMLElement} el @param {import("./layers.js").Marks | null} marks
 */
export function setMarks(el, marks) {
  // @ts-ignore: kept on the element by `replace`
  const plot = el._plot;
  if (!plot) return;
  plot.marks = marks;
  plot.redraw(false);
}

/**
 * Under the curves (drawn as the plot is cleared): shaded bands, and Edit mode's curve and
 * dots as they were when it started (faint, so the live curve reads as the change).
 * @param {uPlot} u
 */
function drawBands(u) {
  // @ts-ignore
  const marks = /** @type {import("./layers.js").Marks | null} */ (u.marks);
  // @ts-ignore
  const shade = /** @type {[number, number] | null} */ (u.shade);
  const { left, top, width, height } = u.bbox;
  const ctx = u.ctx;
  ctx.save();
  if (shade) {
    // outside the clear band (below 20 Hz, above 20 kHz): lightly shaded
    ctx.fillStyle = colours().outside;
    const x0 = Math.min(Math.max(u.valToPos(shade[0], "x", true), left), left + width);
    const x1 = Math.max(Math.min(u.valToPos(shade[1], "x", true), left + width), left);
    if (x0 > left) ctx.fillRect(left, top, x0 - left, height);
    if (x1 < left + width) ctx.fillRect(x1, top, left + width - x1, height);
  }
  // @ts-ignore
  const hatch = /** @type {LineOpts["hatch"] | null} */ (u.hatch);
  if (hatch) drawHatch(u, hatch);
  if (!marks) return void ctx.restore();
  ctx.fillStyle = colours().band;
  for (const b of marks.bands) {
    const x0 = Math.max(u.valToPos(b.lo, "x", true), left);
    const x1 = Math.min(u.valToPos(b.hi, "x", true), left + width);
    if (x1 > x0) ctx.fillRect(x0, top, x1 - x0, height);
  }
  if (marks.before) drawBefore(u, marks.before);
  ctx.restore();
}

/**
 * Diagonal lines from `hatch.from` to the plot's right edge, and its label at the top,
 * right-aligned, so it reads as "nothing can be here". @param {uPlot} u
 * @param {NonNullable<LineOpts["hatch"]>} hatch
 */
function drawHatch(u, hatch) {
  const { left, top, width, height } = u.bbox;
  const px = devicePixelRatio;
  const x0 = Math.max(u.valToPos(hatch.from, "x", true), left);
  const right = left + width;
  if (x0 >= right) return;
  const ctx = u.ctx;
  ctx.save();
  ctx.beginPath();
  ctx.rect(x0, top, right - x0, height);
  ctx.clip();
  ctx.strokeStyle = ctx.fillStyle = colours().hatch;
  ctx.lineWidth = px;
  ctx.beginPath();
  const gap = 8 * px;
  for (let x = x0 - height; x < right; x += gap) {
    ctx.moveTo(x, top + height);
    ctx.lineTo(x + height, top);
  }
  ctx.stroke();
  ctx.restore();
  ctx.save();
  ctx.font = `${10 * px}px ui-monospace, monospace`;
  ctx.fillStyle = colours().marker;
  ctx.textAlign = "right";
  ctx.textBaseline = "top";
  ctx.fillText(hatch.label, right - 3 * px, top + 2 * px);
  ctx.restore();
}

/** @param {uPlot} u @param {import("./layers.js").Before} before */
function drawBefore(u, before) {
  const { left, top, width, height } = u.bbox;
  const px = devicePixelRatio;
  const ctx = u.ctx;
  ctx.save();
  ctx.beginPath();
  ctx.rect(left, top, width, height);
  ctx.clip();
  ctx.strokeStyle = colours().before;
  ctx.lineWidth = 2 * px;
  ctx.beginPath();
  let drawing = false;
  before.x.forEach((f, i) => {
    const v = before.y[i];
    if (v === null || !Number.isFinite(v)) return void (drawing = false);
    const x = u.valToPos(f, "x", true);
    const y = u.valToPos(v, "y", true);
    if (drawing) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
    drawing = true;
  });
  ctx.stroke();
  ctx.lineWidth = 1.5 * px;
  for (const d of before.dots) {
    ctx.beginPath();
    ctx.arc(u.valToPos(d.x, "x", true), u.valToPos(d.y, "y", true), 4 * px, 0, 2 * Math.PI);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * Knee lines (dashed, labelled at the top), peak and dip markers (a small triangle,
 * labelled beside it), the frequency clicked (a solid line), levels (dashed across) and
 * Edit mode's handles (a dot, filled when active, labelled with its part).
 * @param {uPlot} u
 */
function drawMarks(u) {
  // @ts-ignore
  const marks = /** @type {import("./layers.js").Marks | null} */ (u.marks);
  if (!marks) return;
  const c = colours();
  const { left, top, width, height } = u.bbox;
  const px = devicePixelRatio;
  const ctx = u.ctx;
  ctx.save();
  ctx.font = `${10 * px}px ui-monospace, monospace`;
  ctx.lineWidth = px;
  const inside = (/** @type {number} */ x) => x >= left && x <= left + width;
  marks.lines.forEach((m, i) => {
    const x = u.valToPos(m.x, "x", true);
    if (!inside(x)) return;
    ctx.strokeStyle = ctx.fillStyle = c.marker;
    ctx.setLineDash([4 * px, 4 * px]);
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, top + height);
    ctx.stroke();
    ctx.setLineDash([]);
    // labels alternate rows so two knees close together don't overlap
    ctx.textAlign = x > left + width - 80 * px ? "right" : "left";
    ctx.textBaseline = "top";
    ctx.fillText(m.label, x + (ctx.textAlign === "left" ? 3 : -3) * px, top + 2 * px + (i % 2) * 12 * px);
  });
  for (const m of marks.levels) {
    const y = u.valToPos(m.y, "y", true);
    if (y < top || y > top + height) continue;
    ctx.strokeStyle = ctx.fillStyle = c.marker;
    ctx.setLineDash([6 * px, 4 * px]);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + width, y);
    ctx.stroke();
    ctx.setLineDash([]);
    if (!m.label) continue; // unlabelled: the text under the plot says what it is
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    ctx.fillText(m.label, left + 4 * px, y - 2 * px);
  }
  for (const m of marks.points) {
    const x = u.valToPos(m.x, "x", true);
    const y = u.valToPos(m.y, "y", true);
    if (!inside(x)) continue;
    const s = 5 * px;
    const d = m.kind === "peak" ? -1 : 1; // a peak's triangle sits above the curve, pointing down at it
    ctx.fillStyle = c.marker;
    ctx.beginPath();
    ctx.moveTo(x, y + d * 2 * px);
    ctx.lineTo(x - s, y + d * (2 * px + s * 1.5));
    ctx.lineTo(x + s, y + d * (2 * px + s * 1.5));
    ctx.closePath();
    ctx.fill();
    ctx.textAlign = "center";
    ctx.textBaseline = m.kind === "peak" ? "bottom" : "top";
    ctx.fillText(m.label, x, y + d * (4 * px + s * 1.5));
  }
  for (const m of marks.handles ?? []) {
    const x = u.valToPos(m.x, "x", true);
    const y = u.valToPos(m.y, "y", true);
    if (!inside(x) || y < top || y > top + height) continue;
    ctx.beginPath();
    ctx.arc(x, y, (m.active ? 6 : 5) * px, 0, 2 * Math.PI);
    ctx.fillStyle = m.active ? c.at : c.bg;
    ctx.strokeStyle = m.idle ? c.before : c.at; // faint: nothing moves it this way
    ctx.lineWidth = 2 * px;
    ctx.fill();
    ctx.stroke();
    if (m.ids.length > 1) {
      // handles sharing this dot: a second ring, and each one's part in the label
      ctx.beginPath();
      ctx.arc(x, y, (m.active ? 10 : 9) * px, 0, 2 * Math.PI);
      ctx.lineWidth = 1.5 * px;
      ctx.stroke();
    }
    ctx.fillStyle = c.marker;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(m.label, x, y - (m.ids.length > 1 ? 13 : 9) * px);
  }
  ctx.lineWidth = px;
  if (marks.at != null) {
    const x = u.valToPos(marks.at, "x", true);
    if (inside(x)) {
      ctx.strokeStyle = c.at;
      ctx.lineWidth = 1.5 * px;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + height);
      ctx.stroke();
    }
  }
  ctx.restore();
}

/**
 * A line plot changed in place while its series stay the same (a slider moving: one plot,
 * new data each frame), otherwise drawn afresh like `linePlot`. The series' labels and
 * styles are kept on the plot itself, so a plot `linePlot` replaced is never reused.
 * While it's reused the x axis stays as first drawn and the y axis only widens (or takes
 * `opts.yRange` when given), so the plot doesn't shift under the curve as it moves (uPlot
 * re-ranges a log axis its own way).
 * @param {HTMLElement} el
 * @param {import("./series.js").PlotData} data
 * @param {LineOpts} opts
 */
export function liveLinePlot(el, data, opts) {
  const shape = data.series.map((s) => `${s.label}:${s.style}:${!!s.bold}`).join("|");
  // @ts-ignore: kept on the element by `replace`
  const plot = el._plot;
  if (plot && plot.liveShape === shape) {
    // without resetting scales uPlot takes the data but doesn't repaint: setScale or redraw does
    if (opts.marks) plot.marks = opts.marks;
    plot.setData([data.x, ...data.series.map((s) => s.values)], false);
    const [lo, hi] = extent(data);
    const y = plot.scales.y;
    if (opts.yRange && (opts.yRange[0] !== y.min || opts.yRange[1] !== y.max)) {
      plot.setScale("y", { min: opts.yRange[0], max: opts.yRange[1] }); // a held range that moved
    } else if (!opts.yRange && (lo < y.min || hi > y.max)) {
      const [min, max] = uPlot.rangeNum(Math.min(lo, y.min), Math.max(hi, y.max), 0.1, true);
      plot.setScale("y", { min, max });
    } else plot.redraw();
    return plot;
  }
  const fresh = linePlot(el, data, opts);
  fresh.liveShape = shape;
  return fresh;
}

/** The lowest and highest values over all series. @param {import("./series.js").PlotData} data */
function extent(data) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of data.series) {
    for (const v of s.values) {
      if (v === null || !Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return [lo, hi];
}

/**
 * Each series with a `tag` gets it written at its line's right end (DESIGN.md: sweep
 * series carry value labels on the lines).
 * @param {uPlot} u @param {import("./series.js").PlotData} data
 */
function drawTags(u, data) {
  const ctx = u.ctx;
  ctx.save();
  ctx.font = `${10 * devicePixelRatio}px ui-monospace, monospace`;
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  data.series.forEach((s, i) => {
    if (!s.tag) return;
    let k = s.values.length - 1;
    while (k >= 0 && s.values[k] == null) k--;
    if (k < 0) return;
    const x = u.valToPos(data.x[k], "x", true);
    const y = u.valToPos(/** @type {number} */ (s.values[k]), "y", true);
    ctx.fillStyle = /** @type {string} */ (u.series[i + 1].stroke instanceof Function ? colours().current : u.series[i + 1].stroke);
    ctx.fillText(s.tag, x - 2, y - 2);
  });
  ctx.restore();
}

/**
 * Harmonic bars (dB vs the fundamental), even and odd in their own colours.
 * @param {HTMLElement} el @param {NonNullable<ReturnType<typeof import("./series.js").harmonicBars>>} bars
 */
export function barPlot(el, bars) {
  const c = colours();
  const paths = uPlot.paths.bars?.({ size: [0.6, 40] });
  const bar = (/** @type {string} */ label, /** @type {string} */ colour) => ({
    label, stroke: colour, fill: colour, width: 0, paths, points: { show: false },
    fillTo: HARMONIC_FLOOR_DB,
  });
  return replace(
    el,
    {
      scales: { x: { time: false, range: [1.4, 8.6] }, y: { range: [HARMONIC_FLOOR_DB, 0] } },
      axes: [
        axis("harmonic", (_u, splits) => splits.map((v) => (Number.isInteger(v) ? String(v) : ""))),
        axis("dB vs fundamental"),
      ],
      series: [{}, bar("even", c.even), bar("odd", c.odd)],
      legend: { show: true, live: false },
      cursor: { show: false },
    },
    [bars.x, bars.even, bars.odd],
  );
}

/**
 * A device curve (current vs volts) with the operating point and swing on it.
 * @param {HTMLElement} el
 * @param {NonNullable<ReturnType<typeof import("./series.js").deviceCurve>>} curve
 */
export function curvePlot(el, curve) {
  const c = colours();
  const linear = uPlot.paths.linear?.();
  /** @type {uPlot.Series[]} */
  const series = [{}, { label: "curve", stroke: c.current, width: 2, paths: linear, points: { show: false } }];
  /** @type {any[]} */
  const data = [null, [curve.x, curve.y]];
  if (curve.swing) {
    series.push({ label: "swing", stroke: c.marker, width: 3, paths: linear, points: { show: false } });
    data.push([curve.swing.x, curve.swing.y]);
  }
  const point = curve.point;
  const drawPoint = (/** @type {uPlot} */ u) => {
    if (!point) return;
    const x = u.valToPos(point[0], "x", true);
    const y = u.valToPos(point[1], "y", true);
    u.ctx.save();
    u.ctx.fillStyle = c.marker;
    u.ctx.beginPath();
    u.ctx.arc(x, y, 4.5 * devicePixelRatio, 0, 2 * Math.PI);
    u.ctx.fill();
    u.ctx.restore();
  };
  return replace(
    el,
    {
      mode: 2,
      scales: { x: { time: false }, y: curve.log ? { distr: 3, log: 10 } : {} },
      axes: [
        axis(curve.xLabel),
        curve.log
          ? decadeAxis(axis("A", (_u, splits) => splits.map((v) => AMP_DECADES.get(Math.round(Math.log10(v))) ?? "")), decadesOnly)
          : axis("mA"),
      ],
      series,
      hooks: { draw: [drawPoint] },
      legend: { show: true, live: false },
      cursor: { drag: { x: false, y: false } },
    },
    data,
  );
}
