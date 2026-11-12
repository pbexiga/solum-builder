/**
 * Undo/redo as a command stack of whole-circuit snapshots (D-051). Every edit records the
 * circuit as it was before, with a label ("Move R1") and where it came from (`source`:
 * "curve" for Edit curve, "bias" for a Bias & headroom fix, else ""). Circuits are a few kilobytes and edits never mutate
 * them, so a snapshot is just a reference. An edit session (Edit curve, D-101; a bias fix, D-119) fences the
 * stack: undo stops at its start and redo at its end until it's kept (one step) or
 * discarded. `rows()` lists it for the History pane. No DOM.
 * Each step keeps the selection that went with its state (D-148), as editors do: undo
 * and redo put the circuit back and what was selected on it (`restored`), so a moved
 * selection is selected again, ready to move.
 * @template T
 */
export class History {
  /** @param {number} [limit] the most undo steps kept */
  constructor(limit = 200) {
    this.limit = limit;
    /** @type {Array<Step<T>>} each step with the state before it */
    this.past = [];
    /** @type {Array<Step<T>>} undone steps (the next to redo last), each with the state after it */
    this.future = [];
    this.dropped = 0; // steps pushed out by the limit, so a mark stays put
    /** @type {{mark: number, futureBase: number, name: string, source: string} | null} an edit session: where it began, the redo steps from before it, its name ("Edit curve", "Centre Q4") and the `source` its own edits carry */
    this.session = null;
    /** @type {unknown} the selection that went with the state the last undo or redo returned */
    this.restored = null;
  }

  /**
   * Record an edit: `before` is the state it replaced, `selection` what was selected on
   * it. Clears the redo list.
   * @param {T} before @param {string} label @param {string} [source] "curve": made in Edit curve
   * @param {unknown} [selection]
   */
  record(before, label, source = "", selection = null) {
    this.past.push({ label, state: before, source, selection });
    if (this.past.length > this.limit) {
      this.past.shift();
      this.dropped++;
    }
    this.future = [];
    if (this.session) this.session.futureBase = 0;
  }

  /** In an edit session, at its start: undo goes no further. */
  get atSessionStart() {
    return this.session !== null && this.mark() <= this.session.mark;
  }

  /**
   * Step back. Returns the state to show, or null when there's nothing to undo (or an
   * edit session is at its start); `restored` is then the selection that went with it.
   * `selection`: what's selected now, which a redo puts back.
   * @param {T} current @param {unknown} [selection]
   * @returns {T | null}
   */
  undo(current, selection = null) {
    if (this.atSessionStart) return null;
    const step = this.past.pop();
    if (!step) return null;
    this.future.push({ ...step, state: current, selection });
    this.restored = step.selection;
    return step.state;
  }

  /**
   * @param {T} current @param {unknown} [selection] what's selected now, which an undo puts back
   * @returns {T | null}
   */
  redo(current, selection = null) {
    if (this.session && this.future.length <= this.session.futureBase) return null;
    const step = this.future.pop();
    if (!step) return null;
    this.past.push({ ...step, state: current, selection });
    this.restored = step.selection;
    return step.state;
  }

  /** Drop an edit just recorded (it was refused), without touching redo. */
  discard() {
    this.past.pop();
  }

  /** Where the undo list is now, for `squash` or `rollback` later (an edit session). */
  mark() {
    return this.dropped + this.past.length;
  }

  /**
   * Start an edit session here (`squash` or `rollback` ends it).
   * @param {string} [name] what the History pane calls it @param {string} [source] the `source` its own edits carry
   * @returns {number} its mark
   */
  begin(name = "Edit curve", source = "curve") {
    this.session = { mark: this.mark(), futureBase: this.future.length, name, source };
    return this.session.mark;
  }

  /**
   * The steps recorded since `mark` become one, labelled `label` (an edit session kept).
   * @param {number} mark @param {string} label
   */
  squash(mark, label) {
    const base = this.session?.futureBase ?? 0;
    this.session = null;
    this.future.length = Math.min(this.future.length, base); // undone session steps go with it
    const at = Math.max(0, mark - this.dropped);
    if (this.past.length <= at) return;
    const first = this.past[at];
    this.past.length = at;
    this.past.push({ label, state: first.state, source: "", selection: first.selection });
  }

  /** Forget the steps recorded since `mark` (an edit session discarded). @param {number} mark */
  rollback(mark) {
    const base = this.session?.futureBase ?? 0;
    this.session = null;
    const at = Math.max(0, mark - this.dropped);
    if (this.past.length > at) this.past.length = at;
    this.future.length = Math.min(this.future.length, base); // redo from before the session stays
  }

  /**
   * Change every kept state (a file rename: the name isn't an edit, so no step may put
   * the old one back). @param {(state: T) => T} change
   */
  amend(change) {
    this.past = this.past.map((step) => ({ ...step, state: change(step.state) }));
    this.future = this.future.map((step) => ({ ...step, state: change(step.state) }));
  }

  clear() {
    this.past = [];
    this.future = [];
    this.session = null;
  }

  /** What Undo and Redo would do, for button titles (null where the session stops them). */
  get labels() {
    const undo = this.atSessionStart ? null : this.past.at(-1)?.label ?? null;
    const redo = this.session && this.future.length <= this.session.futureBase ? null : this.future.at(-1)?.label ?? null;
    return { undo, redo };
  }

  /**
   * The steps for the History pane, newest first: undone steps (`undone`), the step the
   * circuit is at (`current`), older ones (`done`), then `start` (before them all, or where
   * the limit cut them off). `go`: how many redos (+) or undos (−) reach it; `session`: made
   * in the edit session; `locked`: outside the session while one is open (can't be reached).
   * @returns {Array<{label: string, source: string, kind: "undone" | "current" | "done" | "start", go: number, session: boolean, locked: boolean}>}
   */
  rows() {
    const s = this.session;
    const at = s ? s.mark - this.dropped : Infinity; // past index where the session starts
    const undone = this.future.map((step, i) => {
      const go = this.future.length - i;
      const session = s !== null && i >= s.futureBase;
      return { label: step.label, source: step.source, kind: /** @type {const} */ ("undone"), go, session, locked: s !== null && !session };
    });
    const done = this.past.map((step, i) => {
      const go = i - (this.past.length - 1);
      const session = i >= at;
      return { label: step.label, source: step.source, kind: go === 0 ? /** @type {const} */ ("current") : /** @type {const} */ ("done"), go, session, locked: s !== null && !session && i < at - 1 };
    }).reverse();
    const start = { label: this.dropped ? "Older steps (past the undo limit)" : "Opened", source: "", kind: /** @type {const} */ ("start"), go: -this.past.length, session: false, locked: s !== null && this.past.length > 0 && at > 0 };
    // the step the session started after is reachable (it's where Undo stops): only older ones are locked
    return [...undone, ...done, start];
  }

  /**
   * The edit session's steps, oldest first, each with the states before and after it
   * (for Edit curve's Changed list: which parts changed together, which came from outside).
   * @param {T} current
   * @returns {Array<{label: string, source: string, before: T, after: T}>}
   */
  sessionSteps(current) {
    if (!this.session) return [];
    const at = Math.max(0, this.session.mark - this.dropped);
    return this.past.slice(at).map((step, k, steps) => ({
      label: step.label,
      source: step.source,
      before: step.state,
      after: k + 1 < steps.length ? steps[k + 1].state : current,
    }));
  }
}

/**
 * @template T
 * @typedef {{label: string, state: T, source: string, selection: unknown}} Step
 */
