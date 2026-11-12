/**
 * Power in the header (DOM, D-093, D-145): the supply menu (presets, the circuit's own,
 * Custom…), the chip saying who powers the pedal (the DC jack or the battery), the current
 * drawn at the last run, and the Custom… dialog (the supply's type and voltages, and
 * "compare supply voltages" on one rail, D-068).
 */

import { powerChoices, powerText, setPower, setRails, splitValues } from "./editor/edit.js";
import { openForm, tryButton } from "./editor/form.js";
import { h } from "./panels.js";
import { COMPARE_MAX } from "./series.js";

/**
 * @typedef {object} PowerApp what Power asks of the app root
 * @property {() => any} circuit
 * @property {() => any} view its `power` (who powers the pedal) and `battery_wiring`
 * @property {() => Record<string, number>} controls where the knobs and switches are (the DC jack's plug)
 * @property {() => any} run the last run (its `op.supply`: the current each supply delivers)
 * @property {() => boolean} stale the last run is of an older circuit
 * @property {(next: any, label: string) => unknown} edit apply an edit
 * @property {(next: any, label: string) => Promise<string | null>} tryEdit an edit checked with the server first
 * @property {(ref: string, field: string, values: string[]) => Promise<string | null>} runSweep "try several values"
 * @property {() => void} showSupplyTiles the palette's V+ and V- tiles again
 * @property {(message: string | null) => void} showError
 */

/**
 * @param {{select: HTMLSelectElement, chip: HTMLElement, draw: HTMLElement, host: HTMLElement}} els
 *   the menu, the chip, the current drawn, and where the Custom… dialog opens (the canvas)
 * @param {PowerApp} app
 * @returns {{show: () => void, showDraw: () => void}} `show`: all of it again, for the open
 *   circuit; `showDraw`: only the current drawn, after a run
 */
export function powerMenu(els, app) {
  const { select } = els;

  /** The header's Power menu (D-093, after PedalSpice): presets (9, 12, 18 V, ±9, ±12,
   * ±15 V), the circuit's own supply if it's none of them, and Custom… (type and voltages). */
  function show() {
    const rails = app.circuit().power?.rails ?? {};
    const choices = powerChoices(app.circuit());
    const current = Object.keys(rails).length ? powerText(rails) : null;
    select.replaceChildren(
      ...(current ? [] : [new Option("no supply", "", false, true)]),
      ...choices.map((c) => new Option(c.text, c.key, false, c.text === current)),
      new Option("Custom…", "custom"),
    );
    select.title = "The supply plugged into the pedal: ideal and perfectly clean. 18 V or −9 V made inside the pedal comes from a charge pump block (Blocks), on its own net.";
    const chip = powerChip();
    const el = els.chip;
    el.hidden = !chip;
    el.textContent = chip?.text ?? "";
    el.classList.toggle("battery", Boolean(chip?.battery));
    // with no DC jack drawn there's no plug to put in: draw one (9c)
    const jackless = app.view()?.battery_wiring === "alone";
    el.title = chip?.battery
      ? `The battery powers the pedal: set its voltage on the battery part${jackless ? ". To use a supply, draw a DC jack and wire the battery's + to its battery lug." : ", or plug the DC jack in (Knobs → Power)."}`
      : "The DC jack powers the pedal, at the voltage picked here.";
    select.disabled = Boolean(chip?.battery);
    if (chip?.battery) select.title = `The battery powers the pedal, so this supply isn't used. ${jackless ? "Draw a DC jack to use it." : "Plug the DC jack in (Knobs → Power) to use it."}`;
    app.showSupplyTiles();
    showDraw();
  }

  /**
   * The Power chip (D-145): who powers the pedal, from the view's `power`; with a battery
   * and a DC jack, the entry for where the jack's Power switch is now (0 plugged in).
   * @returns {{text: string, battery: boolean} | null}
   */
  function powerChip() {
    const power = app.view()?.power;
    if (!power?.control) return power ?? null;
    return power.positions[app.controls()[power.control] ?? 0] ?? power.positions[0];
  }

  /** The current each supply delivers at the last run, next to the Power menu ("23.4 mA"). */
  function showDraw() {
    const el = els.draw;
    const supply = app.run()?.op?.supply ?? {};
    const rails = Object.entries(supply);
    el.hidden = !rails.length;
    el.textContent = rails.length === 1 ? rails[0][1].text : rails.map(([n, d]) => `${n.replace("-", "\u2212")} ${d.text}`).join(" · ");
    el.title = rails.length
      ? `Current drawn from the supply at the last run: ${rails.map(([n, d]) => `${n} ${d.text}`).join(", ")}. Pick an adapter (or supply output) rated above it; a charge pump draws about twice what it delivers. An estimate: op-amp models differ in how well they model their own current.`
      : "";
    el.classList.toggle("stale", app.stale());
  }

  /**
   * Power → Custom… (D-093): the supply's type (+, − or ±) and a voltage for each side,
   * and "compare supply voltages" on one rail without building a supply (D-068).
   */
  function powerDialog() {
    const c = app.circuit();
    const rails = c.power?.rails ?? {};
    const names = Object.keys(rails);
    const type = "V+" in rails && "V-" in rails ? "both" : "V-" in rails ? "neg" : "pos";
    const extra = [];
    if (names.length) {
      const which = /** @type {HTMLSelectElement} */ (h("select", { id: "rail-sweep-rail", "aria-label": "Rail to compare" }));
      for (const n of names) which.append(new Option(n, n));
      const values = /** @type {HTMLInputElement} */ (h("input", { type: "text", id: "rail-sweep-values", placeholder: "e.g. 9, 12, 18", autocomplete: "off" }));
      const button = tryButton("rail-sweep-run", values, () => handle, () => app.runSweep(which.value, "rail", splitValues(values.value)));
      extra.push(h("div", { class: "sweep-row" }, [h("label", { for: "rail-sweep-values" }, [`Compare supply voltages, overlaid on the plots (up to ${COMPARE_MAX})`]), which, values, button]));
    }
    const size = (/** @type {string} */ n) => (n in rails ? String(Math.abs(rails[n])) : "9");
    const handle = openForm(els.host, {
      title: "Power",
      subtitle: "custom",
      fields: [
        { name: "type", label: "Type", kind: "select", value: type,
          options: [["pos", "+ (positive)"], ["neg", "\u2212 (negative)"], ["both", "\u00b1 (both)"]],
          hint: "+ for most pedals (NPN transistors, op-amps); \u2212 for PNP circuits like the Fuzz Face; \u00b1 for a split supply." },
        { name: "pos", label: "V+", kind: "number", value: size("V+"), unit: "V" },
        { name: "neg", label: "V\u2212", kind: "number", value: size("V-"), unit: "V", hint: "9 here is \u22129 V." },
      ],
      extra,
      onSubmit: async (values) => {
        let next;
        try {
          next = setRails(c, {
            "V+": values.type === "neg" ? "" : values.pos,
            "V-": values.type === "pos" ? "" : values.neg,
          });
        } catch (err) {
          return /** @type {Error} */ (err).message;
        }
        return app.tryEdit(next, "Edit power");
      },
    });
    // show only the sides the type has
    const typeSelect = /** @type {HTMLSelectElement} */ (handle.form.querySelector("#field-type"));
    const sides = () => {
      for (const [name, shown] of [["pos", typeSelect.value !== "neg"], ["neg", typeSelect.value !== "pos"]]) {
        const row = /** @type {HTMLElement} */ (handle.form.querySelector(`#field-${name}`)?.closest(".form-row"));
        row.hidden = !shown;
      }
    };
    typeSelect.addEventListener("change", sides);
    sides();
  }

  select.addEventListener("change", () => {
    const value = select.value;
    const choice = powerChoices(app.circuit()).find((c) => c.key === value);
    const text = select.selectedOptions[0]?.text ?? "";
    show(); // put the selector back; the edit (or the dialog) makes the change
    if (value === "custom") return powerDialog();
    if (!choice) return;
    try {
      app.edit(setPower(app.circuit(), choice.rails), `Power ${text}`);
    } catch (err) {
      app.showError(/** @type {Error} */ (err).message);
    }
  });

  return { show, showDraw };
}
