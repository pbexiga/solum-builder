/**
 * What the inspector shows for each part type, and how its form turns back into edits.
 * Pure: no DOM. Values stay strings as typed (`4k7`); the server parses and validates.
 *
 * @typedef {{name: string, label: string, kind: "text" | "number" | "select" | "textarea",
 *   value: string, options?: Array<[string, string] | [string, string, string]>, unit?: string, hint?: string, about?: string | string[], help?: string,
 *   fills?: Record<string, Record<string, string>>, showIf?: {field: string, not?: string, is?: string}, readonly?: boolean,
 *   lockedWhile?: string[], lockedHint?: string, remove?: {label: string, fields: string[]},
 *   add?: {label: string, fields: string[], values?: Record<string, string>}, hidden?: boolean, range?: {min: number, max: number, message: string}}} Field
 *   `hint`: a few words under the box (what it means); `about`: the rest (how to measure
 *   it, the datasheet's range, the background), in the form's ⓘ under its label (9c);
 *   `help`: a Help page (`"capacitors"`): the hint is a link that opens it;
 *   `readonly`: shown but not typed into (a targeted trimmer's solved rotation);
 *   `lockedWhile`: read-only only while all these fields have a value (its bias target), its
 *   value as it opened and `lockedHint` then, `hint` while free;
 *   `remove`: a button on its row that empties `fields` and hides their rows (Remove target);
 *   `add`: a button on its row that shows `fields`' rows (Add target), there while they're
 *   hidden, putting `values` in those left empty; `hidden`: its row starts hidden;
 *   `range`: a number outside it is an error, said as soon as the box is left (`fieldProblem`)
 *   `fills`: picking an option sets other fields (option → field → value);
 *   `showIf`: the field shows only while another field isn't `not` (or, with `is`, only while it is)
 * @typedef {{kind: string, name: string, r: string, l: string, c: string, volume: string}} PickupChoice
 * @typedef {{type: string, halves: number, simulated: string[], package: {name: string, pins: Record<string, number>, source: string} | null}} Chip
 *   a chip model's chip: op-amp, inverter or OTA (`/api/models/chips`, D-140, D-180)
 * @typedef {{state: string, name: string, volts: number, hours: number}} BatteryState
 *   a 9 V battery's state as it drains (`/api/guides/batteries`, D-143)
 * @typedef {{kind: string, name: string, measured: string, l: string, r: string}} InductorPreset
 *   a measured wah inductor (`/api/guides/inductors`, D-173)
 * @typedef {{patch: Record<string, unknown>, ref: string,
 *   drain: {trimmer: string | null, volts: number | null} | null}} Edit
 */

import { diodeRef, drainTarget } from "./edit.js";
import { allSwitchKinds, kindOf, poleDraw } from "../schematic/symbols.js";
import { COMPARE_MAX } from "../series.js";

const TAPERS = [["A", "A (log)"], ["B", "B (linear)"], ["C", "C (reverse log)"], ["W", "W (centre-tap)"]];
const CAP_KINDS = [["", "unspecified"], ["film", "film"], ["ceramic", "ceramic"], ["c0g", "C0G"], ["electrolytic", "electrolytic"], ["tantalum", "tantalum"]];

/**
 * The Kind dropdown's options, each with its one-line hint from the capacitor guide
 * (`/api/guides/capacitors`, D-095): "film · signal path, the default for audio".
 * @param {Array<{kind: string, hint: string}>} guide
 * @returns {Array<[string, string]>}
 */
export function capKindOptions(guide) {
  return CAP_KINDS.map(([kind, label]) => {
    const hint = guide.find((g) => g.kind === kind)?.hint;
    return [kind, hint ? `${label} \u00b7 ${hint}` : label];
  });
}

/** @param {unknown} v */
const str = (v) => (v === undefined || v === null ? "" : String(v));

/** @param {number | undefined} f fraction 0-1 → percent text */
const percent = (f) => str(f === undefined ? 50 : Math.round(f * 1000) / 10);

/**
 * @param {string} name @param {string} label @param {unknown} value @param {Partial<Field>} [more]
 * @returns {Field}
 */
const text = (name, label, value, more = {}) => ({ name, label, kind: "text", value: str(value), ...more });

/**
 * @param {string} name @param {string} label @param {unknown} value @param {Partial<Field>} [more]
 * @returns {Field}
 */
const num = (name, label, value, more = {}) => ({ name, label, kind: "number", value: str(value), ...more });

/**
 * @param {string} name @param {string} label @param {unknown} value @param {Array<[string, string]>} options
 * @returns {Field}
 */
const select = (name, label, value, options) => ({ name, label, kind: "select", value: str(value), options });

/**
 * A model dropdown's options: once you've added a model of this type, two groups, *Added
 * by you* first, then *Stock* (9c); one plain list until then. A model no list has (from a
 * file made elsewhere) stays on top, ungrouped.
 * @param {string[]} ids @param {string | undefined} current @param {string[]} [yours] the ids you added
 * @returns {Array<[string, string] | [string, string, string]>}
 */
function modelOptions(ids, current, yours = []) {
  const missing = current && !ids.includes(current) ? [[current, current]] : [];
  const mine = ids.filter((id) => yours.includes(id));
  const grouped = mine.length
    ? [...mine.map((id) => [id, id, "Added by you"]), ...ids.filter((id) => !yours.includes(id)).map((id) => [id, id, "Stock"])]
    : ids.map((id) => [id, id]);
  return /** @type {any} */ ([...missing, ...grouped]);
}

/** A rotation typed by hand: 0 to 100 %, said as soon as the box is left. */
const ROTATION_RANGE = { min: 0, max: 100, message: "Rotation goes from 0 to 100 %." };

/**
 * A targeted trimmer's Rotation: what the last run turned it to, read-only, since the
 * target sets it on every run (D-123). Its `lockedHint` says so; its `hint` is for once
 * Remove target frees it. @param {any} part @param {number | undefined} solved
 * @returns {Field}
 */
export function targetRotation(part, solved) {
  const where = solved === undefined ? "" : ` The last run turned it to ${percent(solved)} %.`;
  return {
    ...num("rotation", "Rotation", percent(solved ?? part.rotation), { unit: "%", range: ROTATION_RANGE }),
    readonly: true,
    lockedWhile: ["bias_node", "bias_volts"],
    hint: "Turned by hand from here, once Apply takes the target off.",
    lockedHint: "Set by its bias target (within 1 mV).",
    about: `Turned until ${part.bias_target.node} is within 1 mV of its target, so it can read e.g. 3.999 V for 4 V.${where} Remove the target to turn it by hand from here.`,
  };
}

/**
 * @typedef {{node: string, volts: number | null}} TargetNode a node a trimmer could hold ("Q1.D"), its voltage now
 */

/** A transistor's output pin, the one a bias trimmer is set by: a JFET's or MOSFET's drain, a BJT's collector. */
const OUTPUT_PIN = { jfet: "D", mosfet: "D", bjt: "C" };

/**
 * The node trimmer `ref` holds to a target (round 3b): the drain or collector of the one
 * transistor it's wired to, whichever pin it touches (a drain or collector resistor, a
 * source or emitter leg, a base divider's wiper), since a stage is biased by its output
 * voltage. One whose own net has a drain or collector on it takes that transistor; else
 * the one transistor it touches at all. None when that's two transistors (a balance trim
 * on a pair: not one node at a voltage), none, or a node another trimmer holds already
 * (two would fight). Its voltage is the last run's.
 * @param {string} ref @param {any} view the circuit's view (`parts` with their pins'
 * nets, `nets` with `rail`) @param {Record<string, number>} [voltages] @returns {TargetNode | null}
 */
export function targetNode(ref, view, voltages = {}) {
  const me = view.parts.find((/** @type {any} */ p) => p.ref === ref);
  if (!me) return null;
  const mine = new Set(me.pins.map((/** @type {any} */ p) => p.net).filter((/** @type {string | null} */ n) => n && !view.nets[n]?.rail));
  const output = (/** @type {any} */ p) => p.pins.find((/** @type {any} */ pin) => pin.name === OUTPUT_PIN[/** @type {"jfet" | "mosfet" | "bjt"} */ (p.type)]);
  const touching = view.parts.filter((/** @type {any} */ p) => p.type in OUTPUT_PIN && p.pins.some((/** @type {any} */ pin) => mine.has(pin.net)));
  const byOutput = touching.filter((/** @type {any} */ p) => mine.has(output(p)?.net));
  // outputs tied together (paralleled transistors) are one node: any of them will do
  const outNets = new Set(byOutput.map((/** @type {any} */ p) => output(p).net));
  const picked = outNets.size === 1 ? byOutput[0] : outNets.size === 0 && touching.length === 1 ? touching[0] : null;
  const pin = picked && output(picked);
  if (!pin) return null;
  const netOf = (/** @type {string} */ node) => {
    const [r, name] = node.split(".");
    return view.parts.find((/** @type {any} */ p) => p.ref === r)?.pins.find((/** @type {any} */ x) => x.name === name)?.net;
  };
  const held = view.circuit.parts.some((/** @type {any} */ p) => p.ref !== ref && p.bias_target && netOf(p.bias_target.node) === pin.net);
  return held ? null : { node: `${picked.ref}.${pin.name}`, volts: voltages[pin.net] ?? null };
}

/**
 * A trimmer without a target: its Rotation by hand, with Add target when there's a node it
 * could hold (round 3). @param {any} part @param {TargetNode | null} node @returns {Field}
 */
function untargetedRotation(part, node) {
  const hint = node
    ? "Turned by hand. To hold a voltage instead: Add target."
    : "To hold a voltage instead, give it a target: Drain target in a JFET's form, or Bias to… in Bias & headroom.";
  return {
    ...num("rotation", "Rotation", percent(part.rotation), { unit: "%", hint, range: ROTATION_RANGE }),
    lockedWhile: ["bias_node", "bias_volts"],
    lockedHint: "Turned to the target on Apply, and again on every run.",
  };
}

/**
 * A trimmer's target fields (D-127, round 3b): the node it holds, shown (it's the drain or
 * collector it's wired to, `targetNode`), and the volts, checked on Apply. With no target
 * they start hidden behind Add target (on Rotation), which fills them: the node, at its
 * voltage now. Remove target hides them again, there and then, and Add target comes back.
 * @param {any} t its target, if any @param {TargetNode} node @returns {Field[]}
 */
function targetFields(t, node) {
  const hint = t ? "Checked on Apply against how far it can move the node." : "Starts at the node's voltage now. Checked on Apply against how far it can move the node.";
  return [
    text("bias_node", "Target node", t?.node ?? "", { readonly: true, hidden: !t, hint: "The drain or collector of the transistor it's wired to." }),
    { ...num("bias_volts", "Target", t?.volts ?? "", { unit: "V", hint }), hidden: !t,
      remove: { label: "Remove target", fields: ["bias_node", "bias_volts"] } },
  ];
}

/** Add target (round 3): shows the target fields, filled with `node` at its voltage now. @param {TargetNode} node */
const addTarget = (node) => ({ label: "Add target", fields: ["bias_node", "bias_volts"],
  values: { bias_node: node.node, bias_volts: node.volts === null ? "" : node.volts.toFixed(2) } });

/**
 * What's wrong with a value typed in a number field, said as soon as the box is left: not
 * a number, or outside its `range`. Null when fine or empty (Apply decides about empty).
 * @param {Field} f @param {string} value @returns {string | null}
 */
export function fieldProblem(f, value) {
  if (f.kind !== "number" || value.trim() === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return `${f.label} must be a number.`;
  if (f.range && (n < f.range.min || n > f.range.max)) return f.range.message;
  return null;
}

/**
 * The inspector's fields for a part, in order. `ref` always comes first.
 * @param {any} part the part as stored in the circuit file
 * @param {{circuit: any, models: Record<string, string[]>, capKinds?: Array<{kind: string, hint: string}>,
 *   pickups?: PickupChoice[], bias?: Record<string, number>, target?: TargetNode | null,
 *   jfets?: Record<string, {idss: number, vp: number}>, bjts?: Record<string, {hfe: number, leakage: number}>,
 *   chips?: Record<string, Chip>, view?: any}} ctx
 *   `models`: model ids by part type (`/api/models`), and under `yours` the ones you added;
 *   `bias`: the last run's solved trimmer rotations (`op.bias`);
 *   `target`: the node a trimmer holds (`targetNode`);
 *   `jfets`: each JFET model's own Idss and Vp (`/api/models/jfets`), where measured ones start;
 *   `bjts`: each transistor model card's own gain and leakage (`/api/models/bjts`), likewise (D-130);
 *   `chips`: each chip model's chip, `view`: the circuit's view (its pins' nets), for a
 *   chip's pins (D-140, D-180);
 *   `capKinds`: the capacitor guide's kinds, for the Kind dropdown's hints;
 *   `pickups`: the pickup guide's measured pickups (D-096); `inductors`: the measured wah inductors (D-173)
 * @returns {Field[]}
 */
export function inspectorFields(part, ctx) {
  /** @type {Field[]} */
  const fixed = FIXED_REFS[part.type];
  const fields = [fixed ? readonly("ref", "Ref", part.ref, fixed) : text("ref", "Ref", part.ref)];
  const model = () => select("model", "Model", part.model, modelOptions(ctx.models[part.type] ?? [], part.model, ctx.models.yours));
  switch (part.type) {
    case "resistor":
      fields.push(text("value", "Value", part.value, { unit: "Ω" }), num("rating_w", "Rating", part.rating_w, { unit: "W" }));
      break;
    case "capacitor":
      fields.push(
        text("value", "Value", part.value, { unit: "F" }),
        { ...select("kind", "Kind", part.kind, capKindOptions(ctx.capKinds ?? [])), hint: "Choosing capacitors", help: "capacitors" },
        num("rating_v", "Rating", part.rating_v, { unit: "V" }),
      );
      break;
    case "inductor":
      fields.push(...inductorFields(part, ctx.inductors ?? []));
      break;
    case "pot":
      fields.push(
        text("value", "Value", part.value, { unit: "Ω" }), select("taper", "Taper", part.taper ?? "B", TAPERS),
        { ...select("gangs", "Gangs", part.gang ? "2" : "1", [["1", "Single"], ["2", "Dual: one knob, two gangs"]]),
          ...(part.gang ? { hint: `Gang ${part.gang.toUpperCase()} of 2; one knob turns both.` } : {}),
          about: ["A dual pot is two pots on one shaft, like a stereo volume or a two-stage gain. Dual draws its second gang beside this one (VR1A, VR1B): wire each where it goes. They share the value, taper, rotation and label."] },
        num("rotation", "Rotation", percent(part.rotation), { unit: "%", range: ROTATION_RANGE, hint: "Where its knob starts when the circuit opens.", about: "Turning the knob doesn't change this; Knobs → Use as opening positions does." }), text("label", "Knob label", part.label),
      );
      break;
    case "trimmer": {
      // the node it holds is the drain or collector it's wired to (a target made elsewhere
      // keeps its own); its volts are checked on Apply against how far the trimmer reaches
      // (D-127). Remove and Add target swap in the form, without an Apply between (round 3b)
      const t = part.bias_target;
      const node = ctx.target ?? (t ? { node: t.node, volts: t.volts } : null);
      fields.push(
        text("value", "Value", part.value, { unit: "Ω" }), select("taper", "Taper", part.taper ?? "B", TAPERS),
        { ...(t ? targetRotation(part, ctx.bias?.[part.ref]) : untargetedRotation(part, node)), ...(node ? { add: addTarget(t ? { node: t.node, volts: ctx.target?.node === t.node ? ctx.target.volts : null } : node) } : {}) },
        ...(node ? targetFields(t, node) : []),
        text("label", "Label", part.label),
      );
      break;
    }
    case "switch":
      fields.push(...switchFields(part));
      break;
    case "diode":
      fields.push(model());
      break;
    case "led":
      fields.push(model(), text("label", "Label", part.label, { hint: "What it's for, shown by its ref: Status for a footswitch's light." }));
      break;
    case "jack":
      fields.push(
        { ...select("stereo", "Jack", part.stereo ? "stereo" : "mono", [["mono", "mono (TS: tip, sleeve)"], ["stereo", "stereo (TRS: tip, ring, sleeve)"]]),
          hint: "Drawn for the build: the simulation runs guitar → amp.",
          about: ["The signal starts at the guitar input and ends at the amp in the simulation, whatever the jacks join.",
            "A stereo input's ring is how pedals switch a battery on: wire the battery's − to R and S to ground. With a battery in the circuit, Knobs has a Cable switch (in: R joins S)."] },
        text("label", "Label", part.label, { hint: "What it's for, shown by its ref: Input, Output." }),
      );
      break;
    case "dcjack":
      fields.push({ ...readonly("lugs", "Lugs", "+ the sleeve, − the centre pin, bat the battery lug",
        "Centre negative. Wire + to V+: the Power menu's supply comes in here."),
      about: "Centre negative, as pedal supplies are: wire − to GND. With a battery in the circuit, its + on the battery lug, Knobs has Power: DC jack or Battery (no plug: the battery lug touches the sleeve)." });
      break;
    case "battery":
      fields.push(...batteryFields(part, ctx.batteries ?? [], ctx.view?.battery_wiring ?? null));
      break;
    case "bjt":
      fields.push(model(), ...bjtSpecFields(part, ctx.bjts?.[part.model]), atRest(part));
      break;
    case "mosfet":
      fields.push(
        { ...model(), hint: "N-channel.", about: ["Enhancement (2N7000, BS170): off until the gate is about 2 V above the source. Depletion (LND150): on at 0 V, off below about −1.7 V.", "The body diode, drawn from source to drain, is in the model."] },
        ...drainFields(part, ctx),
        atRest(part),
      );
      break;
    case "jfet":
      fields.push(model(), ...jfetSpecFields(part, ctx.jfets?.[part.model]), ...drainFields(part, ctx), atRest(part));
      break;
    case "opamp":
    case "inverter":
    case "ota":
    case "powerunit":
      fields.push(...chipFields(part, ctx));
      break;
    case "vsource":
      fields.push(text("value", "Voltage", part.value, { unit: "V", hint: "Drives its own net. V+ and V− come from Power." }));
      break;
    case "chargepump": // D-093, D-226: what it does comes from the parts wired to it
      fields.push(
        { ...model(), about: "Draw its caps and diodes as on the datasheet: a flying cap from pin 2 to pin 4 makes −V+ on pin 5; a cap from pin 2 to two diodes makes 2 × V+ (pin 5 to ground). Both at once is the Klon's. The charge-pump blocks have them drawn. Pin 1 wired to V+ (pin 8) is boost on a TC1044S: the oscillator runs faster, moving the pump's whine above hearing. Pins 6 and 7 may stay open." },
      );
      break;
    case "regulator": // D-227
      fields.push({ ...model(), about: "Holds its output at the model's voltage while its input stays above that plus its dropout (a 78L12: 12 V from 13.7 V or more). Feed it from a charge pump's 18 V for a 12 V supply; its bias current (4.2 mA for a 78L12) flows to ground whatever the load. The datasheet's caps: 0.33 µF on the input, 0.1 µF on the output." });
      break;
    case "guitar":
      fields.push(...guitarFields(part, ctx.pickups ?? []));
      break;
    case "amp":
      fields.push(text("value", "Input impedance", part.value ?? "1M", { unit: "Ω" }));
      break;
  }
  return fields;
}

/**
 * A switch's form (D-143): its type (every pole takes it; poles come and go with it), the
 * position it opens at, by name, its label, and what each position joins.
 * @param {any} part
 * @returns {Field[]}
 */
function switchFields(part) {
  const kind = kindOf(part);
  const kinds = allSwitchKinds();
  const custom = part.kind === "custom" && part.custom;
  const positions = kind?.positions ?? [];
  const at = Math.min(part.position ?? 0, Math.max(positions.length - 1, 0));
  const { lugs, closed } = poleDraw(part);
  const contacts = positions.map((name, i) => `${name}: ${closed[i] ? `${lugs[0]}–${closed[i]}` : "open"}`).join(" · ");
  const poles = kind && kind.poles > 1 ? `One of ${kind.poles} poles; they switch together.` : "";
  return [
    { ...select("kind", "Type", part.kind ?? "spdt", [...kinds.map((k) => /** @type {[string, string]} */ ([k.id, `${k.group}: ${k.name}`])),
      ["custom", custom ? `Custom: ${part.custom.name}` : "Custom: your own contacts…"]]),
      // a custom one's contacts open in their editor (9c); a built-in's poles are said
      ...(custom ? { hint: "Edit its contacts…", help: "custom-switch" } : poles ? { hint: poles } : {}),
      about: [...(kind?.hint ? [kind.hint] : []), "Custom, at the end of the list, starts from the type picked now: set your own poles, throws, positions and what each joins."] },
    { ...select("position", "Position", String(at), positions.map((name, i) => /** @type {[string, string]} */ ([String(i), name]))),
      hint: "Where it is when the circuit opens. Flip it in Knobs." },
    readonly("contacts", "This pole", contacts),
    text("label", "Label", part.label),
    // your name for each position (D-143), on the Knobs buttons and the drawing
    ...positions.map((name, i) => text(`name_${i}`, `Name for ${name}`, part.names?.[i] ?? "",
      i === 0 ? { hint: "Optional, like Vintage or Thick. Empty: the switch's own." } : {})),
  ];
}

/**
 * A battery's form (D-143): how drained it is (each state's voltage from the battery
 * guide, or the voltage you measured) and its internal resistance, if you measured it.
 * @param {any} part @param {BatteryState[]} states @param {string | null} wiring `alone`, `lug`, `beside` or `apart`
 * @returns {Field[]}
 */
function batteryFields(part, states, wiring) {
  const fills = Object.fromEntries(states.map((s) => [s.state, { volts: String(s.volts) }]));
  const options = [...states.map((s) => /** @type {[string, string]} */ ([s.state, `${s.name} (${s.volts} V)`])), ["measured", "Your measured voltage"]];
  return [
    { ...select("state", "Drained", part.state ?? "measured", options), fills, ...BATTERY_WIRING[wiring ?? "unknown"],
      about: [...(BATTERY_WIRING[wiring ?? "unknown"].about ?? []), ...BATTERY_WAYS, "The states are a 9 V alkaline on a pedal's load, from Energizer's 522 datasheet."] },
    text("volts", "Voltage", part.volts ?? 9, { unit: "V", hint: "Measure yours with the pedal on." }),
    text("resistance", "Internal resistance", part.resistance ?? "", { unit: "Ω", hint: "Empty: none.",
      about: "The datasheet gives none. Measure yours: its drop in volts on a known load, divided by the current." }),
  ];
}

/** Every way a battery can be wired and what it does then (D-185, D-202): the battery's ⓘ, after its own case. */
export const BATTERY_WAYS = [
  "Where its + goes decides what it powers:",
  "• On V+, no DC jack drawn: it powers the pedal, and the Power menu is greyed.",
  "• On the DC jack's battery lug (the jack's + on V+): it powers the pedal while no plug is in; plug one in (Knobs → Power) and the Power menu's supply takes over, the battery cut off.",
  "• On V+ beside a DC jack: unplugged, it powers the pedal; plugged in, it stays connected beside the supply, so it needs an internal resistance to run, and Problems warns.",
  "• On any other net: it powers only what's on that net, and the Power menu keeps V+.",
  "Its − goes to ground, or to a stereo input jack's ring so plugging a cable in switches it on (the jack's cable switch in Knobs).",
];

/**
 * What the battery's form says it does, by how it's wired (the view's `battery_wiring`, 9c).
 * @type {Record<string, {hint?: string, about?: string[]}>}
 */
const BATTERY_WIRING = {
  alone: { hint: "It powers the circuit: the Power menu is greyed.",
    about: ["With no DC jack drawn, the battery always powers the circuit. To switch between it and a supply, draw a DC jack and wire the battery's + to its battery lug (Knobs → Power)."] },
  lug: { hint: "It powers the circuit while no plug is in the DC jack (Knobs → Power).",
    about: ["Its + is on the DC jack's battery lug: a plug in the jack cuts it off, as on a real pedal."] },
  beside: { hint: "Its + isn't on the DC jack's battery lug: it stays connected with a plug in.",
    about: ["Wire its + to the DC jack's battery lug for a plug to cut it off. Problems says so too."] },
  apart: { hint: "A supply on its own net: V+ comes from the Power menu.",
    about: ["Its + reaches no supply rail, so it powers only what's wired to its own net, and the Power menu keeps V+. Wire its + to V+ (or to the DC jack's battery lug) for it to power the pedal."] },
  unknown: {},
};

/**
 * An inductor's form (D-173): a measured wah inductor, which fills its inductance and wire
 * resistance, or your own values.
 * @param {any} part @param {InductorPreset[]} presets
 * @returns {Field[]}
 */
function inductorFields(part, presets) {
  const fills = Object.fromEntries(presets.map((p) => [p.kind, { value: p.l, resistance: p.r }]));
  const options = [...presets.map((p) => /** @type {[string, string]} */ ([p.kind, `${p.name} (${p.l}H, ${p.r} Ω)`])), ["own", "Your own values"]];
  return [
    { ...select("kind", "Inductor", part.kind ?? "own", options), fills,
      hint: "Wah inductors as one builder measured them.",
      about: "Measured at 1 kHz with an LCR meter (PedalPCB forum, 2024). Units of a type differ by 10 % or more: measure yours if you can." },
    text("value", "Inductance", part.value, { unit: "H", hint: "At 1 kHz.", about: "At 1 kHz, if your meter lets you pick: a wah inductor reads up to 30 % higher at 100 Hz." }),
    text("resistance", "Wire resistance", part.resistance ?? "", { unit: "Ω", hint: "DC resistance. Empty: an ideal coil.",
      about: "From a multimeter across it. It lowers the wah's peak." }),
  ];
}

/** A measured part's choice: the model's typical unit, or yours (D-130, round 3b). */
const SPEC_HINT = "The model's typical unit, or yours, measured.";
const SPEC_CHOICES = [["model", "the model's (typical)"], ["measured", "your unit's (measured)"]];

/**
 * The spec choice's hint: the model is one typical unit, and yours can be anywhere in the
 * datasheet's range, which is said when the model's record has it (`/api/models/…`).
 * @param {string} model
 * @param {[string, {min: number, max: number, at?: Record<string, number>} | undefined, number, string][]} specs
 *   each quantity's name, its range, the scale to show it in and its unit
 * @param {boolean} [estimated] the card was estimated with no sheet (D-186)
 * @returns {string}
 */
export function unitHint(model, specs, estimated = false) {
  const n = (/** @type {number} */ x) => String(+x.toPrecision(3)).replace("-", "−");
  const spans = specs.filter(([, r]) => r).map(([name, r, k, unit]) => {
    const range = /** @type {{min: number, max: number, at?: Record<string, number>}} */ (r);
    const [lo, hi] = [range.min * k, range.max * k];
    const span = lo < 0 || hi < 0 ? `${n(lo)} to ${n(hi)}` : `${n(lo)}–${n(hi)}`;
    const at = range.at?.ic !== undefined ? ` at ${n(range.at.ic * 1e3)} mA` : "";
    return `${name} ${span}${unit}${at}`;
  });
  const tail = "Measure yours to simulate it.";
  if (estimated && !spans.length) return `The model is an estimate: no ${model} datasheet with curves was found, so it's a related part's shape scaled to the ${model}'s published figures. ${tail}`;
  const head = `The model is one typical ${model}.`;
  if (!spans.length) return `${head} Yours differs, and this model's datasheet range isn't in yet. ${tail}`;
  return `${head} Your unit can be anywhere in the datasheet's range: ${spans.join(", ")}. ${tail}`;
}

/**
 * The model's tester gain where the tester runs it below the sheet's gain curve (9b: the
 * MPSA06 near 0.34 mA, its curve from 0.52 mA): a hint saying the figure is the card's
 * extrapolation. Empty when it's inside the curve.
 * @param {{tester_ic?: number, sheet_low_ic?: number}} model the model's (`/api/models/bjts`)
 * @returns {{hint?: string, about?: string}}
 */
export function belowSheet(model) {
  if (model.tester_ic === undefined || model.sheet_low_ic === undefined) return {};
  const mA = (/** @type {number} */ x) => String(+(x * 1e3).toPrecision(2));
  return { hint: "Extrapolated: below its datasheet's curve.",
    about: `What the model reads on a 9 V tester. The tester runs it near ${mA(model.tester_ic)} mA, below the ${mA(model.sheet_low_ic)} mA where its datasheet's gain curve starts, so this figure is the model's extrapolation, not the sheet's.` };
}

/** Parts whose ref never changes (D-141), and why. */
const FIXED_REFS = /** @type {Record<string, string>} */ ({ guitar: "The guitar input is always IN.", amp: "The amp is always OUT.", dcjack: "The DC jack is always DC." });

// What each chip pin is (= parts.py OPAMP_PIN_ROLES for an op-amp's), for its row
const PIN_ROLES = {
  "+": "+ in", "-": "− in", out: "out", "V+": "V+", "V-": "V−", comp1: "comp", comp2: "comp",
  null1: "offset null", null2: "offset null", nc: "NC", in: "in", iabc: "bias current in (Iabc)",
  dbias: "diode bias", bufin: "buffer in", bufout: "buffer out",
};
// the pins each chip unit has, when its model has no datasheet numbers (= parts.py)
const UNIT_PINS = /** @type {Record<string, string[]>} */ ({
  opamp: ["+", "-", "out"], inverter: ["in", "out"], ota: ["+", "-", "out", "iabc"],
});
const CHIP_NOUNS = /** @type {Record<string, [string, string]>} */ ({ opamp: ["op-amp", "Op-amps"], inverter: ["inverter", "Inverters"], ota: ["OTA", "OTAs"] });
const CHIP_SIZES = /** @type {Record<number, string>} */ ({ 2: "dual", 4: "quad", 6: "hex" });
// how to wire a chip's unused unit, said where the form lists it (the rule says it in full)
const SPARE_HOW = /** @type {Record<string, string>} */ ({ opamp: "as a buffer", inverter: "with its input tied to a supply", ota: "with its inputs grounded" });

/**
 * A chip unit's form (D-140, D-180: an op-amp, an inverter, an OTA), or a chip's power
 * unit's (D-179): its model (one per chip: a chip's units and power unit change together,
 * and only to a chip with as many units, D-172), what chip it is, each pin with its
 * datasheet number, its net and how the simulation handles it, and for a single op-amp
 * with spare pins, whether to draw them.
 * @param {any} part @param {{circuit: any, models: Record<string, string[]>, chips?: Record<string, Chip>, view?: any}} ctx
 * @returns {Field[]}
 */
function chipFields(part, ctx) {
  const chips = ctx.chips ?? {};
  const chip = chips[part.model];
  const unit = part.type === "powerunit";
  const grouped = unit || Boolean(part.half);
  const name = grouped ? part.ref.slice(0, -1) : part.ref;
  const units = ctx.circuit.parts.filter((/** @type {any} */ p) => p.half && p.type !== "switch" && p.ref.slice(0, -1) === name);
  const kind = unit ? units[0]?.type ?? chip?.type ?? "opamp" : part.type;
  const [noun, plural] = CHIP_NOUNS[kind] ?? CHIP_NOUNS.opamp;
  const count = grouped ? units.length : 1;
  // a chip's unit takes only chips with as many units, a single only singles: the drawing is the chip's
  const ids = (ctx.models[kind] ?? []).filter((id) => !chips[id] || chips[id].halves === count);
  const letters = [..."ABCDEF"].slice(0, count).map((x) => `${name}${x}`);
  const power = `${name}${"ABCDEFG"[count]}`;
  const whole = `${count > 2 ? `${letters[0]} to ${letters[count - 1]}` : letters.join(" and ")}, powered from ${power}`;
  const size = `${CHIP_SIZES[count] ?? count}${kind === "opamp" ? "" : ` ${noun}`}`;
  const others = grouped ? letters.filter((r) => r !== part.ref) : [];
  const fields = [
    { ...select("model", "Model", part.model, modelOptions(ids, part.model, ctx.models.yours)),
      hint: grouped ? `One model for the chip: changing it changes ${letters.join(", ")} and ${power}.` : `A single ${noun}.` },
    // the package under the box; the sheet the numbers come from is long, so it's in the ⓘ
    { ...readonly("chip", "Chip", grouped ? `${name}, a ${size}: ${whole}` : `${name}, a single`,
      chip?.package ? `Pin numbers: ${chip.package.name}.` : "No pin numbers: this model's datasheet couldn't be checked."),
      ...(chip?.package ? { about: `The pin numbers are from ${chip.package.source}.` } : {}) },
    ...chipPins(part, kind, chip, ctx.view),
  ];
  if (others.length) {
    const unused = (/** @type {string} */ r) => ctx.view?.parts.find((/** @type {any} */ p) => p.ref === r)?.draw?.unused;
    const spareOnes = others.filter(unused);
    const label = unit ? plural : kind !== "opamp" ? (others.length > 1 ? "Other units" : "Other unit") : others.length > 1 ? "Other halves" : "Other half";
    fields.push(readonly("other_half", label,
      others.map((r) => `${r}${unused(r) ? ", not used" : ", in use"}`).join("; "),
      [spareOnes.length ? `Problems says how to wire ${spareOnes.length > 1 ? "each unused one" : "it"} ${SPARE_HOW[kind]}.` : "",
        unit ? "" : `${power} carries the chip's V+ and V-.`].filter(Boolean).join(" ")));
  }
  const spare = chip?.package && ["null1", "null2", "nc"].some((pin) => pin in (chip.package?.pins ?? {}));
  if (part.type === "opamp" && !part.half && spare) fields.push({ ...select("show_pins", "Draw", part.show_pins ? "on" : "", [["", "the pins in use"], ["on", "all its pins"]]),
    hint: "Its offset and NC pins are drawn only when asked: most builds leave them unconnected." });
  return fields;
}

/**
 * One read-only row per pin of a chip part: `Pin 3 + in`, its net, and how it's handled.
 * A chip's unit lists its own pins, its power unit the chip's V+ and V- (D-179).
 * @param {any} part @param {string} kind the unit's type @param {Chip | undefined} chip @param {any} view
 * @returns {Field[]}
 */
function chipPins(part, kind, chip, view) {
  const drawn = view?.parts.find((/** @type {any} */ p) => p.ref === part.ref)?.pins ?? [];
  const netOf = (/** @type {string} */ pin) => drawn.find((/** @type {any} */ p) => p.name === pin)?.net;
  const numbered = chip?.package?.pins ?? {};
  const mine = Object.entries(numbered)
    .map(([key, n]) => ({ pin: key.includes(".") ? key.split(".")[1] : key, half: key.includes(".") ? key[0] : null, n }))
    .filter(({ pin, half }) => (part.type === "powerunit" ? !half && ["V+", "V-"].includes(pin)
      : half ? half === part.half : !part.half || !["V+", "V-"].includes(pin)))
    .sort((a, b) => a.n - b.n);
  const fallback = part.type === "powerunit" ? ["V+", "V-"] : [...(UNIT_PINS[kind] ?? []), ...(part.half ? (kind === "ota" ? ["dbias", "bufin", "bufout"] : []) : ["V+", "V-"])];
  const pins = mine.length ? mine : fallback.map((pin) => ({ pin, half: null, n: 0 }));
  // connected: another pin or a label on its net
  const joined = (/** @type {string} */ net, /** @type {string} */ pin) =>
    (view?.labels ?? []).some((/** @type {any} */ lb) => lb.net === net)
    || (view?.parts ?? []).some((/** @type {any} */ p) => p.pins.some((/** @type {any} */ q) => q.net === net && !(p.ref === part.ref && q.name === pin)));
  return pins.map(({ pin, n }) => {
    const net = netOf(pin);
    const value = !net ? "not drawn" : joined(net, pin) ? net : "not connected";
    const row = readonly(`pin_${pin}`, n ? `Pin ${n} · ${PIN_ROLES[/** @type {keyof typeof PIN_ROLES} */ (pin)]}` : PIN_ROLES[/** @type {keyof typeof PIN_ROLES} */ (pin)], value, pinHandling(pin, chip));
    return pin === "V+" ? { ...row, about: "The chip's power, V+ and V−, wired like any pin: its label names the supply (double-click the label to change it, e.g. to V+F)." } : row;
  });
}

/**
 * How the simulation handles a chip's pin, for its row's hint: only what's out of the
 * ordinary (not in the model, no connection); a simulated pin says nothing (9c).
 * @param {string} pin @param {Chip | undefined} chip
 */
function pinHandling(pin, chip) {
  if (pin === "nc") return "No internal connection: leave it unconnected.";
  if (chip && !chip.simulated.includes(pin)) return "Not in the model: the simulation leaves it open.";
  return "";
}

/**
 * A row that shows a value without a box to type in.
 * @param {string} name @param {string} label @param {string} value @param {string} [hint]
 * @returns {Field}
 */
function readonly(name, label, value, hint = "") {
  return { ...text(name, label, value), readonly: true, ...(hint ? { hint } : {}) };
}

/**
 * A transistor's gain and leakage (D-130): the model's, or your own transistor's,
 * measured; picked, as a JFET's Idss and Vp are. Measured starts at the model's own. Only
 * for model cards (`/api/models/bjts` lists them).
 * @param {any} part @param {{hfe: number, leakage: number, germanium?: boolean, estimated?: boolean, range?: any, tester_ic?: number, sheet_low_ic?: number} | undefined} model the model's
 * @returns {Field[]}
 */
function bjtSpecFields(part, model) {
  if (!model && !part.measured) return [];
  const own = part.measured ?? model;
  const only = { showIf: { field: "bjt_spec", not: "model" } };
  const typical = { showIf: { field: "bjt_spec", is: "model" }, readonly: true };
  // leakage only where it matters: a germanium model (its card's bandgap says so, D-138;
  // silicon leaks nA) or a part you measured it on (the user, 2026-10-28)
  const leaks = !!model?.germanium || part.measured?.leakage != null;
  return [
    { ...select("bjt_spec", leaks ? "Gain and leakage" : "Gain", part.measured ? "measured" : "model", SPEC_CHOICES),
      hint: SPEC_HINT, about: unitHint(part.model, [["hFE", model?.range?.hfe, 1, ""]], !!model?.estimated) },
    // what the model simulates, shown while it's picked (the user, 2026-10-28)
    ...(model ? [
      num("model_hfe", "Model's hFE", +model.hfe.toPrecision(3), { unit: "", ...typical, ...belowSheet(model) }),
      ...(leaks ? [num("model_leakage", "Model's leakage", +(model.leakage * 1e6).toPrecision(3), { unit: "µA", ...typical, hint: "Collector current, base open, as simulated." })] : []),
    ] : []),
    num("hfe", "Measured hFE", own ? +own.hfe.toPrecision(3) : "", { unit: "", ...only, hint: "Current gain, a plain number.",
      about: ["How many times the base current the collector carries: 85 means 1 µA in the base lets 85 µA through.",
        "On a 9 V tester, collector through 2.4 kΩ: the collector current with 2.2 MΩ from base to the supply, less the leakage, divided by the base current (about 4 µA)."] }),
    ...(leaks ? [num("leakage", "Measured leakage", own ? +((own.leakage ?? model?.leakage ?? 0) * 1e6).toPrecision(3) : "", { unit: "µA", ...only,
      hint: "Collector current, base open.",
      about: ["Germanium leaks; silicon hardly does. On the same tester, base open: the collector current (its volts across the 2.4 kΩ ÷ 2.4 kΩ). Let it settle; a finger's warmth raises it.",
        "Germanium: 100–200 µA is common, over 300 µA suspect, over 500 µA bad (Geofex); silicon reads about 0."] })] : []),
  ];
}

/**
 * Whether a transistor is meant to be off at rest (D-238): a rectifier or a switch is, so
 * Problems doesn't call it cut off and the Frequency curve doesn't doubt itself.
 * @param {any} part @returns {Field}
 */
function atRest(part) {
  return { ...select("at_rest", "At rest", part.off_by_design ? "off" : "", [["", "on, amplifying"], ["off", "off by design"]]),
    hint: "Off by design: a switch or a rectifier, off until a signal turns it on.",
    about: "A compressor's envelope rectifiers (the Dyna Comp's Q3, Q4) sit off with no signal. Marked off by design, being cut off at rest isn't a problem; fully on (saturated) still is." };
}

/**
 * A JFET's or MOSFET's drain target and the trimmer solved to reach it (round 3b, D-176).
 * @param {any} part @param {{circuit: any}} ctx @returns {Field[]}
 */
function drainFields(part, ctx) {
  const target = drainTarget(ctx.circuit, part.ref);
  const trimmers = ctx.circuit.parts.filter((/** @type {any} */ p) => p.type === "trimmer").map((/** @type {any} */ p) => [p.ref, p.ref]);
  return [
    num("drain_volts", "Drain target", target?.volts, { unit: "V", hint: "Solves the trimmer below so the drain sits here.", about: "It's the trimmer's target too: set or removed in either form, it's gone from both." }),
    select("drain_trimmer", "Bias trimmer", target?.trimmer ?? "", [["", "none"], ...trimmers]),
  ];
}

/**
 * A JFET's Idss and Vp (round 3b): the model's, or your own JFET's, measured; picked, so an
 * empty box can't quietly mean "the model". Measured ones start at the model's own.
 * @param {any} part @param {{idss: number, vp: number, range?: any} | undefined} model the model's
 * @returns {Field[]}
 */
function jfetSpecFields(part, model) {
  const own = part.measured ?? model;
  const only = { showIf: { field: "jfet_spec", not: "model" } };
  const typical = { showIf: { field: "jfet_spec", is: "model" }, readonly: true };
  return [
    { ...select("jfet_spec", "Idss and Vp", part.measured ? "measured" : "model", SPEC_CHOICES),
      hint: SPEC_HINT, about: unitHint(part.model, [["Idss", model?.range?.idss, 1e3, " mA"], ["Vp", model?.range?.vp, 1, " V"]]) },
    ...(model ? [
      num("model_idss", "Model's Idss", +(model.idss * 1e3).toPrecision(3), { unit: "mA", ...typical }),
      num("model_vp", "Model's Vp", +model.vp.toPrecision(3), { unit: "V", ...typical }),
    ] : []),
    num("idss", "Measured Idss", own ? +(own.idss * 1e3).toPrecision(3) : "", { unit: "mA", ...only, hint: "Drain current, gate and source grounded.", about: "Drain at 9 V through 100 Ω: its volts ÷ 100." }),
    num("vp", "Measured Vp", own ? +own.vp.toPrecision(3) : "", { unit: "V", ...only, hint: "Source voltage, gate grounded.", about: "1 MΩ from source to ground, drain at 9 V; a minus for an N-channel (−0.8)." }),
  ];
}

/**
 * The guitar input's fields (D-096): the pickup (a measured one, your own values, or
 * buffered: a buffer in front), its coil, the cable and the volume pot. Picking a measured
 * pickup fills the coil and the pot; the coil and cable hide while buffered, the volume
 * pot stays (D-134).
 * @param {any} part @param {PickupChoice[]} pickups @returns {Field[]}
 */
function guitarFields(part, pickups) {
  const has = part.source === "pickup";
  const chosen = has ? (part.pickup?.kind ?? "custom") : "ideal";
  const start = pickups[0] ?? { r: "6k", l: "2.5", c: "150p", volume: "250k" };
  const fills = Object.fromEntries(pickups.map((p) => [p.kind, { pickup_r: p.r, pickup_l: p.l, pickup_c: p.c, volume: p.volume }]));
  const only = { showIf: { field: "source", not: "ideal" } };
  return [
    { ...select("source", "Pickup", chosen, [["ideal", "Buffered"], ...pickups.map((p) => /** @type {[string, string]} */ ([p.kind, p.name])), ["custom", "Your own values"]]),
      fills, hint: "Its pickup loads the input. Buffered: nothing does.",
      about: "Buffered: a buffer pedal or an active pickup in front, so nothing loads the pickup and the guitar's volume only turns the level. It's also the no-guitar case: an ideal source, like a signal generator." },
    text("pickup_r", "Coil R", has ? part.pickup?.r : start.r, { unit: "Ω", ...only }),
    text("pickup_l", "Coil L", has ? part.pickup?.l : start.l, { unit: "H", ...only }),
    text("pickup_c", "Coil C", has ? part.pickup?.c : start.c, { unit: "F", ...only, hint: "The coil's own; the cable is below." }),
    num("cable", "Cable", has ? (part.cable ?? 0) : 3, { unit: "m", ...only, hint: "About 100 pF a metre." }),
    text("volume", "Volume pot", part.volume ?? "", { unit: "Ω", hint: "The guitar's volume pot. Empty: none. Turn it in Knobs." }),
    { ...select("stereo", "Input jack", part.stereo ? "stereo" : "mono", [["mono", "mono"], ["stereo", "stereo (battery switch)"]]),
      hint: "Stereo: its ring lug (R) is drawn.",
      about: "The guitar cable's sleeve joins the ring to ground, so a battery's − wired there is on only with a cable in." },
  ];
}

/**
 * Which field "try several values" sweeps for this part, if any.
 * @param {any} part @returns {"value" | "model" | null}
 */
export function sweepField(part) {
  if (["resistor", "capacitor", "inductor", "pot", "trimmer", "vsource", "amp"].includes(part.type)) return "value";
  if (["diode", "led", "bjt", "jfet", "mosfet", "opamp"].includes(part.type)) return "model";
  return null;
}

const SWEEP_PROMPTS = /** @type {Record<string, [string, string]>} */ ({
  resistor: ["resistances", "4k7, 10k, 22k"],
  capacitor: ["capacitances", "10n, 22n, 47n"],
  inductor: ["inductances", "400m, 500m, 660m"],
  pot: ["pot values", "100k, 250k, 500k"],
  trimmer: ["trimmer values", "10k, 50k, 100k"],
  vsource: ["supply voltages", "9, 12, 18"],
  amp: ["amp input impedances", "100k, 1M"],
});

/**
 * How the inspector's "compare" row asks for values: what's compared and an example that
 * fits the part (a DC source gets voltages, not resistor values).
 * @param {any} part @param {string[]} [models] model ids for this part type
 * @returns {{label: string, placeholder: string} | null}
 */
export function sweepPrompt(part, models = []) {
  const field = sweepField(part);
  if (!field) return null;
  const [what, example] = field === "model"
    ? ["models", models.slice(0, 3).join(", ") || "two or more models"]
    : SWEEP_PROMPTS[part.type];
  return { label: `Compare ${what}, overlaid on the plots (up to ${COMPARE_MAX})`, placeholder: `e.g. ${example}` };
}

/** @param {string} v @param {string} what @returns {number | null} */
function optionalNumber(v, what) {
  if (v.trim() === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`${what} must be a number.`);
  return n;
}

/**
 * A guitar's pickup from its form (D-096): buffered (a stiff source: no coil or cable; its
 * volume pot kept, D-134), or
 * a coil, cable and volume pot. A measured pickup keeps its `kind` while its coil values
 * are the guide's; changed, they're your own.
 * @param {(k: string) => string} v the form's trimmed values
 * @param {PickupChoice[]} pickups @returns {Record<string, unknown>}
 */
function guitarPatch(v, pickups) {
  if (v("source") === "ideal") return { source: null, pickup: null, cable: null, volume: v("volume") || null };
  const pickup = { r: v("pickup_r"), l: v("pickup_l"), c: v("pickup_c") };
  const guide = pickups.find((p) => p.kind === v("source"));
  const same = guide && guide.r === pickup.r && guide.l === pickup.l && guide.c === pickup.c;
  return {
    source: "pickup",
    pickup: { ...pickup, kind: same ? guide.kind : null },
    cable: optionalNumber(v("cable"), "Cable") ?? 0,
    volume: v("volume") || null,
  };
}

/**
 * The part as the open form has it so far, for building the form again when its Model
 * changes (the fields depend on the model: a germanium transistor's leakage, the model's
 * own values). What can't be read yet (an empty measured box) is left as the part had it;
 * the model is always the one picked. @param {any} part @param {Record<string, string>} values
 * @param {{pickups?: PickupChoice[]}} [ctx] @returns {any}
 */
export function draftFrom(part, values, ctx = {}) {
  try {
    const change = editFrom(part, values, ctx);
    return { ...part, ...change.patch, ref: change.ref };
  } catch {
    return { ...part, model: values.model ?? part.model };
  }
}

/**
 * Turn the inspector's form values back into an edit of the part. Throws an Error with a
 * plain message for input that can't be a number; everything else the server checks.
 * @param {any} part @param {Record<string, string>} values from the form, by field name
 * @param {{pickups?: PickupChoice[], batteries?: BatteryState[], inductors?: InductorPreset[], circuit?: any, zeners?: string[]}} [ctx] the measured pickups,
 *   to keep a guitar's `kind`, the battery's states, to keep its `state`, the measured
 *   inductors, to keep an inductor's `kind`, and the circuit and zener models' ids, for a
 *   diode's ref to follow its model (D-229)
 * @returns {Edit}
 */
export function editFrom(part, values, ctx = {}) {
  /** @type {Record<string, unknown>} */
  const patch = {};
  const v = (/** @type {string} */ k) => (values[k] ?? "").trim();
  for (const k of ["value", "label", "model", "taper", "kind"]) {
    if (k in values) patch[k] = v(k) === "" ? null : v(k);
  }
  for (const [k, what] of [["rating_w", "Rating"], ["rating_v", "Rating"]]) {
    if (k in values) patch[k] = optionalNumber(v(k), what);
  }
  const targeted = v("bias_node") !== "" && v("bias_volts") !== "";
  if ("rotation" in values && !targeted) { // a target turns it: what the box says doesn't count
    const r = optionalNumber(v("rotation"), "Rotation");
    if (r !== null && (r < ROTATION_RANGE.min || r > ROTATION_RANGE.max)) throw new Error(ROTATION_RANGE.message);
    patch.rotation = r === null ? null : r / 100;
  }
  if ("bias_node" in values || "bias_volts" in values) {
    // either field cleared takes the target off: the trimmer stays at its Rotation
    const volts = optionalNumber(v("bias_volts"), "Bias target");
    patch.bias_target = targeted ? { node: v("bias_node"), volts } : null;
  }
  if (part.type === "switch" && "position" in values) {
    // a type with fewer positions starts at its first (D-143)
    const positions = kindOf({ ...part, kind: v("kind") || part.kind || "spdt" })?.positions.length ?? 1;
    const at = Number(v("position")) || 0;
    patch.position = at < positions ? at : 0;
    // one name per position, or none; a type changed under them drops them
    const names = Object.keys(values).filter((k) => /^name_\d+$/.test(k)).sort((a, b) => Number(a.slice(5)) - Number(b.slice(5))).map((k) => v(k));
    patch.names = names.length === positions && names.some(Boolean) ? names : null;
  }
  if ("state" in values) { // a battery: a state's voltage, or yours (D-143)
    patch.volts = optionalNumber(v("volts"), "Voltage");
    if (patch.volts === null) throw new Error("Give the battery's voltage.");
    // a voltage typed over a state's is your own measurement
    const state = (ctx.batteries ?? []).find((s) => s.state === v("state"));
    patch.state = state && Math.abs(state.volts - Number(patch.volts)) < 1e-9 ? state.state : null;
    patch.resistance = v("resistance") === "" ? null : v("resistance");
  }
  if (part.type === "inductor" && "resistance" in values) { // a preset's values, or yours (D-173)
    patch.resistance = optionalNumber(v("resistance"), "Wire resistance");
    if (patch.resistance !== null && Number(patch.resistance) < 0) throw new Error("Wire resistance can't be below zero.");
    // values typed over a preset's are your own inductor
    const preset = (ctx.inductors ?? []).find((p) => p.kind === v("kind"));
    patch.kind = preset && preset.l === v("value") && Number(preset.r) === patch.resistance ? preset.kind : null;
  }
  if ("stereo" in values) patch.stereo = v("stereo") === "stereo" ? true : null;
  if ("jfet_spec" in values) {
    const own = v("jfet_spec") === "measured";
    const idss = own ? optionalNumber(v("idss"), "Measured Idss") : null;
    const vp = own ? optionalNumber(v("vp"), "Measured Vp") : null;
    if (own && (idss === null || vp === null)) throw new Error("Give your JFET's measured Idss and Vp, or pick the model's.");
    patch.measured = idss === null ? null : { idss: idss / 1e3, vp };
  }
  if ("bjt_spec" in values) {
    const own = v("bjt_spec") === "measured";
    const hfe = own ? optionalNumber(v("hfe"), "Measured hFE") : null;
    // no leakage box (a silicon model): the model's own, which is nothing to speak of
    const asked = "leakage" in values;
    const leak = own && asked ? optionalNumber(v("leakage"), "Measured leakage") : null;
    if (own && (hfe === null || (asked && leak === null))) throw new Error(asked ? "Give your transistor's measured hFE and leakage, or pick the model's." : "Give your transistor's measured hFE, or pick the model's.");
    patch.measured = hfe === null ? null : leak === null ? { hfe } : { hfe, leakage: leak / 1e6 };
  }
  if ("show_pins" in values) patch.show_pins = v("show_pins") === "on" ? true : null;
  if ("at_rest" in values) patch.off_by_design = v("at_rest") === "off" ? true : null;
  if ("source" in values) Object.assign(patch, guitarPatch(v, ctx.pickups ?? []));
  let drain = null;
  if ("drain_volts" in values) {
    const volts = optionalNumber(v("drain_volts"), "Drain target");
    const trimmer = v("drain_trimmer") || null;
    if (volts !== null && !trimmer) throw new Error("Pick the trimmer that sets the drain voltage.");
    drain = { trimmer, volts: trimmer ? volts : null };
  }
  // a ref left as it was follows a diode's model: D for a plain diode, Z for a zener (D-229)
  const typed = v("ref") && v("ref") !== part.ref ? v("ref") : ctx.circuit ? diodeRef(ctx.circuit, part, /** @type {string | undefined} */ (patch.model ?? undefined), ctx.zeners ?? []) : part.ref;
  // a chip's half or power unit keeps its letter: IC2 typed on IC1B is IC2B, and IC2A follows (D-140, D-179)
  const ref = (["opamp", "inverter", "ota"].includes(part.type) && part.half) || part.type === "powerunit" ? `${typed.replace(/[a-h]$/i, "")}${part.ref.slice(-1)}` : typed;
  return { patch, ref, drain };
}
