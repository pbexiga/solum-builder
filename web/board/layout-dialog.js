/**
 * The board's Layout dialog (DOM, P6h2): one radio list of the layout help, Start a board
 * (with *Make the board compact* under it), Fill the rest and Tidy up, each with a line
 * saying what it does and greyed with the reason when it can't be used; then a
 * confirmation saying what will happen. Nothing is chosen at first once parts are placed:
 * Continue waits for a choice. Below a divider, *Build a full layout* (D-399) with Quick and
 * Thorough under it, each with its time on this machine (asked for as the dialog opens),
 * and two notes. Last, *Standing resistors and diodes* (D-403) for whichever choice runs,
 * set to the board's own. The tick and Quick / Thorough are remembered per viewer.
 * The view does the work; this only asks.
 */

import { ask, confirmed } from "../editor/form.js";
import { h } from "../panels.js";
import { remember, remembered } from "../storage.js";
import { FULL_NOTES, STAND_UP, layoutChoices, layoutConfirm, layoutDefault, timeText } from "./board-logic.js";

/** The dialog's Continue button (there once `ask` has opened it). */
const go = () => /** @type {HTMLButtonElement} */ (document.querySelector("#layout-dialog button[data-answer='go']"));
const COMPACT_KEY = "solum.boardCompact"; // Make the board compact, this browser's
const THOROUGH_KEY = "solum.boardThorough"; // Build a full layout: Thorough, this browser's

/**
 * Ask which layout help to run, then confirm it: null when cancelled at either step.
 * @param {{board: {parts: unknown[], cuts: unknown[], links: unknown[], wires: unknown[]}, toPlace: number,
 *   times: Promise<{quick: number, thorough: number} | null>, standUp: import("./board-logic.js").StandUp}} now
 *   what's on the board, how many parts are still in the tray, *Build a full layout*'s
 *   times on this machine (null: not known), and the board's choice for standing parts
 * @returns {Promise<{choice: import("./board-logic.js").LayoutChoice, compact: boolean, thorough: boolean, seconds: number,
 *   standUp: import("./board-logic.js").StandUp} | null>}
 */
export async function chooseLayout(now) {
  const placed = now.board.parts.length > 0;
  let choice = layoutDefault(placed);
  let compact = remembered(COMPACT_KEY) === true;
  let thorough = remembered(THOROUGH_KEY) === true;
  let standUp = now.standUp;
  /** @type {{quick: number, thorough: number} | null} */
  let times = null;
  const tick = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", id: "layout-compact" }));
  tick.checked = compact;
  tick.addEventListener("change", () => (compact = tick.checked));
  /** Quick or Thorough, with its time once known. @param {boolean} long @param {string} label @param {string} text */
  const speed = (long, label, text) => {
    const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name: "layout-speed", value: long ? "thorough" : "quick" }));
    radio.checked = long === thorough;
    radio.addEventListener("change", () => (thorough = long));
    const time = h("span", { class: "layout-time", "data-time": long ? "thorough" : "quick" }, ["Working out the time…"]);
    return { radio, time, row: h("label", { class: "layout-speed" }, [radio, h("span", { class: "layout-name" }, [label]), " ", time, h("span", { class: "layout-text" }, [text])]) };
  };
  const quick = speed(false, "Quick", "Good for most circuits.");
  const slow = speed(true, "Thorough", "It looks four times as long. Worth it for big circuits (40 parts or more), which keep getting smaller the longer it looks.");
  void now.times.then((t) => {
    times = t;
    quick.time.textContent = t ? `${timeText(t.quick)}.` : "";
    slow.time.textContent = t ? `${timeText(t.thorough)}.` : "";
  });
  const speeds = [quick, slow];
  const rows = layoutChoices(placed).map((c) => {
    const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name: "layout", value: c.value }));
    radio.checked = c.value === choice;
    radio.disabled = Boolean(c.why);
    radio.addEventListener("change", () => {
      choice = c.value;
      tick.disabled = choice !== "start";
      for (const s of speeds) s.radio.disabled = choice !== "full";
      go().disabled = false;
    });
    const row = h("label", { class: c.why ? "layout-choice greyed" : "layout-choice", "data-layout": c.value }, [
      radio,
      h("span", { class: "layout-name" }, [c.label]),
      h("span", { class: "layout-text" }, [c.why || c.text]),
    ]);
    if (c.value === "full") {
      return [h("hr", { class: "layout-divider" }), row, quick.row, slow.row,
        ...FULL_NOTES.map((note) => h("p", { class: "layout-note" }, [note]))];
    }
    if (c.value !== "start") return [row];
    const under = h("label", { class: "layout-compact", title: "Tidy up straight after: smaller, but slower on a big board" }, [tick, " Make the board compact"]);
    return [row, under];
  });
  tick.disabled = choice !== "start";
  for (const s of speeds) s.radio.disabled = choice !== "full";
  const standing = h("div", { class: "layout-standing", role: "radiogroup", "aria-label": "Standing resistors and diodes" }, [
    h("span", { class: "layout-name" }, ["Standing resistors and diodes"]),
    ...STAND_UP.map((s) => {
      const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name: "layout-stand", value: s.value }));
      radio.checked = s.value === standUp;
      radio.addEventListener("change", () => (standUp = s.value));
      return h("label", { class: "layout-stand", title: s.text }, [radio, " ", s.label]);
    }),
  ]);
  const asked = ask({
    id: "layout-dialog",
    title: "Layout",
    text: "Let the app lay the board out for you, or part of it.",
    cancel: "cancel",
    body: () => [h("div", { class: "layout-choices", role: "radiogroup", "aria-label": "Layout" }, rows.flat()), h("hr", { class: "layout-divider" }), standing],
    buttons: [
      { label: "Cancel", value: "cancel" },
      { label: "Continue", value: "go", kind: "primary" },
    ],
  });
  go().disabled = choice === null; // parts placed: nothing chosen until the builder picks
  const answer = await asked;
  if (answer !== "go" || choice === null) return null;
  if (choice === "start") remember(COMPACT_KEY, compact);
  if (choice === "full") remember(THOROUGH_KEY, thorough);
  const seconds = times ? (thorough ? times.thorough : times.quick) : 0;
  const said = layoutConfirm(choice, choice === "start" && compact, now.board, now.toPlace, seconds);
  if (!(await confirmed(said.title, said.text, said.label, "layout"))) return null;
  return { choice, compact: choice === "start" && compact, thorough: choice === "full" && thorough, seconds, standUp };
}
