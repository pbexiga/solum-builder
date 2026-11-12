"""Reference guides shipped in `library/guides/` (D-095): read, checked and served as data,
so the Help pages, the inspector's hints and the rules' advice share one text."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from solum.yamlio import load_yaml


class GuideError(ValueError):
    """A guide file is missing or invalid (plain-English message)."""


class CapacitorKind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    hint: str = Field(max_length=48)  # fits beside the kind in the dropdown
    values: str
    use: str
    watch: str


class CapacitorGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    intro: str
    kinds: list[CapacitorKind] = Field(min_length=1)

    def kind(self, kind: str) -> CapacitorKind:
        return next(k for k in self.kinds if k.kind == kind)


class Pickup(BaseModel):
    """One measured pickup: its coil (R, L at 120 Hz, C from its unloaded resonance) and
    the volume pot it's usually wired with. Values are SI strings, as in circuit files."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    measured: str  # which pickup was measured
    r: str
    l: str  # noqa: E741  (inductance; the domain's own letter)
    c: str
    resonance: str
    volume: str


class PickupGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    intro: str
    source: str
    pot_source: str
    cable_source: str
    pickups: list[Pickup] = Field(min_length=1)


class InductorPreset(BaseModel):
    """One measured wah inductor (D-173): L at 1 kHz and its wire's DC resistance, as SI
    strings, as in circuit files."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    measured: str  # which inductor was measured
    l: str  # noqa: E741  (inductance; the domain's own letter)
    r: str


class InductorGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    intro: str
    source: str
    inductors: list[InductorPreset] = Field(min_length=1)


def _load[G: BaseModel](library_dir: Path, name: str, model: type[G]) -> G:
    """`library/guides/<name>.yaml`, checked against `model`, its folded text tidied."""
    path = library_dir / "guides" / f"{name}.yaml"
    try:
        guide = model.model_validate(load_yaml(path))
    except ValidationError as err:
        raise GuideError(f"{path.name} isn't a valid guide: {err.errors()[0]['msg']}.") from None
    for field, value in guide:
        if isinstance(value, str):
            setattr(guide, field, " ".join(value.split()))
    return guide


def pickup_guide(library_dir: Path) -> PickupGuide:
    """`library/guides/pickups.yaml`, checked (D-096)."""
    return _load(library_dir, "pickups", PickupGuide)


def inductor_guide(library_dir: Path) -> InductorGuide:
    """`library/guides/inductors.yaml`, checked (D-173)."""
    return _load(library_dir, "inductors", InductorGuide)


def capacitor_guide(library_dir: Path) -> CapacitorGuide:
    """`library/guides/capacitors.yaml`, checked."""
    guide = _load(library_dir, "capacitors", CapacitorGuide)
    for k in guide.kinds:
        k.use, k.watch = " ".join(k.use.split()), " ".join(k.watch.split())
    return guide


class BatteryState(BaseModel):
    """One state of a draining 9 V battery: its voltage on a pedal's load (D-143)."""

    model_config = ConfigDict(extra="forbid")

    state: str
    name: str
    volts: float = Field(gt=0)
    hours: float = Field(ge=0)  # into the datasheet's test, where it was read


class BatteryGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    intro: str
    source: str
    states: list[BatteryState] = Field(min_length=1)


def battery_guide(library_dir: Path) -> BatteryGuide:
    """`library/guides/batteries.yaml`, checked (D-143)."""
    return _load(library_dir, "batteries", BatteryGuide)
