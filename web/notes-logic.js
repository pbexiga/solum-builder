/**
 * The circuit's notes (9d4, D-267), DOM-free: general notes (`notes`, titled), a part's
 * note (on the part, `note`) and a named net's (`net_notes`). Each edit returns a new
 * circuit (the input is never changed), so it goes through the editor's normal path.
 * Also finds the notes that mention a renamed part or net, and replaces those mentions
 * the user ticked: note text is never rewritten on its own (it may cite a source's refs).
 *
 * @typedef {import("./editor/edit.js").Circuit} Circuit
 * @typedef {import("./editor/edit.js").Note} Note
 * @typedef {{kind: "general", index: number} | {kind: "part", ref: string} | {kind: "net", net: string}} Where
 * @typedef {{kind: "part" | "net", id: string, text: string}} ItemNote
 * @typedef {{from: string, to: string}} Rename
 * @typedef {{where: Where, field: "title" | "text", start: number, from: string, to: string,
 *   label: string, before: string, after: string}} Mention one whole-word mention of
 *   `from` in a note, with the text around it (`before`, `after`) for the list
 */

import { NOTE_MAX, NOTE_TITLE_MAX } from "./editor/blocks.js";
import { addLabel, pointOnWire } from "./editor/edit.js";

/** Characters of context shown each side of a mention. */
const CONTEXT = 30;

/**
 * The circuit with a general note added at the end.
 * @param {Circuit} circuit @param {Note} note @returns {Circuit}
 */
export function addNote(circuit, note) {
  return { ...circuit, notes: [...(circuit.notes ?? []), clean(note)] };
}

/**
 * General note `index` changed; with no title and no text left, it goes.
 * @param {Circuit} circuit @param {number} index @param {Note} note @returns {Circuit}
 */
export function setNote(circuit, index, note) {
  const kept = clean(note);
  if (!kept.title && !kept.text) return deleteNote(circuit, index);
  return { ...circuit, notes: (circuit.notes ?? []).map((n, i) => (i === index ? kept : n)) };
}

/** @param {Circuit} circuit @param {number} index @returns {Circuit} */
export function deleteNote(circuit, index) {
  const notes = (circuit.notes ?? []).filter((_n, i) => i !== index);
  const out = { ...circuit, notes };
  if (!notes.length) delete out.notes;
  return out;
}

/**
 * Part `ref`'s note set; empty text removes it.
 * @param {Circuit} circuit @param {string} ref @param {string} text @returns {Circuit}
 */
export function setPartNote(circuit, ref, text) {
  const kept = text.trim().slice(0, NOTE_MAX);
  const parts = circuit.parts.map((p) => {
    if (p.ref !== ref) return p;
    const { note: _old, ...rest } = p;
    return kept ? { ...rest, note: kept } : rest;
  });
  return { ...circuit, parts };
}

/**
 * Net `net`'s note set; empty text removes it.
 * @param {Circuit} circuit @param {string} net @param {string} text @returns {Circuit}
 */
export function setNetNote(circuit, net, text) {
  const kept = text.trim().slice(0, NOTE_MAX);
  const notes = { ...(circuit.net_notes ?? {}) };
  if (kept) notes[net] = kept;
  else delete notes[net];
  const out = { ...circuit, net_notes: notes };
  if (!Object.keys(notes).length) delete out.net_notes;
  return out;
}

/**
 * Every part and net note, as the Parts tab lists them: parts by ref (R2 before R10),
 * then nets by name.
 * @param {Circuit} circuit @returns {ItemNote[]}
 */
export function itemNotes(circuit) {
  const byRef = (/** @type {string} */ a, /** @type {string} */ b) => a.localeCompare(b, "en", { numeric: true });
  /** @type {ItemNote[]} */
  const parts = circuit.parts.filter((p) => p.note).map((p) => ({ kind: "part", id: p.ref, text: p.note }));
  /** @type {ItemNote[]} */
  const nets = Object.entries(circuit.net_notes ?? {}).map(([id, text]) => ({ kind: "net", id, text }));
  return [...parts.sort((a, b) => byRef(a.id, b.id)), ...nets.sort((a, b) => byRef(a.id, b.id))];
}

/**
 * Whether `net` is a named net: a label or a supply names it. An unnamed net's name is
 * one of its pins (`Q1.D`, D-082), which changes as the drawing does, so it takes a name
 * before a note (the user, 2026-11-10).
 * @param {Circuit} circuit @param {string} net
 */
export function isNamedNet(circuit, net) {
  return (circuit.labels ?? []).some((lb) => lb.net === net) || net in (circuit.power?.rails ?? {});
}

/**
 * Name an unnamed net so it can take a note: a label called `name` on wire `index`, at
 * the point nearest `at` (where the wire was right-clicked). Throws, in words, when the
 * name isn't one a net can have or another net has it (the label would join the two).
 * @param {Circuit} circuit @param {number} index @param {number[]} at @param {string} name
 * @returns {Circuit}
 */
export function nameNet(circuit, index, at, name) {
  if (!name) throw new Error("Give the net a name, like TONE or Q1C.");
  if (/[.\s]/.test(name)) throw new Error("A net's name has no spaces or dots.");
  if (isNamedNet(circuit, name) || name === "GND") throw new Error(`${name} is another net's name already: a label with it would join the two. Pick another.`);
  const wire = circuit.wires?.[index];
  if (!wire) throw new Error("That wire isn't there any more.");
  return addLabel(circuit, name, pointOnWire(wire, at));
}

/**
 * The renames a part form's change makes, for the notice: the part's own (`C7` → `C9`),
 * or for a chip, switch or dual pot every unit (`IC1A` → `IC2A`…) and its name (`IC1`
 * → `IC2`).
 * @param {string[]} before the units' refs before @param {string[]} after the same units' refs after, in order
 * @returns {Rename[]}
 */
export function renamesOf(before, after) {
  const pairs = before.map((from, i) => ({ from, to: after[i] })).filter((r) => r.to && r.from !== r.to);
  if (pairs.length > 1) {
    const stem = (/** @type {string} */ ref) => ref.slice(0, -1);
    const [from, to] = [stem(pairs[0].from), stem(pairs[0].to)];
    if (from !== to && pairs.every((r) => stem(r.from) === from && stem(r.to) === to)) pairs.unshift({ from, to });
  }
  return pairs;
}

/** @param {string} text */
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Where `name` appears as a whole word in `text` (C7, not C70, IC7 or C7A).
 * @param {string} text @param {string} name @returns {number[]}
 */
export function wordsAt(text, name) {
  if (!name) return [];
  const re = new RegExp(`(?<![A-Za-z0-9_])${escape(name)}(?![A-Za-z0-9_])`, "g");
  return [...text.matchAll(re)].map((m) => /** @type {number} */ (m.index));
}

/**
 * Every note's fields, with where each is and its name in the list.
 * @param {Circuit} circuit @returns {Array<{where: Where, field: "title" | "text", text: string, label: string}>}
 */
function fields(circuit) {
  /** @type {Array<{where: Where, field: "title" | "text", text: string, label: string}>} */
  const out = [];
  (circuit.notes ?? []).forEach((n, index) => {
    const label = n.title || "Untitled note";
    for (const field of /** @type {const} */ (["title", "text"])) if (n[field]) out.push({ where: { kind: "general", index }, field, text: n[field] ?? "", label });
  });
  for (const p of circuit.parts) if (p.note) out.push({ where: { kind: "part", ref: p.ref }, field: "text", text: p.note, label: `${p.ref}'s note` });
  for (const [net, text] of Object.entries(circuit.net_notes ?? {})) out.push({ where: { kind: "net", net }, field: "text", text, label: `${net}'s note` });
  return out;
}

/**
 * The mentions of each renamed name in the notes, in note order.
 * @param {Circuit} circuit @param {Rename[]} renames @returns {Mention[]}
 */
export function mentions(circuit, renames) {
  /** @type {Mention[]} */
  const out = [];
  for (const f of fields(circuit)) {
    for (const { from, to } of renames) {
      for (const start of wordsAt(f.text, from)) {
        const lead = Math.max(0, start - CONTEXT);
        const tail = Math.min(f.text.length, start + from.length + CONTEXT);
        out.push({
          where: f.where, field: f.field, start, from, to, label: f.label,
          before: (lead > 0 ? "…" : "") + f.text.slice(lead, start),
          after: f.text.slice(start + from.length, tail) + (tail < f.text.length ? "…" : ""),
        });
      }
    }
  }
  return out.sort((a, b) => fieldOrder(circuit, a) - fieldOrder(circuit, b) || a.start - b.start);
}

/** @param {Circuit} circuit @param {Mention} m */
function fieldOrder(circuit, m) {
  return fields(circuit).findIndex((f) => sameWhere(f.where, m.where) && f.field === m.field);
}

/** How many notes the mentions are in. @param {Mention[]} found */
export function notesCount(found) {
  return new Set(found.map((m) => whereKey(m.where))).size;
}

/** A key for a note's place: `g:2`, `p:R1`, `n:VREF`. @param {Where} where */
export function whereKey(where) {
  return where.kind === "general" ? `g:${where.index}` : where.kind === "part" ? `p:${where.ref}` : `n:${where.net}`;
}

/** @param {Where} a @param {Where} b */
const sameWhere = (a, b) => whereKey(a) === whereKey(b);

/**
 * The circuit with the given mentions replaced by their new names: one edit, so one undo
 * step. Mentions no longer where they were (the note changed since) are skipped.
 * @param {Circuit} circuit @param {Mention[]} picked @returns {Circuit}
 */
export function replaceMentions(circuit, picked) {
  let out = circuit;
  /** @type {Map<string, Mention[]>} */
  const byField = new Map();
  for (const m of picked) {
    const k = `${whereKey(m.where)}|${m.field}`;
    byField.set(k, [...(byField.get(k) ?? []), m]);
  }
  for (const group of byField.values()) {
    const { where, field } = group[0];
    let text = readField(out, where, field);
    if (text === null) continue;
    for (const m of [...group].sort((a, b) => b.start - a.start)) {
      if (text.slice(m.start, m.start + m.from.length) !== m.from) continue;
      text = text.slice(0, m.start) + m.to + text.slice(m.start + m.from.length);
    }
    out = writeField(out, where, field, text);
  }
  return out;
}

/** @param {Circuit} circuit @param {Where} where @param {"title" | "text"} field @returns {string | null} */
function readField(circuit, where, field) {
  if (where.kind === "general") return circuit.notes?.[where.index]?.[field] ?? null;
  if (where.kind === "part") return circuit.parts.find((p) => p.ref === where.ref)?.note ?? null;
  return circuit.net_notes?.[where.net] ?? null;
}

/** @param {Circuit} circuit @param {Where} where @param {"title" | "text"} field @param {string} text */
function writeField(circuit, where, field, text) {
  if (where.kind === "general") {
    const note = /** @type {Note} */ (circuit.notes?.[where.index]);
    return setNote(circuit, where.index, { ...note, [field]: text });
  }
  return where.kind === "part" ? setPartNote(circuit, where.ref, text) : setNetNote(circuit, where.net, text);
}

/** A note as saved: trimmed, within the schema's limits, empty fields left out. @param {Note} note */
function clean(note) {
  const title = (note.title ?? "").trim().slice(0, NOTE_TITLE_MAX);
  const text = (note.text ?? "").trim().slice(0, NOTE_MAX);
  return { ...(title ? { title } : {}), ...(text ? { text } : {}) };
}
