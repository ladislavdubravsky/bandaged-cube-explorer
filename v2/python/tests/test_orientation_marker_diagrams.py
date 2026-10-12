"""Anonymous facet markers show phase while hiding unfinished permutations."""

from types import SimpleNamespace
import unittest

import bce_v2 as c
from bce_v2.human_chains import _resolve_feature
from bce_v2.human_diagram_render import recognition_diagram_colors
from bce_v2.human_diagrams import _diagram, _orientation_marker_points
from bce_v2.human_methods import _observe


class OrientationMarkerDiagramTests(unittest.TestCase):
    def stage(self, shape, order):
        inventory = c.BlockInventory(shape)
        slots = tuple(index for index, block in enumerate(inventory.blocks)
                      if block.orientation_order == order)
        cells = tuple(cell for index in slots for cell in inventory.blocks[index].cells)
        feature = c.BlockFeature("orient_slots", cells)
        self.assertEqual(_resolve_feature(inventory, feature), slots)
        method = SimpleNamespace(inventory=inventory, reference_shape=shape)
        stage = SimpleNamespace(number=1, feature=feature, block_index=slots)
        return method, stage

    def diagram(self, method, stage, state):
        action = method.inventory.action(state)
        observation = _observe(action, stage.block_index, stage.feature.kind)
        roles = tuple("current" if index in stage.block_index else "unsolved"
                      for index in range(len(method.inventory.blocks)))
        return _diagram(method, stage, observation, state.sticker_permutation, roles)

    def test_normal_edge_and_corner_markers_ignore_hidden_permutations(self):
        shape = c.Shape(list(range(27)))
        for order in (2, 3):
            with self.subTest(order=order):
                method, stage = self.stage(shape, order)
                solved = self.diagram(method, stage, c.State(shape))
                permuted = self.diagram(method, stage, c.State(shape).apply("U"))
                self.assertEqual(solved.observation, permuted.observation)
                self.assertNotEqual(solved.state, permuted.state)
                self.assertEqual(solved.orientation_markers, permuted.orientation_markers)
                self.assertEqual(recognition_diagram_colors(solved),
                                 recognition_diagram_colors(permuted))
                changed = self.diagram(method, stage, c.State(shape).apply("F"))
                self.assertNotEqual(solved.observation, changed.observation)
                self.assertNotEqual(recognition_diagram_colors(solved),
                                    recognition_diagram_colors(changed))
                hidden_permutation = self.diagram(method, stage, c.State(shape).apply("U F"))
                self.assertEqual(changed.observation, hidden_permutation.observation)
                self.assertEqual(recognition_diagram_colors(changed),
                                 recognition_diagram_colors(hidden_permutation))
                self.assertEqual(len(changed.orientation_markers), len(stage.block_index))
                self.assertTrue(all(index % 9 != 4 for index in changed.orientation_markers))

    def test_symmetric_bandaged_markers_distinguish_all_four_phases(self):
        shape = c.Shape([1] * 9 + [2] * 18)
        method, stage = self.stage(shape, 4)
        pictures = tuple(self.diagram(method, stage, c.State(shape).apply(word))
                         for word in ("", "U", "U2", "U'"))
        self.assertEqual({picture.observation for picture in pictures},
                         {(0,), (1,), (2,), (3,)})
        self.assertEqual(len({recognition_diagram_colors(picture) for picture in pictures}), 4)
        self.assertEqual(len({picture.orientation_markers for picture in pictures}), 4)
        self.assertEqual(len(_orientation_marker_points(method.inventory, stage.block_index)), 1)
        from bce_v2.human_diagram_render import validate_face_colors
        palette = validate_face_colors()
        for picture in pictures:
            colors = recognition_diagram_colors(picture)
            for face_index, face in enumerate("URFDLB"):
                self.assertEqual(colors[face_index * 9 + 4], palette[face])


if __name__ == "__main__":
    unittest.main()
