/**
 * The app root: opens circuits (starters and the user's own), applies edits with undo,
 * keeps the selection and knob state, runs the simulations through the API and fills
 * the panels. The only module with globals.
 *
 * Every edit is a pure function of the circuit JSON (editor/edit.js). The new circuit is
 * posted to `/api/view` (the server owns geometry and nets, D-044), drawn, and re-run.
 */

import { getJson, postJson } from "./api.js";
import { audioPanel } from "./audio.js";
import { frequencyTools } from "./frequency.js";
import { stagesPane } from "./stages.js";
import { notesPane, renameNotice } from "./notes.js";
import { atFreqs } from "./audio-logic.js";
import { addItems, allItems, blockAnchor, extract, fixedRefs, isEmpty, itemsInBox, pasteBlock, toggleItems } from "./editor/blocks.js";
import { parseTag, versionTag } from "./editor/files.js";
import { fileDialogs } from "./file-dialogs.js";
import { blockDialogs } from "./block-dialogs.js";
import { palette } from "./palette.js";
import { appMenus } from "./app-menus.js";
import { powerMenu } from "./power.js";
import { inspector } from "./inspector.js";
import { liveSliders, sliderFields } from "./live-sliders.js";
import {
  addLabel, addPart, addText, paletteEntry, groupRefs, withChips, addWires, applyDiff, deleteItems, drawnWire, findRef, moveWireEnd, wireDiff, moveItems, isUnwired, renameLabel, setText, addSupply, itemsAfterMove, itemsAt, rotateLabel, rotatePart, sameConnections, wireRun, updatePart,
} from "./editor/edit.js";
import { ask, closeForm, confirmed, formIsOpen, openForm } from "./editor/form.js";
import { remember, remembered } from "./storage.js";
import { History } from "./editor/history.js";
import { historyPane } from "./history-pane.js";
import { actionFor } from "./editor/keys.js";
import { db, volts } from "./fixed.js";
import { closeMenus } from "./menus.js";
import { reorderable } from "./panes.js";
import { liveCurves, liveValues, nearestStep, readingRows } from "./live.js";
import { h, knobControl, paneInfo, restoreLargeViews, shrinkLargeViews, renderDc, renderKnobs, renderNodeView, renderPartView, renderProbeFailed, renderProblems, renderReadings, renderSweepSummary, showKnob } from "./panels.js";
import { barPlot, curvePlot, forgetColours, linePlot, liveLinePlot } from "./plots.js";
import { desktopMenus, desktopUnsaved } from "./desktop.js";
import { settingsSheet } from "./settings.js";
import { Schematic, supplyKind } from "./schematic/render.js";
import { setSwitchKinds } from "./schematic/symbols.js";
import {
  capacitorSeries, deviceCurve, frequencySeries, harmonicBars, scopeSeries, snapshotOf, sweepSummary, valueSweepSeries,
} from "./series.js";
import { dismissProblem, problemTarget, restoreProblem } from "./problems.js";
import { debounce, focusNet, keptControls, latestOnly, oneAtATime, openingOf, withControls } from "./state.js";

const KNOB_DEBOUNCE_MS = 120;
const EDIT_DEBOUNCE_MS = 250; // re-run the simulation once edits pause (with auto-run on)
const AUTORUN_KEY = "solum.autorun";
const CAP_TYPES_KEY = "solum.capTypes";
const MARKS_KEY = "solum.problemMarks";

/**
 * A switch as it was last left (kept as 1 or 0; Auto-run with the preferences, the View ones in this browser): Auto-run and View → Capacitor
 * types are off unless turned on (D-065); View → Problem marks is on unless turned off (D-176).
 * @param {string} key @param {boolean} fallback
 */
const savedFlag = (key, fallback) => Boolean(remembered(key) ?? fallback);

const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));

/** The part called `ref` on the open sheet. @param {string | null} ref @returns {any} */
const partOf = (ref) => state.circuit?.parts.find((/** @type {any} */ p) => p.ref === ref);

/** The output's net as a selection (what's probed when nothing else is), or null. @returns {Selection | null} */
const outputSelection = () => (state.view?.probes.out ? { kind: "net", id: state.view.probes.out } : null);

/**
 * @typedef {{kind: "starter" | "circuit" | "block" | "new" | "copy", id: string}} Source
 *   `copy`: an unsaved copy of a core block or a final version (`id` is `core:<id>` or
 *   `user:<id>`), saved only when the user saves it (D-075)
 * @typedef {{kind: "circuit" | "block", layer: "user" | "core" | "starter", path: string,
 *   saved: string | null, readonly: boolean, link: string, current: boolean}} FileInfo what the server says about an open file
 * @typedef {import("./schematic/render.js").Selection} Selection
 */

const state = {
  /** @type {Source | null} */ source: null,
  /** @type {any} */ view: null,
  /** @type {any} */ circuit: null,
  /** @type {Selection | null} */ selection: null,
  level: "med",
  /** @type {Record<string, number>} */ controls: {},
  /** @type {any} */ run: null,
  /** @type {any} */ part: null,
  /** @type {any} */ sweep: null,
  /** @type {Record<string, ReturnType<typeof snapshotOf>>} */ snapshots: { frequency: null, scope: null },
  /** @type {Record<string, any>} */ plotted: { frequency: null, scope: null },
  /** @type {Record<string, string[]>} */ models: {},
  /** @type {any[]} */ starters: [],
  /** @type {Array<{kind: string, hint: string}>} the capacitor guide's kinds (D-095) */ capKinds: [],
  /** @type {Record<string, {idss: number, vp: number}>} each JFET model's own Idss and Vp */ jfets: {},
  /** @type {Record<string, {hfe: number, leakage: number}>} each transistor model card's own gain and leakage (D-130) */ bjts: {},
  /** @type {Record<string, import("./editor/fields.js").Chip>} each chip model's chip: its type, units and pins (D-140, D-180) */ chips: {},
  /** @type {import("./editor/fields.js").BatteryState[]} a 9 V battery's states as it drains (D-143) */ batteries: [],
  /** @type {import("./editor/fields.js").InductorPreset[]} measured wah inductors (D-173) */ inductors: [],
  /** @type {import("./editor/fields.js").PickupChoice[]} the measured pickups (D-096) */ pickups: [],
  /** @type {Array<{name: string, text: string}>} the standard enclosure sizes (D-204) */ enclosures: [],
  /** @type {string | null} */ placing: null,
  /** @type {{circuit: any, name: string, inserted: boolean} | null} the block being placed */ placingBlock: null,
  /** @type {any} what Ctrl+C took (a block, D-072) */ clipboard: null,
  /** @type {FileInfo | null} the open file (null for a new sheet or an unsaved copy) */ file: null,
  lastLabel: "OUT",
  dirty: false,
  dc: false,
  impedance: false, // the View → Impedance overlay (D-127)
  capTypes: savedFlag(CAP_TYPES_KEY, false), // View → Capacitor types: "100n film" on the schematic
  marks: savedFlag(MARKS_KEY, true), // View → Problem marks: each problem marked on the sheet (D-176)
  autorun: savedFlag(AUTORUN_KEY, false),
  stale: false,
  shownNet: "", // the net the last run showed "at this point": a group selected runs there again
  updates: 0,
  views: 0,
  edits: 0, // circuits set by edits, undo and redo: a live system fetched before one is stale
  /** @type {Promise<void>} the selection's views loading (the inspector's slider waits for them) */ selecting: Promise.resolve(),
  /** @type {{circuit: any, result: any} | null} the Problems panel's last check, and of what */ problems: null,
  /** @type {Set<string>} problems whose rows are open */ openProblems: new Set(),
  /** @type {{ref: string, live: import("./live.js").Live} | null} the knob being dragged, D-081 */ knobLive: null,
};

/** @type {History<any>} */
const undoStack = new History();
// the header's History button and its pane (D-101): the undo steps, a click goes to one
const historyView = historyPane(/** @type {HTMLButtonElement} */ ($("history-button")), {
  rows: () => undoStack.rows(),
  go: (steps) => goHistory(steps),
  session: () => undoStack.session,
});
const audio = audioPanel($("audio-body"), {
  circuit: () => played(),
  view: () => state.view,
  pots: () => (state.view?.controls ?? []).filter((/** @type {any} */ c) => c.kind === "pot"),
  name: () => state.circuit?.name ?? "circuit",
  pickups: () => state.pickups,
  editGuitar: () => {
    const guitar = state.circuit?.parts.find((/** @type {any} */ p) => p.type === "guitar");
    if (guitar) select({ kind: "part", id: guitar.ref }).then(() => forms.inspect(guitar.ref));
  },
  highlight: (refs, picked) => schematic.highlight(refs, picked),
});
// Bias & headroom (Phase 8c, D-106): measured again when the circuit changes, while it's open
/** the nets the Scope and Harmonics show, for their ⓘ (D-109) */
const notesAt = { scope: "", harmonics: "" };
paneInfo(/** @type {HTMLDetailsElement} */ ($("panel-scope")), "Scope", () => [scopeNote(notesAt.scope)]);
paneInfo(/** @type {HTMLDetailsElement} */ ($("panel-harmonics")), "Harmonics", () => [harmonicsNote(notesAt.harmonics)]);
const stages = stagesPane(/** @type {HTMLDetailsElement} */ ($("panel-stages")), $("stages-body"), {
  circuit: () => (state.circuit && !isUnwired(state.circuit) && !state.view?.problem ? played() : null),
  highlight: (refs, picked) => schematic.highlight(refs, picked),
  edited: () => state.circuit, // as edited, without the knobs' turns: Try changes' Changed list (D-123)
  // Try changes (D-119, D-123): one edit session over any blocks, its values set as one edit each, re-run
  begin: (name, owner) => editSession(name, "bias", owner),
  setParts: async (patches, label, { undo = [], apply = [], run = true } = {}) => {
    let next = state.circuit;
    for (const d of undo) next = applyDiff(next, d, { undo: true }); // an arrangement's parts out (D-124)
    for (const d of apply) next = applyDiff(next, d);
    for (const [ref, fields] of Object.entries(patches)) next = updatePart(next, ref, fields);
    const message = await tryEdit(next, label, "bias");
    if (!message && !state.autorun && run) refresh(); // re-run, as a slider's release does
    return message;
  },
  // a pot's chip (D-122): the Knobs & switches pane's own control, turning the same knob
  knob: (ref) => {
    const c = state.view?.controls.find((/** @type {any} */ x) => x.ref === ref);
    return c ? knobControl(c, state.controls[ref], onKnob, grabKnob, knobInUse) : null;
  },
  editCurve: (ref) => void tools.editPart(ref), // a capacitor in the gain box (D-125)
});
const tools = frequencyTools(
  { panel: $("panel-frequency"), tools: $("frequency-tools"), plot: $("frequency-plot"), body: $("frequency-layers") },
  {
    circuit: () => state.circuit,
    played: () => played(),
    // Edit curve by part (D-102): the value only (a knob's turn is the Knobs panel's)
    slider: (ref) => sliders.slideFields(ref, sliderFields(partOf(ref)).filter((f) => f.field === "value"), "influence-"),
    valueSlider: (ref) => sliders.slideFields(ref, [{ field: "value", label: "Value" }], "handle-"),
    levelSliders: (refs) => sliders.slideTogether(refs, "level-"),
    highlight: (refs) => schematic.highlight(refs),
    showReadings: (readings, net) => renderReadings($("frequency-readings"), readingRows(readings), net),
    redraw: () => state.view && render(currentNet()),
    editSession: (owner) => editSession("Frequency curve", "curve", owner), // its name in History and the prompts (D-127); the button stays Edit curve
    openHistory: () => historyView.open(),
    async putBack(ref, value) {
      const message = await tryEdit(updatePart(state.circuit, ref, { value }), `Put back ${ref}`, "curve");
      if (message) showError(message);
      else if (!state.autorun) refresh(); // re-run, as a slider's release does
    },
  },
);
// the Notes pane (9d4): a note clicked in Parts & nets is selected as a click on the sheet would
const notes = notesPane($("notes-body"), $("notes-count"), {
  circuit: () => state.circuit,
  nets: () => new Set(Object.keys(state.view?.nets ?? {})),
  edit: (next, label) => tryEdit(next, label),
  select(kind, id) {
    if (kind === "part") schematic.reveal(id);
    select({ kind, id });
  },
  reveal() {
    const pane = /** @type {HTMLDetailsElement} */ ($("panel-notes"));
    pane.open = true;
    pane.scrollIntoView({ block: "nearest" });
  },
});
const renameNote = renameNotice($("rename-notice"), {
  circuit: () => state.circuit,
  edit: (next, label) => tryEdit(next, label),
  open: (where) => notes.show(where),
});
/** The line under the canvas. @param {string} text */
const hint = (text) => {
  $("hint").textContent = text;
};
const files = fileDialogs($("canvas-body"), {
  source: () => state.source,
  file: () => state.file,
  circuit: () => state.circuit,
  dirty: () => state.dirty,
  isBlock: () => isBlock(),
  enclosures: () => state.enclosures,
  go: (source) => go(source),
  leaveTo: (source) => leaveTo(source),
  confirmLeave: () => confirmLeave(),
  tryEdit: (next, label) => tryEdit(next, label),
  afterSave: (saved, opts) => afterSave(saved, opts),
  refreshFile: () => refreshFile(),
  setDirty: (dirty) => setDirty(dirty),
  showError: (message) => showError(message),
  hint,
});
const blocks = blockDialogs($("canvas-body"), {
  source: () => state.source,
  circuit: () => state.circuit,
  view: () => state.view,
  selectedItems: () => selectedItems(),
  startPlacingBlock: (block, view, name, inserted) => startPlacingBlock(block, view, name, inserted),
  go: (source) => go(source),
  leaveTo: (source) => leaveTo(source),
  showError: (message) => showError(message),
  hint,
});
const power = powerMenu({ select: /** @type {HTMLSelectElement} */ ($("power")), chip: $("power-chip"), draw: $("power-draw"), host: $("canvas-body") }, {
  circuit: () => state.circuit,
  view: () => state.view,
  controls: () => state.controls,
  run: () => state.run,
  stale: () => state.stale,
  edit: (next, label) => edit(next, label),
  tryEdit: (next, label) => tryEdit(next, label),
  runSweep: (ref, field, values) => runSweep(ref, field, values),
  showSupplyTiles: () => tiles.showSupplyTiles(),
  showError: (message) => showError(message),
});
const sliders = liveSliders({
  circuit: () => state.circuit,
  run: () => state.run,
  played: () => played(),
  autorun: () => state.autorun,
  frequencyNets: () => frequencyNets(),
  fetchLive: (controls, steps, circuit) => fetchLive(controls, steps, circuit),
  drawLive: (live, values) => drawLive(live, values),
  tryEdit: (next, label, source) => tryEdit(next, label, source),
  ranAgain: () => ranAgain(),
  setCircuit: (circuit) => setCircuit(circuit),
  discardUndo: () => undoStack.discard(),
  refresh: () => refresh(),
  redraw: () => render(currentNet()),
});
const forms = inspector($("canvas-body"), {
  circuit: () => state.circuit,
  view: () => state.view,
  run: () => state.run,
  selection: () => state.selection,
  selecting: () => state.selecting,
  library: () => state,
  partOf: (ref) => partOf(ref),
  select: (selection) => select(selection),
  stopPlacing: () => stopPlacing(),
  tryEdit: (next, label) => tryEdit(next, label),
  runSweep: (ref, field, values) => runSweep(ref, field, values),
  sliders: (part) => sliders.forPart(part),
  showRenames: (renamed) => renameNote.show(renamed),
  report: (p) => report(p),
});
const requests = latestOnly();
/** @type {Promise<unknown>} the Bias & headroom pane's measuring of the last run's circuit */
let stagesMeasuring = Promise.resolve();
const viewRequests = latestOnly();
const problemRequests = latestOnly();
const openRequests = latestOnly(); // a circuit opened while another loads: the last one wins
let opening = ""; // the hash of the circuit being opened, until it's shown
const schematic = new Schematic(/** @type {SVGSVGElement} */ (/** @type {unknown} */ ($("schematic"))), {
  onNet: (net, item) => (blocks.marking() ? blocks.addPortRow(net) : select({ kind: "net", id: net, ...item, ...(item.wire !== undefined ? { run: wireRun(state.circuit, item.wire) } : {}) })),
  onPart: (ref) => select({ kind: "part", id: ref }),
  onToggle: (item) => selectItems(toggleItems(currentItems(), item)),
  onBox: (box, add) => selectItems(add ? addItems(currentItems(), itemsInBox(state.circuit, box)) : itemsInBox(state.circuit, box)),
  onEdit: (ref) => forms.inspect(ref),
  onEditLabel: (index) => editLabel(index),
  onText: (index) => selectItems({ parts: [], wires: [], labels: [], texts: [index] }),
  onEditText: (index) => textEditor(index),
  onMove: (items, dx, dy) => moveOnSheet(items, dx, dy),
  onWire: (segments) => {
    clearSelection();
    return edit(addWires(state.circuit, segments), "Add wire");
  },
  onMoveEnd: (from, to) => {
    clearSelection();
    return edit(moveWireEnd(state.circuit, from, to), "Move wire end");
  },
  route: (a, b, horizontal, pending) => drawnWire(state.circuit, a, b, horizontal, pending),
  preview: (change) => {
    const next = "items" in change ? moveItems(state.circuit, change.items, change.dx, change.dy) : moveWireEnd(state.circuit, change.from, change.to);
    return wireDiff(state.circuit.wires ?? [], next.wires ?? []);
  },
  onPlace: (pos, wire) => place(pos, wire),
  onContext: (x, y, item) => menus.contextMenu(x, y, item),
  onMark: (key) => openProblem(key),
  onEmpty: () => select(outputSelection()),
});
const menus = appMenus($("canvas-body"), schematic, {
  source: () => state.source,
  file: () => state.file,
  circuit: () => state.circuit,
  view: () => state.view,
  selection: () => state.selection,
  dirty: () => state.dirty,
  isBlock: () => isBlock(),
  starters: () => state.starters,
  shown: () => state,
  undoLabels: () => undoStack.labels,
  selectedItems: () => selectedItems(),
  canPaste: () => canPaste(),
  deletable: () => deletable(),
  partOf: (ref) => partOf(ref),
  files,
  blocks,
  leaveTo: (source) => leaveTo(source),
  select: (selection) => select(selection),
  inspect: (ref) => forms.inspect(ref),
  tryEdit: (next, label) => tryEdit(next, label),
  showNote: (where, focus) => notes.show(where, focus),
  report: (p) => report(p),
  refreshModels: () => refreshModels(),
  undo: () => undo(),
  redo: () => redo(),
  openHistory: () => historyView.open(),
  rotate: () => rotate(),
  deleteSelection: () => deleteSelection(),
  copy: () => copy(),
  paste: () => paste(),
  selectAll: () => selectItems(allItems(state.circuit)),
  findPart: () => findPart(),
  toggleDc: () => toggleDc(),
  toggleImpedance: () => toggleImpedance(),
  toggleCapTypes: () => toggleCapTypes(),
  toggleMarks: () => toggleMarks(),
  resetPanes: () => resetPanes(),
  openSettings: () => openSettings(),
});
const tiles = palette($("palette"), schematic, {
  circuit: () => state.circuit,
  startPlacing: (type) => startPlacing(type),
  stopPlacing: () => stopPlacing(),
  place: (pos, wire) => place(pos, wire),
  setWireMode: (on) => setWireMode(on),
  askLabel: () => askLabel(),
});


/** @param {string | null} message */
function showError(message) {
  const el = $("error");
  el.hidden = !message;
  el.textContent = message ?? "";
}

// ---- opening circuits ------------------------------------------------------------

/** `#circuit/<id>`, `#starter/<id>`, `#block/<id>`, `#copy/core:<id>` or `#new` (an
 * unsaved sheet); a bare `#ts808` is a starter (Phase 2 links). No hash: a new sheet. */
function sourceFromHash() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (!hash || hash === "new") return /** @type {Source} */ ({ kind: "new", id: "" });
  const [kind, id] = hash.includes("/") ? hash.split("/", 2) : ["starter", hash];
  return ["circuit", "starter", "block", "copy"].includes(kind) ? /** @type {Source} */ ({ kind, id }) : null;
}

/** @param {Source} source */
const hashOf = (source) => (source.kind === "new" ? "#new" : `#${source.kind}/${source.id}`);

/** This page's place in the browser history: each entry is numbered, so Back and Forward
 * can be undone when the user cancels the save prompt. */
let here = 0;

/** Open `source` as a new history entry (or reopen it, if it's the one open). The caller
 * has already checked that leaving is fine (`leaveTo`). @param {Source} source */
function go(source) {
  setDirty(false);
  if (!(state.source && hashOf(source) === hashOf(state.source))) history.pushState({ n: ++here }, "", hashOf(source));
  open(source).catch((err) => showError(err.message));
}

/**
 * Before anything replaces what's open: with unsaved changes, ask Save / Don't Save /
 * Cancel (D-075). True when it's fine to go on (saved, not wanted, or nothing to save).
 */
async function confirmLeave() {
  if (!state.dirty) return true;
  const choice = await ask({
    title: `Do you want to save the changes to \u201c${state.circuit.name}\u201d?`,
    text: "Your changes will be lost if you don't save them.",
    cancel: "cancel",
    buttons: [
      { label: "Don't Save", value: "discard", kind: "aside" },
      { label: "Cancel", value: "cancel" },
      { label: "Save", value: "save", kind: "primary" },
    ],
  });
  if (choice === "discard") return true;
  return choice === "save" ? files.save({ stay: true }) : false;
}

/** File → Settings… (D-310); in the Mac app also its menu bar's Settings… (D-321). */
function openSettings() {
  if (document.getElementById("settings")) return;
  const onTheme = () => {
    forgetColours();
    if (state.run) render(currentNet());
  };
  // a moved folder reloads the page: ask about unsaved work first, as before any leaving
  const leave = async () => {
    if (!(await confirmLeave())) return false;
    state.dirty = false; // answered: the reload must not ask again
    return true;
  };
  report(settingsSheet(onTheme, leave));
}

/** Open `source` once leaving what's open is fine. @param {Source} source */
async function leaveTo(source) {
  if (await confirmLeave()) go(source);
}

/** Where `source`'s view comes from. @param {Source} source */
function viewUrl(source) {
  if (source.kind === "new") return "api/blank";
  if (source.kind === "copy") {
    const [layer, id] = source.id.split(":", 2);
    return `api/blocks/${encodeURIComponent(id)}?layer=${layer}`;
  }
  return `api/${source.kind === "block" ? "blocks" : source.kind === "circuit" ? "circuits" : "starters"}/${encodeURIComponent(source.id)}`;
}

/**
 * Back to the circuit editor: no part form, not placing, the large views shrunk to their
 * bars (D-127). Opening a circuit does this first; a new large view or mode belongs here too.
 */
function backToEditor() {
  closeForm();
  stopPlacing();
  shrinkLargeViews(); // to their bars, not back in the column: less like a hard refresh (D-127)
}

/**
 * @typedef {{pending: () => boolean, end: (how: "keep" | "discard") => unknown}} SessionOwner
 *   what opened a session: whether it has changes, and how to end it as its own Keep or Discard would
 */
/** @type {(SessionOwner & {name: string}) | null} the open session's owner */
let sessionOwner = null;

/**
 * End the open session, if any, as its own Keep or Discard would: with changes, ask Keep
 * changes / Discard changes / Cancel first (D-120); with none, quietly. False when
 * cancelled. @param {string} why the question's reason, before "<its name> ends first."
 */
async function endSession(why) {
  if (!(undoStack.session && sessionOwner)) return true;
  const other = sessionOwner;
  const choice = !other.pending() ? "keep" : await ask({
    title: `${other.name}: keep the changes?`,
    text: `${why} ${other.name} ends first.`,
    cancel: "cancel",
    buttons: [
      { label: "Discard changes", value: "discard", kind: "aside" },
      { label: "Cancel", value: "cancel" },
      { label: "Keep changes", value: "keep", kind: "primary" },
    ],
  });
  if (choice === "cancel") return false;
  await other.end(choice);
  return true;
}

/**
 * An edit session (Edit curve's, D-099; a Bias & headroom fix's, D-119), as a
 * transaction: Keep turns its edits into one undo step; Discard puts the circuit and the
 * Not saved chip back as they were and leaves no undo step. One at a time: with another
 * open, it asks Keep changes / Discard changes / Cancel first (D-120), or ends it quietly
 * when it has no changes. Null when cancelled.
 * @param {string} name what History calls it @param {string} source the `source` its own edits carry
 * @param {SessionOwner} owner
 */
async function editSession(name, source, owner) {
  if (!(await endSession(`${name} makes changes of its own, so`))) return null;
  if (undoStack.session) return null; // still open (it couldn't end): nothing to start
  const mark = undoStack.begin(name, source); // undo and redo stay inside the session until it ends (D-101)
  const circuit = state.circuit;
  const dirty = state.dirty;
  sessionOwner = { ...owner, name };
  historyView.update();
  return {
    /** @param {string} label */
    keep(label) {
      sessionOwner = null;
      undoStack.squash(mark, label);
      historyView.update();
    },
    async discard() {
      sessionOwner = null;
      undoStack.rollback(mark);
      historyView.update();
      if (state.circuit === circuit) return;
      await setCircuit(circuit);
      setDirty(dirty);
      if (!state.autorun) refresh(); // re-run, as a slider's release does
    },
    /** The session's steps so far, with the states before and after each (Edit curve's Changed list). */
    steps: () => undoStack.sessionSteps(state.circuit),
  };
}

/** @param {Source} source @param {boolean} [reload] the page's first open: large views put back by `restoreLargeViews` stay out */
async function open(source, reload = false) {
  showError(null);
  if (!reload) backToEditor();
  const token = openRequests.next();
  opening = hashOf(source);
  let view;
  try {
    view = await getJson(viewUrl(source));
  } finally {
    if (openRequests.isCurrent(token)) opening = "";
  }
  if (!openRequests.isCurrent(token)) return;
  if ((source.kind === "circuit" || source.kind === "block") && view.file?.link && view.file.link !== source.id) {
    source = { ...source, id: view.file.link }; // the current version goes by its short id (D-076)
    history.replaceState(history.state, "", hashOf(source));
  }
  state.source = source;
  state.file = source.kind === "copy" ? null : (view.file ?? null);
  state.run = state.part = state.sweep = state.knobLive = null;
  state.controls = {}; // another circuit: its knobs open where it says
  state.problems = null; // and its own problems: the last one's marks go
  schematic.showMarks([]);
  tools.clear();
  stages.clear(); // the last circuit's chain, card and lit parts go
  state.snapshots = { frequency: null, scope: null };
  audio.opened(); // the last circuit's take stops playing
  undoStack.clear();
  setDirty(false);
  show(view, { fit: true });
  const start = view.probes.out ?? Object.keys(view.nets)[0];
  await select(start ? { kind: "net", id: start } : null);
}

/**
 * Draw a circuit view and bring the panels in line with it.
 * @param {any} view @param {{fit: boolean}} opts
 */
function show(view, { fit }) {
  const controlsChanged = JSON.stringify(view.controls) !== JSON.stringify(state.view?.controls) || fit;
  // the knobs stay where they were turned, unless an edit moved their opening position (D-102)
  state.controls = keptControls(view.controls, state.view?.controls ?? [], state.controls);
  state.view = view;
  state.circuit = view.circuit;
  showTitle();
  schematic.capTypes = state.capTypes;
  schematic.draw(view, switchPositions(), { fit });
  if (state.problems?.result) showProblems(); // the circuit's dismissals may have changed (an undo)
  if (controlsChanged) {
    renderKnobs($("knobs-body"), view.controls, state.controls, onKnob, grabKnob, knobInUse);
    audio.update();
  }
  showOpening();
  audio.changed();
  notes.update();
  renameNote.update();
  power.show();
  updateButtons();
  document.body.dataset.views = String(++state.views);
}

/** @type {{circuit: any, key: string, played: any}} */
let playedCache = { circuit: null, key: "", played: null };

/**
 * The circuit as played (D-102): `state.circuit` holds the knobs' opening positions (what
 * is saved and undone); turning a knob only moves `state.controls`. Everything that
 * simulates or renders takes this. The same object until the circuit or a knob changes.
 */
function played() {
  if (!state.circuit) return state.circuit; // nothing open yet
  const key = JSON.stringify(state.controls);
  if (playedCache.circuit !== state.circuit || playedCache.key !== key) {
    playedCache = { circuit: state.circuit, key, played: withControls(state.circuit, state.view?.controls ?? [], state.controls) };
  }
  return playedCache.played;
}

/** The knobs as they are now, made the circuit's opening positions: one edit, undoable. */
async function useAsOpening() {
  const message = await tryEdit(withControls(state.circuit, state.view.controls, state.controls), "Knob opening positions");
  if (message) showError(message);
}

/** "Use as opening positions": shown with knobs, enabled once one is away from where the circuit opens it. */
function showOpening() {
  const button = /** @type {HTMLButtonElement} */ ($("knobs-opening"));
  const controls = state.view?.controls ?? [];
  button.hidden = !controls.length;
  button.disabled = controls.every((/** @type {any} */ c) => state.controls[c.ref] === openingOf(c));
}

/** Each switch pole's position, by part ref: a switch's knob turns all its poles (D-143). */
function switchPositions() {
  const switches = state.view.controls.filter((/** @type {any} */ c) => c.kind === "switch");
  return Object.fromEntries(switches.flatMap((/** @type {any} */ c) => (c.refs ?? [c.ref]).map((/** @type {string} */ r) => [r, state.controls[c.ref]])));
}

/** @param {boolean} dirty */
function setDirty(dirty) {
  state.dirty = dirty;
  showTitle();
}

/** True when the open thing is a block (one of mine, a core one, or an unsaved copy). */
const isBlock = () => state.source?.kind === "block" || state.source?.kind === "copy" || state.file?.kind === "block";

/**
 * The name at the top and its badges (D-075): BLOCK, the version tag, read-only (starter,
 * core, final), and Not saved / Never saved. The tab title starts with • when unsaved.
 */
function showTitle() {
  const c = state.circuit;
  if (!c) return;
  const file = state.file;
  const never = state.source?.kind === "copy" || (state.source?.kind === "new" && state.dirty);
  $("circuit-name").textContent = c.name;
  $("circuit-name").title = c.name;
  const badges = [];
  if (isBlock()) badges.push(h("span", { class: "badge block" }, ["Block"]));
  if (file) badges.push(h("span", { class: "badge version", title: "Version: major.minor (the minor counts saves)" }, [versionTag(c)]));
  // a starter's badge is short (the header is tight); its tooltip says what it is
  if (file?.readonly) badges.push(h("span", { class: "badge readonly", title: files.readonlyReason() ?? "" }, [file.layer === "core" ? "core \u00b7 read-only" : file.layer === "starter" ? "read-only" : "final \u00b7 read-only"]));
  $("badges").replaceChildren(...badges);
  $("dirty").hidden = !(state.dirty || never);
  $("dirty").textContent = never ? "Never saved" : "Not saved";
  document.title = `${state.dirty ? "\u2022 " : ""}${c.name} \u00b7 Solum Builder`;
}

// ---- editing ---------------------------------------------------------------------

/**
 * Apply an edit: record it for undo, get the new view from the server, redraw, re-run.
 * A circuit the server refuses (e.g. a bad value) is rolled back with its message shown.
 * @param {any} next @param {string} label @param {any} [view] already fetched for `next`
 */
/**
 * @param {any} next @param {string} label @param {any} [view] @param {string} [source] "curve": made in Edit curve
 * @param {boolean} [now] with Auto-run on, re-run at once (`setCircuit`)
 */
async function edit(next, label, view, source = "", now = false) {
  if (!next || next === state.circuit) return;
  undoStack.record(state.circuit, label, source, state.selection);
  await setCircuit(next, view, () => undoStack.discard(), undefined, now);
}

/**
 * Show `next` (from an edit, undo or redo). `restore`: an undo's or redo's selection, the
 * one that went with `next` (D-148); without it the selection is kept where it can be.
 * @param {any} next @param {any} [view] @param {() => void} [onRefused]
 * @param {{selection: any}} [restore]
 * @param {boolean} [now] with Auto-run on, re-run at once: a single edit (a form's Apply, a
 *   slider let go), not one of a burst (a drag, a held key), which wait for a pause (D-283)
 */
async function setCircuit(next, view, onRefused, restore, now = false) {
  const before = state.circuit;
  state.circuit = next;
  state.sweep = null;
  state.knobLive = null;
  state.edits++;
  tools.circuitChanged(); // Edit curve asks for the new nudges alongside the run
  setDirty(true);
  updateButtons();
  const token = viewRequests.next();
  try {
    view ??= await postJson("api/view", { circuit: next });
    if (!viewRequests.isCurrent(token)) return;
  } catch (err) {
    if (!viewRequests.isCurrent(token)) return;
    onRefused?.();
    state.circuit = before;
    updateButtons();
    showError(/** @type {Error} */ (err).message);
    return;
  }
  show(view, { fit: false });
  if (restore) restoreSelection(restore.selection);
  else keepSelection(before);
  if (state.autorun && now) void refresh();
  else if (state.autorun) rerunAfterEdit();
  else setStale(true);
}

/** Results no longer match the circuit (an edit with auto-run off): say so on Run and the panels. @param {boolean} stale */
function setStale(stale) {
  state.stale = stale;
  $("run").classList.toggle("stale", stale);
  $("stale").hidden = !stale;
  $("power-draw").classList.toggle("stale", stale);
}

/** The Run button: simulate the circuit as it is now, at the probed point (or the output). */
function run() {
  if (!state.selection && state.view?.probes.out) return select({ kind: "net", id: state.view.probes.out });
  return refresh();
}

/** @param {boolean} on run after every edit (remembered with the preferences; off by default, D-065) */
function setAutorun(on) {
  state.autorun = on;
  /** @type {HTMLInputElement} */ ($("autorun")).checked = on;
  remember(AUTORUN_KEY, on ? 1 : 0);
  if (on && state.stale) refresh();
}

/** After an edit, keep the selection if it still exists; otherwise fall back to the output. */
/**
 * Let go of a selection of parts or wires: back to probing the output, as a click on
 * empty space does, without a run of its own (the edit that follows runs). Any left-click
 * action other than moving the selection does this, so a selection never ends up half
 * kept, its parts still selected and its wires not (the user, D-095). A probed net stays.
 */
function clearSelection() {
  const kind = state.selection?.kind;
  if (kind !== "items" && kind !== "part") return;
  state.selection = outputSelection();
  schematic.select(state.selection);
  updateButtons();
}

/**
 * Put back the selection that went with an undone or redone circuit (D-148): it was made
 * on that very circuit, so it names the same parts, wires and labels. Nothing selected
 * then: the output's net is probed, as on opening.
 * @param {any} selection
 */
function restoreSelection(selection) {
  state.selection = selection ?? outputSelection();
  schematic.select(state.selection);
  updateButtons();
}

/** @param {any} before the circuit before the edit */
function keepSelection(before) {
  const sel = state.selection;
  const fallback = outputSelection();
  if (!sel) return;
  /** label `i` is the one it was: same place, same name (turned, it's still it) @param {number} i */
  const sameLabel = (i) => {
    const [was, now] = [before?.labels?.[i], state.circuit.labels?.[i]];
    return Boolean(was && now && was.net === now.net && String(was.pos) === String(now.pos));
  };
  if (sel.kind === "items") {
    // keep the parts still here (an inserted block stays whole through a Power change)
    const refs = new Set(state.view.parts.map((/** @type {any} */ p) => p.ref));
    const items = /** @type {import("./schematic/render.js").Items} */ (sel.items);
    const parts = items.parts.filter((r) => refs.has(r));
    const texts = (items.texts ?? []).filter((i) => i < (state.view.texts ?? []).length);
    // wires and labels still at their place in the lists (a Power change leaves them all)
    const kept = (/** @type {string} */ key) => (/** @type {number} */ i) => {
      const was = before?.[key]?.[i];
      return was !== undefined && JSON.stringify(was) === JSON.stringify(state.circuit[key]?.[i]);
    };
    const wires = items.wires.filter(kept("wires"));
    const labels = items.labels.filter(sameLabel);
    state.selection = parts.length || texts.length || wires.length || labels.length ? { kind: "items", id: "", items: { parts, wires, labels, texts } } : fallback;
  } else if (sel.kind === "part" && !state.view.parts.some((/** @type {any} */ p) => p.ref === sel.id)) state.selection = fallback;
  else if (sel.kind === "net" && !(sel.id in state.view.nets)) state.selection = fallback;
  else if (sel.kind === "net") {
    // wire indices may have moved; a label still where it was, by the same name, stays
    // picked, so Space turns a supply again and again (the user, D-164)
    state.selection = { kind: "net", id: sel.id, ...(sel.label !== undefined && sameLabel(sel.label) ? { label: sel.label } : {}) };
  }
  schematic.select(state.selection);
}

const rerunAfterEdit = debounce(() => refresh(), EDIT_DEBOUNCE_MS);

function undo() {
  if (undoStack.atSessionStart) return historyView.note("This is where you started editing the curve: Keep or Discard to undo further back.");
  const prev = undoStack.undo(state.circuit, state.selection);
  if (prev) setCircuit(prev, undefined, undefined, { selection: undoStack.restored }).then(sessionRerun);
}

function redo() {
  const next = undoStack.redo(state.circuit, state.selection);
  if (next) setCircuit(next, undefined, undefined, { selection: undoStack.restored }).then(sessionRerun);
}

/** In Edit curve, undo and redo re-run as its drags do, Auto-run or not (the curve is the point). */
function sessionRerun() {
  if (undoStack.session && !state.autorun) refresh();
}

/** Go that many steps through the undo list at once (+ redo, − undo): the History pane's click. @param {number} steps */
function goHistory(steps) {
  let c = state.circuit;
  let selection = state.selection;
  for (let k = 0; k < Math.abs(steps); k++) {
    const next = steps > 0 ? undoStack.redo(c, selection) : undoStack.undo(c, selection);
    if (!next) break;
    [c, selection] = [next, undoStack.restored];
  }
  if (c !== state.circuit) setCircuit(c, undefined, undefined, { selection }).then(sessionRerun);
}


const HINTS = {
  normal: "Drag parts in from the left. Wire tool: click to start, click to bend, click a pin to finish. Drag a ball to move a wire end. Click to probe, double-click to edit.",
  wiring: "Click to start a wire anywhere, click again for each bend, click a pin, label or wire to finish, or click the last point again to end it there. Esc or right-click drops it; Esc again leaves the tool.",
};

// the canvas hint is one line, so the canvas never resizes as it changes: cut short, it's
// whole in its tooltip
new MutationObserver(() => ($("hint").title = $("hint").textContent ?? "")).observe($("hint"), { childList: true, characterData: true, subtree: true });

/** Keep the palette's Wire tile and the canvas hint in step with wire mode (menus read state when opened). */
function updateButtons() {
  historyView.update(); // an open History pane follows every change
  document.querySelector('[data-tool="wire"]')?.setAttribute("aria-pressed", String(schematic.wireMode));
  hint(schematic.wireMode ? HINTS.wiring : HINTS.normal);
}

/** What Delete would remove: the selected part, or the clicked wire or label; never the
 * circuit's guitar input or amp (D-146). */
function deletable() {
  const sel = state.selection;
  if (!sel) return null;
  const fixed = fixedRefs(state.circuit);
  if (sel.kind === "items") {
    const items = sel.items;
    if (!items) return null;
    const kept = { ...items, parts: items.parts.filter((r) => !fixed.has(r)) };
    return kept.parts.length || kept.wires.length || kept.labels.length || kept.texts?.length ? kept : null;
  }
  if (sel.kind === "part") return fixed.has(sel.id) ? null : { parts: [sel.id] };
  if (sel.wire !== undefined) return { wires: sel.run ?? [sel.wire] };
  if (sel.label !== undefined) return { labels: [sel.label] };
  return null;
}

async function deleteSelection() {
  let what = deletable();
  const fixed = [...fixedRefs(state.circuit)].filter((r) => state.selection?.id === r || state.selection?.items?.parts.includes(r));
  // said after the edit, whose redraw puts the usual hint back
  const kept = () => {
    if (fixed.length) hint(`${fixed.join(" and ")} ${fixed.length > 1 ? "stay" : "stays"}: every circuit has a guitar input and an amp.`);
  };
  if (!what) return kept();
  // half of a chip, a pole of a switch or a gang of a dual pot deletes all of it, once you say so (D-140, D-143, D-217)
  const parts = withChips(state.circuit, what.parts ?? []);
  const added = parts.filter((ref) => !what?.parts?.includes(ref));
  if (added.length) {
    const grouped = parts.filter((ref) => groupRefs(state.circuit, ref).length > 1);
    const chips = [...new Set(grouped.map((ref) => ref.slice(0, -1)))];
    const units = grouped.map((ref) => partOf(ref)?.type);
    const switches = units.includes("switch");
    const pots = !switches && units.includes("pot");
    const [one, piece] = switches ? ["switch", "a pole"] : pots ? ["pot", "a gang"] : ["chip", "a half"];
    const sure = await confirmed(
      `Delete ${chips.join(" and ")}?`,
      `${chips.length > 1 ? `Each is one ${one}` : `${chips[0]} is one ${one}`}: deleting ${piece} deletes the ${one}, so ${added.join(" and ")} ${added.length > 1 ? "go" : "goes"} too.`,
      `Delete ${chips.length > 1 ? `the ${one === "switch" ? "switches" : `${one}s`}` : chips[0]}`,
      "delete",
    );
    if (!sure) return;
    what = { ...what, parts };
  }
  const count = (what.parts?.length ?? 0) + (what.wires?.length ?? 0) + (what.labels?.length ?? 0) + (what.texts?.length ?? 0);
  const oneWire = state.selection?.kind === "net"; // a wire clicked: all of it, bends and all
  const label = oneWire ? "Delete wire" : count > 1 ? `Delete ${count} items` : what.parts?.length ? `Delete ${what.parts[0]}` : what.wires?.length ? "Delete wire" : what.labels?.length ? "Delete label" : "Delete text";
  await edit(deleteItems(state.circuit, what), label);
  kept();
}

function rotate() {
  if (state.placing) return schematic.rotateGhost();
  const sel = state.selection;
  if (sel?.kind === "part") edit(rotatePart(state.circuit, sel.id), `Rotate ${sel.id}`);
  // a supply's symbol (ground, V+, V-) turns too; a plain label's name finds its own side
  const label = sel?.kind === "items" && sel.items?.labels.length === 1 && !sel.items.parts.length && !sel.items.wires.length ? sel.items.labels[0] : sel?.label;
  if (label !== undefined && isSupplyLabel(label)) edit(rotateLabel(state.circuit, label), `Rotate ${state.circuit.labels[label].net}`);
}

/**
 * Whether label `index` is drawn as a supply's symbol: ground, a rail, a chip's supply or a
 * pump's output (the drawing's own test). @param {number} index
 */
function isSupplyLabel(index) {
  const net = state.circuit?.labels?.[index]?.net;
  return net !== undefined && Boolean(state.view) && supplyKind(state.view, net) !== null;
}

/** @param {string} type a palette part type, "label:<net>", or "supply:<net>" (a Supply tile) */
function startPlacing(type) {
  closeForm();
  setWireMode(false);
  state.placing = type;
  if (type.startsWith("label:") || type.startsWith("supply:")) {
    const net = type.slice(type.indexOf(":") + 1);
    const supply = net === "GND" ? "ground" : type.startsWith("supply:") || net in (state.circuit.power?.rails ?? {}) ? "rail" : undefined;
    schematic.startPlacing({ label: net, rot: 0, ...(supply ? { supply } : {}) });
  }
  else if (type === "text") schematic.startPlacing({ text: { title: "Text" }, rot: 0 }); // the editor opens on the click
  else schematic.startPlacing({ part: { type: paletteEntry(type)?.type ?? type, pins: [], draw: {} }, rot: 0 });
  for (const b of document.querySelectorAll("[data-place]")) b.classList.toggle("active", b.getAttribute("data-place") === type);
  document.querySelector('[data-tool="ground"]')?.classList.toggle("active", type === "label:GND");
  for (const t of document.querySelectorAll('[data-tool="supply"]')) t.classList.toggle("active", type === `supply:${t.getAttribute("data-net")}`);
  document.querySelector('[data-tool="text"]')?.classList.toggle("active", type === "text");
  updateButtons();
}

function stopPlacing() {
  state.placing = null;
  state.placingBlock = null;
  schematic.stopPlacing();
  for (const b of document.querySelectorAll(".tile.active")) b.classList.remove("active");
  updateButtons();
}

/** @param {number[]} pos @param {number} [wire] the wire it was dropped on (a block splices into it) */
async function place(pos, wire) {
  const type = state.placing;
  if (!type) return;
  const rot = schematic.ghost?.rot ?? 0;
  const block = state.placingBlock;
  stopPlacing();
  if (type === "block" && block) return dropBlock(block, pos, wire);
  if (type.startsWith("label:")) {
    await edit(addLabel(state.circuit, type.slice(6), pos, rot), `Add label ${type.slice(6)}`);
    return;
  }
  if (type.startsWith("supply:")) {
    await edit(addSupply(state.circuit, type.slice(7), pos, rot), `Add supply ${type.slice(7)}`);
    return;
  }
  if (type === "text") return textEditor(null, pos);
  const { circuit, ref } = addPart(state.circuit, type, pos, rot, state.models);
  await edit(circuit, `Add ${ref}`);
  await select({ kind: "part", id: ref });
}

/** @param {boolean} on */
function setWireMode(on) {
  if (on) stopPlacing();
  schematic.setWireMode(on);
  updateButtons();
}

/** Find part (Ctrl+F): type a ref, the part is selected (probed), brought into view and ringed. */
function findPart() {
  openForm($("canvas-body"), {
    title: "Find part",
    fields: [{ name: "ref", label: "Ref", kind: "text", value: "", hint: "e.g. R12, C3, Q1" }],
    submit: "Find",
    onSubmit: async (values) => {
      const ref = findRef(state.circuit, values.ref);
      if (!ref) return values.ref.trim() ? `There's no part ${values.ref.trim().toUpperCase()} on this sheet.` : "Type a part's ref, e.g. R12.";
      schematic.reveal(ref);
      select({ kind: "part", id: ref });
      return null;
    },
  });
}

function askLabel() {
  openForm($("canvas-body"), {
    title: "Net label",
    subtitle: "then click where it goes",
    fields: [{ name: "net", label: "Name", kind: "text", value: state.lastLabel, hint: "Same name anywhere = same net. GND is ground; supplies (V+, V-) come from the Supply tiles and Power \u2192 Custom\u2026." }],
    submit: "Place",
    onSubmit: async (values) => {
      const net = values.net.trim();
      if (!net) return "Give the label a name.";
      state.lastLabel = net;
      startPlacing(`label:${net}`);
      return null;
    },
  });
}

/** @param {number} index */
function editLabel(index) {
  const label = state.circuit.labels[index];
  if (!label) return;
  openForm($("canvas-body"), {
    title: "Net label",
    fields: [{ name: "net", label: "Name", kind: "text", value: label.net }],
    onSubmit: async (values) => {
      const net = values.net.trim();
      if (!net) return "Give the label a name.";
      const next = renameLabel(state.circuit, index, net);
      const message = await tryEdit(next, `Rename label to ${net}`);
      // the net's last label renamed renames the net: offer to update the notes (9d4)
      if (!message && net !== label.net && !next.labels.some((/** @type {any} */ lb) => lb.net === label.net)) renameNote.show([{ from: label.net, to: net }]);
      return message;
    },
  });
}

/**
 * Check an edit with the server first; apply it only if it's accepted.
 * @param {any} next @param {string} label @param {string} [source] "curve": made in Edit curve
 * @returns {Promise<string | null>} the error, if refused
 */
async function tryEdit(next, label, source = "") {
  let view;
  try {
    view = await postJson("api/view", { circuit: next });
  } catch (err) {
    return /** @type {Error} */ (err).message;
  }
  await edit(next, label, view, source, true); // checked first, so one edit on its own: no wait
  sessionRerun(); // in Edit curve, Auto-run off: re-run as undo does, so it shows Keep and Discard
  return null;
}

// ---- live curves (D-081) -------------------------------------------------------------

/** The Frequency plot's axes, and how its hover readout writes values (frequencies come as text from the server). */
const FREQUENCY_PLOT = { log: true, xLabel: "Hz", yLabel: "dB", hover: { x: (/** @type {number} */ f) => `${Math.round(f)} Hz`, y: db } };
/** Parts whose view plots the response on each of their sides (D-173: an inductor as a capacitor). */
const SIDED = new Set(["capacitor", "inductor"]);
const SCOPE_PLOT = { xLabel: "ms", yLabel: "V", hover: { x: (/** @type {number} */ t) => `${t.toFixed(2)} ms`, y: (/** @type {number} */ v) => volts(v, 3) } };

/** The selected capacitor's or inductor's two sides, when it has curves. @returns {string[] | null} */
function capacitorSides() {
  const curves = SIDED.has(state.part?.type) ? state.part.detail?.curves : null;
  return curves ? Object.keys(curves.nodes) : null;
}

/** The nets the Frequency panel shows for the selection: a capacitor's two sides, else the net; and the output. */
function frequencyNets() {
  return [...new Set([...(capacitorSides() ?? [currentNet()]), state.view.probes.out].filter(Boolean))];
}

/**
 * What a slider needs to redraw the Frequency curve while it moves.
 * @param {Array<{ref: string, field: string}>} controls @param {Record<string, any[]>} [steps] value steps to keep
 * @param {any} [circuit] the circuit as played (a hand-turned trimmer's without its target)
 * @returns {Promise<import("./live.js").Live>}
 */
function fetchLive(controls, steps = {}, circuit = played()) {
  return postJson("api/live", { circuit, nets: frequencyNets(), controls, steps });
}

/**
 * Redraw the Frequency plot from the browser's solve; its readings wait for ngspice.
 * @param {import("./live.js").Live} live @param {Record<string, number>} values
 */
function drawLive(live, values) {
  if (!state.run?.ac) return;
  const curves = liveCurves(live, values);
  if (!curves) return;
  const ac = { ...curves, freq_text: state.run.ac.freq_text }; // the live grid is the run's (D-081)
  const sides = capacitorSides();
  const out = state.view.probes.out;
  const data = sides
    ? capacitorSeries({ ...ac, nodes: Object.fromEntries(sides.map((n) => [n, ac.nodes[n]])) }, { ac }, out)
    : frequencySeries({ ac }, currentNet(), out, state.snapshots.frequency);
  if (!data) return;
  liveLinePlot($("frequency-plot"), data, { ...FREQUENCY_PLOT, ...tools.plotOpts(data, true) });
  $("frequency-readings").classList.add("stale");
  const read = ac.nodes[tools.net()];
  if (read) tools.live(ac.freq, read); // knees, peaks and readings follow, measured on the server (D-097)
  audio.setCurve(outputCurve(ac));
}

/**
 * A knob was grabbed: fetch its live system so the curve follows the drag (D-081).
 * @param {string} ref
 */
/**
 * A knob or switch in use (hovered, held, turned from the keys; null: no longer): its
 * part lit on the canvas, so it's easy to find (D-127), and its band shaded on the curve.
 * @param {string | null} ref
 */
function knobInUse(ref) {
  const control = ref ? state.view?.controls.find((/** @type {any} */ c) => c.ref === ref) : null;
  schematic.highlight(ref ? control?.refs ?? [ref] : []); // a switch's poles, a dual pot's gangs (D-217)
  void tools.knobHover(ref);
}

async function grabKnob(ref) {
  const control = state.view.controls.find((/** @type {any} */ c) => c.ref === ref);
  if (control?.kind !== "pot" || state.knobLive?.ref === ref || !state.run?.ac) return;
  const edits = state.edits;
  try {
    const live = await fetchLive([{ ref, field: "rotation" }]);
    // knob moves since the grab are fine (the steps carry their own values); an edit isn't
    if (state.edits === edits) {
      state.knobLive = { ref, live };
      document.body.dataset.knobLive = ref; // for tests: the curve now follows this knob
    }
  } catch {
    // no live curve for this knob (e.g. a trimmer set by its bias target): the knob still re-runs
  }
}

/**
 * Run "try several values" and overlay the results.
 * @param {string} ref @param {string} field @param {string[]} values
 * @returns {Promise<string | null>} the error, if any
 */
async function runSweep(ref, field, values) {
  document.body.dataset.busy = "true";
  try {
    state.sweep = await postJson("api/sweep", { circuit: played(), ref, field, values, nodes: [currentNet()], level: state.level });
    const netSelect = /** @type {HTMLSelectElement} */ ($("sweep-net"));
    netSelect.replaceChildren(...state.sweep.nodes.map((/** @type {string} */ n, /** @type {number} */ i) => new Option(i === state.sweep.nodes.length - 1 && n === state.view.probes.out ? `${n} (output)` : n, n)));
    // probed on a supply or ground there's no signal to compare: show the output instead
    const probed = state.sweep.nodes[0];
    const out = state.view.probes.out;
    if (out && state.sweep.nodes.includes(out) && (probed === "GND" || state.view.nets[probed]?.rail)) netSelect.value = out;
    // with auto-run off there may be no run yet: make one, so the overlay has panels to go in
    if (!state.run || state.stale) await refresh();
    else render(currentNet());
    return null;
  } catch (err) {
    return /** @type {Error} */ (err).message;
  } finally {
    document.body.dataset.busy = "false";
    document.body.dataset.updates = String(++state.updates);
  }
}
/**
 * The text block editor (D-091): a title and the text. With `index` null it's a new
 * block at `pos` (placed first, then written; Cancel places nothing); otherwise it edits
 * that block, and emptying both removes it.
 * @param {number | null} index @param {number[]} [pos]
 */
function textEditor(index, pos) {
  const block = index === null ? { title: "", text: "" } : state.circuit.texts?.[index];
  if (!block) return;
  openForm($("canvas-body"), {
    title: "Text",
    subtitle: index === null ? "new" : "",
    fields: [
      { name: "title", label: "Title", kind: "text", value: block.title ?? "", hint: "Optional, drawn in bold." },
      { name: "text", label: "Text", kind: "textarea", value: block.text ?? "", hint: index === null ? "A note on the sheet, saved with the circuit (it isn't part of the circuit). Ctrl+Enter applies." : "Empty title and text remove it. Ctrl+Enter applies." },
    ],
    submit: index === null ? "Add" : "Apply",
    onSubmit: async (values) => {
      if (index !== null) return tryEdit(setText(state.circuit, index, values), values.title.trim() || values.text.trim() ? "Edit text" : "Delete text");
      if (!values.title.trim() && !values.text.trim()) return "Give it a title or some text.";
      const at = (state.circuit.texts ?? []).length;
      const message = await tryEdit(addText(state.circuit, values, /** @type {number[]} */ (pos)), "Add text");
      if (!message) selectItems({ parts: [], wires: [], labels: [], texts: [at] });
      return message;
    },
  });
}

// ---- blocks (D-072) --------------------------------------------------------------

/** Select several items (a box, Ctrl+A, a pasted block). @param {import("./schematic/render.js").Items} items */
function selectItems(items) {
  if (isEmpty(items)) return select(null);
  state.selection = { kind: "items", id: "", items };
  schematic.select(state.selection);
  updateButtons();
}

/**
 * The selection as items, for Ctrl+click and Ctrl+Shift+drag to build on: a selected part,
 * or the wire or label clicked to probe a net, counts as one item (D-092).
 * @returns {import("./schematic/render.js").Items}
 */
function currentItems() {
  const sel = state.selection;
  if (sel?.kind === "items" && sel.items) return sel.items;
  if (sel?.kind === "part") return { parts: [sel.id], wires: [], labels: [] };
  if (sel?.kind === "net" && sel.wire !== undefined) return { parts: [], wires: sel.run ?? [sel.wire], labels: [] };
  if (sel?.kind === "net" && sel.label !== undefined) return { parts: [], wires: [], labels: [sel.label] };
  return { parts: [], wires: [], labels: [] };
}

/** What the selection holds as items (a single part counts), or null. */
function selectedItems() {
  const sel = state.selection;
  if (sel?.kind === "items" && sel.items && !isEmpty(sel.items)) return sel.items;
  if (sel?.kind === "part") return { parts: [sel.id], wires: [], labels: [] };
  return null;
}

/**
 * Start placing a block: its ghost follows the pointer; a click drops it (on a wire, it's
 * spliced in). @param {any} block a circuit @param {any} view its view @param {string} name
 * @param {{from: string, version: string}} [source]
 */
function startPlacingBlock(block, view, name, inserted = false) {
  stopPlacing();
  setWireMode(false);
  state.placing = "block";
  state.placingBlock = { circuit: block, name, inserted };
  schematic.startPlacing({ block: { parts: view.parts, wires: view.wires, labels: view.labels, texts: block.texts ?? [], nets: view.nets, anchor: blockAnchor(block) }, rot: 0 });
  hint(`Click to drop ${name}; click a wire to splice it in. It moves aside if it would touch something. Esc cancels.`);
}

/**
 * Drop the block being placed at `pos` (spliced into `wire` when dropped on one), then
 * select it (parts, wires, labels and text) so it can be dragged into place.
 * @param {{circuit: any, name: string, inserted: boolean}} block
 * @param {number[]} pos @param {number} [wire]
 */
async function dropBlock(block, pos, wire) {
  let pasted;
  try {
    pasted = pasteBlock(state.circuit, block.circuit, { at: pos, ...(wire !== undefined ? { splice: wire } : {}) });
  } catch (err) {
    showError(/** @type {Error} */ (err).message);
    return;
  }
  await edit(pasted.circuit, `${block.inserted ? "Insert" : "Paste"} ${block.name}`);
  if (pasted.skipped.length) hint(`Left out ${pasted.skipped.join(" and ")}: a circuit has one guitar input and one amp.`);
  const refs = Object.values(pasted.refs);
  const here = new Set(state.circuit.parts.map((/** @type {any} */ p) => p.ref));
  if (!refs.every((r) => here.has(r))) return; // refused
  // its wires and labels too, found where they went in the server's copy, so a drag right
  // after takes all of it (the user, D-095)
  const { wires, spots, texts } = pasted.placed;
  selectItems({ parts: refs, ...itemsAt(state.circuit, wires, spots), ...(texts.length ? { texts } : {}) });
}

/** Ctrl+C: take the selection (or the selected part) as a block to paste. */
function copy() {
  const items = selectedItems();
  if (!items) return;
  state.clipboard = extract(state.circuit, state.view, items);
}

/** Whether Ctrl+V has something to place: parts, or text blocks alone (D-164). */
const canPaste = () => Boolean(state.clipboard?.parts.length || state.clipboard?.texts?.length);

/** What the hint calls a pasted block: its parts, else its text blocks. @param {any} block */
function pastedName(block) {
  const [n, what] = block.parts.length ? [block.parts.length, "part"] : [block.texts.length, "text block"];
  return `${n} ${what}${n > 1 ? "s" : ""}`;
}

/** Ctrl+V: place what was copied (from this circuit or another). */
async function paste() {
  const block = state.clipboard;
  if (!canPaste()) return;
  try {
    const view = await postJson("api/view", { circuit: block });
    startPlacingBlock(block, view, pastedName(block));
  } catch (err) {
    showError(/** @type {Error} */ (err).message);
  }
}

// ---- the open file (its dialogs are file-dialogs.js) -------------------------------

/** Re-read the open file's details (path, when saved) after the server changed it. */
async function refreshFile() {
  if (state.source?.kind !== "circuit" && state.source?.kind !== "block") return;
  const view = await getJson(viewUrl(state.source));
  state.file = view.file ?? null;
  state.circuit = { ...state.circuit, version: view.circuit.version, final: view.circuit.final };
  showTitle();
}

/**
 * The open circuit after a save: the server's name, id and version, and its link when the
 * name changed (the files followed the name). `renamed`: only the name was saved (the
 * pencil, D-287): unsaved changes stay unsaved, and every undo step takes the new name
 * and id, so none puts the old name back.
 * @param {import("./file-dialogs.js").Saved} saved @param {{renamed?: boolean}} [opts]
 */
async function afterSave(saved, { renamed = false } = {}) {
  const src = /** @type {Source} */ (state.source);
  if (saved.link !== src.id) {
    state.source = { ...src, id: saved.link };
    history.replaceState(history.state, "", hashOf(state.source));
  }
  state.circuit = { ...state.circuit, id: saved.id, name: saved.name, version: parseTag(saved.version) };
  if (renamed) undoStack.amend((/** @type {any} */ c) => ({ ...c, id: saved.id, name: saved.name }));
  setDirty(renamed && state.dirty);
  await refreshFile();
}

// ---- probing and panels ----------------------------------------------------------

/** @param {Selection | null} selection */
async function select(selection) {
  state.selection = selection;
  state.knobLive = null; // its curves were for the old selection's nets
  schematic.select(selection);
  updateButtons();
  if (selection && !selection.id) return; // a loose wire: selected for Delete, nothing to probe
  state.selecting = refresh();
  await state.selecting;
}

/**
 * The Problems panel (D-077): re-checked only when the circuit changed, so clicking a
 * problem (which probes it) keeps the list as it is.
 */
async function checkProblems() {
  const circuit = played();
  if (!circuit || state.problems?.circuit === circuit) return;
  state.problems = { circuit, result: null };
  const token = problemRequests.next();
  try {
    const result = await postJson("api/problems", { circuit });
    if (!problemRequests.isCurrent(token)) return;
    state.problems = { circuit, result };
  } catch (err) {
    if (problemRequests.isCurrent(token)) state.problems = { circuit, result: { problems: [], checked_op: false, error: /** @type {Error} */ (err).message } };
  }
  showProblems();
}

function showProblems() {
  const result = state.problems?.result ?? null;
  const body = $("problems-body");
  if (result?.error) {
    body.replaceChildren(emptyNote(`Couldn't check for problems: ${result.error}`));
    $("problem-count").textContent = "";
    return;
  }
  const count = renderProblems(body, result, (p) => {
    const target = problemTarget(p);
    if (target) select(target);
  }, state.openProblems, { dismissed: state.circuit?.dismissed, onDismiss: dismissDialog, onRestore: (p) => problemEdit(restoreProblem(state.circuit, p), "Bring back problem") });
  $("problem-count").textContent = count ? `\u00b7 ${count}` : "";
  schematic.showMarks(state.marks && result ? result.problems : []);
}

/**
 * A problem's mark clicked (D-176): its row in the Problems panel, opened and in view.
 * @param {string} key `problemKey`
 */
function openProblem(key) {
  const panel = /** @type {HTMLDetailsElement} */ ($("panel-problems"));
  panel.open = true;
  state.openProblems.add(key);
  showProblems();
  const row = [...$("problems-body").querySelectorAll("details.problem")].find((r) => /** @type {HTMLElement} */ (r).dataset.key === key);
  row?.scrollIntoView({ block: "nearest" });
}

/**
 * Dismiss a problem, with an optional reason typed in a popup (D-176).
 * @param {import("./problems.js").Problem} problem
 */
function dismissDialog(problem) {
  openForm($("canvas-body"), {
    title: "Dismiss problem",
    subtitle: problem.title,
    fields: [{ name: "reason", label: "Reason", kind: "text", value: "", hint: "Optional: why it's fine here. Kept with the circuit." }],
    submit: "Dismiss",
    onSubmit: (values) => problemEdit(dismissProblem(state.circuit, problem, values.reason), "Dismiss problem"),
  });
}

/**
 * Dismiss or bring back a problem: an edit like any other (undo, saved with the circuit),
 * but nothing the simulation sees changed, so the problems found and the results stay as
 * they are (no re-check, not stale).
 * @param {any} next @param {string} label @returns {Promise<string | null>} a message, or null when done
 */
async function problemEdit(next, label) {
  const checked = state.problems?.circuit === played() ? state.problems : null;
  const stale = state.stale;
  const message = await tryEdit(next, label);
  if (message) return message;
  if (checked) checked.circuit = played();
  if (!state.autorun) setStale(stale);
  return null;
}

/** Runs what the current selection needs; drops answers that a newer request replaced. */
/** @type {Array<() => void>} waiting for the next run to end (`ranAgain`) */
const afterRun = [];

/**
 * The re-run after an edit, ended: run now with auto-run off, or wait for auto-run's (a
 * slider ignores the arrow keys till then: a press at a time, each drawn, round 2).
 * @returns {Promise<void>}
 */
function ranAgain() {
  const ended = new Promise((resolve) => afterRun.push(() => resolve(undefined)));
  if (!state.autorun) void refresh();
  return ended;
}

/** Run the circuit at the selection and draw every pane. */
async function refresh() {
  try {
    await runSelected();
  } finally {
    for (const f of afterRun.splice(0)) f();
  }
}

async function runSelected() {
  const sel = state.selection;
  if (!sel || !state.circuit) return;
  // a group selected (a pasted block, a box) runs at the net shown last, else the output:
  // an edit made with one selected still runs (the user, 2026-11-10: a block's DC voltages)
  const shown = sel.id || (state.view?.nets[state.shownNet] ? state.shownNet : state.view?.probes.out);
  if (!shown) return;
  if (!isUnwired(state.circuit)) checkProblems();
  if (state.view?.problem) {
    showError(state.view.problem);
    return;
  }
  setStale(false);
  if (isUnwired(state.circuit)) return showUnwired();
  const token = requests.next();
  document.body.dataset.busy = "true";
  // one circuit for both requests: an edit between them (a Delete) would leave the part's
  // pin probed on a circuit without the part
  const circuit = played();
  try {
    let part = null;
    let net = shown;
    if (sel.kind === "part") {
      part = await postJson("api/part", { circuit, ref: sel.id, level: state.level });
      if (!requests.isCurrent(token)) return;
      net = focusNet(part);
    }
    const run = await postJson("api/run", { circuit, nodes: [net], level: state.level });
    if (!requests.isCurrent(token)) return;
    state.run = run;
    state.part = part;
    state.shownNet = net;
    showError(null);
    render(net);
    forms.showTargetRotation();
    stagesMeasuring = stages.refresh().catch(() => {});
  } catch (err) {
    if (requests.isCurrent(token)) {
      showError(/** @type {Error} */ (err).message);
      // the pane is about what's selected: say it has no readings and why (D-318)
      if (sel.id) renderProbeFailed($("probe-body"), sel.id, /** @type {Error} */ (err).message);
    }
  } finally {
    if (requests.isCurrent(token)) {
      document.body.dataset.busy = "false";
      document.body.dataset.updates = String(++state.updates);
    }
  }
}

/**
 * The line under the Scope: what it shows and what the pick levels are (the server's
 * `LEVELS` and `TONE_HZ`, `solum/simulate.py`). @param {string} net the net drawn
 */
function scopeNote(net) {
  return `The waveform at ${net || "the probed point"} with a steady 200 Hz tone at the guitar. The pick level is how hard that tone is: Soft 0.1 V, Medium 0.3 V, Hard 1 V peak (a single coil played lightly, a humbucker played normally, picking hard). Click a wire to probe another point.`;
}

/** The line under Harmonics: where they're measured. @param {string} net */
function harmonicsNote(net) {
  return `The overtones the circuit adds to the Scope's 200 Hz tone, measured at ${net || "the probed point"} at the Scope's pick level: each bar is how far that harmonic sits below the tone itself (2 is 400 Hz, 3 is 600 Hz…). A clean circuit has none worth seeing.`;
}

/**
 * The output's frequency curve from a run's (or the live solve's) AC result, for the
 * Audio panel's Expected line. @param {any} ac
 */
function outputCurve(ac) {
  const out = state.view?.probes.out;
  return ac && out && ac.nodes[out] ? { freq: ac.freq, db: ac.nodes[out] } : null;
}

/** Tell the Audio panel whether the last run's scope tone clipped at the output (D-096). */
function showClipping() {
  const tran = state.run?.tran;
  const curve = outputCurve(state.run?.ac);
  const stats = tran && curve ? tran.nodes[state.view.probes.out]?.stats : null;
  if (!stats) return audio.setClipping(null);
  const [gainDb] = atFreqs(curve.freq, curve.db, [tran.freq]);
  audio.setClipping(stats, { level: tran.level, freq: tran.freq, gainDb });
}

/** @param {string} net the net shown "at this point" */
function render(net) {
  if (!state.sweep) {
    audio.setCurve(outputCurve(state.run?.ac));
    showClipping();
  }
  power.showDraw();
  const { view, run, part, sweep } = state;
  const out = view.probes.out;
  if (part) {
    const tried = sweep?.ref === part.ref && sweep.parts?.length ? sweep : null; // its readings at each value tried (D-318)
    const curveEl = renderPartView($("probe-body"), part, (n) => select({ kind: "net", id: n }), tried);
    const curve = deviceCurve(part);
    if (curveEl && curve) curvePlot(curveEl, curve);
  } else {
    renderNodeView($("probe-body"), view, run, net);
  }

  const sweepNet = sweep ? /** @type {HTMLSelectElement} */ ($("sweep-net")).value || sweep.nodes[0] : null;
  $("sweep-tools").hidden = !sweep;
  $("sweep-summary").hidden = !sweep;
  if (sweep) {
    $("sweep-title").textContent = `${sweep.ref}: ${sweep.values.length} ${sweep.field === "rail" ? "supply voltages" : `${sweep.field}s`}`;
    renderSweepSummary($("sweep-summary"), sweep, sweepSummary(sweep, /** @type {string} */ (sweepNet)), /** @type {string} */ (sweepNet));
  }

  // Frequency: a sweep overlays its runs; a capacitor or inductor shows both its sides and the output, else net + output (a pot's net is its wiper)
  let freq = null;
  if (sweep) freq = valueSweepSeries(sweep, sweepNet, "ac");
  else if (SIDED.has(part?.type)) freq = capacitorSeries(part.detail?.curves, run, out);
  freq ??= frequencySeries(run, net, out, state.snapshots.frequency);
  state.plotted.frequency = freq;
  const freqEl = $("frequency-plot");
  const invalid = run?.ac && !run.ac.valid;
  const warning = $("ac-invalid");
  warning.hidden = !invalid;
  warning.textContent = invalid
    ? `This curve doesn't show what the circuit does. ${run.ac.saturated.map((/** @type {any} */ s) => s.message).join(" ")} A frequency curve assumes every stage is working as an amplifier. Fix the bias first (see Problems).`
    : "";
  freqEl.classList.toggle("invalid", Boolean(invalid));
  const [readingNet, readings] = curveReadings(part, run, net);
  tools.shown(run, readingNet, Boolean(sweep));
  if (freq) linePlot(freqEl, freq, { ...FREQUENCY_PLOT, ...tools.plotOpts(freq) });
  else freqEl.replaceChildren(emptyNote("No frequency response: this circuit has no guitar input."));
  renderReadings($("frequency-readings"), readings && !sweep ? readingRows(readings) : [], readingNet);

  const scope = (sweep && valueSweepSeries(sweep, sweepNet, "tran")) || scopeSeries(run, net, state.snapshots.scope);
  state.plotted.scope = scope;
  notesAt.scope = sweepNet ?? net;
  notesAt.harmonics = net;
  if (scope) linePlot($("scope-plot"), scope, SCOPE_PLOT);
  else $("scope-plot").replaceChildren(emptyNote("No waveform: this circuit has no guitar input."));

  const bars = harmonicBars(run?.tran?.nodes[net]?.stats);
  if (bars) barPlot($("harmonics-plot"), bars);
  else $("harmonics-plot").replaceChildren(emptyNote("No harmonics without a waveform."));

  renderDc($("dc-body"), view, run, (n) => select({ kind: "net", id: n }));
  schematic.showDc(state.dc ? run.op.voltages : null, run.op.held);
  void showImpedance();
  for (const b of document.querySelectorAll("[data-level]")) b.setAttribute("aria-checked", String(b.getAttribute("data-level") === state.level));
}

/**
 * Which curve the Frequency panel's readings are for, and the server's readings of it: a
 * capacitor's effect on the output (its first side when there's no output), else the net
 * shown; the output instead of a supply or ground.
 * @param {any} part @param {any} run @param {string} net
 * @returns {[string, any[] | null]}
 */
function curveReadings(part, run, net) {
  const out = state.view.probes.out;
  const curves = SIDED.has(part?.type) ? part.detail?.curves : null;
  if (curves) {
    if (out && run?.ac?.readings?.[out]) return [out, run.ac.readings[out]];
    const first = Object.keys(curves.nodes)[0];
    return [first, curves.readings?.[first] ?? null];
  }
  const flat = net === "GND" || state.view.nets[net]?.rail;
  const shown = flat && out ? out : net;
  return [shown, run?.ac?.readings?.[shown] ?? null];
}

/** A fresh sheet: say what to do instead of plotting a signal that has no path. */
function showUnwired() {
  showError(null);
  state.run = state.part = null;
  power.showDraw();
  const note = "Nothing is wired yet. Drag parts in from the left, then use the Wire tool to wire the guitar input through them to the amp.";
  $("probe-body").replaceChildren(emptyNote(note));
  for (const id of ["frequency-plot", "scope-plot", "harmonics-plot"]) $(id).replaceChildren(emptyNote("Wire a signal path to see this."));
  notesAt.scope = notesAt.harmonics = "";
  $("dc-body").replaceChildren();
  stages.clear("Wire a signal path to see the stages.");
  $("problems-body").replaceChildren(emptyNote("Nothing to check yet."));
  $("problem-count").textContent = "";
  state.problems = null;
  schematic.showMarks([]);
  $("ac-invalid").hidden = true;
  renderReadings($("frequency-readings"), [], "");
  tools.clear();
  schematic.showDc(null);
  void showImpedance(); // none: there's no run
  document.body.dataset.busy = "false";
  document.body.dataset.updates = String(++state.updates);
}

/** @param {string} text */
function emptyNote(text) {
  const p = document.createElement("p");
  p.className = "empty";
  p.textContent = text;
  return p;
}

// A knob's run, and the Bias & headroom pane's measuring after it, end before the next
// one is sent: taps that come faster than that share one run at the newest position.
const knobRun = oneAtATime(async () => {
  await refresh();
  await stagesMeasuring;
});
const rerun = debounce(() => void knobRun(), KNOB_DEBOUNCE_MS);

/** @param {string} ref @param {number} value */
function onKnob(ref, value) {
  const control = state.view.controls.find((/** @type {any} */ c) => c.ref === ref);
  state.controls = { ...state.controls, [ref]: value }; // played, not saved: the circuit keeps its opening positions (D-102)
  showKnob($("knobs-body"), control, value); // turned from a chip on the stage chain (D-122)
  stages.knobMoved(control, value);
  showOpening();
  state.sweep = null;
  tools.knobTurned(ref);
  const grabbed = state.knobLive?.ref === ref ? state.knobLive.live : null;
  if (grabbed) drawLive(grabbed, liveValues(grabbed.sliders, [nearestStep(grabbed.sliders[0], value)]));
  if (control.kind === "switch") {
    for (const pole of control.refs ?? [ref]) schematic.redrawPart(pole, value);
    schematic.select(state.selection);
  }
  if (ref === state.view.power?.control) power.show(); // the DC jack's plug: battery or supply (D-145)
  audio.changed();
  rerun();
}

function updateSnapshotButtons() {
  for (const which of ["frequency", "scope"]) {
    const has = Boolean(state.snapshots[which]);
    /** @type {HTMLElement} */ (document.querySelector(`[data-clear="${which}"]`)).hidden = !has;
  }
}

function currentNet() {
  if (state.part) return focusNet(state.part);
  // a part whose view hasn't come back yet (its form's sliders ask at once): its ref isn't
  // a net, so the output until then (D-127)
  return /** @type {string} */ (state.selection?.kind === "part" ? state.view?.probes.out : state.selection?.id);
}

// ---- wiring up -------------------------------------------------------------------

/** @param {Promise<void>} p */
const report = (p) => p.catch((err) => showError(err.message));

/** The model lists again, after a model is added (Tools → Add a model, 9c). */
async function refreshModels() {
  const [models, jfets, bjts, chips] = await Promise.all([getJson("api/models"), getJson("api/models/jfets"), getJson("api/models/bjts"), getJson("api/models/chips")]);
  Object.assign(state, { models, jfets, bjts, chips });
}

/** The result panes, reorderable (set up at start). @type {{reset: () => void}} */
let panes = { reset() {} };

/** View → Reset panes: the large views back in the column too (D-127), an open session's changes asked about first. */
async function resetPanes() {
  if (!(await endSession("Resetting the panes collapses the large views, so"))) return;
  tools.collapse();
  audio.collapse();
  stages.collapse();
  panes.reset();
  if (state.run) render(currentNet()); // plots in panes that were shut are drawn at their width
}

/**
 * Move what was dragged. Wires dragged on their own must keep every connection (D-095):
 * a move that would join or split nets is refused and the wire stays put.
 * @param {import("./schematic/render.js").Items} items @param {number} dx @param {number} dy
 */
async function moveOnSheet(items, dx, dy) {
  const before = state.circuit;
  const next = moveItems(before, items, dx, dy);
  if (next === before) return;
  const sel = state.selection;
  const group = sel?.kind === "items" && sel.items === items; // the selection was dragged
  const mine = group || (sel?.kind === "part" && items.parts.length === 1 && items.parts[0] === sel.id);
  if (!mine) clearSelection(); // something else was dragged
  if (items.parts.length || items.labels.length || items.texts?.length) {
    await edit(next, items.parts.length ? `Move ${items.parts.join(", ")}` : items.labels.length ? "Move label" : "Move text");
  } else {
    const view = await postJson("api/view", { circuit: next });
    if (!sameConnections(state.view, view)) {
      hint("That would connect or disconnect something, so the wire stayed put. Dragging a wire keeps its connections; draw a new wire to change them.");
      return;
    }
    await edit(next, items.wires.length > 1 ? "Move wires" : "Move wire", view);
  }
  // a selection stays whole, wires and labels too, so it can be moved again (found in the
  // circuit as the server returned it; unchanged means the edit was refused)
  if (group && state.circuit !== before) selectItems(itemsAfterMove(before, state.circuit, items, dx, dy));
}

function toggleCapTypes() {
  state.capTypes = !state.capTypes;
  remember(CAP_TYPES_KEY, state.capTypes ? 1 : 0);
  schematic.capTypes = state.capTypes; // only the drawing changes: no re-run, nothing to save
  if (state.view) schematic.draw(state.view, switchPositions(), { fit: false });
}

function toggleMarks() {
  state.marks = !state.marks;
  remember(MARKS_KEY, state.marks ? 1 : 0);
  schematic.showMarks(state.marks ? (state.problems?.result?.problems ?? []) : []); // only the drawing changes
}

function toggleImpedance() {
  state.impedance = !state.impedance;
  void showImpedance();
}

let impedanceAsked = 0; // the newest overlay asked for: an older answer is dropped

/** The View → Impedance overlay, asked for after each run while it's on (D-127). */
async function showImpedance() {
  const mine = ++impedanceAsked;
  if (!state.impedance || !state.run || isUnwired(state.circuit)) return schematic.showImpedance(null);
  try {
    const z = await postJson("api/impedance", { circuit: played() });
    if (mine === impedanceAsked) schematic.showImpedance(z);
  } catch {
    if (mine === impedanceAsked) schematic.showImpedance(null); // no guitar or amp, or a failed run: nothing to say
  }
}

function toggleDc() {
  state.dc = !state.dc;
  schematic.showDc(state.dc && state.run ? state.run.op.voltages : null, state.run?.op.held);
}

/** @param {KeyboardEvent} e */
function onKey(e) {
  const target = /** @type {HTMLElement} */ (e.target);
  const act = actionFor({ key: e.key, ctrl: e.ctrlKey, meta: e.metaKey, shift: e.shiftKey, alt: e.altKey });
  // keys typed into a field are the field's, except Run from the header's own controls
  const header = act?.action === "run" && !target.closest("form");
  if (target.closest("input, select, textarea, form") && !header) return;
  if (act?.action === "inspect" && target.closest("button, a, summary")) return; // Enter presses what has focus
  if (!act || !state.circuit) return;
  if (formIsOpen() && act.action !== "cancel") return;
  e.preventDefault();
  closeMenus();
  switch (act.action) {
    case "place": return startPlacing(/** @type {string} */ (act.type));
    case "label": return askLabel();
    case "text": return startPlacing("text");
    case "ground": return startPlacing("label:GND");
    case "wire": return setWireMode(!schematic.wireMode);
    case "rotate": return rotate();
    case "delete": return deleteSelection();
    case "inspect": return state.selection?.kind === "part" ? forms.inspect(state.selection.id) : undefined;
    case "undo": return undo();
    case "redo": return redo();
    case "save": return files.save().then(() => undefined);
    case "run": return run();
    case "copy": return copy();
    case "paste": return paste();
    case "selectAll": return selectItems(allItems(state.circuit));
    case "find": return findPart();
    case "insertBlock": return blocks.blocksDialog();
    case "cancel":
      if (schematic.cancelWire()) return;
      closeForm();
      stopPlacing();
      setWireMode(false);
  }
}

function wireControls() {
  for (const b of document.querySelectorAll("[data-level]")) {
    b.addEventListener("click", () => {
      state.level = /** @type {string} */ (b.getAttribute("data-level"));
      state.sweep = null;
      refresh();
    });
  }
  for (const b of document.querySelectorAll("[data-freeze]")) {
    b.addEventListener("click", () => {
      const which = /** @type {string} */ (b.getAttribute("data-freeze"));
      const data = state.plotted[which];
      const sel = state.selection;
      state.snapshots[which] = snapshotOf(data, `snapshot: ${data?.series[0]?.label ?? sel?.id}`);
      updateSnapshotButtons();
      if (state.run) render(currentNet());
    });
  }
  for (const b of document.querySelectorAll("[data-clear]")) {
    b.addEventListener("click", () => {
      state.snapshots[/** @type {string} */ (b.getAttribute("data-clear"))] = null;
      updateSnapshotButtons();
      if (state.run) render(currentNet());
    });
  }
  $("sweep-clear").addEventListener("click", () => {
    state.sweep = null;
    if (state.run) render(currentNet());
  });
  $("sweep-net").addEventListener("change", () => state.run && render(currentNet()));
  $("fit-button").addEventListener("click", () => schematic.fit());
  $("zoom-in").addEventListener("click", () => schematic.zoomBy(1.25));
  $("zoom-out").addEventListener("click", () => schematic.zoomBy(0.8));
  $("run").addEventListener("click", () => run());
  $("knobs-opening").addEventListener("click", () => useAsOpening());
  const autorun = /** @type {HTMLInputElement} */ ($("autorun"));
  autorun.checked = state.autorun;
  autorun.addEventListener("change", () => setAutorun(autorun.checked));
  window.addEventListener("popstate", onHistory);
  files.nameEditor({ name: $("circuit-name"), box: /** @type {HTMLInputElement} */ ($("name-box")), button: /** @type {HTMLButtonElement} */ ($("rename-button")), error: $("name-error") });
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) e.preventDefault();
  });
  document.addEventListener("keydown", onKey);
  desktopMenus({ settings: openSettings });
  desktopUnsaved(() => state.dirty);
  // the schematic follows its own size (render.js); the plots redraw once the resize stops
  window.addEventListener("resize", debounce(() => {
    if (state.run) render(currentNet());
  }, 200));
}

/** Set while Back/Forward is being undone (the user cancelled the save prompt). */
let restoring = false;

/**
 * Back, Forward, or a link or typed address that changes the hash: ask about unsaved
 * changes first; on Cancel, go back to where we were, keeping the history as it was.
 * @param {PopStateEvent} e
 */
async function onHistory(e) {
  if (restoring) {
    restoring = false;
    return;
  }
  const source = sourceFromHash();
  const n = e.state?.n;
  // the circuit open (or on its way): nothing to do
  if (!source || hashOf(source) === (opening || (state.source && hashOf(state.source)))) {
    if (typeof n === "number") here = n;
    return;
  }
  if (!(await confirmLeave())) {
    restoring = true;
    if (typeof n === "number") history.go(here - n);
    else history.back(); // a typed address: a new entry, so one step back
    return;
  }
  if (typeof n === "number") here = n;
  else history.replaceState({ n: ++here }, "");
  setDirty(false);
  open(source).catch((err) => showError(err.message));
}

async function start() {
  here = typeof history.state?.n === "number" ? history.state.n : 0;
  if (typeof history.state?.n !== "number") history.replaceState({ n: here }, "");
  panes = reorderable(/** @type {HTMLElement} */ (document.querySelector(".panels")));
  const source = sourceFromHash();
  // shrunk to their bars, as they were out before the reload, in the same frame as the
  // pane list's scroll is put back (D-121)
  if (source) restoreLargeViews();
  menus.build();
  wireControls();
  const [starters, models, capacitors, pickups, jfets, bjts, chips, switches, batteries, inductors, enclosures] = await Promise.all([getJson("api/starters"), getJson("api/models"), getJson("api/guides/capacitors"), getJson("api/guides/pickups"), getJson("api/models/jfets"), getJson("api/models/bjts"), getJson("api/models/chips"), getJson("api/switches"), getJson("api/guides/batteries"), getJson("api/guides/inductors"), getJson("api/enclosures")]);
  setSwitchKinds(switches); // before anything is drawn: a pole's lugs come from its type (D-143)
  state.batteries = batteries.states;
  state.inductors = inductors.inductors;
  state.enclosures = enclosures;
  state.starters = starters;
  state.models = models;
  state.jfets = jfets;
  state.bjts = bjts;
  state.chips = chips;
  state.capKinds = capacitors.kinds;
  state.pickups = pickups.pickups;
  // what the address says now: it may have changed while the lists loaded, and opening
  // the one read before them would put a stale sheet over the newer one
  const now = sourceFromHash();
  if (now) await open(now, true);
}

start().catch((err) => showError(err.message));
