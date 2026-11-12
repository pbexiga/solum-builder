import { bandCentres } from "./bands.js";
import { PLOT_BAND } from "./layers.js";
import { COMPARE_MAX } from "./series.js";

/**
 * The Audio panel's logic (no DOM, D-083): asset choices, A/B slots, render positions,
 * job polling and its progress text, and whether the last take is out of date.
 */

/**
 * @typedef {{id: string, name: string, kind: string, layer: "user" | "core", detail: string}} Asset
 * @typedef {{id: string, key: string, label: string, state: "queued" | "running" | "done" | "failed" | "cancelled",
 *   progress: number, message: string, seconds: number, peak: number, amp_in: number,
 *   amp_compression: number}} Job
 * @typedef {{key: string, label: string, amp_in?: number, amp_compression?: number, amp?: boolean,
 *   input_db?: number, from?: Sources, text?: string, notes?: string, circuit?: any}} Take a
 *   finished render that can be played; `amp_in`: its peak into the amp capture, if it had one
 *   (after the amp input trim `input_db`), and `amp_compression` how many dB the capture
 *   squashed it; `from`: what it was rendered from; `text`: what the panel says about it;
 *   `notes`: what it was made from, in words, and `circuit` the circuit as rendered, both
 *   taken when it was rendered (for the zip of all takes)
 * @typedef {Record<string, string>} Sources what a render is made from, each as text so two
 *   can be compared: see `renderSources`
 * @typedef {{pedal: Take | null, dry: Take | null, snapshot: Take | null}} Slots
 */

export const POLL_MS = 250;

/**
 * Where a finished render is served from; `download` names the file to save.
 * @param {string} key @param {string} [download]
 */
export function audioUrl(key, download) {
  const url = `api/render/audio/${key}.wav`;
  return download ? `${url}?download=${encodeURIComponent(download)}` : url;
}

/**
 * Choices for a select: the user's uploads first, marked, then the built-in ones.
 * @param {Asset[]} assets
 * @returns {Array<{value: string, label: string}>}
 */
export function assetOptions(assets) {
  return assets.map((a) => ({
    value: `${a.layer}:${a.id}`,
    label: `${a.name}${a.detail ? ` · ${a.detail}` : ""}`,
  }));
}

/**
 * A select's value back to an asset reference; "" (None) is null.
 * @param {string} value
 * @returns {{layer: string, id: string} | null}
 */
export function assetRef(value) {
  if (!value) return null;
  const at = value.indexOf(":");
  return { layer: value.slice(0, at), id: value.slice(at + 1) };
}

/**
 * Slots after a render: the new pedal take and its dry twin. The snapshot stays.
 * @param {Slots} slots @param {Take} pedal @param {Take | null} dry
 * @returns {Slots}
 */
export function nextSlots(slots, pedal, dry) {
  return { ...slots, pedal, dry };
}

/**
 * A note when the slot chosen holds the same take as another: the snapshot right after
 * Keep is the pedal take itself until a new render. "" otherwise.
 * @param {Slots} slots @param {keyof Slots} slot
 */
export function sameTakeText(slots, slot) {
  const take = slots[slot];
  if (!take) return "";
  const twin = /** @type {Array<keyof Slots>} */ (["pedal", "snapshot"]).find((s) => s !== slot && slots[s]?.key === take.key);
  return twin ? "Snapshot and Pedal are the same take until you render a change." : "";
}

/** The slots in the order they're shown and zipped: Dry, Pedal, Snapshot. */
const SLOT_ORDER = /** @type {const} */ (["dry", "pedal", "snapshot"]);

/**
 * A slot's take: "dry", "pedal", "snapshot", or "sweep-<i>" for the i-th sweep position.
 * @param {Slots} slots @param {Array<Take | null>} sweep @param {string} id
 * @returns {Take | null}
 */
export function takeAt(slots, sweep, id) {
  if (id.startsWith("sweep-")) return sweep[Number(id.slice(6))] ?? null;
  return slots[/** @type {keyof Slots} */ (id)] ?? null;
}

/**
 * The knobs and switches in words: "Drive 75 %, Tone 50 %, Mode: 2", a switch by its
 * position's name (D-143).
 * @param {Array<{ref: string, kind: string, label: string, refs?: string[], positions?: string[], plug?: boolean}>} controls as the view lists them
 * @param {any} circuit where their positions are
 */
export function knobsText(controls, circuit) {
  const parts = new Map((circuit?.parts ?? []).map((/** @type {any} */ p) => [p.ref, p]));
  return controls.map((c) => {
    const p = parts.get(c.refs?.[0] ?? c.ref);
    if (c.kind !== "switch") return `${c.label} ${Math.round((p?.rotation ?? 0.5) * 100)} %`;
    const at = c.plug ? Number(p?.plugged === false) : (p?.position ?? 0);
    return `${c.label}: ${c.positions?.[at] ?? at + 1}`;
  }).join(", ");
}

/**
 * What a take was made from, in words, for the zip of all takes.
 * @param {{name: string, knobs: string | null, clip: string, level: string, amp: string,
 *   input_db: number, cab: string, when: string}} t `knobs` null for the dry take (no pedal)
 */
export function takeNotes(t) {
  return [
    t.knobs === null ? "Pedal: none (the clip straight into the amp)" : `Pedal: ${t.name}`,
    ...(t.knobs ? [`Knobs: ${t.knobs}`] : []),
    `Clip: ${t.clip}, ${t.level === "med" ? "medium" : t.level} pick`,
    `Amp: ${t.amp}${t.amp === "None" ? "" : `, input ${trimText(t.input_db)}`}`,
    `Cab: ${t.cab}`,
    `Rendered: ${t.when}`,
  ].join("\n");
}

/**
 * What goes in the zip of all takes: each take once under a file name of its own, with
 * the circuit it was rendered from beside it, and a text file saying what each was made
 * from. Snapshot is left out when it's Pedal's take.
 * @param {Slots} slots @param {Array<Take | null>} sweep @param {string} name the circuit's
 * @returns {{takes: Array<{key: string, file: string}>, files: Record<string, string>}}
 */
export function zipContents(slots, sweep, name) {
  /** @type {Array<[string, Take]>} */
  const all = [];
  for (const id of SLOT_ORDER) {
    const take = slots[id];
    if (take && !(id === "snapshot" && take.key === slots.pedal?.key)) all.push([id === "dry" ? "Dry" : id === "pedal" ? "Pedal" : "Snapshot", take]);
  }
  for (const take of sweep) if (take) all.push([take.label, take]);
  const used = new Set();
  /** @type {Array<{key: string, file: string}>} */
  const takes = [];
  /** @type {Record<string, string>} */
  const files = {};
  const notes = [];
  for (const [title, take] of all) {
    let file = `${name} ${title}`;
    for (let n = 2; used.has(file); n++) file = `${name} ${title} ${n}`;
    used.add(file);
    takes.push({ key: take.key, file: `${file}.wav` });
    if (take.circuit) files[`${file}.json`] = JSON.stringify(take.circuit, null, 2);
    notes.push(`${file}.wav\n${(take.notes ?? "").replace(/^/gm, "  ")}`);
  }
  files["takes.txt"] = `${notes.join("\n\n")}\n`;
  return { takes, files };
}

/**
 * A sweep's sources leave out the knob it turns, so turning that knob afterwards doesn't
 * make the sweep out of date. @param {Sources} sources @param {string} ref
 * @returns {Sources}
 */
export function withoutKnob(sources, ref) {
  const knobs = JSON.parse(sources.knobs);
  delete knobs[ref];
  return { ...sources, knobs: JSON.stringify(knobs) };
}

/** What each of `renderSources`' entries is called when it changes, in display order. */
export const SOURCE_NAMES = /** @type {const} */ ([
  ["circuit", "circuit"], ["knobs", "knobs"], ["clip", "clip"], ["level", "pick level"],
  ["capture", "amp"], ["ir", "cab"], ["input_db", "amp input"], ["pump_ripple", "pump switching"],
]);

/** Changes after the pedal: a render keeps the pedal's output and only runs the amp and cab. */
const AFTER_PEDAL = new Set(["amp", "cab", "amp input"]);

/**
 * What a render is made from (D-088). The circuit counts only for what it sounds like:
 * parts with their values and models, which net each pin is on, power and probes; not
 * where parts sit or how wires run, so tidying the drawing keeps a take current. Knob
 * and switch positions are kept apart, so the panel can say which changed.
 * @param {any} circuit @param {any} view the circuit's view (pins with their nets)
 * @param {{clip: any, capture: any, ir: any, level: string, input_db: number, pump_ripple?: boolean}} req
 * @returns {Sources}
 */
export function renderSources(circuit, view, req) {
  const pins = Object.fromEntries((view?.parts ?? []).map((/** @type {any} */ p) =>
    [p.ref, (p.pins ?? []).map((/** @type {any} */ pin) => [pin.name, pin.net])]));
  /** @type {Record<string, number>} */
  const knobs = {};
  const parts = (circuit?.parts ?? []).map((/** @type {any} */ p) => {
    const { pos, rot, rotation, position, ...rest } = p;
    if (rotation !== undefined) knobs[p.ref] = rotation;
    if (position !== undefined) knobs[p.ref] = position;
    return { ...rest, pins: pins[p.ref] ?? null };
  });
  const text = (/** @type {any} */ x) => JSON.stringify(x ?? null);
  return {
    circuit: text({ power: circuit?.power, probes: circuit?.probes, parts }),
    knobs: text(knobs),
    clip: text(req.clip), level: req.level, capture: text(req.capture), ir: text(req.ir),
    input_db: String(req.input_db), pump_ripple: String(!!req.pump_ripple),
  };
}

/**
 * Names of what changed between a take's sources and now ([] if nothing did).
 * @param {Sources} then @param {Sources} now
 * @returns {string[]}
 */
export function changedSources(then, now) {
  return SOURCE_NAMES.filter(([k]) => then[k] !== now[k]).map(([, name]) => name);
}

/**
 * The out-of-date line under Render: "" when the take is current.
 * @param {string[]} changed from `changedSources`
 */
export function staleText(changed) {
  if (!changed.length) return "";
  const list = changed.length === 1 ? changed[0] : `${changed.slice(0, -1).join(", ")} and ${changed.at(-1)}`;
  const quick = changed.every((c) => AFTER_PEDAL.has(c)) ? " The pedal isn't simulated again, so it's quick." : "";
  return `Out of date: the ${list} changed since this take. Render to hear ${changed.length === 1 ? "it" : "them"}.${quick}`;
}

/**
 * The sweep's takes are out of date: what changed, and that Render sweep updates them
 * (Render doesn't: a sweep is several renders, D-134).
 * @param {string[]} changed what changed since the sweep was rendered
 * @param {string} [button] what renders it again: a trimmer's sweep has its own (D-198)
 * @returns {string}
 */
export function sweepStaleText(changed, button = "Render sweep") {
  if (!changed.length) return "";
  const list = changed.length === 1 ? changed[0] : `${changed.slice(0, -1).join(", ")} and ${changed.at(-1)}`;
  return `The sweep is from an older setup: the ${list} changed since. ${button} to update it.`;
}

/**
 * Pot positions for a render sweep: "0, 50, 100" (percent) → [0, 0.5, 1].
 * @param {string} text
 * @returns {{rotations: number[]} | {error: string}}
 */
export function parsePositions(text) {
  const parts = text.split(/[,\s]+/).filter(Boolean);
  if (!parts.length) return { error: "List the positions to render, e.g. 0, 50, 100." };
  if (parts.length > COMPARE_MAX) return { error: `Pick up to ${COMPARE_MAX} positions.` };
  const values = parts.map((p) => Number(p.replace(/%$/, "")));
  const bad = parts.find((_, i) => !Number.isFinite(values[i]) || values[i] < 0 || values[i] > 100);
  if (bad !== undefined) return { error: `${bad} isn't a position from 0 to 100 %.` };
  return { rotations: values.map((v) => v / 100) };
}

/**
 * What the panel says about a job. With an amp capture the output level is the
 * capture's, so the circuit's volume is no cure for peaks over full scale.
 * @param {Job} job @param {boolean} [amp] the render went through an amp capture
 */
export function jobText(job, amp = false) {
  if (job.state === "queued") return "Waiting for a free worker…";
  if (job.state === "running") return `Rendering… ${Math.round(job.progress * 100)} %`;
  if (job.state === "failed" || job.state === "cancelled") return job.message;
  const over = `Peaks ${(20 * Math.log10(job.peak)).toFixed(1)} dB over full scale`;
  const loud = job.peak <= 1 ? ""
    : amp ? ` ${over}, from the amp capture's own output level; playback may clip.`
    : ` ${over}: turn the circuit's volume down so playback doesn't clip.`;
  return `${job.label}: ${job.seconds.toFixed(1)} s.${loud}`;
}

/**
 * A peak (full scale 1) in dBFS, one decimal.
 * @param {number} peak
 */
export function dbfs(peak) {
  return peak > 0 ? `${(20 * Math.log10(peak)).toFixed(1)} dBFS` : "silence";
}

/**
 * A trim in dB as the slider shows it: "0 dB", "+3 dB", "−6 dB".
 * @param {number} db
 */
export function trimText(db) {
  return db === 0 ? "0 dB" : `${db > 0 ? "+" : "−"}${Math.abs(db)} dB`;
}

/**
 * How driven the amp sounds for a compression in dB (D-086's bands).
 * @param {number} db
 */
export function ampWord(db) {
  return db < 1 ? "clean" : db < 6 ? "breaking up" : db < 15 ? "driven" : "saturated";
}

/** @param {string} who @param {Take} take */
function ampLine(who, take) {
  const squash = take.amp_compression ?? 0;
  const how = squash < 1 ? "clean" : `${ampWord(squash)}, squashing ${squash.toFixed(0)} dB`;
  return `${who}: ${how} · peaks ${dbfs(take.amp_in ?? 0)} going in.`;
}

/**
 * How hard a take hit the amp capture, with the guitar alone (the dry take) under it.
 * 0 dBFS is the capture's full scale: the loudest input it was made with.
 * @param {Take | null} take @param {Take | null} dry
 */
export function ampText(take, dry) {
  if (!take?.amp || take.amp_in === undefined) return "";
  const alone = take.key === dry?.key;
  const lines = [ampLine(alone ? "Guitar alone" : "Amp", take)];
  if (!alone && dry?.amp_in !== undefined) lines.push(ampLine("Guitar alone", dry));
  if (take.input_db) lines.push(`Both after the amp input trim of ${trimText(take.input_db)}.`);
  if (take.amp_in > 1) {
    lines.push("That's past the capture's full scale, louder than anything it was made with, so it may not sound like the amp. Turn the amp input down.");
  }
  return lines.join("\n");
}

/**
 * Poll a job until it's done or failed, reporting each answer.
 * @param {Job} job
 * @param {(url: string) => Promise<Job>} get
 * @param {(job: Job) => void} onUpdate
 * @param {(ms: number) => Promise<void>} [sleep]
 * @returns {Promise<Job>}
 */
export async function waitForJob(job, get, onUpdate, sleep = (ms) => new Promise((r) => setTimeout(r, ms))) {
  onUpdate(job);
  while (job.state === "queued" || job.state === "running") {
    await sleep(POLL_MS);
    job = await get(`api/render/${job.id}`);
    onUpdate(job);
  }
  return job;
}

/**
 * Cancel render jobs (D-240), each id once. A job the server no longer knows (it
 * restarted) is already stopped, so its error is ignored.
 * @param {string[]} ids @param {(url: string, body: any) => Promise<any>} post
 * @returns {Promise<void>}
 */
export async function cancelJobs(ids, post) {
  await Promise.all([...new Set(ids)].map((id) => post(`api/render/${id}/cancel`, {}).catch(() => null)));
}

/**
 * @typedef {{freq: number[], pedal: number[], heard: number[], di: number[], pedal_top?: number}} Spectra a take's
 *   spectrum from the server (D-096), per 1/6-octave band: the pedal's output (dBV), the take
 *   as heard (dBFS) and the guitar input's pickup as a DI recorded it (dB, 0 without one);
 *   `pedal_top`, the highest frequency the pedal line can hold (D-105: half its rate, 48 kHz
 *   for a pedal take's 96 kHz simulation, the clip's own for a dry take; absent on older
 *   takes, which were 48 kHz)
 * @typedef {"pedal" | "heard"} SpectrumView where the spectrum is read: before or after the amp
 */

/** Below this a band is silence, not a level worth plotting. */
const QUIET_DB = -150;

/**
 * The spectrum's curves, in legend order: [id, label, plot style, the views it belongs to].
 * Expected ("Pedal (no clipping)") is the clip through the circuit's frequency curve at the knobs as
 * they are now, as if the pedal never clipped; the live area is what's playing, so only as heard. A sweep is one curve per position.
 */
export const SPECTRUM_CURVES = /** @type {const} */ ([
  ["dry", "Dry", "input", ["pedal", "heard"]],
  ["pedal", "Pedal", "current", ["pedal", "heard"]],
  ["snapshot", "Snapshot", "snapshot", ["pedal", "heard"]],
  ["expected", "Pedal (no clipping)", "expected", ["pedal", "heard"]],
  ["live", "Playing now", "live", ["heard"]],
]);

/**
 * The spectrum's level range per view (dB): fixed, so the plot doesn't rescale as it plays.
 * The floor is −80 (D-102): −100 dBV is 10 µV, far under any real pedal's noise.
 */
export const SPECTRUM_RANGE = { pedal: [-80, 10], heard: [-80, 0] };

/** Half the takes' 48 kHz rate: nothing after the amp goes above it (D-105). */
export const RECORDED_TOP_HZ = 24000;

/**
 * The hatch over the spectrum where no line can have anything (D-105), or null.
 * After the amp, above 24 kHz: the takes are 48 kHz WAVs played at 48 kHz, whatever the
 * clip's or the capture's own rate. Before the amp, only above what the dry clip holds
 * (half its rate) while Dry or Pedal (no clipping), which is built on Dry's bands, is
 * ticked: a 48 kHz clip stops at 24 kHz, a 96 kHz one reaches 30 kHz (no hatch). The
 * Pedal line, read from the 96 kHz simulation, always reaches 30 kHz.
 * @param {SpectrumView} view @param {Spectra | null} dry the dry take's spectra
 * @param {Set<string>} shown the ticked curves
 * @returns {{from: number, label: string} | null}
 */
export function spectrumHatch(view, dry, shown) {
  if (view === "heard") return { from: RECORDED_TOP_HZ, label: "nothing above 24 kHz: takes play at 48 kHz" };
  if (!dry || !(shown.has("dry") || shown.has("expected"))) return null;
  const top = dry.pedal_top ?? RECORDED_TOP_HZ;
  if (top >= PLOT_BAND[1]) return null;
  const khz = (/** @type {number} */ f) => `${Math.round(f / 100) / 10} kHz`;
  return { from: top, label: `Dry: nothing above ${khz(top)} (a ${khz(2 * top)} clip)` };
}

/**
 * The spectrum's level range: the view's own, raised (in 10 dB steps, 5 dB clear) only if
 * a take or Expected goes over it. The live area never moves it.
 * @param {SpectrumView} view @param {import("./series.js").PlotData} data
 * @returns {[number, number]}
 */
export function spectrumRange(view, data) {
  const [low, high] = SPECTRUM_RANGE[view];
  let top = -Infinity;
  for (const s of data.series) if (s.style !== "live") for (const v of s.values) if (v !== null && v > top) top = v;
  return [low, Math.max(high, Math.ceil((top + 5) / 10) * 10)];
}

/**
 * `y` (on `x`, rising) read at each of `at`, straight-line on a log frequency axis and
 * held flat past the ends.
 * @param {number[]} x @param {number[]} y @param {number[]} at
 * @returns {number[]}
 */
export function atFreqs(x, y, at) {
  const lx = x.map(Math.log10);
  let i = 0;
  return at.map((f) => {
    const l = Math.log10(f);
    if (l <= lx[0]) return y[0];
    if (l >= lx[lx.length - 1]) return y[y.length - 1];
    while (lx[i + 1] < l) i++;
    while (i > 0 && lx[i] > l) i--;
    const t = (l - lx[i]) / (lx[i + 1] - lx[i]);
    return y[i] + t * (y[i + 1] - y[i]);
  });
}

/**
 * What a take should look like from the frequency curve alone (D-096): the dry clip's
 * spectrum in `view`, plus the circuit's gain from the guitar to the output at each band,
 * less the pickup colour the render took out of the clip first. Where the take sits above
 * it, the circuit added harmonics (drive); a clean circuit matches it. After the amp it
 * holds only as far as the amp treats both alike (a driven amp squashes the louder more).
 * @param {Spectra} dry the dry take's spectra @param {Spectra} take the pedal take's (for its `di`)
 * @param {{freq: number[], db: number[]}} curve the output's frequency curve, in dB
 * @param {SpectrumView} [view]
 * @returns {Array<number | null>} on the dry take's bands
 */
export function expectedLevels(dry, take, curve, view = "pedal") {
  const gain = atFreqs(curve.freq, curve.db, dry.freq);
  const di = onBands(take.freq, take.di, dry.freq); // by frequency: the two takes' bands can differ (D-104)
  return dry[view].map((level, i) => (level < QUIET_DB ? null : level + gain[i] - (di[i] ?? 0)));
}

/**
 * The output's level as the spectrum reads it: a steady tone of `peak` volts in dBV (its
 * RMS, as `band_levels` gives a sine's band). @param {number} peak
 */
const toneDbv = (peak) => 20 * Math.log10(peak / Math.SQRT2);

/**
 * Where the pedal clips (D-096): the level its output reached on the probe's scope tone,
 * and about where clipping starts at the guitar (that level less the clean gain), both as
 * the spectrum reads them (dBV). Null when the scope reads clean.
 * @param {{peak_pos: number, peak_neg: number, clipping: {label: string, thd: number}}} stats
 *   the output's scope stats
 * @param {{level: string, freq: number, gainDb: number}} run the scope's pick level, its
 *   tone and the clean gain there (the frequency curve)
 * @returns {{reached: number, starts: number} | null}
 */
export function clipLevels(stats, run) {
  if (stats.clipping.label === "clean") return null;
  const reached = toneDbv(Math.max(Math.abs(stats.peak_pos), Math.abs(stats.peak_neg)));
  return { reached, starts: reached - run.gainDb };
}

/** A level in whole dBV with its sign ("−9 dBV"). @param {number} x */
const dbvText = (x) => {
  const r = Math.round(x);
  return `${r < 0 ? "−" : "+"}${Math.abs(r)} dBV`;
};

/**
 * What the spectrum says when the pedal clips (D-096). Expected is the clean prediction
 * and is left as it is; this says where the clipping is (`clipLevels`), so the gap can be
 * read. Null when the scope reads clean.
 * @param {Parameters<typeof clipLevels>[0]} stats @param {Parameters<typeof clipLevels>[1]} run
 * @returns {string | null}
 */
export function clipText(stats, run) {
  const levels = clipLevels(stats, run);
  if (!levels) return null;
  const pick = run.level === "med" ? "medium" : run.level;
  return `The pedal clips (${stats.clipping.label}, THD ${Math.round(stats.clipping.thd * 100)} % on the probe's ${run.freq} Hz tone at the ${pick} pick). `
    + `Its output reached about ${dbvText(levels.reached)} there, so it can't follow Pedal (no clipping) above that level. `
    + `With ${Math.round(run.gainDb)} dB of clean gain, it starts clipping at about ${dbvText(levels.starts)} at the guitar: where Dry sits above that, the pedal clips.`;
}

/**
 * The clip lines on the Pedal output view (Phase 8b): the two levels of `clipLevels` as
 * dashed lines across the spectrum, unlabelled (the line under the plot says which is
 * which, `clipLimitsText`). None in the other view or when the pedal is clean.
 * @param {ReturnType<typeof clipLevels>} levels @param {SpectrumView} view
 * @returns {Array<{y: number}>}
 */
export function clipLines(levels, view) {
  if (!levels || view !== "pedal") return [];
  return [{ y: levels.reached }, { y: levels.starts }];
}

/**
 * The line right under the spectrum while the clip lines are drawn: what the two are.
 * @param {ReturnType<typeof clipLevels>} levels
 * @returns {string}
 */
export function clipLimitsText(levels) {
  if (!levels) return "";
  return `Upper line: output reached ${dbvText(levels.reached)}. Lower line: clipping starts at ${dbvText(levels.starts)} at the guitar.`;
}

/**
 * The spectrum plot's data: each take that's there and ticked, in one view, with Expected
 * and the live area where they belong. The live area comes first so
 * it's drawn behind the lines. Every curve is placed on the full bands (`bandCentres`,
 * 10 Hz to 30 kHz) by frequency (`onBands`), so takes rendered before the bands reached
 * 10 Hz line up with newer ones and the live area (D-104); a band a curve doesn't have is
 * left empty. With nothing to show yet the axes are still there.
 * @param {SpectrumView} view
 * @param {Record<string, Spectra | null>} takes spectra by slot
 * @param {Set<string>} shown the ticked curves
 * @param {{expected?: Array<number | null> | null, live?: {freq: number[], levels: number[]} | null, playing?: string}} [extra]
 *   `expected`: on the dry take's bands (`expectedLevels`)
 *   `live`: the live area's bands
 *   `playing`: the slot playing, whose curve is drawn heavier
 * @returns {import("./series.js").PlotData}
 */
export function spectrumSeries(view, takes, shown, extra = {}) {
  const x = bandCentres();
  const clean = (/** @type {Array<number | null>} */ v) => v.map((d) => (d === null || d < QUIET_DB ? null : d));
  /** @param {{freq: number[]} | null | undefined} on @param {Array<number | null> | null | undefined} levels */
  const placed = (on, levels) => (on && levels ? onBands(on.freq, levels, x) : null);
  /** @type {import("./series.js").Series[]} */
  const series = [];
  for (const [id, label, style, views] of SPECTRUM_CURVES) {
    if (!shown.has(id) || !(/** @type {readonly string[]} */ (views)).includes(view)) continue;
    const values = id === "expected" ? placed(takes.dry, extra.expected) : id === "live" ? placed(extra.live, extra.live?.levels) : placed(takes[id], takes[id]?.[view]);
    if (!values) continue;
    if (id === "live") series.unshift({ label, values: clean(values), style });
    else series.push({ label, values: clean(values), style, bold: id === extra.playing });
  }
  return { x, series };
}

/**
 * Levels on bands `from` placed on bands `to` by frequency, not position: a take rendered
 * before the bands reached 10 Hz starts at 20 Hz, and the live area stops at its own
 * Nyquist; by position they sat an octave off (D-104). A band with no match within a
 * 1/24 octave is null.
 * @param {number[]} from @param {Array<number | null>} levels @param {number[]} to
 * @returns {Array<number | null>}
 */
export function onBands(from, levels, to) {
  return to.map((f) => {
    const i = from.findIndex((g) => Math.abs(Math.log2(g / f)) < 1 / 24);
    return i < 0 ? null : levels[i];
  });
}

/**
 * What a level smoothed over time reads after one more frame: an average of power with
 * weight `keep` on what it read before (none before: the frame itself).
 * @param {number[] | null} before @param {number[]} now in dB @param {number} keep 0–1
 * @returns {number[]}
 */
export function smoothLevels(before, now, keep) {
  if (!before || before.length !== now.length) return now;
  return now.map((d, i) => 10 * Math.log10(keep * 10 ** (before[i] / 10) + (1 - keep) * 10 ** (d / 10)));
}

/**
 * Levels read after a player's volume, as they are at full volume: the browser applies
 * the player's own volume before Web Audio sees the sound, and the live area is in dBFS
 * of the take, like the averages.
 * @param {number[]} levels in dB @param {number} volume the player's, 0–1
 * @returns {number[]}
 */
export function atFullVolume(levels, volume) {
  const lift = -20 * Math.log10(volume);
  return levels.map((d) => d + lift);
}

/**
 * Bands with no FFT bin in them (the lowest, narrower than the analysis resolution) read
 * as silence; for the live area they take a level between their neighbours instead.
 * @param {number[]} levels in dB @param {number} [silent] the level an empty band reads
 * @returns {number[]}
 */
export function fillEmptyBands(levels, silent = -200) {
  const known = levels.flatMap((d, i) => (d > silent ? [i] : []));
  if (!known.length) return levels;
  return levels.map((d, i) => {
    if (d > silent) return d;
    const after = known.find((k) => k > i);
    const before = known.findLast((k) => k < i);
    if (after === undefined || before === undefined) return d; // past the ends: nothing to go by
    return levels[before] + ((i - before) / (after - before)) * (levels[after] - levels[before]);
  });
}

/**
 * The short name a chip shows for a select's choice: its label up to " · ".
 * @param {string} label
 */
export function chipName(label) {
  return label.split(" · ")[0];
}

/**
 * The circuit's guitar input in a few words, for the Pedal chip: the pickup (by its guide
 * name, else "Your pickup"), cable and volume; "Buffered input" for a stiff source (with
 * its volume when one is set, D-134).
 * @param {any} circuit @param {Array<{kind: string, name: string}>} pickups the pickup guide
 * @returns {string}
 */
export function guitarSummary(circuit, pickups) {
  const guitar = (circuit?.parts ?? []).find((/** @type {any} */ p) => p.type === "guitar");
  if (!guitar) return "No guitar input";
  const vol = guitar.volume ? [`vol ${Math.round((guitar.rotation ?? 1) * 10)}`] : [];
  if (guitar.source !== "pickup" || !guitar.pickup) return ["Buffered input", ...vol].join(" · ");
  const name = pickups.find((p) => p.kind === guitar.pickup.kind)?.name ?? "Your pickup";
  const parts = [name];
  if (guitar.cable) parts.push(`${guitar.cable} m`);
  return [...parts, ...vol].join(" · ");
}

/** The trimmer sweep's positions (D-198): a few, since a trimmer is set once, not played. */
export const TRIM_POSITIONS = [0.25, 0.5, 0.75];

/** What a stuck stage does, by its state from the server's saturation check. */
const STUCK_WORDS = /** @type {Record<string, string>} */ ({
  saturated: "saturates", "cut off": "switches off", triode: "stops amplifying", railed: "sticks at a rail",
});

/**
 * The circuit's trimmers for the Audio pane's Trimmers fold (D-198): each with its name
 * and, if its bias target sets it, why it can't be swept.
 * @param {any} circuit
 * @returns {Array<{ref: string, name: string, held: string | null}>}
 */
export function trimmerRows(circuit) {
  return (circuit?.parts ?? []).filter((/** @type {any} */ p) => p.type === "trimmer").map((/** @type {any} */ p) => ({
    ref: p.ref,
    name: p.label ? `${p.label} · ${p.ref}` : p.ref,
    held: p.bias_target
      ? `Set by its target (${p.bias_target.node} at ${p.bias_target.volts} V). Open it and remove the target to sweep it.`
      : null,
  }));
}

/**
 * Per position, what the saturation check found, in a few words ("Q2 saturates"; "" if
 * nothing), and a line saying what it means ("" if nothing was found).
 * @param {number[]} rotations
 * @param {Array<Array<{ref: string, state: string}>>} found the server's check, per position
 * @returns {{marks: string[], text: string}}
 */
export function stuckText(rotations, found) {
  const marks = found.map((stuck) => stuck.map((s) => `${s.ref} ${STUCK_WORDS[s.state] ?? s.state}`).join(", "));
  const at = marks.map((m, i) => (m ? `at ${Math.round(rotations[i] * 100)} % ${m}` : "")).filter(Boolean);
  if (!at.length) return { marks, text: "" };
  const list = at.length === 1 ? at[0] : `${at.slice(0, -1).join("; ")} and ${at.at(-1)}`;
  const takes = at.length === 1 ? "that take is" : "those takes are";
  return { marks, text: `${list[0].toUpperCase()}${list.slice(1)}: ${takes} a broken bias, not a sound.` };
}
