"""Rule files: one YAML file per rule in `library/rules/` (SPEC §4, D-013, D-077).

A rule says what to tell the user (message, why, fix: plain English, filled in from what
its check found) and names its check (a function in `solum.rules.checks`). Its fixtures
are small circuits it must fire on (`bad`) and stay quiet on (`good`), written in the
circuit builder's terms (`CircuitBuilder.from_spec`), so each rule is one file to review.
"""

import string
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from solum.yamlio import YamlError, load_yaml

Layer = Literal["topology", "operating_point", "sim_error"]
Severity = Literal["error", "warning", "info"]
LAYERS: tuple[Layer, ...] = ("topology", "operating_point", "sim_error")
SEVERITIES: tuple[Severity, ...] = ("error", "warning", "info")


class RuleError(ValueError):
    """A rule file is unreadable or invalid (plain-English message)."""


class Fixtures(BaseModel):
    """Circuits (builder specs) the rule must fire on (`bad`) and stay quiet on (`good`).
    A `sim_error` rule's fixture may instead be `{log: [ngspice lines], nodes: {...}}`."""

    model_config = ConfigDict(extra="forbid")

    bad: list[dict[str, Any]] = Field(min_length=1)
    good: list[dict[str, Any]] = Field(min_length=1)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    layer: Layer
    severity: Severity
    check: str
    # Topology rules only: when it fires, the circuit isn't simulated (ngspice would fail)
    stops_sim: bool = False
    # sim_error rules only: used when no other sim_error rule explains the failure
    fallback: bool = False
    # A build check (9d1, D-203): also listed in File → Export's "Ready to build"
    build: bool = False
    title: str  # a few words for the Problems list ("No feedback")
    message: str  # names the part: "{ref} has no feedback..."
    why: str
    fix: str
    fixtures: Fixtures

    @model_validator(mode="after")
    def _layer_fields(self) -> "Rule":
        if self.stops_sim and self.layer != "topology":
            raise ValueError("only topology rules can stop the simulation (stops_sim)")
        if self.fallback and self.layer != "sim_error":
            raise ValueError("only sim_error rules can be the fallback")
        return self

    def fields(self) -> set[str]:
        """The `{names}` its texts fill in."""
        found = set()
        for text in (self.title, self.message, self.why, self.fix):
            found |= {name for _, name, _, _ in string.Formatter().parse(text) if name}
        return found

    def text(
        self, which: Literal["title", "message", "why", "fix"], values: Mapping[str, str]
    ) -> str:
        return " ".join(getattr(self, which).format_map(dict(values)).split())


@dataclass(frozen=True)
class RuleBook:
    rules: tuple[Rule, ...]

    def layer(self, layer: Layer) -> list[Rule]:
        return [r for r in self.rules if r.layer == layer]

    def get(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(f"No rule {rule_id!r}.")


def load_rule(path: Path) -> Rule:
    try:
        data = load_yaml(path)
    except YamlError as err:
        raise RuleError(str(err)) from None
    if not isinstance(data, dict):
        raise RuleError(f"{path} should hold one rule (a YAML mapping).")
    try:
        rule = Rule.model_validate(data)
    except ValidationError as err:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in err.errors())
        raise RuleError(f"{path.name}: {problems}") from None
    if rule.id != path.stem:
        raise RuleError(
            f"{path.name}: its id is {rule.id!r}; the file must be named {rule.id}.yaml."
        )
    return rule


def load_rules(directory: Path) -> RuleBook:
    """Every `*.yaml` rule in `directory`, sorted by id so runs are deterministic."""
    rules = [load_rule(path) for path in sorted(directory.glob("*.yaml"))]
    return RuleBook(tuple(sorted(rules, key=lambda r: r.id)))
