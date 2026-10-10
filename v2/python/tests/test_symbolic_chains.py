"""Symbolic stabilizers independently compared with exhaustive small groups."""

from copy import deepcopy
from math import prod
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import _inverse, _then
from bce_v2.symbolic_chains import plan_symbolic_stages, symbolic_plan_from_dict


def observation(inventory, permutation, stage):
    action = inventory.action(permutation)
    block = stage.block_index
    if stage.feature.kind == "place_block":
        return (action.destinations[block],)
    return (action.destinations[block], action.phases[block])


@unittest.skipUnless(shutil.which("gap"), "GAP is required to construct symbolic chains")
class SymbolicChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=30)
        cls.explicit = c.plan_human_stages(cls.analysis, max_group_elements=324, timeout=30)
        cls.plan = plan_symbolic_stages(cls.analysis, timeout=30)

    def test_symbolic_stabilizers_match_all_small_group_elements(self):
        plan = self.plan
        self.assertEqual((plan.group_order, plan.quotient_order, plan.kernel_order), (324, 18, 18))
        self.assertEqual(plan.initial_features, self.explicit.initial_features)
        self.assertEqual(tuple((s.feature, s.index) for s in plan.stages),
                         tuple((s.feature, s.index) for s in self.explicit.stages))
        current = set(self.explicit.group.permutations)
        for stage in plan.stages:
            self.assertEqual({p for p in self.explicit.group.permutations
                              if stage.group_before.contains(p)}, current)
            target = {p for p in current
                      if observation(plan.inventory, p, stage) == stage.solved_observation}
            self.assertEqual(stage.group_after.order, len(target))
            self.assertEqual({p for p in self.explicit.group.permutations
                              if stage.group_after.contains(p)}, target)
            corrections = {r.observation: _inverse(r.permutation) for r in stage.representatives}
            for permutation in current:
                corrected = _then(permutation, corrections[observation(plan.inventory, permutation, stage)])
                self.assertIn(corrected, target)
            current = target
        self.assertEqual(current, {tuple(range(48))})
        self.assertEqual(prod(s.index for s in plan.stages), plan.group_order)

    def test_every_transversal_retains_a_legal_original_loop_witness(self):
        initial = c.State(self.plan.inventory.root_shape)
        original_ids = {g.id for g in self.analysis.loops.generators}
        for stage in self.plan.stages:
            for representative in stage.representatives:
                self.assertLessEqual(set(representative.expression.base_ids), original_ids)
                replay = initial.apply(representative.expression.expanded_moves(self.analysis.loops.generators))
                self.assertEqual(replay.shape, initial.shape)
                self.assertEqual(tuple(replay.sticker_permutation), representative.permutation)

    def test_portable_loading_and_membership_need_no_gap(self):
        with patch("subprocess.run", side_effect=AssertionError("offline certificate must not call GAP")):
            loaded = symbolic_plan_from_dict(self.plan.to_dict(), self.plan.inventory,
                                             self.analysis.loops.generators, self.analysis.group_order)
            self.assertEqual(loaded.group_order, 324)
            self.assertTrue(all(loaded.group.contains(p) for p in self.explicit.group.permutations))
            self.assertEqual(loaded.to_dict(), self.plan.to_dict())

    def test_portable_chain_rejects_order_observation_and_literal_word_corruption(self):
        records = []
        changed = deepcopy(self.plan.to_dict())
        # Preserve H=P*K so the independent placement certificate matters.
        changed["quotient_order"] = "9"
        changed["kernel_order"] = "36"
        records.append(changed)
        changed = deepcopy(self.plan.to_dict())
        changed["stages"][0]["representatives"][0]["observation"] = [999]
        records.append(changed)
        changed = deepcopy(self.plan.to_dict())
        witness = changed["stages"][0]["representatives"][0]["expression"]
        changed["stages"][0]["representatives"][0]["expression"] = {
            "kind": "turns", "moves": "U", "children": [witness]}
        records.append(changed)
        changed = deepcopy(self.plan.to_dict())
        changed["stages"][0]["number"] = True
        records.append(changed)
        changed = deepcopy(self.plan.to_dict())
        changed["gap_version"] = True
        records.append(changed)
        changed = deepcopy(self.plan.to_dict())
        changed["stages"][0]["solved_observation"][0] = float(
            changed["stages"][0]["solved_observation"][0])
        records.append(changed)
        for record in records:
            with self.subTest(record=record["quotient_order"]), self.assertRaises(c.GapError):
                symbolic_plan_from_dict(record, self.plan.inventory,
                                        self.analysis.loops.generators, self.analysis.group_order)

    def test_manual_chain_preserves_redundancy_and_rejects_incomplete_features(self):
        features = tuple(s.feature for s in self.plan.stages)
        plan = plan_symbolic_stages(self.analysis, strategy="manual",
                                    features=features + features[-1:], timeout=30)
        self.assertEqual(plan.skipped_features, features[-1:])
        self.assertEqual(plan.terminal_order, 1)
        with self.assertRaisesRegex(ValueError, "leave a subgroup"):
            plan_symbolic_stages(self.analysis, strategy="manual", features=(), timeout=30)

    def test_fullsolve_strategy_is_an_exact_feature_chain(self):
        plan = plan_symbolic_stages(self.analysis, strategy="fully_solve_each_block", timeout=30)
        self.assertTrue(all(s.feature.kind == "solve_block" for s in plan.stages))
        self.assertEqual(prod(s.index for s in plan.stages), 324)
        self.assertEqual(plan.terminal_order, 1)

    def test_trivial_group_and_symmetric_fixed_footprint(self):
        for shape, order in ((c.Shape([1]*27), 1), (c.Shape([1]*9+[2]*18), 4)):
            analysis = c.analyze_isotropy(shape, timeout=30)
            plan = plan_symbolic_stages(analysis, timeout=30)
            self.assertEqual((plan.group_order, plan.quotient_order, plan.kernel_order), (order, 1, order))
            self.assertEqual(plan.placement_group.degree, len(plan.inventory.blocks))
            self.assertEqual(plan.terminal_order, 1)
            if order == 4:
                self.assertEqual(plan.stages[0].observations,
                                 tuple((plan.stages[0].block_index, phase) for phase in range(4)))


if __name__ == "__main__":
    unittest.main()
