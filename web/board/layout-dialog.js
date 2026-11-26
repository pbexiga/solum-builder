/**
 * *Lay it out for me*'s confirmation (DOM, P8 R3; the Layout dialog it replaced offered
 * Start a board, Fill the rest, Tidy up and Thorough too): what it replaces, that it can
 * stop early, that the layout is a draft, and *Standing resistors and diodes* (D-403), set
 * to the board's own. It waits for nothing, so its words never change once open; the time
 * and the large-circuit line are the running window's. The view does the work; this only
 * asks.
 */

import { ask } from "../editor/form.js";
import { h } from "../panels.js";
import { STAND_UP, layOutWords } from "./board-logic.js";

/**
 * Confirm *Lay it out for me*: null when cancelled.
 * @param {{board: {parts: unknown[], cuts: unknown[], links: unknown[], wires: unknown[]},
 *   standUp: import("./board-logic.js").StandUp}} now what's on the board and the board's
 *   choice for standing parts
 * @returns {Promise<{standUp: import("./board-logic.js").StandUp} | null>}
 */
export async function confirmLayOut(now) {
  let standUp = now.standUp;
  const first = layOutWords(now.board);
  const takes = h("p", { class: "ask-text layout-takes" }, [first.takes]);
  const draft = h("p", { class: "ask-text layout-draft" }, [first.draft]);
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
  return { standUp };
}
