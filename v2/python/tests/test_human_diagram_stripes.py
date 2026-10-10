"""White-sticker marks follow displayed geometry without marking hidden colors."""

from collections import Counter
import importlib.util
from pathlib import Path
import unittest

import bce_v2 as c
from bce_v2.human_diagrams import HumanRecognitionDiagram, recognition_stage_diagrams
from bce_v2.human_diagram_stripes import add_white_sticker_stripes


HAS_PLOTS = importlib.util.find_spec("matplotlib") is not None
RESULTS = Path(__file__).resolve().parents[2] / "research-results"


@unittest.skipUnless(HAS_PLOTS, "optional plots extra")
class WhiteStickerStripeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use("Agg")
        from bce_v2.graphics import _FACE_CELLS
        state = c.State().apply("R U F")
        roles = tuple(("current", "solved", "placed", "unsolved")[cell % 4]
                      for cell in range(27))
        cls.diagram = HumanRecognitionDiagram(
            1, (0,), state, roles, roles,
            tuple(roles[cell] for face in "URFDLB" for cell in _FACE_CELLS[face]),
            0, False)

    def tearDown(self):
        import matplotlib.pyplot as plt
        plt.close("all")

    def figure(self, panels):
        import matplotlib.pyplot as plt
        figure = plt.figure()
        for index in range(panels):
            figure.add_subplot(1, panels, index + 1, projection="3d")
        return figure

    def stripes(self, axis):
        return [collection for collection in axis.collections
                if "white-sticker-stripes" in (collection.get_gid() or "")]

    def count(self, axis):
        return sum(len(collection._segments3d) // 10 for collection in self.stripes(axis))

    def expected(self, diagram, white_faces, *, rotation="", transparent=False, panel=0):
        from bce_v2.graphics import _FACE_CELLS
        from bce_v2.loop_rotations import rotation_tuple
        # Compute expected transformed sticker positions independently of the
        # renderer's cell-image lookup and plane tables.
        normals = {"U": (0, 0, 1), "R": (1, 0, 0), "F": (0, -1, 0),
                   "D": (0, 0, -1), "L": (-1, 0, 0), "B": (0, 1, 0)}
        current_rotation = rotation_tuple(rotation)
        spatial = lambda point: tuple((1 if value > 0 else -1) * point[abs(value) - 1]
                                      for value in current_rotation)
        result = Counter()
        for face_index, face in enumerate("URFDLB"):
            normal = spatial(normals[face])
            coordinate = next(index for index, value in enumerate(normal) if value)
            direction = normal[coordinate]
            for sticker, source_cell in enumerate(_FACE_CELLS[face]):
                index = face_index * 9 + sticker
                role = diagram.sticker_roles[index]
                if diagram.state.facelets[index] not in white_faces:
                    continue
                if role != "current" and sticker != 4:
                    continue
                if not transparent and normal not in [normals[letter]
                        for letter in ("UFR" if panel % 2 == 0 else "BLD")]:
                    continue
                original_center = (source_cell % 3 - 1, 1 - source_cell // 3 % 3,
                                   1 - source_cell // 9)
                center = tuple(value + 1.5 for value in spatial(original_center))
                coordinates = tuple(int(value) for value in center)
                result[coordinate, direction, coordinates] += 1
        return result

    def rendered(self, axis):
        from math import floor
        result = Counter()
        for collection in self.stripes(axis):
            segments = collection._segments3d
            self.assertEqual(len(segments) % 10, 0)
            self.assertTrue(all(width < .5 for width in collection.get_linewidths()))
            for start in range(0, len(segments), 10):
                positions = []
                for segment in segments[start:start + 10]:
                    coordinate = next(index for index in range(3)
                                      if abs(segment[0][index] - segment[1][index]) < 1e-8)
                    plane = segment[0][coordinate]
                    self.assertTrue(abs(plane + .004) < 1e-8 or abs(plane - 3.004) < 1e-8)
                    direction = 1 if plane > 0 else -1
                    coordinates = [floor((first + second) / 2)
                                   for first, second in zip(segment[0], segment[1])]
                    coordinates[coordinate] = 2 if direction == 1 else 0
                    self.assertTrue(all(0 <= index <= 2 for index in coordinates))
                    positions.append((coordinate, direction, tuple(coordinates)))
                    others = [index for index in range(3) if index != coordinate]
                    for endpoint in segment:
                        local = [endpoint[index] - coordinates[index] for index in others]
                        self.assertTrue(all(-1e-8 <= value <= 1. + 1e-8 for value in local))
                        self.assertTrue(any(abs(value) < 1e-8 or abs(value - 1.) < 1e-8
                                            for value in local))
                    self.assertAlmostEqual(segment[1][others[0]] - segment[0][others[0]],
                                           segment[1][others[1]] - segment[0][others[1]])
                self.assertEqual(len(set(positions)), 1)
                result[positions[0]] += 1
        return result

    def test_named_hex_and_rgb_white_are_equivalent_and_ordinary_colors_have_no_marks(self):
        for value in ("white", "#ffffff", (1., 1., 1.)):
            figure = self.figure(2)
            add_white_sticker_stripes(figure, self.diagram, {"U": value})
            for panel, axis in enumerate(figure.axes):
                self.assertEqual(self.rendered(axis), self.expected(self.diagram, {"U"}, panel=panel))
            self.assertGreater(sum(self.count(axis) for axis in figure.axes), 0)
        for palette in (None, {"U": "blue", "L": "orange"}):
            figure = self.figure(2)
            add_white_sticker_stripes(figure, self.diagram, palette)
            self.assertTrue(all(not axis.collections for axis in figure.axes))

    def test_opposite_views_mark_only_centers_and_targets_leaving_grey_solved_unmarked(self):
        figure = self.figure(2)
        palette = dict.fromkeys("URFDLB", "white")
        add_white_sticker_stripes(figure, self.diagram, palette)
        for panel, axis in enumerate(figure.axes):
            self.assertEqual(self.rendered(axis), self.expected(self.diagram, set("URFDLB"), panel=panel))
            for collection in self.stripes(axis):
                self.assertFalse(collection.get_gid().endswith("solved"))
                self.assertEqual(collection.get_alpha(), 1.)
        self.assertEqual(sum(self.count(axis) for axis in figure.axes),
                         sum(role == "current" or index % 9 == 4
                             for index, role in enumerate(self.diagram.sticker_roles)))

    def test_transparent_marks_only_centers_and_targets_including_rear_faces(self):
        figure = self.figure(1)
        add_white_sticker_stripes(figure, self.diagram, dict.fromkeys("URFDLB", "white"),
                                 transparent=True)
        axis = figure.axes[0]
        self.assertEqual(self.rendered(axis), self.expected(self.diagram, set("URFDLB"), transparent=True))
        self.assertEqual(self.count(axis), sum(role == "current" or index % 9 == 4
                                              for index, role in enumerate(self.diagram.sticker_roles)))
        self.assertTrue(any(direction < 0 for (_, direction, _) in self.rendered(axis)))
        for collection in self.stripes(axis):
            self.assertEqual(collection.get_alpha(), .95 if collection.get_gid().endswith("current") else 1.)

    def test_all_24_grips_preserve_white_sticker_identity_and_both_camera_sides(self):
        import matplotlib.pyplot as plt
        from bce_v2.loop_rotations import _CANONICAL_WORDS
        for word in _CANONICAL_WORDS.values():
            for transparent in (False, True):
                figure = self.figure(1 if transparent else 2)
                add_white_sticker_stripes(figure, self.diagram, {"U": "white", "F": "white"},
                                         rotation=word, transparent=transparent)
                for panel, axis in enumerate(figure.axes):
                    self.assertEqual(self.rendered(axis), self.expected(
                        self.diagram, {"U", "F"}, rotation=word, transparent=transparent, panel=panel))
                plt.close(figure)

    def test_orientation_variants_and_gallery_panels_use_their_own_sticker_roles(self):
        import matplotlib.pyplot as plt
        method = c.load_human_repertoire(RESULTS / "alcatraz-recognition-repertoire.json")
        variants = next(variants for stage in method.method.stages
                        for variants in recognition_stage_diagrams(method, stage.number).values()
                        if len(variants) > 1)
        self.assertGreater(len({diagram.phase for diagram in variants}), 1)
        for transparent in (False, True):
            figure = self.figure(len(variants) * (1 if transparent else 2))
            add_white_sticker_stripes(figure, variants, {"U": "white"}, transparent=transparent)
            for panel, axis in enumerate(figure.axes):
                diagram = variants[panel // (1 if transparent else 2)]
                self.assertEqual(self.rendered(axis), self.expected(
                    diagram, {"U"}, transparent=transparent, panel=panel))
            plt.close(figure)

    def test_white_markings_stay_visible_above_their_own_block_surfaces(self):
        from bce_v2.human_diagram_render import recognition_diagram_figure
        for mode in c.DiagramMode:
            figure = recognition_diagram_figure(self.diagram, diagram_mode=mode,
                                               face_colors=dict.fromkeys("URFDLB", "white"))
            figure.canvas.draw()
            for axis in figure.axes:
                stripes = self.stripes(axis)
                self.assertTrue(stripes)
                mesh = [collection for collection in axis.collections if collection not in stripes]
                self.assertGreater(min(collection.zorder for collection in stripes),
                                   max(collection.zorder for collection in mesh))


if __name__ == "__main__":
    unittest.main()
