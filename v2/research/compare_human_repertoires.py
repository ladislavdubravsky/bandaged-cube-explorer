#!/usr/bin/env python3
"""Compare verified shared vocabularies and explicit execution tradeoffs.

The fixed stage chains are retained. Every selected wrapper is reloaded and
physically applied to its full reference group. Timings are separate from the
deterministic result and optional Alcatraz repertoire/guide artifacts.
"""

from __future__ import annotations

import argparse
import json
from math import isfinite
from pathlib import Path
import sys
import time

import bce_v2 as c
from bce_v2.human_methods import _state_for_permutation


RESEARCH_RESULTS = Path(__file__).resolve().parent.parent / "research-results"
REFERENCES = ("Alcatraz execution", "Alcatraz recognition", "Bicube Fuse", "Shark Fin Soup")
DEFAULTS = dict(max_trials=64, max_recipes=2000, max_power=4, max_extra_macros=16,
                max_setup_macros=16)
METRIC_KEYS = ("total_htm", "worst_htm", "mean_htm", "total_qtm", "worst_qtm", "mean_qtm")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_method(name, timeout):
    if name.startswith("Alcatraz "):
        suffix = name.split()[-1]
        return c.load_human_method(RESEARCH_RESULTS / f"alcatraz-{suffix}-method.json"), "retained_delivery_4_method"
    plan = c.plan_human_stages(c.fixture(name), max_group_elements=10_368, timeout=timeout)
    require(plan.status == "completed", "reference exceeds the explicit comparison scope")
    return c.select_human_chain(plan).method, "default_delivery_4_chain_selection"


def verify(repertoire, states):
    """Recheck portability and execute all imported root states after loading."""
    record = repertoire.to_dict()
    loaded = c.HumanRepertoire.from_dict(record)
    require(loaded.to_json() == repertoire.to_json(), "repertoire does not round-trip canonically")
    totals, worst, instructions = [0, 0], [0, 0], 0
    for state in states:
        require(state.scramble is None, "verification state unexpectedly retains scramble provenance")
        application = loaded.apply(state)
        require(application.status == "solved" and application.state.is_solved,
                "reloaded repertoire failed a reference-group state")
        require(state.apply(application.turn_sequence) == application.state,
                "reloaded recipe route disagrees with its physical word")
        require(all(step.rank_after < step.rank_before for step in application.steps),
                "reloaded instruction failed its progress rank")
        instructions += len(application.steps)
        moves = application.turn_sequence.split()
        for index, cost in enumerate((len(moves), sum(2 if move.endswith("2") else 1 for move in moves))):
            totals[index] += cost
            worst[index] = max(worst[index], cost)
    metrics = dict(total_htm=totals[0], worst_htm=worst[0], mean_htm=totals[0] / len(states),
                   total_qtm=totals[1], worst_qtm=worst[1], mean_qtm=totals[1] / len(states))
    require(all(metrics[key] == loaded.metadata["selected_metrics"][key] for key in METRIC_KEYS),
            "runtime whole-group costs disagree with selected metrics")
    return loaded, {"portable_roundtrip": True, "physical_states_checked": len(states),
                    "strict_rank_decreases_checked": instructions, "runtime_metrics": metrics}


def compact_record(repertoire, verification):
    record = repertoire.to_dict()
    return {"metadata": record["metadata"], "repertoire_fingerprint": record["fingerprint"],
            "method_fingerprint": record["method"]["fingerprint"], "macros": record["macros"],
            "stages": record["stages"], "verification": verification}


def variants(settings, ratios):
    basic = {**settings, "max_trials": 0, "max_recipes": 0, "max_extra_macros": 0,
             "max_cost_ratio": 1.0}
    yield "basic_graph_control", basic
    yield "strict", {**settings, "max_cost_ratio": 1.0}
    for ratio in ratios:
        yield "ratio_" + str(ratio).replace(".", "_"), {**settings, "max_cost_ratio": ratio}


def compare(name, settings, ratios, timeout, artifacts):
    started = time.perf_counter()
    method, origin = source_method(name, timeout)
    states = tuple(_state_for_permutation(method.reference_shape, permutation)
                   for permutation in sorted(method._permutations))
    preparation = time.perf_counter() - started
    result = {"puzzle": name, "baseline_origin": origin, "reference_shape": method.reference_shape.labels,
              "group_order": str(method.group_order), "quotient_order": str(method.quotient_order),
              "kernel_order": str(method.kernel_order), "gap_version": method.gap_version,
              "source_method_fingerprint": method.to_dict()["fingerprint"],
              "source_correction_count": len(method.algorithms),
              "source_correction_definition_htm": sum(a.htm_length for a in method.algorithms),
              "stage_features": [stage.feature.to_dict() for stage in method.stages], "variants": {}}
    timings = {"puzzle": name, "preparation_seconds": preparation, "variants": {}}
    for label, options in variants(settings, ratios):
        started = time.perf_counter()
        repertoire = c.optimize_human_repertoire(method, **options)
        search_seconds = time.perf_counter() - started
        started = time.perf_counter()
        loaded, verification = verify(repertoire, states)
        timings["variants"][label] = {"search_seconds": search_seconds,
                                     "reload_and_physical_verification_seconds": time.perf_counter() - started}
        result["variants"][label] = compact_record(loaded, verification)
        if label == "strict" and artifacts is not None and name.startswith("Alcatraz "):
            suffix = name.split()[-1]
            loaded.save(artifacts / f"alcatraz-{suffix}-repertoire.json")
            loaded.write_guide(artifacts / f"alcatraz-{suffix}-repertoire.md")
    return result, timings


def distinct_paths(paths):
    paths = [path for path in paths if path is not None]
    for index, path in enumerate(paths):
        for previous in paths[:index]:
            if (path.resolve() == previous.resolve() or
                    path.exists() and previous.exists() and path.samefile(previous)):
                raise ValueError("result, measurements, artifacts, and source methods must be different files")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", choices=REFERENCES, action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--artifacts", type=Path, help="write the two strict Alcatraz wrappers and guides")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--preference", choices=("memory", "execution"), default="memory")
    parser.add_argument("--tradeoff-ratio", type=float, action="append")
    parser.add_argument("--no-symmetry", action="store_true")
    for name, default in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        names = tuple(args.puzzle or REFERENCES)
        settings = {name: getattr(args, name) for name in DEFAULTS}
        for name, value in settings.items():
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")
        settings.update(preference=args.preference, allow_symmetry=not args.no_symmetry)
        ratios = tuple(args.tradeoff_ratio or (1.1, 1.25))
        if any(not isfinite(ratio) or ratio <= 1 for ratio in ratios) or len(set(ratios)) != len(ratios):
            raise ValueError("tradeoff ratios must be distinct, finite values greater than one")
        if args.timeout is not None and (not isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        paths = [args.output, args.measurements]
        paths.extend(dict.fromkeys(RESEARCH_RESULTS / f"alcatraz-{name.split()[-1]}-method.json"
                                   for name in names if name.startswith("Alcatraz ")))
        if args.artifacts is not None:
            if args.artifacts.exists() and not args.artifacts.is_dir():
                raise ValueError("artifacts must name a directory")
            for name in names:
                if name.startswith("Alcatraz "):
                    suffix = name.split()[-1]
                    paths.extend(args.artifacts / f"alcatraz-{suffix}-repertoire.{extension}"
                                 for extension in ("json", "md"))
        distinct_paths(paths)
        if args.artifacts is not None:
            args.artifacts.mkdir(parents=True, exist_ok=True)
        pairs = [compare(name, settings, ratios, args.timeout, args.artifacts) for name in names]
        record = {"format": "bce-v2-human-repertoire-comparison", "version": 1,
                  "quality": "computational_baseline", "human_reviewed": False,
                  "metrics_scope": "all reference-group states; simplified full physical solution words",
                  "settings": settings, "tradeoff_ratios": list(ratios),
                  "basic_control_scope": "zero bounded proposals/deletions; initial inverse-graph controls remain",
                  "results": [result for result, _ in pairs]}
        text = json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output is None:
            print(text, end="")
        else:
            args.output.write_text(text, encoding="utf-8")
        if args.measurements is not None:
            args.measurements.write_text(json.dumps(
                {"format": "bce-v2-human-repertoire-measurements", "version": 1,
                 "results": [timings for _, timings in pairs]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (ValueError, TypeError, RuntimeError, OSError) as error:
        print(f"compare-human-repertoires: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
