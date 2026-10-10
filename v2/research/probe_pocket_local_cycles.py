#!/usr/bin/env python3
"""Compare one-tree root witnesses with loops extracted at every shape.

This is a geometric candidate-pool experiment, not an exhaustive cycle search
or an optimality claim. It leaves the solver and the existing human method
unchanged. Every retained root witness is replayed with the checked engine.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.loop_rotations import rotate_moves


BANDAGE = [
    1, 1, 2, 1, 1, 2, 3, 3, 0,
    0, 0, 4, 0, 0, 4, 5, 5, 6,
    0, 0, 4, 0, 0, 4, 5, 5, 6,
]
IDENTITY = tuple(range(48))


def inverse(permutation):
    result = [0] * len(permutation)
    for source, target in enumerate(permutation):
        result[target] = source
    return tuple(result)


def then(first, second):
    return tuple(second[point] for point in first)


def inverse_moves(moves):
    return tuple(move if move.endswith("2") else move[:-1] if move.endswith("'")
                 else move + "'" for move in reversed(moves))


def costs(word):
    moves = word.split()
    return len(moves), sum(2 if move.endswith("2") else 1 for move in moves)


def core_record(generator, loops):
    """Expose the common setup around a tree-based fundamental cycle."""
    source = loops.transport(generator.source).split()
    target = loops.transport(generator.target).split()
    prefix = 0
    while prefix < min(len(source), len(target)) and source[prefix] == target[prefix]:
        prefix += 1
    expanded = generator.moves.split()
    core = expanded[prefix:len(expanded) - prefix] if prefix else expanded
    return {
        "setup": _simplified_moves(source[:prefix]),
        "local_cycle": _simplified_moves(core),
        "setup_htm": costs(_simplified_moves(source[:prefix]))[0],
        "cycle_htm": costs(_simplified_moves(core))[0],
    }


def shared_chunk_grammar(loops):
    """Verify a common open-path dictionary for the current three masters."""
    chunks = {"K": "F' U L F U'", "P": "U F' L' F U'", "J": "R' F D' F' R"}
    rotation = "x y"
    transferred = rotate_moves(chunks["K"], rotation)
    setup = (*chunks["P"].split(), "U'", "R")
    expansions = {
        477: (*chunks["K"].split(), *transferred.split(), *chunks["J"].split()),
        597: (*chunks["P"].split(), *chunks["K"].split(), *transferred.split()),
        352: (*setup, "B2", *inverse_moves(setup)),
    }
    by_id = {generator.id: generator for generator in loops}
    for identifier, expansion in expansions.items():
        if _simplified_moves(expansion) != by_id[identifier].turn_sequence:
            raise ValueError("shared chunk grammar does not reproduce the native word")
    return {
        "chunks": chunks,
        "rotation": rotation,
        "formulas": {"477": "K rotate(rho, K) J", "597": "P K rotate(rho, K)",
                     "352": "(P U' R) B2 (P U' R)^-1"},
        "expansions_checked_against_native_words": len(expansions),
        "chunk_endpoints": "open paths; these are not independent reference loops",
        "human_memory_claim": False,
    }


def probe():
    reference = c.State(BANDAGE)
    graph = c.explore(reference.shape, metric="QTM")
    analysis = c.analyze_isotropy(graph)
    loops = analysis.loops
    best = {}
    local_costs = Counter()
    one_turn_cycles = []
    for vertex in range(len(graph)):
        setup = tuple(loops.transport(vertex).split())
        setup_action = reference.apply(" ".join(setup)).sticker_permutation
        local_loops = c.isotropy_loops(graph, root=vertex)
        for local in local_loops:
            local_word = local.turn_sequence
            local_costs[costs(local_word)[0]] += 1
            if costs(local_word)[0] == 1:
                one_turn_cycles.append({"vertex": vertex, "word": local_word})
            permutation = then(then(setup_action, local.permutation), inverse(setup_action))
            if permutation == IDENTITY:
                raise ValueError("nonidentity local action became an identity after transport")
            key = min(permutation, inverse(permutation))
            # Orient the word to agree with the inverse-class canonical action.
            body = tuple(local_word.split())
            if permutation != key:
                body = inverse_moves(body)
            word = _simplified_moves((*setup, *body, *inverse_moves(setup)))
            score = (*costs(word), word)
            previous = best.get(key)
            if previous is None or score < previous[0]:
                best[key] = score, {
                    "permutation": list(key),
                    "htm_length": score[0], "qtm_length": score[1],
                    "turn_sequence": word,
                    "base_vertex": vertex,
                    "setup": " ".join(setup),
                    "local_cycle": " ".join(body),
                    "local_cycle_htm": len(body),
                    "source_loop_id": local.id,
                }

    records = [record for _, record in sorted(best.values(), key=lambda pair: pair[0])]
    inventory = analysis.block_inventory
    for record in records:
        replay = reference.apply(record["turn_sequence"])
        if replay.shape != reference.shape or tuple(replay.sticker_permutation) != tuple(record["permutation"]):
            raise ValueError("retained root witness fails checked replay")
        record["block_action"] = inventory.action(record["permutation"]).notation

    original_comparisons = []
    for generator in loops:
        key = min(generator.permutation, inverse(generator.permutation))
        retained = best[key][1]
        original_comparisons.append({
            "id": generator.id,
            "native_htm": generator.htm_length,
            "native_qtm": costs(generator.turn_sequence)[1],
            "native_turn_sequence": generator.turn_sequence,
            "best_lifted_htm": retained["htm_length"],
            "best_lifted_qtm": retained["qtm_length"],
            "tree_cycle_decomposition": core_record(generator, loops),
        })

    rotations = Counter(shape.rotation_key for shape in graph)
    return {
        "format": "bce-v2-pocket-local-cycle-probe", "version": 1,
        "reference_shape": BANDAGE,
        "model": "full-grid-27-fixed-centers",
        "scope": "BandagedPocketCube notebook reference shape",
        "search": "one QTM breadth-first spanning tree at each of the 580 shape roots",
        "transport": "original reference-root shortest QTM tree path",
        "deduplication": "faithful 48-sticker action modulo inverse",
        "ranking": "simplified HTM, simplified QTM, canonical oriented face word",
        "optimality_claim": False,
        "summary": {
            "shape_count": len(graph), "clockwise_arc_count": loops.arc_count,
            "fundamental_cycle_count": loops.candidate_count,
            "native_nonidentity_count": loops.nonidentity_count,
            "native_inverse_action_count": len(loops),
            "group_order": analysis.group_order,
            "reduced_generator_ids": list(analysis.generator_ids),
            "nonidentity_root_symmetries": list(c.bandage_symmetries(reference.shape)),
            "local_rooted_witness_count": sum(local_costs.values()),
            "local_one_htm_cycle_count": len(one_turn_cycles),
            "lifted_inverse_action_count": len(records),
            "existing_native_actions_shortened": sum(
                record["best_lifted_htm"] < record["native_htm"] for record in original_comparisons),
            "rotation_classes_intersecting_component": len(rotations),
            "rotation_class_intersection_sizes": {
                str(size): count for size, count in sorted(Counter(rotations.values()).items())
            },
            "retained_witnesses_legally_replayed": len(records),
        },
        "local_witness_htm_histogram": {
            str(length): count for length, count in sorted(local_costs.items())
        },
        "local_one_turn_cycles": one_turn_cycles,
        "original_loop_comparisons": original_comparisons,
        "shared_chunk_grammar": shared_chunk_grammar(loops),
        "lifted_actions": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.write_text(encoded, encoding="utf-8")
        print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
