"""Anonymous destination phases have exact invariant-region stabilizers."""

from copy import deepcopy
from itertools import product
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import (
    _feature_metadata, _feature_successor, _observation, _resolve_feature,
)
from bce_v2.symbolic_chains import _orbit, symbolic_plan_from_dict


def top_edge_feature(inventory):
    return c.BlockFeature("orient_slots", tuple(
        cell for slot in inventory.blocks
        if slot.kind == "Edge" and "U" in slot.compact_name
        for cell in slot.cells))


class SlotOrientationActionTests(unittest.TestCase):
    def setUp(self):
        self.inventory = c.BlockInventory()
        self.feature = top_edge_feature(self.inventory)
        self.slots = _resolve_feature(self.inventory, self.feature)

    def test_orientation_reads_slots_and_ignores_hidden_occupant_identities(self):
        first = c.State.from_cubies(
            corners=list(range(8)), twists=[0]*8, edges=list(range(12)),
            flips=[1, 0, 1, 0] + [0]*8)
        second = c.State.from_cubies(
            corners=[1, 0, 2, 3, 4, 5, 6, 7], twists=[0]*8,
            edges=[1, 0, 2, 3] + list(range(4, 12)),
            flips=[1, 0, 1, 0] + [0]*8)
        observations = [_observation(self.inventory.action(state.sticker_permutation),
                                     self.slots, "orient_slots") for state in (first, second)]
        self.assertEqual(observations[0], observations[1])
        algorithm = "F R U R' U' F'"
        action = self.inventory.action(c.State().apply(algorithm).sticker_permutation)
        expected = _feature_successor(observations[0], action, self.inventory,
                                      self.slots, "orient_slots")
        for state in (first, second):
            after = state.apply(algorithm)
            self.assertEqual(_observation(self.inventory.action(after.sticker_permutation),
                                          self.slots, "orient_slots"), expected)

    def test_incoming_unobserved_slots_are_rejected(self):
        action = self.inventory.action(c.State().apply("R").sticker_permutation)
        with self.assertRaisesRegex(ValueError, "not invariant"):
            _feature_successor((0,)*4, action, self.inventory, self.slots, "orient_slots")

    def test_corner_phase_patterns_use_the_same_anonymous_action(self):
        feature = c.BlockFeature("orient_slots", tuple(
            cell for slot in self.inventory.blocks
            if slot.kind == "Corner" and "U" in slot.compact_name for cell in slot.cells))
        slots = _resolve_feature(self.inventory, feature)
        word = "R U R' U R U2 R'"
        action = self.inventory.action(c.State().apply(word).sticker_permutation)
        for phases in product(range(3), repeat=4):
            if sum(phases)%3:
                continue
            for corners in (list(range(8)), [1, 2, 0, 3, 4, 5, 6, 7]):
                state = c.State.from_cubies(corners=corners, twists=list(phases)+[0]*4,
                                           edges=list(range(12)), flips=[0]*12)
                before = _observation(self.inventory.action(state.sticker_permutation),
                                      slots, "orient_slots")
                expected = _feature_successor(before, action, self.inventory, slots, "orient_slots")
                after = state.apply(word)
                self.assertEqual(_observation(self.inventory.action(after.sticker_permutation),
                                              slots, "orient_slots"), expected)

    def test_orientation_feature_rejects_trivial_or_incompatible_slots(self):
        center = next(slot for slot in self.inventory.blocks if slot.kind == "Center")
        corner = next(slot for slot in self.inventory.blocks if slot.kind == "Corner")
        for cells, message in ((center.cells, "nontrivial"),
                               (self.feature.cells + corner.cells, "compatible")):
            with self.subTest(cells=cells), self.assertRaisesRegex(ValueError, message):
                _resolve_feature(self.inventory, c.BlockFeature("orient_slots", cells))
        bandaged = c.BlockInventory(c.Shape([1]*9 + [2]*18))
        with self.assertRaisesRegex(ValueError, "complete reference blocks"):
            _resolve_feature(bandaged, c.BlockFeature("orient_slots", (0,)))


@unittest.skipUnless(shutil.which("gap"), "GAP is required for exact feature chains")
class SlotOrientationChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(c.Shape(), timeout=60)
        inventory = cls.analysis.block_inventory
        cls.feature = top_edge_feature(inventory)
        cls.prefix = tuple(c.BlockFeature("solve_block", slot.cells)
                           for slot in inventory.blocks
                           if (slot.kind == "Corner" and "D" in slot.compact_name) or
                           (slot.kind == "Edge" and "U" not in slot.compact_name))
        cls.continuation = tuple(c.BlockFeature("solve_block", slot.cells)
                                 for slot in inventory.blocks)
        cls.plan = c.plan_human_stages(
            cls.analysis, strategy="manual",
            features=(*cls.prefix, cls.feature, cls.feature, *cls.continuation),
            backend="symbolic", timeout=60)
        cls.stage = next(stage for stage in cls.plan.stages if stage.feature == cls.feature)

    def test_grouped_orientation_is_the_exact_eight_case_last_layer_stage(self):
        stage = self.stage
        self.assertEqual((stage.order_before, stage.order_after, stage.case_count),
                         (62208, 7776, 8))
        self.assertEqual(stage.solved_observation, (0, 0, 0, 0))
        self.assertEqual(set(stage.observations),
                         {mask for mask in product(range(2), repeat=4) if sum(mask)%2 == 0})
        self.assertEqual((stage.block_index, stage.block_name),
                         _feature_metadata(self.plan.inventory, self.feature))
        self.assertIn(self.feature, self.plan.skipped_features)
        self.assertEqual(self.plan.terminal_order, 1)

    def test_native_transversals_repair_phases_while_allowing_placement(self):
        identity = c.State()
        for representative in self.stage.representatives:
            state = identity.apply(representative.expression.expanded_moves(self.analysis.loops))
            self.assertEqual(_observation(self.plan.inventory.action(state.sticker_permutation),
                                          self.stage.block_index, "orient_slots"),
                             representative.observation)
            self.assertIn(state.sticker_permutation, self.stage.group_before)
        # A U turn belongs to the solved-phase subgroup despite moving occupants.
        moved = c.State().apply("U")
        self.assertIn(moved.sticker_permutation, self.stage.group_after)
        self.assertNotEqual(moved.edges[:4], list(range(4)))

    def test_current_subgroup_has_all_twenty_seven_corner_phase_patterns(self):
        feature = c.BlockFeature("orient_slots", tuple(
            cell for slot in self.plan.inventory.blocks
            if slot.kind == "Corner" and "U" in slot.compact_name for cell in slot.cells))
        slots = _resolve_feature(self.plan.inventory, feature)
        orbit = _orbit(self.plan.inventory, self.stage.group_before, slots, "orient_slots")
        self.assertEqual(set(orbit), {mask for mask in product(range(3), repeat=4) if sum(mask)%3 == 0})

    def test_portable_grouped_chain_validation_is_offline_and_checks_metadata(self):
        record = self.plan.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("portable import must be offline")):
            loaded = symbolic_plan_from_dict(record, self.plan.inventory,
                                             self.analysis.loops.generators,
                                             self.analysis.group_order)
        self.assertEqual(loaded.to_dict(), record)
        changed = deepcopy(record)
        changed["stages"][self.stage.number-1]["block_index"].reverse()
        with self.assertRaises(c.GapError):
            symbolic_plan_from_dict(changed, self.plan.inventory,
                                    self.analysis.loops.generators,
                                    self.analysis.group_order)

    def test_invariance_uses_the_entire_current_group(self):
        # Full cube H has moves bringing unobserved edges into these slots.
        with self.assertRaisesRegex(ValueError, "entire preceding subgroup"):
            _orbit(self.plan.inventory, self.plan.group, self.stage.block_index, "orient_slots")
        with self.assertRaises(c.GapError):
            c.plan_human_stages(
                self.analysis, strategy="manual", features=(self.feature, *self.continuation),
                backend="symbolic", timeout=60)

    def test_four_phase_bandaged_slot_matches_exhaustive_chain(self):
        analysis = c.analyze_isotropy(c.Shape([1]*9 + [2]*18), timeout=30)
        automatic = c.plan_human_stages(analysis, backend="symbolic", timeout=30)
        feature = c.BlockFeature("orient_slots", automatic.stages[0].feature.cells)
        symbolic = c.plan_human_stages(analysis, strategy="manual", features=(feature,),
                                      backend="symbolic", timeout=30)
        explicit = c.plan_human_stages(analysis, strategy="manual", features=(feature,),
                                      max_group_elements=4, timeout=30)
        self.assertEqual(symbolic.stages[0].observations, ((0,), (1,), (2,), (3,)))
        self.assertEqual(explicit.stages[0].observations, symbolic.stages[0].observations)
        self.assertEqual(explicit.stages[0].index, 4)


if __name__ == "__main__":
    unittest.main()
