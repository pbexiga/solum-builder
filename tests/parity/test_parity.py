"""The in-browser solver (`web/solver.js`) against ngspice `.ac`, within 0.1 dB (D-012):
every starter, every core block with signal ports (in a jig), and slider steps, i.e. the
curve the editor draws while a value slider or knob moves (D-081)."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from playwright.sync_api import Page

from solum.analysis.measures import to_db
from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.linear import branches, system_data
from solum.live import live_view
from solum.models import load_models
from solum.sim.native import NativeNgspice
from solum.simulate import Simulator
from solum.units import format_value, parse_value
from tests.jig import jig, with_values
from tests.ui.conftest import run

REPO = Path(__file__).parents[2]
TOLERANCE_DB = 0.1  # D-012
STARTERS = sorted((REPO / "library" / "starters").glob("*.json"))
BLOCKS = [
    p
    for p in sorted((REPO / "library" / "blocks").glob("*.json"))
    if {"in", "out"} <= set(load_circuit(p).ports)
]


@pytest.fixture(scope="module")
def sim(engine: NativeNgspice) -> Simulator:
    return Simulator(engine, load_models([REPO / "library" / "models"]))


def solve(page: Page, system: dict[str, Any], values: dict[str, float] | None = None) -> Any:
    """`solve(system, values)` in the browser, as the app serves `solver.js`."""
    re, im = run(
        page,
        "const s = await m('solver.js'); const h = s.solve(arg[0], arg[1]);"
        "return [Array.from(h.re), Array.from(h.im)];",
        [system, values or {}],
    )
    return np.asarray(re) + 1j * np.asarray(im)


def worst_db(page: Page, sim: Simulator, circuit: Circuit) -> float:
    lin = sim.linearise(circuit)
    out = circuit.probes.out
    assert out is not None
    found = branches(lin.netlist.elements, lin.ports)
    system = system_data(found, lin.ac.freq.tolist(), lin.netlist.node(out))
    ours = solve(page, system)
    return float(np.abs(to_db(ours) - to_db(lin.ac.responses[out])).max())


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_starters(js: Page, sim: Simulator, path: Path) -> None:
    assert worst_db(js, sim, load_circuit(path)) < TOLERANCE_DB


@pytest.mark.parametrize("path", BLOCKS, ids=lambda p: p.stem)
def test_core_blocks_in_a_jig(js: Page, sim: Simulator, path: Path) -> None:
    assert worst_db(js, sim, jig(load_circuit(path), 1e3, 1e6)) < TOLERANCE_DB


def step_parity(page: Page, sim: Simulator, block: Circuit, ref: str, field: str) -> float:
    """Move one slider a few steps in the browser (the step's element values only) and
    compare with ngspice run on the block with that value."""
    circuit = jig(block, 1e3, 1e6)
    out = circuit.probes.out
    assert out is not None
    view = live_view(sim, circuit, [out], [(ref, field)])  # type: ignore[list-item]
    [slider] = view["sliders"]
    system = {**view["system"], "out": view["nets"][out]}
    worst = 0.0
    for i in (0, len(slider["steps"]) // 3, len(slider["steps"]) - 1):
        step = slider["steps"][i]
        ours = solve(page, system, step["elements"])
        changed = jig(with_values(block, {ref: {field: step["value"]}}), 1e3, 1e6)
        theirs = sim.ac(changed).responses[out]
        worst = max(worst, float(np.abs(to_db(ours) - to_db(theirs)).max()))
    return worst


def test_tone_stack_knobs_and_values(js: Page, sim: Simulator) -> None:
    tmb = load_circuit(REPO / "library" / "blocks" / "fender-tmb-v1.json")
    for ref, field in (("VR1", "rotation"), ("VR3", "rotation"), ("C2", "value"),
                       ("VR2", "value")):  # fmt: skip
        assert step_parity(js, sim, tmb, ref, field) < 1e-3, (ref, field)


def test_gain_resistor_on_an_op_amp_stage(js: Page, sim: Simulator) -> None:
    """The op-amp's admittance was measured at the old values; a feedback resistor moves
    its operating point very little, so the live curve stays within tolerance until ngspice
    re-runs when the slider is let go."""
    stage = load_circuit(REPO / "library" / "blocks" / "opamp-noninv-stage-v1.json")
    feedback = next(r for r in ("R2", "R3") if r in {p.ref for p in stage.parts})
    assert step_parity(js, sim, stage, feedback, "value") < TOLERANCE_DB


# ---- part influence (Phase 8b, D-097): nudged curves vs ngspice with the part changed ----


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_influence_numbers_match_ngspice(js: Page, sim: Simulator, path: Path) -> None:
    """Each part's change to the output curve, solved in the browser (`nudgedCurves`) and
    from a full ngspice run with the part +10 %. Parts that carry no DC (capacitors, signal
    resistors) agree within D-012's 0.1 dB; a part that sets a bias also moves the operating
    point, which the live solver holds fixed (D-079), so for those only the parts' ranking
    is compared loosely: they're marked "sets bias" in the list."""
    circuit = load_circuit(path)
    out = circuit.probes.out
    assert out is not None
    view = live_view(sim, circuit, [out], [], nudge=True)
    curves = run(
        js, "const L = await m('layers.js'); return L.nudgedCurves(arg[0], arg[1]);", [view, out]
    )
    base = np.asarray(curves["base"])
    assert np.abs(base - to_db(sim.ac(circuit).responses[out])).max() < TOLERANCE_DB
    checked = 0
    for nudge in view["nudges"]:
        if nudge["bias"]:
            continue
        part = circuit.part(nudge["ref"])
        value = format_value(parse_value(part.value) * 1.1, 6)  # type: ignore[union-attr]
        theirs = to_db(sim.ac(circuit.with_part(part.ref, value=value)).responses[out])
        ours = np.asarray(curves["nudged"][part.ref])
        assert np.abs(ours - theirs).max() < TOLERANCE_DB, part.ref
        checked += 1
    assert checked >= 4  # the Fuzz Face has only four parts that carry no DC


def test_an_inductor_tank_and_its_slider(js: Page, sim: Simulator) -> None:
    """D-173: a red Fasel (666 mH, 15.65 Ω) across 10 nF fed through 10 kΩ, a wah's tank
    (resonance near 1/(2π√(LC)) = 1.95 kHz), and its value slider's steps."""
    tank = (
        CircuitBuilder("tank")
        .part("IN", "guitar", "in")
        .part("R1", "resistor", "in", "t", value="10k")
        .part("L1", "inductor", "t", "0", value="666m", resistance=15.65)
        .part("C1", "capacitor", "t", "0", value="10n")
        .part("OUT", "amp", "t")
        .probe("in", "t")
        .build()
    )
    assert worst_db(js, sim, tank) < TOLERANCE_DB
    view = live_view(sim, tank, ["t"], [("L1", "value")])
    [slider] = view["sliders"]
    system = {**view["system"], "out": view["nets"]["t"]}
    for i in (0, len(slider["steps"]) // 2, len(slider["steps"]) - 1):
        step = slider["steps"][i]
        ours = solve(js, system, step["elements"])
        theirs = sim.ac(with_values(tank, {"L1": {"value": step["value"]}})).responses["t"]
        assert float(np.abs(to_db(ours) - to_db(theirs)).max()) < TOLERANCE_DB, step["text"]


def test_a_mosfet_common_source_stage(js: Page, sim: Simulator) -> None:
    """D-175: a 2N7000 amplifying (gate 3 V from a divider, 1k in the source bypassed by
    10 µF, 4k7 to 9 V on the drain): its capacitances and gm as ngspice linearises them."""
    stage = (
        CircuitBuilder("mosfet cs")
        .rail("V+", 9.0)
        .part("IN", "guitar", "in")
        .part("C1", "capacitor", "in", "g", value="100n")
        .part("R1", "resistor", "V+", "g", value="2M")
        .part("R2", "resistor", "g", "0", value="1M")
        .part("R3", "resistor", "V+", "d", value="4k7")
        .part("R4", "resistor", "s", "0", value="1k")
        .part("C2", "capacitor", "s", "0", value="10u")
        .part("Q1", "mosfet", "d", "g", "s", model="2N7000")
        .part("C3", "capacitor", "d", "out", value="1u")
        .part("OUT", "amp", "out")
        .probe("in", "out")
        .build()
    )
    assert worst_db(js, sim, stage) < TOLERANCE_DB
    assert sim.ac(stage).saturated == []  # amplifying, not fully on
