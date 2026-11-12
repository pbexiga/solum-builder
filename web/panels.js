/**
 * DOM for the panel contents: probe card (node or part view), DC table, knobs.
 * Data comes straight from the API; numbers with SI prefixes arrive pre-formatted.
 */

import { remember, remembered } from "./storage.js";
import { db, pct, rotationText, volts } from "./fixed.js";
import { forTheBuild, problemCounts, problemKey, splitDismissed } from "./problems.js";

/**
 * @param {string} tag @param {Record<string, string>} [attrs] @param {(Node | string)[]} [children]
 * @returns {HTMLElement}
 */
export function h(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}

/** @param {Array<[string, ...(Node | string)[]]>} rows @param {string[]} [head] */
function table(rows, head) {
  const body = rows.map(([label, ...cells]) => h("tr", {}, [h("th", {}, [label]), ...cells.map((c) => (c instanceof HTMLElement && c.tagName === "TD" ? c : h("td", {}, [c])))]));
  return h("table", { class: "readout" }, [
    ...(head ? [h("thead", {}, [h("tr", {}, head.map((t) => h("th", {}, [t])))])] : []),
    h("tbody", {}, body),
  ]);
}

/** A cell that tests and people can find by field name. @param {string} field @param {string} text */
const cell = (field, text) => h("td", { "data-field": field }, [text]);

/** @param {string | null | undefined} note */
const noteBlock = (note) => (note ? [h("p", { class: "note" }, [note])] : []);

/**
 * Stats rows for a net, side by side with the output.
 * @param {any} here @param {any} out stats objects (or undefined)
 */
function statsRows(here, out) {
  /** @type {Array<[string, (s: any) => string, string]>} */
  const fields = [
    ["Gain vs input", (s) => db(s.gain_db), "gain"],
    ["Polarity", (s) => s.polarity, "polarity"],
    ["Peak +", (s) => volts(s.peak_pos), "peak-pos"],
    ["Peak −", (s) => volts(s.peak_neg), "peak-neg"],
    ["Clipping", (s) => s.clipping.label, "clipping"],
    ["THD (2nd–8th)", (s) => pct(s.clipping.thd), "thd"],
    ["Asymmetry", (s) => pct(s.clipping.asymmetry), "asymmetry"],
  ];
  return fields.map(([label, fmt, field]) => {
    const row = /** @type {[string, ...(Node|string)[]]} */ ([label, cell(field, here ? fmt(here) : "—")]);
    if (out !== undefined) row.push(cell(`out-${field}`, out ? fmt(out) : "—"));
    return row;
  });
}

/**
 * The node view: DC, the scope's stats here and at the output, and the net's note.
 * @param {HTMLElement} el @param {any} view circuit view @param {any} run @param {string} net
 */
export function renderNodeView(el, view, run, net) {
  const out = view.probes.out;
  const info = view.nets[net] ?? {};
  const stats = run?.tran?.nodes[net]?.stats;
  const outStats = out && out !== net ? run?.tran?.nodes[out]?.stats : undefined;
  const head = ["", net, ...(outStats !== undefined ? [`${out} (output)`] : [])];
  /** @type {Array<[string, ...(Node|string)[]]>} */
  const rows = [["DC", cell("dc", volts(run?.op.voltages[net])), ...(outStats !== undefined ? [cell("out-dc", volts(run?.op.voltages[out]))] : [])]];
  if (stats) rows.push(...statsRows(stats, outStats));
  const z = run?.impedance;
  if (z?.[net]) rows.push(["Impedance", impedanceCell("impedance", z[net]), ...(outStats !== undefined ? [impedanceCell("out-impedance", z[out])] : [])]);
  const level = run?.tran ? h("p", { class: "empty" }, [`Scope stats at the ${run.tran.level} pick level (${volts(run.tran.amplitude, 1)} peak, ${run.tran.freq} Hz).`]) : h("p", { class: "empty" }, ["No guitar input in this circuit, so there's DC only."]);
  el.replaceChildren(
    h("div", { class: "probe-title" }, [h("span", { class: "name", "data-testid": "probe-name" }, [net]), h("span", { class: "kind" }, [info.rail ? "supply net" : "net"])]),
    ...noteBlock(info.note),
    table(rows, head),
    level,
  );
}

/**
 * The Probe pane's Impedance cell (D-127): looking into the net at 1 kHz with everything
 * connected; "—" with why when a stage is saturated at DC.
 * @param {string} field @param {{text: string, freq: number, saturated: string | null} | undefined} z
 */
function impedanceCell(field, z) {
  const td = cell(field, !z ? "—" : z.saturated ? "— (a stage is saturated)" : z.text);
  td.title = !z ? "" : z.saturated ?? `Looking into this net at ${z.freq / 1000} kHz, with everything connected (the guitar silent).`;
  return td;
}

/** @param {{up: number | null, down: number | null}} room @param {{up: number, down: number} | null} swing */
function headroomRows(room, swing) {
  /** @type {Array<[string, ...(Node|string)[]]>} */
  const rows = [];
  for (const dir of /** @type {const} */ (["up", "down"])) {
    const r = room[dir];
    const s = swing?.[dir];
    const ok = r == null || s == null || s < r;
    rows.push([dir === "up" ? "Room up" : "Room down", cell(`room-${dir}`, volts(r)), h("td", { class: ok ? "flag-ok" : "flag-warn", "data-field": `swing-${dir}` }, [s == null ? "—" : `swings ${volts(s)}`])]);
  }
  return rows;
}

/**
 * Type-specific rows and an optional device-curve slot.
 * @param {any} part /api/part result
 * @returns {{rows: Array<[string, ...(Node|string)[]]>, curve: boolean, hint?: string}}
 */
function partDetail(part) {
  const d = part.detail;
  switch (part.type) {
    case "resistor":
      return {
        rows: [
          ["Voltage across", cell("across", volts(d.across))],
          ["Current", cell("current", d.display.current)],
          ["Power", cell("power", d.display.power)],
          ["Rating", cell("rating", d.rating_w ? `${d.rating_w} W (${pct(d.load)} used)` : "not set")],
        ],
        curve: false,
      };
    case "capacitor":
      return {
        rows: [
          ["DC across", cell("across", volts(d.across))],
          ["Rating", cell("rating", d.rating_v ? `${d.rating_v} V (${pct(d.load)} used)` : "not set")],
          ...(d.polarised ? [/** @type {[string, Node]} */ (["Polarised", cell("polarised", "pin 1 is +")])] : []),
        ],
        curve: false,
        hint: d.curves ? "The Frequency panel shows the response on each side of it." : undefined,
      };
    case "inductor":
      return {
        rows: [
          ["DC across", cell("across", volts(d.across))],
          ["DC current", cell("current", d.display.current ?? "— (no wire resistance given)")],
        ],
        curve: false,
        hint: d.curves ? "The Frequency panel shows the response on each side of it." : undefined,
      };
    case "pot":
    case "trimmer":
      return {
        rows: [
          ["Rotation", cell("rotation", rotationText(d.rotation))],
          ["Taper", cell("taper", d.taper)],
          ["Pin 1 to wiper", cell("half-a", d.display.halves[0])],
          ["Wiper to pin 3", cell("half-b", d.display.halves[1])],
        ],
        curve: false,
        hint: d.solved ? "Rotation is solved for its bias target before every run." : undefined,
      };
    case "diode":
    case "led":
      return {
        rows: [
          ["DC across", cell("across", volts(d.dc.v))],
          ["DC current", cell("current", d.display.i)],
          ...(d.swing ? [/** @type {[string, Node]} */ (["Swing across", cell("swing", `${volts(Math.min(...d.swing.v))} to ${volts(Math.max(...d.swing.v))}`)])] : []),
        ],
        curve: true,
        hint: "I-V curve of the model with the operating swing traced on it; the dot is the DC point.",
      };
    case "bjt":
      return {
        rows: [
          ["Type", cell("polarity", d.polarity === "p" ? "PNP" : "NPN")],
          ["Vbe", cell("vbe", volts(d.vbe, 3))],
          ["Vce", cell("vce", volts(d.vce))],
          ["Ic", cell("ic", d.display.ic ?? "—")],
          ["Ib", cell("ib", d.display.ib ?? "—")],
          ["β (Ic / Ib)", cell("beta", d.beta == null ? "—" : String(Math.round(d.beta)))],
          ["Judged at", cell("terminal", d.stage.follower ? "emitter (follower)" : "collector")],
          ...headroomRows(d.stage.headroom, d.stage.swing),
        ],
        curve: true,
        hint: "Collector current against Vbe at this Vce; the dot is the operating point.",
      };
    case "jfet":
      return {
        rows: [
          ["Type", cell("polarity", d.polarity === "p" ? "P-channel" : "N-channel")],
          ["Vgs", cell("vgs", volts(d.vgs, 3))],
          ["Vds", cell("vds", volts(d.vds))],
          ["Pinch-off Vp", cell("vp", volts(d.vp))],
          ["Id", cell("id", d.display.id ?? "—")],
          ["Judged at", cell("terminal", d.stage.follower ? "source (follower)" : "drain")],
          ...headroomRows(d.stage.headroom, d.stage.swing),
        ],
        curve: true,
        hint: "Drain current against Vgs at this Vds; the dot is the operating point.",
      };
    case "mosfet":
      return {
        rows: [
          ["Type", cell("polarity", d.depletion ? "N-channel, depletion" : "N-channel, enhancement")],
          ["Vgs", cell("vgs", volts(d.vgs, 3))],
          ["Vds", cell("vds", volts(d.vds))],
          ["Threshold VTO", cell("vto", volts(d.vto))],
          ["Id", cell("id", d.display.id ?? "—")],
          ["Judged at", cell("terminal", d.stage.follower ? "source (follower)" : "drain")],
          ...headroomRows(d.stage.headroom, d.stage.swing),
        ],
        curve: true,
        hint: "Drain current against Vgs at this Vds, on a log scale (below the threshold it falls off steeply, not to zero); the dot is the operating point.",
      };
    case "opamp":
      if (d.unused) {
        return { rows: [["Half", cell("unused", `${d.chip}'s unused half: not simulated. Problems says how to wire it.`)]], curve: false };
      }
      return {
        rows: [
          ["Output DC", cell("out", volts(d.out))],
          ["Supply", cell("rails", `${volts(d.rails[0])} to ${volts(d.rails[1])}`)],
          ["+ input", cell("in-plus", volts(d.inputs["+"]))],
          ["− input", cell("in-minus", volts(d.inputs["-"]))],
          ["Inputs", h("td", { class: d.input_outside ? "flag-warn" : "flag-ok", "data-field": "common-mode" }, [`${d.input_outside ? "outside" : "inside"} ${volts(d.input_limits[0])} to ${volts(d.input_limits[1])} (${d.limits_from === "datasheet" ? "the datasheet's input range" : "a rule of thumb: 2 V from each rail"})`])],
          ...headroomRows(d.to_rails, d.swing),
        ],
        curve: false,
      };
    case "switch":
      return { rows: [["Position", cell("position", `${d.positions[d.position]} (${d.position + 1} of ${d.positions.length})`)]], curve: false };
    default:
      return { rows: [], curve: false };
  }
}

/**
 * The part view (SPEC §2). Returns the element for the device curve, if the part has one.
 * @param {HTMLElement} el @param {any} part /api/part result @param {(net: string) => void} onNet
 * @returns {HTMLElement | null}
 */
export function renderPartView(el, part, onNet) {
  const pinRows = Object.entries(part.pins).map(([pin, info]) => {
    const row = h("tr", { class: "clickable", "data-net": /** @type {any} */ (info).net }, [
      h("th", {}, [`pin ${pin}`]),
      h("td", {}, [/** @type {any} */ (info).net]),
      h("td", {}, [volts(/** @type {any} */ (info).dc)]),
    ]);
    row.addEventListener("click", () => onNet(/** @type {any} */ (info).net));
    return row;
  });
  const detail = partDetail(part);
  const curveEl = detail.curve ? h("div", { class: "plot subplot", id: "device-plot" }) : null;
  el.replaceChildren(
    h("div", { class: "probe-title" }, [h("span", { class: "name", "data-testid": "probe-name" }, [part.ref]), h("span", { class: "kind" }, [`${part.type} · ${part.text}`])]),
    ...noteBlock(part.note),
    table(detail.rows),
    ...(detail.hint ? [h("p", { class: "empty" }, [detail.hint])] : []),
    ...(curveEl ? [curveEl] : []),
    h("table", { class: "readout subplot" }, [h("thead", {}, [h("tr", {}, [h("th", {}, ["Pin"]), h("th", {}, ["Net"]), h("th", {}, ["DC"])])]), h("tbody", {}, pinRows)]),
  );
  return curveEl;
}

/**
 * Every net's DC voltage (rails first), solved trimmers, and saturated stages.
 * @param {HTMLElement} el @param {any} view @param {any} run @param {(net: string) => void} onNet
 */
export function renderDc(el, view, run, onNet) {
  const voltages = run?.op.voltages ?? {};
  const isRail = (/** @type {string} */ n) => view.nets[n]?.rail ?? !(n in view.nets);
  // supplies first, then the guitar's and the amp's nets, so they're easy to find (the
  // user, D-095): DC on either reaches the guitar or the amp
  const rank = (/** @type {string} */ n) => (isRail(n) ? 0 : n === view.probes?.in ? 1 : n === view.probes?.out ? 2 : 3);
  const nets = Object.keys(voltages).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  const rows = nets.map((net) => {
    const end = ["", "from guitar", "to amp", ""][rank(net)];
    const name = [net, ...(end ? [h("span", { class: "dc-end" }, [` ${end}`])] : [])];
    const row = h("tr", { class: `clickable${isRail(net) ? " rail" : ""}`, "data-net": net }, [h("th", {}, name), h("td", {}, [volts(voltages[net])])]);
    row.addEventListener("click", () => onNet(net));
    return row;
  });
  const bias = Object.entries(run?.op.bias ?? {}).map(([ref, rot]) => h("p", { class: "empty" }, [`${ref} solved to ${rotationText(/** @type {number} */ (rot))} for its bias target.`]));
  // every net is listed, so the table scrolls past about a Harmonics plot's height (the user, D-095)
  el.replaceChildren(...bias, h("div", { class: "dc-list" }, [h("table", { class: "readout" }, [h("tbody", {}, rows)])]));
}

/**
 * Knobs for pots, selectors for switches.
 * @param {HTMLElement} el @param {any[]} controls
 * @param {Record<string, number>} values current rotation/position per ref
 * @param {(ref: string, value: number) => void} onChange
 * @param {(ref: string) => void} [onGrab] a knob was grabbed (before it moves: the live curve, D-081)
 * @param {(ref: string | null) => void} [onHover] the pointer is over a knob (null: it left), to shade where it acts (D-102)
 */
export function renderKnobs(el, controls, values, onChange, onGrab = () => {}, onHover = () => {}) {
  if (!controls.length) {
    el.replaceChildren(h("p", { class: "empty" }, ["This circuit has no pots or switches."]));
    return;
  }
  el.replaceChildren(...controls.map((c) => knobControl(c, values[c.ref], onChange, onGrab, onHover)));
}

/**
 * One knob (a pot) or selector (a switch), as the Knobs & switches pane shows it; also
 * what a pot's chip on the stage chain opens (D-122: the same control, not a copy).
 * @param {any} c the control (`view.controls`) @param {number} value its rotation or position
 * @param {(ref: string, value: number) => void} onChange
 * @param {(ref: string) => void} [onGrab] @param {(ref: string | null) => void} [onHover]
 * @returns {HTMLElement}
 */
export function knobControl(c, value, onChange, onGrab = () => {}, onHover = () => {}) {
  if (c.kind === "pot") {
    const meta = h("span", { class: "meta" }, [`${rotationText(value)} · ${c.value} ${c.taper}`]);
    const input = /** @type {HTMLInputElement} */ (h("input", { type: "range", min: "0", max: "100", step: "1", value: String(Math.round(value * 100)), "aria-label": c.label, "data-ref": c.ref }));
    input.addEventListener("pointerdown", () => onGrab(c.ref));
    input.addEventListener("focus", () => onGrab(c.ref)); // keyboard
    input.addEventListener("input", () => {
      const rotation = Number(input.value) / 100;
      meta.textContent = `${rotationText(rotation)} · ${c.value} ${c.taper}`;
      onChange(c.ref, rotation);
    });
    return inUse(h("div", { class: "knob", "data-knob": c.ref }, [h("span", { class: "name" }, [`${c.label}`]), meta, input]), c.ref, onHover);
  }
  const names = Array.isArray(c.positions) ? c.positions : Array.from({ length: c.positions }, (_, i) => String(i + 1));
  const buttons = names.map((/** @type {string} */ name, /** @type {number} */ i) => {
    // what the position joins, on hover (D-143): "1: A2–A1, B2–B1"
    const title = c.contacts?.[i] ? { title: c.contacts[i] } : {};
    const b = h("button", { type: "button", role: "radio", "aria-checked": String(i === value), "data-ref": c.ref, "data-position": String(i), ...title }, [name]);
    b.addEventListener("click", () => {
      for (const other of b.parentElement?.children ?? []) other.setAttribute("aria-checked", String(other === b));
      onChange(c.ref, i);
    });
    return b;
  });
  return inUse(h("div", { class: "knob", "data-knob": c.ref }, [h("span", { class: "name" }, [c.label]), h("span", { class: "meta" }, [c.ref]), h("span", { class: "segmented", role: "radiogroup", "aria-label": c.label }, buttons)]), c.ref, onHover);
}

/**
 * Tell `onHover` while a knob is in use (D-127): hovered, held (a drag that leaves it
 * still counts) or turned from the keyboard (until focus moves on); null once it isn't.
 * The app lights its part on the canvas and shades its band on the curve.
 * @param {HTMLElement} knob @param {string} ref @param {(ref: string | null) => void} onHover
 * @returns {HTMLElement} the knob
 */
function inUse(knob, ref, onHover) {
  let over = false;
  let held = false;
  let keyed = false;
  let was = false;
  const tell = () => {
    const now = over || held || keyed;
    if (now !== was) onHover(now ? ref : null);
    was = now;
  };
  knob.addEventListener("pointerenter", () => { over = true; tell(); });
  knob.addEventListener("pointerleave", () => { over = false; tell(); });
  knob.addEventListener("pointerdown", () => {
    held = true;
    tell();
    window.addEventListener("pointerup", () => { held = false; tell(); }, { once: true });
  });
  knob.addEventListener("keydown", () => { keyed = true; tell(); });
  knob.addEventListener("focusout", () => { keyed = false; tell(); });
  return knob;
}

/**
 * Move a knob already drawn to `value` without telling anyone (another control moved it:
 * a chip's on the stage chain, D-122). @param {HTMLElement} el where the knobs are
 * @param {any} c the control @param {number} value
 */
export function showKnob(el, c, value) {
  const knob = el.querySelector(`[data-knob="${CSS.escape(c.ref)}"]`);
  if (!knob) return;
  if (c.kind === "pot") {
    const input = /** @type {HTMLInputElement | null} */ (knob.querySelector("input"));
    if (input) input.value = String(Math.round(value * 100));
    const meta = knob.querySelector(".meta");
    if (meta) meta.textContent = `${rotationText(value)} · ${c.value} ${c.taper}`;
  } else {
    for (const b of knob.querySelectorAll("[data-position]")) b.setAttribute("aria-checked", String(Number(/** @type {HTMLElement} */ (b).dataset.position) === value));
  }
}

/**
 * The Frequency panel's readings for the curve at `net` (D-081): one cell per measure,
 * the reason in a tooltip when the curve hasn't got it. Empty rows hide the strip.
 * @param {HTMLElement} el @param {Array<{label: string, text: string, title: string}>} rows @param {string} net
 */
export function renderReadings(el, rows, net) {
  el.hidden = !rows.length;
  el.classList.remove("stale");
  el.replaceChildren(
    ...(rows.length ? [h("span", { class: "readings-net" }, [net])] : []),
    ...rows.map((r) => h("span", { class: "reading", title: r.title, "data-reading": r.label }, [h("span", { class: "label" }, [r.label]), h("span", { class: "value" }, [r.text])])),
  );
}

/**
 * The sweep's runs side by side as numbers (D-067): DC, gain at 1 kHz and peaks at the
 * net shown, a note when the curves overlap, and the bias points that moved most.
 * @param {HTMLElement} el @param {any} sweep
 * @param {ReturnType<typeof import("./series.js").sweepSummary>} summary @param {string} net
 */
export function renderSweepSummary(el, sweep, summary, net) {
  const head = ["", "DC", "Gain at 1 kHz", "Peak + / −"];
  const rows = summary.rows.map((r) => [
    `${sweep.ref} = ${r.value}`,
    volts(r.dc),
    r.gain == null ? "—" : db(r.gain),
    r.peak ? `${volts(r.peak[0])} / ${volts(r.peak[1])}` : "—",
  ]);
  const table = h("table", { class: "readout sweep-table" }, [
    h("thead", {}, [h("tr", {}, head.map((t) => h("th", {}, [t])))]),
    h("tbody", {}, rows.map((cells) => h("tr", {}, cells.map((c) => h("td", {}, [c]))))),
  ]);
  const notes = [];
  if (summary.overlap) {
    notes.push(h("p", { class: "note" }, [`The ${sweep.values.length} runs lie on top of each other at ${net}: changing ${sweep.ref} makes no visible difference here.`]));
  }
  if (summary.shifts.length) {
    notes.push(h("p", { class: "note" }, [
      "DC that moved most: ",
      summary.shifts.map((s) => `${s.net} ${s.values.map((v) => volts(v, 1)).join(" → ")}`).join("; "),
    ]));
  }
  el.replaceChildren(table, ...notes);
}

const SEVERITY = { error: "Error", warning: "Warning", info: "Note" };
const DISMISSED_OPEN = "#dismissed"; // in `opened`: the Dismissed section is open (no problem key starts with #)
const BUILD_OPEN = "#build"; // and the Before you build section (D-203)

/**
 * The Problems panel: one row per problem (severity, title, message; why and fix on
 * opening it), errors first as the server sends them. A problem can be dismissed (its
 * Dismiss… button); dismissed ones are listed after the rest, under Dismissed, each with
 * its reason and Bring back (D-176). Returns the heading's count text (not counting the
 * dismissed).
 * @param {HTMLElement} el
 * @param {{problems: import("./problems.js").Problem[], checked_op: boolean} | null} result
 * @param {(problem: import("./problems.js").Problem) => void} onPick a click on a problem
 * @param {Set<string>} opened keys of the rows left open, and of the Dismissed section (kept up to date here)
 * @param {{dismissed?: import("./problems.js").Dismissal[], onDismiss?: (p: import("./problems.js").Problem) => void,
 *   onRestore?: (p: import("./problems.js").Problem) => void}} [dismissal] the circuit's dismissals, and what the buttons do
 * @returns {string}
 */
export function renderProblems(el, result, onPick, opened, dismissal = {}) {
  if (!result) {
    el.replaceChildren();
    return "";
  }
  const { checked_op: checked } = result;
  const split = splitDismissed(result.problems, dismissal.dismissed);
  const { dismissed } = split;
  const active = split.active.filter((p) => !forTheBuild(p));
  const notes = split.active.filter(forTheBuild);
  const scope = checked ? "" : " (the drawing only: the circuit wasn't simulated)";
  /** @param {import("./problems.js").Problem} p @param {Node[]} more under why and fix */
  const row = (p, more) => {
    const where = [...p.refs, ...p.nets].join(", ");
    const head = h("summary", {}, [
      h("span", { class: `severity sev-${p.severity}` }, [SEVERITY[p.severity]]),
      h("span", { class: "problem-title" }, [p.title]),
      ...(where ? [h("span", { class: "problem-where" }, [where])] : []),
    ]);
    const body = h("div", { class: "problem-body" }, [
      h("p", { class: "problem-message" }, [p.message]),
      h("p", { class: "note" }, [h("b", {}, ["Why: "]), p.why]),
      h("p", { class: "note" }, [h("b", {}, ["Fix: "]), p.fix]),
      ...more,
    ]);
    const item = /** @type {HTMLDetailsElement} */ (h("details", { class: "problem", "data-rule": p.rule, "data-key": problemKey(p) }, [head, body]));
    item.open = opened.has(problemKey(p));
    item.addEventListener("toggle", () => (item.open ? opened.add(problemKey(p)) : opened.delete(problemKey(p))));
    head.addEventListener("click", () => onPick(p));
    return item;
  };
  /** @param {string} label @param {string} cls @param {() => void} [run] */
  const action = (label, cls, run) => {
    const b = h("button", { type: "button", class: `link ${cls}` }, [label]);
    b.addEventListener("click", () => run?.());
    return h("p", { class: "problem-actions" }, [b]);
  };
  const dismissable = (/** @type {import("./problems.js").Problem} */ p) => (dismissal.onDismiss ? [action("Dismiss\u2026", "problem-dismiss", () => dismissal.onDismiss?.(p))] : []);
  const rows = active.map((p) => row(p, dismissable(p)));
  const gone = dismissed.map(({ problem: p, reason }) =>
    row(p, [
      h("p", { class: "note problem-reason" }, [h("b", {}, ["Dismissed: "]), reason || "no reason given."]),
      action("Bring back", "problem-restore", () => dismissal.onRestore?.(p)),
    ]),
  );
  /** @type {HTMLElement[]} Before you build and Dismissed, each kept open across re-checks as a row is */
  const shelf = [];
  /** @param {string} id @param {string} title @param {HTMLElement[]} items @param {string} key */
  const section = (id, title, items, key) => {
    const box = /** @type {HTMLDetailsElement} */ (h("details", { class: "dismissed", id }, [h("summary", {}, [`${title} \u00b7 ${items.length}`]), h("div", { class: "problem-list" }, items)]));
    box.open = opened.has(key);
    box.addEventListener("toggle", () => (box.open ? opened.add(key) : opened.delete(key)));
    shelf.push(box);
  };
  if (notes.length) section("problems-build", "Before you build", notes.map((p) => row(p, dismissable(p))), BUILD_OPEN);
  if (gone.length) section("problems-dismissed", "Dismissed", gone, DISMISSED_OPEN);
  if (!active.length) {
    el.replaceChildren(h("p", { class: "empty" }, [`No problems found${scope}${gone.length ? ` besides the ${gone.length} dismissed` : ""}.`]), ...shelf);
    return "";
  }
  // about six rows show; more scroll inside the list (the user, D-095)
  el.replaceChildren(h("div", { class: "problem-list" }, rows), ...shelf, ...(checked ? [] : [h("p", { class: "empty" }, [`Checked${scope}.`])]));
  return problemCounts(active);
}

const LARGE_MIN = 320; // px: a large view's plot, at least
const CANVAS_MIN = 200; // px of canvas an open large view leaves above it, or it shrinks to its bar (D-127)

/** A large view's height (`--large-h` in app.css, D-127). */
function largeHeight() {
  return parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--large-h")) || 560;
}

/**
 * @typedef {{button: HTMLButtonElement, expanded: () => boolean, set: (on: boolean) => void,
 *   collapse: () => void, lock: (reason: string | null) => void,
 *   plotHeight: (reserved: number) => number | undefined, bar: HTMLElement}} LargeView
 */

/**
 * A pane's large view, the one way every pane has it (D-107): its Expand / Collapse button
 * (class `large-toggle`), Esc to shrink it to its bar, and `setLargeView` underneath. In the panel the
 * button is Expand at the right of the pane's title bar, so a shut pane can go large too;
 * large, it's Collapse pinned at the title bar's far right, as a shrunk bar's Collapse
 * (D-110, round 3 of D-127). The pane lays its body out with the
 * `large-split` / `large-side` classes (a main column, a side column whose notes sit at the
 * bottom; the side column scrolls, the view never does).
 * `onChange(on)`: the view just went large or back (switch layer sets, redraw at the new
 * height). `onShow`: it opened again from its bar (redraw at full width). Esc shrinks the
 * open view to its bar, as a click on its title does: it never collapses one, so pending
 * edits are only asked about when the view is collapsed (D-123).
 * `canCollapse`: false holds Collapse (pending edits; `lock` says why on the buttons).
 * `onShrink(shrunk)`: the view shrank to its bar (true) or came back from it or collapsed
 * (false); `bar` is a place on the bar for controls kept usable there (the Audio pane's
 * Render, play and Dry / Pedal / Snapshot): the pane moves them in and out. `pinBar`: its
 * bar is always the bottom one while shrunk (D-111).
 * @param {HTMLDetailsElement} el
 * @param {{id: string, name: string, what: string, tools: HTMLElement, onChange?: (on: boolean) => void, onShow?: () => void,
 *   canCollapse?: () => boolean, onShrink?: (shrunk: boolean) => void, pinBar?: boolean}} opts `name` sets `body.dataset[name + "Expanded"]`;
 *   `what` is the button's tooltip ("A large view of the curve, over the canvas")
 * @returns {LargeView}
 */
export function largeView(el, opts) {
  let on = false;
  let locked = /** @type {string | null} */ (null);
  const button = /** @type {HTMLButtonElement} */ (h("button", { type: "button", id: opts.id, class: "large-toggle", title: opts.what }, ["Expand"]));
  const summary = /** @type {HTMLElement} */ (el.querySelector(":scope > summary"));
  // controls a shrunk bar keeps; a click there doesn't open the view
  const bar = h("span", { class: "large-bar-tools" });
  bar.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
  });
  summary.append(bar);
  if (opts.pinBar) el.dataset.pinBar = "true";
  let shrunk = false;
  /** @param {boolean} now */
  const shrinking = (now) => {
    if (now === shrunk) return;
    shrunk = now;
    opts.onShrink?.(now);
  };
  const canCollapse = () => !locked && (opts.canCollapse?.() ?? true);
  const label = () => {
    button.textContent = on ? "Collapse" : "Expand";
    button.disabled = !!locked;
    button.title = locked ?? (on ? "Back to the panel" : opts.what);
    // in the panel, on the title bar left of the grip; large, pinned at the title bar's far
    // right, where a shrunk bar has its Collapse (round 3)
    summary.insertBefore(button, bar);
  };
  /** @param {boolean} next */
  function set(next) {
    if (next === on || (!next && !canCollapse())) return;
    on = next;
    if (!on) shrinking(false);
    setLargeView(el, on, { onCollapse: () => set(false), onShow: opts.onShow, onShrink: shrinking });
    label();
    document.body.dataset[`${opts.name}Expanded`] = String(on);
    opts.onChange?.(on);
  }
  button.addEventListener("click", (e) => {
    e.preventDefault(); // on the title bar, a click would open or shut the pane too
    e.stopPropagation();
    set(!on);
  });
  label();
  document.addEventListener("keydown", (e) => {
    // Esc is the open view's; an open menu takes it first
    if (e.key !== "Escape" || !on || !el.open || document.querySelector(".menu")) return;
    el.open = false;
  });
  /** @type {LargeView} */
  const view = {
    button,
    expanded: () => on,
    set,
    collapse: () => set(false),
    lock(reason) {
      locked = reason;
      lockLargeView(el, reason);
      label();
    },
    plotHeight: (reserved) => (on ? Math.max(LARGE_MIN, largeHeight() - reserved) : undefined),
    bar,
  };
  largeById.set(el.id, view);
  return view;
}

/** @type {(() => void) | null} closes the ⓘ pop-up that's open (one at a time) */
let infoOpen = null;

/**
 * A pane's ⓘ (D-109): what the pane shows and how to read it, kept out of the way. The
 * button sits in the pane's title bar after its name (so it's there in the panel and in
 * the large view alike). See `infoButton`.
 * @param {HTMLDetailsElement} el the pane @param {string} title its name, the pop-up's heading
 * @param {() => Array<string | Node>} content
 * @returns {{button: HTMLButtonElement, close: () => void}}
 */
export function paneInfo(el, title, content) {
  const summary = /** @type {HTMLElement} */ (el.querySelector(":scope > summary"));
  const info = infoButton(title, content);
  summary.insertBefore(info.button, summary.firstChild?.nextSibling ?? null); // right after the name
  return info;
}

/**
 * An ⓘ button and its pop-up (D-109, D-127): a click opens the explanations under it, like
 * History's. Make it once and put the button where it goes (again after a redraw): its
 * listeners stay for the page's life. See `infoPopup`.
 * @param {string} title the pop-up's heading
 * @param {() => Array<string | Node>} content
 * @returns {{button: HTMLButtonElement, close: () => void}}
 */
export function infoButton(title, content) {
  const popup = infoPopup();
  return { button: popup.button(title, content), close: popup.close };
}

/**
 * One ⓘ pop-up shared by any number of ⓘ buttons (a list's rows, 9c), so buttons made
 * again on each redraw add nothing to the page. A click on a button opens its explanations
 * under it; a click outside or Esc (before any large view's or sheet's Esc) closes them; on
 * a scroll they follow their button, and close once the button is out of sight. Make it
 * once: its listeners stay for the page's life. `content` is built each time it opens, so
 * it says what's on screen now (a chart, a mode); a string is a paragraph, a node goes in
 * as it is.
 * @param {{inSheet?: boolean}} [opts] `inSheet`: its buttons are in a sheet, so it shows over it
 * @returns {{button: (title: string, content: () => Array<string | Node>, hint?: string) => HTMLButtonElement, close: () => void}}
 */
export function infoPopup(opts = {}) {
  const pop = h("div", { class: opts.inSheet ? "info-pop in-sheet" : "info-pop", role: "dialog", hidden: "" });
  document.body.append(pop);
  const GAP = 6;
  const EDGE = 16;
  /** @type {HTMLButtonElement | null} the button whose pop-up is open */
  let at = null;

  /** @param {HTMLButtonElement} button @param {string} title @param {() => Array<string | Node>} content */
  function open(button, title, content) {
    infoOpen?.();
    pop.setAttribute("aria-label", `About ${title}`);
    pop.replaceChildren(
      h("h4", {}, [title]),
      ...content().map((c) => (typeof c === "string" ? h("p", { class: "note" }, [c]) : c)),
    );
    pop.hidden = false;
    at = button;
    button.setAttribute("aria-expanded", "true");
    place();
    infoOpen = close;
  }

  /** Under the button, kept on screen; above it when there's more room there. */
  function place() {
    if (!at) return;
    const r = at.getBoundingClientRect();
    const width = Math.min(400, window.innerWidth - 2 * EDGE);
    pop.style.width = `${width}px`;
    pop.style.left = `${Math.min(Math.max(r.left - 8, EDGE), window.innerWidth - width - EDGE)}px`;
    const below = window.innerHeight - r.bottom - GAP - EDGE;
    const above = r.top - GAP - EDGE;
    const down = below >= Math.min(pop.scrollHeight, 240) || below >= above;
    pop.style.maxHeight = `${down ? below : above}px`;
    pop.style.top = down ? `${r.bottom + GAP}px` : "";
    pop.style.bottom = down ? "" : `${window.innerHeight - r.top + GAP}px`;
  }

  function close() {
    if (pop.hidden) return;
    pop.hidden = true;
    at?.setAttribute("aria-expanded", "false");
    at = null;
    if (infoOpen === close) infoOpen = null;
  }

  /** @param {string} title @param {() => Array<string | Node>} content @param {string} [hint] its tooltip */
  function button(title, content, hint = `About ${title}: what it shows and how to read it`) {
    const b = /** @type {HTMLButtonElement} */ (h("button", {
      type: "button", class: "info-button", "aria-label": `About ${title}`, title: hint, "aria-expanded": "false",
    }, ["i"]));
    b.addEventListener("click", (e) => {
      e.preventDefault(); // a button in a <summary> would open or shut the pane
      e.stopPropagation();
      if (at === b) close();
      else open(b, title, content);
    });
    return b;
  }

  document.addEventListener("pointerdown", (e) => {
    const t = /** @type {Node} */ (e.target);
    if (!pop.contains(t) && !at?.contains(t)) close();
  });
  // in the capture phase on window: Esc shuts the pop-up, not the large view or sheet under it
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || pop.hidden) return;
    e.stopImmediatePropagation();
    close();
  }, true);
  // a scroll elsewhere: it follows its button, and closes once the button is out of sight
  document.addEventListener("scroll", (e) => {
    if (pop.hidden || !at || pop.contains(/** @type {Node} */ (e.target))) return;
    const r = at.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight || !r.width) close();
    else place();
  }, true);
  return { button, close };
}

/** The large views out now (the Frequency panel, the Audio spectrum…); a shrunk one moves to the end as it shrinks. */
const largeViews = new Set();

/** Each pane's large view by the pane's id, to put them back after a reload. @type {Map<string, LargeView>} */
const largeById = new Map();
const LARGE_KEY = "solum.large"; // the panes out as large views, in their bars' order (D-121)

/** Remember which panes are out as large views. */
function saveLargeViews() {
  // the bars from the bottom up, then the open view: the order they'd stack in, all shrunk
  const views = [...largeViews];
  remember(LARGE_KEY, [...views.filter((v) => !v.open), ...views.filter((v) => v.open)].map((v) => v.id));
}

/**
 * Put back the large views that were out before a reload, each shrunk to its bar, in the
 * same order (D-121). Run once at start, after the panes have made their views.
 */
export function restoreLargeViews() {
  const saved = remembered(LARGE_KEY);
  const ids = Array.isArray(saved) ? saved : [];
  const known = ids.filter((id) => largeById.has(id));
  for (const id of known) largeById.get(id)?.set(true);
  // then each shrunk (or, shrunk already as the next went large, moved on) in the saved
  // order, so the bars stack as they did
  for (const id of known) {
    const el = /** @type {HTMLDetailsElement} */ (document.getElementById(id));
    if (!largeViews.has(el)) continue; // held in its panel
    if (el.open) {
      el.open = false;
      shrunkNow(el);
    } else {
      largeViews.delete(el);
      largeViews.add(el);
    }
  }
  stackLargeViews();
  saveLargeViews();
}

/**
 * Show `el` (a `<details>`) as a large view over the canvas, or put it back (D-102): the
 * one way any pane goes large. One is open at a time: opening one (Expand, or its bar)
 * shrinks the open one to its title bar. Shrunk, a view is ringed in the accent so it
 * isn't missed, and the bars stack at the bottom with the open view standing on them, so
 * every bar shows however many panes are out; a click on a bar switches to it. A shrunk
 * bar has a Collapse button pinned right (`lockLargeView` greys it).
 * `onCollapse`: the bar's Collapse was clicked (the pane puts itself back, calling this
 * with `on` false); `onShow`: the view has just opened from its bar and been laid out
 * again, full width (redraw its plots now: drawn on the toggle itself they'd take the
 * bar's width).
 * @param {HTMLDetailsElement} el @param {boolean} on
 * @param {{onCollapse?: () => void, onShow?: () => void}} [hooks]
 */
function setLargeView(el, on, hooks = {}) {
  el.classList.toggle("large-view", on);
  el.classList.toggle("expanded", on);
  if (on) {
    largeViews.add(el);
    // @ts-ignore: as shown so far; opening it from shut is handled on its toggle, as before
    el._shownOpen = el.open;
    el.open = true;
    shrinkOthers(el);
    // @ts-ignore: the hooks and the bar's button live on the element, bound once
    el._largeHooks = hooks;
    // @ts-ignore
    if (!el._largeToggle) {
      el.addEventListener("toggle", () => shrunkNow(el));
      // a click on the title switches at once, in the click: waiting for the toggle event
      // drew each step (this one open, the others shrinking, the bars re-stacked) as a
      // flicker (D-116)
      el.querySelector(":scope > summary")?.addEventListener("click", (e) => {
        if (!largeViews.has(el) || e.defaultPrevented) return;
        e.preventDefault();
        el.open = !el.open;
        shrunkNow(el);
      });
      collapseButton(el);
      // @ts-ignore
      el._largeToggle = true;
    }
  } else {
    largeViews.delete(el);
    el.style.bottom = el.style.left = el.style.right = "";
    el.open = true; // back in its panel open, even from a shrunk bar
  }
  stackLargeViews();
  saveLargeViews();
}

const LARGE_EDGE = 16; // px from the window's bottom
const LARGE_GAP = 8; // px between stacked bars

/** Shrink every open large view to its bar, as Esc does to the open one (D-127). */
export function shrinkLargeViews() {
  for (const el of [...largeViews]) {
    if (!el.open) continue;
    el.open = false;
    shrunkNow(el); // at once, not on the toggle event, as a click on its title
  }
}

/**
 * A large view was shrunk or opened by its title: one just shrunk goes to the end of the
 * order, so its bar lands above the bars already there and none of them moves.
 * @param {HTMLDetailsElement} el
 */
function shrunkNow(el) {
  if (!largeViews.has(el)) return;
  // @ts-ignore: done already, in the click or `shrinkOthers` (the toggle event comes later)
  if (el._shownOpen === el.open) return;
  // @ts-ignore
  el._shownOpen = el.open;
  if (el.open) shrinkOthers(el); // one open at a time: its bar was clicked
  else {
    largeViews.delete(el);
    largeViews.add(el);
  }
  stackLargeViews();
  saveLargeViews();
  // @ts-ignore
  el._largeHooks?.onShrink?.(!el.open);
  // @ts-ignore
  if (el.open) el._largeHooks?.onShow?.(); // laid out full width again: redraw
}

/**
 * The Collapse button on a shrunk view's bar, pinned right: puts the pane back in its
 * panel without opening the view first. Its click doesn't reach the title (which would
 * open it). @param {HTMLDetailsElement} el
 */
function collapseButton(el) {
  const summary = /** @type {HTMLElement} */ (el.querySelector(":scope > summary"));
  const button = h("button", { type: "button", class: "large-collapse", title: "Back to its panel" }, ["Collapse"]);
  button.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    // @ts-ignore
    el._largeHooks?.onCollapse?.();
  });
  summary.append(button);
}

/**
 * Grey out a large view's bar Collapse, saying why (`reason`), or allow it again (null):
 * the Frequency view while Edit curve is on (Keep or Discard first).
 * @param {HTMLDetailsElement} el @param {string | null} reason
 */
function lockLargeView(el, reason) {
  const button = /** @type {HTMLButtonElement | null} */ (el.querySelector(":scope > summary .large-collapse"));
  if (!button) return;
  button.disabled = !!reason;
  button.title = reason ?? "Back to its panel";
}

/** Shrink every large view but `el` to its bar. @param {HTMLDetailsElement} el */
function shrinkOthers(el) {
  for (const v of largeViews) {
    if (v === el || !v.open) continue;
    v.open = false;
    shrunkNow(v); // now, not on its toggle event: in the same frame as the one opening
  }
}

/**
 * A small chip on a large view's title bar, open or shrunk (the Frequency view's "Editing"
 * while Edit curve is on); null takes it off.
 * @param {HTMLDetailsElement} el @param {string | null} text
 */
export function largeViewChip(el, text) {
  const summary = /** @type {HTMLElement} */ (el.querySelector(":scope > summary"));
  let chip = summary.querySelector(".large-chip");
  if (!text) return chip?.remove();
  if (!chip) {
    chip = h("span", { class: "large-chip" });
    summary.append(chip);
  }
  chip.textContent = text;
}

/**
 * Shrunk large views' bars from the bottom up (in the order they shrank), the canvas's
 * width so they don't cover the side panels; then the open ones above them all, across
 * the page.
 */
function stackLargeViews() {
  let bottom = LARGE_EDGE;
  const views = [...largeViews];
  const canvas = document.querySelector(".canvas")?.getBoundingClientRect();
  // a pinned bar (the Audio pane's, with its controls) is always the bottom one, so they
  // don't move about; the others stack above it in the order they shrank (D-111)
  const shrunk = views.filter((x) => !x.open);
  for (const v of [...shrunk.filter((x) => x.dataset.pinBar), ...shrunk.filter((x) => !x.dataset.pinBar)]) {
    v.style.bottom = `${bottom}px`;
    v.style.left = canvas ? `${canvas.left + LARGE_GAP}px` : "";
    v.style.right = canvas ? `${document.documentElement.clientWidth - canvas.right + LARGE_GAP}px` : "";
    bottom += v.offsetHeight + LARGE_GAP;
  }
  for (const v of views.filter((x) => x.open)) {
    v.style.bottom = `${bottom}px`;
    v.style.left = v.style.right = "";
  }
}
window.addEventListener("resize", () => {
  stackLargeViews();
  makeRoom();
});

/** An open large view leaving under `CANVAS_MIN` of the canvas above it shrinks to its bar (a window made shorter, D-127). */
function makeRoom() {
  const canvas = document.querySelector(".canvas")?.getBoundingClientRect();
  if (!canvas) return;
  for (const v of [...largeViews].filter((x) => x.open)) {
    if (v.getBoundingClientRect().top - canvas.top >= CANVAS_MIN) continue;
    v.open = false;
    shrunkNow(v);
  }
}
