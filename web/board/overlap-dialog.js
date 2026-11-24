/**
 * The board's Decide… form for one overlap (DOM, P6h4, D-398): two bodies touching, or one
 * past the board's edge. Its hints first (a trimmer's screw, a socketed chip), then the
 * choices: Stand taller (which part, by how much if known), Bend out of the way (which
 * part, toward which side as the parts side shows it), Accept; a note for any. A part
 * chosen to stand taller fills in by how much from the server's suggestion (the other's
 * typical height and a clearance, D-398), unless the builder typed their own. The edge
 * takes Accept only. Keep waits until the choice is complete; Forget drops an earlier
 * decision. The view makes the edit; this only asks.
 */

import { ask } from "../editor/form.js";
import { h } from "../panels.js";
import { EDGE, SIDES, decisionFrom, fixChoices, fixValues, tallerMm } from "./board-logic.js";

/** The form's Keep button (there once `ask` has opened it). */
const keep = () => /** @type {HTMLButtonElement} */ (document.querySelector("#overlap-dialog button[data-answer='keep']"));

/**
 * Ask what to do about an overlap: the decision to keep, `forget` (an earlier one dropped),
 * or null when cancelled.
 * @param {import("./board-logic.js").Overlap} overlap
 * @param {import("./board-logic.js").Decision | null} earlier its decision now, to change
 * @returns {Promise<{decision: Record<string, unknown>} | {forget: true} | null>}
 */
export async function decideOverlap(overlap, earlier) {
  const [a, b] = overlap.parts;
  const values = fixValues(earlier);
  const refresh = () => {
    keep().disabled = decisionFrom(overlap, values) === null;
    for (const [fix, extra] of extras) extra.hidden = values.fix !== fix;
  };
  /** Which of the two, as radios. @param {string} name */
  const which = (name) => h("span", { class: "overlap-which" }, ["Which: ", ...[a, b].map((ref) => {
    const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name, value: ref }));
    radio.checked = values.part === ref;
    radio.addEventListener("change", () => {
      values.part = ref;
      mm.value = values.mm = tallerMm(overlap, ref, mm.value, shown);
      shown = mm.value === String(overlap.taller?.[ref] ?? "") ? mm.value : "";
      for (const other of document.querySelectorAll(`#overlap-dialog input[value="${CSS.escape(ref)}"]`)) /** @type {HTMLInputElement} */ (other).checked = true;
      refresh();
    });
    return h("label", {}, [radio, ` ${ref}`]);
  })]);
  let shown = ""; // the suggestion last filled in (replaced when the part changes)
  const mm = /** @type {HTMLInputElement} */ (h("input", { type: "text", inputmode: "decimal", id: "overlap-mm", size: "4", value: values.mm, "aria-label": "How much taller, in mm" }));
  mm.addEventListener("input", () => {
    values.mm = mm.value;
    refresh();
  });
  const side = /** @type {HTMLSelectElement} */ (h("select", { id: "overlap-toward", "aria-label": "Toward" }, [
    h("option", { value: "" }, ["choose…"]),
    ...SIDES.map((s) => h("option", { value: s }, [s])),
  ]));
  side.value = values.toward ?? "";
  side.addEventListener("change", () => {
    values.toward = side.value || null;
    refresh();
  });
  /** @type {Map<string, HTMLElement>} */
  const extras = new Map([
    ["taller", h("div", { class: "overlap-extra" }, [which("which-taller"), h("label", {}, [" By ", mm, " mm (if you know)"])])],
    ["bent", h("div", { class: "overlap-extra" }, [which("which-bent"), h("label", { title: "As the parts side shows the board" }, [" Toward ", side])])],
  ]);
  const rows = fixChoices(overlap).flatMap((c) => {
    const radio = /** @type {HTMLInputElement} */ (h("input", { type: "radio", name: "overlap-fix", value: c.value }));
    radio.checked = values.fix === c.value;
    radio.addEventListener("change", () => {
      values.fix = c.value;
      refresh();
    });
    const row = h("label", { class: "layout-choice", "data-fix": c.value }, [
      radio, h("span", { class: "layout-name" }, [c.label]), h("span", { class: "layout-text" }, [c.text]),
    ]);
    const extra = extras.get(c.value);
    return extra ? [row, extra] : [row];
  });
  const note = /** @type {HTMLInputElement} */ (h("input", { type: "text", id: "overlap-note", value: values.note, placeholder: "e.g. sleeve the leg", "aria-label": "Note" }));
  note.addEventListener("input", () => {
    values.note = note.value;
    refresh();
  });
  const edge = b === EDGE;
  const asked = ask({
    id: "overlap-dialog",
    title: edge ? `${a} hangs ${overlap.mm} mm past the edge` : `${a} and ${b} touch (${overlap.mm} mm)`,
    text: edge ? "It's about the enclosure: nothing bends past the edge." : "Decide what you'll do when you build it. It goes on the build sheet.",
    cancel: "cancel",
    body: () => [
      ...(overlap.hints.length ? [h("ul", { class: "overlap-hints" }, overlap.hints.map((t) => h("li", {}, [t])))] : []),
      h("div", { class: "layout-choices", role: "radiogroup", "aria-label": "What to do" }, rows),
      h("label", { class: "overlap-note" }, ["Note ", note]),
    ],
    buttons: [
      ...(earlier ? [{ label: "Forget it", value: /** @type {const} */ ("forget"), kind: /** @type {const} */ ("aside") }] : []),
      { label: "Cancel", value: "cancel" },
      { label: "Keep", value: "keep", kind: "primary" },
    ],
  });
  refresh();
  const answer = await asked;
  if (answer === "forget") return { forget: true };
  const decision = answer === "keep" ? decisionFrom(overlap, values) : null;
  return decision ? { decision } : null;
}
