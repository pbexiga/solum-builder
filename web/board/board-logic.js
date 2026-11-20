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
 *   standing?: string[], cuts?: string[], links?: string[][], pads?: Record<string, string[]>}} BoardData
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
 * The board read from its plain form: each placed part's legs in holes, the cuts, links
 * and pads. Names that aren't holes are left out (the server's check names them).
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
    pads: Object.entries(data?.pads ?? {}).flatMap(([name, ends]) => {
      const hole = parseHole(name);
      return hole ? [{ hole, ends }] : [];
    }),
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
 * The board's header line: "12 × 9, 1 cut, 2 links"; an empty board says so.
 * @param {Board} board
 */
export function sizeLine(board) {
  if (!board.columns || !board.strips) return "Empty board";
  const plural = (/** @type {number} */ n, /** @type {string} */ word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return `${board.columns} × ${board.strips}, ${plural(board.cuts.length, "cut")}, ${plural(board.links.length, "link")}`;
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
 *   pieces: number, shorts: Array<{other: string, words: string}>}} NetProgress
 * @typedef {{leg: string, hole: string | null, net: string | null, reach: Array<{to: string, joined: boolean}>}} LegProgress
 * @typedef {{to_place: string[], pads_to_place: string[], nets: NetProgress[],
 *   legs: Record<string, LegProgress[]>, faults: string[], stale: string[], warnings: string[],
 *   done: boolean, nets_done: number, footprints: Record<string, Footprint>}} Progress
 *   what `/api/stripboard` answers (check.py's `Progress`, with the footprints)
 */

const SHAPE_WORDS = /** @type {Record<string, string>} */ ({ axial: "axial", radial: "radial", inline: "in a line", dip: "DIP", sil: "SIL" });

/**
 * The tray's rows: each part still to place, with its value and footprint, then each
 * off-board wire end still without a pad.
 * @param {Progress} progress @param {any} circuit
 * @returns {Array<{ref: string, value: string, shape: string}>}
 */
export function trayRows(progress, circuit) {
  const parts = progress.to_place.map((ref) => {
    const fp = progress.footprints[ref];
    const pins = fp?.legs.length ?? 0;
    const shape = fp ? (fp.shape === "dip" ? `DIP-${pins}` : SHAPE_WORDS[fp.shape] ?? fp.shape) : "";
    return { ref, value: valueOf(circuit, ref, fp?.refs ?? [ref]), shape };
  });
  const wires = progress.pads_to_place.map((end) => ({ ref: end, value: "", shape: "off-board wire" }));
  return [...parts, ...wires];
}

/**
 * The Nets pane's line: "18 of 24 nets done", or "All 24 nets done".
 * @param {Progress} progress
 */
export function netsLine(progress) {
  const total = progress.nets.length;
  if (!total) return "No nets to join.";
  return progress.nets_done === total ? `All ${total} nets done.` : `${progress.nets_done} of ${total} nets done.`;
}

/**
 * Each net's state in words: done; in pieces ("2 of 4 pins placed, in 2 pieces");
 * shorted (each short's sentence).
 * @param {NetProgress} net @returns {string}
 */
export function netWords(net) {
  if (net.state === "shorted") return net.shorts.map((s) => s.words).join(" ");
  if (net.state === "done") return "done";
  const placed = `${net.placed} of ${net.total} placed`;
  return net.pieces > 1 ? `${placed}, in ${net.pieces} pieces` : placed;
}

/**
 * The board parts with a leg on `net` (to light a probed net on the board).
 * @param {Progress} progress @param {string} net
 */
export function partsOnNet(progress, net) {
  return Object.entries(progress.legs).filter(([, legs]) => legs.some((l) => l.hole && l.net === net)).map(([ref]) => ref);
}
