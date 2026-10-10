"""A globally identical sticker action does not erase a template's root type."""

import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_methods import _state_for_permutation
from bce_v2.template_human_repertoire import template_human_repertoire


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare the complete method")
class TemplateRootGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = c.Shape([1] * 9 + [2] * 18)
        cls.baseline = c.synthesize_human_method(cls.reference, max_group_elements=4, timeout=45)

    def test_optional_template_from_another_bandage_root_is_rejected_even_if_word_and_action_match(self):
        ordinary = c.discover_loop_algorithms(c.Shape(), rounds=0, max_seed_loops=1,
                                               max_candidates=1, max_algorithms=2)
        original = next(generator for generator in ordinary.loops if generator.turn_sequence == "U")
        outsider = ordinary.build_algorithm(c.LoopExpression.loop(original.id))
        self.assertNotEqual(outsider._inventory.root_shape, self.reference)
        self.assertIn(outsider.permutation, self.baseline._permutations)
        replay = c.State(self.reference).apply(outsider.turn_sequence)
        self.assertEqual(replay.shape, self.reference)
        self.assertEqual(replay.sticker_permutation, outsider.permutation)
        # Coincident local IDs and even faithful effects cannot retarget an
        # optional learned template without its exact bandage reference type.
        self.assertIn(original.id, {generator.id for generator in self.baseline.generators})
        with self.assertRaisesRegex(ValueError, "reference|root"):
            template_human_repertoire(self.baseline, templates=(outsider,), max_trials=0,
                                      max_applications=0, max_word_candidates=0,
                                      chunk_options={"max_chunks": 0})

    def test_nontrivial_nonzero_root_policy_reloads_and_solves_every_imported_state(self):
        baseline = c.synthesize_human_method(c.fixture("Bicube Fuse"), root=1,
                                             max_group_elements=60, timeout=45)
        self.assertEqual(baseline.root_vertex, 1)
        self.assertEqual(len(baseline._permutations), 60)
        with patch("subprocess.run", side_effect=AssertionError("prepared methods require no GAP")):
            repertoire = template_human_repertoire(
                baseline, root=1, max_trials=0, max_applications=0, max_word_candidates=0,
                chunk_options={"max_chunks": 0})
            restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
            self.assertEqual(restored.to_json(), repertoire.to_json())
            self.assertEqual(restored.method.root_vertex, 1)
            self.assertEqual(restored.method.reference_shape, baseline.reference_shape)
            self.assertTrue(restored.method.generators)
            for permutation in sorted(baseline._permutations):
                with self.subTest(permutation=permutation):
                    state = _state_for_permutation(baseline.reference_shape, permutation)
                    self.assertIsNone(state.scramble)
                    application = restored.apply(state)
                    self.assertEqual(application.status, "solved")
                    self.assertTrue(application.state.is_solved)
                    self.assertEqual(state.apply(application.turn_sequence), application.state)


if __name__ == "__main__":
    unittest.main()
