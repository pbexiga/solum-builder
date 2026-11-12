/**
 * The Bias & headroom pane (Phase 8c, D-106, D-122), DOM: the stage chain, one block per
 * stage and clipper in signal order with its kind of clipping, from `POST /api/stages`
 * at one of the test tones. Hover a block to light its parts on the schematic; a click
 * keeps them lit and opens its card (bias, the picks, each tone measured, Try changes;
 * its Waveform under the tones). The tone picked is measured on every change; another when it's picked, or all
 * of them on Measure all (D-122). It's 200 Hz when a circuit opens, and stays where it's
 * picked through shutting the pane or its large view (D-127). Its large view
 * (D-107, D-108) puts a chart beside it: the level diagram, or on request the level in →
 * out curve, measured a level at a time (`POST /api/stages/level`) at the tone picked;
 * hovering a block lights its place there. The explanations are behind the pane's ⓘ
 * (D-109). Try changes (D-119, D-123), in the large view: what centres or aims a stage's
 * bias, changes its gain, or swaps its diodes (`POST /api/stages/bias`, `/gain`,
 * `/clipper`), each option a Try. The first Try opens one edit session for any blocks;
 * Keep changes (one History step) or Discard changes in the top bar end it, a Changed
 * list says what's in, and the charts show the chain as it was, faint. Wording, colours
 * and plot data are `stages-logic.js`'s.
 */

import { postJson, postProgress } from "./api.js";
import { applyDiff, editDiff } from "./editor/edit.js";
import { curveChanges, noMarks } from "./layers.js";
import { h, infoButton, largeView, paneInfo, showKnob } from "./panels.js";
import { linePlot, setMarks } from "./plots.js";
import { addedChanges, arrangements, discreteParts, discreteText, clipMarks, gainSpots, nearestStep, stepOption, roomText, arrowLoss, biasAim, biasMark, blockMarks, blockRole, canCentre, cellText, changeText, chipSpot, clipperText, curveNets, fixLabel, fixTitle, LEVELS, levelCurve, levelDiagram, pickLines, PICK_STYLES, potWhere, biasScale, reachText, roleText, rowWorst, settledText, signedDb, startFields, SWEEP_LEVELS, TONES, toneName, triedOption, TRY_FIELDS, tryLabel, tryPatches, waveSeries, waveTable, worstTone } from "./stages-logic.js";

const NOTES = [
  "The chain: each stage and clipper in the order the signal meets them, measured with a sine at three picks (Soft 0.1 V, Medium 0.3 V, Hard 1 V peak at the guitar). "
    + "A block shows its own gain at the tone, and its marks (the key above). "
    + "An arrow's loss under 1 dB isn't shown; a tone stack can lose 15–20 dB.",
  "The tone: 200 Hz when a circuit opens. Pick 100 Hz, 1 kHz or 3 kHz, or Measure all; with all four in, the top line names the worst. "
    + "A change measures the tone picked again.",
  "Each run waits for the circuit to settle, like a pedal played for a moment; one still moving after 0.4 s says so.",
  "Hover a block to light its parts; click it to keep them lit and open its card.",
  "In the card: the bar is where a stage's output sits between its limits (an asterisk: an op-amp's rule-of-thumb swing). "
    + "Spare: how much louder it could get before it clips; over: how much room it lacks; held: diodes in its feedback stop it short. "
    + "A clipper shows where it clamps, and driven: how many dB it takes off.",
  "Waveform, under the tones, draws the picked block at each pick, as a scope does: the last two cycles of the tone (10 ms at 200 Hz), time across in milliseconds, volts to ground up, so the wave rides on its DC bias.",
  "Try changes, in the large view, has its own ⓘ.",
];
/** Try changes' ⓘ (D-127): what Centre, Bias to…, Gain, Find diodes, Try and Keep do. */
const TRY_NOTES = [
  "Centre, on a stage that sits high or low, looks for one resistor next to it that centres it, from a tenth to ten times its value, rounded to a standard (E24) value. "
    + "Drag the mark on its bar to aim the bias anywhere else (Bias to…): the same search, aimed there. A trimmer next to it comes first: turned, or given a target so it holds; "
    + "one that already has a target (a JFET's drain) gets a new one.",
  "Gain finds the parts next to a stage that move its own gain most (each tried 10 % up in ngspice). A resistor or pot gets a slider over its standard values from a tenth to ten times its own, "
    + "spread by the gain each gives; the marks (S, M, H) are where something in the chain starts clipping at a soft, medium or hard pick, and you can drag past them. "
    + "While you drag, each value says its gain and what clips first, estimated from the small-signal gain and each stage's room; letting go Tries it and measures it. "
    + "A slider stops before a value that would knock a stage out of its bias. A pot's slider changes its value (its range), not where it's turned. "
    + "A capacitor moves where the curve bends more than the drive: Edit curve opens on it. "
    + "Find diodes measures each kind (silicon, germanium, Schottky, red LED, and one LED for a lopsided pair) at a hard pick, "
    + "and arrangements that add parts: each diode doubled (two in series clamp higher: louder, less squashed), one side doubled (2 + 1, lopsided), "
    + "and on a clipper to ground a resistor in series (1k, 2k2, 4k7: a softer knee). An added part goes beside the diode, the wires moved to its far end. "
    + "Each says what else moves.",
  "Try puts an option in and measures again; another option in the same box takes its place. Try as many blocks as you like: "
    + "Changed lists everything in, ↺ puts one part back, and the charts show the chain as it was, faint (Before turns that off). "
    + "Keep changes leaves them in, as one step in History; Discard changes puts it all back as it was.",
];
/**
 * The chain's key, at the top of the pane's ⓘ (TODO 2026-11-09): a small block drawn as
 * the chain draws each look, with what it means.
 * @returns {HTMLElement}
 */
function chainKey() {
  /** @param {Record<string, string>} attrs @param {string} what */
  const row = (attrs, what, sample = "Q1") => h("div", { class: "key-row" }, [
    h("span", { class: "chain-block key-block", ...attrs }, [h("b", { class: "ref" }, [sample])]),
    h("span", {}, [what]),
  ]);
  const mark = (/** @type {string} */ tone, /** @type {string} */ text) => h("span", { class: `mark tone-${tone}` }, [text]);
  return h("div", { class: "chain-key", "data-chain-key": "" }, [
    row({ class: "chain-block key-block clips" }, "A solid bar on its left: it clips at a hard pick."),
    row({ "data-kind": "clipper" }, "A dashed outline: a clipper (diodes).", "D1"),
    row({ "aria-pressed": "true" }, "A copper outline: the block you picked; its card is below."),
    row({ class: "chain-block key-block discrete" }, "A double outline: a discrete op-amp, transistors working as one op-amp chip.", "Q2–Q4"),
    h("div", { class: "key-row" }, [h("span", { class: "key-marks" }, [mark("clip", "hard"), mark("ok", "soft")]),
      h("span", {}, ["A clipper's kind: hard (to ground), soft (in feedback) or in series; lit when it clips at a hard pick."])]),
    h("div", { class: "key-row" }, [h("span", { class: "key-marks" }, [mark("over", "clips"), mark("near", "lopsided")]),
      h("span", {}, ["A stage: clips, the device runs out of room at a hard pick; lopsided, its bias sits off centre, so one side clips first."])]),
    h("div", { class: "key-row" }, [h("span", { class: "key-marks" }, [h("b", { class: "key-arrow" }, ["−3 dB →"])]),
      h("span", {}, ["On an arrow: what the parts between two blocks do at the tone."])]),
  ]);
}
const DEFAULT_TONE = 200; // the tone picked when a circuit opens (D-127)
const SESSION = "Bias & headroom"; // Try changes' session, as History names it (as Edit curve's is "Frequency curve")
const CHARTS = /** @type {const} */ ([["diagram", "Level diagram"], ["curve", "Level in → out"]]);
const CHART_NOTES = {
  diagram: "The peak each pick reaches at each stage, along the signal path, in dBV (0 dBV is 1 V peak). "
    + "Dashed: what it would reach if that stage didn't clip. The dots are each stage's limit: where a line meets one, that stage clips. A clipper to ground's limit is where it clamps.",
  curve: "Each stage's peak as the guitar gets louder, both in dBV. The dashed line is the guitar itself. "
    + "Where a line bends flat, that stage is clipping: playing harder gets no louder there. "
    + `Measured at ${SWEEP_LEVELS.length} levels from 3 mV to 3 V; the three picks are marked.`,
};
const PLOT_RESERVED = 130; // px of the large view not the plot's: tools, legend
const KEEP_CURVES = 8; // circuits (at a tone) whose level in → out curve stays measured
const BUSY_AFTER_MS = 200; // measuring shows as busy only after this long (as the fade in app.css, D-281)

/**
 * @param {HTMLDetailsElement} panel the pane @param {HTMLElement} el its body
 * @typedef {{keep: (label: string) => void, discard: () => Promise<void>}} Session an edit session (`editSession` in app.js)
 * @param {{circuit: () => any, edited: () => any, highlight: (refs: string[], picked?: boolean) => void,
 *   begin: (name: string, owner: {pending: () => boolean, end: (how: "keep" | "discard") => unknown}) => Promise<Session | null>,
 *   setParts: (patches: import("./stages-logic.js").Patches, label: string, diffs?: {undo?: import("./editor/edit.js").EditDiff[], apply?: import("./editor/edit.js").EditDiff[], run?: boolean}) => Promise<string | null>,
 *   knob: (ref: string) => HTMLElement | null}} deps
 *   `circuit`: as measured (the knobs' turns in); `edited`: as edited (they're not changes);
 *   `begin`: Try changes' edit session (null if cancelled: another open one is asked about first, D-120); `setParts`: one
 *   edit setting these parts' values (and taking out and putting in parts added in series, and room made for them, D-124),
 *   then a re-run (not with `run` false: another edit follows); `knob`: a pot's control, as the Knobs & switches pane has it
 * @returns {{refresh: () => void, clear: (note?: string) => void, collapse: () => void,
 *   knobMoved: (control: any, value: number) => void}} `knobMoved`: a knob turned (here or in Knobs & switches)
 */
export function stagesPane(panel, el, deps) {
  let asked = 0; // the newest circuit measured: an older answer is dropped
  let stale = true; // the circuit changed while the pane was shut
  let measured = ""; // the circuit the chain is for: probing another point doesn't measure again
  /** @type {{key: string, byTone: Map<number, import("./stages-logic.js").Stages>} | null} the circuit shown, each tone measured */
  let shown = null;
  /** @type {import("./stages-logic.js").Stages | null} the rows last drawn, kept on screen while another tone is measured */
  let drawn = null;
  /** @type {Set<number>} tones being measured for `measured` now */
  const measuring = new Set();
  let tone = DEFAULT_TONE; // the tone picked
  /** @type {string | null} the block picked (its first ref): its parts lit, its card open */
  let picked = null;
  let ours = false; // the schematic's highlight is this pane's (a block or chip hovered)
  let oursPicked = false; // its picked layer is (a block or an arrow's chip picked, D-127)
  /** @type {string | null} a pot on an arrow whose card is open (D-123: the card holds one thing, a block or this) */
  let pickedPot = null;
  let knobsShown = ""; // the pots whose controls are in `potPop` now
  /** @type {"diagram" | "curve"} */
  let chart = "diagram";
  let sweeping = 0; // the newest level in → out sweep: an older one stops
  let running = ""; // the circuit and tone being swept now, and its levels so far
  /** @type {import("./stages-logic.js").LevelPoint[]} */
  let partial = [];
  /** @type {Map<string, import("./stages-logic.js").LevelPoint[]>} circuit and tone → its whole curve */
  const curves = new Map();
  /**
   * The fix open in a block's card (D-119, D-123): Centre or Bias to… (`aim`, null to
   * centre), the gain parts' sliders (D-125), or diode swaps; its options (null while looking).
   * @type {{kind: "bias" | "gain" | "clipper", ref: string, title: string, aim: number | null,
   *   options: import("./stages-logic.js").FixOption[] | null, parts: import("./stages-logic.js").GainPart[], note: string, error: string,
   *   into?: string, busy: boolean, step: {done: number, of: number} | null} | null} `step`: the search's progress
   */
  let fix = null;
  /**
   * Try changes' edit session (D-123), opened by the first Try and ended by Keep changes or
   * Discard changes: the circuit as edited when it began, and as measured then (its key,
   * each tone's chain and level in → out curve), drawn faint and put back by Discard.
   * `added`: the parts an arrangement put in (D-124), each to what put it in (and the room made for it), so ↺ takes them all out.
   * @type {{session: Session, circuit: any, key: string, byTone: Map<number, import("./stages-logic.js").Stages> | null,
   *   curves: Map<number, import("./stages-logic.js").LevelPoint[]>, added: Map<string, import("./stages-logic.js").FixOption>} | null}
   */
  let edit = null;
  let beforeOn = true; // the faint "before" lines on the charts
  /** @type {Map<string, {lo: number, hi: number, aimable: boolean, why: string | null} | "asking">} how far Bias to… can move each stage, by circuit and ref (D-123) */
  const reaches = new Map();
  let aiming = false; // a bias mark is being dragged: the card isn't drawn again under it


  const chartButtons = CHARTS.map(([id, label]) => {
    const b = h("button", { type: "button", role: "radio", "data-stages-chart": id, "aria-checked": String(id === chart) }, [label]);
    b.addEventListener("click", () => {
      chart = id;
      for (const o of chartButtons) o.setAttribute("aria-checked", String(o === b));
      draw();
    });
    return b;
  });
  const charts = h("span", { class: "segmented", role: "radiogroup", "aria-label": "Chart" }, chartButtons);
  // while Try changes is open: Before, then Discard / Keep
  const beforeButton = h("button", { type: "button", id: "stages-before", "aria-pressed": "true", hidden: "", title: "The chain as it was when Try changes began, faint" }, ["Before"]);
  beforeButton.addEventListener("click", () => {
    beforeOn = !beforeOn;
    beforeButton.setAttribute("aria-pressed", String(beforeOn));
    draw();
  });
  const discardButton = h("button", { type: "button", id: "stages-discard", hidden: "", title: "Put back every part changed since the first Try" }, ["Discard changes"]);
  const keepButton = h("button", { type: "button", id: "stages-keep", class: "primary", hidden: "", title: "Leave the changes in, as one step in History" }, ["Keep changes"]);
  discardButton.addEventListener("click", () => void end("discard"));
  keepButton.addEventListener("click", () => void end("keep"));
  const editTools = h("span", { class: "edit-tools" }, [beforeButton, discardButton, keepButton]);
  const tools = h("div", { class: "panel-tools", id: "stages-tools" }, [charts, editTools]);
  const plot = h("div", { class: "plot", id: "stages-plot" });
  // the level in → out sweep's progress: a line and a bar filling a level at a time (D-123)
  const progressText = h("span");
  const progressBar = /** @type {HTMLProgressElement} */ (h("progress", { max: String(SWEEP_LEVELS.length), value: "0" }));
  const progress = h("p", { class: "hint", id: "stages-progress" }, [progressText, progressBar]);
  // the chain over the chart in the large view (D-122): a block over each stage's column
  const strip = h("div", { class: "stage-strip", id: "stage-strip" });
  const main = h("div", { class: "stages-main", id: "stages-main" }, [strip, plot, progress]);

  const toneButtons = TONES.map(([t, name]) => {
    const b = h("button", { type: "button", role: "radio", "data-tone": String(t), "aria-checked": String(t === tone) }, [name]);
    b.addEventListener("click", () => pickTone(t));
    return b;
  });
  const measureAll = h("button", { type: "button", id: "stages-measure-all", title: "Measure the other tones too" }, ["Measure all"]);
  measureAll.addEventListener("click", () => void measureRest());
  // right of the chips, centred in the room left (round 3): what to do, or all done; while a
  // tone is measured, a bar in its place for how far it's got (the small-signal pass, then each pick)
  const toneNote = h("span", { class: "hint", id: "stages-tone-note" });
  const toneBar = /** @type {HTMLProgressElement} */ (h("progress", { class: "tone-progress", id: "stages-tone-progress", hidden: "" }));
  /** @type {ReturnType<typeof setTimeout> | undefined} the bar is due to show (`showBusy`) */
  let busyTimer;
  const tonesBar = h("div", { class: "stage-tones", id: "stage-tones" }, [
    h("span", { class: "segmented", role: "radiogroup", "aria-label": "Test tone" }, toneButtons),
    measureAll,
    h("span", { class: "tone-state" }, [toneNote, toneBar]),
  ]);
  /** @type {Map<number, {done: number, of: number}>} each tone being measured: its steps so far */
  const toneSteps = new Map();
  /** the picked block's Waveform section, under the tones (D-127) */
  const waveSlot = h("div", { id: "stages-wave-slot" });
  const body = h("div", { id: "stages-chain-body" });
  // the card (D-123): what it is at the top, the knobs of its pots, then the rest; the
  // knobs are kept when the rest is drawn again, so measuring again doesn't take a
  // control from under the pointer or the keyboard
  const cardTop = h("div", { class: "card-part" });
  const potPop = h("div", { class: "pot-pop", id: "pot-pop", hidden: "" });
  const cardRest = h("div", { class: "card-part" });
  const cardBody = h("div", { class: "stage-card-box", id: "stages-card-body", hidden: "" }, [cardTop, potPop, cardRest]);
  const changesBox = h("div", { class: "curve-changes-box", id: "try-changed", hidden: "" });
  /** Waveform starts open on every card (D-127) and stays shut once the user shuts it, until reopened or another circuit */
  let wavesShut = false;
  /** its readings (peaks, clipping, THD) start folded, and stay as the user leaves them (round 3b) */
  let readingsOpen = false;
  /** one plot, moved from card to card, so switching cards doesn't empty it for a moment (round 3b) */
  const wavePlot = h("div", { class: "plot stages-wave-plot", id: "stages-wave-plot" });
  /** @type {Map<string, {time_ms: number[], waves: Record<string, number[]>}>} tone, net and circuit → its waveforms */
  const waves = new Map();
  const side = h("div", { class: "stages-side large-side", id: "stages-side" }, [changesBox, tonesBar, waveSlot, body, cardBody]);
  el.replaceChildren(tools, main, side);

  const view = largeView(panel, {
    id: "stages-expand",
    name: "stages",
    what: "A large view of the levels along the signal path, over the canvas",
    tools,
    onChange: (on) => {
      if (!on) stopSweep(); // a sweep nobody can see stops
      if (!on && edit) void end("keep"); // nothing changed (Collapse waits for Keep or Discard otherwise)
      laidOut();
      show(); // Centre's button is the large view's
    },
    onShow: () => draw(),
  });
  paneInfo(panel, "Bias & headroom", () => [
    chainKey(),
    ...NOTES,
    ...(view.expanded() ? [h("h5", {}, [CHARTS.find(([id]) => id === chart)?.[1] ?? ""]), CHART_NOTES[chart]] : []),
  ]);
  const tryInfo = infoButton("Try changes", () => TRY_NOTES); // made once, put back in each Try changes box drawn
  /** @type {Map<string, {style: string, label: string}>} each net's line on the level in → out curve (`curveNets`), for the strip's colours */
  let lines = new Map();
  /** @type {Set<string>} the curve's lines hidden in its legend: their blocks fade (round 2); kept across redraws, cleared with the circuit */
  const hiddenLines = new Set();
  /** the block hovered: its place lit on the chart */
  let lit = /** @type {import("./stages-logic.js").Row | null} */ (null);
  laidOut();
  showTones();
  panel.addEventListener("toggle", () => {
    if (!panel.open) return;
    if (stale) void refresh();
  });

  function laidOut() {
    const on = view.expanded();
    tools.hidden = !on; // the charts and Collapse: nothing to show in the panel
    main.hidden = !on;
    draw();
  }

  /** The rows shown: the tone picked, once measured. */
  function data() {
    return shown?.byTone.get(tone) ?? null;
  }

  /** What's drawn: the tone picked, or while it's measured the last one drawn (faded). */
  function current() {
    const d = data();
    if (d) return (drawn = d);
    return el.dataset.loading ? drawn : null;
  }

  /** Measure again (only while the pane is open; on opening otherwise): the tone picked. */
  async function refresh() {
    const circuit = deps.circuit();
    if (!circuit) return clear();
    if (!panel.open) return void (stale = true);
    const key = JSON.stringify(circuit);
    if (key === measured && !stale) return;
    if (fix && !edit && measured && key !== measured) fix = null; // the circuit changed under its options
    stale = false;
    measured = key;
    asked++;
    waves.clear(); // the last circuit's
    measuring.clear();
    toneSteps.clear();
    if (!shown) body.replaceChildren(h("p", { class: "hint" }, ["Measuring each stage at three picks…"]));
    if (!(shown?.key === key && shown.byTone.has(tone))) el.dataset.loading = "true";
    await measure(tone);
  }

  /** Measure the circuit at `t` (once per circuit), then show it if it's still wanted. @param {number} t */
  async function measure(t) {
    const key = measured;
    if (!key || measuring.has(t) || (shown?.key === key && shown.byTone.has(t))) return;
    const mine = asked;
    measuring.add(t);
    showTones();
    try {
      const got = await postProgress("api/stages", { circuit: JSON.parse(key), tone: t }, (done, of) => {
        if (mine !== asked) return;
        toneSteps.set(t, { done, of });
        showTones();
      });
      if (mine !== asked) return;
      if (shown?.key !== key) shown = { key, byTone: new Map() };
      shown.byTone.set(t, got);
      if (t === tone) delete el.dataset.loading;
      show();
    } catch (err) {
      if (mine !== asked) return;
      if (t === tone) {
        delete el.dataset.loading;
        measured = "";
        body.replaceChildren(h("p", { class: "warning" }, [/** @type {Error} */ (err).message]));
      }
    } finally {
      toneSteps.delete(t);
      if (mine === asked) measuring.delete(t);
      if (mine === asked) showTones();
    }
  }

  /** Measure every tone not measured yet, one at a time (a change stops it: `asked`). */
  async function measureRest() {
    const mine = asked;
    for (const [t] of TONES) {
      if (mine !== asked) return;
      await measure(t);
    }
  }

  /** Show tone `t`: measured at once if it isn't yet. @param {number} t */
  function pickTone(t) {
    toTone(t);
    if (shown && !shown.byTone.has(t) && measured) el.dataset.loading = "true";
    show();
    void measure(t);
  }

  /** @param {number} t */
  function toTone(t) {
    tone = t;
    for (const b of toneButtons) b.setAttribute("aria-checked", String(Number(b.dataset.tone) === t));
  }

  /** The tone picker's state: each tone measured or not, Measure all, and a line saying where things are. */
  function showTones() {
    const have = shown?.key === measured ? shown.byTone : new Map();
    for (const b of toneButtons) {
      const t = Number(b.dataset.tone);
      b.classList.toggle("unmeasured", !have.has(t));
      b.title = have.has(t) ? `Measured at ${toneName(t)}` : measuring.has(t) ? `Measuring ${toneName(t)}…` : `Measure at ${toneName(t)}`;
    }
    const missing = TONES.filter(([t]) => !have.has(t));
    measureAll.hidden = !missing.length || !measured;
    measureAll.disabled = measuring.size > 0;
    const busy = [...measuring].map(toneName);
    const at = measuring.has(tone) ? tone : [...measuring][0];
    const step = at === undefined ? undefined : toneSteps.get(at);
    showBusy(at !== undefined && !!measured);
    if (step) Object.assign(toneBar, { max: step.of, value: step.done });
    else toneBar.removeAttribute("value"); // started, no step yet: a bar that only says it's busy
    toneBar.title = busy.length ? `Measuring ${busy.join(", ")}…` : "";
    toneBar.setAttribute("aria-label", toneBar.title);
    toneNote.textContent = !measured ? "" : missing.length ? "Click a tone to measure it." : "Measured at every tone.";
  }

  /**
   * The progress bar in the note's place while a tone is measured, but only once that
   * has gone on for `BUSY_AFTER_MS`: an answer that comes straight back (a part moved,
   * the circuit electrically the same and its runs kept) left the pane a line shorter for
   * a frame or two, and everything under it jumped (the user, 2026-11-11, D-281).
   * @param {boolean} busy
   */
  function showBusy(busy) {
    if (!busy) {
      clearTimeout(busyTimer);
      busyTimer = undefined;
      toneBar.hidden = true;
      toneNote.hidden = false;
    } else if (toneBar.hidden && busyTimer === undefined) {
      busyTimer = setTimeout(() => {
        busyTimer = undefined;
        toneBar.hidden = false;
        toneNote.hidden = true;
      }, BUSY_AFTER_MS);
    }
  }

  /** @param {string} [note] */
  function clear(note = "") {
    asked++;
    measured = "";
    shown = null;
    drawn = null;
    measuring.clear();
    toneSteps.clear();
    toTone(DEFAULT_TONE); // another circuit (or none) starts at 200 Hz
    hiddenLines.clear();
    fix = null;
    edit = null; // another circuit: its session went with the undo list
    reaches.clear();
    picked = null;
    pickedPot = null;
    wavesShut = false;
    lightParts([]);
    showCard(null, null);
    delete el.dataset.loading;
    body.replaceChildren(...(note ? [h("p", { class: "hint" }, [note])] : []));
    showTones();
    draw();
  }

  /**
   * Look for a fix for block `r` (in the large view, where the fixes live, D-122): what
   * centres it or moves its bias to `aim`, the parts that set its gain (a slider each,
   * D-125), or other diodes. One box at a time; what it tried stays in when another
   * opens (D-123).
   * @param {"bias" | "gain" | "clipper"} kind @param {import("./stages-logic.js").Row} r
   * @param {{aim?: number | null}} [ask]
   */
  async function startFix(kind, r, { aim = null } = {}) {
    const circuit = deps.circuit();
    if (!circuit) return;
    if (!view.expanded()) view.set(true);
    const ref = r.refs[0];
    const mine = (fix = { kind, ref, title: fixTitle(kind, r, aim), aim, options: null, parts: [], note: "", error: "", busy: false, step: null });
    show();
    // a clipper's arrangements are placed here (the router is the browser's) and measured with the swaps (D-124)
    // first making room where there's none beside a diode (D-124): a step of its own, said before and after
    const edited = deps.edited();
    const placed = kind === "clipper" ? arrangements(edited, r) : { arranged: [], missed: [] };
    const diffs = new Map(placed.arranged.map((a) => {
      const room = a.room ? editDiff(edited, a.room.circuit) : undefined;
      return [a.key, { add: editDiff(a.room?.circuit ?? edited, a.circuit), room, roomText: a.room ? roomText(a.room, r.refs) : undefined, moved: a.room?.moved }];
    }));
    const arranged = placed.arranged.map((a) => {
      const d = /** @type {any} */ (diffs.get(a.key));
      const room = d.room ? applyDiff(circuit, d.room) : null;
      return { key: a.key, series: a.series, circuit: applyDiff(room ?? circuit, d.add), room };
    });
    const [url, body] = kind === "bias" ? ["api/stages/bias", { circuit, ref, target: aim }]
      : kind === "gain" ? ["api/stages/gain", { circuit, ref }]
      : ["api/stages/clipper", { circuit, ref, arranged }];
    try {
      const got = await postProgress(url, body, (done, of) => {
        if (fix !== mine) return;
        mine.step = { done, of };
        const bar = /** @type {HTMLProgressElement | null} */ (el.querySelector("#fix-progress"));
        if (bar) Object.assign(bar, { max: of, value: done }); // the box isn't drawn again for a step
      });
      if (fix !== mine) return;
      mine.options = got.options.map((/** @type {import("./stages-logic.js").FixOption} */ o) => {
        const d = o.key ? diffs.get(o.key) : null;
        if (!d) return o;
        return { ...o, ...d };
      });
      mine.parts = got.parts ?? [];
      mine.into = got.into; // what the sliders measure into: the next block, or the output (D-223)
      // a slider's every value is an option (D-125), so Trying and Changed work as for the rest
      if (kind === "gain") mine.options = mine.parts.flatMap((p) => p.steps.filter((st) => !st.now).map((st) => stepOption(p, st)));
      const missed = placed.missed.length ? `There isn't room to add parts beside ${placed.missed.join(", ")}, so some arrangements aren't offered: make some space around them on the sheet and try again.` : "";
      mine.note = [got.note ?? "", missed].filter(Boolean).join(" ");
    } catch (err) {
      if (fix !== mine) return;
      mine.options = [];
      mine.error = /** @type {Error} */ (err).message;
    }
    show();
  }

  /**
   * Put `option` in, and this box's option in before back as it was when the session
   * began: the first Try opens Try changes' session (D-123).
   * @param {import("./stages-logic.js").FixOption} option
   */
  async function tryOption(option) {
    const f = fix;
    if (!f || f.busy || triedOption(f.options ?? [], deps.edited()) === option) return;
    f.busy = true;
    show();
    if (!edit) {
      const at = { circuit: deps.edited(), key: measured, byTone: shown?.key === measured ? shown.byTone : null, curves: startCurves(), added: new Map() };
      const session = await deps.begin(SESSION, { pending: () => changes().length > 0, end: (how) => end(how) });
      if (session) edit = { session, ...at };
    }
    if (!edit) {
      f.busy = false; // cancelled: Edit curve stays open
      return show();
    }
    const tried = triedOption(f.options ?? [], deps.edited());
    const out = tried?.add && tried !== option ? tried : null;
    const undo = out ? takeOut(out) : [];
    let message = null;
    // room made first is a History step of its own (D-124): "Made room for D3, D4: moved …"
    if (option.room) {
      const refs = option.add?.parts.map((p) => p.ref).join(", ");
      message = await deps.setParts({}, `Made room for ${refs}: moved ${option.roomText}`, { undo, apply: [option.room], run: false });
    }
    if (!message) {
      message = await deps.setParts(tryPatches(tried, option, edit.circuit), fixLabel(f.title, option), {
        undo: option.room ? [] : undo,
        apply: option.add ? [option.add] : [],
      });
      // the parts didn't go in: the room made for them comes out again, nothing left moved
      if (message && option.room) await deps.setParts({}, "Put back what moved to make room", { undo: [option.room] });
    }
    if (!message && edit) {
      for (const p of out?.add?.parts ?? []) edit.added.delete(p.ref);
      for (const p of option.add?.parts ?? []) edit.added.set(p.ref, option);
    }
    f.busy = false;
    f.error = message ?? "";
    show();
  }

  /** This circuit's level in → out curves, by tone: Try changes' before (D-123). */
  function startCurves() {
    return new Map(TONES.flatMap(([t]) => {
      const points = curves.get(`${t} ${measured}`);
      return points ? [[t, points]] : [];
    }));
  }

  /** What an arrangement put in, to take out (its parts, then the room made for them). @param {import("./stages-logic.js").FixOption} o */
  function takeOut(o) {
    return /** @type {import("./editor/edit.js").EditDiff[]} */ ([o.add, o.room].filter(Boolean));
  }

  /**
   * What Try changes has changed so far (D-123): values, and the parts arrangements added,
   * each after a line for the room made for them (D-124).
   * @returns {Array<{ref: string, field: string, from: string, to: string, refs?: string[]}>}
   */
  function changes() {
    if (!edit) return [];
    const rooms = [...new Set(edit.added.values())].filter((o) => o.room && o.add?.parts.length).map((o) => ({
      ref: /** @type {any} */ (o.add).parts[0].ref, field: "room", from: "", to: o.roomText ?? "", refs: o.moved ?? [],
    }));
    return [...curveChanges(edit.circuit, deps.edited(), TRY_FIELDS), ...rooms, ...addedChanges(edit.circuit, deps.edited())];
  }

  /**
   * End Try changes (D-123): Keep leaves the changes in as one History step; Discard puts
   * the circuit back, and the chain as it was measured then, so nothing is measured again.
   * @param {"keep" | "discard"} how
   */
  function end(how) {
    const e = edit;
    if (!e) return;
    const label = tryLabel(changes());
    edit = null;
    fix = null;
    if (how === "keep") {
      e.session.keep(label);
      return show();
    }
    if (e.byTone) {
      asked++; // a measurement on its way is for a circuit that's gone
      measuring.clear();
      toneSteps.clear();
      measured = e.key;
      shown = { key: e.key, byTone: e.byTone };
      stale = false;
      delete el.dataset.loading;
    }
    show();
    return e.session.discard();
  }

  /** Close the fix box; what it tried stays in Try changes. */
  function close() {
    fix = null;
    show();
  }

  /**
   * How far Bias to… can move stage `r` (D-123): known, or null while it's asked for
   * (once per circuit; the card is drawn again when it comes).
   * @param {import("./stages-logic.js").Row} r
   */
  function reachOf(r) {
    const key = `${measured}\n${r.refs[0]}`;
    const known = reaches.get(key);
    if (known === "asking") return null;
    if (known) return known;
    const circuit = deps.circuit();
    if (!measured || !circuit) return null;
    reaches.set(key, "asking");
    postJson("api/stages/reach", { circuit, ref: r.refs[0] })
      .then((got) => {
        reaches.set(key, { lo: got.lo, hi: got.hi, aimable: got.aimable, why: got.why });
        if (key.startsWith(`${measured}\n`) && !aiming) show(); // a drag's letting go draws it
      })
      .catch(() => reaches.delete(key)); // no limits drawn: the search says what it finds
    if (reaches.size > 64) reaches.delete(/** @type {string} */ (reaches.keys().next().value));
    return null;
  }

  /**
   * Put part `ref` back as it was when Try changes began (a diode's type with its model);
   * a part an arrangement added comes out, with the others it put in (D-124).
   * @param {string} ref
   */
  async function putBack(ref) {
    if (!edit) return;
    const option = edit.added.get(ref);
    const refs = option?.add?.parts.map((p) => p.ref) ?? [];
    const message = option
      ? await deps.setParts({}, `Take out ${refs.join(", ")}${option.room ? " and the room made for them" : ""}`, { undo: takeOut(option) })
      : await deps.setParts({ [ref]: startFields(edit.circuit, ref, [...TRY_FIELDS, "type"]) }, `Put back ${ref}`);
    if (!message) for (const r of refs) edit?.added.delete(r);
    if (message && fix) fix.error = message;
    show();
  }

  /** The top bar and the Changed list while Try changes is open (D-123). */
  function showEdit() {
    const list = changes();
    for (const b of [beforeButton, discardButton, keepButton]) b.hidden = !edit;
    keepButton.textContent = list.length ? "Keep changes" : "Done";
    view.lock(list.length ? "Keep or discard your Try changes first" : null);
    changesBox.hidden = !edit || !view.expanded();
    if (changesBox.hidden) return void changesBox.replaceChildren();
    changesBox.replaceChildren(
      h("h4", {}, ["Changed"]),
      list.length
        ? h("ul", { class: "curve-changes", id: "try-changes-list" }, list.map((c) => {
          const title = c.field === "added" ? `Take ${c.ref} out` : c.field === "room" ? "Take out the parts and put the moved ones back" : `Put ${c.ref} back to ${c.from}`;
          const back = h("button", { type: "button", class: "link put-back", title }, ["\u21ba"]);
          back.addEventListener("click", () => void putBack(c.ref));
          const li = h("li", { "data-ref": c.ref, ...(c.field === "room" ? { class: "room-made" } : {}) }, [`${changeText(c)} `, back]);
          li.addEventListener("pointerenter", () => lightParts(c.refs ?? [c.ref])); // the room's line lights what moved
          li.addEventListener("pointerleave", () => lightParts([]));
          return li;
        }))
        : h("p", { class: "curve-changes", id: "try-changes-list" }, ["Nothing changed now."]),
    );
  }

  /** A fix's box in its block's card: its options, each with Try (Trying while it's in), then Close. @param {NonNullable<typeof fix>} f */
  function fixBox(f) {
    /** @type {HTMLElement[]} */
    const items = [];
    const looking = {
      bias: f.aim === null ? `Looking for what centres ${f.ref}…` : `Looking for what puts ${f.ref} there…`,
      gain: `Looking for the parts that set ${f.ref}'s gain, and trying each one's values…`,
      clipper: "Trying each kind of diode and arrangement…",
    };
    if (!f.options) {
      items.push(h("p", { class: "hint" }, [looking[f.kind]]),
        h("progress", { class: "fix-progress", id: "fix-progress", ...(f.step ? { max: String(f.step.of), value: String(f.step.done) } : {}) }));
    }
    if (f.parts.length) {
      items.push(h("p", { class: "fix-parts-head" }, ["What moves its gain most, a slider each:"]),
        h("div", { class: "fix-parts" }, f.parts.map((p) => gainPart(f, p))));
    }
    if (f.note) items.push(h("p", { class: "hint", id: "fix-note" }, [f.note]));
    else if (f.options && !f.options.length && !f.error) items.push(h("p", { class: "hint" }, ["Nothing found."]));
    const tried = edit ? triedOption(f.options ?? [], deps.edited()) : null;
    for (const o of f.kind === "gain" ? [] : f.options ?? []) {
      const on = o === tried;
      const tryButton = h("button", { type: "button", "data-try": o.label, "aria-pressed": String(on), ...(f.busy ? { disabled: "" } : {}) }, [on ? "Trying" : "Try"]);
      tryButton.addEventListener("click", () => void tryOption(o));
      const room = o.roomText ? [" ", h("span", { class: "room-note", title: "Everything past a line through the diode's pin moves out, wires stretched: undo or ↺ puts it back" }, [`Makes room first: moves ${o.roomText}.`])] : [];
      items.push(h("div", { class: "fix-option", "data-option": o.label }, [h("span", {}, [o.text, ...room]), tryButton]));
    }
    if (f.error) items.push(h("p", { class: "warning" }, [f.error]));
    const closeButton = h("button", { type: "button", id: "fix-close", title: "Close this box: what it tried stays in until Keep or Discard changes" }, ["Close"]);
    closeButton.addEventListener("click", close);
    return h("div", { class: "fix-box", id: "fix-box", "data-fix": f.kind }, [h("p", { class: "fix-title" }, [f.title]), ...items, h("div", { class: "fix-buttons" }, [closeButton])]);
  }

  /**
   * One part in the gain box (D-125). A resistor or pot: a slider over its values from a
   * tenth to ten times, placed by the gain each gives, with marks where something starts
   * clipping at each pick; dragging reads each value (estimated, instantly), letting go
   * Tries it. A capacitor: what it does, and Edit curve opened on it.
   * @param {NonNullable<typeof fix>} f @param {import("./stages-logic.js").GainPart} p
   */
  function gainPart(f, p) {
    if (!p.steps.length) {
      const open = h("button", { type: "button", class: "edit-curve-part", "data-edit-curve": p.ref, title: `Opens Edit curve with ${p.ref}'s slider, where you see what it does to the curve` }, ["Edit curve"]);
      open.addEventListener("click", () => deps.editCurve(p.ref));
      return h("div", { class: "gain-part gain-cap", "data-part": p.ref }, [h("span", {}, [p.text]), open]);
    }
    const steps = p.steps;
    const spots = gainSpots(steps);
    const inNow = deps.edited()?.parts.find((/** @type {any} */ q) => q.ref === p.ref)?.value;
    let at = steps.findIndex((st) => st.value === inNow);
    if (at < 0) at = steps.findIndex((st) => st.now);
    const knob = h("i", { class: "gain-knob", style: `left: ${spots[at] * 100}%` });
    const was = h("i", { class: "gain-was", title: `${p.ref} ${p.value}, as it was when you opened this`, style: `left: ${spots[Math.max(0, steps.findIndex((st) => st.now))] * 100}%` });
    const found = clipMarks(steps);
    // each mark, and the stretch of the bar past it where that pick clips, tinted (D-127)
    const zones = found.map((m) => h("s", { class: `clip-zone clip-${m.level}`, style: m.up ? `left: ${m.at * 100}%; right: 0` : `left: 0; right: ${(1 - m.at) * 100}%`, title: m.title }));
    const marks = found.map((m) => h("b", { class: `clip-mark clip-${m.level}${m.up ? " up" : ""}`, style: `left: ${m.at * 100}%`, title: m.title }, [m.name[0]]));
    const live = !f.busy;
    const bar = h("span", { class: `gain-bar${live ? "" : " busy"}`, role: "slider", tabindex: "0", "aria-label": `${p.ref}'s value`,
      "aria-valuemin": "0", "aria-valuemax": String(steps.length - 1), "aria-valuenow": String(at), "aria-valuetext": steps[at].value }, [...zones, ...marks, was, knob]);
    const value = h("b", { class: "gain-value" }, [steps[at].value]);
    const line = h("span", { class: "gain-text" }, [steps[at].text]);
    const chain = h("span", { class: "gain-chain", title: "Estimated from the small-signal gain and each stage's room; letting go measures it" }, [steps[at].chain]);
    const read = (/** @type {number} */ i) => {
      at = Math.min(Math.max(i, 0), steps.length - 1);
      knob.style.left = `${spots[at] * 100}%`;
      bar.setAttribute("aria-valuenow", String(at));
      bar.setAttribute("aria-valuetext", steps[at].value);
      value.textContent = steps[at].value;
      line.textContent = steps[at].text;
      chain.textContent = steps[at].chain;
    };
    const go = () => {
      if (steps[at].value === inNow) return;
      const option = steps[at].now ? stepOption(p, steps[at]) : f.options?.find((o) => o.set[p.ref]?.value === steps[at].value);
      if (option) void tryOption(option);
    };
    const from = (/** @type {PointerEvent} */ e) => {
      const box = bar.getBoundingClientRect();
      return nearestStep(spots, (e.clientX - box.left) / box.width);
    };
    let dragging = false;
    bar.addEventListener("pointerdown", (e) => {
      if (!live || el.dataset.loading) return; // trying one, or the chain is being measured
      dragging = aiming = true;
      bar.setPointerCapture(e.pointerId);
      read(from(e));
    });
    bar.addEventListener("pointermove", (e) => dragging && read(from(e)));
    bar.addEventListener("pointercancel", () => void (dragging = aiming = false));
    bar.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = aiming = false;
      go();
    });
    bar.addEventListener("keydown", (e) => {
      if (!live) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowDown") read(at - 1);
      else if (e.key === "ArrowRight" || e.key === "ArrowUp") read(at + 1);
      else if (e.key === "Enter" && !el.dataset.loading) go();
      else return;
      e.preventDefault();
    });
    const ends = h("span", { class: "gain-ends" }, [h("span", {}, [signedDb(steps[0].gain_db)]), h("span", { title: `What reaches ${f.into ?? "the next block"}: the slider runs from the least to the most` }, [f.into ? `into ${f.into}` : "gain"]), h("span", {}, [signedDb(steps.at(-1)?.gain_db ?? 0)])]);
    return h("div", { class: "gain-part", "data-part": p.ref }, [
      h("div", { class: "gain-head" }, [h("span", {}, [p.ref]), value]),
      h("span", { class: "gain-scaled" }, [bar, ends]),
      h("p", { class: "gain-read" }, [line, " ", chain]),
      ...(p.note ? [h("p", { class: "hint gain-note" }, [p.note])] : []),
    ]);
  }

  /**
   * A block's Try changes (D-123), in the large view: Centre (and Bias to…, by dragging
   * the bar's mark) and a gain change for a stage; diode swaps for a clipper. In the
   * panel, one button that opens the large view.
   * @param {import("./stages-logic.js").Row} r
   */
  function tryChanges(r) {
    if (!view.expanded()) {
      const b = h("button", { type: "button", class: "try-changes", title: "Opens the large view, where the changes are" }, ["Try changes…"]);
      b.addEventListener("click", () => view.set(true));
      return [h("div", { class: "card-buttons" }, [b])];
    }
    /** @type {HTMLElement[]} */
    const lines = [];
    if (r.kind === "stage") {
      const centre = h("button", { type: "button", class: "centre-button", "data-centre": r.refs[0] }, ["Centre"]);
      centre.addEventListener("click", () => void startFix("bias", r));
      const aimable = !!r.bias && !!biasAim(r.bias, 0.5);
      const reach = aimable ? reachText(reachOf(r)) : null;
      lines.push(h("div", { class: "try-line", "data-try-line": "bias" }, [
        h("b", {}, ["Bias"]),
        ...(canCentre(r) ? [centre] : []),
        h("span", { class: "hint", id: "bias-reach" }, [!aimable ? "Its room has no limit one way, so it can't be aimed." : reach?.text ?? "Drag the mark on its bar to aim it."]),
      ]));
      const find = h("button", { type: "button", id: "gain-find" }, ["Find parts"]);
      find.addEventListener("click", () => void startFix("gain", r));
      lines.push(h("div", { class: "try-line", "data-try-line": "gain" }, [h("b", {}, ["Gain"]), find,
        h("span", { class: "hint" }, ["A slider for each part that sets it, with what clips first at each value."])]));
    } else {
      const swap = h("button", { type: "button", id: "diode-find" }, ["Find diodes"]);
      swap.addEventListener("click", () => void startFix("clipper", r));
      lines.push(h("div", { class: "try-line", "data-try-line": "clipper" }, [h("b", {}, ["Diodes"]), swap, h("span", { class: "hint" }, ["Each kind, and two in series, 2 + 1", ...(r.role === "to ground" ? [", a resistor in series"] : []), ", measured at a hard pick."])]));
    }
    return [h("div", { class: "try-changes-box", id: "try-changes" }, [h("p", { class: "try-head" }, ["Try changes", tryInfo.button]), ...lines])];
  }

  /** Draw the chain and the card for the tone picked, as things are now. */
  function show() {
    lit = null;
    lightParts([]); // the block hovered is drawn again: it won't say it's left
    showTones();
    showEdit();
    const d = current(); // the tone picked, or the last one, faded, while it's measured
    if (!shown || !d) return draw();
    if (!d.rows.length) {
      picked = pickedPot = null;
      showCard(null, null);
      body.replaceChildren(h("p", { class: "hint" }, [d.note ?? ""]));
      return draw();
    }
    const row = d.rows.find((r) => r.refs[0] === picked) ?? null;
    if (!row) picked = null;
    const pot = d.pots.find((p) => p.ref === pickedPot && "arrow" in chipSpot(p, d.rows.length)) ?? null;
    if (!pot) pickedPot = null;
    const worst = worstTone(shown.byTone);
    const summary = [d.summary];
    if (worst !== null && worst !== tone) summary.push(`Worst at ${toneName(worst)}: ${shown.byTone.get(worst)?.summary.replace(/^Clips first: /, "")}`);
    else if (worst !== null) summary.push(`${toneName(tone)} is the worst tone.`);
    const settled = settledText(d);
    body.replaceChildren(
      h("p", { class: "stages-summary", id: "stages-summary" }, [summary.join(" ")]),
      ...(settled ? [h("p", { class: "warning", id: "stages-settling" }, [settled])] : []),
      chain(d, "stage-chain"),
    );
    strip.replaceChildren(...(view.expanded() ? [chain(d, "stage-strip-chain")] : []));
    showCard(row ? { row, i: d.rows.indexOf(row) } : null, pot ? { pot, d } : null);
    draw();
  }

  /**
   * The card: a block's (what it is, the knobs of its pots, its picks and fixes), or a
   * pot's on an arrow (where it acts, its knob), or nothing. Lights what it's about.
   * @param {{row: import("./stages-logic.js").Row, i: number} | null} b
   * @param {{pot: import("./stages-logic.js").PotChip, d: import("./stages-logic.js").Stages} | null} a
   */
  function showCard(b, a) {
    const d = current();
    const pots = b && d ? d.pots.filter((p) => {
      const spot = chipSpot(p, d.rows.length);
      return "block" in spot && spot.block === b.i;
    }) : a ? [a.pot] : [];
    cardTop.replaceChildren(...(b ? [cardHead(b.row)] : a ? [potCard(a.pot, a.d)] : []));
    showKnobs(pots.map((p) => p.ref));
    const waveBox = b ? waveSection(b.row) : null;
    waveSlot.replaceChildren(...(waveBox ? [waveBox] : []));
    if (b && waveBox?.open) void drawWaves(b.row); // now, not on its toggle: a cached one draws in this frame
    cardRest.replaceChildren(...(b ? [card(b.row, b.i)] : []));
    cardBody.hidden = !b && !a;
    for (const c of el.querySelectorAll(".pot-chip")) {
      c.setAttribute("aria-expanded", String(!!a && /** @type {HTMLElement} */ (c).dataset.pot === a.pot.ref));
    }
    pickParts(b ? b.row.parts : a ? [a.pot.ref] : []);
  }

  /** The controls in the card: these pots' (kept as they are when it's the same pots). @param {string[]} refs */
  function showKnobs(refs) {
    const key = refs.join(" ");
    if (key === knobsShown) return;
    knobsShown = key;
    const controls = refs.map((ref) => deps.knob(ref)).filter((c) => c !== null);
    potPop.replaceChildren(...controls);
    potPop.hidden = !controls.length;
  }

  /** A pot on an arrow's card: its name, where it acts. @param {import("./stages-logic.js").PotChip} p @param {import("./stages-logic.js").Stages} d */
  function potCard(p, d) {
    return h("div", { class: "pot-card", id: "pot-card", "data-pot": p.ref }, [
      h("div", { class: "stage-head" }, [h("span", { class: "ref" }, [p.name]), h("span", { class: "role" }, [p.name === p.ref ? "pot" : `pot · ${p.ref}`])]),
      h("p", { class: "card-text" }, [potWhere(p, d.rows)]),
    ]);
  }

  /** Light `refs` on the schematic (hovered); with none, put out only what this pane lit. @param {string[]} refs */
  function lightParts(refs) {
    if (!refs.length && !ours) return;
    deps.highlight(refs);
    ours = refs.length > 0;
  }

  /** What the card is about, lit in the picked colour under any hover (D-127). @param {string[]} refs */
  function pickParts(refs) {
    if (!refs.length && !oursPicked) return;
    deps.highlight(refs, true);
    oursPicked = refs.length > 0;
  }

  /**
   * The chain: the guitar, a block per row, the amp, an arrow between each (its chips on
   * it). In the panel's side column, and over the chart in the large view.
   * @param {import("./stages-logic.js").Stages} d @param {string} id
   */
  function chain(d, id) {
    const spots = d.pots.map((p) => ({ pot: p, spot: chipSpot(p, d.rows.length) }));
    const on = (/** @type {(s: {block: number} | {arrow: number}) => boolean} */ f) => spots.filter((x) => f(x.spot)).map((x) => chip(x.pot, d));
    lines = new Map(curveNets(d.rows).map((n) => [n.net, { style: n.style, label: n.labels.join(" · ") }]));
    const items = [h("li", { class: "chain-end", style: "--line: var(--plot-input)", "data-line": "Guitar" }, ["Guitar"]), ...d.rows.map((r, i) => block(r, i, on((s) => "block" in s && s.block === i))), h("li", { class: "chain-end" }, ["Amp"])];
    const arrow = (/** @type {number} */ k) => {
      const chips = on((s) => "arrow" in s && s.arrow === k);
      const loss = arrowLoss(d.arrows?.[k], tone);
      const into = k < d.rows.length ? d.rows[k].label : "the amp";
      return h("li", { class: `chain-arrow${chips.length || loss ? " has-chips" : ""}`, "data-arrow": String(k) }, [
        ...(chips.length ? [h("span", { class: "arrow-chips" }, chips)] : []),
        ...(loss ? [h("span", { class: "arrow-loss", title: `What the parts between do to the signal at ${toneName(tone)}, into ${into}` }, [loss])] : []),
        h("span", { class: "arrow-glyph", "aria-hidden": "true" }),
      ]);
    };
    return h("ol", { class: "stage-chain", id, "aria-label": "The signal path" },
      items.flatMap((item, i) => (i ? [arrow(i - 1), item] : [item])));
  }

  /**
   * A pot's chip: its name and rotation; hover lights it on the schematic; a click opens
   * its control under the chain (the Knobs & switches pane's own, D-122).
   * @param {import("./stages-logic.js").PotChip} p @param {import("./stages-logic.js").Stages} d
   */
  function chip(p, d) {
    const b = h("button", { type: "button", class: "pot-chip", "data-pot": p.ref, "aria-expanded": String(pickedPot === p.ref),
      title: `${potWhere(p, d.rows)} Click to turn it.` }, [chipText(p.name, p.rotation)]);
    b.addEventListener("click", (e) => {
      e.stopPropagation(); // the block's click is handled here: its chip toggles its card
      const spot = chipSpot(p, d.rows.length);
      if ("block" in spot) {
        const ref = d.rows[spot.block].refs[0];
        picked = picked === ref ? null : ref;
        pickedPot = null;
      } else {
        pickedPot = pickedPot === p.ref ? null : p.ref;
        picked = null;
      }
      show();
    });
    b.addEventListener("keydown", (e) => e.stopPropagation()); // Enter on the chip isn't the block's
    b.addEventListener("pointerenter", () => lightParts([p.ref]));
    b.addEventListener("pointerleave", () => lightParts([]));
    return b;
  }

  /** A knob turned: its chip and open control follow. @param {any} control @param {number} value */
  function knobMoved(control, value) {
    showKnob(potPop, control, value);
    for (const c of el.querySelectorAll(`.pot-chip[data-pot="${CSS.escape(control.ref)}"]`)) c.textContent = chipText(control.label, value);
  }

  /**
   * A block: its name and own gain at the tone, what it is, its marks; accented when it
   * clips at a hard pick; "worst at 3 kHz" when another tone pushes it harder.
   * @param {import("./stages-logic.js").Row} r @param {number} i
   */
  function block(r, i, chips = /** @type {HTMLElement[]} */ ([])) {
    const gain = r.gain_db?.[String(tone)];
    const worst = shown ? rowWorst(shown.byTone, i) : null;
    const on = picked === r.refs[0];
    const marks = r.state ? [{ text: "saturated", tone: "over", title: r.state }] : blockMarks(r);
    const line = lines.get(r.net);
    const inner = discreteParts(r);
    const li = h("li", {
      class: `chain-block${r.levels.hard?.clips ? " clips" : ""}${inner ? " discrete" : ""}`, "data-refs": r.refs.join(" "), "data-kind": r.kind,
      ...(line ? { style: `--line: var(--plot-${line.style})`, "data-line": line.label } : {}),
      role: "button", tabindex: "0", "aria-pressed": String(on),
      title: `${r.bias?.text ?? clipperText(r)}${r.levels.hard?.clips ? "\nThe solid bar on its left: it clips at a hard pick." : ""}\nClick for its card.`,
    }, [
      h("span", { class: "block-head" }, [
        h("b", { class: "ref" }, [r.label]),
        ...(gain !== undefined && r.kind === "stage" ? [h("span", { class: "block-gain", title: `Its own gain at ${toneName(tone)}` }, [signedDb(gain)])] : []),
        ...(r.kind === "clipper" && r.clamp ? [h("span", { class: "block-gain", title: "Where it clamps, across it at a hard pick" }, [r.clamp.short])] : []),
      ]),
      h("span", { class: "role" }, [blockRole(r)]),
      ...(inner ? [h("span", { class: "discrete-parts" }, inner.map((q) => h("span", { class: "discrete-part", "data-ref": q.ref }, [h("b", {}, [q.ref]), ` ${q.job}`])))] : []),
      ...(marks.length ? [h("span", { class: "block-marks" }, marks.map((m) => h("span", { class: `mark tone-${m.tone}`, title: m.title }, [m.text])))] : []),
      ...(worst !== null && worst !== tone ? [h("span", { class: "block-worst", title: `Pushed hardest at ${toneName(worst)}` }, [`worst at ${toneName(worst)}`])] : []),
      ...(chips.length ? [h("span", { class: "block-chips" }, chips)] : []),
    ]);
    li.addEventListener("pointerenter", () => {
      lightParts(r.parts);
      light(r);
    });
    li.addEventListener("pointerleave", () => {
      lightParts([]);
      light(null);
    });
    const choose = () => {
      picked = on ? null : r.refs[0];
      pickedPot = null;
      show();
    };
    li.addEventListener("click", choose);
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        choose();
      }
    });
    return li;
  }

  /**
   * A block's card under its knobs: the three picks at the tone (or each tone measured),
   * and Try changes.
   * @param {import("./stages-logic.js").Row} r @param {number} i
   */
  function card(r, i) {
    const open = fix?.ref === r.refs[0] ? fix : null;
    const cells = h("div", { class: "stage-levels" }, LEVELS.map(([id, name]) => {
      const cell = r.levels[id];
      const { text, tone: colour } = cellText(r, cell);
      const title = cell.held ? `Held by the diodes in its feedback: they stop it short of its limits. ${cell.title}` : cell.title;
      return h("span", { class: `stage-cell tone-${colour}`, "data-level": id, title }, [h("b", {}, [name]), " ", text]);
    }));
    return h("div", { class: "stage-card-more" }, [
      ...(shown && shown.byTone.size > 1 ? [byToneTable(r, i)] : [h("p", { class: "card-at" }, [`At ${toneName(tone)}:`]), cells]),
      ...(r.state ? [h("p", { class: "warning" }, [r.state])] : []),
      ...tryChanges(r),
      ...(open ? [fixBox(open)] : []),
    ]);
  }

  /**
   * The picked block's Waveform section (D-127), under the tones, open unless the user shut
   * it: its waveform at the three picks, overlaid (the pane's own runs,
   * `POST /api/stages/waves`; what it shows is in the pane's ⓘ), and a table of their peaks,
   * clipping and THD, a column per pick in its line's colour, folded under "Readings"
   * (round 3b).
   * @param {import("./stages-logic.js").Row} r @returns {HTMLDetailsElement}
   */
  function waveSection(r) {
    const head = h("tr", {}, [h("th", {}, []), ...LEVELS.map(([id, name]) => h("th", { class: "wave-pick", style: `--line: var(--plot-${PICK_STYLES[id]})` }, [name]))]);
    const rows = waveTable(r).map((row) => h("tr", {}, [h("th", {}, [row.name]), ...row.cells.map((c) => h("td", {}, [c]))]));
    const readings = /** @type {HTMLDetailsElement} */ (h("details", { class: "wave-readings", id: "stage-wave-readings", ...(readingsOpen ? { open: "" } : {}) }, [
      h("summary", {}, ["Readings"]),
      h("table", { class: "stage-tones-table wave-table", id: "stage-wave-table" }, [h("thead", {}, [head]), h("tbody", {}, rows)]),
    ]));
    readings.addEventListener("toggle", () => { readingsOpen = readings.open; });
    const box = /** @type {HTMLDetailsElement} */ (h("details", { class: "card-waves", id: "stage-waves", ...(wavesShut ? {} : { open: "" }) }, [
      h("summary", {}, ["Waveform ", h("span", { class: "wave-of" }, [r.label])]),
      wavePlot,
      readings,
    ]));
    box.addEventListener("toggle", () => {
      wavesShut = !box.open;
      if (box.open && box.isConnected) void drawWaves(r);
    });
    return box;
  }

  /** The Waveform plot's look: axes, height and hover. */
  const WAVE_PLOT = { xLabel: "time (ms)", yLabel: "volts", height: 160, hover: { x: (/** @type {number} */ x) => `${x.toFixed(2)} ms`, y: (/** @type {number} */ y) => `${y.toFixed(2)} V` } };

  /**
   * Draw row `r`'s waveforms, asked for once per tone and circuit; not again when they're
   * drawn already. Until they come, an empty plot of the same size, so nothing jumps.
   * @param {import("./stages-logic.js").Row} r
   */
  async function drawWaves(r) {
    const key = `${tone} ${r.net} ${measured}`;
    if (wavePlot.dataset.key === key) return;
    wavePlot.dataset.key = key;
    let got = waves.get(key);
    if (!got) {
      const period = 1000 / tone;
      const empty = { x: [0, 2 * period], series: LEVELS.map(([id, name]) => ({ label: name, style: PICK_STYLES[id], values: [null, null] })) };
      linePlot(wavePlot, /** @type {any} */ (empty), { ...WAVE_PLOT, hover: undefined, xRange: [0, 2 * period], yRange: [0, 9] });
      wavePlot.append(h("p", { class: "hint wave-loading" }, ["Drawing the waveforms…"]));
      try {
        got = /** @type {{time_ms: number[], waves: Record<string, number[]>}} */ (await postJson("api/stages/waves", { circuit: JSON.parse(measured), net: r.net, tone }));
      } catch (err) {
        if (wavePlot.dataset.key === key) {
          wavePlot.replaceChildren(h("p", { class: "warning" }, [/** @type {Error} */ (err).message]));
          delete wavePlot.dataset.key; // asked again next time
        }
        return;
      }
      waves.set(key, got);
    }
    if (wavePlot.dataset.key !== key || !wavePlot.isConnected) return; // another card or tone meanwhile
    linePlot(wavePlot, waveSeries(got), WAVE_PLOT);
  }

  /**
   * A block's card, the top: its name and role, the bias bar and its sentence, or a
   * clipper's clamp. @param {import("./stages-logic.js").Row} r
   */
  function cardHead(r) {
    const mark = biasMark(r);
    const guess = r.bias?.limits === "rule of thumb";
    const aimText = h("p", { class: "bias-aim hint", id: "bias-aim", hidden: "" });
    const bar = mark && r.bias ? biasBar(r, mark, aimText) : null;
    // in the large view the bar has its ends in volts under it: what it sets is the output's DC
    const scale = bar && r.bias && view.expanded() ? biasScale(r.bias) : null;
    const scaled = scale ? h("span", { class: "bias-scaled", title: `${r.refs[0]}'s output voltage (DC), between the limits of its room` }, [
      bar, h("span", { class: "bias-scale" }, [h("span", {}, [scale.low]), h("span", {}, ["output DC"]), h("span", {}, [scale.high])]),
    ]) : bar;
    const state = bar && scaled && r.bias
      ? h("span", { class: "bias-line" }, [scaled, h("span", { class: "bias-place" }, [r.bias.place, ...(guess ? [h("sup", {}, ["*"])] : [])])])
      : h("span", { class: "clamp-text" }, [r.clamp?.short ?? ""]);
    return h("div", { class: "stage-card", id: "stage-card", "data-refs": r.refs.join(" "), "data-kind": r.kind }, [
      h("div", { class: "stage-head" }, [h("span", { class: "ref" }, [r.label]), h("span", { class: "role" }, [roleText(r)]), state]),
      ...(discreteText(r) ? [h("p", { class: "card-text discrete-text" }, [discreteText(r)])] : []),
      h("p", { class: "card-text" }, [r.bias ? r.bias.text : clipperText(r)]),
      aimText,
    ]);
  }

  /**
   * A stage's bias bar. In the large view its mark can be dragged (or moved with the
   * arrow keys, Enter to look) to aim the bias anywhere (Bias to…, D-123): the aim's
   * volts and room each way show while it moves, and letting go looks for what puts it
   * there. The aim asked for stays drawn, hollow.
   * @param {import("./stages-logic.js").Row} r @param {{at: number, tone: string}} mark @param {HTMLElement} aimText
   */
  function biasBar(r, mark, aimText) {
    const asked = fix?.kind === "bias" && fix.ref === r.refs[0] && fix.aim !== null ? fix.aim : null;
    const ghost = h("i", { class: "aim", ...(asked === null ? { hidden: "" } : { style: `left: ${asked * 100}%` }) });
    const bias = r.bias;
    const reach = view.expanded() && r.kind === "stage" && bias && biasAim(bias, 0.5) ? reachText(reachOf(r)) : null;
    const can = view.expanded() && r.kind === "stage" && !!bias && !!biasAim(bias, 0.5) && reach?.aimable !== false;
    const known = can ? reaches.get(`${measured}\n${r.refs[0]}`) : null;
    const [lo, hi] = known && known !== "asking" ? [known.lo, known.hi] : [0.02, 0.98];
    const out = (reach?.out ?? []).map(([a, b]) => h("b", { class: "out-of-reach", style: `left: ${a}%; width: ${b - a}%` }));
    const bar = h("span", { class: `bias-bar tone-${mark.tone}${can ? " aimable" : ""}`,
      ...(can ? { role: "slider", tabindex: "0", "aria-label": `Aim ${r.refs[0]}'s bias`, "aria-valuemin": String(Math.round(lo * 100)), "aria-valuemax": String(Math.round(hi * 100)),
        "aria-valuenow": String(Math.round(mark.at)), title: out.length ? "Drag to aim its bias (the hatched ends are out of reach)" : "Drag to aim its bias anywhere" } : {}) },
    [...out, h("i", { style: `left: ${mark.at}%` }), ghost]);
    if (asked !== null && bias) {
      aimText.hidden = false;
      aimText.textContent = biasAim(bias, asked)?.text ?? "";
    }
    if (!can || !bias) return bar;
    let t = asked ?? mark.at / 100;
    const aim = (/** @type {number} */ x) => {
      t = Math.min(Math.max(x, lo), hi); // no part reaches past these
      ghost.hidden = false;
      ghost.style.left = `${t * 100}%`;
      bar.setAttribute("aria-valuenow", String(Math.round(t * 100)));
      aimText.hidden = false;
      aimText.textContent = biasAim(bias, t)?.text ?? "";
    };
    const from = (/** @type {PointerEvent} */ e) => {
      const box = bar.getBoundingClientRect();
      return (e.clientX - box.left) / box.width;
    };
    let dragging = false;
    bar.addEventListener("pointerdown", (e) => {
      if (el.dataset.loading) return; // the chain is being measured again: its bar is old
      dragging = aiming = true;
      bar.setPointerCapture(e.pointerId);
      aim(from(e));
    });
    bar.addEventListener("pointermove", (e) => dragging && aim(from(e)));
    bar.addEventListener("pointercancel", () => void (dragging = aiming = false));
    bar.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = aiming = false;
      void startFix("bias", r, { aim: Math.round(t * 100) / 100 });
    });
    bar.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft" || e.key === "ArrowDown") aim(t - 0.05);
      else if (e.key === "ArrowRight" || e.key === "ArrowUp") aim(t + 0.05);
      else if (e.key === "Enter" && !el.dataset.loading) void startFix("bias", r, { aim: Math.round(t * 100) / 100 });
      else return;
      e.preventDefault();
    });
    return bar;
  }

  /** Each tone measured: the row's own gain and its three picks. @param {import("./stages-logic.js").Row} r @param {number} i */
  function byToneTable(r, i) {
    const tones = TONES.filter(([t]) => shown?.byTone.has(t));
    const head = h("tr", {}, [h("th", {}, ["Tone"]), h("th", {}, ["Gain"]), ...LEVELS.map(([, name]) => h("th", {}, [name]))]);
    const lines = tones.map(([t, name]) => {
      const row = shown?.byTone.get(t)?.rows[i];
      const gain = r.gain_db?.[String(t)];
      return h("tr", { "data-tone": String(t), ...(t === tone ? { class: "here" } : {}) }, [
        h("th", {}, [name]),
        h("td", {}, [r.kind === "stage" && gain !== undefined ? signedDb(gain) : ""]),
        ...LEVELS.map(([id]) => {
          const cell = row?.levels[id];
          if (!row || !cell) return h("td", {}, ["—"]);
          const { text, tone: colour } = cellText(row, cell);
          return h("td", { class: `stage-cell tone-${colour}`, title: cell.title }, [text]);
        }),
      ]);
    });
    return h("table", { class: "stage-tones-table", id: "stage-tones-table" }, [h("thead", {}, [head]), h("tbody", {}, lines)]);
  }

  /** The chart, while the large view is open: the diagram at once, the curve once measured. */
  function draw() {
    if (!view.expanded()) return;
    const d = current();
    const at = shown && d?.rows.length ? { key: shown.key, data: d } : null;
    if (chart === "diagram" || !at) stopSweep(); // the curve isn't wanted any more
    if (chart === "diagram" || !at) progress.hidden = true;
    if (!at) {
      plot.replaceChildren(); // @ts-ignore: a plot is kept on its element (plots.js)
      plot._plot?.destroy(); // @ts-ignore
      plot._plot = null;
      return;
    }
    if (chart === "diagram") {
      const names = ["Guitar", ...at.data.rows.map((r) => r.label)];
      linePlot(plot, levelDiagram(at.data, before() ? (edit?.byTone?.get(tone) ?? null) : null), {
        xLabel: "along the signal path", yLabel: "dBV peak", xNames: names,
        hover: { x: String, y: dbvText }, height: view.plotHeight(PLOT_RESERVED + strip.offsetHeight), marks: diagramMarks(at.data),
      });
    } else void sweep(at);
    keyStrip();
  }

  /**
   * The strip over the chart (D-123): the chain as in the panel, centred and framed, the
   * same over both charts (Phase 8d: hovering a block lights its column, which is
   * enough); over the level in → out curve each block in its line's colour.
   */
  function keyStrip() {
    const keyed = view.expanded() && chart === "curve";
    strip.querySelector(".stage-chain")?.classList.toggle("keyed", keyed);
    for (const b of /** @type {NodeListOf<HTMLElement>} */ (strip.querySelectorAll("[data-line]"))) {
      b.classList.toggle("line-off", keyed && hiddenLines.has(b.dataset.line ?? ""));
    }
  }

  /**
   * The level in → out curve at the tone picked: one guitar level at a time, drawn as it
   * goes, kept once whole (and every transient is in the server's cache, so measuring it
   * again is quick).
   * @param {{key: string, data: import("./stages-logic.js").Stages}} at
   */
  async function sweep(at) {
    const curveKey = `${at.data.tone} ${at.key}`;
    const kept = curves.get(curveKey);
    if (kept) {
      progress.hidden = true;
      return curveOf(at, kept);
    }
    if (running === curveKey) return partial.length ? curveOf(at, partial) : undefined; // carries on
    stopSweep();
    const mine = sweeping;
    running = curveKey;
    const circuit = JSON.parse(at.key);
    const points = (partial = []);
    progress.classList.replace("warning", "hint");
    progress.hidden = false;
    for (const [i, amplitude] of SWEEP_LEVELS.entries()) {
      progressText.textContent = `Measuring the guitar at ${i + 1} of ${SWEEP_LEVELS.length} levels…`;
      progressBar.hidden = false;
      progressBar.value = i;
      try {
        points.push(await postJson("api/stages/level", { circuit, amplitude, tone: at.data.tone }));
      } catch (err) {
        if (mine !== sweeping) return;
        running = "";
        progress.classList.replace("hint", "warning");
        progressText.textContent = /** @type {Error} */ (err).message;
        progressBar.hidden = true;
        return;
      }
      if (mine !== sweeping) return;
      curveOf(at, points);
    }
    running = "";
    progress.hidden = true;
    curves.set(curveKey, points);
    if (curves.size > KEEP_CURVES) curves.delete(/** @type {string} */ (curves.keys().next().value));
  }

  function stopSweep() {
    sweeping++;
    running = "";
  }

  /** @param {{key: string, data: import("./stages-logic.js").Stages}} at @param {import("./stages-logic.js").LevelPoint[]} points */
  function curveOf(at, points) {
    linePlot(plot, levelCurve(at.data.rows, points, lit?.net, before() ? (edit?.curves.get(at.data.tone) ?? null) : null), {
      xLabel: "guitar, dBV peak", yLabel: "dBV peak",
      hover: { x: (x) => `guitar ${dbvText(x)}`, y: dbvText }, height: view.plotHeight(PLOT_RESERVED + strip.offsetHeight),
      marks: { ...noMarks(), lines: pickLines(at.data.picks) },
      hidden: hiddenLines,
      onToggle: (label, on) => {
        if (on) hiddenLines.delete(label);
        else hiddenLines.add(label);
        keyStrip();
      },
    });
    keyStrip();
  }

  /** Whether the charts draw the chain as it was: Try changes open, with changes, Before on. */
  function before() {
    return beforeOn && !!edit && edit.key !== measured;
  }

  /** The level diagram's marks: the hovered block's place shaded. @param {import("./stages-logic.js").Stages} d */
  function diagramMarks(d) {
    const i = lit ? d.rows.indexOf(lit) + 1 : 0; // the guitar is 0
    return { ...noMarks(), bands: i ? [{ lo: i - 0.4, hi: i + 0.4 }] : [] };
  }

  /** @param {import("./stages-logic.js").Row | null} r the block hovered, or none */
  function light(r) {
    lit = r;
    const d = current();
    if (!view.expanded() || !shown || !d) return;
    if (chart === "diagram") setMarks(plot, diagramMarks(d));
    else {
      const curveKey = `${d.tone} ${shown.key}`;
      const points = curves.get(curveKey) ?? (running === curveKey ? partial : []);
      if (points.length) curveOf({ key: shown.key, data: d }, points);
    }
  }

  return { refresh, clear, collapse: view.collapse, knobMoved };
}

/** A chip's text: "Filter 50 %". @param {string} name @param {number} rotation */
function chipText(name, rotation) {
  return `${name} ${Math.round(rotation * 100)} %`;
}


/** A plot value in dBV, as the hover box writes it. @param {number} v */
function dbvText(v) {
  return `${v.toFixed(1)} dBV`;
}
