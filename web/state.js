/**
 * App state helpers: pure functions and small schedulers, no DOM.
 */

/**
 * `circuit` with its knobs where `values` has them (D-102): a pot's (or the guitar
 * volume's) `rotation`, a switch's `position`, per control. The circuit itself holds the
 * opening positions; this is the circuit as played. Parts not in it are skipped. The same
 * object when nothing differs, so it can stand as a cache key. The server validates the
 * result, so this only copies and sets.
 * @template {{parts: Array<{ref: string, [k: string]: any}>}} C
 * @param {C} circuit @param {Array<{ref: string, kind: string, refs?: string[], plug?: boolean}>} controls @param {Record<string, number>} values
 * @returns {C}
 */
export function withControls(circuit, controls, values) {
  const set = new Map();
  for (const c of controls) {
    if (!(c.ref in values)) continue;
    // a switch's knob turns every pole (`refs`, D-143); a `plug` knob (the DC jack's Power,
    // a stereo jack's cable, D-185) is its part's `plugged`, in at position 0
    for (const ref of c.refs ?? [c.ref]) {
      set.set(ref, c.plug ? ["plugged", values[c.ref] === 0] : [c.kind === "switch" ? "position" : "rotation", values[c.ref]]);
    }
  }
  let changed = false;
  const parts = circuit.parts.map((p) => {
    const [field, value] = set.get(p.ref) ?? [];
    if (field === undefined || p[field] === value) return p;
    changed = true;
    return { ...p, [field]: value };
  });
  return changed ? { ...circuit, parts } : circuit;
}

/**
 * A control's opening position, as the server's view gives it (defaults filled in): a
 * switch's `position`, a pot's `rotation`.
 * @param {{kind: string, rotation?: number, position?: number}} c
 * @returns {number | undefined}
 */
export const openingOf = (c) => (c.kind === "switch" ? c.position : c.rotation);

/**
 * The knobs' positions after a circuit changed (D-102): each control keeps where it was
 * turned to, unless its opening position changed (an edit to it, or undo), when it goes
 * there; a new control starts at its opening position.
 * @param {Array<{ref: string, kind: string, rotation?: number, position?: number}>} controls the new ones
 * @param {Array<{ref: string, kind: string, rotation?: number, position?: number}>} old the ones before
 * @param {Record<string, number>} values where the knobs are now
 * @returns {Record<string, number>}
 */
export function keptControls(controls, old, values) {
  const was = new Map(old.map((c) => [c.ref, openingOf(c)]));
  return Object.fromEntries(controls.map((c) => {
    const now = openingOf(c);
    return [c.ref, c.ref in values && was.get(c.ref) === now ? values[c.ref] : now];
  }));
}

/**
 * Hands out tokens so only the newest request's answer is used (older ones that
 * arrive late are dropped).
 */
export function latestOnly() {
  let counter = 0;
  return {
    next: () => ++counter,
    /** @param {number} token */
    isCurrent: (token) => token === counter,
  };
}

/**
 * Call `fn` once calls stop for `ms` milliseconds; the last arguments win.
 * @template {unknown[]} A
 * @param {(...args: A) => void} fn
 * @param {number} ms
 * @param {{setTimeout: typeof setTimeout, clearTimeout: typeof clearTimeout}} [timers]
 */
export function debounce(fn, ms, timers = globalThis) {
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let pending;
  return (/** @type {A} */ ...args) => {
    if (pending !== undefined) timers.clearTimeout(pending);
    pending = timers.setTimeout(() => {
      pending = undefined;
      fn(...args);
    }, ms);
  };
}

/**
 * `fn`, never twice at once: a call made while it runs waits for that run to end, then
 * runs once, however many calls came in meanwhile (they share that one run and its
 * answer). For a knob turned faster than its runs come back: only the newest position
 * is run next, instead of one run per tap lining up at the server (Phase 10, D-276).
 * @template T
 * @param {() => Promise<T> | T} fn
 * @returns {() => Promise<T>}
 */
export function oneAtATime(fn) {
  /** @type {Promise<T> | null} */
  let running = null;
  /** @type {Promise<T> | null} */
  let waiting = null;
  return function call() {
    if (!running) {
      running = (async () => fn())().finally(() => {
        running = null;
      });
      return running;
    }
    waiting ??= running.then(() => {}, () => {}).then(() => {
      waiting = null;
      return call();
    });
    return waiting;
  };
}

/** Which pin's net a part view probes ("at this point"), by part type. */
const FOCUS_PIN = {
  resistor: "2", capacitor: "2", inductor: "2", pot: "2", trimmer: "2", diode: "A", led: "A",
  opamp: "out", guitar: "out", amp: "in", vsource: "+", // a switch: its first pin, the common
};

/**
 * The net to probe alongside a part's own view: the transistor stage's output terminal
 * (as the server judged it), otherwise a fixed pin per type.
 * @param {{type: string, pins: Record<string, {net: string}>, detail: any}} partView
 * @returns {string}
 */
export function focusNet(partView) {
  const stagePin = partView.detail?.stage?.terminal;
  const pin = stagePin ?? FOCUS_PIN[partView.type] ?? Object.keys(partView.pins)[0];
  return (partView.pins[pin] ?? Object.values(partView.pins)[0]).net;
}
