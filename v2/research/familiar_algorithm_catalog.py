"""A bounded familiar-3x3 word catalog for graph-availability experiments.

This is research input, not a solver or a claim of bandage legality. A word is
usable at a graph vertex only after checked legal replay returns to that exact
shape. A path to the vertex, the word, and the reversed path must then be
replayed on the colored bandaged cube before admitting the conjugate.

Inversion is an exact availability equivalence only for such closed words.
Spatial rotations here relabel candidate face turns; they are not assumed to
be symmetries of any particular bandage. Distinct physical words are retained
even when they have the same ordinary-cube effect, because their legality can
differ. Antisune is included by inversion of Sune.
"""

from collections import Counter
from itertools import combinations_with_replacement, product
import json

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.loop_rotations import bandage_symmetries, rotate_moves


def inverse(word):
    """Invert an outer-face word without introducing rotations or slices."""
    return " ".join(token if token.endswith("2") else token[0]
                    if token.endswith("'") else token + "'"
                    for token in reversed(word.split()))


def simplified(word):
    return _simplified_moves(word.split())


def commutator(first, second):
    return simplified(" ".join((first, second, inverse(first), inverse(second))))


def ordinary_effect(word, *, cubies=False):
    """Verify and summarize the exact effect using the native colored engine."""
    state = c.State().apply(word)
    result = dict(
        corner_moved=sum(i != value for i, value in enumerate(state.corners)),
        corner_twisted=sum(bool(value) for value in state.twists),
        edge_moved=sum(i != value for i, value in enumerate(state.edges)),
        edge_flipped=sum(bool(value) for value in state.flips),
    )
    if cubies:
        # Native Kociemba ordering; these arrays completely specify the effect.
        result.update(corners=state.corners, twists=state.twists,
                      edges=state.edges, flips=state.flips)
    return result


def build():
    """Return 27 verified bases and 552 distinct words modulo inversion."""
    bases = []
    # Rotations plus inversion supply all ordered adjacent face pairs. Swapping
    # the two commutator operands inverts the commutator, so six exponent pairs
    # suffice in this base frame instead of nine.
    for first, second in combinations_with_replacement(("", "'", "2"), 2):
        body = commutator("R" + first, "U" + second)
        for power in (1, 2, 3):
            bases.append(dict(
                id=f"comm_R{first}_U{second}_power{power}",
                family="two_face_commutator",
                word=simplified(" ".join([body] * power)),
            ))
    for power in (1, 2):
        inner = " ".join([commutator("R", "U")] * power)
        bases.append(dict(id=f"nested_comm_power{power}_D",
                          family="nested_commutator",
                          word=commutator(inner, "D")))

    extra = (
        ("edge_3cycle", "edge_cycle", "R2 U R U R' U' R' U' R' U R'"),
        # This common OLL also permutes corners/edges. Do not call it a pure flip.
        ("edge_orientation_OLL", "OLL", "R U R' U' R' F R F'"),
        # Outer-face expansion of M' U M' U M' U2 M U M U M U2.
        ("pure_opposite_edge_flip", "edge_flip",
         "R' L F R' L D R' L B2 L' R D L' R F L' R U2"),
        # Outer-face expansion of OLL28 followed by a matching inverse Ua.
        # Longer and five-face: included for exact coverage, not presumed useful.
        ("pure_adjacent_edge_flip", "edge_flip",
         "L F R' F' L' R U R U' R' B U' B U B U B U' B' U' B2"),
        ("sune", "OLL", "R U R' U R U2 R'"),
        ("H_corner_OLL", "OLL", "R U R' U R U' R' U R U2 R'"),
        ("T_PLL", "PLL", "R U R' U' R' F R2 U' R' U' R U R' F'"),
        ("Jb_PLL", "PLL", "R U R' F' R U R' U' R' F R2 U' R' U'"),
    )
    bases.extend(dict(id=name, family=family, word=word)
                 for name, family, word in extra)
    excluded = [row["id"] for row in bases if c.State().apply(row["word"]).is_solved]
    bases = [row for row in bases if row["id"] not in excluded]
    for row in bases:
        row["htm"] = len(row["word"].split())
        row["ordinary_cube_effect"] = ordinary_effect(row["word"], cubies=True)

    variants = {}
    rotations = ("", *bandage_symmetries(c.Shape()))
    for row in bases:
        for rotation in rotations:
            rotated = rotate_moves(row["word"], rotation)
            word = min(rotated, inverse(rotated))
            if word not in variants:
                variants[word] = dict(
                    id=f"A{len(variants) + 1}", base_id=row["id"],
                    family=row["family"], rotation=rotation,
                    inverse=word != rotated, word=word,
                    htm=len(word.split()), ordinary_cube_effect=ordinary_effect(word),
                )
    return dict(base_templates=bases, variants=list(variants.values()),
                excluded_identity_bases=excluded)


def verify_adjacent_commutator_coverage(catalog=None):
    """Compare literal words against independent full ordered-pair enumeration."""
    catalog = build() if catalog is None else catalog
    opposite = dict(U="D", D="U", R="L", L="R", F="B", B="F")
    expected, identity_count = set(), 0
    for first, second in product("URFDLB", repeat=2):
        if first == second or opposite[first] == second:
            continue
        for left, right, power in product(("", "'", "2"), ("", "'", "2"), (1, 2, 3)):
            body = commutator(first + left, second + right)
            word = simplified(" ".join([body] * power))
            if c.State().apply(word).is_solved:
                identity_count += 1
                continue
            expected.add(min(word, inverse(word)))
    actual = {row["word"] for row in catalog["variants"]
              if row["family"] == "two_face_commutator"}
    assert actual == expected, (len(expected - actual), len(actual - expected))
    return dict(ordered_candidate_count=648, excluded_identity_words=identity_count,
                distinct_nonidentity_words_modulo_inverse=len(actual))


if __name__ == "__main__":
    catalog = build()
    print(json.dumps(dict(
        base_count=len(catalog["base_templates"]), variant_count=len(catalog["variants"]),
        families=dict(Counter(row["family"] for row in catalog["variants"])),
        coverage=verify_adjacent_commutator_coverage(catalog),
        base_effects=[dict(id=row["id"], word=row["word"], htm=row["htm"],
                          **ordinary_effect(row["word"]))
                     for row in catalog["base_templates"]],
    ), indent=2))
