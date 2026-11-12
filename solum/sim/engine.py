"""The `SimEngine` interface, its result types, and the engine for the settings.

Every engine takes a complete SPICE netlist (title line first, analyses as dot
commands, `.end` last) and returns one `Plot` per analysis that ran.

ngspice runs analyses in its own order, not the netlist's, and repeated analyses
of one kind come back in an unreliable order. So a netlist may hold at most one
analysis of each kind, and results are looked up by kind: `SimResult.plot("ac")`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import numpy.typing as npt

from solum.config import Settings

ANALYSIS_LINE = re.compile(r"\s*\.(op|ac|dc|tran|noise|tf|disto|pz|sens|four)\b", re.I)

Vector = npt.NDArray[np.float64] | npt.NDArray[np.complex128]


class SimError(Exception):
    """A simulation failed. `str(err)` is plain English; `log` holds raw ngspice lines;
    `nodes` (net → SPICE node, set by `Simulator`) lets the error rules name nets."""

    def __init__(
        self, message: str, log: list[str] | None = None, nodes: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.log = log or []
        self.nodes = nodes or {}


class SimTimeout(SimError):
    """A run took longer than its limit (`seconds`) and was stopped."""

    def __init__(self, message: str, seconds: float, log: list[str] | None = None) -> None:
        super().__init__(message, log)
        self.seconds = seconds


class EngineStuck(SimError):
    """The engine is spinning in a solve that ignores a halt (D-195, D-279): this run is
    lost and so is every later one, until the app is restarted."""


SINGULAR_NODE = re.compile(r"singular matrix:\s+check node (\S+)", re.I)


def singular_nodes(log: list[str]) -> list[str]:
    """Nodes ngspice named when its matrix was singular (usually no DC path to ground),
    each once, in the order reported."""
    return list(dict.fromkeys(m[1] for line in log if (m := SINGULAR_NODE.search(line))))


class EngineUnavailable(SimError):
    """No simulator could be started (library missing, or mode not built yet)."""


@dataclass(frozen=True)
class Plot:
    """One analysis result. `name` is ngspice's plot name (`op1`, `ac1`, `tran1`)."""

    name: str
    vectors: dict[str, Vector]

    @property
    def kind(self) -> str:
        """Analysis kind without the counter: `op`, `ac`, `tran`, `dc`, ..."""
        return self.name.rstrip("0123456789")


@dataclass(frozen=True)
class SimResult:
    plots: list[Plot]
    log: list[str] = field(default_factory=list)

    def plot(self, kind: str) -> Plot:
        """The result of the `kind` analysis (`op`, `ac`, `tran`). KeyError if it didn't run."""
        for p in self.plots:
            if p.kind == kind:
                return p
        raise KeyError(f"no {kind} plot in result (have {[p.name for p in self.plots]})")


def prepare_netlist(netlist: str) -> list[str]:
    """Netlist lines safe to hand to any engine, ending in `.end`.

    Drops `*#` lines (ngspice runs them as commands and can block waiting for
    input), rejects `.control` blocks (they can run shell commands) and rejects a
    second analysis of the same kind (results would be ambiguous).
    """
    lines = [ln for ln in netlist.strip().splitlines() if not ln.lstrip().startswith("*#")]
    if any(ln.strip().lower().startswith(".control") for ln in lines):
        raise SimError(
            "This circuit or one of its models contains a .control block, "
            "which Solum Builder doesn't run. "
            "Remove the .control ... .endc lines from the model file."
        )
    if not lines:
        raise SimError("The netlist is empty.")
    kinds = [ln.split()[0].lower().lstrip(".") for ln in lines if ANALYSIS_LINE.match(ln)]
    repeated = sorted({k for k in kinds if kinds.count(k) > 1})
    if repeated:
        raise SimError(f"Run one {', '.join(repeated)} analysis per simulation, not several.")
    if lines[-1].strip().lower() != ".end":
        lines.append(".end")
    return lines


DEFAULT_TIMEOUT = 30.0  # seconds; long audio renders (Phase 7) pass their own


class SimEngine(Protocol):
    name: str

    def version(self) -> str: ...

    def run(
        self,
        netlist: str,
        timeout: float | None = DEFAULT_TIMEOUT,
        progress: Callable[[float], None] | None = None,
    ) -> SimResult:
        """Run `netlist`. SimError if it fails or takes longer than `timeout` s (None: no
        limit). `progress`, if given, is called with the fraction done (long transients);
        if it raises, the run stops and that exception is raised (a cancelled render)."""
        ...


def engine_from_settings(settings: Settings) -> SimEngine:
    """The engine for these settings: native libngspice (D-004, D-087).

    Raises EngineUnavailable with a plain-English message if it can't start."""
    from solum.sim.native import native_engine

    return native_engine(settings.ngspice_library)
