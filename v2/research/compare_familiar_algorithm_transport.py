#!/usr/bin/env python3
"""Compare production fixed-chain policies with familiar transport off/on.

Native mining and stage-search limits are identical. The familiar source uses
finite work bounds without a wall-clock cutoff for reproducibility. Notebook
bandages are read as literal assignments; no notebook cells are executed.
"""

import argparse
import json
from pathlib import Path
from time import perf_counter

import bce_v2 as c

from profile_symbolic_basis import bandage_from_notebook


def literal_words(expression):
    if expression.kind == "turns":
        return {expression.moves}
    return set().union(*(literal_words(child) for child in expression.children))


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", choices=("FourPair", "BeltRoad", "MostSignaturesCube"),
                        default="FourPair")
    parser.add_argument("--output", type=Path,
                        default=base / "research-results/familiar-algorithm-transport-production.json")
    args = parser.parse_args()
    analysis = c.analyze_isotropy(
        bandage_from_notebook(base / "examples" / "stabilizer-chain-methods" / (args.puzzle + ".ipynb")), timeout=30)
    baseline = c.synthesize_human_method(analysis, backend="symbolic", timeout=30)
    dictionary_settings = dict(max_candidates=256, rounds=1, max_seed_loops=8,
                               max_algorithms=256, max_setup_words=8, max_conjugates=64,
                               max_familiar_seconds=None, timeout=30)
    improvement_settings = dict(max_candidates=512, max_states=256, max_word_length=3,
                                rounds=1, max_seed_loops=8, max_stage_generators=16,
                                max_alternatives=2, max_htm_length=80,
                                max_expanded_moves=400)
    comparison = {}
    for name, enabled in (("native_control", False), ("familiar_enabled", True)):
        started = perf_counter()
        dictionary = c.discover_symbolic_dictionary(
            analysis, **dictionary_settings, max_familiar_candidates=128 if enabled else 0)
        search = c.improve_human_method(baseline, dictionary=dictionary, **improvement_settings)
        familiar = dictionary.metadata["familiar_transport"]
        source_words = {record["conjugate"] for record in familiar["algorithms"].values()}
        words_by_algorithm = {algorithm.id: literal_words(algorithm.expression) & source_words
                              for algorithm in search.method.algorithms}
        used_words = set().union(*words_by_algorithm.values())
        comparison[name] = dict(
            elapsed_seconds=perf_counter() - started,
            group_order=search.method.group_order,
            native_generator_count=len(search.method.generators),
            terminal_order=search.method._symbolic_chain.terminal_order,
            coverage=search.method.coverage, costs=search.method.additive_costs(),
            dictionary_algorithms=len(dictionary.algorithms),
            familiar_dictionary_literals=len(familiar["dictionary_algorithm_ids"]),
            selected_cases_with_familiar_literals=sum(
                bool(words_by_algorithm.get(case.algorithm_id))
                for stage in search.method.stages for case in stage.cases),
            selected_algorithms_with_familiar_literals=sum(map(bool, words_by_algorithm.values())),
            selected_distinct_familiar_literals=len(used_words),
            selected_familiar_words=sorted(used_words),
            changed_cases=sum(stage["changed_cases"] for stage in search.metadata["stages"]),
            candidates_examined=search.metadata["candidates_examined"],
            states_expanded=search.metadata["states_expanded"])
        print(name, comparison[name]["costs"]["htm"], flush=True)
    record = dict(
        format="bce-v2-familiar-transport-production-comparison", version=1,
        puzzle=args.puzzle, strategy=baseline.strategy, baseline_costs=baseline.additive_costs(),
        dictionary_settings=dictionary_settings, improvement_settings=improvement_settings,
        comparison=comparison, full_scan=False, runtime_patches=False,
        discovery_scope="Bounded production nearby-shape scan; one shortest HTM setup per shape",
        caveat="Bounded repertoire and fixed chain; aggregate additive costs before stage-boundary cancellation.")
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
