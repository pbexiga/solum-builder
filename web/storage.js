/**
 * What this browser remembers between visits: JSON in `localStorage`, the one place it is
 * read and written. Storage can be blocked (a private window) or hold something garbled:
 * reading then gives null and writing does nothing, so every caller falls back to its
 * defaults and the choice lasts for the visit.
 */

/** @param {Storage | null} [storage] undefined: the browser's own */
const storeOf = (storage) => (storage === undefined ? globalThis.localStorage : storage);

/**
 * @param {string} key @param {Storage | null} [storage] another store (tests), null for none
 * @returns {any} what was kept under `key`, or null
 */
export function remembered(key, storage) {
  try {
    return JSON.parse(storeOf(storage)?.getItem(key) ?? "null");
  } catch {
    return null;
  }
}

/** @param {string} key @param {unknown} value null forgets it @param {Storage | null} [storage] */
export function remember(key, value, storage) {
  try {
    if (value === null) storeOf(storage)?.removeItem(key);
    else storeOf(storage)?.setItem(key, JSON.stringify(value));
  } catch {
    // storage blocked: it just isn't remembered
  }
}
