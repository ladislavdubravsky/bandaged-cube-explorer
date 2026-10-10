#!/usr/bin/env python3
"""Check the minimal ordinary-cube notebook's portable staged repertoire.

The record keeps experiments out of the notebook. Certificates prove complete
coverage; imported case examples and seeded scrambles independently check
execution. Physical sample costs include cancellation and are not group means.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
from random import Random
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_methods import _state_for_permutation


RESULTS = Path(__file__).resolve().parent.parent / "research-results"
PROBES = (
    ("solved", ""), ("R", "R"), ("B", "B"), ("R U", "R U"),
    ("commutator", "R U R' U'"), ("half turns", "R2 U2 F2"),
    ("twelve turns", "R U R' U' F2 D L2 B U2 R2 F' D'"),
    ("twenty-one turns", "R U2 F B R B2 R U2 L B2 R' U' D' R2 F R' L B2 U2 F2 D2"),
)


def _symbols(recipe):
    return int(recipe.kind != "sequence") + sum(_symbols(child) for child in recipe.children)


def _nodes(recipe):
    yield recipe
    for child in recipe.children:
        yield from _nodes(child)


def verify(repertoire):
    started = perf_counter()
    with patch("subprocess.run", side_effect=AssertionError("offline check invoked a subprocess")):
        restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
        if restored.to_dict() != repertoire.to_dict():
            raise ValueError("portable repertoire changed during offline reload")
        method = restored.method
        examples = 0
        for stage in method.stages:
            for case in stage.cases:
                state = _state_for_permutation(method.reference_shape, case.representative)
                result = restored.apply(state)
                if state.scramble is not None or result.status != "solved" or not result.state.is_solved:
                    raise ValueError("a history-free case example failed")
                if state.apply(result.turn_sequence) != result.state:
                    raise ValueError("case replay disagrees with staged application")
                examples += 1

        rng = Random(23)
        probes = list(PROBES) + [(f"seeded-{number + 1}", " ".join(
            rng.choice("URFDLB") + rng.choice(("", "'", "2")) for _ in range(25)))
            for number in range(24)]
        samples = []
        for label, word in probes:
            state = c.State.from_facelets(c.State(method.reference_shape).apply(word).facelets,
                                         method.reference_shape)
            result = restored.apply(state)
            if state.scramble is not None or result.status != "solved" or not result.state.is_solved:
                raise ValueError("a history-free imported scramble failed")
            if state.apply(result.turn_sequence) != result.state:
                raise ValueError("scramble replay disagrees with staged application")
            turns = result.turn_sequence.split()
            samples.append({"case": label, "scramble": word, "htm": len(turns),
                            "qtm": sum(2 if move.endswith("2") else 1 for move in turns),
                            "steps": len(result.steps), "replay_verified": True})

    recipes = [case.recipe for stage in restored.stages for case in stage.cases
               if case.instruction is not None]
    calls = Counter(node.macro_id for recipe in recipes for node in _nodes(recipe)
                    if node.kind == "macro")
    case_uses = Counter(identifier for recipe in recipes
                        for identifier in {node.macro_id for node in _nodes(recipe)
                                           if node.kind == "macro"})
    kinds = Counter(node.kind for recipe in recipes for node in _nodes(recipe))
    instructions = [case.instruction for stage in restored.stages for case in stage.cases
                    if case.instruction is not None]
    dictionary = restored.metadata.get("chunk_dictionary")
    chunks = c.ChunkDictionary.from_dict(dictionary) if dictionary else None
    from bce_v2.symbolic_template_repertoire import _human_symbols
    records = {macro.id: macro for macro in restored.macros}
    return {
        "offline_reload_verified": True, "offline_execution_verified": True,
        "verified_case_examples": examples, "verified_imported_scrambles": len(samples),
        "verification_seconds": perf_counter() - started,
        "samples": samples,
        "human_quality_proxies": {
            "macro_count": len(restored.macros),
            "macro_definition_htm": sum(m.algorithm.htm_length for m in restored.macros),
            "maximum_macro_htm": max((m.algorithm.htm_length for m in restored.macros), default=0),
            "instruction_symbols": sum(_human_symbols(recipe, records) for recipe in instructions),
            "maximum_instruction_symbols": max((_human_symbols(recipe, records) for recipe in instructions), default=0),
            "formal_recipe_symbols": sum(_symbols(recipe) for recipe in instructions),
            "rule_count": sum(len(stage.rules) for stage in restored.stages),
            "recipe_node_kinds": dict(sorted(kinds.items())),
            "macro_calls": dict(sorted(calls.items())),
            "macros_used_by_multiple_cases": sum(count > 1 for count in case_uses.values()),
            "chunk_count": len(chunks.chunks) if chunks else 0,
            "chunk_metrics": chunks.metrics if chunks else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--method", type=Path, help="compile templates from an existing symbolic method")
    source.add_argument("--repertoire", type=Path, help="evaluate an already generated repertoire")
    parser.add_argument("--preference", choices=("memory", "execution", "recognition"), default="memory")
    parser.add_argument("--output", type=Path, default=RESULTS / "unbandaged3x3-template-repertoire.json")
    parser.add_argument("--save-repertoire", type=Path)
    args = parser.parse_args()
    started = perf_counter()
    if args.repertoire:
        repertoire = c.load_human_repertoire(args.repertoire)
    else:
        initial = c.HumanMethod.from_dict(json.loads(args.method.read_text())) if args.method else [0] * 27
        repertoire = c.template_human_repertoire(initial, preference=args.preference, backend="symbolic")
    preparation_seconds = perf_counter() - started
    if repertoire.method.reference_shape != c.Shape([0] * 27):
        raise ValueError("repertoire belongs to another reference shape")
    checks = verify(repertoire)
    method = repertoire.method
    metadata = {key: value for key, value in repertoire.metadata.items()
                if key not in ("chunk_dictionary", "baseline_chunk_dictionary")}
    record = {
        "format": "bce-v2-symbolic-template-measurement", "version": 1,
        "pipeline": f"template_human_repertoire(analysis, preference={metadata['settings']['preference']!r}, backend='symbolic')",
        "measurement_source": "saved_repertoire" if args.repertoire else "saved_method" if args.method else "shape_input",
        "reference_shape": method.reference_shape.labels, "group_order": method.group_order,
        "coverage": method.coverage, "terminal_order": method.terminal_order,
        "stage_count": len(method.stages),
        "case_count": sum(stage.case_count for stage in method.stages),
        "maximum_stage_cases": max((stage.case_count for stage in method.stages), default=0),
        "preparation_seconds": preparation_seconds,
        "preparation_scope": "saved_repertoire_load" if args.repertoire else "template_compilation" if args.method else "dictionary_chain_and_template_preparation",
        "baseline_additive_costs": repertoire.baseline.additive_costs(),
        "selected_additive_costs": method.additive_costs(),
        "additive_cost_scope": "uniform_reference_group_before_stage_boundary_cancellation",
        "sample_cost_scope": "selected_and_seeded_imports_after_physical_simplification",
        "human_reviewed": False, "globally_shortest_claim": False,
        "metadata": metadata,
        "macro_definitions": [{"id": macro.id, "turn_sequence": macro.algorithm.turn_sequence,
                               "block_action": macro.algorithm.block_action.notation}
                              for macro in repertoire.macros], **checks,
    }
    if args.save_repertoire:
        repertoire.save(args.save_repertoire)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: record[key] for key in (
        "group_order", "stage_count", "case_count", "selected_additive_costs",
        "verified_case_examples", "verified_imported_scrambles", "human_quality_proxies")}, indent=2))


if __name__ == "__main__":
    main()
