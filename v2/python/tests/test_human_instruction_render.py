"""Diagram-frame instructions retain exact physical actions and named words."""

from copy import deepcopy
from types import SimpleNamespace
import unittest

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.human_instruction_render import instruction_presentation
from bce_v2.loop_rotations import normalize_rotation, rotate_moves, rotate_permutation


R = c.HumanMacroRecipe


class HumanInstructionPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Real native ordinary-cube loop witnesses avoid a solver or GAP call.
        cls.loops = c.isotropy_loops(c.Shape())
        first = c.LoopExpression.sequence(c.LoopExpression.loop(1), c.LoopExpression.loop(0),
                                           c.LoopExpression.power(c.LoopExpression.loop(1), -1))
        second = c.LoopExpression.sequence(c.LoopExpression.power(c.LoopExpression.loop(2), 2),
                                            c.LoopExpression.loop(3),
                                            c.LoopExpression.power(c.LoopExpression.loop(5), -1))
        cls.macros = tuple(SimpleNamespace(id=identifier, algorithm=SimpleNamespace(
            expression=expression, turn_sequence=expression.expanded_moves(cls.loops)))
            for identifier, expression in (("M1", first), ("M2", second)))
        cls.repertoire = SimpleNamespace(macros=cls.macros)
        cls.first, cls.second = R.macro("M1"), R.macro("M2")
        cls.rotations = ("",) + c.bandage_symmetries(c.Shape())

    def assert_exact_action(self, recipe, presentation):
        original = recipe.loop_expression(self.macros).evaluate(self.loops)
        local = c.State().apply(presentation.turn_sequence).sticker_permutation
        self.assertEqual(rotate_permutation(local, presentation.rotation), original)
        self.assertTrue(all(move[0] in "URFDLB" for move in presentation.turn_sequence.split()))

    def test_unrotated_macro_inverse_and_complete_power_keep_named_physical_words(self):
        for exponent in (1, -1, 2, -3):
            recipe = R.power(self.first, exponent)
            shown = instruction_presentation(recipe, self.repertoire)
            self.assertEqual(shown.rotation, "")
            self.assertEqual(shown.identifier, recipe.render())
            self.assertFalse(shown.requires_definition)
            self.assertEqual(shown.turn_sequence,
                             recipe.loop_expression(self.macros).expanded_moves(self.loops))
            self.assert_exact_action(recipe, shown)

    def test_each_of_24_starting_frames_executes_the_original_whole_instruction(self):
        for rotation in self.rotations:
            for exponent in (1, -1, 2):
                with self.subTest(rotation=rotation, exponent=exponent):
                    body = R.power(self.first, exponent)
                    recipe = R.rotated(rotation, body)
                    shown = instruction_presentation(recipe, self.repertoire)
                    self.assertEqual(shown.rotation, rotation)
                    self.assertEqual(shown.identifier, body.render())
                    self.assertFalse(shown.requires_definition)
                    self.assertEqual(shown.turn_sequence,
                                     body.loop_expression(self.macros).expanded_moves(self.loops))
                    self.assert_exact_action(recipe, shown)

    def test_nested_noncommuting_regrips_have_the_correct_composed_starting_frame(self):
        for outer in self.rotations:
            for inner in self.rotations:
                with self.subTest(outer=outer, inner=inner):
                    recipe = R.rotated(outer, R.power(R.rotated(inner, self.first), -1))
                    shown = instruction_presentation(recipe, self.repertoire)
                    self.assertEqual(shown.rotation, normalize_rotation((outer + " " + inner).strip()))
                    self.assertEqual(shown.identifier, self.first.render() + "^-1")
                    self.assertFalse(shown.requires_definition)
                    self.assert_exact_action(recipe, shown)
        self.assertNotEqual(normalize_rotation("x y"), normalize_rotation("y x"))

    def test_common_frames_factor_across_sequences_conjugates_and_commutators(self):
        for constructor in (R.sequence, R.conjugate, R.commutator):
            for rotation in self.rotations:
                with self.subTest(kind=constructor.__name__, rotation=rotation):
                    recipe = constructor(R.rotated(rotation, self.first),
                                         R.power(R.rotated(rotation, self.second), -1))
                    shown = instruction_presentation(recipe, self.repertoire)
                    expected = constructor(self.first, R.power(self.second, -1))
                    self.assertEqual(shown.rotation, rotation)
                    self.assertEqual(shown.recipe, expected)
                    self.assertEqual(shown.identifier, expected.render())
                    self.assertFalse(shown.requires_definition)
                    self.assert_exact_action(recipe, shown)

    def test_mixed_frames_need_a_named_exact_local_definition_without_splitting(self):
        body = R.conjugate(R.rotated("y", self.first), self.second)
        recipe = R.power(R.rotated("x", body), -2)
        shown = instruction_presentation(recipe, self.repertoire)
        self.assertEqual(shown.rotation, "x")
        self.assertIsNone(shown.identifier)
        self.assertTrue(shown.requires_definition)
        self.assert_exact_action(recipe, shown)
        # The presentation remains one whole setup/body/undo instruction,
        # even though its named masters require different local face maps.
        expected = body.loop_expression(self.macros)
        expected = c.LoopExpression.power(expected, -2).expanded_moves(self.loops)
        self.assertEqual(shown.turn_sequence, expected)
        mixed = R.sequence(R.rotated("x", self.first), R.rotated("z", self.second))
        reference = instruction_presentation(mixed, self.repertoire)
        self.assertEqual(reference.rotation, "")
        self.assertTrue(reference.requires_definition)
        self.assert_exact_action(mixed, reference)

    def test_text_instructions_remain_in_reference_frame_and_can_define_adapted_words(self):
        recipe = R.rotated("x y", R.power(self.second, -1))
        shown = instruction_presentation(recipe, self.repertoire, rotate_diagram=False)
        self.assertEqual(shown.rotation, "")
        self.assertTrue(shown.requires_definition)
        expected = recipe.loop_expression(self.macros).expanded_moves(self.loops)
        self.assertEqual(shown.turn_sequence, expected)
        self.assert_exact_action(recipe, shown)
        diagram = instruction_presentation(recipe, {macro.id: macro for macro in self.macros})
        self.assertEqual(_simplified_moves(rotate_moves(diagram.turn_sequence, diagram.rotation).split()),
                         expected)

    def test_presentation_keeps_serialized_solver_recipes_and_macro_records_unchanged(self):
        recipe = R.rotated("x", R.commutator(R.power(self.first, -1), self.second))
        saved = deepcopy(recipe.to_dict())
        words = tuple(macro.algorithm.turn_sequence for macro in self.macros)
        shown = instruction_presentation(recipe, self.macros)
        self.assertEqual(recipe.to_dict(), saved)
        self.assertEqual(tuple(macro.algorithm.turn_sequence for macro in self.macros), words)
        self.assertNotIn("rotate(", shown.identifier)
        self.assert_exact_action(recipe, shown)

    def test_input_errors_and_expansion_budget_are_checked_before_large_repetitions(self):
        invalid = (({"rotate_diagram": 1}, TypeError),
                   ({"max_expanded_moves": True}, TypeError),
                   ({"max_expanded_moves": 1.0}, TypeError),
                   ({"max_expanded_moves": 0}, ValueError))
        for options, error in invalid:
            with self.subTest(options=options), self.assertRaises(error):
                instruction_presentation(self.first, self.macros, **options)
        with self.assertRaises(TypeError):
            instruction_presentation(None, self.macros)
        with self.assertRaises(TypeError):
            instruction_presentation(self.first, None)
        with self.assertRaises(ValueError):
            instruction_presentation(R.macro("missing"), self.macros)
        with self.assertRaises(ValueError):
            instruction_presentation(R.power(self.first, 10**12), self.macros)
        with self.assertRaises(ValueError):
            instruction_presentation(self.first, self.macros, max_expanded_moves=2)
        zero = instruction_presentation(R.power(self.first, 0), self.macros)
        self.assertEqual(zero.turn_sequence, "")
        self.assert_exact_action(R.power(self.first, 0), zero)
        zero_rotated = instruction_presentation(R.power(R.rotated("x", self.first), 0), self.macros)
        self.assertFalse(zero_rotated.requires_definition)
        self.assertEqual(zero_rotated.rotation, "")
        self.assertEqual(zero_rotated.turn_sequence, "")


if __name__ == "__main__":
    unittest.main()
