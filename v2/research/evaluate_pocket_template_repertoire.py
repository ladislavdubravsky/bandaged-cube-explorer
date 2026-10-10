#!/usr/bin/env python3
"""Measure the implemented template compiler against the previous notebook.

Every policy is independently loaded and legally replayed on all 432 imported
reference states. Use --repertoire to evaluate an already generated artifact;
otherwise this runs the public constructor with the notebook defaults.
"""

import argparse
import json
from pathlib import Path

import bce_v2 as c
from bce_v2.human_methods import _state_for_permutation


BANDAGE = [1, 1, 2, 1, 1, 2, 3, 3, 0,
           0, 0, 4, 0, 0, 4, 5, 5, 6,
           0, 0, 4, 0, 0, 4, 5, 5, 6]
RESULTS = Path(__file__).resolve().parent.parent / "research-results"


def verify(repertoire):
    restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
    if restored.to_json() != repertoire.to_json():
        raise ValueError("portable repertoire does not round-trip exactly")
    total_htm = total_qtm = worst_htm = worst_qtm = 0
    for permutation in sorted(restored.method._permutations):
        state = _state_for_permutation(restored.method.reference_shape, permutation)
        result = restored.apply(state)
        if state.scramble is not None or not result.state.is_solved:
            raise ValueError("policy failed an imported reference state")
        if state.apply(result.turn_sequence) != result.state:
            raise ValueError("physical replay disagrees with policy application")
        turns = result.turn_sequence.split()
        htm = len(turns)
        qtm = sum(2 if move.endswith("2") else 1 for move in turns)
        total_htm += htm
        total_qtm += qtm
        worst_htm = max(worst_htm, htm)
        worst_qtm = max(worst_qtm, qtm)
    order = restored.method.group_order
    return {"verified_states": order, "macro_count": len(restored.macros),
            "definition_htm": sum(m.algorithm.htm_length for m in restored.macros),
            "total_htm": total_htm, "mean_htm": total_htm / order,
            "worst_htm": worst_htm, "total_qtm": total_qtm,
            "mean_qtm": total_qtm / order, "worst_qtm": worst_qtm,
            "stage_indices": [stage.index for stage in restored.method.stages]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repertoire", type=Path)
    parser.add_argument("--output", type=Path, default=RESULTS / "pocket-template-comparison.json")
    parser.add_argument("--save-repertoire", type=Path,
                        default=RESULTS / "pocket-template-repertoire.json")
    args = parser.parse_args()
    analysis = c.analyze_isotropy(BANDAGE)
    selected = c.select_human_chain(analysis)
    previous = c.generator_human_repertoire(selected.method)
    templates = (c.load_human_repertoire(args.repertoire) if args.repertoire else
                 c.template_human_repertoire(analysis))
    if templates.method.reference_shape != c.Shape(BANDAGE):
        raise ValueError("repertoire belongs to another reference shape")
    before, after = verify(previous), verify(templates)
    for key in ("total_htm", "mean_htm", "worst_htm", "total_qtm", "mean_qtm", "worst_qtm"):
        if after[key] != templates.metadata["selected_metrics"][key]:
            raise ValueError(f"saved selected metric disagrees with replay: {key}")
    dictionary = c.ChunkDictionary.from_dict(templates.metadata["chunk_dictionary"])
    record = {
        "shape_count": analysis.loops.shape_count,
        "group_order": analysis.group_order,
        "colored_state_count": analysis.colored_state_count,
        "previous_pipeline": "generator_human_repertoire(select_human_chain(analysis).method)",
        "implemented_pipeline": "template_human_repertoire(analysis)",
        "previous": before, "implemented": after,
        "mean_htm_reduction_percent": 100 * (before["mean_htm"] - after["mean_htm"]) / before["mean_htm"],
        "worst_htm_reduction_percent": 100 * (before["worst_htm"] - after["worst_htm"]) / before["worst_htm"],
        "chunks": [{"id": chunk.id, "moves": chunk.moves, "kind": chunk.kind}
                   for chunk in dictionary.chunks],
        "formulas": dictionary.master_formulas,
        "dictionary_metrics": dictionary.metrics,
        "local_loops": [{"master_id": item["master_id"],
                         "setup": item["setup"].moves, "body": item["body"].moves}
                        for item in dictionary.local_loops],
        "settings": templates.metadata["settings"],
        "search": templates.metadata["search"],
        "selected_id": templates.metadata["selected_id"],
        "frontier": templates.metadata["frontier"],
        "global_shortest_claim": False, "human_reviewed": False,
    }
    templates.save(args.save_repertoire)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"previous": before, "implemented": after,
                      "chunks": record["chunks"], "formulas": record["formulas"]}, indent=2))


if __name__ == "__main__":
    main()
