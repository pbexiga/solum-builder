/**
 * The check before a version becomes final (DOM, D-362): Mark as final and New major
 * version… run Export's Ready to build check on the last save (`readyRows`, the same
 * function, D-203) and, when anything is open, list it with Mark as final anyway / Cancel.
 */

import { getJson } from "./api.js";
import { ask } from "./editor/form.js";
import { exportTarget, exportUrl, readyRows } from "./export-logic.js";
import { dismissedNote, readyList } from "./export.js";

/**
 * Whether to go on making the open version final: true with nothing open, or when the
 * person chose *Mark as final anyway*. A row naming parts closes the window, answers false
 * and hands its first part to `onPick`. A block has no build check, so it goes through.
 * @param {{source: {kind: string, id: string} | null, name: string, version: string,
 *   dismissed?: import("./problems.js").Dismissal[], onPick: (ref: string) => void}} open
 * @returns {Promise<boolean>}
 */
export async function readyForFinal(open) {
  const target = exportTarget(open.source);
  if ("why" in target) return true;
  /** @type {import("./export-logic.js").ReadyRow[]} */ let rows;
  let dismissed = 0;
  try {
    // the last save is what becomes final: Mark as final needs it saved, New major asks first
    ({ rows, dismissed } = readyRows(await getJson(`${exportUrl(target)}/check`), { dirty: false, dismissed: open.dismissed }));
  } catch (err) {
    rows = [{ severity: "warning", text: `Couldn't check the last save: ${/** @type {Error} */ (err).message}`, refs: [] }];
  }
  if (!rows.length) return true;
  /** @type {string | null} */ let picked = null;
  const choice = await ask({
    id: "final-check",
    title: `“${open.name}” ${open.version} has something outstanding`,
    text: "Fix it first, dismiss it in the Problems panel, or mark it final anyway. Click a row to go to its part.",
    cancel: "cancel",
    body: (answer) => [
      ...readyList(rows, (ref) => {
        picked = ref;
        answer("cancel");
      }),
      ...dismissedNote(dismissed),
    ],
    buttons: [
      // the safe answer has the focus: Enter never makes a version final past its problems
      { label: "Mark as final anyway", value: "anyway", kind: "aside" },
      { label: "Cancel", value: "cancel", kind: "primary" },
    ],
  });
  if (picked) open.onPick(picked);
  return choice === "anyway";
}
