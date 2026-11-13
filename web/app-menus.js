/**
 * What is in each menu (DOM, D-057, D-095): the header's File, Edit, Blocks, View, Tools
 * and Help lists, and the right-click menu built from the same lists, with its Add note…
 * form (9d4). The lists are here; what each item does is the app root's (`app`). The
 * drop-downs themselves are `menus.js`.
 */

import { closeForm, openForm } from "./editor/form.js";
import { exportSheet } from "./export.js";
import { aboutSheet, capacitorSheet, hotkeysSheet, manualSheet, resistorGuideSheet } from "./help.js";
import { menu, openMenu } from "./menus.js";
import { isNamedNet, nameNet, setNetNote, setPartNote } from "./notes-logic.js";
import { addModelSheet, converterSheet, partsSheet, resistorSheet } from "./tools.js";

/**
 * @typedef {import("./menus.js").MenuItem} MenuItem
 * @typedef {import("./app.js").Source} Source
 * @typedef {import("./schematic/render.js").Items} Items
 * @typedef {import("./schematic/render.js").Selection} Selection
 *
 * @typedef {object} MenuApp what the menus ask of the app root: what is open and selected, and each command
 * @property {() => Source | null} source
 * @property {() => import("./app.js").FileInfo | null} file
 * @property {() => any} circuit
 * @property {() => any} view
 * @property {() => Selection | null} selection
 * @property {() => boolean} dirty
 * @property {() => boolean} isBlock
 * @property {() => any[]} starters
 * @property {() => {dc: boolean, impedance: boolean, capTypes: boolean, marks: boolean}} shown View's switches
 * @property {() => {undo: string | null, redo: string | null}} undoLabels what Undo and Redo would do
 * @property {() => Items | null} selectedItems
 * @property {() => boolean} canPaste
 * @property {() => boolean} deletable
 * @property {(ref: string | null) => any} partOf
 * @property {ReturnType<typeof import("./file-dialogs.js").fileDialogs>} files
 * @property {ReturnType<typeof import("./block-dialogs.js").blockDialogs>} blocks
 * @property {(source: Source) => Promise<void>} leaveTo
 * @property {(selection: Selection | null) => Promise<void>} select
 * @property {(ref: string) => void} inspect a part's form
 * @property {(next: any, label: string) => Promise<string | null>} tryEdit
 * @property {(where: any, focus?: boolean) => void} showNote the Notes pane at a part's or net's note
 * @property {(p: Promise<void>) => Promise<void>} report a sheet's opening, its failure shown
 * @property {() => Promise<void>} refreshModels the model lists again, after one is added
 * @property {() => void} undo
 * @property {() => void} redo
 * @property {() => void} openHistory
 * @property {() => void} rotate
 * @property {() => void} deleteSelection
 * @property {() => void} copy
 * @property {() => void} paste
 * @property {() => void} selectAll
 * @property {() => void} findPart
 * @property {() => void} toggleDc
 * @property {() => void} toggleImpedance
 * @property {() => void} toggleCapTypes
 * @property {() => void} toggleMarks
 * @property {() => void} resetPanes
 * @property {() => void} openSettings File → Settings… (D-310)
 */

/**
 * @param {HTMLElement} host where the Add note form opens (the canvas)
 * @param {import("./schematic/render.js").Schematic} schematic the sheet (View's zoom items)
 * @param {MenuApp} app
 * @returns {{build: () => void, contextMenu: (x: number, y: number, item: Items | null) => void}}
 *   `build`: the header menus onto their buttons (each rebuilt when opened)
 */
export function appMenus(host, schematic, app) {
  /** The starter circuits, ticked when one is open. @returns {import("./menus.js").MenuItem[]} */
  function starterItems() {
    return app.starters().map((s) => ({
      label: s.name,
      id: `starter-${s.id}`,
      checked: app.source()?.kind === "starter" && app.source().id === s.id,
      run: () => app.leaveTo({ kind: "starter", id: s.id }),
    }));
  }

  /** File menu items. @returns {MenuItem[]} */
  function fileItems() {
    return [
      { label: "New sheet", id: "menu-new", run: app.files.newSheet },
      { label: "New from starter", id: "menu-starters", items: starterItems() },
      { label: "Open…", id: "menu-open", run: app.files.openDialog },
      "-",
      { label: "Save", id: "menu-save", hint: "Ctrl+S", run: () => app.files.save() },
      { label: "Save as…", id: "menu-save-as", run: () => app.files.saveAs() },
      { label: "Properties…", id: "menu-properties", hint: "name, tags, file, version", run: app.files.properties },
      { label: "New major version…", id: "menu-new-major", disabled: !app.files.ownFile() || !app.file()?.current, run: app.files.newMajor },
      "-",
      { label: "Export…", id: "menu-export", hint: "parts list and build package, from the last save", run: () => exportSheet({ source: app.source(), dirty: app.dirty(), dismissed: app.circuit()?.dismissed, onPick: (ref) => app.select({ kind: "part", id: ref }) }) },
      "-",
      { label: "Settings…", id: "menu-settings", hint: "folders, cache, theme", run: app.openSettings },
      "-",
      { label: app.isBlock() ? "Delete this block…" : "Delete this circuit…", id: "menu-delete-circuit", disabled: !app.files.ownFile(), run: app.files.deleteCircuit },
    ];
  }

  /** Edit menu items. @returns {MenuItem[]} */
  function editItems() {
    const sel = app.selection();
    const { undo: u, redo: r } = app.undoLabels();
    return [
      { label: u ? `Undo ${u}` : "Undo", id: "menu-undo", hint: "Ctrl+Z", disabled: !u, run: app.undo },
      { label: r ? `Redo ${r}` : "Redo", id: "menu-redo", hint: "Ctrl+Shift+Z", disabled: !r, run: app.redo },
      { label: "History…", id: "menu-history", hint: "every step, to go back to one", run: app.openHistory },
      "-",
      { label: "Edit part…", id: "menu-inspect", hint: "Enter", disabled: sel?.kind !== "part", run: () => app.inspect(/** @type {string} */ (sel?.id)) },
      { label: "Rotate", id: "menu-rotate", hint: "Space", disabled: sel?.kind !== "part", run: app.rotate },
      { label: "Delete", id: "menu-delete", hint: "Del", disabled: !app.deletable(), run: app.deleteSelection },
      "-",
      { label: "Copy", id: "menu-copy", hint: "Ctrl+C", disabled: !app.selectedItems(), run: app.copy },
      { label: "Paste", id: "menu-paste", hint: "Ctrl+V", disabled: !app.canPaste(), run: app.paste },
      { label: "Select all", id: "menu-select-all", hint: "Ctrl+A; Shift+drag a box, Ctrl+click to add or remove one", run: app.selectAll },
      { label: "Find part…", id: "menu-find", hint: "Ctrl+F", disabled: !app.circuit()?.parts.length, run: app.findPart },
    ];
  }

  /** Blocks menu items. @returns {MenuItem[]} */
  function blockItems() {
    return [
      { label: "Insert or manage blocks…", id: "menu-insert-block", hint: "B", run: app.blocks.blocksDialog },
      { label: app.selectedItems() ? "Save selection as block…" : "Save sheet as block…", id: "menu-save-block", hint: "Shift+drag to select", run: app.blocks.saveAsBlock },
    ];
  }

  /** View menu items. @returns {MenuItem[]} */
  function viewItems() {
    return [
      { label: "Zoom in", id: "menu-zoom-in", run: () => schematic.zoomBy(1.25) },
      { label: "Zoom out", id: "menu-zoom-out", run: () => schematic.zoomBy(0.8) },
      { label: "Fit circuit", id: "menu-fit", run: () => schematic.fit() },
      "-",
      { label: "DC voltages on schematic", id: "menu-dc", checked: app.shown().dc, run: app.toggleDc },
      { label: "Impedance in and out", id: "menu-impedance", checked: app.shown().impedance, hint: "at 1 kHz", run: app.toggleImpedance },
      { label: "Capacitor types", id: "menu-cap-types", checked: app.shown().capTypes, hint: "100n film", run: app.toggleCapTypes },
      { label: "Problem marks", id: "menu-marks", checked: app.shown().marks, hint: "each problem on the sheet", run: app.toggleMarks },
      "-",
      { label: "Reset pane order", id: "menu-reset-panes", hint: "every pane open, in the column", run: app.resetPanes },
    ];
  }

  /** Tools menu items. @returns {MenuItem[]} */
  function toolsItems() {
    return [
      { label: "Unit converter…", id: "menu-converter", hint: "pF, nF, µF; cap codes", run: () => app.report(converterSheet()) },
      { label: "Resistor colour code…", id: "menu-resistor", hint: "bands ↔ value, E-series", run: () => app.report(resistorSheet()) },
      "-",
      { label: "Parts and datasheets…", id: "menu-parts", hint: "every model, its sheet and caveats", run: () => app.report(partsSheet()) },
      { label: "Add a model…", id: "menu-add-model", hint: "from a maker's SPICE file", run: () => app.report(addModelSheet(app.refreshModels)) },
    ];
  }

  /** Help menu items. @returns {MenuItem[]} */
  function helpItems() {
    return [
      { label: "Documentation…", id: "menu-documentation", hint: "the guide, with search", run: () => manualSheet() },
      { label: "Formulas…", id: "menu-formulas", hint: "the sums, with pedal examples", run: () => manualSheet("formulas") },
      { label: "Hot keys…", id: "menu-hotkeys", hint: "every keyboard and mouse shortcut", run: hotkeysSheet },
      "-",
      { label: "Choosing capacitors…", id: "menu-capacitors", run: () => app.report(capacitorSheet()) },
      { label: "Resistor colour code and values…", id: "menu-resistor-guide", run: () => app.report(resistorGuideSheet()) },
      "-",
      { label: "About Solum Builder…", id: "menu-about", run: () => app.report(aboutSheet()) },
    ];
  }

  /** The header menus, by button; the right-click menu offers the same lists (D-095). */
  const MENUS = /** @type {Array<[string, string, () => MenuItem[]]>} */ ([
    ["file-menu", "File", fileItems], ["edit-menu", "Edit", editItems], ["blocks-menu", "Blocks", blockItems],
    ["view-menu", "View", viewItems], ["tools-menu", "Tools", toolsItems], ["help-menu", "Help", helpItems],
  ]);

  /** The header menus; each is rebuilt when opened so it shows the current state. */
  function build() {
    for (const [id, , items] of MENUS) menu(/** @type {HTMLButtonElement} */ (document.getElementById(id)), items);
  }

  /**
   * The right-click menu (D-095): what can be done to the thing clicked, Paste, then every
   * header menu as a submenu, built from the same item lists (blocks: Blocks ▸ Insert or
   * manage blocks…). Paste follows the pointer until a click drops it, as Ctrl+V does.
   * @param {number} x @param {number} y where the menu opens (window pixels)
   * @param {{parts?: string[], wires?: number[], labels?: number[], texts?: number[]} | null} item what was under the pointer
   */
  function contextMenu(x, y, item) {
    closeForm();
    const ref = item?.parts?.[0];
    /** @type {MenuItem[]} */
    const here = [];
    if (ref) {
      here.push(
        { label: `Edit ${ref}…`, id: "ctx-inspect", hint: "Enter", run: () => app.inspect(ref) },
        { label: "Rotate", id: "ctx-rotate", hint: "Space", run: app.rotate },
      );
    }
    const noteOn = noteTarget(item);
    if (noteOn) {
      const has = noteOn.kind === "part" ? Boolean(app.partOf(noteOn.id)?.note) : Boolean(noteOn.named && app.circuit().net_notes?.[noteOn.id]);
      here.push({ label: has ? "Edit note\u2026" : "Add note\u2026", id: "ctx-note", run: () => (has ? app.showNote(noteOn.kind === "part" ? { kind: "part", ref: noteOn.id } : { kind: "net", net: noteOn.id }) : askNote(noteOn, schematic.toSchematic(x, y))) });
    }
    if (item) {
      here.push({ label: "Delete", id: "ctx-delete", hint: "Del", disabled: !app.deletable(), run: app.deleteSelection });
    }
    if (app.selectedItems()) here.push({ label: "Copy", id: "ctx-copy", hint: "Ctrl+C", run: app.copy });
    if (app.canPaste()) here.push({ label: "Paste", id: "ctx-paste", hint: "Ctrl+V", run: app.paste });
    openMenu(x, y, [
      ...here,
      ...(here.length ? /** @type {MenuItem[]} */ (["-"]) : []),
      ...MENUS.map(([id, name, items]) => /** @type {MenuItem} */ ({ label: name, id: `ctx-${id}`, items: items() })),
    ]);
  }

  /**
   * What a right-click's note goes on (9d4): the part, else the net of the label or wire.
   * `named`: whether a label or supply names that net (an unnamed one is named first).
   * @param {import("./schematic/render.js").Items | null | undefined} item
   * @returns {{kind: "part", id: string} | {kind: "net", id: string, named: boolean, wire?: number} | null}
   */
  function noteTarget(item) {
    if (!item) return null;
    if (item.parts?.[0]) return { kind: "part", id: item.parts[0] };
    const label = app.circuit().labels?.[item.labels?.[0] ?? -1];
    if (label) return { kind: "net", id: label.net, named: true };
    const wire = item.wires?.[0];
    const net = wire === undefined ? null : app.view()?.wires?.[wire]?.net;
    if (!net) return null; // a loose wire: no net to note
    return { kind: "net", id: net, named: isNamedNet(app.circuit(), net), wire };
  }

  /**
   * Add a note to a part or net (right-click → Add note…). An unnamed net takes a name in
   * the same form (a label where the wire was clicked): one edit for both.
   * @param {NonNullable<ReturnType<typeof noteTarget>>} on @param {number[]} at
   */
  function askNote(on, at) {
    const unnamed = on.kind === "net" && !on.named;
    openForm(host, {
      title: on.kind === "part" ? `Note on ${on.id}` : unnamed ? "Note on this net" : `Note on net ${on.id}`,
      subtitle: unnamed ? "it needs a name first" : "",
      fields: [
        ...(unnamed ? [{ name: "net", label: "Net name", kind: "text", value: "", hint: "A label with this name goes where you clicked. Notes go on named nets, so the note keeps its place as the drawing changes." }] : []),
        { name: "note", label: "Note", kind: "textarea", value: "", hint: "Shown in the Notes pane and in Probe. Ctrl+Enter applies." },
      ],
      submit: "Add note",
      onSubmit: async (values) => {
        const text = values.note.trim();
        if (!text) return "Write the note first.";
        let next = app.circuit();
        let net = on.id;
        if (unnamed) {
          net = values.net.trim();
          try {
            next = nameNet(next, /** @type {number} */ (on.kind === "net" ? on.wire : -1), at, net);
          } catch (err) {
            return /** @type {Error} */ (err).message;
          }
        }
        next = on.kind === "part" ? setPartNote(next, on.id, text) : setNetNote(next, net, text);
        const message = await app.tryEdit(next, unnamed ? `Name net ${net}, add its note` : `Add note on ${on.kind === "part" ? on.id : net}`);
        if (!message) app.showNote(on.kind === "part" ? { kind: "part", ref: on.id } : { kind: "net", net }, false);
        return message;
      },
    });
  }

  return { build, contextMenu };
}
