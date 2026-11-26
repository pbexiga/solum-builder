/**
 * *Lay it out for me* in the Board view (DOM, D-399, P8 R3): the running window (what it's
 * doing, the progress, the best board so far, Stop and keep the best, Cancel) while the
 * board behind shows the best so far, dimmed and not editable; then the review, a pane at
 * the top of the right column (D-406), so nothing covers the board's tools: Before → After,
 * After | Before | Both (top and bottom), ◀ Try n of m ▶, Try another, Keep try n / Keep
 * the old board. Keeping a try is one undo step; nothing else
 * changes the circuit. The view draws and locks; this runs and asks.
 */

import { postJson, postProgress } from "../api.js";
import { h } from "../panels.js";
import { figuresLine, figuresOf, leftText, sameTry, standUpOf } from "./board-logic.js";

/**
 * @typedef {{columns: number, strips: number, cuts: number, links: number, stripboard: any}} BoardLine
 *   a board as the server sends it: its figures and its plain form
 * @typedef {BoardLine & {fell_back: boolean, stopped: boolean, note: string}} Made a try's board, wired and checked
 * @typedef {{stripboard: any, title?: string}} Shown a board drawn as a preview, with a line under it
 * @typedef {{
 *   circuit: () => any,
 *   preview: (boards: Shown[] | null, dim: boolean) => void,
 *   lock: (on: boolean) => void,
 *   keep: (stripboard: any) => void,
 *   refuse: (message: string) => void,
 *   reviewing?: (open: boolean) => void,
 * }} RunApp
 *   `preview`: draw these boards in place of the circuit's (one, or Before above After),
 *   dimmed while running; null: the circuit's own again; `lock`: the board's editing off
 *   (tools, tray, panes, keys) or on; `keep`: the board kept, one undo step ("Lay it out for
 *   me"); `reviewing`: the review bar has just opened (true) or been put away (false)
 *   (a hidden right column shown once, D-408)
 */

const SAME = "this circuit doesn't leave room for a different layout this small.";

/**
 * @param {HTMLElement} host the canvas's body @param {RunApp} app
 * @param {HTMLElement} column the right column: the review goes at its top, above the panes
 */
export function compactRun(host, app, column) {
  const stage = h("p", { class: "compact-stage" }, [""]);
  const bar = /** @type {HTMLProgressElement} */ (h("progress", { class: "compact-progress", "aria-label": "Building the layout" }));
  const bestLine = h("p", { class: "compact-best" }, [""]);
  const left = h("p", { class: "compact-left" }, [""]);
  const largeLine = h("p", { class: "compact-large", hidden: "" }, [""]);
  const stopButton = /** @type {HTMLButtonElement} */ (h("button", { type: "button", class: "primary", "data-run": "stop", title: "Keeps the smallest board found so far. It's wired and checked first, a second or so." }, ["Stop and keep the best"]));
  const cancelButton = /** @type {HTMLButtonElement} */ (h("button", { type: "button", "data-run": "cancel", title: "Puts the board back as it was" }, ["Cancel"]));
  const runWindow = h("div", { class: "compact-run", role: "dialog", "aria-label": "Lay it out for me", hidden: "" }, [
    h("h3", {}, ["Lay it out for me"]), largeLine, stage, bar, bestLine, left, h("div", { class: "compact-buttons" }, [stopButton, cancelButton]),
  ]);
  const dimNote = h("div", { class: "compact-dim", hidden: "" }, ["Working… not editable yet"]);

  const figures = h("span", { class: "compact-figures" }, [""]);
  /** @type {Record<string, HTMLButtonElement>} */
  const modes = {};
  for (const [mode, label] of [["after", "After"], ["before", "Before"], ["both", "Both"]]) {
    modes[mode] = /** @type {HTMLButtonElement} */ (h("button", { type: "button", "data-mode": mode, "aria-pressed": "false" }, [label]));
    modes[mode].addEventListener("click", () => {
      view = /** @type {"after" | "before" | "both"} */ (mode);
      review();
    });
  }
  const prev = /** @type {HTMLButtonElement} */ (h("button", { type: "button", "data-try": "prev", title: "The try before" }, ["◀"]));
  const next = /** @type {HTMLButtonElement} */ (h("button", { type: "button", "data-try": "next", title: "The try after" }, ["▶"]));
  const tryText = h("span", { class: "compact-try" }, [""]);
  const another = /** @type {HTMLButtonElement} */ (h("button", { type: "button", "data-review": "another", title: "Run the search again with other random moves: the same base and time, a different board" }, ["Try another"]));
  const keepTry = /** @type {HTMLButtonElement} */ (h("button", { type: "button", class: "primary", "data-review": "keep" }, [""]));
  const keepOld = /** @type {HTMLButtonElement} */ (h("button", { type: "button", "data-review": "old" }, [""]));
  const said = h("p", { class: "compact-said", hidden: "" }, [""]);
  const reviewBar = h("section", { class: "compact-review", role: "toolbar", "aria-label": "Review the layout", hidden: "" }, [
    h("h3", {}, ["Review the layout"]),
    h("div", { class: "compact-row" }, [figures]),
    h("div", { class: "compact-row" }, [
      h("span", { class: "compact-modes", role: "group", "aria-label": "Show" }, Object.values(modes)),
      h("span", { class: "compact-tries" }, [prev, tryText, next]), another, keepTry, keepOld,
    ]),
    said,
  ]);
  host.append(runWindow, dimNote);
  column.prepend(reviewBar); // first: the panes are reordered among themselves after it

  /** @type {any} */
  let circuit = null; // the circuit as it was when the run began
  /** @type {import("./board-logic.js").StandUp} */
  let standUp = "needed"; // standing parts (D-403): every try's the same
  let expected = 0; // seconds a try was said to take (the estimate), 0 when not known
  let attempt = 0;
  /** @type {BoardLine | null} */
  let base = null;
  /** @type {Made[]} */
  let tries = [];
  /** @type {string[]} */
  let notes = []; // what each try's bar says (the same board as before, the base kept)
  let shown = 0;
  /** @type {"after" | "before" | "both"} */
  let view = "after";
  /** @type {AbortController | null} */
  let running = null;
  /** @type {BoardLine | null} */
  let best = null;
  let open = false;

  /** *Before*: the old board, or on an empty board the base the search began from. */
  const before = () => (circuit?.stripboard?.parts && Object.keys(circuit.stripboard.parts).length ? { ...figuresOf(circuit.stripboard), stripboard: circuit.stripboard } : base);

  stopButton.addEventListener("click", () => void stop());
  cancelButton.addEventListener("click", () => cancel());
  prev.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  another.addEventListener("click", () => void runTry());
  keepTry.addEventListener("click", () => {
    const made = tries[shown];
    close();
    app.keep(made.stripboard);
  });
  keepOld.addEventListener("click", () => {
    const old = before();
    const empty = old === base;
    close();
    if (empty && base) app.keep(base.stripboard); // an empty board: the base is the old board's place
  });

  /** One try: the next seed set, streamed; the best drawn as it comes. */
  async function runTry() {
    attempt += 1;
    best = null;
    const control = new AbortController();
    running = control;
    reviewBar.hidden = true;
    runWindow.hidden = false;
    dimNote.hidden = false;
    stopButton.disabled = true;
    stage.textContent = "Starting the board…";
    bar.removeAttribute("value");
    bestLine.textContent = "";
    left.textContent = "";
    let started = 0;
    const begun = performance.now();
    bar.classList.add("working");
    try {
      const made = await postProgress("api/stripboard/compact", { circuit, attempt, stand_up: standUp }, (done, of, line) => {
        if (running !== control) return;
        if (line.base) {
          base ??= line.base;
          stage.textContent = "Making it smaller…";
          if (!best) app.preview([{ stripboard: line.base.stripboard }], true);
          return;
        }
        bar.max = of;
        bar.value = done;
        if (!started && done) started = performance.now() - 1;
        if (started && done < of) left.textContent = leftText(((performance.now() - started) / 1000) * (of - done) / Math.max(done, 1), (performance.now() - begun) / 1000, expected);
        if (line.best) {
          best = line.best;
          stopButton.disabled = false;
          bestLine.textContent = `Best so far: ${figuresLine(line.best)}`;
          app.preview([{ stripboard: line.best.stripboard }], true);
        }
      }, fetch, control.signal);
      if (running === control) added(made);
    } catch (err) {
      if (running !== control) return; // stopped or cancelled: that path goes on
      running = null;
      app.refuse(/** @type {Error} */ (err).message);
      back();
    } finally {
      bar.classList.remove("working");
    }
  }

  /** *Stop and keep the best*: the run ended, its best board wired and checked. */
  async function stop() {
    const kept = best;
    running?.abort();
    running = null;
    if (!kept) return back();
    stage.textContent = "Wiring and checking the best board…";
    stopButton.disabled = cancelButton.disabled = true;
    try {
      added(await postJson("api/stripboard/compact/finish", { circuit, board: kept.stripboard }));
    } catch (err) {
      app.refuse(/** @type {Error} */ (err).message);
      back();
    } finally {
      cancelButton.disabled = false;
    }
  }

  /** *Cancel*: the run ended, nothing from it kept; back to the tries so far, or the board. */
  function cancel() {
    running?.abort();
    running = null;
    attempt -= 1; // the seed set wasn't tried
    back();
  }

  /** A try made: kept for the review, said when it's a board seen already. @param {Made} made */
  function added(made) {
    running = null;
    const same = sameTry(tries, made);
    tries.push(made);
    notes.push(same >= 0 ? `Same board as try ${same + 1}: ${SAME}` : made.note);
    shown = tries.length - 1;
    runWindow.hidden = true;
    dimNote.hidden = true;
    review();
  }

  function back() {
    runWindow.hidden = true;
    dimNote.hidden = true;
    if (tries.length) review();
    else close();
  }

  /** @param {number} by */
  function step(by) {
    shown = Math.max(0, Math.min(tries.length - 1, shown + by));
    review();
  }

  /** The review bar and the boards it shows. */
  function review() {
    const after = tries[shown];
    const old = before();
    const n = shown + 1;
    figures.textContent = old ? `Before ${figuresLine(old)} → After ${figuresLine(after)}` : `After ${figuresLine(after)}`;
    for (const [mode, b] of Object.entries(modes)) b.setAttribute("aria-pressed", String(mode === view));
    modes.before.disabled = modes.both.disabled = !old;
    tryText.textContent = `Try ${n} of ${tries.length}`;
    prev.disabled = shown === 0;
    next.disabled = shown === tries.length - 1;
    keepTry.textContent = `Keep try ${n}`;
    keepOld.textContent = old && old === base ? "Keep the base board" : "Keep the old board";
    said.textContent = notes[shown];
    said.hidden = !notes[shown];
    const opening = reviewBar.hidden;
    if (opening) column.scrollTop = 0; // opening: the review in sight
    reviewBar.hidden = false;
    if (opening) app.reviewing?.(true);
    const showing = view === "before" && old ? [{ stripboard: old.stripboard }]
      : view === "both" && old ? [{ stripboard: old.stripboard, title: `Before: ${figuresLine(old)}` }, { stripboard: after.stripboard, title: `After, try ${n}: ${figuresLine(after)}` }]
        : [{ stripboard: after.stripboard }];
    app.preview(showing, false);
  }

  /** Everything put away: the circuit's own board shown and editable again. */
  function close() {
    running?.abort();
    running = null;
    open = false;
    const reviewed = !reviewBar.hidden;
    runWindow.hidden = reviewBar.hidden = dimNote.hidden = true;
    if (reviewed) app.reviewing?.(false);
    app.preview(null, false);
    app.lock(false);
  }

  return {
    /**
     * Lay out the circuit as it is now: try 1, then the review.
     * @param {{seconds?: number, large?: string, standUp?: import("./board-logic.js").StandUp}} choice
     *   `seconds`: the time it said; `large`: the large-circuit line ("" or not said: none,
     *   P8 R3); `standUp`: standing parts (D-403; the board's own when not said)
     */
    start(choice) {
      circuit = app.circuit();
      standUp = choice.standUp ?? standUpOf(circuit?.stripboard);
      expected = choice.seconds ?? 0;
      largeLine.textContent = choice.large ?? "";
      largeLine.hidden = !choice.large;
      attempt = 0;
      base = null;
      tries = [];
      notes = [];
      view = "after";
      open = true;
      app.lock(true);
      void runTry();
    },
    /** Running or under review: the board locked. */
    active: () => open,
    close,
  };
}

