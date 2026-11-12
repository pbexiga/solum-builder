/**
 * The value and rotation sliders (DOM, D-081): the inspector's, and Edit curve's (a dot's,
 * By part's, the up/down pair's, D-097, D-100, D-102). Dragging one redraws the Frequency
 * curve from the browser's solve; letting go applies the value (one undo step) and re-runs
 * ngspice, as the knobs do. The slider itself is `editor/slider.js`, the steps and the
 * solve `live.js`; fetching a live system and drawing its curve are the app root's.
 */

import { updatePart } from "./editor/edit.js";
import { valueSlider } from "./editor/slider.js";
import { keptSteps, liveValues } from "./live.js";

/**
 * @typedef {import("./live.js").Live} Live
 *
 * @typedef {object} SliderApp what the sliders ask of the app root
 * @property {() => any} circuit
 * @property {() => any} run the last run
 * @property {() => any} played the circuit as played (the knobs where they are)
 * @property {() => boolean} autorun
 * @property {() => string[]} frequencyNets the nets the Frequency panel shows now
 * @property {(controls: Array<{ref: string, field: string}>, steps?: Record<string, any[]>, circuit?: any) => Promise<Live>} fetchLive
 * @property {(live: Live, values: Record<string, number>) => void} drawLive the Frequency plot from the browser's solve
 * @property {(next: any, label: string, source?: string) => Promise<string | null>} tryEdit an edit checked with the server first
 * @property {() => Promise<void>} ranAgain the re-run a let-go slider waits for
 * @property {(circuit: any) => Promise<unknown>} setCircuit put a circuit back (Cancel)
 * @property {() => void} discardUndo drop the newest undo step
 * @property {() => unknown} refresh run again
 * @property {() => void} redraw the panels from the last run (back to ngspice's curve)
 */

/** Parts the inspector gives a value slider. */
const SLIDER_TYPES = ["resistor", "capacitor", "inductor", "pot", "trimmer", "amp"];

/**
 * @typedef {{field: "value" | "rotation", label: string, byHand?: boolean}} SliderField
 * `byHand`: a trimmer's rotation, turned by hand: it moves it as if without its target (its
 * row hides while the form's target holds, `.locked`; turning it after Remove target takes
 * the target off, round 3b)
 */

/**
 * The inspector's sliders for a part: its value, and a pot's or trimmer's rotation.
 * @param {any} part @returns {SliderField[]}
 */
export function sliderFields(part) {
  /** @type {SliderField[]} */
  const fields = [{ field: "value", label: part.type === "amp" ? "Input impedance" : "Value" }];
  if (part.type === "pot") fields.push({ field: "rotation", label: "Rotation" });
  if (part.type === "trimmer") fields.push({ field: "rotation", label: "Rotation", byHand: true });
  return fields;
}

/**
 * @param {SliderApp} app
 */
export function liveSliders(app) {
  /**
   * `circuit` with trimmer `ref` turned by hand: its target off, left at the turn the last
   * run solved. @param {any} circuit @param {string} ref
   */
  function handTurned(circuit, ref) {
    const part = circuit.parts.find((/** @type {any} */ p) => p.ref === ref);
    if (!part?.bias_target) return circuit;
    return updatePart(circuit, ref, { bias_target: null, rotation: app.run()?.op?.bias?.[ref] ?? part.rotation });
  }

  /**
   * The inspector's sliders for `ref`: its value, and a pot's or trimmer's rotation.
   * Dragging one redraws the Frequency curve in the browser; letting go applies it (one undo
   * step) and re-runs ngspice, as the knobs do. Cancel puts everything back.
   * With a `prefix` the sliders stand on their own (Edit curve's: a dot's or By part's, D-097, D-102): they take
   * element ids with it and don't write into the inspector's fields.
   * @param {string} ref @param {SliderField[]} fields @param {string} [prefix]
   */
  function slideFields(ref, fields, prefix = "") {
    const original = app.circuit();
    let commits = 0;
    let closed = false;
    let dragged = false;
    const sliders = fields.map(({ field, label, byHand }) => {
      const base = (/** @type {any} */ c) => (byHand ? handTurned(c, ref) : c);
      /** @type {import("./live.js").Live | null} */
      let live = null;
      /** @type {Promise<void> | null} */
      let catching = null;
      let at = 0; // the step the slider is on
      const input = () => /** @type {HTMLInputElement | null} */ (prefix ? null : document.getElementById(`field-${field}`));
      // the form's own field as the slider moves: a rotation's is in percent
      const shown = (/** @type {import("./live.js").Step} */ step) => (field === "rotation" ? String(Math.round(Number(step.value) * 100)) : step.text);
      const ui = valueSlider(field, label, {
        onInput(i) {
          if (!live) return;
          dragged = true;
          at = i;
          const field_ = input();
          if (field_) field_.value = shown(live.sliders[0].steps[i]);
          // another part selected since the slider loaded: fetch its nets, then draw (the
          // slider keeps its steps and doesn't jump)
          const nets = app.frequencyNets();
          if (nets.every((n) => n in live.nets)) app.drawLive(live, liveValues(live.sliders, [i]));
          else catching ??= app.fetchLive([{ ref, field }], keptSteps(live.sliders), base(app.played()))
            .then((got) => {
              if (closed) return;
              live = got;
              app.drawLive(got, liveValues(got.sliders, [at]));
            })
            .catch(() => {}) // no live curve this time: the release still re-runs ngspice
            .finally(() => { catching = null; });
        },
        onCommit(i) {
          return live ? commit(field, live.sliders[0].steps[i].value) : undefined;
        },
        onSnap(value) {
          const field_ = input();
          if (field_) field_.value = value;
          commit(field, value);
        },
      }, prefix);
      return {
        field,
        base,
        ui,
        /** @param {Record<string, any[]>} [steps] */
        async load(steps = {}) {
          try {
            const got = await app.fetchLive([{ ref, field }], steps, base(app.played()));
            if (closed) return;
            live = got;
            at = got.sliders[0].index;
            ui.show(got.sliders[0]);
          } catch (err) {
            if (!closed) ui.fail(/** @type {Error} */ (err).message);
          }
        },
        kept: () => (live ? keptSteps(live.sliders) : {}),
        /** Its steps as numbers and their text, and the step it's on (null until loaded). */
        steps: () => (live ? { values: live.sliders[0].steps.map((s) => Number(s.si)), texts: live.sliders[0].steps.map((s) => s.text), at } : null),
      };
    });

    /** @param {"value" | "rotation"} field @param {string | number} value */
    async function commit(field, value) {
      const slider = /** @type {(typeof sliders)[number]} */ (sliders.find((x) => x.field === field));
      const kept = slider.kept();
      const message = await app.tryEdit(updatePart(slider.base(app.circuit()), ref, { [field]: value }), `${field === "rotation" ? "Turn" : "Change"} ${ref}`, prefix ? "curve" : ""); // prefixed sliders are Edit curve's (a dot's, or By part's)
      if (closed) return;
      if (message) return slider.ui.fail(message);
      commits++;
      await app.ranAgain(); // the sliders always re-run, as the knobs do
      // every slider's live system now has the new part in it (a new value changes how a turn sounds)
      await Promise.all(sliders.map((x) => x.load(x === slider ? kept : x.kept())));
    }

    return {
      /** @param {HTMLFormElement} form @param {Promise<void>} shown the part's view (its curves name the nets) */
      attach(form, shown) {
        for (const { field, ui } of sliders) form.querySelector(`#field-${field}`)?.closest(".form-row")?.after(ui.row);
        shown.then(() => Promise.all(sliders.map((x) => x.load())));
      },
      /** Put the sliders in `el` on their own (no form) and load their steps. @param {HTMLElement} el */
      mount(el) {
        el.append(...sliders.map((x) => x.ui.row));
        return Promise.all(sliders.map((x) => x.load()));
      },
      /** The first slider's steps (`steps` above), for an Edit mode handle. */
      steps: () => sliders[0].steps(),
      /** Move the first slider to step `i` as a drag would (the curve follows). @param {number} i */
      seek: (i) => sliders[0].ui.seek(i),
      /** Let the first slider go where it is: applied and re-run, as on release. */
      release: () => sliders[0].ui.release(),
      /** @param {boolean} submitted @param {boolean} [quiet] don't redraw the panels (they are being redrawn) */
      close(submitted, quiet = false) {
        closed = true;
        if (!submitted && commits) {
          for (let k = 0; k < commits; k++) app.discardUndo();
          app.setCircuit(original).then(() => app.autorun() || app.refresh());
        } else if (dragged && app.run() && !quiet) app.redraw(); // a drag let go off the slider: back to ngspice's curve
      },
    };
  }

  /**
   * Value sliders for parts that change together (Edit curve's up/down, D-100), in their
   * own rows (`prefix`): one live system with all of them, drawn with each at its step;
   * letting go applies them all as one edit and re-runs, as the other sliders do.
   * @param {string[]} refs @param {string} prefix
   */
  function slideTogether(refs, prefix) {
    /** @type {import("./live.js").Live | null} */
    let live = null;
    /** @type {number[]} */
    let ats = [];
    let closed = false;
    let dragged = false;
    const draw = () => live && app.drawLive(live, liveValues(live.sliders, ats));
    const uis = refs.map((ref, k) =>
      valueSlider("value", `${ref} value`, {
        onInput(i) {
          dragged = true;
          ats[k] = i;
          draw();
        },
        onCommit: () => commit(),
        onSnap: (value) => commit({ [ref]: value }),
      }, `${prefix}${k}-`, ref),
    );

    /** @param {Record<string, any[]>} [steps] */
    async function load(steps = {}) {
      try {
        const got = await app.fetchLive(refs.map((ref) => ({ ref, field: "value" })), steps);
        if (closed) return;
        live = got;
        ats = got.sliders.map((s) => s.index);
        got.sliders.forEach((s, k) => uis[k].show(s));
      } catch (err) {
        if (!closed) uis.forEach((u) => u.fail(/** @type {Error} */ (err).message));
      }
    }

    /** Apply every slider's step (or only `values`, a snap): one undo step. @param {Record<string, string>} [values] */
    async function commit(values) {
      if (!live) return;
      const kept = keptSteps(live.sliders);
      const now = /** @type {import("./live.js").Live} */ (live);
      const wanted = values ?? Object.fromEntries(refs.map((ref, k) => [ref, now.sliders[k].steps[ats[k]].value]));
      let next = app.circuit();
      for (const [ref, value] of Object.entries(wanted)) next = updatePart(next, ref, { value });
      const message = await app.tryEdit(next, `Change ${Object.keys(wanted).join(", ")}`, "curve"); // only Edit curve's up/down uses these
      if (closed) return;
      if (message) return uis.forEach((u) => u.fail(message));
      await app.ranAgain(); // the sliders always re-run, as the knobs do
      await load(values ? {} : kept);
    }

    return {
      /** Put the sliders in `el` and load their steps. @param {HTMLElement} el */
      mount(el) {
        el.append(...uis.map((u) => u.row));
        return load();
      },
      /** Each slider's steps as numbers and their text, and the step it's on (null until loaded). */
      steps: () => live?.sliders.map((s, k) => ({ values: s.steps.map((x) => Number(x.si)), texts: s.steps.map((x) => x.text), at: ats[k] })) ?? null,
      /** Move the sliders to these steps together, as a drag would (the curve follows once). @param {number[]} indices */
      seek(indices) {
        dragged = true;
        ats = [...indices];
        uis.forEach((u, k) => u.place(indices[k]));
        draw();
      },
      /** Let them go where they are: applied and re-run, as on release. */
      release: () => commit(),
      /** @param {boolean} _submitted @param {boolean} [quiet] don't redraw the panels (they are being redrawn) */
      close(_submitted, quiet = false) {
        closed = true;
        if (dragged && app.run() && !quiet) app.redraw();
      },
    };
  }

  /** The inspector's sliders for `part`, or null when its type has none. @param {any} part */
  const forPart = (part) => (SLIDER_TYPES.includes(part.type) ? slideFields(part.ref, sliderFields(part)) : null);

  return { slideFields, slideTogether, forPart };
}
