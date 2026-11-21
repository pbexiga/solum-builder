/**
 * Drop-down menus (DOM): header menu buttons and menus opened at a point (right-click).
 * Picking an item, a click outside or Escape closes them. Items are rebuilt each time a
 * menu opens, so their labels and disabled states are always current. An item with
 * `items` opens a submenu beside it (on hover or click).
 *
 * @typedef {{label: string, id?: string, hint?: string, checked?: boolean,
 *   disabled?: boolean, run?: () => void, items?: MenuItem[]} | "-"} MenuItem
 */

import { h } from "./panels.js";

/** @type {(() => void) | null} */
let closeOpen = null;

/** Close whichever menu is open. */
export function closeMenus() {
  closeOpen?.();
}

/**
 * Turn `button` into a menu button.
 * @param {HTMLButtonElement} button @param {() => MenuItem[]} items
 */
export function menu(button, items) {
  button.setAttribute("aria-haspopup", "menu");
  button.setAttribute("aria-expanded", "false");
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    const wasOpen = button.getAttribute("aria-expanded") === "true";
    closeMenus();
    if (wasOpen) return;
    const r = button.getBoundingClientRect();
    openMenu(r.left, r.bottom + 4, items(), button);
  });
}

/**
 * Open a menu with its top-left corner at (x, y) in the window, kept on screen.
 * @param {number} x @param {number} y @param {MenuItem[]} items
 * @param {HTMLButtonElement} [button] the header button it belongs to, if any
 */
export function openMenu(x, y, items, button) {
  closeMenus();
  const root = list(items, () => lists);
  /** @type {HTMLElement[]} */
  const lists = [root];
  place(root, x, y);
  button?.setAttribute("aria-expanded", "true");
  const onDoc = (/** @type {Event} */ e) => {
    if (e instanceof KeyboardEvent && e.key !== "Escape") return;
    if (e.type === "pointerdown" && lists.some((l) => l.contains(/** @type {Node} */ (e.target)))) return;
    closeMenus();
  };
  closeOpen = () => {
    for (const l of lists) l.remove();
    button?.setAttribute("aria-expanded", "false");
    document.removeEventListener("pointerdown", onDoc, true);
    document.removeEventListener("keydown", onDoc, true);
    closeOpen = null;
  };
  document.addEventListener("pointerdown", onDoc, true);
  document.addEventListener("keydown", onDoc, true);
}

/**
 * One level of a menu. `open` gives the stack of lists shown (the root first), so a
 * submenu can replace the ones below its parent.
 * @param {MenuItem[]} items @param {() => HTMLElement[]} open
 * @returns {HTMLElement}
 */
function list(items, open) {
  const el = h("div", { class: "menu", role: "menu" });
  for (const item of items) {
    if (item === "-") {
      el.append(h("hr", {}));
      continue;
    }
    const role = item.checked === undefined ? "menuitem" : "menuitemcheckbox";
    const attrs = { type: "button", role };
    const sub = item.items;
    const b = /** @type {HTMLButtonElement} */ (h("button", item.id ? { ...attrs, id: item.id } : attrs, [
      h("span", { class: "menu-label" }, [item.label]),
      h("span", { class: "menu-hint" }, [sub ? "▸" : item.hint ?? ""]),
    ]));
    if (item.checked !== undefined) b.setAttribute("aria-checked", String(item.checked));
    b.disabled = Boolean(item.disabled);
    if (sub) {
      b.setAttribute("aria-haspopup", "menu");
      const show = () => {
        const stack = open();
        const depth = stack.indexOf(el);
        if (stack[depth + 1]?.dataset.parent === b.id && b.id) return;
        for (const l of stack.splice(depth + 1)) l.remove();
        const child = list(sub, open);
        child.dataset.parent = b.id;
        stack.push(child);
        const r = b.getBoundingClientRect();
        place(child, r.right + 2, r.top - 4, r.left);
      };
      b.addEventListener("pointerenter", show);
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        show();
      });
    } else {
      // hovering a plain item closes a sibling's submenu
      b.addEventListener("pointerenter", () => {
        const stack = open();
        for (const l of stack.splice(stack.indexOf(el) + 1)) l.remove();
      });
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        closeMenus();
        item.run?.();
      });
    }
    el.append(b);
  }
  return el;
}

/**
 * Put a menu at (x, y), moved back on screen if it would spill over the right or bottom
 * edge (a submenu flips to the left of its parent, at `flipX`).
 * @param {HTMLElement} el @param {number} x @param {number} y @param {number} [flipX]
 */
function place(el, x, y, flipX) {
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
  document.body.append(el);
  const r = el.getBoundingClientRect();
  if (r.right > window.innerWidth - 4) {
    const left = flipX !== undefined ? flipX - r.width - 2 : window.innerWidth - r.width - 4;
    el.style.left = `${Math.max(4, left)}px`;
  }
  if (r.bottom > window.innerHeight - 4) el.style.top = `${Math.max(4, window.innerHeight - r.height - 4)}px`;
  el.style.maxHeight = `${window.innerHeight - 8}px`;
}
