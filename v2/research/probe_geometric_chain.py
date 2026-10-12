#!/usr/bin/env python3
"""Compare certified chain continuations after geometrically compact prefixes.

Run with v2/.venv/bin/python. This diagnostic changes only the experimental
GAP feature chooser, while retaining production dictionary discovery,
Schreier refinement, exact stabilizer certificates and case compilation.
It does not modify production code or notebooks. Prefixes are ordinary cube
controls; no claim that these are optimized chains or Petrus methods is made.
"""

import argparse
import hashlib
from inspect import signature
import json
from pathlib import Path
from random import Random
from time import perf_counter

import bce_v2 as c
from bce_v2 import symbolic_chain_search as search


PREFIXES = {
    "greedy_control": (),
    "compact_2x2x2_prefix": ("UBR", "UB", "UR", "BR"),
    "adjacent_corners_prefix": ("UBR", "UFR", "UR", "UB", "UF"),
    "compact_then_corners": ("UBR", "UB", "UR", "BR", "UBL", "UFR", "UFL", "DBR", "DBL", "DFR"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] /
                        "research-results/geometric-chain-probe.json")
    parser.add_argument("--templates", action="store_true", help="Measure recipe compression as well")
    parser.add_argument("--prefix", choices=tuple(PREFIXES), action="append")
    parser.add_argument("--dictionary", type=Path, default=Path("/tmp/geometric-chain-dictionary.json"))
    parser.add_argument("--samples", type=int, default=32)
    args = parser.parse_args()
    record = dict(format="bce-v2-geometric-chain-diagnostic", version=1,
                  scope="same discovered dictionary, forced prefixes followed by bounded production adaptive chooser",
                  runtime_patch="experimental forced prefix in GAP chooser only", results=[])
    analysis = c.analyze_isotropy([0] * 27)
    started = perf_counter()
    if args.dictionary.exists():
        dictionary = c.SymbolicAlgorithmDictionary.from_dict(json.loads(args.dictionary.read_text()))
        dictionary.validate(inventory=analysis.block_inventory, generators=analysis.loops.generators)
        expected = {name: parameter.default for name, parameter in
                    signature(c.discover_symbolic_dictionary).parameters.items()
                    if name not in ("initial", "gap_executable", "timeout")}
        expected["max_setup_words"] = 384
        if dictionary.metadata["settings"] != expected:
            raise ValueError("cached dictionary has different discovery settings; use a fresh --dictionary path")
    else:
        dictionary = c.discover_symbolic_dictionary(analysis, max_setup_words=384)
        args.dictionary.write_text(json.dumps(dictionary.to_dict()))
    record.update(dictionary_seconds=perf_counter() - started,
                  dictionary_sha256=hashlib.sha256(args.dictionary.read_bytes()).hexdigest(),
                  dictionary_metadata=dictionary.metadata)
    print(json.dumps(dict(phase="dictionary", wall_seconds=record["dictionary_seconds"],
                          algorithms=len(dictionary.algorithms))), flush=True)
    settings = {**search._SEARCH_DEFAULTS, "max_states": 6000}
    record["policy_settings"] = settings
    record["adaptive_settings"] = dict(kind=1, preference="execution", max_expansions=64,
        beam_width=3, max_pool=4096, max_schreier=16000-len(dictionary.algorithms),
        max_htm_length=240, max_expanded_moves=960, gap_timeout=120)
    native_source = search._ADAPTIVE_PROGRAM
    blocks = analysis.block_inventory.blocks
    by_name = {block.name.split()[-1]: i for i, block in enumerate(blocks)}
    random = Random(3941)
    scrambles = [" ".join(random.choice("URFDLB") + random.choice(("", "'", "2"))
                          for _ in range(30)) for _ in range(args.samples)]
    for name in args.prefix or PREFIXES:
        prefix = PREFIXES[name]
        indices = [by_name[part] for part in prefix]
        injection = "" if not prefix else f"""
    if stageNumber < {len(indices)} then
        chosen := First(candidates, c -> c.kind = 1 and c.block = {json.dumps([i+1 for i in indices])}[stageNumber+1]);
        if chosen = fail then Error("forced geometric prefix is not available"); fi;
    fi;
"""
        search._ADAPTIVE_PROGRAM = native_source.replace("    BCEAdaptive.chosen := chosen;", injection + "    BCEAdaptive.chosen := chosen;")
        started = perf_counter()
        plan, pool, stats = search._adaptive_plan(analysis, dictionary.algorithms, kind=1,
            preference="execution", max_expansions=64, beam_width=3,
            max_schreier=16000-len(dictionary.algorithms), max_htm_length=240,
            max_expanded_moves=960, timeout=120)
        raw, method, policy = search._compile_dictionary_policy(plan, pool, settings)
        method.save(Path("/tmp") / ("geometric-chain-" + name + ".json"))
        algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
        stages = []
        for stage in method.stages:
            costs = [0 if case.algorithm_id is None else algorithms[case.algorithm_id].htm_length
                     for case in stage.cases]
            stages.append(dict(stage=stage.number, feature=stage.feature.kind, block=stage.block_name,
                               cases=len(costs), mean_htm=sum(costs)/len(costs), worst_htm=max(costs)))
        samples = []
        for word in scrambles:
            state = c.State.from_facelets(c.State(method.reference_shape).apply(word).facelets, method.reference_shape)
            result = method.apply(state)
            assert state.scramble is None and result.status == "solved" and result.state.is_solved
            assert state.apply(result.turn_sequence) == result.state
            samples.append(dict(scramble=word, htm=len(result.turn_sequence.split()), steps=len(result.steps)))
        row = dict(name=name, prefix=prefix, wall_seconds=perf_counter()-started,
                   additive_costs=method.additive_costs(), fallback_costs=raw.additive_costs(),
                   stages=stages, adaptive=stats, policy=policy, samples=samples,
                   sample_mean_htm=sum(s["htm"] for s in samples)/len(samples))
        if args.templates:
            repertoire = c.template_human_repertoire(method, preference="memory", backend="symbolic")
            row.update(template_metrics=repertoire.metadata["selected_metrics"],
                       learned_gt4_count=sum(m.algorithm.htm_length > 4 for m in repertoire.macros),
                       macro_words=[m.algorithm.turn_sequence for m in repertoire.macros])
        record["results"].append(row)
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({key: row[key] for key in ("name", "wall_seconds", "additive_costs", "sample_mean_htm")}), flush=True)
    search._ADAPTIVE_PROGRAM = native_source


if __name__ == "__main__":
    main()
