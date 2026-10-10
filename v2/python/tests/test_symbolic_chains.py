"""Symbolic stabilizers independently compared with exhaustive small groups."""

from copy import deepcopy
from dataclasses import replace
from math import prod
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import _inverse, _then
from bce_v2.human_methods import _compile_plan
from bce_v2.human_method_io import _fingerprint
from bce_v2.gap_backend import analyze_generators
from bce_v2.symbolic_chains import plan_symbolic_stages, symbolic_plan_from_dict
from bce_v2.symbolic_groups import PermutationGroupCertificate


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

    def test_reduced_and_full_alphabets_certify_the_same_stabilizers(self):
        full = plan_symbolic_stages(self.analysis, generator_basis="full", timeout=30)
        self.assertEqual(tuple((s.feature, s.index) for s in full.stages),
                         tuple((s.feature, s.index) for s in self.plan.stages))
        roots = tuple(g.permutation for g in self.analysis.loops.generators)
        self.assertEqual(self.plan.group.root_generators, roots)
        self.assertEqual(self.plan.group.input_generators, roots)
        self.assertEqual(len(self.plan.algebra_generators), len(self.analysis.generator_ids))
        self.assertLess(len(self.plan.algebra_generators), len(roots))
        for reduced_stage, full_stage in zip(self.plan.stages, full.stages):
            for permutation in self.explicit.group.permutations:
                self.assertEqual(reduced_stage.group_after.contains(permutation),
                                 full_stage.group_after.contains(permutation))
        # Artifacts saved before the reduced-alphabet field used full roots
        # for the placement image and must remain independently loadable.
        legacy = full.to_dict()
        legacy.pop("algebra_generator_ids")
        loaded = symbolic_plan_from_dict(legacy, full.inventory,
                                         self.analysis.loops.generators, 324)
        self.assertEqual(loaded.group_order, 324)
        legacy_method = _compile_plan(full).to_dict()
        legacy_method["symbolic_chain"].pop("algebra_generator_ids")
        legacy_method["fingerprint"] = _fingerprint(legacy_method)
        with patch("subprocess.run", side_effect=AssertionError("legacy imports are offline")):
            loaded_method = c.HumanMethod.from_dict(legacy_method)
        self.assertEqual(loaded_method.to_dict(), legacy_method)

    def test_gap_words_remap_noncontiguous_original_indices_and_ids(self):
        originals = self.analysis.loops.generators
        reversed_roots = tuple(g.permutation for g in reversed(originals))
        reduction = analyze_generators(reversed_roots, timeout=30)
        ids = tuple(originals[len(originals)-1-i].id for i in reduction.generator_indices)
        analysis = replace(self.analysis, generator_ids=ids)
        plan = plan_symbolic_stages(analysis, timeout=30)
        positions = {g.id: i for i, g in enumerate(originals)}
        allowed = {positions[identifier] for identifier in ids}
        self.assertTrue(any(i >= len(ids) for i in allowed))
        self.assertEqual(tuple(g.id for g in plan.algebra_generators), ids)
        self.assertTrue(all(index in allowed for group in
                            (plan.group, *(s.group_after for s in plan.stages))
                            for strong in group.strong_generators
                            for index, exponent in strong.syllables))
        self.assertTrue(all(plan.group.contains(g.permutation) for g in originals))
        for stage in plan.stages:
            for representative in stage.representatives:
                self.assertEqual(representative.expression.evaluate(originals),
                                 representative.permutation)
        loaded = symbolic_plan_from_dict(plan.to_dict(), plan.inventory, originals, 324)
        self.assertEqual(loaded.to_dict(), plan.to_dict())

    def test_incomplete_algebra_basis_cannot_claim_full_native_coverage(self):
        analysis = replace(self.analysis, generator_ids=self.analysis.generator_ids[:1])
        with self.assertRaises(c.GapError):
            plan_symbolic_stages(analysis, timeout=30)
        for identifiers in ((self.analysis.generator_ids[0],) * 2, (999999,)):
            changed = self.plan.to_dict()
            changed["algebra_generator_ids"] = identifiers
            with self.assertRaises(c.GapError):
                symbolic_plan_from_dict(changed, self.plan.inventory,
                                        self.analysis.loops.generators, 324)

    def test_portable_basis_cannot_falsify_the_placement_quotient(self):
        changed = self.plan.to_dict()
        # Keep the full, valid root certificate but falsely declare an empty
        # algebra basis and a compatible trivial placement certificate.
        changed["algebra_generator_ids"] = []
        changed["placement_group"] = PermutationGroupCertificate(
            (), (), (), degree=len(self.plan.inventory.blocks)).to_dict()
        changed["quotient_order"] = "1"
        changed["kernel_order"] = str(self.plan.group_order)
        with self.assertRaisesRegex(c.GapError, "declared algebra basis"):
            symbolic_plan_from_dict(changed, self.plan.inventory,
                                    self.analysis.loops.generators, 324)

    def test_portable_loading_and_membership_need_no_gap(self):
        with patch("subprocess.run", side_effect=AssertionError("offline certificate must not call GAP")):
            loaded = symbolic_plan_from_dict(self.plan.to_dict(), self.plan.inventory,
                                             self.analysis.loops.generators, self.analysis.group_order)
            self.assertEqual(loaded.group_order, 324)
            self.assertTrue(all(loaded.group.contains(p) for p in self.explicit.group.permutations))
            self.assertEqual(loaded.to_dict(), self.plan.to_dict())

    def test_imports_replay_fresh_but_immutable_plan_revalidation_reuses_proof(self):
        original = c.State.apply
        with patch("bce_v2.symbolic_chains.State.apply", autospec=True,
                   side_effect=original) as replay:
            loaded = symbolic_plan_from_dict(self.plan.to_dict(), self.plan.inventory,
                                             self.analysis.loops.generators, 324)
            self.assertGreaterEqual(replay.call_count, len(self.analysis.loops.generators))
            replay.reset_mock()
            loaded.validate(expected_order=324)
            self.assertEqual(replay.call_count, 0)
            with self.assertRaises(c.GapError):
                loaded.validate(expected_order=325)
        changed = replace(loaded, skipped_features=(loaded.stages[0].feature,))
        self.assertIsNone(changed._validation_context)
        with self.assertRaises(c.GapError):
            changed.validate()

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
