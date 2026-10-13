"""Adaptive entry integration, vocabulary limits and portable scope checks."""

from copy import deepcopy
from dataclasses import replace
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_method_io import _fingerprint


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare the suffix certificate")
class WorkspaceMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([1] * 9 + [2] * 18)
        cls.analysis = c.analyze_isotropy(cls.shape, timeout=30)
        cls.builder = c.AlgorithmLibrary(cls.analysis.loops, (), (), ())
        cls.generator = cls.analysis.loops.generators[0]
        cls.action = replace(cls.builder.build_algorithm(c.LoopExpression.loop(cls.generator.id)), id="clockwise")
        cls.entry_palette = c.AlgorithmPalette.from_algorithms((), adjustments=(cls.action,))
        domain = (c.BlockFeature("solve_block", tuple(range(9))),)
        cls.suffix = c.compile_coarse_method(cls.analysis, features=(),
            palette=c.AlgorithmPalette(()), domain_features=domain, timeout=30)
        cls.method = c.compile_workspace_method(cls.suffix, entry_palette=cls.entry_palette,
            max_taught_bodies=0, controller_options={"max_pattern_count": 0, "max_depth": 4})

    def state(self, word):
        state = c.State(self.shape).apply(word)
        return c.State.from_facelets(state.facelets, self.shape)

    def test_all_four_hidden_states_use_only_declared_directed_operations(self):
        with patch("subprocess.run", side_effect=AssertionError("offline entry")):
            for word in ("", "U", "U2", "U'"):
                state = self.state(word)
                result = self.method.apply(state)
                self.assertEqual(result.status, "solved")
                self.assertTrue(result.state.is_solved)
                self.assertEqual(state.apply(result.turn_sequence), result.state)
                self.assertEqual(result.metadata["taught_definition_ids"], [])
                for step in result.entry_steps:
                    self.assertTrue(all(identifier == self.method.controller.actions[0].id
                                        for identifier in step.action_ids))
                    self.assertFalse(step.complete)
        self.assertFalse(self.method.human_method_complete)
        self.assertEqual(self.method.coverage_scope, "bounded_constructive_entry_then_certified_domain_suffix")

    def test_limits_do_not_execute_fallback_or_suffix_outside_domain(self):
        method = c.compile_workspace_method(self.suffix, entry_palette=self.entry_palette,
            max_taught_bodies=0, max_entry_nodes=0)
        state = self.state("U")
        with patch.object(c.CoarseMethod, "apply", side_effect=AssertionError("no suffix outside domain")):
            result = method.apply(state)
        self.assertEqual(result.status, "entry_limit")
        self.assertEqual(result.state, state)
        self.assertEqual(result.entry_steps, ())
        self.assertIn("total_node_limit", result.metadata["entry_stop_reasons"])
        zero = c.compile_workspace_method(self.suffix, entry_palette=self.entry_palette,
            max_taught_bodies=0, max_stages=0)
        self.assertIn("stage_limit", zero.apply(state).metadata["entry_stop_reasons"])

    def test_no_entry_actions_report_bounded_failure(self):
        method = c.compile_workspace_method(self.suffix, entry_palette=c.AlgorithmPalette(()))
        result = method.apply(self.state("U"))
        self.assertEqual(result.status, "entry_limit")
        self.assertIn("outside_action_orbit", result.metadata["entry_stop_reasons"])

    def test_long_entry_words_cannot_bypass_the_teaching_budget(self):
        long = replace(self.builder.build_algorithm(c.LoopExpression.power(
            c.LoopExpression.loop(self.generator.id), 3)), id="long-adjustment")
        palette = c.AlgorithmPalette.from_algorithms((), adjustments=(long,))
        # A zero short-operation threshold charges this otherwise elementary
        # action, making the budget check independent of move simplification.
        with self.assertRaisesRegex(ValueError, "global taught-definition budget"):
            c.compile_workspace_method(self.suffix, entry_palette=palette,
                max_short_setup_htm=0, max_taught_bodies=0)
        method = c.compile_workspace_method(self.suffix, entry_palette=palette,
            max_short_setup_htm=0, max_taught_bodies=1)
        self.assertEqual(method.taught_definition_ids, ("adjustment:long-adjustment",))

    def test_portable_load_revalidates_budget_and_claims_offline(self):
        record = self.method.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("offline load")):
            loaded = c.WorkspaceMethod.from_dict(record)
            self.assertEqual(loaded.to_dict(), record)
            self.assertTrue(loaded.apply(self.state("U")).state.is_solved)
        for key, value in (("human_method_complete", True),
                           ("coverage_scope", "all_scrambles"),
                           ("taught_definition_ids", ["fake"])):
            broken = deepcopy(record)
            broken[key] = value
            broken["fingerprint"] = _fingerprint(broken)
            with self.assertRaisesRegex(ValueError, "claims disagree"):
                c.WorkspaceMethod.from_dict(broken)

    def test_derived_suffix_keeps_its_calls_when_entry_declarations_are_merged(self):
        palette = c.AlgorithmPalette.from_algorithms((self.action,), allow_inverse=False).with_derived_actions(
            max_derived_recipes=1)
        suffix = c.compile_coarse_method(self.analysis, palette=palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        used = {identifier for _, _, path in suffix.case_recipes for identifier in path}
        self.assertTrue(any(record["derived"] and record["id"] in used for record in palette.recipe_records))
        method = c.compile_workspace_method(suffix, entry_palette=self.entry_palette,
            max_taught_bodies=1)
        self.assertEqual(method.taught_definition_ids, (self.action.id,))
        self.assertEqual(method.suffix.palette.recipe_records, palette.recipe_records)
        with patch("subprocess.run", side_effect=AssertionError("portable derived workspace must be offline")):
            loaded = c.WorkspaceMethod.from_dict(method.to_dict())
            self.assertEqual(loaded.taught_definition_ids, (self.action.id,))
            for word in ("", "U", "U2", "U'"):
                self.assertTrue(loaded.apply(self.state(word)).state.is_solved)
        with self.assertRaisesRegex(ValueError, "global taught-definition budget"):
            c.compile_workspace_method(suffix, entry_palette=self.entry_palette, max_taught_bodies=0)

    def test_entry_guide_uses_letter_structure_and_block_actions(self):
        before = self.method.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("guide rendering is offline")):
            guide = self.method.write_guide()
        self.assertEqual(guide.count("## Execution vocabulary"), 1)
        self.assertIn("| Algorithm | Turn sequence | Block action |", guide)
        self.assertIn(f"| `A` | `{self.action.turn_sequence}` | `{self.action.block_action.notation}` |", guide)
        self.assertNotIn("palette:", guide)
        self.assertNotIn("clockwise", guide)
        self.assertEqual(self.method.to_dict(), before)

    def test_derived_entry_and_suffix_share_one_letter_vocabulary_offline(self):
        palette = c.AlgorithmPalette.from_algorithms((self.action,), allow_inverse=False).with_derived_actions(
            max_derived_recipes=1)
        suffix = c.compile_coarse_method(self.analysis, palette=palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        entry = self.entry_palette.with_derived_actions(max_derived_recipes=1)
        method = c.compile_workspace_method(suffix, entry_palette=entry, max_taught_bodies=1)
        before = method.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("derived guide rendering is offline")):
            loaded = c.WorkspaceMethod.from_dict(before)
            guide = loaded.write_guide()
        self.assertEqual(guide.count("## Execution vocabulary"), 1)
        self.assertIn("| Body | `A` |", guide)
        self.assertIn("| Adjustment | `B` |", guide)
        entry_section, continuation = guide.split("## Certified continuation", 1)
        self.assertIn("| `B²` |", entry_section)
        self.assertIn("Repeat **`A`**", continuation)
        self.assertNotIn("palette:", guide)
        self.assertNotIn("clockwise", guide)
        self.assertEqual(loaded.to_dict(), before)

    def test_entry_and_nonempty_suffix_share_letters_without_derived_operations(self):
        palette = c.AlgorithmPalette.from_algorithms((self.action,), allow_inverse=False)
        suffix = c.compile_coarse_method(self.analysis, palette=palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        method = c.compile_workspace_method(suffix, entry_palette=self.entry_palette, max_taught_bodies=1)
        before = method.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("shared guide rendering is offline")):
            guide = method.write_guide()
        self.assertEqual(guide.count("## Execution vocabulary"), 1)
        entry_section, continuation = guide.split("## Certified continuation", 1)
        self.assertIn("| Body | `A` |", entry_section)
        self.assertIn("| Adjustment | `B` |", entry_section)
        self.assertIn(f"| `B` | `{self.action.turn_sequence}` | `{self.action.block_action.notation}` |",
                      entry_section)
        self.assertIn("Repeat **`A`**", continuation)
        self.assertNotIn("palette:", guide)
        self.assertEqual(method.to_dict(), before)

    def test_singleton_configuration_and_wrong_reference(self):
        method = c.compile_workspace_method(self.suffix, max_components=1)
        self.assertEqual(method.assemblies, ())
        self.assertTrue(method.apply(self.state("U")).state.is_solved)
        result = method.apply(c.State())
        self.assertEqual(result.status, "wrong_reference")
        self.assertEqual(result.entry_steps, ())

    def test_input_settings_reject_bad_types(self):
        for name in ("max_taught_bodies", "max_candidates", "max_components", "max_stages", "max_entry_nodes"):
            with self.assertRaises(TypeError):
                c.compile_workspace_method(self.suffix, **{name: True})
        with self.assertRaises(ValueError):
            c.compile_workspace_method(self.suffix, controller_options={"max_pattern_components": 4})


if __name__ == "__main__":
    unittest.main()
