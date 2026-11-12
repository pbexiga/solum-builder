/**
 * A custom switch's contacts as the editor builds them (v22, 9c): start from a type, then
 * resize it (poles, throws, positions) keeping what was set. Pure: no DOM. The server
 * checks the result (schema.py `CustomSwitch`); the limits here only bound the pickers.
 */

import { throwLugs } from "../schematic/symbols.js";

/** The pickers' bounds (= switches.py MAX_POLES, MAX_THROWS, MAX_POSITIONS). */
export const LIMITS = { poles: 4, throws: 12, positions: 12 };

/**
 * A custom switch to start from: the type `kind` as one (its name, throws, look, and each
 * position's joins as throw numbers), so a built-in can be the starting point.
 * @param {import("../schematic/symbols.js").SwitchKind} kind
 * @returns {import("../schematic/symbols.js").CustomSwitch}
 */
export function customFrom(kind) {
  const throws = kind.lugs.slice(1);
  const look = kind.look === "rotary" && throws.length >= 3 ? "rotary" : "toggle";
  // a toggle's lugs read 1, 3 for throws 1, 2: number them in drawing order
  return {
    name: kind.id === "custom" ? kind.name : `My ${kind.short}`.slice(0, 24),
    throws: throws.length,
    look,
    positions: kind.positions.map((name, i) => ({
      name,
      joins: kind.closed[i].map((lug) => (lug == null ? null : throws.indexOf(lug) + 1)),
    })),
  };
}

/**
 * `custom` with this many poles, throws and positions: what was set stays; a new pole
 * copies pole A's joins, a new position joins the next throw, a join past the last throw
 * opens. A rotary of fewer than 3 throws becomes a toggle.
 * @param {import("../schematic/symbols.js").CustomSwitch} custom
 * @param {{poles: number, throws: number, positions: number}} size
 * @returns {import("../schematic/symbols.js").CustomSwitch}
 */
export function resize(custom, size) {
  const fit = (/** @type {number | null} */ j) => (j !== null && j <= size.throws ? j : null);
  const positions = Array.from({ length: size.positions }, (_, i) => {
    const old = custom.positions[i];
    const first = old?.joins[0] ?? Math.min(i + 1, size.throws);
    return {
      name: old?.name ?? `Position ${i + 1}`,
      joins: Array.from({ length: size.poles }, (_, k) => fit(old ? (k < old.joins.length ? old.joins[k] : old.joins[0]) : first)),
    };
  });
  return { ...custom, throws: size.throws, look: size.throws >= 3 ? custom.look ?? "toggle" : "toggle", positions };
}

/**
 * A join's choices for one pole: open, then each throw by the lug name the schematic shows
 * (A1, A3 on a toggle's pole A; C1… on a rotary's), so the grid reads like the drawing.
 * @param {import("../schematic/symbols.js").CustomSwitch} custom @param {number} pole 0 for A
 * @returns {Array<[string, string]>} value (throw number, "" open) and label
 */
export function joinChoices(custom, pole) {
  const letter = custom.positions[0].joins.length > 1 ? "ABCD"[pole] : "";
  const [common, ...throws] = throwLugs(custom.throws, custom.look ?? "toggle");
  return [["", "open"], ...throws.map((lug, i) => /** @type {[string, string]} */ ([String(i + 1), `${letter}${common}–${letter}${lug}`]))];
}

/**
 * What to fix before Apply, in plain English, or null: a name for the switch and each
 * position (the pickers keep the rest within the limits; the server checks it all).
 * @param {import("../schematic/symbols.js").CustomSwitch} custom @returns {string | null}
 */
export function customProblem(custom) {
  if (!custom.name.trim()) return "Give the switch a name, like Clip or Voice.";
  const unnamed = custom.positions.findIndex((p) => !p.name.trim());
  return unnamed < 0 ? null : `Give position ${unnamed + 1} a name, like On or Vintage.`;
}
