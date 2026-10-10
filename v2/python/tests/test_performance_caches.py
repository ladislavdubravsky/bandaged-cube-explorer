"""Immutable cache reuse, budget accounting and independent import checks."""

from dataclasses import replace
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.isotropy import LoopGenerators
from bce_v2.loop_algorithms import _loops_from_records, _records
from bce_v2.computation import Computation, OptimizationBudgetExceeded
from bce_v2.human_repertoire import _build_algorithm


class CountingOwner:
    def __init__(self, native):
        self.native = native
        self.reads = 0

    def __getattr__(self, name):
        return getattr(self.native, name)

    def generator_moves(self, identifier):
        self.reads += 1
        return self.native.generator_moves(identifier)


class ImmutableWitnessCacheTests(unittest.TestCase):
    def test_native_words_lengths_actions_and_id_map_are_shared(self):
        owner = CountingOwner(c.isotropy_loops(c.fixture("Alcatraz"))._native)
        loops = LoopGenerators(owner)
        generator = loops.generators[0]
        word = generator.moves
        for _ in range(5):
            self.assertEqual(generator.moves, word)
            self.assertEqual(generator.htm_length, len(generator.turn_sequence.split()))
            self.assertIs(generator.block_action, generator.block_action)
        self.assertEqual(owner.reads, 1)
        self.assertIs(_records(loops), _records(loops))
        self.assertIs(_loops_from_records(loops.generators), loops)
        with self.assertRaises(TypeError):
            loops.generator_records[generator.id] = generator

    def test_builder_reuses_literal_proof_but_keeps_per_call_bounds(self):
        loops = c.isotropy_loops(c.Shape())
        library = c.AlgorithmLibrary(loops, (), (), ())
        by_word = {generator.turn_sequence: generator for generator in loops}
        witness = c.LoopExpression.sequence(*(c.LoopExpression.loop(by_word[move].id)
                                              for move in ("R", "U")))
        literal = c.LoopExpression.turns("R U", witness)
        apply = c.State.apply
        calls = []

        def counted(state, word):
            calls.append(word)
            return apply(state, word)

        with patch.object(c.State, "apply", counted):
            first = library.build_algorithm(literal, max_expanded_moves=20)
            second = library.build_algorithm(literal, max_expanded_moves=20)
            self.assertEqual(first, second)
            self.assertEqual(calls, ["R U"])
            with self.assertRaisesRegex(ValueError, "max_expanded_moves"):
                library.build_algorithm(literal, max_expanded_moves=1)
        self.assertIs(first.block_action, first.block_action)
        self.assertIs(first.block_action, loops.block_inventory.action(first.permutation))

    def test_witness_replay_cache_is_cold_for_a_new_owner(self):
        loops = c.isotropy_loops(c.Shape())
        loops.validate_witnesses()
        with patch.object(c.State, "apply", side_effect=AssertionError("already verified")):
            self.assertIs(loops.validate_witnesses(), loops)
        fresh = LoopGenerators(loops._native)
        apply = c.State.apply
        calls = []

        def counted(state, word):
            calls.append(word)
            return apply(state, word)

        with patch.object(c.State, "apply", counted):
            fresh.validate_witnesses()
        self.assertEqual(len(calls), len(fresh))

    def test_cached_action_still_rejects_boolean_images(self):
        inventory = c.BlockInventory(c.Shape())
        images = list(range(48))
        inventory.action(images)
        images[0] = False
        with self.assertRaises(TypeError):
            inventory.action(images)

    def test_replaced_records_cannot_reuse_a_literal_certificate(self):
        loops = c.isotropy_loops(c.Shape())
        by_word = {generator.turn_sequence: generator for generator in loops}
        right = by_word["R"]
        literal = c.LoopExpression.turns("R", c.LoopExpression.loop(right.id))
        library = c.AlgorithmLibrary(loops, (), (), ())
        library.build_algorithm(literal)
        replaced = tuple(replace(generator, permutation=by_word["U"].permutation)
                         if generator.id == right.id else generator for generator in loops)
        with self.assertRaisesRegex(ValueError, "do not match"):
            literal.expanded_moves(replaced)

    def test_repertoire_recipes_reuse_owner_and_exact_length_table(self):
        loops = c.isotropy_loops(c.Shape())
        right = next(generator for generator in loops if generator.turn_sequence == "R")
        literal = c.LoopExpression.turns("R", c.LoopExpression.loop(right.id))
        original = c.AlgorithmLibrary(loops, (), (), ()).build_algorithm(literal)
        macro = c.HumanRepertoireMacro("M1", replace(original, id="M1"))
        recipe = c.HumanMacroRecipe.macro("M1")
        method = SimpleNamespace(generators=loops.generators, inventory=loops.block_inventory)
        with patch.object(LoopGenerators, "__init__", side_effect=AssertionError("reuse owner")), patch.object(
                c.State, "apply", side_effect=AssertionError("reuse verified literal")):
            first = _build_algorithm(recipe, (macro,), method, "A1")
            second = _build_algorithm(recipe, (macro,), method, "A2")
        self.assertIs(first._leaf_htm_lengths, loops.generator_htm_lengths)
        self.assertIs(second._leaf_htm_lengths, first._leaf_htm_lengths)
        # A reduced method cannot silently acquire another native owner's leaf.
        reduced = SimpleNamespace(generators=(right,), inventory=loops.block_inventory)
        up = next(generator for generator in loops if generator.turn_sequence == "U")
        outside = c.HumanRepertoireMacro("M2", c.AlgorithmLibrary(loops, (), (), ()).build_algorithm(
            c.LoopExpression.loop(up.id)))
        with self.assertRaisesRegex(ValueError, "unknown original loop IDs"):
            _build_algorithm(c.HumanMacroRecipe.macro("M2"), (outside,), reduced, "A3")


@unittest.skipUnless(shutil.which("gap"), "GAP is required for exact dictionary orders")
class BoundedDictionaryCacheTests(unittest.TestCase):
    def test_large_original_alphabet_keeps_provenance_and_bounds_admission(self):
        analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=30)
        dictionary = c.discover_symbolic_dictionary(
            analysis, max_candidates=36, rounds=1, max_seed_loops=8,
            max_original_loops=2, max_algorithms=32,
            max_setup_words=2, max_conjugates=0, timeout=30)
        metadata = dictionary.metadata
        self.assertIs(dictionary.generators, analysis.loops.generators)
        self.assertLessEqual(metadata["physical_original_loop_count"], len(analysis.generators) + 2)
        self.assertLessEqual(metadata["candidate_count"], 36)
        self.assertTrue(metadata["original_admission_limit_reached"])
        self.assertEqual(metadata["candidate_count"],
                         metadata["work"]["original_proposals_examined"] +
                         (0 if metadata["mining"] is None else metadata["mining"]["examined_count"]))
        with patch.object(c.State, "apply", side_effect=AssertionError("already verified")):
            self.assertIs(dictionary.validate(), dictionary)
        first = dictionary.algorithms[0]
        with self.assertRaises(ValueError):
            replace(dictionary, algorithms=(replace(first, turn_sequence=""),)).validate()
        broken = dictionary.to_dict()
        broken["generators"][0]["moves"] = ""
        with self.assertRaises(ValueError):
            c.SymbolicAlgorithmDictionary.from_dict(broken, initial=analysis)

    def test_zero_mining_budget_retains_bounded_physical_baseline(self):
        dictionary = c.discover_symbolic_dictionary(
            c.Shape([1] * 9 + [2] * 18), max_candidates=0,
            max_original_loops=0, max_conjugates=0, timeout=30)
        self.assertEqual(dictionary.metadata["physical_original_loop_count"], 1)
        self.assertEqual(dictionary.metadata["candidate_count"], 3)
        self.assertTrue(dictionary.metadata["orientation_complete"])

    def test_algorithm_search_uses_shared_work_budget_and_retains_certified_baseline(self):
        reference = c.Shape([1] * 9 + [2] * 18)
        for backend in ("explicit", "symbolic"):
            with self.subTest(backend=backend):
                baseline = c.synthesize_human_method(reference, backend=backend, timeout=30)
                events = []
                context = Computation(max_optimization_work=0, progress=events.append)
                with context.activate(), patch("subprocess.run", side_effect=AssertionError("offline search")):
                    with self.assertRaises(OptimizationBudgetExceeded):
                        c.improve_human_method(baseline, max_candidates=32)
                self.assertEqual(context.best_method.to_dict(), baseline.to_dict())
                self.assertEqual(context.best_method.coverage, "certified")
                self.assertEqual(context.work, 0)
                self.assertTrue(any(event["phase"] == "algorithm_improvement" and
                                    event["status"] == "started" for event in events))

    def test_portable_repertoire_cannot_reuse_a_changed_literal_proof(self):
        reference = c.Shape([1] * 9 + [2] * 18)
        method = c.synthesize_human_method(reference, backend="symbolic", timeout=30)
        repertoire = c.template_human_repertoire(
            method, allow_symmetry=False, max_trials=0, max_applications=0,
            max_word_candidates=0, max_chain_expansions=0, max_chain_methods=0)
        record = repertoire.to_dict()
        item = record["macros"][0]
        witness = repertoire.macros[0].algorithm.expression
        item["expression"] = c.LoopExpression.turns("U2", witness).to_dict()
        from bce_v2.human_method_io import _fingerprint
        record["fingerprint"] = _fingerprint(record)
        with self.assertRaisesRegex(ValueError, "do not match"):
            c.HumanRepertoire.from_dict(record)


if __name__ == "__main__":
    unittest.main()
