"""Complete endpoint operations reuse witnessed declarations and teaching IDs."""

import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette, AlgorithmPaletteBody, AlgorithmPaletteSetup
from bce_v2.algorithm_profiles import discover_palette_profiles
from bce_v2.palette_policies import recipe_taught_ids, stage_policy_frontier
from bce_v2.symbolic_groups import (PermutationGroupCertificate, StabilizerLevel,
                                     StrongGenerator)
from test_algorithm_palette import algorithms_for


class DerivedPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loops = c.isotropy_loops(c.Shape())
        cls.algorithms = algorithms_for(cls.loops, {
            "turn": "U", "first": "R", "second": "R' U",
            "known-turn": "R L R' L' U",
            "edge": "R U' R U R U R U' R' U' R2",
            "long-setup": "R U R' U R U2 R'"})
        cls.inventory = c.BlockInventory()

    def test_powers_keep_original_body_and_directed_execution_permission(self):
        declared = AlgorithmPalette.from_algorithms((self.algorithms["turn"],), allow_inverse=False)
        palette = declared.with_derived_actions()
        records = {record["id"]: record for record in palette.recipe_records}
        self.assertEqual(len(palette.bodies), 1)
        self.assertEqual(len(palette.recipes), 3)
        self.assertEqual({record["body_calls"] for record in records.values()}, {1, 2, 3})
        for algorithm in palette.recipes:
            record = records[algorithm.id]
            self.assertEqual(palette.recipe_body_ids[algorithm.id], ("turn",))
            self.assertEqual(recipe_taught_ids(palette)[algorithm.id], frozenset(("turn",)))
            self.assertEqual(c.State().apply(algorithm.turn_sequence).sticker_permutation,
                             algorithm.permutation)
            for identifier in record["original_recipe_ids"]:
                self.assertEqual(records[identifier]["exponent"], 1)
        # Repeating an available positive call three times is permitted even
        # though its endpoint effect equals an unavailable inverse call.
        triple = next(record for record in records.values() if record["body_calls"] == 3)
        self.assertEqual(len(set(triple["original_recipe_ids"])), 1)
        self.assertEqual(declared.metadata["body_count"], palette.metadata["body_count"])

    def test_composition_profiles_restoration_before_filtering_constituents(self):
        palette = AlgorithmPalette.from_algorithms(
            (self.algorithms["first"], self.algorithms["second"]), allow_inverse=False).with_derived_actions()
        records = {record["id"]: record for record in palette.recipe_records}
        wanted = c.State().apply("U").sticker_permutation
        composed = next(algorithm for algorithm in palette.recipes
                        if algorithm.permutation == wanted and
                        set(palette.recipe_body_ids[algorithm.id]) == {"first", "second"})
        with patch("subprocess.run", side_effect=AssertionError("derivation is offline")):
            discovery = discover_palette_profiles(self.inventory, palette)
        profiles = {profile.recipe_id: profile for profile in discovery.profiles}
        profile = profiles[composed.id]
        sources = records[composed.id]["original_recipe_ids"]
        restored = set(profile.fixed_pose_indices) - set.intersection(
            *(set(profiles[source].fixed_pose_indices) for source in sources))
        self.assertTrue(restored)
        for index in restored:
            self.assertTrue(any(index not in profiles[source].fixed_pose_indices for source in sources))
        self.assertEqual(records[composed.id]["body_calls"], 2)
        self.assertEqual(recipe_taught_ids(palette)[composed.id], frozenset(("first", "second")))
        self.assertEqual(composed.expression.evaluate(palette.generators), wanted)
        self.assertEqual(c.State().apply(composed.turn_sequence).sticker_permutation, wanted)

    def test_long_setup_dependencies_and_conjugate_permissions_survive_powers(self):
        palette = AlgorithmPalette((AlgorithmPaletteBody("edge", self.algorithms["edge"], False),),
            setups=(AlgorithmPaletteSetup("long", self.algorithms["long-setup"]),)).with_derived_actions()
        records = {record["id"]: record for record in palette.recipe_records}
        conjugate_powers = [record for record in records.values()
                            if record["derived"] and record["setup_ids"] == ["long"] and
                            len(set(record["original_recipe_ids"])) == 1]
        self.assertTrue(conjugate_powers)
        for record in conjugate_powers:
            self.assertEqual(recipe_taught_ids(palette)[record["id"]], frozenset(("edge", "setup:long")))
            self.assertEqual(record["setup_calls"], record["body_calls"])
            self.assertTrue(all(records[source]["setup_id"] == "long"
                                for source in record["original_recipe_ids"]))
        # A setup has still not been admitted as an adjustment or body.
        self.assertTrue(all(record["adjustment_ids"] == [] for record in records.values()))

    def test_whole_composition_can_cover_a_stage_when_neither_body_preserves_it(self):
        palette = AlgorithmPalette.from_algorithms(
            (self.algorithms["first"], self.algorithms["second"]), allow_inverse=False).with_derived_actions()
        permutation = self.algorithms["turn"].permutation
        point = next(index for index, destination in enumerate(permutation) if index != destination)
        group = PermutationGroupCertificate((permutation,),
            (StrongGenerator(permutation, ((0, 1),)),), (StabilizerLevel(point, (0,)),))
        self.assertTrue(all(body.algorithm.permutation not in group for body in palette.bodies))
        feature = c.BlockFeature("solve_block", (c.UFR,))
        admitted = stage_policy_frontier(self.inventory, group, feature, palette, max_taught_bodies=2)
        self.assertEqual(admitted.status, "completed")
        self.assertTrue(admitted.policies)
        for policy in admitted.policies:
            self.assertEqual(policy.used_body_ids, frozenset(("first", "second")))
            self.assertEqual(policy.case_count, 4)
        restricted = stage_policy_frontier(self.inventory, group, feature, palette, max_taught_bodies=1)
        self.assertEqual(restricted.status, "uncovered")
        self.assertEqual(restricted.policies, ())

    def test_equal_observer_actions_retain_reuse_and_new_teaching_alternatives(self):
        palette = AlgorithmPalette.from_algorithms(
            (self.algorithms["known-turn"], self.algorithms["turn"]), allow_inverse=False)
        permutation = self.algorithms["turn"].permutation
        self.assertEqual(permutation, self.algorithms["known-turn"].permutation)
        point = next(index for index, destination in enumerate(permutation) if index != destination)
        group = PermutationGroupCertificate((permutation,),
            (StrongGenerator(permutation, ((0, 1),)),), (StabilizerLevel(point, (0,)),))
        result = stage_policy_frontier(self.inventory, group,
            c.BlockFeature("solve_block", (c.UFR,)), palette,
            already_taught=("known-turn",), max_taught_bodies=2)
        self.assertEqual(len(result.policies), 2)
        reuse, faster = result.policies
        self.assertEqual(reuse.total_body_ids, frozenset(("known-turn",)))
        self.assertEqual(faster.total_body_ids, frozenset(("known-turn", "turn")))
        self.assertGreater(reuse.mean_htm, faster.mean_htm)

    def test_derivation_is_deterministic_bounded_and_metadata_is_detached(self):
        bodies = tuple(AlgorithmPaletteBody(identifier, self.algorithms[identifier])
                       for identifier in ("first", "second", "edge"))
        palette = AlgorithmPalette(bodies).with_derived_actions(max_derived_recipes=5)
        reordered = AlgorithmPalette(tuple(reversed(bodies))).with_derived_actions(max_derived_recipes=5)
        self.assertEqual({record["id"] for record in palette.recipe_records},
                         {record["id"] for record in reordered.recipe_records})
        self.assertLessEqual(palette.metadata["derived_recipe_count"], 5)
        record = next(record for record in palette.recipe_records if record["derived"])
        record["body_ids"].append("other")
        self.assertNotIn("other", palette.recipe_body_ids[record["id"]])
        self.assertFalse(palette.metadata["coverage_claim"])
        for kwargs, error in (({"max_power": True}, TypeError),
                              ({"max_power": 0}, ValueError),
                              ({"max_composition_length": 3}, ValueError),
                              ({"max_derived_recipes": -1}, ValueError)):
            with self.subTest(kwargs=kwargs), self.assertRaises(error):
                palette.with_derived_actions(**kwargs)


if __name__ == "__main__":
    unittest.main()
