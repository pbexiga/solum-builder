"""Plain-text and JSON summaries of simulation results (used by `solum run`)."""

import math
from typing import Any

from solum.analysis.measures import corner_3db, gain_at, peak
from solum.analysis.signal import NodeStats
from solum.simulate import AcResult, OpResult, TranResult
from solum.units import format_value

SPOT_FREQS = (100.0, 1000.0, 10000.0)


def hz(f: float) -> str:
    return f"{format_value(f)}Hz"


def op_summary(op: OpResult) -> dict[str, Any]:
    return {"voltages": op.voltages, "currents": op.currents, "bias": op.bias}


def op_text(op: OpResult) -> str:
    lines = ["DC operating point (volts)"]
    width = max((len(n) for n in op.voltages), default=0)
    lines += [f"  {net:<{width}}  {v:8.3f}" for net, v in sorted(op.voltages.items())]
    if op.currents:
        lines.append("Transistor currents")
        lines += [f"  {k:<{width}}  {format_value(v)}A" for k, v in sorted(op.currents.items())]
    for ref, rotation in sorted(op.bias.items()):
        lines.append(f"Bias: {ref} solved to {rotation * 100:.1f} % rotation")
    return "\n".join(lines)


def ac_summary(ac: AcResult, net: str) -> dict[str, Any]:
    h = ac.responses[net]
    f_peak, db_peak = peak(ac.freq, h)
    out: dict[str, Any] = {
        "net": net,
        "valid": ac.valid,
        "saturated": [s.message for s in ac.saturated],
        "peak": {"freq": f_peak, "db": db_peak},
        "gain_db": {
            f"{f:g}": gain_at(ac.freq, h, f) for f in SPOT_FREQS if ac.freq[0] <= f <= ac.freq[-1]
        },
    }
    for side in ("low", "high"):
        try:
            out[f"corner_{side}"] = corner_3db(ac.freq, h, side)
        except ValueError:
            out[f"corner_{side}"] = None
    return out


def ac_text(ac: AcResult, net: str) -> str:
    s = ac_summary(ac, net)
    lines = [f"Frequency response at {net} (vs the guitar input)"]
    if not s["valid"]:
        lines.append(
            "  Not valid: an active stage is saturated at DC, so this curve means nothing."
        )
        lines += [f"    {m}" for m in s["saturated"]]
    lines.append(f"  peak {s['peak']['db']:+.1f} dB at {hz(s['peak']['freq'])}")
    low, high = s["corner_low"], s["corner_high"]
    if low or high:
        band = f"{hz(low) if low else 'below the sweep'} to {hz(high) if high else 'above it'}"
        lines.append(f"  -3 dB band: {band}")
    lines.append(
        "  " + ", ".join(f"{hz(float(f))}: {db:+.1f} dB" for f, db in s["gain_db"].items())
    )
    return "\n".join(lines)


def stats_summary(net: str, s: NodeStats) -> dict[str, Any]:
    return {
        "net": net,
        "dc": s.dc,
        "gain_db": s.gain_db,
        "polarity": s.polarity,
        "peak_pos": s.peak_pos,
        "peak_neg": s.peak_neg,
        "harmonics_db": s.harmonics_db,
        "clipping": {
            "label": s.clipping.label,
            "thd": s.clipping.thd,
            "asymmetry": s.clipping.asymmetry,
        },
    }


def tran_summary(tran: TranResult) -> dict[str, Any]:
    return {
        "level": tran.level,
        "amplitude": tran.amplitude,
        "freq": tran.freq,
        "nodes": [stats_summary(net, s) for net, s in tran.stats.items()],
    }


def tran_text(tran: TranResult) -> str:
    lines = []
    for net, s in tran.stats.items():
        lines += [
            f"Waveform at {net}, {tran.level} input ({tran.amplitude:g} V peak, {tran.freq:g} Hz)",
            f"  gain {s.gain_db:+.1f} dB, {s.polarity} polarity; DC {s.dc:.2f} V; "
            f"peaks {s.peak_pos:+.3f} / {s.peak_neg:+.3f} V",
            f"  clipping: {s.clipping.label} (THD {s.clipping.thd * 100:.1f} %, "
            f"asymmetry {s.clipping.asymmetry:+.2f})",
            "  harmonics (dB vs fundamental): "
            + "  ".join(
                f"{k}: {db:.0f}" if math.isfinite(db) else f"{k}: -"
                for k, db in s.harmonics_db.items()
            ),
        ]
    return "\n".join(lines)
