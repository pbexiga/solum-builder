"""A stage's output kept away from its input (P6i2, D-404).

Two neighbouring strips couple a little through the board: enough, at high gain, for a
later node running alongside an earlier high-gain input to feed back into it and squeal
(a fuzz, a high-gain drive). A pair counts only when the later node would add to the input
(`probe.loud_inputs`' `along`: louder than the input and in phase with it, within ±90°,
at 2, 10 or 50 kHz, while the gain from the input to the output is high gain's); a stage's
own feedback (its output to its − input, its emitter) is meant, and left out there.
"Alongside" is two neighbouring strips' copper side by side for `ALONGSIDE` columns or
more, uncut. A warning, never a refusal: the board is still the circuit.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from solum.circuit.connectivity import Nets
from solum.circuit.parts import PIN_WORDS
from solum.stripboard.board import Hole, Layout, column_name
from solum.stripboard.footprints import BoardPart
from solum.stripboard.limits import LoudInput, pin_said

ALONGSIDE = 3  # columns two neighbouring strips' copper may share before they couple (P6i2)


@dataclass(frozen=True)
class Alongside:
    """A later net's copper beside a high-gain input's: the input (`ref`, `pin`: its board
    ref and leg, for the words: "Q1's base", "IC1's pin 5") and its net, the later net
    (`said`: a leg on it in words), the two strips (top first) and the first and last
    columns they share."""

    ref: str
    pin: str
    net: str
    later: str
    said: str
    strips: tuple[int, int]
    columns: tuple[int, int]


def copper_nets(layout: Layout, board: Mapping[str, BoardPart], nets: Nets,
                copper: Mapping[Hole, int]) -> dict[Hole, str]:  # fmt: skip
    """Each copper hole's net, from the legs on its joined copper (`copper`, each hole's
    group: `check.copper_groups`); copper with no leg on it has none."""
    group_net: dict[int, str] = {}
    for p in layout.parts:
        part = board.get(p.ref)
        if part is None:
            continue
        for leg, hole in p.legs:
            pin = part.pins.get(leg)
            if pin is not None and hole in copper:
                group_net.setdefault(copper[hole], nets.net_of(*pin))
    return {h: group_net[g] for h, g in copper.items() if g in group_net}


def pairs_of(nets: Nets, loud: Sequence[LoudInput]) -> dict[tuple[str, str], LoudInput]:
    """Each (high-gain input's net, later net in phase with it) → the input."""
    found: dict[tuple[str, str], LoudInput] = {}
    for entry in loud:
        net = nets.by_pin.get((entry.ref, entry.pin))
        if net is not None:
            for later in sorted(entry.along):
                found.setdefault((net, later), entry)
    return found


def alongside(layout: Layout, board: Mapping[str, BoardPart], nets: Nets,
              loud: Sequence[LoudInput],
              groups: Mapping[Hole, int]) -> list[Alongside]:  # fmt: skip
    """Each run of a later net's copper beside a high-gain input's, `ALONGSIDE` columns or
    more (the longest per pair of strips), top to bottom; `groups`: each copper hole's
    joined group (`check.copper_groups`)."""
    pairs = pairs_of(nets, loud)
    if not pairs:
        return []
    copper = copper_nets(layout, board, nets, groups)

    def pair(x: int, y: int) -> tuple[str, str] | None:
        a, b = copper.get((x, y)), copper.get((x, y + 1))
        if a is None or b is None:
            return None
        return (a, b) if (a, b) in pairs else (b, a) if (b, a) in pairs else None

    leg_of = {pin: (ref, leg) for ref, part in board.items() for leg, pin in part.pins.items()}
    found: list[Alongside] = []
    for y in range(layout.strips - 1):
        best: dict[tuple[str, str], tuple[int, int]] = {}
        here, start = None, 0
        for x in range(layout.columns + 1):
            key = pair(x, y) if x < layout.columns else None
            if key == here:
                continue
            if here is not None and x - start >= max(ALONGSIDE, _length(best.get(here)) + 1):
                best[here] = (start, x - 1)
            here, start = key, x
        for (net, later), cols in sorted(best.items()):
            entry = pairs[net, later]
            ref, leg = leg_of.get((entry.ref, entry.pin), (entry.ref, entry.pin))
            found.append(Alongside(ref, leg, net, later, net_said(board, nets, later),
                                   (y, y + 1), cols))  # fmt: skip
    return found


def _length(cols: tuple[int, int] | None) -> int:
    return cols[1] - cols[0] + 1 if cols else 0


def net_said(board: Mapping[str, BoardPart], nets: Nets, net: str) -> str:
    """A net in words by a board leg on it: a transistor's first ("Q2's collector"), else
    a chip's or other part's ("IC1's pin 1", "C3's pin 1"), else its name."""
    legs = sorted((ref, leg) for ref, part in board.items() for leg, pin in part.pins.items()
                  if nets.net_of(*pin) == net)  # fmt: skip
    named = [p for p in legs if p[1] in PIN_WORDS] or legs
    return pin_said(*named[0]) if named else net


def apart_warnings(found: Sequence[Alongside]) -> list[str]:
    """Each run in a sentence (a warning in the editor)."""
    said = []
    for f in found:
        first, last = column_name(f.columns[0]), column_name(f.columns[1])
        said.append(
            f"Strips {f.strips[0] + 1} and {f.strips[1] + 1} run side by side from {first} to "
            f"{last}: {pin_said(f.ref, f.pin)} (the high-gain stage's input) beside "
            f"{f.said}, later and in phase with it. Cut one shorter or move "
            "it a strip further, so the output can't feed back into the input and squeal."
        )
    return said
