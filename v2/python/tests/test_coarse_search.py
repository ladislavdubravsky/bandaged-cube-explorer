"""Unseeded method discovery and complete global repertoire commitments."""

from dataclasses import replace
from fractions import Fraction
import json
from math import prod
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette, AlgorithmPaletteSetup
from bce_v2.coarse_search import _dominates, _features, discover_coarse_method
from bce_v2.palette_policies import recipe_taught_ids
from bce_v2.symbolic_chains import plan_symbolic_stages, symbolic_plan_from_dict
from bce_v2.symbolic_groups import (PermutationGroupCertificate, StabilizerLevel,
                                     StrongGenerator)


class CoarseSearchDominanceTests(unittest.TestCase):
    def test_a_longer_history_does_not_dominate_a_shorter_search_horizon(self):
        common = dict(taught=frozenset(("known",)), worst=3, counts=(4,))
        shorter = SimpleNamespace(**common, features=(1,), mean=Fraction(3, 2))
        longer = SimpleNamespace(**common, features=(1, 2), mean=Fraction(1))
        self.assertFalse(_dominates(longer, shorter))
        shorter.mean = Fraction(1)
        self.assertTrue(_dominates(shorter, longer))

    def test_tight_goal_bound_keeps_alignment_variant_beside_grouped_placement(self):
        inventory = c.BlockInventory(c.Shape())
        loops = c.isotropy_loops(c.Shape())
        generator = next(g for g in loops.generators if g.turn_sequence == "U")
        algorithm = c.AlgorithmLibrary(loops, (), (), ()).build_algorithm(
            c.LoopExpression.loop(generator.id))
        permutation = algorithm.permutation
        point = next(i for i, destination in enumerate(permutation) if i != destination)
        group = PermutationGroupCertificate((permutation,),
            (StrongGenerator(permutation, ((0, 1),)),), (StabilizerLevel(point, (0,)),))
        palette = AlgorithmPalette((), adjustments=(AlgorithmPaletteSetup("U", algorithm),))
        corners = c.BlockFeature("place_blocks", (c.UFR, c.UFL, c.UBL, c.UBR))
        edges = c.BlockFeature("place_blocks", (c.UR, c.UF, c.UL, c.UB))
        with patch("bce_v2.coarse_search.propose_palette_goals",
                   return_value=(SimpleNamespace(feature=corners), SimpleNamespace(feature=edges))):
            features = _features(inventory, group, palette, None, 2, 4)
        self.assertEqual(features[0], corners)
        self.assertEqual(features[1].kind, "place_blocks_up_to_alignment")
        self.assertEqual(features[1].cells, corners.cells)
        self.assertEqual(len(features[1].alignment_permutations), 4)


@unittest.skipUnless(shutil.which("gap"), "GAP prepares the exact ambient group")
class CoarseSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([1] * 9 + [2] * 18)
        cls.analysis = c.analyze_isotropy(cls.shape, timeout=30)
        builder = c.AlgorithmLibrary(cls.analysis.loops, (), (), ())
        generator = next(g for g in cls.analysis.loops.generators if g.turn_sequence == "U")
        cls.clockwise = replace(builder.build_algorithm(c.LoopExpression.loop(generator.id)),
                                id="clockwise")
        cls.counterclockwise = replace(builder.build_algorithm(c.LoopExpression.power(
            c.LoopExpression.loop(generator.id), -1)), id="counterclockwise")
        cls.palette = AlgorithmPalette.from_algorithms(
            (cls.clockwise, cls.counterclockwise), allow_inverse=False)
        cls.search = discover_coarse_method(cls.analysis, palette=cls.palette,
            max_taught_bodies=1, beam_width=2, max_expansions=4, max_stages=2, timeout=30)

    def test_workspace_and_goals_are_discovered_without_a_manual_ladder(self):
        result = self.search
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.method)
        self.assertFalse(result.metadata["goals_seeded"])
        self.assertFalse(result.metadata["workspace_seeded"])
        self.assertTrue(result.metadata["whole_scramble_method_claim"])
        self.assertFalse(result.metadata["entry_policy_discovered"])
        self.assertFalse(result.metadata["entry_required_at_reference_shape"])
        self.assertTrue(result.metadata["all_reference_group_states"])
        self.assertEqual(result.method.group_order, 4)
        self.assertEqual(prod(stage.index for stage in result.method.stages), 4)
        self.assertTrue(all(stage.order_before > stage.order_after
                            for stage in result.method.stages))
        self.assertLessEqual(max(stage.case_count for stage in result.method.stages), 4)

    def test_compile_retains_budgeted_paths_instead_of_teaching_a_faster_extra_body(self):
        result = self.search
        selected = next(candidate for candidate in result.candidates
                        if candidate.id == result.selected_id)
        taught = recipe_taught_ids(result.method.palette)
        actual = frozenset(identifier for _, _, path in result.method.case_recipes
                           for recipe in path for identifier in taught[recipe])
        self.assertEqual(actual, selected.taught_definition_ids)
        self.assertEqual(len(actual), 1)
        costs = result.method.additive_costs()["htm"]
        self.assertEqual(selected.mean_recipe_htm,
                         Fraction(costs["mean_numerator"], costs["mean_denominator"]))
        self.assertLessEqual(selected.mean_recipe_htm, Fraction(3, 2))
        self.assertTrue(all(len(candidate.taught_definition_ids) <= 1
                            for candidate in result.candidates))
        for word in ("", "U", "U2", "U'"):
            state = c.State(self.shape).apply(word)
            application = result.method.apply(state)
            self.assertEqual(application.status, "solved")
            self.assertTrue(application.state.is_solved)
            self.assertEqual(state.apply(application.turn_sequence), application.state)

    def test_retained_candidate_selection_is_offline_and_leaves_the_original_unchanged(self):
        original = self.search.to_dict()
        alternative = next(candidate for candidate in self.search.candidates
                           if candidate.id != self.search.selected_id)
        self.assertNotEqual(alternative.taught_definition_ids,
                            frozenset(self.search.method.taught_body_ids))
        with patch("subprocess.run", side_effect=AssertionError("selection must not rerun search")):
            switched = self.search.select_candidate(alternative.id)
            self.assertIsNot(switched, self.search)
            self.assertEqual(switched.selected_id, alternative.id)
            self.assertEqual(switched.to_dict()["selected_id"], alternative.id)
            self.assertEqual(frozenset(switched.method.taught_body_ids),
                             alternative.taught_definition_ids)
            self.assertEqual(len(switched.method.taught_body_ids), 1)
            loaded = c.CoarseMethod.from_dict(switched.method.to_dict())
            for word in ("", "U", "U2", "U'"):
                observed = c.State(self.shape).apply(word)
                state = c.State.from_cubies(observed.specification,
                    corners=observed.corners, twists=observed.twists,
                    edges=observed.edges, flips=observed.flips)
                self.assertIsNone(state.scramble)
                application = loaded.apply(state)
                self.assertTrue(application.state.is_solved)
                self.assertEqual(state.apply(application.turn_sequence), application.state)
        self.assertEqual(self.search.to_dict(), original)
        with self.assertRaisesRegex(ValueError, "unknown coarse-method candidate"):
            self.search.select_candidate("missing")

    def test_retained_selection_rechecks_the_global_teaching_budget(self):
        metadata = self.search.metadata
        metadata["settings"]["max_taught_bodies"] = 0
        restricted = replace(self.search, _metadata_json=json.dumps(metadata, sort_keys=True))
        with patch("subprocess.run", side_effect=AssertionError("budget check is offline")):
            with self.assertRaisesRegex(ValueError, "global taught-definition commitment"):
                restricted.select_candidate(self.search.selected_id)

    def test_zero_body_budget_does_not_compile_computational_fallback_corrections(self):
        result = discover_coarse_method(self.analysis, palette=self.palette,
            max_taught_bodies=0, max_expansions=4, max_stages=2, timeout=30)
        self.assertEqual(result.status, "no_method_found")
        self.assertIsNone(result.method)
        self.assertEqual(result.candidates, ())
        self.assertGreater(result.metadata["proposals_without_complete_policy"], 0)
        self.assertFalse(result.metadata["whole_scramble_method_claim"])

    def test_stage_and_expansion_cutoffs_are_honest_about_missing_methods(self):
        for setting in ({"max_stages": 0}, {"max_expansions": 0}, {"max_policy_labels": 0}):
            result = discover_coarse_method(self.analysis, palette=self.palette,
                timeout=30, **setting)
            self.assertEqual(result.status, "no_method_found")
            self.assertIsNone(result.method)
            self.assertTrue(result.metadata["bounded_search"])
            self.assertFalse(result.metadata["exhaustive_method_search"])
            for name, value in setting.items():
                self.assertEqual(result.metadata["settings"][name], value)
            expected = ("depth_limit" if "max_stages" in setting else
                        "expansion_limit" if "max_expansions" in setting else
                        "policy_max_policy_labels")
            self.assertIn(expected, result.metadata["stop_reasons"])

    def test_explicit_unrestricted_domain_is_saved_as_an_entry_contract(self):
        result = discover_coarse_method(self.analysis, palette=self.palette,
            domain_features=(), max_taught_bodies=1, max_expansions=4,
            max_stages=2, timeout=30)
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.metadata["workspace_seeded"])
        self.assertEqual(result.method.domain_features, ())
        self.assertEqual(result.method.group_order, self.analysis.group_order)

    def test_redundant_immobile_domain_still_covers_the_entire_reference_group(self):
        fixed = next(feature for feature in self.search.method.ambient_method.initial_features
                     if feature.kind == "solve_block")
        result = discover_coarse_method(self.analysis, palette=self.palette,
            domain_features=(fixed,), max_taught_bodies=1, max_expansions=4,
            max_stages=2, timeout=30)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.method.domain_features, (fixed,))
        self.assertEqual(result.method.group_order, self.analysis.group_order)
        self.assertTrue(result.metadata["workspace_seeded"])
        self.assertTrue(result.metadata["all_reference_group_states"])
        self.assertTrue(result.metadata["whole_scramble_method_claim"])
        self.assertFalse(result.metadata["entry_required_at_reference_shape"])

    def test_ambient_proof_reuse_retains_exact_new_stage_and_portable_validation(self):
        trusted = self.search.method.ambient_method._symbolic_chain
        features = tuple(stage.feature for stage in trusted.stages)
        plan = plan_symbolic_stages(self.analysis, strategy="manual", features=features,
                                    ambient_plan=trusted, timeout=30)
        self.assertIs(plan.group, trusted.group)
        self.assertIs(plan.placement_group, trusted.placement_group)
        self.assertEqual(plan.terminal_order, 1)
        self.assertEqual(prod(stage.index for stage in plan.stages), 4)
        self.assertEqual([stage.index for stage in plan.stages],
                         [stage.index for stage in trusted.stages])
        with patch("subprocess.run", side_effect=AssertionError("portable proof checks are offline")):
            loaded = symbolic_plan_from_dict(plan.to_dict(), self.analysis.block_inventory,
                self.analysis.loops.generators, expected_order=4)
        self.assertEqual(loaded.to_dict(), plan.to_dict())
        with patch("bce_v2.symbolic_chains._run_gap", side_effect=AssertionError("reject before GAP")):
            with self.assertRaisesRegex(ValueError, "same analysis"):
                plan_symbolic_stages(self.analysis, strategy="manual", features=features,
                    ambient_plan=replace(trusted, _inventory=c.BlockInventory(self.shape)))
            with self.assertRaisesRegex(RuntimeError, "placement/kernel orders"):
                plan_symbolic_stages(self.analysis, strategy="manual", features=features,
                    ambient_plan=replace(trusted, quotient_order=trusted.quotient_order + 1))


if __name__ == "__main__":
    unittest.main()
