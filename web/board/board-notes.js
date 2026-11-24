/**
 * The board's Notes pane (D-398): the builder's notes on the board, one list as the
 * schematic's Notes pane looks: each "C2, R1: solder C2 a bit higher." (a note with no
 * parts is about the whole board), out-of-date ones dimmed with why (the server's words),
 * with Edit… and Delete; + Note adds one. A note is written in a small form (Parts, the
 * text); a warning's Note… opens it with its parts filled in. Every change is a board edit
 * through the view (one undo step); a refusal is said in the form.
 */

import { openForm } from "../editor/form.js";
import { h } from "../panels.js";
import { noteLine, notePayload } from "./board-logic.js";

/**
 * @typedef {import("./board-logic.js").NoteState} NoteState
 * @param {HTMLElement} body the pane's body @param {HTMLElement} count the summary's count
 * @param {{notes: () => NoteState[], known: () => string[], host: HTMLElement,
 *   edit: (change: Record<string, unknown>, label: string) => Promise<string | null>}} deps
 *   `known` the board's refs (a typed ref matched whatever its case); `host` where the form
 *   goes; `edit` a board edit, its refusal returned
 */
export function boardNotes(body, count, deps) {
  /**
   * The note form: Parts and the text; saving sends `change` built from them.
   * @param {string} title @param {string[]} parts @param {string} text
   * @param {(values: Record<string, string>) => Promise<string | null>} save
   */
  function form(title, parts, text, save) {
    openForm(deps.host, {
      title,
      subtitle: "On the board",
      fields: [
        { name: "parts", label: "Parts", kind: "text", value: parts.join(", "), hint: "Optional: the parts it's about, e.g. C2, R1. Empty: a note on the whole board." },
        { name: "text", label: "Note", kind: "textarea", value: text, hint: "Kept with the board and printed on the build sheet." },
      ],
      submit: "Save",
      onSubmit: (values) => (values.text.trim() ? save(values) : Promise.resolve("A note needs some text.")),
    });
  }

  /**
   * A new note, its parts filled in (a warning's Note…: `overlap`, so it goes out of date
   * when they no longer touch).
   * @param {string[]} [parts] @param {boolean} [overlap]
   */
  function add(parts = [], overlap = false) {
    form("Board note", parts, "", (v) => deps.edit({ kind: "note-add", note: notePayload(v.parts, v.text, { parts, overlap }, deps.known()) }, "Add board note"));
  }

  /** @param {NoteState} note @param {number} index */
  function change(note, index) {
    form("Board note", note.parts, note.text, (v) => deps.edit({ kind: "note-set", index, note: notePayload(v.parts, v.text, note, deps.known()) }, "Edit board note"));
  }

  /** @param {NoteState} note @param {number} index */
  function row(note, index) {
    const edit = h("button", { type: "button", class: "link-button" }, ["Edit…"]);
    edit.addEventListener("click", () => change(note, index));
    const remove = h("button", { type: "button", class: "link-button" }, ["Delete"]);
    remove.title = "Delete this note (Undo brings it back)";
    remove.addEventListener("click", () => void deps.edit({ kind: "note-delete", index }, "Delete board note"));
    return h("li", { class: `board-note${note.why ? " out-of-date" : ""}`, "data-index": String(index) }, [
      h("span", { class: "note-line" }, [noteLine(note)]),
      ...(note.why ? [" ", h("span", { class: "note-why" }, [`(${note.why})`])] : []),
      " ", edit, " ", remove,
    ]);
  }

  /** Draw the pane for the board's notes as they are now. */
  function update() {
    const notes = deps.notes();
    count.textContent = notes.length ? `· ${notes.length}` : "";
    const plus = h("button", { type: "button", id: "board-notes-add", title: "Add a note to the board" }, ["+ Note"]);
    plus.addEventListener("click", () => add());
    body.replaceChildren(
      h("div", { class: "panel-tools notes-tools" }, [plus]),
      notes.length
        ? h("ul", { class: "board-list board-notes" }, notes.map(row))
        : h("p", { class: "empty" }, ["No notes yet. + Note adds one; a warning's Note… starts one about its parts."]),
    );
  }

  return { update, add };
}
