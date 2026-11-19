/**
 * The Frequency plot's view (P5, D-366), DOM: the Pin button and its chip on the pane's
 * title bar (*pinned: R7·Q1.B ×*), the one-line note when a pinned net goes, the lines
 * hidden from the plot's key, and the zoom (a drag across the plot; Reset zoom or a
 * double-click goes back), one for the pane and one for its large view. A view setting:
 * none of it is an edit or in Undo. Logic is in `frequency-view-logic.js`.
 */

import { hiddenLabels, pinGone, roleOf, visibleOnly, withPinned, zoomRange, zoomText } from "./frequency-view-logic.js";
import { h } from "./panels.js";

/**
 * @typedef {{
 *   selectedNet: () => string | null,
 *   expanded: () => boolean,
 *   editing: () => boolean,
 *   redraw: () => void,
 *   rerun: () => void,
 * }} Deps `selectedNet`: the net the selection's curve shows now (the output with nothing
 *   selected); `redraw`: draw the panes again from the run there is; `rerun`: a new run (a
 *   pinned net's curve isn't in the last one)
 */

/**
 * @param {{panel: HTMLDetailsElement, tools: HTMLElement, note: HTMLElement}} els
 * @param {Deps} deps
 */
export function frequencyView(els, deps) {
  /** @type {string | null} */ let pinned = null;
  /** @type {Set<string>} roles hidden from the plot's key */ const hidden = new Set();
  /** @type {{panel: {range: [number, number], text: string} | null, large: {range: [number, number], text: string} | null}} */
  const zooms = { panel: null, large: null };
  /** @type {import("./series.js").PlotData | null} the plot drawn last (its key's labels) */ let drawn = null;

  const pinButton = h("button", { type: "button", id: "frequency-pin", class: "pin-button", "aria-pressed": "false" }, ["Pin"]);
  const chipText = h("span", { id: "frequency-pin-net" });
  const unpinButton = h("button", { type: "button", id: "frequency-unpin", class: "link", title: "Unpin", "aria-label": "Unpin" }, ["×"]);
  const chip = h("span", { class: "pin-chip", id: "frequency-pin-chip", hidden: "" }, ["pinned: ", chipText, " ", unpinButton]);
  const pinTools = h("span", { class: "pin-tools" }, [pinButton, chip]);
  // on the title bar, before Expand: a click there mustn't open or shut the pane
  pinTools.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
  });
  const summary = /** @type {HTMLElement} */ (els.panel.querySelector(":scope > summary"));
  summary.insertBefore(pinTools, summary.querySelector(".large-toggle"));
  pinButton.addEventListener("click", () => (pinned ? unpin() : pin(deps.selectedNet())));
  unpinButton.addEventListener("click", () => unpin());

  const resetButton = h("button", { type: "button", id: "frequency-unzoom", hidden: "", title: "Back to 10 Hz – 30 kHz (or double-click the plot)" }, ["Reset zoom"]);
  els.tools.append(resetButton);
  resetButton.addEventListener("click", () => setZoom(null));

  function showPin() {
    pinButton.setAttribute("aria-pressed", String(Boolean(pinned)));
    pinButton.title = pinned ? `Unpin ${pinned}` : "Pin this curve: it stays on the plot while you select other parts";
    chip.hidden = !pinned;
    chipText.textContent = pinned ?? "";
  }
  showPin();

  /** @param {string} text */
  function note(text) {
    els.note.textContent = text;
    els.note.hidden = !text;
  }

  /**
   * Pin `net` (pinning again moves it). It needs a run with that net's curve.
   * @param {string | null} net
   */
  function pin(net) {
    if (!net) return;
    note("");
    if (net === pinned) return;
    pinned = net;
    showPin();
    deps.rerun();
  }

  /** @param {string} [why] the one-line note that says why the pin went */
  function unpin(why = "") {
    note(why);
    if (!pinned) return;
    pinned = null;
    showPin();
    deps.redraw();
  }

  const zoomKey = () => (deps.expanded() ? "large" : "panel");
  /** This view's zoom, off while Edit curve is on. */
  const zoom = () => (deps.editing() ? null : zooms[zoomKey()]);

  /** @param {[number, number] | null} range */
  function setZoom(range) {
    const text = range && drawn ? zoomText(range, drawn.x, drawn.xText) : "";
    zooms[zoomKey()] = range ? { range, text } : null;
    deps.redraw();
  }

  function showZoom() {
    const z = zoom();
    resetButton.hidden = !z;
    resetButton.textContent = z ? `Reset zoom ${z.text}` : "Reset zoom";
  }

  return {
    pinned: () => pinned,
    pin,
    /** Every line shown again, the pin and the zooms gone: another circuit is open. */
    opened() {
      pinned = null;
      hidden.clear();
      zooms.panel = zooms.large = null;
      note("");
      showPin();
      showZoom();
    },
    /** @param {Record<string, unknown>} nets the view's nets after an edit, undo or redo */
    netsChanged(nets) {
      if (pinGone(pinned, nets)) unpin(`The pinned net ${pinned} is gone from the drawing, so it's unpinned.`);
    },
    /** The roles hidden from the key. */
    hidden: () => /** @type {ReadonlySet<string>} */ (hidden),
    /** The pinned net's line over the plot (none while a sweep is shown: leave it out). @param {import("./series.js").PlotData | null} data @param {any} ac */
    withPinned: (data, ac) => withPinned(data, ac, pinned),
    /**
     * What the Frequency plot takes from the view: the lines hidden, a key clicked, the
     * zoom and a drag or double-click to change it; `fit` is what the level axis fits (the
     * lines shown), `band` the zoom's range for it.
     * @param {import("./series.js").PlotData} data
     */
    plotOpts(data) {
      drawn = data;
      showZoom();
      const z = zoom();
      const editing = deps.editing();
      return {
        hidden: hiddenLabels(data, hidden),
        onToggle: (/** @type {string} */ label, /** @type {boolean} */ shown) => {
          const role = roleOf(drawn, label);
          if (!role) return;
          if (shown) hidden.delete(role);
          else hidden.add(role);
          setTimeout(deps.redraw); // the readings may move to another line; not inside uPlot's own handler
        },
        zoom: z?.range ?? null,
        fit: visibleOnly(data, hidden),
        ...(editing ? {} : {
          onZoom: (/** @type {number} */ a, /** @type {number} */ b) => setZoom(zoomRange(a, b)),
          onUnzoom: () => zoom() && setZoom(null),
        }),
      };
    },
  };
}
