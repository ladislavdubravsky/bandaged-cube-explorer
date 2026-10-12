#!/usr/bin/env python3
"""Compare complete explicit phase-aware methods with exhaustive physical replay."""

import argparse
import json
from pathlib import Path

import bce_v2 as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] /
                        "research-results/algorithm-informed-alcatraz.json")
    args = parser.parse_args()
    plan = c.plan_human_stages(c.fixture("Alcatraz"), max_group_elements=324, timeout=45)
    options = dict(max_expansions=8, max_methods=2, beam_width=2,
                   discovery_options={"max_candidates":128, "max_states":1000, "max_word_length":3})
    record = {"format":"bce-v2-algorithm-informed-alcatraz", "version":1,
              "reference":"Alcatraz", "group_order":len(plan.group),
              "search_options":options, "hard_learned_body_limit":False, "results":[]}
    for name, targets in (("control", {"max_methods":0}), ("orientation_targets", None)):
        search = c.select_human_chain(plan, target_options=targets, **options)
        method = c.HumanMethod.from_dict(search.method.to_dict())
        costs = []
        for permutation in plan.group.permutations:
            word = plan.group.witness(permutation).expanded_moves(plan.group.generators)
            state = c.State(plan.inventory.root_shape).apply(word)
            source = c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                                        edges=state.edges, flips=state.flips)
            result = method.apply(source)
            if (source.scramble is not None or not result.state.is_solved
                    or source.apply(result.turn_sequence) != result.state):
                raise AssertionError("loaded complete method failed imported-state replay")
            costs.append(len(result.turn_sequence.split()))
        mean = sum(costs) / len(costs)
        selected = next(candidate for candidate in search.candidates if candidate.id == search.selected_id)
        if mean != selected.metrics["mean_htm"]:
            raise AssertionError("independent physical costs disagree with search metrics")
        record["results"].append({"name":name, "selected_source":selected.source,
            "features":[stage.feature.to_dict() for stage in method.stages],
            "mean_htm":mean, "worst_htm":max(costs), "states_replayed":len(costs),
            "all_physical_replays_passed":True,
            "best_pooled_control_mean_htm":min(candidate.metrics["mean_htm"]
                for candidate in search.candidates if candidate.source.startswith("baseline:")),
            "attribute_targets":search.metadata["attribute_targets"]})
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps([{key:row[key] for key in ("name", "selected_source", "mean_htm", "states_replayed")}
                      for row in record["results"]], sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
