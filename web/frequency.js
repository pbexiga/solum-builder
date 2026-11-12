/**
 * The Frequency panel's tools (Phase 8b, D-097), DOM: the Layers menu (knees, peaks and
 * dips, knob ranges, part influence), what each layer draws on the plot and lists under
 * it, a click on the plot to ask what shapes the curve at that frequency, and Expand (a
 * large view over the canvas, the schematic still showing above it). Edit curve (expanded
 * only): a dot on each knee, peak and dip to drag (sideways; Shift+drag up or down),
 * changing the parts that move it, over a faint copy of the curve as it was. Logic is in
 * `layers.js`; every measure comes from the server.
 */

import { postJson } from "./api.js";
import { changeLinks, curveChanges, curveMarks, partnerText, dragTarget, grabbed, lostReason, measuredSlope, rowParts, AUDIBLE, EXPANDED_KEY, handleAt, handleMarks, handleParts, influenceRows, knobRows, LAYERS, levelAxis, levelKey, levelMove, levelText, loadLayers, PLOT_BAND, noMarks, nudgedCurves, saveLayers, seekLevel, seekStep, startDots } from "./layers.js";
import { db as dbText } from "./fixed.js";
import { menu } from "./menus.js";
import { h, largeView, largeViewChip, paneInfo } from "./panels.js";
import { setMarks } from "./plots.js";
import { latestOnly } from "./state.js";

// what the pane's ⓘ says (D-109): the curve always, then what's on screen with it
const CURVE_NOTE = "How much louder or quieter each frequency is at the probed point than at the guitar, in dB, with the knobs as they are now. "
  + "It's the small-signal curve: what the circuit does to a quiet signal, before anything clips (the Scope and the Audio panel show clipping). "
  + "Below 20 Hz and above 20 kHz, outside hearing, is shaded. Freeze keeps a copy to compare against.";
const INFLUENCE_NOTE = [
  "Each part's value +10 %, ranked by how much it moves this curve. Small-signal only: it shows filtering, not clipping. Double-click a part to change it in Edit curve.",
  "The live solver holds each stage's bias fixed, so a part marked “sets bias” shows only its filtering here; for all it does, double-click it on the schematic and use Try several values.",
];
const EDIT_CURVE_NOTE = [
  "Drag a dot sideways to move that knee or peak: it changes the part the dot names (Drag ↔ in its row). Shift+drag moves a peak or dip up or down instead: it changes the parts in Shift-drag ↕ together, each the way its arrow shows to raise it (reversed to lower it), so the peak keeps its place. Letting go applies the values and re-runs; the faint line and dots are the curve as it was when you started. Keep changes leaves the values in; Discard changes puts every value back. Esc only shrinks the view to its bar: Edit stays on.",
  "A double ring is two handles close together: its label names both, a plain drag takes the one picked in the list, Shift+drag the one that can go up or down. A faint dot has nothing to move it that way. A row that says “not a corner now” or “lost” has no dot on this curve; the ↺ in Changed puts a part back.",
  "“Whole curve” marks parts that change the level an octave or more away about as much as at the peak: they act like gain, raising everything, rather than making the peak stand out.",
  "Knobs and parts that set a bias are left out (Knob ranges and Try several values are for those). Changing parts around a knob changes what the knob does over its whole turn, not just here. On a drive or fuzz, raising a peak before the clipping means more gain into it: more clipping, not only louder.",
];
const EDIT_PART_NOTE = [
  "Parts ranked by how much +10 % moves this curve. Click one to slide its value: letting go applies it and re-runs, as part of this edit.",
  "A part marked “sets bias” shows only its filtering here. Dragging a dot goes back to By curve.",
];

const SHADE_MS = 1500; // a turned knob's band stays shaded this long after the last turn

/**
 * @typedef {{mount: (el: HTMLElement) => Promise<unknown>, close: (submitted: boolean, quiet?: boolean) => void}} PartSlider
 * @typedef {PartSlider & {steps: () => {values: number[], texts: string[], at: number} | null,
 *   seek: (index: number) => void, release: () => void}} ValueSlider
 * @typedef {PartSlider & {steps: () => Array<{values: number[], texts: string[], at: number}> | null,
 *   seek: (indices: number[]) => void, release: () => void}} LevelSliders
 * @typedef {(ref: string, value: string) => Promise<void>} PutBack
 * @typedef {{
 *   circuit: () => any,
 *   played: () => any,
 *   slider: (ref: string) => PartSlider,
 *   valueSlider: (ref: string) => ValueSlider,
 *   levelSliders: (refs: string[]) => LevelSliders,
 *   highlight: (refs: string[]) => void,
 *   showReadings: (readings: any[], net: string) => void,
 *   redraw: () => void,
 *   editSession: (owner: {pending: () => boolean, end: (how: "keep" | "discard") => unknown}) => Promise<{keep: (label: string) => void, discard: () => Promise<void>, steps: () => Array<{label: string, source: string, before: any, after: any}>} | null>,
 *   putBack: PutBack,
 *   openHistory: () => void,
 * }} Deps
 */

/**
 * @param {{panel: HTMLElement, tools: HTMLElement, plot: HTMLElement, body: HTMLElement}} els
 * @param {Deps} deps
 */
export function frequencyTools(els, deps) {
  // the panel and the expanded view each keep their own layers; expanded starts with all on
  const panelLayers = loadLayers();
  const expandedLayers = loadLayers(undefined, EXPANDED_KEY, LAYERS.map((l) => l.id));
  let layers = panelLayers;
  /** @type {any} the run the panel shows */ let run = null;
  let net = "";
  let sweeping = false;
  /** @type {import("./layers.js").Features | null} */ let features = null;
  /** @type {import("./layers.js").Band | null} */ let shade = null;
  /** @type {number | null} */ let at = null;
  /** @type {any} */ let knobs = null;
  /** @type {{key: any, curves: ReturnType<typeof nudgedCurves>, live: any} | null} */ let nudged = null;
  /** @type {any} */ let influence = null;
  /** @type {{ref: string, slider: PartSlider, row: HTMLElement} | null} */ let open = null;
  /** @type {ReturnType<typeof setTimeout> | undefined} */ let shadeTimer;
  /** @type {string | null} the knob the pointer is over (its band stays shaded) */ let hoveredKnob = null;
  const curveRequests = latestOnly();
  const knobRequests = latestOnly();
  const influenceRequests = latestOnly();
  let curveBusy = false;
  /** @type {{freq: number[], db: number[], steps: number[] | null} | null} */ let curveNext = null;
  // Edit mode: which part each handle moves (picked in its row), the handle being worked
  // (its slider mounted in its row) and the drag in progress
  let editing = false;
  /** @type {"curve" | "part"} Edit curve's way in: the dots and their rows, or the influence list with sliders (D-102) */ let editBy = "curve";
  /** @type {Map<string, string>} */ const picked = new Map();
  /** @type {Map<string, string>} handle id → its level move picked (`levelKey`) */ const pickedLevel = new Map();
  /** @type {string | null} */ let active = null;
  /** @type {{id: string, axis: "x" | "y", key: string, refs: string[], slider: any, row: HTMLElement, ready: Promise<unknown>} | null} */ let grip = null;
  /** @type {Drag | null} */ let drag = null;
  let editNote = "";
  /** @type {[number, number] | null} the level axis as drawn (`levelAxis`: held while live or editing) */ let levelRange = null;
  /** @type {any} the circuit as it was when Edit mode started */ let before = null;
  /** @type {{features: import("./layers.js").Features | null, curve: import("./layers.js").Before | null} | null} the curve then */ let start = null;
  let shiftHeld = false; // the dots name their up/down parts while Shift is down
  // this Edit session: every handle seen (a row stays, saying why, when its dot goes) and
  // every part that moved each one (a changed part stays in its menu when it drops off)
  /** @type {Map<string, import("./layers.js").Handle>} */ const seenHandles = new Map();
  /** @type {Map<string, Map<string, import("./layers.js").HandlePart>>} */ const seenParts = new Map();
  /** @type {{circuit: any, net: string, live: Promise<any>} | null} the nudges asked for as an edit lands, before its run (`circuitChanged`) */ let early = null;
  /** @type {ReturnType<Deps["editSession"]> | null} Keep or Discard ends it */ let session = null;

  // ---- the Layers menu and Expand ----------------------------------------------------
  const layersButton = /** @type {HTMLButtonElement} */ (h("button", { type: "button", id: "layers-button", title: "Lines, markers and lists over the curve" }, ["Layers"]));
  const view = largeView(/** @type {HTMLDetailsElement} */ (els.panel), {
    id: "frequency-expand",
    name: "frequency",
    what: "A large view of the curve, over the canvas",
    tools: els.tools,
    onChange: (on) => {
      if (!on && editing) keep(); // only with nothing changed: Collapse waits for Keep or Discard
      layers = on ? expandedLayers : panelLayers;
      editTools.hidden = !on;
      layersChanged();
      deps.redraw(); // a new height: the plot is drawn again
    },
    onShow: () => deps.redraw(), // a run while shrunk drew at the bar's width
  });
  const expanded = () => view.expanded();
  const setExpanded = view.set;
  // Edit curve (large view only) sits apart at the right of the tools (Collapse is on the title bar); while editing it becomes Discard / Keep
  const editButton = h("button", { type: "button", id: "frequency-edit", title: "Drag the knees and peaks to change the parts that set them" }, ["Edit curve"]);
  const discardButton = h("button", { type: "button", id: "frequency-discard", hidden: "", title: "Put back every value changed since Edit curve (Undo brings them back)" }, ["Discard changes"]);
  const keepButton = h("button", { type: "button", id: "frequency-keep", class: "primary", hidden: "", title: "Leave Edit mode with the values as they are" }, ["Done"]);
  const editTools = h("span", { class: "edit-tools", hidden: "" }, [editButton, discardButton, keepButton]);
  els.tools.append(layersButton, editTools);
  paneInfo(/** @type {HTMLDetailsElement} */ (els.panel), "Frequency", () => {
    const more = editing ? [["Edit curve", ...(editBy === "part" ? EDIT_PART_NOTE : EDIT_CURVE_NOTE)]]
      : !sweeping && layers.has("influence") ? [["Part influence", ...INFLUENCE_NOTE]] : [];
    return [CURVE_NOTE, ...more.flatMap(([head, ...notes]) => [h("h5", {}, [head]), ...notes])];
  });
  menu(layersButton, () =>
    LAYERS.map((l) => ({
      label: l.label,
      id: `layer-${l.id}`,
      checked: layers.has(l.id),
      run: () => toggle(l.id),
    })),
  );
  editButton.addEventListener("click", () => void startEditing());
  keepButton.addEventListener("click", () => keep());
  discardButton.addEventListener("click", () => discard());
  document.addEventListener("keydown", (e) => e.key === "Shift" && setShift(true));
  document.addEventListener("keyup", (e) => e.key === "Shift" && setShift(false));
  window.addEventListener("blur", () => setShift(false));

  /** @param {boolean} on */
  function setShift(on) {
    if (shiftHeld === on) return;
    shiftHeld = on;
    if (editing) drawMarks();
  }

  /** @param {string} id */
  function toggle(id) {
    if (layers.has(id)) layers.delete(id);
    else layers.add(id);
    saveLayers(layers, undefined, expanded() ? EXPANDED_KEY : undefined);
    if (id !== "influence") at = null;
    layersChanged();
  }

  /** The layer set changed (one toggled, or the view switched sets). */
  function layersChanged() {
    if (!layers.has("influence")) at = null;
    document.body.dataset.layers = [...layers].join(" ");
    refreshLayers();
  }

  /**
   * Edit mode on or off (the large view only).
   * @param {boolean} on @param {boolean} [quiet] the view is closing, which redraws it
   */
  function setEditing(on, quiet = false) {
    if (on && !editing) editBy = "curve";
    if (!on) session = null;
    editing = on;
    before = on ? deps.circuit() : null;
    // the curve and its dots as they are now, drawn faint under the curve while editing
    const db = run?.ac?.nodes?.[net];
    start = on ? { features, curve: db ? { x: run.ac.freq, y: db, dots: startDots(features) } : null } : null;
    seenHandles.clear();
    seenParts.clear();
    editButton.hidden = on;
    editButtons();
    document.body.dataset.frequencyEditing = String(on);
    largeViewChip(/** @type {HTMLDetailsElement} */ (els.panel), on ? "Editing" : null); // on its title bar
    closeSlider(); // By part's slider: only inside Edit curve, and fresh each time
    if (!on) {
      releaseGrip();
      drag = null;
      editNote = "";
    }
    at = null;
    if (!quiet) {
      layersChanged();
      deps.redraw(); // the same level axis either way (D-102)
    }
  }

  /**
   * Anything changed since Edit curve started (Collapse waits for Keep or Discard): a value
   * from the curve, or any edit from outside that joined the session (a part moved, the
   * knobs' opening positions, D-101, D-103), not values only.
   */
  const changed = () => editing && JSON.stringify(before) !== JSON.stringify(deps.circuit());

  /** Discard / Keep while editing: Keep reads Done until a value has changed. */
  function editButtons() {
    const pending = changed();
    discardButton.hidden = !pending;
    keepButton.hidden = !editing;
    keepButton.textContent = pending ? "Keep changes" : "Done";
    view.lock(pending ? "Keep or discard your Edit curve changes first" : null);
  }

  /**
   * Edit on: its session first (another one open, a bias fix's, is asked about, D-120).
   * @returns {Promise<boolean>} whether Edit is on
   */
  async function startEditing() {
    if (editing) return true;
    const s = await deps.editSession({ pending: () => changed(), end: (how) => (how === "keep" ? keep() : discard()) });
    if (!s) return false; // cancelled
    if (editing) return true; // a second click while asking
    session = s;
    setEditing(true);
    return true;
  }

  /** Leave Edit mode with its changes, as one undo step ("Edit curve: C3, C5"). */
  function keep() {
    const refs = curveChanges(before, deps.circuit()).map((c) => c.ref);
    const others = session ? changeLinks(session.steps()).others : []; // moves and wiring made outside, kept with it
    const label = [refs.join(", "), ...others].filter(Boolean).join(" \u00b7 ");
    session?.keep(label ? `Frequency curve: ${label}` : "Frequency curve"); // History's name (D-127)
    setEditing(false);
  }

  /** Leave Edit mode, putting back the circuit and the Not saved chip as they were. */
  function discard() {
    const s = session;
    setEditing(false);
    return s?.discard();
  }

  /**
   * Edit curve's way in (D-102): "curve" (the dots and their rows) or "part" (the influence
   * list, a slider per part). Both feed the same session; only one slider is open at a time.
   * @param {"curve" | "part"} by
   */
  function setBy(by) {
    if (editBy === by) return;
    editBy = by;
    if (by === "part") {
      releaseGrip();
      active = null;
      editNote = "";
    } else closeSlider();
    renderBody();
    drawMarks();
  }

  /**
   * A Part influence row double-clicked (D-102): the large view, in Edit curve by part,
   * with that part's slider open.
   * @param {string} ref
   */
  async function editPart(ref) {
    if (!(await startEditing())) return; // asked first: Cancel leaves the view it came from
    setExpanded(true);
    setBy("part");
    if (open?.ref !== ref) openSlider(ref);
  }

  // ---- marks on the plot --------------------------------------------------------------
  function marks() {
    if (sweeping) return noMarks();
    if (editing) {
      const labels = partsNow();
      // Shift held: each dot names what Shift+drag moves (a knee: nothing)
      if (shiftHeld) for (const hd of handles()) labels[hd.id] = upDownLabel(hd.id);
      if (grip?.axis === "y") labels[grip.id] = upDownLabel(grip.id);
      return { ...noMarks(), bands: shade ? [shade] : [], handles: handleMarks(handles(), features, labels, active), before: start?.curve ?? null };
    }
    const m = curveMarks(features, layers);
    if (shade) m.bands.push(shade);
    if (layers.has("influence")) m.at = at;
    return m;
  }

  const drawMarks = () => setMarks(els.plot, marks());

  /** @param {import("./layers.js").Band | null} band */
  function setShade(band) {
    shade = band;
    drawMarks();
  }

  // ---- knob ranges ------------------------------------------------------------------
  async function loadKnobs() {
    const key = { run, net };
    if (knobs?.key.run === run && knobs.key.net === net) {
      renderBody();
      return knobs.ready; // loading already: done when it is
    }
    const token = knobRequests.next();
    /** @type {() => void} */ let done = () => {};
    knobs = { key, result: null, error: null, ready: new Promise((resolve) => { done = () => resolve(undefined); }) };
    renderBody();
    try {
      const result = await postJson("api/knobs", { circuit: deps.played(), net });
      if (knobRequests.isCurrent(token)) knobs = { key, result, error: null };
    } catch (err) {
      if (knobRequests.isCurrent(token)) knobs = { key, result: null, error: /** @type {Error} */ (err).message };
    }
    done();
    if (knobRequests.isCurrent(token)) renderBody();
  }

  /** Where knob `ref` acts on the curve (once the knob ranges are loaded), else null. @param {string | null} ref */
  function knobBand(ref) {
    if (!ref) return null;
    return knobs?.result?.knobs.find((/** @type {any} */ x) => x.ref === ref)?.band ?? null;
  }

  /** The knob ranges for the curve shown, loaded once even with the Knob ranges layer off (for the knobs' hover). */
  async function knobRanges() {
    if (run?.ac && net && !sweeping) await loadKnobs();
  }

  // ---- part influence --------------------------------------------------------------
  async function loadInfluence() {
    const token = influenceRequests.next();
    const wanted = at; // Edit mode ranks over all frequencies
    try {
      if (nudged?.key.run !== run || nudged.key.net !== net) {
        nudged = null;
        // Edit mode keeps its dots and rows until the new ones come, so they don't blink out
        influence = editing && influence?.result ? { ...influence, pending: true } : { pending: true };
        renderBody();
        const circuit = deps.played();
        const live = await (early?.circuit === circuit && early.net === net ? early.live : nudgesFor(circuit));
        if (!influenceRequests.isCurrent(token)) return;
        nudged = { key: { run, net }, curves: nudgedCurves(live, net), live };
      }
      const curves = nudged.curves;
      if (!curves) {
        influence = { error: "No curve to compare: this circuit has no guitar input." };
      } else {
        // up/down leaves out knobs and parts that set a bias (D-100)
        const avoid = nudgeList().filter((/** @type {any} */ n) => n.bias || n.knob).map((/** @type {any} */ n) => n.ref);
        const result = await postJson("api/influence", { ...curves, nudge: nudged.live.nudge, at: editing ? null : wanted, avoid });
        if (!influenceRequests.isCurrent(token)) return;
        influence = { result, rows: influenceRows(result, nudged.live.nudges) };
        if (editing) remember(result.handles);
      }
    } catch (err) {
      if (!influenceRequests.isCurrent(token)) return;
      influence = { error: /** @type {Error} */ (err).message };
    }
    renderBody();
    if (editing) drawMarks(); // the handles came with it
  }

  /** Each part nudged +10 % (`api/live`), for influence and Edit's handles. @param {any} circuit */
  const nudgesFor = (circuit) => postJson("api/live", { circuit, nets: [net], controls: [], nudge: true });

  /** Edit mode keeps every handle and part it has seen this session. @param {import("./layers.js").Handle[]} list */
  function remember(list) {
    for (const hd of list) {
      seenHandles.set(hd.id, hd);
      const parts = seenParts.get(hd.id) ?? new Map();
      for (const p of hd.parts) parts.set(p.ref, p);
      seenParts.set(hd.id, parts);
    }
  }

  function closeSlider() {
    open?.slider.close(true, true);
    open = null;
  }

  /** @param {string} ref */
  function openSlider(ref) {
    if (open?.ref === ref) return closeSlider(), renderBody();
    closeSlider();
    const slider = deps.slider(ref);
    const row = h("div", { class: "influence-slider", id: "influence-slider" });
    open = { ref, slider, row };
    slider.mount(row);
    renderBody();
  }

  // ---- Edit mode -----------------------------------------------------------------------
  /** @returns {import("./layers.js").Handle[]} */
  /** The handles, each offering the parts that move it now and any changed this session that moved it before (`rowParts`). */
  const handles = () => {
    /** @type {import("./layers.js").Handle[]} */ const list = influence?.result?.handles ?? [];
    if (!editing) return list;
    const changedRefs = new Set(curveChanges(before, deps.circuit()).map((c) => c.ref));
    return list.map((hd) => ({ ...hd, parts: rowParts(hd, seenParts.get(hd.id) ?? new Map(), changedRefs) }));
  };
  /** Handles seen this session that the curve has lost now: their rows stay and say why. */
  const lostHandles = () => {
    const now = new Set(handles().map((hd) => hd.id));
    return [...seenHandles.values()].filter((hd) => !now.has(hd.id) && lostReason(hd, features));
  };
  const nudgeList = () => nudged?.live?.nudges ?? [];
  /** Each handle's part: picked in its row, else the server's first that isn't a knob or a bias (`handleParts`). */
  const partsNow = () => handleParts(handles(), nudgeList(), picked);
  /** @param {string} id */
  const handleById = (id) => handles().find((hd) => hd.id === id);
  /** A peak's or dip's level move: picked in its row, else the server's first. @param {string} id */
  const levelNow = (id) => {
    const handle = handleById(id);
    return handle ? levelMove(handle, pickedLevel.get(id)) : null;
  };
  /** A dot's label for up/down: its level move's parts and arrows, blank for none. @param {string} id */
  const upDownLabel = (id) => {
    const move = levelNow(id);
    return move ? levelText({ ...move, spill: 0 }) : "";
  };
  /** Where a handle is on a curve, as its row shows it: a knee's frequency, a peak's or dip's with its level. @param {import("./layers.js").Handle} handle @param {import("./layers.js").Features | null} feats */
  const placeText = (handle, feats) => {
    const here = handleAt(handle, feats);
    if (!here) return null;
    return handle.kind === "knee" ? here.text : `${here.text} ${dbText(here.db)}`;
  };

  function releaseGrip() {
    grip?.slider.close(true, true);
    grip = null;
    deps.highlight([]);
  }

  /**
   * Work on handle `id`: the slider for its part (`axis` "x": sideways) or its level
   * move's parts ("y": up/down) goes in its row.
   * @param {string} id @param {"x" | "y"} [axis]
   */
  function activate(id, axis = grip?.id === id ? grip.axis : "x") {
    active = id;
    const move = axis === "y" ? levelNow(id) : null;
    const refs = axis === "y" ? move?.refs ?? [] : [partsNow()[id]].filter((r) => r !== null);
    const key = refs.join("+");
    if (grip?.id === id && grip.axis === axis && grip.key === key) return;
    releaseGrip();
    editNote = "";
    if (refs.length) {
      if (axis === "y") pickedLevel.set(id, key);
      else picked.set(id, refs[0]); // kept, so a re-run that reorders the parts doesn't swap it
      const slider = axis === "y" ? deps.levelSliders(refs) : deps.valueSlider(refs[0]);
      const row = h("div", { class: "influence-slider handle-slider", id: "handle-slider" });
      grip = { id, axis, key, refs, slider, row, ready: slider.mount(row) };
      deps.highlight(refs);
    }
    renderBody();
    drawMarks();
  }

  /**
   * @typedef {{id: string, axis: "x" | "y", grab: import("./plots.js").DragPoint, point: import("./plots.js").DragPoint, ended: boolean, ready: boolean,
   *   corrections: number, end: boolean, refs: string[], values: number[][], texts: string[][], from: number[], indices: number[],
   *   exponent: number, move: import("./layers.js").LevelMove | null, known: {v: number[], f: number, db: number, steps: number[]},
   *   limit: {dir: number, steps: number[]} | null,
   *   was: {f: number, db: number, text: string}, now: {f: number, db: number, text: string}}} Drag
   */

  /**
   * A handle dragged on the plot (`plots.js`): a plain drag moves it sideways, changing its
   * part (`seekStep`, from how its frequency follows the part); Shift+drag moves it up or
   * down, changing its level move's parts together (`seekLevel`). Either way the sliders
   * follow, corrected as the server measures where the moved curve puts it, and letting go
   * applies them and re-runs. A click (no move) just picks the handle's row.
   * @param {string} id @param {import("./plots.js").DragPoint} point @param {"start" | "move" | "end"} phase
   */
  function onDrag(id, point, phase) {
    if (!editing) return;
    if (phase === "start") {
      if (editBy === "part") setBy("curve"); // a dot dragged: its row shows what it changes
      // a shared dot: Shift+drag takes the one that can go up or down (`grabbed`)
      const mark = marks().handles.find((m) => m.id === id);
      if (mark) id = grabbed(mark, handles(), point.shift);
      drag = /** @type {Drag} */ ({ id, axis: point.shift ? "y" : "x", grab: point, point, ended: false, ready: false });
      begin(drag);
      return;
    }
    if (!drag) return; // (its id may be another handle on a shared dot)
    drag.point = point;
    if (phase === "end") {
      drag.ended = true;
      if (drag.ready) letGo(); // else once its sliders have loaded
      return;
    }
    if (drag.ready) {
      drag.corrections = 0;
      seek();
    }
  }

  /** A drag has started: load its sliders, then follow it. @param {Drag} d */
  async function begin(d) {
    const handle = handleById(d.id);
    const axis = d.axis;
    if (!handle) return void (drag = null);
    activate(d.id, axis);
    const g = grip;
    if (!g) {
      drag = null;
      editNote = axis === "x" ? "No one part moves it sideways."
        : handle.kind === "knee" ? "A knee moves sideways only: drag without Shift."
        : "No part moves just its level.";
      return renderBody();
    }
    await g.ready;
    if (drag !== d || grip !== g) return;
    const steps = axis === "y" ? g.slider.steps() : [g.slider.steps()].filter(Boolean);
    const part = handle.parts.find((p) => p.ref === g.refs[0]);
    if (!steps?.length || (axis === "x" && !part)) return void (drag = null);
    const here = handleAt(handle, features) ?? handle;
    const was = { f: here.f, db: here.db, text: handle.text };
    Object.assign(d, {
      ready: true, corrections: 0, end: false, refs: g.refs, exponent: part?.exponent ?? 0, move: axis === "y" ? levelNow(d.id) : null,
      values: steps.map((/** @type {any} */ s) => s.values), texts: steps.map((/** @type {any} */ s) => s.texts),
      from: steps.map((/** @type {any} */ s) => s.at), indices: steps.map((/** @type {any} */ s) => s.at),
      known: { v: steps.map((/** @type {any} */ s) => s.values[s.at]), f: here.f, db: here.db, steps: steps.map((/** @type {any} */ s) => s.at) },
      limit: null, was, now: was,
    });
    seek();
    if (d.ended) letGo();
  }

  /** Move the sliders to the steps the drag asks for now. */
  function seek() {
    if (!drag?.ready || !grip) return;
    const target = dragTarget(drag.axis, drag.was, drag.grab, drag.point);
    // up/down past where its parts turn the level the other way: held there until the drag turns back
    const dir = Math.sign(target - drag.known.db);
    if (drag.limit && dir !== drag.limit.dir) drag.limit = null;
    if (drag.limit) return showDrag();
    const found = drag.axis === "y"
      ? seekLevel(drag.values, drag.known, target, /** @type {import("./layers.js").LevelMove} */ (drag.move), drag.was.f) // held where it was
      : (({ index, end }) => ({ indices: [index], end }))(seekStep(drag.values[0], { v: drag.known.v[0], f: drag.known.f }, target, drag.exponent));
    drag.end = found.end;
    if (found.indices.some((i, k) => i !== drag?.indices[k])) {
      drag.indices = found.indices;
      // the curve follows (`live` below measures it)
      if (drag.axis === "y") grip.slider.seek(found.indices);
      else grip.slider.seek(found.indices[0]);
    }
    showDrag();
  }

  function letGo() {
    const d = drag;
    drag = null;
    if (!d?.ready || !grip) return;
    if (d.indices.some((i, k) => i !== d.from[k])) grip.slider.release();
    else editNote = "";
    renderBody();
  }

  function showDrag() {
    if (!drag?.ready) return;
    const d = drag;
    const handle = handleById(d.id);
    const what = handle?.kind === "knee" ? `${handle.side} knee` : handle?.kind ?? "";
    const values = d.refs.map((ref, k) => `${ref} ${d.texts[k][d.from[k]]} → ${d.texts[k][d.indices[k]]}`).join(", ");
    const moved = d.axis === "y" ? `${dbText(d.was.db)} → ${dbText(d.now.db)}` : `${d.was.text} → ${d.now.text}`;
    editNote = `${values} · ${what} ${moved}`;
    if (d.limit) editNote += ` (as far as these parts ${d.limit.dir > 0 ? "raise" : "lower"} it here: past this they move it the other way)`;
    else if (d.end) editNote += " (a part is at the end of its range: its slider shows how far it goes)";
    const note = els.body.querySelector("#handle-note");
    if (note) note.textContent = editNote;
  }

  /**
   * The server measured a live curve: while dragging, where the handle is at the steps it
   * was drawn for corrects the next steps (a few times per move, so it can't hunt). Up/down
   * also learns its slope from the last two measurements (`measuredSlope`); where the level
   * went the wrong way, it steps back to the last good steps and holds there.
   * @param {number[] | null} steps
   */
  function measured(steps) {
    if (!drag?.ready || steps === null || !grip) return;
    const d = drag;
    const handle = handleById(d.id);
    const here = handle && handleAt(handle, features);
    if (!here) return;
    const prev = d.known;
    const known = { v: steps.map((i, k) => d.values[k][i]), f: here.f, db: here.db, steps };
    if (d.axis === "y" && d.move) {
      const { move, wrong } = measuredSlope(d.move, prev, known);
      if (wrong) {
        d.limit = { dir: Math.sign(prev.db - known.db), steps: prev.steps };
        d.indices = [...prev.steps];
        grip.slider.seek(d.indices);
        return showDrag(); // `known` stays the last good point
      }
      d.move = move;
    }
    d.known = known;
    d.now = here;
    if (d.corrections++ < 3) seek();
    else showDrag();
  }

  /** Each handle row's frequency, where the curve has it now (a slider or a drag moving). */
  function rowValues() {
    for (const handle of handles()) {
      const el = els.body.querySelector(`li[data-handle="${handle.id}"] > .value`);
      if (el) el.textContent = placeText(handle, features) ?? "–";
    }
  }

  function editSection() {
    const way = (/** @type {"curve" | "part"} */ by, /** @type {string} */ label, /** @type {string} */ title) => {
      const b = h("button", { type: "button", role: "radio", "aria-checked": String(editBy === by), id: `edit-by-${by}`, title }, [label]);
      b.addEventListener("click", () => setBy(by));
      return b;
    };
    const head = h("div", { class: "edit-head" }, [
      h("h4", {}, ["Edit curve"]),
      h("span", { class: "segmented", role: "radiogroup", "aria-label": "Edit the curve" }, [
        way("curve", "By curve", "Drag the dots on the curve: each knee, peak and dip names the parts that move it"),
        way("part", "By part", "Slide any part's value, the parts ranked by how much they move this curve"),
      ]),
    ]);
    const changes = curveChanges(before, deps.circuit());
    const links = changeLinks(session?.steps() ?? []);
    const now = new Set(changes.map((c) => c.ref));
    // under the rows: what's changed since Edit curve, one part per line (it scrolls on its own if long)
    const changed = h("div", { class: "curve-changes-box" }, [
      h("h4", {}, ["Changed"]),
      changes.length
        ? h("ul", { class: "curve-changes", id: "curve-changes" }, changes.map((c) => {
          const back = h("button", { type: "button", class: "link put-back", title: `Put ${c.ref} back to ${c.from}` }, ["↺"]);
          back.addEventListener("click", () => {
            if (grip?.refs.includes(c.ref)) releaseGrip(); // its slider would show the old step
            deps.putBack(c.ref, c.from);
          });
          const partners = links.partners.get(c.ref);
          const li = h("li", { "data-ref": c.ref, ...(partners ? { title: partnerText(partners, now) } : {}) }, [
            ...(partners ? [h("span", { class: "linked-dot", "aria-label": "changed along with other parts" })] : []),
            `${c.ref} ${c.from} → ${c.to} `,
            ...(links.outside.has(c.ref) ? [h("span", { class: "tag" }, ["outside Edit curve"]), " "] : []),
            back,
          ]);
          if (partners) {
            // hover: its partners light up, in the list and on the schematic
            const all = [c.ref, ...partners.flat()];
            li.addEventListener("pointerenter", () => {
              for (const el of els.body.querySelectorAll("#curve-changes li")) el.classList.toggle("partner", all.includes(/** @type {HTMLElement} */ (el).dataset.ref ?? ""));
              deps.highlight(all);
            });
            li.addEventListener("pointerleave", () => {
              for (const el of els.body.querySelectorAll("#curve-changes li.partner")) el.classList.remove("partner");
              deps.highlight(grip?.refs ?? []);
            });
          }
          return li;
        }))
        : h("p", { class: "curve-changes", id: "curve-changes" }, ["No values changed yet."]),
      ...(links.others.length ? [h("p", { class: "curve-others", id: "curve-others" }, [`Also in this edit, from outside: ${links.others.join(", ")}`])] : []),
      button("History", "curve-history", () => deps.openHistory()),
    ]);
    /** @type {Node[]} */ const body = [];
    const list = handles();
    if (sweeping) body.push(h("p", { class: "hint" }, ["Editing is off while a sweep is shown."]));
    else if (editBy === "part") body.push(...influenceList());
    else if (influence?.error) body.push(h("p", { class: "warning" }, [influence.error]));
    else if (list.length) body.push(h("ul", { id: "handle-rows" }, [...list.map((x) => handleRow(x)), ...lostHandles().map((x) => lostRow(x))])); // kept while the next ones load
    else if (influence?.pending || (!influence && run?.ac)) body.push(h("p", { class: "hint" }, ["Finding what moves each knee and peak…"]));
    else body.push(h("p", { class: "hint" }, ["This curve has no knees, peaks or dips to grab."]));
    return h("section", { class: "layer-list", id: "curve-edit" }, [head, ...body, h("hr"), changed]);
  }

  /** @param {import("./layers.js").Handle} handle */
  function handleRow(handle) {
    const ref = partsNow()[handle.id];
    const now = placeText(handle, features) ?? handle.text;
    const was = start ? placeText(handle, start.features) : null;
    const lost = lostReason(handle, features);
    const li = h("li", { "data-handle": handle.id, class: active === handle.id ? "active" : "" }, [
      h("span", { class: "label" }, [handle.label]),
      " ",
      h("span", { class: "value" }, [now]),
      ...(was && was !== now ? [h("span", { class: "was", title: "Where it was when you pressed Edit curve (the faint dot)" }, [`was ${was}`])] : []),
    ]);
    if (lost) li.append(h("span", { class: "handle-lost" }, [lost])); // its dot is gone for now
    const name = handle.label.toLowerCase();
    /** One way to move it: what does it, then the menu of parts (or why there's none). @param {string} way @param {string} title @param {Node} what */
    const wayRow = (way, title, what) => h("span", { class: "handle-way", title }, [way, what]);
    if (!handle.parts.length) li.append(wayRow("Drag ↔", "A plain drag moves it sideways", h("span", {}, [": no one part moves it sideways"])));
    else {
      const select = /** @type {HTMLSelectElement} */ (h("select", { class: "handle-part", "aria-label": `Part that moves the ${name} sideways` },
        handle.parts.map((/** @type {import("./layers.js").RowPart} */ p) => h("option", { value: p.ref }, [p.kept ? `${p.ref} · changed` : p.ref]))));
      select.value = ref ?? "";
      select.addEventListener("change", () => {
        picked.set(handle.id, select.value);
        activate(handle.id, "x");
      });
      li.append(wayRow("Drag ↔", "A plain drag moves it sideways, changing this part", select));
    }
    if (handle.kind !== "knee") {
      const moves = handle.levels ?? [];
      const title = "Shift+drag moves it up or down, changing these parts together: the arrows show which way each goes to raise it";
      if (!moves.length) li.append(wayRow("Shift-drag ↕", title, h("span", {}, [": no part moves just its level"])));
      else {
        const select = /** @type {HTMLSelectElement} */ (h("select", { class: "handle-level", "aria-label": `Parts that move the ${name} up and down` },
          moves.map((m) => h("option", { value: levelKey(m) }, [levelText(m)]))));
        select.value = levelKey(/** @type {import("./layers.js").LevelMove} */ (levelNow(handle.id)));
        select.addEventListener("change", () => {
          pickedLevel.set(handle.id, select.value);
          activate(handle.id, "y");
        });
        li.append(wayRow("Shift-drag ↕", title, select));
      }
    }
    li.addEventListener("click", (e) => {
      if (!(/** @type {HTMLElement} */ (e.target).closest("select, .handle-slider")) && active !== handle.id) activate(handle.id);
    });
    if (active === handle.id && grip?.id === handle.id) li.append(grip.row);
    if (active === handle.id && (grip?.id === handle.id || editNote)) li.append(h("p", { class: "handle-note", id: "handle-note" }, [editNote]));
    return li;
  }

  /** A handle the curve has lost since Edit started: greyed, saying why, where it was. @param {import("./layers.js").Handle} handle */
  function lostRow(handle) {
    const was = start ? placeText(handle, start.features) : null;
    return h("li", { "data-handle": handle.id, class: "lost" }, [
      h("span", { class: "label" }, [handle.label]),
      ...(was ? [h("span", { class: "was" }, [`was ${was}`])] : []),
      h("span", { class: "handle-lost" }, [lostReason(handle, features) ?? ""]),
    ]);
  }

  // ---- the lists under the plot --------------------------------------------------------
  function renderBody() {
    editButtons();
    const parts = [];
    if (editing) parts.push(editSection());
    else if (sweeping && layers.size) parts.push(h("p", { class: "hint" }, ["Layers are off while a sweep is shown."]));
    else {
      if (layers.has("knobs")) parts.push(knobSection());
      if (layers.has("influence")) parts.push(influenceSection());
    }
    els.body.hidden = !parts.length;
    els.body.replaceChildren(...parts);
  }

  function knobSection() {
    const rows = knobs?.result ? knobRows(knobs.result) : [];
    return h("section", { class: "layer-list", id: "knob-ranges" }, [
      h("h4", {}, ["Knob ranges"]),
      knobs?.error ? h("p", { class: "warning" }, [knobs.error])
        : !knobs?.result ? h("p", { class: "hint" }, ["Turning each knob end to end…"])
        : !rows.length ? h("p", { class: "hint" }, ["No knobs in this circuit."])
        : h("ul", {}, rows.map((r) => {
          const li = h("li", { "data-knob": r.ref, title: r.title }, [h("span", { class: "label" }, [`${r.label}:`]), " ", h("span", { class: "value" }, [r.text])]);
          li.addEventListener("pointerenter", () => setShade(r.band));
          li.addEventListener("pointerleave", () => setShade(null));
          return li;
        })),
    ]);
  }

  /** Part influence, for reading (D-102): changing a part is Edit curve's (double-click a row). */
  function influenceSection() {
    const head = h("h4", {}, ["Part influence"]);
    return h("section", { class: "layer-list", id: "influence" }, [head, ...influenceList()]);
  }

  /** The ranked parts (in a scrolling box), for reading or, in Edit curve by part, with sliders. */
  function influenceList() {
    /** @type {Node[]} */ const body = [];
    if (influence?.pending && !(editing && influence.rows)) body.push(h("p", { class: "hint" }, ["Nudging each part…"]));
    else if (influence?.error) body.push(h("p", { class: "warning" }, [influence.error]));
    else if (influence?.result) {
      const { result, rows } = influence;
      if (!editing) {
        body.push(h("p", { class: "influence-at" }, result.at_text
          ? [`What shapes the curve at ${result.at_text}. `, button("All frequencies", "influence-all", () => pickAt(null))]
          : ["Click the curve to rank the parts at one frequency."]));
        body.push(h("p", { class: "influence-at influence-note", id: "influence-edit-note" }, ["Double-click a part to open it in the editor (Edit curve)."]));
      }
      body.push(h("ul", { id: "influence-rows", class: "influence-rows" }, rows.map((/** @type {any} */ r) => influenceRow(r))));
      if (result.hidden.length) body.push(h("p", { class: "hint" }, [`${result.hidden.length} more barely move it: ${result.hidden.join(", ")}.`]));
      if (open && !influence.pending && !rows.some((/** @type {any} */ r) => r.ref === open?.ref)) closeSlider();
    }
    return body;
  }

  /** @param {any} r */
  function influenceRow(r) {
    const sliding = editing && editBy === "part";
    const title = sliding ? `Slide ${r.ref}'s value` : `Double-click to change ${r.ref} in Edit curve`;
    const li = h("li", { "data-ref": r.ref, class: open?.ref === r.ref ? "open" : "" }, [
      h("button", { type: "button", class: "influence-pick", title }, [
        h("span", { class: "ref" }, [r.ref]),
        h("span", { class: "size" }, [r.sizeText]),
        h("span", { class: "what" }, [r.text]),
        ...(r.bias ? [h("span", { class: "tag", title: "It carries DC, so it also moves a stage's bias, which this view holds fixed." }, ["sets bias"])] : []),
      ]),
    ]);
    li.addEventListener("pointerenter", () => {
      deps.highlight([r.ref]);
      setShade(r.band);
    });
    li.addEventListener("pointerleave", () => {
      deps.highlight([]);
      setShade(null);
    });
    const pick = li.querySelector("button");
    if (sliding) pick?.addEventListener("click", () => openSlider(r.ref));
    else pick?.addEventListener("dblclick", () => editPart(r.ref)); // one click is too easy to hit by mistake
    if (open?.ref === r.ref) li.append(open.row);
    return li;
  }

  /** @param {string} label @param {string} id @param {() => void} onClick */
  function button(label, id, onClick) {
    const b = h("button", { type: "button", id, class: "link" }, [label]);
    b.addEventListener("click", onClick);
    return b;
  }

  /** @param {number | null} f */
  function pickAt(f) {
    at = f;
    drawMarks();
    loadInfluence();
  }

  function refreshLayers() {
    drawMarks();
    if (!sweeping && run?.ac && net) {
      if (editing) loadInfluence(); // the handles come with it
      else {
        if (layers.has("knobs")) loadKnobs();
        if (layers.has("influence")) loadInfluence();
      }
    }
    renderBody();
  }

  document.body.dataset.layers = [...layers].join(" ");

  return {
    editPart, // the large view, in Edit curve by part, on one part's slider (D-102; from the gain box, D-125)
    /**
     * What the Frequency plot needs from the tools: its marks, a click, its height, and
     * its axes: 10 Hz - 30 kHz, shaded outside 20 Hz - 20 kHz, the level axis fitted to the
     * audible band, held still while `live` (a slider moving) or editing (D-102).
     * @param {{x: number[], series: Array<{values: Array<number | null>}>}} data @param {boolean} [live]
     */
    plotOpts(data, live = false) {
      const height = view.plotHeight(220);
      levelRange = levelAxis(levelRange, data, live || editing);
      return { marks: marks(), height, xRange: PLOT_BAND, shade: AUDIBLE, yRange: levelRange ?? undefined, onPick: (/** @type {number} */ x) => !editing && layers.has("influence") && !sweeping && pickAt(x), onDrag };
    },
    /**
     * The panel shows a run's curve at `net` (the readings' net), or a sweep.
     * @param {any} shownRun @param {string} shownNet @param {boolean} sweep
     */
    shown(shownRun, shownNet, sweep) {
      if (shownRun !== run || shownNet !== net) at = null;
      run = shownRun;
      net = shownNet;
      sweeping = sweep;
      features = run?.ac?.features?.[net] ?? null;
      refreshLayers();
    },
    /**
     * A live curve at the readings' net (a slider or knob moving): its knees, peaks and
     * readings follow it, measured on the server (one request at a time, the newest next).
     * @param {number[]} freq @param {number[]} db
     */
    live(freq, db) {
      curveNext = { freq, db, steps: drag?.ready ? [...drag.indices] : null };
      if (curveBusy) return;
      const send = async () => {
        while (curveNext) {
          const curve = curveNext;
          curveNext = null;
          curveBusy = true;
          const token = curveRequests.next();
          try {
            const got = await postJson("api/curve", { freq: curve.freq, db: curve.db });
            if (curveRequests.isCurrent(token) && !curveNext) {
              features = got.features;
              measured(curve.steps);
              if (editing) rowValues();
              drawMarks();
              deps.showReadings(got.readings, net);
            }
          } catch {
            // no readings for this step: the next one, or ngspice on release, brings them
          } finally {
            curveBusy = false;
          }
        }
      };
      send();
    },
    /** The net the layers read (the readings' net). */
    net: () => net,
    /**
     * The circuit changed (an edit, undo or redo): while editing, ask for its nudged
     * curves now, alongside its ngspice run rather than after it, so the dots' parts come
     * back sooner.
     */
    circuitChanged() {
      if (!editing || !net || sweeping) return;
      const circuit = deps.played();
      early = { circuit, net, live: nudgesFor(circuit) };
      early.live.catch(() => {}); // a refused edit: loadInfluence asks again
    },
    /** A knob is turning: shade where it acts for a moment (while it's hovered, until the pointer leaves). @param {string} ref */
    knobTurned(ref) {
      const band = knobBand(ref);
      if (!band) return;
      setShade(band);
      clearTimeout(shadeTimer);
      shadeTimer = setTimeout(() => setShade(knobBand(hoveredKnob)), SHADE_MS);
    },
    /**
     * The pointer is over a knob in the Knobs panel (null: it left): its band is shaded
     * while it's there, as a Part influence row's is (D-102), in Edit curve too.
     * @param {string | null} ref
     */
    async knobHover(ref) {
      hoveredKnob = ref;
      clearTimeout(shadeTimer);
      setShade(knobBand(ref));
      if (!ref) return;
      await knobRanges(); // the Knob ranges layer may be off: load them for the hover
      if (hoveredKnob === ref) setShade(knobBand(ref));
    },
    /** Back to the panel, as the app does when another circuit opens (`backToEditor`). */
    collapse: view.collapse,
    /** Nothing to show (an unwired sheet, another circuit): Edit off. */
    clear() {
      if (editing) setEditing(false, true);
      closeSlider();
      releaseGrip();
      picked.clear();
      pickedLevel.clear();
      active = null;
      drag = null;
      editNote = "";
      run = null;
      features = null;
      knobs = nudged = influence = early = null;
      at = shade = null;
      renderBody();
    },
  };
}
