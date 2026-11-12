"""The `solum` command: `solum serve`, `solum bench`, `solum run`."""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from solum.config import load_settings

if TYPE_CHECKING:
    from solum.circuit.schema import Circuit
    from solum.simulate import Simulator


def cmd_bench(args: argparse.Namespace) -> int:
    import shutil

    from solum.bench import KNOB, SEARCH, run_bench, time_cache, time_knob_turn, time_search
    from solum.cache import CachedEngine, SimCache
    from solum.circuit.io import load_circuit
    from solum.fixes import gain_options
    from solum.probe import run_view
    from solum.sim.engine import engine_from_settings
    from solum.simulate import Simulator, model_library

    settings = load_settings()
    engine = engine_from_settings(settings)
    circuit = (settings.library_dir / "bench" / "big-muff.cir").read_text()
    starters = settings.library_dir / "starters"
    starter, ref = KNOB
    viewed = load_circuit(starters / f"{starter}.json")
    models = model_library(settings)
    sim = Simulator(engine, models)  # uncached: every turn is a real run
    # the cache timings run where the app's cache lives (CACHE_DIR, the same disk), in a
    # folder of their own that is removed afterwards
    bench_dir = settings.cache_dir / "bench"
    shutil.rmtree(bench_dir, ignore_errors=True)
    cache = SimCache(bench_dir, max_bytes=10**9)
    searched, stage = SEARCH
    searching = Simulator(CachedEngine(engine, cache), models)
    found = load_circuit(starters / f"{searched}.json")
    more: dict[str, Callable[[], dict[str, Any]]] = {
        "cache": lambda: time_cache(cache),
        "find_parts": lambda: time_search(lambda: gain_options(searching, found, stage)),
    }
    if args.knob_runs > 0:
        more["knob_turn"] = lambda: time_knob_turn(
            lambda c: run_view(sim, c, [], "med"), viewed, ref, args.knob_runs
        )
    try:
        report = run_bench(
            engine,
            circuit,
            runs=args.runs,
            audio_runs=args.audio_runs,
            more=more,
        )
    finally:
        shutil.rmtree(bench_dir, ignore_errors=True)
    report["cache_dir"] = str(settings.cache_dir)
    print(json.dumps(report, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from solum.circuit.io import load_circuit
    from solum.rules.run import Checker, rule_book
    from solum.sim.engine import SimError
    from solum.simulate import simulator_from_settings

    circuit = load_circuit(Path(args.circuit))
    settings = load_settings()
    sim = simulator_from_settings(settings)
    checker = Checker(rule_book(settings.library_dir), sim.models)
    checker.require_runnable(circuit)
    try:
        return _report(args, circuit, sim)
    except SimError as err:
        raise SimError(checker.message(err), err.log) from None


def _report(args: argparse.Namespace, circuit: "Circuit", sim: "Simulator") -> int:
    from solum import report

    texts: list[str] = [f"{circuit.name} ({args.circuit})"]
    data: dict[str, Any] = {"circuit": args.circuit}
    if args.op or not (args.ac or args.tran):
        op = sim.op(circuit)
        texts.append(report.op_text(op))
        data["op"] = report.op_summary(op)
    if args.ac:
        ac = sim.ac(circuit)
        nets = [sim.resolve(circuit, n) for n in args.ac]
        texts += [report.ac_text(ac, net) for net in nets]
        data["ac"] = [report.ac_summary(ac, net) for net in nets]
    if args.tran:
        tran = sim.tran(circuit, args.tran, args.level)
        texts.append(report.tran_text(tran))
        data["tran"] = report.tran_summary(tran)
    print(json.dumps(data, indent=2) if args.json else "\n\n".join(texts))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = load_settings()
    uvicorn.run("solum.api.app:create_app", factory=True, host=args.host, port=settings.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="solum", description="Solum Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="time the Big Muff bench circuit; prints JSON")
    bench.add_argument("--runs", type=int, default=5, help="repeats for op/ac/short tran")
    bench.add_argument("--audio-runs", type=int, default=2, help="repeats for the 5 s render")
    bench.add_argument(
        "--knob-runs", type=int, default=5, help="TS808 Tone turns to time (0 skips)"
    )
    bench.set_defaults(func=cmd_bench)

    run = sub.add_parser("run", help="simulate a circuit file and print the results")
    run.add_argument("circuit", help="circuit .json file")
    run.add_argument("--op", action="store_true", help="DC voltages (the default)")
    run.add_argument("--ac", action="append", metavar="NODE", help="frequency response at NODE")
    run.add_argument("--tran", action="append", metavar="NODE", help="waveform stats at NODE")
    run.add_argument("--level", choices=("soft", "med", "hard"), default="med",
                     help="input level for --tran")  # fmt: skip
    run.add_argument("--json", action="store_true", help="print JSON instead of text")
    run.set_defaults(func=cmd_run)

    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="0.0.0.0")
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as err:  # plain-English message, no traceback, for CLI users
        from solum.sim.engine import SimError

        if isinstance(err, SimError | ValueError):
            print(f"solum: {err}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
