/**
 * The Mac app's side of the page (D-321): its launcher (`solum/desktop/window.py`) puts
 * `window.pywebview.api` on the page and sends the Mac menu bar's items as
 * `solum-desktop` events. In a browser there is neither, and nothing here does anything.
 */

/**
 * @typedef {object} Picked a folder chosen in the macOS picker
 * @property {string} path
 * @property {string | null} problem why it can't be used, in plain English
 * @property {boolean} files_here the folder in use now holds the person's files
 * @property {boolean} files_there the folder chosen holds files already
 */

/**
 * @typedef {object} DesktopApi
 * @property {(kind: "data" | "cache") => Promise<Picked | null>} choose_folder null: cancelled
 * @property {(kind: "data" | "cache", path: string, move: boolean) => Promise<{problem: string | null}>} move_folder
 *   on success the server starts again on the folder and the page reloads
 * @property {(kind: "data" | "cache") => Promise<void>} show_folder in Finder
 * @property {(unsaved: boolean) => Promise<void>} set_unsaved closing the window then asks first
 */

/** The launcher's functions, or null when the page isn't in the Mac app. @returns {DesktopApi | null} */
export function desktopApi() {
  return /** @type {any} */ (globalThis).pywebview?.api ?? null;
}

/**
 * The Mac menu bar's items that open one of the page's dialogs.
 * @param {Record<string, () => void>} open by the item's name ("settings")
 */
export function desktopMenus(open) {
  window.addEventListener("solum-desktop", (e) => open[/** @type {CustomEvent} */ (e).detail]?.());
}

/**
 * Keep the Mac app told whether there is unsaved work, so closing its window or Quit asks
 * first (a browser asks by itself, `beforeunload`; the app's window doesn't). Looked at
 * once a second and sent when it changes: what is unsaved changes in many places.
 * @param {() => boolean} unsaved
 */
export function desktopUnsaved(unsaved) {
  let told = false;
  setInterval(() => {
    const api = desktopApi();
    const now = unsaved();
    if (!api || now === told) return;
    told = now;
    api.set_unsaved(now);
  }, 1000);
}
