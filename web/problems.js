/**
 * The Problems panel's logic, no DOM (D-077): counts for its heading and what a click on
 * a problem selects; dismissing and bringing back a problem, and where its mark goes on
 * the sheet (D-176). Problems come from `POST /api/problems`, already in plain English.
 */

/** @typedef {{rule: string, layer: string, severity: "error" | "warning" | "info", title: string,
 *   message: string, why: string, fix: string, refs: string[], nets: string[], build?: boolean}} Problem
 *   `build`: a build check, also in File → Export's Ready to build (D-203) */

const WORDS = { error: ["error", "errors"], warning: ["warning", "warnings"], info: ["note", "notes"] };

/**
 * "2 errors, 1 warning" (empty when there are none). @param {Problem[]} problems
 * @returns {string}
 */
export function problemCounts(problems) {
  return Object.entries(WORDS)
    .map(([severity, [one, many]]) => {
      const n = problems.filter((p) => p.severity === severity).length;
      return n ? `${n} ${n === 1 ? one : many}` : "";
    })
    .filter(Boolean)
    .join(", ");
}

/**
 * Identifies a problem across re-checks, to keep its row open. @param {Problem} p
 * @returns {string}
 */
export const problemKey = (p) => [p.rule, ...p.refs, ...p.nets].join("|");

/**
 * What clicking a problem selects: its part (probed like a click on it), else its first
 * net, else nothing. @param {Problem} problem
 * @returns {{kind: "part" | "net", id: string} | null}
 */
export function problemTarget(problem) {
  if (problem.refs.length) return { kind: "part", id: problem.refs[0] };
  if (problem.nets.length) return { kind: "net", id: problem.nets[0] };
  return null;
}

/**
 * A note for the build, not a problem with the circuit (D-203): a build check at note level
 * (a capacitor's type or rating not set, no package). The Problems panel keeps these under
 * Before you build, uncounted and unmarked; a build warning or error is a problem like any.
 * @param {Problem} p @returns {boolean}
 */
export const forTheBuild = (p) => Boolean(p.build) && p.severity === "info";

// ---- dismissed problems and marks on the sheet (D-176) ---------------------------

/** @typedef {{rule: string, refs?: string[], nets?: string[], reason?: string}} Dismissal
 *   a dismissed problem as the circuit file keeps it (`schema.Dismissal`) */

const same = (/** @type {string[] | undefined} */ a, /** @type {string[]} */ b) => (a ?? []).length === b.length && b.every((x, i) => (a ?? [])[i] === x);

/**
 * The dismissal that names this problem (same rule, refs and nets), if any.
 * @param {Problem} problem @param {Dismissal[] | undefined} dismissed
 * @returns {Dismissal | undefined}
 */
export function dismissalOf(problem, dismissed) {
  return (dismissed ?? []).find((d) => d.rule === problem.rule && same(d.refs, problem.refs) && same(d.nets, problem.nets));
}

/**
 * The problems still to see, and those dismissed with their reasons (in the list's order).
 * @param {Problem[]} problems @param {Dismissal[] | undefined} dismissed
 * @returns {{active: Problem[], dismissed: Array<{problem: Problem, reason: string}>}}
 */
export function splitDismissed(problems, dismissed) {
  /** @type {Problem[]} */ const active = [];
  /** @type {Array<{problem: Problem, reason: string}>} */ const gone = [];
  for (const p of problems) {
    const d = dismissalOf(p, dismissed);
    if (d) gone.push({ problem: p, reason: d.reason ?? "" });
    else active.push(p);
  }
  return { active, dismissed: gone };
}

/**
 * The circuit with this problem dismissed, `reason` kept when there is one (trimmed). A
 * problem already dismissed gets the new reason. The input isn't changed.
 * @param {any} circuit @param {Problem} problem @param {string} [reason]
 */
export function dismissProblem(circuit, problem, reason = "") {
  const why = reason.trim();
  /** @type {Dismissal} */
  const d = { rule: problem.rule, ...(problem.refs.length ? { refs: [...problem.refs] } : {}), ...(problem.nets.length ? { nets: [...problem.nets] } : {}), ...(why ? { reason: why } : {}) };
  return { ...circuit, dismissed: [...(restoreProblem(circuit, problem).dismissed ?? []), d] };
}

/**
 * The circuit with this problem brought back (its dismissal taken out); the list goes
 * when it's empty, as a file without dismissals has none.
 * @param {any} circuit @param {Problem} problem
 */
export function restoreProblem(circuit, problem) {
  const left = (circuit.dismissed ?? []).filter((/** @type {Dismissal} */ d) => !dismissalOf(problem, [d]));
  const { dismissed: _gone, ...rest } = circuit;
  return left.length ? { ...rest, dismissed: left } : rest;
}

/**
 * Where a problem's mark goes on the sheet (as KiCad's ERC markers): on the pin of its part
 * that is on its net, when exactly one is; else on its part; a problem naming only nets,
 * at its first net's anchor. Null when the drawing has none of these (a part since
 * deleted, a problem about the whole circuit). `view`: the server's circuit view.
 * @param {Problem} problem @param {any} view
 * @returns {{kind: "pin", ref: string, pin: string, pos: number[]} | {kind: "part", ref: string} | {kind: "net", net: string, pos: number[]} | null}
 */
export function markSpot(problem, view) {
  const [ref] = problem.refs;
  const part = ref ? view?.parts.find((/** @type {any} */ p) => p.ref === ref) : null;
  if (part) {
    const pins = problem.nets.length ? part.pins.filter((/** @type {any} */ pin) => pin.net === problem.nets[0]) : [];
    return pins.length === 1 ? { kind: "pin", ref, pin: pins[0].name, pos: pins[0].pos } : { kind: "part", ref };
  }
  if (ref) return null;
  const [net] = problem.nets;
  const anchor = net ? view?.nets[net]?.anchors[0] : null;
  return anchor ? { kind: "net", net, pos: anchor } : null;
}

/**
 * The marks to draw: one per problem not dismissed (nor a note for the build) that has a spot on the sheet, with its
 * key (to open its row), severity and message (the hover).
 * @param {Problem[]} problems @param {Dismissal[] | undefined} dismissed @param {any} view
 * @returns {Array<{key: string, severity: Problem["severity"], message: string, spot: NonNullable<ReturnType<typeof markSpot>>}>}
 */
export function problemMarks(problems, dismissed, view) {
  return splitDismissed(problems, dismissed).active.filter((p) => !forTheBuild(p)).flatMap((p) => {
    const spot = markSpot(p, view);
    return spot ? [{ key: problemKey(p), severity: p.severity, message: p.message, spot }] : [];
  });
}
