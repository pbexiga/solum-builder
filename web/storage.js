/**
 * What the page remembers between visits, the one place it is read and written (D-282).
 * Two homes (D-311):
 * - the preferences in `SERVER_KEYS` (theme, large views, auto-run, pane order, open
 *   panes) are the server's, in its settings file: it sends them inside the page
 *   (`<script id="solum-prefs">`), so reading stays immediate, and a change goes to
 *   `PUT /api/settings`. They follow the person to any browser or port;
 * - everything else is JSON in this browser's `localStorage`.
 * Storage can be blocked (a private window), hold something garbled, or the server be
 * away: reading then gives null and writing does nothing, so every caller falls back to
 * its defaults and the choice lasts for the visit.
 */

import { request } from "./api.js";

/** The keys the server keeps; `solum/settings_file.py` has the same list. */
export const SERVER_KEYS = ["solum.theme", "solum.large", "solum.autorun", "solum.panes", "solum.panes.open"];

/** @param {Storage | null} [storage] undefined: the browser's own */
const storeOf = (storage) => (storage === undefined ? globalThis.localStorage : storage);

/** @param {string} key @param {Storage | null} [storage] @returns {any} */
function localRead(key, storage) {
  try {
    return JSON.parse(storeOf(storage)?.getItem(key) ?? "null");
  } catch {
    return null;
  }
}

/** @param {string} key @param {unknown} value @param {Storage | null} [storage] */
function localWrite(key, value, storage) {
  try {
    if (value === null) storeOf(storage)?.removeItem(key);
    else storeOf(storage)?.setItem(key, JSON.stringify(value));
  } catch {
    // storage blocked: it just isn't remembered
  }
}

/**
 * The server's preferences as this page holds them. Changes are sent one request at a
 * time, the ones made meanwhile together in the next, so they arrive in order.
 * The first visit after they moved (`sent` null: the server keeps none yet) carries this
 * browser's own old values over, once; after that the browser's copies are dropped.
 * @param {unknown} sent what the page was served with
 * @param {Storage | null | undefined} local the browser's storage (null: none)
 * @param {(changes: Record<string, unknown>) => Promise<unknown>} send to the server; a null forgets a key
 * @param {(saving: boolean) => void} [onSaving] told when changes start and stop being on their way
 * @returns {{get: (key: string) => any, set: (key: string, value: unknown) => void, flush: () => void}}
 *   `flush`: send what is waiting now (the page is going away)
 */
export function serverKept(sent, local, send, onSaving = () => {}) {
  /** @type {Record<string, unknown>} */
  const kept = sent && typeof sent === "object" ? { ...sent } : {};
  /** @type {Record<string, unknown> | null} */
  let waiting = null;
  let busy = false;
  const forgetLocal = () => SERVER_KEYS.forEach((key) => localWrite(key, null, local));
  /** @param {() => void} [then] */
  const sendNext = (then) => {
    if (busy || !waiting) return;
    const changes = waiting;
    waiting = null;
    busy = true;
    onSaving(true);
    send(changes).then(then, () => {}).finally(() => {
      busy = false;
      if (waiting) sendNext();
      else onSaving(false);
    });
  };
  if (sent === null) {
    for (const key of SERVER_KEYS) {
      const old = localRead(key, local);
      if (old !== null) kept[key] = old;
    }
    waiting = { ...kept }; // sent even when empty: the server then knows it has been asked
    sendNext(forgetLocal); // the browser's copies go once the server has them
  } else {
    forgetLocal();
  }
  return {
    get: (key) => kept[key] ?? null,
    set(key, value) {
      // as it is already (the panes save their state as the page fills): nothing to send
      if (JSON.stringify(kept[key] ?? null) === JSON.stringify(value)) return;
      if (value === null) delete kept[key];
      else kept[key] = value;
      waiting = { ...waiting, [key]: value };
      sendNext();
    },
    flush() {
      if (!waiting) return;
      send(waiting).catch(() => {});
      waiting = null;
    },
  };
}

/** @type {ReturnType<typeof serverKept> | null} */
let fromServer = null;

/** This page's server preferences, read from the page the first time one is asked for. */
function server() {
  if (fromServer) return fromServer;
  let sent = null;
  try {
    sent = JSON.parse(globalThis.document?.getElementById("solum-prefs")?.textContent ?? "null");
  } catch {
    sent = null;
  }
  // keepalive: a change made just before a reload still arrives. While one is on its way
  // <html data-saving> says so (the UI tests wait for it to go before they reload)
  const kept = serverKept(sent, undefined, (changes) => request("api/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preferences: changes }), keepalive: true,
  }), (saving) => globalThis.document?.documentElement.toggleAttribute("data-saving", saving));
  globalThis.addEventListener?.("pagehide", kept.flush);
  fromServer = kept;
  return kept;
}

/**
 * @param {string} key @param {Storage | null} [storage] another store (tests), null for none; the server's keys don't use it
 * @returns {any} what was kept under `key`, or null
 */
export function remembered(key, storage) {
  return SERVER_KEYS.includes(key) ? server().get(key) : localRead(key, storage);
}

/** @param {string} key @param {unknown} value null forgets it @param {Storage | null} [storage] */
export function remember(key, value, storage) {
  if (SERVER_KEYS.includes(key)) server().set(key, value);
  else localWrite(key, value, storage);
}
