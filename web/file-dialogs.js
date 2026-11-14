/**
 * The file dialogs (DOM, D-075, D-076): Save, Save as, Open (Recent and All circuits,
 * D-287), Properties (with the enclosure, D-204), final and unlock, New major version,
 * Delete; and the name at the top renamed in place (`nameEditor`, D-287). The Open and Blocks
 * dialogs' shared list controls live here too (`listView`, `listControls`, `entryTag`).
 * The app root owns what is open; this module asks it through `app` and never keeps a
 * circuit of its own.
 */

import { deleteJson, getJson, patchJson, postJson, putJson } from "./api.js";
import { splitValues } from "./editor/edit.js";
import { importedFile, openSections, versionTag } from "./editor/files.js";
import { closeForm, confirmed, openForm } from "./editor/form.js";
import { h } from "./panels.js";
import { debounce } from "./state.js";
import { remember, remembered } from "./storage.js";

/**
 * @typedef {import("./app.js").Source} Source
 * @typedef {import("./app.js").FileInfo} FileInfo
 * @typedef {{link: string, id: string, name: string, version: string}} Saved what the server answers a save with
 *
 * @typedef {object} FileApp what the file dialogs ask of the app root
 * @property {() => Source | null} source what is open
 * @property {() => FileInfo | null} file the open file (null for a new sheet or an unsaved copy)
 * @property {() => any} circuit
 * @property {() => boolean} dirty unsaved changes
 * @property {() => boolean} isBlock the open thing is a block
 * @property {() => Array<{name: string, text: string}>} enclosures the standard enclosure sizes (D-204)
 * @property {(source: Source) => void} go open `source` (leaving is already fine)
 * @property {(source: Source) => Promise<void>} leaveTo open `source` once leaving is fine
 * @property {() => Promise<boolean>} confirmLeave the save prompt
 * @property {(next: any, label: string) => Promise<string | null>} tryEdit an edit checked with the server first; the error, if refused
 * @property {(saved: Saved, opts?: {renamed?: boolean}) => Promise<void>} afterSave the open circuit takes the saved name, id and version (and link, if renamed); `renamed`: only the name was saved, so unsaved changes stay unsaved and no undo step puts the old name back
 * @property {() => Promise<void>} refreshFile re-read the open file's details
 * @property {(dirty: boolean) => void} setDirty
 * @property {(message: string | null) => void} showError
 * @property {(text: string) => void} hint the line under the canvas
 */

/**
 * How a list dialog (Open, Blocks) was last left in this browser: sections (Blocks only),
 * sort, and "Current only" (on unless switched off). @param {string} key
 * @returns {{show: {user: boolean, core: boolean}, order: "az" | "za", current: boolean, remember: () => void}}
 */
export function listView(key) {
  const v = remembered(key) ?? {}; // nothing kept: the defaults
  const show = { user: v.show?.user !== false, core: v.show?.core !== false };
  const view = {
    show: show.user || show.core ? show : { user: true, core: true },
    order: /** @type {"az" | "za"} */ (v.order === "za" ? "za" : "az"),
    current: v.current !== false,
    remember: () => remember(key, { show: view.show, order: view.order, current: view.current }),
  };
  return view;
}

/**
 * The "Current only" switch and the A–Z / Z–A sort of a list dialog.
 * @param {ReturnType<typeof listView>} view @param {() => void} draw
 * @returns {HTMLElement[]}
 */
export function listControls(view, draw) {
  const current = h("button", { type: "button", "aria-pressed": String(view.current), "data-list-current": "", title: "Only the newest version of each; switch off to see older versions too" }, ["Current only"]);
  current.addEventListener("click", () => {
    view.current = !view.current;
    current.setAttribute("aria-pressed", String(view.current));
    view.remember();
    draw();
  });
  const order = h(
    "span",
    { class: "segmented", role: "radiogroup", "aria-label": "Sort by name" },
    /** @type {Array<["az" | "za", string]>} */ ([["az", "A\u2013Z"], ["za", "Z\u2013A"]]).map(([value, text]) => {
      const b = h("button", { type: "button", role: "radio", "aria-checked": String(view.order === value), "data-block-order": value, "data-list-order": value }, [text]);
      b.addEventListener("click", () => {
        for (const other of b.parentElement?.children ?? []) other.setAttribute("aria-checked", String(other === b));
        view.order = value;
        view.remember();
        draw();
      });
      return b;
    }),
  );
  return [h("span", { class: "segmented", role: "group", "aria-label": "Versions" }, [current]), order];
}

/** A list row's version tag: `v1.12`, `· final` when frozen. @param {any} e */
export const entryTag = (e) => h("span", { class: "tag" }, [e.problem ? "" : `${e.version}${e.final ? " \u00b7 final" : ""}`]);

/**
 * @param {HTMLElement} host where the dialogs open (the canvas)
 * @param {FileApp} app
 */
export function fileDialogs(host, app) {
  /**
   * Save over the open file; a new sheet, a starter, a core block or an unsaved copy asks
   * for a name (Save as). The server counts the version and renames the file when the name
   * changed. True once saved. @param {{stay?: boolean}} [opts] `stay`: don't open what a
   * Save as made (the save prompt is about to open something else)
   * @returns {Promise<boolean>}
   */
  async function save({ stay = false } = {}) {
    const src = app.source();
    if (app.file()?.readonly && app.file()?.layer === "user") {
      app.showError(`${app.circuit().name} is a final version, so it's read-only. Unlock it in File \u2192 Properties, or File \u2192 Save as\u2026 makes a copy.`);
      return false;
    }
    if ((src?.kind !== "circuit" && src?.kind !== "block") || app.file()?.readonly) return saveAs({ stay });
    const kind = src.kind === "block" ? "blocks" : "circuits";
    try {
      const saved = await putJson(`api/${kind}/${encodeURIComponent(src.id)}`, { circuit: app.circuit() });
      app.showError(null);
      app.hint(`Saved ${saved.name} (${saved.version}).`);
      await app.afterSave(saved);
      return true;
    } catch (err) {
      app.showError(/** @type {Error} */ (err).message);
      return false;
    }
  }

  /**
   * Save as a new circuit, or a new block in My blocks when a block is open. True once
   * saved; false when the dialog is cancelled. @param {{stay?: boolean}} [opts]
   * @returns {Promise<boolean>}
   */
  function saveAs({ stay = false } = {}) {
    const block = app.isBlock();
    const own = app.source()?.kind === "circuit" || (app.source()?.kind === "block" && app.file()?.layer === "user" && !app.file()?.readonly);
    const name = own ? `${app.circuit().name} copy` : app.source()?.kind === "new" ? "" : app.circuit().name;
    return new Promise((resolve) => {
      openForm(host, {
        title: block ? "Save as a new block" : "Save as a new circuit",
        subtitle: block ? "in My blocks" : "in My circuits",
        fields: [{ name: "name", label: "Name", kind: "text", value: name }],
        submit: "Save",
        onSubmit: async (values) => {
          try {
            const view = await postJson(block ? "api/blocks" : "api/circuits", { circuit: app.circuit(), name: values.name });
            app.setDirty(false);
            if (!stay) app.go({ kind: block ? "block" : "circuit", id: view.file?.link ?? view.circuit.id });
            return null;
          } catch (err) {
            return /** @type {Error} */ (err).message;
          }
        },
        onClose: resolve,
      });
    });
  }

  /** A new sheet (unsaved, with a guitar input and an amp output). */
  function newSheet() {
    return app.leaveTo({ kind: "new", id: "" });
  }

  /** "Import…" (D-315): a Solum Builder file from somewhere else (a circuit or a block, as
   * the app saves them: shared by someone, or written by an agent) saved as a new one of
   * yours, under the file's name or another, then opened. Never a netlist. */
  function importDialog() {
    const file = /** @type {HTMLInputElement} */ (h("input", { type: "file", id: "import-file", accept: ".json,application/json" }));
    /** @type {{circuit: any, name: string, block: boolean} | {error: string} | null} */
    let read = null;
    const handle = openForm(host, {
      title: "Import",
      subtitle: "a Solum Builder file (.json), not a netlist",
      fields: [{ name: "name", label: "Save it as", kind: "text", value: "" }],
      submit: "Import",
      onSubmit: async (values) => {
        if (!read) return "Choose a file first.";
        if ("error" in read) return read.error;
        const block = read.block;
        try {
          const view = await postJson(block ? "api/blocks" : "api/circuits", { circuit: read.circuit, name: values.name });
          app.hint(`Imported ${view.circuit.name} into ${block ? "My blocks" : "My circuits"}.`);
          app.leaveTo({ kind: block ? "block" : "circuit", id: view.file?.link ?? view.circuit.id });
          return null;
        } catch (err) {
          return /** @type {Error} */ (err).message;
        }
      },
    });
    const name = /** @type {HTMLInputElement} */ (handle.form.querySelector("#field-name"));
    // the file first, then the name it gives
    name.closest(".form-row")?.before(h("div", { class: "form-row" }, [h("label", { for: "import-file" }, ["File"]), file, h("span", { class: "unit" }, [])]));
    file.addEventListener("change", async () => {
      const picked = file.files?.[0];
      read = picked ? importedFile(await picked.text(), picked.name) : null;
      handle.showError(read && "error" in read ? read.error : null);
      if (read && !("error" in read)) name.value = read.name;
    });
  }

  /** "Open…": the user's circuits in two sections, Recent (the last three saved) and All
   * circuits (by name, D-076); current versions only unless switched off. A search (by
   * name, tag or part model) shows only its matches, no sections (D-287). */
  function openDialog() {
    const view = listView("solum.open.view");
    const list = h("div", { class: "open-list", role: "listbox", "aria-label": "My circuits" });
    /** @type {any[]} */
    let entries = [];
    let query = ""; // what `entries` was searched with
    const row = (/** @type {any} */ c, /** @type {"recent" | "all"} */ key) => {
      const b = /** @type {HTMLButtonElement} */ (
        h("button", { type: "button", role: "option", [key === "recent" ? "data-recent" : "data-circuit"]: c.id, title: c.problem ?? c.tags.join(", ") }, [c.problem ? `${c.id} (can't open)` : c.name, entryTag(c)])
      );
      b.disabled = Boolean(c.problem);
      b.addEventListener("click", () => {
        closeForm();
        app.leaveTo({ kind: "circuit", id: c.id });
      });
      return b;
    };
    const draw = () => {
      const sections = openSections(entries, view.order, view.current, Boolean(query));
      if (!sections.some((s) => s.rows.length)) return list.replaceChildren(h("p", { class: "empty" }, [query ? "No circuits match." : "Nothing saved yet. Save a circuit and it shows up here."]));
      list.replaceChildren(...sections.flatMap(({ key, title, rows }) => [...(title ? [h("h3", { class: "block-section" }, [title])] : []), ...rows.map((c) => row(c, key))]));
    };
    const fill = async () => {
      const q = search.value.trim();
      entries = await getJson(`api/circuits?q=${encodeURIComponent(q)}`);
      query = q;
      draw();
    };
    const handle = openForm(host, {
      title: "Open",
      subtitle: "my circuits",
      fields: [{ name: "q", label: "Search", kind: "text", value: "" }],
      submit: "Open first",
      extra: [h("div", { class: "block-bar" }, listControls(view, draw)), list],
      onSubmit: async () => {
        /** @type {HTMLButtonElement | null} */ (list.querySelector("button:not(:disabled)"))?.click();
        return list.querySelector("button:not(:disabled)") ? null : "No circuit to open.";
      },
    });
    const search = /** @type {HTMLInputElement} */ (handle.form.querySelector("#field-q"));
    search.addEventListener("input", debounce(() => fill().catch((err) => handle.showError(err.message)), 200));
    fill().catch((err) => handle.showError(err.message));
  }

  /** The open file is one of the user's own (not a starter, core block or new sheet). */
  const ownFile = () => app.file()?.layer === "user";

  async function deleteCircuit() {
    if (!ownFile()) return;
    const noun = app.isBlock() ? "block" : "circuit";
    const sure = await confirmed(`Delete the ${noun} \u201c${app.circuit().name}\u201d (${versionTag(app.circuit())})?`, "This version's file is removed and this can't be undone. Other versions stay.", "Delete", "delete");
    if (!sure) return;
    try {
      await deleteJson(`api/${noun}s/${encodeURIComponent(/** @type {Source} */ (app.source()).id)}`);
      app.go({ kind: "new", id: "" });
    } catch (err) {
      app.showError(/** @type {Error} */ (err).message);
    }
  }

  /** Why the open thing can't be renamed or changed in Properties, or null if it can. */
  function readonlyReason() {
    const f = app.file();
    if (!f?.readonly) return null;
    if (f.layer === "starter") return "Starters can't be changed. File \u2192 Save as\u2026 makes a copy you can name.";
    if (f.layer === "core") return "Core blocks can't be changed. Edit it from the Blocks dialog to make a copy.";
    return `${app.circuit().name} is a final version, so it's read-only. Unlock it in File \u2192 Properties first.`;
  }

  /**
   * Rename what is open to `name`. A saved file of the user's is renamed there and then
   * (every version's file follows, the minor counts one on); unsaved changes stay unsaved.
   * A new sheet or an unsaved copy has no file yet: its name is an edit, saved with it.
   * @param {string} name @returns {Promise<string | null>} what's wrong, or null once renamed
   */
  async function renameTo(name) {
    const src = app.source();
    if (!ownFile() || (src?.kind !== "circuit" && src?.kind !== "block")) return app.tryEdit({ ...app.circuit(), name }, "Rename");
    try {
      const view = await patchJson(`api/${src.kind}s/${encodeURIComponent(src.id)}`, { name });
      await app.afterSave({ link: view.file.link, id: view.circuit.id, name: view.circuit.name, version: versionTag(view.circuit) }, { renamed: true });
      app.showError(null);
      app.hint(`Renamed to ${view.circuit.name}.`);
      return null;
    } catch (err) {
      return /** @type {Error} */ (err).message;
    }
  }

  /**
   * The name at the top, renamed in place (D-287). The pencil after it opens the name
   * for editing and turns into a tick; Enter or the tick renames (`renameTo`), Esc or a
   * click elsewhere puts the old name back. What's wrong with a name (empty, taken) is
   * said under the box, which stays open. Called once by the root.
   * @param {{name: HTMLElement, box: HTMLInputElement, button: HTMLButtonElement, error: HTMLElement}} els
   */
  function nameEditor(els) {
    let busy = false; // the rename is with the server: a blur doesn't cancel it
    const editing = () => !els.box.hidden;
    const say = (/** @type {string | null} */ message) => {
      els.error.hidden = !message;
      els.error.textContent = message ?? "";
    };
    const show = (/** @type {boolean} */ on) => {
      els.box.hidden = !on;
      els.name.hidden = on;
      els.button.dataset.editing = String(on);
      const label = on ? "Rename to this (Enter); Esc puts the old name back" : "Rename";
      els.button.title = label;
      els.button.setAttribute("aria-label", label);
      say(null);
    };
    const start = () => {
      const why = readonlyReason();
      if (why) return app.showError(why);
      els.box.value = app.circuit().name;
      show(true);
      els.box.focus();
      els.box.select();
    };
    const commit = async () => {
      const name = els.box.value.trim();
      if (!name) return say(`Give the ${app.isBlock() ? "block" : "circuit"} a name.`);
      if (name === app.circuit().name) return show(false);
      busy = true;
      const message = await renameTo(name).finally(() => (busy = false));
      if (!message) return show(false);
      say(message);
      els.box.focus();
    };
    els.button.addEventListener("mousedown", (e) => e.preventDefault()); // the box keeps the focus: no blur before the click
    els.button.addEventListener("click", () => (editing() ? commit() : start()));
    els.box.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Enter") commit();
      else show(false);
    });
    els.box.addEventListener("blur", () => {
      if (!busy && editing()) show(false);
    });
    show(false);
  }

  /**
   * File → Properties… (D-075): name, tags and description (an edit, saved with Save), and
   * what the file is: kind, `<data>/…` path, version, when saved, final or not, with a
   * button to mark it final or unlock it.
   */
  function properties() {
    const c = app.circuit();
    const f = app.file();
    const why = readonlyReason();
    const when = f?.saved ? new Date(f.saved).toLocaleString() : "never";
    const info = h("dl", { class: "file-info" }, [
      ["Kind", app.isBlock() ? "Block" : "Circuit"],
      ["File", f?.path ?? "not saved yet"],
      ["Version", f ? versionTag(c) : "v1.0 when saved"],
      ["Last saved", when],
      ["Status", !f ? "not saved yet" : f.layer === "user" ? (c.final ? "final (read-only)" : "can be changed") : "built in (read-only)"],
    ].flatMap(([k, v]) => [h("dt", {}, [k]), h("dd", { "data-info": k.toLowerCase().replace(" ", "-") }, [v])]));
    const extra = [info];
    if (ownFile()) {
      const lock = h("button", { type: "button", id: "toggle-final" }, [c.final ? "Unlock\u2026" : "Mark as final"]);
      lock.addEventListener("click", () => setFinal(!c.final).then((message) => (message ? handle.showError(message) : closeForm())));
      extra.push(h("div", { class: "file-actions" }, [lock]));
    }
    const handle = openForm(host, {
      title: "Properties",
      subtitle: why ? "read-only" : "changes are saved with Save",
      fields: [
        { name: "name", label: "Name", kind: "text", value: c.name },
        { name: "tags", label: "Tags", kind: "text", value: (c.tags ?? []).join(", "), hint: "Comma-separated, for search." },
        { name: "description", label: "Description", kind: "text", value: c.description ?? "" },
        ...(app.isBlock() ? [] : enclosureFields(c.enclosure)),
      ],
      extra,
      onSubmit: async (values) => {
        const name = values.name.trim();
        if (!name) return `Give the ${app.isBlock() ? "block" : "circuit"} a name.`;
        const box = app.isBlock() ? { enclosure: c.enclosure ?? null } : enclosureOf(values);
        if ("error" in box) return box.error;
        const { enclosure: _old, ...rest } = c;
        const next = { ...rest, name, tags: splitValues(values.tags), description: values.description.trim(), ...(box.enclosure ? { enclosure: box.enclosure } : {}) };
        const same = next.name === c.name && next.description === (c.description ?? "") && JSON.stringify(next.tags) === JSON.stringify(c.tags ?? []) && JSON.stringify(next.enclosure ?? null) === JSON.stringify(c.enclosure ?? null);
        if (same) return null;
        return why ?? app.tryEdit(next, "Edit properties");
      },
    });
  }

  /**
   * File → Properties' enclosure (D-204): a standard size (`app.enclosures()`, from the
   * server), Custom with its mm, or none yet.
   * @param {any} box the circuit's `enclosure` @returns {import("./editor/fields.js").Field[]}
   */
  function enclosureFields(box) {
    /** @type {Array<[string, string]>} */
    const options = [["", "not chosen yet"], ...app.enclosures().map((e) => /** @type {[string, string]} */ ([e.name, `${e.name} \u00b7 ${e.text}`])), ["custom", "Custom\u2026"]];
    const mm = (/** @type {string} */ name, /** @type {string} */ label) => ({ name, label, kind: /** @type {const} */ ("number"), unit: "mm", value: box?.size === "custom" ? String(box[name]) : "", showIf: { field: "enclosure", is: "custom" } });
    return [
      { name: "enclosure", label: "Enclosure", kind: "select", value: box?.size ?? "", options, hint: "For the parts list; sizes outside, as sellers list them." },
      mm("length", "Length"), mm("width", "Width"), mm("height", "Height"),
    ];
  }

  /**
   * The enclosure the form's values give, or what's wrong with them.
   * @param {Record<string, string>} v @returns {{enclosure: any} | {error: string}}
   */
  function enclosureOf(v) {
    if (!v.enclosure) return { enclosure: null };
    if (v.enclosure !== "custom") return { enclosure: { size: v.enclosure } };
    const dims = ["length", "width", "height"].map((k) => Number(v[k]));
    if (dims.some((x) => !(x > 0 && x <= 1000))) return { error: "Give a custom enclosure's length, width and height in mm." };
    const [length, width, height] = dims;
    return { enclosure: { size: "custom", length, width, height } };
  }

  /**
   * Mark the open file final (read-only) or unlock it. Locking needs nothing unsaved;
   * unlocking asks first. Neither changes the version. Returns a message, or null when done.
   * @param {boolean} final
   */
  async function setFinal(final) {
    if (final && app.dirty()) return "Save your changes first, then mark it final.";
    if (!final) {
      const sure = await confirmed(`Unlock \u201c${app.circuit().name}\u201d?`, "This is a finished version. Unlock it to make changes; its version keeps counting on from where it is.", "Unlock", "unlock");
      if (!sure) return "Still final.";
    }
    const src = /** @type {Source} */ (app.source());
    await patchJson(`api/${src.kind}s/${encodeURIComponent(src.id)}`, { final });
    await app.refreshFile();
    app.hint(final ? `${app.circuit().name} is final (read-only).` : `${app.circuit().name} is unlocked.`);
    return null;
  }

  /**
   * File → New major version… (D-075, D-076): the saved version is kept as final
   * (read-only) and work carries on in a new file at the next major (`v2.0`). Unsaved
   * changes are asked about first, so what's kept is what's on disk.
   */
  async function newMajor() {
    if (!ownFile() || !app.file()?.current) return;
    if (!(await app.confirmLeave())) return;
    const c = app.circuit();
    const major = c.version?.major ?? 1;
    const sure = await confirmed(`Start version ${major + 1} of \u201c${c.name}\u201d?`, `Version ${major} (${versionTag(c)}) is kept as final and read-only, and you carry on with v${major + 1}.0. Older versions show in the lists when Current only is off.`, `Start v${major + 1}`, "go");
    if (!sure) return;
    const src = /** @type {Source} */ (app.source());
    try {
      const view = await postJson(`api/${src.kind}s/${encodeURIComponent(src.id)}/major`, {});
      app.go(src); // reopen: now at the next major
      app.hint(`Kept ${view.final_copy.version} as final. ${c.name} is now v${major + 1}.0.`);
    } catch (err) {
      app.showError(/** @type {Error} */ (err).message);
    }
  }

  return { save, saveAs, newSheet, openDialog, importDialog, deleteCircuit, nameEditor, properties, newMajor, ownFile, readonlyReason };
}
