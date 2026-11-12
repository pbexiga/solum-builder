/**
 * The themes View → Theme offers (D-303): their names. Pure:
 * the colours themselves are theme.css's; `theme-start.js` puts the chosen one on the page
 * before it draws, and `theme-sheet.js` is the window.
 */

/** Where the choice is kept (storage.js); theme-start.js reads the same key. */
export const THEME_KEY = "solum.theme";

/**
 * @typedef {{id: "solum" | "dark" | "light", name: string, about: string}} Theme
 * @type {Theme[]}
 */
export const THEMES = [
  { id: "solum", name: "Solum", about: "Solum Builder's own colours: warm dark, brass highlights." },
  { id: "dark", name: "Dark", about: "Neutral greys, a blue highlight." },
  { id: "light", name: "Light", about: "Dark text on white, a blue highlight." },
];

/**
 * The theme a stored value names, the first (the default) for anything else.
 * @param {unknown} stored
 * @returns {Theme}
 */
export function themeFor(stored) {
  return THEMES.find((t) => t.id === stored) ?? THEMES[0];
}
