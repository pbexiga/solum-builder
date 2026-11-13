/**
 * The themes Settings offers (D-303, D-310): their names. Pure:
 * the colours themselves are theme.css's; the server puts the chosen one on the page
 * it sends (D-311), and `theme-chooser.js` is the cards.
 */

/** Where the choice is kept (storage.js: with the server's preferences); theme-start.js reads the same key. */
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
