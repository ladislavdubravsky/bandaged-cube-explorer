#!/usr/bin/env python3
"""Check compiled word obstructions against independent native shape replay.

Run from the repository root with its installed v2 environment:

    v2/.venv/bin/python v2/research/probe_algorithm_obstructions.py \
        --output v2/research-results/algorithm-obstruction-check.json

This research prototype uses an independent, axis-major 54-bit encoding. Its
bit positions are geometry.BONDS indices, not the native DefaultLayout's raw
bit positions. A native implementation would use BondLayout.POSITIONS.

For a fixed raw algorithm, replay each independent adjacency bond. Bonds that
get split at any intermediate turn form a forbidden mask. Each allowed bond
also has a final destination. A connected fused block is legal precisely when
all of its saturated adjacency bonds are legal, so this mask checks the entire
word with one intersection, including words that temporarily extract pairs.
The final bit permutation independently checks exact shape closure.

Random fixtures include arbitrary connected partitions and invisible core
bonds. These are validation samples, not reachability or puzzle-quality data.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import time

import bce_v2 as c


# Same physical adjacency order as geometry.BONDS: strides 9, 3, 1.
BONDS = tuple((cell, cell + stride)
              for stride in (9, 3, 1)
              for cell in range(27) if (cell // stride) % 3 < 2)


def shape_bits(shape):
    """Saturated independent adjacency encoding, including core bonds."""
    return sum(1 << index for index, (a, b) in enumerate(BONDS)
               if shape[a] == shape[b])


def inverse(word):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(word.split()))


def commutator(first, second):
    return f"{first} {second} {inverse(first)} {inverse(second)}"


def test_words():
    basic = commutator("R", "U")
    return (
        ("open-face-turn", "R"),
        # Raw legality must be checked before simplifying to the empty word.
        ("blocked-cancellation", "R R'"),
        ("RU-commutator", basic),
        ("RU-commutator-squared", f"{basic} {basic}"),
        ("RU-commutator-cubed", f"{basic} {basic} {basic}"),
        ("RU2-commutator", commutator("R", "U2")),
        ("RprimeF-commutator", commutator("R'", "F")),
        ("nested-corner-commutator", commutator(basic, "D")),
        ("nested-two-corner-twist", commutator(f"{basic} {basic}", "D")),
        ("sune", "R U R' U R U2 R'"),
        ("T-permutation", "R U R' U' R' F R2 U' R' U' R U R' F'"),
        ("U-permutation", "R U' R U R U R U' R' U' R2"),
        ("edge-OLL", "F R U R' U' F'"),
        ("long-two-face-word", "R U R U R U R U R U R U"),
    )


def compile_word_obstruction(word):
    """Compile one raw word using 54 checked single-bond shape replays."""
    forbidden, destinations = 0, {}
    for index, (a, b) in enumerate(BONDS):
        labels = [0] * 27
        labels[a] = labels[b] = 1
        try:
            endpoint = c.Shape(labels).apply(word)
        except c.BlockedMoveError:
            forbidden |= 1 << index
        else:
            endpoint_bits = shape_bits(endpoint)
            if endpoint_bits.bit_count() != 1:
                raise AssertionError("a legal single bond must remain a single bond")
            destinations[index] = endpoint_bits
    return forbidden, destinations


def random_shapes(seed, samples_per_density):
    rng = random.Random(seed)
    for probability in (0, .01, .03, .07, .15, .4):
        for _ in range(samples_per_density):
            parent = list(range(27))

            def root(cell):
                while parent[cell] != cell:
                    cell = parent[cell]
                return cell

            for a, b in BONDS:
                if rng.random() < probability:
                    parent[root(b)] = root(a)
            yield c.Shape([root(cell) + 1 for cell in range(27)])


def endpoint_regressions():
    """Distinguish exact word legality, endpoint closure, and face freedom."""
    labels = [0] * 27
    labels[c.UR] = labels[c.R] = 1
    clock = c.Shape(labels)
    pair_labels = [0] * 27
    pair_labels[c.FR] = pair_labels[c.DFR] = 1
    moving_pair = c.Shape(pair_labels)
    bicube = c.fixture("Bicube Fuse")
    fixtures = (
        ("temporarily-extracted-pair", clock, "R U R' D R U' R' D'", True, True),
        ("body-open-and-undo-blocked", bicube, "U F2 U'", False, False),
        ("legal-whole-word-remains-open", bicube, "U F U'", True, False),
        ("ordinary-commutator-moves-pair", moving_pair, "R U R' U'", True, False),
    )
    records = []
    for name, shape, word, expected_legal, expected_closed in fixtures:
        forbidden, destinations = compile_word_obstruction(word)
        original = shape_bits(shape)
        compiled_legal = not (original & forbidden)
        try:
            endpoint = shape.apply(word)
        except c.BlockedMoveError:
            legal, closed = False, False
        else:
            legal, closed = True, endpoint == shape
            compiled_endpoint = 0
            for initial, target in destinations.items():
                if original & (1 << initial):
                    compiled_endpoint |= target
            if compiled_endpoint != shape_bits(endpoint):
                raise AssertionError(f"fixture final action mismatch: {name}")
        if ((legal, closed) != (expected_legal, expected_closed)
                or compiled_legal != legal):
            raise AssertionError(f"fixture applicability mismatch: {name}")
        records.append({"name": name, "shape": shape.labels, "word": word,
                        "legal": legal, "closed": closed,
                        "initial_turnable_faces": [face for face in "URFDLB"
                                                   if shape.is_turnable(face)]})
    return records


def run(seed=470, samples_per_density=200):
    words = test_words()
    started = time.perf_counter()
    compiled = [compile_word_obstruction(word) for _, word in words]
    compile_seconds = time.perf_counter() - started
    shapes = tuple(random_shapes(seed, samples_per_density))
    counts = Counter()
    body_counts = [Counter() for _ in words]
    started = time.perf_counter()
    for shape in shapes:
        original = shape_bits(shape)
        for index, ((name, word), (forbidden, destinations)) in enumerate(zip(words, compiled)):
            expected_legal = not (original & forbidden)
            try:
                endpoint = shape.apply(word)
            except c.BlockedMoveError:
                legal = False
            else:
                legal = True
            if legal != expected_legal:
                raise AssertionError(f"legality mismatch: {name}, {shape}")
            counts["trials"] += 1
            body_counts[index]["trials"] += 1
            if legal:
                expected_bits = 0
                for initial, target in destinations.items():
                    if original & (1 << initial):
                        expected_bits |= target
                if shape_bits(endpoint) != expected_bits:
                    raise AssertionError(f"final bit action mismatch: {name}, {shape}")
                if (endpoint == shape) != (expected_bits == original):
                    raise AssertionError(f"closure mismatch: {name}, {shape}")
                counts["legal"] += 1
                counts["closed"] += endpoint == shape
                body_counts[index]["legal"] += 1
                body_counts[index]["closed"] += endpoint == shape
    validation_seconds = time.perf_counter() - started
    return {
        "schema": "bce.research.algorithm_obstructions.v1",
        "model": "full-grid-27-fixed-centers",
        "scope": "random connected partitions; core bonds included; no reachability claims",
        "bit_encoding": "independent axis-major geometry.BONDS indices; not native DefaultLayout bits",
        "settings": {"seed": seed, "samples_per_density": samples_per_density,
                     "bond_probabilities": [0, .01, .03, .07, .15, .4]},
        "shape_count": len(shapes),
        "unique_shape_count": len(set(shapes)),
        "core_bond_shape_count": sum(any(shape[a] == shape[b] for a, b in BONDS
                                         if c.C in (a, b)) for shape in shapes),
        "totals": {**counts, "mismatches": 0},
        "timings": {"compile_seconds": compile_seconds,
                    "validation_seconds": validation_seconds},
        "endpoint_regressions": endpoint_regressions(),
        "bodies": [{"name": name, "word": word,
                    "forbidden_bond_count": forbidden.bit_count(),
                    "forbidden_bonds": f"{forbidden:014x}",
                    "allowed_single_bonds_moved": sum(target != 1 << initial
                                                       for initial, target in destinations.items()),
                    "all_legal_shapes_closed": all(target == 1 << initial
                                                   for initial, target in destinations.items()),
                    **body_count}
                   for (name, word), (forbidden, destinations), body_count in
                   zip(words, compiled, body_counts)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=470)
    parser.add_argument("--samples-per-density", type=int, default=200)
    args = parser.parse_args()
    if args.samples_per_density < 1:
        parser.error("--samples-per-density must be positive")
    text = json.dumps(run(args.seed, args.samples_per_density), indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
