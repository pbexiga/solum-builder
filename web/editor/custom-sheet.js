/**
 * The custom switch editor (DOM, v22, 9c): its name, poles, throws, positions and look,
 * and a grid: per position its name and, per pole, the throw its common joins. The logic
 * is custom-switch.js's; Apply hands the result to `onApply`, which answers with an error
 * to show (the server's check) or null to close.
 */

import { h } from "../panels.js";
import { LIMITS, customProblem, joinChoices, resize } from "./custom-switch.js";
import { sheet } from "./form.js";

/**
 * @param {{ref: string, start: import("../schematic/symbols.js").CustomSwitch,
 *   onApply: (custom: import("../schematic/symbols.js").CustomSwitch) => Promise<string | null>}} spec
 */
export function openCustomSwitch(spec) {
  let custom = structuredClone(spec.start);
  const range = (/** @type {number} */ lo, /** @type {number} */ hi) => Array.from({ length: hi - lo + 1 }, (_, i) => String(lo + i));
  const picker = (/** @type {string} */ name, /** @type {string[]} */ values, /** @type {string} */ now) => {
    const s = /** @type {HTMLSelectElement} */ (h("select", { name, id: `custom-${name}` }));
    for (const v of values) s.append(new Option(v, v, false, v === now));
    return s;
  };
  const nameBox = /** @type {HTMLInputElement} */ (h("input", { type: "text", id: "custom-name", value: custom.name, maxlength: "24", autocomplete: "off" }));
  const poles = picker("poles", range(1, LIMITS.poles), String(custom.positions[0].joins.length));
  const throws = picker("throws", range(1, LIMITS.throws), String(custom.throws));
  const count = picker("positions", range(2, LIMITS.positions), String(custom.positions.length));
  const look = /** @type {HTMLSelectElement} */ (h("select", { name: "look", id: "custom-look" }));
  look.append(new Option("toggle (a column of contacts)", "toggle"), new Option("rotary (an arc, 3 throws or more)", "rotary"));
  const grid = h("table", { class: "custom-grid" });
  const error = h("p", { class: "error", role: "alert", hidden: "" });

  /** The grid again, from `custom`. */
  function draw() {
    look.value = custom.look ?? "toggle";
    look.disabled = custom.throws < 3;
    const n = custom.positions[0].joins.length;
    const head = h("tr", {}, [h("th", {}, ["Position"]), ...Array.from({ length: n }, (_, k) => h("th", {}, [n > 1 ? `Pole ${"ABCD"[k]}` : "Joins"]))]);
    const rows = custom.positions.map((p, i) => {
      const label = /** @type {HTMLInputElement} */ (h("input", { type: "text", value: p.name, maxlength: "24", "aria-label": `Position ${i + 1} name`, "data-position": String(i) }));
      label.addEventListener("input", () => { custom.positions[i].name = label.value; });
      const cells = p.joins.map((j, k) => {
        const s = /** @type {HTMLSelectElement} */ (h("select", { "aria-label": `Position ${i + 1}, pole ${"ABCD"[k]}`, "data-join": `${i}-${k}` }));
        for (const [v, text] of joinChoices(custom, k)) s.append(new Option(text, v, false, v === (j === null ? "" : String(j))));
        s.addEventListener("change", () => { custom.positions[i].joins[k] = s.value === "" ? null : Number(s.value); });
        return h("td", {}, [s]);
      });
      return h("tr", {}, [h("td", {}, [label]), ...cells]);
    });
    grid.replaceChildren(h("thead", {}, [head]), h("tbody", {}, rows));
  }

  const resized = () => {
    custom = resize(custom, { poles: Number(poles.value), throws: Number(throws.value), positions: Number(count.value) });
    draw();
  };
  for (const s of [poles, throws, count]) s.addEventListener("change", resized);
  look.addEventListener("change", () => { custom.look = /** @type {"toggle" | "rotary"} */ (look.value); draw(); });
  nameBox.addEventListener("input", () => { custom.name = nameBox.value; });

  const row = (/** @type {string} */ text, /** @type {HTMLElement} */ control) => h("div", { class: "form-row" }, [h("label", { for: control.id }, [text]), control]);
  const cancel = h("button", { type: "button" }, ["Cancel"]);
  const apply = h("button", { type: "button", class: "primary" }, ["Apply"]);
  const opened = sheet({
    title: `Custom switch · ${spec.ref}`,
    id: "custom-switch",
    body: [
      h("p", { class: "hint" }, ["Each position joins each pole's common to one throw, or leaves it open. The lugs are named as the schematic draws them."]),
      row("Name", nameBox), row("Poles", poles), row("Throws", throws), row("Positions", count), row("Drawn as", look),
      grid, error,
      h("div", { class: "popup-buttons" }, [cancel, apply]),
    ],
  });
  cancel.addEventListener("click", () => opened.close());
  apply.addEventListener("click", async () => {
    const message = customProblem(custom) ?? (await spec.onApply(custom));
    error.hidden = !message;
    error.textContent = message ?? "";
    if (!message) opened.close();
  });
  draw();
  nameBox.focus();
  return opened;
}
