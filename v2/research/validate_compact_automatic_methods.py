#!/usr/bin/env python3
"""Native acceptance checks for automatically discovered compact methods.

The notebook examples remain input plus discover_method/write_guide and one
final scramble-generator cell. All experiments live here. Small reference
groups are enumerated with native
isotropy witnesses independently of the selected palette and method. Every
stage is checked over its entire certified input subgroup, including states
not encountered after this method's particular earlier corrections.

Run with v2/.venv/bin/python. Discovery uses the public defaults; no goals,
stage orders, case recipes or extra search budgets are supplied.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, deque
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import _observation, _resolve_feature
from bce_v2.human_methods import _stage_observation
from bce_v2.palette_render import certified_procedure, expanded_recipe_path
from validate_scramble_generator import check_scramble_cell


V2 = Path(__file__).resolve().parents[1]
NOTEBOOKS = (V2 / "examples" / "action-family-methods" / "Alcatraz.ipynb",
             V2 / "examples" / "action-family-methods" / "Unbandaged3x3.ipynb")


def history_free(state):
    imported = c.State.from_cubies(state.specification, corners=state.corners,
        twists=state.twists, edges=state.edges, flips=state.flips)
    assert imported == state and imported.scramble is None
    return imported


def qtm(word):
    return sum(2 if move.endswith("2") else 1 for move in word.split())


def metric(values):
    values = tuple(values)
    if not values:
        return {"count": 0, "mean": None, "worst": None}
    mean = Fraction(sum(values), len(values))
    return {"count": len(values), "mean": float(mean),
            "mean_numerator": mean.numerator, "mean_denominator": mean.denominator,
            "best": min(values), "worst": max(values)}


def check_minimal_notebooks():
    """Enforce the requested presentation without editing either notebook."""
    result = []
    for path in NOTEBOOKS:
        document = json.loads(path.read_text(encoding="utf-8"))
        code = [cell for cell in document["cells"] if cell["cell_type"] == "code"]
        check_scramble_cell(code[-1], "bandage")
        assert document["cells"][-2]["cell_type"] == "markdown"
        assert "".join(document["cells"][-2]["source"]).strip() == "## Generate a scramble"
        source = "\n".join("".join(cell["source"]) for cell in code[:-1])
        statements = ast.parse(source).body
        assignments = [node for node in statements if isinstance(node, ast.Assign)]
        assert len(assignments) == 2, f"{path.name} needs only bandage and method assignments"
        assert [node.targets[0].id for node in assignments] == ["bandage", "method"]
        assert isinstance(assignments[0].value, (ast.List, ast.Call))
        assert ast.unparse(assignments[1].value) == "c.discover_method(bandage)"
        expressions = [node for node in statements if isinstance(node, ast.Expr)]
        assert len(expressions) == 1
        assert ast.unparse(expressions[0].value) == "display(Markdown(method.write_guide()))"
        assert all(isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.Expr))
                   for node in statements), f"{path.name} contains experimental code"
        assert not any(isinstance(node, (ast.Dict, ast.For, ast.While, ast.ListComp))
                       for node in ast.walk(ast.parse(source)))
        result.append({"notebook": str(path.relative_to(V2)), "minimal": True,
                       "final_scramble_cell": True,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def native_reference_states(specification, expected_order):
    """Enumerate native closure using the original physical isotropy loops."""
    words = tuple(generator.turn_sequence
                  for generator in c.isotropy_loops(specification).generators)
    initial = c.State(specification)
    queue, known, states = deque((initial,)), {initial.hex_id}, []
    while queue:
        state = queue.popleft()
        assert state.shape == specification
        states.append(history_free(state))
        for word in words:
            following = state.apply(word)
            assert following.shape == specification
            if following.hex_id not in known:
                known.add(following.hex_id)
                queue.append(following)
        assert len(known) <= expected_order, "native closure exceeds certified ambient order"
    assert len(states) == expected_order
    assert len({state.sticker_permutation for state in states}) == expected_order
    return tuple(states)


def feature_satisfied(inventory, state, feature):
    handle = _resolve_feature(inventory, feature)
    return (_observation(inventory.action(state.sticker_permutation), handle, feature.kind) ==
            _observation(inventory.identity(), handle, feature.kind))


def portable_roundtrip(inner):
    record = inner.to_dict()
    with patch("subprocess.run", side_effect=AssertionError("portable validation must be offline")):
        loaded = type(inner).from_dict(json.loads(json.dumps(record)))
    assert loaded.to_dict() == record
    return loaded, {"format": record["format"], "offline_roundtrip": True,
                    "serialized_bytes": len(json.dumps(record, sort_keys=True)),
                    "fingerprint": record.get("fingerprint")}


def certified_stage(method, stage):
    return method.ambient_method._symbolic_chain.stages[
        method.prefix_stage_count + stage.number - 1]


def audit_coarse_application(method, application, initial):
    """Check even skipped stages, plus all earlier commitments at boundaries."""
    current, checks = initial, 0
    assert current.sticker_permutation in method.domain_group
    for stage in method.stages:
        certified = certified_stage(method, stage)
        assert current.sticker_permutation in certified.group_before
        for step in (step for step in application.steps if step.stage_number == stage.number):
            assert step.before == current
            current = current.apply(step.turn_sequence)
            assert current == step.after
            assert current.shape == method.reference_shape
            # During a procedural correction the current goal may still be
            # unfinished. The previous commitments must already be restored.
            assert current.sticker_permutation in certified.group_before
            checks += 1
        assert current.sticker_permutation in certified.group_after
        for preceding in method.stages[:stage.number]:
            assert feature_satisfied(method.inventory, current, preceding.feature)
            checks += 1
        checks += 1
    assert current == application.state
    assert initial.apply(application.turn_sequence) == current
    if application.status == "solved":
        assert current.is_solved
    return checks


def audit_root_application(inner, application, initial):
    if not hasattr(inner, "suffix"):
        return audit_coarse_application(inner, application, initial)
    current, checks = initial, 0
    for step in application.entry_steps:
        assert step.before == current
        current = current.apply(step.turn_sequence)
        assert current == step.after
        for feature in (*step.protected_features, step.feature):
            assert feature_satisfied(inner.inventory, current, feature)
            checks += 1
    if application.suffix_application is not None:
        checks += audit_coarse_application(inner.suffix, application.suffix_application, current)
        current = application.suffix_application.state
    assert current == application.state
    assert initial.apply(application.turn_sequence) == current
    return checks


def audit_shape_restoration(automatic, references):
    """Sample changed shapes while keeping their computational claim separate."""
    if not references:
        return [], 0
    initial = references[0]
    changing = next((move for move in initial.shape.legal_moves
                     if initial.apply(move).shape != automatic.reference_shape), None)
    if changing is None:
        return [], 0
    checks, records = 0, []
    selected = {state.hex_id: state for state in
                (references[0], references[len(references) // 2], references[-1])}
    for reference in selected.values():
        state = history_free(reference.apply(changing))
        assert state.shape != automatic.reference_shape
        application = automatic.apply(state)
        restored = state.apply(application.shape_turn_sequence)
        assert restored.shape == automatic.reference_shape
        checks += audit_root_application(automatic.inner_method, application.method_application, restored)
        assert application.status == "solved" and application.state.is_solved
        assert state.apply(application.turn_sequence) == application.state
        checks += 1
        records.append({"initial": state.hex_id, "shape_changed": True,
            "shape_restoration_htm": len(application.shape_turn_sequence.split()),
            "complete_physical_htm": len(application.turn_sequence.split()),
            "status": application.status, "human_shape_recognition_claim": False})
    return records, checks


def audit_all_stage_fibers(method, reference_states):
    """Check every complete observation fiber, independently of policy entry."""
    result, total_checks = [], 0
    algorithm_table = {algorithm.id: algorithm for algorithm in method.algorithms}
    operations = {algorithm.id: algorithm for algorithm in method.palette.recipes}
    saved = {(number, observation): path for number, observation, path in method.case_recipes}
    procedures = certified_procedure(method)
    for stage, procedure in zip(method.stages, procedures):
        certified = certified_stage(method, stage)
        inputs = tuple(state for state in reference_states
                       if state.sticker_permutation in certified.group_before)
        assert len(inputs) == certified.order_before
        fibers, htm_costs, qtm_costs, repetitions = Counter(), [], [], []
        case_table = {case.observation: case for case in stage.cases}
        for state in inputs:
            action = method.inventory.action(state.sticker_permutation)
            observed = _stage_observation(action, stage, method.inventory)
            fibers[observed] += 1
            assert observed in case_table
            case = case_table[observed]
            word = "" if case.algorithm_id is None else algorithm_table[case.algorithm_id].turn_sequence
            endpoint = state.apply(word)
            assert endpoint.shape == method.reference_shape
            assert endpoint.sticker_permutation in certified.group_after
            for preceding in method.stages[:stage.number]:
                assert feature_satisfied(method.inventory, endpoint, preceding.feature)
                total_checks += 1
            # Execute the displayed procedural instructions against native
            # states, observing again after every complete operation. Their
            # original-call expansion must equal the certified saved policy.
            current, calls, instruction_count, commanded_htm, commanded_qtm = state, [], 0, 0, 0
            while (pattern := _stage_observation(method.inventory.action(current.sticker_permutation),
                                                stage, method.inventory)) != stage.solved_observation:
                assert instruction_count < procedure.maximum_repetitions
                recipe = procedure.instruction_for(pattern)
                assert recipe
                physical = " ".join(operations[identifier].turn_sequence for identifier in recipe)
                commanded_htm += sum(operations[identifier].htm_length for identifier in recipe)
                commanded_qtm += sum(operations[identifier].qtm_length for identifier in recipe)
                current = current.apply(physical)
                assert current.shape == method.reference_shape
                assert current.sticker_permutation in certified.group_before
                for preceding in method.stages[:stage.number - 1]:
                    assert feature_satisfied(method.inventory, current, preceding.feature)
                    total_checks += 1
                calls.extend(expanded_recipe_path(method.palette, recipe))
                instruction_count += 1
                total_checks += 1
            assert tuple(calls) == expanded_recipe_path(method.palette, saved[stage.number, observed])
            assert current == endpoint
            position = procedure.observations.index(observed)
            assert commanded_htm == procedure.htm_costs[position]
            assert commanded_qtm == procedure.qtm_costs[position]
            repetitions.append(instruction_count)
            htm_costs.append(len(word.split()))
            qtm_costs.append(qtm(word))
            total_checks += 1
        assert set(fibers) == set(case_table), "recognition table has missing or unreachable patterns"
        assert len(fibers) == stage.case_count
        if stage.case_count == stage.index:
            assert set(fibers.values()) == {stage.order_after}
        result.append({"stage": stage.number, "goal": stage.feature.to_dict(),
            "order_before": str(stage.order_before), "order_after": str(stage.order_after),
            "observation_count": stage.case_count, "input_states": len(inputs),
            "conditional_rule_count": procedure.rule_count,
            "instruction_family_count": procedure.instruction_family_count,
            "maximum_instructions_per_case": procedure.maximum_repetitions,
            "native_procedural_instructions": metric(repetitions),
            "native_procedure_matches_saved_policy": True,
            "procedural_commanded_htm": metric(procedure.htm_costs),
            "procedural_commanded_qtm": metric(procedure.qtm_costs),
            "fiber_sizes": sorted(set(fibers.values())),
            "all_fibers_covered": True, "all_prior_commitments_preserved": True,
            "uniform_stage_input_htm": metric(htm_costs),
            "uniform_stage_input_qtm": metric(qtm_costs)})
    return result, total_checks


def stage_metadata(suffix):
    stages = [{"stage": stage.number, "goal": stage.feature.to_dict(),
               "order_before": str(stage.order_before), "order_after": str(stage.order_after),
               "observation_count": stage.case_count} for stage in suffix.stages]
    burden = {"stage_observation_counts": [stage.case_count for stage in suffix.stages],
              "total_observation_count": sum(stage.case_count for stage in suffix.stages),
              "largest_observation_count": max((stage.case_count for stage in suffix.stages), default=0),
              "nontrivial_correction_count": sum(case.algorithm_id is not None
                  for stage in suffix.stages for case in stage.cases)}
    procedures = certified_procedure(suffix)
    burden.update(stage_conditional_rule_counts=[procedure.rule_count for procedure in procedures],
        stage_instruction_family_counts=[procedure.instruction_family_count for procedure in procedures],
        total_instruction_family_count=sum(procedure.instruction_family_count for procedure in procedures),
        total_conditional_rule_count=sum(procedure.rule_count for procedure in procedures),
        stage_maximum_instruction_counts=[procedure.maximum_repetitions for procedure in procedures])
    return stages, burden


def procedural_additive_costs(suffix):
    procedures = certified_procedure(suffix)
    result = {"scope": "uniform_declared_domain_before_between_instruction_cancellation", "exact": True}
    for name in ("htm", "qtm"):
        means, worst = Fraction(), 0
        for procedure in procedures:
            values = getattr(procedure, name + "_costs")
            means += Fraction(sum(values), len(values))
            worst += max(values)
        result[name] = {"mean": float(means), "mean_numerator": means.numerator,
                        "mean_denominator": means.denominator, "worst": worst}
    return result


def audit_fixture(name, specification, *, root_limit=512):
    started = perf_counter()
    result = c.discover_method(specification, cache_dir=None)
    print(f"{name}: discovery {result.status} in {perf_counter() - started:.2f}s", flush=True)
    row = {"fixture": name, "discovery_status": result.status,
           "discovery_metadata": result.metadata, "discovery_seconds": perf_counter() - started}
    row["method_available"] = result.method is not None
    if result.method is None:
        row.update(input_count=0, solved_count=0, native_endpoint_checks=0,
                   execution_coverage_claim=False, total_seconds=perf_counter() - started)
        return row
    automatic, inner = result.method, result.method.inner_method
    loaded, row["portable_certificate"] = portable_roundtrip(inner)
    artifact = V2 / "research-results" / ("compact-" + name.lower().replace(" ", "-") + ".method.json")
    artifact.write_text(json.dumps(inner.to_dict(), sort_keys=True, separators=(",", ":"))+"\n",
                        encoding="utf-8")
    row["portable_certificate"]["artifact"] = str(artifact.relative_to(V2))
    suffix = inner.suffix if hasattr(inner, "suffix") else inner
    stages, recognition = stage_metadata(suffix)
    guide = inner.write_guide()
    row["guide"] = {"character_count": len(guide), "line_count": len(guide.splitlines()),
        "markdown_table_row_count": sum(line.startswith("| ") for line in guide.splitlines()),
        "has_block_action_column": "Block action" in guide,
        "has_structure_column": "Structure" in guide}
    taught = (inner.taught_definition_ids if hasattr(inner, "taught_definition_ids")
              else inner.taught_body_ids)
    assert len(taught) <= result.metadata["max_taught_bodies"]
    if taught:
        assert row["guide"]["has_block_action_column"]
        assert row["guide"]["has_structure_column"]
    row.update(stages=stages, recognition=recognition, learned_body_count=len(taught),
        taught_definition_ids=list(taught), reference_policy_coverage=suffix.coverage_scope,
        whole_shape_component_coverage=automatic.coverage_complete,
        whole_shape_component_human_method=automatic.human_method_complete,
        shape_restoration_human_recognition_claim=False,
        reference_additive_physical_costs=suffix.additive_costs(),
        procedural_additive_physical_costs=procedural_additive_costs(suffix))
    order = int(result.metadata["reference_group_order"])
    if order <= root_limit:
        references = native_reference_states(specification, order)
        inputs = references
        row.update(input_coverage="all_reference_shape_states", native_reference_state_count=len(references))
        row["stage_fibers"], stage_checks = audit_all_stage_fibers(suffix, references)
    else:
        # Exercise the certified ordinary suffix independently of bounded
        # constructive workspace entry, then include a few whole-cube inputs.
        examples = [suffix.example_state(stage.number, case.observation)
                    for stage in suffix.stages for case in stage.cases]
        sample_words = ("", "U", "R U R' U'", "F R U R' U' F'", "R2 U F2 D' L2 B")
        inputs = tuple({state.hex_id: history_free(state) for state in
                        (*examples, *(c.State(specification).apply(word) for word in sample_words))}.values())
        row.update(input_coverage="all_suffix_case_examples_plus_five_whole_cube_inputs",
                   native_reference_state_count=None, complete_whole_cube_entry_coverage_claim=False)
        stage_checks = 0
        references = ()
    applications, checks = [], stage_checks
    with patch("subprocess.run", side_effect=AssertionError("method application must be offline")):
        for state in inputs:
            application = loaded.apply(state)
            checks += audit_root_application(loaded, application, state)
            assert application.status == "solved", f"{name}: {state.hex_id}: {application.status}"
            assert application.state.is_solved
            applications.append({"initial": state.hex_id, "status": application.status,
                "physical_htm": len(application.turn_sequence.split()),
                "physical_qtm": qtm(application.turn_sequence)})
        row["computational_shape_restoration_samples"], shape_checks = audit_shape_restoration(
            automatic, references)
        checks += shape_checks
    row.update(input_count=len(inputs), solved_count=len(applications), native_endpoint_checks=checks,
        complete_physical_htm=metric(application["physical_htm"] for application in applications),
        complete_physical_qtm=metric(application["physical_qtm"] for application in applications),
        applications=applications, total_seconds=perf_counter() - started)
    print(f"{name}: solved {len(applications)}; observations "
          f"{recognition['stage_observation_counts']}; {len(taught)} taught bodies; "
          f"HTM mean {row['complete_physical_htm']['mean']:.2f}, "
          f"worst {row['complete_physical_htm']['worst']}", flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="append",
        choices=("Alcatraz", "Bicube Fuse", "Shark Fin Soup", "fused_U", "frozen", "unbandaged"),
        help="Repeat to choose fixtures; defaults to all six")
    parser.add_argument("--output", type=Path,
        default=V2 / "research-results" / "compact-automatic-methods.json")
    args = parser.parse_args()
    notebook_checks = check_minimal_notebooks()
    fixtures = {"Alcatraz": lambda: c.fixture("Alcatraz"),
                "Bicube Fuse": lambda: c.fixture("Bicube Fuse"),
                "Shark Fin Soup": lambda: c.fixture("Shark Fin Soup"),
                "fused_U": lambda: c.Shape([1] * 9 + [2] * 18),
                "frozen": lambda: c.Shape([1] * 27), "unbandaged": c.Shape}
    report = {"format": "bce-v2-compact-automatic-method-acceptance", "version": 1,
              "public_default_discovery_limits": True,
              "goals_stage_order_and_recipes_supplied_by_caller": False,
              "history_free_native_inputs": True, "notebooks": notebook_checks, "fixtures": []}
    started = perf_counter()
    try:
        for name in args.fixture or fixtures:
            report["fixtures"].append(audit_fixture(name, fixtures[name]()))
        assert check_minimal_notebooks() == notebook_checks, "notebook source changed during validation"
        report["all_checks_passed"] = True
        report["all_requested_methods_available"] = all(row["method_available"]
                                                        for row in report["fixtures"])
    finally:
        report["seconds"] = perf_counter() - started
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
