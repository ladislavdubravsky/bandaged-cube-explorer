#!/usr/bin/env python3
"""Exercise the one-call method API on genuinely fused, changing bandages.

Every input is imported from native colored cubies without a scramble witness.
The fixture words are used only to create independently replayable inputs.
No ordinary-cube algorithms, seeded goals, or notebook planner settings are
passed to discovery. Tiny state spaces are exhaustively tested; the larger
Alcatraz experiment is explicitly a sample of its colored state space.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import random
from time import perf_counter

import bce_v2 as c
from bce_v2.human_chains import _observation, _resolve_feature


V2 = Path(__file__).resolve().parents[1]
ORIGINAL_NOTEBOOK = V2 / "examples" / "stabilizer-chain-methods" / "Unbandaged3x3.ipynb"
# The original stabilizer notebook is restored byte-for-byte from repository HEAD.
ORIGINAL_NOTEBOOK_SHA256 = "436f0fd4f3b33002d373f2bcee450c4f470adf87ff162c00dac6d6517e1f03d9"


def history_free(state):
    imported = c.State.from_cubies(state.specification, corners=state.corners,
        twists=state.twists, edges=state.edges, flips=state.flips)
    assert imported == state and imported.scramble is None
    return imported


def native_states(specification):
    """Exhaustive native BFS, reserved for the one/four-state tiny fixtures."""
    initial = c.State(specification)
    queue, known, result = deque((initial,)), {initial.hex_id}, []
    while queue:
        state = queue.popleft()
        result.append(history_free(state))
        for move in state.shape.legal_moves:
            following = state.apply(move)
            if following.hex_id not in known:
                known.add(following.hex_id)
                queue.append(following)
    return tuple(result)


def legal_scramble_samples(specification, *, count=12, length=20, seed=20261012):
    """Recompute legal choices at every changing physical bandage shape."""
    rng = random.Random(seed)
    result = [("F R2", history_free(c.State(specification).apply("F R2")))]
    for _ in range(count):
        state, words, previous = c.State(specification), [], None
        for _ in range(length):
            faces = [move for move in state.shape.legal_moves if len(move) == 1]
            choices = [face for face in faces if face != previous] or faces
            if not choices:
                break
            previous = rng.choice(choices)
            word = previous + rng.choice(("", "2", "'"))
            state = state.apply(word)
            words.append(word)
        result.append((" ".join(words), history_free(state)))
    return tuple(result)


def feature_satisfied(inventory, state, feature):
    block = _resolve_feature(inventory, feature)
    action = inventory.action(state.sticker_permutation)
    return (_observation(action, block, feature.kind) ==
            _observation(inventory.identity(), block, feature.kind))


def audit_root_application(method, application, initial):
    """Replay an inner complete policy or bounded workspace policy directly."""
    current, checks = initial, 0
    if hasattr(method, "suffix"):
        suffix = method.suffix
        inventory = suffix.inventory
        for step in application.entry_steps:
            assert step.before == current
            current = current.apply(step.turn_sequence)
            assert current == step.after
            for feature in (*step.protected_features, step.feature):
                assert feature_satisfied(inventory, current, feature)
                checks += 1
        if application.suffix_application is not None:
            for feature in suffix.domain_features:
                assert feature_satisfied(inventory, current, feature)
                checks += 1
            current, suffix_checks = audit_root_application(
                suffix, application.suffix_application, current)
            checks += suffix_checks
    else:
        # Repertoire stages may need repeated corrections. Their inner
        # HumanMethod supplies the promised features and exact block inventory.
        actual = method.method if hasattr(method, "method") else method
        inventory, stages = actual.inventory, actual.stages
        features = tuple(getattr(actual, "domain_features", ()))
        for feature in features:
            assert feature_satisfied(inventory, current, feature)
            checks += 1
        for step in application.steps:
            assert step.before == current
            current = current.apply(step.turn_sequence)
            assert current == step.after
            done = (*features, *(stage.feature for stage in stages
                if stage.number < step.stage_number or
                (stage.number == step.stage_number and getattr(step, "rank_after", 0) == 0)))
            for feature in done:
                assert feature_satisfied(inventory, current, feature)
                checks += 1
    assert current == application.state
    assert initial.apply(application.turn_sequence) == application.state
    if application.status == "solved":
        assert application.state.is_solved
    return current, checks


def original_notebook_unchanged():
    actual = hashlib.sha256(ORIGINAL_NOTEBOOK.read_bytes()).hexdigest()
    if actual != ORIGINAL_NOTEBOOK_SHA256:
        raise AssertionError("the original Unbandaged3x3 notebook changed during this task")
    return actual


def native_root_states(specification, expected_order):
    """Enumerate a small reference fiber using independent native loop words."""
    loops = c.isotropy_loops(specification)
    words = tuple(generator.turn_sequence for generator in loops.generators)
    initial = c.State(specification)
    queue, known, result = deque((initial,)), {initial.hex_id}, []
    while queue:
        state = queue.popleft()
        assert state.shape == initial.specification
        result.append(history_free(state))
        for word in words:
            following = state.apply(word)
            assert following.shape == initial.specification
            if following.hex_id not in known:
                known.add(following.hex_id)
                queue.append(following)
        if len(known) > expected_order:
            raise AssertionError("native reference closure exceeded its expected fixture order")
    assert len(result) == expected_order
    return tuple(result)


def audit_application(method, application, initial):
    assert initial.scramble is None
    restored = initial.apply(application.shape_turn_sequence)
    checks = 0
    if application.method_application is not None:
        assert restored.shape == method.reference_shape
        checks += 1
        final, root_checks = audit_root_application(
            method.inner_method, application.method_application, restored)
        assert final == application.state
        checks += root_checks
    else:
        assert restored == application.state
    assert initial.apply(application.turn_sequence) == application.state
    assert application.htm_length == len(application.turn_sequence.split())
    if application.status == "solved":
        assert application.state.is_solved
    return {
        "status": application.status,
        "reason": application.reason,
        "input_shape_changed": initial.shape != method.reference_shape,
        "input_hex_id": initial.hex_id,
        "shape_turn_sequence": application.shape_turn_sequence,
        "turn_sequence": application.turn_sequence,
        "physical_htm": application.htm_length,
        "native_endpoint_checks": checks,
    }


def replay_fixture(name, specification, inputs, *, coverage_scope):
    started = perf_counter()
    discovered = c.discover_method(specification)
    print(f"{name}: discovery {discovered.status}", flush=True)
    record = {
        "name": name,
        "discovery_status": discovered.status,
        "discovery_metadata": dict(discovered.metadata),
        "input_coverage_scope": coverage_scope,
        "discovery_seconds": perf_counter() - started,
        "fixtures": [],
    }
    if discovered.method is None:
        record.update(attempted_count=len(inputs), solved_count=0,
                      unavailable_method=True)
        return record
    method = discovered.method
    inner = method.inner_method
    taught = tuple(inner.taught_definition_ids if hasattr(inner, "taught_definition_ids")
                   else inner.taught_body_ids)
    assert len(taught) <= 7
    record.update(method_coverage_scope=method.coverage_scope,
                  coverage_complete=method.coverage_complete,
                  human_method_complete=method.human_method_complete,
                  actual_taught_definition_ids=list(taught))
    for label, state in inputs:
        application = method.apply(state)
        row = audit_application(method, application, state)
        row["fixture_label"] = label
        record["fixtures"].append(row)
    counts = Counter(row["status"] for row in record["fixtures"])
    solved = [row for row in record["fixtures"] if row["status"] == "solved"]
    record.update(attempted_count=len(record["fixtures"]),
        solved_count=len(solved), status_counts=dict(counts),
        changed_shape_count=sum(row["input_shape_changed"] for row in record["fixtures"]),
        native_endpoint_checks=sum(row["native_endpoint_checks"] for row in record["fixtures"]),
        mean_physical_htm_over_solved=(sum(row["physical_htm"] for row in solved) / len(solved)
                                      if solved else None),
        total_seconds=perf_counter() - started)
    print(f"{name}: solved {len(solved)}/{len(inputs)}; "
          f"{record['changed_shape_count']} changed shapes", flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
        default=V2 / "research-results" / "automatic-bandage-method.json")
    args = parser.parse_args()
    original_hash = original_notebook_unchanged()
    started = perf_counter()
    frozen, fused = c.Shape([1] * 27), c.Shape([1] * 9 + [2] * 18)
    frozen_inputs = tuple((state.hex_id, state) for state in native_states(frozen))
    fused_inputs = tuple((state.hex_id, state) for state in native_states(fused))
    assert len(frozen_inputs) == 1 and len(fused_inputs) == 4
    records = [
        replay_fixture("frozen", frozen, frozen_inputs,
                       coverage_scope="all_one_reachable_colored_state"),
        replay_fixture("fused_U", fused, fused_inputs,
                       coverage_scope="all_four_reachable_colored_states"),
    ]
    for name, specification, order, total in (
        ("Alcatraz", c.fixture("Alcatraz"), 324, 469_476),
        ("BicubeFuse", c.fixture("Bicube Fuse"), 60, 7_260),
    ):
        root_states = native_root_states(specification, order)
        shifted = tuple((f"nonreference_fiber_{number}", history_free(state.apply("F R2")))
                        for number, state in enumerate(root_states))
        assert len({state.hex_id for _, state in shifted}) == order
        assert all(state.shape != specification for _, state in shifted)
        inputs = (*shifted, *legal_scramble_samples(specification))
        records.append(replay_fixture(name, specification, inputs,
            coverage_scope=f"all_{order}_states_at_one_nonreference_shape_plus_13_legal_walk_samples"))
        records[-1].update(native_reference_closure_count=order,
                           native_nonreference_fiber_count=order,
                           whole_colored_state_count=total,
                           whole_colored_state_space_exhaustively_replayed=False)
    report = {
        "format": "bce-v2-automatic-bandage-method-acceptance", "version": 1,
        "user_supplied_planning_options": False,
        "user_supplied_algorithm_palette": False,
        "history_free_native_inputs": True,
        "original_notebook_unchanged": original_notebook_unchanged() == original_hash,
        "original_notebook_sha256": original_hash,
        "fixtures": records,
        "all_tested_inputs_solved": all(record["solved_count"] == record["attempted_count"]
                                       for record in records),
        "native_endpoint_checks": sum(record.get("native_endpoint_checks", 0)
                                       for record in records),
        "seconds": perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "fixtures"},
                     indent=2), flush=True)


if __name__ == "__main__":
    main()
