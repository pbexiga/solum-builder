/**
 * One popup form (DOM) for the inspector, the label editor and the circuit dialogs.
 * Fields come from fields.js descriptors; `onSubmit` gets the values by field name and
 * answers with an error message to show, or null to close. `ask` is the modal question
 * with a few buttons (the save prompt, D-075).
 */

import { h, infoPopup } from "../panels.js";
import { fieldProblem } from "./fields.js";

/** @type {{close: () => void} | null} */
let open = null;

/** Close whatever form is open. */
export function closeForm() {
  open?.close();
}

/** @returns {boolean} */
export function formIsOpen() {
  return open !== null;
}

/** @type {ReturnType<typeof infoPopup> | null} the forms' ⓘ pop-up (made once, shared) */
let about = null;

/**
 * The form's ⓘ (9c's info pass): each shown field's `about` under its label, for what
 * doesn't fit a hint (how to measure it, the datasheet's range, the background). Built as
 * it opens, so a row hidden by then (a measured box while the model's is picked) is left
 * out. Null when no field has one.
 * @param {string} title @param {import("./fields.js").Field[]} fields @param {HTMLElement[]} rows
 */
function aboutButton(title, fields, rows) {
  if (!fields.some((f) => f.about)) return null;
  about ??= infoPopup();
  return about.button(title, () => fields.flatMap((f, i) => {
    if (!f.about || rows[i].hidden) return [];
    const paras = Array.isArray(f.about) ? f.about : [f.about];
    return [h("h5", {}, [f.label]), ...paras.map((t) => h("p", { class: "note" }, [t]))];
  }), `About ${title}: what its boxes mean, how to measure them`);
}

/** A hint that opens a Help page. @param {string} text @param {string} page @param {(page: string) => void} onHelp */
function helpLink(text, page, onHelp) {
  const b = h("button", { type: "button", class: "link", "data-help": page }, [text]);
  b.addEventListener("click", () => onHelp(page));
  return b;
}

/** Lines a read-only value needs at the form's width (about 36 characters a line). @param {string} text */
function readRows(text) {
  return Math.max(1, Math.ceil((text ?? "").length / 36));
}

/** @param {import("./fields.js").Field} f */
function input(f) {
  if (f.kind === "select") {
    const s = /** @type {HTMLSelectElement} */ (h("select", { name: f.name, id: `field-${f.name}` }));
    // an option's third item is its group (`<optgroup>`): yours, then stock (9c)
    /** @type {HTMLOptGroupElement | null} */
    let group = null;
    for (const [value, label, named] of f.options ?? []) {
      if (named && group?.label !== named) s.append((group = /** @type {HTMLOptGroupElement} */ (h("optgroup", { label: named }))));
      else if (!named) group = null;
      (named && group ? group : s).append(new Option(label, value, false, value === f.value));
    }
    return s;
  }
  if (f.kind === "textarea") return h("textarea", { name: f.name, id: `field-${f.name}`, rows: "4", spellcheck: "true" }, [f.value]);
  // a value to read, not type: it wraps, so a long one shows whole (the user, 2026-10-28)
  if (f.readonly && f.kind !== "number") return h("textarea", { name: f.name, id: `field-${f.name}`, class: "readonly-text", readonly: "", rows: String(readRows(f.value)) }, [f.value]);
  const attrs = { name: f.name, id: `field-${f.name}`, value: f.value, autocomplete: "off", spellcheck: "false", ...(f.readonly ? { readonly: "" } : {}) };
  return h("input", f.kind === "number" ? { ...attrs, type: "text", inputmode: "decimal" } : { ...attrs, type: "text" });
}

/**
 * Wire up `fills` (picking an option sets other fields), `showIf` (a row shows only while
 * another field isn't a value), `lockedWhile` (read-only while those fields are filled:
 * back to its value as opened, `lockedHint` in place of its hint; the row gets `.locked`),
 * `remove` (its button empties those fields and hides their rows; an `add` on them comes
 * back) and `add` (its button shows those rows, picks fill as if chosen, and hides while
 * they show). A number field's problem (`fieldProblem`) is said as soon as its box is left.
 * @param {import("./fields.js").Field[]} fields @param {HTMLElement[]} rows in the same order
 * @param {(message: string | null) => void} showError
 */
function linkFields(fields, rows, showError) {
  const control = (/** @type {string} */ name) => {
    const i = fields.findIndex((f) => f.name === name);
    return i < 0 ? null : /** @type {HTMLInputElement | HTMLSelectElement} */ (rows[i].querySelector("input, select, textarea"));
  };
  const rowOf = (/** @type {string} */ name) => /** @type {HTMLElement | undefined} */ (control(name)?.closest(".form-row"));
  /** @type {string | null} the field whose problem the error line says */
  let saying = null;
  /** Said or cleared for field `f` as its box is now. @param {import("./fields.js").Field} f @param {HTMLInputElement} box */
  const check = (f, box) => {
    const problem = box.readOnly ? null : fieldProblem(f, box.value);
    if (problem) {
      saying = f.name;
      showError(problem);
    } else if (saying === f.name) {
      saying = null;
      showError(null);
    }
  };
  /** Each Add target button, shown while any of its fields' rows is hidden. */
  const adds = () => fields.forEach((f, k) => {
    const button = /** @type {HTMLElement | null} */ (rows[k].querySelector(".field-add"));
    if (f.add && button) button.hidden = f.add.fields.every((n) => !rowOf(n)?.hidden);
  });
  fields.forEach((f, i) => {
    const own = control(f.name);
    if (f.fills && own) {
      own.addEventListener("change", () => {
        for (const [name, value] of Object.entries(f.fills?.[own.value] ?? {})) {
          const other = control(name);
          if (other) other.value = value;
        }
      });
    }
    const box = /** @type {HTMLInputElement | null} */ (rows[i].querySelector("input"));
    if (f.kind === "number" && box) box.addEventListener("change", () => check(f, box));
    const locks = (f.lockedWhile ?? []).map(control).filter((c) => c !== null);
    if (locks.length && box) {
      const hint = /** @type {HTMLElement | null} */ (rows[i].querySelector(".hint-text"));
      const lock = () => {
        const now = locks.every((c) => /** @type {HTMLInputElement} */ (c).value.trim() !== "");
        if (now && !box.readOnly) box.value = box.defaultValue; // what it was typed to doesn't count: the target turns it
        box.readOnly = now;
        rows[i].classList.toggle("locked", now);
        if (hint && f.lockedHint) hint.textContent = now ? f.lockedHint : f.hint ?? "";
        check(f, box);
      };
      for (const c of locks) /** @type {HTMLElement} */ (c).addEventListener("input", lock);
      lock();
    }
    const gone = f.remove;
    const button = rows[i].querySelector(".field-remove:not(.field-add)");
    if (gone && button) {
      button.addEventListener("click", () => {
        for (const name of gone.fields) {
          const c = control(name);
          if (!c) continue;
          if (!(c instanceof HTMLSelectElement)) c.value = ""; // a pick stays, for Add target
          c.dispatchEvent(new Event("input")); // a lock on it lets go
          /** @type {HTMLElement} */ (c.closest(".form-row")).hidden = true;
        }
        adds();
        // an error about them no longer holds
        if (saying === null) showError(null);
        /** @type {HTMLElement | null} */ (rows.find((r) => r.querySelector(".field-add:not([hidden])"))?.querySelector(".field-add") ?? null)?.focus();
      });
    }
    const added = f.add;
    const addButton = /** @type {HTMLElement | null} */ (rows[i].querySelector(".field-add"));
    if (added && addButton) {
      addButton.addEventListener("click", () => {
        for (const name of added.fields) {
          const c = control(name);
          if (!c) continue;
          /** @type {HTMLElement} */ (c.closest(".form-row")).hidden = false;
          const value = added.values?.[name];
          if (value !== undefined && !c.value) c.value = value;
          if (c instanceof HTMLSelectElement) c.dispatchEvent(new Event("change")); // its `fills`, as if picked
        }
        for (const name of added.fields) control(name)?.dispatchEvent(new Event("input")); // a lock on them holds
        adds();
        control(added.fields[added.fields.length - 1])?.focus();
      });
    }
    const when = f.showIf;
    const other = when && control(when.field);
    if (when && other) {
      const show = () => (rows[i].hidden = when.is !== undefined ? other.value !== when.is : other.value === when.not);
      other.addEventListener("change", show);
      show();
    }
  });
  adds();
}

/**
 * @param {HTMLElement} host where the popup goes
 * @param {{title: string, subtitle?: string, fields: import("./fields.js").Field[], submit?: string,
 *   onSubmit: (values: Record<string, string>) => Promise<string | null>, extra?: HTMLElement[],
 *   onClose?: (submitted: boolean) => void, onHelp?: (page: string) => void}} spec `onClose`: called once when the form goes
 *   (saved, cancelled, Escape, or another form opened); `onHelp`: a field's `help` link clicked
 * @returns {{close: () => void, form: HTMLFormElement, showError: (message: string | null) => void, fields: import("./fields.js").Field[]}}
 *   `fields`: the form's, read again each time its ⓘ opens (a field's `about` may be updated)
 */
export function openForm(host, spec) {
  closeForm();
  const error = h("p", { class: "error", role: "alert", hidden: "" });
  const rows = spec.fields.map((f) =>
    h("div", { class: "form-row" }, [
      h("label", { for: `field-${f.name}` }, [f.label]),
      input(f),
      h("span", { class: "unit" }, [f.unit ?? ""]),
      ...(f.hint ? [h("span", { class: "hint-text" }, [f.help && spec.onHelp ? helpLink(f.hint, f.help, spec.onHelp) : f.hint])] : []),
      ...(f.remove ? [h("button", { type: "button", class: "field-remove", id: `field-${f.name}-remove` }, [f.remove.label])] : []),
      ...(f.add ? [h("button", { type: "button", class: "field-remove field-add", id: `field-${f.name}-add` }, [f.add.label])] : []),
    ]),
  );
  spec.fields.forEach((f, i) => { if (f.hidden) rows[i].hidden = true; });
  const info = aboutButton(spec.title, spec.fields, rows);
  const form = /** @type {HTMLFormElement} */ (
    h("form", { class: "popup", "aria-label": spec.title }, [
      h("div", { class: "popup-title" }, [h("span", { class: "name" }, [spec.title]), h("span", { class: "kind" }, [spec.subtitle ?? ""]), ...(info ? [info] : [])]),
      ...rows,
      error,
      h("div", { class: "popup-buttons" }, [
        h("button", { type: "button", "data-action": "cancel" }, ["Cancel"]),
        h("button", { type: "submit", class: "primary" }, [spec.submit ?? "Apply"]),
      ]),
      ...(spec.extra ?? []),
    ])
  );
  const showError = (/** @type {string | null} */ message) => {
    error.hidden = !message;
    error.textContent = message ?? "";
  };
  linkFields(spec.fields, rows, showError);
  let closed = false;
  const close = (submitted = false) => {
    about?.close();
    form.remove();
    if (open === handle) open = null;
    if (!closed) spec.onClose?.(submitted);
    closed = true;
  };
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const values = Object.fromEntries([...new FormData(form).entries()].map(([k, v]) => [k, String(v)]));
    const message = await spec.onSubmit(values);
    if (message) showError(message);
    else close(true);
  });
  form.querySelector('[data-action="cancel"]')?.addEventListener("click", () => close());
  form.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      close();
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target instanceof HTMLTextAreaElement) {
      e.preventDefault(); // Enter is a new line in a text box; Ctrl+Enter applies
      form.requestSubmit();
    }
  });
  host.append(form);
  const handle = { close: () => close(), form, showError, fields: spec.fields };
  open = handle;
  /** @type {HTMLElement | null} */ (form.querySelector("input, select, textarea"))?.focus();
  return handle;
}

/**
 * A modal question with a few buttons (the save prompt, D-075), laid out the usual way:
 * an `aside` button on the left, apart from the others; the `primary` one answers Enter
 * and has the focus; Escape answers `cancel`.
 * @template {string} V
 * @param {{title: string, text?: string, cancel: V,
 *   buttons: Array<{label: string, value: V, kind?: "primary" | "aside"}>}} spec
 * @returns {Promise<V>}
 */
export function ask(spec) {
  return new Promise((resolve) => {
    const answer = (/** @type {V} */ value) => {
      shade.remove();
      resolve(value);
    };
    const buttons = spec.buttons.map((b) => {
      const el = h("button", { type: "button", "data-answer": b.value, ...(b.kind ? { class: b.kind } : {}) }, [b.label]);
      el.addEventListener("click", () => answer(b.value));
      return el;
    });
    const dialog = h("div", { class: "ask", role: "alertdialog", "aria-modal": "true", "aria-labelledby": "ask-title" }, [
      h("p", { class: "ask-title", id: "ask-title" }, [spec.title]),
      ...(spec.text ? [h("p", { class: "ask-text" }, [spec.text])] : []),
      h("div", { class: "ask-buttons" }, buttons),
    ]);
    const shade = h("div", { class: "ask-shade" }, [dialog]);
    shade.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        answer(spec.cancel);
      }
      e.stopPropagation(); // the editor's hotkeys wait until this is answered
    });
    document.body.append(shade);
    const primary = spec.buttons.findIndex((b) => b.kind === "primary");
    /** @type {HTMLElement} */ (buttons[primary >= 0 ? primary : buttons.length - 1]).focus();
  });
}

/**
 * A Cancel / do-it question (`ask`): true when the do-it button was chosen. Escape cancels.
 * @param {string} title @param {string} text @param {string} label the do-it button's
 * @param {string} answer its `data-answer`
 * @returns {Promise<boolean>}
 */
export async function confirmed(title, text, label, answer) {
  const buttons = [{ label: "Cancel", value: "cancel" }, { label, value: answer, kind: /** @type {const} */ ("primary") }];
  return (await ask({ title, text, cancel: "cancel", buttons })) === answer;
}

/**
 * A sheet: a wider modal for reading and small tools (Help pages, Tools), with a title and
 * a Close button. Escape, Close or a click on the shade around it closes it; keys typed
 * in it never reach the editor's hotkeys.
 * @param {{title: string, id?: string, body: Node[], wide?: boolean, head?: Node[]}} spec `head`: more buttons before Close
 * @returns {{close: () => void, el: HTMLElement}}
 */
export function sheet(spec) {
  const close = () => shade.remove();
  const closeButton = h("button", { type: "button", class: "sheet-close", "aria-label": "Close" }, ["Close"]);
  closeButton.addEventListener("click", close);
  const el = h("div", { class: spec.wide ? "sheet wide" : "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "sheet-title", ...(spec.id ? { id: spec.id } : {}) }, [
    h("div", { class: "sheet-head" }, [h("h2", { class: "sheet-title", id: "sheet-title" }, [spec.title]), h("span", { class: "sheet-tools" }, [...(spec.head ?? []), closeButton])]),
    h("div", { class: "sheet-body" }, spec.body),
  ]);
  const shade = h("div", { class: "ask-shade" }, [el]);
  shade.addEventListener("pointerdown", (e) => {
    if (e.target === shade) close();
  });
  shade.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
    e.stopPropagation();
  });
  document.querySelector(".ask-shade .sheet")?.parentElement?.remove(); // one sheet at a time
  document.body.append(shade);
  /** @type {HTMLElement | null} */ (el.querySelector("input, select") ?? closeButton)?.focus();
  return { close, el };
}

/**
 * The Try button of a form's "try several values" row: runs the sweep, shows what it
 * refused in the form, and Enter in the values box presses it.
 * @param {string} id @param {HTMLInputElement} values
 * @param {() => {showError: (message: string | null) => void} | null} form the form it's in, once open
 * @param {() => Promise<string | null>} sweep
 */
export function tryButton(id, values, form, sweep) {
  const button = h("button", { type: "button", id }, ["Try"]);
  button.addEventListener("click", async () => {
    form()?.showError(null);
    const message = await sweep();
    if (message) form()?.showError(message);
  });
  values.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      button.click();
    }
  });
  return button;
}
