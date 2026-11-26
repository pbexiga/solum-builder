/**
 * Side panes that hide (D-408): each view (the Schematic and the Board) has a left side
 * (the palette; the tray) and a right column (the result panes; the board's panes), and
 * either can be hidden to give the canvas the width, the drawing kept where it is on
 * screen. A thin bar at each end of the window, beyond its column, is always there: a click
 * hides the column or shows it; while it's hidden, resting on the bar slides the column out
 * over the drawing until the pointer leaves, and a click then pins it. Sides slide in and
 * out. Remembered per view and per side (`solum.sides`, kept by the
 * server with the pane order, D-311). `[` and `]` toggle the left and the right side.
 *
 * The state is plain data (`readSides`, `withSide`), tested on its own; `sidePanes` puts
 * it on the page, given the columns and what keeps the drawing still by the app root.
 */

import { h, onBackInColumn, stackLargeViews } from "./panels.js";
import { remember, remembered } from "./storage.js";

/**
 * @typedef {"schematic" | "board"} View
 * @typedef {"left" | "right"} Side
 * @typedef {Record<View, Record<Side, boolean>>} Sides each side true when it's hidden
 */

export const SIDES_KEY = "solum.sides";
/** @type {View[]} */
export const VIEWS = ["schematic", "board"];
/** @type {Side[]} */
export const SIDES = ["left", "right"];

/** What each side is called on its edge tab. @type {Record<View, Record<Side, string>>} */
const NAMES = { schematic: { left: "the parts", right: "the results" }, board: { left: "the tray", right: "the board's panes" } };
const KEYS = { left: "[", right: "]" };

/**
 * The hidden sides as kept, anything missing or garbled read as shown.
 * @param {unknown} saved @returns {Sides}
 */
export function readSides(saved) {
  const from = /** @type {any} */ (saved && typeof saved === "object" ? saved : {});
  return /** @type {Sides} */ (Object.fromEntries(VIEWS.map((v) => [v, Object.fromEntries(SIDES.map((s) => [s, from[v]?.[s] === true]))])));
}

/**
 * The sides with one hidden (true) or shown (false); undefined turns it over.
 * @param {Sides} sides @param {View} view @param {Side} side @param {boolean} [hidden]
 * @returns {Sides}
 */
export function withSide(sides, view, side, hidden) {
  return { ...sides, [view]: { ...sides[view], [side]: hidden ?? !sides[view][side] } };
}

/**
 * What a side's button says it does, with its key: Show on the edge tab, Hide on the
 * button at the column's top, Pin there while the side peeks out. While a full layout is
 * reviewed, the board's right column holds the review (D-406).
 * @param {"Show" | "Hide" | "Pin"} action @param {View} view @param {Side} side @param {boolean} reviewing
 */
export function sideTitle(action, view, side, reviewing) {
  const what = view === "board" && side === "right" && reviewing ? "the review" : NAMES[view][side];
  return `${action} ${what} (${KEYS[side]})`;
}

/** How long a side takes to slide in or out (app.css's `.side-pane` transition), ms. */
const SLIDE_MS = 180;
/** How long the pointer rests on a hidden side's bar before the side peeks out, ms. */
const PEEK_DWELL_MS = 150;
/** How long after the pointer leaves a peeking side it slides back, ms. */
const PEEK_LEAVE_MS = 300;

/**
 * The side panes on the page.
 * @param {HTMLElement} workspace the row the columns and the canvas sit in: the bars go at
 *   its two ends, on the columns' outer edges
 * @param {{
 *   columns: Record<View, Record<Side, HTMLElement>>,
 *   view: () => View,
 *   keepPlace: (change: () => void) => void,
 *   changed?: () => void,
 * }} opts `keepPlace`: runs the change with the view shown's drawing kept still;
 *   `changed`: told after a side is hidden or shown (the menus' ticks)
 */
export function sidePanes(workspace, opts) {
  let sides = readSides(remembered(SIDES_KEY));
  let reviewing = false;
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  /** A side sliding out before it's hidden: finished early if anything else happens. */
  let sliding = /** @type {null | {timer: number, finish: () => void}} */ (null);
  /** The side peeking out over the canvas, if any. */
  let peeking = /** @type {null | Side} */ (null);
  let peekTimer = 0;

  /**
   * Each side's bar, always there at the window's edge beyond its column: a click hides
   * the column or shows it (pins it while it peeks); resting on it while hidden peeks it.
   * @type {Record<Side, HTMLButtonElement>}
   */
  const bars = /** @type {any} */ ({});
  for (const side of SIDES) {
    const bar = /** @type {HTMLButtonElement} */ (h("button", { type: "button", class: `side-bar ${side}`, "data-side": side }));
    bar.addEventListener("click", () => set(side, !sides[opts.view()][side]));
    bar.addEventListener("pointerenter", (e) => {
      clearTimeout(peekTimer);
      if (e.buttons || !sides[opts.view()][side]) return; // a drag reaching it, or a side shown: no peek
      peekTimer = window.setTimeout(() => peek(side), PEEK_DWELL_MS);
    });
    bar.addEventListener("pointerleave", () => {
      clearTimeout(peekTimer);
      if (peeking === side) peekTimer = window.setTimeout(unpeek, PEEK_LEAVE_MS);
    });
    bars[side] = bar;
  }
  workspace.prepend(bars.left);
  workspace.append(bars.right);

  for (const v of VIEWS) {
    for (const s of SIDES) {
      const col = opts.columns[v][s];
      col.classList.add("side-pane", `side-${s}`);
      col.addEventListener("pointerenter", () => { if (peeking && col === column(peeking)) clearTimeout(peekTimer); });
      col.addEventListener("pointerleave", () => {
        if (!peeking || col !== column(peeking)) return;
        clearTimeout(peekTimer);
        peekTimer = window.setTimeout(unpeek, PEEK_LEAVE_MS);
      });
    }
  }

  /** @param {Side} side the view shown's column on that side */
  const column = (side) => opts.columns[opts.view()][side];

  function apply() {
    for (const v of VIEWS) {
      for (const s of SIDES) {
        const col = opts.columns[v][s];
        col.classList.toggle("side-hidden", sides[v][s]);
        if (!sides[v][s] || v !== opts.view()) col.classList.remove("side-peek");
      }
    }
    if (peeking && !column(peeking).classList.contains("side-peek")) peeking = null;
    showBars();
  }

  /** The bars: the chevron pointing the way a click moves the column; what it does, in its tooltip. */
  function showBars() {
    const view = opts.view();
    for (const s of SIDES) {
      const hidden = sides[view][s];
      bars[s].textContent = (s === "left") === hidden ? "›" : "‹";
      bars[s].setAttribute("aria-expanded", String(!hidden));
      bars[s].title = sideTitle(!hidden ? "Hide" : peeking === s ? "Pin" : "Show", view, s, reviewing);
      bars[s].setAttribute("aria-label", bars[s].title);
    }
  }

  /** A hidden side slides out over the canvas, the drawing untouched. @param {Side} side */
  function peek(side) {
    finishSlide(); // a side still sliding out lands first
    if (!sides[opts.view()][side]) return;
    if (peeking && peeking !== side) unpeek();
    peeking = side;
    column(side).classList.remove("side-leaving");
    column(side).classList.add("side-peek");
    showBars();
  }

  function unpeek() {
    clearTimeout(peekTimer);
    if (peeking) {
      // kept above the canvas while it slides back: the left column comes before the
      // canvas in the page, so without it the canvas covers it at once (D-408)
      const col = column(peeking);
      col.classList.add("side-leaving");
      col.classList.remove("side-peek");
      window.setTimeout(() => col.classList.remove("side-leaving"), motion.matches ? 0 : SLIDE_MS);
    }
    peeking = null;
    showBars();
  }

  /** Run the change with the column's slide turned off, so it lands where it is. @param {HTMLElement} col @param {() => void} change */
  function still(col, change) {
    col.classList.add("no-slide");
    change();
    void col.offsetWidth; // laid out where it is before the slide is turned back on
    col.classList.remove("no-slide");
  }

  function finishSlide() {
    if (!sliding) return;
    clearTimeout(sliding.timer);
    const { finish } = sliding;
    sliding = null;
    finish();
  }

  /** @param {Side} side @param {boolean} [hidden] undefined: turned over */
  function set(side, hidden) {
    finishSlide();
    const view = opts.view();
    const next = withSide(sides, view, side, hidden);
    if (next[view][side] === sides[view][side]) return;
    const col = column(side);
    const commit = () => {
      opts.keepPlace(() => {
        sides = next;
        apply();
      });
      remember(SIDES_KEY, sides);
      stackLargeViews(); // the bars span the canvas, wider or narrower now
      opts.changed?.();
    };
    if (next[view][side]) {
      // hiding: it slides out over its own place first, then the canvas takes the width
      unpeek();
      col.classList.add("side-out");
      sliding = { timer: window.setTimeout(finishSlide, motion.matches ? 0 : SLIDE_MS), finish: () => still(col, () => { commit(); col.classList.remove("side-out"); }) };
    } else if (col.classList.contains("side-peek")) {
      peeking = null;
      still(col, commit); // pinned where it peeks: nothing moves
    } else {
      // showing: the canvas gives the width back, then it slides in from the edge
      still(col, () => { col.classList.add("side-out"); commit(); });
      col.classList.remove("side-out");
    }
  }

  // a large view's Collapse puts it back in its column: shown first, so it lands in sight
  onBackInColumn((el) => {
    for (const v of VIEWS) {
      for (const s of SIDES) {
        if (!sides[v][s] || !opts.columns[v][s].contains(el)) continue;
        if (v === opts.view()) set(s, false);
        else {
          sides = withSide(sides, v, s, false);
          apply();
          remember(SIDES_KEY, sides);
        }
      }
    }
  });
  apply();

  return {
    /** Hide or show a side of the view shown. @param {Side} side */
    toggle: (side) => set(side, undefined),
    /** Whether a side of the view shown is hidden. @param {Side} side */
    hidden: (side) => sides[opts.view()][side],
    /** The view changed: its sides and bars. */
    refresh() {
      finishSlide();
      unpeek();
      apply();
    },
    /**
     * A full layout's review opened (true) or closed (false): opening shows the board's
     * hidden right column once, so its result is seen; it can be hidden again.
     * @param {boolean} open
     */
    reviewing(open) {
      reviewing = open;
      if (open && opts.view() === "board" && sides.board.right) set("right", false);
      else apply();
    },
  };
}
