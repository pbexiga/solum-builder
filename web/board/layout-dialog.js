/**
 * The board's Layout dialog (DOM, P6h2): one radio list of the layout help, Start a board
 * (with *Make the board compact* under it), Fill the rest and Tidy up, each with a line
 * saying what it does and greyed with the reason when it can't be used; then a
 * confirmation saying what will happen. Nothing is chosen at first once parts are placed:
 * Continue waits for a choice. The tick is remembered per viewer.
 * The view does the work; this only asks.
 */

import { ask, confirmed } from "../editor/form.js";
import { h } from "../panels.js";
import { remember, remembered } from "../storage.js";
import { layoutChoices, layoutConfirm, layoutDefault } from "./board-logic.js";

/** The dialog's Continue button (there once `ask` has opened it). */
const go = () => /** @type {HTMLButtonElement} */ (document.querySelector("#layout-dialog button[data-answer='go']"));
const COMPACT_KEY = "solum.boardCompact"; // Make the board compact, this browser's

/**
 * Ask which layout help to run, then confirm it: null when cancelled at either step.
 * @param {{board: {parts: unknown[], cuts: unknown[], links: unknown[], wires: unknown[]}, toPlace: number}} now
 *   what's on the board and how many parts are still in the tray
 * @returns {Promise<{choice: import("./board-logic.js").LayoutChoice, compact: boolean} | null>}
 */
export async function chooseLayout(now) {
  const placed = now.board.parts.length > 0;
  let choice = layoutDefault(placed);
  let compact = remembered(COMPACT_KEY) === true;
  const tick = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", id: "layout-compact" }));
  tick.checked = compact;
  tick.addEventListener("change", () => (compact = tick.checked));
  const rows = layoutChoices(placed).map((c) => {
    const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name: "layout", value: c.value }));
    radio.checked = c.value === choice;
    radio.disabled = Boolean(c.why);
    radio.addEventListener("change", () => {
      choice = c.value;
      tick.disabled = choice !== "start";
      go().disabled = false;
    });
    const row = h("label", { class: c.why ? "layout-choice greyed" : "layout-choice", "data-layout": c.value }, [
      radio,
      h("span", { class: "layout-name" }, [c.label]),
      h("span", { class: "layout-text" }, [c.why || c.text]),
    ]);
    if (c.value !== "start") return [row];
    const under = h("label", { class: "layout-compact", title: "Tidy up straight after: smaller, but slower on a big board" }, [tick, " Make the board compact"]);
    return [row, under];
  });
  tick.disabled = choice !== "start";
  const asked = ask({
    id: "layout-dialog",
    title: "Layout",
    text: "Let the app lay the board out for you, or part of it.",
    cancel: "cancel",
    body: () => [h("div", { class: "layout-choices", role: "radiogroup", "aria-label": "Layout" }, rows.flat())],
    buttons: [
      { label: "Cancel", value: "cancel" },
      { label: "Continue", value: "go", kind: "primary" },
    ],
  });
  go().disabled = choice === null; // parts placed: nothing chosen until the builder picks
  const answer = await asked;
  if (answer !== "go" || choice === null) return null;
  if (choice === "start") remember(COMPACT_KEY, compact);
  const said = layoutConfirm(choice, choice === "start" && compact, now.board, now.toPlace);
  if (!(await confirmed(said.title, said.text, said.label, "layout"))) return null;
  return { choice, compact: choice === "start" && compact };
}
