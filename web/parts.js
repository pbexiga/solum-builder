/**
 * Tools → Parts and datasheets, its logic (9c; DOM-free so it can be tested): the models
 * grouped by type, a search over them, and each one's origin in plain words. Every fact is
 * the server's (`/api/models/catalogue`, `Model.catalogue_entry`): this only words it.
 *
 * A card we may not ship (origin `excluded`, `solum/not_included.py`) has no card here: it
 * adds why (`why`), what to download (`get`, `url`) and its name in that file (`card`).
 *
 * @typedef {{id: string, type: string, description: string, maker: string, origin: "ours" | "estimate" | "library" | "maker" | "user" | "excluded",
 *   origin_detail: string, datasheet: string, package: string, sheet: string, figure: string, note: string,
 *   checks: number, unchecked: Array<{quantity: string, name: string, note: string}>,
 *   why?: string, get?: string, url?: string, card?: string}} PartEntry
 */

/** Model types in the order the list shows them, with their headings. */
export const TYPE_NAMES = /** @type {Record<string, string>} */ ({
  bjt: "Transistors (BJT)",
  jfet: "JFETs",
  mosfet: "MOSFETs",
  diode: "Diodes",
  led: "LEDs",
  opamp: "Op-amps",
  ota: "OTAs",
  inverter: "CMOS inverters",
  chargepump: "Charge pumps",
  regulator: "Regulators",
});

/** A short tag for where the card came from. */
export const ORIGIN_TAGS = /** @type {Record<PartEntry["origin"], string>} */ ({
  ours: "Our fit",
  estimate: "Estimate",
  library: "Library card",
  maker: "Maker's model",
  user: "Yours",
  excluded: "Not included",
});

/**
 * Where a model's card came from, in a sentence.
 * @param {PartEntry} e
 */
export function originText(e) {
  switch (e.origin) {
    case "ours":
      return `Our own model, fitted to ${e.origin_detail}.`;
    case "estimate":
      return `An estimate, not a fit: ${e.origin_detail}. Measure your part and give its gain and leakage.`;
    case "library":
      return `${e.maker ? `${e.maker}${e.maker.endsWith("s") ? "'" : "'s"} card` : "A card with no maker named"}, as published in a SPICE library (KiCad-Spice-Library, ${e.origin_detail}); checked here against the datasheet.`;
    case "user":
      return `Added by you from ${e.origin_detail} (Tools → Add a model); it's checked only by the readings it got then.`;
    default:
      return `The maker's own model (${e.origin_detail}).`;
  }
}

/**
 * The datasheet checks in words: how many it meets, and how many figures it's only
 * compared with.
 * @param {PartEntry} e
 */
export function checksText(e) {
  const met = e.checks === 0 ? "No datasheet limits to check it against." : `Meets ${e.checks === 1 ? "the 1 datasheet limit" : `all ${e.checks} datasheet limits`} it's checked against.`;
  return e.unchecked.length ? `${met} Compared with ${e.unchecked.length === 1 ? "1 more figure" : `${e.unchecked.length} more figures`} the sheet gives no limit for:` : met;
}

/** The toggles beside the search (9c), each on or off: which entries each one shows. */
export const SHOWS = /** @type {Record<string, [string, (e: PartEntry) => boolean]>} */ ({
  yours: ["Yours", (e) => e.origin === "user"],
  stock: ["Stock", (e) => e.origin !== "user" && e.origin !== "excluded"],
  excluded: ["Not included", (e) => e.origin === "excluded"],
});

/**
 * A card we may not ship, in words for its ⓘ (9c): why it isn't included, what to get, and
 * how to add it; the link goes after the second line. The LM13700 is an OTA, which Add a
 * model doesn't take yet.
 * @param {PartEntry} e
 * @returns {string[]}
 */
export function excludedText(e) {
  const add = e.type === "ota"
    ? "Tools → Add a model doesn't take OTAs yet, so it can't be added for now."
    : `Then add its card, ${e.card}, with Tools → Add a model; once added, your copy shows in this list instead.`;
  return [`Not included with Solum Builder. ${e.why ?? ""}`.trim(), `To use it, get ${e.get ?? "its file"}:`, add];
}

/**
 * The entries that match a search (id, description, maker or package; any case) and that
 * a toggle that's on shows (`SHOWS`), grouped by type in `TYPE_NAMES` order (a type it
 * doesn't know goes last, under its own name); within a type, yours first, then stock, then
 * the cards not included (9c).
 * @param {PartEntry[]} entries @param {string} query @param {string[]} [on] the `SHOWS` keys turned on
 * @returns {Array<{type: string, name: string, entries: PartEntry[]}>}
 */
export function partGroups(entries, query, on = Object.keys(SHOWS)) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const kept = (/** @type {PartEntry} */ e) => on.some((key) => SHOWS[key][1](e));
  const hit = (/** @type {PartEntry} */ e) => {
    const text = `${e.id} ${e.description} ${e.maker} ${e.package} ${TYPE_NAMES[e.type] ?? e.type}`.toLowerCase();
    return kept(e) && words.every((w) => text.includes(w));
  };
  const rank = (/** @type {PartEntry} */ e) => (e.origin === "user" ? 0 : e.origin === "excluded" ? 2 : 1);
  const mineFirst = (/** @type {PartEntry[]} */ list) => [0, 1, 2].flatMap((r) => list.filter((e) => rank(e) === r));
  const order = [...Object.keys(TYPE_NAMES), ...new Set(entries.map((e) => e.type).filter((t) => !(t in TYPE_NAMES)))];
  return order
    .map((type) => ({ type, name: TYPE_NAMES[type] ?? type, entries: mineFirst(entries.filter((e) => e.type === type && hit(e))) }))
    .filter((g) => g.entries.length);
}
