/**
 * The guitar form's five pickup boxes (DOM, D-363): Coil R, L, C, Peak and Q, any three
 * set and the other two worked out. As you type, the boxes typed (oldest first) go to the
 * server (`/api/pickup`), which says which three are set, the other two's values (shown
 * muted in their empty boxes, as ≈ 151p), the box that can't complete it (dimmed, its
 * title saying why; typing into it is refused with that reason) and the line under them.
 * The browser keeps only the typing order.
 */

import { postJson } from "./api.js";
import { h } from "./panels.js";

/** @typedef {import("./editor/fields.js").PickupAnswer} PickupAnswer */

const NAMES = ["r", "l", "c", "peak", "q"];
const WAIT_MS = 150; // typing pauses this long before the server is asked

/**
 * @param {HTMLFormElement} form the guitar's open form
 * @param {{order: string[], showError: (message: string | null) => void, post?: (url: string, body: unknown) => Promise<any>}} opts
 *   `order`: the three set as it opens, oldest first
 * @returns {{settle: () => Promise<PickupAnswer | string>}} `settle`: the answer for the boxes as
 *   they are now, or the reason they can't be used (for Apply)
 */
export function pickupBoxes(form, { order, showError, post = postJson }) {
  const box = (/** @type {string} */ n) => /** @type {HTMLInputElement} */ (form.querySelector(`input[name="pickup_${n}"]`));
  const source = /** @type {HTMLSelectElement} */ (form.querySelector('select[name="source"]'));
  const rowOf = (/** @type {string} */ n) => /** @type {HTMLElement} */ (box(n).closest(".form-row"));
  const line = h("p", { class: "pickup-line", id: "pickup-line", "aria-live": "polite" });
  rowOf("q").after(line);
  let typed = order.filter((n) => box(n).value.trim());
  /** @type {PickupAnswer | null} */
  let answer = null;
  /** @type {Promise<PickupAnswer | string>} */
  let pending = Promise.resolve("");
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let timer;
  let saying = false; // the error line is ours
  let asked = 0; // requests sent; only the latest one's answer is shown
  let fresh = false; // the answer shown is for the boxes as they are

  const say = (/** @type {string | null} */ message) => {
    if (message || saying) showError(message);
    saying = Boolean(message);
  };
  const showLine = () => (line.hidden = source.value === "ideal");

  /** @param {PickupAnswer} a */
  function show(a) {
    answer = a;
    typed = Object.keys(a.set);
    for (const n of NAMES) {
      const b = box(n);
      const set = n in a.set;
      if (!set && b.value) b.value = ""; // a fourth typed: the oldest is worked out now
      b.placeholder = a.shown[n] ? `≈ ${a.shown[n]}` : "";
      rowOf(n).classList.toggle("worked-out", !set && n in a.shown);
      rowOf(n).classList.toggle("dimmed", n in a.dimmed);
      b.title = a.dimmed[n] ?? "";
    }
    line.textContent = a.line;
  }

  /** Ask the server about the boxes as they are. @returns {Promise<PickupAnswer | string>} */
  function ask() {
    timer = undefined;
    const mine = ++asked;
    const latest = () => mine === asked;
    pending = post("/api/pickup", { typed: typed.map((n) => [n, box(n).value]) }).then(
      (a) => {
        if (!latest()) return pending;
        show(a);
        fresh = true;
        say(null);
        return a;
      },
      (err) => {
        if (!latest()) return pending;
        say(err.message);
        return /** @type {string} */ (err.message);
      },
    );
    return pending;
  }

  for (const n of NAMES) {
    box(n).addEventListener("input", () => {
      const why = fresh ? answer?.dimmed[n] : undefined; // an answer for boxes since changed doesn't count
      if (why && box(n).value) { // L, C and the peak can't fix it
        box(n).value = "";
        say(why);
        return;
      }
      typed = [...typed.filter((t) => t !== n), ...(box(n).value.trim() ? [n] : [])];
      fresh = false;
      clearTimeout(timer);
      timer = setTimeout(ask, WAIT_MS);
    });
  }
  source.addEventListener("change", () => { // a measured pickup fills R, L and C
    showLine();
    if (source.value === "ideal" || source.value === "custom") return;
    typed = ["r", "l", "c"];
    fresh = false;
    void ask();
  });
  showLine();
  void ask();
  return {
    settle: () => {
      if (timer === undefined) return pending;
      clearTimeout(timer);
      return ask();
    },
  };
}
