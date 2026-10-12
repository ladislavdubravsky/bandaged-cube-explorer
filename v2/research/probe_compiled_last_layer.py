#!/usr/bin/env python3
"""Certify and exhaustively replay the generic production last-layer compiler.

The fixture supplies its goals, F2L start domain and four algorithm bodies.
Production code infers no 3x3 convention and performs no goal discovery.
The saved method is loaded without GAP before all 62,208 states are replayed.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette
from bce_v2.coarse_methods import compile_coarse_method, load_coarse_method
from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression
from probe_standard_last_layer import BODIES, SOURCE, last_layer_states


def prepare():
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
    edges, corners = (c.UR, c.UF, c.UL, c.UB), (c.UFR, c.UFL, c.UBL, c.UBR)
    domain = tuple(cell for block in analysis.block_inventory.blocks
                   if block.orientation_order > 1 and not set(block.cells).intersection((*edges, *corners))
                   for cell in block.cells)
    features = (c.BlockFeature("orient_slots", edges), c.BlockFeature("orient_slots", corners),
                c.BlockFeature("place_blocks", corners), c.BlockFeature("place_blocks", edges))
    return compile_coarse_method(analysis, features=features, palette=palette,
                                domain_features=(c.BlockFeature("solve_blocks", domain),), timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]
                        / "research-results/compiled-last-layer.json")
    parser.add_argument("--method-output", type=Path,
                        default=Path("/tmp/bce-v2-compiled-last-layer-method.json"))
    parser.add_argument("--reuse-method", action="store_true",
                        help="load the method artifact instead of repeating symbolic compilation")
    args = parser.parse_args()
    started = perf_counter()
    compilation_seconds = serialization_seconds = 0.0
    if not args.reuse_method:
        phase_started = perf_counter()
        method = prepare()
        compilation_seconds = perf_counter() - phase_started
        phase_started = perf_counter()
        method.save(args.method_output)
        serialization_seconds = perf_counter() - phase_started
        print(json.dumps({"phase": "method_saved", "compilation_seconds": compilation_seconds,
                          "serialization_seconds": serialization_seconds}), flush=True)
    with patch("subprocess.run", side_effect=AssertionError("loaded method must work without GAP")):
        phase_started = perf_counter()
        method = load_coarse_method(args.method_output)
        offline_load_seconds = perf_counter() - phase_started
        print(json.dumps({"phase": "loaded_offline", "offline_load_seconds": offline_load_seconds}), flush=True)
        if method.group_order != 62_208 or [s.case_count for s in method.stages] != [8, 27, 24, 12]:
            raise AssertionError("compiled exact start domain or feature domains changed")
        count, total, worst, physical_total, physical_worst = 0, 0, 0, 0, 0
        endpoint_replays, concatenated_replays = 0, 0
        certificates = method.ambient_method._symbolic_chain.stages[method.prefix_stage_count:]
        stage_costs = [0] * len(method.stages)
        phase_started = perf_counter()
        for state in last_layer_states():
            if state.scramble is not None:
                raise AssertionError("exhaustive state unexpectedly retained move history")
            result = method.apply(state)
            if result.status != "solved" or not result.state.is_solved:
                raise AssertionError("loaded generic method fails exhaustive physical replay")
            additive = sum(step.htm_length for step in result.steps)
            total += additive
            worst = max(worst, additive)
            physical = len(result.turn_sequence.split())
            physical_total += physical
            physical_worst = max(physical_worst, physical)
            for step in result.steps:
                stage_costs[step.stage_number - 1] += step.htm_length
                if step.after.sticker_permutation not in certificates[step.stage_number - 1].group_after:
                    raise AssertionError("a physical stage endpoint misses its exact cumulative stabilizer")
                endpoint_replays += 1
            if count % 1024 == 0:
                if state.apply(result.turn_sequence) != result.state:
                    raise AssertionError("concatenated physical execution differs from its stage trace")
                concatenated_replays += 1
            count += 1
            if count % 8192 == 0:
                print(json.dumps({"replayed": count, "wall_seconds": perf_counter() - started}), flush=True)
        if count != method.group_order:
            raise AssertionError("exhaustive physical replay does not cover the exact domain")
        exhaustive_execution_seconds = perf_counter() - phase_started
    record = {"format": "bce-v2-compiled-last-layer-acceptance", "version": 1,
              "production_integration": True, "goal_discovery_performed": False,
              "whole_scramble_method_claim": False,
              "coverage_scope": method.coverage_scope, "start_domain_order": method.group_order,
              "ambient_group_order": str(method.ambient_group_order),
              "loaded_method_replayed_without_gap": True,
              "complete_physical_state_replays": count, "all_complete_states_solved": True,
              "cumulative_stabilizer_endpoint_checks": endpoint_replays,
              "sampled_concatenated_native_replays": concatenated_replays,
              "all_cumulative_endpoint_goals_preserved": True,
              "strict_palette_coverage": True, "unconstrained_fallback_used": False,
              "supplied_long_bodies": BODIES, "physical_body_source": SOURCE,
              "supplied_long_body_count": len(method.palette.bodies),
              "used_long_body_ids": list(method.taught_body_ids),
              "case_counts": [stage.case_count for stage in method.stages],
              "stage_mean_additive_htm": [cost / count for cost in stage_costs],
              "mean_last_layer_additive_htm": total / count,
              "worst_last_layer_additive_htm": worst,
              "mean_last_layer_physical_htm": physical_total / count,
              "worst_last_layer_physical_htm": physical_worst,
              "certified_additive_costs": method.additive_costs(),
              "method_artifact": str(args.method_output), "wall_seconds": perf_counter() - started,
              "timing_scope": "compilation, artifact serialization, offline loading and complete physical replay",
              "compilation_seconds": compilation_seconds, "serialization_seconds": serialization_seconds,
              "offline_load_seconds": offline_load_seconds,
              "exhaustive_execution_seconds": exhaustive_execution_seconds}
    if total / count != record["certified_additive_costs"]["htm"]["mean"]:
        raise AssertionError("certified uniform-domain cost differs from exhaustive execution")
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
