#!/usr/bin/env python3
"""Profile a prepared symbolic method's zero-quality template fallback.

Run with v2/.venv/bin/python. Preparation is timed separately; cProfile covers
only the public repertoire call. This uses production APIs without patches.
"""

import argparse
import cProfile
import json
from pathlib import Path
import pstats
import signal
from time import perf_counter

import bce_v2 as c

from profile_symbolic_basis import bandage_from_notebook


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", default="BeltRoad")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--output", type=Path, default=base /
                        "research-results/staged-performance-fallback-current.json")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("seconds must be positive")
    record = dict(puzzle=args.puzzle, runtime_patches=False,
                  scope="prepared symbolic method; zero-quality public template fallback only",
                  budget_seconds=args.seconds, completed=False, error=None)
    profiler = cProfile.Profile()

    def expired(*_):
        raise TimeoutError("fallback probe wall-clock bound expired")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(args.seconds)
    try:
        shape = c.Shape(bandage_from_notebook(base / "examples" / (args.puzzle + ".ipynb")))
        start = perf_counter()
        analysis = c.analyze_isotropy(shape, timeout=min(60, args.seconds))
        record["analysis_seconds"] = perf_counter() - start
        record["original_loop_count"] = len(analysis.loops)
        start = perf_counter()
        method = c.synthesize_human_method(analysis, strategy="fully_solve_each_block",
                                           backend="symbolic", timeout=min(60, args.seconds))
        record["method_seconds"] = perf_counter() - start
        start = perf_counter()
        profiler.enable()
        try:
            repertoire = c.template_human_repertoire(
                method, optimization_seconds=0, select_chain=False, allow_symmetry=False)
        finally:
            profiler.disable()
            record["wall_seconds"] = perf_counter() - start
        record.update(completed=True, macros=len(repertoire.macros))
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        stats = pstats.Stats(profiler)
        record["profile_top"] = [
            dict(file=key[0], line=key[1], function=key[2], calls=value[1], seconds=value[3])
            for key, value in sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:40]
        ]
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
