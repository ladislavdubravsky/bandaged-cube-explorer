"""Endpoint families suggest generic coarse goals without implying coverage."""

from dataclasses import FrozenInstanceError, replace
import json
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette
from bce_v2.algorithm_profiles import (_adjacent, discover_palette_profiles,
                                      propose_palette_goals)
from bce_v2.coarse_methods import _domain_ladder
from bce_v2.human_chains import _observation, _resolve_feature
from bce_v2.symbolic_chains import plan_symbolic_stages
from test_coarse_methods import last_layer_inputs


class ProfileInputTests(unittest.TestCase):
    def test_empty_palette_does_not_invent_an_all_fixed_workspace(self):
        discovery = discover_palette_profiles(c.BlockInventory(), AlgorithmPalette(()))
        self.assertEqual(discovery.profiles, ())
        self.assertEqual(discovery.workspaces, ())
        self.assertIsNone(discovery.common_workspace)
        self.assertFalse(discovery.diagnostics["coverage_claim"])
        self.assertFalse(discovery.to_dict()["coverage_claim"])

    def test_invalid_inputs_and_limits_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "BlockInventory"):
            discover_palette_profiles(object(), AlgorithmPalette(()))
        with self.assertRaisesRegex(TypeError, "AlgorithmPalette"):
            discover_palette_profiles(c.BlockInventory(), object())
        for name in ("max_candidates", "max_clusters"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                discover_palette_profiles(c.BlockInventory(), AlgorithmPalette(()), **{name: -1})
            with self.subTest(name=name), self.assertRaises(TypeError):
                discover_palette_profiles(c.BlockInventory(), AlgorithmPalette(()), **{name: True})

    def test_adjacency_uses_real_cells_and_respects_gaps_in_a_footprint(self):
        labels = list(range(27))
        for cell in (0, 1, 2, 3, 6):
            labels[cell] = 30
        inventory = c.BlockInventory(c.Shape(labels))
        by_cells = {block.cells: index for index, block in enumerate(inventory.blocks)}
        self.assertFalse(_adjacent(inventory, by_cells[(0, 1, 2, 3, 6)], by_cells[(8,)]))
        self.assertTrue(_adjacent(inventory, by_cells[(0, 1, 2, 3, 6)], by_cells[(5,)]))


@unittest.skipUnless(shutil.which("gap"), "GAP prepares independent ambient certificates")
class PalettePreservationDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis, cls.palette, cls.features, cls.domain = last_layer_inputs()
        cls.plan = plan_symbolic_stages(cls.analysis, strategy="manual",
            features=(*_domain_ladder(cls.analysis.block_inventory, cls.domain), *cls.features), timeout=90)
        cls.group = cls.plan.stages[11].group_after
        cls.inventory = cls.analysis.block_inventory
        with patch("subprocess.run", side_effect=AssertionError("profiles are computed offline")):
            cls.discovery = discover_palette_profiles(cls.inventory, cls.palette, ambient_group=cls.plan.group)

    def test_shared_preservation_discovers_the_previously_seeded_workspace(self):
        discovery = self.discovery
        workspace = discovery.common_workspace
        self.assertEqual(workspace.feature, self.domain[0])
        self.assertEqual(workspace.preserving_recipe_ids, discovery.recipe_ids)
        self.assertEqual(len(workspace.block_indices), 12)
        self.assertEqual(len(discovery.globally_fixed_pose_indices), 6)
        self.assertEqual(len(workspace.adjacency_components), 1)
        self.assertEqual(tuple(sorted(workspace.adjacency_components[0])), workspace.block_indices)
        for recipe in self.palette.recipes:
            action = self.inventory.action(recipe.permutation)
            self.assertEqual(_observation(action, workspace.block_indices, "solve_blocks"),
                             _observation(self.inventory.identity(), workspace.block_indices, "solve_blocks"))
        # Every omitted observable component is moved or reoriented by at
        # least one recipe; the inferred region is the maximal intersection.
        for index in set(discovery.active_block_indices) - set(workspace.block_indices):
            self.assertTrue(any(self.inventory.action(recipe.permutation).destinations[index] != index or
                                self.inventory.action(recipe.permutation).phases[index] != 0
                                for recipe in self.palette.recipes))

    def test_profiles_are_endpoint_facts_for_complete_physical_recipes(self):
        profiles = {profile.recipe_id: profile for profile in self.discovery.profiles}
        for recipe in self.palette.recipes:
            action = self.inventory.action(c.State().apply(recipe.turn_sequence))
            profile = profiles[recipe.id]
            for index in range(len(self.inventory.blocks)):
                self.assertEqual(index in profile.fixed_placement_indices, action.destinations[index] == index)
                self.assertEqual(index in profile.fixed_pose_indices,
                                 action.destinations[index] == index and action.phases[index] == 0)
            self.assertEqual(set(index for region in profile.invariant_slot_sets for index in region),
                             set(range(len(self.inventory.blocks))))
            for region in profile.invariant_slot_sets:
                self.assertEqual({action.destinations[index] for index in region}, set(region))
        # Setup endpoints may violate a goal, while the complete conjugate
        # restores it. Such a conjugate must retain its corner preservation.
        corner_indices = _resolve_feature(self.inventory, self.features[2])
        records = {row["id"]: row for row in self.palette.recipe_records}
        conjugate = next(recipe for recipe in self.palette.recipes
                         if records[recipe.id]["body_id"] == "Ua" and records[recipe.id]["setup_id"] == "U")
        self.assertTrue(set(corner_indices).issubset(profiles[conjugate.id].fixed_pose_indices))
        self.assertNotEqual(_observation(self.inventory.action(c.State().apply("U")), corner_indices, "place_blocks"),
                            _observation(self.inventory.identity(), corner_indices, "place_blocks"))

    def test_current_group_proposals_prioritize_the_grouped_last_layer_ladder(self):
        with patch("subprocess.run", side_effect=AssertionError("proposal generation is offline")):
            goals = propose_palette_goals(self.inventory, self.group, self.palette, discovery=self.discovery)
        self.assertEqual(tuple(goal.feature for goal in goals[:4]), self.features)
        for goal in goals:
            self.assertFalse(goal.to_dict()["coverage_claim"])
            if goal.feature.kind == "orient_slots":
                for generator in self.group.strong_generators:
                    action = self.inventory.action(generator.permutation)
                    self.assertEqual({action.destinations[index] for index in goal.block_indices}, set(goal.block_indices))
        # The palette alone preserves these regions, but the full ordinary
        # cube group does not. They cannot be anonymous phase stage goals yet.
        ambient = propose_palette_goals(self.inventory, self.plan.group, self.palette, discovery=self.discovery)
        self.assertFalse(any(goal.feature in self.features[:2] for goal in ambient))

    def test_discovery_is_immutable_deterministic_and_bounded(self):
        reordered = AlgorithmPalette(tuple(reversed(self.palette.bodies)), tuple(reversed(self.palette.setups)),
                                     tuple(reversed(self.palette.adjustments)))
        same = discover_palette_profiles(self.inventory, reordered, ambient_group=self.plan.group)
        self.assertEqual(self.discovery.to_dict(), same.to_dict())
        self.assertEqual(json.loads(json.dumps(self.discovery.to_dict())), self.discovery.to_dict())
        with self.assertRaises(FrozenInstanceError):
            self.discovery.profiles[0].recipe_id = "changed"
        with self.assertRaises(TypeError):
            self.discovery.diagnostics["coverage_claim"] = True
        bounded = discover_palette_profiles(self.inventory, self.palette, ambient_group=self.plan.group,
                                            max_candidates=3, max_clusters=1)
        self.assertLessEqual(len(bounded.goals), 3)
        self.assertEqual(bounded.common_workspace.feature, self.domain[0])
        self.assertTrue(bounded.diagnostics["candidates_bounded"])
        with self.assertRaisesRegex(ValueError, "different inventory or palette"):
            propose_palette_goals(self.inventory, self.group, AlgorithmPalette(self.palette.bodies[:-1]),
                                  discovery=self.discovery)
        changed = AlgorithmPalette((replace(self.palette.bodies[0], algorithm=self.palette.bodies[1].algorithm),
                                    *self.palette.bodies[1:]), self.palette.setups, self.palette.adjustments)
        with self.assertRaisesRegex(ValueError, "different inventory or palette"):
            propose_palette_goals(self.inventory, self.group, changed, discovery=self.discovery)

    def test_same_machinery_handles_fused_components_with_four_phase_frames(self):
        shape = c.Shape([1] * 9 + [2] * 18)
        analysis = c.analyze_isotropy(shape, timeout=30)
        plan = plan_symbolic_stages(analysis, timeout=30)
        library = c.AlgorithmLibrary(analysis.loops, (), (), ())
        bodies = tuple(replace(library.build_algorithm(c.LoopExpression.loop(generator.id)), id=f"body-{generator.id}")
                       for generator in analysis.loops.generators)
        palette = AlgorithmPalette.from_algorithms(bodies, allow_inverse=False)
        discovery = discover_palette_profiles(analysis.block_inventory, palette, ambient_group=plan.group)
        self.assertIsNone(discovery.common_workspace)
        self.assertEqual(len(discovery.active_block_indices), 1)
        goals = propose_palette_goals(analysis.block_inventory, plan.group, palette, discovery=discovery)
        phase = next(goal for goal in goals if goal.feature.kind == "orient_slots")
        self.assertEqual(len(phase.feature.cells), 9)
        self.assertEqual(analysis.block_inventory.blocks[phase.block_indices[0]].orientation_order, 4)
        self.assertTrue(phase.repairing_recipe_ids)
        self.assertFalse(discovery.to_dict()["coverage_claim"])


if __name__ == "__main__":
    unittest.main()
