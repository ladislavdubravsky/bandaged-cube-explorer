"""The taught template vocabulary is the one used to choose complete policies."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_methods import _observe, _state_for_permutation, _then
from bce_v2.human_chunks import ChunkDictionary
from bce_v2.human_repertoire_render import _guide_instructions
from bce_v2.loop_rotations import rotate_moves
from bce_v2.template_human_repertoire import template_human_repertoire


POCKET = [1, 1, 2, 1, 1, 2, 3, 3, 0,
          0, 0, 4, 0, 0, 4, 5, 5, 6,
          0, 0, 4, 0, 0, 4, 5, 5, 6]
IDENTITY = tuple(range(48))


def recipe_nodes(recipe):
    yield recipe
    for child in recipe.children:
        yield from recipe_nodes(child)


def refingerprint(record):
    payload = {key: value for key, value in record.items() if key != "fingerprint"}
    record["fingerprint"] = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@unittest.skipUnless(shutil.which("gap"), "GAP prepares exact reference groups")
class TemplateHumanRepertoireSmallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.method = c.synthesize_human_method(c.Shape([1] * 9 + [2] * 18),
            strategy="fully_solve_each_block", max_group_elements=4, timeout=45)
        cls.trivial = c.synthesize_human_method(c.Shape([1] * 27), max_group_elements=1, timeout=45)
        cls.nonzero = c.synthesize_human_method(
            c.Shape([1, 1, 2, 1, 1, 2, 3, 3, 0] + [4] * 18), root=1,
            max_group_elements=1, timeout=45)
        cls.repertoire = template_human_repertoire(cls.method, max_trials=4,
            max_word_candidates=100, max_word_frontier=16)

    def test_portable_prepared_method_needs_no_gap_and_retains_its_chain(self):
        with patch("subprocess.run", side_effect=AssertionError("prepared methods require no GAP")):
            repertoire = template_human_repertoire(self.method, max_trials=0,
                max_applications=0, max_word_candidates=0)
            loaded = c.HumanRepertoire.from_dict(repertoire.to_dict())
            self.assertEqual(repertoire.to_json(), loaded.to_json())
            self.assertFalse(repertoire.metadata["settings"]["select_chain"])
            self.assertEqual(tuple(s.feature for s in repertoire.method.stages),
                             tuple(s.feature for s in self.method.stages))
            for permutation in sorted(self.method._permutations):
                state = _state_for_permutation(self.method.reference_shape, permutation)
                result = loaded.apply(state)
                self.assertTrue(result.state.is_solved)
                self.assertEqual(state.apply(result.turn_sequence), result.state)

    def test_zero_quality_budgets_keep_complete_additive_fallback(self):
        repertoire = template_human_repertoire(self.method, max_trials=0,
            max_applications=0, max_word_candidates=0, max_chain_expansions=0, max_chain_methods=0,
            chunk_options={"max_word_moves": 0})
        self.assertEqual(repertoire.metadata["search"]["physical_words_examined"], 0)
        self.assertEqual(len(repertoire.macros), 1)
        self.assertEqual(repertoire.metadata["chunk_dictionary"]["chunks"], [])
        self.assertEqual(c.HumanRepertoire.from_dict(repertoire.to_dict()).to_json(), repertoire.to_json())
        self.assertTrue(any(node.kind == "power" and abs(node.exponent) > 1
            for stage in repertoire.stages for case in stage.cases for node in recipe_nodes(case.recipe)))
        for move in ("", "U", "U2", "U'"):
            self.assertTrue(repertoire.apply(c.State(self.method.reference_shape).apply(move)).state.is_solved)

    def test_generator_free_and_nonzero_root_policies_reload(self):
        for source in (self.trivial, self.nonzero):
            with self.subTest(root=source.root_vertex):
                with patch("subprocess.run", side_effect=AssertionError("portable trivial methods require no GAP")):
                    repertoire = template_human_repertoire(source, root=source.root_vertex,
                        max_group_elements=1, max_word_candidates=0)
                    restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
                self.assertEqual(restored.method.root_vertex, source.root_vertex)
                self.assertEqual(restored.macros, ())
                self.assertEqual(restored.stages, ())
                self.assertTrue(restored.apply(c.State(source.reference_shape)).state.is_solved)

    def test_invalid_budgets_and_roots_fail_before_external_work(self):
        invalid = (({"max_trials": True}, TypeError), ({"max_trials": -1}, ValueError),
                   ({"max_applications": 1.5}, TypeError), ({"max_word_candidates": -1}, ValueError),
                   ({"max_word_frontier": 0}, ValueError), ({"beam_width": 0}, ValueError),
                   ({"max_chain_expansions": -1}, ValueError), ({"allow_symmetry": 1}, TypeError),
                   ({"select_chain": "yes"}, TypeError), ({"max_cost_ratio": True}, ValueError),
                   ({"max_cost_ratio": float("nan")}, ValueError), ({"preference": "speed"}, ValueError),
                   ({"chunk_options": {"unknown": 1}}, ValueError),
                   ({"chunk_options": {"max_chunks": True}}, TypeError),
                   ({"chunk_options": {"min_chunk_length": 1}}, ValueError),
                   ({"chunk_options": {"max_chunk_length": 1}}, ValueError),
                   ({"max_group_elements": True}, TypeError), ({"max_group_elements": 0}, ValueError),
                   ({"max_group_elements": 3}, ValueError), ({"root": True}, TypeError),
                   ({"root": 1}, ValueError), ({"templates": ("U",)}, TypeError))
        with patch("subprocess.run", side_effect=AssertionError("invalid options must fail before GAP")):
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    template_human_repertoire(self.method, **options)

    def test_saved_metadata_is_recomputed_even_with_a_new_fingerprint(self):
        changes = (
            lambda m: m.__setitem__("basis", "reduced_generators"),
            lambda m: m.__setitem__("physical_shortest_claim", True),
            lambda m: m.__setitem__("human_reviewed", True),
            lambda m: m["selected_metrics"].__setitem__("mean_htm", 0),
            lambda m: m["selected_metrics"].__setitem__("dictionary_score", 0),
            lambda m: m["baseline_metrics"].__setitem__("mean_htm", 0),
            lambda m: m["settings"].__setitem__("max_word_candidates", True),
            lambda m: m.__setitem__("rotations", []),
            lambda m: m.__setitem__("frontier", []),
            lambda m: m["chunk_dictionary"]["metrics"].__setitem__("score", 0),
            lambda m: m["baseline_chunk_dictionary"]["metrics"].__setitem__("score", 0),
            lambda m: m["baseline_chunk_dictionary"].__setitem__("masters", []),
        )
        with patch("subprocess.run", side_effect=AssertionError("portable verification requires no GAP")):
            for change in changes:
                record = deepcopy(self.repertoire.to_dict())
                change(record["metadata"])
                refingerprint(record)
                with self.assertRaises(ValueError):
                    c.HumanRepertoire.from_dict(record)

    def test_portable_loading_checks_grammars_without_rerunning_quality_mining(self):
        with patch("bce_v2.human_chunks.extract_algorithm_chunks",
                   side_effect=AssertionError("portable loading must not run quality search")):
            restored = c.HumanRepertoire.from_dict(self.repertoire.to_dict())
        self.assertEqual(restored.to_json(), self.repertoire.to_json())

    def test_optional_unsimplified_template_is_legally_replayed_then_normalized(self):
        generator = self.method.generators[0]
        proof = c.LoopExpression.power(c.LoopExpression.loop(generator.id), 2)
        # The fixture's generator is one U turn. The raw spelling remains a
        # legal witness, while portable learned words combine equal faces.
        self.assertEqual(generator.turn_sequence, "U")
        template = c.LoopAlgorithm("extra", proof, proof.evaluate(self.method.generators),
            "U U", self.method.inventory, tuple((g.id, g.htm_length) for g in self.method.generators),
            self.method.generators)
        repertoire = template_human_repertoire(self.method, templates=(template,),
            max_trials=0, max_applications=0, max_word_candidates=0)
        self.assertTrue(any(macro.algorithm.turn_sequence == "U2" for macro in repertoire.macros))
        self.assertEqual(c.HumanRepertoire.from_dict(repertoire.to_dict()).to_json(), repertoire.to_json())


@unittest.skipUnless(shutil.which("gap"), "GAP prepares the exact pocket group")
class TemplatePocketRepertoireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repertoire = template_human_repertoire(POCKET, max_group_elements=432, timeout=45,
            max_word_candidates=30000, max_word_frontier=1000, max_chain_expansions=3, max_chain_methods=4)
        cls.states = tuple(_state_for_permutation(cls.repertoire.method.reference_shape, p)
                           for p in sorted(cls.repertoire.method._permutations))

    def test_symmetries_reduce_templates_before_policies_are_compiled(self):
        repertoire = self.repertoire
        self.assertEqual(repertoire.metadata["basis"], "templates")
        self.assertEqual(repertoire.metadata["construction"], "symmetry_template_search")
        self.assertEqual(len(repertoire.method.generators), 3)
        self.assertEqual(len(repertoire.macros), 2)
        self.assertEqual(len(repertoire.metadata["rotations"]), 3)
        self.assertGreater(repertoire.metadata["search"]["accepted_deletions"], 0)
        self.assertTrue(any(node.kind == "rotated" for stage in repertoire.stages
                            for case in stage.cases for node in recipe_nodes(case.recipe)))
        for stage in repertoire.stages:
            for case in stage.cases:
                self.assertLessEqual(set(case.recipe.macro_ids), {m.id for m in repertoire.macros})
                self.assertEqual(case.next_observation, repertoire.method.stages[stage.number - 1].solved_observation)
                self.assertEqual(case.instruction, case.recipe if case.rank else None)
        dictionary = ChunkDictionary.from_dict(repertoire.metadata["chunk_dictionary"])
        self.assertGreater(len(dictionary.chunks), 0)
        for macro in repertoire.macros:
            self.assertEqual(dictionary.expand(macro.id), macro.algorithm.turn_sequence)

    def test_case_targets_correct_every_fiber_and_leave_later_features_free(self):
        repertoire, current = self.repertoire, self.repertoire.method._permutations
        actions = {p: repertoire.method.inventory.action(p) for p in current}
        free_later_effect = False
        for policy, stage in zip(repertoire.stages, repertoire.method.stages):
            target = frozenset(p for p in current
                if _observe(actions[p], stage.block_index, stage.feature.kind) == stage.solved_observation)
            for case in policy.cases:
                effect = case.recipe.loop_expression(repertoire.macros).evaluate(repertoire.method.generators)
                fiber = frozenset(p for p in current
                    if _observe(actions[p], stage.block_index, stage.feature.kind) == case.observation)
                with self.subTest(stage=stage.number, observation=case.observation):
                    self.assertIn(effect, current)
                    self.assertEqual(frozenset(_then(p, effect) for p in fiber), target)
                free_later_effect |= any(_then(p, effect) != IDENTITY for p in fiber)
            current = target
        self.assertEqual(current, frozenset((IDENTITY,)))
        self.assertTrue(free_later_effect)

    def test_all_432_reference_states_solve_after_portable_reload_without_gap(self):
        repertoire = self.repertoire
        with patch("subprocess.run", side_effect=AssertionError("loading and applying require no GAP")):
            loaded = c.HumanRepertoire.from_dict(repertoire.to_dict())
            self.assertEqual(loaded.to_json(), repertoire.to_json())
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "templates.json"
                repertoire.save(path)
                self.assertEqual(c.load_human_repertoire(path).to_json(), repertoire.to_json())
            totals, worst = [0, 0], [0, 0]
            self.assertEqual(len(self.states), 432)
            for index, state in enumerate(self.states):
                with self.subTest(element=index):
                    self.assertIsNone(state.scramble)
                    result = loaded.apply(state)
                    self.assertEqual(result.status, "solved")
                    self.assertTrue(result.state.is_solved)
                    self.assertEqual(state.apply(result.turn_sequence), result.state)
                    moves = result.turn_sequence.split()
                    for i, cost in enumerate((len(moves), sum(2 if m.endswith("2") else 1 for m in moves))):
                        totals[i] += cost
                        worst[i] = max(worst[i], cost)
                    for step in result.steps:
                        self.assertEqual(step.after, step.before.apply(step.turn_sequence))
                        self.assertEqual(step.rank_after, 0)
            measured = repertoire.metadata["selected_metrics"]
            self.assertEqual((measured["total_htm"], measured["total_qtm"], measured["worst_htm"], measured["worst_qtm"]),
                             (*totals, *worst))
            self.assertEqual(measured["mean_htm"], totals[0] / 432)

    def test_whole_method_guard_and_candidate_frontier_use_real_template_policies(self):
        metadata = self.repertoire.metadata
        self.assertLessEqual(metadata["selected_metrics"]["mean_htm"], metadata["baseline_metrics"]["mean_htm"])
        self.assertLessEqual(metadata["selected_metrics"]["worst_htm"], metadata["baseline_metrics"]["worst_htm"])
        self.assertLess(metadata["selected_metrics"]["mean_htm"], 115)
        self.assertIn(metadata["selected_id"], metadata["frontier"])
        self.assertEqual(metadata["candidates"][0]["source"], "exact_baseline")
        self.assertTrue(any(":placement_then_orientation:" in c["source"] for c in metadata["candidates"]))
        self.assertFalse(metadata["physical_shortest_claim"])
        self.assertFalse(metadata["exhaustive_repertoire_search"])
        self.assertFalse(metadata["human_reviewed"])

    def test_guide_teaches_selected_templates_and_shared_pieces_without_extra_case_definitions(self):
        repertoire = self.repertoire
        for rotate_diagram in (False, True):
            presentations, additional = _guide_instructions(repertoire, rotate_diagram=rotate_diagram)
            self.assertEqual(additional, [])
            for recipe, presentation in presentations.items():
                with self.subTest(diagrams=rotate_diagram, recipe=recipe.render()):
                    self.assertFalse(presentation.requires_definition)
                    self.assertIsNotNone(presentation.identifier)
                    self.assertEqual(set(presentation.recipe.macro_ids), set(recipe.macro_ids))
                    physical = rotate_moves(presentation.turn_sequence, presentation.rotation)
                    expected = recipe.loop_expression(repertoire.macros).evaluate(repertoire.method.generators)
                    replay = c.State(repertoire.method.reference_shape).apply(physical)
                    self.assertEqual(replay.shape, repertoire.method.reference_shape)
                    self.assertEqual(replay.sticker_permutation, expected)
        guide = repertoire.write_guide()
        self.assertNotIn("## Pieces", guide)
        self.assertLess(guide.index("### Shared piece recipes"), guide.index("| Piece | Turn sequence |"))
        self.assertNotIn("| `A1` |", guide)
        dictionary = ChunkDictionary.from_dict(repertoire.metadata["chunk_dictionary"])
        for macro in repertoire.macros:
            self.assertIn(dictionary.master_formulas[macro.id], guide)


if __name__ == "__main__":
    unittest.main()
