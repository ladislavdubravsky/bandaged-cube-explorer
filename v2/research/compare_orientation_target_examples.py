#!/usr/bin/env python3
"""Paired small-group quality and preparation-time comparison for phase targets.

Group preparation is shared and measured separately. Search timing includes
dictionary discovery and complete-method scoring/validation, and excludes
portable loading, replay and repertoire compilation. Balanced run order
reduces cache/order bias; all experiments run sequentially.
"""

import argparse
from functools import wraps
import json
from pathlib import Path
import platform
from statistics import median
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chain_search import _Context


POCKET = (1, 1, 2, 1, 1, 2, 3, 3, 0,
          0, 0, 4, 0, 0, 4, 5, 5, 6,
          0, 0, 4, 0, 0, 4, 5, 5, 6)
REFERENCES = ("Alcatraz", "Bicube Fuse", "Shark Fin Soup", "BandagedPocketCube")


def compare(name, repeats):
    started = perf_counter()
    reference = c.Shape(POCKET) if name == "BandagedPocketCube" else c.fixture(name)
    plan = c.plan_human_stages(reference, max_group_elements=10_368, timeout=60)
    preparation = perf_counter()-started
    options = dict(max_expansions=8, max_methods=2, beam_width=2,
                   discovery_options={"max_candidates":128, "max_states":1000, "max_word_length":3})
    rows, saved, targets_time = [], {}, [0.0]
    original = _Context.orientation_targets

    @wraps(original)
    def timed_targets(self, members):
        start = perf_counter()
        try:
            return original(self, members)
        finally:
            targets_time[0] += perf_counter()-start

    for repeat in range(repeats):
        order = ("control", "orientation_targets") if repeat % 2 == 0 else ("orientation_targets", "control")
        for arm in order:
            targets_time[0] = 0.0
            started = perf_counter()
            with patch.object(_Context, "orientation_targets", timed_targets):
                search = c.select_human_chain(
                    plan, target_options={"max_methods":0} if arm == "control" else None, **options)
            seconds = perf_counter()-started
            selected = next(candidate for candidate in search.candidates if candidate.id == search.selected_id)
            row = dict(arm=arm, repeat=repeat, selection_seconds=seconds,
                       target_analysis_seconds=targets_time[0], mean_htm=selected.metrics["mean_htm"],
                       worst_htm=selected.metrics["worst_htm"], selected_source=selected.source,
                       selected_orientation_stages=sum(stage.feature.kind == "orient_slots"
                                                       for stage in search.method.stages),
                       targets_found=len(search.metadata["attribute_targets"]),
                       subgroup_prefixes_examined=search.metadata["attribute_prefixes_evaluated"])
            rows.append(row)
            if arm in saved and saved[arm][0] != row["mean_htm"]:
                raise AssertionError("run order changed deterministic method quality")
            saved[arm] = row["mean_htm"], search.method
            print(json.dumps(dict(puzzle=name, **row), sort_keys=True), flush=True)
    verification = {}
    for arm, (mean, original_method) in saved.items():
        method = c.HumanMethod.from_dict(original_method.to_dict())
        lengths = []
        for permutation in plan.group.permutations:
            word = plan.group.witness(permutation).expanded_moves(plan.group.generators)
            state = c.State(reference).apply(word)
            source = c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                                        edges=state.edges, flips=state.flips)
            result = method.apply(source)
            if (source.scramble is not None or not result.state.is_solved
                    or source.apply(result.turn_sequence) != result.state):
                raise AssertionError("loaded method failed exhaustive imported-state replay")
            lengths.append(len(result.turn_sequence.split()))
        if sum(lengths)/len(lengths) != mean:
            raise AssertionError("physical mean disagrees with selected-method metric")
        verification[arm] = dict(states_replayed=len(lengths), all_physical_replays_passed=True)
    summaries = {}
    for arm in saved:
        samples = [row for row in rows if row["arm"] == arm]
        summaries[arm] = dict(mean_htm=samples[0]["mean_htm"], worst_htm=samples[0]["worst_htm"],
            median_selection_seconds=median(row["selection_seconds"] for row in samples),
            median_target_analysis_seconds=median(row["target_analysis_seconds"] for row in samples),
            selected_orientation_stages=samples[0]["selected_orientation_stages"],
            **verification[arm])
    return dict(puzzle=name, reference_shape=reference.labels, group_order=len(plan.group),
                preparation_seconds=preparation, search_options=options, runs=rows, summary=summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", choices=REFERENCES, action="append")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] /
                        "research-results/orientation-target-example-comparison.json")
    args = parser.parse_args()
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    record = dict(format="bce-v2-orientation-target-example-comparison", version=1,
                  python=platform.python_version(), repeats=args.repeats,
                  timing_scope=__doc__, results=[])
    for name in args.puzzle or REFERENCES:
        record["results"].append(compare(name, args.repeats))
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
