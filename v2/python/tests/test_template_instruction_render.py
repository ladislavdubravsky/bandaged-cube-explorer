"""Template guides preserve named recipes across mixed physical grips."""

from types import SimpleNamespace
import re
import unittest

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.human_instruction_render import instruction_presentation
from bce_v2.human_repertoire_render import _guide_instructions
from bce_v2.loop_rotations import normalize_rotation, rotate_moves, rotate_permutation


R = c.HumanMacroRecipe


class TemplateInstructionRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loops = c.isotropy_loops(c.Shape())
        cls.macros = tuple(SimpleNamespace(
            id=f"M{index + 1}",
            algorithm=SimpleNamespace(
                expression=c.LoopExpression.loop(index),
                turn_sequence=c.LoopExpression.loop(index).expanded_moves(cls.loops),
            ),
        ) for index in range(2))
        cls.first, cls.second = R.macro("M1"), R.macro("M2")

    def test_mixed_grip_spelling_executes_the_original_instruction(self):
        recipe = R.sequence(R.rotated("x", self.first), R.rotated("z", self.second))
        shown = instruction_presentation(recipe, self.macros, preserve_templates=True)
        self.assertFalse(shown.requires_definition)
        self.assertEqual(shown.rotation, "")
        # Interpret the displayed regrips independently, using the taught
        # literal words rather than the serialized recipe tree.
        frame, moves = "", []
        records = {macro.id: macro.algorithm.turn_sequence for macro in self.macros}
        for token in re.findall(r"M[1-9][0-9]*|[xyz](?:2|')?", shown.identifier):
            if token in records:
                moves.extend(rotate_moves(records[token], frame).split())
            else:
                frame = normalize_rotation((frame + " " + token).strip())
        self.assertEqual(frame, "")
        self.assertEqual(_simplified_moves(moves), shown.turn_sequence)
        self.assertEqual(c.State().apply(shown.turn_sequence).sticker_permutation,
                         recipe.loop_expression(self.macros).evaluate(self.loops))

    def test_template_guides_teach_no_extra_algorithm_for_mixed_grips(self):
        recipe = R.rotated("x", R.sequence(R.rotated("y", self.first), self.second))
        repertoire = SimpleNamespace(
            macros=self.macros, metadata={"basis": "templates"},
            stages=(SimpleNamespace(
                cases=(SimpleNamespace(instruction=recipe),), rules=(),
            ),),
        )
        for rotate_diagram in (True, False):
            shown, additional = _guide_instructions(repertoire, rotate_diagram=rotate_diagram)
            self.assertEqual(additional, [])
            presentation = shown[recipe]
            self.assertIn("M1", presentation.identifier)
            self.assertIn("M2", presentation.identifier)
            local = c.State().apply(presentation.turn_sequence).sticker_permutation
            self.assertEqual(rotate_permutation(local, presentation.rotation),
                             recipe.loop_expression(self.macros).evaluate(self.loops))

    def test_common_starting_grip_keeps_the_simple_master_name(self):
        recipe = R.rotated("x y", R.power(self.first, -2))
        shown = instruction_presentation(recipe, self.macros, preserve_templates=True)
        self.assertEqual(shown.rotation, normalize_rotation("x y"))
        self.assertEqual(shown.identifier, "M1^-2")
        self.assertFalse(shown.requires_definition)
        self.assertEqual(rotate_permutation(c.State().apply(shown.turn_sequence).sticker_permutation,
                                            shown.rotation),
                         recipe.loop_expression(self.macros).evaluate(self.loops))

    def test_legacy_presentation_and_option_validation(self):
        recipe = R.sequence(R.rotated("x", self.first), self.second)
        self.assertTrue(instruction_presentation(recipe, self.macros).requires_definition)
        with self.assertRaises(TypeError):
            instruction_presentation(recipe, self.macros, preserve_templates=1)


if __name__ == "__main__":
    unittest.main()
