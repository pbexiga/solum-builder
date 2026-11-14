"""Probe views: what a click on a net or a part shows (SPEC §2, D-002), as JSON-ready data.

`run_view` is the node view and the panels' data: DC at every net, the frequency response
and the scope at the probed nets plus the output. `part_view` is the view for one part,
by type. Both go through `Simulator`, so bias targets are solved and runs are cached.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import ValidationError

from solum.analysis.compare import knob_range
from solum.analysis.dc import (
    BJT_VCE_SAT,
    OPAMP_RAIL_MARGIN,
    Saturation,
    mosfet_vds_sat,
    opamp_input_limits,
    opamp_output_limits,
)
from solum.analysis.measures import corner_3db, features, gain_at, peak, readings, to_db
from solum.analysis.signal import NodeStats, last_cycles
from solum.circuit.build import CircuitBuilder, guitar_into
from solum.circuit.chips import supply_nets, unused
from solum.circuit.connectivity import Nets, connect, loose_net, loose_parts
from solum.circuit.pot import pot_resistances
from solum.circuit.pump import SPARE_PINS
from solum.circuit.schema import (
    POLARISED,
    AmpInput,
    Bjt,
    Capacitor,
    ChargePump,
    Circuit,
    Diode,
    Guitar,
    Inductor,
    Jfet,
    Led,
    Mosfet,
    Opamp,
    Part,
    Pot,
    Resistor,
    Switch,
    Trimmer,
)
from solum.circuit.supply import supply_volts
from solum.netlist import Dc, input_part
from solum.simulate import (
    IMPEDANCE_HZ,
    LEVELS,
    TONE_HZ,
    TONES,
    AcResult,
    OpResult,
    Simulator,
    TranResult,
)
from solum.stages import (
    Clips,
    Stage,
    bias_position,
    clipper_clips,
    device_room,
    drive_db,
    first_to_clip,
    harmonic_lead,
    headroom_db,
    pot_places,
    signal_input,
    signal_stages,
    stage_clips,
    stage_parts,
)
from solum.units import format_quantity, parse_value, signed_db
from solum.view import controls, drawn_pins, part_text, probe_nets, rail_nets

Progress = Callable[[int, int], None]  # steps done, of how many: a progress bar (D-123)


def _quiet(_done: int, _of: int) -> None:
    """No progress bar to tell."""


Array = npt.NDArray[np.float64]

SCOPE_CYCLES = 2  # cycles of the 200 Hz tone shown on the scope
SWEEP_MAX = 5  # "compare several values": most runs or renders at once (SPEC §2, D-096)
SWEEP_FIELDS = ("value", "model", "rail")  # rail: `ref` names a supply rail (D-068)
CURVE_POINTS = 200  # steps in a device curve
DIODE_RANGE = {"diode": (-1.0, 1.0), "led": (-1.0, 3.0)}  # volts across, for the I-V curve
BJT_VBE_BELOW, BJT_VBE_ABOVE = 0.25, 0.15  # transfer curve span around the operating Vbe
MOSFET_VGS_ABOVE = 2.0  # transfer curve reaches this far past the gate (or VTO)
MOSFET_VGS_BELOW = 0.5  # a depletion MOSFET's starts this far below its VTO (or gate)
SIGNAL_FLOOR = 1e-3  # a stage the tone reaches this much weaker than the guitar isn't on the path


def floats(values: npt.ArrayLike) -> list[float]:
    """Values for the browser, to 6 significant figures (frequencies, times): the same
    grid however it was computed (a log axis ending at 100000.0000001 spans a decade more)."""
    return [float(f"{x:.6g}") for x in np.asarray(values, dtype=np.float64)]


def _db(h: npt.NDArray[np.complex128]) -> list[float]:
    return [round(float(x), 2) for x in to_db(h)]


def op_data(op: OpResult) -> dict[str, Any]:
    """The DC results; `supply` is what each rail delivers (amps, and as text: "23.4 mA");
    `held`: each bias target, where it is, its trimmer's turn and whether it's met (D-127)."""
    return {
        "voltages": op.voltages, "currents": op.currents, "bias": op.bias,
        "held": [{**asdict(h), "met": h.met} for h in op.held],
        "supply": {rail: {"amps": amps, "text": format_quantity(abs(amps), "A")}
                   for rail, amps in op.supply.items()},
    }  # fmt: skip


def freq_axis(freq: Array) -> dict[str, Any]:
    """A frequency grid for the plots: its values (`floats`) and each as text ("1.2 kHz"),
    so the plots' hover readout shows frequencies the way the rest of the app does."""
    return {"freq": floats(freq), "freq_text": [format_quantity(float(f), "Hz") for f in freq]}


def ac_data(ac: AcResult, nets: Sequence[str]) -> dict[str, Any]:
    return {
        **freq_axis(ac.freq),
        "valid": ac.valid,
        "saturated": [asdict(s) for s in ac.saturated],
        "nodes": {net: _db(ac.responses[net]) for net in nets if net in ac.responses},
        "readings": {
            net: readings(ac.freq, ac.responses[net]) for net in nets if net in ac.responses
        },
        "features": {
            net: features(ac.freq, ac.responses[net]) for net in nets if net in ac.responses
        },
    }


def knob_ranges(sim: Simulator, circuit: Circuit, net: str) -> dict[str, Any]:
    """Where each knob (a pot, the guitar's volume) acts on the curve at `net`: ngspice's
    curve with the knob at its minimum and at its maximum, compared by `knob_range`
    (Phase 8b). `valid`: neither end saturates a stage (the curve would mean nothing)."""
    name = sim.resolve(circuit, net)
    now = sim.ac(circuit)
    knobs = []
    for control in controls(circuit):
        if control["kind"] != "pot":
            continue
        ref = control["ref"]
        ends = [sim.ac(circuit.with_part(ref, rotation=r)) for r in (0.0, 1.0)]
        low, high = (e.responses[name] for e in ends)
        found = knob_range(now.freq, low, high, now.responses[name])
        valid = all(e.valid for e in ends)
        knobs.append({"ref": ref, "label": control["label"], "valid": valid, **found})
    return {"net": name, "knobs": knobs}


def scope_window(tran: TranResult, net: str) -> Array:
    """The last SCOPE_CYCLES cycles at `net`, on an even time grid."""
    return last_cycles(tran.time, tran.waves[net], tran.freq, SCOPE_CYCLES)


def tran_data(tran: TranResult, nets: Sequence[str]) -> dict[str, Any]:
    """Scope traces with the input overlaid, scaled by the node's gain and polarity so the
    two shapes can be compared directly."""
    inp = scope_window(tran, tran.input)
    n = len(inp)
    nodes = {}
    for net in nets:
        stats = tran.stats[net]
        scale = 10 ** (stats.gain_db / 20) * (-1 if stats.polarity == "inverted" else 1)
        nodes[net] = {
            "wave": floats(scope_window(tran, net)),
            "overlay": floats(stats.dc + scale * (inp - inp.mean())),
            "stats": asdict(stats),
        }
    return {
        "level": tran.level,
        "amplitude": tran.amplitude,
        "freq": tran.freq,
        "input": tran.input,
        "time_ms": _time_ms(tran, n),
        "nodes": nodes,
    }


def _time_ms(tran: TranResult, n: int) -> list[float]:
    return floats(np.arange(n) * 1e3 * SCOPE_CYCLES / (tran.freq * n))


def run_view(sim: Simulator, circuit: Circuit, nodes: Sequence[str], level: str) -> dict[str, Any]:
    """DC everywhere; AC and scope at `nodes` and the output. AC and scope are None when
    the circuit has no guitar input."""
    nets = connect(circuit)
    probes = probe_nets(circuit, nets)
    wanted = [nets.resolve(n) for n in nodes] + ([probes.output] if probes.output else [])
    wanted = list(dict.fromkeys(wanted))
    result: dict[str, Any] = {
        "op": op_data(sim.op(circuit)),
        "nodes": wanted,
        "ac": None,
        "tran": None,
    }
    if input_part(circuit) is not None:
        loose = loose_parts(circuit, nets)  # nothing to show on their nets (D-165)
        wired = [net for net in wanted if not loose_net(nets, loose, net)]
        result["ac"] = ac_data(sim.ac(circuit), wanted)
        result["tran"] = tran_data(sim.tran(circuit, wired, level), wired)
        result["impedance"] = {net: _ohms(*sim.impedance(circuit, net)) for net in wired}
    return result


def _ohms(z: complex, saturated: Sequence[Saturation]) -> dict[str, Any]:
    """An impedance as the page shows it: its size in ohms and words ("47.2 kΩ"), at
    `IMPEDANCE_HZ`; with a stage saturated at DC, why it means little (D-127)."""
    note = saturated[0].message if saturated else None
    return {"ohms": abs(z), "text": format_quantity(abs(z), "\u03a9"), "freq": IMPEDANCE_HZ,
            "saturated": note}  # fmt: skip


RESONANCE_BAND = (500.0, 20e3)  # where a pickup's resonant peak is looked for (Hz)
RESONANCE_BASE_HZ = 100.0  # the level a peak rises over
RESONANCE_MIN_DB = 0.5  # less than this over the base is no peak: the load rolls it off


def impedance_view(sim: Simulator, circuit: Circuit) -> dict[str, Any]:
    """The View → Impedance overlay (D-127, D-241), at `IMPEDANCE_HZ`: what the circuit
    looks like to the guitar (Zin at its net, the guitar left out) and to the amp (Zout at
    its net, the amp left out), with their parts' refs to draw them under; None for a
    missing end. Each says what the loading does to the level (`level_db`, `level_text`,
    against the source unloaded): the input, the
    guitar's own source impedance (`source`, the pedal left out) and its pickup's resonant
    peak straight into the amp and into the pedal (`resonance`); the output, the amp's
    input impedance (`load`) and the knobs at the output that Zout follows (`follows`)."""
    nets = connect(circuit)
    probes = probe_nets(circuit, nets)
    guitar = input_part(circuit)
    amp = next((p for p in circuit.parts if isinstance(p, AmpInput)), None)
    out: dict[str, Any] = {"freq": IMPEDANCE_HZ, "zin": None, "zout": None}
    if guitar is None:
        return out
    amp_ohms = str(amp.value) if amp is not None else "1M"
    if probes.input is not None:
        z, saturated = sim.impedance(circuit, probes.input, open=guitar.ref)
        alone = guitar_into(guitar, amp_ohms)
        source = sim.impedance(alone, "in", open="OUT")[0]
        out["zin"] = {
            "ref": guitar.ref, "net": probes.input, **_ohms(z, saturated),
            **_level(source, z), "source": _ohms(source, [])["text"],
            "resonance": _resonances(sim, circuit, guitar, alone, probes.input),
            "amp": format_quantity(parse_value(amp_ohms), "\u03a9"),
        }  # fmt: skip
    if amp is not None and probes.output is not None:
        z, saturated = sim.impedance(circuit, probes.output, open=amp.ref)
        load = parse_value(str(amp.value))
        out["zout"] = {
            "ref": amp.ref, "net": probes.output, **_ohms(z, saturated), **_level(z, load),
            "load": format_quantity(load, "\u03a9"),
            "follows": _output_knobs(circuit, nets, probes.output),
        }  # fmt: skip
    return out


def _level(source: complex, load: complex) -> dict[str, Any]:
    """What a source impedance driving a load does to the level, against the source
    unloaded: 20·log10|load / (source + load)| dB, and as the overlay writes it (a minus
    sign). Usually a loss; a coil into a capacitive input can resonate and rise a little
    (a pickup into the Rangemaster's 5 nF, near 1.2 kHz)."""
    total = abs(source + load)
    db = 20 * math.log10(abs(load) / total) if total > 0 and abs(load) > 0 else 0.0
    db = round(db, 2) + 0.0  # no "-0.0"
    text = signed_db(db) if round(db, 1) != 0 else "0.0 dB"
    return {"level_db": db, "level_text": text}


def _resonances(
    sim: Simulator, circuit: Circuit, guitar: Guitar, alone: Circuit, net: str
) -> dict[str, Any] | None:
    """A pickup's resonant peak straight into the amp (`alone`: the pedal left out) and
    into the pedal; None for a buffered guitar (a stiff source has none)."""
    if guitar.source != "pickup":
        return None
    bypassed = sim.ac(alone)
    loaded = sim.ac(circuit)
    return {
        "alone": _resonance(bypassed.freq, bypassed.responses["in"]),
        "loaded": _resonance(loaded.freq, loaded.responses[net]),
    }


def _resonance(freq: npt.NDArray[np.float64], h: npt.NDArray[np.complex128]) -> dict[str, Any]:
    """Where a pickup's response peaks in `RESONANCE_BAND`, and how far over its level at
    `RESONANCE_BASE_HZ`; with no peak (a heavy load), where it is 3 dB down instead."""
    band = (freq >= RESONANCE_BAND[0]) & (freq <= RESONANCE_BAND[1])
    f, top = peak(freq[band], h[band])
    rise = top - gain_at(freq, h, RESONANCE_BASE_HZ)
    if rise >= RESONANCE_MIN_DB:
        text = f"{format_quantity(f, 'Hz')}, +{rise:.1f} dB"
        return {"hz": f, "db": round(rise, 2), "text": text}
    corner = corner_3db(freq, h, "high")
    return {"hz": None, "db": 0.0, "corner": corner,
            "text": f"no peak, 3 dB down at {format_quantity(corner, 'Hz')}"}  # fmt: skip


def _output_knobs(circuit: Circuit, nets: Nets, out: str) -> list[str]:
    """The pots that set the output impedance: on the output net, or one resistor or
    capacitor away from it (a Volume pot behind its output cap), as "VR3 (Level)"."""
    near = {out}
    for ref, pin in nets.members[out]:
        part = circuit.part(ref)
        if isinstance(part, Resistor | Capacitor) and pin in ("1", "2"):
            near.add(nets.net_of(ref, "2" if pin == "1" else "1"))
    found: dict[str, str] = {}
    for part in circuit.parts:
        if isinstance(part, Pot) and any(
            nets.by_pin.get((part.ref, pin)) in near for pin in ("1", "2", "3")
        ):
            found[part.knob] = f"{part.knob} ({part.label})" if part.label else part.knob
    return list(found.values())


@dataclass(frozen=True)
class _Ctx:
    sim: Simulator
    circuit: Circuit
    nets: Nets
    op: OpResult
    level: str

    def v(self, part: Part, pin: str) -> float:
        return self.op.voltages[self.nets.net_of(part.ref, pin)]

    def net(self, part: Part, pin: str) -> str:
        return self.nets.net_of(part.ref, pin)

    @property
    def driven(self) -> bool:
        return input_part(self.circuit) is not None

    def tran(self, nets: Sequence[str]) -> TranResult | None:
        return (
            self.sim.tran(self.circuit, list(dict.fromkeys(nets)), self.level)
            if self.driven
            else None
        )

    def rails(self) -> list[float]:
        return sorted({0.0, *supply_volts(self.circuit).values()})


def _resistor(c: _Ctx, p: Resistor) -> dict[str, Any]:
    across = c.v(p, "1") - c.v(p, "2")
    current = across / parse_value(p.value)
    power = across * current
    return {
        "across": across,
        "current": current,
        "power": power,
        "rating_w": p.rating_w,
        "load": power / p.rating_w if p.rating_w else None,
        "display": {"current": format_quantity(current, "A"), "power": format_quantity(power, "W")},
    }


def _capacitor(c: _Ctx, p: Capacitor) -> dict[str, Any]:
    across = c.v(p, "1") - c.v(p, "2")
    sides = [n for n in (c.net(p, "1"), c.net(p, "2")) if n != "GND"]
    curves = ac_data(c.sim.ac(c.circuit), sides) if c.driven else None
    return {
        "across": across,
        "rating_v": p.rating_v,
        "load": abs(across) / p.rating_v if p.rating_v else None,
        "polarised": p.kind in POLARISED,
        "curves": curves,
    }


def _inductor(c: _Ctx, p: Inductor) -> dict[str, Any]:
    """Its DC current from the volts across its wire's resistance (None for an ideal coil,
    which has none across it), and its sides' curves, as a capacitor's (D-173)."""
    across = c.v(p, "1") - c.v(p, "2")
    current = across / p.resistance if p.resistance > 0 else None
    sides = [n for n in (c.net(p, "1"), c.net(p, "2")) if n != "GND"]
    return {
        "across": across,
        "current": current,
        "curves": ac_data(c.sim.ac(c.circuit), sides) if c.driven else None,
        "display": {"current": format_quantity(current, "A") if current is not None else None},
    }


def _pot(c: _Ctx, p: Pot | Trimmer) -> dict[str, Any]:
    rotation = c.op.bias.get(p.ref, p.rotation)
    low, high = pot_resistances(parse_value(p.value), rotation, p.taper)
    view: dict[str, Any] = {
        "rotation": rotation,
        "taper": p.taper,
        "halves": [low, high],
        "display": {"halves": [format_quantity(low, "Ω"), format_quantity(high, "Ω")]},
        "solved": isinstance(p, Trimmer) and p.bias_target is not None,
    }
    return view


def ac_sweep(sim: Simulator, circuits: Sequence[Circuit], nets: Sequence[str]) -> dict[str, Any]:
    """The frequency response at `nets` for each circuit: `nodes[net][i]` is circuit i's."""
    runs = [sim.ac(c) for c in circuits]
    return {
        **freq_axis(runs[0].freq),
        "valid": [run.valid for run in runs],
        "nodes": {net: [_db(run.responses[net]) for run in runs] for net in nets},
    }


class SweepError(ValueError):
    """A "try several values" request that can't run (plain-English message)."""


def _rail_swept(circuit: Circuit, rail: str, values: Sequence[str]) -> list[Circuit]:
    """One circuit per supply voltage for `rail`. A plain number keeps the rail's sign, so
    "9, 12, 18" on V- means -9, -12, -18 V."""
    power = circuit.power
    if rail not in power.rails:
        raise SweepError(f"There's no supply rail called {rail!r} in this circuit.")
    sign = -1.0 if power.rails[rail] < 0 else 1.0
    circuits = []
    for v in values:
        try:
            volts = parse_value(v)
        except ValueError:
            raise SweepError(f"{rail}: can't use {v!r}. Write a voltage like 9 or 12.") from None
        if volts == 0:
            raise SweepError(f"{rail}: 0 V isn't a supply.")
        volts = volts if v.strip().startswith(("-", "\u2212")) else sign * abs(volts)
        rails = {**power.rails, rail: volts}
        circuits.append(
            circuit.model_copy(update={"power": power.model_copy(update={"rails": rails})})
        )
    return circuits


def _swept(circuit: Circuit, ref: str, field: str, values: Sequence[str]) -> list[Circuit]:
    if field not in SWEEP_FIELDS:
        raise SweepError(f"Only a part's value or model can be swept, not {field!r}.")
    if not values:
        raise SweepError("List at least one value to try, separated by commas.")
    if len(values) > SWEEP_MAX:
        raise SweepError(f"Try at most {SWEEP_MAX} values at once (got {len(values)}).")
    if field == "rail":
        return _rail_swept(circuit, ref, values)
    try:
        part = circuit.part(ref)
    except KeyError:
        raise SweepError(f"There's no part {ref} in this circuit.") from None
    if not hasattr(part, field):
        raise SweepError(f"{ref} has no {field} to try other values of.")
    circuits = []
    for v in values:
        try:
            circuits.append(circuit.with_part(ref, **{field: v}))
        except ValidationError as err:
            why = err.errors()[0]["msg"].removeprefix("Value error, ")
            raise SweepError(f"{ref}: can't use {v!r}. {why}") from None
    return circuits


def sweep_view(
    sim: Simulator,
    circuit: Circuit,
    ref: str,
    field: str,
    values: Sequence[str],
    nodes: Sequence[str],
    level: str,
) -> dict[str, Any]:
    """ "Try several values": one run per value of a part's `value` or `model`, with DC,
    the frequency response and the scope at `nodes` and the output, ready to overlay, and
    the part's own view at each value (`parts`)."""
    circuits = _swept(circuit, ref, field, values)
    nets = connect(circuit)
    out = probe_nets(circuit, nets).output
    wanted = list(dict.fromkeys([*(nets.resolve(n) for n in nodes), *([out] if out else [])]))
    ops = [sim.op(c) for c in circuits]
    result: dict[str, Any] = {
        "ref": ref,
        "field": field,
        "values": list(values),
        "nodes": wanted,
        "dc": {net: [op.voltages[net] for op in ops] for net in wanted},
        # every net's DC per run, so the panel can say which bias points moved most
        "dc_all": {
            net: [op.voltages[net] for op in ops]
            for net in nets.members
            if all(net in op.voltages for op in ops)
        },
        "ac": None,
        "tran": None,
        # the part's own readings at each value, for the Probe pane's columns (D-318);
        # none for a supply rail, which is no part
        "parts": [] if field == "rail" else [part_view(sim, c, ref, level) for c in circuits],
    }
    if input_part(circuit) is not None:
        result["ac"] = ac_sweep(sim, circuits, wanted)
        trans = [sim.tran(c, wanted, level) for c in circuits]
        windows = {net: [scope_window(t, net) for t in trans] for net in wanted}
        n = len(windows[wanted[0]][0])
        result["tran"] = {
            "time_ms": _time_ms(trans[0], n),
            "nodes": {net: [floats(w) for w in ws] for net, ws in windows.items()},
        }
    return result


def _amps(*named: tuple[str, float | None]) -> dict[str, str | None]:
    return {k: None if v is None else format_quantity(v, "A") for k, v in named}


def _diode(c: _Ctx, p: Diode | Led) -> dict[str, Any]:
    lo, hi = DIODE_RANGE[p.type]
    jig = (
        CircuitBuilder(f"{p.ref} I-V")
        .part("V3", "vsource", "a", "0", value=0)
        .part("D1", p.type, "a", "0", model=p.model)
        .build()
    )
    sweep = c.sim.sweep(jig, Dc("V3", lo, hi, (hi - lo) / CURVE_POINTS))
    volts, amps = sweep.sweep, sweep.currents["V3"]
    across = c.v(p, "A") - c.v(p, "K")
    current = float(np.interp(across, volts, amps))
    view: dict[str, Any] = {
        "curve": {"v": floats(volts), "i": floats(amps)},
        "dc": {"v": across, "i": current},
        "display": _amps(("i", current)),
        "swing": None,
    }
    tran = c.tran([c.net(p, "A"), c.net(p, "K")])
    if tran is not None:
        wave = scope_window(tran, c.net(p, "A")) - scope_window(tran, c.net(p, "K"))
        view["swing"] = {"v": floats(wave), "i": floats(np.interp(wave, volts, amps))}
    return view


def _stage(
    c: _Ctx, p: Jfet | Bjt | Mosfet, out_pin: str, common_pin: str, sat: float, polarity: str
) -> dict[str, Any]:
    """Room to swing up and down before a rail or saturation, at the terminal the signal
    leaves from: the drain/collector, or the source/emitter when the drain/collector sits
    on a supply net (a follower; `rail_nets`). Coarse on purpose, like D-041."""
    follower = c.net(p, out_pin) in rail_nets(c.circuit, c.nets)
    up, down = device_room(c.v(p, out_pin), c.v(p, common_pin), sat, polarity, follower, c.rails())
    terminal = common_pin if follower else out_pin
    return {
        "terminal": terminal,
        "follower": follower,
        "headroom": {"up": up, "down": down},
        "swing": _swing(c, c.net(p, terminal)),
    }


def _swing(c: _Ctx, net: str) -> dict[str, float] | None:
    tran = c.tran([net])
    if tran is None:
        return None
    stats = tran.stats[net]
    return {"up": stats.peak_pos, "down": -stats.peak_neg}


def _transfer(
    c: _Ctx, p: Jfet | Bjt | Mosfet, fixed: float, span: tuple[float, float]
) -> dict[str, list[float]]:
    """Drain/collector current vs gate/base voltage, both relative to the source/emitter,
    with the drain/collector held at `fixed` volts."""
    extra = {"measured": p.measured.model_dump()} if isinstance(p, Jfet) and p.measured else {}
    jig = (
        CircuitBuilder(f"{p.ref} transfer")
        .part("V1", "vsource", "o", "0", value=fixed)
        .part("V2", "vsource", "i", "0", value=0)
        .part("Q1", p.type, "o", "i", "0", model=p.model, **extra)  # D G S / C B E
        .build()
    )
    lo, hi = sorted(span)
    sweep = c.sim.sweep(jig, Dc("V2", lo, hi, (hi - lo) / CURVE_POINTS))
    return {"v": floats(sweep.sweep), "i": floats(sweep.currents["V1"])}


def _jfet_point(c: _Ctx, p: Jfet) -> tuple[str, float, float, float, float]:
    """A JFET's polarity, pinch-off Vp (measured if given), Vgs, Vds, and the Vds below
    which it leaves saturation (its room to the source)."""
    model = c.sim.models.get(p.model)
    polarity = model.polarity or "n"
    sign = 1.0 if polarity == "n" else -1.0
    vp = p.measured.vp if p.measured else model.param("vto")
    vp = vp if vp is not None else -sign * 5.0
    vgs, vds = c.v(p, "G") - c.v(p, "S"), c.v(p, "D") - c.v(p, "S")
    return polarity, vp, vgs, vds, max(sign * (vgs - vp), 0.0)


def _jfet(c: _Ctx, p: Jfet) -> dict[str, Any]:
    polarity, vp, vgs, vds, vdsat = _jfet_point(c, p)
    drain = c.op.currents.get(f"{p.ref}.id")
    return {
        "polarity": polarity,
        "vgs": vgs,
        "vds": vds,
        "vp": vp,
        "id": drain,
        "display": _amps(("id", drain)),
        "curve": _transfer(c, p, vds, (1.1 * vp, 0.0)),
        "stage": _stage(c, p, "D", "S", vdsat, polarity),
    }


def _vto(c: _Ctx, p: Mosfet) -> float:
    return c.sim.models.get(p.model).param("vto") or 0.0


def _mosfet(c: _Ctx, p: Mosfet) -> dict[str, Any]:
    """An N-channel MOSFET (D-175): its room down to `mosfet_vds_sat`, its threshold the
    card's VTO; the transfer curve from 0 V (a depletion part's, D-178: from half a volt
    below VTO) to 2 V past its gate (or VTO)."""
    vto = _vto(c, p)
    depletion = c.sim.models.get(p.model).depletion
    vgs, vds = c.v(p, "G") - c.v(p, "S"), c.v(p, "D") - c.v(p, "S")
    drain = c.op.currents.get(f"{p.ref}.id")
    low = min(vto, vgs) - MOSFET_VGS_BELOW if depletion else 0.0
    return {
        "polarity": "n",
        "depletion": depletion,
        "vgs": vgs,
        "vds": vds,
        "vto": vto,
        "id": drain,
        "display": _amps(("id", drain)),
        "curve": _transfer(c, p, vds, (low, max(vgs, vto) + MOSFET_VGS_ABOVE)),
        "stage": _stage(c, p, "D", "S", mosfet_vds_sat(vgs, vto), "n"),
    }


def _bjt(c: _Ctx, p: Bjt) -> dict[str, Any]:
    polarity = c.sim.models.get(p.model).polarity or "n"
    sign = 1.0 if polarity == "n" else -1.0
    vbe, vce = c.v(p, "B") - c.v(p, "E"), c.v(p, "C") - c.v(p, "E")
    ic, ib = c.op.currents.get(f"{p.ref}.ic"), c.op.currents.get(f"{p.ref}.ib")
    magnitude = abs(vbe)
    span = (sign * max(magnitude - BJT_VBE_BELOW, 0.0), sign * (magnitude + BJT_VBE_ABOVE))
    return {
        "polarity": polarity,
        "vbe": vbe,
        "vce": vce,
        "ic": ic,
        "ib": ib,
        "beta": ic / ib if ic is not None and ib else None,
        "display": _amps(("ic", ic), ("ib", ib)),
        "curve": _transfer(c, p, vce, span),
        "stage": _stage(c, p, "C", "E", BJT_VCE_SAT, polarity),
    }


def _opamp(c: _Ctx, p: Opamp) -> dict[str, Any]:
    if unused(c.circuit, c.nets, p):
        return {"unused": True, "chip": p.chip}  # not simulated: no DC to show (D-140)
    out = c.v(p, "out")
    pos, neg = supply_nets(c.circuit, c.nets, p)
    high, low = c.op.voltages[pos], c.op.voltages[neg]
    inputs = {"+": c.v(p, "+"), "-": c.v(p, "-")}
    # the model's datasheet common-mode range, else a rule of thumb (D-048, D-077)
    limits = opamp_input_limits(c.sim.models.get(p.model), high, low)
    datasheet = limits is not None
    lo, hi = limits or (low + OPAMP_RAIL_MARGIN, high - OPAMP_RAIL_MARGIN)
    return {
        "out": out,
        "rails": [low, high],
        "to_rails": {"up": high - out, "down": out - low},
        "inputs": inputs,
        "input_limits": [lo, hi],
        "input_outside": any(not lo <= v <= hi for v in inputs.values()),
        "limits_from": "datasheet" if datasheet else "rule of thumb",
        "swing": _swing(c, c.net(p, "out")),
    }


def _switch(c: _Ctx, p: Switch) -> dict[str, Any]:
    return {"position": p.position, "positions": list(p.switch_kind.positions)}


_VIEWS: dict[type, Callable[[_Ctx, Any], dict[str, Any]]] = {
    Resistor: _resistor,
    Capacitor: _capacitor,
    Inductor: _inductor,
    Pot: _pot,
    Trimmer: _pot,
    Diode: _diode,
    Led: _diode,
    Jfet: _jfet,
    Bjt: _bjt,
    Mosfet: _mosfet,
    Opamp: _opamp,
    Switch: _switch,
}


def part_view(
    sim: Simulator,
    circuit: Circuit,
    ref: str,
    level: str,
    pickups: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The view for one part (SPEC §2): its pins' DC plus what matters for its type
    (`pickups`: the guide's kind → name, for a guitar's text). KeyError if there's no
    such part."""
    part = circuit.part(ref)
    nets = connect(circuit)
    ctx = _Ctx(sim, circuit, nets, sim.op(circuit), level)
    pins = {
        pin: {"net": net, "dc": ctx.op.voltages.get(net)}
        for pin, (_pos, net) in drawn_pins(circuit, nets, part, sim.models).items()
        # a pump's pin 6 or 7 left open has no voltage to show (v28)
        if not (isinstance(part, ChargePump) and pin in SPARE_PINS and net not in ctx.op.voltages)
    }
    view = _VIEWS.get(type(part))
    loose = ref in loose_parts(circuit, nets)
    return {
        "ref": ref,
        "type": part.type,
        "text": part_text(part, pickups),
        "note": part.note or None,
        "pins": pins,
        # a loose part isn't simulated (D-165): its pins have no DC, it has no detail, and
        # the pane says so in place of readings (`loose`, D-318)
        "loose": loose,
        "detail": view(ctx, part) if view and not loose else {},
    }


# ---- Bias & headroom (Phase 8c, D-106) ----------------------------------------------


def _room(c: _Ctx, stage: Stage) -> tuple[float, float, float, str]:
    """A stage's output DC and its room (up, down) to swing, and where its limits come
    from: a transistor's from its saturation and the rails, an op-amp's from its output
    swing (`opamp_output_limits`)."""
    p = c.circuit.part(stage.refs[0])
    if isinstance(p, Opamp):
        out = c.v(p, "out")
        pos, neg = supply_nets(c.circuit, c.nets, p)
        high, low = c.op.voltages[pos], c.op.voltages[neg]
        lo, hi, datasheet = opamp_output_limits(c.sim.models.get(p.model), high, low)
        return out, hi - out, out - lo, "datasheet" if datasheet else "rule of thumb"
    if isinstance(p, Jfet):
        polarity, *_, sat = _jfet_point(c, p)
        pins = ("D", "S")
    elif isinstance(p, Mosfet):
        polarity, pins = "n", ("D", "S")
        sat = mosfet_vds_sat(c.v(p, "G") - c.v(p, "S"), _vto(c, p))
    else:
        assert isinstance(p, Bjt)
        polarity, sat, pins = c.sim.models.get(p.model).polarity or "n", BJT_VCE_SAT, ("C", "E")
    follower = stage.role == "buffer"
    up, down = device_room(c.v(p, pins[0]), c.v(p, pins[1]), sat, polarity, follower, c.rails())
    return c.op.voltages[stage.net], _or_inf(up), _or_inf(down), "device"


def _or_inf(x: float | None) -> float:
    return math.inf if x is None else x


def _finite(x: float) -> float | None:
    return x if math.isfinite(x) else None


def _peak(stats: NodeStats) -> float:
    return max(stats.peak_pos, -stats.peak_neg)


@dataclass(frozen=True)
class _Path:
    """The signal path the Bias & headroom pane measures: the guitar's net, the stages and
    clippers on it in signal order, each net's small-signal gain at the scope's tone, and
    the nets a transient must save."""

    source: str
    found: list[Stage]
    gain: dict[str, float]
    ac: AcResult
    tone: float
    inputs: list[str | None]  # where the signal enters each row (`signal_entry`)

    def feed(self, i: int) -> str:
        """The net row `i` is fed from: the row before (or the guitar)."""
        stage = self.found[i]
        return next((r.net for r in reversed(self.found[:i]) if r.net != stage.net), self.source)

    @property
    def wanted(self) -> list[str]:
        clippers = [s.other for s in self.found if s.kind == "clipper"]
        return [self.source, *(s.net for s in self.found), *clippers]

    def predicted(self, i: int, tran: TranResult) -> float:
        """What row `i` would reach unclipped: what reaches it from the row before (or the
        guitar) times the small-signal gain between them, so a stage after a clipper is
        judged on the clipped signal it gets."""
        before = self.feed(i)
        ratio = self.gain[self.found[i].net] / max(self.gain[before], 1e-12)
        return _peak(tran.stats[before]) * ratio

    def own_gain_db(self, i: int) -> dict[str, float]:
        """Row `i`'s own small-signal gain, from where the signal enters it (or, with no
        such pin, what feeds it) to its net, at each of `TONES` (dB, keyed by the tone
        as text). With an arrow's loss before it, the two add up to the row before's
        net to this one's (D-123)."""
        return _gain_db(self.ac, self.inputs[i] or self.feed(i), self.found[i].net)

    def arrow_db(self, k: int, out: str | None) -> dict[str, float] | None:
        """What the passive parts on arrow `k` (into row `k`, or into the amp at `out`
        after the last) do to the signal at each tone, in dB: from the row before's net
        (or the guitar) to where the signal enters the next. None where that isn't a
        separate net (a clipper on a stage's own nets, an inverting op-amp stage)."""
        start = self.source if k == 0 else self.found[k - 1].net
        end = self.inputs[k] if k < len(self.found) else out
        if end is None or end == start:
            return None
        return _gain_db(self.ac, start, end)


def _gain_db(ac: AcResult, start: str, end: str) -> dict[str, float]:
    """The small-signal gain from net `start` to net `end` at each of `TONES`, in dB."""
    return {
        f"{t:g}": 20
        * math.log10(max(_tone_gain(ac, end, t), 1e-12) / max(_tone_gain(ac, start, t), 1e-12))
        for t in TONES
    }


def signal_entry(ac: AcResult, circuit: Circuit, nets: Nets, stage: Stage, feed: str) -> str | None:
    """Where the signal enters a row (`signal_input`), if it does: an op-amp's + input
    that only holds its bias (an inverting stage) carries next to none of the signal
    fed to it, so it has none."""
    net = signal_input(circuit, nets, stage)
    if net is None or net not in ac.responses:
        return None
    return net if _tone_gain(ac, net) > SIGNAL_FLOOR * _tone_gain(ac, feed) else None


def _signal_path(sim: Simulator, circuit: Circuit, tone: float = TONE_HZ) -> _Path | str:
    """The pane's signal path at `tone`, or a note saying why there is none."""
    guitar = input_part(circuit)
    if guitar is None:
        return "Add a guitar input to see the stages."
    nets = connect(circuit)
    ac = sim.ac(circuit)
    source = nets.net_of(guitar.ref, "out")
    every = signal_stages(circuit, nets)
    gain = {
        net: _tone_gain(ac, net, tone)
        for net in {source, *(s.net for s in every)}
        if net in ac.responses
    }
    # a stage the tone barely reaches isn't on the signal path (a VREF buffer)
    found = [s for s in every if gain.get(s.net, 0.0) > SIGNAL_FLOOR * gain[source]]
    if not found:
        return "No transistor, op-amp or clipper on the signal path."
    feeds = [
        next((r.net for r in reversed(found[:i]) if r.net != s.net), source)
        for i, s in enumerate(found)
    ]
    inputs = [signal_entry(ac, circuit, nets, s, f) for s, f in zip(found, feeds, strict=True)]
    return _Path(source, found, gain, ac, tone, inputs)


def _tone_gain(ac: AcResult, net: str, tone: float = TONE_HZ) -> float:
    """The small-signal gain from the guitar to `net` at `tone` (the scope's, unless said)."""
    return float(np.interp(np.log10(tone), np.log10(ac.freq), np.abs(ac.responses[net])))


def _settled(trans: Sequence[TranResult]) -> bool | None:
    """Whether every run settled: False if any is still drifting, None if any wasn't
    checked (a circuit with its own oscillator, D-122)."""
    found = [t.settled for t in trans]
    return False if False in found else None if None in found else True


def stages_view(
    sim: Simulator, circuit: Circuit, tone: float = TONE_HZ, progress: Progress = _quiet
) -> dict[str, Any]:
    """The Bias & headroom pane (Phase 8c, D-106): every stage and clipper on the signal
    path in signal order, each stage's bias between its limits, and at each pick level
    how close each is to clipping (`_Path.predicted`), with a sine of `tone` Hz (one of
    `TONES`, D-122). `picks`: each level's peak at the guitar, in volts (the level
    diagram starts there); `settled`: whether the runs settled (`_settled`); each row's
    `gain_db`: its own small-signal gain at every tone, and `parts`: what a click lights;
    `pots`: each knob's chip, where it acts (`pot_places`), its name and rotation;
    `arrows`: each arrow's loss at every tone (`_Path.arrow_db`, D-123), guitar first.
    `progress`: the small-signal pass, then each pick's transient (D-127)."""
    steps = 1 + len(LEVELS)
    progress(0, steps)
    path = _signal_path(sim, circuit, tone)
    if isinstance(path, str):
        return {"rows": [], "summary": "", "note": path, "picks": LEVELS, "tone": tone,
                "settled": True, "pots": [], "arrows": []}  # fmt: skip
    nets = connect(circuit)
    c = _Ctx(sim, circuit, nets, sim.op(circuit), "med")
    trans = {}
    for i, lv in enumerate(LEVELS, start=1):
        progress(i, steps)
        trans[lv] = sim.tran(circuit, path.wanted, lv, tone)
    progress(steps, steps)
    held = {s.net for s in path.found if s.kind == "clipper" and s.role == "in feedback"}
    saturated = {s.ref: s.message for s in path.ac.saturated}
    rows, clips = [], []
    for i, stage in enumerate(path.found):
        predicted = {lv: path.predicted(i, t) for lv, t in trans.items()}
        stats = {lv: t.stats[stage.net] for lv, t in trans.items()}
        if stage.kind == "stage":
            row, at = _stage_row(c, stage, stats, predicted, stage.net in held)
        else:
            row, at = _clipper_row(stage, stats, predicted, trans["hard"])
        state = next((saturated[r] for r in stage.refs if r in saturated), None)
        rows.append({
            "kind": stage.kind, "refs": list(stage.refs), "label": stage.label,
            "role": stage.role, "net": stage.net, "state": state,
            "gain_db": path.own_gain_db(i), "parts": stage_parts(circuit, nets, stage.refs),
            **row,
        })  # fmt: skip
        what = "clipper" if stage.kind == "clipper" else stage.role
        clips.append(Clips(stage.label, what, frozenset(at)))
    summary = (
        "A stage is saturated at DC (marked below), so these readings mean little: fix its "
        "bias first."
        if path.ac.saturated
        else first_to_clip(clips, list(LEVELS))
    )
    knobs = {k["ref"]: k for k in controls(circuit) if k["kind"] == "pot"}
    pots = [
        {"ref": p.ref, "name": knobs[p.ref]["label"], "at": p.at, "index": p.index,
         "rotation": knobs[p.ref]["rotation"]}
        for p in pot_places(circuit, nets, path.found)
    ]  # fmt: skip
    out = probe_nets(circuit, nets).output
    arrows = [path.arrow_db(k, out) for k in range(len(path.found) + 1)]
    return {"rows": rows, "summary": summary, "note": None, "picks": LEVELS, "tone": tone,
            "settled": _settled(list(trans.values())), "pots": pots, "arrows": arrows}  # fmt: skip


def stage_levels(
    sim: Simulator, circuit: Circuit, amplitude: float, tone: float = TONE_HZ
) -> dict[str, Any]:
    """Every row of `stages_view` with the guitar at `amplitude` volts peak and `tone`
    Hz: the peak it reaches and what it would reach unclipped. The pane's level in ->
    out curve is a dozen of these (each transient is cached, so a second sweep is
    instant)."""
    path = _signal_path(sim, circuit, tone)
    if isinstance(path, str):
        return {"amplitude": amplitude, "tone": tone, "rows": []}
    tran = sim.tran(circuit, path.wanted, amplitude, tone)
    rows = [
        {"net": s.net, "peak": _peak(tran.stats[s.net]), "predicted": path.predicted(i, tran)}
        for i, s in enumerate(path.found)
    ]
    return {"amplitude": amplitude, "tone": tone, "rows": rows, "settled": tran.settled}


def stage_waves(
    sim: Simulator, circuit: Circuit, net: str, tone: float = TONE_HZ
) -> dict[str, Any]:
    """The waveform at a row's `net` at each pick level: the last `SCOPE_CYCLES` cycles
    of the pane's own transients (cached, so nothing runs again once the pane has
    measured the tone), for a block card's Waveform section (D-127). `waves` is empty
    when `net` isn't on the signal path."""
    path = _signal_path(sim, circuit, tone)
    if isinstance(path, str) or net not in path.wanted:
        return {"net": net, "tone": tone, "time_ms": [], "waves": {}}
    trans = {lv: sim.tran(circuit, path.wanted, lv, tone) for lv in LEVELS}
    waves = {lv: scope_window(t, net) for lv, t in trans.items()}
    n = len(next(iter(waves.values())))
    return {"net": net, "tone": tone, "time_ms": _time_ms(trans["med"], n),
            "waves": {lv: floats(w) for lv, w in waves.items()}}  # fmt: skip


def _cell(stats: NodeStats, predicted: float) -> dict[str, Any]:
    """What every row shows at a pick level: the unclipped level, the peaks it reached
    (up, down) and how distorted it is there."""
    return {
        "predicted": predicted,
        "up": stats.peak_pos,
        "down": -stats.peak_neg,
        "thd": stats.clipping.thd,
        "clipping": stats.clipping.label,
        "title": _cell_title(stats, predicted),
    }


def _cell_title(stats: NodeStats, predicted: float) -> str:
    """A cell's tooltip: what it would reach unclipped, what it reached, its THD."""
    up, down = format_quantity(stats.peak_pos, "V"), format_quantity(-stats.peak_neg, "V")
    return (
        f"Would reach {format_quantity(predicted, 'V')} unclipped; reached +{up} / \u2212{down}. "
        f"THD {stats.clipping.thd * 100:.0f} % ({stats.clipping.label})."
    )


def _stage_row(
    c: _Ctx,
    stage: Stage,
    stats: dict[str, NodeStats],
    predicted: dict[str, float],
    held: bool,
) -> tuple[dict[str, Any], set[str]]:
    """A stage's bias and, per level, its headroom (the clipped level when a clipper in
    its feedback holds its output: the diodes stop it short of its limits)."""
    dc, up, down, limits = _room(c, stage)
    position, place = bias_position(up, down)
    levels, at = {}, set()
    for lv, st in stats.items():
        room = headroom_db(up, down, _peak(st) if held else predicted[lv])
        clips = stage_clips(room, held)
        levels[lv] = {**_cell(st, predicted[lv]), "headroom_db": room, "held": held, "clips": clips}
        if clips:
            at.add(lv)
    bias = {
        "v": dc,
        "up": _finite(up),
        "down": _finite(down),
        "position": position,
        "place": place,
        "limits": limits,
        "text": _bias_text(dc, up, down, place, limits),
    }
    limit = _finite(min(up, down))  # the peak it can swing to before it clips
    return {"bias": bias, "levels": levels, "limit": limit}, at


def _clipper_row(
    stage: Stage, stats: dict[str, NodeStats], predicted: dict[str, float], hard: TranResult
) -> tuple[dict[str, Any], set[str]]:
    """A clipper's drive per level (at its node: what it lets through against what would
    get there without it), and where it clamps: the peaks across it at a hard pick."""
    levels, at = {}, set()
    for lv, st in stats.items():
        drive = drive_db(predicted[lv], _peak(st))
        levels[lv] = {
            **_cell(st, predicted[lv]),
            "drive_db": drive,
            "asymmetry": st.clipping.asymmetry,
            "harmonics": harmonic_lead(st.harmonics_db),
            "clips": clipper_clips(drive),
        }
        if levels[lv]["clips"]:
            at.add(lv)
    up, down = clamp_across(hard, stage)
    clamp = {"up": up, "down": down, "text": _clamp_text(up, down), "short": clamp_short(up, down),
             "even": _even(up, down)}  # fmt: skip
    # to ground, the clamp is the node's own limit; in feedback or series it's across the
    # diodes only, not where the node stops
    limit = max(up, down) if stage.role == "to ground" else None
    return {"levels": levels, "clamp": clamp, "limit": limit}, at


def clamp_across(tran: TranResult, stage: Stage) -> tuple[float, float]:
    """Where a clipper holds the signal across itself in a run (up, down): the voltage
    across its diodes, which is what they conduct on (not about its mean, which a
    lopsided pair pulls to one side, D-123)."""
    across = scope_window(tran, stage.net) - scope_window(tran, stage.other)
    return float(across.max()), float(-across.min())


def _volts(x: float) -> str:
    return format_quantity(x, "V") if math.isfinite(x) else "no limit"


def _bias_text(dc: float, up: float, down: float, place: str, limits: str) -> str:
    """ "Sits high at 7.1 V: 1.9 V of room up, 6.8 V down, so it clips at the top first." """
    first = "at the top" if up < down else "at the bottom"
    side = "" if place == "centred" else f", so it clips {first} first"
    source = " (op-amp swing: a rule of thumb)" if limits == "rule of thumb" else ""
    room = f"{_volts(up)} of room up, {_volts(down)} down"
    return f"{place.capitalize()} at {_volts(dc)}: {room}{side}{source}."


def _even(up: float, down: float) -> bool:
    """A clamp the same both ways, within 10 % (an uneven pair clips lopsided)."""
    return abs(up - down) <= 0.1 * max(up, down)


def clamp_short(up: float, down: float) -> str:
    """Where a clipper holds the signal across it at a hard pick: "±450 mV", or each way
    ("+645 mV / -411 mV") when they differ by more than 10 % (`_even`)."""
    if _even(up, down):
        return f"±{format_quantity((up + down) / 2, 'V')}"
    return f"+{format_quantity(up, 'V')} / \u2212{format_quantity(down, 'V')}"


def _clamp_text(up: float, down: float) -> str:
    """ "Clamps at ±450 mV across it (hard pick)." """
    return f"Clamps at {clamp_short(up, down)} across it (hard pick)."
