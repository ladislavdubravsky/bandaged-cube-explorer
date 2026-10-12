#!/usr/bin/env python3
"""Compare production chain selection with anonymous target discovery enabled.

Both searches use the same witnessed dictionary and complete controls. The
record separates exact additive costs, sampled physical costs and the final
template body count. It makes no claim of a hard learned-body budget.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from time import perf_counter

import bce_v2 as c


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=Path("/tmp/geometric-chain-dictionary.json"))
    parser.add_argument("--output", type=Path,
                        default=base / "research-results/algorithm-informed-stage-implementation.json")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--reuse-control", type=Path,
                        help="reuse a measured control with identical dictionary, settings and samples")
    args = parser.parse_args()
    if args.samples < 1:
        raise ValueError("samples must be positive")
    analysis = c.analyze_isotropy(c.Shape())
    if args.dictionary.exists():
        dictionary = c.SymbolicAlgorithmDictionary.from_dict(json.loads(args.dictionary.read_text()))
        dictionary.validate(inventory=analysis.block_inventory, generators=analysis.loops.generators)
    else:
        dictionary = c.discover_symbolic_dictionary(analysis, max_setup_words=384)
        args.dictionary.write_text(json.dumps(dictionary.to_dict()))
    random = Random(3941)
    words = [" ".join(random.choice("URFDLB") + random.choice(("", "'", "2"))
                      for _ in range(30)) for _ in range(args.samples)]
    options = dict(backend="symbolic", strategy="fully_solve_each_block", dictionary=dictionary,
                   beam_width=3, max_expansions=64, max_methods=4,
                   discovery_options={"max_states":6000}, timeout=120)
    record = {"format":"bce-v2-algorithm-informed-stage-implementation", "version":1,
              "reference":"Unbandaged3x3", "dictionary_sha256":sha256(args.dictionary.read_bytes()).hexdigest(),
              "dictionary_algorithm_count":len(dictionary.algorithms),
              "search_options":{key:value for key,value in options.items() if key != "dictionary"},
              "scope":"same dictionary and controls; bounded automatic orientation proposals",
              "hard_learned_body_limit":False, "results":[]}
    prior = json.loads(args.reuse_control.read_text()) if args.reuse_control else None
    if prior is not None:
        if any(prior[key] != record[key] for key in (
                "format", "version", "dictionary_sha256", "search_options")):
            raise ValueError("reused control has different preparation inputs")
        control = next(row for row in prior["results"] if row["name"] == "control")
        if [sample["scramble"] for sample in control["samples"]] != words:
            raise ValueError("reused control has different samples")
    for name, target_options in (("control", {"max_methods":0}), ("orientation_targets", None)):
        if name == "control" and prior is not None:
            record["results"].append({**control, "reused_measurement":True})
            continue
        started = perf_counter()
        search = c.select_human_chain(analysis, target_options=target_options, **options)
        method = search.method
        method.save(Path("/tmp") / ("algorithm-informed-" + name + ".json"))
        candidates = [{"source":candidate.source, "mean_htm":candidate.metrics["mean_htm"],
                       "worst_htm":candidate.metrics["worst_htm"],
                       "orientation_stage_count":sum(stage.feature.kind == "orient_slots"
                                                     for stage in candidate.method.stages)}
                      for candidate in search.candidates]
        repertoire = c.template_human_repertoire(method, backend="symbolic", preference="memory")
        # Independently reload both artifacts before testing imported states.
        loaded = c.HumanMethod.from_dict(method.to_dict())
        loaded_repertoire = c.HumanRepertoire.from_dict(repertoire.to_dict())
        samples = []
        for word in words:
            source = c.State.from_facelets(c.State(method.reference_shape).apply(word).facelets,
                                         method.reference_shape)
            if source.scramble is not None:
                raise AssertionError("sample retained move history")
            result = loaded.apply(source)
            guided = loaded_repertoire.apply(source)
            if (not result.state.is_solved or not guided.state.is_solved
                    or source.apply(result.turn_sequence) != result.state
                    or source.apply(guided.turn_sequence) != guided.state):
                raise AssertionError("complete method or repertoire failed physical replay")
            samples.append({"scramble":word, "htm":len(result.turn_sequence.split()),
                            "repertoire_htm":len(guided.turn_sequence.split())})
        row = {"name":name,"wall_seconds":perf_counter()-started,
               "selected_source":search.metadata["selected_source"],
               "additive_costs":method.additive_costs(), "candidates":candidates,
               "attribute_targets":search.metadata["attribute_targets"],
               "attribute_prefixes_evaluated":search.metadata["attribute_prefixes_evaluated"],
               "learned_long_body_count":sum(macro.algorithm.htm_length > 4 for macro in repertoire.macros),
               "macro_count":len(repertoire.macros),
               "sample_mean_htm":sum(sample["htm"] for sample in samples)/len(samples),
               "samples":samples,"all_method_and_repertoire_replays_passed":True}
        record["results"].append(row)
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({key:row[key] for key in (
            "name","wall_seconds","selected_source","learned_long_body_count","sample_mean_htm")},
                         sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
