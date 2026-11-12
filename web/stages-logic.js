/**
 * The Bias & headroom pane's logic (Phase 8c, D-106), no DOM: how a row's numbers from
 * `POST /api/stages` read. The measures are the server's (`solum/stages.py`,
 * `probe.stages_view`); this only words and colours them.
 */

import { nextRef } from "./editor/edit.js";
import { volts as fixedVolts } from "./fixed.js";
import { insertInSeries, makeRoom } from "./editor/insert.js";
import { pinPositions } from "./schematic/symbols.js";

/** The pick levels, in order, as the Scope names them. */
export const LEVELS = /** @type {const} */ ([["soft", "Soft"], ["med", "Medium"], ["hard", "Hard"]]);

/** Each pick's colour on the level diagram (and a card's Waveform): the harder, the stronger. */
export const PICK_STYLES = { soft: "sweep-12", med: "sweep-6", hard: "sweep-1" };

/** The guitar levels (volts peak) the level in → out curve measures: 12, evenly in dB
 * from 3 mV (a soft single coil) to 3 V (past the hardest pick). */
export const SWEEP_LEVELS = Array.from({ length: 12 }, (_, i) => 0.003 * 10 ** ((3 * i) / 11));

/** Spare room under this (dB) reads "near" its limit. */
export const NEAR_DB = 6;

/**
 * @typedef {{predicted: number, up: number, down: number, thd: number, clipping: string,
 *   title: string, clips: boolean, headroom_db?: number | null, held?: boolean, drive_db?: number, asymmetry?: number,
 *   harmonics?: string}} Cell one pick level's readings
 * @typedef {{kind: "stage" | "clipper", refs: string[], label: string, role: string, net: string,
 *   state: string | null, levels: Record<string, Cell>, gain_db: Record<string, number>, parts: string[],
 *   bias?: {v: number, up: number | null, down: number | null, position: number, place: string, limits: string, text: string},
 *   clamp?: {up: number, down: number, text: string, short: string, even: boolean}, limit?: number | null}} Row `limit`: the peak (volts) it
 *   can reach before it clips (a stage's room the nearer way, a clipper to ground's clamp); none when nothing
 *   limits it, or for a clipper in feedback or series (the clamp is across it, not at its node). `gain_db`: its own
 *   small-signal gain at each test tone (keyed "100", "200", "1000", "3000"); `parts`: what a click lights (D-122)
 * @typedef {{ref: string, name: string, at: "block" | "arrow" | "end", index: number, rotation: number}} PotChip a
 *   knob on the chain (D-122): on block `index`, on the arrow after row `index` (-1: the guitar), or at the end
 * @typedef {{rows: Row[], summary: string, note: string | null, picks: Record<string, number>, tone: number,
 *   settled: boolean | null, pots: PotChip[], arrows?: Array<Record<string, number> | null>}} Stages one tone's
 *   measures; `settled` false: still drifting; null: not checked; `arrows`: each arrow's loss in dB by tone (D-123)
 * @typedef {{amplitude: number, rows: Array<{net: string, peak: number, predicted: number}>}} LevelPoint one
 *   input level's peaks, from `POST /api/stages/level`
 * @typedef {"ok" | "near" | "over" | "held" | "clip" | "off"} Tone how a cell is coloured
 */

/**
 * One pick level of a row, in words and as a tone: a stage's spare room ("12 dB spare",
 * "over by 4 dB", "held": its diodes stop it short of its limits), a clipper's drive ("driven 9 dB", "not
 * clipping"). With a saturated stage the readings mean little ("—").
 * @param {Row} row @param {Cell} cell
 * @returns {{text: string, tone: Tone}}
 */
export function cellText(row, cell) {
  if (row.state) return { text: "—", tone: "off" };
  if (row.kind === "clipper") {
    return cell.clips ? { text: `driven ${Math.round(cell.drive_db ?? 0)} dB`, tone: "clip" } : { text: "not clipping", tone: "ok" };
  }
  if (cell.held) return { text: "held", tone: "held" };
  const room = cell.headroom_db;
  if (room === null || room === undefined) return { text: "no signal", tone: "off" };
  if (room < 0) return { text: `over by ${Math.round(-room)} dB`, tone: "over" };
  return { text: `${Math.round(room)} dB spare`, tone: room < NEAR_DB ? "near" : "ok" };
}

/**
 * A block's waveform at each pick, overlaid in the level diagram's colours (a card's
 * Waveform section, D-127), from `POST /api/stages/waves`.
 * @param {{time_ms: number[], waves: Record<string, number[]>}} got
 * @returns {import("./series.js").PlotData}
 */
export function waveSeries(got) {
  const series = LEVELS.filter(([id]) => got.waves[id]).map(([id, name]) => ({ label: name, style: PICK_STYLES[id], values: got.waves[id] }));
  return { x: got.time_ms, series };
}

/**
 * The Waveform section's table: a row per reading, a column per pick, from the row's own
 * cells (nothing measured again). @param {Row} row @returns {Array<{name: string, cells: string[]}>}
 */
export function waveTable(row) {
  const cells = LEVELS.map(([id]) => row.levels[id]);
  return [
    { name: "Peak +", cells: cells.map((c) => `+${volts(c.up)}`) },
    { name: "Peak \u2212", cells: cells.map((c) => volts(-c.down)) },
    { name: "Clipping", cells: cells.map((c) => c.clipping || "\u2014") },
    { name: "THD", cells: cells.map((c) => thdText(c.thd)) },
  ];
}

/** "0.4 %", "12 %". @param {number} thd a fraction */
function thdText(thd) {
  const pc = thd * 100;
  return `${pc < 1 ? pc.toFixed(1) : Math.round(pc)} %`;
}

/**
 * A clipper's character at a hard pick, after its clamp: which harmonics lead.
 * @param {Row} row @returns {string}
 */
export function clipperText(row) {
  const lead = row.levels.hard?.harmonics;
  const said = lead === "even" ? "Mostly even harmonics (2nd, 4th): it clips one way more than the other."
    : lead === "odd" ? "Mostly odd harmonics (3rd, 5th): it clips both ways alike."
    : "Even and odd harmonics alike.";
  return `${row.clamp?.text ?? ""} ${said}`.trim();
}

/**
 * Where the bias mark sits on its bar, in % from the bottom limit (0) to the top (100),
 * and how the bar is coloured: off-centre is "near", saturated "over".
 * @param {Row} row @returns {{at: number, tone: Tone} | null}
 */
export function biasMark(row) {
  if (!row.bias) return null;
  const at = Math.round(Math.min(1, Math.max(0, row.bias.position)) * 100);
  return { at, tone: row.state ? "over" : row.bias.place === "centred" ? "ok" : "near" };
}

/** What a row is, after its name: "gain stage · q1c", "clipper to ground · clip". @param {Row} row */
export function roleText(row) {
  return row.kind === "clipper" ? `clipper ${row.role} · ${row.net}` : `${row.role} · ${row.net}`;
}

/** Volts peak as dBV (0 dBV = 1 V peak) for a plot; null when there's nothing to plot.
 * @param {number | null | undefined} v */
export function dbv(v) {
  return v != null && v > 0 && Number.isFinite(v) ? 20 * Math.log10(v) : null;
}

/**
 * The level diagram: along the signal path (the guitar, then each row in order), the peak
 * each pick reaches (solid), what it would reach unclipped (dashed) and the row's limit
 * (a dot).
 * Where a line meets the limit the stage clips. A saturated row has no points.
 * `before`: the chain when Try changes began (D-123): each pick's line as it was, faint,
 * matched to the rows now by label (a row that wasn't there has no point).
 * @param {Stages} data @param {Stages | null} [before] @returns {import("./series.js").PlotData}
 */
export function levelDiagram(data, before = null) {
  const names = ["Guitar", ...data.rows.map((r) => r.label)];
  const per = (/** @type {(r: Row) => number | null | undefined} */ f) => data.rows.map((r) => (r.state ? null : dbv(f(r))));
  const peak = (/** @type {Row} */ r, /** @type {string} */ id) => Math.max(r.levels[id].up, r.levels[id].down);
  /** @type {import("./series.js").Series[]} */
  const series = LEVELS.flatMap(([id, name]) => {
    const style = PICK_STYLES[id];
    const guitar = dbv(data.picks[id]);
    return [
      { label: name, style, values: [guitar, ...per((r) => peak(r, id))] },
      { label: `${name}, unclipped`, style, dash: true, values: [guitar, ...per((r) => r.levels[id].predicted)] },
    ];
  });
  series.push({ label: "Limit", style: "expected", dots: true, values: [null, ...per((r) => r.limit)] });
  if (before) {
    const was = new Map(before.rows.map((r) => [r.label, r]));
    for (const [id] of LEVELS) {
      const values = data.rows.map((r) => {
        const old = was.get(r.label);
        return old && !old.state ? dbv(peak(old, id)) : null;
      });
      series.push({ label: "Before", style: PICK_STYLES[id], faint: true, values: [dbv(before.picks[id]), ...values] });
    }
  }
  return { x: names.map((_, i) => i), xText: names, series };
}

/**
 * The level in → out curve: for each net on the path (a clipper and the stage it sits on
 * share one), the peak it reaches against the guitar's, both in dBV, with the guitar
 * itself as the dashed straight line. Where a line bends flat, that stage compresses.
 * @param {Row[]} rows @param {LevelPoint[]} points any order; the ones measured so far
 * @param {string} [lit] the net of the row hovered: its line drawn bold
 * @param {LevelPoint[] | null} [before] the curve when Try changes began (D-123): each
 *   net's line as it was, faint, at the same levels (a net it hadn't has none)
 * @returns {import("./series.js").PlotData}
 */
export function levelCurve(rows, points, lit, before = null) {
  const nets = curveNets(rows);
  const sorted = [...points].sort((a, b) => a.amplitude - b.amplitude);
  const x = sorted.map((p) => /** @type {number} */ (dbv(p.amplitude)));
  const peakAt = (/** @type {LevelPoint | undefined} */ p, /** @type {string} */ net) => dbv(p?.rows.find((r) => r.net === net)?.peak);
  /** @type {import("./series.js").Series[]} */
  const series = nets.map((n) => {
    const label = n.labels.join(" · ");
    return { label, tag: label, style: n.style, values: sorted.map((p) => peakAt(p, n.net)), bold: n.net === lit };
  });
  if (before?.length) {
    const was = new Map(before.map((p) => [p.amplitude, p]));
    for (const n of nets) series.push({ label: "Before", style: n.style, faint: true, values: sorted.map((p) => peakAt(was.get(p.amplitude), n.net)) });
  }
  return { x, series: [{ label: "Guitar", style: "input", values: [...x] }, ...series] };
}

/**
 * The level in → out curve's lines: one per net along the path (a clipper on its stage's
 * output shares that line), each with its colour (`sweep-1` … `sweep-12`, spread over
 * the lines). The strip over the curve gives each block its line's colour (D-123).
 * @param {Row[]} rows @returns {Array<{net: string, labels: string[], style: string}>}
 */
export function curveNets(rows) {
  /** @type {Array<{net: string, labels: string[]}>} */
  const nets = [];
  for (const r of rows) {
    const found = nets.find((n) => n.net === r.net);
    if (found) found.labels.push(r.label);
    else nets.push({ net: r.net, labels: [r.label] });
  }
  const last = Math.max(nets.length - 1, 1);
  return nets.map((n, i) => ({ ...n, style: `sweep-${1 + Math.round((i * 11) / last)}` }));
}

/** Where the three picks sit on the level in → out curve's guitar axis. @param {Record<string, number>} picks */
export function pickLines(picks) {
  return LEVELS.map(([id, name]) => ({ x: /** @type {number} */ (dbv(picks[id])), label: `${name} pick` }));
}

/**
 * @typedef {Record<string, Record<string, any>>} Patches fields to set, per part
 * @typedef {{ref: string, set: Patches, undo: Patches, label: string, text: string, key?: string,
 *   add?: import("./editor/edit.js").EditDiff, room?: import("./editor/edit.js").EditDiff, roomText?: string, moved?: string[]}} FixOption
 *   one change from `POST /api/stages/bias`, `/gain` or `/clipper` (D-119, D-123): what
 *   it sets, what puts it back, its History words and its sentence; an arrangement (D-124)
 *   sets nothing but adds parts: `key` names it, `add` is what placing it added, `room`
 *   what making room for it moved first (`roomText` in words, `moved` the parts)
 */

/**
 * Whether a row offers Centre: a stage whose bias isn't centred (or saturated, as its
 * warning says). A clipper has no bias of its own.
 * @param {Row} row @returns {boolean}
 */
export function canCentre(row) {
  return row.kind === "stage" && !!row.bias && (row.bias.place !== "centred" || !!row.state);
}

/**
 * The fields a Try sets (D-123): `option`'s, over the fields of the option this fix had
 * in before put back as they were when Try changes began (`start`), so trying R14 after
 * R9 leaves R9 as it was, and turning a trimmer after holding it takes its target off.
 * @param {FixOption | null} tried @param {FixOption} option
 * @param {{parts: Array<Record<string, any>>}} start @returns {Patches}
 */
export function tryPatches(tried, option, start) {
  /** @type {Patches} */
  const out = {};
  for (const [ref, fields] of Object.entries(tried && tried !== option ? tried.set : {})) out[ref] = startFields(start, ref, Object.keys(fields));
  for (const [ref, fields] of Object.entries(option.set)) out[ref] = { ...(out[ref] ?? {}), ...fields };
  return out;
}

/**
 * Part `ref`'s `fields` in `circuit`, null where it has none (so setting them takes a
 * field added since off). @param {{parts: Array<Record<string, any>>}} circuit
 * @param {string} ref @param {string[]} fields @returns {Record<string, any>}
 */
export function startFields(circuit, ref, fields) {
  const part = circuit.parts.find((p) => p.ref === ref);
  return Object.fromEntries(fields.map((f) => [f, part?.[f] ?? null]));
}

/**
 * Whether `option`'s values are in `circuit` now: the fix box marks it Trying (so an
 * Undo inside the session, or a part put back, shows as it is).
 * @param {FixOption} option @param {{parts: Array<Record<string, any>>}} circuit
 */
export function optionIn(option, circuit) {
  // an added part is in when it's there as placed: its place and its value or model
  const at = (/** @type {Record<string, any>} */ p) => circuit.parts.some((q) => Object.entries(p).every(([f, v]) => JSON.stringify(q[f]) === JSON.stringify(v)));
  if (option.add && !option.add.parts.every(at)) return false;
  return Object.entries(option.set).every(([ref, fields]) => {
    const now = startFields(circuit, ref, Object.keys(fields));
    return Object.entries(fields).every(([f, v]) => JSON.stringify(now[f]) === JSON.stringify(v ?? null));
  });
}

/**
 * The option of a fix box that's in `circuit` now (Trying), or null: of those whose values
 * are in, the one setting the most parts (an LED pair is in, so its lopsided half is too).
 * @param {FixOption[]} options @param {{parts: Array<Record<string, any>>}} circuit
 * @returns {FixOption | null}
 */
export function triedOption(options, circuit) {
  const size = (/** @type {FixOption} */ o) => Object.keys(o.set).length + (o.add?.parts.length ?? 0);
  return options.filter((o) => optionIn(o, circuit)).reduce((best, o) => (!best || size(o) > size(best) ? o : best), /** @type {FixOption | null} */ (null));
}

/** The resistors a clipper to ground is tried with in series (D-124): the Rat's mod, a softer knee. */
export const SERIES_RESISTORS = ["1k", "2k2", "4k7"];

/**
 * @typedef {{circuit: import("./editor/edit.js").Circuit, moved: string[], ways: string[]}} Room
 *   the sheet with room made for an arrangement (`makeRoom`): the parts it moved, and which ways
 */

/**
 * The arrangements Try changes offers a clipper (D-124), each placed in a copy of
 * `circuit` (`insertInSeries`): two in series (each diode doubled), 2 + 1 (the second of
 * a pair doubled) and, for a clipper to ground, a resistor in series with each diode (as
 * one with the pair: only one of them conducts at a time). The new part goes beside the
 * diode's pin at a label (a ground symbol) when it has one, else beside the other pin.
 * Where neither pin has room, room is made first (`makeRoom`: the sheet split past a
 * pin and moved out a part's length, on the side that moves fewest parts, `room`), and only when that doesn't give room either
 * does the part go to a clear spot further off. `series` says what went where, for the
 * server's check: [new ref, its pin that meets the diode, diode, the diode's pin].
 * `missed`: the diodes nothing could go in series with.
 * @param {import("./editor/edit.js").Circuit} circuit @param {Row} row
 * @returns {{arranged: Array<{key: string, circuit: import("./editor/edit.js").Circuit, series: string[][], room: Room | null}>, missed: string[]}}
 */
export function arrangements(circuit, row) {
  const diodes = row.refs.map((r) => circuit.parts.find((p) => p.ref === r)).filter((p) => p && (p.type === "diode" || p.type === "led"));
  const copy = (/** @type {any} */ d) => ({ type: d.type, model: d.model });
  /** @type {Array<[string, Array<[any, Record<string, string>]>]>} */
  const plans = [["doubled", diodes.map((d) => [d, copy(d)])]];
  if (diodes.length === 2) plans.push(["uneven", [[diodes[1], copy(diodes[1])]]]);
  if (row.role === "to ground") for (const v of SERIES_RESISTORS) plans.push([`resistor ${v}`, diodes.map((d) => [d, { type: "resistor", value: v }])]);
  const labelled = (/** @type {number[]} */ p) => (circuit.labels ?? []).some((lb) => lb.pos[0] === p[0] && lb.pos[1] === p[1]);
  const pinsOf = (/** @type {any} */ d) => Object.entries(pinPositions(d)).sort(([, p], [, q]) => Number(labelled(q)) - Number(labelled(p))).map(([name]) => name);
  const nearOf = (/** @type {Record<string, string>} */ fields, /** @type {string} */ pin) => (fields.type === "resistor" ? "1" : pin === "K" ? "A" : "K");
  const partFor = (/** @type {any} */ c, /** @type {Record<string, string>} */ fields) => ({ ref: nextRef(c, fields.type === "resistor" ? "R" : "D"), ...fields });
  /** @type {Array<{key: string, circuit: any, series: string[][], room: Room | null}>} */
  const arranged = [];
  const missed = new Set();
  for (const [key, adds] of plans) {
    // first, room where a diode has none beside either pin
    let c = circuit;
    const moved = new Set();
    const ways = new Set();
    for (const [d, fields] of adds) {
      const fits = (/** @type {any} */ cc) => pinsOf(d).some((pin) => insertInSeries(cc, d.ref, pin, partFor(cc, fields), nearOf(fields, pin), { spot: false }));
      if (fits(c)) continue;
      // the side that moves fewest parts
      const made = pinsOf(d).map((pin) => makeRoom(c, d.ref, pin)).filter((m) => m && fits(m.circuit))
        .reduce((best, m) => (!best || /** @type {any} */ (m).moved.length < best.moved.length ? m : best), /** @type {any} */ (null));
      if (!made) continue;
      c = made.circuit;
      for (const r of made.moved) moved.add(r);
      ways.add(made.way);
    }
    const room = c === circuit ? null : { circuit: c, moved: [...moved], ways: [...ways] };
    // then the parts: beside a pin (either pin), a clear spot further off only when neither has room
    const series = [];
    for (const [d, fields] of adds) {
      const part = partFor(c, fields);
      let placed = null;
      for (const spot of [false, true]) {
        for (const pin of pinsOf(d)) {
          const next = placed ? null : insertInSeries(c, d.ref, pin, part, nearOf(fields, pin), { spot });
          if (next) placed = { pin, next };
        }
      }
      if (!placed) {
        missed.add(d.ref);
        break;
      }
      c = placed.next;
      series.push([part.ref, nearOf(fields, placed.pin), d.ref, placed.pin]);
    }
    if (series.length === adds.length) arranged.push({ key, circuit: c, series, room });
  }
  return { arranged, missed: [...missed] };
}

/**
 * What making room moves, in words (D-124): "C20, C21 and 12 others down", "the wires
 * and labels below D1 down" when no part moved.
 * @param {Room} room @param {string[]} [diodes] what it was made for, when no part moved
 */
export function roomText(room, diodes = []) {
  const n = room.moved.length;
  const what = !n ? `the wires and labels past ${diodes.join(", ") || "the diodes"}`
    : n <= 3 ? room.moved.join(", ")
    : `${room.moved.slice(0, 2).join(", ")} and ${n - 2} others`;
  return `${what} ${room.ways.join(" and ")}`;
}

/** What Try changes changes, for its Changed list and History (D-123). */
export const TRY_FIELDS = ["value", "model", "rotation", "bias_target"];

/**
 * Try changes' History step: "Bias & headroom: R9, D3, D4" (each part changed once), as Edit curve's is "Edit curve: C3".
 * @param {Array<{ref: string}>} changes
 */
export function tryLabel(changes) {
  const refs = [...new Set(changes.map((c) => c.ref))];
  return refs.length ? `Bias & headroom: ${refs.join(", ")}` : "Bias & headroom";
}

/**
 * The parts Try changes added (D-124), as Changed list entries: "D5 added: 1N4148".
 * @param {{parts: Array<Record<string, any>>}} start @param {{parts: Array<Record<string, any>>}} now
 * @returns {Array<{ref: string, field: string, from: string, to: string}>}
 */
export function addedChanges(start, now) {
  const had = new Set(start.parts.map((p) => p.ref));
  return now.parts.filter((p) => !had.has(p.ref)).map((p) => ({ ref: p.ref, field: "added", from: "", to: String(p.model ?? p.value ?? p.type) }));
}

/** One line of Try changes' Changed list: "R9 470k → 270k", "RT1 target Q1.D 9 V → Q1.D 4 V", "D5 added: 1N4148". @param {{ref: string, field: string, from: string, to: string}} c */
export function changeText(c) {
  if (c.field === "added") return `${c.ref} added: ${c.to}`;
  if (c.field === "room") return `Moved ${c.to} to make room`;
  const what = { rotation: " rotation", bias_target: " target" }[c.field] ?? "";
  return `${c.ref}${what} ${c.from} \u2192 ${c.to}`;
}

/** The undo step a fix makes ("Centre Q4: R9 470k → 270k"). @param {string} title @param {FixOption} option */
export function fixLabel(title, option) {
  return `${title}: ${option.label}`;
}

/**
 * A fix's name, for its session in History: "Centre Q4", "Bias Q4", "Gain U2",
 * "Diodes D1, D2". @param {"bias" | "gain" | "clipper"} kind @param {Row} row @param {number | null} [aim]
 */
export function fixTitle(kind, row, aim = null) {
  if (kind === "bias") return `${aim === null ? "Centre" : "Bias"} ${row.refs[0]}`;
  return `${kind === "gain" ? "Gain" : "Diodes"} ${row.label}`;
}

/**
 * Where an aim on the bias bar puts a stage's output (D-123): `t` from 0 (the bottom of
 * its room) to 1 (the top), as volts and room each way; null when a side has no limit.
 * @param {NonNullable<Row["bias"]>} bias @param {number} t
 */
export function biasAim(bias, t) {
  if (bias.up === null || bias.down === null) return null;
  const span = bias.up + bias.down;
  const v = bias.v - bias.down + t * span;
  return { v, up: span * (1 - t), down: span * t, text: `Aim: ${volts(v)}, ${volts(span * (1 - t))} up, ${volts(span * t)} down` };
}

/**
 * What the bias bar says about how far Bias to… can move a stage (D-123), from
 * `POST /api/stages/reach`: null while unknown (the bar is aimable anywhere); the hint;
 * whether it can be aimed at all (and why not); and the parts of the bar out of reach,
 * as percents. Measured from where the stage sits now, so after a Try it's what one more
 * change can reach.
 * @param {{lo: number, hi: number, aimable: boolean, why: string | null} | null | undefined} reach
 * @returns {{text: string, aimable: boolean, out: Array<[number, number]>} | null}
 */
export function reachText(reach) {
  if (!reach) return null;
  if (!reach.aimable) return { text: `Can't be aimed. ${reach.why ?? ""}`.trim(), aimable: false, out: [] };
  const out = /** @type {Array<[number, number]>} */ ([[0, reach.lo * 100], [reach.hi * 100, 100]].filter(([a, b]) => b - a > 3)); // 2 % at each end is out of reach for every stage
  return { text: out.length ? "Drag the mark on its bar to aim its output voltage; the hatched ends are more than one part change can reach." : "Drag the mark on its bar to aim its output voltage anywhere.", aimable: true, out };
}

/**
 * A stage's bias bar's two ends in volts (the limits of its room), for the scale under
 * it: null when a side has no limit. @param {NonNullable<Row["bias"]>} bias
 */
export function biasScale(bias) {
  const [lo, hi] = [biasAim(bias, 0), biasAim(bias, 1)];
  return lo && hi ? { low: volts(lo.v), high: volts(hi.v) } : null;
}

/** Volts as the pane writes them: "4.52 V", "12.3 V". @param {number} v */
function volts(v) {
  return fixedVolts(v, Math.abs(v) < 10 ? 2 : 1);
}

/**
 * @typedef {{value: string, now: boolean, gain_db: number, own_db?: number, clips: Record<string, boolean>, text: string, chain: string}} GainStep
 *   one value on a gain part's slider (D-125): what reaches the next block (`gain_db`, D-223) and the stage's own gain change,
 *   whether anything clips at each pick (estimated), its two lines
 * @typedef {{ref: string, kind: string, value: string, nudge_db: number, text: string, steps: GainStep[], note?: string | null}} GainPart
 */

/**
 * Where each step sits on a gain slider, 0 to 1 by its gain change (the steps come sorted
 * by it), so the ends are the most and least gain one part reaches.
 * @param {GainStep[]} steps @returns {number[]}
 */
export function gainSpots(steps) {
  const lo = steps[0]?.gain_db ?? 0;
  const hi = steps.at(-1)?.gain_db ?? 0;
  return steps.map((s) => (hi > lo ? (s.gain_db - lo) / (hi - lo) : 0.5));
}

/** The step nearest `t` (0 to 1) on a slider. @param {number[]} spots @param {number} t */
export function nearestStep(spots, t) {
  return spots.reduce((best, x, i) => (Math.abs(x - t) < Math.abs(spots[best] - t) ? i : best), 0);
}

/**
 * The marks on a gain slider (D-125): for each pick, where things start (or stop)
 * clipping along it, halfway between the two steps either side, and which side clips.
 * None for a pick that clips (or doesn't) all along.
 * @param {GainStep[]} steps
 * @returns {Array<{at: number, level: string, name: string, up: boolean, title: string}>}
 */
export function clipMarks(steps) {
  const spots = gainSpots(steps);
  return LEVELS.flatMap(([level, name]) => {
    const marks = [];
    for (let i = 0; i + 1 < steps.length; i++) {
      const [a, b] = [steps[i].clips[level], steps[i + 1].clips[level]];
      if (a === b) continue;
      const up = b; // clipping from here up the slider
      marks.push({ at: (spots[i] + spots[i + 1]) / 2, level, name, up,
        title: `${up ? "Above" : "Below"} this, something clips at a ${name.toLowerCase()} pick` });
    }
    return marks;
  });
}

/**
 * A gain slider's step as a Try (D-125): its value in, what the box began with put back.
 * The step the box began at puts it back as it was.
 * @param {GainPart} part @param {GainStep} step @returns {FixOption}
 */
export function stepOption(part, step) {
  const label = step.now ? `${part.ref} back to ${part.value}` : `${part.ref} ${part.value} \u2192 ${step.value}`;
  return { ref: part.ref, set: { [part.ref]: { value: step.value } }, undo: { [part.ref]: { value: part.value } }, label, text: step.text };
}

/** An arrow's loss under this (dB either way) isn't shown: a coupling cap, a buffer's output. */
export const ARROW_SHOWN_DB = 1;

/**
 * What an arrow's passive parts do at the tone (D-123): "−17 dB", or null when there's
 * nothing to say (a loss under `ARROW_SHOWN_DB`, or no separate net to measure).
 * @param {Record<string, number> | null | undefined} arrow @param {number} tone
 */
export function arrowLoss(arrow, tone) {
  const db = arrow?.[String(tone)];
  return db === undefined || Math.abs(db) < ARROW_SHOWN_DB ? null : signedDb(db);
}

/** The tones the pane measures at (D-122), as the picker names them. */
export const TONES = /** @type {const} */ ([[100, "100 Hz"], [200, "200 Hz"], [1000, "1 kHz"], [3000, "3 kHz"]]);

/** A tone as the pane writes it ("1 kHz"). @param {number} tone */
export function toneName(tone) {
  return TONES.find(([t]) => t === tone)?.[1] ?? `${tone} Hz`;
}

/** dB with a sign, minus as "−" ("+38 dB", "−6 dB"). @param {number} db */
export function signedDb(db) {
  const r = Math.round(db);
  return `${r > 0 ? "+" : r < 0 ? "\u2212" : ""}${Math.abs(r)} dB`;
}

/** What a block on the chain is, short: "gain stage", "buffer", "op-amp stage", "diodes to ground". @param {Row} row */
/**
 * A discrete op-amp's transistors and what each does (D-224), in signal order, or null for
 * any other row. Its refs come output first, then the + and − inputs.
 * @param {Row} row @returns {Array<{ref: string, job: string}> | null}
 */
export function discreteParts(row) {
  if (row.role !== "discrete op-amp") return null;
  const [out, plus, minus] = row.refs;
  return [{ ref: plus, job: "+ in" }, { ref: minus, job: "− in" }, { ref: out, job: "out" }];
}

/**
 * What a discrete op-amp is, for its card (D-224); "" for any other row.
 * @param {Row} row @returns {string}
 */
export function discreteText(row) {
  const parts = discreteParts(row);
  if (!parts) return "";
  const [plus, minus, out] = parts.map((p) => p.ref);
  return `A discrete op-amp: ${plus} and ${minus} are a differential pair (its + and − inputs), ${out} its output stage. `
    + `It works as an op-amp chip does: its feedback, from ${out} back to ${minus}, sets its gain, so it's measured from ${plus}'s input to ${out}'s output.`;
}

export function blockRole(row) {
  return row.kind === "clipper" ? `diodes ${row.role}` : row.role;
}

/**
 * The marks on a block (D-122): a clipper's kind of clipping (hard: to ground; soft: in
 * feedback; in series), lopsided for an uneven pair or a stage biased off centre, and
 * "clips" for a stage that runs out of room at a hard pick (the device itself).
 * @param {Row} row @returns {Array<{text: string, tone: Tone, title: string}>}
 */
export function blockMarks(row) {
  /** @type {Array<{text: string, tone: Tone, title: string}>} */
  const marks = [];
  if (row.kind === "clipper") {
    const kind = row.role === "to ground" ? ["hard", "Diodes to ground: they cut the peaks off sharply."]
      : row.role === "in feedback" ? ["soft", "Diodes in the feedback: they round the peaks off as the gain falls."]
      : ["in series", "Diodes in series with the signal: it has to get past them."];
    marks.push({ text: kind[0], tone: row.levels.hard?.clips ? "clip" : "ok", title: kind[1] });
    if (row.clamp && !row.clamp.even) marks.push({ text: "lopsided", tone: "near", title: "It clamps further one way than the other: an uneven pair." });
  } else {
    if (row.levels.hard?.clips) marks.push({ text: "clips", tone: "over", title: "It runs out of room at a hard pick: the device itself clips." });
    if (row.bias && row.bias.place !== "centred") {
      marks.push({ text: "lopsided", tone: "near", title: `It ${row.bias.place}: it clips on that side first.` });
    }
  }
  return marks;
}

/**
 * How hard a row is pushed at a hard pick, for comparing tones: a clipper's drive, a
 * stage's lack of room (minus its spare dB); none for a held or saturated stage.
 * @param {Row} row @returns {number | null}
 */
function push(row) {
  const cell = row.levels.hard;
  if (!cell || row.state) return null;
  if (row.kind === "clipper") return cell.drive_db ?? null;
  if (cell.held || cell.headroom_db == null) return null;
  return -cell.headroom_db;
}

/**
 * The tone a row is pushed hardest at, among those measured (`byTone`), or null when
 * fewer than two are measured or nothing says.
 * @param {Map<number, Stages>} byTone @param {number} index the row @returns {number | null}
 */
export function rowWorst(byTone, index) {
  if (byTone.size < 2) return null;
  let worst = null;
  let most = -Infinity;
  for (const [tone, data] of byTone) {
    const r = data.rows[index];
    const p = r ? push(r) : null;
    if (p !== null && p > most) [worst, most] = [tone, p];
  }
  return worst;
}

/**
 * The tone the circuit clips soonest at (the softest pick anything clips at, then the
 * hardest push at a hard pick), when every tone is measured; else null.
 * @param {Map<number, Stages>} byTone @returns {number | null}
 */
export function worstTone(byTone) {
  if (TONES.some(([t]) => !byTone.has(t))) return null;
  /** @param {Stages} data */
  const rank = (data) => {
    const first = LEVELS.findIndex(([id]) => data.rows.some((r) => r.levels[id]?.clips));
    const most = Math.max(-Infinity, ...data.rows.map(push).filter((p) => p !== null));
    return [first < 0 ? LEVELS.length : first, -most];
  };
  let best = null;
  /** @type {number[] | null} */
  let bestRank = null;
  for (const [tone] of TONES) {
    const r = rank(/** @type {Stages} */ (byTone.get(tone)));
    if (!bestRank || r[0] < bestRank[0] || (r[0] === bestRank[0] && r[1] < bestRank[1])) [best, bestRank] = [tone, r];
  }
  return best;
}

/** A line saying the numbers may be off, or nothing when the runs settled (D-122). @param {Stages} data */
export function settledText(data) {
  if (data.settled === false) {
    return "Still settling after 0.4 s: a cap or a bias here is still moving, so these numbers are a little off.";
  }
  if (data.settled === null) {
    return "Not checked for settling: the circuit runs an oscillator of its own (a charge pump), too slow to check.";
  }
  return null;
}

/**
 * Where a chip goes on the chain: `{block: i}`, or `{arrow: k}` for the k-th arrow (0:
 * the one after the guitar; the last: the one into the amp, where a pot at the end goes).
 * @param {PotChip} pot @param {number} rows how many rows @returns {{block: number} | {arrow: number}}
 */
export function chipSpot(pot, rows) {
  if (pot.at === "block") return { block: pot.index };
  return { arrow: pot.at === "end" ? rows : pot.index + 1 };
}

/** Where a pot acts, in words, for its pop-up. @param {PotChip} pot @param {Row[]} rows */
export function potWhere(pot, rows) {
  if (pot.at === "block") return `On ${rows[pot.index]?.label}: it sets how much it amplifies, so how hard it clips.`;
  if (pot.at === "end" || pot.index >= rows.length - 1) return "After the last stage: it sets the level into the amp, not how anything clips.";
  const from = pot.index < 0 ? "the guitar" : rows[pot.index].label;
  return `Between ${from} and ${rows[pot.index + 1].label}: it sets what ${rows[pot.index + 1].label} gets.`;
}
