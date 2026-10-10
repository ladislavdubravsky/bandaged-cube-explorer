"""Shared phrases retain exact physical expansions and typed source guards."""

from copy import deepcopy
import unittest

from bce_v2 import Shape, State
from bce_v2._moves import _simplified_moves
from bce_v2.human_chunks import (
    AlgorithmChunk, ChunkDictionary, ChunkExpression, extract_algorithm_chunks,
)
from bce_v2.loop_rotations import rotate_moves
from bce_v2.shape_paths import ShapePath


POCKET = Shape([
    1, 1, 2, 1, 1, 2, 3, 3, 0,
    0, 0, 4, 0, 0, 4, 5, 5, 6,
    0, 0, 4, 0, 0, 4, 5, 5, 6,
])
K = "F' U L F U'"
P = "U F' L' F U'"
J = "R' F D' F' R"


def inverse(word):
    return " ".join(move if move.endswith("2") else move[:-1] if move.endswith("'")
                    else move + "'" for move in reversed(word.split()))


def nodes(expression):
    yield expression
    for child in expression.children:
        yield from nodes(child)


class SharedPocketChunkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rho_k = rotate_moves(K, "x y")
        setup = P + " U' R"
        cls.words = {"M1": K + " " + rho_k + " " + J,
                     "M2": P + " " + K + " " + rho_k,
                     "M3": setup + " B2 " + inverse(setup)}
        cls.dictionary = extract_algorithm_chunks(POCKET, cls.words)

    def test_mines_five_move_shared_paths_without_pocket_specific_rules(self):
        dictionary = self.dictionary
        self.assertEqual({chunk.moves for chunk in dictionary.chunks}, {K, P})
        self.assertEqual(dictionary.metrics["expanded_definition_moves"], 43)
        self.assertEqual(dictionary.metrics["dictionary_definition_moves"], 10)
        self.assertLess(dictionary.metrics["score"], 43)
        self.assertEqual(dictionary.metrics["regrip_count"], 2)
        self.assertIn("x y (C1) y' x'", dictionary.master_formulas["M1"])
        self.assertNotIn("rotate(", dictionary.master_formulas["M1"])
        for identifier, word in self.words.items():
            self.assertEqual(dictionary.expand(identifier), _simplified_moves(word.split()))
            replay = State(POCKET).apply(dictionary.expand(identifier))
            self.assertEqual(replay.shape, POCKET)

    def test_half_turn_boundary_preserves_shared_setup_and_remote_body(self):
        dictionary = self.dictionary
        local, = dictionary.local_loops
        self.assertEqual(local["master_id"], "M3")
        self.assertEqual(local["setup"].moves, "U F' L' F U2 R")
        self.assertEqual(local["body"].moves, "B2")
        self.assertTrue(local["body"].is_closed)
        self.assertNotEqual(local["body"].source_shape, POCKET)
        self.assertIn("C2 U' R", dictionary.master_formulas["M3"])
        master = dict(dictionary.masters)["M3"]
        self.assertEqual(master.path, local["setup"].transport_loop(local["body"]))

    def test_rotated_references_have_exact_distinct_source_instances(self):
        dictionary = self.dictionary
        references = [node for _, expression in dictionary.masters for node in nodes(expression)
                      if node.kind == "chunk"]
        self.assertTrue(any(reference.rotation for reference in references))
        for reference in references:
            definition = dictionary.definitions[reference.chunk_id]
            path = definition.instances[reference.instance]
            if reference.inverse:
                path = path.inverse()
            self.assertEqual(path.rotated(reference.rotation).reframed(""), reference.path)
        self.assertTrue(any(len(chunk.instances) > 1 for chunk in dictionary.chunks))

    def test_roundtrip_is_deterministic_and_replayed(self):
        dictionary = self.dictionary
        record = dictionary.to_dict()
        loaded = ChunkDictionary.from_dict(record)
        self.assertEqual(loaded, dictionary)
        self.assertEqual(loaded.to_dict(), record)
        reverse_input = extract_algorithm_chunks(POCKET, dict(reversed(list(self.words.items()))))
        self.assertEqual(reverse_input.to_dict(), record)

    def test_corruption_of_paths_references_frames_and_metrics_is_rejected(self):
        original = self.dictionary.to_dict()
        corruptions = []
        record = deepcopy(original)
        record["chunks"][0]["instances"][0]["permutation"] = list(range(48))
        corruptions.append(record)
        record = deepcopy(original)
        record["masters"][0]["expression"]["children"][0]["instance"] = 999
        corruptions.append(record)
        record = deepcopy(original)
        record["masters"][0]["expression"]["children"][0]["rotation"] = "x"
        corruptions.append(record)
        record = deepcopy(original)
        record["masters"][0]["expression"]["children"][0]["path"]["frame"] = "x"
        corruptions.append(record)
        record = deepcopy(original)
        record["metrics"]["score"] += 1
        corruptions.append(record)
        record = deepcopy(original)
        record["metrics"]["master_count"] = True
        corruptions.append(record)
        record = deepcopy(original)
        record["master_formulas"]["M3"] = "B2"
        corruptions.append(record)
        record = deepcopy(original)
        record["chunks"][0]["instances"].append(deepcopy(record["chunks"][0]["instances"][0]))
        corruptions.append(record)
        for key, value in (("max_chunks", 0), ("max_candidates", 0),
                           ("max_word_moves", 0), ("max_chunk_length", 3),
                           ("min_chunk_length", True)):
            record = deepcopy(original)
            record["search_limits"][key] = value
            corruptions.append(record)
        for index, record in enumerate(corruptions):
            with self.subTest(corruption=index), self.assertRaises((TypeError, ValueError)):
                ChunkDictionary.from_dict(record)


class GenericChunkTests(unittest.TestCase):
    def test_inverse_and_proper_regrip_phrases_reuse_one_definition(self):
        word = "R U F' L B"
        words = {"A": word, "B": inverse(word), "C": rotate_moves(word, "x"),
                 "D": rotate_moves(inverse(word), "y")}
        dictionary = extract_algorithm_chunks(Shape(), words, max_chunks=1)
        self.assertEqual(len(dictionary.chunks), 1)
        self.assertEqual(len(dictionary.chunks[0].moves.split()), 5)
        references = [node for _, expression in dictionary.masters for node in nodes(expression)
                      if node.kind == "chunk"]
        self.assertEqual(len(references), 4)
        self.assertTrue(any(reference.inverse for reference in references))
        self.assertTrue(any(reference.rotation for reference in references))
        for identifier, word in words.items():
            self.assertEqual(dictionary.expand(identifier), word)
        self.assertEqual(ChunkDictionary.from_dict(dictionary.to_dict()), dictionary)

    def test_source_guard_prevents_using_an_open_phrase_at_another_shape(self):
        path = ShapePath.from_moves(POCKET, K)
        definition = AlgorithmChunk("C", K, (path,))
        other = ShapePath.from_moves(Shape(), K)
        reference = ChunkExpression("chunk", other, chunk_id="C", instance=0)
        with self.assertRaisesRegex(ValueError, "guard"):
            ChunkDictionary(Shape(), (definition,), (("M", reference),))

    def test_transport_rejects_an_open_body_and_mismatched_endpoints(self):
        setup = ShapePath.from_moves(POCKET, "F'")
        body = ShapePath.from_moves(setup.target_shape, "U")
        self.assertFalse(body.is_closed)
        with self.assertRaisesRegex(ValueError, "closed local loop"):
            ChunkExpression("transport", setup,
                            (ChunkExpression("literal", setup), ChunkExpression("literal", body)))
        with self.assertRaisesRegex(ValueError, "endpoint"):
            ChunkExpression("sequence", path=setup,
                            children=(ChunkExpression("literal", setup), ChunkExpression("literal", setup)))

    def test_finite_budgets_retain_complete_literal_fallback(self):
        word = "R U F' L B"
        for budget in ({"max_chunks": 0}, {"max_candidates": 0}, {"max_word_moves": 4}):
            with self.subTest(budget=budget):
                dictionary = extract_algorithm_chunks(Shape(), {"A": word, "B": word}, **budget)
                self.assertEqual(dictionary.chunks, ())
                self.assertEqual(dictionary.expand("A"), word)
                self.assertEqual(dictionary.metrics["score"], 10)
        empty = extract_algorithm_chunks(Shape(), {})
        self.assertEqual(empty.metrics["score"], 0)
        self.assertEqual(ChunkDictionary.from_dict(empty.to_dict()), empty)

    def test_illegal_canceling_input_cannot_hide_behind_literal_fallback(self):
        with self.assertRaisesRegex(ValueError, "blocked"):
            extract_algorithm_chunks(Shape([1] * 27), {"M": "R R'"}, max_chunks=0)

    def test_input_and_budget_validation(self):
        for options, error in (({"max_chunks": True}, TypeError),
                               ({"max_candidates": -1}, ValueError),
                               ({"max_word_moves": 1.5}, TypeError),
                               ({"min_chunk_length": 9, "max_chunk_length": 8}, ValueError)):
            with self.subTest(options=options), self.assertRaises(error):
                extract_algorithm_chunks(Shape(), {}, **options)
        with self.assertRaises(ValueError):
            extract_algorithm_chunks(Shape(), {"bad id": "R"})
        with self.assertRaises(ValueError):
            extract_algorithm_chunks(Shape(), {"M": "x R"})
        with self.assertRaises(KeyError):
            extract_algorithm_chunks(Shape(), {}).expand("missing")

    def test_frozen_dictionary_copies_mutable_pair_inputs(self):
        entry = ["M", ChunkExpression("literal", ShapePath.identity(Shape()))]
        dictionary = ChunkDictionary(Shape(), (), (entry,))
        entry[0] = "changed"
        self.assertEqual(dictionary.master_formulas, {"M": "()"})
        self.assertIsInstance(dictionary.masters[0], tuple)

    def test_total_corpus_budget_retains_additional_masters_literally(self):
        word = "R U F' L B"
        words = {f"A{index:02d}": word for index in range(30)}
        dictionary = extract_algorithm_chunks(Shape(), words, max_candidates=4)
        self.assertTrue(dictionary.chunks)
        literal_masters = [identifier for identifier, expression in dictionary.masters
                           if expression.kind == "literal"]
        self.assertTrue(literal_masters)
        self.assertEqual(len(dictionary.masters), 30)
        for identifier in words:
            self.assertEqual(dictionary.expand(identifier), word)
        self.assertEqual(ChunkDictionary.from_dict(dictionary.to_dict()), dictionary)


if __name__ == "__main__":
    unittest.main()
