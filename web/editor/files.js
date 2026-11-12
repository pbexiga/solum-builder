// Lists of saved files (circuits and blocks), pure: no DOM (D-076).

/**
 * Saved files as the Open and Blocks dialogs list them: by name (A–Z or Z–A, ignoring
 * case, numbers in order), each name's versions newest major first. With `currentOnly`,
 * only each one's current version (its newest major).
 * @template {{name: string, version?: string, current?: boolean}} E
 * @param {E[]} entries @param {"az" | "za"} order @param {boolean} currentOnly
 * @returns {E[]}
 */
export function listFiles(entries, order, currentOnly) {
  const sign = order === "za" ? -1 : 1;
  const major = (/** @type {E} */ e) => Number(/^v(\d+)/.exec(e.version ?? "")?.[1] ?? 0);
  return entries
    .filter((e) => !currentOnly || e.current !== false)
    .sort((a, b) => sign * a.name.localeCompare(b.name, undefined, { sensitivity: "base", numeric: true }) || major(b) - major(a));
}

/** How many circuits the Open dialog's Recent section lists. */
export const RECENT_MAX = 3;

/**
 * The Open dialog's list in sections, as the Blocks dialog has them: Recent (the
 * `RECENT_MAX` last saved, newest first; `saved` is the file's time as ISO 8601) and
 * All circuits (`listFiles`). While `searching`, one section with no title: only the
 * matches. Files that can't be opened are never Recent.
 * @template {{name: string, version?: string, current?: boolean, saved?: string, problem?: string | null}} E
 * @param {E[]} entries @param {"az" | "za"} order @param {boolean} currentOnly @param {boolean} searching
 * @returns {Array<{key: "recent" | "all", title: string, rows: E[]}>}
 */
export function openSections(entries, order, currentOnly, searching) {
  const all = listFiles([...entries], order, currentOnly);
  if (searching) return [{ key: "all", title: "", rows: all }];
  const recent = listFiles([...entries], "az", currentOnly)
    .filter((e) => !e.problem && e.saved)
    .sort((a, b) => (a.saved === b.saved ? 0 : /** @type {string} */ (a.saved) < /** @type {string} */ (b.saved) ? 1 : -1))
    .slice(0, RECENT_MAX);
  return [...(recent.length ? [{ key: /** @type {const} */ ("recent"), title: "Recent", rows: recent }] : []), { key: "all", title: "All circuits", rows: all }];
}

/** `v1.12` from a circuit's version (v1.0 when the file has none yet). @param {any} c */
export const versionTag = (c) => `v${c.version?.major ?? 1}.${c.version?.minor ?? 0}`;

/** `{major, minor}` from a tag like `v1.12`. @param {string} tag */
export const parseTag = (tag) => {
  const m = /^v(\d+)\.(\d+)$/.exec(tag);
  return m ? { major: Number(m[1]), minor: Number(m[2]) } : undefined;
};
