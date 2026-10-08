"""Standard regrips agree with native face mechanics and exact partitions."""

from itertools import product
import random
from types import SimpleNamespace
import unittest

import bce_v2 as c
from bce_v2.block_actions import _ROTATIONS, _CELL_IMAGES
from bce_v2.isotropy import IsotropyAnalysis
from bce_v2.loop_rotations import (
    normalize_rotation, rotation_tuple, inverse_rotation, rotate_moves,
    rotate_permutation, bandage_symmetries,
)


TOKENS = ("x", "x'", "x2", "y", "y'", "y2", "z", "z'", "z2")
IDENTITY = tuple(range(48))


def fused(*members):
    labels = [0] * 27
    for cell in members:
        labels[cell] = 91
    return c.Shape(labels)


def partition(reference):
    groups = {}
    for cell, label in enumerate(reference):
        groups.setdefault(label, set()).add(cell)
    return frozenset(frozenset(members) for members in groups.values())


class RotationGeometryTests(unittest.TestCase):
    def test_standard_axis_conventions_use_inverse_frame_face_mapping(self):
        # Independent expected maps for a physical regrip followed by its
        # inverse, in displayed U R F D L B order (WCA 12a4 directions).
        expected = {"x": "F R D B L U", "y": "U B R D F L",
                    "z": "L U F R D B"}
        for axis, word in expected.items():
            with self.subTest(axis=axis):
                self.assertEqual(rotate_moves("U R F D L B", axis), word)
                self.assertEqual(rotate_moves("U' R2", axis),
                                 word.split()[0] + "' " + word.split()[1] + "2")
                twice = rotate_moves(word, axis)
                self.assertEqual(rotate_moves("U R F D L B", axis + "2"), twice)
                self.assertEqual(rotate_moves(twice, axis),
                                 rotate_moves("U R F D L B", axis + "'"))
        self.assertEqual(rotate_moves("U", "x"), "F")
        self.assertEqual(rotate_moves("R", "y"), "B")
        self.assertEqual(rotate_moves("U", "z"), "L")
        with self.assertRaises(ValueError):
            c.State().apply("x")  # Regrips are not added to the native engine.

    def test_all_24_rotations_have_shortest_deterministic_standard_words(self):
        words = [""] + [" ".join(tokens) for count in (1, 2)
                        for tokens in product(TOKENS, repeat=count)]
        shortest = {}
        for word in words:
            rotation = rotation_tuple(word)
            shortest[rotation] = min(shortest.get(rotation, 100), len(word.split()))
        self.assertEqual(set(shortest), set(_ROTATIONS))
        canonical = {normalize_rotation(word) for word in words}
        self.assertEqual(len(canonical), 24)
        for word in words:
            normal = normalize_rotation(word)
            self.assertEqual(rotation_tuple(normal), rotation_tuple(word))
            self.assertEqual(len(normal.split()), shortest[rotation_tuple(word)])
            self.assertEqual(normalize_rotation(normal), normal)
            inverse = inverse_rotation(word)
            self.assertEqual(normalize_rotation(word + " " + inverse), "")
            self.assertEqual(normalize_rotation(inverse + " " + word), "")
        self.assertEqual(normalize_rotation("x x'"), "")
        self.assertEqual(normalize_rotation("x x"), "x2")
        self.assertEqual(normalize_rotation("x x x"), "x'")
        self.assertEqual(normalize_rotation(" \n x\t x  "), "x2")
        self.assertNotEqual(rotation_tuple("x y"), rotation_tuple("y x"))

    def test_geometric_sticker_conjugation_matches_native_execution(self):
        orientations = ("",) + bandage_symmetries(c.Shape())
        rng = random.Random(73491)
        face_tokens = tuple(face + suffix for face in "URFDLB"
                            for suffix in ("", "'", "2"))
        words = ["", "U R2 F' D L B2", "R U R' U'", "F2 L D2 B' U2 R"]
        words += [" ".join(rng.choice(face_tokens) for _ in range(25))
                  for _ in range(12)]
        for orientation, word in product(orientations, words):
            with self.subTest(orientation=orientation, word=word):
                actual = c.State().apply(rotate_moves(word, orientation))
                expected = rotate_permutation(c.State().apply(word).sticker_permutation,
                                              orientation)
                self.assertEqual(actual.sticker_permutation, expected)
                self.assertEqual(rotate_permutation(expected, inverse_rotation(orientation)),
                                 c.State().apply(word).sticker_permutation)
                self.assertEqual(rotate_permutation(IDENTITY, orientation), IDENTITY)
                self.assertTrue(all(token[0] in "URFDLB"
                                    for token in rotate_moves(word, orientation).split()))

    def test_native_rotation_indices_preserve_the_exact_same_cell_partition(self):
        references = (fused(c.U, c.C), fused(c.L, c.C, c.R),
                      fused(c.UBL, c.UB, c.UL), c.fixture("Bicube Fuse"))
        for reference, rotation in product(references, _ROTATIONS):
            images = _CELL_IMAGES[rotation]
            expected = frozenset(frozenset(images[cell] for cell in members)
                                 for members in partition(reference))
            actual = reference.rotated(_ROTATIONS.index(rotation))
            self.assertEqual(partition(actual), expected)

    def test_invalid_rotation_words_moves_and_permutations_are_rejected(self):
        for word in ("X", "R", "x3", "x2'", "xy", "x R", "z''"):
            for operation in (rotation_tuple, normalize_rotation, inverse_rotation):
                with self.subTest(word=word, operation=operation.__name__):
                    with self.assertRaises(ValueError):
                        operation(word)
        for value in (None, 1, ["x"]):
            with self.assertRaises(TypeError):
                normalize_rotation(value)
        for moves in ("r", "x", "U3", "R2'", "RUR'", "F //"):
            with self.assertRaises(ValueError):
                rotate_moves(moves, "x")
        with self.assertRaises(TypeError):
            rotate_moves(["U"], "x")
        self.assertEqual(rotate_moves("\t U2\nR' ", ""), "U2 R'")
        for images in (range(47), [0] * 48, range(1, 49),
                       [False] + list(range(1, 48)),
                       [0.0] + list(range(1, 48))):
            with self.assertRaises(ValueError):
                rotate_permutation(images, "x")
        with self.assertRaises(TypeError):
            rotate_permutation(None, "x")


class BandageSymmetryTests(unittest.TestCase):
    def test_exact_symmetries_include_core_bonds_and_noncuboid_membership(self):
        ordinary = bandage_symmetries(c.Shape())
        self.assertEqual(len(ordinary), 23)
        self.assertEqual(len(set(map(rotation_tuple, ordinary))), 23)
        self.assertEqual(bandage_symmetries(c.Shape([1] * 27)), ordinary)
        axial = ("y", "y'", "y2")
        self.assertEqual(bandage_symmetries(c.Shape([1] * 9 + [0] * 18)), axial)
        self.assertEqual(bandage_symmetries(fused(c.U, c.C)), axial)
        self.assertEqual(bandage_symmetries(fused(c.U, c.UB, c.UF, c.UL, c.UR)), axial)
        self.assertEqual(len(bandage_symmetries(fused(c.L, c.C, c.R))), 7)
        self.assertEqual(bandage_symmetries(fused(c.UBL, c.UB, c.UL)), ())
        self.assertEqual(bandage_symmetries(c.fixture("Alcatraz")), ())
        self.assertEqual(len(bandage_symmetries(c.fixture("Bicube Fuse"))), 2)
        self.assertEqual(len(bandage_symmetries(c.fixture("Shark Fin Soup"))), 1)

    def test_input_adapters_use_reference_shape_and_ignore_label_names(self):
        reference = fused(c.U, c.C)
        loops = c.isotropy_loops(reference)
        analysis = IsotropyAnalysis(loops, 1, (), "test")
        expected = bandage_symmetries(reference)
        for initial in (loops, analysis, SimpleNamespace(analysis=analysis),
                        c.State(reference).apply("R")):
            self.assertEqual(bandage_symmetries(initial), expected)
        labels = [0] * 27
        labels[c.U] = labels[c.C] = 17
        self.assertEqual(bandage_symmetries(labels), expected)
        self.assertEqual(bandage_symmetries(), bandage_symmetries(c.Shape()))
        moving_reference = c.fixture("Bicube Fuse")
        scrambled = c.State(moving_reference).apply("R")
        self.assertNotEqual(scrambled.shape, moving_reference)
        self.assertEqual(bandage_symmetries(scrambled),
                         bandage_symmetries(moving_reference))
        moved = scrambled.shape
        nonzero_root = c.isotropy_loops(moved)
        self.assertEqual(bandage_symmetries(nonzero_root), bandage_symmetries(moved))

    def test_every_symmetric_loop_transfer_replays_legally_with_exact_action(self):
        references = (c.Shape(), c.Shape([1] * 9 + [0] * 18),
                      fused(c.U, c.UB, c.UF, c.UL, c.UR),
                      fused(c.U, c.C), fused(c.L, c.C, c.R),
                      c.fixture("Bicube Fuse"), c.fixture("Shark Fin Soup"))
        checked = 0
        for reference in references:
            loops = c.isotropy_loops(reference)
            for symmetry, generator in product(bandage_symmetries(loops), loops):
                with self.subTest(shape=reference.labels, symmetry=symmetry,
                                  generator=generator.id):
                    word = rotate_moves(generator.moves, symmetry)
                    replay = c.State(reference).apply(word)
                    self.assertEqual(replay.shape, reference)
                    self.assertEqual(replay.sticker_permutation,
                                     rotate_permutation(generator.permutation, symmetry))
                    checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
