"""Exact staged planning contracts, checked independently on complete groups."""

from dataclasses import FrozenInstanceError, replace
import json
from math import prod
from pathlib import Path
import shutil
import tempfile
import unittest

import bce_v2 as c


IDENTITY = tuple(range(48))


def then(first, second):
    return tuple(second[point] for point in first)


def observation(inventory, permutation, feature):
    block = next(index for index, slot in enumerate(inventory.blocks)
                 if slot.cells == feature.cells)
    action = inventory.action(permutation)
    if feature.kind == "place_block":
        return (action.destinations[block],)
    return (action.destinations[block], action.phases[block])


class BlockFeatureValidationTests(unittest.TestCase):
    def test_feature_rejects_unknown_kind_and_ambiguous_cells(self):
        with self.assertRaises(ValueError):
            c.BlockFeature("orient_block", (0,))
        for cells in ((0, 0), (), (-1,), (27,), (True,)):
            with self.subTest(cells=cells), self.assertRaises((TypeError, ValueError)):
                c.BlockFeature("solve_block", cells)
        self.assertEqual(c.BlockFeature("solve_block", (2, 1)).cells, (1, 2))

    def test_invalid_group_limits_are_rejected(self):
        for limit in (True, 1.5, "4", 0, -1):
            with self.subTest(limit=limit), self.assertRaises((TypeError, ValueError)):
                c.plan_human_stages(c.Shape(), max_group_elements=limit)


@unittest.skipUnless(shutil.which("gap"), "GAP is required for exact stage planning")
class HumanStagePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alcatraz_analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=45)
        cls.alcatraz = c.plan_human_stages(
            cls.alcatraz_analysis, max_group_elements=324, timeout=45)
        cls.fused_face = c.Shape([1] * 9 + [2] * 18)
        cls.fused = c.plan_human_stages(cls.fused_face, max_group_elements=4, timeout=45)

    def assert_complete_chain(self, plan):
        self.assertEqual(plan.status, "completed")
        group = plan.group
        self.assertIsNotNone(group)
        permutations = group.permutations
        inventory = group.inventory
        self.assertEqual(len(permutations), plan.group_order)
        self.assertEqual(len(set(permutations)), plan.group_order)
        self.assertEqual(permutations[0], IDENTITY)
        current = tuple(range(len(permutations)))
        for feature in plan.initial_features:
            solved = observation(inventory, IDENTITY, feature)
            self.assertTrue(all(observation(inventory, p, feature) == solved
                                for p in permutations))
        for number, stage in enumerate(plan.stages, 1):
            with self.subTest(stage=number, feature=stage.feature):
                self.assertEqual(stage.number, number)
                self.assertEqual(stage.members_before, current)
                observed = {index: observation(inventory, permutations[index], stage.feature)
                            for index in current}
                solved = observation(inventory, IDENTITY, stage.feature)
                target = tuple(index for index in current if observed[index] == solved)
                self.assertEqual(stage.members_after, target)
                self.assertEqual(stage.solved_observation, solved)
                self.assertEqual(set(stage.observations), set(observed.values()))
                self.assertEqual(stage.order_before, len(current))
                self.assertEqual(stage.order_after, len(target))
                self.assertEqual(stage.index, len(current) // len(target))
                self.assertEqual(stage.case_count, len(set(observed.values())))
                self.assertEqual(stage.index, stage.case_count)
                self.assertGreater(stage.index, 1)
                for value in stage.observations:
                    fiber = {permutations[index] for index in current if observed[index] == value}
                    representative = next(iter(fiber))
                    self.assertEqual(
                        {then(permutations[index], representative) for index in target}, fiber)
                for feature in stage.implied_features:
                    implied_solved = observation(inventory, IDENTITY, feature)
                    self.assertTrue(all(observation(inventory, permutations[index], feature)
                                        == implied_solved for index in target))
                current = target
        self.assertEqual(tuple(permutations[index] for index in current), (IDENTITY,))
        self.assertEqual(plan.terminal_order, 1)
        self.assertEqual(prod(stage.index for stage in plan.stages), plan.group_order)

    def test_alcatraz_stages_are_exhaustive_actual_coset_actions(self):
        plan = self.alcatraz
        self.assertEqual((plan.group_order, plan.quotient_order, plan.kernel_order),
                         (324, 18, 18))
        self.assert_complete_chain(plan)
        placement_orders = [stage.order_after for stage in plan.stages
                            if stage.feature.kind == "place_block"]
        self.assertEqual(placement_orders[-1], plan.kernel_order)

    def test_every_alcatraz_element_has_an_original_loop_witness(self):
        group = self.alcatraz.group
        initial = c.State(group.inventory.root_shape)
        original_ids = {generator.id for generator in self.alcatraz.analysis.loops}
        for index, permutation in enumerate(group.permutations):
            with self.subTest(element=index):
                expression = group.witness(permutation)
                self.assertEqual(expression, group.witness_for_index(index))
                self.assertTrue(set(expression.base_ids) <= original_ids)
                self.assertEqual(expression.evaluate(group.generators), permutation)
                replayed = initial.apply(expression.expanded_moves(group.generators))
                self.assertEqual(replayed.shape, group.inventory.root_shape)
                self.assertEqual(tuple(replayed.sticker_permutation), permutation)

    def test_fully_solving_blocks_also_gives_a_complete_chain(self):
        plan = c.plan_human_stages(
            self.alcatraz_analysis, strategy="fully_solve_each_block",
            max_group_elements=324, timeout=45)
        self.assert_complete_chain(plan)
        self.assertTrue(all(stage.feature.kind == "solve_block" for stage in plan.stages))

    def test_symmetric_fixed_footprint_requires_four_orientation_cases(self):
        plan = self.fused
        self.assertEqual((plan.group_order, plan.quotient_order, plan.kernel_order), (4, 1, 4))
        self.assert_complete_chain(plan)
        self.assertEqual(len(plan.stages), 1)
        stage = plan.stages[0]
        self.assertEqual(stage.feature.kind, "solve_block")
        self.assertEqual({phase for _, phase in stage.observations}, {0, 1, 2, 3})
        self.assertEqual(stage.index, 4)

    def test_trivial_group_needs_no_stages(self):
        plan = c.plan_human_stages(c.Shape([1] * 27), max_group_elements=1, timeout=45)
        self.assert_complete_chain(plan)
        self.assertEqual(plan.stages, ())
        self.assertEqual((plan.group_order, plan.quotient_order, plan.kernel_order), (1, 1, 1))

    def test_limit_retains_known_order_without_a_partial_plan(self):
        plan = c.plan_human_stages(self.fused.analysis, max_group_elements=3, timeout=45)
        self.assertEqual(plan.status, "limit_reached")
        self.assertEqual(plan.group_order, 4)
        self.assertIsNone(plan.group)
        self.assertEqual(plan.stages, ())
        self.assertIsNone(plan.terminal_order)
        self.assertIsNone(plan.quotient_order)
        self.assertIsNone(plan.kernel_order)

    def test_manual_features_are_complete_and_redundancies_are_reported(self):
        feature = self.fused.stages[0].feature
        plan = c.plan_human_stages(
            self.fused.analysis, strategy="manual", features=(feature, feature),
            max_group_elements=4, timeout=45)
        self.assert_complete_chain(plan)
        self.assertEqual(tuple(stage.feature for stage in plan.stages), (feature,))
        self.assertIn(feature, plan.skipped_features)

    def test_manual_features_reject_residual_orientation_and_partial_blocks(self):
        cells = self.fused.stages[0].feature.cells
        for features in ((), (c.BlockFeature("place_block", cells),),
                         (c.BlockFeature("solve_block", (cells[0],)),)):
            with self.subTest(features=features), self.assertRaises(ValueError):
                c.plan_human_stages(
                    self.fused.analysis, strategy="manual", features=features,
                    max_group_elements=4, timeout=45)

    def test_existing_analysis_cannot_be_silently_rerooted(self):
        with self.assertRaises(ValueError):
            c.plan_human_stages(self.alcatraz_analysis, root=1, timeout=45)

    def test_forged_reduction_must_still_generate_all_original_loops(self):
        loops = c.isotropy_loops(c.Shape())
        forged = c.IsotropyAnalysis(loops, 4, (loops.generators[0].id,), "forged")
        with self.assertRaises(c.GapError):
            c.plan_human_stages(forged, max_group_elements=4, timeout=45)

    def test_prepared_records_cannot_mix_equal_order_groups_at_different_roots(self):
        other = c.plan_human_stages(
            c.Shape([2] * 18 + [1] * 9), max_group_elements=4, timeout=45)
        self.assertEqual(other.group_order, self.fused.group_order)
        self.assertNotEqual(other.inventory.root_shape, self.fused.inventory.root_shape)
        inconsistent = (
            replace(self.fused, analysis=other.analysis),
            replace(self.fused, block_structure=other.block_structure),
            replace(self.fused, group=replace(self.fused.group, analysis=other.analysis)),
        )
        for record in inconsistent:
            with self.subTest(record=record), self.assertRaises((ValueError, c.GapError)):
                c.plan_human_stages(record, max_group_elements=4, timeout=45)

    def test_prepared_kernel_basis_rejects_dependence_and_incorrect_orders(self):
        structure = self.fused.block_structure
        self.assertEqual(len(structure.basis), 1)
        self.assertEqual(structure.basis[0].order, 4)
        incorrect_order = replace(structure.basis[0], order=2)
        for basis in (structure.basis * 2, (incorrect_order,)):
            corrupted = replace(structure, basis=basis)
            with self.subTest(basis=basis), self.assertRaises((ValueError, c.GapError)):
                c.plan_human_stages(corrupted, max_group_elements=4, timeout=45)

    def test_prepared_witness_tree_rejects_wrong_steps_and_forward_parents(self):
        group = self.fused.group
        self.assertEqual(group.parent_indices[1], 0)
        step = group.parent_steps[1]
        steps = (group.parent_steps[0], replace(step, exponent=-step.exponent),
                 *group.parent_steps[2:])
        parents = (group.parent_indices[0], 2, *group.parent_indices[2:])
        corrupted_groups = [replace(group, parent_steps=steps),
                            replace(group, parent_indices=parents)]
        for exponent in (True, 1.0):
            steps = (group.parent_steps[0], replace(step, exponent=exponent),
                     *group.parent_steps[2:])
            corrupted_groups.append(replace(group, parent_steps=steps))
        for corrupted in corrupted_groups:
            record = replace(self.fused, group=corrupted)
            with self.subTest(group=corrupted), self.assertRaises((ValueError, c.GapError)):
                c.plan_human_stages(record, max_group_elements=4, timeout=45)

    def test_records_are_immutable_and_exports_are_deterministic(self):
        with self.assertRaises(FrozenInstanceError):
            self.fused.status = "invalid"
        with self.assertRaises(FrozenInstanceError):
            self.fused.stages[0].number = 42
        record = self.fused.to_dict()
        self.assertEqual(json.loads(self.fused.to_json()), record)
        repeated = c.plan_human_stages(self.fused.analysis, max_group_elements=4, timeout=45)
        self.assertEqual(self.fused.to_json(), repeated.to_json())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            self.fused.save(path)
            self.assertEqual(path.read_text(), self.fused.to_json())


if __name__ == "__main__":
    unittest.main()
