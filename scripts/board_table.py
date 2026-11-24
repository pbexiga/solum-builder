"""The starters' full layouts as a table (P6i): *Build a full layout*, Quick, try 1, on every
starter that can go on a board, and what each board came to. Layouts are deterministic
(D-399), so a change to the layout rules shows as this table's diff.

Usage (dev image): python scripts/board_table.py [--out FILE] [--stand-up CHOICE] [starter ...]
"""

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from solum.api.app import starter_paths
from solum.circuit.connectivity import connect
from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.guides import footprint_table
from solum.probe import loud_inputs
from solum.sim.engine import engine_from_settings
from solum.simulate import simulator_from_settings
from solum.stripboard import compact_job
from solum.stripboard.apart import alongside
from solum.stripboard.board import STAND_UP, Layout, StandUp
from solum.stripboard.check import copper_groups, outline_overlaps, read_layout
from solum.stripboard.compact import finish, problem
from solum.stripboard.limits import broken_limits, placement_limits
from solum.stripboard.quiet import guards, noisy_links
from solum.stripboard.start import StartError

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "scratch" / "board-table"
HEAD = ("| Starter | Holes | Cuts | Links | Limits broken | Noisy links | Touching | Standing "
        "| High-gain inputs | Fell back | Output beside input |")  # fmt: skip


@dataclass(frozen=True)
class Row:
    starter: str
    columns: int
    strips: int
    cuts: int
    links: int
    broken: int
    noisy: int
    touching: int
    standing: tuple[str, ...]
    loud: tuple[str, ...]
    fell_back: bool
    beside: int

    def line(self) -> str:
        holes = f"{self.columns * self.strips} ({self.columns}×{self.strips})"
        standing, loud = ", ".join(self.standing) or "–", ", ".join(self.loud) or "–"
        return (f"| {self.starter} | {holes} | {self.cuts} | {self.links} | {self.broken} "
                f"| {self.noisy} | {self.touching} | {standing} | {loud} "
                f"| {'yes' if self.fell_back else ''} | {self.beside} |")  # fmt: skip


def table(names: list[str] | None, stand_up: StandUp = "room") -> tuple[list[Row], list[str]]:
    """Every starter's full layout (`names`: only those) with standing parts as `stand_up`
    says (D-403), and the starters that can't go on a board, with why."""
    settings = load_settings({"DATA_DIR": str(WORK / "data"), "CACHE_DIR": str(WORK / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    sim = simulator_from_settings(settings, engine_from_settings(settings))
    models, tbl = sim.models, footprint_table(settings.library_dir)
    rows, skipped = [], []
    for name, path in starter_paths(settings.library_dir).items():
        if names and name not in names:
            continue
        circuit = load_circuit(path)
        loud = loud_inputs(sim, circuit)
        empty = Layout(0, 0, (), stand_up=stand_up)
        try:
            pb = problem(empty, circuit, models, tbl, loud)
        except StartError as err:
            skipped.append(f"{name}: {err}")
            continue
        started = time.monotonic()
        got = compact_job.run(pb, empty, circuit, loud, False, 1, settings,
                              lambda *_: None, threading.Event())  # fmt: skip
        built = finish(pb, got.best, models, tbl)
        lay = built.layout
        r = read_layout(lay, circuit, models, tbl)
        nets = connect(circuit)
        rows.append(Row(
            name, lay.columns, lay.strips, len(lay.cuts), len(lay.links),
            len(broken_limits(lay, placement_limits(circuit, nets, r.board, loud))),
            len(noisy_links(lay, r.board, nets, guards(r.board, nets, loud))),
            len(outline_overlaps(lay, r.board)),
            tuple(sorted(p.ref for p in lay.parts if p.standing)),
            tuple(f"{i.ref}.{i.pin}" for i in loud), built.fell_back,
            len(alongside(lay, r.board, nets, loud, copper_groups(lay))),
        ))  # fmt: skip
        print(f"{name}: {time.monotonic() - started:.0f} s", file=sys.stderr, flush=True)
    return rows, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("starters", nargs="*")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stand-up", choices=STAND_UP, default="room")
    args = ap.parse_args()
    rows, skipped = table(args.starters or None, args.stand_up)
    text = "\n".join([HEAD, "|" + "---|" * HEAD.count(" | ") + "---|",
                      *(r.line() for r in rows), "",
                      *(f"Not on a board: {s}" for s in skipped)])  # fmt: skip
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
