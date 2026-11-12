"""The known-good corpus and the mutation test (D-013, D-077).

Corpus: every starter (the acceptance circuits) and every core block has no problems at
all, but for the warnings `corpus_warnings.yaml` lists with the reason the real circuit
raises them (D-135). Mutations: each scripted breakage of a starter must make a new
problem appear, or be listed in `mutation_gaps.yaml` with the reason no rule can see it.
On every mutated circuit, the no-DC-path rule must fire whenever ngspice warns of a
singular matrix.
"""

import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path

import pytest

from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.models import load_models
from solum.netlist import Op, generate_netlist
from solum.rules.run import Checker, rule_book
from solum.sim.engine import SimError
from solum.sim.native import native_engine
from solum.simulate import Simulator
from solum.yamlio import load_yaml
from tests.rules.conftest import LIBRARY
from tests.rules.mutations import Mutation, mutations

STARTERS = sorted((LIBRARY / "starters").glob("*.json"))
BLOCKS = sorted((LIBRARY / "blocks").glob("*.json"))
GAPS = Path(__file__).with_name("mutation_gaps.yaml")
WARNINGS = Path(__file__).with_name("corpus_warnings.yaml")


@cache
def _tools() -> tuple[Checker, Simulator]:
    models = load_models([LIBRARY / "models"])
    return Checker(rule_book(LIBRARY), models), Simulator(native_engine(), models)


def allowed() -> dict[str, set[str]]:
    """Starter id → the warnings it may raise (each listed with its reason)."""
    out: dict[str, set[str]] = {}
    for w in load_yaml(WARNINGS) or []:
        assert w["reason"].strip()
        out.setdefault(w["circuit"], set()).add(w["rule"])
    return out


def _found(circuit: Circuit) -> set[tuple[str, tuple[str, ...]]]:
    """Each problem as its rule and the parts it names: a mutation that makes a rule the
    circuit already raises fire on another part (a second transistor cut off) is noticed."""
    checker, sim = _tools()
    return {(p.rule, p.refs) for p in checker.check(circuit, sim)[0]}


def _rules(circuit: Circuit) -> set[str]:
    return {rule for rule, _ in _found(circuit)}


@cache
def results(path: Path) -> dict[tuple[str, str], tuple[Mutation, set[str]]]:
    """One starter's (starter id, mutation key) → the mutation and the rules it newly
    fires (on a part they didn't name before). A starter at a time, so the tests that
    read them run side by side (Phase 10: one test of all 19 took 55 s)."""
    base = load_circuit(path)
    before = _found(base)
    return {
        (base.id, m.key): (m, {rule for rule, _ in _found(m.circuit) - before})
        for m in mutations(base)
    }


def explained() -> dict[tuple[str, str], str]:
    data = load_yaml(GAPS) or []
    return {(g["circuit"], g["mutation"]): g["reason"] for g in data}


def report() -> Iterator[str]:
    reasons = explained()
    found = {k: v for path in STARTERS for k, v in results(path).items()}
    for (cid, key), (_, fired) in sorted(found.items()):
        note = ", ".join(sorted(fired)) or f"GAP: {reasons.get((cid, key), 'unexplained')}"
        yield f"{cid:16} {key:24} {note}"


@pytest.mark.parametrize("path", STARTERS + BLOCKS, ids=lambda p: p.stem)
def test_corpus_has_no_problems(path: Path) -> None:
    circuit = load_circuit(path)
    expected = allowed().get(circuit.id, set())
    assert _rules(circuit) == expected
    book = _tools()[0].book
    assert all(book.get(r).severity == "warning" for r in expected)


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_every_mutation_is_noticed_or_explained(path: Path) -> None:
    found = results(path)
    cid = load_circuit(path).id
    gaps = {k for k, (_, fired) in found.items() if not fired}
    reasons = {k: why for k, why in explained().items() if k[0] == cid}
    unexplained = sorted(gaps - set(reasons))
    stale = sorted(set(reasons) - gaps)
    assert not unexplained, f"mutations no rule notices: {unexplained}"
    assert not stale, f"listed as gaps but now noticed (remove them): {stale}"
    assert all(r.strip() for r in reasons.values())


def test_every_listed_gap_is_a_starters() -> None:
    starters = {load_circuit(path).id for path in STARTERS}
    assert {cid for cid, _ in explained()} <= starters


def test_mutations_cover_every_operator() -> None:
    kinds = {m.kind for path in STARTERS for m in mutations(load_circuit(path))}
    assert kinds == {"remove-part", "lift-pin", "reverse", "swap-supply"}


def _singular(circuit: Circuit) -> bool | None:
    """Did ngspice warn of a singular matrix? On a floating net it does, then often falls
    back to a transient operating point and reports 0 V there, so the warning is the
    signal, whether or not the run fails. None if no netlist can be made."""
    checker, sim = _tools()
    try:
        netlist = generate_netlist(circuit, checker.models, Op())
    except ValueError:  # netlist or connectivity: not a matrix question
        return None
    try:
        log = sim.engine.run(netlist.text).log
    except SimError as err:
        log = err.log
    return any(_floating(line) for line in log)


INSIDE_MODEL = re.compile(r"^(?:\w\.)?x_[^.\s]+\.")  # v.x_ic1b.vlp#branch: a subcircuit's own


def _floating(line: str) -> bool:
    """A singular-matrix warning that names a node of the circuit. One naming only a
    model's inner nodes is the model failing to converge, not a floating net: TI's TL072
    macromodel's current limiter on a reversed supply (the Klon's IC1C swapped, D-218),
    which opamp-supply-reversed catches."""
    if "singular matrix" not in line:
        return False
    nodes = line.split("check nodes", 1)[-1].replace(" and ", " ").split()
    return not nodes or any(not INSIDE_MODEL.match(n) for n in nodes)


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_no_dc_path_rule_catches_what_ngspice_warns_about(path: Path) -> None:
    """Whenever ngspice warns of a singular matrix, the rule fired first. The rule also
    catches some islands ngspice misses: a group of resistors joined to the rest only
    through capacitors (lifting the TS808's VR3.1) gets an arbitrary voltage, no warning.
    The mutations alone, not what the rules make of them: no `results` to wait for."""
    checker, _ = _tools()
    missed = [
        f"{path.stem} {m.key}"
        for m in mutations(load_circuit(path))
        if _singular(m.circuit)
        and not any(p.rule == "no-dc-path" for p in checker.topology(m.circuit))
    ]
    assert not missed
