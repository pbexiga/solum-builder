/**
 * The inspector's sliders (DOM, D-081): a range over a part's value or rotation steps (the
 * server's, `solum/live.py`), the steps' ends, and for a value off its series the nearest
 * series value to snap to. Logic is in `live.js`; what a move does
 * is up to the handlers.
 */

import { h } from "../panels.js";

/**
 * @typedef {import("../live.js").Slider} Slider
 * @typedef {{onInput: (index: number) => void, onCommit: (index: number) => unknown,
 *   onSnap: (value: string) => void}} Handlers `onCommit` may give back a promise: until
 *   it settles (the re-run drawn) the slider ignores the keys that step it (round 2)
 */

/** The keys that move a range a step or more. */
const STEP_KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"]);

/** Each field's slider: its element id, row label and what it spans (for screen readers). */
const KINDS = {
  value: { id: "value-slider", label: "Slide", span: "from a tenth to ten times" },
  rotation: { id: "rotation-slider", label: "Turn", span: "from 0 to 100 %" },
};

/**
 * A slider row for a part's value or rotation, disabled until `show` gives it its steps.
 * `prefix` goes before its element ids, so a second slider elsewhere (an influence row,
 * D-097) doesn't share the inspector's.
 * @param {"value" | "rotation"} field @param {string} label @param {Handlers} handlers @param {string} [prefix]
 * @param {string} [shown] the row's label (default "Slide" or "Turn"; a part's ref where sliders share a row)
 * `seek(i)` moves it from elsewhere (an Edit mode handle) as a drag would; `place(i)` only
 * moves the thumb (the caller draws); `release()` lets it go there. While a commit's
 * re-run is drawn the arrow keys do nothing (round 2).
 * @returns {{row: HTMLElement, show: (slider: Slider) => void, fail: (message: string) => void,
 *   seek: (index: number) => void, place: (index: number) => void, release: () => void}}
 */
export function valueSlider(field, label, handlers, prefix = "", shown = "") {
  const kind = { ...KINDS[field], id: `${prefix}${KINDS[field].id}` };
  const range = /** @type {HTMLInputElement} */ (h("input", { type: "range", id: kind.id, min: "0", max: "0", step: "1", value: "0", disabled: "", "aria-label": `${label}, ${kind.span}` }));
  const ends = h("span", { class: "slider-ends", id: `${kind.id}-ends` }, ["…"]);
  const snap = h("button", { type: "button", class: "slider-snap", id: `${kind.id}-snap`, hidden: "" });
  let pending = false; // a commit's re-run not drawn yet: the keys wait
  range.addEventListener("keydown", (e) => {
    if (pending && STEP_KEYS.has(e.key)) e.preventDefault();
  });
  range.addEventListener("input", () => handlers.onInput(Number(range.value)));
  range.addEventListener("change", () => commit());
  /** Tell the handler; hold the keys, greyed (`.running`), while what it gives back runs. */
  function commit() {
    const ran = handlers.onCommit(Number(range.value));
    if (!(ran instanceof Promise)) return;
    busy(true);
    ran.finally(() => busy(false)).catch(() => {});
  }
  /** @param {boolean} on */
  function busy(on) {
    pending = on;
    row.classList.toggle("running", on);
    range.setAttribute("aria-busy", String(on));
  }
  snap.addEventListener("click", () => handlers.onSnap(/** @type {string} */ (snap.dataset.value)));
  const row = h("div", { class: "form-row slider-row" }, [h("label", { for: kind.id }, [shown || kind.label]), range, h("span", { class: "unit" }), ends, snap]);
  return {
    row,
    show(slider) {
      range.max = String(slider.steps.length - 1);
      range.value = String(slider.index);
      range.disabled = false;
      ends.textContent = `${slider.steps[0].text} – ${slider.steps[slider.steps.length - 1].text}`;
      snap.hidden = !slider.nearest;
      snap.dataset.value = slider.nearest ?? "";
      snap.textContent = slider.nearest ? `${slider.series}: ${slider.nearest}` : "";
      snap.title = slider.nearest ? `Snap to the nearest ${slider.series} value` : "";
    },
    fail(message) {
      range.disabled = true;
      ends.textContent = message;
    },
    seek(index) {
      range.value = String(index);
      handlers.onInput(index);
    },
    place(index) {
      range.value = String(index);
    },
    release() {
      commit();
    },
  };
}
