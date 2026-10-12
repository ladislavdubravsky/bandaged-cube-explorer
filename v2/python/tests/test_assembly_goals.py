"""Relative assemblies remain exact away from their final reference slots."""

from dataclasses import FrozenInstanceError
import json
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.assembly_goals import (RelativeAssemblyGoal, observe_relative_assembly,
                                  propose_relative_assemblies, rank_relative_assemblies)
from bce_v2.block_actions import _CELL_IMAGES, _IDENTITY, _ROTATIONS


class RelativeAssemblyRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.inventory = c.BlockInventory()
        self.pair = RelativeAssemblyGoal((c.UFR, c.UF))

    def test_joined_pair_is_recognized_away_from_final_slots_without_history(self):
        scrambled = c.State().apply("U")
        imported = c.State.from_facelets(scrambled.facelets)
        self.assertIsNone(imported.scramble)
        with patch("subprocess.run", side_effect=AssertionError("recognition is offline")):
            observation = observe_relative_assembly(self.inventory, imported, self.pair)
        self.assertTrue(observation.is_assembled)
        self.assertTrue(observation.assembled)
        self.assertFalse(observation.is_anchored)
        self.assertEqual(observation.matched_component_count, 2)
        self.assertEqual(len(observation.matching_rotations), 1)
        rotation = observation.matching_rotations[0]
        self.assertNotEqual(rotation, _IDENTITY)
        self.assertEqual(observation.destination_cells,
                         tuple(tuple(_CELL_IMAGES[rotation][cell] for cell in self.inventory.blocks[index].cells)
                               for index in observation.block_indices))

    def test_adjacent_placements_with_wrong_orientation_do_not_form_an_assembly(self):
        solved = c.State()
        twists = list(solved.twists)
        twists[0], twists[4] = 1, 2
        twisted = c.State.from_cubies(corners=solved.corners, twists=twists,
                                    edges=solved.edges, flips=solved.flips)
        observation = observe_relative_assembly(self.inventory, twisted, self.pair)
        self.assertEqual(observation.destination_cells,
                         tuple(self.inventory.blocks[index].cells for index in observation.block_indices))
        self.assertFalse(observation.is_assembled)
        self.assertFalse(observation.is_anchored)
        self.assertEqual(observation.matched_component_count, 1)

    def test_displaced_components_with_different_rigid_rotations_do_not_match(self):
        observation = observe_relative_assembly(self.inventory, c.State().apply("R"), self.pair)
        self.assertFalse(observation.is_assembled)
        self.assertEqual(observation.missing_component_count, 1)
        # A restricted target set may deliberately require an anchored pose.
        anchored = RelativeAssemblyGoal(self.pair.cells, (_IDENTITY,))
        self.assertFalse(observe_relative_assembly(self.inventory, c.State().apply("U"), anchored).is_assembled)
        self.assertTrue(observe_relative_assembly(self.inventory, c.State(), anchored).is_assembled)

    def test_fused_component_is_indivisible_and_recognition_accepts_off_root_state(self):
        labels = [0] * 27
        labels[c.UF] = labels[c.UFR] = 1
        specification = c.Shape(labels)
        inventory = c.BlockInventory(specification)
        goal = RelativeAssemblyGoal((c.UF, c.UFR, c.UR))
        state = c.State(specification).apply("U")
        self.assertNotEqual(state.shape, specification)
        with self.assertRaisesRegex(ValueError, "restore its shape"):
            inventory.action(state)
        observation = observe_relative_assembly(inventory, state, goal)
        self.assertEqual(len(observation.block_indices), 2)
        self.assertTrue(observation.is_assembled)
        self.assertFalse(observation.is_anchored)
        self.assertEqual(sorted(map(len, observation.destination_cells)), [1, 2])
        with self.assertRaisesRegex(ValueError, "complete physical components"):
            observe_relative_assembly(inventory, state, RelativeAssemblyGoal((c.UF, c.UR)))

    def test_block_action_and_raw_permutation_agree_with_native_state(self):
        state = c.State().apply("U R F2")
        expected = observe_relative_assembly(self.inventory, state, self.pair)
        self.assertEqual(expected, observe_relative_assembly(self.inventory, state.sticker_permutation, self.pair))
        self.assertEqual(expected, observe_relative_assembly(self.inventory, self.inventory.action(state), self.pair))
        with self.assertRaisesRegex(ValueError, "specification differs"):
            observe_relative_assembly(self.inventory, c.State(c.Shape([1] * 9 + [2] * 18)), self.pair)
        invalid = list(range(48))
        invalid[0], invalid[1] = invalid[1], invalid[0]
        with self.assertRaisesRegex(ValueError, "rigid physical component"):
            observe_relative_assembly(self.inventory, invalid, self.pair)

    def test_fixed_unmarked_centers_are_checked_without_invented_spin(self):
        goal = RelativeAssemblyGoal((c.UFR, c.UF, c.U))
        observation = observe_relative_assembly(self.inventory, c.State().apply("U"), goal)
        self.assertTrue(observation.is_assembled)
        center = observation.block_indices.index(next(index for index, block in enumerate(self.inventory.blocks)
                                                     if block.cells == (c.U,)))
        self.assertIsNone(observation.rotations[center])
        self.assertEqual(observation.destination_cells[center], (c.U,))
        # R moves this pair away from the fixed U center, breaking its full
        # geometric relation even if orientation of that center is invisible.
        self.assertFalse(observe_relative_assembly(self.inventory, c.State().apply("R"), goal).is_assembled)

    def test_goal_record_is_immutable_and_validates_rotations(self):
        record = self.pair.to_dict()
        self.assertEqual(RelativeAssemblyGoal.from_dict(json.loads(json.dumps(record))), self.pair)
        self.assertFalse(record["subgroup_claim"])
        self.assertEqual(len(self.pair.allowed_rotations), 24)
        with self.assertRaises(FrozenInstanceError):
            self.pair.cells = ()
        for invalid in (((1, 2, -3),), ((True, 2, 3),), (_IDENTITY, _IDENTITY), ()):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                RelativeAssemblyGoal(self.pair.cells, invalid)
        with self.assertRaises(TypeError):
            RelativeAssemblyGoal((True,))


class AssemblyProposalAndChoiceTests(unittest.TestCase):
    def test_connected_collections_respect_real_fused_cells_and_region(self):
        labels = [0] * 27
        for cell in (0, 1, 2, 3, 6):
            labels[cell] = 1
        inventory = c.BlockInventory(c.Shape(labels))
        region = (0, 1, 2, 3, 5, 6, 8)
        proposals = propose_relative_assemblies(inventory, eligible_cells=region)
        collections = {goal.cells for goal in proposals.goals}
        self.assertIn((0, 1, 2, 3, 5, 6), collections)
        self.assertNotIn((0, 1, 2, 3, 6, 8), collections)
        self.assertIn((5, 8), collections)
        self.assertEqual(proposals, propose_relative_assemblies(inventory, required_cells=region))
        self.assertTrue(all(set(goal.cells).issubset(region) for goal in proposals.goals))
        with self.assertRaisesRegex(ValueError, "complete physical components"):
            propose_relative_assemblies(inventory, eligible_cells=(0, 5))

    def test_default_proposals_exclude_unmarked_centers_and_are_bounded_deterministic(self):
        inventory = c.BlockInventory()
        complete = propose_relative_assemblies(inventory, max_components=3, max_candidates=10000)
        self.assertFalse(complete.metadata["candidates_bounded"])
        self.assertFalse(complete.metadata["expansions_bounded"])
        self.assertTrue(all(all(inventory.blocks[index].corners or inventory.blocks[index].edges
                               for index in observe_relative_assembly(inventory, c.State(), goal).block_indices)
                            for goal in complete.goals))
        limited = propose_relative_assemblies(inventory, max_components=3, max_candidates=3)
        self.assertEqual(len(limited.goals), 3)
        self.assertTrue(limited.metadata["candidates_bounded"])
        self.assertEqual(limited.goals, complete.goals[:3])
        shallow = propose_relative_assemblies(inventory, max_expansions=1)
        self.assertTrue(shallow.metadata["expansions_bounded"])
        self.assertEqual(shallow.goals, ())
        self.assertFalse(limited.to_dict()["coverage_claim"])
        self.assertEqual(json.loads(json.dumps(limited.to_dict())), limited.to_dict())
        with self.assertRaises(TypeError):
            limited.metadata["coverage_claim"] = True
        for argument in ("max_candidates", "max_expansions", "max_components", "min_components"):
            with self.subTest(argument=argument), self.assertRaises((TypeError, ValueError)):
                propose_relative_assemblies(inventory, **{argument: True})

    def test_runtime_ranking_changes_with_scramble_and_preserving_faces_are_physical(self):
        inventory = c.BlockInventory()
        top = RelativeAssemblyGoal((c.UF, c.UFR))
        right = RelativeAssemblyGoal((c.UR, c.UFR))
        u_choices = rank_relative_assemblies(inventory, c.State().apply("U"), (top, right))
        self.assertTrue(all(choice.observation.is_assembled for choice in u_choices))
        r_choices = rank_relative_assemblies(inventory, c.State().apply("R"), (top, right))
        self.assertEqual(r_choices[0].goal, right)
        self.assertTrue(r_choices[0].observation.is_assembled)
        self.assertFalse(r_choices[1].observation.is_assembled)
        for choice in r_choices:
            self.assertTrue(set(choice.free_faces).issubset(choice.assembly_preserving_faces))
            for face in choice.free_faces:
                self.assertEqual(observe_relative_assembly(inventory, c.State().apply("R " + face), choice.goal),
                                 choice.observation)
            if choice.observation.is_assembled:
                for face in choice.assembly_preserving_faces:
                    self.assertTrue(observe_relative_assembly(inventory, c.State().apply("R " + face), choice.goal).is_assembled)
        self.assertEqual(len(rank_relative_assemblies(inventory, c.State(), (top, right), max_choices=1)), 1)
        proposals = propose_relative_assemblies(inventory, eligible_cells=(c.UF, c.UFR, c.UR))
        self.assertEqual(rank_relative_assemblies(inventory, c.State(), proposals),
                         rank_relative_assemblies(inventory, c.State(), proposals.goals))
        with self.assertRaisesRegex(ValueError, "distinct"):
            rank_relative_assemblies(inventory, c.State(), (top, top))
        with self.assertRaisesRegex(TypeError, "requires a State"):
            rank_relative_assemblies(inventory, inventory.identity(), (top,))


if __name__ == "__main__":
    unittest.main()
