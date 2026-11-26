/**
 * The Board view's logic, no DOM (D-368): the board's plain form as the circuit file holds
 * it (`Circuit.stripboard`, `solum/stripboard/board.py`'s `layout_data`), read into holes,
 * and the shapes it's drawn with. The browser edits that form as it edits the circuit
 * JSON; the server checks it (`POST /api/stripboard`).
 *
 * Board units: one hole pitch is `STEP` units (as the schematic's grid), so the
 * viewport's zoom limits suit it; hole (column, strip), both from 0, sits at
 * (column·STEP, strip·STEP). Footprint sizes come in mm and are scaled by `MM`.
 *
 * @typedef {[number, number]} Hole (column, strip), from 0
 * @typedef {{size: [number, number], parts?: Record<string, Record<string, string>>,
 *   standing?: string[], cuts?: string[], links?: string[][], wires?: WireData[],
 *   off?: Record<string, [number, number]>}} BoardData
 * @typedef {{from: string, hole?: string, lug?: string, runs?: Array<[number, number]>}} WireData an off-board wire (D-375):
 *   from a lug to a hole, to another lug, or loose
 * @typedef {{shape: string, kind: string, legs: string[], steps: number[], flat: number,
 *   stand: number, length: number, width: number, diameter: number, row_holes: number,
 *   refs: string[], look?: Look}} Footprint what `/api/stripboard` sends to draw a board part by
 * @typedef {{bands?: string[], minus?: string, cathode?: string, face?: boolean}} Look a part's
 *   markings (footprints.py's `look`, D-378): a resistor's colour bands, the leg on an
 *   electrolytic's − stripe, the cathode's leg (a diode's band), a TO-92's flat face
 * @typedef {{kind: "rect", x: number, y: number, w: number, h: number, angle: number, cx: number, cy: number}
 *   | {kind: "circle", cx: number, cy: number, r: number}
 *   | {kind: "lead", x1: number, y1: number, x2: number, y2: number}
 *   | {kind: "band", x: number, y: number, w: number, h: number, angle: number, cx: number, cy: number, colour: string}
 *   | {kind: "path", d: string, cx: number, cy: number, angle: number, cls: string}} Shape
 *   `band`: a colour band or a diode's band across a body; `path`: drawn about (cx, cy)
 *   turned by `angle`: a TO-92's body ("body"), an electrolytic's stripe ("stripe"), a
 *   chip's notch ("notch") and pin-1 dot ("dot")
 */

export const STEP = 10; // board units between holes
export const PITCH_MM = 2.54; // a hole pitch in mm (footprints.py's PITCH)
export const MM = STEP / PITCH_MM; // board units per mm
export const MARGIN = 3; // free holes shown round what's placed, to grow into (spec, *Board size*)

/** 0 → "A", 25 → "Z", 26 → "AA" (board.py's `column_name`); "" off the board's left. @param {number} column */
export function columnName(column) {
  if (!(column >= 0)) return "";
  let name = "";
  let n = column + 1;
  while (n) {
    const rest = (n - 1) % 26;
    name = String.fromCharCode(65 + rest) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

/** (5, 6) → "F7". @param {Hole} hole */
export const holeName = (hole) => `${columnName(hole[0])}${hole[1] + 1}`;

/** "F7" → [5, 6]; null when it isn't a hole's name. @param {string} name @returns {Hole | null} */
export function parseHole(name) {
  const found = /^([A-Z]+)([1-9][0-9]*)$/.exec(String(name).trim().toUpperCase());
  if (!found) return null;
  let column = 0;
  for (const letter of found[1]) column = column * 26 + letter.charCodeAt(0) - 64;
  return [column - 1, Number(found[2]) - 1];
}

/** A hole's middle in board units. @param {Hole} hole @returns {[number, number]} */
export const holeXY = (hole) => [hole[0] * STEP, hole[1] * STEP];

/**
 * The board read from its plain form: each placed part's legs in holes, the cuts, links,
 * off-board wires (`hole` null: to another lug, `to`, or loose) and the spots off-board
 * parts were put at (D-375). Names that aren't holes are left out (the server's check
 * names them).
 * @param {BoardData | null | undefined} data
 */
export function readBoard(data) {
  const [columns, strips] = data?.size ?? [0, 0];
  const standing = new Set(data?.standing ?? []);
  const parts = Object.entries(data?.parts ?? {}).map(([ref, legs]) => ({
    ref,
    standing: standing.has(ref),
    legs: /** @type {Array<[string, Hole]>} */ (Object.entries(legs).flatMap(([leg, name]) => {
      const hole = parseHole(name);
      return hole ? [[leg, hole]] : [];
    })),
  }));
  const holes = (/** @type {string[]} */ names) => /** @type {Hole[]} */ (names.map(parseHole).filter(Boolean));
  return {
    columns,
    strips,
    parts,
    cuts: holes(data?.cuts ?? []),
    links: (data?.links ?? []).map((pair) => holes(pair)).filter((pair) => pair.length === 2),
    wires: (data?.wires ?? []).map((w) => ({ lug: w.from, hole: w.hole ? parseHole(w.hole) : null, to: w.lug ?? null, runs: w.runs ?? [] })),
    spots: /** @type {Record<string, Hole>} */ ({ ...(data?.off ?? {}) }),
  };
}

/** @typedef {ReturnType<typeof readBoard>} Board */

/**
 * The holes shown: the board, and `MARGIN` free holes round it, to place into. An empty
 * board shows the margin round a single hole.
 * @param {Board} board @returns {{c0: number, s0: number, c1: number, s1: number}} first and last column and strip, inclusive
 */
export function shownHoles(board) {
  const columns = Math.max(board.columns, 1);
  const strips = Math.max(board.strips, 1);
  return { c0: -MARGIN, s0: -MARGIN, c1: columns - 1 + MARGIN, s1: strips - 1 + MARGIN };
}

/**
 * The board as drawn: an empty one (nothing placed, nothing saved) at the size it starts
 * at, worked out from the tray (`/api/stripboard`'s `start_size`, D-372), so there's room
 * to start; only what's placed counts.
 * @param {Board} board @param {[number, number] | undefined} start
 * @returns {Board}
 */
export function drawnBoard(board, start) {
  if (board.columns && board.strips) return board;
  const [columns, strips] = start ?? [0, 0];
  return { ...board, columns, strips };
}

/**
 * @typedef {{label: string, change: "insert" | "remove", axis: "column" | "strip", at: number}} LineChange
 *   a size change `/api/stripboard/size` makes (D-372)
 */

/**
 * The changes offered on a column's or strip's ruler mark: a line inserted either side
 * of it (at an edge, that adds one), or it taken out (the server refuses it when it isn't
 * empty, saying what's on it).
 * @param {"column" | "strip"} axis @param {number} line from 0 @returns {LineChange[]}
 */
export function lineChanges(axis, line) {
  const name = axis === "column" ? columnName(line) : String(line + 1);
  const [before, after] = axis === "column" ? ["left of", "right of"] : ["above", "below"];
  return [
    { label: `Insert a ${axis} ${before} ${name}`, change: "insert", axis, at: line },
    { label: `Insert a ${axis} ${after} ${name}`, change: "insert", axis, at: line + 1 },
    { label: `Remove ${axis} ${name}`, change: "remove", axis, at: line },
  ];
}

/**
 * The board's header line: "12 × 9 holes (30 × 23 mm), 1 cut, 2 links", the size in mm
 * as cut midway between hole lines, to the nearest mm (D-373); an empty board says so.
 * @param {Board} board
 */
export function sizeLine(board) {
  if (!board.columns || !board.strips) return "Empty board";
  const plural = (/** @type {number} */ n, /** @type {string} */ word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const mm = (/** @type {number} */ holes) => Math.round(holes * PITCH_MM);
  const wires = board.wires.length ? `, ${plural(board.wires.length, "wire")}` : "";
  return `${board.columns} × ${board.strips} holes (${mm(board.columns)} × ${mm(board.strips)} mm), ${plural(board.cuts.length, "cut")}, ${plural(board.links.length, "link")}${wires}`;
}

const BAND_AT = [-0.3, -0.17, -0.04, 0.3]; // a 4-band code's bands along the body, from its first leg
const round3 = (/** @type {number} */ n) => Math.round(n * 1000) / 1000;

/**
 * The part's body and leads, in board units: a body (a rectangle along the legs' line, or
 * a circle) over the middle of its legs, a lead from each leg to it, and its markings
 * (D-378): a resistor's colour bands, a diode's band at its cathode, an electrolytic's −
 * stripe, a TO-92's D-shaped body (the flat face on the right of its legs' line, from the
 * first leg: the package's pins 1 2 3 read from the face), a chip's notch and pin-1 dot. A
 * standing axial part's body is a circle over its first leg, a lead down to the other.
 * @param {Footprint} fp @param {Array<[string, Hole]>} legs in the footprint's order
 * @param {boolean} standing @returns {Shape[]}
 */
export function partShapes(fp, legs, standing) {
  if (!legs.length) return [];
  const points = legs.map(([, hole]) => holeXY(hole));
  const leadsTo = (/** @type {[number, number]} */ to) => points.map(([x, y]) => /** @type {Shape} */ ({ kind: "lead", x1: x, y1: y, x2: to[0], y2: to[1] }));
  if (fp.shape === "axial" && standing) {
    const [first, ...rest] = points;
    const r = Math.max(fp.width * MM, STEP * 0.6) / 2;
    return [...rest.map(([x, y]) => /** @type {Shape} */ ({ kind: "lead", x1: x, y1: y, x2: first[0], y2: first[1] })), { kind: "circle", cx: first[0], cy: first[1], r }];
  }
  const look = fp.look ?? {};
  const last = points[points.length - 1];
  const legAngle = round3((Math.atan2(last[1] - points[0][1], last[0] - points[0][0]) * 180) / Math.PI);
  /** Whether `leg` is the last leg (the far end of the legs' line). @param {string | undefined} leg */
  const atEnd = (leg) => legs.findIndex(([name]) => name === leg) === legs.length - 1;
  const box = (/** @type {number} */ k) => (Math.min(...points.map((p) => p[k])) + Math.max(...points.map((p) => p[k]))) / 2;
  // a triangle trimmer's body sits over its legs' box (D-393), the rest over their mean
  const cx = fp.shape === "triangle" ? box(0) : points.reduce((s, p) => s + p[0], 0) / points.length;
  const cy = fp.shape === "triangle" ? box(1) : points.reduce((s, p) => s + p[1], 0) / points.length;
  if (fp.diameter) {
    const r = (fp.diameter * MM) / 2;
    /** @type {Shape[]} */
    const shapes = [...leadsTo([cx, cy]), { kind: "circle", cx, cy, r }];
    if (look.minus) {
      const a = r * 0.45;
      const b = Math.sqrt(r * r - a * a);
      shapes.push({ kind: "path", d: `M${round3(a)},${round3(-b)} A${round3(r)},${round3(r)} 0 0 1 ${round3(a)},${round3(b)} Z`, cx, cy, angle: atEnd(look.minus) ? legAngle : legAngle + 180, cls: "stripe" });
    }
    return shapes;
  }
  // along the legs' line: first to last leg; a DIP's along its row, pin 1 to the row's last
  const end = fp.shape === "dip" ? points[Math.max(0, points.length / 2 - 1)] : points[points.length - 1];
  const angle = (Math.atan2(end[1] - points[0][1], end[0] - points[0][0]) * 180) / Math.PI;
  const span = Math.hypot(end[0] - points[0][0], end[1] - points[0][1]);
  const length = fp.length ? fp.length * MM : span + STEP * 0.8;
  const width = Math.max(fp.width * MM, STEP * 0.5);
  const turned = round3(angle);
  const body = /** @type {Shape} */ ({ kind: "rect", x: cx - length / 2, y: cy - width / 2, w: length, h: width, angle: turned, cx, cy });
  if (fp.shape === "dip") { // its legs sit under its body: no leads; the notch at pin 1's end, a dot by pin 1
    const n = width * 0.14;
    const dx = points[0][0] - cx;
    const dy = points[0][1] - cy;
    const t = (-turned * Math.PI) / 180;
    const [px, py] = [dx * Math.cos(t) - dy * Math.sin(t), dx * Math.sin(t) + dy * Math.cos(t)];
    const dot = STEP * 0.12;
    return [body,
      { kind: "path", d: `M${round3(-length / 2)},${round3(-n)} A${round3(n)},${round3(n)} 0 0 1 ${round3(-length / 2)},${round3(n)}`, cx, cy, angle: turned, cls: "notch" },
      { kind: "path", d: `M${round3(px * 0.75 - dot)},${round3(py * 0.55)} a${dot},${dot} 0 1 0 ${2 * dot},0 a${dot},${dot} 0 1 0 ${-2 * dot},0`, cx, cy, angle: turned, cls: "dot" }];
  }
  const leads = leadsTo([cx, cy]);
  if (look.face) {
    const h = width / 2;
    const half = length / 2;
    return [...leads, { kind: "path", d: `M${round3(-half)},${round3(h)} L${round3(half)},${round3(h)} A${round3(half)},${round3(2 * h)} 0 0 0 ${round3(-half)},${round3(h)} Z`, cx, cy, angle: turned, cls: "body" }];
  }
  /** A band across the body at `at` (a fraction of its length from the middle, toward the last leg). @param {number} at @param {string} colour @returns {Shape} */
  const band = (at, colour) => {
    const w = length * 0.08;
    const along = at * length;
    const rad = (turned * Math.PI) / 180;
    const [bx, by] = [cx + along * Math.cos(rad), cy + along * Math.sin(rad)];
    return { kind: "band", x: bx - w / 2, y: by - width / 2, w, h: width, angle: turned, cx: bx, cy: by, colour };
  };
  const marks = (look.bands ?? []).slice(0, BAND_AT.length).map((colour, i) => band(BAND_AT[i], colour));
  if (look.cathode) marks.push(band(atEnd(look.cathode) ? 0.32 : -0.32, "cathode"));
  if (look.minus) marks.push(band(atEnd(look.minus) ? 0.36 : -0.36, "minus")); // an axial electrolytic's − end (D-411)
  return [...leads, body, ...marks];
}

/**
 * Where a part's label goes: the middle of its body (a standing part's, its circle).
 * @param {Shape[]} shapes @returns {[number, number]}
 */
export function labelAt(shapes) {
  const body = shapes.find((s) => s.kind !== "lead");
  return body && body.kind !== "lead" ? [body.cx, body.cy] : [0, 0];
}

/**
 * What a board part is labelled with besides its ref: its value, or a chip's or
 * transistor's model.
 * @param {any} circuit @param {string} ref @param {string[]} refs the circuit parts on it
 */
export function valueOf(circuit, ref, refs) {
  const parts = circuit?.parts ?? [];
  const part = parts.find((/** @type {any} */ p) => p.ref === ref) ?? parts.find((/** @type {any} */ p) => refs.includes(p.ref));
  return String(part?.value ?? part?.model ?? "");
}

/**
 * The board part a circuit part is on: itself, or the chip whose unit it is.
 * @param {Record<string, Footprint>} footprints @param {string} ref
 */
export function boardRefOf(footprints, ref) {
  if (footprints[ref]) return ref;
  return Object.keys(footprints).find((key) => footprints[key].refs.includes(ref)) ?? null;
}

/**
 * @typedef {{net: string, state: "done" | "pieces" | "shorted", placed: number, total: number,
 *   pieces: number, shorts: Array<{other: string, words: string}>, wires?: string[]}} NetProgress
 * @typedef {{leg: string, hole: string | null, net: string | null, reach: Array<{to: string, joined: boolean}>}} LegProgress
 * @typedef {{end: string, label: string, net: string}} Lug an off-board part's lug: `end` as wires name it
 * @typedef {{ref: string, name: string, kind: string, value: string, details: string, lugs: Lug[],
 *   shape: string, size: [number, number], places: Array<[number, number]>}} OffItem an off-board
 *   part beside the board (D-375): drawn as `shape` (row, stomp, toggle, rotary, D-384), its
 *   drawing `size` in holes, each lug's place in it in holes from its top-left hole (offboard.py)
 * @typedef {{parts: [string, string], text: string, reason: string}} Overlap two bodies
 *   touching, or one past the board's edge (`parts[1]` "edge"), D-394; `reason` the
 *   builder's once dismissed (check.py's `Overlap`, D-398)
 * @typedef {{parts: string[], text: string, overlap: boolean, why: string | null}} NoteState
 *   one of the board's notes, `why` it's out of date or null (check.py's `NoteState`)
 * @typedef {{to_place: string[], wires_to_go: string[], loose: number, items: OffItem[],
 *   spots: Record<string, Hole>,
 *   unplaceable: string[], nets: NetProgress[],
 *   legs: Record<string, LegProgress[]>, faults: string[], stale: string[], warnings: string[],
 *   done: boolean, nets_done: number, footprints: Record<string, Footprint>, start_size: [number, number],
 *   shorted: Array<[number, number, number]>, rails?: Record<string, Array<[number, number, number]>>, guidance: Guidance,
 *   choices?: Record<string, Choice>, overlaps?: Overlap[], dismissed?: Overlap[], notes?: NoteState[]}} Progress
 *   what `/api/stripboard` answers (check.py's `Progress`, with the footprints and the
 *   guidance, D-377)
 * @typedef {{where: "board" | "off-board", moved: boolean, why: string | null}} Choice where a
 *   part is built (D-385): `moved` there by the builder's choice, `why` it can't be moved
 */

/**
 * @typedef {{label: string, to: "board" | "off-board", why: string | null, edit: string}} WhereMove
 *   moving a part to the tray's other list (D-385): `why` it can't go (the button greyed, a
 *   drop refused); `edit` the undo step's words
 */

/**
 * Moving a part in the tray to its other list, on the board or off it, by choice (D-385):
 * back to its own list clears the choice. None for what has no choice (Power).
 * @param {Choice | undefined} choice @param {string} ref @returns {WhereMove | null}
 */
export function whereMove(choice, ref) {
  if (!choice) return null;
  return choice.where === "board"
    ? { label: "↓ Off board", to: "off-board", why: choice.why, edit: `Move ${ref} off the board` }
    : { label: "↑ On board", to: "board", why: choice.why, edit: `Put ${ref} on the board` };
}

/**
 * The mark on a part moved by choice (D-385), none on one where the parts list has it.
 * @param {Choice | undefined} choice
 */
export function choiceMark(choice) {
  if (!choice?.moved) return "";
  return choice.where === "board" ? "on the board: your choice" : "off the board: your choice";
}

const SHAPE_WORDS = /** @type {Record<string, string>} */ ({ axial: "axial", radial: "radial", inline: "in a line", dip: "DIP", sil: "SIL" });

/**
 * @typedef {{ref: string, value: string, shape: string, mark?: string, kind?: string, select?: string, item?: string, at?: string}} TrayRow
 *   `mark`: the footprint's shape, for the little drawing beside it; `select`: the
 *   circuit part a click selects; `item`: the off-board part
 *   it is, dragged out beside the board (D-375); `at`: where a placed part sits
 */

/**
 * The tray's on-board rows: each part still to place, with its value and footprint.
 * @param {Progress} progress @param {any} circuit @returns {TrayRow[]}
 */
export function trayRows(progress, circuit) {
  return progress.to_place.map((ref) => trayRow(progress, circuit, ref));
}

/** @param {Progress} progress @param {any} circuit @param {string} ref @returns {TrayRow} */
function trayRow(progress, circuit, ref) {
  const fp = progress.footprints[ref];
  const pins = fp?.legs.length ?? 0;
  const shape = fp ? (fp.shape === "dip" ? `DIP-${pins}` : SHAPE_WORDS[fp.shape] ?? fp.shape) : "";
  return { ref, value: valueOf(circuit, ref, fp?.refs ?? [ref]), shape, mark: fp?.shape ?? "", kind: fp?.kind ?? "", select: ref };
}

/**
 * The tray's placed rows, shown on request: `on`, each part on the board (one gone from
 * the circuit left out), its value and `at`, the holes of its first and last legs
 * ("C4–C8"); `off`, each off-board part put out (beside the board), `at` how many of its lugs are
 * wired.
 * @param {Progress} progress @param {any} circuit @param {ReturnType<typeof readBoard>} board
 * @returns {{on: TrayRow[], off: TrayRow[]}}
 */
export function placedRows(progress, circuit, board) {
  const on = board.parts.filter((p) => progress.footprints[p.ref]).map((p) => {
    const legs = progress.footprints[p.ref].legs.map((leg) => p.legs.find(([name]) => name === leg)?.[1]).filter(Boolean);
    const ends = [legs[0], legs[legs.length - 1]].filter(Boolean).map((h) => holeName(/** @type {Hole} */ (h)));
    return { ...trayRow(progress, circuit, p.ref), at: [...new Set(ends)].join("–") };
  });
  const wired = new Set(board.wires.flatMap((w) => (w.hole || w.to ? [w.lug, ...(w.to ? [w.to] : [])] : [])));
  const off = progress.items.filter((i) => isOut(i, board)).map((i) => {
    const done = i.lugs.filter((l) => wired.has(l.end)).length;
    return { ref: i.name, value: i.value, shape: i.details || i.kind, select: itemRefs(i)[0], item: i.ref, at: `${done} of ${i.lugs.length} wired` };
  });
  return { on, off };
}

/** The tray's groups, in the parts list's order (export.py's `ORDER`), each kind's heading. */
const KIND_GROUPS = /** @type {Array<[string, string[]]>} */ ([
  ["Resistors", ["resistor"]], ["Trimmers", ["trimmer"]], ["Capacitors", ["capacitor"]],
  ["Inductors", ["inductor"]], ["Diodes and LEDs", ["diode", "led"]],
  ["Transistors", ["bjt", "jfet", "mosfet"]], ["Chips", ["chip", "chargepump", "regulator"]],
]);

/**
 * The on-board rows under their kind's heading, empty kinds left out; a kind not listed
 * goes under *Other*.
 * @param {TrayRow[]} rows @returns {Array<{title: string, rows: TrayRow[]}>}
 */
export function trayGroups(rows) {
  const known = new Set(KIND_GROUPS.flatMap(([, kinds]) => kinds));
  const groups = KIND_GROUPS.map(([title, kinds]) => ({ title, rows: rows.filter((r) => kinds.includes(r.kind ?? "")) }));
  groups.push({ title: "Other", rows: rows.filter((r) => !known.has(r.kind ?? "")) });
  return groups.filter((g) => g.rows.length);
}

/** @type {Record<string, TrayRow>} */ ({
  footswitch: { ref: "Footswitch", value: "3PDT", shape: "stock, true bypass" },
  "status LED": { ref: "Status LED", value: "", shape: "stock" },
});

/**
 * The circuit parts an off-board part stands for (a dual pot's gangs, the guitar for the
 * input jack), from its lugs; none for Power.
 * @param {OffItem} item @returns {string[]}
 */
export function itemRefs(item) {
  if (item.kind === "power") return [];
  return [...new Set(item.lugs.map((l) => l.end.split(".")[0]))];
}

/**
 * Whether an off-board part is beside the board: put somewhere, or wired (a board from
 * before v36, whose wires came from pads, D-375).
 * @param {OffItem} item @param {Board} board
 */
export function isOut(item, board) {
  if (board.spots[item.ref]) return true;
  const lugs = new Set(item.lugs.map((l) => l.end));
  return board.wires.some((w) => lugs.has(w.lug) || (w.to !== null && lugs.has(w.to)));
}

/**
 * The tray's off-board rows: each off-board part not yet beside the board, as the parts
 * list names it (its details, else what it is), `item` set so it can be dragged out. Only
 * the circuit's own: no stock footswitch or status LED (D-385).
 * @param {Progress} progress @param {Board} board @returns {TrayRow[]}
 */
export function offBoardRows(progress, board) {
  return progress.items.filter((i) => !isOut(i, board)).map((i) => ({ ref: i.name, value: i.value, shape: i.details || i.kind, select: itemRefs(i)[0], item: i.ref }));
}

/**
 * @typedef {{x: number, y: number, w: number, h: number}} Box
 * @typedef {{end: string, label: string, x: number, y: number, box?: Box}} LugAt `box`: its
 *   part's body (to route a wire round it, D-379)
 * @typedef {{x1: number, y1: number, x2: number, y2: number, loose: boolean, hole: boolean, box: Box | null, runs?: Array<[number, number]>}} WireLine
 *   a wire's ends in board units; `hole`: its far end is in a hole; `box`: its lug's part's body;
 *   `runs`: its route's middle runs moved by hand, [run number, where in holes] (D-380)
 */

/**
 * An off-board part's drawing with its corner at hole `at`, in board units: its body, and
 * each lug at its place (the server's `places`, D-384). A row of lugs hangs below its box,
 * which wires keep off (`wall`); a switch's lugs are inside its outline, which wires may
 * cross only at a cost, so they can leave a lug in the middle (D-384).
 * @param {OffItem} item @param {Hole} at @returns {{body: Box, lugs: LugAt[], wall: boolean}}
 */
export function itemShape(item, at) {
  const [w, h] = item.size;
  const [x0, y0] = holeXY(at);
  const row = item.shape === "row";
  const body = { x: x0 - STEP / 2, y: y0 - STEP / 2, w: w * STEP, h: (row ? h - 1 : h) * STEP };
  const lugs = item.lugs.map((lug, i) => ({ end: lug.end, label: lug.label, x: x0 + item.places[i][0] * STEP, y: y0 + item.places[i][1] * STEP }));
  return { body, lugs, wall: row };
}

/**
 * Where each lug is drawn, for the off-board parts beside the board: each at its spot
 * (the board's, else the server's default).
 * @param {Progress} progress @param {Board} board @returns {Record<string, LugAt>}
 */
export function lugPlaces(progress, board) {
  /** @type {Record<string, LugAt>} */
  const at = {};
  for (const item of progress.items) {
    if (!isOut(item, board)) continue;
    const { body, lugs } = itemShape(item, board.spots[item.ref] ?? progress.spots[item.ref]);
    for (const lug of lugs) at[lug.end] = { ...lug, box: body };
  }
  return at;
}

export const LOOSE_DROP = STEP * 1.6; // how far a loose wire hangs below its lug

/**
 * A wire's line in board units: from its lug to its hole, to its other lug, or hanging
 * loose below its lug; null when its lug isn't drawn.
 * @param {{lug: string, hole: Hole | null, to: string | null, runs?: Array<[number, number]>}} wire @param {Record<string, LugAt>} lugs
 * @returns {WireLine | null}
 */
export function wireLine(wire, lugs) {
  const from = lugs[wire.lug];
  if (!from) return null;
  const start = { x1: from.x, y1: from.y, box: from.box ?? null, runs: wire.runs ?? [] };
  if (wire.hole) {
    const [x2, y2] = holeXY(wire.hole);
    return { ...start, x2, y2, loose: false, hole: true };
  }
  const to = wire.to ? lugs[wire.to] : null;
  if (to) return { ...start, x2: to.x, y2: to.y, loose: false, hole: false };
  return { ...start, x2: from.x, y2: from.y + LOOSE_DROP, loose: true, hole: false };
}

/**
 * An off-board lug in words: "VR1 lug 2", "IN T", "Power V+".
 * @param {Progress | null} progress @param {string} end @returns {string}
 */
export function lugWords(progress, end) {
  const item = progress?.items.find((i) => i.lugs.some((l) => l.end === end));
  const lug = item?.lugs.find((l) => l.end === end);
  if (!item || !lug) return end;
  const name = item.kind === "power" ? "Power" : item.ref;
  return /^\d/.test(lug.label) ? `${name} lug ${lug.label}` : `${name} ${lug.label}`;
}

/**
 * Each part moved on or off the board by choice, its mark's words (D-385).
 * @param {Progress | null} progress @returns {Record<string, string>}
 */
export function chosenMarks(progress) {
  /** @type {Record<string, string>} */
  const marks = {};
  for (const [ref, choice] of Object.entries(progress?.choices ?? {})) if (choice.moved) marks[ref] = choiceMark(choice);
  return marks;
}

/**
 * The off-board parts beside the board and their wires, as the canvas draws them (D-375):
 * each part at its spot (the board's, else the server's default), each drawn wire with
 * its title.
 * @param {Progress | null} progress @param {Board} board
 * @returns {{items: Array<{item: OffItem, at: Hole}>, wires: Array<{index: number, line: WireLine, title: string, pad: boolean}>}}
 */
export function offBoardDrawing(progress, board) {
  if (!progress) return { items: [], wires: [] };
  const lugs = lugPlaces(progress, board);
  const shown = progress.items.filter((i) => isOut(i, board));
  const wires = board.wires.flatMap((wire, index) => {
    const line = wireLine(wire, lugs);
    const far = wire.hole ? holeName(wire.hole) : wire.to ? lugWords(progress, wire.to) : "loose";
    return line ? [{ index, line, title: `${lugWords(progress, wire.lug)} to ${far}: drag either end to move it`, pad: Boolean(wire.hole) }] : [];
  });
  return { items: shown.map((item) => ({ item, at: board.spots[item.ref] ?? progress.spots[item.ref] ?? /** @type {Hole} */ ([0, 0]) })), wires };
}

const CORNER = STEP * 0.25; // a bend's rounding
export const HOP = STEP * 0.3; // a hop's radius, where a wire crosses another
const GRID = STEP / 2; // wires run on a half-hole grid: on the board, along the gaps between holes
const ON_BOARD = 3; // a step over the board costs this many beside it: wires keep to the board's side
const BEND = 4; // a bend costs this many steps
const CROSS = 6; // crossing another wire
const ON_TOP = 200; // lying along another wire, or through its bend: only when there's no other way
const INSIDE = 6; // a step across a switch's outline costs this many beside it (D-384)
const OUTLINE = 12; // a step on the outline's own line: crossed once to reach a lug, never run along (D-384)
const BESIDE = 4; // a step right beside another wire running the same way: they'd read as one line
const LUG_CLEAR = STEP * 0.55; // a lug's ring: other wires keep this far from its middle
const BODY = 40; // a step over a body, when no route keeps off them (D-406): as few as can be
const DROP = 2; // grid steps from its hole a wire may cross a body beside it, to drop in (D-406)

/**
 * @typedef {{boxes: Box[], lines: Array<[number, number, number, number]>, soft?: Box[], lugs?: Array<[number, number]>, labels?: Box[]}} Obstacles
 *   what a wire keeps off (D-379): parts' bodies (board parts and off-board parts) and the
 *   leads of board parts, in board units; `soft`: switches' outlines, crossed only at a
 *   cost (D-384); `lugs`: every off-board lug, wired or not, whose ring only its own wires
 *   cross; `labels`: the names drawn above switches, kept off as bodies are (D-406)
 */

/**
 * What the wires keep off: each placed part's body and leads (`partShapes`), and each
 * off-board part's body beside the board (`itemShape`).
 * @param {Board} board @param {Record<string, Footprint>} footprints
 * @param {Array<{item: OffItem, at: Hole}>} items @returns {Obstacles}
 */
export function wireObstacles(board, footprints, items) {
  const shapes = items.map(({ item, at }) => itemShape(item, at));
  /** @type {Obstacles} */
  const found = { boxes: shapes.filter((x) => x.wall).map((x) => x.body), lines: [], soft: shapes.filter((x) => !x.wall).map((x) => x.body), lugs: shapes.flatMap((x) => x.lugs.map((l) => /** @type {[number, number]} */ ([l.x, l.y]))),
    labels: shapes.filter((x) => !x.wall).map((x) => ({ x: x.body.x, y: x.body.y - STEP, w: x.body.w, h: STEP })) }; // a switch's name sits just above it
  for (const placed of board.parts) {
    const fp = footprints[placed.ref];
    if (!fp) continue;
    const order = new Map(fp.legs.map((leg, i) => [leg, i]));
    const legs = [...placed.legs].sort((a, b) => (order.get(a[0]) ?? 0) - (order.get(b[0]) ?? 0));
    for (const s of partShapes(fp, legs, placed.standing)) {
      if (s.kind === "lead") found.lines.push([s.x1, s.y1, s.x2, s.y2]);
      else if (s.kind === "circle") found.boxes.push({ x: s.cx - s.r, y: s.cy - s.r, w: 2 * s.r, h: 2 * s.r });
      else if (s.kind === "rect") found.boxes.push(turnedBox(s.cx, s.cy, s.w, s.h, s.angle));
      else if (s.kind === "path" && s.cls === "body") found.boxes.push(turnedBox(s.cx, s.cy, fp.length * MM, Math.max(fp.width * MM, STEP * 0.5), s.angle));
    }
  }
  return found;
}

/** The upright box round a w × h rectangle about (cx, cy) turned by `angle` degrees. @returns {Box} */
function turnedBox(/** @type {number} */ cx, /** @type {number} */ cy, /** @type {number} */ w, /** @type {number} */ h, /** @type {number} */ angle) {
  const t = (angle * Math.PI) / 180;
  const [c, s] = [Math.abs(Math.cos(t)), Math.abs(Math.sin(t))];
  const [bw, bh] = [w * c + h * s, w * s + h * c];
  return { x: cx - bw / 2, y: cy - bh / 2, w: bw, h: bh };
}

/** @type {{key: string, routes: Array<Array<[number, number]> | null>} | null} */
let routed = null; // the last routes, kept while only a dragged run changes (D-380)

/**
 * The off-board wires' routes, as points with square corners (D-379): each found by a
 * search on a half-hole grid from its lug (leaving it downward) to its hole, or up into
 * its other lug. Parts' bodies and leads are walls; over the board a wire keeps to the
 * gaps between holes and each step costs more than beside it, so wires run round the
 * board's side and come in near their hole; bends and crossings cost a little, lying
 * along another wire a lot. Wires are routed in order, each keeping off those before it.
 * Loose: its short drop. The wires with runs moved by hand (`runs`, D-380) are routed
 * first, those runs put where they were moved, so the others keep off them. Drawing only: a wire is still lug + hole (D-375).
 * @param {Array<WireLine | null>} lines @param {{columns: number, strips: number}} board
 * @param {Obstacles} [obstacles] @returns {Array<Array<[number, number]> | null>}
 */
export function wireRoutes(lines, board, obstacles = { boxes: [], lines: [] }) {
  const key = JSON.stringify([lines, board.columns, board.strips, obstacles]);
  if (routed?.key !== key) routed = { key, routes: searchRoutes(lines, board, obstacles) };
  return routed.routes.map((r) => r && r.map((p) => /** @type {[number, number]} */ ([...p])));
}

/** The routes `wireRoutes` gives (uncached). @param {Array<WireLine | null>} lines @param {{columns: number, strips: number}} board @param {Obstacles} obstacles */
function searchRoutes(lines, board, obstacles) {
  const half = STEP / 2;
  const edge = { left: -half, right: board.columns * STEP - half, top: -half, bottom: board.strips * STEP - half };
  const soft = obstacles.soft ?? [];
  const xs = [edge.left, edge.right, ...[...obstacles.boxes, ...soft].flatMap((b) => [b.x, b.x + b.w])];
  const ys = [edge.top, edge.bottom, ...[...obstacles.boxes, ...soft].flatMap((b) => [b.y, b.y + b.h])];
  for (const l of lines) if (l) xs.push(l.x1, l.x2), ys.push(l.y1, l.y2);
  const pad = 4 * STEP;
  const x0 = Math.floor((Math.min(...xs) - pad) / GRID) * GRID;
  const y0 = Math.floor((Math.min(...ys) - pad) / GRID) * GRID;
  const cols = Math.ceil((Math.max(...xs) + pad - x0) / GRID) + 1;
  const rows = Math.ceil((Math.max(...ys) + pad - y0) / GRID) + 1;
  const at = (/** @type {number} */ i, /** @type {number} */ j) => j * cols + i;
  const xy = (/** @type {number} */ n) => /** @type {[number, number]} */ ([x0 + (n % cols) * GRID, y0 + Math.floor(n / cols) * GRID]);
  const node = (/** @type {number} */ x, /** @type {number} */ y) => at(Math.round((x - x0) / GRID), Math.round((y - y0) / GRID));
  // walls: bodies (a little round them), leads, the board's holes; the board's area dearer
  const wall = new Uint8Array(cols * rows);
  const dear = new Uint8Array(cols * rows);
  for (let n = 0; n < cols * rows; n++) {
    const [x, y] = xy(n);
    const over = x >= edge.left && x <= edge.right && y >= edge.top && y <= edge.bottom;
    const onLine = soft.some((b) => x >= b.x - 1 && x <= b.x + b.w + 1 && y >= b.y - 1 && y <= b.y + b.h + 1 && (Math.abs(x - b.x) <= 1 || Math.abs(x - b.x - b.w) <= 1 || Math.abs(y - b.y) <= 1 || Math.abs(y - b.y - b.h) <= 1));
    const ruled = MARGIN + 1; // the rulers' letters and numbers, a hole outside the margin: crossed, never run along
    const onRuler = (Math.abs(y + ruled * STEP) < STEP / 2 && x >= edge.left && x <= edge.right) || (Math.abs(x + ruled * STEP) < STEP / 2 && y >= edge.top && y <= edge.bottom);
    dear[n] = onLine || onRuler ? 3 : soft.some((b) => x > b.x && x < b.x + b.w && y > b.y && y < b.y + b.h) ? 2 : over ? 1 : 0;
    if (over && x % STEP === 0 && y % STEP === 0) wall[n] = 1; // a hole: only a wire's own end goes in
    // a body or a lead (2): kept off, but crossed to drop into a hole beside it, or when nothing else reaches
    else if (obstacles.boxes.some((b) => x > b.x - 1 && x < b.x + b.w + 1 && y > b.y - 1 && y < b.y + b.h + 1)) wall[n] = 2;
    else if (obstacles.lines.some(([ax, ay, bx, by]) => nearSegment(x, y, ax, ay, bx, by) < 1.5)) wall[n] = 2;
    else if ((obstacles.labels ?? []).some((b) => x >= b.x && x <= b.x + b.w && y > b.y && y < b.y + b.h)) wall[n] = 2; // a switch's name, as a body
  }
  for (const l of lines) if (l) wall[node(l.x1, l.y1)] = 1; // every lug a wall but to its own wires
  // every lug's ring, wired or not: kept clear by other wires (the user, 2026-11-23: A1's wire ran over A2 and A3)
  const lugAt = [...(obstacles.lugs ?? [])];
  for (const l of lines) if (l) for (const [x, y] of l.loose ? [[l.x1, l.y1]] : l.hole ? [[l.x1, l.y1]] : [[l.x1, l.y1], [l.x2, l.y2]]) if (!lugAt.some(([a, b]) => a === x && b === y)) lugAt.push([x, y]);
  const ring = new Int32Array(cols * rows).fill(-1);
  lugAt.forEach(([x, y], k) => {
    for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
      const [px, py] = [x + di * GRID, y + dj * GRID];
      const n = node(px, py);
      if (Math.hypot(px - x, py - y) < LUG_CLEAR && n >= 0 && n < ring.length) ring[n] = k;
    }
  });
  const lugOf = (/** @type {number} */ x, /** @type {number} */ y) => lugAt.findIndex(([a, b]) => a === x && b === y);
  /** which way the wires before use each point: 1 level, 2 upright, 3 both (a bend or a crossing) */
  const used = new Uint8Array(cols * rows);
  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  // the wires moved by hand first, so the rest go round them (the user, 2026-11-20: they take precedence)
  const order = lines.map((_, n) => n).sort((a, b) => Number(!lines[a]?.runs?.length) - Number(!lines[b]?.runs?.length));
  /** @type {Array<Array<[number, number]> | null>} */
  const found = lines.map(() => null);
  for (const n of order) found[n] = routeOne(lines[n]);
  return found;

  /** One wire's route, its runs moved by hand put where they were moved, marked as taken. @param {WireLine | null} line */
  function routeOne(line) {
    if (!line) return null;
    const { x1, y1, x2, y2 } = line;
    if (line.loose) return /** @type {Array<[number, number]>} */ ([[x1, y1], [x2, y2]]);
    const inside = (/** @type {number} */ x, /** @type {number} */ y) => soft.some((b) => x > b.x && x < b.x + b.w && y > b.y && y < b.y + b.h);
    const into = line.hole || inside(x2, y2) ? -1 : 3; // into another lug: from below, but a switch's from any side (D-384)
    const own = new Set([lugOf(x1, y1), line.hole ? -1 : lugOf(x2, y2)]);
    const goal = node(x2, y2);
    // its hole between bodies (a pad between two caps, D-406): the last steps in cross them
    const drop = new Set();
    if (line.hole) for (const [di, dj] of DIRS) for (let k = 1; k <= DROP; k++) {
      const m = goal + dj * k * cols + di * k;
      if (m < 0 || m >= wall.length || wall[m] !== 2) break;
      drop.add(m);
    }
    const path = search(node(x1, y1), goal, into, inside(x1, y1), own, drop, false)
      ?? search(node(x1, y1), goal, into, inside(x1, y1), own, drop, true); // walled in: over the fewest bodies
    /** @type {Array<[number, number]>} */
    let points = path ? path.map(xy) : [[x1, y1], [x1, y2], [x2, y2]]; // nothing reaches: straight
    points[0] = [x1, y1];
    points[points.length - 1] = [x2, y2];
    points = tidy(points);
    for (const [i, at] of line.runs ?? []) {
      if (i >= 1 && i <= points.length - 3) shiftRun(points, i, at * STEP); // else the route has changed shape: not that run any more
    }
    for (let k = 1; k < points.length; k++) take(points[k - 1], points[k]);
    return points;
  }

  /** Whether a wire before runs the same way (`level` 1 level, 2 upright) right beside grid point (i, j). @param {number} i @param {number} j @param {number} level */
  function besideUsed(i, j, level) {
    const [a, b] = level === 1 ? [[i, j - 1], [i, j + 1]] : [[i - 1, j], [i + 1, j]];
    return [a, b].some(([u, v]) => u >= 0 && v >= 0 && u < cols && v < rows && (used[at(u, v)] & level) !== 0);
  }

  /** Mark the grid points from a to b (a level or upright run) as taken that way. @param {[number, number]} a @param {[number, number]} b */
  function take(a, b) {
    const level = a[1] === b[1];
    const steps = Math.round(Math.abs(level ? b[0] - a[0] : b[1] - a[1]) / GRID);
    for (let k = 0; k <= steps; k++) {
      const t = steps ? k / steps : 0;
      const n = node(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t);
      if (n >= 0 && n < used.length) used[n] |= level ? 1 : 2;
    }
  }

  /**
   * The cheapest path from `start` (leaving it downward, or any way when `anyWay`: a lug
   * inside a switch, D-384) to `goal` (arriving upward when `into` is 3), as grid points;
   * null when there's none.
   * @param {number} start @param {number} goal @param {number} into @param {boolean} anyWay
   * @param {Set<number>} own the lugs this wire may cross the rings of: its own ends'
   * @param {Set<number>} drop bodies beside its hole it may cross to drop in
   * @param {boolean} overBodies bodies crossed at a cost (`BODY`) rather than kept off
   */
  function search(start, goal, into, anyWay, own, drop, overBodies) {
    const blocked = (/** @type {number} */ m) => (wall[m] === 1 || (wall[m] === 2 && !overBodies && !drop.has(m)) || (ring[m] >= 0 && !own.has(ring[m])));
    const [gi, gj] = [goal % cols, Math.floor(goal / cols)];
    const cost = new Float64Array(cols * rows * 4).fill(Infinity);
    const from = new Int32Array(cols * rows * 4).fill(-1);
    const heap = new Heap();
    const [si, sj] = [start % cols, Math.floor(start / cols)];
    for (const e of anyWay ? [0, 1, 2, 3] : [2]) { // down from the lug, or any way
      const [fi, fj] = [si + DIRS[e][0], sj + DIRS[e][1]];
      if (fi < 0 || fj < 0 || fi >= cols || fj >= rows) continue;
      const first = at(fi, fj);
      if (first === goal) return [start, goal];
      if (blocked(first)) continue;
      cost[first * 4 + e] = 1;
      from[first * 4 + e] = start * 4 + e;
      heap.push(first * 4 + e, 1 + Math.abs(gi - fi) + Math.abs(gj - fj));
    }
    while (heap.size) {
      const s = heap.pop();
      const [n, d] = [Math.floor(s / 4), s % 4];
      if (n === goal) return walkBack(s, from, start);
      const [i, j] = [n % cols, Math.floor(n / cols)];
      for (let e = 0; e < 4; e++) {
        const [di, dj] = DIRS[e];
        const [ni, nj] = [i + di, j + dj];
        if (ni < 0 || nj < 0 || ni >= cols || nj >= rows) continue;
        const m = at(ni, nj);
        if (m === goal ? into >= 0 && e !== into : blocked(m)) continue;
        const level = e < 2 ? 1 : 2;
        let step = dear[m] === 3 ? OUTLINE : dear[m] === 2 ? INSIDE : dear[m] ? ON_BOARD : 1;
        if (wall[m] === 2) step += BODY; // over a body: dropping into its hole, or no other way
        if (e !== d) step += BEND;
        if (used[m] & level || (used[m] && e !== d)) step += ON_TOP;
        else if (used[m]) step += CROSS;
        else if (besideUsed(ni, nj, level)) step += BESIDE;
        const c = cost[s] + step;
        const t = m * 4 + e;
        if (c >= cost[t]) continue;
        cost[t] = c;
        from[t] = s;
        heap.push(t, c + Math.abs(gi - ni) + Math.abs(gj - nj));
      }
    }
    return null;
  }
}

/** The grid points from the start to state `s`. @param {number} s @param {Int32Array} from @param {number} start */
function walkBack(s, from, start) {
  const path = [];
  for (let t = s; ; t = from[t]) {
    path.push(Math.floor(t / 4));
    if (Math.floor(t / 4) === start) break;
  }
  return path.reverse();
}

/** How far (x, y) is from the segment a–b. */
function nearSegment(/** @type {number} */ x, /** @type {number} */ y, /** @type {number} */ ax, /** @type {number} */ ay, /** @type {number} */ bx, /** @type {number} */ by) {
  const [dx, dy] = [bx - ax, by - ay];
  const t = dx || dy ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(x - ax - t * dx, y - ay - t * dy);
}

/** A small binary heap of states by priority, for the route search. */
class Heap {
  constructor() {
    /** @type {number[]} */ this.items = [];
    /** @type {number[]} */ this.keys = [];
  }
  get size() { return this.items.length; }
  /** @param {number} item @param {number} key */
  push(item, key) {
    const { items, keys } = this;
    let i = items.length;
    items.push(item);
    keys.push(key);
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (keys[p] <= key) break;
      [items[i], items[p], keys[i], keys[p]] = [items[p], items[i], keys[p], keys[i]];
      i = p;
    }
  }
  /** @returns {number} */
  pop() {
    const { items, keys } = this;
    const top = items[0];
    const [item, key] = [/** @type {number} */ (items.pop()), /** @type {number} */ (keys.pop())];
    if (items.length) {
      items[0] = item;
      keys[0] = key;
      for (let i = 0; ;) {
        const [l, r] = [2 * i + 1, 2 * i + 2];
        let m = i;
        if (l < items.length && keys[l] < keys[m]) m = l;
        if (r < items.length && keys[r] < keys[m]) m = r;
        if (m === i) break;
        [items[i], items[m], keys[i], keys[m]] = [items[m], items[i], keys[m], keys[i]];
        i = m;
      }
    }
    return top;
  }
}

/** Run `i` of route `r` moved to `at` across its length (y for a level run, x for an upright). @param {Array<[number, number]>} r @param {number} i @param {number} at */
function shiftRun(r, i, at) {
  const k = r[i][1] === r[i + 1][1] ? 1 : 0;
  r[i] = /** @type {[number, number]} */ (k ? [r[i][0], at] : [at, r[i][1]]);
  r[i + 1] = /** @type {[number, number]} */ (k ? [r[i + 1][0], at] : [at, r[i + 1][1]]);
}

/**
 * Where run `i` of a route goes when dragged to `point`, in holes (D-380): on the half-hole
 * grid the router uses; over the board, the middle of a gap between holes, never over a
 * row of them.
 * @param {Array<[number, number]>} route @param {number} i @param {[number, number]} point
 * @param {{columns: number, strips: number}} board @returns {number}
 */
export function runAt(route, i, point, board) {
  const level = route[i][1] === route[i + 1][1];
  const at = level ? point[1] : point[0];
  const [lo, hi] = level ? [route[i][0], route[i + 1][0]].sort((a, b) => a - b) : [route[i][1], route[i + 1][1]].sort((a, b) => a - b);
  const half = STEP / 2;
  const [size, across] = level ? [board.strips, board.columns] : [board.columns, board.strips];
  const over = hi > -half && lo < across * STEP - half && at > -half && at < size * STEP - half;
  const snapped = over ? Math.floor(at / STEP) * STEP + half : Math.round(at / GRID) * GRID;
  return snapped / STEP;
}

/** Points without repeats or a middle point on a straight run. @param {Array<[number, number]>} points */
function tidy(points) {
  /** @type {Array<[number, number]>} */
  const out = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (last && last[0] === p[0] && last[1] === p[1]) continue;
    const before = out[out.length - 2];
    if (before && last && ((before[0] === last[0] && last[0] === p[0]) || (before[1] === last[1] && last[1] === p[1]))) out.pop();
    out.push(p);
  }
  return out;
}

/**
 * Where the wires cross: for each route, each hop as [segment index, x], always on the
 * crossing's level run (so each crossing hops once), kept clear of the bends.
 * @param {Array<Array<[number, number]> | null>} routes @returns {Array<Array<[number, number]>>}
 */
export function wireHops(routes) {
  const clear = CORNER + HOP;
  /** @type {Array<{route: number, x: number, y1: number, y2: number}>} */
  const uprights = [];
  routes.forEach((r, route) => r?.forEach((p, i) => {
    const q = r[i + 1];
    if (q && p[0] === q[0]) uprights.push({ route, x: p[0], y1: Math.min(p[1], q[1]), y2: Math.max(p[1], q[1]) });
  }));
  return routes.map((r, route) => {
    /** @type {Array<[number, number]>} */
    const hops = [];
    r?.forEach((p, i) => {
      const q = r[i + 1];
      if (!q || p[1] !== q[1]) return;
      const [lo, hi] = [Math.min(p[0], q[0]), Math.max(p[0], q[0])];
      for (const u of uprights) {
        if (u.route === route || u.x <= lo + clear || u.x >= hi - clear || p[1] <= u.y1 + clear || p[1] >= u.y2 - clear) continue;
        hops.push([i, u.x]);
      }
    });
    return hops;
  });
}

/**
 * An SVG path through a route's points: bends rounded, a half-circle bump up at each hop.
 * @param {Array<[number, number]>} points @param {Array<[number, number]>} [hops] as `wireHops` gives
 */
export function routePath(points, hops = []) {
  const n = (/** @type {number} */ v) => String(Math.round(v * 100) / 100);
  const parts = [`M${n(points[0][0])},${n(points[0][1])}`];
  for (let i = 1; i < points.length; i++) {
    const [a, p, b] = [points[i - 1], points[i], points[i + 1]];
    const dx = Math.sign(p[0] - a[0]);
    for (const [, x] of hops.filter((h) => h[0] === i - 1).sort((h, g) => (h[1] - g[1]) * dx)) {
      parts.push(`L${n(x - dx * HOP)},${n(p[1])}`, `A${n(HOP)},${n(HOP)} 0 0 ${dx > 0 ? 1 : 0} ${n(x + dx * HOP)},${n(p[1])}`);
    }
    if (!b) {
      parts.push(`L${n(p[0])},${n(p[1])}`);
      continue;
    }
    const r = Math.min(CORNER, Math.hypot(p[0] - a[0], p[1] - a[1]) / 2, Math.hypot(b[0] - p[0], b[1] - p[1]) / 2);
    const into = [Math.sign(p[0] - a[0]), Math.sign(p[1] - a[1])];
    const out = [Math.sign(b[0] - p[0]), Math.sign(b[1] - p[1])];
    parts.push(`L${n(p[0] - into[0] * r)},${n(p[1] - into[1] * r)}`, `Q${n(p[0])},${n(p[1])} ${n(p[0] + out[0] * r)},${n(p[1] + out[1] * r)}`);
  }
  return parts.join(" ");
}

/** The point `d` along a route from its start (its end if the route is shorter). @param {Array<[number, number]>} points @param {number} d @returns {[number, number]} */
export function pointAlong(points, d) {
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (d <= length && length) return [a[0] + ((b[0] - a[0]) * d) / length, a[1] + ((b[1] - a[1]) * d) / length];
    d -= length;
  }
  return points[points.length - 1];
}

/**
 * The spot an off-board part goes to when carried with the pointer at `hole`: held by
 * the middle of its body.
 * @param {OffItem} item @param {Hole} hole @returns {Hole}
 */
export function spotFor(item, hole) {
  const [w, h] = item.size;
  return [hole[0] - Math.floor(w / 2), hole[1] - Math.floor((h - 1) / 2)];
}

/**
 * The editor's settings (spec, *Editor settings*), each on or off, remembered per viewer
 * (`solum.board`), in the order shown. `acts`: whether it does anything yet. `group`: where
 * its toggle is (D-406): the Settings pane's *Show* or *While editing*, the tray's heading
 * (`tray`), or the canvas's bar (`bar`).
 */
export const BOARD_SETTINGS = /** @type {const} */ ([
  { key: "values", label: "Values", group: "show", on: true, acts: true, title: "Label each part with its value as well as its ref" },
  { key: "rails", label: "Rails", group: "show", on: false, acts: true, title: "Highlight the rails: the supply's copper (V+, V-) rose, ground's grey" },
  { key: "rats", label: "Ratsnest", group: "show", on: true, acts: true, title: "The dashed lines between the pieces of each net on the board still to join. Off: only the lines of the part selected or carried" },
  { key: "grow", label: "Auto-grow", group: "edit", on: true, acts: true, title: "The board grows to take in what's placed by its edge, and shrinks back. Off: it stays its size (the margin greyed); add or remove lines on the rulers" },
  { key: "shorts", label: "Allow shorts", group: "edit", on: true, acts: true, title: "A move that makes a short is allowed, the short shown red. Off: it's refused" },
  { key: "next", label: "Suggest next", group: "tray", on: true, acts: true, title: "Suggest the part to place next, at the top of the tray" },
  { key: "seeThrough", label: "See-through", group: "show", on: false, acts: true, title: "The parts faint, so the copper and the cuts under them show (T)" },
  { key: "mirror", label: "Flip", group: "bar", on: false, acts: true, title: "The back of the board: the copper side, turned over as you hold it to solder. Off: the front, the parts side" },
]);

/**
 * The Layout dialog's choices (P6h2), in order, each with a line saying what it does and,
 * when it can't be chosen, why (`why`): Fill the rest and Tidy up need something placed,
 * and Fill the rest something to fill (a part in the tray or a net in pieces).
 * The first is *Start a board* on an empty board, *Start over* once parts are placed; it
 * has *Make the board compact* under it (the dialog's own checkbox). The last, below a
 * divider, *Build a full layout* (D-399), has Quick and Thorough under it.
 * @typedef {"start" | "fill" | "tidy" | "full"} LayoutChoice
 * @param {boolean} placed whether any part is on the board
 * @param {boolean} [rest] whether anything is left to fill: a part in the tray, a net in pieces
 * @returns {Array<{value: LayoutChoice, label: string, text: string, why: string}>}
 */
export function layoutChoices(placed, rest = true) {
  const none = placed ? "" : "Nothing is placed yet: start a board first.";
  const filled = none || (rest ? "" : "Every part is placed and every net joined: nothing left to fill.");
  return [
    placed
      ? { value: "start", label: "Start over", text: "Wipes the board and lays it all out afresh: a base layout, the parts in signal order left to right, for you to edit by hand.", why: "" }
      : { value: "start", label: "Start a board", text: "A base layout of the whole board, the parts in signal order left to right, for you to edit by hand.", why: "" },
    { value: "fill", label: "Fill the rest", text: "Keeps what you've placed and lays out the parts still in the tray below it.", why: filled },
    { value: "tidy", label: "Tidy up", text: "Makes the board smaller by moving parts, links and cuts in small steps, keeping the check passing.", why: none },
    { value: "full", label: "Build a full layout", text: "Starts afresh and does everything for you: lays the board out, then keeps making it smaller, wired and checked. Replaces what's on the board.", why: "" },
  ];
}

/**
 * Standing resistors and diodes (D-403), the Layout dialog's last line: used by whichever
 * choice runs and kept with the board it makes. The board's own choice, else the default.
 * @typedef {"never" | "needed" | "prefer"} StandUp
 * @type {Array<{value: StandUp, label: string, text: string}>}
 */
export const STAND_UP = [
  { value: "never", label: "Never", text: "Every resistor and diode lies flat." },
  { value: "needed", label: "When needed", text: "Stood up only where lying flat it can't sit by its pin or would break a rule; never just to save room." },
  { value: "prefer", label: "Prefer", text: "Stood up wherever it fits." },
];

/** The board's choice for standing parts (D-403): its own, else "needed". @param {{stand_up?: string} | null | undefined} data @returns {StandUp} */
export function standUpOf(data) {
  const kept = STAND_UP.find((s) => s.value === data?.stand_up);
  return kept ? kept.value : "needed";
}

/** The notes under *Build a full layout*'s choices (the user, 2026-11-24). */
export const FULL_NOTES = [
  "These times are estimates, from the circuit's size and this computer's speed: the more parts, the longer it takes to build.",
  "The layout is worked out by the app. Check it, and adjust it if you need to, before you build it on a real board.",
];

/**
 * How long a run takes, in words (D-399): "A few seconds", "About 40 seconds", "About a
 * minute", "About 3 minutes".
 * @param {number} seconds
 */
export function timeText(seconds) {
  if (seconds < 10) return "A few seconds";
  if (seconds < 55) return `About ${Math.round(seconds / 5) * 5} seconds`;
  if (seconds < 90) return "About a minute";
  return `About ${Math.round(seconds / 60)} minutes`;
}

export const LONGER = "Taking a little longer than expected…";
/** A run is late past this many times its estimate... */
const LATE_BY = 1.25;
/** ...and these seconds more: the estimate is good to about a quarter either way, and a
 * few seconds' run has fixed costs of its own (D-399). */
const LATE_PLUS = 5;

/**
 * The time a run has left, in words, from its speed so far: "About 25 seconds left."; once
 * the run is clearly late (past `LATE_BY` × its estimate + `LATE_PLUS`), `LONGER` instead.
 * @param {number} seconds left at the speed so far
 * @param {number} [elapsed] seconds the run has taken so far
 * @param {number} [expected] seconds it said it would take (0: not known)
 */
export function leftText(seconds, elapsed = 0, expected = 0) {
  if (expected > 0 && elapsed > expected * LATE_BY + LATE_PLUS) return LONGER;
  if (seconds < 5) return "Almost done.";
  if (seconds < 60) return `About ${Math.ceil(seconds / 5) * 5} seconds left.`;
  const minutes = Math.round(seconds / 60);
  return `About ${minutes} minute${minutes === 1 ? "" : "s"} left.`;
}

/**
 * A board's figures in a line: "21 × 14 holes, 23 cuts, 13 links".
 * @param {{columns: number, strips: number, cuts: number, links: number}} b
 */
export function figuresLine(b) {
  const count = (/** @type {number} */ n, /** @type {string} */ word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return `${b.columns} × ${b.strips} holes, ${count(b.cuts, "cut")}, ${count(b.links, "link")}`;
}

/**
 * A board's figures from its plain form (`circuit.stripboard`), for *Before*.
 * @param {any} stripboard @returns {{columns: number, strips: number, cuts: number, links: number}}
 */
export function figuresOf(stripboard) {
  const b = readBoard(stripboard);
  return { columns: b.columns, strips: b.strips, cuts: b.cuts.length, links: b.links.length };
}

/**
 * The earlier try a new one is the same board as (its index), or -1 (D-399: *Try another*
 * may find the same board when a circuit leaves no room for another this small).
 * @param {Array<{stripboard: any}>} tries @param {{stripboard: any}} made
 */
export function sameTry(tries, made) {
  const text = JSON.stringify(made.stripboard);
  return tries.findIndex((t) => JSON.stringify(t.stripboard) === text);
}

/**
 * The choice the Layout dialog opens on: Start a board on an empty board; none once parts
 * are placed, so the builder chooses (Start a board would wipe them).
 * @param {boolean} placed @returns {LayoutChoice | null}
 */
export function layoutDefault(placed) {
  return placed ? null : "start";
}

/**
 * The confirmation after the Layout dialog: what will happen, what's replaced (named by
 * count), and that it's one step to undo.
 * @param {LayoutChoice} choice @param {boolean} compact *Make the board compact* ticked
 * @param {{parts: unknown[], cuts: unknown[], links: unknown[], wires: unknown[]}} board what's on the board now
 * @param {number} toPlace the parts still in the tray
 * @param {number} [seconds] *Build a full layout*'s time, estimated
 * @returns {{title: string, text: string, label: string}}
 */
export function layoutConfirm(choice, compact, board, toPlace, seconds = 0) {
  const count = (/** @type {number} */ n, /** @type {string} */ word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const undo = "One step to undo.";
  if (choice === "full") {
    const takes = `It takes ${timeText(seconds).toLowerCase()}; you can stop early and keep the best board found so far.`;
    const text = board.parts.length ? `This replaces everything on the board: ${count(board.parts.length, "part")}, its cuts, links and wires. ${takes}` : takes;
    return { title: "Build a full layout", text, label: "Build it" };
  }
  if (choice === "fill") {
    const what = toPlace ? `Lays out the ${count(toPlace, "part")} still in the tray below what you've placed` : "Every part is placed: it joins what's still in pieces";
    return { title: "Fill the rest", text: `${what}; the parts you've placed stay where they are. ${undo}`, label: "Fill the rest" };
  }
  if (choice === "tidy") {
    return { title: "Tidy up", text: `Moves parts, links and cuts a step at a time to make the board smaller, keeping the check passing, so parts may end up away from where you put them. ${undo}`, label: "Tidy up" };
  }
  const then = compact ? ", then made compact" : "";
  if (!board.parts.length) return { title: "Start a board", text: `Lays out the whole board: ${count(toPlace, "part")} in signal order${then}. ${undo}`, label: "Start a board" };
  const listed = [count(board.parts.length, "part"), ...[[board.cuts.length, "cut"], [board.links.length, "link"], [board.wires.length, "wire"]].filter(([n]) => n).map(([n, w]) => count(/** @type {number} */ (n), /** @type {string} */ (w)))];
  const named = listed.length > 1 ? `${listed.slice(0, -1).join(", ")} and ${listed[listed.length - 1]}` : listed[0];
  return { title: "Start over", text: `This replaces everything on the board: ${named}. A fresh layout takes its place${then}. ${undo}`, label: "Replace the board" };
}

/** @typedef {Record<(typeof BOARD_SETTINGS)[number]["key"], boolean>} BoardSettings */

/**
 * The settings as kept, each missing or garbled one at its default.
 * @param {unknown} kept @returns {BoardSettings}
 */
export function readSettings(kept) {
  const from = kept && typeof kept === "object" ? /** @type {Record<string, unknown>} */ (kept) : {};
  return /** @type {BoardSettings} */ (Object.fromEntries(BOARD_SETTINGS.map((s) => [s.key, typeof from[s.key] === "boolean" ? from[s.key] : s.on])));
}

/**
 * The Nets pane's line: "18 of 24 nets done", or "All 24 nets done".
 * @param {Progress} progress
 */
export function netsLine(progress) {
  const total = progress.nets.length;
  if (!total) return "No nets to join.";
  const nets = progress.nets_done === total ? `All ${total} nets done` : `${progress.nets_done} of ${total} nets done`;
  const left = progress.wires_to_go.length;
  const loose = progress.loose ? `, ${progress.loose} loose` : "";
  return left || progress.loose ? `${nets}; ${left} ${left === 1 ? "lug" : "lugs"} to wire${loose}.` : `${nets}.`;
}

/** The other side of a body hanging past the board's edge, in an overlap (board.py's `EDGE`). */
export const EDGE = "edge";

/**
 * An overlap's key, the same either way round: "C1|TR1" (D-398's matching by the pair).
 * @param {string[]} parts @returns {string}
 */
export function overlapKey(parts) {
  return [...parts].sort().join("|");
}

/**
 * Where each warned overlap is marked on the board (D-398, as the schematic's problem
 * marks, D-176): between the two parts' middles, or on a part past the edge; dismissed
 * ones aren't warned, so have none. In board units, with the warning as its title.
 * @param {Progress | null} progress @param {Board} board
 * @returns {Array<{key: string, at: [number, number], title: string}>}
 */
export function overlapMarks(progress, board) {
  const middles = new Map(board.parts.filter((p) => p.legs.length).map((p) => {
    const points = p.legs.map(([, hole]) => holeXY(hole));
    return [p.ref, /** @type {[number, number]} */ ([0, 1].map((k) => points.reduce((sum, pt) => sum + pt[k], 0) / points.length))];
  }));
  return (progress?.overlaps ?? []).flatMap((o) => {
    const ends = o.parts.filter((r) => r !== EDGE).map((r) => middles.get(r));
    if (!ends.length || ends.some((m) => !m)) return [];
    const points = /** @type {Array<[number, number]>} */ (ends);
    const at = /** @type {[number, number]} */ ([0, 1].map((k) => points.reduce((sum, pt) => sum + pt[k], 0) / points.length));
    return [{ key: overlapKey(o.parts), at, title: o.text }];
  });
}

/**
 * The refs typed in a note's Parts box: "c2, R1 r1" → ["C2", "R1"] (commas or spaces,
 * each once), each matched to the board's own ref whatever its case; one not known is
 * kept as typed, for the server to refuse by name.
 * @param {string} text @param {string[]} [known] @returns {string[]}
 */
export function parseRefs(text, known = []) {
  const byCase = new Map(known.map((r) => [r.toUpperCase(), r]));
  return [...new Set(text.split(/[\s,;]+/).filter(Boolean).map((r) => byCase.get(r.toUpperCase()) ?? r))];
}

/**
 * The parts a note starts with from an overlap warning: the two, or the one past the edge.
 * @param {Overlap} overlap @returns {string[]}
 */
export function overlapParts(overlap) {
  return overlap.parts.filter((r) => r !== EDGE);
}

/**
 * A board note's plain form for the server's `note-add` / `note-set`: its refs as typed
 * (`known` the board's refs), the text trimmed, `overlap` kept only while it still names
 * those parts (D-398).
 * @param {string} partsText @param {string} text @param {{parts: string[], overlap: boolean} | null} [was]
 * @param {string[]} [known] @returns {{parts: string[], text: string, overlap?: boolean}}
 */
export function notePayload(partsText, text, was = null, known = []) {
  const parts = parseRefs(partsText, known);
  const same = Boolean(was?.overlap) && overlapKey(parts) === overlapKey(was?.parts ?? []);
  return { parts, text: text.trim(), ...(same ? { overlap: true } : {}) };
}

/**
 * A board note as the Notes pane shows it: "C2, R1: solder C2 a bit higher." or the
 * text alone (check.py's `note_words`).
 * @param {{parts: string[], text: string}} note @returns {string}
 */
export function noteLine(note) {
  return note.parts.length ? `${note.parts.join(", ")}: ${note.text}` : note.text;
}

/**
 * What the board still holds of parts the schematic no longer has (D-376), in one
 * sentence: "R7 is no longer in the circuit.", "R7 and VR9 are …"; "" when none.
 * @param {string[]} stale @returns {string}
 */
export function staleLine(stale) {
  if (!stale.length) return "";
  const names = stale.length > 1 ? `${stale.slice(0, -1).join(", ")} and ${stale[stale.length - 1]}` : stale[0];
  return `${names} ${stale.length > 1 ? "are" : "is"} no longer in the circuit.`;
}

/**
 * Each net's state in words: done; in pieces ("2 of 4 placed, in 2 pieces"), with the
 * lugs it still needs wired ("; a wire from VR1 lug 2"); shorted (each short's sentence).
 * @param {NetProgress} net @returns {string}
 */
export function netWords(net) {
  if (net.state === "shorted") return net.shorts.map((s) => s.words).join(" ");
  if (net.state === "done") return "done";
  const placed = `${net.placed} of ${net.total} placed`;
  const words = net.pieces > 1 ? `${placed}, in ${net.pieces} pieces` : placed;
  const wires = net.wires ?? [];
  return wires.length ? `${words}; ${wires.length === 1 ? "a wire" : "wires"} from ${wires.join(", ")}` : words;
}

/**
 * The board parts with a leg on `net` (to light a probed net on the board).
 * @param {Progress} progress @param {string} net
 */
export function partsOnNet(progress, net) {
  return Object.entries(progress.legs).filter(([, legs]) => legs.some((l) => l.hole && l.net === net)).map(([ref]) => ref);
}

/**
 * @typedef {{turns: number, flipped: boolean, standing: boolean, span: number}} Pose
 *   how a part sits, from its footprint's own way (legs down across the strips, first leg
 *   on top): turned a quarter `turns` times clockwise on screen, its legs' order `flipped`,
 *   an axial part `standing`, `span` holes between a two-leg part's legs or a line's legs
 *   (0 for a chip). The server decides whether it may sit there (D-374).
 * @typedef {Array<[string, Hole]>} Pattern each leg's hole, from where the part is put
 */

/** A part's first pose: its footprint's own way, lying flat, the least span. @param {Footprint} fp @returns {Pose} */
export function firstPose(fp) {
  const span = fp.shape === "axial" ? fp.flat : fp.shape === "dip" ? 0 : (fp.steps[0] ?? 1);
  return { turns: 0, flipped: false, standing: false, span };
}

/**
 * Each leg's offset in a pose, the first leg at [0, 0] before turning.
 * @param {Footprint} fp @param {Pose} pose @returns {Pattern}
 */
export function legPattern(fp, pose) {
  const n = fp.legs.length;
  /** @type {Array<[number, number]>} */
  let at;
  if (fp.shape === "dip") {
    const half = n / 2;
    at = fp.legs.map((_, i) => (i < half ? [0, i] : [fp.row_holes, n - 1 - i]));
  } else if (fp.shape === "triangle") { // a trimmer (D-393): 1 above 3, the wiper a hole back to the left, as footprints.TRIANGLE
    at = [[1, 0], [0, 1], [1, 2]];
  } else {
    at = fp.legs.map((_, i) => [0, i * pose.span]);
  }
  const names = pose.flipped && fp.shape !== "dip" ? [...fp.legs].reverse() : fp.legs; // a triangle's ends 1 and 3 swapped
  const turn = (/** @type {[number, number]} */ [x, y]) => /** @type {[number, number]} */ ([-y, x]);
  return names.map((leg, i) => {
    let p = at[i];
    for (let t = 0; t < ((pose.turns % 4) + 4) % 4; t++) p = turn(p);
    return [leg, [p[0] + 0, p[1] + 0]]; // + 0: no -0
  });
}

/** The hole a pattern is held by: its legs' middle, rounded. @param {Pattern} pattern @returns {Hole} */
export function middleOf(pattern) {
  const mean = (/** @type {number} */ k) => pattern.reduce((s, [, h]) => s + h[k], 0) / (pattern.length || 1);
  return [Math.round(mean(0)), Math.round(mean(1))];
}

/**
 * The legs of a part in `pose` with its middle at `hole`.
 * @param {Footprint} fp @param {Pose} pose @param {Hole} hole @returns {Pattern}
 */
export function legsAt(fp, pose, hole) {
  const pattern = legPattern(fp, pose);
  const [mx, my] = middleOf(pattern);
  return pattern.map(([leg, [x, y]]) => [leg, [hole[0] - mx + x, hole[1] - my + y]]);
}

/**
 * The pose a placed part sits in (its legs as the board holds them), so turning or moving
 * it starts from there; null when its legs fit no pose (a board from a file, odd).
 * @param {Footprint} fp @param {Array<[string, Hole]>} legs @param {boolean} standing
 * @returns {Pose | null}
 */
export function poseOf(fp, legs, standing) {
  const at = new Map(legs.map(([leg, hole]) => [leg, hole]));
  const a = at.get(fp.legs[0]);
  const b = at.get(fp.legs[1]);
  if (!a || !b) return null;
  const span = fp.shape === "dip" ? 0 : Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
  for (const flipped of [false, true]) {
    for (let turns = 0; turns < 4; turns++) {
      const pose = { turns, flipped, standing, span };
      const pattern = legPattern(fp, pose);
      const [, origin] = pattern[0];
      const first = /** @type {Hole} */ (at.get(pattern[0][0]));
      const fits = pattern.every(([leg, [x, y]]) => {
        const hole = at.get(leg);
        return hole && hole[0] - first[0] === x - origin[0] && hole[1] - first[1] === y - origin[1];
      });
      if (fits) return pose;
    }
  }
  return null;
}

/**
 * A pose changed by one of the editor's moves: `turn` a quarter (a chip half round: it
 * only sits across the strips), `flip` its legs' order (not a chip), `stand` up or lay
 * flat (an axial part), `longer` or `shorter` its span (a flat axial part from its least
 * span, flat or standing, D-410; a radial or a line through its footprint's spacings). Null
 * when the move doesn't apply to this part.
 * @param {Footprint} fp @param {Pose} pose @param {"turn" | "flip" | "stand" | "longer" | "shorter"} move
 * @returns {Pose | null}
 */
export function posed(fp, pose, move) {
  if (move === "turn") return { ...pose, turns: (pose.turns + (fp.shape === "dip" ? 2 : 1)) % 4 };
  if (move === "flip") return fp.shape === "dip" ? null : { ...pose, flipped: !pose.flipped };
  if (move === "stand") return fp.shape === "axial" ? { ...pose, standing: !pose.standing, span: pose.standing ? fp.flat : fp.stand } : null;
  if (fp.shape === "dip") return null;
  const by = move === "longer" ? 1 : -1;
  if (fp.shape === "axial") {
    const span = pose.span + by;
    return span >= (pose.standing ? fp.stand : fp.flat) ? { ...pose, span } : null;
  }
  const i = fp.steps.indexOf(pose.span) + by;
  return i >= 0 && i < fp.steps.length ? { ...pose, span: fp.steps[i] } : null;
}

/**
 * The plain words of a pose move, for the menu and the undo list.
 * @param {"turn" | "flip" | "stand" | "longer" | "shorter"} move @param {Pose} pose
 */
export function moveWords(move, pose) {
  return { turn: "Turn", flip: "Flip", stand: pose.standing ? "Lay flat" : "Stand up", longer: "Longer legs", shorter: "Shorter legs" }[move];
}

/**
 * The legs in the board's plain form for the server: leg → [column, strip].
 * @param {Pattern} legs @returns {Record<string, Hole>}
 */
export const legsData = (legs) => Object.fromEntries(legs);

/**
 * Copper runs as rectangles ([strip, first column, last column]): a short's red copper (`progress.shorted`).
 * @param {Array<[number, number, number]>} runs
 */
export function runRects(runs) {
  return runs.map(([strip, c0, c1]) => ({ x: (c0 - 0.5) * STEP, y: (strip - 0.5) * STEP, w: (c1 - c0 + 1) * STEP, h: STEP }));
}

/**
 * The link a drag from `from` to `to` lays: down `from`'s column to `to`'s strip; null
 * when it stays on one strip.
 * @param {Hole} from @param {Hole} to @returns {[Hole, Hole] | null}
 */
export function linkFrom(from, to) {
  return to[1] === from[1] ? null : [from, [from[0], to[1]]];
}

/**
 * A tap on `link` at `hole` (D-410): the link split there, both pieces ending in it; null
 * unless the hole is one the link passes over, between its ends.
 * @param {[Hole, Hole]} link @param {Hole} hole @returns {[Hole, Hole, Hole] | null}
 */
export function linkTap(link, hole) {
  const [top, bottom] = [...link].sort((p, q) => p[1] - q[1]);
  return hole[0] === top[0] && top[1] < hole[1] && hole[1] < bottom[1] ? [link[0], link[1], hole] : null;
}

/**
 * The holes where two or more links end: a tap, one solder joint for both (D-410).
 * @param {Array<[Hole, Hole]>} links @returns {Hole[]}
 */
export function linkTaps(links) {
  /** @type {Map<string, number>} */
  const ends = new Map();
  for (const hole of links.flat()) ends.set(hole.join(","), (ends.get(hole.join(",")) ?? 0) + 1);
  return [...ends].filter(([, n]) => n > 1).map(([key]) => /** @type {Hole} */ (key.split(",").map(Number)));
}

/**
 * @typedef {{net: string, a: Hole, b: Hole}} Strand a ratsnest line: two pieces of `net` not joined yet
 * @typedef {{marks: Record<string, Array<[number, number, number]>>, ratsnest: Strand[], cuts: Hole[],
 *   links: Array<[Hole, Hole]>, stuck: string[], next: {ref: string, why: string} | null}} Guidance
 *   what `/api/stripboard` sends to guide the next step (guidance.py, D-377): each net's
 *   free copper as runs, the ratsnest, the suggested cuts and links, a sentence per join no
 *   suggested link makes (why, what to do), what to place next
 */

/**
 * The holes marked for a part being carried: the free copper of each of its legs' nets,
 * where that leg would join its net (none for a net not on the board yet).
 * @param {Progress} progress @param {Guidance} guidance @param {string} ref @returns {Hole[]}
 */
export function markedHoles(progress, guidance, ref) {
  const nets = new Set((progress.legs[ref] ?? []).map((l) => l.net).filter((n) => n !== null));
  /** @type {Hole[]} */
  const holes = [];
  for (const net of nets) {
    const runs = guidance.marks[/** @type {string} */ (net)] ?? [];
    for (const [strip, c0, c1] of runs) {
      for (let c = c0; c <= c1; c++) holes.push([c, strip]);
    }
  }
  return holes;
}

/**
 * A board part's leg as the builder reads it: a chip's "pin 3", a trimmer's "lug 2", a
 * named leg as it is ("B", "K"), else "leg 1".
 * @param {Footprint | undefined} fp @param {string} leg
 */
export function legLabel(fp, leg) {
  if (!/^\d+$/.test(leg)) return leg;
  if (fp?.shape === "dip" || fp?.shape === "sil") return `pin ${leg}`;
  return fp?.kind === "trimmer" ? `lug ${leg}` : `leg ${leg}`;
}

/**
 * @typedef {{to: string, words: string, state: "joined" | "apart" | "unplaced", lug: boolean}} NeedReach
 *   a terminal a leg must reach; `lug`: an off-board lug (its "unplaced" is "not wired")
 * @typedef {{leg: string, hole: string | null, net: string | null, reach: NeedReach[]}} Need
 */

/**
 * A part's needs, leg by leg (spec, *Guidance as you edit*): each leg's hole and net, and
 * the terminals it must reach: joined already, apart (placed or wired, not joined), or not
 * placed or wired yet. `lugWords` names an off-board lug ("VR1 lug 2").
 * @param {Progress} progress @param {string} ref @param {(end: string) => string} lugWords @returns {Need[]}
 */
export function legNeeds(progress, ref, lugWords) {
  const fp = progress.footprints[ref];
  const unwired = new Set(progress.wires_to_go);
  return (progress.legs[ref] ?? []).map((l) => ({
    leg: legLabel(fp, l.leg),
    hole: l.hole,
    net: l.net,
    reach: l.reach.map((r) => {
      const dot = r.to.lastIndexOf(".");
      const other = dot > 0 ? r.to.slice(0, dot) : "";
      const legs = progress.legs[other];
      if (!legs) return { to: r.to, words: lugWords(r.to), state: r.joined ? "joined" : unwired.has(r.to) ? "unplaced" : "apart", lug: true };
      const leg = r.to.slice(dot + 1);
      const placed = legs.find((x) => x.leg === leg)?.hole;
      return { to: r.to, words: `${other} ${legLabel(progress.footprints[other], leg)}`, state: r.joined ? "joined" : placed ? "apart" : "unplaced", lug: false };
    }),
  }));
}

/**
 * The nets a board part's legs are on (to light their ratsnest lines).
 * @param {Progress} progress @param {string} ref @returns {Set<string>}
 */
export function netsOf(progress, ref) {
  return new Set((progress.legs[ref] ?? []).map((l) => l.net).filter((n) => n !== null));
}

/**
 * The suggested cuts and links in words, for the button that makes them all: "Make the
 * suggested cut and 2 links"; "" when there are none.
 * @param {Guidance} guidance
 */
export function suggestionsLine(guidance) {
  const cuts = guidance.cuts.length;
  const links = guidance.links.length;
  if (!cuts && !links) return "";
  const said = (/** @type {number} */ n, /** @type {string} */ word) => (n === 1 ? `${word}` : `${n} ${word}s`);
  const parts = [cuts ? said(cuts, "cut") : "", links ? said(links, "link") : ""].filter(Boolean);
  return `Make the suggested ${parts.join(" and ")}`;
}
