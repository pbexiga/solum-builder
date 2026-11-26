"""The starters' full layouts as a table (P6i): *Lay it out for me*, try 1, on every
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
from solum.circuit.io import load_circuit
from solum.config import load_settings
from solum.guides import footprint_table
from solum.simulate import model_library
from solum.stripboard import compact_job
from solum.stripboard.board import STAND_UP, Layout, StandUp
from solum.stripboard.check import outline_overlaps, placement_warnings, read_layout
from solum.stripboard.compact import finish, problem
from solum.stripboard.start import StartError

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "scratch" / "board-table"
HEAD = "| Starter | Holes | Cuts | Links | Touching | Warnings | Standing | Fell back |"


@dataclass(frozen=True)
class Row:
    starter: str
    columns: int
    strips: int
    cuts: int
    links: int
    touching: int
    warnings: int
    standing: tuple[str, ...]
    fell_back: bool

    def line(self) -> str:
        holes = f"{self.columns * self.strips} ({self.columns}×{self.strips})"
        standing = ", ".join(self.standing) or "–"
        return (
            f"| {self.starter} | {holes} | {self.cuts} | {self.links} | {self.touching} "
            f"| {self.warnings} | {standing} | {'yes' if self.fell_back else ''} |"
        )


def table(names: list[str] | None, stand_up: StandUp = "needed") -> tuple[list[Row], list[str]]:
    """Every starter's full layout (`names`: only those) with standing parts as `stand_up`
    says (D-403), and the starters that can't go on a board, with why."""
    settings = load_settings({"DATA_DIR": str(WORK / "data"), "CACHE_DIR": str(WORK / "cache"),
                              "LIBRARY_DIR": str(REPO / "library")})  # fmt: skip
    models, tbl = model_library(settings), footprint_table(settings.library_dir)
    rows, skipped = [], []
    for name, path in starter_paths(settings.library_dir).items():
        if names and name not in names:
            continue
        circuit = load_circuit(path)
        empty = Layout(0, 0, (), stand_up=stand_up)
        try:
            pb = problem(empty, circuit, models, tbl)
        except StartError as err:
            skipped.append(f"{name}: {err}")
            continue
        started = time.monotonic()
        got = compact_job.run(pb, empty, circuit, 1, settings,
                              lambda *_: None, threading.Event())  # fmt: skip
        built = finish(pb, got.best, models, tbl)
        lay = built.layout
        r = read_layout(lay, circuit, models, tbl)
        rows.append(Row(
            name, lay.columns, lay.strips, len(lay.cuts), len(lay.links),
            len(outline_overlaps(lay, r.board)), len(placement_warnings(lay, r.board)),
            tuple(sorted(p.ref for p in lay.parts if p.standing)), built.fell_back,
        ))  # fmt: skip
        print(f"{name}: {time.monotonic() - started:.0f} s", file=sys.stderr, flush=True)
    return rows, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("starters", nargs="*")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stand-up", choices=STAND_UP, default="needed")
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
