#!/usr/bin/env python3
"""Compare fixed-chain correction discovery with equal configured budgets.

Deterministic mathematical/physical results and optional machine timings are
written separately. Quality-search limits do not change certified coverage.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import bce_v2 as c


REFERENCES = ("Alcatraz", "Bicube Fuse", "Shark Fin Soup")
MODES = ("original", "shallow", "structured")


def algorithm_record(algorithm):
    return {"id": algorithm.id, "expression": algorithm.expression.to_dict(),
            "turn_sequence": algorithm.turn_sequence,
            "htm_length": algorithm.htm_length, "qtm_length": algorithm.qtm_length}


def compare(name, settings, timeout):
    started = time.perf_counter()
    baseline = c.synthesize_human_method(c.fixture(name), max_group_elements=10_368, timeout=timeout)
    if baseline.status != "completed":
        raise ValueError("reference exceeds the explicit comparison scope")
    preparation = time.perf_counter() - started
    result = {"puzzle": name, "reference_shape": baseline.reference_shape.labels,
              "group_order": str(baseline.group_order), "quotient_order": str(baseline.quotient_order),
              "kernel_order": str(baseline.kernel_order), "gap_version": baseline.gap_version,
              "baseline_fingerprint": baseline.to_dict()["fingerprint"],
              "baseline_algorithms": [algorithm_record(a) for a in baseline.algorithms],
              "stages": [{"feature": s.feature.to_dict(), "block_name": s.block_name,
                          "order_before": str(s.order_before), "order_after": str(s.order_after),
                          "index": s.index} for s in baseline.stages], "variants": {}}
    timings = {"puzzle": name, "preparation_seconds": preparation, "modes": {}}
    for mode in MODES:
        started = time.perf_counter()
        search = c.improve_human_method(baseline, mode=mode, **settings)
        timings["modes"][mode] = time.perf_counter() - started
        method = search.method
        used = {identifier for a in method.algorithms for identifier in a.base_ids}
        result["variants"][mode] = {
            "metadata": search.metadata, "method_fingerprint": method.to_dict()["fingerprint"],
            "algorithms": [algorithm_record(a) for a in method.algorithms],
            "leaf_definitions": [{"id": g.id, "turn_sequence": g.turn_sequence,
                                  "htm_length": g.htm_length} for g in method.generators if g.id in used],
            "cases": [{"stage_number": s.number, "observation": list(case.observation),
                       "algorithm_id": case.algorithm_id} for s in method.stages for case in s.cases],
        }
    return result, timings


def distinct_paths(output, measurements):
    if output is None or measurements is None:
        return
    if (output.resolve() == measurements.resolve() or
            output.exists() and measurements.exists() and output.samefile(measurements)):
        raise ValueError("output and measurements must be different files")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", choices=REFERENCES, action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--timeout", type=float, default=None)
    defaults = dict(max_seed_loops=32, max_candidates=3000, max_word_length=3, rounds=1,
                    max_states=2000, max_stage_generators=24, max_alternatives=3,
                    max_htm_length=120, max_expanded_moves=480)
    for name, default in defaults.items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        distinct_paths(args.output, args.measurements)
        settings = {name: getattr(args, name) for name in defaults}
        for name, value in settings.items():
            minimum = 1 if name == "max_alternatives" else 0
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        pairs = [compare(name, settings, args.timeout) for name in args.puzzle or REFERENCES]
        record = {"format": "bce-v2-human-algorithm-comparison", "version": 1,
                  "quality": "computational_baseline", "human_reviewed": False,
                  "metrics_scope": "all reference-group states; simplified full physical solution words",
                  "settings": settings, "results": [result for result, _ in pairs]}
        text = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(text, end="")
        else:
            args.output.write_text(text, encoding="utf-8")
        if args.measurements is not None:
            args.measurements.write_text(json.dumps(
                {"format": "bce-v2-human-algorithm-measurements", "version": 1,
                 "results": [timings for _, timings in pairs]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (ValueError, TypeError, RuntimeError, OSError) as error:
        print(f"compare-human-algorithms: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
