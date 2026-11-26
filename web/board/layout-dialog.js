/**
 * *Lay it out for me*'s confirmation (DOM, P8 R3; the Layout dialog it replaced offered
 * Start a board, Fill the rest, Tidy up and Thorough too): what it replaces, how long it
 * takes on this machine (asked for as it opens, filled in when known), that it can stop
 * early, that the layout is a draft (the large-circuit line, or what counts as large), and
 * *Standing resistors and diodes* (D-403), set to the board's own. The view does the work;
 * this only asks.
 */

import { ask } from "../editor/form.js";
import { h } from "../panels.js";
import { STAND_UP, largeText, layOutWords } from "./board-logic.js";

/**
 * @typedef {{seconds: number, parts: number, large: number}} Estimate the time on this
 *   machine, the board parts and how many count as large (the server's)
 */

/**
 * Confirm *Lay it out for me*: null when cancelled.
 * @param {{board: {parts: unknown[], cuts: unknown[], links: unknown[], wires: unknown[]}, estimate: Promise<Estimate | null>,
 *   standUp: import("./board-logic.js").StandUp}} now what's on the board, the estimate (null:
 *   not known), and the board's choice for standing parts
 * @returns {Promise<{seconds: number, large: string, standUp: import("./board-logic.js").StandUp} | null>}
 *   `large`: the large-circuit line ("" for a smaller circuit), for the running window
 */
export async function confirmLayOut(now) {
  let standUp = now.standUp;
  /** @type {Estimate | null} */
  let estimate = null;
  const first = layOutWords(now.board);
  const takes = h("p", { class: "ask-text layout-takes" }, [first.takes]);
  const draft = h("p", { class: "ask-text layout-draft" }, [first.draft]);
  void now.estimate.then((e) => {
    estimate = e;
    const said = layOutWords(now.board, e);
    takes.textContent = said.takes;
    draft.textContent = said.draft;
  });
  const standing = h("div", { class: "layout-standing", role: "radiogroup", "aria-label": "Standing resistors and diodes" }, [
    h("span", { class: "layout-name" }, ["Standing resistors and diodes"]),
    ...STAND_UP.map((s) => {
      const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name: "layout-stand", value: s.value }));
      radio.checked = s.value === standUp;
      radio.addEventListener("change", () => (standUp = s.value));
      return h("label", { class: "layout-stand", title: s.text }, [radio, " ", s.label]);
    }),
  ]);
  const answer = await ask({
    id: "layout-dialog",
    title: "Lay it out for me",
    text: first.text,
    cancel: "cancel",
    body: () => [takes, draft, standing],
    buttons: [
      { label: "Cancel", value: "cancel" },
      { label: "Lay it out", value: "layout", kind: "primary" },
    ],
  });
  if (answer !== "layout") return null;
  const e = /** @type {Estimate | null} */ (estimate);
  return { seconds: e?.seconds ?? 0, large: e ? largeText(e.parts, e.large) : "", standUp };
}
