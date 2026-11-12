"""The simulation pipeline: circuit → bias solved → netlist → engine → results by net.

Every analysis first solves trimmers that have a bias target (D-039), so results always
reflect the biased circuit. Results are keyed by net name; probes accept a net name or a
pin reference (`Q1.D`).
"""

import math
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

import numpy as np
import numpy.typing as npt

from solum.analysis.dc import Saturation, saturation
from solum.analysis.signal import NodeStats, detrend, last_cycles, node_stats, spectrum
from solum.bias import (
    TOLERANCE,
    BiasResult,
    Reach,
    bias_trimmers,
    solve_bias,
    target_reach,
)
from solum.cache import CachedEngine, SimCache, cache_from_settings
from solum.circuit.connectivity import Nets, connect
from solum.circuit.schema import Circuit, VSource
from solum.config import Settings
from solum.linear import Ports, held_nodes, port_admittance, port_nodes
from solum.models import ModelLibrary, load_models
from solum.netlist import (
    Ac,
    Dc,
    Netlist,
    NetlistError,
    Op,
    Tran,
    element_name,
    generate_netlist,
    input_part,
    rail_sources,
    require_wired,
)
from solum.sim.engine import (
    DEFAULT_TIMEOUT,
    SimEngine,
    SimError,
    engine_from_settings,
)
from solum.tester import fit_bjt

Array = npt.NDArray[np.float64]
Complex = npt.NDArray[np.complex128]

# Input sine amplitude (volts peak) for the scope's three pick levels (D-038), from the
# TS808 page: single coils 60-200 mV, humbuckers 200-600 mV, hard picking up to 2 V.
LEVELS: dict[str, float] = {"soft": 0.1, "med": 0.3, "hard": 1.0}
TONE_HZ = 200.0
TONES = (100.0, 200.0, 1000.0, 3000.0)  # the tones headroom is measured at (D-122)
MAX_AMPLITUDE = 10.0  # volts peak: far past any pickup, so a level sweep can't ask for nonsense
SETTLE_CYCLES = 10  # the shortest wait before measuring, at any tone
MEASURE_CYCLES = 10
# Settling (D-122): how long a circuit needs before its cycles repeat is found per
# circuit, at a hard pick and a low tone (long windows see slow drift), by doubling the
# wait until the windows after it, twice it and four times it show it converging. Then
# the wait in seconds is used at every tone.
SETTLE_HZ = 100.0
SETTLE_START_S = 0.05  # the first wait tried
SETTLE_TOLERANCE = 0.01  # of a net's harmonics
SETTLE_NOISE = 0.003  # changes this small are steady, whatever their ratio (jitter can
# line up twice by chance; a real slow drift, the 47 uF clamp in the tests, is 0.5 then 0.9 %)
SETTLE_FLOOR = 0.05  # a net's harmonics count as at least this much of the guitar's peak
MAX_SETTLE_S = 0.4
STIFF_PROBE_CYCLES = 2  # a short run counting the simulator's steps first
STIFF_STEPS = 4.0  # times the tone's steps: the starters take 1-1.2, a charge pump 44
SETTLE_MEMO = 64  # circuits whose settling a simulator remembers
OP_MEMO = 8  # circuits whose operating point a simulator holds (`Simulator._op`)
STEPS_PER_CYCLE = 400
# The wait before measuring (D-275): all but its last SETTLE_CYCLES go by at coarser steps
# when there are enough of them to be worth a second run.
WAIT_STEPS_PER_CYCLE = 100
WAIT_WORTH = 10  # cycles
# A recording's run may take this many seconds per second of audio (D-024: the Big Muff
# renders at ~0.7x real time; a hard-driven circuit takes more steps).
RECORDING_TIMEOUT_PER_S = 30.0


def recording_limit(seconds: float) -> float:
    """How long a recording of `seconds` may run before it's stopped (D-095)."""
    return RECORDING_TIMEOUT_PER_S * seconds + 30


@dataclass(frozen=True)
class OpResult:
    voltages: dict[str, float]  # net → volts
    currents: dict[str, float]  # "Q1.ic", "Q1.ib", "J1.id" → amps (into the terminal)
    bias: dict[str, float] = field(default_factory=dict)  # trimmer ref → solved rotation
    supply: dict[str, float] = field(default_factory=dict)  # rail → amps it delivers
    held: list["Held"] = field(default_factory=list)  # each bias target, as the run met it


@dataclass(frozen=True)
class Held:
    """A trimmer's bias target and how the run met it: the DC overlay's ◎ (D-127)."""

    ref: str  # the trimmer
    node: str  # as its target names it ("Q1.D")
    net: str
    volts: float  # the target
    reached: float  # the node's volts at the solved turn
    rotation: float  # the solved turn

    @property
    def met(self) -> bool:
        return abs(self.reached - self.volts) <= TOLERANCE


IMPEDANCE_HZ = 1000.0  # where impedances are measured (D-127)


@dataclass(frozen=True)
class AcResult:
    freq: Array
    responses: dict[str, Complex]  # net → response to a 1 V source at the guitar input
    saturated: list[Saturation]

    @property
    def valid(self) -> bool:
        """False when an active stage is saturated at DC: the curve means nothing then."""
        return not self.saturated


@dataclass(frozen=True)
class TranResult:
    level: str
    amplitude: float
    freq: float
    time: Array
    input: str  # the input net
    waves: dict[str, Array]  # net → volts
    stats: dict[str, NodeStats]  # requested net → stats vs the input
    settled: bool | None = True  # False: still drifting; None: not checked (`Simulator.settling`)


@dataclass(frozen=True)
class Settling:
    seconds: float  # how long to wait before measuring
    settled: bool | None  # False: still drifting at MAX_SETTLE_S; None: not checked


@dataclass(frozen=True)
class Linearised:
    """A circuit as the linear system the in-browser solver solves (`solum.linear`,
    D-079): the biased circuit, ngspice's own AC result, the AC netlist (with sense
    sources) whose elements make the system, and each semiconductor measured as an
    N-port at the operating point."""

    circuit: Circuit  # with bias trimmers solved
    ac: AcResult
    netlist: Netlist
    ports: dict[str, Ports]  # ref → its admittance


@dataclass(frozen=True)
class SweepResult:
    sweep: Array  # the swept source's volts
    voltages: dict[str, Array]  # net → volts at each sweep point
    currents: dict[str, Array]  # vsource ref → amps flowing out of its + pin


class Simulator:
    def __init__(
        self, engine: SimEngine, models: ModelLibrary, timeout: float | None = DEFAULT_TIMEOUT
    ) -> None:
        self.engine = engine
        # a measured transistor's BF and leakage are fitted on the simulated tester (D-153)
        self.models = models.with_fitter(lambda m, hfe, leak: fit_bjt(engine, models, m, hfe, leak))
        self.timeout = timeout
        self._settled: dict[str, Settling] = {}  # first search run's netlist → its settling
        self._last_wait: dict[str, float] = {}  # circuit id → the wait its last search found
        self._ops: list[tuple[Circuit, OpResult]] = []  # the last circuits solved (`_op`)
        self._ops_lock = threading.Lock()

    def resolve(self, circuit: Circuit, name: str) -> str:
        return connect(circuit).resolve(name)

    def solve_bias(self, circuit: Circuit) -> BiasResult:
        return solve_bias(circuit, lambda c: self._op(c).voltages)

    def target_reach(self, circuit: Circuit, ref: str) -> Reach:
        """How far targeted trimmer `ref` moves its node (`bias.target_reach`, D-127)."""
        return target_reach(circuit, ref, lambda c: self._op(c).voltages)

    def _biased(self, circuit: Circuit) -> BiasResult:
        if not bias_trimmers(circuit):
            return BiasResult(circuit, {}, {})
        return self.solve_bias(circuit)

    def _run(
        self,
        netlist: Netlist,
        kind: str,
        timeout: float | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> Mapping[str, npt.NDArray[np.generic]]:
        timeout = timeout or self.timeout
        try:
            return (
                self.engine.run(netlist.text, timeout=timeout, progress=progress).plot(kind).vectors
            )
        except SimError as err:
            # the error rules (solum.rules) map ngspice's node names back to nets
            err.nodes = netlist.nodes
            raise

    def _op(self, circuit: Circuit) -> OpResult:
        """The operating point of `circuit` as it stands (no bias solving). The last few
        circuits' answers are kept by the circuit object itself: one request asks for the
        same circuit's several times over (its DC, then each AC run's saturation check,
        each impedance), and building the netlist again each time was a quarter of a
        search's own work (Phase 10, D-280). Don't change a circuit after running it."""
        with self._ops_lock:
            kept = next((r for c, r in self._ops if c is circuit), None)
        if kept is not None:
            return kept
        result = self._solve_op(circuit)
        with self._ops_lock:
            self._ops.append((circuit, result))
            del self._ops[:-OP_MEMO]
        return result

    def _solve_op(self, circuit: Circuit) -> OpResult:
        netlist = generate_netlist(circuit, self.models, Op())
        vectors = self._run(netlist, "op")
        # Nets the simulator never saw (e.g. unused comp pins) are left out.
        voltages = {
            net: 0.0 if node == "0" else float(vectors[node][0].real)
            for net, node in netlist.nodes.items()
            if node == "0" or node in vectors
        }
        currents = {}
        for ref, name in netlist.devices.items():
            for key in ("ic", "ib", "id"):
                vec = vectors.get(f"@{name.lower()}[{key}]")
                if vec is not None:
                    currents[f"{ref}.{key}"] = float(vec[0].real)
        supply = {  # a source's branch current flows + to - inside it: delivered is minus
            rail: -float(vectors[f"{name.lower()}#branch"][0].real)
            for rail, name in rail_sources(circuit).items()
        }
        return OpResult(voltages, currents, supply=supply)

    def op(self, circuit: Circuit) -> OpResult:
        """DC voltage at every net and each transistor's currents."""
        biased = self._biased(circuit)
        result = self._op(biased.circuit)
        nets = connect(circuit)
        held = [
            Held(t.ref, t.bias_target.node, nets.resolve(t.bias_target.node), t.bias_target.volts,
                 biased.volts[t.ref], biased.rotations[t.ref])
            for t in bias_trimmers(circuit) if t.bias_target is not None
        ]  # fmt: skip
        return replace(result, bias=biased.rotations, held=held)

    def ac(self, circuit: Circuit, sweep: Ac | None = None) -> AcResult:
        """Frequency response at every net, flagged invalid if a stage is saturated at DC."""
        biased = self._biased(circuit).circuit
        found = self._saturated(biased)
        netlist = generate_netlist(biased, self.models, sweep or Ac())
        freq, responses = _ac_vectors(self._run(netlist, "ac"), netlist)
        return AcResult(freq, responses, found)

    def saturated(self, circuit: Circuit) -> list[Saturation]:
        """The active stages saturated or cut off at DC, bias trimmers solved first."""
        return self._saturated(self._biased(circuit).circuit)

    def _saturated(self, biased: Circuit) -> list[Saturation]:
        dc = self._op(biased)
        return saturation(biased, connect(biased), dc.voltages, dc.currents, self.models)

    def impedance(
        self, circuit: Circuit, net: str, freq: float = IMPEDANCE_HZ, open: str | None = None
    ) -> tuple[complex, list[Saturation]]:
        """The impedance looking into `net` at `freq` (ohms): 1 A AC driven there, the guitar
        silent, its volts read back; with `open` the guitar or the amp left out (D-127).
        With it, the stages saturated at DC: the number means little then."""
        biased = self._biased(circuit).circuit
        sweep = Ac(start=freq, stop=freq, per_decade=1, inject=net, open=open)
        netlist = generate_netlist(biased, self.models, sweep)
        _, responses = _ac_vectors(self._run(netlist, "ac"), netlist)
        return complex(responses[net][0]), self._saturated(biased)

    def linearise(self, circuit: Circuit, sweep: Ac | None = None) -> Linearised:
        """The AC response, and every semiconductor as an N-port admittance at the
        operating point: one run with the guitar driving, then one per device node with
        1 A injected there, reading the current into each pin (D-079)."""
        biased = self._biased(circuit).circuit
        dc = self._op(biased)
        nets = connect(biased)
        base = replace(sweep or Ac(), sense=True, inject=None)
        main = generate_netlist(biased, self.models, base, nets)
        held = held_nodes(main.elements)
        nodes = {ref: port_nodes(found, held) for ref, found in main.sensed.items()}
        net_of = {node: net for net, node in main.nodes.items()}
        driven = sorted({n for found in nodes.values() for n in found})
        runs = [self._run(main, "ac")] + [
            self._run(generate_netlist(biased, self.models, replace(base, inject=net_of[n]), nets),
                      "ac")
            for n in driven
        ]  # fmt: skip
        freq, responses = _ac_vectors(runs[0], main)
        ports = {}
        for ref, found in main.sensed.items():
            volts = np.zeros((len(freq), len(nodes[ref]), len(runs)), dtype=np.complex128)
            currents = np.zeros_like(volts)
            for i, node in enumerate(nodes[ref]):
                for k, vectors in enumerate(runs):
                    volts[:, i, k] = vectors[node]
                    for s in found:
                        if s.node == node:
                            currents[:, i, k] += np.asarray(
                                vectors[f"{s.source.lower()}#branch"], dtype=np.complex128
                            )
            y = port_admittance(volts, currents) if nodes[ref] else volts[:, :0, :0]
            ports[ref] = Ports(nodes[ref], y)
        found_sat = saturation(biased, nets, dc.voltages, dc.currents, self.models)
        return Linearised(biased, AcResult(freq, responses, found_sat), main, ports)

    def settling(self, circuit: Circuit) -> Settling:
        """How long `circuit` needs, from switching on, until each cycle repeats the last
        (D-122): coupling caps charged, and a clipping stage's bias moved where the signal
        holds it. Found at a hard pick and `SETTLE_HZ`: the wait is doubled from
        `SETTLE_START_S` until every net has settled by then (`_repeats`), up to
        `MAX_SETTLE_S`; the answer is kept per circuit (`SETTLE_MEMO` circuits). An edited
        circuit (same id) starts at the wait it needed last time (`_settle`)."""
        biased = self._biased(circuit).circuit
        if input_part(biased) is None:
            raise NetlistError("Add a guitar input to the circuit to see its waveforms.")
        wait = SETTLE_START_S
        key = generate_netlist(biased, self.models, _settle_run(wait)).text
        if key not in self._settled:
            if len(self._settled) >= SETTLE_MEMO:
                self._settled.pop(next(iter(self._settled)))
            self._settled[key] = self._settle(biased, self._last_wait.get(circuit.id, wait))
            if len(self._last_wait) >= SETTLE_MEMO and circuit.id not in self._last_wait:
                self._last_wait.pop(next(iter(self._last_wait)))
            self._last_wait[circuit.id] = self._settled[key].seconds or wait
        return self._settled[key]

    def _settle(self, biased: Circuit, wait: float) -> Settling:
        # The search's first run is at `wait`; the shorter waits of the doubling series
        # are checked on that same run (its windows are a prefix of theirs), shortest
        # first, so the answer is the one a search from `SETTLE_START_S` finds.
        # A circuit that makes the simulator take far more steps than the tone needs runs
        # an oscillator of its own (a charge pump): too slow to search, so it's measured
        # after the shortest wait, as before settling was checked, and marked unchecked.
        period = 1 / SETTLE_HZ
        probe = Tran(
            SETTLE_HZ, LEVELS["hard"], STIFF_PROBE_CYCLES * period, period / STEPS_PER_CYCLE
        )
        steps = len(self._run(generate_netlist(biased, self.models, probe), "tran")["time"])
        if steps > STIFF_STEPS * STIFF_PROBE_CYCLES * STEPS_PER_CYCLE:
            return Settling(0.0, None)
        tried = 0.0
        while True:
            netlist = generate_netlist(biased, self.models, _settle_run(wait))
            vectors = self._run(netlist, "tran")
            time = np.asarray(vectors["time"].real, dtype=np.float64)
            waves = [
                np.asarray(vectors[node].real, dtype=np.float64)
                for node in dict.fromkeys(netlist.nodes.values())
                if node != "0" and node in vectors
            ]
            for w in _waits_upto(wait):
                if w > tried and all(_repeats(time, v, w, LEVELS["hard"]) for v in waves):
                    return Settling(w, True)
            if wait >= MAX_SETTLE_S:
                return Settling(wait, False)
            tried, wait = wait, min(2 * wait, MAX_SETTLE_S)

    def tran(
        self, circuit: Circuit, nodes: Sequence[str], level: str | float, tone: float = TONE_HZ
    ) -> TranResult:
        """A sine of `tone` Hz at the guitar input at one pick level (a name in `LEVELS`, or
        its peak in volts: the Bias & headroom pane's level sweep); waveforms and stats at
        `nodes`, measured once the circuit has settled (`settling`)."""
        if isinstance(level, str) and level not in LEVELS:
            raise ValueError(f"Level must be one of {', '.join(LEVELS)} (got {level!r}).")
        if not isinstance(level, str) and not 0 < level <= MAX_AMPLITUDE:
            raise ValueError(f"The input level must be above 0 V and at most {MAX_AMPLITUDE:g} V.")
        amplitude = LEVELS[level] if isinstance(level, str) else float(level)
        name = level if isinstance(level, str) else f"{amplitude:g} V"
        biased = self._biased(circuit).circuit
        guitar = input_part(biased)
        if guitar is None:
            raise NetlistError("Add a guitar input to the circuit to see its waveforms.")
        nets = connect(biased)
        source = nets.net_of(guitar.ref, "out")
        wanted = [nets.resolve(n) for n in nodes]
        for net in wanted:
            require_wired(biased, nets, net)
        settle = self.settling(circuit)
        wait = max(SETTLE_CYCLES, math.ceil(settle.seconds * tone - 1e-9))
        # Every node is recorded, whichever are asked for, and only the cycles measured
        # (and one before): the run is the same for any `nodes`, so the scope at another
        # net, a part's view and the Bias & headroom pane all read this one run (D-277).
        analysis = Tran(
            freq=tone,
            amplitude=amplitude,
            stop=(wait + MEASURE_CYCLES) / tone,
            max_step=1 / (tone * STEPS_PER_CYCLE),
            keep_from=(wait - 1) / tone,
        )
        early = wait - SETTLE_CYCLES  # cycles of the wait that can go by at coarse steps
        state = self._waited(biased, nets, analysis, early) if early >= WAIT_WORTH else None
        if state is not None:
            analysis = replace(
                analysis,
                stop=(SETTLE_CYCLES + MEASURE_CYCLES) / tone,
                keep_from=(SETTLE_CYCLES - 1) / tone,
                state=state[0],
                coil_amps=state[1],
            )
        netlist = generate_netlist(biased, self.models, analysis, nets)
        vectors = self._run(netlist, "tran")
        time = np.asarray(vectors["time"].real, dtype=np.float64)

        def wave(net: str) -> Array:
            node = netlist.node(net)
            return np.zeros_like(time) if node == "0" else np.asarray(vectors[node].real)

        waves = {net: wave(net) for net in dict.fromkeys([source, *wanted])}
        stats = {
            net: node_stats(time, waves[net], waves[source], tone, MEASURE_CYCLES) for net in wanted
        }
        return TranResult(name, amplitude, tone, time, source, waves, stats, settle.settled)

    def _waited(
        self, biased: Circuit, nets: Nets, measured: Tran, cycles: int
    ) -> tuple[tuple[tuple[str, float], ...], tuple[tuple[str, float], ...]] | None:
        """Where the circuit stands after `cycles` of `measured`'s tone, run at
        `WAIT_STEPS_PER_CYCLE`: every node's volts and every inductor's amps at the last
        point, for `Tran.state` and `Tran.coil_amps` (D-275). The wait only has to carry
        the slow things to where they settle (coupling caps, a bias moved by clipping),
        which coarse steps do: handed on, the measuring run's fine cycles land within a
        fraction of a percent of one fine run all the way. None if the state can't be
        handed on whole (an inductor inside a model, whose current can't be set)."""
        step = 1 / (measured.freq * WAIT_STEPS_PER_CYCLE)
        stop = cycles / measured.freq
        wait = replace(measured, stop=stop, max_step=step, keep_from=stop - step / 2)
        netlist = generate_netlist(biased, self.models, wait, nets)
        vectors = self._run(netlist, "tran")
        coils = {e.tokens[0].lower() for e in netlist.elements if e.tokens[0][:1] in "Ll"}
        volts, amps = [], []
        for name, vector in vectors.items():
            last = float(vector[-1].real)
            ref, _, branch = name.partition("#")
            if branch:
                if ref.startswith("l"):
                    if ref not in coils:
                        return None
                    amps.append((ref, last))
            elif name != "time" and not name.startswith("@"):
                volts.append((name, last))
        return tuple(sorted(volts)), tuple(sorted(amps))

    def recording_netlist(
        self, circuit: Circuit, source_file: str, gain: float, seconds: float, rate: int,
        nets: Sequence[str], pump_ripple: bool = True,
    ) -> Netlist:  # fmt: skip
        """The netlist `recording` runs (its text is what a render's cache key covers);
        `pump_ripple` False runs charge pumps at their average (`Tran.pump_ripple`)."""
        biased = self._biased(circuit).circuit
        nets_of = connect(biased)
        wanted = tuple(dict.fromkeys(nets_of.resolve(n) for n in nets))
        analysis = Tran(0, 0, seconds, 1 / rate, wanted, source_file, gain, pump_ripple)
        return generate_netlist(biased, self.models, analysis, nets_of)

    def recording(
        self,
        circuit: Circuit,
        source_file: str,
        gain: float,
        seconds: float,
        rate: int,
        nets: Sequence[str],
        progress: Callable[[float], None] | None = None,
        pump_ripple: bool = True,
    ) -> tuple[Array, dict[str, Array]]:
        """The guitar playing a recording (`Tran.source_file`, scaled by `gain`) for
        `seconds`, at most one step per `1 / rate`: the solver's time points and the volts
        at `nets` (names or pins, keyed as given). The audio renderer puts them on a
        regular grid."""
        netlist = self.recording_netlist(
            circuit, source_file, gain, seconds, rate, nets, pump_ripple
        )
        vectors = self._run(netlist, "tran", recording_limit(seconds), progress)
        time = np.asarray(vectors["time"].real, dtype=np.float64)
        nets_of = connect(circuit)

        def wave(name: str) -> Array:
            node = netlist.node(nets_of.resolve(name))
            return np.zeros_like(time) if node == "0" else np.asarray(vectors[node].real)

        return time, {name: wave(name) for name in nets}

    def sweep(self, circuit: Circuit, analysis: Dc) -> SweepResult:
        """A DC sweep of one source: node voltages and every source's current per step."""
        biased = self._biased(circuit).circuit
        netlist = generate_netlist(biased, self.models, analysis)
        vectors = self._run(netlist, "dc")
        steps = np.asarray(vectors["v-sweep"].real, dtype=np.float64)
        voltages = {
            net: np.zeros_like(steps) if node == "0" else np.asarray(vectors[node].real)
            for net, node in netlist.nodes.items()
            if node == "0" or node in vectors
        }
        currents = {
            p.ref: -np.asarray(vectors[f"{element_name('V', p.ref).lower()}#branch"].real)
            for p in biased.parts
            if isinstance(p, VSource)
        }
        return SweepResult(steps, voltages, currents)


def _ac_vectors(
    vectors: Mapping[str, npt.NDArray[np.generic]], netlist: Netlist
) -> tuple[Array, dict[str, Complex]]:
    """Frequencies and the response at every net the run saw."""
    freq = np.asarray(vectors["frequency"].real, dtype=np.float64)
    zero = np.zeros_like(freq, dtype=np.complex128)
    responses = {
        net: zero if node == "0" else np.asarray(vectors[node], dtype=np.complex128)
        for net, node in netlist.nodes.items()
        if node == "0" or node in vectors
    }
    return freq, responses


def simulator_from_settings(
    settings: Settings, engine: SimEngine | None = None, cache: SimCache | None = None
) -> Simulator:
    """The app's simulator: cached engine (`engine`, or the one the settings pick; in
    `cache`, or the settings' own), user models layered over core ones (D-011)."""
    return Simulator(
        CachedEngine(
            engine or engine_from_settings(settings), cache or cache_from_settings(settings)
        ),
        model_library(settings),
    )


def model_library(settings: Settings) -> ModelLibrary:
    """User models (`DATA_DIR/models`) over core ones (`library/models`), D-011."""
    model_dirs = [settings.data_dir / "models", settings.library_dir / "models"]
    return load_models([d for d in model_dirs if d.is_dir()])


def _waits_upto(wait: float) -> list[float]:
    """The settle search's waits up to `wait`, shortest first: `SETTLE_START_S` doubled,
    the last one capped at `MAX_SETTLE_S`."""
    waits = [SETTLE_START_S]
    while waits[-1] < wait - 1e-12:
        waits.append(min(2 * waits[-1], MAX_SETTLE_S))
    return waits


def _settle_run(wait: float) -> Tran:
    """The settle search's run: a hard pick at `SETTLE_HZ`, four times `wait` plus a
    window, so the windows after `wait`, twice it and four times it are all in it. At the
    wait's coarse steps (D-275): the search compares harmonics 1 to 8 between windows,
    which 100 steps a cycle carry, and it is most of a first run's time."""
    period = 1 / SETTLE_HZ
    return Tran(
        freq=SETTLE_HZ,
        amplitude=LEVELS["hard"],
        stop=4 * wait + MEASURE_CYCLES * period,
        max_step=period / WAIT_STEPS_PER_CYCLE,
    )


def _repeats(time: Array, wave: Array, wait: float, amplitude: float) -> bool:
    """Whether `wave` has settled by `wait`: from the window after `wait` to the one
    after twice it, and from there to the one after four times it, its harmonics
    (1 to 8, as `node_stats` reads them) change by less than `SETTLE_TOLERANCE` of
    their size (at least `SETTLE_FLOOR` of the guitar's peak, `amplitude`), counting
    the drift still to come: a second change the same way as the first is a drift, and
    if each doubling shrinks it by the same factor, the change left from `wait` on is
    the sum of that series; one that doesn't shrink hasn't settled (a drift too slow to
    see in one doubling grows with each). Changes that turn back are jitter, not drift;
    changes both under `SETTLE_NOISE` count as settled.

    Harmonics, not the highest and lowest points: they are averages over the window,
    so a cap after a clipped stage, turning each edge into a spike whose top depends on
    where the steps land (the Big Muff's tone stack), barely moves them, while a bias
    shifting with the signal changes the even ones. Drift is taken out first, as
    `node_stats` does, so a net's DC wandering slowly (a reference rail's big cap)
    isn't counted."""

    def harmonics(start: float) -> Array:
        end = start + MEASURE_CYCLES / SETTLE_HZ
        upto = time <= end + 1e-12
        v = detrend(last_cycles(time[upto], wave[upto], SETTLE_HZ, MEASURE_CYCLES), MEASURE_CYCLES)
        return spectrum(v, MEASURE_CYCLES)[0]

    first, second, last = harmonics(wait), harmonics(2 * wait), harmonics(4 * wait)
    size = max(float(np.linalg.norm(last)), SETTLE_FLOOR * amplitude)
    early, late = (second - first) / size, (last - second) / size
    e, la = float(np.linalg.norm(early)), float(np.linalg.norm(late))
    if max(e, la) <= SETTLE_NOISE:
        return True
    if float(np.dot(early, late)) <= 0:  # turned back: jitter
        return max(e, la) <= SETTLE_TOLERANCE
    shrink = la / e if e > 0 else math.inf
    # still drifting: each change shrinking by `shrink`, what's left adds up to this
    return shrink < 1 and e + la / (1 - shrink) <= SETTLE_TOLERANCE
