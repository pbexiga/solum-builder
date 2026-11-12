/**
 * A recording's spectrum in 1/6-octave bands, as the server's `band_levels` works it out
 * (`solum/analysis/signal.py`), for the Audio panel's live line of what's playing. This is
 * the second piece of backend logic the browser repeats (D-096, after D-012's solver): the
 * live line has to keep up with playback. The parity suite holds it to the server's.
 * No DOM.
 */

import { PLOT_BAND } from "./layers.js";

export const BANDS_PER_OCTAVE = 6;
export const [BAND_LOW, BAND_HIGH] = PLOT_BAND; // the Frequency plot's band (D-102)
/** A silent band's level, as the server reads it. */
export const SILENT_DB = -200;

/**
 * The centres of the 1/`perOctave`-octave bands from `BAND_LOW` up to `BAND_HIGH`.
 * @param {number} [perOctave]
 * @returns {number[]}
 */
export function bandCentres(perOctave = BANDS_PER_OCTAVE) {
  const count = Math.floor(perOctave * Math.log2(BAND_HIGH / BAND_LOW)) + 1;
  return Array.from({ length: count }, (_, i) => BAND_LOW * 2 ** (i / perOctave));
}

/**
 * The power spectrum |FFT|² of `x` (length a power of two), bins 0 to n/2.
 * @param {Float64Array} x
 * @returns {Float64Array}
 */
function powerSpectrum(x) {
  const n = x.length;
  const re = Float64Array.from(x);
  const im = new Float64Array(n);
  for (let i = 1, j = 0; i < n; i++) { // bit-reversed order
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) [re[i], re[j]] = [re[j], re[i]];
  }
  for (let size = 2; size <= n; size <<= 1) {
    const step = (-2 * Math.PI) / size;
    for (let start = 0; start < n; start += size) {
      for (let k = 0; k < size / 2; k++) {
        const wr = Math.cos(step * k);
        const wi = Math.sin(step * k);
        const a = start + k;
        const b = a + size / 2;
        const tr = re[b] * wr - im[b] * wi;
        const ti = re[b] * wi + im[b] * wr;
        re[b] = re[a] - tr;
        im[b] = im[a] - ti;
        re[a] += tr;
        im[a] += ti;
      }
    }
  }
  const out = new Float64Array(n / 2 + 1);
  for (let k = 0; k <= n / 2; k++) out[k] = re[k] * re[k] + im[k] * im[k];
  return out;
}

/**
 * Mean power per FFT bin over Hann-windowed, half-overlapping segments (Welch), scaled
 * one-sided so a band's bins sum to its mean square.
 * @param {ArrayLike<number>} samples @param {number} segment a power of two
 */
function welch(samples, segment) {
  let n = segment;
  while (n > samples.length && n > 2) n >>= 1; // a short recording: the largest power of two that fits
  const window = Float64Array.from({ length: n }, (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1)));
  const sumSq = window.reduce((s, w) => s + w * w, 0);
  const power = new Float64Array(n / 2 + 1);
  let count = 0;
  const hop = Math.max(n >> 1, 1);
  for (let s = 0; s + n <= samples.length; s += hop) {
    let mean = 0; // taken off, so a DC offset doesn't leak into the lowest bands
    for (let i = 0; i < n; i++) mean += samples[s + i];
    mean /= n;
    const seg = new Float64Array(n);
    for (let i = 0; i < n; i++) seg[i] = (samples[s + i] - mean) * window[i];
    const p = powerSpectrum(seg);
    for (let k = 0; k < p.length; k++) power[k] += p[k];
    count++;
  }
  const scale = 2 / (n * sumSq * Math.max(count, 1));
  for (let k = 0; k < power.length; k++) power[k] *= scale;
  power[0] /= 2; // DC isn't doubled
  return { power, n };
}

/**
 * Level per band in dB re 1 RMS (a sine of peak A reads 20·log10(A/√2) in its band); a
 * silent band reads `SILENT_DB`. Segments are a power of two (the server's default 8192).
 * A band takes each bin's share inside it (a bin stands for `step` around it), so the
 * lowest bands, narrower than a bin, read true; a band whose centre is past Nyquist is left
 * off, and one reaching past it is read from its part below, as on the server.
 * @param {ArrayLike<number>} samples @param {number} rate
 * @param {{perOctave?: number, segment?: number}} [opts]
 * @returns {{freq: number[], levels: number[]}}
 */
export function bandLevels(samples, rate, { perOctave = BANDS_PER_OCTAVE, segment = 8192 } = {}) {
  const { power, n } = welch(samples, segment);
  const half = 2 ** (1 / (2 * perOctave));
  const nyquist = rate / 2;
  const freq = bandCentres(perOctave).filter((c) => c < nyquist);
  const step = rate / n;
  // each bin stands for the stretch of width `step` around it; a band takes the share of
  // each bin's power inside it, so a band narrower than a bin isn't over-read (as on the server)
  const levels = freq.map((c) => {
    const lo = c / half;
    const hi = c * half;
    let sum = 0;
    for (let k = Math.max(0, Math.floor(lo / step)); k <= Math.min(power.length - 1, Math.ceil(hi / step)); k++) {
      const share = Math.min(hi, (k + 0.5) * step, nyquist) - Math.max(lo, (k - 0.5) * step);
      if (share > 0) sum += (power[k] * share) / step;
    }
    // the top band can reach past Nyquist: read from the part below it, over its width
    sum *= (hi - lo) / (Math.min(hi, nyquist) - lo);
    return 10 * Math.log10(Math.max(sum, 1e-20));
  });
  return { freq, levels };
}
