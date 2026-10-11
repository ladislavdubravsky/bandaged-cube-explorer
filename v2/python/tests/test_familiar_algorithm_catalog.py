"""Exact physical-word coverage and native obstruction regressions."""

from collections import Counter
from dataclasses import FrozenInstanceError, replace
from itertools import product
import random
import unittest

import bce_v2 as c
from bce_v2.familiar_algorithm_catalog import (
    BONDS, FamiliarAlgorithm, FamiliarAlgorithmCatalog, compile_word_obstruction,
    familiar_algorithm_catalog, shape_bond_bits,
)


def inverse(word):
    return " ".join(token if token.endswith("2") else token[:-1]
                    if token.endswith("'") else token + "'"
                    for token in reversed(word.split()))


def fixture_pair(first, second):
    labels = [0] * 27
    labels[first] = labels[second] = 1
    return c.Shape(labels)


class FamiliarAlgorithmCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = familiar_algorithm_catalog()

    def test_exact_catalog_is_cached_immutable_and_natively_verified(self):
        self.assertIs(self.catalog, familiar_algorithm_catalog())
        self.assertEqual((len(self.catalog.base_templates), len(self.catalog)), (27, 552))
        self.assertEqual(len({entry.word for entry in self.catalog}), 552)
        self.assertEqual(Counter(entry.family for entry in self.catalog), {
            "two_face_commutator": 312, "nested_commutator": 48,
            "edge_cycle": 24, "edge_flip": 48, "OLL": 72, "PLL": 48,
        })
        self.assertTrue(self.catalog.excluded_identity_bases)
        for entry in (*self.catalog.base_templates, *self.catalog.variants):
            with self.subTest(algorithm=entry.id):
                state = c.State().apply(entry.word)
                self.assertFalse(state.is_solved)
                self.assertEqual(entry.htm, len(entry.word.split()))
                self.assertEqual(entry.permutation, state.sticker_permutation)
                self.assertEqual(entry.ordinary_effect.corners, tuple(state.corners))
                self.assertEqual(entry.ordinary_effect.twists, tuple(state.twists))
                self.assertEqual(entry.ordinary_effect.edges, tuple(state.edges))
                self.assertEqual(entry.ordinary_effect.flips, tuple(state.flips))
        with self.assertRaises(FrozenInstanceError):
            self.catalog.variants[0].word = "R"
        with self.assertRaises(TypeError):
            self.catalog.variants[0].ordinary_effect.corners[0] = 2

    def test_adjacent_commutators_have_independent_full_ordered_coverage(self):
        expected, identity_count, tested = set(), 0, 0
        opposite = dict(U="D", D="U", F="B", B="F", R="L", L="R")
        for first, second in product("URFDLB", repeat=2):
            if first == second or second == opposite[first]:
                continue
            for left, right, power in product(("", "'", "2"), ("", "'", "2"), (1, 2, 3)):
                operands = (first + left, second + right)
                body = " ".join((*operands, inverse(operands[0]), inverse(operands[1])))
                word = " ".join([body] * power)
                tested += 1
                if c.State().apply(word).is_solved:
                    identity_count += 1
                else:
                    expected.add(min(word, inverse(word)))
        actual = {entry.word for entry in self.catalog if entry.family == "two_face_commutator"}
        self.assertEqual((tested, identity_count, len(expected)), (648, 24, 312))
        self.assertEqual(actual, expected)

    def test_pure_family_names_match_exact_base_effects(self):
        bases = {entry.id: entry for entry in self.catalog.base_templates}
        for name in ("pure_opposite_edge_flip", "pure_adjacent_edge_flip"):
            effect = bases[name].ordinary_effect
            self.assertEqual((effect.corner_moved, effect.corner_twisted, effect.edge_moved,
                              effect.edge_flipped), (0, 0, 0, 2))
        effect = bases["edge_3cycle"].ordinary_effect
        self.assertEqual((effect.corner_moved, effect.corner_twisted, effect.edge_moved,
                          effect.edge_flipped), (0, 0, 3, 0))
        effect = bases["nested_comm_power1_D"].ordinary_effect
        self.assertEqual((effect.corner_moved, effect.edge_moved, effect.edge_flipped), (3, 0, 0))

    def test_custom_entries_verify_claims_and_retain_raw_words(self):
        entry = FamiliarAlgorithm.from_word(" R  R' ", id="cancellation")
        self.assertEqual(entry.word, "R R'")
        self.assertEqual(entry.htm, 2)
        self.assertTrue(entry.ordinary_effect.is_identity)
        with self.assertRaisesRegex(ValueError, "ordinary effect"):
            replace(entry, ordinary_effect=FamiliarAlgorithm.from_word("U").ordinary_effect)
        with self.assertRaisesRegex(ValueError, "HTM"):
            replace(entry, htm=0)
        custom = FamiliarAlgorithmCatalog([entry], [entry])
        self.assertEqual(custom.variants, (entry,))
        for word in ("r", "R3", "x", "M", "Rw", "R''"):
            with self.subTest(word=word), self.assertRaises(ValueError):
                FamiliarAlgorithm.from_word(word)


class WordObstructionTests(unittest.TestCase):
    def assert_native_match(self, specification, word):
        compiled = compile_word_obstruction(word)
        bits = shape_bond_bits(specification)
        try:
            endpoint = specification.apply(word)
        except c.BlockedMoveError:
            self.assertFalse(compiled.is_legal_bits(bits))
            self.assertIsNone(compiled.endpoint_bits(bits))
            self.assertFalse(compiled.is_closed_bits(bits))
        else:
            self.assertTrue(compiled.is_legal_bits(bits))
            self.assertEqual(compiled.endpoint_bits(bits), shape_bond_bits(endpoint))
            self.assertEqual(compiled.is_closed_bits(bits), endpoint == specification)

    def test_legality_closure_temporary_extraction_and_core_bonds(self):
        clock = fixture_pair(c.UR, c.R)
        self.assertFalse(clock.is_turnable("U"))
        closed = "R U R' D R U' R' D'"
        self.assert_native_match(clock, closed)
        self.assertTrue(compile_word_obstruction(closed).is_closed(clock))
        open_pair = fixture_pair(c.FR, c.DFR)
        self.assert_native_match(open_pair, "R U R' U'")
        self.assertFalse(compile_word_obstruction("R U R' U'").is_closed(open_pair))
        bicube = c.fixture("Bicube Fuse")
        self.assert_native_match(bicube, "U F2 U'")
        self.assert_native_match(bicube, "U F U'")
        core = fixture_pair(c.C, c.R)
        self.assertEqual(shape_bond_bits(core).bit_count(), 1)
        self.assert_native_match(core, "R")
        self.assert_native_match(core, "U")

    def test_raw_blocked_cancellation_is_not_simplified(self):
        locked = c.Shape([1] * 27)
        compiled = compile_word_obstruction("R R'")
        self.assertEqual(compiled.word, "R R'")
        self.assertFalse(compiled.is_legal(locked))
        self.assertFalse(compiled.is_closed(locked))
        self.assertTrue(compile_word_obstruction("").is_closed(locked))
        self.assertIs(compiled, compile_word_obstruction(" R  R' "))

    def test_word_powers_are_compiled_as_whole_words(self):
        pair = fixture_pair(c.UBL, c.UL)
        body = "R2 U2 R2 U2"
        self.assertTrue(compile_word_obstruction(body).is_legal(pair))
        self.assertFalse(compile_word_obstruction(body).is_closed(pair))
        self.assertFalse(compile_word_obstruction(" ".join([body] * 2)).is_closed(pair))
        self.assertTrue(compile_word_obstruction(" ".join([body] * 3)).is_closed(pair))

    def test_random_connected_partitions_match_native_replay(self):
        rng = random.Random(470)
        words = ("R", "R R'", "R U R' U'", "R U R' U' R U R' U'",
                 "R U R' D R U' R' D'", "R U R' U' R' F R2 U' R' U' R U R' F'")
        core_shapes = 0
        for probability in (0, .03, .1, .4):
            for _ in range(20):
                parent = list(range(27))

                def root(cell):
                    while cell != parent[cell]:
                        cell = parent[cell]
                    return cell

                for first, second in BONDS:
                    if rng.random() < probability:
                        parent[root(second)] = root(first)
                specification = c.Shape([root(cell) + 1 for cell in range(27)])
                core_shapes += any(specification[c.C] == specification[neighbor]
                                   for neighbor in (c.U, c.D, c.R, c.L, c.F, c.B))
                for word in words:
                    with self.subTest(probability=probability, shape=specification, word=word):
                        self.assert_native_match(specification, word)
        self.assertGreater(core_shapes, 0)

    def test_invalid_words_and_masks_are_rejected(self):
        for word in ("x", "M2", "U3", "F'2"):
            with self.subTest(word=word), self.assertRaises(ValueError):
                compile_word_obstruction(word)
        with self.assertRaises(TypeError):
            compile_word_obstruction(None)
        compiled = compile_word_obstruction("R")
        for bits in (-1, 1 << 54, True, "0"):
            with self.subTest(bits=bits), self.assertRaises((TypeError, ValueError)):
                compiled.endpoint_bits(bits)


if __name__ == "__main__":
    unittest.main()
