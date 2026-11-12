/**
 * The Notes pane (9d4): a General tab of titled notes (+ Note adds one; collapsible, one
 * open at a time) and a Parts tab listing every part and net note under its ref or net
 * name (a click selects it on the drawing). Editing is in place: a field's change is
 * one edit through the editor's path (undo, the unsaved marker) when it loses focus.
 * The logic is in `notes-logic.js`; this is the DOM.
 */

import { h } from "./panels.js";
import { addNote, deleteNote, itemNotes, mentions, notesCount, replaceMentions, setNetNote, setNote, setPartNote, whereKey } from "./notes-logic.js";

/**
 * @typedef {import("./notes-logic.js").Circuit} Circuit
 * @typedef {"general" | "parts"} Tab
 * @param {HTMLElement} body the pane's body @param {HTMLElement} count the summary's count
 * @param {{circuit: () => Circuit | null, nets: () => Set<string>,
 *   edit: (next: Circuit, label: string) => Promise<string | null>,
 *   select: (kind: "part" | "net", id: string) => void, reveal: () => void}} deps
 *   `reveal` opens the pane and brings it into view
 */
export function notesPane(body, count, deps) {
  /** @type {Tab} */ let tab = "general";
  /** @type {string | null} the open note: `g:2`, `p:R1` or `n:VREF` */ let open = null;
  /** @type {string} a problem saving, shown until the next change */ let error = "";

  /** @param {Circuit} next @param {string} label */
  async function commit(next, label) {
    error = (await deps.edit(next, label)) ?? "";
    if (error) update();
  }

  /** @param {Tab} to */
  function setTab(to) {
    tab = to;
    update();
  }

  function addGeneral() {
    const c = deps.circuit();
    if (!c) return;
    open = `g:${c.notes?.length ?? 0}`;
    tab = "general";
    commit(addNote(c, { title: "New note" }), "Add note").then(() => {
      const title = /** @type {HTMLInputElement | null} */ (body.querySelector(`[data-note="${open}"] .note-title`));
      title?.focus();
      title?.select();
    });
  }

  /** @param {string} key */
  function toggle(key) {
    open = open === key ? null : key;
    update();
  }

  /**
   * One note's row: its head (a click opens or shuts it) and, open, its fields.
   * @param {string} key @param {(string | Node)[]} head @param {() => Node[]} fields
   */
  function row(key, head, fields) {
    const isOpen = open === key;
    const button = h("button", { type: "button", class: "note-head", "aria-expanded": String(isOpen) }, [h("span", { class: "note-caret", "aria-hidden": "true" }, [isOpen ? "▾" : "▸"]), ...head]);
    button.addEventListener("click", () => {
      toggle(key);
      const [kind, id] = [key.slice(0, 1), key.slice(2)];
      if (open === key && kind !== "g") deps.select(kind === "p" ? "part" : "net", id);
    });
    return h("li", { class: `note-item${isOpen ? " open" : ""}`, "data-note": key }, [button, ...(isOpen ? fields() : [])]);
  }

  /**
   * A field that saves when it loses focus with a change (Enter in a title, Ctrl+Enter in
   * a text, do it at once).
   * @param {"input" | "textarea"} tag @param {string} cls @param {string} value
   * @param {(value: string) => void} save @param {string} label
   */
  function field(tag, cls, value, save, label) {
    const attrs = { class: cls, "aria-label": label, ...(tag === "input" ? { type: "text", maxlength: "100" } : { rows: "5", maxlength: "5000" }) };
    const el = /** @type {HTMLInputElement | HTMLTextAreaElement} */ (h(tag, attrs));
    el.value = value;
    el.addEventListener("change", () => save(el.value));
    el.addEventListener("keydown", (e) => {
      const ke = /** @type {KeyboardEvent} */ (e);
      if (ke.key === "Enter" && (tag === "input" || ke.ctrlKey || ke.metaKey)) {
        ke.preventDefault();
        el.blur();
      }
      ke.stopPropagation(); // typing isn't a shortcut on the sheet
    });
    return el;
  }

  /** @param {string} label @param {() => void} run */
  function deleteButton(label, run) {
    const b = h("button", { type: "button", class: "note-delete" }, ["Delete"]);
    b.title = label;
    b.addEventListener("click", run);
    return b;
  }

  /** @param {Circuit} c */
  function general(c) {
    const notes = c.notes ?? [];
    if (!notes.length) return [h("p", { class: "hint notes-empty" }, ["No notes yet. + Note adds one; a block you drop adds its description as one."])];
    return [h("ul", { class: "notes-list" }, notes.map((n, i) => row(`g:${i}`, [h("span", { class: "note-name" }, [n.title || "Untitled note"])], () => [
      field("input", "note-title", n.title ?? "", (v) => commit(setNote(c, i, { ...n, title: v }), "Edit note title"), "Title"),
      field("textarea", "note-text", n.text ?? "", (v) => commit(setNote(c, i, { ...n, text: v }), "Edit note"), "Note"),
      h("div", { class: "note-buttons" }, [deleteButton("Delete this note (Undo brings it back)", () => {
        open = null;
        commit(deleteNote(c, i), "Delete note");
      })]),
    ])))];
  }

  /** @param {Circuit} c */
  function parts(c) {
    const items = itemNotes(c);
    if (!items.length) return [h("p", { class: "hint notes-empty" }, ["No part or net notes. Right-click a part or a wire, then Add note…"])];
    const nets = deps.nets();
    return [h("ul", { class: "notes-list" }, items.map((item) => {
      const key = `${item.kind === "part" ? "p" : "n"}:${item.id}`;
      const gone = item.kind === "net" && !nets.has(item.id);
      const head = [
        h("span", { class: "note-name" }, [item.id]),
        h("span", { class: "note-kind" }, [item.kind === "part" ? "part" : gone ? "net, not on the sheet now" : "net"]),
        h("span", { class: "note-preview" }, [item.text.split("\n")[0]]),
      ];
      const set = item.kind === "part" ? setPartNote : setNetNote;
      return row(key, head, () => [
        field("textarea", "note-text", item.text, (v) => commit(set(c, item.id, v), `Edit ${item.id}'s note`), `${item.id}'s note`),
        h("div", { class: "note-buttons" }, [deleteButton(`Delete ${item.id}'s note (Undo brings it back)`, () => {
          open = null;
          commit(set(c, item.id, ""), `Delete ${item.id}'s note`);
        })]),
      ]);
    }))];
  }

  /** Draw the pane for the circuit as it is now, keeping the focused field and its caret. */
  function update() {
    const c = deps.circuit();
    const active = /** @type {HTMLElement | null} */ (document.activeElement);
    const typing = active && body.contains(active) && (active.tagName === "INPUT" || active.tagName === "TEXTAREA");
    const focused = typing ? { note: active.closest("[data-note]")?.getAttribute("data-note"), cls: active.className,
      start: /** @type {HTMLInputElement} */ (active).selectionStart, end: /** @type {HTMLInputElement} */ (active).selectionEnd } : null;
    const general_ = c?.notes?.length ?? 0;
    const parts_ = c ? itemNotes(c).length : 0;
    count.textContent = general_ + parts_ ? String(general_ + parts_) : "";
    if (!c) return body.replaceChildren();
    const tabs = h("span", { class: "segmented", role: "radiogroup", "aria-label": "Notes shown" }, [
      tabButton("general", `General${general_ ? ` (${general_})` : ""}`),
      tabButton("parts", `Parts & nets${parts_ ? ` (${parts_})` : ""}`),
    ]);
    const add = h("button", { type: "button", id: "notes-add", title: "Add a titled note to the circuit" }, ["+ Note"]);
    add.addEventListener("click", addGeneral);
    body.replaceChildren(
      h("div", { class: "panel-tools notes-tools" }, [tabs, ...(tab === "general" ? [add] : [])]),
      ...(error ? [h("p", { class: "error", role: "alert" }, [error])] : []),
      // a fixed-size box under the tabs: the pane keeps its height across tabs, and scrolls
      h("div", { class: "notes-scroll" }, tab === "general" ? general(c) : parts(c)),
    );
    if (focused?.note) {
      const again = /** @type {HTMLInputElement | null} */ (body.querySelector(`[data-note="${focused.note}"] .${focused.cls.split(" ")[0]}`));
      again?.focus();
      if (again && focused.start !== null) again.setSelectionRange(focused.start, focused.end);
    }
  }

  /** @param {Tab} id @param {string} label */
  function tabButton(id, label) {
    const b = h("button", { type: "button", role: "radio", "aria-checked": String(tab === id), "data-tab": id }, [label]);
    b.addEventListener("click", () => setTab(id));
    return b;
  }

  /**
   * Open one note in the pane: a general note by index, or a part's or net's.
   * @param {import("./notes-logic.js").Where} where @param {boolean} [focus] put the caret in its text
   */
  function show(where, focus = true) {
    tab = where.kind === "general" ? "general" : "parts";
    open = where.kind === "general" ? `g:${where.index}` : where.kind === "part" ? `p:${where.ref}` : `n:${where.net}`;
    deps.reveal();
    update();
    body.querySelector(`[data-note="${open}"]`)?.scrollIntoView({ block: "nearest" });
    if (focus) /** @type {HTMLElement | null} */ (body.querySelector(`[data-note="${open}"] .note-text`))?.focus();
  }

  return { update, show };
}

/** "C7", "C7 and C8", "IC1, IC1A and IC1B". @param {string[]} names */
const listed = (names) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

/**
 * The box after renaming a part or net that notes mention (9d4, the user's design; over
 * the middle of the drawing, D-271): "C7 is mentioned in 2 notes (it's C9 now)", with
 * Show, Replace and Close. It also lists the notes that already use the new name (after
 * an earlier Replace, or a name the part had before), for information. Replace changes every
 * whole-word mention (one undo step); Show lists them in place, each with the text around
 * it and a tick box, and Replace then changes the ticked ones; a note's name opens it in
 * the Notes pane; ✕ closes it with nothing changed. Never automatic. After any other edit
 * it looks again, and goes when nothing is left to replace or the rename was undone.
 * @param {HTMLElement} host
 * @param {{circuit: () => Circuit | null, edit: (next: Circuit, label: string) => Promise<string | null>,
 *   open: (where: import("./notes-logic.js").Where) => void}} deps
 */
export function renameNotice(host, deps) {
  /** @type {import("./notes-logic.js").Rename[]} */ let renames = [];
  let expanded = false;
  /** @type {Set<string>} mentions unticked, by `whereKey|field|start` */ let unticked = new Set();
  let error = "";

  /** @param {import("./notes-logic.js").Mention} m */
  const id = (m) => `${whereKey(m.where)}|${m.field}|${m.start}`;

  /** Whether the renamed names are still there (an undo takes them away). @param {Circuit} c */
  function stillRenamed(c) {
    const names = new Set([...c.parts.map((p) => p.ref), ...c.parts.map((p) => p.ref.slice(0, -1)), ...(c.labels ?? []).map((lb) => lb.net)]);
    return renames.some((r) => names.has(r.to));
  }

  function hide() {
    renames = [];
    host.hidden = true;
    host.replaceChildren();
  }

  function draw() {
    const c = deps.circuit();
    const live = c && renames.length && stillRenamed(c);
    const found = live ? mentions(c, renames) : [];
    // notes that already use the new name (an earlier Replace, or a name the part had before)
    const already = live ? mentions(c, renames.map((r) => ({ from: r.to, to: r.to }))) : [];
    if (!c || !(found.length + already.length)) return hide();
    const names = (/** @type {import("./notes-logic.js").Mention[]} */ ms) => [...new Set(ms.map((m) => m.from))];
    const froms = names(found);
    const tos = froms.map((f) => /** @type {import("./notes-logic.js").Rename} */ (renames.find((r) => r.from === f)).to);
    const nows = names(already);
    const notes = (/** @type {number} */ n) => `${n} note${n > 1 ? "s" : ""}`;
    const button = (/** @type {string} */ label, /** @type {string} */ name, /** @type {() => void} */ run, /** @type {string} */ title, cls = "") => {
      const b = h("button", { type: "button", "data-action": name, title, ...(cls ? { class: cls } : {}) }, [label]);
      b.addEventListener("click", run);
      return b;
    };
    const said = [];
    if (found.length) {
      said.push(h("strong", {}, [listed(froms)]), ` ${froms.length > 1 ? "are" : "is"} mentioned in ${notes(notesCount(found))} (${froms.length > 1 ? "now" : "it\u2019s"} ${listed(tos)}${froms.length > 1 ? "" : " now"}).`);
    } else {
      said.push(`No note mentions ${listed(renames.map((r) => r.from))}.`);
    }
    if (already.length) said.push(` ${notes(notesCount(already))} already say${notesCount(already) > 1 ? "" : "s"} `, h("strong", {}, [listed(nows)]), ".");
    const row = (/** @type {import("./notes-logic.js").Mention} */ m, /** @type {boolean} */ tickable) => {
      const name = button(m.label, "open", () => deps.open(m.where), "Open this note in the Notes pane to edit it by hand", "link-button");
      const text = h("span", { class: "mention-text" }, [m.before, h("mark", {}, [m.from]), m.after]);
      if (!tickable) return h("li", {}, [name, ": ", text]);
      const tick = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", "aria-label": `Replace this ${m.from}` }));
      tick.checked = !unticked.has(id(m));
      tick.addEventListener("change", () => { if (tick.checked) unticked.delete(id(m)); else unticked.add(id(m)); });
      return h("li", {}, [tick, " ", name, ": ", text]);
    };
    const lists = expanded
      ? [
          ...(found.length ? [h("h3", {}, [`To change to ${listed(tos)}`]), h("ul", { class: "mentions" }, found.map((m) => row(m, true)))] : []),
          ...(already.length ? [h("h3", {}, [`Already say ${listed(nows)}`]), h("ul", { class: "mentions" }, already.map((m) => row(m, false)))] : []),
        ]
      : [];
    const buttons = [
      button(expanded ? "Hide" : "Show", "show", () => { expanded = !expanded; draw(); }, "List each mention, to choose which to change"),
      ...(found.length ? [button("Replace", "replace", () => replace(found), expanded ? "Change the ticked mentions to the new name" : "Change every mention to the new name (Undo takes it back)", "primary")] : []),
    ];
    const close = button("Close", "close", hide, "Close, changing nothing", "sheet-close");
    const title = `Renamed ${renames[0].from} to ${renames[0].to}`; // a chip's name first (IC1 to IC2)
    host.replaceChildren(h("div", { class: "sheet rename-sheet", role: "dialog", "aria-label": "Notes that mention the renamed name" }, [
      h("div", { class: "sheet-head" }, [h("h2", { class: "sheet-title" }, [title]), close]),
      h("div", { class: "sheet-body" }, [
        h("p", {}, said),
        ...lists,
        ...(error ? [h("p", { class: "error", role: "alert" }, [error])] : []),
        h("div", { class: "ask-buttons" }, buttons),
      ]),
    ]));
    host.hidden = false;
  }

  /** @param {import("./notes-logic.js").Mention[]} found */
  async function replace(found) {
    const c = deps.circuit();
    if (!c) return;
    const picked = expanded ? found.filter((m) => !unticked.has(id(m))) : found;
    if (!picked.length) return hide();
    const what = [...new Set(picked.map((m) => `${m.from} with ${m.to}`))].join(", ");
    error = (await deps.edit(replaceMentions(c, picked), `Replace ${what} in notes`)) ?? "";
    if (error) draw();
    else hide();
  }

  return {
    /** A rename was made: offer to update the notes that mention it. @param {import("./notes-logic.js").Rename[]} made */
    show(made) {
      renames = made;
      expanded = false;
      unticked = new Set();
      error = "";
      draw();
    },
    /** The circuit changed: look again (some mentions may have gone; ticks are by place, so they reset). */
    update() {
      if (!renames.length) return;
      unticked = new Set();
      draw();
    },
    hide,
  };
}
