/**
 * File → Settings… (DOM, D-310): one dialog for every version (Docker, from source, the
 * Mac app). Folders: where the circuits and the cache are (the server's, shown; changed
 * outside the app unless the server says they can move; in a container, with the host's
 * name for each beside it, D-313). Cache: its largest size, which
 * holds at once, and how much is used. Appearance: the theme chooser.
 * In the Mac app the folders have Change… (the macOS picker; the launcher moves the files
 * and starts the server again, D-323) and Show in Finder.
 * `sizeText` and `cacheSizeProblem` are DOM-free (tested).
 */

import { getJson, putJson } from "./api.js";
import { desktopApi } from "./desktop.js";
import { ask, sheet } from "./editor/form.js";
import { h } from "./panels.js";
import { themeChooser } from "./theme-chooser.js";

/**
 * A size on disk as people say it: "0 MB", "340 MB", "1.2 GB" (decimal, as `CACHE_MAX_GB`).
 * @param {number} bytes @returns {string}
 */
export function sizeText(bytes) {
  if (bytes < 999.5e6) return `${Math.round(bytes / 1e6)} MB`;
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

/**
 * What is wrong with a largest cache size as typed, or null.
 * @param {string} text @returns {string | null}
 */
export function cacheSizeProblem(text) {
  const size = Number(text.trim().replace(",", "."));
  if (!text.trim() || !Number.isFinite(size)) return "Type the largest cache size as a number of gigabytes, such as 2 or 0.5.";
  if (size <= 0) return "The largest cache size must be more than 0.";
  return null;
}

/**
 * @param {string} id @param {string} label @param {string} path
 * @param {string | null} host in a container: the folder as the host names it (D-313)
 * @param {string | null} how the variable that changes it, when the app can't
 * @param {Node[]} [tools] the Mac app's buttons for it
 */
function folderRow(id, label, path, host, how, tools = []) {
  return h("div", { class: "settings-folder", id }, [
    h("span", { class: "settings-label" }, [label]),
    h("code", { class: "settings-path" }, [path]),
    ...(host ? [h("span", { class: "settings-host" }, ["(host path: ", h("code", {}, [host]), ")"])] : []),
    ...(how ? [h("span", { class: "settings-how" }, ["To change it, set ", h("code", {}, [how]), " (in ", h("code", {}, [".env"]), " or the environment), then restart."])] : []),
    ...(tools.length ? [h("span", { class: "settings-tools" }, tools)] : []),
  ]);
}

/**
 * What to ask before the data folder changes while the one in use holds files, or null
 * when there is nothing to ask (DOM-free, tested).
 * @param {import("./desktop.js").Picked} picked
 * @returns {{text: string, stay: string} | null} `stay`: the label for not moving them
 */
export function moveQuestion(picked) {
  if (!picked.files_here) return null;
  return picked.files_there
    ? { text: `Your circuits, blocks, models and audio are in the folder in use now, and ${picked.path} has files already. Move yours in beside them, or leave yours where they are and use what is there?`, stay: "Use what is there" }
    : { text: `Your circuits, blocks, models and audio are in the folder in use now. Move them to ${picked.path}, or leave them where they are and start empty?`, stay: "Start empty" };
}

/**
 * The Mac app's Change… and Show in Finder for one folder (D-323).
 * @param {"data" | "cache"} kind @param {import("./desktop.js").DesktopApi} api
 * @param {() => Promise<boolean>} leave see `settingsSheet`
 * @param {(message: string | null) => void} showError
 * @returns {Node[]}
 */
function folderTools(kind, api, leave, showError) {
  const change = h("button", { type: "button", id: `settings-${kind}-change` }, ["Change…"]);
  const show = h("button", { type: "button", id: `settings-${kind}-show` }, ["Show in Finder"]);
  show.addEventListener("click", () => api.show_folder(kind));
  change.addEventListener("click", async () => {
    showError(null);
    const picked = await api.choose_folder(kind);
    if (!picked) return;
    if (picked.problem) return showError(picked.problem);
    let move = false;
    const question = kind === "data" ? moveQuestion(picked) : null;
    if (question) {
      const answer = await ask({ title: "Move your files?", text: question.text, cancel: "cancel",
        buttons: [{ label: "Cancel", value: "cancel" }, { label: question.stay, value: "stay" }, { label: "Move them", value: "move", kind: "primary" }] });
      if (answer === "cancel") return;
      move = answer === "move";
    }
    if (!(await leave())) return;
    const done = await api.move_folder(kind, picked.path, move); // the page reloads unless it failed
    if (done?.problem) showError(done.problem);
  });
  return [change, show];
}

/**
 * @param {() => void} onTheme called after a theme goes on (the plots redraw)
 * @param {() => Promise<boolean>} leave asks about unsaved work before the page reloads on
 *   a moved folder; false: stay
 */
export async function settingsSheet(onTheme, leave) {
  const now = await getJson("api/settings");
  const api = now.can_move_folders ? desktopApi() : null;
  const size = /** @type {HTMLInputElement} */ (h("input", { id: "settings-cache-size", type: "text", inputmode: "decimal", autocomplete: "off", value: String(now.cache_max_gb) }));
  const used = h("p", { id: "settings-cache-used" });
  const error = h("p", { class: "error", role: "alert", hidden: "" });
  const showUsed = (/** @type {any} */ s) => {
    used.textContent = `Using ${sizeText(s.cache_used_bytes)} of ${sizeText(s.cache_max_gb * 1e9)} now.`;
  };
  /** @param {string | null} message */
  const showError = (message) => {
    error.textContent = message ?? "";
    error.hidden = !message;
  };
  size.addEventListener("change", async () => {
    const problem = cacheSizeProblem(size.value);
    if (problem) return showError(problem);
    try {
      const kept = await putJson("api/settings", { cache_max_gb: Number(size.value.trim().replace(",", ".")) });
      size.value = String(kept.cache_max_gb);
      showUsed(kept);
      showError(null);
    } catch (err) {
      showError(/** @type {Error} */ (err).message);
    }
  });
  showUsed(now);
  const folderError = h("p", { class: "error", id: "settings-folder-error", role: "alert", hidden: "" });
  /** @param {string | null} message */
  const showFolderError = (message) => {
    folderError.textContent = message ?? "";
    folderError.hidden = !message;
  };
  sheet({
    title: "Settings",
    id: "settings",
    body: [
      h("h3", {}, ["Folders"]),
      folderRow("settings-data-dir", "Circuits, blocks, models and audio", now.data_dir, now.host_data_dir, now.can_move_folders ? null : "DATA_DIR", api ? folderTools("data", api, leave, showFolderError) : []),
      folderRow("settings-cache-dir", "Cache", now.cache_dir, now.host_cache_dir, now.can_move_folders ? null : "CACHE_DIR", api ? folderTools("cache", api, leave, showFolderError) : []),
      ...(api ? [folderError] : []),
      h("h3", {}, ["Cache"]),
      h("p", {}, ["Results are kept so the same run is instant the next time. When the cache is full the oldest go first; it is always safe to delete."]),
      h("div", { class: "form-row" }, [h("label", { for: "settings-cache-size" }, ["Largest size"]), size, h("span", { class: "unit" }, ["GB"])]),
      used,
      error,
      h("h3", {}, ["Appearance"]),
      themeChooser(onTheme),
    ],
  });
}
