"""Transported physical words influence stages and retain portable proofs."""

from dataclasses import replace
import json
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_methods import _expression_bound
from bce_v2.symbolic_dictionary import _proof_bound


class FamiliarDictionaryBudgetTests(unittest.TestCase):
    def test_new_limits_are_checked_before_external_work(self):
        with patch("subprocess.run", side_effect=AssertionError("invalid input runs offline")):
            for name in ("max_familiar_shapes", "max_familiar_setup_depth", "max_familiar_work",
                         "max_familiar_candidates", "max_proof_moves"):
                with self.subTest(name=name):
                    with self.assertRaises(TypeError):
                        c.discover_symbolic_dictionary(c.Shape(), **{name: True})
                    with self.assertRaises(ValueError):
                        c.discover_symbolic_dictionary(c.Shape(), **{name: -1})
            for value in (-1, float("inf"), float("nan")):
                with self.assertRaises(ValueError):
                    c.discover_symbolic_dictionary(c.Shape(), max_familiar_seconds=value)
            with self.assertRaises(TypeError):
                c.discover_symbolic_dictionary(c.Shape(), max_familiar_seconds=True)


@unittest.skipUnless(shutil.which("gap"), "GAP prepares exact dictionary orders")
class FamiliarDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([1] * 9 + [2] * 18)
        cls.analysis = c.analyze_isotropy(cls.shape, timeout=30)
        cls.dictionary = c.discover_symbolic_dictionary(
            cls.analysis, max_candidates=0, max_conjugates=0,
            max_familiar_candidates=0, timeout=30)

    def long_proof_dictionary(self):
        original = next(g for g in self.analysis.loops if g.turn_sequence == "U")
        witness = c.LoopExpression.sequence(
            c.LoopExpression.power(c.LoopExpression.loop(original.id), 400),
            c.LoopExpression.loop(original.id))
        expression = c.LoopExpression.turns("U", witness)
        algorithm = c.AlgorithmLibrary(self.analysis.loops, (), (), ()).build_algorithm(
            expression, max_expanded_moves=1, max_htm_length=1)
        metadata = self.dictionary.metadata
        metadata["settings"].update(max_expanded_moves=1, max_htm_length=1,
                                    max_proof_moves=1000)
        metadata.update(algorithm_count=1, orientation_basis_count=1,
                        orientation_basis_total_htm=1, orientation_basis_max_htm=1)
        return replace(self.dictionary, algorithms=(algorithm,), orientation_basis=(algorithm,),
                       _metadata_json=json.dumps(metadata)).validate()

    def test_execution_limit_is_independent_of_original_proof_and_reloads_offline(self):
        dictionary = self.long_proof_dictionary()
        algorithm = dictionary.algorithms[0]
        records = {g.id: g for g in dictionary.generators}
        self.assertEqual(_expression_bound(algorithm.expression, records), 1)
        self.assertEqual(_proof_bound(algorithm.expression, records), 401)
        with patch("subprocess.run", side_effect=AssertionError("portable loading needs no GAP")):
            loaded = c.SymbolicAlgorithmDictionary.from_dict(dictionary.to_dict())
            self.assertEqual(loaded.to_dict(), dictionary.to_dict())
            self.assertEqual(loaded.algorithms[0].turn_sequence, "U")

    def test_proof_bound_and_forged_literal_are_rejected(self):
        dictionary = self.long_proof_dictionary()
        record = dictionary.to_dict()
        record["metadata"]["settings"]["max_proof_moves"] = 400
        with self.assertRaisesRegex(ValueError, "proof bound"):
            c.SymbolicAlgorithmDictionary.from_dict(record)
        record = dictionary.to_dict()
        record["algorithms"][0]["expression"]["moves"] = ""
        with self.assertRaisesRegex(ValueError, "literal turns"):
            c.SymbolicAlgorithmDictionary.from_dict(record)
        original = dictionary.algorithms[0]
        forged = replace(original, expression=c.LoopExpression.turns(
            "U", c.LoopExpression.loop(1_000_000)))
        with self.assertRaisesRegex(ValueError, "unknown original loop ID"):
            replace(dictionary, algorithms=(forged,), orientation_basis=(forged,)).validate()

    def test_stage_improvement_admits_short_literal_with_long_proof(self):
        dictionary = self.long_proof_dictionary()
        baseline = c.synthesize_human_method(self.analysis, backend="symbolic", timeout=30)
        with patch("subprocess.run", side_effect=AssertionError("stage search uses saved proofs")):
            search = c.improve_human_method(
                baseline, dictionary=dictionary, max_candidates=16, max_states=16,
                max_expanded_moves=4, max_htm_length=4)
            self.assertEqual(search.metadata["attempted_by_source"]["shared_dictionary"], 1)
            self.assertEqual(search.metadata.get("dictionary_length_pruned", 0), 0)
            loaded = c.HumanMethod.from_dict(search.method.to_dict())
            for moves in ("", "U", "U2", "U'"):
                self.assertTrue(loaded.apply(c.State(self.shape).apply(moves)).state.is_solved)


@unittest.skipUnless(shutil.which("gap"), "GAP prepares exact dictionary orders")
class TransportedDictionaryTests(unittest.TestCase):
    def test_shape_changing_candidates_enter_dictionary_and_replay_after_offline_load(self):
        reference = c.Shape([0] * 9 + [1, 0, 2, 0, 0, 0, 3, 0, 4] * 2)
        analysis = c.analyze_isotropy(reference, timeout=30)
        dictionary = c.discover_symbolic_dictionary(
            analysis, max_candidates=0, rounds=0, max_conjugates=0, max_original_loops=0,
            max_familiar_shapes=32, max_familiar_setup_depth=1,
            max_familiar_work=20000, max_familiar_candidates=64,
            max_familiar_seconds=None, timeout=30)
        metadata = dictionary.metadata["familiar_transport"]
        self.assertTrue(metadata["dictionary_algorithm_ids"])
        algorithms = {algorithm.id: algorithm for algorithm in dictionary.algorithms}
        transported = [algorithms[identifier] for identifier in metadata["dictionary_algorithm_ids"]
                       if metadata["algorithms"][identifier]["setup"]]
        self.assertTrue(transported)
        for algorithm in transported:
            record = metadata["algorithms"][algorithm.id]
            setup = c.ShapePath.from_moves(reference, record["setup"])
            body = c.ShapePath.local_loop(setup.target_shape, record["body"])
            self.assertEqual(setup.transport_loop(body).permutation, algorithm.permutation)
        with patch("subprocess.run", side_effect=AssertionError("loading runs offline")):
            restored = c.SymbolicAlgorithmDictionary.from_dict(dictionary.to_dict())
            self.assertEqual(restored.to_dict(), dictionary.to_dict())
            for algorithm in restored.algorithms:
                replay = c.State(reference).apply(algorithm.turn_sequence)
                self.assertEqual(replay.shape, reference)
                self.assertEqual(replay.sticker_permutation, algorithm.permutation)


if __name__ == "__main__":
    unittest.main()
