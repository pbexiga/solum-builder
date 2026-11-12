"""Shared pieces for the rule tests: the app's rule book, a simulator, and turning a rule
fixture (builder spec, `starter:` or a sim-error `log:`) into what the checker takes."""

from pathlib import Path
from typing import Any

import pytest

from solum.circuit.build import CircuitBuilder
from solum.circuit.io import load_circuit
from solum.circuit.schema import Circuit
from solum.models import ModelLibrary, load_models
from solum.rules.rule import RuleBook
from solum.rules.run import Checker, Problem, rule_book
from solum.sim.engine import SimError
from solum.sim.native import native_engine
from solum.simulate import Simulator

LIBRARY = Path(__file__).resolve().parents[2] / "library"
# test-only models the library no longer has (a pump with no package, for part-no-package)
RULE_MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "rule-models"


@pytest.fixture(scope="session")
def models() -> ModelLibrary:
    return load_models([LIBRARY / "models", RULE_MODELS])


@pytest.fixture(scope="session")
def book() -> RuleBook:
    return rule_book(LIBRARY)


@pytest.fixture(scope="session")
def checker(book: RuleBook, models: ModelLibrary) -> Checker:
    return Checker(book, models)


@pytest.fixture(scope="session")
def sim(models: ModelLibrary) -> Simulator:
    return Simulator(native_engine(), models)


def fixture_circuit(spec: dict[str, Any]) -> Circuit:
    """A rule fixture as a circuit: a starter by id, or a builder spec."""
    if "starter" in spec:
        return load_circuit(LIBRARY / "starters" / f"{spec['starter']}.json")
    return CircuitBuilder.from_spec({k: v for k, v in spec.items() if k != "expect"}).build()


def fixture_problems(spec: dict[str, Any], checker: Checker, sim: Simulator) -> list[Problem]:
    """Every problem the checker finds for a fixture. A `log:` fixture is a failed run."""
    if "log" in spec:
        err = SimError(spec.get("message", "The simulation failed."), spec["log"])
        err.nodes = {net: node for net, node in spec.get("nodes", {}).items()}
        return checker.explain(err)
    return checker.check(fixture_circuit(spec), sim)[0]
