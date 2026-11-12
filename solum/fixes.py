"""The fixes in a block's card (Phase 8c Part 2, D-119, D-123): values to try for a
stage's bias (Centre, Bias to…), its own gain, and a clipper's diodes.

Every option is the same shape, so the pane tries them all the same way: `set` (the
fields to change, per part), `undo` (what puts them back), a `label` for History and a
sentence saying what changes. Each is measured through `Simulator` (cached runs), so
bias targets are solved as in every other run.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from solum.bias import BiasError, bisect
from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, PinRef, connect
from solum.circuit.schema import (
    AmpInput,
    Capacitor,
    Circuit,
    Diode,
    Led,
    Opamp,
    Part,
    Pot,
    Resistor,
    Trimmer,
)
from solum.live import POT_SERIES
from solum.netlist import input_part
from solum.probe import (
    Progress,
    _Ctx,
    _quiet,
    _room,
    _signal_path,
    _tone_gain,
    clamp_across,
    clamp_short,
    scope_window,
    signal_entry,
)
from solum.sim.engine import SimError
from solum.simulate import LEVELS, TONE_HZ, Simulator
from solum.stages import (
    CENTRED,
    LEVEL_NAMES,
    Stage,
    bias_position,
    centring_rank,
    clipper_clips,
    drive_db,
    headroom_db,
    signal_input,
    signal_stages,
    stage_clips,
)
from solum.units import (
    format_quantity,
    format_value,
    parse_value,
    series_values,
    signed_db,
    snap_to_series,
)
from solum.view import rail_nets

# a value is searched from a tenth to ten times its own, kept within these bounds
FIX_SPAN = 10.0
FIX_BOUNDS = {"resistor": (10.0, 10e6), "capacitor": (1e-12, 1e-3)}
SERIES = {"resistor": "E24", "capacitor": "E12"}
SLIDER_SERIES = "E12"  # a resistor's gain slider: half E24's runs (D-127)
FIXES_VERSION = "1"  # bump when a search's answer changes for the same request (D-127)
REACH_MIN = 0.05  # a bias no one part moves more than this (of its room) can't be aimed
TARGET_DECIMALS = 2  # a bias target is stored to 10 mV, as the bias bar shows it
BIAS_TOLERANCE = 0.01  # the search stops within this of the bias position asked for
FIX_OPTIONS = 3  # bias options shown
GAIN_SAME_DB = 0.1  # a gain change smaller than this reads "unchanged"
INTO_SAID_DB = 1.0  # a step names what reaches the next row once it differs this much
NUDGE = 1.1  # the gain parts are ranked by what +10 % does
GAIN_PARTS = 5  # gain parts shown
GAIN_MOVES_DB = 0.05  # a part that moves the gain less than this isn't one
EDGE = 0.05  # a gain slider stops before the stage's bias is this close to a limit (D-125)
# the clipper swaps (D-118's diodes): type, model, what a builder calls it
CLIPPERS = (
    ("diode", "1N4148", "silicon"),
    ("diode", "1N34A", "germanium"),
    ("diode", "BAT46", "Schottky"),
    ("led", "APT1608SURCK", "red LED"),
)


class FixError(ValueError):
    """There's no such stage or clipper to fix (plain-English message)."""


@dataclass(frozen=True)
class _Place:
    """Where a stage's output sits: its DC and room to swing, as the pane reads them."""

    position: float  # 0 at the bottom of its room, 1 at the top (`bias_position`)
    place: str  # centred, sits high, sits low
    v: float
    up: float
    down: float


@dataclass(frozen=True)
class _Found:
    """A stage or clipper on the signal path, with what its fixes need."""

    nets: Nets
    stages: list[Stage]  # every stage on the path (not the clippers)
    row: Stage
    feed: str  # the net it's fed from: the row before (or the guitar)
    pin_nets: frozenset[str]  # its device's nets, but not a supply's or ground
    after: tuple[str, str] | None = None  # where the next row takes the signal, and its name


def _find(circuit: Circuit, ref: str, kind: str) -> _Found:
    """Stage (or clipper) `ref` on the signal path, or a FixError."""
    nets = connect(circuit)
    path = signal_stages(circuit, nets)
    row = next((s for s in path if s.refs[0] == ref and s.kind == kind), None)
    guitar = input_part(circuit)
    if row is None or guitar is None:
        what = "a stage" if kind == "stage" else "a clipper"
        raise FixError(f"{ref} isn't {what} on the signal path, so there's nothing to change.")
    i = path.index(row)
    feed = next(
        (r.net for r in reversed(path[:i]) if r.net != row.net), nets.net_of(guitar.ref, "out")
    )
    held = rail_nets(circuit, nets) | {GROUND}
    pin_nets = frozenset(
        n
        for n, pins in nets.members.items()
        if n not in held and any(r in row.refs for r, _ in pins)
    )
    stages = [s for s in path if s.kind == "stage"]
    return _Found(nets, stages, row, feed, pin_nets, _after(circuit, nets, path, row))


def _after(
    circuit: Circuit, nets: Nets, path: Sequence[Stage], row: Stage
) -> tuple[str, str] | None:
    """Where the signal leaving `row` is next taken in, and what takes it: the next row's
    input (a base, a gate, a + input, a clipper to ground's node) off `row`'s own output,
    or the amp's input. A part between (a series resistor into a clipper, the BD-2's R12)
    can raise the stage's own gain while passing it less: this is where that shows."""
    for r in path[path.index(row) + 1 :]:
        net = signal_input(circuit, nets, r)
        if net is not None and net != row.net:
            return net, r.label
    amp = next((p for p in circuit.parts if isinstance(p, AmpInput)), None)
    return None if amp is None else (nets.net_of(amp.ref, "in"), "the output")


def _touches(p: Part, f: _Found) -> bool:
    """Whether part `p` has a pin on one of the stage's own nets."""
    return any(net in f.pin_nets for (ref, _), net in f.nets.by_pin.items() if ref == p.ref)


def _own_gain(sim: Simulator, c: Circuit, f: _Found, tone: float) -> float:
    """The stage's own small-signal gain at `tone`, as its block shows it: from where
    the signal enters it (or what feeds it) to its output (D-123)."""
    return _gains(sim, c, f, tone)[0]


def _gains(sim: Simulator, c: Circuit, f: _Found, tone: float) -> tuple[float, float]:
    """The stage's own gain at `tone` (`_own_gain`), and from the same start to where the
    next row takes the signal (`_Found.after`; its own gain again when nothing does)."""
    ac = sim.ac(c)
    start = signal_entry(ac, c, f.nets, f.row, f.feed) or f.feed
    base = max(_tone_gain(ac, start, tone), 1e-12)
    own = _tone_gain(ac, f.row.net, tone) / base
    if f.after is None or f.after[0] not in ac.responses:
        return own, own
    return own, _tone_gain(ac, f.after[0], tone) / base


def _places(sim: Simulator, c: Circuit, f: _Found) -> dict[str, _Place]:
    """Where every stage on the path sits, by its first ref."""
    ctx = _Ctx(sim, c, f.nets, sim.op(c), "med")
    out = {}
    for s in f.stages:
        dc, up, down, _ = _room(ctx, s)
        out[s.refs[0]] = _Place(*bias_position(up, down), dc, up, down)
    return out


def _db(ratio: float) -> float:
    return 20 * math.log10(max(ratio, 1e-12))


def _gain_words(db: float) -> str:
    return "gain unchanged" if abs(db) < GAIN_SAME_DB else f"gain {signed_db(db)}"


def _hard_room(sim: Simulator, c: Circuit, f: _Found, place: _Place) -> float | None:
    """Spare room (dB, negative: over) at a hard pick, for the level it would reach unclipped."""
    peak = LEVELS["hard"] * _tone_gain(sim.ac(c), f.row.net)
    return headroom_db(place.up, place.down, peak)


def _room_words(db: float | None) -> str:
    if db is None:
        return "no signal"
    return f"{abs(db):.0f} dB spare" if db >= 0 else f"{abs(db):.0f} dB over"


# --- bias: Centre and Bias to… -------------------------------------------------------


def bias_options(
    sim: Simulator,
    circuit: Circuit,
    ref: str,
    target: float | None = None,
    progress: Progress = _quiet,
) -> dict[str, Any]:
    """What moves stage `ref`'s bias to `target` (0 the bottom of its room, 1 the top;
    None centres it, D-119). A trimmer next to it comes first (D-123): one with a bias
    target gets a new target, and is the only option while its turn reaches; one without
    is turned, or turned and given a target so it holds. Then each resistor on one of the
    stage's nets (not a supply's), searched over the log of its value (the trimmer
    solver's `bisect`) and snapped to E24. Ranked by `centring_rank`."""
    f = _find(circuit, ref, "stage")
    aim = 0.5 if target is None else min(max(target, 0.02), 0.98)
    before = _places(sim, circuit, f)
    now = before[ref]
    out: dict[str, Any] = {
        "ref": ref,
        "target": aim,
        "now": _place_dict(now),
        "options": [],
        "note": None,
    }
    if target is None and now.place == "centred":
        return {**out, "note": f"{ref} is centred already."}
    if abs(now.position - aim) <= BIAS_TOLERANCE:
        return {**out, "note": f"{ref} sits there already."}
    ctx = _BiasCtx(sim, f, before, aim, _own_gain(sim, circuit, f, TONE_HZ))
    notes: list[str] = []
    base, holds = circuit, list[Trimmer]()
    trimmers = [p for p in circuit.parts if isinstance(p, Trimmer) and _touches(p, f)]
    resistors = [p for p in circuit.parts if isinstance(p, Resistor) and _touches(p, f)]
    steps = len(trimmers) + len(resistors)
    options: list[dict[str, Any]] = []
    for i, t in enumerate(trimmers):
        progress(i, steps)
        free = base.with_part(t.ref, bias_target=None)  # what turning it does by hand
        turned = _turn(ctx, free, t)
        if isinstance(turned, str):
            notes.append(turned)
        elif t.bias_target is not None:
            return {**out, "options": [_target_option(ctx, turned, t)]}
        else:
            options += _turn_options(ctx, turned, t)
        if t.bias_target is not None:
            base, holds = free, [*holds, t]  # out of reach: a resistor moves its range
    for i, p in enumerate(resistors):
        progress(len(trimmers) + i, steps)
        changed = _search(base, p, lambda c: ctx.places(c)[ref].position, aim, BIAS_TOLERANCE)
        if changed is not None:
            options.append(ctx.option(changed, _value_change(p, changed), holds))
    progress(steps, steps)
    better = abs(now.position - aim) - BIAS_TOLERANCE
    options = [
        o
        for o in options
        if abs(o["position"] - aim) <= CENTRED and abs(o["position"] - aim) < better
    ]
    options.sort(key=lambda o: o.pop("rank"))
    if not options:
        does = "centres it" if target is None else "moves it there"
        notes.append(
            f"No single resistor next to {ref} {does} within a tenth to ten times its value."
        )
    return {**out, "options": options[:FIX_OPTIONS], "note": " ".join(notes) or None}


def bias_reach(sim: Simulator, circuit: Circuit, ref: str) -> dict[str, Any]:
    """How far Bias to… can move stage `ref` (D-123): the lowest and highest bias position
    (0 the bottom of its room, 1 the top) that any one part it would change reaches at the
    ends of its range, as `bias_options` searches it (a trimmer turned end to end, without
    its target; a resistor from a tenth to ten times its value), within 2 to 98 %. Where a
    part runs one way as it moves, the bar between `lo` and `hi` can be aimed at."""
    f = _find(circuit, ref, "stage")
    now = _places(sim, circuit, f)[ref].position
    base = circuit
    ends: list[Circuit] = []
    for t in (p for p in circuit.parts if isinstance(p, Trimmer) and _touches(p, f)):
        base = base.with_part(t.ref, bias_target=None)
        ends += [base.with_part(t.ref, rotation=r) for r in (0.0, 1.0)]
    for p in circuit.parts:
        if isinstance(p, Resistor) and _touches(p, f):
            value = parse_value(p.value)
            low, high = FIX_BOUNDS["resistor"]
            for v in (max(value / FIX_SPAN, low), min(value * FIX_SPAN, high)):
                ends.append(base.with_part(p.ref, value=format_value(v)))
    reached = [now]
    for c in ends:
        try:
            reached.append(_places(sim, c, f)[ref].position)
        except (SimError, BiasError):  # an end that doesn't simulate: no reach that way
            continue
    lo, hi = (min(max(x, 0.02), 0.98) for x in (min(reached), max(reached)))
    out = {"ref": ref, "now": now, "lo": lo, "hi": hi, "aimable": hi - lo >= REACH_MIN, "why": None}
    if out["aimable"]:
        return out
    device = circuit.part(ref)
    if isinstance(device, Opamp):
        held = sim.op(circuit).voltages[f.nets.net_of(ref, "+")]
        why = (
            f"An op-amp's output sits where its + input is held, here "
            f"{format_quantity(held, 'V')}, and that comes from a reference elsewhere in "
            "the circuit, not from a part next to it."
        )
    else:
        why = (
            "No one part next to it, from a tenth to ten times its value, moves it more "
            f"than {REACH_MIN:.0%} of its room."
        )
    return {**out, "why": why}


def _place_dict(p: _Place) -> dict[str, Any]:
    return {
        "position": p.position,
        "place": p.place,
        "v": p.v,
        "up": p.up if math.isfinite(p.up) else None,
        "down": p.down if math.isfinite(p.down) else None,
    }


@dataclass(frozen=True)
class _BiasCtx:
    """What every bias option is measured against."""

    sim: Simulator
    f: _Found
    before: dict[str, _Place]
    aim: float
    gain: float  # the stage's own gain now

    @property
    def ref(self) -> str:
        return self.f.row.refs[0]

    def places(self, c: Circuit) -> dict[str, _Place]:
        return _places(self.sim, c, self.f)

    def option(
        self,
        changed: Circuit,
        change: tuple[str, dict[str, Any], dict[str, Any], str],
        holds: list[Trimmer],
        rank_ratio: float | None = None,
    ) -> dict[str, Any]:
        """One option: `change` is (part, its new fields, its old fields, its words);
        `holds`, trimmers whose bias target moves with it (so they keep this bias)."""
        part, new, old, words = change
        after = self.places(changed)
        b = after[self.ref]
        moved = [
            {"ref": r, "from": self.before[r].place, "to": a.place}
            for r, a in after.items()
            if r != self.ref
            and a.place != self.before[r].place
            and abs(a.position - 0.5) > abs(self.before[r].position - 0.5)
        ]
        set_, undo = {part: new}, {part: old}
        op = self.sim.op(changed)
        for t in holds:
            assert t.bias_target is not None
            node = self.f.nets.resolve(t.bias_target.node)
            set_[t.ref] = {
                "bias_target": {
                    "node": t.bias_target.node,
                    "volts": round(op.voltages[node], TARGET_DECIMALS),
                }
            }
            undo[t.ref] = {"bias_target": t.bias_target.model_dump()}
            words += f", {t.ref} aimed at {format_quantity(op.voltages[node], 'V')}"
        gain_db = _db(_own_gain(self.sim, changed, self.f, TONE_HZ) / max(self.gain, 1e-12))
        first = (
            ""
            if b.place == "centred"
            else (", clips the top first" if b.up < b.down else ", clips the bottom first")
        )
        was = _hard_room(
            self.sim, changed, self.f, self.before[self.ref]
        )  # the same level, its old room
        room = _hard_room(self.sim, changed, self.f, b)
        hard = (
            f"; at a hard pick {_room_words(room)} (was {_room_words(was)})"
            if room is not None
            else ""
        )
        side = "".join(f"; {m['ref']} then {m['to']}" for m in moved)
        up, down = format_quantity(b.up, "V"), format_quantity(b.down, "V")
        place = f"{b.place} at {format_quantity(b.v, 'V')}"
        return {
            "ref": part,
            "set": set_,
            "undo": undo,
            "label": words,
            "position": b.position,
            "place": b.place,
            "v": b.v,
            "others": moved,
            "gain_db": gain_db,
            "text": f"{words}: {self.ref} {place}, {up} up, {down} down{first}{hard}; "
            f"{_gain_words(gain_db)}{side}.",
            "rank": centring_rank(b.position, rank_ratio or _ratio(new, old), len(moved), self.aim),
        }


def _ratio(new: Mapping[str, Any], old: Mapping[str, Any]) -> float:
    """How big a change is, for the ranking: a value's new over old (1 for a turn)."""
    if "value" in new and "value" in old:
        return parse_value(str(new["value"])) / parse_value(str(old["value"]))
    return 1.0


def _value_change(
    p: Resistor | Capacitor, changed: Circuit
) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    to = changed.part(p.ref)
    assert isinstance(to, (Resistor, Capacitor))
    return p.ref, {"value": to.value}, {"value": p.value}, f"{p.ref} {p.value} → {to.value}"


def _turn(ctx: _BiasCtx, free: Circuit, t: Trimmer) -> Circuit | str:
    """`free` with trimmer `t` turned so the stage sits at the aim, or why it can't."""

    def at(rotation: float) -> float:
        return ctx.places(free.with_part(t.ref, rotation=rotation))[ctx.ref].position

    try:
        found = bisect(at, 0.0, 1.0, ctx.aim, BIAS_TOLERANCE)
        if found is not None:
            return free.with_part(t.ref, rotation=round(found[0], 3))
        ends = [ctx.places(free.with_part(t.ref, rotation=r))[ctx.ref].v for r in (0.0, 1.0)]
    except (SimError, BiasError):
        return f"Turning {t.ref} doesn't simulate here."
    lo, hi = format_quantity(min(ends), "V"), format_quantity(max(ends), "V")
    return f"Turning {t.ref} end to end only moves {ctx.ref} between {lo} and {hi}."


def _turn_text(rotation: float) -> str:
    """A trimmer's turn as the part form writes it: "88 %", "99.6 %"."""
    return f"{round(rotation * 100, 1):g} %"


def _target_option(ctx: _BiasCtx, turned: Circuit, t: Trimmer) -> dict[str, Any]:
    """A trimmer that sets the bias itself (D-123): its target moved to where the turn
    found puts the stage, to the bias bar's 10 mV, and its rotation set to that turn so
    the part shows where it sits (the solver still re-turns it on every run)."""
    assert t.bias_target is not None
    node = ctx.f.nets.resolve(t.bias_target.node)
    volts = round(ctx.sim.op(turned).voltages[node], TARGET_DECIMALS)
    r = turned.part(t.ref)
    assert isinstance(r, Trimmer)
    words = f"{t.ref} aimed at {format_quantity(volts, 'V')} (turns to {_turn_text(r.rotation)})"
    new = {"rotation": r.rotation, "bias_target": {"node": t.bias_target.node, "volts": volts}}
    old = {"rotation": t.rotation, "bias_target": t.bias_target.model_dump()}
    return {
        k: v for k, v in ctx.option(turned, (t.ref, new, old, words), []).items() if k != "rank"
    }


def _turn_options(ctx: _BiasCtx, turned: Circuit, t: Trimmer) -> list[dict[str, Any]]:
    """A trimmer with no target (D-123): turn it there; or turn it and give it a target
    at the stage's output, so it keeps that bias when parts change."""
    r = turned.part(t.ref)
    assert isinstance(r, Trimmer)
    pin = next(
        (f"{ref}.{p}" for ref, p in ctx.f.nets.members[ctx.f.row.net] if ref == ctx.ref),
        ctx.f.row.net,
    )
    v = round(ctx.sim.op(turned).voltages[ctx.f.row.net], TARGET_DECIMALS)
    old = {"rotation": t.rotation}
    turn = ctx.option(
        turned,
        (t.ref, {"rotation": r.rotation}, old, f"Turn {t.ref} to {_turn_text(r.rotation)}"),
        [],
    )
    hold = ctx.option(
        turned,
        (
            t.ref,
            {"rotation": r.rotation, "bias_target": {"node": pin, "volts": v}},
            {**old, "bias_target": None},
            f"Turn {t.ref} to {_turn_text(r.rotation)} and hold {pin} at {format_quantity(v, 'V')}",
        ),
        [],
    )
    return [turn, hold]


def _search(
    circuit: Circuit,
    p: Resistor | Capacitor,
    measure: Callable[[Circuit], float],
    aim: float,
    tolerance: float,
) -> Circuit | None:
    """The circuit with part `p` at the series value (E24 resistors, E12 capacitors)
    where `measure` comes nearest `aim`, searched from a tenth to ten times its value;
    None when no value there reaches it, or the value wouldn't change."""
    kind = "resistor" if isinstance(p, Resistor) else "capacitor"

    def with_value(value: float) -> Circuit:
        return circuit.with_part(p.ref, value=format_value(value))

    now = parse_value(p.value)
    bounds = FIX_BOUNDS[kind]
    lo = math.log10(max(now / FIX_SPAN, bounds[0]))
    hi = math.log10(min(now * FIX_SPAN, bounds[1]))
    try:
        found = bisect(lambda x: measure(with_value(10**x)), lo, hi, aim, tolerance)
        if found is None:
            return None
        exact = 10 ** found[0]
        near = {
            snap_to_series(exact, SERIES[kind]),
            *series_values(exact / 1.1, exact * 1.1, SERIES[kind]),
        }
        tried = {v: measure(with_value(v)) for v in near if not math.isclose(v, now, rel_tol=1e-6)}
    except (SimError, BiasError):  # a value that doesn't simulate: not an option
        return None
    return with_value(min(tried, key=lambda v: abs(tried[v] - aim))) if tried else None


# --- gain: a slider per part (D-125) -------------------------------------------------


@dataclass(frozen=True)
class _Reading:
    """One row of the chain as estimated at one pick: spare dB for a stage (negative:
    over; None held by diodes in its feedback, or no signal), driven dB for a clipper."""

    label: str
    kind: str
    amount: float | None
    clips: bool


Knee = list[tuple[float, float]]  # a clipper as measured: (dB in, dB driven) at each pick


def clipper_knees(sim: Simulator, circuit: Circuit, tone: float = TONE_HZ) -> dict[str, Knee]:
    """How each clipper takes the signal, by its net (a stage its diodes hold shares it):
    at each pick, the level reaching it unclipped and how many dB it took off, from the
    pane's own transients (cached). Diodes start to bite before their clamp, so a wall at
    the hard pick's peak would call a soft pick clean; these three points don't."""
    path = _signal_path(sim, circuit, tone)
    if isinstance(path, str):
        return {}
    trans = [sim.tran(circuit, path.wanted, lv, tone) for lv in LEVELS]
    knees: dict[str, Knee] = {}
    for i, s in enumerate(path.found):
        if s.kind != "clipper":
            continue
        points = []
        for t in trans:
            st = t.stats[s.net]
            unclipped = path.predicted(i, t)
            points.append((_db(unclipped), drive_db(unclipped, max(st.peak_pos, -st.peak_neg))))
        knees[s.net] = sorted(points)
    return knees


def _driven(knee: Knee, level_db: float) -> float:
    """How many dB a clipper takes off a level (dB) reaching it: read off its measured
    points, and past them as a clamp (what gets through stays put, so the drive moves dB
    for dB with the level, never below 0). On the starters that lands within a dB or two
    of a transient ten times the gain away."""
    xs, ys = [x for x, _ in knee], [y for _, y in knee]
    if level_db < xs[0]:
        return max(0.0, ys[0] + level_db - xs[0])
    if level_db > xs[-1]:
        return ys[-1] + level_db - xs[-1]
    return float(np.interp(level_db, xs, ys))


def estimate_chain(
    sim: Simulator, circuit: Circuit, knees: Mapping[str, Knee], tone: float = TONE_HZ
) -> dict[str, list[_Reading]] | None:
    """The chain at each pick, estimated without a transient (D-125): the small-signal
    level row by row, each stage capped at its room and each clipper taking off what its
    measured `knees` say, so a stage after a clipper gets the clipped level. A DC and an
    AC run, not three transients: quick enough for every value a slider steps through.
    None with no signal path."""
    path = _signal_path(sim, circuit, tone)
    if isinstance(path, str):
        return None
    ctx = _Ctx(sim, circuit, connect(circuit), sim.op(circuit), "med")
    held = {s.net for s in path.found if s.kind == "clipper" and s.role == "in feedback"}
    rooms = {i: _room(ctx, s)[1:3] for i, s in enumerate(path.found) if s.kind == "stage"}
    out: dict[str, list[_Reading]] = {}
    for lv, amplitude in LEVELS.items():
        peak = {path.source: amplitude}
        rows = []
        for i, s in enumerate(path.found):
            feed = path.feed(i)
            unclipped = peak[feed] * path.gain[s.net] / max(path.gain[feed], 1e-12)
            knee = knees.get(s.net)
            drive = _driven(knee, _db(unclipped)) if knee else 0.0
            if s.kind == "clipper":
                reached = unclipped / 10 ** (drive / 20)
                rows.append(_Reading(s.label, "clipper", drive, clipper_clips(drive)))
            elif s.net in held:
                reached = unclipped / 10 ** (drive / 20)
                rows.append(_Reading(s.label, "stage", None, False))
            else:
                up, down = rooms[i]
                room = headroom_db(up, down, unclipped)
                reached = min(unclipped, max(up, down))
                rows.append(_Reading(s.label, "stage", room, stage_clips(room, False)))
            peak[s.net] = reached
        out[lv] = rows
    return out


def _first_clip(chain: Mapping[str, list[_Reading]]) -> tuple[str, int] | None:
    """The first thing to clip as the pick gets harder: (level, row), as the pane's top line."""
    for lv in LEVELS:
        for i, r in enumerate(chain[lv]):
            if r.clips:
                return lv, i
    return None


def _amount_words(r: _Reading) -> str:
    if r.amount is None:
        return "held by its diodes"
    if r.kind == "clipper":
        return f"driven {r.amount:.0f} dB"
    return _room_words(r.amount)


def _clip_words(chain: Mapping[str, list[_Reading]], was: Mapping[str, list[_Reading]]) -> str:
    """ "Clips first: D1, D2, from a soft pick (was medium); at a hard pick driven 16 dB
    (was 13 dB)." Compared with the chain as it is now, both estimated."""
    first, before = _first_clip(chain), _first_clip(was)
    if first is None:
        return "Nothing clips, even at a hard pick" + (
            "." if before is None else f" (was: {was[before[0]][before[1]].label} clipped)."
        )
    lv, i = first
    r, hard = chain[lv][i], chain["hard"][i]
    text = f"Clips first: {r.label}, from a {LEVEL_NAMES[lv]} pick"
    if before is None:
        text += " (was clean)"
    elif before[1] != i:
        text += f" (was {was[before[0]][before[1]].label})"
    elif before[0] != lv:
        text += f" (was {LEVEL_NAMES[before[0]]})"
    then = was["hard"][i]
    same = _amount_words(then) == _amount_words(hard)
    return (
        text
        + f"; at a hard pick {_amount_words(hard)}"
        + ("." if same else f" (was {_amount_words(then).removeprefix('driven ')}).")
    )


def _own_words(f: _Found, chain: Mapping[str, list[_Reading]]) -> str:
    """This stage at a hard pick, unless it's what clips first: its spare or over, or for a
    stage its diodes hold, how hard they're driven."""
    first = _first_clip(chain)
    rows = chain["hard"]
    i = next(k for k, r in enumerate(rows) if r.label == f.row.label and r.kind == "stage")
    if rows[i].amount is None:  # held: its diodes' row comes right after it on the same net
        diodes = rows[i + 1] if i + 1 < len(rows) and rows[i + 1].kind == "clipper" else None
        if diodes is None or (first and first[1] == i + 1):
            return ""
        return f" {diodes.label} {_amount_words(diodes)} at a hard pick."
    if first and first[1] == i:
        return ""
    return f" {f.row.label} itself {_amount_words(rows[i])} at a hard pick."


def _gain_at_full(sim: Simulator, c: Circuit, f: _Found, pot: Pot, tone: float) -> float:
    """A pot's stage gain turned to whichever end gives the most."""
    return max(_own_gain(sim, c.with_part(pot.ref, rotation=r), f, tone) for r in (0.0, 1.0))


def _slider_values(p: Resistor | Pot) -> list[float]:
    """What a part's slider steps through: E12 (a pot: the values pots are sold in) from a
    tenth to ten times its value, its own included."""
    now = parse_value(p.value)
    lo, hi = FIX_BOUNDS["resistor"]
    series = POT_SERIES if isinstance(p, Pot) else SLIDER_SERIES
    found = series_values(max(now / FIX_SPAN, lo), min(now * FIX_SPAN, hi), series)
    return sorted({*found, now})


def _steps(
    sim: Simulator,
    circuit: Circuit,
    f: _Found,
    p: Resistor | Pot,
    tone: float,
    knees: Mapping[str, Knee],
    was: Mapping[str, list[_Reading]],
    g0: tuple[float, float],
    tick: Callable[[], None] = lambda: None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Each value on part `p`'s slider: its gain change (`gains`: own, into the next row),
    sorted by what reaches the next row, what clips first at each pick
    (estimated, `estimate_chain`) and where the stage then sits; and a note when the
    slider stops short. It runs out from the value it has each way and stops before a
    value that saturates a stage at DC (or doesn't simulate): its gain means nothing
    there, so nothing past it is offered. `tick` is called after each value tried."""
    now = parse_value(p.value)
    place = _places(sim, circuit, f)[f.row.refs[0]].place
    broken = {s.ref for s in sim.ac(circuit).saturated}  # already: not this part's doing
    values = _slider_values(p)
    mid = next(i for i, v in enumerate(values) if math.isclose(v, now, rel_tol=1e-6))
    out: list[dict[str, Any]] = []
    stops: list[str] = []
    for run in (values[mid:], values[mid::-1]):
        for v in run:
            step = _step(sim, circuit, f, p, v, tone, knees, was, g0, place, broken)
            tick()
            if isinstance(step, str):
                stops.append(step)
                break
            if not out or not step["now"]:
                out.append(step)
    note = " ".join(stops) or None
    return sorted(out, key=lambda s: float(s["gain_db"])), note


def _stop(value: str, why: str) -> str:
    return f"At {value} {why}, so the slider stops before it."


def _step(
    sim: Simulator,
    circuit: Circuit,
    f: _Found,
    p: Resistor | Pot,
    v: float,
    tone: float,
    knees: Mapping[str, Knee],
    was: Mapping[str, list[_Reading]],
    g0: tuple[float, float],
    place: str,
    broken: set[str],
) -> dict[str, Any] | str:
    """One value on a slider (`_steps`), or why the slider stops there."""
    here = math.isclose(v, parse_value(p.value), rel_tol=1e-6)
    value = str(p.value) if here else format_value(v)
    c = circuit if here else circuit.with_part(p.ref, value=value)
    try:
        stuck = [s for s in sim.ac(c).saturated if s.ref not in broken]
        if stuck:
            return _stop(value, f"{stuck[0].ref} stops working (saturated at DC)")
        sits = _places(sim, c, f)[f.row.refs[0]]
        if not here and not EDGE <= sits.position <= 1 - EDGE:
            return _stop(value, f"{f.row.label} runs into its limit at DC")
        own, nxt = _gains(sim, c, f, tone)
        db, next_db = _db(own / g0[0]), _db(nxt / g0[1])
        chain = estimate_chain(sim, c, knees, tone)
        full = _db(_gain_at_full(sim, c, f, p, tone) / g0[0]) if isinstance(p, Pot) else None
    except (SimError, BiasError, ConnectivityError):
        return _stop(value, "it doesn't simulate")
    if chain is None:
        return _stop(value, "there's no signal path")
    gain = f"gain {signed_db(db)}" if not here else "as it is"
    if full is not None:
        gain += f", {signed_db(full)} turned full up"
    if not here and f.after is not None and abs(next_db - db) >= INTO_SAID_DB:
        gain += f"; into {f.after[1]} {signed_db(next_db)}"  # a part between: they differ
    bias = "" if sits.place == place else f", then {sits.place} at {format_quantity(sits.v, 'V')}"
    return {
        "value": value,
        "now": here,
        "gain_db": next_db,  # what the slider is spread by: what reaches the next row
        "own_db": db,
        "clips": {lv: any(r.clips for r in rows) for lv, rows in chain.items()},
        "text": f"{p.ref} {value}: {gain}{bias}.",
        "chain": _clip_words(chain, was) + _own_words(f, chain),
    }


def gain_options(
    sim: Simulator,
    circuit: Circuit,
    ref: str,
    tone: float = TONE_HZ,
    progress: Progress = _quiet,
) -> dict[str, Any]:
    """The parts that set how hard stage `ref` drives what comes after it (D-123, D-125):
    each resistor, pot and capacitor on one of its nets, ranked by what +10 % does to its
    own gain or to what reaches the next row (`into`), whichever moves more, at `tone`
    (an ngspice AC run each); the sliders are spread by what reaches the next row (D-223).
    A resistor or pot gets a slider: every value from a tenth to ten times its own
    (`_steps`), each with its gain change and
    what clips first at each pick, estimated. A capacitor gets none: it moves where the
    curve bends, which Edit curve shows. Trimmers aren't offered: they set the bias."""
    f = _find(circuit, ref, "stage")
    g0 = _gains(sim, circuit, f, tone)
    near = [
        p for p in circuit.parts if isinstance(p, (Resistor, Capacitor, Pot)) and _touches(p, f)
    ]
    tries = {
        p.ref: len(_slider_values(p)) + 1 if isinstance(p, (Resistor, Pot)) else 1 for p in near
    }
    # until the parts are ranked, the most their sliders could take: the bar never goes back
    most = len(near) + sum(sorted(tries.values(), reverse=True)[:GAIN_PARTS])
    nudged = []
    for i, p in enumerate(near):
        progress(i, most)
        bumped = circuit.with_part(p.ref, value=format_value(parse_value(p.value) * NUDGE))
        try:
            own, nxt = _gains(sim, bumped, f, tone)
        except SimError:
            continue
        db, into = _db(own / g0[0]), _db(nxt / g0[1])
        moved = max(db, into, key=abs)  # its own gain or what reaches the next row
        if abs(moved) >= GAIN_MOVES_DB:
            nudged.append((p, moved))
    nudged.sort(key=lambda x: -abs(x[1]))
    nudged = nudged[:GAIN_PARTS]
    # a step for each part nudged, then for each value tried on each slider (its own
    # twice, once each way; at most: one stopping early skips the rest)
    sliders = [tries[p.ref] for p, _ in nudged]
    steps = len(near) + sum(sliders)
    done = len(near)

    def tick() -> None:
        nonlocal done
        done += 1
        progress(done, steps)

    knees = clipper_knees(sim, circuit, tone)
    was = estimate_chain(sim, circuit, knees, tone)
    parts = []
    for (p, db), size in zip(nudged, sliders, strict=True):
        start = done
        progress(done, steps)
        kind = p.type
        part: dict[str, Any] = {"ref": p.ref, "kind": kind, "value": p.value, "nudge_db": db}
        if isinstance(p, Capacitor):
            part["text"] = (
                f"{p.ref} {p.value}: moves where the curve bends rather than how hard it "
                f"drives (+10 % moves its gain at {format_quantity(tone, 'Hz')} {signed_db(db)})."
            )
            part["steps"] = []
        else:
            assert isinstance(p, (Resistor, Pot)) and was is not None
            part["text"] = f"{p.ref} {p.value}"
            part["steps"], part["note"] = _steps(sim, circuit, f, p, tone, knees, was, g0, tick)
        done = start + size
        parts.append(part)
    progress(steps, steps)
    named = f.after[1] if f.after else f.row.label
    out: dict[str, Any] = {"ref": ref, "tone": tone, "gain_db": _db(g0[0]), "into": named,
                           "parts": parts}  # fmt: skip
    note = None if parts else f"No resistor, pot or capacitor next to {ref} changes its gain."
    return {**out, "note": note, "options": []}


# --- clipper swaps -------------------------------------------------------------------


@dataclass(frozen=True)
class Arranged:
    """A clipper arrangement the browser placed (D-124): the circuit with parts added in
    series, and what went where: (new ref, its pin that meets the diode's, diode, the
    diode's pin). `room`: the sheet with room made first (parts moved, nothing added), if
    it was. `key` comes back with its option, so the browser knows which it is."""

    key: str
    circuit: Circuit
    series: tuple[tuple[str, str, str, str], ...]
    room: Circuit | None = None


def clipper_options(
    sim: Simulator,
    circuit: Circuit,
    ref: str,
    tone: float = TONE_HZ,
    progress: Progress = _quiet,
    arranged: Sequence[Arranged] = (),
) -> dict[str, Any]:
    """Diodes to swap into clipper `ref` (D-118, D-123): every diode in it as each of
    `CLIPPERS`, and for a pair, the second one a red LED (lopsided). Then the
    arrangements placed by the browser (D-124): two in series, 2 + 1, a resistor in
    series; each checked to connect as said (one that doesn't is left out, `note`). Each
    measured at a hard pick: where it then clamps and how much louder or quieter it is
    after it."""
    f = _find(circuit, ref, "clipper")
    diodes = [p for p in (circuit.part(r) for r in f.row.refs) if isinstance(p, (Diode, Led))]
    if not diodes:
        raise FixError(f"{ref} has no diodes to swap.")
    now = _clamp(sim, circuit, f.row, tone)
    swaps: list[tuple[str, dict[str, tuple[str, str]]]] = []
    for kind, model, name in CLIPPERS:
        if all(d.type == kind and d.model == model for d in diodes):
            continue
        label = f"{', '.join(d.ref for d in diodes)} \u2192 {model} ({name})"
        swaps.append((label, {d.ref: (kind, model) for d in diodes}))
    if len(diodes) == 2 and diodes[1].type != "led":
        label = f"{diodes[1].ref} \u2192 APT1608SURCK (red LED), lopsided"
        swaps.append((label, {diodes[1].ref: ("led", "APT1608SURCK")}))
    steps = len(swaps) + len(arranged)

    def option(label: str, changed: Circuit, row: Stage) -> dict[str, Any] | None:
        try:
            up, down, peak = _clamp(sim, changed, row, tone)
        except SimError:
            return None
        louder = _db(peak / max(now[2], 1e-12))
        return {
            "ref": ref,
            "label": label,
            "up": up,
            "down": down,
            "louder_db": louder,
            "text": f"{label}: clamps at {clamp_short(up, down)}, {_level_words(louder)} after it.",
        }

    options = []
    for i, (label, to) in enumerate(swaps):
        progress(i, steps)
        changed = circuit
        for r, (kind, model) in to.items():
            changed = _with_model(changed, r, kind, model)
        got = option(label, changed, f.row)
        if got:
            old = {d.ref: {"type": d.type, "model": d.model} for d in diodes if d.ref in to}
            new = {r: {"type": kind, "model": model} for r, (kind, model) in to.items()}
            options.append({**got, "set": new, "undo": old})
    notes: list[str] = []
    for i, a in enumerate(arranged, len(swaps)):
        progress(i, steps)
        row = _arranged_row(circuit, f, a, {d.ref for d in diodes})
        if isinstance(row, str):
            notes.append(row)
            continue
        got = option(_arranged_label(a, len(diodes)), a.circuit, row)
        if got:
            options.append({**got, "set": {}, "undo": {}, "key": a.key})
    progress(steps, steps)
    note = " ".join(dict.fromkeys(notes)) or None
    return {"ref": ref, "now": {"up": now[0], "down": now[1]}, "options": options, "note": note}


def _arranged_label(a: Arranged, diodes: int) -> str:
    """An arrangement's words: "Two in series: D1 + D5, D2 + D6 (1N4148)", "Uneven, 2 + 1:
    D2 + D6 (1N4148)", "2k2 in series: D1 + R12, D2 + R13"."""
    added = [a.circuit.part(new) for new, _, _, _ in a.series]
    pairs = ", ".join(f"{of} + {new}" for new, _, of, _ in a.series)
    first = added[0]
    if isinstance(first, Resistor):
        return f"{format_value(parse_value(first.value))} in series: {pairs}"
    models = sorted({p.model for p in added if isinstance(p, (Diode, Led))})
    head = "Two in series" if len(a.series) == diodes or diodes == 1 else "Uneven, 2 + 1"
    return f"{head}: {pairs} ({', '.join(models)})"


def _arranged_row(circuit: Circuit, f: _Found, a: Arranged, diodes: set[str]) -> Stage | str:
    """The clipper's row in arrangement `a`, its nets as they're named there; or, when `a`
    isn't `circuit` with only the parts it says added in series with the clipper's diodes
    (and, with room made, only parts moved), why it isn't offered: a placement that joined
    anything else would be measured wrongly."""
    where = ", ".join(sorted({of for _, _, of, _ in a.series}))
    no_room = (
        f"There isn't room to add parts beside {where} cleanly, so some arrangements "
        "aren't offered: make some space around them on the sheet and try again."
    )
    added = {new for new, _, _, _ in a.series}
    before = a.room or circuit
    if (
        {p.ref: p for p in a.circuit.parts if p.ref not in added}
        != {p.ref: p for p in before.parts}
        or any(of not in diodes for _, _, of, _ in a.series)
        or not all(isinstance(a.circuit.part(r), (Diode, Led, Resistor)) for r in added)
    ):
        return no_room
    if a.room is not None:
        try:
            moved = connect(a.room)
        except ConnectivityError:
            moved = None
        if (
            moved is None
            or _unplaced(a.room.parts) != _unplaced(circuit.parts)
            or _groups(moved.by_pin) != _groups(f.nets.by_pin)
        ):
            return (
                f"Making room beside {where} would have changed what's connected, so some "
                "arrangements aren't offered: make some space around them on the sheet and "
                "try again."
            )
    try:
        nets = connect(a.circuit)
    except ConnectivityError:
        return no_room
    expected: dict[PinRef, str] = dict(f.nets.by_pin)
    for new, near, of, pin in a.series:
        far = [p for (r, p) in nets.by_pin if r == new and p != near]
        if (of, pin) not in expected or (new, near) not in nets.by_pin or len(far) != 1:
            return no_room
        expected[(new, far[0])] = expected[(of, pin)]
        expected[(of, pin)] = expected[(new, near)] = f"#{new}"  # a net of its own between them
    if _groups(expected) != _groups(nets.by_pin):
        return no_room
    renamed = {old: nets.by_pin[pin_ref] for pin_ref, old in expected.items()}
    return replace(f.row, net=renamed[f.row.net], other=renamed.get(f.row.other, f.row.other))


def _groups(by_pin: Mapping[PinRef, str]) -> set[frozenset[PinRef]]:
    """The pins joined together, whatever their nets are called."""
    out: dict[str, set[PinRef]] = {}
    for pin_ref, net in by_pin.items():
        out.setdefault(net, set()).add(pin_ref)
    return {frozenset(g) for g in out.values()}


def _unplaced(parts: Sequence[Part]) -> dict[str, dict[str, Any]]:
    """Parts by ref without where they sit: making room may move them, nothing else."""
    return {p.ref: p.model_dump(exclude={"pos"}) for p in parts}


def _with_model(c: Circuit, ref: str, kind: str, model: str) -> Circuit:
    """`c` with diode `ref` as a `kind` ("diode" or "led") of `model`."""
    old = c.part(ref)
    cls = Led if kind == "led" else Diode
    new = cls.model_validate({**old.model_dump(by_alias=True), "type": kind, "model": model})
    return c.model_copy(update={"parts": [new if p.ref == ref else p for p in c.parts]})


def _clamp(sim: Simulator, c: Circuit, row: Stage, tone: float) -> tuple[float, float, float]:
    """Where a clipper clamps across itself at a hard pick (up, down) and the peak at its node."""
    tran = sim.tran(c, [row.net, row.other], "hard", tone)
    node = scope_window(tran, row.net)
    return *clamp_across(tran, row), float(np.max(np.abs(node - float(np.mean(node)))))


def _level_words(db: float) -> str:
    if abs(db) < GAIN_SAME_DB * 5:
        return "about as loud"
    return f"{abs(db):.0f} dB {'louder' if db > 0 else 'quieter'}"
