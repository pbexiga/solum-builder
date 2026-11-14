/**
 * The refusal bar (D-335): an edit the server refuses is undone, and why it was refused
 * shows over the foot of the canvas, where the edit was made, until it times out or is
 * closed. A new refusal takes the old one's place. Errors about the circuit as it stands
 * (a run that failed, a circuit that won't simulate) stay in the Results column.
 */

import { h } from "./panels.js";

/** How long a refusal shows (paused while the pointer is over it). */
export const REFUSAL_MS = 7000;

/**
 * @param {HTMLElement} el the bar's place, over the canvas
 * @returns {{show: (message: string) => void, hide: () => void}}
 */
export function refusalBar(el) {
  let timer = 0;
  const text = h("span", { class: "refusal-text" });
  const close = h("button", { type: "button", class: "refusal-close", title: "Close", "aria-label": "Close" }, ["×"]);
  el.replaceChildren(text, close);
  const hide = () => {
    clearTimeout(timer);
    el.hidden = true;
  };
  const wait = () => {
    clearTimeout(timer);
    timer = window.setTimeout(hide, REFUSAL_MS);
  };
  close.addEventListener("click", hide);
  el.addEventListener("mouseenter", () => clearTimeout(timer));
  el.addEventListener("mouseleave", wait);
  return {
    show(message) {
      text.textContent = message;
      el.hidden = false;
      el.classList.remove("pulse");
      void el.offsetWidth; // restart the pulse when a refusal follows another
      el.classList.add("pulse");
      wait();
    },
    hide,
  };
}
