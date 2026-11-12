/**
 * Fixed-decimal display of volts, dB and percentages. No SI prefixes here: anything that
 * needs them (mA, kΩ, mW) arrives already formatted by the server (`format_quantity`),
 * so SI formatting has one owner (D-045).
 */

const MINUS = "−";

/** @param {number} x @param {number} digits */
function signed(x, digits) {
  const text = Math.abs(x).toFixed(digits);
  return x < 0 && Number(text) !== 0 ? `${MINUS}${text}` : text;
}

/** 4.5 → "4.50 V"; -0.6 → "−0.60 V" @param {number | null | undefined} v */
export const volts = (v, digits = 2) => (v == null ? "—" : `${signed(v, digits)} V`);

/** 6.02 → "+6.0 dB" @param {number | null | undefined} x */
export const db = (x) => (x == null ? "—" : `${x > 0 ? "+" : ""}${signed(x, 1)} dB`);

/** 0.115 → "11.5 %" @param {number | null | undefined} fraction */
export const pct = (fraction, digits = 1) =>
  fraction == null ? "—" : `${signed(fraction * 100, digits)} %`;

/** Pot rotation 0.62 → "62 %" @param {number} rotation */
export const rotationText = (rotation) => `${Math.round(rotation * 100)} %`;

/**
 * A net's DC voltage on the schematic; where a trimmer holds it to a target (D-127) it's
 * drawn in its own colour with a tooltip, "target 4.5 V, held by RT1 at 61 %"; `met`
 * false when the run didn't get there (shown in the warning colour).
 * @param {number} v @param {{ref: string, volts: number, reached: number, rotation: number, met: boolean} | undefined} held
 * @returns {{text: string, title: string | null, met: boolean}}
 */
export function dcText(v, held) {
  if (!held) return { text: volts(v), title: null, met: true };
  const title = held.met
    ? `target ${held.volts} V, held by ${held.ref} at ${rotationText(held.rotation)}`
    : `target ${held.volts} V, not met: ${held.ref} at ${rotationText(held.rotation)} gets ${volts(held.reached)}`;
  return { text: volts(v), title, met: held.met };
}

/**
 * @typedef {{ref: string, net: string, ohms: number, text: string, freq: number, saturated: string | null,
 *   level_db: number, level_text: string, source?: string, amp?: string,
 *   resonance?: {alone: {text: string}, loaded: {text: string}} | null, load?: string, follows?: string[]}} ZEnd
 *   one end of the View → Impedance overlay (`impedance_view`, D-241)
 */

/**
 * What the Impedance overlay writes under the guitar (`zin`) or the amp (`zout`), D-241:
 * the lines drawn ("Zin 33.7 kΩ · +3.1 dB", then a pickup's resonance as the pedal loads
 * it) and the mouse-over: the figures behind them, one per line (D-249).
 * @param {"zin" | "zout"} key @param {ZEnd} end
 * @returns {{lines: string[], title: string}}
 */
export function impedanceText(key, end) {
  const kHz = `${end.freq / 1000} kHz`;
  if (key === "zin") {
    const what = "Input impedance";
    if (end.saturated) return { lines: ["Zin: saturated"], title: `${what}: ${end.saturated}` };
    const res = end.resonance;
    const title = [
      `${what}: ${end.text} at ${kHz}`,
      `Guitar source: ${end.source}`,
      `Level: ${end.level_text}`,
      ...(res ? [`Resonance: ${res.alone.text} into the amp (${end.amp}), ${res.loaded.text} into the pedal`] : []),
    ].join("\n");
    return { lines: [`Zin ${end.text} · ${end.level_text}`, ...(res ? [`Resonance ${res.loaded.text}`] : [])], title };
  }
  const what = "Output impedance";
  if (end.saturated) return { lines: ["Zout: saturated"], title: `${what}: ${end.saturated}` };
  const title = [
    `${what}: ${end.text} at ${kHz}`,
    `Amp input: ${end.load}`,
    `Level: ${end.level_text}`,
    ...(end.follows?.length ? [`Changes with ${end.follows.join(" and ")}`] : []),
  ].join("\n");
  return { lines: [`Zout ${end.text} · ${end.level_text}`], title };
}
