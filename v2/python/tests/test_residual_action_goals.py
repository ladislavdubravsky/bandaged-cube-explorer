"""Full poses modulo a witnessed residual family retain relative phases."""

from dataclasses import replace
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import _feature_successor, _observation, _resolve_feature, _then
from bce_v2.symbolic_chains import plan_symbolic_stages, symbolic_plan_from_dict


@unittest.skipUnless(shutil.which("gap"), "GAP prepares subgroup certificates")
class ResidualActionGoalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(c.fixture("Alcatraz"))
        cls.inventory = cls.analysis.block_inventory
        from bce_v2.automatic_palette import automatic_algorithm_palette
        cls.palette = automatic_algorithm_palette(cls.analysis).palette.with_derived_actions()
        # Infer the pure, order-three twist from endpoint effects, as discovery
        # must. The test does not seed a production goal or identify a loop ID.
        for recipe in cls.palette.recipes:
            action = cls.inventory.action(recipe.permutation)
            support = tuple(i for i, q in enumerate(action.phases) if q)
            if (support and all(action.destinations[i] == i for i in range(len(action.destinations)))
                    and all(cls.inventory.blocks[i].orientation_order == 3 for i in support)):
                cls.twist = recipe
                cls.support = support
                break
        identity = tuple(range(48))
        square = _then(cls.twist.permutation, cls.twist.permutation)
        cls.family = (identity, cls.twist.permutation, square)
        cls.feature = c.BlockFeature("solve_blocks_up_to_actions",
            tuple(cell for i in cls.support for cell in cls.inventory.blocks[i].cells),
            alignment_permutations=cls.family)

    def test_relative_pose_distinguishes_preparation_from_placement_and_zero_phase(self):
        block = _resolve_feature(self.inventory, self.feature)
        solved = _observation(self.inventory.identity(), block, self.feature.kind)
        self.assertEqual(_observation(self.twist.block_action, block, self.feature.kind), solved)
        self.assertNotEqual(_observation(self.twist.block_action, self.support, "orient_slots"),
                            _observation(self.inventory.identity(), self.support, "orient_slots"))
        unequal = next(recipe for recipe in self.palette.recipes
                       if _observation(recipe.block_action, block, self.feature.kind) != solved)
        self.assertNotEqual(_observation(unequal.block_action, block, self.feature.kind), solved)

    def test_transport_is_exact_for_every_palette_endpoint(self):
        block = _resolve_feature(self.inventory, self.feature)
        for first in self.palette.recipes:
            before = _observation(first.block_action, block, self.feature.kind)
            for second in self.palette.recipes:
                self.assertEqual(_feature_successor(before, second.block_action, self.inventory,
                                                    block, self.feature.kind),
                    _observation(self.inventory.action(_then(first.permutation, second.permutation)),
                                 block, self.feature.kind))

    def test_stabilizer_certificate_roundtrip_is_offline(self):
        finish = tuple(c.BlockFeature("solve_block", b.cells) for b in self.inventory.blocks)
        plan = plan_symbolic_stages(self.analysis, strategy="manual", features=(self.feature, *finish))
        self.assertGreater(plan.stages[0].order_after, 1)
        with patch("subprocess.run", side_effect=AssertionError("portable validation must be offline")):
            loaded = symbolic_plan_from_dict(plan.to_dict(), self.inventory,
                self.analysis.loops.generators, expected_order=self.analysis.group_order)
        self.assertEqual(loaded.to_dict(), plan.to_dict())

    def test_family_must_be_a_group_and_preserve_the_region(self):
        with self.assertRaisesRegex(ValueError, "complete group"):
            replace(self.feature, alignment_permutations=self.family[:2])
        moving = next(recipe for recipe in self.palette.recipes
                      if recipe.block_action.destinations[self.support[0]] != self.support[0])
        element, family = tuple(range(48)), []
        while element not in family:
            family.append(element)
            element = _then(element, moving.permutation)
        feature = c.BlockFeature("solve_blocks_up_to_actions",
            self.inventory.blocks[self.support[0]].cells, alignment_permutations=tuple(family))
        with self.assertRaisesRegex(ValueError, "preserve the named component region"):
            _resolve_feature(self.inventory, feature)


if __name__ == "__main__":
    unittest.main()
