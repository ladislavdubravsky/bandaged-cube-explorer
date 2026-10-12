#!/usr/bin/env python3
"""Replay bounded adaptive workspace entry followed by a discovered suffix.

The saved suffix was inferred from a four-body palette without supplied
milestones. Entry receives only legal original-loop adjustments and the
suffix's inferred domain. Scramble strings create independent native fixtures;
the controller receives imported colored states with no scramble history.
Sample success is not a proof of complete entry coverage or a recognition
table for human use. A separate tiny bandage is exhaustively replayed.
"""

import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import random
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette
from bce_v2.coarse_methods import load_coarse_method
from bce_v2.human_chains import _observation, _resolve_feature
from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression, _loops_from_records
from probe_slot_orientation_stage import preserves_first_two_layers


def history_free(state):
    imported = c.State.from_cubies(state.specification, corners=state.corners,
        twists=state.twists, edges=state.edges, flips=state.flips)
    if imported.scramble is not None or imported != state:
        raise AssertionError("native imported fixture retained history or changed colors")
    return imported


def loop_adjustment_palette(method):
    """Explicitly admit signed original loops, never computer entry witnesses."""
    builder = AlgorithmLibrary(_loops_from_records(method.generators), (), (), ())
    algorithms = []
    for generator in method.generators:
        # Native original roots can have duplicate effects; retain stable IDs.
        for power in (1, 2, -1):
            expression = LoopExpression.power(LoopExpression.loop(generator.id), power)
            algorithm = builder.build_algorithm(expression)
            if algorithm.htm_length and algorithm.htm_length <= 4:
                algorithms.append(replace(algorithm, id=f"loop:{generator.id}:{power}"))
    return AlgorithmPalette.from_algorithms((), adjustments=algorithms, allow_inverse=False)


def sample_scrambles(count, length, seed):
    rng = random.Random(seed)
    words = []
    for _ in range(count):
        tokens, previous = [], None
        for _ in range(length):
            face = rng.choice([face for face in "URFDLB" if face != previous])
            tokens.append(face + rng.choice(("", "2", "'")))
            previous = face
        words.append(" ".join(tokens))
    return tuple(words)


def feature_satisfied(method, state, feature):
    handle = _resolve_feature(method.inventory, feature)
    action = method.inventory.action(tuple(state.sticker_permutation))
    return (_observation(action, handle, feature.kind) ==
            _observation(method.inventory.identity(), handle, feature.kind))


def application_record(application):
    """Keep readable diagnostics without embedding the portable certificates."""
    record = {"status": application.status,
              "turn_sequence": application.turn_sequence,
              "physical_htm": len(application.turn_sequence.split()),
              "entry_step_count": len(application.entry_steps),
              "metadata": dict(application.metadata)}
    if application.suffix_application is not None:
        record["suffix_status"] = application.suffix_application.status
    return record


def check_entry_endpoints(method, initial, application):
    current, checks = initial, 0
    for step in application.entry_steps:
        if step.before != current:
            raise AssertionError("entry correction is disconnected from its native predecessor")
        current = current.apply(step.turn_sequence)
        if current != step.after:
            raise AssertionError("native entry endpoint differs from controller prediction")
        for feature in step.protected_features:
            if not feature_satisfied(method.suffix, current, feature):
                raise AssertionError("entry endpoint displaced an earlier commitment")
            checks += 1
        if step.status in ("ready", "already_satisfied"):
            if not feature_satisfied(method.suffix, current, step.feature):
                raise AssertionError("entry correction failed its selected assembly goal")
            checks += 1
    if application.suffix_application is not None:
        if not preserves_first_two_layers(current):
            raise AssertionError("suffix began before native F2L was restored")
        for feature in method.suffix.domain_features:
            if not feature_satisfied(method.suffix, current, feature):
                raise AssertionError("suffix starting contract fails after adaptive entry")
            checks += 1
    return checks


def prepare_tiny_suffix():
    """Seeded, directed four-state bandage fixture for exhaustive entry replay."""
    shape = c.Shape([1] * 9 + [2] * 18)
    analysis = c.analyze_isotropy(shape, timeout=30)
    builder = AlgorithmLibrary(analysis.loops, (), (), ())
    generator = next(generator for generator in analysis.loops.generators
                     if generator.turn_sequence == "U")
    clockwise = replace(builder.build_algorithm(LoopExpression.loop(generator.id)), id="U")
    palette = AlgorithmPalette.from_algorithms((), adjustments=(clockwise,), allow_inverse=False)
    action = analysis.block_inventory.action(clockwise.permutation)
    mobile = tuple(cell for index, block in enumerate(analysis.block_inventory.blocks)
                   if action.destinations[index] != index or action.phases[index]
                   for cell in block.cells)
    target = c.BlockFeature("solve_blocks", mobile)
    suffix = c.compile_coarse_method(analysis, features=(), palette=palette,
                                     domain_features=(target,), timeout=30)
    return suffix, palette


def replay_tiny_fixture(compile_workspace_method):
    suffix, palette = prepare_tiny_suffix()
    with patch("subprocess.run", side_effect=AssertionError("tiny fixture executes offline")):
        method = compile_workspace_method(suffix, entry_palette=palette,
            max_taught_bodies=0, max_components=1, max_candidates=2,
            controller_options={"max_depth": 3, "max_nodes": 10_000})
        loaded = type(method).from_dict(method.to_dict())
        records = []
        for word in ("", "U", "U2", "U'"):
            initial = history_free(c.State(suffix.reference_shape).apply(word))
            application = loaded.apply(initial)
            if application.status != "solved" or not application.state.is_solved:
                raise AssertionError("directed four-state bandage entry was not completely covered")
            if initial.apply(application.turn_sequence) != application.state:
                raise AssertionError("native bandaged whole-method replay disagrees")
            declared = {recipe.id for recipe in palette.recipes}
            if any(action_id not in declared for step in application.entry_steps
                   for action_id in step.action_ids):
                raise AssertionError("entry called an undeclared inverse or half-turn recipe")
            records.append({"fixture_scramble": word, **application_record(application)})
    return {"coverage_scope": "all_four_reference_group_states",
            "native_state_count": len(records), "all_solved": True,
            "seeded_workspace_contract": True, "declared_directed_adjustments": ["U"],
            "max_taught_bodies": 0, "fixtures": records}


def append_native_example(path, records):
    example = next((record for record in records
                    if record["kind"] == "random_full_scramble" and record["status"] == "solved"), None)
    if example is None:
        return
    lines = ["", "## Native replay example", "",
        "This imported state was solved by bounded constructive entry and the certified suffix. "
        "The entry words below are one computed example; they do not form a complete human recognition table.",
        "", "Fixture scramble:", "", "```text", example["fixture_scramble"], "```", "",
        "| Entry stage | Promised components | Correction | HTM |",
        "| --- | --- | --- | ---: |"]
    for number, correction in enumerate(example["entry_corrections"], 1):
        names = ", ".join(c.CELL_NAMES[cell] for cell in correction["feature"]["reference_cells"])
        word = correction["turn_sequence"] or "already satisfied"
        lines.append(f"| {number} | {names} | `{word}` | {len(correction['turn_sequence'].split())} |")
    lines.extend(["", f"Entry stage sum: {example['entry_stage_htm']} HTM. "
        f"Suffix stage sum: {example['suffix_stage_htm']} HTM. "
        f"Concatenated native execution: {example['physical_htm']} HTM.", ""])
    path.write_text(path.read_text(encoding="utf-8") + "\n".join(lines), encoding="utf-8")


def random_sample_summary(records):
    random_records = [record for record in records if record["kind"] == "random_full_scramble"]
    solved = [record for record in random_records if record["status"] == "solved"]
    return {"fixture_count": len(random_records), "solved_count": len(solved),
        "complete_entry_coverage_claim": False,
        "distinct_entry_chains": len({tuple(tuple(correction["feature"]["reference_cells"])
            for correction in record["entry_corrections"]) for record in random_records}),
        "mean_entry_stage_htm_over_solved": sum(record["entry_stage_htm"] for record in solved)
            / len(solved) if solved else None,
        "mean_physical_htm_over_solved": sum(record["physical_htm"] for record in solved)
            / len(solved) if solved else None,
        "max_entry_nodes_expanded": max((record["metadata"]["entry_nodes_expanded"]
                                          for record in random_records), default=0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suffix", type=Path,
        default=Path("/tmp/bce-v2-discovered-last-layer-method-final-code.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]
        / "research-results/workspace-entry.json")
    parser.add_argument("--method-output", type=Path,
        default=Path("/tmp/bce-v2-workspace-method.json"))
    parser.add_argument("--guide-output", type=Path,
        default=Path("/tmp/bce-v2-workspace-method-guide.md"))
    parser.add_argument("--scrambles", type=int, default=8)
    parser.add_argument("--scramble-length", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--max-depth", type=int, default=12)
    parser.add_argument("--max-nodes", type=int, default=2_000_000)
    parser.add_argument("--max-entry-nodes", type=int, default=5_000_000)
    parser.add_argument("--max-candidates", type=int, default=6)
    args = parser.parse_args()
    # Imported lazily so this file can be inspected while production APIs are
    # being implemented without substituting an independent search algorithm.
    from bce_v2.workspace_methods import WorkspaceMethod, compile_workspace_method
    from bce_v2.workspace_goals import propose_workspace_anchors

    started = perf_counter()
    tiny = replay_tiny_fixture(compile_workspace_method)
    with patch("subprocess.run", side_effect=AssertionError("entry must run offline without GAP")):
        suffix = load_coarse_method(args.suffix)
        if suffix.group_order != 62_208:
            raise AssertionError("acceptance requires the inferred ordinary F2L suffix")
        entry_palette = loop_adjustment_palette(suffix)
        method = compile_workspace_method(suffix, entry_palette=entry_palette,
            max_taught_bodies=7, max_candidates=args.max_candidates,
            max_entry_nodes=args.max_entry_nodes,
            controller_options={"max_depth": args.max_depth, "max_nodes": args.max_nodes})
        method.save(args.method_output)
        loaded = WorkspaceMethod.load(args.method_output)
        loaded.write_guide(args.guide_output)
        if len(loaded.taught_definition_ids) > 7 or loaded.human_method_complete:
            raise AssertionError("bounded entry changed its teaching budget or completeness claim")
        original_plan_step = loaded.controller.plan_step
        correction_seconds = {}

        def tracked_plan_step(state, feature, **options):
            phase_started = perf_counter()
            detail = {"feature": feature.to_dict(),
                      "protected_count": len(options.get("protected_features", ()))}
            print(json.dumps({"phase": "entry_candidate_started", **detail}), flush=True)
            correction = original_plan_step(state, feature, **options)
            correction_seconds[id(correction)] = perf_counter()-phase_started
            print(json.dumps({"phase": "entry_candidate_finished", **detail,
                "seconds": correction_seconds[id(correction)], "status": correction.status,
                "metrics": dict(correction.metrics)}), flush=True)
            return correction

        loaded.controller.plan_step = tracked_plan_step
        print(json.dumps({"phase": "prepared_offline", "seconds": perf_counter()-started}), flush=True)
        fixtures = [("random_full_scramble", word) for word in sample_scrambles(
            args.scrambles, args.scramble_length, args.seed)]
        fixtures.append(("late_f2l_disruption", "R U R'"))
        records, endpoint_checks = [], 0
        for number, (kind, word) in enumerate(fixtures, 1):
            initial = history_free(c.State().apply(word))
            case_started = perf_counter()
            application = loaded.apply(initial)
            if initial.apply(application.turn_sequence) != application.state:
                raise AssertionError("native whole-method replay disagrees with returned colors")
            if application.status == "solved" and not application.state.is_solved:
                raise AssertionError("successful entry/suffix execution left the cube unsolved")
            endpoint_checks += check_entry_endpoints(loaded, initial, application)
            record = {"number": number, "kind": kind, "fixture_scramble": word,
                      "history_present": initial.scramble is not None,
                      "seconds": perf_counter()-case_started,
                      **application_record(application)}
            record["entry_stage_htm"] = sum(step.htm_length for step in application.entry_steps)
            record["suffix_stage_htm"] = (sum(len(step.turn_sequence.split())
                for step in application.suffix_application.steps)
                if application.suffix_application is not None else None)
            record["entry_corrections"] = [
                {"status": step.status, "feature": step.feature.to_dict(),
                 "protected_features": [feature.to_dict() for feature in step.protected_features],
                 "protected_cells": sorted({cell for feature in step.protected_features
                                            for cell in feature.cells}),
                 "observation": list(step.observation),
                 "recognition_component_count": len(step.observation) // 2,
                 "action_ids": list(step.action_ids), "turn_sequence": step.turn_sequence,
                 "seconds": correction_seconds.get(id(step)),
                 "metrics": dict(step.metrics)} for step in application.entry_steps]
            records.append(record)
            print(json.dumps({"phase": "fixture_complete", **record}, sort_keys=True), flush=True)
        counts = Counter(record["status"] for record in records)
        report = {"format": "bce-v2-workspace-entry-probe", "version": 1,
            "coverage_scope": "bounded_native_scramble_sample",
            "complete_entry_coverage_claim": False, "human_recognition_table_claim": False,
            "ordinary_native_fixture_count": len(records), "ordinary_status_counts": dict(counts),
            "distinct_adaptive_entry_chains": len({tuple(tuple(
                correction["feature"]["reference_cells"]) for correction in record["entry_corrections"])
                for record in records}),
            "history_free_execution": True, "gap_subprocess_blocked_during_execution": True,
            "unconstrained_solver_fallback_used": False,
            "suffix_group_order": str(suffix.group_order),
            "inferred_domain_features": [feature.to_dict() for feature in suffix.domain_features],
            "suffix_case_counts": [stage.case_count for stage in suffix.stages],
            "combined_taught_definition_ids": list(loaded.taught_definition_ids),
            "global_taught_definition_budget": 7,
            "declared_entry_adjustment_count": len(entry_palette.adjustments),
            "entry_uses_small_pattern_databases": True,
            "supplied_entry_milestones": [],
            "geometry_proposed_anchor_features": [feature.to_dict() for feature in loaded.anchors],
            "geometry_anchor_evidence": propose_workspace_anchors(loaded.inventory,
                tuple(cell for index in loaded.target_indices
                      for cell in loaded.inventory.blocks[index].cells),
                max_candidates=args.max_candidates).to_dict(),
            "settings": vars(args) | {}, "ordinary_fixtures": records,
            "ordinary_random_sample_summary": random_sample_summary(records),
            "workspace_method_settings": loaded.settings,
            "entry_endpoint_checks": endpoint_checks,
            "exhaustive_tiny_bandage": tiny,
            "wall_seconds": perf_counter()-started,
            "portable_method_path": str(args.method_output), "guide_path": str(args.guide_output)}
        report["settings"] = {key: str(value) if isinstance(value, Path) else value
                              for key, value in report["settings"].items()}
        append_native_example(args.guide_output, records)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"phase": "report_written", "output": str(args.output),
                          "statuses": dict(counts), "wall_seconds": report["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
