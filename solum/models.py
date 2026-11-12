"""Device models: the model library, SPICE card parsing, and the importer's fixes (D-029).

A model is `library/models/<type>/<ID>.json` (metadata, source, ratings, validation
record) plus the SPICE card file it names. A behavioural model (a charge pump, D-093) has
no card: its `params` feed the netlist's own model of the part. User models (Phase 4)
layer over core ones.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from solum.cache import content_hash
from solum.model_origin import ESTIMATE, USER, card_origin
from solum.units import parse_spice_number

ModelType = Literal[
    "diode", "led", "jfet", "bjt", "mosfet", "opamp", "inverter", "ota", "chargepump",
    "regulator",
]  # fmt: skip
CHIP_TYPES: tuple[ModelType, ...] = ("opamp", "inverter", "ota")  # drawn as chip units (D-180)
Quantity = Literal[
    "vf",
    "vz",
    "ir",
    "hfe",
    "vbe",
    "vce_sat",
    "vbe_sat",
    "icbo",
    "iceo",
    "tester_hfe",
    "idss",
    "vp",
    "vgs_th",
    "vds_on",
    "aol_db",
    "gbw",
    "swing_pos",
    "swing_neg",
    "buffer_out",
    "vout",
    "gm",
    "iout_max",
    "v_switch",
    "iol",
    "ioh",
]

# Each quantity in plain words, as a datasheet names it (the parts list, 9c).
QUANTITY_NAMES: dict[str, str] = {
    "vf": "Forward voltage", "vz": "Zener voltage", "ir": "Reverse leakage", "hfe": "hFE",
    "vbe": "VBE(on)", "vce_sat": "VCE(sat)", "vbe_sat": "VBE(sat)", "icbo": "ICBO",
    "iceo": "Leakage (ICEO)", "tester_hfe": "Gain on the tester", "idss": "IDSS",
    "vp": "Pinch-off (VP)", "vgs_th": "Gate threshold", "vds_on": "On-voltage",
    "aol_db": "Open-loop gain", "gbw": "Gain-bandwidth", "swing_pos": "Output swing (+)",
    "swing_neg": "Output swing (-)", "buffer_out": "Output as a buffer",
    "vout": "Output voltage", "gm": "Transconductance",
    "iout_max": "Peak output current", "v_switch": "Switching voltage",
    "iol": "Output current (low)", "ioh": "Output current (high)",
}  # fmt: skip

# LTspice-only params that ngspice 44 rejects (D-029), kept as metadata instead:
# mfg → manufacturer; the rest → ratings (Vceo, Icrating, diode Iave and Vpk).
_METADATA_PARAMS = {
    "mfg": "manufacturer", "vceo": "vceo", "icrating": "ic", "iave": "if_avg", "vpk": "vr_max",
}  # fmt: skip
_DROPPED_PARAMS = ("type",)  # LTspice diode "type=silicon": a label, not a parameter
_JFET_UNSUPPORTED = ("isr", "nr", "alpha", "vk")
_MODEL_LINE = re.compile(r"\.model\s+(\S+)\s+([A-Za-z]+)\s*\(?(.*?)\)?\s*$", re.I | re.S)
_PARAM = re.compile(r"([A-Za-z_]\w*)\s*=\s*([^\s,()=]+)")


EG_GERMANIUM_MAX = 0.9  # eV: a BJT card's bandgap below this is germanium (0.67; silicon 1.11)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasheetRange(_Strict):
    """Datasheet limits. `typ` is checked only when `tol` (allowed deviation) is given."""

    min: float | None = None
    typ: float | None = None
    max: float | None = None
    tol: float | None = None
    source: str
    note: str = ""


def _has_limit(d: "DatasheetRange") -> bool:
    """Whether a datasheet figure is checked: a min, a max, or a typical with a tolerance."""
    return d.min is not None or d.max is not None or (d.typ is not None and d.tol is not None)


class Validation(_Strict):
    """One simulated characteristic, checked against the datasheet where we have it.

    `tests/sim/test_models.py` re-measures `simulated` so the record can't go stale.
    """

    quantity: Quantity
    conditions: dict[str, float]
    simulated: float
    datasheet: DatasheetRange | None = None
    note: str = ""


class Source(_Strict):
    url: str
    retrieved: str
    licence: str
    original: str = ""
    card: str = ""  # a user's model: the card's name in their file (Add a model, 9c)


class Package(_Strict):
    """A part's pin numbers as its datasheet gives them (D-140, D-149). `pins`: pin → number;
    a dual's signal pins are `a.out`, `b.+`…, its power pins (one pair for the chip) `V+`
    and `V-`; a transistor's `C`, `B`, `E` (`D`, `G`, `S`), a diode's `A`, `K`. A model whose
    sheet couldn't be checked has none, and draws no numbers."""

    name: str  # the package the numbers are for: "8-pin DIP", "TO-92 (EBC)"
    pins: dict[str, int]
    source: str  # where they were read


class Fit(_Strict):
    """How a model we made ourselves was fitted (D-156): used only where every published
    card is off limits or none exists. `points` are what it was fitted to, read from
    `figure` of `sheet` (each a [quantity, condition] pair, e.g. [volts, amps]; a BJT's
    are always [IC, DC gain], its other curves under `curves`); the record's validation
    checks it at points it wasn't fitted to."""

    sheet: str
    figure: str
    points: list[tuple[float, float]]
    method: str  # what was fitted and how, so it can be repeated
    note: str = ""
    # further curves fitted, by name, where a fit takes more than one figure (a BJT's
    # VBE, VCE(sat) and capacitances beside its hFE, D-163)
    curves: dict[str, list[tuple[float, float]]] = {}


class ModelInfo(_Strict):
    id: str
    type: ModelType
    description: str
    spice_name: str = ""
    kind: Literal["model", "subckt", "behavioural"]
    pins: list[str] = []
    card: str = ""  # none for a behavioural model
    manufacturer: str = ""
    source: Source
    datasheet: str = ""  # the sheet to open: its URL (9c, Tools → Parts and datasheets)
    note: str = ""  # caveats of a card we didn't fit (a fit's are in `fit.note`), in plain words
    fixes: list[str] = []
    ratings: dict[str, float] = {}  # vceo, ic, if_avg, vr_max, vs_max, cm_*_headroom
    rating_sources: dict[str, str] = {}  # rating → where it was read (D-043, D-077)
    params: dict[str, float] = {}  # a behavioural model's values (charge pump: D-093)
    param_sources: dict[str, str] = {}  # param → where it was read
    validation: list[Validation] = []
    # a chip's units: 2 a dual (TL072, D-140, an LM13700), 4 a quad (D-172), 6 a 4049 (D-180)
    channels: Literal[1, 2, 4, 6] = 1
    package: Package | None = None  # pin numbers from the datasheet (D-140, D-149)
    fit: Fit | None = None  # our own fit to a datasheet, not a maker's card (D-156)


@dataclass(frozen=True)
class ModelCard:
    """A parsed `.model` statement. Param names are lower case; values stay as written."""

    name: str
    type: str
    params: dict[str, str]

    def text(self, width: int = 90) -> str:
        """The statement as SPICE text, wrapped with `+` continuation lines."""
        lines: list[str] = []
        current = f".model {self.name} {self.type}("
        for key, value in self.params.items():
            item = f"{key}={value}"
            sep = "" if current.endswith("(") else " "
            if len(current) + len(sep) + len(item) > width and not current.endswith("("):
                lines.append(current)
                current, sep = "+", " "
            current += sep + item
        return "\n".join([*lines, current + ")"])


@dataclass(frozen=True)
class Model:
    info: ModelInfo
    card: str

    @property
    def id(self) -> str:
        return self.info.id

    @cached_property
    def statement(self) -> ModelCard | None:
        """The `.model` statement for this device (None for subcircuit models)."""
        if self.info.kind != "model":
            return None
        for card in parse_model_cards(self.card):
            if card.name.lower() == self.info.spice_name.lower():
                return card
        raise ValueError(f"Model {self.id}: no .model {self.info.spice_name} in {self.info.card}.")

    @property
    def polarity(self) -> Literal["n", "p"] | None:
        """n for NPN / N-channel, p for PNP / P-channel, None otherwise."""
        kind = self.statement.type.upper() if self.statement else ""
        if kind in ("NPN", "NJF") or (kind == "VDMOS" and "pchan" not in self.card.lower()):
            return "n"
        if kind in ("PNP", "PJF", "VDMOS"):
            return "p"
        return None

    @property
    def zener(self) -> bool:
        """A diode whose record checks a zener voltage (`vz`): it draws with KiCad's bent
        cathode bar and is named Z. False for anything else."""
        return self.info.type == "diode" and any(v.quantity == "vz" for v in self.info.validation)

    @property
    def depletion(self) -> bool:
        """A MOSFET that's on at VGS = 0 (D-178): its threshold VTO on the far side of zero
        (below it for N-channel, above for P-channel). False for anything else."""
        card = self.statement
        if card is None or card.type.upper() != "VDMOS":
            return False
        vto = self.param("vto") or 0.0
        return vto < 0 if self.polarity == "n" else vto > 0

    def jfet_spec(self) -> dict[str, float] | None:
        """A level-1 JFET's Idss (A) and pinch-off Vp (V), from its BETA and VTO
        (Idss = BETA·VTO²); None for any other model. A measured JFET replaces both."""
        card = self.statement
        if card is None or card.type.upper() not in ("NJF", "PJF"):
            return None
        if card.params.get("level", "1") not in ("1", "1.0"):
            return None
        vp, beta = self.param("vto"), self.param("beta")
        if vp is None or beta is None:
            return None
        return {"idss": beta * vp**2, "vp": vp}

    def bjt_spec(self) -> dict[str, float | bool] | None:
        """A BJT model's gain and leakage as the Geofex tester reads them (D-130, D-153):
        the gain from its validation record (`tester_hfe`), else its BF (SPICE's default
        100 if the card doesn't set it); the leakage, the collector current with the base
        open (`iceo`), else 0 (a silicon part's is nA); and whether it's `germanium` (the
        card's bandgap EG under `EG_GERMANIUM_MAX`: 0.67 eV against silicon's 1.11,
        SPICE's default; D-138); `estimated` when the card was estimated with no sheet
        (D-186). None for a subcircuit or any other model. A measured transistor replaces
        the gain and leakage (`ModelLibrary.bjt_fit`)."""
        card = self.statement
        if card is None or card.type.upper() not in ("NPN", "PNP"):
            return None
        recorded = {v.quantity: v.simulated for v in self.info.validation}
        hfe = recorded.get("tester_hfe", self.param("bf"))
        leak = recorded.get("iceo", 0.0)
        eg = self.param("eg")
        germanium = eg is not None and eg < EG_GERMANIUM_MAX
        spec: dict[str, float | bool] = {
            "hfe": 100.0 if hfe is None else hfe, "leakage": leak, "germanium": germanium
        }  # fmt: skip
        if self.info.source.original == ESTIMATE:
            spec["estimated"] = True
        return spec | self._below_sheet()

    def _below_sheet(self) -> dict[str, float]:
        """Where the tester runs the transistor below the lowest current of the sheet's gain
        curve the card was fitted to (9b: the MPSA06 near 0.34 mA, its curve from 0.52 mA):
        the tester's collector current (`tester_ic`, amps) and the curve's start
        (`sheet_low_ic`), so the form can say the figure is the card's extrapolation. The
        base current is taken as VCC/RB (the base's 0.2 to 0.7 V is under 8 % of it); the
        collector's is gain times that plus the leakage (`iceo`), as a sheet's curve includes it
        (a germanium's transfer curve, 9c). Empty when it's inside the curve, or there's no
        fit or tester record. A fit's points are (IC, gain)."""
        tester = next((v for v in self.info.validation if v.quantity == "tester_hfe"), None)
        if tester is None or self.info.fit is None or not self.info.fit.points:
            return {}
        leak = next((v.simulated for v in self.info.validation if v.quantity == "iceo"), 0.0)
        ic = tester.simulated * tester.conditions["vcc"] / tester.conditions["rb"] + leak
        low = min(i for i, _ in self.info.fit.points)
        return {"tester_ic": ic, "sheet_low_ic": low} if ic < low else {}

    @property
    def yours(self) -> bool:
        """Whether the user added it (Tools → Add a model, D-192), not a stock model."""
        return self.info.source.original == USER

    def catalogue_entry(self) -> dict[str, Any]:
        """What Tools → Parts and datasheets shows for this model (9c), read from its record
        and nothing else: whose card it is (`card_origin`), its maker, datasheet link and
        package; for our own fit, the sheet and figures; its caveats (`note`, `fit.note`); how many
        datasheet checks it passes (`tests/sim/test_models.py` holds every one), and the
        comparisons the sheet gives no limit for, with their notes (a known miss, or a
        typical with no spread: `unchecked`)."""
        info, fit = self.info, self.info.fit
        origin, detail = card_origin(info.model_dump())
        compared = [v for v in info.validation if v.datasheet is not None]
        unchecked = [
            {"quantity": v.quantity, "name": QUANTITY_NAMES[v.quantity], "note": note}
            for v in compared
            if v.datasheet is not None and not _has_limit(v.datasheet)
            and (note := v.datasheet.note or v.note)
        ]  # fmt: skip
        return {
            "id": info.id, "type": info.type, "description": info.description,
            "maker": info.source.original or info.manufacturer, "origin": origin,
            "origin_detail": detail, "datasheet": info.datasheet,
            "package": info.package.name if info.package else "",
            "sheet": fit.sheet if fit else "", "figure": fit.figure if fit else "",
            "note": " ".join(n for n in (info.note, fit.note if fit else "") if n),
            "checks": sum(1 for v in compared if v.datasheet and _has_limit(v.datasheet)),
            "unchecked": unchecked,
        }  # fmt: skip

    def datasheet_range(self, quantity: Quantity) -> dict[str, Any] | None:
        """The datasheet's min and max for `quantity` with its test conditions, from the
        first validation record that has both; None if no record does (a unit of this
        part can be anywhere in it; the card is one typical unit)."""
        for v in self.info.validation:
            d = v.datasheet
            if v.quantity == quantity and d and d.min is not None and d.max is not None:
                return {"min": d.min, "max": d.max, "at": v.conditions}
        return None

    @property
    def halves(self) -> int:
        """How many units the chip has: 1 a single, 2 a dual (IC1A, IC1B; D-140), 4 a
        quad (IC1A to IC1D; D-172), 6 a 4049 (D-180)."""
        return self.info.channels

    def chip_spec(self) -> dict[str, Any] | None:
        """A chip model's chip, for its form (D-140, D-180): its part type, how many
        units, the pins it simulates, and the datasheet's pin numbers with where they were
        read (or None). None for a model that isn't a chip."""
        if self.info.type not in CHIP_TYPES:
            return None
        package = self.info.package
        return {
            "type": self.info.type,
            "halves": self.halves,
            "simulated": list(self.info.pins),
            "package": package.model_dump() if package else None,
        }

    def pin_number(self, pin: str, half: str | None = None) -> int | None:
        """The datasheet pin number of a chip's `pin` (on unit `half` of a chip of several), or
        None when the record has no package or the chip has no such pin."""
        pins = self.info.package.pins if self.info.package else {}
        return pins.get(f"{half}.{pin}") or pins.get(pin)

    def param(self, name: str) -> float | None:
        """A numeric model parameter (SPICE units), or None if the card doesn't set it."""
        if self.statement is None or name.lower() not in self.statement.params:
            return None
        return parse_spice_number(self.statement.params[name.lower()])


class ModelError(ValueError):
    """A model is missing or broken (plain-English message)."""


@dataclass(frozen=True)
class BjtFit:
    """What a measured transistor's netlist sets (D-153): `scale`, the card's gain scaled
    at every current (BF times it, ISE, the base's recombination current, over it: both
    parts of the base current shrink alike), and `icbo`, a hidden current from collector
    to base on top of the card's own leakage (D-130)."""

    scale: float
    icbo: float


BjtFitter = Callable[[Model, float, float | None], BjtFit]  # model, hFE, leakage (None: own)


def direct_fit(model: Model, hfe: float, leakage: float | None) -> BjtFit:
    """The fit without a simulator: BF becomes the hFE, and Icbo makes up the leakage over
    the model's own at that gain. The tester then reads off, by how far the card's gain
    sits from its BF (D-130); a `Simulator` fits on the tester itself
    (`solum.tester.fit_bjt`)."""
    spec = model.bjt_spec()
    own = float(spec["leakage"]) if spec else 0.0
    bf = model.param("bf") or 100.0
    return BjtFit(hfe / bf, 0.0 if leakage is None else (leakage - own) / (hfe + 1))


class ModelLibrary:
    def __init__(self, models: Mapping[str, Model], fitter: BjtFitter = direct_fit) -> None:
        self._models = dict(models)
        self._fitter = fitter
        self._memo: dict[str, str] = {}  # the fingerprint, shared and cleared with the models

    def with_fitter(self, fitter: BjtFitter) -> "ModelLibrary":
        """The same models, measured transistors fitted by `fitter`. The two share their
        models, so one `add`ed to either is in both."""
        lib = ModelLibrary({}, fitter)
        lib._models, lib._memo = self._models, self._memo
        return lib

    def add(self, model: Model) -> None:
        """A model added while the app runs (Tools → Add a model, `solum.model_import`)."""
        self._models[model.id] = model
        self._memo.clear()

    def bjt_fit(self, model: Model, hfe: float, leakage: float | None) -> BjtFit:
        return self._fitter(model, hfe, leakage)

    def get(self, model_id: str) -> Model:
        try:
            return self._models[model_id]
        except KeyError:
            raise ModelError(
                f"There's no model called {model_id!r} in the library. Add it with Tools "
                "\u2192 Add a model, or choose another model for the part."
            ) from None

    def __contains__(self, model_id: object) -> bool:
        return model_id in self._models

    def ids(self, type: ModelType | None = None) -> list[str]:
        return sorted(k for k, m in self._models.items() if type in (None, m.info.type))

    @property
    def fingerprint(self) -> str:
        """A hash of every model's id and card: part of a cached search's key (D-127)."""
        if "fingerprint" not in self._memo:
            self._memo["fingerprint"] = content_hash(
                *(x for k in sorted(self._models) for x in (k, self._models[k].card))
            )
        return self._memo["fingerprint"]


def load_models(dirs: Sequence[Path]) -> ModelLibrary:
    """Models from `dirs` (each laid out `<type>/<ID>.json`); earlier dirs win (D-011)."""
    models: dict[str, Model] = {}
    for root in reversed(dirs):
        for path in sorted(root.glob("*/*.json")):
            model = load_model(path)
            models[model.id] = model
    return ModelLibrary(models)


def load_model(path: Path) -> Model:
    try:
        info = ModelInfo.model_validate_json(path.read_text(encoding="utf-8"))
        card = (path.parent / info.card).read_text(encoding="utf-8") if info.card else ""
    except (OSError, ValidationError) as err:
        raise ModelError(f"The model file {path} can't be used: {err}") from None
    return Model(info=info, card=card)


def logical_lines(text: str) -> list[str]:
    """SPICE lines with `+` continuations joined onto the line they continue."""
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("+") and out:
            out[-1] += " " + stripped[1:].strip()
        else:
            out.append(raw.rstrip())
    return out


def parse_model_cards(text: str) -> list[ModelCard]:
    """Top-level `.model` statements (those inside a `.subckt` are skipped)."""
    cards: list[ModelCard] = []
    depth = 0
    for line in logical_lines(text):
        word = line.strip().split(maxsplit=1)[0].lower() if line.strip() else ""
        depth += word == ".subckt"
        depth -= word == ".ends"
        if word == ".model" and depth == 0:
            cards.append(parse_model_line(line))
    return cards


def parse_model_line(line: str) -> ModelCard:
    match = _MODEL_LINE.match(line.strip())
    if match is None:
        raise ValueError(f"Not a .model line: {line!r}")
    name, kind, body = match.groups()
    params = {k.lower(): v for k, v in _PARAM.findall(body)}
    return ModelCard(name=name, type=kind.upper(), params=params)


@dataclass(frozen=True)
class CleanedCard:
    text: str
    fixes: list[str]
    manufacturer: str
    ratings: dict[str, float]


def clean_card(text: str) -> CleanedCard:
    """Apply the D-029 fixes so ngspice 44 loads a published card cleanly.

    Drops `*#` lines (ngspice runs them as commands), moves LTspice-only `mfg`, `Vceo`,
    `Icrating`, `Iave` and `Vpk` into metadata, and drops params ngspice doesn't know.
    """
    fixes: list[str] = []
    manufacturer = ""
    ratings: dict[str, float] = {}
    out: list[str] = []
    for line in logical_lines(text):
        stripped = line.strip()
        if stripped.startswith("*#"):
            fixes.append("dropped a '*#' line (ngspice runs those as commands)")
            continue
        if not stripped.lower().startswith(".model"):
            out.append(line)
            continue
        card = parse_model_line(stripped)
        params = dict(card.params)
        for key, meta in _METADATA_PARAMS.items():
            if key in params:
                value = params.pop(key)
                fixes.append(f"moved {key}={value} out of the card into metadata")
                if meta == "manufacturer":
                    manufacturer = value
                else:
                    ratings[meta] = parse_spice_number(value)
        for key in _DROPPED_PARAMS:
            if key in params:
                fixes.append(f"dropped {key}={params.pop(key)} (an LTspice label)")
        if card.type in ("NJF", "PJF"):
            dropped = [k for k in _JFET_UNSUPPORTED if params.pop(k, None) is not None]
            if dropped:
                fixes.append(f"dropped {', '.join(dropped)} (not supported by ngspice's JFET)")
        out.append(ModelCard(card.name, card.type, params).text())
    return CleanedCard("\n".join(out).strip() + "\n", fixes, manufacturer, ratings)


def model_cards_text(models: Iterable[Model]) -> str:
    """The SPICE text for these models, each once, in id order."""
    unique = {m.id: m for m in models if m.card}
    return "\n".join(unique[k].card.strip() for k in sorted(unique))
