"""The `.expected.yaml` acceptance files (D-019, D-034): their format, and how each
check is measured on a starter circuit.

A check names a node (net name or pin, e.g. `Q1.C`), optionally a `ref` node to measure
against (default: the guitar input), part changes to make first (`set`), and a value
with its tolerance. Kinds:
  dc         volts at the node (or at each node of a list), minus `minus` if given, ± tol
  gain       dB at `hz`, ± tol_db, or at most `max_db`
  peak_gain  highest dB of the response, ± tol_db
  corner     -3 dB point below (`side: low`) or above (`side: high`) the peak, ± tol_pct
  notch      lowest point within `band`: frequency ± tol_pct, and dB ± tol_db if given
  clip       transient at `level`: both peaks of node (minus `minus`) at ± volts, ± tol
A check with `known_gap` explains why the simulation misses a published value; one with
`pending` waits for a source (e.g. a datasheet) and is skipped until it's filled in.
Values read off an image (`from: image`) carry the archived `image` link for review.
"""

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from solum.analysis.measures import corner_3db, gain_at, notch, peak
from solum.analysis.signal import last_cycles
from solum.circuit.schema import Circuit
from solum.netlist import Ac
from solum.simulate import MEASURE_CYCLES, Simulator
from solum.yamlio import load_yaml


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Source(_Strict):
    title: str
    url: str
    snapshot: str
    read: datetime.date
    licence: str


class Check(_Strict):
    id: str
    kind: Literal["dc", "gain", "peak_gain", "corner", "notch", "clip"]
    node: str | list[str]
    ref: str | None = None
    minus: str | None = None
    set_: dict[str, dict[str, Any]] = Field(default_factory=dict, alias="set")
    supply: float | None = None  # V+ for this check, where the source measured on another
    sweep: dict[str, float] = Field(default_factory=dict)
    volts: float | None = None
    tol: float | None = None
    hz: float | None = None
    db: float | None = None
    tol_db: float | None = None
    max_db: float | None = None
    tol_pct: float | None = None
    side: Literal["low", "high"] | None = None
    band: tuple[float, float] | None = None
    level: str | None = None
    from_: Literal["text", "image"] = Field(alias="from")
    quote: str | None = None  # the source's own words (a table's row, a short phrase)
    # What the source says, in our words: for a source whose licence keeps its words out
    # of a repo that may be used commercially (ElectroSmash, CC BY-NC; D-292).
    says: str | None = None
    note: str | None = None
    # A published value the simulation doesn't meet, with the reason worked out by hand.
    # The test runs as a strict xfail, so it flags itself if it starts passing.
    known_gap: str | None = None
    pending: str | None = None  # what's missing before this check can run
    image: str | None = None  # archived link to the image a `from: image` value was read from
    confirmed: datetime.date | None = None  # when the user checked a `from: image` reading

    @model_validator(mode="after")
    def _image_has_link(self) -> "Check":
        if self.from_ == "image" and not self.image:
            raise ValueError(f"Check {self.id} is read from an image: add its `image` link.")
        return self


class Omitted(_Strict):
    what: str
    why: str


class Build(_Strict):
    """Where the parts list's details come from (9d2): the capacitor types and ratings,
    the enclosure. `sources` beyond the main one (a kit's parts list of the same circuit),
    and `parts` saying, in plain words, what was taken from which."""

    sources: list[Source] = Field(default_factory=list)
    parts: list[str]


class Expected(_Strict):
    circuit: str
    source: Source
    substitutions: list[str]
    checks: list[Check]
    omitted: list[Omitted] = Field(default_factory=list)
    build: Build | None = None


def load_expected(path: Path) -> Expected:
    return Expected.model_validate(load_yaml(path))


@dataclass(frozen=True)
class Outcome:
    passed: bool
    detail: str  # what was measured vs expected, for the failure message


def _within(measured: float, expected: float, tol: float, unit: str) -> Outcome:
    ok = abs(measured - expected) <= tol
    return Outcome(ok, f"measured {measured:.4g} {unit}, expected {expected:g} ± {tol:g} {unit}")


def _need(value: float | None, name: str, check: Check) -> float:
    if value is None:
        raise ValueError(f"Check {check.id} ({check.kind}) needs `{name}`.")
    return value


def run_check(sim: Simulator, circuit: Circuit, check: Check) -> list[Outcome]:
    for ref, fields in check.set_.items():
        circuit = circuit.with_part(ref, **fields)
    if check.supply is not None:
        rails = {**circuit.power.rails, "V+": check.supply}
        power = circuit.power.model_copy(update={"rails": rails})
        circuit = circuit.model_copy(update={"power": power})
    nodes = check.node if isinstance(check.node, list) else [check.node]
    if check.kind == "dc":
        v = sim.op(circuit).voltages
        volts, tol = _need(check.volts, "volts", check), _need(check.tol, "tol", check)
        base = 0.0 if check.minus is None else v[sim.resolve(circuit, check.minus)]
        label = "" if check.minus is None else f" - {check.minus}"
        return [
            _within(v[sim.resolve(circuit, n)] - base, volts, tol, f"V at {n}{label}")
            for n in nodes
        ]
    if check.kind == "clip":
        return _clip(sim, circuit, check, nodes[0])
    ac = sim.ac(circuit, Ac(**check.sweep))
    if not ac.valid:
        return [Outcome(False, f"AC result invalid: {ac.saturated}")]
    h = ac.responses[sim.resolve(circuit, nodes[0])]
    if check.ref is not None:
        h = h / ac.responses[sim.resolve(circuit, check.ref)]
    f = ac.freq
    if check.kind == "gain":
        g = gain_at(f, h, _need(check.hz, "hz", check))
        if check.max_db is not None:
            return [Outcome(g <= check.max_db, f"measured {g:.4g} dB, at most {check.max_db:g} dB")]
        return [
            _within(g, _need(check.db, "db", check), _need(check.tol_db, "tol_db", check), "dB")
        ]
    if check.kind == "peak_gain":
        g = peak(f, h)[1]
        return [
            _within(g, _need(check.db, "db", check), _need(check.tol_db, "tol_db", check), "dB")
        ]
    hz, pct = _need(check.hz, "hz", check), _need(check.tol_pct, "tol_pct", check)
    if check.kind == "corner":
        if check.side is None:
            raise ValueError(f"Check {check.id} (corner) needs `side`.")
        return [_within(corner_3db(f, h, check.side), hz, hz * pct / 100, "Hz")]
    fn, db = notch(f, h, check.band)
    found = [_within(fn, hz, hz * pct / 100, "Hz")]
    if check.db is not None:
        found.append(_within(db, check.db, _need(check.tol_db, "tol_db", check), "dB"))
    return found


def _clip(sim: Simulator, circuit: Circuit, check: Check, node: str) -> list[Outcome]:
    level = check.level or "med"
    names = [node] if check.minus is None else [node, check.minus]
    tran = sim.tran(circuit, names, level)
    wave = tran.waves[sim.resolve(circuit, node)]
    if check.minus is not None:
        wave = wave - tran.waves[sim.resolve(circuit, check.minus)]
    v = last_cycles(tran.time, wave, tran.freq, MEASURE_CYCLES)
    v = v - float(np.mean(v))
    volts, tol = _need(check.volts, "volts", check), _need(check.tol, "tol", check)
    return [
        _within(float(v.max()), volts, tol, "V peak (+)"),
        _within(float(-v.min()), volts, tol, "V peak (-)"),
    ]
