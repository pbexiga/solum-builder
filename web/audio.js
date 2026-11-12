/**
 * The Audio panel (DOM, D-083, D-096): the signal chain as four chips (Guitar ▸ Pedal ▸
 * Amp ▸ Cab), each opening its own drawer, one at a time; then render, A/B, a live
 * the takes' spectrum and a knob sweep. Once anything the take was
 * rendered from changes, the panel says so (D-088).
 * Logic lives in `audio-logic.js` and `bands.js`; the circuit, knobs and the output's
 * frequency curve come from the app root.
 */

import { remember, remembered } from "./storage.js";
import { getJson, postFile, postJson, deleteJson } from "./api.js";
import { ask } from "./editor/form.js";
import {
  ampText, assetOptions, assetRef, audioUrl, changedSources, chipName, clipLevels, clipLimitsText, clipLines, clipText, atFullVolume, expectedLevels, fillEmptyBands, sameTakeText, guitarSummary, jobText,
  cancelJobs, knobsText, nextSlots, parsePositions, renderSources, takeAt, takeNotes, withoutKnob, zipContents, smoothLevels, SPECTRUM_CURVES, spectrumHatch, spectrumRange, spectrumSeries, staleText, stuckText, sweepStaleText, trimText, trimmerRows, TRIM_POSITIONS, waitForJob,
} from "./audio-logic.js";
import { bandLevels, SILENT_DB } from "./bands.js";
import { db } from "./fixed.js";
import { h, infoButton, largeView, paneInfo } from "./panels.js";
import { AUDIBLE, PLOT_BAND } from "./layers.js";
import { noMarks } from "./layers.js";
import { linePlot, liveLinePlot } from "./plots.js";

/**
 * @typedef {import("./audio-logic.js").Slots} Slots @typedef {import("./audio-logic.js").Job} Job
 * @typedef {import("./audio-logic.js").Spectra} Spectra @typedef {import("./audio-logic.js").SpectrumView} SpectrumView
 * @typedef {import("./audio-logic.js").Take} Take @typedef {import("./audio-logic.js").Sources} Sources
 * @typedef {{freq: number[], db: number[]}} Curve
 */

const SLOTS = /** @type {const} */ ([["dry", "Dry"], ["pedal", "Pedal"], ["snapshot", "Snapshot"]]);
const LIVE_MS = 33; // how often the live area redraws (about 30 times a second)
const LIVE_KEEP = 0.7; // how much of the last frame it keeps (smooths flicker; ~0.1 s)
/** Takes are rendered at 48 kHz (`RATE`, `solum/audio/render.py`): played at that rate, the live area reaches the same top band (D-104). */
const PLAY_RATE = 48000;
const MIN_VOLUME = 0.01; // turned down further, the live area holds still
const GAUGE_DB = 20; // the amp gauge is full at this much squash
const SETTINGS_KEY = "solum.audio"; // the panel's settings, as last left in this browser
const LOOKUP_MS = 300; // after a change settles, look for a take already rendered

/**
 * @typedef {{clips?: string, level?: string, captures?: string, irs?: string, input?: string,
 *   loop?: boolean, pumpRipple?: boolean, positions?: string, clipLines?: boolean}} Settings
 * The panel's settings last left in this browser (empty if none or storage is blocked).
 * @returns {Settings}
 */
function rememberedSettings() {
  return remembered(SETTINGS_KEY) ?? {};
}
// what the Audio pane's ⓘ says (D-109, D-111): where to get files (D-272), the chain, then the spectrum view picked
const AUDIO_NOTES = [
  h5("Clips, captures and IRs"),
  // nothing ships with the app (D-272); the user guide walks through getting each
  h("p", { class: "note" }, ["None come with Solum Builder: upload your own. A clip is a DI recording (the guitar straight into an interface), up to 10 s. Amp captures (.nam) and cab IRs can be downloaded from ", h("a", { href: "https://www.tone3000.com/", target: "_blank", rel: "noopener" }, ["tone3000.com"]), ". With a full-rig capture (amp + cab), leave Cab at None. With Amp at None, a take is the pedal's output alone."]),
  h5("The chain"),
  "Guitar ▸ Pedal ▸ Amp ▸ Cab: click one to set it. The clip is played through the circuit (simulated, clipping and all), then the amp capture and the cab IR, into a take you can play.",
  "Render makes the takes. Pedal is the clip through the circuit; Dry is the clip without the pedal, through the same amp and cab; Keep as snapshot holds a take to compare against. Switching between them keeps your place in the clip.",
  "Render sweep renders one knob at several positions, a take for each, played the same way.",
];
const CAPTIONS = {
  pedal: [
    h5("Spectrum: Pedal output"),
    "Before the amp, in dBV, each take averaged over the clip. Pedal is the rendered take; Dry is the clip on its own.",
    "Pedal (no clipping) is the clip through the frequency curve at the knobs as they are now (it follows the knobs): the pedal as it would sound if it never clipped. Where Pedal sits below it, the pedal is clipping; where above it, the clipping added harmonics.",
    "Pedal is read from the 96 kHz simulation, so it reaches 30 kHz. Dry and Pedal (no clipping) reach as high as the clip holds, half its sample rate: a 48 kHz clip stops at 24 kHz (hatched), a 96 kHz one reaches 30 kHz.",
  ],
  heard: [
    h5("Spectrum: What you hear"),
    "After the amp and cab, in dBFS, each take averaged over the clip. The shaded area is what's playing now.",
    "Pedal (no clipping) is the dry take through the frequency curve at the knobs as they are now, as if the pedal never clipped. A gap under it is mostly the pedal clipping (the same gap shows in Pedal output); a driven amp adds a little more.",
    "Every line here has been through the amp and cab, so all of them fall off where the cab does.",
    "0 dBFS, the top, is the most a digital file can hold. A band sits well under it even when the take's peaks reach it, since each band is a slice of the sound averaged over the clip (a render warns if its peaks went past it).",
    "Nothing here goes past 24 kHz (hatched): takes are written and played at 48 kHz, whatever the clip's or the capture's own rate (shown with each in its drawer).",
  ],
};

/** A heading in an ⓘ pop-up. @param {string} text */
function h5(text) {
  return h("h5", {}, [text]);
}

/**
 * @param {HTMLElement} el the panel body
 * @param {{circuit: () => any, view: () => any, pots: () => Array<{ref: string, label: string}>, name: () => string,
 *   pickups: () => Array<{kind: string, name: string}>, editGuitar: () => void,
 *   highlight: (refs: string[], picked?: boolean) => void}} app
 */
export function audioPanel(el, app) {
  /** @type {Slots} */
  let slots = { pedal: null, dry: null, snapshot: null };
  /** @type {string} the slot playing: "dry", "pedal", "snapshot" or "sweep-<i>" */
  let playing = "pedal";
  const saved = rememberedSettings();
  let level = ["soft", "med", "hard"].includes(saved.level ?? "") ? /** @type {string} */ (saved.level) : "med";
  /** @type {Record<string, HTMLSelectElement>} */
  const selects = {};
  /** @type {Map<string, Spectra>} spectra by take key */
  const spectra = new Map();
  /** @type {Curve | null} the output's frequency curve, as the Frequency panel has it */
  let curve = null;
  /** @type {SpectrumView} */
  let view = "heard"; // what you hear first (the user, D-104)
  /** @type {ReturnType<typeof clipLevels>} where the pedal clips: the spectrum's clip lines */
  let clipped = null;
  const shown = new Set(["dry", "pedal", "live"]); // Pedal (no clipping) is ticked by hand (the user)
  /** a Render or Render sweep is under way (a lookup then leaves the takes alone) */
  let rendering = false;
  /** the take last picked by hand ("" before any), and how many picks so far: a Render
   * finishing plays its take only if nothing else was picked meanwhile (the user, D-198) */
  const picked = { slot: "", count: 0 };
  let sweeping = false;
  /** the jobs of the Render and the Render sweep under way, and whether Cancel was pressed
   * before the server answered with them (D-240) */
  const under = { render: /** @type {string[]} */ ([]), sweep: /** @type {string[]} */ ([]), stopRender: false, stopSweep: false };
  /** what was last looked up, so the same settings aren't asked about twice */
  const lookedUp = { pedal: "", sweep: "" };
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let lookUpTimer;
  /** the asset lists have been loaded once (the settings are restored then) */
  let assetsLoaded = false;
  /** @type {Map<string, Promise<string>>} each take's audio in memory, by key (see `preload`) */
  const audios = new Map();
  /** the take in the player, by key ("" before the first) */
  let playingKey = "";
  /** circuits opened so far: a take still loading when another opens doesn't start */
  let opens = 0;
  let pedalOpens = -1; // `opens` when the pedal take was made: a lookup only fills a circuit just opened
  /** @type {Array<Take | null>} the latest sweep's takes, by position (null: not done) */
  let sweep = [];
  /** @type {{ref: string, from: Sources} | null} the pot the sweep turned, and what it was rendered from */
  let swept = null;
  /** the trimmer the next sweep turns, from the Trimmers fold ("": the pot picked, D-198) */
  let trimmed = "";
  /** @type {{ref: string, sig: string, rotations: number[], found: Array<Array<{ref: string, state: string}>>} | null}
   * the trimmer sweep's saturation check, per position, and what it was checked on */
  let stuck = null;
  /** @type {{freq: number[], levels: number[]} | null} what's playing, by band (placed on the plot by frequency) */
  let live = null;

  const status = h("p", { class: "audio-status", "aria-live": "polite" });
  const stale = h("p", { class: "audio-stale", "aria-live": "polite", hidden: "" });
  const sweepStale = h("p", { class: "audio-sweep-stale", "data-sweep-stale": "", "aria-live": "polite", hidden: "" });

  // ---- the chain: a chip per stage, each with its drawer
  /** @param {string} id @param {string} title */
  const chip = (id, title) => {
    const value = h("span", { class: "v" });
    const sub = h("span", { class: "s" });
    const button = h("button", { type: "button", class: "chip", "data-chip": id, "aria-expanded": "false", "aria-controls": `audio-drawer-${id}` }, [h("span", { class: "t" }, [title]), value, sub]);
    const drawer = h("div", { class: "drawer", id: `audio-drawer-${id}`, "data-drawer": id, hidden: "" });
    button.addEventListener("click", () => openDrawer(button.getAttribute("aria-expanded") === "true" ? null : id));
    return { button, drawer, value, sub };
  };
  const chips = { guitar: chip("guitar", "Guitar"), pedal: chip("pedal", "Pedal"), amp: chip("amp", "Amp"), cab: chip("cab", "Cab") };
  const gauge = h("i");
  const gaugeText = h("span", { class: "n" });
  chips.amp.sub.replaceChildren(h("span", { class: "gauge", title: "How hard the latest take drives the amp: dB of squash" }, [h("span", { class: "bar" }, [gauge]), gaugeText]));

  /** Open one drawer (null: none). @param {string | null} id */
  function openDrawer(id) {
    for (const [key, c] of Object.entries(chips)) {
      c.button.setAttribute("aria-expanded", String(key === id));
      c.drawer.hidden = key !== id;
    }
  }

  /** An asset row: a select with Upload and Delete. @param {string} kind @param {string} label @param {string} accept @param {boolean} optional */
  const assetRow = (kind, label, accept, optional) => {
    const select = /** @type {HTMLSelectElement} */ (h("select", { "aria-label": label, "data-kind": kind }));
    selects[kind] = select;
    select.dataset.optional = String(optional);
    select.dataset.label = label;
    const file = /** @type {HTMLInputElement} */ (h("input", { type: "file", accept, hidden: "" }));
    const upload = h("button", { type: "button" }, ["Upload…"]);
    const remove = h("button", { type: "button", title: "Delete this upload", hidden: "" }, ["Delete"]);
    upload.addEventListener("click", () => file.click());
    file.addEventListener("change", () => file.files?.[0] && uploadFile(kind, file.files[0]).finally(() => (file.value = "")));
    select.addEventListener("change", () => {
      remove.hidden = !select.value.startsWith("user:");
      if (kind === "captures") inputTrim.disabled = !select.value; // no amp, no Input knob
      rememberSettings();
      showChips();
      showStale();
    });
    remove.addEventListener("click", () => removeAsset(kind, select, remove));
    return h("div", { class: "audio-row" }, [h("span", { class: "name" }, [label]), select, upload, remove, file]);
  };

  // nothing ships in library/audio (D-272): an empty list says so, until a file is uploaded
  /** @type {Record<string, HTMLElement>} */
  const emptyNotes = {};
  /** @param {string} kind @param {string} text */
  const emptyNote = (kind, text) => (emptyNotes[kind] = h("p", { class: "note", "data-empty": kind, hidden: "" }, [text]));

  // Guitar: the clip and how hard it's played
  const levels = ["soft", "med", "hard"].map((l) => {
    const b = h("button", { type: "button", role: "radio", "data-audio-level": l, "aria-checked": String(l === level) }, [l === "med" ? "Medium" : l[0].toUpperCase() + l.slice(1)]);
    b.addEventListener("click", () => {
      level = l;
      for (const o of levels) o.setAttribute("aria-checked", String(o === b));
      rememberSettings();
      showChips();
      showStale();
    });
    return b;
  });
  chips.guitar.drawer.append(
    assetRow("clips", "Clip", ".wav,audio/wav", false),
    emptyNote("clips", "No DI clips loaded."),
    h("div", { class: "audio-row" }, [h("span", { class: "name" }, ["Pick"]), h("span", { class: "segmented", role: "radiogroup", "aria-label": "Pick level" }, levels)]),
    h("p", { class: "note" }, ["For a fuzz, set the guitar input (in Pedal) to the pickup the clip was recorded with: the render takes that pickup out of the clip first, so you hear how the fuzz loads it, not the pickup twice."]),
  );

  // Pedal: the circuit, and the guitar input that loads it
  const pedalSummary = h("p", { class: "note" });
  const editGuitar = h("button", { type: "button" }, ["Edit the guitar input…"]);
  editGuitar.addEventListener("click", () => app.editGuitar());
  // a charge pump's switching: off renders about ten times faster, on lets you hear its whine
  const pumpRipple = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", "data-pump-ripple": "" }));
  pumpRipple.checked = !!saved.pumpRipple;
  pumpRipple.addEventListener("change", () => { showStale(); rememberSettings(); });
  const pumpRow = h("label", { class: "switch", hidden: "", title: "Off, the charge pump gives its average voltage: renders run about ten times faster. On, it switches as the chip does, so you hear any whine its ripple leaks into the signal (slow: the simulator follows every switching cycle)." },
    [pumpRipple, " Charge pump switching (hear its whine; about 10× slower)"]);
  chips.pedal.drawer.append(pedalSummary, pumpRow, h("div", { class: "panel-tools" }, [editGuitar]));

  // Amp: the capture, how hard the pedal hits it, and how driven it is
  const inputTrim = /** @type {HTMLInputElement} */ (h("input", { type: "range", value: "0", min: "-40", max: "20", step: "1", "aria-label": "Amp input (dB)", title: "A trim between the pedal and the amp, like the NAM plugin's Input knob: −40 to +20 dB. It changes how hard the amp is driven. Double-click for 0 dB." }));
  const inputMeta = h("span", { class: "meta" }, [trimText(0)]);
  const showInput = () => (inputMeta.textContent = trimText(Number(inputTrim.value)));
  inputTrim.value = saved.input ?? "0";
  showInput();
  inputTrim.addEventListener("input", () => { showInput(); showStale(); rememberSettings(); });
  inputTrim.addEventListener("dblclick", () => { inputTrim.value = "0"; showInput(); showStale(); rememberSettings(); });
  const meter = h("p", { class: "audio-meter", title: "How hard the take drives the amp capture: how many dB it squashes the signal (0 = clean), and the loudest moment going in. 0 dBFS is the capture's full scale, the loudest input it was made with." });
  chips.amp.drawer.append(
    assetRow("captures", "Amp", ".nam", true),
    emptyNote("captures", "No amp captures loaded."),
    h("div", { class: "knob audio-input" }, [h("span", { class: "name" }, ["Input (pedal into amp)"]), inputMeta, inputTrim]),
    meter,
  );

  // Cab
  chips.cab.drawer.append(
    assetRow("irs", "Cab", ".wav,audio/wav", true),
    emptyNote("irs", "No cab IRs loaded."),
  );

  // ---- listen
  // Render and Cancel render both in the button, the one not showing kept invisible: it
  // doesn't change width when it flips, so nothing moves while a render runs (D-134, D-240)
  const renderButton = h("button", { type: "button", class: "primary flip" }, [h("span", { "data-label": "go" }, ["Render"]), h("span", { "data-label": "stop" }, ["Cancel render"])]);
  const bar = /** @type {HTMLProgressElement} */ (h("progress", { max: "1", value: "0", hidden: "" }));
  const player = /** @type {HTMLAudioElement} */ (h("audio", { controls: "", preload: "auto" }));
  const download = /** @type {HTMLAnchorElement} */ (h("a", { class: "button", hidden: "" }, ["Download WAV"]));
  const downloadAll = h("button", { type: "button", hidden: "", title: "Every take, with the circuit each was rendered from and a note of its knobs, clip, amp and cab" }, ["Download all (.zip)"]);
  const keep = h("button", { type: "button", disabled: "" }, ["Keep as snapshot"]);
  const loop = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox" }));
  loop.checked = player.loop = !!saved.loop;
  loop.addEventListener("change", () => { player.loop = loop.checked; rememberSettings(); });
  /** A button that plays a slot. @param {string} slot @param {string} label */
  const slotButton = (slot, label) => {
    const b = h("button", { type: "button", role: "radio", "data-slot": slot, disabled: "" }, [label]);
    b.addEventListener("click", () => {
      picked.slot = slot;
      picked.count++;
      play(slot, true);
    });
    return b;
  };
  const abButtons = SLOTS.map(([slot, label]) => slotButton(slot, label));
  renderButton.addEventListener("click", () => {
    if (rendering) return void stopRender();
    startGraph();
    renderPedal();
  });
  downloadAll.addEventListener("click", () => downloadZip());
  keep.addEventListener("click", () => {
    const take = takeAt(slots, sweep, playing);
    if (!take) return;
    slots = { ...slots, snapshot: { ...take, label: `snapshot: ${take.label.replace(/^snapshot: /, "")}` } };
    shown.add("snapshot");
    for (const t of toggles) if (t.id === "snapshot") /** @type {HTMLInputElement} */ (t.el.querySelector("input")).checked = true;
    showSlots();
    drawSpectrum();
    // the Snapshot button lights and fades: the only sign a snapshot was replaced
    const button = abButtons.find((b) => b.getAttribute("data-slot") === "snapshot");
    if (button) {
      button.classList.remove("kept");
      void button.offsetWidth; // restarts the animation on a second Keep
      button.classList.add("kept");
    }
  });

  // ---- spectrum
  const plot = h("div", { class: "audio-spectrum" });
  /** says where the pedal clips, when it does (see `setClipping`) */
  const clipNote = h("p", { class: "note", "data-clip-note": "" });
  clipNote.hidden = true;
  /** @type {{stats: Parameters<typeof clipText>[0], run: Parameters<typeof clipText>[1]} | null} */
  let clipRun = null;
  // the clip lines on the Pedal output view: off unless turned on (remembered)
  const clipBox = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", "data-clip-lines": "" }));
  clipBox.checked = Boolean(saved.clipLines);
  clipBox.addEventListener("change", () => { rememberSettings(); showClipping(); });
  /** the clip lines' two levels, right under the plot while they're drawn */
  const clipLimits = h("p", { class: "note clip-limits", "data-clip-limits": "" });
  clipLimits.hidden = true;
  const clipToggle = h("label", { "data-curve-label": "clip", title: "Dashed lines at the level the output reached and where clipping starts at the guitar" }, [clipBox, h("i", { class: "swatch clip" }), "Clip levels"]);
  const viewButtons = /** @type {const} */ ([["heard", "What you hear"], ["pedal", "Pedal output"]]).map(([id, label]) => {
    const b = h("button", { type: "button", role: "radio", "data-spectrum-view": id, "aria-checked": String(id === view) }, [label]);
    b.addEventListener("click", () => { view = id; showClipping(); });
    return b;
  });
  const toggles = SPECTRUM_CURVES.map(([id, label]) => {
    const box = /** @type {HTMLInputElement} */ (h("input", { type: "checkbox", "data-curve": id }));
    box.checked = shown.has(id);
    box.addEventListener("change", () => { if (box.checked) shown.add(id); else shown.delete(id); drawSpectrum(); });
    return { id, el: h("label", { "data-curve-label": id }, [box, h("i", { class: `swatch ${id}` }), label]) };
  });
  const spectrumTools = h("div", { class: "panel-tools" }, [h("span", { class: "segmented", role: "radiogroup", "aria-label": "Spectrum view" }, viewButtons)]);
  const spectrum = /** @type {HTMLDetailsElement} */ (h("details", { class: "audio-fold", id: "audio-spectrum", open: "" }, [
    h("summary", {}, ["Spectrum"]),
    h("div", { class: "spectrum-body" }, [
      spectrumTools,
      h("div", { class: "audio-legend" }, [...toggles.map((t) => t.el), clipToggle]),
      plot,
      clipLimits,
      clipNote,
    ]),
  ]));
  spectrum.addEventListener("toggle", () => drawSpectrum());

  // ---- sweep: a button per position, played like the slots above
  const sweepPot = /** @type {HTMLSelectElement} */ (h("select", { "aria-label": "Pot to sweep" }));
  const sweepAt = /** @type {HTMLInputElement} */ (h("input", { type: "text", value: saved.positions ?? "5, 25, 50, 75, 100", size: "14", "aria-label": "Positions (%)" }));
  const sweepButton = h("button", { type: "button", class: "flip" }, [h("span", { "data-label": "go" }, ["Render sweep"]), h("span", { "data-label": "stop" }, ["Cancel sweep"])]);
  const sweepName = h("span", { class: "name" });
  const sweepButtons = h("span", { class: "segmented", role: "radiogroup", "aria-label": "Sweep takes" });
  sweepButton.addEventListener("click", () => {
    if (sweeping) return void stopSweep();
    startGraph();
    renderSweep();
  });
  sweepAt.addEventListener("input", () => { rememberSettings(); if (!swept) showSweep(); lookUpSoon(); });
  sweepPot.addEventListener("change", () => { sweepButton.toggleAttribute("disabled", !sweepPot.value); trimmed = ""; if (!swept) showSweep(); lookUpSoon(); });

  // ---- trimmers (D-198): closed, advanced; a few positions each, checked for a saturated
  // stage first. A trimmer its bias target sets is listed greyed, so the option is seen.
  const trimList = h("ul", { class: "trim-list" });
  const trimStuck = h("p", { class: "audio-sweep-stale", "data-trim-stuck": "", "aria-live": "polite", hidden: "" });
  const trimPositions = TRIM_POSITIONS.map((r) => `${Math.round(r * 100)}`).join(" · ");
  // what it does is behind its ⓘ (9c's info pass, the user 2026-11-04)
  const trimInfo = infoButton("Trimmers", () => [
    `Hear a trimmer at ${trimPositions} %, its takes in the sweep row above. Each position is checked first: one that saturates a stage is marked, since what you'd hear there is a broken bias, not a sound.`,
  ]);
  const trimFold = /** @type {HTMLDetailsElement} */ (h("details", { class: "audio-fold", id: "audio-trimmers", hidden: "" }, [
    h("summary", {}, ["Trimmers (advanced)", trimInfo.button]),
    trimList,
    trimStuck,
  ]));
  trimFold.addEventListener("toggle", () => { if (!trimFold.open) app.highlight([], true); });

  // Dry and Pedal on the left; the snapshot and Keep apart, on the right
  const abSets = [h("span", { class: "segmented" }, abButtons.slice(0, 2)), h("span", { class: "segmented ab-apart" }, abButtons.slice(2))];
  const abRow = h("div", { class: "panel-tools audio-ab", role: "radiogroup", "aria-label": "Listen to" }, [
    ...abSets,
    h("span", { class: "ab-apart" }, [keep]),
  ]);
  const renderPlace = h("span", { class: "push" }, [renderButton]);
  // the render's progress takes the downloads' place while it runs, so nothing moves
  const downloads = h("span", { class: "audio-downloads" }, [download, downloadAll, bar]);
  // on the shrunk bar, a rule keeps Render apart from what plays (the user, D-111)
  const barRule = h("span", { class: "bar-rule", "aria-hidden": "true" });
  // on the shrunk bar only (the player itself is too wide for it): play or pause the take
  // both words in the button, the one not showing kept invisible: it's always as wide as
  // "Pause", so the centred bar doesn't move when it flips (D-116)
  const playButton = /** @type {HTMLButtonElement} */ (h("button", { type: "button", id: "audio-bar-play", title: "Play or pause the take", disabled: "" }, [
    h("span", { "data-label": "play" }, ["Play"]),
    h("span", { "data-label": "pause" }, ["Pause"]),
  ]));
  // greyed out until a take is loaded in the player
  for (const event of ["loadstart", "loadedmetadata", "emptied"]) {
    player.addEventListener(event, () => (playButton.disabled = !player.currentSrc));
  }
  playButton.addEventListener("click", () => {
    if (!player.currentSrc) return;
    if (player.paused) void player.play().catch(() => {});
    else player.pause();
  });
  // the whole player (chain, render, player, A/B, sweep): above the spectrum in the panel,
  // its right-hand column in the large view (D-110)
  const playerBlock = h("div", { class: "audio-player large-side", id: "audio-player" }, [
    h("div", { class: "audio-chain" }, Object.values(chips).map((c) => c.button)),
    ...Object.values(chips).map((c) => c.drawer),
    h("div", { class: "audio-listen" }, [
      h("div", { class: "panel-tools audio-render" }, [h("label", { class: "switch" }, [loop, " Loop"]), downloads, renderPlace]),
      player,
      abRow,
      // what the next sweep turns, then the takes of the last one (named for its knob)
      h("div", { class: "audio-row audio-sweep-set" }, [sweepPot, sweepAt, sweepButton]),
      h("div", { class: "panel-tools audio-sweep" }, [sweepName, sweepButtons]),
      sweepStale,
      trimFold,
      stale,
      status,
    ]),
  ]);
  el.replaceChildren(playerBlock, spectrum);

  // Expand: the whole pane over the canvas, as every pane (D-102, D-107): the spectrum on
  // the left, the player on the right (D-110). Shrunk to its bar, the bar keeps Render,
  // play and Dry / Pedal / Snapshot (moved there, the same buttons), so a change can be
  // heard while another pane is large.
  const panel = /** @type {HTMLDetailsElement} */ (el.closest("details"));
  let spectrumWasOpen = spectrum.open;
  const large = largeView(panel, {
    id: "audio-expand",
    name: "audio",
    what: "A large view of the spectrum and the player, over the canvas",
    tools: spectrumTools,
    pinBar: true, // its bar holds controls: always the bottom one, so they stay put (D-111)
    onChange: (on) => {
      // the large view shows the spectrum; back in the panel, the fold is as it was left
      if (on) spectrumWasOpen = spectrum.open;
      spectrum.open = on || spectrumWasOpen;
      drawSpectrum(); // a new height
    },
    onShow: () => drawSpectrum(), // laid out full width again
    onShrink: (shrunk) => {
      if (shrunk) {
        large.bar.prepend(bar, renderButton);
        large.bar.append(...abSets);
      }
      else {
        downloads.append(bar);
        renderPlace.append(renderButton);
        abRow.prepend(...abSets);
      }
    },
  });
  // built on each opening: a node can sit in one place only
  large.bar.append(barRule, playButton); // the bar's own; Render and the A/B buttons join them while shrunk
  paneInfo(panel, "Audio", () => [...AUDIO_NOTES, ...(spectrum.open ? CAPTIONS[view] : [h5("Spectrum"), "Open the Spectrum to see what each take holds, band by band."])].map((n) => (typeof n === "string" ? n : n.cloneNode(true))));

  // ---- playback through Web Audio: an analyser for the live area
  /** @type {{ctx: AudioContext, analyser: AnalyserNode, buffer: Float32Array} | null} */
  let graph = null;
  let looping = false;

  /** Start Web Audio, once, on a click (browsers start audio only after one). */
  function startGraph() {
    if (graph) return void graph.ctx.resume().catch(() => {});
    try {
      let ctx;
      try {
        ctx = new AudioContext({ sampleRate: PLAY_RATE });
      } catch {
        ctx = new AudioContext(); // a browser that won't run at that rate: its own (at 44.1 kHz the live area stops a band lower)
      }
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 8192;
      analyser.connect(ctx.destination);
      ctx.createMediaElementSource(player).connect(analyser);
      graph = { ctx, analyser, buffer: new Float32Array(analyser.fftSize) };
    } catch {
      graph = null; // no Web Audio: the player plays on its own, with no live area
    }
  }

  player.addEventListener("play", () => {
    playButton.toggleAttribute("data-playing", true);
    startGraph();
    live = null;
    if (!looping) liveLoop();
  });
  player.addEventListener("pause", () => {
    playButton.toggleAttribute("data-playing", false);
    live = null;
    drawSpectrum();
  });
  for (const b of [...abButtons, loop]) b.addEventListener("pointerdown", startGraph);

  let lastFrame = 0;
  function liveLoop() {
    looping = !player.paused;
    if (!looping) return;
    requestAnimationFrame(liveLoop);
    const now = performance.now();
    if (!graph || now - lastFrame < LIVE_MS || !spectrum.open || view !== "heard" || !shown.has("live")) return;
    lastFrame = now;
    if (player.muted || player.volume < MIN_VOLUME) return; // nothing to read through
    graph.analyser.getFloatTimeDomainData(graph.buffer);
    const bands = bandLevels(graph.buffer, graph.ctx.sampleRate);
    const levels = fillEmptyBands(bands.levels, SILENT_DB);
    live = { freq: bands.freq, levels: smoothLevels(live?.levels ?? null, atFullVolume(levels, player.volume), LIVE_KEEP) };
    drawSpectrum(true);
  }

  /** @param {string} text @param {boolean} [error] */
  function say(text, error = false) {
    status.textContent = text;
    status.classList.toggle("failed", error);
  }

  async function loadAssets() {
    const all = await getJson("api/audio");
    for (const [kind, select] of Object.entries(selects)) {
      const optional = select.dataset.optional === "true";
      // the first time, what was last chosen in this browser (`saved` is read once, at the
      // start: each select's change below saves the settings)
      const was = assetsLoaded ? select.value : saved[/** @type {"clips" | "captures" | "irs"} */ (kind)] ?? "";
      const options = assetOptions(all[kind]).map((o) => h("option", { value: o.value }, [o.label]));
      const none = optional ? [h("option", { value: "" }, ["None"])] : [];
      const empty = !optional && !options.length ? [h("option", { value: "" }, [`Upload a ${select.dataset.label?.toLowerCase()} (WAV, up to 10 s)`])] : [];
      select.replaceChildren(...none, ...empty, ...options);
      emptyNotes[kind].hidden = options.length > 0; // gone once one is uploaded, even with None picked
      if ([...select.options].some((o) => o.value === was)) select.value = was;
      select.dispatchEvent(new Event("change"));
    }
    assetsLoaded = true;
  }

  /** Keep the panel's settings for next time (this browser only). */
  function rememberSettings() {
    if (!assetsLoaded) return; // still restoring them
    /** @type {Settings} */
    const now = { clips: selects.clips.value, level, captures: selects.captures.value, irs: selects.irs.value, input: inputTrim.value, pumpRipple: pumpRipple.checked, loop: loop.checked, positions: sweepAt.value, clipLines: clipBox.checked };
    remember(SETTINGS_KEY, now);
  }

  /** @param {string} kind @param {File} file */
  async function uploadFile(kind, file) {
    try {
      const added = await postFile(`api/audio/${kind}?name=${encodeURIComponent(file.name)}`, file);
      await loadAssets();
      selects[kind].value = `user:${added.id}`;
      selects[kind].dispatchEvent(new Event("change"));
      say(`Added ${added.name}.`);
    } catch (err) {
      say(/** @type {Error} */ (err).message, true);
    }
  }

  /** @param {string} kind @param {HTMLSelectElement} select @param {HTMLElement} button */
  async function removeAsset(kind, select, button) {
    const ref = assetRef(select.value);
    if (!ref || ref.layer !== "user") return;
    const name = select.selectedOptions[0]?.textContent ?? ref.id;
    const what = { clips: "clip", captures: "amp capture", irs: "cab IR" }[kind] ?? "file";
    const choice = await ask({
      title: `Delete ${name}?`,
      text: `This ${what} is removed from your uploads; to use it again, upload it again.`,
      cancel: "cancel",
      buttons: [{ label: "Cancel", value: "cancel" }, { label: "Delete", value: "delete", kind: "primary" }],
    });
    if (choice !== "delete") return;
    try {
      await deleteJson(`api/audio/${kind}/${encodeURIComponent(ref.id)}`);
      button.hidden = true;
      await loadAssets();
    } catch (err) {
      say(/** @type {Error} */ (err).message, true);
    }
  }

  function request() {
    const clip = assetRef(selects.clips.value);
    if (!clip) return null;
    const pump_ripple = hasPump() && pumpRipple.checked;
    return { clip, capture: assetRef(selects.captures.value), ir: assetRef(selects.irs.value), level, input_db: Number(inputTrim.value) || 0, pump_ripple };
  }

  /** @param {Job} job */
  function progress(job) {
    bar.hidden = job.state === "done" || job.state === "failed" || job.state === "cancelled";
    downloads.classList.toggle("busy", !bar.hidden);
    bar.value = job.progress;
    bar.title = job.state === "queued" ? jobText(job) : ""; // the bar is the progress: no text under the player to move things
    if (job.state === "failed") say(jobText(job), true);
  }

  /** @param {any} start the job the server answered with @returns {Promise<Job>} */
  const finish = (start) => waitForJob(start, getJson, progress);

  /**
   * While a render runs, its button stops it (D-240).
   * @param {HTMLElement} button @param {string} title
   */
  function busyButton(button, title) {
    button.title = title;
    button.classList.add("cancel");
    button.removeAttribute("disabled");
  }

  /** The button back to starting a render. @param {HTMLElement} button */
  function idleButton(button) {
    button.title = "";
    button.classList.remove("cancel");
  }

  /** Stop the Render under way: its pedal and dry jobs (once the server named them). */
  async function stopRender() {
    under.stopRender = true;
    renderButton.setAttribute("disabled", ""); // until the jobs say they've stopped
    await cancelJobs(under.render, postJson);
  }

  /** Stop the Render sweep under way: every take not finished. */
  async function stopSweep() {
    under.stopSweep = true;
    sweepButton.setAttribute("disabled", "");
    await cancelJobs(under.sweep, postJson);
  }

  /**
   * Render the pedal take and its dry twin. `cachedOnly`: look them up only, loading them
   * (not playing) if they're already rendered for the settings as they are, else nothing.
   * @param {boolean} [cachedOnly]
   */
  async function renderPedal(cachedOnly = false) {
    const req = request();
    if (!req) {
      if (cachedOnly) return;
      openDrawer("guitar");
      return say("Pick or upload a clip first.", true);
    }
    const circuit = structuredClone(app.circuit());
    const from = renderSources(circuit, app.view(), req);
    if (cachedOnly) {
      // a lookup never swaps a take already here for this circuit: what plays changes only
      // with Render or a take's button (the user, 2026-10-28)
      if ((slots.pedal && pedalOpens === opens) || !player.paused) return;
      const sig = JSON.stringify(from);
      if (rendering || sig === lookedUp.pedal || (slots.pedal?.from && !changedSources(slots.pedal.from, from).length)) return;
      lookedUp.pedal = sig;
    }
    const notes = (/** @type {boolean} */ pedal) => notesFor(pedal ? circuit : null);
    if (!cachedOnly) {
      rendering = true;
      under.stopRender = false;
      busyButton(renderButton, "Stop this render");
    }
    const picksThen = picked.count;
    try {
      const [pedalStart, dryStart] = await Promise.all([
        postJson("api/render", { ...req, circuit, cached_only: cachedOnly }),
        postJson("api/render", { ...req, circuit: null, cached_only: cachedOnly }),
      ]);
      if (cachedOnly && (pedalStart?.state !== "done" || rendering || JSON.stringify(from) !== JSON.stringify(currentSources()))) return;
      if (!cachedOnly) {
        under.render = [pedalStart?.id, dryStart?.id].filter(Boolean);
        if (under.stopRender) await stopRender();
      }
      const pedal = await finish(pedalStart);
      if (pedal.state === "cancelled") say("Render cancelled.");
      if (pedal.state !== "done") return;
      const dry = dryStart ? await waitForJob(dryStart, getJson, () => {}) : { state: "missing" };
      const label = `${app.name()} · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
      const amp = !!req.capture;
      slots = nextSlots(slots,
        { ...takeOf(pedal, label, amp, req.input_db, "Pedal"), from, notes: notes(true), circuit },
        dry.state === "done" ? { ...takeOf(/** @type {Job} */ (dry), "dry", amp, req.input_db, "Dry"), notes: notes(false) } : null);
      pedalOpens = opens;
      // another take picked while it rendered (a sweep take, the snapshot, Dry) keeps playing
      if (picked.count === picksThen || picked.slot === "pedal") play("pedal");
      else {
        showSlots();
        say("The new Pedal take is ready: press Pedal to hear it.");
      }
      showStale();
      await loadSpectra();
    } catch (err) {
      bar.hidden = true;
      downloads.classList.remove("busy");
      if (!cachedOnly) say(/** @type {Error} */ (err).message, true); // a lookup fails quietly
    } finally {
      if (!cachedOnly) {
        rendering = false;
        under.render = [];
        idleButton(renderButton);
        renderButton.removeAttribute("disabled");
      }
    }
  }

  /**
   * A finished job as a take to play. @param {Job} job @param {string} label
   * @param {boolean} amp @param {number} inputDb @param {string} [name] what the status calls it
   * @returns {Take}
   */
  function takeOf(job, label, amp, inputDb, name = label) {
    return { key: job.key, label, amp_in: job.amp_in, amp_compression: job.amp_compression, amp, input_db: inputDb, text: jobText({ ...job, label: name }, amp) };
  }

  /** What a take is being rendered from, in words. @param {any} circuit null: the dry take */
  function notesFor(circuit) {
    const option = (/** @type {string} */ kind) => (selects[kind].value ? chipName(selects[kind].selectedOptions[0]?.textContent ?? "") : "None");
    return takeNotes({
      name: app.name(), knobs: circuit ? knobsText(app.view()?.controls ?? [], circuit) : null,
      clip: option("clips"), level, amp: option("captures"), input_db: Number(inputTrim.value) || 0, cab: option("irs"),
      when: new Date().toLocaleString(),
    });
  }

  /**
   * Render a take per position of the pot picked. `cachedOnly`: look them up only, showing
   * those already rendered (the others greyed) if any are, else nothing.
   * @param {boolean} [cachedOnly]
   */
  async function renderSweep(cachedOnly = false) {
    const req = request();
    const positions = sweepTarget();
    const ref = trimmed || sweepPot.value;
    // a lookup leaves the sweep alone while one of its takes is playing
    if (cachedOnly && (!req || "error" in positions || !ref || sweeping || playing.startsWith("sweep-"))) return;
    if (!req) return say("Pick or upload a clip first.", true);
    if ("error" in positions) return say(positions.error, true);
    const knob = knobName(ref);
    const circuit = structuredClone(app.circuit());
    const from = withoutKnob(renderSources(circuit, app.view(), req), ref);
    if (cachedOnly) {
      const sig = JSON.stringify([from, ref, positions.rotations]);
      if (sig === lookedUp.sweep) return;
      lookedUp.sweep = sig;
    } else {
      lookedUp.sweep = JSON.stringify([from, ref, positions.rotations]);
      sweeping = true;
      under.stopSweep = false;
      busyButton(sweepButton, "Stop every take of this sweep");
      showTrimmers();
    }
    try {
      // a trimmer's positions are checked for a saturated stage before rendering
      if (trimmed && !cachedOnly) await checkStuck(circuit, from, ref, positions.rotations);
      /** @type {Array<Job | null>} */
      const answered = await postJson("api/render/sweep", { ...req, circuit, ref, rotations: positions.rotations, cached_only: cachedOnly });
      if (cachedOnly && (!answered.some((j) => j?.state === "done") || sweeping || JSON.stringify(from) !== JSON.stringify(withoutKnob(currentSources(), ref)))) return;
      if (trimmed && cachedOnly) await checkStuck(circuit, from, ref, positions.rotations);
      if (!cachedOnly) {
        under.sweep = answered.flatMap((j) => (j && j.state !== "done" ? [j.id] : []));
        if (under.stopSweep) await stopSweep();
      }
      // a position not rendered yet (looking up only) stays greyed
      /** @type {Job[]} */
      // each labelled with its position: a position the pedal take already renders (or is
      // rendering) comes back as that job, labelled for the pedal
      const at = (/** @type {number} */ i) => `${ref} at ${Math.round(positions.rotations[i] * 100)} %`;
      const started = answered.map((j, i) => (j && (!cachedOnly || j.state === "done") ? { ...j, label: at(i) } : /** @type {Job} */ ({ state: "missing", progress: 0, label: at(i) })));
      const amp = !!req.capture;
      swept = { ref, from };
      sweep = started.map(() => null);
      showSweep(started);
      if (playing.startsWith("sweep-")) play("pedal");
      drawSpectrum();
      let failed = "";
      await Promise.all(started.map(async (job, i) => {
        if (job.state === "missing") return showSweep(started, i, job);
        const done = await waitForJob(job, getJson, (j) => showSweep(started, i, j));
        if (done.state !== "done") {
          if (done.state === "cancelled") failed ||= "Sweep cancelled: the takes already finished still play.";
          else failed = jobText(done, amp);
          return showSweep(started, i, done);
        }
        const pct = Math.round(positions.rotations[i] * 100);
        const turned = { ...circuit, parts: circuit.parts.map((/** @type {any} */ p) => (p.ref === ref ? { ...p, rotation: positions.rotations[i] } : p)) };
        sweep[i] = { ...takeOf(done, `${knob} ${pct} %`, amp, req.input_db), notes: notesFor(turned), circuit: turned };
        preload(done.key);
        try {
          spectra.set(done.key, await getJson(`api/render/spectrum/${done.key}`));
        } catch {
          // no spectrum for this take: it still plays
        }
        showSweep(started, i, done);
        showSlots();
        drawSpectrum();
      }));
      if (failed) say(failed, !under.stopSweep);
      forgetAudio();
      showStale();
    } catch (err) {
      if (!cachedOnly) say(/** @type {Error} */ (err).message, true);
    } finally {
      if (!cachedOnly) {
        sweeping = false;
        under.sweep = [];
        idleButton(sweepButton);
        sweepButton.removeAttribute("disabled");
        showTrimmers();
      }
    }
  }

  /**
   * What the next sweep turns, and where: the trimmer from the Trimmers fold at its few
   * positions, else the pot picked at the positions typed (null: neither).
   * @returns {{rotations: number[]} | {error: string}}
   */
  function sweepTarget() {
    return trimmed ? { rotations: TRIM_POSITIONS } : parsePositions(sweepAt.value);
  }

  /** A pot's or trimmer's name in the sweep row. @param {string} ref */
  function knobName(ref) {
    return app.pots().find((p) => p.ref === ref)?.label ?? trimmerRows(app.circuit()).find((t) => t.ref === ref)?.name ?? ref;
  }

  /**
   * Check each position of a trimmer sweep for a saturated stage (D-198); a failed check
   * is said, and the takes still render.
   * @param {any} circuit @param {Sources} from what it's rendered from, the trimmer left out
   * @param {string} ref @param {number[]} rotations
   */
  async function checkStuck(circuit, from, ref, rotations) {
    const sig = JSON.stringify([from.circuit, from.knobs, ref, rotations]);
    if (stuck?.sig !== sig) {
      try {
        stuck = { ref, sig, rotations, found: await postJson("api/render/sweep/check", { circuit, ref, rotations }) };
      } catch (err) {
        stuck = null;
        say(/** @type {Error} */ (err).message, true);
      }
    }
    showStuck();
  }

  /** The saturation marks on the sweep's buttons, and the line saying what they mean. */
  function showStuck() {
    const ref = swept?.ref ?? trimmed;
    const on = stuck && stuck.ref === ref && sweepButtons.children.length === stuck.rotations.length ? stuck : null;
    const { marks, text } = on ? stuckText(on.rotations, on.found) : { marks: [], text: "" };
    trimStuck.textContent = text;
    trimStuck.hidden = !text;
    [...sweepButtons.children].forEach((b, i) => {
      b.classList.toggle("stuck", !!marks[i]);
      /** @type {HTMLElement} */ (b).dataset.stuck = marks[i] ?? "";
    });
    showSlots();
  }

  /** The Trimmers fold: a row per trimmer, hidden when the circuit has none. */
  function showTrimmers() {
    const rows = trimmerRows(app.circuit());
    trimFold.hidden = !rows.length;
    trimList.replaceChildren(...rows.map((t) => {
      const name = h("button", { type: "button", class: "link trim-name", title: "Show it on the schematic" }, [t.name]);
      name.addEventListener("click", () => app.highlight([t.ref], true));
      const go = h("button", { type: "button", "data-trim-render": t.ref }, ["Render"]);
      go.toggleAttribute("disabled", sweeping);
      go.addEventListener("click", () => {
        trimmed = t.ref;
        // the dropdown names what Render sweep turns next: blank again, so it doesn't seem
        // to disagree with the trimmer's takes in the row
        sweepPot.value = "";
        sweepButton.setAttribute("disabled", "");
        app.highlight([t.ref], true);
        startGraph();
        renderSweep();
      });
      return h("li", { "data-trimmer": t.ref, class: t.held ? "held" : "" }, [
        name,
        t.held ? h("span", { class: "hint" }, [t.held]) : go,
      ]);
    }));
  }

  /** What a take would be rendered from now (null: no clip picked). */
  function currentSources() {
    const req = request();
    return req ? renderSources(app.circuit(), app.view(), req) : null;
  }

  /** After the settings settle, look for takes already rendered for them (never renders). */
  function lookUpSoon() {
    clearTimeout(lookUpTimer);
    lookUpTimer = setTimeout(() => {
      renderPedal(true).catch(() => {});
      renderSweep(true).catch(() => {});
    }, LOOKUP_MS);
  }

  /**
   * The sweep row: the knob's name and a button per position. Before any sweep, the
   * positions typed, greyed; while one renders, each button fills as its take does.
   * @param {Job[]} [jobs] the sweep's jobs @param {number} [i] the one that moved @param {Job} [job] it now
   */
  function showSweep(jobs, i, job) {
    if (jobs && i !== undefined && job) {
      const b = /** @type {HTMLElement | undefined} */ (sweepButtons.children[i]);
      if (!b) return;
      const busy = job.state === "queued" || job.state === "running";
      b.classList.toggle("rendering", busy);
      b.style.setProperty("--done", `${Math.round(job.progress * 100)}%`);
      b.classList.toggle("failed", job.state === "failed");
      return;
    }
    const ref = swept?.ref ?? (trimmed || sweepPot.value);
    sweepName.textContent = ref ? knobName(ref) : "Sweep";
    const parsed = sweepTarget();
    const labels = jobs ? jobs.map((j) => `${j.label.split(" at ").at(-1)}`)
      : "rotations" in parsed ? parsed.rotations.map((r) => `${Math.round(r * 100)} %`) : [];
    sweepButtons.replaceChildren(...labels.map((label, n) => {
      const b = slotButton(`sweep-${n}`, label);
      b.addEventListener("pointerdown", startGraph);
      if (jobs) b.classList.add("rendering");
      return b;
    }));
    showSlots();
    showStuck();
  }

  /** Every take in one zip, with what each was made from. */
  async function downloadZip() {
    const { takes, files } = zipContents(slots, sweep, app.name());
    try {
      const url = URL.createObjectURL(await postJson("api/render/zip", { name: app.name(), takes, files }, undefined, "blob"));
      const a = h("a", { href: url, download: `${app.name()}.zip` });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      say(/** @type {Error} */ (err).message, true);
    }
  }

  /** Fetch the spectra of the takes in the slots that aren't here yet, and preload their audio. */
  async function loadSpectra() {
    const all = /** @type {string[]} */ ([...Object.values(slots), ...sweep].map((t) => t?.key).filter(Boolean));
    all.forEach(preload);
    forgetAudio();
    const keys = all.filter((k) => !spectra.has(k));
    await Promise.all(keys.map(async (key) => {
      try {
        spectra.set(/** @type {string} */ (key), await getJson(`api/render/spectrum/${key}`));
      } catch {
        // an old take whose spectrum isn't cached: it's left off the plot
      }
    }));
    drawSpectrum();
  }

  /** Draw the spectrum, if it's open. @param {boolean} [frame] only the live line moved */
  function drawSpectrum(frame = false) {
    for (const b of viewButtons) b.setAttribute("aria-checked", String(b.dataset.spectrumView === view));
    for (const t of toggles) {
      t.el.hidden = !SPECTRUM_CURVES.find(([id]) => id === t.id)?.[3].includes(/** @type {never} */ (view));
    }
    clipToggle.hidden = !clipped || view !== "pedal";
    if (!spectrum.open) return;
    /** @type {Record<string, Spectra | null>} */
    const takes = Object.fromEntries(SLOTS.map(([slot]) => [slot, (slots[slot] && spectra.get(slots[slot].key)) ?? null]));
    const expected = takes.dry && takes.pedal && curve ? expectedLevels(takes.dry, takes.pedal, curve, view) : null;
    const data = spectrumSeries(view, takes, shown, { expected, live, playing });
    const marks = { ...noMarks(), levels: clipBox.checked ? clipLines(clipped, view) : [] };
    const height = large.plotHeight(170);
    const opts = { log: true, xLabel: "Hz", yLabel: view === "pedal" ? "dBV" : "dBFS", legend: false, xRange: PLOT_BAND, shade: AUDIBLE, hatch: spectrumHatch(view, takes.dry, shown), yRange: spectrumRange(view, data), hover: { x: (/** @type {number} */ f) => `${Math.round(f)} Hz`, y: db }, marks, height };
    if (frame) liveLinePlot(plot, data, opts);
    else linePlot(plot, data, opts);
  }

  /**
   * A take's audio, fetched once into memory as soon as the take is there, so switching to
   * it is instant (the server's URL if the fetch fails). @param {string} key
   * @returns {Promise<string>}
   */
  function preload(key) {
    let url = audios.get(key);
    if (!url) {
      url = fetch(audioUrl(key))
        .then((r) => { if (!r.ok) throw new Error(r.statusText); return r.blob(); })
        .then((b) => URL.createObjectURL(b))
        .catch(() => { audios.delete(key); return audioUrl(key); });
      audios.set(key, url);
    }
    return url;
  }

  /** Let go of the audio of takes no longer in a slot or the sweep. */
  function forgetAudio() {
    const keep = new Set([...Object.values(slots), ...sweep].map((t) => t?.key));
    for (const [key, url] of audios) {
      if (keep.has(key) || key === playingKey) continue;
      audios.delete(key);
      url.then((u) => { if (u.startsWith("blob:")) URL.revokeObjectURL(u); });
    }
  }

  /**
   * Switch what the player plays, keeping its place (A/B).
   * @param {string} slot @param {boolean} [start] start playing (a click on the take)
   */
  async function play(slot, start = false) {
    const take = takeAt(slots, sweep, slot);
    if (!take) return;
    const at = player.currentTime;
    const wasPlaying = !player.paused;
    const opensThen = opens;
    playing = slot;
    const note = slot in slots ? sameTakeText(slots, /** @type {keyof Slots} */ (slot)) : "";
    say(note || take.text || "");
    if (take.key !== playingKey) live = null;
    showTake(take);
    if (take.key === playingKey) { // the same file: keep playing, don't reload
      if (start && player.paused) player.play().catch(() => {});
      return;
    }
    playingKey = take.key;
    const src = await preload(take.key);
    if (playingKey !== take.key) return; // another take was picked meanwhile
    player.src = src;
    player.addEventListener("loadedmetadata", () => {
      const sameCircuit = opens === opensThen;
      player.currentTime = sameCircuit ? Math.min(at, player.duration || 0) : 0;
      if ((wasPlaying || start) && sameCircuit) player.play().catch(() => {});
    }, { once: true });
  }

  /** The panel around the player, for the take it now plays. @param {Take} take */
  function showTake(take) {
    download.href = audioUrl(take.key, `${app.name()} ${take.label}`); // the server makes it a safe file name
    download.hidden = false;
    downloadAll.hidden = false;
    meter.textContent = ampText(take, slots.dry);
    showSlots();
    showChips();
    drawSpectrum();
  }

  function showSlots() {
    // the buttons, wherever they are: Dry / Pedal / Snapshot move onto the shrunk bar (D-110)
    for (const b of [...abButtons, ...sweepButtons.querySelectorAll("[data-slot]")]) {
      const slot = /** @type {string} */ (b.getAttribute("data-slot"));
      const take = takeAt(slots, sweep, slot);
      b.toggleAttribute("disabled", !take);
      b.setAttribute("aria-checked", String(slot === playing && !!take));
      // a trimmer sweep's position that saturates a stage says so (D-198)
      /** @type {HTMLElement} */ (b).title = [take?.label, /** @type {HTMLElement} */ (b).dataset.stuck].filter(Boolean).join(" · ");
    }
    keep.toggleAttribute("disabled", !takeAt(slots, sweep, playing));
  }

  /** Whether the circuit has a charge pump (its switching can be heard, slowly). */
  function hasPump() {
    return (app.circuit()?.parts ?? []).some((/** @type {any} */ p) => p.type === "chargepump");
  }

  /** What each chip says: the chosen clip, circuit, capture and IR, in short. */
  function showChips() {
    /** @param {string} kind */
    const chosen = (kind) => {
      const s = selects[kind];
      return s.value ? chipName(s.selectedOptions[0]?.textContent ?? "") : "None";
    };
    chips.guitar.value.textContent = selects.clips.value ? chosen("clips") : "No clip";
    chips.guitar.sub.textContent = `${levels.find((b) => b.getAttribute("aria-checked") === "true")?.textContent} pick`;
    const summary = guitarSummary(app.circuit(), app.pickups());
    chips.pedal.value.textContent = app.name();
    chips.pedal.sub.textContent = summary;
    pumpRow.hidden = !hasPump();
    pedalSummary.textContent = `Guitar input: ${summary}. The pickup, cable and volume are part of the circuit: they load its input, and its input loads them, just as plugging in does. Set them in the circuit's guitar input.`;
    chips.amp.value.textContent = chosen("captures");
    const take = takeAt(slots, sweep, playing);
    const squash = take?.amp ? take.amp_compression ?? 0 : null;
    gauge.style.width = `${squash === null ? 0 : Math.min(squash / GAUGE_DB, 1) * 100}%`;
    gaugeText.textContent = squash === null ? "" : `${squash.toFixed(0)} dB`;
    chips.cab.value.textContent = chosen("irs");
    chips.cab.sub.textContent = selects.irs.value ? "IR" : "";
  }

  /** The last sweep was rendered from something since changed (turning its own knob doesn't count). */
  function sweepIsStale() {
    return sweepChanges().length > 0;
  }

  /** What changed since the last sweep was rendered (its own knob doesn't count). @returns {string[]} */
  function sweepChanges() {
    const req = request();
    return swept && req ? changedSources(swept.from, withoutKnob(renderSources(app.circuit(), app.view(), req), swept.ref)) : [];
  }

  /** Say whether the latest take is out of date: what changed since it was rendered. */
  function showStale() {
    const req = request();
    const from = slots.pedal?.from;
    const text = from && req ? staleText(changedSources(from, renderSources(app.circuit(), app.view(), req))) : "";
    stale.textContent = text;
    stale.hidden = !text;
    renderButton.classList.toggle("stale", !!text);
    renderButton.title = text ? "Changed since the last take" : "";
    // the sweep's takes: out of date the same way, but turning the swept knob doesn't count
    // not rendered again with Render: a sweep is several renders, so it waits for Render sweep (D-134)
    const changes = sweepChanges();
    for (const b of sweepButtons.children) {
      b.classList.toggle("stale", changes.length > 0);
    }
    sweepStale.textContent = sweepStaleText(changes, trimmed && swept?.ref === trimmed ? "The trimmer's Render" : "Render sweep");
    sweepStale.hidden = !changes.length;
    lookUpSoon();
  }

  /** The circuit changed (opened another, or a new set of pots): refresh the pot list. */
  function update() {
    const pots = app.pots();
    const was = sweepPot.value;
    // the dropdown is the row's label: "Sweep" until a pot is picked
    const none = h("option", { value: "", disabled: "" }, ["Sweep"]);
    sweepPot.replaceChildren(none, ...pots.map((p) => h("option", { value: p.ref }, [p.label])));
    sweepPot.value = pots.some((p) => p.ref === was) ? was : "";
    sweepPot.disabled = !pots.length;
    sweepButton.toggleAttribute("disabled", !sweepPot.value);
    if (!swept) showSweep();
  }

  /**
   * Another circuit was opened: the player stops and goes back to the start. A take
   * already rendered for it is still found and loaded (see `lookUpSoon`), but waits for Play.
   */
  function opened() {
    opens++;
    player.pause();
    player.currentTime = 0;
  }

  /** Something about the circuit changed: the chips and the out-of-date note follow. */
  function changed() {
    // trimmers aren't knobs, so they're listed again on every change: a trimmer gone, or
    // now set by a target, can't be the next sweep
    if (trimmed && !trimmerRows(app.circuit()).some((t) => t.ref === trimmed && !t.held)) trimmed = "";
    showTrimmers();
    showChips();
    showStale();
  }

  /**
   * The output's frequency curve changed (a run finished, or a knob is moving): Expected
   * follows it. @param {Curve | null} next
   */
  function setCurve(next) {
    curve = next;
    if (shown.has("expected")) drawSpectrum(true);
  }

  /**
   * The probe's last scope run at the output, for the clipping note under the spectrum.
   * @param {Parameters<typeof clipText>[0] | null} stats @param {Parameters<typeof clipText>[1]} [run]
   */
  function setClipping(stats, run) {
    clipRun = stats && run ? { stats, run } : null;
    clipped = clipRun ? clipLevels(clipRun.stats, clipRun.run) : null;
    showClipping();
  }

  /** The clipping note, the limits line under the plot (while the lines show) and the spectrum. */
  function showClipping() {
    const text = clipRun ? clipText(clipRun.stats, clipRun.run) : null;
    clipNote.textContent = text ?? "";
    clipNote.hidden = !text;
    clipLimits.textContent = clipLimitsText(clipped);
    clipLimits.hidden = !(clipBox.checked && view === "pedal" && clipped);
    drawSpectrum();
  }

  loadAssets().catch((err) => say(err.message, true));
  showSlots();
  drawSpectrum();

  return {
    update, changed, opened, setCurve, setClipping,
    /** Back to the panel, as the app does when another circuit opens (`backToEditor`). */
    collapse: large.collapse,
  };
}
