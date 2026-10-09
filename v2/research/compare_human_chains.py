#!/usr/bin/env python3
"""Compare algorithm-aware feature chains with one shared discovery pool.

Deterministic mathematical results and optional machine timings are written
separately. Sticker-point chains are structural controls, not human methods.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from math import isfinite, prod
from pathlib import Path
import sys
import time

import bce_v2 as c


REFERENCES = ("Alcatraz", "Bicube Fuse", "Shark Fin Soup")
DISCOVERY_DEFAULTS = dict(max_seed_loops=32, max_candidates=3000, max_word_length=3,
                          rounds=1, max_states=2000, max_stage_generators=24,
                          max_alternatives=3, max_htm_length=120, max_expanded_moves=480)
IDENTITY = tuple(range(48))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def then(first, second):
    return tuple(second[point] for point in first)


def point_chain(group):
    """Minimum nontrivial point orbit, with exact right-coset checks."""
    permutations = group.permutations
    current, stages = tuple(range(len(group))), []
    while len(current) > 1:
        choices = []
        for point in range(48):
            target = tuple(i for i in current if permutations[i][point] == point)
            if len(target) < len(current):
                require(target and len(current) % len(target) == 0,
                        "point stabilizer has inconsistent order")
                choices.append((len(current) // len(target), point, target))
        require(choices, "faithful point action leaves a nontrivial terminal subgroup")
        index, point, target = min(choices)
        fibers = defaultdict(list)
        for i in current:
            fibers[permutations[i][point]].append(i)
        require(len(fibers) == index, "point orbit and stabilizer index disagree")
        for members in fibers.values():
            representative = permutations[members[0]]
            require({then(permutations[i], representative) for i in target} ==
                    {permutations[i] for i in members},
                    "point observations do not identify exact right cosets")
        stages.append({"number": len(stages) + 1, "sticker_point": point,
                       "order_before": str(len(current)), "order_after": str(len(target)),
                       "index": index, "observations": sorted(fibers),
                       "solved_observation": point})
        current = target
    require(current == (0,) and permutations[0] == IDENTITY and
            prod(stage["index"] for stage in stages) == len(group),
            "point chain fails faithful termination or index-product check")
    return {"coverage_scope": "chain_structure_only", "human_method_complete": False,
            "selection": "minimum nontrivial orbit size, then sticker-point index",
            "recognition": "abstract sticker points; no executable human recognition policy",
            "terminal_order": "1", "index_product": str(prod(s["index"] for s in stages)),
            "stage_count": len(stages),
            "max_case_count": max((s["index"] for s in stages), default=0),
            "case_count_sum": sum(s["index"] for s in stages), "stages": stages}


def candidate_record(candidate):
    method = candidate.method
    used = {identifier for algorithm in method.algorithms for identifier in algorithm.base_ids}
    return {"id": candidate.id, "source": candidate.source, "metrics": candidate.metrics,
            "method_fingerprint": method.to_dict()["fingerprint"], "coverage": method.coverage,
            "coverage_scope": method.coverage_scope, "human_method_complete": method.human_method_complete,
            "index_product": str(prod(stage.index for stage in method.stages)),
            "stages": [{"number": stage.number, "feature": stage.feature.to_dict(),
                        "block_index": stage.block_index, "block_name": stage.block_name,
                        "order_before": str(stage.order_before), "order_after": str(stage.order_after),
                        "index": stage.index, "solved_observation": list(stage.solved_observation),
                        "implied_features": [feature.to_dict() for feature in stage.implied_features],
                        "cases": [{"observation": list(case.observation),
                                   "algorithm_id": case.algorithm_id} for case in stage.cases]}
                       for stage in method.stages],
            "algorithms": [{"id": algorithm.id, "expression": algorithm.expression.to_dict(),
                            "turn_sequence": algorithm.turn_sequence,
                            "htm_length": algorithm.htm_length, "qtm_length": algorithm.qtm_length}
                           for algorithm in method.algorithms],
            "leaf_definitions": [{"id": generator.id, "turn_sequence": generator.turn_sequence,
                                  "htm_length": generator.htm_length,
                                  "qtm_length": generator.qtm_length}
                                 for generator in method.generators if generator.id in used]}


def compare(name, settings, discovery_options, timeout):
    started = time.perf_counter()
    plan = c.plan_human_stages(c.fixture(name), max_group_elements=10_368, timeout=timeout)
    require(plan.status == "completed", "reference exceeds the explicit comparison scope")
    preparation = time.perf_counter() - started
    started = time.perf_counter()
    selection = c.select_human_chain(plan, discovery_options=discovery_options, **settings)
    selection_seconds = time.perf_counter() - started
    require(selection.status == "completed", "chain selection did not retain a complete method")
    candidates = [candidate_record(candidate) for candidate in selection.candidates]
    by_id = {candidate["id"]: candidate for candidate in candidates}
    frontier = tuple(selection.frontier)
    require(frontier and all(identifier in by_id for identifier in frontier),
            "selection frontier refers to missing candidates")
    metadata = selection.metadata
    preferred = {}
    for preference, keys in metadata["preference_orders"].items():
        preferred[preference] = min(frontier, key=lambda identifier: (
            tuple(by_id[identifier]["metrics"][key] for key in keys), identifier))
    started = time.perf_counter()
    point_control = point_chain(plan.group)
    point_seconds = time.perf_counter() - started
    return ({"puzzle": name, "reference_shape": plan.inventory.root_shape.labels,
             "group_order": str(plan.group_order), "quotient_order": str(plan.quotient_order),
             "kernel_order": str(plan.kernel_order), "gap_version": plan.analysis.gap_version,
             "metadata": metadata, "selected_id": selection.selected_id,
             "preferred_ids": preferred, "frontier": list(frontier),
             "candidates": candidates, "point_chain_control": point_control},
            {"puzzle": name, "preparation_seconds": preparation,
             "selection_seconds": selection_seconds, "point_control_seconds": point_seconds})


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
    parser.add_argument("--strategy", choices=("placement_then_orientation", "fully_solve_each_block"),
                        default="placement_then_orientation")
    parser.add_argument("--preference", choices=("execution", "recognition"), default="execution")
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--max-expansions", type=int, default=64)
    parser.add_argument("--max-methods", type=int, default=16)
    parser.add_argument("--discovery-mode", choices=("original", "shallow", "structured"),
                        default="structured")
    for name, default in DISCOVERY_DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        distinct_paths(args.output, args.measurements)
        if args.timeout is not None and (not isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        settings = {name: getattr(args, name) for name in
                    ("strategy", "preference", "beam_width", "max_expansions", "max_methods")}
        for name in ("beam_width", "max_expansions", "max_methods"):
            minimum = 1 if name == "beam_width" else 0
            if settings[name] < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        discovery = {name: getattr(args, name) for name in DISCOVERY_DEFAULTS}
        for name, value in discovery.items():
            minimum = 1 if name == "max_alternatives" else 0
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        discovery["mode"] = args.discovery_mode
        pairs = [compare(name, settings, discovery, args.timeout) for name in args.puzzle or REFERENCES]
        record = {"format": "bce-v2-human-chain-comparison", "version": 1,
                  "quality": "computational_baseline", "human_reviewed": False,
                  "metrics_scope": "all reference-group states; simplified full physical solution words",
                  "preparation_max_group_elements": 10_368,
                  "settings": settings, "discovery_options": discovery,
                  "preference_tie_breaker": "candidate ID",
                  "results": [result for result, _ in pairs]}
        text = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(text, end="")
        else:
            args.output.write_text(text, encoding="utf-8")
        if args.measurements is not None:
            args.measurements.write_text(json.dumps(
                {"format": "bce-v2-human-chain-measurements", "version": 1,
                 "results": [timings for _, timings in pairs]}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
        return 0
    except (ValueError, TypeError, RuntimeError, OSError) as error:
        print(f"compare-human-chains: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
