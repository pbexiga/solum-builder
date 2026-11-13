/**
 * Result panes the user can reorder (drag a pane's grip, or focus the grip and press
 * the up and down arrow keys). The order, which panes are open or shut, and how far the
 * pane list is scrolled are remembered (D-121: the order and open or shut with the
 * preferences, the scroll in this browser, D-311); View → Reset pane order
 * puts the default order back and each pane open or shut as the page starts (DC shut,
 * the rest open).
 * `paneOrder`, `movePane` and `openStates` are DOM-free (tested); `reorderable` wires up
 * the panes.
 */

import { remember, remembered } from "./storage.js";
import { h } from "./panels.js";

const KEY = "solum.panes";
const OPEN_KEY = "solum.panes.open";
const SCROLL_KEY = "solum.panes.scroll";
const SCROLL_SETTLE_MS = 10000; // how long a reload keeps putting the saved scroll back as panes fill

/**
 * The order to show: the saved one, minus panes that no longer exist, with any pane it
 * doesn't know put back after the pane that comes before it by default.
 * @param {unknown} saved @param {string[]} defaults @returns {string[]}
 */
export function paneOrder(saved, defaults) {
  const known = Array.isArray(saved) ? saved.filter((id, i) => defaults.includes(id) && saved.indexOf(id) === i) : [];
  const out = [...known];
  defaults.forEach((id, i) => {
    if (out.includes(id)) return;
    const before = defaults.slice(0, i).reverse().find((d) => out.includes(d));
    out.splice(before === undefined ? 0 : out.indexOf(before) + 1, 0, id);
  });
  return out;
}

/**
 * `order` with `id` moved to index `to` (counted in the new order, clamped to the ends).
 * @param {string[]} order @param {string} id @param {number} to @returns {string[]}
 */
export function movePane(order, id, to) {
  const rest = order.filter((o) => o !== id);
  if (rest.length === order.length) return order;
  rest.splice(Math.max(0, Math.min(to, rest.length)), 0, id);
  return rest;
}

/**
 * Each pane's open (true) or shut (false) state: the saved one where it is a yes or no,
 * else how the page starts it.
 * @param {unknown} saved @param {Map<string, boolean>} defaults @returns {Map<string, boolean>}
 */
export function openStates(saved, defaults) {
  const s = saved && typeof saved === "object" ? /** @type {Record<string, unknown>} */ (saved) : {};
  return new Map([...defaults].map(([id, on]) => [id, typeof s[id] === "boolean" ? /** @type {boolean} */ (s[id]) : on]));
}

/**
 * Make the `details` panes in `container` reorderable. Returns `reset`, which puts the
 * default order back and each pane open or shut as it started.
 * @param {HTMLElement} container @returns {{reset: () => void}}
 */
export function reorderable(container) {
  const panes = () => /** @type {HTMLDetailsElement[]} */ ([...container.querySelectorAll(":scope > details")]);
  const defaults = panes().map((p) => p.id);
  const startsOpen = new Map(panes().map((p) => [p.id, p.open]));
  const ids = () => panes().map((p) => p.id);
  const apply = (/** @type {string[]} */ order) => {
    const byId = new Map(panes().map((p) => [p.id, p]));
    for (const id of order) container.append(/** @type {HTMLElement} */ (byId.get(id)));
  };
  const moveTo = (/** @type {string} */ id, /** @type {number} */ to) => {
    const order = movePane(ids(), id, to);
    apply(order);
    remember(KEY, order);
  };
  /** @type {Map<string, boolean>} */
  let opens = openStates(remembered(OPEN_KEY), startsOpen);
  const saveOpen = (/** @type {HTMLDetailsElement} */ p) => {
    opens.set(p.id, p.open);
    remember(OPEN_KEY, Object.fromEntries(opens));
  };
  for (const pane of panes()) {
    const summary = /** @type {HTMLElement} */ (pane.querySelector(":scope > summary"));
    const name = summary.firstChild?.textContent?.trim() ?? pane.id;
    const grip = h("span", {
      class: "grip", role: "button", tabindex: "0", "data-grip": pane.id,
      title: "Drag to move this pane (or use the arrow keys)", "aria-label": `Move the ${name} pane`,
    }, ["⋮⋮"]);
    // the grip moves the pane; it never opens or closes it
    grip.addEventListener("click", (e) => e.preventDefault());
    grip.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      e.preventDefault();
      e.stopPropagation();
      moveTo(pane.id, ids().indexOf(pane.id) + (e.key === "ArrowUp" ? -1 : 1));
      grip.focus();
    });
    grip.addEventListener("pointerdown", (e) => drag(e, pane));
    summary.append(grip);
    // a pane out as a large view opens and shrinks to its bar: that isn't its panel state
    pane.addEventListener("toggle", () => {
      if (!pane.classList.contains("large-view")) saveOpen(pane);
    });
  }

  /** @param {PointerEvent} e @param {HTMLDetailsElement} pane */
  function drag(e, pane) {
    if (e.button !== 0) return;
    e.preventDefault();
    const marker = h("div", { class: "pane-drop" });
    pane.classList.add("moving");
    let to = ids().indexOf(pane.id);
    const onMove = (/** @type {PointerEvent} */ ev) => {
      // where the pane would go: before the first other pane whose middle is below the pointer
      const others = panes().filter((p) => p !== pane);
      const below = others.findIndex((p) => {
        const r = p.getBoundingClientRect();
        return ev.clientY < r.top + Math.min(r.height, 80) / 2;
      });
      to = below < 0 ? others.length : below;
      if (below < 0) container.append(marker);
      else container.insertBefore(marker, others[below]);
      // scroll the pane list when dragging near its top or bottom edge
      const box = container.getBoundingClientRect();
      if (ev.clientY < box.top + 30) container.scrollTop -= 12;
      else if (ev.clientY > box.bottom - 30) container.scrollTop += 12;
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      marker.remove();
      pane.classList.remove("moving");
      if (to !== ids().indexOf(pane.id)) moveTo(pane.id, to);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  }

  apply(paneOrder(remembered(KEY), defaults));
  for (const p of panes()) p.open = opens.get(p.id) ?? true;
  keepScroll(container, panes());
  return {
    reset() {
      remember(KEY, null);
      apply(defaults);
      opens = new Map(startsOpen);
      for (const p of panes()) p.open = startsOpen.get(p.id) ?? true;
      remember(OPEN_KEY, null);
    },
  };
}

/**
 * Remember how far `container` is scrolled, and each pane's height, and put both back on
 * load (D-121). The panes are near empty until the first run fills them, so each one holds
 * its saved height (`--reserve`) until its own content is that tall, and the list keeps the
 * saved place meanwhile; the first frame already shows it there. The holding ends early
 * when the user scrolls, clicks or types in the list, and after `SCROLL_SETTLE_MS` at most.
 * @param {HTMLElement} container @param {HTMLDetailsElement[]} panes
 */
function keepScroll(container, panes) {
  const saved = /** @type {{top?: unknown, heights?: Record<string, unknown>} | null} */ (remembered(SCROLL_KEY));
  const target = Number(saved?.top) || 0;
  /** @type {Map<HTMLDetailsElement, number>} */
  const reserved = new Map();
  for (const p of panes) {
    const height = Number(saved?.heights?.[p.id]);
    if (target > 0 && height > 0 && p.open) reserved.set(p, height); // a shut pane is its title
  }
  let restoring = target > 0;
  const release = (/** @type {HTMLDetailsElement} */ p) => {
    reserved.delete(p);
    p.style.removeProperty("--reserve");
  };
  const stop = () => {
    restoring = false;
    observer.disconnect();
    container.style.overflowAnchor = "";
    for (const p of [...reserved.keys()]) release(p);
  };
  const observer = new ResizeObserver(() => {
    if (!restoring) return;
    for (const [p, height] of reserved) if (contentHeight(p) >= height - 4) release(p);
    container.scrollTop = target;
    if (!reserved.size) stop(); // every pane is as tall as it was: the list is where it was
  });
  if (restoring) {
    for (const [p, height] of reserved) p.style.setProperty("--reserve", `${height}px`);
    for (const p of panes) for (const el of [p, ...p.children]) observer.observe(el);
    container.scrollTop = target;
    for (const ev of ["wheel", "pointerdown", "keydown", "touchstart"]) container.addEventListener(ev, stop, { once: true, passive: true });
    // shut, a pane is its title (opening one fires this too, putting back its saved state)
    for (const p of panes) p.addEventListener("toggle", () => p.open || release(p));
    // the browser would keep the view on what's showing as panes above it settle: hold the place itself
    container.style.overflowAnchor = "none";
    setTimeout(stop, SCROLL_SETTLE_MS);
  }
  container.dataset.ready = "true"; // shown from here (hidden in the CSS until now)
  let timer = 0;
  const save = () => remember(SCROLL_KEY, {
    top: Math.round(container.scrollTop),
    // a pane out as a large view isn't in the list
    heights: Object.fromEntries(panes.filter((p) => !p.classList.contains("large-view")).map((p) => [p.id, p.offsetHeight])),
  });
  container.addEventListener("scroll", () => {
    if (restoring) return; // our own putting back, or the page settling: not a new place
    clearTimeout(timer);
    timer = window.setTimeout(save, 200);
  }, { passive: true });
  window.addEventListener("pagehide", () => {
    if (!restoring) save();
  });
}

/** How tall a pane's own content is, whatever height it's held at. @param {HTMLElement} p */
function contentHeight(p) {
  const top = p.getBoundingClientRect().top;
  return Math.max(0, ...[...p.children].map((c) => c.getBoundingClientRect()).filter((r) => r.height).map((r) => r.bottom - top));
}
