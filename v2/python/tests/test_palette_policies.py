"""Global repertoire choices retain complete, directed correction policies."""

from dataclasses import replace
from fractions import Fraction
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette, AlgorithmPaletteSetup
from bce_v2.human_chains import _feature_successor
from bce_v2.palette_policies import recipe_taught_ids, stage_policy_frontier
from bce_v2.symbolic_groups import (PermutationGroupCertificate, StabilizerLevel,
                                     StrongGenerator)


class StagePalettePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = c.BlockInventory(c.Shape())
        cls.loops = c.isotropy_loops(c.Shape())
        cls.builder = c.AlgorithmLibrary(cls.loops, (), (), ())
        cls.leaves = {g.turn_sequence: c.LoopExpression.loop(g.id)
                      for g in cls.loops.generators}
        cls.clockwise = cls.algorithm("clockwise", "U")
        cls.counterclockwise = cls.algorithm("counterclockwise", "U'")
        permutation = cls.clockwise.permutation
        point = next(i for i, destination in enumerate(permutation) if i != destination)
        # This exact cyclic certificate is built offline, without GAP.
        cls.group = PermutationGroupCertificate(
            (permutation,), (StrongGenerator(permutation, ((0, 1),)),),
            (StabilizerLevel(point, (0,)),))
        cls.feature = c.BlockFeature("solve_block", (c.UFR,))
        cls.palette = AlgorithmPalette.from_algorithms(
            (cls.clockwise, cls.counterclockwise), allow_inverse=False)

    @classmethod
    def algorithm(cls, identifier, word):
        proof = c.LoopExpression.sequence(*(c.LoopExpression.power(
            cls.leaves[token[0]], 2 if token.endswith("2") else
            -1 if token.endswith("'") else 1) for token in word.split()))
        return replace(cls.builder.build_algorithm(c.LoopExpression.turns(word, proof)),
                       id=identifier)

    def search(self, palette=None, **kwargs):
        return stage_policy_frontier(self.inventory, self.group, self.feature,
                                     self.palette if palette is None else palette, **kwargs)

    def assert_complete_replay(self, policy, palette):
        algorithms = {algorithm.id: algorithm for algorithm in palette.recipes}
        for observation, recipe, cost in zip(policy.observations, policy.recipes, policy.costs):
            current = observation
            for identifier in recipe:
                current = _feature_successor(current,
                    self.inventory.action(algorithms[identifier].permutation),
                    self.inventory, policy.block_index, policy.feature.kind)
            self.assertEqual(current, policy.solved_observation)
            self.assertEqual(cost, sum(algorithms[identifier].htm_length for identifier in recipe))

    def test_known_body_policy_survives_alongside_faster_new_body_policy(self):
        with patch("subprocess.run", side_effect=AssertionError("offline policy search")):
            result = self.search(already_taught=("clockwise",), max_taught_bodies=2)
        self.assertTrue(result.complete_search)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.policies), 2)
        reuse, faster = result.policies
        self.assertEqual(reuse.total_body_ids, frozenset(("clockwise",)))
        self.assertEqual((reuse.mean_htm, reuse.worst_htm), (Fraction(3, 2), 3))
        self.assertEqual(faster.total_body_ids, frozenset(("clockwise", "counterclockwise")))
        self.assertEqual((faster.mean_htm, faster.worst_htm), (1, 2))
        for policy in result.policies:
            self.assert_complete_replay(policy, self.palette)

    def test_budget_forces_reuse_instead_of_unrestricted_locally_shortest_paths(self):
        result = self.search(already_taught=("clockwise",), max_taught_bodies=1)
        self.assertEqual(len(result.policies), 1)
        self.assertEqual(result.policies[0].mean_htm, Fraction(3, 2))
        self.assertEqual(result.policies[0].used_body_ids, frozenset(("clockwise",)))
        self.assertEqual(result.total_subsets, 1)

    def test_distinct_one_body_choices_are_incomparable(self):
        result = self.search(max_taught_bodies=1)
        self.assertTrue(result.complete_search)
        self.assertEqual({policy.total_body_ids for policy in result.policies},
                         {frozenset(("clockwise",)), frozenset(("counterclockwise",))})
        self.assertEqual(result.evaluated_subsets, 3)

    def test_directed_paths_repeat_permitted_sign_without_granting_inverse(self):
        palette = AlgorithmPalette.from_algorithms((self.clockwise,), allow_inverse=False)
        policy = self.search(palette, max_taught_bodies=1).policies[0]
        self.assertEqual(policy.worst_htm, 3)
        self.assertEqual(len(set(step for recipe in policy.recipes for step in recipe)), 1)
        self.assert_complete_replay(policy, palette)
        self.assertTrue(all(record["exponent"] == 1 for record in palette.recipe_records))

    def test_zero_body_budget_allows_short_explicit_adjustments(self):
        palette = AlgorithmPalette((), adjustments=(AlgorithmPaletteSetup("align", self.clockwise),))
        result = self.search(palette, max_taught_bodies=0)
        self.assertEqual(result.status, "completed")
        policy = result.policies[0]
        self.assertEqual(policy.used_body_ids, frozenset())
        self.assertEqual(policy.used_adjustment_ids, frozenset(("align",)))
        self.assertEqual(policy.body_calls, (0, 0, 0, 0))
        self.assert_complete_replay(policy, palette)
        missing = self.search(max_taught_bodies=0)
        self.assertEqual(missing.status, "uncovered")
        self.assertTrue(missing.complete_search)
        self.assertEqual(missing.policies, ())
        self.assertEqual(len(missing.observations), 4)

    def test_nonpreserving_bodies_are_filtered_before_subset_search(self):
        palette = AlgorithmPalette.from_algorithms(
            (self.clockwise, self.algorithm("other-face", "R")), allow_inverse=False)
        result = self.search(palette, max_taught_bodies=1)
        self.assertEqual(result.total_subsets, 2)
        self.assertEqual(result.policies[0].used_body_ids, frozenset(("clockwise",)))
        self.assertTrue(all("other-face" not in identifier for identifier in result.eligible_recipe_ids))

    def test_incomplete_domains_and_bounded_quality_search_are_explicit(self):
        result = self.search(max_observations=3)
        self.assertEqual(result.status, "orbit_limit")
        self.assertFalse(result.complete_search)
        self.assertEqual(result.observations, ())
        self.assertEqual(result.policies, ())
        self.assertEqual(result.stop_reasons, ("max_observations",))
        result = self.search(max_policy_labels=2)
        self.assertEqual(result.status, "bounded")
        self.assertFalse(result.complete_search)
        self.assertEqual(result.evaluated_subsets, 2)
        self.assertEqual(result.total_subsets, 4)
        self.assertEqual(result.stop_reasons, ("max_policy_labels",))
        self.assertEqual(len(result.policies), 1)
        self.assert_complete_replay(result.policies[0], self.palette)
        result = self.search(max_candidates=1)
        self.assertEqual(result.status, "bounded")
        self.assertEqual(result.stop_reasons, ("max_candidates",))
        self.assertEqual(len(result.policies), 1)
        result = self.search(max_policy_labels=0)
        self.assertEqual(result.policies, ())
        self.assertFalse(result.complete_search)

    def test_invalid_observer_invariance_and_inputs_are_not_search_cutoffs(self):
        with self.assertRaisesRegex(ValueError, "not invariant"):
            stage_policy_frontier(self.inventory, self.group,
                c.BlockFeature("orient_slots", (c.UFR,)), self.palette)
        with self.assertRaisesRegex(ValueError, "undeclared"):
            self.search(already_taught=("unknown",))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.search(already_taught=("clockwise",), max_taught_bodies=0)
        with self.assertRaisesRegex(TypeError, "integer"):
            self.search(max_policy_labels=True)

    def test_alignment_permission_is_checked_against_entire_preceding_subgroup(self):
        feature = c.BlockFeature("place_blocks_up_to_alignment",
            (c.UFR, c.UFL, c.UBL, c.UBR),
            alignment_permutations=tuple(c.State().apply(word).sticker_permutation
                                         for word in ("", "U", "U2", "U'")))
        allowed = stage_policy_frontier(self.inventory, self.group, feature, self.palette)
        self.assertEqual(allowed.status, "completed")
        self.assertEqual(len(allowed.observations), 1)
        identity_group = PermutationGroupCertificate((self.clockwise.permutation,), (), (),
                                                     input_generators=())
        with self.assertRaisesRegex(ValueError, "entire preceding subgroup"):
            stage_policy_frontier(self.inventory, identity_group, feature, self.palette)

    def test_long_adjustment_cannot_bypass_taught_definition_budget(self):
        # Commuting R/L turns make this a valid, deliberately long U witness.
        long_word = self.algorithm("long", "R L R' L' U")
        self.assertEqual(long_word.htm_length, 5)
        palette = AlgorithmPalette((), adjustments=(AlgorithmPaletteSetup("long", long_word),))
        result = self.search(palette, max_taught_bodies=0)
        self.assertEqual(result.status, "uncovered")
        policy = self.search(palette, max_taught_bodies=1).policies[0]
        self.assertEqual(policy.used_body_ids, frozenset(("adjustment:long",)))
        self.assertEqual(policy.declared_body_ids, frozenset())
        self.assertEqual(policy.long_definition_ids, frozenset(("adjustment:long",)))
        self.assert_complete_replay(policy, palette)
        relaxed = self.search(palette, max_taught_bodies=0, max_short_setup_htm=5)
        self.assertEqual(relaxed.policies[0].used_body_ids, frozenset())

    def test_long_setup_and_adjustment_share_word_and_identical_declared_body(self):
        long_word = self.algorithm("long-body", "R L R' L' U")
        setup = AlgorithmPaletteSetup("long-setup", long_word)
        adjustment = AlgorithmPaletteSetup("long-adjustment", long_word)
        palette = AlgorithmPalette.from_algorithms((self.clockwise,),
            setups=(long_word,), adjustments=(long_word,), allow_inverse=True)
        records = {record["id"]: record for record in palette.recipe_records}
        taught = recipe_taught_ids(palette)
        for identifier, record in records.items():
            expected = {"clockwise"} if record["body_id"] is not None else set()
            if record["setup_id"] is not None or record["adjustment_id"] is not None:
                expected.add("setup:long-body")
            self.assertEqual(taught[identifier], frozenset(expected))
        palette = AlgorithmPalette.from_algorithms((long_word,), setups=(long_word,),
            adjustments=(long_word,), allow_inverse=True)
        self.assertTrue(all(identifiers == frozenset(("long-body",))
                            for identifiers in recipe_taught_ids(palette).values()))
        with self.assertRaises(TypeError):
            taught["unknown"] = frozenset()
        # The distinct setup/adjustment names still share the exact learned word.
        palette = AlgorithmPalette((), (setup,), (adjustment,))
        self.assertEqual(set(recipe_taught_ids(palette).values()),
                         {frozenset(("setup:long-setup",))})


if __name__ == "__main__":
    unittest.main()
