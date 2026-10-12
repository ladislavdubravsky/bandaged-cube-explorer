"""Continuation workspace geometry suggests anchors without cubie cases."""

from dataclasses import FrozenInstanceError
from fractions import Fraction
import json
import unittest

import bce_v2 as c
from bce_v2.block_actions import _coordinates
from bce_v2.workspace_goals import propose_workspace_anchors


def lower_workspace(inventory):
    return tuple(cell for block in inventory.blocks for cell in block.cells
                 if block.movable and (block.corners or block.edges) and
                 all(_coordinates(member)[2] < 1 for member in block.cells))


class WorkspaceAnchorTests(unittest.TestCase):
    def test_ordinary_cross_is_inferred_from_free_face_and_axis_distance(self):
        inventory = c.BlockInventory()
        result = propose_workspace_anchors(inventory, lower_workspace(inventory))
        self.assertEqual(result.features, (c.BlockFeature("solve_blocks", (c.DR, c.DF, c.DL, c.DB)),))
        self.assertEqual(result.metadata["free_faces"], ("U",))
        self.assertEqual(result.evidence[0].free_face, "U")
        self.assertEqual(result.evidence[0].opposite_face, "D")
        self.assertEqual(result.evidence[0].mean_squared_axis_distance, Fraction(1))
        self.assertEqual(len(result.evidence[0].opposite_component_indices), 8)
        self.assertFalse(result.to_dict()["coverage_claim"])
        self.assertEqual(json.loads(json.dumps(result.to_dict())), result.to_dict())

    def test_fused_component_is_never_partially_selected_by_distance(self):
        labels = [0] * 27
        labels[c.DFR] = labels[c.DF] = 1
        inventory = c.BlockInventory(c.Shape(labels))
        result = propose_workspace_anchors(inventory, lower_workspace(inventory))
        self.assertEqual(result.features, (c.BlockFeature("solve_blocks", (c.DR, c.DL, c.DB)),))
        self.assertNotIn(c.DF, result.features[0].cells)
        self.assertNotIn(c.DFR, result.features[0].cells)
        with self.assertRaisesRegex(ValueError, "complete physical components"):
            propose_workspace_anchors(inventory, (c.DF,))

    def test_single_fused_face_is_one_component_even_when_it_has_nine_cells(self):
        inventory = c.BlockInventory(c.Shape([1] * 9 + [2] * 18))
        result = propose_workspace_anchors(inventory, tuple(range(9)), max_components=1)
        self.assertEqual(result.features, (c.BlockFeature("solve_blocks", tuple(range(9))),))
        self.assertEqual(result.metadata["free_faces"], ("D",))
        self.assertEqual(result.evidence[0].mean_squared_axis_distance, Fraction(4, 3))
        self.assertEqual(len(result.evidence[0].block_indices), 1)

    def test_equivalent_free_faces_deduplicate_feature_but_preserve_evidence(self):
        inventory = c.BlockInventory()
        result = propose_workspace_anchors(inventory, (c.DFR,))
        self.assertEqual(result.features, (c.BlockFeature("solve_blocks", (c.DFR,)),))
        self.assertEqual(len(result.evidence), 3)
        self.assertEqual(set(result.metadata["free_faces"]), {"U", "L", "B"})

    def test_limits_skip_whole_oversized_tie_and_report_truncation(self):
        inventory = c.BlockInventory()
        domain = lower_workspace(inventory)
        tied = propose_workspace_anchors(inventory, domain, max_components=3)
        self.assertEqual(tied.features, ())
        self.assertEqual(tied.metadata["oversized_ties"], (("U", 4),))
        zero = propose_workspace_anchors(inventory, domain, max_candidates=0)
        self.assertEqual(zero.features, ())
        self.assertTrue(zero.metadata["candidates_bounded"])
        self.assertEqual(zero.evidence, ())
        for key, value in (("max_candidates", True), ("max_candidates", -1),
                           ("max_components", True), ("max_components", 0)):
            with self.subTest(key=key, value=value), self.assertRaises((TypeError, ValueError)):
                propose_workspace_anchors(inventory, domain, **{key: value})

    def test_empty_and_unmarked_domains_make_no_fictitious_anchor(self):
        inventory = c.BlockInventory()
        self.assertEqual(propose_workspace_anchors(inventory, ()).features, ())
        self.assertEqual(propose_workspace_anchors(inventory, (c.U,)).features, ())
        all_cells = tuple(cell for block in inventory.blocks for cell in block.cells)
        result = propose_workspace_anchors(inventory, all_cells)
        self.assertEqual(result.metadata["free_faces"], ())
        self.assertEqual(result.features, ())
        with self.assertRaises(TypeError):
            result.metadata["coverage_claim"] = True
        with self.assertRaises(FrozenInstanceError):
            result.features = ()


if __name__ == "__main__":
    unittest.main()
