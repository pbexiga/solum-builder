"""Running the rules: topology before simulating, operating point after `.op`, and the
ngspice error layer when a run fails (SPEC §4, D-077)."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from solum.bias import BiasError
from solum.circuit.connectivity import ConnectivityError, connect
from solum.circuit.schema import SCHEMA_VERSION, Circuit
from solum.models import ModelError, ModelLibrary
from solum.netlist import NetlistError
from solum.rules.checks import CHECKS, Context, Hit
from solum.rules.rule import SEVERITIES, Layer, Rule, RuleBook, RuleError, Severity, load_rules
from solum.sim.engine import SimError
from solum.simulate import Simulator

# What a failed run can raise; each becomes a problem, never a traceback.
RUN_ERRORS = (SimError, BiasError, NetlistError, ModelError, ConnectivityError)


class CantSimulate(ValueError):
    """The drawing has a problem that stops simulation (`str(err)` is its message)."""

    def __init__(self, problems: list["Problem"]) -> None:
        super().__init__(problems[0].message)
        self.problems = problems


@dataclass(frozen=True)
class Problem:
    """One problem for the Problems panel: plain English, and what to highlight."""

    rule: str
    layer: Layer
    severity: Severity
    title: str
    message: str
    why: str
    fix: str
    refs: tuple[str, ...]
    nets: tuple[str, ...]
    build: bool = False  # also in Export's "Ready to build" list (D-203)


def problem(rule: Rule, hit: Hit) -> Problem:
    values = {"ref": hit.ref or "", **hit.values}
    return Problem(
        rule=rule.id,
        layer=rule.layer,
        severity=rule.severity,
        title=rule.text("title", values),
        message=rule.text("message", values),
        why=rule.text("why", values),
        fix=rule.text("fix", values),
        refs=((hit.ref,) if hit.ref else ()) + hit.refs,
        nets=hit.nets,
        build=rule.build,
    )


def check_book(book: RuleBook) -> RuleBook:
    """The book, after checking each rule names a check of its own layer."""
    for rule in book.rules:
        if rule.check not in CHECKS:
            raise RuleError(f"{rule.id}.yaml names check {rule.check!r}, which doesn't exist.")
        if CHECKS[rule.check][0] != rule.layer:
            raise RuleError(
                f"{rule.id}.yaml is a {rule.layer} rule, but {rule.check} is a "
                f"{CHECKS[rule.check][0]} check."
            )
    return book


def rule_book(library_dir: Path) -> RuleBook:
    """The app's rules: `library/rules/*.yaml`, checked against the registry."""
    return check_book(load_rules(library_dir / "rules"))


def _order(problems: Iterable[Problem]) -> list[Problem]:
    """Errors first, then warnings, then notes; otherwise in rule order."""
    return sorted(problems, key=lambda p: SEVERITIES.index(p.severity))


class Checker:
    """Runs a rule book over circuits."""

    def __init__(self, book: RuleBook, models: ModelLibrary) -> None:
        self.book = book
        self.models = models

    def _run(self, layer: Layer, ctx: Context) -> list[Problem]:
        found = []
        for rule in self.book.layer(layer):
            if layer == "sim_error" and rule.fallback:
                continue
            found += [problem(rule, hit) for hit in CHECKS[rule.check][1](ctx)]
        return found

    def context(self, circuit: Circuit) -> Context:
        try:
            return Context(circuit, self.models, connect(circuit))
        except ConnectivityError as err:
            return Context(circuit, self.models, None, wiring_error=err)

    def topology(self, circuit: Circuit) -> list[Problem]:
        """Problems visible in the drawing alone (no simulation)."""
        ctx = self.context(circuit)
        if ctx.nets is None:  # only the wiring rule can look at contradictory wiring
            rules = [r for r in self.book.layer("topology") if r.check == "labels_joined"]
            return [problem(r, hit) for r in rules for hit in CHECKS[r.check][1](ctx)]
        return self._run("topology", ctx)

    def explain(self, err: Exception) -> list[Problem]:
        """A failed run in plain English (`SimError.nodes`, set by `Simulator`, maps
        ngspice's node names back to nets)."""
        net_of = {node: net for net, node in err.nodes.items()} if isinstance(err, SimError) else {}
        # the error rules look only at the error, so the circuit is a stand-in
        blank = Circuit.model_construct(schema_=SCHEMA_VERSION, id="error", name="", parts=[])
        ctx = Context(blank, self.models, None, error=err, nodes=net_of)
        found = self._run("sim_error", ctx)
        if not found:
            found = [problem(r, hit) for r in self.book.layer("sim_error") if r.fallback
                     for hit in CHECKS[r.check][1](ctx)]  # fmt: skip
        return found

    def stoppers(self, circuit: Circuit) -> list[Problem]:
        """Topology problems that stop a simulation (no DC path, an unpowered op-amp...)."""
        return [p for p in self.topology(circuit) if self.book.get(p.rule).stops_sim]

    def require_runnable(self, circuit: Circuit) -> None:
        """CantSimulate if the drawing can't be simulated. Run before every simulation:
        on a floating net ngspice may fall back and report a meaningless 0 V."""
        stoppers = self.stoppers(circuit)
        if stoppers:
            raise CantSimulate(stoppers)

    def message(self, err: Exception) -> str:
        """The one line to show for a failed run: the first problem's message."""
        found = self.explain(err)
        return found[0].message if found else str(err)

    def check(self, circuit: Circuit, sim: Simulator | None) -> tuple[list[Problem], bool]:
        """Every problem: topology, then (unless one of those stops it, there's no
        simulator, or it's a block) a `.op` and its operating-point rules, or the failed
        run explained.
        Also says whether the operating point was checked."""
        found = self.topology(circuit)
        stopped = any(self.book.get(p.rule).stops_sim for p in found)
        if stopped or sim is None or circuit.template:  # a block's DC depends on its host
            return _order(found), False
        ctx = self.context(circuit)
        try:
            ctx.op = sim.op(circuit)
        except RUN_ERRORS as err:
            return _order(found + self.explain(err)), False
        return _order(found + self._run("operating_point", ctx)), True
