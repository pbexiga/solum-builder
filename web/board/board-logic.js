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
 * @typedef {{from: string, hole?: string, lug?: string}} WireData an off-board wire (D-375):
 *   from a lug to a hole, to another lug, or loose
 * @typedef {{shape: string, kind: string, legs: string[], steps: number[], flat: number,
 *   stand: number, length: number, width: number, diameter: number, row_holes: number,
 *   refs: string[]}} Footprint what `/api/stripboard` sends to draw a board part by
 * @typedef {{kind: "rect", x: number, y: number, w: number, h: number, angle: number, cx: number, cy: number}
 *   | {kind: "circle", cx: number, cy: number, r: number}
 *   | {kind: "lead", x1: number, y1: number, x2: number, y2: number}} Shape
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
    wires: (data?.wires ?? []).map((w) => ({ lug: w.from, hole: w.hole ? parseHole(w.hole) : null, to: w.lug ?? null })),
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

/**
 * The part's body and leads, in board units: a body (a rectangle along the legs' line, or
 * a circle) over the middle of its legs, a lead from each leg to it. A standing axial
 * part's body is a circle over its first leg, a lead down to the other.
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
  const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
  const cy = points.reduce((s, p) => s + p[1], 0) / points.length;
  if (fp.diameter) return [...leadsTo([cx, cy]), { kind: "circle", cx, cy, r: (fp.diameter * MM) / 2 }];
  // along the legs' line: first to last leg; a DIP's along its row, pin 1 to the row's last
  const end = fp.shape === "dip" ? points[Math.max(0, points.length / 2 - 1)] : points[points.length - 1];
  const angle = (Math.atan2(end[1] - points[0][1], end[0] - points[0][0]) * 180) / Math.PI;
  const span = Math.hypot(end[0] - points[0][0], end[1] - points[0][1]);
  const length = fp.length ? fp.length * MM : span + STEP * 0.8;
  const width = Math.max(fp.width * MM, STEP * 0.5);
  const body = /** @type {Shape} */ ({ kind: "rect", x: cx - length / 2, y: cy - width / 2, w: length, h: width, angle: Math.round(angle * 1000) / 1000, cx, cy });
  // a DIP's legs sit under its body: no leads to draw
  return fp.shape === "dip" ? [body] : [...leadsTo([cx, cy]), body];
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
 *   size: [number, number]}} OffItem an off-board part beside the board (D-375), its drawing `size` in holes
 * @typedef {{to_place: string[], wires_to_go: string[], loose: number, items: OffItem[],
 *   spots: Record<string, Hole>, stock: string[],
 *   unplaceable: string[], nets: NetProgress[],
 *   legs: Record<string, LegProgress[]>, faults: string[], stale: string[], warnings: string[],
 *   done: boolean, nets_done: number, footprints: Record<string, Footprint>, start_size: [number, number],
 *   shorted: Array<[number, number, number]>}} Progress
 *   what `/api/stripboard` answers (check.py's `Progress`, with the footprints)
 */

const SHAPE_WORDS = /** @type {Record<string, string>} */ ({ axial: "axial", radial: "radial", inline: "in a line", dip: "DIP", sil: "SIL" });

/**
 * @typedef {{ref: string, value: string, shape: string, mark?: string, kind?: string, select?: string, item?: string}} TrayRow
 *   `mark`: the footprint's shape, for the little drawing beside it; `select`: the
 *   circuit part a click selects (none for stock hardware); `item`: the off-board part
 *   it is, dragged out beside the board (D-375)
 */

/**
 * The tray's on-board rows: each part still to place, with its value and footprint.
 * @param {Progress} progress @param {any} circuit @returns {TrayRow[]}
 */
export function trayRows(progress, circuit) {
  return progress.to_place.map((ref) => {
    const fp = progress.footprints[ref];
    const pins = fp?.legs.length ?? 0;
    const shape = fp ? (fp.shape === "dip" ? `DIP-${pins}` : SHAPE_WORDS[fp.shape] ?? fp.shape) : "";
    return { ref, value: valueOf(circuit, ref, fp?.refs ?? [ref]), shape, mark: fp?.shape ?? "", kind: fp?.kind ?? "", select: ref };
  });
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

const STOCK_WORDS = /** @type {Record<string, TrayRow>} */ ({
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
 * list names it (its details, else what it is), `item` set so it can be dragged out; then
 * the stock footswitch and status LED the schematic doesn't draw (D-370).
 * @param {Progress} progress @param {Board} board @returns {TrayRow[]}
 */
export function offBoardRows(progress, board) {
  const parts = progress.items.filter((i) => !isOut(i, board)).map((i) => ({ ref: i.name, value: i.value, shape: i.details || i.kind, select: itemRefs(i)[0], item: i.ref }));
  return [...parts, ...progress.stock.map((id) => STOCK_WORDS[id] ?? { ref: id, value: "", shape: "stock" })];
}

/**
 * @typedef {{x: number, y: number, w: number, h: number}} Box
 * @typedef {{end: string, label: string, x: number, y: number}} LugAt
 */

/**
 * An off-board part's drawing with its corner at hole `at`: its body, and its lugs in a
 * row along the bottom, `LUG_GAP` holes apart (offboard.py's `LUG_GAP`), in board units.
 * @param {OffItem} item @param {Hole} at @returns {{body: Box, lugs: LugAt[]}}
 */
export function itemShape(item, at) {
  const [w, h] = item.size;
  const [x0, y0] = holeXY(at);
  const body = { x: x0 - STEP / 2, y: y0 - STEP / 2, w: w * STEP, h: (h - 1) * STEP };
  const lugs = item.lugs.map((lug, i) => ({ end: lug.end, label: lug.label, x: x0 + (1 + 2 * i) * STEP, y: y0 + (h - 1) * STEP }));
  return { body, lugs };
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
    for (const lug of itemShape(item, board.spots[item.ref] ?? progress.spots[item.ref]).lugs) at[lug.end] = lug;
  }
  return at;
}

export const LOOSE_DROP = STEP * 1.6; // how far a loose wire hangs below its lug

/**
 * A wire's line in board units: from its lug to its hole, to its other lug, or hanging
 * loose below its lug; null when its lug isn't drawn.
 * @param {{lug: string, hole: Hole | null, to: string | null}} wire @param {Record<string, LugAt>} lugs
 * @returns {{x1: number, y1: number, x2: number, y2: number, loose: boolean} | null}
 */
export function wireLine(wire, lugs) {
  const from = lugs[wire.lug];
  if (!from) return null;
  if (wire.hole) {
    const [x2, y2] = holeXY(wire.hole);
    return { x1: from.x, y1: from.y, x2, y2, loose: false };
  }
  const to = wire.to ? lugs[wire.to] : null;
  if (to) return { x1: from.x, y1: from.y, x2: to.x, y2: to.y, loose: false };
  return { x1: from.x, y1: from.y, x2: from.x, y2: from.y + LOOSE_DROP, loose: true };
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
 * (`solum.board`). `acts`: whether it does anything yet (the rest come with the editing
 * and guidance they belong to, P6b and P6c).
 */
export const BOARD_SETTINGS = /** @type {const} */ ([
  { key: "values", label: "Show values", on: true, acts: true, title: "Label each part with its value as well as its ref" },
  { key: "next", label: "What to place next", on: true, acts: false, title: "Suggest the part to place next" },
  { key: "shorts", label: "Allow shorts while editing, shown red", on: true, acts: true, title: "Off: a move that makes a short is refused" },
  { key: "grow", label: "Auto-grow", on: true, acts: true, title: "The board grows to take in what's placed by its edge, and shrinks back. Off: it stays its size (the margin greyed); add or remove lines on the rulers" },
  { key: "seeThrough", label: "See-through", on: false, acts: false, title: "The copper side faint under the parts" },
]);

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
  } else {
    const step = fp.shape === "axial" && pose.standing ? fp.stand : pose.span;
    at = fp.legs.map((_, i) => [0, i * step]);
  }
  const names = pose.flipped && fp.shape !== "dip" ? [...fp.legs].reverse() : fp.legs;
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
  const span = fp.shape === "dip" ? 0 : fp.shape === "axial" && standing ? fp.flat : Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
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
 * span, a radial or a line through its footprint's spacings). Null when the move doesn't
 * apply to this part.
 * @param {Footprint} fp @param {Pose} pose @param {"turn" | "flip" | "stand" | "longer" | "shorter"} move
 * @returns {Pose | null}
 */
export function posed(fp, pose, move) {
  if (move === "turn") return { ...pose, turns: (pose.turns + (fp.shape === "dip" ? 2 : 1)) % 4 };
  if (move === "flip") return fp.shape === "dip" ? null : { ...pose, flipped: !pose.flipped };
  if (move === "stand") return fp.shape === "axial" ? { ...pose, standing: !pose.standing, span: fp.flat } : null;
  if (fp.shape === "dip" || pose.standing) return null;
  const by = move === "longer" ? 1 : -1;
  if (fp.shape === "axial") {
    const span = pose.span + by;
    return span >= fp.flat ? { ...pose, span } : null;
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
 * The red copper of a short (`progress.shorted`: [strip, first column, last column] runs).
 * @param {Array<[number, number, number]>} runs
 */
export function shortedRects(runs) {
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
