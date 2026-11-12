/**
 * Part symbols as plain shape lists in the part's own coordinates (before rotation;
 * grid 10, y down). No DOM. Lead ends sit exactly on the pin offsets defined in
 * solum/circuit/parts.py; tests/ui/test_js_logic.py checks `leads` against that table.
 *
 * @typedef {{line: number[]} | {path: string, fill?: boolean} | {circle: number[], fill?: boolean}
 *   | {rect: number[]} | {text: string, at: number[], size?: number, anchor?: string}} Shape
 * @typedef {{shapes: Shape[], leads: Record<string, number[]>, box: number[],
 *   ref: number[], value: number[], anchor: string,
 *   numbers?: Record<string, {at: (number | string)[], text: string}>}} Symbol
 *   (`numbers`: an op-amp's datasheet pin numbers, drawn upright beside each lead, D-140)
 */

const line = (/** @type {number[]} */ ...xy) => ({ line: xy });

/** Arrowhead with its tip at (x, y) pointing along (dx, dy). */
function arrow(x, y, dx, dy, size = 5) {
  const len = Math.hypot(dx, dy);
  const [ux, uy] = [dx / len, dy / len];
  const [bx, by] = [x - ux * size, y - uy * size];
  const [nx, ny] = [-uy * size * 0.5, ux * size * 0.5];
  const f = (/** @type {number} */ v) => +v.toFixed(2);
  return { path: `M${f(x)},${f(y)} L${f(bx + nx)},${f(by + ny)} L${f(bx - nx)},${f(by - ny)} Z`, fill: true };
}

const TWO_PIN_TEXT = { ref: [0, -12], value: [0, 22], anchor: "middle" };

/** The US zigzag body from x = -12 to 12: six legs, 5 units either side of the axis. */
const ZIGZAG = { path: "M-20,0 L-12,0 L-10,-5 L-6,5 L-2,-5 L2,5 L6,-5 L10,5 L12,0 L20,0" };

function resistor() {
  return {
    shapes: [ZIGZAG],
    leads: { 1: [-20, 0], 2: [20, 0] },
    box: [-20, -8, 40, 16],
    ...TWO_PIN_TEXT,
  };
}

/** A coil as KiCad draws one: four bumps between the leads (D-173). */
function inductor() {
  return {
    shapes: [{ path: "M-20,0 L-16,0 A4,4 0 0 1 -8,0 A4,4 0 0 1 0,0 A4,4 0 0 1 8,0 A4,4 0 0 1 16,0 L20,0" }],
    leads: { 1: [-20, 0], 2: [20, 0] },
    box: [-20, -6, 40, 12],
    ...TWO_PIN_TEXT,
  };
}

/** @param {{polarised?: boolean}} draw */
function capacitor(draw) {
  const shapes = [line(-20, 0, -3, 0), line(-3, -9, -3, 9)];
  if (draw.polarised) {
    shapes.push({ path: "M5,-9 Q1,0 5,9" }, line(3, 0, 20, 0), { text: "+", at: [-9, -5], size: 9 });
  } else {
    shapes.push(line(3, -9, 3, 9), line(3, 0, 20, 0));
  }
  return { shapes, leads: { 1: [-20, 0], 2: [20, 0] }, box: [-20, -10, 40, 20], ...TWO_PIN_TEXT };
}

/** @param {boolean} trimmer */
function pot(trimmer) {
  const wiper = trimmer
    ? [line(0, -20, 0, -9), line(-5, -9, 5, -9)]
    : [line(0, -20, 0, -12), arrow(0, -6, 0, 1)];
  return {
    shapes: [ZIGZAG, ...wiper],
    leads: { 1: [-20, 0], 2: [0, -20], 3: [20, 0] },
    box: [-20, -20, 40, 28],
    ref: [0, 18],
    value: [0, 30],
    anchor: "middle",
  };
}

/**
 * A diode, an LED (two arrows out, under it as KiCad's) or a zener: KiCad's D_Zener bends the cathode bar's
 * top end back toward the anode (D-229).
 * @param {boolean} led @param {boolean} [zener]
 */
function diode(led, zener = false) {
  const shapes = [
    line(-20, 0, -6, 0),
    line(6, 0, 20, 0),
    { path: "M-6,-7 L-6,7 L6,0 Z" },
    zener ? { path: "M6,7 L6,-7 L3,-7" } : line(6, -7, 6, 7),
  ];
  // KiCad's LED: two arrows under the body, by the cathode bar, pointing down and away
  // toward K, each with an open head
  if (led) for (const x of [8, 14]) shapes.push(line(x, 4, x + 6, 10), { path: `M${x + 6},10 L${x + 2.5},10 M${x + 6},10 L${x + 6},6.5` });
  return { shapes, leads: { A: [-20, 0], K: [20, 0] }, box: [-20, -10, 40, 20], ...TWO_PIN_TEXT };
}

/** @param {string | null} polarity */
function bjt(polarity) {
  const [ex, ey] = [22, 15]; // emitter line direction, base bar to E pin
  // NPN: arrow points out along the emitter, near its end; PNP: points in, nearer the base
  const t = polarity === "p" ? 0.4 : 0.75;
  const tip = [-2 + ex * t, 5 + ey * t];
  const dir = polarity === "p" ? [-ex, -ey] : [ex, ey];
  return {
    shapes: [
      { circle: [6, 0, 15] },
      line(-20, 0, -2, 0),
      line(-2, -10, -2, 10),
      line(-2, -5, 20, -20),
      line(-2, 5, 20, 20),
      arrow(tip[0], tip[1], dir[0], dir[1]),
    ],
    leads: { C: [20, -20], B: [-20, 0], E: [20, 20] },
    box: [-20, -20, 42, 40],
    ref: [26, -2],
    value: [26, 11],
    anchor: "start",
  };
}

/** @param {string | null} polarity */
function jfet(polarity) {
  const gateArrow = polarity === "p" ? arrow(-8, 0, -1, 0) : arrow(1, 0, 1, 0);
  return {
    shapes: [
      { circle: [8, 0, 15] },
      line(-20, 0, 2, 0),
      line(2, -12, 2, 12),
      { path: "M2,-8 L20,-8 L20,-20" },
      { path: "M2,8 L20,8 L20,20" },
      gateArrow,
    ],
    leads: { D: [20, -20], G: [-20, 0], S: [20, 20] },
    box: [-20, -20, 43, 40],
    ref: [26, -2],
    value: [26, 11],
    anchor: "start",
  };
}

/**
 * An N-channel MOSFET (D-175): the gate plate apart from the channel, broken for
 * enhancement (off until driven), solid for depletion (on at VGS = 0, D-178), the body tied
 * to the source, its arrow pointing in;
 * the body diode beside it, source to drain (D-176: inherent, no pin of its own; it's
 * why a MOSFET can guard against a reversed supply). Pins as a JFET's
 * (= parts.py PIN_OFFSETS["mosfet"]).
 */
function mosfet(depletion = false) {
  const channel = depletion ? [line(1, -12, 1, 12)] : [line(1, -12, 1, -6), line(1, -3, 1, 3), line(1, 6, 1, 12)];
  return {
    shapes: [
      { circle: [8, 0, 15] },
      line(-20, 0, -5, 0),
      line(-5, -10, -5, 10),
      ...channel,
      { path: "M1,-9 L20,-9 L20,-20" },
      { path: "M1,9 L20,9 L20,20" },
      { path: "M1,0 L20,0 L20,9" },
      arrow(2, 0, -1, 0),
      { path: "M20,-14 L30,-14 L30,-3" },
      { path: "M20,14 L30,14 L30,4" },
      { path: "M26,4 L34,4 L30,-3 Z", fill: true },
      line(26, -3, 34, -3),
    ],
    leads: { D: [20, -20], G: [-20, 0], S: [20, 20] },
    box: [-20, -20, 56, 40],
    ref: [40, -2],
    value: [40, 11],
    anchor: "start",
  };
}

// An op-amp's pins (= parts.py PIN_OFFSETS["opamp"]): power V+ and V- at the top and the
// bottom (D-140), compensation beside V+, a single's offset null beside V-, NC top right
const OPAMP_LEADS = {
  "+": [-40, 20], "-": [-40, -20], out: [40, 0], comp1: [-20, -40], comp2: [20, -40],
  "V+": [0, -40], "V-": [0, 40], null1: [-20, 40], null2: [20, 40], nc: [30, -40],
};
// each pin's lead, from its end to the triangle (top edge y = -30 + (x + 30) / 2)
const OPAMP_LINES = {
  "V+": [0, -40, 0, -15], "V-": [0, 40, 0, 15], comp1: [-20, -40, -20, -25], comp2: [20, -40, 20, -5],
  null1: [-20, 40, -20, 25], null2: [20, 40, 20, 5], nc: [30, -40, 30, -33],
};
// where each pin's datasheet number goes, beside its lead: [x, y, anchor]
const OPAMP_NUMBERS = {
  "+": [-35, 17, "middle"], "-": [-35, -23, "middle"], out: [36, -3, "middle"],
  "V+": [3, -31, "start"], "V-": [3, 35, "start"], comp1: [-23, -31, "end"], comp2: [23, -31, "start"],
  null1: [-23, 35, "end"], null2: [23, 35, "start"], nc: [33, -35, "start"],
};

/**
 * An op-amp's pins (D-140): a chip's halves have no power pins (its power unit has them,
 * D-179); a single's offset null and NC pins only while `show_pins`. Mirrors parts.py `opamp_pins`.
 * @param {{half?: string | null, show_pins?: boolean}} draw
 * @returns {Record<string, number[]>}
 */
export function opampLeads(draw) {
  /** @type {Record<string, number[]>} */
  const leads = { ...OPAMP_LEADS };
  if (draw.half) for (const pin of ["V+", "V-"]) delete leads[pin];
  if (draw.half || !draw.show_pins) for (const pin of ["null1", "null2", "nc"]) delete leads[pin];
  return leads;
}

/**
 * @param {{name: string, number?: number | null}[]} pins the pins drawn (comp pins only
 *   when used or the model has them), with their datasheet numbers
 * @param {{half?: string | null, show_pins?: boolean}} draw
 */
function opamp(pins, draw) {
  const drawn = new Set(pins.map((p) => p.name));
  const shapes = [
    { path: "M-30,-30 L-30,30 L30,0 Z" },
    line(-40, -20, -30, -20),
    line(-40, 20, -30, 20),
    line(30, 0, 40, 0),
    { text: "−", at: [-24, -16], size: 11 },
    { text: "+", at: [-24, 24], size: 11 },
  ];
  for (const [pin, xy] of Object.entries(OPAMP_LINES)) if (drawn.has(pin)) shapes.push(line(...xy));
  if (drawn.has("nc")) shapes.push(line(27, -36, 33, -30), line(27, -30, 33, -36)); // no internal connection
  return {
    shapes,
    leads: opampLeads(draw),
    numbers: Object.fromEntries(pins.filter((p) => p.number != null).map((p) => [p.name, { at: OPAMP_NUMBERS[p.name], text: String(p.number) }])),
    box: [-40, -40, 80, 80],
    // beside V- under the triangle, clear of the GND symbol below it (and of null2's lead)
    ref: [draw.show_pins ? 26 : 8, 30],
    value: [draw.show_pins ? 26 : 8, 41],
    anchor: "start",
  };
}

/**
 * One of a 4049's six inverters (D-180, KiCad's 4049 units A to F): a triangle with the
 * inverting bubble, in on the left, out on the right (= parts.py PIN_OFFSETS["inverter"]).
 * @param {{name: string, number?: number | null}[]} pins
 */
function inverter(pins) {
  const at = { in: [-25, -3, "middle"], out: [25, -3, "middle"] };
  return {
    shapes: [{ path: "M-20,-15 L-20,15 L10,0 Z" }, { circle: [14, 0, 4] }, line(-30, 0, -20, 0), line(18, 0, 30, 0)],
    leads: { in: [-30, 0], out: [30, 0] },
    numbers: Object.fromEntries(pins.filter((p) => p.number != null).map((p) => [p.name, { at: at[p.name], text: String(p.number) }])),
    box: [-30, -16, 60, 32],
    ref: [-20, 26],
    value: [-20, 37],
    anchor: "start",
  };
}

// An OTA's pins (= parts.py PIN_OFFSETS["ota"], D-180): an op-amp's inputs and output, its
// bias current in under the right of the triangle; a single's V+ and V- as an op-amp's; an
// LM13700 half's diode bias under the left and its buffer to the lower right
const OTA_LEADS = {
  "+": [-40, 20], "-": [-40, -20], out: [40, 0], iabc: [20, 40], "V+": [0, -40], "V-": [0, 40],
  dbias: [-20, 40], bufin: [60, 40], bufout: [100, 40],
};
const OTA_LINES = {
  iabc: [20, 40, 20, 5], "V+": [0, -40, 0, -15], "V-": [0, 40, 0, 15], dbias: [-20, 40, -20, 25],
  bufin: [60, 40, 70, 40], bufout: [90, 40, 100, 40],
};
const OTA_NUMBERS = {
  "+": [-35, 17, "middle"], "-": [-35, -23, "middle"], out: [36, -3, "middle"], iabc: [23, 35, "start"],
  "V+": [3, -31, "start"], "V-": [3, 35, "start"], dbias: [-23, 35, "end"], bufin: [64, 37, "middle"], bufout: [96, 37, "middle"],
};

/**
 * An OTA's pins (D-180): a single's power pins, or a dual's half's diode bias and buffer.
 * Mirrors parts.py `ota_pins`.
 * @param {{half?: string | null}} draw
 * @returns {Record<string, number[]>}
 */
export function otaLeads(draw) {
  const drop = draw.half ? ["V+", "V-"] : ["dbias", "bufin", "bufout"];
  return Object.fromEntries(Object.entries(OTA_LEADS).filter(([pin]) => !drop.includes(pin)));
}

/**
 * @param {{name: string, number?: number | null}[]} pins @param {{half?: string | null}} draw
 */
function ota(pins, draw) {
  const leads = otaLeads(draw);
  const shapes = [
    { path: "M-30,-30 L-30,30 L30,0 Z" },
    line(-40, -20, -30, -20),
    line(-40, 20, -30, 20),
    line(30, 0, 40, 0),
    { text: "−", at: [-24, -16], size: 11 },
    { text: "+", at: [-24, 24], size: 11 },
    { text: "gm", at: [-8, 3], size: 9 },
  ];
  for (const [pin, xy] of Object.entries(OTA_LINES)) if (pin in leads) shapes.push(line(...xy));
  if (draw.half) shapes.push({ path: "M70,30 L70,50 L90,40 Z" });
  return {
    shapes,
    leads,
    numbers: Object.fromEntries(pins.filter((p) => p.number != null).map((p) => [p.name, { at: OTA_NUMBERS[p.name], text: String(p.number) }])),
    box: draw.half ? [-40, -30, 140, 70] : [-40, -40, 80, 80],
    ref: [8, -32],
    value: [8, -21],
    anchor: "start",
  };
}

/**
 * A chip's power unit (D-179, KiCad's unit C or E): V+ on top, V- under it,
 * numbered from the chip's package.
 * @param {{name: string, number?: number | null}[]} pins
 */
function powerunit(pins) {
  const at = { "V+": [3, -33, "start"], "V-": [3, 37, "start"] };
  return {
    shapes: [
      { path: "M-10,-30 L10,-30 L10,30 L-10,30 Z" },
      line(0, -40, 0, -30),
      line(0, 30, 0, 40),
      { text: "V+", at: [0, -18], size: 9 },
      { text: "V−", at: [0, 24], size: 9 },
    ],
    leads: { "V+": [0, -40], "V-": [0, 40] },
    numbers: Object.fromEntries(pins.filter((p) => p.number != null).map((p) => [p.name, { at: at[p.name], text: String(p.number) }])),
    box: [-12, -40, 24, 80],
    ref: [14, -2],
    value: [14, 9],
    anchor: "start",
  };
}

function vsource() {
  return {
    shapes: [
      { circle: [0, 0, 10] },
      line(0, -20, 0, -10),
      line(0, 10, 0, 20),
      { text: "+", at: [0, -2], size: 9 },
      { text: "−", at: [0, 8], size: 9 },
    ],
    leads: { "+": [0, -20], "-": [0, 20] },
    box: [-12, -20, 24, 40],
    ref: [14, -2],
    value: [14, 11],
    anchor: "start",
  };
}

/**
 * A charge pump's pins as the datasheets draw the 8-pin box: 1-4 down the left, 8-5 up the
 * right; `name` null for the pins drawn but not wired.
 * @type {{n: number, x: number, y: number, name: string | null, text?: string}[]}
 */
const PUMP_PINS = [
  { n: 1, x: -40, y: -30, name: "1" }, { n: 2, x: -40, y: -10, name: "cap+", text: "CAP+" },
  { n: 3, x: -40, y: 10, name: "gnd", text: "GND" }, { n: 4, x: -40, y: 30, name: "cap-", text: "CAP−" },
  { n: 8, x: 40, y: -30, name: "in", text: "V+" }, { n: 7, x: 40, y: -10, name: "7" },
  { n: 6, x: 40, y: 10, name: "6" }, { n: 5, x: 40, y: 30, name: "out", text: "OUT" },
];

/**
 * A charge-pump chip (D-226): the datasheets' numbered 8-pin box. Its caps and diodes are
 * drawn parts; pins 1, 6 and 7 (boost or FB, LV or VREF, OSC: their names differ by chip,
 * so only their numbers show) may be wired or left open; pin 1 on V+ is boost (D-234)
 * (= parts.py PIN_OFFSETS["chargepump"]).
 */
function chargepump() {
  /** @type {Shape[]} */
  const shapes = [{ rect: [-30, -40, 60, 80] }];
  /** @type {Record<string, number[]>} */
  const leads = {};
  /** @type {Record<string, {at: (number | string)[], text: string}>} */
  const numbers = {};
  for (const { n, x, y, name, text } of PUMP_PINS) {
    const side = Math.sign(x);
    shapes.push(line(side * 30, y, x, y));
    numbers[name] = { at: [side * 35, y - 3, "middle"], text: String(n) };
    leads[name] = [x, y];
    if (text) shapes.push({ text, at: [side * 27, y + 3], size: 7, anchor: side < 0 ? "start" : "end" });
  }
  return { shapes, leads, numbers, box: [-40, -42, 80, 84], ref: [20, -54], value: [20, -45], anchor: "end" };
}

/** Where a regulator's pins and their names sit: in left, out right, ground below. */
const REGULATOR_PINS = /** @type {const} */ ([
  { name: "in", lead: [-30, 0, -40, 0], text: "IN", at: [-27, 3], anchor: "start", number: [-35, -3, "middle"] },
  { name: "out", lead: [30, 0, 40, 0], text: "OUT", at: [27, 3], anchor: "end", number: [35, -3, "middle"] },
  { name: "gnd", lead: [0, 20, 0, 40], text: "GND", at: [0, 17], anchor: "middle", number: [3, 31, "start"] },
]);

/**
 * A fixed regulator (D-227) as KiCad's Regulator_Linear draws one: a box, IN on the left,
 * OUT on the right, GND below, with its datasheet pin numbers when the model has them
 * (= parts.py PIN_OFFSETS["regulator"]).
 * @param {Array<{name: string, number?: number | null}>} pins
 */
function regulator(pins) {
  /** @type {Shape[]} */
  const shapes = [{ rect: [-30, -15, 60, 35] }];
  /** @type {Record<string, number[]>} */
  const leads = {};
  /** @type {Record<string, {at: (number | string)[], text: string}>} */
  const numbers = {};
  for (const pin of REGULATOR_PINS) {
    const [x1, y1, x2, y2] = pin.lead;
    shapes.push(line(x1, y1, x2, y2), { text: pin.text, at: [...pin.at], size: 7, anchor: pin.anchor });
    leads[pin.name] = [x2, y2];
    const n = pins.find((p) => p.name === pin.name)?.number;
    if (n != null) numbers[pin.name] = { at: [...pin.number], text: String(n) };
  }
  return { shapes, leads, numbers, box: [-40, -17, 80, 59], ref: [0, -29], value: [0, -20], anchor: "middle" };
}

/**
 * The guitar input: a jack. A stereo one (D-143) has its ring lug below, and the plugged
 * cable's sleeve joining the ring to ground is drawn beside it ("cable in").
 * @param {{stereo?: boolean}} draw
 */
function guitar(draw = {}) {
  const ring = draw.stereo
    ? [line(0, 8, 0, 20), line(0, 14, -12, 14), line(-12, 14, -12, 18), line(-16, 18, -8, 18),
      line(-14, 20.5, -10, 20.5), { text: "R", at: [5, 18], size: 6, anchor: "start" },
      { text: "cable in", at: [-19, 20], size: 6, anchor: "end" }]
    : [];
  return {
    shapes: [{ circle: [0, 0, 8] }, { circle: [0, 0, 2.5], fill: true }, line(8, 0, 20, 0), ...ring],
    leads: draw.stereo ? { out: [20, 0], ring: [0, 20] } : { out: [20, 0] },
    box: [-10, -10, 30, 20],
    // A stereo jack's ring lead is below, so its text goes above, under the ref.
    ref: draw.stereo ? [0, -22] : [0, -13],
    value: draw.stereo ? [0, -12] : [0, 22],
    anchor: "middle",
  };
}

function amp() {
  return {
    shapes: [line(-20, 0, -10, 0), { path: "M-10,-11 L-10,11 L10,0 Z" }],
    leads: { in: [-20, 0] },
    box: [-20, -12, 32, 24],
    ref: [0, -15],
    value: [0, 24],
    anchor: "middle",
  };
}

/**
 * Every switch type's lugs and contacts, from the server (`GET /api/switches`, the one
 * owner: solum/circuit/switches.py, D-143). Set once when the app starts.
 * @typedef {{id: string, name: string, short: string, group: string, poles: number,
 *   lugs: string[], positions: string[], closed: (string | null)[][], hint: string, look: "toggle" | "rotary"}} SwitchKind
 * @typedef {{name: string, throws: number, look?: "toggle" | "rotary",
 *   positions: Array<{name: string, joins: (number | null)[]}>}} CustomSwitch a custom switch's own contacts (v22, 9c)
 * @type {Map<string, SwitchKind>}
 */
const switchKinds = new Map();

/** @param {SwitchKind[]} kinds */
export function setSwitchKinds(kinds) {
  switchKinds.clear();
  for (const k of kinds) switchKinds.set(k.id, k);
}

/** @param {string} id @returns {SwitchKind | undefined} */
export const switchKind = (id) => switchKinds.get(id);

/** @returns {SwitchKind[]} */
export const allSwitchKinds = () => [...switchKinds.values()];

/**
 * A custom pole's lugs, the common first (= switches.py `throw_lugs`, 9c): one throw 1, 2;
 * two drawn as a toggle 2, 1, 3; else C and 1…n.
 * @param {number} throws @param {"toggle" | "rotary"} look @returns {string[]}
 */
export function throwLugs(throws, look) {
  if (throws === 1) return ["1", "2"];
  if (throws === 2 && look === "toggle") return ["2", "1", "3"];
  return ["C", ...Array.from({ length: throws }, (_, i) => String(i + 1))];
}

/**
 * A switch part's type (9c): its own contacts for a custom one (= switches.py
 * `custom_kind`), else the built-in type its `kind` names.
 * @param {{kind?: string, custom?: CustomSwitch | null}} part @returns {SwitchKind | undefined}
 */
export function kindOf(part) {
  const c = part.custom;
  if (part.kind !== "custom" || !c?.positions?.length) return switchKinds.get(part.kind ?? "spdt");
  const look = c.look ?? "toggle";
  const lugs = throwLugs(c.throws, look);
  return {
    id: "custom", name: c.name, short: c.name, group: "Custom", poles: c.positions[0].joins.length, lugs,
    positions: c.positions.map((p) => p.name), closed: c.positions.map((p) => p.joins.map((j) => (j == null ? null : lugs[j]))), hint: "", look,
  };
}

const POLES = "ABCD";

/**
 * A pole's symbol data from the part as the file has it (as view.py's `switch_draw`):
 * its lugs, the common first (A2, A1, A3), and each position's lug the common joins.
 * @param {{kind?: string, pole?: string | null, custom?: CustomSwitch | null}} part
 * @returns {{lugs: string[], closed: (string | null)[], look?: "toggle" | "rotary"}}
 */
export function poleDraw(part) {
  const kind = kindOf(part);
  if (!kind) return { lugs: [], closed: [] };
  const letter = part.pole ? part.pole.toUpperCase() : "";
  const index = letter ? POLES.indexOf(letter) : 0;
  const name = (/** @type {string} */ lug) => `${letter}${lug}`;
  return { lugs: kind.lugs.map(name), closed: kind.closed.map((c) => (c[index] == null ? null : name(c[index]))), look: kind.look };
}

/** A capacitor's type as schematics write it under the value. */
const CAP_TYPES = { film: "film", ceramic: "ceramic", c0g: "C0G", electrolytic: "electrolytic", tantalum: "tantalum" };

/**
 * The line under a part's ref: the view's text, and a switch with named positions saying
 * where it is ("DPDT · Vintage", D-143).
 * @param {any} p a view part @param {number | undefined} position a switch's, if flipped
 * @returns {string}
 */
export function valueLine(p, position) {
  if (p.type !== "switch") return p.text;
  const names = p.draw?.names;
  const at = position ?? p.draw?.position ?? 0;
  return names?.[at] ? `${p.text} · ${names[at]}` : p.text;
}

/**
 * With View → Capacitor types (D-144), a capacitor's type, drawn on its own line under
 * its value ("film"), or "not-set" so the sheet shows what's left before a BOM;
 * "" for any other part.
 * @param {any} p a view part @returns {string}
 */
export function typeLine(p) {
  if (p.type !== "capacitor") return "";
  return /** @type {Record<string, string>} */ (CAP_TYPES)[p.draw?.kind ?? ""] ?? "not-set";
}

/** Whether a capacitor has a type set (one `typeLine` can name). @param {any} p @returns {boolean} */
export const typeSet = (p) => (p.draw?.kind ?? "") in CAP_TYPES;

/**
 * Where a pole's throws sit, top to bottom, as KiCad draws switches (v15, D-143), as
 * parts.py's `throw_offsets`: one level with the common, two a step above and below it
 * (the middle is a centre-off's), three or more 20 apart and centred.
 * @param {number} throws @returns {number[]}
 */
export function throwOffsets(throws) {
  if (throws === 1) return [0];
  if (throws === 2) return [-20, 20];
  return Array.from({ length: throws }, (_, i) => 20 * i - 10 * (throws - 1));
}

/**
 * How far apart a switch type's poles are stacked when placed: its height and room for
 * its ref above and its type under the last (D-143).
 * @param {{kind?: string, custom?: CustomSwitch | null}} part the switch as the file has it
 * @returns {number}
 */
export function poleStep(part) {
  const throws = (kindOf(part)?.lugs.length ?? 3) - 1;
  const ys = throwOffsets(throws);
  return Math.ceil((ys[ys.length - 1] - ys[0] + 40) / 10) * 10;
}

/**
 * One switch pole (D-143): the common's lug at (-20, 0), the other lugs down the right at
 * `throwOffsets`, as parts.py's `switch_pins`; each lug named (A1…, as Aion draws them).
 * A toggle, slide or footswitch pole is KiCad's SW_SPDT_x2 unit (D-231): its contacts in a
 * box, each led out to its lug, the arm on the contact the common joins at `position`. A
 * centre-off's middle is a blank contact (KiCad's SW_SPDT_MSM) the arm points at when off;
 * any other open pole has its arm lifted. A rotary has no box: its contacts sit on an arc
 * (`rotaryInside`).
 * @param {{lugs?: string[], closed?: (string | null)[], look?: "toggle" | "rotary"}} draw @param {number} position
 */
function switchSymbol(draw, position) {
  const [common, ...throws] = draw.lugs ?? [];
  const ys = throwOffsets(Math.max(throws.length, 1));
  const rotary = draw.look === "rotary" && throws.length >= 3;
  const top = Math.min(ys[0], 0);
  const bottom = Math.max(ys[ys.length - 1], 0);
  /** @type {Shape[]} */
  const shapes = [];
  /** @type {Record<string, number[]>} */
  const leads = {};
  if (common !== undefined) {
    leads[common] = [-20, 0];
    shapes.push({ text: common, at: [rotary ? -20 : -23, -5], size: 6 });
  }
  throws.forEach((lug, i) => {
    leads[lug] = [20, ys[i]];
    shapes.push({ text: lug, at: [rotary ? 20 : 23, ys[i] - 5], size: 6 });
  });
  const frame = { leads, box: [-22, top - 12, 44, bottom - top + 24], ref: [0, top - 16], value: [0, bottom + 22], anchor: "middle" };
  if (rotary) {
    const at = throws.indexOf(draw.closed?.[position] ?? "");
    const lugs = [[-20, 0], ...ys.map((y) => [20, y])].map(([x, y]) => ({ circle: [x, y, 2] }));
    return { shapes: [...shapes, ...lugs, ...rotaryInside(ys, at)], ...frame };
  }
  shapes.push({ rect: [-15, top - 8, 30, bottom - top + 16] });
  if (common !== undefined) shapes.push(line(-20, 0, -12, 0), { circle: [-10, 0, 2] });
  for (const y of ys.slice(0, throws.length)) shapes.push({ circle: [10, y, 2] }, line(12, y, 20, y));
  // a centre-off: two throws and a position where the pole joins neither
  const centreOff = throws.length === 2 && (draw.closed ?? []).some((c) => c === null);
  if (centreOff) shapes.push({ circle: [10, 0, 2] });
  const joined = draw.closed?.[position] ?? null;
  const at = joined === null ? -1 : throws.indexOf(joined);
  shapes.push(at >= 0 ? line(-8, 0, 8.5, ys[at]) : centreOff ? line(-8, 0, 7, 0) : line(-8, 0, 6, -6));
  return { shapes, ...frame };
}

/**
 * A rotary pole's inside, as KiCad draws SW_Rotary (9c, the user): the common's lead to a
 * pivot, the contacts on an arc around it (at most 30° apart, within ±80°; the arc grows
 * with them, about 6 apart up to a radius of 20, its right end at x 8), each led out to its lug in
 * the column on the right, and the wiper from the pivot to the contact closed at `at` (-1:
 * open, short of the first contact).
 * @param {number[]} ys the lugs' heights, top to bottom @param {number} at
 * @returns {Shape[]}
 */
function rotaryInside(ys, at) {
  const step = (Math.min(30, 160 / (ys.length - 1)) * Math.PI) / 180;
  const r = Math.min(20, Math.max(13, 6 / step)); // the pivot stays clear of the common (x ≥ -12)
  const px = 8 - r;
  const angle = (/** @type {number} */ i) => (i - (ys.length - 1) / 2) * step;
  const point = (/** @type {number} */ a, /** @type {number} */ k) => [px + k * Math.cos(a), k * Math.sin(a)];
  /** @type {Shape[]} */
  const shapes = [line(-18, 0, px - 2, 0), { circle: [px, 0, 2] }];
  ys.forEach((y, i) => {
    const [cx, cy] = point(angle(i), r);
    shapes.push({ circle: [cx, cy, 1.5] }, line(cx + 1.5, cy, 12, y), line(12, y, 18, y));
  });
  shapes.push(at >= 0 ? line(...point(angle(at), 2), ...point(angle(at), r - 1.5)) : line(...point(angle(0) - step, 2), ...point(angle(0) - step, r * 0.7)));
  return shapes;
}

/**
 * The 2.1 mm DC jack (D-143), drawn as KiCad's Barrel_Jack_Switch (at a fifth of its
 * size): the barrel along the top of a box, its three lugs out to the right: − (the
 * centre pin, centre negative) at the top, the battery lug in the middle and + (the
 * sleeve) at the bottom. The battery lug's spring rests on the sleeve with no plug in and
 * is lifted off by one (the part's text says which).
 * @param {{plugged?: boolean}} draw
 */
function dcjack(draw) {
  const plugged = draw.plugged ?? true;
  const tip = plugged ? 10 : 18; // the spring's tip: lifted by a plug, else on the sleeve
  return {
    shapes: [
      { rect: [-40, -30, 80, 60] },
      { path: "M-26,-25 L29,-25 L29,-15 L-26,-15 Z", fill: true }, { circle: [-26, -20, 5], fill: true }, // the barrel
      line(30, -20, 60, -20), // the centre pin
      line(10, 0, 60, 0), line(10, 0, 10, tip), line(10, tip, 5, tip - 5), line(10, tip, 15, tip - 5), // the battery lug's spring
      line(-30, 20, -20, 20), line(-20, 20, -10, 10), line(-10, 10, 0, 20), line(0, 20, 60, 20), // the sleeve
      { text: "−", at: [50, -23], size: 7 }, { text: "bat", at: [50, -3], size: 6 }, { text: "+", at: [50, 17], size: 7 },
    ],
    leads: { "-": [60, -20], sw: [60, 0], "+": [60, 20] },
    box: [-40, -32, 100, 64],
    ref: [0, -36],
    value: [0, 42],
    anchor: "middle",
  };
}

/**
 * An input or output jack (D-174) as KiCad draws one, 2.54 mm to 20: `AudioJack2` (mono:
 * sleeve S over tip T) or `AudioJack3` (stereo: S, ring R, T). Drawing only, but for a
 * stereo jack's cable (D-185): with one in, its sleeve joins the ring's spring to S
 * (drawn dashed), and the body says "cable in" or "cable out".
 * @param {{stereo?: boolean, plugged?: boolean}} draw
 */
function jack(draw) {
  const plugged = draw.plugged ?? true;
  const pins = (/** @type {[string, number][]} */ names) => names.map(([name, y]) => ({ text: name, at: [33, y - 3], size: 6 }));
  if (!draw.stereo) {
    return {
      shapes: [
        { path: "M-30,0 L-20,0 L-20,20 L-30,20 Z", fill: true }, { rect: [-20, -30, 40, 50] }, // the plug's end, the body
        { path: "M0,0 L5,5 L10,0 L40,0" }, // the tip's spring
        { path: "M40,-20 L-5,-20 L-5,0 L-10,5 L-15,0" }, // the sleeve's
        ...pins([["T", 0], ["S", -20]]),
      ],
      leads: { T: [40, 0], S: [40, -20] },
      box: [-30, -30, 70, 50],
      ref: [0, -36],
      value: [0, 32],
      anchor: "middle",
    };
  }
  return {
    shapes: [
      { path: "M-50,20 L-40,20 L-40,40 L-50,40 Z", fill: true }, { rect: [-40, -30, 60, 70] },
      { path: "M-15,20 L-10,25 L-5,20 L-5,0 L40,0" }, // the ring's spring
      { path: "M0,20 L5,25 L10,20 L40,20" }, // the tip's
      { path: "M40,-20 L-20,-20 L-20,20 L-25,25 L-30,20" }, // the sleeve's
      ...pins([["T", 20], ["R", 0], ["S", -20]]),
      ...(plugged ? [{ path: "M-20,10 L-17,10 M-14,10 L-11,10 M-8,10 L-5,10" }] : []), // a cable's sleeve, ring to S
      { text: plugged ? "cable in" : "cable out", at: [-10, 37], size: 6 },
    ],
    leads: { T: [40, 20], R: [40, 0], S: [40, -20] },
    box: [-50, -30, 90, 70],
    ref: [-10, -36],
    value: [-10, 52],
    anchor: "middle",
  };
}

/** A 9 V battery (D-143): + at the top, − at the bottom, its cells between. */
function battery() {
  return {
    shapes: [
      line(0, -20, 0, -6), line(-10, -6, 10, -6), line(-5, -2, 5, -2),
      line(-10, 2, 10, 2), line(-5, 6, 5, 6), line(0, 6, 0, 20),
      { text: "+", at: [-14, -8], size: 9 },
    ],
    leads: { "+": [0, -20], "-": [0, 20] },
    box: [-12, -20, 24, 40],
    ref: [16, -4],
    value: [16, 8],
    anchor: "start",
  };
}

/**
 * The symbol for a part from the circuit view.
 * @param {{type: string, polarity?: string | null, draw?: any, pins: Array<{name: string}>}} part
 * @param {number} [position] a switch's current position (knob state); a DC jack's is
 *   the Power knob's (0 plugged in, 1 on the battery) and a stereo jack's its Cable knob's
 *   (0 in, 1 out), none when there's no knob
 * @returns {Symbol}
 */
export function symbol(part, position) {
  const draw = part.draw ?? {};
  switch (part.type) {
    case "resistor": return resistor();
    case "capacitor": return capacitor(draw);
    case "jack": return jack(position === undefined ? draw : { ...draw, plugged: position === 0 });
    case "inductor": return inductor();
    case "pot": return pot(false);
    case "trimmer": return pot(true);
    case "diode": return diode(false, Boolean(draw.zener));
    case "led": return diode(true);
    case "bjt": return bjt(part.polarity ?? "n");
    case "jfet": return jfet(part.polarity ?? "n");
    case "mosfet": return mosfet(Boolean(draw.depletion));
    case "opamp": return opamp(part.pins, draw);
    case "inverter": return inverter(part.pins ?? []);
    case "ota": return ota(part.pins ?? [], draw);
    case "powerunit": return powerunit(part.pins ?? []);
    case "vsource": return vsource();
    case "chargepump": return chargepump();
    case "regulator": return regulator(part.pins ?? []);
    case "guitar": return guitar(draw);
    case "dcjack": return dcjack(position === undefined ? draw : { plugged: position === 0 });
    case "battery": return battery();
    case "amp": return amp();
    case "switch": return switchSymbol(draw, position ?? 0);
    default: throw new Error(`No symbol for part type ${part.type}`);
  }
}

/**
 * The symbol drawn for a GND label (pointing down from its point) or a rail label (a bar
 * above it), in the label's own coordinates (its point at 0, 0).
 * @param {"ground" | "rail"} kind
 * @returns {{shapes: Shape[], box: number[], text: number[] | null}}
 */
export function supplySymbol(kind) {
  if (kind === "ground") {
    return { shapes: [line(0, 0, 0, 10), line(-9, 10, 9, 10), line(-5.5, 13.5, 5.5, 13.5), line(-2, 17, 2, 17)], box: [-10, 0, 20, 19], text: null };
  }
  return { shapes: [line(0, 0, 0, -10), line(-8, -10, 8, -10)], box: [-10, -22, 20, 22], text: [0, -14] };
}

/**
 * Where a supply symbol's name goes when it's turned `rot` (D-117): beyond its bar, kept
 * upright (above it, right of it, under it, left of it). Null for ground (no name).
 * @param {"ground" | "rail"} kind @param {number} rot
 * @returns {{x: number, y: number, anchor: string} | null}
 */
export function supplyText(kind, rot) {
  if (kind === "ground") return null;
  return /** @type {Record<number, {x: number, y: number, anchor: string}>} */ ({
    0: { x: 0, y: -14, anchor: "middle" },
    90: { x: 13, y: 3.5, anchor: "start" },
    180: { x: 0, y: 22, anchor: "middle" },
    270: { x: -13, y: 3.5, anchor: "end" },
  })[rot] ?? null;
}

/**
 * Where to put a part's ref (line 0) or value (line 1) text after rotation, in schematic
 * coordinates relative to the part, with the text kept upright and the ref always the
 * upper of the two lines, the value under it on an upright part. Rotation is clockwise on
 * screen (y down), as in parts.py.
 * @param {Symbol} sym @param {number} rot @param {number} line
 * @returns {{x: number, y: number, anchor: string}}
 */
export function placeText(sym, rot, line) {
  const local = line ? sym.value : sym.ref;
  if (rot === 180) {
    const flip = /** @type {Record<string, string>} */ ({ start: "end", end: "start" });
    const anchor = flip[sym.anchor] ?? sym.anchor;
    // text on both sides (two-pin parts) stays above/below, mirrored left to right
    if (Math.sign(sym.ref[1]) !== Math.sign(sym.value[1])) return { x: -local[0], y: local[1], anchor };
    // text on one side moves to the other, keeping the ref above the value
    const [top, bottom] = [-sym.value[1], -sym.ref[1]];
    return { x: -local[0], y: line ? bottom : top, anchor };
  }
  const [x, y] = rotateOffset(local, rot);
  if (rot === 90 || rot === 270) {
    // text that sat above/below a horizontal part goes beside the vertical one, the ref
    // above the value; a two-pin part's value joins its ref's side, right under it
    const [rx] = rotateOffset(sym.ref, rot);
    const at = line && Math.sign(rx) !== Math.sign(x) ? rx : x;
    return { x: at >= 0 ? at + 4 : at - 4, y: y + (line ? 10 : 0), anchor: at >= 0 ? "start" : "end" };
  }
  return { x, y, anchor: sym.anchor };
}

/**
 * Net label text placement from the label's `side` (unit vector away from its part).
 * @param {number[]} pos @param {number[]} side
 * @returns {{x: number, y: number, anchor: string, dcY: number}}
 */
export function labelText(pos, side) {
  const [sx, sy] = side;
  if (sx < 0) return { x: pos[0] - 5, y: pos[1] - 3, anchor: "end", dcY: pos[1] + 9 };
  if (sx > 0) return { x: pos[0] + 5, y: pos[1] - 3, anchor: "start", dcY: pos[1] + 9 };
  if (sy > 0) return { x: pos[0], y: pos[1] + 12, anchor: "middle", dcY: pos[1] + 23 };
  return { x: pos[0], y: pos[1] - 6, anchor: "middle", dcY: pos[1] - 17 };
}

/**
 * Pin offsets before rotation for a part as stored in the circuit file (not the view):
 * the symbol's lead ends, which tests/ui/test_js_logic.py checks against parts.py.
 * @param {{type: string, kind?: string, pole?: string | null}} part
 * @returns {Record<string, number[]>}
 */
export function pinOffsets(part) {
  return symbol({ type: part.type, pins: [], draw: fileDraw(part) }).leads;
}

/**
 * What a symbol needs from a part as the circuit file has it (the view's `draw`): a
 * switch pole's lugs, a jack's state, an op-amp's half and show_pins.
 * @param {any} part
 */
function fileDraw(part) {
  if (part.type === "switch") return poleDraw(part);
  if (part.type === "dcjack") return { plugged: part.plugged ?? true };
  if (part.type === "guitar" || part.type === "jack") return { stereo: !!part.stereo, plugged: part.plugged ?? true };
  if (part.type === "opamp") return { half: part.half ?? null, show_pins: !!part.show_pins };
  if (part.type === "ota") return { half: part.half ?? null };
  return {};
}

/**
 * Rotate an offset clockwise on screen by `rot` degrees (a multiple of 90), as parts.py.
 * @param {number[]} offset @param {number} rot
 * @returns {number[]}
 */
export function rotateOffset(offset, rot) {
  let [x, y] = offset;
  for (let i = 0; i < ((rot / 90) | 0) % 4; i++) [x, y] = [-y, x];
  return [x, y];
}

/**
 * Pin name → absolute position for a part from the circuit file.
 * @param {{type: string, pos?: number[], rot?: number, kind?: string, pole?: string | null}} part
 * @returns {Record<string, number[]>}
 */
export function pinPositions(part) {
  const [px, py] = part.pos ?? [0, 0];
  /** @type {Record<string, number[]>} */
  const out = {};
  for (const [name, offset] of Object.entries(pinOffsets(part))) {
    const [dx, dy] = rotateOffset(offset, part.rot ?? 0);
    out[name] = [px + dx, py + dy];
  }
  return out;
}

/**
 * A part's body as an absolute box [x0, y0, x1, y1] (its symbol's box, turned and moved),
 * for routing wires around it. Its pins sit on or outside the edge.
 * @param {{type: string, pos?: number[], rot?: number, kind?: string, pole?: string | null}} part
 * @returns {number[]}
 */
export function bodyBox(part) {
  const [bx, by, bw, bh] = symbol({ type: part.type, pins: [], draw: fileDraw(part) }).box;
  const [px, py] = part.pos ?? [0, 0];
  const corners = [[bx, by], [bx + bw, by + bh]].map((c) => rotateOffset(c, part.rot ?? 0));
  const xs = corners.map((c) => c[0] + px);
  const ys = corners.map((c) => c[1] + py);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

const CHAR_W = 6; // about one character of part text, schematic units
const TEXT_H = 9;

/**
 * Rough absolute boxes [x0, y0, x1, y1] around a part's ref and value text, so routed
 * wires keep off them (D-063). `value` is the text shown under the ref.
 * @param {{type: string, ref: string, pos?: number[], rot?: number, kind?: string, pole?: string | null}} part
 * @param {string} value
 * @returns {number[][]}
 */
export function textBoxes(part, value) {
  const sym = symbol({ type: part.type, pins: [], draw: fileDraw(part) });
  const [px, py] = part.pos ?? [0, 0];
  return [part.ref, value].filter(Boolean).map((text, line) => {
    const at = placeText(sym, part.rot ?? 0, line);
    const w = text.length * CHAR_W;
    const x0 = at.anchor === "start" ? at.x : at.anchor === "end" ? at.x - w : at.x - w / 2;
    return [px + x0, py + at.y - TEXT_H, px + x0 + w, py + at.y + 2];
  });
}

export const TEXT_SIZE = 10; // a text block's font size, schematic units (D-091)
export const TEXT_LINE = 13; // and its line spacing
const TEXT_CHAR = 5.6; // average character width at TEXT_SIZE, for its hit box

const TITLE_CHAR = 6.4; // the bold title's characters are wider

/**
 * A text block's lines: the title (if any) first, then the text's lines.
 * @param {{title?: string, text?: string}} block
 * @returns {Array<{line: string, title: boolean}>}
 */
export function textLines(block) {
  return [
    ...(block.title ? [{ line: block.title, title: true }] : []),
    ...(block.text ? block.text.split("\n").map((line) => ({ line, title: false })) : []),
  ];
}

/**
 * A text block's box, estimated from its longest line (no layout needed): [x0, y0, x1, y1].
 * @param {{title?: string, text?: string}} block @param {number[]} pos @returns {number[]}
 */
export function textBox(block, pos) {
  const lines = textLines(block);
  const width = Math.max(...lines.map((l) => l.line.length * (l.title ? TITLE_CHAR : TEXT_CHAR)), TEXT_CHAR);
  const pad = 3;
  const height = (Math.max(lines.length, 1) - 1) * TEXT_LINE + TEXT_SIZE;
  return [pos[0] - pad, pos[1] - pad, pos[0] + width + pad, pos[1] + height + pad + 2];
}
