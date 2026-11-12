"""Tools → Add a model (9c): a SPICE `.model` card from the user's own file, cleaned
(`clean_card`, D-029), given a quick check through the real pipeline (`model_checks`) and
saved with its record to `DATA_DIR/models/<type>/<ID>.json`. The file stays on the user's
machine. Discrete parts (diodes and LEDs, BJTs, JFETs, MOSFETs) from a `.model` card; op-amps
from a `.subckt`, with the user's say on which node is which pin.
"""

import json
import multiprocessing as mp
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import count
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Literal

from solum import model_checks, tester
from solum.model_origin import USER
from solum.models import (
    QUANTITY_NAMES,
    Model,
    ModelCard,
    ModelError,
    ModelInfo,
    ModelLibrary,
    ModelType,
    Quantity,
    Source,
    Validation,
    clean_card,
    logical_lines,
    parse_model_line,
)
from solum.sim.engine import SimEngine, SimError
from solum.units import format_quantity

ADDED = "Tools → Add a model"
SUBCKT = "SUBCKT"  # a found card's type when it's a subcircuit
# a card's SPICE type → the part types it can be
PART_TYPES: dict[str, tuple[ModelType, ...]] = {
    "D": ("diode", "led"), "NPN": ("bjt",), "PNP": ("bjt",), "NJF": ("jfet",),
    "PJF": ("jfet",), "VDMOS": ("mosfet",), SUBCKT: ("opamp",),
}  # fmt: skip
# an op-amp's pins in the order its usual model gives them, and the wrapper's nodes for them
OPAMP_PINS = ("+", "-", "V+", "V-", "out")
_WRAPPER_NODES = ("inp", "inm", "vpos", "vneg", "out")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
# what the quick check measures per part type: (quantity, conditions, plausible range)
_TESTER = {"vcc": tester.VCC, "rc": tester.RC, "rb": tester.RB}
CHECKS: dict[str, list[tuple[Quantity, dict[str, float], tuple[float, float]]]] = {
    "diode": [("vf", {"if": 1e-3}, (0.05, 4.0)), ("vf", {"if": 10e-3}, (0.05, 5.0))],
    "led": [("vf", {"if": 2e-3}, (1.2, 4.5)), ("vf", {"if": 20e-3}, (1.2, 5.0))],
    "bjt": [
        ("tester_hfe", _TESTER, (5.0, 3000.0)), ("iceo", _TESTER, (0.0, 2e-3)),
        ("hfe", {"ic": 1e-3, "vce": 5.0}, (5.0, 3000.0)),
        ("vbe", {"ic": 1e-3, "vce": 5.0}, (0.05, 1.0)),
    ],
    "jfet": [
        ("idss", {"vds": 10.0}, (1e-6, 1.0)), ("vp", {"vds": 10.0, "id": 1e-8}, (-15.0, 15.0)),
    ],
    "mosfet": [("vgs_th", {"id": 1e-3}, (-10.0, 10.0))],
    # on a 9 V pedal's ±4.5 V; the buffer and the swing first: a wrong pin order shows there
    "opamp": [
        ("buffer_out", {"supply": 4.5, "vin": 0.5}, (0.45, 0.55)),
        ("buffer_out", {"supply": 4.5, "vin": -0.5}, (-0.55, -0.45)),
        ("swing_pos", {"supply": 4.5, "load": 10e3}, (0.0, 3.0)),
        ("swing_neg", {"supply": 4.5, "load": 10e3}, (0.0, 3.0)),
        ("aol_db", {"supply": 4.5}, (60.0, 160.0)), ("gbw", {"supply": 4.5}, (1e4, 1e9)),
    ],
}  # fmt: skip


Measure = Callable[[Model, ModelLibrary, Quantity, dict[str, float]], float]


@dataclass(frozen=True)
class Found:
    """A `.model` card or `.subckt` in an uploaded file, and the part types it can be. A
    subcircuit's `nodes` are in its order, with `comment`, the comment lines just above it
    (where makers name the pins), and `guess`, the pin on each node in the usual order
    (+, -, V+, V-, out; "" not connected)."""

    name: str
    spice_type: str
    part_types: tuple[ModelType, ...]
    nodes: tuple[str, ...] = ()
    comment: str = ""
    guess: tuple[str, ...] = ()


def cards_in(text: str) -> list[Found]:
    """The cards in a file that can be added: its top-level `.model` cards of a discrete
    part, and its top-level `.subckt`s with five nodes or more (an op-amp). Raises
    `ModelError` in plain words when there are none."""
    found = []
    depth = 0
    comment: list[str] = []
    for line in logical_lines(text):
        word = line.strip().split(maxsplit=1)[0].lower() if line.strip() else ""
        if word == ".subckt" and depth == 0 and len(nodes := _nodes(line)) >= len(OPAMP_PINS):
            guess = OPAMP_PINS + ("",) * (len(nodes) - len(OPAMP_PINS))
            found.append(Found(line.split()[1], SUBCKT, PART_TYPES[SUBCKT], nodes,
                               "\n".join(comment[-12:]), guess))  # fmt: skip
        depth += word == ".subckt"
        depth -= word == ".ends"
        comment = [*comment, line.strip()] if line.strip().startswith("*") else []
        if word == ".model" and depth == 0:
            card = parse_model_line(line.strip())
            if card.type.upper() in PART_TYPES:
                found.append(Found(card.name, card.type.upper(), PART_TYPES[card.type.upper()]))
    if not found:
        raise ModelError(
            "No diode, transistor, JFET or MOSFET .model card, and no op-amp .subckt (one "
            "with five pins or more), in that file."
        )
    return found


def _taken(models: ModelLibrary) -> dict[str, str]:
    """Every model's id, keyed in lower case: ngspice reads names in any case, so 2n3904
    and 2N3904 would be one card in a netlist."""
    return {i.lower(): i for i in models.ids()}


def suggested_id(card: str, models: ModelLibrary) -> str:
    """The name Add a model starts with for `card` (9c): its own, or `<card>-mine` when a
    model has it (then `-mine-2`, …), cut to stay a valid name. A stock model is never
    replaced (D-192)."""
    taken = _taken(models)
    if card.lower() not in taken:
        return card
    for n in count(1):
        tail = "-mine" if n == 1 else f"-mine-{n}"
        name = card[: 40 - len(tail)] + tail
        if name.lower() not in taken:
            return name
    raise AssertionError("unreachable")  # count() never ends


def _nodes(line: str) -> tuple[str, ...]:
    """A `.subckt` line's nodes: the words after its name, up to its parameters."""
    nodes = []
    for word in line.split()[2:]:
        if "=" in word or word.lower().rstrip(":") == "params":
            break
        nodes.append(word)
    return tuple(nodes)


@dataclass(frozen=True)
class Added:
    """A model made from an uploaded card, its quick check, and what was fixed in it."""

    model: Model
    checks: list[dict[str, Any]]  # quantity, name, value, text, at, plausible
    fixes: list[str]


def make_model(
    text: str, name: str, part_type: ModelType, model_id: str, filename: str,
    models: ModelLibrary, measure: Measure, pins: list[str] | None = None, channels: int = 1,
) -> Added:  # fmt: skip
    """The model for card `name` of `text` as part `part_type`, called `model_id`, checked
    with `measure`. Its card is renamed to the id, so it can't clash with another model's
    in a netlist. An op-amp takes `pins`, the pin on each of its nodes ("" none), and
    `channels`, how many are in the package. Raises `ModelError` in plain words."""
    model_id = model_id.strip()
    if not _ID.match(model_id):
        raise ModelError(
            "Give the model a name of letters, digits, - _ or . (up to 40), like 2N3904-mine."
        )
    if (same := _taken(models).get(model_id.lower())) is not None:
        raise ModelError(f"There's already a model called {same}. Give this one another name.")
    found = {f.name.lower(): f for f in cards_in(text)}
    if name.lower() not in found:
        raise ModelError(f"There's no card called {name} in that file.")
    found_card = found[name.lower()]
    name = found_card.name  # as the file spells it
    if part_type not in found_card.part_types:
        kind_said = (
            ".subckt" if found_card.spice_type == SUBCKT else f"{found_card.spice_type} card"
        )
        raise ModelError(f"{name} is a {kind_said}; it can't be a {part_type}.")
    if channels not in (1, 2, 4) or (channels != 1 and part_type != "opamp"):
        raise ModelError("An op-amp comes one, two or four to a package; other parts one.")
    header = f"* {name} from {filename}, added by the user {date.today().isoformat()}\n"
    kind: Literal["model", "subckt"] = "subckt" if found_card.spice_type == SUBCKT else "model"
    if kind == "subckt":
        wired = _pin_nodes(found_card, pins)
        cleaned = clean_card(_definitions(text))
        card_text = header + _wrapper(model_id, found_card, wired, cleaned.text)
    else:
        line = next(ln.strip() for ln in logical_lines(text) if _names(ln, name))
        cleaned = clean_card(line)
        card = parse_model_line(cleaned.text.strip())
        card_text = header + ModelCard(model_id, card.type, card.params).text() + "\n"
    info = ModelInfo(
        id=model_id, type=part_type, kind=kind, spice_name=model_id, card=f"{model_id}.lib",
        description=f"{name} ({filename}, added by you)", manufacturer=cleaned.manufacturer,
        source=Source(url=filename, retrieved=date.today().isoformat(), original=USER,
                      licence="Your own file; it stays on this machine", card=name),
        fixes=cleaned.fixes, ratings=cleaned.ratings, channels=channels,
        pins=list(OPAMP_PINS) if kind == "subckt" else [],
    )  # fmt: skip
    model = Model(info=info, card=card_text)
    trial = ModelLibrary({**{i: models.get(i) for i in models.ids()}, model_id: model})
    checks, records = [], []
    for quantity, conditions, (lo, hi) in CHECKS[part_type]:
        try:
            value = measure(model, trial, quantity, conditions)
        except (SimError, ValueError, KeyError) as err:
            pins_hint = " The pin order may be wrong." if kind == "subckt" else ""
            raise ModelError(
                f"The simulator couldn't run {name} as a {part_type}, so it can't be added."
                f"{pins_hint} Check the card is complete and is the right type."
            ) from err
        if why := _wrong_pins(quantity, value, conditions, (lo, hi)):
            raise ModelError(
                f"{why.format(name=name)}: the pin order is probably wrong. Check the "
                "comments above its .subckt line for which node is which."
            )
        checks.append({"quantity": quantity, "name": QUANTITY_NAMES[quantity], "value": value,
                       "text": format_quantity(value, _UNITS[quantity]).strip(),
                       "at": _at(conditions), "plausible": lo <= value <= hi})  # fmt: skip
        records.append(Validation(quantity=quantity, conditions=conditions, simulated=value,
                                  note=f"Measured when it was added ({ADDED})"))  # fmt: skip
    info = info.model_copy(update={"validation": records})
    return Added(Model(info=info, card=card_text), checks, cleaned.fixes)


def _wrong_pins(
    quantity: Quantity, value: float, conditions: dict[str, float], plausible: tuple[float, float]
) -> str:
    """Why an op-amp reading says its pins are in the wrong order, or "". A buffer that
    doesn't follow its input has its output or supplies astray; an output that goes down
    when + is above - (a swing past the far rail) has + and - swapped, which a buffer's DC
    point can't show: positive feedback balances there too."""
    if quantity == "buffer_out" and not plausible[0] <= value <= plausible[1]:
        return (f"Wired as a buffer, {{name}}'s output doesn't follow its input "
                f"({conditions['vin']:g} V in, {value:.2f} V out)")  # fmt: skip
    if quantity in ("swing_pos", "swing_neg") and value > conditions["supply"]:
        side = "above" if quantity == "swing_pos" else "below"
        return f"With + {side} −, {{name}}'s output goes the other way"
    return ""


def _pin_nodes(found: Found, pins: list[str] | None) -> dict[str, str]:
    """Which of a subcircuit's nodes each op-amp pin is on, from `pins` (the pin on each
    node in order, "" for none; the usual order if not given). Each pin must be on exactly
    one node."""
    pins = list(found.guess) if pins is None else pins
    if len(pins) != len(found.nodes) or sorted(p for p in pins if p) != sorted(OPAMP_PINS):
        raise ModelError(
            f"Put each of +, −, V+, V− and out on one of {found.name}'s nodes, once each."
        )
    return {pin: node for pin, node in zip(pins, found.nodes, strict=True) if pin}


def _definitions(text: str) -> str:
    """A file's definitions, to go inside the wrapper: every top-level `.subckt` block,
    `.model`, `.param` and `.func`. Commands, includes and stray elements are left out."""
    kept, depth = [], 0
    for line in logical_lines(text):
        word = line.strip().split(maxsplit=1)[0].lower() if line.strip() else ""
        depth += word == ".subckt"
        if depth > 0 or word in (".model", ".param", ".func"):
            kept.append(line)
        depth -= word == ".ends" and depth > 0
    return "\n".join(kept) + "\n"


def _wrapper(model_id: str, found: Found, wired: dict[str, str], body: str) -> str:
    """An op-amp `.subckt` called `model_id` with the usual pins (+, -, V+, V-, out) around
    the user's `found` subcircuit, wired as they said, with the file's definitions inside it
    so none of its names can clash with another model's. A node with no pin is held to
    ground through 1 TΩ, so it never floats."""
    pin_of = {node: pin for pin, node in wired.items()}
    free = [n for n in found.nodes if n not in pin_of]
    inner = [
        _WRAPPER_NODES[OPAMP_PINS.index(pin_of[n])] if n in pin_of else f"nc{free.index(n) + 1}"
        for n in found.nodes
    ]
    pins_said = ", ".join(f"{n} {pin_of.get(n, 'none')}" for n in found.nodes)
    return (
        f"* pins as the user set them (node pin): {pins_said}\n"
        f".subckt {model_id} {' '.join(_WRAPPER_NODES)}\n"
        f"X1 {' '.join(inner)} {found.name}\n"
        + "".join(f"R_nc{i} nc{i} 0 1e12\n" for i in range(1, len(free) + 1))
        + body
        + f".ends {model_id}\n"
    )


_UNITS: dict[str, str] = {
    "vf": "V", "vbe": "V", "vp": "V", "vgs_th": "V", "iceo": "A", "idss": "A",
    "hfe": "", "tester_hfe": "", "buffer_out": "V", "aol_db": "dB", "gbw": "Hz",
    "swing_pos": "V", "swing_neg": "V",
}  # fmt: skip
_COND_UNITS = {"if": ("IF", "A"), "ic": ("IC", "A"), "id": ("ID", "A"), "vce": ("VCE", "V"),
               "vds": ("VDS", "V"), "vin": ("in", "V"), "load": ("into", "Ω")}  # fmt: skip


def _at(conditions: dict[str, float]) -> str:
    """Where a check was made, in words: "IC 1 mA, VCE 5 V", "on the 9 V tester", or
    "±4.5 V, in 500 mV"."""
    if "rb" in conditions:
        return f"on the {conditions['vcc']:g} V tester"
    return ", ".join(
        f"±{v:g} V" if k == "supply"
        else f"{_COND_UNITS[k][0]} {format_quantity(v, _COND_UNITS[k][1])}"
        for k, v in conditions.items()
    )  # fmt: skip


def _names(line: str, name: str) -> bool:
    words = line.strip().split()
    return len(words) > 1 and words[0].lower() == ".model" and words[1].lower() == name.lower()


CHECK_TIMEOUT = 30.0  # s for a whole quick check; a good card takes well under one


def check_apart(
    text: str, name: str, part_type: ModelType, model_id: str, filename: str,
    models: ModelLibrary, pins: list[str] | None = None, channels: int = 1,
    library: str | None = None, timeout: float = CHECK_TIMEOUT,
) -> Added:  # fmt: skip
    """`make_model`, its quick check run by an ngspice of its own in a fresh process
    (`library`: libngspice's path, as in the settings), stopped when it's late. Some cards
    and wrong pin orders set ngspice's DC solve spinning, and that ignores a halt (D-195):
    in the app's own ngspice it would hold up every later run. Raises `ModelError`."""
    ctx = mp.get_context("spawn")  # no inherited ngspice state
    receive, send = ctx.Pipe(duplex=False)
    snapshot = {i: models.get(i) for i in models.ids()}
    args = (send, library, text, name, part_type, model_id, filename, snapshot, pins, channels)
    worker = ctx.Process(target=_check_in_worker, args=args, daemon=True)
    worker.start()
    send.close()
    try:
        if not receive.poll(timeout):
            hint = (
                "the pin order is probably wrong. Check the comments above its .subckt line "
                "for which node is which." if part_type == "opamp"
                else "check the card is complete and is the right type."
            )  # fmt: skip
            raise ModelError(
                f"The simulator got stuck on {name} and was stopped, so it can't be added: {hint}"
            )
        ok, result = receive.recv()
    except EOFError:
        raise ModelError(
            f"The simulator stopped unexpectedly checking {name}, so it can't be added. Check "
            "the card is complete and is the right type."
        ) from None
    finally:
        if worker.is_alive():
            worker.kill()
        worker.join()
        receive.close()
    if not ok:
        raise ModelError(result)
    return result  # type: ignore[no-any-return]


def _check_in_worker(
    send: Connection, library: str | None, text: str, name: str, part_type: ModelType,
    model_id: str, filename: str, snapshot: dict[str, Model], pins: list[str] | None,
    channels: int,
) -> None:  # fmt: skip
    """`check_apart`'s worker: the check, its `Added` (or the `ModelError`'s words) sent back."""
    from solum.sim.native import native_engine

    try:
        measure = engine_measure(native_engine(library))
        added = make_model(text, name, part_type, model_id, filename, ModelLibrary(snapshot),
                           measure, pins, channels)  # fmt: skip
        send.send((True, added))
    except ModelError as err:
        send.send((False, str(err)))
    finally:
        send.close()


def engine_measure(engine: SimEngine) -> Measure:
    """The quick check's measure: `model_checks.measure` through `engine`."""
    return lambda model, models, quantity, conditions: model_checks.measure(
        engine, models, model, quantity, conditions
    )


def save_model(model: Model, data_dir: Path) -> Path:
    """Write a model's card and record to `DATA_DIR/models/<type>/` (the user's layer,
    over the core models, D-011). Returns the record's path."""
    folder = data_dir / "models" / model.info.type
    folder.mkdir(parents=True, exist_ok=True)
    (folder / model.info.card).write_text(model.card, encoding="utf-8")
    path = folder / f"{model.id}.json"
    record = model.info.model_dump(exclude_defaults=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
