"""Live curves in the editor (D-012, D-079, D-081): while a value slider or a knob moves,
the browser re-solves the circuit's linear system (`web/solver.js`) at every step, and
ngspice re-runs once the slider is let go.

`live_view` linearises the circuit as drawn (`Simulator.linearise`) and gives each
requested control a slider whose steps carry the SPICE element values they set, worked out
here by the netlist generator, so the browser never parses a value or applies a pot taper.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import numpy as np

from solum.circuit.connectivity import connect
from solum.circuit.schema import (
    AmpInput,
    Capacitor,
    Circuit,
    Guitar,
    Inductor,
    Part,
    Pot,
    Resistor,
    Trimmer,
    turns,
)
from solum.linear import GROUND, ac_magnitude, branches, element_values, system_data
from solum.models import ModelLibrary
from solum.netlist import Ac, Element, input_part, part_elements
from solum.probe import floats
from solum.sim.engine import SimError
from solum.simulate import Simulator
from solum.units import format_value, parse_value, series_values, snap_to_series

SERIES = "E12"  # value sliders step through it; a typed value shows its nearest member
POT_SERIES = "pot"  # pots and trimmers: the values they're sold in
VALUE_SPAN = 10.0  # a value slider runs from value / span to value x span
# a capacitor's slider runs over what pedals use, whatever its value (the user, D-164):
# 10p (an op-amp's compensation) to 470µ (a supply filter), in E12
CAP_RANGE = (10e-12, 470e-6)
# a resistor's too, and a pot's or trimmer's (the user, D-316): 10 Ω (a supply's series
# resistor) to 10 MΩ (an input's bias) in E12; pots over the values they're sold in
RESISTOR_RANGE = (10.0, 10e6)
POT_RANGE = (1e3, 1e6)
ROTATION_STEPS = 101  # 0 to 100 % in 1 % steps
VALUE_PARTS = (Resistor, Capacitor, Inductor, Pot, Trimmer, AmpInput)  # what has a value slider
NUDGE = 0.1  # part influence nudges each part's value by +10 % (Phase 8b, D-097)
NUDGED_PARTS = (Resistor, Capacitor, Inductor, Pot, Trimmer)  # what part influence nudges
BIAS_VOLTS = 0.01  # a resistor with more DC than this across it also sets a bias

Field = Literal["value", "rotation"]


class LiveError(ValueError):
    """A part or field that has no slider (plain-English message)."""


def value_steps(
    value: float,
    kept: Sequence[Any] | None = None,
    series: str = SERIES,
    span: tuple[float, float] | None = None,
) -> list[float]:
    """A value slider's steps: the ones the page already shows (`kept`, so a slider keeps
    its range while it's used), or the series over `span` (low, high), by default from
    value / VALUE_SPAN to value x VALUE_SPAN; `value` itself is always one."""
    low, high = span or (value / VALUE_SPAN, value * VALUE_SPAN)
    steps = [parse_value(str(v)) for v in kept] if kept else series_values(low, high, series)
    if not any(abs(s / value - 1) < 1e-9 for s in steps):
        steps = sorted([*steps, value])
    return steps


def _span(part: Part) -> tuple[float, float] | None:
    """The fixed range a part's value slider runs over, whatever its value; None: a
    decade each way (an inductor, the amp's input)."""
    if isinstance(part, Capacitor):
        return CAP_RANGE
    if isinstance(part, Resistor):
        return RESISTOR_RANGE
    if isinstance(part, Pot | Trimmer):
        return POT_RANGE
    return None


def _series(part: Part) -> str:
    return POT_SERIES if isinstance(part, Pot | Trimmer) else SERIES


def slider(
    circuit: Circuit,
    models: ModelLibrary,
    ref: str,
    field: Field,
    kept: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """The slider for one part's value or rotation: each step's field value, its text and
    the element values it gives (`part_elements` with the part changed), `si` its value as
    a number (ohms, farads; a rotation 0-1), the step the part is at, and its value's
    nearest series member when it's off the series."""
    try:
        part = circuit.part(ref)
    except KeyError:
        raise LiveError(f"There's no part {ref} in this circuit.") from None
    units = [circuit.part(r) for r in circuit.units(ref)]  # a dual pot's gangs (D-217)
    nearest = None
    if field == "value":
        if not isinstance(part, VALUE_PARTS):
            raise LiveError(f"{ref} has no value to slide.")
        series = _series(part)
        current = parse_value(part.value)
        span = _span(part)
        raw = value_steps(current, kept, series, span)
        values: list[Any] = [format_value(v, 6) for v in raw]
        numbers = raw
        texts = [format_value(v) for v in raw]
        index = min(range(len(raw)), key=lambda i: abs(np.log(raw[i] / current)))
        snapped = snap_to_series(current, series)
        if abs(snapped / current - 1) > 1e-9:
            nearest = format_value(snapped)
    elif field == "rotation":
        if not turns(part):
            raise LiveError(f"{ref} isn't a pot or trimmer.")
        if isinstance(part, Trimmer) and part.bias_target:
            raise LiveError(f"{ref} is set by its bias target, not by hand.")
        series = None
        values = [i / (ROTATION_STEPS - 1) for i in range(ROTATION_STEPS)]
        numbers = values
        texts = [f"{round(r * 100)} %" for r in values]
        index = min(range(len(values)), key=lambda i: abs(values[i] - part.rotation))
    else:
        raise LiveError(f"There's no slider for {field!r}.")
    copies = [u.model_copy(update={field: v}) for v in values for u in units]
    flat = part_elements(circuit, copies, models, Ac())
    n = len(units)
    found = [tuple(e for f in flat[i * n : (i + 1) * n] for e in f) for i in range(len(values))]
    return {
        "ref": ref,
        "field": field,
        "series": series,
        "index": index,
        "nearest": nearest,
        "steps": [
            {"value": v, "si": x, "text": t, "elements": _step_values(part, e)}
            for v, x, t, e in zip(values, numbers, texts, found, strict=True)
        ],
    }


def _step_values(part: Part, elements: Sequence[Element]) -> dict[str, float]:
    """A step's element values; a buffered guitar's volume turns its source's level instead
    (it has no pot elements, D-134)."""
    found = element_values(elements)
    if isinstance(part, Guitar) and part.source == "ideal":
        found |= {
            e.tokens[0]: ac_magnitude(e.tokens[3:]) for e in elements if e.tokens[0][0] == "V"
        }
    return found


def nudges(
    circuit: Circuit, models: ModelLibrary, voltages: Mapping[str, float]
) -> list[dict[str, Any]]:
    """Every resistor, capacitor, inductor, pot and trimmer with its value raised by NUDGE: the
    element values that gives (`part_elements`, so the browser never scales a pot's
    halves itself), and `bias`: it has DC across it (`voltages`, net → volts), so it also
    moves an operating point, which the live solver holds fixed (D-079); `knob`: a pot,
    on the pedal's panel (Edit mode's handles leave knobs to the Knob ranges layer)."""
    nets = connect(circuit)
    parts = [p for p in circuit.parts if isinstance(p, NUDGED_PARTS)]
    copies = [
        p.model_copy(update={"value": format_value(parse_value(p.value) * (1 + NUDGE), 6)})
        for p in parts
    ]
    found = part_elements(circuit, copies, models, Ac(), nets)
    out = []
    for part, elements in zip(parts, found, strict=True):
        dc = [voltages.get(net, 0.0) for (ref, _), net in nets.by_pin.items() if ref == part.ref]
        # a capacitor's or inductor's value never moves the DC operating point
        bias = (
            not isinstance(part, Capacitor | Inductor)
            and bool(dc)
            and max(dc) - min(dc) > BIAS_VOLTS
        )
        out.append({"ref": part.ref, "elements": element_values(elements), "bias": bias,
                    "knob": isinstance(part, Pot)})  # fmt: skip
    return out


def live_view(
    sim: Simulator,
    circuit: Circuit,
    nets: Sequence[str],
    controls: Sequence[tuple[str, Field]],
    kept: Mapping[str, Sequence[Any]] | None = None,
    nudge: bool = False,
    simulate: bool = True,
) -> dict[str, Any]:
    """What the browser needs to re-solve the curves at `nets` while `controls` move: the
    linear system, each net's node index in it (-1: ground), and a slider per control.
    No system without a guitar input (there's no curve to redraw), but the sliders still
    work. `kept`: value sliders' steps the page shows, by "REF.value". `nudge`: also each
    part nudged by NUDGE (`nudges`), for part influence. A circuit that can't be run
    (`simulate` off, or ngspice refusing it: half drawn, say) still gets its sliders,
    with no curve (D-164)."""
    kept = kept or {}
    if not simulate:
        return _view(sim, circuit, controls, kept, None, {}, False, [])
    system = None
    where: dict[str, int] = {}
    valid = True
    nudged: list[dict[str, Any]] = []
    if input_part(circuit) is not None:
        try:
            lin = sim.linearise(circuit)
        except SimError:  # half drawn, say: no curve, but the sliders still work (D-164)
            return _view(sim, circuit, controls, kept, None, {}, False, [])
        circuit, valid = lin.circuit, lin.ac.valid
        found = branches(lin.netlist.elements, lin.ports)
        system = system_data(found, floats(lin.ac.freq), GROUND)  # the run's grid exactly
        index = {n: i for i, n in enumerate(system["nodes"])}
        resolved = connect(circuit)
        for net in nets:
            name = resolved.resolve(net)
            where[name] = index.get(lin.netlist.node(name), -1)
        if nudge:
            nudged = nudges(circuit, sim.models, sim.op(circuit).voltages)
    return _view(sim, circuit, controls, kept, system, where, valid, nudged)


def _view(
    sim: Simulator,
    circuit: Circuit,
    controls: Sequence[tuple[str, Field]],
    kept: Mapping[str, Sequence[Any]],
    system: dict[str, Any] | None,
    where: dict[str, int],
    valid: bool,
    nudged: list[dict[str, Any]],
) -> dict[str, Any]:
    """`live_view`'s answer: what it found, and a slider per control."""
    return {
        "system": system,
        "nets": where,
        "sliders": [
            slider(circuit, sim.models, ref, field, kept.get(f"{ref}.{field}"))
            for ref, field in controls
        ],
        "valid": valid,
        "nudge": NUDGE,
        "nudges": nudged,
    }
