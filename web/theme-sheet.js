/**
 * View → Theme… (DOM, D-303): the three themes as cards; a click puts it on at once and
 * this browser keeps it. Canvas plots can't follow CSS, so `onChange` redraws them.
 */

import { sheet } from "./editor/form.js";
import { h } from "./panels.js";
import { remember, remembered } from "./storage.js";
import { THEMES, THEME_KEY, themeFor } from "./theme.js";

/** @returns {import("./theme.js").Theme} the theme this browser chose */
export const currentTheme = () => themeFor(remembered(THEME_KEY));

/** @param {"solum" | "dark" | "light"} id */
function putOn(id) {
  if (id === "solum") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = id;
  remember(THEME_KEY, id === "solum" ? null : id);
}

/** @param {import("./theme.js").Theme} t the theme's own colours, from theme.css */
function preview(t) {
  return h("span", { class: "theme-swatch", "data-theme": t.id, "aria-hidden": "true" }, [
    h("span", { class: "theme-swatch-panel" }), h("span", { class: "theme-swatch-text" }, ["Aa"]), h("span", { class: "theme-swatch-accent" }),
  ]);
}

/** @param {() => void} onChange called after a theme goes on */
export function themeSheet(onChange) {
  const cards = THEMES.map((t) => {
    const card = /** @type {HTMLButtonElement} */ (h("button", { type: "button", class: "theme-option", "data-theme-id": t.id }, [
      preview(t), h("span", { class: "theme-name" }, [t.name]), h("span", { class: "theme-about" }, [t.about]),
    ]));
    card.addEventListener("click", () => {
      putOn(t.id);
      mark();
      onChange();
    });
    return card;
  });
  const mark = () => {
    const on = currentTheme().id;
    for (const c of cards) c.setAttribute("aria-pressed", String(c.dataset.themeId === on));
  };
  mark();
  sheet({ title: "Theme", id: "theme", body: [
    h("p", {}, ["How Solum Builder looks in this browser. Exports and printed schematics keep their own paper colours."]),
    h("div", { class: "theme-options" }, cards),
  ] });
}
