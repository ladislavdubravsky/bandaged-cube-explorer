import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bce_v2 as c
from bce_v2 import automatic_methods as automatic
from bce_v2.isotropy import LoopGenerators


def imported(state):
    result = c.State.from_facelets(state.facelets, state.specification)
    assert result.scramble is None
    return result


class AutomaticMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = c.discover_method([1] * 27, cache_dir=None)
        cls.fused = c.discover_method([1] * 9 + [2] * 18, cache_dir=None)

    def test_bandage_alone_builds_complete_tiny_policies(self):
        for result, words in ((self.frozen, ("",)),
                              (self.fused, ("", "U", "U2", "U'"))):
            self.assertEqual(result.status, "completed")
            self.assertTrue(result.method.coverage_complete)
            self.assertFalse(result.metadata["algorithms_supplied_by_caller"])
            self.assertFalse(result.metadata["goals_supplied_by_caller"])
            self.assertFalse(result.metadata["unrestricted_colored_solver_used"])
            for word in words:
                state = imported(c.State(result.method.reference_shape).apply(word))
                solution = result.apply(state)
                self.assertEqual(solution.status, "solved")
                self.assertTrue(solution.state.is_solved)
                self.assertEqual(state.apply(solution.turn_sequence), solution.state)

    def test_frozen_policy_roundtrips_without_original_loop_witnesses(self):
        inner = self.frozen.method.inner_method
        self.assertEqual(inner.generators, ())
        record = inner.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("portable loading is offline")):
            loaded = type(inner).from_dict(record)
            application = loaded.apply(imported(c.State(inner.reference_shape)))
        self.assertEqual(loaded.to_dict(), record)
        self.assertEqual(application.status, "solved")
        self.assertEqual(application.turn_sequence, "")

    def test_changing_shape_is_restored_without_history(self):
        result = c.discover_method(c.fixture("Bicube Fuse"), cache_dir=None)
        self.assertEqual(result.status, "completed")
        method = result.method
        generator = next(iter(method.graph.isotropy_loops().generators))
        state = imported(c.State(method.reference_shape).apply(generator.turn_sequence + " F R2"))
        self.assertNotEqual(state.shape, method.reference_shape)
        solution = method.apply(state)
        restored = state.apply(solution.shape_turn_sequence)
        self.assertEqual(restored.shape, method.reference_shape)
        self.assertIsNone(restored.scramble)
        self.assertIsNotNone(solution.method_application)
        self.assertEqual(solution.status, "solved")
        self.assertEqual(state.apply(solution.turn_sequence), solution.state)
        self.assertTrue(solution.state.is_solved)
        self.assertLessEqual(len(result.metadata["taught_definition_ids"]), 7)
        self.assertIn("shape graph", result.write_guide())
        self.assertFalse(method.human_method_complete)

    def test_shape_cutoff_does_not_start_group_analysis(self):
        with patch.object(LoopGenerators, "analyze", side_effect=AssertionError("no GAP on partial graph")):
            result = c.discover_method(c.fixture("Alcatraz"), max_shapes=1, cache_dir=None)
        self.assertEqual(result.status, "analysis_limit")
        self.assertIsNone(result.method)
        self.assertFalse(result.metadata["shape_graph_complete"])
        with self.assertRaisesRegex(RuntimeError, "no executable method"):
            result.apply(c.State(c.fixture("Alcatraz")))

    def test_native_workload_cutoff_precedes_group_analysis(self):
        with patch.object(automatic, "_MAX_ORIGINAL_LOOPS", 0), patch.object(
                LoopGenerators, "analyze", side_effect=AssertionError("no GAP on oversized witness alphabet")):
            result = c.discover_method([1] * 9 + [2] * 18, cache_dir=None)
        self.assertEqual(result.status, "preparation_limit")
        self.assertIsNone(result.method)

    def test_zero_budget_does_not_grant_long_loop_bodies(self):
        result = c.discover_method(c.fixture("Bicube Fuse"), max_taught_bodies=0, cache_dir=None)
        self.assertEqual(result.status, "no_method_found")
        self.assertIsNone(result.method)
        self.assertEqual(result.metadata["automatic_palette"]["selected_body_ids"], [])

    def test_regrip_witness_limit_keeps_joint_fallback_available(self):
        search = SimpleNamespace(method=None,
            to_dict=lambda **kwargs: {"status": "no_method_found"})
        with patch.object(automatic, "discover_coarse_method", return_value=search), patch.object(
                c.AlgorithmPalette, "with_rotated_bodies",
                side_effect=ValueError("root proof exceeds max_proof_moves")):
            result = c.discover_method([1] * 9 + [2] * 18, cache_dir=None)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.metadata["route"], "palette_joint_policy")
        self.assertIn("witness limit", result.metadata["attempts"][0])
        self.assertTrue(result.apply(c.State(result.method.reference_shape).apply("U")).state.is_solved)

    def test_wrong_reference_and_input_type_are_explicit(self):
        solution = self.fused.apply(c.State([1] * 27))
        self.assertEqual(solution.status, "wrong_reference")
        self.assertEqual(solution.turn_sequence, "")
        with self.assertRaisesRegex(TypeError, "colored State"):
            self.fused.apply(c.Shape([1] * 9 + [2] * 18))

    def test_invalid_limits_rejected_before_exploration(self):
        for kwargs, error in (({"max_taught_bodies": True}, TypeError),
                              ({"max_taught_bodies": -1}, ValueError),
                              ({"max_shapes": 0}, ValueError),
                              ({"timeout": 0}, ValueError),
                              ({"force": "yes"}, TypeError),
                              ({"progress": "yes"}, TypeError)):
            with self.subTest(kwargs=kwargs), patch.object(automatic, "explore",
                    side_effect=AssertionError("invalid options must not explore")):
                with self.assertRaises(error):
                    c.discover_method([1] * 27, **kwargs)

    def test_progress_callback_and_state_reference_input(self):
        events = []
        initial = c.State([1] * 9 + [2] * 18).apply("U")
        result = c.discover_method(initial, cache_dir=None, progress=events.append)
        self.assertEqual(result.method.reference_shape, initial.specification)
        self.assertTrue(any(event["phase"] == "automatic_shape_graph" for event in events))
        self.assertEqual(result.apply(imported(initial)).status, "solved")


if __name__ == "__main__":
    unittest.main()
