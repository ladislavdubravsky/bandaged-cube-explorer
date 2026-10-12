"""Generic residual observers and bounded continuation scoring."""

from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette
from bce_v2.coarse_search import _continuation_basis_htm, _features, _rank
from bce_v2.human_chains import _resolve_feature
from bce_v2.symbolic_groups import (PermutationGroupCertificate, StabilizerLevel,
                                     StrongGenerator, _power)
from test_algorithm_palette import algorithms_for


def cyclic_group(permutation):
    point = next(index for index, destination in enumerate(permutation) if index != destination)
    return PermutationGroupCertificate((permutation,),
        (StrongGenerator(permutation, ((0, 1),)),), (StabilizerLevel(point, (0,)),))


class CoarseOperationProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = c.BlockInventory()
        cls.loops = c.isotropy_loops(c.Shape())
        cls.builder = c.AlgorithmLibrary(cls.loops, (), (), ())
        cls.algorithms = algorithms_for(cls.loops, {
            "upper": "U", "long": "R L R' L' U",
            "edge": "R U' R U R U R U' R' U' R2"})

    def test_equivalent_residual_observers_keep_a_small_family_and_complete_class(self):
        upper = self.algorithms["upper"]
        lower_edge = self.builder.build_algorithm(c.LoopExpression.rotated(
            "x2", self.algorithms["edge"].expression))
        combined = replace(self.builder.build_algorithm(c.LoopExpression.sequence(
            upper.expression, lower_edge.expression)), id="combined")
        fourth = _power(combined.permutation, 4)
        first_point = next(index for index, destination in enumerate(upper.permutation) if index != destination)
        second_point = next(index for index, destination in enumerate(fourth) if index != destination)
        group = PermutationGroupCertificate((combined.permutation,),
            (StrongGenerator(combined.permutation, ((0, 1),)),
             StrongGenerator(fourth, ((0, 4),))),
            (StabilizerLevel(first_point, (0, 1)), StabilizerLevel(second_point, (1,))))
        self.assertEqual(group.order, 12)
        self.assertIn(upper.permutation, group)
        palette = AlgorithmPalette.from_algorithms((upper, combined), allow_inverse=False)
        with patch("bce_v2.coarse_search.propose_palette_goals", return_value=()):
            features = _features(self.inventory, group, palette, None, 64, 16)
        residuals = [feature for feature in features if feature.kind == "solve_blocks_up_to_actions"]
        keys = [(feature.cells, _resolve_feature(self.inventory, feature)) for feature in residuals]
        self.assertEqual(len(keys), len(set(keys)))
        corner_indices = tuple(index for index, destination in enumerate(upper.block_action.destinations)
            if destination != index and self.inventory.blocks[index].orientation_order == 3)
        cells = tuple(sorted(cell for index in corner_indices for cell in self.inventory.blocks[index].cells))
        corner_goals = [feature for feature in residuals if feature.cells == cells]
        self.assertEqual(len(corner_goals), 1)
        self.assertEqual(len(corner_goals[0].alignment_permutations), 4)
        # No smaller arbitrary subsets of this compatible corner support are
        # inserted merely because another recipe happens to preserve them.
        self.assertFalse(any(set(feature.cells) < set(cells) for feature in residuals))
        full_support = tuple(sorted(cell for index, destination in enumerate(combined.block_action.destinations)
            if destination != index or combined.block_action.phases[index]
            for cell in self.inventory.blocks[index].cells))
        self.assertTrue(any(feature.cells == full_support for feature in residuals))

    def test_continuation_basis_scores_complete_endpoints_and_stays_bounded(self):
        group = cyclic_group(self.algorithms["upper"].permutation)
        short = AlgorithmPalette.from_algorithms((self.algorithms["upper"],), allow_inverse=False)
        long = AlgorithmPalette.from_algorithms((self.algorithms["long"],), allow_inverse=False)
        self.assertEqual(_continuation_basis_htm(group, short), 1)
        self.assertEqual(_continuation_basis_htm(group, long), 5)
        self.assertIsNone(_continuation_basis_htm(group, short, maximum_order=3))

    def test_small_case_count_does_not_hide_an_expensive_remaining_family(self):
        common = dict(domain_order=16, group=SimpleNamespace(order=4), taught=frozenset(),
                      worst=4, features=())
        cheap_goal = SimpleNamespace(**common, mean=Fraction(1), counts=(2, 2), continuation_basis_htm=5)
        cheaper_method = SimpleNamespace(**common, mean=Fraction(2), counts=(4,), continuation_basis_htm=1)
        self.assertLess(_rank(cheaper_method, "recognition", partial=True),
                        _rank(cheap_goal, "recognition", partial=True))
        # Completed method selection retains its published recognition-first
        # comparison; the basis only guides bounded unfinished proposals.
        self.assertLess(_rank(cheap_goal, "recognition"), _rank(cheaper_method, "recognition"))


if __name__ == "__main__":
    unittest.main()
