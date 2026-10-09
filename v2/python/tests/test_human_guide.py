"""User-facing guides put executable words first and keep audit data portable."""

import importlib.util
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.loop_rotations import inverse_rotation, rotate_moves, rotate_permutation


RESULTS = Path(__file__).resolve().parents[2] / "research-results"
HAS_PLOTS = importlib.util.find_spec("matplotlib") is not None


class HumanGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repertoire = c.load_human_repertoire(RESULTS / "alcatraz-execution-repertoire.json")

    def assert_algorithms_first(self, guide, algorithms):
        self.assertEqual(guide.count("## Algorithms\n"), 1)
        self.assertLess(guide.index("## Algorithms\n"), guide.index("## Stage 1:"))
        definitions = guide[:guide.index("## Stage 1:")]
        self.assertEqual(definitions.count("| Turn sequence | Block action | Structure |"), 1)
        for algorithm in algorithms:
            self.assertIn(f"| `{algorithm.id}: {algorithm.turn_sequence}` | "
                          f"`{algorithm.block_action.notation}` | "
                          f"`{c.structured_move_notation(algorithm.turn_sequence)}` |", definitions)
        for removed in ("HTM", "QTM", "Witness provenance", "Original loop definitions",
                        "Expression:", "Shared master definitions", "Shared correction algorithms",
                        "Before starting", "Recognition colors", "Match the footprint",
                        "Restore the reference bandage shape first", "Hold the cube as pictured"):
            self.assertNotIn(removed, guide)

    def test_repertoire_all_words_are_up_front_and_portable_audit_data_is_unchanged(self):
        before = self.repertoire.to_dict()
        guide = self.repertoire.write_guide()
        self.assert_algorithms_first(guide, tuple(macro.algorithm for macro in self.repertoire.macros))
        self.assertIn("### Complete cue lookup", guide)
        for policy in self.repertoire.stages:
            for case in policy.cases:
                if case.instruction is not None:
                    word = case.instruction.loop_expression(self.repertoire.macros).expanded_moves(
                        self.repertoire.method.generators)
                    self.assertIn(f": {word}`", guide)
        self.assertEqual(before, self.repertoire.to_dict())
        self.assertTrue(all("expression" in macro for macro in before["macros"]))

    def test_expanded_method_all_words_are_up_front_without_generating_loop_appendix(self):
        method = self.repertoire.method
        before = method.to_dict()
        guide = method.write_guide()
        self.assert_algorithms_first(guide, method.algorithms)
        for stage in method.stages:
            for case in stage.cases:
                if case.algorithm_id is not None:
                    algorithm = next(algorithm for algorithm in method.algorithms
                                     if algorithm.id == case.algorithm_id)
                    self.assertIn(f"`{case.algorithm_id}: {algorithm.turn_sequence}`", guide)
        self.assertEqual(before, method.to_dict())
        self.assertTrue(all("expression" in algorithm for algorithm in before["algorithms"]))

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_visual_guide_passes_user_palette_to_every_case_without_repeating_color_instructions(self):
        from bce_v2.human_diagram_render import validate_face_colors
        palette = {"U": "purple", "F": "#00ffff"}
        normalized = validate_face_colors(palette)
        with patch("bce_v2.human_diagram_render.recognition_diagram_image",
                   return_value="data:image/png;base64,example") as draw:
            guide = self.repertoire.write_guide(diagram_mode=c.DiagramMode.OPPOSITE_CORNERS,
                                                face_colors=palette)
        self.assertEqual(draw.call_count, sum(len(stage.cases) for stage in self.repertoire.stages))
        for call in draw.call_args_list:
            self.assertEqual(call.kwargs["diagram_mode"], c.DiagramMode.OPPOSITE_CORNERS)
            self.assertEqual(call.kwargs["face_colors"], normalized)
            self.assertIn("rotation", call.kwargs)
        self.assertNotIn("Light face colors", guide)
        self.assertNotIn("normal intensity", guide)
        self.assertNotIn("including correctly placed blocks", guide)
        self.assertNotIn("Dark face colors", guide)
        self.assertNotIn("Grey marks", guide)
        self.assertNotIn("light block", guide)
        self.assert_algorithms_first(guide, tuple(macro.algorithm for macro in self.repertoire.macros))

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_every_case_word_in_the_diagram_frame_matches_its_checked_physical_instruction(self):
        with patch("bce_v2.human_diagram_render.recognition_diagram_image",
                   return_value="data:image/png;base64,example") as draw:
            guide = self.repertoire.write_guide(diagram_mode=c.DiagramMode.TRANSPARENT)
        instructions = iter(re.findall(r"Execute `([^`]+): ([^`]*)`\.", guide))
        cases = [case for stage in self.repertoire.stages for case in stage.cases]
        for case, call in zip(cases, draw.call_args_list):
            frame = call.kwargs["rotation"]
            if case.instruction is None:
                self.assertEqual(frame, "")
                continue
            identifier, word = next(instructions)
            expected = case.instruction.loop_expression(self.repertoire.macros).expanded_moves(
                self.repertoire.method.generators)
            self.assertEqual(word, _simplified_moves(rotate_moves(expected, inverse_rotation(frame)).split()))
            action = c.State().apply(word).sticker_permutation
            self.assertEqual(rotate_permutation(action, frame),
                             case.instruction.loop_expression(self.repertoire.macros).evaluate(
                                 self.repertoire.method.generators))
            self.assertNotIn("rotate(", identifier)
            self.assertNotIn("conj(", identifier)
        self.assertIsNone(next(instructions, None))
        self.assertNotIn("then inspect again", guide)
        self.assertNotIn("undo the regrip", guide)
        self.assertNotIn("rotate(", guide)
        self.assertIn("S^A", guide)
        self.assertNotIn("Hold the cube as pictured", guide)

    def test_mixed_frames_get_named_definitions_with_matching_local_block_actions(self):
        from bce_v2.human_render import _algorithm_table
        from bce_v2.human_repertoire_render import _additional_algorithm_action, _guide_instructions

        # The ordinary cube allows these differently rotated physical words.
        # Alcatraz's asymmetric bandage does not admit arbitrary regrips as
        # new loops, so use genuine ordinary-cube witnesses for this case.
        loops = c.isotropy_loops(c.Shape())
        expressions = (c.LoopExpression.loop(0), c.LoopExpression.loop(1))
        macros = tuple(SimpleNamespace(id=f"M{index}", algorithm=SimpleNamespace(
            expression=expression, turn_sequence=expression.expanded_moves(loops)))
            for index, expression in enumerate(expressions, 1))
        first, second = (c.HumanMacroRecipe.macro(macro.id) for macro in macros)
        recipe = c.HumanMacroRecipe.rotated("x", c.HumanMacroRecipe.sequence(
            c.HumanMacroRecipe.rotated("y", first), second))
        method = SimpleNamespace(reference_shape=c.Shape())
        repertoire = SimpleNamespace(macros=macros,
            stages=(SimpleNamespace(cases=(SimpleNamespace(instruction=recipe),), rules=()),))
        before = recipe.to_dict()
        presentations, additional = _guide_instructions(repertoire, rotate_diagram=True)
        presentation = presentations[recipe]
        identifier, word, frame = additional[0]
        self.assertRegex(identifier, r"^A\d+$")
        self.assertEqual(presentation.identifier, identifier)
        self.assertEqual(presentation.turn_sequence, word)
        action = _additional_algorithm_action(method, word, frame)
        table = "\n".join(_algorithm_table(((identifier, word, action),)))
        self.assertIn(f"| `{identifier}: {word}` | `{action.notation}` | "
                      f"`{c.structured_move_notation(word)}` |", table)
        self.assertEqual(frame, "x")
        self.assertEqual(rotate_permutation(c.State().apply(word).sticker_permutation, frame),
                         recipe.loop_expression(macros).evaluate(loops))
        self.assertEqual(action.permutation, c.State().apply(word).sticker_permutation)
        self.assertNotIn("rotate(", table)
        self.assertEqual(before, recipe.to_dict())

    def test_additional_definition_action_uses_the_pictured_bandage_frame(self):
        from bce_v2.block_actions import _ROTATIONS
        from bce_v2.human_repertoire_render import _additional_algorithm_action
        from bce_v2.loop_rotations import rotation_tuple

        method = self.repertoire.method
        word = rotate_moves(self.repertoire.macros[0].algorithm.turn_sequence, "x'")
        reference = method.reference_shape.rotated(_ROTATIONS.index(rotation_tuple("x")))
        self.assertNotEqual(reference, method.reference_shape)
        replay = c.State(reference).apply(word)
        self.assertEqual(replay.shape, reference)
        action = _additional_algorithm_action(method, word, "x")
        self.assertEqual(action.inventory.root_shape, reference)
        self.assertEqual(action.notation, c.BlockInventory(reference).action(replay).notation)
        self.assertEqual(action.permutation, replay.sticker_permutation)

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_invalid_visual_palette_fails_before_drawing_or_overwriting_saved_guide(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.md"
            path.write_text("saved guide", encoding="utf-8")
            with patch("bce_v2.human_diagram_render.recognition_diagram_image") as draw:
                with self.assertRaises((TypeError, ValueError)):
                    self.repertoire.write_guide(path, diagram_mode="transparent", face_colors={"bad": "red"})
            draw.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf-8"), "saved guide")


if __name__ == "__main__":
    unittest.main()
