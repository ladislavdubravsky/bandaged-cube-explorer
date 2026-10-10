#!/usr/bin/env python3
"""Bounded shape-wide familiar-algorithm discovery, without solver mutation.

Run with v2/.venv/bin/python. The complete native QTM graph is converted to
18 HTM transitions. Catalog words are composed across all vertices with NumPy
gathers. Both legal execution and exact shape closure are required. A single
HTM breadth-first tree supplies shortest setup paths; only a bounded shortlist
is materialized and independently checked with ShapePath and colored replay.

This measures candidate discovery, not a compiled staged solution or its
quality. It deliberately performs no per-hit GAP factorization.
"""

import argparse
from collections import Counter, deque
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import bce_v2 as c

from familiar_algorithm_catalog import build, inverse, verify_adjacent_commutator_coverage
from profile_notebook_graph import notebook_bandage


MOVES = tuple(face + suffix for face in "URFDLB" for suffix in ("", "'", "2"))


def transitions(graph):
    """Add inverse arcs and compose half turns; last vertex is failure sentinel."""
    count = len(graph)
    actions = {move: np.full(count + 1, count, dtype=np.int32) for move in MOVES}
    for source, target, move in graph.arcs:
        actions[move][source] = target
        actions[inverse(move)][target] = source
    for face in "URFDLB":
        actions[face + "2"] = actions[face][actions[face]]
    return actions


def setup_tree(actions, count):
    """One BFS with fixed tie breaking, counting a half turn as one HTM."""
    matrix = np.stack([actions[move] for move in MOVES], axis=1)
    parent = np.full(count, -1, dtype=np.int32)
    parent_move = np.full(count, -1, dtype=np.int8)
    distances = np.full(count, -1, dtype=np.int16)
    distances[0] = 0
    queue = deque([0])
    while queue:
        source = queue.popleft()
        for move_index, target in enumerate(matrix[source]):
            if target == count or distances[target] != -1:
                continue
            parent[target], parent_move[target] = source, move_index
            distances[target] = distances[source] + 1
            queue.append(int(target))
    assert np.all(distances >= 0), "complete graph must be connected"
    return parent, parent_move, distances


def setup_word(vertex, parent, parent_move):
    result = []
    while vertex:
        result.append(MOVES[int(parent_move[vertex])])
        vertex = int(parent[vertex])
    return " ".join(reversed(result))


def measure(name, catalog, replay_budget):
    wall_start = perf_counter()
    bandage = notebook_bandage(name)
    start = perf_counter()
    graph = c.explore(bandage)
    assert graph.complete and graph.metric == "QTM"
    exploration_seconds = perf_counter() - start
    count = len(graph)
    start = perf_counter()
    actions = transitions(graph)
    transition_seconds = perf_counter() - start
    start = perf_counter()
    parent, parent_move, distances = setup_tree(actions, count)
    setup_tree_seconds = perf_counter() - start
    starts = np.arange(count, dtype=np.int32)
    available_shapes = np.zeros(count, dtype=bool)
    records, hits = [], []
    start = perf_counter()
    for algorithm in catalog["variants"]:
        ends = starts.copy()
        for move in algorithm["word"].split():
            ends = actions[move][ends]
        closed = ends == starts
        available_shapes |= closed
        vertices = np.flatnonzero(closed)
        record = dict(algorithm, legal_shapes=int(np.count_nonzero(ends != count)),
                      closed_shapes=len(vertices), closed_at_root=bool(closed[0]))
        if len(vertices):
            # A few equal/near-shortest setups offer different rooted effects.
            nearest = sorted(vertices.tolist(), key=lambda v: (int(distances[v]), v))[:2]
            record.update(minimum_setup_htm=int(distances[nearest[0]]),
                          representative_vertex=nearest[0])
            for vertex in nearest:
                hits.append((int(distances[vertex]) * 2 + algorithm["htm"],
                             algorithm["id"], vertex, record))
        records.append(record)
    scan_seconds = perf_counter() - start
    print(f"{name}: {count} shapes, {sum(bool(r['closed_shapes']) for r in records)} "
          f"usable words; scan {scan_seconds:.3f}s", flush=True)

    # Reserve one hit per available base before filling by total travel/body cost.
    hits.sort(key=lambda hit: hit[:3])
    selected, selected_keys, represented_bases = [], set(), set()
    for hit in hits:
        if hit[3]["base_id"] not in represented_bases:
            selected.append(hit)
            selected_keys.add(hit[1:3])
            represented_bases.add(hit[3]["base_id"])
    for hit in hits:
        if len(selected) >= replay_budget:
            break
        if hit[1:3] not in selected_keys:
            selected.append(hit)
            selected_keys.add(hit[1:3])
    selected = selected[:replay_budget]
    start = perf_counter()
    root = c.Shape(bandage)
    effects, checked = {}, []
    for _, _, vertex, row in selected:
        setup = c.ShapePath.from_moves(root, setup_word(vertex, parent, parent_move))
        assert graph.vertex_id(setup.target_shape) == vertex
        body = c.ShapePath.local_loop(setup.target_shape, row["word"])
        transported = setup.transport_loop(body)
        replay = c.State(root).apply(transported.moves)
        assert replay.shape == root
        assert replay.sticker_permutation == transported.permutation
        effect = tuple(replay.sticker_permutation)
        entry = dict(algorithm_id=row["id"], base_id=row["base_id"], family=row["family"],
                     body=row["word"], setup=setup.moves, vertex=vertex,
                     setup_htm=setup.htm_length, body_htm=row["htm"],
                     conjugate=transported.moves, conjugate_htm=transported.htm_length,
                     body_closed_at_root=row["closed_at_root"],
                     rooted_effect=dict(
                         corner_moved=sum(i != value for i, value in enumerate(replay.corners)),
                         corner_twisted=sum(bool(value) for value in replay.twists),
                         edge_moved=sum(i != value for i, value in enumerate(replay.edges)),
                         edge_flipped=sum(bool(value) for value in replay.flips)))
        checked.append(entry)
        if effect != tuple(range(48)) and (
                effect not in effects or effects[effect]["conjugate_htm"] > entry["conjugate_htm"]):
            effects[effect] = entry
    replay_seconds = perf_counter() - start
    family_counts = {}
    for family in sorted({row["family"] for row in records}):
        rows = [row for row in records if row["family"] == family]
        family_counts[family] = dict(
            catalog_words=len(rows), usable_anywhere=sum(bool(r["closed_shapes"]) for r in rows),
            closed_at_root=sum(r["closed_at_root"] for r in rows),
            available_only_away_from_root=sum(bool(r["closed_shapes"]) and not r["closed_at_root"]
                                              for r in rows),
            legal_without_any_closure=sum(bool(r["legal_shapes"]) and not r["closed_shapes"]
                                          for r in rows))
    return dict(
        puzzle=name, signature=c.block_signature(bandage, include_singletons=True),
        shapes=count, catalog_words=len(records),
        total_catalog_htm=sum(r["htm"] for r in records),
        shapes_with_some_catalog_loop=int(np.count_nonzero(available_shapes)),
        available_words=sum(bool(r["closed_shapes"]) for r in records),
        root_available_words=sum(r["closed_at_root"] for r in records),
        family_counts=family_counts,
        maximum_shortest_setup_htm=int(distances.max()),
        timings=dict(exploration_seconds=exploration_seconds,
                     transition_seconds=transition_seconds, setup_tree_seconds=setup_tree_seconds,
                     catalog_scan_seconds=scan_seconds, checked_replay_seconds=replay_seconds,
                     total_seconds=perf_counter() - wall_start),
        checked_replays=len(checked), distinct_nonidentity_rooted_effects=len(effects),
        shortest_checked_conjugate_htm=min((r["conjugate_htm"] for r in effects.values()), default=None),
        longest_checked_conjugate_htm=max((r["conjugate_htm"] for r in effects.values()), default=None),
        checked_candidates=checked, algorithms=records,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("puzzles", nargs="*", default=["BeltRoad", "MostSignaturesCube", "FourPair"])
    parser.add_argument("--replay-budget", type=int, default=256)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent.parent / "research-results" /
                        "familiar-algorithm-transport.json")
    args = parser.parse_args()
    if args.replay_budget < 1:
        parser.error("replay budget must be positive")
    catalog = build()
    result = dict(
        scope="research-only discovery and checked transport; no compiled method quality claim",
        replay_budget_per_puzzle=args.replay_budget,
        catalog=dict(bases=catalog["base_templates"], variants=len(catalog["variants"]),
                     families=dict(Counter(row["family"] for row in catalog["variants"])),
                     coverage=verify_adjacent_commutator_coverage(catalog)),
        puzzles=[measure(name, catalog, args.replay_budget) for name in args.puzzles],
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
