"""The one place circuit/block files are upgraded between schema versions.

Each entry in MIGRATIONS turns a version-N dict into a version-N+1 dict. Bumping the
schema means: add the migration here, bump `schema.SCHEMA_VERSION`, and add a test that
loads a version-N fixture.
"""

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import TypeAdapter

from solum.circuit.connectivity import GROUND, ConnectivityError, Nets, connect, on_segment
from solum.circuit.parts import PIN_OFFSETS, pin_positions, rotate, throw_offsets
from solum.circuit.refs import FIXED, HALVES, NAMED, PREFIXES, ref_number, ref_problem
from solum.circuit.schema import SCHEMA_VERSION, Circuit, Label, Part, Resistor, VSource, Wire
from solum.circuit.switches import (
    DEFAULT_KIND,
    KINDS,
    POLE_LETTERS,
    from_poles_throws,
    kind_of,
    lug_name,
)
from solum.units import parse_value

Data = dict[str, Any]
Migration = Callable[[Data], Data]


def _v1_to_v2(data: Data) -> Data:
    """v2 added the optional `tags` list; a v1 file is already a valid v2 file."""
    return data


def _v2_to_v3(data: Data) -> Data:
    """v3 added power mode `custom` (dropped again in v6); a v2 file is a valid v3 file."""
    return data


def _v3_to_v4(data: Data) -> Data:
    """v4 made provenance `refs` a map (block ref → ref in the circuit, D-072). A v3 list
    has no record of the block's own refs, so each ref maps to itself."""
    out = dict(data)
    out["provenance"] = [
        {**p, "refs": {r: r for r in p["refs"]}} if isinstance(p.get("refs"), list) else p
        for p in data.get("provenance", [])
    ]
    return out


def _v4_to_v5(data: Data) -> Data:
    """v5 added the version tag and `final` (both default: v1.0, not final) and dropped
    `provenance`: a pasted block is a plain copy, nothing links back to it (D-075)."""
    return {k: v for k, v in data.items() if k != "provenance"}


def _v5_to_v6(data: Data) -> Data:
    """v6 dropped power `mode` (the ideal supply is always on, D-091) and added `texts`
    (none in an older file). A `custom` file's own supply becomes the ideal one."""
    out = dict(data)
    if "power" in data:
        power = {k: v for k, v in data["power"].items() if k != "mode"}
        out["power"] = power
        if data["power"].get("mode") == "custom":
            out = _own_supply_to_ideal(out)
    return out


def _own_supply_to_ideal(data: Data) -> Data:
    """Each DC source that drives V+ or V- from GND, straight or through one series
    resistor, is removed and its voltage becomes the rail's. Through a resistor, a rail
    label takes the source's pin, so the resistor stays as drawn. Other DC sources stay,
    now on nets of their own."""
    parts = TypeAdapter(list[Part]).validate_python(
        [q for p in data.get("parts", []) for q in _as_today(p)], context={"old_refs": True}
    )
    wires = TypeAdapter(list[Wire]).validate_python(data.get("wires", []))
    labels = TypeAdapter(list[Label]).validate_python(data.get("labels", []))
    try:
        drawing = Circuit.model_construct(
            schema_=SCHEMA_VERSION, id="migrating", name="", parts=parts, wires=wires, labels=labels
        )
        nets = connect(drawing)
    except ConnectivityError:
        return data  # contradictory wiring: loading reports it, nothing to work out here
    rails = dict(data["power"].get("rails", {}))
    removed: set[str] = set()
    added: list[dict[str, Any]] = []
    for p in parts:
        if not isinstance(p, VSource) or not (found := _rail_driven(p, nets, parts, set(rails))):
            continue
        rail, pin, series = found
        volts = parse_value(p.value) * (1.0 if pin == "+" else -1.0)
        if volts * (1.0 if rail == "V+" else -1.0) <= 0:
            continue  # wrongly signed: left in, the rules say what's wrong with it
        rails[rail] = volts
        removed.add(p.ref)
        if series:
            added.append({"net": rail, "pos": list(pin_positions(p)[pin])})
    if not removed:
        return data
    return {
        **data,
        "power": {**data["power"], "rails": rails},
        "parts": [p for p in data["parts"] if p.get("ref") not in removed],
        "labels": [*data.get("labels", []), *added],
        "notes": {k: v for k, v in data.get("notes", {}).items()
                  if k.removeprefix("part:") not in removed},
    }  # fmt: skip


def _as_today(part: Data) -> list[Data]:
    """An old part as today's schema reads it, for working out its nets: an op-amp
    without its pre-v12 `supply` field, a switch as its v14 poles."""
    if part.get("type") == "switch":
        return _switch_poles(part)[0]
    return [{k: v for k, v in part.items() if k != "supply"}]


def _rail_driven(
    source: VSource, nets: Nets, parts: list[Part], rails: set[str]
) -> tuple[str, str, bool] | None:
    """(rail, the source's pin on its side, through a resistor?) if `source` drives a
    rail from GND."""
    for pin, other in (("+", "-"), ("-", "+")):
        if nets.net_of(source.ref, other) != GROUND:
            continue
        net = nets.net_of(source.ref, pin)
        if net in rails:
            return net, pin, False
        if net == GROUND or len(nets.members[net]) != 2:
            continue
        (ref, end) = next(m for m in nets.members[net] if m[0] != source.ref)
        series = next((p for p in parts if p.ref == ref), None)
        if isinstance(series, Resistor):
            far = nets.net_of(ref, "2" if end == "1" else "1")
            if far in rails:
                return far, pin, True
    return None


def _v6_to_v7(data: Data) -> Data:
    """v7 added the `chargepump` part (D-093); nothing in a v6 file changes."""
    return data


def _v7_to_v8(data: Data) -> Data:
    """v8 gave the guitar a pickup `kind`, a `cable` and a volume pot (D-096), all off by
    default: a v7 pickup's one capacitance (coil and cable together) stays as its coil's,
    so a v7 file sounds the same."""
    return data


def _v8_to_v9(data: Data) -> Data:
    """v9 let a label (a supply's symbol) be turned, `rot` (D-117), 0 by default: a v8
    file draws as before."""
    return data


def _v9_to_v10(data: Data) -> Data:
    """v10 let a transistor carry its measured gain (`measured.hfe`, D-130), none by
    default: a v9 transistor uses its model's, as before."""
    return data


def _v10_to_v11(data: Data) -> Data:
    """v11 let a measured transistor carry its leakage (`measured.leakage`, D-130); a v10
    one has none, so it leaks as its model does, as before."""
    return data


# The dual op-amp models when chips came in (v12): a v11 file can name no other dual
V11_DUALS = frozenset({"TL072", "RC4558"})
V11_SUPPLY = ("V+", "GND")  # a v11 op-amp's supply when the file doesn't say
SPARE_STEP = 120  # how far from half a an added half b is tried (schematic units)
CHIP_BOX = 40  # a half's reach from its position, leads included


def _v11_to_v12(data: Data) -> Data:
    """v12 drew op-amps as chips (D-140). Op-amps on a dual model pair up into chips, in
    ref order among those with the same model and supply (U1 and U2 → IC1a and IC1b); one
    left over gets a half b of its own, placed clear of the drawing, unused. Singles
    become IC1, IC2… The hidden `supply` becomes labels on the V+ and V- pins of each
    single and each half a. Everything naming a renamed part follows: notes, probes,
    bias targets. The netlist is the same, by its new names."""
    parts = [dict(p) for p in data.get("parts", [])]
    opamps = sorted(
        (p for p in parts if p.get("type") == "opamp"), key=lambda p: _ref_key(p["ref"])
    )
    if not opamps:
        return data
    taken = {p["ref"] for p in parts if p.get("type") != "opamp"}
    renamed: dict[str, str] = {}
    labels = [dict(lb) for lb in data.get("labels", [])]
    added: list[Data] = []
    n = 0
    for chip in _chips(opamps):
        n = _next_chip(n, taken)
        name, power = f"IC{n}", chip[0]
        dual = power["model"] in V11_DUALS
        for half, p in zip("ab", chip, strict=False):
            renamed[p["ref"]] = f"{name}{half}" if dual else name
            if dual:
                p["half"] = half
        if dual and len(chip) == 1:
            added.append(_spare_half(data, power, f"{name}b"))
        labels += _power_labels(power, power.get("supply", V11_SUPPLY))
    wires = [*data.get("wires", []), *_comp_jumpers(data, opamps)]
    for p in parts:
        if p.get("type") == "opamp":
            p.pop("supply", None)
    out = {**data, "parts": [*parts, *added], "labels": labels}
    if wires:
        out["wires"] = wires
    return _rename_refs(out, renamed)


def _rename_refs(data: Data, renamed: Mapping[str, str]) -> Data:
    """`data` with parts renamed (old ref → new), and everything naming them: `part:`
    notes, probes and bias targets on a pin (`U1.out`)."""
    parts = []
    for p in data.get("parts", []):
        p = {**p, "ref": renamed.get(p["ref"], p["ref"])}
        target = p.get("bias_target")
        if isinstance(target, dict) and "node" in target:
            p["bias_target"] = {**target, "node": _renamed_pin(target["node"], renamed)}
        parts.append(p)
    out = {**data, "parts": parts}
    if "notes" in data:
        out["notes"] = {
            (f"part:{renamed[k[5:]]}" if k.startswith("part:") and k[5:] in renamed else k): v
            for k, v in data["notes"].items()
        }
    if "probes" in data:
        out["probes"] = {k: _renamed_pin(v, renamed) for k, v in data["probes"].items()}
    return out


def _v12_to_v13(data: Data) -> Data:
    """v13 fixed each part type's refs (D-141, `refs.py`): a ref that doesn't fit gets its
    type's prefix, keeping its number where that's free (P1 → VR1, RT2 → TR2, S1 → SW1,
    an LED's L3 → LED3), else the one after the highest (FUZZ → VR1, RB → R34). A dual's halves
    end in capitals (IC1a → IC1A). The guitar input is IN and the amp OUT. A pot, trimmer
    or switch named by its ref (FUZZ) keeps the name as its label (Fuzz)."""
    parts = [dict(p) for p in data.get("parts", [])]
    renamed: dict[str, str] = {}
    taken = {p["ref"] for p in parts if _fits(p)}
    for chip, halves in _chip_groups(parts).items():
        if all(_fits(h) for h in halves):
            continue
        name = chip if not ref_problem("opamp", chip) and chip not in taken else None
        name = name or _free("IC", ref_number(chip), taken, chip_refs=True)
        for h in halves:
            renamed[h["ref"]] = name + HALVES[h["half"]]
        taken |= {name, *renamed.values()}
    for p in parts:
        if _fits(p) or p["ref"] in renamed:
            continue
        kind = p.get("type", "")
        if kind in FIXED:
            new = FIXED[kind]
        else:
            is_chip = kind in ("opamp", "chargepump")
            new = _free(PREFIXES[kind][0], ref_number(p["ref"]), taken, chip_refs=is_chip)
        if kind in NAMED and not p.get("label") and ref_number(p["ref"]) is None:
            p["label"] = p["ref"].title()  # FUZZ: its name was its ref
        renamed[p["ref"]] = new
        taken.add(new)
    return _rename_refs({**data, "parts": parts}, renamed)


def _fits(part: Data) -> bool:
    kind = part.get("type", "")
    known = kind in FIXED or kind in PREFIXES  # an unknown type: loading says what's wrong
    return not known or ref_problem(kind, part["ref"], part.get("half")) is None


def _chip_groups(parts: list[Data]) -> dict[str, list[Data]]:
    """A dual's halves by chip (IC1: IC1a, IC1b)."""
    groups: dict[str, list[Data]] = {}
    for p in parts:
        if p.get("type") == "opamp" and p.get("half"):
            groups.setdefault(p["ref"][:-1], []).append(p)
    return groups


def _free(prefix: str, number: int | None, taken: set[str], chip_refs: bool = False) -> str:
    """`prefix` and `number` if no part has that ref, else the number after the highest
    in use (a gap may be the published schematic's own: the TS808's RB → R34, not R7). For a chip,
    its halves' refs (IC1A, IC1B) must be free too."""

    def free(ref: str) -> bool:
        return not ({ref, f"{ref}A", f"{ref}B"} if chip_refs else {ref}) & taken

    if number and free(f"{prefix}{number}"):
        return f"{prefix}{number}"
    used = [n for r in taken if r.startswith(prefix) and (n := ref_number(r)) is not None
            and _numbered(prefix, r)]  # fmt: skip
    return f"{prefix}{max(used, default=0) + 1}"


def _numbered(prefix: str, ref: str) -> bool:
    """`ref` is `prefix`, a number and maybe a half's letter (R12 for R, not RT1)."""
    return ref[len(prefix) :].rstrip("AB").isdigit()


def _chips(opamps: list[Data]) -> list[list[Data]]:
    """v11 op-amps (in ref order) as chips: a dual model's in pairs, by model and supply,
    in the order each pair's first appears; a single model's one each."""
    waiting: dict[tuple[str, tuple[str, ...]], list[Data]] = {}  # a chip with half b free
    chips: list[list[Data]] = []
    for p in opamps:
        key = (p["model"], tuple(p.get("supply", V11_SUPPLY)))
        if p["model"] in V11_DUALS and key in waiting:
            waiting.pop(key).append(p)
            continue
        chips.append([p])
        if p["model"] in V11_DUALS:
            waiting[key] = chips[-1]
    return chips


V11_COMP = {"comp1": (-10, -40), "comp2": (10, -40)}  # where v11 drew the compensation pins


def _comp_jumpers(data: Data, opamps: list[Data]) -> list[Data]:
    """v12 moved the compensation pins out by 10 to make room for V+ between them: a wire
    from each new pin to where the old one was keeps whatever was wired there."""
    touched = {tuple(w[end]) for w in data.get("wires", []) for end in ("from", "to")}
    touched |= {tuple(lb["pos"]) for lb in data.get("labels", [])}
    jumpers = []
    for p in opamps:
        for pin, old in V11_COMP.items():
            was = tuple(_offset(p, old))
            if was in touched:
                jumpers.append({"from": _offset(p, PIN_OFFSETS["opamp"][pin]), "to": list(was)})
    return jumpers


def _ref_key(ref: str) -> tuple[str, int, str]:
    """Refs in the order people count them: U2 before U10."""
    head = ref.rstrip("0123456789")
    tail = ref[len(head) :]
    return (head, int(tail), "") if tail else (ref, 0, "")


def _next_chip(n: int, taken: set[str]) -> int:
    """The next chip number whose refs (ICn, ICna, ICnb) no other part uses."""
    n += 1
    while {f"IC{n}", f"IC{n}a", f"IC{n}b"} & taken:
        n += 1
    return n


def _renamed_pin(name: object, renamed: Mapping[str, str]) -> object:
    """`U1.out` → `IC1a.out` (anything else unchanged)."""
    if not isinstance(name, str):
        return name
    ref, dot, pin = name.partition(".")
    return f"{renamed[ref]}.{pin}" if dot and ref in renamed else name


def _offset(part: Data, offset: tuple[int, int]) -> list[int]:
    x, y = part.get("pos", (0, 0))
    dx, dy = rotate(offset, part.get("rot", 0))
    return [x + dx, y + dy]


def _power_labels(part: Data, supply: object) -> list[Data]:
    """Labels on a chip's V+ and V- pins naming its old supply, turned with the part."""
    pos, neg = (list(supply) if isinstance(supply, list | tuple) else list(V11_SUPPLY))[:2]
    rot = part.get("rot", 0)
    found = []
    for net, pin in ((pos, "V+"), (neg, "V-")):
        label: Data = {"net": net, "pos": _offset(part, PIN_OFFSETS["opamp"][pin])}
        if rot:
            label["rot"] = rot
        found.append(label)
    return found


def _spare_half(data: Data, half_a: Data, ref: str) -> Data:
    """A dual's half b for an op-amp left over, beside half a where nothing is drawn."""
    x, y = half_a.get("pos", (0, 0))
    for step in range(1, 20):
        for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step)):
            spot = (x + dx * SPARE_STEP, y + dy * SPARE_STEP)
            if _clear(data, spot):
                return {"ref": ref, "type": "opamp", "pos": list(spot), "model": half_a["model"],
                        "half": "b"}  # fmt: skip
    return {"ref": ref, "type": "opamp", "pos": [x + SPARE_STEP, y], "model": half_a["model"],
            "half": "b"}  # fmt: skip


def _clear(data: Data, spot: tuple[int, int]) -> bool:
    """Nothing drawn within a chip's reach of `spot`: no part, wire or label."""
    x, y = spot
    lo_x, hi_x, lo_y, hi_y = x - 2 * CHIP_BOX, x + 2 * CHIP_BOX, y - 2 * CHIP_BOX, y + 2 * CHIP_BOX
    points = [p.get("pos", (0, 0)) for p in data.get("parts", [])]
    points += [lb["pos"] for lb in data.get("labels", [])]
    if any(lo_x <= px <= hi_x and lo_y <= py <= hi_y for px, py in points):
        return False
    for w in data.get("wires", []):
        (ax, ay), (bx, by) = w["from"], w["to"]
        if (
            min(ax, bx) <= hi_x
            and max(ax, bx) >= lo_x
            and min(ay, by) <= hi_y
            and max(ay, by) >= lo_y
        ):
            return False
    return True


POLE_STEP = 60  # how far apart a v13 switch's poles were drawn (schematic units)


def _v13_to_v14(data: Data) -> Data:
    """v14 picked switches by type (D-143): a v13 switch's poles and throws become a type
    (2 poles, 2 throws: a DPDT), and each pole of a multi-pole one its own part (SW1 →
    SW1A, SW1B), where the pole was drawn, so every wire still meets its lug. Pins are
    the lugs (1C, 1T1, 1T2 → A2, A1, A3). Notes on the switch go to its first pole;
    probes and bias targets on its pins follow."""
    parts: list[Data] = []
    pins: dict[str, str] = {}  # old "ref.pin" → new
    renamed: dict[str, str] = {}
    for p in data.get("parts", []):
        if p.get("type") != "switch" or "kind" in p:  # a kind: already a v14 pole
            parts.append(p)
            continue
        poles, moved = _switch_poles(p)
        parts += poles
        pins |= moved
        if poles[0]["ref"] != p["ref"]:
            renamed[p["ref"]] = poles[0]["ref"]
    if not pins:
        return data
    out = {**data, "parts": [_moved_target(p, pins) for p in parts]}
    if "probes" in data:  # pins first: then the refs left are the switch's own
        out["probes"] = {k: pins.get(v, v) for k, v in data["probes"].items()}
    return _rename_refs(out, renamed)


def _switch_poles(part: Data) -> tuple[list[Data], dict[str, str]]:
    """A v13 switch as its v14 parts (one per pole) and its pins' new names."""
    poles = int(part.get("poles", 1))
    throws = int(part.get("throws", 2))
    kind_id, position = from_poles_throws(poles, throws, int(part.get("position", 0)))
    kind = kind_of(kind_id)
    base = {k: v for k, v in part.items() if k not in ("poles", "throws", "position")}
    out: list[Data] = []
    pins: dict[str, str] = {}
    for i in range(poles):
        letter = POLE_LETTERS[i].lower() if poles > 1 else None
        ref = f"{part['ref']}{POLE_LETTERS[i]}" if letter else part["ref"]
        pole: Data = {**base, "ref": ref, "kind": kind_id, "position": position}
        if letter:
            pole["pole"] = letter
            pole["pos"] = _offset(part, (0, POLE_STEP * i))
        out.append(pole)
        pins[f"{part['ref']}.{i + 1}C"] = f"{ref}.{lug_name(kind, letter, kind.common)}"
        for t, lug in enumerate(kind.throws[:throws], start=1):
            pins[f"{part['ref']}.{i + 1}T{t}"] = f"{ref}.{lug_name(kind, letter, lug)}"
    return out, pins


def _moved_target(part: Data, pins: Mapping[str, str]) -> Data:
    """A trimmer's bias target that was on a v13 switch pin, on the lug it became."""
    target = part.get("bias_target")
    if isinstance(target, dict) and target.get("node") in pins:
        return {**part, "bias_target": {**target, "node": pins[target["node"]]}}
    return part


def _v14_to_v15(data: Data) -> Data:
    """v15 drew switches as KiCad does (D-143): a pole's throws above and below its
    common (an SPDT's 1 above, 3 below) instead of level with it and down. A rotary of
    three or more throws moves down so its throws stay where they were, and a wire joins
    its common to where the common was; a two-throw pole gets a wire from its new first
    throw down to where it was. Only where something met the lug: a wire, a label or
    another part's pin."""
    points = {tuple(w[end]) for w in data.get("wires", []) for end in ("from", "to")}
    points |= {tuple(lb["pos"]) for lb in data.get("labels", [])}
    pins = [(p.get("ref"), at) for p in data.get("parts", []) for at in _v14_pins(p)]
    parts: list[Data] = []
    jumpers: list[Data] = []
    for p in data.get("parts", []):
        kind = KINDS.get(str(p.get("kind", DEFAULT_KIND))) if p.get("type") == "switch" else None
        throws = len(kind.throws) if kind else 0  # an unknown type: the schema says so
        if throws < 2:
            parts.append(p)
            continue
        new = throw_offsets(throws)
        shift = 0 if throws == 2 else -new[0]  # keeps a rotary's throws where they were
        parts.append({**p, "pos": _offset(p, (0, shift))} if shift else p)
        met = points | {at for ref, at in pins if ref != p.get("ref")}
        old_new = [((-20, 0), (-20, shift))] + [
            ((20, 20 * i), (20, y + shift)) for i, y in enumerate(new)
        ]
        for was, now in old_new:
            at, to = _offset(p, was), _offset(p, now)
            if at != to and tuple(at) in met:
                jumpers.append({"from": to, "to": at})
    if not jumpers and parts == data.get("parts", []):
        return data
    return {**data, "parts": parts, "wires": [*data.get("wires", []), *jumpers]}


LEGACY_RING = "IN_ring"  # v15's battery return, grounded only by a stereo input


def _v15_to_v16(data: Data) -> Data:
    """v16 grounds the battery's - always (D-164): v15's `IN_ring` label reached ground
    only through a stereo input's ring, so with a mono input the battery floated. Each
    `IN_ring` label becomes a GND label, and a block's `IN_ring` port goes, ground
    needing none."""
    labels = data.get("labels", [])
    ports = data.get("ports", {})
    if not any(lb.get("net") == LEGACY_RING for lb in labels) and LEGACY_RING not in ports:
        return data
    out = {
        **data,
        "labels": [{**lb, "net": GROUND} if lb.get("net") == LEGACY_RING else lb for lb in labels],
    }
    if "ports" in data:
        out["ports"] = {k: v for k, v in ports.items() if LEGACY_RING not in (k, v)}
    return out


# The ElectroSmash AC128 cards (D-130) and what each read on the Geofex tester: gain and
# leakage (A). v17 replaces both with one AC128 fitted to Valvo's sheet (D-170).
OLD_AC128 = {"AC128-B85": (79.4, 9.8e-6), "AC128-B120": (110.4, 1.4e-5)}


def _v16_to_v17(data: Data) -> Data:
    """v17 has one AC128 card (D-170). A part on AC128-B85 or -B120 moves to it as a
    measured transistor: its own measured gain and leakage where it has them, else what
    the old card read on the tester, so the circuit behaves as it did."""
    parts = []
    for part in data.get("parts", []):
        old = OLD_AC128.get(str(part.get("model"))) if part.get("type") == "bjt" else None
        if old is not None:
            measured = part.get("measured") or {}
            leakage = measured.get("leakage")
            part = {
                **part,
                "model": "AC128",
                "measured": {
                    "hfe": measured.get("hfe", old[0]),
                    "leakage": old[1] if leakage is None else leakage,
                },
            }
        parts.append(part)
    return data if parts == data.get("parts", []) else {**data, "parts": parts}


def _v17_to_v18(data: Data) -> Data:
    """v18 only adds (D-172): a quad op-amp's halves c and d, and the part types 9b adds.
    A v17 file is a v18 file as it stands; the bump stops an older Solum Builder from
    misreading a file that uses them."""
    return data


# where v19 tries a dual's power unit, beside its half a (before the half's rotation): the
# first spot whose pins and jumpers touch nothing else in the drawing (D-179)
POWER_SPOTS = (60, -60, 80, -80, 100, -100, 120, -120, 160, -160, 200, -200)
POWER_OFFSETS = {"V+": (0, -40), "V-": (0, 40)}
Segment = tuple[tuple[int, ...], tuple[int, ...]]  # v18's half a and v19's power unit alike


def _v18_to_v19(data: Data) -> Data:
    """v19 gives a dual or quad op-amp a power unit (D-179), as KiCad draws a TL072's unit
    C: half a's V+ and V- pins move onto it (IC1C, IC1E: the letter after the last half).
    It sits beside half a, turned with it, at the first spot where it touches nothing: its
    pins on no point or wire, its body crossing no wire and over no other part; failing
    that, when its supply is labelled, past the drawing's right edge.
    Each pin then gets the label its old pin's net had (V+, GND; a label that sat alone on
    the old pin moves), or, on a net with no label, a short wire to where the old pin
    was. With no clear spot at all it sits on half a, its pins where the old ones were.
    Every connection stays as it was."""
    parts = data.get("parts", [])
    chips: dict[str, list[Data]] = {}
    for part in parts:
        if part.get("type") == "opamp" and part.get("half"):
            chips.setdefault(str(part["ref"])[:-1], []).append(part)
    if not chips:
        return data
    wires: list[Data] = list(data.get("wires", []))
    labels: list[Data] = list(data.get("labels", []))
    added: list[Data] = []
    for chip, halves in chips.items():
        first = next((h for h in halves if h.get("half") == "a"), None)
        if first is None:
            continue  # the schema says what's missing
        segments: list[Segment] = [(tuple(w["from"]), tuple(w["to"])) for w in wires]
        points = {end for seg in segments for end in seg} | {tuple(lb["pos"]) for lb in labels}
        outlines = [pins for part in [*parts, *added] if (pins := _v14_pins(part))]
        points |= {at for pins in outlines for at in pins}
        last = max(str(h["half"]) for h in halves).upper()
        unit = {
            "ref": f"{chip}{chr(ord(last) + 1)}",
            "type": "powerunit",
            "model": first.get("model"),
            "pos": first.get("pos"),
            "rot": first.get("rot", 0),
        }
        old = {pin: tuple(_offset(first, at)) for pin, at in POWER_OFFSETS.items()}
        joined = {pin: _joined(at, segments, points) for pin, at in old.items()}
        net = {pin: _label_on(joined[pin], labels) for pin in old}
        met = {pin for pin in old if len(joined[pin]) > 1 or old[pin] in points}
        spots = [{**unit, "pos": _offset(first, (dx, 0))} for dx in POWER_SPOTS]
        if all(net[p] is not None for p in met):  # labels only: past the drawing's right edge
            right = max((p[0] for p in points), default=0) + 80
            level = first.get("pos", [0, 0])[1]
            spots.append({**unit, "pos": [right - right % 20, level], "rot": 0})
        for spot in spots:
            new = {pin: tuple(_offset(spot, at)) for pin, at in POWER_OFFSETS.items()}
            jumpers = [
                seg for p in met if net[p] is None for seg in _jumper(first, old[p], new[p], p)
            ]
            body = (new["V+"], new["V-"])
            if _spot_clear(body, jumpers, points, segments, joined) and not any(
                _overlaps(body, pins) for pins in outlines
            ):
                unit = spot
                for pin in met:
                    if net[pin] is not None:
                        labels = [lb for lb in labels if not _alone(lb, old[pin], segments)]
                        labels.append({"net": net[pin], "pos": list(new[pin])})
                wires += [
                    {"from": list(a), "to": list(b)}
                    for a, b in jumpers
                    if (a, b) not in segments and (b, a) not in segments
                ]
                break
        added.append(unit)
    return {**data, "parts": [*parts, *added], "wires": wires, "labels": labels}


def _jumper(half: Data, old: tuple[int, ...], new: tuple[int, ...], pin: str) -> list[Segment]:
    """A wire from half a's old power pin to the unit's: out 20 (away from the op-amp,
    clear of its own pins' row), across, and back in."""
    dx, dy = rotate((0, -20 if pin == "V+" else 20), half.get("rot", 0))
    a, b = (old[0] + dx, old[1] + dy), (new[0] + dx, new[1] + dy)
    return [(old, a), (a, b), (b, new)]


def _joined(
    start: tuple[int, ...], segments: list[Segment], points: set[tuple[int, ...]]
) -> set[tuple[int, ...]]:
    """The drawing's points wired to `start` (through wires, and points on them)."""
    found, todo = {start}, [start]
    while todo:
        here = todo.pop()
        for a, b in segments:
            if _on(here, a, b):
                for p in [a, b, *(q for q in points if _on(q, a, b))]:
                    if p not in found:
                        found.add(p)
                        todo.append(p)
    return found


def _alone(label: Data, pin: tuple[int, ...], segments: list[Segment]) -> bool:
    """A label sitting on half a's old power pin with no wire there: it labelled only the
    pin, so it moves with it."""
    return tuple(label["pos"]) == pin and not any(_on(pin, a, b) for a, b in segments)


def _label_on(points: set[tuple[int, ...]], labels: list[Data]) -> str | None:
    return next((str(lb["net"]) for lb in labels if tuple(lb["pos"]) in points), None)


def _on(p: tuple[int, ...], a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    return on_segment((p[0], p[1]), (a[0], a[1]), (b[0], b[1]))


def _near(p: tuple[int, ...], a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """`p` within the unit's body: 10 either side of the line from pin `a` to pin `b`."""
    (x0, x1), (y0, y1) = sorted((a[0], b[0])), sorted((a[1], b[1]))
    return x0 - 10 <= p[0] <= x1 + 10 and y0 - 10 <= p[1] <= y1 + 10


def _overlaps(body: Segment, pins: list[tuple[int, ...]]) -> bool:
    """The unit's body (10 either side of its pins' line) over a part's: the box round its
    pins (a resistor's body lies between its two)."""
    xs, ys = [p[0] for p in pins], [p[1] for p in pins]
    (x0, x1), (y0, y1) = sorted((body[0][0], body[1][0])), sorted((body[0][1], body[1][1]))
    return x0 - 10 <= max(xs) and min(xs) <= x1 + 10 and y0 - 10 <= max(ys) and min(ys) <= y1 + 10


def _crosses(one: Segment, two: Segment) -> bool:
    """Two segments meet (touching counts)."""

    def side(p: tuple[int, ...], q: tuple[int, ...], r: tuple[int, ...]) -> int:
        cross = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (cross > 0) - (cross < 0)

    (a, b), (c, d) = one, two
    if side(a, b, c) != side(a, b, d) and side(c, d, a) != side(c, d, b):
        return True
    return any(_on(p, q, r) for p, (q, r) in ((c, one), (d, one), (a, two), (b, two)))


def _spot_clear(
    pins: tuple[tuple[int, ...], tuple[int, ...]],
    jumpers: list[Segment],
    points: set[tuple[int, ...]],
    segments: list[Segment],
    joined: Mapping[str, set[tuple[int, ...]]],
) -> bool:
    """New pins on no existing point or wire, the body between them (20 wide) crossing no
    wire and covering no point, and jumpers only through points already on their own net."""
    top, bottom = pins
    if any(at in points or any(_on(at, a, b) for a, b in segments) for at in (top, bottom)):
        return False
    if any(_near(p, top, bottom) for p in points) or any(
        _crosses((top, bottom), seg) for seg in segments
    ):
        return False
    own = [js for js in joined.values()]  # a jumper may cross its own net's points only
    return not any(
        _on(p, a, b) and not any(a in js and p in js for js in own)
        for a, b in jumpers
        for p in points
    )


def _v14_pins(part: Data) -> list[tuple[int, ...]]:
    """Where a v14 part's pins were: a switch's lugs as v14 drew them (the common at
    (-20, 0), the throws at (20, 0), (20, 20)…), anything else as today (only switches
    moved); none for a part today's schema can't read (it says why later)."""
    if part.get("type") == "switch":
        kind = KINDS.get(str(part.get("kind", DEFAULT_KIND)))
        throws = len(kind.throws) if kind else 0
        return [
            tuple(_offset(part, at)) for at in [(-20, 0), *((20, 20 * i) for i in range(throws))]
        ]
    try:
        today = TypeAdapter(Part).validate_python(part)
    except ValueError:
        return []
    return [tuple(at) for at in pin_positions(today).values()]


def _v19_to_v20(data: Data) -> Data:
    """v20 only adds (D-180): the hex inverter and the OTA part types, and power units on
    their chips. A v19 file is a v20 file as it stands; the bump stops an older build of
    Solum Builder from misreading a file that uses them."""
    return data


def _v20_to_v21(data: Data) -> Data:
    """v21 only adds (D-185): a stereo jack's `plugged` (its cable in or out). A v20 file
    is a v21 file as it stands: every jack's cable is in, as v20 assumed."""
    return data


def _v21_to_v22(data: Data) -> Data:
    """v22 only adds (9c): a custom switch's own contacts (`custom`, kind `custom`). A v21
    file is a v22 file as it stands: its switches are all built-in types."""
    return data


def _v22_to_v23(data: Data) -> Data:
    """v23 only adds (D-204): the circuit's `enclosure`. A v22 file is a v23 file as it
    stands: no enclosure chosen."""
    return data


def _v23_to_v24(data: Data) -> Data:
    """v24 only adds (D-217): a pot's `gang`, for dual pots. A v23 file is a v24 file as it
    stands: every pot is single."""
    return data


def _v24_to_v25(data: Data) -> Data:
    """v25 only adds (D-218): a charge pump's `both` mode. A v24 file is a v25 file as it
    stands."""
    return data


V25_PUMP_PINS = {"in": (-40, 0), "out": (40, 0), "gnd": (0, 40), "neg": (40, 20)}
V25_SHEET_CAP = {"LT1054": "100µ"}  # the cap each chip's r_out was measured with; else 10µ
PUMP_SPOT = (-140, -120, 100, 60)  # what v26's drawn pump covers round its chip: x0, y0, x1, y1


def _v25_to_v26(data: Data) -> Data:
    """v26 draws a charge pump's parts (D-226): the chip has its real pins (in 8, cap+ 2,
    gnd 3, cap- 4, out 5), and the caps and diodes v25 kept inside it are parts. Each
    pump is redrawn at the nearest clear spot, with its sheet's cap (the one its output
    resistance was measured with) and its `diode` as D1 and D2, so it simulates as
    before. It joins its old nets by labels: each old pin's net keeps its label, or gets
    one named after the pin (U1_OUT) where the old pin was. Probes and bias targets on
    its old pins follow (a doubler's `out` is now its second diode's cathode)."""
    parts: list[Data] = list(data.get("parts", []))
    pumps = [p for p in parts if p.get("type") == "chargepump"]
    if not pumps:
        return data
    wires: list[Data] = list(data.get("wires", []))
    labels: list[Data] = list(data.get("labels", []))
    moved: dict[str, str] = {}
    for pump in pumps:
        parts.remove(pump)
        segments: list[Segment] = [(tuple(w["from"]), tuple(w["to"])) for w in wires]
        pins = [at for part in parts for at in _v14_pins(part)]
        points = {*pins, *(tuple(lb["pos"]) for lb in labels)}
        ref, mode = str(pump["ref"]), pump.get("mode", "doubler")
        nets: dict[str, str] = {}
        for name, offset in V25_PUMP_PINS.items():
            if name == "neg" and mode != "both":
                continue
            at = tuple(_offset(pump, offset))
            used = at in points or any(_on(at, a, b) for a, b in segments)
            found = _label_on(_joined(at, segments, points), labels) if used else None
            nets[name] = found or ("GND" if name == "gnd" else f"{ref}_{name.upper()}")
            labels = [lb for lb in labels if not (_alone(lb, at, segments) and at not in pins)]
            if used and found is None:
                labels.append({"net": nets[name], "pos": list(at)})
        drawn, more_wires, more_labels, outputs = _drawn_pump(pump, mode, nets, parts)
        parts += drawn
        moved |= {f"{ref}.{old}": new for old, new in outputs.items()}
        spot = _pump_spot(pump, [*pins, *(tuple(lb["pos"]) for lb in labels)], segments)
        for item in [*drawn, *more_labels]:
            item["pos"] = [item["pos"][0] + spot[0], item["pos"][1] + spot[1]]
        for w in more_wires:
            w["from"] = [w["from"][0] + spot[0], w["from"][1] + spot[1]]
            w["to"] = [w["to"][0] + spot[0], w["to"][1] + spot[1]]
        wires += more_wires
        labels += more_labels
    out = {**data, "parts": [_moved_target(p, moved) for p in parts], "wires": wires,
           "labels": labels}  # fmt: skip
    if "probes" in data:
        out["probes"] = {k: moved.get(v, v) for k, v in data["probes"].items()}
    return out


def _drawn_pump(
    pump: Data, mode: str, nets: Mapping[str, str], parts: list[Data]
) -> tuple[list[Data], list[Data], list[Data], dict[str, str]]:
    """v26's pump round its chip at (0, 0): the parts, wires and labels, and where each
    old pin went. CAP+ (left, 2) runs to the flying cap further left (CAP- under it, 4)
    and up to the pump cap, whose junction sits between D1 (from V+) and D2 (to the
    doubled output) above; V+ (8) and VOUT (5) on the right, GND (3) left."""

    def next_ref(prefix: str) -> str:
        refs = [str(p["ref"]) for p in parts]
        taken = [ref_number(r) or 0 for r in refs if r[:1] == prefix and r[1:].isdigit()]
        number = max(taken, default=0) + 1 + sum(1 for p in made if p["ref"][0] == prefix)
        return f"{prefix}{number}"

    ref = str(pump["ref"])
    cap = V25_SHEET_CAP.get(str(pump.get("model")), "10µ")
    chip = {k: v for k, v in pump.items() if k not in ("mode", "diode", "rot")}
    made: list[Data] = []
    wires: list[list[int]] = []
    labels: list[Data] = [{"net": nets["in"], "pos": [40, -30]},
                          {"net": nets["gnd"], "pos": [-40, 10], "rot": 90}]  # fmt: skip
    outputs: dict[str, str] = {}
    doubler, inverter = mode in ("doubler", "both"), mode in ("inverter", "both")
    if inverter:
        flying = {"ref": next_ref("C"), "type": "capacitor", "pos": [-100, 10], "rot": 90,
                  "value": cap, "kind": "electrolytic", "rating_v": 25.0}  # fmt: skip
        made.append(flying)
        wires += [[-40, -10, -100, -10], [-40, 30, -100, 30], [40, 30, 60, 30]]
        negative = nets["neg" if mode == "both" else "out"]
        labels.append({"net": negative, "pos": [60, 30], "rot": 90})
        outputs["neg" if mode == "both" else "out"] = f"{ref}.out"
    else:
        labels.append({"net": nets["gnd"], "pos": [40, 30]})
    if doubler:
        diode = str(pump.get("diode", "1N5817"))
        made.append({"ref": next_ref("C"), "type": "capacitor", "pos": [-60, -70], "rot": 90,
                     "value": cap, "kind": "electrolytic", "rating_v": 25.0})  # fmt: skip
        low = {"ref": next_ref("D"), "type": "diode", "pos": [-100, -90], "model": diode}
        made.append(low)
        high = {"ref": next_ref("D"), "type": "diode", "pos": [-20, -90], "model": diode}
        made.append(high)
        if not inverter:
            wires.append([-40, -10, -60, -10])
        wires += [[-60, -50, -60, -10], [-80, -90, -40, -90]]
        labels += [{"net": nets["in"], "pos": [-120, -90]}, {"net": nets["out"], "pos": [0, -90]}]
        outputs["out"] = f"{high['ref']}.K"
    drawn = [{**chip, "pos": [0, 0]}, *made]
    return drawn, [{"from": w[:2], "to": w[2:]} for w in wires], labels, outputs


def _pump_spot(
    pump: Data, points: list[tuple[int, ...]], segments: list[Segment]
) -> tuple[int, int]:
    """Where v26's drawn pump goes: the clear spot (`PUMP_SPOT` round it: no point, no
    wire) nearest the old chip; failing that, past the drawing's right edge."""
    x, y = pump.get("pos", (0, 0))
    x0, y0, x1, y1 = PUMP_SPOT

    def clear(cx: int, cy: int) -> bool:
        box = (cx + x0, cy + y0, cx + x1, cy + y1)
        if any(box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3] for p in points):
            return False
        return not any(
            min(a[0], b[0]) <= box[2] and max(a[0], b[0]) >= box[0]
            and min(a[1], b[1]) <= box[3] and max(a[1], b[1]) >= box[1]
            for a, b in segments
        )  # fmt: skip

    spots = sorted(((dx, dy) for dx in range(-600, 601, 20) for dy in range(-600, 601, 20)),
                   key=lambda d: (abs(d[0]) + abs(d[1]), d))  # fmt: skip
    for dx, dy in spots:
        if clear(x + dx, y + dy):
            return (x + dx, y + dy)
    right = max((p[0] for p in points), default=x) + 200
    return (right - right % 20, y)


def _v26_to_v27(data: Data) -> Data:
    """v27 only adds (D-227): the fixed regulator part. A v26 file is a v27 file as it
    stands."""
    return data


V27_PUMP_IN, V27_PUMP_PIN1 = (40, -30), (-40, -30)  # pin 8 (V+) and pin 1, unturned


def _v27_to_v28(data: Data) -> Data:
    """v28 wires a charge pump's boost (D-234): pin 1 on the chip's V+ is boost, as on a
    real board, so `boost` goes. A boosted pump gets a label at pin 1 naming its V+ net
    (the label on pin 8's net, or a new `U1_IN` there when it has none)."""
    parts: list[Data] = list(data.get("parts", []))
    if not any(p.get("type") == "chargepump" for p in parts):
        return data
    wires: list[Data] = list(data.get("wires", []))
    labels: list[Data] = list(data.get("labels", []))
    segments: list[Segment] = [(tuple(w["from"]), tuple(w["to"])) for w in wires]
    pins = [at for part in parts for at in _v14_pins(part)]
    points = {*pins, *(tuple(lb["pos"]) for lb in labels)}
    out: list[Data] = []
    for part in parts:
        if part.get("type") != "chargepump":
            out.append(part)
            continue
        boosted = bool(part.get("boost"))
        part = {k: v for k, v in part.items() if k != "boost"}
        out.append(part)
        if not boosted:
            continue
        at = tuple(_offset(part, V27_PUMP_IN))
        net = _label_on(_joined(at, segments, points), labels)
        if net is None:
            net = f"{part['ref']}_IN"
            labels.append({"net": net, "pos": list(at)})
        labels.append({"net": net, "pos": _offset(part, V27_PUMP_PIN1)})
    return {**data, "parts": out, "labels": labels}


def _v28_to_v29(data: Data) -> Data:
    """v29 only adds (D-238): a transistor's `off_by_design`. A v28 file is a v29 file as
    it stands: no part off by design."""
    return data


def _v29_to_v30(data: Data) -> Data:
    """v30 split the notes (9d4): a `part:REF` note goes onto that part (`note`), a
    `net:NAME` note into `net_notes`, and `notes` becomes the list of general notes. A
    note on a dual pot's or switch's name (VR1, SW1) goes on its first unit (VR1A); one
    naming no part is kept as a general note titled with its key, so nothing is lost."""
    old: Mapping[str, str] = data.get("notes") or {}
    parts: list[Data] = [dict(p) for p in data.get("parts", [])]
    by_ref = {p.get("ref"): p for p in parts}
    net_notes: dict[str, str] = {}
    general: list[Data] = []
    for key, text in old.items():
        kind, _, name = key.partition(":")
        part = by_ref.get(name) or by_ref.get(f"{name}A")
        if kind == "part" and part is not None:
            part["note"] = text
        elif kind == "net" and name:
            net_notes[name] = text
        else:
            general.append({"title": key, "text": text})
    out = {k: v for k, v in data.items() if k != "notes"}
    out["parts"] = parts
    if general:
        out["notes"] = general
    if net_notes:
        out["net_notes"] = net_notes
    return out


MIGRATIONS: dict[int, Migration] = {
    1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4, 4: _v4_to_v5, 5: _v5_to_v6, 6: _v6_to_v7,
    7: _v7_to_v8, 8: _v8_to_v9, 9: _v9_to_v10,
    10: _v10_to_v11, 11: _v11_to_v12, 12: _v12_to_v13, 13: _v13_to_v14, 14: _v14_to_v15,
    15: _v15_to_v16, 16: _v16_to_v17, 17: _v17_to_v18, 18: _v18_to_v19,
    19: _v19_to_v20, 20: _v20_to_v21, 21: _v21_to_v22, 22: _v22_to_v23,
    23: _v23_to_v24, 24: _v24_to_v25, 25: _v25_to_v26, 26: _v26_to_v27,
    27: _v27_to_v28, 28: _v28_to_v29, 29: _v29_to_v30,
}  # fmt: skip


class MigrationError(ValueError):
    """The file's schema version can't be upgraded (plain-English message)."""


def migrate(
    data: Mapping[str, Any],
    migrations: Mapping[int, Migration] = MIGRATIONS,
    current: int = SCHEMA_VERSION,
) -> Data:
    """A copy of `data` upgraded to the `current` schema version."""
    version = data.get("schema")
    if not isinstance(version, int) or isinstance(version, bool):
        raise MigrationError('This file has no "schema" version number, so it isn\'t a circuit.')
    if version > current:
        raise MigrationError(
            f"This file uses schema {version}, made by a newer Solum Builder (this one reads "
            f"up to {current}). Update Solum Builder to open it."
        )
    out = dict(data)
    while version < current:
        if version not in migrations:
            raise MigrationError(f"Files from schema {version} can't be upgraded any more.")
        out = migrations[version](out)
        version += 1
        out["schema"] = version
    return out
