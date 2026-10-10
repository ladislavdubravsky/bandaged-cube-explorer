"""Witnessed dictionaries and exact generic cyclic orientation span."""

from collections import deque
from dataclasses import FrozenInstanceError, replace
import json
from random import Random
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.symbolic_dictionary import _coordinate_span, discover_symbolic_dictionary


def enumerated_span(vectors, orders):
    identity = tuple(0 for _ in orders)
    known, queue = {identity}, deque([identity])
    while queue:
        row = queue.popleft()
        for vector in vectors:
            successor = tuple((a+b) % modulus for a, b, modulus in zip(row, vector, orders))
            if successor not in known:
                known.add(successor)
                queue.append(successor)
    return len(known)


class OrientationCoordinateTests(unittest.TestCase):
    def test_prime_power_span_matches_independent_small_group_closure(self):
        rng = Random(41)
        for orders in ((2, 3, 4), (4, 4), (2, 4), (3, 9), (2, 4, 8), (6, 4)):
            for _ in range(25):
                vectors = [tuple(rng.randrange(m) for m in orders)
                           for _ in range(rng.randrange(5))]
                with self.subTest(orders=orders, vectors=vectors):
                    self.assertEqual(_coordinate_span(vectors, orders)[0],
                                     enumerated_span(vectors, orders))

    def test_order_four_carries_and_mixed_coordinate_orders_are_preserved(self):
        self.assertEqual(_coordinate_span(((2,),), (4,))[0], 2)
        self.assertEqual(_coordinate_span(((1,),), (4,))[0], 4)
        self.assertEqual(_coordinate_span(((1, 1),), (2, 4))[0], 4)
        self.assertEqual(_coordinate_span(((1, 1), (0, 1)), (2, 4))[0], 8)

    def test_budget_validation_precedes_external_work(self):
        with patch("subprocess.run", side_effect=AssertionError("invalid settings must not call GAP")):
            for option in ("max_candidates", "rounds", "max_seed_loops", "max_algorithms", "max_setup_depth",
                           "max_setup_words", "max_conjugates", "max_htm_length", "max_expanded_moves"):
                with self.subTest(option=option):
                    with self.assertRaises(TypeError):
                        discover_symbolic_dictionary(c.Shape(), **{option: True})
                    with self.assertRaises(ValueError):
                        discover_symbolic_dictionary(c.Shape(), **{option: -1})


@unittest.skipUnless(shutil.which("gap"), "GAP is required for exact dictionary target orders")
class SymbolicDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fused = discover_symbolic_dictionary(c.Shape([1] * 9 + [2] * 18),
                                                 max_candidates=0, max_conjugates=0, timeout=30)
        cls.classic = discover_symbolic_dictionary(
            c.Shape(), max_candidates=6000, rounds=3, max_algorithms=1024,
            max_conjugates=6000, timeout=30)

    def test_unbandaged_dictionary_closure_spans_actual_orientation_kernel(self):
        dictionary = self.classic
        metadata = dictionary.metadata
        self.assertEqual(metadata["group_order"], 43_252_003_274_489_856_000)
        self.assertEqual(metadata["orientation_target_order"], 4_478_976)
        self.assertEqual(metadata["orientation_span_order"], 4_478_976)
        self.assertTrue(metadata["orientation_complete"])
        self.assertTrue(metadata["orientation_basis_independent"])
        self.assertEqual(len(dictionary.orientation_basis), 18)
        self.assertLessEqual(metadata["mining"]["examined_count"], 6000)
        self.assertLessEqual(metadata["work"].get("conjugates_examined", 0), 6000)
        self.assertLessEqual(len(dictionary.algorithms), 1024)
        self.assertEqual(metadata["orientation_primary_spans"]["2"]["order"], 2048)
        self.assertEqual(metadata["orientation_primary_spans"]["3"]["order"], 2187)

    def test_rich_pool_retains_odd_original_moves_and_localized_permutation_families(self):
        dictionary = self.classic
        effects = {algorithm.permutation for algorithm in dictionary.algorithms}
        for generator in dictionary.generators:
            self.assertIn(generator.permutation, effects)
        for kind in ("Corner", "Edge"):
            self.assertTrue(any(not algorithm.is_kernel and len(algorithm.support) == 3
                                and {dictionary.inventory.blocks[i].kind
                                     for i in algorithm.support} == {kind}
                                for algorithm in dictionary.algorithms))
        self.assertGreater(len(dictionary.algorithms), len(dictionary.orientation_basis))

    def test_fused_face_order_four_uses_its_actual_coordinates(self):
        dictionary = self.fused
        self.assertEqual(dictionary.metadata["orientation_target_order"], 4)
        self.assertEqual(dictionary.metadata["orientation_span_order"], 4)
        self.assertTrue(dictionary.metadata["orientation_complete"])
        self.assertTrue(any(block.orientation_order == 4 for block in dictionary.inventory.blocks))
        self.assertEqual(len(dictionary.orientation_basis), 1)
        algorithm = dictionary.orientation_basis[0]
        orders = tuple(block.orientation_order for block in dictionary.inventory.blocks)
        self.assertEqual(_coordinate_span((algorithm.block_action.phases,), orders)[0], 4)
        squared = dictionary.inventory.action(c.LoopExpression.power(
            algorithm.expression, 2).evaluate(dictionary.generators))
        self.assertEqual(_coordinate_span((squared.phases,), orders)[0], 2)

    def test_replay_validation_and_export_use_only_matching_original_leaves_offline(self):
        with patch("subprocess.run", side_effect=AssertionError("dictionary validation runs offline")):
            self.assertIs(self.classic.validate(self.classic.inventory, self.classic.generators),
                          self.classic)
            self.assertEqual(json.loads(self.fused.to_json()), self.fused.to_dict())
            loaded = type(self.fused).from_dict(self.fused.to_dict())
            self.assertEqual(loaded.to_dict(), self.fused.to_dict())
        with self.assertRaises(FrozenInstanceError):
            self.fused.algorithms = ()
        metadata = self.fused.metadata
        metadata["orientation_span_order"] = 100
        self.assertEqual(self.fused.metadata["orientation_span_order"], 4)

    def test_corrupt_word_leaf_or_orientation_claim_is_rejected(self):
        dictionary = self.fused
        first = dictionary.algorithms[0]
        with self.assertRaises(ValueError):
            replace(dictionary, algorithms=(replace(first, turn_sequence=""),)).validate()
        bad_metadata = dictionary.metadata
        bad_metadata["orientation_span_order"] = 2
        with self.assertRaises(ValueError):
            replace(dictionary, _metadata_json=json.dumps(bad_metadata)).validate()
        broken = dictionary.to_dict()
        broken["algorithms"][0]["turn_sequence"] = ""
        with self.assertRaises(ValueError):
            type(dictionary).from_dict(broken)
        with self.assertRaises(ValueError):
            dictionary.validate(generators=tuple(reversed(dictionary.generators))) if len(
                dictionary.generators) > 1 else dictionary.validate(generators=())

    def test_restrictive_dictionary_cap_reports_incomplete_orientation_coverage(self):
        limited = discover_symbolic_dictionary(c.Shape(), max_candidates=0,
                                               max_conjugates=0, max_algorithms=1, timeout=30)
        self.assertFalse(limited.metadata["orientation_complete"])
        self.assertEqual(limited.metadata["orientation_span_order"], 1)
        self.assertGreater(limited.metadata["orientation_missing_index"], 1)
        self.assertEqual(limited.metadata["algorithm_count"], 1)


if __name__ == "__main__":
    unittest.main()
