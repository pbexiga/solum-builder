/**
 * File → Export's logic, no DOM (9d1, D-203): what can be exported, and the Ready to build
 * list. Exports are made on the server from the last save, so the package matches the file.
 */

import { splitDismissed } from "./problems.js";

/**
 * Where the open thing's exports come from: a starter or a saved circuit (`/api/export/{kind}/{id}`),
 * else why there's nothing to export yet.
 * @param {{kind: string, id: string} | null} source the app's `state.source`
 * @returns {{kind: "starter" | "circuit", id: string} | {why: string}}
 */
export function exportTarget(source) {
  if (source?.kind === "starter" || source?.kind === "circuit") return { kind: source.kind, id: source.id };
  if (source?.kind === "block" || source?.id?.startsWith("core:")) return { why: "Blocks aren't exported on their own: place this one in a circuit and export that." };
  return { why: "Save the circuit first: exports are made from the last save, so the package matches the file." };
}

/**
 * The export's base URL. @param {{kind: string, id: string}} target @returns {string}
 */
export const exportUrl = (target) => `api/export/${target.kind}/${encodeURIComponent(target.id)}`;

/**
 * Where the last save's own file and view come from (the editor's open routes).
 * @param {{kind: string, id: string}} target @returns {string}
 */
export const savedUrl = (target) => `api/${target.kind === "starter" ? "starters" : "circuits"}/${encodeURIComponent(target.id)}`;

/**
 * A file name from the circuit's name, as the server writes them (`safe_file_name`: no
 * slashes or other characters a file system refuses).
 * @param {string} name @param {string} tail "schematic.svg" @returns {string}
 */
export const fileName = (name, tail) => `${name.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim() || "circuit"} ${tail}`;

/** @typedef {{severity: "error" | "warning" | "info", text: string, refs: string[]}} ReadyRow */

/**
 * The Ready to build list: unsaved changes first (they aren't in the export), a circuit that
 * doesn't simulate (no bias sheet), then each build check not dismissed, errors first. None
 * of it stops an export.
 * @param {{problems: import("./problems.js").Problem[], simulates: boolean}} check `/check`'s answer
 * @param {{dirty: boolean, dismissed?: import("./problems.js").Dismissal[]}} open
 * @returns {{rows: ReadyRow[], dismissed: number}}
 */
export function readyRows(check, open) {
  /** @type {ReadyRow[]} */ const rows = [];
  if (open.dirty) rows.push({ severity: "warning", text: "There are changes since the last save; the export doesn't have them. Save first to include them.", refs: [] });
  if (!check.simulates) rows.push({ severity: "warning", text: "The saved circuit doesn't simulate, so there's no bias sheet. The Problems panel says why.", refs: [] });
  const { active, dismissed } = splitDismissed(check.problems, open.dismissed);
  const order = ["error", "warning", "info"];
  const sorted = [...active].sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
  rows.push(...sorted.map((p) => ({ severity: p.severity, text: p.message, refs: p.refs })));
  return { rows, dismissed: dismissed.length };
}
