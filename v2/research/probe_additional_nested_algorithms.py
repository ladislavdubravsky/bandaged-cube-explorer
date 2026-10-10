#!/usr/bin/env python3
"""Bounded MostSignaturesCube follow-up with additional nested commutators.

Run from the repository root with v2/.venv/bin/python. This research probe
uses independent compiled bond obstructions rather than dense graph traversal.
The selected template family is a sample, not every nested commutator or every
ordinary 3x3 algorithm. No production solver or notebook is changed.
"""

import argparse
from itertools import product
import json
from pathlib import Path
import signal
from time import perf_counter

import bce_v2 as c
from bce_v2.loop_rotations import bandage_symmetries, rotate_moves
import numpy as np

from familiar_algorithm_catalog import (
    build, commutator, inverse, ordinary_effect, simplified,
)
from probe_algorithm_obstructions import BONDS, compile_word_obstruction
from profile_notebook_graph import notebook_bandage


SCOPE = (
    "Selected RU/RUprime inner commutators with powers 1/2/3 and "
    "RU2/R2U inner commutators with powers 1/2; "
    "outer D/Dprime/D2/F/Fprime/F2; all proper rotations and inverse classes; "
    "original familiar-algorithm catalog words excluded. "
    "This does not exhaust nested commutators or ordinary 3x3 algorithms."
)


def candidate_words():
    """Return 1,440 selected forms before excluding the existing catalog."""
    words = {}
    rotations = ("", *bandage_symmetries())
    for first, second in (("R", "U"), ("R", "U'"), ("R", "U2"), ("R2", "U")):
        powers = (1, 2) if "2" in first + second else (1, 2, 3)
        for power, third, suffix in product(powers, ("D", "F"), ("", "'", "2")):
            inner = " ".join([commutator(first, second)] * power)
            body = commutator(inner, third + suffix)
            if c.State().apply(body).is_solved:
                continue
            for rotation in rotations:
                rotated = rotate_moves(body, rotation)
                word = min(rotated, inverse(rotated))
                words.setdefault(word, dict(
                    inner_first=first, inner_second=second, inner_power=power,
                    outer=third + suffix, rotation=rotation, inverse=word != rotated,
                ))
    assert len(words) <= 1440, "follow-up must remain within its proposal bound"
    original = {row["word"] for row in build()["variants"]}
    additional = {word: metadata for word, metadata in words.items() if word not in original}
    return additional, len(words), len(words) - len(additional)


def measure():
    started = perf_counter()
    words, proposed_count, excluded_count = candidate_words()
    bandage = notebook_bandage("MostSignaturesCube")
    graph = c.explore(bandage)
    assert graph.complete, "negative result requires the complete reachable graph"
    labels = np.asarray([shape.labels for shape in graph.shapes], dtype=np.uint8)
    bits = np.zeros(len(graph), dtype=np.uint64)
    for index, (first, second) in enumerate(BONDS):
        bits |= ((labels[:, first] == labels[:, second]).astype(np.uint64)
                 << np.uint64(index))

    mask_started = perf_counter()
    legal_words = closed_words = native_samples = 0
    hits, legal_shapes, closed_shapes = [], set(), set()
    for word, metadata in words.items():
        forbidden, destinations = compile_word_obstruction(word)
        legal = np.flatnonzero((bits & np.uint64(forbidden)) == 0)
        if not len(legal):
            continue
        legal_words += 1
        legal_shapes.update(map(int, legal))
        values = bits[legal]
        final_bits = np.zeros(len(legal), dtype=np.uint64)
        for source, destination in destinations.items():
            final_bits |= (((values >> np.uint64(source)) & np.uint64(1))
                           * np.uint64(destination))
        closed = legal[final_bits == values]

        # Independently replay one complete native shape per legal word form.
        vertex = int(legal[0])
        shape = graph.shapes[vertex]
        endpoint = shape.apply(word)
        assert (endpoint == shape) == bool(final_bits[0] == values[0])
        native_samples += 1
        if not len(closed):
            continue
        closed_words += 1
        closed_shapes.update(map(int, closed))
        vertex = int(closed[0])
        shape = graph.shapes[vertex]
        assert shape.apply(word) == shape
        setup = graph.shortest_path(0, vertex)
        conjugate = simplified(setup + " " + word + " " + inverse(setup))
        replay = c.State(bandage).apply(conjugate)
        assert replay.shape == c.Shape(bandage)
        hits.append(dict(
            word=word, template=metadata, legal_shapes=len(legal),
            closed_shapes=len(closed), vertex=vertex, setup=setup,
            conjugate=conjugate, conjugate_htm=len(conjugate.split()),
            ordinary_effect=ordinary_effect(word), rooted_effect=ordinary_effect(conjugate),
        ))
    return dict(
        puzzle="MostSignaturesCube", graph_shapes=len(graph),
        graph_complete=graph.complete, proposed_words=proposed_count,
        excluded_existing_catalog_words=excluded_count, tested_new_words=len(words),
        legal_words=legal_words, closed_words=closed_words,
        distinct_legal_shapes=len(legal_shapes), distinct_closed_shapes=len(closed_shapes),
        native_sample_replays=native_samples, hits=hits,
        seconds=perf_counter() - started, mask_seconds=perf_counter() - mask_started,
        scope=SCOPE,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=55,
                        help="external wall-clock budget; defaults to 55 seconds")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "research-results" /
                        "mostsignatures-additional-nested.json")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")

    def expired(*_):
        raise TimeoutError("additional nested-algorithm research budget expired")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, args.seconds)
    try:
        result = measure()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "hits"}, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
