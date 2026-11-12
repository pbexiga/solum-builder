/**
 * The inspector (DOM, D-056): a part's form, opened by a double-click, Enter or Edit part…
 * Its fields and what they change are `editor/fields.js`; this builds the form around
 * them: the "try several values" row, the value and rotation sliders (the root's, D-081),
 * a switch's or pot's poles and gangs, renames, a custom switch's contacts editor (9c),
 * and a targeted trimmer's reach and rotation (D-127).
 */

import { postJson } from "./api.js";
import { openCustomSwitch } from "./editor/custom-sheet.js";
import { customFrom } from "./editor/custom-switch.js";
import { chipRefs, groupRefs, movedTargets, renameChip, renamePart, setDrainTarget, setSwitchPoles, splitValues, updatePart } from "./editor/edit.js";
import { draftFrom, editFrom, inspectorFields, sweepField, sweepPrompt, targetNode, targetRotation } from "./editor/fields.js";
import { closeForm, openForm, tryButton } from "./editor/form.js";
import { capacitorSheet } from "./help.js";
import { renamesOf } from "./notes-logic.js";
import { h } from "./panels.js";
import { kindOf } from "./schematic/symbols.js";

/**
 * @typedef {import("./schematic/render.js").Selection} Selection
 * @typedef {{models: Record<string, string[]>, capKinds: any[], pickups: any[], jfets: any, bjts: any, chips: any, batteries: any[], inductors: any[]}} Library
 *   what the server said once at the start: the model lists and the guides' choices
 *
 * @typedef {object} InspectorApp what the inspector asks of the app root
 * @property {() => any} circuit
 * @property {() => any} view
 * @property {() => any} run the last run (its bias and voltages)
 * @property {() => Selection | null} selection
 * @property {() => Promise<void>} selecting the selection's views loading
 * @property {() => Library} library
 * @property {(ref: string | null) => any} partOf
 * @property {(selection: Selection | null) => Promise<void>} select
 * @property {() => void} stopPlacing
 * @property {(next: any, label: string) => Promise<string | null>} tryEdit an edit checked with the server first
 * @property {(ref: string, field: string, values: string[]) => Promise<string | null>} runSweep "try several values"
 * @property {(part: any) => {attach: (form: HTMLFormElement, shown: Promise<void>) => void, close: (submitted: boolean) => void} | null} sliders
 *   the part's value and rotation sliders, if its type has them
 * @property {(renamed: import("./notes-logic.js").Rename[]) => void} showRenames the notice for notes that mention an old name (9d4)
 * @property {(p: Promise<void>) => Promise<void>} report a sheet's opening, its failure shown
 */

/**
 * @param {HTMLElement} host where the form opens (the canvas)
 * @param {InspectorApp} app
 * @returns {{inspect: (ref: string, draft?: any) => void, showTargetRotation: () => void}}
 *   `showTargetRotation`: after each run, an open targeted trimmer's Rotation follows it
 */
export function inspector(host, app) {
  /** @type {string | null} the part whose form is open */
  let inspected = null;
  /** @type {{fields: import("./editor/fields.js").Field[]} | null} the inspector's form, while it's open */
  let inspectedForm = null;

  /**
   * A custom switch's contacts editor (9c), starting from `from` (the switch's type, or its
   * own contacts). Apply makes every pole custom with them, poles coming and going with
   * them, the position kept if it's still there, position names left to the editor's.
   * @param {any} part a pole @param {import("./schematic/symbols.js").SwitchKind} from
   */
  function editContacts(part, from) {
    const name = part.pole ? part.ref.slice(0, -1) : part.ref;
    openCustomSwitch({
      ref: name,
      start: customFrom(from),
      onApply: async (custom) => {
        const poles = custom.positions[0]?.joins.length ?? 1;
        const position = Math.min(part.position ?? 0, custom.positions.length - 1);
        const next = setSwitchPoles(app.circuit(), part.ref, poles, { kind: "custom", custom, position, names: null });
        const message = await app.tryEdit(next, `Edit ${name}`);
        if (!message) {
          closeForm();
          app.select({ kind: "part", id: poles > 1 ? `${name}A` : name });
        }
        return message;
      },
    });
  }

  /** @param {string} ref @param {any} [draft] the part as its form had it, built again for another model */
  function inspect(ref, draft = null) {
    const part = app.partOf(ref);
    if (!part) return;
    const lib = app.library();
    const shownPart = draft ?? part; // the fields as edited so far, when the Model changed
    app.stopPlacing();
    // a double-click's first click may still be loading the part's view: wait for it either way
    const shown = app.selection()?.kind !== "part" || app.selection().id !== ref ? app.select({ kind: "part", id: ref }) : app.selecting();
    const field = sweepField(part);
    const extra = [];
    /** @type {ReturnType<typeof openForm> | null} */
    let handle = null;
    if (field) {
      const prompt = /** @type {{label: string, placeholder: string}} */ (sweepPrompt(part, lib.models[part.type] ?? []));
      const values = /** @type {HTMLInputElement} */ (h("input", { type: "text", id: "sweep-values", placeholder: prompt.placeholder, autocomplete: "off", title: "Not this part's value (that's above): a list of values to compare side by side. Clear sweep puts things back." }));
      const button = tryButton("sweep-run", values, () => handle, () => app.runSweep(ref, field, splitValues(values.value)));
      extra.push(h("div", { class: "sweep-row" }, [h("label", { for: "sweep-values" }, [prompt.label]), values, button]));
    }
    const slide = app.sliders(part);
    inspected = part.ref;
    handle = openForm(host, {
      title: part.ref,
      subtitle: part.type,
      onClose: (submitted) => {
        inspected = null;
        inspectedForm = null;
        slide?.close(submitted);
      },
      onHelp: (page) => {
        if (page === "capacitors") app.report(capacitorSheet());
        if (page === "custom-switch") editContacts(part, kindOf(part));
      },
      fields: inspectorFields(shownPart, { circuit: app.circuit(), models: lib.models, capKinds: lib.capKinds, pickups: lib.pickups, bias: app.run()?.op?.bias,
        jfets: lib.jfets, bjts: lib.bjts, chips: lib.chips, batteries: lib.batteries, inductors: lib.inductors, view: app.view(), target: part.type === "trimmer" && app.view() ? targetNode(part.ref, app.view(), app.run()?.op?.voltages) : null }),
      extra,
      onSubmit: async (values) => {
        let change;
        try {
          change = editFrom(part, values, { pickups: lib.pickups, batteries: lib.batteries, inductors: lib.inductors, circuit: app.circuit(), zeners: lib.models.zeners });
        } catch (err) {
          return /** @type {Error} */ (err).message;
        }
        let next = updatePart(app.circuit(), part.ref, change.patch);
        // a chip's halves share their model and name (D-140)
        const others = (chipRefs(app.circuit(), part.ref) ?? []).filter((r) => r !== part.ref);
        if ("model" in change.patch) for (const other of others) next = updatePart(next, other, { model: change.patch.model });
        let renamedFrom = part.ref;
        if (part.type === "switch") { // every pole takes the type, position, label and position names; poles come and go with the type (D-143)
          const { kind, position, label, names } = /** @type {any} */ (change.patch);
          // a custom one keeps its contacts; another type drops them (null leaves the part)
          const custom = (kind ?? part.kind) === "custom" ? part.custom : null;
          const poles = kindOf({ kind: kind ?? part.kind, custom })?.poles ?? 1;
          next = setSwitchPoles(app.circuit(), part.ref, poles, { kind, position, label, names, custom });
          const name = (/** @type {string} */ ref) => (part.pole ? ref.replace(/[A-D]$/i, "") : ref);
          const first = (/** @type {string} */ stem) => (poles > 1 ? `${stem}A` : stem);
          renamedFrom = first(name(part.ref));
          change.ref = first(name(change.ref));
        }
        if (part.type === "pot") { // every gang takes the value, taper, rotation and label; Single or Dual makes or drops gang B (D-217)
          const { value, taper, rotation, label } = /** @type {any} */ (change.patch);
          const gangs = /** @type {any} */ (values).gangs === "2" ? 2 : 1;
          next = setSwitchPoles(app.circuit(), part.ref, gangs, { value, taper, rotation, label });
          const name = (/** @type {string} */ ref) => (part.gang ? ref.replace(/[AB]$/i, "") : ref);
          const first = (/** @type {string} */ stem) => (gangs > 1 ? `${stem}A` : stem);
          renamedFrom = first(name(part.ref));
          change.ref = first(name(change.ref));
        }
        /** @type {import("./notes-logic.js").Rename[]} */
        let renamed = [];
        if (change.ref !== renamedFrom) {
          const units = groupRefs(next, renamedFrom);
          next = units.length > 1 ? renameChip(next, renamedFrom, change.ref) : renamePart(next, renamedFrom, change.ref);
          const stem = change.ref.replace(/[a-h]$/i, ""); // as renameChip names the units
          renamed = renamesOf(units, units.length > 1 ? units.map((u) => `${stem}${u.slice(-1)}`) : [change.ref]);
        }
        if (change.drain) next = setDrainTarget(next, change.ref, change.drain.trimmer, change.drain.volts);
        if (JSON.stringify(next) === JSON.stringify(app.circuit())) return null; // as the slider left it
        const out = await targetsOutOfReach(next);
        if (out) return out;
        const message = await app.tryEdit(next, `Edit ${change.ref}`);
        if (!message && renamed.length) app.showRenames(renamed); // notes that mention the old name (9d4)
        // don't wait for the new part view: the form closes as soon as the edit is in
        if (!message && change.ref !== part.ref) app.select({ kind: "part", id: change.ref });
        return message;
      },
    });
    inspectedForm = handle;
    slide?.attach(handle.form, shown);
    // another model changes what the form asks (a germanium transistor's leakage, the
    // model's own values): build it again with what's typed so far (the user, 2026-10-28)
    // so does a switch's type: its positions and poles (D-143)
    const box = part.type === "switch" ? "kind" : "model";
    const modelBox = /** @type {HTMLSelectElement | null} */ (handle.form.querySelector(`select[name="${box}"]`));
    let picked = modelBox?.value ?? ""; // the type before Custom… was picked: its editor starts from it
    modelBox?.addEventListener("change", () => {
      if (part.type === "switch" && modelBox.value === "custom" && part.kind !== "custom") {
        const from = kindOf({ kind: picked });
        modelBox.value = picked; // the switch stays as it is until the editor's Apply
        if (from) editContacts(part, from);
        return;
      }
      picked = modelBox.value;
      const values = Object.fromEntries([...new FormData(handle.form).entries()].map(([k, v]) => [k, String(v)]));
      inspect(ref, draftFrom(part, values, { pickups: lib.pickups, batteries: lib.batteries, inductors: lib.inductors }));
      /** @type {HTMLElement | null} */ (document.querySelector(`.popup select[name="${box}"]`))?.focus();
    });
    if (part.type === "trimmer" && part.bias_target) void showReach(part.ref);
    if (part.type === "trimmer") addedTargetReach(handle.form, part.ref);
  }

  /**
   * Add target pressed (again, after Remove target; round 3): how far the trimmer would move
   * that node, under Target, as for a target it has. @param {HTMLFormElement} form @param {string} ref
   */
  function addedTargetReach(form, ref) {
    const node = /** @type {HTMLInputElement | null} */ (form.querySelector("#field-bias_node"));
    if (!node) return;
    const box = /** @type {HTMLInputElement | null} */ (form.querySelector("#field-bias_volts"));
    const reach = () => {
      if (box && !box.value) { // opened before the run came back: its voltage now
        const now = targetNode(ref, app.view(), app.run()?.op?.voltages)?.volts;
        if (now !== undefined && now !== null) {
          box.value = now.toFixed(2);
          box.dispatchEvent(new Event("input")); // Rotation locks
        }
      }
      void showReach(ref, updatePart(app.circuit(), ref, { bias_target: { node: node.value, volts: Number(box?.value) || 0 } }));
    };
    // Add target shows the node's row and fills it (Remove empties it, hidden)
    node.addEventListener("input", () => { if (node.value && !node.closest(".form-row")?.hasAttribute("hidden")) reach(); });
  }

  /**
   * A new or changed bias target the trimmer can't reach, refused in words (D-127): "With
   * RT1 (25k), Q1.D can go from 2.10 V to 8.70 V. …"; null when every one is within reach.
   * @param {any} next the circuit as the form would leave it @returns {Promise<string | null>}
   */
  async function targetsOutOfReach(next) {
    for (const ref of movedTargets(app.circuit(), next)) {
      try {
        const reach = await postJson("api/trimmer/reach", { circuit: next, ref });
        if (!reach.holds) return `${reach.text} Pick a target in that range, or change ${ref}'s value or the resistor in series with it.`;
      } catch (err) {
        return /** @type {Error} */ (err).message;
      }
    }
    return null;
  }

  /**
   * How far a targeted trimmer reaches, under its Target box in its open form.
   * @param {string} ref @param {any} [circuit] with its target (one being added, round 3)
   */
  async function showReach(ref, circuit = app.circuit()) {
    let reach;
    try {
      reach = await postJson("api/trimmer/reach", { circuit, ref });
    } catch {
      return; // the hint stays general; Apply still checks
    }
    const hint = inspected === ref ? document.querySelector("#canvas-body #field-bias_volts")?.closest(".form-row")?.querySelector(".hint-text") : null;
    if (hint) hint.textContent = `${reach.text} Checked on Apply.`;
  }

  /**
   * A targeted trimmer's Rotation in its open form follows each run (D-127): the turn that
   * reaches its target as it is now, so it needn't be looked for elsewhere. Only while the
   * box is read-only (its target fields filled, as stored or as typed).
   */
  function showTargetRotation() {
    const part = app.partOf(inspected);
    const box = /** @type {HTMLInputElement | null} */ (document.querySelector("#canvas-body #field-rotation"));
    if (!part?.bias_target || !box?.readOnly) return;
    const f = targetRotation(part, app.run()?.op?.bias?.[part.ref]);
    box.value = box.defaultValue = f.value; // a Remove then Add target in the form comes back to it
    const hint = box.closest(".form-row")?.querySelector(".hint-text");
    if (hint) hint.textContent = f.lockedHint ?? "";
    const field = inspectedForm?.fields.find((x) => x.name === "rotation");
    if (field) field.about = f.about; // its ⓘ says the new turn (D-200)
  }

  return { inspect, showTargetRotation };
}
