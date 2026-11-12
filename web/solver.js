// In-browser linear solver (D-012): complex modified nodal analysis of the small-signal
// system the server builds (`solum/linear.py`, D-079): passive elements, sources, and each
// semiconductor as an N-port admittance ngspice measured at the operating point. The one
// deliberate copy of backend logic: it must match ngspice's `.ac` within 0.1 dB
// (tests/parity). No DOM.

/** Conductance from every node to ground, as SPICE's gmin: keeps a node that only
 * capacitors reach solvable at the lowest frequencies. Far below any real part. */
export const GMIN = 1e-12;

/**
 * R, C, L: `v` in Ω, F, H between `n[0]` and `n[1]`. V: AC volts `v` from `n[1]` to `n[0]`.
 * Y: a semiconductor's ports `n`, its admittance at frequency f as row-major port × port
 * lists `re[f]`, `im[f]` (current into port i per volt at port j).
 * @typedef {{k: string, name: string, n: number[], v?: number, re?: number[][], im?: number[][]}} Element
 * @typedef {{freq: number[], nodes: string[], elements: Element[], out: number}} System
 */

/**
 * The response at the system's output node (or `node`) at each of its frequencies.
 * @param {System} system
 * @param {Record<string, number>} [values] element name → value, replacing the system's
 * @param {number} [node] node index (default: the output)
 * @returns {{re: Float64Array, im: Float64Array}}
 */
export function solve(system, values = {}, node = system.out) {
  return solveNodes(system, values, [node])[0];
}

/**
 * The responses at several nodes from one solve per frequency (-1: ground, always 0).
 * @param {System} system @param {Record<string, number>} values @param {number[]} nodes
 * @returns {Array<{re: Float64Array, im: Float64Array}>}
 */
export function solveNodes(system, values, nodes) {
  const freqs = system.freq;
  const n = system.nodes.length;
  const extra = system.elements.filter((e) => e.k === "V");
  const size = n + extra.length;
  const out = nodes.map(() => ({ re: new Float64Array(freqs.length), im: new Float64Array(freqs.length) }));
  const ar = new Float64Array(size * size);
  const ai = new Float64Array(size * size);
  const br = new Float64Array(size);
  const bi = new Float64Array(size);
  for (let f = 0; f < freqs.length; f++) {
    ar.fill(0); ai.fill(0); br.fill(0); bi.fill(0);
    stamp(system, f, 2 * Math.PI * freqs[f], values, n, size, ar, ai, br, bi);
    eliminate(size, ar, ai, br, bi);
    nodes.forEach((node, k) => {
      if (node >= 0) {
        out[k].re[f] = br[node];
        out[k].im[f] = bi[node];
      }
    });
  }
  return out;
}

/**
 * Gain in dB from a complex response.
 * @param {{re: Float64Array, im: Float64Array}} h
 * @returns {number[]}
 */
export function toDb(h) {
  return Array.from(h.re, (r, i) => 20 * Math.log10(Math.max(Math.hypot(r, h.im[i]), 1e-15)));
}

function stamp(system, f, w, values, n, size, ar, ai, br, bi) {
  const add = (row, col, r, i) => {
    if (row < 0 || col < 0) return;
    ar[row * size + col] += r;
    ai[row * size + col] += i;
  };
  const admit = (a, b, r, i) => {
    add(a, a, r, i); add(b, b, r, i); add(a, b, -r, -i); add(b, a, -r, -i);
  };
  for (let k = 0; k < n; k++) add(k, k, GMIN, 0);
  let branch = n;
  for (const e of system.elements) {
    const v = e.name in values ? values[e.name] : e.v;
    const [a, b] = e.n;
    switch (e.k) {
      case "R": admit(a, b, 1 / v, 0); break;
      case "C": admit(a, b, 0, w * v); break;
      case "L": admit(a, b, 0, -1 / (w * v)); break;
      case "V":
        add(a, branch, 1, 0); add(b, branch, -1, 0);
        add(branch, a, 1, 0); add(branch, b, -1, 0);
        br[branch] = v;
        branch++;
        break;
      case "Y": {
        const ports = e.n.length, re = e.re[f], im = e.im[f];
        for (let i = 0; i < ports; i++) {
          for (let j = 0; j < ports; j++) add(e.n[i], e.n[j], re[i * ports + j], im[i * ports + j]);
        }
        break;
      }
      default:
        throw new Error(`Unknown element kind ${e.k} (${e.name}).`);
    }
  }
}

// Gaussian elimination with partial pivoting, in place; the solution ends up in (br, bi).
function eliminate(size, ar, ai, br, bi) {
  for (let col = 0; col < size; col++) {
    let pivot = col, best = 0;
    for (let row = col; row < size; row++) {
      const m = Math.hypot(ar[row * size + col], ai[row * size + col]);
      if (m > best) { best = m; pivot = row; }
    }
    if (best === 0) throw new Error("The circuit's equations have no solution (a floating part?).");
    if (pivot !== col) swapRows(size, ar, ai, br, bi, pivot, col);
    const pr = ar[col * size + col], pi = ai[col * size + col];
    const pm = pr * pr + pi * pi;
    for (let row = col + 1; row < size; row++) {
      const xr = ar[row * size + col], xi = ai[row * size + col];
      if (xr === 0 && xi === 0) continue;
      // factor = x / p
      const fr = (xr * pr + xi * pi) / pm, fi = (xi * pr - xr * pi) / pm;
      for (let k = col; k < size; k++) {
        const yr = ar[col * size + k], yi = ai[col * size + k];
        ar[row * size + k] -= fr * yr - fi * yi;
        ai[row * size + k] -= fr * yi + fi * yr;
      }
      br[row] -= fr * br[col] - fi * bi[col];
      bi[row] -= fr * bi[col] + fi * br[col];
    }
  }
  for (let row = size - 1; row >= 0; row--) {
    let sr = br[row], si = bi[row];
    for (let k = row + 1; k < size; k++) {
      const yr = ar[row * size + k], yi = ai[row * size + k];
      sr -= yr * br[k] - yi * bi[k];
      si -= yr * bi[k] + yi * br[k];
    }
    const pr = ar[row * size + row], pi = ai[row * size + row];
    const pm = pr * pr + pi * pi;
    br[row] = (sr * pr + si * pi) / pm;
    bi[row] = (si * pr - sr * pi) / pm;
  }
}

function swapRows(size, ar, ai, br, bi, r1, r2) {
  for (let k = 0; k < size; k++) {
    const i1 = r1 * size + k, i2 = r2 * size + k;
    [ar[i1], ar[i2]] = [ar[i2], ar[i1]];
    [ai[i1], ai[i2]] = [ai[i2], ai[i1]];
  }
  [br[r1], br[r2]] = [br[r2], br[r1]];
  [bi[r1], bi[r2]] = [bi[r2], bi[r1]];
}
