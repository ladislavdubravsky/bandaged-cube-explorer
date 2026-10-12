"""Constructive recognition is local, directed and endpoint safe."""

from dataclasses import replace
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette, AlgorithmPaletteBody
from bce_v2.human_chains import _observation, _resolve_feature
from bce_v2.workspace_entry import ConstructiveEntryController


def history_free(state):
    return c.State.from_facelets(state.facelets, state.specification)


class WorkspaceEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loops = c.isotropy_loops(c.Shape())
        cls.controller = ConstructiveEntryController(cls.loops, max_depth=8, max_nodes=50_000)

    def assert_goal(self, controller, state, feature):
        block = _resolve_feature(controller.inventory, feature)
        actual = _observation(controller.inventory.action(state.sticker_permutation), block, feature.kind)
        goal = _observation(controller.inventory.identity(), block, feature.kind)
        self.assertEqual(actual, goal)

    def test_joint_component_correction_uses_history_free_observation(self):
        feature = c.BlockFeature("solve_blocks", (c.DFR, c.FR))
        state = history_free(c.State().apply("R U F2 L' D"))
        with patch("subprocess.run", side_effect=AssertionError("entry runs offline")):
            step = self.controller.plan_step(state, feature)
        self.assertEqual(step.status, "ready")
        self.assertFalse(step.complete)
        self.assertIsNone(step.before.scramble)
        self.assertEqual(step.before.apply(step.turn_sequence), step.after)
        self.assert_goal(self.controller, step.after, feature)
        self.assertEqual(step.metrics["recognition_components"], 2)
        self.assertTrue(set(step.action_ids).issubset({a.id for a in self.controller.actions}))

    def test_same_word_solves_every_hidden_fiber_without_full_orbit_enumeration(self):
        feature = c.BlockFeature("solve_blocks", (c.DFR, c.FR))
        states = [history_free(c.State().apply(prefix + " R"))
                  for prefix in ("", "U", "U2", "U'", "U F U' F' U R U' R'")]
        # Keep the first four U offsets: they change hidden components while
        # retaining this pair's observed pose under the final R action.
        states = states[:4]
        observations = []
        for state in states:
            step = self.controller.plan_step(state, feature)
            observations.append(step.observation)
            self.assert_goal(self.controller, state.apply(step.turn_sequence), feature)
        self.assertEqual(len(set(observations)), 1)
        first = self.controller.plan_step(states[0], feature)
        for state in states:
            self.assert_goal(self.controller, state.apply(first.turn_sequence), feature)

    def test_temporarily_displaced_protected_components_are_restored_at_endpoint(self):
        protected = c.BlockFeature("solve_blocks", (c.DR, c.DF, c.DL, c.DB))
        feature = c.BlockFeature("solve_blocks", (c.DFR, c.FR))
        state = history_free(c.State().apply("R U R'"))
        self.assert_goal(self.controller, state, protected)
        step = self.controller.plan_step(state, feature, protected_features=(protected,))
        self.assertTrue(step.successful)
        self.assert_goal(self.controller, step.after, protected)
        self.assert_goal(self.controller, step.after, feature)
        current, displaced = state, False
        for token in step.turn_sequence.split():
            current = current.apply(token)
            block = _resolve_feature(self.controller.inventory, protected)
            actual = _observation(self.controller.inventory.action(current.sticker_permutation), block, protected.kind)
            solved = _observation(self.controller.inventory.identity(), block, protected.kind)
            displaced |= actual != solved
        self.assertTrue(displaced)

    def test_allowed_direction_is_repeated_without_implicitly_granting_inverse(self):
        builder = c.AlgorithmLibrary(self.loops, (), (), ())
        leaf = next(g for g in self.loops.generators if g.turn_sequence == "U")
        algorithm = replace(builder.build_algorithm(c.LoopExpression.loop(leaf.id)), id="clockwise")
        palette = AlgorithmPalette((AlgorithmPaletteBody("clockwise", algorithm, False),))
        controller = ConstructiveEntryController(self.loops, palette=palette, max_depth=3)
        step = controller.plan_step(history_free(c.State().apply("U")),
                                    c.BlockFeature("solve_block", (c.UFR,)))
        self.assertEqual(step.status, "ready")
        self.assertEqual(len(step.action_ids), 3)
        self.assertEqual(len(set(step.action_ids)), 1)
        self.assertEqual(step.metrics["additive_recipe_htm"], 3)
        self.assertTrue(all(record["exponent"] == 1 for record in palette.recipe_records))
        self.assert_goal(controller, step.after, step.feature)

    def test_limits_and_missing_action_orbits_do_not_call_an_external_solver(self):
        state = history_free(c.State().apply("R"))
        feature = c.BlockFeature("solve_block", (c.DFR,))
        with patch("subprocess.run", side_effect=AssertionError("no fallback")):
            depth = self.controller.plan_step(state, feature, max_depth=0)
            nodes = self.controller.plan_step(state, feature, max_nodes=0)
            empty = ConstructiveEntryController(self.loops, palette=AlgorithmPalette(()))
            missing = empty.plan_step(state, feature)
        self.assertEqual(depth.status, "depth_limit")
        self.assertEqual(nodes.status, "node_limit")
        self.assertEqual(missing.status, "outside_action_orbit")
        for step in (depth, nodes, missing):
            self.assertFalse(step.complete)
            self.assertEqual(step.action_ids, ())
            self.assertEqual(step.state, state)

    def test_oversized_patterns_are_discarded_while_concrete_search_stays_bounded(self):
        controller = ConstructiveEntryController(self.loops, max_pattern_observations=1,
                                                  max_depth=2, max_nodes=1000)
        step = controller.plan_step(history_free(c.State().apply("R")),
                                    c.BlockFeature("solve_blocks", (c.DFR, c.FR)))
        self.assertEqual(step.status, "ready")
        self.assertGreater(step.metrics["pattern_limits"], 0)
        self.assertEqual(step.metrics["pattern_count"], 0)
        self.assertFalse(step.complete)

    def test_orientation_recognizes_occupants_entering_from_outside_goal_region(self):
        feature = c.BlockFeature("orient_slots", (c.UR, c.UF, c.UL, c.UB))
        step = self.controller.plan_step(history_free(c.State().apply("F")), feature,
                                         max_depth=2, max_nodes=1000)
        self.assertEqual(step.status, "ready")
        self.assert_goal(self.controller, step.after, feature)
        self.assertEqual(step.metrics["recognition_components"], 12)

    def test_nonpose_goals_keep_their_exact_predicates_with_encoded_search(self):
        alignments = tuple(c.State().apply(word).sticker_permutation
                           for word in ("", "U", "U2", "U'"))
        goals = (
            c.BlockFeature("place_blocks", (c.DFR, c.FR)),
            c.BlockFeature("occupy_slots", (c.UFR, c.UFL)),
            c.BlockFeature("place_blocks_up_to_alignment",
                (c.UFR, c.UFL, c.UBL, c.UBR), alignments),
        )
        for goal, word in zip(goals, ("R", "U2", "R")):
            with self.subTest(kind=goal.kind):
                step = self.controller.plan_step(history_free(c.State().apply(word)), goal,
                                                 max_depth=1, max_nodes=100)
                self.assertTrue(step.successful)
                self.assert_goal(self.controller, step.after, goal)

    def test_single_fused_component_goal_retains_its_nonstandard_phase_order(self):
        shape = c.Shape([1] * 9 + [2] * 18)
        controller = ConstructiveEntryController(c.isotropy_loops(shape))
        goal = c.BlockFeature("solve_blocks", tuple(range(9)))
        self.assertEqual(controller.inventory.blocks[0].orientation_order, 4)
        for word in ("U", "U2", "U'"):
            step = controller.plan_step(history_free(c.State(shape).apply(word)), goal)
            self.assertEqual(step.status, "ready")
            self.assertEqual(step.metrics["recognition_components"], 1)
            self.assert_goal(controller, step.after, goal)

    def test_same_controller_accepts_real_fused_components_offline(self):
        shape = c.Shape([1] * 9 + [2] * 18)
        loops = c.isotropy_loops(shape)
        with patch("subprocess.run", side_effect=AssertionError("no GAP needed")):
            controller = ConstructiveEntryController(loops.block_inventory,
                                                      generators=loops.generators)
            goal = c.BlockFeature("solve_blocks", tuple(range(27)))
            for word in ("", "U", "U2", "U'"):
                state = history_free(c.State(shape).apply(word))
                step = controller.plan_step(state, goal)
                self.assertTrue(step.successful)
                self.assertTrue(step.after.is_solved)

    def test_unsatisfied_protection_and_invalid_options_are_explicit(self):
        protected = c.BlockFeature("solve_block", (c.DFR,))
        step = self.controller.plan_step(c.State().apply("R"),
            c.BlockFeature("solve_block", (c.DFL,)), protected_features=(protected,))
        self.assertEqual(step.status, "commitment_not_satisfied")
        with self.assertRaisesRegex(TypeError, "integer"):
            ConstructiveEntryController(self.loops, max_nodes=True)
        with self.assertRaisesRegex(ValueError, "at most three"):
            ConstructiveEntryController(self.loops, max_pattern_components=4)


if __name__ == "__main__":
    unittest.main()
