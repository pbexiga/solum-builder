"""*Tidy up* (spec, *Automatic help*; D-388): a board made smaller in small steps, each
kept only when the board still passes the check and is no worse in size, cuts or links.

The steps are tried in a fixed order, over and over until a whole pass keeps none: take
out an empty column or strip, drop a link or a cut, slide a part left (with the cuts and
links of its own columns, then alone) or up, slide a link, a cut or a pad, shorten a link.
After each step the board is trimmed to what's on it. A step is kept when the check passes
and the board's size, cuts and links are each no worse and its measure (size, cuts, links,
the links' length, then how far everything sits from the top left) is smaller, so the
search always ends and the same board always tidies the same way. It can't break a board.

Parts placed wrongly (the wrong way round, or a leg on a strip carrying only other nets,
as the progress check names them) are offered back to the tray first: with `mend` they go
back and *Fill the rest* lays them out again, then the board is tidied.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from functools import partial

from solum.circuit.schema import Circuit
from solum.guides import FootprintTable
from solum.models import ModelLibrary
from solum.stripboard.board import Hole, Layout, Link, Placed
from solum.stripboard.check import (
    check_layout,
    either_way,
    joined_groups,
    misfits,
    occupants,
    placement_faults,
    read_layout,
)
from solum.stripboard.footprints import BoardPart
from solum.stripboard.size import SizeError, remove_line, trim
from solum.stripboard.start import StartError, start_for_me

JUMP = 6  # holes a part, link or cut may slide left in one step (over what's between)
PASSES = 40  # most passes over the steps (each keeps at least one step, or the search ends)
TRIES = 12000  # most steps tried in all: a big board stops there (a count, so it repeats)

Key = tuple[int, int, int, int, int]
Step = Callable[[Layout], Layout]


class TidyError(ValueError):
    """The board can't be tidied (plain-English message, says what to do)."""


class MendFirst(TidyError):
    """Parts placed wrongly: Tidy up asks before sending them back to the tray."""

    def __init__(self, refs: list[str]) -> None:
        self.refs = refs
        names = ", ".join(refs[:-1]) + f" and {refs[-1]}" if len(refs) > 1 else refs[0]
        verb, them = ("are", "them") if len(refs) > 1 else ("is", "it")
        super().__init__(f"{names} {verb} placed wrongly: Tidy up can lay {them} out again "
                         "with the rest.")  # fmt: skip


@dataclass(frozen=True)
class Tidied:
    """The tidied board, and the parts laid out again (`mend`)."""

    layout: Layout
    mended: tuple[str, ...] = ()


def key(layout: Layout) -> Key:
    """A board's measure, smaller is tidier: its size in holes, its cuts, its links, their
    length, then how far its legs, cuts and links sit from the top left."""
    length = sum(abs(link.a[1] - link.b[1]) for link in layout.links)
    spread = sum(h[0] + h[1] for p in layout.parts for _, h in p.legs)
    spread += sum(h[0] + h[1] for h in layout.cuts)
    spread += sum(h[0] + h[1] for link in layout.links for h in (link.a, link.b))
    return (layout.columns * layout.strips, len(layout.cuts), len(layout.links), length, spread)


def _better(new: Key, old: Key) -> bool:
    """No worse in size, cuts or links, and smaller as a whole."""
    return all(n <= o for n, o in zip(new[:3], old[:3], strict=True)) and new < old


def _plus(hole: Hole, d: Hole) -> Hole:
    return (hole[0] + d[0], hole[1] + d[1])


def _shifted(layout: Layout, d: Hole, parts: frozenset[str] = frozenset(),
             cuts: frozenset[Hole] = frozenset(), links: frozenset[int] = frozenset(),
             pads: frozenset[int] = frozenset()) -> Layout:  # fmt: skip
    """The layout with these parts, cuts, links (by index) and pads (wires, by index)
    moved by `d`; everything else where it was."""
    return replace(
        layout,
        parts=tuple(
            replace(p, legs=tuple((leg, _plus(h, d)) for leg, h in p.legs)) if p.ref in parts else p
            for p in layout.parts
        ),
        cuts=frozenset(_plus(h, d) if h in cuts else h for h in layout.cuts),
        links=tuple(
            Link(_plus(k.a, d), _plus(k.b, d)) if i in links else k
            for i, k in enumerate(layout.links)
        ),
        wires=tuple(
            replace(w, hole=_plus(w.hole, d)) if i in pads and w.hole is not None else w
            for i, w in enumerate(layout.wires)
        ),
    )


def _own(layout: Layout, placed: Placed) -> tuple[frozenset[Hole], frozenset[int]]:
    """A part's own cuts and links: the cuts on its legs' strips from the column left of it
    to its last, and the links in its columns (as Start for me lays them)."""
    columns = [h[0] for _, h in placed.legs]
    first, last = min(columns), max(columns)
    strips = {h[1] for _, h in placed.legs}
    cuts = frozenset(h for h in layout.cuts if first - 1 <= h[0] <= last and h[1] in strips)
    links = frozenset(i for i, k in enumerate(layout.links) if first <= k.a[0] <= last)
    return cuts, links


def _steps(layout: Layout, board: dict[str, BoardPart]) -> Iterator[Step]:
    """The steps to try on `layout`, in their fixed order (each a layout to a layout; one
    that can't be made raises `SizeError` and is skipped)."""
    for column in range(layout.columns - 1, -1, -1):
        yield partial(remove_line, board=board, axis="column", at=column)
    for strip in range(layout.strips - 1, -1, -1):
        yield partial(remove_line, board=board, axis="strip", at=strip)
    for i in range(len(layout.links)):
        yield partial(_relinked, i=i, link=None)
    for cut in sorted(layout.cuts):
        yield partial(_uncut, cut=cut)
    for placed in layout.parts:
        cuts, links = _own(layout, placed)
        ref = frozenset({placed.ref})
        for n in range(1, JUMP + 1):
            yield partial(_shifted, d=(-n, 0), parts=ref, cuts=cuts, links=links)
        for n in range(1, JUMP + 1):
            yield partial(_shifted, d=(-n, 0), parts=ref)
        yield partial(_shifted, d=(0, -1), parts=ref)
        yield partial(_shifted, d=(0, 1), parts=ref)
    for i, link in enumerate(layout.links):
        for n in range(1, JUMP + 1):
            yield partial(_shifted, d=(-n, 0), links=frozenset({i}))
        top, bottom = sorted((link.a, link.b), key=lambda h: h[1])
        if bottom[1] - top[1] > 1:
            yield partial(_relinked, i=i, link=Link((top[0], top[1] + 1), bottom))
            yield partial(_relinked, i=i, link=Link(top, (bottom[0], bottom[1] - 1)))
    for cut in sorted(layout.cuts):
        for n in range(1, JUMP + 1):
            yield partial(_shifted, d=(-n, 0), cuts=frozenset({cut}))
    for i, wire in enumerate(layout.wires):
        if wire.hole is not None:
            for d in ((-1, 0), (0, -1)):
                yield partial(_shifted, d=d, pads=frozenset({i}))


def _uncut(layout: Layout, cut: Hole) -> Layout:
    return replace(layout, cuts=layout.cuts - {cut})


def _relinked(layout: Layout, i: int, link: Link | None) -> Layout:
    """Link `i` replaced by `link` (None: taken out)."""
    return replace(layout, links=(*layout.links[:i], *([link] if link else []),
                                  *layout.links[i + 1 :]))  # fmt: skip


def tidy_steps(layout: Layout, passes: Callable[[Layout], bool],
               board: dict[str, BoardPart]) -> Layout:  # fmt: skip
    """`layout` (which `passes`) made smaller step by step: each step kept when the
    trimmed board still `passes` and is `_better`; passes over the steps until two in a
    row gain nothing but spread (things only nudged towards the top left), `PASSES`, or
    `TRIES` steps tried in all."""
    best, best_key = layout, key(layout)
    idle = tries = 0
    for _ in range(PASSES):
        start = best_key
        for step in _steps(best, board):
            tries += 1
            if tries > TRIES:
                return best
            try:
                made = trim(step(best), board)
            except (SizeError, IndexError):
                continue
            made_key = key(made)
            if _better(made_key, best_key) and passes(made):
                best, best_key = made, made_key
        idle = idle + 1 if best_key[:4] == start[:4] else 0
        if best_key == start or idle == 2:
            break
    return best


Joins = frozenset[tuple[str, ...]]


def joins(layout: Layout, turnable: frozenset[str] = frozenset()) -> Joins:
    """Which legs (`R1.1`) and wired lugs the copper, links and wires join, as a partition:
    two boards with the same joins and no placement faults pass the check alike. A part in
    `turnable` (two legs, either way round) is named by its ref alone, so turned it joins
    the same."""
    copper, lugs = joined_groups(layout, [h for p in layout.parts for _, h in p.legs])
    found: dict[object, list[str]] = {}
    for placed in layout.parts:
        for leg, hole in placed.legs:
            name = placed.ref if placed.ref in turnable else f"{placed.ref}.{leg}"
            found.setdefault(copper.get(hole, f"{placed.ref}.{leg}"), []).append(name)
    for lug, group in lugs.items():
        found.setdefault(group, []).append(lug)
    return frozenset(tuple(sorted(names)) for names in found.values())


def tidy_up(layout: Layout, circuit: Circuit, models: ModelLibrary, table: FootprintTable,
            mend: bool = False) -> Tidied:  # fmt: skip
    """*Tidy up* on a board: smaller, still passing the check, the same every run. Parts
    placed wrongly raise `MendFirst` unless `mend`, which lays them out again first. A
    board that doesn't pass, or can't be made smaller, raises `TidyError` saying so."""
    if not layout.parts:
        raise TidyError("There's nothing on the board to tidy: place the parts first.")
    mended = misfits(layout, circuit, models, table)
    if mended and not mend:
        raise MendFirst(mended)
    if mended:
        tray = replace(layout, parts=tuple(p for p in layout.parts if p.ref not in mended))
        try:
            filled = start_for_me(tray, circuit, models, table, fill=True)
        except StartError as err:
            raise TidyError(str(err)) from None
        if filled.left:
            raise TidyError(" ".join(filled.left))
        layout = filled.layout
    checked = check_layout(layout, circuit, models, table)
    if not checked.ok:
        raise TidyError(f"Tidy up works on a board that passes the check: {checked.faults[0]}")
    r = read_layout(layout, circuit, models, table)
    kinds = {p.ref: p for p in circuit.parts}
    turnable = frozenset(ref for ref, part in r.board.items()
                         if len(part.legs) == 2 and either_way(part, kinds.get(ref)))  # fmt: skip
    board, off, same = r.board, r.off_board, joins(layout, turnable)

    def passes(made: Layout) -> bool:  # quickest first: the holes, the joins, then the check
        return (not occupants(made)[1] and joins(made, turnable) == same
                and not placement_faults(made, board, off)
                and check_layout(made, circuit, models, table).ok)  # fmt: skip

    tidied = tidy_steps(layout, passes, board)
    if key(tidied)[:4] == key(layout)[:4]:  # only nudged: keep the builder's board
        if not mended:
            raise TidyError("Couldn't make this board smaller.")
        tidied = layout
    return Tidied(tidied, tuple(mended))
