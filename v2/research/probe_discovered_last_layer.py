#!/usr/bin/env python3
"""Discover and exhaustively replay a palette-led ordinary last-layer method.

The production search receives witnessed algorithm bodies and permissions,
with neither a seeded start domain nor suffix goals. Native cubie arrays are
used only by the independent exhaustive fixture. A returned start-domain
contract does not establish a method for arbitrary full-cube scrambles.
"""

import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette
from bce_v2.coarse_methods import load_coarse_method, _palette_record
from bce_v2.coarse_search import discover_coarse_method
from bce_v2.computation import Computation
from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression
from bce_v2.palette_policies import recipe_taught_ids
from probe_standard_last_layer import BODIES, SOURCE, last_layer_states


def prepare_palette():
    """Supply legal physical vocabulary without importing any milestone."""
    analysis = c.analyze_isotropy(c.Shape(), timeout=90)
    builder = AlgorithmLibrary(analysis.loops, (), (), ())
    generators = {generator.turn_sequence: generator for generator in analysis.loops.generators}

    def algorithm(identifier, word):
        proof = LoopExpression.sequence(*(LoopExpression.power(
            LoopExpression.loop(generators[token[0]].id),
            2 if token.endswith("2") else -1 if token.endswith("'") else 1)
            for token in word.split()))
        return replace(builder.build_algorithm(LoopExpression.turns(word, proof)), id=identifier)

    adjustments = tuple(algorithm(word, word) for word in ("U", "U2", "U'"))
    palette = AlgorithmPalette.from_algorithms(
        tuple(algorithm(identifier, word) for identifier, word in BODIES.items()),
        setups=adjustments, adjustments=adjustments, allow_inverse=False)
    return analysis, palette


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]
                        / "research-results/discovered-last-layer.json")
    parser.add_argument("--method-output", type=Path,
                        default=Path("/tmp/bce-v2-discovered-last-layer-method.json"))
    parser.add_argument("--search-output", type=Path,
                        default=Path("/tmp/bce-v2-discovered-last-layer-search.json"))
    parser.add_argument("--guide-output", type=Path,
                        default=Path("/tmp/bce-v2-discovered-last-layer-guide.md"))
    parser.add_argument("--reuse-method", action="store_true")
    parser.add_argument("--max-taught-bodies", type=int, default=7)
    parser.add_argument("--beam-width", type=int, default=1)
    parser.add_argument("--max-expansions", type=int, default=6)
    parser.add_argument("--max-stages", type=int, default=6)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--max-observations", type=int, default=128)
    parser.add_argument("--preference", choices=("recognition", "execution"), default="recognition")
    args = parser.parse_args()
    started = perf_counter()
    preparation_seconds = discovery_seconds = serialization_seconds = 0.0
    if not args.reuse_method:
        phase_started = perf_counter()
        analysis, palette = prepare_palette()
        preparation_seconds = perf_counter() - phase_started
        print(json.dumps({"phase": "palette_prepared", "preparation_seconds": preparation_seconds}), flush=True)

        def progress(event):
            if event["phase"] == "coarse_method_frontier":
                print(json.dumps(event, sort_keys=True), flush=True)

        phase_started = perf_counter()
        with Computation(progress=progress).activate():
            search = discover_coarse_method(analysis, palette=palette,
                max_taught_bodies=args.max_taught_bodies, beam_width=args.beam_width,
                max_expansions=args.max_expansions, max_stages=args.max_stages,
                max_candidates=args.max_candidates, max_observations=args.max_observations,
                preference=args.preference, timeout=90)
        discovery_seconds = perf_counter() - phase_started
        if search.method is None:
            raise AssertionError("bounded palette-only search found no complete suffix: " +
                                 json.dumps(search.metadata, sort_keys=True))
        search_record = search.to_dict(include_method=False)
        if search_record["metadata"]["workspace_seeded"] or search_record["metadata"]["goals_seeded"]:
            raise AssertionError("acceptance search received seeded milestones")
        phase_started = perf_counter()
        search.method.save(args.method_output)
        args.search_output.write_text(json.dumps(search_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        serialization_seconds = perf_counter() - phase_started
        print(json.dumps({"phase": "method_saved", "discovery_seconds": discovery_seconds,
                          "case_counts": [stage.case_count for stage in search.method.stages],
                          "taught_body_ids": list(search.method.taught_body_ids)}), flush=True)
    else:
        search_record = json.loads(args.search_output.read_text(encoding="utf-8"))
    selected = next(candidate for candidate in search_record["candidates"]
                    if candidate["id"] == search_record["selected_id"])
    search_metadata = search_record["metadata"]
    if search_metadata["workspace_seeded"] or search_metadata["goals_seeded"]:
        raise AssertionError("saved search was not palette-only discovery")
    with patch("subprocess.run", side_effect=AssertionError("portable method must execute without GAP")):
        phase_started = perf_counter()
        method = load_coarse_method(args.method_output)
        offline_load_seconds = perf_counter() - phase_started
        print(json.dumps({"phase": "loaded_offline", "offline_load_seconds": offline_load_seconds}), flush=True)
        if method.group_order != 62_208:
            raise AssertionError("inferred workspace differs from the independent last-layer fixture")
        if [feature.to_dict() for feature in method.domain_features] != selected["domain_features"]:
            raise AssertionError("loaded method changed the inferred start contract")
        if [stage.feature.to_dict() for stage in method.stages] != selected["features"]:
            raise AssertionError("loaded method changed the discovered suffix")
        taught_per_recipe = recipe_taught_ids(method.palette, search_metadata["settings"]["max_short_setup_htm"])
        actual_taught = {identifier for _, _, recipe in method.case_recipes
                         for call in recipe for identifier in taught_per_recipe[call]}
        if actual_taught != set(selected["taught_definition_ids"]):
            raise AssertionError("compiled palette vocabulary differs from the global search commitment")
        if len(selected["taught_definition_ids"]) > search_metadata["settings"]["max_taught_bodies"]:
            raise AssertionError("method violates the global taught-definition budget")
        outside = c.State().apply("R")
        rejected = method.apply(outside)
        if rejected.status != "outside_domain" or rejected.steps or rejected.state != outside:
            raise AssertionError("suffix incorrectly accepts an unprepared full-cube scramble")
        certificates = method.ambient_method._symbolic_chain.stages[method.prefix_stage_count:]
        rows = {(number, observation): recipe for number, observation, recipe in method.case_recipes}
        recipe_catalog = {recipe.id: recipe for recipe in method.palette.recipes}
        method.write_guide(args.guide_output)
        stage_costs = [0] * len(method.stages)
        stage_visits = [Counter() for _ in method.stages]
        count = total = worst = physical_total = physical_worst = 0
        endpoint_checks = concatenated_replays = 0
        distinct_states = set()
        phase_started = perf_counter()
        for state in last_layer_states():
            if state.scramble is not None:
                raise AssertionError("independent validation fixture retained move history")
            encoded = bytes(state.sticker_permutation)
            if encoded in distinct_states:
                raise AssertionError("independent validation fixture repeated a native state")
            distinct_states.add(encoded)
            if state.sticker_permutation not in method.domain_group:
                raise AssertionError("an independent native last-layer state misses the inferred domain")
            result = method.apply(state)
            if result.status != "solved" or not result.state.is_solved:
                raise AssertionError("loaded discovered method fails exhaustive physical execution")
            additive = sum(step.htm_length for step in result.steps)
            total += additive
            worst = max(worst, additive)
            physical = len(result.turn_sequence.split())
            physical_total += physical
            physical_worst = max(physical_worst, physical)
            observed_steps = {step.stage_number: step for step in result.steps}
            for stage in method.stages:
                step = observed_steps.get(stage.number)
                observation = step.observation if step is not None else stage.solved_observation
                stage_visits[stage.number - 1][observation] += 1
                if step is not None:
                    stage_costs[stage.number - 1] += step.htm_length
                    if step.after.sticker_permutation not in certificates[stage.number - 1].group_after:
                        raise AssertionError("a physical endpoint misses its exact cumulative stabilizer")
                    endpoint_checks += 1
            if count % 1024 == 0:
                if state.apply(result.turn_sequence) != result.state:
                    raise AssertionError("concatenated native execution differs from the portable stage trace")
                concatenated_replays += 1
            count += 1
            if count % 8192 == 0:
                print(json.dumps({"phase": "exhaustive_replay", "replayed": count,
                                  "wall_seconds": perf_counter() - started}), flush=True)
        if count != method.group_order:
            raise AssertionError("independent fixture does not exhaust the certified starting domain")
        exhaustive_execution_seconds = perf_counter() - phase_started
    stage_reports = []
    for stage in method.stages:
        visits = stage_visits[stage.number - 1]
        if set(visits) != set(stage.observations) or len(set(visits.values())) != 1:
            raise AssertionError("exhaustive hidden-state replay disagrees with a uniform stage orbit")
        case_rows = []
        for case in stage.cases:
            recipe = rows[stage.number, case.observation]
            case_rows.append({"observation": list(case.observation), "recipe": list(recipe),
                              "recipe_additive_htm": sum(recipe_catalog[identifier].htm_length for identifier in recipe)})
        stage_reports.append({"stage": stage.number, "feature": stage.feature.to_dict(),
                              "case_count": stage.case_count, "order_before": str(stage.order_before),
                              "order_after": str(stage.order_after), "states_per_observation": next(iter(visits.values())),
                              "mean_physical_stage_htm": stage_costs[stage.number - 1] / count,
                              "taught_definition_ids": sorted({identifier for case in stage.cases
                                  for call in rows[stage.number, case.observation] for identifier in taught_per_recipe[call]}),
                              "complete_native_hidden_state_visits": count, "cases": case_rows})
    record = {"format": "bce-v2-discovered-last-layer-acceptance", "version": 1,
              "production_integration": True, "goal_discovery_performed": True,
              "workspace_discovery_performed": True, "supplied_domain_features": None,
              "supplied_suffix_features": None, "whole_scramble_method_claim": False,
              "entry_policy_discovered": False,
              "starting_domain_claim": "all ordinary reference-group states satisfying the inferred anchored workspace; preparing that workspace from arbitrary scrambles is not certified",
              "coverage_scope": method.coverage_scope, "start_domain_order": method.group_order,
              "ambient_group_order": str(method.ambient_group_order),
              "inferred_workspace_features": [feature.to_dict() for feature in method.domain_features],
              "discovered_stage_features": [stage.feature.to_dict() for stage in method.stages],
              "selected_search_candidate": selected,
              "search_metadata": search_metadata,
              "bounded_method_search": True, "exhaustive_method_search_claim": False,
              "globally_optimal_method_claim": False, "one_algorithm_per_look_claim": False,
              "loaded_method_replayed_without_gap": True,
              "complete_physical_state_replays": count, "all_complete_states_solved": True,
              "distinct_native_states": len(distinct_states),
              "cumulative_stabilizer_endpoint_checks": endpoint_checks,
              "sampled_concatenated_native_replays": concatenated_replays,
              "all_cumulative_endpoint_goals_preserved": True,
              "strict_palette_coverage": True, "unconstrained_fallback_used": False,
              "outside_domain_state_rejected_without_execution": True,
              "supplied_long_bodies": BODIES, "physical_body_source": SOURCE,
              "validation_palette": _palette_record(method.palette),
              "reference_shape": method.reference_shape.labels,
              "supplied_long_body_count": len(method.palette.bodies),
              "used_long_body_ids": list(method.taught_body_ids),
              "global_taught_definition_ids": sorted(actual_taught),
              "global_taught_definition_count": len(actual_taught),
              "max_taught_definitions": search_metadata["settings"]["max_taught_bodies"],
              "global_taught_budget_satisfied": True,
              "case_counts": [stage.case_count for stage in method.stages],
              "total_stage_observation_count": sum(stage.case_count for stage in method.stages),
              "maximum_stage_observation_count": max(stage.case_count for stage in method.stages),
              "stage_reports": stage_reports,
              "mean_last_layer_additive_htm": total / count,
              "worst_last_layer_additive_htm": worst,
              "mean_last_layer_physical_htm": physical_total / count,
              "worst_last_layer_physical_htm": physical_worst,
              "certified_additive_costs": method.additive_costs(),
              "method_artifact": str(args.method_output), "search_artifact": str(args.search_output),
              "guide_artifact": str(args.guide_output), "discovery_artifact_reused": args.reuse_method,
              "artifact_discovery_seconds": search_metadata["wall_seconds"],
              "wall_seconds": perf_counter() - started,
              "timing_scope": "current invocation; reused discovery time is recorded separately as artifact_discovery_seconds",
              "preparation_seconds": preparation_seconds, "discovery_seconds": discovery_seconds,
              "serialization_seconds": serialization_seconds, "offline_load_seconds": offline_load_seconds,
              "exhaustive_execution_seconds": exhaustive_execution_seconds}
    if total / count != record["certified_additive_costs"]["htm"]["mean"]:
        raise AssertionError("certified domain expectation differs from exhaustive native execution")
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "guide": str(args.guide_output),
                      **{key: record[key] for key in (
                          "all_complete_states_solved", "complete_physical_state_replays",
                          "case_counts", "global_taught_definition_ids",
                          "mean_last_layer_additive_htm", "mean_last_layer_physical_htm",
                          "worst_last_layer_physical_htm", "artifact_discovery_seconds",
                          "exhaustive_execution_seconds")}}, sort_keys=True))


if __name__ == "__main__":
    main()
