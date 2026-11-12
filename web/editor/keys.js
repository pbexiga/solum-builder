/**
 * Editor hotkeys: a key press → an action name. Pure (no DOM) so it can be tested.
 * Part hotkeys come from the palette (R resistor, C capacitor…). Space rotates (R is the
 * resistor, D-053); L a net label, X a text block (D-091); B inserts a block, Ctrl+C/V copy and paste the selection, Ctrl+A
 * selects everything (D-072), Ctrl+F finds a part by ref. They're shortcuts: drag-and-drop is the main way in, and the keys show
 * only in tooltips (D-057). Keys typed into a form field never reach here.
 *
 * @typedef {{key: string, ctrl?: boolean, meta?: boolean, shift?: boolean, alt?: boolean}} Press
 * @typedef {{action: string, type?: string}} Action
 */

import { PALETTE } from "./edit.js";

/**
 * @param {Press} press
 * @returns {Action | null}
 */
export function actionFor(press) {
  const key = press.key.length === 1 ? press.key.toLowerCase() : press.key;
  const mod = press.ctrl || press.meta;
  if (mod && !press.alt) {
    if (key === "z") return { action: press.shift ? "redo" : "undo" };
    if (key === "y") return { action: "redo" };
    if (key === "s") return { action: "save" };
    if (key === "Enter") return { action: "run" };
    if (key === "c") return { action: "copy" };
    if (key === "v") return { action: "paste" };
    if (key === "a") return { action: "selectAll" };
    if (key === "f") return { action: "find" };
    return null;
  }
  if (press.alt) return null;
  switch (key) {
    case "Escape": return { action: "cancel" };
    case "Delete":
    case "Backspace": return { action: "delete" };
    case " ": return { action: "rotate" };
    case "l": return { action: "label" };
    case "x": return { action: "text" };
    case "g": return { action: "ground" };
    case "w": return { action: "wire" };
    case "b": return { action: "insertBlock" };
    case "Enter": return { action: "inspect" };
  }
  const entry = PALETTE.find((e) => e.key === key);
  return entry ? { action: "place", type: entry.tool ?? entry.type } : null;
}

/**
 * @typedef {{keys: string, does: string, press?: Press, action?: string}} Hotkey
 *   `press` and `action` tie a row to actionFor (a test checks they agree); rows without
 *   them are the mouse, or keys handled where they apply (a form, a plot, a pane).
 * @typedef {{title: string, rows: Hotkey[]}} HotkeyGroup
 */

/**
 * Every shortcut, grouped for Help → Hot keys. The part keys come from the palette.
 * @returns {HotkeyGroup[]}
 */
export function hotkeyGroups() {
  const parts = PALETTE.filter((e) => e.key).map((e) => ({
    keys: /** @type {string} */ (e.key).toUpperCase(), does: e.name,
    press: { key: /** @type {string} */ (e.key) }, action: "place",
  }));
  return [
    { title: "Drawing", rows: [
      { keys: "W", does: "Wire mode on or off", press: { key: "w" }, action: "wire" },
      { keys: "G", does: "Ground", press: { key: "g" }, action: "ground" },
      { keys: "L", does: "Net label", press: { key: "l" }, action: "label" },
      { keys: "X", does: "Text block", press: { key: "x" }, action: "text" },
      { keys: "B", does: "Insert a block", press: { key: "b" }, action: "insertBlock" },
      { keys: "Space", does: "Rotate the selected part", press: { key: " " }, action: "rotate" },
      { keys: "Enter", does: "Edit the selected part", press: { key: "Enter" }, action: "inspect" },
      { keys: "Del or Backspace", does: "Delete the selection", press: { key: "Delete" }, action: "delete" },
      { keys: "Esc", does: "Stop placing or wiring; close the open window", press: { key: "Escape" }, action: "cancel" },
    ] },
    { title: "Parts (press, then click where it goes)", rows: parts },
    { title: "Editing", rows: [
      { keys: "Ctrl+Z", does: "Undo", press: { key: "z", ctrl: true }, action: "undo" },
      { keys: "Ctrl+Shift+Z or Ctrl+Y", does: "Redo", press: { key: "y", ctrl: true }, action: "redo" },
      { keys: "Ctrl+C", does: "Copy the selection", press: { key: "c", ctrl: true }, action: "copy" },
      { keys: "Ctrl+V", does: "Paste (click where it goes)", press: { key: "v", ctrl: true }, action: "paste" },
      { keys: "Ctrl+A", does: "Select everything", press: { key: "a", ctrl: true }, action: "selectAll" },
      { keys: "Ctrl+F", does: "Find a part by its ref", press: { key: "f", ctrl: true }, action: "find" },
      { keys: "Ctrl+S", does: "Save", press: { key: "s", ctrl: true }, action: "save" },
      { keys: "Ctrl+Enter", does: "Run", press: { key: "Enter", ctrl: true }, action: "run" },
    ] },
    { title: "Mouse on the sheet", rows: [
      { keys: "Scroll", does: "Zoom" },
      { keys: "Drag empty space", does: "Pan" },
      { keys: "Shift+drag", does: "Select what's in the box (Ctrl+Shift+drag adds to it)" },
      { keys: "Ctrl+click", does: "Add or remove one thing from the selection (Shift+click too)" },
      { keys: "Double-click a part", does: "Edit it" },
    ] },
    { title: "Elsewhere", rows: [
      { keys: "Enter / Esc", does: "In a part's form: apply / cancel" },
      { keys: "Ctrl+Enter", does: "In a note: done" },
      { keys: "Shift (held)", does: "Frequency plot: name the parts that move each dot up or down" },
      { keys: "Shift+drag", does: "Frequency plot: move a peak or dip up or down" },
      { keys: "← → and Enter", does: "Bias & headroom bars: step the aim, then go" },
      { keys: "↑ ↓", does: "On a pane's ⋮⋮ grip: move the pane" },
    ] },
  ];
}
