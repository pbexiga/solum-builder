/**
 * The History button in the header and its pane (D-101): the circuit's undo steps,
 * newest first, the current one lit and undone ones dimmed; a click goes to that step.
 * While Edit curve is on, its steps sit under "Edit curve (in progress)" and older ones are
 * greyed (out of reach until Keep or Discard). It follows every change while open. While
 * Edit curve is on the button wears the accent outline, and hovering it shows a small card
 * saying so (`note` puts a message in that card for a moment). The steps come from
 * `History.rows()` (`editor/history.js`); this is only the DOM.
 */

import { h } from "./panels.js";

/**
 * @typedef {ReturnType<import("./editor/history.js").History<any>["rows"]>[number]} Row
 * @param {HTMLButtonElement} button
 * @param {{rows: () => Row[], go: (steps: number) => void, session: () => {name: string, source: string} | null}} deps `go`: that many redos (+) or undos (−); `session`: the edit session open (Edit curve, or a bias fix: D-119)
 */
export function historyPane(button, deps) {
  // the card under the button while Edit curve is on: what that means, and how far it has gone
  const tip = h("div", { class: "history-tip", id: "history-tip", hidden: "", role: "status" });
  /** @type {ReturnType<typeof setTimeout> | undefined} */ let noteTimer;
  let noting = false;
  button.addEventListener("pointerenter", () => {
    if (deps.session() && pane.hidden && !noting) showTip(editingCard());
  });
  button.addEventListener("pointerleave", () => noting || hideTip());
  button.addEventListener("click", () => noting || hideTip());

  function editingCard() {
    const steps = deps.rows().filter((r) => r.session && r.kind !== "undone").length;
    const curve = deps.session()?.source === "curve";
    return [
      h("strong", {}, [curve ? "You're editing the curve" : `You're trying ${deps.session()?.name ?? "a change"}`]),
      h("p", {}, [curve
        ? "Every change, in the curve editor or on the schematic, waits for its Keep changes or Discard changes."
        : "Every change, in the Bias & headroom pane or on the schematic, waits for its Keep or Discard."]),
      h("p", { class: "history-tip-count" }, [
        steps ? `${steps} step${steps > 1 ? "s" : ""} so far. Ctrl+Z goes back through them, as far as where you started.` : "No steps yet. Ctrl+Z won't go back past where you started.",
      ]),
      h("p", { class: "history-tip-more" }, ["Click to see the steps."]),
    ];
  }

  /** @param {Node[]} body */
  function showTip(body) {
    tip.replaceChildren(...body);
    tip.hidden = false;
  }

  function hideTip() {
    tip.hidden = true;
  }

  /**
   * A message in the card for a moment, the button lit (Ctrl+Z at the start of Edit curve).
   * @param {string} text
   */
  function note(text) {
    noting = true;
    showTip([h("strong", {}, [text])]);
    button.classList.remove("noting");
    void button.offsetWidth; // restarts the light on a second press
    button.classList.add("noting");
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => {
      noting = false;
      button.classList.remove("noting");
      hideTip();
    }, 2500);
  }
  const list = h("ul", { class: "history-rows", id: "history-rows" });
  const pane = h("div", { class: "history-pane", id: "history-pane", hidden: "", role: "dialog", "aria-label": "History" }, [
    h("p", { class: "history-hint" }, ["Newest first. Click a step to go back (or forward) to it; Ctrl+Z / Ctrl+Shift+Z step one at a time."]),
    list,
  ]);
  button.after(pane, tip);
  button.setAttribute("aria-expanded", "false");
  button.addEventListener("click", () => (pane.hidden ? open() : close()));
  document.addEventListener("pointerdown", (e) => {
    const t = /** @type {Node} */ (e.target);
    if (!pane.hidden && !pane.contains(t) && !button.contains(t)) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !pane.hidden) {
      e.stopImmediatePropagation(); // Esc closes the pane, nothing else
      close();
    }
  }, true);

  function open() {
    pane.hidden = false;
    button.setAttribute("aria-expanded", "true");
    update();
    list.querySelector(".current")?.scrollIntoView({ block: "nearest" });
  }

  function close() {
    pane.hidden = true;
    button.setAttribute("aria-expanded", "false");
  }

  /** Draw the steps again (only while open: it's cheap, but nothing to see shut). */
  function update() {
    if (pane.hidden) return;
    const all = deps.rows();
    const session = all.some((r) => r.session || r.locked);
    const open = deps.session();
    const name = open?.name ?? "Frequency curve";
    // in a session, redo steps from before it can't be reached (and go with its first change): not shown
    const rows = session ? all.filter((r) => !(r.kind === "undone" && r.locked)) : all;
    /** @type {HTMLElement[]} */
    const items = [];
    let heading = false;
    let fence = false;
    for (const r of rows) {
      if (session && r.session && !heading) {
        items.push(h("li", { class: "history-heading" }, [`${name} (in progress)`]));
        heading = true;
      }
      if (session && !r.session && !fence) {
        items.push(h("li", { class: "history-heading" }, [rows.some((x) => x.locked) ? `Before ${name}: Keep or Discard to go further back` : `Before ${name}`]));
        fence = true;
      }
      const tag = r.session && r.source !== open?.source ? [h("span", { class: "tag" }, [`outside ${name}`])] : [];
      const b = h("button", { type: "button", class: `history-step ${r.kind}`, ...(r.locked ? { disabled: "" } : {}), "data-go": String(r.go) },
        [r.label, ...tag]);
      if (!r.locked && r.go !== 0) b.addEventListener("click", () => deps.go(r.go));
      items.push(h("li", { class: r.kind }, [b]));
    }
    list.replaceChildren(...items);
  }

  return { open, close, update, note };
}
