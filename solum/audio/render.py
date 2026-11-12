"""Rendering a clip through the circuit, then an amp capture and a cab IR (D-015, D-083).

clip WAV → mono, peak scaled to a pick level (volts) → (with a pickup on the guitar
input: the pickup's own colour taken out, D-096) → 96 kHz text file → ngspice transient
(the guitar plays the file) → the amp input's volts on a 96 kHz grid, DC removed (kept
in the cache, so a change after the pedal re-runs only the amp) → 48 kHz → volts to
the capture's digital level → Input trim → NAM → cab IR → WAV (loudness is the
player's). On the way it measures how hard the amp is hit: the peak going into the
capture (`amp_in`) and how much the capture squashes the signal (`amp_compression`:
its output against a copy played `PROBE_DB` quieter, where it stays clean).

A DI recording already carries its pickup's colour, so the guitar input's pickup would
colour it twice. Before the render the clip is filtered by the inverse of that same
guitar (pickup, cable, volume pot on 10) played into a DI's 1 MΩ input, so into a
high-impedance circuit the clip comes out as recorded, and into a low-impedance one (a
Fuzz Face) only the loading changes it (`undo_pickup`).

A "dry" render skips the circuit: the guitar straight into the amp, at the same level, so
A/B compares like with like. Results are cached by a key over everything that decides
them (`render_key`), so playing a render again costs nothing.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt

from solum.analysis.signal import SILENT_DB, band_levels
from solum.audio.ir import convolve, load_ir
from solum.audio.nam import NamModel, load_nam, run_nam
from solum.audio.resample import resample
from solum.audio.wav import Audio, WavError, read_wav, write_wav
from solum.cache import SimCache, content_hash
from solum.circuit.build import guitar_into
from solum.circuit.schema import AmpInput, ChargePump, Circuit, Guitar
from solum.netlist import Ac, NetlistError, input_part
from solum.sim.engine import SimTimeout
from solum.simulate import LEVELS, Simulator

Array = npt.NDArray[np.float64]
Complex = npt.NDArray[np.complex128]
Progress = Callable[[float], None]

RENDER_VERSION = "8"  # bump when the pipeline's output changes for the same inputs
TRIM_DB = (-40.0, 20.0)  # the range of the Input and Output trims
PROBE_DB = 60.0  # the quiet copy for the amp's clean gain (D-086: 60 and 80 dB agree)
SIM_RATE = 96000  # the transient's step: oversampled 2x (SPEC §7)
RATE = 48000  # what comes out
MAX_CLIP_SECONDS = 10.0
DBU_VOLTS = 0.7746  # 0 dBu, RMS volts
# A capture's `input_level_dbu` is the dBu of a 1 kHz sine at 0 dBFS peak (the .nam
# spec). Captures without it are assumed to have been made at this level (D-083).
DEFAULT_INPUT_DBU = 12.0
SIM_SHARE = 0.9  # of the progress bar: the ngspice run; the rest is resampling and NAM
DI_INPUT = "1M"  # what a DI is recorded into: an audio interface's Hi-Z input (D-096)
UNDO_MAX_DB = 24.0  # the undo boosts at most this (above the pickup's peak a DI is mostly noise)
UNDO_FADE_S = 0.005  # the undone clip fades in over this (see `undo_pickup`)


class RenderError(ValueError):
    """A render can't be done (plain-English message)."""


@dataclass(frozen=True)
class Inputs:
    """What a render plays: file contents, so the cache key follows the files."""

    clip: bytes  # a WAV file
    nam: bytes | None = None  # a .nam capture
    ir: bytes | None = None  # a cab IR WAV
    level: str = "med"  # the clip's peak in volts at the guitar output, `LEVELS`
    input_db: float = 0.0  # the amp's Input: more or less into the capture (no capture: unused)
    pump_ripple: bool = False  # charge pumps switch (slow: ~10x); off, their average


@dataclass(frozen=True)
class Rendered:
    wav: bytes  # mono 32-bit float, `RATE`
    seconds: float
    peak: float  # above 1 the WAV is louder than full scale (kept, not clipped)
    amp_in: float  # peak into the capture (after Input); 1 = the capture's 0 dBFS
    amp_compression: float = 0.0  # dB the capture squashes it; 0 = clean (or no capture)
    # the take's spectrum (`take_spectra`): band centres, the pedal's output, what's heard,
    # and the guitar's own colour as a DI has it
    spectra: dict[str, list[float] | float] = field(default_factory=dict)

    def stats(self) -> dict[str, float]:
        return {"seconds": self.seconds, "peak": self.peak, "amp_in": self.amp_in,
                "amp_compression": self.amp_compression}  # fmt: skip


def _input_db(inputs: Inputs) -> float:
    """The amp's Input trim in dB, checked; it counts only with a capture."""
    low, high = TRIM_DB
    if not low <= inputs.input_db <= high:
        raise RenderError(
            f"Input must be between {low:g} and {high:+g} dB (got {inputs.input_db:g})."
        )
    return inputs.input_db if inputs.nam else 0.0


def full_scale_volts(dbu: float) -> float:
    """Peak volts of a 0 dBFS sine whose level is `dbu`."""
    return float(DBU_VOLTS * 10 ** (dbu / 20) * np.sqrt(2))


def read_clip(data: bytes) -> Audio:
    """A clip, checked: readable, not silent, at most `MAX_CLIP_SECONDS`."""
    clip = read_wav(data)
    if clip.seconds > MAX_CLIP_SECONDS:
        raise WavError(
            f"This clip is {clip.seconds:.1f} s long; clips can be up to "
            f"{MAX_CLIP_SECONDS:g} s. Trim it and upload it again."
        )
    if len(clip.samples) == 0 or not np.any(clip.samples):
        raise WavError("This clip is silent.")
    return clip


def clip_gain(clip: Audio, level: str) -> float:
    """Volts per full-scale unit: the clip's peak becomes the pick level's amplitude."""
    if level not in LEVELS:
        raise RenderError(f"Level must be one of {', '.join(LEVELS)} (got {level!r}).")
    return LEVELS[level] / float(np.max(np.abs(clip.samples)))


def source_path(cache_dir: Path, clip_data: bytes, guitar: Guitar | None = None) -> Path:
    """Where the clip's 96 kHz "time volts" file lives: named by the clip's content and,
    with a pickup on the guitar input, by the pickup taken out of it (`undo_pickup`)."""
    parts = [clip_data, str(SIM_RATE).encode()]
    if guitar is not None and guitar.source == "pickup":
        undo = guitar.model_dump(include={"pickup", "cable", "volume", "taper"}, mode="json")
        parts.append(repr((sorted(undo.items()), DI_INPUT, UNDO_MAX_DB)).encode())
    return cache_dir / "audio" / "sources" / f"{content_hash(*parts)}.txt"


def write_source(path: Path, clip: Audio, shape: Callable[[Array], Array] | None = None) -> int:
    """The clip at `SIM_RATE` as ngspice's file source reads it (unscaled; the netlist
    scales it), through `shape` if given. Written once; returns the number of samples."""
    x = resample(clip.samples, clip.rate, SIM_RATE)
    if not path.exists():
        x = shape(x) if shape else x
        path.parent.mkdir(parents=True, exist_ok=True)
        t = np.arange(len(x)) / SIM_RATE
        tmp = path.with_suffix(f".{os.getpid()}.tmp")  # workers may race on one clip
        tmp.write_text(source_text(t, x))
        tmp.replace(path)
    return len(x)


SOURCE_ROWS = 20_000  # rows formatted at a time


def source_text(time: Array, volts: Array) -> str:
    """ "time volts" lines, as `np.savetxt` with `%.10g %.8g` writes them, about four times
    as fast (a second saved on a clip's first render, Phase 10): one format string for
    a block of rows instead of a call a row."""
    blocks = []
    for i in range(0, len(time), SOURCE_ROWS):
        pairs = np.column_stack([time[i : i + SOURCE_ROWS], volts[i : i + SOURCE_ROWS]])
        blocks.append("%.10g %.8g\n" * len(pairs) % tuple(pairs.ravel().tolist()))
    return "".join(blocks)


def amp_net(circuit: Circuit) -> str:
    """What the amp hears: the amp input part's pin."""
    amp = next((p for p in circuit.parts if isinstance(p, AmpInput)), None)
    if amp is None:
        raise NetlistError("Add an amp output to the circuit to hear it.")
    return f"{amp.ref}.in"


def _seconds(clip: Audio) -> float:
    return round(len(clip.samples) * SIM_RATE / clip.rate) / SIM_RATE


def pedal_key(sim: Simulator, circuit: Circuit | None, inputs: Inputs, cache_dir: Path) -> str:
    """What the amp gets, as a key: the recording's netlist (circuit, models, clip file with
    any pickup taken out, level) and the engine, or the clip and level for a dry render."""
    clip = read_clip(inputs.clip)
    gain = clip_gain(clip, inputs.level)
    if circuit is None:
        return content_hash("dry", inputs.clip, repr(gain))
    path = source_path(cache_dir, inputs.clip, input_part(circuit))
    netlist = sim.recording_netlist(
        circuit, str(path), gain, _seconds(clip), SIM_RATE, [amp_net(circuit)], inputs.pump_ripple
    )
    return content_hash(sim.engine.name, sim.engine.version(), netlist.text)


def render_key(sim: Simulator, circuit: Circuit | None, inputs: Inputs, cache_dir: Path) -> str:
    """The cache key: what the amp gets (`pedal_key`), the capture, the IR, the Input trim
    and `RENDER_VERSION`."""
    what = pedal_key(sim, circuit, inputs, cache_dir)
    trim = repr(_input_db(inputs))
    return content_hash(RENDER_VERSION, what, inputs.nam or b"", inputs.ir or b"", trim)


def render(
    sim: Simulator,
    circuit: Circuit | None,
    inputs: Inputs,
    cache_dir: Path,
    progress: Progress | None = None,
    cache: SimCache | None = None,
) -> Rendered:
    """The clip through the circuit (None: dry), the capture and the IR. With `cache`, the
    circuit's output is kept, so a render that differs only after the pedal (capture, IR,
    Input) doesn't simulate again."""
    report = progress or (lambda _f: None)
    input_db = _input_db(inputs)
    clip = read_clip(inputs.clip)
    gain = clip_gain(clip, inputs.level)
    nam = _capture(inputs.nam)
    ir = load_ir(inputs.ir, RATE) if inputs.ir else None
    if circuit is None:
        volts = resample(clip.samples, clip.rate, RATE) * gain
        pedal, pedal_rate = clip.samples * gain, float(clip.rate)  # Dry at the clip's own rate
    else:
        key = content_hash(RENDER_VERSION, "pedal", pedal_key(sim, circuit, inputs, cache_dir))
        kept = cache.get_bytes(key) if cache else None
        if kept is not None:
            pedal = np.frombuffer(kept, dtype=np.float32).astype(np.float64)
        else:
            path = source_path(cache_dir, inputs.clip, input_part(circuit))
            pedal = _through_circuit(sim, circuit, clip, gain, path, report, inputs.pump_ripple)
            if cache:
                cache.put_bytes(key, pedal.astype(np.float32).tobytes())
        pedal_rate = float(SIM_RATE)
        volts = resample(pedal, SIM_RATE, RATE)
    report(SIM_SHARE)
    out, amp_in, squash = _through_amp(volts, nam, ir, input_db)
    spectra = take_spectra(sim, circuit, pedal, out, pedal_rate)
    report(1.0)
    return Rendered(
        write_wav(Audio(RATE, out)), len(out) / RATE, _peak(out), amp_in, squash, spectra
    )


def take_spectra(
    sim: Simulator,
    circuit: Circuit | None,
    volts: Array,
    out: Array,
    volts_rate: float = RATE,
) -> dict[str, list[float] | float]:
    """A take's spectrum for the Audio panel (D-096), per 1/6-octave band (`freq`): the
    pedal's output in dBV (`pedal`), the take as heard in dBFS (`heard`), and the guitar
    input's pickup as a DI recorded it (`di`, dB; 0 with no pickup), which the page takes
    off the live pedal curve so "expected" is the clip through the pedal. `volts` is read
    at its own rate (D-105): a pedal take's 96 kHz simulation reaches 30 kHz, like the
    Frequency chart, and a dry take is the clip at its own rate (a 96 kHz clip reaches 30
    kHz too); `pedal_top` is the highest frequency it can hold (half its rate). The heard
    take is 48 kHz and reads silent (-200 dB) above its 23 kHz band. The segment keeps the
    same resolution at any rate."""
    segment = round(8192 * volts_rate / RATE)
    at_pedal, pedal = band_levels(volts, volts_rate, segment=segment)
    at_heard, heard = band_levels(out, RATE)
    # one band list for both: the shorter line reads silent where it has no bands
    centres = at_pedal if len(at_pedal) >= len(at_heard) else at_heard

    def padded(a: Array) -> Array:
        return np.concatenate([a, np.full(len(centres) - len(a), SILENT_DB)])

    pedal, heard = padded(pedal), padded(heard)
    di = np.zeros_like(centres)
    guitar = input_part(circuit) if circuit is not None else None
    if guitar is not None and guitar.source == "pickup":
        freq, h = di_response(sim, guitar)
        di = np.interp(np.log10(centres), np.log10(freq), 20 * np.log10(np.abs(h)))

    def tidy(a: Array) -> list[float]:
        return [round(float(v), 2) for v in a]

    return {
        "freq": tidy(centres),
        "pedal": tidy(pedal),
        "heard": tidy(heard),
        "di": tidy(di),
        "pedal_top": volts_rate / 2,
    }


def timeout_message(circuit: Circuit, seconds: float, limit: float, done: float) -> str:
    """Why a render of `seconds` was stopped after `limit` s with `done` (0-1) of it
    simulated, and what to do: a charge pump is the usual cause (D-095)."""
    said = f"The render was stopped: a {seconds:g} s clip may run for up to {_duration(limit)}"
    if done > 0:
        said += (
            f", and it had got through {done * 100:.0f} % of it. At that pace the whole clip needs "
            f"about {_duration(limit / done)}, {limit / done / seconds:.0f} times longer than"
            " the clip plays."
        )
    else:
        said += "."
    pumps = [p.ref for p in circuit.parts if isinstance(p, ChargePump)]
    if pumps:
        return (
            f"{said} The likely cause is the charge pump ({', '.join(pumps)}): the simulator"
            " follows every switch of its oscillator, which is slow. Render a shorter clip,"
            " or leave the pump out while you tune (build on an 18 V supply) and add it last."
        )
    return (
        f"{said} Something makes the simulator take tiny steps: most often an oscillator,"
        " such as an op-amp charge pump block, or a part with an extreme value. Render a"
        " shorter clip, or leave the oscillator out while you tune."
    )


def _duration(seconds: float) -> str:
    """'45 s', '2 min 30 s', '12 min'."""
    s = round(seconds)
    if s <= 90:
        return f"{s} s"
    m, rest = divmod(s, 60)
    return f"{m} min" if m >= 10 or rest < 5 else f"{m} min {rest // 5 * 5} s"


def _peak(x: Array) -> float:
    return float(np.max(np.abs(x))) if len(x) else 0.0


def _capture(data: bytes | None) -> NamModel | None:
    return load_nam(data) if data else None


def _through_circuit(
    sim: Simulator,
    circuit: Circuit,
    clip: Audio,
    gain: float,
    path: Path,
    report: Progress,
    pump_ripple: bool = False,
) -> Array:
    """The amp input's volts at `SIM_RATE`, its DC (the operating point) removed."""
    guitar = input_part(circuit)
    undo = guitar if guitar is not None and guitar.source == "pickup" else None
    n = write_source(path, clip, (lambda x: undo_pickup(sim, undo, x)) if undo else None)
    net = amp_net(circuit)
    done = [0.0]

    def progress(fraction: float) -> None:
        done[0] = fraction
        report(SIM_SHARE * fraction)

    try:
        time, waves = sim.recording(
            circuit, str(path), gain, _seconds(clip), SIM_RATE, [net], progress, pump_ripple
        )
    except SimTimeout as err:
        raise RenderError(timeout_message(circuit, _seconds(clip), err.seconds, done[0])) from err
    wave = waves[net]
    grid: Array = np.interp(np.arange(n) / SIM_RATE, time, wave) - wave[0]
    return grid


def di_reference(guitar: Guitar) -> Circuit:
    """The guitar as a DI recorded it: the same pickup, cable and volume pot (on 10),
    into a DI's 1 MΩ input, on net `in`."""
    return guitar_into(guitar, DI_INPUT, rotation=1.0)


def di_response(sim: Simulator, guitar: Guitar) -> tuple[Array, Complex]:
    """(freq, response) of `di_reference`: ngspice's AC run of the guitar's own netlist,
    1 Hz to half `SIM_RATE`."""
    ac = sim.ac(di_reference(guitar), Ac(start=1.0, stop=SIM_RATE / 2, per_decade=100))
    return ac.freq, ac.responses["in"]


def undo_pickup(sim: Simulator, guitar: Guitar, x: Array) -> Array:
    """`x` (at `SIM_RATE`) with the guitar's own colour taken out (D-096): divided, per
    frequency, by `di_response`, boosting at most `UNDO_MAX_DB`."""
    at, h_at = di_response(sim, guitar)
    n = len(x)
    spectrum = np.fft.rfft(x, 2 * n)  # padded: the filter doesn't wrap around
    f = np.log10(np.clip(np.fft.rfftfreq(2 * n, 1 / SIM_RATE), at[0], at[-1]))
    grid = np.log10(at)
    h = np.interp(f, grid, h_at.real) + 1j * np.interp(f, grid, h_at.imag)
    floor = 10 ** (-UNDO_MAX_DB / 20)
    h = np.where(np.abs(h) < floor, h / np.abs(h) * floor, h)
    y = np.fft.irfft(spectrum / h, 2 * n)[:n]
    # The filter rings a little at a sudden start; the take's DC is read at t = 0 (the
    # operating point), so the clip must start from 0 as it did: fade in over UNDO_FADE_S.
    k = min(n, int(UNDO_FADE_S * SIM_RATE))
    y[:k] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k)
    return np.asarray(y, dtype=np.float64)


def _through_amp(
    volts: Array, nam: NamModel | None, ir: Array | None, input_db: float = 0.0
) -> tuple[Array, float, float]:
    """Volts → the capture's digital level → Input → NAM → cab IR, with the peak
    that went into the capture and how much it squashed it (`compression_db`). Without a
    capture the volts are scaled at the default level, so a circuit alone can be heard."""
    dbu = nam.input_level_dbu if nam and nam.input_level_dbu is not None else DEFAULT_INPUT_DBU
    x = volts / full_scale_volts(dbu) * 10 ** (input_db / 20)
    amp_in, squash = _peak(x), 0.0
    if nam is not None:
        rate = nam.sample_rate
        at_rate = resample(x, RATE, rate)
        y = run_nam(nam, at_rate).astype(np.float64)
        squash = compression_db(nam, at_rate, y)
        x = resample(y, rate, RATE)
    if ir is not None:
        x = convolve(x, ir)
    return np.asarray(x, dtype=np.float64), amp_in, squash


def compression_db(nam: NamModel, x: Array, y: Array) -> float:
    """How much quieter the capture's output `y` is than it would be if the amp stayed
    clean, in dB (0 = clean): its gain for `x` against its gain for a copy `PROBE_DB`
    quieter. The model's DC offset is left out."""

    def rms(v: Array) -> float:
        return float(np.sqrt(np.mean((v - np.mean(v)) ** 2))) if len(v) else 0.0

    quiet = run_nam(nam, x * 10 ** (-PROBE_DB / 20)).astype(np.float64)
    loud, soft = rms(y), rms(quiet)
    if loud == 0 or soft == 0:
        return 0.0
    return max(0.0, float(20 * np.log10(soft / loud) + PROBE_DB))
