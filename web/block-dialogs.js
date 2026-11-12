/**
 * The block dialogs (DOM, D-072 to D-075): Blocks (insert a block, edit or delete one of
 * yours) and Save as block, with its ports marked by clicks on the sheet. Pasting itself
 * is `editor/blocks.js`; placing the block on the sheet is the app root's.
 */

import { deleteJson, getJson, postJson, putJson } from "./api.js";
import { allItems, blockSections, extract, markPort, withoutEnds } from "./editor/blocks.js";
import { ask, closeForm, confirmed, openForm } from "./editor/form.js";
import { entryTag, listControls, listView } from "./file-dialogs.js";
import { h } from "./panels.js";
import { debounce } from "./state.js";

/**
 * @typedef {import("./app.js").Source} Source
 *
 * @typedef {object} BlockApp what the block dialogs ask of the app root
 * @property {() => Source | null} source what is open
 * @property {() => any} circuit
 * @property {() => any} view the open circuit's view (its nets)
 * @property {() => import("./schematic/render.js").Items | null} selectedItems the selection as items, or null
 * @property {(block: any, view: any, name: string, inserted?: boolean) => void} startPlacingBlock the block's ghost follows the pointer
 * @property {(source: Source) => void} go open `source` (leaving is already fine)
 * @property {(source: Source) => Promise<void>} leaveTo open `source` once leaving is fine
 * @property {(message: string | null) => void} showError
 * @property {(text: string) => void} hint the line under the canvas
 */

/**
 * @param {HTMLElement} host where the dialogs open (the canvas)
 * @param {BlockApp} app
 */
export function blockDialogs(host, app) {
  /** @type {{rows: Array<{net: string, name: string}>, draw: () => void} | null} ports being marked (Save as block is open) */
  let marking = null;

  /**
   * The Blocks dialog: insert a block, and manage them (D-074, D-075). My blocks and Core
   * blocks are two sections, each switched on or off (never both off), sorted by name.
   * Each row: click the name to insert it; Edit opens it (a core block or a final version
   * opens as an unsaved copy, saved to My blocks only if you save it); Delete (mine only).
   */
  function blocksDialog() {
    const view = listView("solum.blocks.view");
    const list = h("div", { class: "block-list", role: "listbox", "aria-label": "Blocks" });
    /** @type {any[]} */
    let entries = [];
    const draw = () => {
      list.replaceChildren(
        ...blockSections(entries, view.show, view.order, view.current).flatMap(({ layer, title, rows }) => [
          h("h3", { class: "block-section" }, [title]),
          ...rows.map((b) => blockRow(b, refill)),
          ...(rows.length ? [] : [h("p", { class: "empty" }, [search.value ? "No blocks match." : layer === "user" ? "None yet. Select parts, then Blocks \u2192 Save selection as block." : "No core blocks."])]),
        ]),
      );
    };
    const refill = async () => {
      entries = await getJson(`api/blocks?q=${encodeURIComponent(search.value)}`);
      draw();
    };
    const toggles = /** @type {Array<["user" | "core", string]>} */ ([["core", "Core"], ["user", "My blocks"]]).map(([layer, text]) => {
      const b = h("button", { type: "button", "aria-pressed": String(view.show[layer]), "data-block-show": layer }, [text]);
      b.addEventListener("click", () => {
        const other = layer === "user" ? "core" : "user";
        if (view.show[layer] && !view.show[other]) return; // one always stays on
        view.show[layer] = !view.show[layer];
        b.setAttribute("aria-pressed", String(view.show[layer]));
        view.remember();
        draw();
      });
      return b;
    });
    const bar = h("div", { class: "block-bar" }, [h("span", { class: "segmented", role: "group", "aria-label": "Show" }, toggles), ...listControls(view, draw)]);
    const handle = openForm(host, {
      title: "Blocks",
      subtitle: "click a name, then click the sheet (or a wire to splice it in)",
      fields: [{ name: "q", label: "Search", kind: "text", value: "" }],
      submit: "Insert first",
      extra: [bar, list],
      onSubmit: async () => {
        /** @type {HTMLButtonElement | null} */ (list.querySelector("button.insert:not(:disabled)"))?.click();
        return list.querySelector("button.insert:not(:disabled)") ? null : "No block to insert.";
      },
    });
    const search = /** @type {HTMLInputElement} */ (handle.form.querySelector("#field-q"));
    search.addEventListener("input", debounce(() => refill().catch((err) => handle.showError(err.message)), 200));
    refill().catch((err) => handle.showError(err.message));
  }

  /**
   * One row of the Blocks dialog. @param {any} b a block entry from /api/blocks
   * @param {() => Promise<void>} refill redraw the list after a change
   */
  function blockRow(b, refill) {
    const mine = b.layer === "user";
    const fixed = !mine || b.final; // core or final: Edit opens an unsaved copy
    const button = (/** @type {string} */ text, /** @type {Record<string, string>} */ attrs, /** @type {() => Promise<void> | void} */ run) => {
      const el = h("button", { type: "button", ...attrs }, [text]);
      el.addEventListener("click", () => Promise.resolve(run()).catch((err) => app.showError(err.message)));
      return el;
    };
    const insert = /** @type {HTMLButtonElement} */ (
      button(b.problem ? `${b.id} (can't open)` : b.name, { class: "insert", role: "option", "data-block": b.id, "data-layer": b.layer, title: b.problem ?? b.description }, () => {
        closeForm();
        return insertBlock(b.id, b.layer);
      })
    );
    insert.disabled = Boolean(b.problem);
    const tag = entryTag(b);
    const edit = button("Edit", { "data-edit-block": b.id, "data-layer": b.layer, title: fixed ? "Open a copy to change; Save puts it in My blocks (this one stays as it is)" : "Open it to change it, then Save" }, async () => {
      closeForm();
      await app.leaveTo(fixed ? { kind: "copy", id: `${b.layer}:${b.id}` } : { kind: "block", id: b.id });
    });
    const del = mine
      ? [
          button("Delete", { "data-delete-block": b.id, class: "danger", title: "Delete this block from My blocks" }, async () => {
            const sure = await confirmed(`Delete your block \u201c${b.name}\u201d (${b.version})?`, "This version's file is removed and this can't be undone. Other versions stay, and circuits you pasted it into keep their parts.", "Delete", "delete");
            if (!sure) return;
            await deleteJson(`api/blocks/${encodeURIComponent(b.id)}`);
            if (app.source()?.kind === "block" && app.circuit().id === b.id) app.go({ kind: "new", id: "" });
            await refill();
          }),
        ]
      : [];
    return h("div", { class: "block-row" }, [insert, tag, ...(b.problem ? [] : [edit]), ...del]);
  }

  /** Fetch a block and start placing it. @param {string} id @param {string} layer */
  async function insertBlock(id, layer) {
    const view = await getJson(`api/blocks/${encodeURIComponent(id)}?layer=${layer}`);
    app.startPlacingBlock(view.circuit, view, view.circuit.name, true);
  }

  /**
   * Save as block: the selection (or the whole sheet when nothing is selected) goes to My
   * Blocks. While the dialog is open, clicking a wire or pin marks a port there.
   */
  function saveAsBlock() {
    const items = withoutEnds(app.circuit(), app.selectedItems() ?? allItems(app.circuit())); // no guitar or amp in a block (D-146)
    const block = extract(app.circuit(), app.view(), items);
    const whole = !app.selectedItems();
    const ports = h("div", { class: "port-list", id: "port-list" });
    /** @type {Array<{net: string, name: string}>} */
    const rows = [];
    const draw = () => {
      ports.replaceChildren(
        ...rows.map((row, i) => {
          const input = /** @type {HTMLInputElement} */ (h("input", { type: "text", name: `port-${i}`, value: row.name, "aria-label": `Port on ${row.net}`, autocomplete: "off" }));
          input.addEventListener("input", () => (row.name = input.value));
          const remove = h("button", { type: "button", title: "Not a port" }, ["×"]);
          remove.addEventListener("click", () => {
            rows.splice(i, 1);
            draw();
          });
          return h("div", { class: "port-row" }, [input, h("span", { class: "net" }, [`on ${row.net}`]), remove]);
        }),
      );
      if (!rows.length) ports.append(h("p", { class: "hint-text" }, ["Click a wire or pin on the sheet for each port (in, out, vref…). Supplies and ground connect by themselves."]));
    };
    draw();
    marking = { rows, draw };
    const handle = openForm(host, {
      title: "Save as block",
      subtitle: whole ? "the whole sheet, in My Blocks" : `${items.parts.length} parts, in My Blocks`,
      fields: [
        { name: "name", label: "Name", kind: "text", value: whole ? app.circuit().name : "" },
        { name: "description", label: "Description", kind: "text", value: "" },
      ],
      submit: "Save block",
      extra: [h("p", { class: "hint-text" }, ["Ports:"]), ports],
      onSubmit: async (values) => {
        let made = { ...block, description: values.description.trim() };
        try {
          for (const row of rows) made = markPort(made, app.view(), row.net, row.name);
          const name = values.name.trim();
          // one of My blocks has that name already: replace it (asked first), or pick another name
          const mine = /** @type {any[]} */ (await getJson(`api/blocks?q=${encodeURIComponent(name)}`));
          const same = mine.find((b) => b.layer === "user" && b.name.toLowerCase() === name.toLowerCase());
          if (same) {
            const sure = await ask({
              title: `You already have a block called \u201c${same.name}\u201d. Replace it?`,
              text: same.final ? "It's a final version, so it can't be replaced. Pick another name." : "Your block is written over with this one (its version counts on).",
              cancel: "cancel",
              buttons: same.final ? [{ label: "OK", value: "cancel", kind: "primary" }] : [{ label: "Cancel", value: "cancel" }, { label: "Replace", value: "replace", kind: "primary" }],
            });
            if (sure !== "replace") return "Pick another name, or replace your block.";
          }
          const saved = same
            ? await putJson(`api/blocks/${encodeURIComponent(same.id)}`, { circuit: { ...made, id: same.id, name: same.name } })
            : (await postJson("api/blocks", { circuit: made, name })).circuit;
          marking = null;
          app.hint(`${same ? "Replaced" : "Saved"} ${saved.name} in My blocks (${same ? saved.version : "v1.0"}). Blocks \u2192 Insert or manage blocks\u2026 to use it.`);
          return null;
        } catch (err) {
          return /** @type {Error} */ (err).message;
        }
      },
    });
    // the form closes by Cancel, Escape or saving: stop marking then
    new MutationObserver((_m, obs) => {
      if (!handle.form.isConnected) {
        marking = null;
        obs.disconnect();
      }
    }).observe(host, { childList: true });
  }

  /** A click on the sheet while saving a block: a port on that net. @param {string} net */
  function addPortRow(net) {
    const m = marking;
    if (!net || !m || m.rows.some((r) => r.net === net)) return;
    const names = m.rows.map((r) => r.name);
    const name = !names.includes("in") ? "in" : !names.includes("out") ? "out" : net.includes(".") ? `port${m.rows.length + 1}` : net;
    m.rows.push({ net, name });
    m.draw();
  }

  return { blocksDialog, saveAsBlock, addPortRow, marking: () => Boolean(marking) };
}
